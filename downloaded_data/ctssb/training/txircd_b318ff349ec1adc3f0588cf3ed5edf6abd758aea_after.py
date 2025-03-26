from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import DeferredList
from twisted.internet.endpoints import clientFromString, serverFromString
from twisted.internet.task import LoopingCall
from twisted.logger import FilteringLogObserver, globalLogPublisher, InvalidLogLevelError, LogLevel, LogLevelFilterPredicate, Logger
from twisted.plugin import getPlugins
from twisted.python.rebuild import rebuild
from txircd.config import Config, ConfigError, ConfigValidationError
from txircd.factory import ServerConnectFactory, ServerListenFactory, UserFactory
from txircd.module_interface import ICommand, IMode, IModuleData
from txircd.utils import CaseInsensitiveDictionary, ModeType, now, unescapeEndpointDescription
from weakref import WeakValueDictionary
import importlib, os, random, re, shelve, string, txircd.modules

class IRCd(Service):
	def __init__(self, configFileName):
		self.config = Config(self, configFileName)
		
		self.boundPorts = {}
		self.loadedModules = {}
		self._loadedModuleData = {}
		self._unloadingModules = {}
		self.commonModules = set()
		self.userCommands = {}
		self.serverCommands = {}
		self.channelModes = ({}, {}, {}, {})
		self.channelStatuses = {}
		self.channelStatusSymbols = {}
		self.channelStatusOrder = []
		self.channelModeTypes = {}
		self.userModes = ({}, {}, {}, {})
		self.userModeTypes = {}
		self.actions = {}
		self.storage = None
		self.storageSyncer = None
		self.dataCache = {}
		self.functionCache = {}
		
		self.serverID = None
		self.name = None
		self.isupport_tokens = {
			"CASEMAPPING": "strict-rfc1459",
			"CHANTYPES": "#",
		}
		self._uid = self._genUID()
		
		self.users = {}
		self.userNicks = CaseInsensitiveDictionary()
		self.channels = CaseInsensitiveDictionary(WeakValueDictionary)
		self.servers = {}
		self.serverNames = CaseInsensitiveDictionary()
		
		self._logFilter = LogLevelFilterPredicate()
		filterObserver = FilteringLogObserver(globalLogPublisher, (self._logFilter,))
		self.log = Logger("txircd", observer=filterObserver)
		
		self.startupTime = None
	
	def startService(self):
		self.log.info("Starting up...")
		self.startupTime = now()
		self.log.info("Loading configuration...")
		self.config.reload()
		self.name = self.config["server_name"]
		self.serverID = self.config["server_id"]
		self.log.info("Loading storage...")
		self.storage = shelve.open(self.config["datastore_path"], writeback=True)
		self.storageSyncer = LoopingCall(self.storage.sync)
		self.storageSyncer.start(self.config.get("storage_sync_interval", 5), now=False)
		self.log.info("Loading modules...")
		self._loadModules()
		self.log.info("Binding ports...")
		self._bindPorts()
		self.log.info("txircd started!")
		try:
			self._logFilter.setLogLevelForNamespace("txircd", LogLevel.levelWithName(self.config["log_level"]))
		except (KeyError, InvalidLogLevelError):
			self._logFilter.setLogLevelForNamespace("txircd", LogLevel.warn)
		self.runActionStandard("startup")
	
	def stopService(self):
		stopDeferreds = []
		self.log.info("Disconnecting servers...")
		serverList = self.servers.values() # Take the list of server objects
		self.servers = {} # And then destroy the server dict to inhibit server objects generating lots of noise
		for server in serverList:
			if server.nextClosest == self.serverID:
				stopDeferreds.append(server.disconnectedDeferred)
				allUsers = self.users.keys()
				for user in allUsers:
					if user[:3] == server.serverID:
						del self.users[user]
				server.transport.loseConnection()
		self.log.info("Disconnecting users...")
		userList = self.users.values() # Basically do the same thing I just did with the servers
		self.users = {}
		for user in userList:
			if user.transport:
				stopDeferreds.append(user.disconnectedDeferred)
				user.transport.loseConnection()
		self.log.info("Unloading modules...")
		moduleList = self.loadedModules.keys()
		for module in moduleList:
			self._unloadModule(module, False) # Incomplete unload is done to save time and because side effects are destroyed anyway
		self.log.info("Closing data storage...")
		if self.storageSyncer.running:
			self.storageSyncer.stop()
		self.storage.close() # a close() will sync() also
		self.log.info("Releasing ports...")
		stopDeferreds.extend(self._unbindPorts())
		return DeferredList(stopDeferreds)
	
	def _loadModules(self):
		for module in getPlugins(IModuleData, txircd.modules):
			if module.name in self.loadedModules:
				continue
			if module.core or module.name in self.config["modules"]:
				self._loadModuleData(module)
		for moduleName in self.config["modules"]:
			if moduleName not in self.loadedModules:
				self.log.warn("The module {module} failed to load.", module=moduleName)
	
	def loadModule(self, moduleName):
		"""
		Loads a module of the specified name.
		Raises ModuleLoadError if the module cannot be loaded.
		If the specified module is currently being unloaded, returns the
		DeferredList specified by the module when it was unloading with a
		callback to try to load the module again once it succeeds.
		"""
		if moduleName in self._unloadingModules:
			deferList = self._unloadingModules[moduleName]
			deferList.addCallback(self._tryLoadAgain, moduleName)
			return deferList
		for module in getPlugins(IModuleData, txircd.modules):
			if module.name == moduleName:
				rebuild(importlib.import_module(module.__module__)) # getPlugins doesn't recompile modules, so let's do that ourselves.
				self._loadModuleData(module)
				self.log.info("Loaded module {module}.", module=moduleName)
				break
	
	def _tryLoadAgain(self, _, moduleName):
		self.loadModule(moduleName)
	
	def _loadModuleData(self, module):
		if not IModuleData.providedBy(module):
			raise ModuleLoadError ("???", "Module does not implement module interface")
		if not module.name:
			raise ModuleLoadError ("???", "Module did not provide a name")
		if module.name in self.loadedModules:
			return
		module.hookIRCd(self)
		try:
			module.verifyConfig(self.config)
		except ConfigError as e:
			raise ModuleLoadError(module.name, e)
		moduleData = {
			"channelmodes": module.channelModes(),
			"usermodes": module.userModes(),
			"actions": module.actions(),
			"usercommands": module.userCommands(),
			"servercommands": module.serverCommands()
		}
		newChannelModes = ({}, {}, {}, {})
		newChannelStatuses = {}
		newUserModes = ({}, {}, {}, {})
		newActions = {}
		newUserCommands = {}
		newServerCommands = {}
		common = False
		for mode in moduleData["channelmodes"]:
			if mode[0] in self.channelModeTypes:
				raise ModuleLoadError (module.name, "Tries to implement channel mode +{} when that mode is already implemented.".format(mode[0]))
			if not IMode.providedBy(mode[2]):
				raise ModuleLoadError (module.name, "Returns a channel mode object (+{}) that doesn't implement IMode.".format(mode[0]))
			if mode[1] == ModeType.Status:
				if mode[4] in self.channelStatusSymbols:
					raise ModuleLoadError (module.name, "Tries to create a channel rank with symbol {} when that symbol is already in use.".format(mode[4]))
				try:
					newChannelStatuses[mode[0]] = (mode[4], mode[3], mode[2])
				except IndexError:
					raise ModuleLoadError (module.name, "Specifies channel status mode {} without a rank or symbol".format(mode[0]))
			else:
				newChannelModes[mode[1]][mode[0]] = mode[2]
			common = True
		for mode in moduleData["usermodes"]:
			if mode[0] in self.userModeTypes:
				raise ModuleLoadError (module.name, "Tries to implement user mode +{} when that mode is already implemented.".format(mode[0]))
			if not IMode.providedBy(mode[2]):
				raise ModuleLoadError (module.name, "Returns a user mode object (+{}) that doesn't implement IMode.".format(mode[0]))
			newUserModes[mode[1]][mode[0]] = mode[2]
			common = True
		for action in moduleData["actions"]:
			if action[0] not in newActions:
				newActions[action[0]] = [(action[2], action[1])]
			else:
				newActions[action[0]].append((action[2], action[1]))
		for command in moduleData["usercommands"]:
			if not ICommand.providedBy(command[2]):
				raise ModuleLoadError (module.name, "Returns a user command object ({}) that doesn't implement ICommand.".format(command[0]))
			if command[0] not in newUserCommands:
				newUserCommands[command[0]] = []
			newUserCommands[command[0]].append((command[2], command[1]))
		for command in moduleData["servercommands"]:
			if not ICommand.providedBy(command[2]):
				raise ModuleLoadError (module.name, "Returns a server command object ({}) that doesnt implement ICommand.".format(command[0]))
			if command[0] not in newServerCommands:
				newServerCommands[command[0]] = []
			newServerCommands[command[0]].append((command[2], command[1]))
			common = True
		if not common or module.multipleModulesForServers:
			common = module.requiredOnAllServers

		self.log.debug("Loaded data from {module.name}; committing data and calling hooks...", module=module)

		self.loadedModules[module.name] = module
		self._loadedModuleData[module.name] = moduleData
		if common:
			self.commonModules.add(module.name)
		
		self.runActionStandard("moduleload", module.name)
		module.load()
		
		for modeType, typeSet in enumerate(newChannelModes):
			for mode, implementation in typeSet.iteritems():
				self.channelModeTypes[mode] = modeType
				self.channelModes[modeType][mode] = implementation
		for mode, data in newChannelStatuses.iteritems():
			self.channelModeTypes[mode] = ModeType.Status
			self.channelStatuses[mode] = data
			self.channelStatusSymbols[data[0]] = mode
			for index, status in enumerate(self.channelStatusOrder):
				if self.channelStatuses[status][1] < data[1]:
					self.channelStatusOrder.insert(index, mode)
					break
			else:
				self.channelStatusOrder.append(mode)
		for modeType, typeSet in enumerate(newUserModes):
			for mode, implementation in typeSet.iteritems():
				self.userModeTypes[mode] = modeType
				self.userModes[modeType][mode] = implementation
		for action, actionList in newActions.iteritems():
			if action not in self.actions:
				self.actions[action] = []
			for actionData in actionList:
				for index, handlerData in enumerate(self.actions[action]):
					if handlerData[1] < actionData[1]:
						self.actions[action].insert(index, actionData)
						break
				else:
					self.actions[action].append(actionData)
		for command, dataList in newUserCommands.iteritems():
			if command not in self.userCommands:
				self.userCommands[command] = []
			for data in dataList:
				for index, cmd in enumerate(self.userCommands[command]):
					if cmd[1] < data[1]:
						self.userCommands[command].insert(index, data)
						break
				else:
					self.userCommands[command].append(data)
		for command, dataList in newServerCommands.iteritems():
			if command not in self.serverCommands:
				self.serverCommands[command] = []
			for data in dataList:
				for index, cmd in enumerate(self.serverCommands[command]):
					if cmd[1] < data[1]:
						self.serverCommands[command].insert(index, data)
						break
				else:
					self.serverCommands[command].append(data)
	
	def unloadModule(self, moduleName):
		"""
		Unloads the loaded module with the given name. Raises ValueError
		if the module cannot be unloaded because it's a core module.
		"""
		self._unloadModule(moduleName, True)
		self.log.info("Unloaded module {module}.", module=moduleName)
	
	def _unloadModule(self, moduleName, fullUnload):
		unloadDeferreds = []
		if moduleName not in self.loadedModules:
			return
		module = self.loadedModules[moduleName]
		if fullUnload and module.core:
			raise ValueError ("The module you're trying to unload is a core module.")
		moduleData = self._loadedModuleData[moduleName]
		d = module.unload()
		if d is not None:
			unloadDeferreds.append(d)
		
		if fullUnload:
			d = module.fullUnload()
			if d is not None:
				unloadDeferreds.append(d)
		
		for modeData in moduleData["channelmodes"]:
			if fullUnload: # Unset modes on full unload
				if modeData[1] == ModeType.Status:
					for channel in self.ircd.channels.itervalues():
						removeFromChannel = []
						for user, userData in channel.user.iteritems():
							if modeData[0] in userData["status"]:
								removeFromChannel.append((False, modeData[0], user.uuid))
						channel.setModes(removeFromChannel, self.serverID)
				elif modeData[1] == ModeType.List:
					for channel in self.ircd.channels.itervalues():
						if modeData[0] in channel.modes:
							removeFromChannel = []
							for paramData in channel.modes[modeData[0]]:
								removeFromChannel.append((False, modeData[0], paramData[0]))
							channel.setModes(removeFromChannel, self.serverID)
				else:
					for channel in self.ircd.channels.itervalues():
						if modeData[0] in channel.modes:
							channel.setModes([(False, modeData[0], channel.modes[modeData[0]])], self.serverID)
			
			if modeData[1] == ModeType.Status:
				del self.channelStatuses[modeData[0]]
				del self.channelStatusSymbols[modeData[4]]
				self.channelStatusOrder.remove(modeData[0])
			else:
				del self.channelModes[modeData[1]][modeData[0]]
			del self.channelModeTypes[modeData[0]]
		for modeData in moduleData["usermodes"]:
			if fullUnload: # Unset modes on full unload
				if modeData[1] == ModeType.List:
					for user in self.ircd.users.itervalues():
						if modeData[0] in user.modes:
							removeFromUser = []
							for paramData in user.modes[modeData[0]]:
								removeFromUser.append((False, modeData[0], paramData[0]))
							user.setModes(removeFromUser, self.serverID)
				else:
					for user in self.ircd.users.itervalues():
						if modeData[0] in user.modes:
							user.setModes([(False, modeData[0], user.modes[modeData[0]])], self.serverID)
			
			del self.userModes[modeData[1]][modeData[0]]
			del self.userModeTypes[modeData[0]]
		for actionData in moduleData["actions"]:
			self.actions[actionData[0]].remove((actionData[2], actionData[1]))
		for commandData in moduleData["usercommands"]:
			self.userCommands[commandData[0]].remove((commandData[2], commandData[1]))
		for commandData in moduleData["servercommands"]:
			self.serverCommands[commandData[0]].remove((commandData[2], commandData[1]))
		
		del self.loadedModules[moduleName]
		del self._loadedModuleData[moduleName]
		
		if fullUnload:
			self.runActionStandard("moduleunload", module.name)
		
		if unloadDeferreds:
			deferList = DeferredList(unloadDeferreds)
			self._unloadingModules[moduleName] = deferList
			deferList.addCallback(self._removeFromUnloadingList, moduleName)
			return deferList
	
	def _removeFromUnloadingList(self, _, moduleName):
		del self._unloadingModules[moduleName]
	
	def reloadModule(self, moduleName):
		"""
		Reloads the module with the given name.
		Returns a DeferredList if the module unloads with one or more Deferreds.
		May raise ModuleLoadError if the module cannot be loaded.
		"""
		deferList = self._unloadModule(moduleName, False)
		if deferList is None:
			deferList = self.loadModule(moduleName)
		else:
			deferList.addCallback(lambda result: self.loadModule(moduleName))
		return deferList

	def verifyConfig(self, config):
		# IRCd
		if "server_name" not in config:
			raise ConfigValidationError("server_name", "required item not found in configuration file.")
		if not isinstance(config["server_name"], basestring):
			raise ConfigValidationError("server_name", "value must be a string")
		if len(config["server_name"]) > 64:
			config["server_name"] = config["server_name"][:64]
			self.logConfigValidationWarning("server_name", "value is too long and has been truncated", config["server_name"])
		if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+$", config["server_name"]):
			raise ConfigValidationError("server_name", "server name must look like a valid hostname.")
		if "server_id" in config:
			if not isinstance(config["server_id"], basestring):
				raise ConfigValidationError("server_id", "value must be a string")
			else:
				config["server_id"] = config["server_id"].upper()
		else:
			randFromName = random.Random(config["server_name"])
			serverID = randFromName.choice(string.digits) + randFromName.choice(string.digits + string.uppercase) + randFromName.choice(string.digits + string.uppercase)
			config["server_id"] = serverID
		if len(config["server_id"]) != 3 or not config["server_id"].isalnum() or not config["server_id"][0].isdigit():
			raise ConfigValidationError("server_id", "value must be a 3-character alphanumeric string starting with a number.")
		if "server_description" not in config:
			raise ConfigValidationError("server_description", "required item not found in configuration file.")
		if not isinstance(config["server_description"], basestring):
			raise ConfigValidationError("server_description", "value must be a string")
		if not config["server_description"]:
			raise ConfigValidationError("server_description", "value must not be an empty string")
		if "network_name" not in config:
			raise ConfigValidationError("network_name", "required item not found in configuration file.")
		if not isinstance(config["network_name"], basestring):
			raise ConfigValidationError("network_name", "value must be a string")
		if not config["network_name"]:
			raise ConfigValidationError("network_name", "value must not be an empty string")
		if len(config["network_name"]) > 32:
			config["network_name"] = config["network_name"][:32]
			self.logConfigValidationWarning("network_name", "value is too long", config["network_name"])
		if "bind_client" not in config:
			config["bind_client"] = [ "tcp:6667:interface={::}" ]
			self.logConfigValidationWarning("bind_client", "no default client binding specified", "[ \"tcp:6667:interface={::}\" ]")
		if not isinstance(config["bind_client"], list):
			raise ConfigValidationError("bind_client", "value must be a list")
		for bindDesc in config["bind_client"]:
			if not isinstance(bindDesc, basestring):
				raise ConfigValidationError("bind_client", "every entry must be a string")
		if "bind_server" not in config:
			config["bind_server"] = []
		if not isinstance(config["bind_server"], list):
			raise ConfigValidationError("bind_server", "value must be a list")
		for bindDesc in config["bind_server"]:
			if not isinstance(bindDesc, basestring):
				raise ConfigValidationError("bind_server", "every entry must be a string")
		if "modules" not in config:
			config["modules"] = []
		if not isinstance(config["modules"], list):
			raise ConfigValidationError("modules", "value must be a list")
		for module in config["modules"]:
			if not isinstance(module, basestring):
				raise ConfigValidationError("modules", "every entry must be a string")
		if "links" in config:
			if not isinstance(config["links"], dict):
				raise ConfigValidationError("links", "value must be a dictionary")
			for desc, server in config["links"].iteritems():
				if not isinstance(desc, basestring):
					raise ConfigValidationError("links", "\"{}\" is an invalid server description".format(desc))
				if not isinstance(server, dict):
					raise ConfigValidationError("links", "values for \"{}\" must be a dictionary".format(desc))
				if "connect_descriptor" not in server:
					raise ConfigValidationError("links", "server \"{}\" must contain a \"connect_descriptor\" value".format(desc))
				if "in_password" in server:
					if not isinstance(server["in_password"], basestring):
						config["links"][desc]["in_password"] = str(server["in_password"])
				if "out_password" in server:
					if not isinstance(server["out_password"], basestring):
						config["links"][desc]["out_password"] = str(server["out_password"])
		if "datastore_path" not in config:
			config["datastore_path"] = "data.db"
		if self.storage is None and not os.access(config["datastore_path"], os.W_OK):
			raise ConfigValidationError("datastore_path", "path is invalid or txircd does not have write access")
		if "storage_sync_interval" in config and not isinstance(config["storage_sync_interval"], int):
			raise ConfigValidationError(config["storage_sync_interval"], "invalid number")

		# Channels
		if "channel_name_length" in config:
			if not isinstance(config["channel_name_length"], int) or config["channel_name_length"] < 0:
				raise ConfigValidationError("channel_name_length", "invalid number")
			elif config["channel_name_length"] > 64:
				config["channel_name_length"] = 64
				self.logConfigValidationWarning("channel_name_length", "value is too large", 64)
		if "modes_per_line" in config:
			if not isinstance(config["modes_per_line"], int) or config["modes_per_line"] < 0:
				raise ConfigValidationError("modes_per_line", "invalid number")
			elif config["modes_per_line"] > 20:
				config["modes_per_line"] = 20
				self.logConfigValidationWarning("modes_per_line", "value is too large", 20)
		if "channel_listmode_limit" in config:
			if not isinstance(config["channel_listmode_limit"], int) or config["channel_listmode_limit"] < 0:
				raise ConfigValidationError("channel_listmode_limit", "invalid number")
			if config["channel_listmode_limit"] > 256:
				config["channel_listmode_limit"] = 256
				self.logConfigValidationWarning("channel_listmode_limit", "value is too large", 256)

		# Users
		if "user_registration_timeout" in config:
			if not isinstance(config["user_registration_timeout"], int) or config["user_registration_timeout"] < 0:
				raise ConfigValidationError("user_registration_timeout", "invalid number")
			elif config["user_registration_timeout"] < 10:
				config["user_registration_timeout"] = 10
				self.logConfigValidationWarning("user_registration_timeout", "timeout could be too short for clients to register in time", 10)
		if "user_ping_frequency" in config and (not isinstance(config["user_ping_frequency"], int) or config["user_ping_frequency"] < 0):
			raise ConfigValidationError("user_ping_frequency", "invalid number")
		if "hostname_length" in config:
			if not isinstance(config["hostname_length"], int) or config["hostname_length"] < 0:
				raise ConfigValidationError("hostname_length", "invalid number")
			elif config["hostname_length"] > 64:
				config["hostname_length"] = 64
				self.logConfigValidationWarning("hostname_length", "value is too large", 64)
		if "ident_length" in config:
			if not isinstance(config["ident_length"], int) or config["ident_length"] < 0:
				raise ConfigValidationError("ident_length", "invalid number")
			elif config["ident_length"] > 12:
				config["ident_length"] = 12
				self.logConfigValidationWarning("ident_length", "value is too large", 12)
		if "gecos_length" in config:
			if not isinstance(config["gecos_length"], int) or config["gecos_length"] < 0:
				raise ConfigValidationError("gecos_length", "invalid number")
			elif config["gecos_length"] > 128:
				config["gecos_length"] = 128
				self.logConfigValidationWarning("gecos_length", "value is too large", 128)
		if "user_listmode_limit" in config:
			if not isinstance(config["user_listmode_limit"], int) or config["user_listmode_limit"] < 0:
				raise ConfigValidationError("user_listmode_limit", "invalid number")
			if config["user_listmode_limit"] > 256:
				config["user_listmode_limit"] = 256
				self.logConfigValidationWarning("user_listmode_limit", "value is too large", 256)

		# Servers
		if "server_registration_timeout" in config:
			if not isinstance(config["server_registration_timeout"], int) or config["server_registration_timeout"] < 0:
				raise ConfigValidationError("server_registration_timeout", "invalid number")
			elif config["server_registration_timeout"] < 10:
				config["server_registration_timeout"] = 10
				self.logConfigValidationWarning("server_registration_timeout", "timeout could be too short for servers to register in time", 10)
		if "server_ping_frequency" in config and (not isinstance(config["server_ping_frequency"], int) or config["server_ping_frequency"] < 0):
			raise ConfigValidationError("server_ping_frequency", "invalid number")

		for module in self.loadedModules.itervalues():
			module.verifyConfig(config)

	def logConfigValidationWarning(self, key, message, default):
		self.log.warn("Config value \"{configKey}\" is invalid ({message}); the value has been set to a default of \"{default}\".", configKey=key, message=message, default=default)

	def rehash(self):
		"""
		Reloads the configuration file and applies changes.
		"""
		self.log.info("Rehashing...")
		self.config.reload()
		d = self._unbindPorts() # Unbind the ports that are bound
		if d: # And then bind the new ones
			DeferredList(d).addCallback(lambda result: self._bindPorts())
		else:
			self._bindPorts()
		
		try:
			self._logFilter.setLogLevelForNamespace("txircd", LogLevel.levelWithName(self.config["log_level"]))
		except (KeyError, InvalidLogLevelError):
			pass # If we can't set a new log level, we'll keep the old one
		
		for module in self.loadedModules.itervalues():
			module.rehash()
	
	def _bindPorts(self):
		for bindDesc in self.config["bind_client"]:
			try:
				endpoint = serverFromString(reactor, unescapeEndpointDescription(bindDesc))
			except ValueError as e:
				self.log.error(e)
				continue
			listenDeferred = endpoint.listen(UserFactory(self))
			listenDeferred.addCallback(self._savePort, bindDesc, "client")
			listenDeferred.addErrback(self._logNotBound, bindDesc)
		for bindDesc in self.config["bind_server"]:
			try:
				endpoint = serverFromString(reactor, unescapeEndpointDescription(bindDesc))
			except ValueError as e:
				self.log.error(e)
				continue
			listenDeferred = endpoint.listen(ServerListenFactory(self))
			listenDeferred.addCallback(self._savePort, bindDesc, "server")
			listenDeferred.addErrback(self._logNotBound, bindDesc)
	
	def _unbindPorts(self):
		deferreds = []
		for port in self.boundPorts.itervalues():
			d = port.stopListening()
			if d:
				deferreds.append(d)
		return deferreds
	
	def _savePort(self, port, desc, portType):
		self.boundPorts[desc] = port
		self.log.debug("Bound endpoint '{endpointDescription}' for {portType} connections.", endpointDescription=desc, portType=portType)
	
	def _logNotBound(self, err, desc):
		self.log.error("Could not bind '{endpointDescription}': {errorMsg}", endpointDescription=desc, errorMsg=err)
	
	def createUUID(self):
		"""
		Gets the next UUID for a new client.
		"""
		newUUID = self.serverID + self._uid.next()
		while newUUID in self.users: # It'll take over 1.5 billion connections to loop around, but we still
			newUUID = self.serverID + self._uid.next() # want to be extra safe and avoid collisions
		self.log.debug("Generated new UUID {uuid}", uuid=newUUID)
		return newUUID
	
	def _genUID(self):
		uid = "AAAAAA"
		while True:
			yield uid
			uid = self._incrementUID(uid)
	
	def _incrementUID(self, uid):
		if uid == "Z": # The first character must be a letter
			return "A" # So wrap that around
		if uid[-1] == "9":
			return self._incrementUID(uid[:-1]) + "A"
		if uid[-1] == "Z":
			return uid[:-1] + "0"
		return uid[:-1] + chr(ord(uid[-1]) + 1)
	
	def generateISupportList(self):
		isupport = self.isupport_tokens.copy()
		statusSymbolOrder = "".join([self.channelStatuses[status][0] for status in self.channelStatusOrder])
		isupport["CHANMODES"] = ",".join(["".join(modes) for modes in self.channelModes])
		isupport["CHANNELEN"] = self.config.get("channel_name_length", 64)
		isupport["NETWORK"] = self.config["network_name"]
		isupport["PREFIX"] = "({}){}".format("".join(self.channelStatusOrder), statusSymbolOrder)
		isupport["STATUSMSG"] = statusSymbolOrder
		isupport["USERMODES"] = ",".join(["".join(modes) for modes in self.userModes])
		self.runActionStandard("buildisupport", isupport)
		isupportList = []
		for key, val in isupport.iteritems():
			if val is None:
				isupportList.append(key)
			else:
				isupportList.append("{}={}".format(key, val))
		return isupportList
	
	def connectServer(self, name):
		"""
		Connect a server with the given name in the configuration.
		Returns a Deferred for the connection when we can successfully connect
		or None if the server is already connected or if we're unable to find
		information for that server in the configuration.
		"""
		if name in self.serverNames:
			return None
		if name not in self.config.get("links", {}):
			return None
		serverConfig = self.config["links"][name]
		endpoint = clientFromString(reactor, unescapeEndpointDescription(serverConfig["connect_descriptor"]))
		d = endpoint.connect(ServerConnectFactory(self))
		d.addCallback(self._completeServerConnection, name)
		return d
	
	def _completeServerConnection(self, result, name):
		self.log.info("Connected to server {serverName}", serverName=name)
		self.runActionStandard("initiateserverconnection", result)
	
	def broadcastToServers(self, fromServer, command, *params, **kw):
		"""
		Broadcasts a message to all connected servers. The fromServer parameter
		should be the server from which the message came; if this server is the
		originating server, specify None for fromServer.
		"""
		for server in self.servers.itervalues():
			if server.nextClosest == self.serverID and server != fromServer:
				server.sendMessage(command, *params, **kw)
	
	def _getActionModes(self, actionName, *params, **kw):
		users = []
		channels = []
		if "users" in kw:
			users = kw["users"]
		if "channels" in kw:
			channels = kw["channels"]
		
		functionList = []
		
		if users:
			genericUserActionName = "modeactioncheck-user-{}".format(actionName)
			genericUserActionNameWithChannel = "modeactioncheck-user-withchannel-{}".format(actionName)
			for modeType in self.userModes:
				for mode, modeObj in modeType.iteritems():
					if actionName not in modeObj.affectedActions:
						continue
					priority = modeObj.affectedActions[actionName]
					actionList = []
					# Because Python doesn't properly capture variables in lambdas, we have to force static capture
					# by wrapping lambdas in more lambdas.
					# I wish Python wasn't this gross.
					for action in self.actions.get("modeactioncheck-user", []):
						actionList.append(((lambda action, actionName, mode: lambda user, *params: action[0](actionName, mode, user, *params))(action, actionName, mode), action[1]))
					for action in self.actions.get("modeactioncheck-user-withchannel", []):
						for channel in channels:
							actionList.append(((lambda action, actionName, mode, channel: lambda user, *params: action[0](actionName, mode, user, channel, *params))(action, actionName, mode, channel), action[1]))
					for action in self.actions.get(genericUserActionName, []):
						actionList.append(((lambda action, mode: lambda user, *params: action[0](mode, user, *params))(action, mode), action[1]))
					for action in self.actions.get(genericUserActionNameWithChannel, []):
						for channel in channels:
							actionList.append(((lambda action, mode, channel: lambda user, *params: action[0](mode, user, channel, *params))(action, mode, channel), action[1]))
					modeUserActionName = "modeactioncheck-user-{}-{}".format(mode, actionName)
					modeUserActionNameWithChannel = "modeactioncheck-user-withchannel-{}-{}".format(mode, actionName)
					for action in self.actions.get(modeUserActionNameWithChannel, []):
						for channel in channels:
							actionList.append(((lambda action, channel: lambda user, *params: action[0](user, channel, *params))(action, channel), action[1]))
					actionList = sorted(self.actions.get(modeUserActionName, []) + actionList, key=lambda action: action[1], reverse=True)
					applyUsers = []
					for user in users:
						for action in actionList:
							param = action[0](user, *params)
							if param is not None:
								if param is not False:
									applyUsers.append((user, param))
								break
					for user, param in applyUsers:
						functionList.append(((lambda modeObj, actionName, user, param: lambda *params: modeObj.apply(actionName, user, param, *params))(modeObj, actionName, user, param), priority))
		
		if channels:
			genericChannelActionName = "modeactioncheck-channel-{}".format(actionName)
			genericChannelActionNameWithUser = "modeactioncheck-channel-withuser-{}".format(actionName)
			for modeType in self.channelModes:
				for mode, modeObj in modeType.iteritems():
					if actionName not in modeObj.affectedActions:
						continue
					priority = modeObj.affectedActions[actionName]
					actionList = []
					for action in self.actions.get("modeactioncheck-channel", []):
						actionList.append(((lambda action, actionName, mode: lambda channel, *params: action[0](actionName, mode, channel, *params))(action, actionName, mode), action[1]))
					for action in self.actions.get("modeactioncheck-channel-withuser", []):
						for user in users:
							actionList.append(((lambda action, actionName, mode, user: lambda channel, *params: action[0](actionName, mode, channel, user, *params))(action, actionName, mode, user), action[1]))
					for action in self.actions.get(genericChannelActionName, []):
						actionList.append(((lambda action, mode: lambda channel, *params: action[0](mode, channel, *params))(action, mode), action[1]))
					for action in self.actions.get(genericChannelActionNameWithUser, []):
						for user in users:
							actionList.append(((lambda action, mode, user: lambda channel, *params: action[0](mode, channel, user, *params))(action, mode, user), action[1]))
					modeChannelActionName = "modeactioncheck-channel-{}-{}".format(mode, actionName)
					modeChannelActionNameWithUser = "modeactioncheck-channel-withuser-{}-{}".format(mode, actionName)
					for action in self.actions.get(modeChannelActionNameWithUser, []):
						for user in users:
							actionList.append(((lambda action, user: lambda channel, *params: action[0](channel, user, *params))(action, user), action[1]))
					actionList = sorted(self.actions.get(modeChannelActionName, []) + actionList, key=lambda action: action[1], reverse=True)
					applyChannels = []
					for channel in channels:
						for action in actionList:
							param = action[0](channel, *params)
							if param is not None:
								if param is not False:
									applyChannels.append((channel, param))
								break
					for channel, param in applyChannels:
						functionList.append(((lambda modeObj, actionName, channel, param: lambda *params: modeObj.apply(actionName, channel, param, *params))(modeObj, actionName, channel, param), priority))
		return functionList
	
	def _getActionFunctionList(self, actionName, *params, **kw):
		functionList = self.actions.get(actionName, [])
		functionList = functionList + self._getActionModes(actionName, *params, **kw)
		return sorted(functionList, key=lambda action: action[1], reverse=True)
	
	def _combineActionFunctionLists(self, actionLists):
		"""
		Combines multiple lists of action functions into one.
		Assumes all lists are sorted.
		Takes a dict mapping action names to their action function lists.
		Returns a list in priority order (highest to lowest) of (actionName, function) tuples.
		"""
		fullActionList = []
		for actionName, actionList in actionLists.iteritems():
			insertPos = 0
			for action in actionList:
				try:
					while fullActionList[insertPos][1] > action[1]:
						insertPos += 1
					fullActionList.insert(insertPos, (actionName, action[0]))
				except IndexError:
					fullActionList.append((actionName, action[0]))
				insertPos += 1
		return fullActionList
	
	def runActionStandard(self, actionName, *params, **kw):
		"""
		Calls all functions for a given action with the given parameters in
		priority order. Accepts the 'users' and 'channels' keyword arguments to
		determine which mode handlers should be included.
		"""
		actionList = self._getActionFunctionList(actionName, *params, **kw)
		for action in actionList:
			action[0](*params)
	
	def runActionUntilTrue(self, actionName, *params, **kw):
		"""
		Calls functions for a given action with the given parameters in
		priority order until one of them returns a true value. Returns True
		when one of the functions returned True. Accepts the 'users' and
		'channels' keyword arguments to determine which mode handlers should be
		included.
		"""
		actionList = self._getActionFunctionList(actionName, *params, **kw)
		for action in actionList:
			if action[0](*params):
				return True
		return False
	
	def runActionUntilFalse(self, actionName, *params, **kw):
		"""
		Calls functions for a given action with the given parameters in
		priority order until one of them returns a false value. Returns True
		when one of the functions returned False. Accepts the 'users' and
		'channels' keyword arguments to determine which mode handlers should be
		included.
		"""
		actionList = self._getActionFunctionList(actionName, *params, **kw)
		for action in actionList:
			if not action[0](*params):
				return True
		return False
	
	def runActionUntilValue(self, actionName, *params, **kw):
		"""
		Calls functions for a given action with the given parameters in
		priority order until one of them returns a non-None value. Returns the
		value returned by the function that returned a non-None value. Accepts
		the 'users' and 'channels' keyword arguments to determine which mode
		handlers should be included.
		"""
		actionList = self._getActionFunctionList(actionName, *params, **kw)
		for action in actionList:
			value = action[0](*params)
			if value is not None:
				return value
		return None
	
	def runActionFlagTrue(self, actionName, *params, **kw):
		"""
		Calls all functions for a given action with the given parameters in
		priority order. Returns True when one of the functions returns a true
		value. Accepts the 'users' and 'channels' keyword arguments to
		determine which mode handlers should be included.
		"""
		oneIsTrue = False
		actionList = self._getActionFunctionList(actionName, *params, **kw)
		for action in actionList:
			if action[0](*params):
				oneIsTrue = True
		return oneIsTrue
	
	def runActionFlagFalse(self, actionName, *params, **kw):
		"""
		Calls all functions for a given action with the given parameters in
		priority order. Returns True when one of the functions returns a false
		value. Accepts the 'users' and 'channels' keyword arguments to
		determine which mode handlers should be included.
		"""
		oneIsFalse = False
		actionList = self._getActionFunctionList(actionName, *params, **kw)
		for action in actionList:
			if action[0](*params):
				oneIsFalse = True
		return oneIsFalse
	
	def runActionProcessing(self, actionName, data, *params, **kw):
		"""
		Calls functions for a given action with the given parameters in
		priority order until the provided data is all processed (the data
		parameter becomes empty). Accepts 'users' and 'channels' keyword
		arguments to determine which mode handlers should be included.
		"""
		actionList = self._getActionFunctionList(actionName, data, *params, **kw)
		for action in actionList:
			action[0](data, *params)
			if not data:
				return
	
	def runActionProcessingMultiple(self, actionName, dataList, *params, **kw):
		"""
		Calls functions for a given action with the given parameters in
		priority order until the provided data is all processed (all of the
		data structures in the dataList parameter become empty). Accepts
		'users' and 'channels' keyword arguments to determine which mode
		handlers should be included.
		"""
		paramList = dataList + params
		actionList = self._getActionFunctionList(actionName, *paramList, **kw)
		for action in actionList:
			action[0](*paramList)
			for data in dataList:
				if data:
					break
			else:
				return
	
	def runComboActionStandard(self, actionList, **kw):
		"""
		Calls all functions for the given actions with the given parameters in
		priority order. Actions are specifed as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Accepts 'users' and 'channels' keyword arguments to determine which
		mode handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		for actionName, actionFunc in funcList:
			actionFunc(*actionParameters[actionName])
	
	def runComboActionUntilTrue(self, actionList, **kw):
		"""
		Calls functions for the given actions with the given parameters in
		priority order until one of the functions returns a true value. Actions
		are specified as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Returns True if one of the functions returned a true value. Accepts
		'users' and 'channels' keyword arguments to determine which mode
		handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		for actionName, actionFunc in funcList:
			if actionFunc(*actionParameters[actionName]):
				return True
		return False
	
	def runComboActionUntilFalse(self, actionList, **kw):
		"""
		Calls functions for the given actions with the given parameters in
		priority order until one of the functions returns a false value.
		Actions are specified as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Returns True if one of the functions returned a false value. Accepts
		'users' and 'channels' keyword arguments to determine which mode
		handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		for actionName, actionFunc in funcList:
			if not actionFunc(*actionParameters[actionName]):
				return True
		return False
	
	def runComboActionUntilValue(self, actionList, **kw):
		"""
		Calls functions for the given actions with the given parameters in
		priority order until one of the functions returns a non-None value.
		Actions are specified as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Returns the value returned by the function that returned a non-None
		value. Accepts 'users' and 'channels' keyword arguments to determine
		which mode handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		for actionName, actionFunc in funcList:
			value = actionFunc(*actionParameters[actionName])
			if value is not None:
				return value
		return None
	
	def runComboActionFlagTrue(self, actionList, **kw):
		"""
		Calls all functions for the given actions with the given parameters in
		priority order. Actions are specified as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Returns True if any of the functions called returned a true value.
		Accepts 'users' and 'channels' keyword arguments to determine which
		mode handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		oneIsTrue = False
		for actionName, actionFunc in funcList:
			if actionFunc(*actionParameters[actionName]):
				oneIsTrue = True
		return oneIsTrue
	
	def runComboActionFlagFalse(self, actionList, **kw):
		"""
		Calls all functions for the given actions with the given parameters in
		priority order. Actions are specified as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Returns True if any of the functions called returned a false value.
		Accepts 'users' and 'channels' keyword arguments to determine which
		mode handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		oneIsFalse = False
		for actionName, actionFunc in funcList:
			if not actionFunc(*actionParameters[actionName]):
				oneIsFalse = True
		return oneIsFalse
	
	def runComboActionProcessing(self, data, actionList, **kw):
		"""
		Calls functions for the given actions with the given parameters in
		priority order until the data given has been processed (the data
		parameter becomes empty). Actions are specified as a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Accepts 'users' and 'channels' keyword arguments to determine which
		mode handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = [data] + action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		for actionName, actionFunc in funcList:
			actionFunc(*actionParameters[actionName])
			if not data:
				break
	
	def runComboActionProcessingMultiple(self, dataList, actionList, **kw):
		"""
		Calls functions for the given actions with the given parameters in
		priority order until the data given has been processed (all the data
		items in the dataList parameter become empty). Actions are specified as
		a list of tuples:
		[ ("action1", param1, param2, ...), ("action2", param1, param2, ...) ]
		Accepts 'users' and 'channels' keyword arguments to determine which
		mode handlers should be included.
		"""
		actionFuncLists = {}
		actionParameters = {}
		for action in actionList:
			parameters = dataList + action[1:]
			actionParameters[action[0]] = parameters
			actionFuncLists[action[0]] = self._getActionFunctionList(action[0], *parameters, **kw)
		funcList = self._combineActionFunctionLists(actionFuncLists)
		for actionName, actionFunc in funcList:
			actionFunc(*actionParameters[actionName])
			for data in dataList:
				if data:
					break
			else:
				return

class ModuleLoadError(Exception):
	def __init__(self, name, desc):
		self.message = "Module {} could not be loaded: {}".format(name, desc)