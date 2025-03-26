import base64
import logging
import pickle

try:
    from django.utils.timezone import now as datetime_now
    datetime_now  # workaround for pyflakes
except ImportError:
    from datetime import datetime
    datetime_now = datetime.now

from django.core.mail import EmailMessage
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.text import mark_safe


PRIORITY_HIGH = 1
PRIORITY_MEDIUM = 2
PRIORITY_LOW = 3

PRIORITY_CHOICES = (
    (PRIORITY_HIGH, _('High')),
    (PRIORITY_MEDIUM, _('Medium')),
    (PRIORITY_LOW, _('Low')),
)

PRIORITY_MAPPING = {
    "high": PRIORITY_HIGH,
    "medium": PRIORITY_MEDIUM,
    "low": PRIORITY_LOW,
    }

STATUS_PENDING = 0
STATUS_SENT = 1
STATUS_DEFERRED = 2

STATUS_CHOICES = (
    (STATUS_PENDING, _("Pending")),
    (STATUS_SENT, _("Sent")),
    (STATUS_DEFERRED, _("Deferred")),
)


class MessageManager(models.Manager):
    
    def pending(self):
        """
        the messages in the queue for sending
        """
        return self.filter(status=STATUS_PENDING).order_by('priority')
    
    def deferred(self):
        """
        the deferred messages in the queue
        """
        return self.filter(status=STATUS_DEFERRED)
    
    def retry_deferred(self):
        count = 0
        for message in self.deferred():
            if message.retry():
                count += 1
        return count


def email_to_db(email):
    # pickle.dumps returns essentially binary data which we need to encode
    # to store in a unicode field.
    return base64.encodestring(pickle.dumps(email))


def db_to_email(data):
    if data == u"":
        return None
    else:
        try:
            return pickle.loads(base64.decodestring(data.encode("ascii")))
        except Exception:
            try:
                # previous method was to just do pickle.dumps(val)
                return pickle.loads(data.encode("ascii"))
            except Exception:
                return None


class Message(models.Model):
    
    # The actual data - a pickled EmailMessage
    message_data = models.TextField()
    priority = models.PositiveSmallIntegerField(null=False, blank=False, choices=PRIORITY_CHOICES,
                                                default=PRIORITY_MEDIUM, verbose_name=_('Priority'))
    status = models.PositiveIntegerField(null=False, blank=False, choices=STATUS_CHOICES, default=STATUS_PENDING,
                                         verbose_name=_('Status'))
    created = models.DateTimeField(blank=False, null=False, default=datetime_now, verbose_name=_('Created'))
    updated = models.DateTimeField(blank=False, null=False, auto_now=True, verbose_name=_('Updated'))
    # Recipients and subject are cached attrs (for list view)
    recipients = models.TextField(blank=True, null=True, verbose_name=_('Recipients'))
    subject = models.TextField(blank=True, null=True, verbose_name=_('Subject'))

    objects = MessageManager()
    
    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
    
    def defer(self):
        self.status = STATUS_DEFERRED
        self.save()
    
    def retry(self):
        if self.status == STATUS_DEFERRED:
            self.status = STATUS_PENDING
            self.save()
            return True
        else:
            return False

    def set_sent(self):
        self.status = STATUS_SENT
        self.save()
    
    def _get_email(self):
        return db_to_email(self.message_data)
    
    def _set_email(self, val):
        self.message_data = email_to_db(val)
    
    email = property(_get_email, _set_email)

    def set_recipients(self, recipients_list):
        self.recipients = ', '.join(recipients_list)
    
    @property
    def to_addresses(self):
        email = self.email
        if email is not None:
            return email.to
        else:
            return []

    def get_email_content_for_admin_field(self):
        contents = []

        if self.email.body and self.email.body.strip():
            contents.append('<textarea cols="150" rows="20">%s</textarea>' % self.email.body)

        for alternative in self.email.alternatives:
            if alternative[1] == 'text/html':
                contents.append('<textarea cols="150" rows="20">%s</textarea>' % alternative[0])
            else:
                contents.append('<code>Alternative in mime type: %s</code>' % alternative[1])

        return mark_safe('<hr />'.join(contents))

    get_email_content_for_admin_field.short_description = _('Email content')
