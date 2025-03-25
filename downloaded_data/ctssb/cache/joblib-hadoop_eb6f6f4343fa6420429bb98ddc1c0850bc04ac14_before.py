"""Remote worker script."""

import sys
from multiprocessing.pool import worker
from multiprocessing import Process
from multiprocessing.managers import BaseManager
from random import randint


class QueueManager(BaseManager):
    """Message queue manager."""
    pass

QueueManager.register('get_inqueue')
QueueManager.register('get_outqueue')
QueueManager.register('add_worker')
QueueManager.register('remove_worker')


class RemotePoolWorker(object):
    """ The RemotePoolWorker object.

    This worker will connect to a RemotePool over a socket to the specified
    ip and port, and execute all tasks in its queue.
    """

    def __init__(self, ip, port, authkey, worker_id=-1):
        """ Construct a new worker """
        self.mgr = QueueManager(address=(ip, port), authkey=authkey.encode())
        self.mgr.connect()

        self._inqueue = self.mgr.get_inqueue()
        self._outqueue = self.mgr.get_outqueue()

        if worker_id == -1:
            self._id = randint(1, sys.maxsize)
        else:
            self._id = worker_id

    def start(self):
        """ Start this worker. """
        self.mgr.add_worker(self._id)
        try:
            proc = Process(target=worker, args=(self._inqueue, self._outqueue))
            proc.start()
            proc.join()

            self.mgr.remove_worker(self._id, p.exitcode)

        except:
            self.mgr.remove_worker(self._id, 1)
            raise


def parse_and_start_worker():
    """Parse argument and start the remote worker."""
    import argparse

    parser = argparse.ArgumentParser(description='Start a RemotePoolWorker')
    parser.add_argument('--host',
                        metavar='HOSTNAME',
                        type=str,
                        default="localhost",
                        help='The hostname/IP of the RemotePool.')
    parser.add_argument('--port', '-p',
                        metavar='PORT',
                        type=int,
                        required=True,
                        help='The port of the RemotePool.')
    parser.add_argument("--key", '-k',
                        metavar="AUTHKEY",
                        type=str,
                        required=True,
                        help='The authkey used to connecto to the RemotePool')
    parser.add_argument('--workerid', '-w',
                        metavar='ID',
                        type=int,
                        default=-1,
                        help='The id of this RemotePoolWorker.')
    args = parser.parse_args()

    remote_worker = RemotePoolWorker(args.ip,
                                     args.port,
                                     args.key,
                                     args.workerid)
    remote_worker.start()


if __name__ == '__main__':
    parse_and_start_worker()
