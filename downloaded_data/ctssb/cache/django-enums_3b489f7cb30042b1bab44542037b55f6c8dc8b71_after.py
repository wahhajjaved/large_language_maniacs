#!/usr/bin/env python
# vim: set fileencoding=utf-8 :

from __future__ import division, print_function, absolute_import
from django.db import models
from enum import Enum as BaseEnum
from itertools import ifilter
import django


class Enum(BaseEnum):

    def __init__(self, key, label):
        self.key = key
        self.label = label

    @classmethod
    def get_by_key(cls, key):
        return next(iter(filter(lambda x: x.key == key, list(cls))), None)

    @classmethod
    def tuples(cls):
        return map(lambda x: x.value, list(cls))

    @classmethod
    def choices(cls):
        return cls.tuples()

    @classmethod
    def get_max_length(cls):
        return len(max(list(cls), key=(lambda x: len(x.key))).key)


class EnumField(models.CharField):

    def __init__(self, enum, *args, **kwargs):
        self.enum = enum
        self.default_enum = kwargs.pop('default', None)
        kwargs['max_length'] = self.enum.get_max_length()
        kwargs['choices'] = self.enum.choices()
        if self.default_enum is not None:
            kwargs['default'] = self.default_enum.key
        super(EnumField, self).__init__(*args, **kwargs)

    def check(self, **kwargs):
        errors = super(EnumField, self).check(**kwargs)
        errors.extend(self._check_enum_attribute(**kwargs))
        errors.extend(self._check_default_attribute(**kwargs))
        return errors

    def _check_enum_attribute(self, **kwargs):
        if self.enum is None:
            return [
                    checks.Error(
                            "EnumFields must define a 'enum' attribute.",
                            obj=self,
                            id='django-enum.fields.E001',
                            ),
                    ]
        else:
            return []

    def _check_default_attribute(self, **kwargs):
        if self.default_enum is not None:
            if not isinstance(self.default_enum, self.enum):
                return [
                        checks.Error(
                                "'default' must be a member of %s." % (self.enum.__name__),
                                obj=self,
                                id='django-enum.fields.E002',
                                ),
                        ]
        else:
            return []

    def get_internal_type(self):
        return 'EnumField'

    def from_db_value(self, value, expression, connection, context):
        return self.enum.get_by_key(value)

    def to_python(self, value):
        value = super(EnumField, self).to_python(value)
        return self.enum.get_by_key(value)

    def get_prep_value(self, value):
        if value is None:
            return value
        return value.key

    def deconstruct(self):
        name, path, args, kwargs = super(EnumField, self).deconstruct()
        if django.VERSION >= (1, 9):
            kwargs['enum'] = self.enum
        else:
            path = "django.db.models.fields.CharField"
        return name, path, args, kwargs
