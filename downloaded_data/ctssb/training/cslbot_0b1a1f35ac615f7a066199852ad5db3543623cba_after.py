from config import ADMINS, CHANNEL, NICK, LOGFILE
import re
import os
from glob import glob
from random import random
from lxml.html import parse
from urllib.request import urlopen, Request
from urllib.error import URLError
import json
import importlib
import imp
import time
import socket


class MyHandler():
    def __init__(self):
        self.log = []
        self.ignored = []
        self.channels = {}
        self.abuselist = {}
        self.modules = self.loadmodules()
        self.scorefile = os.path.dirname(__file__)+'/score'
        self.logfile = open(LOGFILE, 'a')

    def __del__(self):
        self.logfile.close()

    def loadmodules(self):
        modulemap = {}
        for f in glob(os.path.dirname(__file__)+'/commands/*.py'):
            if os.access(f, os.X_OK):
                cmd = os.path.basename(f).split('.')[0]
                modulemap[cmd] = importlib.import_module("commands."+cmd)
        return modulemap

    def ignore(self, send, nick):
        if nick not in self.ignored:
            self.ignored.append(nick)
            send("Now igoring %s." % nick)

    def abusecheck(self, send, nick, limit):
        if nick not in self.abuselist:
            self.abuselist[nick] = [time.time()]
        else:
            self.abuselist[nick].append(time.time())
        count = 0
        for x in self.abuselist[nick]:
            # 60 seconds - arbitrary cuttoff
            if (time.time() - x) < 60:
                count = count + 1
        if count > limit:
            self.send(CHANNEL, nick, "\x02%s\x02 is a Bot Abuser." % nick)
            self.ignore(send, nick)
            return True

    def privmsg(self, c, e):
        nick = e.source.nick
        msg = e.arguments[0].strip()
        if re.search(r"([a-zA-Z0-9]+)(\+\+|--)", msg):
            self.send(nick, nick, 'Hey, no points in private messages!')
            return
        self.handle_msg('priv', c, e)

    def pubmsg(self, c, e):
        self.handle_msg('pub', c, e)

    def send(self, target, nick, msg):
        self.do_log(target, nick, msg)
        self.connection.privmsg(target, msg)

    def do_log(self, target, nick, msg):
        if type(msg) != str:
            raise Exception("IRC doesn't like it when you send it a " + type(msg).__name__)
        if target[0] == "#":
            try:
                if nick in self.channels[target].opers():
                    nick = '@' + nick
            except:
                pass
        currenttime = time.strftime('%H:%M:%S')
        day = int(time.strftime('%d'))
        if len(self.log) > 0:
            if day != self.log[-1][0]:
                log = time.strftime('New Day: %a, %b %d, %Y\n')
                self.log.append([day, log])
                self.logfile.write(log)
                self.logfile.flush()
        # strip ctrl chars from !creffett
        msg = msg.replace('\x02\x038,4', '<rage>')
        log = '%s <%s> %s\n' % (currenttime, nick, msg)
        self.log.append([day, log])
        self.logfile.write(log)
        self.logfile.flush()

    def handle_args(self, modargs, send, nick):
            args = {}
            for arg in modargs:
                if arg == 'channels':
                    args['channels'] = self.channels
                elif arg == 'connection':
                    args['connection'] = self.connection
                elif arg == 'nick':
                    args['nick'] = nick
                elif arg == 'modules':
                    args['modules'] = self.modules
                elif arg == 'scorefile':
                    args['scorefile'] = self.scorefile
                elif arg == 'ignore':
                    args['ignore'] = lambda nick: self.ignore(send, nick)
                else:
                    raise Exception("Invalid Argument: " + arg)
            return args

    def handle_msg(self, msgtype, c, e):
        nick = e.source.nick
        msg = e.arguments[0].strip()
        target = e.target if msgtype == 'pub' else nick
        self.do_log(target, nick, msg)
        send = lambda msg: self.send(target, NICK, msg)
        if nick not in ADMINS and nick in self.ignored:
            return
        # is this a command?
        cmd = msg.split()[0]
        cmdargs = msg[len(cmd)+1:]
        if cmd[0] == '!':
            if cmd[1:] in self.modules:
                mod = self.modules[cmd[1:]]
                if hasattr(mod, 'limit') and self.abusecheck(send, nick, mod.limit):
                    return
                args = self.handle_args(mod.args, send, nick) if hasattr(mod, 'args') else {}
                mod.cmd(send, cmdargs, args)

        #special commands
        if cmd[0] == '!':
            if cmd[1:] == 'reload':
                send("Aye Aye Capt'n")
                for x in self.modules.values():
                    imp.reload(x)
            # everything below this point requires admin
            if nick in ADMINS:
                if cmd[1:] == 'cignore':
                    self.ignored = []
                    send("Ignore list cleared.")
                elif cmd[1:] == 'ignore':
                    self.ignore(send, cmdargs)
                elif cmd[1:] == 'showignore':
                    send(str(self.ignored))
                elif cmd[1:] == 'join':
                    if not cmdargs:
                        return
                    if cmdargs[0] != '#':
                        cmdargs = '#' + cmdargs
                    c.join(cmdargs)
                    self.send(cmdargs, nick, "Joined at the request of " + nick)
                elif cmd[1:] == 'part':
                    if not cmdargs:
                        # don't leave the primary channel
                        if target == CHANNEL:
                            return
                        else:
                            cmdargs = target
                    if cmdargs[0] != '#':
                        cmdargs = '#' + cmdargs
                    # don't leave the primary channel
                    if cmdargs == CHANNEL:
                        return
                    self.send(cmdargs, nick, "Leaving at the request of " + nick)
                    c.part(cmdargs)
        # ++ and --
        matches = re.findall(r"([a-zA-Z0-9]+)(\+\+|--)", msg)
        if matches:
            for match in matches:
                name = match[0].lower()
                if match[1] == "++":
                    score = 1
                    if name == nick.lower():
                        send(nick + ": No self promotion! You lose 10 points.")
                        score = -10
                else:
                    score = -1
                if os.path.isfile(self.scorefile):
                    scores = json.load(open(self.scorefile))
                else:
                    scores = {}
                if name in scores:
                    scores[name] += score
                else:
                    scores[name] = score
                f = open(self.scorefile, "w")
                json.dump(scores, f)
                f.write("\n")
                f.close()
            return

        # crazy regex to match urls
        match = re.search(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»....]))", msg)
        if match:
            try:
                url = match.group(1)
                if not url.startswith('http'):
                    url = 'http://' + url
                # Wikipedia doesn't like the default User-Agent
                req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                t = parse(urlopen(req, timeout=3))
                send('Website Title: ' + t.find(".//title").text.strip())
            except URLError as ex:
                # website does not exist
                if hasattr(ex.reason, 'errno') and ex.reason.errno == socket.EAI_NONAME:
                    pass
                else:
                    send('%s: %s' % (type(ex).__name__, str(ex)))
            # page does not contain a title
            except AttributeError:
                pass
        if target == "#msbob" and random() < 0.25:
            self.modules['slogan'].cmd(send, 'MS BOB', {})
