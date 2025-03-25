'''
bot.py can be used to automate IRC tasks or create a bot.  It can be used as is, but with
limited functionality.  It will simply join a server of your choice with the given credentials.
If you want to add commands that your IRC bot will interpret, you can add them by using the 
bot.Bot.add_cmd() function.  You may also want to take a look at comm.py.

By default, commands are read in from all channel messages.  For example, someone saying 
'!slap Nick' in a channel that the bot is in would proc the 'slap' command, and the bot
would respond by slapping Nick around a bit with a large trout.

Things to note:
	 - This bot was setup specifically for Freenode IRC
	 - A few threads are going to spawn
	 - Your nick must be registered to use

To use add_cmd(), your function should take parameters like so:
	func(self, sender, channel, cmd, params)

Example:
	
	def slap(self, sender, channel, cmd, params):
		message = 'slaps ' + (params.split(' ')[0] or sender) + " around a bit with a large trout"
		self.comm.perform_action(message, channel)
	
	bot = ircbot.bot('chat.freenode.net', 6697, 'NickBot', 'password1234')
	bot.add_cmd('slap', slap)
	bot.conn()
	bot.join('#channel')
	
	
'''
import threading
import re
import time
import os

class Bot():
	def __init__(self, server, port, username, password=None, hostname="Host", servername='', realname='', nickname='', cmdIdentifier='!', sslOn=True, logs=False):
		'''Initializes:  server, port, username
		If you are registered with the username, set the password parameter.
		Other parameters:
							nickname		default is given username
							hostname		default is "Host"
							realname		default is given username
							servername		default is given server
							cmdIdentifier	default is '!'
							sslOn			default is True
							logs			default is False, set to True if you want
											logs saved in 'nickname_logs/'
		'''
		self.server = server
		self.port = port
		self.username = username
		self.password = password
		
		### Set all defaults ###
		self.hostname = hostname  # default is "Host"
		self.sslOn = sslOn  # default is True
		self.cmdIdentifier = cmdIdentifier  # default identifier is '!'
		
		# set nick to username if not set
		if not nickname:
			self.nickname = username
		else:
			self.nickname = nickname
		
		# set servername to server if not set
		if not servername:
			self.servername = server
		else:
			self.servername = servername
		
		# set realname to username if not set
		if not realname:
			self.realname = username
		else:
			self.realname = realname
		
		# queue of past commands (100)
		self.chat_queue = []
		
		self.commands = {}
		import comm
		self.comm = comm #__import__('comm')
		self.channel_list = []
		self.chanserv = 'ChanServ'  # for accessing channel permissions
		self.accessLists = {}  # for obtaining channel access lists
		self.namesList = {}  # for updating whos in the channel
		self.logs = logs
		self.log_dir = self.nickname + '_logs'
		self.logfile = self.log_dir + '/ircbotlog.txt'
		self.canJoin = False
		self.lastUpdate = 0
		self.channels_updating = []   # list of channels that are updating access lists
		# if logs is turn on, confirm directory exists
		if self.logs and not os.path.exists(self.log_dir):
			os.mkdir(self.log_dir)
		
	
	def conn(self):
		'''Connect to IRC server, logs in, and starts the message handler'''
		self.comm.conn((self.server, self.port), self.sslOn)
		self.comm.login(self.nickname, self.username, self.password, self.realname, self.hostname, self.servername)
		
		# start handler
		t = threading.Thread(target=self.handler)
		t.start()
	
	def join(self, channel):
		'''Join the given channel'''
		# infinite loop until self.conJoin flag is set
		while not self.canJoin:
			time.sleep(5)
		self.comm.join(channel)
	
	def recv(self):
		'''Recommended to not use this function directly.  The function, handler(), will process input/output.'''
		self.comm.recv()
	
	def disconnect(self, message='Goodbye cruel world!'):
		'''Disconnects the bot from IRC with message'''
		self.comm.disconnect(message)
	
	def handleCmd(self, buffer):
		'''Handles commands.  Handler() is meant to spawn a new thread when calling handleCmd() to increase speed.'''
		# syntax is:
		#      :user!user@ip PRIVMSG #channel :!command <optional params>
		bufflist = buffer.split(' ')
		cmd = bufflist[3][2:]  # get cmd ASAP
		
		if cmd not in self.commands:
			return
		
		sender = bufflist[0][:bufflist[0].find(self.cmdIdentifier)][1:]  # get sender
		channel = bufflist[2]  # get channel
		
		# get params if there are any
		params = ''
		if len(bufflist) > 4:
			params = ' '.join(bufflist[4:])
		
		func = self.commands[cmd]  # get function
		func(self, sender, channel, cmd, params) # call function
	# end handleCmd
	
	def handleNames(self, buffer):
		'''This function is used to handle a channel's current names and update the bot's lists of who is in a channel'''
		names = (''.join(buffer.split(' ')[5:]))[1:].split(' ')
		channel = buffer.split(' ')[4]
		print "========== Found Names:",names
		for i in range(len(names)):
			if names[i] == '':
				continue
			if names[i][0] == '+':# or names[i][0] == '@':
				names[i] = names[i][1:]
		self.namesList[channel] = names
	
	def handleAccessList(self, messageList):
		''' Attempts to handle notice's from chanserve contain the users' flags.  May fail.
		If it doesn't... it will add the access list to self.flag_dict[channel]'''
		messages = '\n'.join(messageList)
		pattern = r"\d+\s+[A-Za-z0-9_]+\s+\+[A-Za-z]+"
		found = re.findall(pattern, messages)
		
		if not found:
			return 
		
		flag_dict = {}
		for set in found:
			set = set.replace('\t',' ')
			while '  ' in set:
				set = set[:set.find('  ')] + set[set.find('  ')+1:]
			set = set.split(' ')
			
			user = set[1]
			flags = set[2][1:]
			
			for flag in flags:
				if flag not in flag_dict:
					flag_dict[flag] = [user]
				else:
					flag_dict[flag].append(user)
		
		# last appended message should contain the channel
		n = messageList[-1].find('\x02#')
		if n == -1: return
		channel = messageList[-1][messageList[-1].find('\x02#')+1:]
		n = channel.find('\x02')
		if n == -1: return
		channel = channel[:n]
		
		# set the channels flags
		self.accessLists[channel] = flag_dict
	# end handleAccessList
	
	def handler(self):
		'''Handles input and sends responses for the bot'''
		isCmd = re.compile(r'\S+ PRIVMSG #\S+ :!.+', re.IGNORECASE)
		wasKicked = re.compile(r'\S+ KICK #\S+ ' + self.nickname + r' :.*', re.IGNORECASE)
		isChanServNotice = re.compile(r':' + self.chanserv + r'!\S+ NOTICE ' + self.nickname + r' :.+', re.IGNORECASE)
		isBotJoin = re.compile(r':' + self.nickname + r'!\S+ JOIN #\S+', re.IGNORECASE)
		isJoin = re.compile(r':\S+!\S+ JOIN #\S+', re.IGNORECASE)
		isPart = re.compile(r':\S+!\S+ PART #\S+', re.IGNORECASE)
		isError = re.compile(r'ERROR .*', re.IGNORECASE)
		isNamesList = re.compile(r'\S+ \d+ \S+ * #\S+ :.*')
		
		cs_noticeList = []  # list of notices from chanserv
		
		# set f if loggin is on
		f = False
		if self.logs:
			f = open(self.logfile,'a+')
		
		while True:
			try:
				# get next input
				buffer = self.comm.recv()
				if buffer:
					print ">"+buffer
				else:
					continue
				
				# disallow joins until identified
				if not self.canJoin and "You are now identified for \x02" + self.nickname + "\x02" in buffer:
					self.canJoin = True
				
				if f:  f.write(buffer + '\n')
				
				# check if ping, to respond with pong
				if buffer[:5] == 'PING ':
					sender = buffer.split(' ')[1][1:]
					self.comm.pong(sender)
					continue
				
				# save message into queue
				self.chat_queue.append(buffer)
				if len(self.chat_queue) > 100:
					self.chat_queue = self.chat_queue[1:]
				
				# check if command message from channel
				if isCmd.match(buffer):
					t = threading.Thread(target=self.handleCmd, args=(buffer,))
					t.start()
				# check if joining a channel
				elif isBotJoin.match(buffer):
					channel = buffer.split(' ')[2]
					
					if channel in self.channel_list:
						# update who's in the channel
						t = threading.Thread(target=self.updateNames, args=(channel,))
						t.start()
						continue
					self.channel_list.append(channel)
					if channel not in self.channels_updating:
						self.channels_updating.append(channel)
						self.updateAccess(channel)
				# check if was kicked, rejoin if so
				elif wasKicked.match(buffer):
					channel = buffer.split(' ')[2]
					if channel in self.channel_list:
						self.channel_list.remove(channel)
					self.comm.join(channel)
				# catch chanserv notices
				elif isChanServNotice.match(buffer):
					# just hope no other chanserv notices distrupt this...
					messageList = buffer.split(' ')[3:]
					message = ' '.join(messageList)[1:]
					
					if messageList[0][1:].lower() == 'entry':
						cs_noticeList = []
					cs_noticeList.append(message)
					# last appended message should contain the channel
					if messageList[0][1:].lower() == 'end':
						t = threading.Thread(target=self.handleAccessList, args=(cs_noticeList,))
						t.start()
				elif isNamesList.match(buffer):
					# get the names
					t = threading.Thread(target=self.handleNames, args=(buffer,))
					t.start()
				elif isJoin.match(buffer):
					channel = buffer.split(' ')[2]
					# update who's in the channel
					t = threading.Thread(target=self.updateNames, args=(channel,))
					t.start()
				elif isPart.match(buffer):
					channel = buffer.split(' ')[2]
					# update who's in the channel
					t = threading.Thread(target=self.updateNames, args=(channel,))
					t.start()
				elif isError.match(buffer):
					raise buffer
			except Exception,e:
				# catch all exceptions and exit
				print "Exception in handler: ",e
				os._exit(1)
			
	# end handler
	
	def updateNames(self, channel):
		'''This function is used to send a request to update the bot's list of who is in a channel'''
		self.comm.names(channel)
	
	def updateAccess(self, channel):
		'''This function is used to update the bot's channel access lists for a given channel every hour.'''
		thisUpdate = int(time.time())
		
		# wait at least 10 minutes before requesting another update
		if (thisUpdate - self.lastUpdate) / 60 < 10:
			return
		
		message = "flags " + channel
		self.comm.messageUser(message, self.chanserv)
		
		# request again in an hour
		t = threading.Timer(60*60, self.updateAccess, args=(channel,))
		t.start()
	
	def add_cmd(self, command, function):
		'''This adds the given command and runs function when a users says !command
		The function should take parameters like:
				func(self, sender, channel, cmd, params)'''
		self.commands[command] = function










