# Copyright (C) 2015 SINTEF ICT,
# Applied Mathematics, Norway.
#
# Contact information:
# E-mail: eivind.fonn@sintef.no
# SINTEF ICT, Department of Applied Mathematics,
# P.O. Box 4760 Sluppen,
# 7045 Trondheim, Norway.
#
# This file is part of BADGER.
#
# BADGER is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# BADGER is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with GoTools. If not, see
# <http://www.gnu.org/licenses/>.
#
# In accordance with Section 7(b) of the GNU Affero General Public
# License, a covered work must retain the producer line in every data
# file that is created or manipulated using GoTools.
#
# Other Usage
# You can be released from the requirements of the license by purchasing
# a commercial license. Buying such a license is mandatory as soon as you
# develop commercial activities involving BADGER without disclosing the
# source code of your own applications.
#
# This file may be used in accordance with the terms contained in a
# written agreement between you and SINTEF ICT.

import argparse
import shlex
import sys
import yaml

from collections import OrderedDict
from jinja2 import Template

import badger.output as output
import badger.log as log


def coerce_list(dictionary, key, split=None, required=False):
    if not required:
        if key not in dictionary:
            dictionary[key] = []
    if isinstance(dictionary[key], str):
        if isinstance(split, str):
            dictionary[key] = dictionary[key].split(split)
        elif split:
            dictionary[key] = split(dictionary[key])
        else:
            dictionary[key] = [dictionary[key]]


def parse_args(input=None):
    parser = argparse.ArgumentParser(description='Batch job runner.')
    parser.add_argument('-o', '--output', required=False, default='output.yaml',
                        help='The output file')
    parser.add_argument('-f', '--format', required=False, default=None,
                        choices=output.FORMATS, help='The output format')
    parser.add_argument('-d', '--dry', required=False, default=False,
                        action='store_true', help='Dry run')
    parser.add_argument('-v', '--verbosity', required=False, default=1, type=int,
                        choices=range(0, 5), help='Verbosity level for stdout')
    parser.add_argument('-l', '--logverbosity', required=False, default=3, type=int,
                        choices=range(0, 5), help='Verbosity level for log file')
    parser.add_argument('file', help='Configuration file for the batch job')
    args = parser.parse_args(input)

    if args.format is None:
        try:
            args.format = args.output.split('.')[-1]
            assert args.format in output.FORMATS
        except (AssertionError, IndexError):
            print('Unable to determine output format from filename "{}"'.format(args.output),
                  file=sys.stderr)
            sys.exit(1)

    log.stdout_verbosity = args.verbosity
    log.log_verbosity = args.logverbosity
    log.log_file = args.file + '.log'
    if args.logverbosity > 1:
        with open(log.log_file, 'w') as f: pass

    return args


# YAML is unordered by default, this is an ordered loader
# Thanks http://stackoverflow.com/a/21912744/2729168
def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))

    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)


def treat_setup(setup):
    coerce_list(setup, 'templates')
    coerce_list(setup, 'files')
    coerce_list(setup, 'cmdargs', split=shlex.split)
    coerce_list(setup, 'executable', split=shlex.split, required=True)
    coerce_list(setup, 'parse')
    for key in ['dependencies', 'types', 'parameters']:
        if key not in setup:
            setup[key] = {}

    kwargs = {'variable_start_string': '$',
              'variable_end_string': '$'}
    for k in ['templates', 'files', 'executable', 'cmdargs']:
        setup[k] = [Template(v, **kwargs) for v in setup[k]]

    for key in setup['dependencies']:
        setup['dependencies'][key] = str(setup['dependencies'][key])


def load_setup(fn):
    with open(fn, 'r') as f:
        setup = ordered_load(f, yaml.SafeLoader)
    setup = setup or {}

    treat_setup(setup)

    return setup


def empty_setup(executable='', **kwargs):
    setup = {
        'templates': [],
        'files': [],
        'executable': executable,
        'cmdargs': [],
        'parameters': OrderedDict(),
        'dependencies': OrderedDict(),
        'parse': [],
        'types': OrderedDict(),
        }

    setup.update(kwargs)
    treat_setup(setup)
    return setup
