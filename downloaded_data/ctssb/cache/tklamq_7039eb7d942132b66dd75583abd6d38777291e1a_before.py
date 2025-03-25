"""
Environment variables:

    BROKER_HOSTNAME     default: localhost
    BROKER_PORT         default: 5672
    BROKER_VHOST        default: /
    BROKER_USERID       default: guest
    BROKER_PASSWORD     default: guest
"""

import os

from carrot.connection import BrokerConnection
from carrot.messaging import Publisher, Consumer

BROKER_HOSTNAME = os.getenv('BROKER_HOSTNAME', 'localhost')
BROKER_PORT = os.getenv('BROKER_PORT', 5672)
BROKER_VHOST = os.getenv('BROKER_VHOST', '/')
BROKER_USERID = os.getenv('BROKER_USERID', 'guest')
BROKER_PASSWORD = os.getenv('BROKER_PASSWORD', 'guest')

class Error(Exception):
    pass

class Connection:
    def __init__(self, hostname, port, vhost, userid, password):
        """connects to broker and provides convenience methods"""
        self.broker = BrokerConnection(hostname=hostname, port=port,
                                       userid=userid, password=password,
                                       virtual_host=vhost)
    
    def __del__(self):
        self.broker.close()

    def declare(self, exchange, exchange_type, binding="", queue=""):
        """declares the exchange, the queue and binds the queue to the exchange
        
        exchange        - exchange name
        exchange_type   - direct, topic, fanout
        binding         - binding to queue (optional)
        queue           - queue to bind to exchange using binding (optional)
        """
        if (binding and not queue) or (queue and not binding):
            raise Error("binding and queue are not mutually exclusive")

        consumer = Consumer(connection=self.broker,
                            exchange=exchange, exchange_type=exchange_type,
                            routing_key=binding, queue=queue)
        consumer.declare()
        consumer.close()

    def consume(self, queue, limit=None, callback=None):
        """consume messages in queue
        
        queue    - name of queue
        limit    - amount of messages to iterate through (default: no limit)

        callback - the callback function to call when a new message is received
                   must take two arguments: message_data, message
                   must send the acknowledgement: message.ack()
                   default: print message to stdout and send ack
        """
        if not callback:
            callback = _consume_callback

        consumer = Consumer(connection=self.broker, queue=queue)
        consumer.register_callback(callback)
        for message in consumer.iterqueue(limit=None, infinite=False):
            consumer.receive(message.payload, message)

        consumer.close()

    def publish(self, exchange, routing_key, message, auto_declare=False):
        """publish a message to exchange using routing_key
        
        exchange        - name of exchange
        routing_key     - interpretation of routing key depends on exchange type
        message         - message content to send
        auto_declare    - automatically declare the exchange (default: false)
        """
        publisher = Publisher(connection=self.broker,
                              exchange=exchange, routing_key=routing_key,
                              auto_declare=auto_declare)

        publisher.send(message)
        publisher.close()

def _consume_callback(message_data, message):
    """default consume callback if not specified"""
    print message_data
    message.ack()

def connect():
    """convenience method using environment variables"""
    return Connection(BROKER_HOSTNAME, BROKER_PORT, BROKER_VHOST,
                      BROKER_USERID, BROKER_PASSWORD)


