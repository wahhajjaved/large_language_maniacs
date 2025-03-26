import json
import logging
import re

logger = logging.getLogger(__name__)


class RtmEventHandler(object):
    def __init__(self, slack_clients, msg_writer):
        self.clients = slack_clients
        self.msg_writer = msg_writer

    def handle(self, event):

        if 'type' in event:
            self._handle_by_type(event['type'], event)

    def _handle_by_type(self, event_type, event):
        # See https://api.slack.com/rtm for a full list of events
        if event_type == 'error':
            # error
            self.msg_writer.write_error(event['channel'], json.dumps(event))
        elif event_type == 'message':
            # message was sent to channel
            self._handle_message(event)
        elif event_type == 'channel_joined':
            # you joined a channel
            self.msg_writer.write_help_message(event['channel'])
        elif event_type == 'group_joined':
            # you joined a private group
            self.msg_writer.write_help_message(event['channel'])
        else:
            pass

    def is_loud(self,message):
        emoji_pattern = re.compile(":.*:")
        tokens = message.split()

        if len(tokens) < 2: 
            return False
        for token in message.split():
            if not (token.isupper() or emoji_pattern.match(token)):
                return False
     
        return True

    def _handle_message(self, event):
        # Filter out messages from the bot itself
        if 'user' in event and not self.clients.is_message_from_me(event['user']):

            msg_txt = event['text']

            if self.is_loud(msg_txt):
                self.msg_writer.write_loud(event['channel'],msg_txt)
            
            if msg_txt.startswith('zac ') or msg_text.startswith('Zac ') or self.clients.is_bot_mention(msg_txt):
                # e.g. user typed: "@pybot tell me a joke!"
                if 'help' in msg_txt:
                    self.msg_writer.write_help_message(event['channel'])
                elif re.search('hi|hey|hello|howdy|Hi|Hello|sup', msg_txt):
                    self.msg_writer.write_greeting(event['channel'], event['user'])
                elif re.search('thanks|thank you|thank-you', msg_txt):
                    self.msg_writer.write_your_welcome(event['channel'], event['user'])
                elif 'joke' in msg_txt:
                    self.msg_writer.write_joke(event['channel'])
                elif 'attachment' in msg_txt:
                    self.msg_writer.demo_attachment(event['channel'])
                elif 'weather' in msg_txt:
                    self.msg_writer.write_weather(event['channel'])
                elif 'sad' in msg_txt:
                    self.msg_writer.write_sad(event['channel'])
                elif 'sort me' in msg_txt:
                    self.msg_writer.write_hogwarts_house(event['channel'], event['user'],  msg_txt)
                elif 'sass' in msg_txt:
                    self.msg_writer.write_sass(event['channel'], msg_txt)	
                elif ('945' in msg_txt) and ('?' in msg_txt):
                    self.msg_writer.announce_945(event['channel'])
                elif re.search('apologize|apologise', msg_txt):
                    self.msg_writer.write_apology(event['channel'])
                else:
                    pass