from constants import *
from exceptions import *
from descriptors import *
import mongo
import pymongo
import time
import datetime

class Messenger:
    def __init__(self, channel):
        self.channel = channel

    @static_property
    def collection(cls):
        return mongo.get_collection('messages')

    def publish(self, message):
        self.collection.insert({
            'time': datetime.datetime.utcnow(),
            'channel': self.channel,
            'message': message,
        })

    def subscribe(self):
        try:
            cursor_id = self.collection.find({
                'channel': self.channel,
            }).sort('$natural', pymongo.DESCENDING)[0]['_id']
        except IndexError:
            cursor_id = None
        while True:
            try:
                spec = {
                    'channel': self.channel,
                }
                if cursor_id:
                    spec['_id'] = {'$gt': cursor_id}
                cursor = self.collection.find(spec, tailable=True,
                    await_data=True).sort('$natural', pymongo.DESCENDING)
                while cursor.alive:
                    for doc in cursor:
                        cursor_id = doc['_id']
                        yield doc
            except pymongo.errors.AutoReconnect:
                time.sleep(0.1)
