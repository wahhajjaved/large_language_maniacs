#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import socket
import time
import os
import select
import Queue
import subprocess
from Tkinter import *
from chk_wiki import Wiki
from responses import Response
                   

class Client(object):
    
    def __init__(self, **kwargs):
        self.root = kwargs['root']
        self.user = kwargs['user']
        self.port = kwargs['port']
        self.password = kwargs['password']
        self.channel = kwargs['channel'] 
        self.nick = kwargs['nick']
        self.host = kwargs['host']
        self.create_window
        self.connect_to_host
        self.conn = False                                 
        self.paused = False 
        self.logging = False
        self.search = False
        self.verbose = True
        self.blocked = list()
        self.ln_strip = lambda s: s.strip(':')
        self.rspd = Response(self.chat_log, self.nick, 
                                  self.prefix_response) 
        self.server_reply = {'311':self.rspd.whois_user_repl,  
                             '319':self.rspd.whois_chan_repl, 
                             '353':self.rspd.names_repl,      
                             '371':self.rspd.info_repl,
                             '364':self.rspd.links_repl,
                             '481':self.rspd.perm_denied_repl,
                             '263':self.rspd.rate_lim_repl,
                             '212':self.rspd.server_com_repl,
                             '211':self.rspd.server_con_repl,
                             '242':self.rspd.server_utme_repl,
                             '250':self.rspd.server_utme_repl,
                             '215':self.rspd.clnt_auth_repl,
                             '351':self.rspd.server_ver,
                             '005':self.rspd.server_aux,
                             '331':self.rspd.chan_topic,
                             '332':self.rspd.chan_topic,
                             '433':self.rspd.nick_inuse,
                             '314':self.rspd.whois_user_repl,
                             '322':self.rspd.list_repl,
                             '219':self.rspd.server_com_end,
                             '366':self.rspd.end_names_repl
                            }

        self.commands = {'names':self._names, 
                         'whois':self._whois, 
                         'info':self._info, 
                         'help':self._help,
                         'links':self._links, 
                         'stats':self._stats,
                         'quit':self._quit,
                         'part':self._part,
                         'join':self._join,
                         'wjoin':self._wjoin,
                         'suser':self._shared,
                         'noise':self._noise,
                         'block':self._block,
                         'unblock':self._unblock,
                         'topic':self._topic,
                         'version':self._version,
                         'whereami':self._whereami,
                         'blocklist':self._blocklist,
                         'nick':self._nick,
                         'whowas':self._whowas,
                         'whatis':self._whatis,
                         'whoami':self._whoami,
                         'list':self._list,
                         'pause':self._pause,
                         'reconnect':self._reconnect,
                         'msg':self._usermsg,
                         'log':self._log
                        }

    def _names(self, chan=None):
        '''
           Usage: /NAMES <channel> --> List all nicks visible on channel.
        ''' 
        if chan is None: return self.command_error(self._names.__doc__)
        query = 'NAMES %s\r\n' % chan
        self.cmd_names = True
        self.client.sendall(query)

    def _shared(self, chan1=None, chan2=None):
        '''
            Usage: /SUSER <channel 1> <channel 2> --> List all nicks in both channels.
        '''
        if not all([chan1, chan2]):
            return self.command_error(self._shared.__doc__)
        self.rspd.comp_chan_names = True
        query = 'NAMES %s\r\n' % chan1
        self.client.sendall(query)
        query = 'NAMES %s\r\n' % chan2
        self.client.sendall(query)

    def _whois(self, query=None):
        '''
           Usage: /WHOIS <nick> --> Query information about a user.
        '''
        if query is None:
            return self.command_error(self._whois.__doc__)
        query = 'WHOIS %s\r\n' % query
        self.client.sendall(query)

    def _info(self, srv=None):
        '''
           Usage: /INFO (optional <server> --> Returns information that describes the server, 

           optional parameter defaults to current server.
        '''
        if srv is None:
            query = 'INFO %s\r\n' % self.server
        else:
            query = 'INFO %s\r\n' % srv
        self.client.sendall(query)

    def _links(self, srv=None):
        '''
           Usage: /LINKS --> Lists all of the servers currently linked to network.
        '''
        if srv is None:
            query = 'LINKS \r\n'
        else:
            query = 'LINKS %s\r\n' % srv
        self.client.sendall(query)

    def _stats(self, flags=None):
        '''
           Usage: /STATS <flag> --> Shows statistical information on the server.

           ## STAT-FLAGS ##:

               I = Lists all the current I:Lines (Client auth Lines)

               u = Server Uptime

               m = Gives the Server command list

               L = Information about current server connections
        '''
        if not flags:
            return self.command_error(self._stats.__doc__)
        query = 'STATS %s %s\r\n' % (flags, self.server)
        self.client.sendall(query)

    def _quit(self, msg=None):
        '''
           Usage: /QUIT (optional <message>) --> Ends a client session from server.
        '''
        q_signal = 'QUIT %s\r\n'
        try:
            self.client.sendall(q_signal) 
            self.client.close()
        except socket.error:
            pass
        if self.logging:
            self.log_file.close()
        self.root.destroy()

    def _join(self, chan=None):
        '''
           Usage: /JOIN <channel> --> Allows a client to start communicating on the specified channel
        '''
        if chan is None:
            return self.command_error(self._join.__doc__)
        if isinstance(self.channel, list):
            for channel in self.channel:
                self._part(channel)
        else: 
            self._part(self.channel)
        self.conn = False
        chan_join = 'JOIN %s\r\n' % chan
        self.client.sendall(chan_join)
        self.channel = chan.strip('#')

    def _wjoin(self, chan=None):
        '''
            Usage: /WJOIN <channel> --> Allows a client to start communicating simultaneously on the specified channel and the current channel/s
        '''
        if chan is None or not self.channel:
            return self.command_error(self._wjoin.__doc__)
        self.channel = [self.channel, chan]
        chan_join = 'JOIN %s\r\n' % chan
        self.client.sendall(chan_join)            

    def _part(self, chan=None):
        '''
           Usage: /PART <channel> --> Leave a channels active user's list.
        '''
        if chan is None:
            return self.command_error(self._part.__doc__)
        if isinstance(self.channel, str) and chan == self.channel: 
            self.channel = None
            chan_part = 'PART %s\r\n' % chan
            self.client.sendall(chan_part)
        elif isinstance(self.channel, list) and chan in self.channel:
            self.channel.remove(chan)
            chan_part = 'PART %s\r\n' % chan
            self.client.sendall(chan_part)
            if not self.channel:
                self.channel = None
        else:
            self.prefix_response("Server")
            self.chat_log.insert(END, "You are not currently in %s\n" % chan)
            self.chat_log.see(END)

    def _noise(self, flags=None):
        '''
           Usage: /NOISE <flag> --> Show or block the extra info for the current channel.

           ## NOISE-FLAGS ##:
        
               s = show all channel info

               b = block all channel info
        '''                                              
        if flags is None:
            return self.command_error(self._noise.__doc__)
        elif flags == 's':
            self.verbose = True
        elif flags == 'b':
            self.verbose = False

    def _block(self, nick=None): 
        '''
           Usage: /BLOCK <nick> --> Blocks the chat from the nick supplied.
        '''
        if nick is None:
            return self.command_error(self._block.__doc__)
        if nick not in self.blocked:
            self.blocked.append(nick)

    def _unblock(self, nick=None):
        '''
           Usage: /UNBLOCK <nick> --> Unblocks chat from a nick thats currently being blocked.
        '''
        if nick is None:
            return self.command_error(self._unblock.__doc__)
        if nick in self.blocked:
            self.blocked.remove(nick)   

    def _topic(self, chan=None):
        '''
           Usage: /TOPIC <channel> --> Prints out the topic for the supplied channel.
        '''
        if chan is None:
            return self.command_error(self._topic.__doc__)
        topic = 'TOPIC %s\r\n' % chan
        self.client.sendall(topic)

    def _version(self, server=None):
        '''
           Usage: /VERSION <server> --> Returns the version of program that the server is using.
        '''
        if server is None:
            return self.command_error(self._version.__doc__)
        ver_chk = 'VERSION %s\r\n' % server
        self.cmd_ver = True
        self.client.sendall(ver_chk)

    def _whereami(self, query=None):
        '''
           Usage: /WHEREAMI --> This command will let you know which channel and server you are

           currently connected to.
        '''
        if query is None:
            self.prefix_response("Server")
            self.chat_log.insert(END, 'You are currently connected to server <%s> and in channel <%s>\n' 
                                       % (self.server, str(self.channel))) 
            self.chat_log.see(END)

    def _blocklist(self, nick=None):
        '''
           Usage: /BLOCKLIST --> Shows all the nicks currently being blocked.
        '''
        if nick is None:
            self.prefix_response("Server")
            self.chat_log.insert(END, 'Blocked Nicks: %s\n' % str(self.blocked))
            self.chat_log.see(END)

    def _nick(self, nick=None):
        '''
           Usage /NICK <nick> --> Registers the supplied nick with services.
        '''
        if nick is None:
            return self.command_error(self._nick.__doc__)
        self.nick = nick
        self.rspd.nick = nick
        ident = "NICK %s\r\n" % self.nick
        self.client.sendall(ident)
        if self.channel: 
            self._join(self.channel)

    def _whowas(self, nick=None):
        '''
           Usage: /WHOWAS <nick> --> Returns information about a nick that doesn't exist anymore.
        '''
        if nick is None:
            return self.command_error(self._whowas.__doc__)
        whowas_msg = "WHOWAS %s\r\n" % nick
        self.client.sendall(whowas_msg)

    def _whatis(self, lookup=None):
        '''
           Usage: /WHATIS <item> --> Returns a query of wikipedia for the supplied item.
        '''
        if lookup is None:
            return self.command_error(self._whatis.__doc__)
        if not self.search:        
            self.wiki_q = Queue.Queue()
            self.wiki = Wiki(self, self.chat_log, self.prefix_response, 
                                                    lookup, self.wiki_q)
            self.wiki.start()
            self.search = True
        elif lookup.lower() == 'y':
            self.wiki_q.put('y')
        elif lookup.lower() == 'n':
            self.wiki_q.put('n')
            self.search = False
        elif lookup.isdigit():
            self.wiki_q.put(lookup)

    def _whoami(self, nick=None):
        '''
           Usage: /WHOAMI --> Prints out your current nick.
        '''
        if nick is not None:
            return self.command_error(self._whoami.__doc__)
        self.prefix_response("Server")
        self.chat_log.insert(END, "You are currently known as => %s\n" % self.nick)
        self.chat_log.see(END)

    def _list(self, log=None):
        '''
           Usage: /LIST (optional <log>) --> Will show all the channels available and their topic.
        '''
        if log is None:
            lst_msg = "LIST\r\n"
            self.client.sendall(lst_msg)
        elif log == 'l':
            lst_msg = "LIST\r\n"
            self.client.sendall(lst_msg)
            self.rspd.log_links = True

    def _help(self, cmd=None):
        '''
           Usage: /HELP (optional <command>) --> Show help information for/on valid commands.
        '''
        if cmd is None:
            self.prefix_response("Server")
            new_msg = 'Commands <<' + ' - '.join(self.commands.keys()) + '>>\n'
            self.chat_log.insert(END, new_msg)
            self.chat_log.see(END)
            return
        try:
            func_info = cmd.lower() 
            self.command_error(self.commands[func_info].__doc__)
        except KeyError:
            self.prefix_response("Server")
            new_msg = 'Unknown Command! Type /HELP for a list of commands\n'
            self.chat_log.insert(END, new_msg)
            self.chat_log.see(END)

    def _pause(self, toggle=None):
        '''
           Usage: /PAUSE <(on/off)> --> This will pause the channel's "chatter"

           Pass in "/PAUSE on" to turn on pause or

           use "/PAUSE off" to turn off pause "unpause".
        '''
        if toggle is None or toggle not in ["on", "off"]:
            return self.command_error(self._pause.__doc__)
        if toggle == 'on':
            self.paused = True
        if toggle == 'off':
            self.paused = False

    def _reconnect(self, channel=None):
        '''
           Usage: /RECONNECT (optional <channel>) --> Set-up connection from inside the chat window.
        '''
        self.conn = False
        if channel is None:
            self.client.close()
            self.connect_to_host
        if channel:
            self.channel = channel
            self.client.close()
            self.connect_to_host

    def _usermsg(self, msg, nick=None):
        '''
           Usage: /MSG <nick> <msg> --> Message a user off channel.
        '''
        if nick is None:
            return self.command_error(self._usermsg.__doc__)
        else:
            new_msg = "privmsg %s :" % nick + msg 
            self.client.sendall(new_msg + '\r\n')
            self.prefix_response(self.nick)
            window_msg = nick + ": " + msg 
            self.chat_log.insert(END, window_msg + '\n') 
            self.chat_log.see(END)
                            
    def _log(self, toggle=None):
        '''
           Usage: /LOG <(on/off)> --> Logs the chat in current channel to a file.

           Pass in "/LOG on" to open the log or

           use "/LOG off" to close the log. 
        '''
        if toggle is None or toggle not in ["on", "off"]:
            return self.command_error(self._log.__doc__)
        if toggle == 'on':
            self.logging = True
            self.log_file = open(os.path.join(os.environ['HOME'], 'chat_log.txt'), 'a')
            self.log_file.write(' -- ' + time.ctime() + ' --\n')
        if toggle == 'off':
            if self.logging:
                self.log_file.close()
            self.logging = False

    def command_error(self, cmd_doc):
        self.prefix_response("Server")
        self.chat_log.insert(END, cmd_doc + '\n')
        self.chat_log.see(END)    

    def channel_msg(self, msg):
        channel = msg.split()[0]
        if isinstance(self.channel, list) and channel not in self.channel:
            return self.command_error('Multiple channels open, specify a channel')
        elif isinstance(self.channel, list) and channel in self.channel:
            chan_msg = 'privmsg %s :' % msg + '\r\n'
            self.client.sendall(chan_msg)
            self.prefix_response(self.nick)
            self.chat_log.insert(END, msg + '\n')
            self.chat_log.see(END)
        else:
            chan_msg = 'privmsg %s :'  % self.channel + msg + '\r\n'
            self.client.sendall(chan_msg)
            self.prefix_response(self.nick)
            self.chat_log.insert(END, msg + '\n')
            self.chat_log.see(END)
        if self.logging:
            self.log_file.write(msg + '\n')

    @property
    def create_window(self):
        self.root.geometry("700x450+400+165")
        self.scrollbar = Scrollbar(self.root)
        self.scrollbar.grid(column=1, rowspan=2, sticky=E+S+N)
        self.chat_log = Text(self.root, bg="black", fg="green2",      
                             wrap=WORD, yscrollcommand=self.scrollbar.set)
        self.chat_log.grid(row=0, column=0, sticky=N+S+E+W)
        self.scrollbar.config(command=self.chat_log.yview)
        self.scrn_loop = self.chat_log.after(100, self.msg_buffer_chk)
        self.entry = Entry(self.root, bg="black", fg="green2", 
                                     insertbackground="green2")
        self.entry.bind('<Return>', self.input_handle)
        self.entry.grid(row=1, column=0, sticky=S+E+W)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.chat_log.insert(END, 'ATTEMPTING TO CONNECT TO %s #%s\n' % 
                                              (self.host, self.channel))
        self.entry.focus_set()
        self.chat_log.see(END)

    @property        
    def connect_to_host(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client.connect((self.host, self.port))
            self.client.setblocking(0)
            self.server_login
        except socket.error:
           return self.command_error('Connection Failed! --> check host & port')
            
    @property            
    def connection_drop(self):
        self.client.close()
        self.conn = False
        self.connect_to_host
        return self.command_error('Connection Dropped!')

    @property                    
    def server_login(self):
        if self.password:
            self.client.sendall('PASS %s\r\n' % self.password) 
        self.client.sendall('NICK %s\r\n' % self.nick)  
        userdata = 'USER %s %s servername :%s\r\n' % (self.nick, self.host, self.user) 
        self.client.sendall(userdata) 
        self.client.sendall('JOIN #%s\r\n' % self.channel.strip('#')) 

    @property
    def server_pong(self):
        self.client.sendall('PONG ' + self.recv_msg[1] + '\r\n')
        self.prefix_response("Server")
        self.chat_log.insert(END, "Channel Ping@ ==> %s\n" % time.ctime())
        if self.scrollbar.get()[1] == 1.0:
            self.chat_log.see(END)

        
    def prefix_response(self, prefix_name, peer_state=None):   
        prefix = prefix_name + ' ' * (16 - len(prefix_name)) + '| '
        pos = float(self.chat_log.index(END)) - 1
        self.chat_log.insert(END, prefix)
        if prefix_name == "Server":
            self.chat_log.tag_add("server", str(pos), str(pos + 0.16))
            self.chat_log.tag_config("server", background="gold", 
                                                    foreground="black")
        elif prefix_name == self.nick:
            self.chat_log.tag_add("user", str(pos), str(pos + 0.16))
            self.chat_log.tag_config("user", background="turquoise1",
                                                    foreground="black")
        else:
            if peer_state == 'response':
                self.chat_log.tag_add("peer_response", str(pos), str(pos + 0.16))
                self.chat_log.tag_config("peer_response", background="green2",
                                                        foreground="black")
            elif peer_state == 'enter':
                self.chat_log.tag_add("peer_enter", str(pos), str(pos + 0.16))
                self.chat_log.tag_config("peer_enter", background="red2",
                                                        foreground="black")
            elif peer_state == 'directed':
                self.chat_log.tag_add("peer_directed", str(pos), str(pos + 0.16))
                self.chat_log.tag_config("peer_directed", background="violetred1",
                                                           foreground="black")
            elif peer_state == 'private':
                self.chat_log.tag_add("peer_private", str(pos), str(pos + 0.16))
                self.chat_log.tag_config("peer_private", background="purple",
                                                          foreground="black")
            else:
                self.chat_log.tag_add("peer_leave", str(pos), str(pos + 0.16))
                self.chat_log.tag_config("peer_leave", background="royal blue",
                                                        foreground="black")

    def buffer_data_handle(self, buffer_data):
        if buffer_data:
            for i in [j.split() for j in buffer_data.split('\r\n') if j]:
                self.recv_msg = map(self.ln_strip, i)
                if self.recv_msg[0] == 'PING':
                    self.server_pong
                elif len(self.recv_msg) >= 3: 
                    self.msg_handle()       
        else:
            self.connection_drop

    def channel_join(self, user, channel):
        if user == self.nick and not isinstance(self.channel, list):
            self.channel = channel 
            if not self.conn:
                self.chat_log.insert(END, 'SUCCESSFULLY CONNECTED TO %s\n' % self.host)
            self.chat_log.insert(END, "SUCCESSFULLY JOINED %s\n" % channel)
            self.chat_log.see(END)
        elif user != self.nick and self.verbose:
            if isinstance(self.channel, list) and channel not in self.channel:
                self.channel.append(channel)
            else:
                self.channel = channel
            self.prefix_response(user, 'enter')
            new_msg = "entered --> %s\n" % channel
            self.chat_log.insert(END, new_msg)
            if self.scrollbar.get()[1] == 1.0:
                self.chat_log.see(END)

    def channel_quit(self, user, chan): 
        if user != self.nick and self.verbose:
            self.prefix_response(user, 'leave')
            new_msg = "left --> %s\n" % chan 
            self.chat_log.insert(END, new_msg)
            if self.scrollbar.get()[1] == 1.0:
                self.chat_log.see(END)

    def parse_msg(self, token):
        if 'http' in token:
            self.chat_log.tag_config(token, underline=1)
            self.chat_log.tag_bind(token, "<Enter>", 
                                   lambda e: self.chat_log.config(cursor="hand2"))
            self.chat_log.tag_bind(token, "<Leave>", 
                                   lambda e: self.chat_log.config(cursor=""))
            self.chat_log.tag_bind(token, "<Button-1>", 
                                   lambda e: self.open_link(e))
            self.chat_log.insert(END, token, token)
            self.chat_log.insert(END, ' ')
        else:
            self.chat_log.insert(END, token + ' ')

    def open_link(self, tk_event):
        link = self.chat_log.tag_names(CURRENT)[0]
        subprocess.Popen(["firefox", link])

    def chat_msg(self, channel, user, msg):
        if msg[0] == self.nick and channel != self.nick:
            self.prefix_response(user, 'directed')
        elif channel == self.nick:
            self.prefix_response(user, 'private')
            msg.insert(0, user + ': ')
        else:
            self.prefix_response(user, 'response')
        for token in msg:
            self.parse_msg(token)
        self.chat_log.insert(END, '\n')
        if self.scrollbar.get()[1] == 1.0:
            self.chat_log.see(END)
        if self.logging:
            self.log_file.write(' '.join(msg) + '\n') 		

    def server_reply_msg(self, user, cmd):
        self.server = user
        self.rspd.server = user
        if self.conn:
            try:
                reply = self.server_reply[cmd]
                reply(self.recv_msg[3:])
            except KeyError:
                pass 
        if cmd == '366':
            self.conn = True

    def input_handle(self, event):
        msg = self.entry.get()
        self.entry.delete(0, 'end')
        if not msg: return
        if msg.startswith('/'):
            msg = msg.split() + [None]
            msg_cmd = msg[0][1:].lower()
            command = self.commands.get(msg_cmd)
            if command and msg_cmd != "msg" and msg_cmd != "suser":
                command(msg[1])
            elif command and msg_cmd == "msg":
                command(' '.join(msg[2:-1]), msg[1])
            elif command and msg_cmd == "suser":
                command(msg[1], msg[2])
            else:
                if self.scrollbar.get()[1] == 1.0:
                    self.chat_log.see(END)
                return self.command_error('Unknown Command! Type /HELP for list of commands\n')
        else:
            self.channel_msg(msg) 

    def msg_buffer_chk(self):        
        socket_data = select.select([self.client], [], [], 0.01)
        if socket_data[0]:
            try:
                buffer_data = self.client.recvfrom(4096)[0]
                self.buffer_data_handle(buffer_data)
            except socket.error:
                return self.command_error('Bad Connection!')
        self.root.update_idletasks()
        self.scrn_loop = self.chat_log.after(100, self.msg_buffer_chk)
    
    def msg_handle(self):
        user, cmd, channel = self.recv_msg[:3]  
        user = user.split('!')[0].strip(':')
        if user.endswith('.freenode.net'): 
            self.server_reply_msg(user, cmd)
        if cmd == 'PRIVMSG' and user not in self.blocked and not self.paused:
            self.chat_msg(channel, user, self.recv_msg[3:])
        if cmd == 'JOIN':
            self.channel_join(user, channel)
        if cmd == 'QUIT':
            self.channel_quit(user, channel)
