""" Karma Plugin (botwot plugins.karma) """

# Copyright 2015 Ray Schulz <https://rascul.io>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import random
import re
import string
import time

from pyaib.plugins import keyword, observe, plugin_class
from pyaib.db import db_driver

@plugin_class
@plugin_class.requires('db')
class Karma(object):
	def __init__(self, context, config):
		self.context = context
		self.db = context.db.get("karma")
		self.damage_types = [
			["blast", "blasts"],
			["cleave", "cleaves"],
			["crush", "crushes"],
			["hack", "hacks"],
			["hit", "hits"],
			["lance", "lances"],
			["pierce", "pierces"],
			["pound", "pounds"],
			["scythe", "scythes"],
			["shoot", "shoots"],
			["slash", "slashes"],
			["slice", "slices"],
			["smite", "smites"],
			["stab", "stabs"],
			["sting", "stings"],
			["strike", "strikes"],
			["whip", "whips"]]
		
		
		random.seed()
	
	
	def procs(self, s):
		""" strip punctuation and make lower case a string """
		return "".join(ch for ch in s if ch not in set(string.punctuation)).lower()
	
	
	def hit(self, attacker, defender):
		""" 
		hit somebody
		return true if attacker hits defender, else false
		"""
		
		total = attacker["abs_karma"] + attacker["abs_karma"] / 2 + defender["abs_karma"] + defender["abs_karma"] / 2
		total = total + 10 if total < 20 else total
		
		res = random.randint(1, total)
		
		if res <= attacker["abs_karma"]:
			return True
		elif total - defender["abs_karma"] < res <= total:
			return False
		else:
			if random.choice([attacker, defender]) == attacker:
				return True
			else:
				return False
		
	
	def fight(self, attacker, defender):
		status = 0
		message = ""
		
		if self.hit(attacker, defender):
			status += 1
			message = "%s %s %s" % (attacker["name"], random.choice(self.damage_types)[1], defender["name"])
		else:
			status -= 1
			message = "%s fails to %s %s" % (attacker["name"], random.choice(self.damage_types)[0], defender["name"])
		
		if self.hit(defender, attacker):
			status -= 1
			message = "%s  <>  %s %s %s" % (message, defender["name"], random.choice(self.damage_types)[1], attacker["name"])
		else:
			status += 1
			message = "%s  <>  %s fails to %s %s" % (message, defender["name"], random.choice(self.damage_types)[0], attacker["name"])
		
		return status, message
	
	
	def steal_karma(self, winner, loser):
		""" chance of winner stealing a karma from the loser """
		
		chance = .15
		
		if (winner["karma"] > 0 > loser["karma"]) or (winner["karma"] < 0 < loser["karma"]):
			chance = .6
		
		if random.random() <= chance:
			if winner["karma"] < 0:
				winner["karma"] -= 1
			elif winner["karma"] > 0:
				winner["karma"] += 1
			
			if loser["karma"] < 0:
				loser["karma"] -= 1
			elif loser["karma"] > 0:
				loser["karma"] += 1
			
			for i in winner, loser:
				item = self.db.get("%s/karma" % i["name"])
				item.value = i["karma"]
				item.commit()
			
			return True
		else:
			return False
	
	
	@keyword('k')
	def keyword_kill(self, context, msg, trigger, args, kargs):
		""" <player> - kill player """
		
		if len(args) != 1:
			return
		
		if msg.target != context.config.plugin.karma.channel:
			return
		
		item = self.db.get("%s/next_fight" % msg.sender)
		if item.value and float(item.value) > time.time():
			msg.reply("%s: You are too exhausted." % msg.sender)
			return
				
		item.value = random.randint(180, 900) + time.time()
		item.commit()
		
		attacker = {}
		defender = {}
		
		attacker["name"] = self.procs(msg.sender)
		defender["name"] = self.procs(args[0])
		
		for i in [attacker, defender]:
			i["karma"] = int(self.db.get("%s/karma" % i["name"]).value or 0)
			i["abs_karma"] = abs(i["karma"])
		
		status, message = self.fight(attacker, defender)
		msg.reply(message)
		
		if status > 0:
			if self.steal_karma(attacker, defender):
				msg.reply("%s steals a karma!" % attacker["name"])
		elif status < 0:
			if self.steal_karma(defender, attacker):
				msg.reply("%s steals a karma!" % defender["name"])
	
	
	@keyword('title')
	def keyword_title(self, context, msg, trigger, args, kargs):
		""" set the title """
		
		if len(args) < 1:
			return
		
		name = self.procs(msg.sender)
		item = self.db.get('%s/title' % name)
		item.value = ' '.join(args)
		item.commit()
		
		msg.reply("%s: Ok." % msg.sender)
	
	
	@keyword('karma')
	def keyword_karma(self, context, msg, trigger, args, kargs):
		""" tell you karmas """
		
		name = self.procs(msg.sender)
		karma = self.db.get("%s/karma" % name).value or 0
		
		if karma == 0:
			context.PRIVMSG(msg.sender, "You have no karma.")
		elif karma > 0:
			context.PRIVMSG(msg.sender, "You have %s karma%s." % (karma, "s" if karma > 1 else ""))
			context.PRIVMSG(msg.sender, "You serve the Light.")
		elif karma < 0:
			context.PRIVMSG(msg.sender, "You have %s karma%s." % (abs(karma), "s" if karma < -1 else ""))
			context.PRIVMSG(msg.sender, "You serve the Dark.")
		
		item = self.db.get("%s/next_karma" % msg.sender)
		t = time.time()
		if item.value and int(item.value) > t:
			context.PRIVMSG(msg.sender, "You can give karma in %s more minutes." % (int(int(item.value) - t) / 60))
		
		item = self.db.get("%s/next_fight" % msg.sender)
		t = time.time()
		if item.value and int(item.value) > t:
			context.PRIVMSG(msg.sender, "You are exhausted for %s more minutes." % (int(int(item.value) - t) / 60))
	
	
	@keyword('whois')
	def keyword_whois(self, context, msg, trigger, args, kargs):
		""" whois somebody """
		
		if len(args) != 1:
			return
		
		name = self.procs(args[0])
		
		item = self.db.get("%s/karma" % name)
		karma = int(item.value or 0)
		
		item = self.db.get("%s/title" % name)
		if item.value:
			name = ' '.join([name, item.value])
		
		if karma < 0:
			msg.reply("%s serves the Dark." % name)
		elif karma > 0:
			msg.reply("%s serves the Light." % name)
		else:
			msg.reply("%s is a %s." % (name, random.choice(["vagabond", "mercenary", "bastard", "wildcard", "failure", "butterfly", "harlot"])))
	
	
	@keyword('align')
	def keyword_align(self, context, msg, trigger, args, kargs):
		""" set your alignment """
		
		if len(args) != 1:
			return
		
		name = self.procs(msg.sender)
		align = self.procs(args[0])
		item = self.db.get("%s/karma" % name)
		karma = int(item.value or 0)
		
		if align == "light":
			if karma < 0:
				karma *= -1
			elif karma == 0:
				karma = 1
			msg.reply("%s: You now serve the Light." % msg.sender)
		elif align == "dark":
			if karma > 0:
				karma *= -1
			elif karma == 0:
				karma = -1
			msg.reply("%s: You now serve the Dark." % msg.sender)
		
		item.value = karma
		item.commit()
	
	
	@observe("IRC_MSG_PRIVMSG")
	def observe_privmsg_karma(self, context, msg):
		""" Look for karmas """
		
		m = re.match(r'(?P<name>\S+)(?P<op>\+\+|--)', msg.message)
		if m:
			name = self.procs(m.groupdict().get("name"))
			op = m.groupdict().get("op")
			
			if name != self.procs(msg.sender) and name != context.botnick:
				item = self.db.get("%s/next_karma" % msg.sender)
				
				if (not item.value) or (float(item.value) < time.time()):
					item.value = random.randint(180, 900) + time.time()
					item.commit()
					
					item = self.db.get("%s/karma" % name)
					karma = int(item.value or 0)
					abs_karma = abs(karma)
					
					if abs_karma > 0:
						if op == "++":
							abs_karma += 1
						elif op == "--":
							abs_karma -= 1
						
						if karma < 0:
							item.value = abs_karma * -1
						else:
							item.value = abs_karma
						item.commit()

