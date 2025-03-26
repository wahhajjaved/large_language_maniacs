#!/usr/bin/python
# -*- coding: utf -*-

def call_body(type, jid, nick, text):
	skip = 1
	if len(text):
		try:
			reason = text.split('\n')[1]
			text = text.split('\n')[0]
		except:
			reason = None
		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		fnd = cu.execute('select jid from age where room=? and (nick=? or jid=?)',(jid,text,text)).fetchall()
		if len(fnd) == 1:
			whojid = getRoom(str(fnd[0][0]))
			is_found = 0
			for tmp in megabase:
				if tmp[0] == jid and getRoom(tmp[4]) == whojid:
					is_found = 1
					break
			if is_found:
				msg = u'Хватит бухать! '+text+u' находится тут!'
			else:
				msg = u'Позвала'
				skip = 0
		elif len(fnd) > 1:
			msg = u'Я видела несколько человек с таким ником. Укажите точнее!'
		else:
			msg = u'Я не в курсе кто такой '+text
	else:
		msg = u'Ась?'

	if skip:
	        send_msg(type, jid, nick, msg)
	else:
		inv_msg = nick+u' просит Вас зайти в '+jid
		if reason:
			inv_msg += u' по причине: '+reason
		send_msg('chat',whojid, '',inv_msg)
		send_msg(type, jid, nick, msg)

global execute

execute = [(0, u'invite', call_body, 2)]
