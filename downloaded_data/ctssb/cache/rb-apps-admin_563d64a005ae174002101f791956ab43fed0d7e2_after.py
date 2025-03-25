#!/usr/bin/env python
# Copyright 2015 Magnus Bengtsson

# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
import json
import pytz
import subprocess
import re
from functools import wraps
from flask import request, abort, Response
from flask.ext import restful
from flask.ext.restful import reqparse
from rb_apps_admin import app, api, mongo
from bson.objectid import ObjectId
from datetime import *
from dateutil.relativedelta import *



def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == app.config['AUTH_USER'] and password == app.config['AUTH_PASSWORD']

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

class Resource(restful.Resource):
    method_decorators = [requires_auth]   # applies to all inherited resources


class ApplicationList(Resource):
    def __init__(self, *args, **kwargs):
        self.parser = reqparse.RequestParser()
        self.parser.add_argument('user', type=str)
        super(ApplicationList, self).__init__()

    def get(self):
        args = self.parser.parse_args()
        if args['user']:
            user_id = mongo.db.cloud_users.find_one_or_404({"login": args['user']})
            print user_id
            return [x for x in mongo.db.applications.find({"owner_id": user_id['_id']})]
        return [x for x in mongo.db.applications.find()]


class Application(Resource):
    def get(self, application_id):
        return mongo.db.applications.find_one_or_404({"_id": application_id})


class User(Resource):
    def __init__(self, *args, **kwargs):
        self.parser = reqparse.RequestParser()
        self.parser.add_argument('limit', type=self.is_valid_limit)
        super(User, self).__init__()

    def get(self, login):
        return mongo.db.cloud_users.find_one_or_404({"login": login})

    def put(self, login):
        args = self.parser.parse_args()
        user = mongo.db.cloud_users.find_one_or_404({"login": login})
        if args['limit']:
            return mongo.db.cloud_users.update({'_id': user['_id']}, {'$set': {'capabilities': self.limit_template(args['limit'])}}), 201
        else:
            raise ValueError('This interface needs a limit parameter')

    def post(self, login):
        pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"

        if re.match(pattern, login):
            # create a new user, uses a setuid on /opt/redbridge/bin/rbapps-user (that runs oo-admin-ctl-user -c -l $1)
            try:
                subprocess.check_call(["/opt/redbridge/bin/rbapps-user", login])
                if args['limit']:
                    limit = args['limit']
                else:
                    limit = "regular"
                user = mongo.db.cloud_users.find_one_or_404({"login": login})
                mongo.db.cloud_users.update({'_id': user['_id']}, {'$set': {'capabilities': self.limit_template(limit)}})
                return "created", 201
            except:
                return "error creating user", 400
        return "invalid username", 400

    def is_valid_limit(self, value, name):
        limits = ['limited', 'regular', 'premium']
        if value not in limits:
            raise ValueError("The limit '{}' is not valid. valid limits are {}".format(value, limits))
        return value

    def limit_template(self, limit):
        template = {
            'limited': {
                'max_domains': 1,
                'max_gears': 2,
                'max_tracked_addtl_storage_per_gear': 0,
                'max_teams': 0,
                'private_ssl_certificates': False,
                'ha': False,
                'subaccounts': False,
                'max_untracked_addtl_storage_per_gear': 0,
                'view_global_teams': False,
                'gear_sizes': ['small']
            },
            'regular': {
                'max_domains': 5,
                'max_gears': 16,
                'max_tracked_addtl_storage_per_gear': 10,
                'max_teams': 5,
                'private_ssl_certificates': True,
                'ha': False,
                'subaccounts': False,
                'max_untracked_addtl_storage_per_gear': 0,
                'view_global_teams': False,
                'gear_sizes': ['small', 'medium', 'large']
            },
            'premium': {
                'max_domains': 10,
                'max_gears': 64,
                'max_tracked_addtl_storage_per_gear': 20,
                'max_teams': 10,
                'private_ssl_certificates': True,
                'ha': False,
                'subaccounts': False,
                'max_untracked_addtl_storage_per_gear': 0,
                'view_global_teams': False,
                'gear_sizes': ['small', 'medium', 'large']
            }

        }
        return template[limit]


class UsersList(Resource):
    def get(self):
        return [{'login': x['login']} for x in mongo.db.cloud_users.find()]


class Usage(Resource):
    def __init__(self, *args, **kwargs):
        self.parser = reqparse.RequestParser()
        self.parser.add_argument('start_date', type=str)
        self.parser.add_argument('end_date', type=str)
        super(Usage, self).__init__()

    def get(self, login):
        args = self.parser.parse_args()
        now = datetime.now()
        if args['start_date']:
            try:
                start_date = datetime.strptime(args['start_date'], '%Y-%m-%d')
            except:
                start_date = now - relativedelta(day=1, hour=0, minute=0, second=0)
        else:
            start_date = now - relativedelta(day=1, hour=0, minute=0, second=0)
        if args['end_date']:
            try:
                end_date = datetime.strptime(args['end_date'], '%Y-%m-%d')
                if not end_date > start_date:
                    end_date = now - relativedelta(day=31, hour=0, minute=0, second=0)
            except:
                end_date = now - relativedelta(day=31, hour=0, minute=0, second=0)
        else:
            end_date = now - relativedelta(day=31, hour=0, minute=0, second=0)
        # localize dates
        start_date = pytz.utc.localize(start_date)
        end_date = pytz.utc.localize(end_date)
        # get all usage without an end_time, calculate gear usage between start_date and now
        # get all gear usage with an end time
        user_id = mongo.db.cloud_users.find_one_or_404({"login": login})
        q = {'user_id': user_id['_id']}
        q['$or'] = [{'end_time': None}, {'end_time': {'$gte': start_date}}]
        q['begin_time'] = {'$lte': end_date}
        print q
        gears = [x for x in mongo.db.usage.find(q)]
        print len(gears)
        for gear in gears:
            if not gear.has_key('end_time'):
                end_time = pytz.utc.localize(now)
            else:
                end_time = gear['end_time']
            if gear['begin_time'] < start_date:
                start_time = start_date
            else:
                start_time = gear['begin_time']
            gear['runtime_hours'] = self.total_seconds((end_time - start_time)) // 3600
            print "Usage: %s Gear: %s - Start: %s End: %s Runtime: %s Hours" % (gear['usage_type'], gear['app_name'], start_time, end_time, gear['runtime_hours'])
        return gears

    def total_seconds(self, td):
        return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6

class Root(Resource):
    def get(self):
        return {
            'status': 'OK',
            'mongo': str(mongo.db),
        }

api.add_resource(Root, '/')
api.add_resource(ApplicationList, '/applications')
api.add_resource(Application, '/application/<ObjectId:application_id>')
api.add_resource(User, '/user/<login>')
api.add_resource(UsersList, '/users')
api.add_resource(Usage, '/usage/<login>')
