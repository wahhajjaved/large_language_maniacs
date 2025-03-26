# ===============================================================
SCRIPT_NAME    = "weetext"
SCRIPT_AUTHOR  = "David R. Andersen <k0rx@RXcomm.net>"
SCRIPT_VERSION = "0.0.2"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESC    = "SMS Text Messaging plugin for Weechat using Google Voice"

"""
This script implements chatting via text message with Weechat.

Email and password should be configured (either by editing the script
itself or adding options to plugins.conf). For using secure passwords, 
see the weechat /secure command.

The script will block weechat briefly at startup when it is logging in to
Google Voice. Also, at this time sendText is threaded, but recText is
not.

To initiate a text message session with someone new, type the command:

text <10 digit phone number>

This will pop open a new buffer.

Todo:
1) Threaded recText()
2) Optional encrypted texts
"""

import weechat
import sys
import os
import re
import subprocess
import threading
from googlevoice import Voice
from googlevoice.util import input
from BeautifulSoup import BeautifulSoup, BeautifulStoneSoup, SoupStrainer

script_options = {
    "email" : "", # GV email address
    "passwd" : "", # GV password - can use /secure
    "poll_interval" : "2", # poll interval for receiving messages (sec)
}

conversation_map = {}
number_map = {}

class Conversation(object):
    def __init__(self, conv_id, number, messages):
        self.conv_id = conv_id
        self.number = number
        self.messages = messages

    def new_messages(self, other):
        assert len(self.messages) <= len(other.messages)
        return other.messages[len(self.messages):]

    def __iter__(self):
        return iter(reversed(self.messages))

class SMS:

    def sendText(self, msg, number, buf):
        global voice
        try:
            voice.send_sms(number, msg)
            weechat.prnt(buf, '<message sent>')
        except:
            weechat.prnt(buf, '<message NOT sent!>')

    def getsms(self):
        # We could call voice.sms() directly, but I found this does a rather
        # inefficient parse of things which pegs a CPU core and takes ~50 CPU
        # seconds, while this takes no time at all.
        global voice
        data = voice.sms.datafunc()
        data = re.search(r'<html><\!\[CDATA\[([^\]]*)', data, re.DOTALL).groups()[0]

        divs = SoupStrainer(['div', 'input'])
        tree = BeautifulSoup(data, parseOnlyThese=divs)

        convos = []
        conversations = tree.findAll("div", attrs={"id" : True},recursive=False)
        for conversation in conversations:
            inputs = SoupStrainer('input')
            tree_inp = BeautifulSoup(str(conversation),parseOnlyThese=inputs)
            phone = tree_inp.find('input', "gc-quickcall-ac")['value']

            smses = []
            msgs = conversation.findAll(attrs={"class" : "gc-message-sms-row"})
            for row in msgs:
                msgitem = {"id" : conversation["id"]}
                spans = row.findAll("span", attrs={"class" : True}, recursive=False)
                for span in spans:
                    cl = span["class"].replace('gc-message-sms-', '')
                    msgitem[cl] = (" ".join(span.findAll(text=True))).strip()
                if msgitem["text"]:
                    msgitem["text"] = BeautifulStoneSoup(msgitem["text"],
                                      convertEntities=BeautifulStoneSoup.HTML_ENTITIES
                                      ).contents[0]
                    msgitem['phone'] = phone
                    smses.append(msgitem)
            convos.append(Conversation(conversation['id'], phone, smses))
        return reversed(convos)

def textIn(*args):
    global conversation_map
    sms = SMS()
    conversations = sms.getsms()
    for conversation in conversations:
        if not conversation.conv_id in conversation_map:
            conversation_map[conversation.conv_id] = conversation
            msgs = conversation.messages
        else:
            old = conversation_map[conversation.conv_id]
            conversation_map[conversation.conv_id] = conversation
            msgs = old.new_messages(conversation)
        for msg in msgs:
            if not conversation.number in number_map and msg['from'] != 'Me:':
                number_map[conversation.number] = msg['from']
        for msg in msgs:
            if conversation.number in number_map:
                buf = weechat.buffer_search('python', number_map[conversation.number][:-1])
                if not buf:
                    buf = weechat.buffer_new(number_map[conversation.number][:-1],
                                             "textOut", "", "buffer_close_cb", "")
            else:
                buf = weechat.buffer_search('python', 'Me')
                if not buf:
                    buf = weechat.buffer_new('Me', "textOut", "", "buffer_close_cb", "")
            weechat.prnt(buf, msg['from'] + ' ' + msg['text'])
    return weechat.WEECHAT_RC_OK

def textOut(data, buf, input_data):
    global number_map
    number = None
    for num, dest in number_map.iteritems():
        if dest[:-1] == weechat.buffer_get_string(buf, 'name'):
            number = num
    if not number:
        number = weechat.buffer_get_string(buf, 'name')[2:]
    sms = SMS()
    thread = threading.Thread(target=sms.sendText, args=(input_data, number, buf))
    thread.start()
    return weechat.WEECHAT_RC_OK

def gvOut(data, buf, input_data):
    if input_data[:4] == 'text' and buf == weechat.buffer_search('python', 'gv'):
        buffer = weechat.buffer_new("+1"+input_data[5:], "textOut", "", "buffer_close_cb", "")
    return weechat.WEECHAT_RC_OK

def buffer_input_cb(data, buf, input_data):
    # ...
    return weechat.WEECHAT_RC_OK

def buffer_close_cb(data, buf):
    return weechat.WEECHAT_RC_OK

# register plugin
if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", "UTF-8"):
    buffer = weechat.buffer_new("weeText", "gvOut", "", "buffer_close_cb", "")
    for option, default_value in script_options.iteritems():
        if not weechat.config_is_set_plugin(option):
            weechat.config_set_plugin(option, default_value)

    # create voice instance
    weechat.prnt('', 'Logging in to Google Voice...')
    voice = Voice()
    passwd = weechat.config_get_plugin('passwd')
    if re.search('sec.*data', passwd):
        voice.login(email=weechat.config_get_plugin('email'),
                    passwd=weechat.string_eval_expression(passwd, {}, {}, {}))
    else:
        voice.login(email=weechat.config_get_plugin('email'), passwd=passwd)
    weechat.prnt('', 'Login successful')

    # register the hooks
    weechat.hook_timer(int(weechat.config_get_plugin("poll_interval")) * 60 * 1000, 0, 0, "textIn", "")
