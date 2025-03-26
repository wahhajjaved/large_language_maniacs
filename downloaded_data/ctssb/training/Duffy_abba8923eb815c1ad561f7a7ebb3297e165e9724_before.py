import random
import re
import logging

from smskeeper.models import User, Entry, Message

from smskeeper import sms_util, msg_util, helper_util
from smskeeper.states import tutorial
from smskeeper import actions, keeper_constants

from peanut.settings import constants

logger = logging.getLogger(__name__)


def dealWithNicety(user, msg, keeperNumber):
	cleaned = msg.strip().lower()
	if "thank" in cleaned:
		sms_util.sendMsg(user, "You're welcome.", None, keeperNumber)
	if "hello" in cleaned or "hi" in cleaned:
		sms_util.sendMsg(user, "Hi there.", None, keeperNumber)

def dealWithYesNo(user, msg, keeperNumber):
	sms_util.sendMsg(user, "\xF0\x9F\x98\xB3 I'm not smart enough to know what you mean yet.  Try 'huh?' if you're stuck.", None, keeperNumber)

def getPreviousMessage(user):
	# Normally would sort by added but unit tests barf since they get added at same time
	# Here, sorting by id should accomplish the same goal
	msgs = Message.objects.filter(user=user, incoming=True).order_by("-id")[:2]

	if len(msgs) == 2:
		return msgs[1]
	else:
		return None

def getInferredLabel(user):
	# Normally would sort by added but unit tests barf since they get added at same time
	# Here, sorting by id should accomplish the same goal
	incoming_messages = Message.objects.filter(user=user, incoming=True).order_by("-id")
	if len(incoming_messages) < 2:
		return None

	for i in range(1, len(incoming_messages)):
		msg_body = incoming_messages[i].getBody()
		logger.info("message -%d: %s" % (i, msg_body))
		if msg_util.isLabel(msg_body):
			return msg_body
		elif msg_util.isDeleteCommand(msg_body):
			continue
		else:
			return None

	return None


def dealWithDelete(user, msg, keeperNumber):
	words = msg.strip().lower().split(" ")
	words.remove("delete")
	# what remains in words could be ["1"], ["1,2"], ["1,", "2"] etc.
	requested_indices = set()
	for word in words:
		subwords = word.split(",")
		logger.debug("word, subwords: %s, %s" % (word, subwords))
		for subword in subwords:
			try:
				requested_indices.add(int(subword))
			except:
				pass
	logger.debug("requested indices: %s" % requested_indices)
	item_indices = map(lambda x: x - 1, requested_indices)

	item_indices = sorted(item_indices, reverse=True)
	logger.debug(item_indices)

	label = None
	if msg_util.hasLabel(msg):
		text, label, handles = msg_util.getMessagePieces(msg)
	else:
		label = getInferredLabel(user)

	if label:
		entries = Entry.fetchEntries(user=user, label=label)
		out_of_range = list()
		deleted_texts = list()
		if entries is None:
			helper_util.sendNotFoundMessage(user, label, keeperNumber)
			return
		for item_index in item_indices:
			if item_index < 0 or item_index >= len(entries):
				out_of_range.append(item_index)
				continue
			entry = entries[item_index]
			entry.hidden = True
			entry.save()
			if entry.text:
				deleted_texts.append(entry.text)
			else:
				deleted_texts.append("item " + str(item_index+1))

		if len(deleted_texts) > 0:
			if len(deleted_texts) > 1:
				retMsg = "%d items" % len(deleted_texts)
			else:
				retMsg = "'%s'" % (deleted_texts[0])
			sms_util.sendMsg(user, 'Ok, I deleted %s' % (retMsg), None, keeperNumber)
		if len(out_of_range) > 0:
			out_of_range_string = ", ".join(map(lambda x: str(x + 1), out_of_range))
			sms_util.sendMsg(user, 'Can\'t delete %s in %s' % (out_of_range_string, label), None, keeperNumber)
		actions.fetch(user, label, keeperNumber)
	else:
		sms_util.sendMsg(user, 'Sorry, I\'m not sure which hashtag you\'re referring to. Try "delete [number] [hashtag]"', None, keeperNumber)

def dealWithPrintHashtags(user, keeperNumber):
	#print out all of the active hashtags for the account
	listText = ""
	labels = Entry.fetchAllLabels(user)
	if len(labels) == 0:
		listText = "You don't have anything tagged. Yet."
	for label in labels:
		entries = Entry.fetchEntries(user=user, label=label)
		if len(entries) > 0:
			listText += "%s (%d)\n" % (label, len(entries))

	sms_util.sendMsg(user, listText, None, keeperNumber)

def pickItemForUserLabel(user, label, keeperNumber):
	entries = Entry.fetchEntries(user=user, label=label)
	if len(entries) == 0:
		helper_util.sendNotFoundMessage(user, label, keeperNumber)
		return

	entry = random.choice(entries)
	if entry.img_url:
		sms_util.sendMsg(user, "My pick for %s:" % label, None, keeperNumber)
		sms_util.sendMsg(user, entry.text, entry.img_url, keeperNumber)
	else:
		sms_util.sendMsg(user, "My pick for %s: %s" % (label, entry.text), None, keeperNumber)

def dealWithActivation(user, msg, keeperNumber):
	text, label, handles = msg_util.getMessagePieces(msg)

	try:
		userToActivate = User.objects.get(phone_number=text)
		userToActivate.activate()
		sms_util.sendMsg(user, "Done. %s is now activated" % text, None, keeperNumber)
		sms_util.sendMsgs(userToActivate, ["Oh hello. Someone else entered your magic phrase. Welcome!"] + keeper_constants.INTRO_MESSAGES, None, keeperNumber)
	except User.DoesNotExist:
		sms_util.sendMsg(user, "Sorry, couldn't find a user with phone number %s" % text, None, keeperNumber)


def dealWithCreateHandle(user, msg, keeperNumber):
	phoneNumbers, remaining_str = msg_util.extractPhoneNumbers(msg)
	phoneNumber = phoneNumbers[0]

	words = remaining_str.strip().split(' ')
	handle = None
	for word in words:
		if msg_util.isHandle(word):
			handle = word
			break

	contact, didCreateUser, oldUser = actions.createHandle(user, handle, phoneNumber)

	if oldUser is not None:
		if oldUser.phone_number == phoneNumber:
			sms_util.sendMsg(user, "%s is already set to %s" % (handle, phoneNumber), None, keeperNumber)
		else:
			sms_util.sendMsg(user, "%s is now set to %s (used to be %s)" % (handle, phoneNumber, oldUser.phone_number), None, keeperNumber)
	else:
		sms_util.sendMsg(user, "%s is now set to %s" % (handle, phoneNumber), None, keeperNumber)


#   Main logic for processing a message
#   Pulled out so it can be called either from sms code or command line
def process(user, msg, requestDict, keeperNumber):
	if "NumMedia" in requestDict:
		numMedia = int(requestDict["NumMedia"])
	else:
		numMedia = 0

	try:
		if re.match("yippee ki yay motherfucker", msg):
			raise NameError("intentional exception")
		# STATE_REMIND
		elif msg_util.isRemindCommand(msg) and not msg_util.isClearCommand(msg) and not msg_util.isFetchCommand(msg):
			# TODO  Fix this state so the logic isn't so complex
			user.setState(keeper_constants.STATE_REMIND)
			user.save()
			# Reprocess
			return False
		elif msg_util.isActivateCommand(msg) and user.phone_number in constants.DEV_PHONE_NUMBERS:
			dealWithActivation(user, msg, keeperNumber)
		# STATE_NORMAL
		elif msg_util.isPrintHashtagsCommand(msg):
			# this must come before the isLabel() hashtag fetch check or we will try to look for a #hashtags list
			dealWithPrintHashtags(user, keeperNumber)
		# STATE_NORMAL
		elif msg_util.isFetchCommand(msg) and numMedia == 0:
			actions.fetch(user, msg, keeperNumber)
		# STATE_NORMAL
		elif msg_util.isClearCommand(msg) and numMedia == 0:
			actions.clear(user, msg, keeperNumber)
		# STATE_NORMAL
		elif msg_util.isPickCommand(msg) and numMedia == 0:
			label = msg_util.getLabel(msg)
			pickItemForUserLabel(user, label, keeperNumber)
		# STATE_NORMAL
		elif msg_util.isHelpCommand(msg):
			actions.help(user, msg, keeperNumber)
		elif msg_util.isSetTipFrequencyCommand(msg):
			actions.setTipFrequency(user, msg, keeperNumber)
		# STATE_ADD
		elif msg_util.isCreateHandleCommand(msg):
			dealWithCreateHandle(user, msg, keeperNumber)

		# STATE_DELETE
		elif msg_util.isDeleteCommand(msg):
			dealWithDelete(user, msg, keeperNumber)
		else:  # treat this as an add command
			# STATE_NORMAL
			# STATE_ADD
			if not msg_util.hasLabel(msg):
				if msg_util.isNicety(msg):
					dealWithNicety(user, msg, keeperNumber)
					return True
				elif msg_util.isYesNo(msg):
					dealWithYesNo(user, msg, keeperNumber)
					return True
				# if the user didn't add a label, throw it in #unassigned
				msg += ' ' + keeper_constants.UNASSIGNED_LABEL
			entries, unresolvedHandles = actions.add(user, msg, requestDict, keeperNumber, True)
			if len(unresolvedHandles) > 0:
				user.setState(keeper_constants.STATE_UNRESOLVED_HANDLES)
				user.setStateData(keeper_constants.ENTRY_IDS_DATA_KEY, map(lambda entry: entry.id, entries))
				user.setStateData(keeper_constants.UNRESOLVED_HANDLES_DATA_KEY, unresolvedHandles)
				user.save()
				return False

		return True
	except:
		sms_util.sendMsg(user, keeper_constants.GENERIC_ERROR_MESSAGE, None, keeperNumber)
		raise


