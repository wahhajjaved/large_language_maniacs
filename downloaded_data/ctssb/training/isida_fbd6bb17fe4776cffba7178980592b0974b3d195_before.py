#!/usr/bin/python
# -*- coding: utf -*-

logdir = 'logs_directory.txt'
if os.path.isfile(logdir): log_folder = readfile(logdir)
else: log_folder = u'logs/'
#print '!'+log_folder+'!'
public_log = log_folder+u'chatlogs'
system_log = log_folder+u'syslogs'
if not os.path.exists(log_folder): os.mkdir(log_folder)
if not os.path.exists(public_log): os.mkdir(public_log)
if not os.path.exists(system_log): os.mkdir(system_log)

def html_repl(ms):
	ms = ms.replace('&','&amp;')
	ms = ms.replace('<','&lt;')
	ms = ms.replace('>','&gt;')
	ms = ms.replace('\"','&quot;')
	ms = ms.replace('\'','&apos;')
	ms = ms.replace(u'·','&middot;')
	ms = ms.replace(u'▼','&raquo;')
	ms = ms.replace(u'©','&copy;')
	return ms

def append_message_to_log(room,jid,nick,type,text):
#	print room,jid,nick,type,text
	global public_log, system_log
	if type == 'groupchat':
		msg_logger(room,jid,nick,type,text,public_log)
	if type == 'chat': nick = u'chat | '+nick
	msg_logger(room,jid,nick,type,text,system_log)
	sys.exit(0)

def msg_logger(room,jid,nick,type,text,logfile):
	lt = tuple(time.localtime())
	curr_path = logfile+'/'+room
	if not os.path.exists(curr_path): os.mkdir(curr_path)
	curr_path = curr_path+'/'+str(lt[0])
	if not os.path.exists(curr_path): os.mkdir(curr_path)
	curr_path += '/'+str(lt[1])
	if not os.path.exists(curr_path): os.mkdir(curr_path)
	curr_file = curr_path + '/'+str(lt[2])+'.html'

	text = html_repl(text)
	text = text.replace('\n','<br>')

	log_body = u'<a><font color=gray>['+onlytimeadd(tuple(localtime()))+']</font> '

	if nick == '':
		log_body += u'<font color=#a00000>'+text+u'</font></a><br>'
	else:
		if text[:4] == '/me ': log_body += u'<font color=#0000a0>*'+nick+'</font><font color=#000000> '+text[4:]+'</font></a><br>'
		else: log_body += u'<font color=#0000a0>&lt;'+nick+'&gt;</font><font color=#000000> '+text+'</font></a><br>'

	if not os.path.isfile(curr_file):
		header ='<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru"><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8" /><title>'+room+'</title></head><body>'
		fl = open(curr_file, 'a')
		fl.write(header.encode('utf-8'))
		fl.write(log_body.encode('utf-8'))
	else:
		fl = open(curr_file, 'a')
		fl.write(log_body.encode('utf-8'))

	ender = '</body></html>'
	fl.close()

def append_presence_to_log(room,jid,nick,type,mass):
	global public_log, system_log
	presence_logger(room,jid,nick,type,mass,0,public_log)
	presence_logger(room,jid,nick,type,mass,1,system_log)
	sys.exit(0)

def presence_logger(room,jid,nick,type,mass,mode,logfile):
	role = mass[1]
	affiliation = mass[2]
	if nick[:11] != '<temporary>' and role != 'None' and affiliation != 'None':
		text = mass[0]
		exit_type = mass[3]
		exit_message = mass[4]
		show = mass[5]
		priority = mass[6]
		not_found = mass[7]
		lt = tuple(time.localtime())
		curr_path = logfile+'/'+room
		if not os.path.exists(curr_path): os.mkdir(curr_path)
		curr_path = curr_path+'/'+str(lt[0])
		if not os.path.exists(curr_path): os.mkdir(curr_path)
		curr_path += '/'+str(lt[1])
		if not os.path.exists(curr_path): os.mkdir(curr_path)
		curr_file = curr_path + '/'+str(lt[2])+'.html'

		text = html_repl(text)
		text = text.replace('\n','<br>')

		log_body = u'<a><font color=gray>['+onlytimeadd(tuple(localtime()))+']</font><i> '

		if type == 'unavailable': 
			log_body += u'<font color=#00a000>'+nick
			if mode and jid != 'None':
				log_body += u' ('+jid+u')'
			if len(exit_type): log_body += u' '+exit_type.lower()
			else: log_body += u'вышел '
			if exit_message != '':
				log_body += u' ('+exit_message+') '
			log_body += u'</font></i></a><br>'
		else:
			log_body += u'<font color=#00a000>'+nick
			if not_found == 0:
				if mode and jid != 'None':
					log_body += u' ('+jid+u')'
				log_body += u' зашел как '+role+'/'+affiliation
			elif not_found == 1: 
				log_body += u' теперь '+role+'/'+affiliation
			elif not_found == 2:
				log_body += u' теперь '
			if not_found == 0 or not_found == 2:
				if show != 'None': log_body += ' '+show
				else: log_body += ' online'
				if priority != 'None': log_body += ' ['+priority+']'
				else:  log_body += ' [0]'
				if text != 'None':  log_body += ' ('+text+')'

			log_body += '</font></i></a><br>'

		if not os.path.isfile(curr_file):
			header ='<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru"><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8" /><title>'+room+'</title></head><body>'
			fl = open(curr_file, 'a')
			fl.write(header.encode('utf-8'))
			fl.write(log_body.encode('utf-8'))
		else:
			fl = open(curr_file, 'a')
			fl.write(log_body.encode('utf-8'))

		ender = '</body></html>'

		fl.close()

global execute

message_control = [append_message_to_log]
presence_control = [append_presence_to_log]

execute = []
