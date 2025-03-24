# -*- coding: utf-8 -*-
"""
Update policy command.

:author: Joe Joyce <joe@decafjoe.com>
:copyright: Copyright (c) Joe Joyce and contributors, 2016-2017.
:license: BSD
"""
from __future__ import print_function

import sys

from clik import args, g, parser

from safe.cmd.update import update
from safe.ec import NO_SUCH_POLICY, VALIDATION_ERROR
from safe.form.policy import UpdatePolicyForm
from safe.model import Policy


@update(alias='p')
def policy():
    """Update a policy and/or its associated data."""
    parser.add_argument(
        'policy',
        help='name of policy to update',
        nargs=1,
    )

    form = UpdatePolicyForm()
    form.configure_parser()

    yield

    policy = Policy.for_name(args.policy[0])
    if policy is None:
        print('error: no policy with name:', args.policy[0])
        yield NO_SUCH_POLICY

    if not form.bind_and_validate(policy):
        msg = 'error: there were validation error(s) with input value(s)'
        print(msg, file=sys.stderr)
        form.print_errors()
        yield VALIDATION_ERROR

    form.update_policy()
    g.commit_and_save()
