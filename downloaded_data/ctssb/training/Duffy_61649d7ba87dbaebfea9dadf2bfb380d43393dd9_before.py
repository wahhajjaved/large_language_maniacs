from django.shortcuts import render
from django.http import HttpResponse

from haystack.query import SearchQuerySet

from django.template import RequestContext, loader

import os, datetime
import json
from collections import OrderedDict

from photos.models import Photo, User, Classification
from photos import image_util, search_util
from .forms import ManualAddPhoto

from datetime import datetime
from dateutil.relativedelta import relativedelta

	
def manualAddPhoto(request):
	form = ManualAddPhoto()

	context = {'form' : form}
	return render(request, 'photos/manualAddPhoto.html', context)
	
def groups(request, user_id):
	try:
		user = User.objects.get(id=user_id)
	except User.DoesNotExist:
		return HttpResponse("User id " + str(user_id) + " does not exist")

	thumbnailBasepath = "/user_data/" + str(user.id) + "/"

	classifications = Classification.objects.select_related().filter(user_id = user.id)

	bucketedClasses = dict()
	photos = list()
	
	for classification in classifications:
		if classification.class_name not in bucketedClasses:
			bucketedClasses[classification.class_name] = list()
		bucketedClasses[classification.class_name].append(classification.photo)
		photos.append(classification.photo)
		

	numPhotos = len(set(photos))

	filteredBuckets = dict()

	for key, bucket in bucketedClasses.iteritems():
		if (len(bucket) > 2):
			filteredBuckets[key] = bucket

	sortedBuckets = OrderedDict(reversed(sorted(filteredBuckets.viewitems(), key=lambda x: len(x[1]))))
	
	context = {	'user' : user,
				'numPhotos': numPhotos,
				'sorted_buckets': sortedBuckets,
				'thumbnailBasepath': thumbnailBasepath}
	return render(request, 'photos/groups.html', context)


def search(request, user_id=None):
	if (user_id):
		try:
			user = User.objects.get(id=user_id)
		except User.DoesNotExist:
			return HttpResponse("User id " + str(user_id) + " does not exist")

		thumbnailBasepath = "/user_data/" + str(user.id) + "/"

		numPhotos = Photo.objects.filter(user_id = user.id).count()

		context = {	'user' : user,
					'numPhotos': numPhotos,
					'thumbnailBasepath': thumbnailBasepath}
		return render(request, 'photos/search.html', context)
	else:
		if request.method == 'GET':
			data = request.GET
		elif request.method == 'POST':
			data = request.POST

		if data.has_key('user_id'):
			userId = data['user_id']
		else:
			return HttpResponse("Please specify a userId")

		if data.has_key('count'):
			count = int(data['count'])
		else:
			count = 48

		if data.has_key('page'):
			page = int(data['page'])
		else:
			page = 1

		if data.has_key('imagesize'):
			imageSize = int(data['imagesize'])
		else:
			imageSize = 78;

		width = imageSize*2 #doubled  for retina

		try:
			user = User.objects.get(id=userId)
		except User.DoesNotExist:
			return HttpResponse("Phone id " + str(userId) + " does not exist")

		thumbnailBasepath = "/user_data/" + str(user.id) + "/"

		if data.has_key('q'):
			query = data['q']
		else:
			return HttpResponse("Please specify a query")

		setSession(request, user.id)

		(startDate, newQuery) = search_util.getNattyInfo(query)
		searchResults = search_util.solrSearch(user.id, startDate, newQuery)

		allResults = searchResults.count()
		searchResults = searchResults[((page-1)*count):(count*page)]

		photoIdToThumb = dict()
		for result in searchResults:
			photoIdToThumb[result.photoId] = image_util.imageThumbnail(result.photoFilename, width, user.id)

		start = ((page-1)*count)+1
		if (allResults > count*page):
			end = count*page
			next = True
		else:
			end = allResults
			next = False

		if (start > 1):
			previous = True
		else:
			previous = False


		context = {	'user' : user,
					'imageSize': imageSize,
					'start': start,
					'end': end,
					'resultSize': allResults,
					'next': next,
					'previous': previous,
					'searchResults': searchResults,
					'query': query,
					'page': page,
					'userId': userId,
					'thumbnailBasepath': thumbnailBasepath,
					'photoIdToThumb': photoIdToThumb}
		return render(request, 'photos/search_webview.html', context)



def gallery(request, user_id):
	try:
		user = User.objects.get(id=user_id)
	except User.DoesNotExist:
		return HttpResponse("User id " + str(user_id) + " does not exist")

	thumbnailBasepath = "/user_data/" + str(user.id) + "/"

	if request.method == 'GET':
		data = request.GET
	elif request.method == 'POST':
		data = request.POST

	if data.has_key('imagesize'):
		imageSize = int(data['imagesize'])
	else:
		imageSize = 78;

	width = imageSize*2 #doubled  for retina

	#photos = Photo.objects.filter(user_id = user.id).order_by('time_taken')
	#numPhotos = photos.count()

	photos = getPhotosSplitByMonth(request, user.id)

	#for entry in photos:
	#	image_util.imageThumbnail(entry.new_filename, width, user.id)


	context = {	'user' : user,
				'imageSize': imageSize,
				'photos': photos,
				'thumbnailBasepath': thumbnailBasepath}
	return render(request, 'photos/gallery.html', context)



def serveImage(request):

	if (request.session['userid']):
		userId = request.session['userid']
	else:
		return HttpResponse("Missing user id data")

	if request.method == 'GET':
		data = request.GET
	elif request.method == 'POST':
		data = request.POST

	if data.has_key('photo'):
		photo = data['photo']
	else:
		return HttpResponse("Please specify a photo")


	thumbnailBasepath = "/user_data/" + str(userId) + "/"

	context = {	'photo': photo,
				'thumbnailBasepath': thumbnailBasepath}
	return render(request, 'photos/serve_image.html', context)

# Helper functions

def getPhotosSplitByMonth(request, userId, threshold=None):
	#photos = Photo.objects.filter(user_id = userId).order_by('time_taken')

	if (threshold == None):
		threshold = 11

	dates = Photo.objects.datetimes('time_taken', 'month')
	photos = list()

	entry = dict()
	entry['date'] = 'Undated'
	entry['mainPhotos'] = list(Photo.objects.filter(user_id=userId).filter(time_taken=None)[:threshold])
	entry['subPhotos'] = list(Photo.objects.filter(user_id=userId).filter(time_taken=None)[threshold:])
	entry['count'] = len(entry['subPhotos'])
	photos.append(entry)

	for date in dates:
		entry = dict()
		entry['date'] = date.strftime('%b %Y')
		entry['mainPhotos'] = list(Photo.objects.filter(user_id=userId).exclude(time_taken=None).exclude(time_taken__lt=date).exclude(time_taken__gt=date+relativedelta(months=1)).order_by('time_taken')[:threshold])
		entry['subPhotos'] = list(Photo.objects.filter(user_id=userId).exclude(time_taken=None).exclude(time_taken__lt=date).exclude(time_taken__gt=date+relativedelta(months=1)).order_by('time_taken')[threshold:])
		entry['count'] = len(entry['subPhotos'])
		photos.append(entry)

	return photos

def setSession(request, userId):
	request.session['userid'] = userId



