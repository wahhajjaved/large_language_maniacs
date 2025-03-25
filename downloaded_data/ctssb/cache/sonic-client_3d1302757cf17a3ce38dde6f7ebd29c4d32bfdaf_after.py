import json
import pika
from config import CONF
from encryption import decrypt
from manager import Manager



class ActionUnsupportedError(Exception):
    def __init__(self, action):
        super(Exception, self).__init__("{} action is not"
                                        "supported by sonic"
                                        "client".format(action))


class SonicClient(object):
    QUEUE = CONF.name
    def __init__(self, logger):
        self.amqp_channel = _create_amqp_channel()
        self.amqp_channel.queue_declare(queue=self.QUEUE)
        self.manager = Manager()
        self.logger = logger

    def _callback(self, ch, method, properties, body):
        self.logger.debug("Processing {}".format(body))
        try:
            #message = json.loads(decrypt(body))
            message = json.loads(body)
            for key, val in message.iteritems():
                if hasattr(self.manager, key):
                    getattr(self.manager, key)(val)
                else:
                    raise ActionUnsupportedError(key)
        except Exception as e:
            self.logger.error("Error while processing message - {}"
                              .format(e.message))

    def run(self):
        self.amqp_channel.basic_consume(self._callback,
                                        queue=self.QUEUE,
                                        no_ack=True)
        self.amqp_channel.start_consuming()


def _create_amqp_channel():
    host = CONF.amqp_host
    port = CONF.amqp_port
    username = CONF.amqp_username
    password = CONF.amqp_password
    credentials = pika.PlainCredentials(username, password)
    parameters = pika.ConnectionParameters(host,
                                           port,
                                           '/',
                                           credentials)
    connection = pika.BlockingConnection(parameters)
    return connection.channel()


