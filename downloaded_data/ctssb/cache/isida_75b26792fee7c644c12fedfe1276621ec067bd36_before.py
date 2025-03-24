# -*- coding: utf-8 -*-

def smile(type, jid, nick):
	sml = 'settings/smile'
	if os.path.isfile(sml):
		smiles = eval(readfile(sml))
	else:
		smiles = [(getRoom(jid),0)]
		writefile(sml,str(smiles))
	msg = u'Smiles is '
	is_found = 1
	for sm in smiles:
		if sm[0] == getRoom(jid):
			tsm = (sm[0],not sm[1])
			msg += onoff(not sm[1])
			smiles.remove(sm)
			smiles.append(tsm)
			is_found = 0
	if is_found:
		smiles.append((getRoom(jid),1))
		msg += onoff(1)


	writefile(sml,str(smiles))
        send_msg(type, jid, nick, msg)

def uptime(type, jid, nick):
	msg = u'Время работы: '
	msg += get_uptime_str()

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
        msg = u'За время работы ('+get_uptime_str()+u') я видела всего:'
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
        msg = u'За время работы ('+get_uptime_str()+u') я видела здесь:'
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
	if len(text)>0:
		cmd = int(text)
	else:
		cmd = 1

	if os.path.isfile(LOG_FILENAME):
		log = str(readfile(LOG_FILENAME))
                log = log.split('ERROR:')

                lll = len(log)
        	msg = u'Total Error(s): '+str(lll-1)+', Last:\n'
                for aa in range(lll-cmd,lll):
                        msg += log[aa]+'\n'
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
	logt=localtime()

	if cmd == 'len':
		if arg == '':
			logfile = 'log/'+tZ(logt[0])+tZ(logt[1])+tZ(logt[2])
		else:
			logfile = 'log/'+arg
		if os.path.isfile(logfile):
			log = eval(readfile(logfile))
		else:
			log = []
			writefile(logfile,str(log))
		log_lm = len(str(log))/msg_limit
		msg = u'Log length for '+logfile+' is '+str(len(log))+' record(s) / '+str(log_lm)+' Messages with limit: '+str(msg_limit)
		send_msg(type, jid, nick, msg)
	
	if cmd == 'show':
		if arg == '':
			logfile = 'log/'+tZ(logt[0])+tZ(logt[1])+tZ(logt[2])
		else:
			logfile = 'log/'+arg
		if os.path.isfile(logfile):
			log = eval(readfile(logfile))
		else:
			log = []
			writefile(logfile,str(log))
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

#		print arg1

		arg1 = arg1.split('-')
		log_from = int(arg1[0])
		log_to = int(arg1[1])
		msg = u'Log:'
		for clog in range(log_from, log_to):
			msg += '\n'+log[clog]
		send_msg(type, jid, nick, msg)

def get_access(cjid, cnick):
	access_mode = 0
	jid = 'None'
	if cnick != nickname:
		for base in megabase:
			if base[1].count(cnick) and base[0].lower()==cjid:
				jid = base[4]
				if base[3]==u'admin' or base[3]==u'owner':
        				access_mode = 1

	if ownerbase.count(getRoom(jid)):
		access_mode = 2

	if ignorebase.count(getRoom(jid)):
		access_mode = -1

	if jid == 'None' and ownerbase.count(getRoom(cjid)):
		access_mode = 2

        return (access_mode, jid)


def info_access(type, jid, nick):
	global comms

        ta = get_access(jid,nick)

        access_mode = ta[0]
        realjid =ta[1]

	msg = u'Доступ: '+str(access_mode)
        tb = [u'Минимальный',u'Админ/Владелец конфы',u'Владелец бота']
        msg += ', ' + tb[access_mode]
	
        if realjid != 'None':
                msg += u', jid опознан'

	msg += u', Префикс команд: '+prefix
	send_msg(type, jid, nick, msg)
	

def info_comm(type, jid, nick):
	global comms
	msg = ''
	ccnt = 0
	jidc = comms

	access_mode = 0
	jid2 = 'None'
	if nick != nickname:
		for base in megabase:
			if (base[1].count(nick) and base[0].lower()==jid and (base[3]==u'admin' or base[3]==u'owner')):
				jid2 = base[4]
				access_mode = 1

	if ownerbase.count(getRoom(jid2)):
		access_mode = 2

	if ignorebase.count(getRoom(jid2)):
		access_mode = -1

	if jid2 == 'None' and ownerbase.count(getRoom(jid)):
		access_mode = 2

        accs = [u'всем', u'админам/овнерам', u'владельцу бота']

        for i in range(0,3):
                msg += '['+str(i)+'] '+accs[i]+': '
        	for ccomms in jidc:
        		if not ccomms[1].count(god) and ccomms[0] == i:
#                                ccc = ccomms[1]
#                                if ccc[:len(prefix)] == prefix:
#                                        ccc = ccc[len(prefix):]
#        			msg += ccc +', '
        			msg += ccomms[1] +', '
        			ccnt+= 1
                msg = msg[:-2] + '\n'
			
	msg = u'Команды парсера: '+str(ccnt)+u', Ваш доступ: '+str(access_mode)+u', Префикс: '+prefix+'\n'+msg
	msg = msg[:-1]
	send_msg(type, jid, nick, msg)

def test(type, jid, nick):
	send_msg(type, jid, nick, 'passed')

def test_rus(type, jid, nick):
	send_msg(type, jid, nick, u'две полоски!')
        
def bot_exit(type, jid, nick, text):
	StatusMessage = u'Exit by \'quit\' command from bot owner ('+nick+u')'
	if text != '':
                StatusMessage += ' ['+text+u']'
	send_presence_all(StatusMessage)
	writefile('settings/tmp',str('exit'))
	sleep(3)
        0/0 # :-"

def bot_restart(type, jid, nick, text):
	StatusMessage = u'Restart by \'restart\' command from bot owner ('+nick+u')'
	if text != '':
                StatusMessage += ' ['+text+u']'
	send_presence_all(StatusMessage)
	writefile('settings/tmp',str('restart'))
	sleep(1)
        0/0 # :-"

def bot_update(type, jid, nick, text):
	StatusMessage = u'Self update by \'update\' command from bot owner ('+nick+u')'
	if text != '':
                StatusMessage += ' ['+text+u']'
	send_presence_all(StatusMessage)
	writefile('settings/tmp',str('update'))
	sleep(1)
        0/0 # :-"

def say(type, jid, nick, text):
	nick = ''
	type = 'groupchat'
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
		hlp = hlp.split('[')
		for hh in hlp:
			if len(hh):
				hh = hh.decode('utf-8')
				hhh = hh.split(']')
				helps.append((hhh[0],hhh[1][:-1]))

	mesg = u'Префикс команд: '+prefix+u'\nДоступна справка по командам:\n'

        cnt = 0
        for i in range(0,3):
                mesg += '['+str(i)+'] '
        	for hlp in helps:
                        for cmdd in comms:
				tc = cmdd[1]
				if tc[:len(prefix)]==prefix:
					tc = tc[len(prefix):]
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
				if tc[:len(prefix)]==prefix:
					tc = tc[len(prefix):]
                                if tc == hlp[0]:
                                        fl = 0
                        if fl:
                                mesg += hlp[0] + ', '
                mesg = mesg[:-1]
	mesg = mesg[:-1]

	for hlp in helps:
		if text.lower() == hlp[0]:
			mesg = u'Справочная информация: ' + hlp[1]
			for cmdd in comms:
				tc = cmdd[1]
				if tc[:len(prefix)]==prefix:
					tc = tc[len(prefix):]
                                if tc == hlp[0]:
                                        mesg = u'Уровень доступа: '+str(cmdd[0]) + hlp[1]

	send_msg(type, jid, nick, mesg)

def hidden_clear(type, jid, nick):
        pprint(u'clear: '+unicode(jid)+u' by: '+unicode(nick))
        cntr = 19                
        while (cntr>0):
                cl.send(xmpp.Message(jid, '', "groupchat"))
                time.sleep(1.05)
                cntr=cntr-1
        send_msg(type, jid, nick, u'стирильно!!!')


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
		joinconf(text, domain)
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
                        confbase.append(text)
                        joinconf(text, domain)
                        writefile(confs,str(confbase))
                        send_msg(type, jid, nick, u'зашла в '+text)
                        pprint(u'join to '+text)
                elif confbase.count(text):
                        send_msg(type, jid, nick, u'хватит бухать! Я уже в '+lroom+u' с ником '+lastnick)
                        pprint(u'already in '+text)
		else:
			confbase = arr_del_semi_find(confbase, lroom)
                        confbase.append(text)
			send_msg(type, jid, nick, u'смена ника в '+lroom+u' на '+lastnick)
                        joinconf(text, domain)
                        writefile(confs,str(confbase))
                        pprint(u'change nick '+text)

def bot_leave(type, jid, nick, text):
        global confs, confbase, lastserver, lastnick
        if len(confbase) == 1:
                send_msg(type, jid, nick, u'не могу выйти из последней конфы!')
        else:
		if text == '':
			text = getName(jid)
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
	global plname, plugins, execute
	text = text.split(' ')
	do = ''
	nnick = ''
	if len(text)>0:
		do = text[0]
	if len(text)>1:
		nnick = text[1]
	pprint('plugin '+do+' '+nnick)
	msg = ''
	if do == 'add':
                if not plugins.count(nnick) and os.path.isfile('plugins/'+nnick):
                        plugins.append(nnick)
                        execfile('plugins/'+nnick)
                        msg = u'Загружен плагин: '+nnick+u'\nДоступны комманды: '
                        for commmm in execute:
                                msg += commmm[1]+'['+str(commmm[0])+'], '
                                comms.append(commmm)
                        msg = msg[:-2]
                        
	elif do == 'del':
                if plugins.count(nnick) and os.path.isfile('plugins/'+nnick):
                        plugins.remove(nnick)
                        execfile('plugins/'+nnick)
                        msg = u'Удалён плагин: '+nnick+u'\nУдалены комманды: '
                        for commmm in execute:
                                msg += commmm[1]+'['+str(commmm[0])+'], '
                                for i in comms:
                                        if i[1] == commmm[1]:
                                                comms.remove(i)
                        msg = msg[:-2]

	elif do == 'local':
		a = os.listdir('plugins/')
		b = []
		for c in a:
			if c[-3:] == u'.py' and c != 'main.py':
				b.append(c)
		msg = u'Доступные плагины: '
		for c in b:
				msg += c+', '
		msg = msg[:-2]
		
	else:
		msg = u'Активные плагины: '
		for jjid in plugins:
				msg += jjid+', '
		msg = msg[:-2]


	writefile(plname,str(plugins))
        send_msg(type, jid, nick, msg)

def owner(type, jid, nick, text):
	global ownerbase, owners, god
	do = text[:3]
	nnick = text[4:]
	pprint('owner '+do+' '+nnick)
	if do == 'add':
                if not ownerbase.count(nnick):
                        ownerbase.append(nnick)
	elif do == 'del':
                if ownerbase.count(nnick) and nnick != god:
                        ownerbase.remove(nnick)
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
	nnick = text[4:]
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
			msg += jjid+', '
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
	for i in wbase:
		msg += i[0]+' ['+str(i[1])+']\n'

        msg = msg[:-1]
        send_msg(type, jid, nick, msg)

def get_uptime_raw():
	nowtime = localtime()

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
        msg += u'Сервер: '+lastserver+'\n'
        msg += u'Ник: '+lastnick+'\n'
	msg += u'Лимит размера сообщений: '+str(msg_limit)+'\n'
	msg += u'Время запуска: '+timeadd(starttime)+'\n'
	nowtime = localtime()
	msg += u'Локальное время: '+timeadd(nowtime)+'\n'

	msg += u'Время работы: '
	msg += get_uptime_str()

        send_msg(type, jid, nick, msg)

def info_res(type, jid, nick, text):
	jidb = []
	jidc = []
	for jjid in jidbase:
		jserv = getResourse(jjid)
		if not jidb.count(jserv):
			jidb.append(jserv)
			jidc.append(1)
		else:
			jidc[jidb.index(jserv)] += 1
	msg = u'Уникальных рессурсов: '+str(len(jidb))+u' (Всего: '+str(len(jidbase))+')'
	if text == '':
		for i in range(0,len(jidc)-1):
			for j in range(i,len(jidc)):
				if jidc[i] < jidc[j]:
					jj = jidc[i]
					jidc[i] = jidc[j]
					jidc[j] = jj
					jj = jidb[i]
					jidb[i] = jidb[j]
					jidb[j] = jj
		if len(jidb)>9:
			jidbmax = 10
		else:
			jidbmax = len(jidb)
		for jji in range(0,jidbmax):# jidb:
                        jjid = jidb[jji]
			msg += '\n'+jjid+' '+str(jidc[jidb.index(jjid)])
	else:
                fl = 1
                for jjid in jidb:
                        if jjid.lower().count(text.lower()):
                        	msg += '\n'+jjid+' '+str(jidc[jidb.index(jjid)])
                        	fl = 0
                if fl:
                        msg += '\n'+text+u' Not found!'
        send_msg(type, jid, nick, msg)

def info_serv(type, jid, nick, text):
	jidb = []
	jidc = []
	for jjid in jidbase:
		jserv = getServer(jjid)
		if not jidb.count(jserv):
			jidb.append(jserv)
			jidc.append(1)
		else:
			jidc[jidb.index(jserv)] += 1
	msg = u'Уникальных серверов: '+str(len(jidb))+u' (Всего: '+str(len(jidbase))+')'
	if text == '':
		for i in range(0,len(jidc)-1):
			for j in range(i,len(jidc)):
				if jidc[i] < jidc[j]:
					jj = jidc[i]
					jidc[i] = jidc[j]
					jidc[j] = jj
					jj = jidb[i]
					jidb[i] = jidb[j]
					jidb[j] = jj

		for jjid in jidb:
			msg += ' | '+jjid+':'+str(jidc[jidb.index(jjid)])
	else:
                fl = 1
                for jjid in jidb:
                        if jjid.lower().count(text.lower()):
                        	msg += '\n'+jjid+' '+str(jidc[jidb.index(jjid)])
                        	fl = 0
                if fl:
                        msg += '\n'+text+u' Not found!'
        send_msg(type, jid, nick, msg)

def info_base(type, jid, nick):
        msg = u'Чего искать то будем?'
	if nick != '':
        	msg = u'Найдено:'
                fl = 1
                for base in megabase:
                        if base[1].lower().count(nick.lower()):
				if base[0].lower() == jid:
# 0 - конфа
# 1 - ник
# 2 - роль
# 3 - аффиляция
# 4 - jid
	                        	msg += '\n'+base[0]+' '+base[1]+' '+base[2]+' '+base[3] #+' '+base[4]
	                        	fl = 0
                if fl:
                        msg = '\''+nick+u'\' not found!'
        send_msg(type, jid, nick, msg)

def info_search(type, jid, nick, text):
        msg = u'Чего искать то будем?'
	if text != '':
        	msg = u'Найдено:'
                fl = 1
                for jjid in jidbase:
                        if jjid.lower().count(text.lower()):
                        	msg += '\n'+jjid
                        	fl = 0
                if fl:
                        msg = '\''+text+u'\' not found!'
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
#						if mega1[4] != 'None':
#							msg += u' ('+unicode(mega1[4])+u')'
						msg += ' in '+unicode(mega1[0])
	        	                	fl = 0
						break
                if fl:
                        msg = '\''+text+u'\' not found!'
        send_msg(type, jid, nick, msg)

def rss_replace(ms):
	ms = ms.replace('<br>','\n')
	ms = ms.replace('<br />','\n')
	ms = ms.replace('<br/>','\n')
	ms = ms.replace('<![CDATA[','')
	ms = ms.replace(']]>','')
	ms = ms.replace('&lt;','<')
	ms = ms.replace('&gt;','>')
	ms = ms.replace('&quot;','\"')
	ms = ms.replace('&apos;','\'')
	ms = ms.replace('&amp;','&')
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

#[room, nick, role, affiliation, jid]

feeds = 'settings/feed'
lafeeds = 'settings/lastfeeds'

def rss(type, jid, nick, text):
        msg = u'rss show|add|del|clear|new|get'
	nosend = 0
	text = text.lower()
        text = text.split(' ')
        tl = len(text)

        if tl < 5:
                text.append('!')
                
	mode = text[0] # show | add | del | clear | new | get

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

	if os.path.isfile(feeds):
		feedbase = eval(readfile(feeds))
	else:
		feedbase = []
		writefile(feeds,str(feedbase))

	if os.path.isfile(lafeeds):
		lastfeeds = eval(readfile(lafeeds))
	else:
		lastfeeds = []
		writefile(lafeeds,str(lastfeeds))

	if mode == 'clear':
		msg = u'All RSS was cleared!'
		feedbase = []
		writefile(feeds,str(feedbase))
		lastfeeds = []
		writefile(lafeeds,str(lastfeeds))

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
                        
		lt=localtime()
		link = text[1]
		if link[:7] != 'http://':
        	        link = 'http://'+link
        	for dd in feedbase:
                        if dd[0] == link and dd[4] == jid:
                                feedbase.remove(dd)
		feedbase.append([link, text[2], text[3], lt[:6], jid]) # url time mode
		msg = u'Add feed to schedule: '+link+u' ('+text[2]+u') '+text[3]
		send_msg(type, jid, nick, msg)

		writefile(feeds,str(feedbase))
#---------
		f = urllib.urlopen(link)
		feed = f.read()

		writefile('settings/tempofeed',str(feed))

		if feed[:100].count('rss') and feed[:100].count('xml'):
			encidx = feed.index('encoding=')
			enc = feed[encidx+10:encidx+30]
			enc = enc[:enc.index('?>')-1]
			enc = enc.upper()

			feed = unicode(feed, enc)
			feed = feed.split('<item>')
			msg = 'Feeds for '+link+' '

			lng = 2
			if len(feed) <= lng:
				lng = len(feed)
			if lng>=11:
				lng = 11

			if len(text) > 3:
				submode = text[3]
			else:
				submode = 'full'
			mmsg = feed[0]
			msg += mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]+ '\n'
			mmsg = feed[1]
			mmsg = mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]+ '\n'
			for dd in lastfeeds:
                                if dd[0] == link and dd[2] == jid:
                                        lastfeeds.remove(dd)
			lastfeeds.append([link,mmsg,jid])
			writefile(lafeeds,str(lastfeeds))
			for idx in range(1,lng):
				mmsg = feed[idx]
				if submode == 'full':
					msg += mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]+ '\n'
					msg += mmsg[mmsg.index('<description>')+13:mmsg.index('</description>')] + '\n\n'
				elif submode == 'body':
					msg += mmsg[mmsg.index('<description>')+13:mmsg.index('</description>')] + '\n'
				elif submode[:4] == 'head':
					msg += mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]+ '\n'
			msg = rss_replace(msg)
			msg = rss_del_html(msg)
			msg = rss_replace(msg)
			msg = msg[:-1]
			if lng > 1 and submode == 'full':
				msg = msg[:-1]
		else:
			msg = u'bad url or rss not found!'

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

#		writefile('settings/tempofeed',str(feed))
		if feed[:100].count('rss') and feed[:100].count('xml'):
			encidx = feed.index('encoding=')
			enc = feed[encidx+10:encidx+30]
			enc = enc[:enc.index('?>')-1]
			enc = enc.upper()
		
	        	feed = unicode(feed, enc)
	        	feed = feed.split('<item>')
	        	msg = 'Feeds for '+link+' '
	
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


			tstop = ''
			for ii in lastfeeds:
				if ii[2] == jid and ii[0] == link:
					 tstop = ii[1]
					 tstop = tstop[:-1]

			mmsg = feed[0]
	                msg += mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]+ '\n'
			mmsg = feed[1]
			mmsg = mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]+ '\n'
			for dd in lastfeeds:
                                if dd[0] == link and dd[2] == jid:
                                        lastfeeds.remove(dd)
			lastfeeds.append([link,mmsg,jid])
			writefile(lafeeds,str(lastfeeds))

	        	for idx in range(1,lng):
                                over = idx
	        	        mmsg = feed[idx]
				ttitle = mmsg[mmsg.index('<title>')+7:mmsg.index('</title>')]
#				print '['+ttitle+']-['+tstop+']'
                                if mode == 'new':
        				if ttitle == tstop:
        					break
				if submode == 'full':
		        	        msg += ttitle + '\n'
					msg += mmsg[mmsg.index('<description>')+13:mmsg.index('</description>')] + '\n\n'
				elif submode == 'body':
					msg += mmsg[mmsg.index('<description>')+13:mmsg.index('</description>')] + '\n'
				elif submode[:4] == 'head':
		        	        msg += ttitle+ '\n'

                        if mode == 'new':
        		        if over == 1 and text[4] == 'silent':
                                        nosend = 1
                                elif over == 1 and text[4] != 'silent':
                                        msg = 'New feeds not found! '

			msg = rss_replace(msg)
			msg = rss_del_html(msg)
			msg = rss_replace(msg)

			msg = msg[:-1]

			if lng > 1 and submode == 'full':
				msg = msg[:-1]
		else:
			msg = u'bad url or rss not found!'
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

comms = [(1, prefix+u'stats', stats, 1),
	 (1, prefix+u'gstats', gstats, 1),
         (2, prefix+u'quit', bot_exit, 2),
         (2, prefix+u'restart', bot_restart, 2),
         (2, prefix+u'update', bot_update, 2),
         (1, prefix+u'say', say, 2),
         (2, prefix+u'gsay', gsay, 2),
         (0, u'help', helpme, 2),
         (0, prefix+u'help', helpme, 2),
         (2, prefix+u'join', bot_join, 2),
         (2, prefix+u'leave', bot_leave, 2),
         (2, prefix+u'rejoin', bot_rejoin, 2),
         (2, prefix+u'pass', conf_pass, 2),
         (2, prefix+u'owner', owner, 2),
         (2, prefix+u'ignore', ignore, 2),
         (1, prefix+u'where', info_where, 1),
         (1, prefix+u'res', info_res, 2),
         (1, prefix+u'serv', info_serv, 2),
         (1, prefix+u'inbase', info_base, 1),
         (2, prefix+u'search', info_search, 2),
         (1, prefix+u'look', real_search, 2),
         (1, prefix+u'tempo', tmp_search, 2),
         (2, prefix+u'gtempo', gtmp_search, 2),
         (1, prefix+u'rss', rss, 2),
         (1, prefix+u'commands', info_comm, 1),
         (1, prefix+u'uptime', uptime, 1),
         (1, prefix+u'info', info, 1),
         (1, prefix+u'smile', smile, 1),
#         (2, prefix+u'log', get_log, 2),
         (2, prefix+u'limit', conf_limit, 2),
         (2, prefix+u'plugin', bot_plugin, 2),
         (2, prefix+u'error', show_error, 2),
         (0, prefix+u'whoami', info_access, 1),
         (0, u'whoami', info_access, 1),
         (1, prefix+u'clear', hidden_clear, 1)]
