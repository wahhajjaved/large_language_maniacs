#!/usr/bin/env python

from socket import *
import sys, os
import pickle
import multiprocessing, thread, threading, subprocess
import logging

PORT = 10000
BUFSIZE = 4096

def my_ip_address():
  import commands
  return commands.getoutput('/sbin/ifconfig').split('\n')[1].split()[1][5:]

def handler(work_generator, sock, addr):
  data = sock.recv(BUFSIZE).strip()
  try:
    if not data:
      return

    if 'get_command' == data:
      w = work_generator.next()
      print repr(addr) + ' sent:' + pickle.dumps(w)
      sock.send(w) 

    if data.startswith('file'):
      while True:
        part = sock.recv(BUFSIZE)
        if not part:
          break
        data += part

      fname = data[0:data.find('\n')].split()[1]
      data = data[data.find('\n')+1:]

      log = open(fname, 'w')
      amount = len(data)
      log.write(data)
      log.close()
      print repr(addr) + ' wrote: ', len(data), ' to ', fname

  finally:
    sock.close()
    print repr(addr), ' - closed connection'

def genWork():
  num = 0
  for i in range(1,60):
    for line in open('top-500.csv', 'r'):
      rank, domain = line.strip().split(',')
      for browser in os.listdir('browsers'):
        d = {'exec': 'browsers/' + browser + '/bin/QtTestBrowser',
             'iter': str(i),
             'rank': rank,
             'domain': domain,
             'browser': browser,
             'worknumber': num }
        d['results'] = "results/%(browser)s/rank%(rank)s-iter%(iter)s-%(domain)s"%d
        num += 1
        yield pickle.dumps(d)
  while True:
    yield 'quit'

class LockedIterator(object):
  def __init__(self, it):
    self._lock = threading.Lock()
    self._it = it.__iter__()

  def __iter__(self):
    return self

  def next(self):
    self._lock.acquire()
    try:
      return self._it.next()
    finally:
      self._lock.release()


class Server(object):
  def __init__(self, hostname, port):
    self._logger = logging.getLogger("server")
    self._hostname = hostname
    self._port = port
    self._work = LockedIterator(genWork())
    self._clean()

  def _clean(self):
    fnull = open(os.devnull, 'w')
    kwargs = {'stdout':fnull, 'stderr':fnull, 'shell':True}
    subprocess.call('rm -rf results', **kwargs)
    for browser in os.listdir('browsers'):
      subprocess.call('mkdir -p results/%s'%browser, **kwargs)

  def start(self):
    self._logger.debug("%s listening on %s", self._hostname, self._port)
    self._socket = socket(AF_INET, SOCK_STREAM)
    self._socket.bind((self._hostname, self._port))
    self._socket.listen(1)

    while True:
      conn, addr = self._socket.accept()
      self._logger.debug("%s got connection from %s", self._hostname, addr)
      thread.start_new_thread(handler, (self._work, conn, addr))

if __name__ == '__main__':
  import logging
  logging.basicConfig(level=logging.DEBUG)

  server = Server(my_ip_address(), PORT)
  try:
    logging.info("listening ...")
    server.start()
  #except Exception as e:
  #  print repr(e)
  #  logging.exception("unexpected exception:\n %s", e.child_traceback)
  finally:
    logging.info("shut down server ...")
    for process in multiprocessing.active_children():
      process.terminate()
      process.join()
  logging.info("done.")

