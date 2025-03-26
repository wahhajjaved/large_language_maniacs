from kombu import Connection
from kombu.pools import producers

from st2common import log as logging

CREATE_RK = 'create'
UPDATE_RK = 'update'
DELETE_RK = 'delete'

LOG = logging.getLogger(__name__)


class PoolPublisher(object):
    def __init__(self, url):
        self.pool = Connection(url).Pool(limit=10)

    def errback(self, exc, interval):
        LOG.error('Rabbitmq connection error: %r', exc, exc_info=True)

    def publish(self, payload, exchange, routing_key=''):
        # pickling the payload for now. Better serialization mechanism is essential.
        with self.pool.acquire(block=True) as connection:
            with producers[connection].acquire(block=True) as producer:
                try:
                    publish = connection.ensure(producer, producer.publish, errback=self.errback,
                                                max_retries=3)
                    publish(payload, exchange=exchange, routing_key=routing_key,
                            serializer='pickle')
                except:
                    LOG.exception('Connections to rabbitmq cannot be re-established.')


class CUDPublisher(object):
    def __init__(self, url, exchange):
        self._publisher = PoolPublisher(url)
        self._exchange = exchange

    def publish_create(self, payload):
        self._publisher.publish(payload, self._exchange, CREATE_RK)

    def publish_update(self, payload):
        self._publisher.publish(payload, self._exchange, UPDATE_RK)

    def publish_delete(self, payload):
        self._publisher.publish(payload, self._exchange, DELETE_RK)
