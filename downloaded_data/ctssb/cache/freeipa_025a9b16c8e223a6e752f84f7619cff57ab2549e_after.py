#
# Copyright (C) 2014  FreeIPA Contributors see COPYING for license
#

import logging
import ldap.dn
import os

from ipaplatform.paths import paths
from ipapython import ipautil

from ipapython.dnssec.syncrepl import SyncReplConsumer
from ipapython.dnssec.odsmgr import ODSMgr
from ipapython.dnssec.bindmgr import BINDMgr

SIGNING_ATTR = 'idnsSecInlineSigning'
OBJCLASS_ATTR = 'objectClass'


class KeySyncer(SyncReplConsumer):
    def __init__(self, *args, **kwargs):
        # hack
        self.api = kwargs['ipa_api']
        del kwargs['ipa_api']

        # DNSSEC master should have OpenDNSSEC installed
        # TODO: Is this the best way?
        if os.environ.get('ISMASTER', '0') == '1':
            self.ismaster = True
            self.odsmgr = ODSMgr()
        else:
            self.ismaster = False

        self.bindmgr = BINDMgr(self.api)
        self.init_done = False
        SyncReplConsumer.__init__(self, *args, **kwargs)

    def _get_objclass(self, attrs):
        """Get object class.

        Given set of attributes has to have exactly one supported object class.
        """
        supported_objclasses = set(['idnszone', 'idnsseckey', 'ipk11publickey'])
        present_objclasses = set([o.lower() for o in attrs[OBJCLASS_ATTR]]).intersection(supported_objclasses)
        assert len(present_objclasses) == 1, attrs[OBJCLASS_ATTR]
        return present_objclasses.pop()

    def __get_signing_attr(self, attrs):
        """Get SIGNING_ATTR from dictionary with LDAP zone attributes.

        Returned value is normalized to TRUE or FALSE, defaults to FALSE."""
        values = attrs.get(SIGNING_ATTR, ['FALSE'])
        assert len(values) == 1, '%s is expected to be single-valued' \
            % SIGNING_ATTR
        return values[0].upper()

    def __is_dnssec_enabled(self, attrs):
        """Test if LDAP DNS zone with given attributes is DNSSEC enabled."""
        return self.__get_signing_attr(attrs) == 'TRUE'

    def __is_replica_pubkey(self, attrs):
        vals = attrs.get('ipk11label', [])
        if len(vals) != 1:
            return False
        return vals[0].startswith('dnssec-replica:')

    def application_add(self, uuid, dn, newattrs):
        objclass = self._get_objclass(newattrs)
        if objclass == 'idnszone':
            self.zone_add(uuid, dn, newattrs)
        elif objclass == 'idnsseckey':
            self.key_meta_add(uuid, dn, newattrs)
        elif objclass == 'ipk11publickey' and \
                self.__is_replica_pubkey(newattrs):
            self.hsm_master_sync()

    def application_del(self, uuid, dn, oldattrs):
        objclass = self._get_objclass(oldattrs)
        if objclass == 'idnszone':
            self.zone_del(uuid, dn, oldattrs)
        elif objclass == 'idnsseckey':
            self.key_meta_del(uuid, dn, oldattrs)
        elif objclass == 'ipk11publickey' and \
                self.__is_replica_pubkey(oldattrs):
            self.hsm_master_sync()

    def application_sync(self, uuid, dn, newattrs, oldattrs):
        objclass = self._get_objclass(oldattrs)
        if objclass == 'idnszone':
            olddn = ldap.dn.str2dn(oldattrs['dn'])
            newdn = ldap.dn.str2dn(newattrs['dn'])
            assert olddn == newdn, 'modrdn operation is not supported'

            oldval = self.__get_signing_attr(oldattrs)
            newval = self.__get_signing_attr(newattrs)
            if oldval != newval:
                if self.__is_dnssec_enabled(newattrs):
                    self.zone_add(uuid, olddn, newattrs)
                else:
                    self.zone_del(uuid, olddn, oldattrs)

        elif objclass == 'idnsseckey':
            self.key_metadata_sync(uuid, dn, oldattrs, newattrs)

        elif objclass == 'ipk11publickey' and \
                self.__is_replica_pubkey(newattrs):
            self.hsm_master_sync()

    def syncrepl_refreshdone(self):
        self.log.info('Initial LDAP dump is done, sychronizing with ODS and BIND')
        self.init_done = True
        self.ods_sync()
        self.hsm_replica_sync()
        self.hsm_master_sync()
        self.bindmgr.sync()

    # idnsSecKey wrapper
    # Assumption: metadata points to the same key blob all the time,
    # i.e. it is not necessary to re-download blobs because of change in DNSSEC
    # metadata - DNSSEC flags or timestamps.
    def key_meta_add(self, uuid, dn, newattrs):
        self.hsm_replica_sync()
        self.bindmgr.ldap_event('add', uuid, newattrs)
        self.bindmgr_sync()

    def key_meta_del(self, uuid, dn, oldattrs):
        self.bindmgr.ldap_event('del', uuid, oldattrs)
        self.bindmgr_sync()
        self.hsm_replica_sync()

    def key_metadata_sync(self, uuid, dn, oldattrs, newattrs):
        self.bindmgr.ldap_event('mod', uuid, newattrs)
        self.bindmgr_sync()

    def bindmgr_sync(self):
        if self.init_done:
            self.bindmgr.sync()

    # idnsZone wrapper
    def zone_add(self, uuid, dn, newattrs):
        if not self.ismaster:
            return

        if self.__is_dnssec_enabled(newattrs):
            self.odsmgr.ldap_event('add', uuid, newattrs)
        self.ods_sync()

    def zone_del(self, uuid, dn, oldattrs):
        if not self.ismaster:
            return

        if self.__is_dnssec_enabled(oldattrs):
            self.odsmgr.ldap_event('del', uuid, oldattrs)
        self.ods_sync()

    def ods_sync(self):
        if not self.ismaster:
            return

        if self.init_done:
            self.odsmgr.sync()

    # triggered by modification to idnsSecKey objects
    def hsm_replica_sync(self):
        """Download keys from LDAP to local HSM."""
        if self.ismaster:
            return
        if not self.init_done:
            return
        ipautil.run([paths.IPA_DNSKEYSYNCD_REPLICA])

    # triggered by modification to ipk11PublicKey objects
    def hsm_master_sync(self):
        """Download replica keys from LDAP to local HSM
        & upload master and zone keys to LDAP."""
        if not self.ismaster:
            return
        if not self.init_done:
            return
        ipautil.run([paths.ODS_SIGNER, 'ipa-hsm-update'])
