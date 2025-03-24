# coding: utf8
'''A transport abstracts a transport layer, which may be multichannel.

For details, see doc of class Transport.

Classes defined here:
 * Transport: abstract base
 * StdioTransport: reads from stdin, writes to stdout.
 * MuxTransport: a transport that multiplexes several sub-transports.
 * RestartingTransport: a transport that automatically restarts its child.
 * RestartingTcpClientTransport: convenience class
 * TcpServerTransport: a transport that accepts tcp connections and muxes 
    them into one transport. Actually a forward to quickrpc.network_transports.
 * TcpClientTransport: connects to a TCP server. This is a forward to 
    quickrpc.network_transports.

'''

__all__ = [
    'Transport',
    'StdioTransport',
    'MuxTransport',
    'RestartingTransport',
    'RestartingTcpClientTransport',
    'TcpServerTransport',
    'TcpClientTransport',
]

from collections import namedtuple
import logging
import queue
import sys
import select
import threading
import time
from .util import subclasses, paren_partition
from .promise import Promise, PromiseDoneError

L = lambda: logging.getLogger(__name__)

class TransportException(Exception):
    '''generic error in a transport'''


class Transport(object):
    ''' abstracts a transport layer, which may be multichannel.
    
    Outgoing messages are sent via .send(). (Override!)
    Incoming messages are passed to a callback.
    The callback must be set before the first message arrives via set_on_received().
    
    There are some facilities in place for threaded transports:
    - .run() shall run the transport (possibly blocking)
    - .start() shall start the transport nonblocking
    - .stop() shall stop the transport gracefully
    - Event .running for state and signaling 
        (default .stop() sets running to False).
        
    - .set_on_received is used to set the handler for received data. 
        Signature: ``on_received(sender, data)``, where sender is a
        string describing the origin; data is the received bytes.
        The function returns leftover bytes (if any), that will be
        prepended to the next on_received call.
        
    '''
    # The shorthand to use for string creation.
    shorthand = ''

    def __init__(self):
        self._on_received = None
        self.running = False
        # This lock guards calls to .start() and .stop().
        # E.g. someone might try to stop while we are still starting.
        self._transition_lock = threading.Lock()
        
    @classmethod
    def fromstring(cls, expression):
        '''Creates a transport from a given string expression.

        The expression must be "<shorthand>:<specific parameters>",
        with shorthand being the wanted transport's .shorthand property.
        For the specific parameters, see the respective transport's .fromstring
        method.
        '''
        shorthand, _, expr = expression.partition(':')
        for subclass in subclasses(cls):
            if subclass.shorthand == shorthand:
                return subclass.fromstring(expression)
        raise ValueError('Could not find a transport class with shorthand %s'%shorthand)

    def open(self):
        '''open the communication channel. Override me if required.
        
        When open() exits, the communication line should be ready for send and receive.
        '''
        
    def run(self):
        '''Runs the transport, possibly blocking. Override me.'''
        self.running = True
        
    
    def start(self, block=True):
        '''Run in a new thread.
        
        If block is True, waits until startup is complete, then returns True.
        Otherwise, returns a promise.
        
        If something goes wrong during start, the Exception, like e.g. a 
        socket.error, is passed through.
        '''
        p = Promise()
        
        def starter():
            with self._transition_lock:
                try:
                    self.open()
                except Exception as e:
                    p.set_exception(e)
                    return
                else:
                    p.set_result(True)
            self.run()
                
        self._thread = threading.Thread(target=starter, name=self.__class__.__name__)
        self._thread.start()
        return p.result() if block else p
    
    
    def stop(self, block=True):
        '''Stop running transport (possibly from another thread).'''
        with self._transition_lock:
            self.running = False
            thread = None
            try:
                thread = self._thread
            except AttributeError:
                # run() might have been called explicitly.
                pass
            else:
                # If cross-thread stop, wait until actually stopped.
                if block and thread is not threading.current_thread():
                    self._thread.join()
    
    def set_on_received(self, on_received):
        '''sets the function to call upon receiving data.'''
        self._on_received = on_received
        
    def send(self, data, receivers=None):
        '''sends the given data to the specified receiver(s).
        
        receivers=None means send to all.
        '''
        raise NotImplementedError("Override me")
    
    def received(self, sender, data):
        '''to be called when the subclass received data.
        For multichannel transports, sender is a unique id identifying the source.
        
        If the given data has an undecodable "tail", it is returned.
        In this case you should prepend the tail to the next received bytes from this channel,
        because it is probably an incomplete message.
        '''
        if not self._on_received:
            raise AttributeError("Transport received a message but has no handler set.")
        return self._on_received(sender, data)


class StdioTransport(Transport):
    shorthand = 'stdio'
    @classmethod
    def fromstring(cls, expression):
        '''No configuration options, just use "stdio:".'''
        return cls()

    def stop(self):
        L().debug('StdioTransport.stop() called')
        Transport.stop(self)

    def send(self, data, receivers=None):
        if receivers is not None and 'stdio' not in receivers:
            return
        L().debug('StdioTransport.send %r'%data)
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    def run(self):
        '''run, blocking.'''
        L().debug('StdioTransport.run() called')
        self.running = True
        leftover = b''
        while self.running:
            # FIXME: This loses bytes on startup.
            data = self._input()
            #data = input().encode('utf8') + b'\n'
            if data is None: 
                continue
            L().debug("received: %r"%data)
            leftover = self.received(sender='stdio', data=leftover + data)
        L().debug('StdioTransport has finished')
            
    def _input(self, timeout=0.1):
        '''Input with 0.1s timeout. Return None on timeout.'''
        i, o, e = select.select([sys.stdin.buffer], [], [], timeout)
        if i:
            return sys.stdin.buffer.read1(65536)
        else:
            return None


InData = namedtuple('InData', 'sender data')

class MuxTransport(Transport):
    '''A transport that muxes several transports.
    
    Incoming data is serialized into the thread of MuxTransport.run().
    
    Add Transports via mux_transport += transport.
    Remove via mux_transport -= transport.
    
    Adding a transport changes its on_received binding to the mux transport.
    If MuxTransport is already running, the added transport is start()ed by default.
    
    Removing a transport stop()s it by default.
    
    Running/Stopping the MuxTransport also runs/stops all muxed transports.
    '''
    shorthand='mux'
    @classmethod
    def fromstring(cls, expression):
        '''mux:(<transport1>)(<transport2>)...
        
        where <transport1>, .. are again valid transport expressions.
        '''
        _, _, params = expression.partition(':')
        t = cls()
        while params != '':
            expr, _, params = paren_partition(params)
            t.add_transport(Transport.fromstring(expr))
        return t
        
    
    def __init__(self):
        Transport.__init__(self)
        self.in_queue = queue.Queue()
        self.transports = []
        self.running = False
        # sender --> leftover bytes
        self.leftovers = {}
        
    def send(self, data, receivers=None):
        # Let everyone decide for himself.
        for transport in self.transports:
            transport.send(data, receivers=receivers)
        
    def handle_received(self, sender, data):
        '''handles INCOMING data from any of the muxed transports.
        b'' is returned as leftover ALWAYS; MuxTransport keeps
        internal remainder buffers for all senders, since the
        leftover is only available after the message was processed.
        '''
        self.in_queue.put(InData(sender, data))
        return b''
    
    def add_transport(self, transport, start=True):
        '''add and start the transport (if running).'''
        self.transports.append(transport)
        transport.set_on_received(self.handle_received)
        if start and self.running:
            transport.start()
        return self
        
    def remove_transport(self, transport, stop=True):
        '''remove and stop the transport.'''
        self.transports.remove(transport)
        transport.set_on_received(None)
        if stop:
            transport.stop()
        return self
        
    __iadd__ = add_transport
    __isub__ = remove_transport
    
    def stop(self):
        L().debug('MuxTransport.stop() called')
        Transport.stop(self)
    
    def open(self):
        '''Start all transports that were added so far.
        
        The subtransports are started in parallel, then we wait until all of 
        them are up.
        
        If any transport fails to start, all transports are stopped again,
        and TransportError is raised. It will have a .exceptions attribute being
        a list of all failures.
        '''
        
        L().debug('MuxTransport.run() called')
        promises = []
        exceptions = []
        running = []
        for transport in self.transports:
            promises.append(transport.start(block=False))
        # wait on all the promises
        for transport, promise in zip(self.transports, promises):
            try:
                if promise.result():
                    running.append(transport)
            except Exception as e:
                exceptions.append(e)
        if exceptions:
            # Oh my. Stop everything again.
            L().error('Some transports failed to start. Aborting.')
            for transport in running:
                transport.stop()
            e = TransportException()
            e.exceptions = exceptions
            raise e
        
        L().debug('Thread overview: %s'%([t.name for t in threading.enumerate()],))
        
    def run(self):
        self.running = True
        while self.running:
            try:
                indata = self.in_queue.get(timeout=0.5)
            except queue.Empty:
                # timeout passed, check self.running and try again.
                continue
            L().debug('MuxTransport: received %r'%(indata,))
            leftover = self.leftovers.get(indata.sender, b'')
            leftover = self.received(indata.sender, leftover + indata.data)
            self.leftovers[indata.sender] = leftover
            
        # stop all transports
        for transport in self.transports:
            transport.stop()
        L().debug('MuxTransport has finished')
            

class RestartingTransport(Transport):
    '''A transport that wraps another transport and keeps restarting it.

    E.g. you can wrap a TcpClientTransport to try reconnecting it.
    >>> tr = RestartingTransport(TcpClientTransport(*address), check_interval=10)

    check_interval gives the Restart interval in seconds. It may not be kept exactly.
    It cannot be lower than 1 second. Restarting is attempted as long as the transport is running.
    
    Adding a transport changes its on_received handler to the RestartingTransport.
    '''
    shorthand='restart'
    @classmethod
    def fromstring(cls, expression):
        '''restart:10:<subtransport>

        10 (seconds) is the restart interval.

        <subtransport> is any valid transport string.
        '''
        _, _, expr = expression.partition(':')
        interval, _, expr = expr.partition(':')
        return cls(
                transport=Transport.fromstring(expr),
                check_interval=10,
                name=expression
                )

    def __init__(self, transport, check_interval=10, name=''):
        self.check_interval = check_interval
        self.transport = transport
        self.transport.set_on_received(self.received)
        self._poll_interval = 1
        self.name = name

    def stop(self):
        # First stop self!
        Transport.stop(self)
        
    def _try_start(self):
        try:
            self.transport.start()
        except Exception as e:
            L().info('RestartingTransport: inner transport could not be started.')
            
        
    def open(self):
        self._try_start()

    def run(self):
        self.running = True
        restart_timer = self.check_interval
        while self.running:
            time.sleep(self._poll_interval)
            if not self.transport.running:
                restart_timer -= self._poll_interval
                if restart_timer <= 0:
                    L().info("trying to restart (%s)"%self.name)
                    self._try_start()
                    restart_timer = self.check_interval
        self.transport.stop()

    def send(self, data, receivers):
        if self.transport.running:
            self.transport.send(data, receivers)
        else:
            raise IOError('Transport %s is not running, cannot send message'%(self.name,))

def RestartingTcpClientTransport(host, port, check_interval=10):
    '''Convenience wrapper for the most common use case. Returns TcpClientTransport wrapped in a RestartingTransport.'''
    t = TcpClientTransport(host, port)
    return RestartingTransport(t, check_interval=check_interval, name=t.name)

def TcpServerTransport(port, interface='', announcer=None):
    from .network_transports import TcpServerTransport
    return TcpServerTransport(port, interface, announcer)

def TcpClientTransport(host, port):
    from .network_transports import TcpClientTransport
    return TcpClientTransport(host, port)
