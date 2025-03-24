from flask import Flask, request, render_template
from User import User
import logging
import json
import os
import random
import twilio.twiml

from twilio.rest import TwilioRestClient

client = TwilioRestClient()

app = Flask(__name__)
app.debug = True

Users = {}

@app.route('/', methods=['GET', 'POST'])
def receiveSMS():
    body = request.values.get('Body', '')

    resp = twilio.twiml.Response()
    message = "You've been removed from the game.. sucker."
    resp.sms(message)

    # Get user num who just died and updateTarget
    dead_user_phone_num = request.values.get('From', '')
    updateTarget(Users[dead_user_phone_num])
    print dead_user_phone_num

    del Users[int(dead_user_phone_num)]
    return str(resp)

def updateTarget(user_killed):
    users = Users.values()
    for user in users:
        if user.target_numer = user_killed.number:
            user.target_number = user_killed.target_number  
            break
    

def sendSMS(phone_num, text):
    from_="+19492163884"
    logging.warn('sending a message from %s to %s with content: %s' % (
            phone_num, from_, text))
            
    message = client.sms.messages.create(to=phone_num, from_=from_,
                                     body=text)
    return message

@app.route('/startgame', methods=['GET'])
def getstartgame():
    return render_template('form.html')

@app.route('/startgame', methods=['POST'])
def poststartgame():
    data = request.values['data']

    global Users
    Users = {}
    for line in data.split('\n'):
        line = line.strip()
        if not line:
            continue
        number, name = line.split(',')
        name, number = name.strip(), int(number.strip())
        user = User(name=name, number=number)
        Users[number] = user

    users_list = list(Users.values())
    random.shuffle(users_list)
    for i, user in enumerate(users_list):
        user.target_number = users_list[ (i + 1) % len(users_list)].number

    for i, user in enumerate(users_list):
        sendSMS(user.number,
                "Welcome to the game, your target is: " + Users[user.target_number].name)

        Users[user.target_number].name

    return 'ok'

@app.route('/dashboard', methods=['GET'])
def dashboard():
    return render_template('status.html', **{'Users': Users})

@app.route('/gamestatus', methods=['GET'])
def gamestatus():
    return json.dumps([user.serialize() 
                       for number, user in Users.items()])

if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
