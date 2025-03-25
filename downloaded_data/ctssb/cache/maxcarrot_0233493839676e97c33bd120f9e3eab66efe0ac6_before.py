import rabbitpy
import json


class RabbitWrapper(object):
    def __init__(self, url, username, password, bind):
        if url.startswith('amqp://'):
            self.url = url
        else:
            self.url = 'amqp://{}:{}@{}'.format(username, password, url)
        self.connection = rabbitpy.Connection(self.url)
        self.channel = self.connection.channel()

    def get_user_publish_exchange(self, username):
        # Exchange to sent messages to rabbit
        # routed by topic to destination
        return rabbitpy.Exchange(self.channel, '{}.publish'.format(username), exchange_type='direct', durable=True)

    def get_user_subscribe_exchange(self, username):
        # Exchange to broadcast messages for this user to all
        # the consumers identified with this username

        return rabbitpy.Exchange(self.channel, '{}.subscribe'.format(username), exchange_type='fanout', durable=True)
        # Version with alternate exchange enabled
        #return rabbitpy.Exchange(self.channel, '{}.subscribe'.format(username), exchange_type='fanout', durable=True, arguments={'alternate-exchange': 'unread'})

    def disconnect(self):
        self.connection.close()


class RabbitServer(RabbitWrapper):
    """
    """
    def __init__(self, url, username='guest', password='guest', bind=True):
        super(RabbitServer, self).__init__(url, username, password, bind)

        self.exchanges = {}
        self.queues = {}
        # Defne global conversations exchange
        self.exchanges['conversations'] = rabbitpy.Exchange(self.channel, 'conversations', durable=True, exchange_type='topic')
        self.exchanges['activity'] = rabbitpy.Exchange(self.channel, 'activity', durable=True, exchange_type='direct')
        self.exchanges['twitter'] = rabbitpy.Exchange(self.channel, 'twitter', durable=True, exchange_type='fanout')
        #self.exchanges['unread'] = rabbitpy.Exchange(self.channel, 'unread', durable=True, exchange_type='fanout')

        # Define persistent queue for writing messages to max
        self.queues['messages'] = rabbitpy.Queue(self.channel, 'messages', durable=True)
        self.queues['push'] = rabbitpy.Queue(self.channel, 'push', durable=True)
        self.queues['twitter'] = rabbitpy.Queue(self.channel, 'twitter', durable=True)
        self.queues['twitty_restart'] = rabbitpy.Queue(self.channel, 'tweety_restart', durable=True)
        #self.queues['unread'] = rabbitpy.Queue(self.channel, 'unread', durable=True)

        # Wrapper to interact with conversations
        self.conversations = RabbitConversations(self)
        self.activity = RabbitActivity(self)

        self.declare()

        # Define messages queue to conversations to receive messages from all conversations
        self.queues['messages'].bind(source=self.exchanges['conversations'], routing_key='*')
        self.queues['push'].bind(source=self.exchanges['conversations'], routing_key='*')
        self.queues['push'].bind(source=self.exchanges['activity'], routing_key='*')
        self.queues['twitter'].bind(source=self.exchanges['twitter'])
        #self.queues['unread'].bind(source=self.exchanges['unread'])

    def send(self, exchange, message, routing_key=''):
        str_message = message if isinstance(message, basestring) else json.dumps(message)
        message = rabbitpy.Message(self.channel, str_message)
        message.publish(self.exchanges[exchange], routing_key=routing_key)

    def create_user(self, username):
        user_publish_exchange = self.get_user_publish_exchange(username)
        user_publish_exchange.declare()

        user_subscribe_exchange = self.get_user_subscribe_exchange(username)
        user_subscribe_exchange.declare()

        user_subscribe_exchange.bind(user_publish_exchange, routing_key='internal')

    def create_users(self, usernames):
        for username in usernames:
            self.create_user(username)

    def delete_user(self, username):
        user_publish_exchange = self.get_user_publish_exchange(username)
        user_publish_exchange.delete()

        user_subscribe_exchange = self.get_user_subscribe_exchange(username)
        user_subscribe_exchange.delete()

    def get_all(self, queue_name, retry=False):
        messages = []
        message_obj = True
        tries = 1 if not retry else -1
        while not(tries == 0 or messages != []):
            while message_obj is not None:
                message_obj = self.get(queue_name)
                if message_obj is not None:
                    tries = 1
                    try:
                        message = (message_obj.json(), message_obj)
                    except ValueError:
                        message = (message_obj.body, message_obj)
                    messages.append(message)
            tries -= 1
            message_obj = True
        return messages

    def get(self, queue_name):
        return self.queues[queue_name].get()

    def declare(self):
        for exchange_name, exchange in self.exchanges.items():
            exchange.declare()
        for queue_name, queue in self.queues.items():
            queue.declare()


class RabbitConversations(object):
    """
        Wrapper around conversations, to send and receive messages as a user
    """

    def __init__(self, wrapper):
        self.client = wrapper
        self.exchange = rabbitpy.Exchange(self.client.channel, 'conversations', exchange_type='topic')

    def create(self, conversation, users):
        for user in users:
            self.bind_user(conversation, user)

    def bind_user(self, conversation, user):
        user_publish_exchange = self.client.get_user_publish_exchange(user)
        self.exchange.bind(user_publish_exchange, routing_key=conversation)

        user_subscribe_exchange = self.client.get_user_subscribe_exchange(user)
        user_subscribe_exchange.bind(self.exchange, routing_key=conversation)

    def unbind_user(self, conversation, user):
        user_publish_exchange = self.client.get_user_publish_exchange(user)
        self.exchange.unbind(user_publish_exchange, routing_key=conversation)

        user_subscribe_exchange = self.client.get_user_subscribe_exchange(user)
        user_subscribe_exchange.unbind(self.exchange, routing_key=conversation)


class RabbitActivity(object):
    """
        Wrapper around context activity, to receive messages as a user
    """

    def __init__(self, wrapper):
        self.client = wrapper
        self.exchange = rabbitpy.Exchange(self.client.channel, 'activity', exchange_type='direct')

    def create(self, context, users):
        for user in users:
            self.bind_user(context, user)

    def bind_user(self, context, user):
        user_subscribe_exchange = self.client.get_user_subscribe_exchange(user)
        user_subscribe_exchange.bind(self.exchange, routing_key=context)

    def unbind_user(self, context, user):
        user_subscribe_exchange = self.client.get_user_subscribe_exchange(user)
        user_subscribe_exchange.unbind(self.exchange, routing_key=context)


class RabbitClient(RabbitWrapper):
    def __init__(self, url, username, password, bind=True):
        super(RabbitClient, self).__init__(url, 'guest', 'guest')
        self.username = username

        self.subscribe = self.get_user_subscribe_exchange(self.username)
        self.publish = self.get_user_publish_exchange(self.username)

        self.queue = rabbitpy.Queue(self.channel, exclusive=True)
        self.queue.declare()
        self.queue.bind(self.subscribe)

        # Wrapper to interact with conversations
        self.conversations = RabbitConversations(self)

    def send(self, destination, message):
        str_message = message if isinstance(message, basestring) else json.dumps(message)
        message = rabbitpy.Message(self.channel, str_message)
        message.publish(self.publish, routing_key=destination)

    def get_all(self, retry=False):
        messages = []
        message_obj = True
        tries = 1 if not retry else -1
        while not(tries == 0 or messages != []):
            while message_obj is not None:
                message_obj = self.get()
                if message_obj is not None:
                    tries = 1
                    try:
                        message = (message_obj.json(), message_obj)
                    except ValueError:
                        message = (message_obj.body, message_obj)
                    messages.append(message)
            tries -= 1
            message_obj = True
        return messages

    def get(self):
        return self.queue.get()
