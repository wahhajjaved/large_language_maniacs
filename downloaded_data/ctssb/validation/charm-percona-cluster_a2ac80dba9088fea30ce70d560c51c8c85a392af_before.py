''' General utilities for percona '''
import re
import subprocess
from subprocess import Popen, PIPE
import socket
import tempfile
import os
from charmhelpers.core.host import (
    lsb_release
)
from charmhelpers.core.hookenv import (
    unit_get,
    relation_ids,
    related_units,
    relation_get,
    relation_set,
    local_unit,
    config,
    log,
    INFO
)
from charmhelpers.fetch import (
    apt_install,
    filter_installed_packages
)
from charmhelpers.contrib.network.ip import (
    get_ipv6_addr
)
from mysql import get_mysql_root_password, MySQLHelper


try:
    import jinja2
except ImportError:
    apt_install(filter_installed_packages(['python-jinja2']),
                fatal=True)
    import jinja2

try:
    import dns.resolver
except ImportError:
    apt_install(filter_installed_packages(['python-dnspython']),
                fatal=True)
    import dns.resolver

PACKAGES = [
    'percona-xtradb-cluster-server-5.5',
    'percona-xtradb-cluster-client-5.5',
]

KEY = "keys/repo.percona.com"
REPO = """deb http://repo.percona.com/apt {release} main
deb-src http://repo.percona.com/apt {release} main"""
MY_CNF = "/etc/mysql/my.cnf"
SEEDED_MARKER = "/var/lib/mysql/seeded"
HOSTS_FILE = '/etc/hosts'


def seeded():
    ''' Check whether service unit is already seeded '''
    return os.path.exists(SEEDED_MARKER)


def mark_seeded():
    ''' Mark service unit as seeded '''
    with open(SEEDED_MARKER, 'w') as seeded:
        seeded.write('done')


def setup_percona_repo():
    ''' Configure service unit to use percona repositories '''
    with open('/etc/apt/sources.list.d/percona.list', 'w') as sources:
        sources.write(REPO.format(release=lsb_release()['DISTRIB_CODENAME']))
    subprocess.check_call(['apt-key', 'add', KEY])

TEMPLATES_DIR = 'templates'


def render_template(template_name, context, template_dir=TEMPLATES_DIR):
    templates = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir))
    template = templates.get_template(template_name)
    return template.render(context)


def get_host_ip(hostname=None):
    if config('prefer-ipv6'):
        get_ipv6_addr(exc_list=[config('vip')])[0]
        return socket.gethostname()

    hostname = hostname or unit_get('private-address')
    try:
        # Test to see if already an IPv4 address
        socket.inet_aton(hostname)
        return hostname
    except socket.error:
        # This may throw an NXDOMAIN exception; in which case
        # things are badly broken so just let it kill the hook
        answers = dns.resolver.query(hostname, 'A')
        if answers:
            return answers[0].address


def get_cluster_hosts():
    hosts = []
    hosts_map = {}
    for relid in relation_ids('cluster'):
        for unit in related_units(relid):
            private_address = relation_get('private-address', unit, relid)

            if config('prefer-ipv6'):
                hosts.append(get_host_ip())
                hostname = relation_get('hostname', unit, relid)
                if not hostname:
                    log("No hostname provided by cluster relation for addr "
                        "%s" % (private_address))
                    continue
                else:
                    log("hostname '%s' provided by cluster relation for addr "
                        "%s" % (hostname, private_address))

                hosts_map[private_address] = hostname
                hosts.append(hostname)
            else:
                hosts.append(get_host_ip(private_address))

    update_hosts_file(hosts_map)
    return hosts

SQL_SST_USER_SETUP = "GRANT RELOAD, LOCK TABLES, REPLICATION CLIENT ON *.*" \
    " TO 'sstuser'@'localhost' IDENTIFIED BY '{}'"


def configure_sstuser(sst_password):
    m_helper = MySQLHelper()
    m_helper.connect(password=get_mysql_root_password())
    m_helper.execute(SQL_SST_USER_SETUP.format(sst_password))


# TODO: mysql charmhelper
def configure_mysql_root_password(password):
    ''' Configure debconf with root password '''
    dconf = Popen(['debconf-set-selections'], stdin=PIPE)
    # Set both percona and mysql password options to cover
    # both upstream and distro packages.
    packages = ["percona-server-server", "mysql-server"]
    root_pass = get_mysql_root_password(password)
    for package in packages:
        dconf.stdin.write("%s %s/root_password password %s\n" %
                          (package, package, root_pass))
        dconf.stdin.write("%s %s/root_password_again password %s\n" %
                          (package, package, root_pass))
    dconf.communicate()
    dconf.wait()


# TODO: Submit for charmhelper
def relation_clear(r_id=None):
    ''' Clears any relation data already set on relation r_id '''
    settings = relation_get(rid=r_id,
                            unit=local_unit())
    for setting in settings:
        if setting not in ['public-address', 'private-address']:
            settings[setting] = None
    relation_set(relation_id=r_id,
                 **settings)


def update_hosts_file(map):
    """Percona does not currently like ipv6 addresses so we need to use dns
    names instead. In order to make them resolvable we ensure they are  in
    /etc/hosts.

    See https://bugs.launchpad.net/galera/+bug/1130595 for some more info.
    """
    with open(HOSTS_FILE, 'r') as hosts:
        lines = hosts.readlines()

    log("Updating hosts file with: %s" % (map), level=INFO)

    log("after: %s lines" % (len(lines)))
    key = re.compile("^(.+?)\s(.+)")
    newlines = []
    for ip, hostname in map.items():
        if not ip or not hostname:
            continue

        for line in lines:
            match = re.match(key, line)
            if not (match and
                    (match.group(1) == ip or
                     hostname in match.group(2).split())):
                if line not in newlines:
                    newlines.append(line)

        newlines.append("%s %s\n" % (ip, hostname))

    log("after: %s lines" % (len(newlines)))
    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        with open(tmpfile.name, 'w') as hosts:
            for line in newlines:
                hosts.write(line)

    os.rename(tmpfile.name, HOSTS_FILE)


def assert_charm_supports_ipv6():
    """Check whether we are able to support charms ipv6."""
    if lsb_release()['DISTRIB_CODENAME'].lower() < "trusty":
        raise Exception("IPv6 is not supported in the charms for Ubuntu "
                        "versions less than Trusty 14.04")
