# -*- coding: utf-8 -*-
#
#   Debian Changes Bot
#   Copyright (C) 2008 Chris Lamb <chris@chris-lamb.co.uk>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

from supybot.commands import wrap
import supybot.callbacks as callbacks

from DebianDevelChangesBot.utils import colourise

import urllib2

class DebianUtils(callbacks.Plugin):
    threaded = True

    def madison(self, irc, msg, args, package):
        args = {
            'package': package,
            's': 'stable,testing,unstable,experimental',
            'text': 'on',
        }
        querystr = '&'.join(['%s=%s' % (k, v) for k, v in args.iteritems()])
        fileobj = urllib2.urlopen('http://qa.debian.org/madison.php?%s' % querystr)

        lines = fileobj.readlines()
        if not lines:
            irc.reply('Did not get a response -- is "%s" a valid package?' % package)
            return

        field_styles = ('package', 'version', 'distribution', 'section')
        for line in lines:
            out = []
            fields = line.strip().split('|', len(field_styles))
            for style, data in zip(field_styles, fields):
                out.append('[%s]%s' % (style, data))
            irc.reply(colourise('[reset]|'.join(out)))

    madison = wrap(madison, ['text'])

Class = DebianUtils
