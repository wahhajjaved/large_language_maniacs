import discord
import os
import io
import idioticapi
import random
import json
from discord.ext import commands


class Idiotic:
    def __init__(self, bot):
        self.bot = bot
        with open('data/apikeys.json') as f:
            lol = json.load(f)
        self.token = lol.get("idioticapi")
        self.client = idioticapi.Client(self.token, dev=True)

    def format_avatar(self, avatar_url):
        if avatar_url.endswith(".gif"):
            return avatar_url + "?size=2048"
        return avatar_url.replace("webp", "png")

    @commands.command()
    async def blurple(self, ctx, user: discord.Member = None):
        """Turn your profile pic into blurple!"""
        user = user or ctx.author
        params = {
            "type": "blurplify",
            "image": user.avatar_url
        }
        resp = await self.bot.session.get("https://nekobot.xyz/api/imagegen", params=params)
        resp = await resp.json()
        if not resp['success']:
            return await ctx.send("An error occurred with the API.")
        em = discord.Embed(color=ctx.author.color, title="Blurple!")
        em.set_image(url=resp['message'])
        em.set_footer(text="Powered by nekobot.xyz")
        await ctx.send(embed=em)

    @commands.command()
    async def trump(self, ctx, *, text):
        """Tweet as Trump."""
        params = {
            "type": "trumptweet",
            "text": text
        }
        resp = await self.bot.session.get("https://nekobot.xyz/api/imagegen", params=params)
        resp = await resp.json()
        if not resp['success']:
            return await ctx.send("An error occurred with the API.")
        em = discord.Embed(color=ctx.author.color, title="Trump Tweet")
        em.set_image(url=resp['message'])
        em.set_footer(text="Powered by nekobot.xyz")
        await ctx.send(embed=em)

    @commands.command()
    async def kanna(self, ctx, *, text):
        """Show a message as Kanna."""
        params = {
            "type": "kannagen",
            "text": text
        }
        resp = await self.bot.session.get("https://nekobot.xyz/api/imagegen", params=params)
        resp = await resp.json()
        if not resp['success']:
            return await ctx.send("An error occurred with the API.")
        em = discord.Embed(color=ctx.author.color, title="Kanna")
        em.set_image(url=resp['message'])
        em.set_footer(text="Powered by nekobot.xyz")
        await ctx.send(embed=em)


    @commands.command()
    async def captcha(self, ctx, user: discord.Member = None):
        """Turn yourself into a CAPTCHA challenge."""
        user = user or ctx.author
        params = {
            "type": "captcha",
            "url": user.avatar_url,
            "username": user.name
        }
        resp = await self.bot.session.get("https://nekobot.xyz/api/imagegen", params=params)
        resp = await resp.json()
        if not resp['success']:
            return await ctx.send("An error occurred with the API.")
        em = discord.Embed(color=ctx.author.color, title="CAPTCHA")
        em.set_image(url=resp['message'])
        em.set_footer(text="Powered by nekobot.xyz")
        await ctx.send(embed=em)



    @commands.command()
    async def clyde(self, ctx, *, text):
        """See a message in Clyde-style."""
        params = {
            "type": "clyde",
            "text": text
        }
        resp = await self.bot.session.get("https://nekobot.xyz/api/imagegen", params=params)
        resp = await resp.json()
        if not resp['success']:
            return await ctx.send("An error occurred with the API.")
        em = discord.Embed(color=ctx.author.color, title="Clyde Message")
        em.set_image(url=resp['message'])
        em.set_footer(text="Powered by nekobot.xyz")
        await ctx.send(embed=em)


    @commands.command(aliases=['triggered'])
    async def triggeredpic(self, ctx, user: discord.Member = None):
        """TRI GER RED!!!"""
        if user is None:
            user = ctx.author
        try:
            await ctx.trigger_typing()
            av = self.format_avatar(user.avatar_url)
            await ctx.send(f"Grrrr...**{user.name}** is triggered.", file=discord.File(await self.client.triggered(av), "triggered.gif"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def batslap(self, ctx, user: discord.Member = None):
        """User 1 will be slapping, user 2 will BE SLAPPED! Tehehe!"""
        if user is None:
            await ctx.send("Gotta tag someone that you wanna slap!")
        else:
            await ctx.trigger_typing()
            try:

                av = self.format_avatar(user.avatar_url)
                avatar = self.format_avatar(ctx.author.avatar_url)
                await ctx.send(f"Ouch! **{ctx.author.name}** slapped **{user.name}!**", file=discord.File(await self.client.batslap(avatar, av), "batslap.png"))
            except Exception as e:
                await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def missing(self, ctx, user: discord.Member = None):
        """Uh-oh...someone went missing!"""
        await ctx.trigger_typing()
        user = ctx.author if user is None else user
        try:
            await ctx.send(f"**{user.name}** went missing!", file=discord.File(await self.client.missing(user.avatar_url, user.name), "missing.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def wanted(self, ctx, user: discord.Member = None):
        """Someone is WANTED!"""
        await ctx.trigger_typing()
        user = ctx.author if user is None else user
        try:
            await ctx.send(f"**{user.name}** is wanted!", file=discord.File(await self.client.wanted(user.avatar_url), "wanted.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def achievement(self, ctx, *, text=None):
        """Give yourself an achievement. You need one."""
        await ctx.trigger_typing()
        text = text or "Not putting text when using this command."
        try:
            await ctx.send(f"**{ctx.author.name}** got an achievement!", file=discord.File(await self.client.achievement(ctx.author.avatar_url, text), "achievement.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def facepalm(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** had to facepalm.", file=discord.File(await self.client.facepalm(user.avatar_url), "facepalm.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def beautiful(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is beautiful!", file=discord.File(await self.client.beautiful(user.avatar_url), "beautiful.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def stepped(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** got stepped on.", file=discord.File(await self.client.stepped(user.avatar_url), "stepped.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def fear(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is SCARY!", file=discord.File(await self.client.heavyfear(user.avatar_url), "fear.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def blame(self, ctx, *, text):
        await ctx.trigger_typing()
        try:
            await ctx.send(file=discord.File(await self.client.blame(str(text)), "blame.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def thumbsup(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** gives a thumbs-up.", file=discord.File(await self.client.vault(user.avatar_url), "thumbsup.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def challenger(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is a challenger!", file=discord.File(await self.client.challenger(user.avatar_url), "challenger.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def superpunch(self, ctx, user: discord.Member):
        await ctx.trigger_typing()
        try:
            await ctx.send(f"OUCH. **{ctx.author.name}** punched **{user.name}**!", file=discord.File(await self.client.superpunch(ctx.author.avatar_url, user.avatar_url), "superpunch.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def card(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is on a Steam card!", file=discord.File(await self.client.steam(user.avatar_url, user.name), "steam.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def painting(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is on a painting!", file=discord.File(await self.client.bobross(user.avatar_url), "painting.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")
    
    @commands.command()
    async def waifuinsult(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** got insulted.", file=discord.File(await self.client.waifu_insult(user.avatar_url), "waifuinsult.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def scary(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** scared off a poor kid.", file=discord.File(await self.client.wreckit(user.avatar_url), "scary.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def approved(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is now approved.", file=discord.File(await self.client.approved(user.avatar_url), "approved.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def rejected(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** got rejected.", file=discord.File(await self.client.rejected(user.avatar_url), "rejected.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def gay(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is GAY.", file=discord.File(await self.client.rainbow(user.avatar_url), "gay.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def greyscale(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is in greyscale.", file=discord.File(await self.client.greyscale(user.avatar_url), "greyscale.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def invert(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** has inverted color!", file=discord.File(await self.client.invert(user.avatar_url), "invert.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def crush(self, ctx, user: discord.Member):
        await ctx.trigger_typing()
        try:
            await ctx.send(f"**{ctx.author.name}** has a crush on **{user.name}**!", file=discord.File(await self.client.crush(user.avatar_url, ctx.author.avatar_url), "crush.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def snapchat(self, ctx, *, text):
        await ctx.trigger_typing()
        try:
            await ctx.send(f"**{ctx.author.name}** sent a Snapchat!", file=discord.File(await self.client.snapchat(text), "snapchat.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def respect(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is being respected!", file=discord.File(await self.client.respect(user.avatar_url), "respe.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def cursive(self, ctx, *, text):
        """Turn your text into cursive!"""
        try:
            await ctx.message.delete()
        except:
            pass
        try:
            await ctx.send(await self.client.cursive(text, 'bold'))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")


    @commands.command()
    async def spank(self, ctx, user: discord.Member):
        """Spank someone. Spank someone hARD!"""
        await ctx.trigger_typing()
        try:
            await ctx.send(f"Ouch! **{ctx.author.name}** spanked **{user.name}** hard on the ass.", file=discord.File(await self.client.super_spank(ctx.author.avatar_url, user.avatar_url), "spank.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def garbage(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is garbage.", file=discord.File(await self.client.garbage(user.avatar_url), "garbage.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def confused(self, ctx, user: discord.Member = None):
        await ctx.trigger_typing()
        user = user if user is not None else ctx.author
        try:
            await ctx.send(f"**{user.name}** is confused?!", file=discord.File(await self.client.confused(user.avatar_url, self.bot.get_user(277981712989028353).avatar_url), "confused.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    
    @commands.command()
    async def mock(self, ctx, *, text):
        """Send someone in a MoCKinG voIcE."""
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send(await self.client.mock(text))


    @commands.command()
    async def tiny(self, ctx, *, text):
        """Send your text in ᵗᶦⁿʸ ˡᵉᵗᵗᵉʳˢ."""
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send(await self.client.tiny(text, 'superscript'))

    @commands.command()
    async def tindermatch(self, ctx, user: discord.Member):
        """Match yourself with someone like Tinder!"""
        await ctx.trigger_typing()
        try:
            await ctx.send(f"**{ctx.author.name}** got matched with **{user.name}**.", file=discord.File(await self.client.tinder_match(ctx.author.avatar_url, user.avatar_url), "tindermatch.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def ignore(self, ctx, user: discord.Member=None):
        await ctx.trigger_typing()
        user = user or ctx.author
        try:
            await ctx.send(f"**{user.name}** just ignored a burning house...", file=discord.File(await self.client.ignore(user.avatar_url), "ignore.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def time(self, ctx, user: discord.Member=None):
        await ctx.trigger_typing()
        user = user or ctx.author
        try:
            await ctx.send(f"Apparently, **{user.name}** is the time.", file=discord.File(await self.client.time(user.avatar_url), "time.png"))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

    @commands.command()
    async def owoify(self, ctx, *, text: str):
        await ctx.trigger_typing()
        try:
            await ctx.send(await self.client.owoify(text))
        except Exception as e:
            await ctx.send(f"An error occured with IdioticAPI. \nMore details: \n{e}")

def setup(bot):
    bot.add_cog(Idiotic(bot))
