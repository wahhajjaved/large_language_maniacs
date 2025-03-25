#!/usr/bin/python

from __future__ import division

import argparse
import datetime
import itertools
import os
import random
import sqlite3
import struct
import sys
import time
import json
import signal
import traceback

from twisted.internet import defer, reactor, task
from twisted.web import server, resource
from twisted.python import log
from nattraverso import portmapper, ipdiscover

import bitcoin.p2p, bitcoin.getwork, bitcoin.data
from util import db, expiring_dict, jsonrpc, variable, deferral, math
from . import p2p, worker_interface, skiplists
import p2pool.data as p2pool
import p2pool as p2pool_init

@deferral.retry('Error getting work from bitcoind:', 3)
@defer.inlineCallbacks
def getwork(bitcoind, ht, net):
    try:
        work = yield bitcoind.rpc_getmemorypool()
        defer.returnValue(dict(
            version=work['version'],
            previous_block_hash=int(work['previousblockhash'], 16),
            transactions=[bitcoin.data.tx_type.unpack(x.decode('hex')) for x in work['transactions']],
            subsidy=work['coinbasevalue'],
            time=work['time'],
            target=bitcoin.data.FloatingIntegerType().unpack(work['bits'].decode('hex')[::-1]) if isinstance(work['bits'], (str, unicode)) else bitcoin.data.FloatingInteger(work['bits']),
        ))
    except jsonrpc.Error, e:
        if e.code != -32601:
            raise
        
        print "---> Update your bitcoind to support the 'getmemorypool' RPC call. Not including transactions in generated blocks! <---"
        work = bitcoin.getwork.BlockAttempt.from_getwork((yield bitcoind.rpc_getwork()))
        try:
            subsidy = net.BITCOIN_SUBSIDY_FUNC(ht.getHeight(work.previous_block))
        except ValueError:
            subsidy = net.BITCOIN_SUBSIDY_FUNC(1000)
        
        defer.returnValue(dict(
            version=work.version,
            previous_block_hash=work.previous_block,
            transactions=[],
            subsidy=subsidy,
            time=work.timestamp,
            target=work.block_target,
        ))

@deferral.retry('Error getting payout script from bitcoind:', 1)
@defer.inlineCallbacks
def get_payout_script(factory):
    res = yield (yield factory.getProtocol()).check_order(order=bitcoin.p2p.Protocol.null_order)
    if res['reply'] == 'success':
        defer.returnValue(res['script'])
    elif res['reply'] == 'denied':
        defer.returnValue(None)
    else:
        raise ValueError('Unexpected reply: %r' % (res,))

@deferral.retry('Error creating payout script:', 10)
@defer.inlineCallbacks
def get_payout_script2(bitcoind, net):
    defer.returnValue(bitcoin.data.pubkey_hash_to_script2(bitcoin.data.address_to_pubkey_hash((yield bitcoind.rpc_getaccountaddress('p2pool')), net)))

@defer.inlineCallbacks
def main(args):
    try:
        print 'p2pool (version %s)' % (p2pool_init.__version__,)
        print
        try:
            from . import draw
        except ImportError:
            draw = None
            print "Install Pygame and PIL to enable visualizations! Visualizations disabled."
            print
        
        # connect to bitcoind over JSON-RPC and do initial getwork
        url = 'http://%s:%i/' % (args.bitcoind_address, args.bitcoind_rpc_port)
        print '''Testing bitcoind RPC connection to '%s' with username '%s'...''' % (url, args.bitcoind_rpc_username)
        bitcoind = jsonrpc.Proxy(url, (args.bitcoind_rpc_username, args.bitcoind_rpc_password))
        good = yield deferral.retry('Error while checking bitcoind identity:', 1)(args.net.BITCOIN_RPC_CHECK)(bitcoind)
        if not good:
            print "    Check failed! Make sure that you're connected to the right bitcoind with --bitcoind-rpc-port!"
            return
        temp_work = yield deferral.retry('Error while testing getwork:', 1)(defer.inlineCallbacks(lambda: defer.returnValue(bitcoin.getwork.BlockAttempt.from_getwork((yield bitcoind.rpc_getwork())))))()
        print '    ...success!'
        print '    Current block hash: %x' % (temp_work.previous_block,)
        print
        
        # connect to bitcoind over bitcoin-p2p and do checkorder to get pubkey to send payouts to
        print '''Testing bitcoind P2P connection to '%s:%s'...''' % (args.bitcoind_address, args.bitcoind_p2p_port)
        factory = bitcoin.p2p.ClientFactory(args.net)
        reactor.connectTCP(args.bitcoind_address, args.bitcoind_p2p_port, factory)
        my_script = yield get_payout_script(factory)
        if args.pubkey_hash is None:
            if my_script is None:
                print '    IP transaction denied ... falling back to sending to address.'
                my_script = yield get_payout_script2(bitcoind, args.net)
        else:
            my_script = bitcoin.data.pubkey_hash_to_script2(args.pubkey_hash)
        print '    ...success!'
        print '    Payout script:', bitcoin.data.script2_to_human(my_script, args.net)
        print
        
        print 'Loading cached block headers...'
        ht = bitcoin.p2p.HeightTracker(factory, args.net.NAME + '_headers.dat')
        print '   ...done loading %i cached block headers.' % (len(ht.tracker.shares),)
        print
        
        tracker = p2pool.OkayTracker(args.net)
        ss = p2pool.ShareStore(os.path.join(os.path.dirname(sys.argv[0]), args.net.NAME + '_shares.'), args.net)
        known_verified = set()
        print "Loading shares..."
        for i, (mode, contents) in enumerate(ss.get_shares()):
            if mode == 'share':
                if contents.hash in tracker.shares:
                    continue
                contents.shared = True
                contents.stored = True
                contents.time_seen = 0
                tracker.add(contents)
                if len(tracker.shares) % 1000 == 0 and tracker.shares:
                    print "    %i" % (len(tracker.shares),)
            elif mode == 'verified_hash':
                known_verified.add(contents)
            else:
                raise AssertionError()
        print "    ...inserting %i verified shares..." % (len(known_verified),)
        for h in known_verified:
            if h not in tracker.shares:
                ss.forget_verified_share(h)
                continue
            tracker.verified.add(tracker.shares[h])
        print "    ...done loading %i shares!" % (len(tracker.shares),)
        print
        tracker.added.watch(lambda share: ss.add_share(share))
        tracker.verified.added.watch(lambda share: ss.add_verified_hash(share.hash))
        tracker.removed.watch(lambda share: ss.forget_share(share.hash))
        tracker.verified.removed.watch(lambda share: ss.forget_verified_share(share.hash))
        
        peer_heads = expiring_dict.ExpiringDict(300) # hash -> peers that know of it
        
        # information affecting work that should trigger a long-polling update
        current_work = variable.Variable(None)
        # information affecting work that should not trigger a long-polling update
        current_work2 = variable.Variable(None)
        
        work_updated = variable.Event()
        
        requested = expiring_dict.ExpiringDict(300)
        
        @defer.inlineCallbacks
        def set_real_work1():
            work = yield getwork(bitcoind, ht, args.net)
            changed = work['previous_block_hash'] != current_work.value['previous_block'] if current_work.value is not None else True
            current_work.set(dict(
                version=work['version'],
                previous_block=work['previous_block_hash'],
                target=work['target'],
                best_share_hash=current_work.value['best_share_hash'] if current_work.value is not None else None,
            ))
            current_work2.set(dict(
                transactions=work['transactions'],
                subsidy=work['subsidy'],
                clock_offset=time.time() - work['time'],
                last_update=time.time(),
            ))
            if changed:
                set_real_work2()
        
        def set_real_work2():
            best, desired = tracker.think(ht, current_work.value['previous_block'], time.time() - current_work2.value['clock_offset'])
            
            t = dict(current_work.value)
            t['best_share_hash'] = best
            current_work.set(t)
            
            t = time.time()
            for peer2, share_hash in desired:
                if share_hash not in tracker.tails: # was received in the time tracker.think was running
                    continue
                last_request_time, count = requested.get(share_hash, (None, 0))
                if last_request_time is not None and last_request_time - 5 < t < last_request_time + 10 * 1.5**count:
                    continue
                potential_peers = set()
                for head in tracker.tails[share_hash]:
                    potential_peers.update(peer_heads.get(head, set()))
                potential_peers = [peer for peer in potential_peers if peer.connected2]
                if count == 0 and peer2 is not None and peer2.connected2:
                    peer = peer2
                else:
                    peer = random.choice(potential_peers) if potential_peers and random.random() > .2 else peer2
                    if peer is None:
                        continue
                
                print 'Requesting parent share %s from %s' % (p2pool.format_hash(share_hash), '%s:%i' % peer.addr)
                peer.send_getshares(
                    hashes=[share_hash],
                    parents=2000,
                    stops=list(set(tracker.heads) | set(
                        tracker.get_nth_parent_hash(head, min(max(0, tracker.get_height_and_last(head)[0] - 1), 10)) for head in tracker.heads
                    ))[:100],
                )
                requested[share_hash] = t, count + 1
        
        print 'Initializing work...'
        yield set_real_work1()
        set_real_work2()
        print '    ...success!'
        print
        
        start_time = time.time() - current_work2.value['clock_offset']
        
        # setup p2p logic and join p2pool network
        
        def share_share(share, ignore_peer=None):
            for peer in p2p_node.peers.itervalues():
                if peer is ignore_peer:
                    continue
                #if p2pool_init.DEBUG:
                #    print "Sending share %s to %r" % (p2pool.format_hash(share.hash), peer.addr)
                peer.send_shares([share])
            share.flag_shared()
        
        def p2p_shares(shares, peer=None):
            if len(shares) > 5:
                print 'Processing %i shares...' % (len(shares),)
            
            new_count = 0
            for share in shares:
                if share.hash in tracker.shares:
                    #print 'Got duplicate share, ignoring. Hash: %s' % (p2pool.format_hash(share.hash),)
                    continue
                
                new_count += 1
                
                #print 'Received share %s from %r' % (p2pool.format_hash(share.hash), share.peer.addr if share.peer is not None else None)
                
                tracker.add(share)
            
            if shares and peer is not None:
                peer_heads.setdefault(shares[0].hash, set()).add(peer)
            
            if new_count:
                set_real_work2()
            
            if len(shares) > 5:
                print '... done processing %i shares. New: %i Have: %i/~%i' % (len(shares), new_count, len(tracker.shares), 2*args.net.CHAIN_LENGTH)
        
        @tracker.verified.added.watch
        def _(share):
            if share.bitcoin_hash <= share.header['target']:
                print
                print 'GOT BLOCK! Passing to bitcoind! %s bitcoin: %x' % (p2pool.format_hash(share.hash), share.bitcoin_hash,)
                print
                if factory.conn.value is not None:
                    factory.conn.value.send_block(block=share.as_block(tracker, args.net))
                else:
                    print 'No bitcoind connection! Erp!'
        
        def p2p_share_hashes(share_hashes, peer):
            t = time.time()
            get_hashes = []
            for share_hash in share_hashes:
                if share_hash in tracker.shares:
                    continue
                last_request_time, count = requested.get(share_hash, (None, 0))
                if last_request_time is not None and last_request_time - 5 < t < last_request_time + 10 * 1.5**count:
                    continue
                print 'Got share hash, requesting! Hash: %s' % (p2pool.format_hash(share_hash),)
                get_hashes.append(share_hash)
                requested[share_hash] = t, count + 1
            
            if share_hashes and peer is not None:
                peer_heads.setdefault(share_hashes[0], set()).add(peer)
            if get_hashes:
                peer.send_getshares(hashes=get_hashes, parents=0, stops=[])
        
        def p2p_get_shares(share_hashes, parents, stops, peer):
            parents = min(parents, 1000//len(share_hashes))
            stops = set(stops)
            shares = []
            for share_hash in share_hashes:
                for share in itertools.islice(tracker.get_chain_known(share_hash), parents + 1):
                    if share.hash in stops:
                        break
                    shares.append(share)
            print 'Sending %i shares to %s:%i' % (len(shares), peer.addr[0], peer.addr[1])
            peer.send_shares(shares, full=True)
        
        print 'Joining p2pool network using TCP port %i...' % (args.p2pool_port,)
        
        def parse(x):
            if ':' in x:
                ip, port = x.split(':')
                return ip, int(port)
            else:
                return x, args.net.P2P_PORT
        
        nodes = set([
            ('72.14.191.28', args.net.P2P_PORT),
            ('62.204.197.159', args.net.P2P_PORT),
            ('142.58.248.28', args.net.P2P_PORT),
            ('94.23.34.145', args.net.P2P_PORT),
        ])
        for host in [
            'p2pool.forre.st',
            'dabuttonfactory.com',
        ]:
            try:
                nodes.add(((yield reactor.resolve(host)), args.net.P2P_PORT))
            except:
                log.err(None, 'Error resolving bootstrap node IP:')
        
        p2p_node = p2p.Node(
            current_work=current_work,
            port=args.p2pool_port,
            net=args.net,
            addr_store=db.SQLiteDict(sqlite3.connect(os.path.join(os.path.dirname(sys.argv[0]), 'addrs.dat'), isolation_level=None), args.net.NAME),
            mode=0 if args.low_bandwidth else 1,
            preferred_addrs=set(map(parse, args.p2pool_nodes)) | nodes,
        )
        p2p_node.handle_shares = p2p_shares
        p2p_node.handle_share_hashes = p2p_share_hashes
        p2p_node.handle_get_shares = p2p_get_shares
        
        p2p_node.start()
        
        # send share when the chain changes to their chain
        def work_changed(new_work):
            #print 'Work changed:', new_work
            for share in tracker.get_chain_known(new_work['best_share_hash']):
                if share.shared:
                    break
                share_share(share, share.peer)
        current_work.changed.watch(work_changed)
        
        print '    ...success!'
        print
        
        @defer.inlineCallbacks
        def upnp_thread():
            while True:
                try:
                    is_lan, lan_ip = yield ipdiscover.get_local_ip()
                    if is_lan:
                        pm = yield portmapper.get_port_mapper()
                        yield pm._upnp.add_port_mapping(lan_ip, args.p2pool_port, args.p2pool_port, 'p2pool', 'TCP') # XXX try to forward external correct port?
                except defer.TimeoutError:
                    pass
                except:
                    if p2pool_init.DEBUG:
                        log.err(None, "UPnP error:")
                yield deferral.sleep(random.expovariate(1/120))
        
        if args.upnp:
            upnp_thread()
        
        # start listening for workers with a JSON-RPC server
        
        print 'Listening for workers on port %i...' % (args.worker_port,)
        
        # setup worker logic
        
        merkle_root_to_transactions = expiring_dict.ExpiringDict(300)
        run_identifier = struct.pack('<Q', random.randrange(2**64))
        
        share_counter = skiplists.CountsSkipList(tracker, run_identifier)
        removed_unstales = set()
        def get_share_counts(doa=False):
            height, last = tracker.get_height_and_last(current_work.value['best_share_hash'])
            matching_in_chain = share_counter(current_work.value['best_share_hash'], max(0, height - 1)) | removed_unstales
            shares_in_chain = my_shares & matching_in_chain
            stale_shares = my_shares - matching_in_chain
            if doa:
                stale_doa_shares = stale_shares & doa_shares
                stale_not_doa_shares = stale_shares - stale_doa_shares
                return len(shares_in_chain) + len(stale_shares), len(stale_doa_shares), len(stale_not_doa_shares)
            return len(shares_in_chain) + len(stale_shares), len(stale_shares)
        @tracker.verified.removed.watch
        def _(share):
            if share.hash in my_shares and tracker.is_child_of(share.hash, current_work.value['best_share_hash']):
                removed_unstales.add(share.hash)
        
        def compute(state, payout_script):
            if payout_script is None or random.uniform(0, 100) < args.worker_fee:
                payout_script = my_script
            if state['best_share_hash'] is None and args.net.PERSIST:
                raise jsonrpc.Error(-12345, u'p2pool is downloading shares')
            if len(p2p_node.peers) == 0 and args.net.PERSIST:
                raise jsonrpc.Error(-12345, u'p2pool is not connected to any peers')
            if time.time() > current_work2.value['last_update'] + 60:
                raise jsonrpc.Error(-12345, u'lost contact with bitcoind')
            
            # XXX assuming generate_tx is smallish here..
            def get_stale_frac():
                shares, stale_shares = get_share_counts()
                if shares == 0:
                    return ""
                frac = stale_shares/shares
                return 2*struct.pack('<H', int(65535*frac + .5))
            subsidy = current_work2.value['subsidy']
            generate_tx = p2pool.generate_transaction(
                tracker=tracker,
                previous_share_hash=state['best_share_hash'],
                new_script=payout_script,
                subsidy=subsidy,
                nonce=run_identifier + struct.pack('<Q', random.randrange(2**64)) + get_stale_frac(),
                block_target=state['target'],
                net=args.net,
            )
            print 'New work for worker! Difficulty: %.06f Payout if block: %.6f %s Total block value: %.6f %s including %i transactions' % (0xffff*2**208/p2pool.coinbase_type.unpack(generate_tx['tx_ins'][0]['script'])['share_data']['target'], (generate_tx['tx_outs'][-1]['value']-subsidy//200)*1e-8, args.net.BITCOIN_SYMBOL, subsidy*1e-8, args.net.BITCOIN_SYMBOL, len(current_work2.value['transactions']))
            #print 'Target: %x' % (p2pool.coinbase_type.unpack(generate_tx['tx_ins'][0]['script'])['share_data']['target'],)
            #, have', shares.count(my_script) - 2, 'share(s) in the current chain. Fee:', sum(tx.value_in - tx.value_out for tx in extra_txs)/100000000
            transactions = [generate_tx] + list(current_work2.value['transactions'])
            merkle_root = bitcoin.data.merkle_hash(transactions)
            merkle_root_to_transactions[merkle_root] = transactions # will stay for 1000 seconds
            
            timestamp = int(time.time() - current_work2.value['clock_offset'])
            if state['best_share_hash'] is not None:
                timestamp2 = math.median((s.timestamp for s in itertools.islice(tracker.get_chain_to_root(state['best_share_hash']), 11)), use_float=False) + 1
                if timestamp2 > timestamp:
                    print 'Toff', timestamp2 - timestamp
                    timestamp = timestamp2
            target2 = p2pool.coinbase_type.unpack(generate_tx['tx_ins'][0]['script'])['share_data']['target']
            times[p2pool.coinbase_type.unpack(generate_tx['tx_ins'][0]['script'])['share_data']['nonce']] = time.time()
            #print 'SENT', 2**256//p2pool.coinbase_type.unpack(generate_tx['tx_ins'][0]['script'])['share_data']['target']
            return bitcoin.getwork.BlockAttempt(state['version'], state['previous_block'], merkle_root, timestamp, state['target'], target2)
        
        my_shares = set()
        doa_shares = set()
        times = {}
        
        def got_response(data, user):
            try:
                # match up with transactions
                header = bitcoin.getwork.decode_data(data)
                transactions = merkle_root_to_transactions.get(header['merkle_root'], None)
                if transactions is None:
                    print '''Couldn't link returned work's merkle root with its transactions - should only happen if you recently restarted p2pool'''
                    return False
                block = dict(header=header, txs=transactions)
                hash_ = bitcoin.data.block_header_type.hash256(block['header'])
                if hash_ <= block['header']['target'] or p2pool_init.DEBUG:
                    if factory.conn.value is not None:
                        factory.conn.value.send_block(block=block)
                    else:
                        print 'No bitcoind connection! Erp!'
                    if hash_ <= block['header']['target']:
                        print
                        print 'GOT BLOCK! Passing to bitcoind! bitcoin: %x' % (hash_,)
                        print
                target = p2pool.coinbase_type.unpack(transactions[0]['tx_ins'][0]['script'])['share_data']['target']
                if hash_ > target:
                    print 'Worker submitted share with hash > target:\nhash  : %x\ntarget: %x' % (hash_, target)
                    return False
                share = p2pool.Share.from_block(block)
                my_shares.add(share.hash)
                if share.previous_hash != current_work.value['best_share_hash']:
                    doa_shares.add(share.hash)
                print 'GOT SHARE! %s %s prev %s age %.2fs' % (user, p2pool.format_hash(share.hash), p2pool.format_hash(share.previous_hash), time.time() - times[share.nonce]) + (' DEAD ON ARRIVAL' if share.previous_hash != current_work.value['best_share_hash'] else '')
                good = share.previous_hash == current_work.value['best_share_hash']
                # maybe revert back to tracker being non-blocking so 'good' can be more accurate?
                p2p_shares([share])
                # eg. good = share.hash == current_work.value['best_share_hash'] here
                return good
            except:
                log.err(None, 'Error processing data received from worker:')
                return False
        
        web_root = worker_interface.WorkerInterface(current_work, compute, got_response, args.net)
        
        def get_rate():
            if current_work.value['best_share_hash'] is not None:
                height, last = tracker.get_height_and_last(current_work.value['best_share_hash'])
                att_s = p2pool.get_pool_attempts_per_second(tracker, current_work.value['best_share_hash'], args.net, min(height - 1, 720))
                fracs = [read_stale_frac(share) for share in itertools.islice(tracker.get_chain_known(current_work.value['best_share_hash']), 120) if read_stale_frac(share) is not None]
                return json.dumps(int(att_s / (1. - (math.median(fracs) if fracs else 0))))
            return json.dumps(None)
        
        def get_users():
            height, last = tracker.get_height_and_last(current_work.value['best_share_hash'])
            weights, total_weight = tracker.get_cumulative_weights(current_work.value['best_share_hash'], min(height, 720), 2**256)
            res = {}
            for script in sorted(weights, key=lambda s: weights[s]):
                res[bitcoin.data.script2_to_human(script, args.net)] = weights[script]/total_weight
            return json.dumps(res)
        
        class WebInterface(resource.Resource):
            def __init__(self, func, mime_type):
                self.func, self.mime_type = func, mime_type
            
            def render_GET(self, request):
                request.setHeader('Content-Type', self.mime_type)
                return self.func()
        
        web_root.putChild('rate', WebInterface(get_rate, 'application/json'))
        web_root.putChild('users', WebInterface(get_users, 'application/json'))
        web_root.putChild('fee', WebInterface(lambda: json.dumps(args.worker_fee), 'application/json'))
        if draw is not None:
            web_root.putChild('chain_img', WebInterface(lambda: draw.get(tracker, current_work.value['best_share_hash']), 'image/png'))
        
        reactor.listenTCP(args.worker_port, server.Site(web_root))
        
        print '    ...success!'
        print
        
        # done!
        
        # do new getwork when a block is heard on the p2p interface
        
        def new_block(block_hash):
            work_updated.happened()
        factory.new_block.watch(new_block)
        
        print 'Started successfully!'
        print
        
        ht.updated.watch(set_real_work2)
        
        @defer.inlineCallbacks
        def work1_thread():
            while True:
                flag = work_updated.get_deferred()
                try:
                    yield set_real_work1()
                except:
                    log.err()
                yield defer.DeferredList([flag, deferral.sleep(random.uniform(1, 10))], fireOnOneCallback=True)
        
        @defer.inlineCallbacks
        def work2_thread():
            while True:
                try:
                    set_real_work2()
                except:
                    log.err()
                yield deferral.sleep(random.expovariate(1/20))
        
        work1_thread()
        work2_thread()
        
        
        if hasattr(signal, 'SIGALRM'):
            def watchdog_handler(signum, frame):
                print 'Watchdog timer went off at:'
                traceback.print_stack()
            
            signal.signal(signal.SIGALRM, watchdog_handler)
            task.LoopingCall(signal.alarm, 30).start(1)
        
        
        def read_stale_frac(share):
            if len(share.nonce) != 20:
                return None
            a, b = struct.unpack("<HH", share.nonce[-4:])
            if a != b:
                return None
            return a/65535
        
        while True:
            yield deferral.sleep(3)
            try:
                if time.time() > current_work2.value['last_update'] + 60:
                    print '''---> LOST CONTACT WITH BITCOIND for 60 seconds, check that it isn't frozen or dead <---'''
                if current_work.value['best_share_hash'] is not None:
                    height, last = tracker.get_height_and_last(current_work.value['best_share_hash'])
                    if height > 2:
                        att_s = p2pool.get_pool_attempts_per_second(tracker, current_work.value['best_share_hash'], args.net, min(height - 1, 720))
                        weights, total_weight = tracker.get_cumulative_weights(current_work.value['best_share_hash'], min(height, 720), 2**100)
                        shares, stale_doa_shares, stale_not_doa_shares = get_share_counts(True)
                        stale_shares = stale_doa_shares + stale_not_doa_shares
                        fracs = [read_stale_frac(share) for share in itertools.islice(tracker.get_chain_known(current_work.value['best_share_hash']), 120) if read_stale_frac(share) is not None]
                        print 'Pool: %sH/s in %i shares (%i/%i verified) Recent: %.02f%% >%sH/s Shares: %i (%i orphan, %i dead) Peers: %i' % (
                            math.format(int(att_s / (1. - (math.median(fracs) if fracs else 0)))),
                            height,
                            len(tracker.verified.shares),
                            len(tracker.shares),
                            weights.get(my_script, 0)/total_weight*100,
                            math.format(int(weights.get(my_script, 0)*att_s//total_weight / (1. - (math.median(fracs) if fracs else 0)))),
                            shares,
                            stale_not_doa_shares,
                            stale_doa_shares,
                            len(p2p_node.peers),
                        ) + (' FDs: %i R/%i W' % (len(reactor.getReaders()), len(reactor.getWriters())) if p2pool_init.DEBUG else '')
                        if fracs:
                            med = math.median(fracs)
                            print 'Median stale proportion:', med
                            if shares:
                                print '    Own:', stale_shares/shares
                                if med < .99:
                                    print '    Own efficiency: %.02f%%' % (100*(1 - stale_shares/shares)/(1 - med),)
            
            
            except:
                log.err()
    except:
        log.err(None, 'Fatal error:')
    finally:
        reactor.stop()

def run():
    class FixedArgumentParser(argparse.ArgumentParser):
        def _read_args_from_files(self, arg_strings):
            # expand arguments referencing files
            new_arg_strings = []
            for arg_string in arg_strings:
                
                # for regular arguments, just add them back into the list
                if not arg_string or arg_string[0] not in self.fromfile_prefix_chars:
                    new_arg_strings.append(arg_string)
                
                # replace arguments referencing files with the file content
                else:
                    try:
                        args_file = open(arg_string[1:])
                        try:
                            arg_strings = []
                            for arg_line in args_file.read().splitlines():
                                for arg in self.convert_arg_line_to_args(arg_line):
                                    arg_strings.append(arg)
                            arg_strings = self._read_args_from_files(arg_strings)
                            new_arg_strings.extend(arg_strings)
                        finally:
                            args_file.close()
                    except IOError:
                        err = sys.exc_info()[1]
                        self.error(str(err))
            
            # return the modified argument list
            return new_arg_strings
        
        def convert_arg_line_to_args(self, arg_line):
            return [arg for arg in arg_line.split() if arg.strip()]
    
    parser = FixedArgumentParser(description='p2pool (version %s)' % (p2pool_init.__version__,), fromfile_prefix_chars='@')
    parser.add_argument('--version', action='version', version=p2pool_init.__version__)
    parser.add_argument('--net',
        help='use specified network (default: bitcoin)',
        action='store', choices=sorted(x for x in p2pool.nets if 'testnet' not in x), default='bitcoin', dest='net_name')
    parser.add_argument('--testnet',
        help='''use the network's testnet''',
        action='store_const', const=True, default=False, dest='testnet')
    parser.add_argument('--debug',
        help='debugging mode',
        action='store_const', const=True, default=False, dest='debug')
    parser.add_argument('-a', '--address',
        help='generate to this address (defaults to requesting one from bitcoind)',
        type=str, action='store', default=None, dest='address')
    parser.add_argument('--logfile',
        help='''log to specific file (defaults to <network_name>.log in run_p2pool.py's directory)''',
        type=str, action='store', default=None, dest='logfile')
    
    p2pool_group = parser.add_argument_group('p2pool interface')
    p2pool_group.add_argument('--p2pool-port', metavar='PORT',
        help='use TCP port PORT to listen for connections (default: 9333 normally, 19333 for testnet) (forward this port from your router!)',
        type=int, action='store', default=None, dest='p2pool_port')
    p2pool_group.add_argument('-n', '--p2pool-node', metavar='ADDR[:PORT]',
        help='connect to existing p2pool node at ADDR listening on TCP port PORT (defaults to 9333 normally, 19333 for testnet), in addition to builtin addresses',
        type=str, action='append', default=[], dest='p2pool_nodes')
    parser.add_argument('-l', '--low-bandwidth',
        help='trade lower bandwidth usage for higher latency (reduced efficiency)',
        action='store_true', default=False, dest='low_bandwidth')
    parser.add_argument('--disable-upnp',
        help='''don't attempt to forward port 9333 (19333 for testnet) from the WAN to this computer using UPnP''',
        action='store_false', default=True, dest='upnp')
    
    worker_group = parser.add_argument_group('worker interface')
    worker_group.add_argument('-w', '--worker-port', metavar='PORT',
        help='listen on PORT for RPC connections from miners asking for work and providing responses (default: bitcoin: 9332 namecoin: 9331 ixcoin: 9330 i0coin: 9329, +10000 for testnets)',
        type=int, action='store', default=None, dest='worker_port')
    worker_group.add_argument('-f', '--fee', metavar='FEE_PERCENTAGE',
        help='''charge workers mining to their own bitcoin address (by setting their miner's username to a bitcoin address) this percentage fee to mine on your p2pool instance. Amount displayed at http://127.0.0.1:9332/fee . default: 0''',
        type=float, action='store', default=0, dest='worker_fee')
    
    bitcoind_group = parser.add_argument_group('bitcoind interface')
    bitcoind_group.add_argument('--bitcoind-address', metavar='BITCOIND_ADDRESS',
        help='connect to a bitcoind at this address (default: 127.0.0.1)',
        type=str, action='store', default='127.0.0.1', dest='bitcoind_address')
    bitcoind_group.add_argument('--bitcoind-rpc-port', metavar='BITCOIND_RPC_PORT',
        help='connect to a bitcoind at this port over the RPC interface - used to get the current highest block via getwork (default: 8332, 8338 for ixcoin)',
        type=int, action='store', default=None, dest='bitcoind_rpc_port')
    bitcoind_group.add_argument('--bitcoind-p2p-port', metavar='BITCOIND_P2P_PORT',
        help='connect to a bitcoind at this port over the p2p interface - used to submit blocks and get the pubkey to generate to via an IP transaction (default: 8333 normally. 18333 for testnet)',
        type=int, action='store', default=None, dest='bitcoind_p2p_port')
    
    bitcoind_group.add_argument(metavar='BITCOIND_RPCUSER',
        help='bitcoind RPC interface username (default: empty)',
        type=str, action='store', default='', nargs='?', dest='bitcoind_rpc_username')
    bitcoind_group.add_argument(metavar='BITCOIND_RPCPASSWORD',
        help='bitcoind RPC interface password',
        type=str, action='store', dest='bitcoind_rpc_password')
    
    args = parser.parse_args()
    
    if args.debug:
        p2pool_init.DEBUG = True
    
    if args.logfile is None:
        args.logfile = os.path.join(os.path.dirname(sys.argv[0]), args.net_name + ('_testnet' if args.testnet else '') + '.log')
    
    class LogFile(object):
        def __init__(self, filename):
            self.filename = filename
            self.inner_file = None
            self.reopen()
        def reopen(self):
            if self.inner_file is not None:
                self.inner_file.close()
            open(self.filename, 'a').close()
            f = open(self.filename, 'rb')
            f.seek(0, os.SEEK_END)
            length = f.tell()
            if length > 100*1000*1000:
                f.seek(-1000*1000, os.SEEK_END)
                while True:
                    if f.read(1) in ('', '\n'):
                        break
                data = f.read()
                f.close()
                f = open(self.filename, 'wb')
                f.write(data)
            f.close()
            self.inner_file = open(self.filename, 'a')
        def write(self, data):
            self.inner_file.write(data)
        def flush(self):
            self.inner_file.flush()
    class TeePipe(object):
        def __init__(self, outputs):
            self.outputs = outputs
        def write(self, data):
            for output in self.outputs:
                output.write(data)
        def flush(self):
            for output in self.outputs:
                output.flush()
    class TimestampingPipe(object):
        def __init__(self, inner_file):
            self.inner_file = inner_file
            self.buf = ''
            self.softspace = 0
        def write(self, data):
            buf = self.buf + data
            lines = buf.split('\n')
            for line in lines[:-1]:
                self.inner_file.write('%s %s\n' % (datetime.datetime.now().strftime("%H:%M:%S.%f"), line))
                self.inner_file.flush()
            self.buf = lines[-1]
        def flush(self):
            pass
    logfile = LogFile(args.logfile)
    sys.stdout = sys.stderr = log.DefaultObserver.stderr = TimestampingPipe(TeePipe([sys.stderr, logfile]))
    if hasattr(signal, "SIGUSR1"):
        def sigusr1(signum, frame):
            print 'Caught SIGUSR1, closing %r...' % (args.logfile,)
            logfile.reopen()
            print '...and reopened %r after catching SIGUSR1.' % (args.logfile,)
        signal.signal(signal.SIGUSR1, sigusr1)
    task.LoopingCall(logfile.reopen).start(5)
    
    args.net = p2pool.nets[args.net_name + ('_testnet' if args.testnet else '')]
    
    if args.bitcoind_rpc_port is None:
        args.bitcoind_rpc_port = args.net.BITCOIN_RPC_PORT
    
    if args.bitcoind_p2p_port is None:
        args.bitcoind_p2p_port = args.net.BITCOIN_P2P_PORT
    
    if args.p2pool_port is None:
        args.p2pool_port = args.net.P2P_PORT
    
    if args.worker_port is None:
        args.worker_port = args.net.WORKER_PORT
    
    if args.address is not None:
        try:
            args.pubkey_hash = bitcoin.data.address_to_pubkey_hash(args.address, args.net)
        except Exception, e:
            raise ValueError('error parsing address: ' + repr(e))
    else:
        args.pubkey_hash = None
    
    reactor.callWhenRunning(main, args)
    reactor.run()
