import json
from django.core.serializers.json import DjangoJSONEncoder
from multiprocessing import Process
import uuid
import time
import boto
import requests
import cStringIO
import random
import math
import pytz
import datetime
import humanize
from PIL import Image
import os, sys

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from django.shortcuts import render

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from smskeeper.forms import UserIdForm, SmsContentForm, PhoneNumberForm, SendSMSForm
from smskeeper.models import User, Note, NoteEntry, Message, MessageMedia
from smskeeper import sms_util
from smskeeper import async

from common import api_util, natty_util
from peanut.settings import constants


def sendNoResponse():
	content = '<?xml version="1.0" encoding="UTF-8"?>\n'
	content += "<Response></Response>"
	print "Sending blank response"
	return HttpResponse(content, content_type="text/xml")

def sendNotFoundMessage(user, label, keeperNumber):
	sms_util.sendMsg(user, "Sorry, I don't have anything for %s" % label, None, keeperNumber)

def isLabel(msg):
	stripedMsg = msg.strip()
	return (' ' in stripedMsg) == False and stripedMsg.startswith("#")

def isClearLabel(msg):
	stripedMsg = msg.strip()
	tokens = msg.split(' ')
	return len(tokens) == 2 and ((isLabel(tokens[0]) and tokens[1].lower() == 'clear') or (isLabel(tokens[1]) and tokens[0].lower()=='clear'))

def isPickFromLabel(msg):
	stripedMsg = msg.strip()
	tokens = msg.split(' ')
	return len(tokens) == 2 and ((isLabel(tokens[0]) and tokens[1].lower() == 'pick') or (isLabel(tokens[1]) and tokens[0].lower()=='pick'))

def isRemindCommand(msg):
	return '#remind' in msg.lower()
	
def isListsCommand(msg):
	return msg.strip().lower() == 'show lists' or msg.strip().lower() == 'show all'

def isHelpCommand(msg):
	return msg.strip().lower() == 'huh?'

def isSendContactCommand(msg):
	return msg.strip().lower() == 'vcard'

def hasLabel(msg):
	for word in msg.split(' '):
		if isLabel(word):
			return True
	return False

def getLabel(msg):
	for word in msg.split(' '):
		if isLabel(word):
			return word
	return None

# Returns back (textWithoutLabel, label, listOfUrls)
# Text could have comma's in it, that is dealt with later
def getData(msg, numMedia, requestDict):
	# process text
	nonLabels = list()
	label = None
	for word in msg.split(' '):
		if isLabel(word):
			label = word
		else:
			nonLabels.append(word)

	# process media
	mediaUrlList = list()

	for n in range(numMedia):
		param = 'MediaUrl' + str(n)
		mediaUrlList.append(requestDict[param])
		#TODO need to store mediacontenttype as well. 

	#TODO use a separate process but probably this is not the right place to do it.
	if numMedia > 0:
		mediaUrlList = moveMediaToS3(mediaUrlList)
	return (' '.join(nonLabels), label, mediaUrlList)

def moveMediaToS3(mediaUrlList):

	conn = boto.connect_s3('AKIAJBSV42QT6SWHHGBA', '3DjvtP+HTzbDzCT1V1lQoAICeJz16n/2aKoXlyZL')
	bucket = conn.get_bucket('smskeeper')
	newUrlList = list()
	
	for mediaUrl in mediaUrlList:
		resp = requests.get(mediaUrl)
		media = cStringIO.StringIO(resp.content)

		# Upload to S3 
		keyStr = uuid.uuid4()
		key = bucket.new_key(keyStr)
		key.set_contents_from_string(media.getvalue())
		newUrlList.append('https://s3.amazonaws.com/smskeeper/'+ str(keyStr))

	return newUrlList

def htmlForNote(note):
	html = "%s:\n"%(note.label)
	entries = NoteEntry.objects.filter(note=note).order_by("added")
	if len(entries) == 0:
		html += "(empty)<br><br>"
		return html

	count = 1
	html += "<ol>\n"
	for entry in entries:
		if not entry.img_url:
			html += "<li>%s</li>"%(entry.text)
			count += 1
		else:
			html += "<img src=\"%s\" />"%(entry.img_url)
	html+= "</ol>"

	return html

def sendContactCard(user, keeperNumber):
		cardURL = "https://s3.amazonaws.com/smskeeper/Keeper.vcf"
		sms_util.sendMsg(user, '', cardURL, keeperNumber)

'''
	Gets a list of urls and generates a grid image to send back.
'''
def generateImageGridUrl(imageURLs):
	# if one url, just return that
	if len(imageURLs) == 1:
		return imageURLs[0]

	# if more than one, now setup the grid system
	imageList = list()

	imageSize = 300

	# fetch all images and resize them into imageSize x imageSize
	for imageUrl in imageURLs:
		resp = requests.get(imageUrl)
		img = Image.open(cStringIO.StringIO(resp.content))
		imageList.append(resizeImage(img, imageSize, True))


	if len(imageURLs) < 5:
		# generate an 2xn grid
		rows = int(math.ceil(float(len(imageURLs))/2.0))
		newImage = Image.new("RGB", (2*imageSize, imageSize*rows), "white")
	
		for i,image in enumerate(imageList):
			x = imageSize*(i % 2)
			y = imageSize*(i/2 % 2)
			newImage.paste(image, (x,y,x+imageSize,y+imageSize))
	else:
		# generate a 3xn grid
		rows = int(math.ceil(float(len(imageURLs))/3.0))
		newImage = Image.new("RGB", (3*imageSize, imageSize*rows), "white")

		for i,image in enumerate(imageList):
			x = imageSize*(i % 3)
			y = imageSize*(i/3 % 3)
			newImage.paste(image, (x,y,x+imageSize,y+imageSize))

	return saveImageToS3(newImage)

def dealWithAddMessage(user, msg, numMedia, keeperNumber, requestDict, sendResponse):
	text, label, media = getData(msg, numMedia, requestDict)
	note, created = Note.objects.get_or_create(user=user, label=label)

	# Text comes back without label but still has commas. Split on those here
	for entryText in text.split(','):
		entryText = entryText.strip()
		noteEntry = NoteEntry.objects.create(note=note, text=entryText)

	for entryMediaUrl in media:
		noteEntry = NoteEntry.objects.create(note=note, img_url=entryMediaUrl)

	if sendResponse:
		sms_util.sendMsg(user, "Got it", None, keeperNumber)

	return noteEntry

def dealWithRemindMessage(user, msg, keeperNumber, requestDict):
	text, label, media = getData(msg, 0, requestDict)
	startDate, newQuery = natty_util.getNattyInfo(text)
		
	msgWithLabel = newQuery + " " + label
	noteEntry = dealWithAddMessage(user, msgWithLabel, 0, keeperNumber, requestDict, False)
	if startDate:
		# Hack to assume Eastern time
		startDate = startDate + datetime.timedelta(hours=4)

		noteEntry.remind_timestamp = startDate
		noteEntry.keeper_number = keeperNumber
		noteEntry.save()

		async.processReminder.apply_async([noteEntry.id], eta=startDate)

		sms_util.sendMsg(user, "Got it. Will remind you to %s %s" % (newQuery, humanize.naturaltime(startDate)), None, keeperNumber)
	else:
		sms_util.sendMsg(user, "Got it", None, keeperNumber)
	

def dealWithFetchMessage(user, msg, numMedia, keeperNumber, requestDict):
	# This is a label fetch.  See if a note with that label exists then return
	label = msg
	try:
		note = Note.objects.get(user=user, label=label)
		clearMsg = "\n\nSend '%s clear' to clear this list."%(note.label)
		entries = NoteEntry.objects.filter(note=note).order_by("added")
		mediaUrls = list()

		if len(entries) == 0:
			sendNotFoundMessage(note.user, note.label, keeperNumber)
			return

		currentMsg = "%s:" % note.label

		count = 1
		for entry in entries:
			if entry.img_url:
				mediaUrls.extend(entry.img_url)
			else:
				newStr = str(count) + ". " + entry.text

				if entry.remind_timestamp:
					dt = entry.remind_timestamp.replace(tzinfo=None)
					newStr = "%s %s" % (newStr, naturaltime.naturaltime(dt))
				currentMsg = currentMsg + "\n " + newStr
				count += 1

		if len(mediaUrls) > 0:
			if (len(mediaUrls) > 1):
				photoPhrase = " photos"
			else:
				photoPhrase = " photo"

			currentMsg = currentMsg + "\n +" + str(len(mediaUrls)) + photoPhrase + " coming separately"

			gridImageUrl = generateImageGridUrl(mediaUrls)

			sms_util.sendMsg(note.user, currentMsg + clearMsg, None, keeperNumber)
			sms_util.sendMsg(note.user, '', gridImageUrl, keeperNumber)
		else:
			sms_util.sendMsg(note.user, currentMsg + clearMsg, None, keeperNumber)
	except Note.DoesNotExist:
		sendNotFoundMessage(user, label, keeperNumber)


def sendItemFromNote(note, keeperNumber):
	entries = NoteEntry.objects.filter(note=note).order_by("added")
	if len(entries) == 0:
		sendNotFoundMessage(user, label, keeperNumber)
		return
		
	entry = random.choice(entries)
	if entry.img_url:
		sms_util.sendMsg(note.user, "My pick for %s:"%note.label, None, keeperNumber)
		sms_util.sendMsg(note.user, entry.text, entry.img_url, keeperNumber)
	else:
		sms_util.sendMsg(note.user, "My pick for %s: %s"%(note.label, entry.text), None, keeperNumber)

def getFirstNote(user):
	notes = Note.objects.filter(user=user)
	if len(notes) > 0:
		return notes[0]
	else:
		return None

def dealWithTutorial(user, msg, numMedia, keeperNumber, requestDict):
	if user.tutorial_step == 0:
		sms_util.sendMsg(user, "Hi. I'm Keeper. I can keep track of your lists, notes, photos, etc.", None, keeperNumber)
		time.sleep(1)
		sms_util.sendMsg(user, "Let's try creating a list. Send an item you want to buy and add a hashtag. Like 'bread #grocery'", None, keeperNumber)
		user.tutorial_step = user.tutorial_step + 1
	elif user.tutorial_step == 1:
		if not hasLabel(msg):
			# They didn't send in something with a label.
			sms_util.sendMsg(user, "Actually, let's create a list first. Try 'bread #grocery'.")
		else:
			# They sent in something with a label, have them add to it
			dealWithAddMessage(user, msg, numMedia, keeperNumber, requestDict, False)
			sms_util.sendMsg(user, "Now let's add another item to your list. Don't forget to add the same hashtag '%s'" % getLabel(msg), None, keeperNumber)
			user.tutorial_step = user.tutorial_step + 1
	elif user.tutorial_step == 2:
		# They should be sending in a second add command to an existing label
		if not hasLabel(msg) or isLabel(msg):
			existingLabel = getFirstNote(user).label
			if not existingLabel:
				sms_util.sendMsg(user, "I'm borked, well done", None, keeperNumber)
				return
			sms_util.sendMsg(user, "Actually, let's add to the first list. Try 'foobar %s'." % existingLabel, None, keeperNumber)
		else:
			dealWithAddMessage(user, msg, numMedia, keeperNumber, requestDict, False)
			sms_util.sendMsg(user, "You can add items to this list anytime (including photos). To see your list, send just the hashtag '%s' to me. Give it a shot." % getLabel(msg), None, keeperNumber)
			user.tutorial_step = user.tutorial_step + 1
	elif user.tutorial_step == 3:
		# The should be sending in just a label
		existingLabel = getFirstNote(user).label
		if not existingLabel:
			sms_util.sendMsg(user, "I'm borked, well done", None, keeperNumber)
			return

		if not isLabel(msg):
			sms_util.sendMsg(user, "Actually, let's view your list. Try '%s'." % existingLabel, None, keeperNumber)
			return
			
		if not Note.objects.filter(user=user, label=msg).exists():
			sms_util.sendMsg(user, "Actually, let's view the list you already created. Try '%s'." % existingLabel, None, keeperNumber)
			return
		else:	
			dealWithFetchMessage(user, msg, numMedia, keeperNumber, requestDict)
			sms_util.sendMsg(user, "That should get you started. Send 'huh?' anytime to get help.", None, keeperNumber)
			time.sleep(1)
			sms_util.sendMsg(user, "Btw, here's an easy way to add me to your contacts.", None, keeperNumber)
			sendContactCard(user, keeperNumber)
			user.completed_tutorial = True
		
	user.save()
	
def saveImageToS3(img):
	conn = boto.connect_s3('AKIAJBSV42QT6SWHHGBA', '3DjvtP+HTzbDzCT1V1lQoAICeJz16n/2aKoXlyZL')
	bucket = conn.get_bucket('smskeeper')
	
	outIm = cStringIO.StringIO()
	img.save(outIm, 'JPEG')

	# Upload to S3 
	keyStr = "grid-" + str(uuid.uuid4())
	key = bucket.new_key(keyStr)
	key.set_contents_from_string(outIm.getvalue())
	return 'https://s3.amazonaws.com/smskeeper/'+ str(keyStr)

"""
	Does image resizes and creates a new file (JPG) of the specified size
"""
def resizeImage(im, size, crop):

	#calc ratios and new min size
	wratio = (size/float(im.size[0])) #width check
	hratio = (size/float(im.size[1])) #height check

	if (hratio > wratio):
		newSize = hratio*im.size[0], hratio*im.size[1]
	else:
		newSize = wratio*im.size[0], wratio*im.size[1]
	im.thumbnail(newSize, Image.ANTIALIAS)

	# setup the crop to size x size image
	if (crop):
		if (hratio > wratio):
			buffer = int((im.size[0]-size)/2)
			im = im.crop((buffer, 0, (im.size[0]-buffer), size))			
		else:
			buffer = int((im.size[1]-size)/2)
			im = im.crop((0, buffer, size, (im.size[1] - buffer)))
	
	im.load()
	return im

"""
	Helper method for command line interface input.  Use by:
	python
	>> from smskeeper import views
	>> views.cliMsg("+16508158274", "blah #test")
"""
def cliMsg(phoneNumber, msg):
	jsonDict = {
		"Body": msg,
	}
	processMessage(phoneNumber, msg, 0, jsonDict, "test")

"""
	Main logic for processing a message
	Pulled out so it can be called either from sms code or command line
"""
def processMessage(phoneNumber, msg, numMedia, requestDict, keeperNumber):
	try:
		user = User.objects.get(phone_number=phoneNumber)
	except User.DoesNotExist:
		user = User.objects.create(phone_number=phoneNumber)

		dealWithTutorial(user, msg, numMedia, keeperNumber, requestDict)
		return
	finally:
		Message.objects.create(user=user, msg_json=json.dumps(requestDict), incoming=True)

		
	if numMedia == 0 and isLabel(msg):
		if user.completed_tutorial:
			dealWithFetchMessage(user, msg, numMedia, keeperNumber, requestDict)
		else:
			time.sleep(1)
			dealWithTutorial(user, msg, numMedia, keeperNumber, requestDict)
	elif numMedia == 0 and isClearLabel(msg):
		try:
			label = getLabel(msg)
			note = Note.objects.get(user=user, label=label)
			note.delete()
			sms_util.sendMsg(user, "%s cleared"% (label), None, keeperNumber)
		except Note.DoesNotExist:
			sendNotFoundMessage(user, label, keeperNumber)
	elif numMedia == 0 and isPickFromLabel(msg):
		label = getLabel(msg)
		try:
			note = Note.objects.get(user=user, label=label)
			sendItemFromNote(note, keeperNumber)
		except Note.DoesNotExist:
			sendNotFoundMessage(user, label, keeperNumber)
	elif isHelpCommand(msg):
		sms_util.sendMsg(user, "You can create a list by adding #listname to any msg.\n You can retrieve all items in a list by typing just '#listname' in a message.", None, keeperNumber)
	elif isSendContactCommand(msg):
		sendContactCard(user, keeperNumber)
	elif isRemindCommand(msg):
		dealWithRemindMessage(user, msg, keeperNumber, requestDict)
	elif hasLabel(msg):
		if user.completed_tutorial:
			dealWithAddMessage(user, msg, numMedia, keeperNumber, requestDict, True)
		else:
			time.sleep(1)
			dealWithTutorial(user, msg, numMedia, keeperNumber, requestDict)
	else:
		sms_util.sendMsg(user, "Oops I need a label for that message. ex: #grocery, #tobuy, #toread. Send 'huh?' to find out more.", None, keeperNumber)


#
# Send a sms message to a user from a certain number
# If from_num isn't specified, then defaults to prod
#
# Example url: 
# http://dev.duffyapp.com:8000/smskeeper/send_sms?user_id=23&msg=Test&from_num=%2B12488178301
#
def send_sms(request):
	form = SendSMSForm(api_util.getRequestData(request))
	response = dict()
	if (form.is_valid()):
		user = form.cleaned_data['user']
		msg = form.cleaned_data['msg']
		keeperNumber = form.cleaned_data['from_num']

		if not keeperNumber:
			keeperNumber = constants.TWILIO_SMSKEEPER_PHONE_NUM

		sms_util.sendMsg(user, msg, None, keeperNumber)

		response["result"] = True
		return HttpResponse(json.dumps(response), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


@csrf_exempt
def incoming_sms(request):
	form = SmsContentForm(api_util.getRequestData(request))

	if (form.is_valid()):
		phoneNumber = str(form.cleaned_data['From'])
		keeperNumber = str(form.cleaned_data['To'])
		msg = form.cleaned_data['Body']
		numMedia = int(form.cleaned_data['NumMedia'])
		requestDict = api_util.getRequestData(request)

		processMessage(phoneNumber, msg, numMedia, requestDict, keeperNumber)
		return sendNoResponse()
		
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

def all_notes(request):
	form = PhoneNumberForm(api_util.getRequestData(request))

	if (form.is_valid()):
		phoneNumber = str(form.cleaned_data['PhoneNumber'])
		try:
			user = User.objects.get(phone_number=phoneNumber)
			html = ""
			for note in Note.objects.filter(user=user):
				html += htmlForNote(note)
			return HttpResponse(html, content_type="text/html", status=200)
		except User.DoesNotExist:
			return sendResponse("Phone number not found")
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

def history(request):
	form = UserIdForm(api_util.getRequestData(request))
	
	if (form.is_valid()):
		user = form.cleaned_data['user']			
		context = {	'user_id': user.id }
		return render(request, 'thread_view.html', context)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

def message_feed(request):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']

		messages = Message.objects.filter(user=user).order_by("added")
		messages_dicts = []
		
		for message in messages:
			message_dict = json.loads(message.msg_json)
			if len(message_dict.keys()) > 0:
				if not message_dict.get("From", None):
					message_dict["From"] = user.phone_number
				message_dict["added"] = message.added
				messages_dicts.append(message_dict)
				if message_dict.get("From") == user.phone_number:
					message_dict["incoming"] = True
		return HttpResponse(json.dumps({"messages" : messages_dicts}, cls=DjangoJSONEncoder), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)
