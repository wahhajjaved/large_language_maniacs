#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright 2010 Asidev s.r.l.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import urllib
from aybu.manager.exc import ParamsError
from aybu.manager.models import (User,
                                 Alias,
                                 Group)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from pyramid.httpexceptions import (HTTPCreated,
                                    HTTPNoContent,
                                    HTTPForbidden,
                                    HTTPConflict,
                                    HTTPPreconditionFailed)
from pyramid.view import view_config
from pyramid.security import (effective_principals,
                              authenticated_userid)
from .exceptions import generate_empty_response
import logging
log = logging.getLogger(__name__)


@view_config(route_name='users', request_method=('HEAD', 'GET'))
def list(context, request):
    return {u.email: u.to_dict() for u in User.all(request.db_session)}


@view_config(route_name='users', request_method='POST')
def create(context, request):
    try:
        email = request.params['email']
        password = request.params['password']
        name = request.params['name']
        surname = request.params['surname']
        organization = request.params.get('organization')
        web = request.params.get('web')
        twitter = request.params.get('twitter')
        request_groups = request.params.getall('groups')
        groups = Group.search(request.db_session,
            filters=(Group.name.in_(request_groups), )
        )
        if len(groups) != len(request_groups):
            raise HTTPPreconditionFailed(
                headers={'X-Request-Error': 'Invalid groups "{}"'\
                                        .format(', '.join(request_groups))})

        u = User(email=email, password=password, name=name,
                 surname=surname, organization=organization,
                 web=web, twitter=twitter, groups=groups)
        request.db_session.add(u)
        request.db_session.flush()

    except KeyError as e:
        raise ParamsError(e)

    except IntegrityError as e:
        error = 'User with email {} already exists'\
                .format(request.params['email'])
        request.db_session.rollback()
        raise HTTPConflict(headers={'X-Request-Error': error})

    else:
        request.db_session.commit()
        raise HTTPCreated()


@view_config(route_name='user', request_method=('GET', 'HEAD'),
             permission='user')
def info(context, request):
    email = urllib.unquote(request.matchdict['email'])
    principals = effective_principals(request)

    # a "normal" user get info about itself.
    if not set(('admin', email)) & set(principals):
        return generate_empty_response(HTTPForbidden(), request, 403)

    return User.get(request.db_session, email).to_dict()


@view_config(route_name='user', request_method=('GET', 'HEAD'),
             request_param='action=login',
             permission='user')
def login(context, request):
    email = urllib.unquote(request.matchdict['email'])
    user = User.get(request.db_session, email)

    if authenticated_userid(request) != email and \
        'admin' not in effective_principals(request):
        return generate_empty_response(HTTPForbidden(), request, 403)

    try:
        domain = Alias.get(request.db_session,
                           request.params['domain'])\
                      .instance.domain

    except NoResultFound:
        domain = request.params['domain']

    except KeyError:
        log.error('No domain in request for users.login')
        return generate_empty_response(HTTPForbidden(), request, 403)

    groups = set([g.name for g in user.groups])
    if not set(('admin', domain)) & groups:
        log.error('%s cannot login on %s (%s)', email, domain, groups)
        return generate_empty_response(HTTPForbidden(), request, 403)
    return user.to_dict()


@view_config(route_name='user', request_method='DELETE')
def delete(context, request):
    try:
        email = urllib.unquote(request.matchdict['email'])
        user = User.get(request.db_session, email)
        user.delete()
        request.db_session.flush()

    except IntegrityError:
        request.db_session.rollback()
        raise HTTPPreconditionFailed(
            headers={'X-Request-Error': 'Cannot delete user {}. You must '\
                     'delete owner themes/instances first'.format(email)})
    else:
        request.db_session.commit()
        raise HTTPNoContent()


@view_config(route_name='user', request_method='PUT',
             permission='user')
def update(context, request):
    email = urllib.unquote(request.matchdict['email'])
    user = User.get(request.db_session, email)
    principals = effective_principals(request)

    # an "normal" user can update only itself
    if not set(('admin', email)) & set(principals):
        return generate_empty_response(HTTPForbidden(), request, 403)

    params = {}
    for attr in ('email', 'password', 'name', 'surname', 'organization',
                    'web', 'twitter'):
        value = request.params.get(attr)
        if value:
            params[attr] = value

    # only admins can change users groups
    if 'admin' in principals and 'groups' in request.params:
        groups = request.params.getall('groups')
        params['groups'] = User.search(
            request.db_session,
            filters=(Group.name.in_(groups), )
        )
        if len(groups) != len(params['groups']):
            raise HTTPPreconditionFailed(
                headers={'X-Request-Error': 'Invalid groups {}'\
                                            .format(','.join(groups))})

    if not params:
        raise ParamsError('Missing update fields')

    try:
        for param in params:
            setattr(user, param, params[param])

        request.db_session.flush()

    except IntegrityError:
        error = 'An user with email {} already exists'.format(params['email'])
        raise HTTPPreconditionFailed(headers={'X-Request-Error': error})

    else:
        request.db_session.commit()

    return user.to_dict()
