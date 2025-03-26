# -*- coding: utf-8 -*-
"""
Copy to clipboard command.

:author: Joe Joyce <joe@decafjoe.com>
:copyright: Copyright (c) Joe Joyce and contributors, 2016-2017.
:license: BSD
"""
from __future__ import print_function

import datetime
import math
import sys
import time

from clik import args, parser

from safe.app import safe
from safe.clip import clipboard_drivers
from safe.ec import NO_SUCH_ACCOUNT, NO_SUCH_QUESTION, PASSWORD_NOT_SET, \
    VALIDATION_ERROR
from safe.model import Account, Password


DEFAULT_TIME = 5
JUNK = 'x'
UPDATE_INTERVAL = 0.1


class Countdown(object):
    """Countdown timer on stdout."""

    def __init__(self, format):
        """Format should have a single ``%s``, where time left is inserted."""
        self.format = format
        self._n = 0

    def _print(self, content):
        """Clear current line, replace it with ``content``."""
        out = '\r%s\r%s' % (' ' * self._n, content)
        self._n = len(content)
        sys.stdout.write(out)
        sys.stdout.flush()

    def update(self, time_left):
        """Update stdout with current ``time_left``."""
        self._print(self.format % time_left)

    def end(self):
        """Finish the countdown (by clearing the current line)."""
        self._print('')


@safe(alias='pb')
def copy():
    """Copy secret to clipboard temporarily."""
    parser.add_argument(
        'name',
        nargs=1,
        help='name of the account for which to copy secret',
    )
    parser.add_argument(
        '-q',
        '--question',
        help='copy answer to security question with given identifier to '
             'clipboard instead of the account password',
    )
    parser.add_argument(
        '-t',
        '--time',
        default=DEFAULT_TIME,
        help='amount of time to keep secret on clipboard (default: '
             '%(default)s)',
        type=float,
    )
    clipboard_drivers.configure_parser(parser)

    yield

    if args.time < 1:
        print('error: -t/--time must be one or greater', file=sys.stderr)
        yield VALIDATION_ERROR

    account = Account.for_slug(args.name[0])
    if account is None:
        print('error: no account named', args.name[0], file=sys.stderr)
        yield NO_SUCH_ACCOUNT

    if args.question:
        question = account.question_query\
                          .filter_by(identifier=args.question)\
                          .first()
        if question is None:
            fmt = 'error: no question with identifier "%s" associated with ' \
                  'account "%s"'
            print(fmt % (args.question, account.name), file=sys.stderr)
            yield NO_SUCH_QUESTION
        value = question.answer
    else:
        password = account.password_query\
                          .order_by(Password.changed.desc())\
                          .limit(1)\
                          .first()
        if password is None:
            msg = 'error: no password set for account "%s"' % account.name
            print(msg, file=sys.stderr)
            yield PASSWORD_NOT_SET
        value = password.value

    now = datetime.datetime.today()
    end = now + datetime.timedelta(seconds=args.time)
    countdown = Countdown('secret on clipboard for %ss...')
    clipboard = clipboard_drivers.driver_for_args(args)
    clipboard.put(value)
    while now < end:
        time.sleep(UPDATE_INTERVAL)
        now = datetime.datetime.today()
        countdown.update(math.ceil((end - now).seconds) + 1)
    countdown.end()
    clipboard.put(JUNK)
