# -*- coding: utf-8 -*-
# Copyright 2015 Cyan, Inc.
# Copyright 2016, 2017, 2018, 2019 Ciena Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""KafkaClient class.

High level network client for an Apache Kafka Cluster.
"""
from __future__ import absolute_import, print_function

import collections
import logging
import random
from functools import partial

from twisted.application.internet import backoffPolicy
from twisted.internet import defer
from twisted.internet.defer import CancelledError as t_CancelledError
from twisted.internet.defer import DeferredList, inlineCallbacks, returnValue
from twisted.internet.endpoints import HostnameEndpoint
from twisted.python.compat import nativeString
from twisted.python.compat import unicode as _unicode

from ._protocol import bootstrapFactory as _bootstrapFactory
from ._util import _coerce_client_id, _coerce_consumer_group, _coerce_topic
from .brokerclient import _KafkaBrokerClient
from .common import (
    BrokerMetadata, BrokerResponseError, CancelledError, ClientError,
    ConsumerCoordinatorNotAvailableError, DefaultKafkaPort,
    FailedPayloadsError, KafkaError, KafkaUnavailableError,
    LeaderUnavailableError, NotCoordinatorForConsumerError,
    NotLeaderForPartitionError, OffsetsLoadInProgressError,
    PartitionUnavailableError, RequestTimedOutError, TopicAndPartition,
    UnknownError, UnknownTopicOrPartitionError, _check_error,
)
from .kafkacodec import KafkaCodec

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class KafkaClient(object):
    """Cluster-aware Kafka client

    This is the high-level client which most clients should use. It maintains
    a cache of cluster metadata (brokers, topics, etc.) and routes each request
    to the appropriate broker connection. It must be bootstrapped with the
    address of at least one Kafka broker to retrieve the cluster metadata.

    When done with the client, call :meth:`.close()` to permanently dispose of
    it. This terminates any open connections and release resources.

    Do not set or mutate the attributes of `KafkaClient` objects.
    `KafkaClient` is not intended to be subclassed.

    :ivar reactor:
        Twisted reactor, as passed to the constructor. This must implement
        :class:`~twisted.internet.interfaces.IReactorTime` and
        :class:`~twisted.internet.interfaces.IReactorTCP`.

    :ivar str clientId:
        A short string used to identify the client to the server. This may
        appear in log messages on the server side.

    :ivar _brokers:
        Map of broker ID to broker metadata (host and port). This mapping is
        updated (mutated) whenever metadata is returned by a broker.
    :type _brokers:
        :class:`dict` mapping :class:`int` to :class:`afkak.common.BrokerMetadata`

    :ivar clients:
        Map of broker node ID to broker clients. Items are added to this map as
        a connection to a specific broker is needed. Once present the client's
        broker metadata is updated on change.

        Call :meth:`_get_brokerclient()` to get a broker client. This method
        constructs it and adds it to *clients* if it does not exist.

        Call :meth:`_close_brokerclients()` to close a broker client once it
        has been removed from *clients*.

        .. warning:: Despite the name, ``clients`` is a private attribute.

        Clients are removed when a full metadata fetch indicates that a broker
        no longer exists. Note that Afkak avoids doing a full metadata fetch
        whenever possible because it is an expensive operation, so it is
        possible for a broker client to remain in this map once the node is
        removed from the cluster. No requests will be routed to such a broker
        client, which will effectively leak. Afkak should be enhanced to remove
        such stale clients after a timeout period.
    :type clients:
        :class:`dict` mapping :class:`int` to :class:`_KafkaBrokerClient`

    :ivar float timeout:
        Client side request timeout, **in seconds**.

    :param float timeout:
        Client-side request timeout, **in milliseconds**.

    :param endpoint_factory:
        Callable which accepts *reactor*, *host* and *port* arguments. It must
        return a :class:`twisted.internet.interfaces.IStreamClientEndpoint`.

    :param retry_policy:
        Callable which accepts a count of *failures*. It returns the number of
        seconds (a `float`) to wait before the next attempt. This policy is
        used to schedule reconnection attempts to Kafka brokers.

        Use :func:`twisted.internet.application.backoffPolicy()` to generate
        such a callable.

    .. changeversion:: Afkak 3.0.0

          - The *endpoint_factory* argument was added.
          - The *retry_policy* argument was added.
          - *timeout* may no longer be `None`. Pass a large value instead.
    """

    # This is the __CLIENT_SIDE__ timeout that's used when making requests
    # to our brokerclients. If a request doesn't return within this amount
    # of time, we errback() the deferred. This is _NOT_ the server-side
    # timeout which is passed into the send_{produce,fetch}_request methods
    # which have defaults set below. This one should be larger, btw :-)
    DEFAULT_REQUEST_TIMEOUT_MSECS = 10000
    # Default timeout msec for fetch requests. This is how long the server
    # will wait trying to get enough bytes of messages to fulfill the fetch
    # request. When this times out on the server side, it sends back a
    # response with as many bytes of messages as it has. See the docs for
    # more caveats on this timeout.
    DEFAULT_FETCH_SERVER_WAIT_MSECS = 5000
    # Default minimum amount of message bytes sent back on a fetch request
    DEFAULT_FETCH_MIN_BYTES = 4096
    # Default number of msecs the lead-broker will wait for replics to
    # ack Produce requests before failing the request
    DEFAULT_REPLICAS_ACK_MSECS = 1000

    clientId = u"afkak-client"
    _clientIdBytes = clientId.encode()

    def __init__(self, hosts, clientId=None,
                 timeout=DEFAULT_REQUEST_TIMEOUT_MSECS,
                 disconnect_on_timeout=False,
                 correlation_id=0,
                 reactor=None,
                 endpoint_factory=HostnameEndpoint,
                 retry_policy=backoffPolicy()):
        self.timeout = float(timeout) / 1000.0  # msecs to secs

        if clientId is not None:
            self.clientId = clientId
            self._clientIdBytes = _coerce_client_id(clientId)

        # FIXME: clients should be private
        self.clients = {}  # Broker-NodeID -> _KafkaBrokerClient instance
        self.topics_to_brokers = {}  # TopicAndPartition -> BrokerMetadata
        self.partition_meta = {}  # TopicAndPartition -> PartitionMetadata
        self.consumer_group_to_brokers = {}  # consumer_group -> BrokerMetadata
        self.coordinator_fetches = {}  # consumer_group -> deferred
        self.topic_partitions = {}  # topic_id -> [0, 1, 2, ...]
        self.topic_errors = {}  # topic_id -> topic_error_code
        self.correlation_id = correlation_id
        self.close_dlist = None  # Deferred wait on broker client disconnects
        # Do we disconnect brokerclients when requests via them timeout?
        self._disconnect_on_timeout = disconnect_on_timeout
        self._brokers = {}  # Broker-NodeID -> BrokerMetadata
        self._topics = {}  # Topic-Name -> TopicMetadata
        self._closing = False  # Are we shutting down/shutdown?
        self.update_cluster_hosts(hosts)  # Store hosts and mark for lookup
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self._endpoint_factory = endpoint_factory
        assert retry_policy(1) >= 0.0
        self._retry_policy = retry_policy

    @property
    def clock(self):
        # TODO: Deprecate this
        return self.reactor

    def __repr__(self):
        """return a string representing this KafkaClient."""
        return '<{} clientId={} hosts={} timeout={}>'.format(
            self.__class__.__name__,
            self.clientId,
            ' '.join('{}:{}'.format(h, p) for h, p in self._bootstrap_hosts),
            self.timeout,
        )

    def update_cluster_hosts(self, hosts):
        """
        Advise the client of possible changes to Kafka cluster hosts

        In general Afkak will keep up with changes to the cluster, but in
        a Docker environment where all the nodes in the cluster may change IP
        address at once or in quick succession Afkak may fail to track changes
        to the cluster.

        This function lets you notify the Afkak client that some or all of the
        brokers may have changed. The hosts given are used the next time the
        client needs a fresh connection to look up cluster metadata.

        Parameters
        ==========
        hosts:
            (string|[string]) Hosts as a single comma separated
            "host[:port][,host[:port]]+" string, or a list of strings:
            ["host[:port]", ...]
        """
        self._bootstrap_hosts = _normalize_hosts(hosts)

    def reset_topic_metadata(self, *topics):
        topics = tuple(_coerce_topic(t) for t in topics)
        for topic in topics:
            try:
                partitions = self.topic_partitions[topic]
            except KeyError:
                continue

            for partition in partitions:
                self.topics_to_brokers.pop(
                    TopicAndPartition(topic, partition), None)

            del self.topic_partitions[topic]
            if topic in self.topic_errors:
                del self.topic_errors[topic]

    def reset_consumer_group_metadata(self, *groups):
        """Reset cache of what broker manages the offset for specified groups

        Remove the cache of what Kafka broker should be contacted when
        fetching or updating the committed offsets for a given consumer
        group or groups.

        NOTE: Does not cancel any outstanding requests for updates to the
        consumer group metadata for the specified groups.
        """
        groups = tuple(_coerce_consumer_group(g) for g in groups)
        for group in groups:
            if group in self.consumer_group_to_brokers:
                del self.consumer_group_to_brokers[group]

    def reset_all_metadata(self):
        """Clear all cached metadata

        Metadata will be re-fetched as required to satisfy requests.
        """
        self.topics_to_brokers.clear()
        self.topic_partitions.clear()
        self.topic_errors.clear()
        self.consumer_group_to_brokers.clear()

    def has_metadata_for_topic(self, topic):
        return _coerce_topic(topic) in self.topic_partitions

    def metadata_error_for_topic(self, topic):
        return self.topic_errors.get(
            _coerce_topic(topic), UnknownTopicOrPartitionError.errno)

    def partition_fully_replicated(self, topic_and_part):
        if topic_and_part not in self.partition_meta:
            return False
        part_meta = self.partition_meta[topic_and_part]
        return len(part_meta.replicas) == len(part_meta.isr)

    def topic_fully_replicated(self, topic):
        """
        Determine if the given topic is fully replicated according to the
        currently known cluster metadata.

        .. note::

            This relies on cached cluster metadata. You may call
            :meth:`load_metadata_for_topics()` first to refresh this cache.

        :param str topic: Topic name

        :returns:
            A boolean indicating that:

            1. The number of partitions in the topic is non-zero.
            2. For each partition, all replicas are in the in-sync replica
               (ISR) set.
        :rtype: :class:`bool`
        """
        topic = _coerce_topic(topic)
        if topic not in self.topic_partitions:
            return False
        if not self.topic_partitions[topic]:
            # Don't consider an empty partition list 'fully replicated'
            return False
        return all(
            self.partition_fully_replicated(TopicAndPartition(topic, p))
            for p in self.topic_partitions[topic]
        )

    def close(self):
        """Permanently dispose of the client

        - Immediately mark the client as closed, causing current operations to
          fail with :exc:`~afkak.common.CancelledError` and future operations to
          fail with :exc:`~afkak.common.ClientError`.
        - Clear cached metadata.
        - Close any connections to Kafka brokers.

        :returns:
            deferred that fires when all resources have been released
        """
        # If we're already waiting on an/some outstanding disconnects
        # make sure we continue to wait for them...
        log.debug("%r: close", self)
        self._closing = True
        # Close down any clients we have
        brokerclients, self.clients = self.clients, None
        self._close_brokerclients(brokerclients.values())
        # clean up other outstanding operations
        self.reset_all_metadata()
        return self.close_dlist or defer.succeed(None)

    def load_metadata_for_topics(self, *topics):
        """Discover topic metadata and brokers

        Afkak internally calls this method whenever metadata is required.

        :param str topics:
            Topic names to look up. The resulting metadata includes the list of
            topic partitions, brokers owning those partitions, and which
            partitions are in sync.

            Fetching metadata for a topic may trigger auto-creation if that is
            enabled on the Kafka broker.

            When no topic name is given metadata for *all* topics is fetched.
            This is an expensive operation, but it does not trigger topic
            creation.

        :returns:
            :class:`Deferred` for the completion of the metadata fetch.
            This will fire with ``True`` on success, ``None`` on
            cancellation, or fail with an exception on error.

            On success, topic metadata is available from the attributes of
            :class:`KafkaClient`: :data:`~KafkaClient.topic_partitions`,
            :data:`~KafkaClient.topics_to_brokers`, etc.
        """
        topics = tuple(_coerce_topic(t) for t in topics)
        log.debug("%r: load_metadata_for_topics(%s)", self, ', '.join(repr(t) for t in topics))
        fetch_all_metadata = not topics

        # create the request
        requestId = self._next_id()
        request = KafkaCodec.encode_metadata_request(self._clientIdBytes,
                                                     requestId, topics)

        # Callbacks for the request deferred...
        def _handleMetadataResponse(response):
            # Decode the response
            brokers, topics = KafkaCodec.decode_metadata_response(response)
            log.debug("%r: got metadata brokers=%r topics=%r", self, brokers, topics)

            # If we fetched the metadata for all topics, then store away the
            # received metadata for diagnostics.
            if fetch_all_metadata:
                self._brokers = brokers
                self._topics = topics

            # Iff we were fetching for all topics, and we got at least one
            # broker back, then remove brokers when we update our brokers
            ok_to_remove = (fetch_all_metadata and len(brokers))
            # Take the metadata we got back, update our self.clients, and
            # if needed disconnect or connect from/to old/new brokers
            self._update_brokers(brokers.values(), remove=ok_to_remove)

            # Now loop through all the topics/partitions in the response
            # and setup our cache/data-structures
            for topic, topic_metadata in topics.items():
                _, topic_error, partitions = topic_metadata
                self.reset_topic_metadata(topic)
                self.topic_errors[topic] = topic_error
                if not partitions:
                    log.warning('No partitions for %s, Err:%d',
                                topic, topic_error)
                    continue

                self.topic_partitions[topic] = []
                for partition, meta in partitions.items():
                    self.topic_partitions[topic].append(partition)
                    topic_part = TopicAndPartition(topic, partition)
                    self.partition_meta[topic_part] = meta
                    if meta.leader == -1:
                        log.warning('No leader for topic %s partition %s',
                                    topic, partition)
                        self.topics_to_brokers[topic_part] = None
                    else:
                        self.topics_to_brokers[
                            topic_part] = brokers[meta.leader]
                self.topic_partitions[topic] = sorted(
                    self.topic_partitions[topic])
            return True

        def _handleMetadataErr(err):
            # This should maybe do more cleanup?
            if err.check(t_CancelledError, CancelledError):
                # Eat the error
                # XXX Shouldn't this return False? The success branch
                # returns True.
                return None
            log.error("Failed to retrieve metadata:%s", err)
            raise KafkaUnavailableError(
                "Unable to load metadata from configured "
                "hosts: {!r}".format(err))

        # Send the request, add the handlers
        d = self._send_broker_unaware_request(requestId, request)
        d.addCallbacks(_handleMetadataResponse, _handleMetadataErr)
        return d

    def load_consumer_metadata_for_group(self, group):
        """
        Determine broker for the consumer metadata for the specified group

        Returns a deferred which callbacks with True if the group's coordinator
        could be determined, or errbacks with
        ConsumerCoordinatorNotAvailableError if not.

        Parameters
        ----------
        group:
            group name as `str`
        """
        group = _coerce_consumer_group(group)
        log.debug("%r: load_consumer_metadata_for_group: %r", self, group)

        # If we are already loading the metadata for this group, then
        # just return the outstanding deferred
        if group in self.coordinator_fetches:
            return self.coordinator_fetches[group]

        # No outstanding request, create a new one
        requestId = self._next_id()
        request = KafkaCodec.encode_consumermetadata_request(
            self._clientIdBytes, requestId, group)

        # Callbacks for the request deferred...
        def _handleConsumerMetadataResponse(response, group):
            # Clear the outstanding fetch
            self.coordinator_fetches.pop(group, None)
            # Decode the response (returns ConsumerMetadataResponse)
            c_m_resp = KafkaCodec.decode_consumermetadata_response(response)
            log.debug("%r: c_m_resp: %r", self, c_m_resp)
            if c_m_resp.error:
                # Raise the appropriate error
                resp_err = BrokerResponseError.errnos.get(
                    c_m_resp.error, UnknownError)(c_m_resp)
                raise resp_err

            bm = BrokerMetadata(c_m_resp.node_id, c_m_resp.host,
                                c_m_resp.port)
            self.consumer_group_to_brokers[group] = bm
            self._update_brokers([bm])
            return True

        def _handleConsumerMetadataErr(err, group):
            # Clear the outstanding fetch
            self.coordinator_fetches.pop(group, None)
            log.error("Failed to retrieve consumer metadata "
                      "for group: %s Error:%r", group, err)
            # Clear any stored value for the group's coordinator
            self.reset_consumer_group_metadata(group)
            raise ConsumerCoordinatorNotAvailableError(
                "Coordinator for group: %s not available" % (group))

        # Send the request, add the handlers
        d = self._send_broker_unaware_request(requestId, request)
        # Save the deferred under the fetches for this group
        self.coordinator_fetches[group] = d
        d.addCallback(_handleConsumerMetadataResponse, group)
        d.addErrback(_handleConsumerMetadataErr, group)
        return d

    @inlineCallbacks
    def send_produce_request(self, payloads=None, acks=1,
                             timeout=DEFAULT_REPLICAS_ACK_MSECS,
                             fail_on_error=True, callback=None):
        """
        Encode and send some ProduceRequests

        ProduceRequests will be grouped by (topic, partition) and then
        sent to a specific broker. Output is a list of responses in the
        same order as the list of payloads specified

        Parameters
        ----------
        payloads:
            list of ProduceRequest
        acks:
            How many Kafka broker replicas need to write before
            the leader replies with a response
        timeout:
            How long the server has to receive the acks from the
            replicas before returning an error.
        fail_on_error:
            boolean, should we raise an Exception if we encounter an API error?
        callback:
            function, instead of returning the ProduceResponse,
            first pass it through this function

        Return
        ------
        a deferred which callbacks with a list of ProduceResponse

        Raises
        ------
        FailedPayloadsError, LeaderUnavailableError, PartitionUnavailableError
        """

        encoder = partial(
            KafkaCodec.encode_produce_request,
            acks=acks,
            timeout=timeout)

        if acks == 0:
            decoder = None
        else:
            decoder = KafkaCodec.decode_produce_response

        resps = yield self._send_broker_aware_request(
            payloads, encoder, decoder)

        returnValue(self._handle_responses(resps, fail_on_error, callback))

    @inlineCallbacks
    def send_fetch_request(self, payloads=None, fail_on_error=True,
                           callback=None,
                           max_wait_time=DEFAULT_FETCH_SERVER_WAIT_MSECS,
                           min_bytes=DEFAULT_FETCH_MIN_BYTES):
        """
        Encode and send a FetchRequest

        Payloads are grouped by topic and partition so they can be pipelined
        to the same brokers.

        Raises
        ======
        FailedPayloadsError, LeaderUnavailableError, PartitionUnavailableError
        """
        if (max_wait_time / 1000) > (self.timeout - 0.1):
            raise ValueError(
                "%r: max_wait_time: %d must be less than client.timeout by "
                "at least 100 milliseconds.", self, max_wait_time)

        encoder = partial(KafkaCodec.encode_fetch_request,
                          max_wait_time=max_wait_time,
                          min_bytes=min_bytes)

        # resps is a list of FetchResponse() objects, each of which can hold
        # 1-n messages.
        resps = yield self._send_broker_aware_request(
            payloads, encoder,
            KafkaCodec.decode_fetch_response)

        returnValue(self._handle_responses(resps, fail_on_error, callback))

    @inlineCallbacks
    def send_offset_request(self, payloads=None, fail_on_error=True,
                            callback=None):
        resps = yield self._send_broker_aware_request(
            payloads,
            KafkaCodec.encode_offset_request,
            KafkaCodec.decode_offset_response)

        returnValue(self._handle_responses(resps, fail_on_error, callback))

    @inlineCallbacks
    def send_offset_fetch_request(self, group, payloads=None,
                                  fail_on_error=True, callback=None):
        """
        Takes a group (string) and list of OffsetFetchRequest and returns
        a list of OffsetFetchResponse objects
        """
        encoder = partial(KafkaCodec.encode_offset_fetch_request,
                          group=group)
        decoder = KafkaCodec.decode_offset_fetch_response
        resps = yield self._send_broker_aware_request(
            payloads, encoder, decoder, consumer_group=group)

        returnValue(self._handle_responses(
            resps, fail_on_error, callback, group))

    @inlineCallbacks
    def send_offset_commit_request(self, group, payloads=None,
                                   fail_on_error=True, callback=None,
                                   group_generation_id=-1,
                                   consumer_id=''):
        """Send a list of OffsetCommitRequests to the Kafka broker for the
        given consumer group.

        Args:
          group (str): The consumer group to which to commit the offsets
          payloads ([OffsetCommitRequest]): List of topic, partition, offsets
            to commit.
          fail_on_error (bool): Whether to raise an exception if a response
            from the Kafka broker indicates an error
          callback (callable): a function to call with each of the responses
            before returning the returned value to the caller.
          group_generation_id (int): Must currently always be -1
          consumer_id (str): Must currently always be empty string
        Returns:
          [OffsetCommitResponse]: List of OffsetCommitResponse objects.
          Will raise KafkaError for failed requests if fail_on_error is True
        """
        group = _coerce_consumer_group(group)
        encoder = partial(KafkaCodec.encode_offset_commit_request,
                          group=group, group_generation_id=group_generation_id,
                          consumer_id=consumer_id)
        decoder = KafkaCodec.decode_offset_commit_response
        resps = yield self._send_broker_aware_request(
            payloads, encoder, decoder, consumer_group=group)

        returnValue(self._handle_responses(
            resps, fail_on_error, callback, group))

    # # # Private Methods # # #

    def _handle_responses(self, responses, fail_on_error, callback=None,
                          consumer_group=None):
        out = []
        for resp in responses:
            try:
                _check_error(resp)
            except (UnknownTopicOrPartitionError, NotLeaderForPartitionError):
                log.error('Error found in response: %s', resp)
                self.reset_topic_metadata(resp.topic)
                if fail_on_error:
                    raise
            except (OffsetsLoadInProgressError,
                    NotCoordinatorForConsumerError,
                    ConsumerCoordinatorNotAvailableError):
                log.error('Error found in response: %s Consumer Group: %s',
                          resp, consumer_group)
                self.reset_consumer_group_metadata(consumer_group)
                if fail_on_error:
                    raise

            if callback is not None:
                out.append(callback(resp))
            else:
                out.append(resp)
        return out

    def _get_brokerclient(self, node_id):
        """
        Get a broker client.

        :param int node_id: Broker node ID
        :raises KeyError: for an unknown node ID
        :returns: :class:`_KafkaBrokerClient`
        """
        if self._closing:
            raise ClientError("Cannot get broker client for node_id={}: {} has been closed".format(node_id, self))
        if node_id not in self.clients:
            broker_metadata = self._brokers[node_id]
            log.debug("%r: creating client for %s", self, broker_metadata)
            self.clients[node_id] = _KafkaBrokerClient(
                self.reactor, self._endpoint_factory,
                broker_metadata, self.clientId, self._retry_policy,
            )
        return self.clients[node_id]

    def _close_brokerclients(self, clients):
        """
        Close the given broker clients.

        :param clients: Iterable of `_KafkaBrokerClient`
        """
        def _log_close_failure(failure, brokerclient):
            log.debug(
                'BrokerClient: %s close result: %s: %s', brokerclient,
                failure.type.__name__, failure.getErrorMessage())

        def _clean_close_dlist(result, close_dlist):
            # If there aren't any other outstanding closings going on, then
            # close_dlist == self.close_dlist, and we can reset it.
            if close_dlist == self.close_dlist:
                self.close_dlist = None

        if not self.close_dlist:
            dList = []
        else:
            log.debug("%r: _close_brokerclients has nested deferredlist: %r",
                      self, self.close_dlist)
            dList = [self.close_dlist]
        for brokerClient in clients:
            log.debug("Calling close on: %r", brokerClient)
            d = brokerClient.close().addErrback(_log_close_failure, brokerClient)
            dList.append(d)
        self.close_dlist = DeferredList(dList)
        self.close_dlist.addBoth(_clean_close_dlist, self.close_dlist)

    def _update_brokers(self, brokers, remove=False):
        """
        Update `self._brokers` and `self.clients`

        Update our self.clients based on brokers in received metadata
        Take the received dict of brokers and reconcile it with our current
        list of brokers (self.clients). If there is a new one, bring up a new
        connection to it, and if remove is True, and any in our current list
        aren't in the metadata returned, disconnect from it.

        :param brokers: Iterable of `BrokerMetadata`. A client will be created
            for every broker given if it doesn't yet exist.
        :param bool remove:
            Is this metadata for *all* brokers? If so, clients for brokers
            which are no longer found in the metadata will be closed.
        """
        log.debug("%r: _update_brokers(%r, remove=%r)",
                  self, brokers, remove)
        brokers_by_id = {bm.node_id: bm for bm in brokers}
        self._brokers.update(brokers_by_id)

        # Update the metadata of broker clients that already exist.
        for node_id, broker_meta in brokers_by_id.items():
            if node_id not in self.clients:
                continue
            self.clients[node_id].updateMetadata(broker_meta)

        # Remove any clients for brokers which no longer exist.
        if remove:
            to_close = [
                self.clients.pop(node_id)
                for node_id in set(self.clients) - set(brokers_by_id)
            ]

            if to_close:
                self._close_brokerclients(to_close)

    @inlineCallbacks
    def _get_leader_for_partition(self, topic, partition):
        """
        Returns the leader for a partition or None if the partition exists
        but has no leader.

        PartitionUnavailableError will be raised if the topic or partition
        is not part of the metadata.
        """

        key = TopicAndPartition(topic, partition)
        # reload metadata whether the partition is not available
        # or has no leader (broker is None)
        if self.topics_to_brokers.get(key) is None:
            yield self.load_metadata_for_topics(topic)

        if key not in self.topics_to_brokers:
            raise PartitionUnavailableError("%s not available" % str(key))

        returnValue(self.topics_to_brokers[key])

    @inlineCallbacks
    def _get_coordinator_for_group(self, consumer_group):
        """Returns the coordinator (broker) for a consumer group

        Returns the broker for a given consumer group or
        Raises ConsumerCoordinatorNotAvailableError
        """
        if self.consumer_group_to_brokers.get(consumer_group) is None:
            yield self.load_consumer_metadata_for_group(consumer_group)

        returnValue(self.consumer_group_to_brokers.get(consumer_group))

    def _next_id(self):
        """Generate a new correlation id."""
        # modulo to keep within int32 (signed)
        self.correlation_id = (self.correlation_id + 1) % 2**31
        return self.correlation_id

    def _make_request_to_broker(self, broker, requestId, request, **kwArgs):
        """Send a request to the specified broker."""
        def _timeout_request(broker, requestId):
            """The time we allotted for the request expired, cancel it."""
            try:
                # FIXME: This should be done by calling .cancel() on the Deferred
                # returned by the broker client.
                broker.cancelRequest(requestId, reason=RequestTimedOutError(
                    'Request: {} cancelled due to timeout'.format(requestId)))
            except KeyError:  # pragma: no cover This should never happen...
                log.exception('ERROR: Failed to find key for timed-out '
                              'request. Broker: %r Req: %d',
                              broker, requestId)
                raise
            if self._disconnect_on_timeout:
                broker.disconnect()

        def _alert_blocked_reactor(timeout, start):
            """Complain if this timer didn't fire before the timeout elapsed"""
            now = self.reactor.seconds()
            if now >= (start + timeout):
                log.warning('Reactor was starved for %r seconds', now - start)

        def _cancel_timeout(result, dc):
            """Request completed/cancelled, cancel the timeout delayedCall."""
            if dc.active():
                dc.cancel()
            return result

        # Make the request to the specified broker
        log.debug('_mrtb: sending request: %d to broker: %r',
                  requestId, broker)
        d = broker.makeRequest(requestId, request, **kwArgs)
        # Set a delayedCall to fire if we don't get a reply in time
        dc = self.reactor.callLater(
            self.timeout, _timeout_request, broker, requestId)
        # Set a delayedCall to complain if the reactor has been blocked
        rc = self.reactor.callLater(
            (self.timeout * 0.9), _alert_blocked_reactor, self.timeout,
            self.reactor.seconds())
        # Setup a callback on the request deferred to cancel both callLater
        d.addBoth(_cancel_timeout, dc)
        d.addBoth(_cancel_timeout, rc)
        return d

    @inlineCallbacks
    def _send_broker_unaware_request(self, requestId, request):
        """
        Attempt to send a broker-agnostic request to one of the known brokers:

        1. Try each connected broker (in random order)
        2. Try each known but unconnected broker (in random order)
        3. Try each of the bootstrap hosts (in random order)

        :param bytes request:
            The bytes of a Kafka `RequestMessage`_ structure. It must have
            a unique (to this connection) correlation ID.

        :returns: API response message for *request*
        :rtype: Deferred[bytes]

        :raises:
            `KafkaUnavailableError` when making the request of all known hosts
            has failed.
        """
        node_ids = list(self._brokers.keys())
        # Randomly shuffle the brokers to distribute the load
        random.shuffle(node_ids)

        # Prioritize connected brokers
        def connected(node_id):
            try:
                return self.clients[node_id].connected()
            except KeyError:
                return False

        node_ids.sort(reverse=True, key=connected)

        for node_id in node_ids:
            broker = self._get_brokerclient(node_id)
            try:
                log.debug('_sbur: sending request %d to broker %r', requestId, broker)
                d = self._make_request_to_broker(broker, requestId, request)
                resp = yield d
                returnValue(resp)
            except KafkaError as e:
                log.warning((
                    "Will try next server after request with correlationId=%d"
                    " failed against server %s:%i. Error: %s"
                ), requestId, request, broker.host, broker.port, e)

        # The request was not handled, likely because no broker metadata has
        # loaded yet (or all broker connections have failed). Fall back to
        # boostrapping.
        returnValue((yield self._send_bootstrap_request(request)))

    @inlineCallbacks
    def _send_bootstrap_request(self, request):
        """Make a request using an ephemeral broker connection

        This routine is used to make broker-unaware requests to get the initial
        cluster metadata. It cycles through the configured hosts, trying to
        connect and send the request to each in turn. This temporary connection
        is closed once a response is received.

        Note that most Kafka APIs require requests be sent to a specific
        broker. This method will only function for broker-agnostic requests
        like:

          * `Metadata <https://kafka.apache.org/protocol.html#The_Messages_Metadata>`_
          * `FindCoordinator <https://kafka.apache.org/protocol.html#The_Messages_FindCoordinator>`_

        :param bytes request:
            The bytes of a Kafka `RequestMessage`_ structure. It must have
            a unique (to this connection) correlation ID.

        :returns: API response message for *request*
        :rtype: Deferred[bytes]

        :raises:
            - `KafkaUnavailableError` when making the request of all known hosts
               has failed.
            - `twisted.internet.defer.TimeoutError` when connecting or making
               a request exceeds the timeout.
        """
        hostports = list(self._bootstrap_hosts)
        random.shuffle(hostports)
        for host, port in hostports:
            ep = self._endpoint_factory(self.reactor, host, port)
            try:
                protocol = yield ep.connect(_bootstrapFactory).addTimeout(self.timeout, self.reactor)
            except Exception as e:
                log.debug("%s: bootstrap connect to %s:%s -> %s", self, host, port, e)
                continue

            try:
                response = yield protocol.request(request).addTimeout(self.timeout, self.reactor)
            except Exception:
                log.debug("%s: bootstrap request to %s:%s failed", self, host, port, exc_info=True)
            else:
                returnValue(response)
            finally:
                protocol.transport.loseConnection()

        raise KafkaUnavailableError("Failed to bootstrap from hosts {}".format(hostports))

    @inlineCallbacks
    def _send_broker_aware_request(self, payloads, encoder_fn, decode_fn,
                                   consumer_group=None):
        """
        Group a list of request payloads by topic+partition and send them to
        the leader broker for that partition using the supplied encode/decode
        functions

        Params
        ======
        payloads: list of object-like entities with a topic and
                  partition attribute. payloads must be grouped by
                  (topic, partition) tuples.
        encode_fn: a method to encode the list of payloads to a request body,
                   must accept client_id, correlation_id, and payloads as
                   keyword arguments
        decode_fn: a method to decode a response body into response objects.
                   The response objects must be object-like and have topic
                   and partition attributes
        consumer_group: [string], optional. Indicates the request should be
                   directed to the Offset Coordinator for the specified
                   consumer_group.

        Return
        ======
        deferred yielding a list of response objects in the same order
        as the supplied payloads, or None if decode_fn is None.

        Raises
        ======
        FailedPayloadsError, LeaderUnavailableError, PartitionUnavailableError,

        """

        # Calling this without payloads is nonsensical
        if not payloads:
            raise ValueError("Payloads parameter is empty")

        # Group the requests by topic+partition
        original_keys = []
        payloads_by_broker = collections.defaultdict(list)

        # Go through all the payloads, lookup the leader/coordinator for that
        # payload's topic/partition or consumer group. If there's no
        # leader/coordinator (broker), raise. For each broker, keep
        # a list of the payloads to be sent to it. Also, for each payload in
        # the list of payloads, make a corresponding list (original_keys) with
        # the topic/partition in the same order, so we can lookup the returned
        # result(s) by that topic/partition key in the set of returned results
        # and return them in a list the same order the payloads were supplied
        for payload in payloads:
            # get leader/coordinator, depending on consumer_group
            if consumer_group is None:
                leader = yield self._get_leader_for_partition(
                    payload.topic, payload.partition)
                if leader is None:
                    raise LeaderUnavailableError(
                        "Leader not available for topic %s partition %s" %
                        (payload.topic, payload.partition))
            else:
                leader = yield self._get_coordinator_for_group(consumer_group)
                if leader is None:
                    raise ConsumerCoordinatorNotAvailableError(
                        "Coordinator not available for group: %s" %
                        (consumer_group))

            payloads_by_broker[leader].append(payload)
            original_keys.append((payload.topic, payload.partition))

        # Accumulate the responses in a dictionary
        acc = {}

        # The kafka server doesn't send replies to produce requests
        # with acks=0. In that case, our decode_fn will be
        # None, and we need to let the brokerclient know not
        # to expect a reply. makeRequest() returns a deferred
        # regardless, but in the expectResponse=False case, it will
        # fire as soon as the request is sent, and it can errBack()
        # due to being cancelled prior to the broker being able to
        # send the request.
        expectResponse = decode_fn is not None

        # keep a list of payloads that were failed to be sent to brokers
        failed_payloads = []

        # Keep track of outstanding requests in a list of deferreds
        inFlight = []
        # and the payloads that go along with them
        payloadsList = []
        # For each broker, send the list of request payloads,
        for broker_meta, payloads in payloads_by_broker.items():
            broker = self._get_brokerclient(broker_meta.node_id)
            requestId = self._next_id()
            request = encoder_fn(client_id=self._clientIdBytes,
                                 correlation_id=requestId, payloads=payloads)

            # Make the request
            d = self._make_request_to_broker(broker, requestId, request,
                                             expectResponse=expectResponse)
            inFlight.append(d)
            payloadsList.append(payloads)

        # Wait for all the responses to come back, or the requests to fail
        results = yield DeferredList(inFlight, consumeErrors=True)
        # We now have a list of (succeeded, response/Failure) tuples. Check 'em
        for (success, response), payloads in zip(results, payloadsList):
            if not success:
                # The brokerclient deferred was errback()'d:
                #   The send failed, or this request was cancelled (by timeout)
                log.debug("%r: request:%r to broker failed: %r", self,
                          payloads, response)
                failed_payloads.extend([(p, response) for p in payloads])
                continue
            if not expectResponse:
                continue
            # Successful request/response. Decode it and store by topic/part
            for response in decode_fn(response):
                acc[(response.topic, response.partition)] = response

        # Order the accumulated responses by the original key order
        # Note that this scheme will throw away responses which we did
        # not request.  See test_send_fetch_request, where the response
        # includes an error, but for a topic/part we didn't request.
        # Since that topic/partition isn't in original_keys, we don't pass
        # it back from here and it doesn't error out.
        # If any of the payloads failed, fail
        responses = [acc[k] for k in original_keys if k in acc] if acc else []
        if failed_payloads:
            self.reset_all_metadata()
            raise FailedPayloadsError(responses, failed_payloads)

        returnValue(responses)


def _normalize_hosts(hosts):
    """
    Canonicalize the *hosts* parameter.

    >>> _normalize_hosts("host,127.0.0.2:2909")
    [('127.0.0.2', 2909), ('host', 9092)]

    :param hosts:
        A list or comma-separated string of hostnames which may also include
        port numbers. All of the following are valid::

            b'host'
            u'host'
            b'host:1234'
            u'host:1234,host:2345'
            b'host:1234 , host:2345 '
            [u'host1', b'host2']
            [b'host:1234', b'host:2345']

        Hostnames must be ASCII (IDN is not supported). The default Kafka port
        of 9092 is implied when no port is given.

    :returns: A list of unique (host, port) tuples.
    :rtype: :class:`list` of (:class:`str`, :class:`int`) tuples
    """
    if isinstance(hosts, bytes):
        hosts = hosts.split(b',')
    elif isinstance(hosts, _unicode):
        hosts = hosts.split(u',')

    result = set()
    for host_port in hosts:
        # FIXME This won't handle IPv6 addresses
        res = nativeString(host_port).split(':')
        host = res[0].strip()
        port = int(res[1].strip()) if len(res) > 1 else DefaultKafkaPort
        result.add((host, port))
    return sorted(result)
