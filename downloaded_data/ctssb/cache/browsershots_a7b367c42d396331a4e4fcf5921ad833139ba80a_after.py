#! /usr/bin/env python
# throxy.py - HTTP proxy to simulate dial-up access
# Copyright (C) 2007 Johann C. Rocholl <johann@rocholl.net>
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Throxy (Throttling Proxy)

This is a simple HTTP proxy, with the following features:

* Simulates a slow connection (like dial-up).
* Optionally dumps HTTP headers and content for debugging.
* Supports multiple connections, without threading.
* Written in pure Python.

To use it, run this script on your local machine and adjust your
browser settings to use 127.0.0.1:8080 as HTTP proxy.
"""

import sys
import asyncore
import socket
import time
import re

__revision__ = '$Rev$'

KILO = 1000 # decimal or binary kilo
MIN_FRAGMENT_SIZE = 512 # bytes

request_match = re.compile(r'^([A-Z]+) (\S+) (HTTP/\S+)$').match


class BandwidthMonitor:

    def __init__(self,
                 receive_bytes_per_second=3600,
                 send_bytes_per_second=3600,
                 interval=1.0):
        self.recv_bps = receive_bytes_per_second
        self.send_bps = send_bytes_per_second
        self.interval = interval
        self.recv_log = []
        self.send_log = []

    def log_received_bytes(self, bytes):
        self.recv_log.append((time.time(), bytes))

    def log_sent_bytes(self, bytes):
        self.send_log.append((time.time(), bytes))

    def trim_log(self, log, horizon):
        while len(log) and log[0][0] <= horizon:
            log.pop(0)

    def weighted_bytes(self, log):
        """Compute recent bandwidth usage, in bytes per second."""
        now = time.time()
        self.trim_log(log, now - self.interval)
        if len(log) == 0:
            return 0
        weighted = 0.0
        for timestamp, bytes in log:
            age = now - timestamp # event's age in seconds
            assert 0 <= age <= self.interval
            weight = 2.0 * (self.interval - age) / self.interval
            assert 0.0 <= weight <= 2.0
            weighted += weight * bytes # newer entries count more
        return int(weighted / self.interval)

    def sendable(self):
        """How many bytes can we send without exceeding bandwidth?"""
        return max(0, self.send_bps - self.weighted_bytes(self.send_log))

    def receivable(self):
        """How many bytes can we receive without exceeding bandwidth?"""
        return max(0, self.recv_bps - self.weighted_bytes(self.recv_log))

    def weighted_kbps(self, log):
        """Compute bandwidth usage, in kbps."""
        return 8 * self.weighted_bytes(log) / float(KILO)

    def receiving_kpbs(self):
        """Compute download bandwidth usage, in kbps."""
        return self.weighted_kbps(self.recv_log)

    def sending_kpbs(self):
        """Compute upload bandwidth usage, in kbps."""
        return self.weighted_kbps(self.send_log)


class ProxyServer(asyncore.dispatcher):

    def __init__(self):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bind((options.interface, options.port))
        self.listen(5)
        print >> sys.stderr, "listening on port", options.port

    def handle_accept(self):
        channel, addr = self.accept()
        if addr[0] == '127.0.0.1' or options.allow_remote:
            ClientChannel(channel, addr)
        else:
            channel.close()
            print >> sys.stderr, "remote client %s:%d not allowed" % addr


class Message:

    def __init__(self):
        self.headers = []
        self.data = ''
        self.headers_complete = False
        self.complete = False

    def extract_header(self, name, default=None):
        name = name.lower()
        for line in headers:
            key, value = line.split(':', 1)
            if key.lower() == name:
                return value.strip()
        return default
        self.handle_input()

    def append(self, data):
        self.data += data
        while not self.headers_complete:
            newline = self.data.find('\n')
            if newline < 0:
                break # no complete line found
            line = self.data[:newline]
            if len(line) and line[-1] == '\r':
                line = line[:-1]
            if len(line):
                self.headers.append(line)
            else:
                self.headers_complete = True
                self.content_length = int(
                    self.extract_header('Content-Length', 0))
            self.data = self.data[newline+2:]
        if self.headers_complete:
            self.complete = len(data) == self.content_length


class ClientChannel(asyncore.dispatcher):

    def __init__(self, channel, addr):
        asyncore.dispatcher.__init__(self, channel)
        self.addr = addr
        self.message = Message()
        self.buffer = []
        if not options.quiet:
            print >> sys.stderr, "client %s:%d connected" % self.addr

    def readable(self):
        return monitor.receivable() / 2 > MIN_FRAGMENT_SIZE

    def handle_read(self):
        max_bytes = max(8192, monitor.receivable() / 2)
        if max_bytes < MIN_FRAGMENT_SIZE:
            return
        # print "receivable", max_bytes
        data = self.recv(max_bytes)
        if not len(data):
            return
        monitor.log_received_bytes(len(data))
        self.message.append(data)
        if self.message.headers_complete:
            for line in self.message.headers:
                print repr(line)
            print repr(self.message.data)

    def writable(self):
        return len(self.buffer) and \
               monitor.sendable() / 2 > MIN_FRAGMENT_SIZE

    def handle_write(self):
        max_bytes = monitor.sendable() / 2
        if max_bytes < MIN_FRAGMENT_SIZE:
            return
        # print "sendable", max_bytes
        bytes = self.send(self.buffer[0][:max_bytes])
        monitor.log_sent_bytes(bytes)
        if bytes == len(self.buffer[0]):
            self.buffer.pop(0)
        else:
            self.buffer[0] = self.buffer[0][bytes:]

    def handle_close(self):
        self.close()
        if not options.quiet:
            print >> sys.stderr, "client %s:%d disconnected" % self.addr


class ServerChannel(asyncore.dispatcher):

    def __init__(self, client, request):
        asyncore.dispatcher.__init__(self)
        self.client = client
        self.extract_host(request)
        self.extract_path(request)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect(self.addr)
        self.buffer = []
        self.send_request(request)

    def extract_host(self, request):
        self.host = extract_header(request, 'Host')
        if not self.host:
            raise ValueError("host header missing")
        # print "client %s:%d wants to talk to" % self.client.addr, self.host
        if self.host.count(':'):
            self.host_name, self.host_port = self.host.split(':')
        else:
            self.host_name = self.host
            self.host_port = 80
        self.host_ip = socket.gethostbyname(self.host_name)
        self.addr = (self.host_ip, self.host_port)

    def extract_path(self, request):
        match = request_match(request[0])
        if not match:
            raise ValueError("invalid request " + request[0])
        self.method, self.url, self.proto = match.groups()
        if self.method.upper() == 'CONNECT':
            raise ValueError("method CONNECT is not supported")
        prefix = 'http://' + self.host
        if not self.url.startswith(prefix):
            raise ValueError("URL doesn't start with " + prefix)
        self.path = self.url[len(prefix):]

    def send_request(self, request):
        if options.dump_send_headers:
             print '==== sending header to server %s:%d ====' % self.addr
        self.send_line(' '.join((self.method, self.path, self.proto)))
        self.send_line('Host: ' + self.host)
        self.send_line('Connection: close')
        for line in request[1:]:
            if line.startswith('Host: '):
                pass
            elif line.startswith('Keep-Alive: '):
                pass
            elif line.startswith('Connection: '):
                pass
            elif line.startswith('Proxy-'):
                pass
            else:
                self.send_line(line)
        self.send_line('')

    def send_line(self, line):
        if options.dump_send_headers:
            print line
        self.buffer.append(line + '\r\n')

    def writable(self):
        return len(self.buffer)

    def handle_write(self):
        bytes = self.send(self.buffer[0])
        if bytes == len(self.buffer[0]):
            # print "sent", repr(self.buffer[0])
            self.buffer.pop(0)
        else:
            # print "sent", repr(self.buffer[0][:bytes])
            self.buffer[0] = self.buffer[0][bytes:]

    def handle_read(self):
        data = self.recv(8192)
        # print "received", repr(data)
        self.client.buffer.append(data)

    def handle_connect(self):
        if not options.quiet:
            print >> sys.stderr, "server %s:%d connected" % self.addr

    def handle_close(self):
        self.client.should_close = True
        self.close()
        if not options.quiet:
            print >> sys.stderr, "server %s:%d disconnected" % self.addr


if __name__ == '__main__':
    from optparse import OptionParser
    version = '%prog ' + __revision__.strip('$').replace('Rev: ', 'r')
    parser = OptionParser(version=version)
    parser.add_option('-i', dest='interface', action='store', type='string',
                      metavar='<ip>', default='',
                      help="listen on this interface only (default all)")
    parser.add_option('-p', dest='port', action='store', type='int',
                      metavar='<port>', default=8080,
                      help="listen on this port number (default 8080)")
    parser.add_option('-d', dest='download', action='store', type='float',
                      metavar='<kbps>', default=28.8,
                      help="download bandwidth in kbps (default 28.8)")
    parser.add_option('-u', dest='upload', action='store', type='float',
                      metavar='<kbps>', default=28.8,
                      help="upload bandwidth in kbps (default 28.8)")
    parser.add_option('-o', dest='allow_remote', action='store_true',
                      help="allow remote clients (WARNING: open proxy)")
    parser.add_option('-q', dest='quiet', action='store_true',
                      help="don't show connect and disconnect messages")
    parser.add_option('-s', dest='dump_send_headers', action='store_true',
                      help="dump headers sent to server")
    parser.add_option('-r', dest='dump_recv_headers', action='store_true',
                      help="dump headers received from server")
    parser.add_option('-S', dest='dump_send_data', action='store_true',
                      help="dump data sent to server")
    parser.add_option('-R', dest='dump_recv_data', action='store_true',
                      help="dump data received from server")
    options, args = parser.parse_args()
    monitor = BandwidthMonitor(
        int(options.upload * KILO) / 8,
        int(options.download * KILO) / 8)
    proxy = ProxyServer()
    try:
        asyncore.loop(timeout=0.1)
    except:
        proxy.shutdown(2)
        proxy.close()
        raise
