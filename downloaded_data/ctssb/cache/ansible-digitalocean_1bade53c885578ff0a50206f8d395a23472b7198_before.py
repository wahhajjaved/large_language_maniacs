#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2015, Patrick F. Marques <patrickfmarques@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
DOCUMENTATION = '''
---
module: do_sshkeys
short_description: Manage DigitalOcean SSH keys
description:
     - Create/delete DigitalOcean SSH keys.
version_added: "2.3"
author: "Patrick Marques (@pmarques)"
options:
  state:
    description:
     - Indicate desired state of the target.
    default: present
    choices: ['present', 'absent']
  fingerprint:
    description:
     - This is a unique identified for the SSH key used to delete a key
    required: false
    default: None
  name:
    description:
     - The name for the SSH key
    required: false
    default: None
  ssh_pub_key:
    description:
     - The Public SSH key to add.
    required: false
    default: None
  oauth_token:
    description:
     - DigitalOcean OAuth token.
    required: true

notes:
  - Version 2 of DigitalOcean API is used.
requirements:
  - "python >= 2.6"
'''


EXAMPLES = '''
- name: "Create ssh key"
  do_sshkeys:
    name: "My SSH Public Key"
    public_key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAQQDDHr/jh2Jy4yALcK4JyWbVkPRaWmhck3IgCoeOO3z1e2dBowLh64QAM+Qb72pxekALga2oi4GvT+TlWNhzPH4V example"
  register: result

- name: "Delete ssh key"
  do_sshkeys:
    state: "absent"
    fingerprint: "3b:16:bf:e4:8b:00:8b:b8:59:8c:a9:d3:f0:19:45:fa"
'''


RETURN = '''
# Digital Ocean API info https://developers.digitalocean.com/documentation/v2/#list-all-keys
data:
    description: This is only present when C(state=present)
    returned: when C(state=present)
    type: dict
    sample: {
        "ssh_key": {
            "id": 512189,
            "fingerprint": "3b:16:bf:e4:8b:00:8b:b8:59:8c:a9:d3:f0:19:45:fa",
            "name": "My SSH Public Key",
            "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAQQDDHr/jh2Jy4yALcK4JyWbVkPRaWmhck3IgCoeOO3z1e2dBowLh64QAM+Qb72pxekALga2oi4GvT+TlWNhzPH4V example"
        }
    }
'''

import json
import os
import hashlib
import base64

from ansible.module_utils.basic import env_fallback
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url


class Response(object):

    def __init__(self, resp, info):
        self.body = None
        if resp:
            self.body = resp.read()
        self.info = info

    @property
    def json(self):
        if not self.body:
            if "body" in self.info:
                return json.loads(self.info["body"])
            return None
        try:
            return json.loads(self.body)
        except ValueError:
            return None

    @property
    def status_code(self):
        return self.info["status"]


class Rest(object):

    def __init__(self, module, headers):
        self.module = module
        self.headers = headers
        self.baseurl = 'https://api.digitalocean.com/v2'

    def _url_builder(self, path):
        if path[0] == '/':
            path = path[1:]
        return '%s/%s' % (self.baseurl, path)

    def send(self, method, path, data=None, headers=None):
        url = self._url_builder(path)
        data = self.module.jsonify(data)

        resp, info = fetch_url(self.module, url, data=data, headers=self.headers, method=method)

        return Response(resp, info)

    def get(self, path, data=None, headers=None):
        return self.send('GET', path, data, headers)

    def put(self, path, data=None, headers=None):
        return self.send('PUT', path, data, headers)

    def post(self, path, data=None, headers=None):
        return self.send('POST', path, data, headers)

    def delete(self, path, data=None, headers=None):
        return self.send('DELETE', path, data, headers)


def core(module):
    api_token = module.params['oauth_token']
    state = module.params['state']
    fingerprint = module.params['fingerprint']
    name = module.params['name']
    ssh_pub_key = module.params['ssh_pub_key']

    rest = Rest(module, {'Authorization': 'Bearer {}'.format(api_token),
                         'Content-type': 'application/json'})

    fingerprint = fingerprint or ssh_key_fingerprint(ssh_pub_key)
    response = rest.get('account/keys/{}'.format(fingerprint))
    status_code = response.status_code
    json = response.json

    if status_code not in (200, 404):
        module.fail_json(msg='Error getting ssh key [{}: {}]'.format(
            status_code, response.json['message']), fingerprint=fingerprint)

    if state in ('present'):
        if status_code == 404:
            # IF key not found create it!

            if module.check_mode:
                module.exit_json(changed=True)

            payload = {
                'name': name,
                'public_key': ssh_pub_key
            }
            response = rest.post('account/keys', data=payload)
            status_code = response.status_code
            json = response.json
            if status_code == 201:
                module.exit_json(changed=True, data=json)

            module.fail_json(msg='Error creating ssh key [{}: {}]'.format(
                status_code, response.json['message']))

        elif status_code == 200:
            # If key found was found, check if name needs to be updated
            if json['ssh_key']['name'] == name:
                module.exit_json(changed=False, data=json)

            if module.check_mode:
                module.exit_json(changed=True)

            payload = {
                'name': name,
            }
            response = rest.put('account/keys/{}'.format(fingerprint), data=payload)
            status_code = response.status_code
            json = response.json
            if status_code == 200:
                module.exit_json(changed=True, data=json)

            module.fail_json(msg='Error updating ssh key name [{}: {}]'.format(
                status_code, response.json['message']), fingerprint=fingerprint)

    elif state in ('absent'):
        if status_code == 404:
            module.exit_json(changed=False)

        if module.check_mode:
            module.exit_json(changed=True)

        response = rest.delete('account/keys/{}'.format(fingerprint))
        status_code = response.status_code
        json = response.json
        if status_code == 204:
            module.exit_json(changed=True)

        module.fail_json(msg='Error creating ssh key [{}: {}]'.format(
            status_code, response.json['message']))

def ssh_key_fingerprint(ssh_pub_key):
    key = ssh_pub_key.split(None, 2)[1]
    fingerprint = hashlib.md5(base64.decodestring(key)).hexdigest()
    return ':'.join(a+b for a,b in zip(fingerprint[::2], fingerprint[1::2]))


def main():
    module = AnsibleModule(
        argument_spec = dict(
            state = dict(choices=['present', 'absent'], default='present'),
            fingerprint = dict(aliases=['id'], required=False),
            name = dict(required=False),
            ssh_pub_key = dict(required=False),
            oauth_token = dict(
                no_log=True,
                # Support environment variable for DigitalOcean OAuth Token
                fallback=(env_fallback, ['DO_OAUTH_TOKEN', 'DO_API_TOKEN', 'DO_API_KEY']),
                required=True,
            ),
        ),
        required_one_of = (
            ('fingerprint', 'ssh_pub_key'),
        ),
        # required_if = ([
        #     ('state', 'absent', ['fingerprint']),
        #     ('state', 'present', ['ssh_pub_key']),
        # ]),
        # required_together = (),
        # mutually_exclusive = (
        #     ['region', 'droplet_id']
        # ),
        supports_check_mode=True,
    )

    core(module)

if __name__ == '__main__':
    main()
