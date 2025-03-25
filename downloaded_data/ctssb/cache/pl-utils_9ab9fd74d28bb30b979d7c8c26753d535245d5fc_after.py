#!/usr/bin/env python
# -*- mode: python; coding: utf-8; fill-column: 80; -*-
#
# renew-slice.py
# Created by Balakrishnan Chandrasekaran on 2016-05-20 18:05 -0400.
# Copyright (c) 2016 Balakrishnan Chandrasekaran <balac@cs.duke.edu>.
#

"""
renew-slice.py
Renew a PlanetLab slice.

$ ./renew-slice.py -h
usage: renew-slice.py [-h] [--version] -u usr -s slice-name

Renew a PlanetLab slice as far into the future as permitted.

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -u usr, --usr usr     User ID.
  -s slice-name, --slice slice-name
                        Name of an existing PlanetLab slice.
"""

__author__  = 'Balakrishnan Chandrasekaran <balac@cs.duke.edu>'
__version__ = '1.0'
__license__ = 'MIT'


import argparse
from datetime import datetime as dt
import plc
import sys


def main(args):
    try:
        api = plc.PLC(args.usr, plc.get_pwd(args.usr))
        s = api.get_slice(args.slice_name)

        print(u"- slice '%s(%d)' expires on %s" %
              (s.name, s.slice_id, dt.strftime(s.expires, "%b %d, %Y %T")))

        if not s.can_renew:
            print(u"- slice cannot be renewed at this time!")
            return

        s = api.renew_slice(s.slice_id)
        print(u"- slice '%s(%d)' expires on %s" %
              (s.name, s.slice_id, dt.strftime(s.expires, "%b %d, %Y %T")))
    except Exception as e:
        sys.stderr.write(u"Error> %s\n" % (e.message))


def __get_parser():
    """Configure a parser to parse command-line arguments.
    """
    desc = ("Renew a PlanetLab slice as far into the future as permitted.")
    parser = argparse.ArgumentParser(description = desc)
    parser.add_argument('--version',
                        action = 'version',
                        version = '%(prog)s ' + "%s" % (__version__))
    parser.add_argument('-u', '--usr',
                        dest = 'usr',
                        metavar = 'usr',
                        required = True,
                        help = 'User ID.')
    parser.add_argument('-s', '--slice',
                        dest = 'slice_name',
                        required = True,
                        metavar = 'slice-name',
                        help = 'Name of an existing PlanetLab slice.')
    return parser


if __name__ == '__main__':
    args = __get_parser().parse_args()
    main(args)
