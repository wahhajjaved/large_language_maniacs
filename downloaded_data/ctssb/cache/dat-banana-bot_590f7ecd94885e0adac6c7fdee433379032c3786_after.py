import discord
import brawlstats
import box
from discord.ext import commands


class BS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = brawlstats.BrawlAPI(
            token=bot.config.bsapi,
            session=bot.session,
            is_async=True
        )

    def check_tag(self, tag):
        return [char for char in tag if char.upper() not in '0289PYLQGRJCUV']

    async def get_tag(self, id):
        find = await self.bot.db.bstags.find_one({"id": id})
        found_tag = None
        try:
            found_tag = find["tag"]
        except:
            pass
        return found_tag


    def emoji(self, _id):
        return self.bot.get_emoji(_id)

    def brawler(self, name):
        name = name.replace("8-Bit", "8bit")
        name = name.replace(" ", "")
        name = name.lower()
        return discord.utils.get(self.bot.get_guild(645624855580114965).emojis, name=name)

    def between(self, number, min, max):
        return min <= number < max

    def get_event_emoji(self, name):
        events = {
            "Gem Grab": self.bot.get_emoji(650852285613604890),
            "Heist": self.bot.get_emoji(650852285794222138),
            "Bounty": self.bot.get_emoji(650852285395632211),
            "Siege": self.bot.get_emoji(650854441599107103),
            "Brawl Ball": self.bot.get_emoji(650852285794091047),
            "Lone Star": self.bot.get_emoji(650852284896641024),
            "Takedown": self.bot.get_emoji(650852284934127657),
            "Robo Rumble": self.bot.get_emoji(650852285131390980),
            "Big Game": self.bot.get_emoji(650852285328523294),
            "Boss Fight": self.bot.get_emoji(650852285056024597),
            "Showdown": self.bot.get_emoji(650852285160751135)
        }
        if name in events.keys():
            return events[name]
        else:
            return self.bot.get_emoji(650856644388847637)

    def fmt_time(self, time):
        if time < 86400:
            hours = int(time / 3600)
            minutes = int(time / 60 - hours * 60)
            return f"{hours} hrs, {minutes} mins"
        else:
            days = int(time/86400)
            hours = int(time / 3600 - days * 24)
            minutes = int(time / 60 - hours * 60 - days * 1440)
            return f"{days} days, {hours} hrs, {minutes} mins"

    async def cog_command_error(self, ctx, error):
        if isinstance(error, brawlstats.RequestError):
            em = discord.Embed(
                color=discord.Color.red(),
                title=f'{error.code} - {error.__class__.__name__}',
                description=error.error.split('\nURL')[0]  # chop off the requested URL
            )
            await ctx.send(embed=em)

    @commands.command()
    async def bssave(self, ctx, tag):
        """Saves your Brawl Stars tag to your Discord account."""
        tag = tag.strip("#")
        invalid_chars = self.check_tag(tag)
        if invalid_chars:
            return await ctx.send(f"Looks like that's an invalid tag!\nInvalid characters: {', '.join()}")
        await self.bot.db.bstags.update_one({"id": ctx.author.id}, {"$set": {"tag": tag}}, upsert=True)
        await ctx.send(f"Your Brawl Stars tag has been successfully saved. {self.emoji(484897652220362752)}")


    @commands.command()
    async def bsprofile(self, ctx, tag=None):
        await ctx.trigger_typing()
        if not tag:
            tag = await self.get_tag(ctx.author.id)
            if not tag:
                return await ctx.send("You didn't save a Brawl Stars tag to your profile. Time to get it saved!")
        else:
            tag = tag.strip('#')
            invalid_chars = self.check_tag(tag)
            if invalid_chars:
                return await ctx.send(f"Invalid characters: {', '.join(invalid_chars)}")

        profile = await self.client.get_player(tag)
        club = profile.club
        em = discord.Embed(color=0x00ff00, title=f"{profile.name} (#{profile.tag})")
        em.add_field(name="Trophies", value=f"{profile.trophies} {self.emoji(523919154630361088)}")
        em.add_field(name="Highest Trophies", value=f"{profile.highest_trophies} {self.emoji(523919154630361088)}")
        em.add_field(name="XP Level", value=f"{profile.expLevel} ({profile.exp_fmt}) {self.emoji(523924578314092544)}")
        em.add_field(name="Victories", value=f"**Total:** {profile.victories} {self.emoji(523919154751733762)}\n\
            **Solo Showdown:** {profile.solo_showdown_victories} {self.emoji(523923170755870720)}\n\
            **Duo Showdown:** {profile.duo_showdown_victories} {self.emoji(523923170671984656)}")
        em.add_field(name="Best Time as Big Brawler", value=f"{profile.best_time_as_big_brawler} {self.emoji(523923170970042378)}")
        em.add_field(name="Best Robo Rumble Time", value=f"{profile.best_robo_rumble_time} {self.emoji(523926186620092426)}")
        em.add_field(name="Brawlers", value=f"**{profile.brawlers_unlocked}/30**", inline=False)
        if club:
            em.add_field(name="Club", value=f"{club.name} (#{club.tag})", inline=False)
            em.add_field(name="Role", value=club.role)
            em.add_field(name="Trophies", value=club.trophies)
            em.add_field(name="Required Trophies", value=club.required_trophies)
            em.add_field(name="Members", value=club.members)
        else:
            em.add_field(name="Club", value=f"No club. {self.bot.get_emoji(522524669459431430)}")
        em.set_thumbnail(url=profile.avatar_url)
        await ctx.send(embed=em)

    @commands.command(aliases=["bsclan"])
    async def bsclub(self, ctx, tag=None):
        await ctx.trigger_typing()
        if not tag:
            profile_tag = await self.get_tag(ctx.author.id)
            if not profile_tag:
                return await ctx.send("You didn't save a Brawl Stars tag to your profile. Time to get it saved!")
            profile = await self.client.get_profile(profile_tag)
            club = await profile.get_club()
        else:
            tag = tag.strip('#')
            invalid_chars = self.check_tag(tag)
            if invalid_chars:
                return await ctx.send(f"Invalid characters: {', '.join(invalid_chars)}")
            club = await self.client.get_club(tag)

        em = discord.Embed(color=ctx.author.color, title=f"{club.name} (#{club.tag})")
        em.description = club.description
        em.add_field(name="Trophies", value=f"{club.trophies}")
        em.add_field(name="Members", value=f"**{club.members_count}**/100")
        em.add_field(name="Online Members", value=f"**{club.online_members}**/{club.members_count}")
        em.add_field(name="Required Trophies", value=club.required_trophies)
        em.add_field(name="Status", value=club.status)
        em.set_thumbnail(url=club.badge_url)
        await ctx.send(embed=em)

    @commands.command()
    async def bsbrawlers(self, ctx, tag=None):
        await ctx.trigger_typing()
        if not tag:
            tag = await self.get_tag(ctx.author.id)
            if not tag:
                return await ctx.send("You didn't save a Brawl Stars tag to your profile. Time to get it saved!")
        else:
            tag = tag.strip('#')
            invalid_chars = self.check_tag(tag)
            if invalid_chars:
                return await ctx.send(f"Invalid characters: {', '.join(invalid_chars)}")

        profile = await self.client.get_player(tag)
        em = discord.Embed(title=f"{profile.name} | #{tag}")
        average = 0
        for x in profile.brawlers:
            em.add_field(name=f"{x['name']} {self.brawler(x['name'])}", value=f"R. **{x['rank']}**: {x['power']} {self.bot.get_emoji(645739308711542828) if x['power'] < 10 else self.bot.get_emoji(645762041751273512)} | {x['trophies']} {self.bot.get_emoji(645733305123078155)} | {x['highestTrophies']} {self.bot.get_emoji(645734801139302430)}")
            average += x["trophies"]
        em.description = f"""
**Brawlers:** {len(profile.brawlers)}/30
**Average Trophies:** {int(average/len(profile.brawlers))}
        """
        await ctx.send(embed=em)

    @commands.command()
    async def bsseason(self, ctx, tag=None):
        """Find your end-of-season rewards and trophy loss."""
        await ctx.trigger_typing()
        if not tag:
            tag = await self.get_tag(ctx.author.id)
            if not tag:
                return await ctx.send("You didn't save a Brawl Stars tag to your profile. Time to get it saved!")
        else:
            tag = tag.strip('#')
            invalid_chars = self.check_tag(tag)
            if invalid_chars:
                return await ctx.send(f"Invalid characters: {', '.join(invalid_chars)}")

        profile = await self.client.get_player(tag)
        starpoints = 0
        trophies_lost = 0
        for x in profile.brawlers:
            t = x["trophies"]
            total_starpoints = 0
            trophy_loss = 0
            if 550 <= t < 600:
                total_starpoints = 70
                trophy_loss = t - 525
            elif 600 <= t < 650:
                total_starpoints = 120
                trophy_loss = t - 550
            elif 650 <= t < 700:
                total_starpoints = 160
                trophy_loss = t - 575
            elif 700 <= t < 750:
                total_starpoints = 200
                trophy_loss = t - 600
            elif 750 <= t < 800:
                total_starpoints = 220
                trophy_loss = t - 625
            elif 800 <= t < 850:
                total_starpoints = 240
                trophy_loss = t - 650
            elif 850 <= t < 899:
                total_starpoints = 260
                trophy_loss = t - 675
            elif 900 <= t < 950:
                total_starpoints = 280
                trophy_loss = t - 700
            elif 950 <= t < 1000:
                total_starpoints = 300
                trophy_loss = t - 725
            elif 1000 <= t < 1050:
                total_starpoints = 320
                trophy_loss = t - 750
            elif 1050 <= t < 1100:
                total_starpoints = 340
                trophy_loss = t - 775
            elif 1100 <= t < 1150:
                total_starpoints = 360
                trophy_loss = t - 800
            elif 1150 <= t < 1200:
                total_starpoints = 380
                trophy_loss = t - 825
            elif 1200 <= t < 1250:
                total_starpoints = 400
                trophy_loss = t - 850
            elif 1250 <= t < 1300:
                total_starpoints = 420
                trophy_loss = t - 875
            elif 1300 <= t < 1350:
                total_starpoints = 440
                trophy_loss = t - 900
            elif 1350 <= t < 1400:
                total_starpoints = 460
                trophy_loss = t - 925
            elif t >= 1400:
                total_starpoints = 480
                trophy_loss = t - 950
            starpoints += total_starpoints
            trophies_lost += trophy_loss
        await ctx.send(f"You will gain **{starpoints}** {self.bot.get_emoji(645617676550668288)} at the end of the season. You will lose **{trophies_lost}** {self.bot.get_emoji(645620279439130639)}. Classy!")

    @commands.command()
    async def bsevents(self, ctx):
        await ctx.trigger_typing()
        events = await self.client.get_events()
        current_events = events.current
        next_events = events.upcoming
        em = discord.Embed(title=f"Brawl Stars Events", color=ctx.author.color)
        desc = ""
        desc += "**__Current__**\n"
        for e in current_events:
            e = box.Box(e)
            desc += f"{self.get_event_emoji(e.gameMode)}{e.slotName}: **{e.gameMode}**\n{e.mapName}\n{self.bot.get_emoji(650865620094681108)} **Ends in:** {self.fmt_time(e.endTimeInSeconds)}"
            if e.hasModifier:
                desc += f" (Modifier: {e.modifierName})"
            desc += "\n\n"
        desc += "\n**__Upcoming__**\n"
        for e in next_events:
            e = box.Box(e)
            desc += f"{self.get_event_emoji(e.gameMode)}{e.slotName}: **{e.gameMode}**\n{e.mapName}\n{self.bot.get_emoji(650865620094681108)} **Starts in:** {self.fmt_time(e.startTimeInSeconds)}"
            if e.hasModifier:
                desc += f" (Modifier: **{e.modifierName}**)"
            desc += "\n\n"
        em.description = desc
        em.set_footer(text=str(ctx.author), icon_url=str(ctx.author.avatar_url))
        await ctx.send(embed=em)
        
    @commands.command()
    async def bstimes(self, ctx):
        await ctx.trigger_typing()
        data = await self.client.get_misc()
        em = discord.Embed(title="Brawl Stars Reset Times", color=ctx.author.color)
        em.description = f"""
**Times until...**
{self.bot.get_emoji(650865620094681108)} **Shop Reset:** {self.fmt_time(data.time_until_shop_reset_in_seconds)}
{self.bot.get_emoji(650865620094681108)} **Season Reset:** {self.fmt_time(data.time_until_season_end_in_seconds)}
        """
        em.set_footer(text=str(ctx.author), icon_url=str(ctx.author.avatar_url))
        await ctx.send(embed=em)
    
    @commands.command()
    async def bsbattle(self, ctx, tag=None):
        """Gets the last battle the player did."""
        await ctx.trigger_typing()
        if not tag:
            tag = await self.get_tag(ctx.author.id)
            if not tag:
                return await ctx.send("You didn't save a Brawl Stars tag to your profile. Time to get it saved!")
        else:
            tag = tag.strip('#')
            invalid_chars = self.check_tag(tag)
            if invalid_chars:
                return await ctx.send(f"Invalid characters: {', '.join(invalid_chars)}")

        battle = (await self.client.get_battle_logs(tag))[0]
        #battle = box.Box(battle)
        profile = await self.client.get_profile(tag)
        em = discord.Embed(title=f"{profile.name} | #{tag}")
        desc = ""
        desc += f"""
**{battle['battle']['result'].upper()}: {battle['battle']['type'].title()}** ({"+" if battle['battle']['result'] == "victory" else "−" if battle['battle']['result'] == "defeat" else ""}{abs(battle['battle']['trophyChange'])})
(**{battle['event']['mode'].title()}**: {battle['event']['map'].title()})
**Duration:** {self.fmt_time(battle['battle']['duration'])}\n"""
        if battle['event']['mode'] == "showdown" or battle['event']['mode'] == "takedown" or battle['event']['mode'] == "lone star":
            counter = 0
            desc += "__**Players:**__\n"
            for x in battle['battle']['players']:
                counter += 1
                desc += f"`{counter}.` {x['name']} ({x['tag']}){self.brawler(x['brawler']['name'])} {x['brawler']['power']} {self.bot.get_emoji(645739308711542828)}  | {x['brawler']['trophies']} {self.bot.get_emoji(645733305123078155)}\n"
        else:
            for x in battle['battle']['teams']:
                desc += "**__Your Team__**\n" if x == battle['battle']['teams'][0] else "**__Enemy Team__**\n"
                for i in x:
                    desc += f"{i['name']} ({i['tag']})\n{self.brawler(i['brawler']['name'])} {i['brawler']['power']} {self.bot.get_emoji(645739308711542828)}  | {i['brawler']['trophies']} {self.bot.get_emoji(645733305123078155)}"
                    if i['name'] == battle['battle']['starPlayer'].name:
                        desc += "(:star2: **STAR PLAYER** :star2:)\n"
                    else:
                        desc += "\n"
        print(len(desc))
        em.description = desc
        
        em.set_footer(text=str(ctx.author), icon_url=str(ctx.author.avatar_url))
        await ctx.send(embed=em)
            


def setup(bot):
    bot.add_cog(BS(bot))