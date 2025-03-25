# Authors:
#   Petr Viktorin <pviktori@redhat.com>
#
# Copyright (C) 2011  Red Hat
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

"""Pytest plugin for IPA Integration tests"""

import os
import tempfile
import shutil

import pytest
from pytest_multihost import make_multihost_fixture

from ipapython import ipautil
from ipapython.ipa_log_manager import log_mgr
from ipatests.test_integration import tasks
from ipatests.test_integration.config import Config
from ipatests.test_integration.env_config import get_global_config


log = log_mgr.get_logger(__name__)


def pytest_addoption(parser):
    group = parser.getgroup("IPA integration tests")

    group.addoption(
        '--logfile-dir', dest="logfile_dir", default=None,
        help="Directory to store integration test logs in.")


def collect_test_logs(node, logs_dict, test_config):
    """Collect logs from a test

    Calls collect_logs

    :param node: The pytest collection node (request.node)
    :param logs_dict: Mapping of host to list of log filnames to collect
    :param test_config: Pytest configuration
    """
    collect_logs(
        name=node.nodeid.replace('/', '-').replace('::', '-'),
        logs_dict=logs_dict,
        logfile_dir=test_config.getoption('logfile_dir'),
        beakerlib_plugin=test_config.pluginmanager.getplugin('BeakerLibPlugin'),
    )


def collect_logs(name, logs_dict, logfile_dir=None, beakerlib_plugin=None):
    """Collect logs from remote hosts

    Calls collect_logs

    :param name: Name under which logs arecollected, e.g. name of the test
    :param logs_dict: Mapping of host to list of log filnames to collect
    :param logfile_dir: Directory to log to
    :param beakerlib_plugin:
        BeakerLibProcess or BeakerLibPlugin used to collect tests for BeakerLib

    If neither logfile_dir nor beakerlib_plugin is given, no tests are
    collected.
    """
    if logs_dict and (logfile_dir or beakerlib_plugin):

        if logfile_dir:
            remove_dir = False
        else:
            logfile_dir = tempfile.mkdtemp()
            remove_dir = True

        topdirname = os.path.join(logfile_dir, name)

        for host, logs in logs_dict.items():
            log.info('Collecting logs from: %s', host.hostname)

            # Tar up the logs on the remote server
            cmd = host.run_command(['tar', 'cJv'] + logs, log_stdout=False,
                                   raiseonerr=False)
            if cmd.returncode:
                log.warn('Could not collect all requested logs')

            # Unpack on the local side
            dirname = os.path.join(topdirname, host.hostname)
            try:
                os.makedirs(dirname)
            except OSError:
                pass
            tarname = os.path.join(dirname, 'logs.tar.xz')
            with open(tarname, 'w') as f:
                f.write(cmd.stdout_text)
            ipautil.run(['tar', 'xJvf', 'logs.tar.xz'], cwd=dirname,
                        raiseonerr=False)
            os.unlink(tarname)

        if beakerlib_plugin:
            # Use BeakerLib's rlFileSubmit on the indifidual files
            # The resulting submitted filename will be
            # $HOSTNAME-$FILENAME (with '/' replaced by '-')
            beakerlib_plugin.run_beakerlib_command(['pushd', topdirname])
            try:
                for dirpath, dirnames, filenames in os.walk(topdirname):
                    for filename in filenames:
                        fullname = os.path.relpath(
                            os.path.join(dirpath, filename), topdirname)
                        log.debug('Submitting file: %s', fullname)
                        beakerlib_plugin.run_beakerlib_command(
                            ['rlFileSubmit', fullname])
            finally:
                beakerlib_plugin.run_beakerlib_command(['popd'])

        if remove_dir:
            if beakerlib_plugin:
                # The BeakerLib process runs asynchronously, let it clean up
                # after it's done with the directory
                beakerlib_plugin.run_beakerlib_command(
                    ['rm', '-rvf', topdirname])
            else:
                shutil.rmtree(topdirname)

        logs_dict.clear()


@pytest.fixture(scope='class')
def class_integration_logs():
    """Internal fixture providing class-level logs_dict"""
    return {}


@pytest.yield_fixture
def integration_logs(class_integration_logs, request):
    """Provides access to test integration logs, and collects after each test
    """
    yield class_integration_logs
    collect_test_logs(request.node, class_integration_logs, request.config)


@pytest.yield_fixture(scope='class')
def mh(request, class_integration_logs):
    """IPA's multihost fixture object
    """
    cls = request.cls

    domain_description = {
        'type': 'IPA',
        'hosts': {
            'master': 1,
            'replica': cls.num_replicas,
            'client': cls.num_replicas,
        },
    }
    domain_description['hosts'].update(
        {role: 1 for role in cls.required_extra_roles})

    domain_descriptions = [domain_description]
    for i in range(cls.num_ad_domains):
        domain_descriptions.append({
            'type': 'AD',
            'hosts': {'ad': 1, 'ad_subdomain': 1},
        })

    mh = make_multihost_fixture(
        request,
        domain_descriptions,
        config_class=Config,
        _config=get_global_config(),
    )
    config = mh.config
    mh.domain = mh.config.domains[0]
    [mh.master] = mh.domain.hosts_by_role('master')
    mh.replicas = mh.domain.hosts_by_role('replica')
    mh.clients = mh.domain.hosts_by_role('client')

    cls.logs_to_collect = class_integration_logs

    def collect_log(host, filename):
        log.info('Adding %s:%s to list of logs to collect' %
                 (host.external_hostname, filename))
        class_integration_logs.setdefault(host, []).append(filename)

    print config
    for host in config.get_all_hosts():
        host.add_log_collector(collect_log)
        cls.log.info('Preparing host %s', host.hostname)
        tasks.prepare_host(host)

    setup_class(cls, config)
    mh._pytestmh_request.addfinalizer(lambda: teardown_class(cls))

    yield mh.install()

    for host in cls.get_all_hosts():
        host.remove_log_collector(collect_log)

    collect_test_logs(request.node, class_integration_logs, request.config)


def setup_class(cls, config):
    """Add convenience addributes to the test class

    This is deprecated in favor of the mh fixture.
    To be removed when no more tests using this.
    """
    cls.domain = config.domains[0]
    cls.master = cls.domain.master
    cls.replicas = cls.domain.replicas
    cls.clients = cls.domain.clients
    cls.ad_domains = config.ad_domains


def teardown_class(cls):
    """Add convenience addributes to the test class

    This is deprecated in favor of the mh fixture.
    To be removed when no more tests using this.
    """
    del cls.master
    del cls.replicas
    del cls.clients
    del cls.ad_domains
    del cls.domain
