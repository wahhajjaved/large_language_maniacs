# -*- coding: utf-8 -*-
#  This software and supporting documentation are distributed by
#      Institut Federatif de Recherche 49
#      CEA/NeuroSpin, Batiment 145,
#      91191 Gif-sur-Yvette cedex
#      France
#
# This software is governed by the CeCILL license version 2 under
# French law and abiding by the rules of distribution of free software.
# You can  use, modify and/or redistribute the software under the
# terms of the CeCILL license version 2 as circulated by CEA, CNRS
# and INRIA at the following URL "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license version 2 and that you accept its terms.
"""
This module contains classes defining Brainvisa **processes and pipelines**.

The main class in this module is :py:class:`Process`. It is the base class for all Brainvisa processes. It inherits from the class :py:class:`Parameterized` that defines an object with a list of parameters that we call a signature.
When the processes are loaded at Brainvisa startup, information about them is stored in :py:class:`ProcessInfo` objects.

Several functions are available in this module to get information about the processes or to get instances of the processes:
  * :py:func:`getProcessInfo`
  * :py:func:`allProcessesInfo`
  * :py:func:`getProcess`
  * :py:func:`getProcessInstance`
  * :py:func:`getProcessInstanceFromProcessEvent`
  * :py:func:`getProcessFromExecutionNode`
  * :py:func:`getConverter`
  * :py:func:`getConvertersTo`
  * :py:func:`getConvertersFrom`
  * :py:func:`getViewer`
  * :py:func:`runViewer`
  * :py:func:`getDataEditor`
  * :py:func:`getImporter`
To modify, the lists of processes, several functions are also available:
  * :py:func:`addProcessInfo`
  * :py:func:`readProcess`
  * :py:func:`readProcesses`
  
  
A pipeline is defined as a specific process that has an execution node that describes the pipeline structure. The base class for execution nodes is :py:class:`ExecutionNode`. This class is specialized into several other classes, defining different types of pipelines:
  * :py:class:`ProcessExecutionNode`: only one process
  * :py:class:`SerialExecutionNode`: a list of execution nodes that have to be executed serially.
  * :py:class:`ParallelExecutionNode`: a list of execution nodes that can be executed in parallel.
  * :py:class:`SelectionExecutionNode`: a choice between several execution nodes.
  
Specialized Process classes that use the different types of execution nodes also exist:
  * :py:class:`IterationProcess`: an iteration of a process on a set of data. Uses a :py:class:`ParallelExecutionNode`.
  * :py:class:`ListOfIterationProcess`
  * :py:class:`DistributedProcess`: a pipeline that have a :py:class:`ParallelExecutionNode`
  * :py:class:`SelectionProcess`: a pipeline that have a :py:class:`SelectionExecutionNode`.
  
As processes can be run in different contexts, an object representing this context is passed as a parameter in the processes execution function. This object is an intance of the class :py:class:`ExecutionContext`. A default context associated to the application also exists, to get it use the function :py:func:`defaultContext`.

After loading, Brainvisa processes are stored in an object :py:class:`ProcessTrees` that represents the processes organization in toolboxes and categories. The function :py:func:`updatedMainProcessTree` creates this object if it doesn't exist yet and to returns it.

:Inheritance diagram:

.. inheritance-diagram:: Parameterized Process ExecutionNode SerialExecutionNode ProcessExecutionNode SelectionExecutionNode ParallelExecutionNode ProcessInfo ExecutionContext IterationProcess SelectionProcess DistributedProcess ListOfIterationProcess ProcessTree ProcessTrees

  
:Classes:
  
.. autoclass:: Parameterized
  :show-inheritance:
    
.. autoclass:: Process
  :show-inheritance:

.. autoclass:: ProcessInfo
  :members:
  :show-inheritance:
    
.. autoclass:: ExecutionNode
  :members:
  :show-inheritance:
    
.. autoclass:: ProcessExecutionNode
  :members:
  :show-inheritance:
    
.. autoclass:: SerialExecutionNode
  :members:
  :show-inheritance:
    
.. autoclass:: ParallelExecutionNode
  :members:
  :show-inheritance:

.. autoclass:: SelectionExecutionNode
  :members:
  :show-inheritance:

.. autoclass:: IterationProcess
  :members:
  :show-inheritance:
    
.. autoclass:: ListOfIterationProcess
  :members:
  :show-inheritance:
    
.. autoclass:: DistributedProcess
  :members:
  :show-inheritance:

.. autoclass:: SelectionProcess
  :members:
  :show-inheritance:

.. autoclass:: ExecutionContext
  :members:
  :show-inheritance:
    
.. autoclass:: ProcessTree
  :members:
   
.. autoclass:: ProcessTrees
  :members:
  :show-inheritance:

:Functions:
  
.. autofunction:: getProcessInfo
.. autofunction:: allProcessesInfo
.. autofunction:: getProcess
.. autofunction:: getProcessInstance
.. autofunction:: getProcessInstanceFromProcessEvent
.. autofunction:: getProcessFromExecutionNode
.. autofunction:: getConverter
.. autofunction:: getConvertersTo
.. autofunction:: getConvertersFrom
.. autofunction:: getViewer
.. autofunction:: runViewer
.. autofunction:: getDataEditor
.. autofunction:: getImporter
.. autofunction:: addProcessInfo
.. autofunction:: readProcess
.. autofunction:: readProcesses
.. autofunction:: updatedMainProcessTree
.. autofunction:: allProcessesTree
.. autofunction:: updateProcesses
.. autofunction:: mainThread
.. autofunction:: defaultContext
.. autofunction:: initializeProcesses
.. autofunction:: cleanupProcesses

"""
__docformat__ = 'restructuredtext en'

import traceback, threading, pickle, formatter, htmllib, operator
import inspect, signal, shutil, imp, StringIO, types, copy, weakref
import cPickle
import string
import distutils.spawn
import os, errno, time, calendar

from soma.sorted_dictionary import SortedDictionary
from soma.functiontools import numberOfParameterRange, hasParameter
from soma.minf.api import readMinf, writeMinf, createMinfWriter, iterateMinf, minfFormat
from soma.minf.xhtml import XHTML
from soma.minf.xml_tags import xhtmlTag
from soma.notification import EditableTree, ObservableSortedDictionary, \
                              ObservableAttributes, Notifier
from soma.minf.api import createMinfWriter, iterateMinf, minfFormat
from soma.html import htmlEscape
from soma.somatime import timeDifferenceToString
from soma.path import relative_path

from brainvisa.data.neuroData import *
from brainvisa.data.neuroDiskItems import *
from brainvisa.data.readdiskitem import ReadDiskItem
from brainvisa.data.writediskitem import WriteDiskItem
from brainvisa.configuration import neuroConfig
from brainvisa.data import neuroDiskItems
from brainvisa.processing import neuroLog
from brainvisa.processing.neuroException import *
from brainvisa.validation import ValidationError
from brainvisa.debug import debugHere
from brainvisa.data.sqlFSODatabase import Database, NotInDatabaseError
import brainvisa.toolboxes
from brainvisa.data import fileSystemOntology
from brainvisa.processing.qtgui.backwardCompatibleQt import QProcess
from brainvisa.processing.qtgui.command import CommandWithQProcess as Command
from soma import safemkdir


#----------------------------------------------------------------------------
def pathsplit( path ):
  '''Returns a tuple corresponding to a recursive call to os.path.split
  for example on Unix:
     pathsplit( 'toto/titi/tata' ) == ( 'toto', 'titi', 'tata' )
     pathsplit( '/toto/titi/tata' ) == ( '/', 'toto', 'titi', 'tata' )'''
  if isinstance( path, basestring ):
    if path:
      return pathsplit( ( path, ) )
    else:
      return ()
  else:
    if path[0]:
      d,b = os.path.split( path[0] )
      if b:
        if d:
          return pathsplit( d ) + (b,) + path[1:]
        else:
          return (b,) + path[1:]
      else:
          return (d,) + path[1:]

#----------------------------------------------------------------------------
def getProcdocFileName( processId ):
  """
  Returns the name of the file (.procdoc) that contains the documentation of the process in parameter.
  """
  processInfo = getProcessInfo( processId )
  fileName = getattr( processInfo, 'fileName', None )
  if fileName is None:
    return None

  newFileName = os.path.join( os.path.dirname( fileName ),
                              processInfo.id + ".procdoc" )
  return newFileName

#----------------------------------------------------------------------------
def readProcdoc( processId ):
  """
  Returns the content of the documentation file (.procdoc) of the process in parameter.
  """
  processInfo = getProcessInfo( processId )
  if processInfo is not None:
    procdoc = processInfo.procdoc
    if procdoc is None:
      fileName = getProcdocFileName( processInfo )
      if fileName and os.path.exists( fileName ):
        try:
          procdoc = readMinf( fileName )[ 0 ]
        except:
          print '!Error in!', fileName
          raise
      else:
        procdoc = {}
      processInfo.procdoc = procdoc
  else:
    procdoc = {}
  return procdoc


#----------------------------------------------------------------------------
def writeProcdoc( processId, documentation ):
  """
  Writes the ``documentation`` in the process documentation file (.procdoc).
  """
  fileName = getProcdocFileName( processId )
  if not os.path.exists( fileName ):
    processInfo = getProcessInfo( processId )
    procFileName = getattr( processInfo, 'fileName', None )
    procSourceFileName = os.path.realpath( procFileName )
    # take care of keeping the .procdoc in the same location as the .py,
    # whatever symlinks
    if os.path.islink( procFileName ) and procFileName != procSourceFileName:
      sourceFileName = os.path.join( os.path.dirname( procSourceFileName ),
        os.path.basename( fileName ) )
      os.symlink( sourceFileName, fileName )
      fileName = sourceFileName
  writeMinf( fileName, ( documentation, ) )


#----------------------------------------------------------------------------
def procdocToXHTML( procdoc ):
  """
  Converts HTML tags in the content of a .procdoc file to XHTML tags.
  Checks its syntax.
  """
  stack = [ (procdoc, key, key ) for key in procdoc.iterkeys() ]
  while stack:
    d, k, h = stack.pop()
    value = d[ k ]
    if isinstance( value, types.StringTypes ):
      # Convert HTML tags to XML valid tags

      # Put all tags in lower-case because <TAG> ... </tag> is illegal XML
      def lowerTag( x ):
        result = '<' + x.group(1).lower() + x.group(2)
        return result
      value = re.sub( '<(/?[A-Za-z_][a-zA-Z_0-9]*)(>|[^a-zA-Z_0-9][^>]*>)',
                        lowerTag, value )

      # Add a '/' at the end of non closed tags
      for l in ( 'img', 'br', 'hr' ):
        expr = '<(' + l + '(([^A-Za-z_0-9>/]?)|([^A-Za-z_0-9][^>]*[^/>])))>(?!\s*</' + l + '>)'
        value = re.sub( expr, '<\\1/>', value )

      # convert <s> tag to <xhtml> tag
      value = re.sub( '<(/?)s(>|[^a-zA-Z_0-9][^>]*>)', '<\\1' + xhtmlTag + '\\2', value )

      goOn = True
      while goOn:
        goOn = False
        try:
          newValue = XHTML.buildFromHTML( value )
        except Exception, e:
          # Build a text editor
          from soma.qt4gui.designer import loadUi
          from PyQt4 import QtGui, QtCore
          editor = loadUi( os.path.join( mainPath, '..', 'python', 'brainvisa', 'textEditor.ui' ) )
          #editor.setAttribute( QtCore.Qt.WA_DeleteOnClose, True )
          def f():
            l = editor.content.textCursor().blockNumber()
            c = editor.content.textCursor().columnNumber()
            editor.cursorPosition.setText( str( l+2 ) + ' : ' + str( c ) )
          editor.info.setText( '<h2><font color="red">Error in ' + h + ':<br>  ' + str(e) + '</font></h1>' )
          editor.content.setAcceptRichText( False )
          editor.content.setPlainText( value )
          editor.connect( editor.content, SIGNAL( 'cursorPositionChanged()' ), f )
          editor.btnOk.setText( 'Check and save as XHTML' )
          editor.btnCancel.setText( 'Save as simple text' )
          line = getattr( e, 'getLineNumber', None )
          if line is not None:
            line = line() - 2
          else:
            line = 0
          column = getattr( e, 'getColumnNumber', None )
          if column is not None:
            column = column()
          else:
            column = 0
          if line == 0 and column == 0:
            x = re.match( '^[^0-9]*:([0-9]+):([0-9]+):', str(e) )
            print x
            print str(e)
            if x:
              line = int( x.group(1) ) - 3
              column = int( x.group(2) ) # it's not the column !
              # (maybe the XML tag number ?)
          editor.content.moveCursor( QtGui.QTextCursor.Start )
          for i in xrange( line - 1 ):
            editor.content.moveCursor( QtGui.QTextCursor.NextBlock )
          #for i in xrange( column - 1 ):
            #editor.content.moveCursor( QtGui.QTextCursor.Right )
          if editor.exec_() == QDialog.Accepted:
            value = unicode( editor.content.toPlainText() )
            goOn = True
          else:
            newValue = unicode( editor.content.toPlainText() )
            goOn = False
      d[ k ] = newValue
    elif type( value ) is types.DictType:
      stack += [ ( value, key, h + '.' + key ) for key in value.iterkeys() ]


#----------------------------------------------------------------------------
def getHTMLFileName( processId, documentation=None, language=None ):
  """
  Gets the path to the html page corresponding to the documentation of the process in parameter.
  """
  processInfo = getProcessInfo( processId )
  if documentation is None:
    documentation = readProcdoc( processId )
  if language is None:
    language = neuroConfig.language
  htmlPath=XHTML.html(documentation.get( 'htmlPath', ''))
  if htmlPath:
    defaultPath=htmlPath
  else:
    defaultPath = os.path.dirname( neuroConfig.docPath )
  return os.path.join( defaultPath, language, 'processes',
                       string.replace( processInfo.id, ' ', '_' ) + '.html' )

#----------------------------------------------------------------------------
def convertSpecialLinks( msg, language, baseForLinks, translator ):
  """
  Converts special links and tags in a procdoc documentation.
  The possible special links or tags are:
  
  * *bvcategory://* refers to the documentation of a processes category (directory containing processes).
  * *bvprocess://* refers to the documentation of a process
  * *bvimage://* refers to an image in Brainvisa images directory
  * *<_t_>* translates the string in the selected language 
  * *<bvprocessname name=""> replaces the id by the name of the process
  
  """
  stack = [ msg ]
  while stack:
    item = stack.pop()
    if isinstance( item, XHTML ):# and \
      stack += item.content
      tag = item.tag
      if not tag: continue
      tag = tag.lower()
      if tag == 'a':
        href = item.attributes.get( 'href' )
        if href is not None:
          i = href.find( '#' )
          if i >= 0:
            postHref = href[ i: ]
            href = href[ :i ]
          else:
            postHref = ''
          if not href: continue
          if href.startswith( 'bvcategory://' ):
            href = href[ 13: ]
            if href.startswith( '/' ):
              href = href[ 1: ]
            if baseForLinks:
              base = baseForLinks + '/categories/'
            else:
              base = 'categories/'
            href = base + href.lower() + '/category_documentation.html'
            item.attributes[ 'href' ] = href + postHref
          elif href.startswith( 'bvprocess://' ):
            href = href[ 12: ]
            if href.startswith( '/' ):
              href = href[ 1: ]
            if baseForLinks:
              href = baseForLinks + '/' + href
            href += '.html'
            item.attributes[ 'href' ] = href + postHref
          elif href.startswith( 'bvimage://' ):
            href = href[ 10: ]
            if href.startswith( '/' ):
              href = href[ 1: ]
            if baseForLinks:
              href = baseForLinks + '/../../images/' + href
            else:
              href = '../../images/' + href
            item.attributes[ 'href' ] = href
      elif tag == 'img':
        src = item.attributes.get( 'src', '' )
        if not src: continue
        elif src.startswith( 'bvimage://' ):
          src = src[ 10: ]
          if src.startswith( '/' ):
            src = src[ 1: ]
          if baseForLinks:
            src = baseForLinks + '/../../images/' + src
          else:
            src = '../../images/' + src
          item.attributes[ 'src' ] = src
      elif tag == '_t_':
        item.tag = None
        item.content = ( translator.translate( item.content[0] ), )
      elif tag == 'bvprocessname':
        item.tag = None
        try:
          n = getProcessInfo( item.attributes[ 'name' ] ).name
        except:
          n = item.attributes[ 'name' ]
        item.content = ( translator.translate( n, ) )
  return msg



#----------------------------------------------------------------------------
def generateHTMLProcessesDocumentation( procId = None ):
  """
  Generates HTML pages for the documentation of the process in parameter or for all processes if `procId` is None.
  The process generateDocumentation is used. 
  """
  if procId is None:
    defaultContext().runProcess("generateDocumentation")
  else:
    docproc = getProcessInstance( 'generateDocumentation' )
    translators = {}
    for l in neuroConfig._languages:
      translators[ l ] = neuroConfig.Translator( l )
    ontology = 'all'
    docproc.generateHTMLDocumentation( procId, translators, defaultContext(),
      ontology )

#----------------------------------------------------------------------------
def mapValuesToChildrenParameters(destNode, sourceNode, dest, source, value = None, defaultProcess = None, defaultProcessOptions = {}, name=None):
  sourceObject, sourceParameter = sourceNode.parseParameterString( source )
  l = getattr(sourceObject, sourceParameter, [])
  lsize = len(l)
  csize = len(destNode.childrenNames())
  initcsize = csize
  
  # Resulting size is the max between children size and list size
  rsize = max(csize, lsize)

  for i in xrange(rsize):
    if i == csize:
      if defaultProcess :
        # Add a newc child node
        child = brainvisa.processes.ProcessExecutionNode( 
                  defaultProcess,
                  optional = defaultProcessOptions.get('optional', True), 
                  selected = defaultProcessOptions.get('selected', True), 
                  expandedInGui = defaultProcessOptions.get('expandedInGui', False)
                )
        destNode.addChild(name=name, node = child)
        
      csize += 1

      
    if i < lsize :
      v = l[i]
    else :
      v = None
    
    # Set node value
    k = destNode.childrenNames()[i]
    destChild = destNode._children[k]
    destObject, destParameter = destChild.parseParameterString( dest )
    setattr(destObject, destParameter, v)
    
    i += 1
    
#----------------------------------------------------------------------------
def mapChildrenParametersToValues(destNode, sourceNode, dest, source, value = None):
  r = []
  for k in sourceNode.childrenNames():
    sourceChild = sourceNode._children[k]
    sourceObject, sourceParameter = sourceChild.parseParameterString( source )
    s = getattr(sourceObject, sourceParameter, None)
    r.append(s)

  destObject, destParameter = destNode.parseParameterString( dest )
  setattr(destObject, destParameter, r)


#----------------------------------------------------------------------------
class Parameterized( object ):
  """
  This class represents an object that have a signature, that is to say a list of typed parameters.
  
  A `Parameterized` object can notify the changes in its signature.
  The parameters can be linked together, that is to say, if the value of a parameter changes, the value of all linked parameters may change.
  
  This object has an :py:func:`initialization` function that can define the links between the parameters and their initial values.
  
  :Attributes:
  
  .. py:attribute:: signature
  
    The signature is a :py:class:`brainvisa.data.neuroData.Signature`. It contains the list of parameters accepted by the object and their types. The possible types are described in :py:mod:`brainvisa.data.neuroData`.
  
  .. py:attribute:: signatureChangeNotifier
  
    This variable is a :py:class:`soma.notification.Notifier`. It calls its notify function when the signature of the :py:class:`Parameterized` object changes.
  
  :Methods:
  
  .. automethod:: initialization
  .. automethod:: findValue
  .. automethod:: setValue
  .. automethod:: checkArguments
  .. automethod:: setOptional
  .. automethod:: isDefault
  .. automethod:: setDefault
  .. automethod:: setConvertedValue
  .. automethod:: restoreConvertedValues

  .. automethod:: parameterLinkable
  .. automethod:: linkParameters
  .. automethod:: addLink
  .. automethod:: removeLink
  .. automethod:: addParameterObserver
  .. automethod:: removeParameterObserver
  .. automethod:: changeSignature
  .. automethod:: _parameterHasChanged
  .. automethod:: clearLinksFrom
  .. automethod:: clearLinksTo
  .. automethod:: cleanup

  """

  def __init__( self, signature ):
    # print 'create Parameterized', self
    self.__dict__[ '_deleted' ] = False # safety to avoid double deletion
    # see http://code.activestate.com/lists/python-list/191512/
    self.__dict__[ 'signature' ] = signature
    self._convertedValues = {}
    self._links = {}
    self._isParameterSet = {}
    self._isDefault = {}
    self._immutable = {}
    self._warn = {}
    self.signatureChangeNotifier = Notifier( 1 )
    self.deleteCallbacks = []
    self._blocklinks = False

    for i, p in self.signature.items():
      np = copy.copy( p )
      self.signature[ i ] = np
      np.copyPostprocessing()
      np.setNameAndParameterized( i, self )

    # Values initialization
    for i, p in self.signature.items():
      self.setValue( i, p.defaultValue() )

    self.initialization()
    # Take into account links set during self.initialization() :
    self.linksInitialization()
    
  def linksInitialization( self, parameterizedObjects = None, params = None, excluded = None ):
      
    if parameterizedObjects :
      r = []
      for o in parameterizedObjects :
        if not isinstance(o, weakref.ProxyType):
          o = weakref.proxy(o)
        r.append(o)
        
      parameterizedObjects = r
      
    # Call parameterHasChanged for the parameters that have not their default value anymore or that have a not None value
    for name in [n for n, v in self.signature.items() if ( (self.__dict__[n] != v.defaultValue()) or (self.__dict__[n] != None) ) ]:
      if (not params or (name in params)) \
        and (not excluded or (not name in excluded)) :
        self._parameterHasChanged( name, 
                                   getattr( self, name ), 
                                   parameterizedObjects = parameterizedObjects )

  def __del__( self ):
    if not hasattr( self, '_deleted' ) or self._deleted:
      return
    # print 'del Parameterized', self
    self._deleted = True
    debugHere()
    for x in self.deleteCallbacks:
      x( self )

  def _parameterHasChanged( self, name, newValue, parameterizedObjects = None ):
    """
    This function is called when the value of an attribute described in the signature changes.
    """
    debug = neuroConfig.debugParametersLinks
      
    if debug: print >> debug, 'parameter', name, 'changed in', self, 'with value', newValue
    for function in self._warn.get( name, [] ):
      if debug: print >> debug, '  call (_warn)', function, '(', name, ',', newValue, ')'
      function( self, name, newValue )
    for parameterized, attribute, function, force in self._links.get( name, [] ):
      if parameterized is None:
        if debug: print >> debug, '  call (_links)', function, '(', self, ',', self, ')'
        function( self, self )
      elif (not parameterizedObjects) or (parameterized in parameterizedObjects):
        if debug: print >> debug, ' ', name, 'is linked to parameter', attribute, 'of', parameterized, 'from', self, '(', len( self._links.get( name, [] ) ), ')'
        linkParamType = parameterized.signature[ attribute ]
        if not parameterized._isImmutable( attribute ) and ( force or parameterized.parameterLinkable( attribute, debug=debug ) ):
          linkParamDebug = getattr( linkParamType, '_debug', None )
          if linkParamDebug is not None:
            print >> linkParamDebug, 'parameter', name, 'changed in', self, 'with value', newValue
          if force:
            parameterized.setDefault( attribute, self.isDefault( name ) )
          if function is None:
            if debug: print >> debug, '  ' + str(parameterized) + '.setValue(', repr(attribute), ',', newValue,')'
            if linkParamDebug is not None:
              print >> linkParamDebug, '  ==> ' + str(parameterized) + '.setValue(', repr(attribute), ',', newValue,')'
            valueSet = newValue
            parameterized.setValue( attribute, newValue )
          else:
            if debug: print >> debug, '  call', function, '(', parameterized, ',', self, ')'
            if linkParamDebug is not None:
              print >> linkParamDebug, '  ==> call', function, '(', parameterized, ',', self, ')'
            v = function( parameterized, self )
            valueSet=v
            if debug: print >> debug, '  ' + str(parameterized) + '.setValue(', repr(attribute), ',', v,')'
            if linkParamDebug is not None:
              print >> linkParamDebug, '      ' + str(parameterized) + '.setValue(', repr(attribute), ',', v,')'
            parameterized.setValue( attribute, v )
          # activate the notifier with the parameter that receive a linked value and with the new value after evaluation of a link function.
          parameterized.signature[ attribute ].valueLinkedNotifier.notify(
            parameterized, attribute, valueSet )
     
    if debug :
      debug.flush()

  def isDefault( self, key ):
    """Returns True if the parameter `key` has kept its default value."""
    return self._isDefault.get( key, True )

  def setDefault( self, key, value ):
    """Stores if the parameter `key` have kept its default value or not."""
    debug = neuroConfig.debugParametersLinks
    if debug: print >> debug, '    setDefault(', key, ',', value, ')'
    self._isDefault[ key ] = value

  def _isImmutable( self, key ):
    """Returns True if the parameter `key` is immutable, ie can really be changed by a link. This is an internal state, used only temporarily during parameters assignment."""
    return self._immutable.get( key, False )

  def _clearImmutableParameters( self ):
    self._immutable = {}

  def _setImmutable( self, key, value ):
    """Stores if the parameter `key` immutable, ie can really be changed by a link."""
    self._immutable[ key ] = value

  def parameterLinkable( self, key, debug=None ):
    """Indicates if the value of the parameter can change through a parameter link."""
    if debug is None:
      debug = neuroConfig.debugParametersLinks
    result= bool( self.signature[ key ].linkParameterWithNonDefaultValue or \
                  self.isDefault( key ) )
    if debug: print >> debug, '    parameterLinkable =', result
    return result

  def initialization( self ):
    """This function does nothing by default but it may be overrideed in processes classes to define initial values for the parameters or links between parameters."""
    pass

  def checkArguments( self ):
    """Checks the value of the parameters described in the signature."""
    for p, o in self.signature.items():
      o.checkValue( p, getattr( self, p, None ) )

  def findValue( self, attributeName, value ):
    """Calls :py:func:`setValue`."""
    self.setValue( attributeName, value )

  def __setattr__( self, name, value ):
    """Calls :py:func:`setValue` if the parameter is described in the signature."""
    if self.signature.has_key( name ):
      self.setValue( name, value )
    else:
      self.__dict__[ name ] = value

  def blockLinks( self, blocked ):
    """
    While links are blocked, calls to setValue() or other parameters changes 
    do not trigger links.
    """
    self._blocklinks = blocked

  def setValue( self, name, value, default=None ):
    """
    Checks the value, sets the attribute `name`. 
    If the value has changed, :py:meth:`_parameterHasChanged` is called to apply the links.
    """
    debug = neuroConfig.debugParametersLinks
    if debug:
      print >> debug, str(self) + '.setValue(', repr(name), ',', repr(value), ',', repr(default), ')'
    changed = False
    if default is not None:
      changed = self.isDefault( name ) != default
      self.setDefault( name, default )
    if self._isParameterSet.get( name, False ):
      oldValue = getattr( self, name, None )
      newValue = self.signature[ name ].findValue( value )
      changed = changed or newValue != oldValue
    else:
      self._isParameterSet[ name ] = True
      newValue = self.signature[ name ].findValue( value )
      changed = True
    self.__dict__[ name ] =  newValue
    if changed:
      self._parameterHasChanged( name, newValue )

  def linkParameters( self, destName, sources, function = None ):
    """
    Links the parameters. When one of the `sources` parameters change, the value of `destName` parameter may change.
    It is possible to give a specific link function that will be called when the link is applied but it is not mandatory, a default function exists according to the type of parameter.
        
    :param string destName: name of the parameter that may change when the sources parameters change. If None, the link function will be called every time the sources parameters change.
    :param sources: one or several parameters, whose modification will activate the link function.
    :type sources: string, tuple or list
    :param function function: specific function to call instead of the default one when the link is activated. The signature of the function is *function(self, process ) -> destination*

    """
    if type( sources ) is types.StringType:
      sourcesList = [ sources ]
    else:
      sourcesList = sources
    for p in [ destName ] + list( sourcesList ):
      if not self.signature.has_key( p ):
        raise ValueError( HTMLMessage(_t_( '<em>%s</em> is not a valid parameter name' ) % p) )
    if function is None:
      function = getattr( self.signature[ destName ], 'defaultLinkParametersFunction', None )
    for p in sourcesList:
      self._links.setdefault( p, [] ).append( ( weakref.proxy( self ), destName, function, False ) )

  def addParameterObserver( self, parameterName, function ):
    """Associates a callback function to the modifications of the parameter value.
    
    :param parameterName: the name of the parameter whose modification will activate the callback.
    :param function: the callback function. its signature is *function(self, parameterName, newValue)*
    """
    minimum, maximum = numberOfParameterRange( function )
    if maximum == 0:
      tmp = lambda x, y, z, f=function: f()
      tmp._save_function = function
      function = tmp
    self._warn.setdefault( parameterName, [] ).append( function )

  def removeParameterObserver( self, parameterName, function ):
    """Removes the callback function from the parameter observers."""
    l = self._warn.get( parameterName, None )
    if l is not None:
      l.remove( function )
      if not l:
        del self._warn[ parameterName ]

  def setOptional( self, *args ):
    """Indicates that the parameters are not mandatory."""
    for k in args:
      self.signature[ k ].mandatory = False

  def setMandatory( self, *args ):
    """Indicates that the parameters are mandatory."""
    for k in args:
      self.signature[ k ].mandatory = True

  def setConvertedValue( self, name, value ):
    """Sets the value but stores the previous value in an internal dictionary."""
    self._convertedValues[ name ] = getattr( self, name )
    self.__dict__[ name ] = value

  def restoreConvertedValues( self ):
    """Restore values as they were before conversions using the values stored in an internal dictionary."""
    self.__dict__.update( self._convertedValues )
    self._convertedValues.clear()

  def addLink( self, destination, source, function=None ):
    """Add a link between `source` and `destination` parameters. When the value of `source` changes, the value of `destination` may change.
    Contrary to :py:func:`linkParameters`, the link will always be applied, even if the `destination` parameter has no more its default value.
    
    :param string destination: name of the parameter that may change when the source parameters change. If None, the link function will be called every time the source parameters change.
    :param source: one or several parameters, whose modification will activate the link function.
    :type source: string, tuple or list
    :param function function: specific function that will be called instead of the default one when the link is activated. The signature of the function is *function(self, *sources ) -> destination*
    """
    # Parse source
    sources = []
    if type( source ) in ( types.ListType, types.TupleType ):
      for i in source:
        if type( i ) in ( types.ListType, types.TupleType ):
          sources.append( i )
        else:
          sources.append( ( self, i ) )
    else:
      sources.append( ( self, source ) )

    if destination is None:
      destObject, destParameter = ( None, None )
    else:
      destObject, destParameter = ( weakref.proxy( self ), destination )
    # Check if a default function can be provided
    if function is None:
      if len( sources ) == 1:
        function = lambda x: x
      else:
        raise RuntimeError( HTMLMessage(_t_( 'No function provided in <em>addLink</em>' )) )
    multiLink = ExecutionNode.MultiParameterLink( sources, function )
    for sourceObject, sourceParameter in sources:
      sourceObject._links.setdefault( sourceParameter, [] ).append (
        ( destObject, destParameter, multiLink, True ) )



  def removeLink( self, destination, source ):
    """Removes a link added with :py:func:`addLink` function."""
    # print 'removeLink', self, destination, source
    # Parse source
    sources = []
    if type( source ) in ( types.ListType, types.TupleType ):
      for i in source:
        sources.append( ( self, i ) )
    else:
      sources.append( ( self, source ) )

    if destination is None:
      destObject, destParameter = ( None, None )
    else:
      destObject, destParameter = ( self, destination )

    removed = False
    for sourceObject, sourceParameter in sources:
      l = sourceObject._links.get( sourceParameter, [] )
      if l:
        lbis = l
        l = [i for i in l if ( i[0] is not destObject and i[0] is not weakref.proxy( destObject ) ) or i[1] != destParameter]
        if len( lbis ) != len( l ):
          removed = True
          if l:
            sourceObject._links[ sourceParameter ] = l
          else:
            del sourceObject._links[ sourceParameter ]
        else:
          print 'warning: link not removed:', self, destination, 'from:', source
    return removed


  def changeSignature( self, signature ):
    """Sets a new signature. Previous values of attributes are kept if the attributes are still in the signature.
    Links and observer callbacks that are no more associated to the signature parameters are deleted.
    The :py:attr:`signatureChangeNotifier` is notified.
    """
    # Change signature
    self.signature = signature
    for n in self.signature.keys():
      setattr( self, n, getattr( self, n, None ) )

    # Remove unused links
    for n in self._links.keys():
      if not self.signature.has_key( n ):
        del self._links[ n ]
    for n in self._warn.keys():
      if not self.signature.has_key( n ):
        del self._warn[ n ]

    # Notify listeners
    self.signatureChangeNotifier.notify( self )

  def clearLinksTo( self, *args ):
    """Removes all links that have a parameter in `args` as a destination."""
    for i in args:
      if isinstance( i, basestring ):
        destObject,  destParameter = None, i
      else:
        destObject,  destParameter = i
      if destObject:
        do=destObject
      else:
        do= self
      #do = (self if destObject is None else destObject) # not work in python 2.4
      if not do.signature.has_key( destParameter ):
        raise KeyError( _t_( 'Object %(object)s has not parameter "%(param)s"' ) % { 'object': unicode( do ), 'param': destParameter } )
      for k, l in self._links.items():
        i = 0
        while i < len( l ):
          do, dp, ml, f = l[ i ]
          if ( destObject is None or destObject is do ) and \
             destParameter == dp:
            del l[ i ]
          else:
            i += 1

  def clearLinksFrom( self, *args ):
    """Removes all links associated to a parameter in `args` as a source. """
    for k in args:
      if self._links.has_key( k ):
        del self._links[ k ]


  def cleanup( self ):
    """Removes all links, observers, and stored converted values, reinitializes the signature change notifier."""
    if debugHere is not None: # at exit time, the debug module might already be gone
      debugHere()
    self._convertedValues = {}
    self._links = {}
    self._warn = {}
    self.signatureChangeNotifier = Notifier( 1 )


  def convertStateValue( self, value ):

    if value is not None and not isinstance( value, ( int, float, basestring, list, dict, tuple ) ):
      result = unicode( value )
    elif isinstance( value, list ):
      result = [ self.convertStateValue( itervalue ) for itervalue in value ]
    elif isinstance( value, tuple ):
      result = tuple( self.convertStateValue( itervalue ) for itervalue in value )
    elif isinstance( value, dict ) :
      result = dict( (key, self.convertStateValue( itervalue ) ) for key, itervalue in value.iteritems() )
    else :
      result = value

    return result

  def saveStateInDictionary( self, result=None ):
    if result is None:
      result = {}
    selected = {}
    default = {}
    for n in self.signature.iterkeys():
      value = getattr( self, n, None )
      value = self.convertStateValue( value )

      if self.isDefault( n ):
        default[ n ] = value
      else:
        selected[ n ] = value
    result[ 'parameters' ] =  {
      'selected': selected,
      'default': default,
    }
    return result


#----------------------------------------------------------------------------
class Process( Parameterized ):
  """
  This class represents a Brainvisa process or pipeline.
  
  This object has a **signature** that describes its inputs and outputs and an **execution function** :py:meth:`execution`.
  If it is a **pipeline**, it also have an **execution node** that describes the structure of the pipeline.
  
  :Attributes:
  
  .. py:attribute:: signature
  
    The signature is a :py:class:`brainvisa.data.neuroData.Signature`. It contains the list of parameters accepted by the object and their types. The possible types are described in :py:mod:`brainvisa.data.neuroData`.

  .. py:attribute:: category (string)
  
    The processes are organized into categories. Generally, the category is the name of the directory where the process file is located.
  
  .. py:attribute:: userLevel (integer)
  
    The process is available in Brainvisa interface if its userLevel is lower or equal than the userLevel selected in Brainvisa options.
    0 : Basic, 1: Advanced, 2: Expert.
    
  .. py:attribute:: showMaximized (boolean)
  
    If true, the process window is shown maximized with a frame around it.
  
  :Methods:
  
  .. automethod:: id
  .. automethod:: validation
  .. automethod:: execution
  .. automethod:: executionNode
  .. automethod:: setExecutionNode
  .. automethod:: getAllParameters
  .. automethod:: allProcesses
  .. automethod:: pipelineStructure
  
  .. automethod:: sourceFile
  .. automethod:: sourcePath
  
  .. automethod:: inlineGUI
  
  .. automethod:: _iterate
  .. automethod:: _copy
 
  """
  signature = Signature()
  category = 'BrainVISA'
  userLevel = 2
  showMaximized = False

  def __init__( self ):
    # The following attributes can be set in user defined initialization()
    # mathod which is called by Parameterized constructor. Therefore, it
    # must be set before or never.
    self._executionNode = None

    # Copy signature because there is only one instance of each Parameter
    # object in signature for each Process class. This is an old mistake in
    # BrainVISA design, there should be one Signature instance by Process
    # instance.
    Parameterized.__init__( self, self.signature.shallowCopy())

    self._log = None
    self._outputLog = None
    self._outputLogFile = None
    #Main processes are opposed to subprocessed. There is more information
    # displayed to the user on main processes. For example, start/stop
    # notification and time elapsed in process are only displayed on main
    # processes. By default all processes called by another process are not
    # main process. It can be changed by setting isMainProcess to True.
    self.isMainProcess = False
    if hasattr( self.__class__, '_instance' ):
      self.__class__._instance += 1
    else:
      self.__class__._instance = 1
    self.instance = self.__class__._instance

  def __del__( self ):
    if self._deleted:
      print '*** Process already deleted ***'
      return
    try:
      Parameterized.__del__( self )
    except:
      # can happen when quitting the application: the current module is
      # not available any longer
      pass

  def _iterate( self, **kwargs ):
    """
    Returns a list of copies of the current process with different parameters values. 
    
    :param kwargs: dictionary containing a list of values for each parameter name. 
      The first value is for the first process of the iteration and so on...
    """
    # Find iteration size
    requiredLength = 0
    for values in kwargs.itervalues():
      length = len( values )
      if length > 1:
        if requiredLength > 0 and length > 1 and requiredLength != length:
          raise Exception( _t_( 'all lists of arguments with more than one value must have the same size' ) )
        else:
          requiredLength = length

    # Set lists of values
    finalValues = {}
    for key, values in kwargs.iteritems():
      if values:
        if len( values ) == 1:
          finalValues[ key ] = [ self.signature[ key ].findValue( values[0] ) ] * requiredLength
        else:
          finalValues[ key ] = [ self.signature[ key ].findValue( v ) for v in values ]

    result = []
    for i in xrange( requiredLength ):
      p = self._copy( withparams=True ) # should copy only non-default params
      for argumentName in finalValues.keys():
        p._setImmutable( argumentName, True )
      for argumentName, values in finalValues.iteritems():
        p.setValue( argumentName, values[ i ], default=0 )
      p._clearImmutableParameters()
      result.append( p )
    return result


  def _copy( self, withparams=True ):
    """Returns a copy of the process. The value of the parameters are also copied if withparams is True (which is the default)"""
    result = self.__class__()
    if withparams:
      # disable links
      self.blockLinks( True )
      # set params
      for ( n, p ) in self.signature.items():
        #if not self.isDefault( n ):
          #result.setValue( n, getattr( self, n, None ), default=False )
        result.setValue( n, getattr( self, n, None ),
                        default=self.isDefault( n ) )
    if self._executionNode:
      self._executionNode._copy(result.executionNode(), withparams=withparams)
    self.blockLinks( False )
    return result


  def inlineGUI( self, values, context, parent, externalRunButton=False ):
    """This method can be overrideed in order to specialize buttons of the process window.
    
    :param context: the execution context of the process
    :param parent: The parent widget
    :returns: the widget containing the buttons that will replace the default buttons (Run and Iterate)
    :rtype: QWidget
    """
    return None


  def validation( self ):
    """This method can be overrideed in order to check if the process dependencies are available.
    It will be called at Brainvisa startup when the processes are loaded. If the method raises an exception, the process will not be available.
    
    :raises: :py:class:`brainvisa.validation.ValidationError`
    """
    return 1

  def id( self ):
    """Returns the process id."""
    return self._id

  def sourceFile( self ):
    """Returns the name of the source file of the process."""
    return self._fileName

  def sourcePath( self ):
    """Returns the path to the source file of the process."""
    return os.path.dirname( self._fileName )

  def __str__( self ):
    instance = getattr( self, '_instance', None )
    if instance is None:
      return self.id()
    else:
      return self.id() + '_' + unicode( instance )

  def addLink( self, destination, source, function=None ):
    eNode = getattr( self, '_executionNode', None )
    if eNode is None:
      Parameterized.addLink( self, destination, source, function )
    else:
      eNode.addLink( destination, source, function )
    
  def setExecutionNode( self, eNode ):
    """Sets the execution node of the pipeline.
    
    :param eNode: object that describes the structure of the pipeline.
    :type eNode: :py:class:`ExecutionNode`
    """
    self._executionNode = eNode

  def execution( self, context ):
    """
    Execution function that is called when the process is run.
    """
    if self._executionNode is not None:
        return self._executionNode.run( context )
    else:
      raise RuntimeError( HTMLMessage(_t_( 'No <em>execution</em> method provided' )) )

  def executionNode( self ):
    """Returns the execution node of the pipeline."""
    return self._executionNode


  def pipelineStructure( self ):
    """Returns the description of a pipeline in a dictionary or the id of the process if it is a simple process."""
    return self.id()


  def allProcesses( self ):
    """Returns the current process and all its children if it is a pipeline.
    
    :rtype: generator
    """
    yield self
    if self._executionNode is not None:
      stack = [ self._executionNode ]
      while stack:
        eNode = stack.pop( 0 )
        if isinstance( eNode, ProcessExecutionNode ):
          yield eNode._process
        stack.extend( eNode.children() )

  def allParameterFiles( self ):
    """Get recursively all parameters which are DiskItems, descending through
    the pipeline structure.
    """
    params = []
    files = set()
    for paramname in self.signature.iterkeys():
      param = self.__dict__.get( paramname )
      if param is not None and isinstance( param, DiskItem ):
        filename = param.fullPath()
        if filename not in files:
          params.append( param )
          files.add( filename )
    # parse pipeline structure
    eNodes = []
    eNode = self.executionNode()
    if eNode is not None:
      eNodes.append( eNode )
    while eNodes:
      eNode = eNodes.pop()
      eNodes += list( eNode.children() )
      if isinstance( eNode, ProcessExecutionNode ):
        process = eNode._process
        for paramname in process.signature.iterkeys():
            param = process.__dict__.get( paramname )
            if param is not None and isinstance( param, DiskItem ):
              filename = param.fullPath()
              if filename not in files:
                params.append( param )
                files.add( filename )
    return params


  def saveStateInDictionary( self, result=None ):
    """Returns the description of the process in a dictionary."""
    if result is None:
      result = {}
    result[ 'pipelineStructure' ] = self.pipelineStructure()
    if self._executionNode is not None:
      if self._executionNode._parameterized is not None:
        Parameterized.saveStateInDictionary( self._executionNode._parameterized(), result )
      eNodesState = {}
      for eNodeKey in self._executionNode.childrenNames():
        eNode = self._executionNode.child( eNodeKey )
        eNodeDict = {}
        eNode.saveStateInDictionary( eNodeDict )
        eNodesState[ eNodeKey ] = eNodeDict
      result[ 'executionNodes' ] = eNodesState
    else:
      Parameterized.saveStateInDictionary( self, result )
    return result


  def getAllParameters( self ):
    """
    Returns all the parameters of the current process and its children if it is a pipeline.
    
    :returns: tuples (Parameterized, attribute name, attribute type)
    :rtype: generator
    """
    stack = [ self ]
    while stack:
      node = stack.pop( 0 )
      if isinstance( node, Process ):
        parameterized = node
        node = node.executionNode()
        if node is not None:
          stack += [node.child( i ) for i in node.childrenNames()]
      else:
        parameterized = node._parameterized
        if parameterized is not None: parameterized = parameterized()
        stack += [node.child( i ) for i in node.childrenNames()]
      if parameterized is not None:
        for attribute, type in parameterized.signature.iteritems():
          yield ( parameterized, attribute, type )



#----------------------------------------------------------------------------
class IterationProcess( Process ):
  """
  This class represents a set of process instances that can be executed in parallel. 
  
  It is used to iterate the same process on a set of data.
  """
  def __init__( self, name, processes ):
    self._id = name + 'Iteration'
    self.name = name
    self.instance = 1
    self._processes = [getProcessInstance( p ) for p in processes]
    Process.__init__( self )
    for sp, p in zip( self._executionNode._children.values(), processes ):
      if isinstance( p, ExecutionNode ):
        sp._optional = p._optional
        sp._selected = p._selected

  #def __del__( self ):
    #print 'del IterationProcess', self, ', children:', len( self._processes )
    #print 'children:', self._processes
    #del self._processes
    #import gc
    #print 'refs to execution node:', len( gc.get_referrers( self._executionNode ) )
    #print [ i.keys() for i in gc.get_referrers( self._executionNode ) ]

  def pipelineStructure( self ):
    return { 'type': 'iteration', 'name' : self.name, 'children':[p.pipelineStructure() for p in self._processes] }

  def initialization( self ):
    if len( self._processes ) != 0:
      dp = self._processes[0].name
    else:
      dp = None
    eNode = ParallelExecutionNode( self.name, stopOnError=False,
      possibleChildrenProcesses=dp, notify = True )

    for i in xrange( len( self._processes ) ):
      self._processes[ i ].isMainProcess = True
      self._processes[ i ].name = repr(i+1) + ". " + self._processes[ i ].name
      eNode.addChild( node = ProcessExecutionNode( self._processes[ i ],
                      optional = True, selected = True ) )
      
    # Add callbacks to maintain synchronization
    eNode.beforeChildAdded.add(\
      ExecutionNode.MethodCallbackProxy( self.beforeChildAdded ) )
    eNode.beforeChildRemoved.add(\
      ExecutionNode.MethodCallbackProxy( self.beforeChildRemoved ) )
      
    self._executionNode = eNode
    
  def beforeChildAdded( self, parent, key, child ):
    child._process.isMainProcess = True
    child._process.name = repr(parent._internalIndex) + ". " + child._process.name
    self._processes.append( child._process )

  def beforeChildRemoved( self, parent, key, child ):
    if child._process in self._processes:
      self._processes.remove(child._process)
      
#----------------------------------------------------------------------------
class ListOfIterationProcess( IterationProcess ):
  '''
  An IterationProcess which has on its main signature a list of the first
  element of each sub-process.
  
  Used for viewers and editors of ListOf()
  '''
  class linkP( object ):
    def __init__( self, proc, i ):
      self.proc = proc
      self.num = i
    def __call__( self, par ):
      if len( self.proc.param ) > self.num:
        return self.proc.param[self.num]

  def __init__( self, name, processes ):
    IterationProcess.__init__( self, name, processes )
    chs = list( self.executionNode().children() )[0]._process.signature
    self.changeSignature( Signature( 'param', ListOf( chs.values()[0] ) ) )
    en = self.executionNode()
    en._parameterized = weakref.ref( self )
    for i, p in enumerate( en.children() ):
      s = p._process.signature
      en.addLink( str(i) + '.' + s.keys()[0], 'param', self.linkP( self, i ) )


#----------------------------------------------------------------------------
class DistributedProcess( Process ):
  """
  This class represents a set of process instances that can be executed in parallel. 
  """
  def __init__( self, name, processes ):
    self._id = name + 'DistributedIteration'
    self.name = name
    self.instance = 1
    self._processes = [getProcessInstance( p ) for p in processes]
    Process.__init__( self )
    for sp, p in zip( self._executionNode._children.values(), processes ):
      if isinstance( p, ExecutionNode ):
        sp._optional = p._optional
        sp._selected = p._selected

  def pipelineStructure( self ):
    return { 'type': 'distributed', 'name' : self.name, 'children':[p.pipelineStructure() for p in self._processes] }

  def initialization( self ):
    eNode = ParallelExecutionNode( self.name )
    for i in xrange( len( self._processes ) ):
      self._processes[ i ].isMainProcess = True
      subENode = self._processes[ i ]._executionNode
      eNode.addChild( str( i ), ProcessExecutionNode( self._processes[ i ],
                      optional=True, selected = True ) )
    self._executionNode = eNode


#----------------------------------------------------------------------------
class SelectionProcess( Process ):
  """
  This class represents a choice between a list of processes. 
  """
  def __init__( self, name, processes ):
    self._id = name + 'Selection'
    self.name = name
    self.instance = 1
    self._processes = [getProcessInstance( p ) for p in processes]
    Process.__init__( self )
    for sp, p in zip( self._executionNode._children.values(), processes ):
      if isinstance( p, ExecutionNode ):
        sp._optional = p._optional
        sp._selected = p._selected

  def pipelineStructure( self ):
    return { 'type': 'selection', 'name' : self.name, 'children':[p.pipelineStructure() for p in self._processes] }

  def initialization( self ):
    eNode = SelectionExecutionNode( self.name )
    for i in xrange( len( self._processes ) ):
      self._processes[ i ].isMainProcess = True
      eNode.addChild( str( i ), ProcessExecutionNode( self._processes[ i ],
                        optional=True, selected = True ) )
    self._executionNode = eNode

#----------------------------------------------------------------------------
class TimeoutCall( object ):
  def __init__( self, function, *args, **kwargs ):
    self.function = function
    self.args = args
    self.kwargs = kwargs
    self.event = threading.Event()
    self.callFunction = 0
    self.functionLock =threading.RLock()

  def __del__( self ):
    self.stop()

  def _thread( self ):
    self.event.wait( self.timeout )
    self.functionLock.acquire()
    try:
      if self.callFunction:
        apply( self.function, self.args, self.kwargs )
    finally:
      self.functionLock.release()

  def start( self, timeout ):
    self.stop() # Just in case of multiple start() call during timeout
    self.functionLock.acquire()
    try:
      self.callFunction = 1
      self.event.clear()
      self.timeout = timeout
      threading.Thread( target = self._thread )
    finally:
      self.functionLock.release()

  def stop( self ):
    self.functionLock.acquire()
    try:
      self.callFunction = 0
      self.event.set()
    finally:
      self.functionLock.release()


#----------------------------------------------------------------------------
def signalName( signalNumber ):
  for key, value in signal.__dict__.items():
    if key[ :3 ] == 'SIG' and value == signalNumber:
      return key
  return str( signalNumber )


#----------------------------------------------------------------------------
def escapeQuoteForShell( s ):
  return string.replace( s, "'",  "'\"'\"'" )


#-------------------------------------------------------------------------------
class ExecutionNode( object ):
  """
  Base class for the classes that describe a pipeline structure. 
  """
  class MultiParameterLink:
    def __init__( self, sources, function ):
      self.sources = []
      for p, n in sources:
        if type(p) is weakref.ReferenceType:
          self.sources.append( ( p, n ) )
        else:
          self.sources.append( ( weakref.ref( p ), n ) )
      self.function = function
      self.hasParameterized = hasParameter( function, 'parameterized' )
      self.hasNames = hasParameter( function, 'names' )

    def __call__( self, dummy1, dummy2 ):
      kwargs = {}
      if self.hasParameterized:
        kwargs[ 'parameterized' ] = [i[0]() for i in self.sources]
      if self.hasNames:
        kwargs[ 'names' ] = [i[1] for i in self.sources]
      return self.function( *[getattr( i[0](), i[1], None ) for i in self.sources],
                           **kwargs )

  class MethodCallbackProxy( object ):
    def __init__( self, method ):
      self.object = weakref.ref( method.im_self )
      self.method = method.im_func
    def __call__( self, *args, **kwargs ):
      o = self.object()
      if o is not None:
        self.method( o, *args, **kwargs )
    def __eq__( self, other ):
      if isinstance( other, ExecutionNode.MethodCallbackProxy ):
        return self.object() == other.object() and self.method == other.method
      if self.object() is None:
        return other is None
      return self.method.__get__( self.object() ) == other

  def __init__( self, name='', optional = False, selected = True,
                guiOnly = False, parameterized = None, expandedInGui = False ):
    """
    :param string name: name of the node - default ''.
    :param boolean optional: indicates if this node is optional in the pipeline - default False.
    :param boolean selected: indicates if the node is selected in the pipeline - default True.
    :param boolean guiOnly: default False.
    :param parameterized: :py:class:`Parameterized` containing the signature of the node - default None.
    """
    # Initialize an empty execution node
    #print 'ExecutionNode.__init__', self
    self.__dict__[ '_deleted' ] = False # safety to avoid double deletion
    # see http://code.activestate.com/lists/python-list/191512/
    self.__dict__[ '_children' ] = SortedDictionary()
    if parameterized is not None:
      parameterized = weakref.ref( parameterized )
    self.__dict__[ '_parameterized' ] = parameterized
    self.__dict__[ '_name' ] = str( name )
    self.__dict__[ '_optional' ] = optional
    self.__dict__[ '_selected' ] = selected
    self.__dict__[ '_guiOnly' ] = guiOnly
    self.__dict__[ '_selectionChange' ] = Notifier( 1 )
    self.__dict__[ '_expandedInGui' ] = expandedInGui
    self.__dict__[ '_dependencies' ] = []

  def __del__( self ):
    #print 'del ExecutionNode', self
    if not hasattr( self, '_deleted' ) or self.__dict__[ '_deleted' ]:
      print '*** ExecutionNode already deleted ! ***'
      return
    self.__dict__[ '_deleted' ] = True
    debugHere()

  def _copy(self, node, withparams=True):
    """
    Uses non default parameters values to initialize the parameters of the node given in argument, if withparams is True (which is the default).
    """
    # if execution node contains a process, copy the process parameters and copy its execution node parameters if any
    process=getattr(self, "_process", None)
    if process:
      processCopy=node._process
      if withparams:
        for ( n, v ) in process.signature.items():
          #if not self.isDefault( n ):
            #processCopy.setValue( n, getattr( process, n, None ), 
                                  #default=False )
          processCopy.setValue( n, getattr( process, n, None ), 
                                default=process.isDefault( n ) )
      processNode=process.executionNode()
      if processNode:
        processNode._copy(processCopy.executionNode(), withparams=withparams)
    node.setSelected(self._selected)
    # if execution node have children nodes, copy the parameters of these nodes
    for name in self.childrenNames():
      child=self.child(name)
      child._copy(node.child(name), withparams=withparams)

  def addChild( self, name, node, index = None):
    '''Add a new child execution node.
    
    :param string name: name which identifies the node
    :param node: an :py:class:`ExecutionNode` which will be added to this node's children.
    '''
    if self._children.has_key( name ):
      raise KeyError( HTMLMessage(_t_( '<em>%s</em> already defined' ) % ( name, )) )
    if not isinstance( node, ExecutionNode ):
      raise RuntimeError( HTMLMessage('<em>node</em> argument must be an execution node') )
    
    if not index is None :
      self._children.insert( index, name, node )
    else :
      self._children[ name ] = node

  def removeChild( self, name ):
    '''Remove child execution node.
    
    :param string name: name which identifies the node
    '''
    if not self._children.has_key( name ):
      raise KeyError( HTMLMessage(_t_( '<em>%s</em> not defined' ) % ( name, )) )
    c = self._children[ name ]
    del self._children[ name ]
    
    return c

  def childrenNames( self ):
    '''
    Returns the list of names of the children execution nodes.
    '''
    return self._children.keys()


  def children( self ):
    """Returns the list of children execution nodes."""
    return self._children.itervalues()

  def hasChildren( self ):
    """Returns True if this node has children."""
    return bool( self._children )


  def setSelected( self, selected ):
    """Change the selection state of the node.
    
    :param bool selected: new selection state of the node. If the selection changes, a selection change notifier is notified.
    """
    if selected != self._selected:
      self._selected = selected
      self._selectionChange.notify( self )

  def isSelected( self ):
    """True if this node is selected."""
    return self._selected

  def __setattr__( self, attribute, value ):
    """
    If the attribute is in the signature of the corresponding parameterized object, it is modified.
    """
    if self._parameterized is not None and \
       self._parameterized().signature.has_key( attribute ):
      setattr( self._parameterized(), attribute, value )
    elif self._children.has_key( attribute ):
      raise RuntimeError( HTMLMessage(_t_( 'Direct modification of execution node <em>%s</em> is not allowed.' ) % ( attribute, )) )
    else:
      self.__dict__[ attribute ] = value

  def __getattr__( self, attribute ):
    p = self.__dict__.get( '_parameterized' )
    if p is not None: p = p()
    if p is not None and hasattr( p, attribute ):
      return getattr( p, attribute )
    children = self.__dict__[ '_children' ]
    if children.has_key( attribute ):
      return children[ attribute ]
    raise AttributeError( attribute )

  def child( self, name, default = None ):
    """Get a child node by name."""
    return self._children.get( name, default )

  def allParameterFiles( self ):
    """Get recursively all parameters which are DiskItems, descending through
    the pipeline structure.
    """
    params = []
    files = set()
    # parse pipeline structure
    eNodes = [ self ]
    while eNodes:
      eNode = eNodes.pop()
      eNodes += list( eNode.children() )
      if isinstance( eNode, ProcessExecutionNode ):
        process = eNode._process
        for paramname in process.signature.iterkeys():
            param = process.__dict__.get( paramname )
            if param is not None and isinstance( param, DiskItem ):
              filename = param.fullPath()
              if filename not in files:
                params.append( param )
                files.add( filename )
    return params

  def run( self, context ):
    """
    Calls :py:meth:`_run` method if the node is selected.
    """
    if self._optional and ( not self._selected ):
      context.write( '<font color=orange>Skip unselected node: ' + str(self.name()) + '</font>' )
      return
    if self._guiOnly and not neuroConfig.gui:
      context.write( '<font color=orange>Skip GUI-only node: ' + str(self.name()) + '</font>' )
      return
    return self._run( context )

  def _run( self, context ):
    """
    Does nothing in the base class. It is overriden by derived classes. 
    """
    pass

  def name( self ):
    """Returns the name of the node."""
    return self._name

  def gui( self, parent, processView = None ):
    """
    Returns the graphical user interface of this node.
    """
    from brainvisa.processing.qtgui.neuroProcessesGUI import ExecutionNodeGUI
    if self._parameterized is not None:
      if processView != None and processView.read_only:
        return ExecutionNodeGUI(parent, self._parameterized(), read_only=True)
      return ExecutionNodeGUI(parent, self._parameterized())
    return None

  def addLink( self, destination, source, function=None ):
    """
    Adds a parameter link like :py:meth:`Parameterized.addLink`.
    """
    # Parse source
    sources = []
    if type( source ) in ( types.ListType, types.TupleType ):
      for i in source:
        sources.append( self.parseParameterString( i ) )
    else:
      sources.append( self.parseParameterString( source ) )

    destObject, destParameter = self.parseParameterString( destination )
    if destObject is not None:
      destObject = weakref.proxy( destObject )
    # Check if a default function can be provided
    if function is None:
      if len( sources ) == 1:
        function = lambda x: x
      else:
        raise RuntimeError( HTMLMessage(_t_( 'No function provided in <em>addLink</em>' )) )
    multiLink = self.MultiParameterLink( sources, function )
    for sourceObject, sourceParameter in sources:
      sourceObject._links.setdefault( sourceParameter, [] ).append (
        ( destObject, destParameter, multiLink, True ) )


  def addDoubleLink( self, destination, source, function=None ):
    """
    Creates a double link source -> destination and destination -> source.
    """
    self.addLink( destination, source, function )
    self.addLink( source, destination, function )


  def removeLink( self, destination, source, function=None ):
    """
    Removes a parameters link added with :py:meth:`addLink`.
    """
    # Parse sourceExecutionContext
    sources = []
    if type( source ) in ( types.ListType, types.TupleType ):
      for i in source:
        sources.append( self.parseParameterString( i ) )
    else:
      sources.append( self.parseParameterString( source ) )

    destObject, destParameter = self.parseParameterString( destination )

    removed = 0
    for sourceObject, sourceParameter in sources:
      l = sourceObject._links.get( sourceParameter, [] )
      if l:
        lbis = l
        l = [i for i in l if ( destObject and i[0] is not destObject and ( i[0] is not weakref.proxy( destObject ) ) ) or i[1] != destParameter]
        if len(l) != len(lbis):
          removed = 1
        if l:
          sourceObject._links[ sourceParameter ] = l
        else:
          del sourceObject._links[ sourceParameter ]
          removed=1
    if removed == 0:
      print 'warning: enode link not removed:', self, destination, 'from:', source, ', function:', function

  def removeDoubleLink( self, destination, source, function=None ):
    """
    Removes a double link source -> destination and destination -> source.
    """
    self.removeLink( destination, source, function )
    self.removeLink( source, destination, function )

  def parseParameterString( self, parameterString ):
    """
    Returns a tuple containing the :py:class:`Parameterized` object of the child node indicated in the parameter string and the name of the parameter.
    
    :param string parameterString: references a parameter of a child node with a path like <node name 1>.<node name 2>...<parameter name>
    """
    if parameterString is None: return ( None, None )
    l = parameterString.split( '.' )
    node = self
    for nodeName in l[ : -1 ]:
      node = node.child( nodeName )
    parameterized = node._parameterized
    if parameterized is not None: parameterized = parameterized()
    name = l[ -1 ]
    if parameterized is None or not parameterized.signature.has_key( name ):
      raise KeyError( name )
    return ( parameterized, name )


  def saveStateInDictionary( self, result=None ):
    if result is None:
      result = {}
    result[ 'name' ] = self._name
    result[ 'selected' ] = self._selected
    if self._parameterized is not None:
      Parameterized.saveStateInDictionary( self._parameterized(), result )
    eNodesState = {}
    for eNodeKey in self.childrenNames():
      eNode = self.child( eNodeKey )
      eNodesState[ eNodeKey ] = eNode.saveStateInDictionary()
    result[ 'executionNodes' ] = eNodesState
    return result

  def addExecutionDependencies( self, deps ):
    '''Adds to the execution node dependencies on the execution of other nodes.
    This allows to build a dependencies structure which is not forced to be a
    tree, but can be a grapĥ. Dependencies are used to build Soma-Workflow
    workflows with correct dependencies.
    '''
    if type( deps ) not in ( types.ListType, types.TupleType ):
      deps = [ deps ]
    self._dependencies += [ weakref.ref(x) for x in deps ]

#-------------------------------------------------------------------------------
class ProcessExecutionNode( ExecutionNode ):
  '''
  An execution node that has no children and run one process
  
  '''

  def __init__( self, process, optional = False, selected = True,
                guiOnly = False, expandedInGui = False, altname = None ):
    process = getProcessInstance( process )
    #print 'ProcessExecutionNode.__init__:', self, process.name
    ExecutionNode.__init__( self, process.name,
                            optional = optional,
                            selected = selected,
                            guiOnly = guiOnly,
                            parameterized = process,
                            expandedInGui = expandedInGui )
    self.__dict__[ '_process' ] = process
    if altname is not None:
      self.__dict__[ '_name' ] = altname
    reloadNotifier = getattr( process, 'processReloadNotifier', None )
    if reloadNotifier is not None:
      reloadNotifier.add( ExecutionNode.MethodCallbackProxy( \
        self.processReloaded ) )

  def __del__( self ):
    #print 'del ProcessExecutionNode', self
    if not hasattr( self, '_deleted' ) or self._deleted:
      print '*** already deleted !***'
      return
    if hasattr( self, '_process' ):
      #print '     del proc:', self._process.name
      reloadNotifier = getattr( self._process, 'processReloadNotifier', None )
      if reloadNotifier is not None:
        try:
          l = len( reloadNotifier._listeners )
          z = ExecutionNode.MethodCallbackProxy( self.processReloaded )
          # bidouille: hack z so as to contain a weakref to None
          # since we are in __del__ and existing weakrefs to self have already
          # been neutralized
          class A(object): pass
          w = weakref.ref(A()) # w points to None immediately
          z.object = w
          x = reloadNotifier.remove( z )
        except AttributeError:
          # this try..except is here to prevent an error when quitting
          # BrainVisa:
          # ProcessExecutionNode class is set to None during module destruction
          pass
    else:
      # print 'del ProcessExecutionNode', self
      print 'no _process in ProcessExecutionNode !'
    try:
      ExecutionNode.__del__( self )
    except:
      # same as above
      pass

  def addChild( self, name, node, index = None ):
    raise RuntimeError( _t_( 'A ProcessExecutionNode cannot have children' ) )

  def _run( self, context ):
    return context.runProcess( self._process )

  def gui( self, parent, processView = None ):
    if processView is not None:
      return ProcessView( self._process, parent,
                          externalInfo = processView.info,
                          read_only=processView.read_only)
    else:
      return ProcessView( self._process, parent )

  def children( self ):
    eNode = getattr( self._process, '_executionNode', None )
    if eNode is not None:
      return eNode._children.itervalues()
    else:
      return []

  def childrenNames( self ):
    eNode = getattr( self._process, '_executionNode', None )
    if eNode is not None:
      return eNode._children.keys()
    else:
      return []

  def __setattr__( self, attribute, value ):
    if self._parameterized is not None and \
       self._parameterized().signature.has_key( attribute ):
      setattr( self._parameterized(), attribute, value )
    else:
      eNode = getattr( self._process, '_executionNode', None )
      if eNode is not None and eNode._children.has_key( attribute ):
        raise RuntimeError( HTMLMessage(_t_( 'Direct modification of execution node <em>%s</em> is not allowed.' ) % ( attribute, )) )
      self.__dict__[ attribute ] = value

  def __getattr__( self, attribute ):
    p = self.__dict__.get( '_parameterized' )()
    if p is not None and hasattr( p, attribute ):
      return getattr( p, attribute )
    eNode = getattr( self._process, '_executionNode', None )
    if eNode is not None:
      c = eNode.child( attribute )
      if c is not None:
        return c
    raise AttributeError( attribute )

  def child( self, name, default=None ):
    eNode = getattr( self._process, '_executionNode', None )
    if eNode is not None:
      return eNode.child( name, default )
    return default

  def processReloaded( self, newProcess ):
    """
    If the associated process has an attribute *processReloadNotifier*, this callback is attached to the notifier.
    So, the node is reloaded when the process is reloaded.
    """
    event = ProcessExecutionEvent()
    event.setProcess( self._process )
    self._process.processReloadNotifier.remove( ExecutionNode.MethodCallbackProxy( self.processReloaded ) )
    self.__dict__[ '_process' ] = getProcessInstanceFromProcessEvent( event )
    self._process.processReloadNotifier.add( ExecutionNode.MethodCallbackProxy( self.processReloaded ) )

  def addExecutionDependencies( self, deps ):
    ExecutionNode.addExecutionDependencies( self, deps )
    eNode = self._process._executionNode
    if eNode:
      eNode.addExecutionDependencies( deps )


#-------------------------------------------------------------------------------
class SerialExecutionNode( ExecutionNode ):
  '''An execution node that run all its children sequentially'''

  def __init__(self, name='', optional = False, selected = True,
                guiOnly = False, parameterized = None, stopOnError=True,
                expandedInGui = False, possibleChildrenProcesses = None, notify = False ):
    #print 'SerialExecutionNode.__init__', self
    ExecutionNode.__init__(self, name, optional, selected, guiOnly, parameterized, expandedInGui=expandedInGui )
    self.stopOnError=stopOnError
    self.notify = notify
    
    if possibleChildrenProcesses :
      if not isinstance( possibleChildrenProcesses, dict ) :
        if not isinstance( possibleChildrenProcesses, list ) \
          and not isinstance( possibleChildrenProcesses, tuple ) :
          possibleChildrenProcesses = [ possibleChildrenProcesses ]
        
        r = {}
        for i in xrange(len(possibleChildrenProcesses)) :
          r[possibleChildrenProcesses[i]] = { 'optional' : True,
                                              'selected' : True,
                                              'expandedInGui' : False }
        possibleChildrenProcesses = r
        
      self._internalIndex = 0
      
    self.possibleChildrenProcesses = possibleChildrenProcesses
    
    if self.notify :
      # Add child changes notifiers
      self.beforeChildRemoved = Notifier( 4 )
      self.afterChildRemoved = Notifier( 4 )
      self.beforeChildAdded = Notifier( 4 )
      self.afterChildAdded = Notifier( 4 )

  def _run( self, context ):
    result = []
    pi, p = context.getProgressInfo( self )
    pi.children = [ None ] * len( self._children )
    if self.stopOnError:
      for node in self._children.values():
        npi, proc = context.getProgressInfo( node, parent=pi )
        context.progress()
        result.append( node.run( context ) )
        del npi
    else:
      for node in self._children.values():
        npi, proc = context.getProgressInfo( node, parent=pi )
        context.progress()
        try:
          result.append( node.run( context ) )
          del npi
        except ExecutionContext.UserInterruptionStep, e:
          context.error(unicode(e))
        except ExecutionContext.UserInterruption:
          raise
        except Exception, e:
          context.error("Error in execution node : "+unicode(e))
    context.progress()
    return result
    
  def addChild(self, name = None, node = None, index = None):
    if self.possibleChildrenProcesses :
      if not name :
        if isinstance( node, ExecutionNode ):
          name = node.name() + '_' + str(self._internalIndex)
        else :
          raise RuntimeError( HTMLMessage('<em>node</em> argument must be an execution node') )
      else:
        name += '_' + str(self._internalIndex)
      if not node:
        node = self.possibleChildrenProcesses
      self._internalIndex += 1

    if self.notify :
      self.beforeChildAdded.notify( weakref.proxy( self ), name, weakref.proxy( node ) )

    super( SerialExecutionNode, self ).addChild(name, node, index)
    
    if self.notify :
      self.afterChildAdded.notify( weakref.proxy( self ), name, weakref.proxy( node ) )
  
  def removeChild(self, name):
    if self.possibleChildrenProcesses :
      if not self._children.has_key( name ):
        raise KeyError( HTMLMessage(_t_( '<em>%s</em> not defined' ) % ( name, )) )
      
    if self.notify :
      node = self._children[ name ]
      self.beforeChildRemoved.notify( weakref.proxy( self ), name, weakref.proxy( node ) )

    super( SerialExecutionNode, self ).removeChild(name)
    
    if self.notify :
      self.afterChildRemoved.notify( weakref.proxy( self ), name, weakref.proxy( node ) )


#-------------------------------------------------------------------------------
class ParallelExecutionNode( SerialExecutionNode ):
  """
  An execution node that run all its children in any order (and in parallel
  if possible)
  """
    
  def _run( self, context ):
    pi, p = context.getProgressInfo( self )
    # do as for serial node
    return super( ParallelExecutionNode, self )._run( context )
    
#-------------------------------------------------------------------------------
class SelectionExecutionNode( ExecutionNode ):
  '''An execution node that run one of its children'''

  def __init__( self, *args, **kwargs ):
    #print 'SelectionExecutionNode.__init__', self
    ExecutionNode.__init__( self, *args, **kwargs )

  def __del__( self ):
    #print 'SelectionExecutionNode.__del__', self
    if not hasattr( self, '_deleted' ) or self._deleted:
      print '*** SelectionExecutionNode already deleted'
      return
    for node in self._children.values():
      node._selectionChange.remove( ExecutionNode.MethodCallbackProxy( \
        self.childSelectionChange ) )
    #print '__del__ finished'

  def _run( self, context ):
    'Run the selected child'
    if self._selected is None:
      raise RuntimeError( _t_( 'No children selected' ) )
    pi, p = context.getProgressInfo( self )
    pi.children = [ None ]
    for node in self._children.values():
      if node._selected:
        npi, proc = context.getProgressInfo( node, parent=pi )
        context.progress()
        res =  node.run( context )
        del npi
        context.progress()
        return res
    context.progress()

  def addChild( self, name, node, index = None ):
    'Add a new child execution node'
    ExecutionNode.addChild(self, name, node, index)
    node._selectionChange.add( ExecutionNode.MethodCallbackProxy( \
      self.childSelectionChange ) )
    node._dependencies += self._dependencies

  def childSelectionChange(self, node):
    '''This callback is called when the selection state of a child has changed.
    If the child is selected, all the other children must be unselected
    because this node is a selectionNode.'''
    if node._selected:
      for child in self.children():
        if child != node:
          child.setSelected(False)

  def addExecutionDependencies( self, deps ):
    ExecutionNode.addExecutionDependencies( self, deps )
    for node in self._children.values():
      node.addExecutionDependencies( deps )

#-------------------------------------------------------------------------------
class ExecutionContext( object ):
  """
  This object represents the execution context of the processes. 
  
  Indeed, a process can be started in different contexts :

    * The user starts the process by clicking on the Run button in the graphical interface.
    * The process is started via a script. It is possible to run brainvisa in batch mode (without any graphical interface) and to run a process via a python function : brainvisa.processes.defaultContext().runProcess(...).
    * The process is a converter, so it can be run automatically by BrainVISA when a conversion is needed for another process parameters.
    * The process is a viewer or an editor, it is run when the user clicks on the corresponding icon to view or edit another process parameter. 
    
  The interactions with the user are different according to the context. That's why the context object offers several useful functions to interact with BrainVISA and to call system commands.
  Here are these functions :

    * :py:meth:`write`, :py:meth:`warning`, :py:meth:`error` : prints a message, either in the graphical process window (in GUI mode) or in the terminal (in batch mode).
    * :py:meth:`log` : writes a message in the BrainVISA log file.
    * :py:meth:`ask`, :py:meth:`dialog` : asks a question to the user.
    * :py:meth:`temporary` : creates a temporary file.
    * :py:meth:`system`: calls a system command.
    * :py:meth:`runProcess` : runs a BrainVISA process.
    * :py:meth:`checkInterruption` : defines a breakpoint.

  """
  remote = None

  class UserInterruption( Exception ):
    def __init__( self ):
      Exception.__init__( self, _t_( 'user interruption' ) )

  class UserInterruptionStep( Exception ):
    def __init__( self ):
      Exception.__init__( self, _t_( 'user interruption of current step' ) )

  class StackInfo:
    def __init__( self, process ):
      self.process = process
      self.processCount = {}
      self.thread = None
      self.debug = None
      self.log = None
      self.time = time.localtime()

  def __init__( self, userLevel = None, debug = None ):
    if userLevel is None:
      self.userLevel = neuroConfig.userLevel
    else:
      self.userLevel = userLevel
    #self._processStack = []
    self._lock = threading.RLock()
    self._processStackThread = {}
    self._processStackHead = None
    self.manageExceptions = 1
    self._systemOutputLevel = 0
    self._systemLog = None
    self._systemLogFile = None

    self._interruptionRequest = None
    self._interruptionActions = {}
    self._interruptionActionsId = 0
    self._interruptionLock = threading.RLock()
    self._allowHistory = True

  def _processStack( self ):
    self._lock.acquire()
    try:
      stack = self._processStackThread[ threading.currentThread() ]
    except:
      stack = []
      self._processStackThread[ threading.currentThread() ] = stack
    self._lock.release()
    return stack

  def _popStack( self ):
    self._lock.acquire()
    stack = self._processStackThread[ threading.currentThread() ]
    stackinfo = stack.pop()
    if len( stack ) == 0:
      del self._processStackThread[ threading.currentThread() ]
    if stackinfo is self._processStackHead:
      self._processStackHead = None
    self._lock.release()
    return stackinfo

  def _pushStack( self, stackinfo ):
    self._lock.acquire()
    stack = self._processStack()
    stack.append( stackinfo )
    if self._processStackHead is None:
      self._processStackHead = stackinfo
    self._lock.release()

  def _stackTop( self ):
    stack = self._processStack()
    if len( stack ) == 0:
      return None
    return stack[-1]
  
  def _processStackParent( self ):
    stack = self._processStack()
    if len( stack ) == 0:
      return self._processStackHead
    return stack[-1]

  def _setArguments( self, _process, *args, **kwargs ):
    # Set arguments
    for i, v in enumerate( args ):
      n = _process.signature.keys()[ i ]
      _process._setImmutable( n, True )
      # performing this 2 pass loop allows to set parameters with
      # a forced value to immutable (ie non-linked) before actually
      # setting values and running links. This avoids a bunch of unnecessary
      # links to work (often several times)
    for ( n, v ) in kwargs.items():
      _process._setImmutable( n, True )

    for i, v in enumerate( args ):
      n = _process.signature.keys()[ i ]
      _process.setDefault( n, 0 )
      if v is not None:
        _process.setValue( n, v )
      else:
        setattr( _process, n, None )
    for ( n, v ) in kwargs.items():
      _process.setDefault( n, 0 )
      if v is not None:
        _process.setValue( n, v )
      else:
        setattr( _process, n, None )
    _process._clearImmutableParameters()
    _process.checkArguments()

  def _startProcess( self, _process, executionFunction, *args, **kwargs ):
    if not isinstance( _process, Process ):
      _process = getProcessInstance( _process )
    apply( self._setArguments, (_process,)+args, kwargs )
    # Launch process
    t = threading.Thread( target = self._processExecutionThread,
                          args = ( _process, executionFunction ) )
    t.start()
    return _process

  def runProcess( self, _process, *args, **kwargs ):
    """
    It is possible to call a sub-process in the current process by calling context.runProcess. 
    
    The first argument is the process identifier, which is either the filename wihtout extension of the process or its english name. 
    The other arguments are the values of the process parameters. All mandatory argument must have a value. 
    The function returns the value returned by the sub-process execution method.
    
    *Example*

    >>> context.runProcess( 'do_something', self.input, self.output, value = 3.14 )

    In this example, the process do_something is called with self.input as the first paramter value, self.ouput as the second parameter value and 3.14 to the parameter named value.
    """
    _process = getProcessInstance( _process )
    self.checkInterruption()
    apply( self._setArguments, (_process,)+args, kwargs )
    result = self._processExecution( _process, None )
    self.checkInterruption()
    return result


  @staticmethod
  def createContext():
    return ExecutionContext()


  def runInteractiveProcess( self, callMeAtTheEnd, process, *args, **kwargs ):
    """
    Runs a process in a new thread and calls a callback function when the execution is finished. 
    
    :param function callMeAtTheEnd: callback function which will be called the process execution is finished.
    :param process: id of the process which will be run.
    """
    context = self.createContext()
    process = getProcessInstance( process )
    self.checkInterruption()
    apply( self._setArguments, (process,)+args, kwargs )
    thread = threading.Thread( target = self._runInteractiveProcessThread,
      args = ( context, process, callMeAtTheEnd ) )
    thread.start()


  def _runInteractiveProcessThread( self, context, process, callMeAtTheEnd ):
    try:
      result = context.runProcess( process )
    except Exception, e:
      result = e
    callMeAtTheEnd( result )


  def _processExecutionThread( self, *args, **kwargs ):
    self._processExecution( *args, **kwargs )
    neuroHierarchy.databases.currentThreadCleanup()


  def _processExecution( self, process, executionFunction=None ):

    '''Execute the process "process". The value return is stored to avoid
    the garbage-collection of some of the objects created by the process
    itself (GUI for example).
    '''
    result = None
    stackTop = None
    process = getProcessInstance( process )
    stack = self._processStack()
    stackTop = self._processStackParent()

    if stackTop:
##      if neuroConfig.userLevel > 0:
##        self.write( '<img alt="" src="' + os.path.join( neuroConfig.iconPath, 'icon_process.png' ) + '" border="0">' \
##                    + _t_(process.name) + ' '\
##                    + str(process.instance) + '<p>' )
      # Count process execution
      count = stackTop.processCount.get( process._id, 0 )
      stackTop.processCount[ process._id ] = count + 1


    newStackTop = self.StackInfo( process )
    self._pushStack( newStackTop )
    ishead = not stackTop

    # Logging process start
    if not stackTop:
      process.isMainProcess = True

    try: # finally -> processFinished
      try: # show exception

        # check write parameters if the process is the main process (check all parameters in child nodes if it is a pipeline)
        # or if it has a parent which is not a pipeline that is to say, the current process is run throught context.runProcess
        if ishead:
          self._allWriteDiskItems = {}
        if ishead or (stackTop and stackTop.process._executionNode is None):
          writeParameters = []
          for parameterized, attribute, type in process.getAllParameters():
            if isinstance( type, WriteDiskItem ):
              item = getattr( parameterized, attribute )
              if item is not None:
                writeParameters.append(item)
            elif isinstance( type, ListOf ) and isinstance( type.contentType, WriteDiskItem ):
              itemList = getattr( parameterized, attribute )
              if itemList:
                writeParameters.extend(itemList)
          for item in writeParameters:
            dirname = os.path.dirname( item.fullPath() )
            if not os.path.exists( dirname ):
              safemkdir.makedirs( dirname )

            uuid=item.uuid()
            self._allWriteDiskItems[uuid] = [ item, item.modificationHash() ]

        if ishead:
          log = neuroConfig.mainLog
        else:
          if len( stack ) >= 2:
            log = stack[ -2 ].log
          else:
            # FIXME:
            # attaching to head log is not always the right solution
            # if a sub-process has parallel sub-nodes, then a new thread
            # and a new stack will be created, but the logs will not be
            # appended to the correct parent
            log = self._processStackHead.log
        if log is not None:
          #print "Create subLog for process ", process.name
          newStackTop.log = log.subLog()
          process._log = newStackTop.log
          content = '<html><body><h1>' + _t_(process.name) + '</h1><h2>' + _t_('Process identifier') + '</h2>' + process._id
          content += '<h2>' + _t_('Execution platform') +'</h2>'
          if(hasattr(process, 'executionWorkflow')):
            content += 'Soma-Workflow'
          else :
            content += 'BrainVISA'
            
          content += '<h2>' + _t_('Parameters') +'</h2>'
          for n in process.signature.keys():
            content += '<em>' + n + '</em> = ' + htmlEscape( str( getattr( process, n, None ) ) ) + '<p>'
          content += '<h2>' + _t_( 'Output' ) + '</h2>'
          try:
            #print "Create subTextLog for process ", process.name
            process._outputLog = log.subTextLog()
            process._outputLogFile = open( process._outputLog.fileName, 'w' )
            print >> process._outputLogFile, content
            process._outputLogFile.flush()
            content = process._outputLog
          except:
            content += '<font color=red>' + _t_('Unabled to open log file') + '</font></html></body>'
            process._outputLog = None
            process._outputLogFile = None
          if stackTop:
            self._lastStartProcessLogItem = log.append( _t_(process.name), html=content,
                      children=newStackTop.log, icon='icon_process.png' )
          else:
            self._lastStartProcessLogItem = log.append( _t_(process.name) + ' ' + str(process.instance), html=content,
                      children=newStackTop.log, icon='icon_process.png' )
        else:
          newStackTop.log = None

        if ishead and self._allowHistory:
          self._historyBookEvent, self._historyBooksContext = HistoryBook.storeProcessStart( self, process )

        self._processStarted()
        newStackTop.thread = threading.currentThread()

        self._lastProcessRaisedException = False
        # Check arguments and conversions
        def _getConvertedValue( v, p ):
          # v: value
          # p: parameter (Read/WriteDiskItem)
          if v and getattr(v, "type", None) and ( ( not isSameDiskItemType( v.type, p.type ) ) or v.format not in p.formats ):
            c = None
            formats = [ p.preferredFormat ] \
              + [ f for f in p.formats if f is not p.preferredFormat ]
            for destinationFormat in formats:
              converter = getConverter( (v.type, v.format), (p.type, destinationFormat), checkUpdate=False )
              if converter:
                tmp = self.temporary( destinationFormat )
                tmp.type = v.type
                tmp.copyAttributes( v )
                convargs = { 'read' : v, 'write' : tmp }
                c = getProcessInstance( converter.name )
                if c is not None:
                  try:
                    apply( self._setArguments, (c,), convargs )
                    if c.write is not None:
                      break
                  except:
                    pass
            ##              if not converter: raise Exception( _t_('Cannot convert format <em>%s</em> to format <em>%s</em> for parameter <em>%s</em>') % ( _t_( v.format.name ), _t_( destinationFormat.name ), n ) )
            ##              tmp = self.temporary( destinationFormat )
            ##              tmp.type = v.type
            ##              tmp.copyAttributes( v )
            ##              self.runProcess( converter.name, read = v, write = tmp )
            if not c: raise Exception( HTMLMessage(_t_('Cannot convert format <em>%s</em> to format <em>%s</em> for parameter <em>%s</em>') % ( _t_( v.format.name ), _t_( destinationFormat.name ), n )) )
            self.runProcess( c )
            return tmp

        converter = None
        for ( n, p ) in process.signature.items():
                  
          
          if isinstance( p, ReadDiskItem ) and p.enableConversion:            
            v = getattr( process, n )
            tmp = _getConvertedValue( v, p )
            if tmp is not None:
              process.setConvertedValue( n, tmp )
          elif isinstance( p, WriteDiskItem ):
            v = getattr( process, n )
   
            #test if data is locked
            if  (v is not None ):
              if v.isLockData() and (process.execution.im_func != super(process.__class__, process).execution.im_func ) :
                # raise an error if the diskitem is an output of a process which has an execution function (not the default execution function of the Process class)
                raise IOError ( HTMLMessage(_t_('<b>The file: <em>%s</em> is locked</b>. It cannot be opened for writing. You can unlock it if necessary using  the contextual menu of the parameter %s') % ( str(v), n ) ))
            #end test if data is locked  
   
            
            if v is not None:
              v.createParentDirectory()
          elif isinstance( p, ListOf ):
            needsconv = False
            converted = []
            lv = getattr( process, n )
            for v in lv:
              tmp = _getConvertedValue( v, p.contentType )
              if tmp is not None:
                converted.append( tmp )
                needsconv = True
              else:
                converted.append( v )
            if needsconv:
              process.setConvertedValue( n, converted )
        if executionFunction is None:
          if(hasattr(process, 'executionWorkflow')) :
            from soma_workflow.client import WorkflowController, Workflow, Helper
            jobs, dependencies, root_group = process.executionWorkflow( self )
            workflow = Workflow(jobs = jobs, dependencies = dependencies, root_group = root_group)
            controller = WorkflowController()
            wid = controller.submit_workflow(workflow=workflow, name=process.name)
            Helper.wait_workflow(wid, controller)
            list_failed_jobs = Helper.list_failed_jobs(wid, controller)
            result = workflow
            if (len(list_failed_jobs) > 0):
              raise Exception('run through soma workflow failed, see details with soma-workflow-gui')
            else :
              # Delete the submitted workflow
              controller.delete_workflow(wid, True)
          else :
            result = process.execution( self )
        else:
          result = executionFunction( self )
      except Exception, e:
        self._lastProcessRaisedException = True
        try:
          self._showException()
        except SystemExit, e:
          neuroConfig.exitValue = e.args[0]
        except:
          import traceback
          info = sys.exc_info()
          sys.stderr.write('\n%s: %s\n' % (info[0].__name__, unicode(info[1])))
          traceback.print_tb(info[2], None, sys.stderr)
        logException( context=self )
        if self._depth() != 1 or not self.manageExceptions:
          raise
    finally:
      self._processFinished( result )
      process.restoreConvertedValues()

      # update history
      if self._allowHistory and ishead and hasattr( self, '_historyBookEvent' ) and self._historyBookEvent is not None: # one of these conditions may be false when an exception occurs during execution
        HistoryBook.storeProcessFinished( self, process, self._historyBookEvent, self._historyBooksContext )
        self._historyBookEvent = None
        self._historyBooksContext = None

      for item_hash in self._allWriteDiskItems.values():
        item, hash = item_hash
        if item.isReadable():
          if item.modificationHash() != hash:
            try:
              # do not try to insert in the database an item that doesn't have any reference to a database
              # or which is temporary
              if item.get("_database", None) and \
                ( not hasattr( item, '_isTemporary' ) \
                  or not item._isTemporary ):
                neuroHierarchy.databases.insertDiskItem( item, update=True )
            except NotInDatabaseError:
              pass
            except:
              showException()
            item_hash[ 1 ] = item.modificationHash()
        elif (process.isMainProcess): # clear unused minfs only when the main process is finished to avoid clearing minf that will be used in next steps
          item.clearMinf()

      # Close output log file
      if process._outputLogFile is not None:
        print >> process._outputLogFile, '</body></html>'
        process._outputLogFile.close()
        process.outputLogFile = None
      if process._outputLog is not None:
        process._outputLog.close()
        process._outputLog = None
      if process._log is not None:
        process._log.close()
        process._log = None
      # Expand log to put sublogs inline
      log = self._stackTop().log
      if log is not None:
        if process.isMainProcess and neuroConfig.mainLog:
          neuroConfig.mainLog.expand()
        if self._depth() == 1:
          self._lastStartProcessLogItem = None
      self._popStack().thread = None ##### WARNING !!! not pop()
    return result

  def _currentProcess( self ):
    stackTop = self._stackTop()
    if stackTop is None:
      return None
    else:
      return stackTop.process

  def _depth( self ):
    return len( self._processStack() )

  def _showSystemOutput( self ):
    return self._systemOutputLevel >= 0 and self.userLevel >= self._systemOutputLevel

  def _processStarted( self ):
    if self._currentProcess().isMainProcess:
      msg = '<p><img alt="" src="' + \
            os.path.join( neuroConfig.iconPath, 'process_start.png' ) + \
            '" border="0"><em>' + _t_( 'Process <b>%s</b> started on %s') % \
            ( _t_(self._currentProcess().name ),
              time.strftime( _t_( '%Y/%m/%d %H:%M' ),
                             self._stackTop().time ) ) + \
            '</em></p>'
      self.write( msg )

  def _processFinished( self, result ):
    if self._currentProcess().isMainProcess:
      finalTime = time.localtime()
      elapsed = calendar.timegm( finalTime ) - calendar.timegm( self._stackTop().time )
      msg = '<br><img alt="" src="' + \
            os.path.join( neuroConfig.iconPath, 'process_end.png' ) + \
            '" border="0"><em>' + _t_( 'Process <b>%s</b> finished on %s (%s)' ) % \
        ( _t_(self._currentProcess().name),
          time.strftime( _t_( '%Y/%m/%d %H:%M' ), finalTime), timeDifferenceToString( elapsed ) ) + \
        '</em>'
      self.write( msg )

  def system( self, *args, **kwargs ):
    """
    This function is used to call system commands. It is very similar to functions like os.system in Python and system in C. The main difference is the management of messages sent on standard output. These messages are intercepted and reported in BrainVISA interface according to the current execution context.

    If the command is given as one argument, it is converted to a string and passed to the system. If there are several arguments, each argument is converted to a string, surrounded by simple quotes and all elements are joined, separated by spaces. The resulting command is passed to the system. The second method is recommended because the usage of quotes enables to pass arguments that contain spaces. The function returns the value returned by the system command.
    
    *Example*
    
    >>> arg1 = 'x'
    >>> arg2 = 'y z'
    >>> context.system( 'command ' + arg1 + ' ' + arg2 )
    >>> context.system( 'command', arg1, arg2 )
    
    The first call generates the command command x y z which calls the commands with 3 parameters. The second call generates the command 'command' 'x' 'y z' which calls the command with two parameters.
    """
    self._systemOutputLevel = kwargs.get( 'outputLevel', 0 )
    ignoreReturnValue = kwargs.get( 'ignoreReturnValue', 0 )
    command = [str(i) for i in args]

    ret = self._system( command, self._systemStdout, self._systemStderr )
    if ret and not ignoreReturnValue:
      raise RuntimeError( _t_( 'System command exited with non null value : %s' ) % str( ret ) )
    return ret

  def _systemStdout( self, line, logFile=None ):
    if logFile is None:
      logFile = self._systemLogFile
    if line and logFile is not None and self._showSystemOutput():
      if line[ -1 ] not in ( '\b', '\r' ):
        logFile.write( htmlEscape(line))
        logFile.flush()

  def _systemStderr( self, line, logFile=None ):
    if logFile is None:
      logFile = self._systemLogFile
    if line:
      lineInHTML = '<font color=red>' + htmlEscape(line) + '</font>'
      self.write( lineInHTML )
    if logFile is not None and line:
      logFile.write( lineInHTML )
      logFile.flush()

  def _system( self, command, stdoutAction = None, stderrAction = None ):
    self.checkInterruption()
    stackTop = self._stackTop()

    if type( command ) in types.StringTypes:
      c = Command( command )
    else:
      c = Command( *command )

    # Logging system call start
    if stackTop:
      log = stackTop.log
    else:
      log = neuroConfig.mainLog
    systemLogFile = None
    systemLog = None
    if log is not None:
      #print "Create subTextLog for command ", command[0]
      systemLog = log.subTextLog()
      self._systemLog = systemLog
      systemLogFile = open( systemLog.fileName, 'w' )
      self._systemLogFile = systemLogFile
      log.append( c.commandName(),
                  html=systemLog,
                  icon='icon_system.png' )
    try:
      commandName = distutils.spawn.find_executable( c.commandName() )
      if not commandName:
        commandName = c.commandName()
      if systemLogFile:
        print >> systemLogFile, '<html><body><h1>' + commandName +' </h1><h2>' +_t_('Command line') + \
          '</h2><code>' + htmlEscape( str( c ) ) + '</code></h2><h2>' + _t_('Output') + '</h2><pre>'
        systemLogFile.flush()

  ##    if self._showSystemOutput() > 0:
  ##      self.write( '<img alt="" src="' + os.path.join( neuroConfig.iconPath, 'icon_system.png' ) + '">' + c.commandName() + '<p>' )

      # Set environment for the command
      if (not commandName.startswith(os.path.dirname(neuroConfig.mainPath))): # external command
        if neuroConfig.brainvisaSysEnv:
          c.setEnvironment(neuroConfig.brainvisaSysEnv.getVariables())

      if stdoutAction is not None:
        if stdoutAction is self._systemStdout:
          c.setStdoutAction( lambda line: stdoutAction( line,
            logFile=systemLogFile ) )
        else:
          c.setStdoutAction( stdoutAction )
      if stderrAction is not None:
        if stderrAction is self._systemStderr:
          c.setStderrAction( lambda line: stderrAction( line,
            logFile=systemLogFile ) )
        else:
          c.setStderrAction( stderrAction )

      retry = 1
      first=True
      while (retry > 0):
        try:
          c.start()
          retry=0
        except RuntimeError, e:
          if c.error() == QProcess.FailedToStart:
            if first:
              retry = 2
              first=False
            else:
              retry=retry-1
            self._systemStderr(e.message+"\n", systemLogFile)
            if (retry != 0):
               self._systemStderr("Try to restart the command...\n", systemLogFile)
            else:
              raise e
          else:
            raise e

      intActionId = self._addInterruptionAction( c.stop )
      try:
        try:
          result = c.wait()
        finally:
          self._removeInterruptionAction( intActionId )
      except Command.UserInterruption:
        pass
      self.checkInterruption()
      if systemLogFile is not None:
        print >> systemLogFile, '</pre><h2>' + _t_('Result') + '</h2>' + _t_('Value returned') + ' = ' + str( result ) + '</body></html>'
    finally:
      if systemLogFile is not None:
        systemLogFile.close()
        self._systemLogFile = None
      if systemLog is not None:
        systemLog.close()
      # no need to expand the log associated to the command as it is the log of the parent process,
      # it will be expanded at the end of the process
      # unless we are not during a process execution...
      if log is not None and log is not neuroConfig.mainLog and \
          self._processStackHead is None:
        log.expand()
        self._systemLog = None
    return result

  def temporary( self, format, diskItemType = None ):
    """
    This method enables to create a temporary DiskItem. The argument format is the temporary data format. The optional argument type is the data type. It generates one or several unique filenames (according to the format) in the temporary directory of BrainVISA (it can be changed in BrainVISA configuration). No file is created by this function. The process has to create it. The temporary files are deleted automatically when the temporary diskitem returned by the function is no later used.
    
    *Example*
    
    >>> tmp = context.temporary( 'GIS image' )
    >>> context.runProcess( 'threshold', self.input, tmp, self.threshold )
    >>> tmp2 = context.temporary( 'GIS image' )
    >>> context.system( 'erosion', '-i', tmp.fullPath(), '-o', tmp2.fullPath(), '-s', self.size )
    >>> del tmp

    In this example, a temporary data in GIS format is created and it is used to store the output of the process threshold. Then a new temporary data is created to store the output of a command line. At the end, the variable tmp is deleted, so the temporary data is no more referenced and the corresponding files are deleted.
    """
    result = getTemporary( format, diskItemType )
    return result

  def write( self, *messages, **kwargs ):
    """
     This method is used to print information messages during the process execution. All arguments are converted into strings and joined to form the message. This message may contain HTML tags for an improved display. The result vary according to the context. If the process is run via its graphical interface, the message is displayed in the process window. If the process is run via a script, the message is displayed in the terminal. The message can also be ignored if the process is called automatically by brainvisa or another process.
    """
    self.checkInterruption()
    if messages:
      msg = u' '.join( unicode( i ) for i in messages )
      self._writeMessageInLogFile(msg)
      self._write( msg )

  def _writeMessageInLogFile(self, msg):
    stackTop = self._stackTop()
    if stackTop:
      outputLogFile = stackTop.process._outputLogFile
      if outputLogFile and not outputLogFile.closed:
        print >> outputLogFile, msg
        outputLogFile.flush()
        
  def _write( self, html ):
    if not hasattr( self, '_writeHTMLParser' ):
      self._writeHTMLParser = htmllib.HTMLParser( formatter.AbstractFormatter(
        formatter.DumbWriter( sys.stdout, 80 ) ) )
    self._writeHTMLParser.feed( html + '<br>\n' )

  def warning( self, *messages ):
    """
    This method is used to print a warning message. This function adds some HTML tags to change the appearance of the message and calls the :py:meth:`write` function.
    """
    self.checkInterruption()
    bmsg = '<table width=100% border=1><tr><td><font color=orange><img alt="WARNING: " src="' \
      + os.path.join( neuroConfig.iconPath, 'warning.png' ) + '">'
    emsg = '</font></td></tr></table>'
    apply( self.write, (bmsg, ) + messages + ( emsg, ) )

  def error( self, *messages ):
    """
    This method is used to print an error message. Like the above function, it adds some HTML tags to change the appearance of the message and calls :py:meth:`write` function.
    """
    self.checkInterruption()
    bmsg = '<table width=100% border=1><tr><td><font color=red><img alt="ERROR: " src="' \
      + os.path.join( neuroConfig.iconPath, 'error.png' ) + '">'
    emsg = '</font></td></tr></table>'
    apply( self.write, (bmsg, ) + messages + ( emsg, ) )

  def ask( self, message, *buttons, **kwargs):
    """
    This method asks a question to the user. The message is displayed and the user is invited to choose a value among the propositions. The method returns the index of the chosen value, beginning by 0. If the answer is not valid, the returned value is -1. Sometimes, when the process is called automatically (in batch mode), these calls to context.ask are ignored and return directly -1 without asking question.

    *Example*

>>> if context.ask( 'Is the result ok ?', 'yes', 'no') == 1:
>>>  try_again()

    """
    self.checkInterruption()
    self.write( '<pre>' + message )
    i = 0
    for b in buttons:
      self.write( '  %d: %s' % ( i, str(b) ) )
      i += 1
    sys.stdout.write( 'Choice: ' )
    sys.stdout.flush()
    line = sys.stdin.readline()[:-1]
    self.write( '</pre>' )
    try:
      result = int( line )
    except:
      result = None
    return result


  def dialog( self, *args ):
    """
    This method is available only in a graphical context. Like ask, it is used to ask a question to the user, but the dialog interface is customisable. It is possible to add a signature to the dialog : fields that the user has to fill in.

    *Example*

>>> dial = context.dialog( 1, 'Enter a value', Signature( 'param', Number() ), _t_( 'OK' ), _t_( 'Cancel' ) )
>>> dial.setValue( 'param', 0 )
>>> r = dial.call()
>>> if r == 0:
>>>   v=dial.getValue( 'param' )
            
    """
    self.checkInterruption()
    return None

  def _showException( self, showCallStack = False ):
    stackTop = self._stackTop()
    try:
      self.checkInterruption()
    except:
      pass

    beforeError=_t_( 'in <em>%s</em>' ) % ( _t_(stackTop.process.name) + ' ' + str( stackTop.process.instance ))
    exceptionType, exceptionMessage, _traceBack = sys.exc_info()

    msgFull = self._messageFromException(beforeError, (exceptionType, exceptionMessage, _traceBack  ))
    msgBasic = self._messageFromException(beforeError, (exceptionType, exceptionMessage, None  ))

    self.checkInterruption()

    isNonExpertUser = neuroConfig.userLevel<2
    if(isNonExpertUser):
      self._write( msgBasic )
    else:
      self._write( msgFull )
    self._writeMessageInLogFile(msgFull)

    if neuroConfig.fastStart and not neuroConfig.gui:
      sys.exit( 1 )

  def showException( self, beforeError='', afterError='', exceptionInfo=None ):
    '''same as the global brainvisa.processing.neuroException.showException()
    but displays in the current context (the process output box for instance)
    '''
    if exceptionInfo is None:
      exceptionInfo = sys.exc_info()
    stackTop = self._stackTop()

    if not beforeError:
      beforeError=_t_( 'in <em>%s</em>' ) % ( _t_(stackTop.process.name) + ' ' + str( stackTop.process.instance ))
    exceptionType, exceptionMessage, _traceBack = exceptionInfo

    msgFull = self._messageFromException(beforeError, (exceptionType, exceptionMessage, _traceBack ), afterError=afterError)

    isNonExpertUser = neuroConfig.userLevel<2
    if(isNonExpertUser):
      msgBasic = self._messageFromException(beforeError, (exceptionType, exceptionMessage, None  ))
      self._write( msgBasic )
    else:
      self._write( msgFull )
    self._writeMessageInLogFile( msgFull )


  def _messageFromException(self, beforeError, exceptionInfo, afterError=''):
    exceptionMsgFull = exceptionMessageHTML(exceptionInfo, beforeError=beforeError, afterError=afterError) + '<hr>' + exceptionTracebackHTML(exceptionInfo)
    return '<table width=100% border=1><tr><td>' + exceptionMsgFull + '</td></tr></table>'
  
  def checkInterruption( self ):
    """
    This function is used to define breakpoints. When the process execution reach a breakpoint, the user can interrupt the process. There are 4 types of breakpoints automatically added :

    * before each system call (context.system)
    * after each system call (context.system)
    * before each sub-process call (context.runProcess)
    * after each sub-process call (context.runProcess)

    To allow the user to interrupt the process at another place, you have to use the function context.checkInterruption. If the user has clicked on the Interrupt button while the process runs, it will stop when reaching the checkInterruption point.
    """
    self._interruptionLock.acquire()
    try:
      self._checkInterruption()
      exception = self._interruptionRequest
      if exception is not None:
        self._interruptionRequest = None
        raise exception
    finally:
      self._interruptionLock.release()


  def _checkInterruption( self ):
    self._interruptionLock.acquire()
    try:
      if self._interruptionRequest is not None:
        for function, args, kwargs in self._interruptionActions.values():
          function( *args, **kwargs )
        self._interruptionActions.clear()
    finally:
      self._interruptionLock.release()
    return None

  def _addInterruptionAction( self, function, *args, **kwargs ):
    self._interruptionLock.acquire()
    try:
      result = self._interruptionActionsId
      self._interruptionActionsId += 1
      self._interruptionActions[ result ] = ( function, args, kwargs )
    finally:
      self._interruptionLock.release()
    return result

  def _removeInterruptionAction( self, number ):
    self._interruptionLock.acquire()
    try:
      if self._interruptionActions.has_key( number ):
        del self._interruptionActions[ number ]
    finally:
      self._interruptionLock.release()

  def _setInterruptionRequest( self, interruptionRequest ):
    self._interruptionLock.acquire()
    try:
      self._interruptionRequest = interruptionRequest
      self._checkInterruption()
    finally:
      self._interruptionLock.release()


  def log( self, *args, **kwargs ):
    """
    `context.log(what, when=None, html='', children=[], icon=None)`
    
    This method is used to add a message to BrainVISA log. The first parameter what is the name of the entry in the log, the message to write is in the html parameter.
    """
    stackTop = self._stackTop()
    if stackTop:
      logFile = stackTop.log
    else:
      logFile = neuroConfig.mainLog
    if logFile is not None:
      logFile.append( *args, **kwargs )


  def getConverter( self, source, dest, checkUpdate=True ):
    """
    Gets a converter process which can convert the source diskitem from its format to the destination format.
    """
    # Check and convert source type
    if isinstance( source, DiskItem ):
      source = ( source.type, source.format )
    elif isinstance( source, ReadDiskItem ):
      if source.formats:
        source = ( source.type, source.formats[ 0 ] )
      else:
        source = ( source.type, None )

    # Check and convert dest type
    if isinstance( dest, DiskItem ):
      dest = ( dest.type, dest.format )
    elif isinstance( dest, ReadDiskItem ):
      if dest.formats:
        dest = ( dest.type, dest.formats[ 0 ] )
      else:
        dest = ( dest.type, None )
    st, sf = source
    dt, df = dest
    return getConverter( ( getDiskItemType( st ), getFormat( sf ) ),
                         ( getDiskItemType( dt ), getFormat( df ) ), checkUpdate=checkUpdate )

  def createProcessExecutionEvent( self ):
    from brainvisa.history import ProcessExecutionEvent
    event = ProcessExecutionEvent()
    process = None
    if hasattr( self, 'process' ):
      process = self.process
    stack = self._processStack()
    if stack:
      if process is None:
        process = stack[0].process
      log = stack[0].log
      if log is not None:
        event.setLog( log )
    event.setProcess( process )
    return event

  def _attachProgress( self, parent, count=None, process=None ):
    '''Create a new ProgressInfo object.
    If parent is provided, it is the parent ProgressInfo, or the parent
    process. If not specified, the new ProgressInfo will be attached to the
    top-level ProgressInfo in the context.
    count is the number of children that the new ProgressInfo will hold. It is
    not the maximum value of a numeric progress value (see progress() method).
    process is the current (child) process which will be attached with the new
    ProgressInfo.

    This method is called internally in pipeline execution nodes. Regular
    processes need not to call it directly. They should call getProcessInfo()
    instead.
    '''
    if parent is not None:
      parent, parentproc = self._findProgressInfo( parent )
    if parent is None:
      parent = self._topProgressinfo()
      #if parent is not None and len( parent.children ) == 0:
        #parent.childrendone = 0 # reset
    if parent is None:
      parent = ProgressInfo()
      self._progressinfo = weakref.ref( parent )
      if process is None:
        pi = parent
        pi.children = [ None ] * count
      else:
        pi = ProgressInfo( parent, count, process=process )
    else:
      pi = ProgressInfo( parent, count, process=process )
    pig = self._topProgressinfo()
    if process is not None:
      plist = getattr( pig, 'processes', None )
      if plist is None:
        plist = weakref.WeakKeyDictionary()
        pig.processes = plist
      plist[ process ] = weakref.ref( pi )
    return pi

  def getProgressInfo( self, process, childrencount=None, parent=None ):
    '''Get the progress info for a given process or execution node, or create
    one if none already exists.
    A regular process may call it.
    
    The output is a tuple containing the ProgressInfo and the process itself,
    just in case the input process is in fact a ProgressInfo instance.
    A ProgressInfo has no hard reference in BrainVISA: when you don't need
    it anymore, it is destroyed via Python reference counting, and is
    considered done 100% for its parent.
    
    :param childrencount: it is the number of children that the process will have, and is
      not the same as the own count of the process in itself, which is in
      addition to children (and independent), and specified when using the
      progress() method.
    '''
    pinfo, process = self._findProgressInfo( process )
    if pinfo is None:
      if process is None:
        pinfo = self._topProgressinfo()
      if pinfo is None:
        pinfo = self._attachProgress( parent=parent, process=process,
          count=childrencount )
    return pinfo, process

  def _topProgressinfo( self ):
    '''internal.'''
    if hasattr( self, '_progressinfo' ):
      return self._progressinfo()
    return None

  def _findProgressInfo( self, processOrProgress ):
    '''internal.'''
    if processOrProgress is None:
      return None, None
    if isinstance( processOrProgress, ProgressInfo ):
      return processOrProgress, getattr( processOrProgress, 'process', None )
    # in case it is a ProcessExecutionNode
    down = True
    while down:
      down = False
      if isinstance( processOrProgress, ExecutionNode ) and \
        hasattr( processOrProgress, '_process' ):
          processOrProgress = processOrProgress._process
          down = True
      if not isinstance( processOrProgress, ExecutionNode ) and \
        hasattr( processOrProgress, '_executionNode' ):
          p = processOrProgress._executionNode
          if p is not None:
            processOrProgress = p
            down = True
    if hasattr( processOrProgress, '_progressinfo' ):
      return processOrProgress._progressinfo, processOrProgress
    pinfo = getattr( self, '_progressinfo', None )
    if pinfo is None:
      return None, processOrProgress
    procs = getattr( self._topProgressinfo(), 'processes', None )
    if procs is None:
      return None, processOrProgress
    pi = procs.get( processOrProgress, None )
    if pi is not None:
      pi = pi()
    return pi, processOrProgress

  def progress( self, value=None, count=None, process=None ):
    '''Set the progress information for the parent process or ProgressInfo
    instance, and output it using the context output mechanisms.
    
    :param value: is the progress value to set. If none, the value will not be changed, but the current status will be shown.
    
    :param count: is the maximum value for the process own progress value (not taking children into account).
    
    :param process: is either the calling process, or the ProgressInfo.
    '''
    if value is not None:
      pinfo, process = self.getProgressInfo( process )
      pinfo.setValue( value, count )
    tpi = self._topProgressinfo()
    if tpi is not None:
      self.showProgress( tpi.value() * 100 )

  def showProgress( self, value, count=None ):
    '''Output the given progress value. This is just the output method which
    is overriden in subclassed contexts.
    
    Users should normally not call it directory, but use progress() instead.
    '''
    if count is None:
      self.write( 'progress:', value, '% ...' )
    else:
      self.write( 'progress:', value, '/', count, '...' )

#----------------------------------------------------------------------------
class ProgressInfo( object ):
  '''ProgressInfo is a tree-like structure for progression information in a
  process or a pipeline. The final goal is to provide feedback to the user via
  a progress bar. ProgressInfo has children for sub-processes (when used in a
  pipeline), or a local value for its own progression.
  
  A ProgressInfo normally registers itself in the calling Process, and is
  destroyed when the process is destroyed, or when the process _progressinfo
  variable is deleted.
  '''
  def __init__( self, parent=None, count=None, process=None ):
    '''
    :param parent: is a ProgressInfo instance.
    :param count: is a number of children which will be attached.
    :param process: is the calling process.
    '''
    if count is None:
      self.children = []
    else:
      self.children = [ None ] * count
    self.done = False
    self.childrendone = 0
    if parent is not None:
      parent.attach( self )
      self.parent = parent # prevent parent from deleting
    self._localvalue = 0.
    self._localcount = None
    if process is not None:
      self.process = weakref.ref( process )
      #process._progressinfo = self
    else:
      self.process = None

  def __del__( self ):
    if self.process is not None:
      proc = self.process()
      if proc is not None and hasattr( proc, '_progressinfo' ):
        del proc._progressinfo

  def value( self ):
    '''Calculate the progress value including those of children.
    '''
    if self.done:
      return 1.
    n = self.childrendone + len( self.children )
    if self._localcount is not None:
      n += 1 # self._localcount
    if n == 0:
      return self._localvalue
    done = float( self.childrendone )
    for c in self.children:
      if c is not None:
        done += c().value()
        if c().done:
          self._delchild( c )
    done += self._localvalue
    return done / n

  def setValue( self, value, count=None ):
    '''Set the ProgressInfo own progress value (not its children)
    '''
    if count is None:
      count = self._localcount
    else:
      self._localcount = count
    if self.done:
      if ( count is not None and value != count ) \
        or ( count is None and value != 1. ):
        self.done = False
    if count:
      value = float( value ) / count
    self._localvalue = value

  def setdone( self ):
    '''Marks the ProgressInfo as done 100%, the children are detached.
    '''
    self.done = True
    del self.children

  def _delchild( self, child ):
    if child in self.children:
      del self.children[ self.children.index( child ) ]
      self.childrendone += 1
    if len( self.children ) == 0:
      self.done = True

  def attach( self, pinfo ):
    '''Don't use this method directly, it is part of the internal mechanism,
    called by the constructor.
    '''
    wr = weakref.ref( pinfo, self._delchild )
    if None in self.children:
      i = self.children.index( None )
      self.children[i] = wr
    else:
      self.children.append( wr )
    self.done = False

  def debugDump( self ):
    print 'ProgressInfo:', self
    if hasattr( self, 'process' ):
      print '  process:', self.process
    print '  local value:', self._localvalue, '/', self._localcount
    print '  value:', self.value()
    print '  children:', len( self.children ) + self.childrendone
    print '  done:', self.childrendone
    print '  not started:', len( [ x for x in self.children if x is None ] )
    print '  running:'
    todo = [ ( x(), 1 ) for x in self.children if x is not None ]
    while len( todo ) != 0:
      pi, indent = todo[0]
      del todo[0]
      print '  ' * indent, pi, pi.childrendone,
      if hasattr( pi, 'process' ):
        print pi.process()
      else:
        print
      todo = [ ( x(), indent+1 ) for x in pi.children if x is not None ] + todo


#----------------------------------------------------------------------------
class ProcessInfo:
  """
  This object stores information about a process. Such objects are created at BrainVISA startup when the processes are loaded.
  
  .. py:attribute:: id
  
    Id of the process. It is the name of the file without extension in lowercase.
  
  .. py:attribute:: name
  
    Name of the process as it is displayed in the GUI.
  
  .. py:attribute:: signature
    
    Process excepted parameters.
  
  .. py:attribute:: userLevel
  
    User level needed to see the process.
  
  .. py:attribute:: category
    
    Process category path: <toolbox>/<category1>/<category2>/...
    
  .. py:attribute:: showMaximized
  
    Process window maximized state.
  
  .. py:attribute:: fileName
  
    Path to the file containing the source code of the process.
  
  .. py:attribute:: roles
  
    Tuple containing the specific roles of the process: viewer, converter, editor, importer.
  
  .. py:attribute:: valid
  
    False if the validation method of the process fails - default True.
  
  .. py:attribute:: procdoc
  
    The content of the .procdoc file associated to this process in a dictionary. It represents the documentation of the process.
  
  .. py:attribute:: toolbox
  
    The id of the toolbox containing the process.
  
  .. py:attribute:: module
  
    Module path to the source of the process related to the toolbox directory. 
    <processes>.<category1>...<process>
  """
  def __init__( self, id, name, signature, userLevel, category, fileName, roles, toolbox, module=None, showMaximized=False ):
    self.id = id
    self.name = name
    #TODO: Signature cannot be pickeled
    self.signature = None
    self.userLevel = userLevel
    self.category = category
    self.fileName = fileName
    self.roles = tuple( roles )
    self.valid=True # set to False if process' validation method fails
    self.procdoc = None
    self.toolbox = toolbox
    self.showMaximized = showMaximized

    if module is None:
      for p in ( neuroConfig.mainPath, neuroConfig.homeBrainVISADir ):
        if self.fileName.startswith( p ):
          module = split_path( self.fileName[ len( p ) + 1: ] )
      if module:
        if module[0] == 'toolboxes':
          module = module[ 2: ]
        module = '.'.join( module )
        if module.endswith( '.py' ):
          module = module[ :-3 ]
    self.module = module


  def html( self ):
    """
    Returns the process information in html format.
    """
    return '\n'.join( ['<b>' + n + ': </b>' + unicode( getattr( self, n ) ) + \
                        '<br>\n' for n in ( 'id', 'name', 'toolbox', 'signature',
                                            'userLevel', 'category',
                                            'fileName', 'roles' )] )

#----------------------------------------------------------------------------
def getProcessInfo( processId ):
  """
  Gets information about the process whose id is given in parameter.
  
  :return type: :py:class:`ProcessInfo`
  """
  if isinstance( processId, ProcessInfo ):
    result = processId
  else:
    if type(processId) in types.StringTypes:
      processId = processId.lower()
    result = _processesInfo.get( processId )
    if result is None:
      process = getProcess( processId, checkUpdate=False )
      if process is not None:
        result = _processesInfo.get( process._id.lower() )
  return result

#----------------------------------------------------------------------------
def addProcessInfo( processId, processInfo ):
  """Stores information about the process."""
  _processesInfo[ processId.lower() ] = processInfo

#----------------------------------------------------------------------------
def getProcess( processId, ignoreValidation=False, checkUpdate=True ):
  """
  Gets the class associated to the process id given in parameter.
  
  When the processes are loaded, a new class called :py:class:`NewProcess` is created for each process. 
  This class inherits from :py:class:`Process` and adds an instance counter which is incremented each time a new instance of the process is created.
  
  :param processId: the id or the name of the process, or a dictionary *{'type' : 'iteration|distributed|selection', 'children' : [...] }* to create an :py:class:`IterationProcess`, a :py:class:`DistributedProcess` or a :py:class:`SelectionProcess`.
  
  :param boolean ignoreValidation: if True the validation function of the process won't be executed if the process need to be reloaded - default False.
  
  :param boolean checkUpdate: If True, the modification date of the source file of the process will be checked. If the file has been modified since the process loading, it may need to be reloaded. The user will be asked what he wants to do. Default True.
  
  :returns: a :py:class:`NewProcess` class which inherits from :py:class:`Process`.
  """
  global _askUpdateProcess
  if processId is None: return None
  if isinstance( processId, Process ) or ( type(processId) in (types.ClassType, types.TypeType) and issubclass( processId, Process ) ) or isinstance( processId, weakref.ProxyType ):
    result = processId
    id = getattr( processId, '_id', None )
    if id is not None:
      process = getProcess( id, checkUpdate=False )
      if process is not None:
        result=process
  elif isinstance( processId, dict ):
    if processId[ 'type' ] == 'iteration':
      return IterationProcess( processId.get('name', 'Iteration'), [ getProcessInstance(i) for i in processId[ 'children' ] ] )
    elif processId[ 'type' ] == 'distributed':
      return DistributedProcess( processId.get('name', 'Distributed iteration'), [ getProcessInstance(i) for i in processId[ 'children' ] ] )
    elif processId['type'] == 'selection' :
      return SelectionProcess( processId.get('name', 'Selection'), [ getProcessInstance(i) for i in processId[ 'children' ] ] )
    else:
      raise TypeError( _t_( 'Unknown process type: %s' ) % ( unicode( processId['type'] ) ) )
  else:
    if type(processId) in types.StringTypes:
      processId=processId.lower()
    result = _processes.get( processId )
  if result is None:
    info = _processesInfo.get( processId )
    if info is None:
      info = _processesInfoByName.get( processId )
    if info is not None:
      result = _processes.get( info.id.lower() )
      if result is None:
        result = readProcess( info.fileName, ignoreValidation=ignoreValidation )
        checkUpdate=False
  if result is not None:
    # Check if process source file have changed
    if checkUpdate:
      fileName = getattr( result, '_fileName', None )
      if fileName is not None:
        ask = _askUpdateProcess.get( result._id, 0 )
        # if the user choosed never updating the process, no need to check if it needs update
        if (ask != 2):
          ntime = os.path.getmtime( fileName )
          if ntime > result._fileTime:
            update = 0
            if ask == 0:
              #if neuroConfig.userLevel > 0:
              r = defaultContext().ask( _t_( '%s has been modified, would you like to update the process <em>%s</em> processes ? You should close all processes windows before reloading a process.' ) % \
                ( result._fileName, _t_(result.name) ), _t_('Yes'), _t_('No'), _t_('Always'), _t_('Never') )
              if r == 0:
                update = 1
              elif r == 2:
                update = 1
                _askUpdateProcess[ result._id ] = 1
              elif r == 3:
                update = 0
                _askUpdateProcess[ result._id ] = 2
            elif ask == 1:
              update = 1
            if update:
              result = readProcess( fileName )
  return result

#----------------------------------------------------------------------------
def getProcessInstanceFromProcessEvent( event ):
  """
  Gets an instance of a process described in a :py:class:`brainvisa.history.ProcessExecutionEvent`.
  
  :param event: a :py:class:`brainvisa.history.ProcessExecutionEvent` that describes the process: its structure and its parameters.
  :returns: an instance of the :py:class:`NewProcess` class associated to the described process. Parameters may have been set.
  """
  pipelineStructure = event.content.get( 'id' )
  if pipelineStructure is None:
    pipelineStructure = event.content.get( 'pipelineStructure' )
  result = getProcessInstance( pipelineStructure )
  procs = set()
  if result is not None:
    # 1st pass: disable links to parameters which have a saved value
    selected = event.content.get( 'parameters', {} ).get( 'selected', {} )
    procs.add( result )
    for n, v in selected.iteritems():
      try:
        result._setImmutable( n, True )
      except KeyError:
        pass
    defaultp = event.content.get( 'parameters', {} ).get( 'default', {} )
    for n, v in defaultp.iteritems():
      try:
        result._setImmutable( n, True )
      except KeyError:
        pass
    stackp = [ ( result.executionNode(), k, e.get( 'parameters' ), 
                e[ 'selected' ],
                e.get( 'executionNodes', {} ) ) for k, e in
                event.content.get( 'executionNodes', {} ).iteritems() ]
    stack = list( stackp ) # copy list
    while stack:
      eNodeParent, eNodeName, eNodeParameters, eNodeSelected, eNodeChildren = stack.pop( 0 )
      eNode = eNodeParent.child( eNodeName )

      if eNode :
        eNode.setSelected( eNodeSelected )

        if eNodeParameters:
          for n, v in eNodeParameters[ 'selected' ].iteritems():
            try:
              eNode._setImmutable( n, True )
              procs.add( eNode )
            except KeyError:
              pass
          for n, v in eNodeParameters[ 'default' ].iteritems():
            try:
              eNode._setImmutable( n, True )
              procs.add( eNode )
            except KeyError:
              pass
        stackadd = [ ( eNode, k, e.get( 'parameters' ), e[ 'selected' ],
                  e.get( 'executionNodes', {} ) ) for k, e in eNodeChildren.iteritems() ]
        stackp += stackadd
        stack += stackadd

    # 2nd pass: now really set values
    for n, v in selected.iteritems():
      try:
        result.setValue( n, v, default=False )
      except KeyError:
        pass
    for n, v in defaultp.iteritems():
      try:
        result.setValue( n, v, default=True )
      except KeyError:
        pass
    stack = stackp
    for eNodeParent, eNodeName, eNodeParameters, eNodeSelected, eNodeChildren in stack:
      eNode = eNodeParent.child( eNodeName )

      if eNode :
        eNode.setSelected( eNodeSelected )

        if eNodeParameters:
          for n, v in eNodeParameters[ 'selected' ].iteritems():
            try:
              eNode.setValue( n, v, default=False )
            except KeyError:
              pass
          for n, v in eNodeParameters[ 'default' ].iteritems():
            try:
              eNode.setValue( n, v, default=True )
            except KeyError:
              pass
    for p in procs:
      p._clearImmutableParameters()

    windowGeometry = event.content.get( 'window' )
    if windowGeometry is not None:
      result._windowGeometry = windowGeometry
  return result


#----------------------------------------------------------------------------
def getProcessFromExecutionNode( node ):
  """
  Gets a process instance corresponding to the given execution node.
  
  :param node: a process :py:class:`ExecutionNode`
  :returns: According to the type of node, it returns:
  
    * a :py:class:`NewProcess` instance if the node is :py:class:`ProcessExecutionNode`,
    * an :py:class:`IterationProcess` if the node is a :py:class:`SerialExecutionNode`
    * a :py:class:`DistributedProcess` if the node is a :py:class:`ParallelExecutionNode`
    * a :py:class:`SelectionProcess` if the node is a :py:class:`SelectionExecutionNode`.
  """
  nt = type( node )
  if nt is ProcessExecutionNode:
    return node._process
  elif nt is SerialExecutionNode:
    return IterationProcess( node.name(), node.children() )
  elif nt is ParallelExecutionNode:
    return DistributedProcess( node.name(), node._children.values() )
  elif nt is SelectionExecutionNode:
    return SelectionProcess( node.name(), node.children() )

#----------------------------------------------------------------------------
def getProcessInstance( processIdClassOrInstance ):
  """
  Gets an instance of the process given in parameter.
  
  :param processIdClassOrInstance: a process id, name, class, instance, execution node, or a the name of a file containing a backup copy of a process. 
  :returns: an instance of the :py:class:`NewProcess` class associated to the described process.
  """
  if isinstance( processIdClassOrInstance, weakref.ProxyType ):
    processIdClassOrInstance = copy.copy( processIdClassOrInstance )
  result = getProcess( processIdClassOrInstance )
  if isinstance( processIdClassOrInstance, Process ):
    if result is processIdClassOrInstance or result is processIdClassOrInstance.__class__:
      result = processIdClassOrInstance
    else:
      event = ProcessExecutionEvent()
      event.setProcess( processIdClassOrInstance )
      result = getProcessInstanceFromProcessEvent( event )
  elif result is None:
    if isinstance( processIdClassOrInstance, ExecutionNode ):
      result = getProcessFromExecutionNode( processIdClassOrInstance )
    else:
      try:
        if (isinstance( processIdClassOrInstance, basestring ) or hasattr( processIdClassOrInstance, 'readline' )) and minfFormat( processIdClassOrInstance )[ 1 ] == minfHistory:
          event = readMinf( processIdClassOrInstance )[0]
          result = getProcessInstanceFromProcessEvent( event )
          if result is not None and isinstance( processIdClassOrInstance, basestring):
            result._savedAs = processIdClassOrInstance
      except IOError, e:
        raise KeyError( 'Could not get process "' + repr(processIdClassOrInstance) \
            + '": invalid identifier or process file: ' + repr(e))
  elif not isinstance( result, Process ):
    result = result()
  return result


#----------------------------------------------------------------------------
def allProcessesInfo():
  """
  Returns a list of :py:class:`ProcessInfo` objects for the loaded processes.
  """
  return _processesInfo.values()


#----------------------------------------------------------------------------
def getConverter( source, destination, checkUpdate=True ):
  """
  Gets a converter (a process that have the role converter) which can convert data from source format to destination format.
  Such converters can be used to extend the set of formats that a process accepts.
  
  :param source: tuple (type, format). If a converter is not found directly, parent types are tried.
  :param destination: tuple (type, format)
  :param boolean checkUpdate: if True, Brainvisa will check if the converter needs to be reloaded. Default True.
  :returns: the :py:class:`NewProcess` class associated to the found converter.
  """
  global _processes
  result = _converters.get( destination, {} ).get( source )
  if result is None:
    dt, df = destination
    st, sf = source
    if isSameDiskItemType( st, dt ):
      while result is None and st:
        st = st.parent
        result = _converters.get( ( st, df ), {} ).get( ( st, sf ) )
  return getProcess( result, checkUpdate=checkUpdate )


#--------------------------------------------->-------------------------------
def getConvertersTo( destination, keepType=1, checkUpdate=True ):
  """
  Gets the converters which can convert data to destination format.
  
  :param destination: tuple (type, format). If a converter is not found directly, parent types are tried.
  :param boolean keepType: if True, parent type won't be tried. Default True.
  :param boolean checkUpdate: if True, Brainvisa will check if the converters needs to be reloaded. Default True.
  :returns: a map (type, format) -> :py:class:`NewProcess` class associated to the found converter.
  """

  global _converters
  t, f = destination
  c = _converters.get( ( t, f ), {} )
  if keepType: return c
  while not c and t:
    t = t.parent
    c = _converters.get( ( t, f ), {} )
  return dict([(n,getProcess(p, checkUpdate=checkUpdate,
    ignoreValidation=True)) for n,p in c.items()])


#----------------------------------------------------------------------------
def getConvertersFrom( source, checkUpdate=True ):
  """
  Gets the converters which can convert data from source format to whatever format.
  
  :param source: tuple (type, format). If a converter is not found directly, parent types are tried.
  :param boolean checkUpdate: if True, Brainvisa will check if the converters needs to be reloaded. Default True.
  :returns: a map (type, format) -> :py:class:`NewProcess` class associated to the found converter.
  """
  global _converters
  result = {}
  for destination, i in _converters.items():
    c = i.get( source )
    t,f = source
    while not c and t:
      t = t.parent
      c = i.get( ( t, f ) )
    if c:
      result[ destination ] = getProcess( c, checkUpdate=checkUpdate )
  return result

def getConverters():
    """
    Gets the converter name list.
    """
    global _converters
    results = []
    
    for d in _converters.itervalues():
        for v in d.itervalues():
            if not v in results and type( v ) == str:
                results.append( v )            
    
    return sorted( results )
        

#----------------------------------------------------------------------------
def getViewer( source, enableConversion = 1, checkUpdate=True, listof=False ):
  """
  Gets a viewer (a process that have the role viewer) which can visualize source data.
  The viewer is returned only if its userLevel is lower than the current userLevel.
  
  :param source: a :py:class:`neuroDiskItems.DiskItem`, a list of :py:class:`neuroDiskItems.DiskItem` (only the first will be taken into account), a tuple (type, format).
  :param boolean enableConversion: if True, a viewer that accepts a format in which source can be converted is also accepted. Default True
  :param boolean checkUpdate: if True, Brainvisa will check if the viewer needs to be reloaded. Default True.
  :param boolean listof: If True, we need a viewer for a list of data. If there is no specific viewer for a list of this type of data, a :py:class:`ListOfIterationProcess` is created from the associated simple viewer. Default False.
  :returns: the :py:class:`NewProcess` class associated to the found viewer.
  """
  global _viewers
  global _listViewers
  if listof:
    viewers = _listViewers
  else:
    viewers = _viewers

  if isinstance( source, DiskItem ):
    t0 = source.type
    f = source.format
  elif isinstance( source, list):
    if source != [] and isinstance(source[0], DiskItem):
      t0 = source[0].type
      f=source[0].format
  else:
    t0, f = source
  t = t0
  v = viewers.get( ( t, f ) )
  # if the diskitem has no type, get the more generic viewer that accept the format of the diskitem
  if not v and t is None:
    for k in viewers.keys():
      t0b, fb = k
      if fb == f:
        if t is None or t.isA(t0b):
          t=t0b
          v=viewers.get((t, f))
          if t.parent is None:
            break
  while not v and t:
    t = t.parent
    v = viewers.get( ( t, f ) )
  if not v and enableConversion:
    converters = getConvertersFrom( (t0, f), checkUpdate=checkUpdate )
    t = t0
    while not v and t:
      for tc, fc in converters.keys():
        if ( tc, fc ) != ( t0, f ):
          v = viewers.get( ( t, fc ) )
          if v: break
      t = t.parent
  p =  getProcess( v, checkUpdate=checkUpdate )
  if p and p.userLevel <= neuroConfig.userLevel:
    return p
  if listof:
    if isinstance( source, tuple ) and len( source ) == 2:
      vrs = [ getViewer( source, enableConversion=enableConversion,
                        checkUpdate=checkUpdate ) ]
    else:
      vrs = [ getViewer( s, enableConversion=enableConversion,
                        checkUpdate=checkUpdate ) for s in source ]
    if None not in vrs and len( vrs ) != 0:
      class iterproc( object ):
        def __init__( self, name, procs ):
          self.name = name
          self.procs = procs
        def __call__( self ):
          ip = ListOfIterationProcess( self.name, self.procs )
          return ip
      return iterproc( _t_( 'Viewer for list of ' ) + t0.name, vrs )
  return None


#----------------------------------------------------------------------------
def runViewer( source, context=None ):
  """
  Searches for a viewer for source data and runs the process. 
  
  :param source: a :py:class:`neuroDiskItems.DiskItem` or something that enables to find a :py:class:`neuroDiskItems.DiskItem`.
  :param context: the :py:class:`ExecutionContext`. If None, the default context is used.
  :returns: the result of the execution of the found viewer.
  """
  if not isinstance( source, DiskItem ):
    source = ReadDiskItem( 'Any Type', formats.keys() ).findValue( source )
  if context is None:
    context = defaultContext()
  viewer = getViewer( source, checkUpdate=False )
  return context.runProcess( viewer, source )


#----------------------------------------------------------------------------
def getDataEditor( source, enableConversion = 0, checkUpdate=True, listof=False ):
  """
  Gets a data editor (a process that have the role editor) which can open source data for edition (modification).
  The data editor is returned only if its userLevel is lower than the current userLevel.
  
  :param source: a :py:class:`neuroDiskItems.DiskItem`, a list of :py:class:`neuroDiskItems.DiskItem` (only the first will be taken into account), a tuple (type, format).
  :param boolean enableConversion: if True, a data editor that accepts a format in which source can be converted is also accepted. Default False
  :param boolean checkUpdate: if True, Brainvisa will check if the editor needs to be reloaded. Default True.
  :param boolean listof: If True, we need an editor for a list of data. If there is no specific editor for a list of this type of data, a :py:class:`ListOfIterationProcess` is created from the associated simple editor. Default False.
  :returns: the :py:class:`NewProcess` class associated to the found editor.
  """
  global _dataEditors
  global _listDataEditors
  if listof:
    dataEditors = _listDataEditors
  else:
    dataEditors = _dataEditors

  if isinstance( source, DiskItem ):
    t0 = source.type
    f = source.format
  elif isinstance( source, list):
    if source != [] and isinstance(source[0], DiskItem):
      t0 = source[0].type
      f=source[0].format
  else:
    t0, f = source
  t = t0
  if not isinstance( f, list ) and not isinstance( f, tuple ):
    f = ( f, )
  v = None
  for i in f:
    v = dataEditors.get( ( t, i ) )
    if v is not None:
      format = i
      break
  while not v and t:
    t = t.parent
    v = None
    for i in f:
      v = dataEditors.get( ( t, i ) )
      if v is not None:
        format = i
        break
  if not v and enableConversion:
    for format in f:
      converters = getConvertersFrom( (t0, f), checkUpdate=checkUpdate )
      t = t0
      while not v and t:
        for tc, fc in converters.keys():
          if ( tc, fc ) != ( t0, f ):
            v = dataEditors.get( ( t, fc ) )
            if v: break
        t = t.parent
      if v: break
  p =  getProcess( v, checkUpdate=checkUpdate )
  if p and p.userLevel <= neuroConfig.userLevel:
    return p
  if listof:
    if isinstance( source, tuple ) and len( source ) == 2:
      vrs = [ getDataEditor( source, enableConversion=enableConversion,
                             checkUpdate=checkUpdate ) ]
    else:
      vrs = [ getDataEditor( s, enableConversion=enableConversion,
                             checkUpdate=checkUpdate ) for s in source ]
    if None not in vrs and len( vrs ) != 0:
      class iterproc( object ):
        def __init__( self, name, procs ):
          self.name = name
          self.procs = procs
        def __call__( self ):
          ip = ListOfIterationProcess( self.name, self.procs )
          return ip
      return iterproc( _t_( 'Editor for list of ' ) + t0.name, vrs )
  return None

#----------------------------------------------------------------------------
def getImporter( source, checkUpdate=True ):
  """
  Gets a importer (a process that have the role importer) which can import data in the database.
  
  :param source: a :py:class:`neuroDiskItems.DiskItem` or a tuple (type, format).
  :param boolean checkUpdate: if True, Brainvisa will check if the process needs to be reloaded. Default True.
  :returns: the :py:class:`NewProcess` class associated to the found process.
  """
  global _processes
  if isinstance( source, DiskItem ):
    t0 = source.type
    f = source.format
  else:
    t0, f = source
  t = t0
  v = _importers.get( ( t, f ) )
  while not v and t:
    t = t.parent
    v = _importers.get( ( t, f ) )
  p =  getProcess( v, checkUpdate=checkUpdate )
  if p:
    return p
  return None


#----------------------------------------------------------------------------
_extToModuleDescription ={
  'py': ('.py', 'r', imp.PY_SOURCE),
  'pyo': ('.py', 'r', imp.PY_COMPILED),
  'pyc': ('.py', 'r', imp.PY_COMPILED),
  'so': ('.so', 'rb', imp.C_EXTENSION),
}

#----------------------------------------------------------------------------
def readProcess( fileName, category=None, ignoreValidation=False, toolbox='brainvisa' ):
  """
  Loads a process from its source file. The source file is a python file which defines some variables (signature, name, userLevel) and functions (validation, initialization, execution).
  
  The process is indexed in the global lists of processes so it can be retrieved through the functions :py:func:`getProcess`, :py:func:`getProcessInfo`, :py:func:`getViewer`, ...
  
  :param string fileName: the name of the file containing the source code of the process.
  :param string category: category of the process. If None, it is the name of the directory containing the process.
  :param boolean ignoreValidation: if True, the validation function of the process won't be executed.
  :param string toolbox: The id of the toolbox containing the process. Defaut is 'brainvisa', it indicates that the process is not in a toolbox.
  :returns: A :py:class:`NewProcess` class representing the process if no exception is raised during the loading of the process.

  A new class derived from :py:class:`Process` is defined to store the content of the file:
  
  .. py:class:: NewProcess
  
    Bases: :py:class:`Process`
  
    All the elements defined in the file are added to the class. 
    
    .. py:attribute:: name 
    
      Name of the process. If it is not defined in the process file, it is the base name of the file without extension.
     
    .. py:attribute:: category
    
      The category of the process. If it is not given in parameter, it is the name of the directory containing the process file.
    
    .. py:attribute:: dataDirectory
      
      The data directory of the process is a directory near the process file with the same name and the extension .data. It is optional.
    
    .. py::attribute:: toolbox
      
      Name of the toolbox containing the process.
    
    .. py:attribute:: processReloadNotifier
      
      A :py:class:`soma.notification.Notifier` that will notify its observers when the process is reload.
    
    .. py:attribute:: signature
      
      The parameters excepted by the process.
    
    .. py:attribute:: userLevel
      
      Minimum userLevel needed to see the process.
    
    .. py:attribute:: roles
    
      Roles of the process: viewer, converter, editor, impoter. 
    
    .. py:method:: execution(self, context)
    
      Execution function.
    
  
  """
  result = None
  try:
    global _processModules, _processes, _processesInfo, _processesInfoByName, _readProcessLog, _askUpdateProcess
    # If we do not remove user level here, default userLevel for process
    # will be this one.
    g = globals()
    try:
      del g[ 'userLevel' ]
    except KeyError:
      pass

    extPos = fileName.rfind('.')
    fileExtension = fileName[ extPos+1: ]
    moduleName = os.path.basename( fileName[ : extPos ] )
    dataDirectory = fileName[ : extPos ] + '.data'
    if not os.path.exists( dataDirectory ):
      dataDirectory = None

    # Load module
    moduleDescription = _extToModuleDescription.get( fileExtension )
    if moduleDescription is None:
      raise RuntimeError( HTMLMessage(_t_( 'Cannot load a process from file <em>%s</em>' ) % (fileName,)) )
    currentDirectory = os.getcwdu()
    fileIn = open( fileName, moduleDescription[ 1 ] )
    try:
      if dataDirectory:
        os.chdir( dataDirectory )
      try:
        processModule = imp.load_module( moduleName, fileIn, fileName, moduleDescription )
      except NameError, e:
        showException(beforeError=( _t_('In <em>%s</em>') ) % ( fileName, ), afterError=_t_(' (perharps you need to add the line <tt>"from brainvisa.processes import *"</tt> at the begining of the process)'))
        return
        #raise RuntimeError( HTMLMessage( _t_('In <em>%s</em>')  % ( fileName, ) + " <b>"+str(e)+"</b> "+_t_(' (perharps you need to add the line <tt>"from brainvisa.processes import *"</tt> at the begining of the process)') ))
    finally:
      fileIn.close()
      if dataDirectory:
        os.chdir( currentDirectory )

    _processModules[ moduleName ] = processModule

    if category is None:
      category = os.path.basename( os.path.dirname( fileName ) )
    class NewProcess( Process ):
      _instance = 0

    NewProcess._id = moduleName 
    NewProcess.name = moduleName
    NewProcess.category = category
    NewProcess.dataDirectory = dataDirectory
    NewProcess.toolbox = toolbox
    # The callback registered in processReloadNotifier are called whenever
    # a change in the process source file lead to a reload of the process.
    # The argument is the new process.
    NewProcess.processReloadNotifier = Notifier( 1 )

    # Optional attributes
    for n in ( 'signature', 'execution', 'name', 'userLevel', 'roles' ):
      v = getattr( processModule, n, None )
      if v is not None:
        setattr( NewProcess, n, v )
    v = getattr( processModule, 'category', None )
    if v is not None:
      NewProcess.category = v
    v = getattr( processModule, 'showMaximized', None )
    if v is not None:
      NewProcess.showMaximized = v

    # Other attributes
    for n, v in processModule.__dict__.items():
      if type( v ) is types.FunctionType and \
        g.get( n ) is not v:
        args = inspect.getargs( v.func_code )[ 0 ]
        if args and args[ 0 ] == 'self':
          setattr( NewProcess, n, v )
          delattr( processModule, n )
        else:
          setattr( NewProcess, n, staticmethod( v ) )


    NewProcess._fileName = fileName
    NewProcess._fileTime = os.path.getmtime( fileName )

    processInfo = ProcessInfo( id = NewProcess._id,
      name = NewProcess.name,
      signature = NewProcess.signature,
      userLevel = NewProcess.userLevel,
      category = NewProcess.category,
      fileName = NewProcess._fileName,
      roles = getattr( NewProcess, 'roles', () ),
      toolbox = toolbox,
      showMaximized = NewProcess.showMaximized
    )

    _processesInfo[ processInfo.id.lower() ] = processInfo
    _processesInfoByName[ NewProcess.name.lower() ] = processInfo

    NewProcess.module = processInfo.module

    # Process validation
    if not ignoreValidation:
      v = getattr( processModule, 'validation', None )
      if v is not None:
        try:
          v()
        except Exception, e:
          import codecs
          processInfo.valid=False
          raise ValidationError(HTMLMessage("The process <em>"+relative_path(processInfo.fileName, neuroConfig.toolboxesDir)+"</em> is not available: <b>"+unicode(e)+"</b>"))

    oldProcess = _processes.get( NewProcess._id.lower() )
    if oldProcess is not None:
      if fileName != oldProcess._fileName:
        defaultContext().warning("Two processes have the same id : "+NewProcess._id.lower()+".", fileName, " process will override ", oldProcess._fileName)
      NewProcess.toolbox = oldProcess.toolbox
      processInfo.toolbox = oldProcess.toolbox
      for n in ( 'execution', 'initialization', 'checkArguments' ):
        setattr( oldProcess, n, getattr( NewProcess, n ).im_func )
      oldProcess._fileTime = NewProcess._fileTime

    _processes[ processInfo.id.lower() ] = NewProcess
    result = NewProcess

    def warnRole( processInfo, role ):
      print >> sys.stderr, 'WARNING: process', processInfo.name, '(' + processInfo.fileName + ') is not a valid', role + '. Add the following line in the process to make it a', role + ':\nroles =', ( role, )
    roles = getattr( processModule, 'roles', () )
#    if NewProcess.category.lower() == 'converters/automatic':
    def _setConverter( source, dest, proc ):
      d = _converters.setdefault( dest, {} )
      oldc = d.get( source )
      if oldc:
        oldproc = getProcess( oldc )
        oldpriority = 0
        if oldproc:
          oldpriority = getattr( oldproc, 'rolePriority', 0 )
        newpriority = getattr( proc, 'rolePriority', 0 )
        if oldpriority > newpriority:
          return # don't register because prioriry is not sufficient
      d[ source ] = proc._id
    if 'converter' in roles:
      global _converters
      possibleConversions = getattr( NewProcess, 'possibleConversions', None )
      if possibleConversions is None:
        sourceArg, destArg = NewProcess.signature.values()[ : 2 ]
        for destFormat in destArg.formats:
          for sourceFormat in sourceArg.formats:
            _setConverter( ( sourceArg.type, sourceFormat ),
              ( destArg.type, destFormat ), NewProcess )
      else:
        for source, dest in possibleConversions():
          source = ( getDiskItemType( source[0] ), getFormat( source[1] ) )
          dest = ( getDiskItemType( dest[0] ), getFormat( dest[1] ) )
          _setConverter( source, dest, NewProcess )

    elif NewProcess.category.lower() == 'converters/automatic':
      warnRole( processInfo, 'converter' )
    if 'viewer' in roles:
#    elif NewProcess.category.lower() == 'viewers/automatic':
      global _viewers
      global _listViewers
      arg = NewProcess.signature.values()[ 0 ]
      if isinstance(arg, ListOf):
        arg=arg.contentType
        if hasattr( arg, 'formats' ):
          for format in arg.formats:
            _listViewers[ ( arg.type, format ) ] = NewProcess._id
      elif hasattr( arg, 'formats' ):
        for format in arg.formats:
          _viewers[ ( arg.type, format ) ] = NewProcess._id
    elif NewProcess.category.lower() == 'viewers/automatic':
      warnRole( processInfo, 'viewer' )
    if 'editor' in roles:
#    elif NewProcess.category.lower() == 'editors/automatic':
      global _dataEditors
      global _listDataEditors
      arg = NewProcess.signature.values()[ 0 ]
      if isinstance(arg, ListOf):
        arg=arg.contentType
        if hasattr( arg, 'formats' ):
          for format in arg.formats:
            _listDataEditors[ ( arg.type, format ) ] = NewProcess._id
      elif hasattr( arg, 'formats' ):
        for format in arg.formats:
          _dataEditors[ ( arg.type, format ) ] = NewProcess._id
    elif NewProcess.category.lower() == 'editors/automatic':
      warnRole( processInfo.fileName, 'editor' )
    if 'importer' in roles:
      global _importers
      sourceArg, destArg = NewProcess.signature.values()[ : 2 ]
      if hasattr( destArg, 'formats' ):
        for format in destArg.formats:
          _importers[ ( destArg.type, format ) ] = NewProcess._id

    if _readProcessLog is not None:
      _readProcessLog.append( processInfo.id,
        html='<h1>' + processInfo.id + '</h1>' + processInfo.html(),
        icon = 'icon_process.png' )

    if oldProcess is not None:
      oldProcess.processReloadNotifier.notify( result )

  except ValidationError:
    if _readProcessLog is not None:
      _readProcessLog.append( NewProcess._id, html=exceptionHTML(), icon='warning.png' )
    raise
  except:
    if _readProcessLog is not None:
      _readProcessLog.append( os.path.basename( fileName ), html=exceptionHTML(), icon='error.png' )
    raise
  return result

#----------------------------------------------------------------------------
def readProcesses( processesPath ):
  """
  Read all the processes found in toolboxes and in a list of directories. 
  The toolboxes are found with the function :py:func:`brainvisa.toolboxes.allToolboxes`.
  
  A global object representing a tree of processes is created, it is an instance of the :py:class:`ProcessTree` 
  
  :param list processesPath: list of paths to directories containing processes files.
  """
  # New style processes initialization
  global _processesInfo, _converters
  global _allProcessesTree
  processesCacheFile = os.path.join( neuroConfig.homeBrainVISADir, 'processCache-' + neuroConfig.shortVersion )
  processesCache = {}
  if neuroConfig.fastStart and os.path.exists( processesCacheFile ):
    try:
      _processesInfo, converters = cPickle.load( open( processesCacheFile, 'r' ) )
      # change _converters keys to use the same instances as the global
      # types / formats list
      for k in converters.keys():
        _converters[ ( getDiskItemType( k[0].name ), getFormat( k[1].name ) ) ] = converters[ k ]
    except:
      _processesInfo, _converters = {}, {}
      if neuroConfig.mainLog is not None:
        neuroConfig.mainLog.append( 'Cannot read processes cache',
          html=exceptionHTML( beforeError=_t_( 'Cannot read processes cache file <em>%s</em>' ) % ( processesCacheFile, ) ),
          icon='warning.png' )

  if neuroConfig.gui or not neuroConfig.fastStart or not _processesInfo:
    # create all processes tree while reading processes in processesPath
    _allProcessesTree=ProcessTree("Various processes", "all processes",editable=False, user=False)
    for processesDir in processesPath:
      _allProcessesTree.addDir(processesDir, "", processesCache)
    for toolbox in brainvisa.toolboxes.allToolboxes():
      toolbox.getProcessTree()

    # save processes cache
    try:
      cPickle.dump( ( _processesInfo, _converters ), open( processesCacheFile, 'wb' ) )
    except:
      if neuroConfig.mainLog is not None:
        neuroConfig.mainLog.append( 'Cannot write processes cache',
          html=exceptionHTML( beforeError=_t_( 'Cannot write processes cache file <em>%s</em>' ) % ( processesCacheFile, ) ),
          icon='warning.png' )

#----------------------------------------------------------------------------
class ProcessTree( EditableTree ):
  """
  Bases: :py:class:`soma.notification.EditableTree`
  
  Represents a hierarchy of processes. 
  It is used to represent the processes of a toolbox or a set of personal bookmarks on processes.
  
  The tree contains branches: categories or directories, and leaves: processes.
  
  This object can be saved in a minf file (in userProcessTree.minf for user bookmarks).
  """
  defaultName = "New"

  def __init__( self, name=None, id=None, icon=None, tooltip=None, editable=True, user=True,  content=[]):
    """
    :param string name: name of the tree
    :param string id: id of the process. if None, it is set to the name in lowercase.
    :param string icon: filename of an icon that represents the process tree.
    :param string tooltip: description associated to the process tree
    :param boolean editable: if True, the tree can be modified after its creation. 
    :param boolean user: if True, this tree is a custom process tree created by the user (personal bookmarks on processes)
    :param list content: initial content, list of children to add in the tree.
    """
    if id is None and name is not None:
      id=string.lower(name)
    super(ProcessTree, self).__init__(_t_(name), id, editable, content)
    self.initName=name
    self.onAttributeChange("name", self.updateName)
    self.user = bool( user )
    if icon is not None:
      self.icon=icon
    elif self.user:
      self.icon = 'folder_home.png'
    else:
      self.icon = 'list.png'
    if tooltip!=None:
      self.tooltip=_t_(tooltip)
    else: self.tooltip=self.name
    self.setVisible() # tag the tree as visible or not : it is visible if it contains at least one visible child

  def __getinitargs__(self):
    content=self.values()
    return ( self.initName, self.id, self.icon, self.tooltip, self.modifiable, self.user, content )

  def __getinitkwargs__(self):
    """
    This object can be saved in a minf file (in userProcessTree.minf for user bookmarks). That's why it defines __getinitkwargs__ method.  this method's result is stored in the file and passed to the constructor to restore the object.
    Some changes to the constructor attributes must be reflected in getinitkwargs method, but changes can affect the reading of existing minf files.
    """
    content=self.values()
    return ( (), {'name' : self.initName, 'id': self.id, 'icon' : self.icon, 'editable' : self.modifiable, 'user' : self.user, 'content' : content} )

  def addDir(self, processesDir, category="", processesCache={}, toolbox='brainvisa' ):
    """
    Adds the processes from a directory to the current tree. Subdirectories will become the branches of the tree and processes will become the leaves of the tree.
    
    :param string processesDir: directory where processes are recursively searched.
    :param string category: category prefix for all processes found in this directory (useful for toolboxes : all processes category begins with toolbox's name.
    :param dictionary processesCache: a dictionary containing previously saved processes info stored by id. Processes that are in this cache are not reread.
    """
    if os.path.isdir( processesDir ):
      stack = [ ( self, processesDir, category ) ]
      while stack:
        parent, dir, category = stack.pop( 0 )
        p = []
        try:
          listdir = os.listdir( dir )
        except:
          showException()
          listdir=[]
        for f in sorted( listdir ):
          ff = os.path.join( dir, f )
          if os.path.isdir( ff ):
            if not ff.endswith( '.data' ):
              if category:
                c = category + '/' + f
              else:
                c = f
              b = ProcessTree.Branch( name=f, id=c.lower(), editable=False )
              parent.add( b )
              stack.append( ( b, ff, c ) )
            else:
              continue
          elif ff.endswith( '.py' ) or ff.endswith('.so'):
            p.append( ( f, ff ) )
        for f, ff in p:
          if not os.path.exists( ff ): continue
          id = f[:-3]
          try:
            processInfo = processesCache.get( id )
            if processInfo is None:
              readProcess( ff, category=category,
                ignoreValidation=neuroConfig.ignoreValidation,
                toolbox=toolbox ) # two arguments : process fullpath and category (directories separated by /)
            else:
              addProcessInfo( id, processInfo )
          except ValidationError:# it may occur a validation error on reading process
            pass
          except:
            showException()
          processInfo = getProcessInfo( id )
          if processInfo is not None:
            l = ProcessTree.Leaf( id=processInfo.id, editable=False)
            parent.add( l )

  def setEditable(self, bool):
    """
    Makes the tree editable. All its children becomes modifiable and deletable.
    """
    self.modifiable=bool
    for item in self.values():
      item.setAllModificationsEnabled(bool)

  def setName(self, n):
    """
    Renames the tree. The tooltip is also changed it was equal to the name.
    """
    if self.name==self.tooltip:
      self.tooltip=n
    EditableTree.setName(self, n)

  def setVisible(self):
    """
    Sets the tree as visible if it is a user tree or if it has at least one visible child.
    An empty user tree is visible because it can be a newly created user tree and the user may want to fill it later.
    """
    visible=False
    if self.user:
      visible=True
    else:
      for item in self.values():
        if item.visible:
          visible=True
          break
    self.visible=visible

  def update(self):
    """
   Recursively Updates `visible` attribute for each item in the tree. 
   This method must be called when the visibility may have change. 
   For exemple when the userLevel has changed, some process must become visibles.
    """
    visibleChild=False
    for item in self.values():
      item.update(self.user)
      if item.visible:
        visibleChild=True
    self.visible=(self.user or visibleChild)

  def updateName(self):
    """
    When the tree name is changed after construction. 
    The new name must be saved if the tree is saved in minf file. So change the initName.
    """
    self.initName=self.name

  #----------------------------------------------------------------------------
  class Branch( EditableTree.Branch ):
    """
    Bases: :py:class:`soma.notification.EditableTree.Branch`
    
    A directory that contains processes and/or another branches. 
    Enables to organise processes by category.
    """
    _defaultIcon = 'folder.png'
    defaultName = "New category"

    def __init__( self, name=None, id=None, editable=True, icon=None, content=[] ):
      if icon is None:
        icon = self._defaultIcon
      defaultName = _t_( self.defaultName )
      if id is None or id == defaultName:
        if name is not None and name != defaultName:
          id=string.lower(name)
        else:
          id=None
      #from brainvisa.toolboxes import getToolbox
      #toolbox=getToolbox(id)
      #if toolbox is not None:
         #name=toolbox.name
      # even if the tree isn't editable, copy of elements is enabled
      # (that  doesn't change the tree but enable to  copy elements in another tree)
      super(ProcessTree.Branch, self).__init__(_t_(name), id, icon, _t_("category"), True, editable, editable, content)
      self.initName=name # store the name given in parameters to return in getinitkwargs, so save in minf format will store init name before potential traduction
      self.onAttributeChange("name", self.updateName)
      #EditableTree.Branch.__init__(self, unicode(name), unicode(icon), _t_("category"), True, editable, editable, content)
      self.setVisible() # set the visibility of the branch relatively to its content. As the branch can be constructed with a content (when it is restored from minf file for example), it is usefull to do so.

    def __getinitargs__(self):
      content=self.values()
      return ( self.initName, self.id, self.modifiable, self.icon, content)

    def __getinitkwargs__(self):
      content=self.values()
      return ( (), {'name' : self.initName, 'id' : self.id, 'editable' : self.modifiable, 'content' : content})

    def __reduce__( self ):
      """This method is redefined for enable deepcopy of this object (and potentially pickle).
      It gives the arguments to pass to the init method of the object when creating a copy
      """
      return ( self.__class__, self.__getinitargs__(), None, None, None )

    def setVisible(self):
      """
      Sets the branch as visible if it has no child or if it has at least one visible child.
      Empty branch is visible because it can be a newly created user branch and the user may want to fill it later.
      """
      visible=False
      if len(self)==0:
        visible=True
      else:
        for item in self.values():
          if item.visible:
            visible=True
            break
      self.visible=visible

    def update(self, userTree=False):
      """
      Updates recursively visible attribute for each item in the branch. 
      This method must be called when the visibility may have change. 
      For exemple when the userLevel has changed, some processes must become visibles.
      """
      if len(self)==0:
        self.visible=True
      else:
        visibleChild=False
        for item in self.values():
          item.update(userTree)
          if item.visible:
            visibleChild=True
        self.visible=visibleChild

    def updateName(self):
      self.initName=self.name
  #----------------------------------------------------------------------------
  class Leaf( EditableTree.Leaf ):
    """
    Bases: :py:class:`soma.notification.EditableTree.Leaf`
    
    A ProcessTree.Leaf represents a process.
    """
    def __init__( self, id, name=None, editable=True, icon=None, *args, **kwargs ):
      processInfo=getProcessInfo(id)
      pname=name
      if name is None:
        pname=id
      if processInfo is not None:
        if name is None:
          pname=processInfo.name
        if icon is None: # set icon according to process role and user level
          if 'viewer' in processInfo.roles:
            icon = 'viewer.png'
          elif 'editor' in processInfo.roles:
            icon = 'editor.png'
          elif 'converter' in processInfo.roles:
            icon = 'converter.png'
          else:
            icon = 'icon_process_' + str( min( processInfo.userLevel, 3 ) ) + '.png'
      super(ProcessTree.Leaf, self).__init__(_t_(pname), id, icon, _t_("process"), True, editable, editable)
      self.initName=name
      self.onAttributeChange("name", self.updateName)
      self.setVisible(processInfo)
      if processInfo is not None:
        self.enabled = processInfo.valid
      else:
        self.enabled = True

    def __getinitargs__(self):
      return (self.id, self.initName, self.modifiable, self.icon)

    def __getinitkwargs__(self):
      return ( (), {'id' : self.id, 'name' : self.initName, 'editable' :  self.modifiable}) # do not save icon in minf file for processes because it is determined by its role and user level

    def __reduce__( self ):
      """This method is redefined for enable deepcopy of this object (and potentially pickle).
      It gives the arguments to pass to the init method of the object when creating a copy
      """
      return ( self.__class__,  self.__getinitargs__(), None, None, None )

    def setVisible(self, processInfo):
      """
      A ProcessTree.Leaf is valid if the id references a process in _processesInfo and if the process' userLevel is lower or equal than global userLevel and the related process is valid (validation function succeeded).
      """
      visible=False
      if processInfo is not None:
        if (processInfo.userLevel <= neuroConfig.userLevel):
          visible=True
      self.visible=visible

    def update(self, userTree=False):
      """
      Called when the parent tree is updated because some visibility conditions have changed.
      Evaluates the visibility of the reprensented process.
      """
      processInfo=getProcessInfo(self.id)
      self.setVisible(processInfo)

    def updateName(self):
      self.initName=self.name

#----------------------------------------------------------------------------
class ProcessTrees(ObservableAttributes, ObservableSortedDictionary):
  """
  Model for the list of process trees in brainvisa. A process tree is an instance of the class :py:class:`ProcessTree`.
  It is a dictionary which maps each tree with its id.
  It contains several process trees :
  
  * default process tree : all processes in brainvisa/processes (that are not in a toolbox). Not modifiable by user.
  * toolboxes : processes grouped by theme. Not modifiable by user.
  * user process trees (personal bookmarks): lists created by the user and saved in a minf file.
  
  A tree can be set as default. It becomes the current tree at Brainvisa start.
  
  .. py:attribute:: name 
  
    Name of the object.
  
  .. py:attribute:: userProcessTreeMinfFile
  
    Path to the file which stores the process trees created by the user as bookmarks. 
    Default filename is in brainvisa home directory and is called `userProcessTrees.minf`.
  
  .. py:attribute:: selectedTree
  
    :py:class:`ProcessTree` that is the current tree when Brainvisa starts.
    
  """

  def __init__(self, name=None):
    """
    :param string name: Name of the object. Default is 'Toolboxes'.
    """
    if name is None:
      name = _t_('Toolboxes')
    # set the selected tree
    super(ProcessTrees, self).__init__()
    self.name=name
    self.userProcessTreeMinfFile=os.path.join( neuroConfig.homeBrainVISADir, 'userProcessTrees.minf' )
    self.selectedTree=None
    self.load()

  def add(self, processTree):
    """
    Add an item in the dictionary. If this item's id is already present in the dictionary as a key, add the item's content in the corresponding key.
    recursive method
    """
    key=processTree.id
    if self.has_key(key):
        for v in processTree.values(): # item is also a dictionary and contains several elements, add each value in the tree item
          self[key].add(v)
    else: # new item
      self[key]=processTree

  def load(self):
    """
    Loads process trees :
      - a tree containing all processes that are not in toolboxes: the function :py:func:`allProcessesTree` returns it;
      - toolboxes as new trees;
      - user trees that are saved in a minf file in user's .brainvisa directory.
    """
    allTree=allProcessesTree()
    self.add(allTree)
    # append toolboxes process trees
    from brainvisa.toolboxes import allToolboxes
    for toolbox in allToolboxes(): # add each toolbox's process tree
      self.add(toolbox.getProcessTree())
      # no longer add toolboxes in allProcessesTree, it was redundant
      # and add the toolbox as a branch in all processes tree
      #allTree.add(ProcessTree.Branch(toolbox.processTree.name, toolbox.processTree.id, False, toolbox.processTree.icon, toolbox.processTree.values()))
    for toolbox in allToolboxes(): # when all toolbox are created, add links from each toolbox to others
      for processTree in toolbox.links():
        self.add(processTree) # if a toolbox with the same id already exists, it doesn't create a new tree but update the existing one
        # report the links in the toolbox that are in all processes tree
        #if processTree.id != allTree.id: # except if the links points directly to all processes tree, in that case, there's nothing else to do
        #  allTree.add(ProcessTree.Branch(processTree.name, processTree.id, False, processTree.icon, processTree.values()))
    # sort processes in alphabetical order in toolboxes and in all processes tree
    for toolbox in allToolboxes():
      toolbox.processTree.sort()
    allTree.sort()
    # append other trees here if necessary
    # ....
    # load user trees from minf file
    userTrees=None
    currentTree=None
    if os.access(self.userProcessTreeMinfFile, os.F_OK): # if the file exists, read it
      try:
        format, reduction=minfFormat( self.userProcessTreeMinfFile )
        if (format=="XML") and (reduction=="brainvisa-tree_2.0"):
          userTrees, currentTree=iterateMinf( self.userProcessTreeMinfFile )
      except:
        print "Error while reading", self.userProcessTreeMinfFile
    if userTrees != None:
      for userTree in userTrees:
        self.add(userTree)
    # search selected tree.
    if currentTree is not None:
      # The id of the selected tree is stored in the minf file. But before, the name was stored, so if the value is not a key, search by names
      if self.has_key(currentTree):
        self.selectedTree=self[currentTree]
      else:
        for tree in self.values():
          if tree.name==currentTree:
            self.selectedTree=tree
            break
    else:
      self.selectedTree=None
    # update items visibility it depends on processes user level : must update to invisible branches that only contain invisible items
    self.update()

  def save(self):
    """
    Write trees created by the user in a minf file to restore them next time Brainvisa starts.
    """
    writer = createMinfWriter( self.userProcessTreeMinfFile, reducer='brainvisa-tree_2.0' )
    # save trees created by user
    writer.write( [ i for i in self.values() if i.user] )
    # save selected tree name
    if self.selectedTree is not None:
      writer.write(self.selectedTree.id)
    else:
      writer.write(None)
    writer.close()

  def update(self):
    """
    Updates all trees (evaluates visibility of each items).
    """
    for item in self.values():
      item.update()
#----------------------------------------------------------------------------
_mainProcessTree = None
def updatedMainProcessTree():
  """
  :rtype: :py:class:`ProcessTrees`
  :returns: Brainvisa list of process trees :  all processes tree, toolboxes, user trees
  """
  global _mainProcessTree
  if _mainProcessTree is None:
    _mainProcessTree = ProcessTrees()
  return _mainProcessTree

#----------------------------------------------------------------------------
def allProcessesTree():
  """
  Get the tree that contains all processes. It is created when processes in processesPath are first read.
  Toolboxes processes are also added in this tree.
  
  :rtype: :py:class:`ProcessTrees`
  :return: the tree that contains all processes.
  """
  global _allProcessesTree
  return _allProcessesTree

#----------------------------------------------------------------------------
def updateProcesses():
  """
  Called when option userLevel has changed.
  Associated widgets will be updated automatically because they listens for changes.
  """
  if _mainProcessTree is not None:
    _mainProcessTree.update()

#----------------------------------------------------------------------------
def mainThread():
  """
  Gets Brainvisa main thread.
  """
  return _mainThread

#----------------------------------------------------------------------------
def defaultContext():
  """
  Gets the default execution context.
  
  :rtype: :py:class:`ExecutionContext`
  :return: The default execution context associated to Brainvisa application.
  """
  return _defaultContext


#----------------------------------------------------------------------------
def initializeProcesses():
  """
  Intializes the global variables of the module. 
  The current thread is stored as the main thread. 
  A default execution context is created.
  """
  #TODO: A class would be more clean instead of all these global variables
  global _processModules, _processes, _processesInfo, _processesInfoByName, \
         _converters, _viewers, _listViewers, _mainThread, _defaultContext, _dataEditors, _listDataEditors, _importers,\
         _askUpdateProcess, _readProcessLog
  _mainThread = threading.currentThread()
  _processesInfo = {}
  _processesInfoByName = {}
  _processes = {}
  _processModules = {}
  _askUpdateProcess = {}
  _converters = {}
  _viewers = {}
  _listViewers = {}
  _dataEditors = {}
  _listDataEditors = {}
  _importers = {}
  _defaultContext = ExecutionContext()
  if neuroConfig.mainLog is not None:
    _readProcessLog = neuroConfig.brainvisaSessionLog.subLog()
    neuroConfig.brainvisaSessionLog.append( _t_('Read processes'),
      html='<em>processesPath</em> = ' + str( neuroConfig.processesPath ),
      children=_readProcessLog, icon='icon_process.png' )
  else:
    _readProcessLog = None


#----------------------------------------------------------------------------
def cleanupProcesses():
  """
  Callback associated to the application exit. 
  The global variables are cleaned.
  """
  global _processModules, _processes, _processesInfo, _processesInfoByName, \
         _converters, _viewers, _listViewers, _mainThread, _defaultContext, _dataEditors, _listDataEditors, _importers, \
         _askUpdateProcess, _readProcessLog
  _converters = {}
  _viewers = {}
  _listViewers = {}
  _dataEditors = {}
  _listDataEditors = {}
  _importers = {}
  _processesInfo = {}
  _processesInfoByName = {}
  _processes = {}
  _processModules = {}
  _askUpdateProcess = {}
  _mainThread = None
  _defaultContext = None
  if _readProcessLog is not None:
    _readProcessLog.close()
    _readProcessLog = None

#----------------------------------------------------------------------------
def reloadToolboxes():
  """
  Reloads toolboxes, processes, types, ontology rules, databases. 
  Useful to take into account new files without having to quit and start again Brainvisa.
  """
  from brainvisa.data import neuroHierarchy
  global _mainProcessTree
  
  # init typesPath and fileSystemOntologiesPath
  neuroConfig.initializeOntologyPaths()
  
  # read toolboxes directories: useful if there are new toolbox, process, types, or hierarchy files
  brainvisa.toolboxes.readToolboxes(neuroConfig.toolboxesDir, neuroConfig.homeBrainVISADir)
  # execute intialization files of toolboxes
  for toolbox in brainvisa.toolboxes.allToolboxes():
    toolbox.init()
  
  # reload lists of types and formats
  neuroDiskItems.reloadTypes()
  
  # reload processes
  readProcesses(neuroConfig.processesPath)
  # update the list of processes
  _mainProcessTree=None
  updatedMainProcessTree()
  
  # update databases and ontology rules
  fileSystemOntology.FileSystemOntology.clear()
  neuroHierarchy.initializeDatabases()
  neuroHierarchy.openDatabases()

#----------------------------------------------------------------------------
# tool funciton to open/get a IPython kernel
_ipsubprocs = []

def runIPConsoleKernel():
  from IPython.lib import guisupport
  guisupport.in_event_loop  = True
  from IPython.zmq.ipkernel import IPKernelApp
  app = IPKernelApp.instance()
  if not app.initialized() or not app.kernel:
    print 'runing IP console kernel'
    app.hb_port = 50042 # don't know why this is not set automatically
    if neuroConfig.gui:
      app.initialize( [ 'qtconsole', '--pylab=qt',
        "--KernelApp.parent_appname='ipython-qtconsole'" ] )
    else:
      app.initialize( [ 'console',
        "--KernelApp.parent_appname='ipython-console'" ] )
    app.start()
  return app

#----------------------------------------------------------------------------

from brainvisa.data import neuroHierarchy
from brainvisa.data.neuroHierarchy import *
from brainvisa.history import HistoryBook, minfHistory
