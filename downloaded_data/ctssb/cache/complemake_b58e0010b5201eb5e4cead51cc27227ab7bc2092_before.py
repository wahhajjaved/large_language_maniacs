#!/usr/bin/python
# -*- coding: utf-8; mode: python; tab-width: 3; indent-tabs-mode: nil -*-
#
# Copyright 2014
# Raffaello D. Di Napoli
#
# This file is part of Abaclade.
#
# Abaclade is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Abaclade is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even
# the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with Abaclade. If not, see
# <http://www.gnu.org/licenses/>.
#---------------------------------------------------------------------------------------------------

"""Classes that abstract different software platforms, concealing their differences for the rest of
Abamake.
"""

import os
import sys

import abamake
import abamake.tool

import imp
tpl = imp.find_module('platform', sys.path[1:])
pyplatform = imp.load_module('pyplatform', *tpl)
tpl[0].close()
del tpl


####################################################################################################
# SystemTypeError

class SystemTypeError(Exception):
   """Indicates an error related to system types."""

   pass

####################################################################################################
# SystemTypeTupleError

class SystemTypeTupleError(ValueError, SystemTypeError):
   """Raised when an invalid system type tuple is encountered."""

   pass

####################################################################################################
# SystemType

class SystemType(object):
   """System type tuple.

   See <http://wiki.osdev.org/Target_Triplet> for a clear and concise explanation.
   """

   # See SystemType.kernel.
   _m_sKernel = None
   # See SystemType.machine.
   _m_sMachine = None
   # See SystemType.os.
   _m_sOS = None
   # See SystemType.parsed_source.
   _m_sParsedSource = None
   # See SystemType.vendor.
   _m_sVendor = None

   def __init__(self, sMachine, sVendor, sKernel, sOS):
      """Constructor.

      str sMachine
         See SystemType.machine.
      str sKernel
         See SystemType.kernel.
      str sVendor
         See SystemType.vendor.
      str sOS
         See SystemType.os.
      """

      self._m_sKernel = sKernel
      self._m_sMachine = sMachine
      self._m_sOS = sOS
      self._m_sParsedSource = None
      self._m_sVendor = sVendor

   def __eq__(self, other):
      return \
         self._none_or_equal(self._m_sKernel,  other._m_sKernel ) and \
         self._none_or_equal(self._m_sMachine, other._m_sMachine) and \
         self._none_or_equal(self._m_sOS,      other._m_sOS     ) and \
         self._none_or_equal(self._m_sVendor,  other._m_sVendor )

   def __hash__(self):
      # Hashes like a tuple.
      return hash((self._m_sMachine, self._m_sVendor, self._m_sKernel, self._m_sOS))

   def __len__(self):
      return \
         int(bool(self._m_sMachine)) + int(bool(self._m_sVendor)) + \
         int(bool(self._m_sOS     )) + int(bool(self._m_sKernel))

   def __ne__(self, other):
      return not self.__eq__(self, other)

   def __str__(self):
      sVendor = self._m_sVendor or 'unknown'
      if self._m_sKernel:
         return '{}-{}-{}-{}'.format(self._m_sMachine, sVendor, self._m_sKernel, self._m_sOS)
      if self._m_sOS:
         return '{}-{}-{}'.format(self._m_sMachine, sVendor, self._m_sOS)
      if self._m_sVendor:
         return '{}-{}'.format(self._m_sMachine, self._m_sVendor)
      if self._m_sMachine:
         return '{}'.format(self._m_sMachine)
      return 'unknown'

   @staticmethod
   def detect_host():
      """Returns a SystemType instance describing the host on which Abamake is being run.

      abamake.platform.SystemType return
         Host system type.
      """

      sOS, sNode, sRelease, sVersion, sMachine, sProcessor = pyplatform.uname()

      if sOS == 'Windows':
         if sMachine == 'x86':
            return SystemType('i386', None, None, 'win32')
         elif sMachine == 'AMD64':
            return SystemType('x86_64', None, None, 'win64')
      elif sOS in ('FreeBSD', 'Linux'):
         if sOS == 'Linux':
            sKernel = 'linux'
            # TODO: don’t assume OS == GNU.
            sOS = 'gnu'
         else:
            sKernel = None
            sOS = sOS.lower()
            if sMachine == 'amd64':
               sMachine = 'x86_64'
         if sMachine in ('i386', 'i486', 'i586', 'i686', 'x86_64'):
            return SystemType(sMachine, None, sKernel, sOS)

      raise SystemTypeError('unsupported system type')

   def _get_kernel(self):
      return self._m_sKernel

   kernel = property(_get_kernel, doc = """
      Kernel on which the OS runs. Mostly used for the GNU operating system.
   """)

   def _get_machine(self):
      return self._m_sMachine

   machine = property(_get_machine, doc = """
      Machine type; often this is the processor’s architecture. Examples: 'i386', 'sparc'.
   """)

   @staticmethod
   def _none_or_equal(o1, o2):
      """Returns True if the two values are equal or if either is None.

      object o1
         First value to compare.
      object o2
         Second value to compare.
      bool return
         True if o1 == o2 or either is None, or False otherwise.
      """

      return not o1 or not o2 or o1 == o2

   def _get_os(self):
      return self._m_sOS

   os = property(_get_os, doc = """
      Operating system running on the system, or type of object file format for embedded systems.
      Examples: 'solaris2.5', 'irix6.3', 'elf', 'coff'.
   """)

   @staticmethod
   def parse_tuple(sTuple):
      """Parses a system type tuple into a SystemType instance. The format of the tuple must be one
      of:
      •  machine (1 item)
      •  machine-os (2 items)
      •  machine-vendor-os (3 items)
      •  machine-vendor-kernel-os (4 items)

      str sTuple
         String that will be parsed to extract the necessary information.
      abamake.platform.SystemType return
         Parsed system type.
      """

      # Break the tuple down.
      listTuple = sTuple.split('-')
      cTupleParts = len(listTuple)
      stRet = None
      if cTupleParts == 1:
         # The tuple contains “machine” only.
         stRet = SystemType(listTuple[0])
      elif cTupleParts == 2:
         # The tuple contains “machine” and “os”.
         stRet = SystemType(listTuple[0], None, None, listTuple[1])
      else:
         # The tuple contains “machine”, “vendor” and/or “kernel”, and “os”.
         # Suppress placeholders in the “vendor” field.
         if listTuple[1] in ('none', 'unknown'):
            listTuple[1] = None
         if cTupleParts == 3:
            # Assume that GNU always requires a kernel to be part of the tuple.
            # TODO: find a way to avoid this? It could become a long list of “special cases”.
            if listTuple[2] == 'gnu':
               # The tuple contains “machine”, “kernel” and “os”.
               stRet = SystemType(listTuple[0], None, listTuple[1], listTuple[2])
            else:
               # The tuple contains “machine”, “vendor” and “os”.
               stRet = SystemType(listTuple[0], listTuple[1], None, listTuple[2])
         elif cTupleParts == 4:
            # The tuple contains “machine”, “vendor”, “kernel” and “os”.
            stRet = SystemType(*listTuple)
      if not stRet:
         raise SystemTypeTupleError('invalid system type tuple: “{}”'.format(sTuple))
      # Assign the SystemType the string it was parsed from.
      stRet._m_sParsedSource = sTuple
      return stRet

   def _get_parsed_source(self):
      return self._m_sParsedSource

   parsed_source = property(_get_parsed_source, doc = """
      String from which the Platform object was parsed. Example: 'x86_64-pc-linux-gnu'.
   """)

   def _get_vendor(self):
      return self._m_sVendor

   vendor = property(_get_vendor, doc = """Vendor. Examples: 'unknown'. 'pc', 'sun'.""")

####################################################################################################
# Platform

class Platform(object):
   """Generic software platform (OS/runtime environment)."""

   # Tools to be used for this platform (abamake.tool.Tool => abamake.tool.Tool). Associates a Tool
   # subclass to a more derived Tool subclass, representing the implementation to use of the tool.
   _m_dictTools = None
   # System type (more specific than the platform type).
   _m_st = None

   def __init__(self, st):
      """Constructor.

      abamake.platform.SystemType st
         System type of this platform.
      """

      self._m_dictTools = {}
      self._m_st = st

   def add_dir_to_dynlib_env_path(self, dictEnv, sDir):
      """Modifies an environment dictionary (similar to os.environ) so that it allows to load
      dynamic libraries from the specified directory.

      dict(str: str) dictEnv
         Environment dictionary.
      str sDir
         Directory to add to the dynlib path.
      dict(str: str) return
         Same as dictEnv, returned for convenience.
      """

      raise NotImplementedError(
         'Platform.add_dir_to_dynlib_env_path() must be overridden in ' + type(self).__name__
      )

   def adjust_popen_args_for_script(self, dictPopenArgs):
      """Adjusts a dictionary of arguments to be used to run a program with subprocess.Popen in a
      way that allows to execute non-programs (e.g. scripts), by changing the command into a shell
      invocation if necessary.

      The default implementation assumes that scripts can be executed directly (e.g. via shebang)
      without any changes to dictPopenArgs.

      dict(str: object) dictPopenArgs
         Popen arguments dictionary.
      """

      pass

   def configure_tool(self, tool):
      """Configures the specified tool for this platform.

      abamake.tool.Tool tool
         Tool to configure.
      """

      pass

   @classmethod
   def detect_host(cls):
      """Attempts to detect the underlying (host) platform, returning an instance of the Platform
      subclass that models it best.

      abamake.platform.Platform return
         Model for the underlying (host) platform.
      """

      return cls.from_system_type(SystemType.detect_host())

   @classmethod
   def from_system_type(cls, st):
      """Returns an instance of the Platform subclass that most closely matches the specified system
      type. For example, Platform.from_system_type(SystemType.parse_tuple('i686-pc-linux-gnu')) will
      return an abamake.platform.GnuPlatform instance.

      abamake.platform.SystemType st
         System type.
      abamake.platform.Platform return
         Corresponding platform.
      """

      iBestMatch, clsBestMatch = 0, None
      for clsDeriv in abamake.derived_classes(cls):
         iMatch = clsDeriv._match_system_type(st)
         if iMatch > iBestMatch:
            iBestMatch, clsBestMatch = iMatch, clsDeriv
      if not clsBestMatch:
         raise Exception('unable to detect platform for system type {}'.format(st))
      return clsBestMatch(st)

   def dynlib_file_name(self, sName):
      """Generates a file name for a dynamic library from the specified name.

      str sName
         Name of the dynamic library.
      str return
         Name of the dynamic library’s file.
      """

      raise NotImplementedError(
         'Platform.dynlib_file_name() must be overridden in ' + type(self).__name__
      )

   # If True, dynamic libraries need import libraries (i.e. statically-linked runtime-patchable
   # data) for the linker to be able to generate executables that link to them; if False, dynlibs
   # can be linked to directly.
   dynlibs_need_implibs = False

   def exe_file_name(self, sName):
      """Generates an executable file name from the specified name.

      str sName
         Name of the executable.
      str return
         Name of the executable’s file.
      """

      raise NotImplementedError(
         'Platform.exe_file_name() must be overridden in ' + type(self).__name__
      )

   def get_tool(self, clsTool):
      """Returns a subclass of the specified Tool subclass modeling the implementation of the
      specified tool for the platform.

      For example, my_platform.get_tool(abamake.tool.CxxCompiler) will return
      abamake.tool.GxxCompiler if G++ is the C++ compiler for my_platorm.

      type clsTool
         Subclass of abamake.tool.Tool.
      type return
         Subclass of clsTool.
      """

      clsToolImpl = self._m_dictTools.get(clsTool)
      if not clsToolImpl:
         # TODO: support tools specified via command line: --tool-CxxCompiler i686-pc-linux-gnu-g++
         clsToolImpl = clsTool.get_impl_for_system_type(self._m_st)
         self._m_dictTools[clsTool] = clsToolImpl
      return clsToolImpl

   @classmethod
   def _match_system_type(cls, st):
      """Returns a confidence index of how much the platform models the specified system type.

      The default implementation always returns 0.

      abamake.platform.SystemType st
         System type.
      int return
         A value in range 0-4, representing how many elements of st match the platform.
      """

      return 0

####################################################################################################
# GnuPlatform

class GnuPlatform(Platform):
   """GNU Operating System platform."""

   def add_dir_to_dynlib_env_path(self, dictEnv, sDir):
      """See Platform.add_dir_to_dynlib_env_path()."""

      sLibPath = dictEnv.get('LD_LIBRARY_PATH', '')
      if sLibPath:
         sLibPath += ':'
      sLibPath += os.path.abspath(sDir)
      dictEnv['LD_LIBRARY_PATH'] = sLibPath
      return dictEnv

   def configure_tool(self, tool):
      """See Platform.configure_tool()."""

      if isinstance(tool, abamake.tool.Linker):
         tool.add_input_lib('dl')
         tool.add_input_lib('pthread')

   def dynlib_file_name(self, sName):
      """See Platform.dynlib_file_name()."""

      return 'lib{}.so'.format(sName)

   def exe_file_name(self, sName):
      """See Platform.exe_file_name()."""

      return '{}'.format(sName)

   @classmethod
   def _match_system_type(cls, st):
      """See Platform._match_system_type()."""

      if st.os == 'gnu':
         return 1
      else:
         return 0

####################################################################################################
# WinPlatform

class WinPlatform(Platform):
   """Generic Windows platform."""

   def add_dir_to_dynlib_env_path(self, dictEnv, sDir):
      """See Platform.add_dir_to_dynlib_env_path()."""

      sLibPath = dictEnv.get('PATH', '')
      if sLibPath:
         sLibPath += ';'
      sLibPath += os.path.abspath(sDir)
      dictEnv['PATH'] = sLibPath
      return dictEnv

   def adjust_popen_args_for_script(self, dictPopenArgs):
      """See Platform.adjust_popen_args_for_script()."""

      sArg0 = dictPopenArgs['args'][0]
      if not sArg0.endswith('.exe') and not sArg0.endswith('.com'):
         # Windows cannot execute non-executables directly; have a shell figure out how to run this
         # script.
         dictPopenArgs['shell'] = True

   def configure_tool(self, tool):
      """See Platform.configure_tool()."""

      if isinstance(tool, abamake.tool.Linker):
         tool.add_input_lib('kernel32')
         tool.add_input_lib('user32')

   def dynlib_file_name(self, sName):
      """See Platform.dynlib_file_name()."""

      return '{}.dll'.format(sName)

   # See Platform.dynlibs_need_implibs.
   dynlibs_need_implibs = True

   def exe_file_name(self, sName):
      """See Platform.exe_file_name()."""

      return '{}.exe'.format(sName)

####################################################################################################
# Win32Platform

class Win32Platform(WinPlatform):
   """Win32 platform."""

   @classmethod
   def _match_system_type(cls, st):
      """See WinPlatform._match_system_type()."""

      if st.machine in ('i386', 'i486', 'i586', 'i686') and st.os in ('win32', 'mingw', 'mingw32'):
         return 2
      else:
         return 0

####################################################################################################
# Win64Platform

class Win64Platform(WinPlatform):
   """Win64 platform."""

   @classmethod
   def _match_system_type(cls, st):
      """See WinPlatform._match_system_type()."""

      if st.machine == 'x86_64' and st.os in ('win64', 'mingw64'):
         return 2
      else:
         return 0
