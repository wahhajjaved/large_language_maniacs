# Copyright 2012. Team Flower Power.
# Google Intern Hackathon
# 
# Team:
#	Daniel Gur
#	Elissa Wolf
#	Enrique Sada
# 	Huan Do
#

import json
import logging
import os
import random
import twilio.twiml

from flask import Flask, request, render_template, redirect
from User import User
from twilio.rest import TwilioRestClient

client = TwilioRestClient()

app = Flask(__name__)
app.debug = True

Users = {}

UsersKilled = {}

ShuffledUsers = []

Words = {"blue": False,
         "robust": False,
         "scalable": False,
         "dynamic": False,
         "red": False,
         "spector": False}

@app.route('/kill/', methods=['GET', 'POST'])
def receiveSMS():
    global Users
    # Get info of received SMS
    # text_received = request.values.get('Body', '')
    word = request.values.get('Body', '').strip().lower()
    sender_number = int(request.values.get('From', ''))

    # If user died, make necessary updates
    """if text_received.strip().lower() == 'dead':
        dead_user = Users[sender_number]
        updateTarget(dead_user)
        
        # Add dead user to UsersKilled
        # Delete dead user from current players
        UsersKilled[sender_number] = dead_user 
        del Users[sender_number]
        for i, suser in enumerate(ShuffledUsers):
            if suser.number == dead_user.number:
	            del ShuffledUsers[i]
        message = "you've been removed from the game.. sucker."
        sendSMS(sender_number, message)"""
    if not Words.has_key(word):
        sendSMS(sender_number, "the fuck broah. follow the rules")
    else:
        killer = Users[sender_number]
        target = Users[killer.target_number]
        if not word == target.secret_word:
            sendSMS(sender_number, "the fuck broah. follow the rules")
        else:
            killer.target_name = target.target_name
            killer.target_number = target.target_number
            UsersKilled[target.number] = target
            del Users[target.number]
            for i, suser in enumerate(ShuffledUsers):
                if suser.number == target.number:
	                 del ShuffledUsers[i]
            message = "you've been removed from the game.. sucker."
            sendSMS(target.number, message)

    # End game if there are two or less users
    if len(Users) <= 2:
        Users = {}

        winners = ''
        for user in Users.values():
            sendSMS(user.number, "You freakin WON! Now you have the flower powers.")
            winners += user.name + ' '
        for user in UsersKilled.values():
            sendSMS(user.number, "Loser. Congratulate these bad boys: " + winners)

    return 'ok' 

# Deprecated
def updateTarget(user_killed):
    for user in Users.values():
        if user.target_number == user_killed.number:
            user.target_number = user_killed.target_number  
            user.target_name = user_killed.target_name
            sendSMS(user.number, getPartialCongrats() + "Your new target is: " + user.target_name)
            break


def getPartialCongrats():
    possibleMsgs = ["Nice kill. ",
                    "Great hunt. ",
                    "Get more blood on those hands. ",
                    "Headshot. ",
                    "MOFO is dead. ",
                    "Dead. ",
                    "Good work you beast. "]

    return random.choice(possibleMsgs) 


def sendSMS(phone_num, text):
    from_="+19492163884"
    logging.warn('sending a message from %s to %s with content: %s' % (
            from_, phone_num,  text))
            
    message = client.sms.messages.create(to=phone_num, from_=from_,
                                         body=text)
    return message


def gaming():
    return bool(Users)


@app.route('/fake', methods=['GET'])
def fake():
    # this is just to initialize fake users,
    # so we can test without texting
    global Users
    global ShuffledUsers
    Users = {
        17144175062: User(**{
                "target_name": "daniel gur",
                "target_number": 12169705010,
                "number": 17144175062,
                "name": "Huan",
                "secret_word": "scale"
                }),
        12169705010: User(**{
                "target_name": "Elissa",
                "target_number": 12165482911,
                "number": 12169705010,
                "name": "daniel gur",
                "secret_word": "robust"
                }),
        12165482911: User(**{
                "target_name": "Huan",
                "target_number": 17144175062,
                "number": 12165482911,
                "name": "Elissa",
                "secret_word": "dynamic"
                }),
        14822887950: User(**{
                "target_name": "Huan #2",
                "target_number": 12165482911,
                "number": 14822887950,
                "name": "daniel diaz"
                }),
        }
    ShuffledUsers = Users.values()
    return redirect('/')


@app.route('/', methods=['GET'])
def index():
    if not gaming():
        return render_template('form.html')
    else:
        return render_template('dashboard.html')


@app.route('/startgame', methods=['POST'])
def poststartgame():
    data = request.values['data']

    global Users
    global ShuffledUsers
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
    # This makes sure that there are more secret words than users
    # TODO(esadac): make this more reliable, get more words or something.
    if len(users_list) <= len(Words.values()):
        for user in users_list[:]:
            try:
                sendSMS(user.number,
                       "Get ready. It's about to get real. Your target will be sent shortly.")
            except: 
                logging.warn("Catching exception for " + str(user.number) + " bout to delete...")
                del Users[user.number]
                users_list.remove(user)
   
        random.shuffle(users_list)
        ShuffledUsers = users_list
        for i, user in enumerate(users_list):
            user.target_number = users_list[ (i + 1) % len(users_list)].number
            user.target_name = users_list[ (i + 1) % len(users_list)].name
            user.secret_word = getSecretWord()

        for i, user in enumerate(users_list):
            sendSMS(user.number,
                    "Welcome to the game, your target is: " + Users[user.target_number].name + ". Your secret word is: " + Users[user.number].secret_word)
        
    return 'ok'

# A word is true if it has been used before.
def getSecretWord():
    word = random.choice(Words.keys())
    while Words[word] == True:
        word = random.choice(Words.keys())
    Words[word] = True
    return word

@app.route('/gamestatus', methods=['GET'])
def gamestatus():
    global ShufflesUsers
    users = [user.serialize() for user in ShuffledUsers]
    return json.dumps(users)

if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
