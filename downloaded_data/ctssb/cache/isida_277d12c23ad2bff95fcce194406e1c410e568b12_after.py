#!/usr/bin/python
# -*- coding: utf -*-
# --------------------------------------------------------------------
#
#                             Isida Jabber Bot
#                               version 2.00
#
# --------------------------------------------------------------------
#                  (c) 2oo9-2o1o Disabler Production Lab.
# --------------------------------------------------------------------

from __future__ import with_statement
from xmpp import *
from random import *
from time import *
from pdb import *
from subprocess import Popen, PIPE, STDOUT

import atexit
import chardet
import gc
import hashlib
import htmlentitydefs
import logging
import operator
import os
import pdb
import re
import simplejson
import socket
import sqlite3
import subprocess
import sys
import thread
import threading
import time
import urllib
import urllib2
import xmpp

global execute, prefix, comms, hashlib, trace

sema = threading.BoundedSemaphore(value=30)

class KThread(threading.Thread):
	def __init__(self, *args, **keywords):
		threading.Thread.__init__(self, *args, **keywords)
		self.killed = False

	def start(self):
		self.__run_backup = self.run
		self.run = self.__run
		threading.Thread.start(self)

	def __run(self):
		sys.settrace(self.globaltrace)
		self.__run_backup()
		self.run = self.__run_backup

	def globaltrace(self, frame, why, arg):
		if why == 'call': return self.localtrace
		else: return None

	def localtrace(self, frame, why, arg):
		if self.killed:
			if why == 'line': raise SystemExit()
		return self.localtrace

	def kill(self): self.killed = True

def thr(func,param,name):
	global th_cnt, thread_error_count
	th_cnt += 1
	try:
		if thread_type:
			with sema:
				tmp_th = KThread(group=None,target=log_execute,name=str(th_cnt)+'_'+name,args=(func,param))
				tmp_th.start()
		else: thread.start_new_thread(log_execute,(func,param))
	except Exception, SM:
		if str(SM).lower().count('thread'): thread_error_count += 1
		else: logging.exception(' ['+timeadd(tuple(localtime()))+'] '+str(proc))
		if thread_type:
			try: tmp_th.kill()
			except: pass

def log_execute(proc, params):
	try: proc(*params)
	except: logging.exception(' ['+timeadd(tuple(localtime()))+'] '+str(proc))

def send_count(item):
	global message_out, presence_out, iq_out, unknown_out
	cl.send(item)
	itm = unicode(item)[:2]
	if itm == '<m': message_out += 1
	elif itm == '<p': presence_out += 1
	elif itm == '<i': iq_out += 1
	else: unknown_out += 1

'''	
def sender(item):
	global last_stream
	if last_stream != []: last_stream.append(item)
	else:
		sleep(time_nolimit)
		send_count(item)
'''
def sender(item):
	sleep(time_nolimit)
	send_count(item)
	
def sender_stack():
	global last_stream
	last_item = {}
	while not game_over:
		if last_stream != []:
			time_tmp = time.time()
			tmp = last_stream[0]
			u_tmp = unicode(tmp)
			to_tmp = get_tag(u_tmp,'to')
			type_tmp = get_tag(u_tmp,'type')
			if type_tmp == 'groupchat':
				time_diff = time_tmp - last_item[to_tmp]
				last_item[to_tmp] == time_tmp
				if time_diff < time_limit: sleep(time_limit - time_diff)
				else: sleep(time_limit)
			else: sleep(time_nolimit)
			last_stream = last_stream[1:]
			send_count(tmp)
		else: sleep(1)

def readfile(filename):
	fp = file(filename)
	data = fp.read()
	fp.close()
	return data

def writefile(filename, data):
	fp = file(filename, 'w')
	fp.write(data)
	fp.close()

def getFile(filename,default):
	if os.path.isfile(filename):
		try: filebody = eval(readfile(filename))
		except:
			if os.path.isfile(filename+'.back'):
				while True:
					try:
						filebody = eval(readfile(filename+'.back'))
						break
					except: pass
			else:
				filebody = default
				writefile(filename,str(default))
	else:
		filebody = default
		writefile(filename,str(default))
	writefile(filename+'.back',str(filebody))
	return filebody

def get_subtag(body,tag):
	T = re.findall('%s.*?\"(.*?)\"' % tag,body,re.S)
	if T: return T[0]
	else: return ''

def get_tag(body,tag):
	T = re.findall('<%s.*?>(.*?)</%s>' % (tag,tag),body,re.S)
	if T: return T[0]
	else: return ''

def get_tag_full(body,tag):
	T = re.findall('(<%s.*?>.*?</%s>)' % (tag,tag),body,re.S)
	if T: return T[0]
	else:
		T = re.findall('(<%s.*?/>)' % tag,body,re.S)
		if T: return T[0]
		else: return ''

def get_tag_item(body,tag,item):
	body = get_tag_full(body,tag)
	return get_subtag(body,item)

def parser(text):
	text,ttext = unicode(text),''
	for tmp in text:
		if (tmp<='~'): ttext+=tmp
		else: ttext+='?'
	return ttext

def remove_sub_space(text):
	tx, es = '', '\t\r\n'
	for tmp in text:
		if ord(tmp) >= 32 or tmp in es : tx += tmp
		else: tx += '?'
	return tx

def smart_encode(text,enc):
	tx,splitter = '','|'
	while text.count(splitter): splitter += '|'
	ttext = text.replace('</','<'+splitter+'/').split(splitter)
	for tmp in ttext:
		try: tx += unicode(tmp,enc)
		except: pass
	return tx

def tZ(val):
	val = str(val)
	if len(val) == 1: val = '0'+val
	return val

def timeadd(lt): return '%s.%s.%s %s:%s:%s' % (tZ(lt[2]),tZ(lt[1]),tZ(lt[0]),tZ(lt[3]),tZ(lt[4]),tZ(lt[5]))

def onlytimeadd(lt): return '%s:%s:%s' % (tZ(lt[3]),tZ(lt[4]),tZ(lt[5]))

def pprint(text):
	lt = tuple(localtime())
	zz = parser('['+onlytimeadd(lt)+'] '+text)
	if dm2: print zz
	if CommandsLog:
		fname = slog_folder+tZ(lt[0])+tZ(lt[1])+tZ(lt[2])+'.txt'
		fname = '%s%s%s%s.txt' % (slog_folder,tZ(lt[0]),tZ(lt[1]),tZ(lt[2]))
		fbody = '%s|%s\n' % (onlytimeadd(lt),text)
		fl = open(fname, 'a')
		fl.write(fbody.encode('utf-8'))
		fl.close()

def send_presence_all(sm):
	pr=xmpp.Presence(typ='unavailable')
	pr.setStatus(sm)
	sender(pr)
	sleep(2)	

def errorHandler(text):
	pprint('\n*** Error ***')
	pprint(text)
	pprint('more info at http://isida-bot.com\n')
	sys.exit('exit')

def arr_semi_find(array, string):
	astring = [unicode(string.lower())]
	pos = 0
	for arr in array:
		if re.findall(string, arr.lower()) == astring: break
		pos += 1
	if pos != len(array): return pos
	else: return -1

def arr_del_by_pos(array, position):
	return array[:position] + array[position+1:]

def arr_del_semi_find(array, string):
	pos = arr_semi_find(array, string)
	if pos >= 0: array = arr_del_by_pos(array,pos)
	return array

def get_joke(text):
	from random import randint

	def joke_blond(text):
		b = ''
		cnt = randint(0,1)
		for tmp in text.lower():
			if cnt: b += tmp.upper()
			else: b += tmp
			cnt = not cnt
		return b
		
	def no_joke(text): return text

	jokes = [joke_blond,no_joke]
	return jokes[randint(0,1)](text)
	
def send_msg(mtype, mjid, mnick, mmessage):
	if len(mmessage):
		# 1st april joke :) # if time.localtime()[1:3] == (4,1): mmessage = get_joke(mmessage)
		no_send = True
		if len(mmessage) > msg_limit:
			cnt = 0
			maxcnt = len(mmessage)/msg_limit + 1
			mmsg = mmessage
			while len(mmsg) > msg_limit:
				tmsg = '['+str(cnt+1)+'/'+str(maxcnt)+'] '+mmsg[:msg_limit]+'[...]'
				cnt += 1
				sender(xmpp.Message(mjid+'/'+mnick, tmsg, 'chat'))
				mmsg = mmsg[msg_limit:]
				sleep(1)
			tmsg = '['+str(cnt+1)+'/'+str(maxcnt)+'] '+mmsg
			sender(xmpp.Message(mjid+'/'+mnick, tmsg, 'chat'))
			if mtype == 'chat': no_send = None
			else: mmessage = mmessage[:msg_limit] + '[...]'
		if no_send:
			if mtype == 'groupchat' and mnick != '': mmessage = mnick+': '+mmessage
			else: mjid += '/' + mnick
			while mmessage[-1:] == '\n' or mmessage[-1:] == '\t' or mmessage[-1:] == '\r' or mmessage[-1:] == ' ': mmessage = mmessage[:-1]
			if len(mmessage): sender(xmpp.Message(mjid, mmessage, mtype))

def os_version():
	iSys = sys.platform
	iOs = os.name
	isidaPyVer = sys.version.split(',')[0]+')'
	if iOs == 'posix':
		osInfo = os.uname()
		isidaOs = osInfo[0]+' ('+osInfo[2]+'-'+osInfo[4]+') / Python v'+isidaPyVer
	elif iSys == 'win32':
		def get_registry_value(key, subkey, value):
			import _winreg
			key = getattr(_winreg, key)
			handle = _winreg.OpenKey(key, subkey)
			(value, type) = _winreg.QueryValueEx(handle, value)
			return value
		def get(key):
			return get_registry_value("HKEY_LOCAL_MACHINE", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",key)
		osInfo = get("ProductName")
		buildInfo = get("CurrentBuildNumber")
		try:
			spInfo = get("CSDVersion")
			isidaOs = osInfo+' '+spInfo+' (Build: '+buildInfo+') / Python v'+isidaPyVer
		except: isidaOs = osInfo+' (Build: '+buildInfo+') / Python v'+isidaPyVer
	else: isidaOs = 'unknown'
	return isidaOs

def joinconf(conference, server):
	node = unicode(JID(conference.lower()).getResource())
	jid = JID(node=node, domain=server.lower(), resource=getResourse(Settings['jid']))
	if dm: cl = Client(jid.getDomain())
	else: cl = Client(jid.getDomain(), debug=[])
	conf = unicode(JID(conference))
	return join(conf)

def leaveconf(conference, server, sm):
	node = unicode(JID(conference).getResource())
	jid = JID(node=node, domain=server)
	if dm: cl = Client(jid.getDomain())
	else: cl = Client(jid.getDomain(), debug=[])
	conf = unicode(JID(conference))
	leave(conf, sm)
	sleep(0.1)

def join(conference):
	global pres_answer,cycles_used,cycles_unused
	id = get_id()
	j = Node('presence', {'id': id, 'to': conference}, payload = [Node('show', {},[Settings['status']]), \
																  Node('status', {},[Settings['message']]), \
																  Node('priority', {},[Settings['priority']])])
	j.setTag('x', namespace=NS_MUC).addChild('history', {'maxchars':'0', 'maxstanzas':'0'})
	j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
	sender(j)
	answered, Error, join_timeout = None, None, 3
	while not answered and join_timeout and not game_over:
		if is_start:
			cyc = cl.Process(1)
			if str(cyc) == 'None': cycles_unused += 1
			elif int(str(cyc)): cycles_used += 1
			else: cycles_unused += 1
		else:
			sleep(1)
			join_timeout -= 1
		for tmp in pres_answer:
			if tmp[0]==id:
				Error = tmp[1]
				pres_answer.remove(tmp)
				answered = True
				break
	return Error

def leave(conference, sm):
	j = Presence(conference, 'unavailable', status=sm)
	sender(j)

def timeZero(val):
	rval = []
	for iv in range(0,len(val)):
		if val[iv]<10: rval.append('0'+str(val[iv]))
		else: rval.append(str(val[iv]))
	return rval

def iqCB(sess,iq):
	global timeofset, banbase, raw_iq, iq_in, iq_request
	iq_in += 1
	id = iq.getID()
	if id == None: return None
	nick = unicode(iq.getFrom())
	query = iq.getTag('query')
	
	was_request = id in iq_request
	
	if iq.getType()=='error' and was_request:
		iq_err,er_name = get_tag(unicode(iq),'error'),L('Unknown error!')
		for tmp in iq_error.keys():
			if iq_err.count(tmp):
				er_name = '%s %s!' % (L('Error!'),iq_error[tmp])
				break
		iq_async(id,time.time(),er_name,'error')

	elif iq.getType()=='result' and was_request:
		cparse = unicode(iq)
		raw_iq = [id,cparse]
		is_vcard = iq.getTag('vCard')
		if is_vcard: iq_async(id,time.time(), unicode(is_vcard))
		else:
			try: nspace = query.getNamespace()
			except: nspace = 'None'
			if nspace == NS_MUC_ADMIN:
				cparse = cparse.split('<item')
				for banm in cparse[1:]:
					cjid = get_subtag(banm,'jid')
					if banm.count('<reason />') or banm.count('<reason/>'): creason = ''#L('No reason')
					else: creason=get_tag(banm,'reason')
					banbase.append((cjid, creason, id))
				banbase.append(('TheEnd','None',id))
			elif nspace == NS_MUC_OWNER: banbase.append(('TheEnd', 'None',id))
			elif nspace == NS_VERSION: iq_async(id,time.time(), iq.getTag('query').getTagData(tag='name'), iq.getTag('query').getTagData(tag='version'),iq.getTag('query').getTagData(tag='os'))
			elif nspace == NS_TIME: iq_async(id,time.time(), iq.getTag('query').getTagData(tag='display'),iq.getTag('query').getTagData(tag='utc'),iq.getTag('query').getTagData(tag='tz'))
			else: iq_async(id,time.time(), unicode(iq))

	elif iq.getType()=='get':
		if iq.getTag(name='query', namespace=xmpp.NS_VERSION):
			pprint('*** iq:version from '+unicode(nick))
			i=xmpp.Iq(to=nick, typ='result')
			i.setAttr(key='id', val=id)
			i.setQueryNS(namespace=xmpp.NS_VERSION)
			i.getTag('query').setTagData(tag='name', val=botName)
			i.getTag('query').setTagData(tag='version', val=botVersion)
			i.getTag('query').setTagData(tag='os', val=botOs)
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='query', namespace=xmpp.NS_TIME):
			pprint('*** iq:time from '+unicode(nick))
			gt=timeZero(gmtime())
			t_utc=gt[0]+gt[1]+gt[2]+'T'+gt[3]+':'+gt[4]+':'+gt[5]
			lt=tuple(localtime())
			ltt=timeZero(lt)
			wday = [L('Mon'),L('Tue'),L('Wed'),L('Thu'),L('Fri'),L('Sat'),L('Sun')]
			wlight = [L('Winter time'),L('Summer time')]
			wmonth = [L('Jan'),L('Fed'),L('Mar'),L('Apr'),L('May'),L('Jun'),L('Jul'),L('Aug'),L('Sep'),L('Oct'),L('Nov'),L('Dec')]
			t_display = ltt[3]+':'+ltt[4]+':'+ltt[5]+', '+ltt[2]+'.'+wmonth[lt[1]-1]+'\''+ltt[0]+', '+wday[lt[6]]+', '
			if timeofset < 0: t_tz = 'GMT'+str(timeofset)
			else: t_tz = 'GMT+'+str(timeofset)
			t_display += t_tz + ', ' +wlight[lt[8]]
			i=xmpp.Iq(to=nick, typ='result')
			i.setAttr(key='id', val=id)
			i.setQueryNS(namespace=xmpp.NS_TIME)
			i.getTag('query').setTagData(tag='utc', val=t_utc)
			i.getTag('query').setTagData(tag='tz', val=t_tz)
			i.getTag('query').setTagData(tag='display', val=t_display)
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='query', namespace=xmpp.NS_LAST):
			pprint('*** iq:uptime from '+unicode(nick))
			i=xmpp.Iq(to=nick, typ='result')
			i.setAttr(key='id', val=id)
			i.setTag('query',namespace=xmpp.NS_LAST,attrs={'seconds':str(int(time.time())-starttime)})
			sender(i)
			raise xmpp.NodeProcessed

# iq_request = {id:(time,func,())}
# func = (,is_answ)
# is_answ = time_lim,some[:]
#else: msg = L('Timeout %s sec.') % str(timeout)

def iq_async_clean():
	global iq_reques
	while not game_over:
		to = timeout
		while to > 0 and not game_over:
			to -= 1
			sleep(1)
		if len(iq_request):
			for tmp in iq_request.keys():
				if iq_request[tmp][0] + timeout < time.time(): iq_request.pop(tmp)
				break

def iq_async(*answ):
	global iq_request
	req = iq_request.pop(answ[0])
	try: er_code = answ[3]
	except: er_code = None
	if er_code == 'error':
		send_msg(req[2][0], req[2][1], req[2][2], answ[2])
		return
	is_answ = (answ[1]-req[0],answ[2:])
	req[2].append(is_answ)
	thr(req[1],(tuple(req[2])),'iq_async_%s' % answ[0])

def remove_ignore(jid,al):
	global ignorebase
	sleep(ddos_limit[al])
	ignorebase.remove(jid)

def com_parser(access_mode, nowname, type, room, nick, text, jid):
	global last_command, ignorebase
#	if type == 'chat':
	if last_command[1:7] == [nowname, type, room, nick, text, jid] and time.time() < last_command[7]+ddos_diff[access_mode]:
		jjid = getRoom(jid)
		ignorebase.append(jjid)
		pprint('!!! DDOS Detect: %s %s/%s %s %s' % (access_mode, room, nick, jid, text))
		thr(remove_ignore,(jjid,access_mode),'ddos_remove')
		send_msg(type, room, nick, L('Warning! Exceeded the limit of sending the same message. You are blocked for a period of %s sec.') % ddos_limit[access_mode])
		return None
	no_comm = True
	cof = getFile(conoff,[])
	for parse in comms:
		if access_mode >= parse[0] and nick != nowname:
			not_offed = True
			if access_mode != 2 or ignore_owner:
				for co in cof:
					if co[0]==room and co[1]==text.lower()[:len(co[1])]:
						not_offed = None
						break
			if not_offed and (text.lower() == parse[1].lower() or text[:len(parse[1])+1].lower() == parse[1].lower()+' '):
				pprint(jid+' '+room+'/'+nick+' ['+str(access_mode)+'] '+text)
				no_comm = None
				if not parse[3]: thr(parse[2],(type, room, nick, par),parse[1])
				elif parse[3] == 1: thr(parse[2],(type, room, nick),parse[1])
				elif parse[3] == 2: thr(parse[2],(type, room, nick, text[len(parse[1])+1:]),parse[1])
				last_command = [access_mode, nowname, type, room, nick, text, jid, time.time()]
				break
	return no_comm

def to_scrobble(room,mess):
	item = get_tag(unicode(mess),'item')
	if item.count('http://jabber.org/protocol/tune'):
		if item.count('<title'):
			played = True
			title = get_tag(item,'title')
			if item.count('<artist'):
				artist = get_tag(item,'artist')
				if len(artist) and artist != '?': title = artist + ' - ' + title
			caps_lit = 0
			for tmp in title:
				if re.match(u'[A-Z]|[А-Я]',tmp): caps_lit+=1
			if caps_lit >= len(title)/2:
				tm,tm1 = title.split(),[]
				for tmp in tm: tm1.append(tmp.capitalize())
				title = ' '.join(tm1)
			if title[:10].count('. '): title = title.split('. ',1)[1]
			length = get_tag(item,'length')
			try:
				if int(length) > 86400: length = 'stream'
			except: length = 'unknown'
			#print '%s - %s [%s]' % (room,title,length)
		else: played = None
		stb = os.path.isfile(scrobblebase)
		scrobbase = sqlite3.connect(scrobblebase)
		cu_scrobl = scrobbase.cursor()
		if not stb:
			cu_scrobl.execute('''create table tune (jid text, song text, length text, played integer)''')
			cu_scrobl.execute('''create table nick (jid text, nick text)''')
			scrobbase.commit()
		tune = cu_scrobl.execute('select * from tune where jid=? order by -played',(room,)).fetchone()
		if not tune: tune = ['','','',0]
		if played:
			if tune[1] != title or tune[2] != length:
				if title.count('] ') and title.count('['):
					if title.split('] ',1)[1] != tune[1]: scrb = None
					else: scrb = True
				else: scrb = True
			else: scrb = None
		else: scrb = True
		try: tlen = int(length)/2
		except: tlen = 30
		if scrb:
			if (time.time() - tune[3]) < tlen: cu_scrobl.execute('delete from tune where jid=? and song=? and length=? and played=?',tune).fetchall()
			if played: cu_scrobl.execute('insert into tune values (?,?,?,?)', (room, title, length, int(time.time())))
		scrobbase.commit()
		scrobbase.close()
	
def messageCB(sess,mess):
	global lfrom, lto, owners, ownerbase, confbase, confs, lastserver, lastnick, comms
	global ignorebase, ignores, message_in
	message_in += 1
	type=unicode(mess.getType())
	room=unicode(mess.getFrom().getStripped())
	if type == 'headline': to_scrobble(room,mess)
	text=unicode(mess.getBody())
	if text == 'None' or text == '': return
	if mess.getTimestamp() != None: return
	nick=mess.getFrom().getResource()
	if nick == None: nick = ''
	else: nick = unicode(nick)
	towh=unicode(mess.getTo().getStripped())
	lprefix = get_local_prefix(room)
	back_text = text
	rn = room+"/"+nick
	ft = text
	ta = get_access(room,nick)
	access_mode = ta[0]
	jid =ta[1]

	tmppos = arr_semi_find(confbase, room)
	if tmppos == -1: nowname = Settings['nickname']
	else:
		nowname = getResourse(confbase[tmppos])
		if nowname == '': nowname = Settings['nickname']
	if (jid == 'None' or jid[:4] == 'j2j.') and ownerbase.count(getRoom(room)): access_mode = 2
	if type == 'groupchat' and nick != '' and jid != 'None': talk_count(room,jid,nick,text)
	if nick != '' and nick != 'None' and nick != nowname and len(text)>1 and text != 'None' and text != to_censore(text) and access_mode >= 0:
		gl_censor = getFile(cns,[(getRoom(room),0)])
		if (getRoom(room),1) in gl_censor: send_msg(type,room,nick,L('Censored!'))
	no_comm = 1
	if (text != 'None') and (len(text)>=1) and access_mode >= 0 and not mess.getSubject():
		no_comm = 1
		is_par = 0
		if text[:len(nowname)] == nowname:
			text = text[len(nowname)+2:]
			is_par = 1
		btext = text
		if text[:len(lprefix)] == lprefix:
			text = text[len(lprefix):]
			is_par = 1
		if type == 'chat': is_par = 1
		if is_par: no_comm = com_parser(access_mode, nowname, type, room, nick, text, jid)
		if no_comm:
			for parse in aliases:
				if (btext.lower() == parse[1].lower() or btext[:len(parse[1])+1].lower() == parse[1].lower()+' ') and room == parse[0]:
					pprint(jid+' '+room+'/'+nick+' ['+str(access_mode)+'] '+text)
					argz = btext[len(parse[1])+1:]
					if not argz:
						ppr = parse[2].replace('%*', '')
						cpar = re.findall('%([0-9]+)', ppr, re.S)
						if len(cpar):
							for tmp in cpar:
								try: ppr = ppr.replace('%'+tmp,'')
								except: pass
					else:
						ppr = parse[2].replace('%*', argz)
						if ppr.count('%'):
							cpar = re.findall('%([0-9]+)', ppr, re.S)
							if len(cpar):
								argz = argz.split()
								for tmp in cpar:
									try: ppr = ppr.replace('%'+tmp,argz[int(tmp)])
									except: pass
					if len(ppr) == ppr.count(' '): ppr = ''
					no_comm = com_parser(access_mode, nowname, type, room, nick, ppr, jid)
					break

	if room != selfjid:
		floods = getFile(fld,[(getRoom(room),0)])
		is_flood = (getRoom(room),1) in floods
	else: is_flood = 0

	if selfjid != jid and no_comm and access_mode >= 0 and (ft[:len(nowname)+2] == nowname+': ' or ft[:len(nowname)+2] == nowname+', ' or type == 'chat') and is_flood:
		if len(text)>100: send_msg(type, room, nick, L('Too many letters!'))
		else:
			text = getAnswer(text,type)
			thr(send_msg_human,(type, room, nick, text),'msg_human')
	thr(msg_afterwork,(mess,room,jid,nick,type,back_text),'msg_afterwork')
			
def msg_afterwork(mess,room,jid,nick,type,back_text):
	for tmp in gmessage:
		subj=unicode(mess.getSubject())
		if subj != 'None' and back_text == 'None': tmp(room,jid,'',type,L('*** %s set topic: %s') % (nick,subj))
		else: tmp(room,jid,nick,type,back_text)

def send_msg_human(type, room, nick, text):
	if text: sleep(len(text)/4+randint(0,10))
	else: text = L('What?')
	send_msg(type, room, nick, text)

def getAnswer(tx,type):
	if not len(tx) or tx.count(' ') == len(tx): return None
	mdb = sqlite3.connect(answersbase)
	answers = mdb.cursor()
	la = len(answers.execute('select * from answer').fetchall())
	mrand = str(randint(1,la))
	answers.execute('select * from answer where ind=?', (mrand,))
	for aa in answers: anscom = aa[1]
	if type == 'groupchat':
		tx = to_censore(tx)
		answers.execute('insert into answer values (?,?)', (la+1,tx))
	mdb.commit()
	anscom = to_censore(anscom)
	return anscom

def to_censore(text):
	for c in censor:
		matcher = re.compile(r'.*'+c.lower()+r'.*')
		if matcher.match(r' '+text.lower()+r' '):
			text = '*censored*'
			break
	return text

def get_valid_tag(body,tag):
	if body.count(tag): return get_subtag(body,tag)
	else: return 'None'
	
def presenceCB(sess,mess):
	global megabase, ownerbase, pres_answer, confs, confbase, cu_age, presence_in
	presence_in += 1
	room=unicode(mess.getFrom().getStripped())
	nick=unicode(mess.getFrom().getResource())
	text=unicode(mess.getStatus())
	mss = unicode(mess)
#	caps = get_tag_full(mss,'c')
#	caps_node = get_subtag(caps,'node')
#	caps_ver = get_subtag(caps,'ver')
	if mss.strip().count('<x xmlns=\"http://jabber') > 1 and mss.strip().count(' affiliation=\"') > 1 and mss.strip().count(' role=\"') > 1 : bad_presence = True
	else: bad_presence = None
	while mss.count('<x ') > 1 and mss.count('</x>') > 1: mss = mss[:mss.find('<x ')]+mss[mss.find('</x>')+4:]
	mss = get_tag_full(mss,'x')
	role=get_valid_tag(mss,'role')
	affiliation=get_valid_tag(mss,'affiliation')
	jid=get_valid_tag(mss,'jid')
	priority=unicode(mess.getPriority())
	show=unicode(mess.getShow())
	reason=unicode(mess.getReason())
	type=unicode(mess.getType())
	status=unicode(mess.getStatusCode())
	actor=unicode(mess.getActor())
	to=unicode(mess.getTo())
	id = mess.getID()

	if type=='error':
		try: pres_answer.append((id,get_tag_item(unicode(mess),'error','code')+': '+mess.getTag('error').getTagData(tag='text')))
		except:
			try: 
				pres_answer.append((id,get_tag_item(unicode(mess),'error','code')+': '+mess.getTag('error')))
			except: pres_answer.append((id,L('Unknown error!')))
		return
	elif id != None: pres_answer.append((id,None))
	if jid == 'None': jid = get_access(room,nick)[1]
	if bad_presence: send_msg('groupchat', room, '', L('/me detect bad stanza from %s') % nick)
	al = get_access(room,nick)[0]
	if type == 'subscribe' and al == 2: 
		j = Presence(room, 'subscribed')
		j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		sender(j)
		j = Presence(room, 'subscribe')
		j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		sender(j)
		pprint('Subscribe %s' % room)
	elif type == 'unsubscribed' and al == 2: 
		j = Presence(room, 'unsubscribe')
		j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		sender(j)
		j = Presence(room, 'unsubscribed')
		j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		sender(j)
		pprint('Unsubscribe %s' % room)
	
	tmppos = arr_semi_find(confbase, room.lower())
	if tmppos == -1: nowname = Settings['nickname']
	else:
		nowname = getResourse(confbase[tmppos])
		if nowname == '': nowname = Settings['nickname']

	if room != selfjid and nick == nowname:
		smiles = getFile(sml,[(getRoom(room),0)])
		if (getRoom(room),1) in smiles:
			smile_action = {'participantnone':' :-|', 'participantmember':' :-)', 'moderatormember':' :-"','moderatoradmin':' :-D', 'moderatorowner':' 8-D'}
			try: send_msg('groupchat', room, '', smile_action[role+affiliation])
			except: pass
	
	if ownerbase.count(getRoom(room)) and type != 'unavailable':
		j = Presence(room, show=Settings['status'], status=Settings['message'], priority=Settings['priority'])
		j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		sender(j)

	not_found = 0

	if type=='unavailable' and nick != '':
		for mmb in megabase:
			if mmb[0]==room and mmb[1]==nick: megabase.remove(mmb)
		if to == selfjid and (status=='307' or status=='301') and confbase.count(room+'/'+nick):
			if os.path.isfile(confs):
				confbase = eval(readfile(confs))
				confbase = arr_del_semi_find(confbase,getRoom(room))
				writefile(confs,str(confbase))
	elif nick != '':
		for mmb in megabase:
			if mmb[0]==room and mmb[1]==nick:
				megabase.remove(mmb)
				megabase.append([room, nick, role, affiliation, jid])
				if role != mmb[2] or affiliation != mmb[3]: not_found = 1
				else: not_found = 2
		if not not_found: megabase.append([room, nick, role, affiliation, jid])
	if jid == 'None': jid, jid2 = '<temporary>'+nick, 'None'
	else: jid2, jid = jid, getRoom(jid.lower())
	mdb = sqlite3.connect(agestatbase)
	cu = mdb.cursor()
	ab = cu.execute('select * from age where room=? and jid=? and nick=?',(room, jid, nick)).fetchone()
	tt = int(time.time())
	ttext = role + '\n' + affiliation + '\n' + priority + '\n' + show  + '\n' + text
	exit_type = ''
	exit_message = ''
	if ab:
		if type=='unavailable':
			if status=='307': exit_type,exit_message = L('Kicked'),reason
			elif status=='301': exit_type,exit_message = L('Banned'),reason
			else: exit_type,exit_message = L('Leave'),text
			if exit_message == 'None': exit_message = ''
			cu.execute('update age set time=?, age=?, status=?, type=?, message=? where room=? and jid=? and nick=?', (tt,ab[4]+(tt-ab[3]),1,exit_type,exit_message,room, jid, nick))
		else:
			if ab[5]: cu.execute('update age set time=?, status=?, message=? where room=? and jid=? and nick=?', (tt,0,ttext,room, jid, nick))
			else: cu.execute('update age set status=?, message=? where room=? and jid=? and nick=?', (0,ttext,room, jid, nick))
	else: cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (room,nick,jid,tt,0,0,'',ttext))
	mdb.commit()
	for tmp in gpresence: thr(tmp,(room,jid2,nick,type,(text, role, affiliation, exit_type, exit_message, show, priority, not_found)),'presence_afterwork')
	
def onoff(msg):
	if msg: return L('on').upper()
	return L('off').upper()

def getName(jid):
	jid = unicode(jid)
	if jid == 'None': return jid
	return jid[:jid.find('@')].lower()

def getServer(jid):
	jid = unicode(jid)
	if not jid.count('/'): jid += '/'
	if jid == 'None': return jid
	return jid[jid.find('@')+1:jid.find('/')].lower()

def getResourse(jid):
	jid = unicode(jid)
	if jid == 'None': return jid
	return jid[jid.find('/')+1:]

def getRoom(jid):
	jid = unicode(jid)
	if jid == 'None': return jid
	return getName(jid)+'@'+getServer(jid)

def now_schedule():
	while not game_over:
		to = schedule_time	
		while to > 0 and not game_over:
			to -= 1
			sleep(1)
		if not game_over:
			for tmp in gtimer: log_execute(tmp,())

def check_rss():
	l_hl = int(time.time())
	feedbase = getFile(feeds,[])
	for fd in feedbase:
		ltime = fd[1]
		timetype = ltime[-1:].lower()
		if not timetype in ('h','m'): timetype = 'h'
		try: ofset = int(ltime[:-1])
		except: ofset = 4
		if timetype == 'h': ofset *= 3600
		elif timetype == 'm': ofset *= 60
		try: ll_hl = int(fd[3])
		except: ll_hl = 0
		in_room = None
		for tmp in confbase:
			if getRoom(tmp) == fd[4]:
				in_room = True
				break
		if ofset < 600: ofset = 600
		if in_room and ll_hl + ofset <= l_hl:
			pprint('check rss: '+fd[0]+' in '+fd[4])
			rss('groupchat', fd[4], 'RSS', 'new %s 10 %s silent' % (fd[0],fd[2]))
			break

def talk_count(room,jid,nick,text):
	jid = getRoom(jid)
	mdb = sqlite3.connect(talkersbase)
	cu = mdb.cursor()
	ab = cu.execute('select * from talkers where room=? and jid=?',(room,jid)).fetchone()
	wtext = len(text.split(' '))
	if ab: cu.execute('update talkers set nick=?, words=?, frases=? where room=? and jid=?', (nick,ab[3]+wtext,ab[4]+1,room,jid))
	else: cu.execute('insert into talkers values (?,?,?,?,?)', (room, jid, nick, wtext, 1))
	mdb.commit()

def flush_stats():
	pprint('Executed threads: %s | Error(s): %s' % (th_cnt,thread_error_count))
	pprint('Message in %s | out %s' % (message_in,message_out))
	pprint('Presence in %s | out %s' % (presence_in,presence_out))
	pprint('Iq in %s | out %s' % (iq_in,iq_out))
	pprint('Unknown out %s' % unknown_out)
	pprint('Cycles used %s | unused %s' % (cycles_used,cycles_unused))
	
def disconnecter():
	global bot_exit_type, game_over
	pprint('--- Restart by disconnect handler! ---')
	game_over, bot_exit_type = True, 'restart'
	sleep(2)

def L(text):
	if not len(text): return text
	try: return locales[text]
	except: return text

def kill_all_threads():
	if thread_type:
		for tmp in threading.enumerate():
			try: tmp.kill()
			except: pass
			
def get_id():
	global id_count
	id_count += 1
	return 'request_%s' % id_count

# --------------------- Иницилизация переменных ----------------------
slog_folder = 'log/'					# папка логов
set_folder 	= 'settings/'				# папка настроек
back_folder = 'backup/'					# папка хранения резервных копий
loc_folder 	= 'locales/'				# папка локализаций
LOG_FILENAME = slog_folder+'error.txt'	# логи ошибок
preffile = set_folder+'prefix'			# префиксы
ver_file = set_folder+'version'			# версия бота
configname = set_folder+'config.py'		# конфиг бота
alfile = set_folder+'aliases'			# сокращения
fld = set_folder+'flood'				# автоответчик
sml = set_folder+'smile'				# смайлы на роли
cns = set_folder+'censors'				# состояние цензора
owners = set_folder+'owner'				# база владельцев
ignores = set_folder+'ignore'			# черный список
confs = set_folder+'conf'				# список активных конф
feeds = set_folder+'feed'				# список rss каналов + md5 последниx новостей по каждому каналу
cens = set_folder+'censor.txt'			# список "запрещенных" слов для болтуна
conoff = set_folder+'commonoff'			# список "запрещенных" команд для бота
saytobase = set_folder+'sayto.db'		# база команды "передать"
agestatbase = set_folder+'agestat.db'	# статистика возрастов
talkersbase = set_folder+'talkers.db'	# статистика болтунов
wtfbase = set_folder+'wtfbase2.db'		# определения
answersbase = set_folder+'answers.db'	# ответы бота
scrobblebase = set_folder+'scrobble.db'	# база PEP скробблера
loc_file = set_folder+'locale'			# файл локализации

nmbrs = ['0','1','2','3','4','5','6','7','8','9','.']
ul = 'update.log'				# лог последнего обновление
debugmode = None				# остановка на ошибках
dm = None						# отладка xmpppy
dm2 = None						# отладка действий бота
CommandsLog = None				# логгирование команд
prefix = '_'					# префикс комманд
msg_limit = 1000				# лимит размера сообщений
botName = 'Isida-Bot'			# название бота
botVersion = 'v2.00'			# версия бота
capsVersion = botVersion[1:]	# версия для капса
banbase = []					# результаты muc запросов
pres_answer = []				# результаты посылки презенсов
iq_request = {}					# iq запросы
th_cnt = 0						# счётчик тредов
timeout = 600					# таймаут в секундах на iq запросы
schedule_time = 10				# время проверки расписания
thread_error_count = 0			# счётчик ошибок тредов
reboot_time = 180				# таймаут рестарта бота при ошибке не стадии подключения (нет инета, ошибка авторизации)
bot_exit_type = None			# причина завершения бота
last_stream = []				# очередь станз к отправке
last_command = []				# последняя исполненная ботом команда
ddos_limit = [600,300,0]		# время игнора при ddos'е в зависимости от уровня доступа
ddos_diff = [15,10,0]			# промежуток между сообщениями
thread_type = True				# тип тредов
time_limit = 1.2				# максимальная задержка между посылкой станз с одинаковым типом в groupchat
time_nolimit = 0.05				# задержка между посылкой станз с разными типами
message_in,message_out = 0,0	# статистика сообщений
iq_in,iq_out = 0,0				# статистика iq запросов
presence_in,presence_out = 0,0	# статистика презенсов
unknown_out = 0					# статистика ошибочных отправок
cycles_used,cycles_unused = 0,0	# статистика циклов
id_count = 0					# номер запроса
megabase = []					# главная временная база с полной информацией из презенсов
ignore_owner = None				# исполнять отключенные команды для владельца бота

logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG,)	# включение логгирования

gt=gmtime()
lt=tuple(localtime())
if lt[0:3] == gt[0:3]: timeofset = int(lt[3])-int(gt[3])
elif lt[0:3] > gt[0:3]: timeofset = int(lt[3])-int(gt[3]) + 24
else: timeofset = int(gt[3])-int(lt[3]) + 24

if os.path.isfile(ver_file):
	bvers = str(readfile(ver_file))
	if len(bvers[:-1]) > 1: botVersion +='.'+bvers[:-1]
botOs = os_version()

if os.path.isfile(configname): execfile(configname)
else: errorHandler(configname+' is missed.')
capsNode = 'http://isida-bot.com'
god = SuperAdmin
pprint('-'*50)
pprint('*** Loading localization')

locales = {}
if os.path.isfile(loc_file):
	lf = loc_folder+getFile(loc_file,'\'en\'')+'.txt'
	if os.path.isfile(lf):
		lf = readfile(lf).decode('UTF').replace('\r','').split('\n')
		for c in lf:
			if (not c.count('#')) and len(c) and c.count('\t'): locales[c.split('\t',1)[0].replace('\\n','\n').replace('\\t','\t')] = c.split('\t',1)[1].replace('\\n','\n').replace('\\t','\t')
pprint('*** Loading main plugin')

execfile('plugins/main.py')
plname 		= 'plugins/list.txt'
pliname 	= 'plugins/ignored.txt'
gtimer 		= [check_rss]
gpresence 	= []
gmessage 	= []

pprint('*** Loading other plugins')

plugins   = getFile(plname,[])
pl_ignore = getFile(pliname,[])
	
for pl in plugins:
	if pl in pl_ignore: pprint('Ignore plugin: %s' % pl)
	else:
		presence_control = []
		message_control = []
		iq_control = []
		timer = []
		pprint('Append plugin: %s' % pl)
		execfile('plugins/'+pl)
		for cm in execute: comms.append((cm[0],cm[1],cm[2],cm[3],L('Plugin %s. %s') % (pl[:-3],cm[4])))
		for tmr in timer: gtimer.append(tmr)
		for tmp in presence_control: gpresence.append(tmp)
		for tmp in message_control: gmessage.append(tmp) 

aliases = getFile(alfile,[])

if os.path.isfile('settings/starttime'):
	try: starttime = eval(readfile('settings/starttime'))
	except: starttime = readfile('settings/starttime')
else: starttime = int(time.time())
sesstime = int(time.time())
ownerbase = getFile(owners,[god])
ignorebase = getFile(ignores,[])
cu_age = []
close_age_null()
confbase = getFile(confs,[defaultConf.lower()+'/'+Settings['nickname']])
if os.path.isfile(cens):
	censor = readfile(cens).decode('UTF').split('\n')
	cn = []
	for c in censor:
		if (not c.count('#')) and len(c): cn.append(c)
	censor = cn
else: censor = []

pprint('*'*50)
pprint('*** Bot Name: '+botName)
pprint('*** Version '+botVersion)
pprint('*** OS '+botOs)
pprint('*'*50)
pprint('*** (c) 2oo9-2o1o Disabler Production Lab.')

lastnick = Settings['nickname']
jid = JID(Settings['jid'])
selfjid = jid
pprint('bot jid: '+unicode(jid))
raw_iq = []

try:
	if dm: cl = Client(jid.getDomain())
	else: cl = Client(jid.getDomain(), debug=[])
	cl.connect()
	pprint('Connected')
	cl.auth(jid.getNode(), Settings['password'], jid.getResource())
	pprint('Autheticated')
except:
	pprint('Auth error or no connection. Restart in %s sec.' % reboot_time)
	sleep(reboot_time)
	sys.exit('restart')
pprint('Registration Handlers')
cl.RegisterHandler('message',messageCB)
cl.RegisterHandler('iq',iqCB)
cl.RegisterHandler('presence',presenceCB)
cl.RegisterDisconnectHandler(disconnecter)
cl.UnregisterDisconnectHandler(cl.DisconnectHandler)
cl.sendInitPresence()

pprint('Wait conference')
sleep(0.5)
game_over = None
#thr(sender_stack,(),'sender')
cb = []
is_start = True
lastserver = getServer(confbase[0].lower())
for tocon in confbase:
	baseArg = unicode(tocon)
	if not tocon.count('/'): baseArg += '/'+unicode(Settings['nickname'])
	conf = JID(baseArg)
	zz = joinconf(tocon, getServer(Settings['jid']))
	while unicode(zz)[:3] == '409':
		sleep(1)
		tocon += '_'
		zz = joinconf(tocon, getServer(Settings['jid']))
	cb.append(tocon)
	pprint('--> %s' % tocon)
confbase = cb
is_start = None
pprint('Joined')

#pep = xmpp.Message(to=selfjid, frm=getRoom(selfjid), payload=[xmpp.Node('event',{'xmlns':'http://jabber.org/protocol/pubsub#event'},[xmpp.Node('items',{'node':'http://jabber.org/protocol/tune'},[xmpp.Node('item',{'id':'current'},[xmpp.Node('tune',{'xmlns':'http://jabber.org/protocol/tune'},[])])])])])
#sender(pep)

thr(now_schedule,(),'schedule')
thr(iq_async_clean,(),'async_clean')

while 1:
	try:
		while not game_over:
			cyc = cl.Process(1)
			if str(cyc) == 'None': cycles_unused += 1
			elif int(str(cyc)): cycles_used += 1
			else: cycles_unused += 1
		close_age()
		kill_all_threads()
		flush_stats()
		sys.exit(bot_exit_type)

	except KeyboardInterrupt:
		close_age()
		StatusMessage = L('Shutdown by CTRL+C...')
		pprint(StatusMessage)
		send_presence_all(StatusMessage)
		sleep(0.1)
		kill_all_threads()
		flush_stats()
		sys.exit('exit')

	except Exception, SM:
		pprint('*** Error *** '+str(SM)+' ***')
		logging.exception(' ['+timeadd(tuple(localtime()))+'] ')
		if str(SM).lower().count('parsing finished'):
			close_age()
			kill_all_threads()
			flush_stats()
			sleep(300)
			sys.exit('restart')
		if debugmode: raise

# The end is near!
