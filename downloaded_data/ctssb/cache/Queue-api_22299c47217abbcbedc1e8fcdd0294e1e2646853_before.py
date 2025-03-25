import datetime
import json
import calendar
import os

from flask import Flask, request
from flask.ext.restful import Resource, Api

import requests

from queue import app, api, db

from models import SongItem, User, Artist, Album, Friend, ArtistItem, NoteItem, UrlsForItem
from fixdata import fix_lastfm_listens_data, fix_image_data, fix_lf_track_search, fix_lf_artist_search, fix_search_metadata


SP_API_URL = app.config['SP_API_URL']
LF_API_URL = app.config['LF_API_URL']
LF_API_KEY = app.config['LF_API_KEY']
FB_API_URL = app.config['FB_API_URL']

@app.route('/db/destroy')
def destroy_db():
    os.remove(app.config['DATABASE_FILE'])
    return 'so it is'


@app.route('/db/create')
def create_db():
    import init_db
    init_db.init_db()
    return 'so it is'

class Search(Resource):
    def get(self, search_text):
        search_url = "%smethod=track.search&track=%s&api_key=%sformat=json"
        track_results = requests.get(search_url %
                        (LF_API_URL, search_text, LF_API_KEY)).json()['results']

        search_url = "%smethod=artist.search&artist=%s&api_key=%sformat=json"
        artist_results = requests.get(search_url %
                        (LF_API_URL, search_text, LF_API_KEY)).json()['results']

        results = {'track_results':fix_lf_track_search(track_results),
                   'artist_results':fix_lf_artist_search(artist_results)}

        return results

class Listens(Resource):
    def get(self, user_name):
        data = requests.get("%smethod=user.getrecenttracks&user=%s&api_key=%sformat=json&extended=1"
                            % (LF_API_URL, user_name, LF_API_KEY)).json()
        return fix_lastfm_listens_data(data)

class Home(Resource):
    def get(self):
        return {"hello":"there"}

class Friends(Resource):
    def get(self, user_name):
        args = request.values
        access_token = args['accessToken']
        user = get_user(user_name)

        if not user:
            return no_such_user(user_name)

        friends = []
        for friend in db.session.query(Friend).filter(Friend.user_id == user.id):
            friends.append(friend.dictify())

        return friends

class UserAPI(Resource):
    def post(self, user_name):

        if get_user(user_name):
           return {'message': 'user already exists'}, 400

        args = request.json
        access_token = args['accessToken']
        fb_id = args['fbId']
        resp = requests.get("%s/%s/friends?limit=5000&access_token=%s" %
                                (FB_API_URL, fb_id, access_token))
        if 'data' not in resp.json():
            return {"message": 'problem getting friends'}, 500

        friends = resp.json()['data']
        friends = []
        user = User(fb_id=fb_id, uname=user_name, access_token=access_token,
                    fullname=args['fullname'], image_link=args['imageLink'])
        for friend in friends:
            f = Friend(full_name=friend['name'], fb_id=friend['id'], user=user)
            db.session.add(f)

        db.session.add(user)
        db.session.commit()

        return {"status":"OK"}


class Queue(Resource):
    def get(self, user_name):

        user = get_user(user_name)

        if not user:
            return no_such_user(user_name)

        songs = db.session.query(SongItem)\
            .filter(SongItem.user_id == user.id).all()
        artists = db.session.query(ArtistItem)\
            .filter(ArtistItem.user_id == user.id).all()
        notes = db.session.query(NoteItem)\
            .filter(NoteItem.user_id == user.id).all()

        orm_queue = songs + artists + notes
        queue = []
        for orm_item in orm_queue:
            queue.append(orm_item.dictify())

        queue = sorted(queue, key=lambda x: (x['listened'], -1*x['dateQueued']))
        return {"queue":{"items":queue}}

    def delete(self, user_name):
        access_token = request.values['accessToken']
        item_type = request.values['type']
        item_id = request.values['itemId']
        user = get_user(user_name)

        if not user.access_token == access_token:
            app.logger.warning("invalid accessTokenfor user %s" % user_name)

            return {'message':'invalid accessToken'}, 400

        if item_type == 'song':
            song = db.session.query(SongItem)\
            .filter(SongItem.user_id == user.id)\
            .filter(SongItem.id == item_id).one()
            db.session.remove(song)
        if item_type == 'artist':
            artist = db.session.query(ArtistItem)\
            .filter(ArtistItem.user_id == user.id)\
            .filter(ArtistItem.id == item_id).one()
            db.session.remove(artist)
        if item_type == 'note':
            note = db.session.query(NoteItem)\
            .filter(NoteItem.user_id == user.id)\
            .filter(NoteItem.id == item_id).one()
            db.session.remove(note)

        db.session.commit()

    def put(self, user_name):
        access_token = request.values['accessToken']
        item_type = request.values['type']
        item_id = request.values['itemId']
        listened = True if request.values['listened'] == 'true' else False
        user = get_user(user_name)

        if not user.access_token == access_token:
            app.logger.warning("invalid accessTokenfor user %s" % user_name)
            return {'message':'invalid accessToken'}, 400

        if item_type == 'song':
            song = db.session.query(SongItem)\
            .filter(SongItem.user_id == user.id)\
            .filter(SongItem.id == item_id).one()
            song.listened = listened
            db.session.add(song)
        if item_type == 'artist':
            artist = db.session.query(ArtistItem)\
            .filter(ArtistItem.user_id == user.id)\
            .filter(ArtistItem.id == item_id).one()
            artist.listened = listened
            db.session.add(artist)
        if item_type == 'note':
            note = db.session.query(NoteItem)\
            .filter(NoteItem.user_id == user.id)\
            .filter(NoteItem.id == item_id).one()
            note.listened = listened
            db.session.add(note)

        db.session.commit()


    def post(self, user_name):

        queue_item = request.json
        from_user_name = queue_item['fromUser']['userName']
        access_token = queue_item['fromUser']['accessToken']
        media = queue_item[queue_item['type']]
        queue_item['dateQueued']=int(queue_item['dateQueued'])

        from_user = get_user(from_user_name)
        to_user = get_user(user_name)

        if not from_user:
            return no_such_user(from_user)

        if not to_user:
            return no_such_user(to_user)

        if not from_user.access_token == access_token:
            app.logger.warning("invalid accessTokenfor user %s" % user_name)
            return {'message':'invalid accessToken'}, 400

        if not is_friends(from_user, to_user):
            app.logger.warning("users %s is not friends" % user_name)
            return {'message':'users are not friends'}, 400

        if queue_item['type'] == 'song':
            spotify_url = get_spotify_link_for_song(media)
            artist = media['artist']
            orm_artist = Artist(name=artist['name'],
                                small_image_link=artist['images']['small'],
                                medium_image_link=artist['images']['medium'],
                                large_image_link=artist['images']['large'])

            album = media['album']
            orm_album = Album(name=album['name'])

            orm_urls = UrlsForItem(spotify_url=spotify_url)

            orm_song = SongItem(user=to_user,queued_by_user=from_user,
                            urls=orm_urls,
                            listened=queue_item['listened'], name=media['name'],
                            date_queued=queue_item['dateQueued'],
                            small_image_link=media['images']['small'],
                                medium_image_link=media['images']['medium'],
                                large_image_link=media['images']['large'])

            orm_song.artist = orm_artist
            orm_song.album = orm_album
            db.session.add(orm_song)
            db.session.add(orm_urls)
            db.session.add(orm_album)
            db.session.add(orm_artist)

        elif queue_item['type'] == 'artist':
            spotify_url = get_spotify_link_for_artist(media)
            orm_urls = UrlsForItem(spotify_url=spotify_url)
            orm_artist = ArtistItem(user=to_user,queued_by_user=from_user,
                            urls=orm_urls,
                            listened=queue_item['listened'], name=media['name'],
                            date_queued=queue_item['dateQueued'],
                            small_image_link=media['images']['small'],
                                medium_image_link=media['images']['medium'],
                                large_image_link=media['images']['large'])

            db.session.add(orm_artist)
            db.session.add(orm_urls)

        elif queue_item['type'] == 'note':
            orm_note = NoteItem(user=to_user,queued_by_user=from_user,
                            listened=queue_item['listened'], text=media['text'],
                            date_queued=datetime.datetime.utcnow())

            db.session.add(orm_note)

        db.session.commit()

        return {"status":"OK"}


def get_user(user_name):
    users = list(db.session.query(User).filter(User.uname == user_name))
    if not users:
        return None

    assert len(users) < 2
    return users[0]

def no_such_user(user_name):

    app.logger.warning("no such user %s" % user_name)
    return {"message":"no such user %s" % user_name}, 400

def is_friends(user1, user2):
    friends = list(db.session.query(Friend).filter(Friend.user_id == user1.id)\
                                 .filter(Friend.user_id == user2.id))
    if not friends:
        return False

    return True

def get_spotify_link_for_song(song):
    search_text = " ".join([song['name'], song['artist']['name'],
                           song['album']['name']])
    resp = requests.get("%s/search/1/track.json?q=%s" % (SP_API_URL, search_text))

    if not resp.json()['tracks']:
        return None

    link = resp.json()['tracks'][0]['href']
    return link

def get_spotify_link_for_artist(artist):
    search_text = artist['name']
    resp = requests.get("%s/search/1/artist.json?q=%s" % (SP_API_URL, search_text))
    link = resp.json()['artists'][0]['href']
    return link






api.add_resource(Home, '/')
api.add_resource(Listens, '/<string:user_name>/listens')
api.add_resource(Friends, '/<string:user_name>/friends')
api.add_resource(UserAPI, '/<string:user_name>')
api.add_resource(Queue, '/<string:user_name>/queue')
api.add_resource(Search, '/search/<string:search_text>')


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

