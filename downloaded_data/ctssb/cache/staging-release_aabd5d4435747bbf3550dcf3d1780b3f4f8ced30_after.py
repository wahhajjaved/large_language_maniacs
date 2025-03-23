"""creates and configures ship it"""
import os
from lib.venv import Virtualenv, VirtualenvError
from sh import git
import lib.logger
import logging
import stat

log = logging.getLogger(__name__)


class ShipitError(Exception):
    """Generic Shipit error"""
    pass


class Shipit(object):
    """creates a shipit instance"""
    def __init__(self, configuration):
        self.repository = configuration.get('shipit', 'repository')
        self.username = configuration.get('shipit', 'username')
        self.password = configuration.get('shipit', 'password')
        self.basedir = configuration.get('shipit', 'basedir')
        req = configuration.get('shipit', 'requirements')
        self.requirements = os.path.join(self.basedir, req)
        self.configuration = configuration
        self.activate_path = None
        self.python_path = None

    def install(self):
        """installs buildbot master"""
        self._clone(self.basedir)
        self.create_virtualenv()
        self._create_startup_file()

    def create_virtualenv(self):
        """creates a virtualenv for ship it
           and install all the required packages
        """
        venv = Virtualenv(self.configuration)
        self.activate_path = venv.activate_path
        self.python_path = venv.python_path
        try:
            venv.create(self.basedir)
            venv.install_requirements_from_file(self.requirements)
        except VirtualenvError as error:
            msg = 'cannot create virtualenv: {0}'.format(error.message)
            log.error(msg)
            raise ShipitError(msg)

    def _clone(self, target_dir):
        """clones buildbot-configs into target_dir"""
        log.info('cloning {0}'.format(self.repository))
        git_cmd = ('clone', self.repository, target_dir)
        for line in git(git_cmd, _iter=True):
            log.debug(line.strip())

    def _create_startup_file(self):
        startup = self.configuration.get('shipit', 'startup')
        startup_path = self.configuration.get('shipit', 'startup_path')
        log.info('writing ship it startup file')
        with open(startup_path, 'w') as startup_script:
            startup_script.write('#!/bin/bash\n\n')
            startup_script.write('source {0}\n'.format(self.activate_path))
            startup_script.write("{0} {1}\n".format(self.python_path, startup))

        # log the new file
        with open(startup_path, 'r') as startup_script:
            log.debug(startup_script)

        # make it executable (the hard way)
        st = os.stat(startup_path)
        os.chmod(startup_path, st.st_mode | stat.S_IEXEC)

    def start(self):
        """starts a ship it instance"""
        pass

    def stop(self):
        """stops a ship it instance"""
        pass
