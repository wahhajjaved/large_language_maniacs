from willie import module, web
import json
import random
import urllib
import time
from operator import itemgetter
import unicodedata

# Track if if and when we've seen a particular content id
last_seen = {}
# Track usage so we can rate control
users = {}
# The number of queries allowed per minute
allowed_per_minute = 5
# Already resolved phrase:subreddit mappings to save time
resolved_subreddit = {}
# List of allowed domains for results
allowed_domains = ['i.imgur.com', 'gfycat.com']

def get_content(phrase, mode, period = "day"):
    subreddit = unicodedata.normalize("NFKD", phrase).encode('ascii','ignore').lower()
    if subreddit == "":
        return "Your input is bad and you should feel bad.", None

    if " " in subreddit:
        subreddit_find_string = subreddit.replace(' ','+')
        if not resolved_subreddit.has_key(subreddit_find_string):
            try:
                url = json.loads(web.get("http://www.reddit.com/subreddits/search.json?q=%s" % (subreddit_find_string)))
            except ValueError:
                return "There was an error with your query. Reddit is probably having trouble.", None
                
            result = [x['data']['display_name'] for x in url['data']['children'] if x.has_key('data') and x['data'].has_key('display_name') and x['data']['subreddit_type'] != "private"]
            if len(result) > 0:
                subreddit = result[0].lower()
                resolved_subreddit[subreddit_find_string] = subreddit
            else:
                return "I looked for a public subreddit matching that phrase but didn't find one.", None
        else:
            subreddit = resolved_subreddit[subreddit_find_string]

    if not last_seen.has_key(subreddit):
        last_seen[subreddit] = {}

    url = "http://www.reddit.com/r/{0}/search.json?restrict_sr=on&sort={1}&t={2}".format(subreddit.encode('ascii','ignore'), mode, period)
    get = web.get(url, timeout=5)

    try:
        array = json.loads(get)
    except ValueError:
        #return "/r/{0} doesn't look like a subreddit to me.".format(subreddit), subreddit
        return "/r/%s doesn't look like a subreddit to me." % (subreddit), subreddit

    if 'error' in array:
        if array['error'] == 404:
            #return "/r/{0} isn\'t a real subreddit.".format(subreddit), subreddit
            return "/r/%s isn\'t a real subreddit." % (subreddit), subreddit
        elif array['error'] == 403:
            #return "/r/{0} is a private subreddit.".format(subreddit), subreddit
            return "/r/%s is a private subreddit." % (subreddit), subreddit
        else:
            return "Unknown error. Whoops.", None
    else:
        links = []
        iterator = 0
        if 'children' in array['data']:
            if len(array['data']['children']) > 0:
                while (len(links) < 10) and (iterator < len(array)):
                        for child in array['data']['children']:
                            iterator = iterator + 1
                            if child['data'].has_key('domain') and child['data']['domain'] in allowed_domains:
                                if 'over_18' in child['data']:
                                    id = child['data']['id']
                                    if last_seen[subreddit].has_key(id):
                                        child['data']['lastseen'] = last_seen[subreddit][id]
                                    else:
                                        child['data']['lastseen'] = 0
                                    links.append(child['data'])

                if len(links) == 0:
                    return "I found results for /r/%s but none were from imgur or gfycat." % (subreddit), subreddit
    return links, subreddit

class User(object):
    def __init__(self, user):
        self.user = user
        self.posts = []

    def posted(self):
        self.posts.append(int(time.time()))

    def is_douchebag(self):
        total = 0
        for t in self.posts:
            if int(time.time()) - t <= 60:
                total += 1
            else:
                self.posts.remove(t)
        if total >= allowed_per_minute:
            return total
        return False

@module.rule('($nickname:?\ )(.*)')
def imgurbot(bot, trigger):
    nickname = trigger.nick
    if not users.has_key(nickname):
        users[nickname] = User(nickname)
    else:
        users[nickname].posted()
    douchebag = users[nickname].is_douchebag()
    if douchebag == 5:
        bot.reply("Slow down there cowboy.")
        return
    elif douchebag > 5:
        return

    mode = "hot"
    periods = ['day','week','month','year','all']

    phrase = trigger.group(2)
    reply = None
    for period in periods:
        reply,subreddit = get_content(phrase, mode, period)
        if not subreddit or (type(reply) is list and len([x for x in reply if not last_seen[subreddit].has_key(x['id'])]) != 0):
            break

    if type(reply) is list and subreddit:
        if len(reply) == 0:
            bot.say("No imgur posts were found in /r/{0}".format(subreddit))
        else:
            reply = sorted(reply, key=itemgetter('lastseen'))
            last_seen[subreddit][reply[0]['id']] = int(time.time())
            suffix = ''
            if (reply[0]['over_18'] is True):
                suffix = ' [nsfw]'
            bot.say("[%s] %s - \"%s\"%s" % (subreddit, reply[0]['url'], reply[0]['title'], suffix))
            return
    elif type(reply) is str:
        bot.reply(reply)
        return

