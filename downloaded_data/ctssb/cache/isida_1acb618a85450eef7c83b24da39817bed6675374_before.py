#!/usr/bin/python
# -*- coding: utf -*-

karmabase = set_folder+'karma.db'	# база кармы
karma_limit = 5						# минимум кармы для изменения
karma_timeout = [86400, 3600, 5]	# время, через которое можно менять карму

karmabasefile = os.path.isfile(karmabase)
karma_base = sqlite3.connect(karmabase)
cu_karmabase = karma_base.cursor()
if not karmabasefile:
	cu_karmabase.execute('''create table karma (room text, jid text, karma int)''')
	cu_karmabase.execute('''create table commiters (room text, jid text, karmajid text, last int)''')
	karma_base.commit()
karma_base.close()

def karma(type, jid, nick, text):
	arg = text.split(' ',1)
	try: arg1 = arg[1]
	except: arg1 = None
	if arg[0].lower() == 'show': msg = karma_show(type, jid, nick, arg1)
	elif arg[0].lower() == 'top+': msg = karma_top(type, jid, nick, arg1, None)
	elif arg[0].lower() == 'top-': msg = karma_top(type, jid, nick, arg1, True)
	elif arg[0].lower() == 'ban': msg = karma_ban(type, jid, nick, arg1)
	elif arg[0].lower() == 'moderator': msg = karma_moderator(type, jid, nick, arg1)
	else: msg = karma_show(type, jid, nick, arg[0])
	send_msg(type, jid, nick, msg)

def karma_top(type, jid, nick, text, order):
	try: lim = int(text)
	except: lim = 10
	if lim < 1: lim = 1
	elif lim > 20: lim = 20
	karma_base = sqlite3.connect(karmabase)
	cu_karmabase = karma_base.cursor()
	if order: stat = cu_karmabase.execute('select jid,karma from karma where room=? order by karma',(jid,)).fetchall()
	else: stat = cu_karmabase.execute('select jid,karma from karma where room=? order by -karma',(jid,)).fetchall()
	karma_base.close()
	if stat == None: return L('In this room karma is not changed!')
	msg, cnt = '', 1
	for tmp in stat:
		tmp2 = get_nick_by_jid(jid, tmp[0])
		if tmp2:
			msg += '\n'+str(cnt)+'. '+tmp2+'\t'+karma_val(int(tmp[1]))
			cnt += 1
		if cnt >= lim: break
	if len(msg): return L('Top karma: %s') % msg
	else: return L('Karma for members is present not changed!')
		
	
def karma_show(type, jid, nick, text):
	if text == None or text == '' or text == nick: text, atext = nick, L('Your')
	else: atext = text
	karmajid = getRoom(get_access(jid,text)[1])
	if karmajid == 'None': return L('I\'m not sure, but %s not is here.') % atext
	else:
		karma_base = sqlite3.connect(karmabase)
		cu_karmabase = karma_base.cursor()
		stat = cu_karmabase.execute('select karma from karma where room=? and jid=?',(jid,karmajid)).fetchone()
		karma_base.close()
		if stat == None: return L('%s have a clear karma') % atext
		else: return L('%s karma is %s') % (atext, karma_val(int(stat[0])))

def karma_ban(type, jid, nick, text):
	return L('I can\'t!')

def karma_moderator(type, jid, nick, text):
	return L('I can\'t!')
	
def karma_get_access(room,jid):
	karma_base = sqlite3.connect(karmabase)
	cu_karmabase = karma_base.cursor()
	stat = cu_karmabase.execute('select karma from karma where room=? and jid=?',(room,jid)).fetchone()
	karma_base.close()
	if stat == None: return None
	if int(stat[0]) < karma_limit: return None
	return True
	
def karma_val(val):
	if val == 0: return '0'
	elif val < 0: return str(val)
	else: return '+'+str(val)
	
def karma_change(room,jid,nick,type,text,value):
	if type == 'chat': msg = L('You can\'t change karma in private!')
	else:
		cof = getFile(conoff,[])
		if (room,'karma') in cof: return
		if text.count(': '): text = text.split(': ',1)[0]
		elif text.count(', '): text = text.split(', ',1)[0]
		else: text = text[:-4]
		k_aff = get_affiliation(room,nick)
		k_acc = get_access(room,nick)[0]
		if k_acc < 0: return
		if k_aff != 'none' or k_acc > 0 or karma_get_access(room,jid):
			jid, karmajid = getRoom(jid), getRoom(get_access(room,text)[1])
			if karmajid == getRoom(selfjid): return
			elif karmajid == 'None': msg = L('You can\'t change karma in outdoor conference!')
			elif karmajid == jid: msg = L('You can\'t change own karma!')
			else:
				karma_base = sqlite3.connect(karmabase)
				cu_karmabase = karma_base.cursor()
				stat = cu_karmabase.execute('select last from commiters where room=? and jid=? and karmajid=?',(room,jid,karmajid)).fetchone()
				karma_valid, karma_time = None, int(time.time())
				if stat == None: karma_valid = True
				elif karma_time - int(stat[0]) >= karma_timeout[k_acc]: karma_valid = True
				if karma_valid:
					if stat: cu_karmabase.execute('update commiters set last=? where room=? and jid=? and karmajid=?',(karma_time,room,jid,karmajid))
					else: cu_karmabase.execute('insert into commiters values (?,?,?,?)',(room,jid,karmajid,karma_time))
					stat = cu_karmabase.execute('select karma from karma where room=? and jid=?',(room,karmajid)).fetchone()
					if stat:
						stat = stat[0]+value
						cu_karmabase.execute('delete from karma where room=? and jid=?',(room,karmajid)).fetchall()
					else: stat = value
					cu_karmabase.execute('insert into karma values (?,?,?)',(room,karmajid,stat)).fetchall()
					msg = L('You changes %s\'s karma to %s. Next time to change across: %s.') %\
						(text,karma_val(stat),un_unix(karma_timeout[k_acc]))
					karma_base.commit()
					pprint('karma change in '+room+' for '+text+' to '+str(stat))
				else: msg = L('Time from last change %s\'s karma is very small. Please wait %s.') % \
					(text,un_unix(int(stat[0])+karma_timeout[k_acc]-karma_time))
				karma_base.close()
		else: msg = L('You can\'t change karma!')
	send_msg(type, room, nick, msg)

def karma_check(room,jid,nick,type,text):
	if getRoom(jid) == getRoom(selfjid): return
	if len(unicode(text)) < 5: return
	while len(text) and text[-1:] == ' ': text = text[:-1]
	if text[-3:] == ' +1': karma_change(room,jid,nick,type,text,1)
	elif text[-3:] == ' -1': karma_change(room,jid,nick,type,text,-1)
	
global execute, message_control

message_control = [karma_check]

execute = [(0, 'karma', karma, 2, L('Karma.\nkarma [show] nick\nkarma top+|- [count]\nFor change karma: nick: +1\nnick: -1'))]
