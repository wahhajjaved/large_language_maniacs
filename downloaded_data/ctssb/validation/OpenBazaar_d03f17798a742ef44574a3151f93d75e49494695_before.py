import json
import logging
from pprint import pformat
from pyee import EventEmitter
from threading import Thread
from node.network_util import count_incoming_packet, count_outgoing_packet
import sys
import time

import obelisk
import socket

from node import constants, network_util
from node.crypto_util import Cryptor
from node.guid import GUIDMixin
from rudp.connection import Connection
from rudp.packetsender import PacketSender
from tornado import ioloop


class PeerConnection(GUIDMixin, object):
    def __init__(self, guid, transport, hostname, port=12345, nickname="", peer_socket=None, nat_type=None):

        GUIDMixin.__init__(self, guid)

        self.transport = transport

        self.log = logging.getLogger(
            '[%s] %s' % (self.transport.market_id, self.__class__.__name__)
        )

        self.log.info('Created a peer connection object')

        self.ee = EventEmitter()
        self.sock = peer_socket
        self.hostname = hostname
        self.port = port
        self.nickname = nickname
        self.nat_type = nat_type
        self.pinging = False
        self.relaying = False
        self.reachable = False
        self.last_reached = time.time()
        self.seed = False

        self.init_packetsender()
        self.setup_emitters()

        if nat_type == 'Symmetric NAT':
            self.reachable = True
            self.relaying = True
            self._rudp_connection._sender._packet_sender.relaying = True
            self.send_relayed_ping()
        else:

            self.pinging = True
            self.send_ping()

            def no_response():

                hello_msg = {
                    'type': 'hello',
                    'pubkey': self.transport.pubkey,
                    'senderGUID': self.transport.guid,
                    'hostname': self.transport.hostname,
                    'nat_type': self.transport.nat_type,
                    'port': self.transport.port,
                    'senderNick': self.transport.nickname,
                    'v': constants.VERSION
                }

                if not self.reachable:
                    self.log.error('No response from peer.')
                    self.reachable = True
                    self.relaying = True
                    self._rudp_connection._sender._packet_sender.relaying = True

                    self.log.debug('Relay Hello through Seed')
                    hello_msg['relayed'] = True

                    self.send_to_rudp(json.dumps(hello_msg))
                    self.send_relayed_ping()
                else:
                    self.log.debug('Sending Hello')
                    self.send_raw(
                        json.dumps(hello_msg)
                    )
                    self.send_ping()

                self.pinging = False
                ioloop.IOLoop.instance().call_later(2, self.transport.search_for_my_node)

            ioloop.IOLoop.instance().call_later(2, no_response)

        self.seed = False
        self.punching = False

        # Recurring check for peer accessibility
        def pinger():
            self.log.debug('Pinging: %s', self.guid)

            if time.time() - self.last_reached <= 15:
                self.send_ping()
                # if not self.relaying or self.transport.seed_mode:
                #     self.send_ping()
                # else:
                #     self.send_relayed_ping()
            else:
                self.ping_task.stop()
                self.reachable = False
                if self.guid:
                    self.log.error('Peer not responding. Removing.')
                    self.transport.dht.remove_peer(self.guid)

                # Update GUI if possible
                if self.transport.handler:
                    self.transport.handler.refresh_peers()

                    # yappi.get_thread_stats().print_all()

        self.ping_task = ioloop.PeriodicCallback(pinger, 5000, io_loop=ioloop.IOLoop.instance())
        self.ping_task.start()

    def setup_emitters(self):
        self.log.debug('Setting up emitters')
        self.ee = EventEmitter()

        @self._rudp_connection._sender.ee.on('timeout')
        def on_timeout(data):  # pylint: disable=unused-variable
            self.log.debug('Node Sender Timed Out')
            # self.transport.dht.remove_peer(self.guid)

        @self._rudp_connection.ee.on('data')
        def handle_recv(msg):  # pylint: disable=unused-variable

            self.log.debug('Got the whole message: %s', msg.get('payload'))
            payload = msg.get('payload')

            if payload[:1] == '{':
                try:
                    payload = json.loads(msg.get('payload'))
                    self.transport.listener.on_raw_message(payload)
                    return
                except Exception as e:
                    self.log.debug('Problem with serializing: %s', e)
            else:
                try:
                    payload = msg.get('payload').decode('hex')
                    self.transport.listener.on_raw_message(payload)
                except Exception as e:
                    self.log.debug('not yet %s', e)
                    self.transport.listener.on_raw_message(msg.get('payload'))


    def send_ping(self):
        self.sock.sendto('ping', (self.hostname, self.port))
        count_outgoing_packet('ping')
        return True

    def send_relayed_ping(self):
        self.log.debug('Sending Relay Ping to: %s', self)
        for x in self.transport.dht.active_peers:
            if x.hostname == 'seed2.openbazaar.org' or x.hostname == '205.186.156.31':
                self.sock.sendto('send_relay_ping %s' % self.guid, (x.hostname, x.port))
                count_outgoing_packet('send_relay_ping %s' % self.guid, (x.hostname, x.port))
        return True

    def init_packetsender(self):

        self._packet_sender = PacketSender(
            self.sock,
            self.hostname,
            self.port,
            self.guid,
            self.transport,
            self.nat_type,
            self.relaying
        )

        self._rudp_connection = Connection(self._packet_sender)

        self.packetsmasher = {}
        self.message_size = 0
        self.is_listening = True
        self.hello = False

    def send_to_sock(self, data):
        self.sock.sendto(data, (self.hostname, self.port))
        count_outgoing_packet(data)

    def send(self, data, callback):
        self.send_raw(json.dumps(data), callback)

    def send_raw(self, serialized, callback=None, relay=False):

        if self.transport.seed_mode or relay or self.seed:
            self.send_to_rudp(serialized)
            return

        # if self.relaying:
        # self.log.debug('Relay through seed')
        # self.transport.relay_message(serialized, self.guid)
        #     return

        def sending_out():

            if not self.pinging:
                if self.reachable:
                    self.send_to_rudp(serialized)
                    return
                else:
                    if self.nat_type == 'Restric NAT' and not self.punching and not self.relaying:
                        self.log.debug('Found restricted NAT client')
                        self.transport.start_mediation(self.guid)
                    if self.nat_type == 'Full Cone' and not self.relaying:
                        self.send_to_rudp(serialized)
                        return
                    else:
                        self.log.debug('Relay through seed')
                        # self.transport.relay_message(serialized, self.guid)
                        self.send_to_rudp(serialized)
                        return

            ioloop.IOLoop.instance().call_later(5, sending_out)

        sending_out()

    def send_to_rudp(self, data):
        self._rudp_connection.send(data)

    def reset(self):
        self.log.debug('Reset 2')
        self._rudp_connection._sender._sending = None
        self._rudp_connection._sender._push()
        self.is_listening = False


class CryptoPeerConnection(PeerConnection):
    def __init__(self, transport, hostname, port, pub=None, guid=None, nickname="",
                 sin=None, rudp_connection=None, peer_socket=None, nat_type=None):

        PeerConnection.__init__(self, guid, transport, hostname, port, nickname, peer_socket, nat_type)

        self.pub = pub
        self.sin = sin
        self.waiting = False  # Waiting for ping-pong

    def __repr__(self):
        return '{ guid: %s, hostname: %s, port: %s, pubkey: %s reachable: %s nat: %s relaying: %s}' % (
            self.guid, self.hostname, self.port, self.pub, self.reachable, self.nat_type,
            self.relaying
        )

    @staticmethod
    def generate_sin(guid):
        return obelisk.EncodeBase58Check('\x0F\x02%s' + guid.decode('hex'))

    def sign(self, data):
        return self.transport.cryptor.sign(data)

    def encrypt(self, data):
        """
        Encrypt the data with self.pub and return the ciphertext.
        @raises Exception: The encryption failed.
        """
        assert self.pub, "Attempt to encrypt without key."
        cryptor = Cryptor(pubkey_hex=self.pub)

        # zlib the data
        data = data.encode('zlib')

        return cryptor.encrypt(data)

    def send(self, data, callback=None):
        assert self.guid, 'Uninitialized own guid'

        if not self.pub:
            self.log.warn('There is no public key for encryption')
            return

        # Include sender information and version
        data['guid'] = self.guid
        data['senderGUID'] = self.transport.guid
        data['pubkey'] = self.transport.pubkey
        data['senderNick'] = self.transport.nickname
        data['senderNamecoin'] = self.transport.namecoin_id
        data['v'] = constants.VERSION

        # Sign cleartext data
        sig_data = json.dumps(data).encode('hex')
        signature = self.sign(sig_data).encode('hex')

        self.log.datadump('Sending to peer: %s %s', self.hostname,
                          pformat(data))

        try:
            # Encrypt signature and data
            data = self.encrypt(json.dumps({
                'sig': signature,
                'data': sig_data
            }))
        except Exception as exc:
            self.log.error('Encryption failed. %s', exc)
            return

        try:
            # self.send_raw(base64.b64encode(data), callback)
            # TODO: Refactor to protobuf
            self.send_raw(data, callback)
        except Exception as exc:
            self.log.error("Was not able to send raw data: %s", exc)


class PeerListener(GUIDMixin):
    def __init__(self, hostname, port, guid, data_cb):
        super(PeerListener, self).__init__(guid)

        self.hostname = hostname
        self.port = port
        self._data_cb = data_cb
        self.is_listening = False
        self.socket = None
        self.stream = None
        self._ok_msg = None
        self._connections = {}

        self.log = logging.getLogger(self.__class__.__name__)

        self.ee = EventEmitter()

    def set_ip_address(self, new_ip):
        self.hostname = new_ip
        if not self.is_listening:
            return

        try:
            self.stream.close()
            self.listen()
        except Exception as e:
            self.log.error('[Requests] error: %s', e)

    def set_ok_msg(self, ok_msg):
        self._ok_msg = ok_msg

    def listen(self):
        self.log.info("Listening at: %s:%s", self.hostname, self.port)

        if network_util.is_loopback_addr(self.hostname):
            # we are in local test mode so bind that socket on the
            # specified IP
            self.log.info("PeerListener.socket.bind('%s') LOOPBACK", self.hostname)
            self._prepare_datagram_socket()
        elif '[' in self.hostname:
            self.log.info("PeerListener.socket.bind('tcp://[*]:%s') IPV6", self.port)
            self.socket.ipv6 = True
            self._prepare_datagram_socket(socket.AF_INET6)
        else:
            self.log.info("PeerListener.socket.bind('tcp://*:%s') IPV4", self.port)
            # Temporary while I fix things
            self.hostname = '0.0.0.0'
            self._prepare_datagram_socket()

        self.is_listening = True

        def start_listening():
            while self.is_listening:

                try:
                    data, addr = self.socket.recvfrom(2048)
                    self.log.debug('Got data from %s:%d: %s', addr[0], addr[1], data[:50])
                    count_incoming_packet(data)

                    if data[:4] == 'ping':
                        self.socket.sendto('pong', (addr[0], addr[1]))
                        count_outgoing_packet('pong')
                    elif data[:4] == 'pong':
                        self.ee.emit('on_pong_message', (data, addr))

                    elif data[:15] == 'send_relay_ping':
                        self.ee.emit('on_send_relay_ping', (data, addr))

                    elif data[:10] == 'relay_ping':
                        data = data.split(' ')
                        sender = self.guid
                        recipient = data[1]
                        self.socket.sendto('send_relay_pong %s %s' % (sender, recipient), (addr[0], addr[1]))
                        count_outgoing_packet('send_relay_pong %s %s' % (sender, recipient))

                    elif data[:15] == 'send_relay_pong':
                        self.ee.emit('on_send_relay_pong', (data, addr))

                    elif data[:9] == 'heartbeat':
                        self.log.debug('We just received a heartbeat.')

                    elif data[:7] == 'relayto':
                        self.log.debug('Relay To Packet')
                        self.ee.emit('on_relayto', data)

                    elif data[:6] == 'relay ':
                        self.log.debug('Relay Packet')
                        self.ee.emit('on_message', (data, addr))

                    else:
                        self.ee.emit('on_message', (data, addr))

                except socket.timeout as e:
                    err = e.args[0]

                    if err == 'timed out':
                        time.sleep(0.5)
                        continue
                    else:
                        sys.exit(1)
                except socket.error:
                    # No data. This is normal.
                    pass
                    # except AttributeError as err:
                    # print 'Packet was jacked up: %s', err

        Thread(target=start_listening).start()

    def on_raw_message(self, serialized):
        self.log.info("connected %d", len(serialized))
        try:
            msg = json.loads(serialized[0])
        except ValueError:
            self.log.info("incorrect msg! %s", serialized)
            return

        self._data_cb(msg)

    def _prepare_datagram_socket(self, family=socket.AF_INET):
        self.socket = socket.socket(family, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self.socket.setblocking(0)
        self.socket.bind((self.hostname, self.port))


class CryptoPeerListener(PeerListener):
    def __init__(self, hostname, port, pubkey, secret, guid, data_cb):

        super(CryptoPeerListener, self).__init__(hostname, port, guid, data_cb)

        self.pubkey = pubkey
        self.secret = secret

        # FIXME: refactor this mess
        # this was copied as is from CryptoTransportLayer
        # soon all crypto code will be refactored and this will be removed
        self.cryptor = Cryptor(pubkey_hex=self.pubkey, privkey_hex=self.secret)

    def is_plaintext_message(self, message):
        """
        Return whether message is a plaintext handshake

        :param message: serialized JSON
        :return: True if proper handshake message
        """
        if type(message) is 'dict':
            return message.get('type')

        try:
            message = json.loads(message)
        except (ValueError, TypeError) as e:
            self.log.debug('Cannot deserialize the JSON: %s ', e)
            return False

        return 'type' in message

    def on_raw_message(self, serialized):
        """
        Handles receipt of encrypted/plaintext message
        and passes to appropriate callback.

        :param serialized:
        :return:
        """

        if not self.is_plaintext_message(serialized):
            message = self.process_encrypted_message(serialized)
        else:
            message = json.loads(serialized)

            # If relayed then unwrap and process again
            if message['type'] == 'relayed_msg':
                self.on_raw_message(message['data'].decode('hex'))
                return

        self.log.debugv('Received message of type "%s"',
                        message.get('type', 'unknown'))

        # Execute callback on message type
        if self._data_cb:
            self._data_cb(message)
        else:
            self.log.debugv('Callbacks not ready yet')

    def process_encrypted_message(self, encrypted_message):
        if type(encrypted_message) is dict:
            message = encrypted_message
        else:
            try:

                message = self.cryptor.decrypt(encrypted_message)

                # un-zlib data
                message = message.decode('zlib')

                message = json.loads(message)

                signature = message['sig'].decode('hex')
                signed_data = message['data']

                self.log.debug('Decrypted Data: %s', message)

                if CryptoPeerListener.validate_signature(signature, signed_data):
                    message = signed_data.decode('hex')
                    message = json.loads(message)

                    if message.get('guid') != self.guid:
                        return False

                else:
                    return
            except RuntimeError as e:
                self.log.error('Could not decrypt message properly %s', e)
                return False
            except Exception as e:
                self.log.error('Cannot unpack data: %s', e)
                return False

        return message

    @staticmethod
    def validate_signature(signature, data):
        data_json = json.loads(data.decode('hex'))
        sig_cryptor = Cryptor(pubkey_hex=data_json['pubkey'])

        if sig_cryptor.verify(signature, data):
            return True
        else:
            return False
