"""
    A simple proxy server implementation, which always reads all of a server
    response into memory, performs some transformation, and then writes it back
    to the client. 

    Development started from Neil Schemenauer's munchy.py
"""
import sys, os, time, string, socket, urlparse, re, select, copy, base64
import shutil, tempfile
import optparse, SocketServer, ssl
import utils, controller

NAME = "mitmproxy"


class ProxyError(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg

    def __str__(self):
        return "ProxyError(%s, %s)"%(self.code, self.msg)


class Config:
    def __init__(self, certfile = None, ciphers = None, cacert = None):
        self.certfile = certfile
        self.ciphers = ciphers
        self.cacert = cacert
        self.certdir = None


def read_chunked(fp):
    content = ""
    while 1:
        line = fp.readline()
        if line == "":
            raise IOError("Connection closed")
        if line == '\r\n' or line == '\n':
            continue
        length = int(line,16)
        if not length:
            break
        content += fp.read(length)
        line = fp.readline()
        if line != '\r\n':
            raise IOError("Malformed chunked body")
    while 1:
        line = fp.readline()
        if line == "":
            raise IOError("Connection closed")
        if line == '\r\n' or line == '\n':
            break
    return content
    

def read_http_body(rfile, connection, headers, all):
    if headers.has_key('transfer-encoding'):
        if not ",".join(headers["transfer-encoding"]) == "chunked":
            raise IOError('Invalid transfer-encoding')
        content = read_chunked(rfile)
    elif headers.has_key("content-length"):
        content = rfile.read(int(headers["content-length"][0]))
    elif all:
        content = rfile.read()
        connection.close = True
    else:
        content = ""
    return content


def parse_url(url):
    """
        Returns a (scheme, host, port, path) tuple, or None on error.
    """
    scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
    if not scheme:
        return None
    if ':' in netloc:
        host, port = string.split(netloc, ':')
        port = int(port)
    else:
        host = netloc
        if scheme == "https":
            port = 443
        else:
            port = 80
    path = urlparse.urlunparse(('', '', path, params, query, fragment))
    if not path:
        path = "/"
    return scheme, host, port, path


def parse_request_line(request):
    """
        Parse a proxy request line. Return (method, scheme, host, port, path, minor).
        Raise ProxyError on error.
    """
    try:
        method, url, protocol = string.split(request)
    except ValueError:
        raise ProxyError(400, "Can't parse request")
    if method == 'CONNECT':
        scheme = None
        path = None
        try:
            host, port = url.split(":")
        except ValueError:
            raise ProxyError(400, "Can't parse request")
        port = int(port)
    else:
        if url.startswith("/") or url == "*":
            scheme, port, host, path = None, None, None, url
        else:
            parts = parse_url(url)
            if not parts:
                raise ProxyError(400, "Invalid url: %s"%url)
            scheme, host, port, path = parts
    if not protocol.startswith("HTTP/"):
        raise ProxyError(400, "Unsupported protocol")
    major,minor = protocol.split('/')[1].split('.')
    major = int(major)
    minor = int(minor)
    if major != 1:
        raise ProxyError(400, "Unsupported protocol")
    return method, scheme, host, port, path, minor


class Request(controller.Msg):
    FMT = '%s %s HTTP/1.1\r\n%s\r\n%s'
    FMT_PROXY = '%s %s://%s:%s%s HTTP/1.1\r\n%s\r\n%s'
    def __init__(self, client_conn, host, port, scheme, method, path, headers, content, timestamp=None):
        self.client_conn = client_conn
        self.host, self.port, self.scheme = host, port, scheme
        self.method, self.path, self.headers, self.content = method, path, headers, content
        self.timestamp = timestamp or time.time()
        self.close = False
        controller.Msg.__init__(self)

    def set_replay(self):
        self.client_conn = None

    def is_replay(self):
        if self.client_conn:
            return False
        else:
            return True

    def is_cached(self):
        return False

    def load_state(self, state):
        if state["client_conn"]:
            if self.client_conn:
                self.client_conn.load_state(state["client_conn"])
            else:
                self.client_conn = ClientConnect.from_state(state["client_conn"])
        else:
            self.client_conn = None
        self.host = state["host"]
        self.port = state["port"]
        self.scheme = state["scheme"]
        self.method = state["method"]
        self.path = state["path"]
        self.headers = utils.Headers.from_state(state["headers"])
        self.content = base64.decodestring(state["content"])
        self.timestamp = state["timestamp"]

    def get_state(self):
        return dict(
            client_conn = self.client_conn.get_state() if self.client_conn else None,
            host = self.host,
            port = self.port,
            scheme = self.scheme,
            method = self.method,
            path = self.path,
            headers = self.headers.get_state(),
            content = base64.encodestring(self.content),
            timestamp = self.timestamp,
        )

    @classmethod
    def from_state(klass, state):
        return klass(
            ClientConnect.from_state(state["client_conn"]),
            state["host"],
            state["port"],
            state["scheme"],
            state["method"],
            state["path"],
            utils.Headers.from_state(state["headers"]),
            base64.decodestring(state["content"]),
            state["timestamp"]
        )

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self.get_state() == other.get_state()

    def copy(self):
        c = copy.copy(self)
        c.headers = self.headers.copy()
        return c

    def hostport(self):
        if (self.port, self.scheme) in [(80, "http"), (443, "https")]:
            host = self.host
        else:
            host = "%s:%s"%(self.host, self.port)
        return host

    def url(self):
        return "%s://%s%s"%(self.scheme, self.hostport(), self.path)

    def set_url(self, url):
        parts = parse_url(url)
        if not parts:
            return False
        self.scheme, self.host, self.port, self.path = parts
        return True

    def is_response(self):
        return False

    def short(self):
        return "%s %s"%(self.method, self.url())

    def assemble_proxy(self):
        return self.assemble(True)

    def assemble(self, _proxy = False):
        """
            Assembles the request for transmission to the server. We make some
            modifications to make sure interception works properly.
        """
        headers = self.headers.copy()
        utils.try_del(headers, 'accept-encoding')
        utils.try_del(headers, 'proxy-connection')
        utils.try_del(headers, 'keep-alive')
        utils.try_del(headers, 'connection')
        utils.try_del(headers, 'content-length')
        utils.try_del(headers, 'transfer-encoding')
        if not headers.has_key('host'):
            headers["host"] = [self.hostport()]
        content = self.content
        if content is not None:
            headers["content-length"] = [str(len(content))]
        else:
            content = ""
        if self.close:
            headers["connection"] = ["close"]
        if not _proxy:
            return self.FMT % (self.method, self.path, str(headers), content)
        else:
            return self.FMT_PROXY % (self.method, self.scheme, self.host, self.port, self.path, str(headers), content)


class Response(controller.Msg):
    FMT = '%s\r\n%s\r\n%s'
    def __init__(self, request, code, msg, headers, content, timestamp=None):
        self.request = request
        self.code, self.msg = code, msg
        self.headers, self.content = headers, content
        self.timestamp = timestamp or time.time()
        self.cached = False
        controller.Msg.__init__(self)
        self.replay = False

    def set_replay(self):
        self.replay = True

    def is_replay(self):
        return self.replay

    def load_state(self, state):
        self.code = state["code"]
        self.msg = state["msg"]
        self.headers = utils.Headers.from_state(state["headers"])
        self.content = base64.decodestring(state["content"])
        self.timestamp = state["timestamp"]

    def get_state(self):
        return dict(
            code = self.code,
            msg = self.msg,
            headers = self.headers.get_state(),
            timestamp = self.timestamp,
            content = base64.encodestring(self.content)
        )

    @classmethod
    def from_state(klass, request, state):
        return klass(
            request,
            state["code"],
            state["msg"],
            utils.Headers.from_state(state["headers"]),
            base64.decodestring(state["content"]),
            state["timestamp"],
        )

    def __eq__(self, other):
        return self.get_state() == other.get_state()

    def copy(self):
        c = copy.copy(self)
        c.headers = self.headers.copy()
        return c

    def is_response(self):
        return True

    def is_cached(self):
        return self.cached

    def short(self):
        r = "%s %s"%(self.code, self.msg)
        if self.is_replay():
            r = "[replay] " + r
        return r

    def assemble(self):
        """
            Assembles the response for transmission to the client. We make some
            modifications to make sure interception works properly.
        """
        headers = self.headers.copy()
        utils.try_del(headers, 'accept-encoding')
        utils.try_del(headers, 'proxy-connection')
        utils.try_del(headers, 'connection')
        utils.try_del(headers, 'keep-alive')
        utils.try_del(headers, 'transfer-encoding')
        content = self.content
        if content is not None:
            headers["content-length"] = [str(len(content))]
        else:
            content = ""
        if self.request.client_conn.close:
            headers["connection"] = ["close"]
        proto = "HTTP/1.1 %s %s"%(self.code, str(self.msg))
        data = (proto, str(headers), content)
        return self.FMT%data


class ClientDisconnect(controller.Msg):
    def __init__(self, client_conn):
        controller.Msg.__init__(self)
        self.client_conn = client_conn


class ClientConnect(controller.Msg):
    def __init__(self, address):
        """
            address is an (address, port) tuple, or None if this connection has
            been replayed from within mitmproxy.
        """
        self.address = address
        self.close = False
        controller.Msg.__init__(self)

    def __eq__(self, other):
        return self.get_state() == other.get_state()

    def load_state(self, state):
        self.address = state

    def get_state(self):
        return list(self.address) if self.address else None

    @classmethod
    def from_state(klass, state):
        if state:
            return klass(state)
        else:
            return None

    def copy(self):
        return copy.copy(self)


class Error(controller.Msg):
    def __init__(self, request, msg, timestamp=None):
        self.request, self.msg = request, msg
        self.timestamp = timestamp or time.time()
        controller.Msg.__init__(self)

    def load_state(self, state):
        self.msg = state["msg"]
        self.timestamp = state["timestamp"]

    def copy(self):
        return copy.copy(self)

    def get_state(self):
        return dict(
            msg = self.msg,
            timestamp = self.timestamp,
        )

    @classmethod
    def from_state(klass, state):
        return klass(
            None,
            state["msg"],
            state["timestamp"],
        )

    def __eq__(self, other):
        return self.get_state() == other.get_state()


class FileLike:
    def __init__(self, o):
        self.o = o

    def __getattr__(self, attr):
        return getattr(self.o, attr)

    def flush(self):
        pass

    def read(self, length):
        result = ''
        while len(result) < length:
            data = self.o.read(length)
            if not data:
                break
            result += data
        return result

    def readline(self):
        result = ''
        while True:
            ch = self.read(1)
            if not ch:
                break
            else:
                result += ch
                if ch == '\n':
                    break
        return result


#begin nocover

class ServerConnection:
    def __init__(self, request):
        self.host = request.host
        self.port = request.port
        self.scheme = request.scheme
        self.close = False
        self.server, self.rfile, self.wfile = None, None, None
        self.connect()

    def connect(self):
        try:
            addr = socket.gethostbyname(self.host)
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.scheme == "https":
                server = ssl.wrap_socket(server)
            server.connect((addr, self.port))
        except socket.error, err:
            raise ProxyError(504, 'Error connecting to "%s": %s' % (self.host, err))
        self.server = server
        self.rfile, self.wfile = server.makefile('rb'), server.makefile('wb')

    def send_request(self, request):
        self.request = request
        request.close = self.close
        try:
            self.wfile.write(request.assemble())
            self.wfile.flush()
        except socket.error, err:
            raise ProxyError(504, 'Error sending data to "%s": %s' % (request.host, err))

    def read_response(self):
        line = self.rfile.readline()
        if line == "\r\n" or line == "\n": # Possible leftover from previous message
            line = self.rfile.readline()
        if not line:
            raise ProxyError(502, "Blank server response.")
        parts = line.strip().split(" ", 2)
        if not len(parts) == 3:
            raise ProxyError(502, "Invalid server response: %s."%line)
        proto, code, msg = parts
        code = int(code)
        headers = utils.Headers()
        headers.read(self.rfile)
        if code >= 100 and code <= 199:
            return self.read_response()
        if self.request.method == "HEAD" or code == 204 or code == 304:
            content = ""
        else:
            content = read_http_body(self.rfile, self, headers, True)
        return Response(self.request, code, msg, headers, content)

    def terminate(self):
        try:
            if not self.wfile.closed:
                self.wfile.flush()
            self.server.close()
        except IOError:
            pass


class ProxyHandler(SocketServer.StreamRequestHandler):
    def __init__(self, config, request, client_address, server, q):
        self.config = config
        self.mqueue = q
        SocketServer.StreamRequestHandler.__init__(self, request, client_address, server)

    def handle(self):
        cc = ClientConnect(self.client_address)
        cc.send(self.mqueue)
        while not cc.close:
            self.handle_request(cc)
        cd = ClientDisconnect(cc)
        cd.send(self.mqueue)
        self.finish()

    def handle_request(self, cc):
        server, request = None, None
        try:
            request = self.read_request(cc)
            if request is None:
                cc.close = True
                return
            request = request.send(self.mqueue)
            if request is None:
                cc.close = True
                return

            if request.is_response():
                response = request
                request = False
                response = response.send(self.mqueue)
            else:
                server = ServerConnection(request)
                server.send_request(request)
                response = server.read_response()
                response = response.send(self.mqueue)
                if response is None:
                    server.terminate()
            if response is None:
                cc.close = True
                return
            self.send_response(response)
        except IOError:
            pass
        except ProxyError, e:
            err = Error(request, e.msg)
            err.send(self.mqueue)
            cc.close = True
            self.send_error(e.code, e.msg)
        if server:
            server.terminate()

    def find_cert(self, host):
        if self.config.certfile:
            return self.config.certfile
        else:
            ret = utils.dummy_cert(self.config.certdir, self.config.cacert, host)
            if not ret:
                raise ProxyError(400, "mitmproxy: Unable to generate dummy cert.")
            return ret

    def read_request(self, client_conn):
        line = self.rfile.readline()
        if line == "\r\n" or line == "\n": # Possible leftover from previous message
            line = self.rfile.readline()
        if line == "":
            return None
        method, scheme, host, port, path, httpminor = parse_request_line(line)
        if method == "CONNECT":
            # Discard additional headers sent to the proxy. Should I expose
            # these to users?
            while 1:
                d = self.rfile.readline()
                if d == '\r\n' or d == '\n':
                    break
            self.wfile.write(
                        'HTTP/1.1 200 Connection established\r\n' +
                        ('Proxy-agent: %s\r\n'%NAME) +
                        '\r\n'
                        )
            self.wfile.flush()
            kwargs = dict(
                certfile = self.find_cert(host),
                keyfile = self.config.certfile or self.config.cacert,
                server_side = True,
                ssl_version = ssl.PROTOCOL_SSLv23,
                do_handshake_on_connect = False
            )
            if sys.version_info[1] > 6:
                kwargs["ciphers"] = self.config.ciphers
            self.connection = ssl.wrap_socket(self.connection, **kwargs)
            self.rfile = FileLike(self.connection)
            self.wfile = FileLike(self.connection)
            method, scheme, host, port, path, httpminor = parse_request_line(self.rfile.readline())
        if scheme is None:
            scheme = "https"
        headers = utils.Headers()
        headers.read(self.rfile)
        if host is None and headers.has_key("host"):
            netloc = headers["host"][0]
            if ':' in netloc:
                host, port = string.split(netloc, ':')
                port = int(port)
            else:
                host = netloc
                if scheme == "https":
                    port = 443
                else:
                    port = 80
            port = int(port)
        if host is None:
            raise ProxyError(400, 'Invalid request: %s'%request)
        if headers.has_key('expect'):
            expect = ",".join(headers['expect'])
            if expect == "100-continue" and httpminor >= 1:
                self.wfile.write('HTTP/1.1 100 Continue\r\n')
                self.wfile.write('Proxy-agent: %s\r\n'%NAME)
                self.wfile.write('\r\n')
                del headers['expect']
            else:
                raise ProxyError(417, 'Unmet expect: %s'%expect)
        if httpminor == 0:
            client_conn.close = True
        if headers.has_key('connection'):
            for value in ",".join(headers['connection']).split(","):
                value = value.strip()
                if value == "close":
                    client_conn.close = True
                if value == "keep-alive":
                    client_conn.close = False
        content = read_http_body(self.rfile, client_conn, headers, False)
        return Request(client_conn, host, port, scheme, method, path, headers, content)

    def send_response(self, response):
        self.wfile.write(response.assemble())
        self.wfile.flush()

    def terminate(self, connection, wfile, rfile):
        self.request.close()
        try:
            if not getattr(wfile, "closed", False):
                wfile.flush()
            connection.close()
        except IOError:
            pass

    def finish(self):
        self.terminate(self.connection, self.wfile, self.rfile)

    def send_error(self, code, body):
        try:
            import BaseHTTPServer
            response = BaseHTTPServer.BaseHTTPRequestHandler.responses[code][0]
            self.wfile.write("HTTP/1.1 %s %s\r\n" % (code, response))
            self.wfile.write("Server: %s\r\n"%NAME)
            self.wfile.write("Connection: close\r\n")
            self.wfile.write("Content-type: text/html\r\n")
            self.wfile.write("\r\n")
            self.wfile.write('<html><head>\n<title>%d %s</title>\n</head>\n'
                    '<body>\n%s\n</body>\n</html>' % (code, response, body))
            self.wfile.flush()
        except IOError:
            pass


ServerBase = SocketServer.ThreadingTCPServer
ServerBase.daemon_threads = True        # Terminate workers when main thread terminates
class ProxyServer(ServerBase):
    request_queue_size = 20
    allow_reuse_address = True
    def __init__(self, config, port, address=''):
        self.config, self.port, self.address = config, port, address
        ServerBase.__init__(self, (address, port), ProxyHandler)
        self.masterq = None
        self.certdir = tempfile.mkdtemp(prefix="mitmproxy")
        config.certdir = self.certdir

    def set_mqueue(self, q):
        self.masterq = q

    def finish_request(self, request, client_address):
        self.RequestHandlerClass(self.config, request, client_address, self, self.masterq)

    def shutdown(self):
        shutil.rmtree(self.certdir)
        ServerBase.shutdown(self)


# Command-line utils
def certificate_option_group(parser):
    group = optparse.OptionGroup(parser, "SSL")
    group.add_option(
        "--cert", action="store",
        type = "str", dest="cert", default=None,
        help = "User-created SSL certificate file."
    )
    group.add_option(
        "--cacert", action="store",
        type = "str", dest="cacert", default="~/.mitmproxy/ca.pem",
        help = "SSL CA certificate file. Generated if it doesn't exist."
    )
    group.add_option(
        "--ciphers", action="store",
        type = "str", dest="ciphers", default=None,
        help = "SSL ciphers."
    )
    parser.add_option_group(group)


def process_certificate_option_group(parser, options):
    conf = {}
    if options.cert:
        options.cert = os.path.expanduser(options.cert)
        if not os.path.exists(options.cert):
            parser.error("Manually created certificate does not exist: %s"%options.cert)
    if options.cacert:
        options.cacert = os.path.expanduser(options.cacert)
        if not os.path.exists(options.cacert):
            utils.dummy_ca(options.cacert)
    if getattr(options, "cache", None) is not None:
        options.cache = os.path.expanduser(options.cache)
    return Config(
        certfile = options.cert,
        cacert = options.cacert,
        ciphers = options.ciphers
    )
