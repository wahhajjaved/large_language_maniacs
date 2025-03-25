"""creates and cofigures a staging master"""
import os
import json
import tempfile
import shutil
from sh import hg
from sh import make
import lib.logger
import logging
from lib.config import Config

log = logging.getLogger(__name__)


class MasterError(Exception):
    """Generic Master error"""
    pass


class Master(object):
    """creates a buildbot master"""
    def __init__(self, configuration):
        self.username = configuration.get('DEFAULT', 'username')
        self.basedir = configuration.get('master', 'basedir')
        self.http_port = configuration.get('master', 'http_port')
        self.ssh_port = configuration.get('master', 'ssh_port')
        self.pb_port = configuration.get('master', 'pb_port')
        self.role = configuration.get('master', 'role')
        self.buildbot_configs_repo = configuration.get('master',
                                                       'buildbot_configs_repo')

    def install(self):
        """installs buildbot master"""
        self._prepare_dirs()
        tmp_dir = tempfile.mkdtemp()
        log.info('installing buildbot master')
        log.debug('tmp_dir: {0}'.format(tmp_dir))
        self._clone_builbot_configs(tmp_dir)
        self._make(tmp_dir)
        self.write_master_json(self)
        shutil.rmtree(tmp_dir)

    def _prepare_dirs(self):
        """creates required directories
           rises a MasterError if directories are already in place."""
        # If a directory already exists, probably, this script
        # probaly this script has been executed
        try:
            os.makedirs(self.basedir)
        except OSError as error:
            msg = 'Cannot create: {0} ({1})'.format(self.basedir, error)
            raise MasterError(msg)

    def _clone_builbot_configs(self, target_dir):
        """clones buildbot-configs into target_dir"""
        log.info('cloning {0}'.format(self.buildbot_configs_repo))
        hg_cmd = ('clone', self.buildbot_configs_repo, target_dir)
        for line in hg(hg_cmd, _iter=True):
            log.debug(line.strip())

    def _make(self, cwd):
        """calls make to create a buildbot master"""
        log.info('creating master in {0}'.format(self.basedir))
        make_cmd = ['-f', 'Makefile.setup']
        make_cmd += ['USE_DEV_MASTER=1']
        make_cmd += ['MASTER_NAME={0}'.format(self.username)]
        make_cmd += ['BASEDIR={0}'.format(self.basedir)]
        make_cmd += ['PYTHON=python2.6']
        make_cmd += ['VIRTUALENV=virtualenv-2.6']
        make_cmd += ['BUILDBOTCUSTOM_BRANCH=default']
        make_cmd += ['BUILDBOTCONFIGS_BRANCH=default']
        make_cmd += ['USER={0}'.format(self.username)]
        make_cmd += ['HTTP_PORT={0}'.format(self.http_port)]
        make_cmd += ['PB_PORT={0}'.format(self.pb_port)]
        make_cmd += ['SSH_PORT={0}'.format(self.ssh_port)]
        make_cmd += ['ROLE={0}'.format(self.role)]
        make_cmd += ['virtualenv', 'deps', 'install-buildbot']
        make_cmd += ['master', 'master-makefile']

        for line in make(make_cmd, _cwd=cwd, _iter=True):
            log.debug(line.strip())

    def start(self):
        """starts a master instance"""
        make('start', _cwd=self.basedir)

    def stop(self):
        """stops a master instance"""
        make('stops', _cwd=self.basedir)

    def checkconfig(self):
        """checks master configuration"""
        make('checkconfig', _cwd=self.basedir)

    def write_master_json(self):
        conf = self.configuration
        src_json_ini = conf.get('master', 'src_json_ini')
        dst_json = conf.get('master', 'dst_json')
        mj = MasterJson(self.configuration, src_json_ini)
        mj.write(dst_json)


class MasterJson(object):
    def __init__(self, configuration, src_ini_file):
        self.section = 'master_json'

        dst_conf = Config()
        # set values in current section
        # read values form other sections and write them
        # in current section so it can be interpolated
        basedir = configuration.get('master', 'basedir')
        http_port = configuration.get('master', 'http_port')
        ssh_port = configuration.get('master', 'ssh_port')
        pb_port = configuration.get('master', 'pb_port')

        dst_conf.set('DEFAULT', 'basedir', basedir)
        dst_conf.set('DEFAULT', 'http_port', http_port)
        dst_conf.set('DEFAULT', 'ssh_port', ssh_port)
        dst_conf.set('DEFAULT', 'pb_port', pb_port)
        dst_conf.read_file(src_ini_file)
        self.configuration = dst_conf

    def _limit_keys(self):
        limit = []
        conf = self.configuration
        for limit in conf.get(self.section, 'limit_keys').split(','):
            limit.append(conf._sections[limit])
        return limit

    def write(self, dst):
        # json file == this section + limit branches
        conf = self._sections[self.section]
        conf.append(self._limit_keys)
        print json.dump(conf)
