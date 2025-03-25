"""Main interface to all the goodies.

Copyright (c) 2003-2012 Jamie "Entity" van den Berge <jamie@hlekkir.com>

This code is free software; you can redistribute it and/or modify
it under the terms of the BSD license (see the file LICENSE.txt
included with the distribution).
"""

import __builtin__
import sys
from time import sleep as _sleep

from ._blue import marshal, DBRow, DBRowDescriptor
from . import exceptions, cache, _os as os, _blue, pyFSD
from reverence.carbon.common.lib.utillib import KeyVal


__all__ = ["EVE", "marshal", "os", "pyos", "DBRow", "DBRowDescriptor"]


# Little hack to have our exceptions look pretty when raised; instead of
#   "reverence.blue.marshal.UnmarshalError: not enough kittens!"
# it will look like
#   "UnmarshalError: not enough kittens!"
# Yes I know this is naughty, but EVE presents them like this as well ;)
marshal.UnmarshalError.__module__ = None

# and because the exception class is accessible like this in EVE ...
exceptions.UnmarshalError = exceptions.SQLError = __builtin__.UnmarshalError = marshal.UnmarshalError

class boot:
	role = "client"

class pyos:
	class synchro:
		@staticmethod
		def Sleep(msec):
			_sleep(msec / 1000.0)


class statistics(object):
	# dummy for compatibility with CCP libs

	@staticmethod
	def EnterZone(*args):
		pass

	@staticmethod
	def LeaveZone():
		pass


class _ResFile(object):
	# read-only resource file handler.

	def __init__(self, rot):
		self.fh = None
		self.rot = rot

	def Open(self, filename):
		self.Close()
		try:
			if filename.startswith("res:"):
				# we gotta have to open a .stuff file...
				try:
					self.fh = self.rot.efs.open("res/" + filename[5:])
				except IndexError, e:
					return None
			elif filename.startswith("cache:"):
				self.fh = open(os.path.join(self.eve.root, "cache", filename[7:]), "rb") 
			else:
				self.fh = open(filename, "rb")
		except IOError:
			pass

		return self.fh

	def Read(self, *args):
		return self.fh.read(*args)

	def Close(self):
		if self.fh:
			self.fh.close()
			self.fh = None

	# ---- custom additions ----

	def read(self, *args):
		return self.fh.read(*args)

	def readline(self):
		return self.fh.readline()

	def seek(self, *args, **kw):
		return self.fh.seek(*args, **kw)


class _Rot(object):
	def __init__(self, eve):
		from . import embedfs
		self.eve = eve
		self.efs = embedfs.EmbedFSDirectory(eve.root)


# offline RemoteSvc wrappers

class _RemoteSvcWrap(object):
	def __init__(self, eve, name):
		self.eve = eve
		self.svcName = name

	def __getattr__(self, methodName):
		return _RemoteSvcMethod(self.eve, self.svcName, methodName)


class _RemoteSvcMethod(object):
	def __init__(self, eve, svcName, methodName):
		self.eve = eve
		self.svcName = svcName
		self.methodName = methodName

	def __call__(self, *args, **kw):
		key = (self.svcName, self.methodName) + args
		obj = self.eve.cache.LoadCachedMethodCall(key)
		return obj['lret']


ResFile = None

class EVE(object):
	"""Interface to an EVE installation's related data.

	provides the following methods:
	getconfigmgr() - creates interface to bulkdata. see config.ConfigMgr.
	getcachemgr() - creates interface to cache. see cache.CacheMgr.
	readstuff(name) - reads the specified file from EVE's virtual file system.
	RemoteSvc(service) - creates offline RemoteSvc wrapper for given service.
	"""

	def __init__(self, root, server="Tranquility", machoVersion=-1, languageID="en-us", cachepath=None, wineprefix=".wine"):
		self.root = root
		self.server = server
		self.rot = _Rot(self)
		self.languageID = languageID

		# default cache
		self.cache = cache.CacheMgr(self.root, self.server, machoVersion, cachepath, wineprefix)
		self.machoVersion = self.cache.machoVersion

		self.cfg = self.cache.getconfigmgr(languageID=self.languageID)
		self.cfg._eve = self

		# hack to make blue.ResFile() work. This obviously means that
		# when using multiple EVE versions, only the latest will be accessible
		# in that manner.
		global ResFile
		ResFile = lambda: _ResFile(self.rot)

	def RemoteSvc(self, service):
		"""Creates a wrapper through which offline remote service methods can be called"""
		return _RemoteSvcWrap(self, service)

	# --- custom additions ---

	def ResFile(self):
		return _ResFile(self.rot)

	def getcachemgr(self):
		"""Return CacheMgr instance through which this EVE's cache can be manually accessed"""
		return self.cache

	def getconfigmgr(self):
		"""Return ConfigMgr instance through which this EVE's bulkdata can be accessed"""
		return self.cfg

	def readstuff(self, name):
		"""Reads specified file in the virtual filesystem"""
		f = _ResFile(self.rot)
		f.Open(name)
		return f.read()




def _readstringstable():
	from . import strings

	marshal._stringtable[:] = strings.stringTable
	#marshal._stringtable_rev.clear()

	#c = 1
	#for line in strings.stringsTable:
	#	marshal._stringtable_rev[line] = c
	#	c+=1




def _find_global(module, name):
	# locates a global. used by marshal.Load and integrated unpickler

	# compatibility
	if module == "util" and name == "KeyVal":
		return KeyVal
	try:
		m = __import__(module, globals(), locals(), (), -1)
	except ImportError:
		raise RuntimeError("Unable to locate object: " + module + "." + name + " (import failed)")

	try:
		return getattr(m, name)
	except AttributeError:
		raise RuntimeError("Unable to locate object: " + module + "." + name + " (not in module)")


def _debug(*args):
	print >>sys.stderr, args[0].Keys(), args


# __str__ function for DBRow objects. This is done in python because it would
# take considerably more effort to implement in C. It's not the most efficient
# way to display DBRows, but quite useful for debugging or inspection.
_fmt = u"%s:%s".__mod__
def dbrow_str(row):
	return "DBRow(" + ','.join(map(_fmt, zip(row.__keys__, row))) + ")"
_blue.dbrow_str = dbrow_str


# set the helper functions in the marshaller and init strings table
marshal._set_find_global_func(_find_global)
marshal._set_debug_func(_debug)
_readstringstable()

# hack to make CCP zip libs accept our not-exactly-the-same environment
sys.modules["blue"] = sys.modules["reverence.blue"]

# and this one to make CCP's FSD loader import pyFSD succesfully
sys.modules["pyFSD"] = pyFSD

__builtin__.boot = boot

