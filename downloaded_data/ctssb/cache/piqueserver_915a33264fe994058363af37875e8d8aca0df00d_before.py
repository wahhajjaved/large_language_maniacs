# Copyright (c) Mathias Kaerlev 2011.

# This file is part of pyspades.

# pyspades is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# pyspades is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with pyspades.  If not, see <http://www.gnu.org/licenses/>.

"""
pyspades - default/featured server
"""

import sys
import os
import json

try:
    config = json.load(open('config.txt', 'rb'))
except IOError, e:
    raise SystemExit('no config.txt file found')

profile = config.get('profile', False)
iocp = config.get('iocp', True)

frozen = hasattr(sys, 'frozen')

if frozen:
    CLIENT_VERSION = int(open('client_version', 'rb').read())
    path = os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding()))
    sys.path.append(path)
else:
    sys.path.append('..')
    from pyspades.common import crc32
    CLIENT_VERSION = crc32(open('../data/client.exe', 'rb').read())

if iocp and sys.platform == 'win32':
    # install IOCP
    try:
        from twisted.internet import iocpreactor 
        iocpreactor.install()
    except ImportError:
        print '(dependencies missing for fast IOCP, using normal reactor)'

if sys.version_info < (2, 7):
    try:
        import psyco
        psyco.full()
    except ImportError:
        print '(optional: install psyco for optimizations)'

import pyspades.debug
from pyspades.server import (ServerProtocol, ServerConnection, position_data,
    grenade_packet)
from map import Map
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.python import log
from twisted.internet.stdio import StandardIO
from twisted.protocols.basic import LineReceiver
from pyspades.common import encode, decode
from pyspades.constants import *

import json
import random
import time
import commands

class ConsoleInput(LineReceiver):
    delimiter = '\n'
    protocol = None
    def __init__(self, protocol):
        self.protocol = protocol

    def lineReceived(self, line):
        self.protocol.send_chat(line)

def writelines(fp, lines):
    for line in lines:
        fp.write(line + "\r\n")

class FeatureConnection(ServerConnection):
    printable_name = None
    admin = False
    last_votekick = None
    last_switch = None
    mute = False
    login_retries = None
    god = False
    follow = None
    followable = True
    streak = 0
    best_streak = 0
    
    def on_connect(self, loader):
        if self.master:
            print '(master client connected)'
    
    def on_join(self):
        if self.protocol.motd is not None:
            self.send_lines(self.protocol.motd)
    
    def on_login(self, name):
        self.printable_name = name.encode('ascii', 'replace')
        if self.protocol.follow_attack == 'auto':
            self.follow = "attack"
        if self.protocol.join_part_messages:
            self.protocol.send_chat(
                '%s entered the game!' % self.name)
        print '%s (%s) entered the game!' % (self.printable_name, 
            self.address[0])
        self.protocol.irc_say('* %s entered the game' % self.name)
    
    def disconnect(self):
        ServerConnection.disconnect(self)
        self.drop_followers()
        if self.name is not None:
            if self.protocol.join_part_messages:
                self.protocol.send_chat('%s left the game' % self.name)
            print self.printable_name, 'disconnected!'
            self.protocol.irc_say('* %s disconnected' % self.name)
            if self.protocol.votekick_player is self:
                self.protocol.votekick_call.cancel()
                self.protocol.end_votekick(True, 'Player left the game',
                    left = True)
    
    def on_spawn(self, pos):
        if self.follow is not None:
            if self.follow == "attack":
                attackers = self.get_attackers()
                if attackers is not None:
                    attacker = random.choice(attackers)
                    self.set_location(self.get_follow_location(attacker))
            else:
                self.set_location(self.get_follow_location(self.follow))
    
    def on_command(self, command, parameters):
        log_message = '<%s> /%s %s' % (self.name, command, 
            ' '.join(parameters))
        result = commands.handle_command(self, command, parameters)
        if result is not None:
            log_message += ' -> %s' % result
            self.send_chat(result)
        print log_message.encode('ascii', 'replace')
    
    def on_block_build_attempt(self, x, y, z):
        if not self.god and not self.protocol.building:
            return False
    
    def on_block_build(self, x, y, z):
        if self.god:
            self.refill()
            if self.protocol.god_blocks is None:
                self.protocol.god_blocks = set()
            self.protocol.god_blocks.add((x, y, z))
        elif self.protocol.user_blocks is not None:
            self.protocol.user_blocks.add((x, y, z))
    
    def on_block_destroy(self, x, y, z, mode):
        if not self.god:
            if not self.protocol.building:
                return False
            is_indestructable = self.protocol.is_indestructable
            if mode == DESTROY_BLOCK:
                if is_indestructable(x, y, z):
                    return False
            elif mode == SPADE_DESTROY:
                if (is_indestructable(x, y, z) or
                is_indestructable(x, y, z + 1) or
                is_indestructable(x, y, z - 1)):
                    return False
            elif mode == GRENADE_DESTROY:
                for nade_x in xrange(x - 1, x + 2):
                    for nade_y in xrange(y - 1, y + 2):
                        for nade_z in xrange(z - 1, z + 2):
                            if is_indestructable(nade_x, nade_y, nade_z):
                                return False
    
    def on_block_removed(self, x, y, z):
        if self.protocol.user_blocks is not None:
            self.protocol.user_blocks.discard((x, y, z))
        if self.protocol.god_blocks is not None:
            self.protocol.god_blocks.discard((x, y, z))
    
    def on_hit(self, hit_amount, player):
        if not self.protocol.killing:
            self.send_chat(
                "You can't kill anyone right now! Damage is turned OFF")
            return False
        elif player.god:
            self.send_chat("You can't hurt %s! That player is in *god mode*" %
                player.name)
            return False
        if self.god:
            self.protocol.send_chat('%s, killing in god mode is forbidden!' %
                self.name, irc = True)
            self.protocol.send_chat('%s returned to being a mere human.' %
                self.name, irc = True)
            self.god = False

    def on_kill(self, killer):
        self.streak = 0
        self.airstrike = False
        if killer is None:
            return
        killer.streak += 1
        killer.best_streak = max(killer.streak, killer.best_streak)
    
    def on_grenade(self, time_left):
        if self.god:
            self.refill()
    
    def on_team_join(self, team):
        if self.protocol.teamswitch_interval and self.team is not None:
            teamswitch_interval = self.protocol.teamswitch_interval
            if teamswitch_interval == 'never':
                self.send_chat('Switching teams is not allowed')
                return False
            if (self.last_switch is not None and 
                reactor.seconds() - self.last_switch < teamswitch_interval * 60):
                self.send_chat('You must wait before switching teams again')
                return False
        if team.locked:
            self.send_chat('Team is locked.')
            return False
        balanced_teams = self.protocol.balanced_teams
        if balanced_teams:
            other_team = team.other
            if other_team.count() < team.count() + 1 - balanced_teams:
                self.send_chat('Team is full. Please join the other team')
                return False
        if self.team is not team:
            self.drop_followers()
            self.follow = None
            self.respawn_time = self.protocol.respawn_time
        self.last_switch = reactor.seconds()
    
    def on_chat(self, value, global_message):
        message = '<%s> %s' % (self.name, value)
        if self.mute:
            message = '(MUTED) %s' % message
        elif global_message:
            self.protocol.irc_say('<%s> %s' % (self.name, value))
        print message.encode('ascii', 'replace')
        if self.mute:
            self.send_chat('(Chat not sent - you are muted)')
            return False
    
    def kick(self, reason = None, silent = False):
        if not silent:
            if reason is not None:
                message = '%s was kicked: %s' % (self.name, reason)
            else:
                message = '%s was kicked' % self.name
            self.protocol.send_chat(message, irc = True)
        self.disconnect()
    
    def ban(self, reason = None, duration = None):
        reason = ': ' + reason if reason is not None else ''
        if duration is None:
            message = '%s banned%s' % (self.name, reason)
        else:
            total = duration
            days = duration / 1440
            total -= days * 1440
            hours = total / 60
            minutes = total - hours * 60
            days_s = '%s day' % days if days > 0 else None
            hours_s = '%s hour' % hours if hours > 0 else None
            minutes_s = '%s minute' % minutes if minutes > 0 else None
            if days > 1: days_s += 's'
            if hours > 1: hours_s += 's'
            if minutes > 1: minutes_s += 's'
            time = ', '.join([s for s in days_s, hours_s, minutes_s if s])
            message = '%s banned for %s%s' % (self.name, time,
                reason)
        self.protocol.send_chat(message, irc = True)
        self.protocol.add_ban(self.address[0], reason, duration)

    def get_attackers(self):
        """Return 1/4th of followable teammates
            farthest from base(by x)"""
        initial = filter(lambda player: player.hp and player.followable,
                         self.team.get_players())
        attackers = sorted(initial,
                            key=lambda player: player.world_object.position.x)
        if len(attackers) < 1:
            return None
        if self.team.id is 1:
            attackers.reverse()
        
        stripqty = int(max(1, len(attackers) / 4 ))
        attackers = attackers[-stripqty:]
        return attackers
    
    def get_followers(self):
        return [player for player in self.protocol.players.values()
            if player.follow is self]
    
    def drop_followers(self):
        for player in self.get_followers():
            player.follow = None
            player.respawn_time = player.protocol.respawn_time
            player.send_chat('You are no longer following %s.' % self.name)
    
    def get_follow_location(self, follow):
        x, y, z = (follow.position.get() if follow.hp else
            self.team.get_random_location())
        z -= 2
        return x, y, z
    
    def send_lines(self, lines):
        current_time = 0
        for line in lines:
            reactor.callLater(current_time, self.send_chat, line)
            current_time += 2
    
    def on_hack_attempt(self, reason):
        print 'Hack attempt detected from %s: %s' % (self.printable_name, 
            reason)
        self.kick(reason)
    
    # position methods
    
    def get_location(self):
        position = self.world_object.position
        return position.x, position.y, position.z
    
    def set_location(self, (x, y, z)):
        position_data.x = x
        position_data.y = y
        position_data.z = z
        position_data.player_id = self.player_id
        self.protocol.send_contained(position_data)

def encode_lines(value):
    if value is not None:
        lines = []
        for line in value:
            lines.append(encode(line))
        return lines

class FeatureProtocol(ServerProtocol):
    connection_class = FeatureConnection
    version = CLIENT_VERSION
    admin_passwords = None
    bans = None
    irc_relay = None
    balanced_teams = None
    timestamps = None
    building = True
    killing = True
    remote_console = None
    debug_log = None
    
    # votekick
    votekick_time = 120 # 2 minutes
    votekick_interval = 3 * 60 # 3 minutes
    votekick_percentage = 25.0
    votes_left = None
    votekick_player = None
    voting_player = None
    votes = None
    votekick_update_call = None
    
    map_info = None
    spawns = None
    user_blocks = None
    god_blocks = None
    
    def __init__(self, config, map):
        self.map = map.data
        self.map_info = map
        try:
            self.bans = json.load(open('bans.txt', 'rb'))
        except IOError:
            self.bans = []
        self.config = config
        self.name = config.get('name', 
            'pyspades server %s' % random.randrange(0, 2000))
        
        self.max_score = config.get('cap_limit', None)
        self.join_part_messages = config.get('join_part_messages', False)
        self.respawn_time = config.get('respawn_time', 5)
        self.follow_respawn_time = config.get('follow_respawn_time', self.respawn_time)
        self.master = config.get('master', True)
        self.friendly_fire = config.get('friendly_fire', True)
        self.friendly_fire_time = config.get('grief_friendly_fire_time', 2.0)
        self.teamswitch_interval = config.get('teamswitch_interval', 0)
        self.motd = self.format_lines(config.get('motd', None))
        self.help = self.format_lines(config.get('help', None))
        self.tips = self.format_lines(config.get('tips', None))
        self.tip_frequency = config.get('tip_frequency', 0)
        if self.tips is not None and self.tip_frequency > 0:
            reactor.callLater(self.tip_frequency * 60, self.send_tip)
        self.max_players = config.get('max_players', 20)
        self.max_connections_per_ip = config.get('max_connections_per_ip', 0)
        passwords = config.get('passwords', {})
        self.admin_passwords = passwords.get('admin', [])
        self.server_prefix = encode(config.get('server_prefix', '[*]'))
        self.balanced_teams = config.get('balanced_teams', None)
        self.rules = self.format_lines(config.get('rules', None))
        self.login_retries = config.get('login_retries', 1)
        self.default_ban_time = config.get('default_ban_time', 24*60)
        self.votekick_ban_duration = config.get('votekick_ban_duration', 15)
        self.votekick_percentage = config.get('votekick_percentage', 25)
        self.votekick_public_votes = config.get('votekick_public_votes', True)
        if config.get('user_blocks_only', False):
            self.user_blocks = set()
        self.max_followers = config.get('max_followers', 0)
        self.follow_attack = config.get('follow_attack', False)
        logfile = config.get('logfile', None)
        self.debug_log = config.get('debug_log', False)
        if self.debug_log:
            pyspades.debug.open_debug_log()
        ssh = config.get('ssh', {})
        if ssh.get('enabled', False):
            from ssh import RemoteConsole
            self.remote_console = RemoteConsole(self, ssh)
        irc = config.get('irc', {})
        if irc.get('enabled', False):
            from irc import IRCRelay
            self.irc_relay = IRCRelay(self, irc)
        status = config.get('status_server', {})
        if status.get('enabled', False):
            from statusserver import StatusServerFactory
            self.status_server = StatusServerFactory(self, status)
        publish = config.get('publish_server', {})
        if publish.get('enabled', False):
            from publishserver import PublishServerFactory
            self.publish_server = PublishServerFactory(self, publish)
        self.federated_bans = []
        ban_subscribe = config.get('ban_subscribe', [])
        for ip in ban_subscribe:
            # figure out how to pull the data...
            pass
        
        if logfile is not None and logfile.strip():
            observer = log.FileLogObserver(open(logfile, 'a'))
            log.addObserver(observer.emit)
            log.msg('pyspades server started on %s' % time.strftime('%c'))
        log.startLogging(sys.stdout) # force twisted logging
        
        if sys.platform != 'win32':
            self.console = ConsoleInput(self)
            StandardIO(self.console)
        
        for password in self.admin_passwords:
            if password == 'replaceme':
                print 'REMEMBER TO CHANGE THE DEFAULT ADMINISTRATOR PASSWORD!'
                break
        ServerProtocol.__init__(self)
        # locked teams
        self.blue_team.locked = False
        self.green_team.locked = False
    
    def is_indestructable(self, x, y, z):
        if self.user_blocks is not None:
            if (x, y, z) not in self.user_blocks:
                return True
        if self.god_blocks is not None:
            if (x, y, z) in self.god_blocks:
                return True
        return False
    
    def format_lines(self, value):
        if value is None:
            return
        map = self.map_info
        format_dict = {
            'server_name' : self.name,
            'map_name' : map.name,
            'map_author' : map.author,
            'map_description' : map.description
        }
        lines = []
        for line in value:
            lines.append(encode(line % format_dict))
        return lines
        
    def got_master_connection(self, *arg, **kw):
        print 'Master connection established.'
        ServerProtocol.got_master_connection(self, *arg, **kw)
    
    def master_disconnected(self, *arg, **kw):
        print 'Master connection lost, reconnecting in 20 seconds...'
        ServerProtocol.master_disconnected(self, *arg, **kw)
        reactor.callLater(20, self.set_master)

    def add_ban(self, ip, reason, duration):
        """Ban an ip(if it hasn't already been banned) with an optional reason and
            duration in minutes. If duration is None, ban is permanent."""
        for connection in self.connections.values():
            if connection.address[0] == ip and (len([ban for ban in self.bans
                                                     if ban[1]==ip])<=0):
                if duration:
                    self.bans.append((connection.name, ip, reason,
                                      reactor.seconds()+duration * 60))
                else:
                    self.bans.append((connection.name, ip, reason,
                                      None))
                connection.kick(silent = True)
                self.save_bans()
    
    def remove_ban(self, ip):
        print(ip)
        results = [self.bans.remove(n) for n in self.bans if n[1]==ip]
        print(results)
        self.save_bans()

    def undo_last_ban(self):
        result = self.bans.pop()
        self.save_bans()
        return result
    
    def save_bans(self):
        json.dump(self.bans, open('bans.txt', 'wb'))
    
    def datagramReceived(self, data, address):
        # simple pyspades query
        if data == 'HELLO':
            self.transport.write('HI', address)
            return
        for ban in self.bans:
            ip = ban[1]
            timestamp = ban[3]
            if address[0] == ip:
                if reactor.seconds()>=timestamp:
                    self.remove_ban(ip)
                    self.save_bans()
                else:
                    return
        for ban in self.federated_bans:
            ip = ban[1]
            timestamp = ban[3]
            if address[0] == ip:
                if reactor.seconds()>=timestamp:
                    pass
                else:
                    return
        ServerProtocol.datagramReceived(self, data, address)
        
    def irc_say(self, msg):
        if self.irc_relay:
            self.irc_relay.send(msg)
            
    def send_tip(self):
        line = self.tips[random.randrange(len(self.tips))]
        self.send_chat(line)
        reactor.callLater(self.tip_frequency * 60, self.send_tip)
    
    # votekick
    
    def start_votekick(self, connection, player, reason = None):
        if self.votes is not None:
            return 'Votekick in progress.'
        elif connection is player:
            return "You can't votekick yourself."
        elif player.admin:
            return 'Cannot votekick an administrator.'
        last_votekick = connection.last_votekick
        if (last_votekick is not None and
        reactor.seconds() - last_votekick < self.votekick_interval):
            return "You can't start a votekick now."
        votes_left = int((len(self.players) / 100.0
            ) * self.votekick_percentage)
        if votes_left == 0:
            return 'Not enough players on server.'
        self.votes_left = votes_left
        self.votes = {connection : True}
        self.votekick_call = reactor.callLater(self.votekick_time,
            self.end_votekick, False, 'Votekick timed out')
        if self.votekick_update_call is None:
            self.votekick_update_call = LoopingCall(self.votekick_update)
        self.votekick_update_call.start(30.0, now = False)
        self.irc_say(
            '* %s initiated a votekick against player %s.%s' % (connection.name,
            player.name, ' Reason: %s' % reason if reason else ''))
        self.votekick_reason = reason
        if reason is None:
            reason = 'NO REASON GIVEN'
        self.send_chat('%s initiated a VOTEKICK against player %s. Say /y to '
            'agree.' % (connection.name, player.name), sender = connection)
        self.send_chat('Reason: %s' % reason, sender = connection)
        connection.send_chat('You initiated a VOTEKICK against %s. '
            'Say /cancel to stop it at any time.' % player.name)
        connection.send_chat('Reason: %s' % reason)
        self.votekick_player = player
        self.voting_player = connection
    
    def votekick(self, connection):
        if connection is self.votekick_player:
            return "The votekick victim can't vote."
        if self.votes is None or connection in self.votes:
            return
        self.votes_left -= 1
        self.votes[connection] = True
        if self.votekick_public_votes:
            self.send_chat('%s voted YES.' % connection.name)
        if self.votes_left == 0:
            self.votekick_call.cancel()
            self.end_votekick(True, 'Player kicked')
    
    def cancel_votekick(self, connection):
        if self.votes is None:
            return 'No votekick in progress.'
        if not connection.admin and connection is not self.voting_player:
            return 'You did not start the votekick.'
        self.votekick_call.cancel()
        self.end_votekick(False, 'Cancelled by %s' % connection.name)
    
    def end_votekick(self, enough, result, left = False):
        victim = self.votekick_player
        self.votekick_player = None
        self.send_chat('Votekick for %s has ended. %s.' % (victim.name, result),
            irc = True)
        if enough:
            if self.votekick_ban_duration:
                reason = self.votekick_reason
                message = 'Left during votekick' if left else 'Votekicked'
                victim.ban(message + ' (%s)' % reason if reason else 'no reason',
                    self.votekick_ban_duration)
            else:
                victim.kick(silent = True)
        elif not self.voting_player.admin: # admins are powerful, yeah
            self.voting_player.last_votekick = reactor.seconds()
        self.votes = self.votekick_call = None
        self.voting_player = None
        self.votekick_update_call.stop()
    
    def votekick_update(self):
        reason = self.votekick_reason if self.votekick_reason else 'none'
        self.send_chat('%s is votekicking %s for reason: %s. Say /y to vote '
            '(%s needed)' % (self.voting_player.name,
            self.votekick_player.name, reason, self.votes_left))
    
    def send_chat(self, value, global_message = True, sender = None,
                  team = None, irc = False):
        if irc:
            self.irc_say('* %s' % value)
        ServerProtocol.send_chat(self, value, global_message, sender, team)

PORT = 32887

try:
    map = Map(config['map'])
except KeyError:
    raise SystemExit('no map specified!')
except IOError:
    raise SystemExit('map not found!')

# apply scripts

protocol_class = FeatureProtocol
connection_class = FeatureConnection

script_objects = []

for script in config.get('scripts', []):
    try:
        module = __import__('scripts.%s' % script, globals(), locals(), 
            [script])
        script_objects.append(module)
    except ImportError:
        pass # script not found

script_objects.append(map)

for script in script_objects:
    protocol_class, connection_class = script.apply_script(protocol_class,
        connection_class, config)

protocol_class.connection_class = connection_class

reactor.listenUDP(PORT, protocol_class(config, map), 
    config.get('network_interface', ''))
print 'Started server on port %s...' % PORT

if profile:
    import cProfile
    cProfile.run('reactor.run()', 'profile.dat')
else:
    reactor.run()