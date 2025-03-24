from __future__ import absolute_import
import sys
import os
import datetime
import pytz

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from django.conf import settings

from smskeeper.models import Entry
from smskeeper.models import User
from smskeeper import sms_util
from smskeeper import tips

from peanut.celery import app

from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)


@app.task
def processReminder(entryId):
	logger.debug("Starting reminder process for entry %s" % (entryId))
	entry = Entry.objects.get(id=entryId)
	now = datetime.datetime.now(pytz.utc)

	# See if this entry is valid for reminder
	# It needs to not be hidden
	# As well as the remind_timestamp be within a few seconds of now
	if not entry.hidden and abs((now - entry.remind_timestamp).total_seconds()) < 10:
		msg = "Hi! Friendly reminder: %s" % entry.text

		for user in entry.users.all():
			sms_util.sendMsg(user, msg, None, entry.keeper_number)

		entry.hidden = True
		entry.save()


@app.task
def processAllReminders():
	entries = Entry.objects.filter(remind_timestamp__isnull=False, hidden=False)

	now = datetime.datetime.now(pytz.utc)
	for entry in entries:
		if entry.remind_timestamp < now and entry.remind_timestamp > now - datetime.timedelta(minute=5):
			processReminder(entry.id)


TIP_FREQUENCY_SECS = 60 * 60 * 71  # 71 hours in seconds


def shouldSendUserTip(user):
	if not user.completed_tutorial:
		return False
	if user.disable_tips:
		return False
	if not user.last_tip_sent:
		return True
	else:
		# must use datetime.datetime.now and not utcnow as the test mocks datetime.now
		dt = datetime.datetime.now(pytz.utc) - user.last_tip_sent
		if dt.total_seconds() > TIP_FREQUENCY_SECS:
			return True
	return False


@app.task
def sendTips(keeperNumber=None):
	if not keeperNumber:
		keeperNumber = settings.KEEPER_NUMBER

	users = User.objects.all()
	for user in users:
		if shouldSendUserTip(user):
			sentTips = list()
			if user.sent_tips:
				sentTips = user.sent_tips.split(",")
			for tip in tips.SMSKEEPER_TIPS:
				if tip["identifier"] not in sentTips:
					sms_util.sendMsg(user, tips.renderTip(tip, user.name), None, keeperNumber)
					sentTips.append(tip["identifier"])
					user.sent_tips = ",".join(sentTips)
					user.last_tip_sent = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
					user.save()
					break


def str_now_1():
	return str(datetime.now())
