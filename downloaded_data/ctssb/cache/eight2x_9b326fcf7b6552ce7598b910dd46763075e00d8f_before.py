import tweepy
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.db import Error
from pytz import utc
from time import sleep

from eight2x_app.lib.geocode import get_country
from eight2x_app.models import Status, User, Option


class Command(BaseCommand):
    help = 'Load Tweets history'
    
    def handle(self, *args, **options):
        auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
        auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_TOKEN_SECRET)
        
        api = tweepy.API(auth)
        query = ' OR '.join(settings.TWITTER_SEARCH_HASHTAGS)
        
        while True:
            try:
                max_id = Option.objects.get(option_name='max_id')
            except ObjectDoesNotExist:
                max_id = Option(option_name='max_id', option_value='970307359166746624')
                max_id.save()
            
            try:
                statuses = api.search(query, since_id=0, count=100, max_id=max_id)
            except:
                continue
                
            for s in statuses:
                try:
                    # find user
                    try:
                        user = User.objects.get(id=int(s.author.id))
                    except ObjectDoesNotExist:
                        user = User()
                        user.id = s.author.id
        
                    user.name = s.author.name
                    user.screen_name = s.author.screen_name
                    user.location = s.user.location
                    user.description = s.user.description
                    user.utc_offset = s.user.utc_offset
                    user.time_zone = s.author.time_zone
                    user.lang = s.author.lang
                    user.save()
        
                    status = Status()
                    status.id = s.id
                    status.created_at = utc.localize(s.created_at)
                    status.text = s.text
                    status.entities = []
                    if s.entities['urls'] is not None:
                        for url in s.entities['urls']:
                            status.entities.append(url['url'])
                    status.user = user
                    status.retweet_count = s.retweet_count
                    status.favorite_count = s.favorite_count
                    if s.geo is not None:
                        status.geo = s.geo['coordinates']
                        status.country = get_country(status.geo[0], status.geo[1])
                    else:
                        status.geo = list()
                    status.lang = s.lang
                    status.save()
                    print('Inserted tweet with ID ' + str(s.id))
                except Error:
                    print('Error in inserting tweet ' + str(s['id']))
            
            max_id.option_value = statuses[len(statuses) - 1].id
            max_id.save()
            sleep(5)