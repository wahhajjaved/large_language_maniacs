#!/usr/bin/python
# -*- coding: utf-8 -*-

def gcalc(type, jid, nick, text):
	if not text.strip(): msg = L('What?')
	else:
		start='<h2 class=r style="font-size:138%"><b>'
		end='</b>'
		data = load_page('http://www.google.ru/search?', {'q':text.encode('utf-8'),'hl':GT('youtube_default_lang')})
		if data.find(start)==-1: msg = L('Google Calculator results not found')
		else:
			begin=data.index(start)
			result=data[begin+len(start):begin+data[begin:].index(end)]
			result = result.replace("<font size=-2> </font>",",").replace(" &#215; 10<sup>","E").replace("</sup>","").replace("\xa0","").replace('<sup>','^')
			msg = result.decode('utf-8', 'ignore')
	send_msg(type, jid, nick, msg)

def define(type, jid, nick, text):
	text = text.strip()
	target, define_silent = '', False
	if not text: msg = L('What?')
	else:
		if re.search('\A\d+?(-\d+?)? ', text): target, text = text.split(' ', 1)
		start='<h2 class=r style="font-size:138%"><b>'
		end='</b>'
		data = load_page('http://www.google.ru/search?', {'q': 'define:%s' % text.encode('utf-8')})
		result = re.findall('<li>(.+?)<font color=#008000>(.+?)</font></a><p>', data)
		if target:
			try: n1 = n2 = int(target)
			except: n1, n2 = map(int, target.split('-'))
			if n1+n2 == 0: define_silent,n1,n2 = True,1,1
		if not result: msg = [L('I don\'t know!'),''][define_silent]
		else:
			if target:
				msg = ''
				if 0 < n1 <= n2 <= len(result): 
					for k in xrange(n1-1,n2): msg += result[k][0] + '\nhttp://' + result[k][1] + '\n\n'
				else: msg = [L('I don\'t know!'),''][define_silent]
			else:
				result = random.choice(result)
				msg = result[0] + '\nhttp://' + result[1]
			msg = re.sub(r'<[^<>]+>', ' ', msg).strip()
			msg = rss_replace(html_encode(urllib.unquote(msg)))
	if msg: send_msg(type, jid, nick, msg)

def define_message(room,jid,nick,type,text):
	s = get_config(room,'parse_define')
	if s != 'off':
		cof = getFile(conoff,[])
		if (room,'define') in cof: return
		tmppos = arr_semi_find(confbase, room)
		nowname = getResourse(confbase[tmppos])
		text = re.sub('^%s[,:]\ ' % nowname, '', text.strip())
		what = re.search([u'^(?:(?:что такое)|(?:кто такой)) ([^?]+?)\?$',u'(?:(?:что такое)|(?:кто такой)) ([^?]+?)\?'][s=='partial'], text, re.I+re.U+re.S)
		if what:
			access_mode = get_level(room,nick)[0]
			text = 'define 0 ' + what.group(1)
			com_parser(access_mode, nowname, type, room, nick, text, jid)
			return True

global execute, message_control

message_act_control = [define_message]

execute = [(3, 'gcalc', gcalc, 2, L('Google Calculator')),
	(3, 'define', define, 2, L('Definition for a word or phrase.\ndefine word - random define of word or phrase\ndefine N word - N-th define of word or phrase\ndefine a-b word - from a to b defines of word or phrase'))]
