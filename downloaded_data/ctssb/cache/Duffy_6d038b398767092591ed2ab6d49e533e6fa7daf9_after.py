#!/usr/bin/python
import sys, os
import time, datetime
import logging
from threading import Thread

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from django.db.models import Count
from django.db import IntegrityError

from common.models import User, ContactEntry, FriendConnection
from arbus import similarity_util

from strand import notifications_util

"""
	Returns a dictionary keyed by phone number and value is user
"""
def getUsersByPhoneNumber(users):
	usersByPhoneNumber = dict()

	for user in users:
		usersByPhoneNumber[str(user.phone_number)] = user

	return usersByPhoneNumber

"""
	Returns a dictionary of dictionaires, first keyed by user, second by phone number
	If the entry exists, then that user has that phone number in their contacts
"""
def getContactsByUser(contactEntries):
	contactsByUser = dict()

	for contactEntry in contactEntries:
		if contactEntry.user not in contactsByUser:
			contactsByUser[contactEntry.user] = dict()
			
		try:
			contactsByUser[contactEntry.user][str(contactEntry.phone_number)] = True
		except UnicodeEncodeError:
			logging.error("Unicode Encode Error for contact entry %s" % contactEntry.id)
			contactEntry.skip = True
			contactEntry.save()


	return contactsByUser



def threadedSendNotifications(userIds):
	logging.basicConfig(filename='/var/log/duffy/friends.log',
						level=logging.DEBUG,
						format='%(asctime)s %(levelname)s %(message)s')
	logging.getLogger('django.db.backends').setLevel(logging.ERROR)
	logger = logging.getLogger(__name__)

	users = User.objects.filter(id__in=userIds)

	# Send update feed msg to folks who are involved in these photos
	notifications_util.sendRefreshFeedToUsers(users)
	
"""
	Populate the Friends table.  This creates a link between two users
	Loop through all unprocessed ContactEntries and for each one, see if there is a phone number
	in our db for the ContactEntry.  If so, and the other user has the current user's number, add a 
	Friend entry

"""
def main(argv):
	logger = logging.getLogger(__name__)
	
	logger.info("Starting... ")
	while True:
		contactEntries = ContactEntry.objects.select_related().filter(evaluated=False).filter(skip=False).filter(user_id__gt=600)[:1000]
		newConnectionCount = 0

		if len(contactEntries) > 0:
			# Grab users who these new contact entries point to
			phoneNumbers = [contactEntry.phone_number for contactEntry in contactEntries]
			users = User.objects.filter(phone_number__in=phoneNumbers).filter(product_id=2)

			usersByPhoneNumber = getUsersByPhoneNumber(users)

			for contactEntry in contactEntries:
				contactEntry.evaluated = True
				
				# If we have a user associated with a given phone number
				if contactEntry.phone_number in usersByPhoneNumber:
					forwardFriend = usersByPhoneNumber[contactEntry.phone_number]
					try:
						if contactEntry.user.id == forwardFriend.id:
							continue
						else:
							if FriendConnection.addForwardConnection(contactEntry.user, forwardFriend):
								newConnectionCount += 1
							if contactEntry.contact_type and 'invited' in contactEntry.contact_type:
								if FriendConnection.addReverseConnection(contactEntry.user, forwardFriend):
									newConnectionCount +=1
								
					except IntegrityError:
						logger.warning("Tried to create friend connection between %s and %s but there was one already" % (contactEntry.user.id, friend.id))

			logger.info("Wrote out %s friend entries after evaluating %s contact entries" % (newConnectionCount, len(contactEntries)))
			ContactEntry.bulkUpdate(contactEntries, ["evaluated"])

			usersIdsToUpdate = [contactEntry.user_id for contactEntry in contactEntries]
			usersIdsToUpdate = set(usersIdsToUpdate)

			Thread(target=threadedSendNotifications, args=(usersIdsToUpdate,)).start()
		else:
			time.sleep(1)
		


if __name__ == "__main__":
	logging.basicConfig(filename='/var/log/duffy/friends.log',
						level=logging.DEBUG,
						format='%(asctime)s %(levelname)s %(message)s')
	logging.getLogger('django.db.backends').setLevel(logging.ERROR) 
	main(sys.argv[1:])