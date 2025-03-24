import os
import json
import datetime
import logging

from django.contrib.gis.db import models
from django.template.defaultfilters import escape
from django.db.models import Q
from django.core.urlresolvers import reverse
from django.db.models.signals import pre_delete, post_save
from django.dispatch import receiver
from django.db.models.query import QuerySet
from django.db import IntegrityError

from phonenumber_field.modelfields import PhoneNumberField
from uuidfield import UUIDField

from peanut.settings import constants

from common import bulk_updater

from ios_notifications.models import Notification

logger = logging.getLogger(__name__)
		

class CompressedTextField(models.TextField):
	"""
	model Fields for storing text in a compressed format (bz2 by default)
	"""
	__metaclass__ = models.SubfieldBase

	def to_python(self, value):
		if not value:
			return value

		try:
			return value.decode('base64').decode('bz2').decode('utf-8')
		except Exception:
			return value

	def get_prep_value(self, value):
		if not value:
			return value

		try:
			value.decode('base64')
			return value
		except Exception:
			try:
				tmp = value.encode('utf-8').encode('bz2').encode('base64')
			except Exception:
				return value
			else:
				if len(tmp) > len(value):
					return value

				return tmp
				
# Create your models here.
class User(models.Model):
	uuid = UUIDField(auto=True)
	display_name = models.CharField(max_length=100)
	phone_id = models.CharField(max_length=100, null=True)
	phone_number = PhoneNumberField(null=True, db_index=True)
	auth_token = models.CharField(max_length=100, null=True)
	product_id = models.IntegerField(default=2)
	device_token = models.TextField(null=True)
	last_location_point = models.PointField(null=True)
	last_location_accuracy = models.IntegerField(null=True)
	last_location_timestamp = models.DateTimeField(null=True)
	last_photo_timestamp = models.DateTimeField(null=True)
	last_photo_update_timestamp = models.DateTimeField(null=True)
	last_checkin_timestamp = models.DateTimeField(null=True)
	first_run_sync_timestamp = models.DateTimeField(null=True)
	first_run_sync_count = models.IntegerField(null=True)
	first_run_sync_complete = models.BooleanField(default=False)
	invites_remaining = models.IntegerField(default=5)
	invites_sent = models.IntegerField(default=0)
	api_cache_private_strands_dirty = models.BooleanField(default=True)
	last_build_info = models.CharField(max_length=100, null=True)
	last_actions_list_request_timestamp = models.DateTimeField(null=True)
	install_num = models.IntegerField(default=0)
	has_sms_authed = models.BooleanField(default=0)
	bulk_batch_key = models.IntegerField(null=True, db_index=True)
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'photos_user'
		unique_together = (("phone_id", "product_id"), ("phone_number", "product_id"))

	# You MUST use GeoManager to make Geo Queries
	objects = models.GeoManager()

	"""
		Returns back the full localfile path where the user's photos are located
		So:  /home/blah/1/
	"""
	def getUserDataPath(self):
		return os.path.join(constants.PIPELINE_LOCAL_BASE_PATH, self.getUserDataId())

	def getUserDataId(self):
		return str(self.uuid)

	def photos_info(self):
		photoCount = self.photo_set.count()

		if photoCount == 1:
			return "1 photo"
		else:
			return "%s photos" % (photoCount)

	def private_strands(self):
		strands = self.strand_set.filter(private=True)

		photoCount = 0
		for strand in strands:
			photoCount += strand.photos.count()

		if len(strands) == 1:
			return "1 strand"
		else:
			return "%s strands (%s photos)" % (len(strands), photoCount)

	def shared_strands(self):
		strandCount = self.strand_set.filter(private=False).count()

		if strandCount == 1:
			return "1 strand"
		else:
			return "%s strands" % (strandCount)

	def missingPhotos(self):
		strands = self.strand_set.filter(private=True)

		photosInStrands = list()
		[photosInStrands.extend(strand.photos.all()) for strand in strands]

		links = list()
		for photo in self.photo_set.all():
			if photo not in photosInStrands:
				links.append('<a href="%s">%s</a>' % (reverse("admin:common_photo_change", args=(photo.id,)) , escape(photo)))

		return ', '.join(links)
	missingPhotos.allow_tags = True
	missingPhotos.short_description = "Missing photos"

	@classmethod
	def getIds(cls, objs):
		ids = list()
		for obj in objs:
			ids.append(obj.id)

		return ids

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)

	def __unicode__(self):
		if self.product_id == 0:
			productStr = "Arbus"
		else:
			productStr = "Strand"

		if self.phone_number:
			return "(%s - %s) %s - %s" % (self.id, productStr, self.display_name, self.phone_number)
		else:
			return "(%s - %s) %s - %s" % (self.id, productStr, self.display_name, self.phone_id)			

@receiver(pre_delete, sender=User, dispatch_uid='user_delete_signal')
def delete_empty_strands(sender, instance, using, **kwargs):
	user = instance
	strands = user.strand_set.all()
	for strand in strands:
		logger.debug("Deleting empty strand %s" % (strand.id))
		if strand.users.count() == 1 and strand.users.all()[0].id == user.id:
			strand.delete()

class Photo(models.Model):
	uuid = UUIDField(auto=True)
	user = models.ForeignKey(User)
	orig_filename = models.CharField(max_length=100, null=True)
	full_filename = models.CharField(max_length=100, null=True)
	thumb_filename = models.CharField(max_length=100, null=True, db_index=True)
	metadata = models.CharField(max_length=10000, null=True)
	full_width = models.IntegerField(null=True)
	full_height = models.IntegerField(null=True)
	location_data = models.TextField(null=True)
	location_city =  models.CharField(max_length=1000, null=True)
	location_point = models.PointField(null=True, db_index=True)
	location_accuracy_meters = models.IntegerField(null=True)
	twofishes_data = models.TextField(null=True)
	iphone_faceboxes_topleft = models.TextField(null=True)
	iphone_hash = models.CharField(max_length=100, null=True)
	is_local = models.BooleanField(default=1)
	classification_data = models.TextField(null=True)
	overfeat_data = models.TextField(null=True)
	faces_data = models.TextField(null=True)
	time_taken = models.DateTimeField(null=True, db_index=True)
	local_time_taken = models.DateTimeField(null=True)
	clustered_time = models.DateTimeField(null=True)
	neighbored_time = models.DateTimeField(null=True)
	strand_evaluated = models.BooleanField(default=False, db_index=True)
	strand_needs_reeval = models.BooleanField(default=False, db_index=True)
	notification_evaluated = models.BooleanField(default=False, db_index=True)
	notification_sent = models.DateTimeField(null=True)
	taken_with_strand = models.BooleanField(default=False)
	saved_with_swap = models.BooleanField(default=False)
	file_key = models.CharField(max_length=100, null=True)
	bulk_batch_key = models.IntegerField(null=True, db_index=True)
	product_id = models.IntegerField(default=2, null=True, db_index=True)
	install_num = models.IntegerField(default=0)
	is_dup = models.BooleanField(default=False)
	added = models.DateTimeField(auto_now_add=True, db_index=True)
	updated = models.DateTimeField(auto_now=True, db_index=True)

	 # You MUST use GeoManager to make Geo Queries
	objects = models.GeoManager()

	class Meta:
		db_table = 'photos_photo'
		index_together = ('iphone_hash', 'user')
		unique_together = ('user', 'iphone_hash', 'file_key')

	def __unicode__(self):
		return str(self.id)

	def getUserDataId(self):
		return str(self.uuid)
			
	"""
		Look to see from the iphone's location data if there's a city present
		TODO(derek):  Should this be pulled out to its own table?
	"""
	def getLocationCity(self, locationJson):
		if (locationJson):
			locationData = json.loads(locationJson)

			if ('address' in locationData):
				address = locationData['address']
				if ('City' in address):
					city = address['City']
					return city
		return None

	def save(self, *args, **kwargs):
		city = self.getLocationCity(self.location_data)
		if (city):
			self.location_city = city
		
		models.Model.save(self, *args, **kwargs)

	"""
		Returns back just the filename for the thumbnail.
		So if:  /home/blah/1/1234-thumb-156.jpg
		Will return:  1234-thumb-156.jpg

		This is used as a stopgap, the db also has this name
	"""
	def getDefaultThumbFilename(self):
		return self.getUserDataId() + "-thumb-" + str(constants.THUMBNAIL_SIZE) + '.jpg'

	"""
		Returns back the full localfile path of the thumb
		If the file was moved though this could be different from the default
		So:  /home/blah/1/1234-thumb-156.jpg
	"""
	def getThumbPath(self):
		if self.thumb_filename:
			return os.path.join(self.user.getUserDataPath(), self.thumb_filename)
		else:
			return None

	"""
		Returns back the full localfile path of the thumb
		So:  /home/blah/1/1234-thumb-156.jpg
	"""
	def getDefaultThumbPath(self):
		return os.path.join(self.user.getUserDataPath(), self.getDefaultThumbFilename())

	"""
		Returns back just the filename for the fullsize image.
		So if:  /home/blah/1/1234.jpg
		Will return:  1234.jpg

		This is used as a stopgap, the db also has this name
	"""
	def getDefaultFullFilename(self):
		baseWithoutExtension, fileExtension = os.path.splitext(self.orig_filename)
		fullFilename = self.getUserDataId() + fileExtension

		return fullFilename

	"""
		Returns back the full localfile path of the full res image
		If the file was moved though this could be different from the default
		So:  /home/blah/1/1234.jpg
	"""
	def getFullPath(self):
		if self.full_filename:
			return os.path.join(self.user.getUserDataPath(), self.full_filename)
		else:
			return None

	"""
		Returns back the default path for a new full res image
		So:  /home/blah/1/1234.jpg
	"""
	def getDefaultFullPath(self):
		return os.path.join(self.user.getUserDataPath(), self.getDefaultFullFilename())


	"""
		Returns the URL path (after the port) of the image.  Hardcoded for now but maybe change later
	"""
	def getFullUrlImagePath(self):
		if self.full_filename:
			return "/%s/%s" % (self.user.getUserDataId(), self.full_filename) 
		else:
			return ""

	"""
		Returns the URL path (after the port) of the image.  Hardcoded for now but maybe change later
	"""
	def getThumbUrlImagePath(self):
		if self.thumb_filename:
			return "/%s/%s" % (self.user.getUserDataId(), self.thumb_filename) 
		else:
			return ""

	def photoHtml(self):
		if self.thumb_filename:
			return "<img src='%s%s'></img>" % (constants.AWS_IMAGES_PATH, self.getThumbUrlImagePath())
		if self.full_filename:
			return "<img src='%s%s'></img>" % (constants.AWS_IMAGES_PATH, self.getFullUrlImagePath())
		else:
			return "No image"
	photoHtml.allow_tags = True
	photoHtml.short_description = "Photo"

	def strandListHtml(self):
		links = list()
		for strand in self.strand_set.all():
			links.append('<a href="%s">%s</a>' % (reverse("admin:common_strand_change", args=(strand.id,)) , escape(strand)))
		return ', '.join(links)	

	strandListHtml.allow_tags = True
	strandListHtml.short_description = "Strands"


	def private_strands(self):
		strandCount = self.strand_set.filter(private=True).count()

		return "%s" % (strandCount)

	def shared_strands(self):
		strandCount = self.strand_set.filter(private=False).count()

		return "%s" % (strandCount)

	"""
		Returns the URL path (after the port) of the image.  Hardcoded for now but maybe change later
	"""
	def getThumbUrlImagePath(self):
		if self.thumb_filename:
			return "/%s/%s" % (self.user.getUserDataId(), self.thumb_filename)
		else:
			return ""

	def getUserDisplayName(self):
		return self.user.display_name

	def delete(self):
		strands = self.strand_set.all()
		for strand in strands:
			if strand.photos.count() == 1 and strand.photos.all()[0].id == self.id:
				strand.delete()
				
		super(Photo, self).delete()
		
	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)

	@classmethod
	def getPhotosIds(cls, photos):
		ids = list()
		for photo in photos:
			ids.append(photo.id)

		return ids

	@classmethod
	def getIds(cls, objs):
		return [obj.id for obj in objs]
	
	def __eq__(self, other):
		# Apparently django is sending different types of objects as 'other'.  Sometimes its an object
		# and sometimes its an id
		try:
			return self.id == other['id']
		except TypeError:
			return self.id == other.id


"""
	Originally created to deal with SolrPhotos and DB photos which were different
	Might want to move soon though, not gaining a lot
"""
class SimplePhoto:
	id = None
	time_taken = None
	user = None
	display_name = None

	solrPhoto = None
	dbPhoto = None

	def serialize(self):
		return {'id' : self.id,
				'time_taken' : self.time_taken,
				'user' : self.user}
		
	def isDbPhoto(self):
		if self.dbPhoto:
			return True

	def getDbPhoto(self):
		return self.dbPhoto

	def __init__(self, solrOrDbPhoto):
		if hasattr(solrOrDbPhoto, 'photoId'):
			# This is a solr photo
			self.solrPhoto = solrOrDbPhoto

			self.id = self.solrPhoto.photoId
			self.time_taken = self.solrPhoto.timeTaken
			self.user = self.solrPhoto.userId
		else:
			# This is a database photo
			self.dbPhoto = solrOrDbPhoto

			self.id = self.dbPhoto.id
			self.time_taken = self.dbPhoto.time_taken
			self.user = self.dbPhoto.user_id
			#self.display_name = self.dbPhoto.user.display_name

			

class Classification(models.Model):
	photo = models.ForeignKey(Photo)
	user = models.ForeignKey(User)
	class_name = models.CharField(max_length=100)
	rating = models.FloatField()

	class Meta:
		db_table = 'photos_classification'

	def __unicode__(self): 
		return str(self.photo.id) + " " + self.class_name

class Similarity(models.Model):
	photo_1 = models.ForeignKey(Photo, related_name="photo_1")
	photo_2 = models.ForeignKey(Photo, related_name="photo_2")
	user = models.ForeignKey(User)
	similarity = models.IntegerField()

	class Meta:
		unique_together = ("photo_1", "photo_2")
		db_table = 'photos_similarity'

	def __unicode__(self):
		return '{0}, {1}, {2}'.format(self.photo_1.id, self.photo_2.id, self.similarity)

class NotificationLog(models.Model):
	user = models.ForeignKey(User)
	phone_number = PhoneNumberField(null=True, db_index=True)
	device_token = models.TextField(null=True)
	msg = models.TextField(null=True)
	msg_type = models.IntegerField(db_index=True)
	custom_payload = models.TextField(null=True)
	metadata = models.TextField(null=True)
	# Not used, probably can remove at some point
	apns = models.IntegerField(null=True)
	result = models.IntegerField(db_index=True, null=True)
	added = models.DateTimeField(auto_now_add=True, db_index=True)
	updated = models.DateTimeField(auto_now=True, db_index=True)
	

	class Meta:
		db_table = 'strand_notification_log'


	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)
		
	def __unicode__(self):
		return "%s %s %s %s" % (self.user_id, self.id, self.device_token, self.apns)

class SmsAuth(models.Model):
	phone_number =  models.CharField(max_length=50, db_index=True)
	access_code = models.IntegerField()
	user_created = models.ForeignKey(User, null=True)
	added = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = 'strand_sms_auth'

	def __unicode__(self):
		return "%s %s %s" % (self.id, self.phone_number, self.added)

class DuffyNotification(Notification):
	content_available = models.IntegerField(null=True)

	"""
		Override from main ios_notifications library
	"""
	@property
	def payload(self):
		aps = {}
		if self.message:
			aps['alert'] = self.message
		else:
			aps['alert'] = ''

		if self.badge is not None:
			aps['badge'] = self.badge

		if self.sound:
			aps['sound'] = self.sound
				
		if self.content_available:
			aps['content-available'] = self.content_available
			
		message = {'aps': aps}
		extra = self.extra
		if extra is not None:
			message.update(extra)
		payload = json.dumps(message, separators=(',', ':'))
		return payload

class ContactEntry(models.Model):
	user = models.ForeignKey(User, db_index=True)
	name = models.CharField(max_length=100)
	phone_number = models.CharField(max_length=128, db_index=True)
	evaluated = models.BooleanField(db_index=True, default=False)
	skip = models.BooleanField(db_index=True, default=False)
	contact_type = models.CharField(max_length=30, null=True)
	bulk_batch_key = models.IntegerField(null=True, db_index=True)
	added = models.DateTimeField(auto_now_add=True, db_index=True)
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'strand_contacts'

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)

class Strand(models.Model):
	first_photo_time = models.DateTimeField(db_index=True, null=True)
	last_photo_time = models.DateTimeField(db_index=True, null=True)
	
	# These should come from the first photo
	location_city =  models.CharField(max_length=1000, null=True)
	location_point = models.PointField(null=True, db_index=True)
	
	photos = models.ManyToManyField(Photo)
	users = models.ManyToManyField(User)
	private = models.BooleanField(db_index=True, default=False)
	user = models.ForeignKey(User, null=True, related_name="owner", db_index=True)
	product_id = models.IntegerField(default=2, db_index=True)

	neighbor_evaluated = models.BooleanField(db_index=True, default=True)

	# This is the id of the private Strand that created this.  Not doing ForeignKey because
	#   django isn't good with recusive
	created_from_id = models.IntegerField(null=True)

	# This is the id of the public strand that this private strand swapped photos with
	contributed_to_id = models.IntegerField(null=True)

	suggestible = models.BooleanField(default=True)

	swap_converted = models.BooleanField(default=False)

	cache_dirty = models.BooleanField(default=True)
	
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)	

	def __unicode__(self):
		return str(self.id)
		
	def user_info(self):
		names = [str(user) for user in self.users.all()]
		return " & ".join(names)

	def photo_info(self):
		photoCount = self.photos.count()

		if photoCount == 1:
			return "1 photo"
		else:
			return "%s photos" % (photoCount)
		
	def sharing_info(self):
		if self.private:
			return "Private"
		else:
			return "Shared"

	def photos_link(self):
		photos = self.photos.all()

		links = list()
		for photo in photos:
			links.append('<a href="%s">%s</a>' % (reverse("admin:common_photo_change", args=(photo.id,)) , escape(photo)))
		return ', '.join(links)		
	photos_link.allow_tags = True
	photos_link.short_description = "Photos"

	def users_link(self):
		users = self.users.all()

		links = list()
		for user in users:
			links.append('<a href="%s">%s</a>' % (reverse("admin:common_user_change", args=(user.id,)) , escape(user)))
		return ', '.join(links)

	users_link.allow_tags = True
	users_link.short_description = "Users"

	def strand_neighbors_link(self):
		neighbors = StrandNeighbor.objects.filter(Q(strand_1_id=self.id) | Q(strand_2_id=self.id))
		links = list()
		for neighbor in neighbors:
			strand = None
			if neighbor.strand_1_id == self.id:
				strand = neighbor.strand_2
			if neighbor.strand_2:
				if neighbor.strand_2_id == self.id:
					strand = neighbor.strand_1

			if strand:
				links.append('<a href="%s">%s</a>' % (reverse("admin:common_strand_change", args=(strand.id,)) , escape(strand)))
			
		return ', '.join(links)		
	strand_neighbors_link.allow_tags = True
	strand_neighbors_link.short_description = "Strand Neighbors"

	def user_neighbors_link(self):
		neighbors = StrandNeighbor.objects.select_related().filter(Q(strand_1_id=self.id) & Q(strand_2_id__isnull=True))
		links = list()
		for neighbor in neighbors:
			user = neighbor.strand_2_user
			if user.id != self.user_id:
				links.append('<a href="%s">%s</a>' % (reverse("admin:common_user_change", args=(user.id,)) , escape(user)))
			
		return ', '.join(links)		
	user_neighbors_link.allow_tags = True
	user_neighbors_link.short_description = "User Neighbors"

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)
		
	@classmethod
	def getIds(cls, objs):
		ids = list()
		for obj in objs:
			ids.append(obj.id)

		return ids

	@classmethod
	def getPhotoIds(cls, objs):
		ids = list()
		for strand in objs:
			ids.extend([x.id for x in strand.photos.all()])
		return ids

	class Meta:
		db_table = 'strand_objects'

	# You MUST use GeoManager to make Geo Queries
	objects = models.GeoManager()
	


class ShareInstance(models.Model):
	user = models.ForeignKey(User, db_index=True)
	photo = models.ForeignKey(Photo, db_index=True)
	users = models.ManyToManyField(User, related_name = "si_users")
	shared_at_timestamp = models.DateTimeField(db_index=True, null=True)
	last_action_timestamp = models.DateTimeField(db_index=True, null=True)
	bulk_batch_key = models.IntegerField(null=True)
	mtm_key = models.IntegerField(null=True)
	notification_sent = models.DateTimeField(null=True)
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)

	@classmethod
	def getIds(cls, objs):
		return doGetIds(cls, objs)

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)

	def __unicode__(self):
		return '%s | %s | %s | %s'%(self.id, self.user, self.photo, self.shared_at_timestamp)
		
	class Meta:
		db_table = 'swap_share_instance'

class StrandNeighbor(models.Model):
	strand_1 = models.ForeignKey(Strand, db_index=True, related_name = "strand_1")
	strand_1_private = models.BooleanField(db_index=True, default=False)
	strand_1_user = models.ForeignKey(User, db_index=True, null=True, related_name = "strand_1_user")

	strand_2 = models.ForeignKey(Strand, db_index=True, null=True, related_name = "strand_2")
	strand_2_private = models.BooleanField(db_index=True, default=False)
	strand_2_user = models.ForeignKey(User, db_index=True, null=True, related_name = "strand_2_user")

	distance_in_meters = models.IntegerField(null=True)
	
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)	

	def __unicode__(self):
		return str(self.id)
		
	class Meta:
		unique_together = ("strand_1", "strand_2")
		db_table = 'strand_neighbor'

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)


class FriendConnection(models.Model):
	user_1 = models.ForeignKey(User, related_name="friend_user_1", db_index=True)
	user_2 = models.ForeignKey(User, related_name="friend_user_2", db_index=True)
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ("user_1", "user_2")
		db_table = 'strand_friends'

	@classmethod
	def friendFullConnectionExists(cls, user1, user2, existingFriendConnections):
		forward = reverse = False
		for connection in existingFriendConnections:
			if connection.user_1.id == user1.id and connection.user_2.id == user2.id:
				forward = True
			if connection.user_1.id == user2.id and connection.user_2.id == user1.id:
				reverse = True
			if forward and reverse:
				return True
		return False

	@classmethod
	def friendForwardConnectionExists(cls, user1, user2, existingFriendConnections):
		for connection in existingFriendConnections:
			if connection.user_1.id == user1.id and connection.user_2.id == user2.id:
				return True

	@classmethod
	def friendReverseConnectionExists(cls, user1, user2, existingFriendConnections):
		for connection in existingFriendConnections:
			if connection.user_1.id == user2.id and connection.user_2.id == user1.id:
				return True

	@classmethod
	def addForwardConnection(cls, u1, u2):
		try:
			FriendConnection.objects.create(user_1=u1, user_2=u2)
			logger.debug("Created friend entry for user %s with user %s" % (u1.id, u2.id))
			return True
		except IntegrityError:
			logger.warning("Tried to create friend connection between %s and %s but there was one already" % (u1.id, u2.id))
			return False

	@classmethod
	def addReverseConnection(cls, u1, u2):
		try:
			FriendConnection.objects.create(user_1=u2, user_2=u1)
			logger.debug("Created friend entry for user %s with user %s" % (u1.id, u2.id))
			return True
		except IntegrityError:
			logger.warning("Tried to create friend connection between %s and %s but there was one already" % (u1.id, u2.id))
			return False

	@classmethod
	def addReverseConnections(cls, userToAddTo, users):
		existingReverseConnectionsForUserToAddTo = FriendConnection.objects.filter(user_1__in=users).filter(user_2__in=userToAddTo)

		for user in users:
			if not cls.friendReverseConnectionExists(userToAddTo, user, existingReverseConnectionsForUserToAddTo):
				cls.addReverseConnection(userToAddTo, user)

	@classmethod
	def addNewFullConnections(cls, userToAddTo, users):
		allUsers = list()
		allUsers.extend(users)
		allUsers.append(userToAddTo)
		
		existingFriendConnections = FriendConnection.objects.filter(Q(user_1__in=allUsers) | Q(user_2__in=allUsers))
		for user in users:
			if user.id == userToAddTo.id:
				continue
			if not cls.friendFullConnectionExists(user, userToAddTo, existingFriendConnections):
				cls.addForwardConnection(userToAddTo, user)
				cls.addReverseConnection(userToAddTo, user)
				
		# TODO(Derek): If thie above loop gets bad, put back in the bulk calls
		#FriendConnection.objects.bulk_create(newFriendConnections)

class Action(models.Model):
	user = models.ForeignKey(User, db_index=True)
	action_type = models.IntegerField(db_index=True)
	photo = models.ForeignKey(Photo, db_index=True, related_name = "action_photo", null=True)
	photos = models.ManyToManyField(Photo, related_name = "action_photos")
	strand = models.ForeignKey(Strand, db_index=True, null=True)
	notification_sent = models.DateTimeField(null=True)
	text = models.TextField(null=True)
	share_instance = models.ForeignKey(ShareInstance, db_index=True, null=True)
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)

	def getUserDisplayName(self):
		return self.user.display_name
	
	def getUserPhoneNumber(self):
		return self.user.phone_number

	def __unicode__(self):
		return "%s %s %s %s" % (self.user.id, self.action_type, self.strand, self.added)

	@classmethod
	def getIds(cls, objs):
		return doGetIds(cls, objs)

	class Meta:
		db_table = 'strand_action'
		index_together = ('strand', 'action_type')

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)


class ApiCache(models.Model):
	user = models.ForeignKey(User, db_index=True, unique=True)
	private_strands_data = CompressedTextField(null=True)
	private_strands_data_last_timestamp = models.DateTimeField(null=True)
	private_strands_full_last_timestamp = models.DateTimeField(null=True)
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)
	
	class Meta:
		db_table = 'strand_api_cache'


class LocationRecord(models.Model):
	user = models.ForeignKey(User, db_index=True)
	point = models.PointField(db_index=True)
	accuracy = models.IntegerField(null=True)
	timestamp = models.DateTimeField(null=True)
	neighbor_evaluated = models.BooleanField(default=False)
	added = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'strand_location_records'

	# You MUST use GeoManager to make Geo Queries
	objects = models.GeoManager()

	@classmethod
	def bulkUpdate(cls, objs, attributesList):
		doBulkUpdate(cls, objs, attributesList)

def doGetIds(cls, objs):
	ids = list()
	for obj in objs:
		ids.append(obj.id)
	return ids

def doBulkUpdate(cls, objs, attributesList):
	if not isinstance(objs, list) and not isinstance(objs, QuerySet):
		objs = [objs]

	if len(objs) == 0:
		return
		
	for obj in objs:
		obj.updated = datetime.datetime.now()

	if isinstance(attributesList, list):
		attributesList.append("updated")
	else:
		attributesList = [attributesList, "updated"]

	bulk_updater.bulk_update(objs, update_fields=attributesList)

