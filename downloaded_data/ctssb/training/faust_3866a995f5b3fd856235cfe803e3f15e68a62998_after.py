"""Message transport using :pypi:`aiokafka`."""
import asyncio
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    ClassVar,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    cast,
)

import aiokafka
import aiokafka.abc
from aiokafka.errors import (
    CommitFailedError,
    ConsumerStoppedError,
    IllegalStateError,
    KafkaError,
)
from aiokafka.structs import (
    ConsumerRecord,
    OffsetAndMetadata,
    TopicPartition as _TopicPartition,
)
from kafka.errors import (
    NotControllerError,
    TopicAlreadyExistsError as TopicExistsError,
    for_code,
)
from mode import Seconds, Service, flight_recorder, get_logger, want_seconds
from mode.utils.compat import OrderedDict
from mode.utils.futures import StampedeWrapper
from yarl import URL

from faust.exceptions import ProducerSendError
from faust.transport import base
from faust.transport.consumer import CONSUMER_SEEKING
from faust.types import AppT, Message, RecordMetadata, TP
from faust.types.transports import ConsumerT, ProducerT
from faust.utils import terminal
from faust.utils.kafka.protocol.admin import CreateTopicsRequest

__all__ = ['Consumer', 'Producer', 'Transport']

# This is what we get from aiokafka getmany()
# A mapping of TP to buffer-list of records.
RecordMap = Mapping[TP, List[ConsumerRecord]]

# But we want to process records from topics in round-robin order.
# We convert records into a mapping from topic-name to "chain-of-buffers":
#   topic_index['topic-name'] = chain(all_topic_partition_buffers)
# This means we can get the next message available in any topic
# by doing: next(topic_index['topic_name'])
TopicIndexMap = MutableMapping[str, '_TopicBuffer']

_TPTypes = Union[TP, _TopicPartition]

logger = get_logger(__name__)


def server_list(url: URL, default_port: int) -> str:
    # remove the scheme
    servers = str(url).split('://', 1)[1]
    # add default ports
    return ';'.join(host if ':' in host else f'{host}:{default_port}'
                    for host in servers.split(';'))


def _ensure_TP(tp: _TPTypes) -> TP:
    return tp if isinstance(tp, TP) else TP(tp.topic, tp.partition)


class _TopicBuffer(Iterator):
    _buffers: Dict[TP, Iterator[ConsumerRecord]]
    _it = Iterator[ConsumerRecord]

    def __init__(self) -> None:
        # note: this is a regular dict, but ordered on Python 3.6
        # we use this alias to signify it must be ordered.
        self._buffers = OrderedDict()
        # getmany calls next(_TopicBuffer), and does not call iter(),
        # so the first call to next caches an iterator.
        self._it: Iterator[ConsumerRecord] = None

    def add(self, tp: TP, buffer: List[ConsumerRecord]) -> None:
        assert tp not in self._buffers
        self._buffers[tp] = iter(buffer)

    def __iter__(self) -> Iterator[Tuple[TP, ConsumerRecord]]:
        buffers = self._buffers
        buffers_items = buffers.items
        buffers_remove = buffers.pop
        sentinel = object()
        to_remove: Set[TP] = set()
        mark_as_to_remove = to_remove.add
        while buffers:
            for tp in to_remove:
                buffers_remove(tp, None)
            for tp, buffer in buffers_items():
                item = next(buffer, sentinel)
                if item is sentinel:
                    mark_as_to_remove(tp)
                    continue
                yield tp, item

    def __next__(self) -> Tuple[TP, ConsumerRecord]:
        it = self._it
        if it is None:
            it = self._it = iter(self)
        return it.__next__()


class ConsumerRebalanceListener(aiokafka.abc.ConsumerRebalanceListener):
    # kafka's ridiculous class based callback interface makes this hacky.

    def __init__(self, consumer: ConsumerT) -> None:
        self.consumer: ConsumerT = consumer

    async def on_partitions_revoked(
            self, revoked: Iterable[_TopicPartition]) -> None:
        self.consumer.app.rebalancing = True
        # see comment in on_partitions_assigned
        consumer = cast(Consumer, self.consumer)
        _revoked = cast(Set[TP], set(revoked))
        # remove revoked partitions from active + paused tps.
        consumer._active_partitions.difference_update(_revoked)
        consumer._paused_partitions.difference_update(_revoked)
        # start callback chain of assigned callbacks.
        await consumer.on_partitions_revoked(set(_revoked))

    async def on_partitions_assigned(
            self, assigned: Iterable[_TopicPartition]) -> None:
        # have to cast to Consumer since ConsumerT interface does not
        # have this attribute (mypy currently thinks a Callable instance
        # variable is an instance method).  Furthermore we have to cast
        # the Kafka TopicPartition namedtuples to our description,
        # that way they are typed and decoupled from the actual client
        # implementation.
        consumer = cast(Consumer, self.consumer)
        _assigned = set(assigned)
        # remove recently revoked tps from set of paused tps.
        consumer._paused_partitions.intersection_update(_assigned)
        # cache set of assigned partitions
        cast(Set[TP], consumer._set_active_tps(_assigned))
        # start callback chain of assigned callbacks.
        #   need to copy set at this point, since we cannot have
        #   the callbacks mutate our active list.
        consumer._last_batch = None
        try:
            await consumer.on_partitions_assigned(_assigned)
        finally:
            consumer.app.rebalancing = False


class Consumer(base.Consumer):
    """Kafka consumer using :pypi:`aiokafka`."""

    logger = logger

    RebalanceListener: ClassVar[Type[ConsumerRebalanceListener]]
    RebalanceListener = ConsumerRebalanceListener

    _consumer: aiokafka.AIOKafkaConsumer
    _rebalance_listener: ConsumerRebalanceListener
    _active_partitions: Set[_TopicPartition] = None
    _paused_partitions: Set[_TopicPartition] = None
    _partitions_lock: asyncio.Lock = None
    fetch_timeout: float = 10.0
    wait_for_shutdown = True

    consumer_stopped_errors: ClassVar[Tuple[Type[BaseException], ...]] = (
        ConsumerStoppedError,
    )

    def on_init(self) -> None:
        app = self.transport.app
        transport = cast(Transport, self.transport)
        self._rebalance_listener = self.RebalanceListener(self)
        if app.client_only:
            self._consumer = self._create_client_consumer(app, transport)
        else:
            self._consumer = self._create_worker_consumer(app, transport)
        self._paused_partitions = set()
        self._partitions_lock = asyncio.Lock(loop=self.loop)

    async def on_restart(self) -> None:
        self.on_init()

    def _get_active_partitions(self) -> Set[_TopicPartition]:
        tps = self._active_partitions
        if tps is None:
            # need aiokafka._TopicPartition, not faust.TP
            return self._set_active_tps(self._consumer.assignment())
        return tps

    def _set_active_tps(self,
                        tps: Set[_TopicPartition]) -> Set[_TopicPartition]:
        tps = self._active_partitions = set(tps)  # copy!
        tps.difference_update(self._paused_partitions)
        return tps

    def _create_worker_consumer(
            self,
            app: AppT,
            transport: 'Transport') -> aiokafka.AIOKafkaConsumer:
        self._assignor = self.app.assignor
        return aiokafka.AIOKafkaConsumer(
            loop=self.loop,
            client_id=app.conf.broker_client_id,
            group_id=app.conf.id,
            bootstrap_servers=server_list(
                transport.url, transport.default_port),
            partition_assignment_strategy=[self._assignor],
            enable_auto_commit=False,
            auto_offset_reset='earliest',
            max_poll_records=None,
            max_partition_fetch_bytes=1048576 * 4,
            fetch_max_wait_ms=1500,
            check_crcs=app.conf.broker_check_crcs,
        )

    def _create_client_consumer(
            self,
            app: AppT,
            transport: 'Transport') -> aiokafka.AIOKafkaConsumer:
        return aiokafka.AIOKafkaConsumer(
            loop=self.loop,
            client_id=app.conf.broker_client_id,
            bootstrap_servers=server_list(
                transport.url, transport.default_port),
            enable_auto_commit=True,
            auto_offset_reset='earliest',
            check_crcs=app.conf.broker_check_crcs,
        )

    async def create_topic(self,
                           topic: str,
                           partitions: int,
                           replication: int,
                           *,
                           config: Mapping[str, Any] = None,
                           timeout: Seconds = 1000.0,
                           retention: Seconds = None,
                           compacting: bool = None,
                           deleting: bool = None,
                           ensure_created: bool = False) -> None:
        await cast(Transport, self.transport)._create_topic(
            self,
            self._consumer._client,
            topic,
            partitions,
            replication,
            config=config,
            timeout=int(want_seconds(timeout) * 1000.0),
            retention=int(want_seconds(retention) * 1000.0),
            compacting=compacting,
            deleting=deleting,
            ensure_created=ensure_created,
        )

    async def on_start(self) -> None:
        self.beacon.add(self._consumer)
        await self._consumer.start()

    async def subscribe(self, topics: Iterable[str]) -> None:
        # XXX pattern does not work :/
        self._consumer.subscribe(
            topics=set(topics),
            listener=self._rebalance_listener,
        )

    async def getmany(self,
                      timeout: float) -> AsyncIterator[Tuple[TP, Message]]:
        _consumer = self._consumer
        if _consumer._closed:
            raise ConsumerStoppedError()
        active_partitions = self._get_active_partitions()
        fetcher = _consumer._fetcher
        _next = next

        records: RecordMap = {}
        async with self._partitions_lock:
            if active_partitions:
                # Fetch records only if active partitions to avoid the risk of
                # fetching all partitions in the beginning when none of the
                # partitions is paused/resumed.
                records = await fetcher.fetched_records(
                    active_partitions,
                    timeout=timeout,
                )
            else:
                # We should still release to the event loop
                await self.sleep(0)
        create_message = Message  # localize

        # records' contain mapping from TP to list of messages.
        # if there are two agents, consuming from topics t1 and t2,
        # normal order of iteration would be to process each
        # tp in the dict:
        #    for tp. messages in records.items():
        #        for message in messages:
        #           yield tp, message
        #
        # The problem with this, is if we have prefetched 16k records
        # for one partition, the other partitions won't even start processing
        # before those 16k records are completed.
        #
        # So we try round-robin between the tps instead:
        #
        #    iterators: Dict[TP, Iterator] = {
        #        tp: iter(messages)
        #        for tp, messages in records.items()
        #    }
        #    while iterators:
        #        for tp, messages in iterators.items():
        #            yield tp, next(messages)
        #            # remove from iterators if empty.
        #
        # The problem with this implementation is that
        # the records mapping is ordered by TP, so records.keys()
        # will look like this:
        #
        #  TP(topic='bar', partition=0)
        #  TP(topic='bar', partition=1)
        #  TP(topic='bar', partition=2)
        #  TP(topic='bar', partition=3)
        #  TP(topic='foo', partition=0)
        #  TP(topic='foo', partition=1)
        #  TP(topic='foo', partition=2)
        #  TP(topic='foo', partition=3)
        #
        # If there are 100 partitions for each topic,
        # it will process 100 items in the first topic, then 100 items
        # in the other topic, but even worse if partition counts
        # vary greatly, t1 has 1000 partitions and t2
        # has 1 partition, then t2 will end up being starved most of the time.
        #
        # We solve this by going round-robin through each topic.
        topic_index = self._records_to_topic_index(records, active_partitions)
        to_remove: Set[str] = set()
        sentinel = object()
        while topic_index:
            for topic in to_remove:
                topic_index.pop(topic, None)
            for topic, messages in topic_index.items():
                item = _next(messages, sentinel)
                if item is sentinel:
                    # this topic is now empty,
                    # but we cannot remove from dict while iterating over it,
                    # so move that to the outer loop.
                    to_remove.add(topic)
                    continue
                tp, record = item  # type: ignore
                yield tp, create_message(
                    record.topic,
                    record.partition,
                    record.offset,
                    record.timestamp / 1000.0,
                    record.timestamp_type,
                    record.key,
                    record.value,
                    record.checksum,
                    record.serialized_key_size,
                    record.serialized_value_size,
                    tp,
                )

    def _records_to_topic_index(self,
                                records: RecordMap,
                                active_partitions: Set[TP]) -> TopicIndexMap:
        topic_index: TopicIndexMap = {}
        for tp, messages in records.items():
            if tp not in active_partitions:
                self.log.error(f'SKIP PAUSED PARTITION: {tp} '
                               f'ACTIVES: {active_partitions}')
                continue
            try:
                entry = topic_index[tp.topic]
            except KeyError:
                entry = topic_index[tp.topic] = _TopicBuffer()
            entry.add(tp, messages)
        return topic_index

    async def verify_subscription(self, assigned: Set[TP]) -> None:
        subscription = (
            self._consumer.subscription() - self.randomly_assigned_topics)
        assigned_topics = {t for t, p in assigned}
        missing = subscription - assigned_topics
        if missing:
            self.log.error(
                f'Subscribed but not assigned to topics: {missing}.'
                f'Please restart the worker in a bit, '
                f'maybe topics not created yet')

    def _new_topicpartition(self, topic: str, partition: int) -> TP:
        return cast(TP, _TopicPartition(topic, partition))

    def _new_offsetandmetadata(self, offset: int, meta: str) -> Any:
        return OffsetAndMetadata(offset, meta)

    async def on_stop(self) -> None:
        await self.commit()
        await self._consumer.stop()
        cast(Transport, self.transport)._topic_waiters.clear()

    async def perform_seek(self) -> None:
        await self.transition_with(CONSUMER_SEEKING, self._perform_seek())

    async def _perform_seek(self) -> None:
        read_offset = self._read_offset
        self._consumer.seek_to_committed()
        tps = self._consumer.assignment()
        wait_res = await self.wait(
            asyncio.gather(*[self._consumer.committed(tp) for tp in tps]))
        offsets = zip(tps, wait_res.result)
        committed_offsets = dict(filter(lambda x: x[1] is not None, offsets))
        read_offset.update(committed_offsets)
        self._committed_offset.update(committed_offsets)

    async def _commit(self, offsets: Mapping[TP, Tuple[int, str]]) -> bool:
        table = terminal.logtable(
            [(str(tp), str(offset), meta)
             for tp, (offset, meta) in offsets.items()],
            title='Commit Offsets',
            headers=['TP', 'Offset', 'Metadata'],
        )
        self.log.dev('COMMITTING OFFSETS:\n%s', table)
        try:
            assignment = self.assignment()
            commitable: Dict[TP, OffsetAndMetadata] = {}
            revoked: Dict[TP, OffsetAndMetadata] = {}
            commitable_offsets: Dict[TP, int] = {}
            for tp, (offset, meta) in offsets.items():
                offset_and_metadata = self._new_offsetandmetadata(offset, meta)
                if tp in assignment:
                    commitable_offsets[tp] = offset
                    commitable[tp] = offset_and_metadata
                else:
                    revoked[tp] = offset_and_metadata
            if revoked:
                self.log.info(
                    'Discarded commit for revoked partitions that '
                    'will be eventually processed again: %r',
                    revoked,
                )
            if not commitable:
                return False
            with flight_recorder(self.log, timeout=300.0) as on_timeout:
                on_timeout.info('+aiokafka_consumer.commit()')
                await self._consumer.commit(commitable)
                on_timeout.info('-aiokafka._consumer.commit()')
            self._committed_offset.update(commitable_offsets)
            self._last_batch = None
            return True
        except CommitFailedError as exc:
            self.log.exception(f'Committing raised exception: %r', exc)
            return False
        except IllegalStateError as exc:
            self.log.exception(f'Got exception: {exc}\n'
                               f'Current assignment: {self.assignment()}')
            await self.crash(exc)
            return False

    async def pause_partitions(self, tps: Iterable[TP]) -> None:
        self.log.info(f'Waiting for lock to pause partitions')
        async with self._partitions_lock:
            self.log.info(f'Acquired lock to pause partitions')
            tpset = set(tps)
            self._get_active_partitions().difference_update(tpset)
            self._paused_partitions.update(tpset)
        self.log.info(f'Released pause partitions lock')

    async def resume_partitions(self, tps: Iterable[TP]) -> None:
        self.log.info(f'Waiting for lock to resume partitions')
        async with self._partitions_lock:
            self.log.info(f'Acquired lock to resume partitions')
            tpset = set(tps)
            self._get_active_partitions().update(tps)
            self._paused_partitions.difference_update(tpset)
        self.log.info(f'Released resume partitions lock')

    async def position(self, tp: TP) -> Optional[int]:
        return await self._consumer.position(tp)

    async def _seek_to_beginning(self, *partitions: TP) -> None:
        self.log.dev('SEEK TO BEGINNING: %r', partitions)
        self._read_offset.update((_ensure_TP(tp), None) for tp in partitions)
        await self._consumer.seek_to_beginning(*(
            self._new_topicpartition(tp.topic, tp.partition)
            for tp in partitions
        ))

    async def seek(self, partition: TP, offset: int) -> None:
        self.log.dev('SEEK %r -> %r', partition, offset)
        # reset livelock detection
        self._last_batch = None
        # set new read offset so we will reread messages
        self._read_offset[_ensure_TP(partition)] = offset
        self._consumer.seek(partition, offset)

    def assignment(self) -> Set[TP]:
        return cast(Set[TP], self._consumer.assignment())

    def highwater(self, tp: TP) -> int:
        return self._consumer.highwater(tp)

    async def earliest_offsets(self,
                               *partitions: TP) -> MutableMapping[TP, int]:
        return await self._consumer.beginning_offsets(partitions)

    async def highwaters(self, *partitions: TP) -> MutableMapping[TP, int]:
        return await self._consumer.end_offsets(partitions)


class Producer(base.Producer):
    """Kafka producer using :pypi:`aiokafka`."""

    logger = logger

    _producer: aiokafka.AIOKafkaProducer

    def on_init(self) -> None:
        transport = cast(Transport, self.transport)
        self._producer = aiokafka.AIOKafkaProducer(
            loop=self.loop,
            bootstrap_servers=server_list(
                transport.url, transport.default_port),
            client_id=transport.app.conf.broker_client_id,
            acks=self.acks,
            linger_ms=self.linger_ms,
            max_batch_size=self.max_batch_size,
            max_request_size=self.max_request_size,
            compression_type=self.compression_type,
        )

    async def on_restart(self) -> None:
        self.on_init()

    async def create_topic(self,
                           topic: str,
                           partitions: int,
                           replication: int,
                           *,
                           config: Mapping[str, Any] = None,
                           timeout: Seconds = 1000.0,
                           retention: Seconds = None,
                           compacting: bool = None,
                           deleting: bool = None,
                           ensure_created: bool = False) -> None:
        _retention = (int(want_seconds(retention) * 1000.0)
                      if retention else None)
        await cast(Transport, self.transport)._create_topic(
            self,
            self._producer.client,
            topic,
            partitions,
            replication,
            config=config,
            timeout=int(want_seconds(timeout) * 1000.0),
            retention=_retention,
            compacting=compacting,
            deleting=deleting,
            ensure_created=ensure_created,
        )

    async def on_start(self) -> None:
        self.beacon.add(self._producer)
        self._last_batch = None
        await self._producer.start()

    async def on_stop(self) -> None:
        cast(Transport, self.transport)._topic_waiters.clear()
        self._last_batch = None
        await self._producer.stop()

    async def send(self, topic: str, key: Optional[bytes],
                   value: Optional[bytes],
                   partition: Optional[int]) -> Awaitable[RecordMetadata]:
        try:
            return cast(Awaitable[RecordMetadata], await self._producer.send(
                topic, value, key=key, partition=partition))
        except KafkaError as exc:
            raise ProducerSendError(f'Error while sending: {exc!r}') from exc

    async def send_and_wait(self, topic: str, key: Optional[bytes],
                            value: Optional[bytes],
                            partition: Optional[int]) -> RecordMetadata:
        fut = await self.send(topic, key=key, value=value, partition=partition)
        return await fut

    def key_partition(self, topic: str, key: bytes) -> TP:
        partition = self._producer._partition(
            topic,
            partition=None,
            key=None,
            value=None,
            serialized_key=key,
            serialized_value=None,
        )
        return TP(topic, partition)


class Transport(base.Transport):
    """Kafka transport using :pypi:`aiokafka`."""

    Consumer: ClassVar[Type[ConsumerT]] = Consumer
    Producer: ClassVar[Type[ProducerT]] = Producer

    default_port = 9092
    driver_version = f'aiokafka={aiokafka.__version__}'

    _topic_waiters: MutableMapping[str, StampedeWrapper]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._topic_waiters = {}

    def _topic_config(self,
                      retention: int = None,
                      compacting: bool = None,
                      deleting: bool = None) -> MutableMapping[str, Any]:
        config: MutableMapping[str, Any] = {}
        cleanup_flags: Set[str] = set()
        if compacting:
            cleanup_flags |= {'compact'}
        if deleting:
            cleanup_flags |= {'delete'}
        if cleanup_flags:
            config['cleanup.policy'] = ','.join(sorted(cleanup_flags))
        if retention:
            config['retention.ms'] = retention
        return config

    async def _create_topic(self,
                            owner: Service,
                            client: aiokafka.AIOKafkaClient,
                            topic: str,
                            partitions: int,
                            replication: int,
                            **kwargs: Any) -> None:
        assert topic is not None
        try:
            wrap = self._topic_waiters[topic]
        except KeyError:
            wrap = self._topic_waiters[topic] = StampedeWrapper(
                self._really_create_topic,
                owner,
                client,
                topic,
                partitions,
                replication,
                loop=self.loop, **kwargs)
        try:
            await wrap()
        except Exception as exc:
            self._topic_waiters.pop(topic, None)
            raise

    async def _really_create_topic(self,
                                   owner: Service,
                                   client: aiokafka.AIOKafkaClient,
                                   topic: str,
                                   partitions: int,
                                   replication: int,
                                   *,
                                   config: Mapping[str, Any] = None,
                                   timeout: int = 10000,
                                   retention: int = None,
                                   compacting: bool = None,
                                   deleting: bool = None,
                                   ensure_created: bool = False) -> None:
        owner.log.info(f'Creating topic {topic}')
        protocol_version = 1
        extra_configs = config or {}
        config = self._topic_config(retention, compacting, deleting)
        config.update(extra_configs)

        # Create topic request needs to be sent to the kafka cluster controller
        # Since aiokafka client doesn't currently support MetadataRequest
        # version 1, client.controller will always be None. Hence we cycle
        # through all brokers if we get Error 41 (not controller) until we
        # hit the controller
        nodes = [broker.nodeId for broker in client.cluster.brokers()]
        owner.log.info(f'Nodes: {nodes}')
        for node_id in nodes:
            if node_id is None:
                raise RuntimeError('Not connected to Kafka broker')

            request = CreateTopicsRequest[protocol_version](
                [(topic, partitions, replication, [], list(config.items()))],
                timeout,
                False,
            )
            response = await client.send(node_id, request)
            assert len(response.topic_error_codes), 'Single topic requested.'

            _, code, reason = response.topic_error_codes[0]

            if code != 0:
                if not ensure_created and code == TopicExistsError.errno:
                    owner.log.debug(
                        f'Topic {topic} exists, skipping creation.')
                    return
                elif code == NotControllerError.errno:
                    owner.log.debug(f'Broker: {node_id} is not controller.')
                    continue
                else:
                    raise for_code(code)(
                        f'Cannot create topic: {topic} ({code}): {reason}')
            else:
                owner.log.info(f'Topic {topic} created.')
                return
        raise Exception(f'No controller found among brokers: {nodes}')
