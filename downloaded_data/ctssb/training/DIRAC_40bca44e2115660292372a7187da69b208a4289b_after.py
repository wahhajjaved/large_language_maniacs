# $HeadURL$
__RCSID__ = "$Id$"

import sys
import os.path
from DIRAC.ConfigurationSystem.Client.LocalConfiguration import LocalConfiguration
from DIRAC.FrameworkSystem.Client.Logger import gLogger
from DIRAC.FrameworkSystem.Client.MonitoringClient import gMonitor

localCfg = LocalConfiguration()

scriptName = os.path.basename( sys.argv[0] )

def initAsScript( script = False ):
  global scriptName
  if script:
    scriptName = script
  scriptSection = localCfg.setConfigurationForScript( scriptName )

def parseCommandLine( script = False, ignoreErrors = False, initializeMonitor = False ):
  initialize( script, ignoreErrors, initializeMonitor, True )

def initialize( script = False, ignoreErrors = False, initializeMonitor = False, enableCommandLine = True ):
  global localCfg, scriptName

  userDisabled = not localCfg.isCSEnabled()
  if not userDisabled:
    localCfg.disableCS()

  if not enableCommandLine:
    localCfg.disableParsingCommandLine()

  if script:
    scriptName = script
  scriptSection = localCfg.setConfigurationForScript( scriptName )

  if not ignoreErrors:
    localCfg.addMandatoryEntry( "/DIRAC/Setup" )
  resultDict = localCfg.loadUserData()
  if not ignoreErrors and not resultDict[ 'OK' ]:
    gLogger.error( "There were errors when loading configuration", resultDict[ 'Message' ] )
    sys.exit( 1 )

  if not userDisabled:
    localCfg.enableCS()

  if initializeMonitor:
    gMonitor.setComponentType( gMonitor.COMPONENT_SCRIPT )
    gMonitor.setComponentName( scriptName )
    gMonitor.setComponentLocation( "script" )
    gMonitor.initialize()
  else:
    gMonitor.disable()

def registerSwitch( showKey, longKey, helpString, callback = False ):
  global localCfg
  localCfg.registerCmdOpt( showKey, longKey, helpString, callback )

def getPositionalArgs():
  global localCfg
  return localCfg.getPositionalArguments()

def getExtraCLICFGFiles():
  global localCfg
  return localCfg.getExtraCLICFGFiles()

def getUnprocessedSwitches():
  global localCfg
  return localCfg.getUnprocessedSwitches()

def addDefaultOptionValue( option, value ):
  global localCfg
  localCfg.addDefaultEntry( option, value )

def setUsageMessage( usageMessage ):
  global localCfg
  localCfg.setUsageMessage( usageMessage )

def disableCS():
  localCfg.disableCS()

def enableCS():
  return localCfg.enableCS()

def showHelp( text = False ):
  localCfg.showHelp( text )
