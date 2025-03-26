import sopel.module
import sopel.tools.time
import datetime
import random

@sopel.module.interval(5)
def welp_interval(bot):
    if bot.memory.contains('next_welpcall'):
        now = datetime.datetime.now()
        delta = now - bot.memory['next_welpcall']
        if abs(delta.total_seconds()) < 6:
            if "#testchannelpleaseignore" in bot.channels:
                # It's go time!
                _set_next_welpcall(bot)
                _run_welpcall(bot)
            
    else:
        _set_next_welpcall(bot)

def _set_next_welpcall(bot):
    # hard coded at 1 minute for debugging
    delta = datetime.timedelta(minutes=1)
    future = datetime.datetime.now() + delta
    bot.memory['next_welpcall'] = future

def _run_welpcall(bot):
    if bot.memory['welpcall_active']:
        _end_welpcall(bot)
    bot.msg('#testchannelpleaseignore', 'welpcall, you nerds') 
    bot.memory['welpcall_active'] = True
    bot.memory['welpcall_list'] = []
    
def _end_welpcall(bot):
    bot.memory['welpcall_active'] = False
    if len(bot.memory['welpcall_list']):
        winner = bot.memory['welpcall_list'][0]
    else:
        winner = None
    if '#testchannelpleaseignore' in bot.channels:
        bot.msg('#testchannelpleaseignore', 'welpcall complete.')
        bot.msg('#testchannelpleaseignore', 'Winner: ' + (winner or 'no one'))
        bot.msg('#testchannelpleaseignore', 'Losers: ' + 'everyone else') #TODO
    
@sopel.module.rule('welp')
def record_welp(bot, trigger):
    if bot.memory.contains('welpcall_active') and bot.memory['welpcall_active']:
        welp_list = bot.memory['welpcall_list']
        nick = trigger.nick
        if nick not in welp_list:
            welp_list.append(nick)
        
        if len(welp_list) >= 3:
            _end_welpcall(bot)
    #welp_count = bot.db.get_nick_value(nick, 'welp_count') or 0
    #welp_count = welp_count + 1
    #bot.db.set_nick_value(nick, 'welp_count', welp_count)
    #bot.say('TIME DEBUG: ' + sopel.tools.time.format_time(time=datetime.datetime.now()))
