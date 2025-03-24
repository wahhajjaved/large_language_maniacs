# Copyright (C) 2011-2012 Mitchell Stokes and Daniel Stokes

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import pickle
import Scripts.packages as packages
import Scripts.character_logic as character_logic
import Scripts.effect_manager as effects

from Scripts.networking import COMMAND_SEP, ARG_SEP

# This is used to implement RPC like functionality
def rpc(d, name, *args):
	def decorator(f):
		d[name] = (f, args)
		return f
	return decorator

class RPC:
	def __init__(self, state, client, rdict):
		# Stash the client and state
		self.state = state
		self.client = client
	
		self.funcs = rdict

	def invoke(self, f, *args):
		if f not in self.funcs:
			raise ValueError(f+" is not a registered function.\nAvailable functions: "+
								", ".join([v[0].__name__ for k, v in self.funcs.items()]))
	
		p = []
		
		# Check the data types and convert to strings
		for i in range(len(args)):
			t = self.funcs[f][1][i]
			v = args[i]
			if t is float:
				v = ("%.4f" % v).encode()
			elif t == "pickle":
				v = pickle.dumps(v, -1)
			elif not isinstance(v, t):
				print("Function:", f, "\nArgs:", args)
				raise ValueError("Argument "+str(i)+" should have been of type "+t.__name__+" got "+v.__class__.__name__+" instead.")
			else:
				v = str(v).encode()
				
			p.append(v)
		# Send out the command
		self.client.send(f.encode()+COMMAND_SEP+ARG_SEP.join(p))
		
	def parse_command(self, main, data, client=None):
		if not data:
			return

		# Grab the functions and arguments
		s = data.split(COMMAND_SEP)
		if len(s) != 2:
			print("Invalid command string", data)
			return

		f, args = s[0].decode(), s[1].split(ARG_SEP)
		
		# Make sure we have a function we know
		if f not in self.funcs:
			print("Unrecognized function", f, "for state", self.state.__class__.__name__)
			return
		
		# Make sure we have the correct number of arguments
		if len(self.funcs[f][1]) != 0 and len(args) != len(self.funcs[f][1]):
			print("Invalid command string (incorrect number of arguments)", data)
			return
		
		# Change the strings to the correct data types
		for i in range(len(self.funcs[f][1])):
			t = self.funcs[f][1][i]
			
			if t == "pickle":
				args[i] = pickle.loads(args[i])
			else:
				args[i] = t(args[i].decode())
		
		if client:
			if len(self.funcs[f][1]) != 0:
				self.funcs[f][0](self.state, main, client, *args)
			else:
				self.funcs[f][0](self.state, main, client)
		else:
			if len(self.funcs[f][1]) != 0:
				self.funcs[f][0](self.state, main, *args)
			else:
				self.funcs[f][0](self.state, main)
		

# This class shouldn't be used directly, but rather subclassed

class BaseState:
	"""Base gamestate"""
	
	client_functions = {}
	server_functions = {}
	
	ui_layout = None
	
	def __init__(self, main, is_server=False):
		"""BaseState Constructor"""
		
		# Store main
		self.main = main
		
		# This variable allows for switching states without a return (used for RPC functions)
		self._next_state = ""
		
		# Note whether or note the state is "suspended" (not the top of the stack).
		# This allows the state to alter it's behavior in its suspended state, but still allow necessary code to run.
		self.suspended = False

		# Setup the Remote Procedure Calls
		c = main['server'] if is_server else main.get('client')
		self.clients = RPC(self, c, self.client_functions)
		self.server = RPC(self, c, self.server_functions)
		
		self.is_server = is_server
		
		if is_server:
			self.server_init(main)
			self.cleanup = self.server_cleanup
		else:
			self.client_init(main)
			self.cleanup = self.client_cleanup
		
	def run(self, main, client=None):
		if self._next_state: return (self._next_state, "SWITCH")
	
		# Update main
		self.main = main
		
		# Run the appropriate method
		if self.is_server:
			self.client = RPC(self, client, self.client_functions)
			self.server.parse_command(main, client.data, client)
			return self.server_run(main, client)
		else:
			val = main['client'].run() if "client" in main else None
			while val:
				self.clients.parse_command(main, val)
				val = main['client'].run()
			return self.client_run(main)
					
	##########
	# Client
	##########
	
	def _delete_player(self, main, cid):
		player = main['net_players'][cid]
		player.object.end()
#		effect = effects.FadeEffect(player, 25)
#		def f_end(object, engine):
#			object.end()
#		effect.f_end = f_end
#		self.add_effect(effect)
		
		del main['net_players'][cid]
	
	# Client functions
	@rpc(client_functions, "cid", str)
	def cid(self, main, id):
		print("Setting id to", id)
		main['client'].id = id
		
	@rpc(client_functions, "to", str)
	def to(self, main, cid):
		if 'net_players' not in main: return
		if id not in main['net_players']: return
		
		self._delete_player(self, main, cid)
		print(cid, "timed out.")
		
	@rpc(client_functions, "dis", str)
	def dis(self, main, cid):
		if 'net_players' not in main: return
		if id not in main['net_players']: return
		
		self._delete_player(self, main, cid)
		print(cid, "disconnected.")
		
	@rpc(client_functions, "remove_player", str)
	def remove_player(self, main, cid):
		"""Remove a player without printing a message"""
		if 'net_players' not in main: return
		if cid not in main['net_players']: return

		self._delete_player(main, cid)
		
	@rpc(client_functions, "move", str, float, float, float)
	def move(self, main, cid, x, y, z):
		pass
		
	@rpc(client_functions, "rotate", str, float, float, float)
	def rotate(self, main, cid, x, y, z):
		pass
		
	@rpc(client_functions, "position", str, float, float, float)
	def position(self, main, cid, x, y, z):
		pass
		
	@rpc(client_functions, "animate", str, str, int)
	def animate(self, main, cid, action, mode):
		if 'net_players' not in main: return
		if cid not in main['net_players']: return
		
		character = main['net_players'][cid]
		
		if not character.action_set:
			print("WARNING: attempting to animate character with an empty action set: %s. Skipping..." % character)
			return
		
		if action in main['actions'][character.action_set]:
			actions = main['actions'][character.action_set][action]
			character.object.play_action(actions, mode=mode)
			character.current_action = action
		else:
			print("WARNING: action %s not found in action set %s." % (action, character.action_set))

	@rpc(client_functions, "add_player", str, "pickle", int, "pickle", "pickle")
	def add_player(self, main, cid, char_info, is_monster, pos, ori):
		if cid in main['net_players']:
			# This player is already in the list, so just ignore this call
			return
	
		if is_monster != 0:
			race = packages.Monster(char_info['race'])
		else:
			race = packages.Race(char_info['race'])
		main['engine'].load_library(race)
		
		obj = main['engine'].add_object(race.root_object, pos, ori)
		obj.armature = obj
		
		if is_monster != 0:
			main['net_players'][cid] = character_logic.MonsterLogic(obj, race)
		else:
			main['net_players'][cid] = character_logic.PlayerLogic(obj)

		main['net_players'][cid].load_from_info(char_info)
		main['net_players'][cid].id = cid
		main['net_players'][cid].auto_target = pos
		
		if char_info['weapon']:
			weapon = char_info['weapon']
			wobj = weapon.createObjectInstance(main['engine'])
			main['net_players'][cid].set_right_hand(wobj) 
	
	@rpc(client_functions, "drop_item", int, "pickle", float, float, float)
	def c_drop_item(self, main, id, item, x, y, z):
		obj = main['engine'].add_object("drop", [x, y, z])
		obj.gameobj['id'] = id
		main['ground_items'][id] = [item, obj, None]
		
	@rpc(client_functions, "pickup_item", "pickle")
	def pickup_item(self, main, item):
		print("You picked up this item:")
		print(item)
		main['player'].inventory.append(item)
		
	@rpc(client_functions, "remove_item", int)
	def remove_item(self, main, id):
		if id not in main['ground_items']:
			return
		
		main['ground_items'][id][1].end()
		if main['ground_items'][id][2] is not None:
			main['effect_system'].remove(main['ground_items'][id][2])
		del main['ground_items'][id]
		
	@rpc(client_functions, "reward_xp", "pickle", int)
	def reward_xp(self, main, heroes, xp):
		if main['player'].id in heroes:
			main['player'].xp += xp
			
	@rpc(client_functions, "set_health", str, int)
	def c_set_health(self, main, cid, amount):
		if cid not in main['net_players']: return
		
		main['net_players'][cid].hp = amount
	
	def client_init(self, main):
		"""Initialize the client state"""
		pass
		
	def client_run(self, main):
		"""Client-side run method"""
		pass
			
	def client_cleanup(self, main):
		"""Cleanup the client state"""
		pass
			
	##########
	# Server
	##########
	
	# Server functions
	@rpc(server_functions, "dis")
	def dis(self, main, client):
		client.server.broadcast(b"dis"+COMMAND_SEP+client.id.encode())
		client.server.drop_client(client.peer, "Disconnected")
		
	@rpc(server_functions, "add_player", "pickle", "pickle", "pickle")
	def add_player(self, main, client, char_info, pos, ori):
		client.server.add_player(client.id, char_info, pos, ori)
		self.clients.invoke('add_player', client.id, char_info, 0, pos, ori)
		
		for k, v in main['players'].items():
			if v.__class__.__name__ == 'NetPlayer':
				self.client.invoke('add_player', k, v.char_info, 0, v.position, v.orientation)
		
	@rpc(server_functions, "update_player_info", "pickle")
	def update_player_info(self, main, client, char_info):
		player = main['players'].get(client.id, None)
		
		if player:
			player.load_from_info(char_info)
		
	@rpc(server_functions, "animate", str, str, int)
	def s_animate(self, main, client, cid, action, mode):
		self.clients.invoke('animate', cid, action, mode) 
		
	@rpc(server_functions, "switch_state", str)
	def switch_state(self, main, client, state):
		self._next_state = state
		
	@rpc(server_functions, "drop_item", "pickle", float, float, float)
	def s_drop_item(self, main, client, item, x, y, z):
		self.drop_item(item, [x, y, z])
		
	@rpc(server_functions, "set_health", str, int)
	def s_set_health(self, main, client, cid, amount):
		if cid not in main['players']: return
		
		main['players'][cid].hp = amount
		
		self.clients.invoke('set_health', cid, amount)
	
	@rpc(server_functions, "noop")
	def s_no_op(self, main, client):
		"""This function simply exists to kick the server when needed"""
		pass
		
	def server_init(self, main):
		"""Initialize the server state"""
		pass
		
	def server_run(self, main, client):
		"""Server-side run method"""
		pass
			
	def server_cleanup(self, main):
		"""Cleanup the server state"""
		pass

	##########
	# Other
	##########

# All states should have a controller interface by which things like the AI system may make use
# of the state. Subclass this controller and override methods as you need them.
class BaseController:
	"""Base controller interface"""

	# Threshold limit needed to send position updates to the server
	POSITION_THRESHOLD = 1.0
	
	# Threshold limit needed to send rotation updates to the server (radians)
	ROTATION_THRESHOLD = 0.1
	
	def play_animation(self, character, animation, lock=0, mode=0):
		"""Instruct the character to play the animation
		
		character -- the charcter who will play the animation
		animation -- the animation to play
		lock -- how long to lock for the animation
		
		"""
		
		if lock:
			character.add_lock(lock)
			
		if self.is_server:
			self.clients.invoke('animate', character.id, animation, mode)
		else:
			if (character.current_action != animation):
				self.server.invoke("animate", character.id, animation, mode)
		
	def get_targets(self, type, range):
		"""Get targets in a range
		
		type -- the type of area (line, burst, etc)
		range -- the range to grab (integer)
		
		"""
		
		return []
	
	def modify_health(self, character, amount):
		"""Modify the health of the character
		
		character -- the character whose health you want to change
		amount -- the amount to change the health by (negative for damage, positive to heal)
		
		"""
		id = character.id

		if self.is_server:
			character.hp += amount
	
			self.clients.invoke("modify_health", id, amount)
			
			if character.hp <= 0:
				# XXX We shouldn't be checking the class like this, but at the moment,
				# it's the only method we have for knowing if we have a "player" verus a "monster"
				if character.__class__.__name__ == "NetPlayer":
					self.clients.invoke("kill_player", id)
		else:
			self.server.invoke("modify_health", id, amount)
				
	def modify_stat(self, character, stat, amount):
		if stat not in character.stat_mods:
			character.stat_mods[stat] = 0
		character.stat_mods[stat] += amount
		character.recalc_stats()
	
	def remove_effect(self, id):
		self.main["effect_system"].remove(id)
		
	def drop_item(self, item, position):
		if self.is_server:
			main = self.main
			
			main['ground_item_counter'] += 1
			gid = main['ground_item_counter']
			
			main['ground_items'][gid] = item
			self.clients.invoke("drop_item", gid, item, *position)
		else:
			self.server.invoke("drop_item", item, *position)
			
	def display_tutorial(self, player, tut, force=False):
		if force or (player.tutorials != None and tut not in player.tutorials):
			self.main['tutorial_queue'].append(tut)
			
	def sync_position(self, character):
		if not self.is_server:
			return

		update = False
		last_pos = character.last_position
		for i,v in enumerate(character.position):
			if abs(v - last_pos[i]) > self.POSITION_THRESHOLD:
				update = True
				break
				
		if update:
			character.last_position = character.position
			self.server.invoke("position", character.id, *character.position)
				
	def sync_rotation(self, character, new_rot):
		if self.is_server:
			return
		
		if character.network_rotation:
			character.network_rotation[0] += new_rot[0]
			character.network_rotation[1] += new_rot[1]
			character.network_rotation[2] += new_rot[2]
		else:
			character.network_rotation = list(new_rot)
		
		update = False
		
		for i in character.network_rotation:
			if abs(i) > self.ROTATION_THRESHOLD:
				update = True
				break
		
		if update:
			self.server.invoke("rotate", character.id, *character.network_rotation)
			character.network_rotation = None
			