import json
from datetime import date, timedelta
import os
import sys
import phonenumbers
import logging
import string

parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
	sys.path.insert(0, parentPath)
import django
django.setup()

from common import api_util
from common.models import ContactEntry
from django.conf import settings
from django.conf import settings as djangosettings
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from smskeeper import sms_util, processing_util
from smskeeper.forms import UserIdForm, SmsContentForm, SendSMSForm, ResendMsgForm, WebsiteRegistrationForm
from smskeeper.models import User, Entry, Message

from smskeeper.states import not_activated

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
	logger.info("Sending blank response")
	return HttpResponse(content, content_type="text/xml")


def htmlForUserLabel(user, label):
	html = "%s:\n" % (label)
	entries = Entry.fetchEntries(user, label)
	if len(entries) == 0:
		html += "(empty)<br><br>"
		return html

	count = 1
	html += "<ol>\n"
	for entry in entries:
		if not entry.img_url:
			html += "<li>%s</li>" % (entry.text)
			count += 1
		else:
			html += "<img src=\"%s\" />" % (entry.img_url)
	html += "</ol>"

	return html


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


@login_required(login_url='/admin/login/')
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
			return HttpResponse(json.dumps({'phone_number': "Not Found"}), content_type="text/json", status=400)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

@login_required(login_url='/admin/login/')
def history(request):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']
		context = {	'user_id': user.id}
		context["development"] = settings.DEBUG
		if form.cleaned_data['development']:
			context["development"] = form.cleaned_data['development']

		return render(request, 'thread_view.html', context)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


def getMessagesForUser(user):
	messages = Message.objects.filter(user=user).order_by("added")
	messages_dicts = []

	for message in messages:
		message_dict = json.loads(message.msg_json)
		if len(message_dict.keys()) > 0:
			message_dict["id"] = message.id
			if not message_dict.get("From", None):
				message_dict["From"] = user.phone_number
			message_dict["added"] = message.added
			messages_dicts.append(message_dict)
			if message_dict.get("From") == user.phone_number:
				message_dict["incoming"] = True

	return messages_dicts


# External
@login_required(login_url='/admin/login/')
def message_feed(request):
	form = UserIdForm(api_util.getRequestData(request))
	if (form.is_valid()):
		user = form.cleaned_data['user']

		messages_dicts = getMessagesForUser(user)
		return HttpResponse(json.dumps({"messages": messages_dicts}, cls=DjangoJSONEncoder), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)


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

		if not keeperNumber:
			keeperNumber = settings.KEEPER_NUMBER

		sms_util.sendMsg(user, msg, None, keeperNumber)

		messages_dicts = getMessagesForUser(user)
		return HttpResponse(json.dumps({"messages": messages_dicts}, cls=DjangoJSONEncoder), content_type="text/json", status=200)
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

		if not keeperNumber:
			keeperNumber = settings.KEEPER_NUMBER

		message = Message.objects.get(id=msgId)
		data = json.loads(message.msg_json)

		if (message.incoming):
			requestDict = json.loads(message.msg_json)
			processing_util.processMessage(message.user.phone_number, requestDict["Body"], requestDict, keeperNumber)
		else:
			sms_util.sendMsg(message.user, data["Body"], None, keeperNumber)

		response["result"] = True
		return HttpResponse(json.dumps(response), content_type="text/json", status=200)
	else:
		return HttpResponse(json.dumps(form.errors), content_type="text/json", status=400)

@login_required(login_url='/admin/login/')
def dashboard_feed(request):
	users = User.objects.all().order_by("id")
	user_dicts = []
	phoneNumList = list()
	for user in users:
		phoneNumList.append(user.phone_number)

	phoneNumToContactDict = getNameFromContactsDB(phoneNumList)

	for user in users:
		if user.phone_number in phoneNumToContactDict:
			full_name = phoneNumToContactDict[user.phone_number]
		else:
			full_name = ''
		dict = {
			"id": int(user.id),
			"phone_number": user.phone_number,
			"name": user.name,
			"full_name": full_name,
			"source": "(" + user.signup_data_json + ")" if user.signup_data_json and "default" not in user.signup_data_json else '',
			"activated": user.activated,
			"created": user.added,
			"tutorial_step": user.tutorial_step,
			"completed_tutorial": user.completed_tutorial
		}

		dict["message_stats"] = {}
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
			dict["message_stats"][direction] = {
				"count": count,
				"last": last_message_date,
			}
		dict["history"] = "history?user_id=" + str(user.id)

		user_dicts.append(dict)

	user_dicts = sorted(user_dicts, key=lambda k: k['message_stats']['incoming']['last'], reverse=True)

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
				"messages": message_count,
				"user_count": user_count
			}

	responseJson = json.dumps({"users": user_dicts, "daily_stats": daily_stats}, cls=DjangoJSONEncoder)
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

				bodyText = "You are already on the list. Hang tight and I'll be in touch soon."
				sms_util.sendMsg(target_user, bodyText, None, djangosettings.KEEPER_NUMBER)

			except User.DoesNotExist:
				target_user = User.objects.create(phone_number=phoneNum, signup_data_json=json.dumps(source))
				target_user.save()

				not_activated.dealWithNonActivatedUser(target_user, djangosettings.KEEPER_NUMBER)
		else:
			response['result'] = False
	else:
		return HttpResponse(json.dumps(form.errors), content_type="application/json", status=400)

	return HttpResponse(json.dumps(response), content_type="application/json")
