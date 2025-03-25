# Copyright (C) 2012  Codethink Limited
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import collections
import time


class BuildController(object):

    def __init__(self, app, tempdir):
        self.settings = app.settings
        self.real_msg = app.msg
        self.tempdir = tempdir
        self.indent = 1

        self.workers = set()
        self.busy_workers = set()
        self.idle_workers = set()

        self.blobs = set()
        self.build_order = collections.deque()

    def indent_more(self): # pragma: no cover
        self.indent += 1

    def indent_less(self): # pragma: no cover
        self.indent -= 1

    def msg(self, text): # pragma: no cover
        spaces = '  ' * self.indent
        self.real_msg('%s%s' % (spaces, text))

    def generate_worker_name(self, ident):
        similar_workers = [x for x in self.workers if x.ident == ident]
        return '%s-%s' % (ident, len(similar_workers) + 1)

    def add_worker(self, worker):
        self.workers.add(worker)
        self.mark_idle(worker)

    def wait_for_workers(self, need_idle=False, timeout=0.1): # pragma: no cover
        # first, check if any of the busy workers are finished
        while all([x.check_complete(timeout) for x in self.busy_workers]):
            # wait and repeat if they are all busy and we have no idle workers
            if need_idle and len(self.idle_workers) == 0:
                time.sleep(0.250)
            else:
                break

        # get a list of all finished busy workers
        finished = [x for x in self.busy_workers if x.check_complete(0)]

        # log the result of all workers that we are moving from busy to idle
        for worker in finished:
            self.msg('Built %s using worker %s' % (worker.blob, worker))
            if worker.output:
                for line in worker.output.split('\n'):
                    self.msg('> %s' % line)
            if worker.error:
                import morphlib
                raise morphlib.execute.CommandFailure(worker.error['command'],
                                                      worker.error['error'])

        # mark all finished workers as being idle
        for worker in finished:
            self.mark_idle(worker)

    def wait_for_worker(self): # pragma: no cover
        # wait for at least one worker to be idle
        self.wait_for_workers(need_idle = True)

        # sort idle workers by their idle timestamps (ascending)
        idle_workers = sorted(self.idle_workers, key=lambda x: x.idle_since)

        # return the worker that has been idling for the longest period of time
        return idle_workers[0]

    def build(self, blobs, build_order): # pragma: no cover
        self.blobs = blobs
        self.build_order = build_order

        result = []

        while len(build_order) > 0:
            group = build_order.popleft()
            group_str = ', '.join([x.morph.filename for x in group])
            self.msg('Building parallel group %s' % group_str)
            self.indent_more()

            while len(group) > 0:
                blob = group.pop()

                worker = self.wait_for_worker()
                self.msg('Distributing %s to worker %s' % (blob, worker))
                self.mark_busy(worker)
                worker.build(blob)

            self.wait_for_workers(need_idle = False, timeout = None)

            self.indent_less()

        return result

    def mark_idle(self, worker): # pragma: no cover
        if worker not in self.idle_workers:
            self.idle_workers.add(worker)
        if worker in self.busy_workers:
            self.busy_workers.remove(worker)

    def mark_busy(self, worker): # pragma: no cover
        if worker not in self.busy_workers:
            self.busy_workers.add(worker)
        if worker in self.idle_workers:
            self.idle_workers.remove(worker)
