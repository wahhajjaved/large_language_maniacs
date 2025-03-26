"""rook virtual env control"""
import atexit
import tempfile
import os
import sys
import re
import logging
import argparse
import glob
import shutil
import subprocess as sp
import imp
import stat

import yaml
import setuptools
import subprocess
from rsetup import proc, config


PACKAGE_NAME = re.compile('[a-zA-Z0-9-_]{1,64}$')

TEST_PKGS = ['GitPython==0.3.2.RC1',
             'coverage==3.6',
             'pytest-cov==1.6',
             'pylint==0.28.0',
             'behave==1.2.3',
             'selenium==2.33.0',
             'tox']

ARG_PARSER = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)


SUB_PARSER = ARG_PARSER.add_subparsers(help='Command help')

LOG = logging.getLogger(__name__)


def shellquote(path):
    """escape a path

    :rtype str:"""
    return "'" + path.replace("'", "'\\''") + "'"


def command(func):
    """Decorator for CLI exposed functions"""
    func.parser = SUB_PARSER.add_parser(func.func_name, help=func.__doc__)
    func.parser.set_defaults(func=func)

    # options for all commands
    func.parser.add_argument('--ci', action='store_true',
                             help='running in CI context')
    func.parser.add_argument('--config', help='path to config', default='.')
    return func


def get_setup_data(path):
    """get the arguments of setup() call inside a setup.py by fake loading it

    The only way to get data out of a setup.py is by executing it.  The setuptools
    is mocked to extract the desired information

    :param path: path to the setup.py file
    :type path: str
    :rtype: dict
    """
    data = {}

    old_setup = setuptools.setup
    old_modules = sys.modules.keys()

    def s(**kwargs):
        data.update(kwargs)

    setuptools.setup = s
    imp.load_source('fake-load-setup-py', path)

    for module in sys.modules.keys():
        if module not in old_modules:
            del sys.modules[module]

    setuptools.setup = old_setup
    return data


def get_config_path(args):
    """get the path of the config file if existent

    :rtype: str
    """
    path = os.path.abspath(os.path.join(args.config, '.ci.yml'))
    if os.path.exists(path):
        return path


def get_module_path(name):
    """get the path of the module given by name

    This imports the named module and therefore might have side effects

    :param name: Name of the module
    :type name: str
    :rtype: str
    """
    return os.path.dirname(__import__(name).__file__)


def get_python_interpreter(args):
    if 'PYTHON_EXE' in os.environ:
        return os.environ['PYTHON_EXE']
    return 'python'


@command
def sdist(args):
    """create source distribution

    returns path
    :rtype: str
    """
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    python = get_python_interpreter(args)
    proc.exe([python, 'setup.py', 'sdist', '--dev'])
    dist = os.listdir('dist')
    assert len(dist) == 1
    return os.path.abspath('dist/' + dist[0])


@command
def test(args):
    setup_data = get_setup_data('setup.py')
    pkgs = setup_data['packages']
    pkgs = set(pkg.split('.')[0] for pkg in pkgs)
    pkgs = list(pkgs)

    if args.cfg['test.pytest']:
        LOG.info('running py.test')
        for pkg in pkgs:
            py_test = ['py.test', '--cov', pkg]
            if args.ci:
                py_test += ['--cov-report', 'xml', '--junitxml=junit.xml']
            py_test.append(pkg)

            proc.exe(py_test)
        if args.ci:
            proc.exe(['coverage', 'html'])

    if args.cfg['test.pylint']:
        LOG.info('running pylint')
        pylint = ['pylint', '-f', 'parseable'] + pkgs
        # maybe check pylint return code
        # http://lists.logilab.org/pipermail/python-projects/2009-November/002068.html
        pylint_out = proc.read(pylint, check_exit_code=False)
        open('pylint.out', 'w').write(pylint_out)

    if args.cfg['test.behave']:
        LOG.info('running behave')
        for path in args.cfg['test.behave.features']:
            proc.exe(['behave', path])


@command
def setup(args):
    pkgs = TEST_PKGS[:]
    if args.cfg['test.behave']:
        pkgs.append('rbehave>=0.0.0.git0')
    p = subprocess.Popen(['pip', 'install'] + pkgs)
    p.wait()

    pkgs = proc.read(['pip', 'freeze'])
    before = open('pip_freeze_before_install.txt', 'w')
    for line in pkgs.split('\n'):
        if not line.startswith('rsetup') or line.startswith('configobj'):
            before.write(line + '\n')
    before.close()


@command
def ci(args):
    args.ci = True

    # read config
    LOG.info('Working path %s', os.path.abspath('.'))
    config_arg = ''
    cfg = get_config_path(args)
    if cfg:
        LOG.info('loading {}'.format(cfg))
        args.cfg.update(yaml.load(open('.ci.yml')))
        config_arg = '--config ' + shellquote(cfg)

    setup(args)
    dist = sdist(args)

    if os.path.exists('tox.ini'):
        print ("package tox.ini cannot be handled at this time")

    tox = open('tox.ini', 'w')
    tox.write("""[tox]
envlist = {envist}

[testenv]
deps = rsetup
commands =
  rve initve --ci
  rve setup --ci {config_arg}
  rve test --ci {config_arg}
""".format(envist=args.cfg['envlist'], config_arg=config_arg))
    tox.close()
    proc.exe(['tox', '--installpkg', dist])


def create_test_ve(args):
    """create a virtual env to run tests in"""
    ve_path = tempfile.mkdtemp()
    proc.exe(['virtual'])
    proc.exe(['pip', 'install'] + glob.glob('dist/*.tar.gz'))

    def rm_test_ve():
        shutil.rmtree(ve_path)
    atexit.register(rm_test_ve)
    return ve_path


@command
def initve(args):
    """initilize virtual env with rsetup default configuration"""
    if not 'VIRTUAL_ENV' in os.environ:
        LOG.error('mist be run inside active virtual env')
        return
    run_script = """#!{ve_path}/bin/python

VIRTUAL_ENV = '{ve_path}'

import os
import sys

os.environ['VIRTUAL_ENV'] = VIRTUAL_ENV
os.environ['PATH'] = VIRTUAL_ENV + '/bin:' + os.environ['PATH']

print 'running in ve ' + VIRTUAL_ENV
print sys.argv[1], sys.argv[2:]
sys.stdout.flush()
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
    """
    run_script = run_script.format(ve_path=os.environ['VIRTUAL_ENV'])
    run_script_path = os.path.join(os.environ['VIRTUAL_ENV'], 'bin', 'run')
    if os.path.exists(run_script_path):
        os.unlink(run_script_path)
    open(run_script_path, 'w').write(run_script)
    os.chmod(run_script_path, stat.S_IEXEC | stat.S_IREAD | stat.S_IWUSR)


def rve():
    """rve command line tool entry point"""
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    logging.basicConfig(level=getattr(logging, log_level),
                        format='%(asctime)s %(name)s[%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    args = ARG_PARSER.parse_args()
    args.git_root = proc.read('git', 'rev-parse', '--show-toplevel').strip()
    args.cfg = {'test.pytest': False,
                'test.pylint': False,
                'test.behave': False,
                'test.behave.features': set(),
                'envlist': 'py27'
                }

    # auto detect tests to run
    for dirpath, dirnames, filenames in os.walk('.'):
        for fname in filenames:
            if fname.endswith('.py'):
                args.cfg['test.pylint'] = True
            elif fname.endswith('.feature'):
                args.cfg['test.behave'] = True
                args.cfg['test.behave.features'].add(dirpath)

            if fname.startswith('test_') and fname.endswith('.py'):
                args.cfg['test.pytest'] = True

    args.func(args)