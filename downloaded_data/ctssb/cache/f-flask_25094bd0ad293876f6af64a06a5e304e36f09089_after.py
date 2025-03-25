# -*- encoding: utf-8 -*-

from __future__ import print_function, unicode_literals

import os
import sys
import psycopg2
import urlparse
import logging
from random import choice
from flask import Flask, request, jsonify, json
from flask.ext.cors import CORS

app = Flask(__name__)
CORS(app)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)
'''
urlparse.uses_netloc.append('postgres')
if 'USER' in os.environ.keys():
    _sql = psycopg2.connect(database='sonoba')
else:
    url = urlparse.urlparse(os.environ['DATABASE_URL'])


    _sql = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
'''
_sql = psycopg2.connect(
    database='d3url0227u1a8j',
    user='nxhmrfgqqiruum',
    password='oBLYUOl567RIs-1DBy8W-5dC_o',
    host='ec2-23-21-255-14.compute-1.amazonaws.com',
    port='5432'
)
sql = _sql.cursor()

sql.execute('DROP TABLE IF EXISTS rooms')
sql.execute('DROP TABLE IF EXISTS animals')
sql.execute('DROP TABLE IF EXISTS playing_animals')
sql.execute('DROP TABLE IF EXISTS messages')
sql.execute('CREATE TABLE rooms (rid serial PRIMARY KEY, name text)')
sql.execute('CREATE TABLE animals (name text PRIMARY KEY, playing_room INTEGER)')
sql.execute('CREATE TABLE messages (mid serial PRIMARY KEY, time BIGINT, animal text, message text)')

for l in ['山手線']:
    sql.execute("INSERT INTO rooms (name) VALUES ('%s')" % l)

for a in ['dog', 'cat', 'penguin', 'bear']:
    sql.execute("INSERT INTO animals (name, playing_room) VALUES ('%s', 0)" % a)

_sql.commit()

SUCCESS, FAIL = 'SUCCESS', 'FAIL'

@app.route('/')
def index():
    return jsonify({'msg': 'Hello Sonoba!', 'db_info': ''})


@app.route('/rooms', methods=['GET'])
def rooms():
    sql.execute('SELECT * FROM rooms')
    # d = dict((k, v) for k, v in sql.fetchall())
    d = [{'id': lid, 'line': line} for lid, line in sql.fetchall()]
    return json_unicode(d)


@app.route('/rooms/<int:room_id>', methods=['POST'])
def login(room_id):
    sql.execute('SELECT playing_room FROM animals')
    res = sql.fetchall()
    if all(x != 0 for x in [y[0] for y in res]):
        sql.execute('UPDATE animals SET playing_room = 0')
        _sql.commit()

    sql.execute('SELECT rid FROM rooms')
    res = sql.fetchall()

    if room_id not in res:
        sql.execute('SELECT name FROM animals WHERE playing_room = 0')
        animals = sql.fetchall()

        if len(animals) <= 0:
            return json_unicode({'status': FAIL, 'animal': ''})

        animal = choice(animals)

        w = "UPDATE animals SET playing_room = %d WHERE name = '%s'" % (room_id, animal[0])
        sql.execute(w)
        _sql.commit()
        return json_unicode({'status': SUCCESS, 'animal': animal[0]})
    else:
        return json_unicode({'status': FAIL, 'animal': ''})


@app.route('/rooms/<int:room_id>/<user_id>', methods=['DELETE'])
def logout(room_id, user_id):
    sql.execute("SELECT name, playing_room FROM animals WHERE name = '%s' AND playing_room = %s" % (user_id, room_id))
    res = sql.fetchall()

    if len(res) <= 0:
        return json_unicode({'status': FAIL})
    else:
        sql.execute("UPDATE animals SET playing_room = 0 WHERE name = '%s'" % user_id)
        _sql.commit()
        return json_unicode({'status': SUCCESS})


@app.route('/reset_login')
def reset_login():
    sql.execute('UPDATE animals SET playing_room = 0')
    _sql.commit()
    return json_unicode({'status': SUCCESS})


@app.route('/rooms/<int:room_id>/messages', methods=['GET'])
def message_get(room_id):
    since = int(request.args.get('since'))

    sql.execute('SELECT time, animal, message FROM messages WHERE time >= %d' % since)
    res = sql.fetchall()
    d = {'items': [{'time': time, 'animal': animal, 'message': message} for time, animal, message in res]}
    return json_unicode(d)


@app.route('/rooms/<int:room_id>/messages', methods=['POST'])
def message_post(room_id):
    animal = request.values.get('animal')
    message = request.values.get('message')
    time = int(request.values.get('time'))

    sql.execute("INSERT INTO messages (time, animal, message) VALUES (%d, '%s', $$%s$$)" % (time, animal, message))
    _sql.commit()
    return json_unicode({'status': SUCCESS})


@app.route('/rooms/<int:room_id>/<user_id>/is_alive', methods=['POST'])
def is_alive(room_id, user_id):
    if alive_check(room_id, user_id):
        return json_unicode({'status': True})
    else:
        return json_unicode({'status': False})


def json_unicode(obj):
    return json.htmlsafe_dumps(obj).decode('unicode-escape')


def alive_check(room_id, user_id):
    return True

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
