import os
import pytest
import json
import pyethereum.processblock as processblock
import pyethereum.blocks as blocks
import pyethereum.transactions as transactions
import pyethereum.rlp as rlp
import pyethereum.trie as trie
import pyethereum.miner as miner
import pyethereum.utils as utils
from pyethereum.db import DB as DB
from pyethereum.config import get_default_config
from tests.utils import set_db

import logging
logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger()

set_db()

pblogger = processblock.pblogger

# customize VM log output to your needs
# hint: use 'py.test' with the '-s' option to dump logs to the console
pblogger.log_pre_state = True    # dump storage at account before execution
pblogger.log_post_state = True   # dump storage at account after execution
pblogger.log_block = False       # dump block after TX was applied
pblogger.log_memory = False      # dump memory before each op
pblogger.log_op = True           # log op, gas, stack before each op
pblogger.log_json = False        # generate machine readable output


@pytest.fixture(scope="module")
def accounts():
    k = utils.sha3('cow')
    v = utils.privtoaddr(k)
    k2 = utils.sha3('horse')
    v2 = utils.privtoaddr(k2)
    return k, v, k2, v2


@pytest.fixture(scope="module")
def mkgenesis(initial_alloc={}):
    return blocks.genesis(initial_alloc)


@pytest.fixture(scope="module")
def mkquickgenesis(initial_alloc={}):
    "set INITIAL_DIFFICULTY to a value that is quickly minable"
    return blocks.genesis(initial_alloc, difficulty=2 ** 16)


def mine_next_block(parent, uncles=[], coinbase=None, transactions=[]):
    # advance one block
    coinbase = coinbase or parent.coinbase
    m = miner.Miner(parent, uncles=uncles, coinbase=coinbase)
    for tx in transactions:
        m.add_transaction(tx)
    blk = m.mine(steps=1000 ** 2)
    assert blk is not False, "Mining failed. Use mkquickgenesis!"
    return blk


@pytest.fixture(scope="module")
def get_transaction(gasprice=0, nonce=0):
    k, v, k2, v2 = accounts()
    tx = transactions.Transaction(
        nonce, gasprice, startgas=10000,
        to=v2, value=utils.denoms.finney * 10, data='').sign(k)
    return tx


@pytest.fixture(scope="module")
def get_chainmanager(genesis=None):
    import pyethereum.chainmanager as chainmanager
    cm = chainmanager.ChainManager()
    cm.configure(config=get_default_config(), genesis=genesis)
    return cm


def db_store(blk):
    utils.db_put(blk.hash, blk.serialize())
    assert blocks.get_block(blk.hash) == blk


def test_db():
    set_db()
    db = DB(utils.get_db_path())
    a, b = DB(utils.get_db_path()),  DB(utils.get_db_path())
    assert a == b
    assert a.uncommitted == b.uncommitted
    a.put('a', 'b')
    b.get('a') == 'b'
    assert a.uncommitted == b.uncommitted
    a.commit()
    assert a.uncommitted == b.uncommitted
    assert 'test' not in db
    set_db()
    assert a != DB(utils.get_db_path())


def test_transfer():
    k, v, k2, v2 = accounts()
    blk = blocks.genesis({v: utils.denoms.ether * 1})
    b_v = blk.get_balance(v)
    b_v2 = blk.get_balance(v2)
    value = 42
    success = blk.transfer_value(v, v2, value)
    assert success
    assert blk.get_balance(v) == b_v - value
    assert blk.get_balance(v2) == b_v2 + value


def test_failing_transfer():
    k, v, k2, v2 = accounts()
    blk = blocks.genesis({v: utils.denoms.ether * 1})
    b_v = blk.get_balance(v)
    b_v2 = blk.get_balance(v2)
    value =  utils.denoms.ether * 2
    # should fail
    success = blk.transfer_value(v, v2, value)
    assert not success
    assert blk.get_balance(v) == b_v
    assert blk.get_balance(v2) == b_v2

def test_transient_block():
    blk = blocks.genesis()
    tb_blk = blocks.TransientBlock(blk.serialize())
    assert blk.hash == tb_blk.hash
    assert blk.number == tb_blk.number



def test_genesis():
    k, v, k2, v2 = accounts()
    set_db()
    blk = blocks.genesis({v: utils.denoms.ether * 1})
    sr = blk.state_root
    db = DB(utils.get_db_path())
    assert blk.state.db.db == db.db
    db.put(blk.hash, blk.serialize())
    blk.state.db.commit()
    assert sr in db
    db.commit()
    assert sr in db
    blk2 = blocks.genesis({v: utils.denoms.ether * 1})
    blk3 = blocks.genesis()
    assert blk == blk2
    assert blk != blk3
    set_db()
    blk2 = blocks.genesis({v: utils.denoms.ether * 1})
    blk3 = blocks.genesis()
    assert blk == blk2
    assert blk != blk3


def test_genesis_db():
    k, v, k2, v2 = accounts()
    set_db()
    blk = blocks.genesis({v: utils.denoms.ether * 1})
    db_store(blk)
    blk2 = blocks.genesis({v: utils.denoms.ether * 1})
    blk3 = blocks.genesis()
    assert blk == blk2
    assert blk != blk3
    set_db()
    blk2 = blocks.genesis({v: utils.denoms.ether * 1})
    blk3 = blocks.genesis()
    assert blk == blk2
    assert blk != blk3

def test_mine_block():
    k, v, k2, v2 = accounts()
    set_db()
    blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(blk)
    blk2 = mine_next_block(blk, coinbase=v)
    db_store(blk2)
    assert blk2.get_balance(v) == blocks.BLOCK_REWARD + blk.get_balance(v)
    assert blk.state.db.db == blk2.state.db.db
    assert blk2.get_parent() == blk


def test_mine_block_with_transaction():
    k, v, k2, v2 = accounts()
    # mine two blocks
    set_db()
    a_blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(a_blk)
    tx = get_transaction()
    a_blk2 = mine_next_block(a_blk, transactions=[tx])
    assert tx in a_blk2.get_transactions()


def test_block_serialization_with_transaction_empty_genesis():
    k, v, k2, v2 = accounts()
    set_db()
    a_blk = mkquickgenesis({})
    db_store(a_blk)
    tx = get_transaction(gasprice=10)  # must fail, as there is no balance
    a_blk2 = mine_next_block(a_blk, transactions=[tx])
    assert tx not in a_blk2.get_transactions()


def test_mine_block_with_transaction():
    k, v, k2, v2 = accounts()
    set_db()
    blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(blk)
    tx = get_transaction()
    blk2 = mine_next_block(blk, coinbase=v, transactions=[tx])
    assert tx in blk2.get_transactions()
    db_store(blk2)
    assert tx in blk2.get_transactions()
    assert blocks.get_block(blk2.hash) == blk2
    assert tx.gasprice == 0
    assert blk2.get_balance(
        v) == blocks.BLOCK_REWARD + blk.get_balance(v) - tx.value
    assert blk.state.db.db == blk2.state.db.db
    assert blk2.get_parent() == blk
    assert tx in blk2.get_transactions()
    assert tx not in blk.get_transactions()


def test_block_serialization_same_db():
    k, v, k2, v2 = accounts()
    set_db()
    blk = mkquickgenesis({v: utils.denoms.ether * 1})
    assert blk.hex_hash() == \
        blocks.Block.deserialize(blk.serialize()).hex_hash()
    db_store(blk)
    blk2 = mine_next_block(blk)
    assert blk.hex_hash() == \
        blocks.Block.deserialize(blk.serialize()).hex_hash()
    assert blk2.hex_hash() == \
        blocks.Block.deserialize(blk2.serialize()).hex_hash()


def test_block_serialization_other_db():
    k, v, k2, v2 = accounts()
    # mine two blocks
    set_db()
    a_blk = mkquickgenesis()
    db_store(a_blk)
    a_blk2 = mine_next_block(a_blk)
    db_store(a_blk2)

    # receive in other db
    set_db()
    b_blk = mkquickgenesis()
    assert b_blk == a_blk
    db_store(b_blk)
    b_blk2 = b_blk.deserialize(a_blk2.serialize())
    assert a_blk2.hex_hash() == b_blk2.hex_hash()
    db_store(b_blk2)
    assert a_blk2.hex_hash() == b_blk2.hex_hash()


def test_block_serialization_with_transaction_other_db():

    hx = lambda x: x.encode('hex')

    k, v, k2, v2 = accounts()
    # mine two blocks
    set_db()
    a_blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(a_blk)
    tx = get_transaction()
    logger.debug('a: state_root before tx %r', hx(a_blk.state_root))
    logger.debug('a: state:\n%s', utils.dump_state(a_blk.state))
    a_blk2 = mine_next_block(a_blk, transactions=[tx])
    logger.debug('a: state_root after tx %r', hx(a_blk2.state_root))
    logger.debug('a: state:\n%s', utils.dump_state(a_blk2.state))
    assert tx in a_blk2.get_transactions()
    db_store(a_blk2)
    assert tx in a_blk2.get_transactions()
    logger.debug('preparing receiving chain ---------------------')
    # receive in other db
    set_db()
    b_blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(b_blk)

    assert b_blk.number == 0
    assert b_blk == a_blk
    logger.debug('b: state_root before tx %r', hx(b_blk.state_root))
    logger.debug('starting deserialization of remote block w/ tx')
    b_blk2 = b_blk.deserialize(a_blk2.serialize()) # BOOM
    logger.debug('b: state_root after %r', hx(b_blk2.state_root))

    assert a_blk2.hex_hash() == b_blk2.hex_hash()

    assert tx in b_blk2.get_transactions()
    db_store(b_blk2)
    assert a_blk2.hex_hash() == b_blk2.hex_hash()
    assert tx in b_blk2.get_transactions()


def test_transaction():
    k, v, k2, v2 = accounts()
    set_db()
    blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(blk)
    blk = mine_next_block(blk)
    tx = get_transaction()
    assert tx not in blk.get_transactions()
    success, res = processblock.apply_transaction(blk, tx)
    assert tx in blk.get_transactions()
    assert blk.get_balance(v) == utils.denoms.finney * 990
    assert blk.get_balance(v2) == utils.denoms.finney * 10


def test_transaction_serialization():
    k, v, k2, v2 = accounts()
    tx = get_transaction()
    assert tx in set([tx])
    assert tx.hex_hash() == \
        transactions.Transaction.deserialize(tx.serialize()).hex_hash()
    assert tx.hex_hash() == \
        transactions.Transaction.hex_deserialize(tx.hex_serialize()).hex_hash()
    assert tx in set([tx])


def test_mine_block_with_transaction():
    k, v, k2, v2 = accounts()
    set_db()
    blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(blk)
    tx = get_transaction()
    blk = mine_next_block(blk, transactions=[tx])
    assert tx in blk.get_transactions()
    assert blk.get_balance(v) == utils.denoms.finney * 990
    assert blk.get_balance(v2) == utils.denoms.finney * 10


def test_invalid_transaction():
    k, v, k2, v2 = accounts()
    set_db()
    blk = mkquickgenesis({v2: utils.denoms.ether * 1})
    db_store(blk)
    tx = get_transaction()
    blk = mine_next_block(blk, transactions=[tx])
    assert blk.get_balance(v) == 0
    assert blk.get_balance(v2) == utils.denoms.ether * 1
    assert tx not in blk.get_transactions()


def test_add_side_chain():
    """"
    Local: L0, L1, L2
    add
    Remote: R0, R1
    """
    k, v, k2, v2 = accounts()
    # Remote: mine one block
    set_db()
    R0 = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(R0)
    tx0 = get_transaction(nonce=0)
    R1 = mine_next_block(R0, transactions=[tx0])
    db_store(R1)
    assert tx0 in R1.get_transactions()

    # Local: mine two blocks
    set_db()
    L0 = mkquickgenesis({v: utils.denoms.ether * 1})
    cm = get_chainmanager(genesis=L0)
    tx0 = get_transaction(nonce=0)
    L1 = mine_next_block(L0, transactions=[tx0])
    cm.add_block(L1)
    tx1 = get_transaction(nonce=1)
    L2 = mine_next_block(L1, transactions=[tx1])
    cm.add_block(L2)

    # receive serialized remote blocks, newest first
    transient_blocks = [blocks.TransientBlock(R0.serialize()),
                        blocks.TransientBlock(R1.serialize())]
    cm.receive_chain(transient_blocks=transient_blocks)
    assert L2.hash in cm


def test_add_longer_side_chain():
    """"
    Local: L0, L1, L2
    Remote: R0, R1, R2, R3
    """
    k, v, k2, v2 = accounts()
    # Remote: mine one block
    set_db()
    blk = mkquickgenesis({v: utils.denoms.ether * 1})
    db_store(blk)
    remote_blocks = [blk]
    for i in range(3):
        tx = get_transaction(nonce=i)
        blk = mine_next_block(remote_blocks[-1], transactions=[tx])
        db_store(blk)
        remote_blocks.append(blk)
    # Local: mine two blocks
    set_db()
    L0 = mkquickgenesis({v: utils.denoms.ether * 1})
    cm = get_chainmanager(genesis=L0)
    tx0 = get_transaction(nonce=0)
    L1 = mine_next_block(L0, transactions=[tx0])
    cm.add_block(L1)
    tx1 = get_transaction(nonce=1)
    L2 = mine_next_block(L1, transactions=[tx1])
    cm.add_block(L2)

    # receive serialized remote blocks, newest first
    transient_blocks = [blocks.TransientBlock(b.serialize()) for b in remote_blocks]
    cm.receive_chain(transient_blocks=transient_blocks)
    assert cm.head == remote_blocks[-1]



def test_reward_unlces():
    """
    B0 B1 B2
    B0 Uncle

    We raise the block's coinbase account by Rb, the block reward,
    and also add uncle and nephew rewards
    """
    k, v, k2, v2 = accounts()
    set_db()
    blk0 = mkquickgenesis()
    local_coinbase = '1' * 40
    uncle_coinbase = '2' * 40
    cm = get_chainmanager(genesis=blk0)
    blk1 = mine_next_block(blk0, coinbase=local_coinbase)
    cm.add_block(blk1)
    assert blk1.get_balance(local_coinbase) == 1 * blocks.BLOCK_REWARD
    uncle = mine_next_block(blk0, coinbase=uncle_coinbase)
    cm.add_block(uncle)
    assert uncle.hash in cm
    assert cm.head.get_balance(local_coinbase) == 1 * blocks.BLOCK_REWARD
    assert cm.head.get_balance(uncle_coinbase) == 0
    # next block should reward uncles
    blk2 = mine_next_block(blk1, uncles=[uncle], coinbase=local_coinbase)
    cm.add_block(blk2)
    assert blk2.get_parent().prevhash == uncle.prevhash
    assert blk2 == cm.head
    assert cm.head.get_balance(local_coinbase) == \
        2 * blocks.BLOCK_REWARD + blocks.NEPHEW_REWARD
    assert cm.head.get_balance(uncle_coinbase) == blocks.UNCLE_REWARD


# TODO ##########################################
#
# test for remote block with invalid transaction
# test for multiple transactions from same address received
#    in arbitrary order mined in the same block
