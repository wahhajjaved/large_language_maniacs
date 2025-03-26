from collections import namedtuple
from ws4py.client.threadedclient import WebSocketClient as ThreadedWebSocketClient
from ws4py.client.geventclient import WebSocketClient as GeventWebSocketClient

import httplib
import json
import random
import re
import requests
import socket
import string
import wsaccel

wsaccel.patch_ws4py()

SOCKJS_OPEN = 'o'
SOCKJS_MESSAGE = 'm'
SOCKJS_ARRAY = 'a'
SOCKJS_HEARTBEAT = 'h'
SOCKJS_CLOSE = 'c'

SockJSFrame = namedtuple('SockJSFrame', ['type', 'content'])


class SockJSTransport(object):
    """
        Generic Transport wrapping SockJS communications.

        Not meant to be used by itself.
    """

    transport_id = ''
    transport_send_id = ''
    regular_schema = ''
    secure_schema = ''

    frame = namedtuple('SockJSFrame', ['data'])

    def __init__(self, url, prefix, use_gevent=False):
        """
            Parses url to found all the necessary bits for the connection.

            Each parsed url part is stored on the class to be used by the url
            properties.  If any part is missing, is infered from the other ones.

            The idea is that any transport subclass has all the nedded bits to use
            them as they need.
        """
        schema, host, port, path = re.match(r'(\w+)?(?:://)?([^:/]+)(?::(\d+))?/?(.*?)/?$', url).groups()

        # If schema not defined, determine by its port
        if schema is None:
            schema = self.secure_schema if port == 443 else self.regular_schema

        # if port is not defined define it by its schema
        if port is None:
            port = 443 if schema == self.secure_schema else 80

        path = path.strip('/')
        prefix = prefix.strip('/')

        # Generate the sockjs greeting id's
        server_id = str(random.randint(0, 1000))
        client_id = self.random_str(8)

        self.schema = schema
        self.port = port
        self.host = host
        self.prefix = prefix

        # Reassign class attributes to be able to acces them as class __dict__
        self.transport_id = self.transport_id
        self.transport_send_id = self.transport_send_id

        # The port_bit attribute shows the :port part of the url only if needed
        # This is just to obtain cleaner urls
        regular_http = self.port == 80 and self.schema == self.regular_schema
        regular_https = self.port == 443 and self.schema == self.secure_schema
        self.port_bit = '' if regular_http or regular_https else ':{}'.format(port)

        # Base path is the path to the sockjs endpoint, path is the full greeting url
        # whitout the transport identifier
        self.base_path = '/'.join([path])
        self.greeting_path = '/'.join([prefix, server_id, client_id])
        self.path = '/'.join([self.base_path, self.greeting_path])

        self.closing = False

    @property
    def base_url(self):
        """
            Url of the sockjs endpoint
        """
        return self.normalize('{schema}://{host}{port_bit}/{base_path}'.format(**self.__dict__))

    @property
    def url(self):
        """
            Greeting url of the sockjs
        """
        return self.normalize('{schema}://{host}{port_bit}/{path}/{transport_id}'.format(**self.__dict__))

    @property
    def send_url(self):
        """
            Sockjs url to be used if transport is not socket-like
        """
        return self.normalize('{schema}://{host}{port_bit}/{path}/{transport_send_id}'.format(**self.__dict__))

    @staticmethod
    def normalize(url):
        """
            Removes empty path parts from url
        """
        return re.sub(r'([^:]/)/', r'\1', url)

    @staticmethod
    def random_str(length):
        """
            Generates random strings for the sockjs id's
        """
        letters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(letters) for c in range(length))

    @staticmethod
    def parse_sockjs(frame):
        """
            Parses a sockjs frame and extracts it's content.
            Transforms arrays of messages into single message frames.
        """
        try:
            opcode, body = re.search(r'([acmoh])(.*)', frame, re.DOTALL | re.MULTILINE).groups()
        except:
            return [], frame

        # Try to parse body-less frames first, if found, return remaining data
        if opcode in 'oh':
            return [SockJSFrame(opcode, "")], body

        # Try to parse frames with array of messages, transformt opcode to 'm'
        # for each message in array
        elif opcode in "a":
            full_frames = []
            match = re.search(r'(\[".*?"\])(.*)$', frame, re.DOTALL | re.MULTILINE)
            # we have a full frame
            if match:
                full, remaining = match.groups()
                sockjs_array = json.loads(full)
                for item in sockjs_array:
                    full_frames.append(SockJSFrame('m', item))

                return full_frames, remaining
            # we failed in parsing a full frame, so assume it's partial, and continue
            else:
                return [], frame
        elif opcode == 'c':
            raise Exception('Close frame received, {}'.format(body))
        elif opcode == 'm':
            raise Exception('Message frame received, {}'.format(body))

        return [], ''

    def noop(self, *args):
        """
            NOOP :)
        """
        pass

    def bind(self, on_open=None, on_heartbeat=None, on_message=None, on_close=None):
        """
            Binds event handlers with known sockjs events. Defaults to noop if
            no biding is specified
        """
        self.on_open = on_open if on_open is not None else self.noop
        self.on_heartbeat = on_heartbeat if on_heartbeat is not None else self.noop
        self.on_message = on_message if on_message is not None else self.noop
        self.on_close = on_close if on_close is not None else self.noop

    def handle_sockjs_frame(self, frame):
        """
            Calls bindings based on sockjs frame type
        """
        if frame.type is SOCKJS_OPEN:
            self.on_open()
        elif frame.type is SOCKJS_HEARTBEAT:
            self.on_heartbeat()
        elif frame.type is SOCKJS_MESSAGE:
            self.on_message(frame)
        elif frame.type is SOCKJS_CLOSE:
            self.on_close(frame)

    def sockjs_info(self):
        """
            Retrieves sockjs endpoint information
        """
        response = requests.get(self.base_url + '/info')
        return response.content

    def send(self, message):
        wrapped = '["{}"]'.format(message)
        self._send(wrapped)
        return wrapped

    def connect(self):
        """
            Initiate transport connection
        """
        return self._connect()

    def start(self):
        """
            Start transport listening loop
        """
        self._start()

    def close(self):
        """
            Closes transport connection
        """
        self._close()

    # Methods to be overriden by transport
    # With specific implementations
    def _connect(self):
        pass

    def _start(self):
        pass

    def _close(self):
        pass


class XHRStreamingTransport(SockJSTransport):
    """
        Transport that uses xhr streaming to communicate.

        Reading is made by maintaining an unfinished requests tho the sockjs endpoint,
        acting as a unidirectional socket.

        Writing is made by sending data to the send_url in separate requests.

        It's expected that the server finish the request on connection close.
    """
    transport_id = 'xhr_streaming'
    transport_send_id = 'xhr_send'
    regular_schema = 'http'
    secure_schema = 'https'

    @property
    def url(self):
        """
            Sockjs path to be used if transport needs it without the host part
        """
        return self.normalize('/{greeting_path}/{transport_id}'.format(**self.__dict__))

    # SockJSTransport implementation

    def _send(self, message):
        """
            Make a Http request to send the message to the server
        """
        response = requests.post(
            self.send_url,
            message,
            headers={'Content-Type': 'text/plain'})
        return response.status_code in (200, 204)

    def _connect(self):
        """
            Start streaming request and wrap it with a socket
        """
        conn = httplib.HTTPConnection(self.host, self.port)
        conn.request('POST', self.url)
        response = conn.getresponse()
        self.sock = socket.fromfd(response.fileno(), socket.AF_INET, socket.SOCK_STREAM)

    def _start(self):
        """
            Loops until closing "event" is found.
        """
        data = ""
        partial = ''
        while not self.closing:
            chunk = data = self.sock.recv(1)
            frames = []
            data = partial + chunk
            frames, partial = self.parse_sockjs(data)

            for frame in frames:
                self.handle_sockjs_frame(frame)

    def _close(self):
        """
            Sets the closing flag to stop polling
        """
        self.closing = True


class XHRPollingTransport(SockJSTransport):
    """
        Transport that uses xhr polling to communicate.

        Reading is made by repeatedly making requests tho the sockjs endpoint,
        expecting the server to finish the request when data is received.

        Writing is made by sending data to the send_url in separate requests.

        There's no socket-like communication being active here, to close the connection
        we simply stop polling when the self.closing flag is set.

    """
    transport_id = 'xhr'
    transport_send_id = 'xhr_send'
    regular_schema = 'http'
    secure_schema = 'https'

    # SockJSTransport implementation

    def _send(self, message):
        """
            Make a Http requst to send the message to the server
        """
        response = requests.post(
            self.send_url,
            message,
            headers={'Content-Type': 'text/plain'})
        return response.status_code in (200, 204)

    def _start(self):
        """
            Loops until closing "event" is found.
        """
        data = ""
        partial = ''
        while not self.closing:
            chunk = requests.post(self.url).content
            frames = []
            data = partial + chunk
            frames, partial = self.parse_sockjs(data)

            for frame in frames:
                self.handle_sockjs_frame(frame)

    def _close(self):
        """
            Sets the closing flag to stop polling
        """
        self.closing = True


class WebsocketTransport(SockJSTransport):
    """
        Transport that uses a websocket to communicate.

        Reading and writing is made trough the ws object created. This object
        manages its own thread that listens at the opened socket.
    """

    transport_id = 'websocket'
    regular_schema = 'ws'
    secure_schema = 'wss'

    def __init__(self, url, prefix, use_gevent=False):
        """
            Custom init method to format specific websocket schema, if url
            has been parsed from a http resource
        """
        self.use_gevent = True
        self.client_class = GeventWebSocketClient if use_gevent else ThreadedWebSocketClient
        super(WebsocketTransport, self).__init__(url.replace('http', 'ws'), prefix)

    # SockJSTransport implementation

    def _send(self, message):
        """
            Sends a message trough the websocket connection
        """
        self.ws.send(message)

    def _connect(self):
        """
            Opens the websocket connetion. Opened event on the
            ws object is eluded, because open event is managed by
            sockhs sending an OPEN frame, not websocket opening the connection.
        """
        self.ws = self.client_class(self.url)
        self.ws.opened = self.noop
        self.ws.closed = self.ws_on_close

        # When on gevent mode, messages will be handled inside the
        # gevent receive loop, so don't bind received_message to be
        # able to exit the loop on close call
        if not self.use_gevent:
            self.ws.received_message = self.ws_handle_frame

        self.ws.connect()

    def _start(self):
        """
            Start listening thread
        """
        if self.use_gevent:
            self.ws_gevent_loop()
        else:
            self.ws.run_forever()

    def _close(self):
        """
            Close websocket connection and thread
        """
        self.ws.close()
        self.closing = True

    # Websocket object event handlers

    def ws_on_close(self, code, reason):
        """
            Triggered by the websocket client thread when a remote disconnection occurs.
        """
        self.on_close('{} "{}"'.format(code, reason))

    def ws_handle_frame(self, ws_frame):
        """
            Triggered by the websocket client thread when a frame arrives
        """
        frames, partial = self.parse_sockjs(ws_frame.data)

        for frame in frames:
            self.handle_sockjs_frame(frame)

    def ws_gevent_loop(self):
        """
            Alternative loop to use when running on gevent
        """
        while not self.closing:
            ws_frame = self.ws.receive()
            if ws_frame is not None:
                self.ws_handle_frame(ws_frame)
            else:
                break

# Make a mapping of the available transports, indexed by transport_id
TRANSPORTS = set([obj for obj in locals().values() if getattr(obj, '__base__', '') is SockJSTransport])
TRANSPORTS = {transport.transport_id: transport for transport in TRANSPORTS}
