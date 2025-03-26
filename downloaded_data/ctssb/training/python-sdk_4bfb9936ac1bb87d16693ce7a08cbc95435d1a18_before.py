# -*- coding: utf-8 -*-
import os
import unittest
import string
import random
try:
	import zlib as binascii
except ImportError:
	import binascii
import cStringIO

from qiniu import conf
from qiniu import rs
from qiniu import io

conf.ACCESS_KEY = os.getenv("QINIU_ACCESS_KEY")
conf.SECRET_KEY = os.getenv("QINIU_SECRET_KEY")
bucket_name = os.getenv("QINIU_BUCKET_NAME")

policy = rs.PutPolicy(bucket_name)
extra = io.PutExtra()
extra.mime_type = "text/plain"

def r(length):
	lib = string.ascii_uppercase
	return ''.join([random.choice(lib) for i in range(0, length)])

class TestUp(unittest.TestCase):
	def test(self):
		def test_put():
			key = "test_%s" % r(9)
			params = "op=3"
			data = "hello bubby!"
			extra.check_crc = 2
			extra.crc32 = binascii.crc32(data) & 0xFFFFFFFF
			ret, err = io.put(policy.token(), key, data, extra)
			assert err is None

		def test_put_same_crc():
			key = "test_%s" % r(9)
			data = "hello bubby!"
			extra.check_crc = 2
			ret, err = io.put(policy.token(), key, data, extra)
			assert err is None

		def test_put_no_key():
			data = r(100)
			ret, err = io.put(policy.token(), key=None, data=data)
			assert err is None

		def test_put_unicode1():
			key = "test_%s" % r(9) + '你好'
			data = key
			ret, err = io.put(policy.token(), key, data)
			assert err is None
			assert ret[u'key'].endswith(u'你好')

		def test_put_unicode2():
			key = "test_%s" % r(9) + '你好'
			data = key
			data = data.decode('utf8')
			ret, err = io.put(policy.token(), key, data)
			assert err is None
			assert ret[u'key'].endswith(u'你好')

		def test_put_unicode3():
			key = "test_%s" % r(9) + '你好'
			data = key
			key = key.decode('utf8')
			ret, err = io.put(policy.token(), key, data)
			assert err is None
			assert ret[u'key'].endswith(u'你好')

		def test_put_unicode4():
			key = "test_%s" % r(9) + '你好'
			data = key
			key = key.decode('utf8')
			data = data.decode('utf8')
			ret, err = io.put(policy.token(), key, data)
			assert err is None
			assert ret[u'key'].endswith(u'你好')

		def test_put_StringIO():
			key = "test_%s" % r(9)
			data = cStringIO.StringIO('hello buddy!')
			ret, err = io.put(policy.token(), key, data)
			assert err is None


		test_put()
		test_put_same_crc()
		test_put_no_key()
		test_put_unicode1()
		test_put_unicode2()
		test_put_unicode3()
		test_put_unicode4()
		test_put_StringIO()

	def test_put_file(self):
		localfile = "%s" % __file__
		key = "test_%s" % r(9)

		extra.check_crc = 1
		ret, err = io.put_file(policy.token(), key, localfile, extra)
		assert err is None
		assert ret is not None

	def test_put_crc_fail(self):
		key = "test_%s" % r(9)
		data = "hello bubby!"
		extra.check_crc = 2
		extra.crc32 = "wrong crc32"
		ret, err = io.put(policy.token(), key, data, extra)
		assert err is not None


class Test_get_file_crc32(unittest.TestCase):
	def test_get_file_crc32(self):
		file_path = '%s' % __file__

		data = None
		with open(file_path) as f:
			data = f.read()
		io._BLOCK_SIZE = 4
		assert binascii.crc32(data) % 0xFFFFFFFF == io._get_file_crc32(file_path)


if __name__ == "__main__":
	unittest.main()
