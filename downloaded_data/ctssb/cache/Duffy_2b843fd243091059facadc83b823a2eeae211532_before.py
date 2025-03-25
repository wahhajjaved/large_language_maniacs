import json
from multiprocessing import Process
import time
import random
import math
import pytz
import datetime
from datetime import date, timedelta
import os, sys, re
import requests
import phonenumbers
import logging
import string

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from django.shortcuts import render

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.serializers.json import DjangoJSONEncoder

from smskeeper.forms import UserIdForm, SmsContentForm, PhoneNumberForm, SendSMSForm, ResendMsgForm, WebsiteRegistrationForm

from smskeeper.models import User, Entry, Message, MessageMedia, Contact


from smskeeper import sms_util, image_util, msg_util, processing_util, helper_util
from smskeeper import async, actions, keeper_constants

from common import api_util
from peanut.settings import constants
from peanut import settings
from django.conf import settings as djangosettings

logger = logging.getLogger(__name__)


def sendNoResponse():
	content = '<?xml version="1.0" encoding="UTF-8"?>\n'
	content += "<Response></Response>"
	logger.info("Sending blank response")
	return HttpResponse(content, content_type="text/xml")


def htmlForUserLabel(user, label):
	html = "%s:\n"%(label)
	entries = Entry.fetchEntries(user, label)
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

"""
	Helper method for command line interface input.  Use by:
	python
	>> from smskeeper import views
	>> views.cliMsg("+16508158274", "blah #test")
"""
def cliMsg(phoneNumber, msg, mediaURL=None, mediaType=None):
	numMedia = 0
	jsonDict = {
		"Body": msg,
	}

	if mediaURL is not None:
		numMedia = 1
		jsonDict["MediaUrl0"] = mediaURL
		if mediaType is not None:
			jsonDict["MediaContentType0"] = mediaType
		jsonDict["NumMedia"] = 1
	else:
		jsonDict["NumMedia"] = 0

	processing_util.processMessage(phoneNumber, msg, jsonDict, constants.SMSKEEPER_TEST_NUM)

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

#
# Send a sms message to a user from a certain number
# If from_num isn't specified, then defaults to prod
#
# Example url:
# http://dev.duffyapp.com:8000/smskeeper/send_sms?user_id=23&msg=Test&from_num=%2B12488178301
#
def resend_msg(request):
	form = ResendMsgForm(api_util.getRequestData(request))
	response = dict()
	if (form.is_valid()):
		msgId = form.cleaned_data['msg_id']
		keeperNumber = form.cleaned_data['from_num']

		message = Message.objects.get(id=msgId)
		data = json.loads(message.msg_json)

		sms_util.sendMsg(message.user, data["Body"], None, keeperNumber)

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

		process_util.processMessage(phoneNumber, msg, requestDict, keeperNumber)
		return sendNoResponse()

	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

def all_notes(request):
	form = UserIdForm(api_util.getRequestData(request))

	if (form.is_valid()):
		user = form.cleaned_data['user']
		try:
			html = ""
			for label in Entry.fetchAllLabels(user):
				html += htmlForUserLabel(user, label)
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


def dashboard_feed(request):
	users = User.objects.all().order_by("id")
	user_dicts = []
	for user in users:
		dict = {
			"id" : int(user.id),
			"phone_number" : user.phone_number,
			"name" : user.name,
			"activated" : user.activated,
			"created" : user.added,
			"tutorial_step" : user.tutorial_step,
			"completed_tutorial" : user.completed_tutorial
		}

		dict["message_stats"] = {}
		for direction in ["incoming", "outgoing"]:
			incoming = (direction == "incoming")
			messages = Message.objects.filter(user=user, incoming=incoming).order_by("-added")
			count = messages.count()
			last_message_date = None
			if count > 0:
				last_message_date = messages[0].added
			dict["message_stats"][direction] = {
				"count" : count,
				"last" : last_message_date,
			}
		dict["history"] = "history?user_id=" + str(user.id)

		user_dicts.append(dict)

	daily_stats = {}
	for days_ago in [1, 3, 7, 30]:
		date_filter = date.today() - timedelta(days=days_ago)
		daily_stats[days_ago] = {}
		for direction in ["incoming", "outgoing"]:
			incoming = (direction == "incoming")
			messages = Message.objects.filter(incoming=incoming, added__gt=date_filter)
			message_count = messages.count()
			user_count = messages.values('user').distinct().count()
			daily_stats[days_ago][direction] = {
				"messages" : message_count,
				"user_count" : user_count
			}

	responseJson = json.dumps({"users" : user_dicts, "daily_stats" : daily_stats}, cls=DjangoJSONEncoder)
	return HttpResponse(responseJson, content_type="text/json", status=200)

def dashboard(request):
	return render(request, 'dashboard.html', None)

def signup_from_website(request):
	response = dict({'result': True})
	form = WebsiteRegistrationForm(api_util.getRequestData(request))
	if (form.is_valid()):
		source = form.cleaned_data['source']

		# clean phone number
		region_code = 'US'
		phoneNumberStr = filter(lambda x: x in string.printable, form.cleaned_data['phone_number'].encode('utf-8'))
		phoneNum = None

		for match in phonenumbers.PhoneNumberMatcher(phoneNumberStr, region_code):
			phoneNum = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)

		if phoneNum:
			# create account in database
			try:
				target_user = User.objects.get(phone_number=phoneNum)

				bodyText = "You are already on the list. Hang tight... unless you know the magic phrase?"
				sms_util.sendMsg(target_user, bodyText, None, djangosettings.KEEPER_NUMBER)

			except User.DoesNotExist:
				target_user = User.objects.create(phone_number=phoneNum, state_data=1, signup_data_json=json.dumps(source))
				target_user.save()

				bodyText = "Hi. I'm Keeper. I can help you remember things quickly."
				sms_util.sendMsg(target_user, bodyText, None, djangosettings.KEEPER_NUMBER)
				time.sleep(1)
				bodyText = "I'll let you know when I'm ready for you. Unless you know the magic phrase to skip the line?"
				sms_util.sendMsg(target_user, bodyText, None, djangosettings.KEEPER_NUMBER)
		else:
			response['result'] = False
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response), content_type="application/json")

@receiver(post_save, sender=Message)
def sendLiveFeed(sender, **kwargs):
	message = kwargs.get('instance')
	msgContent = json.loads(message.msg_json)
	if ('To' in msgContent and msgContent['To'] in constants.KEEPER_PROD_PHONE_NUMBERS) or ('From' in msgContent and msgContent['From'] in constants.KEEPER_PROD_PHONE_NUMBERS):
		url = 'https://hooks.slack.com/services/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'
		channel = "#livesmskeeperfeed"
		params = dict()
		text = msgContent['Body']

		if message.incoming:
			userName = message.user.name + ' (' + message.user.phone_number + ')'

			numMedia = int(msgContent['NumMedia'])

			if numMedia > 0:
				for n in range(numMedia):
					param = 'MediaUrl' + str(n)
					text += "\n<" + msgContent[param] + "|" + param + ">"
			params['icon_emoji'] = ':raising_hand:'

		else:
			if message.user.name:
				name = message.user.name
			else:
				name = message.user.phone_number
			userName = "Keeper" + " (to: " + name + ")"
			if msgContent['MediaUrls']:
				text += " <" + str(msgContent['MediaUrls']) + "|Attachment>"
			params['icon_emoji'] = ':rabbit:'


		params['username'] = userName
		params['text'] = text
		params['channel'] = channel

		resp = requests.post(url, data=json.dumps(params))
