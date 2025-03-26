# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from chatbot import settings
from datetime import datetime
from django.http.response import HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt
from fb_bot.models import Feedback
from pprint import pprint

import json
import pytz
import requests
import time

# Create your views here.
class FbBotView(generic.View):
    # WELCOME MESSAGE
    # post_message_url = 'https://graph.facebook.com/v2.6/me/thread_settings?access_token=%s' %(settings.FACEBOOK_PAGE_ACCESS_TOKEN)
    # response_msg = json.dumps({"setting_type":"greeting","greeting":{"text": "This is greeting text"}})
    # status = requests.post(post_message_url, headers={"Content-Type": "application/json"},data=response_msg)
    # pprint(status.json())

    def get(self, request, *args, **kwargs):
        if self.request.GET['hub.verify_token'] == '123456789123456789':
            return HttpResponse(self.request.GET['hub.challenge'])
        else:
            return HttpResponse("Error, invalid token")

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return generic.View.dispatch(self, request, *args, **kwargs)

    def init_feedback(self):
        feedback = {}
        feedback['title'] = 'Facebook messenger feedback'
        feedback['address'] = ''
        feedback['description'] = ''
        feedback['phase'] = 0
        feedback['lat'] = ''
        feedback['long'] = ''
        feedback['media'] = ''
        feedback['timestamp'] = ''
        return feedback

    def check_input(self, phase, user_input):
        try:
            user_input = user_input['message']['text']
        except KeyError:
            if phase == 2 or phase == 4:
                try:
                    user_input = user_input['message']['attachments']
                except KeyError:
                    return False
            else:
                return False

        bot_messages = ['Facebook messenger feedback']
        if any(user_input in s for s in bot_messages):
            pprint("check_input bot message detected and working")
            return False

        if phase == 0:
            string_length = len(user_input)
            if (string_length > 10) and (string_length < 5000):
                return True
            return False

        elif phase == 1 or phase == 3 or phase == 5:
            user_input = user_input.lower()
            user_input = user_input.strip(',.-!?:;')
            accept_answers = ['kyllä', 'joo', 'juu', 'k']
            decline_answers = ['ei', 'e']
            for user_input in accept_answers:
                return True
            for user_input in decline_answers:
                # feedback['phase'] = phase+2
                # save_to_database(feedback)
                return True
            return False

        # elif phase == 2:
        #     #Tarkistetaan, että Käyttäjä on lisännyt kuvan joko puhelimestaan tai suorana linkkinä.
        # elif phase == 4:
        #     # Tarkistetaan, että käyttäjä on jakanut sijainnin
        # elif phase == 6:
        #     # Tarkistetaan, että käyttäjä on kirjoittanut jonkin osoitteen
        return True

    def get_phase(self, message):
        new_row, created = Feedback.objects.create(
            user_id=message['sender']['id'],
            message='temp',
            phase='0'
        )
        user = new_row.user_id
        prev_row = Feedback.objects.filter(user_id=user).latest('source_created_at')
        pprint(type(user))
        pprint('id: %s\nphase: %s\nsource_created_at: %s\nuser_id: %s' % (r.id, r.phase, r.source_created_at, r.user_id))
        # if newest_record['phase'] !=
        Feedback.objects.filter(id=new_row.id).delete()
        return 0


    # Post function to handle Facebook messages
    def post(self, request, *args, **kwargs):
        feedback = self.init_feedback()
        # Converts the text payload into a python dictionary
        incoming_message = json.loads(self.request.body.decode('utf-8'))
        # Facebook recommends going through every entry since they might send
        # multiple messages in a single call during high load
        pprint(incoming_message)
        for entry in incoming_message['entry']:
            for message in entry['messaging']:
                # Check to make sure the received call is a message call
                # This might be delivery, optin, postback for other events 
                if 'message' in message and 'sender' != '204695756714834':
                    feedback['phase'] = self.get_phase(message)
                    if self.check_input(feedback['phase'], message):
                        pprint('check_input == true')
                        feedback_start_at = datetime.fromtimestamp(message['timestamp']/1000)
                        feedback_object, created = Feedback.objects.update_or_create(
                            source_created_at=feedback_start_at,
                            user_id=message['sender']['id'],
                            defaults={
                                'message': message['message']['text'],
                                'phase': feedback['phase']
                            }
                        )
                        if created is True:
                            post_facebook_message(message['sender']['id'], feedback['title'])
                    else:
                        pprint('check_input == false')
                    # Assuming the sender only sends text. Non-text messages like stickers, audio, pictures
                    # are sent as attachments and must be handled accordingly. 


                    # if message['message']['text'] == 'echo':
                    #     post_facebook_message(message['sender']['id'], message['message']['text'])
                    # else:
                    #     post_facebook_message(message['sender']['id'], 'couldn\'t echo that')
        return HttpResponse()

def post_facebook_message(fbid, recevied_message):
    post_message_url = 'https://graph.facebook.com/v2.6/me/messages?access_token=%s' %(settings.FACEBOOK_PAGE_ACCESS_TOKEN)
    response_msg = json.dumps({"recipient":{"id":fbid}, "message":{"text":recevied_message}})
    status = requests.post(post_message_url, headers={"Content-Type": "application/json"},data=response_msg)
    pprint(status.json())
