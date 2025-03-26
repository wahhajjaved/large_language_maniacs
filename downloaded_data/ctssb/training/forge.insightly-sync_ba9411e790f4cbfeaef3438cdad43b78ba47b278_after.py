"""Push updates to LDAP."""
import ldap as _ldap
import ldap.modlist as _modlist
import logging
from __init__ import sanitize, fileToRedmine
from unidecode import unidecode
from canned_mailer import CannedMailer
from insightly_updater import InsightlyUpdater
from fuzzywuzzy.process import extractOne


class ForgeLDAP(object):

    """LDAP connection wrapper.

    Represents an LDAP connection and exposes LDAP CRUD operation funtions.
    """

    _c = None
    _logger = None
    _redmine_key = None
    username = None

    def __init__(self, user, pwd, host, redmine_key=None):
        """Initialize the LDAP connection.

        Initialize an LDAP object and bind it to the specified host.

        Args:
            user (str): The cn attribute of the account to use for binding. Must have administrator rights.
            pwd (str): The password for the specified user.
            host (str): The FQDN or IP of the host running the LDAP server. Connection uses ldaps protocol.
        """
        self._logger = logging.getLogger(self.__class__.__name__)
        self._redmine_key = redmine_key

        dn = 'cn=%s,%s' % (user, LDAPUpdater._LDAP_TREE['accounts'])
        _ldap.set_option(_ldap.OPT_X_TLS_REQUIRE_CERT, _ldap.OPT_X_TLS_ALLOW)
        self._c = _ldap.initialize("ldaps://%s" % host)
        self.username = user
        self._c.bind_s(dn, pwd, _ldap.AUTH_SIMPLE)

    def destroy(self):
        """Unbind the underlying LDAP connection.

        Ensures that the LDAP conection does not remain open.
        """
        self._c.unbind_s()

    def ldap_search(self, *args, **kwargs):
        """Search LDAP.

        Performs an LDAP search.

        Args:
            *args: positional arguments for ldap synchronous search, as per python ldap module.
            *kwargs: keyword arguments for ldap synchronous search, as per python ldap module.

        Returns:
            List: A list containing the results from the LDAP search.
            None: If there are no results.
        """
        try:
            ldap_res = self._c.search_s(*args, **kwargs)
        except _ldap.NO_SUCH_OBJECT:
            return None
        return ldap_res

    def ldap_add(self, *args):
        """Add entries to LDAP.

        Performs an LDAP add operation.

        Args:
            *args: positional arguments for ldap synchronous add, as per python ldap module.
            *kwargs: keyword arguments for ldap synchronous add, as per python ldap module.
        """
        try:
            self._c.add_s(*args)
        except _ldap.ALREADY_EXISTS, err:
            self._logger.info('%s; %s' % (err, 'Ignoring.'))
        except _ldap.LDAPError, err:
            self._logger.error('Try LDAPadd: %s' % list(args))
            self._logger.error(err)
            if self._redmine_key:
                fileToRedmine(key=self._redmine_key, subject=err.__class__.__name__, message='%s\nTry LDAPadd: %s'
                              % (err, args))

    def ldap_update(self, *args):
        """Modify entries on LDAP.

        Performs an LDAP modify operation.

        Args:
            *args: positional arguments for ldap synchronous modify, as per python ldap module.
            *kwargs: keyword arguments for ldap synchronous modify, as per python ldap module.
        """
        try:
            self._c.modify_s(*args)
        except _ldap.LDAPError, err:
            self._logger.error('Try LDAPmodify: %s' % list(args))
            self._logger.error(err)
            if self._redmine_key:
                fileToRedmine(key=self._redmine_key, subject=err.__class__.__name__, message='%s\nTry LDAPmodify: %s'
                              % (err, args))

    def ldap_delete(self, *args):
        """Delete entries from LDAP.

        Performs an LDAP delete operation.

        Args:
            *args: positional arguments for ldap synchronous delete, as per python ldap module.
            *kwargs: keyword arguments for ldap synchronous delete, as per python ldap module.
        """
        try:
            self._c.delete_s(*args)
        except _ldap.LDAPError, err:
            self._logger.error('Try LDAPdelete: %s' % list(args))
            self._logger.error(err)
            if self._redmine_key:
                fileToRedmine(key=self._redmine_key, subject=err.__class__.__name__, message='%s\nTry LDAPdelete: %s'
                              % (err, args))


class LDAPUpdater:

    """Update LDAP server to represent identity and membership relations stated on Insightly.

    Attributes:
        SDA: Constant representing the name of the SDA category on Insightly.
        FPA: Constant representing the name of the FPA category on Insightly.
        FPA_CRA: Constant representing the name of the FPA with CRA category on Insightly.
        OS_TENANT: Constant representing the name of the OpenStack tenant category on Insightly.
        PIPELINE_NAME: Constant representing the name of the Project execution pipeline on Insightly.

        ACTION_CREATE: Constant representing the create key for the Action function.
        ACTION_DELETE: Constant representing the delete key for the Action function.
        ACTION_UPDATE: Constant representing the update key for the Action function.
    """

    SDA = 'SDA'
    FPA = 'FPA'
    FPA_CRA = 'FPA (CRA)'
    OS_TENANT = 'OpenStack Tenant'
    PIPELINE_NAME = 'Project execution'

    ACTION_CREATE = 'create'
    ACTION_DELETE = 'delete'
    ACTION_UPDATE = 'update'

    _LDAP_TREE = {'accounts': "ou=accounts,dc=forgeservicelab,dc=fi",
                  'projects': "ou=projects,dc=forgeservicelab,dc=fi",
                  'admins': "cn=ldap_admins,ou=roles,dc=forgeservicelab,dc=fi"}

    _PROTECTED_ACCOUNTS = ['admin', 'binder', 'pwdchanger', 'syncer']

    _ALL_OTHER_GROUPS_FILTER = '(&(|(objectClass=groupOfNames)\
                                    (objectClass=groupOfUniqueNames))\
                                  (|(member=cn={user_cn},%(s)s)\
                                    (uniqueMember=cn={user_cn},%(s)s))\
                                  (!(cn:dn:={project_cn})))'.replace(' ', '') % {'s': _LDAP_TREE['accounts']}

    _PLACEHOLDER_NAME = 'FirstName'
    _PLACEHOLDER_SN = 'LastName'

    def __init__(self, insightlyUpdater):
        """Initialize instance."""
        self.mailer = CannedMailer()
        self.updater = insightlyUpdater

    def _parseName(self, name):
        """Return the first element of a compound name that is not a known particle.

        Args:
            name (str): The name to be parsed.

        Returns:
            str: The transliterated first non-particle element of a name, capped to 10 characters.
        """
        PARTICLES = ['de', 'della', 'von', 'und']
        SPECIAL_CHARS = ['\'', '.', '!']

        splitName = reduce(list.__add__, map(lambda n: n.split('-'), name.split()))

        try:
            while splitName[0].lower() in PARTICLES:
                splitName.pop(0)
        except IndexError:
            pass

        return unidecode(filter(lambda c: c not in SPECIAL_CHARS,
                                splitName[0].decode('utf-8').lower()[:10])) if splitName else None

    def _ldapCN(self, userID, ldap_conn):
        return ldap_conn.ldap_search(self._LDAP_TREE['accounts'], _ldap.SCOPE_ONELEVEL,
                                     filterstr='employeeNumber=%s' % userID,
                                     attrsonly=1)[0][0]

    def _createCN(self, user, ldap_conn):
        firstName = None if user['givenName'] is self._PLACEHOLDER_NAME else self._parseName(user['givenName'])
        lastName = None if user['sn'] is self._PLACEHOLDER_SN else self._parseName(user['sn'])

        cn = '.'.join(filter(lambda n: n, [firstName, lastName]))

        suffix = 0
        while ldap_conn.ldap_search('cn=%s,%s' % (cn, self._LDAP_TREE['accounts']), _ldap.SCOPE_BASE, attrsonly=1):
            cn = '%s.%s' % (cn[:-2], suffix)
            suffix += 1

        return cn

    def _disableAndNotify(self, dn, ldap_conn):
        account = ldap_conn.ldap_search(dn, _ldap.SCOPE_BASE, attrlist=['employeeType', 'cn', 'mail'])[0][1]
        if account and ('employeeType' not in account or not extractOne(account['employeeType'][0],
                                                                        ['disabled'], score_cutoff=80)):
            ldap_conn.ldap_update(dn, [(_ldap.MOD_REPLACE, 'employeeType', 'disabled')])
            map(lambda e: self.mailer.sendCannedMail(e, self.mailer.CANNED_MESSAGES['disabled_account'],
                                                     account['cn'][0]), account['mail'])

    def _pruneAccounts(self, ldap_conn):
        # Disable orphans
        map(lambda entry: self._disableAndNotify(entry, ldap_conn),
            map(lambda dn: dn[0],
                filter(lambda a: 'memberOf' not in a[1].keys() and not any(cn in a[0] for cn in
                                                                           self._PROTECTED_ACCOUNTS),
                       ldap_conn.ldap_search(self._LDAP_TREE['accounts'],
                                             _ldap.SCOPE_ONELEVEL,
                                             attrlist=['memberOf']))))

        # Re-enable non orphans
        map(lambda entry: ldap_conn.ldap_update(entry, [(_ldap.MOD_REPLACE, 'employeeType', None)]),
            map(lambda dn: dn[0],
                filter(lambda a: 'memberOf' in a[1].keys(),
                       ldap_conn.ldap_search(self._LDAP_TREE['accounts'],
                                             _ldap.SCOPE_ONELEVEL,
                                             attrlist=['memberOf'],
                                             filterstr='(employeeType=disabled)'))))

    def _getLDAPCompatibleProject(self, project, objectClass, ldap_conn):
        project = project.copy()
        project['objectClass'] = objectClass
        project['owner'] = [self._ldapCN(owner['employeeNumber'], ldap_conn) for owner in project.pop('owner', [])]
        project['member'] = [self._ldapCN(member['employeeNumber'], ldap_conn) for member in project.pop('member', [])]
        project['seeAlso'] = [self._ldapCN(seeAlso['employeeNumber'],
                                           ldap_conn) for seeAlso in project.pop('seeAlso', [])]
        project['uniqueMember'] = project['member']
        project.pop('tenants')
        project.pop('member' if objectClass is 'groupOfUniqueNames' else 'uniqueMember')

        return project

    def _getLDAPCompatibleAccount(self, account):
        account = account.copy()
        account['objectClass'] = 'inetOrgPerson'
        account['employeeType'] = 'hidden' if 'True' in account.pop('isHidden') else ''

        return account

    # deprecated
    def _createRecord(self, project, ldap_conn):
        return filter(lambda r: len(r[1]), [
            ('objectClass', ['groupOfNames']),
            ('cn', [project['cn']]),
            ('o', project['o']),
            ('owner', map(lambda o: self._ldapCN(o['uid'], ldap_conn), project['owner'])),
            ('seeAlso', map(lambda a: self._ldapCN(a['uid'], ldap_conn), project['seeAlso'])),
            ('member', map(lambda m: self._ldapCN(m['uid'], ldap_conn), project['members'])),
            ('description', ['type:%s' % item for item in project['description']])
        ])

    # deprecated
    def _createTenantRecord(self, tenant, ldap_conn):
        record = self._createRecord(tenant, ldap_conn)
        record = map(lambda r: r if r[0] != 'objectClass' else (r[0], ['groupOfUniqueNames']), record)
        if len(record) == 7:
            record = map(lambda r: r if r[0] != 'owner' else ('uniqueMember', r[1]), record)
            record.pop(4)
            record.pop(4)
        else:
            record = map(lambda r: r if r[0] != 'member' else ('uniqueMember', r[1]), record)
        return record

    def _createOrUpdate(self, member_list, ldap_conn):
        new_records = filter(lambda m: not ldap_conn.ldap_search(self._LDAP_TREE['accounts'],
                                                                 _ldap.SCOPE_ONELEVEL,
                                                                 filterstr='employeeNumber=%s' % m['employeeNumber'],
                                                                 attrsonly=1),
                             member_list)

        map(lambda c: ldap_conn.ldap_add('cn=%s,%s' % (self._createCN(c, ldap_conn), self._LDAP_TREE['accounts']),
                                         _modlist.addModlist(self._getLDAPCompatibleAccount(c),
                                                             ignore_attr_types=['cn'])),
            new_records)

        map(lambda u: ldap_conn.ldap_update('%s' % self._ldapCN(u['employeeNumber'], ldap_conn),
                                            _modlist.modifyModlist(ldap_conn.ldap_search(self._LDAP_TREE['accounts'],
                                                                                         _ldap.SCOPE_ONELEVEL,
                                                                                         filterstr='employeeNumber=%s'
                                                                                         % u['employeeNumber'])[0][1],
                                                                   self._getLDAPCompatibleAccount(u),
                                                                   ignore_attr_types=['userPassword', 'cn'])),
            filter(lambda m: cmp(dict(self._getLDAPCompatibleAccount(m)),
                                 ldap_conn.ldap_search(self._LDAP_TREE['accounts'],
                                                       _ldap.SCOPE_ONELEVEL,
                                                       filterstr='employeeNumber=%s' % m['employeeNumber'],
                                                       attrlist=['displayName', 'objectClass', 'employeeType',
                                                                 'mobile', 'employeeNumber', 'sn',
                                                                 'mail', 'givenName'])[0][1]),
                   member_list))

        return new_records

    def _sendNewAccountEmails(self, new_accounts, project_type, ldap_conn):
        map(lambda d: map(lambda t: self.mailer.sendCannedMail(t,
                                                               self.mailer.CANNED_MESSAGES['new_devel_account'] if
                                                               project_type in [self.SDA, self.OS_TENANT] else
                                                               self.mailer.CANNED_MESSAGES['new_partner_account'],
                                                               d['cn'][0]),
                          d['mail']),
            map(lambda a: ldap_conn.ldap_search('ou=accounts,dc=forgeservicelab,dc=fi',
                                                _ldap.SCOPE_ONELEVEL,
                                                filterstr='employeeNumber=%s' % a['employeeNumber'],
                                                attrlist=['cn', 'mail'])[0][1],
                new_accounts))

    # deprecated
    def _ensureButlerService(self, record):
        if not any([member.startswith('cn=butler.service') for
                    member in filter(lambda attribute: attribute[0] == 'uniqueMember', record)[0][1]]):
            record = map(lambda r: r if r[0] != 'uniqueMember'
                         else ('uniqueMember',
                               ['cn=butler.service,ou=accounts,dc=forgeservicelab,dc=fi'] + r[1]), record)
        return record

    def _addAndNotify(self, dn, tenant, ldap_conn):
        if 'Digile.Platform' in dn:
            self.updater\
                .addUserToProject(ldap_conn.ldap_search('cn=butler.service,ou=accounts,dc=forgeservicelab,dc=fi',
                                                        _ldap.SCOPE_BASE,
                                                        attrlist=['employeeNumber'])[0][1]['employeeNumber'][0],
                                  tenant)
            if not any([member.startswith('cn=butler.service') for member in tenant['uniqueMember']]):
                tenant['uniqueMember'] += ['cn=butler.service,ou=accounts,dc=forgeservicelab,dc=fi']

        ldap_tenant = self._getLDAPCompatibleProject(tenant, 'groupOfUniqueNames', ldap_conn)
        ldap_conn.ldap_add(dn, _modlist.addModlist(ldap_tenant))

        map(lambda ml: map(lambda e: self.mailer.sendCannedMail(e,
                                                                self.mailer.CANNED_MESSAGES['added_to_tenant'],
                                                                ldap_tenant['cn']),
                           ml),
            [ldap_conn.ldap_search(s, _ldap.SCOPE_BASE,
                                   attrlist=['mail'])[0][1]['mail'] for s in ldap_tenant['uniqueMember']])

    def _createTenants(self, tenant_list, project, ldap_conn):
        if tenant_list:
            map(lambda t: self._sendNewAccountEmails(self._createOrUpdate(t['member'], ldap_conn),
                                                     self.OS_TENANT, ldap_conn), tenant_list)
            map(lambda c: self._addAndNotify('cn=%s,cn=%s,%s' % (c['cn'], project['cn'], self._LDAP_TREE['projects']),
                                             c, ldap_conn),
                tenant_list)
        else:
            insightly_tenant = self.updater.createDefaultTenantFor(project)
            tenant = project.copy()
            tenant['o'] = str(insightly_tenant['PROJECT_ID'])
            tenant['uniqueMember'] = tenant.pop('owner', [])
            tenant.pop('seeAlso')
            self._sendNewAccountEmails(self._createOrUpdate(tenant['uniqueMember'], ldap_conn),
                                       self.OS_TENANT, ldap_conn)
            self._addAndNotify('cn=%(cn)s,cn=%(cn)s,%(sf)s' %
                               {'cn': project['cn'], 'sf': self._LDAP_TREE['projects']}, tenant, ldap_conn)

    def _create(self, project, project_type, ldap_conn):
        self._sendNewAccountEmails(self._createOrUpdate(project['member'], ldap_conn), project_type, ldap_conn)

        ldap_conn.ldap_add(
            'cn=%s,%s' % (project['cn'], self._LDAP_TREE['projects']),
            _modlist.addModlist(self._getLDAPCompatibleProject(project, 'groupOfNames', ldap_conn)))

        if project_type in [self.SDA, self.FPA_CRA]:
            self._createTenants(project['tenants'], project, ldap_conn)

        self.updater.updateProject(project, status=self.updater.STATUS_RUNNING)

        map(lambda a: map(lambda m: self.mailer.sendCannedMail(m, self.mailer.CANNED_MESSAGES['notify_admin_contact'],
                                                               a['displayName']),
                          a['mail']),
            project['seeAlso'])

        map(lambda a: map(lambda m: self.mailer.sendCannedMail(m, self.mailer.CANNED_MESSAGES['added_to_project'],
                                                               project['cn']), a['mail']), project['member'])

    def _updateAndNotify(self, dn, record, ldap_conn, is_tenant=False):
        ldap_record = ldap_conn.ldap_search(dn, _ldap.SCOPE_BASE)[0][1]
        dict_record = self._getLDAPCompatibleProject(record,
                                                     'groupOfUniqueNames' if is_tenant else 'groupOfNames',
                                                     ldap_conn)

        if cmp(dict_record, ldap_record):
            ldap_conn.ldap_update(dn, _modlist.modifyModlist(ldap_record, dict_record))
            new_users = filter(lambda m: m not in (ldap_record['uniqueMember'] if 'uniqueMember' in ldap_record.keys()
                                                   else ldap_record['member']),
                               (dict_record['uniqueMember'] if 'uniqueMember' in dict_record.keys()
                                   else dict_record['member']))
            gone_users = filter(lambda m: m not in (dict_record['uniqueMember'] if 'uniqueMember' in dict_record.keys()
                                                    else dict_record['member']),
                                (ldap_record['uniqueMember'] if 'uniqueMember' in ldap_record.keys()
                                 else ldap_record['member']))

            if any(member_attribute in dict_record.keys() for member_attribute in ['member', 'uniqueMember']):
                map(lambda email_list: map(lambda e: self.mailer
                                                         .sendCannedMail(e,
                                                                         self.mailer.CANNED_MESSAGES['added_to_tenant']
                                                                         if any(self.OS_TENANT in s for s in
                                                                                dict_record['description']) else
                                                                         self.mailer.CANNED_MESSAGES[
                                                                             'added_to_project'],
                                                                         dict_record['cn'][0]), email_list),
                    map(lambda s: ldap_conn.ldap_search(s, _ldap.SCOPE_BASE, attrlist=['mail'])[0][1]['mail'],
                        new_users))
                map(lambda email_list: map(lambda e: self.mailer
                                           .sendCannedMail(e,
                                                           self.mailer.CANNED_MESSAGES[
                                                               'deleted_from_tenant']
                                                           if any(self.OS_TENANT in s for s in
                                                                  dict_record['description']) else
                                                           self.mailer.CANNED_MESSAGES[
                                                               'deleted_from_project'],
                                                           dict_record['cn'][0]), email_list),
                    map(lambda s: ldap_conn.ldap_search(s, _ldap.SCOPE_BASE, attrlist=['mail'])[0][1]['mail'],
                        gone_users))

    def _updateTenants(self, tenant_list, project, ldap_conn):
        map(lambda t: self._sendNewAccountEmails(self._createOrUpdate(t['member'], ldap_conn),
                                                 self.OS_TENANT, ldap_conn), tenant_list)

        ldap_tenant_cns = [cn[1]['cn'][0] for cn in ldap_conn.ldap_search('cn=%s,%s' %
                                                                          (project['cn'],
                                                                           self._LDAP_TREE['projects']),
                                                                          _ldap.SCOPE_ONELEVEL, attrlist=['cn'])]

        new_tenants = filter(lambda t: t['cn'] not in ldap_tenant_cns, tenant_list)
        removed_tenant_cns = filter(lambda cn: cn not in [tenant['cn'] for tenant in tenant_list], ldap_tenant_cns)

        if new_tenants or not tenant_list:
            self._createTenants(new_tenants, project, ldap_conn)

        if removed_tenant_cns:
            map(lambda cn: ldap_conn.ldap_delete('cn=%s,cn=%s,%s' % (cn, project['cn'], self._LDAP_TREE['projects'])),
                removed_tenant_cns)

        map(lambda u: self._updateAndNotify('cn=%s,cn=%s,%s' % (u['cn'], project['cn'], self._LDAP_TREE['projects']),
                                            u, ldap_conn, is_tenant=True),
            filter(lambda nonews: nonews not in new_tenants,
                   filter(lambda t: ldap_conn.ldap_search('cn=%s,cn=%s,%s' %
                                                          (t['cn'], project['cn'],
                                                           self._LDAP_TREE['projects']),
                                                          _ldap.SCOPE_BASE), tenant_list)))

    def _update(self, project, project_type, ldap_conn):
        ldap_record = ldap_conn.ldap_search('cn=%s,%s' % (project['cn'], self._LDAP_TREE['projects']),
                                            _ldap.SCOPE_BASE)

        if ldap_record:
            self._sendNewAccountEmails(self._createOrUpdate(project['member'], ldap_conn), project_type, ldap_conn)
            self._updateAndNotify('cn=%s,%s' % (project['cn'], self._LDAP_TREE['projects']),
                                  project,
                                  #   map(lambda t: (_ldap.MOD_REPLACE, t[0], t[1]),
                                  #       self._createRecord(project, ldap_conn)),
                                  ldap_conn)
            if project_type in [self.SDA, self.FPA_CRA]:
                self._updateTenants(project['tenants'], project, ldap_conn)
        else:
            self._create(project, project_type, ldap_conn)

    def _deleteTenants(self, tenant_list, project, ldap_conn):
        former_members = []
        map(lambda tenant: members.extend(ldap_conn.ldap_search(tenant, _ldap.SCOPE_BASE,
                                                                attrlist=['uniqueMember'])[0][1]['uniqueMember']),
            tenant_list)

        map(lambda tenant: ldap_conn.ldap_delete(tenant), tenant_list)

    def _delete(self, project, project_type, ldap_conn):
        tenant_list = ldap_conn.ldap_search('cn=%s,' % project['cn'] + self._LDAP_TREE['projects'],
                                            _ldap.SCOPE_SUBORDINATE, attrlist=['o'])
        for tenant in tenant_list or []:
            tenant[1]['o'] = tenant[1]['o'][0]

        map(lambda tenant: ldap_conn.ldap_delete(tenant[0]), tenant_list or [])
        ldap_conn.ldap_delete('cn=%s,%s' % (project['cn'], self._LDAP_TREE['projects']))

        map(lambda tenant: self.updater.updateProject(tenant[1], updateStage=False,
                                                      status=self.updater.STATUS_COMPLETED), tenant_list or [])
        self.updater.updateProject(project, updateStage=False, status=self.updater.STATUS_COMPLETED)

    _actions = {
        ACTION_CREATE: _create,
        ACTION_DELETE: _delete,
        ACTION_UPDATE: _update
    }

    def Action(self, action, data_list, ldap_conn):
        """Perform a CRUD action against LDAP.

        Triggers the generation of LDAP payload and executes the requested action against the LDAP connection.

        Args:
            action (str): The action to perform, one of ACTION_CREATE, ACTION_DELETE or ACTION_UPDATE.
            data_list (List): A list of the elements to use as payload for the CRUD action against LDAP.
            ldap_conn (ForgeLDAP): An initialized LDAP connection to perform actions against.
        """
        map(lambda k: map(lambda p: self._actions[action](self, p, k, ldap_conn), data_list[k]), data_list.keys())
        self._pruneAccounts(ldap_conn)
