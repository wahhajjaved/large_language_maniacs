# Copyright (C) 2014 Andrey Antukh <niwi@niwi.be>
# Copyright (C) 2014 Jesús Espino <jespinog@gmail.com>
# Copyright (C) 2014 David Barragán <bameda@dbarragan.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This module contains a domain logic for authentication
process. It called services because in DDD says it.

NOTE: Python doesn't have java limitations for "everytghing
should be contained in a class". Because of that, it
not uses clasess and uses simple functions.
"""

from django.db.models.loading import get_model
from django.db.models import Q
from django.db import transaction as tx
from django.db import IntegrityError
from django.utils.translation import ugettext as _

from djmail.template_mail import MagicMailBuilder

from taiga.base import exceptions as exc
from taiga.users.serializers import UserSerializer
from taiga.users.services import get_and_validate_user

from .backends import get_token_for_user


def send_public_register_email(user) -> bool:
    """
    Given a user, send public register welcome email
    message to specified user.
    """

    context = {"user": user}
    mbuilder = MagicMailBuilder()
    email = mbuilder.public_register_user(user.email, context)
    return bool(email.send())


def send_private_register_email(user, **kwargs) -> bool:
    """
    Given a user, send private register welcome
    email message to specified user.
    """
    context = {"user": user}
    context.update(kwargs)

    mbuilder = MagicMailBuilder()
    email = mbuilder.private_register_user(user.email, context)
    return bool(email.send())


def is_user_already_registred(*, username:str, email:str, github_id:int=None) -> bool:
    """
    Checks if a specified user is already registred.
    """

    user_model = get_model("users", "User")

    or_expr = Q(username=username) | Q(email=email)
    if github_id:
        or_expr = or_expr | Q(email=email)

    qs = user_model.objects.filter(or_expr)
    return qs.exists()


def get_membership_by_token(token:str):
    """
    Given a token, returns a membership instance
    that matches with specified token.

    If not matches with any membership NotFound exception
    is raised.
    """
    membership_model = get_model("projects", "Membership")
    qs = membership_model.objects.filter(user__isnull=True, token=token)
    if len(qs) == 0:
        raise exc.NotFound("Token not matches any valid invitation.")
    return qs[0]


@tx.atomic
def public_register(username:str, password:str, email:str, full_name:str):
    """
    Given a parsed parameters, try register a new user
    knowing that it follows a public register flow.

    This can raise `exc.IntegrityError` exceptions in
    case of conflics found.

    :returns: User
    """

    if is_user_already_registred(username=username, email=email):
        raise exc.IntegrityError("User is already registred.")

    user_model = get_model("users", "User")
    user = user_model(username=username,
                      email=email,
                      full_name=full_name)
    user.set_password(password)
    user.save()

    # send_public_register_email(user)
    return user


@tx.atomic
def private_register_for_existing_user(token:str, username:str, password:str):
    """
    Register works not only for register users, also serves for accept
    inviatations for projects as existing user.

    Given a invitation token with parsed parameters, accept inviation
    as existing user.
    """

    user = get_and_validate_user(username=username, password=password)
    membership = get_membership_by_token(token)

    membership.user = user
    membership.save(update_fields=["user"])

    # send_private_register_email(user)
    return user


@tx.atomic
def private_register_for_new_user(token:str, username:str, email:str,
                                  full_name:str, password:str):
    """
    Given a inviation token, try register new user matching
    the invitation token.
    """
    if is_user_already_registred(username=username, email=email):
        raise exc.WrongArguments(_("Username or Email is already in use."))

    user_model = get_model("users", "User")
    user = user_model(username=username,
                      email=email,
                      full_name=full_name)

    user.set_password(password)
    try:
        user.save()
    except IntegrityError:
        raise exc.IntegrityError(_("Error on creating new user."))

    membership = get_membership_by_token(token)
    membership.user = user
    membership.save(update_fields=["user"])

    return user


@tx.atomic
def github_register(username:str, email:str, full_name:str, github_id:int, bio:str, token:str=None):
    """
    Register a new user from github.

    This can raise `exc.IntegrityError` exceptions in
    case of conflics found.

    :returns: User
    """
    user_model = get_model("users", "User")
    user, created = user_model.objects.get_or_create(github_id=github_id,
                                                     defaults={"username": username,
                                                               "email": email,
                                                               "full_name": full_name,
                                                               "bio": bio})
    if token:
        membership = get_membership_by_token(token)
        membership.user = user
        membership.save(update_fields=["user"])

    return user


def make_auth_response_data(user) -> dict:
    """
    Given a domain and user, creates data structure
    using python dict containing a representation
    of the logged user.
    """
    serializer = UserSerializer(user)
    data = dict(serializer.data)
    data["auth_token"] = get_token_for_user(user)
    return data
