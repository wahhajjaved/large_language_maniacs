# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import requests
import json, re, time, copy
from collections import deque
from threading import Timer
from ws4py.client.threadedclient import WebSocketClient
from sys import platform as sys_platform
from . import endpoints
from .errors import InvalidEventName, InvalidDestination, GatewayNotFound
from .user import User
from .channel import Channel, PrivateChannel
from .server import Server, Member, Permissions, Role
from .message import Message

def _null_event(*args, **kwargs):
    pass

def _keep_alive_handler(seconds, ws):
    def wrapper():
        _keep_alive_handler(seconds, ws)
        payload = {
            'op': 1,
            'd': int(time.time())
        }

        ws.send(json.dumps(payload))

    t =  Timer(seconds, wrapper)
    t.start()
    return t

class Client(object):
    """Represents a client connection that connects to Discord.
    This class is used to interact with the Discord WebSocket and API.

    A number of options can be passed to the :class:`Client` via keyword arguments.

    :param int max_length: The maximum number of messages to store in :attr:`messages`. Defaults to 5000.

    Instance attributes:

     .. attribute:: user

         A :class:`User` that represents the connected client. None if not logged in.
     .. attribute:: servers

         A list of :class:`Server` that the connected client has available.
     .. attribute:: private_channels

         A list of :class:`PrivateChannel` that the connected client is participating on.
     .. attribute:: messages

        A deque_ of :class:`Message` that the client has received from all servers and private messages.

    .. _deque: https://docs.python.org/3.4/library/collections.html#collections.deque
    """

    def __init__(self, **kwargs):
        self._is_logged_in = False
        self.user = None
        self.servers = []
        self.private_channels = []
        self.token = ''
        self.messages = deque([], maxlen=kwargs.get('max_length', 5000))
        self.events = {
            'on_ready': _null_event,
            'on_disconnect': _null_event,
            'on_error': _null_event,
            'on_response': _null_event,
            'on_message': _null_event,
            'on_message_delete': _null_event,
            'on_message_edit': _null_event,
            'on_status': _null_event,
            'on_channel_delete': _null_event,
            'on_channel_create': _null_event,
            'on_member_join': _null_event,
            'on_member_remove': _null_event,
        }

        gateway = requests.get(endpoints.GATEWAY)
        if gateway.status_code != 200:
            raise GatewayNotFound()
        gateway_js = gateway.json()
        url = gateway_js.get('url')
        if url is None:
            raise GatewayNotFound()

        self.ws = WebSocketClient(url, protocols=['http-only', 'chat'])

        # this is kind of hacky, but it's to avoid deadlocks.
        # i.e. python does not allow me to have the current thread running if it's self
        # it throws a 'cannot join current thread' RuntimeError
        # So instead of doing a basic inheritance scheme, we're overriding the member functions.

        self.ws.opened = self._opened
        self.ws.closed = self._closed
        self.ws.received_message = self._received_message

        # the actual headers for the request...
        # we only override 'authorization' since the rest could use the defaults.
        self.headers = {
            'authorization': self.token,
        }

    def _get_message(self, msg_id):
        return next((m for m in self.messages if m.id == msg_id), None)

    def _get_server(self, guild_id):
        return next((s for s in self.servers if s.id == guild_id), None)

    def _resolve_mentions(self, content, mentions):
        if isinstance(mentions, list):
            return [user.id for user in mentions]
        elif mentions == True:
            return re.findall(r'@<(\d+)>', content)
        else:
            return []

    def _invoke_event(self, event_name, *args, **kwargs):
        try:
            self.events[event_name](*args, **kwargs)
        except Exception as e:
            pass

    def _received_message(self, msg):
        response = json.loads(str(msg))
        if response.get('op') != 0:
            return

        self._invoke_event('on_response', response)
        event = response.get('t')
        data = response.get('d')

        if event == 'READY':
            self.user = User(**data['user'])
            guilds = data.get('guilds')

            for guild in guilds:
                guild['roles'] = [Role(**role) for role in guild['roles']]
                members = guild['members']
                for i, member in enumerate(members):
                    roles = member['roles']
                    for j, roleid in enumerate(roles):
                        role = next((r for r in guild['roles'] if r.id == roleid), None)
                        if role is not None:
                            roles[j] = role
                    members[i] = Member(**member)

                for presence in guild['presences']:
                    user_id = presence['user']['id']
                    member = next((m for m in members if m.id == user_id), None)
                    if member is not None:
                        member.status = presence['status']
                        member.game_id = presence['game_id']


                server = Server(**guild)

                # give all the members their proper server
                for member in server.members:
                    member.server = server

                for channel in guild['channels']:
                    changed_roles = []
                    permission_overwrites = channel['permission_overwrites']

                    for overridden in permission_overwrites:
                        # this is pretty inefficient due to the deep nested loops unfortunately
                        role = next((role for role in guild['roles'] if role.id == overridden['id']), None)
                        if role is None:
                            continue
                        denied = overridden.get('deny', 0)
                        allowed = overridden.get('allow', 0)
                        override = copy.deepcopy(role)

                        # Basically this is what's happening here.
                        # We have an original bit array, e.g. 1010
                        # Then we have another bit array that is 'denied', e.g. 1111
                        # And then we have the last one which is 'allowed', e.g. 0101
                        # We want original OP denied to end up resulting in whatever is in denied to be set to 0.
                        # So 1010 OP 1111 -> 0000
                        # Then we take this value and look at the allowed values. And whatever is allowed is set to 1.
                        # So 0000 OP2 0101 -> 0101
                        # The OP is (base ^ denied) & ~denied.
                        # The OP2 is base | allowed.
                        override.permissions.value = ((override.permissions.value ^ denied) & ~denied) | allowed
                        changed_roles.append(override)

                    channel['permission_overwrites'] = changed_roles
                channels = [Channel(server=server, **channel) for channel in guild['channels']]
                server.channels = channels
                self.servers.append(server)

            for pm in data.get('private_channels'):
                self.private_channels.append(PrivateChannel(id=pm['id'], user=User(**pm['recipient'])))

            # set the keep alive interval..
            interval = data.get('heartbeat_interval') / 1000.0
            self.keep_alive = _keep_alive_handler(interval, self.ws)

            # we're all ready
            self._invoke_event('on_ready')
        elif event == 'MESSAGE_CREATE':
            channel = self.get_channel(data.get('channel_id'))
            message = Message(channel=channel, **data)
            self.events['on_message'](message)
            self.messages.append(message)
        elif event == 'MESSAGE_DELETE':
            channel = self.get_channel(data.get('channel_id'))
            message_id = data.get('id')
            found = self._get_message(message_id)
            if found is not None:
                self.events['on_message_delete'](found)
                self.messages.remove(found)
        elif event == 'MESSAGE_UPDATE':
            older_message = self._get_message(data.get('id'))
            if older_message is not None:
                # create a copy of the new message
                message = copy.deepcopy(older_message)
                # update the new update
                for attr in data:
                    if attr == 'channel_id':
                        continue
                    value = data[attr]
                    if 'time' in attr:
                        setattr(message, attr, message._parse_time(value))
                    else:
                        setattr(message, attr, value)
                self._invoke_event('on_message_edit', older_message, message)
                # update the older message
                older_message = message

        elif event == 'PRESENCE_UPDATE':
            server = self._get_server(data.get('guild_id'))
            if server is not None:
                status = data.get('status')
                member_id = data['user']['id']
                member = next((u for u in server.members if u.id == member_id), None)
                if member is not None:
                    member.status = data.get('status')
                    member.game_id = data.get('game_id')
                    # call the event now
                    self._invoke_event('on_status', member)
        elif event == 'USER_UPDATE':
            self.user = User(**data)
        elif event == 'CHANNEL_DELETE':
            server =  self._get_server(data.get('guild_id'))
            if server is not None:
                channel_id = data.get('id')
                channel = next((c for c in server.channels if c.id == channel_id), None)
                server.channels.remove(channel)
                self._invoke_event('on_channel_delete', channel)
        elif event == 'CHANNEL_CREATE':
            is_private = data.get('is_private', False)
            channel = None
            if is_private:
                recipient = User(**data.get('recipient'))
                pm_id = data.get('id')
                channel = PrivateChannel(id=pm_id, user=recipient)
                self.private_channels.append(channel)
            else:
                server = self._get_server(data.get('guild_id'))
                if server is not None:
                    channel = Channel(server=server, **data)
                    server.channels.append(channel)

            self._invoke_event('on_channel_create', channel)
        elif event == 'GUILD_MEMBER_ADD':
            server = self._get_server(data.get('guild_id'))
            member = Member(deaf=False, mute=False, **data)
            server.members.append(member)
            self._invoke_event('on_member_join', member)
        elif event == 'GUILD_MEMBER_REMOVE':
            server = self._get_server(data.get('guild_id'))
            user_id = data['user']['id']
            member = next((m for m in server.members if m.id == user_id), None)
            server.members.remove(member)
            self._invoke_event('on_member_remove', member)

    def _opened(self):
        print('Opened at {}'.format(int(time.time())))

    def _closed(self, code, reason=None):
        print('Closed with {} ("{}") at {}'.format(code, reason, int(time.time())))
        self._invoke_event('on_disconnect')

    def run(self):
        """Runs the client and allows it to receive messages and events."""
        self.ws.run_forever()

    @property
    def is_logged_in(self):
        """Returns True if the client is successfully logged in. False otherwise."""
        return self._is_logged_in

    def get_channel(self, id):
        """Returns a :class:`Channel` or :class:`PrivateChannel` with the following ID. If not found, returns None."""
        if id is None:
            return None

        for server in self.servers:
            for channel in server.channels:
                if channel.id == id:
                    return channel

        for pm in self.private_channels:
            if pm.id == id:
                return pm

    def start_private_message(self, user):
        """Starts a private message with the user. This allows you to :meth:`send_message` to it.

        Note that this method should rarely be called as :meth:`send_message` does it automatically.

        :param user: A :class:`User` to start the private message with.
        """
        if not isinstance(user, User):
            raise TypeError('user argument must be a User')

        payload = {
            'recipient_id': user.id
        }

        r = requests.post('{}/{}/channels'.format(endpoints.USERS, self.user.id), json=payload, headers=self.headers)
        if r.status_code == 200:
            data = r.json()
            self.private_channels.append(PrivateChannel(id=data['id'], user=user))

    def send_message(self, destination, content, mentions=True):
        """Sends a message to the destination given with the content given.

        The destination could be a :class:`Channel` or a :class:`PrivateChannel`. For convenience
        it could also be a :class:`User`. If it's a :class:`User` or :class:`PrivateChannel` then it
        sends the message via private message, otherwise it sends the message to the channel.

        The content must be a type that can convert to a string through ``str(content)``.

        The mentions must be either an array of :class:`User` to mention or a boolean. If
        ``mentions`` is ``True`` then all the users mentioned in the content are mentioned, otherwise
        no one is mentioned. Note that to mention someone in the content, you should use :meth:`User.mention`.

        :param destination: The location to send the message.
        :param content: The content of the message to send.
        :param mentions: A list of :class:`User` to mention in the message or a boolean. Ignored for private messages.
        :return: The :class:`Message` sent or None if error occurred.
        """

        channel_id = ''
        is_private_message = True
        if isinstance(destination, Channel) or isinstance(destination, PrivateChannel):
            channel_id = destination.id
            is_private_message = destination.is_private
        elif isinstance(destination, User):
            found = next((pm for pm in self.private_channels if pm.user == destination), None)
            if found is None:
                # Couldn't find the user, so start a PM with them first.
                self.start_private_message(destination)
                channel_id = self.private_channels[-1].id
            else:
                channel_id = found.id
        else:
            raise InvalidDestination('Destination must be Channel, PrivateChannel, or User')

        content = str(content)
        mentions = self._resolve_mentions(content, mentions)

        url = '{base}/{id}/messages'.format(base=endpoints.CHANNELS, id=channel_id)
        payload = {
            'content': content,
        }

        if not is_private_message:
            payload['mentions'] = mentions

        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            channel = self.get_channel(data.get('channel_id'))
            message = Message(channel=channel, **data)
            return message

    def delete_message(self, message):
        """Deletes a :class:`Message`

        A fairly straightforward function.

        :param message: The :class:`Message` to delete.
        """
        url = '{}/{}/messages/{}'.format(endpoints.CHANNELS, message.channel.id, message.id)
        response = requests.delete(url, headers=self.headers)

    def edit_message(self, message, new_content, mentions=True):
        """Edits a :class:`Message` with the new message content.

        The new_content must be able to be transformed into a string via ``str(new_content)``.

        :param message: The :class:`Message` to edit.
        :param new_content: The new content to replace the message with.
        :param mentions: The mentions for the user. Same as :meth:`send_message`.
        :return: The new edited message or None if an error occurred."""
        channel = message.channel
        content = str(new_content)

        url = '{}/{}/messages/{}'.format(endpoints.CHANNELS, channel.id, message.id)
        payload = {
            'content': content
        }

        if not channel.is_private:
            payload['mentions'] = self._resolve_mentions(content, mentions)

        response = requests.patch(url, headers=self.headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            return Message(channel=channel, **data)

    def login(self, email, password):
        """Logs in the user with the following credentials and initialises
        the connection to Discord.

        After this function is called, :attr:`is_logged_in` returns True if no
        errors occur.

        :param str email: The email used to login.
        :param str password: The password used to login.
        """

        self.ws.connect()

        payload = {
            'email': email,
            'password': password
        }

        r = requests.post(endpoints.LOGIN, json=payload)

        if r.status_code == 200:
            body = r.json()
            self.token = body['token']
            self.headers['authorization'] = self.token
            second_payload = {
                'op': 2,
                'd': {
                    'token': self.token,
                    'properties': {
                        '$os': sys_platform,
                        '$browser': 'discord.py',
                        '$device': 'discord.py',
                        '$referrer': '',
                        '$referring_domain': ''
                    },
                    'v': 2
                }
            }

            self.ws.send(json.dumps(second_payload))
            self._is_logged_in = True

    def logout(self):
        """Logs out of Discord and closes all connections."""
        response = requests.post(endpoints.LOGOUT)
        self.ws.close()
        self._is_logged_in = False
        self.keep_alive.cancel()

    def logs_from(self, channel, limit=500):
        """A generator that obtains logs from a specified channel.

        Yielding from the generator returns a :class:`Message` object with the message data.

        Example: ::

            for message in client.logs_from(channel):
                if message.content.startswith('!hello'):
                    if message.author == client.user:
                        client.edit_message(message, 'goodbye')


        :param channel: The :class:`Channel` to obtain the logs from.
        :param limit: The number of messages to retrieve.
        """

        url = '{}/{}/messages'.format(endpoints.CHANNELS, channel.id)
        params = {
            'limit': limit
        }
        response = requests.get(url, params=params, headers=self.headers)
        if response.status_code == 200:
            messages = response.json()
            for message in messages:
                yield Message(channel=channel, **message)

    def event(self, function):
        """A decorator that registers an event to listen to.

        You can find more info about the events on the :ref:`documentation below <discord-api-events>`.

        Example: ::

            @client.event
            def on_ready():
                print('Ready!')
        """

        if function.__name__ not in self.events:
            raise InvalidEventName('The function name {} is not a valid event name'.format(function.__name__))

        self.events[function.__name__] = function
        return function

    def create_channel(self, server, name, type='text'):
        """Creates a channel in the specified server.

        In order to create the channel the client must have the proper permissions.

        :param server: The :class:`Server` to create the channel from.
        :param name: The name of the channel to create.
        :param type: The type of channel to create. Valid values are 'text' or 'voice'.
        :returns: The recently created :class:`Channel`.
        """
        url = '{}/{}/channels'.format(endpoints.SERVERS, server.id)
        payload = {
            'name': name,
            'type': type
        }
        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code == 200:
            channel = Channel(server=server, **response.json())
            return channel

    def delete_channel(self, channel):
        """Deletes a channel.

        In order to delete the channel, the client must have the proper permissions
        in the server the channel belongs to.

        :param channel: The :class:`Channel` to delete.
        """
        url = '{}/{}'.format(endpoints.CHANNELS, channel.id)
        response = requests.delete(url, headers=self.headers)

