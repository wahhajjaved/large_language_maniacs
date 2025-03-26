from traceback import format_exc

from mesh.exceptions import *
from scheme import current_timestamp
from spire.schema import *
from spire.support.logs import LogHelper
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm.collections import attribute_mapped_collection

from platoon.constants import *
from platoon.queue import ThreadPackage
from platoon.models.action import ProcessAction
from platoon.models.queue import Queue
from platoon.models.scheduledtask import ScheduledTask
from platoon.resources.process import InitiationResponse

log = LogHelper('platoon')
schema = Schema('platoon')

class Process(Model):
    """A process."""

    class meta:
        schema = schema
        tablename = 'process'

    id = Identifier()
    queue_id = ForeignKey('queue.id', nullable=False)
    executor_endpoint_id = ForeignKey('executor_endpoint.id')
    tag = Text(nullable=False)
    timeout = Integer()
    status = Enumeration('pending executing aborted completed failed timedout',
        nullable=False, default='pending')
    input = Json()
    output = Json()
    progress = Json()
    started = DateTime(timezone=True)
    ended = DateTime(timezone=True)
    communicated = DateTime(timezone=True)

    executor_endpoint = relationship('ExecutorEndpoint',
        backref=backref('processes', lazy='dynamic'))
    queue = relationship(Queue, backref=backref('processes', lazy='dynamic'))
    tasks = association_proxy('process_tasks', 'task',
        creator=lambda k, v: ProcessTask(phase=k, task=v))

    @property
    def endpoint(self):
        return self.executor_endpoint.endpoint

    @property
    def executor(self):
        return self.executor_endpoint.executor

    def abandon(self, session):
        session.refresh(self, lockmode='update')
        if self.status != 'executing':
            return

        self.verify(session, True)
        if self.status != 'executing':
            return

        self.status = 'timedout'
        self._schedule_task(session, 'report-timeout-to-executor', limit=10)
        self._schedule_task(session, 'report-timeout-to-queue', limit=10)

    def abort(self, session):
        session.refresh(self, lockmode='update')
        if self.status not in ('pending', 'executing'):
            return

        self.status = 'aborted'
        self._schedule_task(session, 'report-abortion', limit=10)

    def complete(self, session, output=None, bypass_checks=False):
        if not bypass_checks:
            session.refresh(self, lockmode='update')
            if self.status != 'executing':
                return

        self.status = 'completed'
        self.completed = current_timestamp()
        self.output = output
        self._schedule_task(session, 'report-completion', limit=10)

    @classmethod
    def create(cls, session, queue_id, **attrs):
        try:
            queue = Queue.load(session, id=queue_id)
        except NoResultFound:
            raise OperationError(token='invalid-queue-id')

        process = cls(queue_id=queue_id, **attrs)
        session.add(process)

        process.executor_endpoint = queue.assign_executor_endpoint(session)
        if not process.executor_endpoint:
            raise OperationError(token='no-executor-available')

        process._schedule_task(session, 'initiate-process')
        return process

    def fail(self, session, bypass_checks=False):
        if not bypass_checks:
            session.refresh(self, lockmode='update')
            if self.status != 'executing':
                return

        self.status = 'failed'
        self._schedule_task(session, 'report-failure', limit=10)

    def initiate_process(self, session):
        session.refresh(self, lockmode='update')
        if self.status != 'pending':
            return

        self.started = current_timestamp()
        payload = self._construct_payload(input=self.input)

        try:
            response = InitiationResponse.process(self.endpoint.request(payload))
        except Exception, exception:
            log('exception', 'initiation of %s failed', repr(self))
            return self.fail(session, True)

        self.status = response['status']
        if self.status == 'completed':
            self.complete(session, response.get('output'), True)

    @classmethod
    def process_processes(cls, taskqueue, session):
        occurrence = current_timestamp()
        query = session.query(cls).with_lockmode('update').filter(
            cls.timeout != None, (cls.started + cls.timeout) < occurrence)

    def report_abortion(self):
        payload = self._construct_payload(status='aborted')
        self.endpoint.request(payload)

    def report_completion(self):
        payload = self._construct_payload(status='completed', output=self.output)
        self.queue.endpoint.request(payload)

    def report_failure(self):
        payload = self._construct_payload(status='failed')
        self.queue.endpoint.request(payload)

    def report_progress(self):
        payload = self._construct_payload(status='executing', progress=self.progress)
        self.queue.endpoint.request(payload)

    def report_timeout_to_executor(self):
        payload = self._construct_payload(status='timedout')
        self.endpoint.request(payload)

    def report_timeout_to_queue(self):
        payload = self._construct_payload(status='timedout')
        self.queue.endpoint.request(payload)

    def update(self, session, status=None, output=None, progress=None):
        if status == 'aborted':
            self.abort(session)
        elif status == 'completed':
            self.complete(session, output)
        elif progress:
            self.progress = progress
            self._schedule_task(session, 'report-progress', limit=3)

    def verify(self, session, bypass_checks=False):
        if not bypass_checks:
            session.refresh(self, lockmode='update')
            if self.status != 'executing':
                return

        payload = self._construct_payload(status='executing')
        try:
            response = InitiationResponse.process(self.endpoint.request(payload))
        except Exception:
            return self.fail(session, True)

        self.communicated = current_timestamp()
        if response['status'] == 'completed':
            return self.complete(session, response.get('output'), True)

    def _construct_payload(self, **params):
        params.update(id=self.id, tag=self.tag)
        return params

    def _schedule_task(self, session, action, delta=None, limit=0, timeout=120, backoff=1.4):
        self.tasks[action] = ScheduledTask.create(session,
            tag='%s:%s' % (action, self.tag),
            action=ProcessAction(process_id=self.id, action=action),
            delta=delta,
            retry_limit=limit,
            retry_timeout=timeout,
            retry_backoff=backoff)

class ProcessTask(Model):
    """A process task."""

    class meta:
        constraints = [UniqueConstraint('process_id', 'task_id', 'phase')]
        schema = schema
        tablename = 'process_task'

    id = Identifier()
    process_id = ForeignKey('process.id', nullable=False, ondelete='CASCADE')
    task_id = ForeignKey('scheduled_task.task_id', nullable=False)
    phase = Enumeration(PROCESS_TASK_ACTIONS, nullable=False)

    process = relationship(Process, backref=backref('process_tasks',
        collection_class=attribute_mapped_collection('phase'),
        cascade='all,delete-orphan', passive_deletes=True))
    task = relationship(ScheduledTask, cascade='all,delete-orphan', single_parent=True)
