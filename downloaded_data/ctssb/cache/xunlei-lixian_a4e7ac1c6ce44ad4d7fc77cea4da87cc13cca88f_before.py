#!/usr/bin/env python

from lixian import XunleiClient, encypt_password
import lixian_config
import lixian_hash
import lixian_hash_bt
import lixian_hash_ed2k
import subprocess
import sys
import os
import os.path
import re
import urllib2

default_encoding = sys.getfilesystemencoding()
if default_encoding is None or default_encoding.lower() == 'ascii':
	default_encoding = 'utf-8'

def parse_command_line(args, keys=[], bools=[], alias={}, default={}):
	options = {}
	for k in keys:
		options[k] = None
	for k in bools:
		options[k] = None
	left = []
	args = args[:]
	while args:
		x = args.pop(0)
		if x == '--':
			left.extend(args)
			break
		if x.startswith('-'):
			k = x.lstrip('-')
			if k in bools:
				options[k] = True
			elif k.startswith('no-') and k[3:] in bools:
				options[k[3:]] = False
			elif k in keys:
				options[k] = args.pop(0)
			elif '=' in k and k[:k.index('=')] in keys:
				options[k[:k.index('=')]] = k[k.index('=')+1:]
			elif k in alias:
				k = alias[k]
				if k in bools:
					options[k] = True
				else:
					options[k] = args.pop(0)
			else:
				raise RuntimeError('Unknown option '+x)
		else:
			left.append(x)

	for k in default:
		if options[k] is None:
			options[k] = default[k]

	class Args(object):
		def __init__(self, args, left):
			self.__dict__['_args'] = args
			self.__dict__['_left'] = left
		def __getattr__(self, k):
			v = self._args.get(k, None)
			if v:
				return v
			if '_' in k:
				return self._args.get(k.replace('_', '-'), None)
		def __setattr__(self, k, v):
			self._args[k] = v
		def __getitem__(self, i):
			if type(i) == int:
				return self._left[i]
			else:
				return self._args[i]
		def __len__(self):
			return len(self._left)
		def __str__(self):
			return '<Args%s%s>' % (self._args, self._left)
	return Args(options, left)

def parse_login_command_line(args, keys=[], bools=[], alias={}, default={}):
	common_keys = ['username', 'password', 'cookies']
	common_default = {'cookies': lixian_config.LIXIAN_DEFAULT_COOKIES, 'username': lixian_config.get_config('username'), 'password': lixian_config.get_config('password')}
	common_keys.extend(keys)
	common_default.update(default)
	args = parse_command_line(args, common_keys, bools, alias, common_default)
	if args.cookies == '-':
		args._args['cookies'] = None
	return args

def usage():
	print '''python lixian_cli.py login "Your Xunlei account" "Your password"
python lixian_cli.py login "Your password"

python lixian_cli.py config username "Your Xunlei account"
python lixian_cli.py config password "Your password"

python lixian_cli.py list
python lixian_cli.py list --completed
python lixian_cli.py list --completed --name --original-url --download-url --no-status --no-id
python lixian_cli.py list id1 id2
python lixian_cli.py list zip rar
python lixian_cli.py list --search zip rar

python lixian_cli.py download task-id
python lixian_cli.py download ed2k-url
python lixian_cli.py download --tool wget ed2k-url
python lixian_cli.py download --tool asyn ed2k-url
python lixian_cli.py download ed2k-url --output "file to save"
python lixian_cli.py download id1 id2 id3
python lixian_cli.py download url1 url2 url3
python lixian_cli.py download --input download-urls-file
python lixian_cli.py download --input download-urls-file --delete
python lixian_cli.py download --input download-urls-file --ouput-dir root-dir-to-save-files
python lixian_cli.py download bt://torrent-info-hash
python lixian_cli.py download --torrent 1.torrent
python lixian_cli.py download --torrent torrent-info-hash
python lixian_cli.py download --torrent http://xxx/xxx.torrent

python lixian_cli.py add url
python lixian_cli.py add --torrent 1.torrent
python lixian_cli.py add --torrent torrent-info-hash
python lixian_cli.py add --torrent http://xxx/xxx.torrent

python lixian_cli.py delete task-id
python lixian_cli.py delete url
python lixian_cli.py delete file-name-on-cloud-to-delete

python lixian_cli.py pause id

python lixian_cli.py restart id

python lixian_cli.py logout

Please check https://github.com/iambus/xunlei-lixian for detailed (and Chinese) doc.
'''

def login(args):
	args = parse_login_command_line(args)
	if args.cookies == '-':
		args._args['cookies'] = None
	if len(args) < 1:
		raise RuntimeError('Not enough arguments')
	elif len(args) == 1:
		args.username = XunleiClient(cookie_path=args.cookies, login=False).get_username()
		args.password = args[0]
	elif len(args) == 2:
		args.username, args.password = list(args)
	elif len(args) == 3:
		args.username, args.password, args.cookies = list(args)
	elif len(args) > 3:
		raise RuntimeError('Too many arguments')
	if not args.username:
		raise RuntimeError("What's your name?")
	if args.cookies:
		print 'Saving login session to', args.cookies
	else:
		print 'Testing login without saving session'
	client = XunleiClient(args.username, args.password, args.cookies)

def logout(args):
	args = parse_command_line(args, ['cookies'], default={'cookies': lixian_config.LIXIAN_DEFAULT_COOKIES})
	if len(args):
		raise RuntimeError('Too many arguments')
	print 'logging out from', args.cookies
	assert args.cookies
	client = XunleiClient(cookie_path=args.cookies, login=False)
	client.logout()

def urllib2_download(client, download_url, filename, resuming=False):
	'''In the case you don't even have wget...'''
	assert not resuming
	print 'Downloading', download_url, 'to', filename, '...'
	request = urllib2.Request(download_url, headers={'Cookie': 'gdriveid='+client.get_gdriveid()})
	response = urllib2.urlopen(request)
	import shutil
	with open(filename, 'wb') as output:
		shutil.copyfileobj(response, output)

def asyn_download(client, download_url, filename, resuming=False):
	import lixian_download
	lixian_download.download(download_url, filename, headers={'Cookie': 'gdriveid='+str(client.get_gdriveid())}, resuming=resuming)

def wget_download(client, download_url, filename, resuming=False):
	gdriveid = str(client.get_gdriveid())
	wget_opts = ['wget', '--header=Cookie: gdriveid='+gdriveid, download_url, '-O', filename]
	if resuming:
		wget_opts.append('-c')
	exit_code = subprocess.call(wget_opts)
	if exit_code != 0:
		raise Exception('wget exited abnormaly')

def curl_download(client, download_url, filename, resuming=False):
	gdriveid = str(client.get_gdriveid())
	curl_opts = ['curl', '-L', download_url, '--cookie', 'gdriveid='+gdriveid, '--output', filename]
	if resuming:
		curl_opts.append('--continue')
	exit_code = subprocess.call(curl_opts)
	if exit_code != 0:
		raise Exception('curl exited abnormaly')

def aria2_download(client, download_url, filename, resuming=False):
	gdriveid = str(client.get_gdriveid())
	aria2_opts = ['aria2c', '--header=Cookie: gdriveid='+gdriveid, download_url, '--out', filename, '--file-allocation=none']
	if resuming:
		aria2_opts.append('-c')
	exit_code = subprocess.call(aria2_opts)
	if exit_code != 0:
		raise Exception('aria2c exited abnormaly')

# TODO: support axel, ProZilla

def escape_filename(name):
	name = re.sub(r'&(amp;)+', '&', name, flags=re.I)
	name = re.sub(r'[\\/:*?"<>|]', '-', name)
	return name

def verify_hash(path, task):
	if os.path.getsize(path) == task['size'] and lixian_hash.verify_dcid(path, task['dcid']):
		if task['type'] == 'ed2k':
			return lixian_hash_ed2k.verify_ed2k_link(path, task['original_url'])
		else:
			return True

class SimpleProgressBar:
	def __init__(self):
		self.displayed = False
	def update(self, percent):
		self.displayed = True
		bar_size = 40
		percent = int(percent*100)
		if percent > 100:
			percent = 100
		dots = bar_size * percent / 100
		plus = percent - dots / bar_size * 100
		if plus > 0.8:
			plus = '='
		elif plus > 0.4:
			plu = '>'
		else:
			plus = ''
		bar = '=' * dots + plus
		bar = '{:>3}%[{:<40}]'.format(percent, bar)
		sys.stdout.write('\r'+bar)
		sys.stdout.flush()
	def done(self):
		if self.displayed:
			print
			self.displayed = False

def download_single_task(client, download, task, output=None, output_dir=None, delete=False, resuming=False, overwrite=False):
	if task['status_text'] != 'completed':
		print 'skip task %s as the status is %s' % (task['name'].encode(default_encoding), task['status_text'])
		return
	def download1(client, url, path, size):
		if not os.path.exists(path):
			download(client, url, path)
		elif not resuming:
			if overwrite:
				download(client, url, path)
			else:
				raise Exception('%s already exists. Please specify --continue or --overwrite' % path)
		else:
			assert os.path.getsize(path) <= size
			if os.path.getsize(path) < size:
				download(client, url, path, resuming)
			elif os.path.getsize(path) == size:
				pass
			else:
				raise NotImplementedError()
	def download2(client, url, path, task):
		size = task['size']
		download1(client, url, path, size)
		if not verify_hash(path, task):
			print 'hash error, redownloading...'
			os.remove(path)
			download1(client, url, path, size)
			if not verify_hash(path, task):
				raise Exception('hash check failed')
	download_url = str(task['xunlei_url'])
	#filename = output or escape_filename(task['name']).encode(default_encoding)
	if output:
		filename = output
	else:
		filename = escape_filename(task['name']).encode(default_encoding)
		if output_dir:
			filename = os.path.join(output_dir, filename)
	referer = str(client.get_referer())
	gdriveid = str(client.get_gdriveid())

	if task['type'] == 'bt':
		dirname = filename
		if not os.path.exists(dirname):
			os.makedirs(dirname)
		files = client.list_bt(task)
		for f in files:
			name = f['name'].encode(default_encoding)
			print 'Downloading', name, '...'
			path = os.path.join(dirname, *name.split('\\'))
			subdir = os.path.dirname(path)
			if not os.path.exists(subdir):
				os.makedirs(subdir)
			download_url = str(f['xunlei_url'])
			download2(client, download_url, path, f)
		torrent_file = client.get_torrent_file(task)
		print 'Hashing bt ...'
		bar = SimpleProgressBar()
		verified = lixian_hash_bt.verify_bt(dirname, lixian_hash_bt.bdecode(torrent_file)['info'], progress_callback=bar.update)
		bar.done()
		if not verified:
			raise Exception('bt hash check failed')
	else:
		dirname = os.path.dirname(filename)
		if dirname and not os.path.exists(dirname):
			os.makedirs(dirname)
		print 'Downloading', os.path.basename(filename), '...'
		download2(client, download_url, filename, task)

	if delete:
		client.delete_task(task)

def download_multiple_tasks(client, download, tasks, output_dir=None, delete=False, resuming=False, overwrite=False):
	for task in tasks:
		download_single_task(client, download, task, output_dir=output_dir, delete=delete, resuming=resuming, overwrite=overwrite)
	skipped = filter(lambda t: t['status_text'] != 'completed', tasks)
	if skipped:
		print "Below tasks were skipped as they were not ready:"
		for task in skipped:
			print task['id'], task['status_text'], task['name'].encode(default_encoding)

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
			assert torrent.startswith('d8:announce'), 'Probably not a valid torrent file [%s...]' % repr(torrent[:11])
			info_hash = lixian_hash_bt.info_hash_from_content(torrent)
			if info_hash not in hashes:
				print 'Adding bt task', link
				client.add_torrent_task_by_content(torrent, os.path.basename(link))
			link_hashes.append(info_hash)
		elif os.path.exists(link):
			with open(link, 'rb') as stream:
				torrent = stream.read()
			assert torrent.startswith('d8:announce'), 'Probably not a valid torrent file [%s...]' % repr(torrent[:11])
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
		with open(args.input) as x:
			links.extend(line.strip() for line in x.readlines() if line.strip())
	if args.torrent:
		return find_torrents_task_to_download(client, links)
	if args.search or any(re.match(r'^\d+$', x) for x in args):
		return search_tasks(client, args, check='check_none')
	all_tasks = client.read_all_tasks()
	to_add = set(links)
	for t in all_tasks:
		for x in to_add:
			if link_equals(t['original_url'], x):
				to_add.remove(x)
				break
	if to_add:
		print 'Adding below tasks:'
		for link in links:
			if link in to_add:
				print link
		client.add_batch_tasks(to_add)
		for link in to_add:
			# add_batch_tasks doesn't work for bt task, add bt task one by one...
			if link.startswith('bt://'):
				client.add_task(link)
		all_tasks = client.read_all_tasks()
	tasks = []
	for link in links:
		for task in all_tasks:
			if link_equals(link, task['original_url']):
				tasks.append(task)
				break
		else:
			raise NotImplementedError('task not found, wired: '+link)
	return tasks

def download_task(args):
	args = parse_login_command_line(args, ['tool', 'output', 'output-dir', 'input'], ['delete', 'continue', 'overwrite', 'torrent', 'search'], alias={'o': 'output', 'i': 'input'}, default={'tool':lixian_config.get_config('tool', 'wget'),'delete':lixian_config.get_config('delete'),'continue':lixian_config.get_config('continue')})
	download = {'wget':wget_download, 'curl': curl_download, 'aria2':aria2_download, 'asyn':asyn_download, 'urllib2':urllib2_download}[args.tool]
	download_args = {'output_dir':args.output_dir, 'delete':args.delete, 'resuming':args._args['continue'], 'overwrite':args.overwrite}
	client = XunleiClient(args.username, args.password, args.cookies)
	links = None
	if len(args) > 1 or args.input:
		assert not args.output
		tasks = find_tasks_to_download(client, args)
		download_multiple_tasks(client, download, tasks, **download_args)
	elif args.torrent:
		assert not args.search
		assert len(args) == 1
		tasks = find_torrents_task_to_download(client, [args[0]])
		assert len(tasks) == 1
		download_single_task(client, download, tasks[0], args.output, **download_args)
	else:
		if len(args) == 1:
			assert not args.url
			args.url = args[0]
		tasks = search_tasks(client, args, status='all', check='check_none')
		if not tasks:
			assert args.url
			print 'Adding new task %s ...' % args.url
			client.add_task(args.url)
			tasks = client.read_all_completed()
			tasks = filter_tasks(tasks, 'original_url', args.url)
			assert tasks, 'task not found, wired'
		if args.output:
			assert len(tasks) == 1
			download_single_task(client, download, tasks[0], args.output, **download_args)
		else:
			download_multiple_tasks(client, download, tasks, **download_args)


def link_equals(x1, x2):
	from lixian_url import url_unmask, normalize_unicode_link
	x1 = url_unmask(x1)
	x2 = url_unmask(x2)
	if x1.startswith('ed2k://') and x2.startswith('ed2k://'):
		return lixian_hash_ed2k.parse_ed2k_link(x1) == lixian_hash_ed2k.parse_ed2k_link(x2)
		#import urllib
		#if type(x1) == unicode:
		#	x1 = x1.encode('utf-8')
		#if type(x2) == unicode:
		#	x2 = x2.encode('utf-8')
		#x1 = urllib.unquote(x1)
		#x2 = urllib.unquote(x2)
		#x1 = x1.replace('&amp;', '&')
		#x2 = x2.replace('&amp;', '&')
	elif x1.startswith('bt://') and x2.startswith('bt://'):
		x1 = x1.lower()
		x2 = x2.lower()
	elif x1.startswith('http://') and x2.startswith('http://'):
		x1 = normalize_unicode_link(x1)
		x2 = normalize_unicode_link(x2)
	return x1 == x2

def link_in(url, links):
	for link in links:
		if link_equals(url, link):
			return True

def filter_tasks(tasks, k, v):
	if k == 'name':
		matched = filter(lambda t: t[k].find(v) != -1, tasks)
	elif k == 'original_url':
		matched = filter(lambda t: link_equals(t[k], v), tasks)
	else:
		matched = filter(lambda t: t[k] == v, tasks)
	return matched

def search_tasks(client, args, status='all', check=True):
	if status == 'all':
		tasks = client.read_all_tasks()
	elif status == 'completed':
		tasks = client.read_all_tasks()
	else:
		raise NotImplementedError()
	found = []
	for x in args:
		if args.search:
			matched = filter_tasks(tasks, 'name', x)
		else:
			if re.match(r'^\d+$', x):
				matched = filter_tasks(tasks, 'id', x)
			elif re.match(r'\w+://', x):
				matched = filter_tasks(tasks, 'original_url', x)
			else:
				matched = filter_tasks(tasks, 'name', x)
		if check:
			if not matched:
				raise RuntimeError('Not task found for '+x)
			if check != 'check_none' and (not args.all) and len(matched) > 1:
				raise RuntimeError('Too many tasks found for '+x)
		found.extend(matched)
	return found


def list_task(args):
	args = parse_login_command_line(args, [],
	                                ['all', 'completed',
	                                 'id', 'name', 'status', 'size', 'dcid', 'original-url', 'download-url',
	                                 'search'],
									default={'id': True, 'name': True, 'status': True})
	client = XunleiClient(args.username, args.password, args.cookies)
	client.set_page_size(100)
	if len(args):
		tasks = search_tasks(client, args, status=(args.completed and 'completed' or 'all'), check=False)
	elif args.completed:
		tasks = client.read_all_completed()
	else:
		tasks = client.read_all_tasks()
	columns = ['id', 'name', 'status', 'size', 'dcid', 'original-url', 'download-url']
	columns = filter(lambda k: getattr(args, k), columns)
	for t in tasks:
		for k in columns:
			if k == 'id':
				print t['id'],
			elif k == 'name':
				print t['name'].encode(default_encoding),
			elif k == 'status':
				print t['status_text'],
			elif k == 'size':
				print t['size'],
			elif k == 'dcid':
				print t['dcid'],
			elif k == 'original-url':
				print t['original_url'],
			elif k == 'download-url':
				print t['xunlei_url'],
			else:
				raise NotImplementedError()
		print

def add_task(args):
	args = parse_login_command_line(args, ['input'], ['torrent'], alias={'i':'input'})
	assert len(args) or args.input
	client = XunleiClient(args.username, args.password, args.cookies)
	links = []
	links.extend(args)
	if args.input:
		with open(args.input) as x:
			links.extend(line.strip() for line in x.readlines() if line.strip())
	if not args.torrent:
		print 'Adding below tasks:'
		for link in links:
			print link
		client.add_batch_tasks(links)
		print 'All tasks added. Checking status...'
		tasks = client.read_all_tasks()
		for link in links:
			found = filter_tasks(tasks, 'original_url', link)
			if found:
				print found[0]['status_text'], link
			else:
				print 'unknown', link
	else:
		tasks = find_torrents_task_to_download(client, links)
		assert len(tasks) == len(links)
		print 'All tasks added:'
		for link, task in zip(links, tasks):
			print task['status_text'], link

def delete_task(args):
	args = parse_login_command_line(args, [], ['search', 'i', 'all'])
	client = XunleiClient(args.username, args.password, args.cookies)
	to_delete = search_tasks(client, args)
	print "Below files are going to be deleted:"
	for x in to_delete:
		print x['name']
	if args.i:
		yes_or_no = raw_input('Are your sure to delete below files from Xunlei cloud? ')
		while yes_or_no.lower() not in ('y', 'yes', 'n', 'no'):
			yes_or_no = raw_input('yes or no? ')
		if yes_or_no.lower() in ('y', 'yes'):
			pass
		elif yes_or_no.lower() in ('n', 'no'):
			raise RuntimeError('Deletion abort per user request.')
	client.delete_tasks(to_delete)

def pause_task(args):
	args = parse_login_command_line(args, [], ['search', 'i', 'all'])
	client = XunleiClient(args.username, args.password, args.cookies)
	to_pause = search_tasks(client, args)
	print "Below files are going to be paused:"
	for x in to_pause:
		print x['name']
	client.pause_tasks(to_pause)

def restart_task(args):
	args = parse_login_command_line(args, [], ['search', 'i', 'all'])
	client = XunleiClient(args.username, args.password, args.cookies)
	to_restart = search_tasks(client, args)
	print "Below files are going to be restarted:"
	for x in to_restart:
		print x['name']
	client.restart_tasks(to_restart)

def lixian_info(args):
	args = parse_login_command_line(args)
	client = XunleiClient(args.username, args.password, args.cookies, login=False)
	print 'id:', client.get_username()
	print 'internalid:', client.get_userid()
	print 'gdriveid:', client.get_gdriveid()

def lx_config(args):
	args = parse_command_line(args, [], ['print', 'delete'])
	if args.delete:
		assert len(args) == 1
		lixian_config.delete_config(args[0])
	elif args['print'] or not len(args):
		if len(args):
			assert len(args) == 1
			print lixian_config.get_config(args[0])
		else:
			print 'Loading', lixian_config.global_config.path, '...\n'
			print lixian_config.source_config()
			print lixian_config.global_config
	else:
		assert len(args) in (1, 2)
		if args[0] == 'password':
			print 'Saving password (encrypted) to', lixian_config.global_config.path
			lixian_config.put_config(args[0], encypt_password(args[1]))
		else:
			print 'Saving configuration to', lixian_config.global_config.path
			lixian_config.put_config(*args)

def print_hash(args):
	assert len(args) == 1
	print 'ed2k:', lixian_hash_ed2k.hash_file(args[0])
	print 'dcid:', lixian_hash.dcid_hash_file(args[0])

def execute_command(args=sys.argv[1:]):
	if not args:
		usage()
		sys.exit(1)
	command = args[0]
	if command.startswith('-'):
		if command in ('-h', '--help'):
			usage()
		elif command in ('-v', '--version'):
			print '0.0.x'
		else:
			usage()
			sys.exit(1)
		sys.exit(0)
	commands = {'login': login, 'logout': logout, 'download': download_task, 'list': list_task, 'add': add_task, 'delete': delete_task, 'pause': pause_task, 'restart': restart_task, 'info': lixian_info, 'config': lx_config, 'hash': print_hash}
	if command not in commands:
		usage()
		sys.exit(1)
	commands[command](args[1:])

if __name__ == '__main__':
	execute_command()


