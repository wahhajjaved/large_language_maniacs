# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Handles all requests relating to volumes + cinder.
"""


from cinderclient import service_catalog
from cinderclient.v1 import client as cinder_client

from nova.db import base
from nova import exception
from nova import flags
from nova.openstack.common import log as logging

FLAGS = flags.FLAGS

LOG = logging.getLogger(__name__)


def cinderclient(context):

    # FIXME: the cinderclient ServiceCatalog object is mis-named.
    #        It actually contains the entire access blob.
    compat_catalog = {
        'access': {'serviceCatalog': context.service_catalog}
    }
    sc = service_catalog.ServiceCatalog(compat_catalog)
    url = sc.url_for(service_type='volume', service_name='cinder')

    LOG.debug(_('Cinderclient connection created using URL: %s') % url)

    c = cinder_client.Client(context.user_id,
                             context.auth_token,
                             project_id=context.project_id,
                             auth_url=url)
    c.client.auth_token = context.auth_token
    c.client.management_url = url
    return c


def _untranslate_volume_summary_view(context, vol):
    """Maps keys for volumes summary view."""
    d = {}
    d['id'] = vol.id
    d['status'] = vol.status
    d['size'] = vol.size
    d['availability_zone'] = vol.availability_zone
    d['created_at'] = vol.created_at

    # TODO(jdg): The calling code expects attach_time and
    #            mountpoint to be set. When the calling
    #            code is more defensive this can be
    #            removed.
    d['attach_time'] = ""
    d['mountpoint'] = ""

    if vol.attachments:
        att = vol.attachments[0]
        d['attach_status'] = 'attached'
        d['instance_uuid'] = att['server_id']
        d['mountpoint'] = att['device']
    else:
        d['attach_status'] = 'detached'

    d['display_name'] = vol.display_name
    d['display_description'] = vol.display_description

    # TODO(jdg): Information may be lost in this translation
    d['volume_type_id'] = vol.volume_type
    d['snapshot_id'] = vol.snapshot_id

    d['volume_metadata'] = []
    for key, value in vol.metadata.items():
        item = {}
        item['key'] = key
        item['value'] = value
        d['volume_metadata'].append(item)

    return d


def _untranslate_snapshot_summary_view(context, snapshot):
    """Maps keys for snapshots summary view."""
    d = {}

    d['id'] = snapshot.id
    d['status'] = snapshot.status
    d['progress'] = snapshot.progress
    d['size'] = snapshot.size
    d['created_at'] = snapshot.created_at
    d['display_name'] = snapshot.display_name
    d['display_description'] = snapshot.display_description
    d['volume_id'] = snapshot.volume_id
    d['project_id'] = snapshot.project_id
    d['volume_size'] = snapshot.size

    return d


class API(base.Base):
    """API for interacting with the volume manager."""

    def get(self, context, volume_id):
        item = cinderclient(context).volumes.get(volume_id)
        return _untranslate_volume_summary_view(context, item)

    def get_all(self, context, search_opts={}):
        items = cinderclient(context).volumes.list(detailed=True)
        rval = []

        for item in items:
            rval.append(_untranslate_volume_summary_view(context, item))

        return rval

    def check_attach(self, context, volume):
        # TODO(vish): abstract status checking?
        if volume['status'] != "available":
            msg = _("status must be available")
            raise exception.InvalidVolume(reason=msg)
        if volume['attach_status'] == "attached":
            msg = _("already attached")
            raise exception.InvalidVolume(reason=msg)

    def check_detach(self, context, volume):
        # TODO(vish): abstract status checking?
        if volume['status'] == "available":
            msg = _("already detached")
            raise exception.InvalidVolume(reason=msg)

    def reserve_volume(self, context, volume):
        cinderclient(context).volumes.reserve(volume['id'])

    def unreserve_volume(self, context, volume):
        cinderclient(context).volumes.reserve(volume['id'])

    def attach(self, context, volume, instance_uuid, mountpoint):
        cinderclient(context).volumes.attach(volume['id'],
                                             instance_uuid,
                                             mountpoint)

    def detach(self, context, volume):
        cinderclient(context).volumes.detach(volume['id'])

    def initialize_connection(self, context, volume, connector):
        return cinderclient(context).\
                 volumes.initialize_connection(volume['id'], connector)

    def terminate_connection(self, context, volume, connector):
        return cinderclient(context).\
                 volumes.terminate_connection(volume['id'], connector)

    def create(self, context, size, name, description, snapshot=None,
               volume_type=None, metadata=None, availability_zone=None):

        item = cinderclient(context).volumes.create(size,
                                                    snapshot,
                                                    name,
                                                    description,
                                                    volume_type,
                                                    context.user_id,
                                                    context.project_id,
                                                    availability_zone,
                                                    metadata)

        return _untranslate_volume_summary_view(context, item)

    def delete(self, context, volume):
        cinderclient(context).volumes.delete(volume['id'])

    def update(self, context, volume, fields):
        raise NotImplementedError()

    def get_snapshot(self, context, snapshot_id):
        item = cinderclient(context).volume_snapshots.get(snapshot_id)
        return _untranslate_snapshot_summary_view(context, item)

    def get_all_snapshots(self, context):
        items = cinderclient(context).volume_snapshots.list(detailed=True)
        rvals = []

        for item in items:
            rvals.append(_untranslate_snapshot_summary_view(context, item))

        return rvals

    def create_snapshot(self, context, volume, name, description):
        item = cinderclient(context).volume_snapshots.create(volume['id'],
                                                             False,
                                                             name,
                                                             description)
        return _untranslate_snapshot_summary_view(context, item)

    def create_snapshot_force(self, context, volume, name, description):
        item = cinderclient(context).volume_snapshots.create(volume['id'],
                                                             True,
                                                             name,
                                                             description)

        return _untranslate_snapshot_summary_view(context, item)

    def delete_snapshot(self, context, snapshot):
        cinderclient(context).volume_snapshots.delete(snapshot['id'])

    def get_volume_metadata(self, context, volume):
        raise NotImplementedError()

    def delete_volume_metadata(self, context, volume, key):
        raise NotImplementedError()

    def update_volume_metadata(self, context, volume, metadata, delete=False):
        raise NotImplementedError()

    def get_volume_metadata_value(self, volume, key):
        raise NotImplementedError()
