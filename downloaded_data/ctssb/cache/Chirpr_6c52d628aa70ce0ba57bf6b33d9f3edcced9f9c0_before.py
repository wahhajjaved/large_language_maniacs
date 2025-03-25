from flask import Blueprint, request, render_template, session, jsonify, redirect
from chirpr.database import mongo, getRequestData, fs
from datetime import datetime
from bson.objectid import ObjectId
import pymongo
import traceback
import time

chirpMod = Blueprint("chirpMod", __name__)


@chirpMod.route('/additem', methods=['POST'])
def addItem():
    error = False
    errorMsg = ''

    if not session.get('loggedIn'):
        error = True
        errorMsg = 'Not logged in'
        return jsonify({'status': 'error', 'error': errorMsg})

    data = getRequestData(request)
    chirps = mongo.db.chirps
    query = {}

    if 'content' not in data:
        error = True
        errorMsg = 'Invalid request'
        return jsonify({'status': 'error', 'error': errorMsg})

    if 'media' in data:
        query['media'] = data['media']

    content = data['content']
    if (len(content) > 140):
        return jsonify({'status': 'error', 'error': 'Chirp is too long'})

    query['content'] = content
    query['username'] = session.get('username')
    query['timestamp'] = datetime.utcnow()
    # query['retweets'] = 0
    # query['replies'] = []
    query['replies'] = 0
    query['likes'] = []

    if 'parent' in data:
        parent = data['parent']
        query['parent'] = parent
    else:
        parent = -1

    chirp = chirps.insert_one(query).inserted_id
    
    if parent >= 0:
        # chirps.update_one({'_id': parent}, {'$push': {'replies': chirp}})
        chirps.update_one({'_id': parent}, {'$inc': {'replies': 1}})

    print "successful login"
    return jsonify({'status': 'OK', 'id': str(chirp)})


@chirpMod.route('/item/<ObjectId:id>', methods=['GET'])
def getChirp(id):
    error = False
    errorMsg = ''
    if id is None:
        print("Invalid Request: ID is None")
        return jsonify({'status': 'error', 'error': 'Invalid request'})

    chirps = mongo.db.chirps
    chirp = chirps.find_one({'_id': id})
    if chirp is None:
        print("Could not find chirp with ID:")
        print id
        return jsonify({'status': 'error', 'error': 'ID not found'})
    chirp['_id'] = str(chirp['_id'])
    return jsonify({'status': 'OK', 'item': chirp})


@chirpMod.route('/item/<ObjectId:id>', methods=['DELETE'])
def deleteChirp(id):
    error = False
    errorMsg = ''
    if id is None:
        print "Invalid Request: ID is None"
        return jsonify({'status': 'error', 'error': 'Invalid request'})

    chirp = mongo.db.chirps.find_one({'_id': id})

    for media_id in chirp['media']:
        if (fs.exists(id)):
            fs.delete(ObjectId(media_id))
    mongo.db.chirps.delete_one({'_id': id})
    return jsonify({'status': 'OK'})


@chirpMod.route('/item/<ObjectId:id>/like', methods=['POST'])
def like(id):
    error = False
    errorMsg = ''
    if not session.get('loggedIn'):
        error = True
        errorMsg = 'Not logged in'
        print "Not logged in"
        print session
        return jsonify({'status': 'error', 'error': errorMsg})

    data = getRequestData(request)
    if 'like' not in data:
        return jsonify({'status': 'error'})

    chirps = mongo.db.chirps
    users = mongo.db.users

    userId = session.get('userId')
    like = data['like']

    # update in both users and chirps
    if like is True:
        chirps.update_one({'_id': id}, {"$push": {"likes": str(userId)}})
        users.update_one({'_id': ObjectId(userId)}, {'$push': {'likes': str(id)}})
    else:
        chirps.update_one({'_id': id}, {"pull": {"likes": str(userId)}})
        users.update_one({'_id': ObjectId(userId)}, {'pull': {'likes': str(id)}})
    return jsonify({'status': 'OK'})


@chirpMod.route('/search', methods=['POST'])
def search():
    chirps = mongo.db.chirps
    users = mongo.db.users
    data = getRequestData(request)
    print data
    query = {'$and': []}

    if not 'timestamp' in data:
        timestamp = datetime.utcnow()
    else:
        timestamp = datetime.utcfromtimestamp(float(data['timestamp']))

    query["$and"].append({"timestamp": {'$lte': timestamp}})

    if 'limit' in data:
        limit = data['limit']
    else:
        limit = 25

    # filter on search query
    if 'q' in data:
        searchquery = data['q']
        query["$and"].append({"$text": {"$search": searchquery}})

    if 'username' in data:
        username = data['username']
        user = users.find_one({'username': username})
        query["$and"].append({"username": {"$eq": user['username']}})

    # get chirps made in reply to requested tweet
    if 'parent' in data:
        parent = data['parent']
        query["$and"].append({"parent": {"$eq": parent}})

    # get chirps made by users you are following
    if session.get('loggedIn') is True:
        if 'following' in data:
            if data['following'] is True or data['following'] is None:
                user = mongo.db.users.find_one({"username": {"$eq": session.get('username')}})
                if 'following' not in user:
                    user['following'] = []
                query["$and"].append({"following": {"$in": user['following']}})

    # sort by interest or time
    if 'rank' in data:
        rank = data['rank']
    else:
        rank = 'interest'

    # get replies for all filtered tweets
    if 'replies' in data:
        replies = data['replies']
    else:
        replies = True

    if rank == 'time':
        print query 
        results = chirps.find(query).sort('timestamp', pymongo.DESCENDING).limit(limit) 
    else:
        # results = chirps.aggregate(query).limit(limit)
        print query
        print limit
        results = chirps.aggregate([
            {'$match': query},
           {'$project': {'content':1, 'replies':1, 'username':1, 'timestamp':1, 'likes':1, 'rank':{"$sum": ["replies", {"$size": "$likes"}]}}},
            {'$sort': {'rank': -1}},
            {'$limit': limit}
        ])

    chirpList = []
    for chirp in results:
        chirp['id'] = str(chirp['_id'])
        chirp['timestamp'] = int(time.mktime(chirp['timestamp'].timetuple()))
        chirp.pop('_id', None)
        chirpList.append(chirp)
    print len(chirpList)
    return jsonify({'status': 'OK', 'items': chirpList})
