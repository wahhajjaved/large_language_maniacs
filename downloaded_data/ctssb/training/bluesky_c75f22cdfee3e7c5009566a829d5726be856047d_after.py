import time as ttime
import sys
from itertools import count
from collections import namedtuple, deque, defaultdict
import uuid
import signal
import threading
from queue import Queue, Empty
import numpy as np
import types
from utils import CallbackRegistry, SignalHandler

import lmfit
from lmfit.models import GaussianModel, LinearModel



beamline_id='test'
owner='tester'
custom = {}
scan_id = 123


class Msg(namedtuple('Msg_base', ['command', 'obj', 'args', 'kwargs'])):
    __slots__ = ()

    def __new__(cls, command, obj=None, *args, **kwargs):
        return super(Msg, cls).__new__(cls, command, obj, args, kwargs)

    def __repr__(self):
        return '{}: ({}), {}, {}'.format(
            self.command, self.obj, self.args, self.kwargs)


class Base:
    def __init__(self, name, fields):
        self._name = name
        self._fields = fields

    def describe(self):
        return {k: {'source': self._name, 'dtype': 'number'}
                for k in self._fields}

    def __repr__(self):
        return '{}: {}'.format(self._klass, self._name)


class Reader(Base):
    _klass = 'reader'

    def __init__(self, *args, **kwargs):
        super(Reader, self).__init__(*args, **kwargs)
        self._cnt = 0

    def read(self):
        data = dict()
        for k in self._fields:
            data[k] = {'value': self._cnt, 'timestamp': ttime.time()}
            self._cnt += 1

        return data

    def trigger(self):
        pass


class Mover(Base):
    _klass = 'mover'

    def __init__(self, *args, **kwargs):
        super(Mover, self).__init__(*args, **kwargs)
        self._data = {k: {'value': 0, 'timestamp': ttime.time()}
                      for k in self._fields}
        self._staging = None
        self.is_moving = False

    def read(self):
        return dict(self._data)

    def set(self, new_values):
        if set(new_values) - set(self._data):
            raise ValueError('setting non-existent field')
        self._staging = new_values

    def trigger(self, *, block_group=None):
        # block_group is handled by the RunEngine
        self.is_moving = True
        ttime.sleep(0.1)  # simulate moving time
        if self._staging:
            for k, v in self._staging.items():
                self._data[k] = {'value': v, 'timestamp': ttime.time()}

        self.is_moving = False
        self._staging = None

    def settle(self):
        pass


class SynGauss(Reader):
    """
    Evaluate a point on a Gaussian based on the value of a motor.

    Example
    -------
    motor = Mover('motor', ['pos'])
    det = SynGauss('sg', motor, 'pos', center=0, Imax=1, sigma=1)
    """
    _klass = 'reader'

    def __init__(self, name, motor, motor_field, center, Imax, sigma=1):
        super(SynGauss, self).__init__(name, 'I')
        self._motor = motor
        self._motor_field = motor_field
        self.center = center
        self.Imax = Imax
        self.sigma = sigma

    def trigger(self):
        m = self._motor._data[self._motor_field]['value']
        v = self.Imax * np.exp(-(m - self.center)**2 / (2 * self.sigma**2))
        self._data = {'intensity': {'value': v, 'timestamp': ttime.time()}}

    def read(self):
        return self._data


class FlyMagic(Base):
    def kickoff(self):
        pass

    def collect(self):
        pass


def MoveRead_gen(motor, detector):
    try:
        for j in range(10):
            yield Msg('create')
            yield Msg('set', motor, ({'x': j}, ))
            yield Msg('trigger', motor)
            yield Msg('trigger', detector)
            yield Msg('read', detector)
            yield Msg('read', motor)
            yield Msg('save')
    finally:
        print('Generator finished')


def SynGauss_gen(syngaus, motor_steps, motor_limit=None):
    try:
        for x in motor_steps:
            yield Msg('create')
            yield Msg('set', syngaus, ({syngaus.motor_name: x}, ))
            yield Msg('trigger', syngaus)
            yield Msg('sleep', None, (.1,))
            ret = yield Msg('read', syngaus)
            yield Msg('save')
            if motor_limit is not None:
                if ret[syngaus.motor_name] > motor_limit:
                    break
    finally:
        print('generator finished')


def find_center_gen(syngaus, initial_center, initial_width,
                    output_mutable):
    tol = .01
    seen_x = deque()
    seen_y = deque()

    for x in np.linspace(initial_center - initial_width,
                         initial_center + initial_center,
                         5, endpoint=True):
        yield Msg('set', syngaus, ({syngaus.motor_name: x}, ))
        yield Msg('trigger', syngaus)
        yield Msg('sleep', None, (.1, ))
        ret = yield Msg('read', syngaus)
        seen_x.append(ret[syngaus.motor_name])
        seen_y.append(ret[syngaus.det_name])
    model = GaussianModel() + LinearModel()
    guesses = {'amplitude': np.max(seen_y),
               'center': initial_center,
               'sigma': initial_width,
               'slope': 0, 'intercept': 0}
    while True:
        x = np.asarray(seen_x)
        y = np.asarray(seen_y)
        res = model.fit(y, x=x, **guesses)
        old_guess = guesses
        guesses = res.values

        if np.abs(old_guess['center'] - guesses['center']) < tol:
            break

        yield Msg('set', syngaus, ({syngaus.motor_name: guesses['center']}, ))
        yield Msg('trigger', syngaus)
        yield Msg('sleep', None, (.1, ))
        ret = yield Msg('read', syngaus)
        seen_x.append(ret[syngaus.motor_name])
        seen_y.append(ret[syngaus.det_name])

    output_mutable.update(guesses)


class RunEngine:
    def __init__(self):
        self.panic = False
        self._sigint_handler = None
        self._objs_read = deque()  # objects read in one Event
        self._read_cache = deque()  # cache of obj.read() in one Event
        self._describe_cache = dict()  # cache of all obj.describe() output
        self._descriptor_uids = dict()  # cache of all Descriptor uids
        self._sequence_counters = dict()  # a seq_num counter per Descriptor
        self._block_groups = defaultdict(set)  # sets of objs to wait for
        self._temp_callback_ids = set()  # ids from CallbackRegistry
        self._command_registry = {
            'create': self._create,
            'save': self._save,
            'read': self._read,
            'null': self._null,
            'set': self._set,
            'trigger': self._trigger,
            'sleep': self._sleep,
            'wait': self._wait
            }

        # queues for passing Documents from "scan thread" to main thread
        queue_names = ['start', 'stop', 'event', 'descriptor']
        self._queues = {name: Queue() for name in queue_names}

        # public dispatcher for callbacks processed on the main thread
        self.dispatcher = Dispatcher(self._queues)
        self.subscribe = self.dispatcher.subscribe
        self.unsubscribe = self.dispatcher.unsubscribe

        # For why this function is necessary, see
        # http://stackoverflow.com/a/13355291/1221924
        def make_push_func(name):
            return lambda doc: self._push_to_queue(name, doc)

        # private registry of callbacks processed on the "scan thread"
        self._scan_cb_registry = CallbackRegistry()
        for name in self._queues.keys(): 
            self._register_scan_callback(name, make_push_func(name))

    def clear(self):
        self.panic = False
        self._objs_read.clear()
        self._read_cache.clear()
        self._describe_cache.clear()
        self._descriptor_uids.clear()
        self._sequence_counters.clear()
        # Unsubscribe for per-run callbacks.
        for cid in self._temp_callback_ids:
            self.unsubscribe(cid)
        self._temp_callback_ids.clear()

    def register_command(name, func):
        self._command_registry[name]= func

    def unregister_command(name):
        del self._command_registry[name]

    @property
    def panic(self):
        # Release GIL by sleeping, allowing other threads to set panic.
        ttime.sleep(0.01)
        return self._panic

    @panic.setter
    def panic(self, val):
        self._panic = val

    def _register_scan_callback(self, name, func):
        """Register a callback to be processed by the scan thread.

        Functions registered here are guaranteed to be run (there is no Queue
        involved) and they block the scan's progress until they return.
        """
        return self._scan_cb_registry.connect(name, func)

    def _push_to_queue(self, name, doc):
        self._queues[name].put(doc)

    def run(self, gen, subscriptions={}, use_threading=True):
        self.clear()
        for name, func in subscriptions.items():
            self._temp_callback_ids.add(self.subscribe(name, func))
        self._run_start_uid = new_uid()
        if self.panic:
            raise PanicStateError("RunEngine is in a panic state. The run "
                                  "was aborted before it began. No records "
                                  "of this run were created.")
        with SignalHandler(signal.SIGINT) as self._sigint_handler:
            func = lambda: self.run_engine(gen)
            if use_threading:
                thread = threading.Thread(target=func)
                thread.start()
                while thread.is_alive():
                    self.dispatcher.process_all_queues()
            else:
                func()
                self.dispatcher.process_all_queues()
            self.dispatcher.process_all_queues()  # catch any stragglers

    def run_engine(self, gen):
        # This function is optionally run on its own thread.
        doc = dict(uid=self._run_start_uid,
                time=ttime.time(), beamline_id=beamline_id, owner=owner,
                scan_id=scan_id, **custom)
        print("*** Emitted RunStart:\n%s" % doc)
        self.emit('start', doc)
        response = None
        exit_status = None
        reason = ''
        try:
            while True:
                if self.panic:
                    exit_status = 'fail'
                    raise PanicStateError("Something put the RunEngine into a "
                                          "panic state after the run began. "
                                          "Records were created, but the run "
                                          "was marked with "
                                          "exit_status='fail'.")
                if self._sigint_handler.interrupted:
                    exit_status = 'abort'
                    raise RunInterrupt("RunEngine detected a SIGINT (Ctrl+C) "
                                       "and aborted the scan. Records were "
                                       "created, but the run was marked with "
                                       "exit_status='abort'.")
                msg = gen.send(response)
                response = self._command_registry[msg.command](msg)

                print('{}\n   ret: {}'.format(msg, response))
        except StopIteration:
            exit_status = 'success'
        except Exception as err:
            exit_status = 'fail'
            reason = str(err)
            raise err
        finally:
            doc = dict(run_start=self._run_start_uid,
                    time=ttime.time(),
                    exit_status=exit_status,
                    reason=reason)
            self.emit('stop', doc)
            print("*** Emitted RunStop:\n%s" % doc)
            sys.stdout.flush()

    def _create(self, msg):
        self._read_cache.clear()
        self._objs_read.clear()

    def _read(self, msg):
        obj = msg.obj
        self._objs_read.append(obj)
        if obj not in self._describe_cache:
            self._describe_cache[obj] = obj.describe()
        ret = obj.read(*msg.args, **msg.kwargs)
        self._read_cache.append(ret)
        return ret

    def _save(self, msg):
        # The Event Descriptor is uniquely defined by the set of objects
        # read in this Event grouping.
        objs_read = frozenset(self._objs_read)

        # Event Descriptor
        if objs_read not in self._descriptor_uids:
            # We don't not have an Event Descriptor for this set.
            data_keys = {}
            [data_keys.update(self._describe_cache[obj]) for obj in objs_read]
            descriptor_uid = new_uid()
            doc = dict(run_start=self._run_start_uid, time=ttime.time(),
                       data_keys=data_keys, uid=descriptor_uid)
            self.emit('descriptor', doc)
            print("*** Emitted Event Descriptor:\n%s" % doc)
            self._descriptor_uids[objs_read] = descriptor_uid
            self._sequence_counters[objs_read] = count(1)
        else:
            descriptor_uid = self._descriptor_uids[objs_read]

        # Events
        seq_num = next(self._sequence_counters[objs_read])
        event_uid = new_uid()
        # Merge list of readings into single dict.
        readings = {k: v for d in self._read_cache for k, v in d.items()}
        for key in readings:
            readings[key]['value'] = _sanitize_np(readings[key]['value'])
        doc = dict(descriptor=descriptor_uid,
                    time=ttime.time(), data=readings, seq_num=seq_num,
                    uid=event_uid)
        self.emit('event', doc)
        print("*** Emitted Event:\n%s" % doc)

    def _null(self, msg):
        pass

    def _set(self, msg):
        return msg.obj.set(*msg.args, **msg.kwargs)

    def _trigger(self, msg):
        if 'block_group' in msg.kwargs:
            group = msg.kwargs['block_group']
            self._block_groups[group].add(msg.obj)
        return msg.obj.trigger(*msg.args, **msg.kwargs)

    def _wait(self, msg):
        # Block progress until every object that was trigged
        # triggered with the keyword argument `block=group` is done.
        group = msg.kwargs.get('group', msg.args[0])
        objs = self._block_groups[group]
        while True:
            if not any([obj.is_moving for obj in objs]):
                break
        del self._block_groups[group]
        return objs

    def _sleep(self, msg):
        return ttime.sleep(*msg.args)

    def emit(self, name, doc):
        self._scan_cb_registry.process(name, doc)


class Dispatcher(object):
    """Dispatch documents to user-defined consumers on the main thread."""

    def __init__(self, queues, timeout=0.05):
        self.queues = queues
        self.timeout = timeout
        self.cb_registry = CallbackRegistry()

    def process_queue(self, name):
        queue = self.queues[name]
        try:
            document = queue.get(timeout=self.timeout)
        except Empty:
            pass
        else:
            self.cb_registry.process(name, document)

    def process_all_queues(self):
        for name in self.queues.keys():
            self.process_queue(name)

    def subscribe(self, name, func):
        """
        Register a function to consume Event documents.

        The Run Engine can execute callback functions at the start and end
        of a scan, and after the insertion of new Event Descriptors
        and Events.

        Parameters
        ----------
        name: {'start', 'descriptor', 'event', 'stop'}
        func: callable
            expecting signature like ``f(mongoengine.Document)``
        """
        if name not in self.queues.keys():
            raise ValueError("Valid callbacks: {0}".format(self.queues.keys()))
        return self.cb_registry.connect(name, func)

    def unsubscribe(self, callback_id):
        """
        Unregister a callback function using its integer ID.

        Parameters
        ----------
        callback_id : int
            the ID issued by `subscribe`
        """
        self.cb_registry.disconnect(callback_id)


def new_uid():
    return str(uuid.uuid4())


def _sanitize_np(val):
    "Convert any numpy objects into built-in Python types."
    if isinstance(val, np.generic):
        if np.isscalar(val):
            return val.item()
        return val.tolist()
    return val


class PanicStateError(Exception):
    pass


class RunInterrupt(KeyboardInterrupt):
    pass
