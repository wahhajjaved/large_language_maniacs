#!/usr/bin/python
# -*- coding: utf-8 -*-

if not os.path.exists(log_folder): os.mkdir(log_folder)
if not os.path.exists(public_log): os.mkdir(public_log)
if not os.path.exists(system_log) and GT('syslogs_enable'): os.mkdir(system_log)

last_log_file = {}
last_log_presence = {}

log_header = ['','<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru"><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8" /><link href="%s" rel="stylesheet" type="text/css" /><title>\n' % logs_css_path][GT('html_logs_enable')]
def initial_log_users(room,ott):
	txt = []
	for tmp in megabase:
		if tmp[0] == room: txt.append(tmp[1])
	txt.sort()
	log_body = ['[%s] ' % ott,'<p><a id="%s" name="%s" href="#%s" class="time">%s</a> ' % (ott,ott,ott,ott)][GT('html_logs_enable')]
	log_body += ['*** ','<span class="status">'][GT('html_logs_enable')]
	log_body += L('Users: %s (%s)') % (', '.join(txt),len(txt))
	log_body += ['','</span></p>'][GT('html_logs_enable')] + '\n'
	return log_body

def append_message_to_log(room,jid,nick,type,text):
	global public_log, system_log
	hr = getFile(log_conf,[])
	if len(hr) and room in hr:
		if GT('html_logs_enable'): text,jid,nick = html_escape(text).replace('\n','<br>'), html_escape(jid), html_escape(nick)
		if type == 'groupchat' and text != 'None': msg_logger(room,jid,nick,type,text,public_log)
		if type == 'chat' and text != 'None': nick = 'chat | '+nick
		if text != 'None' and GT('syslogs_enable'): msg_logger(room,jid,nick,type,text,system_log)
		
def write_log_with_end(curr_path,curr_file,log_body,log_he):
	global last_log_file
	if not os.path.isfile(curr_file):
		fl = open(curr_file, 'a')
		fl.write(log_he.encode('utf-8'))
		fl.write(log_body.encode('utf-8'))
		try:
			ll = last_log_file[curr_path]
			if os.path.isfile(ll):
				ender = ['\n','</div></div><br>%s</body></html>' % GT('html_logs_end_text')][GT('html_logs_enable')]
				fle = open(ll, 'a')
				fle.write(ender.encode('utf-8'))
				fle.close()
		except: pass
	else:
		fl = open(curr_file, 'a')
		fl.write(log_body.encode('utf-8'))
	fl.close()
	last_log_file[curr_path] = curr_file
		
def msg_logger(room,jid,nick,type,text,logfile):
	lt = tuple(time.localtime())
	curr_path = logfile+'/'+room
	if not os.path.exists(curr_path): os.mkdir(curr_path)
	curr_path = curr_path+'/'+str(lt[0])
	if not os.path.exists(curr_path): os.mkdir(curr_path)
	curr_path += '/'+tZ(lt[1])
	if not os.path.exists(curr_path): os.mkdir(curr_path)
	curr_file = curr_path + '/'+tZ(lt[2])+['.txt','.html'][GT('html_logs_enable')]
	ott = onlytimeadd(tuple(localtime()))
	log_body = ['[%s] ' % ott,'<p><a id="%s" name="%s" href="#%s" class="time">%s</a> ' % (ott,ott,ott,ott)][GT('html_logs_enable')]
	if nick == '': log_body += ['*** %s\n','<span class="topic">%s</span></p>'][GT('html_logs_enable')] % text
	else:
		if text[:4] == '/me ': log_body += ['*%s %s','<span class="me">%s %s</span></p>\n'][GT('html_logs_enable')] % (nick,text[4:])
		else: log_body += ['%s: %s','<span class="nick">%s:&nbsp;</span><span class="text">%s</span></p>\n'][GT('html_logs_enable')] % (nick,text)
	lht = room+' - '+str(lt[0])+'/'+tZ(lt[1])+'/'+tZ(lt[2])
	log_he = ['%s\t\thttp://isida-bot.com\n\n' % lht,log_header+lht+'</title></head><body><div class="main"><div class="top"><div class="heart"><a href="http://isida-bot.com">http://isida-bot.com</a></div><div class="conference">'+lht+'</div></div><div class="container">\n'][GT('html_logs_enable')]
	try: log_he += initial_log_users(room,ott) + ['[%s] ' % ott,'<p><a id="%s" name="%s" href="#%s" class="time">%s</a> ' % (ott,ott,ott,ott)][GT('html_logs_enable')] + ['*** %s\n','<span class="topic">%s</span></p>'][GT('html_logs_enable')] % [topics[room],html_escape(topics[room]).replace('\n','<br>')][GT('html_logs_enable')]
	except: pass
	write_log_with_end(logfile+room,curr_file,log_body,log_he)

def append_presence_to_log(room,jid,nick,type,mass):
	global public_log, system_log
	hr = getFile(log_conf,[])
	if len(hr) and room in hr:
		# (text, role, affiliation, exit_type, exit_message, show, priority, not_found)
		try: llp = [last_log_presence[room+jid+nick],None][type == 'unavailable']
		except: llp = None
		last_log_presence[room+jid+nick] = mass
		if mass == llp: return
		if GT('html_logs_enable'): jid,nick = html_escape(jid), html_escape(nick)
		presence_logger(room,jid,nick,type,mass,0,public_log)
		if GT('syslogs_enable'): presence_logger(room,jid,nick,type,mass,1,system_log)

def presence_logger(room,jid,nick,type,mass,mode,logfile):
	role,affiliation = [mass[1],html_escape(mass[1])][GT('html_logs_enable')], [mass[2],html_escape(mass[2])][GT('html_logs_enable')]
	if nick[:11] != '<temporary>' and role != 'None' and affiliation != 'None':
		text,exit_type = [mass[0],html_escape(mass[0])][GT('html_logs_enable')],mass[3]
		if GT('html_logs_enable') and text[:20] == '&lt;br&gt;&amp;nbsp;': text = ' %s' % text[20:]#text = correct_html(text)
		exit_message,show = [mass[4],html_escape(mass[4])][GT('html_logs_enable')], [mass[5],html_escape(mass[5])][GT('html_logs_enable')]
		priority,not_found = mass[6],mass[7]
		if not_found == 1 and not GT('aff_role_logs_enable'): return
		if not_found == 2 and not GT('status_logs_enable'): return
		lt = tuple(time.localtime())
		curr_path = logfile+'/'+room
		if not os.path.exists(curr_path): os.mkdir(curr_path)
		curr_path = curr_path+'/'+str(lt[0])
		if not os.path.exists(curr_path): os.mkdir(curr_path)
		curr_path += '/'+tZ(lt[1])
		if not os.path.exists(curr_path): os.mkdir(curr_path)
		curr_file = curr_path + '/'+tZ(lt[2])+['.txt','.html'][GT('html_logs_enable')]
		ott = onlytimeadd(tuple(localtime()))
		log_body = ['[%s] ' % ott,'<p><a id="%s" name="%s" href="#%s" class="time">%s</a> ' % (ott,ott,ott,ott)][GT('html_logs_enable')]
		if type == 'unavailable': 
			log_body += ['*** %s','<span class="unavailable">%s'][GT('html_logs_enable')] % nick
			if mode and jid != 'None': log_body += ' ('+jid+')'
			if len(exit_type): log_body += ' '+exit_type.lower()
			else: log_body += ' '+L('leave')
			if exit_message != '': log_body += ' ('+exit_message+') '
			log_body += ['','</span></p>'][GT('html_logs_enable')] + '\n'
		else:
			log_body += ['*** %s','<span class="status">%s'][GT('html_logs_enable')] % nick
			if not_found == 0:
				if mode and jid != 'None': log_body += ' ('+jid+')'
				log_body += ' '+L('join as')+' '+L(role+'/'+affiliation)
			elif not_found == 1: log_body += ' '+L('now is')+' '+L(role+'/'+affiliation)
			elif not_found == 2: log_body += ' '+L('now is')+' '
			if not_found == 0 or not_found == 2:
				if show != 'None': log_body += ' '+show
				else: log_body += ' online'
				if priority != 'None': log_body += ' ['+priority+']'
				else:  log_body += ' [0]'
				if text != 'None':  log_body += ' ('+text+')'
			log_body += ['','</span></p>'][GT('html_logs_enable')] + '\n'
		lht = room+' - '+str(lt[0])+'/'+tZ(lt[1])+'/'+tZ(lt[2])
		log_he = ['%s\t\thttp://isida-bot.com\n\n' % lht,log_header+lht+'</title></head><body><div class="main"><div class="top"><div class="heart"><a href="http://isida-bot.com">http://isida-bot.com</a></div><div class="conference">'+lht+'</div></div><div class="container">\n'][GT('html_logs_enable')]
		try: log_he += initial_log_users(room,ott) + ['[%s] ' % ott,'<p><a id="%s" name="%s" href="#%s" class="time">%s</a> ' % (ott,ott,ott,ott)][GT('html_logs_enable')] + ['*** %s\n','<span class="topic">%s</span></p>'][GT('html_logs_enable')] % [topics[room],html_escape(topics[room]).replace('\n','<br>')][GT('html_logs_enable')]
		except: pass
		write_log_with_end(logfile+room,curr_file,log_body,log_he)

global execute

message_control = [append_message_to_log]
presence_control = [append_presence_to_log]

def log_room(type, jid, nick, text):
	if type == 'groupchat': msg = L('This command available only in private!')
	else:
		hmode = text.split(' ')[0]
		try: hroom = text.split(' ')[1]
		except: hroom = jid
		hr = getFile(log_conf,[])
		if hmode == 'show':
			if len(hr):
				msg = L('Logged conferences:')
				for tmp in hr: msg += '\n'+tmp
			else: msg = L('Logs are turned off in all conferences.')
		elif hmode == 'add':
			if not match_room(hroom): msg = L('I am not in the %s') % hroom
			elif hr.count(hroom): msg = L('Logs for %s already enabled.') % hroom
			else:
				hr.append(hroom)
				msg = L('Logs for %s enabled.') % hroom
				writefile(log_conf,str(hr))
		elif hmode == 'del':
			if not match_room(hroom): msg = L('I am not in the %s') % hroom
			elif hr.count(hroom):
				hr.remove(hroom)
				msg = L('Logs for %s disabled.') % hroom
				writefile(log_conf,str(hr))
		else: msg = L('What?')
	send_msg(type, jid, nick, msg)

execute = [(9, 'log', log_room, 2, L('Logging history conference.\nlog [add|del|show][ room@conference.server.tld]'))]
