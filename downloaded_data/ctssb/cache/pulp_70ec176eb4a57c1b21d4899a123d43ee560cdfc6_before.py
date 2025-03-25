# -*- coding: utf-8 -*-
#
# Copyright © 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

import datetime
import sys
from gettext import gettext as _
from types import NoneType

try:
    from bson import BSON, SON
except ImportError:
    from pymongo.bson import BSON
    from pymongo.son import SON

from isodate import ISO8601Error

from pulp.common import dateutils
from pulp.server import async
from pulp.server.api.repo_sync_task import RepoSyncTask
from pulp.server.db.model.cds import CDS
from pulp.server.db.model.resource import Repo
from pulp.server.pexceptions import PulpException
from pulp.server.tasking.scheduler import IntervalScheduler
from pulp.server.tasking.task import task_complete_states, Task

# schedule validation and manipulation -----------------------------------------

def validate_schedule(schedule):
    """
    Validate and standardize the format of an interval schedule specified in
    iso8601 format.
    @raise PulpException: when the schedule is not in iso8601 format
    @type schedule: str
    @param schedule: interval schedule in iso8601 format
    @rtype: str
    @return: interval schedule in pulp's standard iso8601 format
    """
    interval = start = runs = None
    try:
        interval, start, runs = dateutils.parse_iso8601_interval(schedule)
    except ISO8601Error:
        raise PulpException(_('Imporperly formatted schedule: %s') % schedule), None, sys.exc_info()[2]
    if not isinstance(interval, datetime.timedelta):
        raise PulpException(_('Invalid type for interval: %s') % str(type(interval)))
    # convert the start time to the local timezone
    if isinstance(start, datetime.datetime):
        start = dateutils.to_local_datetime(start)
    # re-format the schedule into pulp's standard format
    return dateutils.format_iso8601_interval(interval, start, runs)

# sync task management ---------------------------------------------------------

def schedule_to_scheduler(schedule):
    """
    Convenience function to turn a serialized task schedule into an interval
    scheduler appropriate for scheduling a sync task.
    @type schedule: basestring
    @param schedule: sync schedule to turn into interval scheduler in iso8601 format
    @rtype: L{IntervalScheduler}
    @return: interval scheduler for the tasking sub-system
    """
    i, s, r = dateutils.parse_iso8601_interval(schedule)
    if s is not None:
        s = dateutils.to_local_datetime(s)
    return IntervalScheduler(i, s, r)


def find_scheduled_task(id, method_name):
    """
    Look up a schedule task in the task sub-system for a given method
    @type id: str
    @param id: argument to the task
    @rtype: None or L{pulp.server.tasking.task.Task}
    @return: the sync task, None if no task is found
    """
    # NOTE this is very inefficient in the worst case: DO NOT CALL OFTEN!!
    # the number of sync tasks * (mean # arguments + mean # keyword arguments)
    for task in async.find_async(method_name=method_name):
        if task.args and id in task.args or \
                task.kwargs and id in task.kwargs.values():
            return task
    return None


def _add_repo_scheduled_sync_task(repo):
    """
    Add a new repo sync task for the given repo
    @type repo: L{pulp.server.db.model.resource.Repo}
    @param repo: repo to add sync task for
    """
    # hack to avoid circular import
    from pulp.server.api.repo import RepoApi
    import repo_sync
    api = RepoApi()
    task = RepoSyncTask(repo_sync._sync, [repo['id']])
    task.scheduler = schedule_to_scheduler(repo['sync_schedule'])
    synchronizer = api.get_synchronizer(repo['source']['type'])
    task.set_synchronizer(api, repo['id'], synchronizer)
    async.enqueue(task)


def _add_cds_scheduled_sync_task(cds):
    from pulp.server.api.cds import CdsApi
    api = CdsApi()
    task = Task(api.cds_sync, [cds['hostname']])
    task.scheduler = schedule_to_scheduler(cds['sync_schedule'])
    async.enqueue(task)


def _update_repo_scheduled_sync_task(repo, task):
    """
    Update and existing repo sync task's schedule
    @type repo: L{pulp.server.db.model.resource.Repo}
    @param repo: repo to update sync task for
    @type task: L{pulp.server.tasking.task.Task}
    @param task: task to update
    """
    if task.state not in task_complete_states:
        task.scheduler = schedule_to_scheduler(repo['sync_schedule'])
        return
    async.remove_async(task)
    task.scheduler = schedule_to_scheduler(repo['sync_schedule'])
    async.enqueue(task)


def _update_cds_scheduled_sync_task(cds, task):
    if task.state not in task_complete_states:
        task.scheduler = schedule_to_scheduler(cds['sync_schedule'])
        return
    async.remove_async(task)
    task.scheduler = schedule_to_scheduler(cds['sync_schedule'])
    async.enqueue(task)


def _remove_repo_scheduled_sync_task(repo):
    """
    Remove the repo sync task from the tasking sub-system for the given repo
    @type repo: L{pulp.server.db.model.resource.Repo}
    @param repo: repo to remove task for
    """
    task = find_scheduled_task(repo['id'], '_sync')
    if task is None:
        return
    async.remove_async(task)


def _remove_cds_scheduled_sync_task(cds):
    task = find_scheduled_task(cds['hostname'], 'cds_sync')
    if task is None:
        return
    async.remove_async(task)

# existing api -----------------------------------------------------------------

def update_repo_schedule(repo, new_schedule):
    """
    Change a repo's sync schedule.
    @type repo: L{pulp.server.db.model.resource.Repo}
    @param repo: repo to change
    @type new_schedule: dict
    @param new_schedule: dictionary representing new schedule
    """
    repo['sync_schedule'] = validate_schedule(new_schedule)
    collection = Repo.get_collection()
    collection.save(repo, safe=True)
    task = find_scheduled_task(repo['id'], '_sync')
    if task is None:
        _add_repo_scheduled_sync_task(repo)
    else:
        _update_repo_scheduled_sync_task(repo, task)

def delete_repo_schedule(repo):
    """
    Remove a repo's sync schedule
    @type repo: L{pulp.server.db.model.resource.Repo}
    @param repo: repo to change
    """
    if repo['sync_schedule'] is None:
        return
    repo['sync_schedule'] = None
    collection = Repo.get_collection()
    collection.save(repo, safe=True)
    _remove_repo_scheduled_sync_task(repo)

def update_cds_schedule(cds, new_schedule):
    '''
    Change a CDS sync schedule.
    '''
    cds['sync_schedule'] = validate_schedule(new_schedule)
    collection = CDS.get_collection()
    collection.save(cds, safe=True)
    task = find_scheduled_task(cds['hostname'], 'cds_sync')
    if task is None:
        _add_cds_scheduled_sync_task(cds)
    else:
        _update_cds_scheduled_sync_task(cds, task)

def delete_cds_schedule(cds):
    if cds['sync_schedule'] is None:
        return
    cds['sync_schedule'] = None
    collection = CDS.get_collection()
    collection.save(cds, safe=True)
    _remove_cds_scheduled_sync_task(cds)

# startup initialization -------------------------------------------------------

def init_scheduled_syncs():
    """
    Iterate through all of the repos in the database and start sync tasks for
    those that have sync schedules associated with them.
    """
    _init_repo_scheduled_syncs()
    _init_cds_scheduled_syncs()

def _init_repo_scheduled_syncs():
    collection = Repo.get_collection()
    for repo in collection.find({}):
        if repo['sync_schedule'] is None:
            continue
        _add_repo_scheduled_sync_task(repo)

def _init_cds_scheduled_syncs():
    collection = CDS.get_collection()
    for cds in collection.find({}):
        if cds['sync_schedule'] is None:
            continue
        _add_cds_scheduled_sync_task(cds)
