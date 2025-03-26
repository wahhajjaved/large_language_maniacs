import logging
import traceback
from collections import defaultdict

from BridgePython import util, connection, reference, serializer, client

'''
@package bridge
A Python API for bridge clients.
'''


class Bridge(object):
    '''Interface to the Bridge server.'''

    def __init__(self, **kwargs):
        '''Initialize Bridge.

        @param kwargs: Specify optional config information.
        @keyword api_key: Bridge cloud api key. No default.
        @keyword log: Specifies a log level. Defaults to logging.WARNING.
        @keyword redirector: Bridge redirector. Defaults to
        http://redirector.getbridge.com.
        @keyword host: Bridge host. No default. Set a value to disable
        redirector based connect.
        @keyword port: Bridge port. No default. Set a value to disable
        redirector based connect.
        @keyword reconnect: Defaults to True to enable reconnects.
        '''
        # Set configuration options
        self._options = {}
        self._options['api_key'] = kwargs.get('api_key')
        self._options['log'] = kwargs.get('log', logging.WARNING)
        self._options['redirector'] = kwargs.get('redirector', 'http://redirector.getbridge.com')
        self._options['secure_redirector'] = kwargs.get('secure_redirector',
                'https://redirector.getbridge.com')
        self._options['host'] = kwargs.get('host')
        self._options['port'] = kwargs.get('port')
        self._options['reconnect'] = kwargs.get('reconnect', True)
        self._options['secure'] = kwargs.get('secure', False)

        if(self._options['secure']):
            self._options['redirector'] = self._options['secure_redirector']

        util.set_log_level(self._options['log'])

        # Initialize system service call
        self._store = {
            'system': _SystemService(self)
        }

        # Indicates whether server is connected and handshaken
        self._ready = False

        # Create connection object
        self._connection = connection.Connection(self)

        # Store event handlers
        self._events = defaultdict(list)

        self._context = None;

    def on(self, name, func):
        '''Registers a callback for the specified event.

        Event names and arity
        ready/0
        disconnect/0
        reconnect/0
        remote_error/1 (msg)

        @param name: The name of the event.
        @param func: Called when this event is emitted.
        '''
        self._events[name].append(func)

    def emit(self, name, *args):
        '''Triggers an event.

        @param name: The name of the event to trigger.
        @param args: A list of arguments to the event callback.
        '''
        if name in self._events:
            for func in self._events[name]:
                func(*args)

    def clear_event(self, name):
        '''Removes the callbacks for the given event.

        @param name: Name of an event.
        '''
        self._events[name] = []

    def publish_service(self, name, handler, callback=None):
        '''Publish a service to Bridge.

        @param name: The name of the service.
        @param handler: Any class with a default constructor, or any instance.
        @param callback: Called (with name of service as argument) when the service has been
        published.
        '''
        if name == 'system':
            logging.error('Invalid service name: %s', name)
        else:
            self._store[name] = handler
            data = {'name': name}
            if callback:
                data['callback'] = serializer.serialize(self, callback)
            self._connection.send_command('JOINWORKERPOOL', data)

    def unpublish_service(self, name, callback=None):
        '''Stops publishing a service to Bridge.

        @param name: The name of the service.
        @param callback: Called (with name of service as argument) when the service has stopped being published.
        '''
        if name == 'system':
            logging.error('Invalid service name: %s', name)
        else:
            data = {'name': name}
            if callback:
                data['callback'] = serializer.serialize(self, callback)
            self._connection.send_command('LEAVEWORKERPOOL', data)

    def get_service(self, name):
        '''Fetch a service from Bridge.

        @param name: The service name.
        @return: An opaque reference to a service.
        '''
        return reference.Reference(self, ['named', name, name])

    def get_channel(self, name):
        '''Fetch a channel from Bridge.

        @param name: The name of the channel.
        @return: An opaque reference to a channel.
        '''
        # Send GETCHANNEL command in order to establih link for channel if client is not member
        self._connection.send_command('GETCHANNEL', {'name': name})
        return reference.Reference(self, ['channel', name, 'channel:' + name])

    def join_channel(self, name, handler, writeable=True, callback=None):
        '''Register a handler with a channel.

        @param name: The name of the channel.
        @param handler: An opaque reference to a channel.
        @param writeable: Whether the handler's owner may write to the channel.
        @param callback: Called (with reference to channel, and name of channel) after the handler has been
        attached to the channel.
        '''
        if hasattr(writeable, '__call__'):
            logging.warn('Deprecated -- the joinChannel API has been revised.')
            writeable, callback = True, writeable
        data = {'name': name, 'handler': serializer.serialize(self, handler), 'writeable': writeable}
        if callback:
            data['callback'] = serializer.serialize(self, callback)
        self._connection.send_command('JOINCHANNEL', data)

    def leave_channel(self, name, handler, callback=None):
        '''Remove yourself from a channel.

        @param name: The name of the channel.
        @param handler: An opaque reference to a channel.
        @param callback: Called (with name of channel as argument) after the handler has been
        attached to the channel.
        '''
        data = {'name': name, 'handler': serializer.serialize(self, handler)}
        if callback:
            data['callback'] = serializer.serialize(self, callback)
        self._connection.send_command('LEAVECHANNEL', data)

    def ready(self, func):
        '''Entry point into the Bridge event loop.

        func is called when this node has established a connection to a Bridge
        instance. This function does not return.

        @param func: Called (with no arguments) after initialization.
        '''
        if not self._ready:
            self.on('ready', func)
        else:
            func()

    def connect(self, callback=None):
        '''Entry point into the Bridge event loop.

        This function starts the event loop. It will eventually execute
        handlers for the 'ready' event. It does not return.

        @param callback: Called (with no arguments) after initialization.
        '''
        if callback:
            self.ready(callback)
        self._connection.start()

    def get_client(self, id):
        return client.Client(self, id)

    def context(self):
        return self._context

    def _execute(self, address, args):
        # Retrieve stored handler
        obj = self._store[address[2]]
        # Retrieve function in handler
        func = getattr(obj, address[3], None)
        if not func:
            logging.warn('Could not find object to handle %s', '.'.join(address))
        else:
            try:
                func(*args)
            except:
                traceback.print_exc()
                logging.error('Exception while calling %s(%s)', address[3], args)

    def _store_object(self, handler, ops):
        # Generate random id for callback being stored
        name = util.generate_guid()
        self._store[name] = handler
        # Return reference to stored callback
        return reference.Reference(self, ['client', self._connection.client_id, name], ops)

    def _send(self, args, destination):
        args = list(args)
        self._connection.send_command('SEND', {
            'args': serializer.serialize(self, args),
            'destination': destination,
        })

class _SystemService(object):
    def __init__(self, bridge):
        self._bridge = bridge

    def hookChannelHandler(self, name, handler, func=None):
        # Store under channel name
        self._bridge._store['channel:' + name] = handler
        if func:
            # Send callback with reference to channel and handler operations
            func(reference.Reference(self._bridge, ['channel', name, 'channel:' + name], util.find_ops(handler)), name)

    def getService(self, name, func):
        if name in self._bridge._store:
            func(self._bridge._store[name], name)
        else:
            func(None, name)

    def remoteError(self, msg):
        logging.warning(msg)
        self._bridge.emit('remote_error', msg)

