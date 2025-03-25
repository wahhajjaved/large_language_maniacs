#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Simple Bot to reply to Telegram messages
# This program is dedicated to the public domain under the CC0 license.
"""
This Bot uses the Updater class to handle the bot.

First, a few callback functions are defined. Then, those functions are passed to
the Dispatcher and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Example of a bot-user conversation using ConversationHandler.
Send /start to initiate the conversation.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging
import operator
import pickle
from classes.questions import initRoute

import os.path
from classes.group import Group
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

NAME = range(1)
ADMIN = range(1)
CODE, QUESTION = range(2)


def loadDict(fname):
    if os.path.isfile(fname):
        with open(fname, 'rb') as fp:
            data = pickle.load(fp)
        return data
    else:
        return dict()

groups = loadDict("groups.p")

def saveDict(fname, savedict):
    with open(fname, 'wb') as fp:
        pickle.dump(savedict, fp, protocol=pickle.HIGHEST_PROTOCOL)

def start(bot, update):
    update.message.reply_text(
        'Hi! Thank you for joining the FoxHunt!!!.\n'
        'What would you like to be your group name?')
    return NAME

def name(bot, update):
    user = update.message.from_user
    groupname = update.message.text
    for id,group in groups.items():
        if groupname == group.getName():
            update.message.reply_text("Name already taken")
            return NAME
    logger.info("New group: %s", groupname)
    update.message.reply_text("Welcome "+groupname)
    groups[update.message.chat_id] = Group(groupname)
    return ConversationHandler.END

def startadmin(bot, update):
    update.message.reply_text("What is the secret word?")
    return ADMIN

def admin(bot, update):
    password = update.message.text
    if password == "iliketrains":
        logger.info("New admin group: %s", groups[update.message.chat_id].getName())
        update.message.reply_text("You are now admin! ")
        groups[update.message.chat_id].setAdmin()
    else:
        logger.info("Wrong admin password: %s", update.message.chat_id)
        update.message.reply_text("Wrong admin password!")
    return ConversationHandler.END

def whoami(bot, update):
    name = groups[update.message.chat_id].getName()
    update.message.reply_text("Hi, "+name)

def cancel(bot, update):
    user = update.message.from_user
    logger.info("User %s canceled the register.", user.first_name)
    update.message.reply_text('Bye bye.',
                              reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END

def error(bot, update):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def startcode(bot, update):
    update.message.reply_text("What is the code you found?")
    return CODE

def code(bot, update):
    password = update.message.text
    group = groups[update.message.chat_id]
    if group.checkCode(password):
        question = group.getQuestion()
        reply_keyboard = [['A', 'B'], ['C', 'D']]
        update.message.reply_text("You found the right code!!\n"+question,
         reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
        return QUESTION
    else:
        update.message.reply_text("That is not the correct code")
        return CODE

def question(bot, update):
    answer = update.message.text
    group = groups[update.message.chat_id]
    chat_id = update.message.chat_id
    if group.checkAnswer(answer):
        checkpoint = group.getCheckpoint()
        if checkpoint == -1:
            update.message.reply_text("Well done. You have finished the foxhunt.\n Your score is: "+str(group.getScore()))
        else:
            update.message.reply_text("That is correct, you are now looking for point "+str(checkpoint), reply_markup=ReplyKeyboardRemove())
            bot.send_photo(chat_id=chat_id, photo=open('fotos/'+str(checkpoint)+'.jpeg', 'rb'))
        return ConversationHandler.END
    else:
        reply_keyboard = [['A', 'B'], ['C', 'D']]
        update.message.reply_text("That is incorrect, try again",
         reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
        return QUESTION

def startpaid(bot, update):
    group = groups[update.message.chat_id]
    if group.isAdmin():
        update.message.reply_text("Who has paid?")
        return 0
    else:
        update.message.reply_text("Fuck off")
        return ConversationHandler.END

def paid(bot, update):
    group = groups[update.message.chat_id]
    paidname = update.message.text
    if group.isAdmin():
        for id,groep in groups.items():
            if groep.getName() == paidname:
                update.message.reply_text(paidname+" have paid")
                groep.setPaid()
                return ConversationHandler.END
        update.message.reply_text("Could not find that name")
    else:
        update.message.reply_text("Fuck off")
    return ConversationHandler.END

def printGroups(bot, update):
    message = "Groups:\n"
    for id,group in groups.items():
        message = message + "ID: " + str(id) + group.getStats()
        message = message + str(group.order) + "\n"
    group = groups[update.message.chat_id]
    if group.isAdmin():
        update.message.reply_text(message)
    else:
        update.message.reply_text("Fuck off")

def printScore(bot, update):
    scores = dict()
    for id,group in groups.items():
        if group.hasPaid():
            scores[id] = group.getScore()
    scores = sorted(scores.items(), key=operator.itemgetter(1))
    message = "ScoreBoard:\n"
    pos = 1
    for groupid in scores:
        group = groups[groupid[0]]
        message = message + str(pos) +". "+  group.getName() + " : " + str(group.getScore()) + "\n"
        pos = pos + 1
    update.message.reply_text(message)

def beginHunt(bot, update):
    chat_id = update.message.chat_id
    group = groups[chat_id]
    if group.finished:
        update.message.reply_text("You have finished the foxhunt.")
    elif group.hasPaid():
        checkpoint = group.getCheckpoint()
        update.message.reply_text("Here is your clue for point "+str(checkpoint)+", let the hunt begin.")
        bot.send_photo(chat_id=chat_id, photo=open('fotos/'+str(checkpoint)+'.jpeg', 'rb'))
    else:
        update.message.reply_text("You have not paid, you cannot start the hunt.")

def Help(bot, update):
    update.message.reply_text("For help contact @VolundrFoxhuntSupport")

def startdiff(bot, update):
    group = groups[update.message.chat_id]
    if group.isAdmin():
        update.message.reply_text("What is the group name?")
        return 0
    else:
        update.message.reply_text("Fuck off")
        return conversationHandler.END

diffchange = 0
def diffgroup(bot, update):
    group = groups[update.message.chat_id]
    paidname = update.message.text
    if group.isAdmin():
        for id, groep in groups.items():
            if groep.getName() == paidname:
                reply_keyboard = [['easy'], ['hard']]
                update.message.reply_text("What diff for "+paidname+"?",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
                global diffchange
                diffchange = id
                return 1
        update.message.reply_text("Could not find that name")
    else:
        update.message.reply_text("Fuck off")
    return ConversationHandler.END

def diff(bot, update):
    logger.info("Changing diff for %d", diffchange)
    groups[diffchange].setDiff(update.message.text == "hard")
    update.message.reply_text("Updated difficulty")
    return ConversationHandler.END

def main():
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    f = open("token.txt","r")
    token = f.readline()
    f.close()
    token = token.strip()
    logger.info("token: %s",token)
    updater = Updater(str(token.strip()))

    initRoute()

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Add conversation handler with the states GENDER, PHOTO, LOCATION and BIO
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(Filters.text, name)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_admin = ConversationHandler(
        entry_points=[CommandHandler('admin', startadmin)],
        states={
            ADMIN: [MessageHandler(Filters.text, admin)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_paid = ConversationHandler(
        entry_points=[CommandHandler('paid', startpaid)],
        states={
            0: [MessageHandler(Filters.text, paid)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_question = ConversationHandler(
        entry_points=[CommandHandler('code', startcode)],
        states={
            CODE: [MessageHandler(Filters.text, code)],
            QUESTION: [RegexHandler('^(A|B|C|D)$', question)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    conv_diff = ConversationHandler(
        entry_points=[CommandHandler('diff', startdiff)],
        states={
            0: [MessageHandler(Filters.text, diffgroup)],
            1: [RegexHandler('^(easy|hard)$', diff)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(conv_admin)
    dp.add_handler(conv_question)
    dp.add_handler(conv_paid)
    dp.add_handler(conv_diff)
    dp.add_handler(CommandHandler("whoami", whoami))
    dp.add_handler(CommandHandler("groups", printGroups))
    dp.add_handler(CommandHandler("score", printScore))
    dp.add_handler(CommandHandler("begin", beginHunt))
    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
    print(groups)
    saveDict("groups.p", groups)

if __name__ == '__main__':
    main()
