#!/usr/bin/env python
'''
PEXPECT LICENSE

    This license is approved by the OSI and FSF as GPL-compatible.
        http://opensource.org/licenses/isc-license.txt

    Copyright (c) 2012, Noah Spurrier <noah@noah.org>
    PERMISSION TO USE, COPY, MODIFY, AND/OR DISTRIBUTE THIS SOFTWARE FOR ANY
    PURPOSE WITH OR WITHOUT FEE IS HEREBY GRANTED, PROVIDED THAT THE ABOVE
    COPYRIGHT NOTICE AND THIS PERMISSION NOTICE APPEAR IN ALL COPIES.
    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

'''
import pexpect
import unittest
import PexpectTestCase
import time
import sys

class TestCtrlChars(PexpectTestCase.PexpectTestCase):

    def test_control_chars (self):

        '''FIXME: Python unicode was too hard to figure out, so
        this tests only the true ASCII characters. This is lame
        and should be fixed. I'm leaving this script here as a
        placeholder so that it will remind me to fix this one day.
        This is what it used to do:
        This tests that we can send all 256 8-bit ASCII characters
        to a child process.'''

        # FIXME: Getting this to support Python's Unicode was
        # too hard, so I disabled this. I should fix this one day.
        return 0
        child = pexpect.spawn('python getch.py')
        try:
            for i in range(256):
#                child.send(unicode('%d'%i, encoding='utf-8'))
                child.send(chr(i))
                child.expect ('%d\r\n' % i)
        except Exception:
            err = sys.exc_info()[1]
            msg = "Did not echo character value: " + str(i) + "\n"
            msg = msg + str(err)
            self.fail(msg)

    def test_sendintr (self):
        try:
            child = pexpect.spawn('python getch.py')
            child.sendintr()
            child.expect ('3\r\n')
        except Exception:
            err = sys.exc_info()[1]
            self.fail(" ".join(["Did not echo character value: 3\n", str(err), child.before, child.after]))

    def test_bad_sendcontrol_chars (self):

        '''This tests that sendcontrol will return 0 for an unknown char. '''

        child = pexpect.spawn('python getch.py')
        retval = child.sendcontrol('1')
        assert retval == 0, "sendcontrol() should have returned 0 because there is no such thing as ctrl-1."

    def test_sendcontrol(self):

        '''This tests that we can send all special control codes by name.
        '''
        child = pexpect.spawn('python getch.py')
        child.delaybeforesend = 0.05
        for ctrl in 'abcdefghijklmnopqrstuvwxyz':
            assert child.sendcontrol(ctrl) == 1
            # Strange: on travis-ci, getch.py actually displays ^A, not '1' !?
            child.expect ('^(%d|%s)\r\n' % (
                ord(ctrl) - (ord('a') - 1),
                ctrl.upper(),), timeout=1)

        # escape character
        assert child.sendcontrol('[') == 1
        child.expect ('27\r\n')
        assert child.sendcontrol('\\') == 1
        child.expect ('28\r\n')
        # telnet escape character
        assert child.sendcontrol(']') == 1
        child.expect ('29\r\n')
        assert child.sendcontrol('^') == 1
        child.expect ('30\r\n')
        # irc protocol uses this to underline ...
        assert child.sendcontrol('_') == 1
        child.expect ('31\r\n')
        # the real "backspace is delete"
        assert child.sendcontrol('?') == 1
        child.expect ('127\r\n')
        # NUL, same as ctrl + ' '
        assert child.sendcontrol('@') == 1
        child.expect ('0\r\n')
        # 0 is sentinel value to getch.py, assert exit:
        #   causes child to exit, but, if immediately tested,
        #   isalive() still returns True unless an artifical timer
        #   is used.
        time.sleep(1)
        assert child.isalive() == False, child.isalive()
        assert child.exitstatus == 0

if __name__ == '__main__':
    unittest.main()

suite = unittest.makeSuite(TestCtrlChars,'test')

