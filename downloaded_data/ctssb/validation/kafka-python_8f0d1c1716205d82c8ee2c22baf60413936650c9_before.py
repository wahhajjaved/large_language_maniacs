import collections
import logging
import time

import six

from .abstract import AbstractCoordinator
import kafka.common as Errors
from kafka.common import OffsetAndMetadata, TopicPartition
from kafka.future import Future
from kafka.protocol.commit import OffsetCommitRequest_v2, OffsetFetchRequest_v1
from kafka.protocol.struct import Struct
from kafka.protocol.types import Array, Bytes, Int16, Int32, Schema, String

log = logging.getLogger(__name__)


class ConsumerProtocolMemberMetadata(Struct):
    SCHEMA = Schema(
        ('version', Int16),
        ('subscription', Array(String('utf-8'))),
        ('user_data', Bytes))


class ConsumerProtocolMemberAssignment(Struct):
    SCHEMA = Schema(
        ('version', Int16),
        ('assignment', Array(
            ('topic', String('utf-8')),
            ('partitions', Array(Int32)))),
        ('user_data', Bytes))

    def partitions(self):
        return [TopicPartition(topic, partition)
                for topic, partitions in self.assignment # pylint: disable-msg=no-member
                for partition in partitions]


class ConsumerProtocol(object):
    PROTOCOL_TYPE = 'consumer'
    ASSIGNMENT_STRATEGIES = ('roundrobin',)
    METADATA = ConsumerProtocolMemberMetadata
    ASSIGNMENT = ConsumerProtocolMemberAssignment


class ConsumerCoordinator(AbstractCoordinator):
    """This class manages the coordination process with the consumer coordinator."""
    _enable_auto_commit = True
    _auto_commit_interval_ms = 5000
    _default_offset_commit_callback = lambda offsets, error: True
    _assignors = ()
    #_heartbeat_interval_ms = 3000
    #_session_timeout_ms = 30000
    #_retry_backoff_ms = 100

    def __init__(self, client, group_id, subscription, **kwargs):
        """Initialize the coordination manager."""
        super(ConsumerCoordinator, self).__init__(client, group_id, **kwargs)
        for config in ('enable_auto_commit', 'auto_commit_interval_ms',
                       'default_offset_commit_callback', 'assignors'):
            if config in kwargs:
                setattr(self, '_' + config, kwargs.pop(config))

        self._cluster = client.cluster
        self._subscription = subscription
        self._partitions_per_topic = {}
        self._auto_commit_task = None
        if not self._assignors:
            raise Errors.IllegalStateError('Coordinator requires assignors')

        self._cluster.request_update()
        self._cluster.add_listener(self._handle_metadata_update)

        if self._enable_auto_commit:
            interval = self._auto_commit_interval_ms / 1000.0
            self._auto_commit_task = AutoCommitTask(self, interval)

        # metrics=None,
        # metric_group_prefix=None,
        # metric_tags=None,
        # self.sensors = ConsumerCoordinatorMetrics(metrics, metric_group_prefix, metric_tags)

    def protocol_type(self):
        return ConsumerProtocol.PROTOCOL_TYPE

    def group_protocols(self):
        """Returns list of preferred (protocols, metadata)"""
        topics = self._subscription.subscription
        metadata_list = []
        for assignor in self._assignors:
            metadata = assignor.metadata(topics)
            group_protocol = (assignor.name, metadata)
            metadata_list.append(group_protocol)
        return metadata_list

    def _handle_metadata_update(self, cluster):
        # if we encounter any unauthorized topics, raise an exception
        # TODO
        #if self._cluster.unauthorized_topics:
        #    raise Errors.TopicAuthorizationError(self._cluster.unauthorized_topics)

        if self._subscription.subscribed_pattern:
            topics = []
            for topic in cluster.topics():
                if self._subscription.subscribed_pattern.match(topic):
                    topics.append(topic)

            self._subscription.change_subscription(topics)
            self._client.set_topics(self._subscription.group_subscription())

        # check if there are any changes to the metadata which should trigger a rebalance
        if self._subscription_metadata_changed():
            self._subscription.mark_for_reassignment()

    def _subscription_metadata_changed(self):
        if not self._subscription.partitions_auto_assigned():
            return False

        old_partitions_per_topic = self._partitions_per_topic
        self._partitions_per_topic = {}
        for topic in self._subscription.group_subscription():
            self._partitions_per_topic[topic] = set(self._cluster.partitions_for_topic(topic))

        if self._partitions_per_topic != old_partitions_per_topic:
            return True
        return False

    def _lookup_assignor(self, name):
        for assignor in self._assignors:
            if assignor.name == name:
                return assignor
        return None

    def _on_join_complete(self, generation, member_id, protocol,
                          member_assignment_bytes):
        assignor = self._lookup_assignor(protocol)
        if not assignor:
            raise Errors.IllegalStateError("Coordinator selected invalid"
                                           " assignment protocol: %s"
                                           % protocol)

        assignment = ConsumerProtocol.ASSIGNMENT.decode(member_assignment_bytes)

        # set the flag to refresh last committed offsets
        self._subscription.needs_fetch_committed_offsets = True

        # update partition assignment
        self._subscription.assign_from_subscribed(assignment.partitions())

        # give the assignor a chance to update internal state
        # based on the received assignment
        assignor.on_assignment(assignment)

        # restart the autocommit task if needed
        if self._enable_auto_commit:
            self._auto_commit_task.enable()

        assigned = set(self._subscription.assigned_partitions())
        log.debug("Set newly assigned partitions %s", assigned)

        # execute the user's callback after rebalance
        if self._subscription.listener:
            try:
                self._subscriptions.listener.on_partitions_assigned(assigned)
            except Exception:
                log.exception("User provided listener failed on partition"
                              " assignment: %s", assigned)

    def _perform_assignment(self, leader_id, assignment_strategy, members):
        assignor = self._lookup_assignor(assignment_strategy)
        if not assignor:
            raise Errors.IllegalStateError("Coordinator selected invalid"
                                           " assignment protocol: %s"
                                           % assignment_strategy)
        member_metadata = {}
        all_subscribed_topics = set()
        for member_id, metadata_bytes in members:
            metadata = ConsumerProtocol.METADATA.decode(metadata_bytes)
            member_metadata[member_id] = metadata
            all_subscribed_topics.update(metadata.subscription) # pylint: disable-msg=no-member

        # the leader will begin watching for changes to any of the topics
        # the group is interested in, which ensures that all metadata changes
        # will eventually be seen
        # Because assignment typically happens within response callbacks,
        # we cannot block on metadata updates here (no recursion into poll())
        self._subscription.group_subscribe(all_subscribed_topics)
        self._client.set_topics(self._subscription.group_subscription())

        log.debug("Performing %s assignment for subscriptions %s",
                  assignor.name, member_metadata)

        assignments = assignor.assign(self._cluster, member_metadata)

        log.debug("Finished assignment: %s", assignments)

        group_assignment = {}
        for member_id, assignment in six.iteritems(assignments):
            group_assignment[member_id] = assignment
        return group_assignment

    def _on_join_prepare(self, generation, member_id):
        # commit offsets prior to rebalance if auto-commit enabled
        self._maybe_auto_commit_offsets_sync()

        # execute the user's callback before rebalance
        log.debug("Revoking previously assigned partitions %s",
                  self._subscription.assigned_partitions())
        if self._subscription.listener:
            try:
                revoked = set(self._subscription.assigned_partitions())
                self._subscription.listener.on_partitions_revoked(revoked)
            except Exception:
                log.exception("User provided subscription listener failed"
                              " on_partitions_revoked")

        self._subscription.mark_for_reassignment()

    def need_rejoin(self):
        """Check whether the group should be rejoined

        Returns:
            bool: True if consumer should rejoin group, False otherwise
        """
        return (self._subscription.partitions_auto_assigned() and
               (super(ConsumerCoordinator, self).need_rejoin() or
                self._subscription.needs_partition_assignment))

    def refresh_committed_offsets_if_needed(self):
        """Fetch committed offsets for assigned partitions."""
        if self._subscription.needs_fetch_committed_offsets:
            offsets = self.fetch_committed_offsets(self._subscription.assigned_partitions())
            for partition, offset in six.iteritems(offsets):
                # verify assignment is still active
                if self._subscription.is_assigned(partition):
                    self._subscription.assignment[partition].committed = offset.offset
            self._subscription.needs_fetch_committed_offsets = False

    def fetch_committed_offsets(self, partitions):
        """Fetch the current committed offsets for specified partitions

        Arguments:
            partitions (list of TopicPartition): partitions to fetch

        Returns:
            dict: {TopicPartition: OffsetAndMetadata}
        """
        while True:
            self.ensure_coordinator_known()

            # contact coordinator to fetch committed offsets
            future = self._send_offset_fetch_request(partitions)
            self._client.poll(future=future)

            if future.succeeded():
                return future.value

            if not future.retriable():
                raise future.exception # pylint: disable-msg=raising-bad-type

            time.sleep(self._retry_backoff_ms / 1000.0)

    def ensure_partition_assignment(self):
        """Ensure that we have a valid partition assignment from the coordinator."""
        if self._subscription.partitions_auto_assigned():
            self.ensure_active_group()

    def close(self):
        try:
            self._maybe_auto_commit_offsets_sync()
        finally:
            super(ConsumerCoordinator, self).close()

    def commit_offsets_async(self, offsets, callback=None):
        """Commit specific offsets asynchronously.

        Arguments:
            offsets (dict {TopicPartition: OffsetAndMetadata}): what to commit
            callback (callable, optional): called as callback(offsets, response)
                response will be either an Exception or a OffsetCommitResponse
                struct. This callback can be used to trigger custom actions when
                a commit request completes.
        Returns:
            Future: indicating whether the commit was successful or not
        """
        self._subscription.needs_fetch_committed_offsets = True
        future = self._send_offset_commit_request(offsets)
        cb = callback if callback else self._default_offset_commit_callback
        future.add_both(cb, offsets)

    def commit_offsets_sync(self, offsets):
        """Commit specific offsets synchronously.

        This method will retry until the commit completes successfully or an
        unrecoverable error is encountered.

        Arguments:
            offsets (dict {TopicPartition: OffsetAndMetadata}): what to commit

        Raises error on failure
        """
        if not offsets:
            return

        while True:
            self.ensure_coordinator_known()

            future = self._send_offset_commit_request(offsets)
            self._client.poll(future=future)

            if future.succeeded():
                return

            if not future.retriable():
                raise future.exception # pylint: disable-msg=raising-bad-type

            time.sleep(self._retry_backoff_ms / 1000.0)

    def _maybe_auto_commit_offsets_sync(self):
        if self._enable_auto_commit:
            # disable periodic commits prior to committing synchronously. note that they will
            # be re-enabled after a rebalance completes
            self._auto_commit_task.disable()

            try:
                self.commit_offsets_sync(self._subscription.all_consumed_offsets())

            # The three main group membership errors are known and should not
            # require a stacktrace -- just a warning
            except (Errors.UnknownMemberIdError,
                    Errors.IllegalGenerationError,
                    Errors.RebalanceInProgressError):
                log.warning("Offset commit failed: group membership out of date"
                            " This is likely to cause duplicate message"
                            " delivery.")
            except Exception:
                log.exception("Offset commit failed: This is likely to cause"
                              " duplicate message delivery")

    def _send_offset_commit_request(self, offsets):
        """Commit offsets for the specified list of topics and partitions.

        This is a non-blocking call which returns a request future that can be
        polled in the case of a synchronous commit or ignored in the
        asynchronous case.

        Arguments:
            offsets (dict of {TopicPartition: OffsetAndMetadata}): what should
                be committed

        Returns:
            Future: indicating whether the commit was successful or not
        """
        if self.coordinator_unknown():
            return Future().failure(Errors.GroupCoordinatorNotAvailableError)

        if not offsets:
            return Future().failure(None)

        # create the offset commit request
        offset_data = collections.defaultdict(dict)
        for tp, offset in six.iteritems(offsets):
            offset_data[tp.topic][tp.partition] = offset

        request = OffsetCommitRequest_v2(
            self.group_id,
            self.generation,
            self.member_id,
            OffsetCommitRequest_v2.DEFAULT_RETENTION_TIME,
            [(
                topic, [(
                    partition,
                    offset.offset,
                    offset.metadata
                ) for partition, offset in six.iteritems(partitions)]
            ) for topic, partitions in six.iteritems(offset_data)]
        )

        log.debug("Sending offset-commit request with %s to %s",
                  offsets, self.coordinator_id)

        future = Future()
        _f = self._client.send(self.coordinator_id, request)
        _f.add_callback(self._handle_offset_commit_response, offsets, future)
        _f.add_errback(self._failed_request, future)
        return future

    def _handle_offset_commit_response(self, offsets, future, response):
        #self.sensors.commit_latency.record(response.requestLatencyMs())
        unauthorized_topics = set()

        for topic, partitions in response.topics:
            for partition, error_code in partitions:
                tp = TopicPartition(topic, partition)
                offset = offsets[tp]

                error_type = Errors.for_code(error_code)
                if error_type is Errors.NoError:
                    log.debug("Committed offset %s for partition %s", offset, tp)
                    if self._subscription.is_assigned(tp):
                        self._subscription.assignment[tp].committed = offset.offset
                elif error_type is Errors.GroupAuthorizationFailedError:
                    log.error("OffsetCommit failed for group %s - %s",
                              self.group_id, error_type.__name__)
                    future.failure(error_type(self.group_id))
                    return
                elif error_type is Errors.TopicAuthorizationFailedError:
                    unauthorized_topics.add(topic)
                elif error_type in (Errors.OffsetMetadataTooLargeError,
                                    Errors.InvalidCommitOffsetSizeError):
                    # raise the error to the user
                    log.info("OffsetCommit failed for group %s on partition %s"
                             " due to %s, will retry", self.group_id, tp,
                             error_type.__name__)
                    future.failure(error_type())
                    return
                elif error_type is Errors.GroupLoadInProgressError:
                    # just retry
                    log.info("OffsetCommit failed for group %s because group is"
                             " initializing (%s), will retry", self.group_id,
                             error_type.__name__)
                    future.failure(error_type(self.group_id))
                    return
                elif error_type in (Errors.GroupCoordinatorNotAvailableError,
                                    Errors.NotCoordinatorForGroupError,
                                    Errors.RequestTimedOutError):
                    log.info("OffsetCommit failed for group %s due to a"
                             " coordinator error (%s), will find new coordinator"
                             " and retry", self.group_id, error_type.__name__)
                    self.coordinator_dead()
                    future.failure(error_type(self.group_id))
                    return
                elif error_type in (Errors.UnknownMemberIdError,
                                    Errors.IllegalGenerationError,
                                    Errors.RebalanceInProgressError):
                    # need to re-join group
                    error = error_type(self.group_id)
                    log.error("OffsetCommit failed for group %s due to group"
                              " error (%s), will rejoin", self.group_id, error)
                    self._subscription.mark_for_reassignment()
                    # Errors.CommitFailedError("Commit cannot be completed due to group rebalance"))
                    future.failure(error)
                    return
                else:
                    log.error("OffsetCommit failed for group % on partition %s"
                              " with offset %s: %s", tp, offset,
                              error_type.__name__)
                    future.failure(error_type())
                    return

        if unauthorized_topics:
            log.error("OffsetCommit failed for unauthorized topics %s",
                      unauthorized_topics)
            future.failure(Errors.TopicAuthorizationFailedError(unauthorized_topics))
        else:
            future.success(True)

    def _send_offset_fetch_request(self, partitions):
        """Fetch the committed offsets for a set of partitions.

        This is a non-blocking call. The returned future can be polled to get
        the actual offsets returned from the broker.

        Arguments:
            partitions (list of TopicPartition): the partitions to fetch

        Returns:
            Future: resolves to dict of offsets: {TopicPartition: int}
        """
        if self.coordinator_unknown():
            return Future().failure(Errors.GroupCoordinatorNotAvailableError)

        log.debug("Fetching committed offsets for partitions: %s", partitions)
        # construct the request
        topic_partitions = collections.defaultdict(set)
        for tp in partitions:
            topic_partitions[tp.topic].add(tp.partition)
        request = OffsetFetchRequest_v1(
            self.group_id,
            list(topic_partitions.items())
        )

        # send the request with a callback
        future = Future()
        _f = self._client.send(self.coordinator_id, request)
        _f.add_callback(self._handle_offset_fetch_response, future)
        _f.add_errback(self._failed_request, future)
        return future

    def _handle_offset_fetch_response(self, future, response):
        offsets = {}
        for topic, partitions in response.topics:
            for partition, offset, metadata, error_code in partitions:
                tp = TopicPartition(topic, partition)
                error_type = Errors.for_code(error_code)
                if error_type is not Errors.NoError:
                    error = error_type()
                    log.debug("Error fetching offset for %s: %s", tp, error_type())
                    if error_type is Errors.GroupLoadInProgressError:
                        # just retry
                        future.failure(error)
                    elif error_type is Errors.NotCoordinatorForGroupError:
                        # re-discover the coordinator and retry
                        self.coordinator_dead()
                        future.failure(error)
                    elif error_type in (Errors.UnknownMemberIdError,
                                        Errors.IllegalGenerationError):
                        # need to re-join group
                        self._subscription.mark_for_reassignment()
                        future.failure(error)
                    else:
                        log.error("Unknown error fetching offsets for %s: %s",
                                  tp, error)
                        future.failure(error)
                    return
                elif offset >= 0:
                    # record the position with the offset (-1 indicates no committed offset to fetch)
                    offsets[tp] = OffsetAndMetadata(offset, metadata)
                else:
                    log.debug("No committed offset for partition %s", tp)
        future.success(offsets)


class AutoCommitTask(object):
    def __init__(self, coordinator, interval):
        self._coordinator = coordinator
        self._client = coordinator._client
        self._interval = interval
        self._enabled = False
        self._request_in_flight = False

    def enable(self):
        if self._enabled:
            log.warning("AutoCommitTask is already enabled")
            return

        self._enabled = True
        if not self._request_in_flight:
            self._client.schedule(self, time.time() + self._interval)

    def disable(self):
        self._enabled = False
        try:
            self._client.unschedule(self)
        except KeyError:
            pass

    def _reschedule(self, at):
        if self._enabled:
            self._client.schedule(self, at)
        else:
            raise Errors.IllegalStateError('AutoCommitTask not enabled')

    def __call__(self):
        if not self._enabled:
            return

        if self._coordinator.coordinator_unknown():
            log.debug("Cannot auto-commit offsets because the coordinator is"
                      " unknown, will retry after backoff")
            next_at = time.time() + self._coordinator._retry_backoff_ms / 1000.0
            self._client.schedule(self, next_at)
            return

        self._request_in_flight = True
        self._coordinator.commit_offsets_async(
            self._coordinator._subscription.all_consumed_offsets(),
            self._handle_commit_response)

    def _handle_commit_response(self, offsets, result):
        self._request_in_flight = False
        if result is True:
            log.debug("Successfully auto-committed offsets")
            next_at = time.time() + self._interval
        elif not isinstance(result, BaseException):
            raise Errors.IllegalStateError(
                'Unrecognized result in _handle_commit_response: %s'
                % result)
        elif hasattr(result, 'retriable') and result.retriable:
            log.debug("Failed to auto-commit offsets: %s, will retry"
                      " immediately", result)
            next_at = time.time()
        else:
            log.warning("Auto offset commit failed: %s", result)
            next_at = time.time() + self._interval

        if not self._enabled:
            log.warning("Skipping auto-commit reschedule -- it is disabled")
            return
        self._reschedule(next_at)


# TODO
"""
class ConsumerCoordinatorMetrics(object):
    def __init__(self, metrics, prefix, tags):
        self.metrics = metrics
        self.group_name = prefix + "-coordinator-metrics"

        self.commit_latency = metrics.sensor("commit-latency")
        self.commit_latency.add(metrics.MetricName(
            "commit-latency-avg", self.group_name,
            "The average time taken for a commit request",
            tags), metrics.Avg())
        self.commit_latency.add(metrics.MetricName(
            "commit-latency-max", self.group_name,
            "The max time taken for a commit request",
            tags), metrics.Max())
        self.commit_latency.add(metrics.MetricName(
            "commit-rate", self.group_name,
            "The number of commit calls per second",
            tags), metrics.Rate(metrics.Count()))

        '''
        def _num_partitions(config, now):
            new Measurable() {
                public double measure(MetricConfig config, long now) {
                    return subscriptions.assignedPartitions().size();
                }
            };
        metrics.addMetric(new MetricName("assigned-partitions",
            this.metricGrpName,
            "The number of partitions currently assigned to this consumer",
            tags),
            numParts);
        '''
"""
