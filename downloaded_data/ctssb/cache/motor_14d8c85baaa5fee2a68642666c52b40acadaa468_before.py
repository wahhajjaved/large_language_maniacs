# Copyright 2013 10gen, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test Motor's async test helpers."""

import datetime
import unittest

from tornado import gen
from tornado.ioloop import IOLoop

import motor
from test import async_test_engine, AssertRaises, MotorTest


class MotorTestTest(unittest.TestCase):
    @async_test_engine()
    def test_generator(self, done):
        loop = IOLoop.instance()
        yield gen.Task(loop.add_callback)
        done()

    @async_test_engine()
    def test_non_generator(self, done):
        done()

    @async_test_engine(timeout_sec=1)
    def pause(self, done):
        loop = IOLoop.instance()
        yield gen.Task(loop.add_timeout, self.pause_delta)
        done()

    def test_timeout(self):
        self.pause_delta = datetime.timedelta(seconds=10)
        self.assertRaises(Exception, self.pause)

    def test_no_timeout(self):
        self.pause_delta = datetime.timedelta(seconds=0)
        self.pause()  # No error.

    @async_test_engine(timeout_sec=0.1)
    def doesnt_call_done(self, done):
        pass

    def test_doesnt_call_done(self):
        self.assertRaises(Exception, self.doesnt_call_done)

    @async_test_engine()
    def yield_assert_raises(self, done):
        def _raise(callback):
            callback(None, self.exception)

        yield AssertRaises(ZeroDivisionError, _raise)
        done()

    def test_assert_raises(self):
        self.exception = ZeroDivisionError()
        self.yield_assert_raises()  # No error.

    def test_assert_raises_failure(self):
        self.exception = None
        self.assertRaises(Exception, self.yield_assert_raises)


def require_callback(callback=None):
    motor.check_callable(callback, True)
    callback(None, None)


def dont_require_callback(callback=None):
    motor.check_callable(callback, False)
    if callback is not None:
        callback(None, None)


class MotorCallbackTestTest(MotorTest):
    @async_test_engine()
    def test_check_required_callback(self, done):
        yield motor.Op(self.check_required_callback, require_callback)
        yield AssertRaises(
            Exception,
            self.check_required_callback, dont_require_callback)

        done()

    @async_test_engine()
    def test_check_optional_callback(self, done):
        yield motor.Op(self.check_optional_callback, dont_require_callback)
        yield AssertRaises(
            Exception, self.check_optional_callback, require_callback)

        done()
