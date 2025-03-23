from random import choice
from datetime import datetime

from config import *

def now():
	return datetime.now()

def timestamp():
	return now().strftime("%Y-%m-%d %H:%M:%S")

def today():
	return now().strftime("%Y-%m-%d")

def getMoodBySmiley(smiley):
	for mood in MOODS.values():
		if smiley.lower() in mood['smileys']:
			return mood
	return None

def getMoodSmileyByScore(score):
	for mood in MOODS.values():
		if score == mood['score']:
			return mood['smileys'][0]
	return None

def getRandomItem(items):
	return choice(items)