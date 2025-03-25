'''
This is used to communicate to the socket via IRC protocol.
Recommended to use the bot.Bot class to create a bot instead of this.
HOWEVER, this is recommended to use this to add commands to your bot.

Example of use:
	SERVER, PORT = "chat.freenode.net", 6697
	
	# connect
	comm.conn((SERVER, PORT))
	
	# login as user Nick 
	comm.login("Nick", username="Nick", password="Password1234", realname='Nicolas',hostname='Host',servername=SERVER )
	
	# join channel
	comm.join("#channel")
	
	# message a user
	comm.messageUser("Hello!", "User")
	
	# disconnect from irc
	comm.disconnect("Off to do the dishes...")
	
''' 
import ircsocket as sock


######################################################################
#                                                                    #
#          IRC (Send) Protocol                                       #
#                                                                    #
######################################################################

###################################
#         Basic Commands          #
###################################

def conn((server, port), sslOn=True):
	'''Connect to irc server at port.  SSL is on by default.'''
	sock.conn((server, port), sslOn)

def login(nickname, username, password, realname, hostname, servername):
	'''Send login data'''
	sock.send_data("USER %s %s %s %s" % (username, hostname, servername, realname))
	# send optional password
	if password:
		sock.send_data("PASS %s" % password, 1)
	sock.send_data("NICK " + nickname)

def join(channel):
	'''Join a channel'''
	sock.send_data("JOIN %s" % channel)

def part(channels, message=''):
	'''Leaves the given channel(s)'''
	if message:
		sock.send_data("PART %s %s" % (channels, message))
	else:
		sock.send_data("PART %s" % channels)

def ping(server, server2=''):
	'''Send a ping to a server'''
	if server2:
		sock.send_data("PING %s %s" % (server, server2))
	else:
		sock.send_data("PING %s" % server)

def pong(server):
	'''For a reply to ping, reply with pong as per RFC 1459'''
	sock.send_data("PONG :%s" % server)

def disconnect(message=''):
	'''Quit IRC with given message and disconnect the socket'''
	sock.send_data('QUIT :%s' % message)
	sock.disconnect()

def quit(message=''):
	'''Quit IRC with given message'''
	sock.send_data('QUIT :%s' % message)

###################################
#      Extra Utility Commands     #
###################################

def messageUser(message, user):
	'''Message a given user'''
	s = 'PRIVMSG %s :%s' % (user, message)
	while len(s) > 510:  # if the message is too long, split up message
		s = 'PRIVMSG %s :' % user 
		s += message[:510-len(s)]  # add first part of message so sending exactly 510
		message = message[510-len(s):]  # set next message to use
		sock.send_data(s)
		# set send message to check for next or to send if its short enough
		s = 'PRIVMSG %s :%s' % (user, message)
	sock.send_data(s)

def messageChannel(message, channel):
	'''Message a given channel'''
	s = 'PRIVMSG %s :%s' %  (channel, message)
	while len(s) > 510:  # if the message is too long, split up message
		s = 'PRIVMSG %s :' % channel
		s += message[:510-len(s)]  # add first part of message so sending exactly 510
		message = message[510-len(s):]  # set next message to use
		sock.send_data(s)
		# set send message to check for next or to send if its short enough
		s = 'PRIVMSG %s :%s' % (user, message)
	sock.send_data(s)

def cmessageUser(message, user, channel):
	'''Sends a private message to a user on the channel. Both users must be in that channel. Bypasses flood protection limits'''
	sock.send_data('CPRIVMSG %s %s :s' % (user, channel, message))

def noticeUser(message, user):
	'''Sends a notice to a user.  Notices are very similar to private messages.'''
	sock.send_data('NOTICE %s :%s' % (user, message))

def cnoticeUser(message, channel, user):
	'''Sends a channel notice to user.  Bypasses flood protection limits.'''
	sock.send_data('CNOTICE %s %s :%s' % (user, channel, message))

def change_topic(topic, channel):
	'''Change topic for channel'''
	sock.send_data("TOPIC %s :%s" % (channel, topic))

def kick_user(user, channel, reason='GTFO'):
	'''Kick a user from channel with a reason'''
	sock.send_data("KICK %s %s :%s" % (channel, user, reason))

def invite(user, channel):
	'''Invites a user to the channel'''
	sock.send_data("INVITE %s %s" % (user, channel))

def perform_action(action, channel):
	'''Performs the given action, commonly refered to as the /me command.  Channel can be a channel or a user'''
	message = "\x01ACTION " + action + "\x01"
	messageChannel(message, channel)

def names(channels='', server=''):
	'''This sends a request to the server, so that it sends who is in a particular channel'''
	if channels:
		if server:
			sock.send_data("NAMES %s %s" % (channels, server))
		else:
			sock.send_data("NAMES %s" % channels)
	else:
		sock.send_data("NAMES")


###################################
#          Other Commands         #
###################################

def admin(servers=''):
	if servers:
		sock.send_data("ADMIN %s" % servers)
	else:
		sock.send_data("ADMIN")

def away(message=''):
	if message:
		sock.send_data("AWAY %s" % message)
	else:
		sock.send_data("AWAY")

def die():
	sock.send_data("DIE")

def encap(source, destination, subcommand, parameters):
	sock.send_data(":%s ENCAP %s %s %s" % (source, destination, subcommand, parameters))

def error(message):
	sock.send_data("ERROR %s" % message)

def help():
	sock.send_data("HELP")

def info(target=''):
	if target:
		sock.send_data("INFO %s" % target)
	else:
		sock.send_data("INFO")

def ison(nicknames):
	sock.send_data("ISON %s" % nicknames)

def kill(client, comment):
	sock.send_data("KILL %s %s" % (client, comment))

def knock(channel, message=''):
	if message:
		sock.send_data("KNOCK %s %s" % (channel, message))
	else:
		sock.send_data("KNOCK %s" % channel)

def links(remoteServer='', serverMask=''):
	if remoteServer:
		if serverMask:
			sock.send_data("LINKS %s %s" % (remoteServer, serverMask))
		else:
			sock.send_data("LINKS %s" % remoteServer)
	else:
		sock.send_data("LINKS")

def list(channels='', server=''):
	if channels:
		if server:
			sock.send_data("LIST %s %s" % (channels, server))
		else:
			sock.send_data("LIST %s" % channels)
	else:
		sock.send_data("LIST")

def lusers(mask='', server=''):
	if mask:
		if server:
			sock.send_data("LUSERS %s %s" % (mask, server))
		else:
			sock.send_data("LUSERS %s" % mask)
	else:
		sock.send_data("LUSERS")

def modeUser(nickname, flags):
	sock.send_data("MODE %s %s" % (nickname, flags))

def modeChannel(channel, flags, args=''):
	if args:
		sock.send_data("MODE %s %s %s" % (channel, flags, args))
	else:
		sock.send_data("MODE %s %s" % (channel, flags))

def motd(server=''):
	if server:
		sock.send_data("MOTD %s" % server)
	else:
		sock.send_data("MOTD")

def namesx():
	sock.send_data("PROTOCTL NAMESX")

def oper(username, password):
	sock.send_data("OPER %s %s" % (username, password))

def rehash():
	sock.send_data("REHASH")

def restart():
	sock.send_data("RESTART")

def rules():
	sock.send_data("RULES")

def server(server, hopcount, info):
	sock.send_data("SERVER %s %s %s" % (server, hopcount, info))

def service(nickname, reserved1, distribution, type, reserved2, info):
	sock.send_data("SERVICE %s %s %s %s %s %s" % (nickname, reserved1, distribution, type, reserved2, info))

def servlist(mask='', type=''):
	if mask:
		if type:
			sock.send_data("SERVLIST %s %s" % (mask, type))
		else:
			sock.send_data("SERVLIST %s" % (mask))
	else:
		sock.send_data("SERVLIST")

def squery(servicename, text):
	sock.send_data("SQUERY %s %s" + (servicename, text))

def squit(server, comment):
	sock.send_data("SQUIT %s %s" % (server, comment))

def setname(new_real_name):
	sock.send_data("SETNAME %s" % new_real_name)

def silence(hostmask=''):
	if hostmask:
		sock.send_data("SILENCE %s" % hostmask)
	else:
		sock.send_data("SILENCE")

def stats(query, server=''):
	if server:
		sock.send_data("STATS %s %s" % (query, server))
	else:
		sock.send_data("STATS %s" % query)

def summon(user, server='', channel=''):
	if server:
		if channel:
			sock.send_data("SUMMON %s %s %s" % (user, server, channel))
		else:
			sock.send_data("SUMMON %s %s" % (user, server))
	else:
		sock.send_data("SUMMON %s" % user)

def time(server=''):
	if server:
		sock.send_data("TIME %s", server)
	else:
		sock.send_data("TIME")

def trace(target=''):
	if target:
		sock.send_data("TRACE %s" % target)
	else:
		sock.send_data("TRACE")

def uhnames():
	sock.send_data("PROTOCTL UHNAMES")

def userhost(*nicknames):
	if nicknames:
		nickname = ' '.join(nicknames)
		sock.send_data("USERHOST %s" % nickname)

def userip(nickname):
	sock.send_data("USERIP %s" % nickname)

def users(server=''):
	if server:
		sock.send_data("USERS %s" % server)
	else:
		sock.send_data("USERS")

def version(server=''):
	if server:
		sock.send_data("VERSION %s" % server)
	else:
		sock.send_data("VERSION")

def wallops(message):
	sock.send_data("WALLOPS %s" % message)

def watch(nicknames):
	sock.send_data("WATCH %s" % nicknames)

def who(name='', flag=''):
	if name:
		if flag == 'o':
			sock.send_data("WHO %s %s" % (name, flag))
		else:
			sock.send_data("WHO %s" % name)
	else:
		sock.send_data("WHO")

def whois(nicknames, server=''):
	if server:
		sock.send_data("WHOIS %s %s" % (server, nicknames))
	else:
		sock.send_data("WHOIS %s" % nicknames)

def whowas(nickname, count='', server=''):
	if count:
		if server:
			sock.send_data("WHOWAS %s %s %s" % (nickname, count, server))
		else:
			sock.send_data("WHOWAS %s %s" % (nickname, count))
	else:
		sock.send_data("WHOWAS %s" % nickname)



######################################################################
#                                                                    #
#          IRC (Recv) Protocol                                       #
#                                                                    #
######################################################################

def recv():
	'''Get the next data from the IRC server'''
	buff = sock.getNext().replace('\r','').replace('\n','')
	return buff

