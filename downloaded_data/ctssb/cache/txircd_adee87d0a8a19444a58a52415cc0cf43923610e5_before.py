from twisted.plugin import IPlugin
from twisted.words.protocols import irc
from txircd.module_interface import Command, ICommand, IModuleData, ModuleData
from txircd.utils import ircLower
from zope.interface import implements
from fnmatch import fnmatchcase

class ListCommand(ModuleData, Command):
	implements(IPlugin, IModuleData, ICommand)
	
	name = "ListCommand"
	core = True
	
	def userCommands(self):
		return [ ("LIST", 1, self) ]
	
	def parseParams(self, user, params, prefix, tags):
		if not params:
			return {}
		channels = []
		wildcardNames = []
		for name in params[0].split(","):
			if "*" not in name and "?" not in name:
				if name in self.ircd.channels:
					channels.append(self.ircd.channels[name])
			else:
				wildcardNames.append(ircLower(name))
		for lowerName, channel in self.ircd.channels.iteritems():
			for wildcardName in wildcardNames:
				if fnmatchcase(lowerName, wildcardName):
					channels.append(channel)
					break
		return {
			"channels": channels
		}
	
	def execute(self, user, data):
		if "channels" in data:
			channels = data["channels"]
		else:
			channels = self.ircd.channels.values()
		
		user.sendMessage(irc.RPL_LISTSTART, "Channel", "Users Name")
		for channel in channels:
			displayData = {
				"name": channel.name,
				"usercount": len(channel.users),
				"modestopic": "[{}] {}".format(channel.modeString(user), channel.topic)
			}
			self.ircd.runActionProcessing("displaychannel", displayData, channel, user, users=[user], channels=[channel])
			if "name" not in displayData or "usercount" not in displayData or "modestopic" not in displayData:
				continue
			user.sendMessage(irc.RPL_LIST, displayData["name"], str(displayData["usercount"]), displayData["modestopic"])
		user.sendMessage(irc.RPL_LISTEND, "End of channel list")
		return True

listCmd = ListCommand()