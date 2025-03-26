import os
import config
import requests
from models import User

class UsersDB:
    def __init__(self, db):
        self.db = db

    def hasDataOf(self, id):
        u = User.query.get(id)
        if u is None:
            return False
        return True

    def add(self, id):
        r = requests.get('https://graph.facebook.com/v2.6/' + str(id), params={
            'fields': 'first_name,last_name,gender,profile_pic',
            'access_token': os.environ.get('ACCESS_TOKEN', config.ACCESS_TOKEN)
        })
        data = r.json()
        try:
            first_name = data["first_name"]
        except:
            first_name = ""

        try:
            last_name = data["last_name"]
        except:
            last_name = ""

        name = first_name + " " + last_name
        user = User(id=id)
        user.add_details(name=name, first_name=data["first_name"], gender=data["gender"], pic_url=data["profile_pic"])
        self.db.session.add(user)
        self.db.session.commit()

    def get(self, id):
        user = User.query.get(id)
        return user

    def getPauseStatus(self, id):
        user = User.query.get(id)
        return user.status

    def setPauseStatus(self, id, status):
        user = User.query.get(id)
        user.status = status
        self.db.session.commit()

    def addMessage(self, id, message):
        user = User.query.get(id)
        m = user.messages
        if m == None:
            user.messages = message
        elif len(m.split('#&#')) == 1:
            user.messages = m + "#&#" + message

        self.db.session.commit()

    def getMessages(self, id):
        user = User.query.get(id)
        m = user.messages
        if m == "":
            return None

        user.messages = ""
        self.db.session.commit()

        return m.split("#&#")