from __future__ import print_function

import zmq
import socket
import dill
import uuid
from collections import defaultdict
import itertools
from multiprocessing.pool import ThreadPool
import random
from datetime import datetime
from threading import Thread, Lock
from contextlib import contextmanager
import traceback
import sys
from time import sleep
from ..compatibility import Queue, unicode, Empty
try:
    import cPickle as pickle
except ImportError:
    import pickle

from ..core import get_dependencies, flatten
from .. import core
from ..async import finish_task, start_state_from_dask as dag_state_from_dask

with open('log.scheduler', 'w') as f:  # delete file
    pass

def log(*args):
    with open('log.scheduler', 'a') as f:
        print(*args, file=f)

@contextmanager
def logerrors():
    try:
        yield
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = ''.join(traceback.format_tb(exc_traceback))
        log('Error!', str(e))
        log('Traceback', str(tb))
        raise

class Scheduler(object):
    """ Disitributed scheduler for dask computations

    Parameters
    ----------

    hostname: string
        hostname or IP address of this machine visible to outside world
    port_to_workers: int
        Port on which to listen to connections from workers
    port_to_clients: int
        Port on which to listen to connections from clients
    bind_to_workers: string
        Addresses from which we accept worker connections, defaults to *
    bind_to_clients: string
        Addresses from which we accept client connections, defaults to *
    block: bool
        Whether or not to block the process on creation

    State
    -----

    workers - dict
        Maps worker identities to information about that worker
    who_has - dict
        Maps data keys to sets of workers that own that data
    worker_has - dict
        Maps workers to data that they own
    data - dict
        Maps data keys to metadata about the computation that produced it
    to_workers - zmq.Socket (ROUTER)
        Socket to communicate to workers
    to_clients - zmq.Socket (ROUTER)
        Socket to communicate with users
    collections - dict
        Dict holding shared collections like bags and arrays
    """
    def __init__(self, port_to_workers=None, port_to_clients=None,
                 bind_to_workers='*', bind_to_clients='*',
                 hostname=None, block=False):
        self.context = zmq.Context()
        hostname = hostname or socket.gethostname()

        # Bind routers to addresses (and create addresses if necessary)
        self.to_workers = self.context.socket(zmq.ROUTER)
        if port_to_workers is None:
            port_to_workers = self.to_workers.bind_to_random_port('tcp://' + bind_to_workers)
        else:
            self.to_workers.bind('tcp://%s:%d' % (bind_to_workers, port_to_workers))
        self.address_to_workers = ('tcp://%s:%d' % (hostname, port_to_workers)).encode()

        self.to_clients = self.context.socket(zmq.ROUTER)
        if port_to_clients is None:
            port_to_clients = self.to_clients.bind_to_random_port('tcp://' + bind_to_clients)
        else:
            self.to_clients.bind('tcp://%s:%d' % (bind_to_clients, port_to_clients))
        self.address_to_clients = ('tcp://%s:%d' % (hostname, port_to_clients)).encode()

        # State about my workers and computed data
        self.workers = dict()
        self.who_has = defaultdict(set)
        self.worker_has = defaultdict(set)
        self.available_workers = Queue()
        self.data = defaultdict(dict)
        self.collections = dict()

        self.pool = ThreadPool(100)
        self.lock = Lock()
        self.status = 'run'
        self.queues = dict()

        self._schedule_lock = Lock()

        # RPC functions that workers and clients can trigger
        self.worker_functions = {'register': self._worker_registration,
                                 'status': self._status_to_worker,
                                 'finished-task': self._worker_finished_task,
                                 'setitem-ack': self._setitem_ack,
                                 'getitem-ack': self._getitem_ack}
        self.client_functions = {'status': self._status_to_client,
                                 'schedule': self._schedule_from_client,
                                 'set-collection': self._set_collection,
                                 'get-collection': self._get_collection,
                                 'close-workers': self._close_workers,
                                 'close': self._close}

        # Away we go!
        log(self.address_to_workers, 'Start')
        self._listen_to_workers_thread = Thread(target=self._listen_to_workers)
        self._listen_to_workers_thread.start()
        self._listen_to_clients_thread = Thread(target=self._listen_to_clients)
        self._listen_to_clients_thread.start()

        if block:
            self.block()

    def _listen_to_workers(self):
        """ Event loop: Listen to worker router """
        while self.status != 'closed':
            try:
                if not self.to_workers.poll(100):
                    continue
            except zmq.ZMQError:
                break
            address, header, payload = self.to_workers.recv_multipart()

            header = pickle.loads(header)
            if 'address' not in header:
                header['address'] = address
            log(self.address_to_workers, 'Receive job from worker', header)

            try:
                function = self.worker_functions[header['function']]
            except KeyError:
                log(self.address_to_workers, 'Unknown function', header)
            else:
                future = self.pool.apply_async(function, args=(header, payload))

    def _listen_to_clients(self):
        """ Event loop: Listen to client router """
        while self.status != 'closed':
            try:
                if not self.to_clients.poll(100):
                    continue
            except zmq.ZMQError:
                break
            address, header, payload = self.to_clients.recv_multipart()
            header = pickle.loads(header)
            if 'address' not in header:
                header['address'] = address
            log(self.address_to_clients, 'Receive job from client', header)

            try:
                function = self.client_functions[header['function']]
            except KeyError:
                log(self.address_to_clients, 'Unknown function', header)
            else:
                self.pool.apply_async(function, args=(header, payload))

    def block(self):
        """ Block until listener threads close

        Warning: If some other thread doesn't call `.close()` then, in the
        common case you can not easily escape from this.
        """
        self._listen_to_workers_thread.join()
        self._listen_to_clients_thread.join()

    def _worker_registration(self, header, payload):
        """ Worker came in, register them """
        payload = pickle.loads(payload)
        address = header['address']
        self.workers[address] = payload
        self.available_workers.put(address)

    def _worker_finished_task(self, header, payload):
        """ Worker reports back as having finished task, ready for more

        See also:
            Scheduler.trigger_task
            Scheduler.schedule
        """
        with logerrors():
            address = header['address']

            payload = pickle.loads(payload)
            key = payload['key']
            duration = payload['duration']
            dependencies = payload['dependencies']

            log(self.address_to_workers, 'Finish task', payload)

            for dep in dependencies:
                self.who_has[dep].add(address)
                self.worker_has[address].add(dep)
            self.available_workers.put(address)

            if isinstance(payload['status'], Exception):
                self.queues[payload['queue']].put(payload)
            else:
                self.data[key]['duration'] = duration
                self.who_has[key].add(address)
                self.worker_has[address].add(key)

                self.queues[payload['queue']].put(payload)

    def _status_to_client(self, header, payload):
        with logerrors():
            out_header = {'jobid': header.get('jobid')}
            log(self.address_to_clients, 'Status')
            self.send_to_client(header['address'], out_header, 'OK')

    def _status_to_worker(self, header, payload):
        out_header = {'jobid': header.get('jobid')}
        log(self.address_to_workers, 'Status sending')
        self.send_to_worker(header['address'], out_header, 'OK')

    def send_to_worker(self, address, header, payload):
        """ Send packet to worker """
        log(self.address_to_workers, 'Send to worker', address, header)
        header['address'] = self.address_to_workers
        loads = header.get('loads', pickle.loads)
        dumps = header.get('dumps', pickle.dumps)
        if isinstance(address, unicode):
            address = address.encode()
        header['timestamp'] = datetime.utcnow()
        with self.lock:
            self.to_workers.send_multipart([address,
                                            pickle.dumps(header),
                                            dumps(payload)])

    def send_to_client(self, address, header, result):
        """ Send packet to client """
        log(self.address_to_clients, 'Send to client', address, header)
        header['address'] = self.address_to_clients
        loads = header.get('loads', pickle.loads)
        dumps = header.get('dumps', pickle.dumps)
        if isinstance(address, unicode):
            address = address.encode()
        header['timestamp'] = datetime.utcnow()
        with self.lock:
            self.to_clients.send_multipart([address,
                                            pickle.dumps(header),
                                            dumps(result)])

    def trigger_task(self, dsk, key, queue):
        """ Send a single task to the next available worker

        See also:
            Scheduler.schedule
            Scheduler.worker_finished_task
        """
        deps = get_dependencies(dsk, key)
        worker = self.available_workers.get()
        locations = dict((dep, self.who_has[dep]) for dep in deps)

        header = {'function': 'compute', 'jobid': key,
                  'dumps': dill.dumps, 'loads': dill.loads}
        payload = {'key': key, 'task': dsk[key], 'locations': locations,
                   'queue': queue}
        self.send_to_worker(worker, header, payload)

    def release_key(self, key):
        """ Release data from all workers

        Example
        -------

        >>> scheduler.release_key('x')  # doctest: +SKIP

        Protocol
        --------

        This sends a 'delitem' request to all workers known to have this key.
        This operation is fire-and-forget.  Local indices will be updated
        immediately.
        """
        with logerrors():
            workers = list(self.who_has[key])
            log(self.address_to_workers, 'Release data', key, workers)
            header = {'function': 'delitem', 'jobid': key}
            payload = {'key': key}
            for worker in workers:
                self.send_to_worker(worker, header, payload)
                self.who_has[key].remove(worker)
                self.worker_has[worker].remove(key)

    def send_data(self, key, value, address=None, reply=True):
        """ Send data up to some worker

        If no address is given we select one worker randomly

        Example
        -------

        >>> scheduler.send_data('x', 10)  # doctest: +SKIP
        >>> scheduler.send_data('x', 10, 'tcp://bob:5000', reply=False)  # doctest: +SKIP

        Protocol
        --------

        1.  Scheduler makes a queue
        2.  Scheduler selects a worker at random (or uses prespecified worker)
        3.  Scheduler sends 'setitem' operation to that worker
            {'key': ..., 'value': ..., 'queue': ...}
        4.  Worker gets data and stores locally, send 'setitem-ack'
            {'key': ..., 'queue': ...}
        5.  Scheduler gets from queue, send_data cleans up queue and returns

        See also:
            Scheduler.setitem_ack
            Worker.setitem
            Scheduler.scatter
        """
        if reply:
            queue = Queue()
            qkey = str(uuid.uuid1())
            self.queues[qkey] = queue
        else:
            qkey = None
        if address is None:
            address = random.choice(list(self.workers))
        header = {'function': 'setitem', 'jobid': key}
        payload = {'key': key, 'value': value, 'queue': qkey}
        self.send_to_worker(address, header, payload)

        if reply:
            queue.get()
            del self.queues[qkey]

    def scatter(self, key_value_pairs, block=True):
        """ Scatter data to workers

        Parameters
        ----------

        key_value_pairs: Iterator or dict
            Data to send
        block: bool
            Block on completion or return immediately (defaults to True)

        Example
        -------

        >>> scheduler.scatter({'x': 1, 'y': 2})  # doctest: +SKIP

        Protocol
        --------

        1.  Scheduler starts up a uniquely identified queue.
        2.  Scheduler sends 'setitem' requests to workers with
            {'key': ..., 'value': ... 'queue': ...}
        3.  Scheduler waits on queue for all responses
        3.  Workers receive 'setitem' requests, send back on 'setitem-ack' with
            {'key': ..., 'queue': ...}
        4.  Scheduler's 'setitem-ack' function pushes keys into the queue
        5.  Once the same number of replies is heard scheduler scatter function
            returns
        6.  Scheduler cleans up queue

        See Also:
            Scheduler.setitem_ack
            Worker.setitem_scheduler
        """
        workers = list(self.workers)
        log(self.address_to_workers, 'Scatter', workers, key_value_pairs)
        workers = itertools.cycle(workers)

        if isinstance(key_value_pairs, dict):
            key_value_pairs = key_value_pairs.items()
        queue = Queue()
        qkey = str(uuid.uuid1())
        self.queues[qkey] = queue
        counter = 0
        for (k, v), w in zip(key_value_pairs, workers):
            header = {'function': 'setitem', 'jobid': k}
            payload = {'key': k, 'value': v}
            if block:
                payload['queue'] = qkey
            self.send_to_worker(w, header, payload)
            counter += 1

        if block:
            for i in range(counter):
                queue.get()

            del self.queues[qkey]

    def gather(self, keys):
        """ Gather data from workers

        Parameters
        ----------

        keys: key, list of keys, nested list of lists of keys
            Keys to collect from workers

        Example
        -------

        >>> scheduler.gather('x')  # doctest: +SKIP
        >>> scheduler.gather([['x', 'y'], ['z']])  # doctest: +SKIP

        Protocol
        --------

        1.  Scheduler starts up a uniquely identified queue.
        2.  Scheduler sends 'getitem' requests to workers with payloads
            {'key': ...,  'queue': ...}
        3.  Scheduler waits on queue for all responses
        3.  Workers receive 'getitem' requests, send data back on 'getitem-ack'
            {'key': ..., 'value': ..., 'queue': ...}
        4.  Scheduler's 'getitem-ack' function pushes key/value pairs onto queue
        5.  Once the same number of replies is heard the gather function
            collects data into form specified by keys input and returns
        6.  Scheduler cleans up queue before returning

        See Also:
            Scheduler.getitem_ack
            Worker.getitem_scheduler
        """
        qkey = str(uuid.uuid1())
        queue = Queue()
        self.queues[qkey] = queue

        # Send of requests
        self._gather_send(qkey, keys)

        # Wait for replies
        cache = dict()
        for i in flatten(keys):
            k, v = queue.get()
            cache[k] = v
        del self.queues[qkey]

        # Reshape to keys
        return core.get(cache, keys)

    def _gather_send(self, qkey, key):
        if isinstance(key, list):
            for k in key:
                self._gather_send(qkey, k)
        else:
            header = {'function': 'getitem', 'jobid': key}
            payload = {'key': key, 'queue': qkey}
            seq = list(self.who_has[key])
            worker = random.choice(seq)
            self.send_to_worker(worker, header, payload)

    def _getitem_ack(self, header, payload):
        """ Receive acknowledgement from worker about a getitem request

        See also:
            Scheduler.gather
            Worker.getitem
        """
        payload = pickle.loads(payload)
        log(self.address_to_workers, 'Getitem ack', payload)
        with logerrors():
            assert header['status'] == 'OK'
            self.queues[payload['queue']].put((payload['key'],
                                               payload['value']))

    def _setitem_ack(self, header, payload):
        """ Receive acknowledgement from worker about a setitem request

        See also:
            Scheduler.scatter
            Worker.setitem
        """
        address = header['address']
        payload = pickle.loads(payload)
        key = payload['key']
        self.who_has[key].add(address)
        self.worker_has[address].add(key)
        queue = payload.get('queue')
        if queue:
            self.queues[queue].put(key)

    def _close_workers(self, header, payload):
        self.close_workers()

    def _close(self, header, payload):
        self._close()

    def close_workers(self):
        header = {'function': 'close'}
        for w in self.workers:
            self.send_to_worker(w, header, {})

    def close(self):
        """ Close Scheduler """
        self.status = 'closed'
        self.to_workers.close(linger=1)
        self.to_clients.close(linger=1)
        self.pool.close()
        self.pool.join()
        self.block()
        self.context.destroy(linger=3)

    def schedule(self, dsk, result, **kwargs):
        """ Execute dask graph against workers

        Parameters
        ----------

        dsk: dict
            Dask graph
        result: list
            keys to return (possibly nested)

        Example
        -------

        >>> scheduler.get({'x': 1, 'y': (add, 'x', 2)}, 'y')  # doctest: +SKIP
        3

        Protocol
        --------

        1.  Scheduler scatters precomputed data in graph to workers
            e.g. nodes like ``{'x': 1}``.  See Scheduler.scatter
        2.
        """
        with self._schedule_lock:
            log(self.address_to_workers, "Scheduling dask")
            if isinstance(result, list):
                result_flat = set(flatten(result))
            else:
                result_flat = set([result])
            results = set(result_flat)

            cache = dict()
            dag_state = dag_state_from_dask(dsk, cache=cache)
            if cache:
                self.scatter(cache.items())  # send data in dask up to workers

            tick = [0]

            if dag_state['waiting'] and not dag_state['ready']:
                raise ValueError("Found no accessible jobs in dask graph")

            event_queue = Queue()
            qkey = str(uuid.uuid1())
            self.queues[qkey] = event_queue

            def fire_task():
                tick[0] += 1  # Update heartbeat

                # Choose a good task to compute
                key = dag_state['ready'].pop()
                dag_state['ready-set'].remove(key)
                dag_state['running'].add(key)

                self.trigger_task(dsk, key, qkey)  # Fire

            try:
                worker = self.available_workers.get(timeout=20)
                self.available_workers.put(worker)  # put him back in
            except Empty:
                raise ValueError("Waited 20 seconds. No workers found")

            # Seed initial tasks
            while dag_state['ready'] and self.available_workers.qsize() > 0:
                fire_task()

            # Main loop, wait on tasks to finish, insert new ones
            while dag_state['waiting'] or dag_state['ready'] or dag_state['running']:
                payload = event_queue.get()

                if isinstance(payload['status'], Exception):
                    raise payload['status']

                key = payload['key']
                finish_task(dsk, key, dag_state, results,
                            release_data=self._release_data)

                while dag_state['ready'] and self.available_workers.qsize() > 0:
                    fire_task()

            result2 = self.gather(result)
            for key in flatten(result):  # release result data from workers
                self.release_key(key)
        return result2

    def _schedule_from_client(self, header, payload):
        """

        Input Payload: keys, dask
        Output Payload: keys, result
        Sent to client on 'schedule-ack'
        """
        with logerrors():
            loads = header.get('loads', dill.loads)
            payload = loads(payload)
            address = header['address']
            dsk = payload['dask']
            keys = payload['keys']

            header2 = {'jobid': header.get('jobid'),
                       'function': 'schedule-ack'}
            try:
                result = self.schedule(dsk, keys)
                header2['status'] = 'OK'
            except Exception as e:
                result = e
                header2['status'] = 'Error'

            payload2 = {'keys': keys, 'result': result}
            self.send_to_client(address, header2, payload2)

    def _release_data(self, key, state, delete=True):
        """ Remove data from temporary storage during scheduling run

        See Also
            Scheduler.schedule
            dask.async.finish_task
        """
        if key in state['waiting_data']:
            assert not state['waiting_data'][key]
            del state['waiting_data'][key]

        state['released'].add(key)

        if delete:
            self.release_key(key)

    def _set_collection(self, header, payload):
        with logerrors():
            log(self.address_to_clients, "Set collection", header)
            payload = header.get('loads', dill.loads)(payload)
            self.collections[payload['name']] = payload

            self.send_to_client(header['address'], {'status': 'OK'}, {})

    def _get_collection(self, header, payload):
        with logerrors():
            log(self.address_to_clients, "Get collection", header)
            payload = header.get('loads', pickle.loads)(payload)
            payload2 = self.collections[payload['name']]

            header2 = {'status': 'OK',
                       'loads': dill.loads,
                       'dumps': dill.dumps}

            self.send_to_client(header['address'], header2, payload2)
