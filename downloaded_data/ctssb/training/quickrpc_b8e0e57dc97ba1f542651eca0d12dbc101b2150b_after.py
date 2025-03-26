__all__ = ['UdpTransport', 'TcpServerTransport']

import logging

import socket as sk
from socketserver import ThreadingTCPServer, BaseRequestHandler
from threading import Thread, Event
from .transports import Transport, MuxTransport

L = lambda: logging.getLogger(__name__)

class UdpTransport(Transport):
    '''transport that communicates over UDP datagrams.
    
    Connectionless - sender/receiver are IP addresses. Sending and receiving is 
    done on the same port. Sending with receiver=None makes a broadcast.
    
    Use messages > 500 Bytes at your own peril.
    '''
    def __init__(self, port):
        Transport.__init__(self)
        self.port = port
        self.socket = sk.socket(sk.AF_INET, sk.SOCK_DGRAM)
        self.socket.settimeout(0.5)
        self.socket.setsockopt(sk.SOL_SOCKET, sk.SO_BROADCAST, 1)
        self.socket.setsockopt(sk.SOL_SOCKET, sk.SO_REUSEADDR, 1)
        self.socket.setsockopt(sk.SOL_SOCKET, sk.IP_MULTICAST_LOOP, 1)
        try:
            self.socket.setsockopt(sk.SOL_SOCKET, sk.SO_REUSEPORT, 1)
        except AttributeError:
            # SO_REUSEPORT not available.
            pass
        
    def run(self):
        self.socket.bind(('', self.port))
        self.running = True
        while self.running:
            try:
                data, addr = self.socket.recvfrom(2048)
            except sk.timeout:
                continue
            host, port = addr
            # not using leftover data  here, since udp packets are
            # not guaranteed to arrive in order.
            L().debug('message from udp %s: %s'%(host, data))
            self.received(data=data, sender=host)
        self.socket.close()
    
    def send(self, data, receivers=None):
        L().debug('message to udp %r: %s'%(receivers, data))
        if receivers:
            for receiver in receivers:
                self.socket.sendto(data, (receiver, self.port))
        else:
            self.socket.sendto(data, ('<broadcast>', self.port))
        

class TcpServerTransport(MuxTransport):
    '''transport that accepts TCP connections as transports.
    
    Basically a mux transport coupled with a TcpServer. Each time somebody
    connects, the connection is wrapped into a transport and added to the
    muxer.
    
    There is (for now) no explicit notification about connects/disconnects;
    use the API for that.
    
    Use .close() for server-side disconnect.
    
    You can optionally pass an announcer (as returned by announcer_api.make_udp_announcer).
    It will be started/stopped together with the TcpServerTransport.
    
    Threads:
     - TcpServerTransport.run() blocks (use .start() for automatic extra Thread)
     - .run() starts a new thread for listening to connections
     - each incoming connection will start another Thread.
    '''
    def __init__(self, port, interface='', announcer=None):
        self.addr = (interface, port)
        self.announcer = announcer
        MuxTransport.__init__(self)
        
    def run(self):
        server = ThreadingTCPServer(self.addr, _TcpConnection, bind_and_activate=True)
        server.mux = self
        Thread(target=server.serve_forever, name="TcpServerTransport_Listen").start()
        if self.announcer:
            self.announcer.transport.start()
        
        MuxTransport.run(self)
        
        if self.announcer:
            self.announcer.transport.stop()
        
        server.shutdown()
        
    def close(self, name):
        '''close the connection with the given sender/receiver name.
        '''
        for transport in self.transports:
            if transport.name == name:
                transport.transport_running.clear()
                                    
                                    
class _TcpConnection(BaseRequestHandler, Transport):
    '''Bridge between TcpServer (BaseRequestHandler) and Transport.
    
    Implicitly created by the TcpServer. .handle() waits until
    Transport.start() is called, and closes the connection and
    exits upon call of .stop().
    
    The Transport also stops upon client-side close of connection.
    
    The _TcpConnection registers and unregisters itself with the TcpServerTransport.
    '''
    
    # BaseRequestHandler overrides
    def __init__(self, request, client_address, server):
        BaseRequestHandler.__init__(self, request, client_address, server)
        #Transport.__init__(self)
        self._api = None

    @property
    def running(self):
        return self.transport_running.is_set()
        
    def setup(self):
        self.name = '%s:%s'%self.client_address
        L().debug('TCP connect from %s'%self.name)
        
        self.request.settimeout(0.5)
        self.transport_running = Event()
        # add myself to the muxer, which will .start() me.
        self.server.mux.add_transport(self)
        
    def handle(self):
        self.transport_running.wait()
        leftover = b''
        while self.transport_running.is_set():
            try:
                data = self.request.recv(1024)
            except sk.timeout:
                continue
            data = data.replace(b'\r\n', b'\n')
            if data == b'':
                # Connection was closed.
                self.stop()
                break
            L().debug('data from %s: %r'%(self.name, data))
            leftover = self.received(sender=self.name, data=leftover+data)
        
    def finish(self):
        L().debug('Closed TCP connection to %s'%self.name)
        # Getting here implies that this transport already stopped.
        self.server.mux.remove_transport(self, stop=False)
    
    # Transport overrides
    def start(self):
        self.transport_running.set()
        
    def run(self):
        # _TcpConnection starts "running" by itself (since the connection is already opened by definition).
        raise Exception('You shall not use .run()')
        
    def stop(self):
        self.transport_running.clear()
        
    def send(self, data, receivers=None):
        if not self.transport_running.is_set():
            raise IOError('Tried to send over non-running transport!')
        if receivers is not None and not self.name in receivers:
            return
        # FIXME: do something on failure
        self.request.sendall(data)