#coding: utf-8

import werobot

from config import TOKEN

import msg
import pattern

robot = werobot.WeRoBot(token=TOKEN)


@robot.subscribe
def subscribe(message):
    return msg.subscribe()


@robot.text
def dispatch(message):
    content = message.content.strip()
    if not isinstance(content, unicode):
        content = content.decode('utf-8')

    if pattern.show_help(content):
        return msg.show_help()

    # turn on/off
    op, obj = pattern.op(content)
    if op and obj:
        return msg.op(op, obj)

    return msg.show_help()
