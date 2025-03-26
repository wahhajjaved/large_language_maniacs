"""
System settings
===============
"""
from __future__ import with_statement

from fabric.api import hide, run, settings

from fabtools.files import is_file
from fabtools.utils import run_as_root


def distrib_id():
    """
    Get the OS distribution ID.

    Returns one of ``"Debian"``, ``"Ubuntu"``, ``"RHEL"``, ``"CentOS"``,
    ``"Fedora"``, ``"Archlinux"``...

    Example::

        from fabtools.system import distrib_id

        if distrib_id() != 'Debian':
            abort(u"Distribution is not supported")

    """
    # lsb_release works on Ubuntu and Debian >= 6.0
    # but is not always included in other distros
    if is_file('/usr/bin/lsb_release'):
        with settings(hide('running', 'stdout')):
            return run('lsb_release --id --short')
    else:
        if is_file('/etc/debian_version'):
            return "Debian"
        elif is_file('/etc/fedora-release'):
            return "Fedora"
        elif is_file('/etc/arch-release'):
            return "Archlinux"
        elif is_file('/etc/redhat-release'):
            release = run('cat /etc/redhat-release')
            if release.startswith('Red Hat Enterprise Linux'):
                return "RHEL"
            elif release.startswith('CentOS'):
                return "CentOS"
            elif release.startswith('Scientific Linux'):
                return "SLES"


def distrib_release():
    """
    Get the release number of the Linux distribution.

    Example::

        from fabtools.system import distrib_id, distrib_release

        if distrib_id() == 'CentOS' and distrib_release() == '6.1':
            print(u"CentOS 6.2 has been released. Please upgrade.")

    """
    with settings(hide('running', 'stdout')):
        return run('lsb_release -r --short')


def distrib_codename():
    """
    Get the codename of the Linux distribution.

    Example::

        from fabtools.deb import distrib_codename

        if distrib_codename() == 'precise':
            print(u"Ubuntu 12.04 LTS detected")

    """
    with settings(hide('running', 'stdout')):
        return run('lsb_release --codename --short')


def distrib_desc():
    """
    Get the description of the Linux distribution.

    For example: ``Debian GNU/Linux 6.0.7 (squeeze)``.
    """
    with settings(hide('running', 'stdout')):
        if not is_file('/etc/redhat-release'):
            return run('lsb_release --desc --short')
        return run('cat /etc/redhat-release')


def distrib_family():
    """
    Get the distribution family.

    Returns one of ``debian``, ``redhat``, ``other``.
    """
    distrib = distrib_id()
    if distrib in ['Debian', 'Ubuntu']:
        return 'debian'
    elif distrib in ['RHEL', 'CentOS', 'Fedora']:
        return 'redhat'
    else:
        return 'other'


def get_hostname():
    """
    Get the fully qualified hostname.
    """
    with settings(hide('running', 'stdout')):
        return run('hostname --fqdn')


def set_hostname(hostname, persist=True):
    """
    Set the hostname.
    """
    run_as_root('hostname %s' % hostname)
    if persist:
        run_as_root('echo %s >/etc/hostname' % hostname)


def get_sysctl(key):
    """
    Get a kernel parameter.

    Example::

        from fabtools.system import get_sysctl

        print "Max number of open files:", get_sysctl('fs.file-max')

    """
    with settings(hide('running', 'stdout')):
        return run_as_root('/sbin/sysctl -n -e %(key)s' % locals())


def set_sysctl(key, value):
    """
    Set a kernel parameter.

    Example::

        import fabtools

        # Protect from SYN flooding attack
        fabtools.system.set_sysctl('net.ipv4.tcp_syncookies', 1)

    """
    run_as_root('/sbin/sysctl -n -e -w %(key)s=%(value)s' % locals())


def supported_locales():
    """
    Gets the list of supported locales.

    Each locale is returned as a ``(locale, charset)`` tuple.
    """
    with settings(hide('running', 'stdout')):
        if distrib_id() == "Archlinux":
            res = run("cat /etc/locale.gen")
        else:
            res = run('cat /usr/share/i18n/SUPPORTED')
    return [line.split(' ') for line in res.splitlines() if not line.startswith('#')]


def get_arch():
    """
    Get the CPU architecture.

    Example::

        from fabtools.system import get_arch

        if get_arch() == 'x86_64':
            print(u"Running on a 64-bit Intel/AMD system")

    """
    with settings(hide('running', 'stdout')):
        arch = run('uname -m')
        return arch


def cpus():
    """
    Get the number of CPU cores.

    Example::

        from fabtools.system import cpus

        nb_workers = 2 * cpus() + 1

    """
    with settings(hide('running', 'stdout')):
        res = run('python -c "import multiprocessing ; print(multiprocessing.cpu_count())"')
        return int(res)
