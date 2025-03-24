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

from common.models import Photo, User, SmsAuth, Strand, NotificationLog, ContactEntry, FriendConnection, StrandInvite, StrandNeighbor, Action
from common.serializers import UserSerializer

from common import api_util, cluster_util, serializers

from strand import geo_util, notifications_util, friends_util, strands_util
from strand.forms import GetJoinableStrandsForm, GetNewPhotosForm, RegisterAPNSTokenForm, UpdateUserLocationForm, GetFriendsNearbyMessageForm, SendSmsCodeForm, AuthPhoneForm, OnlyUserIdForm, StrandApiForm

from ios_notifications.models import APNService, Device, Notification

logger = logging.getLogger(__name__)

def getActionsByPhotoIdCache(photoIds):
	actions = Action.objects.select_related().filter(photo_id__in=photoIds)
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

"""
	Creates a cache which is a dictionary with the key being the strandId and the value
	a list of neighbor strands

	returns cache[strandId] = list(neighborStrand1, neighborStrand2...)
"""
def getStrandNeighborsCache(strands, friends, withUsers = False):
	strandIds = Strand.getIds(strands)
	friendIds = [x.id for x in friends]

	strandNeighbors = StrandNeighbor.objects.prefetch_related('strand_1', 'strand_2').filter((Q(strand_1_id__in=strandIds) & Q(strand_2_user_id__in=friendIds)) | (Q(strand_1_user_id__in=friendIds) & Q(strand_2_id__in=strandIds)))

	if withUsers:
		strandNeighbors = strandNeighbors.prefetch_related('strand_1__users', 'strand_2__users')

	strandNeighbors = list(strandNeighbors)

	strandNeighborsCache = dict()
	for strand in strands:
		for strandNeighbor in strandNeighbors:
			added = False
			if strand.id == strandNeighbor.strand_1_id:
				if strand.id not in strandNeighborsCache:
					strandNeighborsCache[strand.id] = list()
				if strandNeighbor.strand_2 not in strandNeighborsCache[strand.id]:
					strandNeighborsCache[strand.id].append(strandNeighbor.strand_2)
			elif strand.id == strandNeighbor.strand_2_id:
				if strand.id not in strandNeighborsCache:
					strandNeighborsCache[strand.id] = list()
				if strandNeighbor.strand_1 not in strandNeighborsCache[strand.id]:
					strandNeighborsCache[strand.id].append(strandNeighbor.strand_1)
	return strandNeighborsCache

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
		user = User.objects.get(Q(phone_number=phoneNumber) & Q(product_id=2))
		
		# This increments the install number, which we use to track which photos were uploaded when
		user.install_num = user.install_num + 1
		user.save()

		return user
	except User.DoesNotExist:
		pass

	# TODO(Derek): Make this more interesting when we add auth to the APIs
	authToken = random.randrange(10000, 10000000)

	user = User.objects.create(phone_number = phoneNumber, display_name = displayName, phone_id = phoneId, product_id = 2, auth_token = str(authToken))

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

	# Now fill in strand invites for this phone number
	strandInvites = StrandInvite.objects.filter(phone_number=user.phone_number).filter(invited_user__isnull=True).filter(accepted_user__isnull=True)
	for strandInvite in strandInvites:
		strandInvite.invited_user = user
	if len(strandInvites) > 0:
		StrandInvite.bulkUpdate(strandInvites, "invited_user_id")

		user.first_run_sync_timestamp = strandInvites[0].strand.first_photo_time

		logger.debug("Updated %s invites with user id %s and set first_run_sync_timestamp to %s" % (len(strandInvites), user.id, user.first_run_sync_timestamp))


	contacts = ContactEntry.objects.filter(phone_number = user.phone_number).exclude(user=user).exclude(skip=True).filter(user__product_id=2)
	friends = set([contact.user for contact in contacts])

	FriendConnection.addNewConnections(user, friends)

	# Create directory for photos
	# TODO(Derek): Might want to move to a more common location if more places that we create users
	try:
		userBasePath = user.getUserDataPath()
		os.stat(userBasePath)
	except:
		os.mkdir(userBasePath)
		os.chmod(userBasePath, 0775)

	return user


# ------------------------

def getActorsObjectData(users, includePhone = False, invitedUsers = None):
	if not isinstance(users, list):
		users = [users]

	userData = list()
	for user in users:
		entry = {'display_name': user.display_name, 'id': user.id}

		if includePhone:
			entry['phone_number'] = user.phone_number

		userData.append(entry)

	if invitedUsers:
		for user in invitedUsers:
			entry = {'display_name': user.display_name, 'id': user.id, 'invited': True}

			if includePhone:
				entry['phone_number'] = user.phone_number

			userData.append(entry)

	return userData


"""
	This turns a list of list of photos into groups that contain a title and cluster.

	We do all the photos at once so we can load up the sims cache once

	Takes in list of dicts::
	[
		{
			'photos': [photo1, photo2]
			'metadata' : {'strand_id': 12}
		},
		{
			'photos': [photo1, photo2]
			'metadata' : {'strand_id': 17}
		}
	]

	Returns format of:
	[
		{
			'clusters': clusters
			'metadata': {'title': blah,
						 'subtitle': blah2,
						 'strand_id': 12
						}
		},
		{
			'clusters': clusters
			'metadata': {'title': blah3,
						 'subtitle': blah4,
						 'strand_id': 17
						}
		},
	]
"""
def getFormattedGroups(groups, simCaches = None, actionsByPhotoIdCache = None):
	if len(groups) == 0:
		return []

	output = list()

	photoIds = list()
	for group in groups:
		for photo in group['photos']:
			photoIds.append(photo.id)

	# Fetch all the similarities at once so we can process in memory
	a = datetime.datetime.now()
	if simCaches == None:
		simCaches = cluster_util.getSimCaches(photoIds)

	# Do same with actions
	if actionsByPhotoIdCache == None:
		actionsByPhotoIdCache = getActionsByPhotoIdCache(photoIds)

	for group in groups:
		if len(group['photos']) == 0:
			continue

		clusters = cluster_util.getClustersFromPhotos(group['photos'], constants.DEFAULT_CLUSTER_THRESHOLD, 0, simCaches)
		clusters = addActionsToClusters(clusters, actionsByPhotoIdCache)
		

		location = strands_util.getBestLocationForPhotos(group['photos'])
		if not location:
			location = "Location Unknown"

		metadata = group['metadata']
		metadata.update({'subtitle': location, 'location': location})
		
		output.append({'clusters': clusters, 'metadata': metadata})

	return output

"""
	Returns back the objects data for private strands which includes neighbor_users.
	This gets the Strand Neighbors (two strands which are possible to strand together)
"""
def getObjectsDataForPrivateStrands(user, strands, feedObjectType, friends = None, strandNeighborsCache = None):
	groups = list()

	if friends == None:
		friends = friends_util.getFriends(user.id)

	if strandNeighborsCache == None:
		strandNeighborsCache = getStrandNeighborsCache(strands, friends)
		printStats("neighbor-cache")

	for strand in strands:
		strandId = strand.id
		photos = strand.photos.all()

		photos = sorted(photos, key=lambda x: x.time_taken, reverse=True)
		photos = filter(lambda x: x.install_num >= 0, photos)
		
		if len(photos) == 0:
			logger.warning("in getObjectsDataForPrivateStrands found strand with no photos: %s" % (strand.id))
			strand.delete()
			continue
		
		interestedUsers = list()
		if strand.id in strandNeighborsCache:
			for neighborStrand in strandNeighborsCache[strand.id]:
				if neighborStrand.location_point and strand.location_point:
					interestedUsers.extend(friends_util.filterUsersByFriends(user.id, friends, neighborStrand.users.all()))

		interestedUsers = list(set(interestedUsers))

		if len(interestedUsers) > 0:
			title = "might like these photos"
		else:
			title = ""

		
		suggestible = strand.suggestible

		if suggestible and len(interestedUsers) == 0:
			suggestible = False
			
		if not strands_util.getLocationForStrand(strand):
			interestedUsers = list()
			suggestible = False

		metadata = {'type': feedObjectType, 'id': strandId, 'title': title, 'time_taken': strand.first_photo_time, 'actors': getActorsObjectData(interestedUsers, True), 'suggestible': suggestible}
		entry = {'photos': photos, 'metadata': metadata}

		groups.append(entry)
	
	groups = sorted(groups, key=lambda x: x['photos'][0].time_taken, reverse=True)

	formattedGroups = getFormattedGroups(groups)
	
	# Lastly, we turn our groups into sections which is the object we convert to json for the api
	objects = api_util.turnFormattedGroupsIntoFeedObjects(formattedGroups, 200)
	printStats("private-strands")
	return objects


def getPrivateStrandSuggestionsForSharedStrand(user, strand):
	# Look above and below 10x the number of minutes to strand
	timeHigh = strand.last_photo_time + datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING*5)
	timeLow = strand.first_photo_time - datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING*5)

	# Get all the unshared strands for the given user that are close to the given strand
	privateStrands = Strand.objects.prefetch_related('photos', 'photos__user', 'users').filter(users__in=[user]).filter(private=True).filter(last_photo_time__lt=timeHigh).filter(first_photo_time__gt=timeLow)
	
	strandsThatMatch = list()
	for privateStrand in privateStrands:
		for photo in privateStrand.photos.all():
			if strands_util.photoBelongsInStrand(photo, strand, honorLocation=False) and privateStrand not in strandsThatMatch:
				strandsThatMatch.append(privateStrand)

	return strandsThatMatch
	
def getObjectsDataForPost(postAction, simCaches, actionsByPhotoIdCache):
	metadata = {'type': constants.FEED_OBJECT_TYPE_STRAND_POST, 'id': postAction.id, 'time_stamp': postAction.added, 'actors': getActorsObjectData(postAction.user)}
	photos = postAction.photos.all()
	photos = sorted(photos, key=lambda x: x.time_taken)
	
	metadata['title'] = "added %s photos" % len(photos)

	groupEntry = {'photos': photos, 'metadata': metadata}

	formattedGroups = getFormattedGroups([groupEntry], simCaches = simCaches, actionsByPhotoIdCache = actionsByPhotoIdCache)
	# Lastly, we turn our groups into sections which is the object we convert to json for the api
	objects = api_util.turnFormattedGroupsIntoFeedObjects(formattedGroups, 200)
	return objects

def getObjectsDataForStrands(strands, user):
	response = list()
	strandIds = Strand.getIds(strands)
	actionsCache = Action.objects.prefetch_related('strand', 'photos', 'photos__user', 'user').filter(strand__in=strandIds).filter(Q(action_type=constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND) | Q(action_type=constants.ACTION_TYPE_CREATE_STRAND))
	invitesCache =  StrandInvite.objects.prefetch_related('invited_user', 'strand').filter(strand__in=strandIds).filter(accepted_user__isnull=True).exclude(invited_user=user).filter(skip=False)

	photoIds = list()
	for strand in strands:
		photoIds.extend(Photo.getIds(strand.photos.all()))

	photoIds = set(photoIds)

	simCaches = cluster_util.getSimCaches(photoIds)

	actionsByPhotoIdCache = getActionsByPhotoIdCache(photoIds)
	
	actionsCache = list(actionsCache)
	for strand in strands:
		entry = dict()

		postActions = list()
		for action in actionsCache:
			if action.strand == strand:
				postActions.append(action)

		if len(postActions) == 0:
			logger.error("in getObjectsDataForStrand found no actions for strand %s and user %s" % (strand.id, user.id))
			recentTimeStamp = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
		else:
			recentTimeStamp = sorted(postActions, key=lambda x:x.added, reverse=True)[0].added
		users = strand.users.all()

		invites = list()
		for invite in invitesCache:
			if invite.strand == strand:
				invites.append(invite)	

		invitedUsers = list()
		for invite in invites:
			if invite.invited_user and invite.invited_user not in users and invite.invited_user not in invitedUsers:
				invitedUsers.append(invite.invited_user)
			elif not invite.invited_user:
				contactEntries = ContactEntry.objects.filter(user=user, phone_number=invite.phone_number, skip=False)
				name = ""
				for entry in contactEntries:
					if name == "":
						name = entry.name.split(" ")[0]

				invitedUsers.append(User(id=0, display_name=name))
		entry = {'type': constants.FEED_OBJECT_TYPE_STRAND_POSTS, 'title': strands_util.getTitleForStrand(strand), 'id': strand.id, 'actors': getActorsObjectData(list(strand.users.all()), invitedUsers=invitedUsers), 'time_taken': strand.first_photo_time, 'time_stamp': recentTimeStamp, 'location': strands_util.getLocationForStrand(strand)}

		entry['objects'] = list()
		for post in postActions:
			entry['objects'].extend(getObjectsDataForPost(post, simCaches, actionsByPhotoIdCache))
		response.append(entry)
		
	return response

def getInviteObjectsDataForUser(user):
	responseObjects = list()

	strandInvites = StrandInvite.objects.prefetch_related('strand', 'strand__photos', 'strand__users').filter(invited_user=user).exclude(skip=True).filter(accepted_user__isnull=True)
	friends = friends_util.getFriends(user.id)
	
	strands = [x.strand for x in strandInvites]

	strandsObjectData = getObjectsDataForStrands(strands, user)
	
	strandNeighborsCache = getStrandNeighborsCache(strands, friends, withUsers = True)

	strandObjectDataById = dict()
	for strandObjectData in strandsObjectData:
		strandObjectDataById[strandObjectData['id']] = strandObjectData

	lastStrandedPhoto = Photo.objects.filter(user=user, strand_evaluated=True).order_by("-time_taken")[:1]
	if len(lastStrandedPhoto) > 0:
		lastStrandedPhoto = lastStrandedPhoto[0]
	else:
		lastStrandedPhoto = None
		
	for invite in strandInvites:
		inviteIsReady = True
		fullsLoaded = True
		invitePhotos = invite.strand.photos.all()

		# Go through all photos and see if there's any that don't belong to this user
		#  and don't have a thumb.  If a user just created an invite this should be fine
		for photo in invitePhotos:
			if photo.user_id != user.id and not photo.full_filename:
				fullsLoaded = False
				logger.info("Not showing invite %s because photo %s doesn't have a full" % (invite.id, photo.id))
				
		if fullsLoaded:
			if user.first_run_sync_count == 0 or user.first_run_sync_complete:
				inviteIsReady = True
			else:
				inviteIsReady = False
				logger.info("Marking invite %s not ready because I don't think we've stranded first run yet  %s  %s" % (invite.id, user.first_run_sync_count, user.first_run_sync_complete))

			# If the invite's timeframe is within the last photo in the camera roll
			#   then look at the last stranded photo
			if user.last_photo_timestamp:
				if (invite.strand.first_photo_time - constants.TIMEDELTA_FOR_STRANDING < user.last_photo_timestamp and
					invite.strand.last_photo_time + constants.TIMEDELTA_FOR_STRANDING > user.last_photo_timestamp):
					if lastStrandedPhoto and lastStrandedPhoto.time_taken < user.last_photo_timestamp:
						inviteIsReady = False
						logger.info("Marking invite %s not ready because I don't think we've stranded everything yet  %s  %s" % (invite.id, lastStrandedPhoto.time_taken, user.last_photo_timestamp))

			title = "shared %s photos with you" % invite.strand.photos.count()
			entry = {'type': constants.FEED_OBJECT_TYPE_INVITE_STRAND, 'id': invite.id, 'title': title, 'actors': getActorsObjectData(list(invite.strand.users.all())), 'time_stamp': invite.added}
			entry['ready'] = inviteIsReady
			entry['objects'] = list()
			entry['objects'].append(strandObjectDataById[invite.strand.id])

			# TODO - This can be done in one query instead of being in a loop
			privateStrands = getPrivateStrandSuggestionsForSharedStrand(user, invite.strand)
			strandNeighborsCache.update(getStrandNeighborsCache(privateStrands, friends, withUsers = True))
			
			suggestionsEntry = {'type': constants.FEED_OBJECT_TYPE_SUGGESTED_PHOTOS}

			suggestionsEntry['objects'] = getObjectsDataForPrivateStrands(user, privateStrands, constants.FEED_OBJECT_TYPE_STRAND, friends = friends, strandNeighborsCache = strandNeighborsCache)

			entry['objects'].append(suggestionsEntry)

			responseObjects.append(entry)

	responseObjects = sorted(responseObjects, key=lambda x:x['time_stamp'], reverse=True)

	return responseObjects


def getObjectsDataForSpecificTime(user, lower, upper, title, rankNum):
	strands = Strand.objects.prefetch_related('photos', 'user').filter(user=user).filter(private=True).filter(suggestible=True).filter(contributed_to__isnull=True).filter(Q(first_photo_time__gt=lower) & Q(first_photo_time__lt=upper))

	objects = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_SWAP_SUGGESTION, strandNeighborsCache=dict())
	objects = sorted(objects, key=lambda x: x['time_taken'])

	for suggestion in objects:
		suggestion['suggestible'] = True
		suggestion['title'] = title
		suggestion['suggestion_rank'] = rankNum
		rankNum += 1
	return objects


#####################################################################################
#################################  EXTERNAL METHODS  ################################
#####################################################################################


requestStartTime = None
lastCheckinTime = None
lastCheckinQueryCount = 0

def startProfiling():
	global requestStartTime
	global lastCheckinTime
	global lastCheckinQueryCount
	requestStartTime = datetime.datetime.now()
	lastCheckinTime = requestStartTime
	lastCheckinQueryCount = 0

def printStats(title, printQueries = False):
	global lastCheckinTime
	global lastCheckinQueryCount

	now = datetime.datetime.now()
	msTime = ((now-lastCheckinTime).microseconds / 1000 + (now-lastCheckinTime).seconds * 1000)
	lastCheckinTime = now

	queryCount = len(connection.queries) - lastCheckinQueryCount
	

	print "%s took %s ms and did %s queries" % (title, msTime, queryCount)

	if printQueries:
		print "QUERIES for %s" % title
		for query in connection.queries[lastCheckinQueryCount:]:
			print query

	lastCheckinQueryCount = len(connection.queries)


# ----------------------- FEED ENDPOINTS --------------------

"""
	Return the Duffy JSON for the strands a user has that are private and unshared
"""
def private_strands(request):
	startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']

		printStats("private-1")
		
		strands = list(Strand.objects.prefetch_related('photos', 'users', 'photos__user').filter(user=user).filter(private=True))

		printStats("private-2")

		deletedSomething = False
		for strand in strands:
			if len(strand.photos.all()) == 0:
				logging.error("Found strand %s with no photos in private strands, deleting.  users are %s" % (strand.id, strand.users.all()))
				strand.delete()
				deletedSomething = True

		if deletedSomething:
			strands = list(Strand.objects.prefetch_related('photos', 'users', 'photos__user').filter(user=user).filter(private=True))


		friends = friends_util.getFriends(user.id)

		strandNeighborsCache = getStrandNeighborsCache(strands, friends, withUsers=True)
		printStats("neighbors-cache")
		
		response['objects'] = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_STRAND, friends=friends, strandNeighborsCache=strandNeighborsCache)
		
		printStats("private-3")
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")


"""
	Returns back the invites and strands a user has
"""
def strand_inbox(request):
	startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		responseObjects = list()

		# First throw in invite objects
		# TODO(Derek): Take this out once new client is pushed
		responseObjects.extend(getInviteObjectsDataForUser(user))
		printStats("swaps-invites")
		
		# Next throw in the list of existing Strands
		strands = set(Strand.objects.prefetch_related('photos', 'users').filter(users__in=[user]).filter(private=False))
		printStats("inbox-2")

		deletedSomething = False
		for strand in strands:
			if len(strand.photos.all()) == 0:
				logging.error("Found strand %s with no photos in inbox, deleting.  users are %s" % (strand.id, strand.users.all()))
				strand.delete()
				deletedSomething = True

		if deletedSomething:
			strands = set(Strand.objects.prefetch_related('photos', 'users').filter(users__in=[user]).filter(private=False))

		#nonInviteStrandObjects = list()
		responseObjects.extend(getObjectsDataForStrands(strands, user))
		printStats("inbox-3")

		# sorting by last action on the strand
		# Do this up here because the next few entries don't have time_stamps
		responseObjects = sorted(responseObjects, key=lambda x: x['time_stamp'], reverse=True)

		# Add in the list of all friends at the end
		friendsEntry = {'type': constants.FEED_OBJECT_TYPE_FRIENDS_LIST, 'actors': getActorsObjectData(friends_util.getFriends(user.id), True)}
		printStats("inbox-4")

		responseObjects.append(friendsEntry)

		response['objects'] = responseObjects
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

"""
	Returns back the invites and strands a user has
"""
def swaps(request):
	startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		responseObjects = list()

		# First throw in invite objects
		responseObjects.extend(getInviteObjectsDataForUser(user))
		printStats("swaps-invites")

		# Now do neighbor suggestions
		neighborIdList = friends_util.getFriendsIds(user.id)

		strandNeighbors = StrandNeighbor.objects.filter((Q(strand_1_user_id=user.id) & Q(strand_2_user_id__in=neighborIdList)) | (Q(strand_1_user_id__in=neighborIdList) & Q(strand_2_user_id=user.id)))
		strandIds = list()
		for strandNeighbor in strandNeighbors:
			if strandNeighbor.strand_1_user_id == user.id:
				strandIds.append(strandNeighbor.strand_1_id)
			else:
				strandIds.append(strandNeighbor.strand_2_id)

		strands = Strand.objects.prefetch_related('photos').filter(user=user).filter(private=True).filter(suggestible=True).filter(id__in=strandIds).order_by('-first_photo_time')[:20]

		# The prefetch for 'user' took a while here so just do it manually
		for strand in strands:
			for photo in strand.photos.all():
				photo.user = user
				
		strands = list(strands)
		printStats("swaps-strands-fetch")

		strandNeighborsCache = getStrandNeighborsCache(strands, friends_util.getFriends(user.id))
		printStats("swaps-neighbors-cache")

		neighborBasedSuggestions = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_SWAP_SUGGESTION, strandNeighborsCache=strandNeighborsCache)
		neighborBasedSuggestions = filter(lambda x: x['suggestible'], neighborBasedSuggestions)
		neighborBasedSuggestions = sorted(neighborBasedSuggestions, key=lambda x: x['time_taken'])

		rankNum = 0
		for suggestion in neighborBasedSuggestions:
			suggestion['suggestion_rank'] = rankNum
			rankNum += 1
		responseObjects.extend(neighborBasedSuggestions)
		printStats("swaps-neighbor-suggestions")
		
		# Now do halloween suggestions
		halloweenNight = pytz.timezone("US/Eastern").localize(datetime.datetime(2014,10,31,21,0,0,0)).astimezone(pytz.timezone("UTC"))
		lower = halloweenNight - datetime.timedelta(hours=3)
		upper = halloweenNight + datetime.timedelta(hours=7)
		halloweenObjects = getObjectsDataForSpecificTime(user, lower, upper, "Halloween", rankNum)
		rankNum += len(halloweenObjects)
		responseObjects.extend(halloweenObjects)

		# Now do last night suggestions
		now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
		yesterday = now - datetime.timedelta(days=1)
		lastNight = yesterday.replace(hour=21, minute=0)
		lower = lastNight - datetime.timedelta(hours=3)
		upper = lastNight + datetime.timedelta(hours=7)
		lastNightObjects = getObjectsDataForSpecificTime(user, lower, upper, "Last Night", rankNum)
		responseObjects.extend(lastNightObjects)

		printStats("swaps-time-suggestions")
		
		response['objects'] = responseObjects
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")


# ---------------------------------------------------------------

# Soon to be deprecated
def invited_strands(request):
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		response['objects'] = getInviteObjectsDataForUser(user)
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



def nothing(request):
	return HttpResponse(json.dumps(dict()), content_type="application/json")

