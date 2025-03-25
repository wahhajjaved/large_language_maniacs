#!/usr/bin/python
# -*- coding: utf-8 -*-
# --------------------------------------------------------------------
#
#                             Isida Jabber Bot
#                               version 2.30
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
import calendar
import chardet
import datetime
import gc
import hashlib
import htmlentitydefs
import httplib
import logging
import operator
import os
import pdb
import random
import re
import simplejson
import socket
import sqlite3
import subprocess
import string
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
				tmp_th = KThread(group=None,target=log_execute,name='%s_%s' % (str(th_cnt),name),args=(func,param))
				tmp_th.start()
		else: thread.start_new_thread(log_execute,(func,param))
	except SystemExit: pass
	except Exception, SM:
		try: SM = str(SM)
		except: SM = unicode(SM)
		if SM.lower().count('thread'): thread_error_count += 1
		else: logging.exception(' [%s] %s' % (timeadd(tuple(localtime())),unicode(proc)))
		if thread_type:
			try: tmp_th.kill()
			except: pass

def log_execute(proc, params):
	try: proc(*params)
	except SystemExit: pass
	except: logging.exception(' [%s] %s' % (timeadd(tuple(localtime())),unicode(proc)))

def send_count(item):
	global message_out, presence_out, iq_out, unknown_out, last_stanza
	last_stanza = unicode(item)
	if last_stanza[:2] == '<m': message_out += 1
	elif last_stanza[:2] == '<p': presence_out += 1
	elif last_stanza[:2] == '<i': iq_out += 1
	else: unknown_out += 1
	cl.send(item)

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

def get_config(room,item):
	setup = getFile(c_file,{})
	try: return setup[room][item]
	except:
		try: return config_prefs[item][3]
		except: return None

def put_config(room,item,value):
	setup = getFile(c_file,{})
	try: t = setup[room]
	except: setup[room] = {}
	setup[room][item] = value
	writefile(c_file,str(setup))

def GT(item):
	setup = getFile(ow_file,{})
	try: gt_result = setup[item]
	except:
		try: gt_result = owner_prefs[item][2]
		except: gt_result = None
	try: return eval(gt_result)
	except: return gt_result

def PT(item,value):
	setup = getFile(ow_file,{})
	setup[item] = value
	writefile(ow_file,str(setup))

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
	ttext = text.replace('</','<%s/' % splitter).split(splitter)
	for tmp in ttext:
		try: tx += unicode(tmp,enc)
		except: pass
	return tx

def tZ(val): return ['%s','0%s'][val<10] % val

def timeadd(lt): return '%s.%s.%s %s:%s:%s' % (tZ(lt[2]),tZ(lt[1]),tZ(lt[0]),tZ(lt[3]),tZ(lt[4]),tZ(lt[5]))

def onlytimeadd(lt): return '%s:%s:%s' % (tZ(lt[3]),tZ(lt[4]),tZ(lt[5]))

def pprint(text):
	lt = tuple(localtime())
	zz = parser('[%s] %s' % (onlytimeadd(lt),text))
	if dm2: print zz
	if CommandsLog:
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
	pos = 0
	for arr in array:
		if string.lower() in arr.lower(): break
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
	global between_msg_last,time_limit
	if mmessage:
		while True:
			try: lm = between_msg_last[mjid]
			except: between_msg_last[mjid],lm = 0,0
			tt = time.time()
			if lm and tt-lm < time_limit: sleep(tt-lm)
			if between_msg_last[mjid]+time_limit <= time.time(): break
		between_msg_last[mjid] = time.time()
		# 1st april joke :)
		# if time.localtime()[1:3] == (4,1): mmessage = get_joke(mmessage)
		no_send = True
		if len(mmessage) > msg_limit:
			cnt = 0
			maxcnt = int(len(mmessage)/msg_limit) + 1
			mmsg = mmessage
			while len(mmsg) > msg_limit:
				tmsg = u'[%s/%s] %s[…]' % (cnt+1,maxcnt,mmsg[:msg_limit])
				cnt += 1
				sender(xmpp.Message('%s/%s' % (mjid,mnick), tmsg, 'chat'))
				mmsg = mmsg[msg_limit:]
				sleep(1)
			tmsg = '[%s/%s] %s' % (cnt+1,maxcnt,mmsg)
			sender(xmpp.Message('%s/%s' % (mjid,mnick), tmsg, 'chat'))
			if mtype == 'chat': no_send = None
			else: mmessage = mmessage[:msg_limit] + u'[…]'
		if no_send:
			if mtype == 'groupchat' and mnick != '': mmessage = '%s: %s' % (mnick,mmessage)
			else: mjid += '/' + mnick
			while mmessage[-1:] in ['\n','\t','\r',' ']: mmessage = mmessage[:-1]
			if len(mmessage): sender(xmpp.Message(mjid, mmessage, mtype))

def os_version():
	iSys = sys.platform
	iOs = os.name
	isidaPyVer = sys.version.split(',')[0]+')'
	if iOs == 'posix':
		osInfo = os.uname()
		isidaOs = '%s (%s-%s) / Python v%s' % (osInfo[0],osInfo[2],osInfo[4],isidaPyVer)
	elif iSys == 'win32':
		def get_registry_value(key, subkey, value):
			import _winreg
			key = getattr(_winreg, key)
			handle = _winreg.OpenKey(key, subkey)
			(value, type) = _winreg.QueryValueEx(handle, value)
			return value
		def get(key): return get_registry_value("HKEY_LOCAL_MACHINE", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",key)
		osInfo = get("ProductName")
		buildInfo = get("CurrentBuildNumber")
		try:
			spInfo = get("CSDVersion")
			isidaOs = '%s %s (Build: %s) / Python v%s' % (osInfo,spInfo,buildInfo,isidaPyVer)
		except: isidaOs = '%s (Build: %s) / Python v%s' % (osInfo,buildInfo,isidaPyVer)
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

def caps_and_send(tmp):
	tmp.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
	sender(tmp)

def join(conference):
	global pres_answer,cycles_used,cycles_unused
	id = get_id()
	j = Node('presence', {'id': id, 'to': conference}, payload = [Node('show', {},[Settings['status']]), \
																  Node('status', {},[Settings['message']]), \
																  Node('priority', {},[Settings['priority']])])
	j.setTag('x', namespace=NS_MUC).addChild('history', {'maxchars':'0', 'maxstanzas':'0'})
	caps_and_send(j)
	answered, Error, join_timeout = None, None, 3
	if is_start: join_timeout_delay = 0.3
	else: join_timeout_delay = 1
	while not answered and join_timeout >= 0 and not game_over:
		if is_start:
			cyc = cl.Process(1)
			if str(cyc) == 'None': cycles_unused += 1
			elif int(str(cyc)): cycles_used += 1
			else: cycles_unused += 1
		else: sleep(join_timeout_delay)
		join_timeout -= join_timeout_delay
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
		if val[iv]<10: rval.append('0%s' % val[iv])
		else: rval.append(str(val[iv]))
	return rval

def muc_filter_action(act,jid,room,reason):
	if act=='visitor':	sender(Node('iq',{'id': get_id(), 'type': 'set', 'to':room},payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'role':'visitor', 'jid':jid},[Node('reason',{},reason)])])]))
	elif act=='kick':	sender(Node('iq',{'id': get_id(), 'type': 'set', 'to':room},payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'role':'none', 'jid':jid},[Node('reason',{},reason)])])]))
	elif act=='ban':	sender(Node('iq',{'id': get_id(), 'type': 'set', 'to':room},payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'outcast', 'jid':jid},[Node('reason',{},reason)])])]))
	return None

def paste_text(text,room,jid):
	nick = get_nick_by_jid_res(room,jid)
	if GT('html_paste_enable'): text = html_escape(text)
	paste_header = ['','<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru"><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8" /><link href="%s" rel="stylesheet" type="text/css" /><title>\n' % paste_css_path][GT('html_paste_enable')]
	url = '%s%s' % (str(hex(int(time.time()*100)))[2:-1],['.txt','.html'][GT('html_paste_enable')])
	lt = tuple(time.localtime())
	ott = onlytimeadd(tuple(localtime()))
	paste_body = ['%s','<p><span class="text">%s</span></p>\n'][GT('html_paste_enable')] % (text)
	lht = '%s [%s] - %s/%s/%s %s:%s:%s' % (nick,room,lt[0],lt[1],lt[2],lt[3],tZ(lt[4]),tZ(lt[5]))
	paste_he = ['%s\t\thttp://isida-bot.com\n\n' % lht,'%s%s</title></head><body><div class="main"><div class="top"><div class="heart"><a href="http://isida-bot.com">http://isida-bot.com</a></div><div class="conference">%s</div></div><div class="container">\n' % (paste_header,lht,lht)][GT('html_paste_enable')]
	fl = open(pastepath+url, 'a')
	fl.write(paste_he.encode('utf-8'))
	fl.write(paste_body.encode('utf-8'))
	paste_ender = ['','</div></div></body></html>'][GT('html_paste_enable')]
	fl.write(paste_ender.encode('utf-8'))
	fl.close()
	return pasteurl+url

def nice_time(ttim):
	gt=gmtime()
	lt=tuple(localtime(ttim))
	if lt[0:3] == gt[0:3]: timeofset = int(lt[3])-int(gt[3])
	elif lt[0:3] > gt[0:3]: timeofset = int(lt[3])-int(gt[3]) + 24
	else: timeofset = int(gt[3])-int(lt[3]) + 24
	gt=timeZero(gmtime())
	t_utc='%s%s%sT%s:%s:%s' % (gt[0],gt[1],gt[2],gt[3],gt[4],gt[5])
	ltt=timeZero(lt)
	t_display = '%s:%s:%s, %s.%s\'%s, %s, ' % (ltt[3],ltt[4],ltt[5],ltt[2],wmonth[lt[1]-1],ltt[0],wday[lt[6]])
	if timeofset < 0: t_tz = 'GMT%s' % timeofset
	else: t_tz = 'GMT+%s' % timeofset
	t_display += '%s, %s' % (t_tz,wlight[lt[8]])
	return t_utc,t_tz,t_display

def iqCB(sess,iq):
	global timeofset, banbase, raw_iq, iq_in, iq_request, last_msg_base, last_msg_time_base
	iq_in += 1
	id = iq.getID()
	if id == None: return None
	room = unicode(iq.getFrom())
	if ownerbase.count(getRoom(room)): towh = selfjid
	else: towh = '%s/%s' % (getRoom(room),get_nick_by_jid_res(getRoom(room), selfjid))
	query = iq.getTag('query')
	was_request = id in iq_request
	acclvl = get_level(getRoom(room),getResourse(room))[0] >= 7 and GT('iq_disco_enable')
	nnj = False
	if room == selfjid: nnj = True
	else:
		for tmp in megabase:
			if '%s/%s' % tuple(tmp[0:2]) == room:
				nnj = True
				break

	if iq.getType()=='error' and was_request:
		iq_err,er_name = get_tag(unicode(iq),'error'),L('Unknown error!')
		try: JJ = JUICK_JID
		except: JJ = None
		if room == JJ: iq_async(id,time.time(), unicode(iq))
		else:
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
			elif iq.getTag('time',namespace=xmpp.NS_URN_TIME): iq_async(id,time.time(), iq.getTag('time').getTagData(tag='utc'),iq.getTag('time').getTagData(tag='tzo'))
			elif iq.getTag('ping',namespace=xmpp.NS_URN_PING): iq_async(id,time.time())
			else: iq_async(id,time.time(), unicode(iq))

	elif iq.getType()=='get' and nnj:
		
		if iq.getTag(name='query', namespace=xmpp.NS_VERSION) and GT('iq_version_enable'):
			pprint('*** iq:version from %s' % unicode(room))
			i=xmpp.Iq(to=room, typ='result')
			i.setAttr(key='id', val=id)
			i.setQueryNS(namespace=xmpp.NS_VERSION)
			i.getTag('query').setTagData(tag='name', val=botName)
			i.getTag('query').setTagData(tag='version', val=botVersion)
			i.getTag('query').setTagData(tag='os', val=botOs)
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='query', namespace=xmpp.NS_TIME) and GT('iq_time_enable'):
			pprint('*** iq:time from %s' % unicode(room))
			t_utc,t_tz,t_display = nice_time(time.time())
			i=xmpp.Iq(to=room, typ='result')
			i.setAttr(key='id', val=id)
			i.setQueryNS(namespace=xmpp.NS_TIME)
			i.getTag('query').setTagData(tag='utc', val=t_utc)
			i.getTag('query').setTagData(tag='tz', val=t_tz)
			i.getTag('query').setTagData(tag='display', val=t_display)
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='time', namespace=xmpp.NS_URN_TIME) and GT('iq_time_enable'):
			pprint('*** iq:urn:time from %s' % unicode(room))
			if timeofset in [-12,-11,-10]: t_tz = '-%s:00' % timeofset
			elif timeofset in range(-9,-1): t_tz = '-0%s:00' % timeofset
			elif timeofset in range(0,9): t_tz = '+0%s:00' % timeofset
			else: t_tz = '+%s:00' % timeofset
			i=xmpp.Iq(to=room, typ='result')
			i.setAttr(key='id', val=id)
			i.setTag('time',namespace=xmpp.NS_URN_TIME)
			i.getTag('time').setTagData(tag='tzo', val=t_tz)
			i.getTag('time').setTagData(tag='utc', val=str(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='ping', namespace=xmpp.NS_URN_PING) and GT('iq_ping_enable'):
			pprint('*** iq:urn:ping from %s' % unicode(room))
			i=xmpp.Iq(to=room, typ='result')
			i.setAttr(key='id', val=id)
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='query', namespace=xmpp.NS_LAST) and GT('iq_uptime_enable'):
			pprint('*** iq:uptime from %s' % unicode(room))
			i=xmpp.Iq(to=room, typ='result')
			i.setAttr(key='id', val=id)
			i.setTag('query',namespace=xmpp.NS_LAST,attrs={'seconds':str(int(time.time())-starttime)})
			sender(i)
			raise xmpp.NodeProcessed

		elif iq.getTag(name='query', namespace=xmpp.NS_DISCO_INFO):
			node=get_tag_item(unicode(query),'query','node')
			if node.split('#')[0] in ['', disco_config_node, xmpp.NS_COMMANDS]:
				pprint('*** iq:disco_info from %s node "%s"' % (unicode(room),node))
				i=xmpp.Iq(to=room, typ='result')
				i.setAttr(key='id', val=id)
				if node == '': i.setQueryNS(namespace=xmpp.NS_DISCO_INFO)
				else: i.setTag('query',namespace=xmpp.NS_DISCO_INFO,attrs={'node':node})
				i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_DISCO_INFO})
				i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_DISCO_ITEMS})
				i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_COMMANDS})
				i.getTag('query').setTag('feature',attrs={'var':disco_config_node})
				if node == '':
					i.getTag('query').setTag('identity',attrs={'category':'client','type':'bot','name':'iSida Jabber Bot'})
					sender(i)
					raise xmpp.NodeProcessed

				elif node.split('#')[0] == disco_config_node or node == xmpp.NS_COMMANDS:
					i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_COMMANDS})
					i.getTag('query').setTag('feature',attrs={'var':disco_config_node})
					try: tn = '#' + node.split('#')[1]
					except: tn = ''
					if tn:
						if tn.split('-',1)[0] == '#owner': settz = owner_groups
						elif tn.split('-',1)[0] == '#room': settz = config_groups
						else: settz = None
						if settz:
							for tmp in settz:
								if tn == tmp[1]:
									i.getTag('query').setTag('identity',attrs={'category':'automation','type':'command-node','name':tmp[0]})
									break
					sender(i)
					raise xmpp.NodeProcessed

		elif iq.getTag(name='query', namespace=xmpp.NS_DISCO_ITEMS) and acclvl:
			node=get_tag_item(unicode(query),'query','node')
			pprint('*** iq:disco_items from %s node "%s"' % (unicode(room),node))
			if node.split('#')[0] in ['', disco_config_node, xmpp.NS_COMMANDS]:
				try: tn = '#' + node.split('#')[1]
				except: tn = ''
				i=xmpp.Iq(to=room, typ='result')
				i.setAttr(key='id', val=id)
				if node == '': i.setQueryNS(namespace=xmpp.NS_DISCO_ITEMS)
				else: i.setTag('query',namespace=xmpp.NS_DISCO_ITEMS,attrs={'node':node})
				if node == '' or node == xmpp.NS_COMMANDS:
					if towh == selfjid: settings_set = owner_groups
					else: settings_set = config_groups
					for tmp in settings_set: i.getTag('query').setTag('item',attrs={'node':disco_config_node+tmp[1], 'name':tmp[0],'jid':towh})
				sender(i)
				raise xmpp.NodeProcessed

	elif iq.getType()=='set':
		if iq.getTag(name='command', namespace=xmpp.NS_COMMANDS) and acclvl:
			node=get_tag_item(unicode(iq),'command','node')
			if get_tag_item(unicode(iq),'command','action') == 'execute' and node.split('#')[0] in ['', disco_config_node, xmpp.NS_COMMANDS]:
				pprint('*** iq:ad-hoc commands from %s node "%s"' % (unicode(room),node))
				i=xmpp.Iq(to=room, typ='result')
				i.setAttr(key='id', val=id)
				if node == '': i.setQueryNS(namespace=xmpp.NS_DISCO_INFO)
				else: i.setTag('query',namespace=xmpp.NS_DISCO_INFO,attrs={'node':node})
				i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_DISCO_INFO})
				i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_DISCO_ITEMS})
				i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_COMMANDS})
				i.getTag('query').setTag('feature',attrs={'var':disco_config_node})
				if node == '':
					i.getTag('query').setTag('identity',attrs={'category':'client','type':'bot','name':'iSida Jabber Bot'})
					sender(i)
					raise xmpp.NodeProcessed

				elif node.split('#')[0] == disco_config_node or node == xmpp.NS_COMMANDS:
					i.getTag('query').setTag('feature',attrs={'var':xmpp.NS_COMMANDS})
					i.getTag('query').setTag('feature',attrs={'var':disco_config_node})
					try: tn = '#' + node.split('#')[1]
					except: tn = ''
					try: tmpn = tn.split('-',1)[1]
					except: tmpn = ''
					if tmpn:
						action=get_tag_item(unicode(iq),'command','action')
						i=xmpp.Iq(to=room, typ='result')
						i.setAttr(key='id', val=id)
						if action == 'cancel': i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'canceled', 'node':disco_config_node+tn,'sessionid':id})
						elif towh == selfjid:
							if get_tag_item(unicode(iq),'x','type') == 'submit':
								i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'completed', 'node':disco_config_node+tn,'sessionid':id})
								varz = iq.getTag('command').getTag('x')
								for t in owner_prefs.keys():
									try:
										tp = owner_prefs[t][1]
										tm = varz.getTag('field',attrs={'var':t}).getTagData('value')
										try:
											if tp == 'b': tm = [False,True][int(tm)]
											elif tp == 'f': tm = float(tm)
											elif tp == 'i': tm = int(tm)
											elif tp[0] == 't': tm = tm[:int(tp[1:])]
											elif tp[0] == 'l' and len(eval(tm)) == int(tp[1:]): tm = eval(tm)
											elif tp == 'd':
												if tm not in owner_prefs[t][3]: tm = owner_prefs[t][2]
										except: tm = GT(t)
										PT(t,tm)
									except: pass
								pprint('*** bot reconfigure by %s' % unicode(room))
							else:
								i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'executing', 'node':disco_config_node+tn,'sessionid':id})
								i.getTag('command').setTag('x',namespace=xmpp.NS_DATA,attrs={'type':'form'})
								#i.getTag('command').getTag('x').setTag('item',attrs={'node':disco_config_node+tn, 'name':'Configuration','jid':selfjid})
								#i.getTag('command').getTag('x').setTagData('instructions',L('For configure required x:data-compatible client'))
								tkeys = []
								for tmp in owner_groups: tkeys.append(tmp[1])
								if tn in tkeys:
									for tmp in owner_groups:
										if tn == tmp[1]:
											c_prefs,c_name = tmp[2],tmp[0]
											break
									i.getTag('command').getTag('x').setTagData('title',c_name)
									cnf_prefs = {}
									for tmp in c_prefs: cnf_prefs[tmp] = owner_prefs[tmp]
									tmp = cnf_prefs.keys()
									tt = []
									for t in tmp: tt.append((owner_prefs[t][0],t))
									tt.sort()
									tmp = []
									for t in tt: tmp.append(t[1])
									for t in tmp:
										itm = owner_prefs[t]
										itm_label = reduce_spaces(itm[0].replace('%s','').replace(':',''))
										if itm[1] == 'b':
											dc = GT(t) in [True,1,'1','on']
											i.getTag('command').getTag('x').setTag('field',attrs={'type':'boolean','label':itm_label,'var':t})\
											.setTagData('value',[0,1][dc])
										elif itm[1][0] in ['t','i','f','l']:
											i.getTag('command').getTag('x').setTag('field',attrs={'type':'text-single','label':itm_label,'var':t})\
											.setTagData('value',unicode(GT(t)))
										else:
											i.getTag('command').getTag('x').setTag('field',\
											attrs={'type':'list-single','label':itm_label,'var':t})\
											.setTagData('value',GT(t))
											for t2 in itm[3]:
												i.getTag('command').getTag('x').getTag('field',\
												attrs={'type':'list-single','label':itm_label,'var':t})\
												.setTag('option',attrs={'label':L(t2)})\
												.setTagData('value',t2)
						else:
							if get_tag_item(unicode(iq),'x','type') == 'submit':
								i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'completed', 'node':disco_config_node+tn,'sessionid':id})
								varz = iq.getTag('command').getTag('x')
								for t in config_prefs.keys():
									try:
										tmtype = varz.getTagAttr('field','type')
										tm = varz.getTag('field',attrs={'var':t}).getTagData('value')
										if tmtype == 'boolean' and tm in ['0','1']: tm = [False,True][int(tm)]
										elif config_prefs[t][2] != None:
											if config_prefs[t][2] == [True,False] and tm in ['0','1']: tm = [False,True][int(tm)]
											elif tm in config_prefs[t][2]: pass
											else: tm = config_prefs[t][3]
										put_config(getRoom(room),t,tm)
									except: pass
								pprint('*** reconfigure by %s' % unicode(room))
							else:
								i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'executing', 'node':disco_config_node+tn,'sessionid':id})
								i.getTag('command').setTag('x',namespace=xmpp.NS_DATA,attrs={'type':'form'})
								#i.getTag('command').getTag('x').setTag('item',attrs={'node':disco_config_node+tn, 'name':'Configuration','jid':selfjid})
								#i.getTag('command').getTag('x').setTagData('instructions',L('For configure required x:data-compatible client'))
								tkeys = []
								for tmp in config_groups: tkeys.append(tmp[1])
								if tn in tkeys:
									for tmp in config_groups:
										if tn == tmp[1]:
											c_prefs,c_name = tmp[2],tmp[0]
											break
									i.getTag('command').getTag('x').setTagData('title',c_name)
									cnf_prefs = {}
									for tmp in c_prefs: cnf_prefs[tmp] = config_prefs[tmp]
									tmp = cnf_prefs.keys()
									tmp.sort()
									for t in tmp:
										itm = config_prefs[t]
										itm_label = reduce_spaces(itm[0].replace('%s','').replace(':',''))
										if itm[2] == [True,False]:
											dc = get_config(getRoom(room),t) in [True,1,'1','on']
											i.getTag('command').getTag('x').setTag('field',attrs={'type':'boolean','label':itm_label,'var':t})\
											.setTagData('value',[0,1][dc])
										elif itm[2] == None:
											i.getTag('command').getTag('x').setTag('field',attrs={'type':'text-single','label':itm_label,'var':t})\
											.setTagData('value',get_config(getRoom(room),t))
										else:
											i.getTag('command').getTag('x').setTag('field',\
											attrs={'type':'list-single','label':itm_label,'var':t})\
											.setTagData('value',get_config(getRoom(room),t))

											for t2 in itm[2]:
												i.getTag('command').getTag('x').getTag('field',\
												attrs={'type':'list-single','label':itm_label,'var':t})\
												.setTag('option',attrs={'label':onoff(t2)})\
												.setTagData('value',t2)
								else: i.getTag('command').getTag('x').setTagData('title',L('Unknown configuration request!'))
						sender(i)
						raise xmpp.NodeProcessed
					else:
						if tn:
							if tn.split('-',1)[0] == '#owner': settz = owner_groups
							elif tn.split('-',1)[0] == '#room': settz = config_groups
							else: settz = None
							if settz:
								for tmp in settz:
									if tn == tmp[1]:
										i.getTag('query').setTag('identity',attrs={'category':'automation','type':'command-node','name':tmp[0]})
										break
						sender(i)
						raise xmpp.NodeProcessed
			
			else:
				pprint('*** iq:disco_set from %s node "%s"' % (unicode(room),node))
				try: tn = '#' + node.split('#')[1]
				except: tn = ''
				if node.split('#')[0] == disco_config_node or node == xmpp.NS_COMMANDS:
					action=get_tag_item(unicode(iq),'command','action')
					i=xmpp.Iq(to=room, typ='result')
					i.setAttr(key='id', val=id)
					if action == 'cancel': i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'canceled', 'node':disco_config_node+tn,'sessionid':id})
					elif towh == selfjid:
						if get_tag_item(unicode(iq),'x','type') == 'submit':
							i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'completed', 'node':disco_config_node+tn,'sessionid':id})
							varz = iq.getTag('command').getTag('x')
							for t in owner_prefs.keys():
								try:
									tp = owner_prefs[t][1]
									tm = varz.getTag('field',attrs={'var':t}).getTagData('value')
									try:
										if tp == 'b': tm = [False,True][int(tm)]
										elif tp == 'f': tm = float(tm)
										elif tp == 'i': tm = int(tm)
										elif tp[0] == 't': tm = tm[:int(tp[1:])]
										elif tp[0] == 'l' and len(eval(tm)) == int(tp[1:]): tm = eval(tm)
										elif tp == 'd':
											if tm not in owner_prefs[t][3]: tm = owner_prefs[t][2]
									except: tm = GT(t)
									PT(t,tm)
								except: pass
							pprint('*** bot reconfigure by %s' % unicode(room))
						else:
							i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'executing', 'node':disco_config_node+tn,'sessionid':id})
							i.getTag('command').setTag('x',namespace=xmpp.NS_DATA,attrs={'type':'form'})
							#i.getTag('command').getTag('x').setTag('item',attrs={'node':disco_config_node+tn, 'name':'Configuration','jid':selfjid})
							#i.getTag('command').getTag('x').setTagData('instructions',L('For configure required x:data-compatible client'))
							tkeys = []
							for tmp in owner_groups: tkeys.append(tmp[1])
							if tn in tkeys:
								for tmp in owner_groups:
									if tn == tmp[1]:
										c_prefs,c_name = tmp[2],tmp[0]
										break
								i.getTag('command').getTag('x').setTagData('title',c_name)
								cnf_prefs = {}
								for tmp in c_prefs: cnf_prefs[tmp] = owner_prefs[tmp]
								tmp = cnf_prefs.keys()
								tt = []
								for t in tmp: tt.append((owner_prefs[t][0],t))
								tt.sort()
								tmp = []
								for t in tt: tmp.append(t[1])
								for t in tmp:
									itm = owner_prefs[t]
									itm_label = reduce_spaces(itm[0].replace('%s','').replace(':',''))
									if itm[1] == 'b':
										dc = GT(t) in [True,1,'1','on']
										i.getTag('command').getTag('x').setTag('field',attrs={'type':'boolean','label':itm_label,'var':t})\
										.setTagData('value',[0,1][dc])
									elif itm[1][0] in ['t','i','f','l']:
										i.getTag('command').getTag('x').setTag('field',attrs={'type':'text-single','label':itm_label,'var':t})\
										.setTagData('value',unicode(GT(t)))
									else:
										i.getTag('command').getTag('x').setTag('field',\
										attrs={'type':'list-single','label':itm_label,'var':t})\
										.setTagData('value',GT(t))
										for t2 in itm[3]:
											i.getTag('command').getTag('x').getTag('field',\
											attrs={'type':'list-single','label':itm_label,'var':t})\
											.setTag('option',attrs={'label':L(t2)})\
											.setTagData('value',t2)
					else:
						if get_tag_item(unicode(iq),'x','type') == 'submit':
							i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'completed', 'node':disco_config_node+tn,'sessionid':id})
							varz = iq.getTag('command').getTag('x')
							for t in config_prefs.keys():
								try:
									tmtype = varz.getTagAttr('field','type')
									tm = varz.getTag('field',attrs={'var':t}).getTagData('value')
									if tmtype == 'boolean' and tm in ['0','1']: tm = [False,True][int(tm)]
									elif config_prefs[t][2] != None:
										if config_prefs[t][2] == [True,False] and tm in ['0','1']: tm = [False,True][int(tm)]
										elif tm in config_prefs[t][2]: pass
										else: tm = config_prefs[t][3]
									put_config(getRoom(room),t,tm)
								except: pass
							pprint('*** reconfigure by %s' % unicode(room))
						else:
							i.setTag('command',namespace=xmpp.NS_COMMANDS,attrs={'status':'executing', 'node':disco_config_node+tn,'sessionid':id})
							i.getTag('command').setTag('x',namespace=xmpp.NS_DATA,attrs={'type':'form'})
							#i.getTag('command').getTag('x').setTag('item',attrs={'node':disco_config_node+tn, 'name':'Configuration','jid':selfjid})
							#i.getTag('command').getTag('x').setTagData('instructions',L('For configure required x:data-compatible client'))
							tkeys = []
							for tmp in config_groups: tkeys.append(tmp[1])
							if tn in tkeys:
								for tmp in config_groups:
									if tn == tmp[1]:
										c_prefs,c_name = tmp[2],tmp[0]
										break
								i.getTag('command').getTag('x').setTagData('title',c_name)
								cnf_prefs = {}
								for tmp in c_prefs: cnf_prefs[tmp] = config_prefs[tmp]
								tmp = cnf_prefs.keys()
								tmp.sort()
								for t in tmp:
									itm = config_prefs[t]
									itm_label = reduce_spaces(itm[0].replace('%s','').replace(':',''))
									if itm[2] == [True,False]:
										dc = get_config(getRoom(room),t) in [True,1,'1','on']
										i.getTag('command').getTag('x').setTag('field',attrs={'type':'boolean','label':itm_label,'var':t})\
										.setTagData('value',[0,1][dc])
									elif itm[2] == None:
										i.getTag('command').getTag('x').setTag('field',attrs={'type':'text-single','label':itm_label,'var':t})\
										.setTagData('value',get_config(getRoom(room),t))
									else:
										i.getTag('command').getTag('x').setTag('field',\
										attrs={'type':'list-single','label':itm_label,'var':t})\
										.setTagData('value',get_config(getRoom(room),t))

										for t2 in itm[2]:
											i.getTag('command').getTag('x').getTag('field',\
											attrs={'type':'list-single','label':itm_label,'var':t})\
											.setTag('option',attrs={'label':onoff(t2)})\
											.setTagData('value',t2)
							else: i.getTag('command').getTag('x').setTagData('title',L('Unknown configuration request!'))
					sender(i)
					raise xmpp.NodeProcessed
		else:
			msg = iq.getTag(name='query', namespace=xmpp.NS_MUC_FILTER)
			if msg:
				msg,mute = get_tag(unicode(msg),'query'), None
				if msg[:2] == '<m':
					if msg.count('<body>') and msg.count('</body>'):
						jid = rss_replace(get_tag_item(msg,'message','from'))
						tojid = rss_replace(getRoom(get_level(room,getResourse(get_tag_item(msg,'message','to')))[1]))
						nick = rss_replace(get_nick_by_jid_res(room,jid))
						skip_owner = ownerbase.count(getRoom(jid))
						if get_tag_item(msg,'message','type') == 'chat' and not skip_owner:
							mbase,mcur = open_muc_base()
							tmp = mcur.execute('select * from muc where room=? and jid=?', (room,tojid)).fetchall()
							close_muc_base(mbase)
							if tmp: mute = True
						if skip_owner: pass
						elif get_config(getRoom(room),'muc_filter') and not mute:
							body = get_tag(msg,'body')

							# AD-Block filter
							if get_config(getRoom(room),'muc_filter_adblock') != 'off' and msg and not mute:
								f = []
								for reg in adblock_regexp:
									tmp = re.findall(reg,body,re.I+re.S+re.U)
									if tmp: f = f + tmp
								if f:
									act = get_config(getRoom(room),'muc_filter_adblock')
									pprint('MUC-Filter msg adblock (%s): %s [%s] %s' % (act,jid,room,body))
									if act == 'replace':
										for tmp in f: body = body.replace(tmp,[GT('censor_text')*len(tmp),GT('censor_text')][len(GT('censor_text'))>1])
										msg = msg.replace(get_tag_full(msg,'body'),'<body>%s</body>' % body)
									elif act == 'mute': mute = True
									else: msg = muc_filter_action(act,jid,room,L('AD-Block!'))

							# Repeat message filter
							if get_config(getRoom(room),'muc_filter_repeat') != 'off' and msg and not mute:
								grj = getRoom(jid)
								try: lm = last_msg_base[grj]
								except: lm = None
								if lm:
									rep_to = GT('muc_filter_repeat_time')
									try: lmt = last_msg_time_base[grj]
									except: lmt = 0
									if rep_to+lmt > time.time():
										action = False
										if body == lm: action = True
										elif lm in body:
											try: muc_repeat[grj] += 1
											except: muc_repeat[grj] = 1
											if muc_repeat[grj] >= (GT('muc_filter_repeat_count')-1): action = True
										else: muc_repeat[grj] = 0
										if action:
											act = get_config(getRoom(room),'muc_filter_repeat')
											pprint('MUC-Filter msg repeat (%s): %s [%s] %s' % (act,jid,room,body))
											if act == 'mute': mute = True
											else: msg = muc_filter_action(act,jid,room,L('Repeat message block!'))
									else: muc_repeat[grj] = 0
								last_msg_base[grj] = body
								last_msg_time_base[grj] = time.time()

							# Match filter
							if get_config(getRoom(room),'muc_filter_match') != 'off' and msg and not mute and len(body) >= GT('muc_filter_match_view'):
								tbody,warn_match,warn_space = body.split(),0,0
								for tmp in tbody:
									cnt = 0
									for tmp2 in tbody:
										if tmp2.count(tmp): cnt += 1
									if cnt > GT('muc_filter_match_count'): warn_match += 1
									if not len(tmp): warn_space += 1
								if warn_match > GT('muc_filter_match_warning_match') or warn_space > GT('muc_filter_match_warning_space') or body.count('\n'*GT('muc_filter_match_warning_nn')):
									act = get_config(getRoom(room),'muc_filter_match')
									pprint('MUC-Filter msg matcher (%s): %s [%s] %s' % (act,jid,room,body))
									if act == 'mute': mute = True
									else: msg = muc_filter_action(act,jid,room,L('Match message block!'))

							# Censor filter
							if get_config(getRoom(room),'muc_filter_censor') != 'off' and body != to_censore(body) and msg and not mute:
								act = get_config(getRoom(room),'muc_filter_censor')
								pprint('MUC-Filter msg censor (%s): %s [%s] %s' % (act,jid,room,body))
								if act == 'replace': msg = msg.replace(get_tag_full(msg,'body'),'<body>%s</body>' % to_censore(body))
								elif act == 'mute': mute = True
								else: msg = muc_filter_action(act,jid,room,L('Blocked by censor!'))

							# Large message filter
							if get_config(getRoom(room),'muc_filter_large') != 'off' and len(body) > GT('muc_filter_large_message_size') and msg and not mute:
								act = get_config(getRoom(room),'muc_filter_large')
								pprint('MUC-Filter msg large message (%s): %s [%s] %s' % (act,jid,room,body))
								if act == 'paste' or act == 'truncate':
									url = paste_text(rss_replace(body),room,jid)
									if act == 'truncate': body = u'%s[…] %s' % (body[:GT('muc_filter_large_message_size')],url)
									else: body = L('Large message%s %s') % (u'…',url)
									msg = msg.replace(get_tag_full(msg,'body'),'<body>%s</body>' % body)
								elif act == 'mute': mute = True
								else: msg = muc_filter_action(act,jid,room,L('Large message block!'))

						if mute: msg = unicode(xmpp.Message(to=jid,body=L('Warning! Your message is blocked in connection with the policy of the room!'),typ='chat',frm='%s/%s' % (room,get_nick_by_jid(room,tojid))))
					else: msg = None
						
				elif msg[:2] == '<p':
					jid = rss_replace(get_tag_item(msg,'presence','from'))
					tojid = rss_replace(get_tag_item(msg,'presence','to'))
					skip_owner = ownerbase.count(getRoom(jid))
					if skip_owner: pass
					elif get_config(getRoom(room),'muc_filter') and not mute:

						show = ['online',get_tag(msg,'show')][msg.count('<show>') and msg.count('</show>')]
						if show not in ['chat','online','away','xa','dnd']: msg = msg.replace(get_tag_full(msg,'show'), '<show>online</show>')
						status = ['',get_tag(msg,'status')][msg.count('<status>') and msg.count('</status>')]
						nick = ['',tojid[tojid.find('/')+1:]]['/' in tojid]
						gr,newjoin = getRoom(room),True
						for tmp in megabase:
							if tmp[0] == gr and tmp[4] == jid:
								newjoin = False
								break

						# Whitelist
						if get_config(gr,'muc_filter_whitelist') and msg and not mute and newjoin:
							mdb = sqlite3.connect(agestatbase,timeout=base_timeout)
							cu = mdb.cursor()
							in_base = cu.execute('select jid from age where room=? and jid=?',(gr,getRoom(jid))).fetchone()
							mdb.close()
							if not in_base:
								pprint('MUC-Filter whitelist: %s %s' % (gr,jid))
								msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('Deny by whitelist!')])])])).replace('replace_it',get_tag(msg,'presence')),True

						# AD-Block filter
						if get_config(gr,'muc_filter_adblock_prs') != 'off' and msg and not mute:
							fs,fn = [],[]
							for reg in adblock_regexp:
								tmps = [None,re.findall(reg,status,re.I+re.S+re.U)][status != '']
								tmpn = [None,re.findall(reg,nick,re.I+re.S+re.U)][nick != '']
								if tmps: fs = fs + tmps
								if tmpn: fn = fn + tmpn
							if fs:
								act = get_config(gr,'muc_filter_adblock_prs')
								pprint('MUC-Filter adblock prs status (%s): %s [%s] %s' % (act,jid,room,status))
								if act == 'replace':
									for tmp in fs: status = status.replace(tmp,[GT('censor_text')*len(tmp),GT('censor_text')][len(GT('censor_text'))>1])
									msg = msg.replace(get_tag_full(msg,'status'),'<status>%s</status>' % status)
								elif newjoin: msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('AD-Block!')])])])).replace('replace_it',get_tag(msg,'presence')),True
								elif act == 'mute': msg,mute = None,True
								else: msg = muc_filter_action(act,jid,room,L('AD-Block!'))
							if fn and msg:
								act = get_config(gr,'muc_filter_adblock_prs')
								pprint('MUC-Filter adblock prs nick (%s): %s [%s] %s' % (act,jid,room,nick))
								if act == 'replace':
									for tmp in fn: nick = nick.replace(tmp,[GT('censor_text')*len(tmp),GT('censor_text')][len(GT('censor_text'))>1])
									msg = msg.replace(tojid,'%s/%s' % (tojid.split('/',1)[0],nick))
								elif newjoin: msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('AD-Block!')])])])).replace('replace_it',get_tag(msg,'presence')),True
								elif act == 'mute': msg,mute = None,True
								else: msg = muc_filter_action(act,jid,room,L('AD-Block!'))

						# Censor filter
						if get_config(gr,'muc_filter_censor_prs') != 'off' and status+nick != to_censore(status+nick) and msg and not mute:
							act = get_config(gr,'muc_filter_censor_prs')
							pprint('MUC-Filter prs censor (%s): %s [%s] %s' % (act,jid,room,nick+'|'+status))
							if act == 'replace':
								if len(status): msg = msg.replace(get_tag_full(msg,'status'),'<status>%s</status>' % to_censore(status)).replace(tojid,'%s/%s' % (tojid.split('/',1)[0],to_censore(nick)))
								else: msg = msg.replace(tojid,'%s/%s' % (tojid.split('/',1)[0],to_censore(nick)))
							elif newjoin: msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('Blocked by censor!')])])])).replace('replace_it',get_tag(msg,'presence')),True
							elif act == 'mute': msg,mute = None,True
							else: msg = muc_filter_action(act,jid,room,L('Blocked by censor!'))

						# Large status filter
						if get_config(gr,'muc_filter_large_status') != 'off' and len(status) > GT('muc_filter_large_status_size') and msg and not mute:
							act = get_config(gr,'muc_filter_large_status')
							pprint('MUC-Filter large status (%s): %s [%s] %s' % (act,jid,room,status))
							if act == 'truncate': msg = msg.replace(get_tag_full(msg,'status'),u'<status>%s…</status>' % (status[:GT('muc_filter_large_status_size')]))
							elif newjoin: msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('Large status block!')])])])).replace('replace_it',get_tag(msg,'presence')),True
							elif act == 'mute': msg,mute = None,True
							else: msg = muc_filter_action(act,jid,room,L('Large status block!'))

						# Large nick filter
						if get_config(gr,'muc_filter_large_nick') != 'off' and len(nick) > GT('muc_filter_large_nick_size') and msg and not mute:
							act = get_config(gr,'muc_filter_large_nick')
							pprint('MUC-Filter large nick (%s): %s [%s] %s' % (act,jid,room,nick))
							if act == 'truncate': msg = msg.replace(tojid,u'%s/%s…' % (tojid.split('/',1)[0],nick[:GT('muc_filter_large_nick_size')]))
							elif newjoin: msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('Large nick block!')])])])).replace('replace_it',get_tag(msg,'presence')),True
							elif act == 'mute': msg,mute = None,True
							else: msg = muc_filter_action(act,jid,room,L('Large nick block!'))

						# Rejoin filter
						if get_config(gr,'muc_filter_rejoin') and msg and not mute and newjoin:
							try: muc_rejoins[tojid] = [muc_rejoins[tojid],muc_rejoins[tojid][1:]][len(muc_rejoins[tojid])==GT('muc_filter_rejoin_count')] + [int(time.time())]
							except: muc_rejoins[tojid] = []
							if len(muc_rejoins[tojid]) == GT('muc_filter_rejoin_count'):
								tmo = muc_rejoins[tojid][GT('muc_filter_rejoin_count')-1] - muc_rejoins[tojid][0]
								if tmo < GT('muc_filter_rejoin_timeout'):
									msg,mute = unicode(Node('presence', {'from': tojid, 'type': 'error', 'to':jid}, payload = ['replace_it',Node('error', {'type': 'auth','code':'403'}, payload=[Node('forbidden',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[]),Node('text',{'xmlns':'urn:ietf:params:xml:ns:xmpp-stanzas'},[L('To many rejoins! Wait %s sec.') % GT('muc_filter_rejoin_timeout')])])])).replace('replace_it',get_tag(msg,'presence')),True
									pprint('MUC-Filter rejoin: %s [%s] %s' % (jid,room,nick))

						# Status filter
						if get_config(gr,'muc_filter_repeat_prs') != 'off' and msg and not mute and not newjoin:
							try: muc_statuses[tojid] = [muc_statuses[tojid],muc_statuses[tojid][1:]][len(muc_statuses[tojid])==GT('muc_filter_status_count')] + [int(time.time())]
							except: muc_statuses[tojid] = []
							if len(muc_statuses[tojid]) == GT('muc_filter_status_count'):
								tmo = muc_statuses[tojid][GT('muc_filter_status_count')-1] - muc_statuses[tojid][0]
								if tmo < GT('muc_filter_status_timeout'):
									act = get_config(gr,'muc_filter_repeat_prs')
									pprint('MUC-Filter status (%s): %s [%s] %s' % (act,jid,room,nick))
									if act == 'mute': msg,mute = None,True
									else: msg = muc_filter_action(act,jid,room,L('Status-flood block!'))

				if msg:
					i=xmpp.Iq(to=room, typ='result')
					i.setAttr(key='id', val=id)
					i.setTag('query',namespace=xmpp.NS_MUC_FILTER).setTagData(tag='message', val='')
					try:
						sender(unicode(i).replace('<message />',msg))
						raise xmpp.NodeProcessed
					except: pass

def iq_async_clean():
	global iq_reques
	while not game_over:
		to = GT('timeout')
		while to > 0 and not game_over:
			to -= 1
			sleep(1)
		if len(iq_request):
			for tmp in iq_request.keys():
				if iq_request[tmp][0] + GT('timeout') < time.time(): iq_request.pop(tmp)
				break

def presence_async_clean():
	global pres_answer
	while not game_over:
		to = GT('timeout')
		while to > 0 and not game_over:
			to -= 1
			sleep(1)
		if len(pres_answer):
			tm = []
			for tmp in pres_answer:
				if tmp[2] + GT('timeout') > time.time(): tm.append(tmp)
			pres_answer = tm

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
	sleep(GT('ddos_limit')[al])
	try:
		ignorebase.remove(jid)
		pprint('!!! DDOS: Jid %s is removed from ignore!' % jid)
	except: pprint('!!! DDOS: Unable find jid %s in ignore list. Perhaps it\'s removed by bot\'s owner!' % jid)


def com_parser(access_mode, nowname, type, room, nick, text, jid):
	global last_command, ignorebase
#	if type == 'chat':
	if last_command[1:7] == [nowname, type, room, nick, text, jid] and time.time() < last_command[7]+GT('ddos_diff')[access_mode]:
		jjid = getRoom(jid)
		ignorebase.append(jjid)
		pprint('!!! DDOS Detect: %s %s/%s %s %s' % (access_mode, room, nick, jid, text))
		thr(remove_ignore,(jjid,access_mode),'ddos_remove')
		send_msg(type, room, nick, L('Warning! Exceeded the limit of sending the same message. You are blocked for a period of %s sec.') % GT('ddos_limit')[access_mode])
		return None
	no_comm = True
	cof = getFile(conoff,[])
	for parse in comms:
		if access_mode >= parse[0] and nick != nowname:
			not_offed = True
			if access_mode != 9 or ignore_owner:
				for co in cof:
					if co[0]==room and co[1]==text.lower()[:len(co[1])]:
						not_offed = None
						break
			if not_offed and (text.lower() == parse[1].lower() or text[:len(parse[1])+1].lower() == parse[1].lower()+' '):
				pprint('%s %s/%s [%s] %s' % (jid,room,nick,access_mode,text))
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
		scrobbase = sqlite3.connect(scrobblebase,timeout=base_timeout)
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
	global ignorebase, ignores, message_in, no_comm
	message_in += 1
	type=unicode(mess.getType())
	room=unicode(mess.getFrom().getStripped())
	#if type == 'headline': to_scrobble(room,mess)
	text=unicode(mess.getBody())
	if (text == 'None' or text == '') and not mess.getSubject(): return
	if mess.getTimestamp() != None: return
	nick=mess.getFrom().getResource()
	if nick != None: nick = unicode(nick)
	towh=unicode(mess.getTo().getStripped())
	lprefix = get_local_prefix(room)
	back_text = text
	rn = '%s/%s' % (room,nick)
	ft = text
	ta = get_level(room,nick)
	access_mode = ta[0]
	jid = ta[1]

	tmppos = arr_semi_find(confbase, room)
	if tmppos == -1: nowname = Settings['nickname']
	else:
		nowname = getResourse(confbase[tmppos])
		if nowname == '': nowname = Settings['nickname']
	if (jid == 'None' or jid[:4] == 'j2j.') and ownerbase.count(getRoom(room)): access_mode = 9
	if type == 'groupchat' and nick != '' and jid != 'None' and access_mode >= 0: talk_count(room,jid,nick,text)
	if nick != '' and nick != None and nick != nowname and len(text)>1 and text != 'None' and text != to_censore(text) and access_mode >= 0 and get_config(getRoom(room),'censor'):
		cens_text = L('Censored!')
		lvl = get_level(room,nick)[0]
		if lvl >= 5 and get_config(getRoom(room),'censor_warning'): send_msg(type,room,nick,cens_text)
		elif lvl == 4 and get_config(getRoom(room),'censor_action_member') != 'off':
			act = get_config(getRoom(room),'censor_action_member')
			muc_filter_action(act,jid,room,cens_text)
		elif lvl < 4 and get_config(getRoom(room),'censor_action_non_member') != 'off':
			act = get_config(getRoom(room),'censor_action_non_member')
			muc_filter_action(act,jid,room,cens_text)
	no_comm = True
	if (text != 'None') and (len(text)>=1) and access_mode >= 0 and not mess.getSubject():
		no_comm = True
		is_par = False
		if text[:len(nowname)] == nowname:
			text = text[len(nowname)+2:]
			is_par = True
		btext = text
		if text[:len(lprefix)] == lprefix:
			text = text[len(lprefix):]
			is_par = True
		if type == 'chat': is_par = True
		if is_par: no_comm = com_parser(access_mode, nowname, type, room, nick, text, jid)
		if no_comm:
			for parse in aliases:
				if (btext.lower() == parse[1].lower() or btext[:len(parse[1])+1].lower() == parse[1].lower()+' ') and room == parse[0]:
					pprint('%s %s/%s [%s] %s' % (jid,room,nick,access_mode,text))
					argz = btext[len(parse[1])+1:]
					if not argz:
						ppr = parse[2].replace('%*', '').replace('%{reduce}*', '').replace('%{reduceall}*', '').replace('%{unused}*', '')
						cpar = re.findall('%([0-9]+)', ppr, re.S)
						if len(cpar):
							for tmp in cpar:
								try: ppr = ppr.replace('%'+tmp,'')
								except: pass
					else:
						ppr = parse[2].replace('%*', argz).replace('%{reduce}*', reduce_spaces(argz)).replace('%{reduceall}*', reduce_spaces_all(argz))
						if ppr.count('%'):
							cpar = re.findall('%([0-9]+)', ppr, re.S)
							if len(cpar):
								argz = argz.split()
								argzbk = argz
								for tmp in cpar:
									try:
										it = int(tmp)
										ppr = ppr.replace('%'+tmp,argz[it])
										argzbk = argzbk[:it]+argzbk[it+1:]
									except: pass
								ppr = ppr.replace('%{unused}*',' '.join(argzbk))

					if len(ppr) == ppr.count(' '): ppr = ''
					no_comm = com_parser(access_mode, nowname, type, room, nick, ppr, jid)
					break

	thr(msg_afterwork,(mess,room,jid,nick,type,back_text,no_comm,access_mode,nowname),'msg_afterwork')

def msg_afterwork(mess,room,jid,nick,type,back_text,no_comm,access_mode,nowname):
	global topics
	not_alowed_flood = False
	subj = unicode(mess.getSubject())
	text = back_text
	if subj != 'None' and back_text == 'None':
		if subj.count('\n'): subj = '\n%s'  % subj
		if len(nick): text = L('*** %s set topic: %s') % (nick,subj)
		text = L('*** Topic: %s') % subj
		topics[room],nick = subj,''
	elif nick == '': topics[room] = back_text
	for tmp in gmessage: not_alowed_flood = tmp(room,jid,nick,type,text) or not_alowed_flood
	if no_comm:
		for tmp in gactmessage: not_alowed_flood = not_alowed_flood or tmp(room,jid,nick,type,text)
	if not not_alowed_flood and no_comm:
		if room != selfjid: is_flood = get_config(getRoom(room),'flood') not in ['off',False]
		else: is_flood = None
		if selfjid != jid and access_mode >= 0 and (back_text[:len(nowname)+2] == nowname+': ' or back_text[:len(nowname)+2] == nowname+', ' or type == 'chat') and is_flood:
			if len(back_text)>100: send_msg(type, room, nick, L('Too many letters!'))
			else:
				if back_text[:len(nowname)] == nowname: back_text = back_text[len(nowname)+2:]
				try:
					text = getAnswer(type, room, nick, back_text)
					if text: thr(send_msg_human,(type, room, nick, text),'msg_human')
				except: pass

def send_msg_human(type, room, nick, text):
	if text: sleep(len(text)/2.5+randint(0,10))
	else: text = L('What?')
	send_msg(type, room, nick, text)

def to_censore(text):
	wca = None
	for c in censor:
		cn = re.findall(c,' %s ' % text,re.I+re.S+re.U)
		for tmp in cn: text,wca = text.replace(tmp,[GT('censor_text')*len(tmp),GT('censor_text')][len(GT('censor_text'))>1]),True
	if wca: text = del_space_both(text)
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
	jid=rss_replace(get_valid_tag(mss,'jid'))
	priority=unicode(mess.getPriority())
	show=unicode(mess.getShow())
	reason=unicode(mess.getReason())
	type=unicode(mess.getType())
	status=unicode(mess.getStatusCode())
	chg_nick = [None,rss_replace(get_valid_tag(mss,'nick'))][status == '303']
	actor=unicode(mess.getActor())
	to=unicode(mess.getTo())
	id = mess.getID()
	tt = int(time.time())
	if type=='error':
		try: pres_answer.append((id,'%s: %s' % (get_tag_item(unicode(mess),'error','code'),mess.getTag('error').getTagData(tag='text')),tt))
		except:
			try: 
				pres_answer.append((id,'%s: %s' % (get_tag_item(unicode(mess),'error','code'),mess.getTag('error')),tt))
			except: pres_answer.append((id,L('Unknown error!'),tt))
		return
	elif id != None: pres_answer.append((id,None,tt))
	if jid == 'None': jid = get_level(room,nick)[1]
	if bad_presence: send_msg('groupchat', room, '', L('/me detect bad stanza from %s') % nick)
	tmppos = arr_semi_find(confbase, room.lower())
	if tmppos == -1: nowname = Settings['nickname']
	else:
		nowname = getResourse(confbase[tmppos])
		if nowname == '': nowname = Settings['nickname']
	not_found,exit_type,exit_message = 0,'',''
	if type=='unavailable':
		if status=='307': exit_type,exit_message = L('Kicked'),reason
		elif status=='301': exit_type,exit_message = L('Banned'),reason
		elif status=='303': exit_type,exit_message = L('Change nick to %s') % chg_nick,''
		else: exit_type,exit_message = L('Leave'),text
		if exit_message == 'None': exit_message = ''
		if nick != '':
			for mmb in megabase:
				if mmb[0]==room and mmb[1]==nick:
					megabase.remove(mmb)
					break
			if to == selfjid and status in ['307','301'] and confbase.count('%s/%s' % (room,nick)):
				if os.path.isfile(confs):
					confbase = eval(readfile(confs))
					confbase = arr_del_semi_find(confbase,getRoom(room))
					writefile(confs,str(confbase))
				pprint('*** bot was %s %s %s' % (['banned in','kicked from'][status=='307'],room,exit_message))
				if GT('kick_ban_notify'):
					ntf_list = GT('kick_ban_notify_jid').replace(',',' ').replace('|',' ').replace(';',' ')
					while ntf_list.count('  '): ntf_list = ntf_list.replace('  ',' ')
					ntf_list = ntf_list.split()
					if len(ntf_list):
						ntf_msg = [L('banned in'),L('kicked from')][status == '307']
						ntf_msg = L('Bot was %s %s with reason: %s') % (ntf_msg,room,exit_message)
						for tmp in ntf_list: send_msg('chat', tmp, '', ntf_msg)
	else:
		if nick != '':
			for mmb in megabase:
				if mmb[0]==room and mmb[1]==nick:
					megabase.remove(mmb)
					megabase.append([room, nick, role, affiliation, jid])
					if role != mmb[2] or affiliation != mmb[3]: not_found = 1
					else: not_found = 2
					break
			if not not_found: megabase.append([room, nick, role, affiliation, jid])
	if jid == 'None': jid, jid2 = '<temporary>%s' % nick, 'None'
	else: jid2, jid = jid, getRoom(jid.lower())
	for tmp in gpresence: thr(tmp,(room,jid2,nick,type,(text, role, affiliation, exit_type, exit_message, show, priority, not_found, chg_nick)),'presence_afterwork')
	al = get_level(getRoom(room),nick)[0]
	if al == 9:
		if type == 'subscribe': 
			caps_and_send(Presence(room, 'subscribed'))
			caps_and_send(Presence(room, 'subscribe'))
			pprint('Subscribe %s' % room)
		elif type == 'unsubscribed':
			caps_and_send(Presence(room, 'unsubscribe'))
			caps_and_send(Presence(room, 'unsubscribed'))
			pprint('Unsubscribe %s' % room)
	if nick != '' and nick != 'None' and nick != nowname and len(text)>1 and text != 'None' and al >= 0 and get_config(getRoom(room),'censor'):
		nt = '%s %s' % (nick,text)
		if nt != to_censore(nt):
			cens_text = L('Censored!')
			if al >= 5 and get_config(getRoom(room),'censor_warning'): send_msg('groupchat',room,nick,cens_text)
			elif al == 4 and get_config(getRoom(room),'censor_action_member') != 'off':
				act = get_config(getRoom(room),'censor_action_member')
				muc_filter_action(act,jid2,getRoom(room),cens_text)
			elif al < 4 and get_config(getRoom(room),'censor_action_non_member') != 'off':
				act = get_config(getRoom(room),'censor_action_non_member')
				muc_filter_action(act,jid2,getRoom(room),cens_text)
	mdb = sqlite3.connect(agestatbase,timeout=base_timeout)
	cu = mdb.cursor()
	ab = cu.execute('select * from age where room=? and jid=? and nick=?',(room, jid, nick)).fetchone()
	ttext = '%s\n%s\n%s\n%s\n%s' % (role,affiliation,priority,show,text)
	if ab:
		if type=='unavailable': cu.execute('update age set time=?, age=?, status=?, type=?, message=? where room=? and jid=? and nick=?', (tt,ab[4]+(tt-ab[3]),1,exit_type,exit_message,room, jid, nick))
		else:
			if ab[5]: cu.execute('update age set time=?, status=?, message=? where room=? and jid=? and nick=?', (tt,0,ttext,room, jid, nick))
			else: cu.execute('update age set status=?, message=? where room=? and jid=? and nick=?', (0,ttext,room, jid, nick))
	else: cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (room,nick,jid,tt,0,0,'',ttext))
	mdb.commit()

def onoff_no_tr(msg):
	if msg == None or msg == False or msg == 0 or msg == '0': return 'off'
	elif msg == True or msg == 1 or msg == '1': return 'on'
	else: return msg

def onoff(msg): return L(onoff_no_tr(msg))

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
	try: return jid.split('/')[1]
	except: return ''

def getRoom(jid):
	jid = unicode(jid)
	if jid == 'None': return jid
	return '%s@%s' % (getName(jid),getServer(jid))

def now_schedule():
	while not game_over:
		to = GT('schedule_time')
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
			pprint('check rss: %s in %s' % (fd[0],fd[4]))
			rss('groupchat', fd[4], 'RSS', 'new %s 10 %s silent' % (fd[0],fd[2]))
			break

def talk_count(room,jid,nick,text):
	jid = getRoom(jid)
	mdb = sqlite3.connect(talkersbase,timeout=base_timeout)
	cu = mdb.cursor()
	ab = cu.execute('select * from talkers where room=? and jid=?',(room,jid)).fetchone()
	wtext = len(reduce_spaces_all(text).split(' '))
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
	pprint('--- Last stanza ---')
	pprint(last_stanza)
	pprint('-------------------')
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

nmbrs = ['0','1','2','3','4','5','6','7','8','9','.']
ul = 'update.log'					# лог последнего обновление
debugmode = None					# остановка на ошибках
dm = None							# отладка xmpppy
dm2 = None							# отладка действий бота
CommandsLog = None					# логгирование команд
prefix = '_'						# префикс комманд
msg_limit = 1000					# лимит размера сообщений
botName = 'Isida-Bot'				# название бота
botVersion = 'v2.30'				# версия бота
capsVersion = botVersion[1:]		# версия для капса
disco_config_node = 'http://isida-bot.com/config'
banbase = []						# результаты muc запросов
pres_answer = []					# результаты посылки презенсов
iq_request = {}						# iq запросы
th_cnt = 0							# счётчик тредов
thread_error_count = 0				# счётчик ошибок тредов
bot_exit_type = None				# причина завершения бота
last_stream = []					# очередь станз к отправке
last_command = []					# последняя исполненная ботом команда
thread_type = True					# тип тредов
time_limit = 1.1					# максимальная задержка между посылкой станз с одинаковым типом в groupchat
time_nolimit = 0.05					# задержка между посылкой станз с разными типами
message_in,message_out = 0,0		# статистика сообщений
iq_in,iq_out = 0,0					# статистика iq запросов
presence_in,presence_out = 0,0		# статистика презенсов
unknown_out = 0						# статистика ошибочных отправок
cycles_used,cycles_unused = 0,0		# статистика циклов
id_count = 0						# номер запроса
megabase = []						# главная временная база с полной информацией из презенсов
ignore_owner = None					# исполнять отключенные команды для владельца бота
configname = 'settings/config.py'	# конфиг бота
topics = {}							# временное хранение топиков
last_msg_base = {}					# последние сообщения
last_msg_time_base = {}				# время между последними сообщениями последние сообщения
paranoia_mode = False				# режим для параноиков. запрет любых исполнений внешнего кода
no_comm = True
muc_rejoins = {}
muc_statuses = {}
muc_repeat = {}
last_stanza = ''					# последняя станза, посланная ботом
ENABLE_TLS = True					# принудительное отключение TLS
base_timeout = 20					# таймаут на доступ ко всем базам
between_msg_last = {}				# время последнего сообщения

gt=gmtime()
lt=tuple(localtime())
if lt[0:3] == gt[0:3]: timeofset = int(lt[3])-int(gt[3])
elif lt[0:3] > gt[0:3]: timeofset = int(lt[3])-int(gt[3]) + 24
else: timeofset = int(gt[3])-int(lt[3]) + 24

if os.path.isfile(configname): execfile(configname)
else: errorHandler(configname+' is missed.')

#---------------------------
muc_lock_base = set_folder+'muclock.db'
#---------------------------

if os.path.isfile(ver_file):
	bvers = str(readfile(ver_file)).replace('\n','').replace('\r','').replace('\t','').replace(' ','')
	if len(bvers[:-1]) > 1: botVersion +='.%s' % bvers
try: tmp = botOs
except: botOs = os_version()

logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG,)	# включение логгирования
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
			if (not c[:3].count('#')) and len(c) and c.count('\t'): locales[c.split('\t',1)[0].replace('\\n','\n').replace('\\t','\t')] = c.split('\t',1)[1].replace('\\n','\n').replace('\\t','\t')
pprint('*** Loading main plugin')

execfile('plugins/main.py')
plname		= 'plugins/list.txt'
pliname		= 'plugins/ignored.txt'
gtimer		= [check_rss]
gpresence	= []
gmessage	= []
gactmessage	= []

pprint('*** Loading other plugins')

plugins   = getFile(plname,[])
pl_ignore = getFile(pliname,[])

for pl in plugins:
	if pl in pl_ignore: pprint('Ignore plugin: %s' % pl)
	else:
		presence_control,message_control,message_act_control,iq_control,timer,execute = [],[],[],[],[],[]
		pprint('Append plugin: %s' % pl)
		execfile('plugins/%s' % pl)
		for cm in execute: comms.append((cm[0],cm[1],cm[2],cm[3],L('Plugin %s. %s') % (pl[:-3],cm[4])))
		for tmr in timer: gtimer.append(tmr)
		for tmp in presence_control: gpresence.append(tmp)
		for tmp in message_control: gmessage.append(tmp)
		for tmp in message_act_control: gactmessage.append(tmp)

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
confbase = getFile(confs,['%s/%s' % (defaultConf.lower(),Settings['nickname'])])
if os.path.isfile(cens):
	censor = readfile(cens).decode('UTF').replace('\r','').split('\n')
	cn = []
	for c in censor:
		if (not c.count('#')) and len(c): cn.append(c)
	censor = cn
else: censor = []

pprint('*'*50)
pprint('*** Name: %s' % botName)
pprint('*** Version: %s' % botVersion)
pprint('*** OS: %s ' % botOs)
pprint('*'*50)
pprint('*** (c) 2oo9-2o1o Disabler Production Lab.')

lastnick = Settings['nickname']
jid = JID(Settings['jid'])
if getResourse(jid) in ['None','']: jid = JID(Settings['jid'].split('/')[0]+'/my owner is stupid and can not complete the configuration')
selfjid = jid
pprint('JID: %s' % unicode(jid))
raw_iq = []

try:
	try:
		Server = tuple(server.split(':'))
		Port = int(server.split(':')[1])
		pprint('Trying to connect to %s' % server)
	except: Server,Port = None,5222
	if dm: cl = Client(jid.getDomain(),Port,ENABLE_TLS=ENABLE_TLS)
	else: cl = Client(jid.getDomain(),Port,debug=[],ENABLE_TLS=ENABLE_TLS)
	try:
		Proxy = proxy
		pprint('Using proxy %s' % Proxy['host'])
	except NameError: Proxy = None
	try:
		Secure = secure
		pprint('Tryins secured connection')
	except NameError: Secure = None
	cl.connect(Server,Proxy,Secure,ENABLE_TLS=ENABLE_TLS)
	pprint('Connected')
	cl.auth(jid.getNode(), Settings['password'], jid.getResource())
	pprint('Autheticated')
except:
	pprint('Auth error or no connection. Restart in %s sec.' % GT('reboot_time'))
	sleep(GT('reboot_time'))
	sys.exit('restart')
pprint('Registration Handlers')
cl.RegisterHandler('message',messageCB)
cl.RegisterHandler('iq',iqCB)
cl.RegisterHandler('presence',presenceCB)
cl.RegisterDisconnectHandler(disconnecter)
cl.UnregisterDisconnectHandler(cl.DisconnectHandler)
if GT('show_loading_by_status'): caps_and_send(Presence(show=GT('show_loading_by_status_show'), status=GT('show_loading_by_status_message'), priority=Settings['priority']))
else: caps_and_send(Presence(show=Settings['status'], status=Settings['message'], priority=Settings['priority']))
#cl.sendInitPresence()

pprint('Wait conference')
sleep(0.5)
game_over = None
#thr(sender_stack,(),'sender')
cb = []
is_start = True
lastserver = getServer(confbase[0].lower())
setup = getFile(c_file,{})
join_percent, join_pers_add = 0, 100.0/len(confbase)

for tocon in confbase:
	try: t = setup[getRoom(tocon)]
	except: 
		setup[getRoom(tocon)] = {}
		writefile(c_file,str(setup))
	baseArg = unicode(tocon)
	if not tocon.count('/'): baseArg += '/%s' % unicode(Settings['nickname'])
	conf = JID(baseArg)
	zz = joinconf(tocon, getServer(Settings['jid']))
	while unicode(zz)[:3] == '409' and not game_over:
		sleep(1)
		tocon += '_'
		zz = joinconf(tocon, getServer(Settings['jid']))
	cb.append(tocon)
	pprint('--> %s' % tocon)
	if GT('show_loading_by_status_percent'):
		join_percent += join_pers_add
		join_status = '%s %s%s' % (GT('show_loading_by_status_message'),int(join_percent),'%')
		if GT('show_loading_by_status'): caps_and_send(Presence(show=GT('show_loading_by_status_show'), status=join_status, priority=Settings['priority']))
	if game_over: break
confbase = cb
is_start = None
pprint('Joined')

#pep = xmpp.Message(to=selfjid, frm=getRoom(selfjid), payload=[xmpp.Node('event',{'xmlns':'http://jabber.org/protocol/pubsub#event'},[xmpp.Node('items',{'node':'http://jabber.org/protocol/tune'},[xmpp.Node('item',{'id':'current'},[xmpp.Node('tune',{'xmlns':'http://jabber.org/protocol/tune'},[])])])])])
#sender(pep)

thr(now_schedule,(),'schedule')
thr(iq_async_clean,(),'async_iq_clean')
thr(presence_async_clean,(),'async_presence_clean')
try: thr(bomb_random,(),'bomb_random')
except: pass

if GT('show_loading_by_status'): caps_and_send(Presence(show=Settings['status'], status=Settings['message'], priority=Settings['priority']))

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
		try: SM = str(SM)
		except: SM = unicode(SM)
		pprint('*** Error *** %s ***' % SM)
		logging.exception(' [%s] ' % timeadd(tuple(localtime())))
		if str(SM).lower().count('parsing finished'):
			close_age()
			kill_all_threads()
			flush_stats()
			sleep(300)
			sys.exit('restart')
		if debugmode: raise

# The end is near!
