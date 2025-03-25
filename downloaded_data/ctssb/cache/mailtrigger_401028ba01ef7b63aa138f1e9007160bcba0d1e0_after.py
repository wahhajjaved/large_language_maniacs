#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time

from mailtrigger.argument import Argument
from mailtrigger.banner import BANNER
from mailtrigger.logger.logger import Logger
from mailtrigger.mailer.receiver import Receiver, ReceiverException
from mailtrigger.mailer.sender import Sender, SenderException
from mailtrigger.registry import REGISTRY
from mailtrigger.scheduler.scheduler import Scheduler, SchedulerException
from mailtrigger.trigger.trigger import TriggerException

MAILER = 'mailtrigger/config/mailer.json'
SCHEDULER = 'mailtrigger/config/scheduler.json'
TRIGGER = 'mailtrigger/config/trigger.json'


def run_job(args):
    def _run_trigger(data, sender, triggers):
        """TODO"""
        pass

    def _run_receiver(receiver):
        receiver.connect()
        data = receiver.retrieve()
        receiver.disconnect()
        return data

    receiver, sender, triggers = args

    data = _run_receiver(receiver)
    _run_trigger(data, sender, triggers)


def run_scheduler(sched, receiver, sender, triggers):
    sched.add(run_job, [receiver, sender, triggers], 'run_job')

    while True:
        sched.run()
        time.sleep(1)


def main():
    print(BANNER)

    argument = Argument()
    args = argument.parse()

    triggers = args.trigger.split(',')
    buf = list(set(triggers) - set([r['name'] for r in REGISTRY]))
    if len(buf) != 0:
        Logger.error('invalid trigger %s' % ','.join(buf))
        return -1

    try:
        sched = Scheduler(os.path.join(os.path.dirname(__file__), SCHEDULER))
    except SchedulerException as e:
        Logger.error(str(e))
        return -2

    try:
        receiver = Receiver(os.path.join(os.path.dirname(__file__), MAILER))
        sender = Sender(os.path.join(os.path.dirname(__file__), MAILER))
    except (ReceiverException, SenderException) as e:
        Logger.error(str(e))
        sched.stop()
        return -3

    ret = 0

    try:
        run_scheduler(sched, receiver, sender, triggers)
    except (SchedulerException, ReceiverException, SenderException, TriggerException) as e:
        Logger.error(str(e))
        ret = -4
    finally:
        sender.disconnect()
        receiver.disconnect()
        sched.stop()

    return ret


if __name__ == '__main__':
    sys.exit(main())
