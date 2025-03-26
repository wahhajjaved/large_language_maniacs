#!/usr/bin/python
# -*- coding: utf -*-

def juick(type, jid, nick, text):
	if text[:9]== 'tag user ': juick_tag_user(type, jid, nick, text[9:])
	elif text[:8]== 'tag msg ': juick_tag_msg(type, jid, nick, text[8:])
	elif text[:4]== 'msg ': juick_msg(type, jid, nick, text[4:])
	elif text[:5]== 'user ': juick_user(type, jid, nick, text[5:])
	elif text[:5]== 'info ': juick_user_info(type, jid, nick, text[5:])
	else: send_msg(type, jid, nick, L('Smoke help about command!'))

def juick_user_info(type, jid, nick, text):
	text = text.replace('@','')
	if len(text):
		text = text.split(' ')[0]
		link = 'http://juick.com/'+text.encode('utf-8').replace('\\x','%').replace(' ','%20')+'/friends'
		body = urllib.urlopen(link).read()
		body = rss_replace(html_encode(body))

		if body.count('<h1>Page Not Found</h1>'): msg = L('User %s not found') % text
		else:
			link = 'http://juick.com/'+text.encode('utf-8').replace('\\x','%').replace(' ','%20')+'/readers'
			rbody = urllib.urlopen(link).read()
			rbody = rss_replace(html_encode(rbody))
			link = 'http://juick.com/'+text.encode('utf-8').replace('\\x','%').replace(' ','%20')+'/tags'
			tbody = urllib.urlopen(link).read()
			tbody = rss_replace(html_encode(tbody))
			msg = get_tag(body,'h1')+' - http://juick.com'+get_subtag(body.split('pagetabs')[1].split('</li>')[0],'href')
			tb = body.split('<div id="content">')[1].split('</p>')[0]
			try:
				if len(tb)>=20 and tb.count('I read'):
					msg += '\n'+get_tag(tb,'h2')+' - '
					for tmp in tb.split('<p>')[1].split('<a href="')[1:]: msg += tmp[tmp.find('>')+1:tmp.find('<',tmp.find('>'))]+', '
					msg = msg[:-2]
				else: msg += '\nNo readers'
			except: msg += '\nNo readers'

			if not rbody.count('<h1>Page Not Found</h1>'):
				try:
					tb = rbody.split('<div id="content">')[1].split('</div>')[0]
					if len(tb)>=20 and tb.count('My read'):
						msg += '\n'+get_tag(tb,'h2')+' - '
						for tmp in tb.split('<p>')[1].split('<a href="')[1:]: msg += tmp[tmp.find('>')+1:tmp.find('<',tmp.find('>'))]+', '
						msg = msg[:-2]
					else: msg += '\nNo readers'
				except: msg += '\nNo readers'

			if not tbody.count('<h1>Page Not Found</h1>'):
				try:
					tb = tbody.split('<div id="content">')[1].split('</div>')[0]
					msg += '\nTags: '
					for ttb in tb.split('<span')[1:]: msg += get_tag(ttb,'a')+', '
					msg = msg[:-2]
				except: msg += '\nNo tags'
	else: msg = L('Who?')
	send_msg(type, jid, nick, msg)

def juick_user(type, jid, nick, text):
	text = text.replace('@','')
	if len(text):
		try: mlen = int(text.split(' ')[1])
		except: mlen = juick_user_post_limit
		try: mlim = int(text.split(' ')[2])
		except: mlim = juick_user_post_size
		text = text.split(' ')[0]
		link = 'http://juick.com/'+text.encode('utf-8').replace('\\x','%').replace(' ','%20')
		body = urllib.urlopen(link).read()
		body = html_encode(body)
		if body.count('<h1>Page Not Found</h1>'): msg = L('User %s not found') % text
		else:
			msg = get_tag(body,'h1')+' - http://juick.com'+get_subtag(body.split('pagetabs')[1].split('</li>')[0],'href')
			mes = body.split('<li class="liav"')
			mesg = ''
			for us in mes[1:mlen+1]:
				mesg += '\n'+get_tag(us.split('<small>')[1],'a')+' - '
				if us.count('<div class="ps">'): mm = get_subtag(us.split('<div>')[1],'a href') + ' ' + rss_del_html(us.split('<div>',1)[1].split('<small>')[0])
				else: mm = rss_del_html(get_tag(us,'div'))
				mm = rss_replace(mm)
				if len(mm)<mlim: mesg += mm
				else: mesg += mm[:mlim]+'[...]'
				if us.split('</span>')[1].count('<a'): mesg += ' ('+get_tag(us,'span')+'|'+get_tag(us.split('</span>')[1],'a')+')'
				else: mesg += ' ('+get_tag(us,'span')+'|No replies)'
			msg += mesg
	else: msg = L('Who?')
	send_msg(type, jid, nick, msg)

def juick_msg(type, jid, nick, text):
	if len(text):
		try:
			text = text.replace('#','')
			if text.count('/'): link,post = 'http://juick.com/'+text.split('/')[0],int(text.split('/')[1])
			else: link,post = 'http://juick.com/'+text.split(' ')[0],0
			try: repl_limit = int(text.split(' ')[1])
			except: repl_limit = juick_msg_answers_default
			body = urllib.urlopen(link).read()
			body = html_encode(body.replace('<div><a href','<div><a '))
			if body.count('<h1>Page Not Found</h1>'): msg = L('Message #%s not found') % text
			else:
				nname = get_tag(body,'h1')
				if nname.count('(') and nname.count(')'): uname = nname[nname.find('(')+1:nname.find(')')]
				else: uname = nname
				msg = 'http://juick.com/'+uname+'/'+text.split(' ')[0]+'\n'+nname+' - '
				if body.split('<p>')[1].count('<div class="ps">'): msg += get_subtag(body.split('<p>')[1].split('<div class="ps">')[1],'a href') + body.split('<p>')[1].split('</div>',1)[1].split('<small>')[0]
				else: msg += get_tag(body.split('<p>')[1],'div')
			repl = get_tag(body.split('<p>')[1],'h2')
			if repl.lower().count('('):
				hm_repl = int(repl[repl.find('(')+1:repl.find(')')])
				msg += L('(Replies: %s)') % str(hm_repl)
			else:
				hm_repl = 0
				msg += L('(No replies)')
			frm = get_tag(body.split('<p>')[1],'small')
			msg += frm[frm.find(' '):]
			cnt = 1
			if hm_repl:
				if not post:
					for rp in body.split('<li id="')[1:repl_limit+1]:
						msg += '\n'+text.split(' ')[0]+'/'+str(cnt)+' '+get_tag(rp,'a')+': '+get_tag(rp,'div')
						cnt += 1
				else: msg += '\n'+text+' '+get_tag(body.split('<li id="')[post],'div')
			remove = re.findall(r'" rel="nofollow">.*?</a>', msg, re.S)
			for tmp in remove: msg = msg.replace(tmp,' ')
			msg = rss_replace(rss_del_html(msg.replace('<a href="http','http'))).replace('<small>','\n')
			while msg.count('  '): msg = msg.replace('  ',' ')
		except: msg = L('Invalid message number')
	else: msg = L('What message do you want to find?')
	send_msg(type, jid, nick, msg)

def juick_tag_user(type, jid, nick, text):
	if len(text):
		try: mlen = int(text.split(' ')[1])
		except: mlen = juick_tag_user_limit
		text = text.split(' ')[0]
		if mlen > juick_tag_user_max: mlen = juick_tag_user_max
		link = 'http://juick.com/last?tag='+text.encode('utf-8').replace('\\x','%').replace(' ','%20')
		body = urllib.urlopen(link).read()
		body = rss_replace(html_encode(body))
		if body.count('<p>Tag not found</p>') or body.count('<h1>Page Not Found</h1>'): msg = L('Tag %s not found') % text
		else:
			usr = body.split('<h2>Users</h2>')[1].split('<h2>Messages</h2>')[0].split('<a href')
			users = ''
			for us in usr[1:mlen+1]:
				uus = us[us.find('>')+1:us.find('<',us.find('>'))]
				users += '\n'+ uus + ' - http://juick.com/'+uus[1:]
			msg = L('Tag %s found in %s') % (text, users)
	else: msg = L('What tag do you want to find?')
	send_msg(type, jid, nick, msg)

def juick_tag_msg(type, jid, nick, text):
	if len(text):
		try: mlen = int(text.split(' ')[1])
		except: mlen = juick_tag_post_limit
		try: mlim = int(text.split(' ')[2])
		except: mlim = juick_tag_post_size
		text = text.split(' ')[0]
		link = 'http://juick.com/last?tag='+text.encode('utf-8').replace('\\x','%').replace(' ','%20')
		body = urllib.urlopen(link).read()
		body = html_encode(body)
		if body.count('<p>Tag not found</p>') or body.count('<h1>Page Not Found</h1>'): msg = L('Tag %s not found') % text
		else:
			mes = body.split('<h2>Messages</h2>')[1].split('</div><div id="lcol"><h2>')[0].split('<li class="liav"')
			mesg = ''
			for us in mes[1:mlen+1]:
				mesg += '\nhttp://juick.com/'+get_tag(us.split('<big>')[1],'a')[1:]+'/'+get_tag(us.split('</div>')[1],'a')[1:]+' - '
				mm = rss_replace(rss_del_html(get_tag(us,'div')))
				if len(mm)<mlim: mesg += mm
				else: mesg += mm[:mlim]+'[...]'
				if us.split('</span>')[1].count('<a'): mesg += ' ('+get_tag(us,'span')+'|'+get_tag(us.split('</span>')[1],'a')+')'
				else: mesg += ' ('+get_tag(us,'span')+'|No replies)'
			msg = L('Tag %s found in %s') % (text, mesg)
	else: msg = L('What tag do you want to find?')
	send_msg(type, jid, nick, msg)

global execute

execute = [(3, 'juick', juick, 2, L('Miniblogs http://juick.com\njuick tag user <tag> [users count] - users, who use tags\njuick tag msg <tag> [messages_count_limit [message_lenght_limit]] - show messages with requsted tags\njuick msg <message_number> [count] - show message + count replies\njuick msg <message_number/reply_number> [count] - show message + reply\njuick user <username> [message_count_limit [message_lenght_limit]] - last user\'s messages\njuick info <username> - show user info'))]
