from random import randint
import datetime
import logging
import re
import phonenumbers
import json
from threading import Thread
import dateutil.parser

from django.shortcuts import get_list_or_404
from django.db import IntegrityError
from django.db.models import Q
from django.contrib.gis.geos import Point, fromstr
from django.forms.models import model_to_dict
from django.http import HttpResponse

from rest_framework.generics import CreateAPIView, GenericAPIView, RetrieveUpdateDestroyAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.mixins import CreateModelMixin, ListModelMixin
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.views import APIView

from peanut.settings import constants

from common.models import ContactEntry, StrandInvite, User, Photo, Action, Strand, FriendConnection, StrandNeighbor
from common.serializers import PhotoSerializer, BulkContactEntrySerializer, BulkStrandInviteSerializer
from common import location_util, api_util

# TODO(Derek): move this to common
from arbus import image_util

from strand import notifications_util, strands_util

logger = logging.getLogger(__name__)

class BasePhotoAPI(APIView):
    def jsonDictToSimple(self, jsonDict):
        ret = dict()
        for key in jsonDict:
            var = jsonDict[key]
            if type(var) is dict or type(var) is list:
                ret[key] = json.dumps(jsonDict[key])
            else:
                ret[key] = str(var)

        return ret

    """
        Fill in extra data that needs a bit more processing.
        Right now time_taken and location_point.  Both will look at the file exif data if
          we don't have iphone metadata
    """
    def populateExtraData(self, photo):
        if not photo.location_point:
            lat, lon, accuracy = location_util.getLatLonAccuracyFromExtraData(photo, True)

            if (lat and lon):
                photo.location_point = fromstr("POINT(%s %s)" % (lon, lat))
                photo.location_accuracy_meters = accuracy

            elif accuracy and accuracy < photo.location_accuracy_meters:
                photo.location_point = fromstr("POINT(%s %s)" % (lon, lat))
                photo.location_accuracy_meters = accuracy

                if photo.strand_evaluated:
                    photo.strand_needs_reeval = True
                    
            elif accuracy and accuracy >= photo.location_accuracy_meters:
                logger.debug("For photo %s, Got new accuracy but was the same or greater:  %s  %s" % (photo.id, accuracy, photo.location_accuracy_meters))
        
        if not photo.time_taken:
            photo.time_taken = image_util.getTimeTakenFromExtraData(photo, True)
                    
        # Bug fix for bad data in photo where date was before 1900
        # Initial bug was from a photo in iPhone 1, guessing at the date
        if (photo.time_taken and photo.time_taken.date() < datetime.date(1900, 1, 1)):
            logger.debug("Found a photo with a date earlier than 1900: %s" % (photo.id))
            photo.time_taken = datetime.date(2007, 9, 1)
                
        return photo

    def populateExtraDataForPhotos(self, photos):
        for photo in photos:
            self.populateExtraData(photo)
        return photos

    def simplePhotoSerializer(self, photoData):
        photoData["user_id"] = photoData["user"]
        del photoData["user"]

        if "saved_with_swap" in photoData:
            photoData["saved_with_swap"] = int(photoData["saved_with_swap"])

        if "time_taken" in photoData:
            timeStr = photoData["time_taken"].translate(None, 'apm ')
            try:
                photoData["time_taken"] = dateutil.parser.parse(timeStr)
            except ValueError:
                logger.error("Caught a ValueError in the REST photos api.  %s date was invalid.  Setting to Sept 2007 for photo %s and user %s.  You might want to manually edit it and set strand_evaluated to False" % (timeStr, photoData["user_id"]))
                photoData["time_taken"] = datetime.date(2007, 9, 1)

        if "local_time_taken" in photoData:
            timeStr = photoData["time_taken"].translate(None, 'apm ')
            photoData["local_time_taken"] = dateutil.parser.parse(timeStr)

        if "id" in photoData:
            photoId = int(photoData["id"])

            if photoId == 0:
                del photoData["id"]
            else:
                photoData["id"] = photoId

        photo = Photo(**photoData)
        return photo


class PhotoAPI(BasePhotoAPI):
    def getObject(self, photoId):
        try:
            return Photo.objects.get(id=photoId)
        except Photo.DoesNotExist:
            logger.info("Photo id does not exist: %s   returning 404" % (photoId))
            raise Http404

    def get(self, request, photoId=None, format=None):
        if (photoId):
            photo = self.getObject(photoId)
            serializer = PhotoSerializer(photo)
            return Response(serializer.data)
        else:
            pass

    
    def patch(self, request, photoId, format=None):
        photo = self.getObject(photoId)

        photoData = request.DATA
        serializer = PhotoSerializer(photo, data=photoData, partial=True)

        if serializer.is_valid():
            serializer.save()

            Thread(target=threadedSendNotifications, args=(userIds,)).start()
            return Response(serializer.data)
        else:
            logger.info("Photo serialization failed, returning 400.  Errors %s" % (serializer.errors))
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def put(self, request, photoId, format=None):
        photo = self.getObject(photoId)

        if "photo" in request.DATA:
            jsonDict = json.loads(request.DATA["photo"])
            photoData = self.jsonDictToSimple(jsonDict)
        else:
            photoData = request.DATA

        serializer = PhotoSerializer(photo, data=photoData, partial=True)

        if serializer.is_valid():
            # This will look at the uploaded metadata or exif data in the file to populate more fields
            photo = self.populateExtraData(serializer.object)
                        
            image_util.handleUploadedImage(request, serializer.data["file_key"], serializer.object)
            Photo.bulkUpdate(photo, ["location_point", "strand_needs_reeval", "location_accuracy_meters", "full_filename", "thumb_filename", "metadata", "time_taken"])

            logger.info("Successfully did a put for photo %s" % (photo.id))
            return Response(PhotoSerializer(photo).data)
        else:
            logger.info("Photo serialization failed, returning 400.  Errors %s" % (serializer.errors))
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, format=None):
        serializer = PhotoSerializer(data=request.DATA, partial=True)
        if serializer.is_valid():
            try:
                serializer.save()
                image_util.handleUploadedImage(request, serializer.data["file_key"], serializer.object)

                # This will look at the uploaded metadata or exif data in the file to populate more fields
                photo = self.populateExtraData(serializer.object)
                Photo.bulkUpdate(photo, ["location_point", "strand_needs_reeval", "location_accuracy_meters", "full_filename", "thumb_filename", "metadata", "time_taken"])

                logger.info("Successfully did a post for photo %s" % (photo.id))
                return Response(PhotoSerializer(photo).data)
            except IntegrityError:
                logger.error("IntegrityError")
                Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, photoId, format=None):
        # TODO: Derek. Remove this hack that currently handles repetitive requests to delete same photo
        try:
            photo = Photo.objects.get(id=photoId)
        except Photo.DoesNotExist:
            logger.info("Photo id does not exist in delete: %s   returning 204" % (photoId))
            return Response(status=status.HTTP_204_NO_CONTENT)

        userId = photo.user_id

        photo.delete()

        logger.info("DELETE - User %s deleted photo %s" % (userId, photoId))
        return Response(status=status.HTTP_204_NO_CONTENT)

class PhotoBulkAPI(BasePhotoAPI):
    def populateTimezonesForPhotos(self, photos):
        timezonerBaseUrl = "http://localhost:8234/timezone?"
        
        params = list()
        photosNeedingTimezone = list()
        for photo in photos:
            if not photo.time_taken and photo.local_time_taken and photo.location_point:
                photosNeedingTimezone.append(photo)
                params.append("ll=%s,%s" % (photo.location_point.y, photo.location_point.x))
        timezonerParams = '&'.join(params)

        if len(photosNeedingTimezone) > 0:
            timezonerUrl = "%s%s" % (timezonerBaseUrl, timezonerParams)

            logger.info("requesting timezones for %s photos" % len(photosNeedingTimezone))
            timezonerResultJson = urllib2.urlopen(timezonerUrl).read()
            
            if (timezonerResultJson):
                timezonerResult = json.loads(timezonerResultJson)
                for i, photo in enumerate(photosNeedingTimezone):
                    timezoneName = timezonerResult[i]
                    if not timezoneName:
                        logger.error("got no timezone with lat:%s lon:%s, setting to Eastern" % (photo.location_point.y, photo.location_point.x))
                        tzinfo = pytz.timezone('US/Eastern')
                    else:   
                        tzinfo = pytz.timezone(timezoneName)
                            
                    localTimeTaken = photo.local_time_taken.replace(tzinfo=tzinfo)
                    photo.time_taken = localTimeTaken.astimezone(pytz.timezone("UTC"))
                logger.info("Successfully updated timezones for %s photos" % len(photosNeedingTimezone))

    def post(self, request, format=None):
        response = list()

        startTime = datetime.datetime.now()

        objsToCreate = list()
        objsToUpdate = list()

        batchKey = randint(1,10000)  
        if "patch_photos" in request.DATA:
            response = dict()
            photosData = request.DATA["patch_photos"]

            # fetch hashes for these photos to check for dups if this is a new install
            try:
                user = User.objects.get(id=photosData[0]['user'])
            except User.DoesNotExist:
                return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")  

            logger.info("Got request for bulk patch update with %s photos and %s files from user %s" % (len(photosData), len(request.FILES), user.id))

            for photoData in photosData:
                photoData = self.jsonDictToSimple(photoData)
                photoData["bulk_batch_key"] = batchKey

                photo = self.simplePhotoSerializer(photoData)
                objsToUpdate.append(photo)
                
            Photo.bulkUpdate(objsToUpdate, ['install_num', 'iphone_faceboxes_topleft'])
            objsToUpdate = Photo.objects.filter(id__in=Photo.getIds(objsToUpdate))

            response['patch_photos'] = [model_to_dict(photo) for photo in objsToUpdate]

            logger.info("Successfully processed %s photos for user %s" % (len(objsToUpdate), user.id))
            return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json", status=201)


        elif "bulk_photos" in request.DATA:
            photosData = json.loads(request.DATA["bulk_photos"])

            # fetch hashes for these photos to check for dups if this is a new install
            try:
                user = User.objects.get(id=photosData[0]['user'])
            except User.DoesNotExist:
                return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json")  

            logger.info("Got request for bulk photo update with %s photos and %s files from user %s" % (len(photosData), len(request.FILES), user.id))
            
            existingPhotosByHash = dict()
            if user.install_num > 0 and len(request.FILES) == 0:
                logger.info("It appears user %s has a new install, fetching existing photos" % (user.id))
                existingPhotos = Photo.objects.filter(user = user, install_num__lt=user.install_num)
                for photo in existingPhotos:
                    if photo.iphone_hash not in existingPhotosByHash:
                        existingPhotosByHash[photo.iphone_hash] = list()
                    existingPhotosByHash[photo.iphone_hash].append(photo)
                
            for photoData in photosData:
                photoData = self.jsonDictToSimple(photoData)
                photoData["bulk_batch_key"] = batchKey

                photo = self.simplePhotoSerializer(photoData)

                self.populateExtraData(photo)

                # If we see that this photo's hash already exists then 
                if photo.iphone_hash in existingPhotosByHash:
                    if len(existingPhotosByHash[photo.iphone_hash]) == 0:
                        logger.error("Trying to deal with a dup for photo with hash %s but my list is 0" % photo.iphone_hash)
                    else:
                        existingPhoto = existingPhotosByHash[photo.iphone_hash][0]
                        existingPhotosByHash[photo.iphone_hash].remove(existingPhoto)
                        existingPhoto.file_key = photo.file_key
                        existingPhoto.install_num = user.install_num

                        logger.debug("Uploaded photo found with same hash as existing, setting to id %s and filekey %s" % (existingPhoto.id, existingPhoto.file_key))
                        objsToUpdate.append(existingPhoto)
                elif photo.id:
                    objsToUpdate.append(photo)
                else:
                    objsToCreate.append(photo)
            
            # These are all the photos we're going to return back to the client, all should have ids
            allPhotos = list()

            # These are used to deal with dups that occur with photos to be created
            objsToCreateAgain = list()
            objsFoundToMatchExisting = list()

            try:
                Photo.objects.bulk_create(objsToCreate)
            except IntegrityError:
                logger.info("Got IntegrityError on bulk upload for user %s on %s photos" % (user.id, len(objsToCreate)))
                # At this point, we tried created some rows that have the same user_id - hash - file_key
                # This probably means we're dealing with a request the server already processed
                # but the client didn't get back.  So for each photo we think we should create, see if the
                # exact record (hash, file_key) exists and return that id.
                hashes = [obj.iphone_hash for obj in objsToCreate]

                existingPhotos = Photo.objects.filter(user = user, iphone_hash__in=hashes)


                for objToCreate in objsToCreate:
                    foundMatch = False
                    for photo in existingPhotos:
                        if photo.iphone_hash == objToCreate.iphone_hash and photo.file_key == objToCreate.file_key:
                            # We found an exact photo match, so just make sure we return this entry to the client
                            allPhotos.append(photo)
                            objsFoundToMatchExisting.append(photo)
                            foundMatch = True
                            logger.debug("Found match on photo %s, going to return that" % (photo.id))
                    if not foundMatch:
                        objsToCreateAgain.append(objToCreate)
                        logger.debug("Didn't find match on photo with hash %s and file_key %s, going to try to create again" % (objToCreate.iphone_hash, objToCreate.file_key))

                # This call should now not barf because we've filtered out all the existing photos
                Photo.objects.bulk_create(objsToCreateAgain)

            # Only want to grab stuff from the last 60 seconds since bulk_batch_key could repeat
            dt = datetime.datetime.now() - datetime.timedelta(seconds=60)
            createdPhotos = list(Photo.objects.filter(bulk_batch_key = batchKey).filter(updated__gt=dt))

            allPhotos.extend(createdPhotos)
            
            # Now bulk update photos that already exist, this could happen during re-install
            if len(objsToUpdate) > 0:
                Photo.bulkUpdate(objsToUpdate, ['file_key', 'install_num'])
                # Best to just do a fresh fetch from the db
                objsToUpdate = Photo.objects.filter(id__in=Photo.getIds(objsToUpdate))
                allPhotos.extend(objsToUpdate)


            # Now that we've created the images in the db, we need to deal with any uploaded images
            #   and fill in any EXIF data (time_taken, gps, etc)
            if len(allPhotos) > 0:
                logger.info("Successfully created %s entries in db, had %s existing, matched up %s and had to create a second time %s ... now processing photos" % (len(createdPhotos), len(objsToUpdate), len(objsFoundToMatchExisting), len(objsToCreateAgain)))

                # This will move the uploaded image over to the filesystem, and create needed thumbs
                numImagesProcessed = image_util.handleUploadedImagesBulk(request, allPhotos)

                if numImagesProcessed > 0:
                    # These are all the fields that we might want to update.  List of the extra fields from above
                    # TODO(Derek):  Probably should do this more intelligently
                    Photo.bulkUpdate(allPhotos, ["full_filename", "thumb_filename"])
                    logger.info("Doing another update for created photos because %s photos had images" % (numImagesProcessed))
            else:
                logger.error("For some reason got back 0 photos created.  Using batch key %s at time %s", batchKey, dt)
            
            response = [model_to_dict(photo) for photo in allPhotos]

            logger.info("Successfully processed %s photos for user %s" % (len(response), user.id))
            return HttpResponse(json.dumps(response, cls=api_util.DuffyJsonEncoder), content_type="application/json", status=201)
        else:
            logger.error("Got request with no bulk_photos, returning 400")
            return HttpResponse(json.dumps({"bulk_photos": "Missing key"}), content_type="application/json", status=400)


class BulkCreateModelMixin(CreateModelMixin):
    def chunks(self, l, n):
        """ Yield successive n-sized chunks from l.
        """
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    batchSize = 1000

    """
        Return back all new objects, filtering out existing if they already exist
        based on the unique fields
    """
    def getNewObjects(self, objects, model):
        newObjects = list()
        for obj in objects:
            result = self.fetchWithUniqueKeys(obj)
            if not result:
                newObjects.append(obj)

        return newObjects
        
    """
    Either create a single or many model instances in bulk by using the
    Serializer's ``many=True`` ability from Django REST >= 2.2.5.

    .. note::
        This mixin uses the same method to create model instances
        as ``CreateModelMixin`` because both non-bulk and bulk
        requests will use ``POST`` request method.

    Pulled from: https://github.com/miki725/django-rest-framework-bulk
    """

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.DATA)

        model = self.model
        if serializer.is_valid():
            objects = serializer.object[serializer.bulk_key]
            
            [self.pre_save(obj) for obj in objects]

            results = list()
            for chunk in self.chunks(objects, self.batchSize):

                batchKey = randint(1,10000)
                for obj in chunk:
                    obj.bulk_batch_key = batchKey

                try:
                    model.objects.bulk_create(chunk)
                except IntegrityError:
                    newObjects = self.getNewObjects(chunk, model)
                    model.objects.bulk_create(newObjects)

                # Only want to grab stuff from the last 10 seconds since bulk_batch_key could repeat
                dt = datetime.datetime.now() - datetime.timedelta(seconds=10)
                results.extend(model.objects.filter(bulk_batch_key = batchKey).filter(added__gt=dt))

            serializer.object[serializer.bulk_key] = results
            [self.post_save(obj, created=True) for obj in serializer.object[serializer.bulk_key]]
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

"""
    Used to do a fast bulk update with one write to the database
"""
class BulkCreateAPIView(BulkCreateModelMixin,
                        GenericAPIView):
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)



class ContactEntryBulkAPI(BulkCreateAPIView):
    model = ContactEntry
    lookup_field = 'id'
    serializer_class = BulkContactEntrySerializer

    re_pattern = re.compile(u'[^\u0000-\uD7FF\uE000-\uFFFF]', re.UNICODE)

    """
        Clean up the phone number and set it.  Should only be one number per entry

        TODO(Derek): Can this be combined with StrandInviteBulkAPI?
    """
    def pre_save(self, obj):
        foundMatch = False      
        for match in phonenumbers.PhoneNumberMatcher(obj.phone_number, "US"):
            foundMatch = True
            obj.phone_number = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)

        if not foundMatch:
            logger.info("Parse error for contact entry")
            obj.skip = True

        # This will filter out 3-byte and up unicode strings.
        obj.name = self.re_pattern.sub(u'\uFFFD', obj.name) 

"""
   Strand invite API
"""
class StrandInviteBulkAPI(BulkCreateAPIView):
    model = StrandInvite
    lookup_field = 'id'
    serializer_class = BulkStrandInviteSerializer

    def fetchWithUniqueKeys(self, obj):
        try:
            return self.model.objects.get(strand_id=obj.strand_id, user_id=obj.user_id, phone_number=obj.phone_number)
        except self.model.DoesNotExist:
            return None

    """
        Clean up the phone number and set it.  Should only be one number per entry

        TODO(Derek): Can this be combined with ContactEntryBulkAPI?
    """
    def pre_save(self, strandInvite):
        logger.info("Doing a StrandInvite bulk update for user %s of strand %s and number %s" % (strandInvite.user, strandInvite.strand, strandInvite.phone_number))
        foundMatch = False      
        for match in phonenumbers.PhoneNumberMatcher(strandInvite.phone_number, "US"):
            foundMatch = True
            strandInvite.phone_number = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)

        if not foundMatch:
            logger.info("Parse error for Strand Invite")
            strandInvite.skip = True
        else:
            # Found a valid phone number, now lets see if we can find a valid user for that
            try:
                user = User.objects.get(phone_number=strandInvite.phone_number, product_id=2)
                strandInvite.invited_user = user
            except User.DoesNotExist:
                logger.debug("Looked for %s but didn't find matching user" % (strandInvite.phone_number))

class RetrieveUpdateDestroyStrandInviteAPI(RetrieveUpdateDestroyAPIView):
    def post_save(self, strandInvite, created):
        if strandInvite.accepted_user_id:
            oldActions = list(Action.objects.filter(user=strandInvite.accepted_user, strand=strandInvite.strand).order_by("-added"))
            action = Action(user=strandInvite.accepted_user, strand=strandInvite.strand, action_type=constants.ACTION_TYPE_JOIN_STRAND)
            action.save()

            # Run through old actions to see if we need to change the timing of the join (incase the "add"
            #    action happened first).  Also remove if any old ones exist
            for oldAction in oldActions:
                # Can't join a strand more than once, just do a quick check for that
                if oldAction.action_type == action.action_type and oldAction.user == action.user:
                    action.delete()

            FriendConnection.addNewConnections(strandInvite.accepted_user, strandInvite.strand.users.all())
"""
    REST interface for creating new Actions.

    Use a custom overload of the create method so we don't double create likes
"""
class CreateActionAPI(CreateAPIView):
    def post(self, request):
        serializer = self.get_serializer(data=request.DATA, files=request.FILES)

        if serializer.is_valid():
            obj = serializer.object

            # if it's a comment, then allow multiple on the same photo
            if (obj.action_type == constants.ACTION_TYPE_COMMENT):
                for user in obj.strand.users.all():
                    if user.id != obj.user_id:
                        msg = "%s: %s" % (obj.user.display_name, obj.text)
                        logger.debug("going to send %s to user id %s" % (msg, user.id))
                        customPayload = {'strand_id': obj.strand_id, 'id': obj.photo_id}
                        notifications_util.sendNotification(user, msg, constants.NOTIFICATIONS_PHOTO_COMMENT, customPayload)

                return super(CreateActionAPI, self).post(request)
            elif (obj.action_type == constants.ACTION_TYPE_FAVORITE):
                if obj.photo.user_id != obj.user_id:
                        msg = "%s just liked your photo" % (obj.user.display_name)
                        logger.debug("going to send %s to user id %s" % (msg, obj.photo.user_id))
                        customPayload = {'strand_id': obj.strand_id, 'id': obj.photo_id}
                        notifications_util.sendNotification(obj.photo.user, msg, constants.NOTIFICATIONS_PHOTO_FAVORITED_ID, customPayload)

                results = Action.objects.filter(photo_id=obj.photo_id, strand_id=obj.strand_id, user_id=obj.user_id, action_type=obj.action_type)

                if len(results) > 0:
                    serializer = self.get_serializer(results[0])
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                else:
                    return super(CreateActionAPI, self).post(request)

        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RetrieveUpdateUserAPI(RetrieveUpdateAPIView):
    def pre_save(self, user):
        if self.request.DATA['build_id'] and self.request.DATA['build_number']:
            # if last_build_info is empty or if either build_id or build_number is not in last_build_info
            #    update last_build_info
            buildId = self.request.DATA['build_id']
            buildNum = self.request.DATA['build_number']
            if ((not user.last_build_info) or 
                buildId not in user.last_build_info or 
                str(buildNum) not in user.last_build_info):
                user.last_build_info = "%s-%s" % (buildId, buildNum)
                logger.info("Build info updated to %s for user %s" % (user.last_build_info, user.id))

def updateStrandWithCorrectMetadata(strand, created):
    changed = False
    photos = strand.photos.all()
    for photo in photos:
        if photo.time_taken > strand.last_photo_time:
            strand.last_photo_time = photo.time_taken
            changed = True

        if photo.time_taken < strand.first_photo_time:
            strand.first_photo_time = photo.time_taken
            changed = True

    if len(photos) == 0 and created:
        if strand.created_from_id:
            createdFromStrand = Strand.objects.get(id=strand.created_from_id)
            strand.first_photo_time = createdFromStrand.first_photo_time
            strand.last_photo_time = createdFromStrand.last_photo_time
            strand.location_point = createdFromStrand.location_point
            strand.location_city = createdFromStrand.location_city
            
            createNeighborRowsToNewStrand(strand, createdFromStrand)

            # This is used to mark the private strand that we've evaluated it and created a request/invite
            # from it
            createdFromStrand.suggestible = False
            createdFromStrand.save()

            changed = True
        else:
            logger.error("Tried to update a strand with 0 photos and not times set but didn't have created_from_id")
    return changed

# Add in strand Neighbor entries for all the private strands the created from one had
#  to the new public one
def createNeighborRowsToNewStrand(strand, privateStrand):
    newNeighbors = list()
    
    strandNeighbors = StrandNeighbor.objects.select_related().filter(Q(strand_1 = privateStrand) | Q(strand_2 = privateStrand))
    for strandNeighbor in strandNeighbors:
        if strandNeighbor.strand_2_id == privateStrand.id:
            # This means that the strand_1 in the neighbor is the one we want to use in the new Neighbor

            # The newly created strand will always have the higher id since it was just created
            newNeighbors.append(StrandNeighbor(strand_1=strandNeighbor.strand_1, strand_1_user=strandNeighbor.strand_1_user, strand_1_private=strandNeighbor.strand_1_private, strand_2=strand, strand_2_user=strand.user, strand_2_private=strand.private))
        else:
            # This means that strand_2 is the entry we want to copy...but it could be a strand neighbor or a user neighbor
            if strandNeighbor.strand_2:
                newNeighbors.append(StrandNeighbor(strand_1=strandNeighbor.strand_2, strand_1_user=strandNeighbor.strand_2_user, strand_1_private=strandNeighbor.strand_2_private, strand_2=strand, strand_2_user=strand.user, strand_2_private=strand.private))
            else:
                # This is a user neighbor so 
                newNeighbors.append(StrandNeighbor(strand_1=strand, strand_1_user=strand.user, strand_1_private=strand.private, strand_2_user=strandNeighbor.strand_2_user))

    if len(newNeighbors) > 0:
        strands_util.updateOrCreateStrandNeighbors(newNeighbors)
        logger.info("Wrote out or updated %s strand neighbor rows connecting neighbors of %s to new strand %s" % (len(newNeighbors), privateStrand.id, strand.id))


"""
    REST interface for creating and editing strands

    Use a custom overload of the create method so we don't double create likes
"""
class CreateStrandAPI(CreateAPIView):
    def pre_save(self, strand):
        if 'photos' in self.request.DATA:
            self.request.DATA['photos'] = list(set(self.request.DATA['photos']))
        self.request.DATA['users'] = list(set(self.request.DATA['users']))

    def post_save(self, strand, created):
        if created:
            changed = updateStrandWithCorrectMetadata(strand, created)
            if changed:
                logger.debug("Updated strand %d with new times" % (strand.id))
                strand.save()

            # Now we want to create the "Added photos to a strand" Action
            try:
                user = User.objects.get(id=self.request.DATA['user_id'])
            except User.DoesNotExist:
                raise ParseError('User not found')

            if strand.private == False:
                action = Action(user=user, strand=strand, action_type=constants.ACTION_TYPE_CREATE_STRAND)
                action.save()
                action.photos = strand.photos.all()

            # Created from is the private strand of the user.  We now want to hide it from view

            # Go through all the private strands that have any photos we're contributing
            #   and mark them as such
            if 'photos' in self.request.DATA:
                privateStrands = Strand.objects.filter(photos__id__in=self.request.DATA['photos'], private=True, user=user)
                for privateStrand in privateStrands:
                    privateStrand.suggestible = False
                    privateStrand.contributed_to_id = strand.id
                    privateStrand.save()

                    createNeighborRowsToNewStrand(strand, privateStrand)
                    
            logger.info("Created new strand %s with users %s and photos %s" % (strand.id, strand.users.all(), strand.photos.all()))
            
class RetrieveUpdateDestroyStrandAPI(RetrieveUpdateDestroyAPIView):
    def pre_save(self, strand):
        # Don't need to explicity save here since this is pre_save
        updateStrandWithCorrectMetadata(strand, False)

        # Now we want to create the "Added photos to a strand" Action
        try:
            user = User.objects.get(id=self.request.DATA['user_id'])
        except User.DoesNotExist:
            raise ParseError('User not found')

        currentPhotoIds = Photo.getIds(strand.photos.all())
        currentUserIds = User.getIds(strand.users.all())

        if 'photos' in self.request.DATA:
            # Find the photo ids that are in the post data but not in the strand
            newPhotoIds = list()
            for photoId in self.request.DATA['photos']:
                if photoId not in currentPhotoIds:
                    newPhotoIds.append(photoId)

            newPhotoIds = list(set(newPhotoIds))

            self.request.DATA['photos'] = list(set(self.request.DATA['photos']))
        self.request.DATA['users'] = list(set(self.request.DATA['users']))

        if len(newPhotoIds) > 0:
            # Go through all the private strands that have any photos we're contributing
            #   and mark them as such
            privateStrands = Strand.objects.filter(photos__id__in=newPhotoIds, private=True, user=user)

            for privateStrand in privateStrands:
                privateStrand.suggestible = False
                privateStrand.contributed_to_id = strand.id
                privateStrand.save()

            newPhotos = Photo.objects.filter(id__in=newPhotoIds).order_by('time_taken')

            action = Action(user=user, strand=strand, photo_id=newPhotos[0].id, action_type=constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND)
            action.save()
            action.photos = newPhotoIds

        # go through all action posts from this user and make sure they're up to date
        addPhotoActions = Action.objects.filter(user=user, strand=strand).filter(Q(action_type=constants.ACTION_TYPE_ADD_PHOTOS_TO_STRAND) | Q(action_type=constants.ACTION_TYPE_CREATE_STRAND))

        for action in addPhotoActions:
            cleanPhotoIds = list()
            for photo in action.photos.all():
                if photo.id in self.request.DATA['photos']:
                    cleanPhotoIds.append(photo.id)

            action.photos = cleanPhotoIds

            if len(cleanPhotoIds) == 0:
                action.delete()
            else:
                action.save()

    def post_save(self, strand, created):
        if len(strand.photos.all()) == 0:
            strand.delete()


