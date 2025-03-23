from maxtweety.listener import StreamWatcherListener
from maxtweety.utils import setup_logging

import argparse
import ConfigParser
import json
import logging
import multiprocessing
import os
import pika
import requests
import sys
import tweepy

debug_hashtag = u'debugmaxupcnet'
logger = logging.getLogger(__name__)


def main(argv=sys.argv, quiet=False):  # pragma: no cover
    tweety = MaxTwitterListenerRunner(argv, quiet)
    tweety.spawn_process()

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=tweety.config.get('rabbitmq', 'server'))
    )

    channel = connection.channel()

    logger.info('[*] Waiting for restart signal.')

    def callback(ch, method, properties, body):
        logger.info("[x] Received restart from MAX server")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        tweety.restart()

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(callback,
                          queue='tweety_restart')
    channel.start_consuming()


class MaxTwitterListenerRunner(object):  # pragma: no cover
    process = None

    verbosity = 1  # required
    description = "Max Twitter listener runner."
    usage = "usage: %prog [options]"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-c', '--config',
                      dest='configfile',
                      type=str,
                      help=("Configuration file"))

    def __init__(self, argv, quiet=False):
        self.quiet = quiet
        self.options = self.parser.parse_args()
        self.config = ConfigParser.ConfigParser()
        self.config.read(self.options.configfile)

        if not self.options.configfile:
            logging.error('You must provide a valid configuration .ini file.')
            sys.exit(1)

        setup_logging(self.options.configfile)

        try:
            self.consumer_key = self.config.get('twitter', 'consumer_key')
            self.consumer_secret = self.config.get('twitter', 'consumer_secret')
            self.access_token = self.config.get('twitter', 'access_token')
            self.access_token_secret = self.config.get('twitter', 'access_token_secret')

            self.maxservers_settings = [maxserver for maxserver in self.config.sections() if maxserver.startswith('max_')]

        except:
            logging.error('You must provide a valid configuration .ini file.')
            sys.exit(1)

    def spawn_process(self, *args, **kwargs):
        self.process = multiprocessing.Process(target=self.run, args=args, kwargs=kwargs)
        self.process.start()

    def restart(self):
        if self.process.is_alive():
            self.process.terminate()
            self.spawn_process()

    def get_twitter_enabled_contexts(self):
        contexts = {}
        for max_settings in self.maxservers_settings:
            max_url = self.config.get(max_settings, 'server')
            req = requests.get('{}/contexts'.format(max_url), params={"twitter_enabled": True}, headers=self.oauth2Header(self.restricted_username, self.restricted_token))
            context_follow_list = [users_to_follow.get('twitterUsernameId') for users_to_follow in req.json().get('items') if users_to_follow.get('twitterUsernameId')]
            context_readable_follow_list = [users_to_follow.get('twitterUsername') for users_to_follow in req.json().get('items') if users_to_follow.get('twitterUsername')]
            contexts.setdefault(max_settings, {})['ids'] = context_follow_list
            contexts[max_settings]['readable'] = context_readable_follow_list

        self.users_id_to_follow = contexts

    def flatten_users_id_to_follow(self):
        flat_list = []
        for maxserver in self.users_id_to_follow.keys():
            id_list = self.users_id_to_follow.get(maxserver).get('ids')
            flat_list = flat_list + id_list

        return flat_list

    def get_max_global_hashtags(self):
        self.global_hashtags = []
        for max_settings in self.maxservers_settings:
            self.global_hashtags.append(self.config.get(max_settings, 'hashtag'))

    def load_settings(self):
        settings_file = '{}/.max_restricted'.format(self.config.get('general', 'config_directory'))
        if os.path.exists(settings_file):
            settings = json.loads(open(settings_file).read())
        else:
            settings = {}

        if 'token' not in settings or 'username' not in settings:
            logger.info("Unable to load MAX settings, please execute initialization script.")
            sys.exit(1)

        self.restricted_username = settings.get('username')
        self.restricted_token = settings.get('token')

    def oauth2Header(self, username, token, scope="widgetcli"):
        return {
            "X-Oauth-Token": token,
            "X-Oauth-Username": username,
            "X-Oauth-Scope": scope}

    def run(self):
        self.load_settings()
        self.get_max_global_hashtags()
        self.get_twitter_enabled_contexts()

        # Prompt for login credentials and setup stream object
        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        auth.set_access_token(self.access_token, self.access_token_secret)

        # auth = tweepy.auth.BasicAuthHandler(self.options.username, self.options.password)
        stream = tweepy.Stream(auth, StreamWatcherListener(self.config.get('rabbitmq', 'server')), timeout=None)

        # Add the debug hashtag
        self.global_hashtags.append(debug_hashtag)

        logger.info("Listening to this Twitter hashtags: \n{}".format(json.dumps(self.global_hashtags, indent=4, sort_keys=True)))
        logger.info("Listening to this Twitter userIds: \n{}".format(json.dumps(self.users_id_to_follow, indent=4, sort_keys=True)))

        stream.filter(follow=self.flatten_users_id_to_follow(), track=self.global_hashtags)
