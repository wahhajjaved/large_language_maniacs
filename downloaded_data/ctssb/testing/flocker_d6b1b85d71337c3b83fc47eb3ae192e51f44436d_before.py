# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.provision.test.test_install -*-

"""
Install flocker on a remote node.
"""

from pipes import quote
import posixpath
from textwrap import dedent
from urlparse import urljoin, urlparse
from effect import Func, Effect, Constant, parallel
from effect.retry import retry
from time import time
import yaml

from zope.interface import implementer

from eliot import write_failure
from characteristic import attributes
from pyrsistent import PClass, field
from txeffect import perform

from twisted.internet.error import ProcessTerminated

from ._libcloud import INode
from ._common import PackageSource, Variants
from ._ssh import (
    Run, Sudo,
    run_network_interacting_from_args, sudo_network_interacting_from_args,
    run, run_from_args, sudo_from_args,
    put,
    run_remotely,
)
from ._ssh._conch import make_dispatcher
from ._effect import sequence, http_get

from ..common import retry_effect_with_timeout

from flocker import __version__ as version
from flocker.cli import configure_ssh
from flocker.common.version import (
    get_installable_version, get_package_key_suffix, is_release,
)

# A systemctl sub-command to start or restart a service.  We use restart here
# so that if it is already running it gets restart (possibly necessary to
# respect updated configuration) and because restart will also start it if it
# is not running.
START = "restart"

ZFS_REPO = {
    'centos-7': "https://s3.amazonaws.com/archive.zfsonlinux.org/"
                "epel/zfs-release.el7.noarch.rpm",
}

ARCHIVE_BUCKET = 'clusterhq-archive'


class UnknownAction(Exception):
    """
    The action received is not a valid action
    """
    def __init__(self, action):
        Exception.__init__(self, action)


def tag_as_test_install(flocker_version, distribution, package_name):
    """
    Creates an effect of making an HTTP GET to a specific URL in an s3 bucket
    that has logging enabled. This is done so that when computing flocker
    downloads we can subtract the number of requests to this file.

    :param unicode flocker_version: The version of flocker being installed.
    :param unicode distribution: The distribution flocker is being installed
        on.
    :param unicode package_name: The name of the package being installed.

    :returns: An :class:`HTTPGet` ``Effect`` to retrieve a URL that flags this
        as an internal testing install.
    """
    repository_url = get_repository_url(
        distribution=distribution,
        flocker_version=flocker_version)
    repository_host = urlparse(repository_url).hostname
    tag_url = bytes(
        "https://{host}/clusterhq-internal-acceptance-test/{distribution}/"
        "{package}/{version}".format(
            host=repository_host,
            distribution=distribution,
            package=package_name,
            version=flocker_version
        )
    )
    return http_get(tag_url)


def is_rhel(distribution):
    """
    Determine whether the named distribution is a version of RHEL.

    :param bytes distribution: The name of the distribution to inspect.

    :return: ``True`` if the distribution named is a version of RHEL,
        ``False`` otherwise.
    """
    return distribution.startswith("rhel-")


def is_centos(distribution):
    """
    Determine whether the named distribution is a version of CentOS.

    :param bytes distribution: The name of the distribution to inspect.

    :return: ``True`` if the distribution named is a version of CentOS,
        ``False`` otherwise.
    """
    return distribution.startswith("centos-")


def _from_args(sudo):
    """
    Select a function for running a command, either using ``sudo(8)`` or not.

    :param bool sudo: Whether or not the returned function should apply sudo to
        the command.

    :return: If ``sudo`` is ``True``, return a function that runs a command
        using sudo.  If ``sudo`` is ``False``, return a function that runs a
        command as-is, without sudo.
    """
    if sudo:
        return sudo_network_interacting_from_args
    else:
        return run_network_interacting_from_args


def yum_install(args, package_manager="yum", sudo=False):
    """
    Install a package with ``yum`` or a ``yum``-like package manager.
    """
    return _from_args(sudo)([package_manager, "install", "-y"] + args)


def apt_get_install(args, sudo=False):
    """
    Install a package with ``apt-get``.
    """
    return _from_args(sudo)(
        ["apt-get", "-y", "install", ] + args
    )


def apt_get_update(sudo=False):
    """
    Update apt's package metadata cache.
    """
    return _from_args(sudo)(["apt-get", "update"])


def is_ubuntu(distribution):
    """
    Determine whether the named distribution is a version of Ubuntu.

    :param bytes distribution: The name of the distribution to inspect.

    :return: ``True`` if the distribution named is a version of Ubuntu,
        ``False`` otherwise.
    """
    return distribution.startswith("ubuntu-")


def get_repository_url(distribution, flocker_version):
    """
    Return the URL for the repository of a given distribution.

    For ``yum``-using distributions this gives the URL to a package that adds
    entries to ``/etc/yum.repos.d``. For ``apt``-using distributions, this
    gives the URL for a repo containing a Packages(.gz) file.

    :param bytes distribution: The Linux distribution to get a repository for.
    :param bytes flocker_version: The version of Flocker to get a repository
        for.

    :return bytes: The URL pointing to a repository of packages.
    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    distribution_to_url = {
        # TODO instead of hardcoding keys, use the _to_Distribution map
        # and then choose the name
        'centos-7': "https://{archive_bucket}.s3.amazonaws.com/"
                    "{key}/clusterhq-release$(rpm -E %dist).noarch.rpm".format(
                        archive_bucket=ARCHIVE_BUCKET,
                        key='centos',
                        ),
        # Use CentOS packages for RHEL
        'rhel-7.2': "https://{archive_bucket}.s3.amazonaws.com/"
                    "{key}/clusterhq-release$(rpm -E %dist).centos."
                    "noarch.rpm".format(
                        archive_bucket=ARCHIVE_BUCKET,
                        key='centos',
                        ),

        # This could hardcode the version number instead of using
        # ``lsb_release`` but that allows instructions to be shared between
        # versions, and for earlier error reporting if you try to install on a
        # separate version. The $(ARCH) part must be left unevaluated, hence
        # the backslash escapes (one to make shell ignore the $ as a
        # substitution marker, and then doubled to make Python ignore the \ as
        # an escape marker). The output of this value then goes into
        # /etc/apt/sources.list which does its own substitution on $(ARCH)
        # during a subsequent apt-get update

        'ubuntu-14.04': 'https://{archive_bucket}.s3.amazonaws.com/{key}/'
                        '$(lsb_release --release --short)/\\$(ARCH)'.format(
                            archive_bucket=ARCHIVE_BUCKET,
                            key='ubuntu' + get_package_key_suffix(
                                flocker_version),
                        ),

        'ubuntu-15.10': 'https://{archive_bucket}.s3.amazonaws.com/{key}/'
                        '$(lsb_release --release --short)/\\$(ARCH)'.format(
                            archive_bucket=ARCHIVE_BUCKET,
                            key='ubuntu' + get_package_key_suffix(
                                flocker_version),
                        ),
    }

    try:
        return distribution_to_url[distribution]
    except KeyError:
        raise UnsupportedDistribution()


def get_repo_options(flocker_version):
    """
    Get a list of options for enabling necessary yum repositories.

    :param bytes flocker_version: The version of Flocker to get options for.
    :return: List of bytes for enabling (or not) a testing repository.
    """
    is_dev = not is_release(flocker_version)
    if is_dev:
        return ['--enablerepo=clusterhq-testing']
    else:
        return []


class UnsupportedDistribution(Exception):
    """
    Raised if trying to support a distribution which is not supported.
    """


@attributes(['distribution'])
class DistributionNotSupported(NotImplementedError):
    """
    Raised when the provisioning step is not supported on the given
    distribution.

    :ivar bytes distribution: The distribution that isn't supported.
    """
    def __str__(self):
        return "Distribution not supported: %s" % (self.distribution,)


@implementer(INode)
class ManagedNode(PClass):
    """
    A node managed by some other system (eg by hand or by another piece of
    orchestration software).
    """
    address = field(type=bytes, mandatory=True)
    private_address = field(type=(bytes, type(None)),
                            initial=None, mandatory=True)
    distribution = field(type=bytes, mandatory=True)


def ensure_minimal_setup(package_manager):
    """
    Get any system into a reasonable state for installation.

    Although we could publish these commands in the docs, they add a lot
    of noise for many users.  Ensure that systems have sudo enabled.

    :param bytes package_manager: The package manager (apt, dnf, yum).
    :return: a sequence of commands to run on the distribution
    """
    if package_manager in ('dnf', 'yum'):
        return run_network_interacting_from_args([
            'su', 'root', '-c', [package_manager, '-y', 'install', 'sudo']
        ])
    elif package_manager == 'apt':
        return sequence([
            run_network_interacting_from_args([
                'su', 'root', '-c', ['apt-get', 'update']
            ]),
            run_network_interacting_from_args([
                'su', 'root', '-c', ['apt-get', '-y', 'install', 'sudo']
            ]),
        ])
    else:
        raise UnsupportedDistribution()


def cli_pkg_test(package_source=PackageSource()):
    """
    Check that the Flocker CLI is working and has the expected version.

    :param PackageSource package_source: The source from which to install the
        package.

    :return: An ``Effect`` to pass to a ``Dispatcher`` that supports
        ``Sequence``, ``Run``, ``Sudo``, ``Comment``, and ``Put``.
    """
    expected = package_source.version
    if not expected:
        if package_source.branch:
            # If branch is set but version isn't, we don't know the
            # latest version. In this case, just check that the version
            # can be displayed.
            return run('flocker-deploy --version')
        else:
            # If neither branch nor version is set, the latest
            # installable release will be installed.
            expected = get_installable_version(version)
    return run('test `flocker-deploy --version` = {}'.format(quote(expected)))


def wipe_yum_cache(repository):
    """
    Force yum to update the metadata for a particular repository.

    :param bytes repository: The name of the repository to clear.
    """
    return run_from_args([
        b"yum",
        b"--disablerepo=*",
        b"--enablerepo=" + repository,
        b"clean",
        b"expire-cache"
    ])


def install_commands_yum(package_name, distribution, package_source, base_url):
    """
    Install Flocker package on CentOS and RHEL.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param str package_name: The name of the package to install.
    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    :param bytes base_url: URL of repository, or ``None`` if we're not using
        development branch.

    :return: a sequence of commands to run on the distribution
    """
    flocker_version = package_source.version
    if not flocker_version:
        # support empty values other than None, as '' sometimes used to
        # indicate latest version, due to previous behaviour
        flocker_version = get_installable_version(version)
    repo_package_name = 'clusterhq-release'
    commands = [
        # If package has previously been installed, 'yum install' fails,
        # so check if it is installed first.
        # XXX This needs retry
        run(
            command="yum list installed {} || yum install -y {}".format(
                quote(repo_package_name),
                get_repository_url(
                    distribution=distribution,
                    flocker_version=flocker_version))),
        ]

    if base_url is not None:
        repo = dedent(b"""\
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            # There is a distinct clusterhq-build repository for each branch.
            # The metadata across these different repositories varies.  Version
            # numbers are not comparable.  A version which exists in one likely
            # does not exist in another.  In order to support switching between
            # branches (and therefore between clusterhq-build repositories),
            # tell yum to always update metadata for this repository.
            metadata_expire=0
            """) % (base_url,)
        commands.append(put(content=repo,
                            path='/tmp/clusterhq-build.repo'))
        commands.append(run_from_args([
            'cp', '/tmp/clusterhq-build.repo',
            '/etc/yum.repos.d/clusterhq-build.repo']))
        if is_rhel(distribution):
            # Update RHEL releaseversion with CentOS 7 in clusterhq build repo.
            commands.append(run_from_args([
                            'sed', '-i', 's/$releasever/7/g',
                            '/etc/yum.repos.d/clusterhq.repo']))
            commands.append(run_from_args([
                            'cat', '/etc/yum.repos.d/clusterhq.repo']))
        repo_options = ['--enablerepo=clusterhq-build']
    else:
        repo_options = get_repo_options(
            flocker_version=get_installable_version(version))

    base_package = package_name
    os_version = package_source.os_version()
    if os_version:
        package_name += '-%s' % (os_version,)

    # Execute a request to s3 so that this can be tagged as a test install for
    # statistical tracking.
    if base_url is None:
        commands.append(tag_as_test_install(flocker_version,
                                            distribution,
                                            base_package))

    # Install package and all dependencies:

    commands.append(yum_install(repo_options + [package_name]))

    return sequence(commands)


def install_commands_ubuntu(package_name, distribution, package_source,
                            base_url):
    """
    Install Flocker package on Ubuntu.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.
    :param base_url: URL of repository, or ``None`` if we're not using
        development branch.

    :return: a sequence of commands to run on the distribution
    """
    flocker_version = package_source.version
    if not flocker_version:
        # support empty values other than None, as '' sometimes used to
        # indicate latest version, due to previous behaviour
        flocker_version = get_installable_version(version)
    repository_url = get_repository_url(
        distribution=distribution,
        flocker_version=flocker_version)
    commands = [
        # Minimal images often have cleared apt caches and are missing
        # packages that are common in a typical release.  These commands
        # ensure that we start from a good base system with the required
        # capabilities, particularly that the add-apt-repository command
        # is available, and HTTPS URLs are supported.
        apt_get_update(),
        apt_get_install(["apt-transport-https", "software-properties-common"]),

        # Add ClusterHQ repo for installation of Flocker packages.
        # XXX This needs retry
        run(command='add-apt-repository -y "deb {} /"'.format(repository_url))
        ]

    pinned_host = urlparse(repository_url).hostname

    if base_url is not None:
        # Add BuildBot repo for running tests
        commands.append(run_network_interacting_from_args([
            "add-apt-repository", "-y", "deb {} /".format(base_url)]))
        # During a release, or during upgrade testing, we might not be able to
        # rely on package management to install flocker from the correct
        # server. Thus, in all cases we pin precisely which url we want to
        # install flocker from.
        pinned_host = urlparse(package_source.build_server).hostname
    commands.append(put(dedent('''\
        Package: *
        Pin: origin {}
        Pin-Priority: 700
    '''.format(pinned_host)), '/tmp/apt-pref'))
    commands.append(run_from_args([
        'mv', '/tmp/apt-pref', '/etc/apt/preferences.d/buildbot-700']))

    # Update to read package info from new repos
    commands.append(apt_get_update())

    base_package = package_name
    os_version = package_source.os_version()

    if os_version:
        # Set the version of the top-level package
        package_name += '=%s' % (os_version,)

        # If a specific version is required, ensure that the version for
        # all ClusterHQ packages is consistent.  This prevents conflicts
        # between the top-level package, which may depend on a lower
        # version of a dependency, and apt, which wants to install the
        # most recent version.  Note that this trumps the Buildbot
        # pinning above.
        commands.append(put(dedent('''\
            Package: clusterhq-*
            Pin: version {}
            Pin-Priority: 900
        '''.format(os_version)), '/tmp/apt-pref'))
        commands.append(run_from_args([
            'mv', '/tmp/apt-pref', '/etc/apt/preferences.d/clusterhq-900']))

    # Execute a request to s3 so that this can be tagged as a test install for
    # statistical tracking.
    if base_url is None:
        commands.append(tag_as_test_install(flocker_version,
                                            distribution,
                                            base_package))

    # Install package and all dependencies
    # We use --force-yes here because our packages aren't signed.
    commands.append(apt_get_install(["--force-yes", package_name]))

    return sequence(commands)


def task_package_install(package_name, distribution,
                         package_source=PackageSource()):
    """
    Install Flocker package on a distribution.

    The ClusterHQ repo is added for downloading latest releases.  If
    ``package_source`` contains a branch, then a BuildBot repo will also
    be added to the package search path, to use in-development packages.
    Note, the ClusterHQ repo is always enabled, to provide dependencies.

    :param str package_name: The name of the package to install.
    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    if package_source.branch:
        # A development branch has been selected - add its Buildbot repo.
        # Install CentOS packages.
        package_distribution = distribution
        if package_distribution == 'rhel-7.2':
            package_distribution = 'centos-7'
        result_path = posixpath.join(
            '/results/omnibus/', package_source.branch, package_distribution)
        base_url = urljoin(package_source.build_server, result_path)
    else:
        base_url = None

    if is_centos(distribution) or is_rhel(distribution):
        installer = install_commands_yum
    elif is_ubuntu(distribution):
        installer = install_commands_ubuntu
    else:
        raise UnsupportedDistribution()
    return installer(package_name, distribution, package_source,
                     base_url)


def task_cli_pkg_install(distribution, package_source=PackageSource()):
    """
    Install the Flocker CLI package.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :return: a sequence of commands to run on the distribution
    """
    commands = task_package_install("clusterhq-flocker-cli", distribution,
                                    package_source)
    # Although client testing is currently done as root.e want to use
    # sudo for better documentation output.
    return sequence([
        (Effect(Sudo(command=e.intent.command,
                     log_command_filter=e.intent.log_command_filter))
         if isinstance(e.intent, Run) else e)
        for e in commands.intent.effects])


PIP_CLI_PREREQ_APT = [
    'gcc',
    'libffi-dev',
    'libssl-dev',
    'python2.7',
    'python2.7-dev',
    'python-virtualenv',
]

PIP_CLI_PREREQ_YUM = [
    'gcc',
    'libffi-devel',
    'openssl-devel',
    'python',
    'python-devel',
    'python-virtualenv',
]


def task_cli_pip_prereqs(package_manager):
    """
    Install the pre-requisites for pip installation of the Flocker client.

    :param bytes package_manager: The package manager (apt, dnf, yum).
    :return: an Effect to install the pre-requisites.
    """
    if package_manager in ('dnf', 'yum'):
        return yum_install(
            PIP_CLI_PREREQ_YUM, package_manager=package_manager, sudo=True,
        )
    elif package_manager == 'apt':
        return sequence([
            apt_get_update(sudo=True),
            apt_get_install(PIP_CLI_PREREQ_APT, sudo=True),
        ])
    else:
        raise UnsupportedDistribution()


def _get_wheel_version(package_source):
    """
    Get the latest available wheel version for the specified package source.

    If package source version is not set, the latest installable release
    will be installed.  Note, branch is never used for wheel
    installations, since the wheel file is not created for branches.

    :param PackageSource package_source: The source from which to install the
        package.

    :return: a string containing the previous installable version of
        either the package version, or, if that is not specified, of the
        current version.
    """
    return get_installable_version(package_source.version or version)


def task_cli_pip_install(
        venv_name='flocker-client', package_source=PackageSource()):
    """
    Install the Flocker client into a virtualenv using pip.

    :param bytes venv_name: Name for the virtualenv.
    :param package_source: Package source description
    :return: an Effect to install the client.
    """
    url = (
        'https://{bucket}.s3.amazonaws.com/{key}/'
        'Flocker-{version}-py2-none-any.whl'.format(
            bucket=ARCHIVE_BUCKET, key='python',
            version=_get_wheel_version(package_source))
        )
    return sequence([
        run_from_args(
            ['virtualenv', '--python=/usr/bin/python2.7', venv_name]),
        run_from_args(['source', '{}/bin/activate'.format(venv_name)]),
        run_from_args(['pip', 'install', '--upgrade', 'pip']),
        run_from_args(
            ['pip', 'install', url]),
        ])


def cli_pip_test(venv_name='flocker-client', package_source=PackageSource()):
    """
    Test the Flocker client installed in a virtualenv.

    :param bytes venv_name: Name for the virtualenv.
    :return: an Effect to test the client.
    """
    return sequence([
        run_from_args(['source', '{}/bin/activate'.format(venv_name)]),
        run('test `flocker-deploy --version` = {}'.format(
            quote(_get_wheel_version(package_source))))
        ])


def task_install_ssh_key():
    """
    Install the authorized ssh keys of the current user for root as well.
    """
    return sequence([
        sudo_from_args(['cp', '.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys']),
    ])


def task_upgrade_kernel(distribution):
    """
    Upgrade kernel.
    """
    if is_centos(distribution):
        return sequence([
            yum_install(["kernel-devel", "kernel"]),
            run_from_args(['sync']),
        ])
    elif distribution == 'ubuntu-14.04':
        # Not required.
        return sequence([])
    else:
        raise DistributionNotSupported(distribution=distribution)


def _remove_private_key(content):
    """
    Remove most of the contents of a private key file for logging.
    """
    prefix = '-----BEGIN PRIVATE KEY-----'
    suffix = '-----END PRIVATE KEY-----'
    start = content.find(prefix)
    if start < 0:
        # no private key
        return content
    # Keep prefix, subsequent newline, and 4 characters at start of key
    trim_start = start + len(prefix) + 5
    end = content.find(suffix, trim_start)
    if end < 0:
        end = len(content)
    # Keep suffix and previous 4 characters and newline at end of key
    trim_end = end - 5
    if trim_end <= trim_start:
        # strangely short key, keep all content
        return content
    return content[:trim_start] + '...REMOVED...' + content[trim_end:]


def task_install_control_certificates(ca_cert, control_cert, control_key):
    """
    Install certificates and private key required by the control service.

    :param FilePath ca_cert: Path to CA certificate on local machine.
    :param FilePath control_cert: Path to control service certificate on
        local machine.
    :param FilePath control_key: Path to control service private key
        local machine.
    """
    # Be better if permissions were correct from the start.
    # https://clusterhq.atlassian.net/browse/FLOC-1922
    return sequence([
        run('mkdir -p /etc/flocker'),
        run('chmod u=rwX,g=,o= /etc/flocker'),
        put(path="/etc/flocker/cluster.crt", content=ca_cert.getContent()),
        put(path="/etc/flocker/control-service.crt",
            content=control_cert.getContent()),
        put(path="/etc/flocker/control-service.key",
            content=control_key.getContent(),
            log_content_filter=_remove_private_key),
        ])


def task_install_node_certificates(ca_cert, node_cert, node_key):
    """
    Install certificates and private key required by a node.

    :param FilePath ca_cert: Path to CA certificate on local machine.
    :param FilePath node_cert: Path to node certificate on
        local machine.
    :param FilePath node_key: Path to node private key
        local machine.
    """
    # Be better if permissions were correct from the start.
    # https://clusterhq.atlassian.net/browse/FLOC-1922
    return sequence([
        run('mkdir -p /etc/flocker'),
        run('chmod u=rwX,g=,o= /etc/flocker'),
        put(path="/etc/flocker/cluster.crt", content=ca_cert.getContent()),
        put(path="/etc/flocker/node.crt",
            content=node_cert.getContent()),
        put(path="/etc/flocker/node.key",
            content=node_key.getContent(),
            log_content_filter=_remove_private_key),
        ])


def task_install_api_certificates(api_cert, api_key):
    """
    Install certificate and private key required by Docker plugin to
    access the Flocker REST API.

    :param FilePath api_cert: Path to API certificate on local machine.
    :param FilePath api_key: Path to API private key local machine.
    """
    # Be better if permissions were correct from the start.
    # https://clusterhq.atlassian.net/browse/FLOC-1922
    return sequence([
        run('mkdir -p /etc/flocker'),
        run('chmod u=rwX,g=,o= /etc/flocker'),
        put(path="/etc/flocker/plugin.crt",
            content=api_cert.getContent()),
        put(path="/etc/flocker/plugin.key",
            content=api_key.getContent(),
            log_content_filter=_remove_private_key),
        ])


def task_enable_docker(distribution):
    """
    Configure docker.

    We don't actually start it (or on Ubuntu, restart it) at this point
    since the certificates it relies on have yet to be installed.
    """
    # Use the Flocker node TLS certificate, since it's readily
    # available.
    docker_tls_options = (
        '--tlsverify --tlscacert=/etc/flocker/cluster.crt'
        ' --tlscert=/etc/flocker/node.crt --tlskey=/etc/flocker/node.key'
        ' -H=0.0.0.0:2376')

    if is_centos(distribution) or is_rhel(distribution):
        conf_path = (
            "/etc/systemd/system/docker.service.d/01-TimeoutStartSec.conf"
        )
        return sequence([
            # Give Docker a long time to start up.  On the first start, it
            # initializes a 100G filesystem which can take a while.  The
            # default startup timeout is frequently too low to let this
            # complete.
            run("mkdir -p /etc/systemd/system/docker.service.d"),
            put(
                path=conf_path,
                content=dedent(
                    """\
                    [Service]
                    TimeoutStartSec=10min
                    """
                ),
            ),
            put(path="/etc/systemd/system/docker.service.d/02-TLS.conf",
                content=dedent(
                    """\
                    [Service]
                    ExecStart=
                    ExecStart=/usr/bin/docker daemon -H fd:// {}
                    """.format(docker_tls_options))),
            run_from_args(["systemctl", "enable", "docker.service"]),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            put(path="/etc/default/docker",
                content=(
                    'DOCKER_OPTS="-H unix:///var/run/docker.sock {}"'.format(
                        docker_tls_options))),
            ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def open_firewalld(service):
    """
    Open firewalld port for a service.

    :param str service: Name of service.
    """
    return sequence([run_from_args(['firewall-cmd', '--reload'])] + [
        run_from_args(command + [service])
        for command in [['firewall-cmd', '--permanent', '--add-service'],
                        ['firewall-cmd', '--add-service']]])


def open_ufw(service):
    """
    Open ufw port for a service.

    :param str service: Name of service.
    """
    return sequence([
        run_from_args(['ufw', 'allow', service])
        ])


def task_enable_flocker_control(distribution, action="start"):
    """
    Enable flocker-control service. We need to be able to indicate whether
    we want to start the service, when we are deploying a new cluster,
    or if we want to restart it, when we are using an existent cluster in
    managed mode.

    :param bytes distribution: name of the distribution where the flocker
        controls currently runs. The supported distros are:
            - ubuntu-14.04
            - centos-<centos version>
    :param bytes action: action to perform with the flocker control service.
        Currently, we support:
            -start
            -stop

    :raises ``DistributionNotSupported`` if the ``distribution`` is not
            currently supported
            ``UnknownAction`` if the action passed is not a valid one
    """
    validate_start_action(action)

    if is_centos(distribution) or is_rhel(distribution):
        return sequence([
            run_from_args(['systemctl', 'enable', 'flocker-control']),
            run_from_args(['systemctl', action.lower(), 'flocker-control']),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            put(
                path='/etc/init/flocker-control.override',
                content=dedent('''\
                    start on runlevel [2345]
                    stop on runlevel [016]
                    '''),
            ),
            run("echo 'flocker-control-api\t4523/tcp\t\t\t# Flocker Control API port' >> /etc/services"),  # noqa
            run("echo 'flocker-control-agent\t4524/tcp\t\t\t# Flocker Control Agent port' >> /etc/services"),  # noqa
            run_from_args(['service', 'flocker-control', action.lower()]),
        ])

    else:
        raise DistributionNotSupported(distribution=distribution)


def validate_start_action(action):
    """
    Validates if the action given is a valid one  - currently only
    start and restart are supported
    """
    valid_actions = ["start", "restart"]
    if action.lower() not in valid_actions:
        raise UnknownAction(action)


def task_enable_docker_plugin(distribution):
    """
    Enable the Flocker Docker plugin.

    :param bytes distribution: The distribution name.
    """
    if is_centos(distribution):
        return sequence([
            run_from_args(['systemctl', 'enable', 'flocker-docker-plugin']),
            run_from_args(['systemctl', START, 'flocker-docker-plugin']),
            run_from_args(['systemctl', START, 'docker']),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            run_from_args(['service', 'flocker-docker-plugin', 'restart']),
            run_from_args(['service', 'docker', 'restart']),
        ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def task_open_control_firewall(distribution):
    """
    Open the firewall for flocker-control.
    """
    if is_centos(distribution) or is_rhel(distribution):
        open_firewall = open_firewalld
    elif distribution == 'ubuntu-14.04':
        open_firewall = open_ufw
    else:
        raise DistributionNotSupported(distribution=distribution)
    return sequence([
        open_firewall(service)
        for service in ['flocker-control-api', 'flocker-control-agent']
    ])


def catch_exit_code(expected_exit_code):
    """
    :param int expected_exit_code: The expected exit code of the process.
    :returns: An error handler function which accepts a 3-tuple(exception_type,
        exception, None) and re-raises ``exception`` if the exit code is not
        ``expected_exit_code`.
    """
    def error_handler(result):
        exception_type, exception = result[:2]
        if((exception_type is not ProcessTerminated) or
           (exception.exitCode != expected_exit_code)):
            raise exception
    return error_handler


def if_firewall_available(distribution, commands):
    """
    Open the firewall for remote access to control service if firewall command
    is available.
    """
    if is_centos(distribution):
        firewall_command = b'firewall-cmd'
    elif distribution == 'ubuntu-14.04':
        firewall_command = b'ufw'
    else:
        raise DistributionNotSupported(distribution=distribution)

    # Only run the commands if the firewall command is available.
    return run_from_args([b'which', firewall_command]).on(
        success=lambda result: commands,
        error=catch_exit_code(1),
    )


def open_firewall_for_docker_api(distribution):
    """
    Open the firewall for remote access to Docker API.
    """
    if is_centos(distribution):
        upload = put(path="/usr/lib/firewalld/services/docker.xml",
                     content=dedent(
                         """\
                         <?xml version="1.0" encoding="utf-8"?>
                         <service>
                         <short>Docker API Port</short>
                         <description>The Docker API, over TLS.</description>
                         <port protocol="tcp" port="2376"/>
                         </service>
                         """))
        open_firewall = open_firewalld
    elif distribution == 'ubuntu-14.04':
        upload = put(path="/etc/ufw/applications.d/docker",
                     content=dedent(
                         """
                         [docker]
                         title=Docker API
                         description=Docker API.
                         ports=2376/tcp
                         """))
        open_firewall = open_ufw
    else:
        raise DistributionNotSupported(distribution=distribution)

    # Only configure the firewall if the firewall command line is available.
    return sequence([upload, open_firewall('docker')])


# Set of dataset fields which are *not* sensitive.  Only fields in this
# set are logged.  This should contain everything except usernames and
# passwords (or equivalents).  Implemented as a whitelist in case new
# security fields are added.
_ok_to_log = frozenset((
    'auth_plugin',
    'auth_url',
    'backend',
    'region',
    'zone',
    ))


def _remove_dataset_fields(content):
    """
    Remove non-whitelisted fields from dataset for logging.
    """
    content = yaml.safe_load(content)
    dataset = content['dataset']
    for key in dataset:
        if key not in _ok_to_log:
            dataset[key] = 'REMOVED'
    return yaml.safe_dump(content)


def task_configure_flocker_agent(
    control_node, dataset_backend, dataset_backend_configuration,
    logging_config=None,
):
    """
    Configure the flocker agents by writing out the configuration file.

    :param bytes control_node: The address of the control agent.
    :param BackendDescription dataset_backend: The volume backend the nodes are
        configured with.
    :param dict dataset_backend_configuration: The backend specific
        configuration options.
    :param dict logging_config: A Python logging configuration dictionary,
        following the structure of PEP 391.
    """
    dataset_backend_configuration = dataset_backend_configuration.copy()
    dataset_backend_configuration.update({
        u"backend": dataset_backend.name,
    })

    content = {
        "version": 1,
        "control-service": {
            "hostname": control_node,
            "port": 4524,
        },
        "dataset": dataset_backend_configuration,
    }
    if logging_config is not None:
        content['logging'] = logging_config

    put_config_file = put(
        path='/etc/flocker/agent.yml',
        content=yaml.safe_dump(content),
        log_content_filter=_remove_dataset_fields
    )
    return sequence([put_config_file])


def task_enable_flocker_agent(distribution, action="start"):
    """
    Enable the flocker agents.

    :param bytes distribution: The distribution name.
    :param bytes action: action to perform with the flocker action. Currently
                        we only support "start" and "restart"
    :raises ``DistributionNotSupported`` if the ``distribution`` is not
                currently supported.
            ``UnknownAction`` if the action passed is not a valid one
    """
    validate_start_action(action)

    if is_centos(distribution):
        return sequence([
            run_from_args(['systemctl',
                           'enable',
                           'flocker-dataset-agent']),
            run_from_args(['systemctl',
                           action.lower(),
                           'flocker-dataset-agent']),
            run_from_args(['systemctl',
                           'enable',
                           'flocker-container-agent']),
            run_from_args(['systemctl',
                           action.lower(),
                           'flocker-container-agent']),
        ])
    elif distribution == 'ubuntu-14.04':
        return sequence([
            run_from_args(['service',
                           'flocker-dataset-agent',
                           action.lower()]),
            run_from_args(['service',
                           'flocker-container-agent',
                           action.lower()]),
        ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def task_create_flocker_pool_file():
    """
    Create a file-back zfs pool for flocker.
    """
    return sequence([
        run('mkdir -p /var/opt/flocker'),
        run('truncate --size 10G /var/opt/flocker/pool-vdev'),
        # XXX - See FLOC-3018
        run('ZFS_MODULE_LOADING=yes '
            'zpool create flocker /var/opt/flocker/pool-vdev'),
    ])


def task_install_zfs(distribution, variants=set()):
    """
    Install ZFS on a node.

    :param bytes distribution: The distribution the node is running.
    :param set variants: The set of variant configurations to use when
    """
    commands = []
    if distribution == 'ubuntu-14.04':
        commands += [
            # ZFS not available in base Ubuntu - add ZFS repo
            run_network_interacting_from_args([
                "add-apt-repository", "-y", "ppa:zfs-native/stable"]),
        ]
        commands += [
            # Update to read package info from new repos
            apt_get_update(),
            # Package spl-dkms sometimes does not have libc6-dev as a
            # dependency, add it before ZFS installation requires it.
            # See https://github.com/zfsonlinux/zfs/issues/3298
            apt_get_install(["libc6-dev"]),
            apt_get_install(["zfsutils"]),
            ]

    elif is_centos(distribution):
        commands += [
            yum_install([ZFS_REPO[distribution]]),
        ]
        if distribution == 'centos-7':
            commands.append(yum_install(["epel-release"]))

        if Variants.ZFS_TESTING in variants:
            commands += [
                yum_install(['yum-utils']),
                run_from_args([
                    'yum-config-manager', '--enable', 'zfs-testing'])
            ]
        commands.append(yum_install(["zfs"]))
    else:
        raise DistributionNotSupported(distribution)

    return sequence(commands)


def configure_zfs(node, variants):
    """
    Configure ZFS for use as a Flocker backend.

    :param INode node: The node to configure ZFS on.
    :param set variants: The set of variant configurations to use when

    :return Effect:
    """
    return sequence([
        run_remotely(
            username='root',
            address=node.address,
            commands=task_upgrade_kernel(
                distribution=node.distribution),
        ),
        node.reboot(),
        run_remotely(
            username='root',
            address=node.address,
            commands=sequence([
                task_install_zfs(
                    distribution=node.distribution,
                    variants=variants),
                task_create_flocker_pool_file(),
            ]),
        ),
        Effect(
            Func(lambda: configure_ssh(node.address, 22))),
    ])


def _uninstall_flocker_ubuntu1404():
    """
    Return an ``Effect`` for uninstalling the Flocker package from an Ubuntu
    14.04 machine.
    """
    return run_from_args([
        b"apt-get", b"remove", b"-y", b"--purge", b"clusterhq-python-flocker",
    ])


def _uninstall_flocker_centos7():
    """
    Return an ``Effect`` for uninstalling the Flocker package from a CentOS 7
    machine.
    """
    def maybe_disable(unit):
        return run(
            u"{{ "
            u"systemctl is-enabled {unit} && "
            u"systemctl stop {unit} && "
            u"systemctl disable {unit} "
            u"; }} || /bin/true".format(unit=unit).encode("ascii")
        )

    return sequence(
        list(
            # XXX There should be uninstall hooks for stopping services.
            maybe_disable(unit) for unit in [
                u"flocker-control", u"flocker-dataset-agent",
                u"flocker-container-agent", u"flocker-docker-plugin",
            ]
        ) + [
            run_from_args([
                b"yum", b"erase", b"-y", b"clusterhq-python-flocker",
            ]),
            # Force yum to update the metadata for the release repositories.
            # If we are running tests against a release, it is likely that the
            # metadata will not have expired for them yet.
            wipe_yum_cache(repository="clusterhq"),
            wipe_yum_cache(repository="clusterhq-testing"),
            run_from_args([
                b"yum", b"erase", b"-y", b"clusterhq-release",
            ]),
        ]
    )


_flocker_uninstallers = {
    "ubuntu-14.04": _uninstall_flocker_ubuntu1404,
    "centos-7": _uninstall_flocker_centos7,
}


def task_uninstall_flocker(distribution):
    """
    Return an ``Effect`` for uninstalling the Flocker package from the given
    distribution.
    """
    return _flocker_uninstallers[distribution]()


def uninstall_flocker(nodes):
    """
    Return an ``Effect`` for uninstalling the Flocker package from all of the
    given nodes.
    """
    return _run_on_all_nodes(
        nodes,
        task=lambda node: task_uninstall_flocker(node.distribution)
    )


def task_install_docker(distribution):
    """
    Return an ``Effect`` for installing Docker if it is not already installed.

    The state of ``https://get.docker.com/`` at the time the task is run
    determines the version of Docker installed.

    The version of Docker is allowed to float this way because:

    * Docker development is currently proceeding at a rapid pace.  There are
    frequently compelling reasons to want to run Docker 1.(X+1) instead of 1.X.

    * https://get.docker.com/ doesn't keep very old versions of Docker around.
    Pinning a particular version makes it laborious to rely on this source for
    Docker packages (due to the pinned version frequently disappearing from the
    repository).

    * Other package repositories frequently only have older packages available.

    * Different packagers of Docker give the package different names.  The
    different package names make it more difficult to request a specific
    version.

    * Different packagers apply different system-specific patches.  Users may
    have reasons to prefer packages from one packager over another.  Thus if
    Docker is already installed, no matter what version it is, the requirement
    is considered satisfied (we treat the user as knowing what they're doing).
    """
    if is_centos(distribution):
        # The Docker packages don't declare all of their dependencies.  They
        # seem to work on an up-to-date system, though, so make sure the system
        # is up to date.
        update = b"yum --assumeyes update && "
    else:
        update = b""

    return retry_effect_with_timeout(
        run(command=(
            b"[[ -e /usr/bin/docker ]] || { " + update +
            b"curl https://get.docker.com/ > /tmp/install-docker.sh && "
            b"sh /tmp/install-docker.sh"
            b"; }"
        )),
        # Arbitrarily selected value
        timeout=5.0 * 60.0,
    )


def task_install_flocker(
    distribution=None,
    package_source=PackageSource(),
):
    """
    Install flocker cluster on a distribution.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    return task_package_install(
        "clusterhq-flocker-node",
        distribution, package_source,
    )


def task_install_docker_plugin(
    distribution=None,
    package_source=PackageSource(),
):
    """
    Install flocker docker plugin on a distribution.

    :param bytes distribution: The distribution the node is running.
    :param PackageSource package_source: The source from which to install the
        package.

    :raises: ``UnsupportedDistribution`` if the distribution is unsupported.
    """
    return task_package_install(
        "clusterhq-flocker-docker-plugin",
        distribution, package_source,
    )


ACCEPTANCE_IMAGES = [
    "postgres:latest",
    "clusterhq/mongodb:latest",
    "python:2.7-slim",
    "busybox",
]


def task_pull_docker_images(images=ACCEPTANCE_IMAGES):
    """
    Pull docker images.

    :param list images: List of images to pull. Defaults to images used in
        acceptance tests.
    """
    return sequence([
        run_from_args(['docker', 'pull', image]) for image in images
    ])


def task_enable_updates_testing(distribution):
    """
    Enable the distribution's proposed updates repository.

    :param bytes distribution: See func:`task_install_flocker`
    """
    raise DistributionNotSupported(distribution=distribution)


def task_enable_docker_head_repository(distribution):
    """
    Enable the distribution's repository containing in-development docker
    builds.

    :param bytes distribution: See func:`task_install_flocker`
    """
    if is_centos(distribution):
        return sequence([
            put(content=dedent("""\
                [virt7-testing]
                name=virt7-testing
                baseurl=http://cbs.centos.org/repos/virt7-testing/x86_64/os/
                enabled=1
                gpgcheck=0
                """),
                path="/etc/yum.repos.d/virt7-testing.repo")
        ])
    else:
        raise DistributionNotSupported(distribution=distribution)


def provision(distribution, package_source, variants):
    """
    Provision the node for running flocker.

    This drives all the common node installation steps in:
     * http://doc-dev.clusterhq.com/gettingstarted/installation.html

    :param bytes address: Address of the node to provision.
    :param bytes username: Username to connect as.
    :param bytes distribution: See func:`task_install_flocker`
    :param PackageSource package_source: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    commands = []

    if Variants.DISTRO_TESTING in variants:
        commands.append(task_enable_updates_testing(distribution))
    if Variants.DOCKER_HEAD in variants:
        commands.append(task_enable_docker_head_repository(distribution))
    commands.append(task_install_docker(distribution))
    commands.append(
        task_install_flocker(
            package_source=package_source, distribution=distribution))
    commands.append(
        task_install_docker_plugin(
            package_source=package_source, distribution=distribution))
    commands.append(task_enable_docker(distribution))
    return sequence(commands)


def _run_on_all_nodes(nodes, task):
    """
    Run some commands on some nodes.

    :param nodes: An iterable of ``Node`` instances where the commands should
        be run.
    :param task: A one-argument callable which is called with each ``Node`` and
        should return the ``Effect`` to run on that node.

    :return: An ``Effect`` that runs the commands on a group of nodes.
    """
    return parallel(list(
        run_remotely(
            username='root',
            address=node.address,
            commands=task(node),
        )
        for node in nodes
    ))


def install_flocker(nodes, package_source):
    """
    Return an ``Effect`` that installs a certain version of Flocker on the
    given nodes.

    :param nodes: An iterable of ``Node`` instances on which to install
        Flocker.
    :param PackageSource package_source: The version of Flocker to install.

    :return: An ``Effect`` which installs Flocker on the nodes.
    """
    return _run_on_all_nodes(
        nodes,
        task=lambda node: sequence([
            task_install_flocker(
                distribution=node.distribution,
                package_source=package_source,
            ),
            task_install_docker_plugin(
                distribution=node.distribution,
                package_source=package_source,
            ),
        ]),
    )


def configure_cluster(
    cluster, dataset_backend_configuration, provider, logging_config=None
):
    """
    Configure flocker-control, flocker-dataset-agent and
    flocker-container-agent on a collection of nodes.

    :param Cluster cluster: Description of the cluster to configure.

    :param dict dataset_backend_configuration: Configuration parameters to
        supply to the dataset backend.

    :param bytes provider: provider of the nodes  - aws. rackspace or managed.

    :param dict logging_config: A Python logging configuration dictionary,
        following the structure of PEP 391.
    """
    return sequence([
        configure_control_node(
            cluster,
            provider,
            logging_config,
        ),
        parallel([
            sequence([
                configure_node(
                    cluster,
                    node,
                    certnkey,
                    dataset_backend_configuration,
                    provider,
                    logging_config,
                ),
            ]) for certnkey, node
            in zip(cluster.certificates.nodes, cluster.agent_nodes)
        ])
    ])


def reinstall_flocker_from_package_source(
    reactor, nodes, control_node, package_source, distribution,
    destroy_persisted_state=False
):
    """
    Put the version of Flocker indicated by ``package_source`` onto all of
    the given nodes.

    This takes a primitive approach of uninstalling the software and then
    installing the new version instead of trying to take advantage of any
    OS-level package upgrade support.  Because it's easier.  The package
    removal step is allowed to fail in case the package is not installed
    yet (other failures are not differentiated).  The only action taken on
    failure is that the failure is logged.

    :param reactor: The reactor to use to schedule the work.
    :param nodes: An iterable of node addresses of nodes in the cluster.
    :param control_node: The address of the control node.
    :param PackageSource package_source: The version of the software to
        install.
    :param distribution: The distribution installed on the nodes.
    :param bool destroy_persisted_state: Whether to destroy the control
        node's state file when upgrading or not. This might be desirable if you
        know the nodes are clean (all datasets destroyed and all leases
        destroyed) and you are downgrading flocker.

    :return: A ``Deferred`` that fires when the software has been upgraded.
    """
    managed_nodes = list(
        ManagedNode(address=node, distribution=distribution)
        for node in nodes
    )
    dispatcher = make_dispatcher(reactor)

    uninstalling = perform(dispatcher, uninstall_flocker(managed_nodes))

    uninstalling.addErrback(write_failure, logger=None)

    def destroy_control_node_state(_):
        return perform(
            dispatcher,
            run_remotely(
                username='root',
                address=control_node,
                commands=sequence([
                    run_from_args([
                        'mv',
                        '/var/lib/flocker/current_configuration.json',
                        '/var/lib/flocker/current_configuration.json.old',
                    ]),
                ])
            ),
        )

    if destroy_persisted_state:
        uninstalling.addCallback(destroy_control_node_state)

    def install(ignored):
        return perform(
            dispatcher,
            install_flocker(managed_nodes, package_source),
        )
    uninstalling.addCallback(install)

    def restart_services(ignored):
        restart_commands = sequence([
            # First restart the control agent.
            run_remotely(
                username='root',
                address=control_node,
                commands=sequence([
                    task_enable_flocker_control(
                        distribution,
                        'restart'),
                    if_firewall_available(
                        distribution,
                        task_open_control_firewall(
                            distribution
                        )
                    ),
                ])
            ),
            # Then restart the node agents (and docker on all of the nodes).
            parallel([
                run_remotely(
                    username='root',
                    address=node.address,
                    commands=sequence([
                        task_enable_docker_plugin(node.distribution),
                        task_enable_flocker_agent(
                            distribution=node.distribution,
                            action='restart',
                        ),
                    ])
                )
                for node in managed_nodes
            ])
        ])
        return perform(
            dispatcher,
            restart_commands
        )

    uninstalling.addCallback(restart_services)

    return uninstalling


def configure_control_node(
    cluster,
    provider,
    logging_config=None
):
    """
    Configure Flocker control service on the given node.

    :param Cluster cluster: Description of the cluster.
    :param bytes provider: provider of the nodes  - aws. rackspace or managed.
    :param dict logging_config: A Python logging configuration dictionary,
        following the structure of PEP 391.
    """
    setup_action = 'start'
    if provider == "managed":
        setup_action = 'restart'

    return run_remotely(
        username='root',
        address=cluster.control_node.address,
        commands=sequence([
            task_install_control_certificates(
                cluster.certificates.cluster.certificate,
                cluster.certificates.control.certificate,
                cluster.certificates.control.key),
            task_enable_flocker_control(cluster.control_node.distribution,
                                        setup_action),
            if_firewall_available(
                cluster.control_node.distribution,
                task_open_control_firewall(
                    cluster.control_node.distribution
                )
            ),
        ]),
    )


def configure_node(
    cluster,
    node,
    certnkey,
    dataset_backend_configuration,
    provider,
    logging_config=None
):
    """
    Configure flocker-dataset-agent and flocker-container-agent on a node,
    so that it could join an existing Flocker cluster.

    :param Cluster cluster: Description of the cluster.
    :param Node node: The node to configure.
    :param CertAndKey certnkey: The node's certificate and key.
    :param bytes provider: provider of the nodes  - aws. rackspace or managed.
    :param dict logging_config: A Python logging configuration dictionary,
        following the structure of PEP 391.
    """
    setup_action = 'start'
    if provider == "managed":
        setup_action = 'restart'

    return run_remotely(
        username='root',
        address=node.address,
        commands=sequence([
            task_install_node_certificates(
                cluster.certificates.cluster.certificate,
                certnkey.certificate,
                certnkey.key),
            task_install_api_certificates(
                cluster.certificates.user.certificate,
                cluster.certificates.user.key),
            task_enable_docker(node.distribution),
            if_firewall_available(
                node.distribution,
                open_firewall_for_docker_api(node.distribution),
            ),
            task_configure_flocker_agent(
                control_node=cluster.control_node.address,
                dataset_backend=cluster.dataset_backend,
                dataset_backend_configuration=(
                    dataset_backend_configuration
                ),
                logging_config=logging_config,
            ),
            task_enable_docker_plugin(node.distribution),
            task_enable_flocker_agent(
                distribution=node.distribution,
                action=setup_action,
            ),
        ]),
    )


def provision_as_root(node, package_source, variants=()):
    """
    Provision flocker on a node using the root user.

    :param INode node: Node to provision.
    :param PackageSource package_source: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    commands = []

    commands.append(run_remotely(
        username='root',
        address=node.address,
        commands=provision(
            package_source=package_source,
            distribution=node.distribution,
            variants=variants,
        ),
    ))

    return sequence(commands)


def provision_for_any_user(node, package_source, variants=()):
    """
    Provision flocker on a node using the default user. If the user is not
    root, then copy the authorized_users over to the root user and then
    provision as root.

    :param INode node: Node to provision.
    :param PackageSource package_source: See func:`task_install_flocker`
    :param set variants: The set of variant configurations to use when
        provisioning
    """
    username = node.get_default_username()

    if username == 'root':
        return provision_as_root(node, package_source, variants)

    commands = []

    # cloud-init may not have allowed sudo without tty yet, so try SSH key
    # installation for a few more seconds:
    start = []

    def for_thirty_seconds(*args, **kwargs):
        if not start:
            start.append(time())
        return Effect(Constant((time() - start[0]) < 30))

    commands.append(run_remotely(
        username=username,
        address=node.address,
        commands=retry(task_install_ssh_key(), for_thirty_seconds),
    ))

    commands.append(
        provision_as_root(node, package_source, variants))

    return sequence(commands)
