# -*- coding: utf-8 -*-

def iq_uptime(type, jid, nick, text):
	global iq_answer
	if text == '':
		who = getRoom(jid)+'/'+nick
	else:
		who = text
		for mega1 in megabase:
			if mega1[0] == jid and mega1[1] == text:
				who = getRoom(jid)+'/'+text
				break

	iqid = str(randint(1,100000))
	i = Node('iq', {'id': iqid, 'type': 'get', 'to':who}, payload = [Node('query', {'xmlns': NS_LAST},[])])
	cl.send(i)
	to = timeout

	no_answ = 1
	is_answ = [None]
	while to >= 0 and no_answ:
		for aa in iq_answer:
			if aa[0]==iqid:
				is_answ = aa[1:]
				iq_answer.remove(aa)
				no_answ = 0
				break
		sleep(0.05)
		to -= 0.05

	iiqq = []
	for iiq in is_answ:
		if iiq != None:
			iiqq.append(iiq)
		else:
			iiqq.append('None')
	if to > 0:
		if iiqq == ['None']:
			msg = u'Что-то не получается...'
		else:
			try:
				msg = u'Аптайм: '+un_unix(int(iiqq[0].split('seconds="')[1].split('"')[0]))
			except:
				msg = u'Что-то не получается...'

	else:
		msg = u'Истекло время ожидания ('+str(timeout)+u'сек).'
        send_msg(type, jid, nick, msg)

def censor_status(type, jid, nick, text):
	tmode = 0
	if text:
		if text.lower() == 'on':
			tmode = 2
		elif text.lower() == 'off':
			tmode = 1

	gl_censor = getFile(cns,[(getRoom(jid),0)])
	msg = u'Censor is '
	is_found = 1
	for sm in gl_censor:
		if sm[0] == getRoom(jid):
			if tmode:
				tsm = (sm[0],tmode-1)
			else:
				tsm = (sm[0],int(not sm[1]))
			gl_censor.remove(sm)
			gl_censor.append(tsm)
			is_found = 0
			ssta = tsm[1]
	if is_found:
		gl_censor.append((getRoom(jid),1))
		ssta = 1
	msg += onoff(ssta)
	writefile(cns,str(gl_censor))
        send_msg(type, jid, nick, msg)

def status(type, jid, nick, text):
	if text == '':
		text = nick
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	stat = cu.execute('select message,status from age where nick=? and room=?',(text,jid)).fetchone()
	stat2 = cu.execute('select message,status from age where jid=? and room=?',('<temporary>'+text.lower()+'@',jid)).fetchone()

	if stat2:
		stat = stat2
	if stat:
		if stat[1]:
			msg = u'покинул данную конференцию.'
		else:
			stat = stat[0].split('\n',4)
	
			if stat[3] != 'None':
				msg = stat[3]
			else:
				msg = 'online'

			if stat[4] != 'None':
				msg += ' ('+stat[4]+')'
			if stat[2] != 'None':
				msg += ' ['+stat[2]+'] '
			else:
				msg += ' [0] '
			if stat[0] != 'None' and stat[1] != 'None':
				msg += stat[0]+'/'+stat[1]

		if text != nick:
			msg = text + ' - '+msg
	else:
		msg = u'Не найдено!'
        send_msg(type, jid, nick, msg)

def get_tld(type, jid, nick, text):
	if len(text) >= 2:
		tld = readfile('tld/tld.list').decode('utf-8')
		tld = tld.split('\n')
		msg = u'Не найдено!'
		for tl in tld:
			if tl.split('\t')[0]==text:
				msg = '.'+tl.replace('\t',' - ',1).replace('\t','\n')
				break
	else:
		msg = u'Что искать то будем?'
        send_msg(type, jid, nick, msg)

nmbrs = ['0','1','2','3','4','5','6','7','8','9','.']

def get_dns(type, jid, nick, text):
	is_ip = 0
	if text.count('.') == 3:
		is_ip = 1
		for ii in text:
			if not nmbrs.count(ii):
				is_ip = 0
				break
	if is_ip:
		try:
			msg = socket.gethostbyaddr(text)[0]

		except:
			msg = u'Не резолвится'
	else:
		try:
			ans = socket.gethostbyname_ex(text)[2]
			msg = text+' - '
			for an in ans:
				msg += an + ' | '
			msg = msg[:-2]
		except:
			msg = u'Не резолвится'
        send_msg(type, jid, nick, msg)

def ping(type, jid, nick, text):
	global iq_answer
	if text == '':
		sping = 1
		who = getRoom(jid)+'/'+nick
	else:
		sping = 0
		who = text
		for mega1 in megabase:
			if mega1[0] == jid and mega1[1] == text:
				who = getRoom(jid)+'/'+text
				break

	iqid = str(randint(1,100000))
	i = Node('iq', {'id': iqid, 'type': 'get', 'to':who}, payload = [Node('query', {'xmlns': NS_VERSION},[])])
	cl.send(i)
	to = timeout

	lt = time.time()

	no_answ = 1
	is_answ = [None]
	while to >= 0 and no_answ:
		for aa in iq_answer:
			if aa[0]==iqid:
				is_answ = aa[1:]
				iq_answer.remove(aa)
				no_answ = 0
				break
		sleep(0.001)
		to -= 0.001

	ct = time.time()

	iiqq = []
	for iiq in is_answ:
		if iiq != None:
			iiqq.append(iiq)
		else:
			iiqq.append('None')
	if to > 0:
		if iiqq == ['None']:
			msg = u'Что-то не получается...'
		else:
			tpi = ct-lt
			tpi = str(int(tpi))+'.'+str(int((tpi-int(tpi))*10000))

			if sping:
				msg = u'Пинг от тебя '+tpi+u' сек.'
			else:
				msg = u'Пинг от '+text+' '+tpi+u' сек.'
	else:
		msg = u'Истекло время ожидания ('+str(timeout)+u'сек).'
        send_msg(type, jid, nick, msg)

def replacer(msg):
	msg = rss_replace(msg)
	msg = rss_del_html(msg)
	msg = rss_replace(msg)
	msg = rss_del_nn(msg)
	return msg

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
		msg = replacer(noh_title)+replacer(content)+url
	except:
		msg = u'Выражение "' + text + u'" - не найдено!'
        send_msg(type, jid, nick, msg)

def translate(type, jid, nick,text):
	trlang = ['sq','ar','bg','ca','zh-CN','zh-TW','hr','cs','da',
		  'nl','en','et','tl','fi','fr','gl','de','el','iw',
		  'hi','hu','id','it','ja','ko','lv','lt','mt','no',
		  'pl','pt','ro','ru','sr','sk','sl','es','sv','th','tr','uk','vi']
	if text.lower() == 'list':
		msg = u'Доступные языки для перевода: '
		for tl in trlang:
			msg += tl+', '
		msg = msg[:-2]
	else:
		if text.count(' ') > 1:
			text = text.split(' ',2)
			if trlang.count(text[0]) and trlang.count(text[1]) and text[2] != '':
				query = urllib.urlencode({'q' : text[2].encode("utf-8"),'langpair':text[0]+'|'+text[1]})
				url = u'http://ajax.googleapis.com/ajax/services/language/translate?v=1.0&%s'.encode("utf-8") % (query)
				search_results = urllib.urlopen(url)
				json = simplejson.loads(search_results.read())
				msg = json['responseData']['translatedText']
			else:
				msg = u'Неправильно указан язык или нет текста для перевода. tr list - доступные языки'
		else:
			msg = u'Формат команды: tr с_какого на_какой текст'
        send_msg(type, jid, nick, msg)


def svn_get(type, jid, nick,text):
	tlog = 'tempo.log'
	if text[:7] !='http://' and text[:8] !='https://':
                text = 'http://'+text
	count = 1
	revn = 0
	if text.count(' '):
		text = text.split(' ')
		url = text[0]
		try:
			count = int(text[1])
		except:
			try:
				if text[1][0].lower()=='r':
					revn = int(text[1][1:])
			except:
				revn = 0
	else:
		url=text
	if os.path.isfile(tlog):
		os.system('rm -r '+tlog)

	if revn:
		os.system('svn log '+url+' -r'+str(revn)+' > '+tlog)
	else:
		if count > 10:
			count = 10
		os.system('svn log '+url+' --limit '+str(count)+' > '+tlog)
	try:
		result = readfile(tlog).decode('utf-8')
	except:
		result = ''

	if len(result):
		msg = u'last svn update: '+url+'\n'+result
	else:
		msg = url+u' - недоступно!'
        send_msg(type, jid, nick, msg)

def sayto(type, jid, nick, text):
	if text.count(' '):
		to = text[:text.find(' ')]
		what = text[text.find(' ')+1:]
		frm = nick + '\n' + str(int(time.time()))
		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		fnd = cu.execute('select * from age where room=? and (nick=? or jid=?)',(jid,to,to)).fetchall()
		if len(fnd) == 1:
			fnd = fnd[0]
			if fnd[5]:
				msg = u'Передам'
				sdb = sqlite3.connect(saytobase)
				cu = sdb.cursor()
				cu.execute('insert into st values (?,?,?,?)', (frm, jid, fnd[2], what))
				sdb.commit()
			else:
				msg = u'Или я дура, или '+to+u' находится тут...'
		elif len(fnd) > 1:
			msg = u'Я видела несколько человек с таким ником. Укажите точнее!'
		else:
			msg = u'Я не в курсе кто такой '+to+u'. Могу не правильно передать.'
			sdb = sqlite3.connect(saytobase)
			cu = sdb.cursor()
			cu.execute('insert into st values (?,?,?,?)', (frm, jid, to, what))
			sdb.commit()
	else:
		msg = u'Кому что передать?'
        send_msg(type, jid, nick, msg)

def getMucItems(jid,affil,ns):
	global banbase,raw_iq
	iqid = str(randint(1,100000))
	banbase = []
	raw_iq = []
	if ns == NS_MUC_ADMIN:
		i = Node('iq', {'id': iqid, 'type': 'get', 'to':getRoom(jid)}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':affil})])])
	else:
		i = Node('iq', {'id': iqid, 'type': 'get', 'to':getRoom(jid)}, payload = [Node('query', {'xmlns': ns},[])])
	cl.send(i)
	while banbase == []:
	 	sleep(0.5)
	while banbase[-1] != (u'TheEnd', u'None'):
		sleep(0.1)
	banbase = banbase[:-1]
	return (banbase,raw_iq)

def conf_backup(type, jid, nick, text):
	global banbase
	if len(text):
		text = text.split(' ')
		mode = text[0]

		if mode == u'show':
			a = os.listdir(back_folder)
			b = []
			for c in a:
				if c.count('conference'):
					b.append((c,os.path.getmtime(back_folder+c)))
			if len(b):
				msg = u'Резервные копии: '
				for c in b:
					msg += c[0]+' ('+un_unix(time.time()-c[1])+')'+', '
				msg = msg[:-2]
			else:
				msg = u'Резервных копий не найдено!'
		if mode == u'now':
			tmppos = arr_semi_find(confbase, jid)
			if tmppos == -1:
				nowname = nickname
			else:
				nowname = getResourse(confbase[tmppos])
				if nowname == '':
					nowname = nickname
			xtype = ''
        	        for base in megabase:
        	                if base[0].lower() == jid and base[1] == nowname:
					xtype = base[3]
					break
			if xtype != 'owner':
				msg = u'Для резервного копирования мне нужны права владельца конференции!'

			else:
				ns = NS_MUC_ADMIN
				banlist = getMucItems(jid,'outcast',ns)
				memberlist = getMucItems(jid,'member',ns)
				adminlist = getMucItems(jid,'admin',ns)
				ownerlist = getMucItems(jid,'owner',ns)
				configlist = getMucItems(jid,'',NS_MUC_OWNER)
				iqid = str(randint(1,100000))
				i = Node('iq', {'id': iqid, 'type': 'set', 'to':jid}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'admin', 'jid':getRoom(str(selfjid))},[])])])
				cl.send(i)

				msg = u'Копирование завершено!'
				msg += u'\nВладельцев:\t'+str(len(ownerlist[0]))
				msg += u'\nАдминов:\t'+str(len(adminlist[0]))
				msg += u'\nУчастников:\t'+str(len(memberlist[0]))
				msg += u'\nЗабаненных:\t'+str(len(banlist[0]))

				raw_back = []
				raw_back.append(ownerlist[1][1])
				raw_back.append(adminlist[1][1])
				raw_back.append(memberlist[1][1])
				raw_back.append(banlist[1][1])
				raw_back.append(configlist[1][1])
				writefile(back_folder+unicode(jid),str(raw_back))

		if mode == u'restore':
			if len(text)>1:
				a = os.listdir(back_folder)
				a = a.count(text[1])

				if a:
					tmppos = arr_semi_find(confbase, jid)
					if tmppos == -1:
						nowname = nickname
					else:
						nowname = getResourse(confbase[tmppos])
						if nowname == '':
							nowname = nickname
					xtype = ''
        			        for base in megabase:
        			                if base[0].lower() == jid and base[1] == nowname:
							xtype = base[3]
							break
					if xtype != 'owner':
						msg = u'Для восстановления резервной копии мне нужны права владельца конференции!'
	
					else:
						raw_back=eval(readfile(back_folder+unicode(text[1])))

						for zz in range(0,4):
							iqid = str(randint(1,100000))
							end = raw_back[zz][raw_back[zz].find('<query'):]
							beg = '<iq xmlns="jabber:client" to="'+str(jid)+'" from="'+str(selfjid)+'" id="'+str(iqid)+'" type="set">'
							cl.send(beg+end)
						iqid = str(randint(1,100000))
						end = raw_back[4][raw_back[4].find('<query'):]
						beg = '<iq to="'+str(jid)+'" id="'+str(iqid)+'" type="set">'
						i = beg+end
						ci = i.count('label="')
						for ii in range(0,ci):
							i = i[:i.find('label="')-1]+i[i.find('"',i.find('label="')+8)+1:]
						i = i[:i.find('<instructions>')]+i[i.find('</instructions>',i.find('<instructions>')+14)+15:]
						i = i[:i.find('<title>')]+i[i.find('</title>',i.find('<title>')+7)+8:]
						i = i.replace('form','submit')
						cl.send(i)
						iqid = str(randint(1,100000))
						i = Node('iq', {'id': iqid, 'type': 'set', 'to':jid}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'admin', 'jid':getRoom(str(selfjid))},[])])])
					cl.send(i)
					msg = u'Восстановление завершено!'
				else:
					msg = u'Резервная копия не найдена. Просмотрите список используя ключ show'
			else:
				msg = u'Что будем восстанавливать?'
	else:
		msg = u'backup now|show|restore'
        send_msg(type, jid, nick, msg)

def disco(type, jid, nick, text):
        text = text.lower().split(' ')
        where = text[0]
	try:
		what = text[1]
	except:
		what = ''
	try:
		hm = int(text[2])
	except:
		hm = 10

	iqid = str(randint(1,100000))
	i = Node('iq', {'id': iqid, 'type': 'get', 'to':where}, payload = [Node('query', {'xmlns': NS_DISCO_ITEMS},[])])
	cl.send(i)
	to = timeout

	no_answ = 1
	while to >= 0 and no_answ:
		for aa in iq_answer:
			if aa[0]==iqid:
				is_answ = aa[1:]
				iq_answer.remove(aa)
				no_answ = 0
				break
		sleep(0.5)
		to -= 0.5

        if not no_answ:
		if where.count('conference') and not where.count('@'):
			tmp = sqlite3.connect(':memory:')
			cu = tmp.cursor()
			cu.execute('''create table tempo (nick text, room text, size text)''')
			isa = is_answ[0].split('<item ')
			for ii in isa[1:]:
				dname = get_subtag(ii,'name')
				djid = get_subtag(ii,'jid')
				dpos = 1
				for zzz in range(0,dname.count('(')):
					dpos = dname.find('(',dpos+1)
				dsize = dname[dpos+1:dname.find(')',dpos+1)]
				dname = dname[:-(len(dsize)+3)]
				cu.execute('insert into tempo values (?,?,?)', (dname, djid, dsize))
			if len(what):
				cm = cu.execute('select * from tempo where (nick like ? or room like ?) order by -size',('%'+what+'%','%'+what+'%')).fetchmany(hm)
			else:
				cm = cu.execute('select * from tempo order by -size').fetchmany(hm)
			if len(cm):
				cnt = 1
				msg = u'Всего: '+str(len(cm))
				for i in cm:
					msg += u'\n'+str(cnt)+u'. '+i[0]+u' ['+i[1]+u'] . '+i[2]
					cnt += 1
			else:
				msg = u'\"'+what+u'\" не найдено!'
			tmp.close()
		elif where.count('conference') and where.count('@'):
			tmp = sqlite3.connect(':memory:')
			cu = tmp.cursor()
			cu.execute('''create table tempo (nick text)''')
			isa = is_answ[0].split('<item ')
			for ii in isa[1:]:
				dname = get_subtag(ii,'name')
				cu.execute('insert into tempo values (?)', (dname,))
			if len(what):
				cm = cu.execute('select * from tempo where (nick like ?) order by nick',('%'+what+'%',)).fetchmany(hm)
			else:
				cm = cu.execute('select * from tempo order by nick').fetchmany(hm)
			if len(cm):
				msg = u'Всего: '+str(len(cm))+' - '
				for i in cm:
					msg += i[0]+u', '
				msg = msg[:-2]
			else:
				msg = u'\"'+what+u'\" не найдено!'
			tmp.close()
		else:
			tmp = sqlite3.connect(':memory:')
			cu = tmp.cursor()
			cu.execute('''create table tempo (jid text)''')
			isa = is_answ[0].split('<item ')
			for ii in isa[1:]:
				djid = get_subtag(ii,'jid')
				cu.execute('insert into tempo values (?)', (djid,))
			cm = cu.execute('select * from tempo order by jid').fetchall()
			if len(cm):
				cnt = 1
				msg = u'Всего: '+str(len(cm))
				for i in cm:
					msg += '\n'+str(cnt)+'. '+i[0]
					cnt += 1
			else:
				msg = 'не найдено!'
			tmp.close()
	else:
		msg = u'Не получается...'
	msg = rss_replace(msg)
        send_msg(type, jid, nick, msg)

def whereis(type, jid, nick, text):
	if len(text):
	        text = text.split(' ')
        	who = text[0]
	else:
		who = nick
	if len(text)<2:
		where = getServer(jid)
	else:
		if text[1].count('conference'):
		        where = text[1]
		else:
		        where = 'conference.'+text[1]
	iqid = str(randint(1,100000))
	i = Node('iq', {'id': iqid, 'type': 'get', 'to':where}, payload = [Node('query', {'xmlns': NS_DISCO_ITEMS},[])])
	cl.send(i)
	to = timeout

	no_answ = 1
	while to >= 0 and no_answ:
		for aa in iq_answer:
			if aa[0]==iqid:
				is_answ = aa[1:]
				iq_answer.remove(aa)
				no_answ = 0
				break
		sleep(0.5)
		to -= 0.5

        if not no_answ:
		tmp = sqlite3.connect(':memory:')
		cu = tmp.cursor()
		cu.execute('''create table tempo (nick text, room text)''')

		isa = is_answ[0].split('<item ')
		djids = []
		for ii in isa[1:]:
			dname = get_subtag(ii,'name')
			if dname[-5:] != '(n/a)' and dname[-3:] != '(0)':
				djids.append(get_subtag(ii,'jid'))

	        send_msg(type, jid, nick, u'Ожидайте, результат Вы получите в приват примерно через '+str(int(len(djids)/6))+u' сек.')

		for ii in djids:
			iqid = str(randint(1,100000))
			i = Node('iq', {'id': iqid, 'type': 'get', 'to':ii}, payload = [Node('query', {'xmlns': NS_DISCO_ITEMS},[])])
			cl.send(i)
			to = 500

			no_answ = 1
			while to >= 0 and no_answ:
				for aa in iq_answer:
					if aa[0]==iqid:
						is_answ = aa[1:]
						iq_answer.remove(aa)
						no_answ = 0
						break
				sleep(0.01)
				to -= 0.01

		        if not no_answ:
				isd = is_answ[0].split('<item ')
				for iii in isd[1:]:
					dname = get_subtag(iii,'name')
					if dname.lower().count(who.lower()):
						cu.execute('insert into tempo values (?,?)', (dname, getRoom(get_subtag(iii,'jid'))))

		cm = cu.execute('select * from tempo order by nick,room').fetchall()
		if len(cm):
			msgg = u', Совпадений с ником \"'+who+u'\": '+str(len(cm))
			for i in cm:
				msgg += '\n'+i[0]+'\t'+i[1]
		else:
			msgg = u', ник \"'+who+u'\" не найден!'

		msg = u'Всего конференций: '+str(len(isa)-1)+u', доступно: '+str(len(djids))+msgg
		tmp.close()		
	else:
		msg = u'Не получается...'
        send_msg('chat', jid, nick, msg)

ul = 'update.log'
def svn_info(type, jid, nick):
	if os.path.isfile(ul):
		msg = u'Последнее обновление:\n'+readfile(ul).decode('utf-8')
	else:
		msg = u'Файл '+ul+u' не доступен!'
        send_msg(type, jid, nick, msg)

def iq_time(type, jid, nick, text):
	global iq_answer
	if text == '':
		who = getRoom(jid)+'/'+nick
	else:
		who = text
		for mega1 in megabase:
			if mega1[0] == jid and mega1[1] == text:
				who = getRoom(jid)+'/'+text
				break

	iqid = str(randint(1,100000))
	i = Node('iq', {'id': iqid, 'type': 'get', 'to':who}, payload = [Node('query', {'xmlns': NS_TIME},[])])
	cl.send(i)
	to = timeout

	no_answ = 1
	is_answ = [None]
	while to >= 0 and no_answ:
		for aa in iq_answer:
			if aa[0]==iqid:
				is_answ = aa[1:]
				iq_answer.remove(aa)
				no_answ = 0
				break
		sleep(0.5)
		to -= 0.5

	iiqq = []
	for iiq in is_answ:
		if iiq != None:
			iiqq.append(iiq)
		else:
			iiqq.append('None')
	if to > 0:
		if len(iiqq) == 3:
			msg = iiqq[0]+' (Raw time: '+iiqq[1]+' | TimeZone: '+iiqq[2]+')'
		else:
			msg = ''
			for iiq in iiqq:
				msg = iiq+' '
	else:
		msg = u'Истекло время ожидания ('+str(timeout)+u'сек).'
        send_msg(type, jid, nick, msg)

def iq_version(type, jid, nick, text):
	global iq_answer
	if text == '':
		who = getRoom(jid)+'/'+nick
	else:
		who = text
		for mega1 in megabase:
			if mega1[0] == jid and mega1[1] == text:
				who = getRoom(jid)+'/'+text
				break

	iqid = str(randint(1,100000))
	i = Node('iq', {'id': iqid, 'type': 'get', 'to':who}, payload = [Node('query', {'xmlns': NS_VERSION},[])])
	cl.send(i)
	to = timeout

	no_answ = 1
	is_answ = [None]
	while to >= 0 and no_answ:
		for aa in iq_answer:
			if aa[0]==iqid:
				is_answ = aa[1:]
				iq_answer.remove(aa)
				no_answ = 0
				break
		sleep(0.5)
		to -= 0.5

	iiqq = []
	for iiq in is_answ:
		if iiq != None:
			iiqq.append(iiq)
		else:
			iiqq.append('None')
	if to > 0:
		if len(iiqq) == 3:
			msg = iiqq[0]+' '+iiqq[1]+' // '+iiqq[2]
		else:
			msg = ''
			for iiq in iiqq:
				msg = iiq+' '
	else:
		msg = u'Истекло время ожидания ('+str(timeout)+u'сек).'
        send_msg(type, jid, nick, msg)

def netwww(type, jid, nick, text):
	text = text.encode('utf-8')
	text = text.replace('\\x','%')
	text = text.replace(' ','%20')
	if text[:7] !='http://':
                text = 'http://'+text
	f = urllib.urlopen(text)
	page = f.read()
	f.close()

#	print page
	page = html_encode(page)
	msg = get_tag(page,'title')+'\n'

	for a in range(0,page.count('<style')):
		ttag = get_tag_full(page,'style')
		page = page.replace(ttag,'')

	for a in range(0,page.count('<script')):
		ttag = get_tag_full(page,'script')
		page = page.replace(ttag,'')

	page = rss_replace(page)
	page = rss_repl_html(page)
	page = rss_replace(page)
	page = rss_del_nn(page)
	page = page.replace('\n ','')

	msg += page

	send_msg(type, jid, nick, msg)

def seen(type, jid, nick, text):
        while text[-1:] == ' ':
                text = text[:-1]
        
	text = text.split(' ')
	llim = 10
	if len(text)>=2:
		try:
			llim = int(text[0])
		except:
			llim = 10

		text = text[1]
	else:
		text = text[0]

	if llim > 100:
		llim = 100
	if text == '':
		text = nick
	is_found = 0
	ms = []
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	cu.execute('select * from age order by room')
	for aa in cu:
		if aa[0]==jid and (aa[1].lower().count(text.lower()) or aa[2].lower().count(text.lower())):
			if aa[5]:
				r_age = aa[4]
				r_was = int(time.time())-aa[3]
			else:
				r_age = int(time.time())-aa[3]
				r_was = 0
			ms.append((aa[1],r_age,r_was,aa[6],aa[7]))
			is_found = 1
	if is_found:
		lms = len(ms)
		for i in range(0,lms-1):
			for j in range(i,lms):
				if ms[i][1] < ms[j][1]:
					jj = ms[i]
					ms[i] = ms[j]
					ms[j] = jj
		if lms > llim:
			lms = llim
		if lms == 1 and nick == text:
			msg = u'Я тебя вижу!!!'
		else:
			msg = u'Я видела:'
			cnt = 1
			for i in range(0,lms):
				msg += '\n'+str(cnt)+'. '+ms[i][0]
				if ms[i][2]:
					if ms[i][3] != '':
						msg += u'\t'+ms[i][3]+' '+un_unix(ms[i][2])+u' назад'
					else:
						msg += u'\tВышел '+un_unix(ms[i][2])+u' назад'
					if ms[i][4] != '':
						if ms[i][4].count('\n') >= 4:
							stat = ms[i][4].split('\n',4)[4]
							if stat != '':
								msg += ' ('+stat+')'
						else:
							msg += ' ('+ms[i][4]+')'
				else:
					msg += u'\tнаходится тут: '+un_unix(ms[i][1])
				cnt += 1
	else:
		msg = u'Не найдено!'

        send_msg(type, jid, nick, msg)

def seenjid(type, jid, nick, text):
        while text[-1:] == ' ':
                text = text[:-1]
        
	text = text.split(' ')
	llim = 10
	if len(text)>=2:
		try:
			llim = int(text[0])
		except:
			llim = 10

		text = text[1]
	else:
		text = text[0]

	if llim > 100:
		llim = 100
	if text == '':
		text = nick
	is_found = 0
	ms = []
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	cu.execute('select * from age order by room')
	for aa in cu:
		if aa[0]==jid and (aa[1].lower().count(text.lower()) or aa[2].lower().count(text.lower())):
			if aa[5]:
				r_age = aa[4]
				r_was = int(time.time())-aa[3]
			else:
				r_age = int(time.time())-aa[3]
				r_was = 0
			ms.append((aa[1],r_age,r_was,aa[6],aa[7],aa[2]))
			is_found = 1
	if is_found:
		lms = len(ms)
		for i in range(0,lms-1):
			for j in range(i,lms):
				if ms[i][1] < ms[j][1]:
					jj = ms[i]
					ms[i] = ms[j]
					ms[j] = jj
		if lms > llim:
			lms = llim
		if lms == 1 and nick == text:
			msg = u'Я тебя вижу!!!'
		else:
			msg = u'Я видела:'
			cnt = 1
			for i in range(0,lms):
				msg += '\n'+str(cnt)+'. '+ms[i][0]+' ('+ms[i][5]+')'
				if ms[i][2]:
					if ms[i][3] != '':
						msg += u'\t'+ms[i][3]+' '+un_unix(ms[i][2])+u' назад'
					else:
						msg += u'\tВышел '+un_unix(ms[i][2])+u' назад'
					if ms[i][4] != '':
						msg += ' ('+ms[i][4]+')'
				else:
					msg += u'\tнаходится тут: '+un_unix(ms[i][1])
				cnt += 1
	else:
		msg = u'Не найдено!'

        send_msg('chat', jid, nick, msg)

def alias(type, jid, nick, text):
	global aliases
	aliases = getFile(alfile,[])
	gs = text.find(' ')
	if gs >= 0:
		mode = text[:gs]
		text = text[gs+1:]
		gs = text.find('=')
		if gs >= 0:
			cmd = text[:gs]
			cbody = text[gs+1:]
		else:
			cmd = text
			cbody = ''
	else:
		mode = text
		cmd = ''
		cbody = ''

	msg = u'Режим '+mode+u' не опознан!'

	if mode=='add':
		fl = 0
		for i in aliases:
			if i[1] == cmd and i[0] == jid:
				aliases.remove(i)
				fl = 1	
		aliases.append([jid, cmd, cbody])
		if fl:
			msg = u'Обновлено:'
		else:
			msg = u'Добавлено:'
		msg += u' '+cmd+u' == '+cbody

	if mode=='del':
		msg = u'Не возможно удалить '+cmd
		for i in aliases:
			if i[1] == cmd and i[0] == jid:
				aliases.remove(i)
				msg = u'Удалено: '+cmd

	if mode=='show':
		if cmd == '':
			msg = u'Сокращения: '
			isf = 1
			for i in aliases:
				if i[0] == jid:
					msg += i[1] + ', '
					isf = 0
			if isf:
				msg+=u'не найдены'
			else:
				msg = msg[:-2]
		else:
			msg = cmd
			isf = 1
			for i in aliases:
				if i[1].lower().count(cmd.lower()) and i[0] == jid:
					msg += '\n'+i[1]+' = '+i[2]
					isf = 0
			if isf:
				msg+=u' не найдено'
	
	writefile(alfile,str(aliases))
        send_msg(type, jid, nick, msg)

##########################

def inowner(type, jid, nick, text):
	global banbase
	banbase = []
	i = Node('iq', {'id': randint(1,1000), 'type': 'get', 'to':getRoom(jid)}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'owner'})])])
	cl.send(i)
	while banbase == []:
		sleep(0.5)
	while banbase[-1] != (u'TheEnd', u'None'):
		sleep(0.1)

	banbase = banbase[:-1]
	msg = u'Всего владельцев: '+str(len(banbase))
	if text != '':
		mmsg = u', найдено:\n'
		fnd = 1
		cnt = 1
		for i in banbase:
			if i[0].lower().count(text.lower()) or i[1].lower().count(text.lower()):
				mmsg += str(cnt)+'. '+i[0]+'\n'
				fnd = 0
				cnt += 1
		mmsg = mmsg[:-1]
		if fnd:
			mmsg = u', совпадений нет!'
		msg += mmsg
	banbase = []
        send_msg(type, jid, nick, msg)

def inadmin(type, jid, nick, text):
	global banbase
	banbase = []
	i = Node('iq', {'id': randint(1,1000), 'type': 'get', 'to':getRoom(jid)}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'admin'})])])
	cl.send(i)
	while banbase == []:
		sleep(0.5)
	while banbase[-1] != (u'TheEnd', u'None'):
		sleep(0.1)

	banbase = banbase[:-1]
	msg = u'Всего админов: '+str(len(banbase))
	if text != '':
		mmsg = u', найдено:\n'
		fnd = 1
		cnt = 1
		for i in banbase:
			if i[0].lower().count(text.lower()) or i[1].lower().count(text.lower()):
				mmsg += str(cnt)+'. '+i[0]+'\n'
				fnd = 0
				cnt += 1
		if fnd:
			mmsg = u', совпадений нет!'
		msg += mmsg
	banbase = []
        send_msg(type, jid, nick, msg)

def inmember(type, jid, nick, text):
	global banbase
	banbase = []
	i = Node('iq', {'id': randint(1,1000), 'type': 'get', 'to':getRoom(jid)}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'member'})])])
	cl.send(i)
	while banbase == []:
		sleep(0.5)
	while banbase[-1] != (u'TheEnd', u'None'):
		sleep(0.1)

	banbase = banbase[:-1]
	msg = u'Всего мемберов: '+str(len(banbase))
	if text != '':
		mmsg = u', найдено:\n'
		fnd = 1
		cnt = 1
		for i in banbase:
			if i[0].lower().count(text.lower()) or i[1].lower().count(text.lower()):
				mmsg += str(cnt)+'. '+i[0]+'\n'
				fnd = 0
				cnt += 1
		mmsg = mmsg[:-1]
		if fnd:
			mmsg = u', совпадений нет!'
		msg += mmsg
	banbase = []
        send_msg(type, jid, nick, msg)


def fspace(mass):
	bdd = []
	for b in mass:
		if len(b) and len(b) != b.count(' '):
			while b[0] == ' ':
				b = b[1:]
		bdd.append(b)
	return bdd

def weather_gis(type, jid, nick, text):
	city_code = None
	if text == '':
		msg = u'gis город|код города'
	else:
		try:
			city_code = str(int(text))
		except:
			ft = ''
			for tex in text:
				if ord(tex) == 32:
					ft += '%20'
				elif ord(tex)<127:
					ft += tex
				else:
					ft += hex(ord(tex.upper())-1040+192).replace('0x','%').upper()
			link = 'http://wap.gismeteo.ru/gm/normal/node/search_result/6/?like_field_sname='+ft
			f = urllib.urlopen(link)
			body = f.read()
			f.close()
			body = unicode(body.split('<br>')[1],'utf-8').split('field_index=')[1:]
			giss = []
			for tmp in body:
				giss.append((tmp.split('&')[0],tmp.split('gen_past_date_0">')[1].split('</a>')[0]))
			if len(giss) == 1:
				city_code = giss[0][0]
			elif len(giss) == 0:
				msg = u'Город '+text+u' не найден!'
			else:
				msg = u'Найдено больше одного города! Воспользуйтесь командой gis код_города'
				for tmp in giss:
					msg += u'\n'+tmp[0]+u' — '+tmp[1]
	if city_code:
		link = 'http://wap.gismeteo.ru/gm/normal/node/prognoz_type/6/?field_wmo='+city_code+'&field_index='+city_code+'&sd_field_date=gen_past_date_0&ed_field_date=gen_past_date_0'
		f = urllib.urlopen(link)
		body = f.read()
		f.close()
		body = html_encode(body)
		body = replacer(body)
		body = body.split('#006cb7')[3]
		body = body.replace(u',  м/с',u' ')
		body = body.replace(u'безветрие',u'штиль')
		b = body.split('\n')
		if len(b) == 69:
			b.insert(5,'')
		if len(b[5]):
			msg = b[6]+', '+b[5]+', '+b[4]+' ('+b[1]+')'
		else:
			msg = b[6]+', '+b[4]+' ('+b[1]+')'
		msg += u'\n\tt°C\tДавл.\tВлажн.\tВетер'
		ms = ['']
		ms.append(u'\nНочь:\t'+b[12]+'\t'+b[14]+'\t'+b[16]+'\t'+b[18]+b[19]+'\t'+b[10]+', '+b[11])
		ms.append(u'\nУтро:\t'+b[22]+'\t'+b[24]+'\t'+b[26]+'\t'+b[28]+b[29]+'\t'+b[20]+', '+b[21])
		ms.append(u'\nДень:\t'+b[32]+'\t'+b[34]+'\t'+b[36]+'\t'+b[38]+b[39]+'\t'+b[30]+', '+b[31])
		ms.append(u'\nВечер:\t'+b[42]+'\t'+b[44]+'\t'+b[46]+'\t'+b[48]+b[49]+'\t'+b[40]+', '+b[41])

		link = 'http://wap.gismeteo.ru/gm/normal/node/prognoz_tomorrow/6/?field_wmo='+city_code+'&field_index='+city_code+'&sd_field_date=gen_past_date_-1&ed_field_date=gen_past_date_-1'
		f = urllib.urlopen(link)
		body = f.read()
		f.close()
		body = html_encode(body)
		body = replacer(body)
		body = body.split('#006cb7')[3]
		body = body.replace(u',  м/с',u' ')
		body = body.replace(u'безветрие',u'штиль')
		b = body.split('\n')
		if len(b) == 69:
			b.insert(5,' ')
		ms.append(u'\nНочь:\t'+b[12]+'\t'+b[14]+'\t'+b[16]+'\t'+b[18]+b[19]+'\t'+b[10]+', '+b[11])
		ms.append(u'\nУтро:\t'+b[22]+'\t'+b[24]+'\t'+b[26]+'\t'+b[28]+b[29]+'\t'+b[20]+', '+b[21])
		ms.append(u'\nДень:\t'+b[32]+'\t'+b[34]+'\t'+b[36]+'\t'+b[38]+b[39]+'\t'+b[30]+', '+b[31])
		ms.append(u'\nВечер:\t'+b[42]+'\t'+b[44]+'\t'+b[46]+'\t'+b[48]+b[49]+'\t'+b[40]+', '+b[41])
		
		beg = tuple(localtime())[3]/4
		for tmp in ms[beg:beg+4]:
			msg += tmp
        send_msg(type, jid, nick, msg)

def autoflood(type, jid, nick, text):
	tmode = 0
	if text:
		if text.lower() == 'on':
			tmode = 2
		elif text.lower() == 'off':
			tmode = 1

	floods = getFile(fld,[(getRoom(jid),0)])
	msg = u'Flood is '
	is_found = 1
	for sm in floods:
		if sm[0] == getRoom(jid):
			if tmode:
				tsm = (sm[0],tmode-1)
			else:
				tsm = (sm[0],int(not sm[1]))
			floods.remove(sm)
			floods.append(tsm)
			is_found = 0
			ssta = tsm[1]
	if is_found:
		floods.append((getRoom(jid),1))
		ssta = 1
	msg += onoff(ssta)
	writefile(fld,str(floods))
        send_msg(type, jid, nick, msg)

def execute(type, jid, nick, text):
        try:
                text = str(eval(text))
        except:
                text = u'Я не могу это исполнить'
	send_msg(type, jid, nick, text)


def calc(type, jid, nick, text):
        legal = ['0','1','2','3','4','5','6','7','8','9','*','/','+','-','(',')','=','^','!',' ','<','>','.']
        ppc = 1
        for tt in text:
                all_ok = 0
                for ll in legal:
                        if tt==ll:
                                all_ok = 1
                                break
                if not all_ok:
                        ppc = 0
                        break
	if text.count('**'):
		ppc = 0

        if ppc:        
                try:
                        text = str(eval(text))
                except:
                        text = u'Я не могу это посчитать'
        else:
                text = u'Выражение недопустимо!'
	send_msg(type, jid, nick, text)

def wtfsearch(type, jid, nick, text):
	msg = u'Чего искать то будем?'
	if len(text):
		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		text = '%'+text+'%'
		ww = cu.execute('select * from wtf where (room=? or room=? or room=?) and (room like ? or jid like ? or nick like ? or wtfword like ? or wtftext like ? or time like ?)',(jid,'global','import',text,text,text,text,text,text)).fetchall()
		msg = ''
		for www in ww:
			msg += www[4]+', '

		if len(msg):
			msg = u'Нечто похожее я видела в: '+msg[:-2]
		else:
			msg = u'Хм. Ничего похожего я не знаю...'

        send_msg(type, jid, nick, msg)

def wtfrand(type, jid, nick):
	msg = u'Всё, что я знаю это: '
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()

	ww = cu.execute('select * from wtf where room=? or room=? or room=?',(jid,'global','import')).fetchall()
	tlen = len(ww)

	ww = ww[randint(0,tlen-1)]

	msg = u'Я знаю, что '+ww[4]+u' - '+ww[5]

        send_msg(type, jid, nick, msg)

def wtfnames(type, jid, nick, text):
	msg = u'Всё, что я знаю это: '
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()

	if text == 'all':
		cu.execute('select * from wtf where room=? or room=? or room=?',(jid,'global','import'))
	elif text == 'global':
		cu.execute('select * from wtf where room=?',('global',))
	elif text == 'import':
		cu.execute('select * from wtf where room=?',('import',))
	else:
		cu.execute('select * from wtf where room=?',(jid,))

	for ww in cu:
		msg += ww[4]+', '
	msg=msg[:-2]
        send_msg(type, jid, nick, msg)

def wtfcount(type, jid, nick):
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	tlen = len(cu.execute('select * from wtf where 1=1').fetchall())
	cnt = len(cu.execute('select * from wtf where room=?',(jid,)).fetchall())
	glb = len(cu.execute('select * from wtf where room=?',('global',)).fetchall())
	imp = len(cu.execute('select * from wtf where room=?',('import',)).fetchall())
	msg = u'В этой конфе определений: '+str(cnt)+u'\nГлобальных: '+str(glb)+u'\nИмпортировано: '+str(imp)+u'\nВсего: '+str(tlen)
        send_msg(type, jid, nick, msg)
	mdb.close()

def wtf(type, jid, nick, text):
	wtf_get(0,type, jid, nick, text)

def wtff(type, jid, nick, text):
	wtf_get(1,type, jid, nick, text)

def wwtf(type, jid, nick, text):
	wtf_get(2,type, jid, nick, text)

def wtfp(type, jid, nick, text):
	if text.count('\n'):
		text = text.split('\n')
		tnick = text[1]
		ttext = text[0]
		is_found = 0
		for mmb in megabase:
			if mmb[0]==jid and mmb[1]==tnick:
				is_found = 1
				break
		if is_found:
			wtf_get(0,'chat', jid, tnick, ttext)
			send_msg(type, jid, nick, u'Отправлено в приват '+tnick)
		else:
			send_msg(type, jid, nick, u'Ник '+tnick+u' не найден!')
	else:
		wtf_get(0,'chat', jid, nick, text)

def wtf_get(ff,type, jid, nick, text):
	msg = u'Чего искать то будем?'
	if len(text):
		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		tlen = len(cu.execute('select * from wtf where (room=? or room=? or room=?) and wtfword=?',(jid,'global','import',text)).fetchall())
		cu.execute('select * from wtf where (room=? or room=? or room=?) and wtfword=?',(jid,'global','import',text))

		if tlen:
			for aa in cu:
				ww=aa[1:]
			msg = u'Я знаю, что '+text+u' - '+ww[4]
			if ff == 1:
				msg += u'\nот: '+ww[2]+' ['+ww[5]+']'
			elif ff == 2:
				msg = u'Я знаю, что '+text+u' было определено: '+ww[2]+' ('+ww[1]+')'+' ['+ww[5]+']'
		else:
			msg = u'Хм. Мне про это никто не рассказывал...'
        send_msg(type, jid, nick, msg)

def del_space_begin(text):
	if len(text):
		while text[:1] == ' ':
			text = text[1:]
	return text

def del_space_end(text):
	if len(text):
		while text[-1:] == ' ':
			text = text[:-1]
	return text

def dfn(type, jid, nick, text):
	global wbase, wtfbase
	msg = u'Чего запомнить то надо?'
	if len(text) and text.count('='):

	        ta = get_access(jid,nick)

	        realjid =ta[1]

		ti = text.index('=')
		what = del_space_end(text[:ti])
		text = del_space_begin(text[ti+1:])

		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		tlen = len(cu.execute('select * from wtf where (room=? or room=? or room=?) and wtfword=?',(jid,'global','import',what)).fetchall())
		cu.execute('select * from wtf where (room=? or room=? or room=?) and wtfword=?',(jid,'global','import',what))
		
		if tlen:
			for aa in cu:
				ww=aa
			if ww[1] == 'global':
				msg = u'Это глобальное определение и его нельзя изменить!'
				text = ''
			else:
				if text == '':
					msg = u'Жаль, что такую полезную хренотень надо забыть...'
				else:
					msg = u'Боян, но я запомню!'
				cu.execute('delete from wtf where wtfword=?',(what,))
			idx = ww[0]
		else:
			msg = u'Ммм.. Что-то новенькое, ща запомню!'
			idx = len(cu.execute('select * from wtf where 1=1').fetchall())

		if text != '':
			cu.execute('insert into wtf values (?,?,?,?,?,?,?)', (idx, jid, realjid, nick, what, text, timeadd(tuple(localtime()))))
		mdb.commit()
        send_msg(type, jid, nick, msg)

def gdfn(type, jid, nick, text):
	global wbase, wtfbase
	msg = u'Чего запомнить то надо?'
	if len(text) and text.count('='):

	        ta = get_access(jid,nick)

	        realjid =ta[1]

		ti = text.index('=')
		what = del_space_end(text[:ti])
		text = del_space_begin(text[ti+1:])

		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		tlen = len(cu.execute('select * from wtf where (room=? or room=? or room=?) and wtfword=?',(jid,'global','import',what)).fetchall())
		cu.execute('select * from wtf where (room=? or room=? or room=?) and wtfword=?',(jid,'global','import',what))
		
		if tlen:
			for aa in cu:
				ww=aa
			if text == '':
				msg = u'Жаль, что такую полезную хренотень надо забыть...'
			else:
				msg = u'Боян, но я запомню!'
			cu.execute('delete from wtf where wtfword=?',(what,))
			idx = ww[0]
		else:
			msg = u'Ммм.. Что-то новенькое, ща запомню!'
			idx = len(cu.execute('select * from wtf where 1=1').fetchall())

		if text != '':
			cu.execute('insert into wtf values (?,?,?,?,?,?,?)', (idx, 'global', realjid, nick, what, text, timeadd(tuple(localtime()))))
		mdb.commit()
        send_msg(type, jid, nick, msg)

#--------

def un_unix(val):
	tsec = int(val)-int(val/60)*60
	val = int(val/60)
	tmin = int(val)-int(val/60)*60
	val = int(val/60)
	thour = int(val)-int(val/24)*24
	tday = int(val/24)
	ret = tZ(thour)+':'+tZ(tmin)+':'+tZ(tsec)
	if tday:
		ret = str(tday)+' day(s) '+ret
	return ret

def true_age(type, jid, nick, text):
        while text[-1:] == ' ':
                text = text[:-1]
        
	text = text.split(' ')
	llim = 10
	if len(text)>=2:
		try:
			llim = int(text[0])
		except:
			llim = 10

		text = text[1]
	else:
		text = text[0]

	if llim > 100:
		llim = 100
	if text == '':
		text = nick
	is_found = 0
	ms = []
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	cu.execute('select * from age order by room')
	for aa in cu:
		if aa[0]==jid and (aa[1].lower().count(text.lower()) or aa[2].lower().count(text.lower())):
			if aa[5]:
				r_age = aa[4]
				r_was = int(time.time())-aa[3]
			else:
				r_age = int(time.time())-aa[3]+aa[4]
				r_was = 0
			ms.append((aa[1],r_age,r_was,aa[6],aa[7]))
			is_found = 1
	if is_found:
		lms = len(ms)
		for i in range(0,lms-1):
			for j in range(i,lms):
				if ms[i][1] < ms[j][1]:
					jj = ms[i]
					ms[i] = ms[j]
					ms[j] = jj
		if lms > llim:
			lms = llim
		if lms == 1 and nick == text:
			msg = u'Время твоего нахождения в конфе: '+un_unix(ms[0][1])
		else:
			msg = u'Время нахождения в конфе:'
			cnt = 1
			for i in range(0,lms):
				msg += '\n'+str(cnt)+'. '+ms[i][0]+'\t'+un_unix(ms[i][1])
				if ms[i][2]:
					if ms[i][3] != '':
						msg += u', '+ms[i][3]+' '+un_unix(ms[i][2])+u' назад'
					else:
						msg += u', Вышел '+un_unix(ms[i][2])+u' назад'
					if ms[i][4] != '':
						if ms[i][4].count('\n') >= 4:
							stat = ms[i][4].split('\n',4)[4]
							if stat != '':
								msg += ' ('+stat+')'
						else:
							msg += ' ('+ms[i][4]+')'

				cnt += 1
	else:
		msg = u'Не найдено!'

#agebase.append((room, nick,getRoom(jid),tt,ab[4],0))
        send_msg(type, jid, nick, msg)

#cu.execute('''create table age (room text, nick text, jid text, time integer, age integer, status integer, type text, message text)''')
def close_age_null():
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	cu.execute('delete from age where jid like ?',('<temporary>%',)).fetchall()
	ccu = cu.execute('select * from age where status=? order by room',(0,)).fetchall()
	for ab in ccu:
		cu.execute('delete from age where room=? and jid=? and status=?', (ab[0],ab[2],0))
		cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (ab[0],ab[1],ab[2],ab[3],ab[4],1,ab[6],ab[7]))
	mdb.commit()

def close_age():
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	cu.execute('delete from age where jid like ?',('<temporary>%',)).fetchall()
	ccu = cu.execute('select * from age where status=? order by room',(0,)).fetchall()
	tt = int(time.time())
	for ab in ccu:
		if not ab[5]:
			cu.execute('delete from age where room=? and jid=?',(ab[0],ab[2]))
			cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (ab[0],ab[1],ab[2],tt,ab[4]+(tt-ab[3]),1,ab[6],ab[7]))
	mdb.commit()

def close_age_room(room):
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	cu.execute('delete from age where jid like ?',('<temporary>%',)).fetchall()
	ccu = cu.execute('select * from age where status=? order by room',(0,)).fetchall()
	tt = int(time.time())
	for ab in ccu:
		if getRoom(ab[0]) == getRoom(room) and not ab[5]:
			cu.execute('delete from age where room=? and jid=?',(ab[0],ab[2]))
			cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (ab[0],ab[1],ab[2],tt,ab[4]+(tt-ab[3]),1,ab[6],ab[7]))
	mdb.commit()

def weather_city(type, jid, nick, text):
	text = text.upper()
	text = text.split(' ')

	link = 'http://weather.noaa.gov/weather/'+text[0]+'_cc.html'
	f = urllib.urlopen(link)
	wzz = f.read()
	f.close()

	if wzz.count('Not Found'):
		msg = u'Я не знаю такой страны!'
	else:
		wzpos = wzz.find('<select name=\"cccc\">')
		wzz = wzz[wzpos:wzz.find('</select>',wzpos)]

		wzz = wzz.split('<OPTION VALUE=\"')
		msg = u'Города по запросу: '
		not_add = 1
		for wzzz in wzz:
			if wzzz.lower().count(text[1].lower()):
				msg += '\n'+wzzz.replace('\">',' -')[:-1]
				not_add = 0
		if not_add:
			msg = u'Такой город не найден!'

        send_msg(type, jid, nick, msg)

def defcode(type, jid, nick, text):
	dcnt = text[0]
	ddef = text[1:4]
	dnumber = text[4:]
	if text[:2] != '79':
		msg = u'Поиск только по мобильным телефонам России!'
	else:
		link = 'http://www.mtt.ru/info/def/index.wbp?def='+ddef+'&number='+dnumber+'&region=&standard=&date=&operator='
		f = urllib.urlopen(link)
		msg = f.read()
		f.close()

		encidx = msg.find('charset=')
		if encidx >= 0:
			enc = msg[encidx+8:encidx+30]
			enc = enc[:enc.index('\">')]
			enc = enc.upper()
		else:
			enc = 'UTF-8'

		msg = unicode(msg, enc)

		mbeg = msg.find('<INPUT TYPE=\"submit\" CLASS=\"submit\"')
		msg = msg[mbeg:msg.find('</table>',mbeg)]
		msg = msg.split('<tr')
		
		if msg[0].count(u'не найдено'):
			msg = u'Не найдено!'
		else:
			msg.remove(msg[0])
			mmsg = u'Найдено:\n'
			for mm in msg:
				tmm = mm
				tmm = replacer(tmm)
				tmm = tmm[tmm.find('>')+1:]
				tmm = tmm.replace('\n','\t')
				mmsg += tmm[1:-2] + '\n'
			msg = mmsg[:-1]
	
       	send_msg(type, jid, nick, msg)
	
def weather_raw(type, jid, nick, text):
	text = text.upper()
	link = 'http://weather.noaa.gov/pub/data/observations/metar/decoded/'+text+'.TXT'
	f = urllib.urlopen(link)
	msg = f.read()
	f.close()

	msg = msg[:-1]

	if msg.count('Not Found'):
		msg = u'Город не найден!'

        send_msg(type, jid, nick, msg)

def sfind(mass,stri):
	for a in mass:
		if a.count(stri):
			return a
	return ''

def weather(type, jid, nick, text):
	text = text.upper()
	link = 'http://weather.noaa.gov/pub/data/observations/metar/decoded/'+text+'.TXT'
	f = urllib.urlopen(link)
	wzz = f.read()
	f.close()

	if wzz.count('Not Found'):
		msg = u'Город не найден!'
	else:
		wzz = wzz.split('\n')

		wzr = []
		wzr.append(wzz[0])			# 0
		wzr.append(wzz[1])			# 1
		wzr.append(sfind(wzz,'Temperature'))	# 2
		wzr.append(sfind(wzz,'Wind'))		# 3
		wzr.append(sfind(wzz,'Relative'))	# 4
		wzr.append(sfind(wzz,'Sky'))		# 5
		wzr.append(sfind(wzz,'Weather'))	# 6
		wzr.append(sfind(wzz,'Visibility'))	# 7
		wzr.append(sfind(wzz,'Pressure'))	# 8

		msg = wzr[0][:wzr[0].find(')')+1]
		msg += '\n'+ wzr[1]

		wzz1 = wzr[2].find(':')+1 # Temperature
		wzz2 = wzr[2].find('(',wzz1)
		wzz3 = wzr[2].find(')',wzz2)
		msg += '\n'+ wzr[2][:wzz1] + ' ' + wzr[2][wzz2+1:wzz3]

		wzz1 = wzr[3].find('(')
		wzz2 = wzr[3].find(')',wzz1)
		wzz3 = wzr[3].find(':',wzz2)
		msg += '\n'+ wzr[3][:wzz1-1] + wzr[3][wzz2+1:wzz3]

		msg += '\n'+ wzr[4]
		if len(wzr[5]):
			msg += ','+ wzr[5][wzr[5].find(':')+1:]
		if len(wzr[6]):
			msg += ','+ wzr[6][wzr[6].find(':')+1:]
		if not (len(wzr[5])+len(wzr[6])):
			msg += ', clear'

		msg += '\n'+ wzr[7][:-2]
		
		wzz1 = wzr[8].find('(')
		wzz2 = wzr[8].find(':',wzz1)
		wzz3 = wzr[8].find('(',wzz2)
		msg += ', '+ wzr[8][:wzz1-1]+': '+wzr[8][wzz3+1:-1]

        send_msg(type, jid, nick, msg)

def get_local_prefix(jid):
	lprefix = prefix
	if os.path.isfile(preffile):
		pref = eval(readfile(preffile))
		for pp in pref:
			if pp[0] == getRoom(jid):
				lprefix = pp[1]
				break
	return lprefix

def get_prefix(prefix):
	if prefix != u'':
	        return prefix
	else:
		return u'отсутствует'

#  0     1            2     3      4
# [1,prefix+cmd, exe_alias, 0, prefix+cbody])

def set_prefix(type, jid, nick, text):
        global preffile, prefix
	msg = u'Префикс команд: '

        if text != '':
                lprefix = text

	if text.lower() == 'none':
		lprefix = u''

	if text.lower() == 'del':
		lprefix = prefix

	if len(text):
	        if os.path.isfile(preffile):
			pref = eval(readfile(preffile))
			for pp in pref:
				if pp[0] == getRoom(jid):
					pref.remove(pp)
					break
			pref.append((getRoom(jid),lprefix))
			writefile(preffile,str(pref))
		else:
			pref = [(getRoom(jid),lprefix)]
			writefile(preffile,str(pref))
	else:
		lprefix = get_local_prefix(jid)
	msg += get_prefix(lprefix)

	send_msg(type, jid, nick, msg)
	
def inban(type, jid, nick, text):
	global banbase
	banbase = []
	i = Node('iq', {'id': randint(1,1000), 'type': 'get', 'to':getRoom(jid)}, payload = [Node('query', {'xmlns': NS_MUC_ADMIN},[Node('item',{'affiliation':'outcast'})])])
	cl.send(i)
	while banbase == []:
		sleep(0.5)
	while banbase[-1] != (u'TheEnd', u'None'):
		sleep(0.1)

	banbase = banbase[:-1]
	msg = u'Всего в бане: '+str(len(banbase))
	if text != '':
		mmsg = u', найдено:\n'
		fnd = 1
		cnt = 1
		for i in banbase:
			if i[0].lower().count(text.lower()) or i[1].lower().count(text.lower()):
				mmsg += str(cnt)+'. '+i[0]+' - '+i[1]+'\n'
				fnd = 0
				cnt += 1
		mmsg = mmsg[:-1]
		if fnd:
			mmsg = u', совпадений нет!'
		msg += mmsg
	banbase = []
        send_msg(type, jid, nick, msg)

def youtube(type, jid, nick, text):
	text = text.lower()
	text = text.encode('utf-8')
	text = text.replace('\\x','%')
	text = text.replace(' ','%20')
	link = 'http://www.youtube.com/results?search_type=&search_query='+text+'&aq=f'
	f = urllib.urlopen(link)
	tube = f.read()
	f.close()
#	tube = tube.split('video-title video-title-results')
	tube = tube.split('video-run-time')

	tmass = []
	ltube = len(tube)
	smsg = u'Всего найдено: '+str(ltube-1)
	if ltube > 4:
		ltube=4
	for i in range(1,ltube):

		msg = tube[i].decode('utf')
		idx = msg.index('>')
		imsg = msg[idx+1:]
		idx = imsg.index('<')
		mtime = imsg[:idx]

		idx = msg.index('/watch?v=')
		imsg = msg[idx:]
		idx = imsg.index('\"')
		imsg = imsg[:idx]
		murl = 'http://www.youtube.com'+imsg

		idx = msg.index('title=\"')
		imsg = msg[idx+7:]
		idx = imsg.index('\"')
		imsg = imsg[:idx]
		imsg = rss_replace(imsg)
		msg = murl +'\t'+ imsg +' ('+ mtime +')'
		tmass.append(msg)
	
	msg = smsg + '\n'
	for i in tmass:
		msg += i + '\n'
	msg = msg[:-1]
        send_msg(type, jid, nick, msg)
	

def smile(type, jid, nick, text):
	tmode = 0
	if text:
		if text.lower() == 'on':
			tmode = 2
		elif text.lower() == 'off':
			tmode = 1
	smiles = getFile(sml,[(getRoom(jid),0)])
	msg = u'Smiles is '
	is_found = 1
	for sm in smiles:
		if sm[0] == getRoom(jid):
			if tmode:
				tsm = (sm[0],tmode-1)
			else:
				tsm = (sm[0],int(not sm[1]))
			smiles.remove(sm)
			smiles.append(tsm)
			is_found = 0
			ssta = tsm[1]
	if is_found:
		smiles.append((getRoom(jid),1))
		ssta = 1
	msg += onoff(ssta)
	writefile(sml,str(smiles))
        send_msg(type, jid, nick, msg)

def uptime(type, jid, nick):
	msg = u'Время работы: ' + get_uptime_str()+ u', Последняя сессия: '+un_unix(int(time.time())-sesstime)

        send_msg(type, jid, nick, msg)
	

def null_vars():
        vars = {'none/visitor':0,
                'none/participant':0,
                'none/moderator':0,
                'member/visitor':0,
                'member/participant':0,
                'member/moderator':0,
                'admin/moderator':0,
                'owner/moderator':0}
	return vars

def gstats(type, jid, nick):
        msg = u'За последнюю сессию ('+un_unix(int(time.time())-sesstime)+u') я видела всего:'
	vars = null_vars()

        for mega in megabase2:
                        ta = mega[3]+'/'+mega[2]
			for va in vars:
				if va == ta:
		                        vars[ta]+=1
        for va in vars:
                if vars[va]:
                        msg += '\n'+str(va)+' '+str(vars[va])

        send_msg(type, jid, nick, msg)
	

def stats(type, jid, nick):
        msg = u'За последнюю сессию ('+un_unix(int(time.time())-sesstime)+u') я видела здесь:'
	vars = null_vars()

        for mega in megabase2:
                if mega[0] == jid:
                        ta = mega[3]+'/'+mega[2]
			for va in vars:
				if va == ta:
		                        vars[ta]+=1
        for va in vars:
                if vars[va]:
                        msg += '\n'+str(va)+' '+str(vars[va])

        send_msg(type, jid, nick, msg)

	
def show_error(type, jid, nick, text):
        if text.lower() == 'clear':
                writefile(LOG_FILENAME,'')
        try:
		cmd = int(text)
        except:
                cmd = 1

	if os.path.isfile(LOG_FILENAME) and text.lower() != 'clear':
		log = str(readfile(LOG_FILENAME))
                log = log.split('ERROR:')

                lll = len(log)
                if cmd > lll:
                        cmd = lll
                
        	msg = u'Total Error(s): '+str(lll-1)+'\n'
        	if text != '':
                        for aa in range(lll-cmd,lll):
                                msg += log[aa]+'\n'
                else:
                        msg += ' '
                msg = msg[:-2]
        else:
                msg = u'No Errors'
	send_msg(type, jid, nick, msg)
	

def get_log(type, jid, nick, text):
	text = text.split(' ')
	if len(text)>0:
		cmd = text[0]
	else:
		cmd = ''
	if len(text)>1:
		arg = text[1]
	else:
		arg = ''
	logt=tuple(localtime())

	if cmd == 'len':
		if arg == '':
			logfile = 'log/'+tZ(logt[0])+tZ(logt[1])+tZ(logt[2])
		else:
			logfile = 'log/'+arg
		log = getFile(logfile,[])
		log_lm = len(str(log))/msg_limit
		msg = u'Log length for '+logfile+' is '+str(len(log))+' record(s) / '+str(log_lm)+' Messages with limit: '+str(msg_limit)
		send_msg(type, jid, nick, msg)
	
	if cmd == 'show':
		if arg == '':
			logfile = 'log/'+tZ(logt[0])+tZ(logt[1])+tZ(logt[2])
		else:
			logfile = 'log/'+arg
		log = getFile(logfile,[])
		if len(text)>2:
			arg1 = text[2]
		else:
			arg1 = '0-'+str(len(log)-1)
		if arg == '':
			llog = len(log)
			if llog >= 5:
				lllim = 5
			else:
				lllim = llog
			arg1 = str(len(log)-lllim)+'-'+str(len(log))

		arg1 = arg1.split('-')
		log_from = int(arg1[0])
		log_to = int(arg1[1])
		msg = u'Log:'
		for clog in range(log_from, log_to):
			msg += '\n'+log[clog]
		send_msg(type, jid, nick, msg)
	

def get_access(cjid, cnick):
	access_mode = -2
	jid = 'None'
	for base in megabase:
		if base[1].count(cnick) and base[0].lower()==cjid:
			jid = base[4]
			if base[3]==u'admin' or base[3]==u'owner':
       				access_mode = 1
				break
			if base[3]==u'member' or base[3]==u'none':
       				access_mode = 0
				break

	for iib in ignorebase:
		grj = getRoom(jid.lower())
		if iib.lower() == grj:
			access_mode = -1
			break
		if not (iib.count('.')+iib.count('@')) and grj.count(iib.lower()):
			access_mode = -1
			break

	if ownerbase.count(getRoom(jid)):
		access_mode = 2

	if jid == 'None' and ownerbase.count(getRoom(cjid)):
		access_mode = 2

        return (access_mode, jid)

def info_whois(type, jid, nick, text):
	if text != '':
		msg = raw_who(jid, text)
	else:
		msg = u'Кто нужен?'
	send_msg(type, jid, nick, msg)
		
def info_access(type, jid, nick):
	msg = raw_who(jid, nick)
	send_msg(type, jid, nick, msg)

def raw_who(room,nick):
        ta = get_access(room,nick)
        access_mode = ta[0]
	if access_mode == -2:
		msg = u'А был ли мальчег?'
	else:
		realjid = ta[1]
		msg = u'Доступ: '+str(access_mode)
        	tb = [u'Игнорируемый',u'Минимальный',u'Админ/Владелец конфы',u'Владелец бота']
        	msg += ', ' + tb[access_mode+1]
        	if realjid != 'None':
        	        msg += u', jid опознан'
		msg += u', Префикс: ' + get_local_prefix(room)
	return msg

def info_comm(type, jid, nick):
	global comms
	msg = ''
	ta = get_access(jid,nick)
	access_mode = ta[0]
	tmp = sqlite3.connect(':memory:')
	cu = tmp.cursor()
	cu.execute('''create table tempo (comm text, am integer)''')

	for i in comms:
		if access_mode >= i[0]:
			cu.execute('insert into tempo values (?,?)', (unicode(i[1]),i[0]))

	for j in range(0,access_mode+1):
		cm = cu.execute('select * from tempo where am=? order by comm',(j,)).fetchall()
		msg += u'\n• '+str(j)+' ... '
		for i in cm:
			msg += i[0] +', '
		msg = msg[:-2]
	msg = u'Всего команд: '+str(len(comms))+u' | Префикс: '+get_local_prefix(jid)+u' | Ваш доступ: '+str(access_mode)+u' | Доступно команд: '+str(len(cu.execute('select * from tempo where am<=?',(access_mode,)).fetchall()))+msg
	tmp.close()
	send_msg(type, jid, nick, msg)

def bot_exit(type, jid, nick, text):
	global game_over
	StatusMessage = u'Exit by \'quit\' command from bot owner ('+nick+u')'
	if text != '':
                StatusMessage += ' ['+text+u']'
	send_presence_all(StatusMessage)
	writefile(tmpf,str('exit'))
	sleep(3)
	game_over = 1

def bot_restart(type, jid, nick, text):
	global game_over
	StatusMessage = u'Restart by \'restart\' command from bot owner ('+nick+u')'
	if text != '':
                StatusMessage += ' ['+text+u']'
	send_presence_all(StatusMessage)
	writefile(tmpf,str('restart'))
	game_over = 1

def bot_update(type, jid, nick, text):
	global game_over
	StatusMessage = u'Self update by \'update\' command from bot owner ('+nick+u')'
	if text != '':
                StatusMessage += ' ['+text+u']'
	send_presence_all(StatusMessage)
	writefile(tmpf,str('update'))
	game_over = 1

def say(type, jid, nick, text):
	nick = ''
	type = 'groupchat'
	text = to_censore(text)
#	text = rss_replace(text) #!!!!!
	send_msg(type, jid, nick, text)	

def gsay(type, jid, nick, text):
        global confbase

	type = 'groupchat'
        msg = text
	nick = ''
        for jjid in confbase:
	        send_msg(type, getRoom(jjid), nick, msg)
	

def helpme(type, jid, nick, text):
	pprint(text)
	hlpfile = 'help/help.txt'
	helps = []
	if os.path.isfile(hlpfile):
		hlp = readfile(hlpfile)
		hlp = hlp.split('{')
		for hh in hlp:
			if len(hh):
				hh = hh.decode('utf-8')
				hhh = hh.split('}')
				helps.append((hhh[0],hhh[1][:-1]))

	if text != '':
		mesg = u'Префикс команд: '+get_local_prefix(jid)+u'\nДоступна справка по командам:\n'

	        cnt = 0
       		for i in range(0,3):
        	        mesg += '['+str(i)+'] '
        		for hlp in helps:
        	                for cmdd in comms:
					tc = cmdd[1]
        	                        if tc == hlp[0] and cmdd[0] == i:
        	                                mesg += hlp[0] + ', '
        	                                cnt += 1
        	        mesg = mesg[:-2]
        	        mesg += '\n'
        	if cnt != len(helps):
        	        mesg += '[?] '
        	        for hlp in helps:
        	                fl = 1
        	                for cmdd in comms:
					tc = cmdd[1]
        	                        if tc == hlp[0]:
        	                                fl = 0
        	                if fl:
        	                        mesg += hlp[0] + ', '
        	        mesg = mesg[:-1]
		mesg = mesg[:-1]

	else:
		mesg = u'Isida Jabber Bot\nИнформационно-справочный бот\nhttp://isida.googlecode.com\n© 2oo9 Disabler Production Lab.\nСправка по командам: help команда'

	for hlp in helps:
		if text.lower() == hlp[0]:
			mesg = u'Справочная информация: ' + hlp[1]
			for cmdd in comms:
				tc = cmdd[1]
                                if tc == hlp[0]:
                                        mesg = u'Уровень доступа: '+str(cmdd[0]) + hlp[1]

	send_msg(type, jid, nick, mesg)
	

def hidden_clear(type, jid, nick, text):
	try:
		cntr = int(text)
	except:
		cntr = 20

	if cntr < 1 or cntr > 100:
		cntr = 20
        pprint(u'clear: '+unicode(jid)+u' by: '+unicode(nick))
        send_msg(type, jid, nick, u'Начинаю зачистку! Сообщений: '+str(cntr)+u', время зачистки примерно '+str(int(cntr*1.3))+u' сек.')
        while (cntr>0):
                cl.send(xmpp.Message(jid, '', "groupchat"))
                time.sleep(1.3)
                cntr=cntr-1
        send_msg(type, jid, nick, u'стерильно!!!')
	

def bot_rejoin(type, jid, nick, text):
        global lastserver, lastnick, confbase
        text=unicode(text)

	if len(text):
		text=unicode(text)
	else:
		text=jid

	if toSymbolPosition(text,'@')<0:
		text+='@'+lastserver
	if toSymbolPosition(text,'/')<0:
		text+='/'+lastnick
                             
	lastserver = getServer(text)
	lastnick = getResourse(text)

	lroom = text
                                
	if arr_semi_find(confbase, getRoom(lroom)) >= 0:
		pprint(u'rejoin '+text+' by '+nick)
		sm = u'Перезахожу по команде от '+nick
		leaveconf(text, domain, sm)
		zz = joinconf(text, domain)
		if zz != None:
			send_msg(type, jid, nick, u'Ошибка! '+zz)
	else:
		send_msg(type, jid, nick, u'хватит бухать! Меня нету в '+getRoom(lroom))
		pprint(u'never be in '+text)
	

def bot_join(type, jid, nick, text):
        global lastserver, lastnick, confs, confbase
        text=unicode(text)
        if text=='':
                send_msg(type, jid, nick, u'косяк с аргументами!')
        else:
                if toSymbolPosition(text,'@')<0:
                        text+='@'+lastserver
                if toSymbolPosition(text,'/')<0:
                        text+='/'+lastnick
                             
                lastserver = getServer(text)
                lastnick = getResourse(text)
                                
                lroom = text.index('/')
                lroom = text[:lroom]

		if arr_semi_find(confbase, lroom) == -1:                                
			zz = joinconf(text, domain)
			if zz != None:
				send_msg(type, jid, nick, u'Ошибка! '+zz)
	                        pprint(u'*** Error join to '+text+' '+zz)
			else:
	                        confbase.append(text)
	                        writefile(confs,str(confbase))
        	                send_msg(type, jid, nick, u'зашла в '+text)
	                        pprint(u'join to '+text)

                elif confbase.count(text):
                        send_msg(type, jid, nick, u'хватит бухать! Я уже в '+lroom+u' с ником '+lastnick)
                        pprint(u'already in '+text)
		else:
                        zz = joinconf(text, domain)
			if zz != None:
				send_msg(type, jid, nick, u'Ошибка! '+zz)
	                        pprint(u'*** Error join to '+text+' '+zz)
			else:
				confbase = arr_del_semi_find(confbase, lroom)
	                        confbase.append(text)
				send_msg(type, jid, nick, u'смена ника в '+lroom+u' на '+lastnick)
	                        writefile(confs,str(confbase))
	                        pprint(u'change nick '+text)
	

def bot_leave(type, jid, nick, text):
        global confs, confbase, lastserver, lastnick
        if len(confbase) == 1:
                send_msg(type, jid, nick, u'не могу выйти из последней конфы!')
        else:
		if text == '':
			text = jid
                if toSymbolPosition(text,'@')<0:
                        text+='@'+lastserver
                if toSymbolPosition(text,'/')<0:
                        text+='/'+lastnick
                             
                lastserver = getServer(text)
                lastnick = getResourse(text)

                if len(text):
                        text=unicode(text)
                else:
                        text=jid
                lroom = text
                              

		if ownerbase.count(getRoom(jid)):
			nick = getName(jid)
  
		if arr_semi_find(confbase, getRoom(lroom)) >= 0:
#                if confbase.count(lroom):
#                        confbase.remove(lroom)
			confbase = arr_del_semi_find(confbase,getRoom(lroom))
                        writefile(confs,str(confbase))
                        send_msg(type, jid, nick, u'свалила из '+text)
			sm = u'Меня выводит '+nick
                        leaveconf(getRoom(text), domain, sm)
                        pprint(u'leave '+text+' by '+nick)
                else:
                        send_msg(type, jid, nick, u'хватит бухать! Меня нету в '+lroom)
                        pprint(u'never be in '+text)
	

def conf_pass(type, jid, nick, text):
	global psw
	text=unicode(text)
	if text!='':
		psw = text
	send_msg(type, jid, nick, u'пароль \''+psw+'\'')
	

def conf_limit(type, jid, nick, text):
	global msg_limit
	text=unicode(text)
	if text!='':
		try:
			msg_limit = int(text)
		except:
			msg_limit = 1000
	send_msg(type, jid, nick, u'Message limit is '+str(msg_limit))
	

def bot_plugin(type, jid, nick, text):
	global plname, plugins, execute, gtimer, gpresence, gmassage
	text = text.split(' ')
	do = ''
	nnick = ''
	if len(text)>0:
		do = text[0]
	if len(text)>1:
		nnick = text[1]+'.py'
	pprint('plugin '+do+' '+nnick)
	msg = ''
	if do == 'add':
                if not plugins.count(nnick) and os.path.isfile('plugins/'+nnick):
                        plugins.append(nnick)
                        execfile('plugins/'+nnick)
                        msg = u'Загружен плагин: '+nnick[:-3]+u'\nДоступны комманды: '
                        for commmm in execute:
                                msg += commmm[1]+'['+str(commmm[0])+'], '
                                comms.append(commmm)
                        msg = msg[:-2]
			for tmr in timer:
				gtimer.append(tmr)
			for tmp in presence_control:
				gpresence.append(tmp)
			for tmp in message_control:
				gmessage.append(tmp)
                        
	elif do == 'del':
                if plugins.count(nnick) and os.path.isfile('plugins/'+nnick):
                        plugins.remove(nnick)
                        execfile('plugins/'+nnick)
                        msg = u'Удалён плагин: '+nnick[:-3]+u'\nУдалены комманды: '
                        for commmm in execute:
                                msg += commmm[1]+'['+str(commmm[0])+'], '
                                for i in comms:
                                        if i[1] == commmm[1]:
                                                comms.remove(i)
                        msg = msg[:-2]
			for tmr in timer:
				gtimer.remove(tmr)
			for tmp in presence_control:
				gpresence.remove(tmp)
			for tmp in message_control:
				gmessage.remove(tmp)

	elif do == 'local':
		a = os.listdir('plugins/')
		b = []
		for c in a:
			if c[-3:] == u'.py' and c != 'main.py':
				b.append(c[:-3].decode('utf-8'))
		msg = u'Доступные плагины: '
		for c in b:
				msg += c+', '
		msg = msg[:-2]
		
	else:
		msg = u'Активные плагины: '
		for jjid in plugins:
				msg += jjid[:-3]+', '
		msg = msg[:-2]


	writefile(plname,str(plugins))
        send_msg(type, jid, nick, msg)
	
#                        elif text[:5] == u'/auth':
#                                j = Presence(BaseJid, 'subscribed')
#				j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
#                                clc[selcon].send(j)
#                                nosend=0

def owner(type, jid, nick, text):
	global ownerbase, owners, god
	do = text[:3]
	nnick = text[4:]
	pprint('owner '+do+' '+nnick)
	if do == 'add':
                if not ownerbase.count(nnick):
                        ownerbase.append(nnick)
		        j = Presence(nnick, 'subscribe')
			j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		        cl.send(j)

	elif do == 'del':
                if ownerbase.count(nnick) and nnick != god:
                        ownerbase.remove(nnick)
		        j = Presence(nnick, 'unsubscribed')
			j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
		        cl.send(j)
#        elif do == 'clr':
#                ownerbase = [god]

	msg = u'Я принимаю команды от: '
	for jjid in ownerbase:
			msg += jjid+', '
	msg = msg[:-2]
	writefile(owners,str(ownerbase))
        send_msg(type, jid, nick, msg)
	

def ignore(type, jid, nick, text):
	global ignorebase, ignores, god
	do = text[:3]
	nnick = text[4:].lower()
	pprint('ignore '+do+' '+nnick)
	if do == 'add':
                if not ignorebase.count(nnick):
                        ignorebase.append(nnick)
	elif do == 'del':
                if ignorebase.count(nnick) and nnick != god:
                        ignorebase.remove(nnick)
#        elif do == 'clr':
#                ignorebase = []

	msg = u'Я не принимаю команды от: '
	for jjid in ignorebase:
			if jjid.count('@') and jjid.count('.'):
				msg += jjid+', '
			else:
				msg += '*'+jjid+'*, '
	msg = msg[:-2]
	writefile(ignores,str(ignorebase))
        send_msg(type, jid, nick, msg)
	

def info_where(type, jid, nick):
        global confbase
        msg = u'Активных конференций: '+str(len(confbase))+'\n'
	wbase = []
        for jjid in confbase:
		cnt = 0
		rjid = getRoom(jjid)
		for mega in megabase:
			if mega[0] == rjid:
				cnt += 1
		wbase.append((jjid, cnt))

	for i in range(0,len(wbase)-1):
		for j in range(i,len(wbase)):
			if wbase[i][1] < wbase[j][1]:
				jj = wbase[i]
				wbase[i] = wbase[j]
				wbase[j] = jj
	nmb = 1
	for i in wbase:
		msg += str(nmb)+'. '+i[0]+' ['+str(i[1])+']\n'
		nmb += 1

        msg = msg[:-1]
        send_msg(type, jid, nick, msg)
	

def get_uptime_raw():
	nowtime = tuple(localtime())

	difftime = [0,0,0,0,0,0]

	difftime[5] = nowtime[5]-starttime[5]
	if difftime[5] < 0:
		difftime[5] += 60
		difftime[4] -= 1

	difftime[4] += nowtime[4]-starttime[4]
	if difftime[4] < 0:
		difftime[4] += 60
		difftime[3] -= 1

	difftime[3] += nowtime[3]-starttime[3]
	if difftime[3] < 0:
		difftime[3] += 24
		difftime[2] -= 1

	timemonth = [31,28,31,30,31,30,31,31,30,31,30,31]

	difftime[2] += nowtime[2]-starttime[2]
	if difftime[2] < 0:
		difftime[2] += timemonth(nowtime[2])
		difftime[1] -= 1

	difftime[1] += nowtime[1]-starttime[1]
	if difftime[1] < 0:
		difftime[1] += 12
		difftime[0] -= 1

	difftime[0] += nowtime[0]-starttime[0]
	return difftime

def get_uptime_str():
	difftime = get_uptime_raw()
	msg = u''
	if difftime[0] >0:
                msg += str(difftime[0])+'y '
	if difftime[1] >0:
                msg += str(difftime[1])+'m '
	if difftime[2] >0:
                msg += str(difftime[2])+'d '
        msg += tZ(difftime[3])+':'+tZ(difftime[4])+':'+tZ(difftime[5])
	return msg

def info(type, jid, nick):
        global confbase        
        msg = u'Конференций: '+str(len(confbase))+u' (подробнее where)\n'
        msg += u'Сервер: '+lastserver+u' | Ник: '+lastnick+'\n'
	msg += u'Лимит размера сообщений: '+str(msg_limit)+'\n'
	msg += u'Время запуска: '+timeadd(starttime)+'\n'
	msg += u'Локальное время: '+timeadd(tuple(localtime()))+'\n'
	msg += u'Время работы: ' + get_uptime_str()+u', Последняя сессия: '+un_unix(int(time.time())-sesstime)
	smiles = getFile(sml,[(getRoom(jid),0)])
	msg += u'\nSmiles: ' + onoff(int((getRoom(jid),1) in smiles))
	floods = getFile(fld,[(getRoom(jid),0)])
	msg += u' | Flood: ' + onoff(int((getRoom(jid),1) in floods))
	gl_censor = getFile(cns,[(getRoom(jid),0)])
	msg += u' | Censor: ' + onoff(int((getRoom(jid),1) in gl_censor))
	msg += u' | Префикс команд: '+get_prefix(get_local_prefix(jid))

        send_msg(type, jid, nick, msg)
	

def info_res(type, jid, nick, text):
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	if text == 'count':
		tlen = len(cu.execute('select resourse,count(*) from jid group by resourse order by -count(*)').fetchall())
		jidbase = []
	elif text == '':
		tlen = len(cu.execute('select resourse,count(*) from jid group by resourse order by -count(*)').fetchall())
		jidbase = cu.execute('select resourse,count(*) from jid group by resourse order by -count(*)').fetchmany(10)
	else:
		text1 = '%'+text+'%'
		tlen = len(cu.execute('select resourse,count(*) from jid where resourse like ? group by resourse order by -count(*)',(text1,)).fetchall())
		jidbase = cu.execute('select resourse,count(*) from jid where resourse like ? group by resourse order by -count(*)',(text1,)).fetchmany(10)
	if not tlen:
		msg = u'Не найдено: '+text
	else:
		if text == '':
			msg = u'Всего ресурсов: '+str(tlen)+' \n'
		else:
			msg = u'Найдено ресурсов: '+str(tlen)+' \n'
		cnt = 1
		for jj in jidbase:
			msg += str(cnt)+'. '+jj[0]+'\t'+str(jj[1])+' \n'
			cnt += 1
		msg = msg[:-2]

        send_msg(type, jid, nick, msg)
	

def info_serv(type, jid, nick, text):
	mdb = sqlite3.connect(mainbase)
	cu = mdb.cursor()
	if text == 'count':
		tlen = len(cu.execute('select server,count(*) from jid group by server order by -count(*)').fetchall())
		jidbase = []
	elif text == '':
		tlen = len(cu.execute('select server,count(*) from jid group by server order by -count(*)').fetchall())
		jidbase = cu.execute('select server,count(*) from jid group by server order by -count(*)').fetchall()
	else:
		text1 = '%'+text+'%'
		tlen = len(cu.execute('select server,count(*) from jid where server like ? group by server order by -count(*)',(text1,)).fetchall())
		jidbase = cu.execute('select server,count(*) from jid where server like ? group by server order by -count(*)',(text1,)).fetchall()
	if not tlen:
		msg = u'Не найдено: '+text
	else:
		if text == '':
			msg = u'Всего серверов: '+str(tlen)+' \n'
		else:
			msg = u'Найдено серверов: '+str(tlen)+' \n'
		for jj in jidbase:
			msg += jj[0]+':'+str(jj[1])+' | '
		msg = msg[:-2]

        send_msg(type, jid, nick, msg)
	

def info_base(type, jid, nick):
        msg = u'Чего искать то будем?'
	if nick != '':
        	msg = u'Ты виден мне как '
                fl = 1
                for base in megabase:
                        if base[1].count(nick):
				if base[0].lower() == jid:
# 0 - конфа
# 1 - ник
# 2 - роль
# 3 - аффиляция
# 4 - jid
#	                        	msg += '\n'+base[0]+' '+base[1]+' '+base[2]+' '+base[3] +' '+base[4]
	                        	msg += base[2]+'/'+base[3]
	                        	fl = 0
                if fl:
                        msg = '\''+nick+u'\' not found!'
        send_msg(type, jid, nick, msg)
	

def info_search(type, jid, nick, text):
        msg = u'Чего искать то будем?'
	if text != '':
		mdb = sqlite3.connect(mainbase)
		cu = mdb.cursor()
		ttext = '%'+text+'%'
		tma = cu.execute('select * from jid where login like ? or server like ? or resourse like ? order by login',(ttext,ttext,ttext)).fetchmany(10)
		if len(tma):
		        msg = u'Найдено:'
			cnd = 1
			for tt in tma:
        		        msg += u'\n'+str(cnd)+'. '+tt[0]+'@'+tt[1]+'/'+tt[2]
				cnd += 1
		else:
			msg = text +u' не найдено!'
	send_msg(type, jid, nick, msg)


def gtmp_search(type, jid, nick, text):
        msg = u'Чего искать то будем?'
	if text != '':
        	msg = u'Найдено:'
                fl = 1
                for mega1 in megabase2:
			for mega2 in mega1:
	                        if mega2.lower().count(text.lower()):
        	                	msg += u'\n'+unicode(mega1[1])+u' is '+unicode(mega1[2])+u'/'+unicode(mega1[3])
					if mega1[4] != 'None':
						msg += u' ('+unicode(mega1[4])+u')'
					msg += ' in '+unicode(mega1[0])
        	                	fl = 0
					break
                if fl:
                        msg = '\''+text+u'\' not found!'
        send_msg(type, jid, nick, msg)
	

def tmp_search(type, jid, nick, text):
        msg = u'Чего искать то будем?'
	if text != '':
        	msg = u'Найдено:'
                fl = 1
                for mega1 in megabase2:
			if getRoom(mega1[0]) == getRoom(jid):
				for mega2 in mega1:
		                        if mega2.lower().count(text.lower()):
        		                	msg += u'\n'+unicode(mega1[1])+u' is '+unicode(mega1[2])+u'/'+unicode(mega1[3])
						if mega1[4] != 'None':
							msg += u' ('+unicode(mega1[4])+u')'
#						msg += ' in '+unicode(mega1[0])
        		                	fl = 0
						break
                if fl:
                        msg = '\''+text+u'\' not found!'
        send_msg(type, jid, nick, msg)


def real_search_owner(type, jid, nick, text):
        msg = u'Чего искать то будем?'
	if text != '':
        	msg = u'Найдено:'
                fl = 1
                for mega1 in megabase:
			if mega1[2] != 'None' and mega1[3] != 'None':
				for mega2 in mega1:
		                        if mega2.lower().count(text.lower()):
	        	                	msg += u'\n'+unicode(mega1[1])+u' is '+unicode(mega1[2])+u'/'+unicode(mega1[3])
						if mega1[4] != 'None':
							msg += u' ('+unicode(mega1[4])+u')'
						msg += ' in '+unicode(mega1[0])
	        	                	fl = 0
						break
                if fl:
                        msg = '\''+text+u'\' not found!'
        send_msg(type, jid, nick, msg)	

def real_search(type, jid, nick, text):
        msg = u'Чего искать то будем?'
	if text != '':
        	msg = u'Найдено:'
                fl = 1
                for mega1 in megabase:
			if mega1[2] != 'None' and mega1[3] != 'None':
				for mega2 in mega1:
		                        if mega2.lower().count(text.lower()):
	        	                	msg += u'\n'+unicode(mega1[1])+u' is '+unicode(mega1[2])+u'/'+unicode(mega1[3])
						msg += ' in '+unicode(mega1[0])
	        	                	fl = 0
						break
                if fl:
                        msg = '\''+text+u'\' not found!'
        send_msg(type, jid, nick, msg)

def isNumber(text):
	try:
		it = int(text,16)
		if it >= 32 and it <= 127:
			return chr(int(text,16))
		else:
#			zz =  '\u'+text
#			zz = zz.decode('utf-16')
			return '?'
	except:
		return 'None'

def rss_replace(ms):
	ms = ms.replace('<br>','\n')
	ms = ms.replace('<br />','\n')
	ms = ms.replace('<br/>','\n')
	ms = ms.replace('\n\r','\n')
	ms = ms.replace('<![CDATA[','')
	ms = ms.replace(']]>','')
	ms = ms.replace('&lt;','<')
	ms = ms.replace('&gt;','>')
	ms = ms.replace('&quot;','\"')
	ms = ms.replace('&apos;','\'')
	ms = ms.replace('&amp;','&')
	ms = ms.replace('&middot;',u'·')
	ms = ms.replace('&nbsp;','')
	ms = ms.replace('&raquo;',u'▼')
	ms = ms.replace('&copy;',u'©')
	mm = ''
	m = 0
	while m<len(ms):
		try:
			if ms[m:m+2] == u'&#':
				if ms[2].lower() == 'x':
					tnum = ms[m+3:ms.find(';',m+3)]
				else:
					tnum = ms[m+2:ms.find(';',m+2)]
				num = isNumber(tnum[:5])
				if num != 'None':
					mm += unicode(num)
					m += 3 + len(tnum)
				else:
					mm += ms[m]
			else:
				mm += ms[m]
		except:
			mm += ms[m]
		m += 1
# &#x2212;
	return mm

def rss_repl_html(ms):
	i=0
	lms = len(ms)
	while i < lms:
		if ms[i] == '<':
			for j in range(i, lms):
				if ms[j] == '>':
					break
			ms = ms[:i] +' '+ ms[j+1:]
			lms = len(ms)
			i -= 1
		i += 1
	return ms

def rss_del_html(ms):
	i=0
	lms = len(ms)
	while i < lms:
		if ms[i] == '<':
			for j in range(i, lms):
				if ms[j] == '>':
					break
			ms = ms[:i] + ms[j+1:]
			lms = len(ms)
			i -= 1
		i += 1
	return ms

def rss_del_nn(ms):
	while ms.count('  '):
		ms = ms.replace('  ',' ')
	ms = ms.replace('\r','')
	ms = ms.replace('\t','')
	ms = ms.replace('\n \n','\n')
	while ms.count('\n\n'):
		ms = ms.replace('\n\n','\n')
	ms += '\n'
	return ms

def html_encode(body):
	encidx = body.find('encoding=')
	if encidx >= 0:
		enc = body[encidx+10:encidx+30]
		enc = enc[:enc.find('?>')-1]
	else:
		encidx = body.find('charset=')
		if encidx >= 0:
			enc = body[encidx+8:encidx+30]
			enc = enc[:enc.find('"')]
		else:
			enc = chardet.detect(body)['encoding']

	if body == None:
		body = ''
	if enc == None or enc == '':
		enc = 'utf-8'
	return unicode(body,enc)

#[room, nick, role, affiliation, jid]

def rss(type, jid, nick, text):
	global feedbase, feeds,	lastfeeds, lafeeds
        msg = u'rss show|add|del|clear|new|get'
	nosend = 0
        text = text.split(' ')
        tl = len(text)

        if tl < 5:
                text.append('!')
                
	mode = text[0].lower() # show | add | del | clear | new | get

	if mode == 'add':
                if tl < 4:
                        msg = 'rss add [http://]url timeH|M [full|body|head]'
                        mode = ''
        elif mode == 'del':
                if tl < 2:
                        msg = 'rss del [http://]url'
                        mode = ''
        elif mode == 'new':
                if tl < 4:
                        msg = 'rss new [http://]url max_feed_humber [full|body|head]'
                        mode = ''
        elif mode == 'get':
                if tl < 4:
                        msg = 'rss get [http://]url max_feed_humber [full|body|head]'
                        mode = ''

	feedbase = getFile(feeds,[])
	lastfeeds = getFile(lafeeds,[])

	if mode == 'clear':
		msg = u'All RSS was cleared!'
		tf = []
		for taa in feedbase:
			if taa[4] != jid:
				tf.append(taa)
		feedbase = tf
		writefile(feeds,str(feedbase))

		tf = []
		for taa in lastfeeds:
			if taa[2] == jid:
				tf.append(taa)
		lastfeeds = tf
		writefile(lafeeds,str(lastfeeds))


	if mode == 'all':
		msg = u'No RSS found!'
		if feedbase != []:
			stt = 1
			msg = u'All schedule feeds:'
			for rs in feedbase:
				msg += u'\n'+getName(rs[4])+'\t'+rs[0]+u' ('+rs[1]+u') '+rs[2]
				lt = rs[3]
				msg += u' '+tZ(lt[2])+u'.'+tZ(lt[1])+u'.'+tZ(lt[0])+u' '+tZ(lt[3])+u':'+tZ(lt[4])+u':'+tZ(lt[5])
				stt = 0
			if stt:
				msg+= u' not found!'

	if mode == 'show':
		msg = u'No RSS found!'
		if feedbase != []:
			stt = 1
			msg = u'Schedule feeds for '+jid+u':'
			for rs in feedbase:
				if rs[4] == jid:
					msg += u'\n'+rs[0]+u' ('+rs[1]+u') '+rs[2]
					lt = rs[3]
					msg += u' '+tZ(lt[2])+u'.'+tZ(lt[1])+u'.'+tZ(lt[0])+u' '+tZ(lt[3])+u':'+tZ(lt[4])+u':'+tZ(lt[5])
					stt = 0
			if stt:
				msg+= u' not found!'

	elif mode == 'add':
                        
		lt=tuple(localtime())
		link = text[1]
		if link[:7] != 'http://':
        	        link = 'http://'+link
        	for dd in feedbase:
                        if dd[0] == link and dd[4] == jid:
                                feedbase.remove(dd)
				break
		feedbase.append([link, text[2], text[3], lt[:6], getRoom(jid)]) # url time mode
		writefile(feeds,str(feedbase))

		msg = u'Add feed to schedule: '+link+u' ('+text[2]+u') '+text[3]
		send_msg(type, jid, nick, msg)

		f = urllib.urlopen(link)
		feed = f.read()
		f.close()

		is_rss_aton = 0
		if feed[:256].count('rss') and feed[:256].count('xml'):
			is_rss_aton = 1
		elif feed[:256].count('http://www.w3.org/2005/Atom') and feed[:256].count('xml'):
			is_rss_aton = 2

		if is_rss_aton:
			feed = html_encode(feed)

			if feed.count('<items>'):
				feed = get_tag(feed,'items')

			if is_rss_aton == 1:
		        	feed = feed.split('<item')
			else:
		        	feed = feed.split('<entry>')

			if len(text) > 3:
				submode = text[3]
			else:
				submode = 'full'

			msg = 'Feeds for '
			if submode[-4:] == '-url':
				submode = submode[:-4]
				urlmode = 1

			else:
				urlmode = 0
				msg += link+' '

	                msg += get_tag(feed[0],'title') + '\n'
			mmsg = feed[1]
			if is_rss_aton==1:
				mmsg = get_tag(mmsg,'title') + '\n'
			else:
				mmsg = ttitle = get_tag(mmsg,'content') + '\n'

			for dd in lastfeeds:
                                if dd[0] == link and dd[2] == jid:
                                        lastfeeds.remove(dd)
					break
			lastfeeds.append([link,mmsg,jid])
			writefile(lafeeds,str(lastfeeds))

			mmsg = feed[1]
			if is_rss_aton==1:
				ttitle = get_tag(mmsg,'title')
				tbody = get_tag(mmsg,'description')
				turl = get_tag(mmsg,'link')
			else:
				ttitle = get_tag(mmsg,'content')
				tbody = get_tag(mmsg,'title')
				tu1 = mmsg.index('<link')
				tu2 = mmsg.find('href=\"',tu1)+6
				tu3 = mmsg.find('\"',tu2)
				turl = mmsg[tu2:tu3]

			msg += u' • '
			if submode == 'full':
				msg += ttitle+ '\n'
				msg += tbody + '\n\n'
			elif submode == 'body':
				msg += tbody + '\n'
			elif submode[:4] == 'head':
				msg += ttitle + '\n'
			if urlmode:
				msg += turl+'\n'

			msg = replacer(msg)

			msg = msg[:-1]
			if submode == 'full':
				msg = msg[:-1]
		else:
			feed = html_encode(feed)
			title = get_tag(feed,'title')
			msg = u'bad url or rss/atom not found at '+link+' - '+title

#---------

	elif mode == 'del':
		link = text[1]
		if link[:7] != 'http://':
        	        link = 'http://'+link

		bedel1 = 0
		for rs in feedbase:
			if rs[0] == link and rs[4] == jid:
				feedbase.remove(rs)
				bedel1 = 1

		bedel2 = 0
		for rs in lastfeeds:
			if rs[0] == link and rs[2] == jid:
				lastfeeds.remove(rs)
				bedel2 = 1

		if bedel1 or bedel2:
			msg = u'Delete feed from schedule: '+link
		if bedel1:
			writefile(feeds,str(feedbase))
		if bedel2:
			writefile(lafeeds,str(lastfeeds))
		else:
			msg = u'Can\'t find in schedule: '+link

	elif mode == 'new' or mode == 'get':
	        link = text[1]
       		if link[:7] != 'http://':
        	        link = 'http://'+link
        	f = urllib.urlopen(link)
        	feed = f.read()
		f.close()

		is_rss_aton = 0
		if feed[:256].count('rss') and feed[:256].count('xml'):
			is_rss_aton = 1
		elif feed[:256].count('http://www.w3.org/2005/Atom') and feed[:256].count('xml'):
			is_rss_aton = 2

		if is_rss_aton:
			feed = html_encode(feed)
			if feed.count('<items>'):
				feed = get_tag(feed,'<items>')

			if is_rss_aton == 1:
		        	feed = feed.split('<item')
			else:
		        	feed = feed.split('<entry>')
	
	        	if len(text) > 2:
	        	        lng = int(text[2])+1
	        	else:
	        	        lng = len(feed)
	        	        
	        	if len(feed) <= lng:
	        	        lng = len(feed)
	        	if lng>=11:
	        	        lng = 11

	        	if len(text) > 3:
	        	        submode = text[3]
	        	else:
	        	        submode = 'full'

			msg = 'Feeds for '
			if submode[-4:] == '-url':
				submode = submode[:-4]
				urlmode = 1
			else:
				urlmode = 0
				msg += link+' '

			tstop = ''
			for ii in lastfeeds:
				if ii[2] == jid and ii[0] == link:
					 tstop = ii[1]
					 tstop = tstop[:-1]

	                msg += get_tag(feed[0],'title') + '\n'
			mmsg = feed[1]
			if is_rss_aton==1:
				mmsg = get_tag(mmsg,'title') + '\n'
			else:
				mmsg = ttitle = get_tag(mmsg,'content') + '\n'

			for dd in lastfeeds:
                                if dd[0] == link and dd[2] == jid:
                                        lastfeeds.remove(dd)
					break
			lastfeeds.append([link,mmsg,jid])
			writefile(lafeeds,str(lastfeeds))

	        	for mmsg in feed[1:lng]:
				if is_rss_aton == 1:
					ttitle = get_tag(mmsg,'title')
					tbody = get_tag(mmsg,'description')
					turl = get_tag(mmsg,'link')
				else:
					ttitle = get_tag(mmsg,'content')
					tbody = get_tag(mmsg,'title')
					tu1 = mmsg.index('<link')
					tu2 = mmsg.find('href=\"',tu1)+6
					tu3 = mmsg.find('\"',tu2)
					turl = mmsg[tu2:tu3]

                                if mode == 'new':
        				if ttitle == tstop:
        					break
        			msg += u' • '
				if submode == 'full':
		        	        msg += ttitle + '\n'
					msg += tbody + '\n\n'
				elif submode == 'body':
					msg += tbody + '\n'
				elif submode[:4] == 'head':
		        	        msg += ttitle+ '\n'
				if urlmode:
					msg += turl+'\n'

                        if mode == 'new':
        		        if mmsg == feed[1] and text[4] == 'silent':
                                        nosend = 1
                                elif mmsg == feed[1] and text[4] != 'silent':
                                        msg = 'New feeds not found! '

			if submode == 'body' or submode == 'head':
				msg = msg[:-1]

			msg = replacer(msg)
			msg = msg[:-1]

			if lng > 1 and submode == 'full':
				msg = msg[:-1]
		else:
			feed = html_encode(feed)
			title = get_tag(feed,'title')
			msg = u'bad url or rss/atom not found at '+link+' - '+title
        if not nosend:
		send_msg(type, jid, nick, msg)
	

#------------------------------------------------

# в начале
# 0 - всем
# 1 - админам\овнерам
# 2 - владельцу бота

# в конце
# 0 - передавать параметры
# 1 - ничего не передавать
# 2 - передавать остаток текста

comms = [(1, u'stats', stats, 1),
	 (1, u'gstats', gstats, 1),
         (2, u'quit', bot_exit, 2),
         (2, u'restart', bot_restart, 2),
         (2, u'update', bot_update, 2),
         (1, u'say', say, 2),
         (0, u'calc', calc, 2),
         (0, u'age', true_age, 2),
         (0, u'seen', seen, 2),
         (1, u'seenjid', seenjid, 2),
         (2, u'exec', execute, 2),
         (2, u'gsay', gsay, 2),
         (0, u'help', helpme, 2),
         (2, u'join', bot_join, 2),
         (2, u'leave', bot_leave, 2),
         (2, u'rejoin', bot_rejoin, 2),
         (2, u'pass', conf_pass, 2),
         (2, u'bot_owner', owner, 2),
         (2, u'bot_ignore', ignore, 2),
         (1, u'where', info_where, 1),
         (1, u'res', info_res, 2),
         (1, u'serv', info_serv, 2),
         (0, u'inbase', info_base, 1),
         (2, u'search', info_search, 2),
         (1, u'look', real_search, 2),
         (2, u'glook', real_search_owner, 2),
         (1, u'tempo', tmp_search, 2),
         (2, u'gtempo', gtmp_search, 2),
         (1, u'rss', rss, 2),
         (0, u'wtfrand', wtfrand, 1),
         (0, u'wtfnames', wtfnames, 2),
         (0, u'wtfcount', wtfcount, 1),
         (0, u'wtfsearch', wtfsearch, 2),
         (2, u'wwtf', wwtf, 2),
         (0, u'wtff', wtff, 2),
         (0, u'wtfp', wtfp, 2),
         (0, u'wtf', wtf, 2),
         (1, u'dfn', dfn, 2),
         (2, u'gdfn', gdfn, 2),
         (1, u'alias', alias, 2),
         (0, u'youtube', youtube, 2),
         (1, u'www', netwww, 2),
         (0, u'wzcity', weather_city, 2),
         (0, u'wzz', weather_raw, 2),
         (0, u'wz', weather, 2),
         (0, u'gis', weather_gis, 2),
         (0, u'commands', info_comm, 1),
         (0, u'bot_uptime', uptime, 1),
         (1, u'info', info, 1),
         (0, u'new', svn_info, 1),
         (0, u'svn', svn_get, 2),
         (1, u'smile', smile, 2),
         (1, u'flood', autoflood, 2),
         (1, u'inban', inban, 2),
         (1, u'censor', censor_status, 2),
         (1, u'inmember', inmember, 2),
         (1, u'inadmin', inadmin, 2),
         (1, u'inowner', inowner, 2),
         (0, u'ver', iq_version, 2),
         (0, u'ping', ping, 2),
         (0, u'time', iq_time, 2),
         (0, u'uptime', iq_uptime, 2),
         (2, u'log', get_log, 2),
         (2, u'limit', conf_limit, 2),
         (2, u'plugin', bot_plugin, 2),
         (0, u'def', defcode, 2),
         (2, u'error', show_error, 2),
         (0, u'whoami', info_access, 1),
         (0, u'whois', info_whois, 2),
         (0, u'disco', disco, 2),
         (0, u'tr', translate, 2),
         (0, u'google', google, 2),
         (0, u'sayto', sayto, 2),
         (0, u'dns', get_dns, 2),
         (0, u'tld', get_tld, 2),
         (0, u'status', status, 2),
         (1, u'whereis', whereis, 2),
	 (1, u'prefix', set_prefix, 2),
	 (1, u'backup', conf_backup, 2),
         (1, u'clear', hidden_clear, 2)]

