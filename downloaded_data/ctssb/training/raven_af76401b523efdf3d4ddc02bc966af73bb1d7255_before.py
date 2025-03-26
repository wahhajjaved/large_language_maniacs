"""
Created on July 10, 2013

@author: alfoa
"""
from __future__ import division, print_function, unicode_literals, absolute_import
import warnings
warnings.simplefilter('default',DeprecationWarning)

#External Modules------------------------------------------------------------------------------------
import sys
import numpy as np
from sklearn import tree
from scipy import spatial
#from scipy import interpolate
from scipy import integrate
import os
from glob import glob
import copy
import DataObjects
import math
#External Modules End--------------------------------------------------------------------------------

#Internal Modules------------------------------------------------------------------------------------
import utils
import mathUtils
from Assembler import Assembler
import SupervisedLearning
import MessageHandler
#Internal Modules End--------------------------------------------------------------------------------

"""
  ***************************************
  *  SPECIALIZED PostProcessor CLASSES  *
  ***************************************
"""

class BasePostProcessor(Assembler,MessageHandler.MessageUser):
  """"This is the base class for postprocessors"""
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    self.type              = self.__class__.__name__  # pp type
    self.name              = self.__class__.__name__  # pp name
    self.assemblerObjects  = {}                       # {MainClassName(e.g.Distributions):[class(e.g.Models),type(e.g.ROM),objectName]}
    self.requiredAssObject = (False,([],[]))          # tuple. self.first entry boolean flag. True if the XML parser must look for assembler objects;
                                                      # second entry tuple.self.first entry list of object can be retrieved, second entry multiplicity (-1,-2,-n means optional (max 1 object,2 object, no number limit))
    self.assemblerDict     = {}  # {'class':[['subtype','name',instance]]}
    self.messageHandler = messageHandler

  def initialize(self, runInfo, inputs, initDict) :
    """
     Method to initialize the pp.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    #if 'externalFunction' in initDict.keys(): self.externalFunction = initDict['externalFunction']
    self.inputs           = inputs

  def inputToInternal(self,currentInput):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, list, list of current inputs
    """
    return [(copy.deepcopy(currentInput))]

  def run(self, Input):
    """
     This method executes the postprocessor action.
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, dictionary, Dictionary containing the evaluated data
    """
    pass

class LimitSurfaceIntegral(BasePostProcessor):
  """
  This post-processor is aimed to compute the n-dimensional integral of an inputted Limit Surface
  """
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.variableDist   = {}                                    # dictionary created upon the .xml input file reading. It stores the distributions for each variable.
    self.target         = None                                  # target that defines the f(x1,x2,...,xn)
    self.tolerance      = 0.0001                                # integration tolerance
    self.integralType   = 'montecarlo'                          # integral type (which alg needs to be used). Either montecarlo or quadrature(quadrature not yet)
    self.seed           = 20021986                              # seed for montecarlo
    self.matrixDict     = {}                                    # dictionary of arrays and target
    self.lowerUpperDict = {}
    self.functionS      = None
    self.stat           = returnInstance('BasicStatistics',self)# instantiation of the 'BasicStatistics' processor, which is used to compute the pb given montecarlo evaluations
    self.stat.what      = ['expectedValue']
    self.requiredAssObject = (False,(['Distribution'],['n']))
    self.printTag       = 'POSTPROCESSOR INTEGRAL'

  def _localWhatDoINeed(self):
    """
    This method is a local mirror of the general whatDoINeed method.
    It is implemented by this postprocessor that need to request special objects
    @ In , None, None
    @ Out, needDict, list of objects needed
    """
    needDict = {'Distributions':[]}
    for distName in self.variableDist.values():
      if distName != None: needDict['Distributions'].append((None,distName))
    return needDict

  def _localGenerateAssembler(self,initDict):
    """ see generateAssembler method in Assembler.py """
    for varName, distName in self.variableDist.items():
      if distName != None:
        if distName not in initDict['Distributions'].keys(): self.raiseAnError(IOError,'distribution ' +distName+ ' not found.')
        self.variableDist[varName] = initDict['Distributions'][distName]
        self.lowerUpperDict[varName]['lowerBound'] = self.variableDist[varName].lowerBound
        self.lowerUpperDict[varName]['upperBound'] = self.variableDist[varName].upperBound

  def _localReadMoreXML(self,xmlNode):
    """
    Function to read the portion of the xml input that belongs to this specialized class
    and initialize some stuff based on the inputs got
    @ In, xmlNode    : Xml element node
    @ Out, None
    """
    for child in xmlNode:
      varName = None
      if child.tag == 'variable':
        varName = child.attrib['name']
        self.lowerUpperDict[varName] = {}
        self.variableDist[varName] = None
        for childChild in child:
          if childChild.tag == 'distribution': self.variableDist[varName] = childChild.text
          elif childChild.tag == 'lowerBound':
            if self.variableDist[varName] != None: self.raiseAnError(NameError,'you can not specify both distribution and lower/upper bounds nodes for variable ' +varName+' !')
            self.lowerUpperDict[varName]['lowerBound'] = float(childChild.text)
          elif childChild.tag == 'upperBound':
            if self.variableDist[varName] != None: self.raiseAnError(NameError,'you can not specify both distribution and lower/upper bounds nodes for variable ' +varName+' !')
            self.lowerUpperDict[varName]['upperBound'] = float(childChild.text)
          else:
            self.raiseAnError(NameError,'invalid labels after the variable call. Only "distribution" is accepted. tag: '+child.tag)
      elif child.tag == 'tolerance':
        try              : self.tolerance = float(child.text)
        except ValueError: self.raiseAnError(ValueError,"tolerance can not be converted into a float value!")
      elif child.tag == 'integralType':
        self.integralType = child.text.strip().lower()
        if self.integralType not in ['montecarlo']: self.raiseAnError(IOError,'only one integral types are available: MonteCarlo!')
      elif child.tag == 'seed':
        try              : self.seed = int(child.text)
        except ValueError: self.raiseAnError(ValueError,'seed can not be converted into a int value!')
        if self.integralType != 'montecarlo': self.raiseAWarning('integral type is '+self.integralType+' but a seed has been inputted!!!')
        else: np.random.seed(self.seed)
      elif child.tag == 'target':
        self.target = child.text
      else: self.raiseAnError(NameError,'invalid or missing labels after the variables call. Only "variable" is accepted.tag: '+child.tag)
      #if no distribution, we look for the integration domain in the input
      if varName != None:
        if self.variableDist[varName] == None:
          if 'lowerBound' not in self.lowerUpperDict[varName].keys() or 'upperBound' not in self.lowerUpperDict[varName].keys():
            self.raiseAnError(NameError,'either a distribution name or lowerBound and upperBound need to be specified for variable '+varName)
    if self.target == None: self.raiseAWarning('integral target has not been provided. The postprocessor is going to take the last output it finds in the provided limitsurface!!!')

  def initialize(self,runInfo,inputs,initDict):
    """
     Method to initialize the Limit Surface Integral post-processor. This method here
     is in charge of 'training' the nearest Neighbors ROM.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    self.inputToInternal(inputs)
    if self.integralType in ['montecarlo']:
      self.stat.parameters['targets'] = [self.target]
      self.stat.initialize(runInfo,inputs,initDict)
    self.functionS = SupervisedLearning.returnInstance('SciKitLearn',self,**{'SKLtype':'neighbors|KNeighborsClassifier','Features':','.join(list(self.variableDist.keys())),'Target':self.target})
    self.functionS.train(self.matrixDict)
    self.raiseADebug('DATA SET MATRIX:')
    self.raiseADebug(self.matrixDict)

  def inputToInternal(self,currentInput):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, None, the resulting converted object is stored as an attribute of this class
    """
    for item in currentInput:
      if item.type == 'TimePointSet':
        self.matrixDict = {}
        if not set(item.getParaKeys('inputs')) == set(self.variableDist.keys()): self.raiseAnError(IOError,'The variables inputted and the features in the input TimePointSet '+ item.name + 'do not match!!!')
        if self.target == None: self.target = item.getParaKeys('outputs')[-1]
        if self.target not in item.getParaKeys('outputs'): self.raiseAnError(IOError,'The target '+ self.target + 'is not present among the outputs of the TimePointSet '+ item.name)
        # construct matrix
        for  varName in self.variableDist.keys(): self.matrixDict[varName] = item.getParam('input',varName)
        outputarr = item.getParam('output',self.target)
        if len(set(outputarr)) != 2: self.raiseAnError(IOError,'The target '+ self.target + ' needs to be a classifier output (-1 +1 or 0 +1)!')
        outputarr[outputarr==-1] = 0.0
        self.matrixDict[self.target] = outputarr
      else: self.raiseAnError(IOError,'Only TimePointSet is accepted as input!!!!')

  def run(self,Input):
    """
     This method executes the postprocessor action. In this case, it performs the computation of the LS integral
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, float, integral outcome (probability of the event)
    """
    pb = None
    if self.integralType == 'montecarlo':
      tempDict = {}
      randomMatrix = np.random.rand(math.ceil(1.0/self.tolerance),len(self.variableDist.keys()))
      for index, varName in enumerate(self.variableDist.keys()):
        if self.variableDist[varName] == None: randomMatrix[:,index] = randomMatrix[:,index]*(self.lowerUpperDict[varName]['upperBound']-self.lowerUpperDict[varName]['lowerBound'])+self.lowerUpperDict[varName]['lowerBound']
        else:
          for samples in range(randomMatrix.shape[0]): randomMatrix[samples,index] = self.variableDist[varName].ppf(randomMatrix[samples,index])
        tempDict[varName] = randomMatrix[:,index]
      pb = self.stat.run({'targets':{self.target:self.functionS.evaluate(tempDict)}})
    else: self.raiseAnError(NotImplemented, "quadrature not yet implemented")
    return pb['expectedValue'][self.target]

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    if finishedjob.returnEvaluation() == -1: self.raiseAnError(RuntimeError,'no available output to collect.')
    else:
      pb = finishedjob.returnEvaluation()[1]
      lms = finishedjob.returnEvaluation()[0][0]
      if output.type == 'TimePointSet':
        # we store back the limitsurface
        for key,value in lms.getParametersValues('input').items():
          for val in value: output.updateInputValue(key, val)
        for key,value in lms.getParametersValues('output').items():
          for val in value: output.updateOutputValue(key,val)
        for _ in range(len(lms)): output.updateOutputValue('EventProbability',pb)
      elif output.type == 'FileObject':
        fileobject = open(output,'w')
        headers = lms.getParaKeys('inputs')+lms.getParaKeys('outputs')+['EventProbability']
        fileobject.write(','.join(headers))
        stack  = [None]*len(headers)
        outIndex = 0
        for key,value in lms.getParametersValues('input').items() : stack[headers.index(key)] = np.asarray(value).flatten()
        for key,value in lms.getParametersValues('output').items():
          stack[headers.index(key)] = np.asarray(value).flatten()
          outIndex = headers.index(key)
        stack[headers.index('EventProbability')] = np.array([pb]*len(stack[outIndex])).flatten()
        stacked = np.column_stack(stack)
        np.savetxt(output, stacked, delimiter=',', header=','.join(headers))
      else: self.raiseAnError(Exception, self.type + ' accepts TimePointSet or FileObject only')
#
#
#
class SafestPoint(BasePostProcessor):
  """
  It searches for the probability-weighted safest point inside the space of the system controllable variables
  """
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.controllableDist = {}                                    #dictionary created upon the .xml input file reading. It stores the distributions for each controllale variable.
    self.nonControllableDist = {}                                 #dictionary created upon the .xml input file reading. It stores the distributions for each non-controllale variable.
    self.controllableGrid = {}                                    #dictionary created upon the .xml input file reading. It stores the grid type ('value' or 'CDF'), the number of steps and the step length for each controllale variable.
    self.nonControllableGrid = {}                                 #dictionary created upon the .xml input file reading. It stores the grid type ('value' or 'CDF'), the number of steps and the step length for each non-controllale variable.
    self.gridInfo = {}                                            #dictionary contaning the grid type ('value' or 'CDF'), the grid construction type ('equal', set by default) and the list of sampled points for each variable.
    self.controllableOrd = []                                     #list contaning the controllable variables' names in the same order as they appear inside the controllable space (self.controllableSpace)
    self.nonControllableOrd = []                                  #list contaning the controllable variables' names in the same order as they appear inside the non-controllable space (self.nonControllableSpace)
    self.surfPointsMatrix = None                                  #2D-matrix containing the coordinates of the points belonging to the failure boundary (coordinates are derived from both the controllable and non-controllable space)
    self.stat = returnInstance('BasicStatistics',self)            #instantiation of the 'BasicStatistics' processor, which is used to compute the expected value of the safest point through the coordinates and probability values collected in the 'run' function
    self.stat.what = ['expectedValue']
    self.requiredAssObject = (True,(['Distribution'],['n']))
    self.printTag = 'POSTPROCESSOR SAFESTPOINT'

  def _localGenerateAssembler(self,initDict):
    """ see generateAssembler method in Assembler """
    for varName, distName in self.controllableDist.items():
      if distName not in initDict['Distributions'].keys():
        self.raiseAnError(IOError,'distribution ' +distName+ ' not found.')
      self.controllableDist[varName] = initDict['Distributions'][distName]
    for varName, distName in self.nonControllableDist.items():
      if distName not in initDict['Distributions'].keys():
        self.raiseAnError(IOError,'distribution ' +distName+ ' not found.')
      self.nonControllableDist[varName] = initDict['Distributions'][distName]

  def _localReadMoreXML(self,xmlNode):
    """
    Function to read the portion of the xml input that belongs to this specialized class
    and initialize some stuff based on the inputs got
    @ In, xmlNode    : Xml element node
    @ Out, None
    """
    for child in xmlNode:
      if child.tag == 'controllable':
        for childChild in child:
          if childChild.tag == 'variable':
            varName = childChild.attrib['name']
            for childChildChild in childChild:
              if childChildChild.tag == 'distribution':
                self.controllableDist[varName] = childChildChild.text
              elif childChildChild.tag == 'grid':
                if 'type' in childChildChild.attrib.keys():
                  if 'steps' in childChildChild.attrib.keys():
                    self.controllableGrid[varName] = (childChildChild.attrib['type'], int(childChildChild.attrib['steps']), float(childChildChild.text))
                  else:
                    self.raiseAnError(NameError,'number of steps missing after the grid call.')
                else:
                  self.raiseAnError(NameError,'grid type missing after the grid call.')
              else:
                self.raiseAnError(NameError,'invalid labels after the variable call. Only "distribution" and "grid" are accepted.')
          else:
            self.raiseAnError(NameError,'invalid or missing labels after the controllable variables call. Only "variable" is accepted.')
      elif child.tag == 'non-controllable':
        for childChild in child:
          if childChild.tag == 'variable':
            varName = childChild.attrib['name']
            for childChildChild in childChild:
              if childChildChild.tag == 'distribution':
                self.nonControllableDist[varName] = childChildChild.text
              elif childChildChild.tag == 'grid':
                if 'type' in childChildChild.attrib.keys():
                  if 'steps' in childChildChild.attrib.keys():
                    self.nonControllableGrid[varName] = (childChildChild.attrib['type'], int(childChildChild.attrib['steps']), float(childChildChild.text))
                  else:
                    self.raiseAnError(NameError,'number of steps missing after the grid call.')
                else:
                  self.raiseAnError(NameError,'grid type missing after the grid call.')
              else:
                self.raiseAnError(NameError,'invalid labels after the variable call. Only "distribution" and "grid" are accepted.')
          else:
            self.raiseAnError(NameError,'invalid or missing labels after the controllable variables call. Only "variable" is accepted.')
    self.raiseADebug('CONTROLLABLE DISTRIBUTIONS:')
    self.raiseADebug(self.controllableDist)
    self.raiseADebug('CONTROLLABLE GRID:')
    self.raiseADebug(self.controllableGrid)
    self.raiseADebug('NON-CONTROLLABLE DISTRIBUTIONS:')
    self.raiseADebug(self.nonControllableDist)
    self.raiseADebug('NON-CONTROLLABLE GRID:')
    self.raiseADebug(self.nonControllableGrid)

  def initialize(self,runInfo,inputs,initDict):
    """
     Method to initialize the Safest Point pp. This method is in charge
     of creating the Controllable and no-controllable grid.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    self.__gridSetting__()
    self.__gridGeneration__()
    self.inputToInternal(inputs)
    self.stat.parameters['targets'] = self.controllableOrd
    self.stat.initialize(runInfo,inputs,initDict)
    self.raiseADebug('GRID INFO:')
    self.raiseADebug(self.gridInfo)
    self.raiseADebug('N-DIMENSIONAL CONTROLLABLE SPACE:')
    self.raiseADebug(self.controllableSpace)
    self.raiseADebug('N-DIMENSIONAL NON-CONTROLLABLE SPACE:')
    self.raiseADebug(self.nonControllableSpace)
    self.raiseADebug('CONTROLLABLE VARIABLES ORDER:')
    self.raiseADebug(self.controllableOrd)
    self.raiseADebug('NON-CONTROLLABLE VARIABLES ORDER:')
    self.raiseADebug(self.nonControllableOrd)
    self.raiseADebug('SURFACE POINTS MATRIX:')
    self.raiseADebug(self.surfPointsMatrix)

  def __gridSetting__(self,constrType='equal'):
    for varName in self.controllableGrid.keys():
      if self.controllableGrid[varName][0] == 'value':
        self.__stepError__(float(self.controllableDist[varName].lowerBound),float(self.controllableDist[varName].upperBound),self.controllableGrid[varName][1],self.controllableGrid[varName][2],varName)
        self.gridInfo[varName] = (self.controllableGrid[varName][0], constrType, [float(self.controllableDist[varName].lowerBound)+self.controllableGrid[varName][2]*i for i in range(self.controllableGrid[varName][1]+1)])
      elif self.controllableGrid[varName][0] == 'CDF':
        self.__stepError__(0,1,self.controllableGrid[varName][1],self.controllableGrid[varName][2],varName)
        self.gridInfo[varName] = (self.controllableGrid[varName][0], constrType, [self.controllableGrid[varName][2]*i for i in range(self.controllableGrid[varName][1]+1)])
      else:
        self.raiseAnError(NameError,'inserted invalid grid type. Only "value" and "CDF" are accepted.')
    for varName in self.nonControllableGrid.keys():
      if self.nonControllableGrid[varName][0] == 'value':
        self.__stepError__(float(self.nonControllableDist[varName].lowerBound),float(self.nonControllableDist[varName].upperBound),self.nonControllableGrid[varName][1],self.nonControllableGrid[varName][2],varName)
        self.gridInfo[varName] = (self.nonControllableGrid[varName][0], constrType, [float(self.nonControllableDist[varName].lowerBound)+self.nonControllableGrid[varName][2]*i for i in range(self.nonControllableGrid[varName][1]+1)])
      elif self.nonControllableGrid[varName][0] == 'CDF':
        self.__stepError__(0,1,self.nonControllableGrid[varName][1],self.nonControllableGrid[varName][2],varName)
        self.gridInfo[varName] = (self.nonControllableGrid[varName][0], constrType, [self.nonControllableGrid[varName][2]*i for i in range(self.nonControllableGrid[varName][1]+1)])
      else:
        self.raiseAnError(NameError,'inserted invalid grid type. Only "value" and "CDF" are accepted.')

  def __stepError__(self,lowerBound,upperBound,steps,tol,varName):
    if upperBound-lowerBound<steps*tol:
      self.raiseAnError(IOError,'requested number of steps or tolerance for variable ' +varName+ ' exceeds its limit.')

  def __gridGeneration__(self):
    NotchesByVar = [None]*len(self.controllableGrid.keys())
    controllableSpaceSize = None
    for varId, varName in enumerate(self.controllableGrid.keys()):
      NotchesByVar[varId] = self.controllableGrid[varName][1]+1
      self.controllableOrd.append(varName)
    controllableSpaceSize = tuple(NotchesByVar+[len(self.controllableGrid.keys())])
    self.controllableSpace = np.zeros(controllableSpaceSize)
    iterIndex = np.nditer(self.controllableSpace,flags=['multi_index'])
    while not iterIndex.finished:
      coordIndex = iterIndex.multi_index[-1]
      varName = self.controllableGrid.keys()[coordIndex]
      notchPos = iterIndex.multi_index[coordIndex]
      if self.gridInfo[varName][0] == 'CDF':
        valList = []
        for probVal in self.gridInfo[varName][2]:
          valList.append(self.controllableDist[varName].cdf(probVal))
        self.controllableSpace[iterIndex.multi_index] = valList[notchPos]
      else:
        self.controllableSpace[iterIndex.multi_index] = self.gridInfo[varName][2][notchPos]
      iterIndex.iternext()
    NotchesByVar = [None]*len(self.nonControllableGrid.keys())
    nonControllableSpaceSize = None
    for varId, varName in enumerate(self.nonControllableGrid.keys()):
      NotchesByVar[varId] = self.nonControllableGrid[varName][1]+1
      self.nonControllableOrd.append(varName)
    nonControllableSpaceSize = tuple(NotchesByVar+[len(self.nonControllableGrid.keys())])
    self.nonControllableSpace = np.zeros(nonControllableSpaceSize)
    iterIndex = np.nditer(self.nonControllableSpace,flags=['multi_index'])
    while not iterIndex.finished:
      coordIndex = iterIndex.multi_index[-1]
      varName = self.nonControllableGrid.keys()[coordIndex]
      notchPos = iterIndex.multi_index[coordIndex]
      if self.gridInfo[varName][0] == 'CDF':
        valList = []
        for probVal in self.gridInfo[varName][2]:
          valList.append(self.nonControllableDist[varName].cdf(probVal))
        self.nonControllableSpace[iterIndex.multi_index] = valList[notchPos]
      else:
        self.nonControllableSpace[iterIndex.multi_index] = self.gridInfo[varName][2][notchPos]
      iterIndex.iternext()

  def inputToInternal(self,currentInput):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, None, the resulting converted object is stored as an attribute of this class
    """
    for item in currentInput:
      if item.type == 'TimePointSet':
        self.surfPointsMatrix = np.zeros((len(item.getParam('output',item.getParaKeys('outputs')[-1])),len(self.gridInfo.keys())+1))
        k=0
        for varName in self.controllableOrd:
          self.surfPointsMatrix[:,k] = item.getParam('input',varName)
          k+=1
        for varName in self.nonControllableOrd:
          self.surfPointsMatrix[:,k] = item.getParam('input',varName)
          k+=1
        self.surfPointsMatrix[:,k] = item.getParam('output',item.getParaKeys('outputs')[-1])

  def run(self,Input):
    """
     This method executes the postprocessor action. In this case, it computes the safest point
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, TimePointSet, TimePointSet containing the elaborated data
    """
    nearestPointsInd = []
    dataCollector = DataObjects.returnInstance('TimePointSet',self)
    dataCollector.type = 'TimePointSet'
    surfTree = spatial.KDTree(copy.copy(self.surfPointsMatrix[:,0:self.surfPointsMatrix.shape[-1]-1]))
    self.controllableSpace.shape = (np.prod(self.controllableSpace.shape[0:len(self.controllableSpace.shape)-1]),self.controllableSpace.shape[-1])
    self.nonControllableSpace.shape = (np.prod(self.nonControllableSpace.shape[0:len(self.nonControllableSpace.shape)-1]),self.nonControllableSpace.shape[-1])
    self.raiseADebug('RESHAPED CONTROLLABLE SPACE:')
    self.raiseADebug(self.controllableSpace)
    self.raiseADebug('RESHAPED NON-CONTROLLABLE SPACE:')
    self.raiseADebug(self.nonControllableSpace)
    for ncLine in range(self.nonControllableSpace.shape[0]):
      queryPointsMatrix = np.append(self.controllableSpace,np.tile(self.nonControllableSpace[ncLine,:],(self.controllableSpace.shape[0],1)),axis=1)
      self.raiseADebug('QUERIED POINTS MATRIX:')
      self.raiseADebug(queryPointsMatrix)
      nearestPointsInd = surfTree.query(queryPointsMatrix)[-1]
      distList = []
      indexList = []
      probList = []
      for index in range(len(nearestPointsInd)):
        if self.surfPointsMatrix[np.where(np.prod(surfTree.data[nearestPointsInd[index],0:self.surfPointsMatrix.shape[-1]-1] == self.surfPointsMatrix[:,0:self.surfPointsMatrix.shape[-1]-1],axis=1))[0][0],-1] == 1:
          distList.append(np.sqrt(np.sum(np.power(queryPointsMatrix[index,0:self.controllableSpace.shape[-1]]-surfTree.data[nearestPointsInd[index],0:self.controllableSpace.shape[-1]],2))))
          indexList.append(index)
      if distList == []:
        self.raiseAnError(ValueError,'no safest point found for the current set of non-controllable variables: ' +str(self.nonControllableSpace[ncLine,:])+ '.')
      else:
        for cVarIndex in range(len(self.controllableOrd)):
          dataCollector.updateInputValue(self.controllableOrd[cVarIndex],copy.copy(queryPointsMatrix[indexList[distList.index(max(distList))],cVarIndex]))
        for ncVarIndex in range(len(self.nonControllableOrd)):
          dataCollector.updateInputValue(self.nonControllableOrd[ncVarIndex],copy.copy(queryPointsMatrix[indexList[distList.index(max(distList))],len(self.controllableOrd)+ncVarIndex]))
          if queryPointsMatrix[indexList[distList.index(max(distList))],len(self.controllableOrd)+ncVarIndex] == self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].lowerBound:
            if self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][0] == 'CDF':
              prob = self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]/float(2)
            else:
              prob = self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].cdf(self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].lowerBound+self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]/float(2))
          elif queryPointsMatrix[indexList[distList.index(max(distList))],len(self.controllableOrd)+ncVarIndex] == self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].upperBound:
            if self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][0] == 'CDF':
              prob = self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]/float(2)
            else:
              prob = 1-self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].cdf(self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].upperBound-self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]/float(2))
          else:
            if self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][0] == 'CDF':
              prob = self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]
            else:
              prob = self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].cdf(queryPointsMatrix[indexList[distList.index(max(distList))],len(self.controllableOrd)+ncVarIndex]+self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]/float(2))-self.nonControllableDist[self.nonControllableOrd[ncVarIndex]].cdf(queryPointsMatrix[indexList[distList.index(max(distList))],len(self.controllableOrd)+ncVarIndex]-self.nonControllableGrid[self.nonControllableOrd[ncVarIndex]][2]/float(2))
          probList.append(prob)
      dataCollector.updateOutputValue('Probability',np.prod(probList))
      dataCollector.updateMetadata('ProbabilityWeight',np.prod(probList))
    dataCollector.updateMetadata('ExpectedSafestPointCoordinates',self.stat.run(dataCollector)['expectedValue'])
    self.raiseADebug(dataCollector.getParametersValues('input'))
    self.raiseADebug(dataCollector.getParametersValues('output'))
    self.raiseADebug(dataCollector.getMetadata('ExpectedSafestPointCoordinates'))
    return dataCollector

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    if finishedjob.returnEvaluation() == -1:
      self.raiseAnError(RuntimeError,'no available output to collect (the run is likely not over yet).')
    else:
      dataCollector = finishedjob.returnEvaluation()[1]
      if output.type != 'TimePointSet':
        self.raiseAnError(TypeError,'output item type must be "TimePointSet".')
      else:
        if not output.isItEmpty():
          self.raiseAnError(ValueError,'output item must be empty.')
        else:
          for key,value in dataCollector.getParametersValues('input').items():
            for val in value: output.updateInputValue(key, val)
          for key,value in dataCollector.getParametersValues('output').items():
            for val in value: output.updateOutputValue(key,val)
          for key,value in dataCollector.getAllMetadata().items(): output.updateMetadata(key,value)
#
#
#
class ComparisonStatistics(BasePostProcessor):
  """
  ComparisonStatistics is to calculate statistics that compare
  two different codes or code to experimental data.
  """

  class CompareGroup:
    def __init__(self):
      """
       Constructor
      """
      self.dataPulls = []
      self.referenceData = {}

  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.dataDict = {} #Dictionary of all the input data, keyed by the name
    self.compareGroups = [] #List of each of the groups that will be compared
    #self.dataPulls = [] #List of data references that will be used
    #self.referenceData = [] #List of reference (experimental) data
    self.methodInfo = {} #Information on what stuff to do.
    self.f_z_stats = False
    self.interpolation = "quadratic"
    self.requiredAssObject = (True,(['Distribution'],['-n']))
    self.distributions = {}

  def inputToInternal(self,currentInput):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, object, the resulting converted object
    """
    return [(currentInput)]

  def initialize(self, runInfo, inputs, initDict):
    """
     Method to initialize the ComparisonStatistics pp.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    BasePostProcessor.initialize(self, runInfo, inputs, initDict)

  def _localReadMoreXML(self,xmlNode):
    """
    Function to read the portion of the xml input that belongs to this specialized class
    and initialize some stuff based on the inputs got
    @ In, xmlNode    : Xml element node
    @ Out, None
    """
    for outer in xmlNode:
      if outer.tag == 'compare':
        compareGroup = ComparisonStatistics.CompareGroup()
        for child in outer:
          if child.tag == 'data':
            dataName = child.text
            splitName = dataName.split("|")
            name, kind = splitName[:2]
            rest = splitName[2:]
            compareGroup.dataPulls.append([name, kind, rest])
          elif child.tag == 'reference':
            #This is either name=distribution or mean=num and sigma=num
            compareGroup.referenceData = dict(child.attrib)
        self.compareGroups.append(compareGroup)
      if outer.tag == 'kind':
        self.methodInfo['kind'] = outer.text
        if 'num_bins' in outer.attrib:
          self.methodInfo['num_bins'] = int(outer.attrib['num_bins'])
        if 'bin_method' in outer.attrib:
          self.methodInfo['bin_method'] = outer.attrib['bin_method'].lower()
      if outer.tag == 'fz':
        self.f_z_stats =  (outer.text.lower() in utils.stringsThatMeanTrue())
      if outer.tag == 'interpolation':
        interpolation = outer.text.lower()
        if interpolation == 'linear':
          self.interpolation = 'linear'
        elif interpolation == 'quadratic':
          self.interpolation = 'quadratic'
        else:
          self.raiseADebug('unexpected interpolation method '+interpolation)
          self.interpolation = interpolation


  def _localGenerateAssembler(self, initDict):
    self.distributions = initDict.get('Distributions',{})
    #print("initDict", initDict)

  def run(self, Input): # inObj,workingDir=None):
    """
     This method executes the postprocessor action. In this case, it just returns the inputs
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, dictionary, Dictionary containing the inputs
    """
    dataDict = {}
    for aInput in Input: dataDict[aInput.name] = aInput
    return dataDict

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    self.raiseADebug("finishedjob: "+str(finishedjob)+", output "+str(output))
    if finishedjob.returnEvaluation() == -1: self.raiseAnError(RuntimeError,'no available output to collect.')
    else: self.dataDict.update(finishedjob.returnEvaluation()[1])

    dataToProcess = []
    for compareGroup in self.compareGroups:
      dataPulls = compareGroup.dataPulls
      reference = compareGroup.referenceData
      foundDataObjects = []
      for name, kind, rest in dataPulls:
        data = self.dataDict[name].getParametersValues(kind)
        if len(rest) == 1:
          foundDataObjects.append(data[rest[0]])
      dataToProcess.append((dataPulls,foundDataObjects,reference))
    generateCSV = False
    generateTimePointSet = False
    if output.type == 'FileObject':
      generateCSV = True
    elif output.type == 'TimePointSet':
      generateTimePointSet = True
    else:
      self.raiseAnError(IOError,'unsupported type '+str(type(output)))
    if generateCSV:
      csv = open(output,"w")
    for dataPulls, datas, reference in dataToProcess:
      graphData = []
      if "mean" in reference:
          refDataStats = {"mean":float(reference["mean"]),
                            "stdev":float(reference["sigma"]),
                            "min_bin_size":float(reference["sigma"])/2.0}
          refPdf = lambda x:mathUtils.normal(x,refDataStats["mean"],refDataStats["stdev"])
          refCdf = lambda x:mathUtils.normalCdf(x,refDataStats["mean"],refDataStats["stdev"])
          graphData.append((refDataStats,refCdf,refPdf,"ref"))
      if "name" in reference:
        distribution_name = reference["name"]
        if not distribution_name in self.distributions:
          self.raiseAnError(IOError,'Did not find '+distribution_name+
                             ' in '+str(self.distributions.keys()))
        else:
          distribution = self.distributions[distribution_name]
        refDataStats = {"mean":distribution.untruncatedMean(),
                        "stdev":distribution.untruncatedStdDev()}
        refDataStats["min_bin_size"] = refDataStats["stdev"]/2.0
        refPdf = lambda x:distribution.pdf(x)
        refCdf = lambda x:distribution.cdf(x)
        graphData.append((refDataStats,refCdf,refPdf,"ref_"+distribution_name))
      for dataPull, data in zip(dataPulls,datas):
        dataStats = self.processData(dataPull, data, self.methodInfo)
        dataKeys = set(dataStats.keys())
        counts = dataStats['counts']
        bins = dataStats['bins']
        countSum = sum(counts)
        binBoundaries = [dataStats['low']]+bins+[dataStats['high']]
        if generateCSV:
          utils.printCsv(csv,'"'+str(dataPull)+'"')
          utils.printCsv(csv,'"num_bins"',dataStats['num_bins'])
          utils.printCsv(csv,'"bin_boundary"','"bin_midpoint"','"bin_count"','"normalized_bin_count"','"f_prime"','"cdf"')
        cdf = [0.0]*len(counts)
        midpoints = [0.0]*len(counts)
        cdfSum = 0.0
        for i in range(len(counts)):
          f_0 = counts[i]/countSum
          cdfSum += f_0
          cdf[i] = cdfSum
          midpoints[i] = (binBoundaries[i]+binBoundaries[i+1])/2.0
        cdfFunc = mathUtils.createInterp(midpoints,cdf,0.0,1.0,self.interpolation)
        fPrimeData = [0.0]*len(counts)
        for i in range(len(counts)):
          h = binBoundaries[i+1] - binBoundaries[i]
          nCount = counts[i]/countSum #normalized count
          f_0 = cdf[i]
          if i + 1 < len(counts):
            f_1 = cdf[i+1]
          else:
            f_1 = 1.0
          if i + 2 < len(counts):
            f_2 = cdf[i+2]
          else:
            f_2 = 1.0
          if self.interpolation == 'linear':
            fPrime = (f_1 - f_0)/h
          else:
            fPrime = (-1.5*f_0 + 2.0*f_1 + -0.5*f_2)/h
          fPrimeData[i] = fPrime
          if generateCSV:
            utils.printCsv(csv,binBoundaries[i+1],midpoints[i],counts[i],nCount,fPrime,cdf[i])
        pdfFunc = mathUtils.createInterp(midpoints,fPrimeData,0.0,0.0,self.interpolation)
        dataKeys -= set({'num_bins','counts','bins'})
        if generateCSV:
          for key in dataKeys:
            utils.printCsv(csv,'"'+key+'"',dataStats[key])
        self.raiseADebug("data_stats: "+str(dataStats))
        graphData.append((dataStats, cdfFunc, pdfFunc,str(dataPull)))
      graph_data = mathUtils.getGraphs(graphData, self.f_z_stats)
      if generateCSV:
        for key in graph_data:
          value = graph_data[key]
          if type(value).__name__ == 'list':
            utils.printCsv(csv,*(['"' + l[0] + '"' for l in value]))
            for i in range(1,len(value[0])):
              utils.printCsv(csv,*([l[i] for l in value]))
          else:
            utils.printCsv(csv,'"'+key+'"',value)
      if generateTimePointSet:
        for key in graph_data:
          value = graph_data[key]
          if type(value).__name__ == 'list':
            for i in range(len(value)):
              subvalue = value[i]
              name = subvalue[0]
              subdata = subvalue[1:]
              if i == 0:
                output.updateInputValue(name, subdata)
              else:
                output.updateOutputValue(name, subdata)
            break #XXX Need to figure out way to specify which data to return
      if generateCSV:
        for i in range(len(graphData)):
          dataStat = graphData[i][0]
          def delist(l):
            if type(l).__name__ == 'list':
              return '_'.join([delist(x) for x in l])
            else:
              return str(l)
          newFileName = output[:-4]+"_"+delist(dataPulls)+"_"+str(i)+".csv"
          if type(dataStat).__name__ != 'dict':
            assert(False)
            continue
          dataPairs = []
          for key in sorted(dataStat.keys()):
            value = dataStat[key]
            if type(value).__name__ in ["int","float"]:
              dataPairs.append((key,value))
          extraCsv = open(newFileName,"w")
          extraCsv.write(",".join(['"'+str(x[0])+'"' for x in dataPairs]))
          extraCsv.write(os.linesep)
          extraCsv.write(",".join([str(x[1]) for x in dataPairs]))
          extraCsv.write(os.linesep)
          extraCsv.close()
        utils.printCsv(csv)

  def processData(self,dataPull, data, methodInfo):
      ret = {}
      try:
        sortedData = data.tolist()
      except:
        sortedData = list(data)
      sortedData.sort()
      low = sortedData[0]
      high = sortedData[-1]
      dataRange = high - low
      ret['low'] = low
      ret['high'] = high
      if not 'bin_method' in methodInfo:
        numBins = methodInfo.get("num_bins",10)
      else:
        binMethod = methodInfo['bin_method']
        dataN = len(sortedData)
        if binMethod == 'square-root':
          numBins = int(math.ceil(math.sqrt(dataN)))
        elif binMethod == 'sturges':
          numBins = int(math.ceil(mathUtils.log2(dataN)+1))
        else:
          self.raiseADebug("Unknown bin_method "+binMethod,'ExceptedError')
          numBins = 5
      ret['num_bins'] = numBins
      kind = methodInfo.get("kind","uniform_bins")
      if kind == "uniform_bins":
        bins = [low+x*dataRange/numBins for x in range(1,numBins)]
        ret['min_bin_size'] = dataRange/numBins
      elif kind == "equal_probability":
        stride = len(sortedData)//numBins
        bins = [sortedData[x] for x in range(stride-1,len(sortedData)-stride+1,stride)]
        if len(bins) > 1:
          ret['min_bin_size'] = min(map(lambda x,y: x - y,bins[1:],bins[:-1]))
        else:
          ret['min_bin_size'] = dataRange
      counts = mathUtils.countBins(sortedData,bins)
      ret['bins'] = bins
      ret['counts'] = counts
      ret.update(mathUtils.calculateStats(sortedData))
      skewness = ret["skewness"]
      delta = math.sqrt((math.pi/2.0)*(abs(skewness)**(2.0/3.0))/
                        (abs(skewness)**(2.0/3.0)+((4.0-math.pi)/2.0)**(2.0/3.0)))
      delta = math.copysign(delta,skewness)
      alpha = delta/math.sqrt(1.0-delta**2)
      variance = ret["sample_variance"]
      omega = variance/(1.0-2*delta**2/math.pi)
      mean = ret['mean']
      xi = mean - omega*delta*math.sqrt(2.0/math.pi)
      ret['alpha'] = alpha
      ret['omega'] = omega
      ret['xi'] = xi
      return ret
#
#
#
class PrintCSV(BasePostProcessor):
  """
  PrintCSV PostProcessor class. It prints a CSV file loading data from a hdf5 database or other sources
  """
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.paramters  = ['all']
    self.inObj      = None
    self.workingDir = None
    self.printTag   = 'POSTPROCESSOR PRINTCSV'

  def inputToInternal(self,currentInput):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, None, the resulting converted object is stored as an attribute of this class
    """
    return [(currentInput)]

  def initialize(self, runInfo, inputs, initDict):
    """
     Method to initialize the PrintCSV pp. In here, the workingdir is collected and eventually created
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    BasePostProcessor.initialize(self, runInfo, inputs, initDict)
    self.workingDir               = os.path.join(runInfo['WorkingDir'],runInfo['stepName']) #generate current working dir
    runInfo['TempWorkingDir']     = self.workingDir
    try:                            os.mkdir(self.workingDir)
    except:                         self.raiseAWarning('current working dir '+self.workingDir+' already exists, this might imply deletion of present files')
    #if type(inputs[-1]).__name__ == "HDF5" : self.inObj = inputs[-1]      # this should go in run return but if HDF5, it is not pickable

  def _localReadMoreXML(self,xmlNode):
    """
    Function to read the portion of the xml input that belongs to this specialized class
    and initialize some stuff based on the inputs got
    @ In, xmlNode    : Xml element node
    @ Out, None
    """
    for child in xmlNode:
      if child.tag == 'parameters':
        param = child.text
        if(param.lower() != 'all'): self.paramters = param.strip().split(',')
        else: self.paramters[param]

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    # Check the input type
    if finishedjob.returnEvaluation() == -1: self.raiseAnError(RuntimeError,'No available Output to collect (Run probabably is not finished yet)')
    self.inObj = finishedjob.returnEvaluation()[1]
    if(self.inObj.type == "HDF5"):
      #  Input source is a database (HDF5)
      #  Retrieve the ending groups' names
      endGroupNames = self.inObj.getEndingGroupNames()
      histories = {}

      #  Construct a dictionary of all the histories
      for index in range(len(endGroupNames)): histories[endGroupNames[index]] = self.inObj.returnHistory({'history':endGroupNames[index],'filter':'whole'})
      #  If file, split the strings and add the working directory if present
      for key in histories:
        #  Loop over histories
        #  Retrieve the metadata (posion 1 of the history tuple)
        attributes = histories[key][1]
        #  Construct the header in csv format (first row of the file)
        headers = b",".join([histories[key][1]['output_space_headers'][i] for i in
                             range(len(attributes['output_space_headers']))])
        #  Construct history name
        hist = key
        #  If file, split the strings and add the working directory if present
        if self.workingDir:
          if os.path.split(output)[1] == '': output = output[:-1]
          splitted_1 = os.path.split(output)
          output = splitted_1[1]
        splitted = output.split('.')
        #  Create csv files' names
        addfile = splitted[0] + '_additional_info_' + hist + '.'+splitted[1]
        csvfilen = splitted[0] + '_' + hist + '.'+splitted[1]
        #  Check if workingDir is present and in case join the two paths
        if self.workingDir:
          addfile  = os.path.join(self.workingDir,addfile)
          csvfilen = os.path.join(self.workingDir,csvfilen)

        #  Open the files and save the data
        with open(csvfilen, 'wb') as csvfile, open(addfile, 'wb') as addcsvfile:
          #  Add history to the csv file
          np.savetxt(csvfile, histories[key][0], delimiter=",",header=utils.toString(headers))
          csvfile.write(os.linesep)
          #  process the attributes in a different csv file (different kind of informations)
          #  Add metadata to additional info csv file
          addcsvfile.write(b'# History Metadata, ' + os.linesep)
          addcsvfile.write(b'# ______________________________,' + b'_'*len(key)+b','+os.linesep)
          addcsvfile.write(b'#number of parameters,' + os.linesep)
          addcsvfile.write(utils.toBytes(str(attributes['n_params']))+b','+os.linesep)
          addcsvfile.write(b'#parameters,' + os.linesep)
          addcsvfile.write(headers+os.linesep)
          addcsvfile.write(b'#parent_id,' + os.linesep)
          addcsvfile.write(utils.toBytes(attributes['parent_id'])+os.linesep)
          addcsvfile.write(b'#start time,' + os.linesep)
          addcsvfile.write(utils.toBytes(str(attributes['start_time']))+os.linesep)
          addcsvfile.write(b'#end time,' + os.linesep)
          addcsvfile.write(utils.toBytes(str(attributes['end_time']))+os.linesep)
          addcsvfile.write(b'#number of time-steps,' + os.linesep)
          addcsvfile.write(utils.toBytes(str(attributes['n_ts']))+os.linesep)
          addcsvfile.write(os.linesep)
    else: self.raiseAnError(NotImplementedError,'for input type ' + self.inObj.type + ' not yet implemented.')

  def run(self, Input): # inObj,workingDir=None):
    """
     This method executes the postprocessor action. In this case, it just returns the input
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, object, the input
    """
    return Input[-1]
#
#
#
class BasicStatistics(BasePostProcessor):
  """
    BasicStatistics filter class. It computes all the most popular statistics
  """
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.parameters        = {}                                                                                                      #parameters dictionary (they are basically stored into a dictionary identified by tag "targets"
    self.acceptedCalcParam = ['covariance','NormalizedSensitivity','VarianceDependentSensitivity','sensitivity','pearson','expectedValue','sigma','variationCoefficient','variance','skewness','kurtosis','median','percentile']  # accepted calculation parameters
    self.what              = self.acceptedCalcParam                                                                                  # what needs to be computed... default...all
    self.methodsToRun      = []                                                                                                      # if a function is present, its outcome name is here stored... if it matches one of the known outcomes, the pp is going to use the function to compute it
    self.externalFunction  = []
    self.printTag          = 'POSTPROCESSOR BASIC STATISTIC'
    self.requiredAssObject = (True,(['Function'],[-1]))
    self.biased            = False
    self.sampled           = {}
    self.calculated        = {}

  def inputToInternal(self,currentInp):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, inputDict, dictionary of the converted data
    """
    # each post processor knows how to handle the coming inputs. The BasicStatistics postprocessor accept all the input type (files (csv only), hdf5 and datas
    if type(currentInp) == list  : currentInput = currentInp [-1]
    else                         : currentInput = currentInp
    if type(currentInput) == dict:
      if 'targets' in currentInput.keys(): return currentInput
    inputDict = {'targets':{},'metadata':{}}
    try: inType = currentInput.type
    except:
      if type(currentInput).__name__ == 'list'    : inType = 'list'
      else: self.raiseAnError(IOError,self,'BasicStatistics postprocessor accepts files,HDF5,Data(s) only! Got '+ str(type(currentInput)))
    if inType not in ['FileObject','HDF5','TimePointSet','list']: self.raiseAnError(IOError,self,'BasicStatistics postprocessor accepts files,HDF5,Data(s) only! Got '+ str(inType) + '!!!!')
    if inType == 'FileObject':
      if currentInput.subtype == 'csv': pass
    if inType == 'HDF5': pass # to be implemented
    if inType in ['TimePointSet']:
      for targetP in self.parameters['targets']:
        if   targetP in currentInput.getParaKeys('input' ):
          inputDict['targets'][targetP] = currentInput.getParam('input' ,targetP)
          self.sampled[targetP]         = currentInput.getParam('input' ,targetP)
        elif targetP in currentInput.getParaKeys('output'):
          inputDict['targets'][targetP] = currentInput.getParam('output',targetP)
          self.calculated[targetP]      = currentInput.getParam('output',targetP)
      inputDict['metadata'] = currentInput.getAllMetadata()
#     # now we check if the sampler that genereted the samples are from adaptive... in case... create the grid
      if inputDict['metadata'].keys().count('SamplerType') > 0: pass

    return inputDict

  def initialize(self, runInfo, inputs, initDict):
    """
     Method to initialize the BasicStatistic pp. In here the working dir is
     grepped.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    BasePostProcessor.initialize(self, runInfo, inputs, initDict)
    self.__workingDir = runInfo['WorkingDir']

  def _localReadMoreXML(self,xmlNode):
    """
      Function to read the portion of the xml input that belongs to this specialized class
      and initialize some stuff based on the inputs got
      @ In, xmlNode    : Xml element node
      @ Out, None
    """
    for child in xmlNode:
      if child.tag =="what":
        self.what = child.text
        if self.what == 'all': self.what = self.acceptedCalcParam
        else:
          for whatc in self.what.split(','):
            if whatc not in self.acceptedCalcParam: self.raiseAnError(IOError,'BasicStatistics postprocessor asked unknown operation ' + whatc + '. Available '+str(self.acceptedCalcParam))
          self.what = self.what.split(',')
      if child.tag =="parameters"   : self.parameters['targets'] = child.text.split(',')
      if child.tag =="methodsToRun" : self.methodsToRun          = child.text.split(',')
      if child.tag =="biased"       :
          if child.text.lower() in utils.stringsThatMeanTrue(): self.biased = True

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    #output
    parameterSet = list(set(list(self.parameters['targets'])))
    if finishedjob.returnEvaluation() == -1: self.raiseAnError(RuntimeError,' No available Output to collect (Run probabably is not finished yet)')
    outputDict = finishedjob.returnEvaluation()[1]
    methodToTest = []
    for key in self.methodsToRun:
      if key not in self.acceptedCalcParam: methodToTest.append(key)
    if output.type == 'FileObject':
      availextens = ['csv','txt']
      outputextension = output.split('.')[-1].lower()
      if outputextension not in availextens:
        self.raiseAWarning('BasicStatistics postprocessor output extension you input is '+outputextension)
        self.raiseAWarning('Available are '+str(availextens)+ '. Convertint extension to '+str(availextens[0])+'!')
        outputextension = availextens[0]
      if outputextension != 'csv': separator = ' '
      else                       : separator = ','
      basicStatFilename = os.path.join(self.__workingDir,output[:output.rfind('.')]+'.'+outputextension)
      self.raiseADebug("workingDir",self.__workingDir+" output "+str(output.split('.')))
      self.raiseADebug('BasicStatistics postprocessor: dumping output in file named ' + basicStatFilename)
      with open(basicStatFilename, 'wb') as basicStatdump:
        basicStatdump.write('BasicStatistics '+separator+str(self.name)+os.linesep)
        basicStatdump.write('----------------'+separator+'-'*len(str(self.name))+os.linesep)
        for targetP in parameterSet:
          self.raiseADebug('BasicStatistics postprocessor: writing variable '+ targetP)
          basicStatdump.write('Variable'+ separator + targetP +os.linesep)
          basicStatdump.write('--------'+ separator +'-'*len(targetP)+os.linesep)
          for what in outputDict.keys():
            if what not in ['covariance','pearson','NormalizedSensitivity','VarianceDependentSensitivity','sensitivity'] + methodToTest:
              self.raiseADebug('BasicStatistics postprocessor: writing variable '+ targetP + '. Parameter: '+ what)
              basicStatdump.write(what+ separator + '%.8E' % outputDict[what][targetP]+os.linesep)
        maxLength = max(len(max(parameterSet, key=len))+5,16)
        for what in outputDict.keys():
          if what in ['covariance','pearson','NormalizedSensitivity','VarianceDependentSensitivity']:
            self.raiseADebug('BasicStatistics postprocessor: writing parameter matrix '+ what )
            basicStatdump.write(what+os.linesep)
            if outputextension != 'csv': basicStatdump.write(' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in parameterSet])+os.linesep)
            else                       : basicStatdump.write('matrix' + separator+''.join([str(item) + separator for item in parameterSet])+os.linesep)
            for index in range(len(parameterSet)):
              if outputextension != 'csv': basicStatdump.write(parameterSet[index] + ' '*(maxLength-len(parameterSet[index])) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict[what][index]])+os.linesep)
              else                       : basicStatdump.write(parameterSet[index] + ''.join([separator +'%.8E' % item for item in outputDict[what][index]])+os.linesep)
          if what == 'sensitivity':
            if not self.sampled: self.raiseAWarning('No sampled Input variable defined in '+str(self.name)+' PP. The I/O Sensitivity Matrix wil not be calculated.')
            else:
              self.raiseADebug('BasicStatistics postprocessor: writing parameter matrix '+ what )
              basicStatdump.write(what+os.linesep)
              calculatedSet = list(set(list(self.calculated)))
              sampledSet    = list(set(list(self.sampled)))
              if outputextension != 'csv': basicStatdump.write(' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in sampledSet])+os.linesep)
              else                       : basicStatdump.write('matrix' + separator+''.join([str(item) + separator for item in sampledSet])+os.linesep)
              for index in range(len(calculatedSet)):
                if outputextension != 'csv': basicStatdump.write(calculatedSet[index] + ' '*(maxLength-len(calculatedSet[index])) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict[what][index]])+os.linesep)
                else                       : basicStatdump.write(calculatedSet[index] + ''.join([separator +'%.8E' % item for item in outputDict[what][index]])+os.linesep)
        if self.externalFunction:
          self.raiseADebug('BasicStatistics postprocessor: writing External Function results')
          basicStatdump.write(os.linesep +'EXT FUNCTION '+os.linesep)
          basicStatdump.write('------------'+os.linesep)
          for what in self.methodsToRun:
            if what not in self.acceptedCalcParam:
              self.raiseADebug('BasicStatistics postprocessor: writing External Function parameter '+ what )
              basicStatdump.write(what+ separator + '%.8E' % outputDict[what]+os.linesep)
    elif output.type == 'DataObjects':
      self.raiseADebug('BasicStatistics postprocessor: dumping output in data object named ' + output.name)
      for what in outputDict.keys():
        if what not in ['covariance','pearson','NormalizedSensitivity','VarianceDependentSensitivity','sensitivity'] + methodToTest:
          for targetP in parameterSet:
            self.raiseADebug('BasicStatistics postprocessor: dumping variable '+ targetP + '. Parameter: '+ what + '. Metadata name = '+ targetP+'|'+what)
            output.updateMetadata(targetP+'|'+what,outputDict[what][targetP])
        else:
          if what not in methodToTest:
            self.raiseADebug('BasicStatistics postprocessor: dumping matrix '+ what + '. Metadata name = ' + what + '. Targets stored in ' + 'targets|'+what)
            output.updateMetadata('targets|'+what,parameterSet)
            output.updateMetadata(what,outputDict[what])
      if self.externalFunction:
        self.raiseADebug('BasicStatistics postprocessor: dumping External Function results')
        for what in self.methodsToRun:
          if what not in self.acceptedCalcParam:
            output.updateMetadata(what,outputDict[what])
            self.raiseADebug('BasicStatistics postprocessor: dumping External Function parameter '+ what)
    elif output.type == 'HDF5' : self.raiseAWarning('BasicStatistics postprocessor: Output type '+ str(output.type) + ' not yet implemented. Skip it !!!!!')
    else: self.raiseAnError(IOError,'BasicStatistics postprocessor: Output type '+ str(output.type) + ' unknown.')

  def run(self, InputIn):
    """
     This method executes the postprocessor action. In this case, it computes all the requested statistical FOMs
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, dictionary, Dictionary containing the results
    """
    Input  = self.inputToInternal(InputIn)
    outputDict = {}

    if self.externalFunction:
      # there is an external function
      for what in self.methodsToRun:
        outputDict[what] = self.externalFunction.evaluate(what,Input['targets'])
        # check if "what" corresponds to an internal method
        if what in self.acceptedCalcParam:
          if what not in ['pearson','covariance','NormalizedSensitivity','VarianceDependentSensitivity','sensitivity']:
            if type(outputDict[what]) != dict: self.raiseAnError(IOError,'BasicStatistics postprocessor: You have overwritten the "'+what+'" method through an external function, it must be a dictionary!!')
          else:
            if type(outputDict[what]) != np.ndarray: self.raiseAnError(IOError,'BasicStatistics postprocessor: You have overwritten the "'+what+'" method through an external function, it must be a numpy.ndarray!!')
            if len(outputDict[what].shape) != 2:     self.raiseAnError(IOError,'BasicStatistics postprocessor: You have overwritten the "'+what+'" method through an external function, it must be a 2D numpy.ndarray!!')

    #setting some convenience values
    parameterSet = list(set(list(self.parameters['targets'])))  #@Andrea I am using set to avoid the test: if targetP not in outputDict[what].keys()
    N            = [np.asarray(Input['targets'][targetP]).size for targetP in parameterSet]
    if 'metadata' in Input.keys(): pbPresent = Input['metadata'].keys().count('ProbabilityWeight')>0
    else                         : pbPresent = False
    if not pbPresent:
      if 'metadata' in Input.keys():
        if Input['metadata'].keys().count('SamplerType') > 0:
          if Input['metadata']['SamplerType'][0] != 'MC' : self.raiseAWarning('BasicStatistics postprocessor can not compute expectedValue without ProbabilityWeights. Use unit weight')
        else: self.raiseAWarning('BasicStatistics postprocessor can not compute expectedValue without ProbabilityWeights. Use unit weight')
      pbweights    = np.zeros(len(Input['targets'][self.parameters['targets'][0]]),dtype=np.float)
      pbweights[:] = 1.0/pbweights.size # it was an Integer Division (1/integer) => 0!!!!!!!! Andrea
    else: pbweights       = Input['metadata']['ProbabilityWeight']
    sumSquarePbWeights  = np.sum(np.square(pbweights))
    sumPbWeights        = np.sum(pbweights)
    # if here because the user could have overwritten the method through the external function
    if 'expectedValue' not in outputDict.keys(): outputDict['expectedValue'] = {}
    expValues = np.zeros(len(parameterSet))
    for myIndex, targetP in enumerate(parameterSet):
      outputDict['expectedValue'][targetP]= np.average(Input['targets'][targetP],weights=pbweights)
      expValues[myIndex] = outputDict['expectedValue'][targetP]

    for what in self.what:
      if what not in outputDict.keys(): outputDict[what] = {}
      #sigma
      if what == 'sigma':
        for myIndex, targetP in enumerate(parameterSet):
          outputDict[what][targetP] = np.sqrt(np.average((Input['targets'][targetP]-expValues[myIndex])**2,weights=pbweights)/(sumPbWeights-sumSquarePbWeights/sumPbWeights))
      #variance
      if what == 'variance':
        for myIndex, targetP in enumerate(parameterSet):
          outputDict[what][targetP] = np.average((Input['targets'][targetP]-expValues[myIndex])**2,weights=pbweights)/(sumPbWeights-sumSquarePbWeights/sumPbWeights)
      #coefficient of variation (sigma/mu)
      if what == 'variationCoefficient':
        for myIndex, targetP in enumerate(parameterSet):
          sigma = np.sqrt(np.average((Input['targets'][targetP]-expValues[myIndex])**2,weights=pbweights)/(sumPbWeights-sumSquarePbWeights/sumPbWeights))
          outputDict[what][targetP] = sigma/outputDict['expectedValue'][targetP]
      #kurtosis
      if what == 'kurtosis':
        for myIndex, targetP in enumerate(parameterSet):
          if pbPresent:
              sigma = np.sqrt(np.average((Input['targets'][targetP]-expValues[myIndex])**2, weights=pbweights))
              outputDict[what][targetP] = np.average(((Input['targets'][targetP]-expValues[myIndex])**4), weights=pbweights)/sigma**4
          else:
            outputDict[what][targetP] = -3.0 + (np.sum((np.asarray(Input['targets'][targetP]) - expValues[myIndex])**4)/(N[myIndex]-1))/(np.sum((np.asarray(Input['targets'][targetP]) - expValues[myIndex])**2)/float(N[myIndex]-1))**2
      #skewness
      if what == 'skewness':
        for myIndex, targetP in enumerate(parameterSet):
          if pbPresent:
            sigma = np.sqrt(np.average((Input['targets'][targetP]-expValues[myIndex])**2, weights=pbweights))
            outputDict[what][targetP] = np.average((((Input['targets'][targetP]-expValues[myIndex])/sigma)**3), weights=pbweights)
          else:
            outputDict[what][targetP] = (np.sum((np.asarray(Input['targets'][targetP]) - expValues[myIndex])**3)*(N[myIndex]-1)**-1)/(np.sum((np.asarray(Input['targets'][targetP]) - expValues[myIndex])**2)/float(N[myIndex]-1))**1.5
      #median
      if what == 'median':
        for targetP in parameterSet: outputDict[what][targetP]  = np.median(Input['targets'][targetP])
      #percentile
      if what == 'percentile':
        outputDict.pop(what)
        if what+'_5%'  not in outputDict.keys(): outputDict[what+'_5%']  ={}
        if what+'_95%' not in outputDict.keys(): outputDict[what+'_95%'] ={}
        for targetP in self.parameters['targets'  ]:
          if targetP not in outputDict[what+'_5%'].keys():
            outputDict[what+'_5%'][targetP]  = np.percentile(Input['targets'][targetP],5)
          if targetP not in outputDict[what+'_95%'].keys():
            outputDict[what+'_95%'][targetP]  = np.percentile(Input['targets'][targetP],95)
      #cov matrix
      if what == 'covariance':
        feat = np.zeros((len(Input['targets'].keys()),utils.first(Input['targets'].values()).size))
        for myIndex, targetP in enumerate(parameterSet): feat[myIndex,:] = Input['targets'][targetP][:]
        outputDict[what] = self.covariance(feat, weights=pbweights)
      #pearson matrix
      if what == 'pearson':
        feat = np.zeros((len(Input['targets'].keys()),utils.first(Input['targets'].values()).size))
        for myIndex, targetP in enumerate(parameterSet): feat[myIndex,:] = Input['targets'][targetP][:]
        outputDict[what] = self.corrCoeff(feat, weights=pbweights) #np.corrcoef(feat)
      #sensitivity matrix
      if what == 'sensitivity':
        if self.sampled:
          self.SupervisedEngine          = {}         # dict of ROM instances (== number of targets => keys are the targets)
          for target in self.calculated:
            self.SupervisedEngine[target] =  SupervisedLearning.returnInstance('SciKitLearn',self,**{'SKLtype':'linear_model|LinearRegression',
                                                                                                     'Features':','.join(self.sampled.keys()),
                                                                                                     'Target':target})
            self.SupervisedEngine[target].train(Input['targets'])
          for myIndex in range(len(self.calculated)):
            outputDict[what][myIndex] = self.SupervisedEngine[self.calculated.keys()[myIndex]].ROM.coef_
      #VarianceDependentSensitivity matrix
      if what == 'VarianceDependentSensitivity':
        feat = np.zeros((len(Input['targets'].keys()),utils.first(Input['targets'].values()).size))
        for myIndex, targetP in enumerate(parameterSet): feat[myIndex,:] = Input['targets'][targetP][:]
        covMatrix = self.covariance(feat, weights=pbweights)
        variance  = np.zeros(len(list(parameterSet)))
        for myIndex, targetP in enumerate(parameterSet):
          variance[myIndex] = np.average((Input['targets'][targetP]-expValues[myIndex])**2,weights=pbweights)/(sumPbWeights-sumSquarePbWeights/sumPbWeights)
        for myIndex in range(len(parameterSet)):
          outputDict[what][myIndex] = covMatrix[myIndex,:]/(variance[myIndex])
      #Normalizzate sensitivity matrix: linear regression slopes normalizited by the mean (% change)/(% change)
      if what == 'NormalizedSensitivity':
        feat = np.zeros((len(Input['targets'].keys()),utils.first(Input['targets'].values()).size))
        for myIndex, targetP in enumerate(parameterSet): feat[myIndex,:] = Input['targets'][targetP][:]
        covMatrix = self.covariance(feat, weights=pbweights)
        variance  = np.zeros(len(list(parameterSet)))
        for myIndex, targetP in enumerate(parameterSet):
          variance[myIndex] = np.average((Input['targets'][targetP]-expValues[myIndex])**2,weights=pbweights)/(sumPbWeights-sumSquarePbWeights/sumPbWeights)
        for myIndex in range(len(parameterSet)):
          outputDict[what][myIndex] = ((covMatrix[myIndex,:]/variance)*expValues)/expValues[myIndex]

    # print on screen
    self.raiseADebug('BasicStatistics '+str(self.name)+'pp outputs')
    methodToTest = []
    for key in self.methodsToRun:
      if key not in self.acceptedCalcParam: methodToTest.append(key)
    msg=os.linesep
    for targetP in parameterSet:
      msg+='        *************'+'*'*len(targetP)+'***' + os.linesep
      msg+='        * Variable * '+ targetP +'  *' + os.linesep
      msg+='        *************'+'*'*len(targetP)+'***' + os.linesep
      for what in outputDict.keys():
        if what not in ['covariance','pearson','NormalizedSensitivity','VarianceDependentSensitivity','sensitivity'] + methodToTest:
          msg+='               '+'**'+'*'*len(what)+ '***'+6*'*'+'*'*8+'***' + os.linesep
          msg+='               '+'* '+what+' * ' + '%.8E' % outputDict[what][targetP]+'  *' + os.linesep
          msg+='               '+'**'+'*'*len(what)+ '***'+6*'*'+'*'*8+'***' + os.linesep
    maxLength = max(len(max(parameterSet, key=len))+5,16)
    if 'covariance' in outputDict.keys():
      msg+=' '*maxLength+'*****************************' + os.linesep
      msg+=' '*maxLength+'*         Covariance        *' + os.linesep
      msg+=' '*maxLength+'*****************************' + os.linesep
      msg+=' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in parameterSet]) + os.linesep
      for index in range(len(parameterSet)):
        msg+=parameterSet[index] + ' '*(maxLength-len(parameterSet[index])) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict['covariance'][index]]) + os.linesep
    if 'pearson' in outputDict.keys():
      msg+=' '*maxLength+'*****************************' + os.linesep
      msg+=' '*maxLength+'*    Pearson/Correlation    *' + os.linesep
      msg+=' '*maxLength+'*****************************' + os.linesep
      msg+=' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in parameterSet]) + os.linesep
      for index in range(len(parameterSet)):
        msg+=parameterSet[index] + ' '*(maxLength-len(parameterSet[index])) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict['pearson'][index]]) + os.linesep
    if 'VarianceDependentSensitivity' in outputDict.keys():
      msg+=' '*maxLength+'******************************' + os.linesep
      msg+=' '*maxLength+'*VarianceDependentSensitivity*' + os.linesep
      msg+=' '*maxLength+'******************************' + os.linesep
      msg+=' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in parameterSet]) + os.linesep
      for index in range(len(parameterSet)):
        msg+=parameterSet[index] + ' '*(maxLength-len(parameterSet[index])) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict['VarianceDependentSensitivity'][index]]) + os.linesep
    if 'NormalizedSensitivity' in outputDict.keys():
      msg+=' '*maxLength+'******************************' + os.linesep
      msg+=' '*maxLength+'* Normalized V.D.Sensitivity *' + os.linesep
      msg+=' '*maxLength+'******************************' + os.linesep
      msg+=' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in parameterSet]) + os.linesep
      for index in range(len(parameterSet)):
        msg+=parameterSet[index] + ' '*(maxLength-len(parameterSet[index])) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict['NormalizedSensitivity'][index]]) + os.linesep
    if 'sensitivity' in outputDict.keys():
      if not self.sampled: self.raiseAWarning('No sampled Input variable defined in '+str(self.name)+' PP. The I/O Sensitivity Matrix wil not be calculated.')
      else:
        msg+=' '*maxLength+'*****************************' + os.linesep
        msg+=' '*maxLength+'*    I/O   Sensitivity      *' + os.linesep
        msg+=' '*maxLength+'*****************************' + os.linesep
        msg+=' '*maxLength+''.join([str(item) + ' '*(maxLength-len(item)) for item in self.sampled]) + os.linesep
        for index in range(len(self.sampled.keys())):
          variable = self.sampled.keys()[index]
          msg+=self.calculated.keys()[index] + ' '*(maxLength-len(variable)) + ''.join(['%.8E' % item + ' '*(maxLength-14) for item in outputDict['sensitivity'][index]/outputDict['sigma'][variable]]) + os.linesep

    if self.externalFunction:
      msg+=' '*maxLength+'+++++++++++++++++++++++++++++' + os.linesep
      msg+=' '*maxLength+'+ OUTCOME FROM EXT FUNCTION +' + os.linesep
      msg+=' '*maxLength+'+++++++++++++++++++++++++++++' + os.linesep
      for what in self.methodsToRun:
        if what not in self.acceptedCalcParam:
          msg+='              '+'**'+'*'*len(what)+ '***'+6*'*'+'*'*8+'***' + os.linesep
          msg+='              '+'* '+what+' * ' + '%.8E' % outputDict[what]+'  *' + os.linesep
          msg+='              '+'**'+'*'*len(what)+ '***'+6*'*'+'*'*8+'***' + os.linesep
    self.raiseADebug(msg)
    return outputDict

  def covariance(self, feature, weights=None, rowvar=1):
      """
      This method calculates the covariance Matrix for the given data.
      Unbiased unweighted covariance matrix, weights is None, bias is 0 (default)
      Biased unweighted covariance matrix,   weights is None, bias is 1
      Unbiased weighted covariance matrix,   weights is not None, bias is 0
      Biased weighted covariance matrix,     weights is not None, bias is 1
      can be calcuated depending on the selection of the inputs.
      @Inputs  -> feature, weights, bias, rowvar
      @Outputs -> covMatrix
      """
      X    = np.array(feature, ndmin=2, dtype=np.result_type(feature, np.float64))
      diff = np.zeros(feature.shape, dtype=np.result_type(feature, np.float64))
      if weights != None: w = np.array(weights, ndmin=1, dtype=np.float64)
      if X.shape[0] == 1: rowvar = 1
      if rowvar:
          N = X.shape[1]
          axis = 0
      else:
          N = X.shape[0]
          axis = 1
      if weights != None:
          sumWeights       = np.sum(weights)
          sumSquareWeights = np.sum(np.square(weights))
          diff = X - np.atleast_2d(np.average(X, axis=1-axis, weights=weights)).T
      else:
          diff = X - np.mean(X, axis=1-axis, keepdims=True)
      if weights != None:
          if not self.biased: fact = float(sumWeights/((sumWeights*sumWeights - sumSquareWeights)))
          else:               fact = float(1.0/(sumWeights))
      else:
          if not self.biased: fact = float(1.0/(N-1))
          else:               fact = float(1.0/N)
      if fact <= 0:
          warnings.warn("Degrees of freedom <= 0", RuntimeWarning)
          fact = 0.0
      if not rowvar:
        if weights != None: covMatrix = (np.dot(diff.T, w*diff)*fact).squeeze()
        else:               covMatrix = (np.dot(diff.T, diff)*fact).squeeze()
      else:
        if weights != None: covMatrix = (np.dot(w*diff, diff.T)*fact).squeeze()
        else:               covMatrix = (np.dot(diff, diff.T)*fact).squeeze()
      return covMatrix

  def corrCoeff(self, feature, weights=None, rowvar=1):
      covM = self.covariance(feature, weights, rowvar)
      try: d = np.diag(covM)
      except ValueError:  # scalar covariance
      # nan if incorrect value (nan, inf, 0), 1 otherwise
        return covM / covM
      return covM / np.sqrt(np.multiply.outer(d, d))
#
#
#
class LoadCsvIntoInternalObject(BasePostProcessor):
  """
    LoadCsvIntoInternalObject pp class. It is in charge of loading CSV files into one of the internal object (Data(s) or HDF5)
  """
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.sourceDirectory = None
    self.listOfCsvFiles = []
    self.printTag = 'POSTPROCESSOR LoadCsv'

  def initialize(self, runInfo, inputs, initDict):
    """
     Method to initialize the LoadCSV pp.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    BasePostProcessor.initialize(self, runInfo, inputs, initDict)
    self.__workingDir = runInfo['WorkingDir']
    if '~' in self.sourceDirectory               : self.sourceDirectory = os.path.expanduser(self.sourceDirectory)
    if not os.path.isabs(self.sourceDirectory)   : self.sourceDirectory = os.path.normpath(os.path.join(self.__workingDir,self.sourceDirectory))
    if not os.path.exists(self.sourceDirectory)  : self.raiseAnError(IOError,"The directory indicated for PostProcessor "+ self.name + "does not exist. Path: "+self.sourceDirectory)
    for _dir,_,_ in os.walk(self.sourceDirectory): self.listOfCsvFiles.extend(glob(os.path.join(_dir,"*.csv")))
    if len(self.listOfCsvFiles) == 0             : self.raiseAnError(IOError,"The directory indicated for PostProcessor "+ self.name + "does not contain any csv file. Path: "+self.sourceDirectory)
    self.listOfCsvFiles.sort()

  def inputToInternal(self,currentInput):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, list, list of csv files
    """
    return self.listOfCsvFiles

  def _localReadMoreXML(self,xmlNode):
    """
      Function to read the portion of the xml input that belongs to this specialized class
      and initialize some stuff based on the inputs got
      @ In, xmlNode    : Xml element node
      @ Out, None
    """
    for child in xmlNode:
      if child.tag =="directory": self.sourceDirectory = child.text
    if not self.sourceDirectory: self.raiseAnError(IOError,"The PostProcessor "+ self.name + "needs a directory for loading the csv files!")

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    for index,csvFile in enumerate(self.listOfCsvFiles):

      attributes={"prefix":str(index),"input_file":self.name,"type":"csv","name":os.path.join(self.sourceDirectory,csvFile)}
      metadata = finishedjob.returnMetadata()
      if metadata:
        for key in metadata: attributes[key] = metadata[key]
      try:                   output.addGroup(attributes,attributes)
      except AttributeError:
        output.addOutput(os.path.join(self.sourceDirectory,csvFile),attributes)
        if metadata:
          for key,value in metadata.items(): output.updateMetadata(key,value,attributes)

  def run(self, InputIn):
    """
     This method executes the postprocessor action. In this case, it just returns the list of csv files
     @ In,  Input, object, object contained the data to process. (inputToInternal output)
     @ Out, list, list of csv files
    """
    return self.listOfCsvFiles
#
#
#
class LimitSurface(BasePostProcessor):
  """
    LimitSurface filter class. It computes the limit surface associated to a dataset
  """

  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.parameters        = {}               #parameters dictionary (they are basically stored into a dictionary identified by tag "targets"
    self.surfPoint         = None             #coordinate of the points considered on the limit surface
    self.testMatrix        = None             #This is the n-dimensional matrix representing the testing grid
    #self.oldTestMatrix     = None             #This is the test matrix to use to store the old evaluation of the function
    self.functionValue     = {}               #This a dictionary that contains np vectors with the value for each variable and for the goal function
    self.ROM               = None             #Pointer to a ROM
    self.externalFunction  = None             #Pointer to an external Function
    self.subGridTol        = 1.0e-4           #SubGrid tollerance
    self.gridVectors       = {}
    self.gridFromOutside   = False            #The grid has been passed from outside (self._initFromDict)?
    self.lsSide            = "negative"       # Limit surface side to compute the LS for (negative,positive,both)
    self.requiredAssObject = (True,(['ROM','Function'],[-1,1]))
    self.printTag = 'POSTPROCESSOR LIMITSURFACE'

  def inputToInternal(self,currentInp):
    """
     Method to convert an input object into the internal format that is
     understandable by this pp.
     @ In, currentInput, object, an object that needs to be converted
     @ Out, dict, the resulting dictionary containing features and response
    """
    # each post processor knows how to handle the coming inputs. The BasicStatistics postprocessor accept all the input type (files (csv only), hdf5 and datas
    if type(currentInp) == list: currentInput = currentInp[-1]
    else                       : currentInput = currentInp
    if type(currentInp) == dict:
      if 'targets' in currentInput.keys(): return
    inputDict = {'targets':{},'metadata':{}}
    try   : inType = currentInput.type
    except: self.raiseAnError(IOError,self,'LimitSurface postprocessor accepts files,HDF5,Data(s) only! Got '+ str(type(currentInput)))
    if inType == 'FileObject':
      if currentInput.subtype == 'csv': pass
    if inType == 'HDF5': pass # to be implemented
    if inType in ['TimePointSet']:
      for targetP in self.parameters['targets']:
        if   targetP in currentInput.getParaKeys('input' ): inputDict['targets'][targetP] = currentInput.getParam('input' ,targetP)
        elif targetP in currentInput.getParaKeys('output'): inputDict['targets'][targetP] = currentInput.getParam('output',targetP)
      inputDict['metadata'] = currentInput.getAllMetadata()
    # to be added
    return inputDict

  def _initializeLSpp(self, runInfo, inputs, initDict):
    """
     Method to initialize the LS post processor (create grid, etc.)
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    BasePostProcessor.initialize(self, runInfo, inputs, initDict)
    self.externalFunction = self.assemblerDict['Function'][0][3]
    if 'ROM' not in self.assemblerDict.keys():
      mySrting= ','.join(list(self.parameters['targets']))
      self.ROM = SupervisedLearning.returnInstance('SciKitLearn',self,**{'SKLtype':'neighbors|KNeighborsClassifier','Features':mySrting,'Target':self.externalFunction.name})
    else: self.ROM = self.assemblerDict['ROM'][0][3]
    self.ROM.reset()
    self.__workingDir = runInfo['WorkingDir']
    self.indexes = -1
    for index,inp in enumerate(self.inputs):
      if type(inp) in [str,bytes,unicode]: self.raiseAnError(IOError,'LimitSurface PostProcessor only accepts Data(s) as inputs!')
      if inp.type in ['TimePointSet','TimePoint']: self.indexes = index
    if self.indexes == -1: self.raiseAnError(IOError,'LimitSurface PostProcessor needs a TimePoint or TimePointSet as INPUT!!!!!!')
    else:
      # check if parameters are contained in the data
      inpKeys = self.inputs[self.indexes].getParaKeys("inputs")
      outKeys = self.inputs[self.indexes].getParaKeys("outputs")
      self.paramType ={}
      for param in self.parameters['targets']:
        if param not in inpKeys+outKeys: self.raiseAnError(IOError,'LimitSurface PostProcessor: The param '+ param+' not contained in Data '+self.inputs[self.indexes].name +' !')
        if param in inpKeys: self.paramType[param] = 'inputs'
        else:                self.paramType[param] = 'outputs'
    self.nVar        = len(self.parameters['targets'])         #Total number of variables
    stepLength        = self.subGridTol**(1./float(self.nVar)) #build the step size in 0-1 range such as the differential volume is equal to the tolerance
    self.axisName     = []                                     #this list is the implicit mapping of the name of the variable with the grid axis ordering self.axisName[i] = name i-th coordinate
    #here we build lambda function to return the coordinate of the grid point depending if the tolerance is on probability or on volume
    stepParam = lambda x: [stepLength*(max(self.inputs[self.indexes].getParam(self.paramType[x],x))-min(self.inputs[self.indexes].getParam(self.paramType[x],x))),
                                       min(self.inputs[self.indexes].getParam(self.paramType[x],x)),
                                       max(self.inputs[self.indexes].getParam(self.paramType[x],x))]
    #moving forward building all the information set
    pointByVar = [None]*self.nVar                              #list storing the number of point by cooridnate
    #building the grid point coordinates
    for varId, varName in enumerate(self.parameters['targets']):
      self.axisName.append(varName)
      if not self.gridFromOutside:
        [myStepLength, start, end]  = stepParam(varName)
        if start == end:
          start = start - 0.001*start
          end   = end   + 0.001*end
          myStepLength = stepLength*(end - start)
        start                      += 0.5*myStepLength
        self.gridVectors[varName]   = np.arange(start,end,myStepLength)
      pointByVar[varId]           = np.shape(self.gridVectors[varName])[0]
    self.gridShape                = tuple   (pointByVar)          #tuple of the grid shape
    self.testGridLength           = np.prod (pointByVar)          #total number of point on the grid
    self.testMatrix               = np.zeros(self.gridShape)      #grid where the values of the goalfunction are stored
    #self.oldTestMatrix            = np.zeros(self.gridShape)      #swap matrix fro convergence test
    self.gridCoorShape            = tuple(pointByVar+[self.nVar]) #shape of the matrix containing all coordinate of all points in the grid
    self.gridCoord                = np.zeros(self.gridCoorShape)  #the matrix containing all coordinate of all points in the grid
    #filling the coordinate on the grid
    myIterator = np.nditer(self.gridCoord,flags=['multi_index'])
    while not myIterator.finished:
      coordinateID  = myIterator.multi_index[-1]
      axisName      = self.axisName[coordinateID]
      valuePosition = myIterator.multi_index[coordinateID]
      self.gridCoord[myIterator.multi_index] = self.gridVectors[axisName][valuePosition]
      myIterator.iternext()
    self.axisStepSize = {}
    for varName in self.parameters['targets']:
      self.axisStepSize[varName] = np.asarray([self.gridVectors[varName][myIndex+1]-self.gridVectors[varName][myIndex] for myIndex in range(len(self.gridVectors[varName])-1)])
    self.raiseADebug('self.gridShape '+str(self.gridShape))
    self.raiseADebug('self.testGridLength '+str(self.testGridLength))
    self.raiseADebug('self.gridCoorShape '+str(self.gridCoorShape))
    for key in self.gridVectors.keys():
      self.raiseADebug('the variable '+key+' has coordinate: '+str(self.gridVectors[key]))
    myIterator          = np.nditer(self.testMatrix,flags=['multi_index'])
    while not myIterator.finished:
      self.raiseADebug('Indexes: '+str(myIterator.multi_index)+'    coordinate: '+str(self.gridCoord[myIterator.multi_index]))
      myIterator.iternext()

  def _initializeLSppROM(self, inp, raiseErrorIfNotFound = True):
    """
     Method to initialize the LS accellation rom
     @ In, inp, Data(s) object, data object containing the training set
     @ In, raiseErrorIfNotFound, bool, throw an error if the limit surface is not found
    """
    self.raiseADebug('Initiate training')
    self.raiseADebug('Initiate training')
    if type(inp) == dict:
      self.functionValue.update(inp['inputs' ])
      self.functionValue.update(inp['outputs'])
    else:
      self.functionValue.update(inp.getParametersValues('inputs',nodeid='RecontructEnding'))
      self.functionValue.update(inp.getParametersValues('outputs',nodeid='RecontructEnding'))

    #recovery the index of the last function evaluation performed
    if self.externalFunction.name in self.functionValue.keys(): indexLast = len(self.functionValue[self.externalFunction.name])-1
    else                                                      : indexLast = -1

    #index of last set of point tested and ready to perform the function evaluation
    indexEnd  = len(self.functionValue[self.axisName[0]])-1
    tempDict  = {}
    if self.externalFunction.name in self.functionValue.keys():
      self.functionValue[self.externalFunction.name] = np.append( self.functionValue[self.externalFunction.name], np.zeros(indexEnd-indexLast))
    else: self.functionValue[self.externalFunction.name] = np.zeros(indexEnd+1)

    for myIndex in range(indexLast+1,indexEnd+1):
      for key, value in self.functionValue.items(): tempDict[key] = value[myIndex]
      #self.hangingPoints= self.hangingPoints[    ~(self.hangingPoints==np.array([tempDict[varName] for varName in self.axisName])).all(axis=1)     ][:]
      self.functionValue[self.externalFunction.name][myIndex] =  self.externalFunction.evaluate('residuumSign',tempDict)
      if abs(self.functionValue[self.externalFunction.name][myIndex]) != 1.0: self.raiseAnError(IOError,'LimitSurface: the function evaluation of the residuumSign method needs to return a 1 or -1!')
      if self.externalFunction.name in inp.getParaKeys('inputs'): inp.self.updateInputValue (self.externalFunction.name,self.functionValue[self.externalFunction.name][myIndex])
      if self.externalFunction.name in inp.getParaKeys('output'): inp.self.updateOutputValue(self.externalFunction.name,self.functionValue[self.externalFunction.name][myIndex])
    if np.sum(self.functionValue[self.externalFunction.name]) == float(len(self.functionValue[self.externalFunction.name])) or np.sum(self.functionValue[self.externalFunction.name]) == -float(len(self.functionValue[self.externalFunction.name])):
      if raiseErrorIfNotFound: self.raiseAnError(ValueError,'LimitSurface: all the Function evaluations brought to the same result (No Limit Surface has been crossed...). Increase or change the data set!')
      else                   : self.raiseAWarning('LimitSurface: all the Function evaluations brought to the same result (No Limit Surface has been crossed...)!')
    #printing----------------------
    self.raiseADebug('LimitSurface: Mapping of the goal function evaluation performed')
    self.raiseADebug('LimitSurface: Already evaluated points and function values:')
    keyList = list(self.functionValue.keys())
    self.raiseADebug(','.join(keyList))
    for index in range(indexEnd+1):
      self.raiseADebug(','.join([str(self.functionValue[key][index]) for key in keyList]))
    #printing----------------------
    tempDict = {}
    for name in self.axisName: tempDict[name] = np.asarray(self.functionValue[name])
    tempDict[self.externalFunction.name] = self.functionValue[self.externalFunction.name]
    self.ROM.train(tempDict)
    self.raiseADebug('LimitSurface: Training performed')
    self.raiseADebug('LimitSurface: Training finished')

  def initialize(self, runInfo, inputs, initDict):
    """
     Method to initialize the LS pp.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    self._initializeLSpp(runInfo, inputs, initDict)
    self._initializeLSppROM(self.inputs[self.indexes])

  def _initFromDict(self,dictIn):
    """
      Initialize the LS pp from a dictionary (not from xml input).
      This is used when other objects initialize and use the LS pp for internal
      calculations
      @ In, dictIn, dict, dictionary of initialization options
    """
    if "parameters" not in dictIn.keys(): self.raiseAnError(IOError,'No Parameters specified in XML input!!!!')
    if type(dictIn["parameters"]) == list: self.parameters['targets'] = dictIn["parameters"]
    else                                 : self.parameters['targets'] = dictIn["parameters"].split(",")
    if "tolerance" in dictIn.keys(): self.subGridTol = float(dictIn["tolerance"])
    if "side" in dictIn.keys(): self.lsSide = dictIn["side"]
    if self.lsSide not in ["negative","positive","both"]: self.raiseAnError(IOError,'Computation side can be positive, negative, both only !!!!')
    if "gridVectors" in dictIn.keys():
      self.gridVectors     = dictIn["gridVectors"]
      self.gridFromOutside = True
    if "verbosity"       in dictIn.keys(): self.verbosity = utils.interpretBoolean(dictIn["verbosity"])

  def getFunctionValue(self):
    """
    Method to get a pointer to the dictionary self.functionValue
    @ In, None
    @ Out, dictionary, self.functionValue
    """
    return self.functionValue

  def getTestMatrix(self):
    """
    Method to get a pointer to the testMatrix object (evaluation grid)
    @ In, None
    @ Out, ndarray , self.testMatrix
    """
    return self.testMatrix

  def _localReadMoreXML(self,xmlNode):
    """
      Function to read the portion of the xml input that belongs to this specialized class
      and initialize some stuff based on the inputs got
      @ In, xmlNode    : Xml element node
      @ Out, None
    """
    initDict = {}
    for child in xmlNode: initDict[child.tag] = child.text.lower()
    initDict.update(xmlNode.attrib)
    self._initFromDict(initDict)

  def collectOutput(self,finishedjob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    if finishedjob.returnEvaluation() == -1: self.raiseAnError(RuntimeError,'No available Output to collect (Run probabably is not finished yet)')
    self.raiseADebug(str(finishedjob.returnEvaluation()))
    limitSurf = finishedjob.returnEvaluation()[1]
    if limitSurf[0]!=None:
      for varName in output.getParaKeys('inputs'):
        for varIndex in range(len(self.axisName)):
          if varName == self.axisName[varIndex]:
            output.removeInputValue(varName)
            for value in limitSurf[0][:,varIndex]: output.updateInputValue(varName,copy.copy(value))
      output.removeOutputValue(self.externalFunction.name)
      for value in limitSurf[1]: output.updateOutputValue(self.externalFunction.name,copy.copy(value))

  def run(self, InputIn = None, returnListSurfCoord = False): # inObj,workingDir=None):
    """
     This method executes the postprocessor action. In this case it computes the limit surface.
     @ In ,InputIn, dictionary, dictionary of data to process
     @ In ,returnListSurfCoord, boolean, True if listSurfaceCoordinate needs to be returned
     @ Out, dictionary, Dictionary containing the limitsurface
    """
    self.testMatrix.shape     = (self.testGridLength)                            #rearrange the grid matrix such as is an array of values
    self.gridCoord.shape      = (self.testGridLength,self.nVar)                  #rearrange the grid coordinate matrix such as is an array of coordinate values
    tempDict ={}
    for  varId, varName in enumerate(self.axisName): tempDict[varName] = self.gridCoord[:,varId]
    self.testMatrix[:]        = self.ROM.evaluate(tempDict)                      #get the prediction on the testing grid
    self.testMatrix.shape     = self.gridShape                                   #bring back the grid structure
    self.gridCoord.shape      = self.gridCoorShape                               #bring back the grid structure
    self.raiseADebug('LimitSurface: Prediction performed')
    #here next the points that are close to any change are detected by a gradient (it is a pre-screener)
    toBeTested = np.squeeze(np.dstack(np.nonzero(np.sum(np.abs(np.gradient(self.testMatrix)),axis=0))))
    #printing----------------------
    self.raiseADebug('LimitSurface:  Limit surface candidate points')
    for coordinate in np.rollaxis(toBeTested,0):
      myStr = ''
      for iVar, varnName in enumerate(self.axisName): myStr +=  varnName+': '+str(coordinate[iVar])+'      '
      self.raiseADebug('LimitSurface: ' + myStr+'  value: '+str(self.testMatrix[tuple(coordinate)]))
    #printing----------------------
    #check which one of the preselected points is really on the limit surface
    nNegPoints = 0
    nPosPoints = 0
    listsurfPointNegative = []
    listsurfPointPositive = []
    if self.lsSide in ["negative","both"]:
      #it returns the list of points belonging to the limit state surface and resulting in a negative response by the ROM
      listsurfPointNegative=self.__localLimitStateSearch__(toBeTested,-1)
      nNegPoints = len(listsurfPointNegative)
    if self.lsSide in ["positive","both"]:
      #it returns the list of points belonging to the limit state surface and resulting in a positive response by the ROM
      listsurfPointPositive= self.__localLimitStateSearch__(toBeTested,1)
      nPosPoints = len(listsurfPointPositive)
    listsurfPoint = listsurfPointNegative + listsurfPointPositive
#     #printing----------------------
    if len(listsurfPoint) > 0: self.raiseADebug('LimitSurface: Limit surface points:')
    for coordinate in listsurfPoint:
      myStr = ''
      for iVar, varnName in enumerate(self.axisName): myStr +=  varnName+': '+str(coordinate[iVar])+'      '
      self.raiseADebug('LimitSurface: ' + myStr+'  value: '+str(self.testMatrix[tuple(coordinate)]))
    #printing----------------------

    #if the number of point on the limit surface is > than zero than save it
    evaluations = None
    if len(listsurfPoint)>0:
      self.surfPoint = np.ndarray((len(listsurfPoint),self.nVar))
      for pointID, coordinate in enumerate(listsurfPoint):
        self.surfPoint[pointID,:] = self.gridCoord[tuple(coordinate)]
      evaluations = np.concatenate((-np.ones(nNegPoints),np.ones(nPosPoints)), axis=0)
    if returnListSurfCoord: return self.surfPoint,evaluations,listsurfPoint
    else                  : return self.surfPoint,evaluations


  def __localLimitStateSearch__(self,toBeTested,sign):
    """
    It returns the list of points belonging to the limit state surface and resulting in
    positive or negative responses by the ROM, depending on whether ''sign''
    equals either -1 or 1, respectively.
    """
    listsurfPoint=[]
    myIdList= np.zeros(self.nVar)
    for coordinate in np.rollaxis(toBeTested,0):
      myIdList[:]=coordinate
      if self.testMatrix[tuple(coordinate)]*sign>0:
        for iVar in range(self.nVar):
          if coordinate[iVar]+1<self.gridShape[iVar]:
            myIdList[iVar]+=1
            if self.testMatrix[tuple(myIdList)]*sign<=0:
              listsurfPoint.append(copy.copy(coordinate))
              break
            myIdList[iVar]-=1
            if coordinate[iVar]>0:
              myIdList[iVar]-=1
              if self.testMatrix[tuple(myIdList)]*sign<=0:
                listsurfPoint.append(copy.copy(coordinate))
                break
              myIdList[iVar]+=1
    return listsurfPoint
#
#
#

class ExternalPostProcessor(BasePostProcessor):
  """
    ExternalPostProcessor class. It will apply an arbitrary python function to
    a dataset and append each specified function's output to the output data
    object, thus the function should produce a scalar value per row of data. I
    have no idea what happens if the function produces multiple outputs.
  """
  def __init__(self,messageHandler):
    """
     Constructor
     @ In, messageHandler, message handler object
    """
    BasePostProcessor.__init__(self,messageHandler)
    self.methodsToRun = []              # A list of strings specifying what
                                        # methods the user wants to compute from
                                        # the external interfaces

    self.externalInterfaces = []        # A list of Function objects that
                                        # hopefully contain definitions for all
                                        # of the methods the user wants

    self.printTag = 'POSTPROCESSOR EXTERNAL FUNCTION'
    self.requiredAssObject = (True,(['Function'],['n']))

  def inputToInternal(self,currentInp):
    """
      Function to convert the received input into a format this object can
      understand
      @ In, currentInp: Some form of data object or list of data objects handed
                        to the post-processor
      @ Out, An input dictionary this object can process
    """

    if type(currentInp) == dict:
      if 'targets' in currentInp.keys(): return
    currentInput = currentInp
    if type(currentInput) != list: currentInput = [currentInput]
    inputDict = {'targets':{},'metadata':{}}
    metadata = []
    for item in currentInput:
      inType = None
      if hasattr(item,'type')  : inType = item.type
      elif type(item) in [list]: inType = "list"
      if inType not in ['FileObject','HDF5','TimePointSet','list']: self.raiseAWarning(self,'Input type ' + type(item).__name__ + ' not' + ' recognized. I am going to skip it.')
      elif inType == 'FileObject':
        if currentInput.subtype == 'csv': self.raiseAWarning(self,'Input type ' + inType + ' not yet ' + 'implemented. I am going to skip it.')
      elif inType == 'HDF5':
        # TODO
          self.raiseAWarning(self,'Input type ' + inType + ' not yet '+ 'implemented. I am going to skip it.')
      elif inType == 'TimePointSet':
        for param in item.getParaKeys('input') : inputDict['targets'][param] = item.getParam('input', param)
        for param in item.getParaKeys('output'): inputDict['targets'][param] = item.getParam('output', param)
        metadata.append(item.getAllMetadata())
      #Not sure if we need it, but keep a copy of every inputs metadata
      inputDict['metadata'] = metadata

    if len(inputDict['targets'].keys()) == 0: self.raiseAnError(IOError,"No input variables have been found in the input objects!")
    for interface in self.externalInterfaces:
      for _ in self.methodsToRun:
        # The function should reference self and use the same variable names
        # as the xml file
        for param in interface.parameterNames():
          if param not in inputDict['targets']:
            self.raiseAnError(IOError,self,'variable \"' + param + '\" unknown.'+' Please verify your external'+' script ('+interface.functionFile
                                          + ') variables match the data'
                                          + ' available in your dataset.')
    return inputDict

  def initialize(self, runInfo, inputs, initDict):
    """
     Method to initialize the External pp.
     @ In, runInfo, dict, dictionary of run info (e.g. working dir, etc)
     @ In, inputs, list, list of inputs
     @ In, initDict, dict, dictionary with initialization options
    """
    BasePostProcessor.initialize(self, runInfo, inputs, initDict)
    self.__workingDir = runInfo['WorkingDir']
    for key in self.assemblerDict.keys():
      if 'Function' in key:
        indice = 0
        for _ in self.assemblerDict[key]:
          self.externalInterfaces.append(self.assemblerDict[key][indice][3])
          indice += 1

  def _localReadMoreXML(self,xmlNode):
    """
      Function to grab the names of the methods this post-processor will be
      using
      @ In, xmlNode    : Xml element node
      @ Out, None
    """
    for child in xmlNode:
      if child.tag == 'method':
        methods = child.text.split(',')
        self.methodsToRun.extend(methods)

  def collectOutput(self,finishedJob,output):
    """
      Function to place all of the computed data into the output object
      @ In, finishedJob: A JobHandler object that is in charge of running this
                         post-processor
      @ In, output: The object where we want to place our computed results
      @ Out, None
    """
    if finishedJob.returnEvaluation() == -1:
      ##TODO This does not feel right
      self.raiseAnError(RuntimeError,'No available Output to collect (Run '
                                       + 'probably did not finish yet)')
    inputList = finishedJob.returnEvaluation()[0]
    outputDict = finishedJob.returnEvaluation()[1]

    if output.type == 'FileObject':
      self.raiseAWarning('Output type ' + type(output).__name__ + ' not'
                               + ' yet implemented. I am going to skip it.')
    elif output.type == 'DataObjects':
      self.raiseAWarning('Output type ' + type(output).__name__ + ' not'
                               + ' yet implemented. I am going to skip it.')
    elif output.type == 'HDF5':
      self.raiseAWarning('Output type ' + type(output).__name__ + ' not'
                               + ' yet implemented. I am going to skip it.')
    elif output.type == 'TimePointSet':
      requestedInput = output.getParaKeys('input')
      requestedOutput = output.getParaKeys('output')
      ## The user can simply ask for a computation that may exist in multiple
      ## interfaces, in that case, we will need to qualify their names for the
      ## output. The names should already be qualified from the outputDict.
      ## However, the user may have already qualified the name, so make sure and
      ## test whether the unqualified name exists in the requestedOutput before
      ## replacing it.
      for key,replacements in outputDict['qualifiedNames'].iteritems():
        if key in requestedOutput:
          requestedOutput.remove(key)
          requestedOutput.extend(replacements)

      ## Grab all data from the outputDict and anything else requested not
      ## present in the outputDict will be copied from the input data.
      ## TODO: User may want to specify which dataset the parameter comes from.
      ##       For now, we assume that if we find more than one an error will
      ##      occur.
      ## FIXME: There is an issue that the data size should be determined before
      ##        entering this loop, otherwise if say a scalar is first added,
      ##        then dataLength will be 1 and everything longer will be placed
      ##        in the Metadata.
      ##        How do we know what size the output data should be?
      dataLength = None
      for key in requestedInput+requestedOutput:
        storeInOutput = True
        value = []
        if key in outputDict:
          value = outputDict[key]
        else:
          foundCount = 0
          if key in requestedInput:
            for inputData in inputList:
              if key in inputData.getParametersValues('input').keys():
                value = inputData.getParametersValues('input')[key]
                foundCount += 1
          else:
            for inputData in inputList:
                if key in inputData.getParametersValues('output').keys():
                  value = inputData.getParametersValues('output')[key]
                  foundCount += 1

          if foundCount == 0:
            self.raiseAnError(IOError,key + ' not found in the input '
                                            + 'object or the computed output '
                                            + 'object.')
          elif foundCount > 1:
            self.raiseAnError(IOError,key + ' is ambiguous since it occurs'
                                            + ' in multiple input objects.')

        ## We need the size to ensure the data size is consistent, but there
        ## is no guarantee the data is not scalar, so this check is necessary
        myLength = 1
        if not hasattr(value, "__iter__"):
          value = [value]
        myLength = len(value)

        if dataLength is None:
          dataLength = myLength
        elif dataLength != myLength:
          self.raiseAWarning('Requested output for ' + key + ' has a'
                                    + ' non-conformant data size ('
                                    + str(dataLength) + ' vs ' + str(myLength)
                                    + '), it is being placed in the metadata.')
          storeInOutput = False

        ## Finally, no matter what, place the requested data somewhere
        ## accessible
        if storeInOutput:
          if key in requestedInput:
            for val in value:
              output.updateInputValue(key, val)
          else:
            for val in value:
              output.updateOutputValue(key, val)
        else:
          if not hasattr(value, "__iter__"):
            value = [value]
          for val in value:
            output.updateMetadata(key, val)

    else: self.raiseAnError(IOError,'Unknown output type: ' + str(output.type))

  def run(self, InputIn):
    """
     This method executes the postprocessor action. In this case it performs the action defined int
     the external pp
     @ In , InputIn, dictionary, dictionary of data to process
     @ Out, dictionary, Dictionary containing the post-processed results
    """
    Input  = self.inputToInternal(InputIn)
    outputDict = {'qualifiedNames' : {}}
    ## This will map the name to its appropriate interface and method
    ## in the case of a function being defined in two separate files, we
    ## qualify the output by appending the name of the interface from which it
    ## originates
    methodMap = {}

    ## First check all the requested methods are available and if there are
    ## duplicates then qualify their names for the user
    for method in self.methodsToRun:
      matchingInterfaces = []
      for interface in self.externalInterfaces:
        if method in interface.availableMethods():
          matchingInterfaces.append(interface)


      if len(matchingInterfaces) == 0:
        self.raiseAWarning(method + ' not found. I will skip it.')
      elif len(matchingInterfaces) == 1:
        methodMap[method] = (matchingInterfaces[0],method)
      else:
        outputDict['qualifiedNames'][method] = []
        for interface in matchingInterfaces:
          methodName = interface.name + '.' + method
          methodMap[methodName] = (interface,method)
          outputDict['qualifiedNames'][method].append(methodName)

    ## Evaluate the method and add it to the outputDict, also if the method
    ## adjusts the input data, then you should update it as well.
    for methodName,(interface,method) in methodMap.iteritems():
      outputDict[methodName] = interface.evaluate(method,Input['targets'])
      for target in Input['targets']:
        if hasattr(interface,target):
          outputDict[target] = getattr(interface, target)
    return outputDict

"""
 Interface Dictionary (factory) (private)
"""
__base                                       = 'PostProcessor'
__interFaceDict                              = {}
__interFaceDict['SafestPoint'              ] = SafestPoint
__interFaceDict['LimitSurfaceIntegral'     ] = LimitSurfaceIntegral
__interFaceDict['PrintCSV'                 ] = PrintCSV
__interFaceDict['BasicStatistics'          ] = BasicStatistics
__interFaceDict['LoadCsvIntoInternalObject'] = LoadCsvIntoInternalObject
__interFaceDict['LimitSurface'             ] = LimitSurface
__interFaceDict['ComparisonStatistics'     ] = ComparisonStatistics
__interFaceDict['External'                 ] = ExternalPostProcessor
__knownTypes                                 = __interFaceDict.keys()

def knownTypes():
  return __knownTypes

def returnInstance(Type,caller):
  """
    function used to generate a Filter class
    @ In, Type : Filter type
    @ Out,Instance of the Specialized Filter class
  """
  try: return __interFaceDict[Type](caller.messageHandler)
  except KeyError: caller.raiseAnError(NameError,'not known '+__base+' type '+Type)
