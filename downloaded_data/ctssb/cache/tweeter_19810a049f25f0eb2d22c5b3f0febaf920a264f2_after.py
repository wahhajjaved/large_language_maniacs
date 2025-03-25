import twitter
from twitter.twitter_utils import enf_type
import yaml
import os
from dateutil import parser
import re
import collections

RT_P = 'https://twitter.com/[^/]+/status/(\d+)'
RETWEET_PATTERN = re.compile(RT_P)
SUBTWEET_PATTERN = re.compile('.+'+RT_P, re.DOTALL)

WEB_P = 'https://twitter.com/i/web/status/'

def copy_fields(obj, D, fields):
    for field in fields:
        value = getattr(obj, field)
        if type(value)==unicode:
            try:
                value = str(value)
            except UnicodeEncodeError:
                None
        D[field] = value

def is_retweet(tweet):
    m = RETWEET_PATTERN.match(tweet['text'])
    if m:
        return m.group(1)

def is_subtweet(tweet):
    m = SUBTWEET_PATTERN.match(tweet['text'])
    if m:
        return m.group(1)
    if 'rt_text' in tweet:
        m = SUBTWEET_PATTERN.match(tweet['rt_text'])
        if m:
            return m.group(1)
        
def needs_extension(text):
    return WEB_P in text

def sort_by_date(tweets):
    return sorted(tweets, key=lambda t: parser.parse(t['created_at']))

class Tweeter:
    def __init__(self):
        config_fn = os.path.join( os.path.dirname(__file__), 'config.yaml')
        config = yaml.load(open(config_fn))

        self.api = twitter.Api(consumer_key=config['api_key'],
                          consumer_secret=config['api_secret'],
                          access_token_key=config['token'],
                          access_token_secret=config['token_secret'])
                          
        self.root = config['folder']
        self.mute_filters = config.get('mute', [])
        if not os.path.exists(self.root):
            os.mkdir(self.root)
        
        main_fn = os.path.join(self.root, 'tweeter.yaml')
        if os.path.exists(main_fn):
            self.meta = yaml.load(open(main_fn))
        else:
            self.meta = {}

        skipped_fn = os.path.join(self.root, 'skipped.yaml')
        if os.path.exists(skipped_fn):
            self.skipped = set(yaml.load(open(skipped_fn)))
        else:
            self.skipped = set()

        self.lists = {}
        self.tweets = {}
        for slug in self.meta.get('lists', []):
            fn = self.get_list_info(slug)
            if os.path.exists(fn):
                D = yaml.load(open(fn))
            else:
                D = {}
            self.lists[slug] = D
            
            fn = self.get_tweet_info(slug)
            if os.path.exists(fn):
                A = yaml.load(open(fn))
            else:
                A = []
            self.tweets[slug] = A
            
        self.users = {}
        user_folder = os.path.join(self.root, 'users')
        if not os.path.exists(user_folder):
            os.mkdir(user_folder)

        tweets_folder = os.path.join(self.root, 'tweets')
        if not os.path.exists(tweets_folder):
            os.mkdir(tweets_folder)
    
    def get_list_info(self, slug):
        return os.path.join(self.root, slug + '.yaml')
        
    def get_user_info(self, handle):
        return os.path.join(self.root, 'users', handle + '.yaml')

    def get_tweet_info(self, slug):
        return os.path.join(self.root, 'tweets', slug + '.yaml')

    # API METHODS ##############################################################
    def query_lists(self):
        lists = {}
        for t_list in self.api.GetListsList():
            d = {'id': t_list.id, 
                 'name': str(t_list.name), 
                 'member_count': t_list.member_count}
            lists[str(t_list.slug)] = d
        return lists
        
    def get_list_tweets(self, list_id, since_id=None, max_id=None, count=200):
        return self.api.GetListTimeline(list_id=list_id, since_id=since_id, max_id=max_id, count=count)
        
    def get_extended_status(self, status_id):
        url = '%s/statuses/show.json' % (self.api.base_url)

        parameters = {
            'id': enf_type('status_id', int, status_id),
            'tweet_mode': 'extended'
        }
        resp = self.api._RequestUrl(url, 'GET', data=parameters)
        data = self.api._ParseAndCheckTwitter(resp.content.decode('utf-8'))
        data['text'] = data['full_text']
        return twitter.Status.NewFromJsonDict(data)
        
    # DB METHODS ###############################################################
    def update_lists(self):
        slugs = []
        for slug, info in sorted(self.query_lists().items()):
            if slug in self.lists:
                self.lists[slug].update(info)
            else:
                self.lists[slug] = info
            slugs.append(slug)
        self.meta['lists'] = slugs
        yaml.dump({'lists': slugs}, open(os.path.join(self.root, 'tweeter.yaml'), 'w'))
        
    def get_user(self, handle):
        if handle in self.users:
            return self.users[handle]
            
        fn = self.get_user_info(handle)
        if os.path.exists(fn):
            D = yaml.load(open(fn))
        else:
            D = {}
        self.users[handle] = D
        return D   
        
    def process_user(self, info):
        handle = info.screen_name
        D = self.get_user(handle)
        fields = ['name', 'description', 'followers_count', 'id', 'profile_image_url']
        copy_fields(info, D, fields)

    def clean_tweet(self, obj):
        tweet = {}
        fields = ['created_at', 'id_str', 'retweet_count', 'text']
        copy_fields(obj, tweet, fields)
        tweet['handle'] = str(obj.user.screen_name)
        if obj.retweeted_status:
            handle = str(obj.retweeted_status.user.screen_name)
            id_str = str(obj.retweeted_status.id_str)
            tweet['text'] = 'https://twitter.com/%s/status/%s'%(handle, id_str)
        else:            
            for url in obj.urls:
                tweet['text'] = tweet['text'].replace( url.url, url.expanded_url)
        return tweet

    def recurse(self, tweet):
        id_str = is_retweet(tweet)
        if id_str and 'rt' not in tweet:
            rt = self.get_extended_status(id_str)
            c_rt = self.clean_tweet(rt)
            tweet['rt'] = id_str
            tweet['rt_text'] = c_rt['text']
        
        id_str2 = is_subtweet(tweet)
        if id_str2 and 'id2' not in tweet:
            tweet['id2'] = str(id_str2)

    def update_list(self, slug, count=150):
        info = self.lists[slug]
        max_id = info.get('max_id', None)
        raw_tweets = self.get_list_tweets(list_id=info['id'], since_id=info['since_id'], max_id=max_id, count=count)
        print len(raw_tweets)
        if len(raw_tweets)==1 and max_id is not None:
            del info['max_id']
            raw_tweets = self.get_list_tweets(list_id=info['id'], since_id=info['since_id'], count=count)
            print len(raw_tweets)
        first_id = None
        max_id = None
        for x in raw_tweets:
            self.process_user(x.user)
            if needs_extension(x.text):
                x = self.get_extended_status(x['id_str'])
            tweet = self.clean_tweet(x)
            self.recurse(tweet)
            if self.should_mute_tweet(tweet):
                continue
            if tweet not in self.tweets[slug]:
                self.tweets[slug].append(tweet)
            print tweet['id_str'], tweet['text']
            if first_id is None:
                first_id = tweet['id_str']
            max_id = tweet['id_str']
            
        if len(raw_tweets)>=count:
            info['max_id'] = max_id
        elif first_id:
            info['since_id'] = first_id
            info.pop('max_id', None)
    
    def should_mute_tweet(self, tweet):
        for needle in self.mute_filters:
            if needle in tweet['text']:
                return True
            if 'rt_text' in tweet and needle in tweet['rt_text']:
                return True
        return False
            
    def get_tweets(self):
        for slug in self.lists:
            self.update_list(slug)

    def all_tweets(self):
        all_tweets = []
        for tweets in self.tweets.values():
            all_tweets += tweets
        return all_tweets

    def clear_tweets(self, name):
        self.tweets[name] = []
        
    def is_valid_tweet(self, tweet, mode):
        if mode=='all':
            return True
        if tweet['id_str'] in self.skipped:
            return False
        if mode=='fresh' and is_retweet(tweet):
            return False
        return True
        
    def get_sizes(self, mode='fresh'):
        sizes = []
        for name in self.lists:
            c = 0
            for tweet in self.tweets[name]:
                if self.is_valid_tweet(tweet, mode):
                    c+=1
            if c>0:
                sizes.append( (name, c))
        return sizes
    
    def get_user_counts(self, slug, mode='fresh'):
        counts = collections.defaultdict(int)
        for tweet in self.tweets[slug]:
            if self.is_valid_tweet(tweet, mode):
                counts[tweet['handle']]+=1
        return dict(counts)
        
    def get_user_list(self, user):
        info = self.get_user(user)
        if 'list' in info:
            return info['list']
        for slug, tweets in self.tweets.iteritems():
            for tweet in tweets:
                if tweet['handle'] == user:
                    info['list'] = slug
                    return slug

    def mark_as_read(self, tweet, slug=None):
        if slug is None:
            for slug, tweets in self.tweets.iteritems():
                if tweet in tweets:
                    break
        self.tweets[slug].remove(tweet)

    def skip_tweet(self, tweet):
        self.skipped.add(tweet['id_str'])

    def mark_all(self, user):
        slug = self.get_user_list(user)
        tweets = []
        for tweet in self.tweets[slug]:
            if tweet['handle'] == user:
                tweets.append(tweet)
        for tweet in tweets:
            self.tweets[slug].remove(tweet)

    def get_tweet(self, slug=None, username=None, mode='fresh'):
        if slug:
            return self.get_tweet_from_list(slug, username, mode)
        
        tweets = []
        for key in self.lists.keys():
            tweet = self.get_tweet_from_list(key, username, mode)
            if tweet:
                tweets.append(tweet)
        if len(tweets)>0:
            return sort_by_date(tweets)[0]
        
    def get_tweet_from_list(self, slug, username=None, mode='fresh'):
        for tweet in sort_by_date(self.tweets[slug]):
            if not self.is_valid_tweet(tweet, mode):
                continue
            elif username and username!=tweet['handle']:
                continue
            else:
                return tweet

    def clear_skips(self):
        n = len(self.skipped)
        self.skipped = set()
        return n

    def write(self):
        main_fn = os.path.join(self.root, 'tweeter.yaml')
        yaml.dump(self.meta, open(main_fn, 'w'))
        skipped_fn = os.path.join(self.root, 'skipped.yaml')
        yaml.dump(list(self.skipped), open(skipped_fn, 'w'))
        for slug, info in self.lists.iteritems():
            yaml.dump(info, open(self.get_list_info(slug), 'w'))
            yaml.dump(self.tweets[slug], open(self.get_tweet_info(slug), 'w'))
            print slug, len(self.tweets[slug])
        for handle, info in self.users.iteritems():
            fn = self.get_user_info(handle)
            yaml.dump(info, open(fn, 'w'))
