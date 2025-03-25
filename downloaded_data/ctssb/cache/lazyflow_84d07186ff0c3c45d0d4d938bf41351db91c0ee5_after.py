import time, os, sys
import psutil
import atexit
from collections import deque
from Queue import Queue, LifoQueue, Empty, PriorityQueue
from threading import Thread, current_thread
import greenlet
import threading
from helpers import detectCPUs
import math

greenlet.GREENLET_USE_GC = False #use garbage collection
sys.setrecursionlimit(1000)


def patchIfForeignThread(thread):
  if not hasattr(thread, "finishedGreenlets"):
    setattr(thread, "wlock", threading.Lock())
    setattr(thread, "workAvailable", False)
    setattr(thread, "requests", deque())
    setattr(thread, "finishedGreenlets", deque())
    setattr(thread, "last_request", None)
    setattr(thread, "current_request", None)

def wakeUp(thread):
  try:
    thread.workAvailable = True
    thread.wlock.release()
  except:
    pass


class Worker(Thread):
  def __init__(self, machine, wid = 0):
    Thread.__init__(self)
    self.daemon = True # kill automatically on application exit!
    print "Creating worker %r for ThreadPool %r" % (self, machine)
    self.wid = wid
    self.machine = machine
    self.running = True
    self.processing = False
    self.last_request = None
    self.current_request = None
    #self.socket = zmq.Socket(context,zmq.SUB)
    #self.socket.bind("inproc://%d" % self.wid)
    self.requests = deque()#PriorityQueue()
    self.finishedGreenlets = deque()
    self.process = psutil.Process(os.getpid())
    self.wlock = threading.Lock()
    self.wlock.acquire()
    self.workAvailable = False


  def stop(self):
    print "stopping worker %r of machine %r" % (self, self.machine)
    allDone = False

    while not allDone:
      # wait untile all threads have nothing to do anymore
      allDone = True
      for w in self.machine.workers:
        if w.running and (w.processing or w.workAvailable):
          #print "Worker %r still working..." % w
          allDone = False
          time.sleep(0.1)
          break

    self.running = False
    wakeUp(self)
    self.join()

  def run(self):
    # cache value for less dict lookups
    requests0 = self.machine.requests0
    requests1 = self.machine.requests1
    freeWorkers = self.machine.freeWorkers

    while self.running:
      self.processing = False
      freeWorkers.add(self)
      #print "Worker %r sleeping..." % self
      self.wlock.acquire()
      self.processing = True
      #print "Worker %r working..." % self
      try:
        freeWorkers.remove(self)
      except KeyError:
        pass
      didRequest = True
      while len(self.finishedGreenlets) != 0 or didRequest:
        self.workAvailable = False
        # first process all finished greenlets
        while not len(self.finishedGreenlets) == 0:
          gr = self.finishedGreenlets.popleft()
          if gr.request.canceled is False:
            self.current_request = gr.request
            gr.switch()
        
        # processan higher priority request if available
        didRequest = False
        req = None
        try:
          req = requests1.pop()
          #prio, req = requests.get(block=False)
        except: 
          # requests was empty..
          pass
        if req is not None and req.finished is False and req.canceled is False:
          didRequest = True
          gr = CustomGreenlet(req._execute)
          self.current_request = req
          gr.thread = self
          gr.request = req
          gr.switch()

        if didRequest is False:
          # only do a low priority request if no higher priority request
          # was available
          try:
            req = requests0.pop()
          except: 
            # requests was empty..
            pass
          if req is not None and req.finished is False and req.canceled is False:
            didRequest = True
            gr = CustomGreenlet(req._execute)
            self.current_request = req
            gr.thread = self
            gr.request = req
            gr.switch()
        
        # reset the wait lock state, otherwise the surrounding while self.running loop will always be executed twice
        try:
          self.wlock.release()
        except:
          pass
        self.wlock.acquire()



class Singleton(type):
  """
  simple implementation of meta class that implements the singleton pattern.
  """
  def __init__(cls, name, bases, dict):
      super(Singleton, cls).__init__(name, bases, dict)
      cls.instance = None 

  def __call__(cls,*args,**kw):
      if cls.instance is None:
          cls.instance = super(Singleton, cls).__call__(*args, **kw)
      return cls.instance


class ThreadPool(object):
  """
  This class uses the Singleton meta class to
  represent the cpus of the machine
  """
  __metaclass__ = Singleton

  def __init__(self):
    self._finished = False
    #self.requests = PriorityQueue()
    self.requests0 = deque()
    self.requests1 = deque()
    self.workers = set()
    self.freeWorkers = set()
    self.numThreads = detectCPUs()
    self.lastWorker = None
    for i in range(int(math.ceil(self.numThreads/2.0))):
      w = Worker(self)
      self.workers.add(w)
      w.start()
      self.lastWorker = w

  def putRequest(self, request):
    """
    Put a job in the queue of a free worker. if no
    worker is free, put it to the threadpool request queue,
    the first free worker will take it from there.
    """
    #self.requests.put((request.prio,request))
    if request.prio == 0:
      self.requests0.append(request)
    else:
      self.requests1.append(request)
    try:
      w = self.freeWorkers.pop()
      wakeUp(w)
    except:
      pass

  def stopThreadPool(self):
    """
    wait until all requests are processed and stop the workers.
    """
    if not self._finished:
      self._finished = True
      # stop the workers of the machine
      for w in self.workers:
        w.stop()
      

@atexit.register
def stopThreadPool():
  """
  global atexit handler, on program exit stop
  all workers.
  """
  # get the machine singleton
  machine = ThreadPool()
  machine.stopThreadPool()

# create a  globalmachine instance
global_thread_pool = ThreadPool()


# unused decorator
class inThread(object):
  def __init__(self, f):
    self.f = f
    f.func_dict['greencall_inThread'] = True

  def __call__(self):
    self.f()


class CustomGreenlet(greenlet.greenlet):
  """
  small heler class that wraps a greenlet and provides
  additional attributes.
  """
  __slots__ = ("thread", "request")



class Lock(object):
  """
  experimental non blocking, request/threadpool/worker compatible
  Lock object that can be used for long running tasks.

  The Lock object can only be used from within CustomGreenlets.

  If a thread would normally block on an acquire() call, due to an
  already acquired lock, this lock instead switches to the
  Workers run function, so that the thread can execute other tasks.
  """

  def __init__(self):
    self.lock1 = threading.Lock()
    self.lock1.acquire()
    self.lock2 = threading.Lock()
    self.waiting = deque()

  def acquire(self):
    try:
      # try to acqiure lock1 (unlocked lock1 means 
      # this Lock object is already acquired by somebody else
      self.lock1.release()
      self.lock2.acquire()
    except:
      # equivalent to locked
      cur_gr = greenlet.getcurrent()
      self.waiting.append(cur_gr)
      
      # yield to Worker run loop
      cur_gr.parent.switch()


  def release(self):
    self.lock2.release()

    # try to pop a waiting greenlet from the queue
    # and wake it up
    try:
      gr = self.waiting.popleft()

      # reset the state of this Lock object to acquired
      # because the greenlet that is woken up
      # will release it for us
      self.lock2.acquire()
      gr.thread.finishedGreenlets.appendleft(gr)
      wakeUp(gr.thread)
    except IndexError:
      # indicate that this Lock object can be acquired again
      self.lock1.acquire()



class Request(object):
  """
  Class that wraps a computation.

  it takes a function and its arguments on initialization and allows
  to execute this function synchronously and asynchronously. In addition
  various types of callbacks can be provided that notify
  of cancellation, finished computation etc.
  """
  def __init__(self, function, **kwargs):
    self.running = False
    self.finished = False
    self.canceled = False
    self.processing = False
    self.lock = threading.Lock()
    self.function = function
    self.kwargs = kwargs
    self.callbacks_cancel = []
    self.callbacks_finish = []
    self.waiting_greenlets = []
    #self.waiting_locks = []
    self.child_requests = set()
    self.result = None
    self.parent_request = None
    self.prio = 0
    cur_gr = greenlet.getcurrent()
    cur_tr = threading.current_thread()
    patchIfForeignThread(cur_tr)

    if isinstance(cur_gr, CustomGreenlet):
      self.parent_request = cur_gr.request
      self.prio = self.parent_request.prio - 1

      # self.parent_request.lock.acquire()
      self.parent_request.child_requests.add(self)
      # self.parent_request.lock.release()
    
      # always hold back one request that
      # was created in a thread.
      # if a second one is created, submit the first one to the job queue
    last_request = cur_tr.last_request
    if last_request is not None:
      #print "bursting..."
      last_request.submit()
    cur_tr.last_request = self


  def __call__(self):
    """
    synchronous wait without timeout
    """
    return self.wait()

  def _releaseLock(self, lock):
    """
    helper function that sets an event. this is used by the wait
    method to provide a possiblity for an non-worker thread to wait
    for completion of a request.
    """
    try:
      lock.release()
    except:
      pass
  
  def wait(self, timeout = 0):
    """
    synchronous wait for exectution of function
    """
    cur_gr = greenlet.getcurrent()
    cur_tr =  threading.current_thread()

    # if we are waiting for something else
    # burst the last reqeust
    last_request = cur_tr.last_request
    if last_request is not None and last_request != self:
      #print "bursting..."
      last_request.submit()
    cur_tr.last_request = None

    self.lock.acquire()
    if not self.finished and not self.canceled:
      if not self.running:
        self.running = True
        self.lock.release()
        patchIfForeignThread(cur_tr)
        self._execute()
      else:
        # wait for results
        if isinstance(cur_tr, Worker):
          # just wait for the request to finish
          # we will get woken up
          self.waiting_greenlets.append(cur_gr)
          self.lock.release()
          # switch back to parent 
          cur_gr.parent.switch()
        else:
          lock = cur_tr.wlock
          try:
            lock.release()
          except:
            pass
          lock.acquire()
          #self.waiting_locks.append(lock)
          self.callbacks_finish.append((Request._releaseLock, {"lock" : lock}))    
          self.lock.release()
          lock.acquire()
    return self.result
  
  def submit(self):
    """
    asynchronous execution in background
    """
    if self.finished or self.canceled:
      return
    self.lock.acquire()
    if not self.running:
      self.running = True
      self.lock.release()
      global_thread_pool.putRequest(self)
    else:
      self.lock.release()
    return self


  def onCancel(self, callback, *args, **kwargs):
    """
    specify a callback that is called when the request is canceled.
    """
    self.lock.acquire()
    if not self.canceled:
      self.callbacks_cancel.append((callback, args, kwargs))
      self.lock.release()
    else:
      self.lock.release()
      callback(self, *args,**kwargs)
    return self

  def onFinish(self, callback, **kwargs):
    """
    execute function asynchronously and
    call the specified callback function with the given
    args and kwargs.
    """
    self.lock.acquire()
    if not self.finished:
      self.callbacks_finish.append((callback, kwargs))
      self.lock.release()
    else:
      self.lock.release()
      callback(self,**kwargs)
    return self


  def cancel(self):
    """
    cancel a running request
    """
    self.lock.acquire()
    if not self.finished: 
      callbacks_cancel = self.callbacks_cancel
      self.callbacks_cancel = []
      child_requests = self.child_requests
      self.child_requests = set()
      self.lock.release()
      
      canceled = True
      for c in callbacks_cancel:
        # call the callback tuples
        canceled = c[0](self, *c[1],**c[2])
        if canceled is False:
          break
      if canceled:
        for c in child_requests:
          print "canceling child.."
          c.cancel()
        self.canceled = True
    else:
      print "tryed to cancel but, ",self.finished, self.canceled


  def _execute(self):
    """
    helper function that executes the actual function of the request
    calls all callbacks specified with onNotify and 
    resumes all waiters in other worker threads.
    """
    # assert self.running is True
    # assert self.finished is False
    if self.canceled:
      return
    
    cur_tr = threading.current_thread()
    req_backup = cur_tr.current_request 
    cur_tr.current_request = self

    # do the actual work
    self.result = self.function(**self.kwargs)

    self.lock.acquire()
    self.processing = True
    self.finished = True
    waiting_greenlets = self.waiting_greenlets
    self.waiting_greenlets = None
    # waiting_locks = self.waiting_locks
    # self.waiting_locks = None   
    callbacks_finish = self.callbacks_finish
    self.callbacks_finish = None
    self.lock.release()
    
    #self.lock.acquire()
    if self.parent_request is not None:
      # self.parent_request.lock.acquire()
      try:
        self.parent_request.child_requests.remove(self)
      except KeyError:
        pass
      # self.parent_request.lock.release()
      if self.prio - 1 < self.parent_request.prio:
        self.parent_request.prio = self.prio - 1
    #self.lock.release()
    
    for gr in waiting_greenlets:
      # greenlets ready to continue in the quee of the corresponding workers
      gr.thread.finishedGreenlets.append(gr)
      wakeUp(gr.thread)
 
    #for l in waiting_locks:
    #  l.release()

    for c in callbacks_finish:
      # call the callback tuples
      c[0](self, **c[1])          

    cur_tr.current_request = req_backup

  
  #
  #
  #  Functions for backwards compatability !
  #

  
  def _wrapperFinishCallback(self, real_callback, **kwargs):
    real_callback(self.result, **kwargs)


  def notify(self, function, **kwargs):
    """
    convenience function, setup a callback for finished computation
    and start the computation in the background
    """
    self.onFinish( Request._wrapperFinishCallback, real_callback = function, **kwargs)
    self.submit()
    return self

  def allocate(self, priority = 0):
    return self


  def writeInto(self, destination):
    self.kwargs["destination"] = destination
    return self

  def getResult(self):
    return self.result



if __name__ == "__main__":
  def callback(s):
    pass
    #print "callback: finished ", req

  def testA():
    time.sleep(1)
    #print "producer finished"

  def test(s):
    req = Request(testA)
    req.notify(callback)
    req.wait()
    #print "sleeping ..."
    time.sleep(1)
    print s
    return s

  req = Request( test, s = "hallo !")
  req.notify(callback)
  assert req.wait() == "hallo !"


  requests = []
  for i in range(10):
    req = Request( test, s = "hallo %d" %i)
    requests.append(req)





