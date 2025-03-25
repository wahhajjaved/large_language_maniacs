#!/usr/bin/python
# -*- coding: utf-8 -*-
# $Id: bot.py,v 1.2 2006/10/06 12:30:42 normanr Exp $
#

##
##  Description: Flintus - Chat/XMPP bot
##
##  Author: Anton Goroshkin <antihaos@gmail.com> http://magos-linux.ru
##  Copyright (C) 2013 neobht


import sys,os,json
import xmpp,feedparser
import httplib, urllib
from HTMLParser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []
        self.flag=False
    def handle_starttag(self, tag, attrs):
        self.flag=True
    def handle_endtag(self, tag):
        self.flag=False
    def handle_data(self, data):
        self.fed.append(data)
    def get_data(self):
        return ''.join(self.fed)

###  Взаимодействие с чатом Blab
def Send2Chat(msg,clr,forum,tfrm="3"):
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    server={}
    server['magos']="chat.magos-linux.ru"
#    server['mageia']="chat.mageialinux.ru"

    params[forum]['cp']=msg.encode('utf-8')
    params[forum]['txt_c']=clr
    params[forum]['tfrm']=tfrm

    try:
        conn = httplib.HTTPConnection(server[forum])
        conn.request("POST", "/ajb.php", urllib.urlencode(params[forum]), headers)
        response = conn.getresponse()
    #print response.status, response.reason
        data = response.read()
        return data
        conn.close()
    except:
        print "Error connecting to Blab Chat."
        return "error"

###  Глобальные переменные
params={}
params_file_name="config_params"

forum_magos="magos"
#forum_mageia="mageia"

old_msg={}
msg_chat={}
old_msg_users={}

old_msg[forum_magos]=""
msg_chat[forum_magos]=""
#old_msg[forum_mageia]=""
#msg_chat[forum_mageia]=""

#to_users={}
#forum_use={}
#pref_file_name1="forum_use"
#pref_file_name2="to_users"
users_params={}
pref_file_name="users_params"
online_jab={}

commands={}
i18n={'ru':{},'en':{}}

########################### user handlers start ##################################
i18n['ru']['Помощь']="Доступные команды: %s\n\nОписание команд:%s"
def helpHandler(user,command,args,mess):
    info='''
follow magos/mageia - включить отслеживание форума
unfollow - отключить отслеживание
gethistory 1-20  - показать историю последних сообщений
system time 0-5   - установить формат вывода даты и времени сообщений чата
online - показать пользователей online
bash 0-99 - показать последнюю 0-99 цитату с http://bash.im
help - справка по командам
    '''

    lst=commands.keys()
    lst.remove('empty')
    lst.sort()
    return "Помощь",(', '.join(lst),info)

i18n['en']['gethistory']='%s'
def gethistoryHandler(user,command,args,mess):
    if not users_params.has_key(user.getStripped()): return "Необходимо отслеживать один из форумов: follow magos/mageia "
    msg=Send2Chat('',18,users_params[user.getStripped()]['forum'],users_params[user.getStripped()]['tfrm'])
    parser=MyHTMLParser()
    parser.feed( msg.split('|:|')[0])
    last_id=int(msg.split('|:|')[2])
    try:
        count_h=args and (int(args)>19 and 20 or (int(args)<1 and 1 or int(args))) or 5
    except:
        count_h=5
    msg_hist=parser.get_data().split(str(last_id-count_h+1).zfill(9)+":|:")[1]
    for i in range(last_id-count_h+1,last_id+1):
        msg_hist=msg_hist.replace(str(i).zfill(9)+":|:","\n")
    return "gethistory",'%s'%msg_hist

i18n['en']['send']='--> online jabber users:\n%s\n\n-->online chat users:\n%s'
def onlineHandler(user,command,args,mess):
    if not users_params.has_key(user.getStripped()): return "Необходимо отслеживать один из форумов: follow magos/mageia "
    msg=Send2Chat('',18,users_params[user.getStripped()]['forum'],users_params[user.getStripped()]['tfrm'])
    parser = MyHTMLParser()
    parser.feed( msg.split('|:|')[1])
    online_chat=parser.get_data()

    online_ret=""
    for online in online_jab:
        if online_jab[online]!="":
            online_ret=online_ret+online+"("+online_jab[online]+"), "

    return "send",(online_ret,online_chat)

i18n['en']['error']=u'-->упс... ошибочка!'
i18n['en']['follow']='-->ok'
def followHandler(user,command,args,mess):
    if args not in ["magos"]: return "error"
#    if args not in ["magos","mageia"]: return "error"
    #to_users[user.getStripped()]=user.getStripped()
    #forum_use[user.getStripped()]=args
    if not users_params.has_key(user.getStripped()):
        users_params[user.getStripped()]={}

    if not users_params[user.getStripped()].has_key('tfrm'):
        users_params[user.getStripped()]['tfrm']="3"

    users_params[user.getStripped()]['jid']=user.getStripped()
    users_params[user.getStripped()]['forum']=args

#   if os.path.isfile(pref_file_name1):
#       with open(pref_file_name1, 'w') as pref_file:
#           json.dump(forum_use,pref_file)
#   if os.path.isfile(pref_file_name2):
#       with open(pref_file_name2, 'w') as pref_file:
#           json.dump(to_users,pref_file)
    if os.path.isfile(pref_file_name):
        with open(pref_file_name, 'w') as pref_file:
            json.dump(users_params,pref_file)
    return "follow"


i18n['en']['unfollow']='-->ok'
def unfollowHandler(user,command,args,mess):
#   to_users.pop(user.getStripped())
#   forum_use.pop(user.getStripped())
#   if os.path.isfile(pref_file_name1):
#       with open(pref_file_name1, 'w') as pref_file:
#           json.dump(forum_use,pref_file)
#   if os.path.isfile(pref_file_name2):
#       with open(pref_file_name2, 'w') as pref_file:
#           json.dump(to_users,pref_file)
    users_params.pop(user.getStripped())
    if os.path.isfile(pref_file_name):
        with open(pref_file_name, 'w') as pref_file:
            json.dump(users_params,pref_file)
    return "unfollow"

i18n['en']['empty']=''
def emptyHandler(user,command,args,mess):
    if users_params.has_key(user.getStripped()):
        Send2Chat(user.getStripped()+" "+command+" "+args,18,users_params[user.getStripped()]['forum'],users_params[user.getStripped()]['tfrm'])
        pass
    return "empty"

i18n['en']['bash']='%s'
def bashHandler(user,command,args,mess):
    feed=feedparser.parse("http://bash.im/rss")
    try:
        bash_body=feed['items'][args and ((int(args)<len(feed['items'])) and int(args) or 99) or 0]['summary']
    except:
        bash_body="упс... ошибочка вышла!"
        pass
    return "bash",bash_body.replace("<br />","\n")

i18n['en']['bf']='%s'
def bfHandler(user,command,args,mess):
    try:
        args=args+":"
        arg=args.split(":")
        feed=feedparser.parse("http://blogs.yandex.ru/search.rss?text="+arg[0]+"&ft=all&holdres=mark")
        bf_body=feed['items'][arg[1] and ((int(arg[1])<len(feed['items'])) and int(arg[1]) or 99) or 0]['summary']
    except:
        bf_body="упс... ошибочка вышла!"
        pass
    return "bf",bf_body.replace("<br />","\n")

i18n['en']['system']='%s'
def systemHandler(user,command,args,mess):
    if args == params['system']['shutdown']:
        sys.exit()
    par=args.split(" ")
    if par[0]=="time":
        try:
            if int(par[1])>=0 and int(par[1])<6:
                users_params[user.getStripped()]['tfrm']=par[1]
                if os.path.isfile(pref_file_name):
                    with open(pref_file_name, 'w') as pref_file:
                        json.dump(users_params,pref_file)
                return "system","-->ok"
        except:
            pass
    return "system",u"упс... ошибочка!"

########################### user handlers stop ###################################
############################ bot logic start #####################################
i18n['en']["UNKNOWN COMMAND"]='Unknown command "%s". Try "help"'
i18n['ru']["UNKNOWN COMMAND"]='Неизвестная команда "%s". Список команд: "help"'
i18n['en']["UNKNOWN USER"]="I do not know you. Register first."

def messageCB(conn,mess):
    text=mess.getBody()
    user=mess.getFrom()
    user.lang='ru'      # dup
    if text==None: return
    if text.find(' ')+1: command,args=text.split(' ',1)
    else: command,args=text,''
    cmd=command.lower()

    if commands.has_key(cmd):
        reply=commands[cmd](user,command,args,mess)
    else:
        reply=("UNKNOWN COMMAND",cmd)
        if users_params.has_key(user.getStripped()):
            if users_params[user.getStripped()]['jid'] :
                reply=commands['empty'](user,command,args,mess)

    if type(reply)==type(()):
        key,args=reply
        if i18n[user.lang].has_key(key): pat=i18n[user.lang][key]
        elif i18n['en'].has_key(key): pat=i18n['en'][key]
        else: pat="%s"
        if type(pat)==type(''):
            if  isinstance(args, unicode):
                reply=pat%args.encode('utf-8')
            else:
                reply=pat%args

        else: reply=pat(**args)
    else:
        try: reply=i18n[user.lang][reply]
        except KeyError:
            try: reply=i18n['en'][reply]
            except KeyError: pass
    if reply:
        conn.send(xmpp.Message(mess.getFrom(),reply,'chat'))

for i in globals().keys():
    if i[-7:]=='Handler' and i[:-7].lower()==i[:-7]: commands[i[:-7]]=globals()[i]

############################# bot logic stop #####################################

def StepOn(conn):
    try:
        conn.Process(1)

        #Основной код
        try:
            msg=Send2Chat('',18,forum_magos,3)
            if msg=="error": return 1
            parser = MyHTMLParser()
            parser.feed( msg.split('|:|')[0])
            msg_chat[forum_magos]=parser.get_data().split(msg.split('|:|')[2]+":|:")[1]
            #msg=Send2Chat('',18,forum_mageia,3)
            #if msg=="error": return 1
            #parser = MyHTMLParser()
            #parser.feed( msg.split('|:|')[0])
            #msg_chat[forum_mageia]=parser.get_data().split(msg.split('|:|')[2]+":|:")[1]
        except:
            print "Error get Data from Blab-Chat"
            return 1

    #TODO: надо переделать как-то получше этот кусок
        for k in online_jab:
            online_jab[k]=""

        for jid in conn.Roster.getItems():
            for resources in conn.Roster.getResources(jid):
                jid_full="%s/%s"%(jid,resources)
                online_jab[jid]=str(conn.Roster.getShow(jid_full)==None and "online" or conn.Roster.getShow(jid_full))

        for users in users_params:
            msg=Send2Chat('',18,users_params[users]['forum'],users_params[users]['tfrm'])
            if msg=="error": return 1
            parser = MyHTMLParser()
            parser.feed( msg.split('|:|')[0])
            msg_chat_users=parser.get_data().split(msg.split('|:|')[2]+":|:")[1]

            if old_msg_users.has_key(users):
                if old_msg_users[users].has_key(users_params[users]['forum']):
                    if online_jab.has_key(users_params[users]['jid'].encode("utf-8")):
                        if (old_msg_users[users][users_params[users]['forum']] != msg_chat_users) and (online_jab[users_params[users]['jid']]=="online" ):
                #and    ("Flintus:" not in msg_chat[forum_use[users]]):
                            conn.Roster.Authorize(users_params[users]['jid'])
                            conn.Roster.Subscribe(users_params[users]['jid'])
                            conn.send(xmpp.protocol.Message(users_params[users]['jid'], msg_chat_users,'chat'))

            else:
                old_msg_users[users]={}

            old_msg_users[users][users_params[users]['forum']]=msg_chat_users

#Обработчик для чата
#        if ("‹@Flintus› bash" in msg_chat[forum_magos])and(old_msg[forum_magos] != msg_chat[forum_magos]):
#            feed=feedparser.parse("http://bash.im/rss")
#            try:
#                try:
#                    args=msg_chat[forum_magos].split(" ")[5]
#                except:
#                    args="0"
#                bash_body=feed['items'][args and ((int(args)<len(feed['items'])) and int(args) or 99) or 0]['summary']
#            except:
#                bash_body=u"упс... ошибочка вышла!"
#                pass
#            Send2Chat(bash_body.replace("<br />","\n"),18,forum_magos,3)

    # надо оптимизировать код
#        if ("‹@Flintus› bash" in msg_chat[forum_mageia])and(old_msg[forum_mageia] != msg_chat[forum_mageia]):
#            feed=feedparser.parse("http://bash.im/rss")
#            try:
#                try:
#                    args=msg_chat[forum_mageia].split(" ")[5]
#                except:
#                    args="0"
#                bash_body=feed['items'][args and ((int(args)<len(feed['items'])) and int(args) or 99) or 0]['summary']
#            except:
#                bash_body=u"упс... ошибочка вышла!"
#                pass
#            Send2Chat(bash_body.replace("<br />","\n"),18,forum_mageia,3)



#Эхо между чатами
#   if (old_msg[forum_magos] != msg_chat[forum_magos]) and ('Flintus:' not in msg_chat[forum_magos]) and echo:
#       Send2Chat("MagOS Forum "+msg_chat[forum_magos],18,forum_mageia)
#   if (old_msg[forum_mageia] != msg_chat[forum_mageia]) and ('Flintus:' not in msg_chat[forum_mageia]) and echo:
#       Send2Chat("MRC Forum "+msg_chat[forum_mageia],18,forum_magos)

        old_msg[forum_magos]=msg_chat[forum_magos]
#        old_msg[forum_mageia]=msg_chat[forum_mageia]

    except KeyboardInterrupt: return 0
    return 1

def GoOn(conn):
    while StepOn(conn): pass

#Main program
if len(sys.argv)<3:
    print "Usage: bot.py username@server.net password"
else:
    jid=xmpp.JID(sys.argv[1])
    user,server,password=jid.getNode(),jid.getDomain(),sys.argv[2]

    conn=xmpp.Client(server,debug=[])
    conres=conn.connect()
    if not conres:
        print "Unable to connect to server %s!"%server
        sys.exit(1)
    if conres<>'tls':
        print "Warning: unable to estabilish secure connection - TLS failed!"
    authres=conn.auth(user,password)
    if not authres:
        print "Unable to authorize on %s - check login/password."%server
        sys.exit(1)
    if authres<>'sasl':
        print "Warning: unable to perform SASL auth os %s. Old authentication method used!"%server
    conn.RegisterHandler('message',messageCB)
    conn.sendInitPresence()
    print "Bot started."
#   if os.path.isfile(pref_file_name1):
#       with open(pref_file_name1, 'r') as pref_file:
#           try:
#               forum_use = json.load(pref_file)
#           except:
#               pass

#   if os.path.isfile(pref_file_name2):
#       with open(pref_file_name2, 'r') as pref_file:
#           try:
#               to_users = json.load(pref_file)
#           except:
#               pass
    if os.path.isfile(pref_file_name):
        with open(pref_file_name, 'r') as pref_file:
            try:
                users_params = json.load(pref_file)
            except:
                pass
    if os.path.isfile(params_file_name):
        with open(params_file_name, 'r') as params_file:
            try:
                params = json.load(params_file)
            except:
                pass
    GoOn(conn)
