from carrot.connection import DjangoAMQPConnection
from celery.log import setup_logger
from celery.registry import tasks
from celery.messaging import TaskPublisher, TaskConsumer
from celery.models import TaskMeta
from django.core.cache import cache
from datetime import timedelta
from celery.backends import default_backend
from celery.datastructures import PositionQueue
from celery.result import AsyncResult
from celery.timer import TimeoutTimer
import uuid
import pickle


def delay_task(task_name, *args, **kwargs):
    """Delay a task for execution by the ``celery`` daemon.

        >>> delay_task("update_record", name="George Constanza", age=32)

    """
    if task_name not in tasks:
        raise tasks.NotRegistered(
                "Task with name %s not registered in the task registry." % (
                    task_name))
    publisher = TaskPublisher(connection=DjangoAMQPConnection())
    task_id = publisher.delay_task(task_name, *args, **kwargs)
    publisher.close()
    return AsyncResult(task_id)


def discard_all():
    """Discard all waiting tasks.

    This will ignore all tasks waiting for execution, and they will
    be deleted from the messaging server.

    Returns the number of tasks discarded.

    """
    consumer = TaskConsumer(connection=DjangoAMQPConnection())
    discarded_count = consumer.discard_all()
    consumer.close()
    return discarded_count


def mark_as_done(task_id, result):
    """Mark task as done (executed)."""
    return default_backend.mark_as_done(task_id, result)


def mark_as_failure(task_id, exc):
    """Mark task as done (executed)."""
    return default_backend.mark_as_failure(task_id, exc)


def is_done(task_id):
    """Returns ``True`` if task with ``task_id`` has been executed."""
    return default_backend.is_done(task_id)


class Task(object):
    """A task that can be delayed for execution by the ``celery`` daemon.

    All subclasses of ``Task`` has to define the ``name`` attribute, which is
    the name of the task that can be passed to ``celery.task.delay_task``,
    it also has to define the ``run`` method, which is the actual method the
    ``celery`` daemon executes.
    
    This is a simple task just logging a message,

        >>> from celery.task import tasks, Task
        >>> class MyTask(Task):
        ...     name = "mytask"
        ...
        ...     def run(self, some_arg=None, **kwargs):
        ...         logger = self.get_logger(**kwargs)
        ...         logger.info("Running MyTask with arg some_arg=%s" %
        ...                     some_arg))
        ...         return 42
        ... tasks.register(MyTask)

    You can delay the task using the classmethod ``delay``...

        >>> result = MyTask.delay(some_arg="foo")
        >>> result.status # after some time
        'DONE'
        >>> result.result
        42

    ...or using the ``celery.task.delay_task`` function, by passing the
    name of the task.

        >>> from celery.task import delay_task
        >>> delay_task(MyTask.name, some_arg="foo")

    """
    name = None
    type = "regular"
    max_retries = 0 # unlimited
    retry_interval = timedelta(seconds=2)
    auto_retry = False

    def __init__(self):
        if not self.name:
            raise NotImplementedError("Tasks must define a name attribute.")

    def __call__(self, *args, **kwargs):
        """The ``__call__`` is called when you do ``Task().run()`` and calls
        the ``run`` method. It also catches any exceptions and logs them."""
        return self.run(*args, **kwargs)

    def run(self, *args, **kwargs):
        """The actual task. All subclasses of :class:`Task` must define
        the run method, if not a ``NotImplementedError`` exception is raised.
        """
        raise NotImplementedError("Tasks must define a run method.")

    def get_logger(self, **kwargs):
        """Get a process-aware logger object."""
        return setup_logger(**kwargs)

    def get_publisher(self):
        """Get a celery task message publisher."""
        return TaskPublisher(connection=DjangoAMQPConnection())

    def get_consumer(self):
        """Get a celery task message consumer."""
        return TaskConsumer(connection=DjangoAMQPConnection())

    def requeue(self, task_id, args, kwargs):
        self.get_publisher().requeue_task(self.name, task_id, args, kwargs)

    def retry(self, task_id, args, kwargs):
        retry_queue.put(self.name, task_id, args, kwargs)

    @classmethod
    def delay(cls, *args, **kwargs):
        """Delay this task for execution by the ``celery`` daemon(s)."""
        return delay_task(cls.name, *args, **kwargs)


class TaskSet(object):
    """A task containing several subtasks, making it possible
    to track how many, or when all of the tasks are completed.
    
        >>> from djangofeeds.tasks import RefreshFeedTask
        >>> taskset = TaskSet(RefreshFeedTask, args=[
        ...                 {"feed_url": "http://cnn.com/rss"},
        ...                 {"feed_url": "http://bbc.com/rss"},
        ...                 {"feed_url": "http://xkcd.com/rss"}])

        >>> taskset_id, subtask_ids = taskset.run()
        

    """

    def __init__(self, task, args):
        """``task`` can be either a fully qualified task name, or a task
        class, args is a list of arguments for the subtasks.
        """

        try:
            task_name = task.name
        except AttributeError:
            task_name = task

        self.task_name = task_name
        self.arguments = args
        self.total = len(args)

    def run(self):
        """Run all tasks in the taskset.

        Returns a tuple with the taskset id, and a list of subtask id's.

            >>> ts = RefreshFeeds([
            ...         ["http://foo.com/rss", {}],
            ...         ["http://bar.com/rss", {}],
            ... )
            >>> taskset_id, subtask_ids = ts.run()
            >>> taskset_id
            "d2c9b261-8eff-4bfb-8459-1e1b72063514"
            >>> subtask_ids
            ["b4996460-d959-49c8-aeb9-39c530dcde25",
            "598d2d18-ab86-45ca-8b4f-0779f5d6a3cb"]
            >>> time.sleep(10)
            >>> is_done(taskset_id)
            True
        """
        taskset_id = str(uuid.uuid4())
        publisher = TaskPublisher(connection=DjangoAMQPConnection())
        subtask_ids = []
        for arg, kwarg in self.arguments:
            subtask_id = publisher.delay_task_in_set(task_name=self.task_name,
                                                     taskset_id=taskset_id,
                                                     task_args=arg,
                                                     task_kwargs=kwarg)
            subtask_ids.append(subtask_id) 
        publisher.close()
        return taskset_id, subtask_ids

    def iterate(self):
        """Iterate over the results returned after calling ``run()``.
        
        If any of the tasks raises an exception, the exception will
        be reraised by ``iterate``.
        """
        taskset_id, subtask_ids = self.run()
        results = dict([(task_id, AsyncResult(task_id))
                            for task_id in subtask_ids])
        while results:
            for task_id, pending_result in results.items():
                if pending_result.status == "DONE":
                    del(results[task_id])
                    yield pending_result.result
                elif pending_result.status == "FAILURE":
                    raise pending_result.result

    def join(self, timeout=None):
        """Gather the results for all of the tasks in the taskset,
        and return a list with them ordered by the order of which they
        were called.

        If any of the tasks raises an exception, the exception
        will be reraised by ``join``.

        If ``timeout`` is not ``None`` and the operation takes
        longer than ``timeout`` seconds, it will raise
        the :class:`celery.timer.TimeoutError` exception.

        """
        timeout_timer = TimeoutTimer(timeout) # Timeout timer starts here.
        taskset_id, subtask_ids = self.run()
        pending_results = map(AsyncResult, subtask_ids)
        results = PositionQueue(length=len(subtask_ids))

        while True:
            for position, pending_result in enumerate(pending_results):
                if pending_result.status == "DONE":
                    results[position] = pending_result.result
                elif pending_result.status == "FAILURE":
                    raise pending_result.result
            if results.full():
                # Make list copy, so the returned type is not a position
                # queue.
                return list(results)

            # This raises TimeoutError when timed out.
            timeout_timer.tick()

    @classmethod
    def remote_execute(cls, func, args):
        """Apply ``args`` to function by distributing the args to the
        celery server(s)."""
        pickled = pickle.dumps(func)
        arguments = [[[pickled, arg, {}], {}] for arg in args]
        return cls(ExecuteRemoteTask, arguments)

    @classmethod
    def map(cls, func, args, timeout=None):
        """Distribute processing of the arguments and collect the results."""
        remote_task = cls.remote_execute(func, args)
        return remote_task.join(timeout=timeout)

    @classmethod
    def map_async(cls, func, args, timeout=None):
        """Distribute processing of the arguments and collect the results
        asynchronously.
        
        Returns :class:`celery.result.AsyncResult` instance.
        
        """
        serfunc = pickle.dumps(func)
        return AsynchronousMapTask.delay(serfunc, args, timeout=timeout)


def dmap(func, args, timeout=None):
    """Distribute processing of the arguments and collect the results.

        >>> from celery.task import map
        >>> import operator
        >>> dmap(operator.add, [[2, 2], [4, 4], [8, 8]])
        [4, 8, 16]

    """
    return TaskSet.map(func, args, timeout=timeout)


class AsynchronousMapTask(Task):
    """Task used internally by ``dmap_async``."""
    name = "celery.map_async"

    def run(self, serfunc, args, **kwargs):
        timeout = kwargs.get("timeout")
        return TaskSet.map(pickle.loads(serfunc), args, timeout=timeout)
tasks.register(AsynchronousMapTask)


def dmap_async(func, args, timeout=None):
    """Distribute processing of the arguments and collect the results
    asynchronously.
    
    Returns a :class:`celery.result.AsyncResult` object.

        >>> from celery.task import dmap_async
        >>> import operator
        >>> presult = dmap_async(operator.add, [[2, 2], [4, 4], [8, 8]])
        >>> presult
        <AsyncResult: 373550e8-b9a0-4666-bc61-ace01fa4f91d>
        >>> presult.status
        'DONE'
        >>> presult.result
        [4, 8, 16]

    """
    return TaskSet.map_async(func, args, timeout=timeout)


class PeriodicTask(Task):
    """A periodic task is a task that behaves like a cron job.

    The ``run_every`` attribute defines how often the task is run (its
    interval), it can be either a ``datetime.timedelta`` object or a integer
    specifying the time in seconds.

    You have to register the periodic task in the task registry.

        >>> from celery.task import tasks, PeriodicTask
        >>> from datetime import timedelta
        >>> class MyPeriodicTask(PeriodicTask):
        ...     name = "my_periodic_task"
        ...     run_every = timedelta(seconds=30)
        ...
        ...     def run(self, **kwargs):
        ...         logger = self.get_logger(**kwargs)
        ...         logger.info("Running MyPeriodicTask")
        >>> tasks.register(MyPeriodicTask)

    """
    run_every = timedelta(days=1)
    type = "periodic"

    def __init__(self):
        if not self.run_every:
            raise NotImplementedError(
                    "Periodic tasks must have a run_every attribute")

        # If run_every is a integer, convert it to timedelta seconds.
        if isinstance(self.run_every, int):
            self.run_every = timedelta(seconds=self.run_every)

        super(PeriodicTask, self).__init__()


class ExecuteRemoteTask(Task):
    """Execute arbitrary function/object.

    The object must be pickleable, so you can't use lambdas or functions
    defined in the REPL.
    
    """
    name = "celery.execute_remote"

    def run(self, ser_callable, fargs, fkwargs, **kwargs):
        """Execute the pickled ``ser_callable``, with ``fargs`` as positional
        arguments and ``fkwargs`` as keyword arguments."""
        callable_ = pickle.loads(ser_callable)
        return callable_(*fargs, **fkwargs)
tasks.register(ExecuteRemoteTask)


def execute_remote(func, *args, **kwargs):
    """Execute arbitrary function/object remotely.

    The object must be picklable, so you can't use lambdas or functions
    defined in the REPL (the objects must have an associated module).
    
    """
    return ExecuteRemoteTask.delay(pickle.dumps(func), args, kwargs)


class DeleteExpiredTaskMetaTask(PeriodicTask):
    """A periodic task that deletes expired task metadata every day.

    This runs the current backend's cleanup() method.
    """
    name = "celery.delete_expired_task_meta"
    run_every = timedelta(days=1)

    def run(self, **kwargs):
        logger = self.get_logger(**kwargs)
        logger.info("Deleting expired task meta objects...")
        default_backend.cleanup()
tasks.register(DeleteExpiredTaskMetaTask)
