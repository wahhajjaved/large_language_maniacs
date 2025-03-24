# -*- coding: utf-8 -*-

# Command plugin for t2jrbot.
# Copyright © 2014 Tuomas Räsänen <tuomasjjrasanen@tjjr.fi>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

class _CommandPlugin(object):

    def __init__(self, bot):
        self.__bot = bot
        self.__command_handlers = {}
        self.__command_descriptions = {}

        self.__pre_eval_hooks = {}

        self.__bot.add_irc_callback(self.__irc_privmsg, command="PRIVMSG")
        self.register_command("!help", self.__command_help,
                              "Since you got this far, "
                              "you already know what this command does.")

    def __command_help(self, nick, host, channel, this_command, argstr):
        command = argstr.strip()
        if not command:
            commands = sorted(self.__command_descriptions.keys())
            self.__bot.irc.send_privmsg(channel,
                                        "%s: Commands: %s"
                                        % (nick, ", ".join(commands)))
            self.__bot.irc.send_privmsg(channel,
                                        "%s: To get detailed help on a command, "
                                        "use %s COMMAND, e.g. %s %s"
                                        % (nick, this_command, this_command, this_command))
        else:
            try:
                descr = self.__command_descriptions[command]
            except KeyError:
                self.__bot.irc.send_privmsg(channel,
                                            "%s: command '%s' not found" % (nick, command))
            else:
                self.__bot.irc.send_privmsg(channel, "%s: %s - %s"
                                            % (nick, command, descr))

    def add_pre_eval_hook(self, hook, command=None):
        hooks = self.__pre_eval_hooks.setdefault(command, set())
        hooks.add(hook)

    def register_command(self, command, handler, description=""):
        if command in self.__command_handlers:
            raise Error("command '%s' is already registered" % command)
        self.__command_handlers[command] = handler
        self.__command_descriptions[command] = description

    def unregister_command(self, command):
        try:
            del self.__command_handlers[command]
        except KeyError:
            raise Error("command '%s' is not registered" % command)
        del self.__command_descriptions[command]

    def __irc_privmsg(self, prefix, this_command, params):
        nick, sep, host = prefix.partition("!")

        target, text = params

        if target == self.__bot.nick:
            # User-private messages are not supported and are silently
            # ignored.
            return

        channel = target

        # Ignore all leading whitespaces.
        text = text.lstrip()

        if not text.startswith("%s:" % self.__bot.nick):
            # The message is not designated to me, ignore.
            return

        # Strip my nick from the beginning of the text.
        commandstr = text[len("%s:" % self.__bot.nick):].lstrip()

        command, _, argstr = commandstr.partition(' ')

        self.__eval_command(nick, host, channel, command, argstr)

    def __eval_command(self, nick, host, channel, command, argstr):
        hooks = set()

        hooks.update(self.__pre_eval_hooks.get(command, set()),
                     self.__pre_eval_hooks.get(None, set()))

        if not all([hook(nick, host, channel, command, argstr) for hook in hooks]):
            return

        try:
            command_handler = self.__command_handlers[command]
        except KeyError:
            # Silently ignore all input except registered commands.
            return

        try:
            command_handler(nick, host, channel, command, argstr)
        except Exception, e:
            self.irc.send_privmsg(channel,
                                  "%s: error: %s" % (nick, e.message))


def load(bot, conf):
    return _CommandPlugin(bot)
