from flask import render_template, redirect, request
from app import app, db, models
from models import Player

import twilio.twiml
from twilio.rest import TwilioRestClient

account_sid = "AC6202a281694e94d9df7485b5d21b5dcd"
auth_token  = "8b213cfb31f8b3e4a355fb913ebfde69"


@app.route("/", methods=['GET', 'POST'])
def hello():

    players = models.Player.query.all()

    if request.method == 'POST':
        from_number = request.values.get('From', None)
        text = request.values.get('Body', None)
        print(text)
        client = TwilioRestClient(account_sid, auth_token)


    return render_template("players.html", players=players)



@app.route("/players", methods=['GET', 'POST'])
def players():
    
    body = request.values.get('Body', None)
    from_number = request.values.get('From', None)

    numbers = get_numbers()

    if from_number not in numbers:
        player = models.Player(number=from_number)
        db.session.add(player)
        db.session.commit()
        msg = "number not in database"
    else:
        msg = "number in database"

    resp = twilio.twiml.Response()
    resp.message(msg)
    return str(resp)



def get_numbers():
    numbers = []
    players = db.query.all()

    for player in players:
        numbers.add(player.number)
    
    return players
