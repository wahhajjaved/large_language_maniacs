import time
import json
import datetime
import os
import pytz
import random
import logging

from django.http import HttpResponse
from django.db.models import Q
from django.contrib.gis.geos import Point, fromstr
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.http import Http404
from django.db import IntegrityError

from peanut.settings import constants

from common.models import Photo, User, SmsAuth, PhotoAction, Strand, NotificationLog, ContactEntry, FriendConnection
from common.serializers import UserSerializer

from common import api_util, cluster_util

from strand import geo_util, notifications_util, friends_util, strands_util
from strand.forms import GetJoinableStrandsForm, GetNewPhotosForm, RegisterAPNSTokenForm, UpdateUserLocationForm, GetFriendsNearbyMessageForm, SendSmsCodeForm, AuthPhoneForm, OnlyUserIdForm, StrandApiForm

from ios_notifications.models import APNService, Device, Notification

logger = logging.getLogger(__name__)

# TODO(Derek): move to a common loc, used in sendStrandNotifications
def cleanName(str):
	return str.split(' ')[0].split("'")[0]

def removeDups(seq, idFunction=None): 
   # order preserving
   if idFunction is None:
	   def idFunction(x): return x
   seen = {}
   result = []
   for item in seq:
	   id = idFunction(item)
	   if id in seen: continue
	   seen[id] = 1
	   result.append(item)
   return result

def getBestLocation(photo):
	if photo.twofishes_data:
		twoFishesData = json.loads(photo.twofishes_data)
		bestLocationName = None
		bestWoeType = 100
		if "interpretations" in twoFishesData:
			for data in twoFishesData["interpretations"]:
				if "woeType" in data["feature"]:
					# https://github.com/foursquare/twofishes/blob/master/interface/src/main/thrift/geocoder.thrift
					if data["feature"]["woeType"] < bestWoeType:
						bestLocationName = data["feature"]["displayName"]
						bestWoeType = data["feature"]["woeType"]
						if bestLocationName:
							return bestLocationName
						else:
							return photo.location_city
	
	return None

def getActionsByPhotoIdCache(photoIds):
	actions = PhotoAction.objects.select_related().filter(photo_id__in=photoIds)
	actionsByPhotoId = dict()

	for action in actions:
		if action.photo_id not in actionsByPhotoId:
			actionsByPhotoId[action.photo_id] = list()
		actionsByPhotoId[action.photo_id].append(action)

	return actionsByPhotoId

def addActionsToClusters(clusters, actionsByPhotoIdCache):
	for cluster in clusters:
		for entry in cluster:
			if entry["photo"].id in actionsByPhotoIdCache:
				entry["actions"] = actionsByPhotoIdCache[entry["photo"].id]

	return clusters

def groupIsSolo(group, userId):
	for photo in group:
		if photo.user_id != userId:
			return False
	return True

"""
	This turns a list of list of photos into groups that contain a title and cluster.

	We do all the photos at once so we can load up the sims cache once

	Returns format of:
	[
		{
			'title': blah
			'clusters': clusters
		},
		{
			'title': blah2
			'clusters': clusters
		},
	]
"""
def getFormattedGroups(groups, userId):
	if len(groups) == 0:
		return []

	output = list()

	photoIds = list()
	for group in groups:
		for photo in group['photos']:
			photoIds.append(photo.id)

	# Fetch all the similarities at once so we can process in memory
	simCaches = cluster_util.getSimCaches(photoIds)

	# Do same with actions
	actionsByPhotoIdCache = getActionsByPhotoIdCache(photoIds)
	
	for group in groups:
		if len(group['photos']) == 0:
			continue
			
		# Grab title from the location_city of a photo...but find the first one that has
		#   a valid location_city
		bestLocation = None
		subtitle = ""
		i = 0
		while (not bestLocation) and i < len(group['photos']):
			bestLocation = getBestLocation(group['photos'][i])
			i += 1

		names = list()
		for photo in group['photos']:
			if photo.user_id != userId:
				names.append(photo.user.display_name)

		names = set(names)


		if (groupIsSolo(group['photos'], userId)):
			title = "Just you"
		else:
			title = ", ".join(names) + " and You"

		if bestLocation:
			subtitle = bestLocation
		else:
			subtitle = "Location Unknown"
			
		clusters = cluster_util.getClustersFromPhotos(group['photos'], constants.DEFAULT_CLUSTER_THRESHOLD, 0, simCaches)

		clusters = addActionsToClusters(clusters, actionsByPhotoIdCache)
		
		output.append({'title': title, 'subtitle': subtitle, 'clusters': clusters, 'id': group['id']})
	return output

"""
	Helper Method for auth_phone

	Strand specific code for creating a user.  If a user already exists, this will
	archive the old one by changing the phone number to an archive format (2352+15555555555)

	This also updates the SmsAuth object to point to this user

	Lastly, this creates the local directory

	TODO(Derek):  If we create users in more places, might want to move this
"""
def createStrandUser(phoneNumber, displayName, phoneId, smsAuth, returnIfExist = False):
	try:
		user = User.objects.get(Q(phone_number=phoneNumber) & Q(product_id=1))
		
		if returnIfExist or phoneNumber in constants.DEV_PHONE_NUMBERS:
			return user
		else:
			# User exists, so need to archive
			# To do that, re-do the phone number, adding in an archive code
			archiveCode = random.randrange(1000, 10000)
			
			user.phone_number = "%s%s" %(archiveCode, phoneNumber)
			user.save()
	except User.DoesNotExist:
		pass

	# TODO(Derek): Make this more interesting when we add auth to the APIs
	authToken = random.randrange(10000, 10000000)

	user = User.objects.create(phone_number = phoneNumber, display_name = displayName, phone_id = phoneId, product_id = 1, auth_token = str(authToken))

	if smsAuth:
		smsAuth.user_created = user
		smsAuth.save()

	logger.info("Created new user %s" % user)

	# Now pre-populate friends who this user was invited by
	invitedBy = ContactEntry.objects.filter(phone_number=phoneNumber).filter(contact_type="invited").exclude(skip=True)
	
	for invite in invitedBy:
		try:
			if user.id < invite.user.id:
				FriendConnection.objects.create(user_1=user, user_2=invite.user)
			else:
				FriendConnection.objects.create(user_1=invite.user, user_2=user)
			logger.debug("Created invite friend entry for user %s with user %s" % (user.id, invite.user.id))
		except IntegrityError:
			logger.warning("Tried to create friend connection between %s and %s but there was one already" % (user.id, invite.user.id))

	# Create directory for photos
	# TODO(Derek): Might want to move to a more common location if more places that we create users
	try:
		userBasePath = user.getUserDataPath()
		os.stat(userBasePath)
	except:
		os.mkdir(userBasePath)
		os.chmod(userBasePath, 0775)

	return user

#####################################################################################
#################################  EXTERNAL METHODS  ################################
#####################################################################################



"""
	Return the Duffy JSON for the strands a user has that are unshared

	This uses the Strand objects instead of neighbors
"""
def unshared_strands(request):
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	nowTime = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
	timeLow = nowTime - datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING)

	if (form.is_valid()):
		userId = int(form.cleaned_data['user_id'])
		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			return HttpResponse(json.dumps({'user_id': 'User not found'}), content_type="application/json", status=400)


		strands = Strand.objects.select_related().filter(users__in=[user]).filter(shared=False)

		# list of list of photos
		groups = list()
		for strand in strands:
			strandId = strand.id			
			photos = strand.photos.all().order_by("-time_taken")
			entry = {'photos': photos, 'id': strandId}

			if len(photos) > 0:
				groups.append(entry)

		if len(groups) > 0:
			# now sort groups by the time_taken of the first photo in each group
			groups = sorted(groups, key=lambda x: x['photos'][0].time_taken, reverse=True)

		formattedGroups = getFormattedGroups(groups, userId)
			
		# Lastly, we turn our groups into sections which is the object we convert to json for the api
		objects = api_util.turnFormattedGroupsIntoSections(formattedGroups, 1000)
		response['objects'] = objects
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")
	
"""
	Return the Duffy JSON for the photo feed.

	This uses the Strand objects instead of neighbors
"""
def strand_feed(request):
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	nowTime = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
	timeLow = nowTime - datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING)

	if (form.is_valid()):
		userId = int(form.cleaned_data['user_id'])
		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			return HttpResponse(json.dumps({'user_id': 'User not found'}), content_type="application/json", status=400)

		friendsData = friends_util.getFriendsData(userId)

		strands = Strand.objects.select_related().filter(users__in=[user]).filter(shared=True)

		# list of list of photos
		groups = list()
		for strand in strands:
			strandId = strand.id
			photos = friends_util.filterStrandPhotosByFriends(userId, friendsData, strand)
			entry = {'photos': photos, 'id': strandId}

			if len(photos) > 0:
				groups.append(entry)

		if len(groups) > 0:
			# now sort groups by the time_taken of the first photo in each group
			groups = sorted(groups, key=lambda x: x['photos'][0].time_taken, reverse=True)

		# Lastly, grab all our locked strands and add in those photos
		lockedGroup = list()
		if user.last_location_point:
			strands = Strand.objects.select_related().filter(last_photo_time__gt=timeLow)
			lockedGroup = strands_util.getJoinableStrandPhotos(userId, user.last_location_point.x, user.last_location_point.y, strands, friendsData)
			# TODO: get a real id for locked group
			entry = {'photos': lockedGroup, 'id': 0}

			if len(lockedGroup) > 0:
				groups.insert(0, entry)

		# Now we have to turn into our Duffy JSON, first, convert into the right format
		formattedGroups = getFormattedGroups(groups, userId)

		if len(lockedGroup) > 0:
			formattedGroups[0]['title'] = "Locked"
			
		# Lastly, we turn our groups into sections which is the object we convert to json for the api
		objects = api_util.turnFormattedGroupsIntoSections(formattedGroups, 1000)
		response['objects'] = objects
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")


"""
	the user would join if they took a picture at the given startTime (defaults to now)

	Searches for all photos of their friends within the time range and geo range but that don't have a
	  neighbor entry

	Used by the web view and the mobile client call

	returns (lastDate, objects) which should be handed back in the response as response['objects']
"""
def get_joinable_strands(request):
	response = dict({'result': True})

	nowTime = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
	timeLow = nowTime - datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING)

	form = GetJoinableStrandsForm(api_util.getRequestData(request)) 
	if form.is_valid():
		userId = form.cleaned_data['user_id']
		lon = form.cleaned_data['lon']
		lat = form.cleaned_data['lat']

		friendsData = friends_util.getFriendsData(userId)
		strands = Strand.objects.select_related().filter(last_photo_time__gt=timeLow)

		joinableStrandPhotos = strands_util.getJoinableStrandPhotos(userId, lon, lat, strands, friendsData)

		formattedGroups = getFormattedGroups([{'photos': joinableStrandPhotos, 'id': 0}], userId)
		objects = api_util.turnFormattedGroupsIntoSections(formattedGroups, 1000)
		response['objects'] = objects

		return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

"""
	Returns back any new photos in the user's strands after the given date and time
"""
def get_new_photos(request):
	response = dict({'result': True})

	form = GetNewPhotosForm(api_util.getRequestData(request))
	if form.is_valid():
		userId = form.cleaned_data['user_id']
		startTime = form.cleaned_data['start_date_time']
		photoList = list()

		strands = Strand.objects.filter(last_photo_time__gt=startTime).filter(shared=True)
		
		for strand in strands:
			for photo in strand.photos.filter(time_taken__gt=startTime):
				if photo.user_id != userId:
					photoList.append(photo)

		photoList = removeDups(photoList, lambda x: x.id)

		formattedGroups = getFormattedGroups([{'photos':photoList, 'id': 0}], userId)
		objects = api_util.turnFormattedGroupsIntoSections(formattedGroups, 1000)
		response['objects'] = objects

		return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

"""
	Registers a user's current location (and only stores the last location)
"""
def update_user_location(request):
	response = dict({'result': True})
	form = UpdateUserLocationForm(api_util.getRequestData(request))

	if (form.is_valid()):
		userId = form.cleaned_data['user_id']
		lon = form.cleaned_data['lon']
		lat = form.cleaned_data['lat']
		timestamp = form.cleaned_data['timestamp']
		accuracy = form.cleaned_data['accuracy']
		last_photo_timestamp = form.cleaned_data['last_photo_timestamp']
		
		now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			logger.error("Could not find user: %s " % (userId))
			response['user_id'] = 'userId not found'
			return HttpResponse(json.dumps(response), content_type="application/json", status=400)

		if ((not lon == 0) or (not lat == 0)):
			if ((user.last_location_timestamp and timestamp and timestamp > user.last_location_timestamp) or not user.last_location_timestamp):
				user.last_location_point = fromstr("POINT(%s %s)" % (lon, lat))

				if timestamp:
					user.last_location_timestamp = timestamp
				else:
					user.last_location_timestamp = now

				user.last_location_accuracy = accuracy

				if last_photo_timestamp:
					user.last_photo_timestamp = last_photo_timestamp
					logger.info("Last Photo: %s, %s" % (user.id, last_photo_timestamp))
				
				# We're saving last build info here since we are already writing to the user row in the database
				if form.cleaned_data['build_id'] and form.cleaned_data['build_number']:
					# if last_build_info is empty or if either build_id or build_number is not in last_build_info
					#    update last_build_info
					if ((not user.last_build_info) or 
						form.cleaned_data['build_id'] not in user.last_build_info or 
						str(form.cleaned_data['build_number']) not in user.last_build_info):
						user.last_build_info = "%s-%s" % (form.cleaned_data['build_id'], form.cleaned_data['build_number'])
						logger.info("Build info updated to %s" % (user.last_build_info))
			
				user.save()
				logger.info("Location updated for user %s. %s: %s, %s, %s" % (userId, datetime.datetime.utcnow().replace(tzinfo=pytz.utc), userId, user.last_location_point, accuracy))
			else:
				logger.info("Location NOT updated for user %s. Old Timestamp. %s: %s, %s" % (userId, timestamp, userId, str((lon, lat))))
		else:
			logger.info("Location NOT updated for user %s. Lat/Lon Zero. %s: %s, %s" % (userId, datetime.datetime.utcnow().replace(tzinfo=pytz.utc), userId, str((lon, lat))))

	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response), content_type="application/json")


"""
	Receives device tokens for APNS notifications
"""
def register_apns_token(request):
	response = dict({'result': True})
	form = RegisterAPNSTokenForm(api_util.getRequestData(request))

	if (form.is_valid()):
		userId = form.cleaned_data['user_id']
		deviceToken = form.cleaned_data['device_token'].replace(' ', '').replace('<', '').replace('>', '')

		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			logger.error("Could not find user: %s " % (userId))
			return HttpResponse(json.dumps(response), content_type="application/json")

		# TODO (Aseem): Make this more efficient. Assume nothing!
		user.device_token = deviceToken
		apnsDev = APNService.objects.get(id=constants.IOS_NOTIFICATIONS_DEV_APNS_ID)
		apnsProd = APNService.objects.get(id=constants.IOS_NOTIFICATIONS_PROD_APNS_ID)
		apnsDerekDev = APNService.objects.get(id=constants.IOS_NOTIFICATIONS_DEREK_DEV_APNS_ID)
		apnsEnterpriseProd = APNService.objects.get(id=constants.IOS_NOTIFICATIONS_ENTERPRISE_PROD_APNS_ID)
		apnsEnterpriseDev = APNService.objects.get(id=constants.IOS_NOTIFICATIONS_ENTERPRISE_DEV_APNS_ID)

		devices = Device.objects.filter(token=deviceToken)

		if (len(devices) == 0):
			Device.objects.create(token=deviceToken, is_active=True, service=apnsDev)
			Device.objects.create(token=deviceToken, is_active=True, service=apnsDerekDev)
			Device.objects.create(token=deviceToken, is_active=True, service=apnsProd)
			Device.objects.create(token=deviceToken, is_active=True, service=apnsEnterpriseProd)			
			Device.objects.create(token=deviceToken, is_active=True, service=apnsEnterpriseDev)
		else:
			for device in devices:
				if (not(device.token == deviceToken)):
					device.token = deviceToken
				if (not device.is_active):
					device.is_active = True
				device.save()

		user.save()
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	
	return HttpResponse(json.dumps(response), content_type="application/json")

"""
	Returns a string that describes who is around.
	If people are around but haven't taken a photo, returns:  "5 friends are near you"
	If people are around and someone has taken a photo, returns:  "Henry & 4 other friends are near you"
	If more than one person is nearby, returns:  "Henry & Aseem & 1 other friend are near you"
"""
def get_nearby_friends_message(request):
	response = dict({'result': True})
	form = GetFriendsNearbyMessageForm(api_util.getRequestData(request))

	timeWithinHours = 3
	
	if (form.is_valid()):
		userId = form.cleaned_data['user_id']
		lat = form.cleaned_data['lat']
		lon = form.cleaned_data['lon']

		now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
		timeWithin = now - datetime.timedelta(hours=timeWithinHours)

		friendsData = friends_util.getFriendsData(userId)
		
		# For now, search through all Users, when we have more, do something more efficent
		users = User.objects.exclude(id=userId).exclude(last_location_point=None).filter(product_id=1).filter(last_location_timestamp__gt=timeWithin)
		users = friends_util.filterUsersByFriends(userId, friendsData, users)

		nearbyUsers = geo_util.getNearbyUsers(lon, lat, users, filterUserId=userId)

		photos = Photo.objects.filter(user_id__in=User.getIds(nearbyUsers)).filter(time_taken__gt=timeWithin)
		
		nearbyPhotosData = geo_util.getNearbyPhotos(now, lon, lat, photos, filterUserId=userId)

		photoUsers = list()
		nonPhotoUsers = nearbyUsers
		
		for user in users:
			hasPhoto = False
			for nearbyPhotoData in nearbyPhotosData:
				photo, timeDistance, geoDistance = nearbyPhotoData
				if photo.user_id == user.id:
					hasPhoto = True

			if hasPhoto:
				photoUsers.append(user)

				# Remove this user from the nonPhotos list since we've found a photo
				nonPhotoUsers = filter(lambda a: a.id != user.id, nonPhotoUsers)

		if len(photoUsers) == 0 and len(nonPhotoUsers) == 0:
			message = ""
			expMessage = "No friends are near you."
		elif len(photoUsers) == 0:
			if len(nonPhotoUsers) == 1:
				message = "1 friend will see this photo"
				expMessage = "1 friend near you hasn't taken a photo yet. Take a photo to share with them."
			else:
				message = "%s friends will see this photo" % (len(nonPhotoUsers))
				expMessage = "%s friends near you haven't taken a photo yet. Take a photo to share with them." % (len(nearbyUsers))
		elif len(photoUsers) > 0:
			names = list()
			for user in photoUsers:
				names.append(cleanName(user.display_name))
		
			if len(nonPhotoUsers) == 0:
				if len(names) <= 2:
					message = " & ".join(names)
				else:
					numNames = len(names)
					message = ", ".join(names[:numNames-2])
					message += " & %s" % (names[numNames-1])
				expMessage = message + " took a photo near you."
			else:
				message = ", ".join(names)
				expMessage = message + " took a photo near you."

				if len(nonPhotoUsers) == 1:
					message += " & 1 friend"
					expMessage += " 1 other friend near you hasn't taken a photo yet."
				else:
					message += " & %s friends" % len(nonPhotoUsers)
					expMessage += " %s other friends near you haven't taken a photo yet." % len (nonPhotoUsers)

			message += " will see this photo"

		response['message'] = message
		response['expanded_message'] = expMessage
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	
	return HttpResponse(json.dumps(response), content_type="application/json")

"""
	Sends a notification to the device based on the user_id
"""

def send_notifications_test(request):
	response = dict({'result': True})
	data = api_util.getRequestData(request)

	msg = None
	customPayload = dict()

	if data.has_key('user_id'):
		userId = data['user_id']
		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			return api_util.returnFailure(response, "user_id not found")
	else:
		return api_util.returnFailure(response, "Need user_id")

	if data.has_key('msg'):
		msg = str(data['msg'])

	if data.has_key('msgTypeId'):
		msgTypeId = int(data['msgTypeId'])
	else:
		return api_util.returnFailure(response, "Need msgTypeId")

	if data.has_key('pid'):
		customPayload['pid'] = int(data['pid'])

	notifications_util.sendNotification(user, msg, msgTypeId, customPayload)

	return HttpResponse(json.dumps(response), content_type="application/json")

"""
	Sends a test text message to a phone number
"""

def send_sms_test(request):
	response = dict({'result': True})
	data = api_util.getRequestData(request)

	if data.has_key('phone'):
		phone = data['phone']
	else:
		phone = '6505759014'

	if data.has_key('body'):
		bodytext = data['body']
	else:
		bodytext = "Test msg from Strand/send_sms_test"
	
	notifications_util.sendSMS(phone, bodytext)
	return HttpResponse(json.dumps(response), content_type="application/json")

"""
	Sends SMS code to the given phone number.

	Right now theres no SPAM protection for numbers.  Can be added by looking at the last time
	a code was sent to a number
"""
def send_sms_code(request):
	response = dict({'result': True})

	form = SendSmsCodeForm(api_util.getRequestData(request))
	if (form.is_valid()):
		phoneNumber = str(form.cleaned_data['phone_number'])

		if "555555" not in phoneNumber:
			accessCode = random.randrange(1000, 10000)

			msg = "Your Strand code is:  %s" % (accessCode)
	
			notifications_util.sendSMS(phoneNumber, msg)
			SmsAuth.objects.create(phone_number = phoneNumber, access_code = accessCode)
		else:
			response['debug'] = "Skipped"
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	
	return HttpResponse(json.dumps(response), content_type="application/json")

"""
	Call to authorize a phone with an sms code.  The SMS code should have been sent with send_sms_code
	above already.

	This then takes in the display_name and creates a user account
"""
@csrf_exempt
def auth_phone(request):
	response = dict({'result': True})
	form = AuthPhoneForm(api_util.getRequestData(request))

	timeWithinMinutes = 10

	if (form.is_valid()):
		phoneNumber = str(form.cleaned_data['phone_number'])
		accessCode = form.cleaned_data['sms_access_code']
		displayName = form.cleaned_data['display_name']
		phoneId = form.cleaned_data['phone_id']

		if "555555" not in phoneNumber:
			timeWithin = datetime.datetime.utcnow().replace(tzinfo=pytz.utc) - datetime.timedelta(minutes=timeWithinMinutes)

			smsAuth = SmsAuth.objects.filter(phone_number=phoneNumber, access_code=accessCode)

			if len(smsAuth) == 0 or len(smsAuth) > 1:
				return HttpResponse(json.dumps({'access_code': 'Invalid code'}), content_type="application/json", status=400)
			elif smsAuth[0].user_created:
				return HttpResponse(json.dumps({'access_code': 'Code already used'}), content_type="application/json", status=400)
			elif smsAuth[0].added < timeWithin:
				return HttpResponse(json.dumps({'access_code': 'Code expired'}), content_type="application/json", status=400)
			else:
				# TODO(Derek):  End of August, change returnIfExists to False, so we start archiving again
				user = createStrandUser(phoneNumber, displayName, phoneId, smsAuth[0], returnIfExist = True)
				serializer = UserSerializer(user)
				response['user'] = serializer.data
		else:
			if accessCode == 2345:
				user = createStrandUser(phoneNumber, displayName, phoneId, None, returnIfExist = True)
				serializer = UserSerializer(user)
				response['user'] = serializer.data
			else:
				return HttpResponse(json.dumps({'access_code': 'Invalid code'}), content_type="application/json", status=400)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

def get_invite_message(request):
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		userId = int(form.cleaned_data['user_id'])
		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			return HttpResponse(json.dumps({'user_id': 'User not found'}), content_type="application/json", status=400)	
		if ('enterprise' in form.cleaned_data['build_id'].lower()):
			inviteLink = constants.INVITE_LINK_ENTERPRISE
		else:
			inviteLink = constants.INVITE_LINK_APP_STORE

		response['invite_message'] = "Try this app so we can share photos when we hang out: "  + inviteLink + "."
		response['invites_remaining'] = user.invites_remaining
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

def get_notifications(request):
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		userId = form.cleaned_data['user_id']
		response['notifications'] = list()

		photoActions = PhotoAction.objects.filter(photo__user_id=userId).order_by("-added")[:20]

		for photoAction in photoActions:
			if photoAction.user_id != userId:
				metadataMsg = 'liked your photo'
				metadata = {'photo_id': photoAction.photo_id,
							'action_text': metadataMsg,
							'actor_user': photoAction.user_id,
							'actor_display_name':  photoAction.user.display_name,
							'photo_thumb_path': photoAction.photo.getThumbUrlImagePath(),
							'time': photoAction.added}
				response['notifications'].append(metadata)
		
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")


