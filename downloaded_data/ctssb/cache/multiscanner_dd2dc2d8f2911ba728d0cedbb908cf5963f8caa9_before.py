# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/
from __future__ import division, absolute_import, with_statement, print_function, unicode_literals
import requests
import json
import time
from common import basename
from collections import Counter

__author__ = "Drew Bonasera"
__license__ = "MPL 2.0"

TYPE = "Detonation"
NAME = "Cuckoo Sandbox"
DEFAULTCONF = {
    "ENABLED": False,
    "API URL": 'http://cuckoo:8090/',
    "timeout": 360,
    "running timeout": 120,
    "delete tasks": False,
}

def check(conf=DEFAULTCONF):
    return conf["ENABLED"]

def scan(filelist, conf=DEFAULTCONF):
    resultlist = []
    tasks = []
    if conf['API URL'].endswith('/'):
        url = conf['API URL']
    else:
        url = conf['API URL'] + '/'
    new_file_url = url + 'tasks/create/file'
    report_url = url + 'tasks/report/'
    view_url = url + 'tasks/view/'
    delete_url = url + 'tasks/delete/'

    for fname in filelist:
        with open(fname, "rb") as sample:
            multipart_file = {"file": (basename(fname), sample)}
            payload = {"timeout": conf['timeout']}
            request = requests.post(new_file_url, files=multipart_file, json=json.dumps(payload))

        task_id = request.json()["task_id"]
        if task_id is not None:
            tasks.append((fname, str(task_id)))
        else:
            #TODO Do something here?
            pass

    # Wait for tasks to finish
    task_status = {}
    while tasks:
        for fname, task_id in tasks[:]:
            status = requests.get(view_url+task_id).json()['task']['status']

            # If we have a report
            if status == 'reported':
                report = requests.get(report_url+task_id)
                if report.status_code == 200:
                    report = report.json()
                    resultlist.append((fname, report))
                    tasks.remove((fname, task_id))
                    if conf['delete tasks']:
                        requests.get(delete_url+task_id)
                else:
                    # Do we ever actually hit here?
                    pass

            # Check for dead tasks
            elif status == 'running':
                if task_id not in task_status:
                    task_status[task_id] = time.time() + conf['timeout'] + conf['task timeout']
                else:
                    if time.time() > task_status[task_id]:
                        #TODO Log timeout
                        tasks.remove((fname, task_id))

            # If there is an unknown status
            elif status not in ['pending', 'processing', 'finished', 'completed', 'running']:
                #TODO Log errors better
                tasks.remove((fname, task_id))
        time.sleep(15)

    metadata = {}
    metadata["Name"] = NAME
    metadata["Type"] = TYPE
    metadata["Include"] = False
    return (resultlist, metadata)
