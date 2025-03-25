# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack, LLC
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
Functional tests for the Swift store interface

Set the GLANCE_TEST_SWIFT_CONF environment variable to the location
of a Glance config that defines how to connect to a functional
Swift backend
"""

import ConfigParser
import os
import os.path
import random
import StringIO
import unittest
import urlparse
import urllib

import nose.plugins.skip

import glance.openstack.common.cfg
from glance.openstack.common import uuidutils
import glance.store.swift
import glance.tests.functional.store as store_tests

try:
    import swiftclient
except ImportError:
    swiftclient = None


class SwiftStoreError(RuntimeError):
    pass


def _uniq(value):
    return '%s.%d' % (value, random.randint(0, 99999))


def read_config(path):
    cp = ConfigParser.RawConfigParser()
    cp.read(path)
    return cp


def parse_config(config):
    out = {}
    options = [
        'swift_store_auth_address',
        'swift_store_auth_version',
        'swift_store_user',
        'swift_store_key',
        'swift_store_container',
    ]

    for option in options:
        out[option] = config.defaults()[option]

    return out


def swift_connect(auth_url, auth_version, user, key):
    try:
        return swiftclient.Connection(authurl=auth_url,
                                      auth_version=auth_version,
                                      user=user,
                                      key=key,
                                      snet=False,
                                      retries=1)
    except AttributeError:
        msg = "Could not find swiftclient module"
        raise nose.SkipTest(msg)


def swift_list_containers(swift_conn):
    try:
        _, containers = swift_conn.get_account()
    except Exception, e:
        msg = ("Failed to list containers (get_account) "
               "from Swift. Got error: %s" % e)
        raise SwiftStoreError(msg)
    else:
        return containers


def swift_create_container(swift_conn, container_name):
    try:
        swift_conn.put_container(container_name)
    except swiftclient.ClientException, e:
        msg = "Failed to create container. Got error: %s" % e
        raise SwiftStoreError(msg)


def swift_get_container(swift_conn, container_name, **kwargs):
    return swift_conn.get_container(container_name, **kwargs)


def swift_delete_container(swift_conn, container_name):
    try:
        swift_conn.delete_container(container_name)
    except swiftclient.ClientException, e:
        msg = "Failed to delete container from Swift. Got error: %s" % e
        raise SwiftStoreError(msg)


def swift_put_object(swift_conn, container_name, object_name, contents):
    return swift_conn.put_object(container_name, object_name, contents)


def swift_head_object(swift_conn, container_name, obj_name):
    return swift_conn.head_object(container_name, obj_name)


def keystone_authenticate(auth_url, auth_version, tenant_name,
                          username, password):
    assert int(auth_version) == 2, 'Only auth version 2 is supported'

    import keystoneclient.v2_0.client
    ksclient = keystoneclient.v2_0.client.Client(tenant_name=tenant_name,
                                                 username=username,
                                                 password=password,
                                                 auth_url=auth_url)

    auth_resp = ksclient.service_catalog.catalog
    tenant_id = auth_resp['token']['tenant']['id']
    service_catalog = auth_resp['serviceCatalog']
    return tenant_id, ksclient.auth_token, service_catalog


class TestSwiftStore(store_tests.BaseTestCase, unittest.TestCase):

    store_cls = glance.store.swift.Store
    store_name = 'swift'

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_SWIFT_CONF')
        if not config_path:
            msg = "GLANCE_TEST_SWIFT_CONF environ not set."
            raise nose.SkipTest(msg)

        glance.openstack.common.cfg.CONF(default_config_files=[config_path])

        raw_config = read_config(config_path)
        config = parse_config(raw_config)

        swift = swift_connect(config['swift_store_auth_address'],
                              config['swift_store_auth_version'],
                              config['swift_store_user'],
                              config['swift_store_key'])

        #NOTE(bcwaldon): Ensure we have a functional swift connection
        swift_list_containers(swift)

        self.swift_client = swift
        self.swift_config = config

        self.swift_config['swift_store_create_container_on_put'] = True

        super(TestSwiftStore, self).setUp()

    def get_store(self, **kwargs):
        store = glance.store.swift.Store(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def get_default_store_specs(self, image_id):
        return {
            'scheme': 'swift+http',
            'auth_or_store_url': self.swift_config['swift_store_auth_address'],
            'user': self.swift_config['swift_store_user'],
            'key': self.swift_config['swift_store_key'],
            'container': self.swift_config['swift_store_container'],
            'obj': image_id,
        }

    def test_object_chunking(self):
        """Upload an image that is split into multiple swift objects.

        We specifically check the case that
        image_size % swift_store_large_object_chunk_size != 0 to
        ensure we aren't losing image data.
        """
        self.config(
            swift_store_large_object_size=2,  # 2 MB
            swift_store_large_object_chunk_size=2,  # 2 MB
        )
        store = self.get_store()
        image_id = uuidutils.generate_uuid()
        image_size = 5242880  # 5 MB
        image_data = StringIO.StringIO('X' * image_size)
        image_checksum = 'eb7f8c3716b9f059cee7617a4ba9d0d3'
        uri, add_size, add_checksum = store.add(image_id,
                                                image_data,
                                                image_size)

        self.assertEqual(image_size, add_size)
        self.assertEqual(image_checksum, add_checksum)

        location = glance.store.location.Location(
                self.store_name,
                store.get_store_location_class(),
                uri=uri,
                image_id=image_id)

        # Store interface should still be respected even though
        # we are storing images in multiple Swift objects
        (get_iter, get_size) = store.get(location)
        self.assertEqual('5242880', get_size)
        self.assertEqual('X' * 5242880, ''.join(get_iter))

        # The object should have a manifest pointing to the chunks
        # of image data
        swift_location = location.store_location
        headers = swift_head_object(self.swift_client,
                                    swift_location.container,
                                    swift_location.obj)
        manifest = headers.get('x-object-manifest')
        self.assertTrue(manifest)

        # Verify the objects in the manifest exist
        manifest_container, manifest_prefix = manifest.split('/', 1)
        container = swift_get_container(self.swift_client,
                                        manifest_container,
                                        prefix=manifest_prefix)
        segments = [segment['name'] for segment in container[1]]

        for segment in segments:
            headers = swift_head_object(self.swift_client,
                                        manifest_container,
                                        segment)
            self.assertTrue(headers.get('content-length'))

        # Since we used a 5 MB image with a 2 MB chunk size, we should
        # expect to see the manifest object and three data objects for
        # a total of 4
        self.assertEqual(4, len(segments), 'Got segments %s' % segments)

        store.delete(location)

        # Verify the segments in the manifest are all gone
        for segment in segments:
            self.assertRaises(swiftclient.ClientException,
                              swift_head_object,
                              self.swift_client,
                              manifest_container,
                              segment)

    def stash_image(self, image_id, image_data):
        container_name = self.swift_config['swift_store_container']
        swift_put_object(self.swift_client,
                         container_name,
                         image_id,
                         'XXX')

        #NOTE(bcwaldon): This is a hack until we find a better way to
        # build this URL
        auth_url = self.swift_config['swift_store_auth_address']
        auth_url = urlparse.urlparse(auth_url)
        user = urllib.quote(self.swift_config['swift_store_user'])
        key = self.swift_config['swift_store_key']
        netloc = ''.join(('%s:%s' % (user, key), '@', auth_url.netloc))
        path = os.path.join(auth_url.path, container_name, image_id)

        # This is an auth url with /<CONTAINER>/<OBJECT> on the end
        return 'swift+http://%s%s' % (netloc, path)

    def test_multitenant(self):
        """Ensure an image is properly configured when using multitenancy."""
        fake_swift_admin = 'd2f68325-8e2c-4fb1-8c8b-89de2f3d9c4a'
        self.config(
            swift_store_multi_tenant=True,
        )

        swift_store_user = self.swift_config['swift_store_user']
        tenant_name, username = swift_store_user.split(':')
        tenant_id, auth_token, service_catalog = keystone_authenticate(
                self.swift_config['swift_store_auth_address'],
                self.swift_config['swift_store_auth_version'],
                tenant_name,
                username,
                self.swift_config['swift_store_key'])

        context = glance.context.RequestContext(
                tenant=tenant_id,
                service_catalog=service_catalog,
                auth_tok=auth_token)
        store = self.get_store(context=context)

        image_id = uuidutils.generate_uuid()
        image_data = StringIO.StringIO('XXX')
        uri, _, _ = store.add(image_id, image_data, 3)

        location = glance.store.location.Location(
                self.store_name,
                store.get_store_location_class(),
                uri=uri,
                image_id=image_id)

        read_tenant = uudiutils.generate_uuid()
        write_tenant = uuidutils.generate_uuid()
        store.set_acls(location,
                       public=False,
                       read_tenants=[read_tenant],
                       write_tenants=[write_tenant])

        container_name = location.store_location.container
        container, _ = swift_get_container(self.swift_client, container_name)
        self.assertEqual(read_tenant, container.get('x-container-read'))
        self.assertEqual(write_tenant, container.get('x-container-write'))

        store.set_acls(location, public=True, read_tenants=[read_tenant])

        container_name = location.store_location.container
        container, _ = swift_get_container(self.swift_client, container_name)
        self.assertEqual('.r:*', container.get('x-container-read'))
        self.assertEqual('', container.get('x-container-write', ''))

        (get_iter, get_size) = store.get(location)
        self.assertEqual('3', get_size)
        self.assertEqual('XXX', ''.join(get_iter))

        store.delete(location)
