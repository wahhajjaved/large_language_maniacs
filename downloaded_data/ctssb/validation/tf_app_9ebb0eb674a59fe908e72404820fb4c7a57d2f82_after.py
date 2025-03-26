# -*- coding: utf-8 -*-
# Copyright 2017 GIG Technology NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @@license_version:1.3@@
import json
import logging

from google.appengine.ext import deferred

from framework.bizz.session import create_session
from framework.plugin_loader import get_config
from mcfw.consts import MISSING
from mcfw.rpc import returns, arguments, serialize_complex_value
from plugins.its_you_online_auth.bizz.authentication import create_jwt, get_itsyouonline_client_from_jwt
from plugins.its_you_online_auth.plugin_consts import NAMESPACE as IYO_AUTH_NAMESPACE
from plugins.rogerthat_api.api import system
from plugins.rogerthat_api.to import UserDetailsTO
from plugins.tff_backend.bizz import get_rogerthat_api_key
from plugins.tff_backend.bizz.iyo.keystore import create_keystore_key, get_keystore
from plugins.tff_backend.bizz.iyo.user import get_user
from plugins.tff_backend.bizz.iyo.utils import get_iyo_organization_id, get_iyo_username
from plugins.tff_backend.plugin_consts import KEY_NAME, KEY_ALGORITHM
from plugins.tff_backend.to.iyo.keystore import IYOKeyStoreKey, IYOKeyStoreKeyData


@returns()
@arguments(user_detail=UserDetailsTO, data=unicode)
def user_registered(user_detail, data):
    logging.info('User %s:%s registered', user_detail.email, user_detail.app_id)
    data = json.loads(data)
    access_token = data.get('result', {}).get('access_token')
    username = data.get('result', {}).get('info', {}).get('username')
    if not access_token or not username:
        logging.warn('No access_token/username in %s', data)
        return

    iyo_config = get_config(IYO_AUTH_NAMESPACE)

    organization_id = get_iyo_organization_id()
    logging.debug('Creating JWT')
    jwt = create_jwt(access_token, scope=iyo_config.required_scopes)
    # Creation session such that the JWT is automatically up to date
    create_session(username, iyo_config.required_scopes.split(','), jwt)

    logging.info('Inviting user %s to IYO organization %s', username, organization_id)
    client = get_itsyouonline_client_from_jwt(jwt)
    notification = None
    client.api.organizations.AddOrganizationMember(notification, organization_id)

    deferred.defer(_store_name, username, jwt, user_detail)


@returns()
@arguments(username=unicode, jwt=unicode, user_detail=UserDetailsTO)
def _store_name(username, jwt, user_detail):
    logging.info('Getting the user\'s name from IYO')
    iyo_user = get_user(username)
    if not iyo_user.firstname and not iyo_user.lastname:
        logging.debug('There is no firstname and lastname in %s', iyo_user)
        return

    logging.info('Storing name in user_data')  # used for pre-filling message flows
    api_key = get_rogerthat_api_key()
    user_data = system.get_user_data(api_key, user_detail.email, user_detail.app_id, ['name'])
    if user_data.get('name'):
        logging.debug('The name was already stored in user_data')
    else:
        user_data = dict(name='%s %s' % (iyo_user.firstname, iyo_user.lastname))
        system.put_user_data(api_key, user_detail.email, user_detail.app_id, user_data)


@returns()
@arguments(user_detail=UserDetailsTO)
def store_public_key(user_detail):
    logging.info('Storing %s key in IYO for user %s:%s', KEY_NAME, user_detail.email, user_detail.app_id)

    for rt_key in user_detail.public_keys:
        if rt_key.algorithm == KEY_ALGORITHM and rt_key.name == KEY_NAME:
            break
    else:
        logging.warn('No key found with name "%s" and algorithm "%s" in %s', KEY_NAME, KEY_ALGORITHM,
                     serialize_complex_value(user_detail, UserDetailsTO, False, skip_missing=True))
        return

    organization_id = get_iyo_organization_id()
    username = get_iyo_username(user_detail)
    key = IYOKeyStoreKey()
    key.key = rt_key.public_key
    key.globalid = organization_id
    key.username = username
    key.label = KEY_NAME
    key.keydata = IYOKeyStoreKeyData()
    key.keydata.timestamp = MISSING
    key.keydata.comment = u'ThreeFold app'
    key.keydata.algorithm = rt_key.algorithm
    result = create_keystore_key(username, key)
    if result is None:
        # Already exists, retry with a different name
        # Ensure we change the label so it doesn't conflict with previously generated keys
        keystore = sorted(get_keystore(username), key=lambda x: x.label)
        suffix = 2
        for k in keystore:
            if k.label.endswith(str(suffix)):
                suffix += 1
        key.label = u'%s %d' % (KEY_NAME, suffix)
        create_keystore_key(username, key)
