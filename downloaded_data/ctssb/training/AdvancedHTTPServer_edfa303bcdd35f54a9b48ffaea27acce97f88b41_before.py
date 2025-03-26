#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  AdvancedHTTPServer.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the SecureState Consulting nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

#  Homepage: https://gist.github.com/zeroSteiner/4502576
#  Author:   Spencer McIntyre (zeroSteiner)

"""
# The AdvancedHTTPServer systemd service unit file
#
# Quick HowTo:
# 1. Copy this file to /etc/systemd/system/pyhttpd.service
# 2. Edit <USER> and run parameters appropriately in the ExecStart option
# 3. Set configuration settings in /etc/pyhttpd.conf
# 4. Run "systemctl daemon-reload"

[Unit]
Description=Python Advanced HTTP Server
After=network.target

[Service]
Type=simple
ExecStart=/sbin/runuser -l <USER> -c "/usr/bin/python -m AdvancedHTTPServer -c /etc/pyhttpd.conf"
ExecStop=/bin/kill -INT $MAINPID

[Install]
WantedBy=multi-user.target
"""

__version__ = '0.1'
__all__ = [ 'AdvancedHTTPServer', 'AdvancedHTTPServerRequestHandler', 'AdvancedHTTPServerRPCClient', 'AdvancedHTTPServerRPCError' ]

import os
import re
import cgi
import ssl
import sys
import hmac
import json
import pickle
import shutil
import hashlib
import httplib
import logging
import logging.handlers
import mimetypes
import posixpath

from SocketServer import ThreadingMixIn
from urlparse import urlparse, parse_qs
from urllib import unquote as url_unquote
from urllib import quote as url_quote
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

SERIALIZER_DRIVERS = {}
SERIALIZER_DRIVERS['binary/python-pickle'] = {'loads':pickle.loads, 'dumps':pickle.dumps}
SERIALIZER_DRIVERS['binary/json'] = {'loads':json.loads, 'dumps':json.dumps}

try:
	import msgpack
	SERIALIZER_DRIVERS['binary/message-pack'] = {'loads':msgpack.loads, 'dumps':msgpack.dumps}
except ImportError:
	pass

if hasattr(logging, 'NullHandler'):
	logging.getLogger('AdvancedHTTPServer').addHandler(logging.NullHandler())

class SectionConfigParser:
	__version__ = '0.1'
	def __init__(self, section_name, config_parser):
		self.section_name = section_name
		self.config_parser = config_parser

	def get_raw(self, option, opt_type, default = None):
		get_func = getattr(self.config_parser, 'get' + opt_type)
		if default == None:
			return get_func(self.section_name, option)
		elif self.config_parser.has_option(self.section_name, option):
			return get_func(self.section_name, option)
		else:
			return default

	def get(self, option, default = None):
		return self.get_raw(option, '', default)

	def getint(self, option, default = None):
		return self.get_raw(option, 'int', default)

	def getfloat(self, option, default = None):
		return self.get_raw(option, 'float', default)

	def getboolean(self, option, default = None):
		return self.get_raw(option, 'boolean', default)

	def has_option(self, option):
		return self.config_parser.has_option(self.section_name, option)

	def options(self):
		return self.config_parser.options(self.section_name)

	def items(self):
		return self.config_parser.items(self.section_name)

def get_server_from_config(config, section_name):
	config = SectionConfigParser(section_name, config)
	port = config.getint('port')
	web_root = config.get('web_root')

	ip = config.get('ip', '0.0.0.0')
	use_ssl = config.getboolean('use_ssl', False)
	ssl_certfile = None
	if use_ssl:
		ssl_certfile = config.get('ssl_cert')

	password = None
	if config.has_option('password'):
		password = config.get('password')
		password_type = config.get('password_type', 'md5')

	server = AdvancedHTTPServer(AdvancedHTTPServerRequestHandler, address = (ip, port), use_ssl = use_ssl, ssl_certfile = ssl_certfile)
	if password:
		server.auth_add_creds('', password, pwtype = password_type)
	server.serve_files = True
	server.serve_files_root = web_root
	return server

class AdvancedHTTPServerRPCError(Exception):
	def __init__(self, message, status, remote_exception = None):
		self.message = message
		self.status = status
		self.remote_exception = remote_exception

	def __repr__(self):
		return "{0}(remote_exception={1})".format(self.__class__.__name__, self.is_remote_exception)

	@property
	def is_remote_exception(self):
		return bool(self.remote_exception != None)

class AdvancedHTTPServerRPCClient(object):
	def __init__(self, address, use_ssl = False, username = None, password = None, uri_base = '/', hmac_key = None):
		self.host = address[0]
		self.port = address[1]

		self.use_ssl = use_ssl
		self.uri_base = uri_base
		self.username = username
		self.password = password
		self.hmac_key = hmac_key
		if self.use_ssl:
			self.client = httplib.HTTPSConnection(self.host, self.port)
		else:
			self.client = httplib.HTTPConnection(self.host, self.port)

	def encode(self,data):
		return pickle.dumps(data)

	def decode(self,data):
		return pickle.loads(data)

	def call(self, meth, *options):
		options = self.encode(options)

		headers = {}
		headers['Content-Type'] = 'binary/python-pickle'
		headers['Content-Length'] = str(len(options))

		if self.hmac_key != None:
			hmac_calculator = hmac.new(self.hmac_key, digestmod = hashlib.sha1)
			hmac_calculator.update(options)
			headers['HMAC'] = hmac_calculator.hexdigest()

		if self.username != None and self.password != None:
			headers['Authorization'] = 'Basic ' + (self.username + ':' + self.password).encode('base64')

		self.client.request("RPC", self.uri_base + meth, options, headers)
		resp = self.client.getresponse()
		if resp.status != 200:
			raise AdvancedHTTPServerRPCError(resp.reason, resp.status)

		resp_data = resp.read()
		if self.hmac_key != None:
			hmac_digest = resp.getheader('hmac')
			if not isinstance(hmac_digest, str):
				raise AdvancedHTTPServerRPCError('hmac validation error', resp.status)
			hmac_digest = hmac_digest.lower()
			hmac_calculator = hmac.new(self.hmac_key, digestmod = hashlib.sha1)
			hmac_calculator.update(resp_data)
			if hmac_digest != hmac_calculator.hexdigest():
				raise AdvancedHTTPServerRPCError('hmac validation error', resp.status)
		resp_data = self.decode(resp_data)
		if not ('exception_occurred' in resp_data and 'result' in resp_data):
			raise AdvancedHTTPServerRPCError('missing response information', resp.status)
		if resp_data['exception_occurred']:
			raise AdvancedHTTPServerRPCError('remote method incured an exception', resp.status, remote_exception = resp_data['exception'])
		return resp_data['result']

class AdvancedHTTPServerNonThreaded(HTTPServer):
	def __init__(self, *args, **kwargs):
		self.logger = logging.getLogger('AdvancedHTTPServer')
		self.allow_reuse_address = True
		self.using_ssl = False
		self.serve_files = False
		self.serve_files_root = os.getcwd()
		self.serve_files_list_directories = False # irrelevant if serve_files == False
		self.serve_robots_txt = True
		self.rpc_hmac_key = None
		self.basic_auth = None
		self.robots_txt = 'User-agent: *\nDisallow: /\n'
		self.server_version = 'HTTPServer/' + __version__
		HTTPServer.__init__(self, *args, **kwargs)

class AdvancedHTTPServerThreaded(ThreadingMixIn, AdvancedHTTPServerNonThreaded):
	pass

class AdvancedHTTPServerRequestHandler(BaseHTTPRequestHandler):
	if not mimetypes.inited:
		mimetypes.init() # try to read system mime.types
	extensions_map = mimetypes.types_map.copy()
	extensions_map.update({
		'': 'application/octet-stream', # Default
		'.py': 'text/plain',
		'.rb': 'text/plain',
		'.c':  'text/plain',
		'.h':  'text/plain',
		})

	def __init__(self, *args, **kwargs):
		self.handler_map = {}
		self.rpc_handler_map = {}
		self.install_handlers()
		BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

	def version_string(self):
		return self.server.server_version

	def install_handlers(self):
		pass # over ride me

	def respond_not_found(self):
		self.send_response(404, 'Resource Not Found')
		self.send_header('Content-Type', 'text/html')
		self.end_headers()
		self.wfile.write('Resource Not Found\n')
		return

	def respond_redirect(self, location = '/'):
		self.send_response(301)
		self.send_header('Location', location)
		self.end_headers()
		return

	def respond_unauthorized(self, request_authentication = False):
		self.send_response(401)
		if request_authentication:
			self.send_header('WWW-Authenticate', 'Basic realm="' + self.server_version + '"')
		self.send_header('Content-Type', 'text/html')
		self.end_headers()
		self.wfile.write('Unauthorized\n')
		return

	def dispatch_handler(self, query = {}):
		# normalize the path
		# abandon query parameters
		self.path = self.path.split('?', 1)[0]
		self.path = self.path.split('#', 1)[0]
		self.original_path = url_unquote(self.path)
		self.path = posixpath.normpath(self.original_path)
		words = self.path.split('/')
		words = filter(None, words)
		tmp_path = ''
		for word in words:
			drive, word = os.path.splitdrive(word)
			head, word = os.path.split(word)
			if word in (os.curdir, os.pardir):
				continue
			tmp_path = os.path.join(tmp_path, word)
		self.path = tmp_path

		if self.path == 'robots.txt' and self.server.serve_robots_txt:
			self.send_response(200)
			self.send_header('Content-type', 'text/plain')
			self.end_headers()
			self.wfile.write(self.server.robots_txt)
			return

		for (path_regex, handler) in self.handler_map.items():
			if re.match(path_regex, self.path):
				handler(query)
				return

		if not self.server.serve_files:
			self.respond_not_found()
			return

		file_path = self.server.serve_files_root
		file_path = os.path.join(file_path, tmp_path)
		if os.path.isdir(file_path) and self.server.serve_files_list_directories:
			if not self.original_path.endswith('/'):
				# redirect browser - doing basically what apache does
				self.send_response(301)
				self.send_header('Location', self.path + '/')
				self.end_headers()
				return
			for index in ['index.html', 'index.htm']:
				index = os.path.join(file_path, index)
				if os.path.exists(index):
					file_path = index
					break
			else:
				try:
					dir_contents = os.listdir(file_path)
				except os.error:
					self.respond_not_found()
					return None
				dir_contents.sort(key=lambda a: a.lower())
				f = StringIO()
				displaypath = cgi.escape(url_unquote(self.path))
				f.write('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
				f.write('<html>\n<title>Directory listing for ' + displaypath + '</title>\n')
				f.write('<body>\n<h2>Directory listing for ' + displaypath + '</h2>\n')
				f.write('<hr>\n<ul>\n')
				for name in dir_contents:
					fullname = os.path.join(file_path, name)
					displayname = linkname = name
					# Append / for directories or @ for symbolic links
					if os.path.isdir(fullname):
						displayname = name + "/"
						linkname = name + "/"
					if os.path.islink(fullname):
						displayname = name + "@"
						# Note: a link to a directory displays with @ and links with /
					f.write('<li><a href="' + url_quote(linkname) + '">' + cgi.escape(displayname) + '</a>\n')
				f.write('</ul>\n<hr>\n</body>\n</html>\n')
				length = f.tell()
				f.seek(0)
				self.send_response(200)
				encoding = sys.getfilesystemencoding()
				self.send_header('Content-Type', 'text/html; charset=' + encoding)
				self.send_header('Content-Length', str(length))
				self.end_headers()
				shutil.copyfileobj(f, self.wfile)
				f.close()
				return

		elif os.path.isfile(file_path):
			try:
				file_obj = open(file_path, 'rb')
			except IOError:
				self.respond_not_found()
				return None
			self.send_response(200)
			self.send_header('Content-Type', self.guess_mime_type(file_path))
			fs = os.fstat(file_obj.fileno())
			self.send_header('Content-Length', str(fs[6]))
			self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
			self.end_headers()
			shutil.copyfileobj(file_obj, self.wfile)
			file_obj.close()
			return

		self.respond_not_found()
		return

	def guess_mime_type(self, path):
		base, ext = posixpath.splitext(path)
		if ext in self.extensions_map:
			return self.extensions_map[ext]
		ext = ext.lower()
		if ext in self.extensions_map:
			return self.extensions_map[ext]
		else:
			return self.extensions_map['']

	def stock_handler_respond_unauthorized(self, query):
		self.respond_unauthorized()
		return

	def stock_handler_respond_not_found(self, query):
		self.respond_not_found()
		return

	def check_authorization(self):
		try:
			if self.server.basic_auth == None:
				return True
			auth_info = self.headers.getheader('Authorization')
			if not auth_info:
				return False
			auth_info = auth_info.split()
			if len(auth_info) != 2:
				return False
			if auth_info[0] != 'Basic':
				return False

			auth_info = auth_info[1].decode('base64')
			username = auth_info.split(':')[0]
			password = ':'.join(auth_info.split(':')[1:])
			if not username in self.server.basic_auth:
				self.server.logger.warning('received invalid username: ' + username)
				return False
			password_data = self.server.basic_auth[username]

			if password_data['type'] == 'plain':
				if password == password_data['value']:
					return True
			elif password_data['type'] == 'md5':
				if hashlib.new('md5', password).hexdigest() == password_data['value']:
					return True
			elif password_data['type'] == 'sha1':
				if hashlib.new('sha1', password).hexdigest() == password_data['value']:
					return True
			self.server.logger.warning('received invalid password from user: ' + username)
			return False
		except:
			return False

	def do_GET(self):
		if not self.check_authorization():
			self.respond_unauthorized(request_authentication = True)
			return
		uri = urlparse(self.path)
		self.path = uri.path
		query = parse_qs(uri.query)

		self.dispatch_handler(query)
		return

	def do_POST(self):
		if not self.check_authorization():
			self.respond_unauthorized(request_authentication = True)
			return
		content_length = int(self.headers.getheader('content-length') or 0)
		data = self.rfile.read(content_length)
		query = parse_qs(data, keep_blank_values = 1)

		self.dispatch_handler(query)
		return

	def do_OPTIONS(self):
		available_methods = map(lambda x: x[3:], filter(lambda x: x.startswith('do_'), dir(self)))
		if 'RPC' in available_methods and len(self.rpc_handler_map) == 0:
			available_methods.remove('RPC')
		self.send_response(200)
		self.send_header('Allow', ','.join(available_methods))
		self.end_headers()

	def do_RPC(self):
		if not self.check_authorization():
			self.respond_unauthorized(request_authentication = True)
			return

		data_length = self.headers.getheader('content-length')
		if self.headers.getheader('content-length') == None:
			self.send_error(411)
			return

		data_type = self.headers.getheader('content-type')
		if data_type == None:
			self.send_error(400, 'Missing Header: Content-Type')
			return

		if not data_type in SERIALIZER_DRIVERS:
			self.send_error(400, 'Invalid Content-Type')
			return
		serializer = SERIALIZER_DRIVERS[data_type]

		try:
			data_length = int(self.headers.getheader('content-length'))
			data = self.rfile.read(data_length)
		except:
			self.send_error(400, 'Invalid Data')
			return

		if self.server.rpc_hmac_key != None:
			hmac_digest = self.headers.getheader('hmac')
			if not isinstance(hmac_digest, str):
				self.respond_unauthorized(request_authentication = True)
				return
			hmac_digest = hmac_digest.lower()
			hmac_calculator = hmac.new(self.server.rpc_hmac_key, digestmod = hashlib.sha1)
			hmac_calculator.update(data)
			if hmac_digest != hmac_calculator.hexdigest():
				self.respond_unauthorized(request_authentication = True)
				return

		try:
			data = serializer['loads'](data)
			if type(data) == list:
				data = tuple(data)
			assert(type(data) == tuple)
		except:
			self.send_error(400, 'Invalid Data')
			return

		if not self.path in self.rpc_handler_map:
			self.send_error(501, 'Method Not Implemented')
			return

		self.server.logger.info('running RPC method: ' + self.path)
		response = { 'result':None, 'exception_occurred':False }
		try:
			result = self.rpc_handler_map[self.path](*data)
			response['result'] = result
		except Exception as error:
			response['exception_occurred'] = True
			exc = {}
			exc['name'] = error.__class__.__name__
			exc['message'] = error.message
			response['exception'] = exc
			self.server.logger.error('error: ' + error.__class__.__name__ + ' occurred while calling RPC method: ' + self.path)

		try:
			response = serializer['dumps'](response)
		except:
			self.send_error(500, 'Failed To Pack Response')
			return

		self.send_response(200)
		self.send_header('Content-Type', data_type)
		if self.server.rpc_hmac_key != None:
			hmac_calculator = hmac.new(self.server.rpc_hmac_key, digestmod = hashlib.sha1)
			hmac_calculator.update(response)
			self.send_header('HMAC', hmac_calculator.hexdigest())
		self.end_headers()
		self.wfile.write(response)
		return

	def log_error(self, format, *args):
		self.server.logger.warning(self.address_string() + ' ' + format % args)

	def log_message(self, format, *args):
		self.server.logger.info(self.address_string() + ' ' + format % args)

class AdvancedHTTPServer(object):
	"""
	Setable properties:
		serve_files (boolean)
		serve_files_root (string)
		serve_files_list_directories (boolean)
		serve_robots_txt (boolean)
		rpc_hmac_key (string)
		server_version (string)
	"""
	def __init__(self, request_handler, address = None, use_threads = True, use_ssl = False, ssl_certfile = None):
		if address == None:
			if use_ssl:
				if os.getuid():
					address = ('0.0.0.0', 8443)
				else:
					address = ('0.0.0.0', 443)
			else:
				if os.getuid():
					address = ('0.0.0.0', 8080)
				else:
					address = ('0.0.0.0', 80)
		self.address = address
		self.use_ssl = use_ssl
		self.ssl_certfile = ssl_certfile
		self.logger = logging.getLogger('AdvancedHTTPServer')

		if use_threads:
			self.http_server = AdvancedHTTPServerThreaded(address, request_handler)
		else:
			self.http_server = AdvancedHTTPServerNonThreaded(address, request_handler)
		self.logger.info('listening on ' + address[0] + ':' + str(address[1]))

		if use_ssl:
			self.http_server.socket = ssl.wrap_socket(self.http_server.socket, certfile = ssl_certfile, server_side = True)
			self.http_server.using_ssl = True
			self.logger.info(address[0] + ':' + str(address[1]) + ' - ssl has been enabled')

	def fork_and_serve_forever(self):
		if not hasattr(os, 'fork'):
			raise Exception('os.fork is not available')
		child_pid = os.fork()
		if child_pid == 0:
			self.serve_forever()
		else:
			self.logger.info(self.address[0] + ':' + str(self.address[1]) + ' - forked child process: ' + str(child_pid))
		return child_pid

	def serve_forever(self):
		self.http_server.serve_forever()

	@property
	def serve_files(self):
		return self.http_server.serve_files

	@serve_files.setter
	def serve_files(self, value):
		value = bool(value)
		if self.http_server.serve_files == value:
			return
		self.http_server.serve_files = value
		if value:
			self.logger.info(self.address[0] + ':' + str(self.address[1]) + ' - serving files has been enabled')
		else:
			self.logger.info(self.address[0] + ':' + str(self.address[1]) + ' - serving files has been disabled')

	@property
	def serve_files_root(self):
		return self.http_server.serve_files_root

	@serve_files_root.setter
	def serve_files_root(self, value):
		self.http_server.serve_files_root = os.path.abspath(value)

	@property
	def serve_files_list_directories(self):
		return self.http_server.serve_files_list_directories

	@serve_files_list_directories.setter
	def serve_files_list_directories(self, value):
		self.http_server.serve_files_list_directories = bool(value)

	@property
	def serve_robots_txt(self):
		return self.http_server.serve_robots_txt

	@serve_robots_txt.setter
	def serve_robots_txt(self, value):
		self.http_server.serve_robots_txt = bool(value)

	@property
	def rpc_hmac_key(self):
		return self.http_server.rpc_hmac_key

	@rpc_hmac_key.setter
	def rpc_hmac_key(self, value):
		self.http_server.rpc_hmac_key = str(value)

	@property
	def server_version(self):
		return self.http_server.server_version

	@server_version.setter
	def server_version(self, value):
		self.http_server.server_version = str(value)

	def auth_set(self, status):
		if not bool(status):
			self.http_server.basic_auth = None
			self.logger.info(self.address[0] + ':' + str(self.address[1]) + ' - basic authentication has been disabled')
		else:
			self.http_server.basic_auth = {}
			self.logger.info(self.address[0] + ':' + str(self.address[1]) + ' - basic authentication has been enabled')

	def auth_add_creds(self, username, password, pwtype = 'plain'):
		pwtype = pwtype.lower()
		if not pwtype in ('plain', 'md5', 'sha1'):
			raise Exception('invalid password type, must be (\'plain\', \'md5\', \'sha1\')')
		if self.http_server.basic_auth == None:
			self.http_server.basic_auth = {}
			self.logger.info(self.address[0] + ':' + str(self.address[1]) + ' - basic authentication has been enabled')
		if pwtype != 'plain':
			password = password.lower()
		self.http_server.basic_auth[username] = {'value':password, 'type':pwtype}

def main():
	try:
		import argparse
		import ConfigParser
		parser = argparse.ArgumentParser(description = 'AdvancedHTTPServer', conflict_handler='resolve')
		parser.epilog = 'When a config file is specified with --config the --ip, --port and --web-root options are all ignored.'
		parser.add_argument('-w', '--web-root', dest = 'web_root', action = 'store', default = '.', help = 'path to the web root directory')
		parser.add_argument('-p', '--port', dest = 'port', action = 'store', default = 8080, type = int, help = 'port to serve on')
		parser.add_argument('-i', '--ip', dest = 'ip', action = 'store', default = '0.0.0.0', help = 'the ip address to serve on')
		parser.add_argument('--password', dest = 'password', action = 'store', default = None, help = 'password to use for basic authentication')
		parser.add_argument('--log-file', dest = 'log_file', action = 'store', default = None, help = 'log information to a file')
		parser.add_argument('-c', '--conf', dest = 'config', action = 'store', default = None, type = argparse.FileType('r'), help = 'read settings from a config file')
		parser.add_argument('-v', '--version', action = 'version', version = parser.prog + ' Version: ' + __version__)
		parser.add_argument('-L', '--log', dest = 'loglvl', action = 'store', choices = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default = 'INFO', help = 'set the logging level')
		arguments = parser.parse_args()

		logging.getLogger('').setLevel(logging.DEBUG)
		console_log_handler = logging.StreamHandler()
		console_log_handler.setLevel(getattr(logging, arguments.loglvl))
		console_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
		logging.getLogger('').addHandler(console_log_handler)

		if arguments.log_file:
			main_file_handler = logging.handlers.RotatingFileHandler(arguments.log_file, maxBytes = 262144, backupCount = 5)
			main_file_handler.setLevel(logging.DEBUG)
			main_file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)-30s %(levelname)-10s %(message)s"))
			logging.getLogger('').setLevel(logging.DEBUG)
			logging.getLogger('').addHandler(main_file_handler)

		if arguments.config:
			config = ConfigParser.ConfigParser()
			config.readfp(arguments.config)
			server = get_server_from_config(config, 'server')
			web_root = server.serve_files_root
		else:
			server = AdvancedHTTPServer(AdvancedHTTPServerRequestHandler, address = (arguments.ip, arguments.port))
			web_root = arguments.web_root
		if arguments.password:
			server.auth_add_creds('', arguments.password)
	except ImportError:
		server = AdvancedHTTPServer(AdvancedHTTPServerRequestHandler)
		web_root = '.'

	server.serve_files = True
	server.serve_files_root = web_root
	try:
		server.serve_forever()
	except Exception as err:
		pass
	logging.shutdown()
	return 0

if __name__ == '__main__':
	main()
