# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2017 SML

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import discord
from discord.ext import commands
from discord.ext.commands import Context
from cogs.utils.chat_formatting import pagify
from .utils import checks
from random import choice
import math
from __main__ import send_cmd_help
from cogs.economy import SetParser

RULES_URL = "https://www.reddit.com/r/CRRedditAlpha/comments/584ba2/reddit_alpha_clan_family_rules/"
ROLES_URL = "https://www.reddit.com/r/CRRedditAlpha/wiki/roles"
DISCORD_URL = "http://discord.me/racf"

welcome_msg = "Hi {}! Are you in the Reddit Alpha Clan Family (RACF) / " \
              "interested in joining our clans / just visiting?"

CHANGECLAN_ROLES = ["Leader", "Co-Leader", "Elder", "High Elder", "Member"]
DISALLOWED_ROLES = ["SUPERMOD", "MOD", "Bot Commander",
                    "Higher Power", "AlphaBot"]
HEIST_ROLE = "Heist"
RECRUIT_ROLE = "Recruit"
TOGGLE_ROLES = ["Member"]
TOGGLEABLE_ROLES = ["Heist", "Practice", "Tourney", "Recruit"]
MEMBER_DEFAULT_ROLES = ["Member", "Tourney", "Practice"]
CLANS = [
    "Alpha", "Bravo", "Charlie", "Delta",
    "Echo", "Foxtrot", "Golf", "Hotel"]
BOTCOMMANDER_ROLE = ["Bot Commander"]


class RACF:
    """Display RACF specifc info.

    Note: RACF specific plugin for Red
    """

    def __init__(self, bot):
        """Constructor."""
        self.bot = bot

    @commands.command(pass_context=True, no_pm=True)
    async def racf(self, ctx: Context):
        """RACF Rules + Roles."""
        server = ctx.message.server

        color = ''.join([choice('0123456789ABCDEF') for x in range(6)])
        color = int(color, 16)

        data = discord.Embed(
            color=discord.Color(value=color),
            title="Rules + Roles",
            description="Important information for all members. Please read.")

        if server.icon_url:
            data.set_author(name=server.name, url=server.icon_url)
            data.set_thumbnail(url=server.icon_url)
        else:
            data.set_author(name=server.name)

        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say(
                "I need the `Embed links` permission to send this.")

        out = []
        out.append("**Rules**")
        out.append("<{}>".format(RULES_URL))
        out.append('')
        out.append("**Roles**")
        out.append("<{}>".format(ROLES_URL))
        out.append('')
        out.append("**Discord invite**")
        out.append("<{}>".format(DISCORD_URL))
        await self.bot.say('\n'.join(out))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*CHANGECLAN_ROLES)
    async def changeclan(self, ctx, clan: str=None):
        """Update clan role when moved to a new clan.

        Example: !changeclan Delta
        """
        clans = [c.lower() for c in CLANS]
        author = ctx.message.author
        server = ctx.message.server

        if clan is None:
            await send_cmd_help(ctx)
            return

        if clan.lower() not in clans:
            await self.bot.say(
                "{} is not a clan you can self-assign.".format(clan))
            return

        clan_roles = [r for r in server.roles if r.name.lower() in clans]

        to_remove_roles = set(author.roles) & set(clan_roles)
        to_add_roles = [
            r for r in server.roles if r.name.lower() == clan.lower()]

        await self.bot.remove_roles(author, *to_remove_roles)
        await self.bot.say("Removed {} for {}".format(
            ",".join([r.name for r in to_remove_roles]),
            author.display_name))

        await self.bot.add_roles(author, *to_add_roles)
        await self.bot.say("Added {} for {}".format(
            ",".join([r.name for r in to_add_roles]),
            author.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def addrole(
            self, ctx, member: discord.Member=None, role_name: str=None):
        """Add role to a user.

        Example: !addrole SML Delta

        Role name needs be in quotes if it is a multi-word role.
        """
        server = ctx.message.server
        author = ctx.message.author
        if member is None:
            await self.bot.say("You must specify a member.")
            return
        if role_name is None:
            await self.bot.say("You must specify a role.")
            return
        if role_name.lower() in [r.lower() for r in DISALLOWED_ROLES]:
            await self.bot.say("You are not allowed to add those roles.")
            return
        if role_name.lower() not in [r.name.lower() for r in server.roles]:
            await self.bot.say("{} is not a valid role.".format(role_name))
            return

        desired_role = discord.utils.get(server.roles, name=role_name)
        rh = server.role_hierarchy
        if rh.index(desired_role) < rh.index(author.top_role):
            await self.bot.say(
                "{} does not have permission to edit {}.".format(
                    author.display_name, role_name))
            return

        to_add_roles = [
            r for r in server.roles if (
                r.name.lower() == role_name.lower())]
        await self.bot.add_roles(member, *to_add_roles)
        await self.bot.say("Added {} for {}".format(
            role_name, member.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def removerole(
            self, ctx, member: discord.Member=None, role_name: str=None):
        """Remove role from a user.

        Example: !removerole SML Delta

        Role name needs be in quotes if it is a multi-word role.
        """
        server = ctx.message.server
        if member is None:
            await self.bot.say("You must specify a member.")
        elif role_name is None:
            await self.bot.say("You must specify a role.")
        elif role_name.lower() in [r.lower() for r in DISALLOWED_ROLES]:
            await self.bot.say("You are not allowed to remove those roles.")
        elif role_name.lower() not in [r.name.lower() for r in server.roles]:
            await self.bot.say("{} is not a valid role.".format(role_name))
        else:
            to_remove_roles = [
                r for r in server.roles if (
                    r.name.lower() == role_name.lower())]
            await self.bot.remove_roles(member, *to_remove_roles)
            await self.bot.say("Removed {} from {}".format(
                role_name, member.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def changerole(self, ctx, member: discord.Member=None, *roles: str):
        """Change roles of a user.

        Example: !changerole SML +Delta "-Foxtrot Lead" "+Delta Lead"

        Multi-word roles must be surrounded by quotes.
        Operators are used as prefix:
        + for role addition
        - for role removal
        """
        server = ctx.message.server
        author = ctx.message.author
        if member is None:
            await self.bot.say("You must specify a member")
            return
        elif roles is None or not roles:
            await self.bot.say("You must specify a role.")
            return

        server_role_names = [r.name for r in server.roles]
        role_args = []
        flags = ['+', '-']
        for role in roles:
            has_flag = role[0] in flags
            flag = role[0] if has_flag else '+'
            name = role[1:] if has_flag else role

            if name.lower() in [r.lower() for r in server_role_names]:
                role_args.append({'flag': flag, 'name': name})

        plus = [r['name'].lower() for r in role_args if r['flag'] == '+']
        minus = [r['name'].lower() for r in role_args if r['flag'] == '-']
        disallowed_roles = [r.lower() for r in DISALLOWED_ROLES]

        for role in server.roles:
            if role.name.lower() not in disallowed_roles:
                if role.name.lower() in minus:
                    await self.bot.remove_roles(member, role)
                    await self.bot.say(
                        "Removed {} from {}".format(
                            role.name, member.display_name))
                if role.name.lower() in plus:
                    # respect role hiearchy
                    rh = server.role_hierarchy
                    if rh.index(role) < rh.index(author.top_role):
                        await self.bot.say(
                            "{} does not have permission to edit {}.".format(
                                author.display_name, role.name))
                    else:
                        await self.bot.add_roles(member, role)
                        await self.bot.say(
                            "Added {} for {}".format(
                                role.name, member.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(mention_everyone=True)
    async def mentionusers(self, ctx, role: str, *msg):
        """Mention users by role.

        Example:
        !mentionusers Delta Anyone who is 4,300+ please move up to Charlie!

        Note: only usable by people with the permission to mention @everyone
        """
        server = ctx.message.server
        server_roles_names = [r.name for r in server.roles]

        if role not in server_roles_names:
            await self.bot.say(
                "{} is not a valid role on this server.".format(role))
        elif not msg:
            await self.bot.say("You have not entered any messages.")
        else:
            out_mentions = []
            for m in server.members:
                if role in [r.name for r in m.roles]:
                    out_mentions.append(m.mention)
            await self.bot.say("{} {}".format(" ".join(out_mentions),
                                              " ".join(msg)))

    @commands.command(pass_context=True, no_pm=True)
    async def avatar(self, ctx, member: discord.Member=None):
        """Display avatar of the user."""
        author = ctx.message.author

        if member is None:
            member = author
        avatar_url = member.avatar_url
        data = discord.Embed()
        data.set_image(url=avatar_url)
        await self.bot.say(embed=data)

    @commands.command(pass_context=True, no_pm=True)
    async def serverinfo2(self, ctx: Context):
        """Show server's informations specific to RACF."""
        server = ctx.message.server
        online = len([m.status for m in server.members
                      if m.status == discord.Status.online or
                      m.status == discord.Status.idle])
        total_users = len(server.members)
        text_channels = len([x for x in server.channels
                             if x.type == discord.ChannelType.text])
        voice_channels = len(server.channels) - text_channels
        passed = (ctx.message.timestamp - server.created_at).days
        created_at = ("Since {}. That's over {} days ago!"
                      "".format(server.created_at.strftime("%d %b %Y %H:%M"),
                                passed))

        role_names = [
            "Leader", "Co-Leader", "High Elder", "Elder",
            "Member", "Honorary Member", "Visitor"]
        role_count = {}
        for role_name in role_names:
            role_count[role_name] = len(
                [m for m in server.members
                    if role_name in [r.name for r in m.roles]])

        colour = ''.join([choice('0123456789ABCDEF') for x in range(6)])
        colour = int(colour, 16)

        data = discord.Embed(
            description=created_at,
            colour=discord.Colour(value=colour))
        data.add_field(name="Region", value=str(server.region))
        data.add_field(name="Users", value="{}/{}".format(online, total_users))
        data.add_field(name="Text Channels", value=text_channels)
        data.add_field(name="Voice Channels", value=voice_channels)
        data.add_field(name="Roles", value=len(server.roles))
        data.add_field(name="Owner", value=str(server.owner))
        data.add_field(name="\a", value="\a", inline=False)

        for role_name in role_names:
            data.add_field(name="{}s".format(role_name),
                           value=role_count[role_name])

        data.set_footer(text="Server ID: " + server.id)

        if server.icon_url:
            data.set_author(name=server.name, url=server.icon_url)
            data.set_thumbnail(url=server.icon_url)
        else:
            data.set_author(name=server.name)

        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say("I need the `Embed links` permission "
                               "to send this")

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(administrator=True)
    async def member2roles(self, ctx: Context, with_role, new_role):
        """Add role to a list of users with specific roles."""
        server = ctx.message.server
        with_role = discord.utils.get(server.roles, name=with_role)
        new_role = discord.utils.get(server.roles, name=new_role)
        if with_role is None:
            await self.bot.say('{} is not a valid role'.format(with_role))
            return
        if new_role is None:
            await self.bot.say('{} is not a valid role.'.format(new_role))
            return
        members = [m for m in server.members if with_role in m.roles]
        for member in members:
            await self.bot.add_roles(member, new_role)
            await self.bot.say("Added {} for {}".format(
                new_role, member.display_name))

    @commands.command(pass_context=True, no_pm=True, aliases=["m2v"])
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def member2visitor(self, ctx: Context, *members: discord.Member):
        """Re-assign list of people from members to visitors."""
        server = ctx.message.server
        to_remove_roles = [
            r for r in server.roles if r.name in MEMBER_DEFAULT_ROLES]
        to_add_roles = [r for r in server.roles if r.name == 'Visitor']
        for member in members:
            await self.bot.add_roles(member, *to_add_roles)
            await self.bot.say("Added {} for {}".format(
                ", ".join([r.name for r in to_add_roles]), member.display_name))
            await self.bot.remove_roles(member, *to_remove_roles)
            await self.bot.say("Removed {} from {}".format(
                ", ".join([r.name for r in to_remove_roles]), member.display_name))

    @commands.command(pass_context=True, no_pm=True, aliases=["v2m"])
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def visitor2member(
            self, ctx: Context, member: discord.Member, *roles):
        """Assign visitor to member and add clan name."""
        server = ctx.message.server
        to_add_roles = [
            r for r in server.roles if r.name in MEMBER_DEFAULT_ROLES]
        to_add_roles.extend(
            [r for r in server.roles if r.name.lower() in
                [r2.lower() for r2 in roles]])
        to_remove_roles = [r for r in server.roles if r.name == 'Visitor']

        await self.bot.add_roles(member, *to_add_roles)
        await self.bot.say("Added {} for {}".format(
            ", ".join([r.name for r in to_add_roles]), member.display_name))
        await self.bot.remove_roles(member, *to_remove_roles)
        await self.bot.say("Removed {} from {}".format(
            ", ".join([r.name for r in to_remove_roles]), member.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def dmusers(self, ctx: Context, msg: str=None,
                      *members: discord.Member):
        """Send a DM to a list of people.

        Example
        !dmusers "Please move up to Charlie" @SML @6john Meridian
        """
        if msg is None:
            await self.bot.say("Please include a message.")
        elif not len(members):
            await self.bot.say("You must include at least one member.")
        else:
            data = discord.Embed(description=msg)
            data.set_author(
                name=ctx.message.author,
                icon_url=ctx.message.author.avatar_url)
            data.set_footer(text=ctx.message.server.name)
            data.add_field(
                name="How to reply",
                value="DM or tag {0.mention} if you want to reply.".format(
                    ctx.message.author))
            for m in members:
                await self.bot.send_message(m, embed=data)
                await self.bot.say("Message sent to {}".format(m.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*BOTCOMMANDER_ROLE)
    async def changenick(
            self, ctx: Context, member: discord.Member, nickname: str):
        """Change the nickname of a member.

        Example
        !changenick SML "New Nick"
        !changenick @SML "New Nick"
        """
        # await self.bot.change_nickname(member, nickname)
        try:
            await self.bot.change_nickname(member, nickname)
        except discord.HTTPException:
            await self.bot.say(
                "I don’t have permission to do this.")
        else:
            await self.bot.say(f"{member.mention} changed to {nickname}.")

    @commands.command(pass_context=True, no_pm=True)
    async def emojis(self, ctx: Context):
        """Show all emojis available on server."""
        server = ctx.message.server
        out = []
        for emoji in server.emojis:
            emoji_str = str(emoji)
            out.append("{} `:{}:`".format(emoji_str, emoji.name))
        for page in pagify("\n".join(out), shorten_by=12):
            await self.bot.say(page)


    @commands.command(pass_context=True, no_pm=True)
    async def trophy2rank(self, ctx: Context, trophies:int):
        """Convert trophies to rank.

        log10(rank) = -2.102e-3 * trophies + 14.245
        """
        # log_a(b) = (log_e b / log_e a))
        # (log_a b = 3 => b = a^3)
        rank = 10 ** (-2.102e-3 * int(trophies) + 14.245)
        rank = int(rank)
        await self.bot.say(
            f"With {trophies} trophies, the approximate rank you will get is {rank:d}")
        await self.bot.say("Calculated using 28 data points only so it may not be accurate.")

    @commands.command(pass_context=True, no_pm=True)
    async def rank2trophy(self, ctx: Context, rank:int):
        """Convert rank to trophies.

        log10(rank) = -2.102e-3 * trophies + 14.245
        """
        trophies = (math.log10(int(rank)) - 14.245) / -2.102e-3
        trophies = int(trophies)
        await self.bot.say(
            f"Rank {rank} will need approximately {trophies:d} trophies.")
        await self.bot.say("Calculated using 28 data points only so it may not be accurate.")

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions()
    async def bankset(
            self, ctx: Context, user: discord.Member, credits: SetParser):
        """Work around to allow MODs to set bank."""
        econ = self.bot.get_cog("Economy")
        await ctx.invoke(econ._set, user, credits)

    @commands.group(pass_context=True, no_pm=True)
    @checks.mod_or_permissions()
    async def removereaction(self, ctx:Context):
        """Remove reactions from messages."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @removereaction.command(name="messages", pass_context=True, no_pm=True)
    async def removereaction_messages(self, ctx: Context, number: int):
        """Removes reactions from last X messages."""
        channel = ctx.message.channel
        author = ctx.message.author
        server = author.server
        is_bot = self.bot.user.bot
        has_permissions = channel.permissions_for(server.me).manage_messages
        to_manage = []

        if not has_permissions:
            await self.bot.say("I’m not allowed to remove reactions.")
            return

        async for message in self.bot.logs_from(channel, limit=number+1):
            to_manage.append(message)

        await self.remove_reactions(to_manage)

    async def remove_reactions(self, messages):
        for message in messages:
            await self.bot.clear_reactions(message)

    @commands.command(pass_context=True, no_pm=True)
    async def toggleheist(self, ctx: Context):
        """Self-toggle heist role."""
        author = ctx.message.author
        server = ctx.message.server
        heist_role = discord.utils.get(
            server.roles, name=HEIST_ROLE)
        if heist_role in author.roles:
            await self.bot.remove_roles(author, heist_role)
            await self.bot.say(
                "Removed {} role from {}.".format(
                    HEIST_ROLE, author.display_name))
        else:
            await self.bot.add_roles(author, heist_role)
            await self.bot.say(
                "Added {} role for {}.".format(
                    HEIST_ROLE, author.display_name))

    @commands.command(pass_context=True, no_pm=True)
    async def togglerecruit(self, ctx: Context):
        """Self-toggle heist role."""
        author = ctx.message.author
        server = ctx.message.server
        role = discord.utils.get(
            server.roles, name=RECRUIT_ROLE)
        if role in author.roles:
            await self.bot.remove_roles(author, role)
            await self.bot.say(
                "Removed {} role from {}.".format(
                    HEIST_ROLE, author.display_name))
        else:
            await self.bot.add_roles(author, role)
            await self.bot.say(
                "Added {} role for {}.".format(
                    RECRUIT_ROLE, author.display_name))

    @commands.command(pass_context=True, no_pm=True)
    @commands.has_any_role(*TOGGLE_ROLES)
    async def togglerole(self, ctx: Context, role_name):
        """Self-toggle role assignments."""
        author = ctx.message.author
        server = ctx.message.server
        toggleable_roles = [r.lower() for r in TOGGLEABLE_ROLES]
        if role_name.lower() in toggleable_roles:
            role = [
                r for r in server.roles
                if r.name.lower() == role_name.lower()]
            # role = discord.utils.get(server.roles, name=role_name)
            if role is not None:
                role = role[0]
                if role in author.roles:
                    await self.bot.remove_roles(author, role)
                    await self.bot.say(
                        "Removed {} role from {}.".format(
                            role_name, author.display_name))
                else:
                    await self.bot.add_roles(author, role)
                    await self.bot.say(
                        "Added {} role for {}.".format(
                            role_name, author.display_name))
            else:
                await self.bot.say(
                    "{} is not a valid role on this server.".format(role_name))
        else:
            out = []
            out.append("{} is not a toggleable role.".format(role_name))
            out.append(
                "Toggleable roles: {}.".format(", ".join(TOGGLEABLE_ROLES)))
            await self.bot.say("\n".join(out))


def setup(bot):
    r = RACF(bot)
    bot.add_cog(r)
