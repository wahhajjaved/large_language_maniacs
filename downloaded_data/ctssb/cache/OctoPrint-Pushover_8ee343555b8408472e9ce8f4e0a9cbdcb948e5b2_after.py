# coding=utf-8
from __future__ import absolute_import
import os
import sys

import octoprint.plugin
from octoprint.events import Events

from flask.ext.login import current_user

import httplib, urllib, json

__author__ = "Thijs Bekke <thijsbekke@gmail.com>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Released under terms of the AGPLv3 License"
__plugin_name__ = "Pushover"

from PIL import Image

import flask, requests, StringIO, PIL
import octoprint.plugin


class PushoverPlugin(octoprint.plugin.EventHandlerPlugin,
					 octoprint.plugin.SettingsPlugin,
					 octoprint.plugin.StartupPlugin,
					 octoprint.plugin.SimpleApiPlugin,
					 octoprint.plugin.TemplatePlugin,
					 octoprint.plugin.AssetPlugin,
					 octoprint.plugin.OctoPrintPlugin):
	user_key = ""
	api_url = "https://api.pushover.net/1"
	m70_cmd = ""

	def get_assets(self):
		return {
			"js": ["js/pushover.js"]
		}

	def get_api_commands(self):
		return dict(
			test=["api_key", "user_key"]
		)

	def on_api_command(self, command, data):
		if command == "test":
			# When we are testing the token, create a test notification
			payload = {
				"message": "pewpewpew!! OctoPrint works.",
				"token": data["api_key"],
				"user": data["user_key"],
			}

			# If there is a sound, include it in the payload
			if "sound" in data:
				payload["sound"] = data["sound"]

			if "image" in data:
				payload["image"] = data["image"]

			# Validate the user key and send a message
			try:
				self.validate_pushover(data["user_key"])
				self.event_message(payload)
				return flask.jsonify(dict(success=True))
			except Exception as e:
				return flask.jsonify(dict(success=False, msg=str(e.message)))
		return flask.make_response("Unknown command", 400)


	def validate_pushover(self, user_key):
		"""
		Validate settings, this will do a post request too users/validate.json
		:param user_key: 
		:return: 
		"""
		if not user_key:
			raise ValueError("No user key provided")

		self.user_key = user_key
		try:
			r = requests.post(self.api_url + "/users/validate.json", data=self.create_payload({}))

			if r is not None and not r.status_code == 200:
				raise ValueError("error while instantiating Pushover, header %s" % r.status_code)

			response = json.loads(r.content)

			if response["status"] == 1:
				self._logger.info("Connected to Pushover")

				return True

		except Exception, e:
			raise ValueError("error while instantiating Pushover: %s" % str(e))

		return False

	def image(self):

		snapshot_url = self._settings.global_get(["webcam", "snapshot"])
		if not snapshot_url:
			return None

		self._logger.debug("Snapshot URL: " + str(snapshot_url))
		image = requests.get(snapshot_url, stream=True).content

		hflip = self._settings.global_get(["webcam", "flipH"])
		vflip = self._settings.global_get(["webcam", "flipV"])
		rotate = self._settings.global_get(["webcam", "rotate90"])

		if hflip or vflip or rotate:
			# https://www.blog.pythonlibrary.org/2017/10/05/how-to-rotate-mirror-photos-with-python/
			image_obj = Image.open(StringIO.StringIO(image))
			if hflip:
				image_obj = image_obj.transpose(Image.FLIP_LEFT_RIGHT)
			if vflip:
				image_obj = image_obj.transpose(Image.FLIP_TOP_BOTTOM)
			if rotate:
				image_obj = image_obj.rotate(90)

			# https://stackoverflow.com/questions/646286/python-pil-how-to-write-png-image-to-string/5504072
			output = StringIO.StringIO()
			image_obj.save(output, format="JPEG")
			image = output.getvalue()
			output.close()
		return image

	def sent_m70(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		"""
		M70 Gcode commands are used for sending a text when print is paused
		:param comm_instance: 
		:param phase: 
		:param cmd: 
		:param cmd_type: 
		:param gcode: 
		:param args: 
		:param kwargs: 
		:return: 
		"""
		if gcode and gcode == "M70":
			self.m70_cmd = cmd[3:]

	def PrintDone(self, payload):
		file = os.path.basename(payload["file"])
		elapsed_time_in_seconds = payload["time"]

		import datetime
		import octoprint.util
		elapsed_time = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=elapsed_time_in_seconds))

		# Create the message
		return self._settings.get(["events", "PrintDone", "message"]).format(**locals())

	def PrintFailed(self, payload):
		file = os.path.basename(payload["file"])
		return self._settings.get(["events", "PrintFailed", "message"]).format(**locals())

	def PrintPaused(self, payload):
		m70_cmd = ""
		if (self.m70_cmd != ""):
			m70_cmd = self.m70_cmd

		return self._settings.get(["events", "PrintPaused", "message"]).format(**locals())

	def Waiting(self, payload):
		return self.PrintPaused(payload)

	def PrintStarted(self, payload):
		self.m70_cmd = ""

	def on_event(self, event, payload):
		# It's easier to ask forgiveness than to ask permission.
		if (payload is None):
			payload = {}
		try:
			# Method exists, and was used.
			payload["message"] = getattr(self, event)(payload)

			self._logger.info("Event triggered: %s " % str(event))
		except AttributeError:
			return

		# Does the event exists in the settings ?
		if not event in self.get_settings_defaults()["events"]:
			return False

		# Only continue when there is a priority
		priority = self._settings.get(["events", event, "priority"])

		# By default, messages have normal priority (a priority of 0).
		# We do not support the Emergency Priority (2) because there is no way of canceling it here,
		if priority:
			payload["priority"] = priority

		self.event_message(payload)


	def event_message(self, payload):
		"""
		Do send the notification to the cloud :)
		:param payload: 
		:return: 
		"""
		# Create an url, if the fqdn is not correct you can manually set it at your config.yaml
		url = self._settings.get(["url"])
		if (url):
			payload["url"] = url
		else:
			# Create an url
			import socket
			payload["url"] = "http://%s" % socket.getfqdn()

		if "sound" not in payload:
			# If no sound parameter is specified, the user"s default tone will play.
			# If the user has not chosen a custom sound, the standard Pushover sound will play.
			sound = self._settings.get(["sound"])
			if sound:
				payload["sound"] = sound

		if "device" not in payload:
			# If no device parameter is specified, get it from the settings.
			device = self._settings.get(["device"])
			if device:
				payload["device"] = device

		if self._printer_profile_manager is not None and "name" in self._printer_profile_manager.get_current_or_default():
			payload["title"] = "Octoprint: %s" % self._printer_profile_manager.get_current_or_default()["name"]

		files = {}
		try:
			if self._settings.get(["image"]) or ("image" in payload and payload["image"]):
				files['attachment'] = ("image.jpg", self.image())
		except Exception, e:
			self._logger.exception(str(e))

		try:
			r = requests.post(self.api_url + "/messages.json",
							  files=files, data=self.create_payload(payload))
			self._logger.info("Response: " + str(r.content))
		except Exception, e:
			self._logger.exception(str(e))

	def on_after_startup(self):
		try:
			self.validate_pushover(self._settings.get(["user_key"]))
		except Exception, e:
			self._logger.exception(str(e))

	def on_settings_save(self, data):
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		try:
			import threading
			thread = threading.Thread(target=self.validate_pushover, args=(self._settings.get(["user_key"]),))
			thread.daemon = True
			thread.start()
		except Exception, e:
			self._logger.exception(str(e))

	def on_settings_load(self):
		data = octoprint.plugin.SettingsPlugin.on_settings_load(self)

		# only return our restricted settings to admin users - this is only needed for OctoPrint <= 1.2.16
		restricted = ("token", "user_key")
		for r in restricted:
			if r in data and (current_user is None or current_user.is_anonymous() or not current_user.is_admin()):
				data[r] = None

		return data

	def get_settings_restricted_paths(self):
		# only used in OctoPrint versions > 1.2.16
		return dict(admin=[["token"], ["user_key"]])

	def create_payload(self, payload):
		if "token" not in payload:
			payload["token"] = self._settings.get(["token"])

		if "user" not in payload:
			payload["user"] = self.user_key

		return payload

	def get_settings_defaults(self):
		return dict(
			token="apWqpdodabxA5Uw11rY4g4gC1Vbbrs",
			user_key=None,
			sound=None,
			device=None,
			image=True,
			events=dict(
				PrintDone=dict(
					name="Print done",
					message="Print job finished: {file}, finished printing in {elapsed_time}",
					priority=0
				),
				PrintFailed=dict(
					name="Print failed",
					message="Print job failed: {file}",
					priority=0
				),
				PrintPaused=dict(
					name="Print paused",
					help="Send a notification when a Pause event is received. When a <code>m70</code> was sent "
						 "to the printer, the message will be appended to the notification.",
					message="Print job paused {m70_cmd}",
					priority=0
				),
				Waiting=dict(
					name="Printer is waiting",
					help="Send a notification when a Waiting event is received. When a <code>m70</code> was sent "
						 "to the printer, the message will be appended to the notification.",
					message="Printer is waiting {m70_cmd}",
					priority=0
				)
			)
		)

	def get_template_vars(self):
		return dict(
			sounds=self.get_sounds(),
			events=self.get_settings_defaults()["events"]
		)

	def get_sounds(self):
		try:
			r = requests.get(self.api_url + "/sounds.json?token="+ self._settings.get(["token"]) )
			return json.loads(r.content)["sounds"]
		except Exception, e:
			self._logger.exception(str(e))
			return {}

	def get_template_configs(self):
		return [
			dict(type="settings", name="Pushover", custom_bindings=True)
		]

	def get_update_information(self):
		return dict(
			pushover=dict(
				displayName="Pushover Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="thijsbekke",
				repo="OctoPrint-Pushover",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/thijsbekke/OctoPrint-Pushover/archive/{target_version}.zip"
			)
		)


__plugin_name__ = "Pushover"


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = PushoverPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.comm.protocol.gcode.sent": __plugin_implementation__.sent_m70
	}
