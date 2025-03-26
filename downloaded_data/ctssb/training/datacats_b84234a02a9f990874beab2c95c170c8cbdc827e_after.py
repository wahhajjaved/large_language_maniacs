# Copyright 2014-2015 Boxkite Inc.

# This file is part of the DataCats package and is released under
# the terms of the GNU Affero General Public License version 3.0.
# See LICENSE.txt or http://www.fsf.org/licensing/licenses/agpl-3.0.html

from __future__ import absolute_import

from os import environ, devnull
import json
import subprocess
from urlparse import urlparse
from functools import cmp_to_key
from warnings import warn

# XXX our fixes on top of fixes to work with docker-py and docker
# incompatibilities are approaching the level of superstition.
# let's hope docker calms down a bit so we can clean this out
# in the future.

from docker import Client
try:
    # Versions after 1.2.0
    from docker.constants import DEFAULT_DOCKER_API_VERSION
except ImportError:
    # Versions before 1.2.0
    from docker.client import DEFAULT_DOCKER_API_VERSION
from docker.utils import kwargs_from_env, compare_version, create_host_config
from docker.errors import APIError
from requests import ConnectionError

from datacats.error import DatacatsError

MINIMUM_API_VERSION = '1.16'


def get_api_version(*versions):
    # compare_version is backwards
    def cmp(a, b):
        return -1 * compare_version(a, b)
    return min(versions, key=cmp_to_key(cmp))

# Lazy instantiation of _docker
_docker = None

_docker_kwargs = kwargs_from_env()


def _get_docker():
    global _docker
    if not _docker:
        # First, check if boot2docker is powered on.
        try:
            # Use an absolute path to avoid any funny business
            # with the PATH.
            with open(devnull, 'w') as devnull_f:
                status = subprocess.check_output(
                    ['boot2docker', 'status'],
                    # Don't show boot2docker message
                    # to the user... it's ugly!
                    stderr=devnull_f
                    ).strip()
            if status == 'poweroff':
                raise DatacatsError('boot2docker is not powered on.'
                                    ' Please run "boot2docker up".')
        except OSError:
            # We're on Linux, or boot2docker isn't installed.
            pass
        except subprocess.CalledProcessError:
            raise DatacatsError('You have not created your boot2docker VM. '
                                'Please run "boot2docker create" to do so.')

        # Create the Docker client
        version_client = Client(version=MINIMUM_API_VERSION, **_docker_kwargs)
        try:
            api_version = version_client.version()['ApiVersion']
        except ConnectionError:
            # workaround for connection issue when old version specified
            # on some clients
            version_client = Client(**_docker_kwargs)
            api_version = version_client.version()['ApiVersion']

        version = get_api_version(DEFAULT_DOCKER_API_VERSION, api_version)
        _docker = Client(version=version, **_docker_kwargs)

    return _docker


class WebCommandError(Exception):

    def __init__(self, command, container_id, logs):
        self.command = command
        self.container_id = container_id
        self.logs = logs

    def __str__(self):
        return \
            ('\nSSH command to remote server failed\n'
             '    Command: {0}\n'
             '    Docker Error Log:\n'
             '    {1}\n').format(self.command, self.logs, self.container_id)


class PortAllocatedError(Exception):
    pass

_boot2docker = None


def is_boot2docker():
    global _boot2docker
    if _boot2docker is None:
        _boot2docker = 'Boot2Docker' in _get_docker().info()['OperatingSystem']
    return _boot2docker


def docker_host():
    url = _docker_kwargs.get('base_url')
    if not url:
        return 'localhost'
    return urlparse(url).netloc.split(':')[0]


def ro_rw_to_binds(ro, rw):
    """
    ro and rw {localdir: binddir} dicts to docker-py's
    {localdir: {'bind': binddir, 'ro': T/F}} binds dicts
    """
    out = {}
    if ro:
        for localdir, binddir in ro.iteritems():
            out[localdir] = {'bind': binddir, 'ro': True}
    if rw:
        for localdir, binddir in rw.iteritems():
            out[localdir] = {'bind': binddir, 'ro': False}
    return out


def binds_to_volumes(volumes):
    """
    Return the target 'bind' dirs of volumnes from a volumes dict
    for passing to create_container
    """
    return [v['bind'] for v in volumes.itervalues()]


def web_command(command, ro=None, rw=None, links=None,
                image='datacats/web', volumes_from=None, commit=False,
                clean_up=False, stream_output=None):
    """
    Run a single command in a web image optionally preloaded with the ckan
    source and virtual envrionment.

    :param command: command to execute
    :param ro: {localdir: binddir} dict for read-only volumes
    :param rw: {localdir: binddir} dict for read-write volumes
    :param links: links passed to start
    :param image: docker image name to use
    :param volumes_from:
    :param commit: True to create a new image based on result
    :param clean_up: True to remove container even on error
    :param stream_output: file to write stderr+stdout from command

    :returns: image id if commit=True
    """
    binds = ro_rw_to_binds(ro, rw)
    c = _get_docker().create_container(
        image=image,
        command=command,
        volumes=binds_to_volumes(binds),
        detach=False,
        host_config=create_host_config(binds=binds))
    _get_docker().start(
        container=c['Id'],
        links=links,
        binds=binds,
        volumes_from=volumes_from)
    if stream_output:
        for output in _get_docker().attach(
                c['Id'], stdout=True, stderr=True, stream=True):
            stream_output.write(output)
    if _get_docker().wait(c['Id']):
        # Before the (potential) cleanup, grab the logs!
        logs = _get_docker().logs(c['Id'])

        if clean_up:
            remove_container(c['Id'])
        raise WebCommandError(command, c['Id'][:12], logs)
    if commit:
        rval = _get_docker().commit(c['Id'])
    if not remove_container(c['Id']):
        # circle ci doesn't let us remove containers, quiet the warnings
        if not environ.get('CIRCLECI', False):
            warn('failed to remove container: {0}'.format(c['Id']))
    if commit:
        return rval['Id']


def run_container(name, image, command=None, environment=None,
                  ro=None, rw=None, links=None, detach=True, volumes_from=None,
                  port_bindings=None):
    """
    Wrapper for docker create_container, start calls

    :returns: container info dict or None if container couldn't be created

    Raises PortAllocatedError if container couldn't start on the
    requested port.
    """
    binds = ro_rw_to_binds(ro, rw)
    c = _get_docker().create_container(
        name=name,
        image=image,
        command=command,
        environment=environment,
        volumes=binds_to_volumes(binds),
        detach=detach,
        stdin_open=False,
        tty=False,
        ports=list(port_bindings) if port_bindings else None,
        host_config=create_host_config(binds=binds))
    try:
        _get_docker().start(
            container=c['Id'],
            links=links,
            binds=binds,
            volumes_from=volumes_from,
            port_bindings=port_bindings)
    except APIError as e:
        if 'address already in use' in e.explanation:
            try:
                _get_docker().remove_container(name, force=True)
            except APIError:
                pass
            raise PortAllocatedError()
        raise
    return c


def image_exists(name):
    """
    Queries Docker about if a particular image has been downloaded.

    :param name: The name of the image to check for.
    """
    # This returns a list of container dicts matching (exactly)
    # the name `name`.
    return bool(_get_docker().images(name=name))



def remove_container(name, force=False):
    """
    Wrapper for docker remove_container

    :returns: True if container was found and removed
    """

    try:
        if not force:
            _get_docker().stop(name)
    except APIError as e:
        pass
    try:
        _get_docker().remove_container(name, force=True)
        return True
    except APIError as e:
        return False


def inspect_container(name):
    """
    Wrapper for docker inspect_container

    :returns: container info dict or None if not found
    """
    try:
        return _get_docker().inspect_container(name)
    except APIError as e:
        return None


def container_logs(name, tail, follow, timestamps):
    """
    Wrapper for docker logs, attach commands.
    """
    if follow:
        return _get_docker().attach(
            name,
            stdout=True,
            stderr=True,
            stream=True
            )

    return _docker.logs(
        name,
        stdout=True,
        stderr=True,
        tail=tail,
        timestamps=timestamps,
    )


def pull_stream(image):
    """
    Return generator of pull status objects
    """
    return (json.loads(s) for s in _get_docker().pull(image, stream=True))


def data_only_container(name, volumes):
    """
    create "data-only container" if it doesn't already exist.

    We'd like to avoid these, but postgres + boot2docker make
    it difficult, see issue #5
    """
    info = inspect_container(name)
    if info:
        return
    c = _get_docker().create_container(
        name=name,
        image='datacats/postgres',  # any image will do
        command='true',
        volumes=volumes,
        detach=True)
    return c


def remove_image(image, force=False, noprune=False):
    _get_docker().remove_image(image, force=force, noprune=noprune)
