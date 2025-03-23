# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os.path

import ldap
from ldap import filter as ldap_filter

from keystone.common.ldap import fakeldap
from keystone import exception
from keystone.openstack.common import log as logging

LOG = logging.getLogger(__name__)


LDAP_VALUES = {'TRUE': True, 'FALSE': False}
CONTROL_TREEDELETE = '1.2.840.113556.1.4.805'
LDAP_SCOPES = {'one': ldap.SCOPE_ONELEVEL,
               'sub': ldap.SCOPE_SUBTREE}
LDAP_DEREF = {'always': ldap.DEREF_ALWAYS,
              'default': None,
              'finding': ldap.DEREF_FINDING,
              'never': ldap.DEREF_NEVER,
              'searching': ldap.DEREF_SEARCHING}
LDAP_TLS_CERTS = {'never': ldap.OPT_X_TLS_NEVER,
                  'demand': ldap.OPT_X_TLS_DEMAND,
                  'allow': ldap.OPT_X_TLS_ALLOW}


def py2ldap(val):
    if isinstance(val, str):
        return val
    elif isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    else:
        return str(val)


def ldap2py(val):
    try:
        return LDAP_VALUES[val]
    except KeyError:
        pass
    try:
        return int(val)
    except ValueError:
        pass
    return val


def safe_iter(attrs):
    if attrs is None:
        return
    elif isinstance(attrs, list):
        for e in attrs:
            yield e
    else:
        yield attrs


def parse_deref(opt):
    try:
        return LDAP_DEREF[opt]
    except KeyError:
        raise ValueError((_('Invalid LDAP deref option: %s. Choose one of: ') %
                         opt) + ', '.join(LDAP_DEREF.keys()))


def parse_tls_cert(opt):
    try:
        return LDAP_TLS_CERTS[opt]
    except KeyError:
        raise ValueError(_(
            'Invalid LDAP TLS certs option: %(option). '
            'Choose one of: %(options)s') % {
                'option': opt,
                'options': ', '.join(LDAP_TLS_CERTS.keys())})


def ldap_scope(scope):
    try:
        return LDAP_SCOPES[scope]
    except KeyError:
        raise ValueError(
            _('Invalid LDAP scope: %(scope)s. Choose one of: %(options)s') % {
                'scope': scope,
                'options': ', '.join(LDAP_SCOPES.keys())})


class BaseLdap(object):
    DEFAULT_SUFFIX = "dc=example,dc=com"
    DEFAULT_OU = None
    DEFAULT_STRUCTURAL_CLASSES = None
    DEFAULT_ID_ATTR = 'cn'
    DEFAULT_OBJECTCLASS = None
    DEFAULT_FILTER = None
    DEFAULT_EXTRA_ATTR_MAPPING = []
    DUMB_MEMBER_DN = 'cn=dumb,dc=nonexistent'
    NotFound = None
    notfound_arg = None
    options_name = None
    model = None
    attribute_options_names = {}
    immutable_attrs = []
    attribute_ignore = []
    tree_dn = None

    def __init__(self, conf):
        self.LDAP_URL = conf.ldap.url
        self.LDAP_USER = conf.ldap.user
        self.LDAP_PASSWORD = conf.ldap.password
        self.LDAP_SCOPE = ldap_scope(conf.ldap.query_scope)
        self.alias_dereferencing = parse_deref(conf.ldap.alias_dereferencing)
        self.page_size = conf.ldap.page_size
        self.use_tls = conf.ldap.use_tls
        self.tls_cacertfile = conf.ldap.tls_cacertfile
        self.tls_cacertdir = conf.ldap.tls_cacertdir
        self.tls_req_cert = parse_tls_cert(conf.ldap.tls_req_cert)
        self.attribute_mapping = {}

        if self.options_name is not None:
            self.suffix = conf.ldap.suffix
            if self.suffix is None:
                self.suffix = self.DEFAULT_SUFFIX
            dn = '%s_tree_dn' % self.options_name
            self.tree_dn = (getattr(conf.ldap, dn)
                            or '%s,%s' % (self.DEFAULT_OU, self.suffix))

            idatt = '%s_id_attribute' % self.options_name
            self.id_attr = getattr(conf.ldap, idatt) or self.DEFAULT_ID_ATTR

            objclass = '%s_objectclass' % self.options_name
            self.object_class = (getattr(conf.ldap, objclass)
                                 or self.DEFAULT_OBJECTCLASS)

            for k, v in self.attribute_options_names.iteritems():
                v = '%s_%s_attribute' % (self.options_name, v)
                self.attribute_mapping[k] = getattr(conf.ldap, v)

            attr_mapping_opt = ('%s_additional_attribute_mapping' %
                                self.options_name)
            attr_mapping = (getattr(conf.ldap, attr_mapping_opt)
                            or self.DEFAULT_EXTRA_ATTR_MAPPING)
            self.extra_attr_mapping = self._parse_extra_attrs(attr_mapping)

            filter = '%s_filter' % self.options_name
            self.filter = getattr(conf.ldap, filter) or self.DEFAULT_FILTER

            allow_create = '%s_allow_create' % self.options_name
            self.allow_create = getattr(conf.ldap, allow_create)

            allow_update = '%s_allow_update' % self.options_name
            self.allow_update = getattr(conf.ldap, allow_update)

            allow_delete = '%s_allow_delete' % self.options_name
            self.allow_delete = getattr(conf.ldap, allow_delete)

            self.structural_classes = self.DEFAULT_STRUCTURAL_CLASSES

            if self.notfound_arg is None:
                self.notfound_arg = self.options_name + '_id'

            attribute_ignore = '%s_attribute_ignore' % self.options_name
            self.attribute_ignore = getattr(conf.ldap, attribute_ignore)

        self.use_dumb_member = getattr(conf.ldap, 'use_dumb_member')
        self.dumb_member = (getattr(conf.ldap, 'dumb_member') or
                            self.DUMB_MEMBER_DN)

        self.subtree_delete_enabled = getattr(conf.ldap,
                                              'allow_subtree_delete')

    def _not_found(self, object_id):
        if self.NotFound is None:
            return exception.NotFound(target=object_id)
        else:
            return self.NotFound(**{self.notfound_arg: object_id})

    def _parse_extra_attrs(self, option_list):
        mapping = {}
        for item in option_list:
            try:
                ldap_attr, attr_map = item.split(':')
            except Exception:
                LOG.warn(_(
                    'Invalid additional attribute mapping: "%s". '
                    'Format must be <ldap_attribute>:<keystone_attribute>')
                    % item)
                continue
            if attr_map not in self.attribute_mapping:
                LOG.warn(_('Invalid additional attribute mapping: "%(item)s". '
                           'Value "%(attr_map)s" must use one of %(keys)s.') %
                         {'item': item, 'attr_map': attr_map,
                          'keys': ', '.join(self.attribute_mapping.keys())})
                continue
            mapping[ldap_attr] = attr_map
        return mapping

    def get_connection(self, user=None, password=None):
        if self.LDAP_URL.startswith('fake://'):
            conn = fakeldap.FakeLdap(self.LDAP_URL)
        else:
            conn = LdapWrapper(self.LDAP_URL,
                               self.page_size,
                               alias_dereferencing=self.alias_dereferencing,
                               use_tls=self.use_tls,
                               tls_cacertfile=self.tls_cacertfile,
                               tls_cacertdir=self.tls_cacertdir,
                               tls_req_cert=self.tls_req_cert)

        if user is None:
            user = self.LDAP_USER

        if password is None:
            password = self.LDAP_PASSWORD

        # not all LDAP servers require authentication, so we don't bind
        # if we don't have any user/pass
        if user and password:
            conn.simple_bind_s(user, password)

        return conn

    def _id_to_dn_string(self, id):
        return '%s=%s,%s' % (self.id_attr,
                             ldap.dn.escape_dn_chars(str(id)),
                             self.tree_dn)

    def _id_to_dn(self, id):
        if self.LDAP_SCOPE == ldap.SCOPE_ONELEVEL:
            return self._id_to_dn_string(id)
        conn = self.get_connection()
        search_result = conn.search_s(
            self.tree_dn, self.LDAP_SCOPE,
            '(&(%(id_attr)s=%(id)s)(objectclass=%(objclass)s))' %
            {'id_attr': self.id_attr,
             'id': ldap.filter.escape_filter_chars(str(id)),
             'objclass': self.object_class})
        if search_result:
            dn, attrs = search_result[0]
            return dn
        else:
            return self._id_to_dn_string(id)

    @staticmethod
    def _dn_to_id(dn):
        return ldap.dn.str2dn(dn)[0][0][1]

    def _ldap_res_to_model(self, res):
        obj = self.model(id=self._dn_to_id(res[0]))
        for k in obj.known_keys:
            if k in self.attribute_ignore:
                continue

            try:
                v = res[1][self.attribute_mapping.get(k, k)]
            except KeyError:
                pass
            else:
                try:
                    obj[k] = v[0]
                except IndexError:
                    obj[k] = None

        return obj

    def affirm_unique(self, values):
        if values.get('name') is not None:
            try:
                self.get_by_name(values['name'])
            except exception.NotFound:
                pass
            else:
                raise exception.Conflict(type=self.options_name,
                                         details=_('Duplicate name, %s.') %
                                         values['name'])

        if values.get('id') is not None:
            try:
                self.get(values['id'])
            except exception.NotFound:
                pass
            else:
                raise exception.Conflict(type=self.options_name,
                                         details=_('Duplicate ID, %s.') %
                                         values['id'])

    def create(self, values):
        self.affirm_unique(values)
        if not self.allow_create:
            action = _('LDAP %s create') % self.options_name
            raise exception.ForbiddenAction(action=action)

        conn = self.get_connection()
        object_classes = self.structural_classes + [self.object_class]
        attrs = [('objectClass', object_classes)]
        for k, v in values.iteritems():
            if k == 'id' or k in self.attribute_ignore:
                continue
            if v is not None:
                attr_type = self.attribute_mapping.get(k, k)
                attrs.append((attr_type, [v]))
                extra_attrs = [attr for attr, name
                               in self.extra_attr_mapping.iteritems()
                               if name == k]
                for attr in extra_attrs:
                    attrs.append((attr, [v]))

        if 'groupOfNames' in object_classes and self.use_dumb_member:
            attrs.append(('member', [self.dumb_member]))

        conn.add_s(self._id_to_dn(values['id']), attrs)
        return values

    def _ldap_get(self, id, filter=None):
        conn = self.get_connection()
        query = ('(&(%(id_attr)s=%(id)s)'
                 '%(filter)s'
                 '(objectClass=%(object_class)s))'
                 % {'id_attr': self.id_attr,
                    'id': ldap.filter.escape_filter_chars(str(id)),
                    'filter': (filter or self.filter or ''),
                    'object_class': self.object_class})
        try:
            attrs = list(set((self.attribute_mapping.values() +
                              self.extra_attr_mapping.keys())))
            res = conn.search_s(self.tree_dn, self.LDAP_SCOPE, query, attrs)
        except ldap.NO_SUCH_OBJECT:
            return None
        try:
            return res[0]
        except IndexError:
            return None

    def _ldap_get_all(self, filter=None):
        conn = self.get_connection()
        query = '(&%s(objectClass=%s))' % (filter or self.filter or '',
                                           self.object_class)
        try:
            return conn.search_s(self.tree_dn,
                                 self.LDAP_SCOPE,
                                 query,
                                 self.attribute_mapping.values())
        except ldap.NO_SUCH_OBJECT:
            return []

    def get(self, id, filter=None):
        res = self._ldap_get(id, filter)
        if res is None:
            raise self._not_found(id)
        else:
            return self._ldap_res_to_model(res)

    def get_by_name(self, name, filter=None):
        query = ('(%s=%s)' % (self.attribute_mapping['name'],
                              ldap_filter.escape_filter_chars(name)))
        res = self.get_all(query)
        try:
            return res[0]
        except IndexError:
            raise self._not_found(name)

    def get_all(self, filter=None):
        return [self._ldap_res_to_model(x)
                for x in self._ldap_get_all(filter)]

    def update(self, id, values, old_obj=None):
        if not self.allow_update:
            action = _('LDAP %s update') % self.options_name
            raise exception.ForbiddenAction(action=action)

        if old_obj is None:
            old_obj = self.get(id)

        modlist = []
        for k, v in values.iteritems():
            if k == 'id' or k in self.attribute_ignore:
                continue
            if k in self.immutable_attrs and old_obj[k] != v:
                msg = (_("Cannot change %(option_name)s %(attr)s") %
                       {'option_name': self.options_name, 'attr': k})
                raise exception.ValidationError(msg)
            if v is None:
                if old_obj[k] is not None:
                    modlist.append((ldap.MOD_DELETE,
                                    self.attribute_mapping.get(k, k),
                                    None))
            elif old_obj[k] != v:
                if old_obj[k] is None:
                    op = ldap.MOD_ADD
                else:
                    op = ldap.MOD_REPLACE
                modlist.append((op, self.attribute_mapping.get(k, k), [v]))

        if modlist:
            conn = self.get_connection()
            try:
                conn.modify_s(self._id_to_dn(id), modlist)
            except ldap.NO_SUCH_OBJECT:
                raise self._not_found(id)

        return self.get(id)

    def delete(self, id):
        if not self.allow_delete:
            action = _('LDAP %s delete') % self.options_name
            raise exception.ForbiddenAction(action=action)

        conn = self.get_connection()
        try:
            conn.delete_s(self._id_to_dn(id))
        except ldap.NO_SUCH_OBJECT:
            raise self._not_found(id)

    def deleteTree(self, id):
        conn = self.get_connection()
        tree_delete_control = ldap.controls.LDAPControl(CONTROL_TREEDELETE,
                                                        0,
                                                        None)
        try:
            conn.delete_ext_s(self._id_to_dn(id),
                              serverctrls=[tree_delete_control])
        except ldap.NO_SUCH_OBJECT:
            raise self._not_found(id)


class LdapWrapper(object):
    def __init__(self, url, page_size, alias_dereferencing=None,
                 use_tls=False, tls_cacertfile=None, tls_cacertdir=None,
                 tls_req_cert='demand'):
        LOG.debug(_("LDAP init: url=%s"), url)
        LOG.debug(_('LDAP init: use_tls=%(use_tls)s\n'
                  'tls_cacertfile=%(tls_cacertfile)s\n'
                  'tls_cacertdir=%(tls_cacertdir)s\n'
                  'tls_req_cert=%(tls_req_cert)s\n'
                  'tls_avail=%(tls_avail)s\n') %
                  {'use_tls': use_tls,
                   'tls_cacertfile': tls_cacertfile,
                   'tls_cacertdir': tls_cacertdir,
                   'tls_req_cert': tls_req_cert,
                   'tls_avail': ldap.TLS_AVAIL
                   })

        #NOTE(topol)
        #for extra debugging uncomment the following line
        #ldap.set_option(ldap.OPT_DEBUG_LEVEL, 4095)

        using_ldaps = url.lower().startswith("ldaps")

        if use_tls and using_ldaps:
            raise AssertionError(_('Invalid TLS / LDAPS combination'))

        if use_tls:
            if not ldap.TLS_AVAIL:
                raise ValueError(_('Invalid LDAP TLS_AVAIL option: %s. TLS '
                                   'not available') % ldap.TLS_AVAIL)
            if tls_cacertfile:
                #NOTE(topol)
                #python ldap TLS does not verify CACERTFILE or CACERTDIR
                #so we add some extra simple sanity check verification
                #Also, setting these values globally (i.e. on the ldap object)
                #works but these values are ignored when setting them on the
                #connection
                if not os.path.isfile(tls_cacertfile):
                    raise IOError(_("tls_cacertfile %s not found "
                                    "or is not a file") %
                                  tls_cacertfile)
                ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, tls_cacertfile)
            elif tls_cacertdir:
                #NOTE(topol)
                #python ldap TLS does not verify CACERTFILE or CACERTDIR
                #so we add some extra simple sanity check verification
                #Also, setting these values globally (i.e. on the ldap object)
                #works but these values are ignored when setting them on the
                #connection
                if not os.path.isdir(tls_cacertdir):
                    raise IOError(_("tls_cacertdir %s not found "
                                    "or is not a directory") %
                                  tls_cacertdir)
                ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, tls_cacertdir)
            if tls_req_cert in LDAP_TLS_CERTS.values():
                ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, tls_req_cert)
            else:
                LOG.debug(_("LDAP TLS: invalid TLS_REQUIRE_CERT Option=%s"),
                          tls_req_cert)

        self.conn = ldap.initialize(url)
        self.conn.protocol_version = ldap.VERSION3

        if alias_dereferencing is not None:
            self.conn.set_option(ldap.OPT_DEREF, alias_dereferencing)
        self.page_size = page_size

        if use_tls:
            self.conn.start_tls_s()

    def simple_bind_s(self, user, password):
        LOG.debug(_("LDAP bind: dn=%s"), user)
        return self.conn.simple_bind_s(user, password)

    def add_s(self, dn, attrs):
        ldap_attrs = [(kind, [py2ldap(x) for x in safe_iter(values)])
                      for kind, values in attrs]
        sane_attrs = [(kind, values
                       if kind != 'userPassword'
                       else ['****'])
                      for kind, values in ldap_attrs]
        LOG.debug(_('LDAP add: dn=%(dn)s, attrs=%(attrs)s') % {
            'dn': dn, 'attrs': sane_attrs})
        return self.conn.add_s(dn, ldap_attrs)

    def search_s(self, dn, scope, query, attrlist=None):
        LOG.debug(_(
            'LDAP search: dn=%(dn)s, scope=%(scope)s, query=%(query)s, '
            'attrs=%(attrlist)s') % {
                'dn': dn,
                'scope': scope,
                'query': query,
                'attrlist': attrlist})
        if self.page_size:
            res = self.paged_search_s(dn, scope, query, attrlist)
        else:
            res = self.conn.search_s(dn, scope, query, attrlist)

        o = []
        for dn, attrs in res:
            o.append((dn, dict((kind, [ldap2py(x) for x in values])
                               for kind, values in attrs.iteritems())))
        return o

    def paged_search_s(self, dn, scope, query, attrlist=None):
        res = []
        lc = ldap.controls.SimplePagedResultsControl(
            controlType=ldap.LDAP_CONTROL_PAGE_OID,
            criticality=True,
            controlValue=(self.page_size, ''))
        msgid = self.conn.search_ext(dn,
                                     scope,
                                     query,
                                     attrlist,
                                     serverctrls=[lc])
        # Endless loop request pages on ldap server until it has no data
        while True:
            # Request to the ldap server a page with 'page_size' entries
            rtype, rdata, rmsgid, serverctrls = self.conn.result3(msgid)
            # Receive the data
            res.extend(rdata)
            pctrls = [c for c in serverctrls
                      if c.controlType == ldap.LDAP_CONTROL_PAGE_OID]
            if pctrls:
                # LDAP server supports pagination
                est, cookie = pctrls[0].controlValue
                if cookie:
                    # There is more data still on the server
                    # so we request another page
                    lc.controlValue = (self.page_size, cookie)
                    msgid = self.conn.search_ext(dn,
                                                 scope,
                                                 query,
                                                 attrlist,
                                                 serverctrls=[lc])
                else:
                    # Exit condition no more data on server
                    break
            else:
                LOG.warning(_('LDAP Server does not support paging. '
                              'Disable paging in keystone.conf to '
                              'avoid this message.'))
                self._disable_paging()
                break
        return res

    def modify_s(self, dn, modlist):
        ldap_modlist = [
            (op, kind, (None if values is None
                        else [py2ldap(x) for x in safe_iter(values)]))
            for op, kind, values in modlist]

        sane_modlist = [(op, kind, (values if kind != 'userPassword'
                                    else ['****']))
                        for op, kind, values in ldap_modlist]
        LOG.debug(_('LDAP modify: dn=%(dn)s, modlist=%(modlist)s') % {
            'dn': dn, 'modlist': sane_modlist})

        return self.conn.modify_s(dn, ldap_modlist)

    def delete_s(self, dn):
        LOG.debug(_("LDAP delete: dn=%s"), dn)
        return self.conn.delete_s(dn)

    def delete_ext_s(self, dn, serverctrls):
        LOG.debug(
            _('LDAP delete_ext: dn=%(dn)s, serverctrls=%(serverctrls)s') % {
                'dn': dn, 'serverctrls': serverctrls})
        return self.conn.delete_ext_s(dn, serverctrls)

    def _disable_paging(self):
        # Disable the pagination from now on
        self.page_size = 0


class EnabledEmuMixIn(BaseLdap):
    """Emulates boolean 'enabled' attribute if turned on.

    Creates groupOfNames holding all enabled objects of this class, all missing
    objects are considered disabled.

    Options:

    * $name_enabled_emulation - boolean, on/off
    * $name_enabled_emulation_dn - DN of that groupOfNames, default is
      cn=enabled_$name,$tree_dn

    Where $name is self.options_name ('user' or 'tenant'), $tree_dn is
    self.tree_dn.
    """

    def __init__(self, conf):
        super(EnabledEmuMixIn, self).__init__(conf)
        enabled_emulation = '%s_enabled_emulation' % self.options_name
        self.enabled_emulation = getattr(conf.ldap, enabled_emulation)

        enabled_emulation_dn = '%s_enabled_emulation_dn' % self.options_name
        self.enabled_emulation_dn = getattr(conf.ldap, enabled_emulation_dn)
        if not self.enabled_emulation_dn:
            self.enabled_emulation_dn = ('cn=enabled_%ss,%s' %
                                         (self.options_name, self.tree_dn))

    def _get_enabled(self, object_id):
        conn = self.get_connection()
        dn = self._id_to_dn(object_id)
        query = '(member=%s)' % dn
        try:
            enabled_value = conn.search_s(self.enabled_emulation_dn,
                                          ldap.SCOPE_BASE,
                                          query)
        except ldap.NO_SUCH_OBJECT:
            return False
        else:
            return bool(enabled_value)

    def _add_enabled(self, object_id):
        if not self._get_enabled(object_id):
            conn = self.get_connection()
            modlist = [(ldap.MOD_ADD,
                        'member',
                        [self._id_to_dn(object_id)])]
            try:
                conn.modify_s(self.enabled_emulation_dn, modlist)
            except ldap.NO_SUCH_OBJECT:
                attr_list = [('objectClass', ['groupOfNames']),
                             ('member',
                             [self._id_to_dn(object_id)])]
                if self.use_dumb_member:
                    attr_list[1][1].append(self.dumb_member)
                conn.add_s(self.enabled_emulation_dn, attr_list)

    def _remove_enabled(self, object_id):
        conn = self.get_connection()
        modlist = [(ldap.MOD_DELETE,
                    'member',
                    [self._id_to_dn(object_id)])]
        try:
            conn.modify_s(self.enabled_emulation_dn, modlist)
        except (ldap.NO_SUCH_OBJECT, ldap.NO_SUCH_ATTRIBUTE):
            pass

    def create(self, values):
        if self.enabled_emulation:
            enabled_value = values.pop('enabled', True)
            ref = super(EnabledEmuMixIn, self).create(values)
            if 'enabled' not in self.attribute_ignore:
                if enabled_value:
                    self._add_enabled(ref['id'])
                ref['enabled'] = enabled_value
            return ref
        else:
            return super(EnabledEmuMixIn, self).create(values)

    def get(self, object_id, filter=None):
        ref = super(EnabledEmuMixIn, self).get(object_id, filter)
        if 'enabled' not in self.attribute_ignore and self.enabled_emulation:
            ref['enabled'] = self._get_enabled(object_id)
        return ref

    def get_all(self, filter=None):
        if 'enabled' not in self.attribute_ignore and self.enabled_emulation:
            # had to copy BaseLdap.get_all here to filter by DN
            tenant_list = [self._ldap_res_to_model(x)
                           for x in self._ldap_get_all(filter)
                           if x[0] != self.enabled_emulation_dn]
            for tenant_ref in tenant_list:
                tenant_ref['enabled'] = self._get_enabled(tenant_ref['id'])
            return tenant_list
        else:
            return super(EnabledEmuMixIn, self).get_all(filter)

    def update(self, object_id, values, old_obj=None):
        if 'enabled' not in self.attribute_ignore and self.enabled_emulation:
            data = values.copy()
            enabled_value = data.pop('enabled', None)
            ref = super(EnabledEmuMixIn, self).update(object_id, data, old_obj)
            if enabled_value is not None:
                if enabled_value:
                    self._add_enabled(object_id)
                else:
                    self._remove_enabled(object_id)
            return ref
        else:
            return super(EnabledEmuMixIn, self).update(
                object_id, values, old_obj)

    def delete(self, object_id):
        if self.enabled_emulation:
            self._remove_enabled(object_id)
        super(EnabledEmuMixIn, self).delete(object_id)
