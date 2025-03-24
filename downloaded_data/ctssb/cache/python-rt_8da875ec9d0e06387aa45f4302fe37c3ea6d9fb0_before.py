"""Tests for Rt - Python interface to Request Tracker :term:`API`"""

__license__ = """ Copyright (C) 2013 CZ.NIC, z.s.p.o.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
__docformat__ = "reStructuredText en"
__authors__ = [
  '"Jiri Machalek" <jiri.machalek@nic.cz>'
]

import unittest
import random
import string

from six import iteritems
from six.moves import range

import rt

class RtTestCase(unittest.TestCase):

    RT_VALID_CREDENTIALS = {
        'RT3.8 stable (admin)': {
            'url': 'http://rt.easter-eggs.org/demos/oldstable/REST/1.0',
            'default_login': 'admin',
            'default_password': 'admin',
        },
        'RT3.8 stable (john.foo)': {
            'url': 'http://rt.easter-eggs.org/demos/oldstable/REST/1.0',
            'default_login': 'john.foo',
            'default_password': 'john.foo',
        },
        'RT4 stable (admin)': {
            'url': 'http://rt.easter-eggs.org/demos/stable/REST/1.0',
            'default_login': 'admin',
            'default_password': 'admin',
        },
        'RT4 stable (john.foo)': {
            'url': 'http://rt.easter-eggs.org/demos/stable/REST/1.0',
            'default_login': 'john.foo',
            'default_password': 'john.foo',
        },
    }

    RT_INVALID_CREDENTIALS = {
        'RT3.8 stable (bad credentials)': {
            'url': 'http://rt.easter-eggs.org/demos/oldstable/REST/1.0',
            'default_login': 'idontexist',
            'default_password': 'idonthavepassword',
        },
    }

    RT_MISSING_CREDENTIALS = {
        'RT4 stable (missing credentials)': {
            'url': 'http://rt.easter-eggs.org/demos/stable/REST/1.0',
        },
    }

    RT_BAD_URL = {
        'RT (bad url)': {
            'url': 'http://httpbin.org/status/404',
            'default_login': 'idontexist',
            'default_password': 'idonthavepassword',
        },
    }

    def test_login_and_logout(self):
        for name, params in iteritems(self.RT_VALID_CREDENTIALS):
            tracker = rt.Rt(**params)
            self.assertTrue(tracker.login(), 'Invalid login to RT demo site ' + name)
            self.assertTrue(tracker.logout(), 'Invalid logout from RT demo site ' + name)
        for name, params in iteritems(self.RT_INVALID_CREDENTIALS):
            tracker = rt.Rt(**params)
            self.assertFalse(tracker.login(), 'Login to RT demo site ' + name + ' should fail but did not')
            self.assertRaises(rt.AuthorizationError, lambda: tracker.search())
        for name, params in iteritems(self.RT_MISSING_CREDENTIALS):
            tracker = rt.Rt(**params)
            self.assertRaises(rt.AuthorizationError, lambda: tracker.login())
        for name, params in iteritems(self.RT_BAD_URL):
            tracker = rt.Rt(**params)
            self.assertRaises(rt.UnexpectedResponse, lambda: tracker.login())

    def test_ticket_operations(self):
        ticket_subject = 'Testing issue ' + "".join([random.choice(string.ascii_letters) for i in range(15)])
        ticket_text = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        for name in ('RT4 stable (john.foo)', 'RT3.8 stable (john.foo)'):
            params = self.RT_VALID_CREDENTIALS[name]
            tracker = rt.Rt(**params)
            self.assertTrue(tracker.login(), 'Invalid login to RT demo site ' + name)
            # create
            ticket_id = tracker.create_ticket(Subject=ticket_subject, Text=ticket_text)
            self.assertTrue(ticket_id > -1, 'Creating ticket failed.')
            # search
            search_result = tracker.search(Subject=ticket_subject)
            self.assertEqual(len(search_result), 1, 'Created ticket is not found by the subject.')
            self.assertEqual(search_result[0]['id'], 'ticket/' + str(ticket_id), 'Bad id in search result of just created ticket.')
            self.assertEqual(search_result[0]['Status'], 'new', 'Bad status in search result of just created ticket.')
            # raw search
            search_result = tracker.search(raw_query='Subject="%s"' % ticket_subject)
            self.assertEqual(len(search_result), 1, 'Created ticket is not found by the subject.')
            self.assertEqual(search_result[0]['id'], 'ticket/' + str(ticket_id), 'Bad id in search result of just created ticket.')
            self.assertEqual(search_result[0]['Status'], 'new', 'Bad status in search result of just created ticket.')
            # get ticket
            ticket = tracker.get_ticket(ticket_id)
            self.assertEqual(ticket, search_result[0], 'Ticket get directly by its id is not equal to previous search result.')
            # edit ticket
            requestors = ['tester1@example.com', 'tester2@example.com']
            tracker.edit_ticket(ticket_id, Status='open', Requestors=requestors)
            # get ticket (edited)
            ticket = tracker.get_ticket(ticket_id)
            self.assertEqual(ticket['Status'], 'open', 'Ticket status was not changed to open.')
            self.assertEqual(ticket['Requestors'], requestors, 'Ticket requestors were not added properly.')
            # get history
            hist = tracker.get_history(ticket_id)
            self.assertTrue(len(hist) > 0, 'Empty ticket history.')
            self.assertEqual(hist[0]['Content'], ticket_text, 'Ticket text was not receives is it was submited.')
            # get_short_history
            short_hist = tracker.get_short_history(ticket_id)
            self.assertTrue(len(short_hist) > 0, 'Empty ticket short history.')
            self.assertEqual(short_hist[0][1], 'Ticket created by john.foo')
            # create 2nd ticket
            ticket2_subject = 'Testing issue ' + "".join([random.choice(string.ascii_letters) for i in range(15)])
            ticket2_id = tracker.create_ticket(Subject=ticket2_subject)
            self.assertTrue(ticket2_id > -1, 'Creating 2nd ticket failed.')
            # edit link
            self.assertTrue(tracker.edit_link(ticket_id, 'DependsOn', ticket2_id))
            # get links
            links1 = tracker.get_links(ticket_id)
            self.assertTrue('DependsOn' in links1, 'Missing just created link DependsOn.')
            self.assertTrue(links1['DependsOn'][0].endswith('ticket/' + str(ticket2_id)), 'Unexpected value of link DependsOn.')
            links2 = tracker.get_links(ticket2_id)
            self.assertTrue('DependedOnBy' in links2, 'Missing just created link DependedOnBy.')
            self.assertTrue(links2['DependedOnBy'][0].endswith('ticket/' + str(ticket_id)), 'Unexpected value of link DependedOnBy.')
            # reply with attachment
            attachment_content = b'Content of attachment.'
            attachment_name = 'attachment.txt'
            reply_text = 'Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.'
            self.assertTrue(tracker.reply(ticket_id, text=reply_text, files=[(attachment_name, attachment_content)]), 'Reply to ticket returned False indicating error.')
            at_ids = tracker.get_attachments_ids(ticket_id)
            self.assertTrue(at_ids, 'Emply list with attachment ids, something went wrong.')
            at_content = tracker.get_attachment_content(ticket_id, at_ids[-1])
            self.assertEqual(at_content, attachment_content, 'Recorded attachment is not equal to the original file.')
            # attachments list
            at_list = tracker.get_attachments(ticket_id)
            at_names = [at[1] for at in at_list]
            self.assertTrue(attachment_name in at_names, 'Attachment name is not in the list of attachments.')
            # merge tickets
            self.assertTrue(tracker.merge_ticket(ticket2_id, ticket_id), 'Merging tickets failed.')
            # delete ticket
            self.assertTrue(tracker.edit_ticket(ticket_id, Status='deleted'), 'Ticket delete failed.')
            # get user
            self.assertEqual(self.get_user(params['default_login'])['EmailAddress'], params['default_login'] + '@no.mail', 'Bad user email received.')

if __name__ == '__main__':
    unittest.main()

