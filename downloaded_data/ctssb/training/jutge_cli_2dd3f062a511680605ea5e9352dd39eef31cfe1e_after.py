#!/usr/bin/python3

# Copyright (C) 2017  Aleix Boné (abone9999 at gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Jutge_cli command line

This module performs the actions needed to parse the console arguments and call
the needed submodule
"""

import sys
import logging
from os.path import expanduser

import argparse

from .commands import add_test, archive, check_submissions, cookie,\
                      defaults, download, get_code, import_zip, login,\
                      new, show, test, upload

JUTGE_CLI_VERSION = '2.1.9'

CONFIG = defaults.config()
DEFAULT_PARAM = CONFIG['param']

BANNER = r'''
       ██╗██╗   ██╗████████╗ ██████╗ ███████╗   ______     ___
       ██║██║   ██║╚══██╔══╝██╔════╝ ██╔════╝  / ___| |   |_ _|
       ██║██║   ██║   ██║   ██║  ███╗█████╗   | |   | |    | |
  ██   ██║██║   ██║   ██║   ██║   ██║██╔══╝   | |___| |___ | |
  ╚█████╔╝╚██████╔╝   ██║   ╚██████╔╝███████╗  \____|_____|___|
   ╚════╝  ╚═════╝    ╚═╝    ╚═════╝ ╚══════╝  v{} by Leix_b

'''.format(JUTGE_CLI_VERSION)

PARSER = argparse.ArgumentParser(
    description=BANNER,
    formatter_class=argparse.RawDescriptionHelpFormatter)

PARENT_PARSER = argparse.ArgumentParser(add_help=False)

PARENT_PARSER.add_argument(
    '-d', '--database', type=str,
    default=DEFAULT_PARAM['database'],
    help='directory containing the test samples')
PARENT_PARSER.add_argument(
    '-r', '--regex', type=str,
    help='regular expression used to find the code from filename',
    default=DEFAULT_PARAM['regex'])
PARENT_PARSER.add_argument(
    '--no-download', action='store_true', default=False,
    help='do not attempt to fetch data from jutge.org')
PARENT_PARSER.add_argument(
    '--cookie', type=str,
    metavar='PHPSESSID',
    help='cookie used to fetch data from jutge.org \
(this is needed for private problems which code begins with an X)')

PARENT_PARSER_VERBOSITY = PARENT_PARSER.add_mutually_exclusive_group()
PARENT_PARSER_VERBOSITY.add_argument('-q', '--quiet', action='store_true')
PARENT_PARSER_VERBOSITY.add_argument(
    '-v', '--verbosity', action='count',
    default=0)

SUBPARSERS = PARSER.add_subparsers(title='subcommands', dest='subcmd')
SUBPARSERS.required = True

PARSER_ADD_TEST = SUBPARSERS.add_parser(
    'add-test', aliases=['add'],
    help='add custom test case to database',
    parents=[PARENT_PARSER])
PARSER_ADD_TEST.set_defaults(subcommand=add_test.add_test)
PARSER_ADD_TEST.add_argument(
    'prog', type=str, metavar='code',
    help='string containing the problem code')
PARSER_ADD_TEST.add_argument(
    '-i', '--input-file', type=argparse.FileType('r'),
    metavar='test1.inp',
    help='test case input file',
    default=sys.stdin)
PARSER_ADD_TEST.add_argument(
    '-o', '--output-file', type=argparse.FileType('r'),
    metavar='test1.cor',
    help='test case expected output file',
    default=sys.stdin)
PARSER_ADD_TEST.add_argument(
    '--inp-suffix', type=str,
    default=DEFAULT_PARAM['inp-suffix'],
    help='suffix of test input files')
PARSER_ADD_TEST.add_argument(
    '--cor-suffix', type=str,
    default=DEFAULT_PARAM['cor-suffix'],
    help='suffix of test correct output files')
PARSER_ADD_TEST.add_argument(
    '--delete', action='store_true', default=False,
    help='delete all custom tests for problem')

PARSER_ARCHIVE = SUBPARSERS.add_parser(
    'archive',
    help='move program to archived folder',
    parents=[PARENT_PARSER])
PARSER_ARCHIVE.set_defaults(subcommand=archive.archive)
PARSER_ARCHIVE.add_argument(
    'prog', type=argparse.FileType('r+'),
    metavar='prog.cpp',
    help='file to move')
PARSER_ARCHIVE.add_argument(
    '-f', '--folder', type=str,
    default=DEFAULT_PARAM['folder'],
    help='folder where program will be archived')
PARSER_ARCHIVE.add_argument(
    '--overwrite', action='store_true', default=False,
    help='overwrite program if already in archive')
PARSER_ARCHIVE.add_argument(
    '--copy', action='store_true', default=False,
    help='copy file instead of moving to the archive')

PARSER_CHECK = SUBPARSERS.add_parser(
    'check',
    help='check last sent submissions',
    parents=[PARENT_PARSER])
PARSER_CHECK.set_defaults(subcommand=check_submissions.check_submissions)
PARSER_CHECK_MODE = \
    PARSER_CHECK.add_mutually_exclusive_group()
PARSER_CHECK_MODE.add_argument(
    '--last', action='store_true',
    default=False,
    help='only show last submission')
PARSER_CHECK_MODE.add_argument(
    '--reverse', action='store_true',
    help='show last submission on top',
    default=False)
PARSER_CHECK.add_argument(
    '-c', '--code', metavar='code',
    type=str,
    help='string that contains problem code')

PARSER_COOKIE = SUBPARSERS.add_parser(
    'cookie',
    help='save cookie to temporary file for later use to delete cookie \
issue the command: jutge cookie delete',
    parents=[PARENT_PARSER])
PARSER_COOKIE.set_defaults(subcommand=cookie.Cookie)
PARSER_COOKIE.add_argument(
    'cookie',
    metavar='PHPSESSID',
    help='cookie to save (special values: delete -> deletes saved cookie; \
print -> print current saved cookie)')
PARSER_COOKIE.add_argument(
    '--skip-check', action='store_true', default=False,
    help='Save cookie file even if not valid')

PARSER_DOWNLOAD = SUBPARSERS.add_parser(
    'download', aliases=['down'],
    help='download problem files to local database',
    parents=[PARENT_PARSER])
PARSER_DOWNLOAD.set_defaults(subcommand=download.download)
PARSER_DOWNLOAD.add_argument(
    'prog', metavar='code',
    type=str,
    help='string containing problem code')
PARSER_DOWNLOAD.add_argument(
    '--overwrite', action='store_true', default=False,
    help='overwrite existing files in database')

PARSER_LOGIN = SUBPARSERS.add_parser(
    'login', parents=[PARENT_PARSER],
    help='login to jutge.org and save cookie')
PARSER_LOGIN.set_defaults(subcommand=login.login)
PARSER_LOGIN.add_argument(
    '--email', default=DEFAULT_PARAM['email'],
    help='jutge.org email')
PARSER_LOGIN.add_argument(
    '--password', default=DEFAULT_PARAM['password'],
    help='jutge.org password')
PARSER_LOGIN.add_argument(
    '--prompt', action='store_true', default=False,
    help='jutge.org password')

PARSER_NEW = SUBPARSERS.add_parser(
    'new', help='create new file',
    parents=[PARENT_PARSER])
PARSER_NEW.set_defaults(subcommand=new.new)
PARSER_NEW.add_argument(
    'code', type=str,
    help='problem code')
PARSER_NEW.add_argument(
    '-e', '--extension', type=str, default='cpp',
    help='file extension')
PARSER_NEW.add_argument(
    '--overwrite', action='store_true', default=False,
    help='overwrite existing files')
PARSER_NEW.add_argument(
    '--problem-set', action='store_true', default=False,
    help='Create all files in problem set')

PARSER_SHOW = SUBPARSERS.add_parser(
    'show',
    help='show title, statement or test cases corresponding to problem \
            code',
    parents=[PARENT_PARSER])
PARSER_SHOW.set_defaults(subcommand=show.show)
PARSER_SHOW.add_argument(
    'mode',
    type=str,
    choices=['title', 'stat', 'cases'])
PARSER_SHOW.add_argument(
    'prog', metavar='code',
    type=str,
    help='string containing problem code')
PARSER_SHOW.add_argument(
    '--inp-suffix',
    type=str,
    help='suffix of test input files',
    default=DEFAULT_PARAM['inp-suffix'])
PARSER_SHOW.add_argument(
    '--cor-suffix', type=str,
    default=DEFAULT_PARAM['cor-suffix'],
    help='suffix of test correct output files')
PARSER_SHOW.add_argument(
    '--html', action='store_true', default=False,
    help='Use html instead of pypandoc to print problem statement (faster)')

PARSER_TEST = SUBPARSERS.add_parser(
    'test',
    help='test program using cases from database',
    parents=[PARENT_PARSER])
PARSER_TEST.set_defaults(subcommand=test.test)
PARSER_TEST.add_argument(
    'prog', type=argparse.FileType('r'),
    metavar='prog.cpp',
    help='Program to test')
PARSER_TEST.add_argument(
    '-c', '--code', type=str,
    help='code to use instead of searching in the filename')
PARSER_TEST.add_argument(
    '--diff-prog', type=str, default=DEFAULT_PARAM['diff-prog'],
    help='diff shell command to compare tests')
PARSER_TEST.add_argument(
    '--diff-flags', type=str,
    default=DEFAULT_PARAM['diff-flags'],
    help='diff shell command flags used to compare tests \
            (comma separated)')
PARSER_TEST.add_argument(
    '--inp-suffix', type=str,
    default=DEFAULT_PARAM['inp-suffix'],
    help='suffix of test input files')
PARSER_TEST.add_argument(
    '--cor-suffix', type=str,
    default=DEFAULT_PARAM['cor-suffix'],
    help='suffix of test correct output files')
PARSER_TEST.add_argument(
    '--no-custom', action='store_true', default=False,
    help='do not test custom cases')
PARSER_TEST.add_argument(
    '--no-color', action='store_true', default=False,
    help='do not use ansi color sequences')

PARSER_IMPORT_ZIP = SUBPARSERS.add_parser(
    'import',
    help='add programs to archived folder from zip file',
    parents=[PARENT_PARSER])
PARSER_IMPORT_ZIP.set_defaults(subcommand=import_zip.import_zip)
PARSER_IMPORT_ZIP.add_argument(
    'zip', type=argparse.FileType('r'),
    help='zip file containing the problems')
PARSER_IMPORT_ZIP.add_argument(
    '-f', '--folder', type=str,
    default=DEFAULT_PARAM['folder'],
    help='archive folder')
PARSER_IMPORT_ZIP.add_argument(
    '--delay', type=int, default=100,
    metavar='milliseconds',
    help='delay between jutge.org GET requests')
PARSER_IMPORT_ZIP.add_argument(
    '--overwrite', action='store_true',
    default=False,
    help='overwrite programs already found in archive')

PARSER_UPLOAD = SUBPARSERS.add_parser(
    'upload', aliases=['up'],
    help='Upload program for jutge evaluation',
    parents=[PARENT_PARSER])
PARSER_UPLOAD.set_defaults(subcommand=upload.upload)
PARSER_UPLOAD.add_argument(
    'prog', type=str,
    metavar='prog.cpp',
    help='program file to upload')
PARSER_UPLOAD.add_argument(
    '-c', '--code', type=str,
    metavar='CODE',
    help='code of problem to submit')
PARSER_UPLOAD.add_argument(
    '--compiler', type=str,
    metavar='COMPILER_ID',
    help='jutge.org compiler_id to use')
PARSER_UPLOAD.add_argument(
    '--problem-set', action='store_true', default=False,
    help='upload all files in problem set')
PARSER_UPLOAD.add_argument(
    '--delay', type=int, default=100,
    metavar='milliseconds',
    help='delay between jutge.org upload requests')
PARSER_UPLOAD.add_argument(
    '-f', '--folder', type=str,
    default=DEFAULT_PARAM['folder'],
    help='folder where programs are archived')
PARSER_UPLOAD.add_argument(
    '--skip-test', action='store_true', default=False,
    help='do not test public cases before uploading')
PARSER_UPLOAD.add_argument(
    '--no-skip-accepted', action='store_true',
    default=False,
    help='do not skip accepted problems when uploading')
PARSER_UPLOAD.add_argument(
    '--check', action='store_true', default=False,
    help='wait for veredict after uploading')

def config_logger(verbosity, quiet):
    """Configure logger based on verbosity and quiet

    :param verbosity: verbosity level
    :param quiet: quiet or not
    :type verbosity: int
    :type quiet: Boolean
    """

    if verbosity >= 3:
        log_lvl = logging.DEBUG
    elif verbosity == 2:
        log_lvl = logging.INFO
    elif verbosity == 1:
        log_lvl = logging.WARNING
    elif quiet:
        log_lvl = logging.CRITICAL
    else:
        log_lvl = logging.ERROR

    logging.basicConfig(
        format='%(levelname)s#%(name)s.%(funcName)s@%(lineno)d: %(message)s', level=log_lvl)


def main():
    """Parase arguments, configure needed variables and call submodules
    """

    args = PARSER.parse_args()

    config_logger(args.verbosity, args.quiet)

    log = logging.getLogger('jutge')

    log.debug(args.regex)
    log.debug(args.database)

    # Add code to kwargs
    args_dict = vars(args)

    cmd = args.subcmd

    if cmd in ('check', 'download', 'down', 'upload',
               'up', 'new', 'show', 'test'):
        args_dict['cookies'] = cookie.get_cookie(skip_check=True, **args_dict)
        if cmd in ('check', 'upload') and args_dict['cookies'] == {}:
            log.error('Please login before upload or check with: jutge login')
            exit(2)

    if cmd not in ('login', 'check', 'import', 'cookie'):
        args_dict['code'] = get_code.get_code(**args_dict)

    args_dict['database'] = expanduser(args_dict['database'])
    if 'folder' in args_dict:
        args_dict['folder'] = expanduser(args_dict['folder'])

    if cmd in ('new', 'show', 'test'):
        download.download(**args_dict)

    if cmd in ('archive', 'new'):
        args_dict['title'] = show.get_title(**args_dict)
        if args_dict['title'] is None:
            log.warning('Cannot find title, defaulting to code...')
            args_dict['title'] = args_dict['code']

    if cmd in ('archive', 'new', 'upload', 'up'):
        args_dict['problem_sets'] = CONFIG['problem_sets']

    if cmd != 'cookie':
        args_dict.pop('cookie', None)

    if 'prog' not in args_dict:
        args_dict['prog'] = None

    log.debug(args_dict)

    args.subcommand(**args_dict)  # expand flags to kwargs


if __name__ == '__main__':
    main()
