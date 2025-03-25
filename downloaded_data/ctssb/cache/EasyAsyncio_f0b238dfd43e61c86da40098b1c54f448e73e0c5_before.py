import abc
import asyncio
import logging
from abc import abstractmethod
from asyncio import (AbstractEventLoop, Semaphore, Future, Queue,
                     QueueFull, CancelledError)
from collections import deque, Counter
from time import time
from typing import (Set, Any, MutableMapping, TYPE_CHECKING, Dict,
                    Optional)

import attr
from aiohttp import ServerDisconnectedError
from diskcache import Deque, Index

from .cachetypes import CacheSet, EvictingIndex
from .context import Context
from .helper import hash

if TYPE_CHECKING:
    from . import DataManager

check_mark = '\N{WHITE HEAVY CHECK MARK}'
x_mark = '\N{CROSS MARK}'


def color_cyan(skk):
    return "\033[96m {}\033[00m".format(skk)


def color_green(skk):
    return "\033[92m {}\033[00m".format(skk)


def color_red(skk):
    return "\033[91m {}\033[00m".format(skk)


class Job(abc.ABC):
    tasks: Set[Future]
    max_concurrent: int
    context: Context
    loop: AbstractEventLoop
    sem: Semaphore
    end_time: float
    input_data: Any
    fail_cache_name = 'failed'
    data: 'DataManager'
    primary = False
    fail_string_length = 0
    success_string_length = 0
    result_justify = 0
    input_justify = 0

    def __init__(self,
                 input_data=None,
                 max_concurrent=20,
                 max_queue_size=0,
                 cache_name='completed',
                 continuous=False,
                 enable_cache=True,
                 auto_add_results=True,
                 queue_cache_name='resume',
                 product_name='successes',
                 log_level=logging.INFO,
                 auto_requeue=True,
                 exit_on_queue_finish=True,
                 print_successes=False) -> None:
        """

        Args:

            input_data (Any): Starting data to work on that is usually loaded
                from a file
            max_concurrent (int): The maximum number of workers
            max_queue_size (int): The maximum items the queue can hold at once
            cache_name (str): The name of the cache to save completed data to.
                This will default to **self.name**
            continuous (bool): Whether the predecessor of this Job should end
                this Job when its queue is empty
            queue_cache_name (str): The name to save the queue_cache as
            product_name (str): The item that this job produces
            auto_requeue (bool): Automatically re-add certain failed items
                back into queue
            exit_on_queue_finish (bool): Exit when self.queue_finished is
                called
            print_successes (bool): Whether to automatically print success
                information
        See Also: :class:`OutputJob` :class:`ForwardQueuingJob`
            :class:`BackwardQueuingJob`
        """
        self.log_level = log_level
        self.auto_add_results = auto_add_results
        self.input_data = input_data
        self.max_concurrent = max_concurrent
        self.stats = Counter()
        self.tasks = set()
        self.info: Dict[str, Any] = {
                'max_queue_size': ('infinite' if max_queue_size == 0
                                   else max_queue_size),
                'max_workers':    max_concurrent,
                'workers':        0
        }
        self.logs: deque[str] = deque(maxlen=50)
        self.log = logging.getLogger(self.name)
        self.with_errors = False
        self.running = False
        self.max_queue_size = max_queue_size
        self.cache_name = cache_name
        self.queue_cache_name = queue_cache_name
        self.cache_enabled = enable_cache
        self.continuous = continuous
        self.result_name = product_name
        self.auto_requeue = auto_requeue
        self.exit_on_queue_finish = exit_on_queue_finish

        self.queue_looped = False
        self.finished = False
        self.last_queue_item_grab_time = time()
        self.min_idle_time_before_finish = 5
        self.predecessor: 'Optional[Job]' = None
        self.successor: 'Optional[Job]' = None
        self.print_successes = print_successes

        if len(self.__class__.__name__) > 15:
            self.log.warning(
                    '[WARNING] Class names greater than 15 characters '
                    'will cause logger formatting bugs.')

    @property
    def queue(self) -> Queue:
        return self.context.queues.get(self.name)

    @property
    def queue_cache(self) -> CacheSet:
        """
        A cache built for resuming any progress made when any Job is
        restarted.
        """
        return self.data.get_job_cache(self, self.queue_cache_name)

    @property
    def failed_inputs(self) -> CacheSet:
        """
        This cache will store all of the queued item that returned a value that
        is False
        """
        return self.get_data('%s.failed' % self.name)

    @property
    def name(self):
        return self.__class__.__name__

    def initialize(self, context: Context):
        """
        Set all of the context-dependent variables

        This is called during manager.add_job(...) and needs to be called
        before this class can access any property from **self.context**
        """
        self._initialize_variables(context)
        self.context.jobs.add(self)
        self._initialize_config()
        self.status('initialized')
        self.log.info('loading cached items...')
        if self.cache_enabled:
            context.data.register_job_cache(self, dict(), self.cache_name)
        self.data.register_cache('%s.failed' % self.name, set(),
                                 './data/failed/%s.txt' % self.name)

    def _initialize_config(self):
        self.context.queues.new(self.name)
        self.sem = Semaphore(self.max_concurrent, loop=self.loop)
        self.log.addHandler(JobLogHandler(self, level=self.log_level))

    def _initialize_variables(self, context):
        self.context = context
        self.data = context.data
        self.loop = context.loop

    async def run(self):
        """setup workers and start"""
        self.log.debug('starting...')
        self.running = True
        try:
            self.create_workers()
        except Exception:
            self.log.error('Failed to create workers.')
            raise
        else:
            # fill queue
            self.status('filling queue')
            self.log.debug('creating queue task...')
            await self._create_queue_tasks()
            # process
            self.status('working')
            try:
                await asyncio.gather(*self.tasks, loop=self.loop,
                                     return_exceptions=False)
            except CancelledError:
                pass
            except Exception as e:
                self.log.exception(e)
                raise
        finally:
            self.running = False
            await self.on_finish()

    async def _create_queue_tasks(self):
        if (isinstance(self, ForwardQueuingJob)
                or isinstance(self, OutputJob) and self.input_data):
            queue_task = self.loop.create_task(self.fill_queue())
            self.tasks.add(queue_task)
        queue_watcher_task = self.loop.create_task(self.queue_watcher())
        self.tasks.add(queue_watcher_task)

    async def fill_queue(self):
        """implement the queue filling logic here"""
        for d in self.input_data:
            if d in self.failed_inputs:
                continue
            await self.add_to_queue(d)
            await asyncio.sleep(0)
        await self.filled_queue()

    def create_workers(self):
        self.status('creating workers')
        self.log.debug('creating workers...')
        for _ in range(self.max_concurrent):
            self.tasks.add(self.loop.create_task(self.worker(_)))

    async def worker(self, num: int):
        """
        Get each item from the queue and pass it to **self.do_work.**

        This is the main event loop for each worker. The worker will wait
        until an item is available in **self.queue**, then do what ever logic
        is present in the abstract method **self.do_work()**
        This method will also handle caching and will pass finished data
        to post_process() for further action

        See Also self.do_work()
        """
        self.info['workers'] += 1
        self.log.debug('[worker%s] started', num)
        while self.context.running:
            result = None
            self.status('waiting on queue')
            queued_data = await self.queue.get()
            self.last_queue_item_grab_time = time()
            self.log.debug('[worker%s] retrieved queued data "%s"',
                           num, queued_data)
            self.status('working')
            if isinstance(queued_data, QueueLooped):
                self.queue_looped = True
                continue
            if queued_data is False:
                break
            if queued_data in self.failed_inputs:
                continue
            if self.cache_enabled:
                result = self.deindex(queued_data)
                if result:
                    output = self.get_formatted_output(result)
                    if not self.print_successes:
                        self.log.info(
                                check_mark + '[Cache] Input: %s Output: %s ',
                                queued_data, output)
            # noinspection PyBroadException
            try:
                result = result if result is not None else await self.do_work(
                        queued_data)
                self.queue.task_done()
            except CancelledError:
                self.log.debug('work on %s has been cancelled', queued_data)
                break
            except ServerDisconnectedError:
                self.log.error('server disconnected')
                await self.queue.put(queued_data)
            except FailResponse as fr:
                self.increment_stat(name=fr.reason)
                self.failed_inputs.add(queued_data)
                self.print_failed(fr.reason, queued_data)
                self.queue.task_done()
            except RequeueResponse as rr:
                if self.auto_requeue:
                    await self.queue.put(queued_data)
                    self.increment_stat(name=rr.reason)
                self.print_failed(rr.reason, queued_data)
            except NoRequeueResponse as nrr:
                self.increment_stat(name=nrr.reason)

                self.print_failed(nrr.reason, queued_data)
                # self.log.info(x_mark + '[No Requeue][%s] %s', nrr.reason,
                #               queued_data)
                self.log.debug('%s NoRequeue reason: %s', queued_data,
                               nrr.reason)
                self.queue.task_done()
            except UnknownResponse as ur:
                self.diag_save(ur.diagnostics)
                self.print_failed(ur.reason, queued_data)
                if ur.extra_info:
                    self.log.info('❌%s', ur.extra_info)
                self.increment_stat(name=ur.reason)
                self.queue.task_done()
            except Exception:
                self.increment_stat(name='uncaught-exceptions')
                self.log.exception('worker uncaught exception: %s',
                                   dict(queued_data=queued_data))
                self.with_errors = True
                self.queue.task_done()
            else:
                await self._on_work_processed(queued_data, result)
            finally:
                self.increment_stat(name='attempted')

        self.info['workers'] -= 1
        self.log.debug('[worker%s] terminated', num)

    async def _on_work_processed(self, input_data, result):
        if self.cache_enabled:
            self.index(input_data, result)
        if self.auto_add_results:
            await self._post_process(result)
        if self.print_successes:
            self.print_success(input_data, result)

    def print_success(self, input_data, result):
        if len(repr(input_data)) > self.input_justify:
            self.input_justify = len(repr(input_data))
        output = self.get_formatted_output(result)
        if len(repr(output)) > self.result_justify:
            self.result_justify = len(repr(output))
        success_colored = color_green('[Success]')
        if len(success_colored) > self.success_string_length:
            self.success_string_length = len(success_colored)
        success_colored = success_colored.ljust(self.fail_string_length)
        input_colored = color_cyan('Input')
        input_data_formatted = str(input_data).ljust(self.input_justify)
        i_len = len(input_data_formatted)
        max_str_len = 45
        if i_len > max_str_len:
            input_data_formatted = input_data_formatted[:max_str_len] + '...'
        output_data_formatted = output.ljust(self.result_justify)
        self.log.info(check_mark + '%s %s: %s %s: %s',
                      success_colored,
                      input_colored,
                      input_data_formatted,
                      color_cyan('Output'),
                      output_data_formatted)

    def print_failed(self, reason, queued_data: str):
        string = '%s %s' % (color_cyan('Input:'), queued_data)
        failed_string = color_red('[%s]' % reason.capitalize())
        if len(failed_string) > self.fail_string_length:
            self.fail_string_length = len(failed_string)
        formatted = '%s%s %s' % (
                x_mark, failed_string.ljust(
                        max(self.fail_string_length,
                            self.success_string_length)),
                string)
        self.log.info(formatted)

    @abstractmethod
    async def do_work(self, input_data) -> object:
        """
        Do business logic on each enqueued item and returns the completed data.

        This method should not be called directly.

        This method should return an object or raise type of Response on
        completion.
        If the work fails in a predicted way and is expected to continue to
        fail, this method should raise a FailedResponse.
        If the work fails in a predicted way and needs to be requeued, it
        should raise a RequeueResponse.
        If the work fails in a predicted way and should not be requeued, it
        should raise a NoRequeueResponse
        If the work fails in an unexpected way, it should raise a
        UnknownResponse and have a Diagnostics object passed to it with the
        fail information

        All completed items will be added to the queue if self.cache_enabled is
        set to true. Completed items will then be passed to _post_process for
        further processing.

        See Also :class:`Job.worker`
        """

    async def _post_process(self, obj):
        if (isinstance(obj,
                       (list, set)) and not isinstance(
                obj, str)):
            for o in obj:
                await self.on_item_completed(o)
                await asyncio.sleep(0)
            self.log.debug('finished postprocessing %s items', len(obj))
        elif isinstance(obj, MutableMapping):
            for t in obj.items():
                await self.on_item_completed(t)
                await asyncio.sleep(0)
            self.log.debug('finished postprocessing %s items', len(obj))
        else:
            await self.on_item_completed(obj)

    @abstractmethod
    async def on_item_completed(self, obj):
        """Called after post-processing is finished"""

    async def on_finish(self):
        """Called when all tasks are finished"""
        self.finished = True
        self.end_time = time()
        self.status('finished')
        self.log.debug('finished!')
        if self.with_errors:
            self.log.warning('Some errors occurred. See logs')

    async def filled_queue(self):
        self.log.debug('finished queueing')
        await self.queue.put(QueueLooped())

    async def queue_finished(self):
        """Tells this Job to stop watching the queue and close"""
        for index in range(self.info['workers']):
            try:
                await self.add_to_queue(False)
            except QueueFull:
                while not self.queue.empty():
                    await self.queue.get()

    async def add_to_queue(self, obj):
        if obj is False:
            optional = obj
        else:
            optional = await self.queue_filter(obj)
        if optional is not None:
            await self.queue.put(optional)

    # noinspection PyMethodMayBeStatic
    async def queue_filter(self, obj):
        """All items added to the queue must fulfil this requirement"""
        if obj in self.failed_inputs:
            return None
        return obj

    async def requeue(self, obj, reason=''):
        await self.queue.put(obj)
        if 'requeued' not in self.info:
            self.info['requeued'] = Counter()
        self.info.get('requeued')[reason or 'unspecified'] += 1

    def index(self, input_data, result):
        hash_id = input_data if isinstance(input_data, (str, int)) else hash(
                input_data)
        self.data.get_job_cache(self, self.cache_name)[hash_id] = result

    def deindex(self, input_data):
        hash_id = input_data if isinstance(input_data, (str, int)) else hash(
                input_data)
        return self.data.get_job_cache(self, self.cache_name).get(hash_id)

    def increment_stat(self, n=1, name: str = None) -> None:
        """increment the count of whatever this Job is processing"""
        self.stats[name or self.result_name] += n

    def status(self, *strings: str):
        status = ' '.join(
                [str(s) if not isinstance(s, str) else s for s in strings])
        self.info['status'] = status

    def time_left(self):
        elapsed_time = self.context.stats.elapsed_time
        per_second = self.context.stats[self.name] / elapsed_time
        return round((self.queue.qsize()) / per_second)

    def get_data(self, name):
        return self.data.get(name)

    def diag_save(self, diag: 'Diagnostics', name=None):
        """
        Save useful diagnostic information
        """
        name = name or str(time()).replace('.', '')
        json = dict(content=diag.content, input_data=diag.input_data,
                    extras=diag.extras or {}, timestamp=time())
        path = f'./diagnostics/{self.name}/{name}{diag.extension}'
        self.data.register(name, json, path, False, False)
        self.log.info(
                'saved diagnostic info for %s -> %s' % (diag.input_data, path))

    def get_formatted_output(self, obj) -> str:
        return (f'{len(obj)} {self.result_name}'
                if isinstance(obj, (list, set, dict)) else str(obj))

    def get_formatted_input(self, obj) -> str:
        return obj

    def set_primary(self):
        self.primary = True

    @abstractmethod
    async def queue_watcher(self):
        pass

    @property
    def idle(self):
        return self.queue.qsize() == 0 and self.info.get(
                'status') == 'waiting on queue'

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class ForwardQueuingJob(Job, abc.ABC):
    """
    This :class:`Job` will pass all items completed to its successor for
    further processing
    """

    def __init__(self, successor: Job, **kwargs) -> None:
        """

        Args:
            successor (Job): The Job that will receive this Job's completed
                data
        """
        super().__init__(**kwargs)
        self.successor = successor
        self.successor.predecessor = self
        self.info['precedes'] = successor
        successor.info['supersedes'] = self

    async def on_item_completed(self, obj):
        if self.successor.max_queue_size:
            while (self.successor.queue.qsize()
                   >= self.successor.max_queue_size):
                self.status('paused')
                await asyncio.sleep(10)
        await self.queue_successor(obj)
        self.increment_stat(name=self.result_name)

    async def queue_successor(self, data):
        await self.successor.add_to_queue(data)

    async def filled_queue(self):
        await super().filled_queue()
        self.log.debug('adding QueueLooped() to successor')
        await self.successor.queue.put(QueueLooped())

    async def queue_watcher(self):
        self.log.debug('starting queue watcher')
        while self.context.running:
            await asyncio.sleep(0.5)
            if (not self.queue_looped
                    or not self.idle
                    or not self.queue.empty()):
                continue
            predecessor_not_finished = (self.predecessor
                                        and not self.predecessor.finished)
            successor_not_finished = (self.successor
                                      and isinstance(self.successor,
                                                     BackwardQueuingJob)
                                      and not self.successor.finished)
            if predecessor_not_finished or successor_not_finished:
                continue
            if (time() - self.last_queue_item_grab_time
                    > self.min_idle_time_before_finish):
                await self.queue_finished()
                break


class BackwardQueuingJob(Job, abc.ABC):
    """
    This :class:`Job` will pass all items completed to its predecessor for
    further processing
    """

    def __init__(self, predecessor: Job, **kwargs) -> None:
        """

        Args:
            predecessor (Job, Optional): The queue that passes completed data
                to this Job
            **kwargs:
        """
        kwargs.setdefault('cache_queued_items', True)
        super().__init__(**kwargs)
        self.predecessor = predecessor
        self.predecessor.successor = self
        self.info['supersedes'] = predecessor

    async def on_item_completed(self, obj):
        if self.predecessor and self.predecessor.max_queue_size:
            while (self.predecessor.queue.qsize()
                   >= self.predecessor.max_queue_size):
                self.status('paused')
                await asyncio.sleep(10)
        await self.queue_predecessor(obj)
        self.increment_stat(name=self.result_name)

    async def queue_predecessor(self, data):
        await self.predecessor.queue.put(data)

    async def queue_watcher(self):
        self.log.debug('starting queue watcher')
        while self.context.running:
            await asyncio.sleep(0.5)
            if not self.queue_looped or not self.idle:
                continue
            if self.predecessor and not self.predecessor.finished:
                continue
            await self.queue_finished()
            break


class OutputJob(Job, abc.ABC):
    """This :class:`Job` will pass all completed items to an output file"""

    def __init__(self, output: Optional[str] = '', **kwargs) -> None:
        self.output = output
        super().__init__(**kwargs)

    def initialize(self, context: Context):
        super().initialize(context)
        self.log.info('starting with %s items in output',
                      len(self.get_data(self.output)))

    async def on_item_completed(self, o):
        if not self.output:
            self.log.info(o)
        cache = self.get_data(self.output)
        if not o not in cache:
            self.increment_stat()
        if isinstance(cache, (CacheSet, set)):
            cache.add(o)
        elif isinstance(cache, (Deque, list)):
            cache.append(o)
        elif isinstance(cache, (Index, MutableMapping, EvictingIndex)):
            key, value = o
            cache[key] = value

    async def queue_watcher(self):
        self.log.debug('starting queue watcher')
        while self.context.running:
            await asyncio.sleep(0.5)
            if not self.queue_looped or not self.idle:
                continue
            if self.predecessor and not self.predecessor.finished:
                continue
            if (time() - self.last_queue_item_grab_time
                    > self.min_idle_time_before_finish):
                await self.queue_finished()
                break


class JobLogHandler(logging.Handler):
    """This will handle all messages passed via :class:`Job.log`"""

    def __init__(self, worker: Job,
                 level=logging.DEBUG) -> None:
        super().__init__(level)
        self.worker = worker

    def emit(self, record: logging.LogRecord) -> None:
        self.worker.logs.append(record.getMessage())


class QueueLooped:
    pass


class Response(Exception):
    reason: str

    def __init__(self, reason, *args: object) -> None:
        super().__init__(*args)
        self.reason = reason


class RequeueResponse(Response):
    """Processing did not return meaning data, and it will be added to the
     queue for reprocessing."""

    def __init__(self, reason='requeued', *args: object) -> None:
        super().__init__(reason, *args)


class FailResponse(Response):
    """Processing failed and will consistently fail so it will not be added
    back to the queue and will not be processed in the future."""

    def __init__(self, reason='failed', *args: object) -> None:
        super().__init__(reason, *args)


class NoRequeueResponse(Response):
    """Processing did not return a value, but will not be requeued during this
    session. However it will be added on the next run."""

    def __init__(self, reason='temporarily-failed', *args: object) -> None:
        super().__init__(reason, *args)


class UnknownResponse(Response):
    def __init__(self, diagnostics: 'Diagnostics', reason='unknown',
                 extra_info='', *args: object) -> None:
        super().__init__(reason, *args)
        self.diagnostics = diagnostics
        self.extra_info = extra_info


@attr.s(auto_attribs=True)
class Diagnostics:
    """Save response information for diagnostics and debugging"""
    content: object
    input_data: object
    extras: dict = {}
    extension: str = '.json'
