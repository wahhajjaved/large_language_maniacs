#!/usr/bin/env python3

import os
import re
import apt
import yaml
import errno
import shutil
from random import choice
from string import hexdigits
from datetime import datetime
from subprocess import check_call, check_output, CalledProcessError
from distutils.dir_util import copy_tree
from charms.reactive import set_state
from charmhelpers.core import hookenv
from charmhelpers.fetch import (
    add_source,
    apt_update,
    apt_install,
    )
from charmhelpers.core.templating import render


os.environ['DJANGO_SETTINGS_MODULE'] = 'weebl.settings'
WEEBL_YAML = '/etc/weebl/weebl.yaml'
WEEBL_SETTINGS_PATH = "/usr/lib/python3/dist-packages/weebl/settings.py"
WEEBL_PKG = "python3-weebl"
NON_WEEBL_DEB_PKGS = ["postgresql-client", "npm", "python3-pip"]
PIP_DIR = "./wheels/"
NPM_DIR = "./npms/"
JSLIBS_DIR = "/var/lib/weebl/static"
SVG_DIR = os.path.join(JSLIBS_DIR, "img/bundles")


def mkdir_p(directory_name):
    try:
        os.makedirs(directory_name)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(directory_name):
            raise exc


def get_package_version(pkg):
    try:
        cache = apt.Cache()[pkg]
        if not cache.is_installed:
            return False
        return cache.installed.version.split('~')[0]
    except KeyError:
        return False


def get_weebl_package_version():
    return get_package_version(WEEBL_PKG)


def cmd_service(cmd, service):
    command = ['systemctl', cmd, service]
    hookenv.log(command)
    check_call(command)


def fix_bundle_dir_permissions():
    shutil.chown(path="{}/img/bundles/".format(JSLIBS_DIR), user="www-data")


def get_or_generate_apikey(apikey):
    if apikey not in [None, "", "None"]:
        hookenv.log("Using apikey already provided.")
        return apikey
    else:
        hookenv.log("No apikey provided - generating random apikey.")
        return ''.join([choice(hexdigits[:16]) for _ in range(40)])


def install_npm_deps():
    hookenv.log('Installing npm packages...')
    node_modules_dir = os.path.join(JSLIBS_DIR, "node_modules")
    if not os.path.exists(node_modules_dir):
        mkdir_p(node_modules_dir)
    original_dir = os.getcwd()
    full_path_to_npms = os.path.abspath(NPM_DIR)
    try:
        os.chdir(full_path_to_npms)
        check_call(["npm", "install"])
        copy_tree("node_modules", node_modules_dir)
    finally:
        os.chdir(original_dir)


def install_pip_deps():
    hookenv.log('Installing pip packages...')
    with open(os.path.join(PIP_DIR, "wheels.yaml"), 'r') as f:
        pips = yaml.load(f.read())
    for pip in pips:
        msg = "Installing {} via pip".format(pip)
        hookenv.status_set('maintenance', msg)
        hookenv.log(msg)
        check_call(['pip3', 'install', '-U', '--no-index', '-f', PIP_DIR, pip])


def edit_settings(debug_mode):
    hookenv.status_set(
        'maintenance', "Setting DEBUG to {} in {}"
        .format(debug_mode, WEEBL_SETTINGS_PATH))
    if not os.path.isfile(WEEBL_SETTINGS_PATH):
        err_msg = 'There is no settings file here!: {}'.format(
            WEEBL_SETTINGS_PATH)
        hookenv.log(err_msg)
        raise Exception(err_msg)
    with open(WEEBL_SETTINGS_PATH, 'r') as weebl_settings_file:
        weebl_settings = weebl_settings_file.read()
        weebl_settings = re.sub(
            "\nDEBUG = .*\n",
            "\nDEBUG = " + debug_mode + "\n",
            weebl_settings)
        weebl_settings = re.sub(
            "\nTEMPLATE_DEBUG = .*\n",
            "\nTEMPLATE_DEBUG = " + debug_mode + "\n",
            weebl_settings)
    with open(WEEBL_SETTINGS_PATH, 'w') as weebl_settings_file:
        weebl_settings_file.write(weebl_settings)
    cmd_service('restart', 'weebl-gunicorn')
    hookenv.status_set('active', 'Ready')


def setup_weebl_site(config):
    hookenv.log('Setting up weebl site...')
    check_call(['django-admin', 'set_up_site', config['weebl_name'].lower()])


def generate_timestamp(timestamp_format="%F_%H-%M-%S"):
    return datetime.now().strftime(timestamp_format)


def render_config(pgsql):
    db_settings = {
        'host':  pgsql.master['host'],
        'port': pgsql.master['port'],
        'database': pgsql.master['dbname'],
        'user': pgsql.master['user'],
        'password': pgsql.master['password'],
    }
    db_config = {
        'database': db_settings,
        'static_root': JSLIBS_DIR,
    }
    mkdir_p(os.path.dirname(WEEBL_YAML))
    with open(WEEBL_YAML, 'w') as weebl_db:
        weebl_db.write(yaml.dump(db_config))


def get_weebl_data():
    return yaml.load(open(WEEBL_YAML).read())['database']


def install_deb_from_ppa(pkg, config):
    hookenv.log('Adding ppa')
    ppa = config['ppa']
    ppa_key = config['ppa_key']
    add_source(ppa, ppa_key)
    install_deb(pkg)


def install_debs(weebl_pkg, config):
    hookenv.status_set('maintenance', 'Installing Weebl package')
    for deb_pkg in NON_WEEBL_DEB_PKGS:
        hookenv.status_set('maintenance', 'Installing ' + deb_pkg + ' package')
        install_deb(deb_pkg)
    install_deb_from_ppa(weebl_pkg, config)


def install_weebl(config):
    install_debs(WEEBL_PKG, config)
    install_npm_deps()
    install_pip_deps()
    setup_weebl_gunicorn_service(config)
    cmd_service('start', 'weebl-gunicorn')
    cmd_service('restart', 'nginx')
    setup_weebl_site(config)
    fix_bundle_dir_permissions()
    edit_settings(config['debug_mode'])
    hookenv.open_port(80)
    hookenv.status_set('active', 'Ready')
    set_state('weebl.ready')


def install_deb(pkg):
    hookenv.log('Installing/upgrading {}!'.format(pkg))
    apt_update()
    apt_install([pkg])
    hookenv.log("{} installed!".format(pkg))


def setup_weebl_gunicorn_service(config):
    render(
        source="weebl-gunicorn.service",
        target="/lib/systemd/system/weebl-gunicorn.service",
        context={'extra_options': config['extra_options']})
    cmd_service('enable', 'weebl-gunicorn')


def backup_testrun_svgs(parent_dir):
    hookenv.log("Copying test run svgs")
    destination = os.path.join(parent_dir, 'bundles/')
    copy_tree(SVG_DIR, destination)
    hookenv.log("Bundle images (SVGs) copied to {}".format(destination))


def add_testrun_svgs_to_bundles_dir(source):
    mkdir_p(SVG_DIR)
    bundles = os.path.join(source, 'weebl_data/bundles')
    copy_tree(bundles, SVG_DIR)
    fix_bundle_dir_permissions()
    hookenv.log("Bundle images (SVGs) copied into {}".format(SVG_DIR))


def remote_db_cli_interaction(app, weebl_data, custom=''):
    os.environ['PGPASSWORD'] = weebl_data['password']
    base_cmd = [app, '-h', weebl_data['host'], '-U', weebl_data['user'], '-p',
                weebl_data['port']]
    base_cmd.extend(custom)
    hookenv.log(
        "PGPASSWORD=" + os.environ['PGPASSWORD'] + " " + " ".join(base_cmd))
    return check_call(base_cmd)


def save_database_dump(weebl_data, output_file):
    custom = ['-f', output_file, '--no-owner', '--no-acl', '-x', '-F', 't',
              '-d', weebl_data['database']]
    remote_db_cli_interaction("pg_dump", weebl_data, custom)


def drop_database(weebl_data, database):
    remote_db_cli_interaction("dropdb", weebl_data, [database])


def create_empty_database(weebl_data, database, postgres_user="postgres"):
    create_cmds = [database, '-O', postgres_user]
    remote_db_cli_interaction("createdb", weebl_data, create_cmds)


def upload_database_dump(weebl_data, dump_file):
    restore_cmds = ['-d', weebl_data['database'], '--exit-on-error',
                    '--no-owner', dump_file]
    remote_db_cli_interaction("pg_restore", weebl_data, restore_cmds)


def create_default_user(username, email, uid, apikey, provider="ubuntu"):
    hookenv.log('Setting up {} as the default user...'.format(username))
    try:
        check_call(['django-admin', 'preseed_user', username,
                    email, provider, uid, apikey, True])
    except CalledProcessError:
        err_msg = "Error setting up default weebl user ({})".format(username)
        hookenv.log(err_msg)
        hookenv.status_set('maintenance', err_msg)
        raise Exception(err_msg)


def run_migrations(cwd='/home/ubuntu/'):
    hookenv.log('Running migrations...')
    os.chdir(cwd) # as otherwise we get a FileNotFound error
    output = check_output(['django-admin', 'migrate', '--noinput'])
    for line in output.decode('utf-8').split('\n'):
        hookenv.log(line)
