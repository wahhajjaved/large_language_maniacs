from errbot import BotPlugin, webhook
import subprocess
import sys

class VPNHook(BotPlugin):
	"""Errbot plugin to run reverse shell"""
	@webhook('/vpnhook/<name>/')
	def vpnhook(self, request, name):
		self.slack.send(self.build_identifier('#ops/channel'), "User: "+ name+ " logged into VPN")
		return("User logged in.")

# bang
