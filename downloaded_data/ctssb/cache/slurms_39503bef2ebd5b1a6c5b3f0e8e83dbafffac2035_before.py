#!/usr/bin/python

import httplib, urllib, json, getpass
from subprocess import call
import Adafruit_CharLCD as LCD
import smtplib
import sys

# config
email = 'flactester@murfie.com'
password = 'T35T1NGMurf13'

# globals
authtoken = ''
nowPlayingDisc = 0
totalDisccount = 0
noticeCount = 0
warnCount = 0
errorCount = 0
peakMessageLevel = 0  

# API http bits
conn = httplib.HTTPSConnection('api.murfie.com')

# init lcd library for pi plate
lcd = LCD.Adafruit_CharLCDPlate()

def logMessage(message, level):

	global noticeCount
	global warnCount
	global errorCount
	global peakMessageLevel

	print(message)

	if level == 1:
		noticeCount = noticeCount + 1 

		if peakMessageLevel < 1:
			peakMessageLevel = 1
			lcd.set_color(0.0, 1.0, 0.0)

	if level == 2:
		warnCount = warnCount + 1

		if peakMessageLevel < 2:
			peakMessageLevel = 2
			lcd.set_color(0.0, 1.0, 1.0)

	if level == 3:
		errorCount = errorCount + 1

		if peakMessageLevel < 3:
			peakMessageLevel = 3
			lcd.set_color(1.0, 0.0, 0.0)

	lcd.clear()
	lcd.message(message)
	lcd.message('\nn:%s w:%s e:%s' % (noticeCount, warnCount, errorCount))

	# notify jason of errors
	if level == 3:

		server = smtplib.SMTP('smtp.gmail.com', 587)
		server.starttls()
		server.login('jason@murfie.com','backinblack')

		server.sendmail('jason@murfie.com', '9203199152@vtext.com', '\n%s' % message)

def authenticate(email, password):

	logMessage('authenticating', 1)

	try:
		# get the token
		params = urllib.urlencode({'email':email, 'password':password})
		headers = {'Content-type':'application/x-www-form-urlencoded','Accept':'text/plain'}
		conn.request('POST', '/api/tokens', params, headers)
		response = conn.getresponse()

		apiResult = json.loads(response.read())
		conn.close()

		return apiResult['user']['token']

	except:
		logMessage('error authenticating: %s' % sys.exc_info()[0], 3)
		return None

def pickDisc():

	# get the album list
	try:
		conn.request('GET', '/api/discs.json?auth_token=' + authtoken + '&device=slurms')
		response = conn.getresponse()
		apijson = json.loads(response.read())

 	except:
		logMessage('error loading albums: %s' % sys.exc_info()[0], 3)
 		return None

	# select the disc to play
	try:
		global totalDiscCount
		totalDiscCount = len(apijson)

		selecteddisc = nowPlayingDisc
		selecteddiscid = apijson[selecteddisc]['disc']['id']
		print("\n%s by %s selected" % (apijson[selecteddisc]['disc']['album']['title'],apijson[selecteddisc]['disc']['album']['main_artist']))

	except:
		logMessage('error selecting disc: %s' % sys.exc_info()[0], 3)
		return None
	
	# get tracks for selected disc
	try:
		conn.request('GET', '/api/discs/%d.json?auth_token=%s' % (apijson[selecteddisc]['disc']['id'], authtoken + '&device=slurms'))
		response = conn.getresponse()
		apiResult = json.loads(response.read())

		conn.close()
		disc = apiResult['disc']

		return disc

	except:
		logMessage('error loading tracks: %s' % sys.exc_info()[0], 3)
		return None 

def playDisc(disc):

	# play each track in the disc
	for track in disc['tracks']:

		try:
			logMessage(track['title'], 1)

			#logMessage('%s \n by %s' % (track['title'], disc['album']['main_artist']), 'notice')

			# get the media Uri
			conn.request('GET', '/api/discs/%s/tracks/%s.json?auth_token=%s' % (disc['id'],track['id'],authtoken + '&device=slurms'))
			response = conn.getresponse()
			apiResult = json.loads(response.read())
			conn.close()
			mediaUri = '\"%s\"' % apiResult['track']['url']

			mediaUri = mediaUri.replace('https', 'http')

			call('mplayer -quiet %s' % mediaUri, shell=True)

		except:
			logMessage('error playing track: %s' % sys.exc_info()[0], 3)

	# when the disc is over, select another
	global nowPlayingDisc
	nowPlayingDisc = nowPlayingDisc + 1

	if nowPlayingDisc < totalDiscCount:
		#logMessage('so tired of partying...', 2)
		playDisc(pickDisc())
	else:
		logMessage('Can I stop parytying now?', 2)

# start by authenticating
logMessage('Wibby wam wam wozzel!', 1)

authtoken = authenticate(email, password)
playDisc(pickDisc())
