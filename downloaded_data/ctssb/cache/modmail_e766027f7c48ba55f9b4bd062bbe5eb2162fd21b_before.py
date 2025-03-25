'''
MIT License

Copyright (c) 2017 Kyb3r

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

__version__ = '1.1.7'

import discord
from discord.ext import commands
import aiohttp
from urllib.parse import urlparse
import asyncio
import textwrap
import datetime
import time
import json
import sys
import os
import re
import string
import traceback
import io
import inspect
from contextlib import redirect_stdout


class Modmail(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix=self.get_pre)
        self.start_time = datetime.datetime.utcnow()
        self.session = aiohttp.ClientSession()
        self.loop.create_task(self.data_loop())
        self._add_commands()

    def _add_commands(self):
        '''Adds commands automatically'''
        self.remove_command('help')
        for attr in dir(self):
            cmd = getattr(self, attr)
            if isinstance(cmd, commands.Command):
                self.add_command(cmd)
    @property
    def config(self):
        with open('config.json') as f:
            config = json.load(f)
        config.update(os.environ)
        return config
    
    @property
    def snippets(self):
        return {
            key.split('_')[1].lower(): val
            for key, val in self.config.items() 
            if key.startswith('SNIPPET_')
            }

    @property
    def token(self):
        '''Returns your token wherever it is'''
        return self.config.get('TOKEN')
    
    @staticmethod
    async def get_pre(bot, message):
        '''Returns the prefix.'''
        p = bot.config.get('PREFIX') or 'm.'
        return [p, f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']

    async def on_connect(self):
        print('---------------')
        print('Modmail connected!')
        status = os.getenv('STATUS') or self.config.get('STATUS')
        if status:
            print(f'Setting Status to {status}')
            await self.change_presence(activity=discord.Game(status))
        else:
            print('No status set.')

    @property
    def guild_id(self):
        return int(self.config.get('GUILD_ID'))
    
    @property
    def guild(self):
        g = discord.utils.get(self.guilds, id=self.guild_id)
        return g

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        print(textwrap.dedent(f'''
        ---------------
        Client is ready!
        ---------------
        Author: kyb3r
        ---------------
        Logged in as: {self.user}
        User ID: {self.user.id}
        ---------------
        '''))


    async def on_message(self, message):
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return await self.process_modmail(message)

        prefix = self.config.get('PREFIX', 'm.')

        if message.content.startswith(prefix):
            cmd = message.content[len(prefix):].strip()
            if cmd in self.snippets:
                message.content = f'{prefix}reply {self.snippets[cmd]}'
                
        await self.process_commands(message)
    
    async def on_message_delete(self, message):
        '''Support for deleting linked messages'''
        if message.embeds and not isinstance(message.channel, discord.DMChannel):
            matches = re.findall(r'Moderator - (\d+)', str(message.embeds[0].footer.text))
            if matches:
                user_id = None
                if not message.channel.topic:
                    user_id = await self.find_user_id_from_channel(message.channel)
                user_id = user_id or int(message.channel.topic.split(': ')[1])

                user = self.get_user(user_id)
                channel = user.dm_channel
                message_id = matches[0]

                async for msg in channel.history():
                    if msg.embeds:
                        if f'Moderator - {message_id}' == msg.embeds[0].footer.text:
                            await msg.delete()
                            break

    def overwrites(self, ctx, modrole=None):
        '''Permision overwrites for the guild.'''
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        if modrole:
            overwrites[modrole] = discord.PermissionOverwrite(read_messages=True)
        else:
            for role in self.guess_modroles(ctx):
                overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        return overwrites

    def help_embed(self, prefix):
        em = discord.Embed(color=0x00FFFF)
        em.set_author(name='Mod Mail - Help', icon_url=self.user.avatar_url)
        em.description = 'This bot is a python implementation of a "Mod Mail" bot. ' \
                         'Made by kyb3r and improved by the suggestions of others.' 

        cmds = f'`{prefix}setup` - Sets up the categories that will be used by the bot.\n' \
               f'`{prefix}about` - Shows general information about the bot.\n' \
               f'`{prefix}contact` - Allows a moderator to initiate a thread with a given recipient.\n' \
               f'`{prefix}reply <message...>` - Sends a message to the current thread\'s recipient.\n' \
               f'`{prefix}close` - Closes the current thread and deletes the channel.\n' \
               f'`{prefix}archive` - Closes the current thread and moves the channel to archive category.\n' \
               f'`{prefix}block` - Blocks a user from using modmail.\n' \
               f'`{prefix}blocked` - Shows a list of currently blocked users.\n' \
               f'`{prefix}unblock` - Unblocks a user from using modmail.\n' \
               f'`{prefix}snippets` - See a list of snippets that are currently configured.\n' \
               f'`{prefix}customstatus` - Sets the Bot status to whatever you want.\n' \
               f'`{prefix}disable` - Closes all threads and disables modmail for the server.\n' 

        warn = 'This bot saves no data and utilises channel topics for tracking and relaying messages.' \
               ' Therefore do not manually delete the category or channels as it will break the system. ' \
               'Modifying the channel topic will also break the system. Dont break the system buddy.'

        snippets = 'Snippets are shortcuts for predefined messages that you can send.' \
                   ' You can add snippets by adding config variables in the form **`SNIPPET_{NAME}`**' \
                   ' and setting the value to what you want the message to be. You can now use the snippet by' \
                   f' typing the command `{prefix}name` in the thread you want to reply to.'

        mention = 'If you want the bot to mention a specific role instead of @here,' \
                  ' you need to set a config variable **`MENTION`** and set the value ' \
                  'to the *mention* of the role or user you want mentioned. To get the ' \
                  'mention of a role or user, type `\@role` in chat and you will see ' \
                  'something like `<@&515651147516608512>` use this string as ' \
                  'the value for the config variable.'

        em.add_field(name='Commands', value=cmds)
        em.add_field(name='Snippets', value=snippets)
        em.add_field(name='Custom Mentions', value=mention)
        em.add_field(name='Warning', value=warn)
        em.add_field(name='Github', value='https://github.com/kyb3r/modmail')
        em.set_footer(text=f'Modmail v{__version__} | Star the repository to unlock hidden features! /s')

        return em
    
    async def data_loop(self):
        await self.wait_until_ready()

        while True:
            data = {
                "bot_id": self.user.id,
                "bot_name": str(self.user),
                "guild_id": self.guild_id,
                "guild_name": self.guild.name,
                "member_count": len(self.guild.members),
                "uptime": (datetime.datetime.utcnow() - self.start_time).total_seconds(),
                "version": __version__
            }

            await self.session.post('https://api.kybr.tk/modmail', data=data)
            await asyncio.sleep(3600)

    @property
    def uptime(self):
        now = datetime.datetime.utcnow()
        delta = now - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        fmt = '{h}h {m}m {s}s'
        if days:
            fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    @commands.command()
    async def help(self, ctx):
        prefix = self.config.get('PREFIX', 'm.')
        em = self.help_embed(prefix)
        await ctx.send(embed=em)
    
    @commands.command()
    async def about(self, ctx):
        em = discord.Embed(color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        em.set_author(name='Mod Mail - Information', icon_url=self.user.avatar_url)
        em.set_thumbnail(url=self.user.avatar_url)

        em.description = 'This is an open source discord bot made by kyb3r and '\
                         'improved upon suggestions by the users! This bot serves as a means for members to '\
                         'easily communicate with server leadership in an organised manner.'
        
        try:
            meta = await self.session.get('https://api.kybr.tk/modmail')
        except:
            meta = None

        em.add_field(name='Uptime', value=self.uptime)
        em.add_field(name='Latency', value=f'{self.latency*1000:.2f} ms')
        em.add_field(name='Version', value=f'[`{__version__}`](https://github.com/kyb3r/modmail/blob/master/bot.py#L45)')
        em.add_field(name='Author', value='[`kyb3r`](https://github.com/kyb3r)')
        
        footer = f'Bot ID: {self.user.id}'
        if meta:
            em.add_field(name='Instances', value=meta['instances'])
            if __version__ != meta['latest_version']:
                footer = f'Latest version available is {meta['latest_version']}'
        
        em.add_field(name='Github', value='https://github.com/kyb3r/modmail')

        em.set_footer(text=footer)

        await ctx.send(embed=em)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx, *, modrole: discord.Role=None):
        '''Sets up a server for modmail'''
        if discord.utils.get(ctx.guild.categories, name='Mod Mail'):
            return await ctx.send('This server is already set up.')

        categ = await ctx.guild.create_category(
            name='Mod Mail', 
            overwrites=self.overwrites(ctx, modrole=modrole)
            )
        archives = await ctx.guild.create_category(
            name='Mod Mail Archives',
            overwrites=self.overwrites(ctx, modrole=modrole)
        )
        await categ.edit(position=0)
        c = await ctx.guild.create_text_channel(name='bot-info', category=categ)
        await c.edit(topic='Manually add user id\'s to block users.\n\n'
                           'Blocked\n-------\n\n')
        await c.send(embed=self.help_embed(ctx.prefix))
        await ctx.send('Successfully set up server.')
    
    @commands.command(name='snippets')
    @commands.has_permissions(manage_messages=True)
    async def _snippets(self, ctx):
        '''Returns a list of snippets that are currently set.'''
        em = discord.Embed(color=discord.Color.green())
        em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
        first_line = 'Here is a list of snippets that are currently configured. '
        if not self.snippets:
            first_line = 'You dont have any snippets at the moment. '
        em.description =  first_line + 'You can add snippets by adding config variables in the form' \
                         ' **`SNIPPET_{NAME}`**'
        for name, value in self.snippets.items():
            em.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=em)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx, delete_archives: bool=False):
        '''Close all threads and disable modmail.'''
        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        archives = discord.utils.get(ctx.guild.categories, name='Mod Mail Archives')
        if not categ:
            return await ctx.send('This server is not set up.')
        em = discord.Embed(title='Thread Closed')
        em.description = f'{ctx.author.mention} has closed this modmail session.'
        em.color = discord.Color.red()
        for category, channels in ctx.guild.by_category():
            if category == categ:
                for chan in channels:
                    if 'User ID:' in str(chan.topic):
                        user_id = int(chan.topic.split(': ')[1])
                        user = self.get_user(user_id)
                        await user.send(embed=em)
                    await chan.delete()
        await categ.delete()
        if delete_archives:
            await archives.delete()
        await ctx.send('Disabled modmail.')

    @commands.command(name='close')
    @commands.has_permissions(manage_channels=True)
    async def _close(self, ctx):
        '''Close the current thread.'''
        user_id = None
        if not ctx.channel.topic:
            user_id = await self.find_user_id_from_channel(ctx.channel)
        elif 'User ID:' not in str(ctx.channel.topic) and not user_id:
            return await ctx.send('This is not a modmail thread.')

        user_id = user_id or int(ctx.channel.topic.split(': ')[1])
        user = self.get_user(user_id)
        em = discord.Embed(title='Thread Closed')
        em.description = f'{ctx.author.mention} has closed this modmail session.'
        em.color = discord.Color.red()
        if ctx.channel.category.name != 'Mod Mail Archives': # already closed.
            try:
                await user.send(embed=em)
            except:
                pass
        await ctx.channel.delete()
    
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def archive(self, ctx):
        '''
        Archive the current thread. (Visually closes the thread
        but moves the channel into an archives category instead of 
        deleteing the channel.)
        '''
        user_id = None

        if not ctx.channel.topic:
            user_id = await self.find_user_id_from_channel(ctx.channel)
        elif 'User ID:' not in str(ctx.channel.topic) and not user_id:
            return await ctx.send('This is not a modmail thread.')

        user_id = user_id or int(ctx.channel.topic.split(': ')[1])

        archives = discord.utils.get(ctx.guild.categories, name='Mod Mail Archives')

        if ctx.channel.category is archives:
            return await ctx.send('This channel is already archived.')

        user = self.get_user(user_id)
        em = discord.Embed(title='Thread Closed')
        em.description = f'{ctx.author.mention} has closed this modmail session.'
        em.color = discord.Color.red()

        try:
            await user.send(embed=em)
        except:
            pass

        await ctx.channel.edit(category=archives)
        done = discord.Embed(title='Thread Archived')
        done.description = f'{ctx.author.mention} has archived this modmail session.'
        done.color = discord.Color.red()
        await ctx.send(embed=done)
        await ctx.message.delete()

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        em = discord.Embed()
        em.title ='Pong! Websocket Latency:'
        em.description = f'{self.ws.latency * 1000:.4f} ms'
        em.color = 0x00FF00
        await ctx.send(embed=em)

    def guess_modroles(self, ctx):
        '''Finds roles if it has the manage_guild perm'''
        for role in ctx.guild.roles:
            if role.permissions.manage_guild:
                yield role

    def format_info(self, user, description=None):
        '''Get information about a member of a server
        supports users from the guild or not.'''
        server = self.guild
        member = self.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.datetime.utcnow()
        desc = description or f'{user.mention} has started a thread.'
        color = discord.Color.blurple()

        if member:
            roles = sorted(member.roles, key=lambda c: c.position)
            rolenames = ' '.join([r.mention for r in roles if r.name != "@everyone"])
            member_number = sorted(server.members, key=lambda m: m.joined_at).index(member) + 1
            for role in roles:
                if str(role.color) != "#000000":
                    color = role.color

        em = discord.Embed(colour=color, description=desc, timestamp=time)

        days = lambda d: (' day ago.' if d == '1' else ' days ago.')

        created = str((time - user.created_at).days)
        # em.add_field(name='Mention', value=user.mention)
        em.add_field(name='Registered', value=created + days(created))
        footer = 'User ID: '+str(user.id)
        em.set_footer(text=footer)
        em.set_thumbnail(url=avi)
        em.set_author(name=str(user), icon_url=avi)

        if member:
            joined = str((time - member.joined_at).days)
            em.add_field(name='Joined', value=joined + days(joined))
            em.add_field(name='Member No.',value=str(member_number),inline = True)
            em.add_field(name='Nickname', value=member.nick, inline=True)
            if rolenames:
                em.add_field(name='Roles', value=rolenames, inline=False)
        else:
            em.set_footer(text=footer+' | Note: this member is not part of this server.')
        
        

        return em

    async def send_mail(self, message, channel, from_mod, delete_message=True):
        author = message.author
        em = discord.Embed()
        em.description = message.content
        em.timestamp = message.created_at

        image_types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
        is_image_url = lambda u: any(urlparse(u).path.endswith(x) for x in image_types)

        delete_message = not bool(message.attachments) 
        attachments = list(filter(lambda a: not is_image_url(a.url), message.attachments))

        image_urls = [a.url for a in message.attachments]
        image_urls.extend(re.findall(r'(https?://[^\s]+)', message.content))
        image_urls = list(filter(is_image_url, image_urls))

        if image_urls:
            em.set_image(url=image_urls[0])

        if attachments:
            att = attachments[0]
            em.add_field(name='File Attachment', value=f'[{att.filename}]({att.url})')

        if from_mod:
            em.color=discord.Color.green()
            em.set_author(name=str(author), icon_url=author.avatar_url)
            em.set_footer(text=f'Moderator - {message.id}')
        else:
            em.color=discord.Color.gold()
            em.set_author(name=str(author), icon_url=author.avatar_url)
            em.set_footer(text='User')

        await channel.send(embed=em)

        if delete_message:
            try:
                await message.delete()
            except:
                pass

    async def process_reply(self, message, user_id=None):
        user_id = user_id or int(re.findall(r'\d+', message.channel.topic)[0])
        user = self.get_user(user_id)
        if not user:
            return await message.channel.send('This user does not have any mutual servers with the bot and is thus unreachable.')
        await asyncio.gather(
            self.send_mail(message, message.channel, from_mod=True),
            self.send_mail(message, user, from_mod=True)
        )

    def format_name(self, author, channels):
        name = author.name.lower()
        new_name = ''
        for letter in name:
            if letter in string.ascii_letters + string.digits:
                new_name += letter
        if not new_name:
            new_name = 'null'
        new_name += f'-{author.discriminator}'
        while new_name in [c.name for c in channels]:
            new_name += '-x' # two channels with same name
        return new_name

    @property
    def blocked_em(self):
        em = discord.Embed(title='Message not sent!', color=discord.Color.red())
        em.description = 'You have been blocked from using modmail.'
        return em

    async def process_modmail(self, message):
        '''Processes messages sent to the bot.'''

        guild = self.guild
        categ = discord.utils.get(guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        blocked = top_chan.topic.split('Blocked\n-------')[1].strip().split('\n')
        blocked = [x.strip() for x in blocked]
        reaction = '🚫' if str(message.author.id) in blocked else '✅'

        try:
            await message.add_reaction(reaction)
        except:
            pass

        if str(message.author.id) in blocked:
            await message.author.send(embed=self.blocked_em)
        else:
            channel = await self.create_thread(message.author)
            await self.send_mail(message, channel, from_mod=False)
            

    async def create_thread(self, user, *, creator=None):

        guild = self.guild
        topic = f'User ID: {user.id}'
        channel = discord.utils.get(guild.text_channels, topic=topic)
        categ = discord.utils.get(guild.categories, name='Mod Mail')
        archives = discord.utils.get(guild.categories, name='Mod Mail Archives')

        em = discord.Embed(title='Thanks for the message!')
        em.description = 'The moderation team will get back to you as soon as possible!'
        em.color = discord.Color.green()
        
        info_description = None

        if creator:
            em = discord.Embed(title='Modmail thread started')
            em.description = f'{creator.mention} has started a modmail thread with you.'
            em.color = discord.Color.green()

            info_description = f'{creator.mention} has created a thread with {user.mention}'

        mention = (self.config.get('MENTION') or '@here') if not creator else None


        if channel is not None:
            if channel.category is archives:
                if creator: # thread appears to be closed 
                    await user.send(embed=em)
                await channel.edit(category=categ)
                info_description = info_description or f'{user.mention} has reopened this thread.'
                await channel.send(mention, embed=self.format_info(user, info_description))
        else:
            await user.send(embed=em)
            channel = await guild.create_text_channel(
                name=self.format_name(user, guild.text_channels),
                category=categ
                )
            await channel.edit(topic=topic)
            await channel.send(mention, embed=self.format_info(user, info_description))
        
        return channel

    async def find_user_id_from_channel(self, channel):
        async for message in channel.history():
            if message.embeds:
                em = message.embeds[0]
                matches = re.findall(r'<@(\d+)>', str(em.description))
                if matches:
                    return int(matches[0])

    @commands.command()
    async def reply(self, ctx, *, msg=''):
        '''Reply to users using this command.'''
        ctx.message.content = msg

        categ = discord.utils.get(ctx.guild.categories, id=ctx.channel.category_id)
        if categ is not None and categ.name == 'Mod Mail':
            if ctx.channel.topic and 'User ID:' in ctx.channel.topic:
                await self.process_reply(ctx.message)
            if not ctx.channel.topic:
                user_id = await self.find_user_id_from_channel(ctx.channel)
                if user_id:
                    await self.process_reply(ctx.message, user_id=user_id)
    
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def contact(self, ctx, *, user: discord.Member):
        '''Create a thread with a specified member.'''
        categ = discord.utils.get(ctx.guild.categories, id=ctx.channel.category_id)
        channel = await self.create_thread(user, creator=ctx.author)
        
        em = discord.Embed(title='Created Thread')
        em.description = f'Thread started in {channel.mention} for {user.mention}'
        em.color = discord.Color.green()

        await ctx.send(embed=em)

    @commands.command(name="customstatus", aliases=['status', 'presence'])
    @commands.has_permissions(administrator=True)
    async def _status(self, ctx, *, message):
        '''Set a custom playing status for the bot.'''
        if message == 'clear':
            return await self.change_presence(activity=None)
        await self.change_presence(activity=discord.Game(message))
        em = discord.Embed(title='Status Changed')
        em.description = message
        em.color = discord.Color.green()
        em.set_footer(text='Note: this change is temporary.')
        await ctx.send(embed=em)
    
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def blocked(self, ctx):
        '''Returns a list of blocked users'''
        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        ids = re.findall(r'\d+', top_chan.topic)

        em = discord.Embed(title='Blocked Users', color=discord.Color.green())
        em.description = ''

        users = []
        not_reachable = []

        for id in ids:
            user = self.get_user(int(id))
            if user:
                users.append(user)
            else:
                not_reachable.append(id)
        
        em.description = 'Here is a list of blocked users.'
        
        if users:
            em.add_field(name='Currently Known', value=' '.join(u.mention for u in users))
        if not_reachable:
            em.add_field(name='Unknown', value='\n'.join(f'`{i}`' for i in not_reachable), inline=False)
        
        if not users and not not_reachable:
            em.description = 'Currently there are no blocked users'

        await ctx.send(embed=em)
        
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def block(self, ctx, id=None):
        '''Block a user from using modmail.'''
        if id is None:
            if 'User ID:' in str(ctx.channel.topic):
                id = ctx.channel.topic.split('User ID: ')[1].strip()
            else:
                return await ctx.send('No User ID provided.')

        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic += '\n' + id

        user = self.get_user(int(id))
        mention = user.mention if user else f'`{id}`'

        em = discord.Embed()
        em.color = discord.Color.green()

        if id not in top_chan.topic:  
            await top_chan.edit(topic=topic)

            em.title = 'Success'
            em.description = f'{mention} is now blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def unblock(self, ctx, id=None):
        '''Unblocks a user from using modmail.'''
        if id is None:
            if 'User ID:' in str(ctx.channel.topic):
                id = ctx.channel.topic.split('User ID: ')[1].strip()
            else:
                return await ctx.send('No User ID provided.')

        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic = topic.replace('\n'+id, '')

        user = self.get_user(int(id))
        mention = user.mention if user else f'`{id}`'

        em = discord.Embed()
        em.color = discord.Color.green()

        if id in top_chan.topic:  
            await top_chan.edit(topic=topic)

            em.title = 'Success'
            em.description = f'{mention} is no longer blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is not already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

    @commands.command(hidden=True, name='eval')
    async def _eval(self, ctx, *, body: str):
        """Evaluates python code"""
        allowed = [int(x) for x in self.config.get('OWNERS', '').split(',')]

        if ctx.author.id not in allowed: 
            return
        
        env = {
            'bot': self,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'source': inspect.getsource
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()
        err = out = None

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            err = await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
            return await err.add_reaction('\u2049')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            err = await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        out = await ctx.send(f'```py\n{value}\n```')
                    except:
                        await ctx.send('```Result is too long to send.```')
            else:
                self._last_result = ret
                try:
                    out = await ctx.send(f'```py\n{value}{ret}\n```')
                except:
                    await ctx.send('```Result is too long to send.```')
        if out:
            await ctx.message.add_reaction('\u2705') #tick
        if err:
            await ctx.message.add_reaction('\u2049') #x
        else:
            await ctx.message.add_reaction('\u2705')

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')
        
if __name__ == '__main__':
    bot = Modmail()
    bot.run(bot.token)
