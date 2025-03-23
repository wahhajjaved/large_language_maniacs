import json
import datetime
import os
import sys
import phonenumbers
import logging
import pytz
import string
import re
from time import time
from operator import add

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from common import api_util, date_util
from common.models import ContactEntry
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from smskeeper import sms_util, processing_util, keeper_constants, user_util
from smskeeper.forms import UserIdForm, SendMediaForm, SmsContentForm, SendSMSForm, ResendMsgForm, WebsiteRegistrationForm, StripeForm, TelegramForm
from smskeeper.models import User, Entry, Message
from smskeeper import admin

from smskeeper import analytics, helper_util

from smskeeper.serializers import EntrySerializer
from smskeeper.serializers import MessageSerializer

from rest_framework import generics
from rest_framework import permissions
from rest_framework import authentication
from common import phone_info_util
from smskeeper.telegram import telegram_util

from common.api_util import DuffyJsonEncoder

logger = logging.getLogger(__name__)


def jsonp(f):
	"""Wrap a json response in a callback, and set the mimetype (Content-Type) header accordingly
	(will wrap in text/javascript if there is a callback). If the "callback" or "jsonp" paramters
	are provided, will wrap the json output in callback({thejson})

	Usage:

	@jsonp
	def my_json_view(request):
		d = { 'key': 'value' }
		return HTTPResponse(json.dumps(d), content_type='application/json')

	"""
	from functools import wraps

	@wraps(f)
	def jsonp_wrapper(request, *args, **kwargs):
		resp = f(request, *args, **kwargs)
		if resp.status_code != 200:
			return resp
		if 'callback' in request.GET:
			callback = request.GET['callback']
			resp['Content-Type'] = 'text/javascript; charset=utf-8'
			resp.content = "%s(%s)" % (callback, resp.content)
			return resp
		elif 'jsonp' in request.GET:
			callback = request.GET['jsonp']
			resp['Content-Type'] = 'text/javascript; charset=utf-8'
			resp.content = "%s(%s)" % (callback, resp.content)
			return resp
		else:
			return resp

	return jsonp_wrapper


def sendNoResponse():
	content = '<?xml version="1.0" encoding="UTF-8"?>\n'
	content += "<Response></Response>"
	return HttpResponse(content, content_type="text/xml")


@csrf_exempt
def incoming_sms(request):
	form = SmsContentForm(api_util.getRequestData(request))

	if (form.is_valid()):
		phoneNumber = str(form.cleaned_data['From'])
		keeperNumber = str(form.cleaned_data['To'])
		msg = form.cleaned_data['Body']
		requestDict = api_util.getRequestData(request)

		processing_util.processMessage(phoneNumber, msg, requestDict, keeperNumber)
		return sendNoResponse()

	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

@csrf_exempt
def incoming_telegram(request):
	logger.info("Incoming telegram request with body:\n%s", request, request.body)
	try:
		requestDict = json.loads(request.body)
	except Exception:
		logger.error("Couldn't parse telegram request body: %s", request.body)
		return HttpResponse(json.dumps({"Error": "Not JSON"}), content_type="text/json", status=400)

	form = TelegramForm(requestDict)

	error = None
	if form.is_valid():
		updateId = form.cleaned_data.get('update_id', None)
		message = requestDict.get('message', None)

		if message:
			logger.info("Received telegram update %d: %s", updateId, message)
			fromInfo = message.get('from', {'id': None})
			telegramUid = fromInfo['id']
			text = message.get('text', None)
			if telegramUid and text:
				fakePhoneNumber = telegram_util.telegramUidToPhoneNumber(telegramUid)  # it's not an actual phone number
				processing_util.processMessage(
					fakePhoneNumber,
					message['text'],
					requestDict,
					settings.TELEGRAM_BOT_NAME + keeper_constants.TELEGRAM_NUMBER_SUFFIX
				)
			elif telegramUid and not text:
				logger.info('User %s: sent a non-text message, ignorning', telegram_util.telegramUidToPhoneNumber(telegramUid))
			else:
				error = {"Error": "UID not found"}
		else:
			error = {"Error": "message object not found"}
	else:
		error = form.errors

	if error:
		logger.info("Received malformed telegram message: %s\n\nerror:%s", json.dumps(requestDict), json.dumps(error))
		return HttpResponse(json.dumps(error), content_type="text/json", status=400)
	else:
		return sendNoResponse()


@login_required(login_url='/admin/login/')
def keeper_app(request):
	return renderReact(request, 'keeper_app', 'keeper_app.html')


def mykeeper(request, key):
	keys = ["K" + key, "P" + key]
	try:
		user = User.objects.get(key__in=keys)
		return renderReact(request, 'keeper_app', 'keeper_app.html', user)
	except User.DoesNotExist:
		return HttpResponse(json.dumps({"Errors": "User not found"}), content_type="text/json", status=400)


@login_required(login_url='/admin/login/')
def history(request):
	return renderReact(
		request,
		'history',
		'history.html',
		context={"classifications": keeper_constants.CLASS_MENU_OPTIONS}
	)


@login_required(login_url='/admin/login/')
def review(request):
	return renderReact(
		request,
		'review',
		'review.html',
		requiresUser=False,
	)


def renderReact(request, appName, templateFile="react_app.html", user=None, context=dict(), requiresUser=True):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		if requiresUser:
			if not user:
				user = form.cleaned_data['user']
			phoneNumToContactDict = getNameFromContactsDB([user.phone_number])
			context["user_data"] = json.dumps(getUserDataDict(user, phoneNumToContactDict), cls=DjangoJSONEncoder)
		else:
			context["user_data"] = json.dumps({})

		context["development"] = settings.DEBUG
		if form.cleaned_data['development']:
			context["development"] = form.cleaned_data['development']
		context["script_name"] = appName

		return render(request, templateFile, context)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


def getMessagesForUser(user):
	messages = Message.objects.filter(user=user).order_by("added")
	messages_dicts = []

	for message in messages:
		message_dict = json.loads(message.msg_json)
		if message_dict.get("message"):  # telegram message
			message_dict = {
				'Body': message_dict['message']['text'],
				'NumMedia': 0
			}
		if len(message_dict.keys()) > 0:
			message_dict["id"] = message.id
			if not message_dict.get("From", None):
				message_dict["From"] = user.phone_number
			message_dict["added"] = message.added
			message_dict["incoming"] = message.incoming
			message_dict["manual"] = message.manual
			if message.incoming:
				message_dict["classification"] = message.classification
				message_dict["auto_classification"] = message.auto_classification
				if message.classification_scores_json:
					message_dict["classification_scores"] = json.loads(message.classification_scores_json)
				message_dict["statement_bounds"] = []
				if(message.statement_bounds_json):
					message_dict["statement_bounds"] = json.loads(message.statement_bounds_json)

			messages_dicts.append(message_dict)

	return messages_dicts


def getMessagesResponseForUser(user):
	response = dict()
	messages_dicts = getMessagesForUser(user)
	response['messages'] = messages_dicts
	response['paused'] = user.isPaused()

	return response


# External
@login_required(login_url='/admin/login/')
def message_feed(request):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']

		return HttpResponse(json.dumps(getMessagesResponseForUser(user), cls=DjangoJSONEncoder), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


class MessageDetail(generics.RetrieveUpdateAPIView):
	authentication_classes = (authentication.BasicAuthentication,)
	permission_classes = (permissions.AllowAny,)
	queryset = Message.objects.all()
	serializer_class = MessageSerializer

def entry_feed(request):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']

		entries = Entry.fetchEntries(user, hidden=None, orderByString="-updated")
		serializer = EntrySerializer(entries, many=True)
		return HttpResponse(json.dumps(serializer.data, cls=DjangoJSONEncoder), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

# These are used from urls.py and turned into JSON feeds
class ReviewFeed(generics.ListCreateAPIView):
	# set authentication to basic and allow any to disable CSRF protection
	authentication_classes = (authentication.BasicAuthentication,)
	permission_classes = (permissions.AllowAny,)
	queryset = Entry.objects.filter(manually_check=True, hidden=False)
	queryset = admin.filterReminderQueryset(queryset)
	serializer_class = EntrySerializer

class EntryList(generics.ListCreateAPIView):
	# set authentication to basic and allow any to disable CSRF protection
	authentication_classes = (authentication.BasicAuthentication,)
	permission_classes = (permissions.AllowAny,)
	queryset = Entry.objects.all()
	serializer_class = EntrySerializer


class EntryDetail(generics.RetrieveUpdateAPIView):
	# set authentication to basic and allow any to disable CSRF protection
	authentication_classes = (authentication.BasicAuthentication,)
	permission_classes = (permissions.AllowAny,)
	queryset = Entry.objects.all()
	serializer_class = EntrySerializer


def unknown_messages_feed(request):
	response = dict()
	messages = Message.objects.filter(manually_check=True)

	messages_dicts = []

	for message in messages:
		message_dict = dict()
		message_dict["id"] = message.id
		message_dict["user"] = message.user_id
		message_dict["body"] = message.getBody()
		message_dict["manually_check"] = message.manually_check
		message_dict["user_name"] = message.user.name

		followupBodies = list()
		followups = Message.objects.filter(user=message.user, added__gt=message.added).order_by("added")
		for followup in followups:
			manualStr = " (manual)" if followup.manual else ""

			if followup.incoming:
				followupBodies.append("Them%s:  %s" % (manualStr, followup.getBody()))
			else:
				if followup.manual:
					followupBodies.append("Us%s: %s" % (manualStr, followup.getBody()))
				else:
					followupBodies.append("Us%s:      %s" % (manualStr, followup.getBody()))

		message_dict["followups"] = followupBodies

		messages_dicts.append(message_dict)

	response["messages"] = messages_dicts

	return HttpResponse(json.dumps(response, cls=DjangoJSONEncoder), content_type="text/json", status=200)


#
# Send a sms message to a user from a certain number
# If from_num isn't specified, then defaults to prod
#
# Example url:
# http://dev.duffyapp.com:8000/smskeeper/send_sms?user_id=23&msg=Test&from_num=%2B12488178301
#
@csrf_exempt
def send_sms(request):
	form = SendSMSForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']
		msg = form.cleaned_data['msg']
		keeperNumber = form.cleaned_data['from_num']
		direction = form.cleaned_data['direction']
		override_class = form.cleaned_data['override_class']
		media = None  # add a link here to send to users

		if not keeperNumber:
			keeperNumber = user.getKeeperNumber()

		if direction == "ToUser":
			sms_util.sendMsg(user, msg, media, keeperNumber, manual=True)
		else:
			if (user.paused):
				user_util.setPaused(user, False, keeperNumber, "manual send")
			requestDict = dict()
			requestDict["Body"] = msg
			requestDict["To"] = keeperNumber
			requestDict["From"] = user.phone_number
			requestDict["Manual"] = True
			requestDict["OverrideClass"] = override_class
			processing_util.processMessage(user.phone_number, msg, requestDict, keeperNumber)
		return HttpResponse(json.dumps({"result": "success"}), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


@csrf_exempt
def toggle_paused(request):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']

		user_util.setPaused(user, not user.paused, user.getKeeperNumber(), "manual toggle")

		return HttpResponse(json.dumps(getMessagesResponseForUser(user), cls=DjangoJSONEncoder), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


#
# Send a sms message to a user from a certain number
# If from_num isn't specified, then defaults to prod
#
# Example url:
# http://dev.duffyapp.com:8000/smskeeper/resend_sms?msg_id=12345
#
@csrf_exempt
def resend_msg(request):
	form = ResendMsgForm(api_util.getRequestData(request))
	response = dict()
	if (form.is_valid()):
		msgId = form.cleaned_data['msg_id']
		keeperNumber = form.cleaned_data['from_num']

		message = Message.objects.get(id=msgId)

		if not keeperNumber:
			keeperNumber = message.user.getKeeperNumber()

		if (message.incoming):
			if (message.user.paused):
				user_util.setPaused(message.user, False, message.user.getKeeperNumber(), "manual resend")

			requestDict = json.loads(message.msg_json)
			requestDict["Manual"] = True
			processing_util.processMessage(message.user.phone_number, requestDict["Body"], requestDict, keeperNumber)
		else:
			sms_util.sendMsg(message.user, message.getBody(), None, keeperNumber)

		response["result"] = True
		return HttpResponse(json.dumps(response), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


@csrf_exempt
def send_media(request):
	form = SendMediaForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']
		media = form.cleaned_data['url']
		msg = form.cleaned_data['msg']

		if not msg:
			msg = ""

		keeperNumber = user.getKeeperNumber()

		sms_util.sendMsg(user, msg, media, keeperNumber, manual=True)
		return HttpResponse(json.dumps({"result": "success"}), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


def getUserDataDict(user, phoneNumToContactDict):
	if user.phone_number in phoneNumToContactDict:
		full_name = phoneNumToContactDict[user.phone_number]
	else:
		full_name = ''

	newSignupData = dict()
	if user.signup_data_json:
		signupData = json.loads(user.signup_data_json)

		if 'source' in signupData and signupData['source'] != 'default':
			newSignupData['source'] = signupData['source']
		if 'referrer' in signupData and len(signupData['referrer']) > 0:
			newSignupData['ref'] = signupData['referrer']
		if 'paid' in signupData and len(signupData['paid']) > 0 and signupData['paid'] != '0':
			newSignupData['paid'] = signupData['paid']
		if 'exp' in signupData and len(signupData['exp']) > 0:
			newSignupData['exp'] = signupData['exp']

	userData = {
		"id": user.id,
		"key": user.key,
		"phone_number": user.phone_number,
		"name": user.name,
		"full_name": full_name,
		"source": json.dumps(newSignupData),
		"activated": user.activated,
		"paused": user.paused,
		"created": user.added,
		"state": user.state,
		"tutorial_step": user.tutorial_step,
		"product_id": user.product_id,
		"completed_tutorial": user.completed_tutorial,
		"timezone": str(user.getTimezone()),
		"postal_code": user.postal_code,
		"carrier": phone_info_util.getUserCarrierInfo(user).get('name', 'unknown')
	}
	return userData


@login_required(login_url='/admin/login/')
def dashboard_feed(request):

	###### measuring perf
	n = len(connection.queries)
	start = time()
	######

	users = list()
	daily_stats = {}
	for days_ago in [1, 3, 7, 30]:
		date_filter = date_util.now(pytz.utc) - datetime.timedelta(days=days_ago)
		daily_stats[days_ago] = {}
		for direction in ["incoming", "outgoing"]:
			incoming = (direction == "incoming")
			messages = Message.objects.filter(incoming=incoming, added__gt=date_filter)
			message_count = messages.count()
			msg_users = messages.values_list('user').distinct()
			if days_ago == 7:
				users = msg_users
			user_count = msg_users.count()
			daily_stats[days_ago][direction] = {
				"messages": message_count,
				"user_count": user_count
			}


	all_users = User.objects.all().order_by("id")
	user_dicts = []
	phoneNumList = list()
	for user in all_users:
		phoneNumList.append(user.phone_number)

	phoneNumToContactDict = getNameFromContactsDB(phoneNumList)

	users = User.objects.filter(id__in=users)

	for user in users:
		userData = getUserDataDict(user, phoneNumToContactDict)

		userData["message_stats"] = {}
		for direction in ["incoming", "outgoing"]:
			incoming = (direction == "incoming")
			messages = Message.objects.filter(user=user, incoming=incoming).order_by("-added")
			count = messages.count()
			last_message_date = None
			if count > 0:
				last_message_date = messages[0].added
			else:
				# for new users, setting it to beginning of 2015
				last_message_date = user.added
			userData["message_stats"][direction] = {
				"count": count,
				"last": last_message_date,
			}
		userData["history"] = "history?user_id=" + str(user.id)

		user_dicts.append(userData)

	user_dicts = sorted(user_dicts, key=lambda k: k['message_stats']['incoming']['last'], reverse=True)

	##### measuring perf
	total_time = time() - start

	db_queries = len(connection.queries) - n
	if db_queries:
		db_time = reduce(add, [float(q['time'])
							   for q in connection.queries[n:]])
	else:
		db_time = 0.0

	# and backout python time
	python_time = total_time - db_time

	stats = {
		'total_time': total_time,
		'python_time': python_time,
		'db_time': db_time,
		'db_queries': db_queries,
	}
	##### End of measurement code

	responseJson = json.dumps({"users": user_dicts, "daily_stats": daily_stats, "stats": stats}, cls=DjangoJSONEncoder)
	return HttpResponse(responseJson, content_type="text/json", status=200)


def getNameFromContactsDB(phoneNumList):
	contacts = ContactEntry.objects.values('name', 'phone_number').filter(phone_number__in=phoneNumList).distinct()

	#build a dictionary
	phoneToNameDict = dict()
	for contact in contacts:
		if contact['phone_number'] not in phoneToNameDict:
			phoneToNameDict[contact['phone_number']] = [contact['name']]
		else:
			phoneToNameDict[contact['phone_number']].append(contact['name'])
	return phoneToNameDict


@login_required(login_url='/admin/login/')
def dashboard(request):
	return render(request, "dashboard.html", None)


@jsonp
def signup_from_website(request):
	response = dict({'result': True})
	form = WebsiteRegistrationForm(api_util.getRequestData(request))
	if (form.is_valid()):
		source = form.cleaned_data['source']
		referrerCode = form.cleaned_data['referrer']
		paid = form.cleaned_data['paid']
		exp = form.cleaned_data['exp']

		# clean phone number
		region_code = 'US'
		phoneNumberStr = filter(lambda x: x in string.printable, form.cleaned_data['phone_number'].encode('utf-8'))
		phoneNum = None

		for match in phonenumbers.PhoneNumberMatcher(phoneNumberStr, region_code):
			phoneNum = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)

		if phoneNum:
			# create account in database
			try:
				user = User.objects.get(phone_number=phoneNum)
			except User.DoesNotExist:
				if not helper_util.isUSRegionCode(phoneNum):
					productId = keeper_constants.WHATSAPP_TODO_PRODUCT_ID
				elif "medical" in exp:
					productId = keeper_constants.MEDICAL_PRODUCT_ID
				elif "student" in exp:
					productId = keeper_constants.STUDENT_PRODUCT_ID
				else:
					productId = keeper_constants.TODO_PRODUCT_ID

				user = user_util.createUser(phoneNum, json.dumps({'source': source, 'referrer': referrerCode, 'paid': paid, 'exp': exp}), None, productId, None)

				logger.debug("User %s: Just created user with productId %s and keeperNumber %s" % (user.id, user.product_id, user.getKeeperNumber()))

				analytics.logUserEvent(user, "Website Signup", {
					"source": source,
					"referred": True if referrerCode else False
				})
				if 'no-js' in source:
					return HttpResponseRedirect('http://getkeeper.com/')
		else:
			response['result'] = False
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response), content_type="application/json")


@jsonp
def update_stripe_info(request):
	response = dict({'result': True})
	form = StripeForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']
		stripe_data = form.cleaned_data['stripe_data']

		user.stripe_data_json = stripe_data
		user.save()

		sms_util.sendMsg(user, "Thanks for subscribing! You can now schedule unlimited reminders :sunglasses:")
		logger.info("Registered users %s for medical" % (user.id))
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response), content_type="application/json")


@login_required(login_url='/admin/login/')
def approved_todos(request):
	entries = Entry.objects.prefetch_related('creator').filter(manually_check=0, remind_recur=keeper_constants.RECUR_DEFAULT).order_by("-added")[:1000]

	entryList = list()

	for entry in entries:
		s = EntrySerializer(entry)
		s.data["timezone"] = str(entry.creator.getTimezone())
		entryList.append(s.data)

	return HttpResponse(json.dumps({"entries": entryList}, cls=DuffyJsonEncoder), content_type="text/text", status=200)
