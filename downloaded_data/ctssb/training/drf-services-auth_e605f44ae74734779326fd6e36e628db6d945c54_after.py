from __future__ import unicode_literals

import base64

from django.apps import apps as django_apps

from datetime import datetime, timedelta

import jwt
from django.core.exceptions import ImproperlyConfigured
from jwt.exceptions import InvalidTokenError
from rest_framework_services_auth.settings import auth_settings

'''
Dealing with no UUID serialization support in json
'''
from json import JSONEncoder
from uuid import UUID
JSONEncoder_olddefault = JSONEncoder.default


def JSONEncoder_newdefault(self, o):
    if isinstance(o, UUID):
        return str(o)
    return JSONEncoder_olddefault(self, o)


JSONEncoder.default = JSONEncoder_newdefault


DEFAULT_EXPIRATION_DELAY = 15 * 60  # 15 minutes


def encode_username(service_user_id):
    return base64.b64encode(
        str(service_user_id).replace('-', '').decode("hex"),
        altchars=str("+-")
    ).replace("=", "")


def jwt_encode_user(user, target, *args, **kwargs):
    return jwt_encode_uid(user.service_user.id, target, *args, **kwargs)


def jwt_encode_uid(uid, target, expiration_time=None, not_before=None,
                   *args, **kwargs):
    headers = {}
    if 'SECRET_KEY' not in target:
        raise ValueError("Must specify target's secret key")
    if 'ALGORITHM' not in target:
        raise ValueError("Must specify target's algorithm")
    if 'AUDIENCE' not in target:
        raise ValueError("Must specify target's audience")
    if 'ISSUER' not in target:
        raise ValueError("Must specify issuer name")
    if 'KEY_ID' in target:
        headers['kid'] = target['KEY_ID']

    expiration_time = (
        expiration_time or
        datetime.utcnow() +
            timedelta(seconds=target.get('EXPIRATION_DELAY',
                                         DEFAULT_EXPIRATION_DELAY))
    )

    not_before = not_before or datetime.utcnow()

    payload = {
        'uid': str(uid),
        'exp': expiration_time,
        'nbf': not_before,
        'iat': datetime.utcnow(),
        'iss': target["ISSUER"],
        'aud': target['AUDIENCE']
    }

    payload.update(kwargs.get('override', {}))

    return jwt.encode(
        payload,
        target['SECRET_KEY'],
        target['ALGORITHM'],
        headers=headers
    )


DEFAULT_LEEWAY = 5000

class Struct(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)


def load_verify_settings_from_dict(settings):
    return Struct(**settings)


def jwt_decode_token(token, verify_settings=auth_settings):
    options = {
        'verify_exp': True,
        'verify_iss': True,
        'verify_aud': True,
        'verify_nbf': True,
        'verify_iat': True
    }

    if not verify_settings.JWT_VERIFICATION_KEY:
        raise ValueError("Must specify verification key")

    payload = jwt.decode(
        token,
        verify_settings.JWT_VERIFICATION_KEY,
        options=options,
        leeway=getattr(verify_settings, 'JWT_LEEWAY', DEFAULT_LEEWAY),
        audience=verify_settings.JWT_AUDIENCE,
        issuer=verify_settings.JWT_ISSUER,
        algorithms=[verify_settings.JWT_ALGORITHM]
    )

    if (hasattr(verify_settings, 'JWT_MAX_VALID_INTERVAL')):

        exp = int(payload['exp'])
        nbf = int(payload['nbf'])

        if (exp - nbf > int(verify_settings.JWT_MAX_VALID_INTERVAL)):
            raise ValidIntervalError(exp,
                                     nbf,
                                     verify_settings.JWT_MAX_VALID_INTERVAL)
    return payload


class ValidIntervalError(InvalidTokenError):
    def __init__(self, exp, nbf, max_valid_interval, *args, **kwargs):
        self.exp = exp
        self.nbf = nbf
        self.max_valid_interval = max_valid_interval

    def __str__(self):
        return "Valid interval of token too long: " +  \
               "(Starts at %s and ending at %s) " % (
                   datetime.utcfromtimestamp(self.nbf),
                   datetime.utcfromtimestamp(self.exp),
               ) + "Max interval length is %s" % (
                   timedelta(seconds=self.max_valid_interval)
               )


def get_service_user_model():
    """
    Returns the User model that is active in this project.
    """
    try:
        return django_apps.get_model(auth_settings.SERVICE_USER_MODEL)
    except ValueError:
        raise ImproperlyConfigured("SERVICE_USER_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "SERVICE_USER_MODEL refers to model '%s' that has not been installed" % auth_settings.SERVICE_USER_MODEL
        )
