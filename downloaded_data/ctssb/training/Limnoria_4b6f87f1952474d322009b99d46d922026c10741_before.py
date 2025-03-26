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
Provides fun/useless commands that require threads.

Commands include:
  dns
  kernel
"""

from baseplugin import *

import socket
import telnetlib

import ircutils
import privmsgs
import callbacks

class ThreadedFunCommands(callbacks.Privmsg):
    threaded = True
    def dns(self, irc, msg, args):
        """<host|ip>"""
        host = privmsgs.getArgs(args)
        if ircutils.isIP(host):
            hostname = socket.getfqdn(host)
            if hostname == host:
                irc.error(msg, 'Host not found.')
            else:
                irc.reply(msg, hostname)
        else:
            try:
                ip = socket.gethostbyname(host)
                irc.reply(msg, ip)
            except socket.error:
                irc.error(msg, 'Host not found.')

    def kernel(self, irc, msg, args):
        """takes no arguments"""
        conn = telnetlib.Telnet('kernel.org', 79)
        conn.write('\n')
        text = connection.read_all()
        for line in text.splitlines():
            (name, version) = line.split(':')
            if name.find('latest stable') != -1:
                stable = version.strip()
            elif name.find('latest beta') != -1:
                beta = version.strip()
        irc.reply(msg, 'The latest stable kernel is %s; ' \
                       'the latest beta kernel is %s.' % (stable, beta))
        
Class = ThreadedFunCommands
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
