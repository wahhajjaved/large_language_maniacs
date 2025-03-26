# $Id$

from .base_state import *
from .default_state import DefaultState, TURN
from Scripts.packages import *
from Scripts.character_logic import MonsterLogic, PlayerLogic

import random
import time
from math import *

import cego as AiManager
from cego.state_machine import StateMachine as AiStateMachine
from Scripts.mathutils import Vector, Matrix
import Scripts.effect_manager as effects
import Scripts.items as Items

# Constants for grid generation
UNIT_SIZE = 1
HALF_UNIT_SIZE = UNIT_SIZE/2.0
SAFE_Z = 0.01

class Combat:
	"""Combat utility class"""
	
	def __init__(self):
		self.hero_list = {}
		self.monster_list = {}
		self.environment = []
		self.owner = None

class CombatState(DefaultState, BaseController):
	
	client_functions = DefaultState.client_functions.copy()
	server_functions = DefaultState.server_functions.copy()
	
	ui_layout = "combat"
	
	##########
	# Client
	##########
	
	@rpc(client_functions, "add_monster", str, str, str, float, float, float)
	def add_monster(self, main, cid, monster, id, x, y, z):
		if cid != main['combat_id']: return
		if id in self.monster_list: return
		
		if id not in main['net_players']:
			print("Warning, couldn't find MonsterLogic for id:", id)
			return
			
		# Add the monster to the monster list
		logic = main['net_players'][id]
		
		obj = logic.object
		self.monster_list[id] = logic
		
		color = obj.color
		color[3] = 0
		obj.color = color
	
		effect = effects.FadeEffect(obj, duration=90, amount=1)
		self.add_effect(effect)
		
	@rpc(client_functions, "kill_monster", str, str)
	def kill_monster(self, main, cid, id):
		if cid != main['combat_id']: return
		if id not in self.monster_list: return
		monster = self.monster_list[id]
		main['player'].xp += monster.xp_reward//len(self.hero_list)
		
		if monster in main['player'].targets:
			main['player'].targets.remove(monster)

		# Clear any of the monster's statuses out of the status list
		for status in self.status_list:
			if status['user'] == monster:
				self.status_list.remove(status)

		del self.monster_list[id]
		
	@rpc(client_functions, "move_monster", str, float, float, float)
	def move_monster(self, main, cid, x, y, z):
		if cid not in self.monster_list: return
		
		if main['is_host']:
			monster = self.monster_list[cid]
			monster.object.move((x, y, z), min=[-50, -50, 0], max=[50, 50, 0], local=True)
			self.server.invoke("position", cid, *monster.position)
		
	@rpc(client_functions, "rotate_monster", str, float, float, float)
	def rotate_monster(self, main, cid, x, y, z):
		if cid not in self.monster_list: return
		monster = self.monster_list[cid]
		monster.object.rotate((x, y, z))
		self.server.invoke("rotation", cid, monster.object.get_orientation().to_euler()[2])

	@rpc(client_functions, "add_hero", str, str)
	def add_hero(self, main, cid, hid):
		if cid != main['combat_id']: return
		if hid in self.hero_list: return
		
		self.hero_list[hid] = main['net_players'][hid]
	
	@rpc(client_functions, "end_combat", str)
	def end_combat(self, main, cid):
		if cid != main['combat_id']: return
		main['dgen'].clear_encounter(main['room'])
		main['room'] = None
		self._next_state = "Default"
	
	def client_init(self, main):
		"""Initialize the client state"""
		
		main['engine'].play_bgm('Take the Lead.mp3')
		
		self.monster_list = {}
		self.hero_list = {main['client'].id:main['player']}
		
		# Place the monsters
		if main['owns_combat']:
			nav_nodes =  main['room'].get_nav_nodes()
			for node in nav_nodes:
				self.server.invoke("add_node", node)
				
			self.server.invoke("set_environment")
			
			players = [i for i in main['net_players'].values() if isinstance(i, PlayerLogic)]
			num_players = len(players)
			
			party_level = 0
			for i in players:
				party_level += i.level
			party_level //= num_players
				
			for i, monster in enumerate(self._generate_encounter(main['dgen'].deck, num_players)):
				
				# Update the server
				self.server.invoke("add_monster", monster, party_level, str(i), 0, 0, SAFE_Z)
					
		else:
			# Request monsters from the server
			self.server.invoke("request_monsters")
			
		# Put up the combat barriers
		main['dgen'].place_combat_barriers(main['room'])
			
		self.camera = 'combat'
		self.last_camera = 'frankie'
		
		self.status_list = []
			
		
	def client_run(self, main):
		"""Client-side run method"""
		
		# Update the camera
		if not self.suspended:
			if self.camera != self.last_camera:
				main['camera'].change_mode(self.camera, 15)
				self.last_camera = self.camera
			else:
				main['camera'].update(main['player'].lock)
			self.camera = 'combat'
		
		# Update the effect system
		main['effect_system'].update()

		# Update the player's lock
		main['player'].update_lock()
		
		main['player'].powers.update_cooldown()
		
		# Handles input
		inputs = main['input_system'].run()
		
		# Reset the target shapes
		for key, shape in main['target_shapes'].items():
			shape.visible = False
			
		# Handle status effects
		for status in self.status_list:
			status['time'] += 1
			if status['time'] == TURN:
				status['time'] = 0
				status['power'].use(self, status['user'])
				status['duration'] -= 1
				if status['duration'] <= 0:
					status['power'].pop(self, status['user'])
		
		# Targeting
		if not main['player'].targets:
			target = self.get_closest_target(main['player'], self.monster_list.values())
			if target:
				main['player'].targets = [target]
#		active_power = main['player'].powers.active
#		range_type = active_power.effect_shape
#		if "WEAPON_RANGE" in active_power.flags:
#			range_size = main['player'].weapon.range
#		else:
#			range_size = active_power.distance
#		if range_type == 'SINGLE':
#			# If the player already has targets, find out if they are valid
#			if main['player'].targets:
#				# Ranged can only have one target
#				if len(main['player'].targets) > 1:
#					main['player'].targets = []
#				else:
#					# The target must be in range
#					if (main['player'].targets[0].object.position-main['player'].object.position).length > range_size + HALF_UNIT_SIZE:
#						main['player'].targets = []
#			else:
#				target = None
#				target_dist = range_size + HALF_UNIT_SIZE
#				for monster in self.monster_list.values():
#					dist = (monster.object.position-main['player'].object.position).length
#					if dist < target_dist:
#						target = monster
#						target_dist = dist
#				main['player'].targets = [target,] if target else []
#		else:	
#			mask = getattr(active_power, "mask", {'ENEMIES'})
#			main['player'].targets = self.get_targets(main['player'], range_type, range_size, target_types=mask)		
		
		# Maintain monsters
		for id, monster in self.monster_list.items():
			# Highlight any targets
			alpha = monster.object.color[3]
			if monster in main['player'].targets:
				monster.object.color = [1, 0.6, 0.6, alpha]
			else:
				monster.object.color = [1, 1, 1, alpha]
			# Get rid of any dead guys
			if main['owns_combat'] and monster.hp <= 0:
				self.server.invoke("kill_monster", id)
		
			# This should get moved, but it will sit here for now
#			if monster.action_set:
#				self.play_animation(monster, "Idle", mode=1)
			
		# Make sure the server moves along
		if main['owns_combat']:
			self.server.invoke("noop")

		# Our id so we can talk with the server
		id = main['client'].id
		
		if inputs and not self.suspended:
			# Only let the player do stuff while they are not "locked"
			if not main['player'].lock:
				
				player = main['player']
				
				if ("UsePower", "INPUT_CLICK") in inputs:
					self.use_power(player, player.powers.active.name)
				if ("NextPower", "INPUT_CLICK") in inputs:
					player.powers.make_next_active()
				if ("PrevPower", "INPUT_CLICK") in inputs:
					player.powers.make_prev_active()
				if ("UsePowerOne", "INPUT_CLICK") in inputs:
					if player.powers.has_power(0):
						self.use_power(player, player.powers.all[0])
				if ("UsePowerTwo", "INPUT_CLICK") in inputs:
					if player.powers.has_power(1):
						self.use_power(player, player.powers.all[1])
				if ("UsePowerThree", "INPUT_CLICK") in inputs:
					if player.powers.has_power(2):
						self.use_power(player, player.powers.all[2])
				if ("UsePowerFour", "INPUT_CLICK") in inputs:
					if player.powers.has_power(3):
						self.use_power(player, player.powers.all[3])
				if ("UsePowerFive", "INPUT_CLICK") in inputs:
					if player.powers.has_power(4):
						self.use_power(player, player.powers.all[4])
				if ("UsePowerSix", "INPUT_CLICK") in inputs:
					if player.powers.has_power(5):
						self.use_power(player, player.powers.all[5])
			
				if ("Exp", "INPUT_CLICK") in inputs:
					self.modify_health(player, -1)

				if ("TargetClosest", "INPUT_CLICK") in inputs:
					target = self.get_closest_target(player, self.monster_list.values())
					if target:
						player.targets = [target]
				if ("TargetPrevious", "INPUT_CLICK") in inputs:
					target = self.get_prev_target(player.targets[0], list(self.monster_list.values()))
					if target:
						player.targets = [target]
				if ("TargetNext", "INPUT_CLICK") in inputs:
					target = self.get_next_target(player.targets[0], list(self.monster_list.values()))
					if target:
						player.targets = [target]

				if ("Aim", "INPUT_ACTIVE") in inputs:
					if player.powers.active.effect_shape == "SINGLE":
						self.camera = 'shoulder'
						main['ui_system'].mouse.visible = True
						
						# Enable camera pitch on mouse look
						dy = 0.5 - main['input_system'].mouse.position[1]
						cam_ori = Matrix(main['camera'].world_orientation)
						main['camera'].world_orientation = cam_ori * Matrix.Rotation(dy, 3, 'X')
						
						# Build a list of possible targets
						targets = self.monster_list.values()
						
						# Gather some info for the target searching
						distance = player.powers.active.distance * UNIT_SIZE
						cam_vec = main['camera'].pivot.getAxisVect((0,0,-1))
						
						final_target = None
						final_factor = .5 #atan(1/distance) * distance
						for target in targets:
							target_vec = target.object.position - main['camera'].pivot.worldPosition.copy()
							target_vec_len = target_vec.length * UNIT_SIZE - 2
							if target_vec_len < distance:
								factor = cam_vec.angle(target_vec.normalized()) * target_vec_len
								if factor < final_factor:
									final_target = target
									final_factor = factor
									
						player.targets = [final_target] if final_target else []
									
						
					else:					
						# Show the range of the active power
						power = player.powers.active
						type = power.effect_shape
						size = power.distance
						
						if type in main['target_shapes']:
							main['target_shapes'][type].color = [1, 0, 0, 0.25]
							main['target_shapes'][type].scaling = Vector([size+HALF_UNIT_SIZE]*2 + [1])
							main['target_shapes'][type].visible = True
				else:
					main['ui_system'].mouse.visible = False

					
			result = self._handle_generic_input(main, inputs)
			if result: return result

	def client_cleanup(self, main):
		"""Cleanup the client state"""
		
		player = main['player']
		
		# Clear any targeting
		player.targets = []
		player.auto_target = player.auto_range = None
		
						
	##########
	# Server
	##########
	
	@rpc(server_functions, "add_monster", str, int, str, float, float, float)
	def s_add_monster(self, main, client, monster, level, cid, x, y, z):
		combat = main['combats'].get(client.combat_id, None)
		if combat is None: return
		
		if cid not in combat.monster_list:
			ori = [
				[1, 0, 0],
				[0, 1, 0],
				[0, 0, 1]
			]
			combat.monster_list[cid] = client.server.create_monster(Monster(monster), level, [x, y, z], ori)
																#[MonsterLogic(None, Monster(monster), level), [x, y, z]]
			combat.monster_list[cid].id = cid
			AiManager.add_agent(combat.monster_list[cid], "Scripts/ai/definitions/base.json", "spawn")
			combat.monster_list[cid].rotation = 0
			self.clients.invoke("add_player", cid, combat.monster_list[cid].get_info(), 1, [x, y, z], None)
			self.clients.invoke("add_monster", client.combat_id, monster, cid, x, y, z)
			
			main['players'][cid] = combat.monster_list[cid]
		# else:
			# print("WARNING (add_monster): Monster id, '%s', has already been added, ignoring" % id)
		
	@rpc(server_functions, "kill_monster", str)
	def s_kill_monster(self, main, client, id):
		combat = main['combats'].get(client.combat_id, None)
		if combat is None: return
		
		if id in combat.monster_list:
			monster = combat.monster_list[id]
			
			# Get rid of the monster
			self.clients.invoke("kill_monster", client.combat_id, id)
			self.clients.invoke("remove_player", id)
			
			# Now calculate some loot
			main['ground_item_counter'] += 1
			gid = main['ground_item_counter']
			
			item = random.choice([Items.Weapon, Items.Armor])
			item = item(random.choice(item.available_items), 1) # XXX level should be calculated from party level
			
			main['ground_items'][gid] = item
			self.clients.invoke("drop_item", gid, item, *monster.position)
			
			# Now give all the participants some xp
			self.clients.invoke("reward_xp", [i for i in combat.hero_list.keys()], monster.xp_reward)
			
			del combat.monster_list[id]
			del main['players'][id]
		else:
			# print("WARNING (kill_monster): Monster id, '%s', not in list, ignoring" % id)
			return
			
		if len(combat.monster_list) < 1:
			self.clients.invoke("end_combat", client.combat_id)	
			del main['combats'][client.combat_id]
			self._next_state = "Default"
		
	@rpc(server_functions, "modify_health", str, float)
	def s_modify_health(self, main, client, id, amount):
		combat = main['combats'].get(client.combat_id, None)
		if combat is None: return
		
		if id in combat.hero_list:
			self.modify_health(combat.hero_list[id], amount)
		elif id in combat.monster_list:
			self.modify_health(combat.monster_list[id], amount)
			if combat.monster_list[id].hp <= 0:
				self.s_kill_monster(main, client, id)
			
	@rpc(server_functions, "request_monsters")
	def request_monsters(self, main, client):
		combat = main['combats'].get(client.combat_id, None)
		if combat is None: return

		for i, v in combat.monster_list.items():
			self.client.invoke("add_player", i, v.get_info(), 1, v.position, None)
			self.client.invoke("add_monster", client.combat_id, v.name, i, *v.position)

	@rpc(server_functions, "add_hero")
	def s_add_hero(self, main, client):
		combat = main['combats'].get(client.combat_id, None)
		if combat is None: return
		
		if client.id in combat.hero_list:
			# Already added, ignore
			return
			
		combat.hero_list[client.id] = main['player'][client.id]	
		
		self.clients.invoke('add_hero', client.combat_id, client.id)
		
		for hero in combat.hero_list:
			self.client.invoke('add_hero', client.combat_id, hero)
	
	@rpc(server_functions, "rotate_monster", str, float, float, float)
	def s_rotate_monster(self, main, client, cid, x, y, z):
		self.clients.invoke("rotate_monster", cid, x, y, z)
		
	@rpc(server_functions, "rotation", str, float)
	def s_rotation(self, main, client, cid, rotation):
		combat = main['combats'].get(client.combat_id, None)
		if combat:
			character = combat.monster_list.get(cid, None)
			if character:
				character.rotation = rotation
		
	@rpc(server_functions, "position_monster", str, float, float, float)
	def s_position_monster(self, main, client, cid, x, y, z):
		combat = main['combats'].get(client.combat_id, None)
		if combat is None: return
		combat.monster_list[cid].position = [x, y, z]
		self.clients.invoke("position_monster", cid, x, y, z)
		
	@rpc(server_functions, "add_node", "pickle")
	def s_add_node(self, main, client, node):
		combat = main['combats'].get(client.combat_id, None)
		combat.environment.append(node)
	
	@rpc(server_functions, "set_environment")
	def s_set_environment(selfself, main, client):
		combat = main['combats'].get(client.combat_id, None)
		AiManager.set_environment(combat.environment)
	
	def server_init(self, main):
		"""Initialize the server state"""
		self.main = main
		
		self.monster_id = 0
		
		self.ai_accum = 0
		self.ai_time = time.time()
		
		DefaultState.server_init(self, main)
		
	def server_run(self, main, client):
		"""Server-side run method"""
		self.main = main
		self.client_handle = client
		
		combat = main['combats'].get(client.combat_id)
				
		if combat == -1:
			# Init combat here so we have access to the client
			main['combats'][client.combat_id] = combat =Combat()
			combat.owner = client.id
			combat.hero_list[client.id] = main['players'][client.id]
			
			# Setup Ai
			AiManager.set_controller(self)
			AiManager.set_extern_actions("Scripts.ai.actions")
			AiManager.set_extern_transitions("Scripts.ai.transitions")
		elif combat is None:
			return
		elif client.id not in combat.hero_list:
			combat.hero_list[client.id] = main['players'][client.id]	
			
			self.clients.invoke('add_hero', client.combat_id, client.id)
			
			for hero in combat.hero_list:
				self.client.invoke('add_hero', client.combat_id, hero)
			
		if not combat.owner:
			# If we don't have an owner, just grab the "first" hero.
			# combat.hero_list should never be empty (someone has to be in combat to get here).
			combat.owner = next(iter(combat.hero_list.keys()))
		
		# Check to see if the player has died
		if combat.hero_list[client.id].hp <= 0:
			if client.id == combat.owner:
				combat.owner = None
			del combat.hero_list[client.id]
			return ("Dead", "SWITCH")

		# Run the ai if it is set up, else try to set it up
		if client.id == combat.owner:
			new_time = time.time()
			self.ai_accum += new_time - self.ai_time
			self.ai_time = new_time
			
			dt = 1/30
			while self.ai_accum >= dt:
				if AiManager.get_environment():
					AiManager.run()
				self.ai_accum -= dt
				
				# update monster lock
				for monster in combat.monster_list.values():
					monster.update_lock()
			
		DefaultState.server_run(self, main, client)
			
			
				
	##########
	# Other
	##########
	
	def _generate_encounter(self, deck, num_players=1):
		"""Generate an encounter by drawing cards from the encounter deck"""
		random.seed()

		monsters = []
		
		remaining = 4*num_players
		while remaining > 0:
			draw = random.choice(deck.cards)
			
			if draw['points'] <= remaining:
				monsters.append(draw['monster'])
				remaining -= draw['points']

		return monsters
	
	##########
	# Controller
	##########
	def deal_damage(self, caster, target, power, damage, type):
		damage += caster.affinities[power.element]
		damage -= target.affinities[power.element]
		
		type = type.upper()
		if type == "PHYSICAL":
			damage += caster.physical_damage
			damage -= target.physical_defense
		elif type == "ARCANE":
			damage += caster.arcane_damage
			damage -= target.arcane_defense
		else:
			print("WARNING: invalid type supplied to deal_damage() from power:", power.name)
		
		self.modify_health(target, -max(1, damage))
		
	def modify_health(self, character, amount):
		BaseController.modify_health(self, character, amount)
		
		if not self.is_server:
			for i, v in self.monster_list.items():
				if character == v:
					self.server.invoke("modify_health", i, amount)
					
					pos = character.object.position[:2]+(character.object.position[2]+2,)
					effect = effects.TextEffect(amount, pos, 90)
					self.add_effect(effect)
		
	def end_effect(self, id):
		self.main["effect_system"].remove(id)
		
	def get_potential_targets(self):
		l = []
		
		if self.is_server:
			combat = self.client_handle.server.main['combats'].get(self.client_handle.combat_id)
			if combat:
				l.extend(combat.hero_list.values())
				l.extend(combat.monster_list.values())
				
		return l
		
	def get_closest_target(self, character, targets):
		"""Get the closest target to the given character from the targets list"""
		
		cobj = character.object
		
		closest = None
		
		min_distance = 1000
		
		for target in targets:
			v = cobj.position - target.object.position
			distance2 = v.dot(v)

			if closest == None or distance2 < min_distance:
				closest = target
				min_distance = distance2
				
		return closest
	
	def get_next_target(self, current, targets):
		"""Get the next target in the targets list"""
		
		try:
			idx = targets.index(current)+1
		except ValueError:
			return None
		
		if idx >= len(targets):
			idx = 0
			
		return targets[idx]
		
	def get_prev_target(self, current, targets):
		"""Get the previous target in the targets list"""
		
		try:
			idx = targets.index(current) - 1
		except ValueError:
			return None
		
		# Negative numbers are fine, Python will just go to the back of the list, which we want.
		return targets[idx]
	
	def get_targets(self, power, character):
		if "WEAPON_RANGE" in power.flags:
			distance = character.weapon.range
		else:
			distance = power.distance
		
		return self.get_targets_ex(character, power.effect_shape, distance, power.target_mask)
		
	def get_targets_ex(self, character, shape, distance, target_types={'ENEMIES'}, source=None):
		"""Get targets in a range
		
		character -- character using the power
		shape -- the shape of area (line, burst, etc)
		range -- the range to grab (integer)
		target_types -- which type of targets to grab (SELF, ALLIES, ENEMIES, etc)
		
		"""
		
		# If we have a shape of "SELF" just return the character
		if shape == 'SELF':
			return [character]
		
		# Bump the range a bit to compensate for the first half "tile"
		# that the player occupies
		distance += character.size
		
		if not source:
			source = character.position

		targets = []
		
		if not target_types:
			return targets
			
		if self.is_server:
			combat = self.main['combats'].get(self.client_handle.combat_id, None)
			if not combat:
				hero_list = monster_list = {}
			else:
				hero_list = combat.hero_list
				monster_list = combat.monster_list
		else:
			hero_list = self.hero_list
			monster_list = self.monster_list
	
		tlist = []
		if 'SELF' in target_types:
			tlist.append(character)
		if 'ALLIES' in target_types:
			tlist.extend(hero_list.values() if character in hero_list.values() else monster_list.values())
		if 'ENEMIES' in target_types:
			tlist.extend(monster_list.values() if character in hero_list.values() else hero_list.values())
		
		if shape == 'ALL' or (self.is_server and shape == 'SINGLE'):
			targets = tlist
		elif shape == 'SINGLE':
			ori_ivnt = character.orientation.inverted()
			for target in tlist:
				# Convert to local space
				v = target.position - source
				v = ori_ivnt * v
				
				# Now do a simple bounds check
				if v[1] < distance + target.size and abs(v[0]) < target.size * 2: # Multiply by 2 to allow for more error
					targets.append(target)
		elif shape == 'BURST':
			for target in tlist:
				
				# Do a simple distance check
				if (target.position - source).length < distance:
					targets.append(target)
		elif shape == 'CONE':
			pi_fourths = pi / 4
			for target in tlist:
			
				# Start with a simple distance check
				if (target.position - source).length < distance:
					
					# Now do an angle check
					v1 = character.object.forward_vector
					v2 = target.position - character.position
					
					angle = v1.angle(v2, 0)
					
					if angle < pi_fourths:
						targets.append(target)
				
		return targets		
	
	def spawn(self, character, position):
		if hasattr(self, 'clients'):
			combat = self.main['combats'].get(self.client_handle.combat_id, None)
			if combat and character.id in combat.monster_list:
				self.animate_lock(character, "Spawn")
				combat.monster_list[character.id].position = position
				self.clients.invoke("position", character.id, *position)
	
	def move(self, character, linear = (0,0,0) , angular = (0,0,0) , local = False):
		"""Handles linear and angular movement of a character"""
		if self.is_server:
			# The only people that should be moving server side are monsters
			self.clients.invoke("move_monster", character.id, *linear)
			self.clients.invoke("rotate_monster", character.id, *angular)
			self.play_animation(character, "Move", mode=1)
		else:
			# Move the character
			character.object.move(linear, min=[-50, -50, 0], max=[50, 50, 0], local=local)
			
			# Now handle rpcs
			self.server.invoke("rotate", character.id, *angular)
			self.server.invoke("position", character.id, *character.position)
		
	def reposition(self, character, position):
		character.object.position = position
		self.server.invoke("position", character.id, *character.object.position)
		
	def despawn(self, character):
		pass
	
	def attack(self, power, character, multiplier=1):
		self.animate_weapon(character, character.get_action("Attack"))
		for target in self.get_targets(power, character):
			damage = character.weapon.damage*multiplier
			hit = True #character.accuracy - target.reflex + random.randint(3, 18) >= 11
			for callback in character.callbacks['ATTACK']:
				target, hit, damage, complete = callback(target, hit, damage)
				if complete:
					character.remove_callback("ATTACK", callback)
			if hit:
				self.deal_damage(character, target, power, damage, 'PHYSICAL')
			else:
				self.modify_health(target, 0)
	
	def use_power(self, character, power, auto_range=True):
		if isinstance(power, str):
			power = Power(power)
			
		if power.timer > 0:
			return
		if power.effect_shape == 'SELF' or not auto_range:
			power.use(self, character)
			power.timer = power.cool_down * TURN
		else:
			character.auto_power = power
			character.auto_target = character.targets[0]
		
	def check_save(self, defender, def_stat, offender, off_stat):
		def_value = 0
		off_value = 0
		
		if offender == 'STATIC':
			off_value = 10
			if off_stat in defender.saving_throw_mods:
				off_value += defender.saving_throw_mods['off_stat']
				
			return random.randint(1, 20) >= off_value
			
		if off_stat.strip().lower()[:3] in ('str', 'con', 'dex', 'int', 'wis', 'cha'):
			off_value = offender.level//2 + getattr(offender, off_stat.strip().lower()[:3]+"_mod")
			off_value += random.randint(1, 20)
			
		if def_stat.strip().lower() in ('ac', 'fortitude', 'reflex', 'will'):
			def_value = getattr(defender, def_stat.strip().lower())
			
		
		return def_value >= off_value
