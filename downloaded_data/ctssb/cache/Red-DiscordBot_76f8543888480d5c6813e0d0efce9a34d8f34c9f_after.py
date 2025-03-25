import discord
from discord.ext import commands
from .utils.dataIO import fileIO
from .utils import checks
import os
import time
import aiohttp
import asyncio
from copy import deepcopy
import logging

class Streams:
    """Streams

    Twitch and Hitbox alerts"""

    def __init__(self, bot):
        self.bot = bot
        self.twitch_streams = fileIO("data/streams/twitch.json", "load")
        self.hitbox_streams = fileIO("data/streams/hitbox.json", "load")

    @commands.command()
    async def hitbox(self, stream : str):
        """Checks if hitbox stream is online"""
        online = await self.hitbox_online(stream)
        if online:
            await self.bot.say("http://www.hitbox.tv/{}/ is online!".format(stream))
        elif online == False:
            await self.bot.say(stream + " is offline.")
        elif online == None:
            await self.bot.say("That stream doesn't exist.")
        else:
            await self.bot.say("Error.")

    @commands.command()
    async def twitch(self, stream : str):
        """Checks if twitch stream is online"""
        online = await self.twitch_online(stream)
        if online:
            await self.bot.say("http://www.twitch.tv/{} is online!".format(stream))
        elif online == False:
            await self.bot.say(stream + " is offline.")
        elif online == None:
            await self.bot.say("That stream doesn't exist.")
        else:
            await self.bot.say("Error.")

    @commands.group(pass_context=True)
    @checks.mod_or_permissions(manage_server=True)
    async def streamalert(self, ctx):
        """Adds/removes stream alerts from the current channel"""
        if ctx.invoked_subcommand is None:
            await self.bot.say("Type help streamalert for info.")

    @streamalert.command(name="twitch", pass_context=True)
    async def twitch_alert(self, ctx, stream : str):
        """Adds/removes twitch alerts from the current channel"""
        channel = ctx.message.channel
        check = await self.twitch_online(stream)
        if check == None:
            await self.bot.say("That stream doesn't exist.")
            return
        elif check == "error":
            await self.bot.say("Error.")
            return
        
        done = False

        for i, s in enumerate(self.twitch_streams):
            if s["NAME"] == stream:
                if channel.id in s["CHANNELS"]:
                    if len(s["CHANNELS"]) == 1:
                        self.twitch_streams.remove(s)
                        await self.bot.say("Alert has been removed from this channel.")
                        done = True
                    else:
                        self.twitch_streams[i]["CHANNELS"].remove(channel.id)
                        await self.bot.say("Alert has been removed from this channel.")
                        done = True
                else:
                    self.twitch_streams[i]["CHANNELS"].append(channel.id)
                    await self.bot.say("Alert activated. I will notify this channel everytime {} is live.".format(stream))
                    done = True

        if not done:
            self.twitch_streams.append({"CHANNELS" : [channel.id], "NAME" : stream, "ALREADY_ONLINE" : False})
            await self.bot.say("Alert activated. I will notify this channel everytime {} is live.".format(stream))

        fileIO("data/streams/twitch.json", "save", self.twitch_streams)

    @streamalert.command(name="hitbox", pass_context=True)
    async def hitbox_alert(self, ctx, stream : str):
        """Adds/removes hitbox alerts from the current channel"""
        channel = ctx.message.channel
        check = await self.hitbox_online(stream)
        if check == None:
            await self.bot.say("That stream doesn't exist.")
            return
        elif check == "error":
            await self.bot.say("Error.")
            return
        
        done = False

        for i, s in enumerate(self.hitbox_streams):
            if s["NAME"] == stream:
                if channel.id in s["CHANNELS"]:
                    if len(s["CHANNELS"]) == 1:
                        self.hitbox_streams.remove(s)
                        await self.bot.say("Alert has been removed from this channel.")
                        done = True
                    else:
                        self.hitbox_streams[i]["CHANNELS"].remove(channel.id)
                        await self.bot.say("Alert has been removed from this channel.")
                        done = True
                else:
                    self.hitbox_streams[i]["CHANNELS"].append(channel.id)
                    await self.bot.say("Alert activated. I will notify this channel everytime {} is live.".format(stream))
                    done = True

        if not done:
            self.hitbox_streams.append({"CHANNELS" : [channel.id], "NAME" : stream, "ALREADY_ONLINE" : False})
            await self.bot.say("Alert activated. I will notify this channel everytime {} is live.".format(stream))

        fileIO("data/streams/hitbox.json", "save", self.hitbox_streams)

    @streamalert.command(name="stop", pass_context=True)
    async def stop_alert(self, ctx):
        """Stops all streams alerts in the current channel"""
        channel = ctx.message.channel

        to_delete = []

        for s in self.hitbox_streams:
            if channel.id in s["CHANNELS"]:
                if len(s["CHANNELS"]) == 1:
                    to_delete.append(s)
                else:
                    s["CHANNELS"].remove(channel.id)

        for s in to_delete:
            self.hitbox_streams.remove(s)

        to_delete = []

        for s in self.twitch_streams:
            if channel.id in s["CHANNELS"]:
                if len(s["CHANNELS"]) == 1:
                    to_delete.append(s)
                else:
                    s["CHANNELS"].remove(channel.id)

        for s in to_delete:
            self.twitch_streams.remove(s)

        fileIO("data/streams/twitch.json", "save", self.twitch_streams)
        fileIO("data/streams/hitbox.json", "save", self.hitbox_streams)

        await self.bot.say("There will be no more stream alerts in this channel.")


    async def hitbox_online(self, stream):
        url = "https://api.hitbox.tv/user/" + stream
        try:
            async with aiohttp.get(url) as r:
                data = await r.json()
            if data["is_live"] == "0":
                return False
            elif data["is_live"] == "1":
                return True
            elif data["is_live"] == None:
                return None
        except:
            return "error"

    async def twitch_online(self, stream):
        url =  "https://api.twitch.tv/kraken/streams/" + stream
        async with aiohttp.get(url) as r:
            data = await r.json()
        try:
            if "stream" in data:
                if data["stream"] != None:
                    return True
                else:
                    return False
            elif "error" in data:
                return None
        except:
            return "error"
        return "error"

    async def stream_checker(self):
        CHECK_DELAY = 60
        old_alerts = []
        last_twitch_alert = None
        last_hitbox_alert = None
        while "Streams" in self.bot.cogs:
            
            old = (deepcopy(self.twitch_streams), deepcopy(self.hitbox_streams))

            for stream in self.twitch_streams:
                online = await self.twitch_online(stream["NAME"])
                if online and not stream["ALREADY_ONLINE"]:
                    stream["ALREADY_ONLINE"] = True
                    for channel in stream["CHANNELS"]:
                        if self.bot.get_channel(channel):
                            if last_twitch_alert:
                                old_alerts.append(last_twitch_alert)
                            last_twitch_alert = await self.bot.send_message(self.bot.get_channel(channel), "http://www.twitch.tv/{} is online!".format(stream["NAME"]))
                else:
                    if stream["ALREADY_ONLINE"] and not online: stream["ALREADY_ONLINE"] = False
                await asyncio.sleep(0.5)
            
            for stream in self.hitbox_streams:
                online = await self.hitbox_online(stream["NAME"])
                if online and not stream["ALREADY_ONLINE"]:
                    stream["ALREADY_ONLINE"] = True
                    for channel in stream["CHANNELS"]:
                        if self.bot.get_channel(channel):
                            if last_hitbox_alert:
                                old_alerts.append(last_hitbox_alert)
                            last_hitbox_alert = await self.bot.send_message(self.bot.get_channel(channel), "http://www.hitbox.tv/{} is online!".format(stream["NAME"]))
                else:
                    if stream["ALREADY_ONLINE"] and not online: stream["ALREADY_ONLINE"] = False
                await asyncio.sleep(0.5)

            if old != (self.twitch_streams, self.hitbox_streams):
                fileIO("data/streams/twitch.json", "save", self.twitch_streams)
                fileIO("data/streams/hitbox.json", "save", self.hitbox_streams)

            for msg in old_alerts:
                await self.bot.delete_message(msg)
            old_alerts = []
            
            await asyncio.sleep(CHECK_DELAY)

def check_folders():
    if not os.path.exists("data/streams"):
        print("Creating data/streams folder...")
        os.makedirs("data/streams")

def check_files():
    f = "data/streams/twitch.json"
    if not fileIO(f, "check"):
        print("Creating empty twitch.json...")
        fileIO(f, "save", [])

    f = "data/streams/hitbox.json"
    if not fileIO(f, "check"):
        print("Creating empty hitbox.json...")
        fileIO(f, "save", [])

def setup(bot):
    logger = logging.getLogger('aiohttp.client')
    logger.setLevel(50) #Stops warning spam
    check_folders()
    check_files()
    n = Streams(bot)
    loop = asyncio.get_event_loop()
    loop.create_task(n.stream_checker())
    bot.add_cog(n)