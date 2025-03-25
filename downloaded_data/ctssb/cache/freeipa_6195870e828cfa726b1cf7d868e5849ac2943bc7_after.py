# Authors:
#     Alexander Bokovoy <abokovoy@redhat.com>
#
# Copyright (C) 2011  Red Hat
# see file 'COPYING' for use and warranty information
#
# Portions (C) Andrew Tridgell, Andrew Bartlett
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

# Make sure we only run this module at the server where samba4-python
# package is installed to avoid issues with unavailable modules

from ipalib.plugins.baseldap import *
from ipalib import api, Str, Password, DefaultFrom, _, ngettext, Object
from ipalib.parameters import Enum
from ipalib import Command
from ipalib import errors
from ipapython import ipautil
from ipapython.ipa_log_manager import *
from ipapython.dn import DN
from ipaserver.install import installutils
from ipaserver.plugins import ldap2
from ipalib.util import normalize_name

import os, string, struct, copy
import uuid
from samba import param
from samba import credentials
from samba.dcerpc import security, lsa, drsblobs, nbt, netlogon
from samba.ndr import ndr_pack, ndr_print
from samba import net
import samba
import random
from M2Crypto import RC4
try:
    from ldap.controls import RequestControl as LDAPControl #pylint: disable=F0401
except ImportError:
    from ldap.controls import LDAPControl as LDAPControl    #pylint: disable=F0401
import ldap as _ldap
from ipapython.ipaldap import IPAdmin
from ipalib.session import krbccache_dir, krbccache_prefix
from dns import resolver, rdatatype
from dns.exception import DNSException
import pysss_nss_idmap
import pysss

__doc__ = _("""
Classes to manage trust joins using DCE-RPC calls

The code in this module relies heavily on samba4-python package
and Samba4 python bindings.
""")


def is_sid_valid(sid):
    try:
        security.dom_sid(sid)
    except TypeError:
        return False
    else:
        return True


access_denied_error =  errors.ACIError(info=_('CIFS server denied your credentials'))
dcerpc_error_codes = {
    -1073741823:
        errors.RemoteRetrieveError(reason=_('communication with CIFS server was unsuccessful')),
    -1073741790: access_denied_error,
    -1073741715: access_denied_error,
    -1073741614: access_denied_error,
    -1073741603:
        errors.ValidationError(name=_('AD domain controller'), error=_('unsupported functional level')),
    -1073741811: # NT_STATUS_INVALID_PARAMETER
        errors.RemoteRetrieveError(
            reason=_('AD domain controller complains about communication sequence. It may mean unsynchronized time on both sides, for example')),
}

dcerpc_error_messages = {
    "NT_STATUS_OBJECT_NAME_NOT_FOUND":
         errors.NotFound(reason=_('Cannot find specified domain or server name')),
    "NT_STATUS_INVALID_PARAMETER_MIX":
         errors.RequirementError(name=_('At least the domain or IP address should be specified')),
}

def assess_dcerpc_exception(num=None,message=None):
    """
    Takes error returned by Samba bindings and converts it into
    an IPA error class.
    """
    if num and num in dcerpc_error_codes:
        return dcerpc_error_codes[num]
    if message and message in dcerpc_error_messages:
        return dcerpc_error_messages[message]
    reason = _('''CIFS server communication error: code "%(num)s",
                  message "%(message)s" (both may be "None")''') % dict(num=num, message=message)
    return errors.RemoteRetrieveError(reason=reason)

class ExtendedDNControl(LDAPControl):
    # This class attempts to implement LDAP control that would work
    # with both python-ldap 2.4.x and 2.3.x, thus there is mix of properties
    # from both worlds and encodeControlValue has default parameter
    def __init__(self):
        self.controlValue = 1
        self.controlType = "1.2.840.113556.1.4.529"
        self.criticality = False
        self.integerValue = 1

    def encodeControlValue(self, value=None):
        return '0\x03\x02\x01\x01'


class DomainValidator(object):
    ATTR_FLATNAME = 'ipantflatname'
    ATTR_SID = 'ipantsecurityidentifier'
    ATTR_TRUSTED_SID = 'ipanttrusteddomainsid'
    ATTR_TRUST_PARTNER = 'ipanttrustpartner'
    ATTR_TRUST_AUTHOUT = 'ipanttrustauthoutgoing'

    def __init__(self, api):
        self.api = api
        self.ldap = self.api.Backend.ldap2
        self.domain = None
        self.flatname = None
        self.dn = None
        self.sid = None
        self._domains = None
        self._info = dict()
        self._creds = None
        self._parm = None

    def is_configured(self):
        cn_trust_local = DN(('cn', self.api.env.domain), self.api.env.container_cifsdomains, self.api.env.basedn)
        try:
            entry_attrs = self.ldap.get_entry(cn_trust_local, [self.ATTR_FLATNAME, self.ATTR_SID])
            self.flatname = entry_attrs[self.ATTR_FLATNAME][0]
            self.sid = entry_attrs[self.ATTR_SID][0]
            self.dn = entry_attrs.dn
            self.domain = self.api.env.domain
        except errors.NotFound, e:
            return False
        return True

    def get_trusted_domains(self):
        """
        Returns case-insensitive dict of trusted domain tuples
        (flatname, sid, trust_auth_outgoing), keyed by domain name.
        """
        cn_trust = DN(('cn', 'ad'), self.api.env.container_trusts,
                      self.api.env.basedn)

        try:
            search_kw = {'objectClass': 'ipaNTTrustedDomain'}
            filter = self.ldap.make_filter(search_kw, rules=self.ldap.MATCH_ALL)
            (entries, truncated) = self.ldap.find_entries(
                filter=filter,
                base_dn=cn_trust,
                attrs_list=[self.ATTR_TRUSTED_SID,
                            self.ATTR_FLATNAME,
                            self.ATTR_TRUST_PARTNER]
                )

            # We need to use case-insensitive dictionary since we use
            # domain names as keys and those are generally case-insensitive
            result = ipautil.CIDict()

            for entry in entries:
                try:
                    trust_partner = entry[self.ATTR_TRUST_PARTNER][0]
                    flatname_normalized = entry[self.ATTR_FLATNAME][0].lower()
                    trusted_sid = entry[self.ATTR_TRUSTED_SID][0]
                except KeyError, e:
                    # Some piece of trusted domain info in LDAP is missing
                    # Skip the domain, but leave log entry for investigation
                    api.log.warn("Trusted domain '%s' entry misses an "
                                 "attribute: %s", entry.dn, e)
                    continue

                result[trust_partner] = (flatname_normalized,
                                         security.dom_sid(trusted_sid))
            return result
        except errors.NotFound, e:
            return []

    def set_trusted_domains(self):
        # At this point we have SID_NT_AUTHORITY family SID and really need to
        # check it against prefixes of domain SIDs we trust to
        if not self._domains:
            self._domains = self.get_trusted_domains()
        if len(self._domains) == 0:
            # Our domain is configured but no trusted domains are configured
            # This means we can't check the correctness of a trusted
            # domain SIDs
            raise errors.ValidationError(name='sid',
                  error=_('no trusted domain is configured'))

    def get_domain_by_sid(self, sid, exact_match=False):
        if not self.domain:
            # our domain is not configured or self.is_configured() never run
            # reject SIDs as we can't check correctness of them
            raise errors.ValidationError(name='sid',
                  error=_('domain is not configured'))

        # Parse sid string to see if it is really in a SID format
        try:
            test_sid = security.dom_sid(sid)
        except TypeError:
            raise errors.ValidationError(name='sid',
                  error=_('SID is not valid'))

        # At this point we have SID_NT_AUTHORITY family SID and really need to
        # check it against prefixes of domain SIDs we trust to
        self.set_trusted_domains()

        # We have non-zero list of trusted domains and have to go through
        # them one by one and check their sids as prefixes / exact match
        # depending on the value of exact_match flag
        if exact_match:
            # check exact match of sids
            for domain in self._domains:
                if sid == str(self._domains[domain][1]):
                    return domain

            raise errors.NotFound(reason=_("SID does not match exactly"
                                           "with any trusted domain's SID"))
        else:
            # check as prefixes
            test_sid_subauths = test_sid.sub_auths
            for domain in self._domains:
                domsid = self._domains[domain][1]
                sub_auths = domsid.sub_auths
                num_auths = min(test_sid.num_auths, domsid.num_auths)
                if test_sid_subauths[:num_auths] == sub_auths[:num_auths]:
                    return domain
            raise errors.NotFound(reason=_('SID does not match any '
                                           'trusted domain'))

    def is_trusted_sid_valid(self, sid):
        try:
            self.get_domain_by_sid(sid)
        except (errors.ValidationError, errors.NotFound):
            return False
        else:
            return True

    def is_trusted_domain_sid_valid(self, sid):
        try:
            self.get_domain_by_sid(sid, exact_match=True)
        except (errors.ValidationError, errors.NotFound):
            return False
        else:
            return True

    def get_sid_from_domain_name(self, name):
        """Returns binary representation of SID for the trusted domain name
           or None if name is not in the list of trusted domains."""

        domains = self.get_trusted_domains()
        if name in domains:
            return domains[name][1]
        else:
            return None

    def get_trusted_domain_objects(self, domain=None, flatname=None, filter="",
            attrs=None, scope=_ldap.SCOPE_SUBTREE, basedn=None):
        """
        Search for LDAP objects in a trusted domain specified either by `domain'
        or `flatname'. The actual LDAP search is specified by `filter', `attrs',
        `scope' and `basedn'. When `basedn' is empty, database root DN is used.
        """
        assert domain is not None or flatname is not None
        """Returns SID for the trusted domain object (user or group only)"""
        if not self.domain:
            # our domain is not configured or self.is_configured() never run
            raise errors.ValidationError(name=_('Trust setup'),
                error=_('Our domain is not configured'))
        if not self._domains:
            self._domains = self.get_trusted_domains()
        if len(self._domains) == 0:
            # Our domain is configured but no trusted domains are configured
            raise errors.ValidationError(name=_('Trust setup'),
                error=_('No trusted domain is not configured'))

        entries = None
        if domain is not None:
            if domain not in self._domains:
                raise errors.ValidationError(name=_('trusted domain object'),
                   error= _('domain is not trusted'))
            # Now we have a name to check against our list of trusted domains
            entries = self.search_in_dc(domain, filter, attrs, scope, basedn)
        elif flatname is not None:
            # Flatname was specified, traverse through the list of trusted
            # domains first to find the proper one
            found_flatname = False
            for domain in self._domains:
                if self._domains[domain][0] == flatname:
                    found_flatname = True
                    entries = self.search_in_dc(domain, filter, attrs, scope, basedn)
                    if entries:
                        break
            if not found_flatname:
                raise errors.ValidationError(name=_('trusted domain object'),
                        error= _('no trusted domain matched the specified flat name'))
        if not entries:
            raise errors.NotFound(reason=_('trusted domain object not found'))

        return entries

    def get_trusted_domain_object_sid(self, object_name):
        result = pysss_nss_idmap.getsidbyname(object_name)
        if object_name in result and (pysss_nss_idmap.SID_KEY in result[object_name]):
            object_sid = result[object_name][pysss_nss_idmap.SID_KEY]
            return object_sid

        # Else, we are going to contact AD DC LDAP
        components = normalize_name(object_name)
        if not ('domain' in components or 'flatname' in components):
            # No domain or realm specified, ambiguous search
             raise errors.ValidationError(name=_('trusted domain object'),
                   error= _('Ambiguous search, user domain was not specified'))

        attrs = ['objectSid']
        filter = '(&(sAMAccountName=%(name)s)(|(objectClass=user)(objectClass=group)))' \
                % dict(name=components['name'])
        scope = _ldap.SCOPE_SUBTREE
        entries = self.get_trusted_domain_objects(components.get('domain'),
                components.get('flatname'), filter, attrs, scope)

        if len(entries) > 1:
            # Treat non-unique entries as invalid
            raise errors.ValidationError(name=_('trusted domain object'),
               error= _('Trusted domain did not return a unique object'))
        sid = self.__sid_to_str(entries[0]['objectSid'][0])
        try:
            test_sid = security.dom_sid(sid)
            return unicode(test_sid)
        except TypeError, e:
            raise errors.ValidationError(name=_('trusted domain object'),
               error= _('Trusted domain did not return a valid SID for the object'))

    def __get_trusted_domain_user_and_groups(self, object_name):
        """
        Returns a tuple with user SID and a list of SIDs of all groups he is
        a member of.

        LIMITATIONS:
            - only Trusted Admins group members can use this function as it
              uses secret for IPA-Trusted domain link
            - List of group SIDs does not contain group memberships outside
              of the trusted domain
        """
        components = normalize_name(object_name)
        domain = components.get('domain')
        flatname = components.get('flatname')
        name = components.get('name')

        is_valid_sid = is_sid_valid(object_name)
        if is_valid_sid:
            # Find a trusted domain for the SID
            domain = self.get_domain_by_sid(object_name)
            # Now search a trusted domain for a user with this SID
            attrs = ['cn']
            filter = '(&(objectClass=user)(objectSid=%(sid)s))' \
                    % dict(sid=object_name)
            try:
                entries = self.get_trusted_domain_objects(domain=domain, filter=filter,
                        attrs=attrs, scope=_ldap.SCOPE_SUBTREE)
            except errors.NotFound:
                raise errors.NotFound(reason=_('trusted domain user not found'))
            user_dn = entries[0].dn
        elif domain or flatname:
            attrs = ['cn']
            filter = '(&(sAMAccountName=%(name)s)(objectClass=user))' \
                    % dict(name=name)
            try:
                entries = self.get_trusted_domain_objects(domain,
                        flatname, filter, attrs, _ldap.SCOPE_SUBTREE)
            except errors.NotFound:
                raise errors.NotFound(reason=_('trusted domain user not found'))
            user_dn = entries[0].dn
        else:
            # No domain or realm specified, ambiguous search
            raise errors.ValidationError(name=_('trusted domain object'),
                   error= _('Ambiguous search, user domain was not specified'))

        # Get SIDs of user object and it's groups
        # tokenGroups attribute must be read with a scope BASE for a known user
        # distinguished name to avoid search error
        attrs = ['objectSID', 'tokenGroups']
        filter = "(objectClass=user)"
        entries = self.get_trusted_domain_objects(domain,
            flatname, filter, attrs, _ldap.SCOPE_BASE, user_dn)
        object_sid = self.__sid_to_str(entries[0]['objectSid'][0])
        group_sids = [self.__sid_to_str(sid) for sid in entries[0]['tokenGroups']]
        return (object_sid, group_sids)

    def get_trusted_domain_user_and_groups(self, object_name):
        """
        Returns a tuple with user SID and a list of SIDs of all groups he is
        a member of.

        First attempts to perform SID lookup via SSSD and in case of failure
        resorts back to checking trusted domain's AD DC LDAP directly.

        LIMITATIONS:
            - only Trusted Admins group members can use this function as it
              uses secret for IPA-Trusted domain link if SSSD lookup failed
            - List of group SIDs does not contain group memberships outside
              of the trusted domain
        """
        group_sids = None
        group_list = None
        object_sid = None
        is_valid_sid = is_sid_valid(object_name)
        if is_valid_sid:
            object_sid = object_name
            result = pysss_nss_idmap.getnamebysid(object_name)
            if object_name in result and (pysss_nss_idmap.NAME_KEY in result[object_name]):
                group_list = pysss.getgrouplist(result[object_name][pysss_nss_idmap.NAME_KEY])
        else:
            result = pysss_nss_idmap.getsidbyname(object_name)
            if object_name in result and (pysss_nss_idmap.SID_KEY in result[object_name]):
                object_sid = result[object_name][pysss_nss_idmap.SID_KEY]
                group_list = pysss.getgrouplist(object_name)

        if not group_list:
            return self.__get_trusted_domain_user_and_groups(object_name)

        group_sids = pysss_nss_idmap.getsidbyname(group_list)
        return (object_sid, [el[1][pysss_nss_idmap.SID_KEY] for el in group_sids.items()])

    def __sid_to_str(self, sid):
        """
        Converts binary SID to string representation
        Returns unicode string
        """
        sid_rev_num = ord(sid[0])
        number_sub_id = ord(sid[1])
        ia = struct.unpack('!Q','\x00\x00'+sid[2:8])[0]
        subs = [
            struct.unpack('<I',sid[8+4*i:12+4*i])[0]
            for i in range(number_sub_id)
        ]
        return u'S-%d-%d-%s' % ( sid_rev_num, ia, '-'.join([str(s) for s in subs]),)

    def kinit_as_http(self, domain):
        """
        Initializes ccache with http service credentials.

        Applies session code defaults for ccache directory and naming prefix.
        Session code uses krbccache_prefix+<pid>, we use
        krbccache_prefix+<TD>+<domain netbios name> so there is no clash.

        Returns tuple (ccache path, principal) where (None, None) signifes an
        error on ccache initialization
        """

        domain_suffix = domain.replace('.', '-')

        ccache_name = "%sTD%s" % (krbccache_prefix, domain_suffix)
        ccache_path = os.path.join(krbccache_dir, ccache_name)

        realm = api.env.realm
        hostname = api.env.host
        principal = 'HTTP/%s@%s' % (hostname, realm)
        keytab = '/etc/httpd/conf/ipa.keytab'

        # Destroy the contents of the ccache
        root_logger.debug('Destroying the contents of the separate ccache')

        (stdout, stderr, returncode) = ipautil.run(
            ['/usr/bin/kdestroy', '-A', '-c', ccache_path],
            env={'KRB5CCNAME': ccache_path},
            raiseonerr=False)

        # Destroy the contents of the ccache
        root_logger.debug('Running kinit from ipa.keytab to obtain HTTP '
                          'service principal with MS-PAC attached.')

        (stdout, stderr, returncode) = ipautil.run(
            ['/usr/bin/kinit', '-kt', keytab, principal],
            env={'KRB5CCNAME': ccache_path},
            raiseonerr=False)

        if returncode == 0:
            return (ccache_path, principal)
        else:
            return (None, None)

    def search_in_dc(self, domain, filter, attrs, scope, basedn=None,
                     quiet=False):
        """
        Perform LDAP search in a trusted domain `domain' Domain Controller.
        Returns resulting entries or None.
        """

        entries = None

        info = self.__retrieve_trusted_domain_gc_list(domain)

        if not info:
            raise errors.ValidationError(
                name=_('Trust setup'),
                error=_('Cannot retrieve trusted domain GC list'))

        for (host, port) in info['gc']:
            entries = self.__search_in_dc(info, host, port, filter, attrs,
                                          scope, basedn=basedn,
                                          quiet=quiet)
            if entries:
                break

        return entries

    def __search_in_dc(self, info, host, port, filter, attrs, scope,
                       basedn=None, quiet=False):
        """
        Actual search in AD LDAP server, using SASL GSSAPI authentication
        Returns LDAP result or None.
        """

        (ccache_name, principal) = self.kinit_as_http(info['dns_domain'])

        if ccache_name:
            with installutils.private_ccache(path=ccache_name):
                entries = None

                try:
                    conn = IPAdmin(host=host,
                                   port=389,  # query the AD DC
                                   no_schema=True,
                                   decode_attrs=False,
                                   sasl_nocanon=True)
                    # sasl_nocanon used to avoid hard requirement for PTR
                    # records pointing back to the same host name

                    conn.do_sasl_gssapi_bind()

                    if basedn is None:
                        # Use domain root base DN
                        basedn = ipautil.realm_to_suffix(info['dns_domain'])

                    entries = conn.get_entries(basedn, scope, filter, attrs)
                except Exception, e:
                    msg = "Search on AD DC {host}:{port} failed with: {err}"\
                          .format(host=host, port=str(port), err=str(e))
                    if quiet:
                        root_logger.debug(msg)
                    else:
                        root_logger.warning(msg)
                finally:
                    return entries

    def __retrieve_trusted_domain_gc_list(self, domain):
        """
        Retrieves domain information and preferred GC list
        Returns dictionary with following keys
             name       -- NetBIOS name of the trusted domain
             dns_domain -- DNS name of the trusted domain
             gc         -- array of tuples (server, port) for Global Catalog
        """
        if domain in self._info:
            return self._info[domain]

        if not self._creds:
            self._parm = param.LoadParm()
            self._parm.load(os.path.join(ipautil.SHARE_DIR,"smb.conf.empty"))
            self._parm.set('netbios name', self.flatname)
            self._creds = credentials.Credentials()
            self._creds.set_kerberos_state(credentials.MUST_USE_KERBEROS)
            self._creds.guess(self._parm)
            self._creds.set_workstation(self.flatname)

        netrc = net.Net(creds=self._creds, lp=self._parm)
        finddc_error = None
        result = None
        try:
            result = netrc.finddc(domain=domain, flags=nbt.NBT_SERVER_LDAP | nbt.NBT_SERVER_GC | nbt.NBT_SERVER_CLOSEST)
        except RuntimeError, e:
            finddc_error = e

        if not self._domains:
            self._domains = self.get_trusted_domains()

        info = dict()
        servers = []

        if result:
            info['name'] = unicode(result.domain_name)
            info['dns_domain'] = unicode(result.dns_domain)
            servers = [(unicode(result.pdc_dns_name), 3268)]
        else:
            info['name'] = self._domains[domain]
            info['dns_domain'] = domain
            # Retrieve GC servers list
            gc_name = '_gc._tcp.%s.' % info['dns_domain']

            try:
                answers = resolver.query(gc_name, rdatatype.SRV)
            except DNSException, e:
                answers = []

            for answer in answers:
                server = str(answer.target).rstrip(".")
                servers.append((server, answer.port))

        info['gc'] = servers

        # Both methods should not fail at the same time
        if finddc_error and len(info['gc']) == 0:
            raise assess_dcerpc_exception(message=str(finddc_error))

        self._info[domain] = info
        return info

def string_to_array(what):
    blob = [0] * len(what)

    for i in range(len(what)):
        blob[i] = ord(what[i])
    return blob

class TrustDomainInstance(object):

    def __init__(self, hostname, creds=None):
        self.parm = param.LoadParm()
        self.parm.load(os.path.join(ipautil.SHARE_DIR,"smb.conf.empty"))
        if len(hostname) > 0:
            self.parm.set('netbios name', hostname)
        self.creds = creds
        self.hostname = hostname
        self.info = {}
        self._pipe = None
        self._policy_handle = None
        self.read_only = False
        self.ftinfo_records = None

    def __gen_lsa_connection(self, binding):
       if self.creds is None:
           raise errors.RequirementError(name=_('CIFS credentials object'))
       try:
           result = lsa.lsarpc(binding, self.parm, self.creds)
           return result
       except RuntimeError, (num, message):
           raise assess_dcerpc_exception(num=num, message=message)

    def init_lsa_pipe(self, remote_host):
        """
        Try to initialize connection to the LSA pipe at remote host.
        This method tries consequently all possible transport options
        and selects one that works. See __gen_lsa_bindings() for details.

        The actual result may depend on details of existing credentials.
        For example, using signing causes NO_SESSION_KEY with Win2K8 and
        using kerberos against Samba with signing does not work.
        """
        # short-cut: if LSA pipe is initialized, skip completely
        if self._pipe:
            return

        attempts = 0
        bindings = self.__gen_lsa_bindings(remote_host)
        for binding in bindings:
            try:
                self._pipe = self.__gen_lsa_connection(binding)
                if self._pipe:
                    break
            except errors.ACIError, e:
                attempts = attempts + 1

        if self._pipe is None and attempts == len(bindings):
            raise errors.ACIError(
                info=_('CIFS server %(host)s denied your credentials') % dict(host=remote_host))

        if self._pipe is None:
            raise errors.RemoteRetrieveError(
                reason=_('Cannot establish LSA connection to %(host)s. Is CIFS server running?') % dict(host=remote_host))
        self.binding = binding

    def __gen_lsa_bindings(self, remote_host):
        """
        There are multiple transports to issue LSA calls. However, depending on a
        system in use they may be blocked by local operating system policies.
        Generate all we can use. init_lsa_pipe() will try them one by one until
        there is one working.

        We try NCACN_NP before NCACN_IP_TCP and signed sessions before unsigned.
        """
        transports = (u'ncacn_np', u'ncacn_ip_tcp')
        options = ( u',', u'')
        binding_template=lambda x,y,z: u'%s:%s[%s]' % (x, y, z)
        return [binding_template(t, remote_host, o) for t in transports for o in options]

    def retrieve_anonymously(self, remote_host, discover_srv=False):
        """
        When retrieving DC information anonymously, we can't get SID of the domain
        """
        netrc = net.Net(creds=self.creds, lp=self.parm)
        try:
            if discover_srv:
                result = netrc.finddc(domain=remote_host, flags=nbt.NBT_SERVER_LDAP | nbt.NBT_SERVER_DS)
            else:
                result = netrc.finddc(address=remote_host, flags=nbt.NBT_SERVER_LDAP | nbt.NBT_SERVER_DS)
        except RuntimeError, e:
            raise assess_dcerpc_exception(message=str(e))

        if not result:
            return False
        self.info['name'] = unicode(result.domain_name)
        self.info['dns_domain'] = unicode(result.dns_domain)
        self.info['dns_forest'] = unicode(result.forest)
        self.info['guid'] = unicode(result.domain_uuid)
        self.info['dc'] = unicode(result.pdc_dns_name)

        # Netlogon response doesn't contain SID of the domain.
        # We need to do rootDSE search with LDAP_SERVER_EXTENDED_DN_OID control to reveal the SID
        ldap_uri = 'ldap://%s' % (result.pdc_dns_name)
        conn = _ldap.initialize(ldap_uri)
        conn.set_option(_ldap.OPT_SERVER_CONTROLS, [ExtendedDNControl()])
        search_result = None
        try:
            (objtype, res) = conn.search_s('', _ldap.SCOPE_BASE)[0]
            search_result = res['defaultNamingContext'][0]
            self.info['dns_hostname'] = res['dnsHostName'][0]
        except _ldap.LDAPError, e:
            root_logger.error(
                "LDAP error when connecting to %(host)s: %(error)s" %
                    dict(host=unicode(result.pdc_name), error=str(e)))
        except KeyError, e:
            root_logger.error("KeyError: {err}, LDAP entry from {host} "
                              "returned malformed. Your DNS might be "
                              "misconfigured."
                              .format(host=unicode(result.pdc_name),
                                      err=unicode(e)))

        if search_result:
            self.info['sid'] = self.parse_naming_context(search_result)
        return True

    def parse_naming_context(self, context):
        naming_ref = re.compile('.*<SID=(S-.*)>.*')
        return unicode(naming_ref.match(context).group(1))

    def retrieve(self, remote_host):
        self.init_lsa_pipe(remote_host)

        objectAttribute = lsa.ObjectAttribute()
        objectAttribute.sec_qos = lsa.QosInfo()
        try:
            self._policy_handle = self._pipe.OpenPolicy2(u"", objectAttribute, security.SEC_FLAG_MAXIMUM_ALLOWED)
            result = self._pipe.QueryInfoPolicy2(self._policy_handle, lsa.LSA_POLICY_INFO_DNS)
        except RuntimeError, (num, message):
            raise assess_dcerpc_exception(num=num, message=message)

        self.info['name'] = unicode(result.name.string)
        self.info['dns_domain'] = unicode(result.dns_domain.string)
        self.info['dns_forest'] = unicode(result.dns_forest.string)
        self.info['guid'] = unicode(result.domain_guid)
        self.info['sid'] = unicode(result.sid)
        self.info['dc'] = remote_host

    def generate_auth(self, trustdom_secret):
        def arcfour_encrypt(key, data):
            c = RC4.RC4(key)
            return c.update(data)

        password_blob = string_to_array(trustdom_secret.encode('utf-16-le'))

        clear_value = drsblobs.AuthInfoClear()
        clear_value.size = len(password_blob)
        clear_value.password = password_blob

        clear_authentication_information = drsblobs.AuthenticationInformation()
        clear_authentication_information.LastUpdateTime = samba.unix2nttime(int(time.time()))
        clear_authentication_information.AuthType = lsa.TRUST_AUTH_TYPE_CLEAR
        clear_authentication_information.AuthInfo = clear_value

        authentication_information_array = drsblobs.AuthenticationInformationArray()
        authentication_information_array.count = 1
        authentication_information_array.array = [clear_authentication_information]

        outgoing = drsblobs.trustAuthInOutBlob()
        outgoing.count = 1
        outgoing.current = authentication_information_array

        confounder = [3]*512
        for i in range(512):
            confounder[i] = random.randint(0, 255)

        trustpass = drsblobs.trustDomainPasswords()
        trustpass.confounder = confounder

        trustpass.outgoing = outgoing
        trustpass.incoming = outgoing

        trustpass_blob = ndr_pack(trustpass)

        encrypted_trustpass = arcfour_encrypt(self._pipe.session_key, trustpass_blob)

        auth_blob = lsa.DATA_BUF2()
        auth_blob.size = len(encrypted_trustpass)
        auth_blob.data = string_to_array(encrypted_trustpass)

        auth_info = lsa.TrustDomainInfoAuthInfoInternal()
        auth_info.auth_blob = auth_blob
        self.auth_info = auth_info


    def generate_ftinfo(self, another_domain):
        """
        Generates TrustDomainInfoFullInfo2Internal structure
        This structure allows to pass information about all domains associated
        with the another domain's realm.

        Only top level name and top level name exclusions are handled here.
        """
        if not another_domain.ftinfo_records:
            return

        ftinfo_records = []
        info = lsa.ForestTrustInformation()

        for rec in another_domain.ftinfo_records:
            record = lsa.ForestTrustRecord()
            record.flags = 0
            record.time = rec['rec_time']
            record.type = rec['rec_type']
            record.forest_trust_data.string = rec['rec_name']
            ftinfo_records.append(record)

        info.count = len(ftinfo_records)
        info.entries = ftinfo_records
        return info

    def update_ftinfo(self, another_domain):
        """
        Updates forest trust information in this forest corresponding
        to the another domain's information.
        """
        try:
            if another_domain.ftinfo_records:
                ftinfo = self.generate_ftinfo(another_domain)
                # Set forest trust information -- we do it only against AD DC as
                # smbd already has the information about itself
                ldname = lsa.StringLarge()
                ldname.string = another_domain.info['dns_domain']
                collision_info = self._pipe.lsaRSetForestTrustInformation(self._policy_handle,
                                                                          ldname,
                                                                          lsa.LSA_FOREST_TRUST_DOMAIN_INFO,
                                                                          ftinfo, 0)
                if collision_info:
                    root_logger.error("When setting forest trust information, got collision info back:\n%s" % (ndr_print(collision_info)))
        except RuntimeError, e:
            # We can ignore the error here -- setting up name suffix routes may fail
            pass

    def establish_trust(self, another_domain, trustdom_secret):
        """
        Establishes trust between our and another domain
        Input: another_domain -- instance of TrustDomainInstance, initialized with #retrieve call
               trustdom_secret -- shared secred used for the trust
        """
        if self.info['name'] == another_domain.info['name']:
            # Check that NetBIOS names do not clash
            raise errors.ValidationError(name=u'AD Trust Setup',
                    error=_('the IPA server and the remote domain cannot share the same '
                            'NetBIOS name: %s') % self.info['name'])

        self.generate_auth(trustdom_secret)

        info = lsa.TrustDomainInfoInfoEx()
        info.domain_name.string = another_domain.info['dns_domain']
        info.netbios_name.string = another_domain.info['name']
        info.sid = security.dom_sid(another_domain.info['sid'])
        info.trust_direction = lsa.LSA_TRUST_DIRECTION_INBOUND | lsa.LSA_TRUST_DIRECTION_OUTBOUND
        info.trust_type = lsa.LSA_TRUST_TYPE_UPLEVEL
        info.trust_attributes = lsa.LSA_TRUST_ATTRIBUTE_FOREST_TRANSITIVE

        try:
            dname = lsa.String()
            dname.string = another_domain.info['dns_domain']
            res = self._pipe.QueryTrustedDomainInfoByName(self._policy_handle, dname, lsa.LSA_TRUSTED_DOMAIN_INFO_FULL_INFO)
            self._pipe.DeleteTrustedDomain(self._policy_handle, res.info_ex.sid)
        except RuntimeError, (num, message):
            # Ignore anything but access denied (NT_STATUS_ACCESS_DENIED)
            if num == -1073741790:
                raise access_denied_error

        try:
            trustdom_handle = self._pipe.CreateTrustedDomainEx2(self._policy_handle, info, self.auth_info, security.SEC_STD_DELETE)
        except RuntimeError, (num, message):
            raise assess_dcerpc_exception(num=num, message=message)

        self.update_ftinfo(another_domain)

        # We should use proper trustdom handle in order to modify the
        # trust settings. Samba insists this has to be done with LSA
        # OpenTrustedDomain* calls, it is not enough to have a handle
        # returned by the CreateTrustedDomainEx2 call.
        trustdom_handle = self._pipe.OpenTrustedDomainByName(self._policy_handle, dname, security.SEC_FLAG_MAXIMUM_ALLOWED)
        try:
            infoclass = lsa.TrustDomainInfoSupportedEncTypes()
            infoclass.enc_types = security.KERB_ENCTYPE_RC4_HMAC_MD5
            infoclass.enc_types |= security.KERB_ENCTYPE_AES128_CTS_HMAC_SHA1_96
            infoclass.enc_types |= security.KERB_ENCTYPE_AES256_CTS_HMAC_SHA1_96
            self._pipe.SetInformationTrustedDomain(trustdom_handle, lsa.LSA_TRUSTED_DOMAIN_SUPPORTED_ENCRYPTION_TYPES, infoclass)
        except RuntimeError, e:
            # We can ignore the error here -- changing enctypes is for
            # improved security but the trust will work with default values as
            # well. In particular, the call may fail against Windows 2003
            # server as that one doesn't support AES encryption types
            pass

    def verify_trust(self, another_domain):
        def retrieve_netlogon_info_2(domain, function_code, data):
            try:
                netr_pipe = netlogon.netlogon(domain.binding, domain.parm, domain.creds)
                result = netr_pipe.netr_LogonControl2Ex(logon_server=None,
                                           function_code=function_code,
                                           level=2,
                                           data=data
                                           )
                return result
            except RuntimeError, (num, message):
                raise assess_dcerpc_exception(num=num, message=message)

        result = retrieve_netlogon_info_2(self,
                                          netlogon.NETLOGON_CONTROL_TC_VERIFY,
                                          another_domain.info['dns_domain'])
        if (result and (result.flags and netlogon.NETLOGON_VERIFY_STATUS_RETURNED)):
            # netr_LogonControl2Ex() returns non-None result only if overall call
            # result was WERR_OK which means verification was correct.
            # We only check that it was indeed status for verification process
            return True
        return False


def fetch_domains(api, mydomain, trustdomain, creds=None):
    trust_flags = dict(
                NETR_TRUST_FLAG_IN_FOREST = 0x00000001,
                NETR_TRUST_FLAG_OUTBOUND  = 0x00000002,
                NETR_TRUST_FLAG_TREEROOT  = 0x00000004,
                NETR_TRUST_FLAG_PRIMARY   = 0x00000008,
                NETR_TRUST_FLAG_NATIVE    = 0x00000010,
                NETR_TRUST_FLAG_INBOUND   = 0x00000020,
                NETR_TRUST_FLAG_MIT_KRB5  = 0x00000080,
                NETR_TRUST_FLAG_AES       = 0x00000100)

    trust_attributes = dict(
                NETR_TRUST_ATTRIBUTE_NON_TRANSITIVE     = 0x00000001,
                NETR_TRUST_ATTRIBUTE_UPLEVEL_ONLY       = 0x00000002,
                NETR_TRUST_ATTRIBUTE_QUARANTINED_DOMAIN = 0x00000004,
                NETR_TRUST_ATTRIBUTE_FOREST_TRANSITIVE  = 0x00000008,
                NETR_TRUST_ATTRIBUTE_CROSS_ORGANIZATION = 0x00000010,
                NETR_TRUST_ATTRIBUTE_WITHIN_FOREST      = 0x00000020,
                NETR_TRUST_ATTRIBUTE_TREAT_AS_EXTERNAL  = 0x00000040)

    def communicate(td):
        td.init_lsa_pipe(td.info['dc'])
        netr_pipe = netlogon.netlogon(td.binding, td.parm, td.creds)
        domains = netr_pipe.netr_DsrEnumerateDomainTrusts(td.binding, 1)
        return domains

    domains = None
    domain_validator = DomainValidator(api)
    configured = domain_validator.is_configured()
    if not configured:
        return None

    td = TrustDomainInstance('')
    td.parm.set('workgroup', mydomain)
    cr = credentials.Credentials()
    cr.set_kerberos_state(credentials.DONT_USE_KERBEROS)
    cr.guess(td.parm)
    cr.set_anonymous()
    cr.set_workstation(domain_validator.flatname)
    netrc = net.Net(creds=cr, lp=td.parm)
    try:
        result = netrc.finddc(domain=trustdomain,
                              flags=nbt.NBT_SERVER_LDAP | nbt.NBT_SERVER_DS)
    except RuntimeError, e:
        raise assess_dcerpc_exception(message=str(e))

    td.info['dc'] = unicode(result.pdc_dns_name)
    if creds is None:
        domval = DomainValidator(api)
        (ccache_name, principal) = domval.kinit_as_http(trustdomain)
        td.creds = credentials.Credentials()
        td.creds.set_kerberos_state(credentials.MUST_USE_KERBEROS)
        if ccache_name:
            with installutils.private_ccache(path=ccache_name):
                td.creds.guess(td.parm)
                td.creds.set_workstation(domain_validator.flatname)
                domains = communicate(td)
    else:
        td.creds = credentials.Credentials()
        td.creds.set_kerberos_state(credentials.DONT_USE_KERBEROS)
        td.creds.guess(td.parm)
        td.creds.parse_string(creds)
        td.creds.set_workstation(domain_validator.flatname)
        domains = communicate(td)

    if domains is None:
        return None

    result = []
    for t in domains.array:
        if ((t.trust_attributes & trust_attributes['NETR_TRUST_ATTRIBUTE_WITHIN_FOREST']) and
            (t.trust_flags & trust_flags['NETR_TRUST_FLAG_IN_FOREST'])):
            res = dict()
            res['cn'] = unicode(t.dns_name)
            res['ipantflatname'] = unicode(t.netbios_name)
            res['ipanttrusteddomainsid'] = unicode(t.sid)
            res['ipanttrustpartner'] = res['cn']
            result.append(res)
    return result


class TrustDomainJoins(object):
    def __init__(self, api):
        self.api = api
        self.local_domain = None
        self.remote_domain = None

        domain_validator = DomainValidator(api)
        self.configured = domain_validator.is_configured()

        if self.configured:
            self.local_flatname = domain_validator.flatname
            self.local_dn = domain_validator.dn
            self.__populate_local_domain()

    def __populate_local_domain(self):
        # Initialize local domain info using kerberos only
        ld = TrustDomainInstance(self.local_flatname)
        ld.creds = credentials.Credentials()
        ld.creds.set_kerberos_state(credentials.MUST_USE_KERBEROS)
        ld.creds.guess(ld.parm)
        ld.creds.set_workstation(ld.hostname)
        ld.retrieve(installutils.get_fqdn())
        self.local_domain = ld

    def populate_remote_domain(self, realm, realm_server=None, realm_admin=None, realm_passwd=None):
        def get_instance(self):
            # Fetch data from foreign domain using password only
            rd = TrustDomainInstance('')
            rd.parm.set('workgroup', self.local_domain.info['name'])
            rd.creds = credentials.Credentials()
            rd.creds.set_kerberos_state(credentials.DONT_USE_KERBEROS)
            rd.creds.guess(rd.parm)
            return rd

        rd = get_instance(self)
        rd.creds.set_anonymous()
        rd.creds.set_workstation(self.local_domain.hostname)
        if realm_server is None:
            rd.retrieve_anonymously(realm, discover_srv=True)
        else:
            rd.retrieve_anonymously(realm_server, discover_srv=False)
        rd.read_only = True
        if realm_admin and realm_passwd:
            if 'name' in rd.info:
                names = realm_admin.split('\\')
                if len(names) > 1:
                    # realm admin is in DOMAIN\user format
                    # strip DOMAIN part as we'll enforce the one discovered
                    realm_admin = names[-1]
                auth_string = u"%s\%s%%%s" % (rd.info['name'], realm_admin, realm_passwd)
                td = get_instance(self)
                td.creds.parse_string(auth_string)
                td.creds.set_workstation(self.local_domain.hostname)
                if realm_server is None:
                    # we must have rd.info['dns_hostname'] then, part of anonymous discovery
                    td.retrieve(rd.info['dns_hostname'])
                else:
                    td.retrieve(realm_server)
                td.read_only = False
                self.remote_domain = td
                return
        # Otherwise, use anonymously obtained data
        self.remote_domain = rd

    def get_realmdomains(self):
        """
        Generate list of records for forest trust information about
        our realm domains. Note that the list generated currently
        includes only top level domains, no exclusion domains, and no TDO objects
        as we handle the latter in a separate way
        """
        if self.local_domain.read_only:
            return

	self.local_domain.ftinfo_records = []

        realm_domains = self.api.Command.realmdomains_show()['result']
        # Use realmdomains' modification timestamp to judge records last update time
        entry = self.api.Backend.ldap2.get_entry(realm_domains['dn'], ['modifyTimestamp'])
        # Convert the timestamp to Windows 64-bit timestamp format
        trust_timestamp = long(time.mktime(time.strptime(entry['modifytimestamp'][0][:14], "%Y%m%d%H%M%S"))*1e7+116444736000000000)

        for dom in realm_domains['associateddomain']:
            ftinfo = dict()
            ftinfo['rec_name'] = dom
            ftinfo['rec_time'] = trust_timestamp
            ftinfo['rec_type'] = lsa.LSA_FOREST_TRUST_TOP_LEVEL_NAME
            self.local_domain.ftinfo_records.append(ftinfo)

    def join_ad_full_credentials(self, realm, realm_server, realm_admin, realm_passwd):
        if not self.configured:
            return None

        if not(isinstance(self.remote_domain, TrustDomainInstance)):
            self.populate_remote_domain(
                realm,
                realm_server,
                realm_admin,
                realm_passwd
            )

        if not self.remote_domain.read_only:
            trustdom_pass = samba.generate_random_password(128, 128)
            self.get_realmdomains()
            self.remote_domain.establish_trust(self.local_domain, trustdom_pass)
            self.local_domain.establish_trust(self.remote_domain, trustdom_pass)
            result = self.remote_domain.verify_trust(self.local_domain)
            return dict(local=self.local_domain, remote=self.remote_domain, verified=result)
        return None

    def join_ad_ipa_half(self, realm, realm_server, trustdom_passwd):
        if not self.configured:
            return None

        if not(isinstance(self.remote_domain, TrustDomainInstance)):
            self.populate_remote_domain(realm, realm_server, realm_passwd=None)

        self.local_domain.establish_trust(self.remote_domain, trustdom_passwd)
        return dict(local=self.local_domain, remote=self.remote_domain, verified=False)
