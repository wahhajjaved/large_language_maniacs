#!/usr/bin/env python
# -*- coding: utf-8 -*-


import tweepy, time, sys, os, json
from random import randint
from ConfigParser import SafeConfigParser
from tweepy.streaming import StreamListener
from tweepy import OAuthHandler
from tweepy import Stream

reload(sys)
sys.setdefaultencoding('utf-8')

# Our name
BOT_NAME = 'updogbot'

TWITTER_LIMIT = 140

parser = SafeConfigParser()
parser.read('secrets.cfg')

# Twitter credentials
CONSUMER_KEY = parser.get('Twitter', 'CONSUMER_KEY')
CONSUMER_SECRET = parser.get('Twitter', 'CONSUMER_SECRET')
ACCESS_KEY = parser.get('Twitter', 'ACCESS_KEY')
ACCESS_SECRET = parser.get('Twitter', 'ACCESS_SECRET')

EMOJI_RESPONSE_ARRAY = ['🤔', '🐶', '🐕', '🐩', '🐺', '🐾']
DEFAULT_RESPONSE = 'What\'s updog?'

# Blacklists, all lowercase
BLACKLISTED_USERS = ['updogband']
BLACKLISTED_TEXT = ['posey', 'brandie', 'blissbends', 'yoga', 'tour']

with open('badwords.json') as data_file:
    BLACKLISTED_TEXT.extend(json.load(data_file))

auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)
api = tweepy.API(auth)

# To ensure some rate limiting
MIN_SECS_BETWEEN_RESPONSES = 15
lastResponseTimestamp = time.time()

# Keep track of the latest people we've responded to
CIRCULAR_ARRAY_MAX_CAPACITY = 4
circularArrayOfHandles = [''] * CIRCULAR_ARRAY_MAX_CAPACITY
circularArrayPointer = 0

# Update the circular array and increment the pointer
def updateCircularArray(handle):
	global circularArrayPointer

	# Insert handle into our list of handles we've last responded to
	if not handle in circularArrayOfHandles:
		circularArrayOfHandles[circularArrayPointer] = handle
		circularArrayPointer = circularArrayPointer + 1
		if circularArrayPointer >= CIRCULAR_ARRAY_MAX_CAPACITY:
			circularArrayPointer = 0
	
	print circularArrayOfHandles

# Ensure the given object is a str, not a unicode object
def unicodeToStr(s):
	if isinstance(s, unicode):
		s = str(s)
	return s

# Posts a response tweet
def respond(tweet):
	global lastResponseTimestamp

	tweetInterval = time.time() - lastResponseTimestamp
	if tweetInterval < MIN_SECS_BETWEEN_RESPONSES:
		print 'Rate limit: Just tweeted ' + str(tweetInterval) + ' secs ago'
		return

	lastResponseTimestamp = time.time()

	handle = '@' + tweet.screen_name
	replyText = handle + ' '

	if BOT_NAME in tweet.text.lower() or 'updog bot' in tweet.text.lower():
		# If they're aware of us, respond with an emoji
		replyText = replyText + EMOJI_RESPONSE_ARRAY[randint(0, len(EMOJI_RESPONSE_ARRAY)-1)]
	elif 'what\'s updog' in tweet.text.lower() or 'what is updog' in tweet.text.lower():
		# If they're asking what it is, only respond with the thinking face emoji
		replyText = replyText + '🤔'
	else:
		# Ask what updog is
		replyText = replyText + DEFAULT_RESPONSE

	api.update_status(status = replyText, in_reply_to_status_id = tweet.tweet_id)

# RTs the given tweet
def retweet(tweet):
	try:
		api.retweet(tweet.tweet_id)
	except tweepy.error.TweepError as err:
		print("RTing, Tweepy error: {0}".format(err))

# Follows the user who posted the given tweet
def followUser(tweet):
	try:
		api.create_friendship(tweet.screen_name)
	except tweepy.error.TweepError as err:
		print("Following user, Tweepy error: {0}".format(err))

# Determines whether we should retweet a given tweet or not
def shouldRetweet(tweet):
	if BOT_NAME in tweet.text.lower() or 'updog bot' in tweet.text.lower():
		print 'Not RTing: the tweet mentions us'
		return False

	handle = '@' + tweet.screen_name
	if handle in circularArrayOfHandles:
		print 'Not RTing: We recently interacted with this person'
		return False

	# The tweet is quoting us
	if unicodeToStr(tweet.full.get('quoted_status', {}).get('user', {}).get('screen_name', '')) == BOT_NAME:
		print 'Not RTing: the tweet quotes us'
		return False

	# Don't RT if they're asking what updog is
	if 'what\'s updog' in tweet.text.lower() or 'what is updog' in tweet.text.lower():
		print 'Not RTing: the tweet asks what updog is'
		return False

	# Don't RT if it's a reply to someone
	if tweet.text[0] == '@':
		print 'Not RTing: the tweet is a reply to someone'
		return False

	return True

# Determines whether the tweet should be ignored entirely
def shouldIgnoreTweet(tweet):
	# Ignore the tweet if it's us or if we think the tweeter is a bot
	if 'updog' in tweet.screen_name.lower() or 'bot' in tweet.screen_name.lower() or 'ebooks' in tweet.screen_name.lower():
		print 'Ignoring tweet: The tweeter\'s handle contains updog or bot'
		return True

	# Ignore the tweet if updog is not in it
	if 'updog' not in tweet.text.lower():
		print 'Ignoring tweet: Updog not in text'
		return True

	if handle in circularArrayOfHandles:
		print 'Ignoring tweet: We recently interacted with this user'
		return True

	if len(tweet.urls):
		print 'Not RTing: the tweet contains URLs'
		return True

	# Don't RT if there's a photo or video
	if len(tweet.media):
		print 'Not RTing: the tweet contains media'
		return True

	if str.startswith(tweet.text, 'RT '):
		print 'Not RTing: the tweet is already an RT'
		return True

	if tweet.screen_name.lower() in BLACKLISTED_USERS:
		print 'Ignoring tweet: The tweeter is blacklisted'
		return True

	for badword in BLACKLISTED_TEXT:
		if badword in tweet.text.lower():
			print 'Ignoring tweet: The tweet has blacklisted text'
			return True

	return False


# Tweet class with some attributes and the full JSON itself
class Tweet:
	text = str()
	hashtags = []
	urls = []
	media = []

	tweet_id = ''
	screen_name = ''
	user = {}
	full = {}

	def __init__(self, json):
		self.tweet_id = unicodeToStr(json.get('id', ''))

		self.user = json.get('user', {})
		self.screen_name = unicodeToStr(self.user.get('screen_name', ''))

		self.text = unicodeToStr(json.get('text', ''))

		self.hashtags = json.get('entities', {}).get('hashtags', [])
		self.urls = json.get('entities', {}).get('urls', [])
		self.media = json.get('entities', {}).get('media', [])

		self.full = json

# Basic listener: parse the tweet, respond if appropriate, RT if appropriate, and follow the user
class TweetListener(StreamListener):
	def on_data(self, data):
		jsonData = json.loads(data)
		tweet = Tweet(jsonData)

		print '@' + tweet.screen_name.encode("utf-8") + ': ' + tweet.text.encode("utf-8")

		# Just quit if the tweet is worth ignoring
		if shouldIgnoreTweet(tweet):
			return True
		
		if shouldRetweet(tweet):
			retweet(tweet)
		
		respond(tweet)

		followUser(tweet)

		updateCircularArray('@' + tweet.screen_name)

		return True

	def on_error(self, status):
		print status

if __name__ == '__main__':
	print '\n\n-----\nStarting up the updog bot...'
	listener = TweetListener()
	stream = Stream(auth, listener)	
	stream.filter(track=['updog', 'Updog'])
