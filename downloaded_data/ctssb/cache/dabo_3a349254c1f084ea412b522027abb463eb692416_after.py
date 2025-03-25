# -*- coding: utf-8 -*-
import sys
import os
import locale
import warnings
import glob
import tempfile
import ConfigParser
import inspect
import datetime
import urllib
import shutil
import dabo
import dabo.ui
import dabo.db
from dabo.lib.connParser import importConnections
import dSecurityManager
from dLocalize import _
from dabo.lib.SimpleCrypt import SimpleCrypt
from dabo.dObject import dObject
import dUserSettingProvider


class Collection(list):
	""" Collection : Base class for the various collection
	classes used in the app object.
	"""
	def __init__(self):
		list.__init__(self)


	def add(self, objRef):
		"""Add the object reference to the collection."""
		self.append(objRef)
		

	def remove(self, objRef):
		"""Delete the object reference from the collection."""
		try:
			index = self.index(objRef)
		except ValueError:
			index = None
		if index is not None:
			del self[index]



class TempFileHolder(object):
	"""Utility class to get temporary file names and to make sure they are 
	deleted when the Python session ends.
	"""
	def __init__(self):
		self._tempFiles = []


	def __del__(self):
		self._eraseTempFiles()
		
		
	def _eraseTempFiles(self):
		# Try to erase all temp files created during life.
		# Need to re-import the os module here for some reason.
		try:
			import os
			for f in self._tempFiles:
				if not os.path.exists(f):
					continue
				try:
					os.remove(f)
				except OSError, e:
					if not f.endswith(".pyc"):
						# Don't worry about the .pyc files, since they may not be there
						print "Could not delete %s: %s" % (f, e)
		except:
			# In these rare cases, Python has already 'gone away', so just bail
			pass
	
	
	def release(self):
		self._eraseTempFiles()		


	def append(self, f):
		self._tempFiles.append(f)


	def getTempFile(self, ext=None, badChars=None, directory=None):
		if ext is None:
			ext = "py"
		if badChars is None:
			badChars = "-:"
		fname = ""
		suffix = ".%s" % ext
		while not fname:
			if directory is None:
				fd, tmpname = tempfile.mkstemp(suffix=suffix)
			else:
				fd, tmpname = tempfile.mkstemp(suffix=suffix, dir=directory)
			os.close(fd)
			bad = [ch for ch in badChars if ch in os.path.split(tmpname)[1]]
			if not bad:
				fname = tmpname
		self.append(fname)
		if fname.endswith(".py"):
			# Track the .pyc file, too.
			self.append(fname + "c")
		return fname



class dApp(dObject):
	"""The containing object for the entire application.

	All Dabo objects have an Application property which refers to the dApp
	instance. Instantiate your dApp object from your main script, like so:

	>>> import dabo
	>>> app = dabo.dApp
	>>> app.start()

	Normally, dApp gets instantiated from the client app's main Python script,
	and lives through the life of the application.

		-- set up an empty data connections object which holds 
		-- connectInfo objects connected to pretty names. If there 
		-- is a file named 'default.cnxml' present, it will import the
		-- connection definitions contained in that. If no file of that
		-- name exists, it will import any .cnxml file it finds. If there
		-- are no such files, it will then revert to the old behavior
		-- of importing a file in the current directory called 
		-- 'dbConnectionDefs.py', which contains connection
		-- definitions in python code format instead of XML.

		-- Set up a DB Connection manager, that is basically a dictionary
		-- of dConnection objects. This allows connections to be shared
		-- application-wide.

		-- decide which ui to use (wx) and gets that ball rolling

		-- look for a MainForm in an expected place, otherwise use default dabo 
		-- dMainForm, and instantiate that. 

		-- maintain a forms collection and provide interfaces for
		-- opening dForms, closing them, and iterating through them.

		-- start the main app event loop.

		-- clean up and exit gracefully

	"""
	_call_beforeInit, _call_afterInit, _call_initProperties = False, False, True
	# Behaviors which are normal in the framework may need to
	# be modified when run as the Designer. This flag will 
	# distinguish between the two states.
	isDesigner = False

	
	def __init__(self, selfStart=False, properties=None, *args, **kwargs):
		self._uiAlreadySet = False
		dabo.dAppRef = self
		self._beforeInit()
		
		# If we are displaying a splash screen, these attributes control
		# its appearance. Extract them before the super call.
		self.showSplashScreen = self._extractKey(kwargs, "showSplashScreen", False)
		basepath = os.path.split(dabo.__file__)[0]
		img = os.path.join(basepath, "icons", "daboSplashName.png")
		self.splashImage = self._extractKey(kwargs, "splashImage", img)
		self.splashMaskColor = self._extractKey(kwargs, "splashMaskColor", None)
		self.splashTimeout = self._extractKey(kwargs, "splashTimeout", 5000)
		
		super(dApp, self).__init__(properties, *args, **kwargs)
		# egl: added the option of keeping the main form hidden
		# initially. The default behavior is for it to be shown, as usual.
		self.showMainFormOnStart = True
		self._wasSetup = False
		self._cryptoProvider = None
		# Track names of menus whose MRUs need to be persisted. Set
		# the key for each entry to the menu caption, and the value to
		# the bound function.
		self._persistentMRUs = {}
		# Create the temp file handlers.
		self._tempFileHolder = TempFileHolder()
		self.getTempFile = self._tempFileHolder.getTempFile
		# Create the framework-level preference manager
		self._frameworkPrefs = dabo.dPref(key="dabo_framework")

		# List of form classes to open on App Startup
		self.formsToOpen = []  
		# Form to open if no forms were passed as a parameter
		self.default_form = None

		# For simple UI apps, this allows the app object to be created
		# and started in one step. It also suppresses the display of
		# the main form.
		if selfStart:
			self.showMainFormOnStart = False
			self.setup()

		self._afterInit()
		self.autoBindEvents()
		

	def __del__(self):
		"""Make sure that temp files are removed"""
		self._tempFileHolder.release()
		

	def setup(self, initUI=True):
		"""Set up the application object."""
		# dabo is going to want to import various things from the Home Directory
		if self.HomeDirectory not in sys.path:
			sys.path.append(self.HomeDirectory)
		
		def initAppInfo(item, default):
			if not self.getAppInfo(item):
				self.setAppInfo(item, default)

		initAppInfo("appName", "Dabo Application")
		initAppInfo("appShortName", self.getAppInfo("appName").replace(" ", ""))
		initAppInfo("appVersion", "")
		initAppInfo("vendorName", "")

		self._initDB()
		
		if initUI:
			self._initUI()
			if self.UI is not None:
				if self.showSplashScreen:
					#self.uiApp = dabo.ui.uiApp(self, callback=self.initUIApp)
					self.uiApp = dabo.ui.getUiApp(self, callback=self.initUIApp)
				else:
					#self.uiApp = dabo.ui.uiApp(self, callback=None)
					self.uiApp = dabo.ui.getUiApp(self, callback=None)
					self.initUIApp()
		else:
			self.uiApp = None
		# Flip the flag
		self._wasSetup = True


	def startupForms(self):
		"""Open one or more of the defined forms. The default one is specified 
		in .default_form. If form names were passed on the command line, 
		they will be opened instead of the default one as long as they exist.
		"""
		form_names = [class_name[3:] for class_name in dir(self.ui) if class_name[:3] == "Frm"]
		for arg in sys.argv[1:]:
			arg = arg.lower()
			for form_name in form_names:
				if arg == form_name.lower():
					self.formsToOpen.append(getattr(self.ui, "Frm%s" % form_name))
		if not self.formsToOpen:
			self.formsToOpen.append(self.default_form)
		for frm in self.formsToOpen:
			frm(self.MainForm).show()

	def initUIApp(self):
		"""Callback from the initial app setup. Used to allow the 
		splash screen, if any, to be shown quickly.
		"""
		self.uiApp.setup()
		
	
	def start(self):
		"""Start the application event loop."""
		if not self._wasSetup:
			# Convenience; if you don't need to customize setup(), just
			# call start()
			self.setup()
			
		if (not self.SecurityManager or not self.SecurityManager.RequireAppLogin
			or self.SecurityManager.login()):
			
			userName = self.getUserCaption()
			if userName:
				userName = " (%s)" % userName
			else:
				userName = ""
			
			self._retrieveMRUs()
			self.uiApp.start(self)
		self.finish()
	
	
	def finish(self):
		"""Called when the application event loop has ended."""
		self._persistMRU()
		self.uiApp.finish()
		self.closeConnections()
		self._tempFileHolder.release()
		dabo.infoLog.write(_("Application finished."))


	def getLoginInfo(self, message=None):
		"""Return the user/password to dSecurityManager.login().

		The default is to display the standard login dialog, and return the 
		user/password as entered by the user, but subclasses can override to get
		the information from whereever is appropriate.

		Return a tuple of (user, pass).
		"""
		import dabo.ui.dialogs.login as login
		ld = login.Login(self.MainForm)
		ld.setMessage(message)
		ld.show()
		user, password = ld.user, ld.password
		return user, password
	
	
	def _persistMRU(self):
		"""Persist any MRU lists to disk."""
		base = "MRU.%s" % self.getAppInfo("appName")
		self.deleteAllUserSettings(base)		
		for cap in self._persistentMRUs.keys():
			mruList = self.uiApp.getMRUListForMenu(cap)
			setName = ".".join((base, cap))
			self.setUserSetting(setName, mruList)
	
	
	def _retrieveMRUs(self):
		"""Retrieve any saved MRU lists."""
		base = "MRU.%s" % self.getAppInfo("appName")
		for cap, fcn in self._persistentMRUs.items():
			itms = self.getUserSetting(".".join((base, cap)))
			if itms:
				# Should be a list of items. Add 'em in reverse order
				for itm in itms:
					self.uiApp.addToMRU(cap, itm, fcn)
		

	def getAppInfo(self, item):
		"""Look up the item, and return the value."""
		try:
			retVal = self._appInfo[item]
		except KeyError:
			retVal = None
		return retVal


	def setAppInfo(self, item, value):
		"""Set item to value in the appinfo table."""
		self._appInfo[item] = value


	def _currentUpdateVersion(self):
		localVers = dabo.version["revision"]
		try:
			localVers = localVers.split(":")[1]
		except:
			# Not a mixed version
			pass
		ret = int("".join([ch for ch in localVers if ch.isdigit()]))
		return ret

	
	def checkForUpdates(self, evt=None):
		"""Public interface to the web updates mechanism."""
		return self.uiApp.checkForUpdates(force=True)
		
		
	def _checkForUpdates(self, force=False):
		ret = False
		prf = self._frameworkPrefs
		val = prf.getValue
		runCheck = False
		now = datetime.datetime.now()
		if not force:
			webUpdate = val("web_update")
			if webUpdate:
				checkInterval = val("update_interval")
				if checkInterval is None:
					# Default to one day
					checkInterval = 24 * 60
				mins = datetime.timedelta(minutes=checkInterval)
				lastCheck = val("last_check")
				if lastCheck is None:
					lastCheck = datetime.datetime(1900, 1, 1)
				runCheck = (now > (lastCheck + mins))
		if runCheck:
			# See if there is a later version
			url = "http://dabodev.com/frameworkVersions/latest"
			try:
				vers = int(urllib.urlopen(url).read())
			except:
				vers = -1
			localVers = self._currentUpdateVersion()
			ret = localVers < vers
		prf.setValue("last_check", now)
		return ret


	def _updateFramework(self):
		"""Get any changed files from the dabodev.com server, and replace the local copies with them."""
		url = "http://dabodev.com/frameworkVersions/changedFiles/%s" % self._currentUpdateVersion()
		try:
			resp = urllib.urlopen(url)
		except:
			# No internet access, or Dabo site is down.
			return
		flist = eval(resp.read())
		basePth = os.path.split(dabo.__file__)[0]
		url = "http://dabodev.com/versions/dabo/%s"
		for mtype, fpth in flist:
			localFile = os.path.join(basePth, fpth)
			localPath = os.path.split(localFile)[0]
			if mtype == "D" and os.path.exists(localFile):
				if os.path.isdir(localFile):
					shutil.rmtree(localFile)
				else:
					os.remove(localFile)
			else:
				if not os.path.isdir(localPath):
					os.mkdirs(localPath)
				try:
					urllib.urlretrieve(url % fpth, localFile)
				except StandardError, e:
					dabo.errorLog.write(_("Cannot update file: '%s'. Error: %s") % (fpth, e))
		urllib.urlcleanup()
		

	def _setWebUpdate(self, auto, interval=None):
		"""Sets the web update settings for the entire framework. If set to True, the 
		interval is expected to be in minutes between checks.
		"""
		prf = self._frameworkPrefs
		prf.setValue("web_update", auto)
		if auto:
			if interval is None:
				# They want it checked every time
				interval = 0
			prf.setValue("update_interval", interval)
	
	
	def getWebUpdateInfo(self):
		"""Returns a 2-tuple that reflects the current settings for web updates.
		The first position is a boolean that reflects whether auto-checking is turned
		on; the second is the update frequency in minutes.
		"""
		return (self._frameworkPrefs.web_update, self._frameworkPrefs.update_interval)
		
		
	def getUserSettingKeys(self, spec):
		"""Return a list of all keys underneath <spec> in the user settings table.
		
		For example, if spec is "appWizard.dbDefaults", and there are
		userSettings entries for:
			appWizard.dbDefaults.pkm.Host
			appWizard.dbDefaults.pkm.User
			appWizard.dbDefaults.egl.Host
			
		The return value would be ["pkm", "egl"]
		"""
		usp = self.UserSettingProvider
		if usp:
			return usp.getUserSettingKeys(spec)
		return None


	def getUserSetting(self, item, default=None):
		"""Return the value of the item in the user settings table."""
		usp = self.UserSettingProvider
		if usp:
			return usp.getUserSetting(item, default)
		return None


	def setUserSetting(self, item, value):
		"""Persist a value to the user settings file."""
		usp = self.UserSettingProvider
		if usp:
			usp.setUserSetting(item, value)
	
	
	def setUserSettings(self, setDict):
		"""Convenience method for setting several settings with one
		call. Pass a dict containing {settingName: settingValue} pairs.
		"""
		usp = self.UserSettingProvider
		if usp:
			usp.setUserSettings(setDict)
	
	
	def deleteUserSetting(self, item):
		"""Removes the given item from the user settings file."""
		usp = self.UserSettingProvider
		if usp:
			usp.deleteUserSetting(item)
	
	
	def deleteAllUserSettings(self, spec):
		"""Deletes all settings that begin with the supplied spec."""
		usp = self.UserSettingProvider
		if usp:
			usp.deleteAllUserSettings(spec)
		
		
	def getUserCaption(self):
		""" Return the full name of the currently logged-on user."""
		if self.SecurityManager:
			return self.SecurityManager.UserCaption
		else:
			return None


	def str2Unicode(self, strVal):
		"""Given a string, this method will try to return a properly decoded
		unicode value. It will first try the default Encoding, and then try the
		more common encoding types.
		"""
		if not isinstance(strVal, basestring):
			strVal = strVal.__str__()
		if isinstance(strVal, unicode):
			return strVal
		ret = None
		try:
			ret = unicode(strVal, self.Encoding)
		except UnicodeDecodeError, e:
			# Try some common encodings:
			for enc in ("utf-8", "latin-1", "iso-8859-1"):
				if enc != self.Encoding:
					try:
						ret = unicode(strVal, enc)
						break
					except UnicodeDecodeError:
						continue
		if ret is None:
			# All attempts failed
			raise UnicodeDecodeError, e
		return ret


	# These two methods pass encryption/decryption requests
	# to the Crypto object
	def encrypt(self, val):
		"""Return the encrypted string value. The request is passed 
		to the Crypto object for processing.
		"""
		return self.Crypto.encrypt(val)
		

	def decrypt(self, val):
		"""Return decrypted string value. The request is passed to 
		the Crypto object for processing.
		"""
		return self.Crypto.decrypt(val)

	
	def getCharset(self):
		"""Returns one of 'unicode' or 'ascii'."""
		return self.uiApp.charset
		
		
	def _initProperties(self):
		""" Initialize the public properties of the app object."""
		self.uiType   = None    # ("wx", "qt", "curses", "http", etc.)
		#self.uiModule = None

		# Initialize UI collections
		self.uiForms = Collection()
		self.uiMenus = Collection()
		self.uiToolBars = Collection()
		self.uiResources = {}

		# Initialize DB collections
		self.dbConnectionDefs = {}
		self.dbConnectionNameToFiles = {}
		self.dbConnections = {}

		self._appInfo = {}
		super(dApp, self)._initProperties()

		
	def _initDB(self):
		"""Set the available connection definitions for use by the app. 

		First read in all .cnxml files. If no such XML definition files exist,
		check for a python code definition file named 'dbConnectionDefs.py'.
		"""
		connDefs = {}

		# Import any .cnxml files in HomeDir and/or HomeDir/db:
		for dbDir in (os.path.join(self.HomeDirectory, "db"), self.HomeDirectory):
			if os.path.exists(dbDir) and os.path.isdir(dbDir):
				files = glob.glob(os.path.join(dbDir, "*.cnxml"))
				for f in files:
					cn = importConnections(f)
					connDefs.update(cn)
					for kk in cn.keys():
						self.dbConnectionNameToFiles[kk] = f
		
		# Import any python code connection definitions (the "old" way).
		try:
			import dbConnectionDefs
			defs = dbConnectionDefs.getDefs()
			connDefs.update(defs)
			for kk in defs.keys():
				self.dbConnectionNameToFiles[kk] = os.abspath("dbConnectionDefs.py")
		except:
			pass
		
		# For each connection definition, add an entry to 
		# self.dbConnectionDefs that contains a key on the 
		# name, and a value of a dConnectInfo object.
		for k,v in connDefs.items():
			ci = dabo.db.dConnectInfo()
			ci.setConnInfo(v)
			self.dbConnectionDefs[k] = ci

		dabo.infoLog.write(_("%s database connection definition(s) loaded.") 
			% (len(self.dbConnectionDefs)))


	def _initUI(self):
		""" Set the user-interface library for the application. Ignored 
		if the UI was already explicitly set by user code.
		"""
		if self.UI is None and not self._uiAlreadySet:
			# For now, default to wx, but it should be enhanced to read an
			# application config file. Actually, that may not be necessary, as the
			# user's main.py can just set the UI directly now: dApp.UI = "qt".
			self.UI = "wx"
		else:
			# Custom app code or the dabo.ui module already set this: don't touch
			dabo.infoLog.write(_("User interface already set to '%s', so dApp didn't touch it.") 
					% self.UI)


	def getConnectionByName(self, connName):
		"""Given the name of a connection, returns the actual
		connection. Stores the connection so that multiple requests
		for the same named connection will not open multiple
		connections. If the name doesn't exist in self.dbConnectionDefs,
		then None is returned.
		"""
		if not self.dbConnections.has_key(connName):
			if self.dbConnectionDefs.has_key(connName):
				ci = self.dbConnectionDefs[connName]
				self.dbConnections[connName] = dabo.db.dConnection(ci)
		try:
			ret = self.dbConnections[connName]
		except KeyError:
			ret = None
		return ret
	
	
	def getConnectionNames(self):
		"""Returns a list of all defined connection names"""
		return self.dbConnectionDefs.keys()
		
		
	def closeConnections(self):
		"""Cleanup as the app is exiting."""
		for conn in self.dbConnections:
			try:
				conn.close()
			except:
				pass
	
	
	def addConnectInfo(self, ci, name=None):
		if name is None:
			try:
				name = ci.Name
			except:
				# Use a default name
				name = "%s@%s" % (ci.User, ci.Host)
		self.dbConnectionDefs[name] = ci
		self.dbConnectionNameToFiles[name] = None
	

	def addConnectFile(self, connFile):
		"""Accepts a cnxml file path, and reads in the connections
		defined in it, adding them to self.dbConnectionDefs.
		"""
		if not os.path.exists(connFile):
			homeFile = os.path.join(self.HomeDirectory, connFile)
			if os.path.exists(homeFile):
				connFile = homeFile
		if not os.path.exists(connFile):
			# Search sys.path for the file.
			for sp in sys.path:
				sysFile = os.path.join(sp, connFile)
				if os.path.exists(sysFile):
					connFile = sysFile
					break
		if os.path.exists(connFile):
			connDefs = importConnections(connFile)
			# For each connection definition, add an entry to 
			# self.dbConnectionDefs that contains a key on the 
			# name, and a value of a dConnectInfo object.
			for k,v in connDefs.items():
				ci = dabo.db.dConnectInfo()
				ci.setConnInfo(v)
				self.dbConnectionDefs[k] = ci
				self.dbConnectionNameToFiles[k] = connFile


	def setLanguage(self, lang, charset=None):
		"""Allows you to change the language used for localization. If the language
		passed is not one for which there is a translation file, an IOError exception
		will be raised. You may optionally pass a character set to use.
		"""
		dabo.dLocalize.setLanguage(lang, charset)

		
	def showCommandWindow(self, context=None):
		"""Shows a command window with a full Python interpreter.

		This is great for debugging during development, but you should turn off
		app.ShowCommandWindowMenu in production, perhaps leaving backdoor 
		access to this function.

		The context argument tells dShell what object becomes 'self'. If not
		passed, context will be app.ActiveForm.
		"""
		self.uiApp.showCommandWindow(context)


	def fontZoomIn(self, evt=None):
		"""Increase the font size on the active form."""
		self.uiApp.fontZoomIn()

	def fontZoomOut(self, evt=None):
		"""Decrease the font size on the active form."""
		self.uiApp.fontZoomOut()

	def fontZoomNormal(self, evt=None):
		"""Reset the font size to normal on the active form."""
		self.uiApp.fontZoomNormal()


	########################
	# This next section simply passes menu events to the UI
	# layer to be handled there.
	def onCmdWin(self, evt):
		self.uiApp.onCmdWin(evt)
	def onWinClose(self, evt):
		self.uiApp.onWinClose(evt)
	def onFileExit(self, evt):
		self.uiApp.onFileExit(evt)
	def onEditUndo(self, evt):
		self.uiApp.onEditUndo(evt)
	def onEditRedo(self, evt):
		self.uiApp.onEditRedo(evt)
	def onEditCut(self, evt):
		self.uiApp.onEditCut(evt)
	def onEditCopy(self, evt):
		self.uiApp.onEditCopy(evt)
	def onEditPaste(self, evt):
		self.uiApp.onEditPaste(evt)
	def onEditSelectAll(self, evt):
		self.uiApp.onEditSelectAll(evt)
	def onEditFind(self, evt):
		self.uiApp.onEditFind(evt)
	def onEditFindAlone(self, evt):
		self.uiApp.onEditFindAlone(evt)
	def onEditFindAgain(self, evt):
		self.uiApp.onEditFindAgain(evt)
	def onShowSizerLines(self, evt):
		self.uiApp.onShowSizerLines(evt)

	def onEditPreferences(self, evt):
		try:
			self.ActiveForm.onEditPreferences(evt)
		except:
			if self.PreferenceDialogClass:
				dlgPref = self.PreferenceDialogClass()
				dlgPref.show()
				if dlgPref.Modal:
					dlgPref.release()
			else:
				dabo.infoLog.write(_("Stub: dApp.onEditPreferences()"))

	# These handle MRU menu requests
	def addToMRU(self, menu, prmpt, bindfunc=None, *args, **kwargs):
		self.uiApp.addToMRU(menu, prmpt, bindfunc, *args, **kwargs)
	def onMenuOpenMRU(self, menu):
		self.uiApp.onMenuOpenMRU(menu)
	############################	
	
	
	def copyToClipboard(self, txt):
		"""Place the passed text onto the clipboard."""
		self.uiApp.copyToClipboard(txt)
		

	def onWebUpdatePrefs(self, evt):
		self.uiApp.onWebUpdatePrefs(evt)

	def showWebUpdatePrefs(self):
		self.onWebUpdatePrefs(None)		
		
	def onHelpAbout(self, evt):
		about = self.AboutFormClass
		if about is None:
			from dabo.ui.dialogs.htmlAbout import HtmlAbout as about
		frm = self.ActiveForm
		if frm is None:
			frm = self.MainForm
		if frm.MDI:
			# Strange big sizing of the about form happens on Windows
			# when the parent form is MDI.
			frm = None
		dlg = about(frm)
		dlg.show()
	
	
	def addToAbout(self):
		"""Adds additional app-specific information to the About form.
		This is just a stub method; override in subclasses if needed."""
		pass
	
	
	def clearActiveForm(self, frm):
		"""Called by the form when it is deactivated."""
		if frm is self.ActiveForm:
			self.uiApp.ActiveForm = None

	
	def _getAboutFormClass(self):
		return getattr(self, "_aboutFormClass", None)

	def _setAboutFormClass(self, val):
		self._aboutFormClass = val


	def _getActiveForm(self):
		if hasattr(self, "uiApp") and self.uiApp is not None:
			return self.uiApp.ActiveForm
		else:
			return None
			
	def _setActiveForm(self, frm):
		if hasattr(self, "uiApp") and self.uiApp is not None:
			self.uiApp._setActiveForm(frm)
		else:
			dabo.errorLog.write(_("Can't set ActiveForm: no uiApp."))
	

	def _getBasePrefKey(self):
		try:
			ret = self._basePrefKey
		except AttributeError:
			ret = self._basePrefKey = ""
		if not ret:
			try:
				ret = self.ActiveForm.BasePrefKey
			except: pass
		if not ret:
			try:
				ret = self.MainForm.BasePrefKey
			except: pass
		if not ret:
			dabo.infoLog.write(_("WARNING: No BasePrefKey has been set for this application."))
			try:
				f = inspect.stack()[-1][1]
				pth = os.path.abspath(f)
			except IndexError:
				# This happens in some Class Designer forms
				pth = os.path.join(os.getcwd(), sys.argv[0])
			if pth.endswith(".py"):
				pth = pth[:-3]
			pthList = pth.strip(os.sep).split(os.sep)
			ret = ".".join(pthList)
			ret = ret.decode(sys.getfilesystemencoding())
		return ret

	def _setBasePrefKey(self, val):
		super(dApp, self)._setBasePrefKey(val)


	def _getCrypto(self):
		if self._cryptoProvider is None:
			# Use the default crypto
			self._cryptoProvider = SimpleCrypt()
		return self._cryptoProvider

	def _setCrypto(self, val):
		self._cryptoProvider = val


	def _getDatabaseActivityLog(self):
		return dabo.dbActivityLog.LogObject

	def _setDatabaseActivityLog(self, val):
		if isinstance(val, basestring):
			try:
				f = open(val, "a")
			except:
				dabo.errorLog.write(_("Could not open file: '%s'") % val)
				return
		else:
			f = val
		dabo.dbActivityLog.LogObject = f


	def _getDrawSizerOutlines(self):
		return self.uiApp.DrawSizerOutlines
	
	def _setDrawSizerOutlines(self, val):
		self.uiApp.DrawSizerOutlines = val
	

	def _getEncoding(self):
		ret = locale.getlocale()[1]
		if ret is None:
			ret = dabo.defaultEncoding
		return ret
		

	def _getHomeDirectory(self):
		try:
			hd = self._homeDirectory
		except AttributeError:
			# Note: sometimes the runtime distros will alter the path so
			# that the first entry is not a valid directory. Go through the path
			# and use the first valid directory.
			hd = None
			for pth in sys.path:
				if os.path.exists(os.path.join(pth, ".")):
					hd = pth
					break
			if hd is None or len(hd.strip()) == 0:
				# punt:
				hd = os.getcwd()

			if os.path.split(hd)[1][-4:].lower() in (".zip", ".exe"):
				# mangle HomeDirectory to not be the py2exe library.zip file,
				# but the containing directory (the directory where the exe lives)
				hd = os.path.split(hd)[0]
			self._homeDirectory = hd			
		return hd
		
	def _setHomeDirectory(self, val):
		if os.path.exists(val):
			self._homeDirectory = os.path.abspath(val)
		else:
			raise ValueError, _("%s: Path does not exist.") % val


	def _getIcon(self):
		return getattr(self, "_icon", "daboIcon.ico")

	def _setIcon(self, val):
		self._icon = val

				
	def _getMainForm(self):
		try:
			frm = self._mainForm
		except AttributeError:
			frm = None
			self._mainForm = None
		return frm
			
	def _setMainForm(self, val):
		self.uiApp.setMainForm(val)
		self._mainForm = val

				
	def _getMainFormClass(self):
		try:
			cls = self._mainFormClass
		except AttributeError:
			cls = dabo.ui.dFormMain
			self._mainFormClass = cls
		return cls
			
	def _setMainFormClass(self, val):
		self._mainFormClass = val
		
		
	def _getNoneDisp(self):
		v = self._noneDisplay = getattr(self, "_noneDisplay", _("< None >"))
		return v

	def _setNoneDisp(self, val):
		assert isinstance(val, basestring)
		self._noneDisplay = val
		

	def _getPlatform(self):
		try:
			uiApp = self.uiApp
		except AttributeError:
			uiApp = None
		if uiApp is not None:
			return self.uiApp._getPlatform()
		else:
			return "?"


	def _getPreferenceDialogClass(self):
		return getattr(self, "_preferenceDialogClass", None)

	def _setPreferenceDialogClass(self, val):
		self._preferenceDialogClass = val


	def _getSearchDelay(self):
		try:
			return self._searchDelay
		except AttributeError:
			## I've found that a value of 300 isn't too fast nor too slow:
			# egl: 2006-11-16 - based on feedback from others, I'm 
			# 	lengthening this to 500 ms.
			return 500
			
	def _setSearchDelay(self, value):
		self._searchDelay = int(value)			

			
	def _getSecurityManager(self):
		try:
			return self._securityManager
		except AttributeError:
			return None
			
	def _setSecurityManager(self, value):
		if isinstance(value, dSecurityManager.dSecurityManager):
			if self.SecurityManager:
				warnings.warn(Warning, _("SecurityManager previously set"))
			self._securityManager = value
		else:
			raise TypeError, _("SecurityManager must descend from dSecurityManager.")
			
			
	def _getShowCommandWindowMenu(self):
		try:
			v = self._showCommandWindowMenu
		except AttributeError:
			v = self._showCommandWindowMenu = True
		return v
			
	def _setShowCommandWindowMenu(self, val):
		self._showCommandWindowMenu = bool(val)
			

	def _getShowSizerLinesMenu(self):
		try:
			v = self._showSizerLinesMenu
		except AttributeError:
			v = self._showSizerLinesMenu = True
		return v
			
	def _setShowSizerLinesMenu(self, val):
		self._showSizerLinesMenu = bool(val)

			
	def _getShowWebUpdateMenu(self):
		v = getattr(self, "_showWebUpdateMenu", None)
		if v is None:
			v = self._showWebUpdateMenu = True
		return v
			
	def _setShowWebUpdateMenu(self, val):
		self._showWebUpdateMenu = bool(val)


	def _getUI(self):
		try:
			return dabo.ui.getUIType()
		except AttributeError:
			return None
			
	def _setUI(self, uiType):
		# Load the appropriate ui module. dabo.ui will now contain
		# the classes of that library, wx for instance.
		if self.UI is None:
			if uiType is None:
				self._uiAlreadySet = True
				dabo.infoLog.write(_("User interface set set to None."))
			elif dabo.ui.loadUI(uiType):
				self._uiAlreadySet = True
				dabo.infoLog.write(_("User interface set to '%s' by dApp.") % uiType)
			else:
				dabo.infoLog.write(_("Tried to set UI to '%s', but it failed.") % uiType)
		else:
			raise RuntimeError, _("The UI cannot be reset once assigned.")

	
	def _getUserSettingProvider(self):
		try:
			ret = self._userSettingProvider
		except AttributeError:
			if self.UserSettingProviderClass is not None:
				ret = self._userSettingProvider = \
						self.UserSettingProviderClass()
			else:
				ret = self._userSettingProvider = None
		return ret
		
	def _setUserSettingProvider(self, val):
		self._userSettingProvider = val


	def _getUserSettingProviderClass(self):
		try:
			ret = self._userSettingProviderClass
		except AttributeError:
			ret = self._userSettingProviderClass = \
					dUserSettingProvider.dUserSettingProvider
		return ret

	def _setUserSettingProviderClass(self, val):
		self._userSettingProviderClass = val


	AboutFormClass = property(_getAboutFormClass, _setAboutFormClass, None,
			_("Specifies the form class to use for the application's About screen."))

	ActiveForm = property(_getActiveForm, _setActiveForm, None, 
			_("Returns the form that currently has focus, or None.  (dForm)" ) )
	
	BasePrefKey = property(_getBasePrefKey, _setBasePrefKey, None,
			_("""Base key used when saving/restoring preferences. This differs
			from the default definition of this property in that if it is empty, it 
			will return the ActiveForm's BasePrefKey or the MainForm's BasePrefKey
			in that order. (str)"""))
	
	Crypto = property(_getCrypto, _setCrypto, None, 
			_("Reference to the object that provides cryptographic services.  (varies)" ) )
	
	DatabaseActivityLog = property(_getDatabaseActivityLog, _setDatabaseActivityLog, None,
			_("""Path to the file (or file-like object) to be used for logging all database 
			activity. Default=None, which means no log is kept.   (file or str)"""))
	
	DrawSizerOutlines = property(_getDrawSizerOutlines, _setDrawSizerOutlines, None,
			_("Determines if sizer outlines are drawn on the ActiveForm.  (bool)"))
	
	Encoding = property(_getEncoding, None, None,
			_("Name of encoding to use for unicode  (str)") )
			
	HomeDirectory = property(_getHomeDirectory, _setHomeDirectory, None,
			_("""Specifies the application's home directory. (string)

			The HomeDirectory is the top-level directory for your application files,
			the directory where your main script lives. You never know what the 
			current directory will be on a given system, but HomeDirectory will always
			get you to your files."""))
		
	Icon = property(_getIcon, _setIcon, None,
			_("""Specifies the icon to use on all forms and dialogs by default.

			The value passed can be a binary icon bitmap, a filename, or a
			sequence of filenames. Providing a sequence of filenames pointing to
			icons at expected dimensions like 16, 22, and 32 px means that the
			system will not have to scale the icon, resulting in a much better
			appearance."""))

	MainForm = property(_getMainForm, _setMainForm, None,
			_("""The object reference to the main form of the application, or None.

			The MainForm gets instantiated automatically during application setup, 
			based on the value of MainFormClass. If you want to swap in your own
			MainForm instance, do it after setup() but before start(), as in:

			>>> import dabo
			>>> app = dabo.dApp()
			>>> app.setup()
			>>> app.MainForm = myMainFormInstance
			>>> app.start()"""))
		
	MainFormClass = property(_getMainFormClass, _setMainFormClass, None,
			_("""Specifies the class to instantiate for the main form. Can be a
			class reference, or the path to a .cdxml file.

			Defaults to the dFormMain base class. Set to None if you don't want a 
			main form, or set to your own main form class. Do this before calling
			dApp.start(), as in:

			>>> import dabo
			>>> app = dabo.dApp()
			>>> app.MainFormClass = MyMainFormClass
			>>> app.start()
			(dForm) """))
	
	NoneDisplay = property(_getNoneDisp, _setNoneDisp, None, 
			_("Text to display for null (None) values.  (str)") )
	
	Platform = property(_getPlatform, None, None,
			_("""Returns the platform we are running on. This will be 
			one of 'Mac', 'Win' or 'GTK'.  (str)""") )

	PreferenceDialogClass = property(_getPreferenceDialogClass, _setPreferenceDialogClass, None,
			_("""Specifies the dialog to use for the application's user preferences.

			If None, the application will try to run the active form's onEditPreferences()
			method, if any. Otherwise, the preference dialog will be instantiated and 
			shown when the user chooses to see the preferences."""))

	SearchDelay = property(_getSearchDelay, _setSearchDelay, None,
			_("""Specifies the delay before incrementeal searching begins.  (int)

				As the user types, the search string is modified. If the time between
				keystrokes exceeds SearchDelay (milliseconds), the search will run and 
				the search string	will be cleared.

				The value set here in the Application object will become the default for
				all objects that provide incremental searching application-wide.""") )
			
	SecurityManager = property(_getSecurityManager, _setSecurityManager, None, 
			_("""Specifies the Security Manager, if any. 

			You must subclass dSecurityManager, overriding the appropriate hooks 
			and properties, and then set dApp.SecurityManager to an instance of your 
			subclass. There is no security manager by default - you explicitly set 
			this to use Dabo security.""") )

	ShowCommandWindowMenu = property(_getShowCommandWindowMenu,
			_setShowCommandWindowMenu, None, 
			_("""Specifies whether the command window option is shown in the menu.

			If True (the default), there will be a File|Command Window option
			available in the base menu. If False, your code can still start the 
			command window by calling app.showCommandWindow() directly.""") )

	ShowSizerLinesMenu = property(_getShowSizerLinesMenu,
			_setShowSizerLinesMenu, None, 
			_("""Specifies whether the "Show Sizer Lines" option is shown in the menu.

			If True (the default), there will be a View|Show Sizer Lines option
			available in the base menu.""") )

	ShowWebUpdateMenu = property(_getShowWebUpdateMenu, _setShowWebUpdateMenu, None, 
			_("""Specifies whether the web update option is shown in the menu.

			If True, there will be a Web Update Options menu item in the Help menu. 
			If False (the default), your code can still start the Web Update Options
			screen by calling app.showWebUpdatePrefs() directly.""") )

	UI = property(_getUI, _setUI, None, 
			_("""Specifies the user interface to load, or None. (str)

			This is the user interface library, such as 'wx' or 'tk'. Note that
			'wx' is the only supported user interface library at this point."""))

	UserSettingProvider = property(_getUserSettingProvider, 
			_setUserSettingProvider, None,
			_("""Specifies the reference to the object providing user preference persistence.
			
			The default UserSettingProvider will save user preferences inside the .dabo
			directory inside the user's home directory."""))

	UserSettingProviderClass = property(_getUserSettingProviderClass,
			_setUserSettingProviderClass, None,
			_("""Specifies the class to use for user preference persistence.
			
			The default UserSettingProviderClass will save user preferences inside the .dabo
			directory inside the user's home directory, and will be instantiated by Dabo
			automatically."""))

