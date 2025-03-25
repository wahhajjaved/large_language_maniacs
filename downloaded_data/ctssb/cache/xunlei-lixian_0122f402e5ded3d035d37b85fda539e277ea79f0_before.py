
__all__ = ['search_tasks', 'find_task_by_url', 'find_tasks_to_download', 'find_torrents_task_to_download']

import re
import urllib2
import fileinput

from lixian_encoding import default_encoding
import lixian_hash_bt
import lixian_hash_ed2k

def to_utf_8(url):
	try:
		return url.decode(default_encoding).encode('utf-8')
	except:
		return url

def link_normalize(url):
	from lixian_url import url_unmask, normalize_unicode_link
	from lixian_url import url_unmask, normalize_unicode_link
	url = url_unmask(url)
	if url.startswith('magnet:'):
		return 'bt://'+lixian_hash_bt.magnet_to_infohash(url).encode('hex')
	elif url.startswith('ed2k://'):
		return lixian_hash_ed2k.parse_ed2k_link(url)
	elif url.startswith('bt://'):
		return url.lower()
	elif url.startswith('http://') or url.startswith('ftp://'):
		return normalize_unicode_link(url)
	return url

def link_equals(x1, x2):
	return link_normalize(x1) == link_normalize(x2)

def link_in(url, links):
	for link in links:
		if link_equals(url, link):
			return True

def is_url(url):
	return re.match(r'\w+://|magnet:', url)

def is_id(x):
	return re.match(r'^#?\d+(/[-.\w\[\],\s]+)?$', x) or re.match(r'^#?\d+-\d+$', x)

def find_task_by_url(tasks, url):
	for t in tasks:
		if link_equals(t['original_url'], url):
			return t

def find_tasks_by_range(tasks, x):
	m = re.match(r'^#?(\d+)-(\d+)$', x)
	begin = int(m.group(1))
	end = int(m.group(2))
	return filter(lambda x: begin <= x['#'] <= end, tasks)

def find_task_by_id(tasks, id):
	for t in tasks:
		if str(t['id']) == id or str(t['#']) == id or '#'+str(t['#']) == id:
			return t

def find_tasks_by_id(tasks, id):
	if re.match(r'^#?\d+-\d+$', id):
		return find_tasks_by_range(tasks, id)

	task_id, sub_id = re.match(r'^(#?\d+)(?:/([-.\w\[\],\s]+))?$', id).groups()
	task = find_task_by_id(tasks, task_id)

	if not task:
		return []

	if not sub_id:
		return [task]

	assert task['type'] == 'bt', 'task %s is not a bt task' % task['name'].encode(default_encoding)
	matched = []
	if re.match(r'\[.*\]', sub_id):
		for sub_id in re.split(r'\s*,\s*', sub_id[1:-1]):
			assert re.match(r'^\d+(-\d+)?|\.\w+$', sub_id), sub_id
			if sub_id.startswith('.'):
				t = dict(task)
				t['index'] = sub_id
				matched.append(t)
			elif '-' in sub_id:
				start, end = sub_id.split('-')
				for i in range(int(start), int(end)+1):
					t = dict(task)
					t['index'] = str(i)
					matched.append(t)
			else:
				assert re.match(r'^\d+$', sub_id), sub_id
				t = dict(task)
				t['index'] = sub_id
				matched.append(t)
	elif re.match(r'^\.\w+$', sub_id):
		t = dict(task)
		t['index'] = sub_id
		matched.append(t)
	else:
		assert re.match(r'^\d+$', sub_id), sub_id
		t = dict(task)
		t['index'] = sub_id
		matched.append(t)
	return matched

def search_in_tasks(tasks, keywords):
	found = []
	for x in keywords:
		# search url
		if is_url(x):
			task = find_task_by_url(tasks, x)
			if task:
				found.append(task)
			else:
				found.append(x) # keep the task order per arguments
			continue
		# search id
		if is_id(x):
			matched = find_tasks_by_id(tasks, x)
			if matched:
				found += matched
				continue
		# search date
		if re.match(r'^\d{4}\.\d{2}\.\d{2}$', x):
			raise NotImplementedError()
			matched = filter(lambda t: t['date'] == v, tasks)
			if matched:
				found += matched
				continue
		# search name
		matched = filter(lambda t: t['name'].lower().find(x.lower()) != -1, tasks)
		if matched:
			found += matched
		else:
			# keyword not matched
			pass
	found = merge_bt_sub_tasks(found)
	return filter(lambda x: type(x) == dict, found), filter(lambda x: type(x) != dict, found), found

def search_tasks(client, args, status='all'):
	if status == 'all':
		tasks = client.read_all_tasks()
	elif status == 'completed':
		tasks = client.read_all_tasks()
	else:
		raise NotImplementedError()
	return search_in_tasks(tasks, list(args))[0]

def find_torrents_task_to_download(client, links):
	tasks = client.read_all_tasks()
	hashes = set(t['bt_hash'].lower() for t in tasks if t['type'] == 'bt')
	link_hashes = []
	for link in links:
		if re.match(r'^(?:bt://)?([a-fA-F0-9]{40})$', link):
			info_hash = link[-40:].lower()
			if info_hash not in hashes:
				print 'Adding bt task', link
				client.add_torrent_task_by_info_hash(info_hash)
			link_hashes.append(info_hash)
		elif re.match(r'http://', link):
			print 'Downloading torrent file from', link
			torrent = urllib2.urlopen(link, timeout=60).read()
			assert torrent.startswith('d8:announce') or torrent.startswith('d13:announce-list'), 'Probably not a valid torrent file [%s...]' % repr(torrent[:17])
			info_hash = lixian_hash_bt.info_hash_from_content(torrent)
			if info_hash not in hashes:
				print 'Adding bt task', link
				client.add_torrent_task_by_content(torrent, os.path.basename(link))
			link_hashes.append(info_hash)
		elif os.path.exists(link):
			with open(link, 'rb') as stream:
				torrent = stream.read()
			assert torrent.startswith('d8:announce') or torrent.startswith('d13:announce-list'), 'Probably not a valid torrent file [%s...]' % repr(torrent[:17])
			info_hash = lixian_hash_bt.info_hash_from_content(torrent)
			if info_hash not in hashes:
				print 'Adding bt task', link
				client.add_torrent_task_by_content(torrent, os.path.basename(link))
			link_hashes.append(info_hash)
		else:
			raise NotImplementedError('Unknown torrent '+link)
	all_tasks = client.read_all_tasks()
	tasks = []
	for h in link_hashes:
		for t in all_tasks:
			if t['bt_hash'].lower() == h.lower():
				tasks.append(t)
				break
		else:
			raise NotImplementedError('not task found')
	return tasks

def find_tasks_to_download(client, args):
	links = []
	links.extend(args)
	if args.input:
		links.extend(line.strip() for line in fileinput.input(args.input) if line.strip())
	if args.torrent:
		return find_torrents_task_to_download(client, links)
	found, missing, all = search_in_tasks(client.read_all_tasks(), links)
	to_add = set(missing)
	if to_add:
		print 'Adding below tasks:'
		for link in missing:
			print link
		client.add_batch_tasks(map(to_utf_8, to_add))
		for link in to_add:
			# add_batch_tasks doesn't work for bt task, add bt task one by one...
			if link.startswith('bt://') or link.startswith('magnet:'):
				client.add_task(link)
		all_tasks = client.read_all_tasks()
	tasks = []
	for x in all:
		if type(x) == dict:
			tasks.append(x)
		else:
			task = find_task_by_url(x)
			if not task:
				raise NotImplementedError('task not found, wired: '+x)
			tasks.append(task)
	return tasks

def merge_bt_sub_tasks(tasks):
	result_tasks = []
	task_mapping = {}
	for task in tasks:
		if type(task) == dict:
			id = task['id']
			if id in task_mapping:
				if 'index' in task and 'files' in task_mapping[id]:
					task_mapping[id]['files'].append(task['index'])
			else:
				if 'index' in task:
					t = dict(task)
					t['files'] = [t['index']]
					del t['index']
					result_tasks.append(t)
					task_mapping[id] = t
				else:
					result_tasks.append(task)
					task_mapping[id] = task
		else:
			if task in task_mapping:
				pass
			else:
				result_tasks.append(task)
				task_mapping[task] = task
	return result_tasks

