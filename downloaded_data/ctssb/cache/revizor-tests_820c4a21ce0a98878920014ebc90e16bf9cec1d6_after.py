__author__ = 'gigimon'

import re
import logging
import time
import requests

from lettuce import world, step

from revizor2.utils import wait_until
from revizor2.fixtures import resources


LOG = logging.getLogger(__name__)

GLOBAL_TEMPLATE = 'global \n    log 127.0.0.1   local0 \n    log 127.0.0.1   local1 notice \n    maxconn     256000\n'
PROXY_TEMPLATE = '    stats enable \n    option forwardfor \n    stats uri'

def parse_haproxy_config(node):
    config = [l for l in node.run('cat /etc/haproxy/haproxy.cfg')[0].splitlines() if l.strip()]
    parameters = {'listens': {},
                  'backends': {}}

    tmp_section = None
    tmp_opts = []
    for line in config:
        if (line.strip().startswith('listen') or line.strip().startswith('backend')) and 'scalr' in line:
            if tmp_section:
                parameters[tmp_section.split()[0]+'s'][int(tmp_section.split()[1].split(':')[-1])] = tmp_opts
                tmp_section = None
                tmp_opts = []
            tmp_section = line.strip()
        elif tmp_section and (line.startswith('\t') or line.startswith('    ')):
            tmp_opts.append(line.strip().replace('\t', ' '))
        else:
            if tmp_section:
                parameters[tmp_section.split()[0]+'s'][int(tmp_section.split()[1].split(':')[-1])] = tmp_opts
                tmp_section = None
                tmp_opts = []
    else:
        if tmp_section:
            parameters[tmp_section.split()[0]+'s'][int(tmp_section.split()[1].split(':')[-1])] = tmp_opts
    return parameters

def check_config_for_option(node, section, port):
    config = parse_haproxy_config(node)
    try:
        section = config[section][port]
    except KeyError:
        pass
    if section:
        return config

@step(r"I add proxy ([\w\d]+) to ([\w\d]+) role for ([\d]+) port with ([\w\d]+) role backend([\w ]+)?")
def add_proxy_to_role(step, proxy_name, proxy_role, port, backend_role, options):
    LOG.info("Add haproxy proxy %s with role backend" % proxy_name)
    proxy_template = None
    proxy_role = world.get_role(proxy_role)
    backend_role = world.get_role(backend_role)
    backends = [{
        'farm_role_id': backend_role.id,
        'port': str(port),
        'backup': '0',
        'down': '0'
    }]
    if options:
        if ('public' or 'private') in options:
            backends[0].update({'network': options.strip().split()[1]})
        if 'proxy template' in options:
            proxy_template = PROXY_TEMPLATE
    proxy_role.add_haproxy_proxy(port, backends, description=proxy_name, proxy_template=proxy_template)
    LOG.info("Save proxy %s with backends: %s" % (proxy_name, backends))
    setattr(world, '%s_proxy' % proxy_name, {"port": port, "backends": backends, "proxy_template": proxy_template})


@step(r"I add proxy ([\w\d]+) to ([\w\d]+) role for ([\d]+) port with backends: ([\w\d\' ,:\.]+) and healthcheck: ([\w\d, ]+)")
def add_proxy_with_healtcheck(step, proxy_name, proxy_role, port, options, healthchecks):
    LOG.info("Add proxy %s with many backends (%s) and healthcheck (%s)" % (proxy_name, options, healthchecks))
    proxy_role = world.get_role(proxy_role)
    options = options.strip().replace('\'', '').split()
    options = zip(*[options[i::2] for i in range(2)])
    healthchecks = [int(x.strip()) for x in healthchecks.replace(',', '').split()]
    LOG.info("Healthchecks for proxy: %s" % healthchecks)
    backends = []
    for o in options:
        if ':' in o[0]:
            host, backend_port = o[0].split(':')
        else:
            host = o[0]
            backend_port = port
        serv = getattr(world, host, None)
        backends.append({
            'host': serv.private_ip if serv else str(o[0]),
            'port': str(backend_port),
            'backup': "1" if o[1] == 'backup' else "0",
            'down': "1" if o[1] in ['down', 'disabled'] else "0",
        })
    LOG.info("Save proxy %s with backends: %s" % (proxy_name, backends))
    proxy_role.add_haproxy_proxy(port, backends, description=proxy_name, interval=healthchecks[0],
                                  fall=healthchecks[1], rise=healthchecks[2])
    setattr(world, '%s_proxy' % proxy_name, {"port": port, "backends": backends})


@step(r"I modify proxy ([\w\d]+) in ([\w\d]+) role with backends: ([\w\d\' ,\.]+) and healthcheck: ([\w\d, ]+)")
def modify_haproxy_role(step, proxy_name, proxy_role, options, healthchecks):
    LOG.info("Modify proxy %s" % proxy_name)
    proxy_role = world.get_role(proxy_role)
    proxy = getattr(world, '%s_proxy' % proxy_name)
    options = options.strip().replace('\'', '').split()
    options = zip(*[options[i::2] for i in range(2)])
    healthchecks = [int(x.strip()) for x in healthchecks.replace(',', '').split()]
    LOG.info("Healthchecks for proxy: %s" % healthchecks)
    backends = []
    for o in options:
        serv = getattr(world, o[0], None)
        backends.append({
            "host": serv.private_ip if serv else o[0],
            "port": "80",
            "backup": "1" if o[1] == 'backup' else "0",
            "down": "1" if o[1] in ['down', 'disabled'] else "0",
        })
    LOG.info("Save proxy changes with backends: %s" % backends)
    proxy_role.edit_haproxy_proxy(proxy['port'], backends, interval=healthchecks[0],
                                  fall=healthchecks[1], rise=healthchecks[2])


@step(r'([\w\d]+) backend list for (\d+) port should( not)? contains ([\w\d, :\'\.]+)')
def verify_backends_for_port(step, serv_as, port, has_not, backends_servers):
    time.sleep(10)
    LOG.info("Verify backends servers in config")
    haproxy_server = getattr(world, serv_as)
    port = int(port)
    LOG.info("Backend port: %s" % port)
    backends = []
    for back in backends_servers.split(','):
        if back.strip().startswith("'"):
            new_back = back.strip().replace("'", '').split()
            if ':' in new_back[0]:
                host, backend_port = new_back[0].split(':')
            else:
                host = new_back[0]
                backend_port = port
            hostname = getattr(world, host, host)
            if not isinstance(hostname, (unicode, str)):
                hostname = hostname.private_ip
            if new_back[1] == 'default':
                backends.append(re.compile('%s:%s' % (hostname, backend_port)))
            else:
                backends.append(re.compile('%s:%s(?: check)? %s' % (hostname, backend_port, new_back[1])))
        elif ':' in back.strip():
            serv, network = back.strip().split(':')
            hostname = getattr(world, serv, serv)
            if not isinstance(hostname, (unicode, str)):
                if network == 'public':
                    hostname = hostname.public_ip
                elif network == 'private':
                    hostname = hostname.private_ip
            backends.append(re.compile('%s:%s' % (hostname, port)))
        else:
            hostname = getattr(world, back.strip(), back.strip())
            if not isinstance(hostname, (unicode, str)):
                hostname = hostname.private_ip
            backends.append(re.compile('%s:%s' % (hostname, port)))
    LOG.info("Will search backends: %s" % backends)
    node = world.cloud.get_node(haproxy_server)
    config = wait_until(check_config_for_option,
                        args=[node, 'backends', port],
                        timeout=180,
                        error_text='No backends section in HAProxy config')

    for backend in backends:
        for server in config['backends'][port]:
            if not server.startswith('server'):
                continue
            if has_not and backend.search(server):
                raise AssertionError("Backend '%s' in backends file (%s) for port '%s'" % (backend, server, port))
            elif not has_not:
                if backend.search(server):
                    break
        else:
            if not has_not:
                raise AssertionError("Backend '%s' not found in backends (%s) file for port '%s'" % (backend.pattern, config['backends'][port], port))


@step(r'([\w\d]+) listen list should contains ([\w\d\s]+) for (\d+) port')
def verify_listen_for_port(step, serv_as, option, port):
    LOG.info("Verify backends servers in config")
    haproxy_server = getattr(world, serv_as)
    port = int(port)
    LOG.info("Backend port: %s" % port)
    node = world.cloud.get_node(haproxy_server)
    config = wait_until(check_config_for_option,
                        args=[node, 'listens', port],
                        timeout=300,
                        error_text='No listens section in HAProxy config')
    LOG.debug("HAProxy config : %s" % config)
    if option == 'backend':
        for opt in config['listens'][port]:
            if re.match('default_backend scalr(?:\:\d+)?:backend(?:\:\w+)?:%s' % port, opt):
                LOG.info('Haproxy server "%s" has default_backend for "%s" port: "%s"' % (haproxy_server.id, port, opt))
                break
        else:
            raise AssertionError(
                "Listens sections not contain backend for '%s' port: %s" % (port, config['listens'][port]))
    else:
        proxy = getattr(world, '%s_proxy' % option.split()[0])
        proxy_template = [i.strip()
                          for i in proxy["proxy_template"].strip().split('\n')]
        if [i for i in config['listens'][port] if i in proxy_template] == proxy_template:
            LOG.info('Haproxy server "%s" has correct proxy  template for "%s" port: "%s"' % (
                haproxy_server.id, port, proxy_template))
        else:
            raise AssertionError("Listens sections not contain '%s' for '%s' port: %s" % (option, port, config['listens'][port]))


@step(r'healthcheck parameters is (\d+), (\d+), (\d+) in ([\w\d]+) backend file for (\d+) port')
def verify_healtcheck_parameters(step, interval, fall, rise, serv_as, port):
    server = getattr(world, serv_as)
    LOG.info("Verify healthcheck parameters for %s %s" % (server.id, port))
    port = int(port)
    healthcheck = {'inter': interval.strip(), 'fall': fall.strip(), 'rise': rise.strip()}
    LOG.info("Parameters must be: %s" % healthcheck)
    node = world.cloud.get_node(server)
    config = parse_haproxy_config(node)
    LOG.debug("HAProxy config: %s" % config)
    config_healthcheck = [l for l in config['backends'][port] if l.startswith('default-server')]
    LOG.debug("Healthcheck in config: %s" % config_healthcheck)
    if config_healthcheck:
        config_healthcheck = dict(re.findall('(fall|inter|rise) (\d+)', config_healthcheck[0]))
        if not healthcheck == config_healthcheck:
            raise AssertionError("Healtcheck parameters invalid, must be: %s but %s" % (healthcheck, config_healthcheck))
        return True
    raise AssertionError("Healthcheck parameters not found in backends for port: %s" % port)


@step(r'([\w\d]+) backend list should be clean')
def verify_backend_list_clean(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    config = parse_haproxy_config(node)
    if config['backends'] or config['listens']:
        raise AssertionError("HAProxy config contains backends/listeners section: %s" % config)


@step(r'I delete proxy ([\w\d]+) in ([\w\d]+) role')
def delete_haproxy_proxy(step, proxy_name, proxy_role):
    LOG.info("Delete haproxy proxy %s" % proxy_name)
    proxy_role = world.get_role(proxy_role)
    proxy = getattr(world, '%s_proxy' % proxy_name)
    LOG.info("Delete haproxy proxy for port %s" % proxy['port'])
    proxy_role.delete_haproxy_proxy(proxy['port'])


@step(r'([\w\d]+) config should not contains ([\w\d]+)')
def verify_proxy_in_config(step, serv_as, proxy_name):
    proxy = getattr(world, '%s_proxy' % proxy_name)
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    config = parse_haproxy_config(node)
    if proxy['port'] in config['backends'] or proxy['port'] in config['listens']:
        raise AssertionError("HAProxy config contains parameters for %s proxy (port %s): %s" % (proxy_name,
                                                                                                proxy['port'], config))


@step(r'I add global config to ([\w\d]+) role')
def add_global_config(step, proxy_role):
    proxy_role = world.get_role(proxy_role)
    proxy_role.add_haproxy_global_config(GLOBAL_TEMPLATE)


@step(r'([\w\d]+) config should contain global section')
def check_global_in_config(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    c = node.run('cat /etc/haproxy/haproxy.cfg')[0].strip()
    section_start = c.find('##### main template start #####') + len('##### main template start #####')
    section_end = c.find('##### main template end #####')
    config = [i.strip() for i in c[section_start:section_end].replace('   ',' ').split('\n')]
    global_template = [i.strip() for i in GLOBAL_TEMPLATE.replace('   ',' ').split('\n')]
    options_in_config = [i for i in global_template if i in config]
    if options_in_config == global_template:
        LOG.info('Haproxy server "%s" contains global config: %s' % (serv_as, global_template))
    else:
        raise AssertionError("%s server does not contain global config: %s" % (serv_as, global_template))
