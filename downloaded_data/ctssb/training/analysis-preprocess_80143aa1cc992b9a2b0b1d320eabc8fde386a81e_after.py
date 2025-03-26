# -*- coding: utf-8 -*-
"""
===================================
Analysis Tweet Preprocessor

DEPENDENCIES: cython, numpy, scipy, hdbscan, textblob-de(includes en), langid, faker, pymongo

NOTE: textblob needs language files, download them
	  via $ python -m textblob.download_corpora
===================================
"""

import calendar
import time
import random
import os
import logging
import numpy as np
import requests
from datetime import datetime, timedelta
from langid import classify
from pymongo import MongoClient, GEO2D, ASCENDING, bulk
from textblob import TextBlob as TextBlobEN
from textblob_de import TextBlobDE

# Sensible logging format
# TODO: proper setup for debug and release mode
logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', level=logging.DEBUG)

# TODO: possibly others? see: http://www.ling.upenn.edu/courses/Fall_2003/ling001/penn_treebank_pos.html
ALLOWED_WORD_TOKENS = { 'N', 'J', 'V' }

# Custom exceptions
class RestConnectionException(Exception):
	pass
class UnknownLanguageException(Exception):
	pass

# Connect to 
def connect_to_and_setup_database():
	while True:
		try:
			addr = os.getenv('MONGODB_PORT_27017_TCP_ADDR', 'localhost')
			port = os.getenv('MONGODB_PORT_27017_TCP_PORT', '16018')
			passwd = os.getenv('MONGODB_PASS', 'supertopsecret')
			client = MongoClient('mongodb://analysis:' + passwd + '@' + addr + ':' + port + '/analysis')
			db = client.analysis
			db.tweets.ensure_index([("loc", GEO2D)])
			db.tweets.ensure_index([("created_at", ASCENDING)])
			logging.info("Connected to database: mongodb://%s:%s/analysis", addr, port)
			return client, db
		except Exception as error: 
			logging.error(repr(error))
			time.sleep(2) # wait with the retry, database is possibly starting up

#
def get_rest_get_via_timestamp_url():
	addr = os.getenv('REST_PORT_3000_TCP_ADDR', 'localhost')
	port = os.getenv('REST_PORT_3000_TCP_PORT', '16300')
	return 'http://' + addr + ':' + port + '/tweets/ts/'

#
def get_new_tweets(url, newer_than_time):
	res = requests.get(url + str(int(calendar.timegm(newer_than_time.utctimetuple()) * 1000)))
	if res.status_code == 200:
		tweets = res.json()
		return tweets if type(tweets) is list else list(tweets)
	else:
		raise RestConnectionException('Connection to tweetdb rest-service failed with status-code ' + res.status_code + ': ' + res.text)

# takes the raw tweet data and already preprocesses (includes sentiment analysis) for a better internal representation 
def preprocess_tweet(data):
	try:
		created_at = datetime.strptime(data['created_at'],'%a %b %d %H:%M:%S +0000 %Y')
		# detect the language of the tweet or use predefined language
		lang = classify(data['text'])[0] if not 'lang' in data else data['lang']
		# tokenize the text dependent on the language
		blob = None
		if lang == 'en':
			blob = TextBlobEN(data['text'])
		elif lang == 'de':
			blob = TextBlobDE(data['text'])
		else: # avoid unknown languages
			raise UnknownLanguageException('Unknown language: ' + data['text'])
		# get the polarity of the tweet sentences and summerize them
		# NOTE: TextBlobDE is not as great as the english analyzer and is fairly barebone.
		#	    If the resulting polarity is inaccurate, one possibility to solve this is to
		#		only process english tweets
		polarity = 0
		polarity_count = 0
		for sentence in blob.sentences:
			# ignore unimportant sentiment, because in most cases failed detection or hashtag parts from tweet
			if sentence.sentiment.polarity != 0.0:
				polarity = sentence.sentiment.polarity
				polarity_count += 1
		if polarity_count > 0:
			polarity /= polarity_count
		# extract _important_ words from the word tokens
		words = []
		is_hashtag = False
		for tag in blob.tags:
			word = tag[0]
			kind = tag[1]
			# TODO: special behaviour for hashtag is possibly also necessary for @
			if word[0] == '#': # special case means next word is a hashtag
				is_hashtag = True
			else:
				if is_hashtag: # previous word was a hashtag, so remerge with # and save
					words.append("#" + word)
					is_hashtag = False
				else: # just normal word of the tweet
					# check the word is of an allowed grammatical type
					if kind[0] in ALLOWED_WORD_TOKENS: 
						words.append(word)
		# find out where the tweet came from by either taking existing coordinates
		# or center of place
		# TODO: check if coordinates exist before using place
		# TODO: verify structure of place coordinates
		coords = data['place']['bounding_box']['coordinates'][0] 
		loc = [0.0, 0.0]
		for coord in coords:
			loc[0] += coord[0]
			loc[1] += coord[1]
		loc[0] /= len(coords)
		loc[1] /= len(coords)
		# create tweet object 
		tweet = { "_id": data['_id'], # use same id
				  "user": {
				  	"name": data['user']['name'],
				  	"screen_name": data['user']['screen_name'],
				  	"followers_count": data['user']['followers_count'],
				  	"friends_count": data['user']['friends_count'],
				  	"listed_count": data['user']['listed_count'],
				  	"statuses_count": data['user']['statuses_count'],
				  	"following": data['user']['following']
				  },
				  "created_at": created_at,
				  "words": words,
				  "loc": loc,
				  "polarity": polarity,
				  "retweet_count": data['retweet_count'],
				  "favorite_count": data['favorite_count'] }
		return tweet
	except UnknownLanguageException as error: # catch exceptions, usually failed language detection
		logging.warning(repr(error))

if __name__ == '__main__':
	# connect to mongodb, get rest url and setup last_access_time
	client, db = connect_to_and_setup_database()
	url = get_rest_get_via_timestamp_url()
	last_access_time = datetime.utcnow() - timedelta(days=7)
	# always try to get new tweets and process them
	while True: 
		try:
			raw_tweets = get_new_tweets(url, last_access_time)
			if len(raw_tweets) > 0:
				last_access_time = datetime.utcnow()
				processed_tweets = list(filter(None.__ne__, map(preprocess_tweet, raw_tweets)))
				# insert data into mongo using bulk
				b = bulk.BulkOperationBuilder(db.tweets, ordered=False)
				for t in processed_tweets:
					b.find({ "_id": t['_id'] }).upsert().update_one({
        				"$setOnInsert": t
    				})
				response = b.execute() # errors for duplicates are ignored
				logging.debug("Bulk Response: %s", str(response))
			time.sleep(5)
		except RestConnectionException as error:
			logging.warning(repr(error))





