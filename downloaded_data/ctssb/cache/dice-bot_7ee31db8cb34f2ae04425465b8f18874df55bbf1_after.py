#!/usr/bin/env python3

import argparse
import asyncio
import logging
import random
import re
from collections import OrderedDict
from contextlib import closing

import discord
from discord.ext import commands
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

import equations
import model as m

description = '''D&D manager bot for discord based RPGs

Note:
Any parameters that have spaces in them need to be wrapped in quotes "
'''
bot = commands.Bot(
    command_prefix='!',
    description=description,
    loop=asyncio.new_event_loop())


# ----#-   Classes


class BotError (Exception):
    pass


class NoCharacterError (BotError):
    pass


class ItemNotFoundError (BotError):
    pass


class Cog:
    def __init__(self, bot):
        self.bot = bot


# ----#-   Utilities


async def do_roll(ctx, session, character, expression, adv=0):
    '''
    Does the dice rolling after const replacement
    '''
    original_expression = expression
    output = []

    # Set up operations
    def roll_dice(a, b, *, silent=False):
        out = 0
        for _ in range(a):
            n = random.randint(1, b)
            out += n
        if not silent:
            output.append('{}d{}: {}'.format(a, b, out))
        return out

    def great_weapon_fighting(a, b, *, silent=False):
        out = 0
        for _ in range(a):
            n = roll_dice(1, b, silent=True)
            if n <= 2:
                n2 = random.randint(1, b)
                if not silent:
                    output.append('1d{0}: {1}, rerolling, 1d{0}: {2}'.format(
                        b, n, n2))
                n = n2
            elif not silent:
                output.append('1d{}: {}'.format(b, n))
            out += n
        return out

    def roll_advantage(a, b, *, silent=False):
        if a == 1 and b == 20:
            first = roll_dice(a, b, silent=True)
            second = roll_dice(a, b, silent=True)
            out = max(first, second)
            if not silent:
                output.append('{}d{}, picking larger of {} and {}: {}'.format(
                    a, b, first, second, out))
        else:
            out = roll_dice(a, b, silent=silent)
        return out

    def roll_disadvantage(a, b, *, silent=False):
        if a == 1 and b == 20:
            first = roll_dice(a, b, silent=True)
            second = roll_dice(a, b, silent=True)
            out = min(first, second)
            if not silent:
                output.append('{}d{}, picking smaller of {} and {}: {}'.format(
                    a, b, first, second, out))
        else:
            out = roll_dice(a, b, silent=silent)
        return out

    operations = equations.operations.copy()
    if adv == 0:
        operations['d'] = roll_dice
    elif adv > 0:
        operations['d'] = roll_advantage
    else:
        operations['d'] = roll_disadvantage
    operations['D'] = operations['d']
    operations['g'] = great_weapon_fighting
    operations['G'] = operations['g']
    operations['>'] = max
    operations['<'] = min
    order_of_operations = [['d', 'D', 'g', 'G']]
    order_of_operations.extend(equations.order_of_operations)
    order_of_operations.append(['>', '<'])

    if character:
        # replace only 1 roll
        rolls = session.query(m.Roll)\
            .filter_by(character=character)\
            .order_by(func.char_length(m.Roll.name).desc())
        for roll in rolls:
            if roll.name in expression:
                expression = expression.replace(
                    roll.name, '({})'.format(roll.expression), 1)
                break

        # replace constants
        consts = session.query(m.Constant)\
            .filter_by(character=character)\
            .order_by(func.char_length(m.Constant.name).desc())
        for const in consts:
            expression = expression.replace(
                const.name, '({})'.format(const.value))

    # validate
    for token in re.findall(r'[a-zA-Z]+', expression):
        if token not in operations:
            search = r'[a-zA-Z]*' + re.escape(token) + r'[a-zA-Z]*'
            search = re.findall(search, original_expression)
            if search:
                token = search[0]
            raise equations.EquationError('Could not find `{}`'.format(token))

    # do roll
    output.append('Rolling: {}'.format(expression))
    roll = equations.solve(expression, operations, order_of_operations)
    output.append('I rolled {}'.format(roll))

    await ctx.send('\n'.join(output))

    return roll


def get_character(session, userid, server):
    '''
    Gets a character based on their user
    '''
    try:
        character = session.query(m.Character)\
            .filter_by(user=userid, server=server).one()
    except NoResultFound:
        raise NoCharacterError()
    return character


def sql_update(session, type, keys, values):
    '''
    Updates a sql object
    '''
    try:
        obj = session.query(type)\
            .filter_by(**keys).one()
        for value in values:
            setattr(obj, value, values[value])
    except NoResultFound:
        values = values.copy()
        values.update(keys)
        obj = type(**values)
        session.add(obj)

    session.commit()

    return obj


# ----#-   Converters


def int_or_max(value: str):
    if value == 'max':
        return value
    else:
        try:
            return int(value)
        except ValueError:
            raise commands.BadArgument(value)


# ----#-   Commands


class CharacterCog (Cog):
    @commands.command()
    async def iam(self, ctx, *, name: str):
        '''
        Associates user with a character
        It is highly encouraged to change your nickname to match the character
        A user can only be associated with 1 character at a time

        Parameters:
        [name] is he name of the character to associate
            to remove character association use !iam done
        '''
        server = ctx.guild.id
        if name.lower() == 'done':
            # remove character association
            with closing(self.bot.Session()) as session:
                try:
                    character = session.query(m.Character)\
                        .filter_by(user=ctx.author.id, server=server).one()
                    character.user = None
                    await ctx.send('{} is no longer playing as {}'.format(
                        ctx.author.mention, str(character)))
                except NoResultFound:
                    await ctx.send(
                        '{} does not have a character to remove'.format(
                            ctx.author.mention))

                session.commit()
        else:
            # associate character
            with closing(self.bot.Session()) as session:
                try:
                    character = session.query(m.Character)\
                        .filter_by(name=name, server=server).one()
                except NoResultFound:
                    character = m.Character(name=name, server=server)
                    session.add(character)
                    await ctx.send('Creating character: {}'.format(name))

                if character.user is None:
                    character.user = ctx.author.id
                    try:
                        session.commit()
                        await ctx.send('{} is {}'.format(
                            ctx.author.mention, str(character)))
                    except IntegrityError:
                        await ctx.send(
                            'You are already using a different character')
                else:
                    await ctx.send('Someone else is using {}'.format(
                        str(character)))

    @commands.command()
    async def whois(self, ctx, *, member: discord.Member):
        '''
        Retrieves character information for a user

        Parameters:
        [user] should be a user on this channel
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, member.id, ctx.guild.id)
            await ctx.send('{} is {}'.format(member.mention, str(character)))

    @commands.command()
    async def changename(self, ctx, *, name: str):
        '''
        Changes the character's name

        Parameters:
        [name] the new name
        '''
        with closing(self.bot.Session()) as session:
            try:
                character = get_character(session, ctx.author.id, ctx.guild.id)
                original_name = character.name
                character.name = name
                session.commit()
                await ctx.send("{} has changed {}'s name to {}".format(
                    ctx.author.mention, original_name, name))
            except IntegrityError:
                await ctx.send('There is already a character with that name')

    @commands.command()
    async def rest(self, ctx, *, rest: str):
        '''
        Take a rest

        Parameters:
        [type] should be short|long
        '''
        if rest not in ['short', 'long']:
            raise commands.BadArgument('rest')
        # short or long rest
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            if character:
                for resource in character.resources:
                    if resource.recover == m.Rest.long and rest == 'long':
                        resource.current = resource.max
                    elif resource.recover == m.Rest.short:
                        resource.current = resource.max

                session.commit()

                await ctx.send(
                    '{} has taken a {} rest, resources recovered'.format(
                        str(character), rest))
            else:
                await ctx.send('User has no character')


class RollCog (Cog):
    @commands.group('roll', invoke_without_command=True)
    async def group(self, ctx, *expression: str):
        '''
        Rolls dice
        Note: consts can be used in rolls and are replaced by the const value

        Parameters:
        [expression] standard dice notation specifying what to roll
            the expression may include up to 1 saved roll
        [adv] (optional) if present should be adv|disadv to indicate that any
            1d20 should be rolled with advantage or disadvantage respectively

        For finer control over advantage/disadvantage the > operator
        picks the larger operand and the < operator picks the smaller

        *Everything past here may change*

        There is a special 'great weapon fighting' operator
        which rerolls a 1 or 2, i.e. "2g6+5"
        '''
        if not expression:
            raise commands.MissingRequiredArgument('expression')

        if expression[-1] == 'disadv':
            adv = -1
            expression = expression[:-1]
        elif expression[-1] == 'adv':
            adv = 1
            expression = expression[:-1]
        else:
            adv = 0

        expression = ' '.join(expression)

        with closing(self.bot.Session()) as session:
            try:
                character = session.query(m.Character)\
                    .filter_by(user=ctx.author.id, server=ctx.guild.id).one()
            except NoResultFound:
                character = None

            await do_roll(ctx, session, character, expression, adv)

    @group.command('add', aliases=['set', 'update'])
    async def add(self, ctx, name: str, expression: str):
        '''
        Adds/updates a new roll for a character

        Parameters:
        [name] name of roll to store
        [expression] dice equation
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            roll = sql_update(session, m.Roll, {
                'character': character,
                'name': name,
            }, {
                'expression': expression,
            })

            await ctx.send('{} now has {}'.format(str(character), str(roll)))

    @group.command('check', aliases=['list'])
    async def check(self, ctx, *, name: str):
        '''
        Checks the status of a roll

        Parameters:
        [name] the name of the roll
            use the value "all" to list all rolls
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            if name != 'all':
                try:
                    roll = session.query(m.Roll)\
                        .filter_by(name=name, character=character).one()
                except NoResultFound:
                    raise ItemNotFoundError

                await ctx.send(str(roll))
            else:
                text = ["{}'s rolls:".format(str(character))]
                for roll in character.rolls:
                    text.append(str(roll))
                await ctx.send('\n'.join(text))

    @group.command('remove', aliases=['delete'])
    async def remove(self, ctx, *, name: str):
        '''
        Deletes a roll from the character

        Parameters:
        [name] the name of the roll
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            try:
                roll = session.query(m.Roll)\
                    .filter_by(name=name, character=character).one()
            except NoResultFound:
                raise ItemNotFoundError

            session.delete(roll)
            session.commit()
            await ctx.send('{} removed'.format(str(roll)))


class ResourceCog (Cog):
    @commands.group('resource', invoke_without_command=True)
    async def group(self, ctx):
        '''
        Manages character resources
        '''
        await ctx.send('Invalid subcommand')

    @group.command('add', aliases=['update'])
    async def add(self, ctx, name: str, max_uses: int, recover: str):
        '''
        Adds or changes a character resource

        Parameters:
        [name] the name of the new resource
        [max uses] the maximum number of uses of the resource
        [recover] the rest required to recover the resource,
            can be short|long|other
        '''
        if recover not in ['short', 'long', 'other']:
            raise commands.BadArgument('recover')

        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            resource = sql_update(session, m.Resource, {
                'character': character,
                'name': name,
            }, {
                'max': max_uses,
                'current': max_uses,
                'recover': recover,
            })

            await ctx.send('{} now has {}'.format(
                str(character), str(resource)))

    @group.command('use')
    async def use(self, ctx, number: int, *, name: str):
        '''
        Consumes 1 use of the resource

        Parameters:
        [number] the quantity of the resource to use
            can be negative to regain, but cannot go above max
        [name] the name of the resource
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            try:
                resource = session.query(m.Resource)\
                    .filter_by(name=name, character=character).one()
            except NoResultFound:
                raise ItemNotFoundError

            if resource.current - number >= 0:
                resource.current -= number
                if resource.current > resource.max:
                    resource.current = resource.max
                session.commit()
                await ctx.send('{} used {} {}, {}/{} remaining'.format(
                    str(character), number, resource.name,
                    resource.current, resource.max))
            else:
                await ctx.send('{} does not have enough to use: {}'.format(
                    str(character), str(resource)))

    @group.command('set')
    async def set(self, ctx, name: str, uses: int_or_max):
        '''
        Sets the remaining uses of a resource

        Parameters:
        [name] the name of the resource
        [uses] can be the number of remaining uses or
            the special value "max" to refill all uses
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            try:
                resource = session.query(m.Resource)\
                    .filter_by(name=name, character=character).one()
            except NoResultFound:
                raise ItemNotFoundError

            if uses == 'max':
                resource.current = resource.max
            else:
                resource.current = uses
            session.commit()

            await ctx.send('{} now has {}/{} uses of {}'.format(
                str(character), resource.current, resource.max, resource.name))

    @group.command('check', aliases=['list'])
    async def check(self, ctx, *, name: str):
        '''
        Checks the status of a resource

        Parameters:
        [name] the name of the resource
            use the value "all" to list resources
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            if name != 'all':
                try:
                    resource = session.query(m.Resource)\
                        .filter_by(name=name, character=character).one()
                except NoResultFound:
                    raise ItemNotFoundError

                await ctx.send(str(resource))
            else:
                text = ["{}'s resources:".format(character)]
                for resource in character.resources:
                    text.append(str(resource))
                await ctx.send('\n'.join(text))

    @group.command('remove', aliases=['delete'])
    async def remove(self, ctx, *, name: str):
        '''
        Deletes a resource from the character

        Parameters:
        [name] the name of the resource
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            try:
                resource = session.query(m.Resource)\
                    .filter_by(name=name, character=character).one()
            except NoResultFound:
                raise ItemNotFoundError

            session.delete(resource)
            session.commit()
            await ctx.send('{} removed'.format(str(resource)))


class ConstCog (Cog):
    @commands.group('const', invoke_without_command=True)
    async def group(self, ctx, *, expression: str):
        '''
        Manage character values
        '''
        await ctx.send('Invalid subcommand')

    @group.command('add', aliases=['set', 'update'])
    async def add(self, ctx, name: str, value: int):
        '''
        Adds/updates a new const for a character

        Parameters:
        [name] name of const to store
        [value] value to store
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            const = sql_update(session, m.Constant, {
                'character': character,
                'name': name,
            }, {
                'value': value,
            })

            await ctx.send('{} now has {}'.format(str(character), str(const)))

    @group.command('check', aliases=['list'])
    async def check(self, ctx, *, name: str):
        '''
        Checks the status of a const

        Parameters:
        [name] the name of the const
            use the value "all" to list all consts
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            if name != 'all':
                try:
                    const = session.query(m.Constant)\
                        .filter_by(name=name, character=character).one()
                except NoResultFound:
                    raise ItemNotFoundError

                await ctx.send(str(const))
            else:
                text = ["{}'s consts:\n".format(character)]
                for const in character.constants:
                    text.append(str(const))
                await ctx.send('\n'.join(text))

    @group.command('remove', aliases=['delete'])
    async def remove(self, ctx, *, name: str):
        '''
        Deletes a const from the character

        Parameters:
        [name] the name of the const
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            try:
                const = session.query(m.Constant)\
                    .filter_by(name=name, character=character).one()
            except NoResultFound:
                raise ItemNotFoundError

            session.delete(const)
            session.commit()
            await ctx.send('{} removed'.format(str(const)))


class InitiativeCog (Cog):
    @commands.group('initiative', invoke_without_command=True)
    async def group(self, ctx):
        '''
        Manage initiative by channel
        '''
        await ctx.send('Invalid subcommand')

    @group.command('add', aliases=['set', 'update'])
    async def add(self, ctx, *, value: int):
        '''
        Set initiative

        Parameters:
        [value] the initiative to store
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            initiative = sql_update(session, m.Initiative, {
                'character': character,
                'channel': ctx.message.channel.id,
            }, {
                'value': value,
            })

            await ctx.send('Initiative {} added'.format(str(initiative)))

    @group.command('roll')
    async def roll(self, ctx, *, expression: str):
        '''
        Roll initiative using the notation from the roll command

        Parameters:
        [expression] either the expression to roll or the name of a stored roll
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            value = await do_roll(ctx, session, character, expression)

            initiative = sql_update(session, m.Initiative, {
                'character': character,
                'channel': ctx.message.channel.id,
            }, {
                'value': value,
            })

            await ctx.send('Initiative {} added'.format(str(initiative)))

    @group.command('check', aliases=['list'])
    async def check(self, ctx):
        '''
        Lists all initiatives currently stored in this channel
        '''
        with closing(self.bot.Session()) as session:
            initiatives = session.query(m.Initiative)\
                .filter_by(channel=ctx.message.channel.id).all()
            text = ['Initiatives:']
            for initiative in initiatives:
                text.append(str(initiative))
            await ctx.send('\n'.join(text))

    @group.command('remove', aliases=['delete'])
    async def remove(self, ctx):
        '''
        Deletes a character's current initiative
        '''
        with closing(self.bot.Session()) as session:
            character = get_character(session, ctx.author.id, ctx.guild.id)

            try:
                channel = ctx.message.channel.id
                initiative = session.query(m.Initiative)\
                    .filter_by(character=character, channel=channel).one()
            except NoResultFound:
                raise ItemNotFoundError

            session.delete(initiative)
            session.commit()
            await ctx.send('Initiative removed')

    @group.command('endcombat', aliases=['removeall', 'deleteall'])
    @commands.has_role('DM')
    async def endcombat(self, ctx):
        '''
        Removes all initiative entries for the current channel
        '''
        with closing(self.bot.Session()) as session:
            session.query(m.Initiative)\
                .filter_by(channel=ctx.message.channel.id).delete(False)


for cog in [CharacterCog, RollCog, ResourceCog, ConstCog, InitiativeCog]:
    bot.add_cog(cog(bot))


# ----#-   Application


@bot.event
async def on_ready():
    '''
    Sets up the bot
    '''
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


@bot.event
async def on_command_error(ctx, error):
    if (isinstance(error, commands.CommandInvokeError)):
        error = error.original

    if isinstance(error, commands.BadArgument):
        await ctx.send(
            '{}\n'.format(error) +
            'See the help text for valid parameters')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            'Missing parameter: {}\n'.format(error.param) +
            'See the help text for valid parameters')
    elif isinstance(error, commands.TooManyArguments):
        await ctx.send(
            'Too many parameters\nSee the help text for valid parameters')
    elif isinstance(error, NoCharacterError):
        await ctx.send('User does not have a character')
    elif isinstance(error, ItemNotFoundError):
        await ctx.send('Could not find requested item')
    elif isinstance(error, equations.EquationError):
        if error.args:
            await ctx.send('Invalid dice expression: {}'.format(error.args[0]))
        else:
            await ctx.send('Invalid dice expression')
    elif isinstance(error, ValueError):
        if error.args:
            await ctx.send('Invalid parameter: {}'.format(error.args[0]))
        else:
            await ctx.send('Invalid parameter')
    else:
        await ctx.send('Error: {}'.format(error))
        raise error


def main(args):
    bot.config = OrderedDict([
        ('token', None),
    ])

    engine = create_engine(args.database)
    m.Base.metadata.create_all(engine)
    bot.Session = sessionmaker(bind=engine)
    with closing(bot.Session()) as session:
        for name in bot.config:
            try:
                key = session.query(m.Config).filter_by(name=name).one()
                bot.config[name] = key.value
            except NoResultFound:
                key = m.Config(name=name, value=bot.config[name])
                session.add(key)
                session.commit()

            if args.initialize:
                arg = input('[{}] (default: {}): '.format(
                    name, repr(key.value)))
                if arg:
                    key.value = arg
                    bot.config[name] = arg
                    session.commit()

    bot.run(bot.config['token'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Discord D&D bot')
    parser.add_argument(
        'database', nargs='?', default='sqlite:///:memory:',
        help='The database url to be accessed')
    parser.add_argument(
        '-i, --initialize', dest='initialize', action='store_true',
        help='Allows for initialization of config values')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    main(args)
