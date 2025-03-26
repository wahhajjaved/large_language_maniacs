# -*- coding: utf-8 -*-

import os.path

from cuisine import *


CONF_DIR = '/etc/swift'
STORAGE_CONFIGS = (
    'account-server.conf', 'object-server.conf', 'container-server.conf')

RSYNC_CONF = '/etc/rsyncd.conf'
OWNER = {
    'owner': 'swift',
    'group': 'swift'
}


def install_storage_packages():
    for package in ('swift-account', 'swift-container', 'swift-object'):
        package_ensure(package)


def install_storage_config():
    with cd(CONF_DIR):
        for config in STORAGE_CONFIGS:
            with mode_sudo():
                file_write(config, _template(config, {}))


def install_rsync_packages():
    package_ensure('rsync')


def install_rsync_config():
    rsync_conf_template = os.path.basename(RSYNC_CONF)

    with mode_sudo():
        file_write(RSYNC_CONF, _template(rsync_conf_template, {}))

    sudo("sed -ie 's/RSYNC_ENABLE=false/RSYNC_ENABLE=true/' "
         "/etc/default/rsync")


def start():
    sudo('swift-init all start')


def stop():
    sudo('swift-init all stop')


def _template(name, data):
    return _get_template(name).format(**data)


def _get_template(name):
    template_path = os.path.join(os.path.dirname(__file__), 'templates', name)

    with open(template_path) as template:
        return template.read()


# Validations

from expects import expect


def validate_storage_config():
    with cd(CONF_DIR):
        for config in STORAGE_CONFIGS:
            _expect_file_exists(config)
            _expect_owner(config, OWNER)


def validate_rsync_config():
    _expect_file_exists(RSYNC_CONF)
    _expect_owner(RSYNC_CONF, {'owner': 'root', 'group': 'root'})


def validate_started():
    for service in ('swift-account', 'swift-container', 'swift-object'):
        expect(process_find(service)).not_to.be.empty


def _expect_file_exists(path):
    expect(file_exists(path)).to.be.true


def _expect_owner(path, owner):
    attribs = file_attribs_get(path)

    expect(attribs).to.have.keys(owner)
