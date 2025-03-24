from pyxmpp.exceptions import JIDError
from pyxmpp.jabber.client import JabberClient
from pyxmpp.jid import JID
from pyxmpp.presence import Presence
import pynotifyd

class BaseJabberClient(JabberClient):
	def __init__(self, jid, password):
		JabberClient.__init__(self, jid, password)

	### Section: own hooks
	def handle_session_started(self):
		pass

	def handle_contact_available(self, jid, state):
		"""
		@type jid: pyxmpp.jid.JID
		@type state: unicode
		"""
		pass

	def handle_contact_unavailable(self, jid):
		"""
		@type jid: pyxmpp.jid.JID
		"""
		pass

	### Section: handler functions passed to pyxmpp
	def handle_presence_available(self, presence):
		jid = presence.get_from_jid()
		show = presence.get_show() or u"online"
		self.handle_contact_available(jid, show)

	def handle_presence_unavailable(self, presence):
		jid = presence.get_from_jid()
		self.handle_contact_unavailable(jid)

	### Section: pyxmpp JabberClient API methods
	def session_started(self):
		self.stream.set_presence_handler("available", self.handle_presence_available)
		self.stream.set_presence_handler("unavailable", self.handle_presence_unavailable)
		self.handle_session_started()
		self.request_roster()
		self.stream.send(Presence())

def make_set(value):
	if isinstance(value, list):
		pass # ok
	elif isinstance(value, str):
		value = map(str.strip, value.split(","))
	else:
		raise ValueError("invalid value type")
	return set(value)

def validate_recipient(recipient):
	"""Extracts and parses the keys "jabber", "jabber_exclude_resources"
	and "jabber_include_states" from the given recipient configuration.

	@type recipient: dict
	@raises pynotifyd.PyNotifyDConfigurationError:
	@rtype: (pyxmpp.jid.JID, set([str]), set([str]))
	@returns: (jid, exclude_resources, include_states)
	"""
	try:
		jid = recipient["jabber"]
	except KeyError:
		raise pynotifyd.PyNotifyDConfigurationError(
				"missing jabber on contact")
	try:
		jid = JID(jid)
	except JIDError, err:
		raise pynotifyd.PyNotifyDConfigurationError(
				"failed to parse jabber id: %s" % str(err))
	try:
		exclude_resources = make_set(recipient["jabber_exclude_resources"])
	except KeyError:
		exclude_resources = set()
	except ValueError, err:
		raise pynotifyd.PyNotifyDConfigurationError(
				"invalid value for jabber_exclude_resources: %s" % str(err))
	try:
		include_states = make_set(recipient["jabber_include_states"])
	except KeyError:
		include_states = set(["online"])
	except ValueError:
		raise pynotifyd.PyNotifyDConfigurationError(
				"invalid value for jabber_include_states: %s" % str(err))
	if not include_states:
		raise pynotifyd.PyNotifyDConfigurationError(
				"jabber_include_states is empty")
	return jid, exclude_resources, include_states
