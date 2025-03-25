#!/usr/bin/python
# -*- coding: utf-8; mode: python; tab-width: 3; indent-tabs-mode: nil -*-
#
# Copyright 2013-2017 Raffaello D. Di Napoli
#
# This file is part of Complemake.
#
# Complemake is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Complemake is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License along with Complemake. If not, see
# <http://www.gnu.org/licenses/>.
#-------------------------------------------------------------------------------------------------------------

"""Builds outputs and runs tests as specified in a .comk file."""

# TODO: maybe support launching gdb/devenv to run one of the programs via debugger?
#
# POSIX:
#    gdb --args {exe}
#
# Win32:
#    devenv.exe /debugexe {exe}  Opens the specified executable to be debugged. The remainder of the command
#                                line is passed to this executable as its arguments.
#    vsjitdebugger.exe -p {pid}  Attaches the debugger from the command line.

import os
import sys

import comk.make
import comk.tool


##############################################################################################################

def main(args):
   """Implementation of __main__.

   iterable(str*) args
      Command-line arguments.
   int return
      Command return status.
   """

   import argparse

   argparser = argparse.ArgumentParser(add_help=False)
   #   Usage: complemake.py [options] [makefile] [targets...]
   argparser.add_argument(
      '-n', '--dry-run', action='store_true', default=False,
      help='Don’t actually run any external commands. Useful to test if anything needs to be built.'
   )
   argparser.add_argument(
      '-f', '--force-build', action='store_true', default=False,
      help='Unconditionally rebuild all targets.'
   )
   argparser.add_argument(
      '-t', '--force-test', action='store_true', default=False,
      help='Unconditionally run all test targets.'
   )
   argparser.add_argument(
      '--help', action='help',
      help='Show this informative message and exit.'
   )
   argparser.add_argument(
      '-j', '--jobs', default=None, metavar='N', type=int,
      help='Build using N processes at at time; if N is omitted, build all independent targets at the same ' +
           'time. If not specified, the default is --jobs <number of processors>.'
   )
   argparser.add_argument(
      '-k', '--keep-going', action='store_true', default=False,
      help='Continue building targets even if other independent targets fail.'
   )
   argparser.add_argument(
      '-m', '--makefile', metavar='PROJECT.comk',
      help='Complemake file (.comk) containing instructions on how to build targets. If omitted and the ' +
           'current directory contains a single file matching *.comk, that file will be used as makefile.'
   )
   argparser.add_argument(
      '-g', '--target-system-type', metavar='SYSTEM-TYPE',
      help='Use SYSTEM-TYPE (e.g. dash-separated triplet) as the build target system type.'
   )
   argparser.add_argument(
      '--tool-c++', metavar='/path/to/c++', dest='tool_cxx',
      help='Use /path/to/c++ as the C++ compiler (and linker driver, unless --tool-ld is also specified).'
   )
   argparser.add_argument(
      '--tool-ld', metavar='/path/to/ld',
      help='Use /path/to/ld as the linker/linker driver.'
   )
   argparser.add_argument(
      '-v', '--verbose', action='count', default=0,
      help='Increase verbosity level; can be specified multiple times.'
   )
   argparser.add_argument(
      'target', nargs='*',
      help='List of target files to be conditionally built. If none are specified, all targets declared in ' +
           'the Complemake file (.comk) will be conditionally built.'
   )

   args = argparser.parse_args()

   mk = comk.make.Make()
   mk.dry_run = args.dry_run
   mk.force_build = args.force_build
   mk.force_test = args.force_test
   if args.jobs:
      mk.job_runner.running_jobs_max = args.jobs
   mk.keep_going = args.keep_going
   if args.target_system_type:
      mk.target_platform = args.target_system_type
   if args.tool_cxx:
      mk.target_platform.set_tool(comk.tool.CxxCompiler, args.tool_cxx)
      if not args.tool_ld:
         # Also use the C++ compiler as the linker driver.
         mk.target_platform.set_tool(comk.tool.Linker, args.tool_cxx)
   if args.tool_ld:
      mk.target_platform.set_tool(comk.tool.Linker, args.tool_ld)
   mk.log.verbosity += args.verbose

   # Check for a makefile.
   makefile_path = args.makefile
   if not makefile_path:
      # Check if the current directory contains a single Complemake file.
      for file_path in os.listdir(os.getcwd()):
         if file_path.endswith('.comk'):
            if makefile_path:
               sys.stderr.write(
                  'error: multiple makefiles found in the current directory, please specify one explicitly ' +
                  'with --makefile PROJECT.comk\n'
               )
               return 1
            makefile_path = file_path
      del file_path
      # Still no makefile?
      if not makefile_path:
         sys.stderr.write(
            'error: no makefiles in current directory, please specify one explicitly with --makefile ' +
            'PROJECT.comk\n'
         )
         return 1
   # Load the makefile.
   mk.parse(makefile_path)
#   mk.print_target_graphs()

   # If any targets were specified, only a subset of the targets should be built; otherwise all named targets
   # will be built.
   if args.target:
      targets = []
      for target in args.target:
         # mk.get_file_target() will raise an exception if no such file target is defined.
         targets.append(mk.get_named_target(target, None) or mk.get_file_target(os.path.normpath(target)))
   else:
      targets = mk.named_targets

   # Build the selected targets.
   all_succeeded = mk.build_targets(targets)

   mk.log.test_summary()
   return 0 if all_succeeded else 1

if __name__ == '__main__':
   sys.exit(main(sys.argv))
