from twisted.internet import reactor
from twisted.plugin import IPlugin
from txircd.config import ConfigValidationError
from txircd.module_interface import IModuleData, ModuleData
from txircd.utils import now
from zope.interface import implements
from weakref import WeakKeyDictionary
from datetime import timedelta

class AccountNickProtect(ModuleData):
	implements(IPlugin, IModuleData)
	
	name = "AccountNickProtect"
	blockedNickChangeUsers = WeakKeyDictionary()
	
	def actions(self):
		return [ ("welcome", 1, self.checkNickOnConnect),
			("changenick", 1, self.checkNickOnNickChange),
			("quit", 1, self.cancelTimerOnQuit),
			("commandpermission-NICK", 10, self.checkCanChangeNick) ]
	
	def verifyConfig(self, config):
		if "account_nick_protect_seconds" in config:
			if not isinstance(config["account_nick_protect_seconds"], int) or config["account_nick_protect_seconds"] < 1:
				raise ConfigValidationError("account_nick_protect_seconds", "invalid number")
		if "account_nick_recover_seconds" in config:
			if not isinstance(config["account_nick_recover_seconds"], int) or config["account_nick_recover_seconds"] < 1:
				raise ConfigValidationError("account_nick_recover_seconds", "invalid number")
	
	def checkNickOnConnect(self, user):
		if not self.userSignedIntoNickAccount(user):
			self.applyNickProtection(user)
	
	def checkNickOnNickChange(self, user, oldNick, fromServer):
		self.cancelOldProtectTimer(user)
		if not self.userSignedIntoNickAccount(user):
			self.applyNickProtection(user)
	
	def cancelTimerOnQuit(self, user, reason, fromServer):
		self.cancelOldProtectTimer(user)
	
	def checkCanChangeNick(self, user, data):
		if user not in self.blockedNickChangeUsers:
			return None
		if self.blockedNickChangeUsers[user] < now():
			del self.blockedNickChangeUsers[user]
			return None
		user.sendMessage("NOTICE", "You can't change nicknames yet.")
		return False
	
	def applyNickProtection(self, user):
		if user.uuid[:3] != self.ircd.serverID:
			return
		protectDelay = self.ircd.config.get("account_nick_protect_seconds", 30)
		user.sendMessage("NOTICE", "The nickname you're using is owned by an account to which you are not identified. Please identify to that account or change your nick in the next \x02{}\x02 seconds.".format(protectDelay))
		user.cache["accountNickProtectTimer"] = reactor.callLater(protectDelay, self.resolveNickProtection, user, user.nick)
	
	def resolveNickProtection(self, user, nick):
		if user.nick != nick:
			return
		if self.userSignedIntoNickAccount(user):
			return
		user.changeNick(user.uuid)
		recoverSeconds = self.ircd.config.get("account_nick_recover_seconds", 10)
		if recoverSeconds > 0:
			recoveryTime = timedelta(seconds = recoverSeconds)
			self.blockedNickChangeUsers[user] = now() + recoveryTime
	
	def cancelOldProtectTimer(self, user):
		if "accountNickProtectTimer" not in user.cache:
			return
		if user.cache["accountNickProtectTimer"].active():
			user.cache["accountNickProtectTimer"].cancel()
		del user.cache["accountNickProtectTimer"]
	
	def userSignedIntoNickAccount(self, user):
		accountName = self.ircd.runActionUntilValue("accountfromnick", user.nick)
		if accountName is None:
			return True # Nick applies to all accounts and no-account users
		userAccount = user.metadataValue("account")
		if userAccount == accountName:
			return True
		return False

accountNickProtect = AccountNickProtect()