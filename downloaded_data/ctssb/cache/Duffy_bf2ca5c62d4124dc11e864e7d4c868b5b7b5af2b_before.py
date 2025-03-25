#!/usr/bin/python
import sys, os
import time, datetime
import pytz
import logging

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from django.db.models import Count
from django.db.models import Q

from peanut.settings import constants
from common.models import Action, Photo, NotificationLog, User, ShareInstance

from strand import notifications_util, friends_util

logger = logging.getLogger(__name__)

def listToPhrases(siList):
	photoCount = len(siList)

	photoPhrase = ""
	if (photoCount == 1):
		photoPhrase = "a photo"
	elif (photoCount > 1):
		photoPhrase = "%s photos" % (photoCount)

	userNames = set()

	for si in siList:
		userNames.add(si.user.display_name.split(' ', 1)[0])

	userNames = list(userNames)
	if len(userNames) == 0:
		userPhrase = ''
	if len(userNames) == 1:
		userPhrase = 'from ' + userNames[0]
	elif len(userNames) == 2:
		userPhrase = "from " + userNames[0] + " and " + userNames[1]
	elif len(userNames) > 2:
		userPhrase = "from " + ', '.join(userNames[:-1]) + ', and ' + userNames[-1]

	return photoPhrase, userPhrase

def sendUnactivatedAccountFS():

	now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
	gracePeriodTimedeltaDays = datetime.timedelta(days=constants.NOTIFICATIONS_ACTIVATE_ACCOUNT_FS_GRACE_PERIOD_DAYS)
	intervalTimedeltaDays = datetime.timedelta(days=constants.NOTIFICATIONS_ACTIVATE_ACCOUNT_FS_INTERVAL_DAYS)

	# generate a list of non-authed users
	nonAuthedUsers = list(User.objects.filter(product_id=2).filter(has_sms_authed=False).filter(added__lt=now-gracePeriodTimedeltaDays).filter(added_gt=now-intervalTimedeltaDays))
	
	logger.info("Non-authed users: %s"% nonAuthedUsers)

	# generate a list of pinged users (as a dict - because of distinct() clause) in the interval for this notification
	recentlyPingedUsers = NotificationLog.objects.filter(added__gt=now-intervalTimedeltaDays).filter(msg_type=constants.NOTIFICATIONS_ACTIVATE_ACCOUNT_FS).filter(user__in=nonAuthedUsers).values('user').distinct()

	logger.info("recentlyPingedUsers %s"% recentlyPingedUsers)

	recentUserIds = [entry['user'] for entry in recentlyPingedUsers]
	
	# remove those users
	usersToNotify = [user for user in nonAuthedUsers if not (user.id in recentUserIds)]

	logger.info("usersToNotify %s"% usersToNotify)

	# remove those users who don't have any photos to see in the app
	shareInstances = ShareInstance.objects.filter(users__in=usersToNotify)

	usersWithPhotos = set()
	shareInstancesByUserId = dict()

	for si in shareInstances:
		for user in si.users.all():
			if user in usersToNotify:
				usersWithPhotos.add(user)
				if user.id in shareInstancesByUserId:
					shareInstancesByUserId[user.id].append(si)
				else:
					shareInstancesByUserId[user.id] = [si]

	logger.info("usersWithPhotos %s" % usersWithPhotos)

	msgCount = 0
	for user in list(usersWithPhotos):
		# generate msg
		photoPhrase, userPhrase = listToPhrases(shareInstancesByUserId[user.id])
		msg = "You have " + photoPhrase + " " + userPhrase + " waiting for you in Swap"
		msgCount += 1

		# send msg
		logger.debug("going to send '%s' to user id %s" % (msg, user.id))
		customPayload = {}
		notifications_util.sendNotification(user, msg, constants.NOTIFICATIONS_ACTIVATE_ACCOUNT_FS, customPayload)

	return msgCount

# TODO: Finish when inbox_feed is refactored
def sendUnseenPhotosFS():
	return 0


def main(argv):
	logger.info("Starting Periodic Notification Script... ")

	msgCount = sendUnactivatedAccountFS()
	logger.info('Sent %s msgs for Unactivated Accounts'%(msgCount))

	msgCount = sendUnseenPhotosFS()
	logger.info('Sent %s msgs for Unseen photos'%(msgCount))

	logger.info('Finished Periodic Notification script')		
if __name__ == "__main__":
	logging.basicConfig(filename='/var/log/duffy/periodic-notifications.log',
						level=logging.DEBUG,
						format='%(asctime)s %(levelname)s %(message)s')
	logging.getLogger('django.db.backends').setLevel(logging.ERROR) 
	main(sys.argv[1:])