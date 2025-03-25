import random
import scheduler
import threading
import time
import sys
import traceback
import logging

logger = logging.getLogger('luigi-interface')


class Worker(object):
    """ Worker object communicates with a scheduler.

    Simple class that talks to a scheduler and:
    - Tells the scheduler what it has to do + its dependencies
    - Asks for stuff to do (pulls it in a loop and runs it)
    """

    def __init__(self, sch=None, locally=False, pass_exceptions=None, worker_id=None):
        if not worker_id:
            worker_id = 'worker-%09d' % random.randrange(0, 999999999)

        self.__id = worker_id

        if sch:
            self.__scheduler = sch
            self.__pass_exceptions = True
        elif locally:
            self.__scheduler = scheduler.CentralPlannerScheduler()
            self.__pass_exceptions = True
        else:
            self.__scheduler = scheduler.RemoteScheduler()
            self.__pass_exceptions = False

        if pass_exceptions != None:
            self.__pass_exceptions = pass_exceptions

        self.__scheduled_tasks = {}

        sch = self.__scheduler

        class KeepAliveThread(threading.Thread):
            def run(self):
                while True:
                    time.sleep(1.0)
                    try:
                        sch.ping(worker=worker_id)
                    except:  # httplib.BadStatusLine:
                        print 'WARNING: could not ping!'
                        raise

        k = KeepAliveThread()
        k.daemon = True
        k.start()

    def add(self, task):
        s = str(task)
        if s in self.__scheduled_tasks:
            return
        self.__scheduled_tasks[s] = task

        if task.complete():
            self.__scheduler.add_task(s, status='DONE', worker=self.__id)
            return

        elif task.run == NotImplemented:
            logger.warning('Task %s is is not complete and run() is not implemented. Probably a missing external dependency.', s)
            self.__scheduler.add_task(s, status='BROKEN', worker=self.__id)
            logger.debug("Done marking task %s as broken", s)
            return

        else:
            self.__scheduler.add_task(s, status='PENDING', worker=self.__id)
            logger.info('Scheduled %s' % s)
            for task_2 in task.deps():
                s2 = str(task_2)
                self.add(task_2)  # Schedule it recursively
                self.__scheduler.add_dep(s, s2, worker=self.__id)

    def run(self):
        while True:
            logger.debug("Asking scheduler for work...")
            done, s = self.__scheduler.get_work(worker=self.__id)
            logger.debug("Got response from scheduler!", done, s)
            if done:
                break

            if s == None:
                break

            task = self.__scheduled_tasks[s]

            # Verify that all the tasks are fulfilled!
            ok = True
            for task_2 in task.deps():
                if not task_2.complete():
                    ok = False

            if not ok:
                logger.error('Unfulfilled dependencies at run time!')
                break

            try:
                logger.info('Running   %s' % s)
                task.run()
                logger.info('Done      %s' % s)
                status, expl = 'DONE', None
            except KeyboardInterrupt:
                raise
            except:
                if not self.__pass_exceptions:
                    raise  # TODO: not necessarily true that we want to break on the first exception
                status = 'FAILED'
                expl = traceback.format_exc(sys.exc_info()[2])

                print expl

            self.__scheduler.status(s, status=status, expl=expl, worker=self.__id)
