from flask import Flask, request, render_template
from User import User
import json
import os
import twilio.twiml

from twilio.rest import TwilioRestClient

client = TwilioRestClient()

app = Flask(__name__)
app.debug = True

Users = []

@app.route('/', methods=['GET', 'POST'])
def receiveSMS():
    body = request.values.get('Body', '')
    resp = twilio.twiml.Response()
    message = "You've been removed from the game.. sucker."
    resp.sms(message)
    user = request.values.get('From', '')
    print user
    del Users[user]
    return str(resp)

def sendSMS(phone_num, text):
    message = client.sms.messages.create(to=phone_num, from_="+19492163884",
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
        name, number = name.strip(), number.strip()
        user = User(name=name, number=number)
        Users[number] = user

    users_list = list(Users.values())
    for i, user in enumerate(users_list):
        user.target_number = users_list[ (i + 1) % len(users_list)].number

    return 'ok'

@app.route('/gamestatus', methods=['GET'])
def gamestatus():
    return json.dumps([user.serialize() 
                       for number, user in Users.items()])

if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
