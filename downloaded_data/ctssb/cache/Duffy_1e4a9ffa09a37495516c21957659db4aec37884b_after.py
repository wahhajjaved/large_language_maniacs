import pytz
import logging
import re
import json
import datetime
from dateutil import relativedelta

from peanut.settings import constants

from common import natty_util, date_util

from smskeeper import sms_util, msg_util, actions
from smskeeper import keeper_constants
from smskeeper import helper_util
from smskeeper import analytics

from smskeeper.models import Entry, Contact

logger = logging.getLogger(__name__)


# Returns True if the the user entered any type of timing information
def validTime(nattyResult):
	return nattyResult.hadDate or nattyResult.hadTime


# Returns True if this message has a valid time and it doesn't look like another remind command
# If reminderSent is true, then we look for again or snooze which if found, we'll assume is a followup
# Like "remind me again in 5 minutes"
# If the message (without timing info) only is "remind me" then also is a followup due to "remind me in 5 minutes"
# Otherwise False
def isFollowup(user, entry, nattyResult, reminderSent):
	if validTime(nattyResult):
		cleanedText = msg_util.cleanedReminder(nattyResult.queryWithoutTiming)  # no "Remind me"
		if reminderSent and msg_util.isRemindCommand(nattyResult.queryWithoutTiming):
			query = nattyResult.queryWithoutTiming.lower()
			if "again" in query or "snooze" in query:
				return True
			else:
				return False
		# Covers cases where there the cleanedText is "in" or "around"
		elif len(cleanedText) <= 2 or cleanedText == "around":
			return True
		# If they write "no, remind me sunday instead" then want to process as followup
		elif msg_util.startsWithNo(nattyResult.queryWithoutTiming):
			return True
		elif user.product_id == keeper_constants.TODO_PRODUCT_ID:
			# This could be a new entry due to todos
			# Check to see if there's a fuzzy match to the last entry.  If so, treat as followup
			bestEntry, score = actions.getBestEntryMatch(user, nattyResult.queryWithoutTiming)
			if bestEntry and bestEntry.id == entry.id and score > 60:
				logger.debug("User %s: I think '%s' is a followup because it matched entry id %s with score %s" % (user.id, nattyResult.queryWithoutTiming, bestEntry.id, score))
				return True
			return False
		# Regular reminders will just assume that if it doesn't have "remind me" in it then its followup
		elif not msg_util.isRemindCommand(nattyResult.queryWithoutTiming):
			return True

	return False


def isTutorial(user):
	return False if user.getStateData(keeper_constants.FROM_TUTORIAL_KEY) is None else True


def dealWithTutorialEdgecases(user, msg, keeperNumber):
	# If we're coming from the tutorial and we find a message with a zipcode in it...just ignore the whole message
	# Would be great not to have a hack here
	if user.getStateData(keeper_constants.FROM_TUTORIAL_KEY):
		postalCodes = re.search(r'.*(\d{5}(\-\d{4})?)', msg)
		if postalCodes:
			# ignore the message
			return True
	return False


# If we got a natty result with no time, then we need to pick one.
# If there was no date, pick the default time (could be 9am tmr or later today)
# If there a date, then see if its today.  If so, pick best default time for today.
# If not today, then pick that day and set to the default time (9am)
def dealWithDefaultTime(user, nattyResult):
	if nattyResult.hadTime:
		return nattyResult

	# If there was no time whatsoever, plug in the default time
	if not nattyResult.hadDate:
		nattyResult.utcTime = getDefaultTime(user)
	else:
		tzAwareNow = date_util.now(user.getTimezone())
		tzAwareDate = nattyResult.utcTime.astimezone(user.getTimezone())

		# If the user says 'today', then this should match up.
		if tzAwareDate.day == tzAwareNow.day:
			nattyResult.utcTime = getDefaultTime(user, isToday=True)
		else:
			tzAwareDate = tzAwareDate.replace(hour=9, minute=0)
			nattyResult.utcTime = tzAwareDate.astimezone(pytz.utc)

	return nattyResult


# Remove and replace troublesome strings for Natty
# This is meant to just be used to change up the string for processing, not used later for
def fixMsgForNatty(msg, user):
	newMsg = msg

	# Replace 'around' with 'at' since natty recognizes that better
	newMsg = newMsg.replace("around", "at")

	# Fix 3 digit numbers with timing info like "520p"
	threeDigitsWithAP = re.search(r'.* (?P<time>\d{3}) ?(p|a)', newMsg)
	if threeDigitsWithAP:
		oldtime = threeDigitsWithAP.group("time")  # This is the 520 part, the other is the 'p'
		newtime = oldtime[0] + ":" + oldtime[1:]

		newMsg = newMsg.replace(oldtime, newtime)

	# Fix 3 digit numbers with timing info like "at 520". Not that we don't have p/a but we require 'at'
	threeDigitsWithAT = re.search(r'.*at (?P<time>\d{3})', newMsg)
	if threeDigitsWithAT:
		oldtime = threeDigitsWithAT.group("time")
		newtime = oldtime[0] + ":" + oldtime[1:]

		newMsg = newMsg.replace(oldtime, newtime)

	# Change '4th' to 'June 4th'
	dayOfMonth = re.search(r'.*the (?P<time>(1st|2nd|3rd|[0-9]+th))', newMsg)
	if dayOfMonth:
		localtime = date_util.now(user.getTimezone())

		dayStr = dayOfMonth.group("time")
		number = int(filter(str.isdigit, str(dayStr)))

		if number <= localtime.day:
			# They said 1st while it was June 2nd, so return July 1st
			monthName = (localtime + relativedelta.relativedelta(months=1)).strftime("%B")
		else:
			monthName = localtime.strftime("%B")

		# Turn 'the 9th' into 'June 9th'
		newMsg = newMsg.replace("the %s" % dayStr, "%s %s" % (monthName, dayStr))

	# Take anything like 7ish and just make 7
	ish = re.search(r'.* (?P<time>[0-9]+)ish', newMsg)
	if ish:
		time = ish.group("time")
		newMsg = newMsg.replace(time + "ish", time)

	return newMsg


def getBestNattyResult(nattyResults):
	if len(nattyResults) == 0:
		return None

	# Sort by the date, we want to soonest first
	nattyResults = sorted(nattyResults, key=lambda x: x.utcTime)

	# prefer anything that has "at" in the text
	# Make sure it's "at " (with a space) since Saturday will match
	nattyResults = sorted(nattyResults, key=lambda x: "at " in x.textUsed, reverse=True)
	return nattyResults[0]


def process(user, msg, requestDict, keeperNumber):
	if dealWithTutorialEdgecases(user, msg, keeperNumber):
		return True

	# Deal with legacy stuff
	if '#remind' in msg:
		msg = msg.replace("#reminder", "remind me")
		msg = msg.replace("#remind", "remind me")

	nattyMsg = fixMsgForNatty(msg, user)
	nattyResult = getBestNattyResult(natty_util.getNattyInfo(nattyMsg, user.getTimezone()))

	if not nattyResult:
		nattyResult = natty_util.NattyResult(None, msg, None, False, False)

	# Deal with situation where a time wasn't specified
	if not nattyResult.hadTime:
		nattyResult = dealWithDefaultTime(user, nattyResult)

	entry = None
	if user.getStateData(keeper_constants.ENTRY_ID_DATA_KEY):
		entryId = int(user.getStateData(keeper_constants.ENTRY_ID_DATA_KEY))
		try:
			entry = Entry.objects.get(id=entryId)
		except Entry.DoesNotExist:
			pass

	# Create a new reminder
	if not entry:
		sendFollowup = False

		if not validTime(nattyResult) or isTutorial(user):
			sendFollowup = True

		entry = createReminderEntry(user, nattyResult, msg, sendFollowup, keeperNumber)

		# See if the entry didn't create. This means there's unresolved handes
		if not entry:
			return False  # Send back for reprocessing by unknown handles state

		sendCompletionResponse(user, entry, sendFollowup, keeperNumber)

		# If we came from the tutorial, then set state and return False so we go back for reprocessing
		if user.getStateData(keeper_constants.FROM_TUTORIAL_KEY):
			# Note, some behind the scene magic sets the state and state_data for us.  So this call
			# is kind of overwritten.  Done so the tutorial state can worry about its state and formatting
			user.setState(keeper_constants.STATE_TUTORIAL_REMIND)
			# We set this so it knows what entry was created
			user.setStateData(keeper_constants.ENTRY_ID_DATA_KEY, entry.id)
			user.save()
			return False

		# Always save the entryId state since we always come back into this state.
		# If they don't enter timing info then we kick out
		user.setStateData(keeper_constants.ENTRY_ID_DATA_KEY, entry.id)
		user.save()
	else:
		# If we have an entry id, then that means we are doing a follow up
		# See if what they entered is a valid time and if so, assign it.
		# If not, kick out to normal mode and re-process

		if user.getStateData("fromUnresolvedHandles"):
			logger.debug("User %s: Going to deal with unresolved handles for entry %s and user %s" % (user.id, entry.id, user.id))

			# Mark it that we're not coming back from unresolved handle
			# So incase there's a followup we don't, re-enter this section
			user.setStateData("fromUnresolvedHandles", False)
			user.save()

			unresolvedHandles = user.getStateData(keeper_constants.UNRESOLVED_HANDLES_DATA_KEY)
			# See if we have all the handles resolved
			if len(unresolvedHandles) == 0:
				for handle in user.getStateData(keeper_constants.RESOLVED_HANDLES_DATA_KEY):
					contact = Contact.fetchByHandle(user, handle)
					entry.users.add(contact.target)

				sendCompletionResponse(user, entry, False, keeperNumber)

			else:
				# This message could be a correction or something else.  Might need more logic here
				sendCompletionResponse(user, entry, False, keeperNumber)
		elif isFollowup(user, entry, nattyResult, user.getStateData("reminderSent")):
			logger.debug("User %s: Doing followup on entry %s with msg %s" % (user.id, entry.id, msg))
			isSnooze = user.getStateData("reminderSent")
			updateReminderEntry(user, nattyResult, msg, entry, keeperNumber, isSnooze)
			sendCompletionResponse(user, entry, False, keeperNumber)

			if isSnooze:
				entry.hidden = False
				entry.save()
			return True
		else:
			# Send back for reprocessing
			user.setState(keeper_constants.STATE_NORMAL)
			user.save()
			return False

	return True


def dealWithSuspiciousHour(user, entry, keeperNumber):
	# If we're setting for early morning, send out a warning
	tzAwareDate = entry.remind_timestamp.astimezone(user.getTimezone())
	hourForUser = tzAwareDate.hour
	if (isReminderHourSuspicious(hourForUser) and keeperNumber != constants.SMSKEEPER_TEST_NUM):
		logger.info("User %s: Scheduling an alert for %s am local time, might want to check entry id %s" % (user.id, hourForUser, entry.id))
		return True
	return False


def createReminderEntry(user, nattyResult, msg, sendFollowup, keeperNumber):
	cleanedText = msg_util.cleanedReminder(nattyResult.queryWithoutTiming)  # no "Remind me"
	cleanedText = msg_util.warpReminderText(cleanedText)  # I to your
	entry = Entry.createEntry(user, keeperNumber, keeper_constants.REMIND_LABEL, cleanedText)

	entry.remind_timestamp = nattyResult.utcTime
	entry.remind_last_notified = None

	entry.orig_text = json.dumps([msg])
	entry.save()

	logger.debug("User %s: Created entry %s and msg '%s' with timestamp %s from using nattyResult %s" % (user.id, entry.id, msg, nattyResult.utcTime, nattyResult))

	# Don't do any of this logic in the tutorial state, shouldn't be correct
	if not isTutorial(user):
		handle = msg_util.getReminderHandle(nattyResult.queryWithoutTiming)  # Grab "me" or "mom"

		if handle and handle != "me":
			# If we ever handle multiple handles... we need to create seperate entries to deal with snoozes
			contact = Contact.fetchByHandle(user, handle)

			if contact is None:
				logger.debug("User %s: Didn't find handle %s and msg %s on entry %s" % (user.id, handle, msg, entry.id))
				# We couldn't find the handle so go into unresolved state
				# Set data for ourselves for when we come back
				user.setStateData(keeper_constants.ENTRY_ID_DATA_KEY, entry.id)
				user.setStateData("fromUnresolvedHandles", True)
				user.setState(keeper_constants.STATE_UNRESOLVED_HANDLES, saveCurrent=True)
				user.setStateData(keeper_constants.UNRESOLVED_HANDLES_DATA_KEY, [handle])
				user.save()
				return False
			else:
				logger.debug("User %s: Didn't find handle %s and entry %s...goint to unresolved" % (user.id, handle, entry.id))
				# We found the handle, so share the entry with the user.
				entry.users.add(contact.target)

	suspiciousHour = dealWithSuspiciousHour(user, entry, keeperNumber)

	analytics.logUserEvent(
		user,
		"Created Reminder",
		{
			"Needed Followup": sendFollowup,
			"Was Suspicious Hour": suspiciousHour,
			"In tutorial": isTutorial(user),
			"Is shared": len(entry.users.all()) > 1,
			"interface": keeperNumber,
		}
	)

	return entry


def updateReminderEntry(user, nattyResult, msg, entry, keeperNumber, isSnooze=False):
	newDate = entry.remind_timestamp.astimezone(user.getTimezone())
	nattyTzTime = nattyResult.utcTime.astimezone(user.getTimezone())
	# Only update with a date or time if Natty found one
	if nattyResult.hadDate:
		newDate = newDate.replace(year=nattyTzTime.year)
		newDate = newDate.replace(month=nattyTzTime.month)
		newDate = newDate.replace(day=nattyTzTime.day)

	if nattyResult.hadTime:
		newDate = newDate.replace(hour=nattyTzTime.hour)
		newDate = newDate.replace(minute=nattyTzTime.minute)
		newDate = newDate.replace(second=nattyTzTime.second)

	logger.debug("User %s: Updating entry %s with and msg '%s' with timestamp %s from using nattyResult %s.  Old timestamp was %s" % (user.id, entry.id, msg, newDate, nattyResult, entry.remind_timestamp))
	entry.remind_timestamp = newDate.astimezone(pytz.utc)
	entry.remind_last_notified = None

	if entry.orig_text:
		try:
			origTextList = json.loads(entry.orig_text)
		except ValueError:
			origTextList = [entry.orig_text]
	else:
		origTextList = []
	origTextList.append(msg)
	entry.orig_text = json.dumps(origTextList)
	entry.save()

	suspiciousHour = dealWithSuspiciousHour(user, entry, keeperNumber)

	analytics.logUserEvent(
		user,
		"Updated Reminder",
		{
			"Was Suspicious Hour": suspiciousHour,
			"In tutorial": isTutorial(user),
			"Is shared": len(entry.users.all()) > 1,
			"Type": "Snooze" if isSnooze else "Time Correction"
		}
	)


#  Send off a response like "I'll remind you Sunday at 9am" or "I'll remind mom Sunday at 9am"
def sendCompletionResponse(user, entry, sendFollowup, keeperNumber):
	tzAwareDate = entry.remind_timestamp.astimezone(user.getTimezone())

	# Include time if old product or if its not a default time
	includeTime = (user.product_id == 0 or (user.product_id == 1 and not (tzAwareDate.hour == 9 and tzAwareDate.minute == 0)))

	# Get the text liked "tomorrow" or "Sat at 5pm"
	userMsg = msg_util.naturalize(date_util.now(user.getTimezone()), tzAwareDate, includeTime=includeTime)

	# If this is a shared reminder then look up the handle to send things out with
	if user == entry.creator and len(entry.users.all()) > 1:
		for target in entry.users.all():
			if target.id != user.id:
				contact = Contact.fetchByTarget(user, target)
				handle = contact.handle
	else:
		handle = "you"

	toSend = "%s I'll remind %s %s." % (helper_util.randomAcknowledgement(), handle, userMsg)

	# Tutorial gets a special followup message
	if sendFollowup:
		if isTutorial(user):
			toSend = toSend + " (If that time doesn't work, just tell me what time is better)"
		else:
			toSend = toSend + "\n\n"
			toSend = toSend + "If that time doesn't work, tell me what time is better"

	sms_util.sendMsg(user, toSend, None, keeperNumber)


def isReminderHourSuspicious(hourForUser):
	return hourForUser >= 0 and hourForUser <= 6


def getDefaultTime(user, isToday=False):
	userNow = date_util.now(user.getTimezone())

	if user.product_id == 0 or (user.product_id == 1 and isToday):
		# If before 2 pm, remind at 6 pm
		if userNow.hour < 14:
			replaceTime = userNow.replace(hour=18, minute=0, second=0)
		# If between 2 pm and 5 pm, remind at 9 pm
		elif userNow.hour >= 14 and userNow.hour < 17:
			replaceTime = userNow.replace(hour=21, minute=0, second=0)
		else:
			# If after 5 pm, remind 9 am next day
			replaceTime = userNow + datetime.timedelta(days=1)
			replaceTime = replaceTime.replace(hour=9, minute=0, second=0)
	else:
		# Remind 9 am next day
		replaceTime = userNow + datetime.timedelta(days=1)
		replaceTime = replaceTime.replace(hour=9, minute=0, second=0)
	return replaceTime
