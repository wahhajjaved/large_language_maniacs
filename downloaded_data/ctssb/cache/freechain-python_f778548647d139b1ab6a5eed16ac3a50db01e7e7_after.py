import threading
import asyncio
import janus
import time
import json

from blockchain.events import Events
from blockchain.network import Network
from blockchain.chain import *
from blockchain.loaf import Loaf
from blockchain.block import Block
from blockchain.validator import Validator

from blockchain.common import *

from queue import Empty as SyncQueueEmpty

#   _   _           _
#  | \ | |         | |
#  |  \| | ___   __| | ___
#  | . ` |/ _ \ / _` |/ _ \
#  | |\  | (_) | (_| |  __/
#  \_| \_/\___/ \__,_|\___|
#

class Node():
    def __init__(self, port):
        """ Node class constructor
        """
        self._network = Network(port)

        self._chain = Chain()
        self._loaf_pool = {}
        self._loaf_pool_lock = threading.RLock()
        self._mined_loaves = {}
        self._mined_loaves_lock = threading.RLock()

        self._events_thread = threading.Thread(target=self._start_events_thread,
                                               daemon=True)
        self._events_thread.start()
        time.sleep(0.5) ## TODO: Shall be fixed to a smarter solution
        self._worker_thread = threading.Thread(target=self._worker_thread,
                                               daemon=True)

    def start(self):
        """ Starts the node by creating a worker thread and a network thread """
        self._network.start()
        self._worker_thread.start()

        def new_connection_callback(websocket):
            self._get_length(websocket)
        Events.Instance().register_callback(EVENTS_TYPE.NEW_CLIENT_CONNECTION,
                                            new_connection_callback)

    def attach_loaf_validator(self, function):
        Validator.Instance().attach_loaf_validator(function)

    def attach_block_validator(self, function):
        Validator.Instance().attach_block_validator(function)

    def connect_node(self, ip, port=9000):
        """ Connects to another node through its IP address """
        self._network.connect_node(ip, port)

    def add_loaf(self, loaf):
        with self._loaf_pool_lock:
            if not loaf.validate():
                print(fail('Loaf could not validate'))
                return False
            if loaf.get_hash() in self._loaf_pool:
                return False
            if loaf.get_hash() in self._mined_loaves.keys():
                print(warning('Loaf has already been mined'))
                return False
            self._loaf_pool[loaf.get_hash()] = loaf
            return True

    def add_block(self, block):
        height = block.get_height()
        with self._loaf_pool_lock:
            for loaf in block.get_loaves():
                try:
                    del self._loaf_pool[loaf.get_hash()]
                except KeyError:
                    pass
        with self._mined_loaves_lock:
            for loaf in block.get_loaves():
                self._mined_loaves[loaf.get_hash()] = height
        return self._chain.add_block(block)

    def remove_block(self, height):
        for loaf in self._chain.get_block(height).get_loaves():
            with self._mined_loaves_lock:
                try:
                    del self._mined_loaves[loaf.get_hash()]
                except KeyError:
                    pass
            with self._loaf_pool_lock:
                self._loaf_pool[loaf.get_hash()] = loaf
        self._chain.remove_block(height)

    def broadcast_loaf(self, loaf):
        """ Validates a loaf. If it is validated, it puts the loaves hash in
            the loaf pool and broadcasts it to all connected nodes
        """
        self._network.broadcast(
            self._json({'type': 'request',
                        'function': FUNCTIONS.BROADCAST_LOAF,
                        'loaf': loaf}))

    def broadcast_block(self, block):
        self._network.broadcast(
            self._json({'type': 'request',
                        'function': FUNCTIONS.BROADCAST_BLOCK,
                        'block': block}))

    def mine(self):
        with self._loaf_pool_lock:
            loaves_total = 0
            loaves_hash = []
            loaves = []
            loaf_pool_keys = list(self._loaf_pool.keys())
            loaves_total = min(1000, len(loaf_pool_keys))
            loaves_hash = loaf_pool_keys[:loaves_total]
            for h in loaves_hash:
                loaves.append(self._loaf_pool[h])

            block = self._chain.mine_block(loaves)

            if block.validate():
                return block
            else:
                print(fail('block could not be mined'))
                return None

    def _get_length(self, websocket):
        """ Requests the length of the blockchain from a node """

        self._network.send(websocket, self._json(
            {'type': 'request',
             'function': FUNCTIONS.GET_LENGTH}))

    def _get_hash(self, websocket, height):
            self._network.send(websocket, self._json(
                {'type': 'request',
                 'function': FUNCTIONS.GET_HASH,
                 'height': height}))

    def _get_blocks(self, websocket, offset, length):
        """ Requests  missing blocks from a node """

        self._network.send(websocket, self._json(
            {'type': 'request',
             'function': FUNCTIONS.GET_BLOCKS,
             'offset': offset,
             'length': length}))

    def _start_events_thread(self):
        """ Starts an event thread that runs untill completion """
        try:
            Events.Instance().start()
        except:
            print(fail('fatal error regarding events'))
            raise

    def _worker_thread(self):
        """ Starts the worker thread, which listens for requests from other
            nodes in the network.
        """
        while True:
            for websocket in list(self._network.get_queues().keys()):
                try:
                    raw_data = self._network.recv_nowait(websocket)
                    message = json.loads(raw_data.decode('utf-8'))

                    if message['type'] == 'error':
                        if 'description' in message:
                            desc = message['description']
                        else:
                            desc = 'No description'
                        Events.Instance().notify(EVENTS_TYPE.RECEIVED_ERROR,
                                                 desc)
                        print(fail('Error received: ' + desc))
                    elif message['type'] != 'request' and \
                         message['type'] != 'response':
                        self._network.send(
                            websocket, self._json({'type': 'error',
                                                   'description': \
                                                   'type is not supported'}))
                    elif message['function'] == FUNCTIONS.GET_LENGTH:
                        self._handle_get_length(message, websocket)
                    elif message['function'] == FUNCTIONS.GET_HASH:
                        self._handle_get_hash(message, websocket)
                    elif message['function'] == FUNCTIONS.GET_BLOCKS:
                        self._handle_get_blocks(message, websocket)
                    elif message['function'] == FUNCTIONS.BROADCAST_LOAF:
                        self._handle_broadcast_loaf(message)
                    elif message['function'] == FUNCTIONS.BROADCAST_BLOCK:
                        self._handle_broadcast_block(message, websocket)
                    else:
                        self._network.send(
                            websocket, self._json({'type': 'error',
                                                   'description':
                                                   'Unsupported function'}))

                except (AttributeError, KeyError):
                    response = self._json({'type': 'error',
                                           'description': 'Attribute or ' + \
                                           'KeyError. Consider adding "raise"'})
                    self._network.send(websocket, response)
                except SyncQueueEmpty:
                    pass
                except:
                    print(fail("fatal error"))
                    raise
            time.sleep(0.05)

    def _handle_get_length(self, message, websocket):
        """ Reads a request for the length of the blockchain. If local
            blockchain is shorter, it sends a request for missing blocks
        """
        if message['type'] == 'request':
            chain_length = self._chain.get_length()
            response = self._json({'type': 'response',
                                   'function': FUNCTIONS.GET_LENGTH,
                                   'length': chain_length})
            self._network.send(websocket, response)

        elif message['type'] == 'response':
            chain_length = self._chain.get_length()
            response_length = message['length']
            print(info('Recieved blockchain length is: ' +
                       str(response_length)))
            print(info('local block length is : ' +
                       str(chain_length)))
            if response_length > chain_length:
                print(info('Requesting hash of block: ' + str(chain_length-1)))
                self._get_hash(websocket, chain_length-1)
            else:
                print(info('Keeping local blocks'))

    def _handle_get_hash(self, message, websocket):
        if message['type'] == 'request':
            height = message['height']
            hash = self._chain.get_block(height).get_hash()
            length = self._chain.get_length()
            response = self._json({'type': 'response',
                                   'function': FUNCTIONS.GET_HASH,
                                   'height': height,
                                   'hash': hash})
            self._network.send(websocket, response)

        elif message['type'] == 'response':
            height = message['height']
            block_hash = self._chain.get_block(height).get_hash()
            response_hash = message['hash']
            if block_hash == response_hash:
                print(info('Block hashes of height: ' + str(height) +
                           ' matches'))
                print(info('Requesting blocks'))
                self._get_blocks(websocket, height+1, -1)
            else:
                print(info('Block hashes of height: ' + str(height) +
                           ' do not match'))
                print(info('Requesting block hash of height: ' + str(height-1)))
                self._get_hash(websocket, height-1)

    def _handle_get_blocks(self, message, websocket):
        """ Reads a request for missing blocks and sends them if local chain
            is longer
        """
        if message['type'] == 'request':
            if message['length'] == -1:
                length = self._chain.get_length() - message['offset']
            else:
                length = message['length']
            if self._chain.get_length() >= \
               message['offset'] + length:
                blocks = []
                for i in range(length):
                    blocks.append(self._chain.get_block(i + message['offset']))
                response = self._json({'type': 'response',
                                       'function': FUNCTIONS.GET_BLOCKS,
                                       'blocks': blocks})
                self._network.send(websocket, response)
            else:
                self._network.send(
                    websocket,
                    self._json({'type': 'error',
                                'description': 'requested length is ' + \
                                'longer than chain'}))

        elif message['type'] == 'response':
            blocks = []
            for block_dict in message['blocks']:
                blocks.append(Block.create_block_from_dict(block_dict))
            if blocks[0].get_height()+len(blocks) <= self._chain.get_length():
                print(fail('Replacing the local blocks with the received ' + \
                           'ones will result in a shorther blockchain'))
                return
            for i in range(len(blocks)):
                if not blocks[i].validate():
                    print(fail('Failed to validate block: ' + str(blocks[k])))
                    return
                if i > 0 and blocks[i-1].get_hash() != \
                   blocks[i].get_previous_block_hash():
                    print(fail('Hash of previous block, does not match ' + \
                               'previous_block_hash'))
                    return

            print(info('Replacing blocks from height ' +
                       str(blocks[0].get_height()) + ' and up'))

            for i in reversed(range(blocks[0].get_height(),
                                    self._chain.get_length())):
                self.remove_block(i)
            for block in blocks:
                if not self.add_block(block):
                    print(fail('block of height ' + str(block.get_height()) +
                               ' cannot be added'))
                    return
            Events.Instance().notify(EVENTS_TYPE.BLOCKS_ADDED, None)
            print(info('blocks succesfully added to blockchain'))

    def _handle_broadcast_loaf(self, message):
        """ Receives and validates a loaf. If loaf is not validated,
            an error message is displayed. If loaf is validated, it checks
            whether loaf already exists in the local loaf pool. If it does not
            exist in the loaf pool, it adds the loaf to the loaf pool and
            broadcasts the loaf to all connected nodes.
        """
        loaf = Loaf.create_loaf_from_dict(message['loaf'])
        with self._loaf_pool_lock:
            if self.add_loaf(loaf):
                print(info('Received loaf and forwarding it'))
                Events.Instance().notify(EVENTS_TYPE.RECEIVED_LOAF, loaf)
                self.broadcast_loaf(loaf)

    def _handle_broadcast_block(self, message, websocket):
        block = Block.create_block_from_dict(message['block'])
        block_height = block.get_height()

        if block.get_height() > self._chain.get_length():
            self._get_length(websocket)
        elif block.get_height() < self._chain.get_length():
            return
        elif self.add_block(block):
            print(info('Block succesfully added'))
            Events.Instance().notify(EVENTS_TYPE.RECEIVED_BLOCK, block)
            self.broadcast_block(block)
        else:
            print(fail('block could not be added'))

    @staticmethod
    def _json(dictio):
        """ Serializes object to a JSON formatted string, encodes to utf-8
            and returns
        """
        return json.dumps(dictio, cls=BlockEncoder).encode('utf-8')
