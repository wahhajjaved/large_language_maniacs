import sys
import traceback
import discord
from discord.ext import commands
import utils.data as data
import utils.roles
import asyncio

description = '''Bot'''

modules = {'cogs.roles_management', 'cogs.roles_config', 'cogs.cleaner', 'cogs.crytopto', 'cogs.greeter'}

bot = commands.Bot(command_prefix='!', description=description)


@bot.event
async def on_ready():
    print('Amnesio Bot starting...')

    print(bot.user.name)
    print(bot.user.id)
    data.server = bot.get_server('399637505512701952')
    everyone = data.server.members
    online_members = list(filter(lambda x: x.status.value == 'online' , everyone))
    online_members2 = list(filter(lambda y: y.status.value == 'idle' , everyone))
    online_members3 = list(filter(lambda z: z.status.value == 'dnd' , everyone))
    online_membersfin = [(lambda x, y, z: x+y+z)]
    await bot.change_presence(game=discord.Game(name='{} din {} Online'.format(online_membersfin.__len__(), members.__len__())))
    print('Loading cogs...')
    if __name__ == '__main__':
        modules_loaded = 0
        for module in modules:
            try:
                bot.load_extension(module)
                print('\t' + module)
                modules_loaded += 1
            except Exception as e:
                traceback.print_exc()
                print('Error loading the extension {module}', file=sys.stderr)
        print(str(modules_loaded) + '/' + str(modules.__len__()) + ' modules loaded')
        print('Systems 100%')
        print(data.server.name)
    print('------')


@bot.event
async def on_member_join(member: discord.Member):
    if member.id in data.joined:
        print('Bang!')
        await bot.send_message(member, 'LOL, you got banned :D :D!')
        await bot.ban(member)
        del data.joined[member.id]
    data.joined.append(member.id)

# Test bot
bot.run('NDA2MDU3OTgwNjg1OTc1NTUz.DUtapg.c9aAei-lco0085EnmoAh1rpqZx4')
