from __future__ import absolute_import

from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django import forms
from django.forms.util import flatatt
from django.utils.html import conditional_escape
from django.utils.encoding import force_unicode
from django.contrib.contenttypes.models import ContentType
from django.db.models.base import ModelBase
from django.template.defaultfilters import capfirst

from .literals import CONTENT_TYPE_ICON_MAP


def content_type_icon(content_type):
	return mark_safe(u'<span class="famfam active famfam-%s"></span>' % CONTENT_TYPE_ICON_MAP.get('%s.%s' % (content_type.app_label, content_type.name), 'help'))


def object_w_content_type_icon(obj):
    content_type = ContentType.objects.get_for_model(obj)

    ct_fullname = '%s.%s' % (content_type.app_label, content_type.name)
    if isinstance(obj, ModelBase):
        label = getattr(obj._meta, 'verbose_name_plural', unicode(content_type))
    else:
        if ct_fullname == 'auth.user':
            label = obj.get_full_name()
        else:
            label = unicode(obj)
        
    return mark_safe('%s<span>%s</span>' % (content_type_icon(content_type), capfirst(label)))
