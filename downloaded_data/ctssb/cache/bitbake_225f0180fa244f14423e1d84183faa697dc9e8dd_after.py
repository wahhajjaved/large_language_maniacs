"""
OpenEmbedded 'Fetch' implementations

Classes for obtaining upstream sources for the
OpenEmbedded (http://openembedded.org) build infrastructure.

NOTE that it requires Python 2.x due to its use of static methods.

Copyright: (c) 2003 Chris Larson

Based on functions from the base oe module, Copyright 2003 Holger Schurig
"""

import os, re
from oe import *

class FetchError(Exception):
	"""Exception raised when a download fails"""

class NoMethodError(Exception):
	"""Exception raised when there is no method to obtain a supplied url or set of urls"""

class MissingParameterError(Exception):
	"""Exception raised when a fetch method is missing a critical parameter in the url"""

class FetchUrls:
	"""Class to obtain a set of urls, via any available methods"""
	__methods = {	"Wget" : None,
			"Cvs" : None,
			"Bk" : None,
			"Local" : None }

	def setMethods(self, methods):
		self.__methods = methods

	def getMethods(self):
		return self.__methods

	methods = property(getMethods, setMethods, None, "Methods property")

	def init(self, urls = []):
		"""Initial setup function for url fetching.
		   Determines which urls go with which 'fetch' methods.
		"""
		for method in self.__methods.keys():
			if self.__methods[method] is not None:
				self.__methods[method].urls = []

		for url in urls:
			decoded = decodeurl(url)
			if Wget.supports(decoded):
				if self.__methods["Wget"] is None:
					self.__methods["Wget"] = Wget()
				self.__methods["Wget"].urls.append(url) 
			elif Cvs.supports(decoded):
				if self.__methods["Cvs"] is None:
					self.__methods["Cvs"] = Cvs()
				self.__methods["Cvs"].urls.append(url) 
			elif Bk.supports(decoded):
				if self.__methods["Bk"] is None:
					self.__methods["Bk"] = Bk()
				self.__methods["Bk"].urls.append(url) 
			elif Local.supports(decoded):
				if self.__methods["Local"] is None:
					self.__methods["Local"] = Local()
				self.__methods["Local"].urls.append(url) 
			else:
				raise NoMethodError(url)
	
	def go(self):
		"""Fetch all urls"""
		for method in self.__methods.keys():
			if self.__methods[method] is None:
				continue
			debug(2,"Obtaining urls via %s method..." % method)
			self.__methods[method].go()

	def localpaths(self):
		"""Return a list of the local filenames, assuming successful fetch"""
		local = []
		for method in self.__methods.keys():
			if self.__methods[method] is None:
				continue
			for url in self.__methods[method].urls:
				local.append(self.__methods[method].localpath(url))
		return local

	def localpath(self, url):
		for method in self.__methods.keys():
			if self.__methods[method] is not None:
				if url in self.__methods[method].urls:
					return self.__methods[method].localpath(url)
		return url 

class Fetch(object):
	"""Base class for 'fetch'ing data"""
	
	def __init__(self, urls = []):
		self.urls = []
		for url in urls:
			if self.supports(decodeurl(url)) is 1:
				self.urls.append(url)

	def supports(decoded):
		"""Check to see if this fetch class supports a given url.
		   Expects supplied url in list form, as outputted by oe.decodeurl().
		"""
		return 0
	supports = staticmethod(supports)

	def localpath(url):
		"""Return the local filename of a given url assuming a successful fetch.
		"""
		return url
	localpath = staticmethod(localpath)

	def setUrls(self, urls):
		self.__urls = urls

	def getUrls(self):
		return self.__urls

	urls = property(getUrls, setUrls, None, "Urls property")

	def go(self, urls = []):
		"""Fetch urls"""
		raise NoMethodError("Missing implementation for url")

class Wget(Fetch):
	"""Class to fetch urls via 'wget'"""
	def supports(decoded):
		"""Check to see if a given url can be fetched using wget.
		   Expects supplied url in list form, as outputted by oe.decodeurl().
		"""
		return decoded[0] in ['http','https','ftp']
	supports = staticmethod(supports)

	def localpath(url):
		(type, host, path, user, pswd, parm) = decodeurl(expand(url))
		if parm.has_key("localpath"):
			# if user overrides local path, use it.
			return parm["localpath"]
		return os.path.join(getenv("DL_DIR"), re.sub(r";.*$","",os.path.basename(url)))
	localpath = staticmethod(localpath)

	def go(self, urls = []):
		"""Fetch urls"""
		if not urls:
			urls = self.urls

		for loc in urls:
			(type, host, path, user, pswd, parm) = decodeurl(expand(loc))
			myfile = os.path.basename(path)
			dlfile = self.localpath(loc)

			myfetch = getenv("RESUMECOMMAND")
			note("fetch " +loc)
			myfetch = myfetch.replace("${URI}",re.sub(r";.*$","",loc))
			myfetch = myfetch.replace("${FILE}",myfile)
			debug(2,myfetch)
			myret = os.system(myfetch)
			if myret != 0:
				raise FetchError(myfile)

class Cvs(Fetch):
	"""Class to fetch a module or modules from cvs repositories"""
	checkoutopts = { "tag": "-r",
			 "date": "-D" }

	def supports(decoded):
		"""Check to see if a given url can be fetched with cvs.
		   Expects supplied url in list form, as outputted by oe.decodeurl().
		"""
		return decoded[0] in ['cvs', 'pserver']
	supports = staticmethod(supports)

	def localpath(url):
		(type, host, path, user, pswd, parm) = decodeurl(expand(url))
		if parm.has_key("localpath"):
			# if user overrides local path, use it.
			return parm["localpath"]

		if not parm.has_key("module"):
			return url
		else:
			return os.path.join(getenv("DL_DIR"), parm["module"])
	localpath = staticmethod(localpath)

	def go(self, urls = []):
		"""Fetch urls"""
		if not urls:
			urls = self.urls

		for loc in urls:
			(type, host, path, user, pswd, parm) = decodeurl(expand(loc))
			if not parm.has_key("module"):
				raise MissingParameterError("cvs method needs a 'module' parameter")
			else:
				module = parm["module"]

			dlfile = self.localpath(loc)
			# if local path contains the cvs
			# module, consider the dir above it to be the
			# download directory
			pos = dlfile.find(module)
			if pos:
				dldir = dlfile[:pos]
			else:
				dldir = os.path.dirname(dlfile)

			options = []

			for opt in self.checkoutopts:
				if parm.has_key(opt):
					options.append(self.checkoutopts[opt] + " " + parm[opt])

			if parm.has_key("method"):
				method = parm["method"]
			else:
				method = "pserver"

			os.chdir(expand(dldir))
			cvsroot = ":" + method + ":" + user
			if pswd is not None:
				cvsroot += ":" + pswd
			cvsroot += "@" + host + ":" + path

			if method == "pserver":
				# Login to the server
				cvscmd = "cvs -d" + cvsroot + " login"
				myret = os.system(cvscmd)
				if myret != 0:
					raise FetchError(module)

			cvscmd = "cvs -d" + cvsroot
			cvscmd += " checkout " + string.join(options) + " " + module 
			note("fetch " + loc)
			myret = os.system(cvscmd)
			if myret != 0:
				raise FetchError(module)

class Bk(Fetch):
	def supports(decoded):
		"""Check to see if a given url can be fetched via bitkeeper.
		   Expects supplied url in list form, as outputted by oe.decodeurl().
		"""
		return decoded[0] in ['bk']
	supports = staticmethod(supports)

class Local(Fetch):
	def supports(decoded):
		"""Check to see if a given url can be fetched in the local filesystem.
		   Expects supplied url in list form, as outputted by oe.decodeurl().
		"""
		return decoded[0] in ['file','patch']
	supports = staticmethod(supports)

	def localpath(url):
		"""Return the local filename of a given url assuming a successful fetch.
		"""
		return url.split("://")[1]
	localpath = staticmethod(localpath)

	def go(self, urls = []):
		"""Fetch urls (no-op for Local method)"""
		# no need to fetch local files, we'll deal with them in place.
		return 1
