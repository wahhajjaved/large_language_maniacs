'''A `RemoteAPI` is an interface-like class whose methods correspond to remote calls.

Let us start with an example::

    from quickrpc.remote_api import RemoteAPI, incoming, outgoing
    
    class MyAPI(RemoteAPI):
        @incoming
        def notify(self, sender, arg1=val1, arg2=val2):
            """notification that something happened"""
            
        @outgoing
        def helloworld(self, receivers, arg1=val1):
            """Tell everybody that I am here."""
            
        @incoming(has_reply=true)
        def echo(self, sender, text="test"):
            """returns the text that was sent."""

RemoteAPI is used by subclassing it. Remote methods are defined by the
``@incoming`` and ``@outgoing`` decorators.

Important:
    The method body of remote methods must be empty.

This is because by caling ``@outgoing`` methods, you actually issue a call
over the :class:`~.transports.Transport` that is bound to the 
``RemoteAPI`` at runtime. Since the API is meant to be used by both sides (by 
means of inverting it), ``@incoming`` methods should be empty, too. The side 
effect of this is that the class definition is more or less a printable 
specification of your interface.

``@incoming`` methods have a ``.connect()`` method to attach an implementation
to that message. The connected handler has the same signature as the
``@incoming`` method, except for the ``self`` argument.

By default, all defined calls are resultless (i.e. notifications). To define
calls with return value, decorate with ``has_reply=True`` kwarg.

When handling such a call on the incoming side, your handler's return value
is returned to the sender. Exceptions are caught and sent as error reply.

On the ``outgoing`` side, the call immediately returns a 
:class:`~.Promise` object.
You then use :meth:`~.Promise.result` to get at the actual 
result. This will block
until the result arrived.

(TODO: make blocking call by default, add block=False param for Promises)

'''
import logging
from .promise import Promise
import itertools as it
import inspect
from .codecs import Codec, Message, Reply, ErrorReply
from .transports import Transport

L = lambda: logging.getLogger(__name__)

__all__ = [
    'RemoteAPI',
    'incoming',
    'outgoing',
]


class RemoteAPI(object):
    '''Describes an API i.e. a set of allowed outgoing and incoming calls.
    
    Subclass and add your calls.
    
    :attr:`.codec` holds the Codec for (de)serializing data.
    :attr:`.transport` holds the underlying transport.

    Both can also be strings, then :meth:`.Transport.fromstring` / :meth:`.Codec.fromstring` are used
    to acquire the respective objects. In this case, transport still needs to be started
    via ``myapi.transport.start()``.
    
    Methods marked as ``@outgoing`` are automatically turned into
    messages when called. The method body is executed before sending. (use e.g.
    for validation of outgoing data).
    They must accept a special `receivers` argument, which is passed to the
    Transport.
    
    Methods marked as ``@incoming`` are called by the transport when
    messages arrive. They work like signals - you can connect your
    own handler(s) to them. Connected handlers must have the same
    signature as the incoming call. All @incoming methods MUST support
    a `senders` argument.
    
    Connect like this:
    
    >>> def handler(self, foo=None): pass
    >>> remote_api.some_method.connect(handler)
    >>> # later
    >>> remote_api.some_method.disconnect(handler)
    
    Execution order: the method of remote_api is executed first,
    then the connected handlers in the order of registering.
    
    Incoming messages with unknown method will not be processed. If the message
    has ``.id != 0``, it will automatically be replied with an error.
    
    Threading:
    
        * outgoing messages are sent on the calling thread.
        * incoming messages are handled on the thread which
          handles Transport receive events. I.e. the
          Transport implementation defines the behaviour.
            
    Lastly, you can :meth:`.invert` the whole api,
    swapping incoming and outgoing methods. When inverted, the ``sender`` and 
    ``receiver`` arguments of each method swap their roles.
    
    '''
    def __init__(self, codec='jrpc', transport=None, invert=False):
        if isinstance(codec, str):
            codec = Codec.fromstring(codec)
        if isinstance(transport, str):
            transport = Transport.fromstring(transport)
        self.codec = codec
        self.transport = transport
        # FIXME: limit size of _pending_replies somehow
        self._pending_replies = {}
        self._id_dispenser = it.count()
        # pull the 0
        next(self._id_dispenser)
        if invert:
            self.invert()
        
    @property
    def transport(self):
        '''Gets/sets the transport used to send and receive messages.
        
        You can change the transport at runtime.'''
        return self._transport
    @transport.setter
    def transport(self, value):
        self._transport = value
        if self._transport:
            self._transport.set_on_received(self._handle_received)
            
    def invert(self):
        '''Swaps ``@incoming`` and ``@outgoing`` decoration
        on all methods of this INSTANCE.
        
        I.e. generates the opposite-side API.
        
        Do this before connecting any handlers to incoming calls.
        
        You can achieve the same effect by instantiating with ``invert=True`` kwarg.
        '''
        for attr in dir(self):
            field = getattr(self, attr)
            if hasattr(field, '_remote_api_incoming') or hasattr(field, '_remote_api_outgoing'):
                # The decorators add a "method" .inverted() to the field,
                # which will yield the inverse-decorated field.
                setattr(self, attr, field.inverted().__get__(self))
        

    # ---- handling of incoming messages ----

    def _handle_received(self, sender, data):
        '''called by the Transport when data comes in.'''
        messages, remainder = self.codec.decode(data)
        for message in messages:
            if isinstance(message, Exception):
                self.message_error(message)
                continue
            elif isinstance(message, Reply) or isinstance(message, ErrorReply):
                self._deliver_reply(message)
            else:
                self._handle_method(sender, message)
        return remainder

    def _handle_method(self, sender, message):
        try:
            method = getattr(self, message.method)
        except AttributeError:
            self.message_error(AttributeError("Incoming call of %s not defined on the api"%message.method), message)
            return
        if not hasattr(method, "_remote_api_incoming"):
            self.message_error(AttributeError("Incoming call of %s not marked as @incoming on the api"%message.method), message)
            return
        has_reply = method._remote_api_incoming['has_reply']
        try:
            result = method(sender, message)
        except Exception as e:
            L().error(str(e), exc_info = True)
            if has_reply: 
                self.message_error(e, message)
        else:
            if has_reply:
                data = self.codec.encode_reply(message, result)
                self.transport.send(data)

    def message_error(self, exception, in_reply_to=None):
        '''Called each time that an incoming message causes problems.
        
        By default, it logs the error as warning. in_reply_to is the message that 
        triggered the error, None if decoding failed. If the requested method can be 
        identified and has a reply, an error reply is returned to the sender.
        '''
        L().warning(exception)
        if in_reply_to.id:
            data = self.codec.encode_error(in_reply_to, exception, errorcode=0)
            self.transport.send(data)

    def _deliver_reply(self, reply):
        id = reply.id
        try:
            promise = self._pending_replies.pop(id)
        except KeyError:
            # do not raise, since it cannot be caught by user.
            L().warning('Received reply that was never requested: %r'%(reply,))

        if isinstance(reply, Reply):
            promise.set_result(reply.result)
        else:
            # Put the ErrorReply in the result queue.
            promise.set_exception(reply)

    # ---- handling of outgoing messages ----

    def _new_request(self):
        call_id = next(self._id_dispenser)
        promise = Promise()
        self._pending_replies[call_id] = promise
        return call_id, promise

    # ---- stuff ----

    def unhandled_calls(self):
        '''Generator, returns the names of all *incoming*, unconnected methods.

        If no results are returned, all incoming messages are connected. Use 
        this to check for missed ``.connect`` calls.
        '''
        result = []
        for attr in dir(self):
            field = getattr(self, attr)
            if hasattr(field, '_remote_api_incoming') and not field._listeners:
                yield attr


# TODO: keep signature of wrapped methods

def incoming(unbound_method=None, has_reply=False, allow_positional_args=False):
    '''Marks a method as possible incoming message.
    
    ``@incoming(has_reply=False, allow_position_args=False)``
    
    Incoming methods keep list of connected listeners, which are called with the 
    signature of the incoming method (excluding ``self``). The first argument
    will be passed positional and is a string describing the sender of the message.
    The remaining arguments can be chosen freely and will usually be passed as named
    args.
    
    Listeners can be added with ``myapi.<method>.connect(handler)`` and 
    disconnected with ``.disconnect(handler)``. They are called in the order that 
    they were added.
    
    If ``has_reply=True``, the handler should return a value that is sent back 
    to the sender. If multiple handlers are connected, at most one of them must 
    return something.
    
    If ``allow_positional_args=True``, messages with positional (unnamed) 
    arguments are accepted. Otherwise such arguments throw an error message without 
    executing the handler(s). Note that the :class:`.Codec` must support positional 
    and/or mixed args as well. It is strongly recommended to use named args only.
    
    Lastly, the incoming method has a ``myapi.<method>.inverted()`` method, which
    will return the ``@outgoing`` variant of it.
    '''
    if not unbound_method:
        # when called as @decorator(...)
        return lambda unbound_method: incoming(unbound_method=unbound_method, has_reply=has_reply, allow_positional_args=allow_positional_args)
    # when called as @decorator or explicitly
    def fn(self, sender, message):
        if isinstance(message.kwargs, dict):
            args, kwargs = [], message.kwargs
        else:
            if not allow_positional_args:
                raise ValueError('Please call with named parameters only!')
            if isinstance(message.kwargs, list):
                args, kwargs = message.kwargs, {}
            else:
                args, kwargs = [message.kwargs], {}
        L().debug('incoming call of %s, args=%r, kwargs=%r'%(message.method, args, kwargs))
        try:
            replies = [unbound_method(self, sender, *args, **kwargs)]
        except TypeError:
            # signature is wrong
            raise TypeError('incoming call with wrong signature')
        for listener in fn._listeners:
            replies.append(listener(sender, *args, **kwargs))
        if has_reply:
            replies = [r for r in replies if r is not None]
            if len(replies) > 1:
                raise ValueError('Incoming call produced more than one reply!')
            replies.append(None) # If there is no result, reply with None
            return replies[0]

    # Presence of this attribute indicates that this method is a valid incoming target
    fn._remote_api_incoming = {'has_reply': has_reply}
    fn._listeners = []
    fn._unbound_method = unbound_method
    fn.connect = lambda listener: fn._listeners.append(listener)
    fn.disconnect = lambda listener: fn._listeners.remove(listener)
    fn.__name__ = unbound_method.__name__
    fn.__doc__ = unbound_method.__doc__
    fn.inverted = lambda: outgoing(unbound_method, has_reply=has_reply, allow_positional_args=allow_positional_args)
    return fn


def outgoing(unbound_method=None, has_reply=False, allow_positional_args=False):
    '''Marks a method as possible outgoing message.
    
    ``@outgoing(has_reply=False, allow_position_args=False)``
    
    Invocation of outgoing methods leads to a message being sent over the 
    :class:`.Transport` of the :class:`RemoteAPI`.
    
    The first argument must be the list of receivers of the message, as a list 
    of strings. When calling the method, usually you will use the sender name(s) 
    received via an incoming call.  Set receivers=None to send to all connected 
    peers.
    
    The remaining arguments can be choosen freely. The argument values can be 
    anything supported by the :class:`.Codec` that you use. The builtin Codecs 
    support all the "atomic" builtin types, as well as dicts and lists.
    
    If ``has_reply=True``, the other side is expected to return a result value. In this case,
    calling the outgoing method returns a :class:`.Promise` immediately.
    
    If ``allow_positional_args=True``, calls with positional (unnamed) 
    arguments are accepted. Otherwise such arguments raise :class:`ValueError`.
    **For sending, they will be converted into named arguments.**
    It is strongly recommended to use named args only.
    
    Lastly, the outgoing method has a ``myapi.<method>.inverted()`` method, which
    will return the ``@incoming`` variant of it.
    '''
    if not unbound_method:
        # when called as @decorator(...)
        return lambda unbound_method: outgoing(unbound_method=unbound_method, has_reply=has_reply, allow_positional_args=allow_positional_args)
    # when called as @decorator or explicitly
    if allow_positional_args:
        sig = inspect.signature(unbound_method)
        # cut off self and sender/receiver arg
        argnames = [p.name for p in sig.parameters.values()][2:]
    else:
        argnames = []
    def fn(self, receivers=None, *args, **kwargs):
        if args and not allow_positional_args:
            raise ValueError('Please call with named parameters only!')
        else:
            # map positional to named args
            for name, arg in zip(argnames, args):
                if name in kwargs:
                    raise ValueError('argument %s given twice!'%name)
                kwargs[name] = arg
        # this ensures that all args and kwargs are valid
        unbound_method(self, receivers, **kwargs)
        if has_reply:
            call_id, promise = self._new_request()
        else:
            call_id = 0
        data = self.codec.encode(unbound_method.__name__, kwargs=kwargs, id=call_id)
        self.transport.send(data, receivers=receivers)
        if has_reply:
            return promise

    fn._remote_api_outgoing = {'has_reply': has_reply}
    fn.__name__ = unbound_method.__name__
    fn.__doc__ = unbound_method.__doc__
    fn.inverted = lambda: incoming(unbound_method, has_reply=has_reply, allow_positional_args=allow_positional_args)
    return fn
