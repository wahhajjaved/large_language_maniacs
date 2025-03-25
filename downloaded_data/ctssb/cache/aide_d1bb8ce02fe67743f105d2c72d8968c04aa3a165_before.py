#!/usr/bin/env python

###
# Copyright (c) 2002, Jeremiah Fincher
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

__revision__ = "$Id$"

import fix

import copy
import sets
import time
from itertools import imap, chain, cycle

import log
import conf
import utils
import world
import ircdb
import ircmsgs
import ircutils
from structures import queue, smallqueue, RingBuffer

###
# The base class for a callback to be registered with an Irc object.  Shows
# the required interface for callbacks -- name(),
# inFilter(irc, msg), outFilter(irc, msg), and __call__(irc, msg) [used so
# functions can be used as callbacks conceivable, and so if refactoring ever
# changes the nature of the callbacks from classes to functions, syntactical
# changes elsewhere won't be required.
###

class IrcCommandDispatcher(object):
    """Base class for classes that must dispatch on a command."""
    def dispatchCommand(self, command):
        """Given a string 'command', dispatches to doCommand."""
        return getattr(self, 'do' + command.capitalize(), None)


class IrcCallback(IrcCommandDispatcher):
    """Base class for standard callbacks.

    Callbacks derived from this class should have methods of the form
    "doCommand" -- doPrivmsg, doNick, do433, etc.  These will be called
    on matching messages.
    """
    # priority determines the order in which callbacks are called.  Lower
    # numbers mean *higher* priority (like nice values in *nix).  Higher
    # priority means the callback is called *earlier* on the inFilter chain,
    # *earlier* on the __call__ chain, and *later* on the outFilter chain.
    priority = 99
    __metaclass__ = log.MetaFirewall
    __firewalled__ = {'die': None,
                      'reset': None,
                      '__call__': None,
                      'inFilter': lambda self, irc, msg: msg,
                      'outFilter': lambda self, irc, msg: msg,
                      'name': lambda self: self.__class__.__name__,}
    def name(self):
        """Returns the name of the callback."""
        return self.__class__.__name__

    def inFilter(self, irc, msg):
        """Used for filtering/modifying messages as they're entering.

        ircmsgs.IrcMsg objects are immutable, so this method is expected to
        return another ircmsgs.IrcMsg object.  Obviously the same IrcMsg
        can be returned.
        """
        return msg

    def outFilter(self, irc, msg):
        """Used for filtering/modifying messages as they're leaving.

        As with inFilter, an IrcMsg is returned.
        """
        return msg

    def __call__(self, irc, msg):
        """Used for handling each message."""
        method = self.dispatchCommand(msg.command)
        if method is not None:
            method(irc, msg)

    def reset(self):
        """Resets the callback.  Called when reconnecting to the server."""
        pass

    def die(self):
        """Makes the callback die.  Called when the parent Irc object dies."""
        pass

###
# Basic queue for IRC messages.  It doesn't presently (but should at some
# later point) reorder messages based on priority or penalty calculations.
###
_high = sets.ImmutableSet(['MODE', 'KICK', 'PONG', 'NICK', 'PASS'])
_low = sets.ImmutableSet(['PRIVMSG', 'PING', 'WHO', 'NOTICE'])
class IrcMsgQueue(object):
    """Class for a queue of IrcMsgs.  Eventually, it should be smart.

    Probably smarter than it is now, though it's gotten quite a bit smarter
    than it originally was.  A method to "score" methods, and a heapq to
    maintain a priority queue of the messages would be the ideal way to do
    intelligent queueing.

    As it stands, however, we simple keep track of 'high priority' messages,
    'low priority' messages, and normal messages, and just make sure to return
    the 'high priority' ones before the normal ones before the 'low priority'
    ones.
    """
    __slots__ = ('msgs', 'highpriority', 'normal', 'lowpriority')
    def __init__(self, iterable=()):
        self.reset()
        for msg in iterable:
            self.enqueue(msg)

    def reset(self):
        """Clears the queue."""
        self.highpriority = smallqueue()
        self.normal = smallqueue()
        self.lowpriority = smallqueue()
        self.msgs = sets.Set()

    def enqueue(self, msg):
        """Enqueues a given message."""
        if msg in self.msgs:
            log.warning('Not adding message %r to queue, already added.' % msg)
        else:
            self.msgs.add(msg)
            if msg.command in _high:
                self.highpriority.enqueue(msg)
            elif msg.command in _low:
                self.lowpriority.enqueue(msg)
            else:
                self.normal.enqueue(msg)

    def dequeue(self):
        """Dequeues a given message."""
        msg = None
        if self.highpriority:
            msg = self.highpriority.dequeue()
        elif self.normal:
            msg = self.normal.dequeue()
        elif self.lowpriority:
            msg = self.lowpriority.dequeue()
        if msg:
            try:
                self.msgs.remove(msg)
            except KeyError:
                s = 'Odd, dequeuing a message that\'s not in self.msgs.'
                log.warning(s)
        return msg

    def __nonzero__(self):
        return bool(self.highpriority or self.normal or self.lowpriority)

    def __len__(self):
        return sum(imap(len,[self.highpriority,self.lowpriority,self.normal]))

    def __repr__(self):
        name = self.__class__.__name__
        return '%s(%r)' % (name, list(chain(self.highpriority,
                                            self.normal,
                                            self.lowpriority)))
    __str__ = __repr__


###
# Maintains the state of IRC connection -- the most recent messages, the
# status of various modes (especially ops/halfops/voices) in channels, etc.
###
class ChannelState(object):
    __slots__ = ('users', 'ops', 'halfops', 'voices', 'topic', 'modes')
    def __init__(self):
        self.topic = ''
        self.users = ircutils.IrcSet()
        self.ops = ircutils.IrcSet()
        self.halfops = ircutils.IrcSet()
        self.voices = ircutils.IrcSet()
        self.modes = ircutils.IrcDict()

    def addUser(self, user):
        "Adds a given user to the ChannelState.  Power prefixes are handled."
        nick = user.lstrip('@%+')
        if not nick:
            return
        while user and user[0] in '@%+':
            (marker, user) = (user[0], user[1:])
            if marker == '@':
                self.ops.add(nick)
            elif marker == '%':
                self.halfops.add(nick)
            elif marker == '+':
                self.voices.add(nick)
        self.users.add(nick)

    def replaceUser(self, oldNick, newNick):
        """Changes the user oldNick to newNick; used for NICK changes."""
        # Note that this doesn't have to have the sigil (@%+) that users
        # have to have for addUser; it just changes the name of the user
        # without changing any of his categories.
        for s in (self.users, self.ops, self.halfops, self.voices):
            if oldNick in s:
                s.remove(oldNick)
                s.add(newNick)

    def removeUser(self, user):
        """Removes a given user from the channel."""
        self.users.discard(user)
        self.ops.discard(user)
        self.halfops.discard(user)
        self.voices.discard(user)

    def setMode(self, mode, value=None):
        self.modes[mode] = value

    def unsetMode(self, mode):
        if mode in self.modes:
            del self.modes[mode]

    def __getstate__(self):
        return [getattr(self, name) for name in self.__slots__]

    def __setstate__(self, t):
        for (name, value) in zip(self.__slots__, t):
            setattr(self, name, value)

    def __eq__(self, other):
        ret = True
        for name in self.__slots__:
            ret = ret and getattr(self, name) == getattr(other, name)
        return ret

    def __ne__(self, other):
        # This shouldn't even be necessary, grr...
        return not self == other

class IrcState(IrcCommandDispatcher):
    """Maintains state of the Irc connection.  Should also become smarter.
    """
    __slots__ = ('history', 'nicksToHostmasks', 'channels')
    __metaclass__ = log.MetaFirewall
    __firewalled__ = {'addMsg': None}
    def __init__(self):
        self.history = RingBuffer(conf.supybot.maxHistoryLength())
        self.reset()

    def reset(self):
        """Resets the state to normal, unconnected state."""
        self.history.reset()
        self.channels = ircutils.IrcDict()
        self.nicksToHostmasks = ircutils.IrcDict()

    def __getstate__(self):
        return map(curry(getattr, self), self.__slots__)

    def __setstate__(self, t):
        for (name, value) in zip(self.__slots__, t):
            setattr(self, name, value)

    def __eq__(self, other):
        ret = True
        for name in self.__slots__:
            ret = ret and getattr(self, name) == getattr(other, name)
        return ret

    def __ne__(self, other):
        return not self == other

    def copy(self):
        ret = self.__class__()
        ret.history = copy.deepcopy(self.history)
        ret.nicksToHostmasks = copy.deepcopy(self.nicksToHostmasks)
        ret.channels = copy.deepcopy(self.channels)
        return ret

    def addMsg(self, irc, msg):
        """Updates the state based on the irc object and the message."""
        self.history.append(msg)
        if ircutils.isUserHostmask(msg.prefix) and not msg.command == 'NICK':
            self.nicksToHostmasks[msg.nick] = msg.prefix
        method = self.dispatchCommand(msg.command)
        if method is not None:
            method(irc, msg)

    def getTopic(self, channel):
        """Returns the topic for a given channel."""
        return self.channels[channel].topic

    def nickToHostmask(self, nick):
        """Returns the hostmask for a given nick."""
        return self.nicksToHostmasks[nick]

    def do352(self, irc, msg):
        (nick, user, host) = (msg.args[2], msg.args[5], msg.args[3])
        hostmask = '%s!%s@%s' % (nick, user, host)
        self.nicksToHostmasks[nick] = hostmask

    def doJoin(self, irc, msg):
        for channel in msg.args[0].split(','):
            if channel in self.channels:
                self.channels[channel].addUser(msg.nick)
            else:
                chan = ChannelState()
                chan.addUser(msg.nick)
                self.channels[channel] = chan

    def doMode(self, irc, msg):
        channel = msg.args[0]
        if ircutils.isChannel(channel):
            chan = self.channels[channel]
            for (mode, value) in ircutils.separateModes(msg.args[1:]):
                if mode == '-o':
                    chan.ops.discard(value)
                elif mode == '+o':
                    chan.ops.add(value)
                if mode == '-h':
                    chan.halfops.discard(value)
                elif mode == '+h':
                    chan.halfops.add(value)
                if mode == '-v':
                    chan.voices.discard(value)
                elif mode == '+v':
                    chan.voices.add(value)
                elif mode[-1] in 'beq':
                    pass # We don't need this right now.
                else:
                    modeChar = mode[1]
                    if mode[0] == '+':
                        chan.setMode(modeChar, value)
                    else:
                        assert mode[0] == '-'
                        chan.unsetMode(modeChar)

    def do324(self, irc, msg):
        channel = msg.args[1]
        chan = self.channels[channel]
        for (mode, value) in ircutils.separateModes(msg.args[2:]):
            modeChar = mode[1]
            if mode[0] == '+':
                chan.setMode(modeChar, value)
            else:
                assert mode[0] == '-'
                chan.unsetMode(modeChar)

    def do353(self, irc, msg):
        (_, _, channel, users) = msg.args
        chan = self.channels[channel]
        users = users.split()
        for user in users:
            chan.addUser(user)

    def doPart(self, irc, msg):
        for channel in msg.args[0].split(','):
            chan = self.channels[channel]
            if msg.nick == irc.nick:
                del self.channels[channel]
            else:
                chan.removeUser(msg.nick)

    def doKick(self, irc, msg):
        (channel, users) = msg.args[:2]
        chan = self.channels[channel]
        for user in users.split(','):
            chan.removeUser(user)

    def doQuit(self, irc, msg):
        for channel in self.channels.itervalues():
            channel.removeUser(msg.nick)

    def doTopic(self, irc, msg):
        if len(msg.args) == 1:
            return # Empty TOPIC for information.  Does not affect state.
        chan = self.channels[msg.args[0]]
        chan.topic = msg.args[1]

    def do332(self, irc, msg):
        chan = self.channels[msg.args[1]]
        chan.topic = msg.args[2]

    def doNick(self, irc, msg):
        newNick = msg.args[0]
        oldNick = msg.nick
        try:
            if msg.user and msg.host:
                # Nick messages being handed out from the bot itself won't
                # have the necessary prefix to make a hostmask.
                newHostmask = ircutils.joinHostmask(newNick,msg.user,msg.host)
                self.nicksToHostmasks[newNick] = newHostmask
            del self.nicksToHostmasks[oldNick]
        except KeyError:
            pass
        for channel in self.channels.itervalues():
            channel.replaceUser(oldNick, newNick)



###
# The basic class for handling a connection to an IRC server.  Accepts
# callbacks of the IrcCallback interface.  Public attributes include 'driver',
# 'queue', and 'state', in addition to the standard nick/user/ident attributes.
###
class Irc(IrcCommandDispatcher):
    """The base class for an IRC connection.

    Handles PING commands already.
    """
    __metaclass__ = log.MetaFirewall
    __firewalled__ = {'die': None,
                      'feedMsg': None,
                      'takeMsg': None,}
    _nickSetters = sets.Set(['001', '002', '003', '004', '250', '251', '252',
                             '254', '255', '265', '266', '372', '375', '376',
                             '333', '353', '332', '366', '005'])
    def __init__(self, nick, user='', ident='', password='', callbacks=None):
        world.ircs.append(self)
        self.originalNick = intern(nick)
        self.nick = self.originalNick
        self.network = 'unset'
        self.nickmods = cycle(conf.supybot.nickmods())
        self.password = password
        self.user = intern(user or nick)  # Default to nick
        self.ident = intern(ident or nick)  # Ditto.
        self.prefix = '%s!%s@%s' % (nick, ident, 'unset.domain')
        if callbacks is None:
            self.callbacks = []
        else:
            self.callbacks = callbacks
        self.state = IrcState()
        self.queue = IrcMsgQueue()
        self.lastTake = 0
        self.server = 'unset'
        self.afterConnect = False
        self.fastqueue = smallqueue()
        self.lastping = time.time()
        self.outstandingPing = False
        self.driver = None # The driver should set this later.
        if self.password:
            self.queue.enqueue(ircmsgs.password(self.password))
        self.queue.enqueue(ircmsgs.nick(self.nick))
        self.queue.enqueue(ircmsgs.user(self.ident, self.user))

    def reset(self):
        """Resets the Irc object.  Called when the driver reconnects."""
        self.nick = self.originalNick
        self.prefix = '%s!%s@%s' % (self.nick, self.ident, 'unset.domain')
        self.state.reset()
        self.queue.reset()
        self.server = 'unset'
        self.afterConnect = False
        self.lastping = time.time()
        self.outstandingPing = False
        self.fastqueue = queue()
        if self.password:
            self.queue.enqueue(ircmsgs.password(self.password))
        self.queue.enqueue(ircmsgs.nick(self.nick))
        self.queue.enqueue(ircmsgs.user(self.ident, self.user))
        for callback in self.callbacks:
            callback.reset()

    def addCallback(self, callback):
        """Adds a callback to the callbacks list."""
        self.callbacks.append(callback)
        utils.sortBy(lambda cb: cb.priority, self.callbacks)

    def getCallback(self, name):
        """Gets a given callback by name."""
        name = name.lower()
        for callback in self.callbacks:
            if callback.name().lower() == name:
                return callback
        else:
            return None

    def removeCallback(self, name):
        """Removes a callback from the callback list."""
        name = name.lower()
        def nameMatches(cb):
            return cb.name().lower() == name
        (bad, good) = partition(nameMatches, self.callbacks)
        self.callbacks[:] = good
        return bad

    def queueMsg(self, msg):
        """Queues a message to be sent to the server."""
        self.queue.enqueue(msg)

    def sendMsg(self, msg):
        """Queues a message to be sent to the server *immediately*"""
        self.fastqueue.enqueue(msg)

    def takeMsg(self):
        """Called by the IrcDriver; takes a message to be sent."""
        now = time.time()
        msg = None
        if self.fastqueue:
            msg = self.fastqueue.dequeue()
        elif self.queue:
            if not world.testing and now - self.lastTake <= \
                                           conf.supybot.throttleTime():
                log.debug('Irc.takeMsg throttling.')
            else:
                self.lastTake = now
                msg = self.queue.dequeue()
        elif conf.supybot.pingServer() and \
             now > (self.lastping + conf.supybot.pingInterval()) and \
             self.afterConnect:
            if self.outstandingPing:
                s = 'Reconnecting to %s, ping not replied to.' % self.server
                log.warning(s)
                self.driver.reconnect()
                self.reset()
            else:
                self.lastping = now
                now = str(int(now))
                self.outstandingPing = True
                self.queueMsg(ircmsgs.ping(now))
        if msg:
            #log.debug(repr(msg)) # Useless!
            for callback in reviter(self.callbacks):
                msg = callback.outFilter(self, msg)
                if msg is None:
                    log.debug('%s.outFilter returned None.' % callback.name())
                    return self.takeMsg()
            if len(str(msg)) > 512:
                # Yes, this violates the contract, but at this point it doesn't
                # matter.  That's why we gotta go munging in private attributes
                msg._str = msg._str[:500] + '\r\n'
                msg._len =  len(str(msg))
            self.state.addMsg(self, msg)
            log.debug('Outgoing message: ' + str(msg).rstrip('\r\n'))
            return msg
        else:
            return None

    def do001(self, msg):
        """Logs (and stores) the name of the network."""
        welcome = msg.args[1]
        if not welcome.startswith('Welcome to the '):
            log.info('Unexpected 001 welcome, guessing at network name.')
        words = welcome.split()
        self.network = words[3].lower()
        log.info('Setting network to %s.', self.network)

    def do002(self, msg):
        """Logs the ircd version."""
        (beginning, version) = rsplit(msg.args[-1], maxsplit=1)
        log.info('Server %s has version %s', self.server, version)

    def doPing(self, msg):
        """Handles PING messages."""
        self.sendMsg(ircmsgs.pong(msg.args[0]))

    def doPong(self, msg):
        """Handles PONG messages."""
        self.outstandingPing = False

    def do376(self, msg):
        log.info('Got end of MOTD from %s', self.server)
        self.afterConnect = True
    do377 = do422 = do376

    def do433(self, msg):
        """Handles 'nickname already in use' messages."""
        if self.nick != self.originalNick:
            newNick = self.nickmods.next() % self.originalNick
            log.info('Got 433: %s is in use.  Trying %s.', self.nick, newNick)
            self.sendMsg(ircmsgs.nick(newNick))
    do432 = do433

    def doJoin(self, msg):
        if msg.nick == self.nick:
            channel = msg.args[0]
            self.queueMsg(ircmsgs.who(channel))
            self.queueMsg(ircmsgs.mode(channel))

    def doError(self, msg):
        """Handles ERROR messages."""
        log.info('Error message from %s: %s', self.server, msg.args[0])
        if msg.args[0].startswith('Closing Link'):
           self.driver.reconnect()
        elif 'too fast' in msg.args[0]:
           self.driver.reconnect(wait=True)

    def doNick(self, msg):
        """Handles NICK messages."""
        if msg.nick == self.nick:
            newNick = intern(msg.args[0])
            self.nick = newNick
            (nick, user, domain) = ircutils.splitHostmask(msg.prefix)
            self.prefix = ircutils.joinHostmask(self.nick, user, domain)
            self.prefix = intern(self.prefix)
        elif conf.supybot.followIdentificationThroughNickChanges():
            # We use elif here because this means it's someone else's nick
            # change, not our own.
            try:
                id = ircdb.users.getUserId(msg.prefix)
                u = ircdb.users.getUser(id)
            except KeyError:
                return
            if u.auth:
                (_, user, host) = ircutils.splitHostmask(msg.prefix)
                newhostmask = ircutils.joinHostmask(msg.args[0], user, host)
                log.info('Following identification for %s: %s -> %s',
                         u.name, u.auth[1], newhostmask)
                u.auth = (u.auth[0], newhostmask)
                ircdb.users.setUser(id, u)

    def feedMsg(self, msg):
        """Called by the IrcDriver; feeds a message received."""
        log.debug('Incoming message: ' + str(msg).rstrip('\r\n'))

        # Yeah, so this is odd.  Some networks (oftc) seem to give us certain
        # messages with our nick instead of our prefix.  We'll fix that here.
        if msg.prefix == self.nick:
            log.debug('Got one of those odd nick-instead-of-prefix msgs.')
            msg = ircmsgs.IrcMsg(prefix=self.prefix, msg=msg)

        # This catches cases where we know our own nick (from sending it to the
        # server) but we don't yet know our prefix.
        if msg.nick == self.nick and self.prefix != msg.prefix:
            self.prefix = msg.prefix

        # This keeps our nick and server attributes updated.
        if msg.command in self._nickSetters:
            if msg.args[0] != self.nick:
                log.info('Updating nick attribute.')
                self.nick = msg.args[0]
            if msg.prefix != self.server:
                log.info('Updating server attribute.')
                self.server = msg.prefix

        # Dispatch to specific handlers for commands.
        method = self.dispatchCommand(msg.command)
        if method is not None:
            method(msg)

        # Now update the IrcState object.
        try:
            self.state.addMsg(self, msg)
        except:
            log.exception('Exception in update of IrcState object:')

        # Now call the callbacks.
        for callback in self.callbacks:
            try:
                m = callback.inFilter(self, msg)
                if not m:
                    log.debug('%s.inFilter returned None' % callback.name())
                    return
                msg = m
            except:
                log.exception('Uncaught exception in inFilter:')
        for callback in self.callbacks:
            try:
                if callback is not None:
                    callback(self, msg)
            except:
                log.exception('Uncaught exception in callback:')

    def die(self):
        """Makes the Irc object die.  Dead."""
        log.info('Irc object for %s dying.' % self.server)
        if self in world.ircs:
            for cb in self.callbacks:
                cb.die()
            world.ircs.remove(self)
        else:
            log.warning('Irc object killed twice.')

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return id(self) == id(other)

    def __ne__(self, other):
        return not (self == other)

    def __str__(self):
        return 'Irc object for server %s' % self.server


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
