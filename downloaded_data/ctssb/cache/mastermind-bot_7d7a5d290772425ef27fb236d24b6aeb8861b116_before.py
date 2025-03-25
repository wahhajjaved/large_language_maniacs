# mastermind-bot - A mastermind bot for slack
# © 2015 João Victor Duarte Martins <jvdm@sdf.org>
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import json
import re
import logging
import functools

import aiohttp
from aiohttp import MsgType, ws_connect
from aslack.slack_bot import SlackBot
from aslack.utils import truncate
import asyncio

from .version_info import __version__


log = logging.getLogger(__name__)


def get_api_url(api, **kwds):
    #return ('http://localhost:8000/api/{}/'
    return ('https://mastermind-macacoprego.herokuapp.com/api/{}/'
            .format(api.format(**kwds)))


class MastermindBot(SlackBot):

    VERSION = __version__

    loop = None

    # FIXME We need to overwrite this method because we want to access
    #       the socket later on.  We changed only the `self.socket`
    #       line and references to `logger`.

    async def join_rtm(self, filters=None):
        """Join the real-time messaging service."""
        if filters is None:
            filters = self.MESSAGE_FILTERS
        url = await self.get_socket_url()
        log.debug('Connecting to %r', url)
        async with ws_connect(url) as socket:
            # Export the socket to the class:
            self.socket = socket
            first_msg = await socket.receive()
            self._validate_first_message(first_msg)
            async for message in socket:
                if message.tp == MsgType.text:
                    result = await self.handle_message(message, filters)
                    if result is not None:
                        log.info(
                            'Sending message: %r',
                            truncate(result, max_len=50),
                        )
                        socket.send_str(result)
                elif message.tp in (MsgType.closed, MsgType.error):
                    if not socket.closed:
                        await socket.close()
                    break
        log.info('Left real-time messaging.')

    def send_message(self, channel, text, **kwds):
        kwds['channel'] = channel
        kwds['text'] = text
        payload = {'type': 'message', 'id': next(self._msg_ids)}
        payload.update(kwds)
        self.socket.send_str(json.dumps(payload))

    def _reply_to(self, msg, text):
        return {'channel': msg['channel'],
                'text': '<@{user}>: {text}'
                    .format(user=msg['user'], text=text)}

    def _filter_command(self, msg, command):
        return (self.message_is_to_me(msg) and
                msg['text'].lstrip(self.address_as).startswith(command))

    def _reply_callback(self, msg, fut):
        try:
            text = fut.result()
        except:
            text = ("sorry guys, couldn't create your game, something bad "
                    "happend: {}".format(fut.exception()))
            log.exception('request failed')
        self.send_message(**self._reply_to(msg, text))

    def filter_create_command(self, msg):
        return self._filter_command(msg, 'create')

    def filter_guess_command(self, msg):
        if not self._filter_command(msg, 'guess'):
            return False
        return re.search(r'#(\d+) (\w+)', msg['text'])
            
    def filter_hint_command(self, msg):
        return  self.message_is_to_me(msg) \
            and re.search(r' hint .*#\d+', msg['text'])

    async def dispatch_create_command(self, msg):
        players = re.findall(r'<@\w+>', msg['text'].lstrip(self.address_as))
        # The creator is just another player.
        players.insert(0, '<@{}>'.format(msg['user']))
        asyncio.ensure_future(self.create_game(msg, players),
                              loop=self.loop) \
               .add_done_callback(functools.partial(self._reply_callback, msg))
        return self._reply_to(msg,
                              'sure, give me a second to create '
                              'a game for you...')

    async def dispatch_guess_command(self, msg):
        match = re.search(r'#(\d+) (\w+)', msg['text'])
        game_id, code = match.groups()
        with aiohttp.ClientSession() as session:
            async with session.post(get_api_url('games/{id}/guess',
                                                id=game_id),
                                    data={'name': '<@{}>'.format(msg['user']),
                                          'code': code}) \
                    as resp:
                data = await resp.json()
                print(data)
                if resp.status != 201:
                    return self._reply_to(msg, 'bad guess')
                return self._reply_to(
                    msg,
                    '{} exacts, {} nears (total guess: {})'
                    .format(data['exact'], data['near'], data['num_guesses']))

    async def dispatch_hint_command(self, msg):
        match = re.search(r'#(\d+)', msg['text'])
        game_id = match.groups()[0]
        with aiohttp.ClientSession() as session:
            async with session.post(get_api_url('games/{id}/hint',
                                                id=game_id),
                                    data={'name': '<@{}>'.format(msg['user'])}) \
                    as resp:
                data = await resp.json()
                print(data)
                if resp.status != 200:
                    return self._reply_to(msg, 'sorry, I could not find a hint!')
                return self._reply_to(
                    msg,
                    "'{}' at position {}".format(data['position'], data['color']))
    
    async def create_game(self, msg, players):
        log.info('creating game for %s', players)
        with aiohttp.ClientSession() as session:
            async with session.post(get_api_url('games'),
                                    data={'players_count': len(players)}) \
                    as resp:
                text = await resp.text()
                if resp.status != 201:
                    raise Exception(text)
                game_info = await resp.json()
            # Join every player listed in the create command.
            for player in players:
                async with session.post(get_api_url('games/{id}/join',
                                               id=game_info['id']),
                                        data={'name': player}) \
                        as resp:
                    text = await resp.text()
                    if resp.status != 201:
                        raise Exception(text)
                    log.info('player %s has joined game %s: %s',
                             player, game_info['id'], text)
            return ("the game #{id} has been created, there are "
                    "{players_count} players ({names}), you all may "
                    "send guesses by sending messages like "
                    "'guess #{id} <your guess>'."
                    .format(names=', '.join(players), **game_info))

    MESSAGE_FILTERS = {
        filter_create_command: dispatch_create_command,
        filter_guess_command: dispatch_guess_command,
        filter_hint_command: dispatch_hint_command}


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='A mastermind bot for slack.')
    parser.add_argument(
        '--token',
        help='slack bot token')
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        datefmt='%H:%M:%S',
        format='%(asctime)s %(name)s [%(levelname)s] %(message)s',
        level=logging.INFO)
    token = args.token
    if not token:
        token = os.environ.get('MACACOPREGO_MASTERMIND_BOT_TOKEN')
    loop = asyncio.get_event_loop()
    bot = loop.run_until_complete(MastermindBot.from_api_token(token))
    # FIXME Usually we would pass this to __init__, but this aslack
    #       lib is very poorly designed.
    bot.loop = loop
    loop.run_until_complete(bot.join_rtm())
