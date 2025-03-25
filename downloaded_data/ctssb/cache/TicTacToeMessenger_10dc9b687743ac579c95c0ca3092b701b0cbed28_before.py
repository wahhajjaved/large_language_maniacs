# coding=utf-8
import json

import os

import requests
from app import app
from static import States


def call_send_api(message_data):
    r = requests.post('https://graph.facebook.com/v2.6/me/messages',
                      data=message_data,
                      params={'access_token': os.environ['PAGE_ACCESS_TOKEN']},
                      headers={'Content-Type': 'application/json'})
    app.logger.info('response: {}'.format(r.content))


def send_text_message(recipient_id, text):
    app.logger.info('sending message to {}'.format(recipient_id))
    message_data = json.dumps({
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'text': text
        }
    })
    call_send_api(message_data)


def text_message_sender(text):
    def f(user_id, **kwargs):
        return send_text_message(text, user_id)
    return f


def start_the_game(**kwargs):
    pass