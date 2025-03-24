#!/usr/bin/python
# -*- coding: utf -*-

watch_time = time.time()
watch_count = 0
watch_reset = True
watch_last_activity = {}

def connect_watch():
	global iq_request, watch_time, game_over, watch_count, bot_exit_type, watch_reset
	if (time.time() - watch_time) > GT('watch_size'):
		watch_time = time.time()
		watch_count += 1
		watch_reset = True
		iqid = get_id()
		i = Node('iq', {'id': iqid, 'type': 'get', 'to':selfjid}, payload = [Node('query', {'xmlns': NS_URN_PING},[])])
		iq_request[iqid]=(time.time(),watcher_reset,['chat',god,'',''])
		sender(i)
		to = GT('timeout') - 10
		while to > 0 and not game_over:
			to -= 1
			sleep(1)
		if watch_reset:
			pprint('Restart by watcher\'s timeout!')
			bot_exit_type, game_over = 'restart', True
			sleep(2)
			
def watch_room_activity():
	if not GT('watcher_room_activity'): return
	global watch_last_activity
	to = int(time.time())-GT('watch_activity_timeout')
	for tmp in confbase:
		try: cw = watch_last_activity[getRoom(tmp)]
		except: cw = to
		if cw < to:
			watch_last_activity[getRoom(tmp)] = int(time.time())
			domain,text = getServer(Settings['jid']),tmp
			zz = joinconf(text, domain)
			while unicode(zz)[:3] == '409':
				sleep(1)
				text += '_'
				zz = joinconf(text, domain)
			sleep(1)
			pprint('Low activity! Try rejoin into %s' % text)

def watcher_reset(a,b,c,d,e):
	global watch_reset
	watch_reset = None
			
def c_watcher(type, jid, nick): send_msg(type, jid, nick, L('Timeout for ask: %s | Timeout for answer: %s | Last ask: %s | Total checks: %s') % (GT('watch_size'),GT('timeout'),un_unix(int(time.time() - watch_time)),watch_count))

def connect_watch_uni(room,jid,nick,type,mass):
	global watch_last_activity
	if jid != 'None': watch_last_activity[getRoom(room)] = int(time.time())

global execute, timer

if GT('iq_version_enable'): timer = [connect_watch,watch_room_activity]
presence_control = [connect_watch_uni]
message_control = [connect_watch_uni]

execute = [(6,'watcher',c_watcher,1,L('Connection activity control.'))]
