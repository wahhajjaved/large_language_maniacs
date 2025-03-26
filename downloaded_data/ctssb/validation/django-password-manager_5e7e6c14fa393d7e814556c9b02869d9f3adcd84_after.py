#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
"""

# future
from __future__ import unicode_literals

import pytz
from urllib.parse import urlparse, urlunparse
from datetime import datetime, timedelta

# Django
import django

from django.http import QueryDict
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password
from pass_manager.models import PasswordHistory

from . import settings

try:
    from django.core.urlresolvers import resolve, reverse, NoReverseMatch
except ImportError:
    from django.urls import resolve, reverse, NoReverseMatch


def is_authenticated(user):
    if django.VERSION >= (1, 10):
        return user.is_authenticated
    else:
        return user.is_authenticated()


def expire_middleware_as_function(request):
    """
    In DRF we can't use Django middleware since in DRF Authentication is handled at View layer So we will always get
    Anonymous user if we will use request.user to get current authenticated user, So we can use this function
    to check user password validity.
    """
    if is_authenticated(request.user) and not request.user.is_staff:
        next_url = resolve(request.path).url_name
        # Authenticated users must be allowed to access
        # "change password" page and "log out" page.
        # even if password is expired.
        if next_url not in [settings.ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL,
                            settings.ACCOUNT_LOGOUT_URL,
                            ]:
            return check_password_expired(request.user)


def get_pass_reset_url():
    """
    :return password rest url.
    """
    change_password_url = reverse(settings.ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL)
    url_bits = list(urlparse(change_password_url))
    querystring = QueryDict(url_bits[4], mutable=True)
    url_bits[4] = querystring.urlencode(safe="/")

    return urlunparse(url_bits)


def check_password_expired(user):
    """check Password expiry

    :return True if expired else False
    """
    if not settings.STORE_PASSWORD_HISTORY:
        return False

    expiry = getattr(settings, 'PASSWORD_EXPIRY_TIME')

    try:
        # get latest password info
        latest = user.password_history.latest("pk")
    except PasswordHistory.DoesNotExist:
        return True

    now = datetime.now(tz=pytz.UTC)
    expiration = latest.timestamp + timedelta(days=expiry)

    if expiration < now:
        return True
    else:
        return False


def validate_and_create_password_history(password, user):
    """
        - Validate user new password must not be as same as he have already used in Past (the history be storing)

    :param password: plaintext password
    :param user: user object
    """
    if settings.STORE_PASSWORD_HISTORY:
        # validate password history

        for item in PasswordHistory.objects.filter(user=user):
            if check_password(password, item.password):
                raise ValidationError({'detail': 'cannot use any one of your last {0} passwords'.
                                      format(settings.PASSWORD_HISTORY_LIFE)})

        PasswordHistory.objects.create(
            user=user,
            password=make_password(password)
        )
