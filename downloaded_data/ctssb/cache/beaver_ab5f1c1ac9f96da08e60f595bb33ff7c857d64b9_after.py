# -*- coding: utf-8 -*-
import pika

from beaver.transports.base_transport import BaseTransport
from beaver.transports.exception import TransportException


class RabbitmqTransport(BaseTransport):

    def __init__(self, beaver_config, logger=None):
        super(RabbitmqTransport, self).__init__(beaver_config, logger=logger)

        self._rabbitmq_key = beaver_config.get('rabbitmq_key')
        self._rabbitmq_exchange = beaver_config.get('rabbitmq_exchange')

        # Setup RabbitMQ connection
        credentials = pika.PlainCredentials(
            beaver_config.get('rabbitmq_username'),
            beaver_config.get('rabbitmq_password')
        )
        parameters = pika.connection.ConnectionParameters(
            credentials=credentials,
            host=beaver_config.get('rabbitmq_host'),
            port=beaver_config.get('rabbitmq_port'),
            virtual_host=beaver_config.get('rabbitmq_vhost')
        )
        self._connection = pika.adapters.BlockingConnection(parameters)
        self._channel = self._connection.channel()

        # Declare RabbitMQ queue and bindings
        self._channel.queue_declare(
            queue=beaver_config.get('rabbitmq_queue'),
            durable=beaver_config.get('rabbitmq_queue_durable'),
            arguments={'x-ha-policy': 'all'} if beaver_config.get('rabbitmq_ha_queue') else {}
        )
        self._channel.exchange_declare(
            exchange=self._rabbitmq_exchange,
            type=beaver_config.get('rabbitmq_exchange_type'),
            durable=beaver_config.get('rabbitmq_exchange_durable')
        )
        self._channel.queue_bind(
            exchange=self._rabbitmq_exchange,
            queue=beaver_config.get('rabbitmq_queue'),
            routing_key=self._rabbitmq_key
        )

    def callback(self, filename, lines, **kwargs):
        timestamp = self.get_timestamp(**kwargs)
        if kwargs.get('timestamp', False):
            del kwargs['timestamp']

        for line in lines:
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('error')
                    self._channel.basic_publish(
                        exchange=self._rabbitmq_exchange,
                        routing_key=self._rabbitmq_key,
                        body=self.format(filename, line, timestamp, **kwargs),
                        properties=pika.BasicProperties(
                            content_type='text/json',
                            delivery_mode=1
                        )
                    )
            except UserWarning:
                self._is_valid = False
                raise TransportException('Connection appears to have been lost')
            except Exception, e:
                self._is_valid = False
                try:
                    raise TransportException(e.strerror)
                except AttributeError:
                    raise TransportException('Unspecified exception encountered')  # TRAP ALL THE THINGS!

    def interrupt(self):
        if self._connection:
            self._connection.close()

    def unhandled(self):
        return True
