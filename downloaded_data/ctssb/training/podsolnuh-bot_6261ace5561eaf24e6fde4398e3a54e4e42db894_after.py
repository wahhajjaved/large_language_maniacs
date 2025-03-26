# -*- coding: utf8 -*-
""" Podsolnuh Bot v. 0.0 """

import json
import os
from datetime import datetime
import vk
from flask import Flask, jsonify, make_response, request
from hooks.dialogflow import dialogflow_webhook

APP = Flask(__name__)
LOG = APP.logger


@APP.route('/')
def homepage():
    """Generate default page"""
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    return """
    <h1>Hello heroku</h1>
    <p>It is currently {time}.</p>
    """.format(time=the_time)


@APP.route(os.environ.get('HOOK_URL_DIALOGFLOW', '/empty'), methods=['POST'])
def webhook():
    """This method handles the http requests for the  Dialogflow webhook
    This is meant to be used in conjunction with the translate Dialogflow agent
    """

    return make_response(jsonify(dialogflow_webhook(request.get_json(force=True), LOG)))


if __name__ == '__main__':
    APP.run(debug=True, use_reloader=True)
