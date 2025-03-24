#!/usr/bin/python
# -*- coding: utf-8 -*-

def kinopoisk(type, jid, nick, text):
	text=text.strip().split(' ', 1)
	if len(text) == 2 and not text[0] in ['id', 'search'] or len(text) == 1: text = [' ', ' '.join(text)]
	if text[0] == 'search' or text[0] == ' ' and not re.search('^\d+$', text[-1]):
		query=urllib.quote(text[-1].encode('cp1251'))
		data = html_encode(load_page('http://m.kinopoisk.ru/search/'+query))
		temp_urls = re.findall('<a href="/movie/(\d+?)/">(.+?)</a>', data)
		if temp_urls:
			msg = L('Found:')
			for t_u in temp_urls:
				msg += '\n%s - %s' % (t_u[0], t_u[1])
		else: msg = L('Not found!')
	elif re.search('^\d+$', text[-1]):
		data = html_encode(load_page('http://m.kinopoisk.ru/movie/'+text[-1]))
		tmp = unhtml_hard(re.search('<p class="title">((?:.|\s)+?)</div>', data).group(1)).split('\n')
		msg = '\n'.join([i[0].upper()+i[1:] for i in tmp])
	else: msg = L('What?')
	send_msg(type,jid,nick,msg)

global execute

execute = [(0, 'film', kinopoisk, 2, L('Search in www.kinopoisk.ru. Example:\nfilm [id] film_id\nfilm [search] film_name'))]
