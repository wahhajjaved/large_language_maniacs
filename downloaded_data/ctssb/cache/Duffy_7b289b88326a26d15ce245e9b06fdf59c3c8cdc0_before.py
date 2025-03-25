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

from common.models import Photo, User, SmsAuth, Strand, NotificationLog, ContactEntry, FriendConnection, StrandInvite, StrandNeighbor, Action, LocationRecord, ShareInstance
from common.serializers import UserSerializer

from common import api_util, cluster_util, serializers

from strand import geo_util, notifications_util, friends_util, strands_util, users_util
from strand.forms import UserIdAndStrandIdForm, RegisterAPNSTokenForm, UpdateUserLocationForm, SendSmsCodeForm, AuthPhoneForm, OnlyUserIdForm

from ios_notifications.models import APNService, Device, Notification


logger = logging.getLogger(__name__)

def getActionsCache(user, publicStrandIds, photoIds):
	# Need to find all actions that affect the public strands (other people liking, commenting)
	# but filter down photos to only those strands
	# also find all actions this user took on any photos on the list
	# but filter out eval actions by other people
	
	oldActions = list(Action.objects.prefetch_related('strand', 'photos', 'photos__user', 'user').filter(Q(strand__in=publicStrandIds) | (Q(photo_id__in=photoIds) & Q(strand__in=publicStrandIds)) | (Q(photo_id__in=photoIds) & Q(user=user))).exclude(Q(action_type=constants.ACTION_TYPE_PHOTO_EVALUATED) & ~Q(user=user)))
	evalActions = Action.objects.prefetch_related('photo', 'user').filter(Q(action_type=constants.ACTION_TYPE_PHOTO_EVALUATED) & Q(user=user) & Q(photo_id__in=photoIds))

	oldActions.extend(evalActions)

	return oldActions
	
def getActionsByPhotoIdCache(actionsCache):
	actionsByPhotoId = dict()

	for action in actionsCache:
		if action.photo_id:
			if action.photo_id not in actionsByPhotoId:
				actionsByPhotoId[action.photo_id] = list()

			actionsByPhotoId[action.photo_id].append(action)

	return actionsByPhotoId

def addActionsToClusters(clusters, strandId, actionsByPhotoIdCache):
	finalClusters = list()

	for cluster in clusters:
		entriesToRemove = list()
		for entry in cluster:
			if entry["photo"].id in actionsByPhotoIdCache:
				entry["actions"] = actionsByPhotoIdCache[entry["photo"].id]
				
			entry["photo"].strand_id = strandId
		for entry in entriesToRemove:
			cluster.remove(entry)
		finalClusters.append(cluster)

	return finalClusters

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

	neighborStrandsByStrandId = dict()
	neighborUsersByStrandId = dict()
	for strand in strands:
		for strandNeighbor in strandNeighbors:
			added = False
			if strand.id == strandNeighbor.strand_1_id:
				if strand.id not in neighborStrandsByStrandId:
					neighborStrandsByStrandId[strand.id] = list()
				if strandNeighbor.strand_2 and strandNeighbor.strand_2 not in neighborStrandsByStrandId[strand.id]:
					neighborStrandsByStrandId[strand.id].append(strandNeighbor.strand_2)
				if not strandNeighbor.strand_2:
					if strandNeighbor.distance_in_meters:
						if strandNeighbor.distance_in_meters > constants.DISTANCE_WITHIN_METERS_FOR_FINE_NEIGHBORING:
							continue
					if strand.id not in neighborUsersByStrandId:
						neighborUsersByStrandId[strand.id] = list()
					neighborUsersByStrandId[strand.id].append(strandNeighbor.strand_2_user)
					
			elif strand.id == strandNeighbor.strand_2_id:
				if strand.id not in neighborStrandsByStrandId:
					neighborStrandsByStrandId[strand.id] = list()
				if strandNeighbor.strand_1 not in neighborStrandsByStrandId[strand.id]:
					neighborStrandsByStrandId[strand.id].append(strandNeighbor.strand_1)

	return (neighborStrandsByStrandId, neighborUsersByStrandId)

def userHasPostedPhotosToStrand(user, strand, actionsCache):
	hasPostedPhotos = False
	for action in actionsCache:
		if action.strand == strand and action.user_id == user.id and (action.action_type == constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND or action.action_type == constants.ACTION_TYPE_CREATE_STRAND):
			hasPostedPhotos = True
	return hasPostedPhotos


# ------------------------
def getActorsObjectData(userId, users, includePhone = True, invitedUsers = None):
		if not isinstance(users, list):
			users = [users]

		userData = list()
		for user in users:
			userData.append(user.id)

		if invitedUsers:
			for user in invitedUsers:
				userData.append(user.id)
		return userData

def getFriendsObjectData(userId, users, includePhone = True):
	if not isinstance(users, list) and not isinstance(users, set):
		users = [users]

	friendList = friends_util.getFriendsIds(userId)

	userData = list()
	for user in users:
		if user in friendList:
			relationship = constants.FEED_OBJECT_TYPE_RELATIONSHIP_FRIEND
		else:
			relationship = constants.FEED_OBJECT_TYPE_RELATIONSHIP_USER
		
		entry = {'display_name': user.display_name, 'id': user.id, constants.FEED_OBJECT_TYPE_RELATIONSHIP: relationship}

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
def getFormattedGroups(groups, simCaches = None, actionsByPhotoIdCache = None, filterOutEvaluated = True):
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

	for group in groups:
		if len(group['photos']) == 0:
			continue

		if actionsByPhotoIdCache and filterOutEvaluated:
			# Look through all our photos and actions taken on the photos
			# If we find that a photo already has an action of EVALUATED then we take it out

			# Have to make a list() of this since we need an independent copy to loop through
			photosNotEvaluated = list(group['photos'])
			for photo in group['photos']:
				if photo.id in actionsByPhotoIdCache:
					for action in actionsByPhotoIdCache[photo.id]:
						if action.action_type == constants.ACTION_TYPE_PHOTO_EVALUATED and photo in photosNotEvaluated:
							photosNotEvaluated.remove(photo)

			if len(photosNotEvaluated) == 0:
				continue
			else:
				group['photos'] = photosNotEvaluated

		clusters = cluster_util.getClustersFromPhotos(group['photos'], constants.DEFAULT_CLUSTER_THRESHOLD, 0, simCaches)

		if actionsByPhotoIdCache:
			clusters = addActionsToClusters(clusters, group['metadata']['strand_id'], actionsByPhotoIdCache)
		
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
def getObjectsDataForPrivateStrands(thisUser, strands, feedObjectType, friends = None, neighborStrandsByStrandId = None, neighborUsersByStrandId = None, locationRequired = True, requireInterestedUsers = True, findInterestedUsers = True):
	groups = list()

	if friends == None:
		friends = friends_util.getFriends(thisUser.id)

	if (neighborStrandsByStrandId == None or neighborUsersByStrandId == None) and findInterestedUsers:
		neighborStrandsByStrandId, neighborUsersByStrandId = getStrandNeighborsCache(strands, friends)
		printStats("neighbor-cache")

	strandsToDelete = list()
	for strand in strands:
		photos = strand.photos.all()

		photos = sorted(photos, key=lambda x: x.time_taken, reverse=True)
		photos = filter(lambda x: x.install_num >= 0, photos)
		
		if len(photos) == 0:
			logger.warning("in getObjectsDataForPrivateStrands found strand with no photos: %s" % (strand.id))
			strandsToDelete.append(strand)
			continue
		
		title = ""
		matchReasons = dict()
		interestedUsers = list()
		if findInterestedUsers:
			if strand.id in neighborStrandsByStrandId:
				for neighborStrand in neighborStrandsByStrandId[strand.id]:
					if neighborStrand.location_point and strand.location_point and strands_util.strandsShouldBeNeighbors(strand, neighborStrand, distanceLimit = constants.DISTANCE_WITHIN_METERS_FOR_FINE_NEIGHBORING, locationRequired = locationRequired):
						val, reason = strands_util.strandsShouldBeNeighbors(strand, neighborStrand, distanceLimit = constants.DISTANCE_WITHIN_METERS_FOR_FINE_NEIGHBORING, locationRequired = locationRequired)
						interestedUsers.extend(friends_util.filterUsersByFriends(thisUser.id, friends, neighborStrand.users.all()))

						for user in friends_util.filterUsersByFriends(thisUser.id, friends, neighborStrand.users.all()):
							dist = geo_util.getDistanceBetweenStrands(strand, neighborStrand)
							matchReasons[user.id] = "location-strand %s" % reason


					elif not locationRequired and strands_util.strandsShouldBeNeighbors(strand, neighborStrand, noLocationTimeLimitMin=3, distanceLimit = constants.DISTANCE_WITHIN_METERS_FOR_FINE_NEIGHBORING, locationRequired = locationRequired):
						interestedUsers.extend(friends_util.filterUsersByFriends(thisUser.id, friends, neighborStrand.users.all()))
						
						for user in friends_util.filterUsersByFriends(thisUser.id, friends, neighborStrand.users.all()):
							matchReasons[user.id] = "nolocation-strand"

				if strand.id in neighborUsersByStrandId:
					interestedUsers.extend(neighborUsersByStrandId[strand.id])
					for user in neighborUsersByStrandId[strand.id]:
						matchReasons[user.id] = "location-user"
					
			interestedUsers = list(set(interestedUsers))

			if len(interestedUsers) > 0:
				title = "might like these photos"
		
		suggestible = strand.suggestible

		if suggestible and len(interestedUsers) == 0 and requireInterestedUsers:
			suggestible = False
			
		if not strands_util.getLocationForStrand(strand) and locationRequired:
			interestedUsers = list()
			suggestible = False

		metadata = {'type': feedObjectType, 'id': strand.id, 'match_reasons': matchReasons, 'strand_id': strand.id, 'title': title, 'time_taken': strand.first_photo_time, 'actors': getActorsObjectData(thisUser.id, interestedUsers), 'suggestible': suggestible}
		entry = {'photos': photos, 'metadata': metadata}

		groups.append(entry)
	
	groups = sorted(groups, key=lambda x: x['photos'][0].time_taken, reverse=True)

	actionsCache = getActionsCache(thisUser, Strand.getIds(strands), Strand.getPhotoIds(strands))
	actionsByPhotoIdCache = getActionsByPhotoIdCache(actionsCache)
	# Pass in none for actions because there are no actions on private photos so don't use anything
	formattedGroups = getFormattedGroups(groups, actionsByPhotoIdCache = actionsByPhotoIdCache, filterOutEvaluated = True)
	
	# Lastly, we turn our groups into sections which is the object we convert to json for the api
	objects = api_util.turnFormattedGroupsIntoFeedObjects(formattedGroups, 10000)
	printStats("private-strands")

	# These are strands that are found to have no valid photos.  So maybe they were all deleted photos
	# Can remove them here since they're private strands so something with no valid photos shouldn't exist
	for strand in strandsToDelete:
		logger.info("Deleting private strand %s for user %s" % (strand.id, thisUser.id))
		strand.delete()

	return objects

def getPrivateStrandSuggestionsForSharedStrand(user, strand):
	# Look above and below 10x the number of minutes to strand
	timeHigh = strand.last_photo_time + datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING*5)
	timeLow = strand.first_photo_time - datetime.timedelta(minutes=constants.TIME_WITHIN_MINUTES_FOR_NEIGHBORING*5)

	# Get all the unshared strands for the given user that are close to the given strand
	privateStrands = Strand.objects.prefetch_related('photos', 'photos__user', 'users').filter(users__in=[user]).filter(private=True).filter(last_photo_time__lt=timeHigh).filter(first_photo_time__gt=timeLow)

	strandsThatMatch = list()
	for privateStrand in privateStrands:
		if (strands_util.strandsShouldBeNeighbors(strand, privateStrand, distanceLimit = constants.DISTANCE_WITHIN_METERS_FOR_FINE_NEIGHBORING, locationRequired = False)
			and privateStrand not in strandsThatMatch):
			strandsThatMatch.append(privateStrand)

	return strandsThatMatch
	
def getObjectsDataForPost(user, postAction, simCaches, actionsByPhotoIdCache):
	metadata = {'type': constants.FEED_OBJECT_TYPE_STRAND_POST, 'id': postAction.id, 'strand_id': postAction.strand.id, 'time_stamp': postAction.added, 'actors': getActorsObjectData(user.id, postAction.user)}
	photos = postAction.photos.all()
	photos = sorted(photos, key=lambda x: x.time_taken)

	photos = filter(lambda x: x.full_filename, photos)
	
	if len(photos) > 0:
		metadata['title'] = "added %s photos" % len(photos)

		groupEntry = {'photos': photos, 'metadata': metadata}

		formattedGroups = getFormattedGroups([groupEntry], simCaches = simCaches, actionsByPhotoIdCache = actionsByPhotoIdCache, filterOutEvaluated = False)
		# Lastly, we turn our groups into sections which is the object we convert to json for the api
		objects = api_util.turnFormattedGroupsIntoFeedObjects(formattedGroups, 200)
		return objects
	else:
		return []

def getBuildNumForUser(user):
	if user.last_build_info:
		return int(user.last_build_info.split('-')[1])
	else:
		return 4000

def getObjectsDataForStrands(strands, user):
	response = list()
	strandIds = Strand.getIds(strands)
	invitesCache =  StrandInvite.objects.prefetch_related('invited_user', 'strand').filter(strand__in=strandIds).filter(accepted_user__isnull=True).exclude(invited_user=user).filter(skip=False)
	
	photoIds = list()
	for strand in strands:
		photoIds.extend(Photo.getIds(strand.photos.all()))
	photoIds = set(photoIds)
	
	# Grab all actions for any strand or photo we're looking at
	# We use this to look for:
	# Grabbing all the post actions for a strand
	# Getting the likes and comments for a photo
	# See if the user has done a post, and if not...put in suggested photos
	actionsCache = getActionsCache(user, strandIds, photoIds)

	actionsByPhotoIdCache = getActionsByPhotoIdCache(actionsCache)

	simCaches = cluster_util.getSimCaches(photoIds)
	for strand in strands:
		entry = dict()

		postActions = list()
		for action in actionsCache:
			if action.strand == strand:
				postActions.append(action)

		# Find the timestamp of the most recent post
		if len(postActions) == 0:
			logger.error("in getObjectsDataForStrand found no actions for strand %s and user %s" % (strand.id, user.id))
			recentTimeStamp = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
		else:
			recentTimeStamp = sorted(postActions, key=lambda x:x.added, reverse=True)[0].added
		users = strand.users.all()

		# Create a list of all the invited users
		invites = list()
		for invite in invitesCache:
			if invite.strand == strand:
				invites.append(invite)	

		invitedUsers = list()
		for invite in invites:
			if invite.invited_user and invite.invited_user not in users and invite.invited_user not in invitedUsers:
				invitedUsers.append(invite.invited_user)
			elif not invite.invited_user:
				invitedUsers.append(User(id=0, display_name="", phone_number=invite.phone_number))
		entry = {'type': constants.FEED_OBJECT_TYPE_STRAND_POSTS, 'title': strands_util.getTitleForStrand(strand), 'id': strand.id, 'actors': getActorsObjectData(user.id, list(strand.users.all()), invitedUsers=invitedUsers), 'time_taken': strand.first_photo_time, 'time_stamp': recentTimeStamp, 'location': strands_util.getLocationForStrand(strand)}

		# Add the individual posts to the list
		entry['objects'] = list()
		for post in postActions:
			entry['objects'].extend(getObjectsDataForPost(user, post, simCaches, actionsByPhotoIdCache))

		if getBuildNumForUser(user) <= 4805:
			# Add in the suggested private photos if the user hasn't done a post yet and has photos that match
			if not userHasPostedPhotosToStrand(user, strand, actionsCache):
				privateStrands = getPrivateStrandSuggestionsForSharedStrand(user, strand)
				if len(privateStrands) > 0:
					suggestionsEntry = {'type': constants.FEED_OBJECT_TYPE_SUGGESTED_PHOTOS}
					suggestionsEntry['objects'] = getObjectsDataForPrivateStrands(user, privateStrands, constants.FEED_OBJECT_TYPE_STRAND, requireInterestedUsers = False, findInterestedUsers = False)
					entry['objects'].append(suggestionsEntry)
		response.append(entry)
		
	return response

def getInviteObjectsDataForUser(user):
	responseObjects = list()

	strandInvites = StrandInvite.objects.prefetch_related('strand', 'strand__photos', 'strand__users').filter(invited_user=user).exclude(skip=True).filter(accepted_user__isnull=True)
	friends = friends_util.getFriends(user.id)

	# Temp solution for using invites to hold incoming pictures 
	if getBuildNumForUser(user) > 4805:
		for strandInvite in strandInvites:
			strandInvite.accepted_user = user
			if user not in strandInvite.strand.users.all():
				action = Action.objects.create(user=user, strand=strandInvite.strand, action_type=constants.ACTION_TYPE_JOIN_STRAND)
				strandInvite.strand.users.add(user)
			strandInvite.save()
		return responseObjects

	
	strands = [x.strand for x in strandInvites]

	strandsObjectData = getObjectsDataForStrands(strands, user)
	
	neighborStrandsByStrandId, neighborUsersByStrandId = getStrandNeighborsCache(strands, friends, withUsers = True)

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
				logger.info("Not showing invite %s for user %s because photo %s doesn't have a full" % (invite.id, user.id, photo.id))
				
		if fullsLoaded:
			if user.first_run_sync_count == 0 or user.first_run_sync_complete:
				inviteIsReady = True
			else:
				inviteIsReady = False
				logger.info("Marking invite %s for user %s not ready because I don't think we've stranded first run yet  %s  %s" % (invite.id, user.id, user.first_run_sync_count, user.first_run_sync_complete))

			# If the invite's timeframe is within the last photo in the camera roll
			#   then look at the last stranded photo
			if user.last_photo_timestamp:
				if (invite.strand.first_photo_time - constants.TIMEDELTA_FOR_STRANDING < user.last_photo_timestamp and
					invite.strand.last_photo_time + constants.TIMEDELTA_FOR_STRANDING > user.last_photo_timestamp):
					if lastStrandedPhoto and lastStrandedPhoto.time_taken < user.last_photo_timestamp:
						inviteIsReady = False
						logger.info("Marking invite %s for user %s not ready because I don't think we've stranded everything yet  %s  %s" % (invite.id, user.id, lastStrandedPhoto.time_taken, user.last_photo_timestamp))

			invitePhotoCount = len(invite.strand.photos.all())
			if invitePhotoCount > 0:
				title = "shared %s photos with you" % invitePhotoCount
			else:
				title = "would like your photos"
				
			entry = {'type': constants.FEED_OBJECT_TYPE_INVITE_STRAND, 'id': invite.id, 'title': title, 'actors': getActorsObjectData(user.id, list(invite.strand.users.all())), 'time_stamp': invite.added}
			entry['ready'] = inviteIsReady
			entry['objects'] = list()
			entry['objects'].append(strandObjectDataById[invite.strand.id])

			# TODO - This can be done in one query instead of being in a loop
			privateStrands = getPrivateStrandSuggestionsForSharedStrand(user, invite.strand)
			newNeighborStrandsByStrandId, newNeighborUsersByStrandId = getStrandNeighborsCache(privateStrands, friends, withUsers = True)
			neighborStrandsByStrandId.update(newNeighborStrandsByStrandId)
			neighborUsersByStrandId.update(newNeighborUsersByStrandId)
			
			suggestionsEntry = {'type': constants.FEED_OBJECT_TYPE_SUGGESTED_PHOTOS}

			suggestionsEntry['objects'] = getObjectsDataForPrivateStrands(user, privateStrands, constants.FEED_OBJECT_TYPE_STRAND, friends = friends, neighborStrandsByStrandId = neighborStrandsByStrandId, neighborUsersByStrandId = neighborUsersByStrandId)
				
			entry['objects'].append(suggestionsEntry)

			if invitePhotoCount > 0:
				entry['location'] = strands_util.getLocationForStrand(invite.strand)
			elif len(suggestionsEntry['objects']) > 0:
				entry['location'] = suggestionsEntry['objects'][0]['location']


			responseObjects.append(entry)

	responseObjects = sorted(responseObjects, key=lambda x:x['time_stamp'], reverse=True)

	return responseObjects


def getObjectsDataForSpecificTime(user, lower, upper, title, rankNum):
	strands = Strand.objects.prefetch_related('photos', 'user').filter(user=user).filter(private=True).filter(suggestible=True).filter(contributed_to_id__isnull=True).filter(Q(first_photo_time__gt=lower) & Q(first_photo_time__lt=upper))

	objects = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_SWAP_SUGGESTION, neighborStrandsByStrandId=dict(), neighborUsersByStrandId=dict())
	objects = sorted(objects, key=lambda x: x['time_taken'], reverse=True)

	for suggestion in objects:
		suggestion['suggestible'] = True
		suggestion['suggestion_type'] = "timed-%s" % (title)
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
		
		response['objects'] = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_STRAND, friends=friends, locationRequired = True)
		
		printStats("private-3")
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")


def swap_inbox(request):
	startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		responseObjects = list()

		shareInstances = ShareInstance.objects.prefetch_related('photo', 'users', 'photo__user').filter(users__in=[user.id])

		shareInstanceIds = ShareInstance.getIds(shareInstances)
		printStats("swaps_inbox-1")

		actions = Action.objects.filter(share_instance_id__in=shareInstanceIds)
		actionsByShareInstanceId = dict()
		for action in actions:
			if action.share_instance_id not in actionsByShareInstanceId:
				actionsByShareInstanceId[action.share_instance_id] = list()
			actionsByShareInstanceId[action.share_instance_id].append(action)
		
		printStats("swaps_inbox-2")

		for shareInstance in shareInstances:
			actions = list()
			if shareInstance.id in actionsByShareInstanceId:
				actions = actionsByShareInstanceId[shareInstance.id]
			responseObjects.append(serializers.objectDataForShareInstance(shareInstance, actions, user))

		printStats("swaps_inbox-3")

		# Add in the list of all friends at the end
		peopleIds = friends_util.getFriendsIds(user.id)

		# Also add in all of the actors they're dealing with
		for obj in responseObjects:
			peopleIds.extend(obj['actors'])

		people = set(User.objects.filter(id__in=peopleIds))
		peopleEntry = {'type': constants.FEED_OBJECT_TYPE_FRIENDS_LIST, 'people': getFriendsObjectData(user.id, people, True)}
		responseObjects.append(peopleEntry)

		printStats("swaps_inbox-end")


		response["objects"] = responseObjects
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
		#responseObjects.extend(getInviteObjectsDataForUser(user))
		#printStats("swaps-invites")
		
		# Next throw in the list of existing Strands
		strands = set(Strand.objects.prefetch_related('photos', 'users').filter(users__in=[user]).filter(private=False).order_by('-added')[:50])
		printStats("inbox-2")

		strandsWithPhotos = list()
		for strand in strands:
			if len(strand.photos.all()) > 0:
				strandsWithPhotos.append(strand)

		responseObjects.extend(getObjectsDataForStrands(strandsWithPhotos, user))
		printStats("inbox-3")

		# sorting by last action on the strand
		# Do this up here because the next few entries don't have time_stamps
		responseObjects = sorted(responseObjects, key=lambda x: x['time_stamp'], reverse=True)

		# Add in the list of all friends at the end
		friends = friends_util.getFriends(user.id)
		friendsEntry = {'type': constants.FEED_OBJECT_TYPE_FRIENDS_LIST, 'actors': getActorsObjectData(user.id, friends, True)}
		printStats("inbox-4")

		responseObjects.append(friendsEntry)

		response['objects'] = responseObjects
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

def actions_list(request):
	startProfiling()
	response = dict({'result': True})

	form = OnlyUserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		responseObjects = list()

		# This code is duplicated in notifications_util
		# TODO(Derek): possibly refactor if we do stuff with this
		strands = Strand.objects.filter(users__in=[user]).filter(private=False)

		strandIds = Strand.getIds(strands)
		
		actions = Action.objects.prefetch_related('user', 'strand').exclude(user=user).filter(Q(action_type=constants.ACTION_TYPE_FAVORITE) | Q(action_type=constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND) | Q(action_type=constants.ACTION_TYPE_CREATE_STRAND) | Q(action_type=constants.ACTION_TYPE_COMMENT)).filter(strand_id__in=strandIds).order_by("-added")[:40]

		actionsData = list()
		for action in actions:
			# This filters out creates or requests with 0 photos
			if len(action.photos.all()) == 0 and (action.action_type == constants.ACTION_TYPE_CREATE_STRAND or action.action_type == constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND):
				continue
				
			actionsData.append(serializers.actionDataForApiSerializer(action))

		actionsData = {'type': 'actions_list', 'actions': actionsData}

		response['objects'] = [actionsData]
		printStats("actions-end")

		user.last_actions_list_request_timestamp = datetime.datetime.utcnow()
		user.save()
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

		inviteObjectIds = list()
		inviteObjects = list()

		# First throw in invite objects
		if not form.cleaned_data['build_number'] or (form.cleaned_data['build_number'] and int(form.cleaned_data['build_number']) <= 4805):
			inviteObjects = getInviteObjectsDataForUser(user)
			responseObjects.extend(inviteObjects)

			for objects in inviteObjects:
				# This grabs the id of the suggestions post object, which is the private strand id
				suggestedStrands = objects['objects'][1]['objects']
				for suggestedStrand in suggestedStrands:
					inviteObjectIds.append(suggestedStrand['id'])
			printStats("swaps-invites")

		# Now do neighbor suggestions
		friendsIdList = friends_util.getFriendsIds(user.id)

		strandNeighbors = StrandNeighbor.objects.filter((Q(strand_1_user_id=user.id) & Q(strand_2_user_id__in=friendsIdList)) | (Q(strand_1_user_id__in=friendsIdList) & Q(strand_2_user_id=user.id)))
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

		neighborStrandsByStrandId, neighborUsersByStrandId = getStrandNeighborsCache(strands, friends_util.getFriends(user.id))
		printStats("swaps-neighbors-cache")

		locationBasedSuggestions = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_SWAP_SUGGESTION, neighborStrandsByStrandId = neighborStrandsByStrandId, neighborUsersByStrandId = neighborUsersByStrandId, locationRequired = True)
		locationBasedSuggestions = filter(lambda x: x['suggestible'], locationBasedSuggestions)
		locationBasedSuggestions = sorted(locationBasedSuggestions, key=lambda x: x['time_taken'], reverse=True)

		rankNum = 0
		locationBasedIds = list()
		for suggestion in locationBasedSuggestions:
			suggestion['suggestion_rank'] = rankNum
			suggestion['suggestion_type'] = "friend-location"
			rankNum += 1
			locationBasedIds.append(suggestion['id'])

		for objects in locationBasedSuggestions:
			if objects['id'] not in inviteObjectIds:
				responseObjects.append(objects)
		printStats("swaps-location-suggestions")

		if len(inviteObjects) == 0:
			"""
			# Now do last night suggestions
			now = datetime.datetime.utcnow()

			if (now.hour < 5):
				lower = now - datetime.timedelta(days=1)
			else:
				lower = now
				
			lower = lower.replace(hour=0, minute=0)
			upper = lower + datetime.timedelta(hours=8) # So this now means 3 am

			lastNightObjects = getObjectsDataForSpecificTime(user, lower, upper, "Last Night", rankNum)
			rankNum += len(lastNightObjects)
			
			for objects in lastNightObjects:
				if objects['id'] not in inviteObjectIds:
					responseObjects.append(objects)

			printStats("swaps-time-suggestions")
			"""
			"""
			if len(responseObjects) < 20:
				# repeat the last request because we might have deleted some before.
				# TODO(Derek): find a way to avoid this
				strands = Strand.objects.prefetch_related('photos').filter(user=user).filter(private=True).filter(suggestible=True).filter(id__in=strandIds).order_by('-first_photo_time')[:20]

				noLocationSuggestions = getObjectsDataForPrivateStrands(user, strands, constants.FEED_OBJECT_TYPE_SWAP_SUGGESTION, neighborStrandsByStrandId=neighborStrandsByStrandId,  neighborUsersByStrandId = neighborUsersByStrandId, locationRequired=False)
				noLocationSuggestions = filter(lambda x: x['suggestible'], noLocationSuggestions)
				noLocationSuggestions = sorted(noLocationSuggestions, key=lambda x: x['time_taken'], reverse=True)

				# Filter out the location based suggestions we got before
				noLocationSuggestions = filter(lambda x: x['id'] not in locationBasedIds, noLocationSuggestions)
				for suggestion in noLocationSuggestions:
					suggestion['suggestion_rank'] = rankNum
					suggestion['suggestion_type'] = "friend-nolocation"
					rankNum += 1

				for suggestion in noLocationSuggestions:
					if suggestion['id'] not in inviteObjectIds:
						responseObjects.append(suggestion)

				printStats("swaps-nolocation-suggestions")
			"""
			# Last resort, try throwing in recent photos
			if len(responseObjects) < 3:
				now = datetime.datetime.utcnow()
				lower = now - datetime.timedelta(days=7)

				lastWeekObjects = getObjectsDataForSpecificTime(user, lower, now, "Last Week", rankNum)
				rankNum += len(lastWeekObjects)
			
				for objects in lastWeekObjects:
					if objects['id'] not in inviteObjectIds:
						responseObjects.append(objects)

				printStats("swaps-recent-photos")
		response['objects'] = responseObjects
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)
	return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")

def add_photos_to_strand(request):
	response = dict({'result': True})

	form = UserIdAndStrandIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		strand = form.cleaned_data['strand']
		
		requestData = api_util.getRequestData(request)

		photoIds = [int(x) for x in requestData["photo_ids[]"].split(',')]
		existingPhotoIds = Photo.getIds(strand.photos.all())

		entriesToCreate = list()
		newPhotoIds = list()
		for photoId in photoIds:
			if photoId not in existingPhotoIds:
				photo = Photo.objects.get(id=photoId)
				strands_util.addPhotoToStrand(strand, photo, {strand.id: list(strand.photos.all())}, {strand.id: list(strand.users.all())})
				newPhotoIds.append(photoId)

		if len(newPhotoIds) > 0:
			action = Action(user=user, strand=strand, photo_id=newPhotoIds[0], action_type=constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND)
			action.save()
			action.photos = newPhotoIds

			privateStrands = Strand.objects.prefetch_related('photos').filter(photos__id__in=newPhotoIds, private=True, user=user)

			for photoId in newPhotoIds:
				for privateStrand in privateStrands:
					ids = Photo.getIds(privateStrand.photos.all())
					if photoId in ids:
						action = Action.objects.create(user=user, strand=privateStrand, photo_id=photoId, action_type=constants.ACTION_TYPE_PHOTO_EVALUATED)
						
			for privateStrand in privateStrands:
				strands_util.checkStrandForAllPhotosEvaluated(privateStrand)

		
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

