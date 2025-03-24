#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import logging

from snisi_core.models.Projects import Domain
from snisi_sms.common import test, echo, change_passwd, ask_for_help

logger = logging.getLogger(__name__)


def snisi_sms_handler(message):

    # migration to non-snisi prefixed SMS
    if message.startswith('snisi '):
        message.text = message.content[6:]
        message.save()

    logger.debug("Incoming SMS from {}: {}".format(
        message.identity, message.content))

    keywords = {'test': test,
                'echo': echo,
                'passwd': change_passwd,
                'help': ask_for_help}

    for domain in Domain.active.all():
        domain_kw = domain.import_from('sms_handlers.KEYWORDS')
        if domain_kw:
            keywords.update(domain_kw)

    for keyword, handler in keywords.items():
        if message.content.lower().startswith(keyword):
            return handler(message)
    # message.respond("Message non pris en charge.")
    return False
