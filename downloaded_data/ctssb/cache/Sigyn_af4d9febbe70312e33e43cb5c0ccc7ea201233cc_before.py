#!/usr/bin/env/python
#
# -*- coding: utf-8 -*-

###
# Copyright (c) 2016, Nicolas Coevoet
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

import os
import re
import sys
import time
import urllib
import sqlite3
import httplib
import threading
import dns.resolver

import supybot.log as log
import supybot.conf as conf
import supybot.utils as utils
import supybot.ircdb as ircdb
import supybot.world as world
from supybot.commands import *
import supybot.ircmsgs as ircmsgs
import supybot.plugins as plugins
import supybot.commands as commands
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.schedule as schedule
import supybot.registry as registry

try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Sigyn')
except:
    _ = lambda x:x

def repetitions(s):
    # returns a list of (pattern,count), used to detect a repeated pattern inside a single string.
    r = re.compile(r"(.+?)\1+")
    for match in r.finditer(s):
        yield (match.group(1), len(match.group(0))/len(match.group(1)))

def isCloaked (prefix):
    if not ircutils.isUserHostmask(prefix):
        return False
    (nick,ident,host) = ircutils.splitHostmask(prefix)
    if '/' in host:
        if host.startswith('gateway/') or host.startswith('nat/') or host.endswith('skraito-0x71'):
            return False
        return True
    return False

def compareString (a,b):
    """return 0 to 1 float percent of similarity ( 0.85 seems to be a good average )"""
    if a == b:
        return 1
    sa, sb = set(a), set(b)
    n = len(sa.intersection(sb))
    if float(len(sa) + len(sb) - n) == 0:
        return 0
    jacc = n / float(len(sa) + len(sb) - n)
    return jacc

def largestString (s1,s2):
    """return largest pattern available in 2 strings"""
    # From https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Longest_common_substring#Python2
    # License: CC BY-SA
    m = [[0] * (1 + len(s2)) for i in xrange(1 + len(s1))]
    longest, x_longest = 0, 0
    for x in xrange(1, 1 + len(s1)):
        for y in xrange(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
    return s1[x_longest - longest: x_longest]

def floatToGMT (t):
    f = None
    try:
        f = float(t)
    except:
        return None
    return time.strftime('%Y-%m-%d %H:%M:%S GMT',time.gmtime(f))

def _getRe(f):
    def get(irc, msg, args, state):
        original = args[:]
        s = args.pop(0)
        def isRe(s):
            try:
                foo = f(s)
                return True
            except ValueError:
                return False
        try:
            while len(s) < 512 and not isRe(s):
                s += ' ' + args.pop(0)
            if len(s) < 512:
                state.args.append([s,f(s)])
            else:
                state.errorInvalid('regular expression', s)
        except IndexError:
            args[:] = original
            state.errorInvalid('regular expression', s)
    return get

getPatternAndMatcher = _getRe(utils.str.perlReToPythonRe)

addConverter('getPatternAndMatcher', getPatternAndMatcher)

class Ircd (object):
    
    __slots__ = ('irc', 'channels','whowas','klines','queues','opered','defcon','pending','logs','limits','dline','efnet','digs','netsplit','tors','ping','servers','resolving','stats','dnv','patterns','throttled')

    def __init__(self,irc):
        self.irc = irc
        # contains Chan instances
        self.channels = {}
        # contains Pattern instances
        self.patterns = {}
        # contains whowas requested for a short period of time
        self.whowas = {}
        # contains klines requested for a short period of time
        self.klines = {}
        # contains various TimeoutQueue for detection purpose 
        # often it's [host] { with various TimeOutQueue and others elements }
        self.queues = {}
        # flag or time
        self.opered = False
        # flag or time
        self.defcon = False
        # used for temporary storage of outgoing actions
        self.pending = {}
        self.logs = {}
        # contains servers notices when full or in bad state
        # [servername] = time.time()
        self.limits = {}
        # current ip to dline, one at time, due to testline limitation
        self.dline = ''
        # flag or time
        self.efnet = False
        # { ip : message }
        self.digs = {}
        # flag or time
        self.netsplit = False
        self.tors = {}
        self.ping = None
        self.servers = {}
        self.resolving = {}
        self.stats = {}
        self.dnv = {}
        self.throttled = False

    def __repr__(self):
        return '%s(patterns=%r, queues=%r, channels=%r, pending=%r, logs=%r, digs=%r, limits=%r, whowas=%r, klines=%r)' % (self.__class__.__name__,
        self.patterns, self.queues, self.channels, self.pending, self.logs, self.digs, self.limits, self.whowas, self.klines)

    def restore (self,db):
        c = db.cursor()
        c.execute("""SELECT id, pattern, regexp, mini, life FROM patterns WHERE removed_at is NULL""")
        items = c.fetchall()
        if len(items):
            for item in items:
                (uid,pattern,regexp,limit,life) = item
                if regexp == 1:
                    regexp = True
                else:
                    regexp = False
                self.patterns[uid] = Pattern(uid,pattern,regexp,limit,life)
        c.close()

    def add (self,db,prefix,pattern,limit,life,regexp):
        c = db.cursor()
        t = 0
        if regexp:
            t = 1
        c.execute("""INSERT INTO patterns VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)""", (pattern,t,limit,life,prefix,'',0,float(time.time())))
        uid = int(c.lastrowid)
        self.patterns[uid] = Pattern(uid,pattern,regexp,limit,life) 
        db.commit()
        c.close()
        return uid

    def count(self,db,uid):
        uid = int(uid)
        if uid in self.patterns:
            c = db.cursor()
            c.execute("""SELECT id, triggered FROM patterns WHERE id=? LIMIT 1""",(uid,))
            items = c.fetchall()
            if len(items):
                (uid,triggered) = items[0]
                triggered = int(triggered + 1)
                c.execute("""UPDATE patterns SET triggered=? WHERE id=?""",(triggered,uid))
                db.commit()
            c.close()

    def ls (self,db,pattern,deep=False):
        c = db.cursor()
        glob = '*%s*' % pattern
        like = '%'+pattern+'%'
        i = None
        try:
            i = int(pattern)
        except:
            i = None
        if i:
            c.execute("""SELECT id, pattern, regexp, operator, at, triggered, removed_at, removed_by, comment, mini, life FROM patterns WHERE id=? LIMIT 1""",(i,))
        else:
            if deep:
                c.execute("""SELECT id, pattern, regexp, operator, at, triggered, removed_at, removed_by, comment, mini, life FROM patterns WHERE id GLOB ? OR id LIKE ? OR pattern GLOB ? OR pattern LIKE ? OR comment GLOB ? OR comment LIKE ? ORDER BY id DESC""",(glob,like,glob,like,glob,like))
            else:
                c.execute("""SELECT id, pattern, regexp, operator, at, triggered, removed_at, removed_by, comment, mini, life FROM patterns WHERE (id GLOB ? OR id LIKE ? OR pattern GLOB ? OR pattern LIKE ? OR comment GLOB ? OR comment LIKE ?) and removed_at is NULL ORDER BY id DESC""",(glob,like,glob,like,glob,like))
        items = c.fetchall()
        c.close()
        if len(items):
            results = []
            for item in items:
                (uid,pattern,regexp,operator,at,triggered,removed_at,removed_by,comment,limit,life) = item
                end = ''
                if i:
                    if removed_by:
                        end = ' - disabled on %s by %s - ' % (floatToGMT(removed_at),removed_by.split('!')[0])
                    results.append('#%s "%s" by %s on %s (%s calls) %s/%ss%s(%s)' % (uid,pattern,operator.split('!')[0],floatToGMT(at),triggered,limit,life,end,comment))
                else:
                    if removed_by:
                        end = ' (disabled)'
                    results.append('[#%s "%s" (%s calls) %s/%ss%s]' % (uid,pattern,triggered,limit,life,end))
            return results
        return []

    def edit (self,db,uid,limit,life,comment):
        c = db.cursor()
        uid = int(uid)
        c.execute("""SELECT id, life FROM patterns WHERE id=? LIMIT 1""",(uid,))
        items = c.fetchall()
        if len(items):
            if comment:
                c.execute("""UPDATE patterns SET life=?, mini=?, comment=? WHERE id=? LIMIT 1""",(life,limit,comment,uid))
            else:
                c.execute("""UPDATE patterns SET life=?, mini=? WHERE id=? LIMIT 1""",(life,limit,uid))
            db.commit()
            if uid in self.patterns:
               self.patterns[uid].life = life
               self.patterns[uid].limit = limit
            found = True
        c.close()
        return (len(items))

    def toggle (self,db,uid,prefix,active):
        c = db.cursor()
        uid = int(uid)
        c.execute("""SELECT id, pattern, regexp, mini, life, removed_at, removed_by FROM patterns WHERE id=? LIMIT 1""",(uid,))
        items = c.fetchall()
        updated = False
        if len(items):
            (id,pattern,regexp,limit,life,removed_at,removed_by) = items[0]
            if active and removed_at:
                c.execute("""UPDATE patterns SET removed_at=NULL, removed_by=NULL WHERE id=? LIMIT 1""",(uid,))
                self.patterns[uid] = Pattern(uid,pattern,regexp == 1,limit,life)
                updated = True
            elif not removed_at:
                c.execute("""UPDATE patterns SET removed_at=?, removed_by=? WHERE id=? LIMIT 1""",(float(time.time()),prefix,uid))
                if uid in self.patterns:
                    del self.patterns[uid]
                updated = True
            db.commit()
        c.close()
        return updated

class Chan (object):
    __slots__ = ('channel', 'patterns', 'buffers', 'logs', 'nicks', 'called')
    def __init__(self,channel):
        self.channel = channel
        self.patterns = None
        self.buffers = {}
        self.logs = {}
        self.nicks = {}
        self.called = False
    def __repr__(self):
        return '%s(channel=%r, patterns=%r, buffers=%r, logs=%r, nicks=%r)' % (self.__class__.__name__,
        self.channel, self.patterns, self.buffers, self.logs, self.nicks)

class Pattern (object):
    __slots__ = ('uid', 'pattern', 'limit', 'life', '_match')
    def __init__(self,uid,pattern,regexp,limit,life):
        self.uid = uid
        self.pattern = pattern
        self.limit = limit
        self.life = life
        self._match = False
        if regexp:
            self._match = utils.str.perlReToPythonRe(pattern)
    def match (self,text):
        if self._match:
            return self._match.search (text) != None
        return self.pattern in text
    def __repr__(self):
        return '%s(uid=%r, pattern=%r, limit=%r, life=%r, _match=%r)' % (self.__class__.__name__,
        self.uid, self.pattern, self.limit, self.life, self._match)

def fillDnsbl (ip,droneblHost,droneblKey):
    def check(answer):
        if 'listed="1"' in answer:
            return
        add = "<?xml version=\"1.0\"?><request key='"+droneblKey+"'><add ip='"+ip+"' type='3' comment='used by irc spam bot' /></request>"
        type, uri = urllib.splittype(droneblHost)
        host, handler = urllib.splithost(uri)
        connection = httplib.HTTPConnection(host)
        connection.putrequest("POST",handler)
        connection.putheader("Content-Type", "text/xml")
        connection.putheader("Content-Length", str(int(len(add))))
        connection.endheaders()
        connection.send(add)
    request = "<?xml version=\"1.0\"?><request key='"+droneblKey+"'><lookup ip='"+ip+"' /></request>"
    type, uri = urllib.splittype(droneblHost)
    host, handler = urllib.splithost(uri)
    connection = httplib.HTTPConnection(host)
    connection.putrequest("POST",handler)
    connection.putheader("Content-Type", "text/xml")
    connection.putheader("Content-Length", str(int(len(request))))
    connection.endheaders()
    connection.send(request)
    check(connection.getresponse().read())

class Sigyn(callbacks.Plugin,plugins.ChannelDBHandler):
    """Network and Channels Spam protections"""
    threaded = True
    noIgnore = True

    def __init__(self, irc):
        callbacks.Plugin.__init__(self, irc)
        plugins.ChannelDBHandler.__init__(self)
        self._ircs = ircutils.IrcDict()
        self.cache = utils.structures.CacheDict(10000)
        self.getIrc(irc)
        self.log.debug('init() called')

    def dnv (self,irc,msg,args):
        """rehash local file blacklist"""
        try:
            i = self.getIrc(irc)
            index = 0
            i.dnv = {}
            with open('/home/sigyn/Sigyn/plugins/Sigyn/passed.log', 'r') as content_file:
                file = content_file.read()
                for line in file.split('\n'):
                    i.dnv[line.split(':')[0].strip()] = line.strip()
                    index = index + 1
            irc.reply('%s ip added' % index)
        except:
            irc.reply('error during rehash')
    dnv = wrap(dnv,['owner'])

    def state (self,irc,msg,args,channel):
        """[<channel>]

        returns state of the plugin, for optional <channel>"""
        self.cleanup(irc)
        i = self.getIrc(irc)
        if not channel:
            irc.queueMsg(ircmsgs.privmsg(msg.nick,'Opered %s, enable %s, defcon %s, netsplit %s, efnet %s' % (i.opered,self.registryValue('enable'),(i.defcon),i.netsplit,i.efnet)))
            irc.queueMsg(ircmsgs.privmsg(msg.nick,'There is %s permanent patterns and %s channels directly monitored' % (len(i.patterns),len(i.channels))))
            channels = 0
            prefixs = 0
            for k in i.queues:
                if irc.isChannel(k):
                    channels += 1
                elif ircutils.isUserHostmask(k):
                    prefixs += 1
            irc.queueMsg(ircmsgs.privmsg(msg.nick,"Via server's notices: %s channels and %s users monitored" % (channels,prefixs)))
        for chan in i.channels:
            if channel == chan:
                ch = self.getChan(irc,chan)
                if not self.registryValue('ignoreChannel',channel=chan):
                    called = ""
                    if ch.called:
                        called = 'currently in defcon'
                    irc.queueMsg(ircmsgs.privmsg(msg.nick,'On %s (%s users) %s:' % (chan,len(ch.nicks),called)))
                    protections = ['flood','lowFlood','repeat','lowRepeat','massRepeat','lowMassRepeat','hilight','nick','ctcp']
                    for protection in protections:
                        if self.registryValue('%sPermit' % protection,channel=chan) > -1:
                            permit = self.registryValue('%sPermit' % protection,channel=chan) 
                            life = self.registryValue('%sLife' % protection,channel=chan) 
                            abuse = self.hasAbuseOnChannel(irc,chan,protection)
                            if abuse:
                                abuse = ' (ongoing abuses) '
                            else:
                                abuse = ''
                            count = 0
                            if protection == 'repeat':
                                for b in ch.buffers:
                                    if ircutils.isUserHostmask('n!%s' % b):
                                        count += 1
                            else:
                                for b in ch.buffers:
                                    if protection in b:
                                        count += len(ch.buffers[b])
                            if count:
                                count = " - %s user's buffers" % count
                            else:
                                count = ""
                            irc.queueMsg(ircmsgs.privmsg(msg.nick," - %s : %s/%ss %s%s" % (protection,permit,life,abuse,count)))        
        self.log.debug('%r' % i)
        irc.replySuccess()
    state = wrap(state,['owner',optional('channel')])

    def defcon (self,irc,msg,args,channel):
        """takes no arguments

        force bot to enter in defcon mode: lowered triggers limits, no ignore, kline of hosts in efnet's dnsbl, bot is less tolerant against abuse"""
        i = self.getIrc(irc)
        if channel:
            if channel in i.channels and self.registryValue('abuseDuration',channel=channel) > 0:
                chan = self.getChan(irc,channel)
                if chan.called:
                    self.logChannel(irc,'INFO: [%s] rescheduled ignores lifted, limits lowered (by %s) for %ss' % (channel,msg.nick,self.registryValue('abuseDuration',channel=channel)))
                    chan.called = time.time()
                else:    
                    self.logChannel(irc,'INFO: [%s] ignores lifted, limits lowered (by %s) for %ss' % (channel,msg.nick,self.registryValue('abuseDuration',channel=channel)))
                    chan.called = time.time()
        else:
            if i.defcon:
                i.defcon = time.time()
                irc.reply('Already in defcon mode, reset, %ss more' % self.registryValue('defcon'))
            else:
                i.defcon = time.time()
                self.logChannel(irc,"INFO: ignores lifted and abuses end to klines for %ss by %s" % (self.registryValue('defcon'),msg.nick))
        irc.replySuccess()
    defcon = wrap(defcon,['owner',optional('channel')])

    def vacuum (self,irc,msg,args):
        """takes no arguments

        VACUUM the permanent patterns's database"""
        db = self.getDb(irc.network)
        c = db.cursor()
        c.execute('VACUUM')
        c.close()
        irc.replySuccess()
    vacuum = wrap(vacuum,['owner'])

    def rehash (self,irc,msg,args):
        """takes no arguments

        clear plugin's state, buffers, cache etc"""
        self.cache = utils.structures.CacheDict(10000)
        self._ircs = ircutils.IrcDict()
        irc.replySuccess()
    clear = wrap(rehash,['owner'])

    def efnet (self,irc,msg,args,duration):
        """<duration>

         kline on join user listed in efnet's dnsbl for <duration> (in seconds)"""
        i = self.getIrc(irc)
        if i.efnet:
            i.efnet = time.time()+duration
            irc.reply('Already in efnet mode, reset, %ss more' % duration)
        else:
            i.efnet = time.time()+duration
            self.logChannel(irc,"INFO: klining efnet's users for %ss by %s" % (duration,msg.nick))
            irc.replySuccess()
    efnet = wrap(efnet,['owner','positiveInt'])

    def netsplit (self,irc,msg,args,duration):
        """<duration>

         entering netsplit mode for <duration> (in seconds)"""
        i = self.getIrc(irc)
        if i.netsplit:
            i.netsplit = time.time()+duration
            irc.reply('Already in netsplit mode, reset, %ss more' % duration)
        else:
            i.netsplit = time.time()+duration
            self.logChannel(irc,"INFO: netsplit activated for %ss by %s: some abuses are ignored" % (duration,msg.nick))
            irc.replySuccess()
    netsplit = wrap(netsplit,['owner','positiveInt'])

    def lspattern (self,irc,msg,args,optlist,pattern):
        """[--deep] <id|pattern>

        returns patterns which matchs pattern or info about pattern #id, use --deep to search on deactivated patterns"""
        i = self.getIrc(irc)
        deep = False
        for (option, arg) in optlist:
            if option == 'deep':
                deep = True
                break
        results = i.ls(self.getDb(irc.network),pattern,deep)
        if len(results):
            if deep:
                for r in results:
                    irc.queueMsg(ircmsgs.privmsg(msg.nick,r))
            else:
                irc.replies(results,None,None,False)
        else:
            irc.reply('no pattern found')
    lspattern = wrap(lspattern,['owner',getopts({'deep': ''}),'text'])

    def addpattern (self,irc,msg,args,limit,life,pattern):
        """<limit> <life> <pattern>

        add a permanent <pattern> : kline after <limit> calls raised during <life> seconds,
        for immediate kline use limit 0"""
        i = self.getIrc(irc)
        result = i.add(self.getDb(irc.network),msg.prefix,pattern,limit,life,False)
        self.logChannel(irc,'PATTERN: %s added #%s : "%s" %s/%ss' % (msg.nick,result,pattern,limit,life))
        irc.reply('#%s added' % result)
    addpattern = wrap(addpattern,['owner','nonNegativeInt','positiveInt','text'])

    def addregexpattern (self,irc,msg,args,limit,life,pattern):
        """<limit> <life> /<pattern>/

        add a permanent /<pattern>/ to kline after <limit> calls raised during <life> seconds,
        for immediate kline use limit 0"""
        i = self.getIrc(irc)
        result = i.add(self.getDb(irc.network),msg.prefix,pattern[0],limit,life,True)
        self.logChannel(irc,'PATTERN: %s added #%s : "%s" %s/%ss' % (msg.nick,result,pattern[0],limit,life))
        irc.reply('#%s added' % result)
    addregexpattern = wrap(addregexpattern,['owner','nonNegativeInt','positiveInt','getPatternAndMatcher'])

    def editpattern (self,irc,msg,args,uid,limit,life,comment):
        """<id> <limit> <life> [<comment>]

        edit #<id> with new <limit> <life> and <comment>"""
        i = self.getIrc(irc)
        result = i.edit(self.getDb(irc.network),uid,limit,life,comment)
        if result:
            if comment:
                self.logChannel(irc,'PATTERN: %s edited #%s with %s/%ss (%s)' % (msg.nick,uid,limit,life,comment))
            else:
                self.logChannel(irc,'PATTERN: %s edited #%s with %s/%ss' % (msg.nick,uid,limit,life))
            irc.replySuccess()
        else:
            irc.reply("#%s doesn't exist")
    editpattern = wrap(editpattern,['owner','positiveInt','nonNegativeInt','positiveInt',optional('text')])

    def togglepattern (self,irc,msg,args,uid,toggle):
        """<id> <boolean>

        activate or desactivate #<id>"""
        i = self.getIrc(irc)
        result = i.toggle(self.getDb(irc.network),uid,msg.prefix,toggle)
        if result:
            if toggle:
                self.logChannel(irc,'PATTERN: %s enabled #%s' % (msg.nick,uid))
            else:
                self.logChannel(irc,'PATTERN: %s disabled #%s' % (msg.nick,uid))
            irc.replySuccess()
        else:
            irc.reply("#%s doesn't exist or is already in requested state" % uid)
    togglepattern = wrap(togglepattern,['owner','positiveInt','boolean'])

    def lstmp (self,irc,msg,args,channel):
        """[<channel>]

        returns temporary patterns for given channel"""
        i = self.getIrc(irc)
        if channel in i.channels:
            chan = self.getChan(irc,channel)
            if chan.patterns:
                patterns = list(chan.patterns)
                if len(patterns):
                    irc.reply('[%s] %s patterns : %s' % (channel,len(patterns),', '.join(patterns)))
                else:
                    irc.reply('[%s] no active pattern' % channel)
            else:
                irc.reply('[%s] no active pattern' % channel)
        else:
            irc.reply('[%s] is unknown' % channel)
    lstmp = wrap(lstmp,['op'])

    def addtmp (self,irc,msg,args,channel,text):
        """[<channel>] <message>

        add a string in channel's temporary patterns"""
        text = text.lower()
        i = self.getIrc(irc)
        if channel in i.channels:
            chan = self.getChan(irc,channel)
            life = self.registryValue('computedPatternLife',channel=channel)
            if not chan.patterns:
                chan.patterns = utils.structures.TimeoutQueue(life)
            elif chan.patterns.timeout != life:
                chan.patterns.setTimeout(life)
            chan.patterns.enqueue(text)
            self.logChannel(irc,'PATTERN: [%s] added tmp "%s" for %ss by %s' % (channel,text,life,msg.nick))
            irc.replySuccess()
        else:
            irc.reply('unknown channel')
    addtmp = wrap(addtmp,['op','text'])

    def rmtmp (self,irc,msg,args,channel):
        """[<channel>]

        remove temporary patterns for given channel"""
        i = self.getIrc(irc)
        if channel in i.channels:
            chan = self.getChan(irc,channel)
            if chan.patterns:
                l = len(chan.patterns)
                chan.patterns.reset()
                if l:
                    self.logChannel(irc,'PATTERN: [%s] removed %s tmp pattern by %s' % (channel,l,msg.nick))
                    irc.replySuccess()
                else:
                    irc.reply('[%s] no active pattern' % channel)
            else:
                irc.reply('[%s] no active pattern' % channel)
        else:
            irc.reply('unknown channel')
    rmtmp = wrap(rmtmp,['op'])

    def oper (self,irc,msg,args):
        """takes no arguments

        ask bot to oper"""
        if len(self.registryValue('operatorNick')) and len(self.registryValue('operatorPassword')):
            irc.sendMsg(ircmsgs.IrcMsg('OPER %s %s' % (self.registryValue('operatorNick'),self.registryValue('operatorPassword'))))
            irc.replySuccess()
        else:
            irc.replyError('operatorNick or operatorPassword is empty')
    oper = wrap(oper,['owner'])

    # internal stuff

    def resolve (self,irc,prefix,channel=''):
        (nick,ident,host) = ircutils.splitHostmask(prefix)
        if ident.startswith('~'):
            ident = '*'
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.registryValue('resolverTimeout')
            resolver.lifetime = self.registryValue('resolverTimeout')
            ips = resolver.query(host,'A')
            L = []
            if ips:
                for ip in ips:
                    L.append(str(ip))
            if len(L) == 1:
                h = L[0]
                if ':' in h:
                    if h.startswith('2400:6180:') or h.startswith('2604:a880:') or h.startswith('2a03:b0c0:') or h.startswith('2001:0:53aa:64c:'):
                        h = '%s/116' % h
                    elif h.startswith('2600:3c01'):
                        h = '%s/124' % h
                    if not '/' in h:
                        a = h.split(':')
                        if len(a) > 4:
                            h = '%s:*' % ':'.join(a[:4])
                self.log.debug('%s is resolved as %s@%s' % (prefix,ident,h))
                self.cache[prefix] = '%s@%s' % (ident,h)
                if utils.net.isIPV4(h) and channel:
                    key = 'dig %s' % h
                    i = self.getIrc(irc)
                    if not key in i.pending:
                        i.pending[key] = True
                        self.dig(irc,channel,prefix)
            else:
                self.cache[prefix] = '%s@%s' % (ident,host)
        except:
            self.cache[prefix] = '%s@%s' % (ident,host)
        i = self.getIrc(irc)
        if prefix in i.resolving:
            del i.resolving[prefix]

    def prefixToMask (self,irc,prefix,channel=''):
        if prefix in self.cache:
            return self.cache[prefix]
        (nick,ident,host) = ircutils.splitHostmask(prefix)
        if '/' in host:
            if host.startswith('gateway/web/freenode'):
                if 'ip.' in host:
                    self.cache[prefix] = '*@%s' % host.split('ip.')[1]
                else:
                    # syn offline / busy
                    self.cache[prefix] = '%s@gateway/web/freenode/*' % ident
            elif host.startswith('gateway/tor-sasl'):
                self.cache[prefix] = '*@%s' % host
            elif host.startswith('gateway'):
                h = host.split('/')
                if 'ip.' in host:
                    ident = '*'
                    h = host.split('ip.')[1]
                elif '/vpn/' in host:
                    if 'x-' in host:
                        h = h[:3]
                        h = '%s/*' % '/'.join(h)
                    else:
                        h = host
                    if ident.startswith('~'):
                        ident = '*'
                elif len(h) > 3:
                    h = h[:3]
                    h = '%s/*' % '/'.join(h)
                else:
                    h = host
                self.cache[prefix] = '%s@%s' % (ident,h)
            elif host.startswith('nat'):
                h = host.split('/')
                h = h[:2]
                h = '%s/*' % '/'.join(h)
                self.cache[prefix] = '%s@%s' % (ident,host)
            else:
                if ident.startswith('~'):
                    ident = '*'
                self.cache[prefix] = '%s@%s' % (ident,host)
        else:
            if ident.startswith('~'):
                ident = '*'
            if utils.net.isIPV4(host):
                self.cache[prefix] = '%s@%s' % (ident,host)
            elif utils.net.bruteIsIPV6(host):
                h = host
                if h.startswith('2400:6180:') or h.startswith('2604:a880:') or h.startswith('2a03:b0c0:') or h.startswith('2001:0:53aa:64c:'):
                    h = '%s/116' % h
                elif h.startswith('2600:3c01'):
                    h = '%s/124' % h
                if not '/' in h:
                    a = h.split(':')
                    if len(a) > 4:
                        h = '%s:*' % ':'.join(a[:4])
                self.cache[prefix] = '%s@%s' % (ident,h)
            else:
                i = self.getIrc(irc)
                if not prefix in i.resolving:
                    i.resolving[prefix] = True
                    t = world.SupyThread(target=self.resolve,name=format('resolve %s', prefix),args=(irc,prefix,channel))
                    t.setDaemon(True)
                    t.start()
                return '%s@%s' % (ident,host)
        if prefix in self.cache:
            return self.cache[prefix]
        else:
            if ident.startswith('~'):
                ident = '*'
            return '%s@%s' % (ident,host)

    def do001 (self,irc,msg):
        i = self.getIrc(irc)
        if not i.opered:
            if len(self.registryValue('operatorNick')) and len(self.registryValue('operatorPassword')):
                irc.queueMsg(ircmsgs.IrcMsg('OPER %s %s' % (self.registryValue('operatorNick'),self.registryValue('operatorPassword'))))

    def do381 (self,irc,msg):
        i = self.getIrc(irc)
        if not i.opered:
            i.opered = True
            #MODE %s +s +bfC
            irc.queueMsg(ircmsgs.IrcMsg('MODE %s +p' % irc.nick))
            irc.queueMsg(ircmsgs.IrcMsg('MODE %s +s +bnf' % irc.nick))
            try:
                conf.supybot.protocols.irc.throttleTime.setValue(0.0)
            except:
                t = True

    def doMode (self,irc,msg):
        target = msg.args[0]
        if target == irc.nick:
            i = self.getIrc(irc)
            modes = ircutils.separateModes(msg.args[1:])
            for change in modes:
                (mode,value) = change
                if mode == '-o':
                    i.opered = False
                    if len(self.registryValue('operatorNick')) and len(self.registryValue('operatorPassword')):
                        irc.queueMsg(ircmsgs.IrcMsg('OPER %s %s' % (self.registryValue('operatorNick'),self.registryValue('operatorPassword'))))
        elif target in irc.state.channels and 'm' in irc.state.channels[target].modes:
            modes = ircutils.separateModes(msg.args[1:])
            for change in modes:
                (mode,value) = change
                if mode == '+v':
                    chan = self.getChan(irc,target)
                    if value in chan.nicks:
                        a = chan.nicks[value]
                        if len(a) == 5:
                            chan.nicks[msg.nick] = [time.time(),a[1],a[2],a[3],a[4]]
                        else:
                            chan.nicks[msg.nick] = [time.time(),a[1],a[2],'','']
                       

    def getIrc (self,irc):
        if not irc.network in self._ircs:
            self._ircs[irc.network] = Ircd(irc)
            self._ircs[irc.network].restore(self.getDb(irc.network))
            if len(self.registryValue('operatorNick')) and len(self.registryValue('operatorPassword')):
                irc.queueMsg(ircmsgs.IrcMsg('OPER %s %s' % (self.registryValue('operatorNick'),self.registryValue('operatorPassword'))))
        return self._ircs[irc.network]

    def doAccount (self,irc,msg):
        if ircutils.isUserHostmask(msg.prefix):
            nick = ircutils.nickFromHostmask(msg.prefix)
            acc = msg.args[0]
            if acc == '*':
                acc = None
            for channel in irc.state.channels:
                if irc.isChannel(channel):
                    chan = self.getChan(irc,channel)
                    if nick in chan.nicks:
                        a = chan.nicks[msg.nick]
                        if len(a) == 5:
                            chan.nicks[msg.nick] = [a[0],a[1],a[2],a[3],acc]
                        else:
                            chan.nicks[msg.nick] = [a[0],a[1],a[2],'',acc]

    def getChan (self,irc,channel):
        i = self.getIrc(irc)
        if not channel in i.channels:
            i.channels[channel] = Chan(channel)
        return i.channels[channel]

    def kill (self,irc,nick,reason=None):
        i = self.getIrc(irc)
        if i.defcon:
            i.defcon = time.time()
        if not self.registryValue('enable'):
            self.logChannel(irc,"INFO: disabled, can't kill %s" % nick)
            return
        if not i.opered:
            self.logChannel(irc,"INFO: not opered, can't kill %s" % nick)
            return
        if not reason:
            reason = self.registryValue('killMessage')
        irc.sendMsg(ircmsgs.IrcMsg('KILL %s :%s' % (nick,reason)))

    def do338 (self,irc,msg):
        i = self.getIrc(irc)
        if msg.args[0] == irc.nick and msg.args[1] in i.whowas:
            pending = i.whowas[msg.args[1]]
            del i.whowas[msg.args[1]]
            (nick,ident,host) = ircutils.splitHostmask(pending[0])
            # [prefix,mask,duration,reason,klineMessage]
            ident = pending[1].split('@')[0]
            mask = self.prefixToMask(irc,'%s!%s@%s' % (nick,ident,msg.args[2]))
            if not self.registryValue('enable'):
                self.logChannel(irc,"INFO: disabled, can't kline %s (%s)" % (mask,pending[3]))
                if pending[1] in i.klines:
                    del i.klines[pending[1]]
                return
            if not i.opered:
                self.logChannel(irc,"INFO: not opered, can't kline %s (%s)" % (mask,pending[3]))
                if pending[1] in i.klines:
                    del i.klines[pending[1]]
                return
            irc.sendMsg(ircmsgs.IrcMsg('KLINE %s %s :%s|%s' % (pending[2],mask,pending[4],pending[3])))
            if pending[1] in i.klines:
                del i.klines[pending[1]]

    def kline (self,irc,prefix,mask,duration,reason,klineMessage=None):
        i = self.getIrc(irc)
        if mask in i.klines:
            return
        if duration < 0:
            self.log.debug('Ignored kline %s due to no duration', mask)
            return
        if not klineMessage:
            klineMessage = self.registryValue('klineMessage')
        if '"' in klineMessage:
            klineMessage = self.registryValue('klineMessage')
        canKline = True
        i.klines[mask] = mask
        if '/' in mask:
            if '@gateway' in mask or '@nat' in mask:
                canKline = True
            else:
                # we must search ip behind cloak; user is already killed
                if ircutils.isUserHostmask(prefix):
                    # with pattern creation, we don't have nicks
                    canKline = False
                    (nick,ident,host) = ircutils.splitHostmask(prefix)
                    if not nick in i.whowas:
                        i.whowas[nick] = [prefix,mask,duration,reason,klineMessage]
                        irc.sendMsg(ircmsgs.IrcMsg('WHOWAS %s' % nick))
        if canKline:
            if not self.registryValue('enable'):
                self.logChannel(irc,"INFO: disabled, can't kline %s (%s)" % (mask,reason))
            else:
                irc.sendMsg(ircmsgs.IrcMsg('KLINE %s %s :%s|%s' % (duration,mask,klineMessage,reason)))
        def forgetKline ():
            i = self.getIrc(irc)
            if mask in i.klines:
                del i.klines[mask]
        schedule.addEvent(forgetKline,time.time()+7)

    def ban (self,irc,nick,prefix,mask,duration,reason,message,log,killReason=None):
        self.kill(irc,nick,killReason)
        self.kline(irc,prefix,mask,duration,reason,message)
        self.logChannel(irc,log)

    def getIrcQueueFor (self,irc,key,kind,life):
        i = self.getIrc(irc)
        if not key in i.queues:
            i.queues[key] = {}
        if not kind in i.queues[key]:
            i.queues[key][kind] = utils.structures.TimeoutQueue(life)
        elif i.queues[key][kind].timeout != life:
            i.queues[key][kind].setTimeout(life)
        return i.queues[key][kind]

    def rmIrcQueueFor (self,irc,key):
        i = self.getIrc(irc)
        if key in i.queues:
            for k in i.queues[key]:
                if type(i.queues[key][k]) == utils.structures.TimeoutQueue:
                    i.queues[key][k].reset()
                    i.queues[key][k].queue = None
            i.queues[key].clear()
            del i.queues[key]

    def handleReportMessage (self,irc,msg):
        (targets, text) = msg.args
        #if msg.nick.startswith(self.registryValue('reportNick')):
        nicks = self.registryValue('reportNicks')
        if msg.nick in nicks:
            i = self.getIrc(irc)
            if text.startswith('BAD:') and not '(tor' in text:
                permit = self.registryValue('reportPermit')
                if permit > -1:
                    life = self.registryValue('reportLife')
                    queue = self.getIrcQueueFor(irc,'report','bad',life)
                    queue.enqueue(text)
                    if len(queue) > permit:
                        queue.reset()
                        if not i.defcon:
                            self.logChannel(irc,"BOT: Wave in progress (%s/%ss), ignores lifted, triggers thresholds lowered for %ss at least" % (self.registryValue('reportPermit'),self.registryValue('reportLife'),self.registryValue('defcon'))) 
                        i.defcon = time.time()

    def tor (self,irc,ip):
        i = self.getIrc(irc)
        if utils.net.isIPV4(ip):
            ports = self.registryValue('torPorts')
            server = self.registryValue('torServer')
            target = self.registryValue('torTarget')
            ipr = '.'.join(ip.split('.')[::-1])
            targetr = '.'.join(target.split('.')[::-1])
            for port in ports:
                request = '%s.%s.%s.%s' % (ipr,port,targetr,server)
                try:
                    resolver = dns.resolver.Resolver()
                    resolver.timeout = self.registryValue('resolverTimeout')
                    resolver.lifetime = self.registryValue('resolverTimeout')
                    result = resolver.query(request,'A')
                    self.log.debug('%s : %s : %s' % (ip,request,str(result)))
                    if result:
                        for ip in result:
                            ip = str(ip)
                            if ip == '127.0.0.2':
                                self.log.debug('Tor : %s : %s is a tor exit node' % (request,ip))
                                i.tors[ip] = True
                                break
                    else:
                        if not ip in i.tors:
                            i.tors[ip] = False
                except:
                    if not ip in i.tors:
                        i.tors[ip] = False
                if ip in i.tors and i.tors[ip]:
                    break
        else:
            i.tors[ip] = False

    def handleSaslMessage (self,irc,msg):
        (targets, text) = msg.args
        if msg.nick == self.registryValue('saslNick') and self.registryValue('saslPermit') > -1:
            host = text.split('(')[1].replace(')','')
            if ircdb.checkIgnored('*!*@%s' % host,self.registryValue('saslChannel')):
                return
            uuid = text.split('SASL login failure by ')[1].split(' ')[0]
            queue = self.getIrcQueueFor(irc,'sasl',host,self.registryValue('saslLife'))
            stored = False
            # we are adding unique connexion id from a given host into the queue
            # to prevent the various fallback clients are using when they are trying to find the right way to id via sasl
            # some thunderbird tries 7 various way per connection
            # abuses are triggered by number of connection with sasl failure from a given host
            if len(queue):
                for uid in queue:
                    if uid == uuid:
                        stored = True
                        break
            if not stored:
                queue.enqueue(uuid)
            i = self.getIrc(irc)
            if not host in i.tors and utils.net.isIPV4(host):
                if len(self.registryValue('torPorts')) and len(self.registryValue('torServer')) and len(self.registryValue('torTarget')):
                    t = world.SupyThread(target=self.tor,name=format('tor %s for %s', host, uuid),args=(irc,host))
                    t.setDaemon(True)
                    t.start()
                else:
                    i.tors[host] = False
            if len(queue) > self.registryValue('saslPermit') or (host in i.tors and i.tors[host]):
                if not len(i.dline):
                    # if there is already a testline outside, we just keep the queue up
                    # it will be triggered at next try
                    queue.reset()
                    i.dline = host
                    irc.sendMsg(ircmsgs.IrcMsg('TESTLINE %s' % host))
                    def forget ():
                        i = self.getIrc(irc)
                        if i.dline == host:
                            i.dline = ''
                    schedule.addEvent(forget,time.time()+7)
            # removing empty queues, to save some memory
            removes = []
            for k in list(i.queues['sasl'].keys()):
                if not len(i.queues['sasl'][k]):
                    removes.append(k)
            for k in removes:
                del i.queues['sasl'][k]
                if k in i.tors:
                    del i.tors[k]
        if self.registryValue('saslPermit') < 0:
            self.rmIrcQueueFor(irc,'sasl')

    def do015 (self,irc,msg):
        try:
            (targets,text) = msg.args
            i = self.getIrc(irc)
            reg = r".*\s+([a-z]+)\.freenode\.net.*:\s+(\d{2,6})\s+"
            result = re.match(reg,text)
            if result:
                i.servers[result.group(1)] = int(result.group(2))
        except:
            self.log.debug('do015, a server gone')

    def do017 (self,irc,msg):
        found = None
        users = None
        i = self.getIrc(irc)
        for server in i.servers:
            if not users or users < i.servers[server]:
                found = server
                users = i.servers[server]
        server = None
        if found:
            i.servers = {}
            server = '%s.freenode.net' % found
            i.servers[server] = time.time()
            def bye():
                i = self.getIrc(irc)
                if server in i.servers:
                    del i.servers[server]
                    if not i.netsplit:
                        self.logChannel(irc,'INFO: netsplit activated for %ss due to %s/%ss of lags with %s : some abuses are ignored' % (self.registryValue('netsplitDuration'),self.registryValue('lagPermit'),self.registryValue('lagPermit'),server))
                    i.netsplit = time.time() + self.registryValue('netsplitDuration')
            schedule.addEvent(bye,time.time()+self.registryValue('lagPermit')+2)
            irc.queueMsg(ircmsgs.IrcMsg('TIME %s' % server))
        try:
            if server:
                resolver = dns.resolver.Resolver()
                resolver.timeout = self.registryValue('resolverTimeout')
                resolver.lifetime = self.registryValue('resolverTimeout')
                ips = resolver.query(server,'A')
                for ip in ips:
                    if utils.net.isIPV4(str(ip)):
                        conf.supybot.plugins.Sigyn.torTarget.setValue(str(ip))
                        break
        except:
            self.log.debug('do017 torTarget not updated')

    def cleanup (self,irc):
        i = self.getIrc(irc)
        kinds = []
        for kind in i.queues:
            count = 0
            ks = []
            for k in i.queues[kind]:
                if isinstance(i.queues[kind][k],utils.structures.TimeoutQueue):
                    if not len(i.queues[kind][k]):
                       ks.append(k)
                    else:
                       count += 1
                else:
                    count += 1
            if len(ks):
                for k in ks:
                    del i.queues[kind][k]
            if count == 0:
               kinds.append(kind)
        for kind in kinds:
            del i.queues[kind]
        chs = []
        for channel in i.channels:
            chan = i.channels[channel]
            ns = []
            for n in chan.nicks:
                if channel in irc.state.channels:
                    if not n in irc.state.channels[channel].users:
                        ns.append(n)
                else:
                    ns.append(n)
            for n in ns:
                del chan.nicks[n]
            bs = []
            for b in chan.buffers:
                 qs = []
                 count = 0
                 for q in chan.buffers[b]:
                     if isinstance(chan.buffers[b][q],utils.structures.TimeoutQueue):
                         if not len(chan.buffers[b][q]):
                            qs.append(q)
                         else:
                            count += 1
                     else:
                        count +=1 
                 for q in qs:
                     del chan.buffers[b][q]
                 if count == 0:
                     bs.append(b)
            for b in bs:
                del chan.buffers[b]
            logs = []
            if chan.logs:
                for log in chan.logs:
                    if not len(chan.logs[log]):
                        logs.append(log)
            for log in logs:
                del chan.logs[log]
            if len(ns) or len(bs) or len(logs):
                chs.append('[%s : %s nicks, %s buffers, %s logs]' % (channel,len(ns),len(bs),len(logs)))
        self.log.debug('cleanup,removed : %s queues, %s' % (len(kinds),', '.join(chs)))

    def do391 (self,irc,msg):
        i = self.getIrc(irc)
        if msg.prefix in i.servers:
            delay = time.time()-i.servers[msg.prefix]
            del i.servers[msg.prefix]
            if delay > self.registryValue('lagPermit'):
                if not i.netsplit:
                    self.logChannel(irc,'INFO: netsplit activated for %ss due to %s/%ss of lags with %s : some abuses are ignored' % (self.registryValue('netsplitDuration'),delay,self.registryValue('lagPermit'),msg.prefix))    
                i.netsplit = time.time() + self.registryValue('netsplitDuration')
     
    def do219 (self,irc,msg):
        i = self.getIrc(irc)
        r = []
        for k in i.stats:
            if i.stats[k] > self.registryValue('ghostPermit'):
                r.append(k.replace('[unknown@','').replace(']',''))
        for ip in r:
            irc.sendMsg(ircmsgs.IrcMsg('DLINE %s %s on * :%s' % (1440,ip,'Banned due to too many connections in a short period, email kline@freenode.net when corrected.')))
        i.stats = {}
        if len(r):
            self.logChannel(irc,'DOS: %s ip(s) %s' % (len(r),', '.join(r)))

    def do211 (self,irc,msg):
        i = self.getIrc(irc)
        if msg.args[1].startswith('[unknown@'):
            if msg.args[1] in i.stats:
                i.stats[msg.args[1]] = i.stats[msg.args[1]] + 1
            else:
                i.stats[msg.args[1]] = 0

    def handleMsg (self,irc,msg,isNotice):
        if not ircutils.isUserHostmask(msg.prefix):
            return
        if msg.prefix == irc.prefix:
            return
        (targets, text) = msg.args
        if ircmsgs.isAction(msg):
            text = ircmsgs.unAction(msg)
        raw = text
        text = text.lower()
        mask = self.prefixToMask(irc,msg.prefix)
        i = self.getIrc(irc)
        if not i.ping or time.time() - i.ping > self.registryValue('lagInterval'):
            i.ping = time.time()
            self.cleanup(irc)
            if self.registryValue('lagPermit') > -1:
                i.stats = {}
                if self.registryValue('ghostPermit') > -1:
                    irc.queueMsg(ircmsgs.IrcMsg('STATS L'))
                irc.queueMsg(ircmsgs.IrcMsg('MAP'))
        if i.defcon:
            if time.time() > i.defcon + self.registryValue('defcon'):
                i.defcon = False
                self.logChannel(irc,"INFO: triggers restored to normal behaviour")
        if i.efnet:
            if time.time() > i.efnet:
                i.efnet = False
                self.logChannel(irc,"INFO: efnet users are no longer klined on join")
        if i.netsplit:
            if time.time() > i.netsplit:
                i.netsplit = False
                self.logChannel(irc,"INFO: netsplit mode deactivated")
        if self.registryValue('saslChannel'):
            if i.netsplit:
                if self.registryValue('saslChannel') in irc.state.channels:
                    irc.queueMsg(ircmsgs.part(self.registryValue('saslChannel')))
            else:
                if not self.registryValue('saslChannel') in irc.state.channels:
                    irc.queueMsg(ircmsgs.join(self.registryValue('saslChannel')))
        if mask in i.klines:
            self.log.debug('Ignoring %s (%s) - kline in progress', msg.prefix,mask)
            return
        isBanned = False
        for channel in targets.split(','):
            # handle CPRIVMSG
            if channel.startswith('@'):
                channel = channel.replace('@','')
            if channel.startswith('+'):
                channel = channel.replace('+','')
            if irc.isChannel(channel) and channel in irc.state.channels:
                if self.registryValue('reportChannel') == channel:
                    self.handleReportMessage(irc,msg)
                if self.registryValue('saslChannel') == channel:
                    self.handleSaslMessage(irc,msg)
                if self.registryValue('ignoreChannel',channel):
                    continue
                if ircdb.checkCapability(msg.prefix, 'protected'):
                    continue
                chan = self.getChan(irc,channel)
                if chan.called:
                    if time.time() - chan.called > self.registryValue('abuseDuration',channel=channel):
                        chan.called = False
                        self.logChannel(irc,'INFO: [%s] returns to regular state' % channel)
                elif irc.nick in raw or '!ops' in raw:
                    if not chan.called:
                        self.logChannel(irc,'INFO: [%s] ignores lifted, limits lowered (by %s) for %ss' % (channel,msg.nick,self.registryValue('abuseDuration',channel=channel)))
                        chan.called = time.time()
                if isBanned:
                    continue
                if msg.nick in list(irc.state.channels[channel].ops):
                    continue
                protected = ircdb.makeChannelCapability(channel, 'protected')
                if ircdb.checkCapability(msg.prefix, protected):
                    continue
                killReason = self.registryValue('killMessage',channel=channel)
                for k in i.patterns:
                    pattern = i.patterns[k]
                    if pattern.match(raw):
                        if pattern.limit == 0:
                            isBanned = True
                            reason = 'matchs #%s in %s' % (pattern.uid,channel)
                            log = 'BAD: [%s] %s (matchs #%s) -> %s' % (channel,msg.prefix,pattern.uid,mask)
                            self.ban(irc,msg.nick,msg.prefix,mask,self.registryValue('klineDuration'),reason,self.registryValue('klineMessage'),log,killReason)
                            i.count(self.getDb(irc.network),pattern.uid)
                            break
                        else:
                            queue = self.getIrcQueueFor(irc,mask,pattern.uid,pattern.life)
                            queue.enqueue(text)
                            if len(queue) > pattern.limit:
                                isBanned = True
                                reason = 'matchs #%s (%s/%ss) in %s' % (pattern.uid,pattern.limit,pattern.life,channel)
                                log = 'BAD: [%s] %s (matchs #%s %s/%ss) -> %s' % (channel,msg.prefix,pattern.uid,pattern.limit,pattern.life,mask)
                                self.ban(irc,msg.nick,msg.prefix,mask,self.registryValue('klineDuration'),reason,self.registryValue('klineMessage'),log,killReason)
                                self.rmIrcQueueFor(irc,mask)
                                i.count(self.getDb(irc.network),pattern.uid)
                                break
                            i.count(self.getDb(irc.network),pattern.uid)
                if isBanned:
                    continue
                ignoreDuration = self.registryValue('ignoreDuration',channel=channel)
                if not msg.nick in chan.nicks:
                    t = time.time()
                    if isCloaked(msg.prefix):
                        t = t - ignoreDuration - 1
                    chan.nicks[msg.nick] = [t,msg.prefix,mask]
                isIgnored = False
                if ignoreDuration > 0:
                    ts = chan.nicks[msg.nick][0]
                    if time.time()-ts > ignoreDuration:
                        # TODO previously we do not ignore on chan.called or i.defcon
                        # could be 'not (chan.called or i.defcon)'
                        isIgnored = True
                reason = ''
                if chan.patterns:
                    for pattern in chan.patterns:
                        if pattern in text:
                            reason = 'matchs tmp pattern in %s' % channel
                            # redo duration
                            chan.patterns.enqueue(pattern)
                            break
                # channel detections
                massrepeat = False
                flag = ircdb.makeChannelCapability(channel, 'massRepeat')
                if ircdb.checkCapability(msg.prefix, flag):
                    massrepeat = self.isChannelMassRepeat(irc,msg,channel,mask,text)
                    if massrepeat and self.hasAbuseOnChannel(irc,channel,'massRepeat'):
                        isIgnored = False
                lowmassrepeat = False
                flag = ircdb.makeChannelCapability(channel, 'lowMassRepeat')
                if ircdb.checkCapability(msg.prefix, flag):
                    lowmassrepeat = self.isChannelLowMassRepeat(irc,msg,channel,mask,text)
                    if lowmassrepeat and self.hasAbuseOnChannel(irc,channel,'lowMassRepeat'):
                        isIgnored = False
                repeat = False
                flag = ircdb.makeChannelCapability(channel, 'repeat')
                if ircdb.checkCapability(msg.prefix, flag):
                    repeat = self.isChannelRepeat(irc,msg,channel,mask,text)
                    if repeat and self.hasAbuseOnChannel(irc,channel,'repeat'):
                        isIgnored = False
                lowrepeat = False
                flag = ircdb.makeChannelCapability(channel, 'lowRepeat')
                if ircdb.checkCapability(msg.prefix, flag):
                    lowrepeat = self.isChannelLowRepeat(irc,msg,channel,mask,text)
                    if lowrepeat and self.hasAbuseOnChannel(irc,channel,'lowRepeat'):
                        isIgnored = False
                hilight = False
                flag = ircdb.makeChannelCapability(channel, 'hilight')
                if ircdb.checkCapability(msg.prefix, flag):
                    hilight = self.isChannelHilight(irc,msg,channel,mask,text)
                    if hilight and self.hasAbuseOnChannel(irc,channel,'hilight'):
                        isIgnored = False
                lowhilight = False
                flag = ircdb.makeChannelCapability(channel, 'lowHilight')
                if ircdb.checkCapability(msg.prefix, flag):
                    lowhilight = self.isChannelLowHilight(irc,msg,channel,mask,text)
                    if lowhilight and self.hasAbuseOnChannel(irc,channel,'lowHilight'):
                        isIgnored = False
                flood = False
                flag = ircdb.makeChannelCapability(channel, 'flood')
                if ircdb.checkCapability(msg.prefix, flag):
                    flood = self.isChannelFlood(irc,msg,channel,mask,text)
                    if flood and self.hasAbuseOnChannel(irc,channel,'flood'):
                        isIgnored = False
                lowflood = False
                flag = ircdb.makeChannelCapability(channel, 'lowFlood')
                if ircdb.checkCapability(msg.prefix, flag):
                    lowflood = self.isChannelLowFlood(irc,msg,channel,mask,text)
                    if lowflood and self.hasAbuseOnChannel(irc,channel,'lowFlood'):
                        isIgnored = False
                ctcp = False
                flag = ircdb.makeChannelCapability(channel, 'ctcp')
                if ircdb.checkCapability(msg.prefix, flag):
                    if not ircmsgs.isAction(msg) and (ircmsgs.isCtcp(msg) or isNotice):
                        ctcp = self.isChannelCtcp(irc,msg,channel,mask,text)
                    if ctcp and self.hasAbuseOnChannel(irc,channel,'ctcp'):
                        isIgnored = False
                if not reason:
                    if massrepeat:
                        reason = massrepeat
                    elif lowmassrepeat:
                        reason = lowmassrepeat
                    elif repeat:
                        reason = repeat
                    elif lowrepeat:
                        reason = lowrepeat
                    elif hilight:
                        reason = hilight
                    elif lowhilight:
                        reason = lowhilight
                    elif flood:
                        reason = flood
                    elif lowflood:
                        reason = lowflood
                    elif ctcp:
                        reason = ctcp
                if reason:
                    if chan.called:
                        isIgnored = False
                    if isIgnored:
                        bypassIgnore = self.isBadOnChannel(irc,channel,'bypassIgnore',mask)
                        if bypassIgnore:
                            isBanned = True
                            reason = '%s %s' % (reason,bypassIgnore)
                            log = 'BAD: [%s] %s (%s) -> %s' % (channel,msg.prefix,reason,mask)
                            self.ban(irc,msg.nick,msg.prefix,mask,self.registryValue('klineDuration'),reason,self.registryValue('klineMessage'),log,killReason)
                        else:
                            self.logChannel(irc,'IGNORED: [%s] %s (%s)' % (channel,msg.prefix,reason))
                    else:
                        isBanned = True
                        log = 'BAD: [%s] %s (%s) -> %s' % (channel,msg.prefix,reason,mask)
                        self.ban(irc,msg.nick,msg.prefix,mask,self.registryValue('klineDuration'),reason,self.registryValue('klineMessage'),log,killReason)
                        ip = mask.split('@')[1]
                        if hilight and i.defcon and utils.net.isIPV4(ip):
                            if len(self.registryValue('droneblKey')) and len(self.registryValue('droneblHost')) and self.registryValue('enable'):
                                self.log.debug('filling dronebl with %s' % ip)
                                t = world.SupyThread(target=fillDnsbl,name=format('fillDnsbl %s', ip),args=(ip,self.registryValue('droneblHost'),self.registryValue('droneblKey')))
                                t.setDaemon(True)
                                t.start()

                if not isBanned:
                    # todo re-implement amsg detection
                    mini = self.registryValue('amsgMinium')
                    if len(text) > mini:
                        limit = self.registryValue('amsgPermit')
                        if limit > -1:
                            life = self.registryValue('amsgLife')
                            percent = self.registryValue('amsgPercent')
                            queue = self.getIrcQueueFor(irc,mask,channel,life)
                            queue.enqueue(text)
                            found = None
                            for ch in i.channels:
                                chc = self.getChan(irc,ch)
                                if msg.nick in chc.nicks and ch != channel:
                                    queue = self.getIrcQueueFor(irc,mask,ch,life)
                                    for m in queue:
                                        if compareString(m,text) > percent:
                                            found = ch
                                            break
                                    if found:
                                        break
                            if found:
                                queue = self.getIrcQueueFor(irc,mask,'amsg',life)
                                flag = False
                                for q in queue:
                                    if found in q:
                                        flag = True
                                        break
                                if not flag:
                                    queue.enqueue(found)
                                if len(queue) > limit:
                                    chs = list(queue)
                                    queue.reset()
                                    key = 'amsg %s' % mask
                                    if not key in i.queues:
                                        chs.append(channel)
                                        self.logChannel(irc,'AMSG: %s (%s) in %s' % (msg.nick,text,', '.join(chs)))
                                        def rc():
                                            i = self.getIrc(irc)
                                            if key in i.queues:
                                                del i.queues[key]
                                        schedule.addEvent(rc,time.time()+self.registryValue('alertPeriod'))
                                        i.queues[key] = time.time()

    def doPrivmsg (self,irc,msg):
        self.handleMsg(irc,msg,False)

    def do903 (self,irc,msg):
        irc.queueMsg(ircmsgs.IrcMsg('CAP REQ :extended-join account-notify'))

    def do215 (self,irc,msg):
        i = self.getIrc(irc)
        if msg.args[0] == irc.nick and msg.args[1] == 'I' and msg.args[2] == 'NOMATCH':
            if len(i.dline):
                duration = self.registryValue('saslDuration')
                if self.registryValue('saslChannel') in irc.state.channels:
                    if self.registryValue('enable'):
                        irc.sendMsg(ircmsgs.IrcMsg('DLINE %s %s on * :%s' % (duration,i.dline,self.registryValue('saslReason'))))
                        tor = ''
                        if i.dline in i.tors and i.tors[i.dline]:
                            tor = '(TOR)'
                    irc.queueMsg(ircmsgs.privmsg(self.registryValue('saslChannel'),'DLINED %s for %sm : SASL Brute Force %s/%ss %s' % (i.dline,duration,self.registryValue('saslPermit'),self.registryValue('saslLife'),tor)))
        else:
                if self.registryValue('saslChannel') in irc.state.channels:
                    irc.queueMsg(ircmsgs.privmsg(self.registryValue('saslChannel'),'IGNORED %s due to iline (%s)' % (i.dline,msg.args[2])))
        i.dline = ''

    def do726 (self,irc,msg):
        # other ircd
        i = self.getIrc(irc)
        if msg.args[0] == irc.nick and msg.args[1].strip() == i.dline.strip() and msg.args[2].strip() == 'No matches':
             duration = self.registryValue('saslDuration')
             if self.registryValue('saslChannel') in irc.state.channels:
                 if self.registryValue('enable'):
                    irc.sendMsg(ircmsgs.IrcMsg('DLINE %s %s on * :%s' % (duration,i.dline,self.registryValue('saslReason'))))
                 tor = ''
                 if i.dline in i.tors and i.tors[i.dline]:
                     tor = '(TOR)'
                 irc.queueMsg(ircmsgs.privmsg(self.registryValue('saslChannel'),'DLINED %s for %sm : SASL Brute Force %s/%ss %s' % (i.dline,duration,self.registryValue('saslPermit'),self.registryValue('saslLife'),tor)))
        i.dline = ''

    def do723 (self,irc,msg):
        # not enough rights for dline
        (targets, text) = msg.args
        if len(targets):
            if targets[0] == irc.nick and targets[1] == 'remoteban':
                if self.registryValue('saslChannel') in irc.state.channels:
                    irc.queueMsg(ircmsgs.privmsg(self.registryValue('saslChannel'),text))

    def handleFloodSnote (self,irc,text):
        user = text.split('Possible Flooder ')[1]
        a = user[::-1]
        ar = a.split(']',1)
        ar.reverse()
        ar.pop()
        user = "%s" % ar[0]
        user = user.replace('[','!',1)
        user = '%s' % user[::-1]
        if not ircutils.isUserHostmask(user):
            return
        target = text.split('target: ')[1]
        i = self.getIrc(irc)
        if irc.isChannel(target):
            # channel being flooded by someone
            limit = self.registryValue('channelFloodPermit')
            life = self.registryValue('channelFloodLife')
            key = 'snoteFloodAlerted'
            if limit > -1:
                if not self.registryValue('ignoreChannel',target):
                    protected = ircdb.makeChannelCapability(target, 'protected')
                    if not ircdb.checkCapability(user, protected):
                        queue = self.getIrcQueueFor(irc,target,'snoteFlood',life)
                        # we are looking for notices from various users who targets a channel
                        stored = False
                        for u in queue:
                            if u == user:
                                stored = True
                                break
                        if not stored:
                            queue.enqueue(user)
                        users = list(queue)
                        if len(queue) > limit:
                            queue.reset()
                            if not key in i.queues[target]:
                                self.logChannel(irc,'NOTE: [%s] is flooded by %s' % (target,', '.join(users)))
                                i.queues[target][key] = time.time() + self.registryValue('alertPeriod')
                                def rc():
                                    i = self.getIrc(irc)
                                    if target in i.queues:
                                        if key in i.queues[target]:
                                            del i.queues[target][key]
                                i.queues[target][key] = time.time()
                                schedule.addEvent(rc,time.time()+self.registryValue('alertPeriod'))
                            else:
                                def rkc():
                                    i = self.getIrc(irc)
                                    if target in i.queues:
                                        if 'kline' in i.queues[target]:
                                            del i.queues[target]['kline']
                                i.queues[target]['kline'] = True
                                schedule.addEvent(rkc,time.time()+self.registryValue('alertPeriod'))
#                        if 'kline' in i.queues[target]:
#                                for u in users:
#                                    umask = self.prefixToMask(irc,u)
                                    #self.kill(irc,u.split('!')[0],u)
                                    #self.kline(irc,u,umask,self.registryValue('klineDuration'),'snote flood on %s' % target)
#                                    self.logChannel(irc,"NOTE: %s (snote flood on %s) -> %s" % (u,target,umask))
        else:
            # nick being flood by someone
            limit = self.registryValue('userFloodPermit')
            life = self.registryValue('userFloodLife')
            if limit > -1:
                queue = self.getIrcQueueFor(irc,target,'snoteFlood',life)
                stored = False
                for u in queue:
                    if u == user:
                        stored = True
                        break
                if not stored:
                    queue.enqueue(user)
                users = list(queue)
                if len(queue) > limit:
                    queue.reset()
                    key = 'snoteFloodAlerted'
                    if not key in i.queues[target]:
                        self.logChannel(irc,'NOTE: %s is flooded by %s' % (target,', '.join(users)))
                        def ru():
                            i = self.getIrc(irc)
                            if target in i.queues:
                                if key in i.queues[target]:
                                    del i.queues[target][key]
                        i.queues[target][key] = time.time()
                        schedule.addEvent(ru,time.time()+self.registryValue('alertPeriod'))
                    else:
                        def rku():
                            i = self.getIrc(irc)
                            if target in i.queues:
                                if 'kline' in i.queues[target]:
                                    del i.queues[target]['kline']
                        i.queues[target]['kline'] = True
                        schedule.addEvent(rku,time.time()+self.registryValue('alertPeriod'))
                if 'kline' in i.queues[target]:
                        for u in users:
                            umask = self.prefixToMask(irc,u)
                            self.kline(irc,u,umask,self.registryValue('klineDuration'),'snote flood on %s' % target)
                            self.logChannel(irc,"BAD: %s (snote flood on %s) -> %s" % (u,target,umask))

    def handleJoinSnote (self,irc,text):
        limit = self.registryValue('joinRatePermit')
        life = self.registryValue('joinRateLife')
        target = text.split('trying to join ')[1].split(' is')[0]
        if self.registryValue('ignoreChannel',target):
            return
        user = text.split('User ')[1].split(')')[0]
        user = user.replace('(','!').replace(')','').replace(' ','')
        mask = self.prefixToMask(irc,user)
        if not ircutils.isUserHostmask(user):
            return
        protected = ircdb.makeChannelCapability(target, 'protected')
        if ircdb.checkCapability(user, protected):
            return
        queue = self.getIrcQueueFor(irc,user,'snoteJoin',life)
        stored = False
        for u in queue:
            if u == user:
                stored = True
                break
        if not stored:
            queue.enqueue(user)
        i = self.getIrc(irc)
        key = 'snoteJoinAlerted'
        if len(queue) > limit and limit > 0:
            users = list(queue)
            queue.reset()
            if not key in i.queues[target]:
                self.logChannel(irc,'NOTE: [%s] join/part by %s' % (target,', '.join(users)))
                def rc():
                    i = self.getIrc(irc)
                    if target in i.queues:
                        if key in i.queues[target]:
                            del i.queues[target][key]
                i.queues[target][key] = time.time()
                schedule.addEvent(rc,time.time()+self.registryValue('alertPeriod'))
        life = self.registryValue('crawlLife')
        limit = self.registryValue('crawlPermit')
        queue = self.getIrcQueueFor(irc,mask,'snoteJoin',life)
        stored = False
        for u in queue:
            if u == target:
                stored = True
                break
        if not stored:
            queue.enqueue(target)
        self.log.debug('%s : %s : %s : %s : %s' % (user,mask,len(queue),life,limit)) 
        if len(queue) > limit and limit > 0:
            channels = list(queue)
#            if not i.defcon:
            queue.reset()
            if not key in i.queues[mask]:
                self.logChannel(irc,'NOTE: %s is crawling freenode (%s)' % (user,', '.join(channels)))
                def rc():
                    i = self.getIrc(irc)
                    if mask in i.queues:
                        if key in i.queues[mask]:
                            del i.queues[mask][key]
                i.queues[mask][key] = time.time()
                schedule.addEvent(rc,time.time()+self.registryValue('alertPeriod')*2)
            else:
                self.kline(irc,user,mask,self.registryValue('klineDuration'),'crawling')
                self.logChannel(irc,"BAD: %s (crawling) -> %s" % (user,mask))

    def handleIdSnote (self,irc,text):
        target = text.split('failed login attempts to ')[1].split('.')[0].strip()
        user = text.split('Last attempt received from ')[1].split(' on')[0].strip()
        if not ircutils.isUserHostmask(user):
            return
        if user.split('!')[0].lower() == target.lower():
            return
        limit = self.registryValue('idPermit')
        life = self.registryValue('idLife')
        if limit < 0:
            return
        # user send nickserv's id
        queue = self.getIrcQueueFor(irc,user,'snoteId',life)
        queue.enqueue(target)
        i = self.getIrc(irc)
        targets = []
        key = 'snoteIdAlerted'
        if len(queue) > limit:
            targets = list(queue)
            queue.reset()
            if not key in i.queues[user]:
                def rcu():
                    i = self.getIrc(irc)
                    if user in i.queues:
                        if key in i.queues[user]:
                            del i.queues[user][key]
                i.queues[user][key] = time.time()
                schedule.addEvent(rcu,time.time()+self.registryValue('abuseLife'))
        if key in i.queues[user]:
            if len(queue):
                targets = list(queue)
                queue.reset()
            a = []
            for t in targets:
                if not t in a:
                    a.append(t)
            mask = self.prefixToMask(irc,user)
            (nick,ident,host) = ircutils.splitHostmask(user)
            if not mask in i.klines:
                #self.kill(irc,nick,user)
                self.kline(irc,user,mask,self.registryValue('klineDuration'),'ns id flood (%s)' % ', '.join(a))
                self.logChannel(irc,"BAD: %s (ns id flood %s) -> %s" % (user,', '.join(a),mask))
                if i.defcon and utils.net.isIPV4(mask.split('@')[1]):
                    if len(self.registryValue('droneblKey')) and len(self.registryValue('droneblHost')) and self.registryValue('enable'):
                        self.log.debug('filling dronebl with %s' % mask.split('@')[1])
                        t = world.SupyThread(target=fillDnsbl,name=format('fillDnsbl %s', mask.split('@')[1]),args=(mask.split('@')[1],self.registryValue('droneblHost'),self.registryValue('droneblKey')))
                        t.setDaemon(True)
                        t.start()
        # user receive nickserv's id
        queue = self.getIrcQueueFor(irc,target,'snoteId',life)
        queue.enqueue(user)
        targets = []
        if len(queue) > limit:
            targets = list(queue)
            queue.reset()
            def rct():
                i = self.getIrc(irc)
                if target in i.queues:
                    if key in i.queues[target]:
                        del i.queues[target][key]
            i.queues[target][key] = time.time()
            schedule.addEvent(rct,time.time()+self.registryValue('abuseLife'))
        if key in i.queues[target]:
            if len(queue):
                targets = list(queue)
                queue.reset() 
            a = {}
            for t in targets:
                if not t in a:
                    a[t] = t
            for u in a:
                mask = self.prefixToMask(irc,u)
                (nick,ident,host) = ircutils.splitHostmask(u)
                if not mask in i.klines:
                    #self.kill(irc,nick,u)
                    self.kline(irc,u,mask,self.registryValue('klineDuration'),'ns id flood on %s' % target)
                    self.logChannel(irc,"BAD: %s (ns id flood on %s) -> %s" % (u,target,mask))
                    if i.defcon and utils.net.isIPV4(mask.split('@')[1]):
                        if len(self.registryValue('droneblKey')) and len(self.registryValue('droneblHost')) and self.registryValue('enable'):
                            self.log.debug('filling dronebl with %s' % mask.split('@')[1])
                            t = world.SupyThread(target=fillDnsbl,name=format('fillDnsbl %s', mask.split('@')[1]),args=(mask.split('@')[1],self.registryValue('droneblHost'),self.registryValue('droneblKey')))
                            t.setDaemon(True)
                            t.start()

    def handleKline(self,irc,text):
        if self.registryValue('alertOnWideKline') > -1:
            i = self.getIrc(irc)
            user = text.split('active for')[1]
            a = user[::-1]
            ar = a.split(']',1)
            ar.reverse()
            ar.pop()
            user = "%s" % ar[0]
            user = user.replace('[','!',1)
            user = '%s' % user[::-1]
            user = user.strip()
            if not ircutils.isUserHostmask(user):
                return
            (nick,ident,host) = ircutils.splitHostmask(user)
            # avoid resolve here 
            #mask = self.prefixToMask(irc,user)
            #mask = '*@%s' % mask.split('@')[1]
            nicks = self.getIrcQueueFor(irc,'nickKlineNote','nickKlineNote',50)
            nicks.enqueue(ident)
            nickPattern = ''
            nickCurrent = ''
            for n in nicks:
                if n != ident:
                    nickCurrent = largestString(n,ident)
                if len(nickCurrent) > len(nickPattern):
                    nickPattern = nickCurrent
            if len(nicks) > 10 and len(nickPattern) > 4:
                nicks.reset()
                self.log.debug('HANDLEKLINE %s : %s' % (user,nickPattern))
            mask = '*@%s' % host
            queue = self.getIrcQueueFor(irc,mask,'klineNote',7)
            queue.enqueue(user)
            key = 'wideKlineAlert'
            if len(queue) > self.registryValue('alertOnWideKline'):
                queue.reset()
                if not key in i.queues[mask]:
                    self.logChannel(irc,"NOTE: a kline similar to %s seems to hit more than %s users" % (mask,self.registryValue('alertOnWideKline')))
                    i.queues[mask][key] = time.time()
            def rct():
                i = self.getIrc(irc)
                if mask in i.queues:
                    if key in i.queues[mask]:
                        del i.queues[mask][key]
                self.rmIrcQueueFor(irc,mask)
            schedule.addEvent(rct,time.time()+8)

    def handleClientCon (self,irc,text):
        i = self.getIrc(irc)
        a = text.split(' ')
        if len(a) > 4 and utils.net.isIPV4(a[4]):
            key = 'dig %s' % a[4]
            prefix = '%s!%s@%s' % (a[1],a[2],a[3])
            if not '/' in a[3]:
                if a[2].startswith('~'):
                    a[2] = '*'
                self.cache[prefix] = '%s@%s' % (a[2],a[4])
                if not key in i.pending and not i.netsplit:
                    i.pending[key] = True
                    channel = self.registryValue('logChannel')
                    channels = [channel]
                    #if a[4] in i.dnv:
                        #self.logChannel(irc,'BOT: [%s] %s ( %s )' % (channel,prefix,i.dnv[a[4]]))
                    t = world.SupyThread(target=self.dig,name=format('Dig %s for %s',prefix, ','.join(channels)),args=(irc,channel,prefix))
                    t.setDaemon(True)
                    t.start()

    def handleNickSnote (self,irc,text):
        text = text.replace('Nick change: From ','')
        text = text.split(' to ')[1]
        nick = text.split(' ')[0]
        host = text.split(' ')[1]
        host = host.replace('[','',1)
        host = host[:-1]
        limit = self.registryValue('nickChangePermit')
        life = self.registryValue('nickChangeLife')
        if limit < 0:
            return
        mask = self.prefixToMask(irc,'%s!%s' % (nick,host))
        #self.kline(irc,u,umask,self.registryValue('klineDuration'),'snote flood on %s' % target)
        #self.logChannel(irc,"BAD: %s (snote flood on %s) -> %s" % (u,target,umask))
        i = self.getIrc(irc)
        if not i.defcon:
            return
        queue = self.getIrcQueueFor(irc,mask,'snoteNick',life)
        queue.enqueue(nick)
        if len(queue) > limit:
            nicks = list(queue)
            queue.reset()
            self.kline(irc,'%s!%s' % (nick,host),mask,self.registryValue('klineDuration'),'nick changes abuses %s/%ss' % (limit,life))
            self.logChannel(irc,"BAD: %s abuses nick change (%s) -> %s" % (mask,','.join(nicks),mask))
            
    def doNotice (self,irc,msg):
        (targets, text) = msg.args
        if len(targets) and targets[0] == '*':
            # server notices
            text = text.replace('\x02','')
            if text.startswith('*** Notice -- '):
                text = text.replace('*** Notice -- ','')
            if text.startswith('Possible Flooder '):
                self.handleFloodSnote(irc,text)
            elif text.startswith('Nick change: From'):
                self.handleNickSnote(irc,text)
            elif text.startswith('User') and text.endswith('is a possible spambot'):
                self.handleJoinSnote(irc,text)
            elif 'failed login attempts to' in text and not '<sasl>' in text:
                self.handleIdSnote(irc,text)
            elif text.startswith('Too many clients, rejecting ') or text.startswith('All connections in use.') or text.startswith('creating SSL/TLS socket pairs: 24 (Too many open files)'):
                i = self.getIrc(irc)
                if not msg.prefix in i.limits or time.time() - i.limits[msg.prefix] > self.registryValue('alertPeriod'):
                    i.limits[msg.prefix] = time.time()
                    self.logChannel(irc,'INFRA: %s is rejecting clients' % msg.prefix.split('.')[0])
                if not i.netsplit:
                    self.logChannel(irc,'INFO: netsplit activated for %ss : some abuses are ignored' % self.registryValue('netsplitDuration'))
                i.netsplit = time.time() + self.registryValue('netsplitDuration')
            elif text.startswith('KLINE active') or text.startswith('K/DLINE active'):
                self.handleKline(irc,text)
            elif text.startswith('CLICONN'):
                self.handleClientCon(irc,text)
        else:
            self.handleMsg(irc,msg,True)

    def hasAbuseOnChannel (self,irc,channel,key):
        chan = self.getChan(irc,channel)
        kind = 'abuse'
        limit = self.registryValue('%sPermit' % kind,channel=channel)
        if kind in chan.buffers:
            if key in chan.buffers[kind]:
                if len(chan.buffers[kind][key]) > limit:
                    return True
        return False

    def isAbuseOnChannel (self,irc,channel,key,mask):
        chan = self.getChan(irc,channel)
        kind = 'abuse'
        limit = self.registryValue('%sPermit' % kind,channel=channel)
        if limit < 0:
            return False
        life = self.registryValue('%sLife' % kind,channel=channel)
        if not kind in chan.buffers:
            chan.buffers[kind] = {}
        if not key in chan.buffers[kind]:
            chan.buffers[kind][key] = utils.structures.TimeoutQueue(life)
        elif chan.buffers[kind][key].timeout != life:
            chan.buffers[kind][key].setTimeout(life)
        found = False
        for m in chan.buffers[kind][key]:
            if mask == m:
                found = True
                break
        if not found:
            chan.buffers[kind][key].enqueue(mask)
        if len(chan.buffers[kind][key]) > limit:
            self.log.debug('abuse in %s : %s : %s/%s' % (channel,key,len(chan.buffers[kind][key]),limit))
            # chan.buffers[kind][key].reset()
            # queue not reseted, that way during life, it returns True
            if not chan.called:
                self.logChannel(irc,"INFO: [%s] ignores lifted, limits lowered due to %s abuses for %ss" % (channel,key,self.registryValue('abuseDuration',channel=channel))) 
            chan.called = time.time()
            return True
        return False

    def isBadOnChannel (self,irc,channel,kind,key):
        chan = self.getChan(irc,channel)
        limit = self.registryValue('%sPermit' % kind,channel=channel)
        if limit < 0:
            return False
        i = self.getIrc(irc)
        if i.netsplit:
            kinds = ['flood','lowFlood','nick','lowRepeat','lowMassRepeat','broken']
            if kind in kinds:
                return False
        life = self.registryValue('%sLife' % kind,channel=channel)
        if limit == 0:
            return '%s %s/%ss in %s' % (kind,limit,life,channel)
        if not kind in chan.buffers:
            chan.buffers[kind] = {}
        newUser = False
        if not key in chan.buffers[kind]:
            newUser = True
            chan.buffers[kind][key] = utils.structures.TimeoutQueue(life)
            chan.buffers[kind]['%s-creation' % key] = time.time()
        elif chan.buffers[kind][key].timeout != life:
            chan.buffers[kind][key].setTimeout(life)
        ignore = self.registryValue('ignoreDuration',channel=channel)
        if ignore > 0:
           if time.time() - chan.buffers[kind]['%s-creation' % key] < ignore:
               newUser = True
        chan.buffers[kind][key].enqueue(key)
        if newUser or i.defcon or self.hasAbuseOnChannel(irc,channel,kind) or chan.called:
            limit = limit - 1
            if limit < 0:
                limit = 0
        if len(chan.buffers[kind][key]) > limit:
            chan.buffers[kind][key].reset()
            if not kind == 'broken':
                self.isAbuseOnChannel(irc,channel,kind,key)
            return '%s %s/%ss in %s' % (kind,limit,life,channel)
        return False

    def isChannelCtcp (self,irc,msg,channel,mask,text):
        return self.isBadOnChannel(irc,channel,'ctcp',mask)

    def isChannelLowFlood (self,irc,msg,channel,mask,text):
        return self.isBadOnChannel(irc,channel,'lowFlood',mask)

    def isChannelFlood (self,irc,msg,channel,mask,text):
        if len(text) == 0 or len(text) > self.registryValue('floodMinimum',channel=channel) or text.isdigit():
            return self.isBadOnChannel(irc,channel,'flood',mask)
        return False

    def isChannelHilight (self,irc,msg,channel,mask,text):
        return self.isHilight(irc,msg,channel,mask,text,False)

    def isChannelLowHilight (self,irc,msg,channel,mask,text):
        return self.isHilight(irc,msg,channel,mask,text,True)

    def isHilight (self,irc,msg,channel,mask,text,low):
        kind = 'hilight'
        if low:
            kind = 'lowHilight'
        limit = self.registryValue('%sNick' % kind,channel=channel)
        if limit < 0:
            return False
        count = 0
        users = []
        if channel in irc.state.channels and irc.isChannel(channel):
            for u in list(irc.state.channels[channel].users):
                if u == 'ChanServ' or u == msg.nick:
                    continue
                users.append(u.lower())
        flag = False
        us = {}
        for user in users:
            if len(user) > 2:
                if not user in us and user in text:
                    us[user] = True
                    count = count + 1
                    if count > limit:
                        flag = True
                        break
        result = False
        if flag:
            result = self.isBadOnChannel(irc,channel,kind,mask)
        return result

    def isChannelRepeat (self,irc,msg,channel,mask,text):
        return self.isRepeat(irc,msg,channel,mask,text,False)

    def isChannelLowRepeat (self,irc,msg,channel,mask,text):
        return self.isRepeat(irc,msg,channel,mask,text,True)

    def isRepeat(self,irc,msg,channel,mask,text,low):
        kind = 'repeat'
        key = mask
        if low:
            kind = 'lowRepeat'
            key = 'low_repeat %s' % mask
        limit = self.registryValue('%sPermit' % kind,channel=channel)
        if limit < 0:
            return False
        if low:
            if len(text) < self.registryValue('%sMinimum' % kind,channel=channel):
                return False
        chan = self.getChan(irc,channel)
        life = self.registryValue('%sLife'  % kind,channel=channel)
        trigger = self.registryValue('%sPercent' % kind,channel=channel)
        if not key in chan.logs:
            chan.logs[key] = utils.structures.TimeoutQueue(life)
        elif chan.logs[key].timeout != life:
            chan.logs[key].setTimeout(life)
        logs = chan.logs[key]
        flag = False
        result = False
        for m in logs:
            if compareString(m,text) > trigger:
                flag = True
                break
        if flag:
            result = self.isBadOnChannel(irc,channel,kind,mask)
        enough = False
        if flag:
            if kind in chan.buffers and key in chan.buffers[kind]:
                if len(chan.buffers[kind][key])/(limit * 1.0) > 0.66:
                    enough = True
        if enough:
            life = self.registryValue('computedPatternLife',channel=channel)
            if not chan.patterns:
                chan.patterns = utils.structures.TimeoutQueue(life)
            elif chan.patterns.timeout != life:
                chan.patterns.setTimeout(life)
            if len(text) > self.registryValue('computedPattern',channel=channel):
                repeats = list(repetitions(text))
                candidate = ''
                patterns = {}
                for repeat in repeats:
                    (p,c) = repeat
                    if p in patterns:
                        patterns[p] += c
                    else:
                        patterns[p] = c
                    p = p.strip()
                    if len(p) > self.registryValue('computedPattern',channel=channel):
                        if len(p) > len(candidate):
                            candidate = p
                    elif len(p) > self.registryValue('computedPattern',channel=channel) and patterns[p] > self.registryValue('%sCount' % kind,channel=channel):
                        if len(p) > len(candidate):
                            candidate = p
                    elif len(p) * c > self.registryValue('computedPattern',channel=channel):
                        tentative = p * c
                        if not tentative in text:
                            tentative = (p + ' ') * c
                            if not tentative in text:
                                tentative = ''
                        if len(tentative):
                            tentative = tentative[:self.registryValue('computedPattern',channel=channel)]
                        if len(tentative) > len(candidate):
                            candidate = tentative
                if len(candidate):
                    found = False
                    for p in chan.patterns:
                        if p in candidate:
                            found = True
                            break
                    if not found:
                        candidate = candidate.strip()
                        shareID = self.registryValue('shareComputedPatternID',channel=channel)
                        if shareID != -1:
                            nb = 0
                            i = self.getIrc(irc)
                            for chan in i.channels:                                
                                ch = i.channels[chan]
                                life = self.registryValue('computedPatternLife',channel=chan)
                                if shareID != self.registryValue('shareComputedPatternID',channel=chan):
                                    continue                                                                                                                                                                 
                                if not ch.patterns:                                                                                                                                                                                                            
                                    ch.patterns = utils.structures.TimeoutQueue(life)                                                                                                                                                                          
                                elif ch.patterns.timeout != life:                                                                                                                                                                                              
                                    ch.patterns.setTimeout(life)                                                                                                                                                                                               
                                if len(candidate) > self.registryValue('computedPattern',channel=chan):
                                    ch.patterns.enqueue(candidate)
                                    nb = nb + 1                                
                            self.logChannel(irc,'PATTERN: [%s] added "%s" in %s channels' % (channel,candidate,nb,kind))
                        else:
                            chan.patterns.enqueue(candidate)
                            self.logChannel(irc,'PATTERN: [%s] added "%s" for %ss (%s)' % (channel,candidate,self.registryValue('computedPatternLife',channel=channel),kind))
                        # maybe, instead of awaiting for others repeated messages before kline, we could return
                        # and remove others users which matchs ..
                        # return 'repeat pattern creation'
        logs.enqueue(text)
        return result

    def isChannelMassRepeat (self,irc,msg,channel,mask,text):
        return self.isMassRepeat(irc,msg,channel,mask,text,False)

    def isChannelLowMassRepeat (self,irc,msg,channel,mask,text):
        return self.isMassRepeat(irc,msg,channel,mask,text,True)

    def isMassRepeat (self,irc,msg,channel,mask,text,low):
        kind = 'massRepeat'
        key = 'mass Repeat'
        if low:
            kind = 'lowMassRepeat'
            key = 'low mass Repeat'
        limit = self.registryValue('%sPermit' % kind,channel=channel)
        if limit < 0:
            return False
        if len(text) < self.registryValue('%sMinimum' % kind,channel=channel):
            return False
        chan = self.getChan(irc,channel)
        life = self.registryValue('%sLife' % kind,channel=channel)
        trigger = self.registryValue('%sPercent' % kind,channel=channel)
        length = self.registryValue('computedPattern',channel=channel)
        if not key in chan.logs:
            chan.logs[key] = utils.structures.TimeoutQueue(life)
        elif chan.logs[key].timeout != life:
            chan.logs[key].setTimeout(life)
        flag = False
        result = False
        pattern = None
        s = ''
        logs = chan.logs[key]
        for m in logs:
            found = compareString(m,text)
            if found > trigger:
                if length > 0:
                    pattern = largestString(m,text)
                    if len(pattern) < length:
                        pattern = None
                    else:
                        if len(s) > len(pattern):
                            pattern = s
                        s = pattern
                flag = True
                break
        if flag:
            result = self.isBadOnChannel(irc,channel,kind,channel)
            if result and pattern:
                life = self.registryValue('computedPatternLife',channel=channel)
                if not chan.patterns:
                    chan.patterns = utils.structures.TimeoutQueue(life)
                elif chan.patterns.timeout != life:
                    chan.patterns.setTimeout(life)
                if len(pattern) > self.registryValue('computedPattern',channel=channel):
                    pattern = pattern[:-1]
                    found = False
                    for p in chan.patterns:
                        if p in pattern:
                            found = True
                            break
                    if not found:
                        pattern = pattern.strip()
                        users = {}
                        users[mask] = True
                        for u in chan.logs:
                            user = 'n!%s' % u
                            if not u in users and ircutils.isUserHostmask(user):
                                for m in chan.logs[u]:
                                    if pattern in m:
                                        # todo, recover nick ..
                                        prefix = u
                                        if isCloaked(user):
                                            nick = None
                                            for n in chan.nicks:
                                                if chan.nicks[n][2] == u:
                                                    nick = n
                                                    break
                                            if nick:
                                                prefix = '%s!%s' % (nick,u)
                                        self.kline(irc,prefix,u,self.registryValue('klineDuration'),'pattern creation in %s (%s)' % (channel,kind))
                                        self.logChannel(irc,"BAD: [%s] %s (pattern creation - %s)" % (channel,u,kind))
                                        break
                            users[u] = True
                        shareID = self.registryValue('shareComputedPatternID',channel=channel)
                        if shareID != -1:
                            nb = 0
                            i = self.getIrc(irc)
                            for chan in i.channels:
                                ch = i.channels[chan]
                                if shareID != self.registryValue('shareComputedPatternID',channel=chan):
                                    continue                                              
                                life = self.registryValue('computedPatternLife',channel=chan)
                                if not ch.patterns:
                                    ch.patterns = utils.structures.TimeoutQueue(life)
                                elif ch.patterns.timeout != life:
                                    ch.patterns.setTimeout(life)
                                if len(pattern) > self.registryValue('computedPattern',channel=chan):                                                                                                                                
                                    ch.patterns.enqueue(pattern)
                                    nb = nb + 1                                                                                                                                                                                              
                            self.logChannel(irc,'PATTERN: [%s] added "%s" in %s channels (%s)' % (channel,pattern,nb,kind))                            
                        else:
                            chan.patterns.enqueue(pattern)
                            self.logChannel(irc,'PATTERN: [%s] added "%s" for %ss (%s)' % (channel,pattern,self.registryValue('computedPatternLife',channel=channel),kind))
                            
        logs.enqueue(text)
        if result and pattern:
            return result
        return False

    def logChannel(self,irc,message):
        channel = self.registryValue('logChannel')
        i = self.getIrc(irc)
        if channel in irc.state.channels:
            msg = ircmsgs.privmsg(channel,message)
            if self.registryValue('useNotice'):
                msg = ircmsgs.notice(channel,message)
            life = self.registryValue('announceLife')
            limit = self.registryValue('announcePermit')
            if limit > 0:    
                q = self.getIrcQueueFor(irc,'status','announce',life)
                q.enqueue(message)
                if len(q) > limit:
                    if not i.throttled:
                        i.throttled = True
                        irc.queueMsg(ircmsgs.privmsg(channel,'NOTE: messages throttled to avoid spam for %ss' % life))
                    self.log.info('throttled %s' % message)
                else:
                    i.throttled = False
                    if i.opered:
                        irc.sendMsg(msg)
                    else:
                        irc.queueMsg(msg)
            else:
                if i.opered:
                    irc.sendMsg(msg)
                else:
                    irc.queueMsg(msg)

    def dig (self,irc,channel,prefix):
        # this method is called in threads to avoid to lock the bot during calls
        i = self.getIrc(irc)
        mask = self.prefixToMask(irc,prefix)
        ip = mask.split('@')[1]
        h = '.'.join(ip.split('.')[::-1])
        h = h + '.rbl.efnetrbl.org.'
        m = None
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.registryValue('resolverTimeout')
            resolver.lifetime = self.registryValue('resolverTimeout')
            resolver.nameservers = ['208.67.222.222','208.67.220.220']
            m = resolver.query(h,'A')
        except:
           m = None
        message = None
        if m:
            for entry in m:
                entry = str(entry)
                if entry == '127.0.0.1':
                    message = 'Open Proxy'
                    break
                elif entry == '127.0.0.2' or entry == '127.0.0.3':
                    message = 'Virus'
                    break
                elif entry == '127.0.0.5':
                    message = 'Drone/Irc bot'
                    break
        self.log.debug('%s (%s) efnetrbl : %s' % (prefix,ip,message))
        if message:
            if not ip in i.digs:
                i.digs[ip] = message
                duration = self.registryValue('efnetDuration',channel=channel)
                if self.isBadOnChannel(irc,channel,'efnet',channel):
                    if not i.efnet:
                        self.logChannel(irc,"INFO: klining efnet's users for %ss because joins in %s" % (duration,channel))
                    i.efnet = time.time()+duration
                if i.efnet:
                    i.efnet = time.time()+duration
                if i.efnet or i.defcon:
                    log = 'BAD: [%s] %s (%s - EFNET) -> %s' % (channel,prefix,message,mask)
                    (nick,ident,host) = ircutils.splitHostmask(prefix)
                    if self.registryValue('logChannel') == channel:
                        self.kline(irc,prefix,mask,self.registryValue('klineDuration'),'efnet')
                    else:
                        self.ban(irc,nick,prefix,mask,self.registryValue('klineDuration'),'efnet',self.registryValue('klineMessage'),log)
                    if len(self.registryValue('droneblKey')) and len(self.registryValue('droneblHost')) and self.registryValue('enable'):
                        self.log.debug('filling dronebl with %s' % ip)
                        t = world.SupyThread(target=fillDnsbl,name=format('fillDnsbl %s', ip),args=(ip,self.registryValue('droneblHost'),self.registryValue('droneblKey')))
                        t.setDaemon(True)
                        t.start()
                else:
                    if '#freenode' in irc.state.channels and 'm' in irc.state.channels['#freenode'].modes and prefix.split('!')[0] in irc.state.channels['#freenode'].users:
                        if 'eir' in irc.state.channels['#freenode'].ops:
                            match = '*!*@%s' % prefix.split('@')[1]
                            irc.queueMsg(ircmsgs.privmsg('eir','add %s %s %s' % (match,self.registryValue('eirDuration'),message)))
                    self.logChannel(irc,"EFNET: [%s] %s (%s)" % (channel,prefix,message))
        else:
            chan = self.getChan(irc,channel)
            if chan.called or self.isAbuseOnChannel(irc,channel,'efnet',channel):
                h = '.'.join(ip.split('.')[::-1])
                h = h + '.xbl.spamhaus.org.'
                m = None         
                message = None                                                                                                                                                                                                                    
                try:                                                                                                                                                                                                                                 
                    resolver = dns.resolver.Resolver()                                                                                                                                                                                               
                    resolver.timeout = self.registryValue('resolverTimeout')                                                                                                                                                                         
                    resolver.lifetime = self.registryValue('resolverTimeout')
                    resolver.nameservers = ['208.67.222.222','208.67.220.220']                                                                                                                                                                        
                    m = resolver.query(h,'A')                                                                                                                                                                                                        
                except:                                                                                                                                                                                                                              
                    m = None
                if m:
                    for entry in m:
                        entry = str(entry)                                                                                                                                                                                                           
                        if entry == '127.0.0.2':
                            message = 'SBL'                                                                                                                                                                                                   
                            break
                        elif entry == '127.0.0.3':                                                                                                                                                                           
                            message = 'SBLCSS'                                                                                                                                                                                                        
                            break               
                        elif entry == '127.0.0.4' or entry == '127.0.0.5' or entry == '127.0.0.6' or entry == '127.0.0.7':                                                                                                                                                                                                     
                            message = 'CBL'
                            break          
                        elif entry == '127.0.0.10' or entry == '127.0.0.11':
                            message = 'PBL'
                            break
                i.digs[ip] = message
                if message:
                    log = 'BAD: [%s] %s (%s - SPAMHAUS) -> %s' % (channel,prefix,message,mask)
                    (nick,ident,host) = ircutils.splitHostmask(prefix)
                    self.ban(irc,nick,prefix,mask,self.registryValue('klineDuration'),'%s - Spamhaus' % message,self.registryValue('klineMessage'),log)
                self.log.debug('%s (%s) spamhaus : %s' % (prefix,ip,message))
            else:
                i.digs[ip] = False
        key = 'dig %s' % ip
        if key in i.pending:
            del i.pending[key]
        def rd():
            i = self.getIrc(irc)
            if ip in i.digs:
                del i.digs[ip]
        schedule.addEvent(rd,time.time()+self.registryValue('efnetDuration',channel=channel))

    def doJoin (self,irc,msg):
        if irc.prefix == msg.prefix:
            i = self.getIrc(irc)
            return
        channels = msg.args[0].split(',')
        if not ircutils.isUserHostmask(msg.prefix):
            return
        if ircdb.checkCapability(msg.prefix, 'protected'):
            return
        i = self.getIrc(irc)
        prefix = msg.prefix
        gecos = None
        account = None
        if len(msg.args) == 3:
            gecos = msg.args[2]
            account = msg.args[1]
            if account == '*':
                account = None
        for channel in channels:
            if ircutils.isChannel(channel) and channel in irc.state.channels:
                if self.registryValue('ignoreChannel',channel):
                    continue
                chan = self.getChan(irc,channel)
                t = time.time()
                mask = self.prefixToMask(irc,msg.prefix,channel)
                if isCloaked(msg.prefix):
                    t = t - self.registryValue('ignoreDuration',channel=channel) - 1
                chan.nicks[msg.nick] = [t,msg.prefix,mask,gecos,account]
                if i.netsplit:
                    continue
                protected = ircdb.makeChannelCapability(channel, 'protected')
                if ircdb.checkCapability(prefix, protected):
                    continue
                ip = mask.split('@')[1]
                if utils.net.isIPV4(ip):
                    if ip in i.dnv:
                        if channel == '#freenode' and msg.nick in irc.state.channels[channel].users and 'm' in irc.state.channels[channel].modes and 'eir' in irc.state.channels[channel].ops:
                            self.logChannel(irc,'DNV: [%s] %s ( %s )' % (channel,prefix,i.dnv[ip]))
                            match = '*!*@%s' % msg.prefix.split('@')[1]
                            irc.queueMsg(ircmsgs.privmsg('eir','add %s %s %s' % (match,self.registryValue('eirDuration'),i.dnv[ip])))
                        else:
                            self.logChannel(irc,'BOT: [%s] %s ( %s )' % (channel,prefix,i.dnv[ip]))
                    if ip in i.digs:
                        if i.digs[ip]:
                            if (i.efnet or i.defcon):
                                log = 'BAD: [%s] %s (%s - EFNET) -> %s' % (channel,prefix,i.digs[ip],mask)
                                self.ban(irc,msg.nick,prefix,mask,self.registryValue('klineDuration'),'efnet',self.registryValue('klineMessage'),log)
                            else:
                                if channel == '#freenode' and msg.nick in irc.state.channels[channel].users and 'm' in irc.state.channels[channel].modes and 'eir' in irc.state.channels[channel].ops:
                                    match = '*!*@%s' % msg.prefix.split('@')[1]
                                    irc.queueMsg(ircmsgs.privmsg('eir','add %s %s %s' % (match,self.registryValue('eirDuration'),i.digs[ip])))
                    else:
                        key = 'dig %s' % ip
                        if not key in i.pending:
                            i.pending[key] = True
                            t = world.SupyThread(target=self.dig,name=format('Dig %s for %s', msg.prefix, ','.join(channels)),args=(irc,channel,msg.prefix))
                            t.setDaemon(True)
                            t.start()

    def doPart (self,irc,msg):
        channels = msg.args[0].split(',')
        i = self.getIrc(irc)
        if not ircutils.isUserHostmask(msg.prefix):
            return
        if msg.prefix == irc.prefix:
            for channel in channels:
                if ircutils.isChannel(channel):
                    if channel in i.channels:
                        del i.channels[channel]
            return
        mask = self.prefixToMask(irc,msg.prefix)
        isBanned = False
        reason = ''
        if len(msg.args) == 2:
            reason = msg.args[1].lstrip().rstrip()
        for channel in channels:
            if ircutils.isChannel(channel) and channel in irc.state.channels and not isBanned:
                chan = self.getChan(irc,channel)
                if msg.nick in chan.nicks:
                    if self.registryValue('ignoreChannel',channel):
                        continue
                    protected = ircdb.makeChannelCapability(channel, 'protected')
                    if ircdb.checkCapability(msg.prefix, protected):
                        continue
                    bad = False
                    flag = ircdb.makeChannelCapability(channel, 'cycle')
                    if ircdb.checkCapability(msg.prefix, flag):
                        bad = self.isBadOnChannel(irc,channel,'cycle',mask)
                    if bad:
                        isBanned = True
                        log = "BAD: [%s] %s (join/part) -> %s" % (channel,msg.prefix,mask)
                        comment = 'join/part flood in %s' % channel
                        self.ban(irc,msg.nick,msg.prefix,mask,self.registryValue('klineDuration'),comment,self.registryValue('klineMessage'),log)
                    if len(reason):
                        bad = self.isChannelMassRepeat(irc,msg,channel,mask,reason)
                        if bad:
                            # todo, needs to see more on that one to avoid false positive
                            #self.kill(irc,msg.nick,msg.prefix)
                            #self.kline(irc,msg.prefix,mask,self.registryValue('klineDuration'),'%s in %s' % (bad,channel))
                            self.logChannel(irc,"IGNORED: [%s] %s (Part's message %s) : %s" % (channel,msg.prefix,bad,reason))

    def doKick (self,irc,msg):
        channel = target = reason = None
        if len(msg.args) == 3:
            (channel,target,reason) = msg.args
        else:
            (channel,target) = msg.args
            reason = ''
        i = self.getIrc(irc)
        if target == irc.nick:
            if channel in i.channels:
                del i.channels[channel]

    def doQuit (self,irc,msg):
        if msg.prefix == irc.prefix:
            return
        reason = ''
        if len(msg.args) == 1:
            reason = msg.args[0].lstrip().rstrip()
        i = self.getIrc(irc)
        if reason == '*.net *.split':
            # TODO use i.netsplit for server's lags too, with another duration
            if not i.netsplit:
                self.logChannel(irc,'INFO: netsplit activated for %ss : some abuses are ignored' % self.registryValue('netsplitDuration'))
            i.netsplit = time.time() + self.registryValue('netsplitDuration')
        mask = self.prefixToMask(irc,msg.prefix)
        isBanned = False
        (nick,ident,host) = ircutils.splitHostmask(msg.prefix)
        for channel in irc.state.channels:
            if ircutils.isChannel(channel):
               chan = self.getChan(irc,channel)
               if msg.nick in chan.nicks:
                    if self.registryValue('ignoreChannel',channel):
                        continue
                    protected = ircdb.makeChannelCapability(channel, 'protected')
                    if ircdb.checkCapability(msg.prefix, protected):
                        continue
                    bad = False
                    flag = ircdb.makeChannelCapability(channel, 'broken')
                    if ircdb.checkCapability(msg.prefix, flag):
                        bad = self.isBadOnChannel(irc,channel,'broken',mask)
                    if isBanned:
                        continue
                    if bad and not i.netsplit:
                        self.kline(irc,msg.prefix,mask,self.registryValue('brokenDuration'),'%s in %s' % ('join/quit flood',channel),self.registryValue('brokenReason') % self.registryValue('brokenDuration'))
                        self.logChannel(irc,'BAD: [%s] %s (%s) -> %s' % (channel,msg.prefix,'broken client',mask))
                        isBanned = True
                        continue
                    # to work, the bot must CAP REQ extended-join
                    hosts = self.registryValue('brokenHost',channel=channel)
                    reasons = ['Read error: Connection reset by peer','Client Quit','Excess Flood','Max SendQ exceeded','Remote host closed the connection']
                    if 'broken' in chan.buffers and mask in chan.buffers['broken'] and len(chan.buffers['broken'][mask]) > 1 and reason in reasons and len(hosts):
                        found = False
                        for h in hosts:
                            if len(h):
                                if h.isdigit() and host.startswith(h):
                                    found = True
                                    break
                                if h in host:
                                    found = True
                                    break
                        if found and len(chan.nicks[msg.nick]) == 5:
                            gecos = chan.nicks[msg.nick][3]
                            account = chan.nicks[msg.nick][4]
                            if not account and gecos == msg.nick and gecos in ident and len(msg.nick) < 6:
                                isBanned = True
                                self.kline(irc,msg.prefix,mask,self.registryValue('brokenDuration')*4,'%s in %s' % ('join/quit flood',channel),self.registryValue('brokenReason') % (self.registryValue('brokenDuration')*4))
                                self.logChannel(irc,'BAD: [%s] %s (%s) -> %s' % (channel,msg.prefix,'broken bottish client',mask))

    def doNick (self,irc,msg):
        oldNick = msg.prefix.split('!')[0]
        newNick = msg.args[0]
        if oldNick == irc.nick or newNick == irc.nick:
            return
        newPrefix = '%s!%s' % (newNick,msg.prefix.split('!')[1])
        mask = self.prefixToMask(irc,newPrefix)
        i = self.getIrc(irc)
        isBanned = False
        for channel in irc.state.channels:
            if ircutils.isChannel(channel):
                if self.registryValue('ignoreChannel',channel):
                    continue
                protected = ircdb.makeChannelCapability(channel, 'protected')
                if ircdb.checkCapability(newPrefix, protected):
                    continue
                chan = self.getChan(irc,channel)
                if oldNick in chan.nicks:
                    chan.nicks[newNick] = chan.nicks[oldNick]
                    if not newNick.startswith('Guest'):
                        if not isBanned:
                            reason = False
                            flag = ircdb.makeChannelCapability(channel, 'nick')
                            if ircdb.checkCapability(msg.prefix, flag):
                                reason = self.isBadOnChannel(irc,channel,'nick',mask)
                            hasBeenIgnored = False
                            ignore = self.registryValue('ignoreDuration',channel=channel)
                            if ignore > 0:
                                ts = chan.nicks[newNick][0]
                                if time.time()-ts > ignore:
                                    hasBeenIgnored = True
                            if not isCloaked(msg.prefix):
                                if i.defcon or chan.called:
                                    hasBeenIgnored = False
                            if not reason and i.defcon and self.hasAbuseOnChannel(irc,channel,'nick'):
                                reason = 'nick changes, due to abuses'
                            if reason:
                                if hasBeenIgnored:
                                    bypass = self.isBadOnChannel(irc,channel,'bypassIgnore',mask)
                                    if bypass:
                                        comment = '%s %s' % (reason,bypass)
                                        log = 'BAD: [%s] %s (%s) -> %s' % (channel,newPrefix,comment,mask)
                                        self.ban(irc,newNick,newPrefix,mask,self.registryValue('klineDuration'),comment,self.registryValue('klineMessage'),log)
                                        isBanned = True
                                    else:
                                        self.logChannel(irc,'IGNORED: [%s] %s (%s)' % (channel,newPrefix,reason))
                                else:
                                    log = 'BAD: [%s] %s (%s) -> %s' % (channel,newPrefix,reason,mask)
                                    self.ban(irc,newNick,newPrefix,mask,self.registryValue('klineDuration'),reason,self.registryValue('klineMessage'),log)
                                    isBanned = True
                    del chan.nicks[oldNick]

    def reset(self):
        self._ircs = ircutils.IrcDict()

    def die(self):
        self.log.debug('die() called')
        self.cache = utils.structures.CacheDict(100)
        try:
            conf.supybot.protocols.irc.throttleTime.setValue(1.6)
        except:
            self.log.debug('error while trying to change throttleTime')
        self._ircs = ircutils.IrcDict()

    def doError (self,irc,msg):
        self._ircs = ircutils.IrcDict()

    def makeDb(self, filename):
        """Create a database and connect to it."""
        if os.path.exists(filename):
            db = sqlite3.connect(filename,timeout=10)
            db.text_factory = str
            return db
        db = sqlite3.connect(filename)
        db.text_factory = str
        c = db.cursor()
        c.execute("""CREATE TABLE patterns (
                id INTEGER PRIMARY KEY,
                pattern VARCHAR(512) NOT NULL,
                regexp INTEGER,
                mini INTEGER,
                life INTEGER,
                operator VARCHAR(512) NOT NULL,
                comment VARCHAR(512),
                triggered INTEGER,
                at TIMESTAMP NOT NULL,
                removed_at TIMESTAMP,
                removed_by VARCHAR(512)
                )""")
        db.commit()
        c.close()
        return db

    def getDb(self, irc):
        """Use this to get a database for a specific irc."""
        currentThread = threading.currentThread()
        if irc not in self.dbCache and currentThread == world.mainThread:
            self.dbCache[irc] = self.makeDb(self.makeFilename(irc))
        if currentThread != world.mainThread:
            db = self.makeDb(self.makeFilename(irc))
        else:
            db = self.dbCache[irc]
        db.isolation_level = None
        return db

Class = Sigyn
