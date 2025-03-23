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

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from pyspades.protocol import (BaseConnection, sized_sequence, 
    sized_data, in_packet, out_packet)
from pyspades.bytes import ByteReader, ByteWriter
from pyspades.packet import load_client_packet
from pyspades.loaders import *
from pyspades.common import *
from pyspades.constants import *
from pyspades import serverloaders, clientloaders
from pyspades.multidict import MultikeyDict
from pyspades.idpool import IDPool
from pyspades.master import get_master_connection
from pyspades.collision import vector_collision
from pyspades import world
from pyspades.debug import *

import random
import math
import shlex
import textwrap
import collections

ORIENTATION_DISTANCE = 128.0
ORIENTATION_DISTANCE_SQUARED = 128.0 ** 2

player_data = serverloaders.PlayerData()
create_player = serverloaders.CreatePlayer()
position_data = serverloaders.PositionData()
orientation_data = serverloaders.OrientationData()
movement_data = serverloaders.MovementData()
animation_data = serverloaders.AnimationData()
hit_packet = serverloaders.HitPacket()
grenade_packet = serverloaders.GrenadePacket()
set_tool = serverloaders.SetTool()
set_color = serverloaders.SetColor()
existing_player = serverloaders.ExistingPlayer()
intel_action = serverloaders.IntelAction()
block_action = serverloaders.BlockAction()
kill_action = serverloaders.KillAction()
chat_message = serverloaders.ChatMessage()
map_data = MapData()

class ServerConnection(BaseConnection):
    master = False
    protocol = None
    is_client = False
    address = None
    player_id = None
    map_packets_sent = 0
    team = None
    weapon = None
    name = None
    kills = 0
    orientation_sequence = 0
    hp = None
    tool = None
    color = (0x70, 0x70, 0x70)
    grenades = None
    blocks = None
    spawn_call = None
    respawn_time = None
    saved_loaders = None
    last_refill = None
    last_block_destroy = None
    filter_visibility_data = False
    speedhack_detect = False
    timers = None
    world_object = None
    
    def __init__(self, protocol, address):
        BaseConnection.__init__(self)
        self.protocol = protocol
        self.address = address
        self.respawn_time = protocol.respawn_time
        self.timers = collections.deque()
    
    def loader_received(self, loader):
        if self.connection_id is None:
            if loader.id == ConnectionRequest.id:
                if loader.client:
                    if loader.version != self.protocol.version:
                        self.disconnect()
                        return
                    max_players = min(32, self.protocol.max_players)
                    if len(self.protocol.connections) > max_players:
                        self.disconnect()
                        return
                    if self.protocol.max_connections_per_ip:
                        shared = [conn for conn in
                            self.protocol.connections.values()
                            if conn.address[0] == self.address[0]]
                        if len(shared) > self.protocol.max_connections_per_ip:
                            self.disconnect()
                            return
                self.master = not loader.client
                if self.on_connect(loader) == False:
                    return
                self.auth_val = loader.auth_val
                self.saved_loaders = []
                self.connection_id = self.protocol.connection_ids.pop()
                self.unique = random.randint(0, 3)
                connection_response = ConnectionResponse()
                connection_response.auth_val = loader.auth_val
                connection_response.unique = self.unique
                connection_response.connection_id = self.connection_id

                self.send_loader(connection_response, True, 0xFF
                    ).addCallback(self._connection_ack)
            else:
                self.disconnect()
            return
        else:
            if loader.id == Packet10.id:
                return
            elif loader.id == Disconnect.id:
                self.disconnect()
                return
            elif loader.id == Ping.id:
                return
        
        if self.player_id is not None:
            if loader.id in (SizedData.id, SizedSequenceData.id):
                contained = load_client_packet(loader.data)
                if contained.id == clientloaders.JoinTeam.id:
                    if contained.name is None and contained.weapon != -1:
                        if self.name is None:
                            return
                        if self.on_weapon_set(contained.weapon) == False:
                            if self.weapon != contained.weapon:
                                self.set_weapon(local = True)
                            return
                        self.weapon = contained.weapon
                        self.kill()
                        return
                    old_team = self.team
                    team = [self.protocol.blue_team, 
                        self.protocol.green_team][contained.team]
                    if self.on_team_join(team) == False:
                        if old_team is not None:
                            return
                        team = team.other
                    self.team = team
                    if self.name is None and contained.name is not None:
                        name = contained.name
                         # vanilla AoS behaviour
                        if name == 'Deuce':
                            name = name + str(self.player_id)
                        self.name = self.protocol.get_name(name)
                        if self.weapon is None:
                            self.weapon = contained.weapon
                        self.protocol.players[self.name, self.player_id] = self
                    if old_team is None:
                        if self.protocol.speedhack_detect:
                            self.speedhack_detect = True
                        self.on_login(self.name)
                        self.spawn(name = self.name)
                    else:
                        self.kill()
                    return
                if self.hp:
                    world_object = self.world_object
                    if contained.id == clientloaders.OrientationData.id:
                        world_object.set_orientation(contained.x,
                            contained.y, contained.z)
                        if self.filter_visibility_data:
                            return
                        orientation_data.x = contained.x
                        orientation_data.y = contained.y
                        orientation_data.z = contained.z
                        orientation_data.player_id = self.player_id
                        self.protocol.send_contained(orientation_data, 
                            True, sender = self)
                    elif contained.id == clientloaders.PositionData.id:
                        world_object.set_position(contained.x, contained.y,
                            contained.z)
                        self.on_position_update()
                        other_flag = self.team.other.flag
                        if vector_collision(world_object.position, self.team.base):
                            if other_flag.player is self:
                                self.capture_flag()
                            last_refill = self.last_refill
                            if (last_refill is None or 
                            reactor.seconds() - last_refill > 
                            self.protocol.refill_interval):
                                self.last_refill = reactor.seconds()
                                if self.on_refill() != False:
                                    self.refill()
                        if self.filter_visibility_data:
                            return
                        if other_flag.player is None and vector_collision(
                        world_object.position, other_flag):
                            self.take_flag()
                        position_data.player_id = self.player_id
                        position_data.x = contained.x
                        position_data.y = contained.y
                        position_data.z = contained.z
                        self.protocol.send_contained(position_data, 
                            sender = self)
                    elif contained.id == clientloaders.MovementData.id:
                        world_object.set_walk(contained.up, contained.down,
                            contained.left, contained.right)
                        if self.filter_visibility_data:
                            return
                        movement_data.up = contained.up
                        movement_data.down = contained.down
                        movement_data.left = contained.left
                        movement_data.right = contained.right
                        movement_data.player_id = self.player_id
                        self.protocol.send_contained(movement_data, 
                            sender = self)
                    elif contained.id == clientloaders.AnimationData.id:
                        world_object.set_animation(contained.fire,
                            contained.jump, contained.crouch, contained.aim)
                        if self.filter_visibility_data:
                            return
                        animation_data.fire = contained.fire
                        animation_data.jump = contained.jump
                        animation_data.crouch = contained.crouch
                        animation_data.aim = contained.aim
                        animation_data.player_id = self.player_id
                        self.protocol.send_contained(animation_data, 
                            sender = self)
                    elif contained.id == clientloaders.HitPacket.id:
                        if contained.player_id != -1:
                            player = self.protocol.players[contained.player_id]
                            hit_amount = HIT_VALUES[contained.value][self.weapon]
                            returned = self.on_hit(hit_amount, player)
                            if returned == False:
                                return
                            elif returned is not None:
                                hit_amount = returned
                            player.hit(hit_amount, self)
                        else:
                            self.hit(contained.value)
                    elif contained.id == clientloaders.GrenadePacket.id:
                        if not self.grenades:
                            return
                        self.grenades -= 1
                        if self.on_grenade(contained.value) == False:
                            return
                        world_object.throw_grenade(contained.value,
                            self.grenade_exploded)
                        if self.filter_visibility_data:
                            return
                        grenade_packet.player_id = self.player_id
                        grenade_packet.value = contained.value
                        self.protocol.send_contained(grenade_packet, 
                            sender = self)
                    elif contained.id == clientloaders.SetTool.id:
                        self.tool = contained.value
                        if self.filter_visibility_data:
                            return
                        set_tool.player_id = self.player_id
                        set_tool.value = contained.value
                        self.protocol.send_contained(set_tool, sender = self)
                    elif contained.id == clientloaders.SetColor.id:
                        color = get_color(contained.value)
                        if self.on_color_set_attempt(color) == False:
                            return
                        self.color = color
                        self.on_color_set(color)
                        if self.filter_visibility_data:
                            return
                        set_color.player_id = self.player_id
                        set_color.value = contained.value
                        self.protocol.send_contained(set_color, sender = self,
                            save = True)
                    elif contained.id == clientloaders.BlockAction.id:
                        value = contained.value
                        map = self.protocol.map
                        x = contained.x
                        y = contained.y
                        z = contained.z
                        if value == BUILD_BLOCK:
                            # if not self.blocks:
                                # self.on_hack_attempt('Block hack detected')
                                # return
                            self.blocks -= 1
                            if self.on_block_build_attempt(x, y, z) == False:
                                return
                            elif not map.set_point(x, y, z, self.color + (255,)):
                                return
                            self.on_block_build(x, y, z)
                        else:
                            if self.on_block_destroy(x, y, z, value) == False:
                                return
                            elif value == DESTROY_BLOCK:
                                self.blocks += 1
                                map.remove_point(x, y, z)
                                self.on_block_removed(x, y, z)
                            elif value == SPADE_DESTROY:
                                map.remove_point(x, y, z)
                                map.remove_point(x, y, z + 1)
                                map.remove_point(x, y, z - 1)
                                self.on_block_removed(x, y, z)
                                self.on_block_removed(x, y, z + 1)
                                self.on_block_removed(x, y, z - 1)
                            self.last_block_destroy = reactor.seconds()
                        block_action.x = x
                        block_action.y = y
                        block_action.z = z
                        block_action.value = contained.value
                        block_action.player_id = self.player_id
                        self.protocol.send_contained(block_action, save = True)
                        self.protocol.update_entities()
                if contained.id == clientloaders.ChatMessage.id:
                    if not self.name:
                        return
                    value = contained.value
                    if value.startswith('/'):
                        value = encode(value[1:])
                        try:
                            splitted = shlex.split(value)
                        except ValueError:
                            # shlex failed. let's just split per space
                            splitted = value.split(' ')
                        if splitted:
                            command = splitted.pop(0)
                        else:
                            command = ''
                        splitted = [decode(value) for value in splitted]
                        self.on_command(command, splitted)
                    else:
                        global_message = contained.global_message
                        if self.on_chat(value, global_message) == False:
                            return
                        chat_message.global_message = global_message
                        chat_message.value = value
                        chat_message.player_id = self.player_id
                        if contained.global_message:
                            team = None
                        else:
                            team = self.team
                        self.protocol.send_contained(chat_message, 
                            sender = self, team = team)
            return

    def get_location(self):
        position = self.world_object.position
        return position.x, position.y, position.z
    
    def set_location(self, (x, y, z)):
        self.world_object.set_position(x, y, z)
        position_data.x = x
        position_data.y = y
        position_data.z = z
        position_data.player_id = self.player_id
        if self.filter_visibility_data:
            self.send_contained(position_data)
        else:
            self.protocol.send_contained(position_data)
    
    def get_orientation_sequence(self):
        sequence = self.orientation_sequence
        self.orientation_sequence = (sequence + 1) & 0xFFFF
        return sequence
    
    def refill(self):
        self.hp = 100
        self.grenades = 2
        self.blocks = 50
        intel_action.action_type = 4
        self.send_contained(intel_action)
    
    def take_flag(self):
        flag = self.team.other.flag
        if flag.player is not None:
            return
        flag.player = self
        intel_action.action_type = 1
        intel_action.player_id = self.player_id
        self.protocol.send_contained(intel_action, save = True)
    
    def respawn(self):
        if self.spawn_call is None:
            self.spawn_call = reactor.callLater(
                self.respawn_time, self.spawn)
    
    def spawn(self, pos = None, name = None):
        self.spawn_call = None
        if pos is None:
            pos = self.team.get_random_location(True)
        x, y, z = pos
        if self.world_object is not None:
            self.world_object.set_position(x, y, z, True)
        else:
            position = Vertex3(x, y, z)
            self.world_object = self.protocol.world.create_object(
                world.Character, position, None, self._on_fall)
        self.world_object.dead = False
        self.hp = 100
        self.tool = 3
        self.grenades = 2
        self.blocks = 50
        self.on_spawn(pos)
        create_player.player_id = self.player_id
        create_player.name = name
        create_player.x = x
        create_player.y = y - 128
        create_player.weapon = self.weapon
        if self.filter_visibility_data:
            self.send_contained(create_player, save = True)
        else:
            self.protocol.send_contained(create_player, save = True)
    
    def capture_flag(self):
        other_team = self.team.other
        flag = other_team.flag
        player = flag.player
        if player is not self:
            return
        self.add_score(10) # 10 points for intel
        self.on_flag_capture()
        if (self.protocol.max_score not in (0, None) and 
        self.team.score + 1 >= self.protocol.max_score):
            self.protocol.reset_game(self)
            self.protocol.on_game_end(self)
        else:
            intel_action.action_type = 3
            intel_action.player_id = self.player_id
            intel_action.game_end = False
            self.team.score += 1
            flag = other_team.set_flag()
            intel_action.x = flag.x
            intel_action.y = flag.y
            self.protocol.send_contained(intel_action, save = True)
    
    def drop_flag(self):
        protocol = self.protocol
        for flag in (protocol.blue_team.flag, protocol.green_team.flag):
            player = flag.player
            if player is not self:
                continue
            position = self.world_object.position
            x = int(position.x)
            y = int(position.y)
            z = max(0, int(position.z))
            z = self.protocol.map.get_z(x, y, z)
            flag.set(x, y, z)
            flag.player = None
            intel_action.action_type = 2
            intel_action.player_id = self.player_id
            intel_action.x = flag.x
            intel_action.y = flag.y
            intel_action.z = flag.z
            self.protocol.send_contained(intel_action, save = True)
            break
    
    def disconnect(self):
        if self.disconnected:
            return
        print_top_100()
        BaseConnection.disconnect(self)
        del self.protocol.connections[self.address]
        if self.connection_id is not None and not self.master:
            self.protocol.connection_ids.put_back(self.connection_id)
        if self.player_id is not None:
            self.protocol.player_ids.put_back(self.player_id)
            self.protocol.update_master()
        if self.name is not None:
            self.drop_flag()
            player_data.player_left = self.player_id
            self.protocol.send_contained(player_data, sender = self,
                save = True)
            del self.protocol.players[self]
        if self.spawn_call is not None:
            self.spawn_call.cancel()
            self.spawn_call = None
        if self.world_object is not None:
            self.world_object.delete()
    
    def hit(self, value, by = None):
        if self.hp is None:
            return
        if by is not None and self.team is by.team:
            friendly_fire = self.protocol.friendly_fire
            hit_time = self.protocol.friendly_fire_time
            if friendly_fire == 'on_grief':
                if (self.last_block_destroy is None 
                or reactor.seconds() - self.last_block_destroy >= hit_time):
                    return
            elif not friendly_fire:
                return
        self.set_hp(self.hp - value, by)
    
    def set_hp(self, value, hit_by = None, not_fall = True):
        value = int(value)
        self.hp = max(0, min(100, value))
        if self.hp <= 0:
            self.kill(hit_by, not_fall)
            return
        hit_packet.hp = self.hp
        hit_packet.not_fall = not_fall
        self.send_contained(hit_packet)
    
    def set_weapon(self, weapon = None, local = False):
        if weapon is None:
            weapon = self.weapon
        self.weapon = weapon
        existing_player.name = None
        existing_player.player_id = self.player_id
        existing_player.team = self.team.id
        existing_player.weapon = weapon
        if local:
            self.send_contained(existing_player)
        else:
            self.protocol.send_contained(existing_player, save = True)
    
    def kill(self, by = None, not_fall = True):
        if self.hp is None:
            return
        self.on_kill(by)
        self.drop_flag()
        self.hp = None
        kill_action.not_fall = not_fall
        if by is None:
            kill_action.player1 = kill_action.player2 = self.player_id
        else:
            kill_action.player1 = by.player_id
            kill_action.player2 = self.player_id
        if by is not None and by is not self:
            by.add_score(1)
        self.protocol.send_contained(kill_action, save = True)
        self.world_object.dead = True
        self.respawn()

    def add_score(self, score):
        self.kills += score
    
    def _connection_ack(self, ack):
        if self.master:
            # this shouldn't happen, but let's make sure
            self.disconnect()
            return
        # send players
        saved_loaders = self.saved_loaders
        for player in self.protocol.players.values():
            if player.name is None:
                continue
            existing_player.name = player.name
            existing_player.player_id = player.player_id
            existing_player.tool = player.tool or 3
            existing_player.weapon = player.weapon
            existing_player.kills = player.kills
            existing_player.team = player.team.id
            existing_player.color = make_color(*player.color)
            saved_loaders.append(existing_player.generate())
    
        # send initial data
        blue = self.protocol.blue_team
        green = self.protocol.green_team
        blue_flag = blue.flag
        green_flag = green.flag
        blue_base = blue.base
        green_base = green.base
        
        self.player_id = self.protocol.player_ids.pop()
        self.protocol.update_master()

        player_data.player_left = -1
        player_data.player_id = self.player_id
        player_data.max_score = self.protocol.max_score
        player_data.blue_score = blue.score
        player_data.green_score = green.score
        
        player_data.blue_base_x = blue_base.x
        player_data.blue_base_y = blue_base.y
        player_data.blue_base_z = blue_base.z
        
        player_data.green_base_x = green_base.x
        player_data.green_base_y = green_base.y
        player_data.green_base_z = green_base.z
        
        if blue_flag.player is None:
            player_data.blue_flag_player = -1
            player_data.blue_flag_x = blue_flag.x
            player_data.blue_flag_y = blue_flag.y
            player_data.blue_flag_z = blue_flag.z
        else:
            player_data.blue_flag_player = blue_flag.player.player_id
        
        if green_flag.player is None:
            player_data.green_flag_player = -1
            player_data.green_flag_x = green_flag.x
            player_data.green_flag_y = green_flag.y
            player_data.green_flag_z = green_flag.z
        else:
            player_data.green_flag_player = green_flag.player.player_id
        
        saved_loaders.append(player_data.generate())
        
        self.map_data = ByteReader(self.protocol.map.generate())
        self.send_map()
        
    def grenade_exploded(self, grenade):
        position = grenade.position
        x = position.x
        y = position.y
        z = position.z
        if x < 0 or x > 512 or y < 0 or y > 512 or z < 0 or z > 63:
            return
        x = int(x)
        y = int(y)
        z = int(z)
        for player_list in (self.team.other.get_players(), (self,)):
            for player in player_list:
                if not player.hp:
                    continue
                damage = grenade.get_damage(player.world_object.position)
                if damage == 0:
                    continue
                returned = self.on_hit(damage, player)
                if returned == False:
                    continue
                elif returned is not None:
                    damage = returned
                player.set_hp(player.hp - damage, self)
        if self.on_block_destroy(x, y, z, GRENADE_DESTROY) == False:
            return
        map = self.protocol.map
        for nade_x in xrange(x - 1, x + 2):
            for nade_y in xrange(y - 1, y + 2):
                for nade_z in xrange(z - 1, z + 2):
                    map.remove_point(nade_x, nade_y, 
                        nade_z)
                    self.on_block_removed(nade_x, nade_y,
                        nade_z)
        block_action.x = x
        block_action.y = y
        block_action.z = z
        block_action.value = GRENADE_DESTROY
        block_action.player_id = self.player_id
        self.protocol.send_contained(block_action, save = True)
        self.protocol.update_entities()
    
    def _on_fall(self, damage):
        if not self.hp:
            return
        returned = self.on_fall(damage)
        if returned == False:
            return
        elif returned is not None:
            damage = returned
        self.set_hp(self.hp - damage, not_fall = False)
    
    def send_map(self):
        if self.map_data is None:
            return
        if not self.map_data.dataLeft():
            self.map_data = None
            # get the saved loaders
            for data in self.saved_loaders:
                sized_data.data = data
                self.send_loader(sized_data, True)
            self.saved_loaders = None
            self.on_join()
            return
        for _ in xrange(4):
            sequence = self.packet_handler1.sequence + 1
            data_size = min(5120, self.map_data.dataLeft())
            new_data = ByteReader('\x0F' + self.map_data.read(data_size))
            new_data_size = len(new_data)
            nums = int(math.ceil(new_data_size / 1024.0))
            for i in xrange(nums):
                map_data.data = new_data.readReader(1024)
                map_data.sequence2 = sequence
                map_data.num = i
                map_data.total_num = nums
                map_data.data_size = new_data_size
                map_data.current_pos = i * 1024
                self.send_loader(map_data, True).addCallback(self.got_map_ack)
                self.map_packets_sent += 1
    
    def got_map_ack(self, ack):
        self.map_packets_sent -= 1
        if not self.map_packets_sent:
            self.send_map()
    
    def send_data(self, data):
        self.protocol.transport.write(data, self.address)
    
    def send_chat(self, value, global_message = None):
        if global_message is None:
            chat_message.player_id = -1
            prefix = ''
        else:
            chat_message.global_message = global_message
            # 32 is guaranteed to be out of range!
            chat_message.player_id = 32
            prefix = self.protocol.server_prefix + ' '
        lines = textwrap.wrap(value, MAX_CHAT_SIZE - len(prefix) - 1)
        for line in lines:
            chat_message.value = '%s%s' % (prefix, line)
            self.send_contained(chat_message)
    
    def timer_received(self, value):
        if not self.speedhack_detect:
            return
        timers = self.timers
        seconds = reactor.seconds()
        timers.append((value, seconds))
        if len(timers) <= TIMER_WINDOW_ENTRIES:
            return
        timers.popleft()
        start_timer, start_seconds = timers[0]
        end_timer, end_seconds = timers[-1]
        diff = (end_timer - start_timer) / (end_seconds - start_seconds)
        if diff > MAX_TIMER_SPEED:
            print 'SPEEDHACK -> Diff:', diff, timers
            self.on_hack_attempt('Speedhack detected '
                '(or really awful connection)')

    # events/hooks
    
    def on_connect(self, loader):
        pass
    
    def on_join(self):
        pass
    
    def on_login(self, name):
        pass
    
    def on_spawn(self, pos):
        pass
    
    def on_chat(self, value, global_message):
        pass
        
    def on_command(self, command, parameters):
        pass
    
    def on_hit(self, hit_amount, hit_player):
        pass
    
    def on_kill(self, killer):
        pass
    
    def on_team_join(self, team):
        pass
    
    def on_grenade(self, time_left):
        pass
    
    def on_block_build_attempt(self, x, y, z):
        pass
    
    def on_block_build(self, x, y, z):
        pass

    def on_block_destroy(self, x, y, z, mode):
        pass
        
    def on_block_removed(self, x, y, z):
        pass
    
    def on_refill(self):
        pass
    
    def on_color_set_attempt(self, color):
        pass
    
    def on_color_set(self, color):
        pass
    
    def on_flag_capture(self):
        pass
    
    def on_hack_attempt(self, reason):
        pass

    def on_position_update(self):
        pass
    
    def on_weapon_set(self, value):
        pass
    
    def on_fall(self, damage):
        pass

class Flag(Vertex3):
    player = None
    team = None

class Team(object):
    score = None
    flag = None
    other = None
    map = None
    name = None
    spawns = None
    kills = None
    
    def __init__(self, id, name, protocol):
        self.id = id
        self.name = name
        self.map = protocol.map
        self.players = protocol.players
        x_offset = id * 384
        self.spawns = spawns = []
        for x in xrange(x_offset, 128 + x_offset):
            for y in xrange(128, 384):
                z = self.map.get_z(x, y)
                if z < 63:
                    spawns.append((x, y))
        self.initialize()
    
    def get_players(self):
        for player in self.players.values():
            if player.team is self:
                yield player
    
    def count(self):
        count = 0
        for player in self.players.values():
            if player.team is self:
                count += 1
        return count
    
    def initialize(self):
        self.score = 0
        self.kills = 0
        self.set_flag()
        self.set_base()
    
    def set_flag(self):
        self.flag = Flag(*self.get_random_location(True))
        self.flag.team = self
        return self.flag

    def set_base(self):    
        self.base = Vertex3(*self.get_random_location(True))
    
    def get_random_location(self, force_land = False):
        if force_land and len(self.spawns) > 0:
            x, y = random.choice(self.spawns)
            return (x, y, self.map.get_z(x, y))
        x_offset = self.id * 384
        x = self.id * 384 + random.randrange(128)
        y = 128 + random.randrange(256)
        z = self.map.get_z(x, y)
        return x, y, z

class ServerProtocol(DatagramProtocol):
    connection_class = ServerConnection

    name = 'pyspades server'
    max_players = 20
    connections = None
    connection_ids = None
    player_ids = None
    master = False
    max_score = 10
    map = None
    friendly_fire = False
    friendly_fire_time = 2
    server_prefix = '[*]'
    respawn_time = 5
    refill_interval = 20
    master_connection = None
    speedhack_detect = True
    
    def __init__(self):
        self.connections = {}
        self.players = MultikeyDict()
        self.connection_ids = IDPool()
        self.player_ids = IDPool()
        self.blue_team = Team(0, 'Blue', self)
        self.green_team = Team(1, 'Green', self)
        self.blue_team.other = self.green_team
        self.green_team.other = self.blue_team
        self.world = world.World(self.map)
        self.update_loop = LoopingCall(self.update_world)
        self.update_loop.start(UPDATE_FREQUENCY)
    
    def update_world(self):
        self.world.update(UPDATE_FREQUENCY)
    
    def reset_game(self, player):
        blue_team = self.blue_team
        green_team = self.green_team
        blue_team.initialize()
        green_team.initialize()
        blue_team = self.blue_team
        green_team = self.green_team
        intel_action.blue_flag_x = blue_team.flag.x
        intel_action.blue_flag_y = blue_team.flag.y
        intel_action.blue_base_x = blue_team.base.x
        intel_action.blue_base_y = blue_team.base.y
        intel_action.green_flag_x = green_team.flag.x
        intel_action.green_flag_y = green_team.flag.y
        intel_action.green_base_x = green_team.base.x
        intel_action.green_base_y = green_team.base.y
        intel_action.action_type = 3
        intel_action.player_id = player.player_id
        intel_action.game_end = True
        self.send_contained(intel_action, save = True)

        for player in self.players.values():
            if player.name is not None:
                player.spawn()
    
    def get_name(self, name):
        i = 0
        new_name = name
        names = [p.name.lower() for p in self.players.values()]
        while 1:
            if new_name.lower() in names:
                i += 1
                new_name = name + str(i)
            else:
                break
        return new_name
    
    def startProtocol(self):
        self.set_master()
    
    def set_master(self):
        if self.master:
            get_master_connection(self.name, self.max_players,
                self.transport.interface).addCallback(
                self.got_master_connection)
        
    def got_master_connection(self, connection):
        self.master_connection = connection
        connection.disconnect_callback = self.master_disconnected
    
    def master_disconnected(self):
        self.master_connection = None
    
    def update_master(self):
        if self.master_connection is None:
            return
        count = 0
        for connection in self.connections.values():
            if connection.player_id is not None:
                count += 1
        self.master_connection.set_count(count)
    
    def datagramReceived(self, data, address):
        if not data:
            return
        in_packet.read(data)
        if address not in self.connections:
            if in_packet.connection_id != CONNECTIONLESS:
                return
            self.connections[address] = self.connection_class(self, address)
        connection = self.connections[address]
        connection.packet_received(in_packet)
    
    def update_entities(self):
        blue_team = self.blue_team
        green_team = self.green_team
        map = self.map
        intel_action.action_type = 0
        for (move_type, entity) in ((MOVE_BLUE_FLAG, blue_team.flag),
                                   (MOVE_GREEN_FLAG, green_team.flag),
                                   (MOVE_BLUE_BASE, blue_team.base),
                                   (MOVE_GREEN_BASE, green_team.base)):
            moved = False
            if map.get_solid(entity.x, entity.y, entity.z - 1):
                moved = True
                entity.z -= 1
                while map.get_solid(entity.x, entity.y, entity.z - 1):
                    entity.z -= 1
            else:
                while not map.get_solid(entity.x, entity.y, entity.z):
                    moved = True
                    entity.z += 1
            if moved:
                intel_action.move_type = move_type
                intel_action.z = entity.z
                self.send_contained(intel_action)
    
    def send_contained(self, contained, sequence = False, sender = None,
                       team = None, save = False):
        
        if sequence:
            loader = sized_sequence
            check_distance = (sender is not None and 
                              sender.world_object is not None)
            if check_distance:
                position = sender.world_object.position
                x = position.x
                y = position.y
        else:
            loader = sized_data
        data = ByteWriter()
        contained.write(data)
        loader.data = data
        for player in self.connections.values():
            if player is sender or player.player_id is None:
                continue
            if team is not None and player.team is not team:
                continue
            if sequence:
                if check_distance and player.world_object is not None:
                    position = player.world_object.position
                    distance_squared = (position.x - x)**2 + (position.y - y)**2
                    if distance_squared > ORIENTATION_DISTANCE_SQUARED:
                        continue
                loader.sequence2 = player.get_orientation_sequence()
            if player.saved_loaders is not None:
                if save:
                    player.saved_loaders.append(data)
            else:
                player.send_loader(loader, not sequence)
    
    def send_chat(self, value, global_message = None, sender = None,
                  team = None):
        for player in self.players.values():
            if player is sender:
                continue
            if team is not None and player.team is not team:
                continue
            player.send_chat(value, global_message)

    # events
    
    def on_game_end(self, player):
        pass
