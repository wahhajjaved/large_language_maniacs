#!/usr/bin/python3
import discord
import DiscordThrall
#import logging
from keyring import *  # @UnusedWildImport

client = discord.Client()
Bot = DiscordThrall.Bot()

# This doesn't work. Why?
# @client.event
# async def wait_until_ready():
#     logger = logging.getLogger('discord')
#     logger.setLevel(logging.WARNING)
#     handler = logging.FileHandler(filename='bot_technical.loggimm', encoding='utf-8', mode='w')
#     handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
#     logger.addHandler(handler)

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

#When someone joins the server
# @client.event
# async def on_member_join(member):
#     server = member.server
#     fmt = 'Welcome {0.mention} to {1.name}!'
#     await client.send_message(server, fmt.format(member, server))

@client.event
async def on_message(message):
    destination = None
    response = None
    if message.content.startswith('!test'):
        return
#         counter = 0
#         tmp = await client.send_message(message.channel, 'Calculating messages...')
#         async for log in client.logs_from(message.channel, limit=100):
#             if log.author == message.author:
#                 counter += 1
#  
#         await client.edit_message(tmp, 'You have {} messages.'.format(counter))
#     elif message.content.startswith('!sleep'):
#         await asyncio.sleep(5)
#         await client.send_message(message.channel, 'Done sleeping')

    elif message.content.startswith('!introduce yourself'):
        await client.send_message(message.channel, 'Hello, I am your humble servant.')
        
    # Rolling
    elif message.content.startswith('!r ') or message.content.startswith('!roll '):
        chan = message.channel
        response = Bot.dice(message)
        
    # Schrecknet
    elif message.content.startswith('!sch ') or message.content.startswith('!schrecknet '):
        destination, response = Bot.schrecknetpost(message)
        
    # Pruning
    elif message.content.startswith('!prune '):
        destination = message.channel.id
        if Bot.check_role_sufficiency(message.author, "Assistant Storyteller") == None:
            response = "Something is wrong with the Role Hierarchy."
        elif Bot.check_role_sufficiency(message.author, "Assistant Storyteller") == False:
            response = "Only staff can prune messages."
        else:
            try:
                try:
                    target = message.mentions[0]
                except:
                    try:
                        target = message.content.split(' ')[1]
                        if target != "offserver":
                            raise Exception("Neither name nor offserver")
                        target = None
                    except:
                        response = "I don't see a target mentioned."
                try:
                    parts = message.content.split(' ')
                    num_to_prune = int(parts[2])
                except:
                    response = "The amount to prune seems invalid"
                if response is None:
                    history = []
                    
                    async for msg in client.logs_from(message.channel, limit=500):
                        if msg.server.get_member(msg.author.id) == target:
                            history.append(msg)
                    sorted_history = sorted(history, key=lambda entry: entry.timestamp)
                    sorted_history.reverse()
                    
                    for msg in sorted_history[:num_to_prune]:
                        await client.delete_message(msg)
                    response = "Pruned successfully."
            except:
                response = "Some messages couldn't be deleted."
            
    # Figuring out who is an inactive member
    #elif message.content.startswith('!inactive '):
            
    # Role adding
    elif message.content.startswith('!promote '):
        destination = message.channel.id
        role, target = Bot.give_role(message)
        if target is not None:
            try:
                await client.add_roles(target,role)
                response = message.mentions[0].name + " has been granted the role of " + role.name + "!"
            except Exception as e:
                print(e)
                response = "I was unable to complete this promotion :'("
        else:
            response = role
            
    # Role removing
    elif message.content.startswith('!demote '):
        destination = message.channel.id
        role, target = Bot.give_role(message)
        if target is not None:
            try:
                await client.remove_roles(target,role)
                response = message.mentions[0].name + " is no longer a " + role.name + "!"
            except Exception as e:
                print(e)
                response = "I was unable to complete this demotion :'("
        else:
            response = role
    
    # Help requests
    elif message.content.startswith('!help '):
        destination = message.channel.id
        response = Bot.print_info(message)   
    
    # Blank help request 
    elif message.content.startswith('!help'):
        destination = message.channel.id
        response = Bot.print_info(message)
        
    # Character sheet creation
    elif message.content.startswith('!create '):
        destination = message.channel.id
        response, name = Bot.create_character(message)
        if name != None:
            charlist = await client.get_message(client.get_channel(DiscordThrall.Sheets_Channel), DiscordThrall.Character_List)
            await client.edit_message(charlist, charlist.content+"\n"+name+":"+message.author.mention)
        
    # Character sheet functionality
    elif message.content.startswith('!char ') or message.content.startswith('!c '):
        response,private = Bot.character_handling(message)
        splits = DiscordThrall.splitstr(response, 2000)
        if splits > 1:
            private = True
        if private:
            chan = message.author
            for msg in splits: # Discord message length limit
                await client.send_message(message.author, msg)
            return
        else:
            chan = message.channel
            
    # Same as above, but *always* send success response to both the requester and someone else
    elif message.content.startswith('!st '):
        response,st = Bot.character_handling_st(message)
        if st is not None:
            try:
                stuser = client.get_user_info(st)
                for msg in DiscordThrall.splitstr(response, 2000): # Discord message length limit
                    await client.send_message(message.author, msg)
                    await client.send_message(stuser, msg)
                return
            except:
                response = "The Storyteller specified was invalid (if you changed your sheet, it might still have been changed)"
                pass
        else:
            for msg in DiscordThrall.splitstr(response, 2000): # Discord message length limit
                await client.send_message(message.author, msg)
            return
    
    # Manual greeting
    elif message.content.startswith('!greet'):
        chan = message.author
        response = Bot.greet(message.author, client.get_channel(DiscordThrall.Announce_Channel))
    
    # Promoting to Newbie
#     elif message.content.startswith('I am ready to see the listings'):
#         chan = message.author
#         try:
#             sender = client.get_server(DiscordThrall.R20BNServer).get_member(message.author.id)
#             if Bot.check_role_sufficiency(sender, "Newbie") == True:
#                 response = "You can already see the listings."
#             else:
#                 sender = client.get_server(DiscordThrall.R20BNServer).get_member(message.author.id)
#                 role = Bot.find_role(client.get_server(DiscordThrall.R20BNServer), "Newbie")
#                 await client.add_roles(sender,role)
#                 await client.send_message(client.get_channel(DiscordThrall.Bot_Update_Channel), 
#                                           "New Newbie: " + sender.mention)
#                 response = Bot.accept_newbie(sender, client.get_channel(DiscordThrall.Gamelist_Channel))
#         except Exception as e:
#             print("Error resolving '" + str(message) + "': " + str(e))
#             response = "You are not a member of the appropriate server."
        
    # Promoting to Applicant
    elif message.content.startswith('I am ready to see the listings'):
        chan = message.author
        try:
            sender = client.get_server(DiscordThrall.R20BNServer).get_member(message.author.id)
            if Bot.check_role_sufficiency(sender, "Player") == True:
                response = "You are already in a game."
            else:
                role = Bot.find_role(client.get_server(DiscordThrall.R20BNServer), "Applicant")
                await client.add_roles(sender,role)
                await client.send_message(client.get_channel(DiscordThrall.Bot_Update_Channel), 
                                          "New Applicant: " + message.author.mention)
                response = Bot.accept_applicant(sender,
                                                client.get_channel(DiscordThrall.Application_Channel) ,
                                                client.get_channel(DiscordThrall.Gamelist_Channel) ,
                                                client.get_channel(DiscordThrall.Appquestion_Channel))
        except Exception as e:
            print("Error resolving '" + str(message) + "': " + str(e))
            response = "You are not a member of the appropriate server."
    
    else:
        return
    try:
        if isinstance(destination, str):
            chan = client.get_channel(destination)
    except Exception as e:
        print("The message failing was:" + message.content + "\nThe error is: " + str(e))
    await client.send_message(chan, response)
    
    
@client.event
async def on_member_join(member):
    if member.server != client.get_server(DiscordThrall.R20BNServer):
        return
    infochannel = client.get_channel(DiscordThrall.Bot_Update_Channel)
    await client.send_message(infochannel, member.mention + " joined the server!")
    content = Bot.greet(member, client.get_channel(DiscordThrall.Announce_Channel))
    await client.send_message(member, content)
    
@client.event
async def on_member_remove(member):
    if member.server != client.get_server(DiscordThrall.R20BNServer):
        return
    infochannel = client.get_channel(DiscordThrall.Bot_Update_Channel)
    await client.send_message(infochannel, member.name + " has left the server.")
        
@client.event
async def on_typing(channel,user,when):
    if not Bot.rss_ready():
        return
    logs = []
    # Everything here is a dirty, inefficient hack. Optimize it!
    for ch_id in DiscordThrall.rss_chan:
        chan = client.get_channel(ch_id)
        async for message in client.logs_from(chan, limit=50):
            logs.append(message)
    rssupdates = Bot.rss_update(logs)
    if rssupdates is not None:
        for update in rssupdates:
            for ch_id in DiscordThrall.rss_chan:
                chan = client.get_channel(ch_id)
                await client.send_message(chan,update)
    pruned = await client.prune_members(server = client.get_server(DiscordThrall.R20BNServer), days = 15)
    if pruned > 0:
        await client.send_message(client.get_channel(DiscordThrall.Bot_Update_Channel),
                                  "Pruning users... " + str(pruned) + " removed.") #TODO 
        
            
client.run(DiscordToken)









