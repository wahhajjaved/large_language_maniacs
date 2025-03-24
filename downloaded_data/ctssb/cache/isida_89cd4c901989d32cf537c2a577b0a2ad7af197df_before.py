# -*- coding: utf-8 -*-

rlmas = ((u'&','&amp;'),(u'\"','&quot;'),(u'\'','&apos;'),(u'˜\'','&tilde;'),(u'<','&lt;'),(u'>','&gt;'))

lmass = (('\n','<br>'),('\n','<br />'),('\n','<br/>'),('\n','\n\r'),('','<![CDATA['),('',']]>'),(u'','&nbsp;'),
		(u'','&shy;'),(u'','&ensp;'),(u'','&emsp;'),(u'','&thinsp;'),(u'','&zwnj;'),(u'','&zwj;'))
		
rmass = ((u'\"','&quot;'),(u'\'','&apos;'),(u'˜\'','&tilde;'),
		(u'&','&amp;'),(u'<','&lt;'),(u'>','&gt;'),(u'¡','&iexcl;'),(u'¢','&cent;'),(u'£','&pound;'),
		(u'¤','&curren;'),(u'¥','&yen;'),(u'¦','&brvbar;'),(u'§','&sect;'),(u'¨','&uml;'),(u'©','&copy;'),(u'ª','&ordf;'),
		(u'«','&laquo;'),(u'¬','&not;'),(u'®','&reg;'),(u'¯','&macr;'),(u'°','&deg;'),(u'±','&plusmn;'),
		(u'²','&sup2;'),(u'³','&sup3;'),(u'´','&acute;'),(u'µ','&micro;'),(u'¶','&para;'),(u'·','&middot;'),(u'¸','&cedil;'),
		(u'¹','&sup1;'),(u'º','&ordm;'),(u'»','&raquo;'),(u'¼','&frac14;'),(u'½','&frac12;'),(u'¾','&frac34;'),(u'¿','&iquest;'),
		(u'×','&times;'),(u'÷','&divide;'),(u'À','&Agrave;'),(u'Á','&Aacute;'),(u'Â','&Acirc;'),(u'Ã','&Atilde;'),(u'Ä','&Auml;'),
		(u'Å','&Aring;'),(u'Æ','&AElig;'),(u'Ç','&Ccedil;'),(u'È','&Egrave;'),(u'É','&Eacute;'),(u'Ê','&Ecirc;'),(u'Ë','&Euml;'),
		(u'Ì','&Igrave;'),(u'Í','&Iacute;'),(u'Î','&Icirc;'),(u'Ï','&Iuml;'),(u'Ð','&ETH;'),(u'Ñ','&Ntilde;'),(u'Ò','&Ograve;'),
		(u'Ó','&Oacute;'),(u'Ô','&Ocirc;'),(u'Õ','&Otilde;'),(u'Ö','&Ouml;'),(u'Ø','&Oslash;'),(u'Ù','&Ugrave;'),(u'Ú','&Uacute;'),
		(u'Û','&Ucirc;'),(u'Ü','&Uuml;'),(u'Ý','&Yacute;'),(u'Þ','&THORN;'),(u'ß','&szlig;'),(u'à','&agrave;'),(u'á','&aacute;'),
		(u'â','&acirc;'),(u'ã','&atilde;'),(u'ä','&auml;'),(u'å','&aring;'),(u'æ','&aelig;'),(u'ç','&ccedil;'),(u'è','&egrave;'),
		(u'é','&eacute;'),(u'ê','&ecirc;'),(u'ë','&euml;'),(u'ì','&igrave;'),(u'í','&iacute;'),(u'î','&icirc;'),(u'ï','&iuml;'),
		(u'ð','&eth;'),(u'ñ','&ntilde;'),(u'ò','&ograve;'),(u'ó','&oacute;'),(u'ô','&ocirc;'),(u'õ','&otilde;'),(u'ö','&ouml;'),
		(u'ø','&oslash;'),(u'ù','&ugrave;'),(u'ú','&uacute;'),(u'û','&ucirc;'),(u'ü','&uuml;'),(u'ý','&yacute;'),(u'þ','&thorn;'),
		(u'ÿ','&yuml;'),(u'∀','&forall;'),(u'∂','&part;'),(u'∃','&exists;'),(u'∅','&empty;'),(u'∇','&nabla;'),(u'∈','&isin;'),
		(u'∉','&notin;'),(u'∋','&ni;'),(u'∏','&prod;'),(u'∑','&sum;'),(u'−','&minus;'),(u'∗','&lowast;'),(u'√','&radic;'),
		(u'∝','&prop;'),(u'∞','&infin;'),(u'∠','&ang;'),(u'∧','&and;'),(u'∨','&or;'),(u'∩','&cap;'),(u'∪','&cup;'),
		(u'∫','&int;'),(u'∴','&there4;'),(u'∼','&sim;'),(u'≅','&cong;'),(u'≈','&asymp;'),(u'≠','&ne;'),(u'≡','&equiv;'),
		(u'≤','&le;'),(u'≥','&ge;'),(u'⊂','&sub;'),(u'⊃','&sup;'),(u'⊄','&nsub;'),(u'⊆','&sube;'),(u'⊇','&supe;'),
		(u'⊕','&oplus;'),(u'⊗','&otimes;'),(u'⊥','&perp;'),(u'⋅','&sdot;'),(u'Α','&Alpha;'),(u'Β','&Beta;'),(u'Γ','&Gamma;'),
		(u'Δ','&Delta;'),(u'Ε','&Epsilon;'),(u'Ζ','&Zeta;'),(u'Η','&Eta;'),(u'Θ','&Theta;'),(u'Ι','&Iota;'),(u'Κ','&Kappa;'),
		(u'Λ','&Lambda;'),(u'Μ','&Mu;'),(u'Ν','&Nu;'),(u'Ξ','&Xi;'),(u'Ο','&Omicron;'),(u'Π','&Pi;'),(u'Ρ','&Rho;'),
		(u'Σ','&Sigma;'),(u'Τ','&Tau;'),(u'Υ','&Upsilon;'),(u'Φ','&Phi;'),(u'Χ','&Chi;'),(u'Ψ','&Psi;'),(u'Ω','&Omega;'),
		(u'α','&alpha;'),(u'β','&beta;'),(u'γ','&gamma;'),(u'δ','&delta;'),(u'ε','&epsilon;'),(u'ζ','&zeta;'),(u'η','&eta;'),
		(u'θ','&theta;'),(u'ι','&iota;'),(u'κ','&kappa;'),(u'λ','&lambda;'),(u'μ','&mu;'),(u'ν','&nu;'),(u'ξ','&xi;'),
		(u'ο','&omicron;'),(u'π','&pi;'),(u'ρ','&rho;'),(u'ς','&sigmaf;'),(u'σ','&sigma;'),(u'τ','&tau;'),(u'υ','&upsilon;'),
		(u'φ','&phi;'),(u'χ','&chi;'),(u'ψ','&psi;'),(u'ω','&omega;'),(u'ϑ','&thetasym;'),(u'ϒ','&upsih;'),(u'ϖ','&piv;'),
		(u'Œ','&OElig;'),(u'œ','&oelig;'),(u'Š','&Scaron;'),(u'š','&scaron;'),(u'Ÿ','&Yuml;'),(u'ƒ','&fnof;'),(u'ˆ','&circ;'),
		(u'‎','&lrm;'),(u'‏','&rlm;'),(u'–','&ndash;'),(u'—','&mdash;'),(u'‘','&lsquo;'),(u'’','&rsquo;'),(u'‚','&sbquo;'),
		(u'“','&ldquo;'),(u'”','&rdquo;'),(u'„','&bdquo;'),(u'†','&dagger;'),(u'‡','&Dagger;'),(u'•','&bull;'),(u'…','&hellip;'),
		(u'‰','&permil;'),(u'′','&prime;'),(u'″','&Prime;'),(u'‹','&lsaquo;'),(u'›','&rsaquo;'),(u'‾','&oline;'),(u'€','&euro;'),
		(u'™','&trade;'),(u'←','&larr;'),(u'↑','&uarr;'),(u'→','&rarr;'),(u'↓','&darr;'),(u'↔','&harr;'),(u'↵','&crarr;'),
		(u'⌈','&lceil;'),(u'⌉','&rceil;'),(u'⌊','&lfloor;'),(u'⌋','&rfloor'),(u'◊','&loz;'),(u'♠','&spades;'),(u'♣','&clubs;'),
		(u'♥','&hearts;'),(u'♦','&diams;'))

levl = {'no|limit':0,'visitor|none':1,'visitor|member':2,'participant|none':3,'participant|member':4,
		'moderator|none':5,'moderator|member':6,'moderator|admin':7,'moderator|owner':8,'bot|owner':9}

unlevl = [L('no limit'),L('visitor/none'),L('visitor/member'), L('participant/none'),L('participant/member'),
		  L('moderator/none'),L('moderator/member'),L('moderator/admin'),L('moderator/owner'),L('bot owner')]
		  
unlevltxt = [L('You should be at least %s to do it.'),L('You must be a %s to do it.')]

unlevlnum = [0,0,0,0,0,0,0,0,0,1]
		
def get_level(cjid, cnick):
	access_mode = -2
	jid = 'None'
	for base in megabase:
		if base[1].count(cnick) and base[0].lower()==cjid:
			jid = base[4]
			if base[2]+'|'+base[3] in levl:
				access_mode = levl[base[2]+'|'+base[3]]
				break
	for iib in ignorebase:
		grj = getRoom(jid.lower())
		if iib.lower() == grj:
			access_mode = -1
			break
		if not (iib.count('.')+iib.count('@')) and grj.count(iib.lower()):
			access_mode = -1
			break
	rjid = getRoom(jid)
	if ownerbase.count(rjid): access_mode = 9
	if jid == 'None' and ownerbase.count(getRoom(cjid)): access_mode = 9
	return (access_mode, jid)

def get_scrobble(type, room, nick, text):
	def last_time_short(tm):
		tm = time.localtime(tm)
		tnow = time.localtime()
		if tm[0] != tnow[0]: form = '%d.%m.%Y %H:%M'
		elif tm[1]!=tnow[1] or tm[2]!=tnow[2]: form = '%d.%m %H:%M'
		else: form = '%H:%M'
		return str(time.strftime(form,tm))
	if text == '': text = nick
	text = text.split()
	csize = 3
	if len(text)>1:
		try: csize = int(text[1])
		except: pass
	text = text[0]
	if csize < 1: csize = 1
	elif csize > 10: csize = 10
	jid = getRoom(get_access(room,text)[1])
	if jid == 'None': jid = room
	stb = os.path.isfile(scrobblebase)
	scrobbase = sqlite3.connect(scrobblebase)
	cu_scrobl = scrobbase.cursor()
	if not stb:
		cu_scrobl.execute('''create table tune (jid text, song text, length integer, played integer)''')
		cu_scrobl.execute('''create table nick (jid text, nick text)''')
		scrobbase.commit()
	tune = cu_scrobl.execute('select song,length,played from tune where jid=? order by -played',(jid,)).fetchmany(csize)
	scrobbase.close()
	if tune:
		msg = ''
		for ttune in tune:
			try:
				t_time = int(ttune[1])
				t_min = tZ(t_time/60)
				t_sec = tZ(t_time - int(t_min)*60)
				t_minsec = t_min+':'+t_sec
			except: t_minsec = ttune[1]
			msg += '\n[%s] %s - %s' % (last_time_short(ttune[2]),unescape(ttune[0]),t_minsec)
		if len(msg): msg = 'PEP Scrobbled:' + msg
		else: msg = L('Not found!')
	else: msg = L('Not found!')
	send_msg(type, room, nick, msg)
		
def set_locale(type, jid, nick, text):
	global locales
	if len(text) >= 2:
		text = text.lower()
		if text != 'en':
			lf = loc_folder+text+'.txt'
			if os.path.isfile(lf):
				locales = {}
				lf = readfile(lf).decode('UTF').replace('\r','').split('\n')
				for c in lf:
					if (not c.count('#')) and len(c) and c.count('\t'): locales[c.split('\t',1)[0].replace('\\n','\n').replace('\\t','\t')] = c.split('\t',1)[1].replace('\\n','\n').replace('\\t','\t')
				writefile(loc_file,unicode('\''+text+'\''))
				msg = L('Locale set to: %s') % text
			else: msg = L('Locale not found!')
		else:
			locales = {}
			msg = L('Locale set to: en')
			writefile(loc_file,'\'en\'')
	else: msg = L('Current locale: %s') % getFile(loc_file,'\'en\'')
	send_msg(type, jid, nick, msg)

def match_room(room):
	for tmp in confbase:
		if getRoom(tmp) == room: return True
	return None

def shell_execute(cmd):
	tmp_file = 'tmp'
	try: os.remove(tmp_file)
	except: pass
	try:
		os.system(cmd+' >> '+tmp_file)
		try: body = readfile(tmp_file)
		except: body = L('Command execution error.')
		if len(body):
			enc = chardet.detect(body)['encoding']
			return unicode(body,enc)
		else: return L('ok')
	except Exception, SM: return L('I can\'t execute it! Error: %s') % str(SM)
	
def concat(list):
	result = ''
	for tmp in list: result += tmp
	return result

def get_affiliation(jid,nick):
	xtype = ''
	for base in megabase:
		if base[0].lower() == jid and base[1] == nick:
			xtype = base[3]
			break
	return xtype

def comm_on_off(type, jid, nick, text):
	cof = getFile(conoff,[])
	if len(text):
		if text[:3] == 'on ':
			text = text[3:].lower()
			if len(text):
				if cof.count((jid,text)):
					if get_affiliation(jid,nick) == 'owner' or get_access(jid,nick)[0] == 2:
						cof.remove((jid,text))
						writefile(conoff, str(cof))
						msg = L('Enabled: %s') % text
					else: msg = L('Only conference owner can enable commands!')
				else: msg = L('Command %s is not disabled!') % text
			else: msg = L('What enable?')
		if text[:4] == 'off ':
			if get_affiliation(jid,nick) == 'owner' or get_access(jid,nick)[0] == 2:
				text = text[4:].lower()
				if len(text):
					text = text.split(' ')
					msg_found = ''
					msg_notfound = ''
					msg_offed = ''
					for tex in text:
						fl = 0
						if tex != 'comm':
							for cm in comms:
								if cm[1] == tex:
									fl = 1
									break
						if fl:
							if not cof.count((jid,tex)):
								cof.append((jid,tex))
								writefile(conoff, str(cof))
								msg_found += tex + ', '
							else: msg_offed += tex + ', '
						else: msg_notfound += tex + ', '
					if len(msg_found): msg = L('Disabled commands: %s') % msg_found[:-2]
					else: msg = ''
					if len(msg_offed):
						if msg != '': msg += '\n'
						msg += L('Commands disabled before: %s') % msg_offed[:-2]
					if len(msg_notfound):
						if msg != '': msg += '\n'
						msg += L('Commands not found: %s') % msg_notfound[:-2]
				else: msg = L('What disable?')
			else: msg = L('Only conference owner can disable commands!')
	else:
		msg = ''
		for tmp in cof:
			if tmp[0] == jid: msg += tmp[1] + ', '
		if len(msg): msg = L('Disabled commands: %s') % msg[:-2]
		else: msg = L('Disabled commands not found!')
	send_msg(type, jid, nick, msg)

def reduce_spaces(text):
	if len(text) == text.count(' '): return ''
	elif len(text):
		while text[0] == ' ': text = text[1:]
		while text[-1:] == ' ': text = text[:-1]
	return text

def censor_status(type, jid, nick, text):
	tmode = 0
	if text:
		if text.lower() == L('on'): tmode = 2
		elif text.lower() == L('off'): tmode = 1

	gl_censor = getFile(cns,[(getRoom(jid),0)])
	is_found = 1
	for sm in gl_censor:
		if sm[0] == getRoom(jid):
			if tmode: tsm = (sm[0],tmode-1)
			else: tsm = (sm[0],int(not sm[1]))
			gl_censor.remove(sm)
			gl_censor.append(tsm)
			is_found = 0
			ssta = tsm[1]
	if is_found:
		gl_censor.append((getRoom(jid),1))
		ssta = 1
	msg = L('Censor is %s') % onoff(ssta)
	writefile(cns,str(gl_censor))
	send_msg(type, jid, nick, msg)

def status(type, jid, nick, text):
	if text == '': text = nick
	is_found = None
	for tmp in megabase:
		if tmp[0] == jid and tmp[1] == text:
			is_found = True
			break
	if is_found:
		realjid = getRoom(get_access(jid,text)[1])
		mdb = sqlite3.connect(agestatbase)
		cu = mdb.cursor()
		stat = cu.execute('select message,status from age where jid=? and room=? and nick=?',(realjid,jid,text)).fetchone()
		if stat[1]: msg = L('leave this room.')
		else:
			stat = stat[0].split('\n',4)
			if stat[3] != 'None': msg = stat[3]
			else: msg = 'online'
			if stat[4] != 'None': msg += ' ('+stat[4]+')'
			if stat[2] != 'None': msg += ' ['+stat[2]+'] '
			else: msg += ' [0] '
			if stat[0] != 'None' and stat[1] != 'None': msg += stat[0]+'/'+stat[1]
		if text != nick: msg = text + ' - '+msg
	else: msg = L('I can\'t see %s here...') % text
	send_msg(type, jid, nick, msg)

def replacer(msg):
	msg = rss_replace(msg)
	msg = rss_del_html(msg)
	msg = rss_replace(msg)
	msg = rss_del_nn(msg)
	return msg

def svn_info(type, jid, nick):
	if os.path.isfile(ul): msg = L('Last update:\n%s') % readfile(ul).decode('utf-8')
	else: msg = L('File %s not found!') % ul
	send_msg(type, jid, nick, msg)

def unhtml(page):
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
	return page

def del_space_both(t):
	return del_space_end(del_space_begin(t))
	
def alias(type, jid, nick, text):
	global aliases
	aliases = getFile(alfile,[])
	
	text = text.strip()
	while text.count('  '): text = text.replace('  ',' ')
	mode = del_space_both(text.split(' ',1)[0])
	try: cmd = del_space_both(text.split(' ',1)[1].split('=',1)[0])
	except: cmd = ''
	try: cbody = del_space_both(text.split(' ',1)[1].split('=',1)[1])
	except: cbody = ''
	msg = L('Mode %s not detected!') % mode
	if mode=='add':
		fl = 0
		for i in aliases:
			if i[1] == cmd and i[0] == jid:
				aliases.remove(i)
				fl = 1	
		aliases.append([jid, cmd, cbody])
		if fl: msg = L('Updated:')
		else: msg = L('Added:')
		msg += ' '+cmd+' == '+cbody
	if mode=='del':
		msg = L('Unable to remove %s') % cmd
		for i in aliases:
			if i[1] == cmd and i[0] == jid:
				aliases.remove(i)
				msg = L('Removed %s') % cmd
	if mode=='show':
		msg = ''
		if cmd == '':
			for i in aliases:
				if i[0] == jid: msg += i[1] + ', '
			if len(msg): msg = L('Aliases: %s') % msg[:-2]
			else: msg = L('Aliases not found!')
		else:
			for i in aliases:
				if i[1].lower().count(cmd.lower()) and i[0] == jid: msg += '\n'+i[1]+' = '+i[2]
			if len(msg): msg = L('Aliases: %s') % msg
			else: msg = L('Aliases not found!')
	writefile(alfile,str(aliases))
	send_msg(type, jid, nick, msg)

def fspace(mass):
	bdd = []
	for b in mass:
		if len(b) and len(b) != b.count(' '):
			while b[0] == ' ': b = b[1:]
		bdd.append(b)
	return bdd

def autoflood(type, jid, nick, text):
	tmode = 0
	if text:
		if text.lower() == L('on'): tmode = 2
		elif text.lower() == L('off'): tmode = 1

	floods = getFile(fld,[(getRoom(jid),0)])
	is_found = 1
	for sm in floods:
		if sm[0] == getRoom(jid):
			if tmode: tsm = (sm[0],tmode-1)
			else: tsm = (sm[0],int(not sm[1]))
			floods.remove(sm)
			floods.append(tsm)
			is_found = 0
			ssta = tsm[1]
	if is_found:
		floods.append((getRoom(jid),1))
		ssta = 1
	msg = L('Flood is %s') % onoff(ssta)
	writefile(fld,str(floods))
	send_msg(type, jid, nick, msg)

def del_space_begin(text):
	if len(text):
		while text[:1] == ' ': text = text[1:]
	return text

def del_space_end(text):
	if len(text):
		while text[-1:] == ' ': text = text[:-1]
	return text

def un_unix(val):
	tsec = int(val)-int(val/60)*60
	val = int(val/60)
	tmin = int(val)-int(val/60)*60
	val = int(val/60)
	thour = int(val)-int(val/24)*24
	val = int(val/24)
	tday = int(val)-int(val/30)*30
	val = int(val/30)
	tmonth = int(val)-int(val/12)*12
	tyear = int(val/12)
	ret = tZ(thour)+':'+tZ(tmin)+':'+tZ(tsec)
	if tday or tmonth or tyear:
		ttday = int(str(tday)[-1:])
		try: tttday = int(str(tday)[-2:-1])
		except: tttday = 0
		if tttday == 1: ret = L('%s days %s') % (str(tday),ret)
		else:
			if ttday in [0,5,6,7,8,9]: ret = L('%s days %s') % (str(tday),ret)
			elif ttday in [2,3,4]: ret = L('%s Days %s').lower() % (str(tday),ret)
			else: ret = L('%s day %s') % (str(tday),ret)
	if tmonth or tyear:
		if tmonth in [0,5,6,7,8,9,10,11,12]: ret = L('%s months %s') % (str(tmonth),ret)
		elif tmonth in [2,3,4]: ret = L('%s Months %s').lower() % (str(tmonth),ret)
		else: ret = L('%s month %s') % (str(tmonth),ret)
	if tyear:
		if tyear in [5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]: ret = L('%s years %s') % (str(tyear),ret)
		elif tyear in [2,3,4]: ret = L('%s Years %s').lower() % (str(tyear),ret)
		else: ret = L('%s year %s') % (str(tyear),ret)
	return ret

def close_age_null():
	mdb = sqlite3.connect(agestatbase)
	cu = mdb.cursor()
	cu.execute('delete from age where jid like ?',('<temporary>%',)).fetchall()
	ccu = cu.execute('select * from age where status=? order by room',(0,)).fetchall()
	cu.execute('delete from age where status=?', (0,)).fetchall()
	for ab in ccu: cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (ab[0],ab[1],ab[2],ab[3],ab[4],1,ab[6],ab[7]))
	mdb.commit()

def close_age():
	mdb = sqlite3.connect(agestatbase)
	cu = mdb.cursor()
	cu.execute('delete from age where jid like ?',('<temporary>%',)).fetchall()
	ccu = cu.execute('select * from age where status=? order by room',(0,)).fetchall()
	cu.execute('delete from age where status=?', (0,)).fetchall()
	tt = int(time.time())
	for ab in ccu: cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (ab[0],ab[1],ab[2],tt,ab[4]+(tt-ab[3]),1,ab[6],ab[7]))
	mdb.commit()

def close_age_room(room):
	mdb = sqlite3.connect(agestatbase)
	cu = mdb.cursor()
	cu.execute('delete from age where jid like ?',('<temporary>%',)).fetchall()
	ccu = cu.execute('select * from age where status=? and room=? order by room',(0,room)).fetchall()
	cu.execute('delete from age where status=? and room=?',(0,room)).fetchall()
	tt = int(time.time())
	for ab in ccu: cu.execute('insert into age values (?,?,?,?,?,?,?,?)', (ab[0],ab[1],ab[2],tt,ab[4]+(tt-ab[3]),1,ab[6],ab[7]))
	mdb.commit()

def sfind(mass,stri):
	for a in mass:
		if a.count(stri): return a
	return ''

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
	if prefix != '': return prefix
	else: return L('absent')

def set_prefix(type, jid, nick, text):
	global preffile, prefix

	if text != '': lprefix = text
	if text.lower() == 'none': lprefix = ''
	if text.lower() == 'del': lprefix = prefix

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
	else: lprefix = get_local_prefix(jid)
	msg = L('Command prefix: %s') % get_prefix(lprefix)
	send_msg(type, jid, nick, msg)

def smile(type, jid, nick, text):
	tmode = 0
	if text:
		if text.lower() == L('on'): tmode = 2
		elif text.lower() == L('off'): tmode = 1
	smiles = getFile(sml,[(getRoom(jid),0)])
	is_found = 1
	for sm in smiles:
		if sm[0] == getRoom(jid):
			if tmode: tsm = (sm[0],tmode-1)
			else: tsm = (sm[0],int(not sm[1]))
			smiles.remove(sm)
			smiles.append(tsm)
			is_found = 0
			ssta = tsm[1]
	if is_found:
		smiles.append((getRoom(jid),1))
		ssta = 1
	msg = L('Smiles is %s') % onoff(ssta)
	writefile(sml,str(smiles))
	send_msg(type, jid, nick, msg)

def uptime(type, jid, nick):
	msg = L('Uptime: %s, Last session: %s') % (get_uptime_str(), un_unix(int(time.time())-sesstime))
	send_msg(type, jid, nick, msg)

def show_error(type, jid, nick, text):
	if text.lower() == 'clear': writefile(LOG_FILENAME,'')
	try: cmd = int(text)
	except: cmd = 1
	if os.path.isfile(LOG_FILENAME) and text.lower() != 'clear':
		log = readfile(LOG_FILENAME).decode('UTF')
		log = log.split('ERROR:')
		lll = len(log)
		if cmd > lll: cmd = lll
		msg = L('Total Error(s): %s\n') % str(lll-1)
		if text != '':
			for aa in range(lll-cmd,lll): msg += log[aa]+'\n'
		else: msg += ' '
		msg = msg[:-2]
	else: msg = L('No Errors')
	send_msg(type, jid, nick, msg)

def get_nick_by_jid(room, jid):
	for tmp in megabase:
		if tmp[0] == room and getRoom(tmp[4]) == jid: return tmp[1]
	return None
	
def get_access(cjid, cnick):
	access_mode = -2
	jid = 'None'
	for base in megabase:
		if base[1].count(cnick) and base[0].lower()==cjid:
			jid = base[4]
			if base[3]=='admin' or base[3]=='owner':
				access_mode = 1
				break
			if base[3]=='member' or base[3]=='none':
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
	rjid = getRoom(jid)
	if ownerbase.count(rjid): access_mode = 2
	if (jid == 'None' or jid[:4] == 'j2j.') and ownerbase.count(getRoom(cjid)): access_mode = 2
	return (access_mode, jid)

def info_whois(type, jid, nick, text):
	if text != '': msg = raw_who(jid, text)
	else: msg = L('What?')
	send_msg(type, jid, nick, msg)
		
def info_access(type, jid, nick):
	msg = raw_who(jid, nick)
	send_msg(type, jid, nick, msg)

def raw_who(room,nick):
	ta = get_access(room,nick)
	access_mode = ta[0]
	if access_mode == -2: msg = L('Who do you need?')
	else:
		realjid = ta[1]
		msg = L('Access level: %s') % str(access_mode)
		tb = [L('Ignored'),L('Minimal'),L('Admin/Owner'),L('Bot\'s owner')]
		msg += ', ' + tb[access_mode+1]
		if realjid != 'None': msg = L('%s, jid detected') % msg
		msg = L('%s, Prefix: %s') % (msg,get_prefix(get_local_prefix(room)))
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
		if access_mode >= i[0]: cu.execute('insert into tempo values (?,?)', (unicode(i[1]),i[0]))
	for j in range(0,access_mode+1):
		cm = cu.execute('select * from tempo where am=? order by comm',(j,)).fetchall()
		msg += u'\n• '+str(j)+' ... '
		for i in cm: msg += i[0] +', '
		msg = msg[:-2]
	msg = L('Total commands: %s | Prefix: %s | Your access level: %s | Available commands: %s%s') % (str(len(comms)), get_prefix(get_local_prefix(jid)), str(access_mode), str(len(cu.execute('select * from tempo where am<=?',(access_mode,)).fetchall())), msg)
	tmp.close()
	send_msg(type, jid, nick, msg)
	
def helpme(type, jid, nick, text):
	text = text.lower()
	if text == 'about': msg = u'Isida Jabber Bot | © 2oo9-2o1o Disabler Production Lab. | http://isida-bot.com'
	elif text == 'donation' or text == 'donations': msg = L('Send donation to: %sBest regards, %s') % ('\nYandexMoney: 41001384336826\nWMZ: Z392970180590\nWMR: R378494692310\nWME: E164241657651\n','Disabler')
	elif text == L('access'): msg = L('Bot has 3 access level:\n0 - Available for all.\n1 - For admins/owners.\n2 - Bot\'s settings. Available only for bot owner')
	elif text != '':
		msg = L('Prefix: %s, Available help for commands:\n') % get_prefix(get_local_prefix(jid))
		tmpbase = sqlite3.connect(':memory:')
		cu = tmpbase.cursor()
		cu.execute('''create table tempo (level integer, name text, body text)''')
		for tmp in comms: cu.execute('insert into tempo values (?,?,?)', (tmp[0], tmp[1], tmp[4]))
		cm = cu.execute('select level, body from tempo where name=?',(text,)).fetchone()
		if cm: msg = L('Access level: %s. %s') % (str(cm[0]),cm[1])
		else:
			cm = cu.execute('select * from tempo order by name').fetchall()
			tmpbase.close()
       			for i in range(0,3):
				msg += '['+str(i)+'] '
				for tmp in cm:
					if tmp[0] == i and tmp[2] != '': msg += tmp[1] + ', '
				msg = msg[:-2]+'\n'
	else: msg = L('%sInformation-referral bot%s Help for command: help command') % ('Isida Jabber Bot - ', u' | http://isida-bot.com | © 2oo9-2o1o Disabler Production Lab. | ')
	send_msg(type, jid, nick, msg)

def bot_rejoin(type, jid, nick, text):
	global lastserver, lastnick, confbase
	text=unicode(text)
	domain = getServer(Settings['jid'])
	if len(text): text=unicode(text)
	else: text=jid
	if not text.count('@'): text+='@'+lastserver
	if not text.count('/'): text+='/'+lastnick
	lastserver = getServer(text.lower())
	lastnick = getResourse(text)
	lroom = text
	if arr_semi_find(confbase, getRoom(lroom)) >= 0:
		sm = L('Rejoin by %s') % nick
		leaveconf(text, domain, sm)
		sleep(1)
		zz = joinconf(text, domain)
		while unicode(zz)[:3] == '409':
			sleep(1)
			text += '_'
			zz = joinconf(text, domain)
		sleep(1)
		if zz != None: send_msg(type, jid, nick, L('Error! %s') % zz)
		else:
			confbase = remove_by_half(confbase, getRoom(lroom))
			confbase.append(text)
			writefile(confs,str(confbase))
	else: send_msg(type, jid, nick, L('I have never been in %s') % getRoom(lroom))
		
def remove_by_half(cb,rm):
	for tmp in cb:
		if tmp[:len(rm)] == rm:
			cb.remove(tmp)
			break
	return cb

def bot_join(type, jid, nick, text):
	global lastserver, lastnick, confs, confbase, blacklist_base
	text=unicode(text)
	domain = getServer(Settings['jid'])
	blklist = getFile(blacklist_base, [])
	if text=='' or getRoom(text).count(' '): send_msg(type, jid, nick, L('Wrong arguments!'))
	else:
		if not text.count('@'): text+='@'+lastserver
		if not text.count('/'): text+='/'+lastnick
		if getRoom(text) in blklist: send_msg(type, jid, nick, L('Denied!'))
		else:
			lastserver = getServer(text.lower())
			lastnick = getResourse(text)
			lroom = text.lower().split('/')[0]
			if arr_semi_find(confbase, lroom) == -1:				
				zz = joinconf(text, domain)
				while unicode(zz)[:3] == '409':
					sleep(1)
					text += '_'
					zz = joinconf(text, domain)
				if zz != None: send_msg(type, jid, nick, L('Error! %s') % zz)
				else:
					confbase.append(text)
					writefile(confs,str(confbase))
					send_msg(type, jid, nick, L('Joined to %s') % text)
			elif confbase.count(text): send_msg(type, jid, nick, L('I\'m already in %s with nick %s') % (lroom,lastnick))
			else:
				zz = joinconf(text, domain)
				while unicode(zz)[:3] == '409':
					sleep(0.1)
					text += '_'
					zz = joinconf(text, domain)
				if zz != None: send_msg(type, jid, nick, L('Error! %s') % zz)
				else:
					confbase = remove_by_half(confbase, lroom)
					confbase.append(text)
					#sleep(1)
					#send_msg(type, jid, nick, L('Changed nick in %s to %s') % (lroom,getResourse(text)))
					writefile(confs,str(confbase))

def bot_leave(type, jid, nick, text):
	global confs, confbase, lastserver, lastnick
	domain = getServer(Settings['jid'])
	if len(confbase) == 1: send_msg(type, jid, nick, L('I can\'t leave last room!'))
	else:
		if text == '': text = jid
		if not text.count('@'): text+='@'+lastserver
		if not text.count('/'): text+='/'+lastnick
		lastserver = getServer(text)
		lastnick = getResourse(text)
		if len(text): text=unicode(text)
		else: text=jid
		lroom = text
		if ownerbase.count(getRoom(jid)): nick = getName(jid)
		if arr_semi_find(confbase, getRoom(lroom)) >= 0:
			confbase = arr_del_semi_find(confbase,getRoom(lroom))
			writefile(confs,str(confbase))
			send_msg(type, jid, nick, L('Leave room %s') % text)
			sm = L('Leave room by %s') % nick
			leaveconf(getRoom(text), domain, sm)
		else: send_msg(type, jid, nick, L('I never be in %s') % lroom)

def conf_limit(type, jid, nick, text):
	global msg_limit
	if text!='':
		try: msg_limit = int(text)
		except: msg_limit = 1000
	send_msg(type, jid, nick, L('Temporary message size limit %s') % str(msg_limit))

def bot_plugin(type, jid, nick, text):
	global plname, plugins, execute, gtimer, gpresence, gmassage
	text = text.split(' ')
	do = ''
	nnick = ''
	if len(text)>0: do = text[0]
	if len(text)>1: nnick = text[1]+'.py'
	msg = ''
	if do == 'add':
		if os.path.isfile('plugins/'+nnick):
			pl_ignore = getFile(pliname,[])
			if nnick in pl_ignore:
				pl_ignore.remove(nnick)
				writefile(pliname,str(pl_ignore))
			if not nnick in plugins: plugins.append(nnick)
			presence_control = []
			message_control = []
			iq_control = []
			timer = []
			execfile('plugins/'+nnick)
			msg = ''
			for cm in execute:
				msg += cm[1]+'['+str(cm[0])+'], '
				comms.append((cm[0],cm[1],cm[2],cm[3],L('Plugin %s. %s') % (nnick[:-3],cm[4])))
			msg = L('Loaded plugin: %s\nAdd commands: %s') % (nnick[:-3],msg[:-2])
			for tmr in timer: gtimer.append(tmr)
			for tmp in presence_control: gpresence.append(tmp)
			for tmp in message_control: gmessage.append(tmp)
				
	elif do == 'del':
		if os.path.isfile('plugins/'+nnick):
			pl_ignore = getFile(pliname,[])
			if not nnick in pl_ignore:
				pl_ignore.append(nnick)
				writefile(pliname,str(pl_ignore))
			if nnick in plugins: plugins.remove(nnick)
			presence_control = []
			message_control = []
			iq_control = []
			timer = []
			execfile('plugins/'+nnick)
			msg = ''
			for commmm in execute:
				msg += commmm[1]+'['+str(commmm[0])+'], '
				for i in comms:
					if i[1] == commmm[1]: comms.remove(i)
			msg = L('Unloaded plugin: %s\nDel commands: %s') % (nnick[:-3],msg[:-2])
			for tmr in timer: gtimer.remove(tmr)
			for tmp in presence_control: gpresence.remove(tmp)
			for tmp in message_control: gmessage.remove(tmp)
	elif do == 'local':
		a = os.listdir('plugins/')
		b = []
		for c in a:
			if c[-3:] == u'.py' and c != 'main.py': b.append(c[:-3].decode('utf-8'))
		msg = L('Available plugins: %s') % ', '.join(b)
		pl_ignore = getFile(pliname,[])
		if len(pl_ignore):
			b = []
			for tmp in pl_ignore: b.append(tmp[:-3])
			msg += L('\nIgnored plugins: %s') % ', '.join(b)
	elif do == 'show':
		msg = ''
		for jjid in plugins: msg += jjid[:-3]+', '
		msg = L('Active plugins: %s') % msg[:-2]
		pl_ignore = getFile(pliname,[])
		if len(pl_ignore):
			b = []
			for tmp in pl_ignore: b.append(tmp[:-3])
			msg += L('\nIgnored plugins: %s') % ', '.join(b)
	else: msg = L('Wrong arguments!')
	plugins.sort()
	writefile(plname,unicode(plugins))
	send_msg(type, jid, nick, msg)

def owner(type, jid, nick, text):
	global ownerbase, owners, god
	text = text.lower().strip()
	do = text.split(' ',1)[0]
	try: nnick = text.split(' ',1)[1].lower()
	except:
		if do != 'show':
			send_msg(type, jid, nick, L('Wrong arguments!'))
			return	
	if do == 'add':
		if not ownerbase.count(nnick):
			if nnick.count('@') and nnick.count('.'):
				ownerbase.append(nnick)
				j = Presence(nnick, 'subscribed')
				j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
				sender(j)
				j = Presence(nnick, 'subscribe')
				j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
				sender(j)
				msg = L('Append: %s') % nnick
			else: msg = L('Wrong jid!')
		else: msg = L('%s is alredy in list!') % nnick
	elif do == 'del':
		if ownerbase.count(nnick) and nnick != god:
			ownerbase.remove(nnick)
			j = Presence(nnick, 'unsubscribe')
			j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
			sender(j)
			j = Presence(nnick, 'unsubscribed')
			j.setTag('c', namespace=NS_CAPS, attrs={'node':capsNode,'ver':capsVersion})
			sender(j)
			msg = L('Removed: %s') % nnick
		else: msg = L('Not found!')
	elif do == 'show':
		msg = ''		
		for jjid in ownerbase: msg += jjid+', '
		msg = L('Bot owner(s): %s') % msg[:-2]
	else: msg = L('Wrong arguments!')
	writefile(owners,str(ownerbase))
	send_msg(type, jid, nick, msg)

def ignore(type, jid, nick, text):
	global ignorebase, ignores, god
	text = text.lower().strip()
	do = text.split(' ',1)[0]
	try: nnick = text.split(' ',1)[1].lower()
	except:
		if do != 'show':
			send_msg(type, jid, nick, L('Wrong arguments!'))
			return
	if do == 'add':
		if not ignorebase.count(nnick):
			ignorebase.append(nnick)
			if nnick.count('@') and nnick.count('.'): msg = L('Append: %s') % nnick
			else: msg = L('Append: %s') % '*'+nnick+'*'
		else: msg = L('%s alredy in list!') % nnick
	elif do == 'del':
		if ignorebase.count(nnick) and nnick != god:
			ignorebase.remove(nnick)
			if nnick.count('@') and nnick.count('.'): msg = L('Removed: %s') % nnick
			else: msg = L('Removed: %s') % '*'+nnick+'*'
		else: msg = L('Not found!')
	elif do == 'show':
		msg = ''
		for jjid in ignorebase:
			if jjid.count('@') and jjid.count('.'): msg += jjid+', '
			else: msg += '*'+jjid+'*, '
		msg = L('Ignore list: %s') % msg[:-2]
	else: msg = L('Wrong arguments!')
	writefile(ignores,str(ignorebase))
	send_msg(type, jid, nick, msg)

def info_where(type, jid, nick):
	global confbase
	msg = L('Active conference(s): %s') % str(len(confbase))
	wbase = []
	for jjid in confbase:
		cnt = 0
		rjid = getRoom(jjid)
		for mega in megabase:
			if mega[0] == rjid: cnt += 1
		wbase.append((jjid, cnt))
	for i in range(0,len(wbase)-1):
		for j in range(i,len(wbase)):
			if wbase[i][1] < wbase[j][1]:
				jj = wbase[i]
				wbase[i] = wbase[j]
				wbase[j] = jj
	nmb = 1
	hr = getFile(hide_conf,[])
	hr_count = 0
	for i in wbase:
		if hr.count(getRoom(i[0])): hr_count += 1
		else:
			msg += '\n'+str(nmb)+'. '+i[0]+' ['+str(i[1])+']'
			nmb += 1
	if hr_count: msg += L('\nHidden conference(s): %s') % str(hr_count)
	send_msg(type, jid, nick, msg)

def get_uptime_str():
	return un_unix(int(time.time()-starttime))

def info(type, jid, nick):
	global confbase	
	msg = L('Conference(s): %s (for more info use \'where\' command)\n') % str(len(confbase))
	msg += L('Server: %s | Nick: %s\n') % (lastserver,lastnick)
	msg += L('Message size limit: %s\n') % str(msg_limit)
	msg += L('Local time: %s\n') % timeadd(tuple(localtime()))
	msg += L('Uptime: %s, Last session: %s') % (get_uptime_str(), un_unix(int(time.time())-sesstime))
	smiles = getFile(sml,[(getRoom(jid),0)])
	floods = getFile(fld,[(getRoom(jid),0)])
	gl_censor = getFile(cns,[(getRoom(jid),0)])
	msg += L('\nSmilies: %s | Flood: %s | Censor: %s | Prefix: %s') % (onoff(int((getRoom(jid),1) in smiles)),onoff(int((getRoom(jid),1) in floods)),onoff(int((getRoom(jid),1) in gl_censor)),get_prefix(get_local_prefix(jid)))
	msg += L('\nExecuted threads: %s | Error(s): %s') % (th_cnt,thread_error_count)
	msg += L('\nMessage in: %s | out: %s') % (message_in,message_out)
	msg += L('\nPresence in: %s | out: %s') % (presence_in,presence_out)
	msg += L('\nIq in: %s | out: %s') % (iq_in,iq_out)
	msg += L('\nUnknown out: %s') % unknown_out
	msg += L('\nCycles used: %s | unused: %s') % (cycles_used,cycles_unused)
	send_msg(type, jid, nick, msg)

# 0 - конфа
# 1 - ник
# 2 - роль
# 3 - аффиляция
# 4 - jid

def info_base(type, jid, nick):
	msg = L('What need find?')
	if nick != '':
		msg = ''
		fl = 1
		for base in megabase:
			if base[1] == (nick) and base[0].lower() == jid:
				msg = L('I see you as %s/%s') % (base[2],base[3])
				break
	send_msg(type, jid, nick, msg)

def real_search_owner(type, jid, nick, text):
	msg = L('What need find?')
	if text != '':
		msg = L('Found:')
		fl = 1
		for mega1 in megabase:
			if mega1[2] != 'None' and mega1[3] != 'None':
				for mega2 in mega1:
					if mega2.lower().count(text.lower()):
						msg += u'\n'+unicode(mega1[1])+u' is '+unicode(mega1[2])+u'/'+unicode(mega1[3])
						if mega1[4] != 'None': msg += u' ('+unicode(mega1[4])+u')'
						msg += ' '+unicode(mega1[0])
						fl = 0
						break
		if fl: msg = L('\'%s\' not found!') % text
	send_msg(type, jid, nick, msg)	

def real_search(type, jid, nick, text):
	msg = L('What do you need to find?')
	if text != '':
		msg = L('Found:')
		fl = 1
		for mega1 in megabase:
			if mega1[2] != 'None' and mega1[3] != 'None':
				for mega2 in mega1:
					if mega2.lower().count(text.lower()):
						msg += u'\n'+unicode(mega1[1])+u' - '+unicode(mega1[2])+u'/'+unicode(mega1[3])+ ' '+unicode(mega1[0])
						fl = 0
						break
		if fl: msg = L('\'%s\' not found!') % text
	send_msg(type, jid, nick, msg)

def isNumber(text):
	try:
		it = int(text,16)
		if it >= 32 and it <= 127: return chr(int(text,16))
		else: return '?'
	except: return 'None'

def unescape(text):
	def fixup(m):
		text = m.group(0)
		if text[:2] == "&#":
			try:
				if text[:3] == "&#x": return unichr(int(text[3:-1], 16))
				else: return unichr(int(text[2:-1]))
			except ValueError: pass
		else:
			try: text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
			except KeyError: pass
		return text
	return re.sub("&#?\w+;", fixup, text)	

def html_escape(ms):
	for tmp in rlmas: ms = ms.replace(tmp[0],tmp[1])
	return ms
	
def rss_replace(ms):
	for tmp in lmass: ms = ms.replace(tmp[1],tmp[0])
	for tmp in rmass: ms = ms.replace(tmp[1],tmp[0])
	return unescape(ms)

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
	ms = ms.replace('\r',' ').replace('\t',' ')
	while ms.count('\n '): ms = ms.replace('\n ','\n')
	while len(ms) and (ms[0] == '\n' or ms[0] == ' '): ms = ms[1:]
	while ms.count('\n\n'): ms = ms.replace('\n\n','\n')
	while ms.count('  '): ms = ms.replace('  ',' ')
	while ms.count(u'\n\n•'): ms = ms.replace(u'\n\n•',u'\n•')
	while ms.count(u'• \n'): ms = ms.replace(u'• \n',u'• ')
	return ms.strip()

def html_encode(body):
	encidx = body.find('encoding=')
	if encidx >= 0:
		enc = body[encidx+10:encidx+30]
		if enc.count('"'): enc = enc[:enc.find('"')]
		elif enc.count('\''): enc = enc[:enc.find('\'')]
		elif enc.count('&'): enc = enc[:enc.find('&')]
	else:
		encidx = body.find('charset=')
		if encidx >= 0:
			enc = body[encidx+8:encidx+30]
			if enc.count('"'): enc = enc[:enc.find('"')]
			elif enc.count('\''): enc = enc[:enc.find('\'')]
			elif enc.count('&'): enc = enc[:enc.find('&')]
		else: enc = chardet.detect(body)['encoding']
	if body == None: body = ''
	if enc == None or enc == '' or enc.lower() == 'unicode': enc = 'utf-8'
	try: return smart_encode(body,enc)
	except: return L('Encoding error!')

#[room, nick, role, affiliation, jid]

def rss(type, jid, nick, text):
	global feedbase, feeds,	lastfeeds, lafeeds
	msg = u'rss show|add|del|clear|new|get'
	nosend = None
	text = text.split(' ')
	tl = len(text)
	if tl < 5: text.append('!')
	mode = text[0].lower() # show | add | del | clear | new | get
	if mode == 'add' and tl < 4: msg,mode = 'rss add [http://]url timeH|M [full|body|head]',''
	elif mode == 'del' and tl < 2: msg,mode = 'rss del [http://]url',''
	elif mode == 'new' and tl < 4: msg,mode = 'rss new [http://]url max_feed_humber [full|body|head]',''
	elif mode == 'get' and tl < 4: msg,mode = 'rss get [http://]url max_feed_humber [full|body|head]',''
	lastfeeds = getFile(lafeeds,[])
	if mode == 'clear':
		feedbase = getFile(feeds,[])
		msg, tf = L('All RSS was cleared!'), []
		for taa in feedbase:
			if taa[4] != jid: tf.append(taa)
		feedbase = tf
		writefile(feeds,str(feedbase))
		tf = []
		for taa in lastfeeds:
			if taa[2] == jid: tf.append(taa)
		lastfeeds = tf
		writefile(lafeeds,str(lastfeeds))
	elif mode == 'all':
		feedbase = getFile(feeds,[])
		msg = L('No RSS found!')
		if feedbase != []:
			msg = L('All schedule feeds:')
			for rs in feedbase:
				msg += u'\n'+getName(rs[4])+'\t'+rs[0]+u' ('+rs[1]+u') '+rs[2]
				try: msg += u' - '+time.ctime(rs[3])
				except: msg += u' - Unknown'
	elif mode == 'show':
		feedbase = getFile(feeds,[])
		msg = L('No RSS found!')
		if feedbase != []:
			msg = ''
			for rs in feedbase:
				if rs[4] == jid:
					msg += u'\n'+rs[0]+u' ('+rs[1]+u') '+rs[2]
					try: msg += u' - '+time.ctime(rs[3])
					except: msg += u' - Unknown'
			if len(msg): msg = L('Schedule feeds for %s:%s') % (jid,msg)
			else: msg = L('Schedule feeds for %s not found!') % jid
	elif mode == 'add':
		mdd = ['full','body','head']
		if text[3].split('-')[0] not in mdd: 
			send_msg(type, jid, nick, L('Mode %s not detected!') % text[3])
			return
		feedbase = getFile(feeds,[])
		link = text[1]
		if not link[:10].count('://'): link = 'http://'+link
		for dd in feedbase:
			if dd[0] == link and dd[4] == jid:
				feedbase.remove(dd)
				break
		feedbase.append([link, text[2], text[3], int(time.time()), getRoom(jid)]) # url time mode
		writefile(feeds,str(feedbase))
		msg = L('Add feed to schedule: %s (%s) %s') % (link,text[2],text[3])
		send_msg(type, jid, nick, msg)
		rss(type, jid, nick, 'get %s 1 %s' % (link,text[3]))
	elif mode == 'del':
		feedbase = getFile(feeds,[])
		link = text[1]
		if not link[:10].count('://'): link = 'http://'+link
		msg = L('Can\'t find in schedule: %s') % link
		for rs in feedbase:
			if rs[0] == link and rs[4] == jid:
				feedbase.remove(rs)
				msg = L('Delete feed from schedule: %s') % link
				writefile(feeds,str(feedbase))
				for rs in lastfeeds:
					if rs[0] == link and rs[2] == jid:
						lastfeeds.remove(rs)
						writefile(lafeeds,str(lastfeeds))
						break
				break
	elif mode == 'new' or mode == 'get':
		link = text[1]
		if not link[:10].count('://'): link = 'http://'+link
		try: feed = urllib.urlopen(link).read()
		except: return
		is_rss_aton = 0
		if feed[:256].count('rss') and feed[:256].count('xml'): is_rss_aton = 1
		elif feed[:256].count('rss') and feed[:256].count('version=\"2.0\"'): is_rss_aton = 1
		elif feed[:256].count('http://www.w3.org/2005/Atom') and feed[:256].count('xml'): is_rss_aton = 2
		feed = html_encode(feed)
		if is_rss_aton and feed != L('Encoding error!'):
			if is_rss_aton == 1:
				if feed.count('<item>'): feed = feed.split('<item>')
				else: feed = feed.split('<item ')
			else: feed = feed.split('<entry>')
			if len(text) > 2: lng = int(text[2])+1
			else: lng = len(feed)
			if len(feed) <= lng: lng = len(feed)
			if lng>=11: lng = 11
			if len(text) > 3: submode = text[3]
			else: submode = 'full'
			msg = L('Feeds for')+' '
			if 'url' in submode.split('-'): submode,urlmode = submode.split('-')[0],True
			else:
				urlmode = None
				msg += link+' '
			tstop = ''
			msg += get_tag(feed[0],'title')
			try:
				mmsg = feed[1]
				if is_rss_aton==1: mmsg = get_tag(mmsg,'title') + '\n'
				else: mmsg = get_tag(mmsg,'content').replace('&lt;br&gt;','\n') + '\n'
				for dd in lastfeeds:
					try:
						if dd[0] == link and dd[2] == jid:
							tstop = dd[1]
							tstop = tstop[:-1]
							lastfeeds.remove(dd)
							break
					except: lastfeeds.remove(dd)
				lastfeeds.append([link,mmsg,jid])
				writefile(lafeeds,str(lastfeeds))
				t_msg = []
				for mmsg in feed[1:lng]:
					if is_rss_aton == 1:
						ttitle = get_tag(mmsg,'title')
						tbody = get_tag(mmsg,'description')
						turl = get_tag(mmsg,'link')
					else:
						ttitle = get_tag(mmsg,'content').replace('&lt;br&gt;','\n')
						tbody = get_tag(mmsg,'title').replace('&lt;br&gt;','\n')
						tu1 = mmsg.index('<link')
						tu2 = mmsg.find('href=\"',tu1)+6
						tu3 = mmsg.find('\"',tu2)
						turl = mmsg[tu2:tu3].replace('&lt;br&gt;','\n')
					if mode == 'new' and ttitle == tstop: break
					tsubj,tmsg,tlink = '','',''
					if submode == 'full': tsubj,tmsg = replacer(ttitle),replacer(tbody)
					elif submode == 'body': tmsg = replacer(tbody)
					elif submode == 'head': tsubj = replacer(ttitle)
					else: return
					if urlmode: tlink = turl
					t_msg.append((tsubj,tmsg,tlink))
				t_msg.reverse()
				tmp = ''
				for tm in t_msg: tmp += '!'.join(tm)
				if len(tmp+msg)+len(t_msg)*12 >= msg_limit:
					over = (len(tmp+msg)+len(t_msg)*12.0 - msg_limit) / msg_limit * 100 # overflow in persent
					tt_msg = []
					for tm in t_msg:
						tsubj,tmsg,tlink = tm
						if len(tmsg): tmsg = tmsg[:-int(len(tsubj+tmsg+tlink)/100*over+1)]+'[...]'
						else: tsubj = tsubj[:-int(len(tsubj+tmsg+tlink)/100*over+1)]+'[...]'
						tt_msg.append((tsubj,tmsg,tlink))
					t_msg = tt_msg
				tmp = ''
				for tm in t_msg:
					if submode == 'full': tmp += u'\n\n• %s\n%s' % tm[0:2]
					elif submode == 'body': tmp += u'\n\n• %s' % tm[1]
					elif submode == 'head': tmp += u'\n\n• %s' % tm[0]
					if len(tm[2]): tmp += '\n'+tm[2]
				msg += tmp
				if mode == 'new' and mmsg == feed[1]:
					if text[4] == 'silent': nosend = True
					else: msg = L('New feeds not found!')
			except Exception,SM:
				if text[4] == 'silent': nosend = True
				else: msg = L('Error! %s' % SM)
		else:
			if text[4] == 'silent': nosend = True
			else:
				if feed != L('Encoding error!'): title = get_tag(feed,'title')
				else: title = feed
				msg = L('Bad url or rss/atom not found at %s - %s') % (link,title)
	if not nosend: send_msg(type, jid, nick, msg)

#------------------------------------------------

# в начале
# 0 - всем
# 1 - админам\овнерам
# 2 - владельцу бота

# в конце
# 1 - ничего не передавать
# 2 - передавать остаток текста

comms = [
	 (0, u'help', helpme, 2, L('Help system. Helps without commands: about, donation, access')),
	 (2, u'join', bot_join, 2, L('Join conference.\njoin room[@conference.server.ru[/nick]]')),
	 (2, u'leave', bot_leave, 2, L('Leave conference.\nleave room[@conference.server.ru[/nick]]')),
	 (2, u'rejoin', bot_rejoin, 2, L('Rejoin conference.\nrejoin room[@conference.server.ru[/nick]]')),
	 (2, u'bot_owner', owner, 2, L('Bot owners list.\nbot_owner show\nbot_owner add|del jid')),
	 (2, u'bot_ignore', ignore, 2, L('Black list.\nbot_ignore show\nbot_ignore add|del jid')),
	 (1, u'where', info_where, 1, L('Show conferences.')),
	 (0, u'inbase', info_base, 1, L('Your identification in global base.')),
	 (2, u'look', real_search, 2, L('Search user in conferences where the bot is.')),
	 (2, u'glook', real_search_owner, 2, L('Search user in conferences where the bot is. Also show jid\'s')),
	 (1, u'rss', rss, 2, L('News:\nrss show - show current.\nrss add url time mode - add news.\nrss del url - remove news.\nrss get url feeds mode - get current news.\nrss new url feeds mode - get unread news only.\nrss clear - clear all news in current conference.\nrss all - show all news in all conferences.\n\nurl - url of rss/atom chanel. can set without http://\ntime - update time. number + time identificator. h - hour, m - minute. allowed only one identificator.\nfeeds - number of messages to receive. 10 max.\nmode - receive mode. full - full news, head - only headers, body - only bodies.\nwith -url to be show url of news.')),
	 (1, u'alias', alias, 2, L('Aliases.\nalias add new=old\nalias del|show text')),
	 (0, u'commands', info_comm, 1, L('Show commands list.')),
	 (1, u'comm', comm_on_off, 2, L('Enable/Disable commands.\ncomm - show disable commands\ncomm on command - enable command\ncomm off command1[ command2 command3 ...] - disable one or more command')),
	 (0, u'bot_uptime', uptime, 1, L('Show bot uptime.')),
	 (1, u'info', info, 1, L('Misc information about bot.')),
	 (0, u'new', svn_info, 1, L('Last svn update log')),
	 (1, u'smile', smile, 2, L('Smile action for role/affiliation change\nsmile [on|off]')),
	 (1, u'flood', autoflood, 2, L('Autoanswer\nflood [on|off]')),
	 (1, u'censor', censor_status, 2, L('Censor notification\ncensor [on|off]')),
	 (2, u'limit', conf_limit, 2, L('Set temporary message limit.')),
	 (2, u'plugin', bot_plugin, 2, L('Plugin system.\nplugin show|local\nplugin add|del name')),
	 (2, u'error', show_error, 2, L('Show error(s).\nerror [number|clear]')),
	 (0, u'whoami', info_access, 1, L('Your identification.')),
	 (0, u'whois', info_whois, 2, L('Identification.')),
	 (0, u'status', status, 2, L('Show status.')),
	 (1, u'prefix', set_prefix, 2, L('Set command prefix. Use \'none\' for disabler prefix')),
	 (2, u'set_locale', set_locale, 2, u'Change bot localization.\nset_locale ru|en'),
	 (2, u'tune', get_scrobble, 2, u'PEP Scrobbler. Test version')]
