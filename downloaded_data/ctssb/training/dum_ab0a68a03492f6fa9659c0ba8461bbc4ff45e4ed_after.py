# -*- coding: utf-8 -*-

import os
import re

import six
from django.apps import apps
from django.conf import settings
from django.core.validators import EMPTY_VALUES
from django.db import models


def _get_file_fields():
    """
        Get all fields which are inherited from FileField
    """

    # get models. Compatibility with 1.6

    if getattr(apps, 'get_models'):
        all_models = apps.get_models()
    else:
        all_models = models.get_models()

    # get fields

    fields = []

    for model in all_models:
        for field in model._meta.get_fields():
            if isinstance(field, models.FileField):
                fields.append(field)

    return fields


def get_used_media():
    """
        Get media which are still used in models
    """

    media = []

    for field in _get_file_fields():
        is_null = {
            '%s__isnull' % field.name: True,
        }
        is_empty = {
            '%s' % field.name: '',
        }

        storage = field.storage

        for value in field.model.objects \
                .values_list(field.name, flat=True) \
                .exclude(**is_empty).exclude(**is_null):
            if value not in EMPTY_VALUES:
                media.append(storage.path(value))

    return media


def _get_all_media(exclude=None):
    """
        Get all media from MEDIA_ROOT
    """

    if not exclude:
        exclude = []

    media = []

    for root, dirs, files in os.walk(six.text_type(settings.MEDIA_ROOT)):
        for name in files:
            path = os.path.join(root, name)
            relpath = os.path.relpath(path, settings.MEDIA_ROOT)
            in_exclude = False
            for e in exclude:
                if re.match(r'^%s$' % re.escape(e).replace('\\*', '.*'), relpath):
                    in_exclude = True
                    break

            if not in_exclude:
                media.append(path)

    return media


def get_unused_media(exclude=None):
    """
        Get media which are not used in models
    """

    if not exclude:
        exclude = []

    all_media = _get_all_media(exclude)
    used_media = get_used_media()

    return [x for x in all_media if x not in used_media]


def _remove_media(files):
    """
        Delete file from media dir
    """
    for filename in files:
        os.remove(os.path.join(settings.MEDIA_ROOT, filename))


def remove_unused_media():
    """
        Remove unused media
    """
    _remove_media(get_unused_media())


def remove_empty_dirs(path=None):
    """
        Recursively delete empty directories; return True if everything was deleted.
    """

    if not path:
        path = settings.MEDIA_ROOT

    if not os.path.isdir(path):
        return False

    listdir = [os.path.join(path, filename) for filename in os.listdir(path)]

    if all(list(map(remove_empty_dirs, listdir))):
        os.rmdir(path)
        return True
    else:
        return False
