from flask import current_app
from celery import Celery
from simpledoge import db, coinserv
from simpledoge.models import (
    Share, Block, OneMinuteShare, Payout, Transaction, Blob, last_block_time,
    last_block_share_id, FiveMinuteShare, Status, OneMinuteReject,
    OneMinuteTemperature, FiveMinuteReject, OneMinuteHashrate)
from sqlalchemy.sql import func
from cryptokit import bits_to_shares, bits_to_difficulty
from pprint import pformat
from bitcoinrpc import CoinRPCException
from celery.utils.log import get_task_logger

import requests
import json
import sqlalchemy
import logging
import datetime

logger = get_task_logger(__name__)
celery = Celery('simpledoge')


@celery.task(bind=True)
def update_coin_transaction(self):
    """
    Loops through all immature transactions
    """
    try:
        # Select all unconfirmed transactions
        unconfirmed = Transaction.query.filter_by(confirmed=False)
        for tx in unconfirmed:
            # Check to see if the transaction hash exists in the block chain
            try:
                t = coinserv.gettransaction(tx.id)
                if t.get('confirmations', 0) >= 6:
                    tx.confirmed = True
            except CoinRPCException:
                tx.confirmed = False

        db.session.commit()
    except Exception as exc:
        logger.error("Unhandled exception in update block status", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def update_block_state(self):
    """
    Loops through all immature and non-orphaned blocks.
    First checks to see if blocks are orphaned,
    then it checks to see if they are now matured.
    """
    mature_diff = current_app.config['block_mature_confirms']
    try:
        # Select all immature & non-orphaned blocks
        immature = (Block.query.filter_by(mature=False, orphan=False))
        blockheight = coinserv.getblockcount()
        for block in immature:
            logger.info("Checking block height: {}".format(block.height))
            # Check to see if the block hash exists in the block chain
            try:
                output = coinserv.getblock(block.hash)
                logger.debug("Confirms: {}; Height diff: {}"
                             .format(output['confirmations'],
                                     blockheight - block.height))
            except CoinRPCException:
                logger.info("Block {}:{} not in coin database, assume orphan!"
                            .format(block.height, block.hash))
                block.orphan = True
            else:
                if output['confirmations'] > mature_diff:
                    logger.info("Block {}:{} meets 120 confirms, mark mature"
                                .format(block.height, block.hash))
                    block.mature = True
                elif (blockheight - block.height) > mature_diff and output['confirmations'] < mature_diff:
                    logger.info("Block {}:{} 120 height ago, but not enough confirms. Marking orphan."
                                .format(block.height, block.hash))
                    block.orphan = True

        db.session.commit()
    except Exception as exc:
        logger.error("Unhandled exception in update block status", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def add_share(self, user, shares):
    """
    Adds a round share to postgresql

    user: should be a username/wallet address
    shares: should be an integer representation of n1 shares
    """
    try:
        Share.create(user=user, shares=shares)
        db.session.commit()
    except Exception as exc:
        logger.error("Unhandled exception in add share", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def add_block(self, user, height, total_value, transaction_fees, bits,
              hash_hex):
    """
    Insert a block & blockchain data

    user: should be a username/wallet address of who found block
    height: should be the height of the given block in the blockchain
    total_value: should be an integer representation of the value of the
                  newly discovered block. E.G.
                  DOGE = 2364681.04976814
                  network_value = 236468104976814

    transaction_fees: should be an integer amount awarded due to transactions
                     handled by the block. E.G.
                     transaction fees on new block = 6.5
                     transaction_fees = 650000000
    """
    logger.warn(
        "Recieved an add block notification!\nUser: {}\nHeight: {}\n"
        "Total Height: {}\nTransaction Fees: {}\nBits: {}\nHash Hex: {}"
        .format(user, height, total_value, transaction_fees, bits, hash_hex))
    try:
        last = last_block_share_id()
        block = Block.create(user, height, total_value, transaction_fees, bits,
                             hash_hex, time_started=last_block_time())
        db.session.flush()
        count = (db.session.query(func.sum(Share.shares)).
                 filter(Share.id > last).
                 filter(Share.id <= block.last_share_id).scalar()) or 128
        block.shares_to_solve = count
        db.session.commit()
    except Exception as exc:
        logger.error("Unhandled exception in add_block", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def add_one_minute(self, user, valid_shares, minute, worker='', dup_shares=0,
                   low_diff_shares=0, stale_shares=0):
    """
    Adds a new single minute entry for a user

    minute: timestamp (int)
    shares: number of shares recieved over the timespan
    user: string of the user
    """
    def count_share(typ, amount, user_=user):
        logger.debug("Adding {} for {} of amount {}"
                     .format(typ.__name__, user_, amount))
        try:
            typ.create(user_, amount, minute, worker)
            db.session.commit()
        except sqlalchemy.exc.IntegrityError:
            db.session.rollback()
            typ.add_value(user_, amount, minute, worker)
            db.session.commit()

    try:
        # log their valid shares
        if valid_shares:
            count_share(OneMinuteShare, valid_shares)

        # we want to log how much of each type of reject for the whole pool
        if user == "pool":
            if low_diff_shares:
                count_share(OneMinuteReject, low_diff_shares, user_="pool_low_diff")
            if dup_shares:
                count_share(OneMinuteReject, dup_shares, user_="pool_dup")
            if stale_shares:
                count_share(OneMinuteReject, stale_shares, user_="pool_stale")

        # only log a total reject on a per-user basis
        else:
            total_reject = dup_shares + low_diff_shares + stale_shares
            if total_reject:
                count_share(OneMinuteReject, total_reject)
    except Exception as exc:
        logger.error("Unhandled exception in add_one_minute", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def new_block(self, blockheight, bits=None, reward=None):
    """
    Notification that a new block height has been reached.
    """
    logger.info("Recieved notice of new block height {}".format(blockheight))
    if not isinstance(blockheight, int):
        logger.error("Invalid block height submitted, must be integer")

    blob = Blob(key='block', data={'height': str(blockheight),
                                   'difficulty': str(bits_to_difficulty(bits)),
                                   'reward': str(reward)})
    db.session.merge(blob)
    db.session.commit()


@celery.task(bind=True)
def cleanup(self, simulate=False):
    """
    Finds all the shares that will no longer be used and removes them from
    the database.
    """
    try:
        # find the oldest un-processed block
        block = (Block.query.
                 filter_by(processed=False).
                 order_by(Block.height).first())
        if block is None:
            # sloppy hack to get the newest block that is processed
            block = (Block.query.
                     filter_by(processed=True).
                     order_by(Block.height.desc()).first())
            if block is None:
                logger.debug("No block found, exiting...")
                return

        mult = int(current_app.config['last_n'])
        # take our standard share count times two for a safe margin. divide
        # by 16 to get the number of rows, since a rows minimum share count
        # is 16
        shares = (bits_to_shares(block.bits) * mult) * 2
        id_diff = shares // 16
        # compute the id which earlier ones are safe to delete
        stale_id = block.last_share.id - id_diff
        if simulate:
            print("Share for block computed: {}".format(shares // 2))
            print("Share total margin computed: {}".format(shares))
            print("Id diff computed: {}".format(id_diff))
            print("Stale ID computed: {}".format(stale_id))
            exit(0)
        elif stale_id > 0:
            logger.info("Cleaning all shares older than {}".format(stale_id))
            # delete all shares that are sufficiently old
            Share.query.filter(Share.id < stale_id).delete(
                synchronize_session=False)
            db.session.commit()
        else:
            logger.info("Not cleaning anything, stale id less than zero")
    except Exception as exc:
        logger.error("Unhandled exception in cleanup", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def payout(self, simulate=False):
    """
    Calculates payouts for users from share records for found blocks.
    """
    try:
        if simulate:
            logger.debug("Running in simulate mode, no commit will be performed")
            logger.setLevel(logging.DEBUG)

        # find the oldest un-processed block
        block = (Block.query.
                 filter_by(processed=False).
                 order_by(Block.height).first())
        if block is None:
            logger.debug("No block found, exiting...")
            return

        logger.debug("Processing block height {}".format(block.height))

        mult = int(current_app.config['last_n'])
        # take our standard share count times two for a safe margin. divide
        # by 16 to get the number of rows, since a rows minimum share count
        # is 16
        total_shares = (bits_to_shares(block.bits) * mult)
        logger.debug("Looking for up to {} total shares".format(total_shares))
        remain = total_shares
        start = block.last_share.id
        logger.debug("Identified last matching share id as {}".format(start))
        user_shares = {}
        for share in Share.query.order_by(Share.id.desc()).filter(Share.id <= start).yield_per(100):
            user_shares.setdefault(share.user, 0)
            if remain > share.shares:
                user_shares[share.user] += share.shares
                remain -= share.shares
            else:
                user_shares[share.user] += remain
                remain = 0
                break

        # if we found less than n, use what we found as the total
        total_shares -= remain
        logger.debug("Found {} shares".format(total_shares))
        if simulate:
            logger.debug("Share distribution:\n {}"
                         .format(pformat(user_shares)))

        # Calculate the portion going to the miners by truncating the
        # fractional portions and giving the remainder to the pool owner
        fee = float(current_app.config['fee'])
        logger.debug("Fee loaded as {}".format(fee))
        distribute_amnt = int((block.total_value * (100 - fee)) // 100)
        # record the fee collected by the pool for convenience
        block.fees = block.total_value - distribute_amnt
        logger.debug("Block fees computed to {}".format(block.fees))
        logger.debug("Distribute_amnt: {}".format(distribute_amnt))
        # Below calculates the truncated portion going to each miner. because
        # of fractional pieces the total accrued wont equal the disitrubte_amnt
        # so we will distribute that round robin the miners in dictionary order
        accrued = 0
        user_payouts = {}
        for user, share_count in user_shares.iteritems():
            user_payouts.setdefault(share.user, 0)
            user_payouts[user] = (share_count * distribute_amnt) // total_shares
            accrued += user_payouts[user]

        logger.debug("Total accrued after trunated iteration {}; {}%"
                     .format(accrued, (accrued / float(distribute_amnt)) * 100))
        # loop over the dictionary indefinitely until we've distributed
        # all the remaining funds
        while accrued < distribute_amnt:
            for key in user_payouts:
                user_payouts[key] += 1
                accrued += 1
                # exit if we've exhausted
                if accrued >= distribute_amnt:
                    break

        assert accrued == distribute_amnt
        logger.info("Successfully distributed all rewards among {} users"
                    .format(len(user_payouts)))

        if simulate:
            logger.debug("Share distribution:\n {}".format(pformat(user_payouts)))
            db.session.rollback()
        else:
            for user, amount in user_payouts.iteritems():
                Payout.create(user, amount, block, user_shares[user])
            block.processed = True
            db.session.commit()
    except Exception as exc:
        logger.error("Unhandled exception in payout", exc_info=True)
        db.session.rollback()
        raise self.retry(exc=exc)


@celery.task(bind=True)
def compress_minute(self):
    try:
        OneMinuteShare.compress()
        OneMinuteReject.compress()
        OneMinuteTemperature.compress()
        db.session.commit()
    except Exception:
        logger.error("Unhandled exception in compress_minute", exc_info=True)
        db.session.rollback()


@celery.task(bind=True)
def compress_five_minute(self):
    try:
        FiveMinuteShare.compress()
        FiveMinuteReject.compress()
        db.session.commit()
    except Exception:
        logger.error("Unhandled exception in compress_five_minute", exc_info=True)
        db.session.rollback()


@celery.task(bind=True)
def remove_old_statuses(self):
    try:
        ten_hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=12)
        Status.query.filter(Status.time < ten_hour_ago).delete()
        db.session.commit()
    except Exception:
        logger.error("Unhandled exception in remove_old_statuses", exc_info=True)
        db.session.rollback()


@celery.task(bind=True)
def agent_receive(self, address, worker, typ, payload, timestamp):
    # convert unix timestamp to datetime
    dt = datetime.datetime.utcfromtimestamp(timestamp)

    def inject_device_stat(cls, device, value):
        blob = cls(user=address, worker=worker, device=device, value=value,
                   time=dt)
        db.session.merge(blob)

    try:
        if typ == 'status':
            ret = (db.session.query(Status).filter_by(user=address, worker=worker).
                   update({"status": json.dumps(payload), "time": dt}))
            # if the update affected nothing
            if ret == 0:
                new = Status(user=address, worker=worker,
                             status=json.dumps(payload), time=dt)
                db.session.add(new)
        elif typ == 'temp':
            for i, value in enumerate(payload):
                if value:
                    inject_device_stat(OneMinuteTemperature, i, value)
        elif typ == 'hashrate':
            for i, value in enumerate(payload):
                if value:
                    # multiply by a million to turn megahashes to hashes
                    inject_device_stat(OneMinuteHashrate, i, value * 1000000)
        db.session.commit()
    except Exception:
        logger.error("Unhandled exception in update_status", exc_info=True)
        db.session.rollback()


@celery.task(bind=True)
def server_status(self):
    """
    Periodic pull update of server stats
    """
    mon_addr = current_app.config['monitor_addr']
    try:
        req = requests.get(mon_addr)
        data = req.json()
    except Exception:
        logger.warn("Couldn't connect to internal monitor at {}".format(mon_addr),
                    exc_info=True)
        output = {'stratum_clients': 0, 'agent_clients': 0}
    else:
        output = {'stratum_clients': data['stratum_clients'],
                  'agent_clients': data['agent_clients']}
    blob = Blob(key='server', data={k: str(v) for k, v in output.iteritems()})
    db.session.merge(blob)
    db.session.commit()
