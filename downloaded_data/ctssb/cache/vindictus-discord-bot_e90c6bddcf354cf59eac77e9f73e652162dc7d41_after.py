import asyncio
import discord
import json
from bs4 import BeautifulSoup
import requests
import time
import datetime
import functools
from concurrent.futures import CancelledError
import aiohttp
import math
import string
import youtube_dl
import async_timeout
from PIL import Image
import io
import re
import sys

post_queue = asyncio.Queue()
wolfram_queue = asyncio.Queue()
dev = True if "--dev" in sys.argv else False
print("Dev bot") if dev else print("Starting Vindictus Bot")
token_file = "token_dev.txt" if dev else "token.txt"
with open(token_file) as f:
    token = f.read()
log_file = "log.log"
wolfram_appid = "7W664G-6TT5XQA4XX"
wolfram_url = "http://api.wolframalpha.com/v1/result"
months_re = "January|February|March|April|May|June|July|August|September|October|November|December"
#months_re = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
months_array = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
#months_array = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
days_re = "([0-9]|)[0-9]"
years_re = "20[0-9][0-9]"

try:
    open(log_file).close()
except FileNotFoundError:
    open(log_file, "w+").close()

with open("news.json") as news_json:
    news = json.load(news_json)
    
news_link = "http://vindictus.nexon.net/news/all/"

class Event:
    def __init__(self, name=None, start=None, end=None, link=None, jjson=None):
        self.name = name
        self.start = start
        self.end = end
        self.url = link

        if jjson != None:
            self.from_json(jjson)

    def is_going_on(self):
        return self.start < datetime.datetime.now() < self.end

    def has_finished(self):
        return datetime.datetime.now() > self.end

    def is_new(self):
        return datetime.timedelta() < datetime.datetime.now() - self.start < datetime.timedelta(days=3)

    def print_self(self):
        print(self.name)
        print(self.start)
        print(self.end)

    def to_json(self):
        return {
            "name": self.name,
            "url": self.url,
            "start": self.start.timestamp(),
            "end": self.end.timestamp()
            }

    def from_json(self, jjson):
        self.name = jjson["name"]
        self.url = jjson["url"]
        self.start = datetime.datetime.fromtimestamp(jjson["start"])
        self.end = datetime.datetime.fromtimestamp(jjson["end"])

with open("events.json") as events_json:
    events_sales = json.load(events_json)
    events = list(map(lambda x: Event(jjson=x), events_sales["events"]))
    sales = list(map(lambda x: Event(jjson=x), events_sales["sales"]))

class MusicHandler():
    def __init__(self, client, message = None):
        self.__base_yt__ = "https://www.youtube.com/watch?v="
        self.message = message
        self.client = client
        self.voice = None
        self.player = None
        self.url = None
        self.play_next = False
        self.music_queue = asyncio.Queue()
        self.volume = 0.2
        if self.message != None:
            self.handle(message)
        self.stopped = False

    def __call__(self):
        if not self.stopped:
            func = asyncio.run_coroutine_threadsafe(self.nextSong(), loop = self.client.loop)
            func.result()
        self.stopped = False

    async def handle(self, message):
        self.message = message
        command_position = 1
        if message.content.lower().split()[command_position] == "play":
            if self.message.content.split()[command_position + 1] == "search":
                self.url = self.__base_yt__ + await youtubeSearch(
                    " ".join(self.message.content.split()[command_position + 2:]))
            elif self.__base_yt__ in self.message.content.split()[-1]:
                self.url = self.message.content.split()[-1]
            await self.play()
        elif (message.content.lower().split()[command_position] == "pause"
              and self.voice != None
              and self.player != None
              and self.voice.is_connected()
              and self.player.is_playing()):
            await self.pause()
        elif (message.content.lower().split()[command_position] == "resume"
              and self.voice != None
              and self.player != None
              and self.voice.is_connected()
              and not self.player.is_playing()):
            await self.resume()
        elif (message.content.lower().split()[command_position] == "stop"):
            await self.stop()
        elif (message.content.lower().split()[command_position] == "volume"
              and self.voice != None
              and self.player != None
              and self.voice.is_connected()):
            try:
                volume = float(message.content.split()[command_position + 1])
                if volume > 1:
                    volume /= 10
                if volume > 1:
                    volume = 1
                if volume < 0:
                    volume = 0
                self.volume = volume
                await self.setVolume(volume)
            except:
                pass
        elif (message.content.lower().split()[command_position] == "next"
              and self.voice != None
              and self.player != None
              and self.voice.is_connected()):
            await self.client.send_message(message.channel, "Moving to next song!")
            await self.nextSong()
        elif (message.content.lower().split()[command_position] == "queue"
              and self.voice != None
              and self.player != None
              and self.voice.is_connected()):
            if message.content.lower().split()[command_position + 1] == "clear":
                self.music_queue = asyncio.Queue()
                await self.client.send_message(message.channel, "Queue cleared!")
            elif message.content.lower().split()[command_position + 1] == "put":
                if message.content.lower().split()[command_position + 2] == "search":
                    url = self.__base_yt__ + await youtubeSearch(
                        " ".join(self.message.content.split()[command_position + 3:]))
                elif self.__base_yt__ in message.contentlower.spli()[-1]:
                    url = self.message.content.split()[-1]
                await self.music_queue.put(url)
                await self.client.send_message(message.channel, "Added to queue!")
        elif message.content.lower().split()[command_position] == "help":
            help_message = "Bot music commands:\n\
@bot !music play _Youtube-url_\n\
@bot !music play search _Youtube search query_\n\
@bot !music pause\n\
@bot !music resume\n\
@bot !music stop\n\
@bot !music volume _value (0.0 - 1.0)_\n\
@bot !music queue put _Youtube-url_\n\
@bot !music queue put search _Youtube search query_\n\
@bot !music queue clear\n\
@bot !music next\n\
@bot !music help\n"
            await self.client.send_message(message.channel, help_message)

    async def play(self):
        if self.voice == None:
            for channel in self.message.server.channels:
                if (channel.type == discord.ChannelType.voice
                    and self.message.author in channel.voice_members):
                    self.voice = await self.client.join_voice_channel(channel)
                    break

        if self.url != None and self.voice != None:
            if self.player != None:
                self.stopped = True
                self.player.stop()
            self.player = await self.voice.create_ytdl_player(self.url, after = self)
            self.player.volume = self.volume
            self.player.start()
            await self.client.send_message(self.message.channel, "Now playing: "
                                    + self.player.title)

    async def pause(self):
        self.player.pause()

    async def resume(self):
        self.player.resume()

    async def stop(self):
        if self.player != None:
            self.stopped = True
            self.player.stop()
            self.player = None
        if self.voice != None and self.voice.is_connected():
            await self.voice.disconnect()
        if self.voice != None:
            self.voice = None

    async def setVolume(self, value):
        self.player.volume = value

    async def nextSong(self):
        if not self.music_queue.empty():
            self.url = await self.music_queue.get()
        await self.play()
        self.stopped = False
  

class discordClient(discord.Client):
    async def on_ready(self): 
        self.post_channels = []
        self.player = None
        self.voice = None
        self.mh = MusicHandler(self)
        
        for server in self.servers:
            for channel in server.channels:
                if channel.name == "general":
                    self.post_channels.append(channel)
                    print("Posting to: " + channel.name + " in " + server.name)

        try:
            self.tasks
            printlog("Client restarted for some reason")
        except AttributeError:
            self.tasks = []
            self.tasks.append(asyncio.ensure_future(get_news(), loop = self.loop))
            self.tasks.append(asyncio.ensure_future(news_poster(self), loop = self.loop))
            self.tasks.append(asyncio.ensure_future(wolfram_responder(self), loop = self.loop))
            log(str(datetime.datetime.now()) + ": Ready")
 
    async def on_message(self, message):
        # !DELMSG AND !GAME
        if message.channel.is_private and "!game" in message.content:
            await self.change_presence(game =
                discord.Game(name = " ".join(message.content.split()[1:])))
        elif message.channel.is_private and "!delmsg" in message.content:
            self.appinfo = await self.application_info()
            if message.author == self.appinfo.owner:
                msgid = message.content.split()[-1]
                msg = None
                if len(message.content.split()) == 2:
                    msg = discord.utils.find(lambda m: m.id == msgid, self.messages)
                    errmsg = "No such message found, try !delmsg [ch id] [msg id]"
                elif len(message.content.split()) == 3:
                    chid = message.content.split()[-2]
                    ch = self.get_channel(chid)
                    if ch:
                        msg = await self.get_message(ch, msgid)
                        errmsg = "Couldn't find a message with id " + msgid
                    else:
                        errmsg = "Couldn't find a channel with id " + chid
                else:
                    errmsg = "Incorrent parameter count"
                    
                if not msg:
                    await self.send_message(message.channel, errmsg)
                else:
                    try:
                        await self.delete_message(msg)
                        await self.send_message(message.channel, "Message deleted")
                    except:
                        await self.send_message(message.channel, "Couldn't delete message")

        # !DELMESSAGES
        elif message.channel.is_private and "!delmessages" in message.content.lower():
            # syntax: !delmessages chid list of msgid
            cnt = message.content.lower()
            chid = cnt.split()[1]
            messageids = cnt.split()[2:]
            ch = self.get_channel(chid)
            messages = []
            for msgid in messageids:
                messages.append(await self.get_message(ch, msgid))
            if len(messages) > 1:
                try:
                    await self.delete_messages(messages)
                except discord.Forbidden:
                    for msg in messages:
                        try:
                            await self.delete_message(msg)
                        except Exception as e:
                            await self.send_message(message.channel, e)

            elif len(messages) == 1:
                await self.delete_message(messages[0])
            await self.send_message(message.channel, "Deleted messages")


        # HANDLE SNOWVISION
        elif len(message.content.split()) >= 2 and message.content.lower().split()[0] == "!snowvision":
            valid_extensions = ["jpeg", "jpg", "png"]
            url = message.content.split(" ")[-1].split("?")[0]
            if url.split(".")[-1].lower() in valid_extensions:
                await sendImage(url, message.channel, self)

        # HANDLE EVENTS AND SALES
        elif message.content.lower() in ["!events", "!sales"]:
            await postEvents(message.content.lower(), message.channel, self)

        # HANDLE REFRESH
        elif message.content.lower() == "!refresh":
            await self.send_message(message.channel, "Refreshing")
            urls = []
            for news_piece in news["news"]:
                if not news_piece["link"] in urls:
                    urls.append(news_piece["link"])
            for url in urls:
                await parseEvents(url)
            await self.send_message(message.channel, "Finished")

        # HANDLE EMOTES
        elif "!emote" in message.content.lower() or "!animated" in message.content.lower():
            for emoji in self.get_all_emojis():
                if emoji.name.lower() == message.content.lower().split()[-1]:
                    pref = "a" if "!animated" in message.content.lower() else ""
                    name = emoji.name
                    idd = emoji.id
                    await self.send_message(message.channel, "<{}:{}:{}>".format(pref, name, idd))
                    try: 
                        await self.delete_message(message)
                    except:
                        print("Tried to delete message, unable")
                    break         

        # HANDLE REACTIONS
        elif "!react" in message.content.lower():
            # msg syntax !react [msg id] [ch id] [emote name]
            split = message.content.lower().split()
            msgid = split[1]
            chid = split[2] if len(split) == 4 else None
            emotename = split[-1]
            emote = None
            for emoji in self.get_all_emojis():
                if emoji.name.lower() == emotename:
                    emote = emoji
                    break
            if emote:
                ch = self.get_channel(chid)
                msg = await self.get_message(ch, msgid) if chid else discord.utils.find(lambda m: m.id == msgid, self.messages)
                await self.add_reaction(msg, emote)
                await asyncio.sleep(0.5)
                await self.wait_for_reaction(timeout=10, message=msg)
                await self.remove_reaction(msg, emote, msg.server.me)

        # HANDLE ADDING NEW EVENT
        elif message.content.lower() == "!addevent":
            global events
            global sales

            sender = message.author
            channel = message.channel
            event_type = None
            while event_type == None:
                await self.send_message(channel, "Enter type (event / sale)")
                resp = await self.wait_for_message(timeout=15, author=sender)
                if resp != None:
                    if resp.content.lower() in ["event", "sale"]:
                        event_type = resp.content.lower()
                else:
                    break

            if event_type != None:
                event_name = None
                await self.send_message(channel, "Enter {} name".format(event_type))
                name_resp = await self.wait_for_message(timeout=15, author=sender)
                if name_resp != None:
                    event_name = name_resp.content
                
                if event_name != None:
                    start_date = None
                    while start_date == None:
                        await self.send_message(channel, "Enter starting date")
                        start_resp = await self.wait_for_message(timeout=15, author=sender)
                        if start_resp != None:
                            start_mon = re.search(months_re, start_resp.content)
                            start_day = re.search(days_re, start_resp.content)
                            if start_mon != None and start_day != None:
                                start_date = datetime.datetime(
                                    datetime.date.today().year,
                                    months_array.index(start_mon.group()),
                                    int(start_day.group()),
                                    10
                                )
                        else:
                            break

                    if start_date != None:
                        end_date = None
                        while end_date == None:
                            await self.send_message(channel, "Enter ending date")
                            end_resp = await self.wait_for_message(timeout=15, author=sender)
                            if end_resp != None:
                                end_mon = re.search(months_re, end_resp.content)
                                end_day = re.search(days_re, end_resp.content)
                                if end_mon != None and end_day != None:
                                    end_date = datetime.datetime(
                                        datetime.date.today().year,
                                        months_array.index(end_mon.group()),
                                        int(end_day.group()),
                                        10
                                    )
                            else:
                                break

                        if end_date != None:
                            link = None
                            await self.send_message(channel, "Enter event link")
                            link_resp = await self.wait_for_message(timeout=15, author=sender)
                            if link_resp != None:
                                link = link_resp.content

            if event_type != None and event_name != None and start_date != None and end_date != None:
                e = Event(event_name, start_date, end_date, link)
                events.append(e) if event_type == "event" else sales.append(e)
                sales_not_finished = [sale for sale in sales if not sale.has_finished()]
                events_not_finished = [event for event in events if not event.has_finished()]
                with open("events.json", "w+") as f:
                    json.dump({
                        "events": [event.to_json() for event in events_not_finished],
                        "sales": [sale.to_json() for sale in sales_not_finished]}, f)
                await self.send_message(channel, "Added a new {}".format(event_type))
            else:
                await self.send_message(channel, "Stopped adding a new event")

        #!ACTIVE AND !INACTIVE
        elif message.content.lower() in ["!active", "!inactive"]:
            if message.server.name in ["Vindi", "Dev serv"]:
                active_role = discord.utils.get(message.server.roles, name="Vindictus Active")
                if message.content.lower() == "!active":
                    if not active_role in message.author.roles:
                        await self.add_roles(message.author, active_role)
                        await self.add_reaction(message, "✅")
                    else:
                        await self.add_reaction(message, "❌")
                elif message.content.lower() == "!inactive":
                    if active_role in message.author.roles:
                        await self.remove_roles(message.author, active_role)
                        await self.add_reaction(message, "✅")
                    else:
                        await self.add_reaction(message, "❌")

        #HANDLE MUSIC
        elif message.content.lower().split()[0] == "!music":
            await self.mh.handle(message)


        #HANDLE WOLFRAM ALPHA
        elif self.user in message.mentions:
            await wolfram_queue.put(message)

        #HANDLE DISCO PARTY
        elif "disco" in message.content.lower() and message.author != self.user:
            await discoParty(message, self)

    async def on_member_join(self, member):
        if member.server.name == "Vindi":
            newb_role = discord.utils.get(member.server.roles, name="Newbs")
            await self.add_roles(member, newb_role)

def log(text):
    limit = 2000
    if not str(datetime.date.today().year) + "-" in text:
        text = str(datetime.datetime.now()) + ": " + text
    if not "\n" in text:
        text += "\n"
    with open(log_file) as log:
        lines = log.readlines()
        lines.append(text)

    with open(log_file, "w") as log:
        log.write("".join(lines[max(0, len(lines) - limit):len(lines)]))

def printlog(text):
    print(text)
    log(text)

async def get_news():
    global news
    while loop.is_running():
        new_news = {"news": []}

        try:
            with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(news_link) as response:
                        resText = await response.text()
        except asyncio.TimeoutError:
            await asyncio.sleep(60)
        soup = BeautifulSoup(resText, "html.parser")

        news_raw = soup.find_all("div", class_ = "news-list-item")

        for news_piece in news_raw:
            news_item = {}
            news_item["title"] = news_piece.find(class_ = "news-list-item-title").text.replace("\r", "").replace("\n", "").replace("\t", "").replace("  ", "")
            news_item["content"] = news_piece.find(class_ = "news-list-item-text").text.replace("\r", "").replace("\n", "").replace("\t", "").replace("  ", "")
            news_item["link"] = "http://vindictus.nexon.net" + news_piece.find(class_ = "news-list-link").get("href")
            new_news["news"].append(news_item)

        news_list = new_news["news"]
        news_list.reverse()
        for news_piece in news_list:
            if not news_piece in news["news"]:
                await post_queue.put(news_piece)
                news["news"].append(news_piece)
                log("New news found")
        if new_news["news"] != []:
            with open("news.json", "w") as news_json:
                news["news"] = news["news"][max(0, len(news["news"]) - 25):]
                json.dump(news, news_json)
        log("News gotten")

        await asyncio.sleep(60)

async def news_poster(client):
    while loop.is_running():
        item = await post_queue.get()
        title = item["title"]
        link = item["link"]
        await parseEvents(link)
        for channel in client.post_channels:
            await client.send_message(channel, title + " " + link)
            printlog("Sent: " + title)

async def wolfram_responder(client):
    while loop.is_running():
        message = await wolfram_queue.get()
        await client.send_typing(message.channel)
        i = " ".join(message.content.split()[1:])
        params = {"appid": wolfram_appid, "input": i}
        async with aiohttp.ClientSession() as session:
            async with session.get(wolfram_url, params = params) as resp:
                answer = await resp.text()
        if answer == "Wolfram|Alpha did not understand your input":
            answer = "I didn't quite understand"
        mention = "<@" + message.author.id + ">"
        if len(answer) > 1000:
            count = math.ceil(len(answer) / 1000)
            for x in range(0, count):
                await client.send_message(message.channel, mention + " " + answer[1000 * x : 1000 * (x + 1)])
        else:
            await client.send_message(message.channel, mention + " " + answer)

async def discoParty(message, client):
    msg = message.content.lower()
    newmsg = ""
    to_return = None
    for letter in msg:
        if not letter in string.punctuation:
            newmsg += letter
        elif letter in string.punctuation:
            newmsg += " "
    newmsg.replace("  ", " ")
    if "you say disco" in newmsg:
        to_return = "Disco, Disco!"
    elif "i say disco" in newmsg and not "you say party" in newmsg:
        to_return = "I say Party!"
    elif ("i say disco" in newmsg and "you say party" in newmsg
          and newmsg.split(" ").count("disco") > 1):
        to_return = "Party, " * (newmsg.split(" ").count("disco") - 2) + "Party!"
    elif not "i say disco" in newmsg and "disco" in newmsg.split():
        to_return =  "Party, " * (newmsg.split(" ").count("disco") - 1) + "Party!"
    if not to_return == None:
        await client.send_typing(message.channel)
        await client.send_message(message.channel, to_return)

async def youtubeSearch(query):
    params = {"search_query": query}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.youtube.com/results", params = params) as resp:
            soup = BeautifulSoup(await resp.text(), "html.parser")
            vid_div = soup.find_all("div", class_ = "yt-lockup-video")[0]
            return vid_div.get_attribute_list("data-context-item-id")[0]

async def sendImage(url, destination, client):
    try:
        with async_timeout.timeout(20):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    respBytes = await response.read()
        imgname = "img." + url.split(".")[-1]
        oldimg = Image.open(io.BytesIO(respBytes))
        newimg = oldimg.convert(mode="L")
        newimg.save(imgname)
        await client.send_file(destination, imgname)
        printlog("Sent an image")
    except asyncio.TimeoutError:
        await asyncio.sleep(5)

async def parseEvents(url):
    global sales
    global events
    new_sales = []
    new_events = []
    tables = []
    
    try:
        with async_timeout.timeout(10):
            async with aiohttp.get(url) as response:
                respText = await response.text()
                print("Got a response")
                soup = BeautifulSoup(respText, "html.parser")
                tables = soup.find_all("table")
    except asyncio.TimeoutError:
        print("timeout")

    items = {}
    names = []

    for table in tables:
        datas = table.find_all("td")
        if len(datas) < 3:
            continue
        if len(datas) == 4 or datas[2].text.strip() not in ["Sale Start", "Event Start", "Starting Date"]:
            e_type = "event" if datas[0].text.strip() == "Event Name" else "sale"
            name = datas[2].text.strip()
            if not name in items:
                names.append(name)
                items[name] = {}
            if datas[1].text.strip() == "Event Start":
                items[name]["start"] = datas[3].text.strip()
            elif datas[1].text.strip() == "Event End":
                items[name]["end"] = datas[3].text.strip()
            items[name]["type"] = e_type
        else:
            name = datas[1].text.strip()
            start = datas[3].text.strip()
            end = datas[5].text.strip()
            e_type = "event" if datas[0].text.strip() == "Event Name" else "sale"
            items[name] = {"start": start, "end": end, "type": e_type}
            names.append(name)


    for name in names:
        item = items[name]
        if not ("start" in item and "end" in item):
            continue
        start = item["start"]
        end = item["end"]
        e_type = item["type"]
        obj = None
        try:
            start_year = re.search(years_re, start)
            end_year = re.search(years_re, end)
            if start_year == None:
                start_year = datetime.date.today().year
            else:
                start_year = int(start_year.group())
            if end_year == None:
                end_year = datetime.date.today().year
            else:
                end_year = int(end_year.group())

            start_date = datetime.datetime(
                int(start_year),
                months_array.index(re.search(months_re, start).group()),
                int(re.search(days_re, start).group()),
                10)

            end_date = datetime.datetime(
                int(end_year),
                months_array.index(re.search(months_re, end).group()),
                int(re.search(days_re, end).group()),
                10)
            
            if start_date > end_date:
                end_date = end_date.replace(year=end_year + 1)
                
            obj = Event(name, start_date, end_date, url)
        except Exception as e:
            print(e)

        if obj:
            new_sales.append(obj) if e_type == "sale" else new_events.append(obj)

    old_sale_names = list(map(lambda x: x.name, sales))
    old_event_names = list(map(lambda x: x.name, events))

    sales += list(filter(lambda x: not x.name in old_sale_names, new_sales))
    events += list(filter(lambda x: not x.name in old_event_names, new_events))

    sales_not_finished = list(filter(lambda x: not x.has_finished(), sales))
    events_not_finished = list(filter(lambda x: not x.has_finished(), events))

    if (sales_not_finished != sales or events_not_finished != events
        or new_sales != [] or new_events != []):
        with open("events.json", "w+") as f:
            json.dump({"events": list(map(lambda x: x.to_json(), events_not_finished)),
                       "sales": list(map(lambda x: x.to_json(), sales_not_finished))}, f)

async def postEvents(type, destination, client):

    li = events if type == "!events" else sales
    going_on = list(filter(lambda x: x.is_going_on(), li))

    emb = discord.Embed(colour=discord.Colour(int("020b1c", 16)))
    emb.set_author(
        icon_url="https://cdn.discordapp.com/attachments/344883962612678657/399689459081150485/vindidiscord.png",
        name="Vindictus "+ type.replace("!", "").capitalize())
    for event in going_on:
        start_month = months_array[event.start.month].capitalize()
        end_month = months_array[event.end.month].capitalize()
        start_date = start_month + " " + str(event.start.day)
        end_date = end_month + " " + str(event.end.day)
        name = event.name
        if event.is_new():
            name += " (New!)"
        emb.add_field(
            name=name,
            value="{} - {}. [Link]({})".format(start_date, end_date, event.url),
            inline=False
        )
    await client.send_message(destination, embed=emb)

loop = asyncio.get_event_loop()
discord_client = discordClient(loop=loop)

try:
    loop.run_until_complete(discord_client.start(token))
    printlog("Loop finished")
except KeyboardInterrupt:
    printlog("Keyboard interrupted")
finally:
    printlog("Logging out")
    loop.run_until_complete(discord_client.logout())
    for task in discord_client.tasks:
        task.cancel()
    loop.stop()
    loop.close()
    printlog("Loop closed")
