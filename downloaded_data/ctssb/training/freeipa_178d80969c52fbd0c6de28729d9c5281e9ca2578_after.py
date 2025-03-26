#
# Copyright (C) 2018  FreeIPA Contributors see COPYING for license
#
"""Misc test for 'ipa' CLI regressions
"""
from __future__ import absolute_import

import base64
import re
import os
import logging
import random
import ssl
from itertools import chain, repeat
import textwrap
import time
import paramiko
import pytest
from subprocess import CalledProcessError

from cryptography.hazmat.backends import default_backend
from cryptography import x509
from datetime import datetime, timedelta

from ipalib.constants import IPAAPI_USER

from ipaplatform.paths import paths

from ipapython.dn import DN

from ipapython.certdb import get_ca_nickname

from ipatests.test_integration.base import IntegrationTest

from ipatests.pytest_ipa.integration import tasks
from ipaplatform.tasks import tasks as platform_tasks
from ipatests.create_external_ca import ExternalCA
from ipatests.test_ipalib.test_x509 import good_pkcs7, badcert
from ipapython.ipautil import realm_to_suffix, ipa_generate_password
from ipaserver.install.installutils import realm_to_serverid

logger = logging.getLogger(__name__)

# from ipaserver.masters
CONFIGURED_SERVICE = u'configuredService'
ENABLED_SERVICE = u'enabledService'
HIDDEN_SERVICE = u'hiddenService'

DIRSRV_SLEEP = 5

isrgrootx1 = (
    b'-----BEGIN CERTIFICATE-----\n'
    b'MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw\n'
    b'TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\n'
    b'cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4\n'
    b'WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu\n'
    b'ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY\n'
    b'MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc\n'
    b'h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+\n'
    b'0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U\n'
    b'A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW\n'
    b'T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH\n'
    b'B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC\n'
    b'B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv\n'
    b'KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn\n'
    b'OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn\n'
    b'jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw\n'
    b'qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI\n'
    b'rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV\n'
    b'HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq\n'
    b'hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL\n'
    b'ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ\n'
    b'3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK\n'
    b'NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5\n'
    b'ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur\n'
    b'TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC\n'
    b'jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc\n'
    b'oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq\n'
    b'4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA\n'
    b'mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d\n'
    b'emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=\n'
    b'-----END CERTIFICATE-----\n'
)
isrgrootx1_nick = 'CN=ISRG Root X1,O=Internet Security Research Group,C=US'

# This sub-CA expires on Oct 6, 2021 but it is functional for our
# purposes of testing, the date validity is not considered (yet).
letsencryptauthorityx3 = (
    b'-----BEGIN CERTIFICATE-----\n'
    b'MIIFjTCCA3WgAwIBAgIRANOxciY0IzLc9AUoUSrsnGowDQYJKoZIhvcNAQELBQAw\n'
    b'TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\n'
    b'cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTYxMDA2MTU0MzU1\n'
    b'WhcNMjExMDA2MTU0MzU1WjBKMQswCQYDVQQGEwJVUzEWMBQGA1UEChMNTGV0J3Mg\n'
    b'RW5jcnlwdDEjMCEGA1UEAxMaTGV0J3MgRW5jcnlwdCBBdXRob3JpdHkgWDMwggEi\n'
    b'MA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCc0wzwWuUuR7dyXTeDs2hjMOrX\n'
    b'NSYZJeG9vjXxcJIvt7hLQQWrqZ41CFjssSrEaIcLo+N15Obzp2JxunmBYB/XkZqf\n'
    b'89B4Z3HIaQ6Vkc/+5pnpYDxIzH7KTXcSJJ1HG1rrueweNwAcnKx7pwXqzkrrvUHl\n'
    b'Npi5y/1tPJZo3yMqQpAMhnRnyH+lmrhSYRQTP2XpgofL2/oOVvaGifOFP5eGr7Dc\n'
    b'Gu9rDZUWfcQroGWymQQ2dYBrrErzG5BJeC+ilk8qICUpBMZ0wNAxzY8xOJUWuqgz\n'
    b'uEPxsR/DMH+ieTETPS02+OP88jNquTkxxa/EjQ0dZBYzqvqEKbbUC8DYfcOTAgMB\n'
    b'AAGjggFnMIIBYzAOBgNVHQ8BAf8EBAMCAYYwEgYDVR0TAQH/BAgwBgEB/wIBADBU\n'
    b'BgNVHSAETTBLMAgGBmeBDAECATA/BgsrBgEEAYLfEwEBATAwMC4GCCsGAQUFBwIB\n'
    b'FiJodHRwOi8vY3BzLnJvb3QteDEubGV0c2VuY3J5cHQub3JnMB0GA1UdDgQWBBSo\n'
    b'SmpjBH3duubRObemRWXv86jsoTAzBgNVHR8ELDAqMCigJqAkhiJodHRwOi8vY3Js\n'
    b'LnJvb3QteDEubGV0c2VuY3J5cHQub3JnMHIGCCsGAQUFBwEBBGYwZDAwBggrBgEF\n'
    b'BQcwAYYkaHR0cDovL29jc3Aucm9vdC14MS5sZXRzZW5jcnlwdC5vcmcvMDAGCCsG\n'
    b'AQUFBzAChiRodHRwOi8vY2VydC5yb290LXgxLmxldHNlbmNyeXB0Lm9yZy8wHwYD\n'
    b'VR0jBBgwFoAUebRZ5nu25eQBc4AIiMgaWPbpm24wDQYJKoZIhvcNAQELBQADggIB\n'
    b'ABnPdSA0LTqmRf/Q1eaM2jLonG4bQdEnqOJQ8nCqxOeTRrToEKtwT++36gTSlBGx\n'
    b'A/5dut82jJQ2jxN8RI8L9QFXrWi4xXnA2EqA10yjHiR6H9cj6MFiOnb5In1eWsRM\n'
    b'UM2v3e9tNsCAgBukPHAg1lQh07rvFKm/Bz9BCjaxorALINUfZ9DD64j2igLIxle2\n'
    b'DPxW8dI/F2loHMjXZjqG8RkqZUdoxtID5+90FgsGIfkMpqgRS05f4zPbCEHqCXl1\n'
    b'eO5HyELTgcVlLXXQDgAWnRzut1hFJeczY1tjQQno6f6s+nMydLN26WuU4s3UYvOu\n'
    b'OsUxRlJu7TSRHqDC3lSE5XggVkzdaPkuKGQbGpny+01/47hfXXNB7HntWNZ6N2Vw\n'
    b'p7G6OfY+YQrZwIaQmhrIqJZuigsrbe3W+gdn5ykE9+Ky0VgVUsfxo52mwFYs1JKY\n'
    b'2PGDuWx8M6DlS6qQkvHaRUo0FMd8TsSlbF0/v965qGFKhSDeQoMpYnwcmQilRh/0\n'
    b'ayLThlHLN81gSkJjVrPI0Y8xCVPB4twb1PFUd2fPM3sA1tJ83sZ5v8vgFv2yofKR\n'
    b'PB0t6JzUA81mSqM3kxl5e+IZwhYAyO0OTg3/fs8HqGTNKd9BqoUwSRBzp06JMg5b\n'
    b'rUCGwbCUDI0mxadJ3Bz4WxR6fyNpBK2yAinWEsikxqEt\n'
    b'-----END CERTIFICATE-----\n'
)
le_x3_nick = "CN=Let's Encrypt Authority X3,O=Let's Encrypt,C=US"


class TestIPACommand(IntegrationTest):
    """
    A lot of commands can be executed against a single IPA installation
    so provide a generic class to execute one-off commands that need to be
    tested without having to fire up a full server to run one command.
    """
    topology = 'line'

    @pytest.fixture
    def pwpolicy_global(self):
        """Fixture to change global password history policy and reset it"""
        tasks.kinit_admin(self.master)
        self.master.run_command(
            ["ipa", "pwpolicy-mod", "--history=5", "--minlife=0"],
        )
        yield
        self.master.run_command(
            ["ipa", "pwpolicy-mod", "--history=0", "--minlife=1"],
        )

    def get_cert_base64(self, host, path):
        """Retrieve cert and return content as single line, base64 encoded
        """
        cacrt = host.get_file_contents(path, encoding='ascii')
        cader = ssl.PEM_cert_to_DER_cert(cacrt)
        return base64.b64encode(cader).decode('ascii')

    def test_aes_sha_kerberos_enctypes(self):
        """Test AES SHA 256 and 384 Kerberos enctypes enabled

        AES SHA 256 and 384-bit enctypes supported by MIT kerberos but
        was not enabled in IPA. This test is to check if these types are
        enabled.

        related: https://pagure.io/freeipa/issue/8110
        """
        tasks.kinit_admin(self.master)
        dn = DN(("cn", self.master.domain.realm), ("cn", "kerberos"),
                realm_to_suffix(self.master.domain.realm))
        result = tasks.ldapsearch_dm(self.master, str(dn),
                                     ["krbSupportedEncSaltTypes"],
                                     scope="base")
        assert "aes128-sha2:normal" in result.stdout_text
        assert "aes128-sha2:special" in result.stdout_text
        assert "aes256-sha2:normal" in result.stdout_text
        assert "aes256-sha2:special" in result.stdout_text

    def test_certmap_match_issue7520(self):
        # https://pagure.io/freeipa/issue/7520
        tasks.kinit_admin(self.master)
        result = self.master.run_command(
            ['ipa', 'certmap-match', paths.IPA_CA_CRT],
            raiseonerr=False
        )
        assert result.returncode == 1
        assert not result.stderr_text
        assert "0 users matched" in result.stdout_text

        cab64 = self.get_cert_base64(self.master, paths.IPA_CA_CRT)
        result = self.master.run_command(
            ['ipa', 'certmap-match', '--certificate', cab64],
            raiseonerr=False
        )
        assert result.returncode == 1
        assert not result.stderr_text
        assert "0 users matched" in result.stdout_text

    def test_cert_find_issue7520(self):
        # https://pagure.io/freeipa/issue/7520
        tasks.kinit_admin(self.master)
        subject = 'CN=Certificate Authority,O={}'.format(
            self.master.domain.realm)

        # by cert file
        result = self.master.run_command(
            ['ipa', 'cert-find', '--file', paths.IPA_CA_CRT]
        )
        assert subject in result.stdout_text
        assert '1 certificate matched' in result.stdout_text

        # by base64 cert
        cab64 = self.get_cert_base64(self.master, paths.IPA_CA_CRT)
        result = self.master.run_command(
            ['ipa', 'cert-find', '--certificate', cab64]
        )
        assert subject in result.stdout_text
        assert '1 certificate matched' in result.stdout_text

    def test_add_permission_failure_issue5923(self):
        # https://pagure.io/freeipa/issue/5923
        # error response used to contain bytes instead of text

        tasks.kinit_admin(self.master)
        # neither privilege nor permission exists
        result = self.master.run_command(
            ["ipa", "privilege-add-permission", "loc",
             "--permission='System: Show IPA Locations"],
            raiseonerr=False
        )
        assert result.returncode == 2
        err = result.stderr_text.strip()
        assert err == "ipa: ERROR: loc: privilege not found"
        # add privilege
        result = self.master.run_command(
            ["ipa", "privilege-add", "loc"],
        )
        assert 'Added privilege "loc"' in result.stdout_text
        # permission is still missing
        result = self.master.run_command(
            ["ipa", "privilege-add-permission", "loc",
             "--permission='System: Show IPA Locations"],
            raiseonerr=False
        )
        assert result.returncode == 1
        assert "Number of permissions added 0" in result.stdout_text

    def test_change_sysaccount_password_issue7561(self):
        sysuser = 'system'
        original_passwd = 'Secret123'
        new_passwd = 'userPasswd123'

        master = self.master

        base_dn = str(master.domain.basedn)
        entry_ldif = textwrap.dedent("""
            dn: uid={sysuser},cn=sysaccounts,cn=etc,{base_dn}
            changetype: add
            objectclass: account
            objectclass: simplesecurityobject
            uid: {sysuser}
            userPassword: {original_passwd}
            passwordExpirationTime: 20380119031407Z
            nsIdleTimeout: 0
        """).format(
            base_dn=base_dn,
            original_passwd=original_passwd,
            sysuser=sysuser)
        tasks.ldapmodify_dm(master, entry_ldif)

        tasks.ldappasswd_sysaccount_change(sysuser, original_passwd,
                                           new_passwd, master)

    def get_krbinfo(self, user):
        base_dn = str(self.master.domain.basedn)
        result = tasks.ldapsearch_dm(
            self.master,
            'uid={user},cn=users,cn=accounts,{base_dn}'.format(
                user=user, base_dn=base_dn),
            ['krblastpwdchange', 'krbpasswordexpiration'],
            scope='base'
        )
        output = result.stdout_text.lower()

        # extract krblastpwdchange and krbpasswordexpiration
        krbchg_pattern = 'krblastpwdchange: (.+)\n'
        krbexp_pattern = 'krbpasswordexpiration: (.+)\n'
        krblastpwdchange = re.findall(krbchg_pattern, output)[0]
        krbexp = re.findall(krbexp_pattern, output)[0]
        return krblastpwdchange, krbexp

    def test_ldapmodify_password_issue7601(self):
        user = 'ipauser'
        original_passwd = 'Secret123'
        new_passwd = 'userPasswd123'
        new_passwd2 = 'mynewPwd123'
        master = self.master
        base_dn = str(master.domain.basedn)

        # Create a user with a password
        tasks.kinit_admin(master)
        add_password_stdin_text = "{pwd}\n{pwd}".format(pwd=original_passwd)
        master.run_command(['ipa', 'user-add', user,
                            '--first', user,
                            '--last', user,
                            '--password'],
                           stdin_text=add_password_stdin_text)
        # kinit as that user in order to modify the pwd
        user_kinit_stdin_text = "{old}\n%{new}\n%{new}\n".format(
            old=original_passwd,
            new=original_passwd)
        master.run_command(['kinit', user], stdin_text=user_kinit_stdin_text)
        # Retrieve krblastpwdchange and krbpasswordexpiration
        krblastpwdchange, krbexp = self.get_krbinfo(user)

        # sleep 1 sec (krblastpwdchange and krbpasswordexpiration have at most
        # a 1s precision)
        time.sleep(1)
        # perform ldapmodify on userpassword as dir mgr
        entry_ldif = textwrap.dedent("""
            dn: uid={user},cn=users,cn=accounts,{base_dn}
            changetype: modify
            replace: userpassword
            userpassword: {new_passwd}
        """).format(
            user=user,
            base_dn=base_dn,
            new_passwd=new_passwd)
        tasks.ldapmodify_dm(master, entry_ldif)

        # Test new password with kinit
        master.run_command(['kinit', user], stdin_text=new_passwd)

        # both should have changed
        newkrblastpwdchange, newkrbexp = self.get_krbinfo(user)
        assert newkrblastpwdchange != krblastpwdchange
        assert newkrbexp != krbexp

        # Now test passwd modif with ldappasswd
        time.sleep(1)
        master.run_command([
            paths.LDAPPASSWD,
            '-D', str(master.config.dirman_dn),
            '-w', master.config.dirman_password,
            '-a', new_passwd,
            '-s', new_passwd2,
            '-x', '-ZZ',
            '-H', 'ldap://{hostname}'.format(hostname=master.hostname),
            'uid={user},cn=users,cn=accounts,{base_dn}'.format(
                user=user, base_dn=base_dn)]
        )
        # Test new password with kinit
        master.run_command(['kinit', user], stdin_text=new_passwd2)

        # both should have changed
        newkrblastpwdchange2, newkrbexp2 = self.get_krbinfo(user)
        assert newkrblastpwdchange != newkrblastpwdchange2
        assert newkrbexp != newkrbexp2

    def test_change_sysaccount_pwd_history_issue7181(self, pwpolicy_global):
        """
        Test that a sysacount user maintains no password history
        because they do not have a Kerberos identity.
        """
        sysuser = 'sysuser'
        original_passwd = 'Secret123'
        new_passwd = 'userPasswd123'

        master = self.master

        # Add a system account and add it to a group managed by the policy
        base_dn = str(master.domain.basedn)  # pylint: disable=no-member
        entry_ldif = textwrap.dedent("""
            dn: uid={account_name},cn=sysaccounts,cn=etc,{base_dn}
            changetype: add
            objectclass: account
            objectclass: simplesecurityobject
            uid: {account_name}
            userPassword: {original_passwd}
            passwordExpirationTime: 20380119031407Z
            nsIdleTimeout: 0
        """).format(
            account_name=sysuser,
            base_dn=base_dn,
            original_passwd=original_passwd)

        tasks.ldapmodify_dm(master, entry_ldif)

        # Now change the password. It should succeed since password
        # policy doesn't apply to non-Kerberos users.
        tasks.ldappasswd_sysaccount_change(sysuser, original_passwd,
                                           new_passwd, master)
        tasks.ldappasswd_sysaccount_change(sysuser, new_passwd,
                                           original_passwd, master)
        tasks.ldappasswd_sysaccount_change(sysuser, original_passwd,
                                           new_passwd, master)

    def test_change_user_pwd_history_issue7181(self, pwpolicy_global):
        """
        Test that password history for a normal IPA user is honored.
        """
        user = 'user1'
        original_passwd = 'Secret123'
        new_passwd = 'userPasswd123'

        master = self.master

        tasks.user_add(master, user, password=original_passwd)

        tasks.ldappasswd_user_change(user, original_passwd,
                                     new_passwd, master)
        tasks.ldappasswd_user_change(user, new_passwd,
                                     original_passwd, master)
        try:
            tasks.ldappasswd_user_change(user, original_passwd,
                                         new_passwd, master)
        except CalledProcessError as e:
            if e.returncode != 1:
                raise
        else:
            pytest.fail("Password change violating policy did not fail")

    def test_dm_change_user_pwd_history_issue7181(self, pwpolicy_global):
        """
        Test that password policy is not applied with Directory Manager.

        The minimum lifetime of the password is set to 1 hour. Confirm
        that the user cannot re-change their password immediately but
        the DM can.
        """
        user = 'user1'
        original_passwd = 'Secret123'
        new_passwd = 'newPasswd123'

        master = self.master

        # reset minimum life to 1 hour.
        self.master.run_command(
            ["ipa", "pwpolicy-mod", "--minlife=1"],
        )

        try:
            tasks.ldappasswd_user_change(user, original_passwd,
                                         new_passwd, master)
        except CalledProcessError as e:
            if e.returncode != 1:
                raise
        else:
            pytest.fail("Password change violating policy did not fail")

        # DM should be able to change any password regardless of policy
        try:
            tasks.ldappasswd_user_change(user, new_passwd,
                                         original_passwd, master,
                                         use_dirman=True)
        except CalledProcessError:
            pytest.fail("Password change failed when it should not")

    def test_huge_password(self):
        user = 'toolonguser'
        hostname = 'toolong.{}'.format(self.master.domain.name)
        huge_password = ipa_generate_password(min_len=1536)
        original_passwd = 'Secret123'
        master = self.master
        base_dn = str(master.domain.basedn)

        # Create a user with a password that is too long
        tasks.kinit_admin(master)
        add_password_stdin_text = "{pwd}\n{pwd}".format(pwd=huge_password)
        result = master.run_command(['ipa', 'user-add', user,
                                     '--first', user,
                                     '--last', user,
                                     '--password'],
                                    stdin_text=add_password_stdin_text,
                                    raiseonerr=False)
        assert result.returncode != 0

        # Try again with a normal password
        add_password_stdin_text = "{pwd}\n{pwd}".format(pwd=original_passwd)
        master.run_command(['ipa', 'user-add', user,
                            '--first', user,
                            '--last', user,
                            '--password'],
                           stdin_text=add_password_stdin_text)

        # kinit as that user in order to modify the pwd
        user_kinit_stdin_text = "{old}\n%{new}\n%{new}\n".format(
            old=original_passwd,
            new=original_passwd)
        master.run_command(['kinit', user], stdin_text=user_kinit_stdin_text)
        # sleep 1 sec (krblastpwdchange and krbpasswordexpiration have at most
        # a 1s precision)
        time.sleep(1)
        # perform ldapmodify on userpassword as dir mgr
        entry_ldif = textwrap.dedent("""
            dn: uid={user},cn=users,cn=accounts,{base_dn}
            changetype: modify
            replace: userpassword
            userpassword: {new_passwd}
        """).format(
            user=user,
            base_dn=base_dn,
            new_passwd=huge_password)

        result = tasks.ldapmodify_dm(master, entry_ldif, raiseonerr=False)
        assert result.returncode != 0

        # ask_password in ipa-getkeytab will complain about too long password
        keytab_file = os.path.join(self.master.config.test_dir,
                                   'user.keytab')
        password_stdin_text = "{pwd}\n{pwd}".format(pwd=huge_password)
        result = self.master.run_command(['ipa-getkeytab',
                                          '-p', user,
                                          '-P',
                                          '-k', keytab_file,
                                          '-s', self.master.hostname],
                                         stdin_text=password_stdin_text,
                                         raiseonerr=False)
        assert result.returncode != 0
        assert "clear-text password is too long" in result.stderr_text

        # Create a host with a user-set OTP that is too long
        tasks.kinit_admin(master)
        result = master.run_command(['ipa', 'host-add', '--force',
                                     hostname,
                                     '--password', huge_password],
                                    raiseonerr=False)
        assert result.returncode != 0

        # Try again with a valid password
        result = master.run_command(['ipa', 'host-add', '--force',
                                     hostname,
                                     '--password', original_passwd],
                                    raiseonerr=False)
        assert result.returncode == 0

    def test_cleartext_password_httpd_log(self):
        """Test to check password leak in apache error log

        Host enrollment with OTP used to log the password in cleartext
        to apache error log. This test ensures that the password should
        not be log in cleartext.

        related: https://pagure.io/freeipa/issue/8017
        """
        hostname = 'test.{}'.format(self.master.domain.name)
        passwd = 'Secret123'

        self.master.run_command(['ipa', 'host-add', '--force',
                                 hostname, '--password', passwd])

        # remove added host i.e cleanup
        self.master.run_command(['ipa', 'host-del', hostname])

        result = self.master.run_command(['grep', hostname,
                                          paths.VAR_LOG_HTTPD_ERROR])
        assert passwd not in result.stdout_text

    def test_change_selinuxusermaporder(self):
        """
        An update file meant to ensure a more sane default was
        overriding any customization done to the order.
        """
        maporder = "unconfined_u:s0-s0:c0.c1023"

        # set a new default
        tasks.kinit_admin(self.master)
        result = self.master.run_command(
            ["ipa", "config-mod",
             "--ipaselinuxusermaporder={}".format(maporder)],
            raiseonerr=False
        )
        assert result.returncode == 0

        # apply the update
        result = self.master.run_command(
            ["ipa-server-upgrade"],
            raiseonerr=False
        )
        assert result.returncode == 0

        # ensure result is the same
        result = self.master.run_command(
            ["ipa", "config-show"],
            raiseonerr=False
        )
        assert result.returncode == 0
        assert "SELinux user map order: {}".format(
            maporder) in result.stdout_text

    def test_ipa_console(self):
        tasks.kinit_admin(self.master)
        result = self.master.run_command(
            ["ipa", "console"],
            stdin_text="api.env"
        )
        assert "ipalib.config.Env" in result.stdout_text

        filename = tasks.upload_temp_contents(
            self.master,
            "print(api.env)\n"
        )
        result = self.master.run_command(
            ["ipa", "console", filename],
        )
        assert "ipalib.config.Env" in result.stdout_text

    def test_list_help_topics(self):
        tasks.kinit_admin(self.master)
        result = self.master.run_command(
            ["ipa", "help", "topics"],
            raiseonerr=False
        )
        assert result.returncode == 0

    def test_ssh_key_connection(self, tmpdir):
        """
        Integration test for https://pagure.io/SSSD/sssd/issue/3747
        """
        if self.master.is_fips_mode:  # pylint: disable=no-member
            pytest.skip("paramiko is not compatible with FIPS mode")

        test_user = 'test-ssh'
        external_master_hostname = \
            self.master.external_hostname

        pub_keys = []

        for i in range(40):
            ssh_key_pair = tasks.generate_ssh_keypair()
            pub_keys.append(ssh_key_pair[1])
            with open(os.path.join(
                    tmpdir, 'ssh_priv_{}'.format(i)), 'w') as fp:
                fp.write(ssh_key_pair[0])

        tasks.kinit_admin(self.master)
        self.master.run_command(['ipa', 'user-add', test_user,
                                 '--first=tester', '--last=tester'])

        keys_opts = ' '.join(['--ssh "{}"'.format(k) for k in pub_keys])
        cmd = 'ipa user-mod {} {}'.format(test_user, keys_opts)
        self.master.run_command(cmd)

        # connect with first SSH key
        first_priv_key_path = os.path.join(tmpdir, 'ssh_priv_1')
        # change private key permission to comply with SS rules
        os.chmod(first_priv_key_path, 0o600)

        sshcon = paramiko.SSHClient()
        sshcon.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # first connection attempt is a workaround for
        # https://pagure.io/SSSD/sssd/issue/3669
        try:
            sshcon.connect(external_master_hostname, username=test_user,
                           key_filename=first_priv_key_path, timeout=1)
        except (paramiko.AuthenticationException, paramiko.SSHException):
            pass

        try:
            sshcon.connect(external_master_hostname, username=test_user,
                           key_filename=first_priv_key_path, timeout=1)
        except (paramiko.AuthenticationException,
                paramiko.SSHException) as e:
            pytest.fail('Authentication using SSH key not successful', e)

        journal_cmd = ['journalctl', '--since=today', '-u', 'sshd']
        result = self.master.run_command(journal_cmd)
        output = result.stdout_text
        assert not re.search('exited on signal 13', output)

        # cleanup
        self.master.run_command(['ipa', 'user-del', test_user])

    def test_ssh_leak(self):
        """
        Integration test for https://pagure.io/SSSD/sssd/issue/3794
        """

        def count_pipes():

            res = self.master.run_command(['pidof', 'sssd_ssh'])
            pid = res.stdout_text.strip()
            proc_path = '/proc/{}/fd'.format(pid)
            res = self.master.run_command(['ls', '-la', proc_path])
            fds_text = res.stdout_text.strip()
            return sum((1 for _ in re.finditer(r'pipe', fds_text)))

        test_user = 'test-ssh'

        tasks.kinit_admin(self.master)
        self.master.run_command(['ipa', 'user-add', test_user,
                                 '--first=tester', '--last=tester'])

        certs = []

        # we are ok with whatever certificate for this test
        external_ca = ExternalCA()
        for _dummy in range(3):
            cert = external_ca.create_ca()
            cert = tasks.strip_cert_header(cert.decode('utf-8'))
            certs.append('"{}"'.format(cert))

        cert_args = list(
            chain.from_iterable(list(zip(repeat('--certificate'), certs))))
        cmd = 'ipa user-add-cert {} {}'.format(test_user, ' '.join(cert_args))
        self.master.run_command(cmd)

        tasks.clear_sssd_cache(self.master)

        num_of_pipes = count_pipes()

        for _dummy in range(3):
            self.master.run_command([paths.SSS_SSH_AUTHORIZEDKEYS, test_user])
            current_num_of_pipes = count_pipes()
            assert current_num_of_pipes == num_of_pipes

        # cleanup
        self.master.run_command(['ipa', 'user-del', test_user])

    def test_certificate_out_write_to_file(self):
        # commands to test; name of temporary file will be appended
        commands = [
            ['ipa', 'cert-show', '1', '--certificate-out'],
            ['ipa', 'cert-show', '1', '--chain', '--certificate-out'],
            ['ipa', 'ca-show', 'ipa', '--certificate-out'],
            ['ipa', 'ca-show', 'ipa', '--chain', '--certificate-out'],
        ]

        for command in commands:
            cmd = self.master.run_command(['mktemp'])
            filename = cmd.stdout_text.strip()

            self.master.run_command(command + [filename])

            # Check that a PEM file was written.  If --chain was
            # used, load_pem_x509_certificate will return the
            # first certificate, which is fine for this test.
            data = self.master.get_file_contents(filename)
            x509.load_pem_x509_certificate(data, backend=default_backend())

            self.master.run_command(['rm', '-f', filename])

    def test_sssd_ifp_access_ipaapi(self):
        # check that ipaapi is allowed to access sssd-ifp for smartcard auth
        # https://pagure.io/freeipa/issue/7751
        username = 'admin'
        # get UID for user
        result = self.master.run_command(['ipa', 'user-show', username])
        mo = re.search(r'UID: (\d+)', result.stdout_text)
        assert mo is not None, result.stdout_text
        uid = mo.group(1)

        cmd = [
            'dbus-send',
            '--print-reply', '--system',
            '--dest=org.freedesktop.sssd.infopipe',
            '/org/freedesktop/sssd/infopipe/Users',
            'org.freedesktop.sssd.infopipe.Users.FindByName',
            'string:{}'.format(username)
        ]
        # test IFP as root
        result = self.master.run_command(cmd)
        assert uid in result.stdout_text

        # test IFP as ipaapi
        result = self.master.run_command(
            ['sudo', '-u', IPAAPI_USER, '--'] + cmd
        )
        assert uid in result.stdout_text

    def test_ipa_cacert_manage_install(self):
        # Re-install the IPA CA
        self.master.run_command([
            paths.IPA_CACERT_MANAGE,
            'install',
            paths.IPA_CA_CRT])

        # Test a non-existent file
        result = self.master.run_command([
            paths.IPA_CACERT_MANAGE,
            'install',
            '/run/cert_not_found'], raiseonerr=False)
        assert result.returncode == 1

        cmd = self.master.run_command(['mktemp'])
        filename = cmd.stdout_text.strip()

        for contents in (good_pkcs7,):
            self.master.put_file_contents(filename, contents)
            result = self.master.run_command([
                paths.IPA_CACERT_MANAGE,
                'install',
                filename])

        for contents in (badcert,):
            self.master.put_file_contents(filename, contents)
            result = self.master.run_command([
                paths.IPA_CACERT_MANAGE,
                'install',
                filename], raiseonerr=False)
            assert result.returncode == 1

        self.master.run_command(['rm', '-f', filename])

    def test_hbac_systemd_user(self):
        # https://pagure.io/freeipa/issue/7831
        tasks.kinit_admin(self.master)
        # check for presence
        self.master.run_command(
            ['ipa', 'hbacsvc-show', 'systemd-user']
        )
        result = self.master.run_command(
            ['ipa', 'hbacrule-show', 'allow_systemd-user', '--all']
        )
        lines = set(l.strip() for l in result.stdout_text.split('\n'))
        assert 'User category: all' in lines
        assert 'Host category: all' in lines
        assert 'Enabled: TRUE' in lines
        assert 'HBAC Services: systemd-user' in lines
        assert 'accessruletype: allow' in lines

        # delete both
        self.master.run_command(
            ['ipa', 'hbacrule-del', 'allow_systemd-user']
        )
        self.master.run_command(
            ['ipa', 'hbacsvc-del', 'systemd-user']
        )

        # run upgrade
        result = self.master.run_command(['ipa-server-upgrade'])
        assert 'Created hbacsvc systemd-user' in result.stderr_text
        assert 'Created hbac rule allow_systemd-user' in result.stderr_text

        # check for presence
        result = self.master.run_command(
            ['ipa', 'hbacrule-show', 'allow_systemd-user', '--all']
        )
        lines = set(l.strip() for l in result.stdout_text.split('\n'))
        assert 'User category: all' in lines
        assert 'Host category: all' in lines
        assert 'Enabled: TRUE' in lines
        assert 'HBAC Services: systemd-user' in lines
        assert 'accessruletype: allow' in lines

        self.master.run_command(
            ['ipa', 'hbacsvc-show', 'systemd-user']
        )

        # only delete rule
        self.master.run_command(
            ['ipa', 'hbacrule-del', 'allow_systemd-user']
        )

        # run upgrade
        result = self.master.run_command(['ipa-server-upgrade'])
        assert (
            'hbac service systemd-user already exists' in result.stderr_text
        )
        assert (
            'Created hbac rule allow_systemd-user' not in result.stderr_text
        )
        result = self.master.run_command(
            ['ipa', 'hbacrule-show', 'allow_systemd-user'],
            raiseonerr=False
        )
        assert result.returncode != 0
        assert 'HBAC rule not found' in result.stderr_text

    def test_config_show_configured_services(self):
        # https://pagure.io/freeipa/issue/7929
        states = {CONFIGURED_SERVICE, ENABLED_SERVICE, HIDDEN_SERVICE}
        dn = DN(
            ('cn', 'HTTP'), ('cn', self.master.hostname), ('cn', 'masters'),
            ('cn', 'ipa'), ('cn', 'etc'),
            self.master.domain.basedn
        )

        conn = self.master.ldap_connect()
        entry = conn.get_entry(dn)  # pylint: disable=no-member

        # original setting and all settings without state
        orig_cfg = list(entry['ipaConfigString'])
        other_cfg = [item for item in orig_cfg if item not in states]

        try:
            # test with hidden
            cfg = [HIDDEN_SERVICE]
            cfg.extend(other_cfg)
            entry['ipaConfigString'] = cfg
            conn.update_entry(entry)  # pylint: disable=no-member
            self.master.run_command(['ipa', 'config-show'])

            # test with configured
            cfg = [CONFIGURED_SERVICE]
            cfg.extend(other_cfg)
            entry['ipaConfigString'] = cfg
            conn.update_entry(entry)  # pylint: disable=no-member
            self.master.run_command(['ipa', 'config-show'])
        finally:
            # reset
            entry['ipaConfigString'] = orig_cfg
            conn.update_entry(entry)  # pylint: disable=no-member

    def test_ssh_from_controller(self):
        """https://pagure.io/SSSD/sssd/issue/3979
        Test ssh from test controller after adding
        ldap_deref_threshold=0 to sssd.conf on master

        Steps:
        1. setup a master
        2. add ldap_deref_threshold=0 to sssd.conf on master
        3. add an ipa user
        4. ssh from controller to master using the user created in step 3
        """
        if self.master.is_fips_mode:  # pylint: disable=no-member
            pytest.skip("paramiko is not compatible with FIPS mode")

        cmd = self.master.run_command(['sssd', '--version'])
        sssd_version = platform_tasks.parse_ipa_version(
            cmd.stdout_text.strip())
        if sssd_version < platform_tasks.parse_ipa_version('2.2.0'):
            pytest.xfail(reason="sssd 2.2.0 unavailable in F29 nightly")

        username = "testuser" + str(random.randint(200000, 9999999))
        # add ldap_deref_threshold=0 to /etc/sssd/sssd.conf
        sssd_conf_backup = tasks.FileBackup(self.master, paths.SSSD_CONF)
        with tasks.remote_sssd_config(self.master) as sssd_config:
            sssd_config.edit_domain(
                self.master.domain, 'ldap_deref_threshold', 0)
        try:
            self.master.run_command(['systemctl', 'restart', 'sssd.service'])

            # kinit admin
            tasks.kinit_admin(self.master)

            # add ipa user
            cmd = ['ipa', 'user-add',
                   '--first', username,
                   '--last', username,
                   '--password', username]
            input_passwd = 'Secret123\nSecret123\n'
            cmd_output = self.master.run_command(cmd, stdin_text=input_passwd)
            assert 'Added user "%s"' % username in cmd_output.stdout_text
            input_passwd = 'Secret123\nSecret123\nSecret123\n'
            self.master.run_command(['kinit', username],
                                    stdin_text=input_passwd)

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(self.master.hostname,
                           username=username,
                           password='Secret123')
            client.close()
        finally:
            sssd_conf_backup.restore()
            self.master.run_command(['systemctl', 'restart', 'sssd.service'])

    def test_user_mod_change_capitalization_issue5879(self):
        """
        Test that an existing user which has been modified using ipa user-mod
        and has the first and last name beginning with caps does not
        throw the error 'ipa: ERROR: Type or value exists:' and
        instead gets modified

        This is a test case for Pagure issue
        https://pagure.io/freeipa/issue/5879

        Steps:
        1. setup a master
        2. add ipa user on master
        3. now run ipa user-mod and specifying capital letters in names
        4. user details should be modified
        5. ipa: ERROR: Type or value exists is not displayed on console.
        """
        # Create an ipa-user
        tasks.kinit_admin(self.master)
        ipauser = 'ipauser1'
        first = 'ipauser'
        modfirst = 'IpaUser'
        last = 'test'
        modlast = 'Test'
        password = 'Secret123'
        self.master.run_command(
            ['ipa', 'user-add', ipauser, '--first', first, '--last', last,
             '--password'],
            stdin_text="%s\n%s\n" % (password, password))
        cmd = self.master.run_command(
            ['ipa', 'user-mod', ipauser, '--first', modfirst,
             '--last', modlast])
        assert 'Modified user "%s"' % (ipauser) in cmd.stdout_text
        assert 'First name: %s' % (modfirst) in cmd.stdout_text
        assert 'Last name: %s' % (modlast) in cmd.stdout_text

    @pytest.mark.skip_if_platform(
        "debian", reason="Crypto policy is not supported on Debian"
    )
    def test_enabled_tls_protocols(self):
        """Check Apache has same TLS versions enabled as crypto policy

        This is the regression test for issue
        https://pagure.io/freeipa/issue/7995.
        """
        def is_tls_version_enabled(tls_version):
            res = self.master.run_command(
                ['openssl', 's_client',
                 '-connect', '{}:443'.format(self.master.hostname),
                 '-{}'.format(tls_version)],
                stdin_text='\n',
                ok_returncode=[0, 1]
            )
            return res.returncode == 0

        # get minimum version from current crypto-policy
        openssl_cnf = self.master.get_file_contents(
            "/etc/crypto-policies/back-ends/opensslcnf.config",
            encoding="utf-8"
        )
        mo = re.search(r"MinProtocol\s*=\s*(TLSv[0-9.]+)", openssl_cnf)
        assert mo
        min_tls = mo.group(1)
        # Fedora DEFAULT has TLS 1.0 enabled, NEXT has TLS 1.2
        # even FUTURE crypto policy has TLS 1.2 as minimum version
        assert min_tls in {"TLSv1", "TLSv1.2"}

        # On Fedora FreeIPA still disables TLS 1.0 and 1.1 in ssl.conf.

        assert not is_tls_version_enabled('tls1')
        assert not is_tls_version_enabled('tls1_1')
        assert is_tls_version_enabled('tls1_2')
        assert is_tls_version_enabled('tls1_3')

    def test_sss_ssh_authorizedkeys(self):
        """Login via Ssh using private-key for ipa-user should work.

        Test for : https://pagure.io/SSSD/sssd/issue/3937
        Steps:
        1) setup user with ssh-key and certificate stored in ipaserver
        2) simulate p11_child timeout
        3) try to login via ssh using private key.
        """
        user = 'testsshuser'
        passwd = 'Secret123'
        user_key = tasks.create_temp_file(self.master, create_file=False)
        pem_file = tasks.create_temp_file(self.master)
        # Create a user with a password
        tasks.create_active_user(self.master, user, passwd, extra_args=[
            '--homedir', '/home/{}'.format(user)])
        tasks.kinit_admin(self.master)
        tasks.run_command_as_user(
            self.master, user, ['ssh-keygen', '-N', '',
                                '-f', user_key])
        ssh_pub_key = self.master.get_file_contents('{}.pub'.format(
            user_key), encoding='utf-8')
        openssl_cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-days', '365',
            '-nodes', '-out', pem_file, '-subj', '/CN=' + user]
        self.master.run_command(openssl_cmd)
        cert_b64 = self.get_cert_base64(self.master, pem_file)
        sssd_p11_child = '/usr/libexec/sssd/p11_child'
        backup = tasks.FileBackup(self.master, sssd_p11_child)
        try:
            content = '#!/bin/bash\nsleep 999999'
            # added sleep to simulate the timeout for p11_child
            self.master.put_file_contents(sssd_p11_child, content)
            self.master.run_command(
                ['ipa', 'user-mod', user, '--ssh', ssh_pub_key])
            self.master.run_command([
                'ipa', 'user-add-cert', user, '--certificate', cert_b64])
            # clear cache to avoid SSSD to check the user in old lookup
            tasks.clear_sssd_cache(self.master)
            result = self.master.run_command(
                [paths.SSS_SSH_AUTHORIZEDKEYS, user])
            assert ssh_pub_key in result.stdout_text
            # login to the system
            self.master.run_command(
                ['ssh', '-v', '-o', 'PasswordAuthentication=no',
                 '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=no',
                 '-o', 'ConnectTimeout=10', '-l', user, '-i', user_key,
                 self.master.hostname, 'true'])
        finally:
            # cleanup
            self.master.run_command(['ipa', 'user-del', user])
            backup.restore()
            self.master.run_command(['rm', '-f', pem_file, user_key,
                                     '{}.pub'.format(user_key)])

    def test_cacert_manage(self):
        """Exercise ipa-cacert-manage delete"""

        # deletion without nickname
        result = self.master.run_command(
            ['ipa-cacert-manage', 'delete'],
            raiseonerr=False
        )
        assert result.returncode != 0

        # deletion with an unknown nickname
        result = self.master.run_command(
            ['ipa-cacert-manage', 'delete', 'unknown'],
            raiseonerr=False
        )
        assert result.returncode != 0
        assert "Unknown CA 'unknown'" in result.stderr_text

        # deletion of IPA CA
        ipa_ca_nickname = get_ca_nickname(self.master.domain.realm)
        result = self.master.run_command(
            ['ipa-cacert-manage', 'delete', ipa_ca_nickname],
            raiseonerr=False
        )
        assert result.returncode != 0
        assert 'The IPA CA cannot be removed with this tool' in \
               result.stderr_text

        # Install 3rd party CA's, Let's Encrypt in this case
        for cert in (isrgrootx1, letsencryptauthorityx3):
            certfile = os.path.join(self.master.config.test_dir, 'cert.pem')
            self.master.put_file_contents(certfile, cert)
            result = self.master.run_command(
                ['ipa-cacert-manage', 'install', certfile],
            )

        # deletion of a root CA needed by a subCA, without -f option
        result = self.master.run_command(
            ['ipa-cacert-manage', 'delete', isrgrootx1_nick],
            raiseonerr=False
        )
        assert result.returncode != 0
        assert "Verifying \'%s\' failed. Removing part of the " \
               "chain? certutil: certificate is invalid: Peer's " \
               "Certificate issuer is not recognized." \
               % isrgrootx1_nick in result.stderr_text

        # deletion of a root CA needed by a subCA, with -f option
        result = self.master.run_command(
            ['ipa-cacert-manage', 'delete', isrgrootx1_nick, '-f'],
            raiseonerr=False
        )
        assert result.returncode == 0

        # deletion of a subca
        result = self.master.run_command(
            ['ipa-cacert-manage', 'delete', le_x3_nick],
            raiseonerr=False
        )
        assert result.returncode == 0

    def test_ipa_adtrust_install_with_locale_issue8066(self):
        """
        This test checks that ipa-adtrust-install command runs successfully
        on a system with locale en_IN.UTF-8 without displaying error below
        'IndexError: list index out of range'
        This is a testcase for Pagure issue
        https://pagure.io/freeipa/issue/8066
        """
        # Set locale to en_IN.UTF-8 in .bashrc file to avoid reboot
        tasks.kinit_admin(self.master)
        BASHRC_CFG = "/root/.bashrc"
        bashrc_backup = tasks.FileBackup(self.master, BASHRC_CFG)
        exp_msg = "en_IN.UTF-8"
        try:
            self.master.run_command(
                'echo "export LC_TIME=en_IN.UTF-8" >> ' + BASHRC_CFG
            )
            result = self.master.run_command('echo "$LC_TIME"')
            assert result.stdout_text.rstrip() == exp_msg
            # Install ipa-server-adtrust and check status
            msg1 = (
                "Unexpected error - see /var/log/ipaserver-install.log"
                "for details"
            )
            msg2 = "IndexError: list index out of range"
            tasks.install_packages(self.master, ["*ipa-server-trust-ad"])
            result = self.master.run_command(
                ["ipa-adtrust-install", "-U"], raiseonerr=False
            )
            assert msg1 not in result.stderr_text
            assert msg2 not in result.stderr_text
        finally:
            bashrc_backup.restore()

    @pytest.fixture
    def user_creation_deletion(self):
        # create user
        self.testuser = 'testuser'
        tasks.create_active_user(self.master, self.testuser, 'Secret123')

        yield

        # cleanup
        tasks.kinit_admin(self.master)
        self.master.run_command(['ipa', 'user-del', self.testuser])

    def test_login_wrong_password(self, user_creation_deletion):
        """Test ipa user login with wrong password

        When ipa user login to machine using wrong password, it
        should log proper message

        related: https://github.com/SSSD/sssd/issues/5139
        """
        # try to login with wrong password
        sssd_version = tasks.get_sssd_version(self.master)
        if (sssd_version < tasks.parse_version('2.3.0')):
            pytest.xfail('Fix is part of sssd 2.3.0 and is'
                         ' available from fedora32 onwards')

        sshconn = paramiko.SSHClient()
        sshconn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # start to look at logs a bit before "now"
        # https://pagure.io/freeipa/issue/8432
        since = time.strftime(
            '%H:%M:%S', (datetime.now() - timedelta(seconds=10)).timetuple()
        )
        try:
            sshconn.connect(self.master.hostname,
                            username=self.testuser,
                            password='WrongPassword')
        except paramiko.AuthenticationException:
            pass

        sshconn.close()

        # check if proper message logged
        exp_msg = ("pam_sss(sshd:auth): received for user {}: 7"
                   " (Authentication failure)".format(self.testuser))
        result = self.master.run_command(['journalctl',
                                          '-u', 'sshd',
                                          '--since={}'.format(since)])
        assert exp_msg in result.stdout_text

    def get_dirsrv_id(self):
        serverid = realm_to_serverid(self.master.domain.realm)
        return("dirsrv@%s.service" % serverid)

    def test_ipa_nis_manage_enable(self):
        """
        This testcase checks if ipa-nis-manage enable
        command enables plugin on an IPA master
        """
        dirsrv_service = self.get_dirsrv_id()
        console_msg = (
            "Enabling plugin\n"
            "This setting will not take effect until "
            "you restart Directory Server.\n"
            "The rpcbind service may need to be started"
        )
        status_msg = "Plugin is enabled"
        tasks.kinit_admin(self.master)
        result = self.master.run_command(
            ["ipa-nis-manage", "enable"],
            stdin_text=self.master.config.admin_password,
        )
        assert console_msg in result.stdout_text
        # verify using backend
        conn = self.master.ldap_connect()  # pylint: disable=no-member
        dn = DN(('cn', 'NIS Server'), ('cn', 'plugins'), ('cn', 'config'))
        entry = conn.get_entry(dn)  # pylint: disable=no-member
        nispluginstring = entry.get('nsslapd-pluginEnabled')
        assert 'on' in nispluginstring
        # restart for changes to take effect
        self.master.run_command(["systemctl", "restart", dirsrv_service])
        self.master.run_command(["systemctl", "restart", "rpcbind"])
        time.sleep(DIRSRV_SLEEP)
        # check status msg on the console
        result = self.master.run_command(
            ["ipa-nis-manage", "status"],
            stdin_text=self.master.config.admin_password,
        )
        assert status_msg in result.stdout_text

    def test_ipa_nis_manage_disable(self):
        """
        This testcase checks if ipa-nis-manage disable
        command disable plugin on an IPA Master
        """
        dirsrv_service = self.get_dirsrv_id()
        msg = (
            "This setting will not take effect "
            "until you restart Directory Server."
        )
        status_msg = "Plugin is not enabled"
        tasks.kinit_admin(self.master)
        result = self.master.run_command(
            ["ipa-nis-manage", "disable"],
            stdin_text=self.master.config.admin_password,
        )
        assert msg in result.stdout_text
        # verify using backend
        conn = self.master.ldap_connect()  # pylint: disable=no-member
        dn = DN(('cn', 'NIS Server'), ('cn', 'plugins'), ('cn', 'config'))
        entry = conn.get_entry(dn)  # pylint: disable=no-member
        nispluginstring = entry.get('nsslapd-pluginEnabled')
        assert 'off' in nispluginstring
        # restart dirsrv for changes to take effect
        self.master.run_command(["systemctl", "restart", dirsrv_service])
        time.sleep(DIRSRV_SLEEP)
        # check status msg on the console
        result = self.master.run_command(
            ["ipa-nis-manage", "status"],
            stdin_text=self.master.config.admin_password,
            raiseonerr=False,
        )
        assert result.returncode == 4
        assert status_msg in result.stdout_text

    def test_ipa_nis_manage_enable_incorrect_password(self):
        """
        This testcase checks if ipa-nis-manage enable
        command throws error on console for invalid DS admin password
        """
        msg = (
            "Insufficient access: Invalid credentials "
            "Invalid credentials\n"
        )
        result = self.master.run_command(
            ["ipa-nis-manage", "enable"],
            stdin_text='Invalid_pwd',
            raiseonerr=False,
        )
        assert result.returncode == 1
        assert msg in result.stderr_text
