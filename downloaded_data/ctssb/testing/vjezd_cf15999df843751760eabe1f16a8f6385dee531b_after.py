# encoding: utf-8

# Copyright (c) 2014, Ondrej Balaz. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of the original author nor the names of contributors
#   may be used to endorse or promote products derived from this software
#   without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

""" Ports
    *****

    Ports are device I/O. Each device type has different needs and thus
    requires different ports. Currently application supports 4 different
    classes of ports (with modes which use it):

    * button: for trigger ticket printer button (print)
    * relay: for door opening relay (print, scan)
    * printer: for printing tickets (print)
    * scanner: for scanning tickets (scan)

    Each of these classes can have multiple implementations based on their
    base class. These implementations have to be thread-safe as in 'both' mode
    both printer and scanner might want access them.

    Configuration Options
    ---------------------
"""

import sys
import os
import importlib
import logging
logger = logging.getLogger(__name__)

from vjezd import crit_exit
from vjezd import conffile


# Stores port instances. Each port class can have only one instance.
ports = {}


def init():
    """ Initialize ports.
    """
    global ports

    logger.debug('Initializing ports')
    for port_name in ('button', 'relay', 'printer', 'scanner'):
        ports[port_name] = port_factory(port_name)


def port(port_name):
    """ Return instance of port if exists, otherwise None.
    """
    return ports.get(port_name)


def has_ports(port_names):
    """ Checks if all ports passed as port_names list are available.
    """
    for port_name in port_names:
        if not port(port_name):
            return False
    return True


def open_ports(port_names):
    """ Open specified ports.
    """
    logger.debug('Opening ports: {}'.format(port_names))
    for port_name in port_names:
        p = port(port_name)
        try:
            if p and not p.is_open():
                p.open()
        except Exception as err:
            logger.critical('Cannot open port {}: {}'.format(port_name, err))
            crit_exit(4, err)


def close_ports():
    """ Close all open ports.
    """
    logger.debug('Closing ports')
    for p in ports:
        if ports[p] and ports[p].is_open():
            ports[p].close()


def port_factory(port_name):
    """ Get port instance.

        Port class is imported from vjezd.ports.<port>.<port_class> and
        expected to be assigned to port_class variable.
    """
    logger.info('Trying to create port {}'.format(port_name))

    # Read the port configuration
    conf = conffile.get('ports', port_name, None)
    klass = None
    if conf:
        conf = conf.split(':')
        klass = conf[0]
        args = []
        if len(conf) > 1:
            args = conf[1].split(',')

    if not klass:
        logger.info('Port {} is not configured. Skipping.'.format(port_name))
        return None

    logger.info('Initializing port {} as class:{} with args:{}.'.format(
        port_name, klass, args))

    # Import and instantiate port class
    path = 'vjezd.ports.{}.{}'.format(port_name, klass)
    logger.debug('Importing port module from: {}'.format(path))

    inst = None
    try:
        module = importlib.import_module('{}'.format(path))
        obj = getattr(module, 'port_class')
        inst = obj(*args)
    except (ImportError, AttributeError) as err:
        logger.error('Cannot import port {} module: {}! Skipping'.format(
            port_name, err))
        return None

    # Instance must be of BasePort type
    from vjezd.ports.base import BasePort
    if not isinstance(inst, BasePort):
        logger.error('Port {} class must inherit BasePort! Skipping.'.format(
            port_name))
        return None

    try:
        inst.test()
    except Exception as err:
        logger.error('Port {} test failed: {}!'.format(port_name, err))
        return None

    logger.info('Port {} created'.format(port_name))
    return inst
