import logging
from defaults import *
import webapp2
import vendor
vendor.add("lib")
from instagram.client import InstagramAPI
from users import *
import json
from oneself import *
from webapp2_extras import sessions
from google.appengine.ext import deferred


scope = raw_scope.split(' ')
if not scope or scope == [""]:
    scope = ["basic"]

api = InstagramAPI(client_id=INSTAGRAM_CLIENT_ID, client_secret=INSTAGRAM_CLIENT_SECRET, redirect_uri=INSTAGRAM_REDIRECT_URL)

sessions.default_config['secret_key'] = APP_SESSION_SECRET
sessions.default_config['cookie_name'] = 'oneself_cookie'

class MainPage(webapp2.RequestHandler):

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session()

    def get(self):
        oneself_userName = self.request.get("username")
        oneself_regToken = self.request.get("token")

        if (oneself_userName == "") or (oneself_regToken == ""):
            self.response.write("1self metadata not found")
            return

        self.session_store = sessions.get_store(request=self.request)
        self.session['oneself_userName'] = oneself_userName
        self.session['oneself_regToken'] = oneself_regToken
        
        self.session_store.save_sessions(self.response)

        auth_uri = api.get_authorize_login_url(scope = scope)
        logging.info("Redirecting to: %s" % auth_uri)

        self.redirect(auth_uri)

class AuthRedirect(webapp2.RequestHandler):
    
    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session()

    def get(self):
        code = self.request.get('code')
        user_metadata = api.exchange_code_for_access_token(code)
        access_token, user_info = user_metadata

        logging.info("Access token successfully found: %s" % access_token)
        logging.info("User info fetched successfully: %s" % user_info)

        self.session_store = sessions.get_store(request=self.request)
        oneself_userName = self.session.get("oneself_userName")
        oneself_regToken = self.session.get("oneself_regToken")

        stream = register_stream(oneself_userName, oneself_regToken, user_info["id"])



        user = User()
        user.access_token = access_token
        user.full_name = user_info["full_name"]
        user.uid = user_info["id"]
        user.username = user_info["username"]
        user.profile_picture = user_info["profile_picture"]
        user.stream_id = stream["streamid"]
        user.oneself_readToken = stream["readToken"]
        user.oneself_writeToken = stream["writeToken"]
        
        logging.info("%s" % user)

        key = user.put()

        logging.info("User stored successfully. Key id: %s" % key)
        logging.info("Instagram UserId: %s" % user.uid)

        lastSyncDate = datetime(1, 1, 1)
        logging.info("Date time is: %s" % lastSyncDate)

        events = []
        events.append(sync_event("start"))
        sendTo1self(user, events)

        deferred.defer(syncOffline, user, lastSyncDate)
        self.redirect("" + ONESELF_APP_ENDPOINT + ONESELF_AFTER_SETUP_REDIRECT)

class HandlePushFromInstagram(webapp2.RequestHandler):
    def get(self):
        challenge = self.request.get('hub.challenge')
        self.response.write(challenge)

    def post(self):
        # eas: disabled the pushes, we poll instead
        jsonstring = self.request.body
        jsonobject = json.loads(jsonstring)
        # logging.info("Request received from instagram: %s" % jsonobject)
        # formatAndSend(jsonobject)
        logging.info("Request received from instagram: %s" % jsonobject)
        self.response.write("success")

class Nothing(webapp2.RequestHandler):
    def get(self):
        self.response.write("Sorry, there is nothing here")


class HandleOfflineSyncRequest(webapp2.RequestHandler):
    def get(self):
        stream_id = self.request.get('streamid')
        stringLastSync = self.request.get('latestSyncField')
        logging.info(stringLastSync)
        logging.info(stringLastSync == 'null')
        if stringLastSync == "undefined" or stringLastSync is None or stringLastSync == 'null':
            logging.info("last sync is null")
            stringLastSync == "2000-01-01T00:00:00"
        #eas: sometimes the format of latest sync field comes with milliseconds and timezone information. Haven't 
        #figured out why this in the platform yet, but here we want to guard against it by substringing
        logging.info(stringLastSync)
        if len(stringLastSync) == 28:
            logging.info("Long format of last sync date detected")
            latestSyncField = datetime.strptime(stringLastSync[:23], "%Y-%m-%dT%H:%M:%S.%f")
        else:
            logging.info("short format of last sync date detected")
            latestSyncField = datetime.strptime(stringLastSync[:23], "%Y-%m-%dT%H:%M:%S")

        
        logging.info("{0}: sync started, last sync: {1}".format(stream_id, latestSyncField.isoformat()))
        user = get_user_by_stream_id(stream_id)

        logging.info("user: {0}".format(user))

        events = []
        events.append(sync_event("start"))
        sendTo1self(user, events)

        syncOffline(user, latestSyncField)
        self.response.write("Sync finished successfully")

class UpgradeSchema(webapp2.RequestHandler):
    def get(self):
        update_user_stream_id(logging)



def formatAndSend(data):
    #currently instagram supports only media post notification
    #theoritically data will only come for 1 user, still iterating
    #we have to send each media upload as an event to 1self
    #logic may have to change as we support more

    for d in data:
        userid = d["object_id"]
        logging.info("Finding user with id: %s" % userid)
        user = getUserByInstagramId(userid)
        logging.info("User found with: %s" % userid)
        sendMediaUpload(user)


def sendMediaUpload(user):
    events = []
    events.append(media_upload_event())
    sendTo1self(user, events)

def dump(prelude, obj):
  for attr in dir(obj):
    print "%s: obj.%s = %s" % (prelude ,attr, getattr(obj, attr))

def upload_event(media):
    return {
        "source": APP_SOURCE,
        "actionTags": STANDARD_ACTION_TAGS + ["share", "publish"],
        "objectTags": STANDARD_OBJECT_TAGS + ["media", "photo"],
        "dateTime": media.created_time.isoformat(),
        "latestSyncField": media.created_time.isoformat(),
        "properties": {
            "likes": media.like_count,
            "comments": media.comment_count,
            }
        }

def syncOffline(user, latestSyncDate):
    logging.info("{0}: User found, user id".format(user.username, user.uid))
    logging.info("{0}: syncing to {1}".format(user.username, latestSyncDate))

    events = []
    logging.info("")

    instagram_client = InstagramAPI(access_token=user.access_token, client_secret=INSTAGRAM_CLIENT_SECRET)
    user_details = instagram_client.user(user.uid)
    logging.info("User details: %s" % user_details.counts)
    recent_media, next_ = api.user_recent_media(user_id=user.uid, access_token=user.access_token, count=10)

    events = []
    for media in recent_media:
        #logging.info("date comparison {0} vs {1} is {2}".format(media.created_time, latestSyncDate, media.created_time > latestSyncDate))
        if(media.created_time > latestSyncDate):
            events.append(upload_event(media))

    while next_:
        more_media, next_ = api.user_recent_media(user_id=user.uid, access_token=user.access_token, count=10, with_next_url=next_)
        for media in more_media:
            #logging.info("date comparison {0} vs {1} is {2}".format(media.created_time, latestSyncDate, media.created_time > latestSyncDate))
            if(media.created_time > latestSyncDate):
                events.append(upload_event(media))

    events.append(following_event(user_details.counts["follows"]))
    events.append(followers_event(user_details.counts["followed_by"]))
    events.append(sync_event("complete"))
    sendTo1self(user, events)

    logging.info("Sync successfully finished for user: %s" % user.uid)

application = webapp2.WSGIApplication([
    ('/', Nothing),
    ('/login', MainPage),
    ('/authRedirect', AuthRedirect),
    ('/push', HandlePushFromInstagram),
    ('/sync', HandleOfflineSyncRequest),
    ('/upgradeSchema', UpgradeSchema)
], debug=True)

