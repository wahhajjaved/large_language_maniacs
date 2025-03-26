import sys
import socket
import logging
import collections
import operator
import re
from distutils.version import LooseVersion

import requests
from lettuce import world

from lxml import etree

from revizor2.api import Server
from revizor2.conf import CONF
from revizor2.consts import ServerStatus

LOG = logging.getLogger(__name__)


IP_RESOLVER_SITES = (
    'http://revizor2.scalr-labs.com/get_ext_ip/',
    'http://ifconfig.me/ip',
    'http://myexternalip.com/raw',
    'http://ip-address.ru/show'
)


@world.absorb
def wrt(what):
    what = etree.tostring(what)
    if isinstance(what, unicode):
        what = what.encode('utf-8')
    sys.stdout.write(what+'\n')


@world.absorb
def run_only_if(*args, **kwargs):
    """
    Accept parameters: platform, storage, dist, szr_version
    """
    if kwargs.get('szr_version'):
        check_version = kwargs.get('szr_version').translate(None, '<>=!')
        comparison = ''.join(set(kwargs.get('szr_version')).difference(check_version))
        if comparison != '!=':
            comparison = comparison[::-1]
        ops = {'=': operator.eq,
               '<': operator.lt,
               '<=': operator.le,
               '!=': operator.ne,
               '>': operator.gt,
               '>=': operator.ge}
        if CONF.feature.branch == 'latest':
            web_content = requests.get('http://stridercd.scalr-labs.com/scalarizr/apt-plain/release/%s/' %
                                       CONF.feature.branch).text.splitlines()
        else:
            web_content = requests.get('http://stridercd.scalr-labs.com/scalarizr/apt-plain/develop/%s/' %
                                       CONF.feature.branch).text.splitlines()
        for line in web_content:
            m = re.search('scalarizr_(.+?)-1_', line)
            if m:
                version = m.group(1)
                break
    current = []
    if kwargs.get('platform'):
        current.append(CONF.feature.driver.current_cloud)
    if kwargs.get('storage'):
        current.append(CONF.feature.storage)
    if kwargs.get('dist'):
        current.append(CONF.feature.dist)
    options = []
    pass_list = []
    skip_list = []
    for v in kwargs.values():
        if isinstance(v, tuple):
            for i in v:
                options.append(i)
        else:
            options.append(v)
    for v in options:
        if v.startswith('!'):
            skip_list.append(v.strip('!'))
        else:
            pass_list.append(v)

    def wrapper(func):
        for v in current:
            if (not skip_list and v not in pass_list) or (skip_list and v in skip_list):
                func._exclude = True
                break
        if kwargs.get('szr_version') and not ops[comparison](LooseVersion(version), LooseVersion(check_version)):
            func._exclude = True
        return func
    return wrapper


@world.absorb
def passed_by_version_scalarizr(version, reverse=False):
    """
    Decorator for set maximum/minimum (with reverse) version of scalarizr version
    for this step.
    If we set 0.23 - step will passed if server has version more 0.23
    With reverse=True, step will passed if server has version less 0.23

    :param str version: Scalarizr version for compare
    :param bool reverse: If set reverse to True, version will be minimum for this step
    """
    version = LooseVersion(version)
    LOG.debug('Initialize decorator for passed step by version: %s%s' % ('<' if reverse else '>', version))

    def decorator(func):
        def wrapper(*args, **kwargs):
            LOG.debug('Passed by version work')
            server_szr_version = None
            for arg in args:
                LOG.debug('Lookup argument %s for server' % arg)
                if isinstance(arg, (str, unicode)) and hasattr(world, arg):
                    obj = getattr(world, arg)
                    if isinstance(obj, Server) and obj.status == ServerStatus.RUNNING:
                        server_szr_version = LooseVersion(obj.agent_version)
                        break
            if server_szr_version:
                LOG.debug('Compare version scalarizr %s with %s' % (server_szr_version, version))
                LOG.debug('%s < %s = %s' % (version, server_szr_version, version < server_szr_version))
                if version < server_szr_version and not reverse:
                    LOG.info('Pass step because selected version (%s) < version on scalarizr (%s)'
                             % (version, server_szr_version))
                    return True
                elif version > server_szr_version and reverse:
                    LOG.info('Pass step because selected version (%s) > version on scalarizr (%s) and reverse enable'
                             % (version, server_szr_version))
                    return True
            return func(*args, **kwargs)
        return wrapper
    return decorator


@world.absorb
def check_resolving(domain):
    LOG.debug('Try resolve domain %s' % domain)
    try:
        ip = socket.gethostbyname(domain)
        LOG.info('Domain resolved to %s' % ip)
        return ip
    except socket.gaierror:
        LOG.debug('Domain not resolved')
        return False


@world.absorb
def check_open_port(server, port):
    LOG.debug('Check open port %s:%s' % (server.public_ip, port))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    try:
        s.connect((server.public_ip, int(port)))
        s.shutdown(2)
        return True
    except socket.error:
        return False


@world.absorb
def get_external_local_ip():
    for site in IP_RESOLVER_SITES:
        try:
            LOG.debug('Try get external IP address from site %s' % site)
            my_ip = requests.get(site).text.strip()
            break
        except requests.ConnectionError:
            LOG.warning("Can't get external IP from site: %s, try next" % site)
    else:
        raise requests.ConnectionError("Can't get external IP from all sites in list")
    LOG.info('Current external IP address is %s' % my_ip)
    return my_ip


@world.absorb
def wait_site_response(domain, msg, proto='http', **kwargs):
    try:
        resp = requests.get("%s://%s" % (proto, domain)).text
    except requests.ConnectionError:
        LOG.debug('Site %s://%s unavailable' % (proto, domain))
        return False
    if msg in resp:
        return True
    return False


@world.absorb
def get_szr_messages(node):
    LOG.info('Get messages list from server %s' % node.id)
    out = node.run('szradm list-messages')

    if out[0] in ('', ' '):
        return []
    lines = out[0].splitlines()
    # remove horizontal borders
    lines = filter(lambda x: not x.startswith("+"), lines)
    # split each line

    def split_tline(line):
        return map(lambda x: x.strip("| "), line.split(" | "))

    lines = map(split_tline, lines)
    # get column names
    head = lines.pop(0)

    # [{column_name: value}]
    messages = [dict(zip(head, line)) for line in lines]
    LOG.info('Server messages: %s' % messages)
    return messages


@world.absorb
def assert_exist(first, message='Equal'):
    '''Assert if first exist'''
    assert not first, message


@world.absorb
def assert_not_exist(first, message='Equal'):
    '''Assert if first not exist'''
    assert first, message


@world.absorb
def assert_equal(first, second, message='Equal'):
    '''Assert if first==second'''
    assert not first == second, message

@world.absorb
def assert_not_equal(first, second, message='Not equal'):
    '''Assert if not first==second'''
    assert first == second, message

@world.absorb
def assert_in(first, second, message=''):
    '''Assert if first in second'''
    assert not first in second, message

@world.absorb
def assert_not_in(first, second, message=''):
    '''Assert if not first in second'''
    assert first in second, message
