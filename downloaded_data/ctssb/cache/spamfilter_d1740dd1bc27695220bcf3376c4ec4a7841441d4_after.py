import time
import glob
import random
import sys
import os
import pickle
from collections import defaultdict


class Predictor:
    '''
    Predictor which will do prediction on emails
    '''
    def __init__(self, spamFolder, hamFolder):
        self.__createdAt = time.strftime("%d %b %H:%M:%S", time.gmtime())
        self.__spamFolder = spamFolder
        self.__hamFolder = hamFolder
        self.__spamFrequency = 0

        # do training on spam and ham
        self.__trained = self.__train__()

    def __train__(self):
        '''train model on spam and ham'''
        # the following code is only an naive example,
        # implement your own training methond here
        spamCount = len(glob.glob(self.__spamFolder+'/*'))
        hamCount = len(glob.glob(self.__hamFolder+'/*'))
        #self.__spamFrequency = 1.0*spamCount/(spamCount+hamCount)
        toks = tokenizedirs([self.__spamFolder+'/*', self.__hamFolder+'/*'])

        print "mothafucka: ", toks

        return biNaiveBayes(toks[:][1])
        
    def getTrained(self):
    	return self.__trained

    def predict(self, filename):
        '''Take in a filename, return whether this file is spam
        return value:
        True - filename is spam
        False - filename is not spam (is ham)
        '''
        # do prediction on filename
        if random.random() <= self.__spamFrequency:
            return True
        else:
            return False

	def bigramify(self, str):
		return "hey"

def tokenizer(filename):
	file = open(filename, 'r')
	viabletext = ""
	lines = file.readline()
	word = lines.split()[0]
	
	while (not (word == "Subject:")):
		lines = file.readline()
		word = lines.split()[0]	
	if (word == "Subject:"):
		while (not (lines == "")):
			viabletext = viabletext + lines
			lines = file.readline()
	else :
		print "you dun goofed"
	toks = viabletext.split()
	for i in range(len(toks)):
		if (toks[i].isdigit()):
			if (len(toks[i]) == 6):
				toks[i] = "JSNUM6"
			elif (len(toks[i]) == 3):
				toks[i] = "JSNUM3"
			else:
				toks[i] = "JSNUM"
		if (toks[i][0] == "$"):
			toks[i] = "JSMONEY"
		if (not(toks[i].find("http") == -1) or not(toks[i].find("www") == -1)):
			toks[i] = "JSWEBSITE"
	return toks

	
def tokenizedirs(dirs):
	print dirs
	classes = []
	for dir in dirs:
		dirclass = []
		files = glob.glob(dir+"/*")
		for file in files:
			print file
			dirclass.append(tokenizer(file))
		
		classes.append((dir, dirclass))
	return classes
		
		
def BiGramsTokenizer (string) :
	str = []
	for word in string:
		#print "word is ", word
		if word == 'JSNUM' or word == 'JSNUM3' or word == 'JSNUM6' or word == 'JSMONEY':
			str.append(word)
		if word.isalpha():
			str.append(word.lower())
	#print "printing str ", str
	return str

def createVocab (allStrings) :
	dir = {}
	for string in allStrings:
		#print "string ", string
		string = BiGramsTokenizer(string)
		for i in range(len(string)-1):
			word1 = string[i]
			word2 = string[i+1]
			#print word1, word2
			if (word1, word2) in dir:
				dir[(word1,word2)] += 1
			else :
				dir[(word1,word2)] = 0
	return dir

def biNaiveBayes (spamham) :
	print "spam ham in beNaiveBaives", spamham
	vocab = defaultdict(int)
	for allStrings in spamham:
		vocab.update(createVocab(allStrings))
	classes = []
	i = 0
	print "vocab", vocab
	for allStrings in spamham:
		countdict = defaultdict(int, vocab)
		countdict.update(createVocab(allStrings))
		m = 1
		total = len(countdict.keys())
		for ele in countdict:
			countdict[ele] = float(countdict[ele] + m) / float(len(allStrings) + total/m)
			print "printing countdict ", countdict[ele]
		classes.append((i,countdict))
		i += 1
	return classes
		
		
if __name__ == '__main__':
	print "time to train"
	if not (len(sys.argv) == 4):
		print "incorrect arguments given"
	else:
		if (os.path.isdir(sys.argv[1]) and os.path.isdir(sys.argv[2])):
			print "training"
			predictor = Predictor(sys.argv[1], sys.argv[2])
			print "trained:  ", predictor.getTrained()
			files = glob.glob(sys.argv[3]+"/*")
			for file in files:
				print predictor.predict('file')
			# save to pickle
			print 'saving predictor to pickle'
			pickle.dump(predictor, open('predictor.pickle', 'w'))
		else:
			print "you can't train on this :( sorry qq"