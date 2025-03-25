# Copyright 2014-2015 Boxkite Inc.

# This file is part of the DataCats package and is released under
# the terms of the GNU Affero General Public License version 3.0.
# See LICENSE.txt or http://www.fsf.org/licensing/licenses/agpl-3.0.html

from os.path import abspath, split as path_split, expanduser, isdir, exists
from os import makedirs, getcwd, remove
import sys
import subprocess
import shutil
import json
import time
from string import uppercase, lowercase, digits
from random import SystemRandom
from sha import sha
from struct import unpack
from ConfigParser import (SafeConfigParser, Error as ConfigParserError,
    NoOptionError, NoSectionError)

from datacats.validate import valid_name
from datacats.docker import (web_command, run_container, remove_container,
    inspect_container, is_boot2docker, data_only_container, docker_host,
    PortAllocatedError, container_logs, remove_image, WebCommandError)
from datacats.template import ckan_extension_template
from datacats.scripts import WEB, SHELL, PASTER, PASTER_CD, PURGE
from datacats.network import wait_for_service_available, ServiceTimeout

WEB_START_TIMEOUT_SECONDS = 30
DB_INIT_RETRY_SECONDS = 30
DB_INIT_RETRY_DELAY = 2
DOCKER_EXE = 'docker'


class ProjectError(Exception):
    def __init__(self, message, format_args=()):
        self.message = message
        self.format_args = format_args
        super(ProjectError, self).__init__(message, format_args)

    def __str__(self):
        return self.message.format(*self.format_args)


class Project(object):
    """
    DataCats project settings object

    Create with Project.new(path) or Project.load(path)
    """
    def __init__(self, name, target, datadir, ckan_version=None, port=None,
                deploy_target=None, site_url=None, always_prod=False,
                extension_dir='ckan'):
        self.name = name
        self.target = target
        self.datadir = datadir
        self.extension_dir = extension_dir
        self.ckan_version = ckan_version
        self.port = int(port if port else self._choose_port())
        self.deploy_target = deploy_target
        self.site_url = site_url
        self.always_prod = always_prod

    def save(self):
        """
        Save project settings into project directory
        """
        cp = SafeConfigParser()

        cp.add_section('datacats')
        cp.set('datacats', 'name', self.name)
        cp.set('datacats', 'ckan_version', self.ckan_version)
        cp.set('datacats', 'port', str(self.port))

        if self.deploy_target:
            cp.add_section('deploy')
            cp.set('deploy', 'target', self.deploy_target)

        if self.site_url or self.always_prod:
            if self.site_url:
                cp.set('datacats', 'site_url', self.site_url)
            if self.always_prod:
                cp.set('datacats', 'always_prod', 'true')

        with open(self.target + '/.datacats-environment', 'w') as config:
            cp.write(config)

        # save passwords to datadir
        cp = SafeConfigParser()

        cp.add_section('passwords')
        for n in sorted(self.passwords):
            cp.set('passwords', n.lower(), self.passwords[n])

        with open(self.datadir + '/passwords.ini', 'w') as config:
            cp.write(config)

        self._update_saved_project_dir()

    def _update_saved_project_dir(self):
        """
        Store the last place we've seen this project so the user
        can use "datacats -p ..." to specify a project by name
        """
        with open(self.datadir + '/project-dir', 'w') as pdir:
            pdir.write(self.target)

    @classmethod
    def new(cls, path, ckan_version, port=None):
        """
        Return a Project object with settings for a new project.
        No directories or containers are created by this call.

        :params path: location for new project directory, may be relative
        :params ckan_version: release of CKAN to install
        :params port: preferred port for local instance

        Raises ProjectError if directories or project with same
        name already exits.
        """
        workdir, name = path_split(abspath(expanduser(path)))

        if not valid_name(name):
            raise ProjectError('Please choose an environment name starting'
                ' with a letter and including only lowercase letters'
                ' and digits')
        if not isdir(workdir):
            raise ProjectError('Parent directory for environment'
                ' does not exist')

        datadir = expanduser('~/.datacats/' + name)
        target = workdir + '/' + name

        if isdir(datadir):
            raise ProjectError('Environment data directory {0} already exists',
                (datadir,))
        if isdir(target):
            raise ProjectError('Environment directory already exists')

        project = cls(name, target, datadir, ckan_version, port)
        project._generate_passwords()
        return project

    @classmethod
    def load(cls, project_name=None, data_only=False):
        """
        Return a Project object based on an existing project.

        :param project_name: exising project name, path or None to look in
            current or parent directories for project
        :param data_only: set to True to only load from data dir, not
            the project dir; Used for purging project data.

        Raises ProjectError if project can't be found or if there is an
        error parsing the project information.
        """
        if project_name is None:
            project_name = '.'

        extension_dir = 'ckan'
        if valid_name(project_name) and isdir(
                expanduser('~/.datacats/' + project_name)):
            used_path = False
            datadir = expanduser('~/.datacats/' + project_name)
            with open(datadir + '/project-dir') as pd:
                wd = pd.read()
            if not data_only and not exists(wd + '/.datacats-environment'):
                raise ProjectError(
                    'Environment data found but environment directory is'
                    ' missing. Try again from the new environment directory'
                    ' location or remove the environment data with'
                    ' "datacats purge"')
        else:
            used_path = True
            wd = abspath(project_name)
            if not isdir(wd):
                raise ProjectError('No environment found with that name')

            first_wd = wd
            oldwd = None
            while not exists(wd + '/.datacats-environment'):
                oldwd = wd
                wd, ignore = path_split(wd)
                if wd == oldwd:
                    raise ProjectError(
                        'Environment not found in {0} or above', first_wd)

            if oldwd:
                ignore, extension_dir = path_split(oldwd)

        if data_only and not used_path:
            return cls(project_name, None, datadir)

        cp = SafeConfigParser()
        try:
            cp.read([wd + '/.datacats-environment'])
        except ConfigParserError:
            raise ProjectError('Error reading environment information')

        name = cp.get('datacats', 'name')
        datadir = expanduser('~/.datacats/' + name)
        ckan_version = cp.get('datacats', 'ckan_version')
        try:
            port = cp.getint('datacats', 'port')
        except NoOptionError:
            port = None
        try:
            site_url = cp.get('datacats', 'site_url')
        except NoOptionError:
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
            cp.read(datadir + '/passwords.ini')
            try:
                pw_options = cp.options('passwords')
            except NoSectionError:
                pw_options = []

        for n in pw_options:
            passwords[n.upper()] = cp.get('passwords', n)

        project = cls(name, wd, datadir, ckan_version, port, deploy_target,
        site_url=site_url, always_prod=always_prod, extension_dir=extension_dir)
        if passwords:
            project.passwords = passwords
        else:
            project._generate_passwords()

        if not used_path:
            project._update_saved_project_dir()

        return project

    def data_exists(self):
        """
        Return True if the datadir for this project exists
        """
        return isdir(self.datadir)

    def data_complete(self):
        """
        Return True if all the expected datadir files are present
        """
        if (not isdir(self.datadir + '/files')
                or not isdir(self.datadir + '/run')
                or not isdir(self.datadir + '/search')):
            return False
        if is_boot2docker():
            return True
        return (
            isdir(self.datadir + '/venv') and
            isdir(self.datadir + '/data'))

    def require_data(self):
        """
        raise a ProjectError if the datadir is missing or damaged
        """
        if not self.data_exists():
            raise ProjectError('Environment datadir missing. '
                'Try "datacats init".')
        if not self.data_complete():
            raise ProjectError('Environment datadir damaged. '
                'Try "datacats purge" followed by "datacats init".')

    def create_directories(self, create_project_dir=True):
        """
        Call once for new projects to create the initial project directories.
        """
        makedirs(self.datadir, mode=0o700)
        makedirs(self.datadir + '/search')
        if not is_boot2docker():
            makedirs(self.datadir + '/venv')
            makedirs(self.datadir + '/data')
        makedirs(self.datadir + '/files')
        makedirs(self.datadir + '/run')
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
            data_only_container('datacats_pgdata_' + self.name,
                ['/var/lib/postgresql/data'])
            rw = {}
            volumes_from = 'datacats_pgdata_' + self.name
        else:
            rw = {self.datadir + '/postgres': '/var/lib/postgresql/data'}
            volumes_from = None

        # users are created when data dir is blank so we must pass
        # all the user passwords as environment vars
        run_container(
            name='datacats_postgres_' + self.name,
            image='datacats/postgres',
            environment=self.passwords,
            rw=rw,
            volumes_from=volumes_from)
        run_container(
            name='datacats_solr_' + self.name,
            image='datacats/solr',
            rw={self.datadir + '/solr': '/var/lib/solr'},
            ro={self.target + '/schema.xml': '/etc/solr/conf/schema.xml'})

    def stop_postgres_and_solr(self):
        """
        stop and remove postgres and solr containers
        """
        remove_container('datacats_postgres_' + self.name)
        remove_container('datacats_solr_' + self.name)

    def fix_storage_permissions(self):
        """
        Set the owner of all apache storage files to www-data container user
        """
        web_command(
            command='/bin/chown -R www-data: /var/www/storage',
            rw={self.datadir + '/files': '/var/www/storage'})

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
        Use config-tool to update development.ini with our project settings

        :param skin: use project template skin plugin True/False
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
        Create an example ckan extension for this project and install it
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
            'POSTGRES_PASSWORD': generate_db_password(),
            'CKAN_PASSWORD': generate_db_password(),
            'DATASTORE_RO_PASSWORD': generate_db_password(),
            'DATASTORE_RW_PASSWORD': generate_db_password(),
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
            raise ProjectError('Error reading development.ini')

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

        if not isdir(self.datadir + '/run'):
            makedirs(self.datadir + '/run')  # upgrade old datadir
        with open(self.datadir + '/run/' + output, 'w') as runini:
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
            name='datacats_web_' + self.name,
            image='datacats/web',
            rw={self.datadir + '/files': '/var/www/storage'},
            ro=dict({
                self.target: '/project/',
                self.datadir + '/run/development.ini':
                    '/project/development.ini',
                WEB: '/scripts/web.sh'}, **ro),
            links={'datacats_solr_' + self.name: 'solr',
                'datacats_postgres_' + self.name: 'db'},
            volumes_from=volumes_from,
            command=command,
            port_bindings={
                5000: port if is_boot2docker() else ('127.0.0.1', port)},
            )

    def wait_for_web_available(self):
        """
        Wait for the web server to become available or raise ProjectError
        if it fails to start.
        """
        try:
            if not wait_for_service_available(
                    'datacats_web_' + self.name,
                    self.web_address(),
                    WEB_START_TIMEOUT_SECONDS):
                raise ProjectError('Failed to start web container.'
                    ' Run "datacats logs" to check the output.')
        except ServiceTimeout:
            raise ProjectError('Timeout waiting for web container to start.'
                ' Run "datacats logs" to check the output.')

    def _choose_port(self):
        """
        Return a port number from 5000-5999 based on the project name
        to be used as a default when the user hasn't selected one.
        """
        # instead of random let's base it on the name chosen
        return 5000 + unpack('Q',
            sha(self.name.decode('ascii')).digest()[:8])[0] % 1000

    def _next_port(self, port):
        """
        Return another port from the 5000-5999 range
        """
        port = 5000 + (port + 1) % 1000
        if port == self.port:
            raise ProjectError('Too many instances running')
        return port

    def stop_web(self):
        """
        Stop and remove the web container
        """
        remove_container('datacats_web_' + self.name, force=True)

    def _current_web_port(self):
        """
        return just the port number for the web container, or None if
        not running
        """
        info = inspect_container('datacats_web_' + self.name)
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
        Return a list including 0 or more of ['web', 'data', 'search']
        for containers tracked by this project that are running
        """
        running = []
        for n in ['web', 'postgres', 'solr']:
            info = inspect_container('datacats_' + n + '_' + self.name)
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
        with open(self.datadir + '/run/admin.json', 'w') as out:
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
            ro={self.datadir + '/run/admin.json': '/input/admin.json'},
            )
        remove(self.datadir + '/run/admin.json')

    def interactive_shell(self, command=None, paster=False):
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

        # FIXME: consider switching this to dockerpty
        # using subprocess for docker client's interactive session
        return subprocess.call([
            DOCKER_EXE, 'run', '--rm',
            '-it' if use_tty else '-i',
            ] + venv_volumes + [
            '-v', self.target + ':/project:rw',
            '-v', self.datadir + '/files:/var/www/storage:rw',
            '-v', script + ':/scripts/shell.sh:ro',
            '-v', PASTER_CD + ':/scripts/paster_cd.sh:ro',
            '-v', self.datadir + '/run/run.ini:/project/development.ini:ro',
            '-v', self.datadir + '/run/test.ini:/project/ckan/test-core.ini:ro',
            '--link', 'datacats_solr_' + self.name + ':solr',
            '--link', 'datacats_postgres_' + self.name + ':db',
            '--hostname', self.name,
            'datacats/web', '/scripts/shell.sh'] + command)

    def install_package_requirements(self, psrc):
        """
        Install from requirements.txt file found in src_package

        :param src_package: name of directory under project src directory
        """
        package = self.target + '/' + psrc
        assert isdir(package), package
        reqname = '/requirements.txt'
        if not exists(package + reqname):
            reqname = '/pip-requirements.txt'
            if not exists(package + reqname):
                return
        self.run_command(
            command=[
                '/usr/lib/ckan/bin/pip', 'install', '-r',
                '/project/' + psrc + reqname,
                ],
            rw_venv=True,
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
        self.run_command(
            ['/usr/lib/ckan/bin/pip', 'install', '-e', '/project/' + psrc],
            rw_venv=True,
            rw={self.target + '/' + psrc: '/project/' + psrc},
            )
        # .egg-info permissions
        self.run_command(
            ['/bin/chown', '-R', '--reference=/project', '/project/' + psrc],
            rw={self.target + '/' + psrc: '/project/' + psrc},
            )

    def run_command(self, command, db_links=False, rw_venv=False,
            rw_project=False, rw=None, ro=None, clean_up=False):

        rw = {} if rw is None else dict(rw)
        ro = {} if ro is None else dict(ro)

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
                'datacats_solr_' + self.name: 'solr',
                'datacats_postgres_' + self.name: 'db',
                }
            ro[self.datadir + '/run/run.ini'] = '/project/development.ini'
        else:
            links = None

        return web_command(command=command, ro=ro, rw=rw, links=links,
                volumes_from=volumes_from, clean_up=clean_up)


    def purge_data(self):
        """
        Remove uploaded files, postgres db, solr index, venv
        """
        datadirs = ['files', 'solr']
        if is_boot2docker():
            remove_container('datacats_pgdata_' + self.name)
            remove_container('datacats_venv_' + self.name)
        else:
            datadirs += ['postgres', 'venv']

        web_command(
            command=['/scripts/purge.sh']
                + ['/project/data/' + d for d in datadirs],
            ro={PURGE: '/scripts/purge.sh'},
            rw={self.datadir: '/project/data'},
            )
        shutil.rmtree(self.datadir)

    def logs(self, container, tail='all', follow=False, timestamps=False):
        """
        :param container: 'web', 'solr' or 'postgres'
        :param tail: number of lines to show
        :param follow: True to return generator instead of list
        :param timestamps: True to include timestamps
        """
        return container_logs(
            'datacats_' + container + '_' + self.name,
            tail,
            follow,
            timestamps)


def generate_db_password():
    """
    Return a 16-character alphanumeric random string generated by the
    operating system's secure pseudo random number generator
    """
    chars = uppercase + lowercase + digits
    return ''.join(SystemRandom().choice(chars) for x in xrange(16))
