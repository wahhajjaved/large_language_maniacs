#!/usr/bin/env python
# -*- coding: utf-8 -*-

import config # Get config

import random
import logging
import re
import urllib
import requests
import urlparse

# Needed for reading the memories file
import yaml

# Needed for loading the brain files
import aiml
import os.path

# Needed for logging into SQLite
import databasecommands
import time

# Initialize Alice
brain = aiml.Kernel()

log = logging.getLogger(__name__)

def get_user_affiliation(connection, nick):
    """Get a user's affiliation with the room"""
    useraffiliation = connection.plugin['xep_0045'].getJidProperty(connection.channel, nick, 'affiliation')
    return useraffiliation

def get_user_jid(connection, nick):
    """Get the JID from a user based on their nick"""
    userjid = connection.plugin['xep_0045'].getJidProperty(connection.channel, nick, 'jid')
    return userjid

def get_user_role(connection, nick):
    """Get a user's affiliation with the room"""
    userrole = connection.plugin['xep_0045'].getJidProperty(connection.channel, nick, 'role')
    return userrole

def kick_user(connection, nick, sender, room):
    """Kick a user from the room"""
    senderrole = get_user_role(connection, sender)
    receiverrole = get_user_role(connection, nick)
    if receiverrole is None:
        log.debug("Kick requested by %s failed because target %s is not in the room" %(sender, nick))
        connection.send_message(mto=room, mbody="I'm sorry, %s, I can't find %s in the room. :sweetiestare:" % (sender, nick))
        return
    if senderrole != 'moderator':
        log.debug("Kick requested by %s failed because they are not a moderator" % sender)
        connection.send_message(mto=room, mbody="I'm sorry, %s, I can't let you do that. :sweetiestare:" % sender, mtype="groupchat")
        return
    if receiverrole == 'moderator':
        log.debug("Kick requested by %s failed because target %s is a moderator" %(sender, nick))
        connection.send_message(mto=room, mbody="I'm sorry, %s, I can't let you do that. :sweetiestare:" % sender, mtype="groupchat")
        return
    userjid = get_user_jid(connection, nick)
    log.debug("Attempting to kick %s" % nick)
    try:
        kick = connection.plugin['xep_0045'].setRole(connection.channel, nick=nick, role="none")
        if kick:
            log.debug("Kicking of %s successful" % nick)
        else:
            log.debug("Kicking of %s failed" % nick)
            connection.send_message(mto=room, mbody="I could not kick %s, maybe do it yourself instead? :sweetiestare:" % nick, mtype="groupchat")
    except Exception as e:
        log.warning("Exception raised while kicking %s!" % nick)
        log.warning("Exception was: %s" % str(e))
        pass
    
def ban_user(connection, nick, sender, room):
    """Ban a user from the room"""
    senderrole = get_user_role(connection, sender)
    receiverrole = get_user_role(connection, nick)
    if  receiverrole is None:
        log.debug("Ban requested by %s failed because target %s is not in the room" %(sender, nick))
        connection.send_message(mto=room, mbody="I'm sorry, %s, I can't find %s in the room. :sweetiestare:" % (sender, nick))
        return
    if senderrole != 'moderator':
        log.debug("Ban requested by %s failed because they are not a moderator" % sender)
        connection.send_message(mto=room, mbody="I'm sorry, %s, I can't let you do that. :sweetiestare:" % sender, mtype="groupchat")
        return
    if receiverrole == 'moderator':
        log.debug("Ban requested by %s failed because target %s is a moderator" %(sender, nick))
        connection.send_message(mto=room, mbody="I'm sorry, %s, I can't let you do that. :sweetiestare:" % sender, mtype="groupchat")
        return
    userjid = get_user_jid(connection, nick)
    log.debug("Attempting to ban " + userjid.bare)
    try:
        ban = connection.plugin['xep_0045'].setAffiliation(connection.channel, jid=userjid.bare, affiliation="outcast")
        if ban:
            log.debug("Banning %s was successful. Writing to database." % userjid.bare)
            databasecommands.insert_in_ban_table(userjid.bare)
        else:
            log.debug("Banning %s failed" % nick)
            connection.send_message(mto=room, mbody="I could not ban %s. If you ban this person yourself, ask Minuette to put %s in my banlist." % (nick, userjid.bare), mtype="groupchat")
    except Exception as e:
        log.warning("Exception raised while banning %s!" % nick)
        log.warning("Exception was: %s" % str(e))
        pass
    
def argue():
    """Tumblr-argueing thanks to Nyctef and his TumblrAAS"""
    res = requests.get('http://tumblraas.azurewebsites.net/', timeout=5)
    return res.text.strip()

def rant():
    """Tumblr-rants thanks to Nyctef and his TumblrAAS"""
    res = requests.get('http://tumblraas.azurewebsites.net/rant', timeout=5)
    return res.text.strip()

def ceedee():
    """Confirm or deny"""
    return random.choice(['c', 'd'])

def brain_start():
    """Creates the brain file if needed and then loads it.
    Afterwards, the memories will be loaded so the bot gets her identity"""
    if os.path.isfile("standard.brn"):
	    # Brain is available, load it
        log.info("Found my brain, loading it now!")
        brain.bootstrap(brainFile = "standard.brn")
    else:
	    # No brain file, so we create one.
        log.info("Didn't find my brain, generating a new one!")
        brain.bootstrap(learnFiles = "aiml/std-startup.xml", commands = "load aiml b")
        brain.saveBrain("standard.brn")
    log.info("Brain loaded. Now setting all my memories!")
    memoryfile = file('personality.yaml', 'r')
    memories = yaml.load(memoryfile)
    for k, v in memories.items():
        brain.setBotPredicate(k, v)

def imgur_filter(link):
    """Convert Imgur image links into their full fledged counterparts"""
    imgurregex = re.compile(r'^http(s)?://i.imgur.com/([a-zA-Z0-9]*)\..*$')
    match = imgurregex.match(link)
    if (match):
        replacement = 'http://imgur.com/'+match.group(2)
        log.debug("replacing "+link+" with "+replacement)
        return replacement
    return link

def e621_filter(link):
    """Convert e621 image links into their full fledged counterparts"""
    e621regex = re.compile(r'http(s)?://static([0-9]*).e621.net/data(/sample)?.*?((?:[a-z0-9][a-z0-9]*[a-z0-9][a-z0-9]+[a-z0-9]*))')
    match = e621regex.match(link)
    if (match):
        replacement = 'https://e621.net/post/show?md5='+match.group(4)
        log.debug("replacing "+link+" with "+replacement)
        return replacement
    return link
    
def deviantart_filter(link):
    """Convert DeviantArt image links into their full fledged counterparts"""
    deviantartregex = re.compile(r'http(s)?://([a-z0-9]*).deviantart.(net|com)?/.*?((?:[a-z0-9][a-z0-9]*[a-z0-9][a-z0-9]+[a-z0-9_\\/]*)).*?((?:[a-z0-9][a-z0-9]*[a-z0-9][a-z0-9]+[a-z0-9]*))')
    match = deviantartregex.match(link)
    if (match):
        replacement = 'http://www.deviantart.com/#/' + match.group(5)
        log.debug("replacing "+link+" with "+replacement)
        return replacement
    return link

def goodtuch(nick):
    """Someone touches the bot in a nice way"""
    emotes = [":sweetie:",
              ":sweetiecreep:",
              ":sweetieglee:",
              ":sweetieidea:",
              ":sweetiepleased:",
              ":sweetieshake:"]
    actions = ["/me nuzzles %s",
               "/me snuggles %s",
               "/me cuddles %s",
               "/me hugs %s",
               "/me kisses %s",
               "/me licks %s"]
    return random.choice(actions) % nick + " " + random.choice(emotes)

def badtuch(nick):
    """Someone touches the bot in a bad way"""
    emotes = [":sweetiecrack:",
              ":sweetiedesk:",
              ":sweetiedust:",
              ":sweetielod:",
              ":sweetiemad:",
              ":sweetietwitch:"]
    actions = ["/me defenestrates %s",
               "/me hits %s with a spiked stick",
               "/me electrocutes %s",
               "/me throws %s into a bottomless pit",
               "/me teleports %s into space"]
    return random.choice(actions) % nick + " " + random.choice(emotes)

def sextuch(nick):
    """Someone touches the bot in a sexual way"""
    emotes = [":sweetiecrack:",
              ":sweetiedesk:",
              ":sweetiedust:",
              ":sweetielod:",
              ":sweetiemad:",
              ":sweetietwitch:"]
    actions = ["/me sticks a broken glass bottle into %s's ass",
               "/me inserts red hot metal pokers into %s's orifices",
               "/me electrocutes %s",
               "/me tosses %s's soap into a prison shower"]
    return random.choice(actions) % nick + " " + random.choice(emotes)

def tuch(nick, body):
    """Someone does something to me, decide what to do with them"""
    log.debug("Getting actions from database")
    niceActions = databasecommands.get_actions("nice")
    sexActions = databasecommands.get_actions("sex")
    
    if "pets" in body.lower():
        log.debug("%s is petting me!" % nick)
        return "/me purrs :sweetiepleased:"
    if [i for i in niceActions if i in body.lower()]:
        log.debug("%s is doing nice things to me!" % nick)
        return goodtuch(nick)
    if [i for i in sexActions if i in body.lower()]:
        log.debug("%s is doing sex things to me!" % nick)
        return sextuch(nick)
    else:
        log.debug("%s is doing bad things to me!" % nick)
        return badtuch(nick)
    
def alicemessage(nick, body):
    """Generate a response using Alice AI subroutines"""
    log.debug("I don't know what %s is saying, so I'll let Alice respond for me!" % nick)
    if body.startswith(config.nick + ": "):
        body = body.replace(config.nick + ": ", "", 1)
    
    body.replace(config.nick, "you")

    resp = brain.respond(body, nick)
    return resp
    
def handle_url(timestamp, sender, body):
    """Handle URL's and get titles from the pages"""
    urlregex = re.compile(
        r"((([A-Za-z]{3,9}:(?:\/\/)?)(?:[-;:&=\+\$,\w]+@)?[A-Za-z0-9.-]+|(?:www.|[-;:&=\+\$,\w]+@)[A-Za-z0-9.-]+)((?:\/[\+~%\/.\w_-]*)?\??(?:[-\+=&;%@.\w_]*)#?(?:[\w]*))?)")
    matches = urlregex.findall(body)
    matches = map(lambda x: x[0], matches)
    matches = map(imgur_filter, matches)
    matches = map(e621_filter, matches)
    # matches = map(deviantart_filter, matches)                      # Doesn't work properly and makes normal ones barf.
    if matches:
        log.debug("I think I see an URL! " + " / ".join(matches))
        results = []
        from bs4 import BeautifulSoup
        for match in matches:
            try:
                res = requests.get(match, timeout=5)
                
                domain = urlparse.urlparse(match).hostname.split(".")
                domain = ".".join(len(domain[-2]) < 4 and domain[-3:] or domain[-2:])
                
                if domain == "youtu.be":
                    domain = "youtube.com"
                if domain == "deviantart.net":
                    domain = "deviantart.com"
                
                if not 'html' in res.headers['content-type']:
                    log.debug("%s isn't HTML!" % match)
                    databasecommands.insert_in_link_table(timestamp, sender, match, match, domain)
                else:
                    soup = BeautifulSoup(res.text)
                    title = soup.title.string.strip()
                    databasecommands.insert_in_link_table(timestamp, sender, match, title, domain)
                    results.append(title)
            except Exception as e:
                log.debug("Error fetching url "+match+" : "+str(e))
                pass
        if not len(results):
            # no results
            return False
        result = " / ".join(results).strip()
        return result
        
def handler(connection, msg):
    """Handle incoming messages"""
    fullmessage = msg["mucnick"] + ": " + msg["body"]
    log.info(fullmessage)

    timestamp = int(time.time())
    sender = msg["mucnick"]
    
    try:
        affiliation = get_user_affiliation(connection, sender)
        role = get_user_role(connection, sender)
        userjid = get_user_jid(connection, sender)
        log.debug("Nick: %s JID: %s Affiliation: %s Role: %s" %(sender, userjid.bare, affiliation, role))
    except Exception as e:
        pass
    
    # Log messages in the database
    if userjid is not None:
        databasecommands.insert_in_messages_table(timestamp, msg["mucnick"], userjid.bare, msg["body"])

    # Write into the logfile
    #with open("cardboardbot.log", "a") as logfile:
    #    logfile.write(fullmessage + "\n")

    # Don't respond to the MOTD
    if not len(msg["mucnick"]):
        return
    
    # Don't respond to ourself
    if msg["mucnick"] == connection.nick:
        return

    # Administrative commands
    if "!kick" in msg["body"].lower():
        log.debug("Kick command detected")
        to_kick = msg["body"].split("!kick ")[-1]
        kick_user(connection, to_kick, msg["mucnick"], msg["from"].bare)
        return

    if "!identify" in msg["body"].lower():
        log.debug("Identify command detected")
        to_identify = msg["body"].split("!identify ")[-1]
        affiliation = get_user_affiliation(connection, to_identify)
        role = get_user_role(connection, to_identify)
        userjid = get_user_jid(connection, to_identify)
        connection.send_message(mto=msg["from"].bare,
                                mbody="%s was identified as %s, with role %s and affiliation %s" %(to_identify, userjid.bare, role, affiliation),
                                mtype="groupchat")
        return
        
    # Respond to mentions
    if connection.nick.lower() in msg["body"].lower():
        log.debug("Someone said my name!")
        
        if "deminu" in msg["body"].lower():
            log.debug("Deminu detected")
            roulette = random.randint(1, 10)
            if roulette == 10:
                log.debug("Rolled a 10! Kicking!")
                connection.send_message(mto=msg["from"].bare,
                                    mbody=badtuch(msg["mucnick"]),
                                    mtype="groupchat")
                kick_user(connection, msg["mucnick"], connection.nick, msg["from"].bare)
            else:
                log.debug("Didn't roll a 10, just doing a badtuch")
                connection.send_message(mto=msg["from"].bare,
                                    mbody=badtuch(msg["mucnick"]),
                                    mtype="groupchat")
            return
        
        # C/D mode
        if msg["body"].lower().endswith("c/d") or msg["body"].lower().endswith("c/d?"):
            log.debug("Confirm/deny detected")
            connection.send_message(mto=msg["from"].bare,
                                    mbody="%s: %s" %(msg["mucnick"], ceedee()),
                                    mtype="groupchat")
            return
        
        # Someone does things to me!
        if msg["body"].lower().startswith("/me"):
            log.debug("I am being touched by %s!" % msg["mucnick"])
            connection.send_message(mto=msg["from"].bare, mbody=tuch(msg["mucnick"], msg["body"]), mtype="groupchat")
            return
            
        
        # Tumblr argueing
        if "argue" in msg["body"].lower():
            log.debug("Someone wants me to argue!")
            connection.send_message(mto=msg["from"].bare, mbody=argue(), mtype="groupchat")
            return

        # Tumblr rant
        if "rant" in msg["body"].lower():
            log.debug("Someone wants me to rant!")
            connection.send_message(mto=msg["from"].bare, mbody=rant(), mtype="groupchat")
            return

        # Delegate response to Alice
        log.debug("I don't know what to say, delegating to Alice")
        connection.send_message(mto=msg["from"].bare, mbody=alicemessage(msg["mucnick"], msg["body"]), mtype="groupchat")
        return

    # Handle links in messages
    links = handle_url(timestamp, userjid.bare, msg["body"])
    if links:
        connection.send_message(mto=msg["from"].bare, mbody=links, mtype="groupchat")
        
    return