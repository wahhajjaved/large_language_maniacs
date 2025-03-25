# -*- coding: utf-8 -*-

import datetime

import unittest2
import webapp2
from google.appengine.ext import testbed

import main
from objects.pair import ScheduledPair


class PairsTest(unittest2.TestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()

    @staticmethod
    def make_request(url, method, body=''):
        request = webapp2.Request.blank(url)
        request.method = method
        request.body = body
        return request.get_response(main.application)

    @staticmethod
    def post_pair(pair, key=''):
        body = 'classname=' + pair.classname +\
            '&year=' + str(pair.date.year) +\
            '&month=' + str(pair.date.month) +\
            '&day=' + str(pair.date.day) +\
            '&hour=' + str(pair.start_time.hour) +\
            '&minute=' + str(pair.start_time.minute) + '&task=' + pair.task +\
            '&key=' + key
        return PairsTest.make_request('/pairs', 'POST', body)

    def check_pair_fields(self, pair1, pair2):
        self.assertEqual(pair1.classname,  pair2.classname)
        self.assertEqual(pair1.date,       pair2.date)
        self.assertEqual(pair1.start_time, pair2.start_time)
        self.assertEqual(pair1.task,       pair2.task)

    def test_create_pair(self):
        response = PairsTest.make_request('/new_pair', 'GET')
        self.assertEqual(response.status_int, 200)
        pair1 = ScheduledPair(classname='Math',
                              date=datetime.date(2015, 4, 14),
                              start_time=datetime.time(9, 40),
                              task='some_task')
        response = PairsTest.post_pair(pair1)
        self.assertEqual(response.status_int, 302)
        pairs_list = ScheduledPair.query().fetch(2)
        self.assertEqual(len(pairs_list), 1)
        added_pair = pairs_list[0]
        self.check_pair_fields(added_pair, pair1)
        response = PairsTest.make_request('/pairs', 'GET')
        self.assertEqual(response.status_int, 200)
        pair2 = ScheduledPair(classname='Math2',
                              date=datetime.date(2015, 4, 15),
                              start_time=datetime.time(9, 40),
                              task='some_task')
        response = PairsTest.post_pair(pair2)
        self.assertEqual(response.status_int, 302)
        pairs_list = ScheduledPair.query().fetch(3)
        self.assertEqual(len(pairs_list), 2)
        added_pair1 = pairs_list[0]
        added_pair2 = pairs_list[1]
        if added_pair1.classname != pair1.classname:
            swap(added_pair1, added_pair2)
        self.check_pair_fields(added_pair1, pair1)
        self.check_pair_fields(added_pair2, pair2)
        response = PairsTest.make_request('/pairs', 'GET')
        self.assertEqual(response.status_int, 200)

    def test_edit_pair(self):
        pair = ScheduledPair(classname='Math',
                             date=datetime.date(2015, 4, 14),
                             start_time=datetime.time(9, 40),
                             task='some_task')
        response = PairsTest.post_pair(pair)
        added_pair = ScheduledPair.query().fetch(2)[0]
        response = PairsTest.make_request('/edit_pair?key=' +
                                          added_pair.key.urlsafe(), 'GET')
        self.assertEqual(response.status_int, 200)
        pair = ScheduledPair(classname='Math1',
                             date=datetime.date(2016, 5, 15),
                             start_time=datetime.time(10, 41),
                             task='some_task1')
        response = PairsTest.post_pair(pair, added_pair.key.urlsafe())
        self.assertEqual(response.status_int, 302)
        pairs_list = ScheduledPair.query().fetch(2)
        self.assertEqual(len(pairs_list), 1)
        added_pair = pairs_list[0]
        self.check_pair_fields(added_pair, pair)
        response = PairsTest.make_request('/pairs', 'GET')
        self.assertEqual(response.status_int, 200)

    def test_delete_pair(self):
        pair1 = ScheduledPair(classname='Math1',
                              date=datetime.date(2015, 4, 14),
                              start_time=datetime.time(10, 40),
                              task='some_task')
        pair2 = ScheduledPair(classname='Math2',
                              date=datetime.date(2015, 4, 15),
                              start_time=datetime.time(9, 40),
                              task='some_task')
        PairsTest.post_pair(pair1)
        PairsTest.post_pair(pair2)
        pairs_list = ScheduledPair.query().fetch(2)
        added_pair1 = pairs_list[0]
        added_pair2 = pairs_list[1]
        response = PairsTest.make_request('/delete_pair?key=' +
                                          added_pair1.key.urlsafe() +
                                          '&return_url=/pairs', 'GET')
        self.assertEqual(response.status_int, 302)
        pairs_list = ScheduledPair.query().fetch(2)
        self.assertEqual(len(pairs_list), 1)
        remained_pair = pairs_list[0]
        self.assertEqual(remained_pair, added_pair2)

    def test_show_pairs(self):
        response = PairsTest.make_request('/pairs', 'GET')
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.body.count('<tr>'), 0)
        pair1 = ScheduledPair(classname='Math1',
                              date=datetime.date(2015, 4, 14),
                              start_time=datetime.time(10, 40),
                              task='some_task')
        pair2 = ScheduledPair(classname='Math2',
                              date=datetime.date(2015, 4, 15),
                              start_time=datetime.time(9, 40),
                              task='some_task')
        pair3 = ScheduledPair(classname='Math3',
                              date=datetime.date(2015, 4, 15),
                              start_time=datetime.time(10, 40),
                              task='some_task')
        PairsTest.post_pair(pair2)
        PairsTest.post_pair(pair3)
        PairsTest.post_pair(pair1)
        response = PairsTest.make_request('/pairs', 'GET')
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.body.count('<tr>'), 3)
        self.assertNotEqual(response.body.find('Math1'), -1)
        self.assertNotEqual(response.body.find('Math2'), -1)
        self.assertNotEqual(response.body.find('Math3'), -1)
        self.assertLess(response.body.find('Math1'), response.body.find('Math2'))
        self.assertLess(response.body.find('Math2'), response.body.find('Math3'))

    def test_show_schedule(self):
        response = PairsTest.make_request('/', 'GET')
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.body.count('<tr>'), 1)
        pair1 = ScheduledPair(classname='Math1',
                              date=datetime.date.today(),
                              start_time=datetime.time(9, 10),
                              task='some_task')
        pair2 = ScheduledPair(classname='Math2',
                              date=datetime.date.today(),
                              start_time=datetime.time(10, 40),
                              task='some_task')
        pair3 = ScheduledPair(classname='Math3',
                              date=datetime.date.today() +
                              datetime.timedelta(days=1),
                              start_time=datetime.time(9, 40),
                              task='some_task')
        PairsTest.post_pair(pair2)
        PairsTest.post_pair(pair3)
        PairsTest.post_pair(pair1)
        response = PairsTest.make_request('/', 'GET')
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.body.count('<tr>'), 4)
        self.assertNotEqual(response.body.find('Math1'), -1)
        self.assertNotEqual(response.body.find('Math2'), -1)
        self.assertNotEqual(response.body.find('Math3'), -1)
        self.assertLess(response.body.find('Math1'), response.body.find('Math2'))
        self.assertLess(response.body.find('Math2'), response.body.find('Math3'))

    def tearDown(self):
        self.testbed.deactivate()


if __name__ == '__main__':
    unittest2.main()
