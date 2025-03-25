#!/usr/bin/env python

###
# Copyright (c) 2003, Daniel DiPaolo
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
A module to allow each channel to have "news" which people will be notified of
when they join the channel.  News items may have expiration dates.
"""

__revision__ = "$Id$"

import supybot.plugins as plugins

import os
import time

import supybot.conf as conf
import supybot.ircdb as ircdb
import supybot.utils as utils
import supybot.privmsgs as privmsgs
import supybot.callbacks as callbacks

try:
    import sqlite
except ImportError:
    raise callbacks.Error, 'You need to have PySQLite installed to use this ' \
                           'plugin.  Download it at <http://pysqlite.sf.net/>'

class News(plugins.ChannelDBHandler, callbacks.Privmsg):
    def __init__(self):
        plugins.ChannelDBHandler.__init__(self)
        callbacks.Privmsg.__init__(self)
        self.removeOld = False

    def makeDb(self, filename):
        if os.path.exists(filename):
            return sqlite.connect(filename)
        db = sqlite.connect(filename)
        cursor = db.cursor()
        cursor.execute("""CREATE TABLE news (
                          id INTEGER PRIMARY KEY,
                          subject TEXT,
                          item TEXT,
                          added_at TIMESTAMP,
                          expires_at TIMESTAMP,
                          added_by TEXT
                          )""")
        db.commit()
        return db

    def add(self, irc, msg, args, channel):
        """[<channel>] <expires> <subject>: <text>

        Adds a given news item of <text> to a channel with the given <subject>.
        If <expires> isn't 0, that news item will expire <expires> seconds from
        now.  <channel> is only necessary if the message isn't sent in the
        channel itself.
        """
        # Parse out the args
        i = 0
        for i, arg in enumerate(args):
            if arg.endswith(':'):
                i += 1
                break
        if not i:
            raise callbacks.ArgumentError
        added_at = int(time.time())
        expire_interval = int(args[0])
        expires = expire_interval and (added_at + expire_interval)
        subject = ' '.join(args[1:i])
        text = ' '.join(args[i:])
        # Set the other stuff needed for the insert.
        if ircdb.users.hasUser(msg.prefix):
            name = ircdb.users.getUser(msg.prefix).name
        else:
            name = msg.nick

        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("INSERT INTO news VALUES (NULL, %s, %s, %s, %s, %s)",
                       subject[:-1], text, added_at, expires, name)
        db.commit()
        irc.replySuccess()
    add = privmsgs.checkChannelCapability(add, 'news')

    def _readnews(self, irc, msg, args):
        """[<channel>] <number>

        Display the text for news item with id <number> from <channel>.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        channel = privmsgs.getChannel(msg, args)
        id = privmsgs.getArgs(args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT news.item, news.subject, news.added_at,
                          news.expires_at, news.added_by FROM news
                          WHERE news.id=%s""", id)
        if cursor.rowcount == 0:
            irc.error('No news item matches that id.')
        else:
            item, subject, added_at, expires_at, added_by = cursor.fetchone()
            if int(expires_at) == 0:
                s = '%s (Subject: "%s", added by %s on %s)' % \
                    (item, subject, added_by,
                     time.strftime(conf.supybot.humanTimestampFormat(),
                                   time.localtime(int(added_at))))
            else:
                s = '%s (Subject: "%s", added by %s on %s, expires at %s)' % \
                    (item, subject, added_by,
                     time.strftime(conf.supybot.humanTimestampFormat(),
                                   time.localtime(int(added_at))),
                     time.strftime(conf.supybot.humanTimestampFormat(),
                                   time.localtime(int(expires_at))))
            irc.reply(s)

    def news(self, irc, msg, args):
        """[<channel>] [<number>]

        Display the news items for <channel> in the format of '(#id) subject'.
        If <number> is given, retrieve only that news item; otherwise retrieve
        all news items.  <channel> is only necessary if the message isn't sent
        in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        number = privmsgs.getArgs(args, required=0, optional=1)
        if number:
            self._readnews(irc, msg, [channel, number])
            return
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT news.id, news.subject FROM news
                          WHERE news.expires_at > %s
                          OR news.expires_at=0""", int(time.time()))
        if cursor.rowcount == 0:
            irc.reply('No news for %s.' % channel)
        else:
            items = ['(#%s) %s' % (id, s) for (id, s) in cursor.fetchall()]
            s = 'News for %s: %s' % (channel, '; '.join(items))
            irc.reply(s)

    def remove(self, irc, msg, args, channel):
        """[<channel>] <number>

        Removes the news item with id <number> from <channel>.  <channel> is
        only necessary if the message isn't sent in the channel itself.
        """
        id = privmsgs.getArgs(args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT * FROM news WHERE id=%s""", id)
        if cursor.rowcount == 0:
            irc.error('No news item matches that id.')
        else:
            cursor.execute("""DELETE FROM news WHERE news.id = %s""", id)
            db.commit()
            irc.replySuccess()
    remove = privmsgs.checkChannelCapability(remove, 'news')

    def change(self, irc, msg, args, channel):
        """[<channel>] <number> <regexp>

        Changes the news item with id <number> from <channel> according to the
        regular expression <regexp>.  <regexp> should be of the form
        s/text/replacement/flags.  <channel> is only necessary if the message
        isn't sent on the channel itself.
        """
        (id, regexp) = privmsgs.getArgs(args, required=2)
        try:
            replacer = utils.perlReToReplacer(regexp)
        except ValueError, e:
            irc.error(str(e))
            return
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT subject, item FROM news WHERE id=%s""", id)
        if cursor.rowcount == 0:
            irc.error('No news item matches that id.')
            return
        (subject, item) = cursor.fetchone()
        s = '%s: %s' % (subject, item)
        s = replacer(s)
        (newSubject, newItem) = s.split(': ')
        cursor.execute("""UPDATE news SET subject=%s, item=%s WHERE id=%s""",
                       newSubject, newItem, id)
        irc.replySuccess()
    change = privmsgs.checkChannelCapability(change, 'news')

    def old(self, irc, msg, args):
        """[<channel>] [<number>]

        Returns the old news item for <channel> with id <number>.  If no number
        is given, returns all the old news items in reverse order.  <channel>
        is only necessary if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        id = privmsgs.getArgs(args, required=0, optional=1)
        db = self.getDb(channel)
        cursor = db.cursor()
        if id:
            try:
                id = int(id)
            except ValueError:
                irc.error('%r isn\'t a valid id.' % id)
                return
            cursor.execute("""SELECT subject, item FROM news WHERE id=%s""",id)
            if cursor.rowcount == 0:
                irc.error('No news item matches that id.')
            else:
                (subject, item) = cursor.fetchone()
                irc.reply('%s: %s' % (cursor, item))
        else:
            cursor.execute("""SELECT id, subject FROM news
                              WHERE expires_at <> 0 AND expires_at < %s
                              ORDER BY id DESC""", int(time.time()))
            if cursor.rowcount == 0:
                irc.error('I have no news for that channel.')
                return
            subjects = ['#%s: %s' % (id, s) for (id, s) in cursor.fetchall()]
            irc.reply(utils.commaAndify(subjects))




Class = News

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
