# Encoding: utf-8
# -----------------------------------------------------------------------------
# Project   : Reporter
# -----------------------------------------------------------------------------
# Author    : Sebastien Pierre                            <sebastien@ffctn.com>
# License   : BSD License                       <http://ffctn.com/licenses/bsd>
# -----------------------------------------------------------------------------
# Creation  : 21-Sep-2009
# Last mod  : 18-Feb-2016
# -----------------------------------------------------------------------------

import sys, smtplib, json, time, socket, types, string, collections

# TODO: Add info
# TODO: Add better message formatting

# Good error format
#
# [!] WARNING:-:module.Class.methodName:Your message (var=xx,var=xx)

#   CRITICAL = 50
#   DEBUG = 10
#   ERROR = 40
#   FATAL = 50
#   INFO = 20
#   NOTSET = 0
#   WARN = 30
#   WARNING = 30


# TODO: Mirror logging
LoggingInterface  = collections.namedtuple("LoggingInterface",(
	"debug", "trace", "info", "warning", "error", "fatal"
))

IS_REPORTER  = True
IS_INSTALLED = False

__version__ = "0.6.0"
__doc__ = """
The reporter module defines a simple interface to report errors that may occur
during program execution. Errors are composed of the following property:

 - 'message' which is the textual description of the error
 - 'component' which is the textual identifier for the component
 - 'code' which is the (optional) error code

Errors have three levels of severity:

 - 'warning'  which would be ''low severity''
 - 'error'    which would be ''medium severity''
 - 'fatal' which would be ''high severity''

The reporter module offers three main ways of reporting errors:

 - 'StderrReporter' which logs all the errors to stderrr (the default)
 - 'FileReporter' which logs all the errors to a file (which could be a named pipe
   if you want to process it to somewhere else).
 - 'SMTPReporter' which will send an email as soon as the error happens
 - 'XMPPReporter' which will send an instant message as soon as the error happens.

The main functions you'll use in this module are the following:

>    reporter.warning(message, component, code=None)
>    reporter.error(message, component, code=None)
>    reporter.fatal(message, component, code=None)

all of these functions will use the global 'reporter.REPORTER' instance, to which
you can 'register' more reporters. Here's for instance a setup where you'll report
errors both on stderr and on XMPP:

>    reporter.REPORTER.register(reporter.StderrReporter())
>    reporter.REPORTER.register(reporter.XMPPReporter('reporter@myserver.com','mypassword','admin@myserver.com'))

"""

DEBUG    = 0
TRACE    = 1
INFO     = 2
WARNING  = 3
ERROR    = 4
FATAL    = 5
DEFAULT_LEVEL = 2

COLOR_NONE         = -1
COLOR_BLACK        = 1
COLOR_RED          = 2
COLOR_GREEN        = 3
COLOR_BLUE         = 4
COLOR_MAGENTA      = 5
COLOR_CYAN         = 6
COLOR_BLACK_BOLD   = 11
COLOR_RED_BOLD     = 12
COLOR_GREEN_BOLD   = 13
COLOR_BLUE_BOLD    = 14
COLOR_MAGENTA_BOLD = 15
COLOR_CYAN_BOLD    = 16
COLOR_LIGHT_GRAY   = 17
COLOR_DARK_GRAY    = 18

# ------------------------------------------------------------------------------
#
# REPORTER
#
# ------------------------------------------------------------------------------

# FIXME: Should aggregate message when there's no delegate
class Reporter:
	"""Abstract class that defines the main (abstract) methods for an error
	reporter."""

	TEMPLATES = [
		"▶▶▶ {0}│{2}│{3}",
		"─── {0}│{2}│{3}",
		" ┈  {0}│{2}│{3}",
		"WRN {0}│{2}│{3}",
		"ERR {0}│{2}│{3}",
		"!!! {0}│{2}│{3}"
	]

	INSTANCE = None

	@classmethod
	def GetInstance( cls, *args ):
		if not cls.INSTANCE:
			cls.INSTANCE = cls(*args)
		return cls.INSTANCE

	@classmethod
	def Install( cls, *args ):
		l = cls.GetInstance(*args)
		register(l)
		return

	def __init__( self, level=None ):
		self.delegates = []
		self.setLevel(level if level is not None else DEFAULT_LEVEL)

	def setLevel( self, level ):
		self.level = level
		for _ in self.delegates:_.setLevel(level)
		return self

	def has( self, reporterClass ):
		for _ in self.delegates:
			if _.__class__ is reporterClass:
				return True
		return False

	def register( self, *reporters ):
		for reporter in reporters:
			if reporter not in self.delegates:
				reporter.level = self.level
				self.delegates.append(reporter)

	def unregister( self, *reporters ):
		for reporter in reporters:
			assert (reporter in self.delegates), "Reporter not registered as a delegate"
			self.delegates.remove(reporter)

	def timestamp( self ):
		return time.strftime("%Y-%m-%dT%H:%M:%S")

	def debug( self, message, component, code=None, color=None):
		if DEBUG >= self.level:
			self._send(DEBUG, self.TEMPLATES[DEBUG].format(self.timestamp(), code or "-", self._getComponent(component), message))
		return message

	def trace( self, message, component, code=None, color=None ):
		if TRACE >= self.level:
			self._send(TRACE, self.TEMPLATES[TRACE].format(self.timestamp(), code or "-", self._getComponent(component), message))
		return message

	def info( self, message, component, code=None, color=None ):
		"""Sends an info with the given message (as a string) and
		component (as a string)."""
		if INFO >= self.level:
			self._send(INFO, self.TEMPLATES[INFO].format(self.timestamp(), code or "-", self._getComponent(component), message), color=color)
		return message

	def warning( self, message, component, code=None, color=None):
		"""Sends a warning with the given message (as a string) and
		component (as a string)."""
		if WARNING >= self.level:
			self._send(WARNING, self.TEMPLATES[WARNING].format(self.timestamp(), code or "-", self._getComponent(component), message))
		return message

	def error( self, message, component, code=None, color=None ):
		"""Sends an error with the given message (as a string) and
		component (as a string)."""
		if ERROR >= self.level:
			self._send(ERROR, self.TEMPLATES[ERROR].format(self.timestamp(),code or "-", self._getComponent(component), message))
		return message

	def fatal( self, message, component, code=None, color=None ):
		"""Sends a fatal error with the given message (as a string) and
		component (as a string)."""
		if FATAL >= self.level:
			self._send(FATAL, self.TEMPLATES[FATAL].format(self.timestamp(), code or "-", self._getComponent(component), message))
		return message

	def _send( self, level, message, color=None ):
		self._forward(level, message, color=color )
		return message

	def _forward( self, level, message, color=None ):
		for delegate in self.delegates:
			delegate._send(level, message, color=color)
		return message

	def _getComponent( self, component ):
		if not component:
			return "-"
		elif isinstance(component, str):
			return component
		elif hasattr(component, "__name__"):
			return component.__name__
		else:
			return component.__class__.__name__

# ------------------------------------------------------------------------------
#
# FILE REPORTER
#
# ------------------------------------------------------------------------------

class FileReporter(Reporter):

	def __init__( self, path=None, fd=None, level=0 ):
		Reporter.__init__(self, level)
		if path:
			self.path = path
			self.fd   = None
		else:
			assert path is None
			assert not (fd is None)
			self.fd = fd

	def _send( self, level, message, color=None ):
		if self.level > level: return
		if self.fd is None:
			# We don't necessarily want this to be alway open
			with file(self.path, "a") as fd:
				fd.write(message + "\n")
				fd.flush()
		else:
			self.fd.write(message + "\n")
			self.fd.flush()

# ------------------------------------------------------------------------------
#
# CONSOLE REPORTER
#
# ------------------------------------------------------------------------------

class ConsoleReporter(FileReporter):

	def __init__( self, fd=None, level=0, color=True ):
		if fd is None: fd = sys.stdout
		FileReporter.__init__(self, fd=fd, level=level)
		self.color        = color
		self.colorByLevel = [
			COLOR_CYAN_BOLD,     # DEBUG
			COLOR_LIGHT_GRAY,    # TRACE
			COLOR_NONE,          # INFO
			COLOR_MAGENTA_BOLD,  # WARNING
			COLOR_RED,           # ERROR
			COLOR_RED_BOLD,      # FATAL
		]

	def _send( self, level, message , color=None):
		color = color or self.getColorForLevel(level)
		FileReporter._send(self, level, self._colorStart(color) + message + self._colorEnd(color))

	def getColorForLevel( self, level ):
		level = max(0, min(level, len(self.colorByLevel)))
		return self.colorByLevel[level]

	def _colorStart( self, color ):
		# SEE: http://tldp.org/HOWTO/Bash-Prompt-HOWTO/x329.html
		if not self.color: return ''
		if   color==COLOR_NONE:
			return ''
		elif color==COLOR_LIGHT_GRAY:
			return ('[0m[00;37m')
		elif color==COLOR_DARK_GRAY:
			return ('[0m[01;30m')
		elif color==COLOR_BLACK:
			return ('[0m[00;30m')
		elif color==COLOR_BLACK_BOLD:
			return ('[0m[01;30m')
		elif color==COLOR_RED:
			return ('[0m[00;31m')
		elif color==COLOR_RED_BOLD:
			return ('[0m[01;31m')
		elif color==COLOR_GREEN:
			return ('[0m[00;32m')
		elif color==COLOR_GREEN_BOLD:
			return ('[0m[01;32m')
		elif color==COLOR_BLUE:
			return ('[0m[00;34m')
		elif color==COLOR_BLUE_BOLD:
			return ('[0m[01;34m')
		elif color==COLOR_MAGENTA:
			return ('[0m[00;35m')
		elif color==COLOR_MAGENTA_BOLD:
			return ('[0m[01;35m')
		elif color==COLOR_CYAN:
			return ('[0m[00;35m')
		elif color==COLOR_CYAN_BOLD:
			return ('[0m[01;35m')
		else:
			raise Exception("ConsoleReporter._colorStart: Unsupported color", color)

	def _colorEnd( self, color ):
		if self.color and color != COLOR_NONE:
			return ('[0m')
		else:
			return ''

# ------------------------------------------------------------------------------
#
# STDERR REPORTER
#
# ------------------------------------------------------------------------------

class StderrReporter(ConsoleReporter):

	def __init__( self, level=0, color=True ):
		ConsoleReporter.__init__(self, fd=sys.stderr, level=level, color=color)

# ------------------------------------------------------------------------------
#
# STDOUT REPORTER
#
# ------------------------------------------------------------------------------

class StdoutReporter(ConsoleReporter):

	def __init__( self, level=0, color=True ):
		ConsoleReporter.__init__(self, fd=sys.stdout, level=level, color=color)

# ------------------------------------------------------------------------------
#
# SMTP REPORTER
#
# ------------------------------------------------------------------------------

class SMTPReporter(Reporter):
	"""Sends an email"""

	MESSAGE = """\
	|From: ${from}
	|To:   ${to}
	|Subject: ${subject}
	|
	|level: ${level}
	|${message}
	|--
	|Timestamp: ${timestamp}
	|--
	""".replace("\t|", "")

	def __init__( self, recipient, user=None, password=None, origin=None, host="localhost", level=0 ):
		Reporter.__init__(self, level=level)
		self.host      = host
		self.recipient = recipient
		self.origin    = origin or "reporter@%s" % (host)
		self.user      = user
		self.password  = password

	def send(self, message, subject=None):
		server = smtplib.SMTP(self.host)
		email  = string.Template(self.MESSAGE).safe_substitute({
			"from": self.origin,
			"to": self.recipient,
			"subject": subject,
			"message": message,
			"level"  : self.level,
			"timestamp": self.timestamp(),
		})
		server.ehlo()
		server.starttls()
		server.ehlo()
		if self.password:
			server.login(self.user, self.password)
		server.sendmail(self.origin, self.recipient, email)
		try:
			server.quit()
		except:
			pass
		return email

	def _send( self, level, message ):
		self.send(message, "[!][%s]FF-Collector: %s" % (level, message[:30]))

# ------------------------------------------------------------------------------
#
# XMPP REPORTER
#
# ------------------------------------------------------------------------------

class XMPPReporter(Reporter):

	def __init__( self, fromName, fromPassword, toUser, level=0 ):
		Reporter.__init__(self, level=level)
		self.name       = fromName
		self.password   = fromPassword
		self.recipients = toUser
		self._sendMessage = None
		try:
			self._sendMessage = pyxmpp2.simple.send_message
		except ImportError as e:
			raise Exception("PyXMPP2 Module is required for Jabber reporting")

	def _send( self, level, message, color=None ):
		for recipient in self.recipients:
			iself._sendMessage(self.name, self.password, recipient, message)

# ------------------------------------------------------------------------------
#
# BEANSTALK REPORTER
#
# ------------------------------------------------------------------------------

class BeanstalkReporter(Reporter):
	"""Allows to send jobs on the Beanstalkd work queue, that could later be
	processed by a BeanstalkWorker."""

	def __init__( self, host="0.0.0.0", port=11300, tube="report", level=0 ):
		Reporter.__init__(self, level=level)
		self.host = host
		self.port = port
		self.tube = tube
		self.beanstalk = None
		try:
			self.connect()
		except socket.error as e:
			print ("[!] BeanstalkWorker cannot connect to beanstalkd server")

	def connect( self ):
		import beanstalkc
		self.beanstalkc = beanstalkc
		self.beanstalk  = self.beanstalkc.Connection(host=self.host, port=self.port)
		self.beanstalk.use(self.tube)

	def _send( self, level, message, color=None ):
		if self.beanstalk:
			self.beanstalk.put(json.dumps({
				"type"    : "reporter.Message",
				"message" : message,
				"level"   : level,
			}))
		else:
			print ("[!] BeanstalkWorker cannot connect to beanstalkd server")

# ------------------------------------------------------------------------------
#
# BEANSTALK WORKER
#
# ------------------------------------------------------------------------------

class BeanstalkWorker:
	"""Processes report jobs posted through Beanstalkd."""

	def __init__( self, host="0.0.0.0", port=11300, tube="report" ):
		import beanstalkc
		self.beanstalkc = beanstalkc
		self.beanstalk  = beanstalkc.Connection(host=host, port=port)
		self.beanstalk.watch(tube)
		self.beanstalk.ignore("default")
		self.isRunning = False

	def start( self ):
		self.isRunning = True
		self.run()

	def stop( self ):
		self.isRunning = False

	def run( self ):
		while self.isRunning:
			self._iterate()

	def _iterate( self ):
		try:
			job  = self.beanstalk.reserve()
		except (self.beanstalkc.DeadlineSoon, self.beanstalkc.CommandFailed, self.beanstalkc.UnexpectedResponse) as e:
			reporter.error(str(e), "beanstalkc")
			return False
		# We make sure that the job is JSON
		try:
			data = json.loads(job.body)
		except:
			job.release()
			return False
		if not data or not (type(data) is dict) or not (data.get("type") == "reporter.Message"):
			return False
		else:
			self._process(data, job)
			return True

	def _process( self, message, job ):
		REPORTER._send( message["level"], message["message"] )
		job.delete()

# ------------------------------------------------------------------------------
#
# MODULE GLOBALES AND FUNCTIONS
#
# ------------------------------------------------------------------------------

REPORTER = Reporter()

def register( *reporter, **options ):
	"""Registers the reporter instance(s) in the `REPORTER` singleton."""
	res    = []
	unique = True if "unique" not in options else options.get("unique")
	if "level" in options: setLevel(options["level"])
	for _ in reporter:
		if (not unique) or (not REPORTER.has(_.__class__)):
			res.append(REPORTER.register(_))
	return REPORTER

def unregister( *reporter ):
	"""Unegisters the reporter instance(s) in the `REPORTER` singleton."""
	return REPORTER.unregister(*reporter)

def setLevel( l ):
	REPORTER.setLevel(l)
	return REPORTER

def install( channel=None, level=TRACE ):
	global IS_INSTALLED
	if not IS_INSTALLED:
		IS_INSTALLED = True
		if channel in (sys.stderr, "stderr", "err"): channel = StderrReporter()
		return register(channel or StdoutReporter()).setLevel(level)
	else:
		return REPORTER.setLevel(level)


def debug( message, component=None, code=None, color=None ):
	return REPORTER.debug(message, component, code, color=color)

def trace( message, component=None, code=None, color=None  ):
	return REPORTER.trace(message, component, code, color=color)

def info( message, component=None, code=None, color=None ):
	return REPORTER.info(message, component, code, color=color)

def warning( message, component=None, code=None, color=None  ):
	return REPORTER.warning(message, component, code, color=color)

def warn( message, component=None, code=None, color=None  ):
	return REPORTER.warning(message, component, code, color=color)

def error( message, component=None, code=None, color=None  ):
	return REPORTER.error(message, component, code, color=color)

def fatal( message, component=None, code=None, color=None  ):
	return REPORTER.fatal(message, component, code, color=color)

def bind( component, name=None):
	"""Returns `(debug,trace,info,warning,error,fatal)` functions that take `(message,code=None)`
	as parameters. This should be used in the following way, at the head of a
	module:

	>    debug, trace, info, warning, error, fatal = reporter.bind("mymodule")

	and then

	>    info("Hello, world!")
	"""
	if   type(component) in (types.InstanceType,):
		(component.debug,
		component.trace,
		component.info,
		component.warning,
		component.error,
		component.fatal) = bind(name or component.__class__.__name__)
	elif type(component) in (str, unicode):
		def wrap(function):
			def _(*args,**kwargs):
				function(" ".join(map(str,args)), component, code=kwargs.get("code"), color=kwargs.get("color"))
			return _
		return LoggingInterface(
			wrap(debug),
			wrap(trace),
			wrap(info),
			wrap(warning),
			wrap(error),
			wrap(fatal)
		)
	else:
		raise Exception("reporter.bind: Unsupported type: %s" % (type(component)))

if not IS_INSTALLED:
	install()

if __name__ == "__main__":
	register(ConsoleReporter(), unique=True)
	debug("DEBUG")
	trace("TRACE")
	info("INFO")
	warning("WARNING")
	error("ERROR")
	fatal("FATAL")

# EOF - vim: ts=4 sw=4 noet
