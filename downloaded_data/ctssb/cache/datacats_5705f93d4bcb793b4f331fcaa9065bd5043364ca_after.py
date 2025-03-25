# Copyright 2014-2015 Boxkite Inc.

# This file is part of the DataCats package and is released under
# the terms of the GNU Affero General Public License version 3.0.
# See LICENSE.txt or http://www.fsf.org/licensing/licenses/agpl-3.0.html

from os.path import abspath, split as path_split, expanduser, isdir, exists, join
from os import makedirs, getcwd, remove, environ, listdir
import sys
import subprocess
import shutil
import json
import time
from sha import sha
from struct import unpack
from ConfigParser import (SafeConfigParser, Error as ConfigParserError,
    NoOptionError, NoSectionError)

from datacats.validate import valid_name
from datacats.docker import (web_command, run_container, remove_container,
    inspect_container, is_boot2docker, data_only_container, docker_host,
    PortAllocatedError, container_logs, remove_image, WebCommandError)
from datacats.template import ckan_extension_template
from datacats.scripts import (WEB, SHELL, PASTER, PASTER_CD, PURGE,
    RUN_AS_USER, INSTALL_REQS, CLEAN_VIRTUALENV, INSTALL_PACKAGE)
from datacats.network import wait_for_service_available, ServiceTimeout
from datacats.migrate import needs_format_conversion, convert_environment
from datacats.password import generate_password

WEB_START_TIMEOUT_SECONDS = 30
DB_INIT_RETRY_SECONDS = 30
DB_INIT_RETRY_DELAY = 2
DOCKER_EXE = 'docker'


class DatacatsError(Exception):
    def __init__(self, message, format_args=()):
        self.message = message
        self.format_args = format_args
        super(DatacatsError, self).__init__(message, format_args)

    def __str__(self):
        return self.message.format(*self.format_args)


class Environment(object):
    """
    DataCats environment settings object

    Create with Environment.new(path) or Environment.load(path)
    """
    def __init__(self, name, target, datadir, child_name, ckan_version=None, port=None,
                deploy_target=None, site_url=None, always_prod=False,
                extension_dir='ckan'):
        self.name = name
        self.target = target
        self.datadir = datadir
        self.extension_dir = extension_dir
        self.ckan_version = ckan_version
        # This is the child that all commands will operate on.
        self.child_name = child_name
        self.childdir = join(datadir, 'children', child_name)
        self.port = int(port if port else self._choose_port())
        self.deploy_target = deploy_target
        self.site_url = site_url
        self.always_prod = always_prod
        self.children = None

    def _load_children(self):
        """
        Gets the names of all of the children from the datadir and stores them
        in self.children. Also returns this list.
        """
        if not self.children:
            # get a list of all of the subdirectories. We'll call this the list
            # of children.
            try:
                self.children = listdir(join(self.datadir, 'children'))
            except OSError:
                self.children = []

        return self.children

    def save_child(self):
        """
        Save environment settings in the directory that need to be saved
        even when creating only a new child env.
        """
        cp = SafeConfigParser()

        cp.read([self.target + '/.datacats-environment'])

        self._load_children()

        self.children.append(self.child_name)

        section_name = 'child_' + self.child_name

        cp.add_section(section_name)
        cp.set(section_name, 'port', str(self.port))

        if self.site_url:
            cp.set(section_name, 'site_url', self.site_url)

        with open(self.target + '/.datacats-environment', 'w') as config:
            cp.write(config)

        # save passwords to datadir
        cp = SafeConfigParser()

        cp.add_section('passwords')
        for n in sorted(self.passwords):
            cp.set('passwords', n.lower(), self.passwords[n])

        # Write to the childdir so we maintain separate passwords.
        with open(self.childdir + '/passwords.ini', 'w') as config:
            cp.write(config)

    def save(self):
        """
        Save environment settings into environment directory
        """
        cp = SafeConfigParser()

        cp.add_section('datacats')
        cp.set('datacats', 'name', self.name)
        cp.set('datacats', 'ckan_version', self.ckan_version)

        if self.deploy_target:
            cp.add_section('deploy')
            cp.set('deploy', 'target', self.deploy_target)

        if self.always_prod:
            cp.set('datacats', 'always_prod', 'true')

        with open(self.target + '/.datacats-environment', 'w') as config:
            cp.write(config)


        self._update_saved_project_dir()

    def _update_saved_project_dir(self):
        """
        Store the last place we've seen this environment so the user
        can specify an environment by name
        """
        with open(self.datadir + '/project-dir', 'w') as pdir:
            pdir.write(self.target)

    @classmethod
    def new(cls, path, ckan_version, child_name, port=None):
        """
        Return a Environment object with settings for a new project.
        No directories or containers are created by this call.

        :params path: location for new project directory, may be relative
        :params ckan_version: release of CKAN to install
        :params child_name: The name of the child environment to install database and solr eventually.
        :params port: preferred port for local instance

        Raises DatcatsError if directories or project with same
        name already exits.
        """
        workdir, name = path_split(abspath(expanduser(path)))

        if not valid_name(name):
            raise DatacatsError('Please choose an environment name starting'
                ' with a letter and including only lowercase letters'
                ' and digits')
        if not isdir(workdir):
            raise DatacatsError('Parent directory for environment'
                ' does not exist')

        datadir = expanduser('~/.datacats/' + name)
        childdir = join(datadir, child_name)
        # We track through the datadir to the target if we are just making a
        # child
        if isdir(datadir):
            with open(join(datadir, 'project-dir')) as pd:
                target = pd.read()
        else:
            target = workdir + '/' + name

        if isdir(childdir):
            raise DatacatsError('Child environment data directory {0} already exists',
                (childdir,))
        # This is the case where the data dir has been removed,
        if isdir(target) and not isdir(datadir):
            raise DatacatsError('Environment directory exists, but data directory does not.\n'
                                'If you simply want to recreate the data directory, run "datacats init"'
                                ' in the environment directory.')

        environment = cls(name, target, datadir, child_name, ckan_version, port)
        environment._generate_passwords()
        return environment

    @classmethod
    def load(cls, environment_name=None, child_name='primary', data_only=False):
        """
        Return an Environment object based on an existing project.

        :param environment_name: exising environment name, path or None to
            look in current or parent directories for project
        :param data_only: set to True to only load from data dir, not
            the project dir; Used for purging environment data.

        Raises DatacatsError if environment can't be found or if there is an
        error parsing the environment information.
        """
        if environment_name is None:
            environment_name = '.'

        extension_dir = 'ckan'
        if valid_name(environment_name) and isdir(
                expanduser('~/.datacats/' + environment_name)):
            used_path = False
            datadir = expanduser('~/.datacats/' + environment_name)
            with open(datadir + '/project-dir') as pd:
                wd = pd.read()
            if not data_only and not exists(wd + '/.datacats-environment'):
                raise DatacatsError(
                    'Environment data found but environment directory is'
                    ' missing. Try again from the new environment directory'
                    ' location or remove the environment data with'
                    ' "datacats purge"')
        else:
            used_path = True
            wd = abspath(environment_name)
            if not isdir(wd):
                raise DatacatsError('No environment found with that name')

            first_wd = wd
            oldwd = None
            while not exists(wd + '/.datacats-environment'):
                oldwd = wd
                wd, ignore = path_split(wd)
                if wd == oldwd:
                    raise DatacatsError(
                        'Environment not found in {0} or above', first_wd)

            if oldwd:
                ignore, extension_dir = path_split(oldwd)

        if data_only and not used_path:
            return cls(environment_name, None, datadir, child_name)


        cp = SafeConfigParser()
        try:
            cp.read([wd + '/.datacats-environment'])
        except ConfigParserError:
            raise DatacatsError('Error reading environment information')

        child_section = 'child_' + child_name
        name = cp.get('datacats', 'name')
        datadir = expanduser('~/.datacats/' + name)
        # Kinda a hack... we read the config and if datadir is being upgraded,
        # load it again.
        if needs_format_conversion(datadir):
            convert_environment(datadir)
            cp = SafeConfigParser()
            try:
                cp.read([wd + '/.datacats-environment'])
            except ConfigParserError:
                raise DatacatsError('Something went wrong with the upgrade! '
                                    'There is a backup of the old files in ' +
                                    datadir + '.bak')

        ckan_version = cp.get('datacats', 'ckan_version')
        try:
            port = cp.getint(child_section, 'port')
        except (NoOptionError, NoSectionError):
            port = None
        try:
            site_url = cp.get(child_section, 'site_url')
        except (NoOptionError, NoSectionError):
            site_url = None
        try:
            always_prod = cp.getboolean('datacats', 'always_prod')
        except NoOptionError:
            always_prod = False
        try:
            deploy_target = cp.get('deploy', 'target', None)
        except NoSectionError:
            deploy_target = None

        passwords = {}
        try:
            # backwards compatibility  FIXME: remove this
            pw_options = cp.options('passwords')
        except NoSectionError:
            cp = SafeConfigParser()
            cp.read(join(datadir, child_name) + '/passwords.ini')
            try:
                pw_options = cp.options('passwords')
            except NoSectionError:
                pw_options = []

        for n in pw_options:
            passwords[n.upper()] = cp.get('passwords', n)

        environment = cls(name, wd, datadir, child_name, ckan_version, port, deploy_target,
        site_url=site_url, always_prod=always_prod, extension_dir=extension_dir)
        if passwords:
            environment.passwords = passwords
        else:
            environment._generate_passwords()

        if not used_path:
            environment._update_saved_project_dir()

        environment._load_children()

        return environment

    def data_exists(self):
        """
        Return True if the datadir for this environment exists
        """
        return isdir(self.datadir)

    def require_valid_child(self):
        if self.child_name not in self.children:
            raise DatacatsError('Invalid child name: {}. Valid names are: {}'
                                .format(self.child_name,
                                        ', '.join(self.children)))

    def data_complete(self):
        """
        Return True if all the expected datadir files are present
        """
        if (not isdir(self.childdir + '/files')
                or not isdir(self.childdir + '/run')
                or not isdir(self.childdir + '/search')):
            return False
        if is_boot2docker():
            return True
        return (
            isdir(self.datadir + '/venv') and
            isdir(self.childdir + '/data'))

    def require_data(self):
        """
        raise a DatacatsError if the datadir is missing or damaged
        """
        if not self.data_exists():
            raise DatacatsError('Environment datadir missing. '
                'Try "datacats init".')
        if not self.data_complete():
            raise DatacatsError('Environment datadir damaged. '
                'Try "datacats purge" followed by "datacats init".')

    def create_directories(self, create_project_dir=True):
        """
        Call once for new projects to create the initial project directories.
        """
        # It's possible that the datadir already exists (we're making a secondary child)
        if not isdir(self.datadir):
            makedirs(self.datadir, mode=0o700)
        # This should take care if the 'child' subdir if needed
        makedirs(self.childdir, mode=0o700)

        # venv isn't child-specific, the rest are.
        makedirs(self.childdir + '/search')
        if not is_boot2docker():
            makedirs(self.datadir + '/venv')
            makedirs(self.childdir + '/data')
        makedirs(self.childdir + '/files')
        makedirs(self.childdir + '/run')

        if create_project_dir:
            makedirs(self.target)

    def create_bash_profile(self):
        """
        Create a default .bash_profile for the shell user that
        activates the ckan virtualenv
        """
        with open(self.target + '/.bash_profile', 'w') as prof:
            prof.write('source /usr/lib/ckan/bin/activate\n')

    def _preload_image(self):
        """
        Return the preloaded ckan src and venv image name
        """
        # FIXME: when we support more than one preload image
        # get the preload name from self.ckan_version
        return 'datacats/web:preload-2.3'

    def create_virtualenv(self):
        """
        Populate venv directory from preloaded image
        """
        if is_boot2docker():
            data_only_container('datacats_venv_' + self.name,
                ['/usr/lib/ckan'])
            img_id = web_command(
                '/bin/mv /usr/lib/ckan/ /usr/lib/ckan_original',
                image=self._preload_image(),
                commit=True,
                )
            web_command(
                command='/bin/cp -a /usr/lib/ckan_original/. /usr/lib/ckan/.',
                volumes_from='datacats_venv_' + self.name,
                image=img_id,
                )
            remove_image(img_id)
        else:
            web_command(
                command='/bin/cp -a /usr/lib/ckan/. /usr/lib/ckan_target/.',
                rw={self.datadir + '/venv': '/usr/lib/ckan_target'},
                image=self._preload_image())

    def clean_virtualenv(self):
        """
        Empty our virtualenv so that new (or older) dependencies may be
        installed
        """
        self.user_run_script(
            script=CLEAN_VIRTUALENV,
            args=[],
            rw_venv=True,
            )

    def create_source(self):
        """
        Populate ckan directory from preloaded image and copy
        who.ini and schema.xml info conf directory
        """
        web_command(
            command='/bin/cp -a /project/ckan /project_target/ckan',
            rw={self.target: '/project_target'},
            image=self._preload_image())
        shutil.copy(
            self.target + '/ckan/ckan/config/who.ini',
            self.target)
        shutil.copy(
            self.target + '/ckan/ckan/config/solr/schema.xml',
            self.target)

    def start_postgres_and_solr(self):
        """
        run the DB and search containers
        """
        # complicated because postgres needs hard links to
        # work on its data volume. see issue #5
        if is_boot2docker():
            data_only_container('datacats_pgdata_' + self.name + '_' + self.child_name,
                ['/var/lib/postgresql/data'])
            rw = {}
            volumes_from = 'datacats_pgdata_' + self.name + '_' + self.child_name
        else:
            rw = {self.childdir + '/postgres': '/var/lib/postgresql/data'}
            volumes_from = None

        running = self.containers_running()

        if 'postgres' not in running or 'solr' not in running:
            # users are created when data dir is blank so we must pass
            # all the user passwords as environment vars
            self.stop_postgres_and_solr()
            run_container(
                name='datacats_postgres_' + self.name + '_' + self.child_name,
                image='datacats/postgres',
                environment=self.passwords,
                rw=rw,
                volumes_from=volumes_from)
            run_container(
                name='datacats_solr_' + self.name + '_' + self.child_name,
                image='datacats/solr',
                rw={self.childdir + '/solr': '/var/lib/solr'},
                ro={self.target + '/schema.xml': '/etc/solr/conf/schema.xml'})

    def stop_postgres_and_solr(self):
        """
        stop and remove postgres and solr containers
        """
        remove_container('datacats_postgres_' + self.name + '_' + self.child_name)
        remove_container('datacats_solr_' + self.name + '_' + self.child_name)

    def fix_storage_permissions(self):
        """
        Set the owner of all apache storage files to www-data container user
        """
        web_command(
            command='/bin/chown -R www-data: /var/www/storage',
            rw={self.childdir + '/files': '/var/www/storage'})

    def create_ckan_ini(self):
        """
        Use make-config to generate an initial development.ini file
        """
        self.run_command(
            command='/usr/lib/ckan/bin/paster make-config'
                ' ckan /project/development.ini',
            rw_project=True,
            )

    def update_ckan_ini(self, skin=True):
        """
        Use config-tool to update development.ini with our environment settings

        :param skin: use environment template skin plugin True/False
        """
        command = [
            '/usr/lib/ckan/bin/paster', '--plugin=ckan', 'config-tool',
            '/project/development.ini', '-e',
            'sqlalchemy.url = postgresql://<hidden>',
            'ckan.datastore.read_url = postgresql://<hidden>',
            'ckan.datastore.write_url = postgresql://<hidden>',
            'solr_url = http://solr:8080/solr',
            'ckan.storage_path = /var/www/storage',
            'ckan.plugins = datastore resource_proxy text_view '
            + 'recline_grid_view recline_graph_view'
            + (' {0}_theme'.format(self.name) if skin else ''),
            'ckan.site_title = ' + self.name,
            'ckan.site_logo =',
            'ckan.auth.create_user_via_web = false',
            ]
        self.run_command(command=command, rw_project=True)

    def create_install_template_skin(self):
        """
        Create an example ckan extension for this environment and install it
        """
        ckan_extension_template(self.name, self.target)
        self.install_package_develop('ckanext-' + self.name + 'theme')


    def fix_project_permissions(self):
        """
        Reset owner of project files to the host user so they can edit,
        move and delete them freely.
        """
        self.run_command(
            command='/bin/chown -R --reference=/project'
                ' /usr/lib/ckan /project',
            rw_venv=True,
            rw_project=True,
            )

    def ckan_db_init(self, retry_seconds=DB_INIT_RETRY_SECONDS):
        """
        Run db init to create all ckan tables

        :param retry_seconds: how long to retry waiting for db to start
        """
        started = time.time()
        while True:
            try:
                self.run_command(
                    '/usr/lib/ckan/bin/paster --plugin=ckan db init '
                    '-c /project/development.ini',
                    db_links=True,
                    clean_up=True,
                    )
                return
            except WebCommandError:
                if started + retry_seconds > time.time():
                    raise
            time.sleep(DB_INIT_RETRY_DELAY)

    def _generate_passwords(self):
        """
        Generate new DB passwords and store them in self.passwords
        """
        self.passwords = {
            'POSTGRES_PASSWORD': generate_password(),
            'CKAN_PASSWORD': generate_password(),
            'DATASTORE_RO_PASSWORD': generate_password(),
            'DATASTORE_RW_PASSWORD': generate_password(),
            'BEAKER_SESSION_SECRET': generate_password(),
            }

    def start_web(self, production=False):
        """
        Start the apache server or paster serve

        :param production: True for apache, False for paster serve + debug on
        """
        port = self.port
        command = None

        production = production or self.always_prod
        if not production:
            command = ['/scripts/web.sh']

        # XXX nasty hack, remove this once we have a lessc command
        # for users (not just for building our preload image)
        if not production:
            css = self.target + '/ckan/ckan/public/base/css'
            if not exists(css + '/main.debug.css'):
                from shutil import copyfile
                copyfile(css + '/main.css', css + '/main.debug.css')

        while True:
            self._create_run_ini(port, production)
            try:
                self._run_web_container(port, command)
            except PortAllocatedError:
                port = self._next_port(port)
                continue
            break

    def _create_run_ini(self, port, production, output='development.ini',
            source='development.ini', override_site_url=True):
        """
        Create run/development.ini in datadir with debug and site_url overridden
        and with correct db passwords inserted
        """
        cp = SafeConfigParser()
        try:
            cp.read([self.target + '/' + source])
        except ConfigParserError:
            raise DatacatsError('Error reading development.ini')

        cp.set('DEFAULT', 'debug', 'false' if production else 'true')

        if self.site_url:
            site_url = self.site_url
        else:
            site_url = 'http://{0}:{1}/'.format(docker_host(), port)

        if override_site_url:
            cp.set('app:main', 'ckan.site_url', site_url)

        cp.set('app:main', 'sqlalchemy.url',
            'postgresql://ckan:{0}@db:5432/ckan'
                .format(self.passwords['CKAN_PASSWORD']))
        cp.set('app:main', 'ckan.datastore.read_url',
            'postgresql://ckan_datastore_readonly:{0}@db:5432/ckan_datastore'
                .format(self.passwords['DATASTORE_RO_PASSWORD']))
        cp.set('app:main', 'ckan.datastore.write_url',
            'postgresql://ckan_datastore_readwrite:{0}@db:5432/ckan_datastore'
                .format(self.passwords['DATASTORE_RW_PASSWORD']))
        cp.set('app:main', 'solr_url', 'http://solr:8080/solr')
        cp.set('app:main', 'beaker.session.secret', self.passwords['BEAKER_SESSION_SECRET'])

        if not isdir(self.childdir + '/run'):
            makedirs(self.childdir + '/run')  # upgrade old datadir
        with open(self.childdir + '/run/' + output, 'w') as runini:
            cp.write(runini)

    def _run_web_container(self, port, command):
        """
        Start web comtainer on port with command
        """
        if is_boot2docker():
            ro = {}
            volumes_from = 'datacats_venv_' + self.name
        else:
            ro = {self.datadir + '/venv': '/usr/lib/ckan'}
            volumes_from = None

        run_container(
            name='datacats_web_' + self.name + '_' + self.child_name,
            image='datacats/web',
            rw={self.childdir + '/files': '/var/www/storage'},
            ro=dict({
                self.target: '/project/',
                self.childdir + '/run/development.ini':
                    '/project/development.ini',
                WEB: '/scripts/web.sh'}, **ro),
            links={'datacats_solr_' + self.name + '_' + self.child_name: 'solr',
                'datacats_postgres_' + self.name + '_' + self.child_name: 'db'},
            volumes_from=volumes_from,
            command=command,
            port_bindings={
                5000: port if is_boot2docker() else ('127.0.0.1', port)},
            )

    def wait_for_web_available(self):
        """
        Wait for the web server to become available or raise DatacatsError
        if it fails to start.
        """
        try:
            if not wait_for_service_available(
                    'datacats_web_' + self.name + '_' + self.child_name,
                    self.web_address(),
                    WEB_START_TIMEOUT_SECONDS):
                raise DatacatsError('Failed to start web container.'
                    ' Run "datacats logs" to check the output.')
        except ServiceTimeout:
            raise DatacatsError('Timeout waiting for web container to start.'
                ' Run "datacats logs" to check the output.')

    def _choose_port(self):
        """
        Return a port number from 5000-5999 based on the environment name
        to be used as a default when the user hasn't selected one.
        """
        # instead of random let's base it on the name chosen (and the childname)
        return 5000 + unpack('Q',
            sha((self.name + self.child_name).decode('ascii')).digest()[:8])[0] % 1000

    def _next_port(self, port):
        """
        Return another port from the 5000-5999 range
        """
        port = 5000 + (port + 1) % 1000
        if port == self.port:
            raise DatacatsError('Too many instances running')
        return port

    def stop_web(self):
        """
        Stop and remove the web container
        """
        remove_container('datacats_web_' + self.name + '_' + self.child_name, force=True)

    def _current_web_port(self):
        """
        return just the port number for the web container, or None if
        not running
        """
        info = inspect_container('datacats_web_' + self.name + '_' + self.child_name)
        if info is None:
            return None
        try:
            if not info['State']['Running']:
                return None
            return info['NetworkSettings']['Ports']['5000/tcp'][0]['HostPort']
        except TypeError:
            return None

    def containers_running(self):
        """
        Return a list including 0 or more of ['web', 'postgres', 'solr']
        for containers tracked by this project that are running
        """
        running = []
        for n in ['web', 'postgres', 'solr']:
            info = inspect_container('datacats_' + n + '_' + self.name + '_' + self.child_name)
            if info and not info['State']['Running']:
                running.append(n + '(halted)')
            elif info:
                running.append(n)
        return running

    def web_address(self):
        """
        Return the url of the web server or None if not running
        """
        port = self._current_web_port()
        if port is None:
            return None
        return 'http://{0}:{1}/'.format(docker_host(), port)

    def create_admin_set_password(self, password):
        """
        create 'admin' account with given password
        """
        with open(self.childdir + '/run/admin.json', 'w') as out:
            json.dump({
                'name': 'admin',
                'email': 'none',
                'password': password,
                'sysadmin': True},
                out)
        self.run_command(
            command=['/bin/bash', '-c', '/usr/lib/ckan/bin/ckanapi '
                'action user_create -i -c /project/development.ini '
                '< /input/admin.json'],
            db_links=True,
            ro={self.childdir + '/run/admin.json': '/input/admin.json'},
            )
        remove(self.childdir + '/run/admin.json')

    def interactive_shell(self, command=None, paster=False, detach=False):
        """
        launch interactive shell session with all writable volumes

        :param: list of strings to execute instead of bash
        """
        if not exists(self.target + '/.bash_profile'):
            # this file is required for activating the virtualenv
            self.create_bash_profile()

        if not command:
            command = []
        use_tty = sys.stdin.isatty() and sys.stdout.isatty()

        background = environ.get('CIRCLECI', False) or detach

        if is_boot2docker():
            venv_volumes = ['--volumes-from', 'datacats_venv_' + self.name]
        else:
            venv_volumes = ['-v', self.datadir + '/venv:/usr/lib/ckan:rw']

        self._create_run_ini(self.port, production=False, output='run.ini')
        self._create_run_ini(self.port, production=True, output='test.ini',
            source='ckan/test-core.ini', override_site_url=False)

        script = SHELL
        if paster:
            script = PASTER
            if command and command != ['help'] and command != ['--help']:
                command += ['--config=/project/development.ini']
            command = [self.extension_dir] + command

        proxy_settings = self._proxy_settings()
        if proxy_settings:
            venv_volumes += ['-v',
                self.childdir + '/run/proxy-environment:/etc/environment:ro']

        # FIXME: consider switching this to dockerpty
        # using subprocess for docker client's interactive session
        return subprocess.call([
            DOCKER_EXE, 'run',
            ] + (['--rm'] if not background else []) + [
            '-t' if use_tty else '',
            '-d' if detach else '-i',
            ] + venv_volumes + [
            '-v', self.target + ':/project:rw',
            '-v', self.childdir + '/files:/var/www/storage:rw',
            '-v', script + ':/scripts/shell.sh:ro',
            '-v', PASTER_CD + ':/scripts/paster_cd.sh:ro',
            '-v', self.childdir + '/run/run.ini:/project/development.ini:ro',
            '-v', self.childdir + '/run/test.ini:/project/ckan/test-core.ini:ro',
            '--link', 'datacats_solr_' + self.name + '_' + self.child_name  + ':solr',
            '--link', 'datacats_postgres_' + self.name + '_' + self.child_name + ':db',
            '--hostname', self.name,
            'datacats/web', '/scripts/shell.sh'] + command)

    def install_package_requirements(self, psrc):
        """
        Install from requirements.txt file found in psrc

        :param psrc: name of directory in environment directory
        """
        package = self.target + '/' + psrc
        assert isdir(package), package
        reqname = '/requirements.txt'
        if not exists(package + reqname):
            reqname = '/pip-requirements.txt'
            if not exists(package + reqname):
                return
        self.user_run_script(
            script=INSTALL_REQS,
            args=['/project/' + psrc + reqname],
            rw_venv=True,
            rw_project=True,
            )

    def install_package_develop(self, psrc):
        """
        Install a src package in place (setup.py develop)

        :param psrc: name of directory under project directory
        """
        package = self.target + '/' + psrc
        assert isdir(package), package
        if not exists(package + '/setup.py'):
            return
        self.user_run_script(
            script=INSTALL_PACKAGE,
            args=['/project/' + psrc],
            rw_venv=True,
            rw_project=True,
            )

    def user_run_script(self, script, args, db_links=False, rw_venv=False,
            rw_project=False, rw=None, ro=None):
        return self.run_command(
            command=['/scripts/run_as_user.sh', '/scripts/run.sh'] + args,
            db_links=db_links,
            rw_venv=rw_venv,
            rw_project=rw_project,
            rw=rw,
            ro=dict(ro or {}, **{
                RUN_AS_USER: '/scripts/run_as_user.sh',
                script: '/scripts/run.sh',
                }),
            )

    def run_command(self, command, db_links=False, rw_venv=False,
            rw_project=False, rw=None, ro=None, clean_up=False):

        rw = {} if rw is None else dict(rw)
        ro = {} if ro is None else dict(ro)

	ro.update(self._proxy_settings())

        if is_boot2docker():
            volumes_from = 'datacats_venv_' + self.name
        else:
            volumes_from = None
            venvmount = rw if rw_venv else ro
            venvmount[self.datadir + '/venv'] = '/usr/lib/ckan'
        projectmount = rw if rw_project else ro
        projectmount[self.target] = '/project'

        if db_links:
            self._create_run_ini(self.port, production=False, output='run.ini')
            links = {
                'datacats_solr_' + self.name + '_' + self.child_name: 'solr',
                'datacats_postgres_' + self.name + '_' + self.child_name: 'db',
                }
            ro[self.childdir + '/run/run.ini'] = '/project/development.ini'
        else:
            links = None

        try:
            return web_command(command=command, ro=ro, rw=rw, links=links,
                    volumes_from=volumes_from, clean_up=clean_up)
        except WebCommandError as e:
            print 'Failed to run command %s. Logs are as follows:\n%s' % (e.command, e.logs)
            raise


    def purge_data(self, which_children=None):
        """
        Remove uploaded files, postgres db, solr index, venv
        """
        # Default to the set of all children
        if not which_children:
            which_children = self.children

        datadirs = []
        boot2docker = is_boot2docker()

        if which_children:
            if self.target:
                cp = SafeConfigParser()
                cp.read([self.target + '/.datacats-environment'])

            for child in which_children:
                if boot2docker:
                    remove_container('datacats_pgdata_' + self.name + '_' + child)
                else:
                    datadirs += [child + '/postgres']
                # Always rm the child dir & solr & files
                datadirs += [child, child + '/files', child + '/solr']
                if self.target:
                    cp.remove_section('child_' + child)
                    self.children.remove(child)

            if self.target:
                with open(self.target + '/.datacats-environment', 'w') as conf:
                    cp.write(conf)

        web_command(
            command=['/scripts/purge.sh']
                + ['/project/data/children/' + d for d in datadirs],
            ro={PURGE: '/scripts/purge.sh'},
            rw={self.datadir: '/project/data'},
            )
        if not self.children:
            shutil.rmtree(self.datadir)

    def logs(self, container, tail='all', follow=False, timestamps=False):
        """
        :param container: 'web', 'solr' or 'postgres'
        :param tail: number of lines to show
        :param follow: True to return generator instead of list
        :param timestamps: True to include timestamps
        """
        return container_logs(
            'datacats_' + container + '_' + self.name + '_' + self.child_name,
            tail,
            follow,
            timestamps)

    def _proxy_settings(self):
        """
        Create/replace ~/.datacats/run/proxy-environment and return
        entry for ro mount for containers
        """
        if not ('https_proxy' in environ or 'HTTPS_PROXY' in environ
                or 'http_proxy' in environ or 'HTTP_PROXY' in environ):
            return {}
        https_proxy = environ.get('https_proxy')
        if https_proxy is None:
            https_proxy = environ.get('HTTPS_PROXY')
        http_proxy = environ.get('http_proxy')
        if http_proxy is None:
            http_proxy = environ.get('HTTP_PROXY')
        no_proxy = environ.get('no_proxy')
        if no_proxy is None:
            no_proxy = environ.get('NO_PROXY', '')
        no_proxy = no_proxy + ',solr,db'

        out = ['PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games"\n']
        if https_proxy is not None:
            out.append('https_proxy=' + posix_quote(https_proxy) + '\n')
            out.append('HTTPS_PROXY=' + posix_quote(https_proxy) + '\n')
        if http_proxy is not None:
            out.append('http_proxy=' + posix_quote(http_proxy) + '\n')
            out.append('HTTP_PROXY=' + posix_quote(http_proxy) + '\n')
        if no_proxy is not None:
            out.append('no_proxy=' + posix_quote(no_proxy) + '\n')
            out.append('NO_PROXY=' + posix_quote(no_proxy) + '\n')

        with open(self.datadir + '/run/proxy-environment', 'w') as f:
            f.write("".join(out))

        return {self.datadir + '/run/proxy-environment': '/etc/environment'}


def posix_quote(s):
    return "\\'".join("'" + p + "'" for p in s.split("'"))
