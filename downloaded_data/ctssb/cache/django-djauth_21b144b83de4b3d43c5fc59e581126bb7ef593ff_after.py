# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib.auth.models import User, Group

import ldap
import ldap.modlist as modlist
import logging
logger = logging.getLogger(__name__)

class LDAPManager(object):

    def __init__(self, protocol=settings.LDAP_PROTOCOL,
                 port=settings.LDAP_PORT,server=settings.LDAP_SERVER,
                 user=settings.LDAP_USER,password=settings.LDAP_PASS,
                 base=settings.LDAP_BASE):
        # Authenticate the base user so we can search
        try:
            self.l = ldap.initialize(
                '%s://%s:%s' % (protocol,server,port)
            )
            self.l.protocol_version = ldap.VERSION3
            # not certain if this is necessary but passwd_s is killing me
            #self.l.set_option(ldap.OPT_PROTOCOL_VERSION,ldap.VERSION3)
            # logging
            #ldap.set_option(ldap.OPT_DEBUG_LEVEL,255)
            self.l.simple_bind_s(user,password)
            self.base = base
        except ldap.LDAPError, e:
            raise Exception(e)

    def unbind(self):
        #
        # Disconnect and free resources when done
        #
        self.l.unbind_s()

    def bind(self, dn, password):

        # Attempt to bind to the user's DN.
        self.l.simple_bind_s(dn,password)

    def create(self, person):
        """
        Creates a new LDAP user.
        Takes as argument a dictionary with the following key/value pairs:

        objectclass                 ["User","etc"]
        givenName                   [first name]
        sn                          [last name]
        carthageDob                 [date of birth]
        settings.LDAP_ID_ATTR       [college ID]
        cn                          [we use email for username]
        mail                        [email]
        userPassword                [password]
        carthageFacultyStatus       [faculty]
        carthageStaffStatus         [staff]
        carthageStudentStatus       [student]
        carthageFormerStudentStatus [alumni]
        carthageOtherStatus         [trustees etc]
        """
        user = modlist.addModlist(person)

        dn = 'cn=%s,%s' % (person["cn"],self.base)
        self.l.add_s(dn, user)
        return self.search(person[settings.LDAP_ID_ATTR])

    def dj_create(self, data, auth_user_pk=False):
        # We create a User object for LDAP users so we can get
        # permissions, however we -don't- want them to be able to
        # login without going through LDAP with this user. So we
        # effectively disable their non-LDAP login ability by
        # setting it to a random password that is not given to
        # them. In this way, static users that don't go through
        # ldap can still login properly, and LDAP users still
        # have a User object.

        data = data[0][1]
        email = data['mail'][0]
        # if auth_user_pk is True, then we use the primary key from the database
        # rather than the LDAP user ID
        if auth_user_pk:
            uid = None
        else:
            uid = data[settings.LDAP_ID_ATTR][0]
        cn = data['cn'][0]
        password = User.objects.make_random_password(length=24)
        user = User.objects.create(pk=uid,username=cn,email=email)
        user.set_password(password)
        user.first_name = data['givenName'][0]
        user.last_name = data['sn'][0]
        user.save()
        # add to groups
        for key, val in settings.LDAP_GROUPS.items():
            group = data.get(key)
            if group and group[0] == 'A':
                g = Group.objects.get(name__iexact=key)
                g.user_set.add(user)
        return user

    def update_password(self, dn, password):
        """
        Changes an LDAP user's password.
        takes a dn and a password.

        The passwd_s() method and its asynchronous counterpart, passwd()
        take three arguments:

        The DN of the record to change.
        The old password (or None if an admin user makes the change)
        The new password

        If the passwd_s change is successful, it returns a tuple with the
        status code (ldap.RES_EXTENDED, which is the integer 120), and an
        empty list:

        (120, [])

        passwd returns a result ID code.

        Novell do not see to support 3062 so passwd & passwd_s fail
        with a PROTOCOL_ERROR. Returns 2 if using passwd, which means
        the same thing.
        """
        #print "protocol version = %s" % self.l.protocol_version
        #print ldap.TLS_AVAIL
        #print "require cert = %s" % ldap.OPT_X_TLS_REQUIRE_CERT
        status = self.l.passwd_s( dn, None, password )

        return status

    def modify(self, dn, name, value):
        """
        Modifies an LDAP user's attribute.
        """

        #ldif = modlist.modifyModlist(old,new)
        # Do the actual modification
        #l.modify_s(dn,ldif)
        return self.l.modify_s(dn, [(ldap.MOD_REPLACE, name, str(value))])

    def delete(self, person):
        """
        Deletes an LDAP user.
        Takes as argument a dictionary with the following key/value pairs:

        cn              [username]
        """
        dn = "cn=%s,%s" % (person["cn"],self.base)
        try:
            self.l.delete_s(dn)
        except ldap.LDAPError, e:
            raise Exception(e)

    def search(self, val, field=settings.LDAP_ID_ATTR, ret=settings.LDAP_RETURN):
        """
        Searches for an LDAP user.
        Takes as argument a value and a valid unique field from
        the schema (i.e. LDAP_ID_ATTR, cn, mail).
        Returns None or a list with dn tuple and a dictionary with the
        following key/value pairs:

        givenName               [first name]
        sn                      [last name]
        cn                      [username]
        carthageDob             [date of birth]
        settings.LDAP_ID_ATTR   [college ID]
        carthageStaffStatus     [staff?]
        carthageOtherStatus     [alumni?]
        carthageFacultyStatus   [faculty?]
        carthageStudentStatus   [student?]
        mail                    [email]
        """

        valid = ["cn",settings.LDAP_ID_ATTR,"mail"]
        if field not in valid:
            return None
        philter = "(&(objectclass=%s) (%s=%s))" % (
            settings.LDAP_OBJECT_CLASS,field,val
        )

        result_id = self.l.search(
            self.base,ldap.SCOPE_SUBTREE,philter,ret
        )
        result_type, result_data = self.l.result(result_id, 0)
        # If the user does not exist in LDAP, Fail.
        if (len(result_data) != 1):
            return None
        else:
            return result_data
