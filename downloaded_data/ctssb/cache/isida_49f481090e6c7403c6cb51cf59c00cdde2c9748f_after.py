#!/usr/bin/python
# -*- coding: utf -*-

def wiki_search(type, jid, nick,text):
	ntext = u'вики '+text+u' inurl:ru.wikipedia.org/wiki'
	query = urllib.urlencode({'q' : ntext.encode("utf-8")})
	url = u'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&%s'.encode("utf-8") % (query)
	search_results = urllib.urlopen(url)
	json = simplejson.loads(search_results.read())
	try:
		results = json['responseData']['results']
		title = results[0]['title']
		content = results[0]['content']
		noh_title = title.replace('<b>', u'').replace('</b>', u'')
		content = content.replace('<b>', u'').replace('</b>', u'')
		url = results[0]['unescapedUrl']
		msg = replacer(noh_title)+u'\n'+replacer(content)+u'\n'+url
	except: msg = u'Выражение \"' + text + u'\" не найдено!'
	send_msg(type, jid, nick, msg)

def xep_show(type, jid, nick,text):
	ntext = u'xep '+text+' inurl:xmpp.org'
	query = urllib.urlencode({'q' : ntext.encode("utf-8")})
	url = u'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&%s'.encode("utf-8") % (query)
	search_results = urllib.urlopen(url)
	json = simplejson.loads(search_results.read())
	try:
		results = json['responseData']['results']
		title = results[0]['title']
		content = results[0]['content']
		noh_title = title.replace('<b>', u'').replace('</b>', u'')
		content = content.replace('<b>', u'').replace('</b>', u'')
		url = results[0]['unescapedUrl']
		msg = replacer(noh_title)+u'\n'+replacer(content)+u'\n'+url
	except: msg = u'xep \"' + text + u'\" не найден!'
	send_msg(type, jid, nick, msg)

def google(type, jid, nick,text):
	query = urllib.urlencode({'q' : text.encode("utf-8")})
	url = u'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&%s'.encode("utf-8") % (query)
	search_results = urllib.urlopen(url)
	json = simplejson.loads(search_results.read())
	try:
		results = json['responseData']['results']
		title = results[0]['title']
		content = results[0]['content']
		noh_title = title.replace('<b>', u'«').replace('</b>', u'»')
		content = content.replace('<b>', u'«').replace('</b>', u'»')
		url = results[0]['unescapedUrl']
		msg = replacer(noh_title)+u'\n'+replacer(content)+u'\n'+url
	except: msg = u'Выражение \"' + text + u'\" - не найдено!'
	send_msg(type, jid, nick, msg)

def translate(type, jid, nick,text):
	trlang = {'sq':u'албанский','en':u'английский','ar':u'арабский','af':u'африкаанс',
			  'be':u'белорусский','bg':u'болгарский','cy':u'валлийский','hu':u'венгерский','vi':u'вьетнамский',
			  'gl':u'галисийский','nl':u'голландский','el':u'греческий','da':u'датский','iw':u'иврит','yi':u'идиш',
			  'id':u'индонезийский','ga':u'ирландский','is':u'исландский','es':u'испанский','it':u'итальянский',
			  'ca':u'каталанский','zh-CN':u'китайский','ko':u'корейский','lv':u'латышский','lt':u'литовский',
			  'mk':u'македонский','ms':u'малайский','mt':u'мальтийский','de':u'немецкий','no':u'норвежский',
			  'fa':u'персидский','pl':u'польский','pt':u'португальский','ro':u'румынский','ru':u'русский',
			  'sr':u'сербский','sk':u'словацкий','sl':u'словенский','sw':u'суахили','tl':u'тагальский',
			  'th':u'тайский','tr':u'турецкий','uk':u'украинский','fi':u'финский','fr':u'французский','hi':u'хинди',
			  'hr':u'хорватский','cs':u'чешский','sv':u'шведский','et':u'эстонский','ja':u'японский'}
	if text.lower() == 'list':
		msg = u'Доступные языки для перевода: '
		for tl in trlang: msg += tl+', '
		msg = msg[:-2]
	elif text[:4].lower() == 'info':
		text = text.split(' ')
		msg = u''
		for tmp in text:
			if tmp in trlang: msg += tmp+' - '+trlang[tmp]+', '
		if len(msg): msg = u'Извесные языки: '+msg[:-2]
		else: msg = u'Я не знаю таких языков'
	else:
		if text.count(' ') > 1:
			text = text.split(' ',2)
			if (text[0] in trlang) and (text[1] in trlang) and text[2] != '':
				query = urllib.urlencode({'q' : text[2].encode("utf-8"),'langpair':text[0]+'|'+text[1]})
				url = u'http://ajax.googleapis.com/ajax/services/language/translate?v=1.0&%s'.encode("utf-8") % (query)
				search_results = urllib.urlopen(url)
				json = simplejson.loads(search_results.read())
				msg = rss_replace(json['responseData']['translatedText'])
			else: msg = u'Неправильно указан язык или нет текста для перевода. tr list - доступные языки'
		else: msg = u'Формат команды: tr с_какого на_какой текст'
	send_msg(type, jid, nick, msg)

global execute

execute = [(0, u'tr', translate, 2, u'Переводчик.\ntr с_какого_языка на_какой_язык текст - перевод текста\ntr list - список языков для перевода\ntr info <сокращение> - расшифровка сокращения языка'),
	 (0, u'google', google, 2, u'Поиск через google'),
	 (0, u'xep', xep_show, 2, u'Поиск XEP'),
	 (0, u'wiki', wiki_search, 2, u'Поиск по Wikipedia')]
