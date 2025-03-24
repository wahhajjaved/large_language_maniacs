#!/usr/bin/python
# -*- coding: utf -*-

def exec_ute(type, jid, nick, text):
	try: text = remove_sub_space(unicode(eval(text)))
	except Exception, SM:
		try: SM = str(SM)
		except: SM = unicode(SM)
		text = L('I can\'t execute it! Error: %s') % SM[:int(msg_limit/2)]
	send_msg(type, jid, nick, text)

def calc(type, jid, nick, text):
	legal = string.digits + string.letters + '*/+-()=^!<>. '
	ppc = 1	
	if '**' in text or 'pow' in text: ppc = 0
	else:
		for tt in text:
			if tt not in legal:
				ppc = 0
				break
	if ppc:	
		try: text = remove_sub_space(str(eval(re.sub('([^a-zA-Z]|\A)([a-zA-Z])', r'\1math.\2', text))))
		except: text = L('I can\'t calculate it')
	else: text = L('Expression unacceptable!')
	send_msg(type, jid, nick, text)

global execute

if not GT('paranoia_mode'): execute = [(3, 'calc', calc, 2, L('Calculator.')),
								 (9, 'exec', exec_ute, 2, L('Execution of external code.'))]
