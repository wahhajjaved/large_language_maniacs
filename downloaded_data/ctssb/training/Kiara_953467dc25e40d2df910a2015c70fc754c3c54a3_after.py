import asyncio
import datetime
import random
from .utils import time
from discord.ext import commands
import discord

EXCLUDED_CHANNELS = []


def exp_needed(level):
    return level*250


def exp_total(level):
    return sum([exp_needed(x) for x in range(level+1)])


def needs_profile(keys=None):
    async def predicate(ctx):
        if ctx.guild is None:
            return False

        if ctx.invoked_with == 'help':
            return True

        cog = ctx.bot.get_cog('Profiles')
        async with ctx.typing():
            ctx.profile = await cog.get_profile(ctx.author.id, keys)

        return True
    return commands.check(predicate)


class Profile:
    __slots__ = ('user_id', 'level', 'experience', 'fame', 'coins')

    def __init__(self, uid, **kwargs):
        self.user_id = uid
        self.level = kwargs.get('level', 1)
        self.experience = kwargs.get('experience', 0)
        self.coins = kwargs.get('coins', 0)

    async def save(self, db):
        s = ','.join([f'{s}={getattr(self,s,None)}' for s in self.__slots__[1:] if getattr(self, s, None) is not None])
        await db.execute(f"UPDATE profiles SET {s} WHERE user_id={self.user_id}")

    async def has_item(self, name=None):
        pass


class Profiles:
    """Stuff for profiles"""

    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self._lock = asyncio.Lock(loop=bot.loop)

    async def get_profile(self, uid, keys=None):
        s = ', '.join(keys)
        profile = await self.bot.db.fetchdict(f'SELECT {s or "*"} FROM profiles WHERE user_id={uid}')
        if not profile:
            await self.bot.db.execute(f'INSERT INTO profiles (user_id) VALUES ("{uid}")')
            return Profile(uid, level=1, experience=0, coins=0)
        return Profile(uid, **profile)

    async def on_message(self, msg):
        if not msg.guild:
            return
        if msg.channel.id in EXCLUDED_CHANNELS:
            return
        if msg.author.bot:
            return
        async with self._lock:
            profile = await self.get_profile(msg.author.id, ('level', 'experience', 'coins'))

            d = abs(msg.created_at - self.cooldowns.get(profile.user_id, datetime.datetime(2000, 1, 1)))
            if d < datetime.timedelta(seconds=5):
                return

            profile.experience += 10
            needed = exp_needed(profile.level)

            # Terrible temporary levelup
            if profile.experience >= needed:
                profile.level += 1
                profile.experience -= needed
                profile.coins += random.randint(1, 10)

                if profile.level % 5 == 0:
                    role = discord.utils.get(msg.guild.roles, name=str(profile.level))
                    if role:
                        await msg.author.add_roles(role, reason=f"Reached level {profile.level}")
                        rem = discord.utils.get(msg.guild.roles, name=str(max(profile.level-5, 1)))
                        await msg.author.remove_roles(rem, reason=f"Reached level {profile.level}")

            await profile.save(self.bot.db)
            self.cooldowns[profile.user_id] = msg.created_at

    async def on_member_join(self, member):
        profile = await self.get_profile(member.id, ('level',))
        role = discord.utils.get(member.guild.roles, name=str(profile.level//5*5))
        if role:
            await member.add_roles(role, reason=f"Re-joined the server at level {profile.level}")


    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def givegold(self, ctx, member: discord.Member, gold: int):
        async with self._lock:
            profile = await self.get_profile(member.id, ['coins'])
            profile.coins += gold
            await profile.save(self.bot.db)
            await ctx.send(f"{member} now has {profile.coins} gold")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def takegold(self, ctx, member: discord.Member, gold: int):
        async with self._lock:
            profile = await self.get_profile(member.id, ['coins'])
            profile.coins -= gold
            await profile.save(self.bot.db)
            await ctx.send(f"{member} now has {profile.coins} gold")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int, xp: int= None):
        async with self._lock:
            profile = await self.get_profile(member.id, ['level'])
            profile.level = level
            if xp:
                profile.experience = xp
            await profile.save(self.bot.db)
            await ctx.send(f"{member} is now level {level}")

    @commands.command()
    async def profile(self, ctx):
        """Display your profile"""
        member = ctx.author
        e = discord.Embed(title=member.display_name, colour=discord.Colour.green())
        e.set_thumbnail(url=member.avatar_url_as(size=128))
        e.add_field(name=f'Created', value=time.time_ago(member.created_at), inline=True)
        if ctx.guild:
            e.add_field(name=f'Joined', value=time.time_ago(member.joined_at), inline=True)
            e.add_field(name=f'Nickname', value=member.nick or "None", inline=False)
            e.add_field(name=f'Roles', value=' '.join([role.mention for role in member.roles[1:]]), inline=False)
        await ctx.send(embed=e)

    @commands.command(hidden=True)
    async def rank(self, ctx, member: discord.Member = None):
        if not member:
            member = ctx.author
        qry = f"""
        select `level`, `experience`, `rank` FROM
        (
        select t.*, @r := @r + 1 as `rank`
        from  profiles t,
        (select @r := 0) r
        order by `level` desc, `experience` desc
        ) as t
        where `user_id`={member.id}
        """
        lvl, xp, rank = await ctx.bot.db.fetchone(qry)
        em = discord.Embed(title=f'**{member.display_name}**',
                           description=f'**Rank {rank} - Lv{lvl}** {xp}/{exp_needed(lvl)}xp')
        await ctx.send(embed=em)

    @commands.command(hidden=True)
    async def leaderboard(self, ctx):
        guild = self.bot.get_guild(215424443005009920)
        qry = f"""
        select `user_id`, `level`, `experience`, `rank` FROM
        (
        select t.*, @r := @r + 1 as `rank`
        from  profiles t,
        (select @r := 0) r
        order by `level` desc, `experience` desc
        ) as t
        limit 10
        """
        r = await ctx.bot.db.fetch(qry)
        output = '```\n'+'\n'.join([f"{int(rank)} - {getattr(guild.get_member(user_id),'display_name','user_left')} - Lv{lvl} {xp}/{exp_needed(lvl)}xp" for user_id, lvl, xp, rank in r])+'```'
        await ctx.send(output)

    @commands.command(hidden=True)
    async def xp(self, ctx, member: discord.Member = None):
        if not member:
            member = ctx.author
        p = await self.get_profile(member.id, ('level', 'experience'))
        em = discord.Embed(title=f'**{member}**',
                           description=f'**Lv{p.level}** {p.experience}/{exp_needed(p.level)}xp')
        await ctx.send(embed=em)

    def get_top_color(self, roles):
        excluded = ['Muted']
        for role in roles[::-1]:
            if role.color != discord.Colour.default() and role.name not in excluded:
                return role
        return None

    @commands.command(hidden=True, aliases=['buy'])
    async def colors(self, ctx, *, color=None):
        # This is mostly temporary until shop data and items are stored in the database
        colors = {
            "Red":      424579184216506368,
            "Yellow":   424579315066208276,
            "Green":    424579385983762432,
            "Orange":   424579446578872332,
            "Cyan":     424579523363733507,
            "Blue":     424579641802752000,
            "Purple":   424579707573633024,
            "Pink":     424579770240466951,
            "Charcoal": 424579833994149888,
        }

        if color:
            color = color.capitalize()
            if color not in colors:
                return await ctx.send(f"{color} is not a valid color")

        owned = await self.bot.db.fetch(f'SELECT color FROM colors WHERE user_id={ctx.author.id}') or ((1,),)
        owned = [x[0] for x in owned]

        async with self._lock:
            profile = await self.get_profile(ctx.author.id, ('coins',))
            if color:
                if colors[color] not in owned:
                    if profile.coins >= 30:
                        profile.coins -= 30
                        await profile.save(self.bot.db)
                    else:
                        return await ctx.send(f"You don't have enough gold ({profile.coins}g)")
                    await self.bot.db.execute(f'INSERT INTO colors (user_id, color) VALUES ({ctx.author.id}, {colors[color]})')

                topcolor = self.get_top_color(ctx.author.roles)
                if topcolor:
                    await ctx.author.remove_roles(topcolor)

                role = discord.utils.get(ctx.guild.roles, id=colors[color])
                await ctx.author.add_roles(role)
                if colors[color] in owned:
                    await ctx.send(f"I swapped your color to {role.mention}!")
                else:
                    await ctx.send(f"You bought {role.mention}! You have {profile.coins}g left")
            else:
                em = discord.Embed(title="Color shop~", description="You can buy your colors here. To buy, type `~buy [color]`")
                for k, v in colors.items():
                    em.add_field(name=f'{k}', value="[Owned]" if v in owned else "30g")
                em.set_footer(text=f"You have {profile.coins} gold")
                await ctx.send(embed=em)


def setup(bot):
    bot.add_cog(Profiles(bot))
