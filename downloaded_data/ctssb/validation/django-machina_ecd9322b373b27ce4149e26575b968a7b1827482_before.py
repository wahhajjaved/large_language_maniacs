# -*- coding: utf-8 -*-

# Standard library imports
from __future__ import unicode_literals

# Third party imports
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

# Local application / specific library imports
from machina.conf import settings as machina_settings


@python_2_unicode_compatible
class AbstractAttachment(models.Model):
    """
    Represents a post attachment. An attachment is always linked to a post.
    """
    post = models.ForeignKey('conversation.Post', verbose_name=_('Post'), related_name='attachments')
    file = models.FileField(verbose_name=_('File'), upload_to=machina_settings.ATTACHMENT_FILE_UPLOAD_TO)
    comment = models.CharField(max_length=255, verbose_name=_('Comment'), blank=True, null=True)

    class Meta:
        abstract = True
        verbose_name = _('Attachment')
        verbose_name_plural = _('Attachments')

    def __str__(self):
        return '{}'.format(self.topic.subject)
