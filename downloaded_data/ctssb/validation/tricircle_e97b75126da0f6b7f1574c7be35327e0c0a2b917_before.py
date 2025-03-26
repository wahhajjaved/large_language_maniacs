# Copyright 2014  Huawei Technologies Co., LTD
# All Rights Reserved.
#
#    @author: z00209472, Huawei Technologies Co., LTD
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
cinder-proxy manages creating, attaching, detaching, and persistent storage.
cinder-proxy acts as the same role of cinder-volume in cascading OpenStack.
cinder-proxy treats cascaded cinder as its cinder volume,convert the internal
request message from the message bus to restful API calling to cascaded cinder.

Persistent storage volumes keep their state independent of instances.  You can
attach to an instance, terminate the instance, spawn a new instance (even
one from a different image) and re-attach the volume with the same data
intact.

**Related Flags**

:volume_topic:  What :mod:`rpc` topic to listen to (default: `cinder-volume`).
:volume_manager:  The module name of a class derived from
                  :class:`manager.Manager` (default:
                  :class:`cinder.volume.cinder_proxy.CinderProxy`).
:volume_group:  Name of the group that will contain exported volumes (default:
                `cinder-volumes`)
:num_shell_tries:  Number of times to attempt to run commands (default: 3)

"""
import time

from oslo.config import cfg
from oslo import messaging

from cinder import context
from cinder import exception
from cinder import manager
from cinder import quota
from cinder import utils
from cinder import volume

from cinder.i18n import _
from cinder.image import glance
from cinder.openstack.common import excutils
from cinder.openstack.common import log as logging
from cinder.openstack.common import periodic_task
from cinder.openstack.common import timeutils
from cinder.openstack.common import uuidutils
from cinder.volume.configuration import Configuration
from cinder.volume import utils as volume_utils
from cinderclient.v2 import client as cinder_client
from cinderclient import exceptions as cinder_exception

from eventlet.greenpool import GreenPool
from keystoneclient.v2_0 import client as kc
from keystoneclient import exceptions as keystone_exception


LOG = logging.getLogger(__name__)

QUOTAS = quota.QUOTAS
CGQUOTAS = quota.CGQUOTAS

volume_manager_opts = [
    cfg.IntOpt('migration_create_volume_timeout_secs',
               default=300,
               help='Timeout for creating the volume to migrate to '
                    'when performing volume migration (seconds)'),
    cfg.ListOpt('enabled_volume_types',
                default=None,
                help='A list of volume types to use'),
    cfg.IntOpt('volume_sync_interval',
               default=5,
               help='seconds between cascading and cascaded cinders'
                    'when synchronizing volume data'),
    cfg.IntOpt('pagination_limit',
               default=50,
               help='pagination limit query for volumes between'
                    'cascading and cascaded OpenStack'),
    cfg.IntOpt('voltype_sync_interval',
               default=3600,
               help='seconds between cascading and cascaded cinders'
                    'when synchronizing volume type and qos data'),
    cfg.BoolOpt('volume_sync_timestamp_flag',
                default=True,
                help='whether to sync volume status based on timestamp'),
    cfg.BoolOpt('clean_extra_cascaded_vol_flag',
                default=False,
                help='whether to clean extra cascaded volumes while sync'
                     'volumes between cascading and cascaded OpenStack'
                     'please with caution when set to True'),
    cfg.BoolOpt('volume_service_inithost_offload',
                default=False,
                help='Offload pending volume delete during '
                     'volume service startup'),
    cfg.StrOpt('cinder_username',
               default='cinder_username',
               help='username for connecting to cinder in admin context'),
    cfg.StrOpt('cinder_password',
               default='cinder_password',
               help='password for connecting to cinder in admin context',
               secret=True),
    cfg.StrOpt('cinder_tenant_id',
               default='cinder_tenant_id',
               help='tenant id for connecting to cinder in admin context'),
    cfg.StrOpt('cascaded_available_zone',
               default='nova',
               help='available zone for cascaded OpenStack'),
    cfg.StrOpt('keystone_auth_url',
               default='http://127.0.0.1:5000/v2.0/',
               help='value of keystone url'),
    cfg.StrOpt('cascaded_cinder_url',
               default='http://127.0.0.1:8776/v2/%(project_id)s',
               help='value of cascaded cinder url'),
    cfg.StrOpt('cascading_cinder_url',
               default='http://127.0.0.1:8776/v2/%(project_id)s',
               help='value of cascading cinder url'),
    cfg.BoolOpt('glance_cascading_flag',
                default=False,
                help='Whether to use glance cescaded'),
    cfg.StrOpt('cascading_glance_url',
               default='127.0.0.1:9292',
               help='value of cascading glance url'),
    cfg.StrOpt('cascaded_glance_url',
               default='http://127.0.0.1:9292',
               help='value of cascaded glance url'),
    cfg.StrOpt('cascaded_region_name',
               default='RegionOne',
               help='Region name of this node'),
]
CONF = cfg.CONF
CONF.register_opts(volume_manager_opts)


def locked_volume_operation(f):




    """Lock decorator for volume operations.

    Takes a named lock prior to executing the operation. The lock is named with
    the operation executed and the id of the volume. This lock can then be used
    by other operations to avoid operation conflicts on shared volumes.

    Example use:

    If a volume operation uses this decorator, it will block until the named
    lock is free. This is used to protect concurrent operations on the same
    volume e.g. delete VolA while create volume VolB from VolA is in progress.
    """
    def lvo_inner1(inst, context, volume_id, **kwargs):
        @utils.synchronized("%s-%s" % (volume_id, f.__name__), external=True)
        def lvo_inner2(*_args, **_kwargs):
            return f(*_args, **_kwargs)
        return lvo_inner2(inst, context, volume_id, **kwargs)
    return lvo_inner1 


def locked_snapshot_operation(f):
    """Lock decorator for snapshot operations.

    Takes a named lock prior to executing the operation. The lock is named with
    the operation executed and the id of the snapshot. This lock can then be
    used by other operations to avoid operation conflicts on shared snapshots.

    Example use:

    If a snapshot operation uses this decorator, it will block until the named
    lock is free. This is used to protect concurrent operations on the same
    snapshot e.g. delete SnapA while create volume VolA from SnapA is in
    progress.
    """
    def lso_inner1(inst, context, snapshot_id, **kwargs):
        @utils.synchronized("%s-%s" % (snapshot_id, f.__name__), external=True)
        def lso_inner2(*_args, **_kwargs):
            return f(*_args, **_kwargs)
        return lso_inner2(inst, context, snapshot_id, **kwargs)
    return lso_inner1


class CinderProxy(manager.SchedulerDependentManager):

    """Manages attachable block storage devices."""

    RPC_API_VERSION = '1.18'
    target = messaging.Target(version=RPC_API_VERSION)

    VOLUME_NAME_MAX_LEN = 255
    VOLUME_UUID_MAX_LEN = 36
    SNAPSHOT_NAME_MAX_LEN = 255
    SNAPSHOT_UUID_MAX_LEN = 36

    def __init__(self, service_name=None, *args, **kwargs):
        """Load the specified in args, or flags."""
        # update_service_capabilities needs service_name to be volume
        super(CinderProxy, self).__init__(service_name='volume',
                                          *args, **kwargs)
        self.configuration = Configuration(volume_manager_opts,
                                           config_group=service_name)
        self._tp = GreenPool()
        self.volume_api = volume.API()
        self._last_info_volume_state_heal = 0
        self._change_since_time = None
        self.volumes_mapping_cache = {'volumes': {}, 'snapshots': {}}
        self.image_service = glance.get_default_image_service()
        self.adminCinderClient = self._get_cinder_cascaded_admin_client()
        self._init_volume_mapping_cache()

    def _init_volume_mapping_cache(self):
        try:
            volumes = \
                self._query_vol_cascaded_pagination(change_since_time=None)
            for vol in volumes:
                ccding_volume_id = self._get_ccding_volume_id(vol)
                if ccding_volume_id == '':
                    continue
                self.volumes_mapping_cache['volumes'][ccding_volume_id] = \
                    vol._info['id']

            snapshots = self._query_snapshot_cascaded_all_tenant()
            for snapshot in snapshots:
                ccding__snapshot_id = self._get_ccding_snapsot_id(snapshot)
                if ccding__snapshot_id == '':
                    continue
                self.volumes_mapping_cache['snapshots'][ccding__snapshot_id] = \
                    snapshot._info['id']

            LOG.info(_("cascade info: init volume mapping cache is %s"),
                     self.volumes_mapping_cache)
        except Exception as ex:
            LOG.error(_("Failed init volumes mapping cache"))
            LOG.exception(ex)

    def _get_ccding_volume_id(self, volume):
        csd_name = volume._info.get("name", None)
        if csd_name is None:
            LOG.error(_("Cascade info: csd_name is None!!!. %s"),
                      volume._info)
            return ''

        uuid_len = self.VOLUME_UUID_MAX_LEN
        if len(csd_name) > (uuid_len+1) and csd_name[-(uuid_len+1)] == '@':
            return csd_name[-uuid_len:]
        try:
            return volume._info['metadata']['logicalVolumeId']
        except KeyError:
            return ''

    def _get_ccding_snapsot_id(self, snapshot):
        csd_name = snapshot._info["name"]
        uuid_len = self.SNAPSHOT_UUID_MAX_LEN
        if len(csd_name) > (uuid_len+1) and csd_name[-(uuid_len+1)] == '@':
            return csd_name[-uuid_len:]
        try:
            return snapshot._info['metadata']['logicalVolumeId']
        except KeyError:
            return ''

    def _gen_ccding_volume_name(self, volume_name, volume_id):
        max_len = self.VOLUME_NAME_MAX_LEN - self.VOLUME_UUID_MAX_LEN - 1
        if (len(volume_name) <= max_len):
            return volume_name + "@" + volume_id
        else:
            return volume_name[0:max_len] + "@" + volume_id

    def _gen_ccding_snapshot_name(self, snapshot_name, snapshot_id):
        max_len = self.SNAPSHOT_NAME_MAX_LEN - self.SNAPSHOT_UUID_MAX_LEN - 1
        if (len(snapshot_name) <= max_len):
            return snapshot_name + "@" + snapshot_id
        else:
            return snapshot_name[0:max_len] + "@" + snapshot_id

    def _get_cinder_cascaded_admin_client(self):

        try:
            kwargs = {'username': cfg.CONF.cinder_username,
                      'password': cfg.CONF.cinder_password,
                      'tenant_id': cfg.CONF.cinder_tenant_id,
                      'auth_url': cfg.CONF.keystone_auth_url
                      }

            keystoneclient = kc.Client(**kwargs)
            cinderclient = cinder_client.Client(
                username=cfg.CONF.cinder_username,
                auth_url=cfg.CONF.keystone_auth_url,
                insecure=True)
            cinderclient.client.auth_token = keystoneclient.auth_ref.auth_token
            diction = {'project_id': cfg.CONF.cinder_tenant_id}
            cinderclient.client.management_url = \
                cfg.CONF.cascaded_cinder_url % diction

            return cinderclient
        except keystone_exception.Unauthorized:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Token unauthorized failed for keystoneclient '
                            'constructed when get cascaded admin client'))
        except cinder_exception.Unauthorized:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Token unauthorized failed for cascaded '
                            'cinderClient constructed'))
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to get cinder python client.'))

    def _get_cinder_cascaded_user_client(self, context):

        try:
            ctx_dict = context.to_dict()
            cinderclient = cinder_client.Client(
                username=ctx_dict.get('user_id'),
                auth_url=cfg.CONF.keystone_auth_url,
                insecure=True)
            cinderclient.client.auth_token = ctx_dict.get('auth_token')
            cinderclient.client.management_url = \
                cfg.CONF.cascaded_cinder_url % ctx_dict
            return cinderclient

        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to get cinder python client.'))

    def _get_image_cascaded(self, context, image_id, cascaded_glance_url):

        try:
            # direct_url is returned by v2 api
            netloc = cfg.CONF.cascading_glance_url
            header = 'http://'
            if header in cfg.CONF.cascading_glance_url:
                netloc = netloc[len(header):]

            client = glance.GlanceClientWrapper(
                context,
                netloc=netloc,
                use_ssl=False,
                version="2")
            image_meta = client.call(context, 'get', image_id)

        except Exception:
            glance._reraise_translated_image_exception(image_id)

        if not self.image_service._is_image_available(context, image_meta):
            raise exception.ImageNotFound(image_id=image_id)

        LOG.debug(_("cascade ino: image glance get_image_cascaded,"
                    "cascaded_glance_url:%s"), cascaded_glance_url)

        locations = getattr(image_meta, 'locations', None)
        LOG.debug(_("cascade ino: image glance get_image_cascaded,"
                    "locations:%s"), locations)
        cascaded_image_id = None
        for loc in locations:
            image_url = loc.get('url')
            LOG.debug(_("cascade ino: image glance get_image_cascaded,"
                        "image_url:%s"), image_url)
            if cascaded_glance_url in image_url:
                (cascaded_image_id, glance_netloc, use_ssl) = \
                    glance._parse_image_ref(image_url)
                LOG.debug(_("cascade ino : result :image glance "
                            "get_image_cascaded,%s") % cascaded_image_id)
                break

        if cascaded_image_id is None:
            raise exception.CinderException(
                _("cascade exception: cascaded image for image %s not exist.")
                % image_id)

        return cascaded_image_id

    def _add_to_threadpool(self, func, *args, **kwargs):
        self._tp.spawn_n(func, *args, **kwargs)

    def init_host(self):
        """Do any initialization that needs to be run if this is a
           standalone service.
        """

        ctxt = context.get_admin_context()

        volumes = self.db.volume_get_all_by_host(ctxt, self.host)
        LOG.debug(_("Re-exporting %s volumes"), len(volumes))

        LOG.debug(_('Resuming any in progress delete operations'))
        for volume in volumes:
            if volume['status'] == 'deleting':
                LOG.info(_('Resuming delete on volume: %s') % volume['id'])
                if CONF.volume_service_inithost_offload:
                    # Offload all the pending volume delete operations to the
                    # threadpool to prevent the main volume service thread
                    # from being blocked.
                    self._add_to_threadpool(self.delete_volume(ctxt,
                                                               volume['id']))
                else:
                    # By default, delete volumes sequentially
                    self.delete_volume(ctxt, volume['id'])

        # collect and publish service capabilities
        self.publish_service_capabilities(ctxt)

    def create_volume(self, context, volume_id, request_spec=None,
                      filter_properties=None, allow_reschedule=True,
                      snapshot_id=None, image_id=None, source_volid=None,
                      source_replicaid=None, consistencygroup_id=None):
        """Creates and exports the volume."""

        ctx_dict = context.to_dict()
        try:
            volume_properties = request_spec.get('volume_properties')
            size = volume_properties.get('size')
            volume_name = volume_properties.get('display_name')
            display_name = self._gen_ccding_volume_name(volume_name, volume_id)
            display_description = volume_properties.get('display_description')
            volume_type_id = volume_properties.get('volume_type_id')
            user_id = ctx_dict.get('user_id')
            project_id = ctx_dict.get('project_id')

            cascaded_snapshot_id = None
            if snapshot_id is not None:
                cascaded_snapshot_id = \
                    self.volumes_mapping_cache['snapshots'].get(snapshot_id,
                                                                None)
                LOG.info(_('cascade ino: create volume from snapshot, '
                           'cascade id:%s'), cascaded_snapshot_id)

            cascaded_source_volid = None
            if source_volid is not None:
                cascaded_source_volid = \
                    self.volumes_mapping_cache['volumes'].get(source_volid,
                                                              None)
                LOG.info(_('cascade ino: create volume from source volume, '
                           'cascade id:%s'), cascaded_source_volid)

            cascaded_volume_type = None
            if volume_type_id is not None:
                volume_type_ref = \
                    self.db.volume_type_get(context, volume_type_id)
                cascaded_volume_type = volume_type_ref['name']
                LOG.info(_('cascade ino: create volume use volume type, '
                           'cascade name:%s'), cascaded_volume_type)

            cascaded_image_id = None
            if image_id is not None:
                if cfg.CONF.glance_cascading_flag:
                    cascaded_image_id = self._get_image_cascaded(
                        context,
                        image_id,
                        cfg.CONF.cascaded_glance_url)
                else:
                    cascaded_image_id = image_id
                LOG.info(_("cascade ino: create volume use image, "
                           "cascaded image id is %s:"), cascaded_image_id)

            availability_zone = cfg.CONF.cascaded_available_zone
            LOG.info(_('cascade ino: create volume with available zone:%s'),
                     availability_zone)

            metadata = volume_properties.get('metadata', {})
            metadata['logicalVolumeId'] = volume_id

            cinderClient = self._get_cinder_cascaded_user_client(context)

            bodyResponse = cinderClient.volumes.create(
                size=size,
                snapshot_id=cascaded_snapshot_id,
                source_volid=cascaded_source_volid,
                name=display_name,
                description=display_description,
                volume_type=cascaded_volume_type,
                user_id=user_id,
                project_id=project_id,
                availability_zone=availability_zone,
                metadata=metadata,
                imageRef=cascaded_image_id)

            if bodyResponse._info['status'] == 'creating':
                self.volumes_mapping_cache['volumes'][volume_id] = \
                    bodyResponse._info['id']
                if 'logicalVolumeId' in metadata:
                    metadata.pop('logicalVolumeId')
                metadata['mapping_uuid'] = bodyResponse._info['id']
                self.db.volume_metadata_update(context, volume_id,
                                               metadata, True)
            return volume_id

        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.volume_update(context,
                                      volume_id,
                                      {'status': 'error'})

    def _query_vol_cascaded_pagination(self, change_since_time=None):

        if not CONF.volume_sync_timestamp_flag:
            change_since_time = None

        try:
            page_limit = CONF.pagination_limit
            marker = None
            volumes = []
            while True:
                sopt = {'all_tenants': True,
                        'changes-since': change_since_time,
                        'sort_key': 'updated_at',
                        'sort_dir': 'desc',
                        'marker': marker,
                        'limit': page_limit,
                        }
                vols = \
                    self.adminCinderClient.volumes.list(search_opts=sopt)

                LOG.debug(_('cascade ino: volume pagination query. marker: %s,'
                            ' pagination_limit: %s, change_since: %s, vols: %s'
                            ), marker, page_limit, change_since_time,  vols)

                if (vols):
                    volumes.extend(vols)
                    marker = vols[-1]._info['id']
                    continue
                else:
                    break

            LOG.debug(_('cascade ino: ready to update volume status from '
                        'pagination query. volumes: %s'), volumes)
            return volumes
        except cinder_exception.Unauthorized:
            self.adminCinderClient = self._get_cinder_cascaded_admin_client()
            return self._query_vol_cascaded_pagination(change_since_time)
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to query volumes by pagination.'))

    def _query_snapshot_cascaded_all_tenant(self):
        """ cinder snapshots pagination query API has not been supported until
            native OpenStack Juno version yet.
        """
        try:
            opts = {'all_tenants': True}
            snapshots = \
                self.adminCinderClient.volume_snapshots.list(search_opts=opts)
            LOG.debug(_('cascade ino: snapshots query.'
                        'snapshots: %s'),  snapshots)
            return snapshots
        except cinder_exception.Unauthorized:
            self.adminCinderClient = self._get_cinder_cascaded_admin_client()
            return self._query_snapshot_cascaded_all_tenant()
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to query snapshots by all tenant.'))

    def _check_update_volume(self, context, refresh_vol):
        '''check refresh volumes before update'''

        volume_id = refresh_vol._info['metadata'].get('logicalVolumeId', None)
        if volume_id is None:
            LOG.error(_("cascade info: logicalVolumeId for %s is None !"),
                      volume_id)
            return False

        volume = self.db.volume_get(context, volume_id)
        volume_metadata = dict((item['key'], item['value'])
                               for item in volume['volume_metadata'])
        mapping_uuid = volume_metadata.get('mapping_uuid', None)

        ccded_id = self.volumes_mapping_cache['volumes'].get(volume_id, None)
        if ccded_id is None:
            LOG.error(_("cascade info:cascaded volume for %s in volume mapping"
                        "cache is None"), volume_id)
            return False

        if mapping_uuid != ccded_id:
            msg = _("cascade info: cascaded vol for %(volume_id)s in volume"
                    " mapping cache is %(ccded_id)s ,not equal mapping_uuid"
                    "%(mapping_uuid)s")
            LOG.error(msg % {"volume_id": volume_id,
                             "ccded_id": ccded_id,
                             "mapping_uuid": mapping_uuid})
            return False

        if ccded_id != refresh_vol._info['id']:
            rtn_id = refresh_vol._info['id']
            msg = _("cascade info: cascaded vol id %(ccded_id)s not equal"
                    " return volume id:%(rtn_id)s")
            LOG.error(msg % {"ccded_id": ccded_id,
                             "rtn_id": rtn_id})
            return False

        return True

    def _update_volumes(self, context, volumes):
        for volume in volumes:
            LOG.debug(_("cascade ino: update volume:%s"), str(volume._info))
            try:
                ret = self._check_update_volume(context, volume)
                if not ret:
                    if CONF.clean_extra_cascaded_vol_flag:
                        ccded_vol = volume._info['id']
                        self.adminCinderClient.volumes.delete(volume=ccded_vol)
                        LOG.info(_("Cascade info:cascaded volume %s deleted!"),
                                 ccded_vol)
                    continue

                volume_id = volume._info['metadata']['logicalVolumeId']
                volume_status = volume._info['status']
                if volume_status == "available":
                    if volume._info['bootable'].lower() == 'false':
                        bootable_vl = '0'
                    else:
                        bootable_vl = '1'
                    self.db.volume_update(context, volume_id,
                                          {'status': volume._info['status'],
                                           'attach_status': 'detached',
                                           'instance_uuid': None,
                                           'attached_host': None,
                                           'mountpoint': None,
                                           'attach_time': None,
                                           'bootable': bootable_vl
                                           })
                    metadata = volume._info['metadata']
                    self._update_volume_metada(context, volume_id, metadata)
                elif volume_status == "in-use":
                    self.db.volume_update(context, volume_id,
                                          {'status': volume._info['status'],
                                           'attach_status': 'attached',
                                           'attach_time': timeutils.strtime()
                                           })
                else:
                    self.db.volume_update(context, volume_id,
                                          {'status': volume._info['status']})
                LOG.info(_('cascade ino: updated the volume  %s status from'
                           'cinder-proxy'), volume_id)
            except exception.VolumeNotFound:
                LOG.error(_("cascade ino: cascading volume for %s not found!"),
                          volume._info['id'])
                continue

    def _update_volume_metada(self, context, volume_id, ccded_volume_metadata):
        ccding_vol_metadata = self.db.volume_metadata_get(context, volume_id)
        ccded_vol_metadata_keys = ccded_volume_metadata.keys()
        unsync_metada_keys_list = ['logicalVolumeId', 'urn', 'uri']
        for temp_unsync_key in unsync_metada_keys_list:
            if temp_unsync_key in ccded_vol_metadata_keys:
                ccded_vol_metadata_keys.remove(temp_unsync_key)

        for temp_key in ccded_vol_metadata_keys:
            ccding_vol_metadata[temp_key] =\
                ccded_volume_metadata.get(temp_key, None)

        self.db.volume_metadata_update(context, volume_id,
                                       ccding_vol_metadata, False)

    def _update_volume_types(self, context, volumetypes):
        vol_types = self.db.volume_type_get_all(context, inactive=False)
        LOG.debug(_("cascade ino:, vol_types cascading :%s"), vol_types)
        for volumetype in volumetypes:
            LOG.debug(_("cascade ino: vol types cascaded :%s"), volumetype)
            volume_type_name = volumetype._info['name']
            if volume_type_name not in vol_types.keys():
                extraspec = volumetype._info['extra_specs']
                self.db.volume_type_create(
                    context,
                    dict(name=volume_type_name, extra_specs=extraspec))
            elif not vol_types[volume_type_name]['extra_specs']:
                # don't replace existed backend, just fill blank extra specs
                # which made from inconsistent volume type update
                LOG.debug(_("update extra spec for vol_type:%s"),
                    vol_types[volume_type_name])
                extraspec = volumetype._info['extra_specs']
                vol_type = vol_types[volume_type_name]
                self.db.volume_type_extra_specs_update_or_create(
                    context, vol_type['id'], extraspec)
        LOG.debug(_("cascade ino: update volume types finished"))

    def _update_volume_qos(self, context, qosSpecs):
        qos_specs = self.db.qos_specs_get_all(context, inactive=False)

        qosname_list_cascading = []
        for qos_cascading in qos_specs:
            qosname_list_cascading.append(qos_cascading['name'])

        for qos_cascaded in qosSpecs:
            qos_name_cascaded = qos_cascaded._info['name']

            """update qos from cascaded cinder
            """
            if qos_name_cascaded not in qosname_list_cascading:
                qos_create_val = {}
                qos_create_val['name'] = qos_name_cascaded
                qos_spec_value = qos_cascaded._info['specs']
                qos_spec_value['consumer'] = \
                    qos_cascaded._info['consumer']
                qos_create_val['qos_specs'] = qos_spec_value
                LOG.info(_('cascade ino: create qos_spec %sin db'),
                         qos_name_cascaded)
                self.db.qos_specs_create(context, qos_create_val)
                LOG.info(_('cascade ino: qos_spec finished %sin db'),
                         qos_create_val)

            """update qos specs association with vol types from cascaded
            """
            qos_specs_id = qos_cascading['id']
            assoc_ccd = \
                self.db.volume_type_qos_associations_get(context,
                                                         qos_specs_id)
            qos = qos_cascaded._info['id']
            association = \
                self.adminCinderClient.qos_specs.get_associations(qos)

            for assoc in association:
                assoc_name = assoc._info['name']
                LOG.debug(_("cascade ino: assoc name %s"), assoc_name)
                if assoc_ccd is None or assoc_name not in assoc_ccd:
                    voltype = \
                        self.db.volume_type_get_by_name(context,
                                                        assoc_name)
                    LOG.debug(_("cascade ino: voltypes %s"), voltype)
                    self.db.qos_specs_associate(context,
                                                qos_cascading['id'],
                                                voltype['id'],)
        LOG.debug(_("cascade ino: update qos from cascaded finished"))

    @periodic_task.periodic_task(spacing=CONF.volume_sync_interval,
                                 run_immediately=True)
    def _heal_volume_status(self, context):

        # TIME_SHIFT_TOLERANCE = 3

        heal_interval = CONF.volume_sync_interval

        if not heal_interval:
            return

        curr_time = time.time()
        if self._last_info_volume_state_heal + heal_interval > curr_time:
            return
        self._last_info_volume_state_heal = curr_time

        try:
            LOG.debug(_('cascade ino: current change since time:'
                        '%s'), self._change_since_time)
            volumes = \
                self._query_vol_cascaded_pagination(self._change_since_time)
            if volumes:
                self._update_volumes(context, volumes)

            self._change_since_time = timeutils.isotime()

        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to sys volume status to db.'))

    @periodic_task.periodic_task(spacing=CONF.voltype_sync_interval,
                                 run_immediately=True)
    def _heal_volumetypes_and_qos(self, context):

        try:

            volumetypes = self.adminCinderClient.volume_types.list()
            if volumetypes:
                self._update_volume_types(context, volumetypes)

            qosSpecs = self.adminCinderClient.qos_specs.list()
            if qosSpecs:
                self._update_volume_qos(context, qosSpecs)
        except cinder_exception.Unauthorized:
            self.adminCinderClient = self._get_cinder_cascaded_admin_client()
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to sys volume type to db.'))

    @locked_volume_operation
    def delete_volume(self, context, volume_id, unmanage_only=False):
        """Deletes and unexports volume."""
        context = context.elevated()

        volume_ref = self.db.volume_get(context, volume_id)

        if context.project_id != volume_ref['project_id']:
            project_id = volume_ref['project_id']
        else:
            project_id = context.project_id

        LOG.info(_("volume %s: deleting"), volume_ref['id'])
        if volume_ref['attach_status'] == "attached":
            # Volume is still attached, need to detach first
            raise exception.VolumeAttached(volume_id=volume_id)

        self._notify_about_volume_usage(context, volume_ref, "delete.start")
        self._reset_stats()

        try:
            if unmanage_only:
                self._ummanage(context, volume_id)
            else:
                self._delete_cascaded_volume(context, volume_id)
        except exception.VolumeIsBusy:
            LOG.error(_("Cannot delete volume %s: volume is busy"),
                      volume_ref['id'])
            self.db.volume_update(context, volume_ref['id'],
                                  {'status': 'available'})
            return True
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.volume_update(context,
                                      volume_ref['id'],
                                      {'status': 'error_deleting'})

        # If deleting the source volume in a migration, we want to skip quotas
        # and other database updates.
        if volume_ref['migration_status']:
            return True

        # Get reservations
        try:
            reserve_opts = {'volumes': -1, 'gigabytes': -volume_ref['size']}
            QUOTAS.add_volume_type_opts(context,
                                        reserve_opts,
                                        volume_ref.get('volume_type_id'))
            reservations = QUOTAS.reserve(context,
                                          project_id=project_id,
                                          **reserve_opts)
        except Exception:
            reservations = None
            LOG.exception(_("Failed to update usages deleting volume"))

        # Delete glance metadata if it exists
        try:
            self.db.volume_glance_metadata_delete_by_volume(context, volume_id)
            LOG.debug(_("volume %s: glance metadata deleted"),
                      volume_ref['id'])
        except exception.GlanceMetadataNotFound:
            LOG.debug(_("no glance metadata found for volume %s"),
                      volume_ref['id'])

        self.db.volume_destroy(context, volume_id)
        LOG.info(_("volume %s: deleted successfully"), volume_ref['id'])
        self._notify_about_volume_usage(context, volume_ref, "delete.end")

        # Commit the reservations
        if reservations:
            QUOTAS.commit(context, reservations, project_id=project_id)

        self.publish_service_capabilities(context)

        return True

    def _delete_cascaded_volume(self, context, volume_id):

        try:
            # vol_ref = self.db.volume_get(context, volume_id)
            # caecaded_volume_id = vol_ref['mapping_uuid']
            cascaded_volume_id = \
                self.volumes_mapping_cache['volumes'].get(volume_id, None)
            if cascaded_volume_id is None:
                LOG.error(_("cascade info: physical volume for vol %s "
                            "not found !"), volume_id)
                return
            LOG.info(_('cascade ino: prepare to delete cascaded volume  %s.'),
                     cascaded_volume_id)

            cinderClient = self._get_cinder_cascaded_user_client(context)
            cinderClient.volumes.get(cascaded_volume_id)
            cinderClient.volumes.delete(volume=cascaded_volume_id)
            self.volumes_mapping_cache['volumes'].pop(volume_id, '')
            LOG.info(_('cascade ino: finished to delete cascade volume %s'),
                     cascaded_volume_id)
            return
            # self._heal_volume_mapping_cache(volume_id,casecade_volume_id,s'remove')
        except cinder_exception.NotFound:
            self.volumes_mapping_cache['volumes'].pop(volume_id, '')

            LOG.info(_('cascade ino: finished to delete cascade volume %s'),
                     cascaded_volume_id)
            return
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.volume_update(context,
                                      volume_id,
                                      {'status': 'error_deleting'})
                LOG.error(_('cascade ino: failed to delete cascaded'
                            'volume %s'), cascaded_volume_id)

    def create_snapshot(self, context, volume_id, snapshot_id):
        """Creates and exports the snapshot."""

        context = context.elevated()
        snapshot_ref = self.db.snapshot_get(context, snapshot_id)
        snap_name = snapshot_ref['display_name']
        display_name = self._gen_ccding_snapshot_name(snap_name, snapshot_id)
        display_description = snapshot_ref['display_description']
        LOG.info(_("snapshot %s: creating"), snapshot_ref['id'])

        self._notify_about_snapshot_usage(
            context, snapshot_ref, "create.start")

        vol_ref = self.db.volume_get(context, volume_id)

        try:
            cascaded_volume_id = \
                self.volumes_mapping_cache['volumes'].get(volume_id, '')
            LOG.debug(_('cascade ino: create snapshot, cascaded volume'
                        'id is : %s '), cascaded_volume_id)
            cinderClient = self._get_cinder_cascaded_user_client(context)
            bodyResponse = cinderClient.volume_snapshots.create(
                volume_id=cascaded_volume_id,
                force=False,
                name=display_name,
                description=display_description)

            LOG.info(_("cascade ino: create snapshot while response is:%s"),
                     bodyResponse._info)
            if bodyResponse._info['status'] == 'creating':
                self.volumes_mapping_cache['snapshots'][snapshot_id] = \
                    bodyResponse._info['id']

            while True:
                time.sleep(CONF.volume_sync_interval)
                queryResponse = \
                    cinderClient.volume_snapshots.get(bodyResponse._info['id'])
                query_status = queryResponse._info['status']
                if query_status != 'creating':
                    self.db.snapshot_update(context, snapshot_ref['id'],
                                            {'status': query_status,
                                             'progress': '100%'
                                             })
                    break
                else:
                    continue
                # self.db.snapshot_update(
                #    context,
                #    snapshot_ref['id'],
                #    {'mapping_uuid': bodyResponse._info['id']})

        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.snapshot_update(context,
                                        snapshot_ref['id'],
                                        {'status': 'error'})
                return
                # vol_ref = self.db.volume_get(context, volume_id)

        if vol_ref.bootable:
            try:
                self.db.volume_glance_metadata_copy_to_snapshot(
                    context, snapshot_ref['id'], volume_id)
            except exception.CinderException as ex:
                LOG.exception(_("Failed updating %(snapshot_id)s"
                                " metadata using the provided volumes"
                                " %(volume_id)s metadata") %
                              {'volume_id': volume_id,
                               'snapshot_id': snapshot_id})
                raise exception.MetadataCopyFailure(reason=ex)

        LOG.info(_("cascade ino: snapshot %s, created successfully"),
                 snapshot_ref['id'])
        self._notify_about_snapshot_usage(context, snapshot_ref, "create.end")

        return snapshot_id

    @locked_snapshot_operation
    def delete_snapshot(self, context, snapshot_id):
        """Deletes and unexports snapshot."""
        caller_context = context
        context = context.elevated()
        snapshot_ref = self.db.snapshot_get(context, snapshot_id)
        project_id = snapshot_ref['project_id']

        LOG.info(_("snapshot %s: deleting"), snapshot_ref['id'])
        self._notify_about_snapshot_usage(
            context, snapshot_ref, "delete.start")

        try:
            LOG.debug(_("snapshot %s: deleting"), snapshot_ref['id'])

            # Pass context so that drivers that want to use it, can,
            # but it is not a requirement for all drivers.
            snapshot_ref['context'] = caller_context

            self._delete_snapshot_cascaded(context, snapshot_id)
        except exception.SnapshotIsBusy:
            LOG.error(_("Cannot delete snapshot %s: snapshot is busy"),
                      snapshot_ref['id'])
            self.db.snapshot_update(context,
                                    snapshot_ref['id'],
                                    {'status': 'available'})
            return True
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.snapshot_update(context,
                                        snapshot_ref['id'],
                                        {'status': 'error_deleting'})

        # Get reservations
        try:
            if CONF.no_snapshot_gb_quota:
                reserve_opts = {'snapshots': -1}
            else:
                reserve_opts = {
                    'snapshots': -1,
                    'gigabytes': -snapshot_ref['volume_size'],
                }
            volume_ref = self.db.volume_get(context, snapshot_ref['volume_id'])
            QUOTAS.add_volume_type_opts(context,
                                        reserve_opts,
                                        volume_ref.get('volume_type_id'))
            reservations = QUOTAS.reserve(context,
                                          project_id=project_id,
                                          **reserve_opts)
        except Exception:
            reservations = None
            LOG.exception(_("Failed to update usages deleting snapshot"))
        self.db.volume_glance_metadata_delete_by_snapshot(context, snapshot_id)
        self.db.snapshot_destroy(context, snapshot_id)
        LOG.info(_("snapshot %s: deleted successfully"), snapshot_ref['id'])
        self._notify_about_snapshot_usage(context, snapshot_ref, "delete.end")

        # Commit the reservations
        if reservations:
            QUOTAS.commit(context, reservations, project_id=project_id)
        return True

    def _delete_snapshot_cascaded(self, context, snapshot_id):

        try:
            # snapshot_ref = self.db.snapshot_get(context, snapshot_id)
            # cascaded_snapshot_id = snapshot_ref['mapping_uuid']
            cascaded_snapshot_id = \
                self.volumes_mapping_cache['snapshots'].get(snapshot_id, '')
            LOG.info(_("cascade ino: delete cascaded snapshot:%s"),
                     cascaded_snapshot_id)

            cinderClient = self._get_cinder_cascaded_user_client(context)
            cinderClient.volume_snapshots.get(cascaded_snapshot_id)
            resp = cinderClient.volume_snapshots.delete(cascaded_snapshot_id)
            self.volumes_mapping_cache['snapshots'].pop(snapshot_id, '')
            LOG.info(_("delete cascaded snapshot %s successfully. resp :%s"),
                     cascaded_snapshot_id, resp)
            return
        except cinder_exception.NotFound:
            self.volumes_mapping_cache['snapshots'].pop(snapshot_id, '')
            LOG.info(_("delete cascaded snapshot %s successfully."),
                     cascaded_snapshot_id)
            return
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.snapshot_update(context,
                                        snapshot_id,
                                        {'status': 'error_deleting'})
                LOG.error(_("failed to delete cascaded snapshot %s"),
                          cascaded_snapshot_id)

    def attach_volume(self, context, volume_id, instance_uuid, host_name,
                      mountpoint, mode):
        """Updates db to show volume is attached
           interface about attch_volume has been realized in nova-proxy
           cinder-proxy just update cascading level data, other fields
           about attaching is synced from timer (_heal_volume_status)
        """
        @utils.synchronized(volume_id, external=True)
        def do_attach():
            # check the volume status before attaching
            volume = self.db.volume_get(context, volume_id)
            volume_metadata = self.db.volume_admin_metadata_get(
                context.elevated(), volume_id)
            if volume['status'] == 'attaching':
                if (volume['instance_uuid'] and volume['instance_uuid'] !=
                        instance_uuid):
                    msg = _("being attached by another instance")
                    raise exception.InvalidVolume(reason=msg)
                if (volume['attached_host'] and volume['attached_host'] !=
                        host_name):
                    msg = _("being attached by another host")
                    raise exception.InvalidVolume(reason=msg)
                if (volume_metadata.get('attached_mode') and
                        volume_metadata.get('attached_mode') != mode):
                    msg = _("being attached by different mode")
                    raise exception.InvalidVolume(reason=msg)
            elif volume['status'] != "available":
                msg = _("status must be available")
                raise exception.InvalidVolume(reason=msg)
            # TODO(jdg): attach_time column is currently varchar
            # we should update this to a date-time object
            # also consider adding detach_time?
            self._notify_about_volume_usage(context, volume,
                                            "attach.start")
            host_name_sanitized = None
            if instance_uuid is not None:
                if uuidutils.is_uuid_like(instance_uuid):
                    self.db.volume_update(context, volume_id,
                                          {"instance_uuid": instance_uuid,
                                           "mountpoint": mountpoint
                                           })
                    LOG.debug(_('Cascade info: attach volume, db, vm_uuid %s,'
                                'mountpoint:%s'), instance_uuid, mountpoint)
                else:
                    self.db.volume_update(context, volume_id,
                                          {'status': 'error_attaching'})
                    raise exception.InvalidUUID(uuid=instance_uuid)
            elif host_name is not None:
                self.db.volume_update(context, volume_id,
                                      {"attached_host": host_name,
                                       "mountpoint": mountpoint,
                                       })
                LOG.debug(_('Cascade info: attach volume, db, host_name %s,'
                            'mountpoint:%s'), host_name, mountpoint)
                host_name_sanitized = utils.sanitize_hostname(host_name)
            self.db.volume_admin_metadata_update(context.elevated(),
                                                 volume_id,
                                                 {"attached_mode": mode},
                                                 False)
            volume = self.db.volume_attached(context.elevated(),
                                             volume_id,
                                             instance_uuid,
                                             host_name_sanitized,
                                             mountpoint)
            if volume['migration_status']:
                self.db.volume_update(context, volume_id,
                                      {'migration_status': None})
            self._notify_about_volume_usage(context, volume, "attach.end")
        return do_attach()

    @locked_volume_operation
    def detach_volume(self, context, volume_id):
        """Updates db to show volume is detached
           interface about detach_volume has been realized in nova-proxy
           cinder-proxy just update cascading level data, other fields
           about detaching is synced from timer (_heal_volume_status)
        """
        # TODO(vish): refactor this into a more general "unreserve"
        # TODO(sleepsonthefloor): Is this 'elevated' appropriate?
        # self.db.volume_detached(context.elevated(), volume_id)
        self.db.volume_admin_metadata_delete(context.elevated(), volume_id,
                                             'attached_mode')

    def copy_volume_to_image(self, context, volume_id, image_meta):
        """Uploads the specified volume to Glance.

        image_meta is a dictionary containing the following keys:
        'id', 'container_format', 'disk_format'

        """
        LOG.info(_("cascade ino: copy volume to image, image_meta is:%s"),
                 image_meta)
        # TODO: make force default as True for now, api should pass this
        # param down through context here (image_meta doesn't has this param)
        force = image_meta.get('force', True)
        image_name = image_meta.get("name")
        container_format = image_meta.get("container_format")
        disk_format = image_meta.get("disk_format")
        # vol_ref = self.db.volume_get(context, volume_id)
        # casecaded_volume_id = vol_ref['mapping_uuid']
        cascaded_volume_id = \
            self.volumes_mapping_cache['volumes'].get(volume_id, '')
        LOG.debug(_('cascade ino: cop vol to img, ccded vol id is %s'),
                  cascaded_volume_id)
        cinderClient = self._get_cinder_cascaded_user_client(context)

        resp = cinderClient.volumes.upload_to_image(
            volume=cascaded_volume_id,
            force=force,
            image_name=image_name,
            container_format=container_format,
            disk_format=disk_format)

        if cfg.CONF.glance_cascading_flag:
            cascaded_image_id = resp[1]['os-volume_upload_image']['image_id']
            LOG.debug(_('cascade ino:upload volume to image,get cascaded '
                        'image id is %s'), cascaded_image_id)
            url = '%s/v2/images/%s' % (cfg.CONF.cascaded_glance_url,
                                       cascaded_image_id)
            locations = [{
                         'url': url,
                         'metadata': {'image_id': str(cascaded_image_id),
                                      'image_from': 'volume'
                                      }
                         }]

            image_service, image_id = \
                glance.get_remote_image_service(context, image_meta['id'])
            LOG.debug(_("cascade ino: image service:%s"), image_service)

            netloc = cfg.CONF.cascading_glance_url
            header = 'http://'
            if header in cfg.CONF.cascading_glance_url:
                netloc = netloc[len(header):]

            glanceClient = glance.GlanceClientWrapper(
                context,
                netloc=netloc,
                use_ssl=False,
                version="2")
            glanceClient.call(context, 'update', image_id,
                              remove_props=None, locations=locations)
            LOG.debug(_('cascade ino:upload volume to image,finish update'
                        'image %s locations %s.'), (image_id, locations))

            volume = self.db.volume_get(context, volume_id)
            if (volume['instance_uuid'] is None and
                    volume['attached_host'] is None):
                self.db.volume_update(context, volume_id,
                                      {'status': 'available'})
            else:
                self.db.volume_update(context, volume_id,
                                      {'status': 'in-use'})

    def initialize_connection(self, context, volume_id, connector):
        """Prepare volume for connection from host represented by connector.
           volume in openstack cascading level is just a logical data,
           initialize connection has losts its meaning, so the interface here
           just return a None value
        """
        return None

    def terminate_connection(self, context, volume_id, connector, force=False):
        """Cleanup connection from host represented by connector.
           volume in openstack cascading level is just a logical data,
           terminate connection has losts its meaning, so the interface here
           just return a None value
        """
        return None

    @periodic_task.periodic_task
    def _report_driver_status(self, context):
        """cinder cascading driver has losts its meaning.
           so driver-report info here is just a copy of simulation message
        """
        LOG.info(_("report simulation volume driver"))
        simu_location_info = 'LVMVolumeDriver:Huawei:cinder-volumes:default:0'

        volume_backend_list = ['LVM_ISCSI']

        volume_stats = {
            'QoS_support': True,
            'free_capacity_gb': 10240.0,
            'location_info': simu_location_info,
            'total_capacity_gb': 10240.0,
            'reserved_percentage': 0,
            'driver_version': '2.0.0',
            'vendor_name': 'Huawei',
            'storage_protocol': 'iSCSI'}

        if CONF.enabled_volume_types:
            for voltype_name in CONF.enabled_volume_types:
                vol_type =\
                    self.db.volume_type_get_by_name(context, voltype_name)
                for key, value in vol_type['extra_specs'].iteritems():
                    LOG.debug("key %s, value %s", key, value)
                    if key == 'volume_backend_name' and \
                       value not in volume_backend_list:
                        volume_backend_list.append(value)
                    else:
                        continue

        LOG.info('cascade info: proxy support volume backends: %s !!!!',
                 volume_backend_list)
        for volume_backend in volume_backend_list:
            volume_stats['volume_backend_name'] = volume_backend
            self.update_service_capabilities(volume_stats)

    def publish_service_capabilities(self, context):
        """Collect driver status and then publish."""
        self._report_driver_status(context)
        self._publish_service_capabilities(context)

    def _reset_stats(self):
        LOG.info(_("Clear capabilities"))
        self._last_volume_stats = []

    def notification(self, context, event):
        LOG.info(_("Notification {%s} received"), event)
        self._reset_stats()

    def _notify_about_volume_usage(self,
                                   context,
                                   volume,
                                   event_suffix,
                                   extra_usage_info=None):
        volume_utils.notify_about_volume_usage(
            context, volume, event_suffix,
            extra_usage_info=extra_usage_info, host=self.host)

    def _notify_about_snapshot_usage(self,
                                     context,
                                     snapshot,
                                     event_suffix,
                                     extra_usage_info=None):
        volume_utils.notify_about_snapshot_usage(
            context, snapshot, event_suffix,
            extra_usage_info=extra_usage_info, host=self.host)

    def extend_volume(self, context, volume_id, new_size, reservations):
        volume = self.db.volume_get(context, volume_id)

        self._notify_about_volume_usage(context, volume, "resize.start")
        try:
            LOG.info(_("volume %s: extending"), volume['id'])

            cinderClient = self._get_cinder_cascaded_user_client(context)

            # vol_ref = self.db.volume_get(context, volume_id)
            # cascaded_volume_id = vol_ref['mapping_uuid']
            cascaded_volume_id = \
                self.volumes_mapping_cache['volumes'].get(volume_id, '')
            LOG.info(_("cascade ino: extend volume cascaded volume id is:%s"),
                     cascaded_volume_id)
            cinderClient.volumes.extend(cascaded_volume_id, new_size)
            LOG.info(_("cascade ino: volume %s: extended successfully"),
                     volume['id'])

        except Exception:
            LOG.exception(_("volume %s: Error trying to extend volume"),
                          volume_id)
            try:
                self.db.volume_update(context, volume['id'],
                                      {'status': 'error_extending'})
            finally:
                QUOTAS.rollback(context, reservations)
                return

        QUOTAS.commit(context, reservations)
        self.db.volume_update(context, volume['id'], {'size': int(new_size),
                                                      'status': 'extending'})
        self._notify_about_volume_usage(
            context, volume, "resize.end",
            extra_usage_info={'size': int(new_size)})

    def migrate_volume(self, ctxt, volume_id, host, force_host_copy=False):
        """Migrate the volume to the specified host (called on source host).
           the interface is being realized
        """
        return
