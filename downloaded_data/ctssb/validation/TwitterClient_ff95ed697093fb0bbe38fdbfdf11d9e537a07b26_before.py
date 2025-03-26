import json
import datetime

from django.http import HttpResponse
from django.shortcuts import render_to_response

from twt_client.models import Tweet, Meta
from twt_client.twitter_api import list_timeline

import pprint

pp = pprint.PrettyPrinter(indent=4)

# Create your views here.

def hello(request):
    html = "<html><body><h1>Hello</h1></body></html>"
    return HttpResponse(html)

def update(request):
    tweets = list_timeline()

    for tweet in tweets:
        Tweet(id = tweet['id'], data = json.dumps(tweet)).save()

    return HttpResponse("<html><head></head><body>success</body></html>")

def list_tweets(request):

    try:
        expiretime = int(Meta.objects.get(id=0).time) + 300
    except Meta.DoesNotExist:
        Meta(id=0, time=datetime.datetime.now().timestamp()).save()

    now = datetime.datetime.now().timestamp()

    print("Expiration: " + str(expiretime))
    print("Now:        " + str(now))

    if now > expiretime:
        print("Not cached")
        update(request)

        newtime = Meta.objects.get(id=0)
        newtime.time = datetime.datetime.now().timestamp()
        newtime.save()
    else:
        print("Cached")

    tweets = []
    for tweet in sorted(Tweet.objects.all(), key=lambda tweet: datetime.datetime.strptime(json.loads(tweet.data)['created_at'], "%a %b %d %H:%M:%S %z %Y").timestamp(), reverse=True):
        tweets.append(json.loads(tweet.data))
    return render_to_response('tweets.html', {'tweets':tweets})