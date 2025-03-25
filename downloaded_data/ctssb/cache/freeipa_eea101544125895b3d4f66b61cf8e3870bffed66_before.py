# Authors:
#   Martin Kosek <mkosek@redhat.com>
#
# Copyright (C) 2012  Red Hat
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import ldap as _ldap
import traceback
import time

from ldif import LDIFWriter

from ipaserver.install.plugins import MIDDLE, LAST
from ipaserver.install.plugins.baseupdate import (PostUpdate, PreUpdate,
                                                  PreSchemaUpdate)
from ipaserver.install import sysupgrade
from ipalib import api, errors, util
from ipapython.dn import DN
from ipalib.plugins.dns import dns_container_exists
from ipapython.ipa_log_manager import *


class update_dnszones(PostUpdate):
    """
    Update all zones to meet requirements in the new FreeIPA versions

    1) AllowQuery and AllowTransfer
    Set AllowQuery and AllowTransfer ACLs in all zones that may be configured
    in an upgraded FreeIPA instance.

    Upgrading to new version of bind-dyndb-ldap and having these ACLs empty
    would result in a leak of potentially sensitive DNS information as
    zone transfers are enabled for all hosts if not disabled in named.conf
    or LDAP.

    This plugin disables the zone transfer by default so that it needs to be
    explicitly enabled by FreeIPA Administrator.

    2) Update policy
    SSH public key support includes a feature to automatically add/update
    client SSH fingerprints in SSHFP records. However, the update won't
    work for zones created before this support was added as they don't allow
    clients to update SSHFP records in their update policies.

    This module extends the original policy to allow the SSHFP updates.
    """
    order=MIDDLE

    def execute(self, **options):
        ldap = self.obj.backend

        try:
            zones = api.Command.dnszone_find(all=True)['result']
        except errors.NotFound:
            self.log.info('No DNS zone to update found')
            return (False, False, [])

        for zone in zones:
            update = {}
            if not zone.get('idnsallowquery'):
                # allow query from any client by default
                update['idnsallowquery'] = u'any;'

            if not zone.get('idnsallowtransfer'):
                # do not open zone transfers by default
                update['idnsallowtransfer'] = u'none;'

            old_policy = util.get_dns_forward_zone_update_policy(api.env.realm, ('A', 'AAAA'))
            if zone.get('idnsupdatepolicy', [''])[0] == old_policy:
                update['idnsupdatepolicy'] = util.get_dns_forward_zone_update_policy(\
                        api.env.realm)

            if update:
                api.Command.dnszone_mod(zone[u'idnsname'][0], **update)

        return (False, False, [])

api.register(update_dnszones)


class update_dns_limits(PostUpdate):
    """
    bind-dyndb-ldap persistent search queries LDAP for all DNS records.
    The LDAP connection must have no size or time limits to work
    properly. This plugin updates limits of the existing DNS service
    principal to match there requirements.
    """
    limit_attributes = ['nsTimeLimit', 'nsSizeLimit', 'nsIdleTimeout', 'nsLookThroughLimit']
    limit_value = '-1'

    def execute(self, **options):
        ldap = self.obj.backend

        if not dns_container_exists(ldap):
            return (False, False, [])

        dns_principal = 'DNS/%s@%s' % (self.env.host, self.env.realm)
        dns_service_dn = DN(('krbprincipalname', dns_principal),
                            self.env.container_service,
                            self.env.basedn)

        try:
            entry = ldap.get_entry(dns_service_dn, self.limit_attributes)
        except errors.NotFound:
            # this host may not have DNS service set
            root_logger.debug("DNS: service %s not found, no need to update limits" % dns_service_dn)
            return (False, False, [])

        if all(entry.get(limit.lower(), [None])[0] == self.limit_value for limit in self.limit_attributes):
            root_logger.debug("DNS: limits for service %s already set" % dns_service_dn)
            # service is already updated
            return (False, False, [])

        limit_updates = []

        for limit in self.limit_attributes:
            limit_updates.append('only:%s:%s' % (limit, self.limit_value))

        dnsupdates = {}
        dnsupdates[dns_service_dn] = {'dn': dns_service_dn,
                                      'updates': limit_updates}
        root_logger.debug("DNS: limits for service %s will be updated" % dns_service_dn)


        return (False, True, [dnsupdates])

api.register(update_dns_limits)


class update_check_forwardzones(PreSchemaUpdate):
    """
    Check if the idnsforwardzone objectclass is in LDAP schema.
    If not update is required (update_to_forward_zones), set sysupgrade state
    'update_to_forward_zones' to True
    """

    def execute(self, **options):
        state = sysupgrade.get_upgrade_state('dns', 'update_to_forward_zones')
        if state is False:
            # no upgrade is needed
            return (False, False, [])
        ldap = self.obj.backend
        result = ldap.schema.get_obj(_ldap.schema.models.ObjectClass, 'idnsforwardzone')
        if result is None:
            sysupgrade.set_upgrade_state('dns', 'update_to_forward_zones', True)
            self.log.info('Prepared upgrade to forward zones')
        else:
            sysupgrade.set_upgrade_state('dns', 'update_to_forward_zones', False)
        return (False, False, [])

api.register(update_check_forwardzones)


class update_master_to_dnsforwardzones(PostUpdate):
    """
    Update all zones to meet requirements in the new FreeIPA versions

    All masters zones with specified forwarders, and forward-policy different
    than none, will be tranformed to forward zones.
    Original masters zone will be backed up to ldif file.

    This should be applied only once, and only if original version was lower than 4.0
    """
    order = LAST

    backup_dir = u'/var/lib/ipa/backup/'
    backup_filename = u'dns-forward-zones-backup-%Y-%m-%d-%H-%M-%S.ldif'
    backup_path = u'%s%s' % (backup_dir, backup_filename)

    def execute(self, **options):
        ldap = self.obj.backend
        if not sysupgrade.get_upgrade_state('dns', 'update_to_forward_zones'):
            # forward zones was tranformed before, nothing to do
            return (False, False, [])

        try:
            # raw values are required to store into ldif
            zones = api.Command.dnszone_find(all=True,
                                             raw=True,
                                             sizelimit=0)['result']
        except errors.NotFound:
            self.log.info('No DNS zone to update found')
            return (False, False, [])

        zones_to_transform = []

        for zone in zones:
            if (
                zone.get('idnsforwardpolicy', [u'first'])[0] == u'none' or
                zone.get('idnsforwarders', []) == []
            ):
                continue  # don't update zone

            zones_to_transform.append(zone)

        if zones_to_transform:
            # add time to filename
            self.backup_path = time.strftime(self.backup_path)

            self.log.info('Zones with specified forwarders with policy different'
                          ' than none will be transformed to forward zones.')
            self.log.info('Original zones will be saved in LDIF format in '
                          '%s file' % self.backup_path)
            try:

                with open(self.backup_path, 'w') as f:
                    writer = LDIFWriter(f)
                    for zone in zones_to_transform:
                        # save backup to ldif
                        try:

                            dn = str(zone['dn'])
                            del zone['dn']  # dn shouldn't be as attribute in ldif
                            writer.unparse(dn, zone)

                            if 'managedBy' in zone:
                                entry = ldap.get_entry(DN(zone['managedBy'][0]))
                                writer.unparse(str(entry.dn), dict(entry))

                            # raw values are required to store into ldif
                            records = api.Command['dnsrecord_find'](
                                        zone['idnsname'][0],
                                        all=True,
                                        raw=True,
                                        sizelimit=0)['result']
                            for record in records:
                                if record['idnsname'][0] == u'@':
                                    # zone record was saved before
                                    continue
                                dn = str(record['dn'])
                                del record['dn']
                                writer.unparse(dn, record)

                        except Exception, e:
                            self.log.error('Unable to backup zone %s' %
                                           zone['idnsname'][0])
                            self.log.error(traceback.format_exc())
                            return (False, False, [])
                    f.close()
            except Exception:
                self.log.error('Unable to create backup file')
                self.log.error(traceback.format_exc())
                return (False, False, [])

            # update
            for zone in zones_to_transform:
                # delete master zone
                try:
                    api.Command['dnszone_del'](zone['idnsname'])
                except Exception, e:
                    self.log.error('Transform to forwardzone terminated: '
                                   'removing zone %s failed (%s)' % (
                                       zone['idnsname'][0], e)
                                  )
                    self.log.error(traceback.format_exc())
                    continue

                # create forward zone
                try:
                    kw = {
                        'idnsforwarders': zone.get('idnsforwarders', []),
                        'idnsforwardpolicy': zone.get('idnsforwardpolicy', [u'first'])[0]
                    }
                    api.Command['dnsforwardzone_add'](zone['idnsname'][0], **kw)
                except Exception, e:
                    self.log.error('Transform to forwardzone terminated: creating '
                                   'forwardzone %s failed' %
                                   zone['idnsname'][0])
                    self.log.error(traceback.format_exc())
                    continue

                # create permission if original zone has one
                if 'managedBy' in zone:
                    try:
                        api.Command['dnsforwardzone_add_permission'](zone['idnsname'][0])
                    except Exception, e:
                        self.log.error('Transform to forwardzone terminated: '
                                       'Adding managed by permission to forward zone'
                                       ' %s failed' % zone['idnsname'])
                        self.log.error(traceback.format_exc())
                        self.log.info('Zone %s was transformed to forward zone '
                                      ' without managed permissions',
                                      zone['idnsname'][0])
                        continue

                self.log.info('Zone %s was sucessfully transformed to forward zone',
                              zone['idnsname'][0])

        sysupgrade.set_upgrade_state('dns', 'update_to_forward_zones', False)

        return (False, False, [])

api.register(update_master_to_dnsforwardzones)
