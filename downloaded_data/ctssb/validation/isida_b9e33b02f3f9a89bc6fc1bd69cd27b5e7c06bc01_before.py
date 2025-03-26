#!/usr/bin/python
# -*- coding: utf -*-

turn_base = []

def turner(type, jid, nick, text):
	if type != 'groupchat':
		send_msg(type, jid, nick, L('Not allowed in private!'))
		return
	global turn_base
	rtab = L('qwertyuiop[]asdfghjkl;\'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>~')
	ltab = L('QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>~qwertyuiop[]asdfghjkl;\'zxcvbnm,.`')
	if text == '':
		for tmp in turn_base:
			if tmp[0] == jid and tmp[1] == nick:
				turn_base.remove(tmp)
				to_turn = tmp[2]
				break
	else: to_turn = text
	if to_turn[:3] == '/me': msg, to_turn = '*'+nick, to_turn[3:]
	elif to_turn.count(': '): msg, to_turn = to_turn.split(': ',1)[0]+': ', to_turn.split(': ',1)[1]
	else: msg = ''
	for tex in to_turn:
		notur = 1
		for i in range(0,len(rtab)):
			if tex == rtab[i]:
				msg += ltab[i]
				notur = 0
				break
		if notur: msg += tex
	if get_config(getRoom(room),'censor'): msg = to_censore(msg)
	send_msg('groupchat', jid, '', msg)

def append_to_turner(room,jid,nick,type,text):
	global turn_base
	for tmp in turn_base:
		if tmp[0] == room and tmp[1] == nick:
			turn_base.remove(tmp)
			break
	turn_base.append((room,nick,text))

def remove_from_turner(room,jid,nick,type,text):
	global turn_base
	if type=='unavailable':
		for tmp in turn_base:
			if tmp[0] == room and tmp[1] == nick:
				turn_base.remove(tmp)
				break

global execute

message_control = [append_to_turner]
presence_control = [remove_from_turner]

execute = [(0, 'turn', turner, 2, L('Turn text from one layout to another.'))]
