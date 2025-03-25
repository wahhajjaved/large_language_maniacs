# -*- coding: utf-8 -*-
import sys
if sys.version_info[0] < 3 or sys.version_info[1] < 6:
    LOGGER.error("You MUST have a python version of at least 3.6!")
    quit(1)
from telethon import TelegramClient, events
from async_generator import aclosing
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChannelBannedRights
from telethon.errors import UserAdminInvalidError
from telethon.errors import ChatAdminRequiredError
from telethon.errors import ChannelInvalidError
from telethon.tl.functions.channels import EditAdminRequest
from telethon.tl.types import ChannelAdminRights
from datetime import datetime, timedelta
import time
import logging
import random, re
import asyncio
import os
from gtts import gTTS
import time
import hastebin
import urbandict
import gsearch
import subprocess
import google_images_download
from datetime import datetime
from requests import get
import wikipedia
import inspect
import platform
import pybase64
import pyfiglet
from googletrans import Translator
from random import randint
from zalgo_text import zalgo
import sqlite3
logging.basicConfig(level=logging.DEBUG)
api_id=os.environ['API_KEY']
api_hash=os.environ['API_HASH']
global SPAM
SPAM=False
global ISAFK
ISAFK=False
global AFKREASON
AFKREASON="No Reason"
global USERS
USERS={}
global SNIPE_TEXT
SNIPE_TEXT=""
global SNIPE_ID
SNIPE_ID=0
global SNIPER
SNIPER=False
global COUNT_MSG
global SPAM_ALLOWANCE
global SPAM_CHAT_ID
SPAM_CHAT_ID=[]
SPAM_ALLOWANCE=3
global MUTING_USERS
MUTING_USERS={}
global MUTED_USERS
MUTED_USERS={}
COUNT_MSG=0
BRAIN_CHECKER=[]
subprocess.run(['rm','-rf','brains.check'], stdout=subprocess.PIPE)
subprocess.run(['wget','https://storage.googleapis.com/project-aiml-bot/brains.check'], stdout=subprocess.PIPE)
db=sqlite3.connect("brains.check")
cursor=db.cursor()
cursor.execute('''SELECT * FROM BRAIN1''')
all_rows = cursor.fetchall()
for i in all_rows:
    BRAIN_CHECKER.append(i[0])
db.close()
WIDE_MAP = dict((i, i + 0xFEE0) for i in range(0x21, 0x7F))
WIDE_MAP[0x20] = 0x3000
bot = TelegramClient('userbot', api_id, api_hash)
bot.start()
if not os.path.exists('filters.db'):
     db= sqlite3.connect("filters.db")
     cursor=db.cursor()
     cursor.execute('''CREATE TABLE FILTER(chat_id INTEGER,filter TEXT, reply TEXT)''')
     cursor.execute('''CREATE TABLE NOTES(chat_id INTEGER,note TEXT, reply TEXT)''')
     db.commit()
     db.close()
if not os.path.exists("spam_mute.db"):
     db= sqlite3.connect("spam_mute.db")
     cursor=db.cursor()
     cursor.execute('''CREATE TABLE SPAM(chat_id INTEGER,sender INTEGER)''')
     cursor.execute('''CREATE TABLE MUTE(chat_id INTEGER,sender INTEGER)''')
     db.commit()
     db.close()
@bot.on(events.NewMessage(outgoing=True,pattern='.*'))
@bot.on(events.MessageEdited(outgoing=True))
async def common_outgoing_handler(e):
    find = e.text
    find = str(find[1:])
    if find=="delmsg" :
        i=1
        async for message in bot.iter_messages(e.chat_id,from_user='me'):
            if i>2:
                break
            i=i+1
            await message.delete()
    elif find == "shg":
        await e.edit("¯\_(ツ)_/¯")
    elif find == "get userbotfile":
        file=open(sys.argv[0], 'r')
        await bot.send_file(e.chat_id, sys.argv[0], reply_to=e.id, caption='`Here\'s me in a file`')
        file.close()
    elif find == "reportbug":
        await e.edit("Report bugs here: @userbot_support")
    elif find == "help":
        await e.edit('https://github.com/baalajimaestro/Telegram-UserBot/blob/master/README.md')
    elif find == "repo":
        await e.edit('https://github.com/baalajimaestro/Telegram-UserBot/')
    elif find == "supportchannel":
        await e.edit('t.me/maestro_userbot_channel')
    elif find == "thanos":
        rights = ChannelBannedRights(
                             until_date=None,
                             view_messages=True,
                             send_messages=True,
                             send_media=True,
                             send_stickers=True,
                             send_gifs=True,
                             send_games=True,
                             send_inline=True,
                             embed_links=True
                             )
        if (await e.get_reply_message()).sender_id in BRAIN_CHECKER:
            await e.edit("`Ban Error! Couldn\'t ban this user`")
            return
        await e.edit("`Thanos snaps!`")
        time.sleep(5)
        try:
            await bot(EditBannedRequest(e.chat_id,(await e.get_reply_message()).sender_id,rights))
        except UserAdminInvalidError:
          if e.sender_id in BRAIN_CHECKER:
             await e.edit('<triggerban> '+str((await e.get_reply_message()).sender_id))
               return
        except ChatAdminRequiredError:
         if e.sender_id in BRAIN_CHECKER:
             await e.edit('<triggerban> '+str((await e.get_reply_message()).sender_id))
              return
        except ChannelInvalidError:
          if e.sender_id in BRAIN_CHECKER:
             await e.edit('<triggerban> '+(await e.get_reply_message()).sender_id)
               return
        await e.delete()
    elif find == "addsudo":
        if e.sender_id==BRAIN_CHECKER[0]:
            db=sqlite3.connect("brains.check")
            cursor=db.cursor()
            id=(await e.get_reply_message()).sender_id
            cursor.execute('''INSERT INTO BRAIN1 VALUES(?)''',(id,))
            db.commit()
            await e.edit("```Added to Sudo Successfully```")
            db.close()
    elif find == 'del':
        (await e.get_reply_message()).delete()
        await e.delete()
    elif find == "spider":
        if (await e.get_reply_message()).sender_id in BRAIN_CHECKER:
            await e.edit("`Mute Error! Couldn\'t mute this user`")
            return
        db=sqlite3.connect("spam_mute.db")
        cursor=db.cursor()
        cursor.execute('''INSERT INTO MUTE VALUES(?,?)''', (int(e.chat_id),int((await e.get_reply_message()).sender_id)))
        db.commit()
        db.close()
        await e.edit("`Spiderman nabs him!`")
        time.sleep(5)
        await e.delete()
        await bot.send_file(e.chat_id,"https://image.ibb.co/mNtVa9/ezgif_2_49b4f89285.gif")
    elif find == "wizard":
        rights = ChannelAdminRights(
        add_admins=True,
        invite_users=True,
        change_info=True,
        ban_users=True,
        delete_messages=True,
        pin_messages=True,
        invite_link=True,
        )
        await e.edit("`Wizard waves his wand!`")
        time.sleep(3)
        await bot(EditAdminRequest(e.chat_id,(await e.get_reply_message()).sender_id,rights))
        await e.edit("A perfect magic has happened!")
    elif find == "nosnipe":
            global SNIPE_TEXT
            global SNIPER
            global SNIPER_ID
            SNIPER=False
            SNIPE_TEXT=""
            SNIPER_ID=0
            await e.edit('`Sniping Turned Off!`')
    elif find == "asmoff":
        global SPAM
        SPAM=False
        await e.edit("Spam Tracking turned off!")
        db=sqlite3.connect("spam_mute.db")
        cursor=db.cursor()
        cursor.execute('''DELETE FROM SPAM WHERE chat_id<0''')
        db.commit()
        db.close()
    elif find == "rmfilters":
        await e.edit("```Will be kicking away all Marie filters.```")
        time.sleep(3)
        r = await e.get_reply_message()
        filters = r.text.split('-')[1:]
        for filter in filters:
            await e.reply('/stop %s' % (filter.strip()))
            await asyncio.sleep(0.3)
        await e.respond('/filter filters @baalajimaestro kicked them all')
        await e.respond("```Successfully cleaned Marie filters yaay!```\n Gimme cookies @baalajimaestro")
    elif find == "rmnotes":
        await e.edit("```Will be kicking away all Marie notes.```")
        time.sleep(3)
        r = await e.get_reply_message()
        filters = r.text.split('-')[1:]
        for filter in filters:
            await e.reply('/clear %s' % (filter.strip()))
            await asyncio.sleep(0.3)
        await e.respond('/save save @baalajimaestro kicked them all')
        await e.respond("```Successfully cleaned Marie notes yaay!```\n Gimme cookies @baalajimaestro")
    elif find=="rekt":
        await e.edit("Get Rekt man! ( ͡° ͜ʖ ͡°)")
    elif find=="speed":
            l=await e.reply('`Running speed test . . .`')
            k=subprocess.run(['speedtest-cli'], stdout=subprocess.PIPE)
            await l.edit('`' + k.stdout.decode()[:-1] + '`')
            await e.delete()
    elif find == "alive":
        await e.edit("`Master! I am alive😁`")
    elif find=="notafk":
        global ISAFK
        global COUNT_MSG
        global USERS
        global AFKREASON
        ISAFK=False
        await e.edit("I have returned from AFK mode.")
        await e.respond("`You had recieved "+str(COUNT_MSG)+" messages while you were away. Check log for more details. This auto-generated message shall be self destructed in 2 seconds.`")
        time.sleep(2)
        i=1
        async for message in bot.iter_messages(e.chat_id,from_user='me'):
            if i>1:
                break
            i=i+1
            await message.delete()
        await bot.send_message(-1001200493978,"You had recieved "+str(COUNT_MSG)+" messages from "+str(len(USERS))+" chats while you were away")
        for i in USERS:
            await bot.send_message(-1001200493978,str(i)+" sent you "+"`"+str(USERS[i])+" messages`")
        COUNT_MSG=0
        USERS={}
        AFKREASON="No reason"
    elif find=="runs":
        reactor=['Runs to Modi for Help','Runs to Donald Trumpet for help','Runs to Kaala','Runs to Thanos','Runs far, far away from earth','Running faster than usian bolt coz I\'mma Bot','Runs to Marie']
        index=randint(0,len(reactor)-1)
        reply_text=reactor[index]
        await e.edit(reply_text)
        await bot.send_message(-1001200493978,"You ran away from a cancerous chat")
    elif find=="react":
        reactor=['ʘ‿ʘ','ヾ(-_- )ゞ','(っ˘ڡ˘ς)','(´ж｀ς)','( ಠ ʖ̯ ಠ)','(° ͜ʖ͡°)╭∩╮','(ᵟຶ︵ ᵟຶ)','(งツ)ว','ʚ(•｀','(っ▀¯▀)つ','(◠﹏◠)','( ͡ಠ ʖ̯ ͡ಠ)','( ఠ ͟ʖ ఠ)','(∩｀-´)⊃━☆ﾟ.*･｡ﾟ','(⊃｡•́‿•̀｡)⊃','(._.)','{•̃_•̃}','(ᵔᴥᵔ)','♨_♨','⥀.⥀','ح˚௰˚づ ','(҂◡_◡)','ƪ(ړײ)‎ƪ​​','(っ•́｡•́)♪♬','◖ᵔᴥᵔ◗ ♪ ♫ ','(☞ﾟヮﾟ)☞','[¬º-°]¬','(Ծ‸ Ծ)','(•̀ᴗ•́)و ̑̑','ヾ(´〇`)ﾉ♪♪♪','(ง\'̀-\'́)ง','ლ(•́•́ლ)','ʕ •́؈•̀ ₎','♪♪ ヽ(ˇ∀ˇ )ゞ','щ（ﾟДﾟщ）','( ˇ෴ˇ )','눈_눈','(๑•́ ₃ •̀๑) ','( ˘ ³˘)♥ ','ԅ(≖‿≖ԅ)','♥‿♥','◔_◔','⁽⁽ଘ( ˊᵕˋ )ଓ⁾⁾','乁( ◔ ౪◔)「      ┑(￣Д ￣)┍','( ఠൠఠ )ﾉ','٩(๏_๏)۶','┌(ㆆ㉨ㆆ)ʃ','ఠ_ఠ','(づ｡◕‿‿◕｡)づ','(ノಠ ∩ಠ)ノ彡( \\o°o)\\','“ヽ(´▽｀)ノ”','༼ ༎ຶ ෴ ༎ຶ༽','｡ﾟ( ﾟஇ‸இﾟ)ﾟ｡','(づ￣ ³￣)づ','(⊙.☉)7','ᕕ( ᐛ )ᕗ','t(-_-t)','(ಥ⌣ಥ)','ヽ༼ ಠ益ಠ ༽ﾉ','༼∵༽ ༼⍨༽ ༼⍢༽ ༼⍤༽','ミ●﹏☉ミ','(⊙_◎)','¿ⓧ_ⓧﮌ','ಠ_ಠ','(´･_･`)','ᕦ(ò_óˇ)ᕤ','⊙﹏⊙','(╯°□°）╯︵ ┻━┻','¯\_(⊙︿⊙)_/¯','٩◔̯◔۶','°‿‿°','ᕙ(⇀‸↼‶)ᕗ','⊂(◉‿◉)つ','V•ᴥ•V','q(❂‿❂)p','ಥ_ಥ','ฅ^•ﻌ•^ฅ','ಥ﹏ಥ','（ ^_^）o自自o（^_^ ）','ಠ‿ಠ','ヽ(´▽`)/','ᵒᴥᵒ#','( ͡° ͜ʖ ͡°)','┬─┬﻿ ノ( ゜-゜ノ)','ヽ(´ー｀)ノ','☜(⌒▽⌒)☞','ε=ε=ε=┌(;*´Д`)ﾉ','(╬ ಠ益ಠ)','┬─┬⃰͡ (ᵔᵕᵔ͜ )','┻━┻ ︵ヽ(`Д´)ﾉ︵﻿ ┻━┻','¯\_(ツ)_/¯','ʕᵔᴥᵔʔ','(`･ω･´)','ʕ•ᴥ•ʔ','ლ(｀ー´ლ)','ʕʘ̅͜ʘ̅ʔ','（　ﾟДﾟ）','¯\(°_o)/¯','(｡◕‿◕｡)']
        index=randint(0,len(reactor))
        reply_text=reactor[index]
        await e.edit(reply_text)
    elif find == "fastpurge":
        chat = await e.get_input_chat()
        msgs = []
        count =0
        async with aclosing(bot.iter_messages(chat, min_id=e.reply_to_msg_id)) as h:
         async for m in h:
             msgs.append(m)
             count=count+1
             if len(msgs) == 100:
                 await bot.delete_messages(chat, msgs)
                 msgs = []
        if msgs:
         await bot.delete_messages(chat, msgs)
        await bot.send_message(e.chat_id,"`Fast Purge Complete!\n`Purged "+str(count)+" messages. **This auto-generated message shall be self destructed in 2 seconds.**")
        await bot.send_message(-1001200493978,"Purge of "+str(count)+" messages done successfully.")
        time.sleep(2)
        i=1
        async for message in bot.iter_messages(e.chat_id,from_user='me'):
             if i>1:
                 break
             i=i+1
             await message.delete()
    elif find == "restart":
        await e.edit("`Thank You master! I am taking a break!`")
        os.execl(sys.executable, sys.executable, *sys.argv)
    elif find == "pingme":
        start = datetime.now()
        await e.edit('Pong!')
        end = datetime.now()
        ms = (end - start).microseconds/1000
        await e.edit('Pong!\n%sms' % (ms))
'''@bot.on(events.NewMessage(outgoing=True, pattern='.fig'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.fig'))
async def figlet(e):
    text= e.text                        #useless
    text = text[5:]
    res = pyfiglet.figlet_format(text)
    print(res)
    await e.respond(res)
    await e.edit(res)'''
@bot.on(events.NewMessage(incoming=True))
@bot.on(events.MessageEdited(incoming=True))
async def common_incoming_handler(e):
    global SNIPE_TEXT
    global SNIPER
    global SNIPE_ID
    global SPAM
    global MUTING_USERS
    global SPAM_ALLOWANCE
    if SPAM:
      db=sqlite3.connect("spam_mute.db")
      cursor=db.cursor()
      cursor.execute('''SELECT * FROM SPAM''')
      all_rows = cursor.fetchall()
      for row in all_rows:
        if int(row[0]) == int(e.chat_id):
            if int(row[1]) == int(e.sender_id):
                await e.delete()
                return
    db=sqlite3.connect("spam_mute.db")
    cursor=db.cursor()
    cursor.execute('''SELECT * FROM MUTE''')
    all_rows = cursor.fetchall()
    for row in all_rows:
       if int(row[0]) == int(e.chat_id):
          if int(row[1]) == int(e.sender_id):
            await e.delete()
            return
    if SNIPER:
         if SNIPE_ID == e.chat_id:
             if SNIPE_TEXT in e.text:
                  await e.delete()
    if SPAM:
        if e.sender_id not in MUTING_USERS:
                  MUTING_USERS={}
                  MUTING_USERS.update({e.sender_id:1})
        if e.sender_id in MUTING_USERS:
                     MUTING_USERS[e.sender_id]=MUTING_USERS[e.sender_id]+1
                     if MUTING_USERS[e.sender_id]>SPAM_ALLOWANCE:
                         db=sqlite3.connect("spam_mute.db")
                         cursor=db.cursor()
                         cursor.execute('''INSERT INTO SPAM VALUES(?,?)''', (int(e.chat_id),int(e.sender_id)))
                         db.commit()
                         db.close()
                         await bot.send_message(e.chat_id,"`Spammer Nibba was muted.`")
                         return
                         if e.chat_id > 0:
                             await bot.send_message(e.chat_id,"`Boss! I am not trained to deal with people spamming on PM.\n I request to take action with **Report Spam** button`")
                             return
    if e.text == '.killme':
        name = await bot.get_entity(e.from_id)
        name0 = str(name.first_name)
        await e.reply('**K I L L  **[' + name0 + '](tg://user?id=' + str(e.from_id) + ')**\n\nP L E A S E\n\nE N D  T H E I R  S U F F E R I N G**')
@bot.on(events.NewMessage(incoming=True))
@bot.on(events.MessageEdited(incoming=True))
async def filter_incoming_handler(e):
    db=sqlite3.connect("filters.db")
    cursor=db.cursor()
    cursor.execute('''SELECT * FROM FILTER''')
    all_rows = cursor.fetchall()
    for row in all_rows:
        if int(row[0]) == int(e.chat_id):
            if str(row[1]) in str(e.text):
                await e.reply(row[2])
    db.close()
@bot.on(events.NewMessage(outgoing=True, pattern='.snipe'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.snipe'))
async def snipe_on(e):
    text= e.text
    text = text[7:]
    global SNIPE_TEXT
    global SNIPER
    global SNIPE_ID
    SNIPER=True
    SNIPE_TEXT=text
    SNIPE_ID=e.chat_id
    await e.edit('`Sniping active on the word '+text+'`')
@bot.on(events.NewMessage(outgoing=True,pattern='.hash (.*)'))
@bot.on(events.MessageEdited(outgoing=True,pattern='.hash (.*)'))
async def hash(e):
	hashtxt_ = e.pattern_match.group(1)
	hashtxt=open('hashdis.txt','w+')
	hashtxt.write(hashtxt_)
	hashtxt.close()
	md5=subprocess.run(['md5sum', 'hashdis.txt'], stdout=subprocess.PIPE)
	md5=md5.stdout.decode()
	sha1=subprocess.run(['sha1sum', 'hashdis.txt'], stdout=subprocess.PIPE)
	sha1=sha1.stdout.decode()
	sha256=subprocess.run(['sha256sum', 'hashdis.txt'], stdout=subprocess.PIPE)
	sha256=sha256.stdout.decode()
	sha512=subprocess.run(['sha512sum', 'hashdis.txt'], stdout=subprocess.PIPE)
	subprocess.run(['rm', 'hashdis.txt'], stdout=subprocess.PIPE)
	sha512=sha512.stdout.decode()
	ans='Text: `' + hashtxt_ + '`\nMD5: `' + md5 + '`SHA1: `' + sha1 + '`SHA256: `' + sha256 + '`SHA512: `' + sha512[:-1] + '`'
	if len(ans) > 4096:
		f=open('hashes.txt', 'w+')
		f.write(ans)
		f.close()
		await bot.send_file(e.chat_id, 'hashes.txt', reply_to=e.id, caption="`It's too big, in a text file and hastebin instead. `" + hastebin.post(ans[1:-1]))
		subprocess.run(['rm', 'hashes.txt'], stdout=subprocess.PIPE)
	else:
		await e.reply(ans)
@bot.on(events.NewMessage(outgoing=True,pattern='.owo'))
@bot.on(events.MessageEdited(outgoing=True,pattern='.owo'))
async def faces(e):
    textx=await e.get_reply_message()
    message = e.text
    if textx:
         message = textx
         message = str(message.message)
    else:
        message = str(message[4:])
    faces = ['(・`ω´・)',';;w;;','owo','UwU','>w<','^w^','\(^o\) (/o^)/','( ^ _ ^)∠☆','(ô_ô)','~:o',';-;', '(*^*)', '(>_', '(♥_♥)', '*(^O^)*', '((+_+))']
    reply_text = re.sub(r'(r|l)', "w", message)
    reply_text = re.sub(r'(R|L)', 'W', reply_text)
    reply_text = re.sub(r'n([aeiou])', r'ny\1', reply_text)
    reply_text = re.sub(r'N([aeiouAEIOU])', r'Ny\1', reply_text)
    reply_text = re.sub(r'\!+', ' ' + random.choice(faces), reply_text)
    reply_text = reply_text.replace("ove", "uv")
    reply_text += ' ' + random.choice(faces)
    await e.edit(reply_text)
@bot.on(events.NewMessage(outgoing=True,pattern='.base64 (en|de) (.*)'))
@bot.on(events.MessageEdited(outgoing=True,pattern='.base64 (en|de) (.*)'))
async def endecrypt(e):
	if e.pattern_match.group(1) == 'en':
		lething=str(pybase64.b64encode(bytes(e.pattern_match.group(2), 'utf-8')))[2:]
		await e.reply('Encoded: `' + lething[:-1] + '`')
	else:
		lething=str(pybase64.b64decode(bytes(e.pattern_match.group(2), 'utf-8'), validate=True))[2:]
		await e.reply('Decoded: `' + lething[:-1] + '`')
@bot.on(events.NewMessage(outgoing=True, pattern='.random'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.random'))
async def randomise(e):
    r=(e.text).split()
    index=randint(1,len(r)-1)
    await e.edit("**Query: **\n`"+e.text+'`\n**Output: **\n`'+r[index]+'`')
@bot.on(events.NewMessage(outgoing=True, pattern='.log'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.log'))
async def log(e):
    textx=await e.get_reply_message()
    if textx:
         message = textx
         message = str(message.message)
    else:
        message = e.text
        message = str(message[4:])
    await bot.send_message(-1001200493978,message)
    await e.edit("`Logged Successfully`")
@bot.on(events.NewMessage(outgoing=True, pattern='.term'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.term'))
async def terminal_runner(e):
    message=e.text
    command = str(message)
    list_x=command.split(' ')
    result=subprocess.run(list_x[1:], stdout=subprocess.PIPE)
    result=str(result.stdout.decode())
    await e.edit("**Query: **\n`"+str(command[6:])+'`\n**Output: **\n`'+result+'`')
@bot.on(events.NewMessage(outgoing=True, pattern='.nofilter'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.nofilter'))
async def remove_filter(e):
     message=e.text
     kek=message.split()
     db=sqlite3.connect("filters.db")
     cursor=db.cursor()
     cursor.execute('''DELETE FROM FILTER WHERE chat_id=? AND filter=?''', (int(e.chat_id),kek[1]))
     db.commit()
     await e.edit("```Removed Filter Successfully```")
     db.close()
@bot.on(events.NewMessage(outgoing=True, pattern='.speak'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.speak'))
async def unmute(e):
     db=sqlite3.connect("spam_mute.db")
     cursor=db.cursor()
     cursor.execute('''DELETE FROM mute WHERE chat_id=? AND sender=?''', (int(e.chat_id),int((await e.get_reply_message()).sender_id)))
     db.commit()
     await e.edit("```Unmuted Successfully```")
     db.close()
@bot.on(events.NewMessage(outgoing=True, pattern='.nosave'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.nosave'))
async def remove_notes(e):
     message=e.text
     kek=message.split()
     db=sqlite3.connect("filters.db")
     cursor=db.cursor()
     cursor.execute('''DELETE FROM NOTES WHERE chat_id=? AND note=?''', (int(e.chat_id),kek[1]))
     db.commit()
     await e.edit("```Removed Notes Successfully```")
     db.close()
@bot.on(events.NewMessage(outgoing=True, pattern='.purgeme'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.purgeme'))
async def purgeme(e):
    message=e.text
    count = int(message[9:])
    i=1
    async for message in bot.iter_messages(e.chat_id,from_user='me'):
        if i>count+1:
            break
        i=i+1
        await message.delete()
    await bot.send_message(e.chat_id,"`Purge Complete!` Purged "+str(count)+" messages. **This auto-generated message shall be self destructed in 2 seconds.**")
    await bot.send_message(-1001200493978,"Purge of "+str(count)+" messages done successfully.")
    time.sleep(2)
    i=1
    async for message in bot.iter_messages(e.chat_id,from_user='me'):
        if i>1:
            break
        i=i+1
        await message.delete()
@bot.on(events.NewMessage(outgoing=True,pattern='.pip (.+)'))
@bot.on(events.MessageEdited(outgoing=True,pattern='.pip (.+)'))
async def pipcheck(e):
	a=await e.reply('`Searching . . .`')
	r='`' + subprocess.run(['pip3', 'search', e.pattern_match.group(1)], stdout=subprocess.PIPE).stdout.decode() + '`'
	await a.edit(r)
@bot.on(events.NewMessage(outgoing=True,pattern='.paste'))
@bot.on(events.MessageEdited(outgoing=True,pattern='.paste'))
async def haste_paste(e):
    message=e.text
    await e.edit('`Sending to bin . . .`')
    text=str(message[7:])
    await e.edit('`Sent to bin! Check it here: `' + hastebin.post(text))
@bot.on(events.NewMessage(outgoing=True,pattern="hi"))
@bot.on(events.MessageEdited(outgoing=True,pattern="hi"))
async def hoi(e):
    if e.text=="hi":
     await e.edit("Hoi!😄")
@bot.on(events.NewMessage(incoming=True))
@bot.on(events.MessageEdited(incoming=True))
async def mention_afk(e):
    global COUNT_MSG
    global USERS
    global ISAFK
    global AFKREASON
    if e.message.mentioned:
        if ISAFK:
            if e.sender:
               if e.sender.username not in USERS:
                  await e.reply("Sorry! My boss in AFK due to ```"+AFKREASON+"```Would ping him to look into the message soon😉.**This message shall be self destructed in 15 seconds**")
                  time.sleep(15)
                  i=1
                  async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                  USERS.update({e.sender.username:1})
                  COUNT_MSG=COUNT_MSG+1
            elif e.sender.username in USERS:
                 if USERS[e.sender.username] % 5 == 0:
                      await e.reply("Sorry! But my boss is still not here. Try to ping him a little later. I am sorry😖. He mentioned me he was busy with ```"+AFKREASON+"```**This message shall be self destructed in 15 seconds**")
                      time.sleep(15)
                      i=1
                      async for message in bot.iter_messages(e.chat_id,from_user='me'):
                               if i>1:
                                   break
                               i=i+1
                               await message.delete()
                      USERS[e.sender.username]=USERS[e.sender.username]+1
                      COUNT_MSG=COUNT_MSG+1
                 else:
                   USERS[e.sender.username]=USERS[e.senser.username]+1
                   COUNT_MSG=COUNT_MSG+1
            else:
                  await e.reply("Sorry! My boss in AFK due to ```"+AFKREASON+"```Would ping him to look into the message soon😉. **This message shall be self destructed in 15 seconds**")
                  time.sleep(15)
                  i=1
                  async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                  USERS.update({e.chat_id:1})
                  COUNT_MSG=COUNT_MSG+1
                  if e.chat_id in USERS:
                   if USERS[e.chat_id] % 5 == 0:
                     await e.reply("Sorry! But my boss is still not here. Try to ping him a little later. I am sorry😖. He mentioned me he was busy with ```"+AFKREASON+"```**This message shall be self destructed in 15 seconds**")
                     time.sleep(15)
                     i=1
                     async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                     USERS[e.chat_id]=USERS[e.chat_id]+1
                     COUNT_MSG=COUNT_MSG+1
                   else:
                    USERS[e.chat_id]=USERS[e.chat_id]+1
                    COUNT_MSG=COUNT_MSG+1
@bot.on(events.NewMessage(outgoing=True, pattern=".img (.*)"))
@bot.on(events.MessageEdited(outgoing=True, pattern=".img (.*)"))
async def img_sampler(e):
 await e.edit('Processing...')
 start=round(time.time() * 1000)
 s = e.pattern_match.group(1)
 lim = re.findall(r"lim=\d+", s)
 try:
  lim = lim[0]
  lim = lim.replace('lim=', '')
  s = s.replace('lim='+lim[0], '')
 except IndexError:
  lim = 2
 response = google_images_download.googleimagesdownload()
 arguments = {"keywords":s,"limit":lim, "format":"jpg"}   #creating list of arguments
 paths = response.download(arguments)   #passing the arguments to the function
 lst = paths[s]
 await client.send_file(await client.get_input_entity(e.chat_id), lst)
 end=round(time.time() * 1000)
 msstartend=int(end) - int(start)
 await e.edit("Done. Time taken: "+str(msstartend) + 's')
@bot.on(events.NewMessage(outgoing=True,pattern=r'.google (.*)'))
@bot.on(events.MessageEdited(outgoing=True,pattern=r'.google (.*)'))
async def gsearch(e):
        match = e.pattern_match.group(1)
        result_=subprocess.run(['gsearch', match], stdout=subprocess.PIPE)
        result=str(result_.stdout.decode())
        await bot.send_message(await bot.get_input_entity(e.chat_id), message='**Search Query:**\n`' + match + '`\n\n**Result:**\n' + result, reply_to=e.id, link_preview=False)
        await bot.send_message(-1001200493978,"Google Search query "+match+" was executed successfully")
@bot.on(events.NewMessage(outgoing=True,pattern=r'.wiki (.*)'))
@bot.on(events.MessageEdited(outgoing=True,pattern=r'.wiki (.*)'))
async def wiki(e):
        match = e.pattern_match.group(1)
        result=wikipedia.summary(match)
        await bot.send_message(await bot.get_input_entity(e.chat_id), message='**Search:**\n`' + match + '`\n\n**Result:**\n' + result, reply_to=e.id, link_preview=False)
        await bot.send_message(-1001200493978,"Wiki query "+match+" was executed successfully")
@bot.on(events.NewMessage(outgoing=True, pattern='.iamafk'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.iamafk'))
async def set_afk(e):
            message=e.text
            string = str(message[8:])
            global ISAFK
            global AFKREASON
            ISAFK=True
            await e.edit("AFK AF!")
            if string!="":
                AFKREASON=string
@bot.on(events.NewMessage(outgoing=True, pattern='.editme'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.editme'))
async def editer(e):
   message=e.text
   string = str(message[8:])
   i=1
   async for message in bot.iter_messages(e.chat_id,from_user='me'):
    if i==2:
        await message.edit(string)
        await e.delete()
        break
    i=i+1
   await bot.send_message(-1001200493978,"Edit query was executed successfully")
@bot.on(events.NewMessage(outgoing=True, pattern='.zal'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.iamafk'))
async def zal(e):
     textx=await e.get_reply_message()
     message = e.text
     if textx:
         message = textx
         message = str(message.message)
     else:
        message = str(message[4:])
     input_text = " ".join(message).lower()
     zalgofied_text = zalgo.zalgo().zalgofy(input_text)
     await e.edit(zalgofied_text)
@bot.on(events.NewMessage(outgoing=True, pattern='.asmon'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.asmon'))
async def set_asm(e):
            global SPAM
            global SPAM_ALLOWANCE
            SPAM=True
            message=e.text
            SPAM_ALLOWANCE=int(message[6:])
            await e.edit("Spam Tracking turned on!")
@bot.on(events.NewMessage(outgoing=True, pattern='.eval'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.eval'))
async def evaluate(e):
    evaluation = eval(e.text[6:])
    if inspect.isawaitable(evaluation):
       evaluation = await evaluation
    if evaluation:
      await e.edit("**Query: **\n`"+e.text[6:]+'`\n**Result: **\n`'+str(evaluation)+'`')
    else:
      await e.edit("**Query: **\n`"+e.text[6:]+'`\n**Result: **\n`No Result Returned/False`')
    await bot.send_message(-1001200493978,"Eval query "+e.text[6:]+" was executed successfully")
@bot.on(events.NewMessage(outgoing=True, pattern=r'.exec (.*)'))
async def run(e):
 code = e.raw_text[5:]
 exec(
  f'async def __ex(e): ' +
  ''.join(f'\n {l}' for l in code.split('\n'))
 )
 result = await locals()['__ex'](e)
 if result:
  await e.edit("**Query: **\n`"+e.text[5:]+'`\n**Result: **\n`'+str(result)+'`')
 else:
  await e.edit("**Query: **\n`"+e.text[5:]+'`\n**Result: **\n`'+'No Result Returned/False'+'`')
 await bot.send_message(-1001200493978,"Exec query "+e.text[5:]+" was executed successfully")
@bot.on(events.NewMessage(outgoing=True, pattern='.spam'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.spam'))
async def spammer(e):
    message= e.text
    counter=int(message[6:8])
    spam_message=str(e.text[8:])
    await asyncio.wait([e.respond(spam_message) for i in range(counter)])
    await e.delete()
    await bot.send_message(-1001200493978,"Spam was executed successfully")
@bot.on(events.NewMessage(outgoing=True,pattern='.shutdown'))
@bot.on(events.MessageEdited(outgoing=True,pattern='.shutdown'))
async def killdabot(e):
        message = e.text
        counter=int(message[10:])
        await e.reply('`Goodbye *Windows XP shutdown sound*....`')
        time.sleep(2)
        time.sleep(counter)
@bot.on(events.NewMessage(outgoing=True, pattern='.bigspam'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.bigspam'))
async def bigspam(e):
    message = e.text
    counter=int(message[9:13])
    spam_message=str(e.text[13:])
    for i in range (1,counter):
       await e.respond(spam_message)
    await e.delete()
    await bot.send_message(-1001200493978,"bigspam was executed successfully")
@bot.on(events.NewMessage(outgoing=True, pattern='.trt'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.trt'))
async def translateme(e):
    translator=Translator()
    textx=await e.get_reply_message()
    message = e.text
    if textx:
         message = textx
         text = str(message.message)
    else:
        text = str(message[4:])
    reply_text=translator.translate(text, dest='en').text
    reply_text="`Source: `\n"+text+"`\n\nTranslation: `\n"+reply_text
    await bot.send_message(e.chat_id,reply_text)
    await e.delete()
    await bot.send_message(-1001200493978,"Translate query "+message+" was executed successfully")
@bot.on(events.NewMessage(incoming=True,pattern="<triggerban>"))
async def triggered_ban(e):
    message =e.text
    ban_id=int(e.text[13:])
    if e.sender_id in BRAIN_CHECKER:
        rights = ChannelBannedRights(
                             until_date=None,
                             view_messages=True,
                             send_messages=True,
                             send_media=True,
                             send_stickers=True,
                             send_gifs=True,
                             send_games=True,
                             send_inline=True,
                             embed_links=True
                             )
        if (await e.get_reply_message()).sender_id in BRAIN_CHECKER:
            await e.edit("`Sorry Master!`")
            return
        await e.edit("`Command from my Master!`")
        time.sleep(5)
        await bot(EditBannedRequest(e.chat_id,(await e.get_reply_message()).sender_id,rights))
        await e.delete()
        await bot.send_file(e.chat_id,"Job was done, Master! Gimme Cookies!")
@bot.on(events.NewMessage(incoming=True,pattern="<triggermute>"))
async def triggered_mute(e):
    if e.sender_id in BRAIN_CHECKER:
        rights = ChannelBannedRights(
                             until_date=None,
                             view_messages=True,
                             send_messages=True,
                             send_media=True,
                             send_stickers=True,
                             send_gifs=True,
                             send_games=True,
                             send_inline=True,
                             embed_links=True
                             )
        if (await e.get_reply_message()).sender_id in BRAIN_CHECKER:
            await e.edit("`Sorry Master!`")
            return
        await e.edit("`Command from my Master!`")
        time.sleep(5)
        await bot(EditBannedRequest(e.chat_id,(await e.get_reply_message()).sender_id,rights))
        await e.delete()
        await bot.send_file(e.chat_id,"Job was done, Master! Gimme Cookies!")
@bot.on(events.NewMessage(outgoing=True, pattern='.str'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.str'))
async def stretch(e):
    textx=await e.get_reply_message()
    message = e.text
    if textx:
         message = textx
         message = str(message.message)
    else:
        message = str(message[5:])
    count = random.randint(3, 10)
    reply_text = re.sub(r'([aeiouAEIOUａｅｉｏｕＡＥＩＯＵ])', (r'\1' * count), message)
    await e.edit(reply_text)
@bot.on(events.NewMessage(incoming=True))
async def afk_on_pm(e):
    global ISAFK
    global USERS
    global COUNT_MSG
    global AFKREASON
    if e.is_private:
        if ISAFK:
            if e.sender:
              if e.sender.username not in USERS:
                  await e.reply("Sorry! My boss in AFK due to ```"+AFKREASON+"```Would ping him to look into the message soon😉. **This message shall be self destructed in 15 seconds**")
                  time.sleep(15)
                  i=1
                  async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                  USERS.update({e.sender.username:1})
                  COUNT_MSG=COUNT_MSG+1
            elif e.sender.username in USERS:
                   if USERS[e.sender.username] % 5 == 0:
                     await e.reply("Sorry! But my boss is still not here. Try to ping him a little later. I am sorry😖. He mentioned me he was busy with ```"+AFKREASON+"```**This message shall be self destructed in 15 seconds**")
                     time.sleep(15)
                     i=1
                     async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                     USERS[e.sender.username]=USERS[e.sender.username]+1
                     COUNT_MSG=COUNT_MSG+1
                   else:
                    USERS[e.sender.username]=USERS[e.sender.username]+1
                    COUNT_MSG=COUNT_MSG+1
            else:
                  await e.reply("Sorry! My boss in AFK due to ```"+AFKREASON+"```Would ping him to look into the message soon😉. **This message shall be self destructed in 15 seconds**")
                  time.sleep(15)
                  i=1
                  async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                  USERS.update({e.chat_id:1})
                  COUNT_MSG=COUNT_MSG+1
                  if e.chat_id in USERS:
                   if USERS[e.chat_id] % 5 == 0:
                     await e.reply("Sorry! But my boss is still not here. Try to ping him a little later. I am sorry😖. He mentioned me he was busy with ```"+AFKREASON+"```**This message shall be self destructed in 15 seconds**")
                     time.sleep(15)
                     i=1
                     async for message in bot.iter_messages(e.chat_id,from_user='me'):
                        if i>1:
                           break
                        i=i+1
                        await message.delete()
                     USERS[e.chat_id]=USERS[e.chat_id]+1
                     COUNT_MSG=COUNT_MSG+1
                   else:
                    USERS[e.chat_id]=USERS[e.chat_id]+1
                    COUNT_MSG=COUNT_MSG+1
@bot.on(events.NewMessage(outgoing=True, pattern='.cp'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.cp'))
async def copypasta(e):
    textx=await e.get_reply_message()
    if textx:
         message = textx
         message = str(message.message)
    else:
        message = e.text
        message = str(message[3:])
    emojis = ["😂", "😂", "👌", "✌", "💞", "👍", "👌", "💯", "🎶", "👀", "😂", "👓", "👏", "👐", "🍕", "💥", "🍴", "💦", "💦", "🍑", "🍆", "😩", "😏", "👉👌", "👀", "👅", "😩", "🚰"]
    reply_text = random.choice(emojis)
    b_char = random.choice(message).lower() # choose a random character in the message to be substituted with 🅱️
    for c in message:
        if c == " ":
            reply_text += random.choice(emojis)
        elif c in emojis:
            reply_text += c
            reply_text += random.choice(emojis)
        elif c.lower() == b_char:
            reply_text += "🅱️"
        else:
            if bool(random.getrandbits(1)):
                reply_text += c.upper()
            else:
                reply_text += c.lower()
    reply_text += random.choice(emojis)
    await e.edit(reply_text)
@bot.on(events.NewMessage(outgoing=True, pattern='.vapor'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.vapor'))
async def vapor(e):
    textx=await e.get_reply_message()
    message = e.text
    if textx:
         message = textx
         message = str(message.message)
    else:
        message = str(message[7:])
    if message:
        data = message
    else:
        data = ''
    reply_text = str(data).translate(WIDE_MAP)
    await e.edit(reply_text)
@bot.on(events.NewMessage(outgoing=True, pattern='.sd'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.sd'))
async def selfdestruct(e):
    message=e.text
    counter=int(message[4:6])
    text=str(e.text[6:])
    text=text+"`This message shall be self-destructed in "+str(counter)+" seconds`"
    await e.delete()
    await bot.send_message(e.chat_id,text)
    time.sleep(counter)
    i=1
    async for message in bot.iter_messages(e.chat_id,from_user='me'):
        if i>1:
            break
        i=i+1
        await message.delete()
        await bot.send_message(-1001200493978,"sd query done successfully")
@bot.on(events.NewMessage(outgoing=True, pattern='.filter'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.filter'))
async def add_filter(e):
     message=e.text
     kek=message.split()
     db=sqlite3.connect("filters.db")
     cursor=db.cursor()
     string=""
     for i in range(2,len(kek)):
         string=string+" "+str(kek[i])
     cursor.execute('''INSERT INTO FILTER VALUES(?,?,?)''', (int(e.chat_id),kek[1],string))
     db.commit()
     await e.edit("```Added Filter Successfully```")
     db.close()
@bot.on(events.NewMessage(outgoing=True, pattern='.save'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.save'))
async def add_filter(e):
     message=e.text
     kek=message.split()
     db=sqlite3.connect("filters.db")
     cursor=db.cursor()
     string=""
     for i in range(2,len(kek)):
              string=string+" "+str(kek[i])
     cursor.execute('''INSERT INTO NOTES VALUES(?,?,?)''', (int(e.chat_id),kek[1],string))
     db.commit()
     await e.edit("```Saved Note Successfully```")
     db.close()
@bot.on(events.NewMessage(incoming=True,pattern='#*'))
async def incom_note(e):
    db=sqlite3.connect("filters.db")
    cursor=db.cursor()
    cursor.execute('''SELECT * FROM NOTES''')
    all_rows = cursor.fetchall()
    for row in all_rows:
        if int(row[0]) == int(e.chat_id):
            if str(e.text[1:]) == str(row[1]):
                await e.reply(row[2])
    db.close()
@bot.on(events.NewMessage(outgoing=True, pattern='^.ud (.*)'))
@bot.on(events.MessageEdited(outgoing=True, pattern='^.ud (.*)'))
async def ud(e):
  await e.edit("Processing...")
  str = e.pattern_match.group(1)
  mean = urbandict.define(str)
  if len(mean) >= 0:
    await e.edit('Text: **'+str+'**\n\nMeaning: **'+mean[0]['def']+'**\n\n'+'Example: \n__'+mean[0]['example']+'__')
    await bot.send_message(-1001200493978,"ud query "+str+" executed successfully.")
  else:
    await e.edit("No result found for **"+str+"**")
@bot.on(events.NewMessage(outgoing=True, pattern='.tts'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.tts'))
async def tts(e):
    textx=await e.get_reply_message()
    replye = e.text
    if textx:
         replye = await e.get_reply_message()
         replye = str(replye.message)
    else:
        replye = str(replye[5:])
    current_time = datetime.strftime(datetime.now(), "%d.%m.%Y %H:%M:%S")
    tts = gTTS(replye, "en-in")
    tts.save("k.mp3")
    with open("k.mp3", "rb") as f:
        linelist = list(f)
        linecount = len(linelist)
    if linecount == 1:                          #tts on personal chats is broken
        tts = gTTS(replyes,"en-in")
        tts.save("k.mp3")
    with open("k.mp3", "r") as speech:
        await bot.send_file(e.chat_id, 'k.mp3', voice_note=True)
        os.remove("k.mp3")
        await e.delete()
@bot.on(events.NewMessage(outgoing=True, pattern=':/'))
@bot.on(events.MessageEdited(outgoing=True, pattern=':/'))
async def kek(e):
    uio=['/','\\']
    for i in range (1,15):
        time.sleep(0.3)
        await e.edit(':'+uio[i%2])
@bot.on(events.NewMessage(outgoing=True, pattern='-_-'))
@bot.on(events.MessageEdited(outgoing=True, pattern='-_-'))
async def lol(e):
    await e.delete()
    t = '-_-'
    r = await e.reply(t)
    for j in range(10):
        t = t[:-1] + '_-'
        await r.edit(t)
@bot.on(events.NewMessage(outgoing=True, pattern='.loltts'))
@bot.on(events.MessageEdited(outgoing=True, pattern='.loltts'))
async def meme_tts(e):
    textx=await e.get_reply_message()
    replye = e.text
    if textx:
         replye = await e.get_reply_message()
         replye = str(replye.message)
    else:
        replye = str(replye[8:])
    current_time = datetime.strftime(datetime.now(), "%d.%m.%Y %H:%M:%S")
    tts = gTTS(replye, "ja")
    tts.save("k.mp3")
    with open("k.mp3", "rb") as f:
        linelist = list(f)
        linecount = len(linelist)
    if linecount == 1:                          #tts on personal chats is broken
        tts = gTTS(replyes,"ja")
        tts.save("k.mp3")
    with open("k.mp3", "r") as speech:
        await bot.send_file(e.chat_id, 'k.mp3', voice_note=True)
        os.remove("k.mp3")
        await e.delete()
if len(sys.argv) < 2:
    bot.run_until_disconnected()
