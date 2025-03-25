# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals


import frappe
import os
import time
import redis
from functools import wraps
from frappe.utils import get_site_path
import json
from frappe import conf

END_LINE = '<!-- frappe: end-file -->'
TASK_LOG_MAX_AGE = 86400  # 1 day in seconds
redis_server = None


def handler(f):
	cmd = f.__module__ + '.' + f.__name__

	def _run(args, set_in_response=True):
		from frappe.tasks import run_async_task
		from frappe.handler import execute_cmd
		if frappe.conf.disable_async:
			return execute_cmd(cmd, async=True)
		args = frappe._dict(args)
		task = run_async_task.delay(frappe.local.site,
			(frappe.session and frappe.session.user) or 'Administrator', cmd, args)
		if set_in_response:
			frappe.local.response['task_id'] = task.id
		return task.id

	@wraps(f)
	def queue(*args, **kwargs):
		from frappe.tasks import run_async_task
		from frappe.handler import execute_cmd
		if frappe.conf.disable_async:
			return execute_cmd(cmd, async=True)
		task = run_async_task.delay(frappe.local.site,
			(frappe.session and frappe.session.user) or 'Administrator', cmd,
				frappe.local.form_dict)
		frappe.local.response['task_id'] = task.id
		return {
			"status": "queued",
			"task_id": task.id
		}
	queue.async = True
	queue.queue = f
	queue.run = _run
	frappe.whitelisted.append(f)
	frappe.whitelisted.append(queue)
	return queue


def run_async_task(method, args, reference_doctype=None, reference_name=None, set_in_response=True):
	if frappe.local.request and frappe.local.request.method == "GET":
		frappe.throw("Cannot run task in a GET request")
	task_id = method.run(args, set_in_response=set_in_response)
	task = frappe.new_doc("Async Task")
	task.celery_task_id = task_id
	task.status = "Queued"
	task.reference_doctype = reference_doctype
	task.reference_name = reference_name
	task.save()
	return task_id


@frappe.whitelist()
def get_pending_tasks_for_doc(doctype, docname):
	return frappe.db.sql_list("select name from `tabAsync Task` where status in ('Queued', 'Running') and reference_doctype='%s' and reference_name='%s'" % (doctype, docname))


@handler
def ping():
	from time import sleep
	sleep(6)
	return "pong"


@frappe.whitelist()
def get_task_status(task_id):
	from frappe.celery_app import get_celery
	c = get_celery()
	a = c.AsyncResult(task_id)
	frappe.local.response['response'] = a.result
	return {
		"state": a.state,
		"progress": 0
	}


def set_task_status(task_id, status, response=None):
	frappe.db.set_value("Async Task", task_id, "status", status)
	if not response:
		response = {}
	response.update({
		"status": status,
		"task_id": task_id
	})
	emit_via_redis("task_status_change", response, room="task:" + task_id)


def remove_old_task_logs():
	logs_path = get_site_path('task-logs')

	def full_path(_file):
		return os.path.join(logs_path, _file)

	files_to_remove = [full_path(_file) for _file in os.listdir(logs_path)]
	files_to_remove = [_file for _file in files_to_remove if is_file_old(_file) and os.path.isfile(_file)]
	for _file in files_to_remove:
		os.remove(_file)


def is_file_old(file_path):
	return ((time.time() - os.stat(file_path).st_mtime) > TASK_LOG_MAX_AGE)


def publish_realtime(event, message=None, room=None, user=None, doctype=None, docname=None, now=False):
	"""Publish real-time updates

	:param event: Event name, like `task_progress` etc.
	:param message: JSON message object. For async must contain `task_id`
	:param room: Room in which to publish update (default entire site)
	:param user: Transmit to user
	:param doctype: Transmit to doctype, docname
	:param docname: Transmit to doctype, docname"""
	if message is None:
		message = {}

	if not room:
		if user:
			room = get_user_room(user)
		elif doctype and docname:
			room = get_doc_room(doctype, docname)
		else:
			room = get_site_room()

	if now:
		emit_via_redis(event, message, room)
	else:
		frappe.local.realtime_log.append([event, message, room])

def emit_via_redis(event, message, room):
	"""Publish real-time updates via redis

	:param event: Event name, like `task_progress` etc.
	:param message: JSON message object. For async must contain `task_id`
	:param room: name of the room"""
	r = get_redis_server()

	try:
		r.publish('events', json.dumps({'event': event, 'message': message, 'room': room}))
	except redis.exceptions.ConnectionError:
		pass

def put_log(line_no, line, task_id=None):
	r = get_redis_server()
	if not task_id:
		task_id = frappe.local.task_id
	task_progress_room = "task_progress:" + frappe.local.task_id
	task_log_key = "task_log:" + task_id
	publish_realtime('task_progress', {
		"message": {
			"lines": {line_no: line}
		},
		"task_id": task_id
	}, room=task_progress_room)
	r.hset(task_log_key, line_no, line)
	r.expire(task_log_key, 3600)


def get_redis_server():
	"""Returns memcache connection."""
	global redis_server
	if not redis_server:
		from redis import Redis
		redis_server = Redis.from_url(conf.get("async_redis_server") or "redis://localhost:12311")
	return redis_server


class FileAndRedisStream(file):
	def __init__(self, *args, **kwargs):
		ret = super(FileAndRedisStream, self).__init__(*args, **kwargs)
		self.count = 0
		return ret

	def write(self, data):
		ret = super(FileAndRedisStream, self).write(data)
		if frappe.local.task_id:
			put_log(self.count, data, task_id=frappe.local.task_id)
			self.count += 1
		return ret


def get_std_streams(task_id):
	stdout = FileAndRedisStream(get_task_log_file_path(task_id, 'stdout'), 'w')
	# stderr = FileAndRedisStream(get_task_log_file_path(task_id, 'stderr'), 'w')
	return stdout, stdout


def get_task_log_file_path(task_id, stream_type):
	logs_dir = frappe.utils.get_site_path('task-logs')
	return os.path.join(logs_dir, task_id + '.' + stream_type)


@frappe.whitelist(allow_guest=True)
def can_subscribe_doc(doctype, docname, sid):
	from frappe.sessions import Session
	from frappe.exceptions import PermissionError
	session = Session(None).get_session_data()
	if not frappe.has_permission(user=session.user, doctype=doctype, doc=docname, ptype='read'):
		raise PermissionError()
	return True

@frappe.whitelist(allow_guest=True)
def get_user_info(sid):
	from frappe.sessions import Session
	session = Session(None).get_session_data()
	return {
		'user': session.user,
	}

def get_doc_room(doctype, docname):
	return ''.join([frappe.local.site, ':doc:', doctype, '/', docname])

def get_user_room(user):
	return ''.join([frappe.local.site, ':user:', user])

def get_site_room():
	return ''.join([frappe.local.site, ':all'])

