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

"""
Allows 'aliases' for other commands.
"""

from baseplugin import *

import re
import sets

import conf
import debug
import utils
import privmsgs
import callbacks

def configure(onStart, afterConnect, advanced):
    # This will be called by setup.py to configure this module.  onStart and
    # afterConnect are both lists.  Append to onStart the commands you would
    # like to be run when the bot is started; append to afterConnect the
    # commands you would like to be run when the bot has finished connecting.
    from questions import expect, anything, something, yn
    onStart.append('load Alias')

example = utils.wrapLines("""
<jemfinch> @list Alias
<supybot> jemfinch: advogato, alias, debplanet, devshed, freeze, gnome, googlebsd, googlelinux, googlemac, k5, kde, kt, lambda, linuxmag, lj, lwn, nyttech, osnews, pypi, python, slashdot, unalias, unfreeze
<jemfinch> (just pay attention to the freeze/unfreeze and alias/unalias)
<jemfinch> @alias rot26 "rot13 [rot13 $1]"
<supybot> jemfinch: The operation succeeded.
<jemfinch> @rot26 jemfinch
<supybot> jemfinch: jemfinch
<jemfinch> @unalias rot26
<supybot> jemfinch: The operation succeeded.
<jemfinch> @rot26 jemfinch
<jemfinch> (look, Ma!  No rot26!)
<Cerlyn> ooohh
<jemfinch> @alias rot26 "rot13 [rot13 $1]"
<supybot> jemfinch: The operation succeeded.
<jemfinch> @freeze rot26
<supybot> jemfinch: The operation succeeded.
<jemfinch> (now's your queue :))
<Cerlyn> @unalias rot26
<supybot> Cerlyn: Error: That alias is frozen.
<Cerlyn> @unalias rot26nothere
<supybot> Cerlyn: Error: There is no such alias.
<Cerlyn> @unfreeze rot26
<supybot> Cerlyn: Error: You don't have the "admin" capability.
<jemfinch> @unfreeze rot26
<supybot> jemfinch: The operation succeeded.
<jemfinch> (now try to remove it :))
<Cerlyn> @unalias rot26
<supybot> Cerlyn: The operation succeeded.
<jemfinch> @rot26 blah blah blah
<jemfinch> @help slashdot
<supybot> jemfinch: slashdot <an alias, None arguments> (for more help use the morehelp command)
<jemfinch> hehe...I should fix that.
<jemfinch> @morehelp slashdot
""")

class RecursiveAlias(Exception):
    pass

def findAliasCommand(s, alias):
    r = re.compile(r'(^|\[)\s*%s' % re.escape(s))
    return bool(r.search(alias))

dollarRe = re.compile(r'\$(\d+)')
def findBiggestDollar(alias):
    dollars = dollarRe.findall(alias)
    dollars = map(int, dollars)
    dollars.sort()
    if dollars:
        return dollars[-1]
    else:
        return None

def makeNewAlias(name, alias):
    if findAliasCommand(name, alias):
        raise RecursiveAlias
    doChannel = '$channel' in alias
    biggestDollar = findBiggestDollar(alias)
    doDollars = bool(biggestDollar)
    if biggestDollar is not None:
        biggestDollar = int(biggestDollar)
    def f(self, irc, msg, args):
        alias_ = alias
        if doChannel:
            channel = privmsgs.getChannel(msg, args)
            alias_ = alias.replace('$channel', channel)
        if doDollars:
            args = privmsgs.getArgs(args, needed=biggestDollar)
            if biggestDollar == 1:
                args = (args,)
            def replace(m):
                idx = int(m.group(1))
                return args[idx-1]
            alias_ = dollarRe.sub(replace, alias_)
        self.Proxy(irc.irc, msg, callbacks.tokenize(alias_))
    f.__doc__ ='<an alias, %s %s>\n\nAlias for %r' % \
                (biggestDollar,
                 utils.pluralize(biggestDollar, 'argument'),
                 alias)
    #f = new.function(f.func_code, f.func_globals, name)
    return f


class Alias(callbacks.Privmsg):
    def __init__(self):
        callbacks.Privmsg.__init__(self)
        self.frozen = sets.Set()

    def freeze(self, irc, msg, args):
        """<alias>

        'Freezes' an alias so that no one else can change it.
        """
        name = privmsgs.getArgs(args)
        name = callbacks.canonicalName(name)
        if hasattr(self, name) and self.isCommand(name):
            self.frozen.add(name)
            irc.reply(msg, conf.replySuccess)
        else:
            irc.error(msg, 'There is no such alias.')
    freeze = privmsgs.checkCapability(freeze, 'admin')

    def unfreeze(self, irc, msg, args):
        """<alias>

        'Unfreezes' an alias so that people can define new aliases over it.
        """
        name = privmsgs.getArgs(args)
        name = callbacks.canonicalName(name)
        if hasattr(self, name) and self.isCommand(name):
            self.frozen.discard(name)
            irc.reply(msg, conf.replySuccess)
        else:
            irc.error(msg, 'There is no such alias.')
    unfreeze = privmsgs.checkCapability(unfreeze, 'admin')

    def alias(self, irc, msg, args):
        """<name> <alias commands>

        Defines an alias <name> for the commands <commands>.  The <commands>
        should be in the standard [command argument [nestedcommand argument]]
        format.  Underscores can be used to represent arguments to the alias
        itself; for instance ...
        """
        (name, alias) = privmsgs.getArgs(args, needed=2)
        realName = callbacks.canonicalName(name)
        if name != realName:
            irc.error(msg, 'That name isn\'t valid.  Try %r instead.' %\
                realName)
            return
        else:
            name = realName
        cb = irc.findCallback(name)
        if cb is not None and cb != self:
            irc.error(msg, 'A command with that name already exists.')
            return
        if name in self.frozen:
            irc.error(msg, 'That alias is frozen.')
            return
        try:
            f = makeNewAlias(name, alias)
        except RecursiveAlias:
            irc.error(msg, 'You can\'t define a recursive alias.')
            return
        setattr(self.__class__, name, f)
        irc.reply(msg, conf.replySuccess)


    def unalias(self, irc, msg, args):
        """<name>

        Removes the given alias, if unfrozen.
        """
        name = privmsgs.getArgs(args)
        name = callbacks.canonicalName(name)
        if hasattr(self, name) and self.isCommand(name):
            if name not in self.frozen:
                delattr(self.__class__, name)
                irc.reply(msg, conf.replySuccess)
            else:
                irc.error(msg, 'That alias is frozen.')
        else:
            irc.error(msg, 'There is no such alias.')




Class = Alias

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
