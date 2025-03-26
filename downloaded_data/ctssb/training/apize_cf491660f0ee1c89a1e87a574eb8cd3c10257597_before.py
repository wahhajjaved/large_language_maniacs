#!/usr/bin/env python3

from __future__ import absolute_import

from apize.exceptions import *
from apize.http_request import send_request


def apize_raw(url, method='GET'):
	"""
	Convert data and params dict -> json.
	"""
	def decorator(func):
		def wrapper(*args, **kwargs):
			elem = func(*args, **kwargs)

			if type(elem) is not dict:
				raise BadReturnVarType(func.__name__)

			response = send_request(url, method, 
				elem.get('data', {}),
				elem.get('args', {}),
				elem.get('params', {}),
				elem.get('headers', {}),
				elem.get('cookies', {}),
				elem.get('timeout', 8),
				elem.get('is_json', False),
				elem.get('verify_cert', False)
			)

			return response
		return wrapper

	return decorator
