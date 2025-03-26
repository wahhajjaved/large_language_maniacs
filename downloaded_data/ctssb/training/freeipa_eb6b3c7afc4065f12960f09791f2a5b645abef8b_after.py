# Authors:
#   Jason Gerard DeRose <jderose@redhat.com>
#   Pavel Zuna <pzuna@redhat.com>
#
# Copyright (C) 2008  Red Hat
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
"""
Users

Manage user entries. All users are POSIX users.

IPA supports a wide range of username formats, but you need to be aware of any
restrictions that may apply to your particular environment. For example,
usernames that starts with a digit or usernames that exceed a certain length
may cause problems for some UNIX systems.
Use 'ipa config-mod' to change the username format allowed by IPA tools.

Disabling a user account prevents that user from obtaining new Kerberos
credentials. It does not invalidate any credentials that have already
been issued.

Password management is not a part of this module. For more information
about this topic please see: ipa help passwd

EXAMPLES:

 Add a new user:
   ipa user-add --first=Tim --last=User --password tuser1

 Find all users whose entries include the string "Tim":
   ipa user-find Tim

 Find all users with "Tim" as the first name:
   ipa user-find --first=Tim

 Disable a user account:
   ipa user-disable tuser1

 Enable a user account:
   ipa user-enable tuser1

 Delete a user:
   ipa user-del tuser1
"""

from ipalib import api, errors
from ipalib import Flag, Int, Password, Str, Bool
from ipalib.plugins.baseldap import *
from ipalib import _, ngettext
from ipalib.request import context
from time import gmtime, strftime

def validate_nsaccountlock(entry_attrs):
    if 'nsaccountlock' in entry_attrs:
        if not isinstance(entry_attrs['nsaccountlock'], basestring):
            raise errors.OnlyOneValueAllowed(attr='nsaccountlock')
        if entry_attrs['nsaccountlock'].lower() not in ('true','false'):
            raise errors.ValidationError(name='nsaccountlock', error='must be TRUE or FALSE')

class user(LDAPObject):
    """
    User object.
    """
    container_dn = api.env.container_user
    object_name = 'user'
    object_name_plural = 'users'
    object_class = ['posixaccount']
    object_class_config = 'ipauserobjectclasses'
    possible_objectclasses = ['meporiginentry']
    search_attributes_config = 'ipausersearchfields'
    default_attributes = [
        'uid', 'givenname', 'sn', 'homedirectory', 'loginshell', 'ou',
        'telephonenumber', 'title', 'memberof', 'nsaccountlock',
        'memberofindirect',
    ]
    uuid_attribute = 'ipauniqueid'
    attribute_members = {
        'memberof': ['group', 'netgroup', 'role'],
        'memberofindirect': ['group', 'netgroup', 'role'],
    }
    rdnattr = 'uid'
    bindable = True

    label = _('Users')

    takes_params = (
        Str('uid',
            pattern='^[a-zA-Z0-9_.][a-zA-Z0-9_.-]{0,252}[a-zA-Z0-9_.$-]?$',
            pattern_errmsg='may only include letters, numbers, _, -, . and $',
            maxlength=255,
            cli_name='login',
            label=_('User login'),
            primary_key=True,
            default_from=lambda givenname, sn: givenname[0] + sn,
            normalizer=lambda value: value.lower(),
        ),
        Str('givenname',
            cli_name='first',
            label=_('First name'),
        ),
        Str('sn',
            cli_name='last',
            label=_('Last name'),
        ),
        Str('cn?',
            label=_('Full name'),
            default_from=lambda givenname, sn: '%s %s' % (givenname, sn),
            autofill=True,
        ),
        Str('displayname?',
            label=_('Display name'),
            default_from=lambda givenname, sn: '%s %s' % (givenname, sn),
            autofill=True,
        ),
        Str('initials?',
            label=_('Initials'),
            default_from=lambda givenname, sn: '%c%c' % (givenname[0], sn[0]),
            autofill=True,
        ),
        Str('homedirectory?',
            cli_name='homedir',
            label=_('Home directory'),
            default_from=lambda uid: '/home/%s' % uid,
        ),
        Str('gecos?',
            label=_('GECOS field'),
            default_from=lambda uid: uid,
            autofill=True,
        ),
        Str('loginshell?',
            cli_name='shell',
            label=_('Login shell'),
            default=u'/bin/sh',
        ),
        Str('krbprincipalname?',
            cli_name='principal',
            label=_('Kerberos principal'),
            default_from=lambda uid: '%s@%s' % (uid, api.env.realm),
            autofill=True,
            flags=['no_update'],
        ),
        Str('mail*',
            cli_name='email',
            label=_('Email address'),
        ),
        Password('userpassword?',
            cli_name='password',
            label=_('Password'),
            doc=_('Prompt to set the user password'),
            # FIXME: This is temporary till bug is fixed causing updates to
            # bomb out via the webUI.
            exclude='webui',
        ),
        Int('uidnumber?',
            cli_name='uid',
            label=_('UID'),
            doc=_('User ID Number (system will assign one if not provided)'),
            autofill=True,
            default=999,
            minvalue=1,
        ),
        Int('gidnumber?',
            label=_('GID'),
            doc=_('Group ID Number'),
            default_from=lambda uid: uid,
        ),
        Str('street?',
            cli_name='street',
            label=_('Street address'),
        ),
        Str('l?',
            cli_name='city',
            label=_('City'),
        ),
        Str('st?',
            cli_name='state',
            label=_('State/Province'),
        ),
        Int('postalcode?',
            label=_('ZIP'),
        ),
        Str('telephonenumber*',
            cli_name='phone',
            label=_('Telephone Number')
        ),
        Str('mobile*',
            label=_('Mobile Telephone Number')
        ),
        Str('pager*',
            label=_('Pager Number')
        ),
        Str('facsimiletelephonenumber*',
            cli_name='fax',
            label=_('Fax Number'),
        ),
        Str('ou?',
            cli_name='orgunit',
            label=_('Org. Unit'),
        ),
        Str('title?',
            label=_('Job Title'),
        ),
        Str('manager?',
            label=_('Manager'),
        ),
        Str('carlicense?',
            label=_('Car License'),
        ),
        Bool('nsaccountlock?',
            label=_('Account disabled'),
            flags=['no_create', 'no_update', 'no_search'],
        ),
    )

    def _normalize_email(self, email, config=None):
        if not config:
            config = self.backend.get_ipa_config()[1]

        # check if default email domain should be added
        if email and 'ipadefaultemaildomain' in config:
            norm_email = []
            if not isinstance(email, (list, tuple)):
                email = [email]
            for m in email:
                if isinstance(m, basestring) and m.find('@') == -1:
                    norm_email.append(m + u'@' + config['ipadefaultemaildomain'][0])
                else:
                    norm_email.append(m)
            return norm_email

        return email

api.register(user)


class user_add(LDAPCreate):
    """
    Add a new user.
    """

    msg_summary = _('Added user "%(value)s"')

    def pre_callback(self, ldap, dn, entry_attrs, attrs_list, *keys, **options):
        try:
            # The Managed Entries plugin will allow a user to be created
            # even if a group has a duplicate name. This would leave a user
            # without a private group. Check for both the group and the user.
            self.api.Command['group_show'](keys[-1])
            try:
                self.api.Command['user_show'](keys[-1])
                raise errors.DuplicateEntry()
            except errors.NotFound:
                raise errors.ManagedGroupExistsError(group=keys[-1])
        except errors.NotFound:
            pass
        validate_nsaccountlock(entry_attrs)
        config = ldap.get_ipa_config()[1]
        if 'ipamaxusernamelength' in config:
            if len(keys[-1]) > int(config.get('ipamaxusernamelength')[0]):
                raise errors.ValidationError(
                    name=self.obj.primary_key.cli_name,
                    error=_('can be at most %(len)d characters') % dict(
                        len = int(config.get('ipamaxusernamelength')[0])
                    )
                )
        entry_attrs.setdefault('loginshell', config.get('ipadefaultloginshell'))
        # hack so we can request separate first and last name in CLI
        full_name = '%s %s' % (entry_attrs['givenname'], entry_attrs['sn'])
        entry_attrs.setdefault('cn', full_name)
        if 'homedirectory' not in entry_attrs:
            # get home's root directory from config
            homes_root = config.get('ipahomesrootdir', '/home')[0]
            # build user's home directory based on his uid
            home_dir = '%s/%s' % (homes_root, keys[-1])
            home_dir = home_dir.replace('//', '/').rstrip('/')
            entry_attrs['homedirectory'] = home_dir
        entry_attrs.setdefault('krbpwdpolicyreference', 'cn=global_policy,cn=%s,cn=kerberos,%s' % (api.env.realm, api.env.basedn))

        if ldap.has_upg():
            # User Private Groups - uidNumber == gidNumber
            entry_attrs['gidnumber'] = entry_attrs['uidnumber']
        else:
            # we're adding new users to a default group, get its gidNumber
            # get default group name from config
            def_primary_group = config.get('ipadefaultprimarygroup')
            group_dn = self.api.Object['group'].get_dn(def_primary_group)
            try:
                (group_dn, group_attrs) = ldap.get_entry(group_dn, ['gidnumber'])
            except errors.NotFound:
                error_msg = 'Default group for new users not found.'
                raise errors.NotFound(reason=error_msg)
            entry_attrs['gidnumber'] = group_attrs['gidnumber']

        if 'mail' in entry_attrs:
            entry_attrs['mail'] = self.obj._normalize_email(entry_attrs['mail'], config)

        return dn

    def post_callback(self, ldap, dn, entry_attrs, *keys, **options):
        config = ldap.get_ipa_config()[1]
        # add the user we just created into the default primary group
        def_primary_group = config.get('ipadefaultprimarygroup')
        group_dn = self.api.Object['group'].get_dn(def_primary_group)
        ldap.add_entry_to_group(dn, group_dn)
        return dn

api.register(user_add)


class user_del(LDAPDelete):
    """
    Delete a user.
    """

    msg_summary = _('Deleted user "%(value)s"')

    def post_callback(self, ldap, dn, *keys, **options):
        return True

api.register(user_del)


class user_mod(LDAPUpdate):
    """
    Modify a user.
    """

    msg_summary = _('Modified user "%(value)s"')

    def pre_callback(self, ldap, dn, entry_attrs, attrs_list, *keys, **options):
        if 'mail' in entry_attrs:
            entry_attrs['mail'] = self.obj._normalize_email(entry_attrs['mail'])
        validate_nsaccountlock(entry_attrs)
        return dn

    def post_callback(self, ldap, dn, entry_attrs, *keys, **options):
        if not 'nsaccountlock' in entry_attrs:
            entry_attrs['nsaccountlock'] = [u'False']
        return dn

api.register(user_mod)


class user_find(LDAPSearch):
    """
    Search for users.
    """
    member_attributes = ['memberof']

    takes_options = LDAPSearch.takes_options + (
        Flag('whoami',
            label=_('Self'),
            doc=_('Display user record for current Kerberos principal'),
        ),
    )

    def pre_callback(self, ldap, filter, attrs_list, base_dn, scope, *keys, **options):
        if options.get('whoami'):
            return ("(&(objectclass=posixaccount)(krbprincipalname=%s))"%\
                        getattr(context, 'principal'), base_dn, scope)

        return (filter, base_dn, scope)

    def post_callback(self, ldap, entries, truncated, *args, **options):
        for entry in entries:
            (dn, attrs) = entry
            if not 'nsaccountlock' in attrs:
                attrs['nsaccountlock'] = [u'False']

    msg_summary = ngettext(
        '%(count)d user matched', '%(count)d users matched', 0
    )

api.register(user_find)


class user_show(LDAPRetrieve):
    """
    Display information about a user.
    """
    def post_callback(self, ldap, dn, entry_attrs, *keys, **options):
        if not 'nsaccountlock' in entry_attrs:
            entry_attrs['nsaccountlock'] = [u'False']
        return dn

api.register(user_show)


class user_disable(LDAPQuery):
    """
    Disable user account.
    """

    has_output = output.standard_value
    msg_summary = _('Disabled user account "%(value)s"')

    def execute(self, *keys, **options):
        ldap = self.obj.backend

        dn = self.obj.get_dn(*keys, **options)

        ldap.deactivate_entry(dn)

        return dict(
            result=True,
            value=keys[0],
        )

api.register(user_disable)


class user_enable(LDAPQuery):
    """
    Enable user account.
    """

    has_output = output.standard_value
    msg_summary = _('Enabled user account "%(value)s"')

    def execute(self, *keys, **options):
        ldap = self.obj.backend

        dn = self.obj.get_dn(*keys, **options)

        ldap.activate_entry(dn)

        return dict(
            result=True,
            value=keys[0],
        )

api.register(user_enable)

class user_unlock(LDAPQuery):
    """
    Lock user account

    - locked account can't log in against Kerberos and must be unlocked by admin
    - account can be locked e.g. by inputting wrong password too many times
    """
    has_output = output.standard_value
    msg_summary = _('Unlocked account "%(value)s"')

    def execute(self, *keys, **options):
        dn = self.obj.get_dn(*keys, **options)
        entry_attrs = {'krbLastAdminUnlock': strftime("%Y%m%d%H%M%SZ",gmtime()), 'krbLoginFailedCount': '0'}

        self.obj.backend.update_entry(dn, entry_attrs)

        return dict(
            result=True,
            value=keys[0],
        )

api.register(user_unlock)
