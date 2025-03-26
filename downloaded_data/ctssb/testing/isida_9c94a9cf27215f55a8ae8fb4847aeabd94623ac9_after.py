#!/usr/bin/python
# -*- coding: utf-8 -*-

def bash_org_ru(type, jid, nick, text):
	try: url = u'http://bash.org.ru/quote/'+str(int(text))
	except: url = u'http://bash.org.ru/random'
	body = html_encode(urllib.urlopen(url).read())
	if body.count('<div class="vote">') > 1 and url.count('quote'): msg = u'Цитата не найдена!'
	else:
		body = body.split('<div class="vote">')[1].split('<div class="q">')[0]
		msg = u'http://bash.org.ru/quote/'+str(get_tag(body, 'a'))+u' '+replacer(body[body.find('[:||||:]'):].replace('</div>', '\n').replace('[:||||:]', '::: ').replace('</a>\n', ''))
	send_msg(type, jid, nick, msg)

def ibash_org_ru(type, jid, nick, text):
	try: url = u'http://ibash.org.ru/quote.php?id='+str(int(text))
	except: url = u'http://ibash.org.ru/random.php'
	body = html_encode(urllib.urlopen(url).read())
	msg = u'http://ibash.org.ru/quote.php?id='+replacer(body.split('<div class="quothead"><span>')[1].split('</a></span>')[0])[1:]
	if msg[-3:] == '???': msg = u'Цитата не найдена!'
	else: msg += '\n'+replacer(body.split('<div class="quotbody">')[1].split('</div>')[0])
	send_msg(type, jid, nick, msg)

global execute

execute = [(0, u'bash', bash_org_ru, 2, u'Цитата с bash.org.ru\nbash [номер]'),
		   (0, u'ibash', ibash_org_ru, 2, u'Цитата с ibash.org.ru\nibash [номер]')]