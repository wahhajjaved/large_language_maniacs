###
# Copyright (c) 2002-2004, Jeremiah Fincher
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

from testsupport import *

import supybot.utils as utils

if network:
    class GameknotTestCase(PluginTestCase, PluginDocumentation):
        plugins = ('Gameknot',)
        def testGkstats(self):
            self.assertNotRegexp('gkstats jemfinch', 'Old GK rating')
            self.assertError('gkstats %s' % utils.mktemp())
            self.assertError('gkstats Strike')

        def testNoHtmlInTeam(self):
            self.assertNotRegexp('gkstats jeffuk', '9608')

        def testUrlSnarfer(self):
            orig = conf.supybot.plugins.Gameknot.gameSnarfer()
            try:
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(True)
                self.assertSnarfNotError(
                        'http://gameknot.com/chess.pl?bd=1019508')
                self.assertSnarfNotError(
                        'here\'s a link: '
                        'http://gameknot.com/chess.pl?bd=1077350&r=394 '
                        'and here\'s another one: '
                        'http://gameknot.com/chess.pl?bd=1116828&r=250')
                self.irc.takeMsg() # The next snarfed response.
                self.assertSnarfNotRegexp(
                        'http://gameknot.com/chess.pl?bd=1019508',
                        self.nick)
            finally:
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(orig)

        def testStatsUrlSnarfer(self):
            orig = conf.supybot.plugins.Gameknot.statSnarfer()
            try:
                conf.supybot.plugins.Gameknot.statSnarfer.setValue(True)
                self.assertSnarfNotError(
                    'http://gameknot.com/stats.pl?ironchefchess')
                self.assertSnarfRegexp(
                    'http://gameknot.com/stats.pl?ddipaolo&1',
                    r'^[^&]+$')
                self.assertSnarfRegexp(
                    'http://gameknot.com/stats.pl?ddipaolo and some extra',
                    r'^ddipaolo is rated')
            finally:
                conf.supybot.plugins.Gameknot.statSnarfer.setValue(orig)

        def testConfig(self):
            game = conf.supybot.plugins.Gameknot.gameSnarfer()
            stat = conf.supybot.plugins.Gameknot.statSnarfer()
            try:
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(False)
                conf.supybot.plugins.Gameknot.statSnarfer.setValue(False)
                self.assertSnarfNoResponse(
                    'http://gameknot.com/stats.pl?ironchefchess')
                self.assertSnarfNoResponse(
                    'http://gameknot.com/chess.pl?bd=907498')
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(True)
                conf.supybot.plugins.Gameknot.statSnarfer.setValue(True)
                self.assertSnarfNotError(
                    'http://gameknot.com/stats.pl?ironchefchess', timeout=20)
                self.assertSnarfNotError(
                    'http://gameknot.com/chess.pl?bd=907498')
            finally:
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(game)
                conf.supybot.plugins.Gameknot.statSnarfer.setValue(stat)


        def testSnarfer(self):
            orig = conf.supybot.plugins.Gameknot.gameSnarfer()
            try:
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(True)
                self.assertSnarfRegexp(
                    'http://gameknot.com/chess.pl?bd=955432',
                    '\x02ddipaolo\x02 lost')
                self.assertSnarfRegexp(
                    'http://gameknot.com/chess.pl?bd=1077345&r=365',
                    'draw')
            finally:
                conf.supybot.plugins.Gameknot.gameSnarfer.setValue(orig)


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

