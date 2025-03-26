from discord.ext import commands


def is_owner():
    def p(ctx):
        return ctx.message.author.id == '196391063987027969'
    return commands.check(p)
