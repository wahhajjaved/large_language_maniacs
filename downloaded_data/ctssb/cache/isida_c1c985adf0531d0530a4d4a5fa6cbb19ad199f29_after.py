# -*- coding: utf-8 -*-

global execute, lf_api, lfm_url, lfm_api

lfm_url = u'http://ws.audioscrobbler.com/2.0/'

def lf_api(method, user, splitter):
	user = user.lower()
	user = user.encode('utf-8')
	user = user.replace('\\x','%')
	user = user.replace(' ','%20')
	link = lfm_url + '?method=' + method + '&user=' + user + '&api_key='+lfm_api
	f = urllib.urlopen(link)
	lfxml = f.read()
	f.close()
	lfxml = html_encode(lfxml)
	lfxml = rss_replace(lfxml)
	lfxml = lfxml.split(splitter)
	return lfxml

def lasttracks(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.getrecenttracks',text, '<track')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Последние дорожки '+text+':'
	for a in ms[1:cnt]:
		msg += '\n ['+get_tag(a,'date')+'] '+get_tag(a,'artist')+u' – '+get_tag(a,'name')
        send_msg(type, jid, nick, msg)

def lastfriends(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.getfriends',text, '<user')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Друзья '+text+': '
	for a in ms[1:cnt]:
		msg += get_tag(a,'name')+' ('+get_tag(a,'realname')+u'), '
	msg = msg[:-2]
        send_msg(type, jid, nick, msg)

def lastloved(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.getlovedtracks',text, '<track')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Топ альбомов '+text+':'
	for a in ms[1:cnt]:
		b = a.split('<artist')
		msg += '\n ['+get_tag(a,'date')+'] '+get_tag(b[1],'name')+u' – '+get_tag(a,'name')
        send_msg(type, jid, nick, msg)

def lastneighbours(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.getneighbours',text, '<user')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Соседи '+text+':'
	for a in ms[1:cnt]:
		msg += '\n'+get_tag(a,'match')+u' – '+get_tag(a,'name')
        send_msg(type, jid, nick, msg)

def lastplaylist(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 2
	text = text[0]
	ms = lf_api('user.getplaylists',text, '<playlist')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Плейлисты '+text+':'
	for a in ms[2:cnt]:
		msg += '\n['+get_tag(a,'id')+'] '+get_tag(a,'title')+' ('+get_tag(a,'description')+u') – '+get_tag(a,'size')+u' – '+get_tag(a,'duration')
        send_msg(type, jid, nick, msg)

def topalbums(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.gettopalbums',text, '<album')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Топ альбомов '+text+':'
	for a in ms[1:cnt]:
		b = a.split('<artist')
		msg += '\n['+get_tag(a,'playcount')+'] '+get_tag(b[1],'name')+u' – '+get_tag(a,'name')
        send_msg(type, jid, nick, msg)

def topartists(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.gettopartists',text, '<artist')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Топ исполнителей '+text+':'
	for a in ms[1:cnt]:
		msg += '\n['+get_tag(a,'playcount')+'] '+get_tag(a,'name')
        send_msg(type, jid, nick, msg)

def toptags(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.gettoptags',text, '<tag')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Топ тегов '+text+':'
	for a in ms[1:cnt]:
		msg += '\n['+get_tag(a,'count')+'] '+get_tag(a,'name')+u' – '+get_tag(a,'url')
        send_msg(type, jid, nick, msg)

def toptracks(type, jid, nick, text):
	text = text.split(' ')
	try:
		cnt = int(text[1])
	except:
		cnt = 10
	cnt += 1
	text = text[0]
	ms = lf_api('user.gettoptracks',text, '<track')

	if cnt > len(ms):
		cnt = len(ms)
	msg = u'Топ треков '+text+':'
	for a in ms[1:cnt]:
		b = a.split('<artist')
		msg += '\n['+get_tag(a,'playcount')+'] '+get_tag(b[1],'name')+u' – '+get_tag(a,'name')
        send_msg(type, jid, nick, msg)

def tasteometer(type, jid, nick, text):
	text = text.lower()
	text = text.encode('utf-8')
	text = text.replace('\\x','%')
	text = text.split(' ')
	user1 = text[0]
	user2 = text[1]
	link = lfm_url + '?method=tasteometer.compare&type1=user&type2=user&value1=' + user1 + '&value2=' + user2 + '&api_key='+lfm_api
	f = urllib.urlopen(link)
	lfxml = f.read()
	f.close()
	lfxml = html_encode(lfxml)

	msg = u'Совместимость '+user1+u' и '+user2
	if get_tag(lfxml,'score') <= '0':
		msg += u' - нулевая!'
	else:
		msg += u' – '+get_tag(lfxml,'score') +u'\nСовпадение вкусов: '
		lfxml = lfxml.split('<artist')
		cnt = len(lfxml)
		for a in lfxml[2:cnt]:
			msg += get_tag(a,'name')+', '
		msg = msg[:-2]
        send_msg(type, jid, nick, msg)

def no_api(type, jid, nick):
        send_msg(type, jid, nick, u'Не найден файл LastFM.api')

apifile = 'plugins/LastFM.api'

exec_yes = [(0, u'lasttracks', lasttracks, 2),
	    (0, u'lastfriends', lastfriends, 2),
	    (0, u'lastloved', lastloved, 2),
	    (0, u'lastneighbours', lastneighbours, 2),
	    (0, u'lastplaylist', lastplaylist, 2),
	    (0, u'topalbums', topalbums, 2),
	    (0, u'topartists', topartists, 2),
	    (0, u'toptags', toptags, 2),
	    (0, u'toptracks', toptracks, 2),
	    (0, u'tasteometer', tasteometer, 2)]

exec_no = [(0, u'lasttracks', no_api, 1),
	   (0, u'lastfriends', no_api, 1),
	   (0, u'lastloved', no_api, 1),
	   (0, u'lastneighbours', no_api, 1),
	   (0, u'lastplaylist', no_api, 1),
	   (0, u'topalbums', no_api, 1),
	   (0, u'topartists', no_api, 1),
	   (0, u'toptags', no_api, 1),
	   (0, u'toptracks', no_api, 1),
	   (0, u'tasteometer', no_api, 1)]

if os.path.isfile(apifile):
	lfm_api = str(readfile(apifile))
	if len(lfm_api) == 33:
		execute = exec_yes
	else:
		execute = exec_no
else:
	execute = exec_no


