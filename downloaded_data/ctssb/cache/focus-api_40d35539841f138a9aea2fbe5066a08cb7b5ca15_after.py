#!/usr/bin/env python2.6
#!/usr/bin/env python2.6
# vim: set fileencoding=utf-8

import datetime
import time
import tornado
import pymongo
from bson.objectid import ObjectId
import smtplib
from random import choice
import string
from password import Password

from email.Header import Header
from email.MIMEMultipart import MIMEMultipart
from email.mime.text import MIMEText

import api_base

class RootHandler(api_base.BaseHandler):
    """Root API that validates credentials.
    """

    api_path = '/'

    @api_base.auth
    def get(self):
        """Example API for authorization."""

class UserHandler(api_base.BaseHandler):
    """User handler, which can create user and modify user profiles.
    """

    api_path = '/user/([^/]*)'
    profile_key_modifiable = ('first_name', 'last_name', 'password',
            'status', 'gender', 'language', 'work_field', 'location',
            'population_target', 'mobile_countrycode', 'mobile',
            'email_type', 'street', 'city', 'province', 'zip', 'country',
            'skype_ID', 'organization_address', 'organization_name',
            'organization_acronym', 'organization_formed_date',
            'organization_website', 'organization_type',
            'organization_employee_num', 'organization_budget',
            'organization_phone_countrycode', 'organization_phone')
    profile_key_checkable = ('_id', 'first_name', 'last_name', 'status',
            'role', 'gender', 'language', 'work_field', 'location',
            'population_target', 'mobile_countrycode', 'mobile',
            'email_type', 'street', 'city', 'province', 'zip',
            'country', 'skype_ID', 'organization_address',
            'organization_name', 'organization_acronym',
            'organization_formed_date', 'organization_website',
            'organization_type', 'organization_employee_num',
            'organization_budget', 'organization_phone_countrycode',
            'organization_phone',  'follower',  'following',
            'tags_following',  'activity_following')
    profile_key_enum = {'gender':('male', 'female', 'secrecy'),
            'role':('admin', 'fellow'), 'email_type':('home', 'business'),
            'organization_type':
            ('Private sector','Government Agency','Multilateral'),
            'organization_employee_num':
            ('less than 10', '11-25', '26-40', '41-60', '61-80', '81-100',
                '101-150', '151-200', 'more than 200'),
            'organization_budget':('less than $50,000', '$50,000-$100000',
                '$100,000-$200,000','$200,000-$500,000',
              '$500,000-$1,000,000', '$1,000,000-$5,000,000',
              '$5,000,000-$10,000,000', 'more than $10,000,000')}

    @api_base.auth
    @api_base.json
    def post(self, login):
        """Create a new user."""

        if self.get_user_role() != 'admin':
            raise tornado.web.HTTPError(403)

        try:
            for key in ('email', 'first_name', 'last_name', 'role'):
                self.req[key] = str(self.req[key])
        except KeyError:
            raise tornado.web.HTTPError(400)

        if self.req['role'] not in ('fellow', 'admin'):
            raise tornado.web.HTTPError(400)

        self.req['created_at'] = int(time.time())

        try:
            self.mongo.user.insert({"_id": self.req['email'], "first_name":
                self.req['first_name'], "last_name": self.req['last_name'],
                "role": self.req['role'],  'following': [], 'follower': [],
                'tags_following': [], 'activity_following': []})

        except pymongo.errors.DuplicateKeyError:
            raise tornado.web.HTTPError(409)

        useractivity = {"title": self.req['first_name'] + " Register", "type": "people",
                                   "description": "Hi,everyone. I'm " + self.req['first_name'] + ". Glad to join the OmarHub!",
                                   "owner": self.req['email'], "created_at": int(time.time()),
                                   "publish": True, "tags": ["User"]}
        self.mongo.activity.insert(useractivity)

        # send activation email
        cookbook = string.ascii_letters + string.digits
        link = ''.join([choice(cookbook) for i in range(0,64)])
        msg = 'This is from focus team, here is your activation link: \r\n http://localhost:49258/OmarHub/login.aspx?hash=' + link
        subject = 'Welcome to OmarHub!'

        try:
            sendmail(self.req['email'], subject, msg)
        except smtplib.SMTPHeloError:
            raise tornado.web.HTTPError(503)

        self.mongo.user.update({"_id": self.req['email']},
                {"$set": {"validation_link": link}})

    @api_base.auth
    def get(self, email):
        """Get user profile"""

        profile = self.mongo.user.find_one({"_id" : email})

        if (profile is None):
            raise tornado.web.HTTPError(404)

        profile['activity_following'] = [str(activity_id) for activity_id in profile['activity_following']]
        profile['tags_following'] = [str(tag_id) for tag_id in profile['tags_following']]

        self.res = self.restrict_to(profile, self.profile_key_checkable)
        self.res['email'] = self.res['_id']
        del(self.res['_id'])

    @api_base.auth
    def delete(self, email):
        """Delete user profile"""

        if self.get_user_role() != 'admin':
            raise tornado.web.HTTPError(403)

        profile = self.mongo.user.find_one({"_id" : email})

        if (profile is None):
            raise tornado.web.HTTPError(404)

        self.mongo.user.remove({"_id": email})
        self.mongo.activity.remove({"type": "people", "owner": email})

    @api_base.auth
    @api_base.json
    def put(self, email):
        """Modify user profile.
        """

        if self.get_user_role() != 'admin' and \
                not (self.get_user_role() == 'fellow' and \
                email == self.current_user):
                    raise tornado.web.HTTPError(403)

        if self.mongo.user.find_one({'_id': email}) is None:
            raise tornado.web.HTTPError(404)

        self.restrict_to(self.req, self.profile_key_modifiable)
        for key in self.req.keys():
            if key in self.profile_key_enum.keys():
                if self.req[key] not in self.profile_key_enum[key]:
                    raise tornado.web.HTTPError(400)

        if self.req.has_key('password'):
            from password import Password
            self.req['password'] = Password.encrypt(self.req['password'])

        try:
            self.mongo.user.update({'_id': email}, {'$set': self.req})
        except pymongo.errors.DuplicateKeyError:
            raise tornado.web.HTTPError(409)

class ActivityHandler(api_base.BaseHandler):
    """Post and view activities."""

    api_path = '/activity'

    @api_base.auth
    @api_base.json
    def post(self):
        try:
            for key in ('title', 'description', 'type'):
                self.req[key] = str(self.req[key])

            self.req['publish'] = bool(self.req['publish'])

            if self.req.has_key(('start_at', 'end_at')):
                for key in ('start_at', 'end_at'):
                    self.req[key] = int(self.req[key])
        except KeyError:
            raise tornado.web.HTTPError(400)

        self.req['owner'] = self.current_user
        self.req['created_at'] = int(time.time())

        if self.req['type'] not in ('offer', 'need', 'event'):
            raise tornado.web.HTTPError(400)
        if not isinstance(self.req['tags'], list):
            raise tornado.web.HTTPError(400)

        for tag in self.req['tags']:
            if not self.mongo.tag.find_one({"_id": tag}):
                self.mongo.tag.insert({"_id": tag, 'follower': [],
                'follower_count': 0})

        activity_id = self.mongo.activity.insert(self.req)
        self.set_status(201)
        self.set_header('Location', '/activity/' + str(activity_id))

    @api_base.auth
    def get(self):
        offset = self.get_argument('offset', 0)
        limit = self.get_argument('limit', 20)
        activity_type = self.get_argument('type', None)
        sort_by = self.get_argument('sort_by', None)
        event_type = self.get_argument('event_type', None)
        all_user = self.get_argument('all_user', 'all')
        year_joined = self.get_argument('year_joined', None)
        tags = self.get_argument('tags', None)

        offset = int(offset)
        limit = int(limit)
        if year_joined is not None:
            year_joined = int(year_joined)
        if tags:
            tags = tags.split(' ')

        if activity_type not in (None, 'offer', 'need', 'event', 'people'):
            raise tornado.web.HTTPError(400)
        if sort_by not in (None, 'most_followed', 'most_recent'):
            raise tornado.web.HTTPError(400)
        if activity_type != 'event' and event_type is not None:
            raise tornado.web.HTTPError(400)
        if event_type not in (None, 'upcoming', 'past', 'ongoing'):
            raise tornado.web.HTTPError(400)
        if activity_type != 'people' and year_joined is not None:
            raise tornado.web.HTTPError(400)
        if all_user not in ('all', 'following'):
            raise tornado.web.HTTPError(400)

        query = {}
        if self.user_role == 'fellow':
            query['$or'] = [{'publish': True}, {'owner': self.current_user}]
        if activity_type:
            query['type'] = activity_type
        if event_type:
            now = int(time.time())
            if event_type == 'upcoming':
                query['start_at'] = {'$gt': now}
            elif event_type == 'ongoing':
                query['start_at'] = {'$lte': now}
                query['end_at'] = {'$gte': now}
            elif event_type == 'past':
                query['end_at'] = {'$lt': now}
        if all_user == 'following':
            query['follower'] = self.current_user
        if year_joined:
            year_start = time.mktime((year_joined, 1, 1, 0, 0, 0, 0, 0, 0))
            year_end = time.mktime((year_joined, 12, 31, 0, 0, 0, 0, 0, 0))
            query['created_at'] = {'$gte': year_start, '$lte': year_end}
        if tags:
            query['tags'] = {'$in': tags}

        if sort_by == 'most_followed':
            sort = [('follower_count', pymongo.DESCENDING), ('created_at', pymongo.DESCENDING)]
        else:
            sort = [('created_at', pymongo.DESCENDING)]

        activity_array = self.mongo.activity.find(query).sort(sort).skip(offset).limit(limit)

        self.res = {'activity': []}
        for activity in activity_array:
            activity['id'] = str(activity['_id'])
            del(activity['_id'])
            if activity.has_key('follower_count'):
                del(activity['follower_count'])
            self.res['activity'].append(activity)

class GetUserActivityHandler(api_base.BaseHandler):
    """get some user's activities"""

    api_path = '/user/([^/]*)/activity'

    @api_base.auth
    def get(self, email):
        """get activities created by user (email)"""
        offset = self.get_argument('offset', 0)
        limit = self.get_argument('limit', 20)

        offset = int(offset)
        limit = int(limit)

        if not self.mongo.user.find_one({"_id": email}):
            raise tornado.web.HTTPError(404)

        query = {'owner': email}
        if self.user_role == 'fellow' and self.current_user != email:
            query['publish'] = True
        activity_array = self.mongo.activity.find(query).\
        sort('created_at', pymongo.DESCENDING).skip(offset).limit(limit)

        self.res = {'activity': []}
        for activity in activity_array:
            activity['id'] = str(activity['_id'])
            del(activity['_id'])
            if activity.has_key('follower_count'):
                del(activity['follower_count'])
            self.res['activity'].append(activity)

class EditActivityHandler(api_base.BaseHandler):
    """edit and delete an activity"""

    api_path = '/activity/([^/]*)'
    activity_key_modifiable = ('description', 'title', 'start_at', 'end_at',
    'publish')
    activity_key_checkable = ('description', 'title', 'type', 'start_at',
    'end_at', 'created_at', 'publish', 'owner', 'follower',  'tags',
    'comment')

    @api_base.auth
    def get(self, activity_id):
        """Get activity information"""

        activity = self.mongo.activity.find_one({"_id" : ObjectId(activity_id)})
        if (activity is None):
            raise tornado.web.HTTPError(404)

        if not bool(activity['publish']) and self.get_user_role() != 'admin' and \
                not (self.get_user_role() == 'fellow' and \
                activity['owner'] == self.current_user):
                    raise tornado.web.HTTPError(403)

        self.res = self.restrict_to(activity, self.activity_key_checkable)

    @api_base.auth
    def delete(self, activity_id):
        """delete activity"""

        activity_id = ObjectId(activity_id)
        activity = self.mongo.activity.find_one({"_id": activity_id})
        if (activity is None):
            raise tornado.web.HTTPError(404)

        if self.get_user_role() != 'admin' and \
                not (self.get_user_role() == 'fellow' and \
                activity['owner'] == self.current_user):
                    raise tornado.web.HTTPError(403)

        self.mongo.activity.remove({"_id": activity_id})

    @api_base.auth
    @api_base.json
    def put(self, activity_id):
        """Modify activity."""

        activity_id = ObjectId(activity_id)
        activity = self.mongo.activity.find_one({"_id": activity_id})
        if (activity is None):
            raise tornado.web.HTTPError(404)

        if self.get_user_role() != 'admin' and \
                not (self.get_user_role() == 'fellow' and \
                activity['owner'] == self.current_user):
                    raise tornado.web.HTTPError(403)

        self.restrict_to(self.req, self.activity_key_modifiable)
        for key in self.req.keys():
            activity[key] = self.req[key]
        if self.req.has_key('publish'):
            if self.req['publish'] != True and self.req['publish'] != False:
                raise tornado.web.HTTPError(400)
        self.mongo.activity.update({"_id": activity_id}, {"$set": self.req})

class GetFollowHandler(api_base.BaseHandler):
    """Get follow status."""

    api_path = '/user/([^/]*)/follow'

    @api_base.auth
    def get(self, login):
        self.res = self.mongo.user.find_one({'_id': login}, {'following': 1, 'follower': 1,
            'tags_following': 1, 'activity_following': 1})
        self.res['email'] = str(login)

        profile['activity_following'] = [str(activity_id) for activity_id in profile['activity_following']]
        profile['tags_following'] = [str(tag_id) for tag_id in profile['tags_following']]

        del self.res['_id']

class PutFollowHandler(api_base.BaseHandler):
    """Modify follow status"""

    api_path = '/user/([^/]*)/follow/([^/]*)/([^/]*)'

    def follow_to(self, login, follow_type, follow_id, isfollow):
        follow_key = {'user': 'following', 'activity': 'activity_following',
                'tag': 'tags_following'}[follow_type]

        if isfollow:
            if self.mongo.user.find_one({'_id': login,
                follow_key: follow_id}):
                raise tornado.web.HTTPError(409)
            self.mongo.user.update({'_id': login},
                    {'$push': {follow_key: follow_id}})
            self.mongo[follow_type].update({'_id': follow_id},
                    {'$push': {'follower': login},
                        '$inc': {'follower_count': 1}})
        else:
            if not self.mongo.user.find_one({'_id': login,
                follow_key: follow_id}):
                raise tornado.web.HTTPError(409)
            self.mongo.user.update({'_id': login},
                    {'$pull': {follow_key: follow_id}})
            self.mongo[follow_type].update({'_id': follow_id},
                    {'$pull': {'follower': login},
                        '$inc': {'follower_count': -1}})

    @api_base.auth
    @api_base.json
    def put(self, login, follow_type, follow_id):
        if self.current_user != login:
            raise tornado.web.HTTPError(403)
        if follow_type not in ('user', 'activity', 'tag'):
            raise tornado.web.HTTPError(400)

        if follow_type != 'user':
            follow_id = ObjectId(follow_id)
        if not self.mongo[follow_type].find_one({'_id': follow_id}):
            raise tornado.web.HTTPError(404)

        if follow_type == 'activity':
            activity = self.mongo.activity.find_one({'_id':follow_id})
            if activity['type'] == 'people':
                self.follow_to(login, 'user', activity['owner'], self.req['follow'])

        if follow_type == 'user':
            activity = self.mongo.activity.find_one({'owner': follow_id, 'type': 'people'})
            self.follow_to(login, 'activity',  activity['_id'],  self.req['follow'])

        self.follow_to(login, follow_type, follow_id, self.req['follow'])

class CommentHandler(api_base.BaseHandler):
    """respond to an activity."""

    api_path = '/activity/(.*)/comment'

    @api_base.auth
    @api_base.json
    def post(self, activity_id):
        activity_id = ObjectId(activity_id)
        activity = self.mongo.activity.find_one({'_id': activity_id})
        if activity is None:
            raise tornado.web.HTTPError(404)
        comment = {}
        comment['description'] = self.req['description']
        comment['created_at'] = int(time.time())
        comment['owner'] = self.current_user
        if activity.has_key('comment'):
            activity['comment'].append(comment)
        else:
            activity['comment'] = [comment]
        self.mongo.activity.update({'_id': activity_id},
                {"$set": {'comment': activity['comment']}} )

class ActivationHandler(api_base.BaseHandler):
    """activate the user"""

    api_path = '/user/validation/(\w+)'

    @api_base.json
    def put(self, validation_link):
        login = self.req['email']
        password = Password.encrypt(self.req['password'])
        if not self.mongo.user.find_one({"_id": login, "validation_link": validation_link}):
            raise tornado.web.HTTPError(404)
        self.mongo.user.update({"validation_link": validation_link},
                {"$set": {"password": password}})
        self.mongo.user.update({"validation_link": validation_link},
                {"$unset": {"validation_link": 1}})

class TagsHandler(api_base.BaseHandler):
    """Get and delete a tag
    """

    api_path = '/tags/([^/]*)'
    tag_key_checkable = ('_id', 'follower')

    @api_base.auth
    def get(self, tag_id):
        """Get all tag"""

        offset = self.get_argument('offset', 0)
        limit = self.get_argument('limit', 20)
        all_tag = self.get_argument('all_tag',  'True')
        all_tag = all_tag == 'True'

        if all_tag:
            tag_array = self.mongo.tag.find(). \
            sort([('_id', pymongo.ASCENDING)]).skip(offset).limit(limit)
        else:
            tag_array = self.mongo.tag.find({'follower': self.current_user}). \
            sort([('_id', pymongo.ASCENDING)]).skip(offset).limit(limit)

        self.res = {'tags': []}

        self.res['tags'] = [self.restrict_to(tag,  self.tag_key_checkable) for tag in tag_array]
        for tag in self.res['tags']:
            tag['id']=tag['_id']
            del(tag['_id'])

    @api_base.auth
    def delete(self, tag_id):
        """Delete tag"""

        tag = self.mongo.tag.find_one({"_id": tag_id})
        if (tag is None):
            raise tornado.web.HTTPError(404)

        if self.get_user_role() != 'admin':
            raise tornado.web.HTTPError(403)

        self.mongo.tag.remove({"_id": tag_id})

def sendmail(toaddr, subject, text):
    """utility to send mail"""

    msg = MIMEMultipart()
    server = 'smtp.qq.com'
    fromaddr = '324823396@qq.com'
    s = smtplib.SMTP(server)
    s.set_debuglevel(1)
    s.login("324823396@qq.com","5gmailqq")
    msg['to'] =toaddr
    msg['from'] = 'admin@OmarHub.com'
    msg['subject'] = Header(subject, 'gb2312')
    msg.attach(MIMEText(text))
    print '!!!', msg
    s.sendmail(fromaddr,toaddr,msg.as_string())
    s.quit()
