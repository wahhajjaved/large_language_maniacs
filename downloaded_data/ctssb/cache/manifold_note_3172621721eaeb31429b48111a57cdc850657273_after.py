import os
import codecs
import json
import tempfile

import jinja2
import jinja2.ext

import filters

SUBDIR = 'notes'

def _ensure_dir(f):
	d = os.path.dirname(f)
	if not os.path.isdir(d):
		os.makedirs(d)

def _render(note, charset='utf-8'):

	# load from FileSystem directory
	#loader = jinja2.FileSystemLoader('templates')
	loader = jinja2.PackageLoader('manifold_note', 'templates')

	# create environment and set to strip code blocks
	env = jinja2.Environment(loader=loader, trim_blocks=True, lstrip_blocks=True, extensions=[jinja2.ext.with_])

	# add datetime formatting filter
	env.filters['dtformat'] = filters.dtformat

	# render template and return
	return env.get_template('manifold-note.html').render(note=note)

def create(storage, data):

	# get uid and use as file name
	try:
		uid = data['properties']['uid'][0]
		uid = uid.strip()

		if not uid: 
			return {'code': 400, 'message': 'uid of data not valid'}
	except KeyError:
		return {'code': 400, 'message': 'uid of data not found'}
		pass

	dir_path = os.path.join(storage, SUBDIR, uid)
	html_path = os.path.join(dir_path, uid+'.html')

	#  if file already exists return error
	if os.path.exists(html_path):
		return {'code': 409, 'message': 'File already exists'}

	# make sure the directories exist
	_ensure_dir(html_path)

	# create HTML file
	with codecs.open(html_path, 'w', 'utf-8') as f:
		f.write(_render(data['properties']))

	json_path = os.path.join(dir_path, uid+'.json')

	# create JSON file for data
	with codecs.open(json_path, 'w', 'utf-8') as f:
		json.dump(data, f, ensure_ascii=False)

	return {'code': 200, 'message': 'File stored'}

def read(storage, uid):

	# read directly from json; create function should make JSON

	dir_path = os.path.join(storage, SUBDIR, uid)
	json_path = os.path.join(dir_path, uid+'.json')

	# if JSON exists read from JSON
	if not os.path.exists(json_path):
		return {'code': 404, 'message': 'File not found'}

	with codecs.open(json_path, 'r', 'utf-8') as f:
		data = json.load(f)

	return {'code': 200, 'message': 'File read', 'data': data}

def update(storage, data):

	# get uid and use as file name
	try:
		uid = data['properties']['uid'][0]
		uid = uid.strip()

		if not uid:
			return {'code': 400, 'message': 'uid of data not valid'}
	except KeyError:
		return {'code': 400, 'message': 'uid of data not found'}
		pass

	# open file. if does not exist throw error
	dir_path = os.path.join(storage, SUBDIR, uid)
	json_path = os.path.join(dir_path, uid+'.json')

	if not os.path.exists(json_path):
		return {'code': 404, 'message': 'File not found'}

	old_data = None

	with codecs.open(json_path, 'r', 'utf-8') as f:
		old_data = json.load(f)

	# don't allow uid change through update
	if old_data['properties']['uid'][0] != uid:
		return {'code': 400, 'message': 'uid of data does not match uid of file'}

	# create temp file to write json data
	with tempfile.NamedTemporaryFile(delete=False, dir=dir_path) as temp_f:
		json.dump(data, temp_f, ensure_ascii=False)
		# replace original json file
		os.rename(temp_f.name, json_path)

	html_path = os.path.join(dir_path, uid+'.html')

	# create temp file to write html data
	with tempfile.NamedTemporaryFile(delete=False, dir=dir_path) as temp_f:
		temp_f.write(_render(data['properties']).encode('utf-8'))
		# replace original file
		os.rename(temp_f.name, html_path)

	return {'code': 200, 'message': 'File updated'}

def extend(storage, uid, data):

	# used to add some properties to the file such as syndication links, responses without changing the whole file

	# return status of extend
	return None

def delete(storage, uid):

	# find file. raise error if does not exist

	# flag file as deleted

	# return status of delete
	return None

def undelete(storage, uid):

	# find file. raise error if does not exist

	# unflag the deleted file?

	# return status of undelete
	return None
