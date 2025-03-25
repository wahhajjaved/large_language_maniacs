import re
import random

def Harambe(message):
	if 'harambe' in message:
		return "DICKS OUT"
	return "-0"

#######################################

def KnowHer(wordList):
	last = wordList[-1]
	first = wordList[0]

	if len(last) > 3 and last[-1] == 'r' and last[-2] == 'e':
		return "{0} 'er? I hardly know her!".format(last[0:-2])

	elif len(first) > 3 and first[-1] == 'r' and first[-2] == 'e':
		return "{0} 'er? I hardly know her!".format(first[0:-2])
	
	return "-0"

#######################################
def PostJoePic():
	randNum = random.randrange(0, 14)
	sNum = '12'

	if randNum == 0:
		picSuffix = 't62zmp0f1/banana_Joe.jpg'
	if randNum == 1:
		picSuffix = 'jzkozev6l/Joeand_Nick.jpg'
	if randNum == 2:
		picSuffix = 'c83z0ur19/peacock_Joe.jpg'
	if randNum == 3:
		picSuffix = '5ixfku5p9/Sleepy_Joe1.jpg'
	if randNum == 4:
		picSuffix = '5uzinsuin/sleepyjoe2.jpg'
	if randNum == 5:
		picSuffix = '4vyivb8t9/sleepyjoe3.jpg'
	if randNum == 6:
		picSuffix = '5zin79tgd/sleepyjoe4.jpg'
	if randNum == 7:
		sNum = '16'
		picSuffix = '9uqjishgx/blowjobjoe.jpg'
	if randNum == 8:
		sNum = '16'
		picSuffix = 'q70l8ivsh/frenchmaidjoe.jpg'
	if randNum == 9:
		sNum = '16'
		picSuffix = 'ej6jdz6nl/joejames.jpg'
	if randNum == 10:
		sNum = '16'
		picSuffix = 'crimg6tm9/sexyyoungjoe.jpg'
	if randNum == 11:
		sNum = '16'
		picSuffix = 'm0ksqb2i9/tyreejoe.jpg'
	if randNum == 12:
		sNum = '16'
		picSuffix = 'j7rl6a25t/xrayjoe.jpg'
	if randNum == 13:
		sNum = '16'
		picSuffix = 'pzi094r5d/zombiejoe.jpg'

	return 'https://s' + sNum + '.postimg.org/' + picSuffix

def PostMariaPic():
	randNum = random.randrange(0, 15)
	sNum = '17'

	if randNum == 0:
		picSuffix = 'm421ddsu3/maria_1.jpg'
	if randNum == 1:
		picSuffix = '9qp76h35n/maria_2.jpg'
	if randNum == 2:
		picSuffix = 'p0p2dnynv/maria_3.jpg'
	if randNum == 3:
		picSuffix = '5k4cr53jv/maria_4.jpg'
	if randNum == 4:
		picSuffix = 'sa3hk4mrf/maria_5.jpg'
	if randNum == 5:
		picSuffix = 'qwbuotni3/maria_6.jpg'
	if randNum == 6:
		picSuffix = 'ndzusfmm3/maria_7.jpg'
	if randNum == 7:
		picSuffix = 'tgc2wo0fv/maria_8.jpg'
	if randNum == 8:
		picSuffix = 'e8w3cb8l7/maria_9.jpg'
	if randNum == 9:
		picSuffix = 'hh0kpcuuz/maria_10.jpg'
	if randNum == 10:
		picSuffix = 'bu47rvscb/maria_11.jpg'
	if randNum == 11:
		picSuffix = '42nhtbo6z/maria_12.jpg'
	if randNum == 12:
		picSuffix = 'h82zzfi2j/maria_13.jpg'
	if randNum == 13:
		picSuffix = 'wi2v6mdkr/maria_14.jpg'
	if randNum == 14:
		picSuffix = '6b1oanvaz/maria_15.jpg'

	return 'https://s' + sNum + '.postimg.org/' + picSuffix

def PeoplePics(wordList):
	# TODO - implement switches so only one pic for each person is posted
	for word in wordList:
		# Joe
		if word == 'joe':
			return PostJoePic()	
			break
		
		# Maria / MC
		if word == "maria" or word == "mc":
			return PostMariaPic()
			break

	return "-0"

#######################################