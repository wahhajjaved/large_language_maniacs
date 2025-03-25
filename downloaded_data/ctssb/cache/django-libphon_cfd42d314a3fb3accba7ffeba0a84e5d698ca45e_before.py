# -*- coding: utf-8 -*-
from channels.generic import BaseConsumer

from .sms.backends import get_backend


class SendSmsConsumer(BaseConsumer):

    method_mapping = {
        'libphon.send_sms': 'send_sms_consumer',
    }

    def _send_sms(self, phone, message, send_date=None):
        """Send the SMS and return the backend instance."""
        SMS = get_backend()
        sms = SMS(phone, message, send_date=send_date)
        sms.send()
        return sms

    def send_sms_consumer(self, message, **kwargs):
        phone = message.content['phone']
        text_msg = message.content['message']
        send_date = message.content.get('send_date')
        self._send_sms(phone, text_msg, send_date)
