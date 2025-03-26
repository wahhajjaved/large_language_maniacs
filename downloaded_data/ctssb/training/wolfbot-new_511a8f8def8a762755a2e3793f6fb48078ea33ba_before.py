# Copyright (c) 2011, Jimmy Cao
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

# Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from oyoyo.parse import parse_nick
import var
import botconfig
import decorators
from datetime import datetime, timedelta
import threading
import random
import copy
from time import sleep
from time import time as timetime
import re
import logging
import sys
import os

COMMANDS = {}
PM_COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
pmcmd = decorators.generate(PM_COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True)

# Game Logic Begins:

def connect_callback(cli):
    cli.ns_identify(botconfig.PASS)

    def prepare_stuff():
        cli.join(botconfig.CHANNEL)
        cli.msg("ChanServ", "op "+botconfig.CHANNEL)

        var.USERS = []
        var.CLOAKS = []

        @hook("whoreply")
        def on_whoreply(cli, server, dunno, chan, dunno1,
                        cloak, dunno3, user, status, dunno4):
            if user in var.USERS: return  # Don't add someone who is already there
            var.USERS.append(user)
            var.CLOAKS.append(cloak)
        cli.who(botconfig.CHANNEL)

    @hook("nicknameinuse")
    def mustghost(cli, *blah):
        cli.nick(botconfig.NICK+"_")
        cli.ns_identify(botconfig.PASS)
        cli.ns_ghost()
        cli.nick(botconfig.NICK)
        prepare_stuff()

    @hook("unavailresource")
    def mustrelease(cli, *blah):
        cli.nick(botconfig.NICK+"_")
        cli.ns_identify(botconfig.PASS)
        cli.ns_release()
        cli.nick(botconfig.NICK)
        prepare_stuff()

    var.LAST_PING = 0  # time of last ping
    var.ROLES = {"person" : []}
    var.ORIGINAL_ROLES = {}
    var.PHASE = "none"  # "join", "day", or "night"
    var.TIMERS = [None, None]
    var.DEAD = []

    var.ORIGINAL_SETTINGS = {}
    var.DENIED_SETTINGS_CHANGE = []
    var.SETTINGS_CHANGE_OPPOSITION = []
    var.SETTINGS_CHANGE_REQUESTER = None

    var.LAST_SAID_TIME = {}

    var.GAME_START_TIME = datetime.now()  # for idle checker only
    var.GRAVEYARD_LOCK = threading.RLock()
    var.GAME_ID = 0

    prepare_stuff()


def mass_mode(cli, md):
    """ Example: mass_mode(cli, (('+v', 'asdf'), ('-v','wobosd'))) """
    lmd = len(md)  # store how many mode changes to do
    for start_i in range(0, lmd, 4):  # 4 mode-changes at a time
        if start_i + 4 > lmd:  # If this is a remainder (mode-changes < 4)
            z = list(zip(*md[start_i:]))  # zip this remainder
            ei = lmd % 4  # len(z)
        else:
            z = list(zip(*md[start_i:start_i+4])) # zip four
            ei = 4 # len(z)
        # Now z equal something like [('+v', '-v'), ('asdf', 'wobosd')]
        arg1 = "".join(z[0])
        arg2 = " ".join(z[1]) + " " + " ".join([x+"!*@*" for x in z[1]])
        cli.mode(botconfig.CHANNEL, arg1, arg2)



def reset_settings():
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    dict.clear(var.ORIGINAL_SETTINGS)

    var.SETTINGS_CHANGE_OPPOSITION = []
    var.SETTINGS_CHANGE_REQUESTER = None


def reset(cli):
    chan = botconfig.CHANNEL
    var.PHASE = "none"

    if var.TIMERS[0]:
        var.TIMERS[0].cancel()
        var.TIMERS[0] = None
    if var.TIMERS[1]:
        var.TIMERS[1].cancel()
        var.TIMERS[1] = None
    var.GAME_ID = 0

    cli.mode(chan, "-m")
    cmodes = []
    for plr in var.list_players():
        cmodes.append(("-v", plr))
    for deadguy in var.DEAD:
       cmodes.append(("-q", deadguy))
    mass_mode(cli, cmodes)
    var.DEAD = []

    var.ROLES = {"person" : []}

    reset_settings()
    var.DENIED_SETTINGS_CHANGE = []

    dict.clear(var.LAST_SAID_TIME)


@pmcmd("bye", admin_only=True)
@cmd("bye", admin_only=True)
@pmcmd("die", admin_only=True)
@cmd("die", admin_only=True)
def forced_exit(cli, nick, *rest):  # Admin Only
    """Forces the bot to close"""

    reset(cli)
    dict.clear(COMMANDS)
    dict.clear(PM_COMMANDS)
    dict.clear(HOOKS)
    cli.quit("Forced quit from admin")
    raise SystemExit



@cmd("exec", owner_only = True)
def py(cli, nick, chan, rest):
    try:
        exec(rest)
    except Exception as e:
        cli.msg(chan, str(type(e))+":"+str(e))



@cmd("eval", owner_only = True)
def pyeval(cli, nick, chan, rest):
    try:
        a = str(eval(rest))
        if len(a) < 500:
            cli.msg(chan, a)
        else:
            cli.msg(chan, a[0:500])
    except Exception as e:
        cli.msg(chan, str(type(e))+":"+str(e))


@cmd("restart", admin_only=True)
def restart_program(cli, nick, chan, rest):
    """Restarts the bot."""
    try:
        forced_exit(cli, nick, chan, rest)
    finally:
        print("RESTARTING")
        python = sys.executable
        os.execl(python, python, *sys.argv)



@cmd("op", admin_only=True)
def give_op(cli, nick, chan, rest):
    """OP [(person)] Makes someone or yourself a channel operator"""
    if not rest.strip():
        rest = nick

    for a in re.split(" +",rest):
        a = a.strip()
        if not a:
            continue
        cli.msg("ChanServ", " ".join(("op",chan,a)))
    
    
    
@pmcmd("op", admin_only=True)
def give_op_pm(cli, nick, rest):
    give_op(cli, nick, botconfig.CHANNEL, rest)



@cmd("deop", admin_only=True)
def take_op(cli, nick, chan, rest):
    """Takes operator rights from someone or yourself."""
    if not rest.strip():
        rest = nick
    
    for a in re.split(" +",rest):
        a = a.strip()
        if not a:
            continue
        cli.msg("ChanServ", " ".join(("deop",chan,a)))



@cmd("ping")
def pinger(cli, nick, chan, rest):
    """Pings the channel to get people's attention.  Rate-Limited."""
    if (var.LAST_PING and
        var.LAST_PING + timedelta(seconds=300) > datetime.now()):
        cli.notice(nick, ("This command is ratelimited. " +
                          "Please wait a while before using it again."))
        return

    var.LAST_PING = datetime.now()
    var.PINGING = True
    TO_PING = []



    @hook("whoreply")
    def on_whoreply(cli, server, dunno, chan, dunno1,
                    cloak, dunno3, user, status, dunno4):
        if not var.PINGING: return
        if user in (botconfig.NICK, nick): return  # Don't ping self.

        if (var.PINGING and 'G' not in status and
            '+' not in status and cloak not in var.AWAY):
            TO_PING.append(user)



    @hook("endofwho")
    def do_ping(*args):
        if not var.PINGING: return

        cli.msg(chan, "PING! "+" ".join(TO_PING))
        var.PINGING = False

        HOOKS.pop("whoreply")
        HOOKS.pop("endofwho")

    cli.who(chan)


@cmd("away", raw_nick=True)
@pmcmd("away", raw_nick=True)
@cmd("back", raw_nick=True)
@pmcmd("back", raw_nick=True)
def away(cli, nick, *rest):
    """Use this to toggle your away status (for !ping)."""
    cloak = parse_nick(nick)[3]
    nick = parse_nick(nick)[0]
    if cloak in var.AWAY:
        var.AWAY.remove(cloak)
        cli.notice(nick, "You are now no longer marked as away.")
        return
    var.AWAY.append(cloak)
    cli.notice(nick, "You are now marked as away.")



@cmd("fping", admin_only=True)
def fpinger(cli, nick, chan, rest):
    var.LAST_PING = None
    pinger(cli, nick, chan, rest)



@cmd("join")
def join(cli, nick, chan, rest):
    """Either starts a new game of Werewolf or joins an existing game that has not started yet."""
    pl = var.list_players()
    if var.PHASE == "none":
        cli.mode(chan, "+v", nick, nick+"!*@*")
        var.ROLES["person"].append(nick)
        var.PHASE = "join"
        var.WAITED = 0
        var.GAME_ID = timetime()
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Werewolf. '+
                      'Type "{1}join" to join. Type "{1}start" to start the game. '+
                      'Type "{1}wait" to increase join wait time.').format(nick, botconfig.CMD_CHAR))
    elif nick in pl:
        cli.notice(nick, "You're already playing!")
    elif len(pl) >= var.MAX_PLAYERS:
        cli.notice(nick, "Too many players!  Try again next time.")
    elif var.PHASE != "join":
        cli.notice(nick, "Sorry but the game is already running.  Try again next time.")
    else:
        cli.mode(chan, "+v", nick, nick+"!*@*")
        var.ROLES["person"].append(nick)
        cli.msg(chan, '\u0002{0}\u0002 has joined the game.'.format(nick))


@cmd("fjoin", admin_only=True)
def fjoin(cli, nick, chan, rest):
    noticed = False
    if not rest.strip():
        join(cli, nick, chan, "")

    for a in re.split(" +",rest):
        a = a.strip()
        if not a:
            continue
        ull = [u.lower() for u in var.USERS]
        if a.lower() not in ull:
            if not is_fake_nick(a):
                if not noticed:  # important
                    cli.msg(chan, nick+(": You may only fjoin fake people "+
                                        "or people in this channel for now."))
                    noticed = True
                continue
        if not is_fake_nick(a):
            a = var.USERS[ull.index(a.lower())]
        if a != botconfig.NICK:
            join(cli, a.strip(), chan, "")
        else:
            cli.notice(nick, "No, that won't be allowed.")

@cmd("fleave","fquit","fdel", admin_only=True)
def fleave(cli, nick, chan, rest):
    for a in re.split(" +",rest):
        a = a.strip()
        if not a:
            continue
        pll = [x.lower() for x in var.list_players()]
        if a.lower() != botconfig.NICK.lower() and a.lower() in pll:
            del_player(cli, a.strip())
            cli.msg(chan, ("\u0002{0}\u0002 has used fleave"+
                          " on \u0002{1}\u0002.").format(nick, a.strip()))
        elif a.lower() not in pll:
            cli.msg(chan, nick+": That could not be done.")



@cmd("fstart", admin_only=True)
def fstart(cli, nick, chan, rest):
    var.CAN_START_TIME = datetime.now()
    cli.msg(chan, "\u0002{0}\u0002 has forced the game to start.".format(nick))
    start(cli, nick, chan, rest)



@cmd("chankick", admin_only=True)
def chankick(cli, nick, chan, rest):
    rest = re.split(" +", rest, 1)
    if not rest[0]:
        cli.notice(nick, "Invalid syntax for this command.")
        return
    if rest[0] != botconfig.NICK:
        cli.kick(chan, *rest)
    else:
        cli.kick(chan, nick, "No.")



@hook("kick")
def on_kicked(cli, nick, chan, victim, reason):
    if victim == botconfig.NICK:
        cli.join(botconfig.CHANNEL)
        cli.msg("ChanServ", "op "+botconfig.CHANNEL)
        #  cli.kick(chan, nick, "No.")



@cmd("stats")
def stats(cli, nick, chan, rest):
    """Display the player statistics"""
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return

    pl = var.list_players()
    if len(pl) > 1:
        cli.msg(chan, '{0}: \u0002{1}\u0002 players: {2}'.format(nick,
            len(pl), ", ".join(pl)))
    else:
        cli.msg(chan, '{0}: \u00021\u0002 player: {1}'.format(nick, pl[0]))

    if var.PHASE == "join":
        return

    message = []
    f = False  # set to true after the is/are verb is decided
    l1 = [k for k in var.ROLES.keys()
          if var.ROLES[k]]
    l2 = [k for k in var.ORIGINAL_ROLES.keys()
          if var.ORIGINAL_ROLES[k]]
    for role in set(l1+l2):
        count = len(var.ROLES[role])
        if not f and count>1:
            vb = "are"
            f = True
        elif not f:
            vb = "is"
            f = True
        if count > 1 or count == 0:
            message.append("\u0002{0}\u0002 {1}".format(count if count else "\u0002no\u0002", var.plural(role)))
        else:
            message.append("\u0002{0}\u0002 {1}".format(count, role))
    cli.msg(chan, "{0}: There {3} {1}, and {2}.".format(nick,
                                                        ", ".join(message[0:-1]),
                                                        message[-1],
                                                        vb))



def hurry_up(cli, gameid=0):
    if var.PHASE != "day": return
    if gameid:
        if gameid != var.DAY_ID:
            return
    var.DAY_ID = 0

    chan = botconfig.CHANNEL
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1

    found_dup = False
    maxfound = (0, "")
    for votee, voters in iter(var.VOTES.items()):
        if len(voters) > maxfound[0]:
            maxfound = (len(voters), votee)
            found_dup = False
        elif len(voters) == maxfound[0]:
            found_dup = True
    if maxfound[0] > 0 and not found_dup:
        cli.msg(chan, "The sun sets.")
        var.VOTES[maxfound[1]] = [None] * votesneeded
        chk_decision(cli)  # Induce a lynch
    else:
        cli.msg(chan, "The sun is almost setting.")
        for plr in pl:
            var.VOTES[plr] = [None] * (votesneeded - 1)



@cmd("fnight", admin_only=True)
def fnight(cli, nick, chan, rest):
    if var.PHASE != "day":
        cli.notice(nick, "It is not daytime.")
    else:
        hurry_up(cli)


@cmd("fday", admin_only=True)
def fday(cli, nick, chan, rest):
    if var.PHASE != "night":
        cli.notice(nick, "It is not nighttime.")
    else:
        transition_day(cli)



def chk_decision(cli):
    chan = botconfig.CHANNEL
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1
    for votee, voters in iter(var.VOTES.items()):
        if len(voters) >= votesneeded:
            cli.msg(botconfig.CHANNEL,
                    random.choice(var.LYNCH_MESSAGES).format(
                    votee, var.get_role(votee)))
            if del_player(cli, votee, True):
                transition_night(cli)



@cmd("votes")
def show_votes(cli, nick, chan, rest):
    """Displays the voting statistics."""
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, "Voting is only during the day.")
        return
    elif not var.VOTES.values():
        cli.msg(chan, nick+": No votes yet.")
        return
    if None in [x for voter in var.VOTES.values() for x in voter]:
        cli.msg(chan, (nick+": Tiebreaker conditions.  Whoever "+
                      "receives the next vote will be lynched."))
        return

    votelist = ["{0}: {1} ({2})".format(votee,
                                        len(var.VOTES[votee]),
                                        " ".join(var.VOTES[votee]))
                for votee in var.VOTES.keys()]
    cli.msg(chan, "{0}: {1}".format(nick, ", ".join(votelist)))

    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1
    cli.msg(chan, ("{0}: \u0002{1}\u0002 players, \u0002{2}\u0002 votes "+
                   "required to lynch, \u0002{3}\u0002 players available " +
                   "to vote.").format(nick, len(pl), votesneeded, avail))



def chk_traitor(cli):
    for tt in var.ROLES["traitor"]:
        var.ROLES["wolf"].append(tt)
        var.ROLES["traitor"].remove(tt)
        cli.msg(tt, ('HOOOOOOOOOWL. You have become... a wolf!\n'+
                     'It is up to you to avenge your fallen leaders!'))



def stop_game(cli):
    chan = botconfig.CHANNEL
    if var.DAY_START_TIME:
        now = datetime.now()
        td = now - var.DAY_START_TIME
        var.DAY_TIMEDELTA += td
    if var.NIGHT_START_TIME:
        now = datetime.now()
        td = now - var.NIGHT_START_TIME
        var.NIGHT_TIMEDELTA += td

    daymin, daysec = var.DAY_TIMEDELTA.seconds // 60, var.DAY_TIMEDELTA.seconds % 60
    nitemin, nitesec = var.NIGHT_TIMEDELTA.seconds // 60, var.NIGHT_TIMEDELTA.seconds % 60
    total = var.DAY_TIMEDELTA + var.NIGHT_TIMEDELTA
    tmin, tsec = total.seconds // 60, total.seconds % 60
    cli.msg(chan, ("Game lasted \u0002{0:0>2}:{1:0>2}\u0002. " +
                   "\u0002{2:0>2}:{3:0>2}\u0002 was day. " +
                   "\u0002{4:0>2}:{5:0>2}\u0002 was night. ").format(tmin, tsec,
                                                                     daymin, daysec,
                                                                     nitemin, nitesec))

    roles_msg = []
    var.ORIGINAL_ROLES["cursed villager"] = var.CURSED
    lroles = list(var.ORIGINAL_ROLES.keys())
    lroles.remove("wolf")
    lroles.insert(0, "wolf")   # picky, howl consistency
    for role in lroles:
        if len(var.ORIGINAL_ROLES[role]) == 0 or role == "villager":
            continue
        elif len(var.ORIGINAL_ROLES[role]) == 2:
            msg = "The {1} were \u0002{0[0]}\u0002 and \u0002{0[1]}\u0002."
            roles_msg.append(msg.format(var.ORIGINAL_ROLES[role], var.plural(role)))
        elif len(var.ORIGINAL_ROLES[role]) == 1:
            roles_msg.append("The {1} was \u0002{0[0]}\u0002.".format(var.ORIGINAL_ROLES[role],
                                                                      role))
        else:
            msg = "The {2} were {0}, and \u0002{1}\u0002."
            nickslist = ["\u0002"+x+"\u0002" for x in var.ORIGINAL_ROLES[role][0:-1]]
            roles_msg.append(msg.format(", ".join(nickslist),
                                                  var.ORIGINAL_ROLES[role][-1],
                                                  var.plural(role)))
    cli.msg(chan, " ".join(roles_msg))

    reset(cli)
    return True                     
                     
                     

def chk_win(cli):
    """ Returns True if someone won """

    chan = botconfig.CHANNEL
    lpl = len(var.list_players())
    if lpl == 0:
        cli.msg(chan, "No more players remaining. Game ended.")
        reset(cli)
        return True
    if var.PHASE == "join":
        return False
    elif (len(var.ROLES["wolf"])+
          #len(var.ROLES["traitor"])+   Apparently not.
          len(var.ROLES["werecrow"])) == lpl / 2:
        cli.msg(chan, ("Game over! There are the same number of wolves as "+
                       "villagers. The wolves eat everyone, and win."))
    elif (len(var.ROLES["wolf"])+
          #len(var.ROLES["traitor"])+
          len(var.ROLES["werecrow"])) > lpl / 2:
        cli.msg(chan, ("Game over! There are more wolves than "+
                       "villagers. The wolves eat everyone, and win."))
    elif (not var.ROLES["wolf"] and
          not var.ROLES["traitor"] and
          not var.ROLES["werecrow"]):
        cli.msg(chan, ("Game over! All the wolves are dead! The villagers "+
                       "chop them up, BBQ them, and have a hearty meal."))
    elif not len(var.ROLES["wolf"]) and var.ROLES["traitor"]:
        chk_traitor(cli)
        cli.msg(chan, ('\u0002The villagers, during their celebrations, are '+
                       'frightened as they hear a loud howl. The wolves are '+
                       'not gone!\u0002'))
        return False
    else:
        return False
    stop_game(cli)





def del_player(cli, nick, forced_death = False):
    """
    Returns: False if one side won.
    arg: forced_death = True when lynched or when the seer/wolf both don't act
    """
    t = timetime()  #  time
    with var.GRAVEYARD_LOCK:
        if not var.GAME_ID or var.GAME_ID > t:
            #  either game ended, or a new game has started.
            return False
        cmode = []
        cmode.append(("-v", nick))
        var.del_player(nick)
        ret = True
        if var.PHASE == "join":
            # Died during the joining process as a person
            mass_mode(cli, cmode)
            return not chk_win(cli)
        if var.PHASE != "join" and ret:
            # Died during the game, so quiet!
            if not is_fake_nick(nick):
                cmode.append(("+q", nick))
            mass_mode(cli, cmode)
            var.DEAD.append(nick)
            ret = not chk_win(cli)
        if var.PHASE in ("night", "day") and ret:
            # remove him from variables if he is in there
            if var.VICTIM == nick:
                var.VICTIM = ""
            for x in (var.OBSERVED, var.HVISITED, var.GUARDED):
                keys = list(x.keys())
                for k in keys:
                    if k == nick:
                        del x[k]
                    elif x[k] == nick:
                        del x[k]
            if nick in var.GUNNERS.keys():
                del var.GUNNERS[nick]
            if nick in var.CURSED:
                var.CURSED.remove(nick)
        if var.PHASE == "day" and not forced_death and ret:  # didn't die from lynching
            if nick in var.VOTES.keys():
                del var.VOTES[nick]  #  Delete his votes
            for k in var.VOTES.keys():
                if nick in var.VOTES[k]:
                    var.VOTES[k].remove(nick)
            chk_decision(cli)
        return ret


@hook("ping")
def on_ping(cli, prefix, server):
    cli.send('PONG', server)



def reaper(cli, gameid):
    # check to see if idlers need to be killed.
    var.IDLE_WARNED = []

    if not var.WARN_IDLE_TIME or not var.KILL_IDLE_TIME:
        return

    while gameid == var.GAME_ID:
        with var.GRAVEYARD_LOCK:
            to_warn = []
            to_kill = []
            for nick in var.list_players():
                lst = var.LAST_SAID_TIME.get(nick, var.GAME_START_TIME)
                tdiff = datetime.now() - lst
                if (tdiff > timedelta(seconds=var.WARN_IDLE_TIME) and
                                        nick not in var.IDLE_WARNED):
                    to_warn.append(nick)
                    var.IDLE_WARNED.append(nick)
                    var.LAST_SAID_TIME[nick] = (datetime.now() -
                        timedelta(seconds=var.WARN_IDLE_TIME))  # Give him a chance
                elif (tdiff > timedelta(seconds=var.KILL_IDLE_TIME) and
                    nick in var.IDLE_WARNED):
                    to_kill.append(nick)
                    print("WILL KILL "+nick)
                elif (tdiff < timedelta(seconds=var.WARN_IDLE_TIME) and
                    nick in var.IDLE_WARNED):
                    var.IDLE_WARNED.remove(nick)  # he saved himself from death
            chan = botconfig.CHANNEL
            for nck in to_kill:
                if nck not in var.list_players():
                    continue
                cli.msg(chan, ("\u0002{0}\u0002 didn't get out of bed "+
                    "for a very long time. S/He is declared dead. Appears "+
                    "(s)he was a \u0002{1}\u0002.").format(nck, var.get_role(nck)))
                if not del_player(cli, nck):
                    return
            pl = var.list_players()
            x = [a for a in to_warn if a in pl]
            if x:
                cli.msg(chan, ("{0}: \u0002You have been idling for a while. "+
                               "Please remember to say something soon or you "+
                               "might be declared dead.\u0002").format(", ".join(x)))
        sleep(10)



@cmd("")  # update last said
def update_last_said(cli, nick, *rest):
    if var.PHASE not in ("join", "none"):
        var.LAST_SAID_TIME[nick] = datetime.now()



@hook("join")
def on_join(cli, raw_nick, chan):
    nick,m,u,cloak = parse_nick(raw_nick)
    if nick not in var.USERS and nick != botconfig.NICK:
        var.USERS.append(nick)
        var.CLOAKS.append(cloak)
    #if nick in var.list_players():
    #    cli.mode(chan, "+v", nick, nick+"!*@*") needed?

@cmd("goat")
def goat(cli, nick, chan, rest):
    """Use a goat to interact with anyone in the channel during the day"""
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, "You can only do that in the day.")
        return
    if var.GOATED:
        cli.notice(nick, "You can only do that once per day.")
        return
    if rest.strip() in var.USERS:
        cli.msg(chan, ("\u0002{0}\u0002's goat walks by "+
                      "and kicks \u0002{1}\u0002.").format(nick,
                                                           rest.strip()))



@hook("nick")
def on_nick(cli, prefix, nick):
    prefix,u,m,cloak = parse_nick(prefix)

    if prefix in var.DENIED_SETTINGS_CHANGE:
        var.DENIED_SETTINGS_CHANGE.append(nick)
        var.DENIED_SETTINGS_CHANGE.remove(prefix)

    if prefix in var.USERS:
        var.USERS.remove(prefix)
        var.CLOAKS.remove(cloak)
        var.USERS.append(nick)
        var.CLOAKS.append(cloak)

    opl = []
    for k,v in var.ORIGINAL_ROLES.items():
        if prefix in v:
            var.ORIGINAL_ROLES[k].remove(prefix)
            var.ORIGINAL_ROLES[k].append(nick)
            break

    if prefix in var.list_players():
        r = var.ROLES[var.get_role(prefix)]
        r.append(nick)
        r.remove(prefix)

        if var.PHASE in ("night", "day"):
            if var.VICTIM == prefix:
                var.VICTIM = nick
            kvp = []
            for dictvar in (var.HVISITED, var.OBSERVED, var.GUARDED):
                for a,b in dictvar.items():
                    if a == prefix:
                        a = nick
                    if b == prefix:
                        b = nick
                    kvp.append((a,b))
                dictvar.update(kvp)
                if prefix in dictvar.keys():
                    del dictvar[prefix]
            if prefix in var.SEEN:
                var.SEEN.remove(prefix)
                var.SEEN.append(nick)
            if nick in var.GUNNERS.keys():
                del var.GUNNERS[nick]
            if nick in var.CURSED:
                var.CURSED.remove(nick)

        if var.PHASE == "day":
            if prefix in var.WOUNDED:
                var.WOUNDED.remove(prefix)
                var.WOUNDED.append(nick)
            if prefix in var.INVESTIGATED:
                var.INVESTIGATED.remove(prefix)
                var.INVESTIGATED.append(prefix)
            if prefix in var.VOTES:
                var.VOTES[nick] = var.VOTES.pop(prefix)
            for v in var.VOTES.values():
                if prefix in v:
                    v.remove(prefix)
                    v.append(nick)
    else:
        return


def leave(cli, what, nick, why=""):
    """Exit the game."""
    if why and why == botconfig.CHANGING_HOST_QUIT_MESSAGE:
        return
    if var.PHASE == "none" and what.startswith(botconfig.CMD_CHAR):
        cli.notice(nick, "No game is currently running.")
        return
    elif var.PHASE == "none":
        return
    if nick not in var.list_players() and what.startswith(botconfig.CMD_CHAR):  # not playing
        cli.notice(nick, "You're not currently playing.")
        return
    elif nick not in var.list_players():
        return
    msg = ""
    if what in (botconfig.CMD_CHAR+"quit", botconfig.CMD_CHAR+"leave"):
        msg = ("\u0002{0}\u0002 died of an unknown disease. "+
               "S/He was a \u0002{1}\u0002.")
    elif what == "part":
        msg = ("\u0002{0}\u0002 died due to eating poisonous berries. "+
               "Appears (s)he was a \u0002{1}\u0002.")
    elif what == "quit":
        msg = ("\u0002{0}\u0002 died due to a fatal attack by wild animals. "+
               "Appears (s)he was a \u0002{1}\u0002.")
    elif what == "kick":
        msg = ("\u0002{0}\u0002 died due to falling off a cliff. "+
               "Appears (s)he was a \u0002{1}\u0002.")
    msg = msg.format(nick, var.get_role(nick))
    cli.msg(botconfig.CHANNEL, msg)
    del_player(cli, nick)

cmd("leave")(lambda cli, nick, *rest: leave(cli, botconfig.CMD_CHAR+"leave", nick))
cmd("quit")(lambda cli, nick, *rest: leave(cli, botconfig.CMD_CHAR+"quit", nick))
#Functions decorated with hook do not parse the nick by default
hook("part")(lambda cli, nick, *rest: leave(cli, "part", parse_nick(nick)[0]))
hook("quit")(lambda cli, nick, *rest: leave(cli, "quit", parse_nick(nick)[0], rest[0]))
hook("kick")(lambda cli, nick, *rest: leave(cli, "kick", parse_nick(rest[1])[0]))



def begin_day(cli):
    chan = botconfig.CHANNEL

    # Reset nighttime variables
    var.VICTIM = ""  # nickname of kill victim
    var.ACTED_WOLVES = set()
    var.GUARDED = ""
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    var.GUARDED = {}

    cli.msg(chan, ("The villagers must now vote for whom to lynch. "+
                   'Use "{0}lynch <nick>" to cast your vote. 3 votes '+
                   'are required to lynch.').format(botconfig.CMD_CHAR))

    if var.DAY_TIME_LIMIT > 0:  # Time limit enabled
        var.DAY_ID = timetime()
        t = threading.Timer(var.DAY_TIME_LIMIT, hurry_up, [cli, var.DAY_ID])
        var.TIMERS[1] = t
        var.TIMERS[1].daemon = True
        t.start()



def transition_day(cli, gameid=0):
    if gameid:
        if gameid != var.NIGHT_ID:
            return
    var.NIGHT_ID = 0
    var.PHASE = "day"
    var.GOATED = False
    chan = botconfig.CHANNEL

    if not len(var.SEEN)+len(var.ACTED_WOLVES) and var.FIRST_NIGHT and var.ROLES["seer"]:
        cli.msg(botconfig.CHANNEL, ("\u0002{0}\u0002, a \u0002wolf\u0002, and \u0002{1}\u0002, a \u0002seer\u0002 "+
                                    "were both found dead in their beds.").format(var.ROLES["wolf"][0],
                                                                                  var.ROLES["seer"][0]))
        for x in (var.ROLES["wolf"][0],var.ROLES["seer"][0]):
            del_player(cli, x, True)  # kill them.
        chk_win(cli)  # force to end
        return

    # Reset daytime variables
    var.VOTES = {}
    var.INVESTIGATED = []
    var.WOUNDED = []
    var.DAY_START_TIME = datetime.now()

    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    message = [("Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. "+
               "The villagers awake, thankful for surviving the night, "+
               "and search the village... ").format(min, sec)]
    dead = []
    crowonly = var.ROLES["werecrow"] and not var.ROLES["wolf"]
    for crow, target in iter(var.OBSERVED.items()):
        if target in list(var.HVISITED.keys())+var.SEEN+list(var.GUARDED.keys()):
            cli.msg(crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was not in "+
                          "bed at night, and you fly back to your house.").format(target))
        elif target not in var.ROLES["village drunk"]:
            cli.msg(crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was sleeping "+
                          "all night long, and you fly back to your house.").format(target))
    if var.VICTIM in var.GUARDED.values():
        message.append(("\u0002{0}\u0002 was attacked by the wolves last night, but luckily, the "+
                        "guardian angel protected him/her.").format(var.VICTIM))
        var.VICTIM = ""
    elif not var.VICTIM:
        message.append(random.choice(var.NO_VICTIMS_MESSAGES) +
                    " All villagers, however, have survived.")
    elif var.VICTIM in var.ROLES["harlot"]:  # Attacked harlot, yay no kill
        if var.HVISITED.get(var.VICTIM):
            message.append("The wolves' selected victim was a harlot, "+
                           "but she wasn't home.")
    elif var.VICTIM in var.GUNNERS.keys() and var.GUNNERS[var.VICTIM]:  # victim had bullets!
        if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
            wc = var.ROLES["werecrow"]
            for crow in wc:
                if crow in var.OBSERVED.keys():
                    wc.remove(crow)
            # don't kill off werecrows that observed
            deadwolf = random.choice(var.ROLES["wolf"]+wc)
            message.append(("The wolves made the fortunate mistake of attacking "+
                            "a gunner last night, and \u0002{0}\u0002, a \u0002wolf\u0002,"+
                            " was shot dead.").format(deadwolf))
            dead.append(deadwolf)
            var.VICTIM = ""
    if var.VICTIM and (var.VICTIM not in var.ROLES["harlot"] or   # not a harlot
                          not var.HVISITED.get(var.VICTIM)):   # harlot stayed home
        message.append(("The dead body of \u0002{0}\u0002, a "+
                        "\u0002{1}\u0002, is found. Those remaining mourn his/her "+
                        "death.").format(var.VICTIM, var.get_role(var.VICTIM)))
        dead.append(var.VICTIM)
    if var.VICTIM in var.HVISITED.values():  #  victim was visited by some harlot
        for hlt in var.HVISITED.keys():
            if var.HVISITED[hlt] == var.VICTIM:
                message.append(("\u0002{0}\u0002, a harlot, made the unfortunate mistake of "+
                                "visiting the victim's house last night and is "+
                                "now dead.").format(hlt))
                dead.append(hlt)
    for harlot in var.ROLES["harlot"]:
        if var.HVISITED.get(harlot) in var.ROLES["wolf"]+var.ROLES["werecrow"]:
            message.append(("\u0002{0}\u0002, a harlot, made the unfortunate mistake of "+
                            "visiting a wolf's house last night and is "+
                            "now dead.").format(harlot))
            dead.append(harlot)
    for gangel in var.ROLES["guardian angel"]:
        if var.GUARDED.get(gangel) in var.ROLES["wolf"]+var.ROLES["werecrow"]:
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                message.append(("\u0002{0}\u0002, a guardian angel, "+
                                "made the unfortunate mistake of guarding a wolf "+
                                "last night, attempted to escape, but failed "+
                                "and is now dead.").format(gangel))
                dead.append(gangel)
    for crow, target in iter(var.OBSERVED.items()):
        if (target in var.ROLES["harlot"] and
            target in var.HVISITED.keys() and
            target not in dead):
            # Was visited by a crow
            cli.msg(target, ("You suddenly remember that you were startled by the loud "+
                            "sound of the flapping of wings during the walk back home."))
        elif target in var.ROLES["village drunk"]:
            # Crow dies because of tiger (HANGOVER)
            cli.msg(chan, ("The bones of \u0002{0}\u0002, a werecrow, "+
                           "were found near the village drunk's house. "+
                           "The drunk's pet tiger probably ate him.").format(crow))
            dead.append(crow)
    cli.msg(chan, "\n".join(message))
    for deadperson in dead:
        if not del_player(cli, deadperson):
            return
    begin_day(cli)


def chk_nightdone(cli):
    if (len(var.SEEN) == len(var.ROLES["seer"]) and  # Seers have seen.
        len(var.HVISITED.keys()) == len(var.ROLES["harlot"]) and  # harlots have visited.
        len(var.GUARDED.keys()) == len(var.ROLES["guardian angel"]) and  # guardians have guarded
        len(var.ROLES["werecrow"]+var.ROLES["wolf"]) == len(var.ACTED_WOLVES) and
        var.PHASE == "night"):
        if var.TIMERS[0]:
            var.TIMERS[0].cancel()  # cancel timer
            var.TIMERS[0] = None
        if var.PHASE == "night":  # Double check
            transition_day(cli)



@cmd("lynch", "vote")
def vote(cli, nick, chan, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    pl = var.list_players()
    pl_l = [x.strip().lower() for x in pl]
    rest = re.split(" +",rest)[0].strip().lower()
    if rest in pl_l:
        if nick in var.WOUNDED:
            cli.msg(chan, ("{0}: You are wounded and resting, "+
                          "thus you are unable to vote for the day."))
        voted = pl[pl_l.index(rest)]
        lcandidates = list(var.VOTES.keys())
        for voters in lcandidates:  # remove previous vote
            if nick in var.VOTES[voters]:
                var.VOTES[voters].remove(nick)
                if not var.VOTES.get(voters) and voters != voted:
                    del var.VOTES[voters]
                break
        if voted not in var.VOTES.keys():
            var.VOTES[voted] = [nick]
        else:
            var.VOTES[voted].append(nick)
        cli.msg(chan, ("\u0002{0}\u0002 votes for "+
                       "\u0002{1}\u0002.").format(nick, voted))
        chk_decision(cli)
    elif not rest:
        cli.notice(nick, "Not enough parameters.")
    else:
        cli.notice(nick, "\u0002{0}\u0002 is currently not playing.".format(rest))



@cmd("retract")
def retract(cli, nick, chan, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return

    candidates = var.VOTES.keys()
    for voter in list(candidates):
        if nick in var.VOTES[voter]:
            var.VOTES[voter].remove(nick)
            if not var.VOTES[voter]:
                del var.VOTES[voter]
            cli.msg(chan, "\u0002{0}\u0002 retracted his/her vote.".format(nick))
            break
    else:
        cli.notice(nick, "You haven't voted yet.")



@cmd("shoot")
def shoot(cli, nick, chan, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if var.PHASE != "day":
        cli.notice(nick, ("Shooting is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    if nick not in var.GUNNERS.keys():
        cli.msg(nick, "You don't have a gun.")
        return
    elif not var.GUNNERS[nick]:
        cli.msg(nick, "You don't have any more bullets.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        cli.notice(nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.notice(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]
    
    var.GUNNERS[nick] -= 1
    
    rand = random.random()
    if nick in var.ROLES["village drunk"]:
        chances = var.DRUNK_GUN_CHANCES
    else:
        chances = var.GUN_CHANCES
    if rand <= chances[0]:
        cli.msg(chan, ("\u0002{0}\u0002 shoots \u0002{1}\u0002 with "+
                       "a silver bullet!").format(nick, victim))
        victimrole = var.get_role(victim)
        if victimrole in ("wolf", "werecrow"):
            cli.msg(chan, ("\u0002{0}\u0002 is a wolf, and is dying from "+
                           "the silver bullet.").format(victim))
            if not del_player(cli, victim):
                return
        elif random.random() <= var.MANSLAUGHTER_CHANCE:
            cli.msg(chan, ("\u0002{0}\u0002 is a not a wolf "+
                           "but was accidentally fatally injured.").format(victim))
            cli.msg(chan, "Appears (s)he was a \u0002{0}\u0002.".format(victimrole))
            if not del_player(cli, victim):
                return
        else:
            cli.msg(chan, ("\u0002{0}\u0002 is a villager and is injured but "+
                          "will have a full recovery. S/He will be resting "+
                          "for the day.").format(victim))
            var.WOUNDED.append(victim)
            chk_decision(cli)
    elif rand <= chances[0] + chances[1]:
        cli.msg(chan, "\u0002{0}\u0002 is a lousy shooter.  S/He missed!".format(nick))
    else:
        cli.msg(chan, ("\u0002{0}\u0002 should clean his/her weapons more often. "+
                      "The gun exploded and killed him/her!").format(nick))
        cli.msg(chan, "Appears that (s)he was a \u0002{0}\u0002.".format(var.get_role(nick)))
        if not del_player(cli, nick):
            return  # Someone won.



@pmcmd("kill")
def kill(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role not in ('wolf', 'werecrow'):
        cli.msg(nick, "Only a wolf may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only kill people at night.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if role == "werecrow":  # Check if flying to observe
        if var.OBSERVED.get(nick):
            cli.msg(nick, ("You are flying to \u0002{0}'s\u0002 house, and "+
                          "therefore you don't have the time "+
                          "and energy to kill a villager.").format(var.OBSERVED[nick]))
            return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if victim == nick.lower():
        cli.msg(nick, "Suicide is bad.  Don't do it.")
        return
    if victim in var.ROLES["wolf"]+var.ROLES["traitor"]+var.ROLES["werecrow"]:
        cli.msg(nick, "You may only kill villagers, not other wolves")
        return
    var.VICTIM = pl[pll.index(victim)]
    cli.msg(nick, "You have selected \u0002{0}\u0002 to be killed".format(var.VICTIM))
    var.ACTED_WOLVES.add(nick)
    chk_nightdone(cli)


@pmcmd("guard")
def guard(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    role = var.get_role(nick)
    if role != 'guardian angel':
        cli.msg(nick, "Only a guardian angel may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only protect people at night.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if var.GUARDED.get(nick):
        cli.msg(nick, ("You are already protecting "+
                      "\u0002{0}\u0002.").format(var.GUARDED[nick]))
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if victim == nick.lower():
        cli.msg(nick, "You may not guard yourself.")
        return
    var.GUARDED[nick] = pl[pll.index(victim)]
    cli.msg(nick, "You are protecting \u0002{0}\u0002 tonight. Farewell!".format(var.GUARDED[nick]))
    cli.msg(victim, "You can sleep well tonight, for a guardian angel is protecting you.")
    chk_nightdone(cli)



@pmcmd("observe")
def observe(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "werecrow"):
        cli.msg(nick, "Only a werecrow may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only transform into a crow at night.")
        return
    victim = re.split(" +", rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.msg(nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]
    if victim == nick.lower():
        cli.msg(nick, "Instead of doing that, you should probably go kill someone.")
        return
    if var.get_role(victim) in ("werecrow", "traitor", "wolf"):
        cli.msg(nick, "Flying to another wolf's house is a waste of time.")
        return
    var.OBSERVED[nick] = victim
    var.ACTED_WOLVES.add(nick)
    cli.msg(nick, ("You transform into a large crow and start your flight "+
                   "to \u0002{0}'s\u0002 house. You will return after "+
                  "collecting your observations when day begins.").format(victim))



@pmcmd("id")
def investigate(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "detective"):
        cli.msg(nick, "Only a detective may use this command.")
        return
    if var.PHASE != "day":
        cli.msg(nick, "You may only investigate people during the day.")
        return
    if nick in var.INVESTIGATED:
        cli.msg(nick, "You may only investigate one person per round.")
        return
    victim = re.split(" +", rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.msg(nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]

    var.INVESTIGATED.append(nick)
    cli.msg(nick, ("The results of your investigation have returned. \u0002{0}\u0002"+
                   " is a... \u0002{1}\u0002!").format(victim, var.get_role(victim)))
    if random.random() < var.DETECTIVE_REVEALED_CHANCE:  # a 2/5 chance (should be changeable in settings)
        # Reveal his role!
        for badguy in var.ROLES["wolf"] + var.ROLES["werecrow"] + var.ROLES["traitor"]:
            cli.msg(badguy, ("\u0002{0}\u0002 accidentally drops a paper. The paper reveals "+
                            "that (s)he is the detective!").format(nick))



@pmcmd("visit")
def hvisit(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "harlot"):
        cli.msg(nick, "Only a harlot may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only visit someone at night.")
        return
    if var.HVISITED.get(nick):
        cli.msg(nick, ("You are already spending the night "+
                      "with \u0002{0}\u0002.").format(var.HVISITED[nick]))
        return
    victim = re.split(" +",rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    pl = [x.lower() for x in var.list_players()]
    if victim not in pl:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if nick.lower() == victim:  # Staying home
        var.HVISITED[nick] = None
        cli.msg(nick, "You have chosen to stay home for the night.")
    else:
        var.HVISITED[nick] = var.list_players()[pl.index(victim)]
        cli.msg(nick, ("You are spending the night with \u0002{0}\u0002. "+
                      "Have a good time!").format(victim))
        if var.HVISITED[nick] not in var.ROLES["wolf"]:
            cli.msg(var.HVISITED[nick], ("You are spending the night with \u0002{0}"+
                                          "\u0002. Have a good time!").format(nick))
    chk_nightdone(cli)


def is_fake_nick(who):
    return not( ((who[0].isalpha() or (who[0] in (botconfig.CMD_CHAR, "\\", "_", "`"))) and
              not who.lower().endswith("serv")))



@pmcmd("see")
def see(cli, nick, rest):
    if var.PHASE in ("none", "join"):
        cli.notice(nick, "No game is currently running.")
        return
    elif nick not in var.list_players():
        cli.notice(nick, "You're not currently playing.")
        return
    if not var.is_role(nick, "seer"):
        cli.msg(nick, "Only a seer may use this command")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only have visions at night.")
        return
    if nick in var.SEEN:
        cli.msg(nick, "You may only have one vision per round.")
        return
    victim = re.split(" +",rest)[0].strip().lower()
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if victim not in pll:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]
    if victim in var.CURSED:
        role = "wolf"
    elif var.get_role(victim) == "traitor":
        role = "villager"
    else:
        role = var.get_role(victim)
    cli.msg(nick, ("You have a vision; in this vision, "+
                    "you see that \u0002{0}\u0002 is a "+
                    "\u0002{1}\u0002!").format(victim, role))
    var.SEEN.append(nick)
    chk_nightdone(cli)



@hook("featurelist")  # For multiple targets with PRIVMSG
def getfeatures(cli, nick, *rest):
    var.MAX_PRIVMSG_TARGETS = 1
    for r in rest:
        if r.startswith("TARGMAX="):
            x = r[r.index("PRIVMSG:"):]
            if "," in x:
                l = x[x.index(":")+1:x.index(",")]
            else:
                l = x[x.index(":")+1:]
            l = l.strip()
            if not l or not l.isdigit():
                continue
            else:
                var.MAX_PRIVMSG_TARGETS = int(l)
                break




@pmcmd("")
def relay(cli, nick, rest):
    if var.PHASE != "night":
        return
    badguys = var.ROLES["wolf"] + var.ROLES["traitor"] + var.ROLES["werecrow"]
    if len(badguys) > 1:
        if nick in badguys:
            badguys.remove(nick)  #  remove self from list
            while badguys:
                if len(badguys) <= var.MAX_PRIVMSG_TARGETS:
                    bgs = ",".join(badguys)
                    badguys = []
                else:
                    bgs = ",".join(badguys[0:var.MAX_PRIVMSG_TARGETS])
                    badguys = badguys[var.MAX_PRIVMSG_TARGETS:]
                cli.msg(bgs, "{0} says: {1}".format(nick, rest))



def transition_night(cli):
    var.PHASE = "night"

    if var.TIMERS[1]:  # cancel daytime-limit timer
        var.TIMERS[1].cancel()
        var.TIMERS[1] = None

    var.FIRST_NIGHT = (var.ROLES == var.ORIGINAL_ROLES)

    # Reset nighttime variables
    var.VICTIM = ""  # nickname of kill victim
    var.ACTED_WOLVES = set()
    var.GUARDED = {}  # key = by whom, value = the person that is visited
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    var.NIGHT_START_TIME = datetime.now()

    daydur_msg = ""

    if var.NIGHT_TIMEDELTA or var.START_WITH_DAY:  #  transition from day
        td = var.NIGHT_START_TIME - var.DAY_START_TIME
        var.DAY_START_TIME = None
        var.DAY_TIMEDELTA += td
        min, sec = td.seconds // 60, td.seconds % 60
        daydur_msg = "Day lasted \u0002{0:0>2}:{1:0>2}\u0002. ".format(min,sec)

    chan = botconfig.CHANNEL

    if var.NIGHT_TIME_LIMIT > 0:
        var.NIGHT_ID = timetime()
        t = threading.Timer(var.NIGHT_TIME_LIMIT, transition_day, [cli, var.NIGHT_ID])
        var.TIMERS[0] = t
        var.TIMERS[0].daemon = True
        t.start()

    # send PMs
    ps = var.list_players()
    wolves = var.ROLES["wolf"]+var.ROLES["traitor"]+var.ROLES["werecrow"]
    for wolf in wolves:
        if wolf in var.ROLES["wolf"]:
            cli.msg(wolf, ('You are a \u0002wolf\u0002. It is your job to kill all the '+
                           'villagers. Use "kill <nick>" to kill a villager.'))
        elif wolf in var.ROLES["traitor"]:
            cli.msg(wolf, ('You are a \u0002traitor\u0002. You are exactly like a '+
                           'villager and not even a seer can see your true identity. '+
                           'Only detectives can. '))
        else:
            cli.msg(wolf, ('You are a \u0002werecrow\u0002.  You are able to fly at night. '+
                           'Use "kill <nick>" to kill a a villager.  Alternatively, you can '+
                           'use "observe <nick>" to check if someone is in bed or not. '+
                           'Observing will prevent you participating in a killing.'))
        if len(wolves) > 1:
            cli.msg(wolf, 'Also, if you PM me, your message will be relayed to other wolves.')
        pl = ps[:]
        pl.remove(wolf)  # remove self from list
        for i, player in enumerate(pl):
            if player in var.ROLES["wolf"]:
                pl[i] = player + " (wolf)"
            elif player in var.ROLES["traitor"]:
                pl[i] = player + " (traitor)"
            elif player in var.ROLES["werecrow"]:
                pl[i] = player + " (werecrow)"
        cli.msg(wolf, "\u0002Players:\u0002 "+", ".join(pl))

    for seer in var.ROLES["seer"]:
        pl = ps[:]
        pl.remove(seer)  # remove self from list
        cli.msg(seer, ('You are a \u0002seer\u0002. '+
                      'It is your job to detect the wolves, you '+
                      'may have a vision once per night. '+
                      'Use "see <nick>" to see the role of a player.'))
        cli.msg(seer, "Players: "+", ".join(pl))

    for harlot in var.ROLES["harlot"]:
        pl = ps[:]
        pl.remove(harlot)
        cli.msg(harlot, ('You are a \u0002harlot\u0002. '+
                         'You may spend the night with one person per round. '+
                         'If you visit a victim of a wolf, or visit a wolf, '+
                         'you will die. Use !visit to visit a player.'))
        cli.msg(harlot, "Players: "+", ".join(pl))

    for g_angel in var.ROLES["guardian angel"]:
        pl = ps[:]
        pl.remove(g_angel)
        cli.msg(g_angel, ('You are a \u0002guardian angel\u0002. '+
                          'It is your job to protect the villagers. If you guard a'+
                          ' wolf, there is a 50/50 chance of you dying, if you guard '+
                          'a victim, they will live. Use !guard to guard a player.'));
        cli.msg(g_angel, "Players: " + ", ".join(pl))
    for dttv in var.ROLES["detective"]:
        cli.msg(dttv, ("You are a \u0002detective\u0002.\n"+
                      "It is your job to determine all the wolves and traitors. "+
                      "Your job is during the day, and you can see the true "+
                      "identity of all users, even traitors."))
    for d in var.ROLES["village drunk"]:
        cli.msg(d, 'You have been drinking too much! You are the \u0002village drunk\u0002.')

    for g in tuple(var.GUNNERS.keys()):
        gun_msg =  ("You hold a gun that shoots special silver bullets. You may only use it "+
                    "during the day. If you shoot a wolf, (s)he will die instantly, but if you "+
                    "shoot a villager, that villager will likely survive. You get {0}.")
        if var.GUNNERS[g] == 1:
            gun_msg = gun_msg.format("1 bullet")
        elif var.GUNNERS[g] > 1:
            gun_msg = gun_msg.format(str(var.GUNNERS[g]) + " bullets")
        else:
            continue
        cli.msg(g, gun_msg)

    cli.msg(chan, (daydur_msg + "It is now nighttime. All players "+
                   "check for PMs from me for instructions. "+
                   "If you did not receive one, simply sit back, "+
                   "relax, and wait patiently for morning."))

    # cli.msg(chan, "DEBUG: "+str(var.ROLES))
    if not var.ROLES["wolf"]:  # Probably something interesting going on.
        chk_nightdone(cli)
        chk_traitor(cli)



def cgamemode(cli, *args):
    chan = botconfig.CHANNEL
    for arg in args:
        modeargs = arg.split("=", 1)
        modeargs[0] = modeargs[0].strip()
        if modeargs[0] in var.GAME_MODES.keys():
            md = modeargs.pop(0)
            modeargs[0] = modeargs[0].strip()
            try:
                gm = var.GAME_MODES[md](modeargs[0])
                for attr in dir(gm):
                    val = getattr(gm, attr)
                    if (hasattr(var, attr) and not callable(val)
                                            and not attr.startswith("_")):
                        var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)
                        setattr(var, attr, val)
                return True
            except var.InvalidModeException as e:
                cli.msg(botconfig.CHANNEL, "Invalid mode: "+str(e))
                return False
        else:
            cli.msg(chan, "Mode \u0002{0}\u0002 not found.".format(modeargs[0]))


@cmd("start")
def start(cli, nick, chan, rest):
    villagers = var.list_players()

    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in villagers:
        cli.notice(nick, "You're currently not playing.")
        return
    now = datetime.now()
    var.GAME_START_TIME = now  # Only used for the idler checker
    dur = int((var.CAN_START_TIME - now).total_seconds())
    if dur > 0:
        cli.msg(chan, "Please wait at least {0} more seconds.".format(dur))
        return

    if len(villagers) < 4:
        cli.msg(chan, "{0}: Four or more players are required to play.".format(nick))
        return

    for pcount in range(len(villagers), 3, -1):
        addroles = var.ROLES_GUIDE.get(pcount)
        if addroles:
            break

    if var.ORIGINAL_SETTINGS:  # Custom settings
        while True:
            wvs = (addroles[var.INDEX_OF_ROLE["wolf"]] +
                  addroles[var.INDEX_OF_ROLE["traitor"]])
            if len(villagers) < (sum(addroles) - addroles[var.INDEX_OF_ROLE["gunner"]] -
                    addroles[var.INDEX_OF_ROLE["cursed"]]):
                cli.msg(chan, "There are too few players in the "+
                              "game to use the custom roles.")
            elif not wvs:
                cli.msg(chan, "There has to be at least one wolf!")
            elif wvs > (len(villagers) / 2):
                cli.msg(chan, "Too many wolves.")
            else:
                break
            reset_settings()
            cli.msg(chan, "The default settings have been restored.  Please !start again.")
            var.PHASE = "join"
            return


    var.ROLES = {}
    var.CURSED = []
    var.GUNNERS = {}

    villager_roles = ("gunner", "cursed")
    for i, count in enumerate(addroles):
        role = var.ROLE_INDICES[i]
        if role in villager_roles:
            var.ROLES[role] = [None] * count
            continue # We deal with those later, see below
        selected = random.sample(villagers, count)
        var.ROLES[role] = selected
        for x in selected:
            villagers.remove(x)

    # Now for the villager roles
    # Select cursed (just a villager)
    if var.ROLES["cursed"]:
        var.CURSED = random.sample((villagers +  # harlot and drunk can be cursed
                                     var.ROLES["harlot"] +
                                     var.ROLES["village drunk"]),
                                     len(var.ROLES["cursed"]))
    del var.ROLES["cursed"]
    # Select gunner (also a villager)
    if var.ROLES["gunner"]:
        possible = (villagers +
                   var.ROLES["harlot"] +
                   var.ROLES["village drunk"] +
                   var.ROLES["seer"])
        for csd in var.CURSED:
            if csd in possible:
                possible.remove(csd)
        for gnr in random.sample(possible, len(var.ROLES["gunner"])):
            if var.ROLES["village drunk"] == gnr:
                var.GUNNERS[gnr] = var.DRUNK_SHOTS_MULTIPLIER * var.MAX_SHOTS
            else:
                var.GUNNERS[gnr] = var.MAX_SHOTS
    del var.ROLES["gunner"]

    var.ROLES["villager"] = villagers

    cli.msg(chan, ("{0}: Welcome to Werewolf, the popular detective/social party "+
                   "game (a theme of Mafia).").format(", ".join(var.list_players())))
    cli.mode(chan, "+m")

    var.ORIGINAL_ROLES = copy.deepcopy(var.ROLES)  # Make a copy
    var.DAY_TIMEDELTA = timedelta(0)
    var.NIGHT_TIMEDELTA = timedelta(0)
    var.DAY_START_TIME = None
    var.NIGHT_START_TIME = None


    if not var.START_WITH_DAY:
        transition_night(cli)
    else:
        transition_day(cli)

    # DEATH TO IDLERS!
    reapertimer = threading.Thread(None, reaper, args=(cli,var.GAME_ID))
    reapertimer.daemon = True
    reapertimer.start()


@cmd("game", admin_only=var.GAME_COMMAND_ADMIN_ONLY)
def game(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    if nick in var.DENIED_SETTINGS_CHANGE:
        cli.notice(nick, "You cannot vote because your previous "+
                         "settings change was denied by vote.")
        return
    if var.SETTINGS_CHANGE_REQUESTER:
        cli.notice(nick, "There is already an existing "+
                         "settings change request.")
        return
    rest = rest.strip().lower()
    if rest:
        if cgamemode(cli, *re.split(" +",rest)):
            var.SETTINGS_CHANGE_REQUESTER = nick
            cli.msg(chan, ("\u0002{0}\u0002 has changed the "+
                            "game settings successfully. To "+
                            'oppose this change, use "{1}no".').format(nick, botconfig.CMD_CHAR))
            if var.CAN_START_TIME <= datetime.now():
                var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.EXTRA_WAIT) * 2
                cli.msg(chan, "The wait time has also been extended.")


@cmd("no")
def nay(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE != "join" or not var.SETTINGS_CHANGE_REQUESTER:
        cli.notice(nick, "This command is only allowed if there is "+
                   "a game settings change request in effect.")
        return
    if nick not in pl:
        cli.notice(nick, "You're not currently playing.")
        return
    if var.SETTINGS_CHANGE_REQUESTER in pl:
        pl.remove(var.SETTINGS_CHANGE_REQUESTER)
    if nick in var.SETTINGS_CHANGE_OPPOSITION:
        cli.notice(nick, "You are already in the opposition.")
        return
    var.SETTINGS_CHANGE_OPPOSITION.append(nick)
    needed = max(len(pl)//2 + 1, 2)
    if len(var.SETTINGS_CHANGE_OPPOSITION) >= needed:
        cli.msg(chan, "The settings change request has been downvoted "+
                      "to oblivion.  The default settings are restored.")
        var.DENIED_SETTINGS_CHANGE.append(var.SETTINGS_CHANGE_REQUESTER)
        reset_settings()
    else:
        cli.msg(chan, ("\u0002{0}\u0002 has voted \u0002no\u0002. {1} more "+
                      "vote{2} are needed to deny the change.").format(nick,
                       needed - len(var.SETTINGS_CHANGE_OPPOSITION),
                      "s" if needed > len(var.SETTINGS_CHANGE_OPPOSITION) + 1 else ""))



@cmd("wait")
def wait(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    if var.WAITED >= var.MAXIMUM_WAITED:
        cli.msg(chan, "Limit has already been reached for extending the wait time.")
        return

    now = datetime.now()
    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT)
    else:
        var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT)
    var.WAITED += 1
    cli.msg(chan, ("\u0002{0}\u0002 increased the wait time by "+
                  "{1} seconds.").format(nick, var.EXTRA_WAIT))



@cmd("fwait", admin_only=True)
def fwait(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return

    now = datetime.now()
    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT)
    else:
        var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT)
    var.WAITED += 1
    cli.msg(chan, ("\u0002{0}\u0002 increased the wait time by "+
                  "{1} seconds.").format(nick, var.EXTRA_WAIT))


@cmd("fstop",admin_only=True)
def reset_game(cli, nick, chan, rest):
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    cli.msg(chan, "\u0002{0}\u0002 has forced the game to stop.".format(nick))
    stop_game(cli)


@pmcmd("rules")
def pm_rules(cli, nick, rest):
    cli.msg(nick, var.RULES)

@cmd("rules")
def show_rules(cli, nick, chan, rest):
    cli.msg(chan, var.RULES)


@pmcmd("help", raw_nick = True)
def help(cli, rnick, rest):
    nick, mode, user, cloak = parse_nick(rnick)
    fns = []

    cname = rest.strip().replace(botconfig.CMD_CHAR, "").lower()
    if cname:
        for c in (COMMANDS,PM_COMMANDS):
            if cname in c.keys():
                for fn in c[cname]:
                    if fn.__doc__:
                        cli.msg(nick, fn.__doc__)
                        return
                    else:
                        continue
                else:
                    cli.msg(nick, "No documentation is available for this function.")
                return
        cli.msg(nick, "Command not found.")
    # if command was not found, or if no command was given:
    for name, fn in COMMANDS.items():
        if name and not fn[0].admin_only and not fn[0].owner_only:
            fns.append("\u0002"+name+"\u0002")
    afns = []
    if cloak in botconfig.ADMINS:
        for name, fn in COMMANDS.items():
            if fn[0].admin_only:
                afns.append("\u0002"+name+"\u0002")
    cli.notice(nick, "Commands: "+", ".join(fns))
    if afns:
        cli.notice(nick, "Admin Commands: "+", ".join(afns))



@cmd("help", raw_nick = True)
def help2(cli, nick, chan, rest):
    if rest.strip():  # command was given
        help(cli, chan, rest)
    else:
        help(cli, nick, rest)


@hook("invite", raw_nick = False, admin_only = True)
def on_invite(cli, nick, something, chan):
    if chan == botconfig.CHANNEL:
        cli.join(chan)



@cmd("admins")
def show_admins(cli, nick, chan, rest):
    """Pings the admins that are available."""
    admins = []

    @hook("whoreply")
    def on_whoreply(cli, server, dunno, chan, dunno1,
                    cloak, dunno3, user, status, dunno4):
        if ((cloak in botconfig.ADMINS or cloak == botconfig.OWNER) and 'G' not in status and
            user != botconfig.NICK and cloak not in var.AWAY):
            admins.append(user)



    @hook("endofwho")
    def show(*args):
        cli.msg(chan, "Available admins: "+" ".join(admins))

        HOOKS.pop("whoreply")  # todo, makes this better :(
        HOOKS.pop("endofwho")

    cli.who(chan)



@cmd("coin")
def coin(cli, nick, chan, rest):
    """Ugh"""
    cli.msg(chan, "\2{0}\2 tosses a coin into the air...".format(nick))
    cli.msg(chan, "The coin lands on \2{0}\2.".format("heads" if random.random() < 0.5 else "tails"))


if var.DEBUG_MODE:
    @cmd("revealroles", admin_only=True)
    def revroles(cli, nick, chan, rest):
        cli.msg(chan, str(var.ROLES))
        #TODO: make this and other functions debug-mode only



    @cmd("force", admin_only=True)
    def forcepm(cli, nick, chan, rest):
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
            return
        who = rst.pop(0).strip()
        if not who or who == botconfig.NICK:
            cli.msg(chan, "That won't work.")
            return
        if not is_fake_nick(who):
            if who not in var.USERS:
                cli.msg(chan, "This can only be done on fake nicks.")
                return
        cmd = rst.pop(0).lower().replace(botconfig.CMD_CHAR, "", 1)
        if cmd in PM_COMMANDS.keys() and not PM_COMMANDS[cmd][0].owner_only:
            for fn in PM_COMMANDS[cmd]:
                fn(cli, who, " ".join(rst))
            cli.msg(chan, "Operation successful.")
            #if var.PHASE == "night":   <-  Causes problems with night starting twice.
            #    chk_nightdone(cli)
        elif cmd.lower() in COMMANDS.keys() and not COMMANDS[cmd][0].owner_only:
            for fn in COMMANDS[cmd]:
                fn(cli, who, chan, " ".join(rst))
            cli.msg(chan, "Operation successful.")
        else:
            cli.msg(chan, "That command was not found.")



    @cmd("frole", admin_only=True)
    def frole(cli, nick, chan, rest):
        rst = re.split(" +",rest)
        if len(rst) < 2:
            cli.msg(chan, "The syntax is incorrect.")
        who = rst.pop(0).strip()
        rol = " ".join(rst).strip()
        ull = [u.lower() for u in var.USERS]
        if who.lower() not in ull:
            if not is_fake_nick(who):
                cli.msg(chan, "Could not be done.")
                cli.msg(chan, "The target needs to be in this channel or a fake name.")
                return
        if not is_fake_nick(who):
            who = var.USERS[ull.index(who.lower())]
        if who == botconfig.NICK or not who:
            cli.msg(chan, "No.")
            return
        if rol not in var.ROLES.keys():
            pl = var.list_players()
            if var.PHASE not in ("night", "day"):
                cli.msg(chan, "This is only allowed in game.")
            if rol == "gunner":
                var.GUNNERS[who] = var.MAX_SHOTS
                if who not in pl:
                    var.ROLES["villager"].append(who)
            elif rol == "cursed":
                var.CURSED.append(who)
                if who not in pl:
                    var.ROLES["villager"].append(who)
            else:
                cli.msg(chan, "Not a valid role.")
                return
            cli.msg(chan, "Operation successful.")
            return
        if who in var.list_players():
            var.del_player(who)
        var.ROLES[rol].append(who)
        cli.msg(chan, "Operation successful.")
        if var.PHASE not in ('none','join'):
            chk_win(cli)
