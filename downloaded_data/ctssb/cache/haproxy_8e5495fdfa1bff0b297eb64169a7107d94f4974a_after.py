#!/usr/bin/env python
import logging
import os
import time
import string
import subprocess
import sys
import re
import socket
from collections import OrderedDict

import requests


logger = logging.getLogger(__name__)

# Config ENV
PORT = os.getenv("PORT", "80")
MODE = os.getenv("MODE", "http")
BALANCE = os.getenv("BALANCE", "roundrobin")
MAXCONN = os.getenv("MAXCONN", "4096")
SSL = os.getenv("SSL", "")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")
OPTION = os.getenv("OPTION", "redispatch, httplog, dontlognull, forwardfor").split(",")
TIMEOUT = os.getenv("TIMEOUT", "connect 5000, client 50000, server 50000").split(",")
VIRTUAL_HOST = os.getenv("VIRTUAL_HOST", None)
TUTUM_CONTAINER_API_URL = os.getenv("TUTUM_CONTAINER_API_URL", None)

TUTUM_AUTH = os.getenv("TUTUM_AUTH")
DEBUG = os.getenv("DEBUG", False)

# Const var
CONFIG_FILE = '/etc/haproxy/haproxy.cfg'
HAPROXY_CMD = ['/usr/sbin/haproxy', '-f', CONFIG_FILE, '-db']
POLLING_PERIOD = 30
LINK_ENV_PATTERN = "_PORT_%s_TCP" % PORT
LINK_ADDR_SUFFIX = LINK_ENV_PATTERN + "_ADDR"
LINK_PORT_SUFFIX = LINK_ENV_PATTERN + "_PORT"
TUTUM_URL_SUFFIX = "_TUTUM_API_URL"
VIRTUAL_HOST_SUFFIX = "_ENV_VIRTUAL_HOST"

# Global Var
HAPROXY_CURRENT_SUBPROCESS = None

endpoint_match = re.compile(r"(?P<proto>tcp|udp):\/\/(?P<addr>[^:]*):(?P<port>.*)")


def get_cfg_text(cfg):
    text = ""
    for section, contents in cfg.items():
        text += "%s\n" % section
        for content in contents:
            text += "  %s\n" % content
    return text.strip()


def create_default_cfg(maxconn, mode):
    cfg = OrderedDict({
        "global": ["log 127.0.0.1 local0",
                   "log 127.0.0.1 local1 notice",
                   "maxconn %s" % maxconn,
                   "pidfile /var/run/haproxy.pid",
                   "user haproxy",
                   "group haproxy",
                   "daemon"],
        "defaults": ["log     global",
                     "mode %s" % mode]})
    for option in OPTION:
        if option:
            cfg["defaults"].append("option %s" % option.strip())
    for timeout in TIMEOUT:
        if timeout:
            cfg["defaults"].append("timeout %s" % timeout.strip())

    return cfg


def get_backend_routes(dict_var):
    # Return sth like: {'HELLO_WORLD_1': {'addr': '172.17.0.103', 'port': '80'},
    # 'HELLO_WORLD_2': {'addr': '172.17.0.95', 'port': '80'}}
    addr_port_dict = {}
    for name, value in dict_var.iteritems():
        position = string.find(name, LINK_ENV_PATTERN)
        if position != -1:
            container_name = name[:position]
            add_port = addr_port_dict.get(container_name, {'addr': "", 'port': ""})
            add_port['addr'] = socket.gethostbyname(container_name.lower().replace("_", "-"))
            if name.endswith(LINK_PORT_SUFFIX):
                add_port['port'] = value
            addr_port_dict[container_name] = add_port

    return addr_port_dict


def update_cfg(cfg, backend_routes, vhost):
    logger.debug("Updating cfg: \n old cfg: %s\n backend_routes: %s\n vhost: %s", cfg, backend_routes, vhost)
    # Set frontend
    frontend = []
    frontend.append("bind 0.0.0.0:80")
    if SSL:
        frontend.append("redirect scheme https code 301 if !{ ssl_fc }"),
        frontend.append("bind 0.0.0.0:443 %s" % SSL)
        frontend.append("reqadd X-Forwarded-Proto:\ https")
    if vhost:
        for service_name, domain_name in vhost.iteritems():
            service_name = service_name.upper()
            frontend.append("acl host_%s hdr(host) -i %s" % (service_name, domain_name))
            frontend.append("use_backend %s_cluster if host_%s" % (service_name, service_name))
    else:
        frontend.append("default_backend default_service")
    cfg["frontend default_frontend"] = frontend

    # Set backend
    if vhost:
        for service_name, domain_name in vhost.iteritems():
            service_name = service_name.upper()
            backend = []
            if SESSION_COOKIE:
                backend.append("appsession %s len 64 timeout 3h request-learn prefix" % (SESSION_COOKIE, ))

            backend.append("balance %s" % BALANCE)
            for container_name, addr_port in backend_routes.iteritems():
                if container_name.startswith(service_name):
                    server_string = "server %s %s:%s" % (container_name, addr_port["addr"], addr_port["port"])
                    if SESSION_COOKIE:
                        server_string += " cookie check"

                    # Do not add duplicate backend routes
                    duplicated = False
                    for server_str in backend:
                        if "%s:%s" % (addr_port["addr"], addr_port["port"]) in server_str:
                            duplicated = True
                            break
                    if not duplicated:
                        backend.append(server_string)
            if backend:
                cfg["backend %s_cluster" % service_name] = sorted(backend)

    else:
        backend = []
        if SESSION_COOKIE:
            backend.append("appsession %s len 64 timeout 3h request-learn prefix" % (SESSION_COOKIE, ))

        backend.append("balance %s" % BALANCE)
        for container_name, addr_port in backend_routes.iteritems():
            server_string = "server %s %s:%s" % (container_name, addr_port["addr"], addr_port["port"])
            if SESSION_COOKIE:
                server_string += " cookie check"

            # Do not add duplicate backend routes
            duplicated = False
            for server_str in backend:
                if "%s:%s" % (addr_port["addr"], addr_port["port"]) in server_str:
                    duplicated = True
                    break
            if not duplicated:
                backend.append(server_string)

        cfg["backend default_service"] = sorted(backend)

    logger.debug("New cfg: %s", cfg)


def save_config_file(cfg_text, config_file):
    try:
        directory = os.path.dirname(config_file)
        if not os.path.exists(directory):
            os.makedirs(directory)
        f = open(config_file, 'w')
    except Exception as e:
        logger.error(e)
    else:
        f.write(cfg_text)
        logger.info("Config file is updated")
        f.close()


def reload_haproxy():
    global HAPROXY_CURRENT_SUBPROCESS
    if HAPROXY_CURRENT_SUBPROCESS:
        # Reload haproxy
        logger.info("Reloading haproxy")
        process = subprocess.Popen(HAPROXY_CMD + ["-sf", str(HAPROXY_CURRENT_SUBPROCESS.pid)])
        HAPROXY_CURRENT_SUBPROCESS.wait()
        HAPROXY_CURRENT_SUBPROCESS = process
    else:
        # Launch haproxy
        logger.info("Lauching haproxy")
        HAPROXY_CURRENT_SUBPROCESS = subprocess.Popen(HAPROXY_CMD)


def update_virtualhost(vhost):
    if VIRTUAL_HOST:
        for host in VIRTUAL_HOST.split(","):
            tmp = host.split("=", 2)
            if len(tmp) == 2:
                vhost[tmp[0].strip()] = tmp[1].strip()

    for name, value in os.environ.iteritems():
        position = string.find(name, VIRTUAL_HOST_SUFFIX)
        if position != -1:
            hostname = name[:position]
            vhost[hostname] = value


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout)
    logging.getLogger(__name__).setLevel(logging.DEBUG if DEBUG else logging.INFO)

    cfg = create_default_cfg(MAXCONN, MODE)
    vhost = {}

    # Tell the user the mode of autoupdate we are using, if any
    if TUTUM_CONTAINER_API_URL:
        if TUTUM_AUTH:
            logger.info("HAproxy has access to Tutum API - will reload list of backends every %d seconds",
                        POLLING_PERIOD)
        else:
            logger.warning(
                "HAproxy doesn't have access to Tutum API and it's running in Tutum - you might want to give "
                "an API role to this service for automatic backend reconfiguration")
    else:
        logger.info("HAproxy is not running in Tutum")
    session = requests.Session()
    headers = {"Authorization": TUTUM_AUTH}

    # Main loop
    old_text = ""
    while True:
        try:
            if TUTUM_CONTAINER_API_URL and TUTUM_AUTH:
                # Running on Tutum with API access - fetch updated list of environment variables
                r = session.get(TUTUM_CONTAINER_API_URL, headers=headers)
                r.raise_for_status()
                container_details = r.json()

                backend_routes = {}
                for link in container_details.get("linked_to_container", []):
                    for port, endpoint in link.get("endpoints", {}).iteritems():
                        if port == "%s/tcp" % PORT:
                            backend_routes[link["name"]] = endpoint_match.match(endpoint).groupdict()
            else:
                # No Tutum API access - configuring backends based on static environment variables
                backend_routes = get_backend_routes(os.environ)

            # Update backend routes
            update_virtualhost(vhost)
            update_cfg(cfg, backend_routes, vhost)
            cfg_text = get_cfg_text(cfg)

            # If cfg changes, write to file
            if old_text != cfg_text:
                logger.info("HAProxy configuration has been changed:\n%s" % cfg_text)
                save_config_file(cfg_text, CONFIG_FILE)
                reload_haproxy()
                old_text = cfg_text
        except Exception as e:
            logger.exception("Error: %s" % e)

        time.sleep(POLLING_PERIOD)
