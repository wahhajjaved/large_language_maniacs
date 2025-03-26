import json
import logging
import re
import os.path
from response_master import Response_master
from tictactoe_manager import TicTacToeManager
from user_manager import UserManager
from game_manager import GameManager
from rude_manager import RudeManager
from markov import Markov

logger = logging.getLogger(__name__)


class RtmEventHandler(object):

    bold_pattern = re.compile(
        "(((?<!.)| )\*(?=\S)(?!\*).+?(?<!\*)(?<=\S)\*( |(?!.)))"
    )

    def __init__(self, slack_clients, msg_writer, markov_chain):
        self.clients = slack_clients
        self.msg_writer = msg_writer
        self.game_manager = GameManager(self.msg_writer)
        self.user_manager = UserManager(self.clients, self.msg_writer)
        self.tictactoe_manager = TicTacToeManager(
            self.msg_writer, self.user_manager, self.game_manager
        )
        self.response_master = Response_master(self.msg_writer)
        self.user_manager = UserManager(self.clients, self.msg_writer)
        self.rude_manager = RudeManager(self.msg_writer)

        self.markov_chain = markov_chain

        self.lotrMarkov = Markov(2)
        self.lotrMarkov.add_file(open(
            os.path.join('./resources', 'hpOne.txt'), 'r')
        )
        self.lotrMarkov.add_file(open(
            os.path.join('./resources', 'random_comments.txt'), 'r')
        )
        self.lotrMarkov.add_file(open(
            os.path.join('./resources', 'lotrOne.txt'), 'r')
        )
        # self.lotrMarkov.add_file(open(os.path.join('./resources', 'lotrTwo.txt'), 'r'))
        # self.lotrMarkov.add_file(open(os.path.join('./resources', 'lotrThree.txt'), 'r'))
        # self.lotrMarkov.add_file(open(os.path.join('./resources', 'hobbit.txt'), 'r'))

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
        elif event_type == "reaction_added":
            response_master_response = self.response_master.get_emoji_response(event["reaction"])
            if response_master_response and "channel" in event["item"]:
                self.msg_writer.write_slow(event["item"]['channel'], response_master_response)
        else:
            pass

    def _is_edited_with_star(self, message):
        return "*" in re.sub(self.bold_pattern, '', message)

    def is_loud(self, message):
        emoji_pattern = re.compile(":.*:")
        tag_pattern = re.compile("<@.*")

        tokens = message.split()
        if len(tokens) < 2:
            return False
        for token in tokens:
            if not (token.isupper() or emoji_pattern.match(token)) or tag_pattern.match(token):
                return False

        return True

    def _is_edited_by_user(self, event):
        if 'subtype' in event:
            if event['subtype'] == 'message_changed':
                if "message" in event and "user" in event["message"] and "edited" in event["message"] and "user" in event["message"]["edited"] and ("subtype" not in event["message"] or event["message"]["subtype"] != "bot_message"):
                     return event["message"]["user"] == event["message"]["edited"]["user"]
        return False

    def _handle_message(self, event):
        if 'subtype' in event:
            if self._is_edited_by_user(event):
                self.msg_writer.write_spelling_mistake(event['channel'])
            elif event['subtype'] == 'channel_join':
                # someone joined a channel
                self.msg_writer.write_joined_channel(event['channel'], event['user'])
            elif event['subtype'] == 'message_deleted':
                self.msg_writer.write_message_deleted(event['channel'])
            elif event['subtype'] == 'channel_leave':
                self.msg_writer.write_left_channel(event['channel'])

        # Filter out messages from the bot itself
        if 'user' in event and not self.clients.is_message_from_me(event['user']):

            msg_txt = event['text']
            channel = event['channel']
            user = event['user']
            user_name = self.user_manager.get_user_by_id(user)
            lower_txt = msg_txt.lower()

            self.markov_chain.add_single_line(msg_txt)

            self.rude_manager.run(channel, user)

            response_master_response = self.response_master.get_response(msg_txt, user)

            if "printchannel" in lower_txt:
                self.msg_writer.write_channel_id(lower_txt.split()[1])

            if channel == 'C244LFHS7' or lower_txt == "markov":
                #markov
                self.msg_writer.send_message(channel, str(self.lotrMarkov))

            if lower_txt == "channelinfo":
                self.msg_writer.send_message(channel, channel)

            if lower_txt == "userinfo":
                self.msg_writer.send_message(channel, user)

            if lower_txt == "allusersinfo":
                self.user_manager.print_all_users(self.msg_writer)

            if response_master_response:
                self.msg_writer.write_slow(channel, response_master_response)

            if channel == 'C17QBAY2X':
                self.msg_writer.write_dont_talk(channel, user, event['ts'])

            if self.is_loud(msg_txt):
                self.msg_writer.write_loud(channel, msg_txt)

            if re.search('i choose you', msg_txt.lower()):
                self.msg_writer.write_cast_pokemon(channel, msg_txt.lower())

            if re.search('weather', msg_txt.lower()):
                self.msg_writer.write_weather(channel)

            if self._is_edited_with_star(msg_txt):
                self.msg_writer.write_spelling_mistake(channel)

            if re.search('riri', msg_txt.lower()):
                self.msg_writer.write_riri_me(channel, msg_txt)

            if 'xkcd' in lower_txt:
                requestedComic = lower_txt[lower_txt.find('xkcd') + 4:]
                self.msg_writer.write_xkcd(channel, requestedComic)

            if 'tictactoe' in lower_txt or 'ttt' in lower_txt:
                self.tictactoe_manager.get_message(channel, lower_txt, user_name)

            if re.search(' ?zac', msg_txt.lower()) or self.clients.is_bot_mention(msg_txt):
                if 'help' in msg_txt.lower():
                    self.msg_writer.write_help_message(channel)
                if re.search('night', msg_txt.lower()):
                    self.msg_writer.write_good_night(channel, user)
                if 'joke' in msg_txt.lower():
                    self.msg_writer.write_joke(channel)
                if 'french' in msg_txt.lower():
                    self.msg_writer.write_to_french(channel, msg_txt)
                if re.search('who\'?s that pokemon', msg_txt):
                    self.msg_writer.write_whos_that_pokemon(channel)
                if re.search(' ?zac it\'?s', msg_txt.lower()):
                    self.msg_writer.write_pokemon_guessed_response(channel, user, msg_txt)
                if 'attachment' in msg_txt:
                    self.msg_writer.demo_attachment(channel)
                if 'sad' in msg_txt.lower():
                    self.msg_writer.write_sad(channel)
                if 'kill me' in msg_txt.lower():
                    self.msg_writer.write_bang(channel, user)
                if re.search('(feed)|(hungry)', msg_txt.lower()):
                    self.msg_writer.write_food(channel)
                if re.search('encourage me', msg_txt.lower()):
                    self.msg_writer.write_encouragement(channel, user)
                if 'sort me' in msg_txt.lower():
                    self.msg_writer.write_hogwarts_house(channel, user,  msg_txt)
                if 'sass ' in msg_txt.lower():
                    self.msg_writer.write_sass(channel, msg_txt)
                if re.search('apologize|apologise', msg_txt.lower()):
                    self.msg_writer.write_apology(channel)
                if 'solve' in msg_txt.lower():
                    self.msg_writer.write_solution(channel, msg_txt)
                if re.search('explain|why', msg_txt.lower()):
                    self.msg_writer.write_explanation(channel)
                if re.search('sweetpotato me|sweet potato me', msg_txt.lower()):
                    self.msg_writer.write_sweetpotato_me(channel, user)
                if re.search('marry me', msg_txt.lower()):
                    self.msg_writer.write_marry_me(channel)
                if re.search('draw me', msg_txt.lower()):
                    self.msg_writer.write_draw_me(channel)
                if re.search('love|forever|relationship|commitment', msg_txt.lower()):
                    self.msg_writer.write_forever(channel)
                if re.search('unflip', msg_txt.lower()):
                    self.msg_writer.write_unflip(channel)
                elif re.search('flip|rageflip', msg_txt.lower()):
                    self.msg_writer.write_flip(channel)
                if re.search('sup son', msg_txt.lower()):
                    self.msg_writer.write_sup_son(channel)
                if msg_txt.lower().count("zac") >= 2:
                    self.msg_writer.write_prompt(channel)
                else:
                    pass
