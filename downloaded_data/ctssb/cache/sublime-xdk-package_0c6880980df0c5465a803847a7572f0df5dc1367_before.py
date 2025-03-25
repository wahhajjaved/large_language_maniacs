# coding: utf-8

# Copyright 2015 Intel Corporation All Rights Reserved.
# The source code, information and material ("Material") contained herein is owned by Intel Corporation or its suppliers or licensors, 
# and title to such Material remains with Intel Corporation or its suppliers or licensors. The Material contains proprietary information
# of Intel or its suppliers and licensors. The Material is protected by worldwide copyright laws and treaty provisions. No part of the 
# Material may be used, copied, reproduced, modified, published, uploaded, posted, transmitted, distributed or disclosed in any way without
# Intel's prior express written permission. No license under any patent, copyright or other intellectual property rights in the Material is
# granted to or conferred upon you, either expressly, by implication, inducement, estoppel or otherwise. Any license under such intellectual
# property rights must be express and approved by Intel in writing.
#
# Unless otherwise agreed by Intel in writing, you may not remove or alter this notice or any other notice embedded in Materials by Intel or
# Intel's suppliers or licensors in any way.

import sublime, sublime_plugin
import os
import json
import sys
import re

IS_PYTHON_2 = sys.version < '3'

if IS_PYTHON_2:
	from urllib2		import Request, urlopen, HTTPError, URLError
else:
	from urllib.request import Request, urlopen
	from urllib.error 	import HTTPError, URLError

### CONFIGURATION
PLUGIN_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PLUGIN_PATH, 'xdk_plugin.conf')
API_VERSION = '0.0.1'
DEBUG_ENABLED = True
MSGS = {
	'SPECIFIED_DIRECTORY_IS_NOT_XDK': u'Path specified in configuration is not Intel® XDK one. Please enter correct XDK folder in the prompt below.',
	'CAN_NOT_PARSE_SERVER_DATA': u'Can not parse XDK server data file.',
	'CAN_NOT_VALIDATE_SECRET_KEY': u'Can not authorize to Intel® XDK.',
	'XDK_CONNECTION_FAILED': u'Connection to XDK failed. Do you have Intel® XDK running?',
	'CAN_NOT_GET_FOLDER': u'Can not get current folder. Do you have project folder opened?',
	'CAN_NOT_PARSE_RESPONSE_JSON': u'Can not parse response JSON',
	'CAN_NOT_FIND_XDK': u'Can not find Intel® XDK installation'
}
### E.O. CONFIGURATION

def _print(s):
	if DEBUG_ENABLED:
		print(s)

class UrllibHelper:
	@staticmethod
	def is_connection_refused(exception):
		return isinstance(exception, (HTTPError, URLError) if IS_PYTHON_2 else (HTTPError, URLError, ConnectionRefusedError))
	@staticmethod
	def extract_status(response):
		#return response['code' if IS_PYTHON_2 else 'status'];
		return getattr(response, 'code' if IS_PYTHON_2 else 'status')
	@staticmethod
	def extract_headers(response):
		return response.headers if IS_PYTHON_2 else dict(response.info().items())

class XDKException(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class XDKPluginCore:
	# contents of plugin's conf file
	config_contents = None
	# xdk system dir
	xdk_dir = None
	# path to server-data.txt file
	server_data_path = None
	# entrance point for plugin-listener
	plugin_base_path = None
	# entrace to xdk
	base_path = None

	auth_secret = None
	auth_cookie = None

	def make_request(self, addr, params={}, headers={}):
		_print('make_request: addr=' + addr);
		if params:
			params['_api_version'] = API_VERSION
			params = json.dumps(params)
			_print('make_request: params=' + str(params))
			headers['Content-Type'] = 'application/json'
		else:
			params = ''


		request = Request(addr, params.encode('utf-8'), headers)
		response = urlopen(request)
		return response

	def invoke_command(self, cmd):
		def _make_request():
			try: 
				return self.make_request(self.plugin_base_path, cmd, {
					'Cookie' : self.auth_cookie
				})
			except HTTPError as e:
				_print("Caught HTTPError' " + str(e.code))
				if (int(e.code) == 401):
					_print('401, trying to get new one'); 
					self.reset_authorization()
					self.prepare()
					return self.make_request(self.plugin_base_path, cmd, {
						'Cookie' : self.auth_cookie
					})
				else:
					raise

		try:
			response = _make_request()
			content = response.read()
			_print('invoke_command: content=')
			_print(content);
			try:
				parsed = json.loads(content.decode())
			except:
				raise XDKException(MSGS['CAN_NOT_PARSE_RESPONSE_JSON'])
		
			if parsed.get('error'):
				raise XDKException(parsed.get('msg') or 'Unknown error')

		except XDKException as e:
			sublime.error_message(e.value)
		except:
			_print('invoke_command: not XDKException')
			sublime.error_message(MSGS['XDK_CONNECTION_FAILED'])


	def get_data_path(self):
		p = sys.platform
		path = None
		if p == 'darwin' and os.getenv('HOME'):
			path = os.path.join(os.getenv('HOME'), 'Library', 'Application Support', 'XDK')
		elif p == 'win32' and os.getenv('LOCALAPPDATA'):
			path = os.path.join(os.getenv('LOCALAPPDATA'), 'XDK')
		elif p == 'linux2' and os.getenv('HOME'):
			path = os.path.join(os.getenv('HOME'), '.config', 'XDK')
		server_data = os.path.join(path, 'server-data.txt')
		if path is None or not os.path.isfile(server_data) or not os.access(server_data, os.R_OK):
			raise XDKException(MSGS['CAN_NOT_FIND_XDK']) 
		return path


	def load_config_data(self):
		if self.plugin_base_path is not None:
			_print('load_config_data: already has plugn_base_path')
			return

		_print('load_config_data: trying to read CONFIG_FILE=' + CONFIG_FILE);
		with open(CONFIG_FILE, 'r') as f:
			self.config_contents = f.read();
		_print('load_config_data: CONFIG_FILE read')
		if not self.config_contents:
			self.find_xdk_installation()
		self.xdk_dir = self.config_contents.strip()
		_print('load_config_data: xdk_dir=' + self.xdk_dir)
		self.server_data_path = os.path.join(self.xdk_dir, 'server-data.txt')
		_print('load_config_data: server_data_path=' + self.server_data_path)
		if not os.path.isfile(self.server_data_path):
			raise XDKException(MSGS['SPECIFIED_DIRECTORY_IS_NOT_XDK'])
		server_data_contents = None;
		with open(self.server_data_path, 'r') as f:
			server_data_contents = f.read()
		_print('load_config_data: server_data_contents=' + server_data_contents);	
		try:
			decoded = json.loads(server_data_contents.replace('[END]', ''))
			self.auth_secret = decoded['secret']
			self.base_path = 'http://localhost:' + str(decoded['port']);
			self.plugin_base_path = 'http://localhost:' + str(decoded['port']) + '/http-services/plugin-listener/plugin/entrance'
			_print('load_config_data: auth_secret=' + self.auth_secret);
			_print('load_config_data: base_path=' + self.base_path);
			_print('load_config_data: plugin_base_path=' + self.plugin_base_path);
		except:
			raise XDKException(MSGS['CAN_NOT_PARSE_SERVER_DATA']);

	def authorize(self):
		if self.auth_cookie is not None:
			_print('authorize: auth_cookie is not none');
			return 

		_print('authorize: making request to /validate');	
		response = self.make_request(self.base_path + '/validate', {}, {'x-xdk-local-session-secret': self.auth_secret })
		headers = UrllibHelper.extract_headers(response)
		status = UrllibHelper.extract_status(response)
		_print('authorize: response.status=' + str(status))
		_print('authorize: headers length=' + str(len(headers)))
		if status != 200 or 'Set-Cookie' not in headers: 
			raise XDKException(MSGS['CAN_NOT_VALIDATE_SECRET_KEY'])
		self.auth_cookie = headers['Set-Cookie']
		_print('authorize: auth_cookie=' + self.auth_cookie);

	def reset_authorization(self):
		self.xdk_dir = None
		self.auth_secret = None
		self.auth_cookie = None
		self.plugin_base_path = None
	
	def find_xdk_installation(self):
		_print('find_xdk_installation: self.xdk_dir=' + str(self.xdk_dir))
		if self.xdk_dir is not None:
			_print('find_xdk_installation: self.xdk_dir is not none')
			return self.xdk_dir 	
		path = self.get_data_path()
		_print('find_xdk_installation: found path' + path)
		with open(CONFIG_FILE, 'w') as f:
			f.write(path);		
		_print('find_xdk_installation: CONFIG_FILE written')

	def prepare(self):
		_print('prepare:')
		try:
			self.find_xdk_installation()
			self.load_config_data()
			self.authorize()
			return True

		except XDKException as e:
			sublime.error_message(e.value);
			return False
			
		except Exception as e:
			if UrllibHelper.is_connection_refused(e):
				_print('prepare: is_connection_refused exception');
				sublime.error_message(MSGS['XDK_CONNECTION_FAILED'])
				return False
			else:
				raise
		

	def prepare_request_data(self):
		folder = os.path.dirname(self.view.file_name())
		return {
			'folder': 				folder,
			'filename': 			self.view.file_name()
		}






