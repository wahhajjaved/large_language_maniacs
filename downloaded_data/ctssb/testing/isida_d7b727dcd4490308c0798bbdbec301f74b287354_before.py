#!/usr/bin/python
# -*- coding: utf-8 -*-

ANSW_PREV = {}

MIND_FILE = set_folder + 'mind.txt'
EMPTY_FILE = set_folder + 'empty.txt'
ANSWER_FILE = set_folder + 'answer.txt'

list_of_mind = [m.strip() for m in readfile(MIND_FILE).split('\n') if m.strip()]
list_of_answers = readfile(ANSWER_FILE).split('\n')
list_of_empty = readfile(EMPTY_FILE).split('\n')

def addAnswerToBase(tx):
	if not len(tx) or tx.count(' ') == len(tx): return
	mdb = sqlite3.connect(answersbase,timeout=base_timeout)
	answers = mdb.cursor()
	answers.execute('insert into answer values (?,?)', (len(answers.execute('select ind from answer').fetchall())+1,tx))
	mdb.commit()
	mdb.close()

def getRandomAnswer(tx):
	if not len(tx) or tx.count(' ') == len(tx): return None
	mdb = sqlite3.connect(answersbase,timeout=base_timeout)
	answers = mdb.cursor()
	mrand = str(randint(1,len(answers.execute('select ind from answer').fetchall())))
	answ = to_censore(answers.execute('select body from answer where ind=?', (mrand,)).fetchone()[0])
	mdb.close()
	return answ

def getSmartAnswer(text,room):
	if '?' in text: answ = random.choice(list_of_answers).strip()
	else: answ = random.choice(list_of_empty).strip()
	score,sc = 1.5,0
	text = text.upper()
	for answer in list_of_mind:
		s = answer.split('||')
		sc = rating(s[0], text, room)
		if sc > score: score,answ = sc,random.choice(s[1].split('|'))
		elif sc == score: answ = random.choice(s[1].split('|')+[answ])
	return answ.decode('utf-8')

def rating(s, text, room):
	oc,spisok = 0.0,s.decode('utf-8').split('|')
	for _ in spisok:
		if _ in text: oc = oc + 1
		if _ in ANSW_PREV.get(room, ''): oc = oc + 0.5	
	return oc

def getAnswer(text,room,type):
	text = text.strip()
	if get_config(getRoom(room),'flood') in ['random',True]: answ = getRandomAnswer(text)
	else:
		answ = getSmartAnswer(text,room)
		ANSW_PREV[room] = text.upper()
	if type == 'groupchat' and tx == to_censore(tx): addAnswerToBase(text)
	return answ
