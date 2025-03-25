# Authors:
#   Petr Viktorin <pviktori@redhat.com>
#
# Copyright (C) 2013  Red Hat
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

"""Common tasks for FreeIPA integration tests"""

import os
import textwrap
import re
import collections
import itertools
import time

import dns
from ldif import LDIFWriter
from six import StringIO

from ipapython import ipautil
from ipaplatform.paths import paths
from ipapython.dn import DN
from ipapython.ipa_log_manager import log_mgr
from ipatests.test_integration import util
from ipatests.test_integration.env_config import env_to_script
from ipatests.test_integration.host import Host
from ipalib import errors
from ipalib.util import get_reverse_zone_default, verify_host_resolvable
from ipalib.constants import DOMAIN_SUFFIX_NAME
from ipalib.constants import DOMAIN_LEVEL_0

log = log_mgr.get_logger(__name__)

IPATEST_NM_CONFIG = '20-ipatest-unmanaged-resolv.conf'


def check_arguments_are(slice, instanceof):
    """
    :param: slice - tuple of integers denoting the beginning and the end
    of argument list to be checked
    :param: instanceof - name of the class the checked arguments should be
    instances of
    Example: @check_arguments_are((1, 3), int) will check that the second
    and third arguments are integers
    """
    def wrapper(func):
        def wrapped(*args):
            for i in args[slice[0]:slice[1]]:
                assert isinstance(i, instanceof), "Wrong type: %s: %s" % (i, type(i))
            return func(*args)
        return wrapped
    return wrapper

def prepare_reverse_zone(host, ip):
    zone = get_reverse_zone_default(ip)
    host.run_command(["ipa",
                      "dnszone-add",
                      zone], raiseonerr=False)

def prepare_host(host):
    if isinstance(host, Host):
        env_filename = os.path.join(host.config.test_dir, 'env.sh')

        # First we try to run simple echo command to test the connection
        host.run_command(['true'], set_env=False)

        host.collect_log(env_filename)
        host.transport.mkdir_recursive(host.config.test_dir)
        host.put_file_contents(env_filename, env_to_script(host.to_env()))


def allow_sync_ptr(host):
    kinit_admin(host)
    host.run_command(["ipa", "dnsconfig-mod", "--allow-sync-ptr=true"],
                     raiseonerr=False)


def apply_common_fixes(host):
    fix_etc_hosts(host)
    fix_hostname(host)
    modify_nm_resolv_conf_settings(host)
    fix_resolv_conf(host)


def backup_file(host, filename):
    if host.transport.file_exists(filename):
        backupname = os.path.join(host.config.test_dir, 'file_backup',
                                  filename.lstrip('/'))
        host.transport.mkdir_recursive(os.path.dirname(backupname))
        host.run_command(['cp', '-af', filename, backupname])
        return True
    else:
        rmname = os.path.join(host.config.test_dir, 'file_remove')
        host.run_command('echo %s >> %s' % (
            ipautil.shell_quote(filename),
            ipautil.shell_quote(rmname)))
        contents = host.get_file_contents(rmname)
        host.transport.mkdir_recursive(os.path.dirname(rmname))
        return False


def fix_etc_hosts(host):
    backup_file(host, paths.HOSTS)
    contents = host.get_file_contents(paths.HOSTS)
    # Remove existing mentions of the host's FQDN, short name, and IP
    # Removing of IP must be done as first, otherwise hosts file may be
    # corrupted
    contents = re.sub('^%s.*' % re.escape(host.ip), '', contents,
                      flags=re.MULTILINE)
    contents = re.sub('\s%s(\s|$)' % re.escape(host.hostname), ' ', contents,
                      flags=re.MULTILINE)
    contents = re.sub('\s%s(\s|$)' % re.escape(host.shortname), ' ', contents,
                      flags=re.MULTILINE)
    # Add the host's info again
    contents += '\n%s %s %s\n' % (host.ip, host.hostname, host.shortname)
    log.debug('Writing the following to /etc/hosts:\n%s', contents)
    host.put_file_contents(paths.HOSTS, contents)


def fix_hostname(host):
    backup_file(host, paths.ETC_HOSTNAME)
    host.put_file_contents(paths.ETC_HOSTNAME, host.hostname + '\n')
    host.run_command(['hostname', host.hostname])

    backupname = os.path.join(host.config.test_dir, 'backup_hostname')
    host.run_command('hostname > %s' % ipautil.shell_quote(backupname))


def host_service_active(host, service):
    res = host.run_command(['systemctl', 'is-active', '--quiet', service],
                           raiseonerr=False)

    if res.returncode == 0:
        return True
    else:
        return False


def modify_nm_resolv_conf_settings(host):
    if not host_service_active(host, 'NetworkManager'):
        return

    config = "[main]\ndns=none\n"
    path = os.path.join(paths.NETWORK_MANAGER_CONFIG_DIR, IPATEST_NM_CONFIG)

    host.put_file_contents(path, config)
    host.run_command(['systemctl', 'restart', 'NetworkManager'],
                     raiseonerr=False)


def undo_nm_resolv_conf_settings(host):
    if not host_service_active(host, 'NetworkManager'):
        return

    path = os.path.join(paths.NETWORK_MANAGER_CONFIG_DIR, IPATEST_NM_CONFIG)
    host.run_command(['rm', '-f', path], raiseonerr=False)
    host.run_command(['systemctl', 'restart', 'NetworkManager'],
                     raiseonerr=False)


def fix_resolv_conf(host):
    backup_file(host, paths.RESOLV_CONF)
    lines = host.get_file_contents(paths.RESOLV_CONF).splitlines()
    lines = ['#' + l if l.startswith('nameserver') else l for l in lines]
    for other_host in host.domain.hosts:
        if other_host.role in ('master', 'replica'):
            lines.append('nameserver %s' % other_host.ip)
    contents = '\n'.join(lines)
    log.debug('Writing the following to /etc/resolv.conf:\n%s', contents)
    host.put_file_contents(paths.RESOLV_CONF, contents)


def fix_apache_semaphores(master):
    systemd_available = master.transport.file_exists(paths.SYSTEMCTL)

    if systemd_available:
        master.run_command(['systemctl', 'stop', 'httpd'], raiseonerr=False)
    else:
        master.run_command([paths.SBIN_SERVICE, 'httpd', 'stop'],
                           raiseonerr=False)

    master.run_command('for line in `ipcs -s | grep apache | cut -d " " -f 2`; '
                       'do ipcrm -s $line; done', raiseonerr=False)


def unapply_fixes(host):
    restore_files(host)
    restore_hostname(host)
    undo_nm_resolv_conf_settings(host)

    # Clean up the test directory
    host.run_command(['rm', '-rvf', host.config.test_dir])


def restore_files(host):
    backupname = os.path.join(host.config.test_dir, 'file_backup')
    rmname = os.path.join(host.config.test_dir, 'file_remove')

    # Prepare command for restoring context of the backed-up files
    sed_remove_backupdir = 's/%s//g' % backupname.replace('/', '\/')
    restorecon_command = (
        "find %s | "
        "sed '%s' | "
        "sed '/^$/d' | "
        "xargs -d '\n' "
        "/sbin/restorecon -v" % (backupname, sed_remove_backupdir))

    # Prepare command for actual restoring of the backed up files
    copyfiles_command = 'if [ -d %(dir)s/ ]; then cp -arvf %(dir)s/* /; fi' % {
        'dir': ipautil.shell_quote(backupname)}

    # Run both commands in one session. For more information, see:
    # https://fedorahosted.org/freeipa/ticket/4133
    host.run_command('%s ; (%s ||:)' % (copyfiles_command, restorecon_command))

    # Remove all the files that did not exist and were 'backed up'
    host.run_command(['xargs', '-d', r'\n', '-a', rmname, 'rm', '-vf'],
                     raiseonerr=False)
    host.run_command(['rm', '-rvf', backupname, rmname], raiseonerr=False)


def restore_hostname(host):
    backupname = os.path.join(host.config.test_dir, 'backup_hostname')
    try:
        hostname = host.get_file_contents(backupname)
    except IOError:
        log.debug('No hostname backed up on %s' % host.hostname)
    else:
        host.run_command(['hostname', hostname.strip()])
        host.run_command(['rm', backupname])


def enable_replication_debugging(host):
    log.info('Enable LDAP replication logging')
    logging_ldif = textwrap.dedent("""
        dn: cn=config
        changetype: modify
        replace: nsslapd-errorlog-level
        nsslapd-errorlog-level: 8192
        """)
    host.run_command(['ldapmodify', '-x',
                      '-D', str(host.config.dirman_dn),
                      '-w', host.config.dirman_password],
                     stdin_text=logging_ldif)


def install_master(host, setup_dns=True, setup_kra=False):
    host.collect_log(paths.IPASERVER_INSTALL_LOG)
    host.collect_log(paths.IPACLIENT_INSTALL_LOG)
    inst = host.domain.realm.replace('.', '-')
    host.collect_log(paths.SLAPD_INSTANCE_ERROR_LOG_TEMPLATE % inst)
    host.collect_log(paths.SLAPD_INSTANCE_ACCESS_LOG_TEMPLATE % inst)

    apply_common_fixes(host)
    fix_apache_semaphores(host)

    args = [
        'ipa-server-install', '-U',
        '-n', host.domain.name,
        '-r', host.domain.realm,
        '-p', host.config.dirman_password,
        '-a', host.config.admin_password,
        "--domain-level=%i" % host.config.domain_level
    ]

    if setup_dns:
        args.extend([
            '--setup-dns',
            '--forwarder', host.config.dns_forwarder,
            '--auto-reverse'
        ])

    host.run_command(args)
    enable_replication_debugging(host)
    setup_sssd_debugging(host)

    if setup_kra:
        args = [
            "ipa-kra-install",
            "-p", host.config.dirman_password,
            "-U",
        ]
        host.run_command(args)

    kinit_admin(host)


def get_replica_filename(replica):
    return os.path.join(replica.config.test_dir, 'replica-info.gpg')


def domainlevel(host):
    # Dynamically determines the domainlevel on master. Needed for scenarios
    # when domainlevel is changed during the test execution.
    result = host.run_command(['ipa', 'domainlevel-get'], raiseonerr=False)
    level = 0
    domlevel_re = re.compile('.*(\d)')
    if result.returncode == 0:
        # "domainlevel-get" command doesn't exist on ipa versions prior to 4.3
        level = int(domlevel_re.findall(result.stdout_text)[0])
    return level


def replica_prepare(master, replica):
    apply_common_fixes(replica)
    fix_apache_semaphores(replica)
    prepare_reverse_zone(master, replica.ip)
    master.run_command(['ipa-replica-prepare',
                        '-p', replica.config.dirman_password,
                        '--ip-address', replica.ip,
                        replica.hostname])
    replica_bundle = master.get_file_contents(
        paths.REPLICA_INFO_GPG_TEMPLATE % replica.hostname)
    replica_filename = get_replica_filename(replica)
    replica.put_file_contents(replica_filename, replica_bundle)


def install_replica(master, replica, setup_ca=True, setup_dns=False,
                    setup_kra=False):
    replica.collect_log(paths.IPAREPLICA_INSTALL_LOG)
    replica.collect_log(paths.IPAREPLICA_CONNCHECK_LOG)
    allow_sync_ptr(master)
    # Otherwise ipa-client-install would not create a PTR
    # and replica installation would fail
    args = ['ipa-replica-install', '-U',
            '-p', replica.config.dirman_password,
            '-w', replica.config.admin_password,
            '--ip-address', replica.ip]
    if setup_ca:
        args.append('--setup-ca')
    if setup_dns:
        args.extend([
            '--setup-dns',
            '--forwarder', replica.config.dns_forwarder
        ])
    if domainlevel(master) == DOMAIN_LEVEL_0:
        apply_common_fixes(replica)
        # prepare the replica file on master and put it to replica, AKA "old way"
        replica_prepare(master, replica)
        replica_filename = get_replica_filename(replica)
        args.append(replica_filename)
    else:
        # install client on a replica machine and then promote it to replica
        install_client(master, replica)
        fix_apache_semaphores(replica)

    replica.run_command(args)
    enable_replication_debugging(replica)
    setup_sssd_debugging(replica)

    if setup_kra:
        assert setup_ca, "CA must be installed on replica with KRA"
        args = [
            "ipa-kra-install",
            "-p", replica.config.dirman_password,
            "-U",
        ]
        if domainlevel(master) == DOMAIN_LEVEL_0:
            args.append(replica_filename)
        replica.run_command(args)

    kinit_admin(replica)


def install_client(master, client, extra_args=()):
    client.collect_log(paths.IPACLIENT_INSTALL_LOG)

    apply_common_fixes(client)

    client.run_command(['ipa-client-install', '-U',
                        '--domain', client.domain.name,
                        '--realm', client.domain.realm,
                        '-p', client.config.admin_name,
                        '-w', client.config.admin_password,
                        '--server', master.hostname]
                       + list(extra_args))

    setup_sssd_debugging(client)
    kinit_admin(client)


def install_adtrust(host):
    """
    Runs ipa-adtrust-install on the client and generates SIDs for the entries.
    Configures the compat tree for the legacy clients.
    """

    # ipa-adtrust-install appends to ipaserver-install.log
    host.collect_log(paths.IPASERVER_INSTALL_LOG)

    inst = host.domain.realm.replace('.', '-')
    host.collect_log(paths.SLAPD_INSTANCE_ERROR_LOG_TEMPLATE % inst)
    host.collect_log(paths.SLAPD_INSTANCE_ACCESS_LOG_TEMPLATE % inst)

    kinit_admin(host)
    host.run_command(['ipa-adtrust-install', '-U',
                      '--enable-compat',
                      '--netbios-name', host.netbios,
                      '-a', host.config.admin_password,
                      '--add-sids'])

    # Restart named because it lost connection to dirsrv
    # (Directory server restarts during the ipa-adtrust-install)
    # we use two services named and named-pkcs11,
    # if named is masked restart named-pkcs11
    result = host.run_command(['systemctl', 'is-enabled', 'named'],
                              raiseonerr=False)
    if result.stdout_text.startswith("masked"):
        host.run_command(['systemctl', 'restart', 'named-pkcs11'])
    else:
        host.run_command(['systemctl', 'restart', 'named'])

    # Check that named is running and has loaded the information from LDAP
    dig_command = ['dig', 'SRV', '+short', '@localhost',
                   '_ldap._tcp.%s' % host.domain.name]
    dig_output = '0 100 389 %s.' % host.hostname
    dig_test = lambda x: re.search(re.escape(dig_output), x)

    util.run_repeatedly(host, dig_command, test=dig_test)


def configure_dns_for_trust(master, ad):
    """
    This configures DNS on IPA master according to the relationship of the
    IPA's and AD's domains.
    """

    def is_subdomain(subdomain, domain):
        subdomain_unpacked = subdomain.split('.')
        domain_unpacked = domain.split('.')

        subdomain_unpacked.reverse()
        domain_unpacked.reverse()

        subdomain = False

        if len(subdomain_unpacked) > len(domain_unpacked):
            subdomain = True

            for subdomain_segment, domain_segment in zip(subdomain_unpacked,
                                                         domain_unpacked):
                subdomain = subdomain and subdomain_segment == domain_segment

        return subdomain

    kinit_admin(master)

    if is_subdomain(ad.domain.name, master.domain.name):
        master.run_command(['ipa', 'dnsrecord-add', master.domain.name,
                            '%s.%s' % (ad.shortname, ad.netbios),
                            '--a-ip-address', ad.ip])

        master.run_command(['ipa', 'dnsrecord-add', master.domain.name,
                            ad.netbios,
                            '--ns-hostname',
                            '%s.%s' % (ad.shortname, ad.netbios)])

        master.run_command(['ipa', 'dnszone-mod', master.domain.name,
                            '--allow-transfer', ad.ip])
    else:
        master.run_command(['ipa', 'dnsforwardzone-add', ad.domain.name,
                            '--forwarder', ad.ip,
                            '--forward-policy', 'only',
                            ])


def establish_trust_with_ad(master, ad, extra_args=()):
    """
    Establishes trust with Active Directory. Trust type is detected depending
    on the presence of SfU (Services for Unix) support on the AD.

    Use extra arguments to pass extra arguments to the trust-add command, such
    as --range-type="ipa-ad-trust" to enfroce a particular range type.
    """

    # Force KDC to reload MS-PAC info by trying to get TGT for HTTP
    master.run_command(['kinit', '-kt', paths.IPA_KEYTAB,
                        'HTTP/%s' % master.hostname])
    master.run_command(['systemctl', 'restart', 'krb5kdc.service'])
    master.run_command(['kdestroy', '-A'])

    kinit_admin(master)
    master.run_command(['klist'])
    master.run_command(['smbcontrol', 'all', 'debug', '100'])
    util.run_repeatedly(master,
                        ['ipa', 'trust-add',
                         '--type', 'ad', ad.domain.name,
                         '--admin', 'Administrator',
                         '--password'] + list(extra_args),
                        stdin_text=master.config.ad_admin_password)
    master.run_command(['smbcontrol', 'all', 'debug', '1'])
    clear_sssd_cache(master)


def remove_trust_with_ad(master, ad):
    """
    Removes trust with Active Directory. Also removes the associated ID range.
    """

    kinit_admin(master)

    # Remove the trust
    master.run_command(['ipa', 'trust-del', ad.domain.name])

    # Remove the range
    range_name = ad.domain.name.upper() + '_id_range'
    master.run_command(['ipa', 'idrange-del', range_name])


def configure_auth_to_local_rule(master, ad):
    """
    Configures auth_to_local rule in /etc/krb5.conf
    """

    section_identifier = " %s = {" % master.domain.realm
    line1 = ("  auth_to_local = RULE:[1:$1@$0](^.*@%s$)s/@%s/@%s/"
             % (ad.domain.realm, ad.domain.realm, ad.domain.name))
    line2 = "  auth_to_local = DEFAULT"

    krb5_conf_content = master.get_file_contents(paths.KRB5_CONF)
    krb5_lines = [line.rstrip() for line in krb5_conf_content.split('\n')]
    realm_section_index = krb5_lines.index(section_identifier)

    krb5_lines.insert(realm_section_index + 1, line1)
    krb5_lines.insert(realm_section_index + 2, line2)

    krb5_conf_new_content = '\n'.join(krb5_lines)
    master.put_file_contents(paths.KRB5_CONF, krb5_conf_new_content)

    master.run_command(['systemctl', 'restart', 'sssd'])


def setup_sssd_debugging(host):
    """
    Sets debug level to 7 in each section of sssd.conf file.
    """

    # Set debug level in each section of sssd.conf file to 7
    # First, remove any previous occurences
    host.run_command(['sed', '-i',
                      '/debug_level = 7/d',
                      paths.SSSD_CONF],
                     raiseonerr=False)

    # Add the debug directive to each section
    host.run_command(['sed', '-i',
                      '/\[*\]/ a\debug_level = 7',
                      paths.SSSD_CONF],
                     raiseonerr=False)

    host.collect_log('/var/log/sssd/*')

    # Clear the cache and restart SSSD
    clear_sssd_cache(host)


def clear_sssd_cache(host):
    """
    Clears SSSD cache by removing the cache files. Restarts SSSD.
    """

    systemd_available = host.transport.file_exists(paths.SYSTEMCTL)

    if systemd_available:
        host.run_command(['systemctl', 'stop', 'sssd'])
    else:
        host.run_command([paths.SBIN_SERVICE, 'sssd', 'stop'])

    host.run_command("find /var/lib/sss/db -name '*.ldb' | "
                     "xargs rm -fv")
    host.run_command(['rm', '-fv', paths.SSSD_MC_GROUP])
    host.run_command(['rm', '-fv', paths.SSSD_MC_PASSWD])

    if systemd_available:
        host.run_command(['systemctl', 'start', 'sssd'])
    else:
        host.run_command([paths.SBIN_SERVICE, 'sssd', 'start'])

    # To avoid false negatives due to SSSD not responding yet
    time.sleep(10)


def sync_time(host, server):
    """
    Syncs the time with the remote server. Please note that this function
    leaves ntpd stopped.
    """

    host.run_command(['systemctl', 'stop', 'ntpd'])
    host.run_command(['ntpdate', server.hostname])


def connect_replica(master, replica):
    kinit_admin(replica)
    replica.run_command(['ipa-replica-manage', 'connect', master.hostname])


def disconnect_replica(master, replica):
    kinit_admin(replica)
    replica.run_command(['ipa-replica-manage', 'disconnect', master.hostname])


def kinit_admin(host):
    host.run_command(['kinit', 'admin'],
                     stdin_text=host.config.admin_password)


def uninstall_master(host, ignore_topology_disconnect=True):
    host.collect_log(paths.IPASERVER_UNINSTALL_LOG)
    uninstall_cmd = ['ipa-server-install', '--uninstall', '-U']

    host_domain_level = domainlevel(host)

    if ignore_topology_disconnect and host_domain_level != DOMAIN_LEVEL_0:
        uninstall_cmd.append('--ignore-topology-disconnect')

    host.run_command(uninstall_cmd, raiseonerr=False)
    host.run_command(['pkidestroy', '-s', 'CA', '-i', 'pki-tomcat'],
                     raiseonerr=False)
    host.run_command(['rm', '-rf',
                      paths.TOMCAT_TOPLEVEL_DIR,
                      paths.SYSCONFIG_PKI_TOMCAT,
                      paths.SYSCONFIG_PKI_TOMCAT_PKI_TOMCAT_DIR,
                      paths.VAR_LIB_PKI_TOMCAT_DIR,
                      paths.PKI_TOMCAT,
                      paths.REPLICA_INFO_GPG_TEMPLATE % host.hostname],
                     raiseonerr=False)
    unapply_fixes(host)


def uninstall_client(host):
    host.collect_log(paths.IPACLIENT_UNINSTALL_LOG)

    host.run_command(['ipa-client-install', '--uninstall', '-U'],
                     raiseonerr=False)
    unapply_fixes(host)


@check_arguments_are((0, 2), Host)
def clean_replication_agreement(master, replica):
    """
    Performs `ipa-replica-manage del replica_hostname --force`.
    """
    master.run_command(['ipa-replica-manage',
                        'del',
                        replica.hostname,
                        '--force'])


@check_arguments_are((0, 3), Host)
def create_segment(master, leftnode, rightnode):
    """
    creates a topology segment. The first argument is a node to run the command
    :returns: a hash object containing segment's name, leftnode, rightnode
    information and an error string.
    """
    kinit_admin(master)
    lefthost = leftnode.hostname
    righthost = rightnode.hostname
    segment_name = "%s-to-%s" % (lefthost, righthost)
    result = master.run_command(["ipa", "topologysegment-add", DOMAIN_SUFFIX_NAME,
                                 segment_name,
                                 "--leftnode=%s" % lefthost,
                                 "--rightnode=%s" % righthost], raiseonerr=False)
    if result.returncode == 0:
        return {'leftnode': lefthost,
                'rightnode': righthost,
                'name': segment_name}, ""
    else:
        return {}, result.stderr_text


def destroy_segment(master, segment_name):
    """
    Destroys topology segment.
    :param master: reference to master object of class Host
    :param segment_name: name of the segment to be created
    """
    assert isinstance(master, Host), "master should be an instance of Host"
    kinit_admin(master)
    command = ["ipa",
               "topologysegment-del",
               DOMAIN_SUFFIX_NAME,
               segment_name]
    result = master.run_command(command, raiseonerr=False)
    return result.returncode, result.stderr_text


def get_topo(name_or_func):
    """Get a topology function by name

    A topology function receives a master and list of replicas, and yields
    (parent, child) pairs, where "child" should be installed from "parent"
    (or just connected if already installed)

    If a callable is given instead of name, it is returned directly
    """
    if callable(name_or_func):
        return name_or_func
    return topologies[name_or_func]


def _topo(name):
    """Decorator that registers a function in topologies under a given name"""
    def add_topo(func):
        topologies[name] = func
        return func
    return add_topo
topologies = collections.OrderedDict()


@_topo('star')
def star_topo(master, replicas):
    r"""All replicas are connected to the master

          Rn R1 R2
           \ | /
        R7-- M -- R3
           / | \
          R6 R5 R4
    """
    for replica in replicas:
        yield master, replica


@_topo('line')
def line_topo(master, replicas):
    r"""Line topology

          M
           \
           R1
            \
            R2
             \
             R3
              \
              ...
    """
    for replica in replicas:
        yield master, replica
        master = replica


@_topo('complete')
def complete_topo(master, replicas):
    r"""Each host connected to each other host

          M--R1
          |\/|
          |/\|
         R2-R3
    """
    for replica in replicas:
        yield master, replica
    for replica1, replica2 in itertools.combinations(replicas, 2):
        yield replica1, replica2


@_topo('tree')
def tree_topo(master, replicas):
    r"""Binary tree topology

             M
            / \
           /   \
          R1   R2
         /  \  / \
        R3 R4 R5 R6
       /
      R7 ...

    """
    replicas = list(replicas)

    def _masters():
        for host in [master] + replicas:
            yield host
            yield host

    for parent, child in zip(_masters(), replicas):
        yield parent, child


@_topo('tree2')
def tree2_topo(master, replicas):
    r"""First replica connected directly to master, the rest in a line

          M
         / \
        R1 R2
            \
            R3
             \
             R4
              \
              ...

    """
    if replicas:
        yield master, replicas[0]
    for replica in replicas[1:]:
        yield master, replica
        master = replica


def install_topo(topo, master, replicas, clients,
                 skip_master=False, setup_replica_cas=True):
    """Install IPA servers and clients in the given topology"""
    replicas = list(replicas)
    installed = {master}
    if not skip_master:
        install_master(master)

    add_a_records_for_hosts_in_master_domain(master)

    for parent, child in get_topo(topo)(master, replicas):
        if child in installed:
            log.info('Connecting replica %s to %s' % (parent, child))
            connect_replica(parent, child)
        else:
            log.info('Installing replica %s from %s' % (parent, child))
            install_replica(parent, child, setup_ca=setup_replica_cas)
        installed.add(child)
    install_clients([master] + replicas, clients)


def install_clients(servers, clients):
    """Install IPA clients, distributing them among the given servers"""
    for server, client in itertools.izip(itertools.cycle(servers), clients):
        log.info('Installing client %s on %s' % (server, client))
        install_client(server, client)


def _entries_to_ldif(entries):
    """Format LDAP entries as LDIF"""
    lines = []
    io = StringIO()
    writer = LDIFWriter(io)
    for entry in entries:
        writer.unparse(str(entry.dn), dict(entry))
    return io.getvalue()


def wait_for_replication(ldap, timeout=30):
    """Wait until updates on all replication agreements are done (or failed)

    :param ldap: LDAP client
        autenticated with necessary rights to read the mapping tree
    :param timeout: Maximum time to wait, in seconds

    Note that this waits for updates originating on this host, not those
    coming from other hosts.
    """
    log.debug('Waiting for replication to finish')
    for i in range(timeout):
        time.sleep(1)
        status_attr = 'nsds5replicaLastUpdateStatus'
        progress_attr = 'nsds5replicaUpdateInProgress'
        entries = ldap.get_entries(
            DN(('cn', 'mapping tree'), ('cn', 'config')),
            filter='(objectclass=nsds5replicationagreement)',
            attrs_list=[status_attr, progress_attr])
        log.debug('Replication agreements: \n%s', _entries_to_ldif(entries))
        if any(not e.single_value[status_attr].startswith('0 ')
               for e in entries):
            log.error('Replication error')
            continue
        if any(e.single_value[progress_attr] == 'TRUE' for e in entries):
            log.debug('Replication in progress (waited %s/%ss)',
                      i, timeout)
        else:
            log.debug('Replication finished')
            break
    else:
        log.error('Giving up wait for replication to finish')


def add_a_records_for_hosts_in_master_domain(master):
    for host in master.domain.hosts:
        # We don't need to take care of the zone creation since it is master
        # domain
        try:
            verify_host_resolvable(host.hostname, log)
            log.debug("The host (%s) is resolvable." % host.domain.name)
        except errors.DNSNotARecordError:
            log.debug("Hostname (%s) does not have A/AAAA record. Adding new one.",
                     master.hostname)
            add_a_record(master, host)


def add_a_record(master, host):
    # Find out if the record is already there
    cmd = master.run_command(['ipa',
                              'dnsrecord-show',
                              master.domain.name,
                              host.hostname + "."],
                             raiseonerr=False)

    # If not, add it
    if cmd.returncode != 0:
        master.run_command(['ipa',
                            'dnsrecord-add',
                            master.domain.name,
                            host.hostname + ".",
                            '--a-rec', host.ip])


def resolve_record(nameserver, query, rtype="SOA", retry=True, timeout=100):
    """Resolve DNS record
    :retry: if resolution failed try again until timeout is reached
    :timeout: max period of time while method will try to resolve query
     (requires retry=True)
    """
    res = dns.resolver.Resolver()
    res.nameservers = [nameserver]
    res.lifetime = 10  # wait max 10 seconds for reply

    wait_until = time.time() + timeout

    while time.time() < wait_until:
        try:
            ans = res.query(query, rtype)
            return ans
        except dns.exception.DNSException:
            if not retry:
                raise
        time.sleep(1)


def ipa_backup(master):
    result = master.run_command(["ipa-backup"])
    path_re = re.compile("^Backed up to (?P<backup>.*)$", re.MULTILINE)
    matched = path_re.search(result.stdout_text + result.stderr_text)
    return matched.group("backup")


def ipa_restore(master, backup_path):
    master.run_command(["ipa-restore", "-U",
                        "-p", master.config.dirman_password,
                        backup_path])


def install_kra(host, domain_level=None, first_instance=False, raiseonerr=True):
    if domain_level is None:
        domain_level = domainlevel(host)
    command = ["ipa-kra-install", "-U"]
    if domain_level == DOMAIN_LEVEL_0 and not first_instance:
        replica_file = get_replica_filename(host)
        command.append(replica_file)
    return host.run_command(command, raiseonerr=raiseonerr)


def install_ca(host, domain_level=None, first_instance=False, raiseonerr=True):
    if domain_level is None:
        domain_level = domainlevel(host)
    command = ["ipa-ca-install", "-U", "-p", host.config.dirman_password,
               "-P", 'admin', "-w", host.config.admin_password]
    if domain_level == DOMAIN_LEVEL_0 and not first_instance:
        replica_file = get_replica_filename(host)
        command.append(replica_file)
    return host.run_command(command, raiseonerr=raiseonerr)


def install_dns(host, raiseonerr=True):
    args = [
        "ipa-dns-install",
        "--forwarder", host.config.dns_forwarder,
        "-U",
    ]
    return host.run_command(args, raiseonerr=raiseonerr)


def uninstall_replica(master, replica):
    master.run_command(["ipa-replica-manage", "del", "--force",
                        "-p", master.config.dirman_password,
                        replica.hostname], raiseonerr=False)
    uninstall_master(replica)
