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
from django.db import IntegrityError, connection

from peanut.settings import constants

from common.models import Photo, User, SmsAuth, Strand, NotificationLog, ContactEntry, FriendConnection, StrandNeighbor, Action, LocationRecord, ShareInstance
from common.serializers import UserSerializer

from common import api_util, serializers, stats_util

from strand import geo_util, notifications_util, friends_util, strands_util, users_util, swaps_util
from strand.forms import UserIdAndStrandIdForm, RegisterAPNSTokenForm, UpdateUserLocationForm, SendSmsCodeForm, AuthPhoneForm, OnlyUserIdForm

from ios_notifications.models import APNService, Device, Notification


logger = logging.getLogger(__name__)

def uniqueObjects(seq, idfun=None): 
   # order preserving
   if idfun is None:
	   def idfun(x): return x.id
   seen = {}
   result = []
   for item in seq:
	   marker = idfun(item)
	   # in old Python versions:
	   # if seen.has_key(marker)
	   # but in new ones:
	   if marker in seen: continue
	   seen[marker] = 1
	   result.append(item)
   return result



def getFriendsObjectData(userId, users, includePhone = True):
	if not isinstance(users, list) and not isinstance(users, set):
		users = [users]

	friendList = friends_util.getFriendsIds(userId)

	userData = list()
	for user in users:
		if user.id in friendList:
			relationship = constants.FEED_OBJECT_TYPE_RELATIONSHIP_FRIEND
		else:
			relationship = constants.FEED_OBJECT_TYPE_RELATIONSHIP_USER
		
		entry = {'display_name': user.display_name, 'id': user.id, constants.FEED_OBJECT_TYPE_RELATIONSHIP: relationship}

		if includePhone:
			entry['phone_number'] = user.phone_number

		userData.append(entry)

	return userData



def getBuildNumForUser(user):
	if user.last_build_info:
		return int(user.last_build_info.split('-')[1])
	else:
		return 4000


# Need to create a key that is sortable, consistant (to deal with partial updates) and handles
# many photos shared at once
def getSortRanking(user, shareInstance, actions):
	lastTimestamp = shareInstance.shared_at_timestamp
	
	a = (long(lastTimestamp.strftime('%s')) % 1000000000) * 10000000
	b = long(shareInstance.photo.time_taken.strftime('%s')) % 10000000

	return -1 * (a + b)


#####################################################################################
#################################  EXTERNAL METHODS  ################################
#####################################################################################


# ----------------------- FEED ENDPOINTS --------------------

"""
	Return the Duffy JSON for the strands a user has that are private and unshared
"""
def private_strands(request):
	stats_util.startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']

		objs = swaps_util.getFeedObjectsForPrivateStrands(user)
		
		stats_util.printStats("private-end")
		response['objects'] = objs
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

"""
	Returns back the suggested shares
"""
def swaps(request):
	stats_util.startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']

		objs = swaps_util.getFeedObjectsForSwaps(user)
		
		stats_util.printStats("swaps-end")
		response['objects'] = objs
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")


def swap_inbox(request):
	stats_util.startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		num = form.cleaned_data['num']

		# Add in buffer for the last timestamp, or if not sent in, use long ago date
		if form.cleaned_data['last_timestamp']:
			lastTimestamp = form.cleaned_data['last_timestamp'] - datetime.timedelta(seconds=10)
		else:
			lastTimestamp = datetime.datetime.fromtimestamp(0)

		responseObjects = list()

		# Grab all share instances we want.  Might filter by a last timestamp for speed
		shareInstances = ShareInstance.objects.prefetch_related('photo', 'users', 'photo__user').filter(users__in=[user.id]).filter(updated__gt=lastTimestamp).order_by("-updated", "id")
		if num:
			shareInstances = shareInstances[:num]

		# The above search won't find photos that this user has evaluated if the last_action_timestamp
		# is before the given lastTimestamp
		# So in that case, lets search for all the actions since that timestamp and add those
		# ShareInstances into the mix to be sorted
		recentlyEvaluatedActions = Action.objects.prefetch_related('share_instance', 'share_instance__photo', 'share_instance__users', 'share_instance__photo__user').filter(user=user).filter(updated__gt=lastTimestamp).filter(action_type=constants.ACTION_TYPE_PHOTO_EVALUATED).order_by('-added')
		if num:
			recentlyEvaluatedActions = recentlyEvaluatedActions[:num]
			
		shareInstanceIds = ShareInstance.getIds(shareInstances)
		shareInstances = list(shareInstances)
		for action in recentlyEvaluatedActions:
			if action.share_instance_id and action.share_instance_id not in shareInstanceIds:
				shareInstances.append(action.share_instance)
			
		# Now filter out anything that doesn't have a thumb...unless its your own photo
		filteredShareInstances = list()
		for shareInstance in shareInstances:
			if shareInstance.user_id == user.id:
				filteredShareInstances.append(shareInstance)
			elif shareInstance.photo.thumb_filename:
				filteredShareInstances.append(shareInstance)
		shareInstances = filteredShareInstances
		
		# Now grab all the actions for these ShareInstances (comments, evals, likes)
		shareInstanceIds = ShareInstance.getIds(shareInstances)
		stats_util.printStats("swaps_inbox-1")

		actions = Action.objects.filter(share_instance_id__in=shareInstanceIds)
		actionsByShareInstanceId = dict()
		
		for action in actions:
			if action.share_instance_id not in actionsByShareInstanceId:
				actionsByShareInstanceId[action.share_instance_id] = list()
			actionsByShareInstanceId[action.share_instance_id].append(action)

		stats_util.printStats("swaps_inbox-2")

		# Loop through all the share instances and create the feed data
		for shareInstance in shareInstances:
			actions = list()
			if shareInstance.id in actionsByShareInstanceId:
				actions = actionsByShareInstanceId[shareInstance.id]

			actions = uniqueObjects(actions)
			objectData = serializers.objectDataForShareInstance(shareInstance, actions, user)

			# suggestion_rank here for backwards compatibility, remove upon next mandatory updatae after Jan 2
			objectData['sort_rank'] = getSortRanking(user, shareInstance, actions)
			objectData['suggestion_rank'] = objectData['sort_rank']
			responseObjects.append(objectData)

		responseObjects = sorted(responseObjects, key=lambda x: x['sort_rank'])
		
		count = 0
		for responseObject in responseObjects:
			responseObject["debug_rank"] = count
			count += 1

		stats_util.printStats("swaps_inbox-3")

		# Add in the list of all friends at the end
		peopleIds = friends_util.getFriendsIds(user.id)

		# Also add in all of the actors they're dealing with
		for obj in responseObjects:
			peopleIds.extend(obj['actor_ids'])

		people = set(User.objects.filter(id__in=peopleIds))

		peopleEntry = {'type': constants.FEED_OBJECT_TYPE_FRIENDS_LIST, 'share_instance': -1, 'people': getFriendsObjectData(user.id, people, True)}		
		responseObjects.append(peopleEntry)

		stats_util.printStats("swaps_inbox-end")

		response["objects"] = responseObjects
		response["timestamp"] = datetime.datetime.now()
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

def compressGroup(lastActionData, count):
	if count == 1:
		lastActionData['text'] = "sent 1 photo"
	else:
		lastActionData['text'] = "sent %s photos" % count

	# Also update the ID to be unique.  Multiple existing id by count to make unique
	lastActionData['id'] = count * lastActionData['id']

	return lastActionData

def compressActions(actionsData):
	# We want to group together all the photos shared around the same time
	lastActionData = None
	count = 1
	doingCompress = False
	compressedActionsData = list()

	for actionData in actionsData:
		if actionData['action_type'] == constants.ACTION_TYPE_SHARED_PHOTOS:
			if not doingCompress:
				doingCompress = True
				count = 1

			if not lastActionData:
				lastActionData = actionData
			else:
				if (lastActionData['action_type'] == constants.ACTION_TYPE_SHARED_PHOTOS and
					actionData['action_type'] == constants.ACTION_TYPE_SHARED_PHOTOS and
					lastActionData['user'] == actionData['user'] and 
					abs((lastActionData['time_stamp'] - actionData['time_stamp']).total_seconds()) < constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING * 60):
					count += 1
					lastActionData = actionData
				else:
					compressedActionsData.append(compressGroup(lastActionData, count))

					count = 1
					lastActionData = None
		else:
			if doingCompress:
				compressedActionsData.append(compressGroup(lastActionData, count))
				doingCompress = False
				lastActionData = None
			compressedActionsData.append(actionData)

	if doingCompress:
		compressedActionsData.append(compressGroup(lastActionData, count))

	return compressedActionsData
	
def actions_list(request):
	stats_util.startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		responseObjects = list()
		actionsData = list()

		# Do favorites and comments
		actions = Action.objects.prefetch_related('user', 'share_instance').exclude(user=user).filter(Q(action_type=constants.ACTION_TYPE_FAVORITE) | Q(action_type=constants.ACTION_TYPE_COMMENT)).filter(share_instance__users__in=[user.id]).order_by("-added")[:50]
		for action in actions:
			actionData = serializers.actionDataOfActionApiSerializer(user, action)
			if actionData:
				actionsData.append(actionData)

		# Do shares to this user
		shareInstances = ShareInstance.objects.filter(users__in=[user.id]).order_by("-added", "-id")[:100]
		for shareInstance in shareInstances:
			actionData = serializers.actionDataOfShareInstanceApiSerializer(user, shareInstance)

			if actionData:
				actionsData.append(actionData)

		actionsData = sorted(actionsData, key=lambda x: x['time_stamp'], reverse=True)

		actionsData = compressActions(actionsData)[:50]

		response['objects'] = [{'type': 'actions_list', 'actions': actionsData}]
		stats_util.printStats("actions-end")

		user.save()
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

#   -------------------------  OTHER ENDPOINTS ---------------------



"""
	Registers a user's current location (and only stores the last location)
"""
def update_user_location(request):
	response = dict({'result': True})
	form = UpdateUserLocationForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		lon = form.cleaned_data['lon']
		lat = form.cleaned_data['lat']
		timestamp = form.cleaned_data['timestamp']
		accuracy = form.cleaned_data['accuracy']
		
		now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
		
		if ((not lon == 0) or (not lat == 0)):
			record = LocationRecord(user = user, point = fromstr("POINT(%s %s)" % (lon, lat)), timestamp = timestamp, accuracy = accuracy)
			record.save()
			
			if ((user.last_location_timestamp and timestamp and timestamp > user.last_location_timestamp) or not user.last_location_timestamp):
				user.last_location_point = fromstr("POINT(%s %s)" % (lon, lat))

				if timestamp:
					user.last_location_timestamp = timestamp
				else:
					user.last_location_timestamp = now

				user.last_location_accuracy = accuracy
							
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
				logger.info("Location updated for user %s. %s: %s, %s, %s" % (user.id, datetime.datetime.utcnow().replace(tzinfo=pytz.utc), user.id, user.last_location_point, accuracy))
			else:
				logger.info("Location NOT updated for user %s. Old Timestamp. %s: %s, %s" % (user.id, timestamp, user.id, str((lon, lat))))
		else:
			logger.info("Location NOT updated for user %s. Lat/Lon Zero. %s: %s, %s" % (user.id, datetime.datetime.utcnow().replace(tzinfo=pytz.utc), user.id, str((lon, lat))))

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
		user = form.cleaned_data['user']
		deviceToken = form.cleaned_data['device_token'].replace(' ', '').replace('<', '').replace('>', '')

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

		if form.cleaned_data['build_id'] and form.cleaned_data['build_number']:
			# if last_build_info is empty or if either build_id or build_number is not in last_build_info
			#    update last_build_info
			buildId = form.cleaned_data['build_id']
			buildNum = form.cleaned_data['build_number']
			if ((not user.last_build_info) or 
				buildId not in user.last_build_info or 
				str(buildNum) not in user.last_build_info):
				user.last_build_info = "%s-%s" % (buildId, buildNum)
				logger.info("Build info updated to %s" % (user.last_build_info))

		user.save()
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

	if data.has_key('id'):
		customPayload['id'] = int(data['id'])

	if data.has_key('share_instance_id'):
		customPayload['share_instance_id'] = int(data['share_instance_id'])

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

			msg = "Your Swap code is:  %s" % (accessCode)
	
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
				user = users_util.createStrandUserThroughSmsAuth(phoneNumber, displayName, smsAuth[0], form.cleaned_data['build_number'])
				serializer = UserSerializer(user)
				response['user'] = serializer.data
		else:
			if accessCode == 2345:
				user = users_util.createStrandUserThroughSmsAuth(phoneNumber, displayName, None, form.cleaned_data['build_number'])
				serializer = UserSerializer(user)
				response['user'] = serializer.data
			else:
				return HttpResponse(json.dumps({'access_code': 'Invalid code'}), content_type="application/json", status=400)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")



def nothing(request):
	return HttpResponse(json.dumps(dict()), content_type="application/json")

