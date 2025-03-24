import base64
try:
    import cPickle as pickle
except ImportError:
    import pickle
import datetime
import logging
import sys
import traceback
import warnings

from django.conf import settings as dj_settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction
from django.http import Http404
from django.utils.encoding import smart_unicode
from django.utils.translation import ugettext_lazy as _

from sentry import settings
from sentry.client.base import SentryClient
from sentry.helpers import cached_property, construct_checksum, get_db_engine, get_installed_apps, transform
from sentry.manager import GroupedMessageManager, SentryManager
from sentry.reporter import FakeRequest

_reqs = ('paging', 'indexer')
for r in _reqs:
    if r not in dj_settings.INSTALLED_APPS:
        raise ImproperlyConfigured("Put '%s' in your "
            "INSTALLED_APPS setting in order to use the sentry application." % r)

try:
    from idmapper.models import SharedMemoryModel as Model
except ImportError:
    Model = models.Model

logger = logging.getLogger('sentry')

__all__ = ('Message', 'GroupedMessage')

STATUS_LEVELS = (
    (0, _('unresolved')),
    (1, _('resolved')),
)

class GzippedDictField(models.TextField):
    """
    Slightly different from a JSONField in the sense that the default
    value is a dictionary.
    """
    __metaclass__ = models.SubfieldBase
 
    def to_python(self, value):
        if isinstance(value, basestring) and value:
            value = pickle.loads(base64.b64decode(value).decode('zlib'))
        elif not value:
            return {}
        return value

    def get_prep_value(self, value):
        if value is None: return
        return base64.b64encode(pickle.dumps(transform(value)).encode('zlib'))
 
    def value_to_string(self, obj):
        value = self._get_val_from_obj(obj)
        return self.get_db_prep_value(value)

    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        from south.modelsinspector import introspector
        field_class = "django.db.models.fields.TextField"
        args, kwargs = introspector(self)
        return (field_class, args, kwargs)

class MessageBase(Model):
    logger          = models.CharField(max_length=64, blank=True, default='root', db_index=True)
    class_name      = models.CharField(_('type'), max_length=128, blank=True, null=True, db_index=True)
    level           = models.PositiveIntegerField(choices=settings.LOG_LEVELS, default=logging.ERROR, blank=True, db_index=True)
    message         = models.TextField()
    traceback       = models.TextField(blank=True, null=True)
    view            = models.CharField(max_length=255, db_index=True, blank=True, null=True)
    checksum        = models.CharField(max_length=32, db_index=True)

    objects         = SentryManager()

    class Meta:
        abstract = True

    def shortened_traceback(self):
        return '\n'.join(self.traceback.split('\n')[-5:])
    shortened_traceback.short_description = _('traceback')
    shortened_traceback.admin_order_field = 'traceback'
    
    def error(self):
        if self.message:
            message = smart_unicode(self.message)
            if len(message) > 100:
                message = message[:97] + '...'
            if self.class_name:
                return "%s: %s" % (self.class_name, message)
        else:
            self.message = self._class_name or ''
        return message
    error.short_description = _('error')

    def description(self):
        return self.traceback or ''
    description.short_description = _('description')

class GroupedMessage(MessageBase):
    status          = models.PositiveIntegerField(default=0, choices=STATUS_LEVELS)
    times_seen      = models.PositiveIntegerField(default=1)
    last_seen       = models.DateTimeField(default=datetime.datetime.now, db_index=True)
    first_seen      = models.DateTimeField(default=datetime.datetime.now, db_index=True)

    objects         = GroupedMessageManager()

    class Meta:
        unique_together = (('logger', 'view', 'checksum'),)
        verbose_name_plural = _('grouped messages')
        verbose_name = _('grouped message')
        permissions = (
            ("can_view", "Can view"),
        )
        db_table = 'sentry_groupedmessage'

    def __unicode__(self):
        return "(%s) %s" % (self.times_seen, self.error())

    def natural_key(self):
        return (self.logger, self.view, self.checksum)

    @classmethod
    def get_score_clause(cls):
        engine = get_db_engine()
        if engine.startswith('postgresql'):
            return 'times_seen / (pow((floor(extract(epoch from now() - last_seen) / 3600) + 2), 1.25) + 1)'
        if engine.startswith('mysql'):
            return 'times_seen / (pow((floor((unix_timestamp(now()) - unix_timestamp(last_seen)) / 3600) + 2), 1.25) + 1)'
        return 'times_seen'

    def mail_admins(self, request=None, fail_silently=True):
        if not settings.ADMINS:
            return
        
        from django.core.mail import send_mail
        from django.template.loader import render_to_string

        message = self.message_set.order_by('-id')[0]

        obj_request = message.request

        subject = 'Error (%s IP): %s' % ((obj_request.META.get('REMOTE_ADDR') in dj_settings.INTERNAL_IPS and 'internal' or 'EXTERNAL'), obj_request.path)
        try:
            request_repr = repr(obj_request)
        except:
            request_repr = "Request repr() unavailable"

        if request:
            link = request.build_absolute_url(self.get_absolute_url())
        else:
            link = None

        body = render_to_string('sentry/emails/error.txt', {
            'request_repr': request_repr,
            'request': obj_request,
            'group': self,
            'traceback': message.traceback,
            'link': link,
        })
        
        send_mail(dj_settings.EMAIL_SUBJECT_PREFIX + subject, body,
                  dj_settings.SERVER_EMAIL, settings.ADMINS,
                  fail_silently=fail_silently)

class Message(MessageBase):
    group           = models.ForeignKey(GroupedMessage, blank=True, null=True, related_name="message_set")
    datetime        = models.DateTimeField(default=datetime.datetime.now, db_index=True)
    data            = GzippedDictField(blank=True, null=True)
    url             = models.URLField(verify_exists=False, null=True, blank=True)
    server_name     = models.CharField(max_length=128, db_index=True)

    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        db_table = 'sentry_message'

    def __unicode__(self):
        return self.error()

    def save(self, *args, **kwargs):
        if not self.checksum:
            self.checksum = construct_checksum(**self.__dict__)
        super(Message, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return self.url
    
    def shortened_url(self):
        if not self.url:
            return _('no data')
        url = self.url
        if len(url) > 60:
            url = url[:60] + '...'
        return url
    shortened_url.short_description = _('url')
    shortened_url.admin_order_field = 'url'
    
    def full_url(self):
        return self.data.get('url') or self.url
    full_url.short_description = _('url')
    full_url.admin_order_field = 'url'

    @cached_property
    def request(self):
        fake_request = FakeRequest()
        fake_request.META = self.data.get('META', {})
        fake_request.GET = self.data.get('GET', {})
        fake_request.POST = self.data.get('POST', {})
        fake_request.FILES = self.data.get('FILES', {})
        fake_request.COOKIES = self.data.get('COOKIES', {})
        fake_request.url = self.url
        if self.url:
            fake_request.path_info = '/' + self.url.split('/', 3)[-1]
        else:
            fake_request.path_info = ''
        fake_request.path = fake_request.path_info
        return fake_request
