#Module to contain functions to handle messages
import sys
import customExceptions
import textwrap

textWrapper = textwrap.TextWrapper(break_long_words=False)

class Message():
	shortname = "message(s)"
	"Class that describes messages displayed at end of program"
	def __init__(self,msg):
		self.msg = msg	
		addToCount(Message)
		
	def display(self):
		print textWrapper.fill(self.msg)


class WarningMessage(Message):
	shortname = "warning(s)"
	def __init__(self,msg):
		self.msg = msg
		addToCount(WarningMessage)

	def display(self):
		print textWrapper.fill("* WARNING *: %s" % self.msg)


class ErrorMessage(Message):
	shortname = "error(s)"
	def __init__(self,msg,forcequit=False):
		self.msg = msg
		addToCount(ErrorMessage)

	def display(self):
		print textWrapper.fill("** ERROR **: %s" % self.msg)


def addToCount(classname):
	if classname not in messagecount:
		messagecount[classname] = 1
	else:
		messagecount[classname] += 1

def printMessages():
	for message in messagequeue:
		message.display()
		print ""

def add(Message):
	exists = False
	for message in messagequeue:
		if Message.msg == message.msg:
			exists = True

	if not exists:
		messagequeue.append(Message)

def addWarning(msg):
	add(WarningMessage(msg))

def addMessage(msg, forcequit=False):
	add(Message(msg))
	if forcequit:
		forceQuit()

def addError(msg, forcequit=True):
	"Adds Error Message class to messagequeue; Quits program by default"
	add(ErrorMessage(msg))
	if forcequit:
		forceQuit()

def forceQuit():
	raise customExceptions.ForceQuit()

messagecount = {} #Message, count
messagequeue = []

