# -*- coding: utf-8 -*-
#
# Usage:
# python2 twanalzr.py -n screen_name
# 
# Install:
# pip install tweepy ascii_graph tqdm numpy
from ascii_graph import Pyasciigraph
from ascii_graph.colors import *
from ascii_graph.colordata import vcolor
from ascii_graph.colordata import hcolor
from tqdm import tqdm
import tweepy
import time
import numpy
import argparse
import datetime

from secrets import consumer_key, consumer_secret, access_token, access_token_secret

parser = argparse.ArgumentParser(description='Analyze a Twitter account activity')
parser.add_argument('-l', '--limit', metavar='N', type=int, default=1000,
                    help='limit the number of tweets to retreive (default=1000)')
parser.add_argument('-n', '--name', required=True, metavar="screen_name",
                    help='target screen_name')

parser.add_argument('-f', '--filter', help='filter by source (ex. -f android will get android tweets only)')

parser.add_argument('--no-timezone',  action='store_true',
                    help='removes the timezone auto-adjustment (default is UTC)')

parser.add_argument('--utc-offset',  type=int,
                    help='manually apply a timezone offset (in seconds)')


args = parser.parse_args()

# Here are globals used to store data - I know it's dirty, whatever
start_date = 0
end_date = 0

activity_hourly = {
    "00:00": 0,
    "01:00": 0,
    "02:00": 0,
    "03:00": 0,
    "04:00": 0,
    "05:00": 0,
    "06:00": 0,
    "07:00": 0,
    "08:00": 0,
    "09:00": 0,
    "10:00": 0,
    "11:00": 0,
    "12:00": 0,
    "13:00": 0,
    "14:00": 0,
    "15:00": 0,
    "16:00": 0,
    "17:00": 0,
    "18:00": 0,
    "19:00": 0,
    "20:00": 0,
    "21:00": 0,
    "22:00": 0,
    "23:00": 0
    }

activity_weekly = {
    "0": 0,
    "1": 0,
    "2": 0,
    "3": 0,
    "4": 0,
    "5": 0,
    "6": 0
    }

detected_langs = {}
detected_sources = {}
detected_places = {}
geo_enabled_tweets = 0
detected_hashtags = {}
detected_timezones = {}
retweets = 0
retweeted_users = {}
mentioned_users = {}
id_screen_names = {}

def process_tweet(tweet):
    """ Processing a single Tweet and updating our datasets """
    global activity_hourly
    global activity_weekly
    global start_date
    global end_date
    global detected_langs
    global detected_sources
    global detected_places
    global geo_enabled_tweets
    global detected_hashtags
    global detected_timezones
    global retweets
    global retweeted_names
    global mentioned_users

    # Check for filters before processing any further
    if args.filter and tweet.source:
        if not args.filter.lower() in tweet.source.lower():
            return

    tw_date = tweet.created_at

    # Updating most recent tweet
    if end_date == 0:
        end_date = tw_date
    start_date = tw_date

    # Handling retweets
    try:
        # We use id to get unique accounts (screen_name can be changed)
        rt_id_user = tweet.retweeted_status.user.id_str
        if rt_id_user in retweeted_users:
            retweeted_users[rt_id_user] += 1
        else:
            retweeted_users[rt_id_user] = 1

        if not tweet.retweeted_status.user.screen_name in id_screen_names:
            id_screen_names[rt_id_user] = "@%s" % tweet.retweeted_status.user.screen_name
        
        retweets += 1
    except:
        pass

    # Adding timezone from profile offset to set to local hours
    if tweet.user.utc_offset and not args.no_timezone:
        tw_date = (tweet.created_at + datetime.timedelta(seconds=tweet.user.utc_offset))

    if args.utc_offset:
        tw_date = (tweet.created_at + datetime.timedelta(seconds=args.utc_offset))

    # Updating our activity datasets (distribution maps)
    activity_hourly["%s:00" % str(tw_date.hour).zfill(2)] += 1
    activity_weekly[str(tw_date.weekday())] += 1

    # Updating langs
    if tweet.lang in detected_langs:
        detected_langs[tweet.lang] += 1
    else:
        detected_langs[tweet.lang] = 1

    # Updating sources
    tweet.source = tweet.source.encode('utf-8') # fix bug in python2, some source string are unicode
    if tweet.source in detected_sources:
        detected_sources[tweet.source] += 1
    else:
        detected_sources[tweet.source] = 1

    # Detecting geolocation
    if tweet.place:
        geo_enabled_tweets += 1
        tweet.place.name = tweet.place.name.encode('utf-8')
        if tweet.place.name in detected_places:
            detected_places[tweet.place.name] += 1
        else:
            detected_places[tweet.place.name] = 1

    # Updating hashtags list
    if tweet.entities['hashtags']:
        for ht in tweet.entities['hashtags']:
            ht['text'] = "#%s" % ht['text'].encode('utf-8')
            if ht['text']in detected_hashtags:
                detected_hashtags[ht['text']] += 1
            else:
                detected_hashtags[ht['text']] = 1

    # Updating mentioned users list
    if tweet.entities['user_mentions']:
        for ht in tweet.entities['user_mentions']:

            if ht['id_str'] in mentioned_users:
                mentioned_users[ht['id_str']] += 1
            else:
                mentioned_users[ht['id_str']] = 1

            if not ht['screen_name'] in id_screen_names:
                id_screen_names[ht['id_str']] = "@%s" % ht['screen_name']

def get_tweets(api, username, limit):
    """ Download Tweets from username account """
    i = 0
    for status in tqdm(
        tweepy.Cursor(api.user_timeline, screen_name=username).items(),
        unit="tw", total=limit):
        process_tweet(status)
        i += 1
        if i >= limit:
            break;
    return i

def int_to_weekday(day):
    if day == "0":
        return "Monday"
    elif day == "1":
        return "Tuesday"
    elif day == "2":
        return "Wednesday"
    elif day == "3":
        return "Thursday"
    elif day == "4":
        return "Friday"
    elif day == "5":
        return "Saturday"
    else:
        return "Sunday"

def print_stats(dataset, top=5):
    """ Displays top values by order """
    sum = numpy.sum(dataset.values())
    i = 0
    if sum != 0:
        sorted_keys = sorted(dataset, key=dataset.get, reverse=True)
        max_len_key = max([len(x) for x in sorted_keys][:top]) # use to adjust column width
        for k in sorted_keys:
            print(("- \033[1m{:<%d}\033[0m {:>6} {:<4}" % max_len_key).format(k, dataset[k], "(%d%%)" % ((float(dataset[k])/sum)*100)))
            i += 1
            if i >= top:
                break
    else:
        print ("No data")
    print("")

def print_charts(dataset, title, weekday=False):
    """ Prints nice charts based on a dict {(key, value), ...} """
    chart = []
    keys = dataset.keys()
    mean = numpy.mean(dataset.values())
    median = numpy.median(dataset.values())

    keys.sort()
    for key in keys:

        if (dataset[key] >= median*1.33):
            displayed_key = "%s (\033[92m+\033[0m)" % (int_to_weekday(key) if weekday else key)
        elif (dataset[key] <= median*0.66):
            displayed_key = "%s (\033[91m-\033[0m)" % (int_to_weekday(key) if weekday else key)
        else:
            displayed_key = (int_to_weekday(key) if weekday else key)

        chart.append((displayed_key, dataset[key]))

    thresholds = {
        int(mean):  Gre, int(mean*2): Yel, int(mean*3): Red,
    }
    data = hcolor(chart, thresholds)

    graph = Pyasciigraph(
        separator_length=4,
        multivalue=False,
        human_readable='si',
        )

    for line in graph.graph(title, data):
        print(line)
    print("")

def main():
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    twitter_api = tweepy.API(auth)

    # Getting data on account
    print("[+] Getting @%s account data..." % args.name)
    user_info = twitter_api.get_user(screen_name=args.name)

    print("[+] lang           : \033[1m%s\033[0m" % user_info.lang)
    print("[+] geo_enabled    : \033[1m%s\033[0m" % user_info.geo_enabled)
    print("[+] time_zone      : \033[1m%s\033[0m" % user_info.time_zone)
    print("[+] utc_offset     : \033[1m%s\033[0m" % user_info.utc_offset)

    if user_info.utc_offset is None:
        print("[\033[91m!\033[0m] Can't get specific timezone for this user")

    if args.utc_offset:
        print("[\033[91m!\033[0m] Applying timezone offset %d (--utc-offset)" % args.utc_offset)

    print("[+] statuses_count : \033[1m%s\033[0m" % user_info.statuses_count)

    # Will retreive all Tweets from account (or max limit)
    num_tweets = numpy.amin([args.limit, user_info.statuses_count])
    print("[+] Retrieving last %d tweets..." % num_tweets)

    # Download tweets
    num_tweets = get_tweets(twitter_api, args.name, limit=num_tweets)
    print("[+] Downloaded %d tweets from %s to %s (%d days)" % (num_tweets, start_date, end_date, (end_date - start_date).days))

    if (end_date - start_date).days != 0:
        print("[+] Average number of tweets per day: \033[1m%.1f\033[0m" % (num_tweets / float((end_date - start_date).days)))

    # Print activity distrubution charts
    print_charts(activity_hourly, "Daily activity distribution (per hour)")
    print_charts(activity_weekly, "Weekly activity distribution (per day)", weekday=True)

    print "[+] Detected languages (top 5)"
    print_stats(detected_langs)

    print "[+] Detected sources (top 10)"
    print_stats(detected_sources, top=10)

    print("[+] There are \033[1m%d\033[0m geo enabled tweet(s)" % geo_enabled_tweets)
    if len(detected_places) != 0:
        print "[+] Detected places (top 10)"
        print_stats(detected_places, top=10)

    print "[+] Top 10 hashtags"
    print_stats(detected_hashtags, top=10)

    print "[+] @%s did \033[1m%d\033[0m RTs out of %d tweets (%.1f%%)" % (args.name, retweets, num_tweets, (float(retweets)*100/num_tweets))

    # Converting users id to screen_names
    retweeted_users_names = {}
    for k in retweeted_users.keys():
        retweeted_users_names[id_screen_names[k]] = retweeted_users[k]

    print "[+] Top 5 most retweeted users"
    print_stats(retweeted_users_names, top=5)

    mentioned_users_names = {}
    for k in mentioned_users.keys():
        mentioned_users_names[id_screen_names[k]] = mentioned_users[k]
    print "[+] Top 5 most mentioned users"
    print_stats(mentioned_users_names, top=5)

if __name__ == '__main__':
    try:
        main()
    except tweepy.error.TweepError as e:
        print("[\033[91m!\033[0m] Twitter error: %s" % e)
    except Exception as e:
        print("[\033[91m!\033[0m] Error: %s" % e)
