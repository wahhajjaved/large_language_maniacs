#!/bin/env python

################################################################################
#
# @file        BuildCommand.py
#
# $Id: BuildCommand.py 3699 2012-12-18 19:08:52Z dfeiock $
#
# @author      James H. Hill
#
################################################################################

import getopt
import os
import sys
import logging

from ..Command import Command
from ..Context import Context

#
# Factory method for the command
#
def __create__ ():
  return BuildCommand ()

#
# @class BuildContext
#
class BuildContext (Context):
  @staticmethod
  def init_parser (parser):
    build_parser = parser.add_parser ('build',
                                       help = 'Build all the projects in the workspace',
                                       description = 'Build all the projects in the workspace')

    build_parser.add_argument ('--versioned-namespace', '-v',
                               help = 'Build with versioned namespace support',
                               action = 'store_true')

    build_parser.add_argument ('--clean', '-x',
                               help = 'Clean the projects',
                               action = 'store_true')

    build_parser.add_argument ('--threads', '-t',
                               help = 'Number of threads to use when compiling',
                               type = str,
                               default = 1)

    build_parser.set_defaults (cmd = BuildCommand)
    build_parser.set_defaults (ctx = BuildContext)

  def __init__ (self, args):
    Context.__init__ (self, args)
    self.versioned_namespace = args.versioned_namespace
    self.clean = args.clean
    self.threads = args.threads

#   
# @class BuildCommand
#
# Command that builds all projects in the workspace.
#
class BuildCommand (Command):
  context = BuildContext
  
  #
  # Get the command's name
  #
  def name (self):
    return 'build'
  
  #
  # Execute the command
  #
  def execute (self, ctx):
    # First, configure the environment so the build does not fail
    # because of missing environment variables.
    configure_environment (ctx.prefix)
    
    # Auto-detect the build type.
    from ..Utilities import autodetect_build_type
    build_type = autodetect_build_type ()

    # Validate build environment
    logging.getLogger ().info ('validating build environment')
    for proj in ctx.workspace.order_projects ():
        if not proj.validate_environment ():
            sys.exit (1)
    
    if (ctx.versioned_namespace):
        logging.getLogger ().info ('building projects with versioned namespace support')
        
    if (ctx.clean):
      for proj in ctx.workspace.order_projects ():
          logging.getLogger ().info ('cleaning {0}...'.format (proj.name ()))
          proj.clean (ctx.prefix, build_type, ctx.versioned_namespace)
    else:
      for proj in ctx.workspace.order_projects ():
          logging.getLogger ().info ('building {0}...'.format (proj.name ()))
          proj.build (ctx, build_type)
      

#
# Utility method that configures the enviroment using the properties
# file at the specified location
#
# @param          prefix          Location of property file 
#
def configure_environment (prefix):
  logging.getLogger ().info ("configuring the enviroment")
  # Load the existing properties file into memory and use it
  # to configure our execution environment, if the file does
  # indeed exist.
  properties_filename = os.path.join (prefix, 'configure.properties')

  if os.path.exists (properties_filename):
      # Read the properties from the file, and update the
      # environment variables.
      logging.getLogger ().info ('loading properties from {0}'.format (properties_filename))

      from ..scripts import PropertiesFile
      props = PropertiesFile.PropertiesFile.read (properties_filename)

      for key, value in props.items ():
          if key == 'LIB_PATH':
              from build.Utilities import append_libpath_variable
              append_libpath_variable (value)
          elif key == 'PATH':
              from build.Utilities import append_path_variable
              append_path_variable (value)                
          else:
              os.environ[key] = value
  else:
      logging.getLogger ().error ('{0} does not exist'.format (properties_filename))

