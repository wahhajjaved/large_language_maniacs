"""
Module where the base class and the specialization of different type of sampler are
"""
#for future compatibility with Python 3--------------------------------------------------------------
from __future__ import division, print_function, unicode_literals, absolute_import
import warnings
warnings.simplefilter('default',DeprecationWarning)
#if not 'xrange' in dir(__builtins__): xrange = range
#End compatibility block for Python 3----------------------------------------------------------------

#External Modules------------------------------------------------------------------------------------
import sys
import os
import copy
import abc
import numpy as np
import json
from operator import mul,itemgetter
from collections import OrderedDict
from functools import reduce
from scipy import spatial
from scipy.interpolate import InterpolatedUnivariateSpline
import xml.etree.ElementTree as ET
import itertools
from math import ceil
from collections import OrderedDict
from sklearn import neighbors
from sklearn.utils.extmath import cartesian

if sys.version_info.major > 2: import pickle
else: import cPickle as pickle
#External Modules End--------------------------------------------------------------------------------

#Internal Modules------------------------------------------------------------------------------------
import utils
from BaseClasses import BaseType
from Assembler import Assembler
import Distributions
import DataObjects
import TreeStructure as ETS
import SupervisedLearning
import pyDOE as doe
import Quadratures
import OrthoPolynomials
import IndexSets
import Models
import PostProcessors
import MessageHandler
import GridEntities
from AMSC_Object import AMSC_Object
distribution1D = utils.find_distribution1D()
#Internal Modules End--------------------------------------------------------------------------------

class Sampler(utils.metaclass_insert(abc.ABCMeta,BaseType),Assembler):
  """
    This is the base class for samplers
    Samplers own the sampling strategy (Type) and they generate the
    input values using the associate distribution. They do not have distributions inside!!!!

    --Instance--
    myInstance = Sampler()
    myInstance.XMLread(xml.etree.ElementTree.Element)  This method generates all the information that will be permanent for the object during the simulation

    --usage--
    myInstance = Sampler()
    myInstance.XMLread(xml.etree.ElementTree.Element)  This method generate all permanent information of the object from <Simulation>
    myInstance.whatDoINeed()                           -see Assembler class-
    myInstance.generateDistributions(dict)             Here the seed for the random engine is started and the distributions are supplied to the sampler and
                                                       initialized. The method is called come from <Simulation> since it is the only one possess all the distributions.
    myInstance.initialize()                            This method is called from the <Step> before the Step process start. In the base class it reset the counter to 0
    myInstance.amIreadyToProvideAnInput                Requested from <Step> used to verify that the sampler is available to generate a new input
    myInstance.generateInput(self,model,oldInput)      Requested from <Step> to generate a new input. Generate the new values and request to model to modify according the input and returning it back

    --Other inherited methods--
    myInstance.whoAreYou()                            -see BaseType class-
    myInstance.myInitializzationParams()              -see BaseType class-
    myInstance.myCurrentSetting()                     -see BaseType class-

    --Adding a new Sampler subclass--
    <MyClass> should inherit at least from Sampler or from another step already presents

    DO NOT OVERRIDE any of the class method that are not starting with self.local*

    ADD your class to the dictionary __InterfaceDict at the end of the module

    The following method overriding is MANDATORY:
    self.localGenerateInput(model,oldInput)  : this is where the step happens, after this call the output is ready

    the following methods could be overrode:
    self.localInputAndChecks(xmlNode)
    self.localAddInitParams(tempDict)
    self.localAddCurrentSetting(tempDict)
    self.localInitialize()
    self.localStillReady(ready)
    self.localFinalizeActualSampling(jobObject,model,myInput)
  """

  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    BaseType.__init__(self)
    self.counter                       = 0                         # Counter of the samples performed (better the input generated!!!). It is reset by calling the function self.initialize
    self.auxcnt                        = 0                         # Aux counter of samples performed (for its usage check initialize method)
    self.limit                         = sys.maxsize               # maximum number of Samples (for example, Monte Carlo = Number of HistorySet to run, DET = Unlimited)
    self.toBeSampled                   = {}                        # Sampling mapping dictionary {'Variable Name':'name of the distribution'}
    self.dependentSample               = {}                        # Sampling mapping dictionary for dependent variables {'Variable Name':'name of the external function'}
    self.distDict                      = {}                        # Contains the instance of the distribution to be used, it is created every time the sampler is initialized. keys are the variable names
    self.funcDict                      = {}                        # Contains the instance of the function     to be used, it is created every time the sampler is initialized. keys are the variable names
    self.values                        = {}                        # for each variable the current value {'var name':value}
    self.inputInfo                     = {}                        # depending on the sampler several different type of keywarded information could be present only one is mandatory, see below
    self.initSeed                      = None                      # if not provided the seed is randomly generated at the istanciation of the sampler, the step can override the seed by sending in another seed
    self.inputInfo['SampledVars'     ] = self.values               # this is the location where to get the values of the sampled variables
    self.inputInfo['SampledVarsPb'   ] = {}                        # this is the location where to get the probability of the sampled variables
    self.inputInfo['PointProbability'] = None                      # this is the location where the point wise probability is stored (probability associated to a sampled point)
    self.inputInfo['crowDist']         = {}                        # Stores a dictionary that contains the information to create a crow distribution.  Stored as a json object
    self.reseedAtEachIteration         = False                     # Logical flag. True if every newer evaluation is performed after a new reseeding
    self.FIXME                         = False                     # FIXME flag
    self.printTag                      = self.type                 # prefix for all prints (sampler type)
    self.restartData                   = None                      # presampled points to restart from

    self._endJobRunnable               = sys.maxsize               # max number of inputs creatable by the sampler right after a job ends (e.g., infinite for MC, 1 for Adaptive, etc)

    ######
    self.variables2distributionsMapping = {}                       # for each variable 'varName'  , the following informations are included:  'varName': {'dim': 1, 'reducedDim': 1,'totDim': 2, 'name': 'distName'} ; dim = dimension of the variable; reducedDim = dimension of the variable in the transformed space; totDim = total dimensionality of its associated distribution
    self.distributions2variablesMapping = {}                       # for each variable 'distName' , the following informations are included: 'distName': [{'var1': 1}, {'var2': 2}]} where for each var it is indicated the var dimension
    self.NDSamplingParams               = {}                       # this dictionary contains a dictionary for each ND distribution (key). This latter dictionary contains the initialization parameters of the ND inverseCDF ('initialGridDisc' and 'tolerance')
    ######

    self.assemblerObjects               = {}                       # {MainClassName(e.g.Distributions):[class(e.g.Models),type(e.g.ROM),objectName]}
    #self.requiredAssObject             = (False,([],[]))          # tuple. first entry boolean flag. True if the XML parser must look for objects;
                                                                   # second entry tuple.first entry list of object can be retrieved, second entry multiplicity (-1,-2,-n means optional (max 1 object,2 object, no number limit))
    self.requiredAssObject              = (True,(['Restart','function'],['-n','-n']))
    self.assemblerDict                  = {}                       # {'class':[['subtype','name',instance]]}

    #used for pca analysis
    self.variablesTransformationDict    = {}                       # for each variable 'modelName', the following informations are included: {'modelName': {latentVariables:[latentVar1, latentVar2, ...], manifestVariables:[manifestVar1,manifestVar2,...]}}
    self.transformationMethod           = {}                       # transformation method used in variablesTransformation node {'modelName':method}
    self.entitiesToRemove               = []                       # This variable is used in order to make sure the transformation info is printed once in the output xml file.

  def _localGenerateAssembler(self,initDict):
    """ see generateAssembler method """
    availableDist = initDict['Distributions']
    availableFunc = initDict['Functions']
    self._generateDistributions(availableDist,availableFunc)

  def _addAssObject(self,name,flag):
    """
      Method to add required assembler objects to the requiredAssObject dictionary.
      @ In, name, the node name to search for
      @ In, flag, the number of nodes to look for (- means optional, n means any number)
      @ Out, None
    """
    self.requiredAssObject[1][0].append(name)
    self.requiredAssObject[1][1].append(flag)

  def _localWhatDoINeed(self):
    """
    This method is a local mirror of the general whatDoINeed method.
    It is implemented by the samplers that need to request special objects
    @ In , None, None
    @ Out, needDict, list of objects needed
    """
    needDict = {}
    needDict['Distributions'] = [] # Every sampler requires Distributions OR a Function
    needDict['Functions']     = [] # Every sampler requires Distributions OR a Function
    for dist in self.toBeSampled.values():     needDict['Distributions'].append((None,dist))
    for func in self.dependentSample.values(): needDict['Functions'].append((None,func))
    return needDict

  def _readMoreXML(self,xmlNode):
    """
    Function to read the portion of the xml input that belongs to this specialized class
    and initialize some stuff based on the inputs got
    @ In, xmlNode    : Xml element node
    @ Out, None
    The text is supposed to contain the info where and which variable to change.
    In case of a code the syntax is specified by the code interface itself
    """

    Assembler._readMoreXML(self,xmlNode)
    self._readMoreXMLbase(xmlNode)
    self.localInputAndChecks(xmlNode)

  def _readMoreXMLbase(self,xmlNode):
    """
    Function to read the portion of the xml input that belongs to the base sampler only
    and initialize some stuff based on the inputs got
    @ In, xmlNode    : Xml element node
    @ Out, None
    The text is supposed to contain the info where and which variable to change.
    In case of a code the syntax is specified by the code interface itself
    """

    for child in xmlNode:
      prefix = ""
      if child.tag == 'Distribution':
        for childChild in child:
          if childChild.tag =='distribution':
            prefix = "<distribution>"
            tobesampled = childChild.text
        self.toBeSampled[prefix+child.attrib['name']] = tobesampled
      elif child.tag == 'variable':
        foundDistOrFunc = False
        for childChild in child:
          if childChild.tag =='distribution':
            if not foundDistOrFunc: foundDistOrFunc = True
            else: self.raiseAnError(IOError,'A sampled variable cannot have both a distribution and a function!')
            tobesampled = childChild.text
            varData={}
            varData['name']=childChild.text
            if childChild.get('dim') == None:
              dim=1
            else:
              dim=childChild.attrib['dim']
            varData['dim']=int(dim)
            self.variables2distributionsMapping[child.attrib['name']] = varData
            self.toBeSampled[prefix+child.attrib['name']] = tobesampled
          elif childChild.tag == 'function':
            if not foundDistOrFunc: foundDistOrFunc = True
            else: self.raiseAnError(IOError,'A sampled variable cannot have both a distribution and a function!')
            tobesampled = childChild.text
            self.dependentSample[prefix+child.attrib['name']] = tobesampled
        if not foundDistOrFunc: self.raiseAnError(IOError,'Sampled variable',child.attrib['name'],'has neither a <distribution> nor <function> node specified!')
      elif child.tag == "samplerInit":
        self.initSeed = Distributions.randomIntegers(0,2**31,self)
        for childChild in child:
          if childChild.tag == "limit":
            self.limit = childChild.text
          elif childChild.tag == "initialSeed":
            self.initSeed = int(childChild.text)
          elif childChild.tag == "reseedEachIteration":
            if childChild.text.lower() in utils.stringsThatMeanTrue(): self.reseedAtEachIteration = True
          elif childChild.tag == "distInit":
            for childChildChild in childChild:
              NDdistData = {}
              for childChildChildChild in childChildChild:
                if childChildChildChild.tag == 'initialGridDisc':
                  NDdistData[childChildChildChild.tag] = int(childChildChildChild.text)
                elif childChildChildChild.tag == 'tolerance':
                  NDdistData[childChildChildChild.tag] = float(childChildChildChild.text)
                else:
                  self.raiseAnError(IOError,'Unknown tag '+childChildChildChild.tag+' .Available are: initialGridDisc and tolerance!')
              self.NDSamplingParams[childChildChild.attrib['name']] = NDdistData
          else: self.raiseAnError(IOError,'Unknown tag '+childChild.tag+' .Available are: limit, initialSeed, reseedEachIteration and distInit!')
      elif child.tag == "variablesTransformation":
        transformationDict = {}
        listIndex = None
        for childChild in child:
          if childChild.tag == "latentVariables":
            transformationDict[childChild.tag] = list(inp.strip() for inp in childChild.text.strip().split(','))
          elif childChild.tag == "manifestVariables":
            transformationDict[childChild.tag] = list(inp.strip() for inp in childChild.text.strip().split(','))
          elif childChild.tag == "manifestVariablesIndex":
            # the index provided by the input file starts from 1, but the index used by the code starts from 0.
            listIndex = list(int(inp.strip()) - 1  for inp in childChild.text.strip().split(','))
          elif childChild.tag == "method":
            self.transformationMethod[child.attrib['distribution']] = childChild.text
        if listIndex == None:
          self.raiseAWarning('Index is not provided for manifestVariables, default index will be used instead!')
          listIndex = range(len(transformationDict["manifestVariables"]))
        transformationDict["manifestVariablesIndex"] = listIndex
        self.variablesTransformationDict[child.attrib['distribution']] = transformationDict

    if self.initSeed == None:
      self.initSeed = Distributions.randomIntegers(0,2**31,self)

    # Creation of the self.distributions2variablesMapping dictionary: {'distName': ({'variable_name1': dim1}, {'variable_name2': dim2})}
    for variable in self.variables2distributionsMapping.keys():
      distName = self.variables2distributionsMapping[variable]['name']
      dim      = self.variables2distributionsMapping[variable]['dim']
      listElement={}
      listElement[variable] = dim
      if (distName in self.distributions2variablesMapping.keys()):
        self.distributions2variablesMapping[distName].append(listElement)
      else:
        self.distributions2variablesMapping[distName]=[listElement]

    # creation of the self.distributions2variablesIndexList dictionary:{'distName':[dim1,dim2,...,dimN]}
    self.distributions2variablesIndexList = {}
    for distName in self.distributions2variablesMapping.keys():
      positionList = []
      for var in self.distributions2variablesMapping[distName]:
        position = utils.first(var.values())
        positionList.append(position)
      positionList.sort()
      self.distributions2variablesIndexList[distName] = positionList

    for key in self.variables2distributionsMapping.keys():
      distName = self.variables2distributionsMapping[key]['name']
      dim      = self.variables2distributionsMapping[key]['dim']
      reducedDim = self.distributions2variablesIndexList[distName].index(dim) + 1
      self.variables2distributionsMapping[key]['reducedDim'] = reducedDim  # the dimension of variable in the transformed space
      self.variables2distributionsMapping[key]['totDim'] = max(self.distributions2variablesIndexList[distName]) # We will reset the value if the node <variablesTransformation> exist in the raven input file
      if not self.variablesTransformationDict:
        if self.variables2distributionsMapping[key]['totDim'] != len(self.distributions2variablesIndexList[distName]):
          self.raiseAnError(IOError,'The "dim" assigned to the variables insider Sampler are not correct! the "dim" should start from 1, and end with the full dimension of given distribution')

    #Checking the variables transformation
    if self.variablesTransformationDict:
      for dist,varsDict in self.variablesTransformationDict.items():
        maxDim = len(varsDict['manifestVariables'])
        listLatentElement = varsDict['latentVariables']
        if len(set(listLatentElement)) != len(listLatentElement):
          self.raiseAnError(IOError,'There are replicated variables listed in the latentVariables!')
        if len(set(varsDict['manifestVariables'])) != len(varsDict['manifestVariables']):
          self.raiseAnError(IOError,'There are replicated variables listed in the manifestVariables!')
        if len(set(varsDict['manifestVariablesIndex'])) != len(varsDict['manifestVariablesIndex']):
          self.raiseAnError(IOError,'There are replicated variables indices listed in the manifestVariablesIndex!')
        listElement = self.distributions2variablesMapping[dist]
        for var in listElement:
          self.variables2distributionsMapping[var.keys()[0]]['totDim'] = maxDim #reset the totDim to reflect the totDim of original input space
        tempListElement = {k.strip():v for x in listElement for ks,v in x.items() for k in list(ks.strip().split(','))}
        listIndex = []
        for var in listLatentElement:
          if var not in set(tempListElement.keys()):
            self.raiseAnError(IOError, 'The variable listed in latentVariables is not listed in the given distribution: ' + dist)
          listIndex.append(tempListElement[var]-1)
        if max(listIndex) > maxDim: self.raiseAnError(IOError,'The maximum dim = ' + str(max(listIndex)) + ' defined for latent variables is exceeded the dimension of the problem!')
        if len(set(listIndex)) != len(listIndex):
          self.raiseAnError(IOError,'There are at least two latent variables assigned with the same dimension!')
        # update the index for latentVariables according to the 'dim' assigned for given var defined in Sampler
        self.variablesTransformationDict[dist]['latentVariablesIndex'] = listIndex

  def readSamplerInit(self,xmlNode):
    """
    This method is responsible to read only the samplerInit block in the .xml file.
    This method has been moved from the base sampler class since the samplerInit block is needed only for the MC and stratified (LHS) samplers
    @ In xmlNode
    """
    for child in xmlNode:
      if child.tag == "samplerInit":
        self.initSeed = Distributions.randomIntegers(0,2**31,self)
        for childChild in child:
          if childChild.tag == "limit":
            self.limit = childChild.text
          elif childChild.tag == "initialSeed":
            self.initSeed = int(childChild.text)
          elif childChild.tag == "reseedEachIteration":
            if childChild.text.lower() in utils.stringsThatMeanTrue(): self.reseedAtEachIteration = True
          elif childChild.tag == "distInit":
            for childChildChild in childChild:
              NDdistData = {}
              for childChildChildChild in childChildChild:
                if childChildChildChild.tag == 'initialGridDisc':
                  NDdistData[childChildChildChild.tag] = int(childChildChildChild.text)
                elif childChildChildChild.tag == 'tolerance':
                  NDdistData[childChildChildChild.tag] = float(childChildChildChild.text)
                else:
                  self.raiseAnError(IOError,'Unknown tag '+childChildChildChild.tag+' .Available are: initialGridDisc and tolerance!')
              self.NDSamplingParams[childChildChild.attrib['name']] = NDdistData
          else: self.raiseAnError(IOError,'Unknown tag '+child.tag+' .Available are: limit, initialSeed, reseedEachIteration and distInit!')

  def endJobRunnable(self):
    """
    Returns the maximum number of inputs allowed to be created by the sampler
    right after a job ends (e.g., infinite for MC, 1 for Adaptive, etc)
    """
    return self._endJobRunnable

  def localInputAndChecks(self,xmlNode):
    """place here the additional reading, remember to add initial parameters in the method localAddInitParams"""
    pass

  def addInitParams(self,tempDict):
    """
    This function is called from the base class to print some of the information inside the class.
    Whatever is permanent in the class and not inherited from the parent class should be mentioned here
    The information is passed back in the dictionary. No information about values that change during the simulation are allowed
    @ In/Out tempDict: {'attribute name':value}
    """
    for variable in self.toBeSampled.items():
      tempDict[variable[0]] = 'is sampled using the distribution ' +variable[1]
    tempDict['limit' ]        = self.limit
    tempDict['initial seed' ] = self.initSeed
    self.localAddInitParams(tempDict)

  def localAddInitParams(self,tempDict):
    """use this function to export to the printer in the base class the additional PERMANENT your local class have"""

  def addCurrentSetting(self,tempDict):
    """
    This function is called from the base class to print some of the information inside the class.
    Whatever is a temporary value in the class and not inherited from the parent class should be mentioned here
    The information is passed back in the dictionary
    Function adds the current settings in a temporary dictionary
    @ In, tempDict
    @ Out, tempDict
    """
    tempDict['counter'       ] = self.counter
    tempDict['initial seed'  ] = self.initSeed
    for key in self.inputInfo:
      if key!='SampledVars': tempDict[key] = self.inputInfo[key]
      else:
        for var in self.inputInfo['SampledVars'].keys(): tempDict['Variable: '+var+' has value'] = tempDict[key][var]
    self.localAddCurrentSetting(tempDict)

  def localAddCurrentSetting(self,tempDict):
    """use this function to export to the printer in the base class the additional PERMANENT your local class have"""
    pass

  def _generateDistributions(self,availableDist,availableFunc):
    """
      Generates the distrbutions and functions.
      @ In, availDist, dict of distributions
      @ In, availDist, dict of functions
      @ Out, None
    """
    if self.initSeed != None:
      Distributions.randomSeed(self.initSeed)
    for key in self.toBeSampled.keys():
      if self.toBeSampled[key] not in availableDist.keys(): self.raiseAnError(IOError,'Distribution '+self.toBeSampled[key]+' not found among available distributions (check input)!')
      self.distDict[key] = availableDist[self.toBeSampled[key]]
      self.inputInfo['crowDist'][key] = json.dumps(self.distDict[key].getCrowDistDict())
    for key,val in self.dependentSample.items():
      if val not in availableFunc.keys(): self.raiseAnError('Function',val,'was not found among the available functions:',availableFunc.keys())
      self.funcDict[key] = availableFunc[val]

  def initialize(self,externalSeeding=None,solutionExport=None):
    """
    This function should be called every time a clean sampler is needed. Called before takeAstep in <Step>
    @in solutionExport: in goal oriented sampling (a.k.a. adaptive sampling this is where the space/point satisfying the constrains)
    """
    self.counter = 0
    if   not externalSeeding          :
      Distributions.randomSeed(self.initSeed)       #use the sampler initialization seed
      self.auxcnt = self.initSeed
    elif externalSeeding=='continue'  : pass        #in this case the random sequence needs to be preserved
    else                              :
      Distributions.randomSeed(externalSeeding)     #the external seeding is used
      self.auxcnt = externalSeeding

    #grab restart dataobject if it's available, then in localInitialize the sampler can deal with it.
    if 'Restart' in self.assemblerDict.keys():
      self.raiseADebug('Restart object: '+str(self.assemblerDict['Restart']))
      self.restartData = self.assemblerDict['Restart'][0][3]
      self.raiseAMessage('Restarting from '+self.restartData.name)
      #check consistency of data
      try:
        rdata = self.restartData.getAllMetadata()['crowDist']
        sdata = self.inputInfo['crowDist']
        self.raiseAMessage('sampler inputs:')
        for sk,sv in sdata.items():
          self.raiseAMessage('|   '+str(sk)+': '+str(sv))
        for i,r in enumerate(rdata):
          if type(r) != dict: continue
          if not r==sdata:
            self.raiseAMessage('restart inputs %i:' %i)
            for rk,rv in r.items():
              self.raiseAMessage('|   '+str(rk)+': '+str(rv))
            self.raiseAnError(IOError,'Restart "%s" data[%i] does not have same inputs as sampler!' %(self.restartData.name,i))
      except KeyError as e:
        self.raiseAWarning("No CROW distribution available in restart -",e)
    else:
      self.raiseAMessage('No restart for '+self.printTag)

    #specializing the self.localInitialize() to account for adaptive sampling
    if solutionExport != None : self.localInitialize(solutionExport=solutionExport)
    else                      : self.localInitialize()

    for distrib in self.NDSamplingParams:
      if distrib in self.distributions2variablesMapping:
        params = self.NDSamplingParams[distrib]
        temp = utils.first(self.distributions2variablesMapping[distrib][0].keys())
        self.distDict[temp].updateRNGParam(params)
      else:
        self.raiseAnError(IOError,'Distribution "%s" specified in distInit block of sampler "%s" does not exist!' %(distrib,self.name))

    # Store the transformation matrix in the metadata
    if self.variablesTransformationDict:
      self.entitiesToRemove = []
      for variable in self.variables2distributionsMapping.keys():
        distName = self.variables2distributionsMapping[variable]['name']
        dim      = self.variables2distributionsMapping[variable]['dim']
        totDim   = self.variables2distributionsMapping[variable]['totDim']
        if totDim > 1 and dim  == 1:
          transformDict = {}
          transformDict['type'] = self.distDict[variable.strip()].type
          transformDict['transformationMatrix'] = self.distDict[variable.strip()].transformationMatrix()
          self.inputInfo['transformation-'+distName] = transformDict
          self.entitiesToRemove.append('transformation-'+distName)

  def localInitialize(self):
    """
    use this function to add initialization features to the derived class
    it is call at the beginning of each step
    """
    pass

  def amIreadyToProvideAnInput(self): #inLastOutput=None):
    """
    This is a method that should be call from any user of the sampler before requiring the generation of a new sample.
    This method act as a "traffic light" for generating a new input.
    Reason for not being ready could be for example: exceeding number of samples, waiting for other simulation for providing more information etc. etc.
    @ In, None, None
    @ Out, ready, Boolean
    """
    if(self.counter < self.limit): ready = True
    else                         : ready = False
    ready = self.localStillReady(ready)
    return ready

  def localStillReady(self,ready): #,lastOutput=None
    """Use this function to change the ready status"""
    return ready

  def generateInput(self,model,oldInput):
    """
      This method has to be overwritten to provide the specialization for the specific sampler
      The model instance in might be needed since, especially for external codes,
      only the code interface possesses the dictionary for reading the variable definition syntax
      @ In, model, model instance, it is the instance of a RAVEN model
      @ In, oldInput, list, a list of the original needed inputs for the model (e.g. list of files, etc. etc)
      @ Out, model.createNewInput(...), list, list containing the new inputs -in reality it is the model that return this the Sampler generate the value to be placed in the input the model
    """
    self.counter +=1                              #since we are creating the input for the next run we increase the counter and global counter
    self.auxcnt  +=1
    #FIXME, the following condition check is make sure that the require info is only printed once when dump metadata to xml, this should be removed in the future when we have a better way to dump the metadata
    if self.counter >1:
      for key in self.entitiesToRemove:
        self.inputInfo.pop(key,None)
    if self.reseedAtEachIteration: Distributions.randomSeed(self.auxcnt-1)
    self.inputInfo['prefix'] = str(self.counter)
    model.getAdditionalInputEdits(self.inputInfo)
    self.localGenerateInput(model,oldInput)
    # add latent variables and original variables to self.inputInfo
    if self.variablesTransformationDict:
      for dist,var in self.variablesTransformationDict.items():
        if self.transformationMethod[dist] == 'pca':
          self.pcaTransform(var,dist)
        else:
          self.raiseAnError(NotImplementedError,'transformation method is not yet implemented for ' + self.transformationMethod[dist] + ' method')
    # generate the function variable values
    for var in self.dependentSample.keys():
      test=self.funcDict[var].evaluate(var,self.values)
      self.values[var] = test
    return model.createNewInput(oldInput,self.type,**self.inputInfo)

  def pcaTransform(self,varsDict,dist):
    """
      This method is used to map latent variables with respect to the model input variables
      both the latent variables and the model input variables will be stored in the dict: self.inputInfo['SampledVars']
      @ In, varsDict, dict, dictionary contains latent and manifest variables {'latentVariables':[latentVar1,latentVar2,...], 'manifestVariables':[var1,var2,...]}
      @ In, dist, string, the distribution name associated with given variable set
    """
    latentVariablesValues = []
    listIndex = []
    manifestVariablesValues = [None] * len(varsDict['manifestVariables'])
    for index,lvar in enumerate(varsDict['latentVariables']):
      for var,value in self.values.items():
        if lvar == var:
          latentVariablesValues.append(value)
          listIndex.append(varsDict['latentVariablesIndex'][index])
    varName = utils.first(utils.first(self.distributions2variablesMapping[dist]).keys())
    varsValues = self.distDict[varName].pcaInverseTransform(latentVariablesValues,listIndex)
    for index1,index2 in enumerate(varsDict['manifestVariablesIndex']):
      manifestVariablesValues[index2] = varsValues[index1]
    manifestVariablesDict = dict(zip(varsDict['manifestVariables'],manifestVariablesValues))
    self.values.update(manifestVariablesDict)

  @abc.abstractmethod
  def localGenerateInput(self,model,oldInput):
    """
    This class need to be overwritten since it is here that the magic of the sampler happens.
    After this method call the self.inputInfo should be ready to be sent to the model
    @in model   : it is the instance of a model
    @in oldInput: [] a list of the original needed inputs for the model (e.g. list of files, etc. etc)
    """
    pass

  def generateInputBatch(self,myInput,model,batchSize,projector=None): #,lastOutput=None
    """
    this function provide a mask to create several inputs at the same time
    It call the generateInput function as many time as needed
    @in myInput: [] list containing one input set
    @in model: instance of a model
    @in batchSize: integer the number of input sets required
    @in projector used for adaptive sampling to provide the projection of the solution on the success metric
    @return newInputs: [[]] list of the list of input sets"""
    newInputs = []
    #inlastO = None
    #if lastOutput:
    #  if not lastOutput.isItEmpty(): inlastO = lastOutput
    #while self.amIreadyToProvideAnInput(inlastO) and (self.counter < batchSize):
    while self.amIreadyToProvideAnInput() and (self.counter < batchSize):
      if projector==None: newInputs.append(self.generateInput(model,myInput))
      else              : newInputs.append(self.generateInput(model,myInput,projector))
    return newInputs

  def finalizeActualSampling(self,jobObject,model,myInput):
    """
    This function is used by samplers that need to collect information from a
    finished run.
    Provides a generic interface that all samplers will use, for specifically
    handling any sub-class, the localFinalizeActualSampling should be overridden
    instead, as finalizeActualSampling provides only generic functionality
    shared by all Samplers and will in turn call the localFinalizeActualSampling
    before returning.
    @in jobObject: an instance of a JobHandler
    @in model    : an instance of a model
    @in myInput  : the generating input
    """
    self.localFinalizeActualSampling(jobObject,model,myInput)

  def localFinalizeActualSampling(self,jobObject,model,myInput):
    """
    Overwrite only if you need something special at the end of each run....
    This function is used by samplers that need to collect information from the just ended run
    For example, for a Dynamic Event Tree case, this function can be used to retrieve
    the information from the just finished run of a branch in order to retrieve, for example,
    the distribution name that caused the trigger, etc.
    It is a essentially a place-holder for most of the sampler to remain compatible with the StepsCR structure
    @in jobObject: an instance of a JobHandler
    @in model    : an instance of a model
    @in myInput  : the generating input
    """
    pass

  def handleFailedRuns(self,failedRuns):
    """Collects the failed runs from the Step and allows samples to handle them individually if need be.
    @ In, failedRuns, list of JobHandler.ExternalRunner objects
    @ Out, None
    """
    self.raiseADebug('===============')
    self.raiseADebug('| RUN SUMMARY |')
    self.raiseADebug('===============')
    if len(failedRuns)>0:
      self.raiseAWarning('There were %i failed runs!  Run with verbosity = debug for more details.' %(len(failedRuns)))
      for run in failedRuns:
        metadata = run.returnMetadata()
        self.raiseADebug('  Run number %s FAILED:' %run.identifier,run.command)
        self.raiseADebug('      return code :',run.getReturnCode())
        self.raiseADebug('      sampled vars:')
        for v,k in metadata['SampledVars'].items():
          self.raiseADebug('         ',v,':',k)
    else:
      self.raiseADebug('All runs completed without returning errors.')
    self._localHandleFailedRuns(failedRuns)
    self.raiseADebug('===============')
    self.raiseADebug('  END SUMMARY  ')
    self.raiseADebug('===============')

  def _localHandleFailedRuns(self,failedRuns):
    """Specialized method for samplers to handle failed runs.  Defaults to failing runs.
    @ In, failedRuns, list of JobHandler.ExternalRunner objects
    @ Out, None
    """
    if len(failedRuns)>0:
      self.raiseAnError(IOError,'There were failed runs; aborting RAVEN.')
#
#
#
#

class StaticSampler(Sampler):
  """This is a general static, blind, once-through sampler"""
  pass
#
#
#
#
class AdaptiveSampler(Sampler):
  """This is a general adaptive sampler"""
  pass
#
#
#
#
class LimitSurfaceSearch(AdaptiveSampler):
  """
  A sampler that will adaptively locate the limit surface of a given problem
  """
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Sampler.__init__(self)
    self.goalFunction        = None             #this is the pointer to the function defining the goal
    self.tolerance           = None             #this is norm of the error threshold
    self.subGridTol          = None             #This is the tolerance used to construct the testing sub grid
    self.toleranceWeight     = 'cdf'            #this is the a flag that controls if the convergence is checked on the hyper-volume or the probability
    self.persistence         = 5                #this is the number of times the error needs to fell below the tollerance before considering the sim converged
    self.repetition          = 0                #the actual number of time the error was below the requested threshold
    self.forceIteration      = False            #this flag control if at least a self.limit number of iteration should be done
    self.axisName            = None             #this is the ordered list of the variable names (ordering match self.gridStepSize anfd the ordering in the test matrixes)
    self.oldTestMatrix       = OrderedDict()    #This is the test matrix to use to store the old evaluation of the function
    self.persistenceMatrix   = OrderedDict()    #this is a matrix that for each point of the testing grid tracks the persistence of the limit surface position
    self.invPointPersistence = OrderedDict()    #this is a matrix that for each point of the testing grid tracks the inverse of the persistence of the limit surface position
    self.solutionExport      = None             #This is the data used to export the solution (it could also not be present)
    self.nVar                = 0                #this is the number of the variable sampled
    self.surfPoint           = None             #coordinate of the points considered on the limit surface
    self.hangingPoints       = []               #list of the points already submitted for evaluation for which the result is not yet available
    self.refinedPerformed    = False            # has the grid refinement been performed?
    self.limitSurfacePP      = None             # post-processor to compute the limit surface
    self.exceptionGrid       = None             # which cell should be not considered in the limit surface computation? set by refinement
    self.errorTolerance      = 1.0              # initial error tolerance (number of points can change between iterations in LS search)
    self.jobHandler          = None             # jobHandler for generation of grid in parallel
    self.firstSurface        = True             # if first LS do not consider the invPointPersistence information (if true)
    self.scoringMethod  = 'distancePersistence' # The scoring method to use
    self.batchStrategy  = 'none'                # The batch strategy to use
    # self.generateCSVs   = False                 # Flag: should intermediate
    #                                             #  results be stored?
    self.toProcess      = []                    # List of the top batchSize
                                                #  candidates that will be
                                                #  populated and depopulated
                                                #  during subsequent calls of
                                                #  localGenerateInput
    self.maxBatchSize   = None                  # Maximum batch size, the top
                                                #  candidates will be selected,
                                                #  if there are more local
                                                #  maxima than this value, then
                                                #  we wiil only take the top
                                                #  persistence ones, if there
                                                #  are fewer, then we will only
                                                #  grab that many and then force
                                                #  an early update
    self.thickness      = 0                      # Number of steps outward from
                                                #  the extracted limit surface
                                                #  to include in the candidate
                                                #  set
    self.simplification = 0                     # Pre-rank simpligication level
                                                #  (% of range space)
    self.threshold      = 0                     # Post-rank function value
                                                #  cutoff (%  of range space)
    self.printTag            = 'SAMPLER ADAPTIVE'

    self.acceptedScoringParam = ['distance','distancePersistence']
    self.acceptedBatchParam = ['none','naive','maxV','maxP']

    self._addAssObject('TargetEvaluation','n')
    self._addAssObject('ROM','n')
    self._addAssObject('Function','-n')

  def _localWhatDoINeed(self):
    """
    This method is a local mirror of the general whatDoINeed method.
    It is implemented by the samplers that need to request special objects
    @ In , None, None
    @ Out, needDict, list of objects needed
    """
    LSDict = AdaptiveSampler._localWhatDoINeed(self)
    LSDict['internal'] = [(None,'jobHandler')]
    return LSDict

  def _localGenerateAssembler(self,initDict):
    """Generates the assembler.
    @ In, initDict, dict of init objects
    @ Out, None
    """
    AdaptiveSampler._localGenerateAssembler(self, initDict)
    self.jobHandler = initDict['internal']['jobHandler']
    #do a distributions check for ND
    for dist in self.distDict.values():
      if isinstance(dist,Distributions.NDimensionalDistributions): self.raiseAnError(IOError,'ND Dists not supported for this sampler (yet)!')

  def localInputAndChecks(self,xmlNode):
    """
    Class specific xml inputs will be read here and checked for validity.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    @ Out, None
    """
    if 'limit' in xmlNode.attrib.keys():
      try: self.limit = int(xmlNode.attrib['limit'])
      except ValueError: self.raiseAnError(IOError,'reading the attribute for the sampler '+self.name+' it was not possible to perform the conversion to integer for the attribute limit with value '+xmlNode.attrib['limit'])
    # convergence Node
    convergenceNode = xmlNode.find('Convergence')
    if convergenceNode==None:self.raiseAnError(IOError,'the node Convergence was missed in the definition of the adaptive sampler '+self.name)
    try   : self.tolerance=float(convergenceNode.text)
    except: self.raiseAnError(IOError,'Failed to convert '+convergenceNode.text+' to a meaningful number for the convergence')
    attribList = list(convergenceNode.attrib.keys())
    if 'limit'          in convergenceNode.attrib.keys():
      attribList.pop(attribList.index('limit'))
      try   : self.limit = int (convergenceNode.attrib['limit'])
      except: self.raiseAnError(IOError,'Failed to convert the limit value '+convergenceNode.attrib['limit']+' to a meaningful number for the convergence')
    if 'persistence'    in convergenceNode.attrib.keys():
      attribList.pop(attribList.index('persistence'))
      try   : self.persistence = int (convergenceNode.attrib['persistence'])
      except: self.raiseAnError(IOError,'Failed to convert the persistence value '+convergenceNode.attrib['persistence']+' to a meaningful number for the convergence')
    if 'weight'         in convergenceNode.attrib.keys():
      attribList.pop(attribList.index('weight'))
      try   : self.toleranceWeight = str(convergenceNode.attrib['weight']).lower()
      except: self.raiseAnError(IOError,'Failed to convert the weight type '+convergenceNode.attrib['weight']+' to a meaningful string for the convergence')
    if 'subGridTol'    in convergenceNode.attrib.keys():
      attribList.pop(attribList.index('subGridTol'))
      try   : self.subGridTol = float (convergenceNode.attrib['subGridTol'])
      except: self.raiseAnError(IOError,'Failed to convert the subGridTol '+convergenceNode.attrib['subGridTol']+' to a meaningful float for the convergence')
    if 'forceIteration' in convergenceNode.attrib.keys():
      attribList.pop(attribList.index('forceIteration'))
      if   convergenceNode.attrib['forceIteration']=='True' : self.forceIteration   = True
      elif convergenceNode.attrib['forceIteration']=='False': self.forceIteration   = False
      else: self.raiseAnError(RuntimeError,'Reading the convergence setting for the adaptive sampler '+self.name+' the forceIteration keyword had an unknown value: '+str(convergenceNode.attrib['forceIteration']))
    #assembler node: Hidden from User
    # set subgrid
    if self.subGridTol == None: self.subGridTol = self.tolerance
    if self.subGridTol > self.tolerance: self.raiseAnError(IOError,'The sub grid tolerance '+str(self.subGridTol)+' must be smaller than the tolerance: '+str(self.tolerance))
    if len(attribList)>0: self.raiseAnError(IOError,'There are unknown keywords in the convergence specifications: '+str(attribList))

    # Batch parameters
    for child in xmlNode:
      if child.tag == "generateCSVs" : self.generateCSVs = True
      if child.tag == "batchStrategy":
        self.batchStrategy = child.text.encode('ascii')
        if self.batchStrategy not in self.acceptedBatchParam:
          self.raiseAnError(IOError, 'Requested unknown batch strategy: ',
                            self.batchStrategy, '. Available options: ',
                            self.acceptedBatchParam)
      if child.tag == "maxBatchSize":
        try   : self.maxBatchSize = int(child.text)
        except: self.raiseAnError(IOError, 'Failed to convert the maxBatchSize value: ' + child.text + ' into a meaningful integer')
        if self.maxBatchSize < 0:
          self.raiseAWarning(IOError,'Requested an invalid maximum batch size: ', self.maxBatchSize, '. This should be a non-negative integer value. Defaulting to 1.')
          self.maxBatchSize = 1
      if child.tag == "scoring":
        self.scoringMethod = child.text.encode('ascii')
        if self.scoringMethod not in self.acceptedScoringParam:
          self.raiseAnError(IOError, 'Requested unknown scoring type: ', self.scoringMethod, '. Available options: ', self.acceptedScoringParam)
      if child.tag == 'simplification':
        try   : self.simplification = float(child.text)
        except: self.raiseAnError(IOError, 'Failed to convert the simplification value: ' + child.text + ' into a meaningful number')
        if self.simplification < 0 or self.simplification > 1:
          self.raiseAWarning('Requested an invalid simplification level: ', self.simplification, '. Defaulting to 0.')
          self.simplification = 0
      if child.tag == 'thickness':
        try   : self.thickness = int(child.text)
        except: self.raiseAnError(IOError, 'Failed to convert the thickness value: ' + child.text +' into a meaningful integer')
        if self.thickness < 0:
          self.raiseAWarning('Requested an invalid thickness size: ', self.thickness, '. Defaulting to 0.')
      if child.tag == 'threshold':
        try   : self.threshold = float(child.text)
        except: self.raiseAnError(IOError, 'Failed to convert the threshold value: ' + child.text + ' into a meaningful number')
        if self.threshold < 0 or self.threshold > 1:
          self.raiseAWarning('Requested an invalid threshold level: ', self.threshold, '. Defaulting to 0.')
          self.threshold = 0

  def localAddInitParams(self,tempDict):
    """
    Appends a given dictionary with class specific member variables and their
    associated initialized values.
    @ InOut, tempDict: The dictionary where we will add the initialization
                       parameters specific to this Sampler.
    """
    tempDict['Iter. forced'    ] = str(self.forceIteration)
    tempDict['Norm tolerance'  ] = str(self.tolerance)
    tempDict['Sub grid size'   ] = str(self.subGridTol)
    tempDict['Error Weight'    ] = str(self.toleranceWeight)
    tempDict['Persistence'     ] = str(self.repetition)
    tempDict['batchStrategy'   ] = self.batchStrategy
    tempDict['maxBatchSize'    ] = self.maxBatchSize
    tempDict['scoring'         ] = str(self.scoringMethod)
    tempDict['simplification'  ] = self.simplification
    tempDict['thickness'       ] = self.thickness
    tempDict['threshold'       ] = self.threshold

  def localAddCurrentSetting(self,tempDict):
    """
    Appends a given dictionary with class specific information regarding the
    current status of the object.
    @ InOut, tempDict: The dictionary where we will add the parameters specific
                       to this Sampler and their associated values.
    """
    if self.solutionExport!=None: tempDict['The solution is exported in '    ] = 'Name: ' + self.solutionExport.name + 'Type: ' + self.solutionExport.type
    if self.goalFunction!=None  : tempDict['The function used is '] = self.goalFunction.name

  def localInitialize(self,solutionExport=None):
    """
    Will perform all initialization specific to this Sampler. For instance,
    creating an empty container to hold the identified surface points, error
    checking the optionally provided solution export and other preset values,
    and initializing the limit surface Post-Processor used by this sampler.

    @ InOut, solutionExport: a PointSet to hold the solution (a list of limit
                             surface points)
    """
    self.limitSurfacePP   = PostProcessors.returnInstance("LimitSurface",self)
    if 'Function' in self.assemblerDict.keys(): self.goalFunction = self.assemblerDict['Function'][0][3]
    if 'TargetEvaluation' in self.assemblerDict.keys(): self.lastOutput = self.assemblerDict['TargetEvaluation'][0][3]
    #self.memoryStep        = 5               # number of step for which the memory is kept
    self.solutionExport    = solutionExport
    # check if solutionExport is actually a "DataObjects" type "PointSet"
    if type(solutionExport).__name__ != "PointSet": self.raiseAnError(IOError,'solutionExport type is not a PointSet. Got '+ type(solutionExport).__name__+'!')
    self.surfPoint         = None             #coordinate of the points considered on the limit surface
    self.oldTestMatrix     = OrderedDict()    #This is the test matrix to use to store the old evaluation of the function
    self.persistenceMatrix = OrderedDict()    #this is a matrix that for each point of the testing grid tracks the persistence of the limit surface position
    if self.goalFunction.name not in self.solutionExport.getParaKeys('output'): self.raiseAnError(IOError,'Goal function name does not match solution export data output.')
    # set number of job request-able after a new evaluation
    self._endJobRunnable   = 1
    #check if convergence is not on probability if all variables are bounded in value otherwise the problem is unbounded
    if self.toleranceWeight=='value':
      for varName in self.distDict.keys():
        if not(self.distDict[varName].upperBoundUsed and self.distDict[varName].lowerBoundUsed):
          self.raiseAnError(TypeError,'It is impossible to converge on an unbounded domain (variable '+varName+' with distribution '+self.distDict[varName].name+') as requested to the sampler '+self.name)
    elif self.toleranceWeight=='cdf': pass
    else: self.raiseAnError(IOError,'Unknown weight string descriptor: '+self.toleranceWeight)
    #setup the grid. The grid is build such as each element has a volume equal to the sub grid tolerance
    #the grid is build in such a way that an unit change in each node within the grid correspond to a change equal to the tolerance
    self.nVar         = len(self.distDict.keys())              # Total number of variables
    bounds          = {"lowerBounds":{},"upperBounds":{}}
    transformMethod = {}
    for varName in self.distDict.keys():
      if self.toleranceWeight!='cdf': bounds["lowerBounds"][varName.replace('<distribution>','')], bounds["upperBounds"][varName.replace('<distribution>','')] = self.distDict[varName].lowerBound, self.distDict[varName].upperBound
      else:
        bounds["lowerBounds"][varName.replace('<distribution>','')], bounds["upperBounds"][varName.replace('<distribution>','')] = 0.0, 1.0
        transformMethod[varName.replace('<distribution>','')] = [self.distDict[varName].ppf]
    #moving forward building all the information set
    self.axisName = list(self.distDict.keys())
    self.axisName.sort()
    # initialize LimitSurface PP
    self.limitSurfacePP._initFromDict({"name":self.name+"LSpp","parameters":[key.replace('<distribution>','') for key in self.axisName],"tolerance":self.tolerance,"side":"both","transformationMethods":transformMethod,"bounds":bounds})
    self.limitSurfacePP.assemblerDict = self.assemblerDict
    self.limitSurfacePP._initializeLSpp({'WorkingDir':None},[self.lastOutput],{'computeCells':self.tolerance != self.subGridTol})
    matrixShape = self.limitSurfacePP.getTestMatrix().shape
    self.persistenceMatrix[self.name+"LSpp"]  = np.zeros(matrixShape) #matrix that for each point of the testing grid tracks the persistence of the limit surface position
    self.oldTestMatrix[self.name+"LSpp"]      = np.zeros(matrixShape) #swap matrix fro convergence test
    self.hangingPoints                        = np.ndarray((0, self.nVar))
    self.raiseADebug('Initialization done')

  def localStillReady(self,ready): #,lastOutput=None
    """
    first perform some check to understand what it needs to be done possibly perform an early return
    ready is returned
    lastOutput should be present when the next point should be chosen on previous iteration and convergence checked
    lastOutput it is not considered to be present during the test performed for generating an input batch
    ROM if passed in it is used to construct the test matrix otherwise the nearest neighbor value is used
    @ In,  ready, boolean, a boolean representing whether the caller is prepared for another input.
    @ Out, ready, boolean, a boolean representing whether the caller is prepared for another input.
    """
    self.raiseADebug('From method localStillReady...')
    #test on what to do
    if ready      == False: return ready #if we exceeded the limit just return that we are done
    if type(self.lastOutput) == dict:
      if self.lastOutput == None and self.limitSurfacePP.ROM.amITrained==False: return ready
    else:
      #if the last output is not provided I am still generating an input batch, if the rom was not trained before we need to start clean
      if self.lastOutput.isItEmpty() and self.limitSurfacePP.ROM.amITrained==False: return ready
    #first evaluate the goal function on the newly sampled points and store them in mapping description self.functionValue RecontructEnding
    if type(self.lastOutput) == dict: self.limitSurfacePP._initializeLSppROM(self.lastOutput,False)
    else:
      if not self.lastOutput.isItEmpty(): self.limitSurfacePP._initializeLSppROM(self.lastOutput,False)
    self.raiseADebug('Classifier ' +self.name+' has been trained!')
    self.oldTestMatrix = copy.deepcopy(self.limitSurfacePP.getTestMatrix("all",exceptionGrid=self.exceptionGrid))    #copy the old solution (contained in the limit surface PP) for convergence check
    # evaluate the Limit Surface coordinates (return input space coordinates, evaluation vector and grid indexing)
    self.surfPoint, evaluations, self.listSurfPoint = self.limitSurfacePP.run(returnListSurfCoord = True, exceptionGrid=self.exceptionGrid, merge=False)
    self.raiseADebug('Limit Surface has been computed!')
    # check hanging points
    if self.goalFunction.name in self.limitSurfacePP.getFunctionValue().keys(): indexLast = len(self.limitSurfacePP.getFunctionValue()[self.goalFunction.name])-1
    else                                                                      : indexLast = -1
    #index of last set of point tested and ready to perform the function evaluation
    indexEnd  = len(self.limitSurfacePP.getFunctionValue()[self.axisName[0].replace('<distribution>','')])-1
    tempDict  = {}
    for myIndex in range(indexLast+1,indexEnd+1):
      for key, value in self.limitSurfacePP.getFunctionValue().items(): tempDict[key] = value[myIndex]
      if len(self.hangingPoints) > 0: self.hangingPoints = self.hangingPoints[~(self.hangingPoints==np.array([tempDict[varName] for varName in [key.replace('<distribution>','') for key in self.axisName]])).all(axis=1)][:]
    for key,value in self.limitSurfacePP.getTestMatrix("all",exceptionGrid=self.exceptionGrid).items():
      self.persistenceMatrix[key] += value
    # get the test matrices' dictionaries to test the error
    testMatrixDict, oldTestMatrixDict = list(self.limitSurfacePP.getTestMatrix("all",exceptionGrid=self.exceptionGrid).values()),list(self.oldTestMatrix.values())
    # the first test matrices in the list are always represented by the coarse grid (if subGridTol activated) or the only grid available
    coarseGridTestMatix, coarseGridOldTestMatix = testMatrixDict.pop(0), oldTestMatrixDict.pop(0)
    # compute the Linf norm with respect the location of the LS
    testError = np.sum(np.abs(np.subtract(coarseGridTestMatix,coarseGridOldTestMatix)))
    if len(testMatrixDict) > 0: testError += np.sum(np.abs(np.subtract(testMatrixDict,oldTestMatrixDict))) # compute the error
    if (testError > self.errorTolerance): ready, self.repetition = True, 0                                 # we still have error
    else                                : self.repetition +=1                                              # we are increasing persistence
    if self.persistence<self.repetition:
      ready =  False
      if self.subGridTol != self.tolerance and evaluations is not None and self.refinedPerformed != True:
        # we refine the grid since we converged on the coarse one. we use the "ceil" method in order to be sure
        # that the volumetric cell weight is <= of the subGridTol
        self.raiseAMessage("Grid refinement activated! Refining the evaluation grid!")
        self.limitSurfacePP.refineGrid(int(ceil((self.tolerance/self.subGridTol)**(1.0/self.nVar))))
        self.exceptionGrid, self.refinedPerformed, ready, self.repetition = self.name + "LSpp", True, True, 0
        self.persistenceMatrix.update(copy.deepcopy(self.limitSurfacePP.getTestMatrix("all",exceptionGrid=self.exceptionGrid)))
        self.errorTolerance = self.subGridTol
    self.raiseAMessage('counter: '+str(self.counter)+'       Error: ' +str(testError)+' Repetition: '+str(self.repetition))
    #if the number of point on the limit surface is > than compute persistence
    realAxisNames, cnt = [key.replace('<distribution>','') for key in self.axisName], 0
    for gridID,listsurfPoint in self.listSurfPoint.items():
      if len(listsurfPoint)>0:
        self.invPointPersistence[gridID] = np.ones(len(listsurfPoint))
        if self.firstSurface == False:
          for pointID, coordinate in enumerate(listsurfPoint): self.invPointPersistence[gridID][pointID]=abs(self.persistenceMatrix[gridID][tuple(coordinate)])
          maxPers = np.max(self.invPointPersistence[gridID])
          if maxPers != 0: self.invPointPersistence[gridID] = (maxPers-self.invPointPersistence[gridID])/maxPers
        else: self.firstSurface = False
        if self.solutionExport!=None:
          for varName in self.solutionExport.getParaKeys('inputs'):
            for varIndex in range(len(self.axisName)):
              if varName == realAxisNames[varIndex]:
                if cnt == 0: self.solutionExport.removeInputValue(varName)
                for value in self.surfPoint[gridID][:,varIndex]: self.solutionExport.updateInputValue(varName,copy.copy(value))
          # to be fixed
          if cnt == 0: self.solutionExport.removeOutputValue(self.goalFunction.name)
          for index in range(len(evaluations[gridID])):
            self.solutionExport.updateOutputValue(self.goalFunction.name,copy.copy(evaluations[gridID][index]))
        cnt+=1

    # Keep track of some extra points that we will add to thicken the limit
    # surface candidate set
    self.bandIndices = OrderedDict()
    for gridID,points in self.listSurfPoint.items():
      setSurfPoint = set()
      self.bandIndices[gridID] = set()
      for surfPoint in points: setSurfPoint.add(tuple(surfPoint))
      newIndices = set(setSurfPoint)
      for step in xrange(1,self.thickness):
        prevPoints = set(newIndices)
        newIndices = set()
        for i,iCoords in enumerate(prevPoints):
          for d in xrange(len(iCoords)):
            offset = np.zeros(len(iCoords),dtype=int)
            offset[d] = 1
            if iCoords[d] - offset[d] > 0: newIndices.add(tuple(iCoords - offset))
            if iCoords[d] + offset[d] < self.oldTestMatrix[gridID].shape[d]-1: newIndices.add(tuple(iCoords + offset))
        self.bandIndices[gridID].update(newIndices)
      self.bandIndices[gridID] = self.bandIndices[gridID].difference(setSurfPoint)
      self.bandIndices[gridID] = list(self.bandIndices[gridID])
      for coordinate in self.bandIndices[gridID]: self.surfPoint[gridID] = np.vstack((self.surfPoint[gridID],self.limitSurfacePP.gridCoord[gridID][coordinate]))
    return ready

  def scoreCandidates(self):
    """compute the scores of the 'candidate set' which should be the currently
    extracted limit surface.
    @ In, None
    @ Out, None
    """
    # DM: This sequence gets used repetitively, so I am promoting it to its own
    #  variable
    axisNames = [key.replace('<distribution>','') for key in self.axisName]
    matrixShape = self.limitSurfacePP.getTestMatrix().shape
    self.scores = OrderedDict()
    if self.scoringMethod.startswith('distance'):
      sampledMatrix = np.zeros((len(self.limitSurfacePP.getFunctionValue()[axisNames[0]])+len(self.hangingPoints[:,0]),len(self.axisName)))
      for varIndex, name in enumerate(axisNames):
        sampledMatrix[:,varIndex] = np.append(self.limitSurfacePP.getFunctionValue()[name],self.hangingPoints[:,varIndex])
      distanceTree = spatial.cKDTree(copy.copy(sampledMatrix),leafsize=12)
      # The hanging point are added to the list of the already explored points
      # so as not to pick the same when in parallel
      for varIndex, _ in enumerate(axisNames):
        self.inputInfo['distributionName'][self.axisName[varIndex]] = self.toBeSampled[self.axisName[varIndex]]
        self.inputInfo['distributionType'][self.axisName[varIndex]] = self.distDict[self.axisName[varIndex]].type

      for key, value in self.invPointPersistence.items():
        if key != self.exceptionGrid and self.surfPoint[key] is not None:
          distance, _ = distanceTree.query(self.surfPoint[key])
          # Different versions of scipy/numpy will yield different results on
          # our various supported platforms. If things are this close, then it
          # it is highly unlikely choosing one point over the other will affect
          # us much, so limit the precision to allow the same results on older
          # versions. Scale could be important, though, so normalize the
          # distances first. Alternatively, we could force newer versions of
          # these libraries, but since our own HPC does not yet support them,
          # this should be acceptable, agreed? - DPM Nov. 23, 2015
          maxDistance = max(distance)
          if maxDistance != 0:
            distance = np.round(distance/maxDistance,15)
          if self.scoringMethod == 'distance' or max(self.invPointPersistence) == 0:
            self.scores[key] = distance
          else:
            self.scores[key] = np.multiply(distance,self.invPointPersistence[key])
    elif self.scoringMethod == 'debug':
      self.scores = OrderedDict()
      for key, value in self.invPointPersistence.items():
        self.scores[key] = np.zeros(len(self.surfPoint[key]))
        for i in xrange(len(self.listsurfPoint)): self.scores[key][i] = 1
    else:
      self.raiseAnError(NotImplementedError,self.scoringMethod + ' scoring method is not implemented yet')

  def localGenerateInput(self,model,oldInput):
    """
      Function to select the next most informative point for refining the limit
      surface search.
      After this method is called, the self.inputInfo should be ready to be sent
      to the model
      @ In model, Model, an instance of a model
      @ In oldInput, [], a list of the original needed inputs for the model (e.g. list of files, etc.)
      @ Out, None
    """
    #  Alternatively, though I don't think we do this yet:
    #  compute the direction normal to the surface, compute the derivative
    #  normal to the surface of the probability, check the points where the
    #  derivative probability is the lowest

    # create values dictionary
    self.inputInfo['distributionName'] = {} #Used to determine which distribution to change if needed.
    self.inputInfo['distributionType'] = {} #Used to determine which distribution type is used
    self.raiseADebug('generating input')
    varSet=False

    # DM: This sequence gets used repetitively, so I am promoting it to its own
    #  variable
    axisNames = [key.replace('<distribution>','') for key in self.axisName]

    if self.surfPoint is not None and len(self.surfPoint) > 0:
      if self.batchStrategy == 'none':
        self.scoreCandidates()
        maxDistance, maxGridId, maxId =  0.0, "", 0
        for key, value in self.invPointPersistence.items():
          if key != self.exceptionGrid and self.surfPoint[key] is not None:
            localMax = np.max(self.scores[key])
            if localMax > maxDistance:
              maxDistance, maxGridId, maxId  = localMax, key,  np.argmax(self.scores[key])
        if maxDistance > 0.0:
          for varIndex, _ in enumerate([key.replace('<distribution>','') for key in self.axisName]):
            self.values[self.axisName[varIndex]] = copy.copy(float(self.surfPoint[maxGridId][maxId,varIndex]))
            self.inputInfo['SampledVarsPb'][self.axisName[varIndex]] = self.distDict[self.axisName[varIndex]].pdf(self.values[self.axisName[varIndex]])
          varSet=True
        else:
          self.raiseADebug('Maximum score is 0.0')
      elif self.batchStrategy.startswith('max'):
        ########################################################################
        ## Initialize the queue with as many points as requested or as many as
        ## possible
        if len(self.toProcess) == 0:
          self.scoreCandidates()
          edges = []

          flattenedSurfPoints = list()
          flattenedBandPoints = list()
          flattenedScores     = list()
          for key in self.bandIndices.keys():
            flattenedSurfPoints = flattenedSurfPoints + list(self.surfPoint[key])
            flattenedScores = flattenedScores + list(self.scores[key])
            flattenedBandPoints = flattenedBandPoints + self.listSurfPoint[key] + self.bandIndices[key]

          flattenedSurfPoints = np.array(flattenedSurfPoints)
          for i,iCoords in enumerate(flattenedBandPoints):
            for j in xrange(i+1, len(flattenedBandPoints)):
              jCoords = flattenedBandPoints[j]
              ijValidNeighbors = True
              for d in xrange(len(jCoords)):
                if abs(iCoords[d] - jCoords[d]) > 1:
                  ijValidNeighbors = False
                  break
              if ijValidNeighbors:
                edges.append((i,j))
                edges.append((j,i))

          names = [ name.encode('ascii', 'ignore') for name in axisNames]
          names.append('score'.encode('ascii','ignore'))
          amsc = AMSC_Object(X=flattenedSurfPoints, Y=flattenedScores,
                             w=None, names=names, graph='none',
                             gradient='steepest', normalization='feature',
                             persistence='difference', edges=edges, debug=False)
          plevel = self.simplification*(max(flattenedScores)-min(flattenedScores))
          partitions = amsc.StableManifolds(plevel)
          mergeSequence = amsc.GetMergeSequence()
          maxIdxs = list(set(partitions.keys()))

          thresholdLevel = self.threshold*(max(flattenedScores)-min(flattenedScores))+min(flattenedScores)
          # Sort the maxima based on decreasing function value, thus the top
          # candidate is the first element.
          if self.batchStrategy.endswith('V'):
            sortedMaxima = sorted(maxIdxs, key=lambda idx: flattenedScores[idx], reverse=True)
          else:
          # Sort the maxima based on decreasing persistence value, thus the top
          # candidate is the first element.
            sortedMaxima = sorted(maxIdxs, key=lambda idx: mergeSequence[idx][1], reverse=True)
          B = min(self.maxBatchSize,len(sortedMaxima))
          for idx in sortedMaxima[0:B]:
            if flattenedScores[idx] >= thresholdLevel:
              self.toProcess.append(flattenedSurfPoints[idx,:])
          if len(self.toProcess) == 0:
            self.toProcess.append(flattenedSurfPoints[np.argmax(flattenedScores),:])
        ########################################################################
        ## Select one sample
        selectedPoint = self.toProcess.pop()
        for varIndex, varName in enumerate(axisNames):
          self.values[self.axisName[varIndex]] = float(selectedPoint[varIndex])
          self.inputInfo['SampledVarsPb'][self.axisName[varIndex]] = self.distDict[self.axisName[varIndex]].pdf(self.values[self.axisName[varIndex]])
        varSet=True
      elif self.batchStrategy == 'naive':
        ########################################################################
        ## Initialize the queue with as many points as requested or as many as
        ## possible
        if len(self.toProcess) == 0:
          self.scoreCandidates()
          sortedIndices = sorted(range(len(self.scores)), key=lambda k: self.scores[k],reverse=True)
          B = min(self.maxBatchSize,len(sortedIndices))
          for idx in sortedIndices[0:B]:
            self.toProcess.append(self.surfPoint[idx,:])
          if len(self.toProcess) == 0:
            self.toProcess.append(self.surfPoint[np.argmax(self.scores),:])
        ########################################################################
        ## Select one sample
        selectedPoint = self.toProcess.pop()
        for varIndex, varName in enumerate(axisNames):
          self.values[self.axisName[varIndex]] = float(selectedPoint[varIndex])
          self.inputInfo['SampledVarsPb'][self.axisName[varIndex]] = self.distDict[self.axisName[varIndex]].pdf(self.values[self.axisName[varIndex]])
        varSet=True

    if not varSet:
      #here we are still generating the batch
      for key in self.distDict.keys():
        if self.toleranceWeight=='cdf':
          self.values[key]                       = self.distDict[key].ppf(float(Distributions.random()))
        else:
          self.values[key]                       = self.distDict[key].lowerBound+(self.distDict[key].upperBound-self.distDict[key].lowerBound)*float(Distributions.random())
        self.inputInfo['distributionName'][key]  = self.toBeSampled[key]
        self.inputInfo['distributionType'][key]  = self.distDict[key].type
        self.inputInfo['SampledVarsPb'   ][key]  = self.distDict[key].pdf(self.values[key])
        self.inputInfo['ProbabilityWeight-'+key] = self.distDict[key].pdf(self.values[key])
    self.inputInfo['PointProbability'    ]      = reduce(mul, self.inputInfo['SampledVarsPb'].values())
    # the probability weight here is not used, the post processor is going to recreate the grid associated and use a ROM for the probability evaluation
    self.inputInfo['ProbabilityWeight']         = self.inputInfo['PointProbability']
    self.hangingPoints                          = np.vstack((self.hangingPoints,copy.copy(np.array([self.values[axis] for axis in self.axisName]))))
    self.raiseADebug('At counter '+str(self.counter)+' the generated sampled variables are: '+str(self.values))
    self.inputInfo['SamplerType'] = 'LimitSurfaceSearch'
    self.inputInfo['subGridTol' ] = self.subGridTol

    #      This is the normal derivation to be used later on
    #      pbMapPointCoord = np.zeros((len(self.surfPoint),self.nVar*2+1,self.nVar))
    #      for pointIndex, point in enumerate(self.surfPoint):
    #        temp = copy.copy(point)
    #        pbMapPointCoord[pointIndex,2*self.nVar,:] = temp
    #        for varIndex, varName in enumerate([key.replace('<distribution>','') for key in self.axisName]):
    #          temp[varIndex] -= np.max(self.axisStepSize[varName])
    #          pbMapPointCoord[pointIndex,varIndex,:] = temp
    #          temp[varIndex] += 2.*np.max(self.axisStepSize[varName])
    #          pbMapPointCoord[pointIndex,varIndex+self.nVar,:] = temp
    #          temp[varIndex] -= np.max(self.axisStepSize[varName])
    #      #getting the coordinate ready to be evaluated by the ROM
    #      pbMapPointCoord.shape = (len(self.surfPoint)*(self.nVar*2+1),self.nVar)
    #      tempDict = {}
    #      for varIndex, varName in enumerate([key.replace('<distribution>','') for key in self.axisName]):
    #        tempDict[varName] = pbMapPointCoord.T[varIndex,:]
    #      #acquiring Pb evaluation
    #      pbPoint       = self.ROM.confidence(tempDict)
    #      pbPoint.shape = (len(self.surfPoint),self.nVar*2+1,2)
    #      pbMapPointCoord.shape = (len(self.surfPoint),self.nVar*2+1,self.nVar)
    #      #computing gradient
    #      modGrad   = np.zeros((len(self.surfPoint)))
    #      gradVect  = np.zeros((len(self.surfPoint),self.nVar))
    #      for pointIndex in range(len(self.surfPoint)):
    #        centralCoor = pbMapPointCoord[pointIndex,2*self.nVar,:]
    #        centraPb    = pbPoint[pointIndex,2*self.nVar][0]
    #        sum = 0.0
    #        for varIndex in range(self.nVar):
    #          d1Down     = (centraPb-pbPoint[pointIndex,varIndex][0])/(centralCoor[varIndex]-pbMapPointCoord[pointIndex,varIndex,varIndex])
    #          d1Up       = (pbPoint[pointIndex,varIndex+self.nVar][0]-centraPb)/(pbMapPointCoord[pointIndex,varIndex+self.nVar,varIndex]-centralCoor[varIndex])
    #          if np.abs(d1Up)>np.abs(d1Down): d1Avg = d1Up
    #          else                          : d1Avg = d1Down
    #          gradVect[pointIndex,varIndex] = d1Avg
    #          sum +=d1Avg
    #          modGrad[pointIndex] += d1Avg**2
    #        modGrad[pointIndex] = np.sqrt(modGrad[pointIndex])*np.abs(sum)/sum
    #        #concavityPb[pointIndex] = concavityPb[pointIndex]/float(self.nVar)
    #      for pointIndex, point in enumerate(self.surfPoint):
    #        myStr  = ''
    #        myStr  += '['
    #        for varIndex in range(self.nVar):
    #          myStr += '{:+6.4f}'.format(pbMapPointCoord[pointIndex,2*self.nVar,varIndex])
    #        myStr += '] '+'{:+6.4f}'.format(pbPoint[pointIndex,2*self.nVar,0])+'   '
    #        for varIndex in range(2*self.nVar):
    #          myStr += '['
    #          for varIndex2 in range(self.nVar):
    #            myStr += '{:+6.4f}'.format(pbMapPointCoord[pointIndex,varIndex,varIndex2])+' '
    #          myStr += '] '+'{:+6.4f}'.format(pbPoint[pointIndex,varIndex,0])+'   '
    #        myStr += '   gradient  ['
    #        for varIndex in range(self.nVar):
    #          myStr += '{:+6.4f}'.format(gradVect[pointIndex,varIndex])+'  '
    #        myStr += ']'
    #        myStr += '    Module '+'{:+6.4f}'.format(modGrad[pointIndex])
    #
    #      minIndex = np.argmin(np.abs(modGrad))
    #      pdDist = self.sign*(pbPoint[minIndex,2*self.nVar][0]-0.5-10*self.tolerance)/modGrad[minIndex]
    #      for varIndex, varName in enumerate([key.replace('<distribution>','') for key in self.axisName]):
    #        self.values[varName] = copy.copy(float(pbMapPointCoord[minIndex,2*self.nVar,varIndex]+pdDist*gradVect[minIndex,varIndex]))
    #      gradVect = np.ndarray(self.nVar)
    #      centraPb = pbPoint[minIndex,2*self.nVar]
    #      centralCoor = pbMapPointCoord[minIndex,2*self.nVar,:]
    #      for varIndex in range(self.nVar):
    #        d1Down = (centraPb-pbPoint[minIndex,varIndex])/(centralCoor[varIndex]-pbMapPointCoord[minIndex,varIndex,varIndex])
    #        d1Up   = (pbPoint[minIndex,varIndex+self.nVar]-centraPb)/(pbMapPointCoord[minIndex,varIndex+self.nVar,varIndex]-centralCoor[varIndex])
    #        d1Avg   = (d1Up+d1Down)/2.0
    #        gradVect[varIndex] = d1Avg
    #      gradVect = gradVect*pdDist
    #      gradVect = gradVect+centralCoor
    #      for varIndex, varName in enumerate([key.replace('<distribution>','') for key in self.axisName]):
    #        self.values[varName] = copy.copy(float(gradVect[varIndex]))

  def localFinalizeActualSampling(self,jobObject,model,myInput):
    """generate representation of goal function"""
    pass

#
#
#
#
class MonteCarlo(Sampler):
  """MONTE CARLO Sampler"""
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Sampler.__init__(self)
    self.printTag = 'SAMPLER MONTECARLO'

  def localInputAndChecks(self,xmlNode):
    """
    Class specific xml inputs will be read here and checked for validity.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    @ Out, None
    """
    Sampler.readSamplerInit(self,xmlNode)
    if xmlNode.find('samplerInit')!= None:
      if xmlNode.find('samplerInit').find('limit')!= None:
        try              : self.limit = int(xmlNode.find('samplerInit').find('limit').text)
        except ValueError: self.raiseAnError(IOError,'reading the attribute for the sampler '+self.name+' it was not possible to perform the conversion to integer for the attribute limit with value '+xmlNode.attrib['limit'])
      else: self.raiseAnError(IOError,self,'Monte Carlo sampler '+self.name+' needs the limit block (number of samples) in the samplerInit block')
    else: self.raiseAnError(IOError,self,'Monte Carlo sampler '+self.name+' needs the samplerInit block')

  def localInitialize(self):
    """
    Will perform all initialization specific to this Sampler. This will be
    called at the beginning of each Step where this object is used. See base
    class for more details.
    """
    if self.restartData:
      self.counter+=len(self.restartData)
      self.raiseAMessage('Number of points from restart: %i' %self.counter)
      self.raiseAMessage('Number of points needed:       %i' %(self.limit-self.counter))
    #pass #TODO fix the limit based on restartData

  def localGenerateInput(self,model,myInput):
    """
    Will generate an input and associate it with a probability
    (set up self.inputInfo before being sent to the model)
      @ In, model, the model to evaluate
      @ In, myInput, list of original inputs (unused)
      @ Out, None
    """
    # create values dictionary
    for key in self.distDict:
      # check if the key is a comma separated list of strings
      # in this case, the user wants to sample the comma separated variables with the same sampled value => link the value to all comma separated variables

      dim    = self.variables2distributionsMapping[key]['dim']
      totDim = self.variables2distributionsMapping[key]['totDim']
      dist   = self.variables2distributionsMapping[key]['name']
      reducedDim = self.variables2distributionsMapping[key]['reducedDim']

      if totDim == 1:
        for var in self.distributions2variablesMapping[dist]:
          varID  = utils.first(var.keys())
          rvsnum = self.distDict[key].rvs()
          self.inputInfo['SampledVarsPb'][key] = self.distDict[key].pdf(rvsnum)
          for kkey in varID.strip().split(','):
            self.values[kkey] = np.atleast_1d(rvsnum)[0]
      elif totDim > 1:
        if reducedDim == 1:
          rvsnum = self.distDict[key].rvs()
          coordinate = np.atleast_1d(rvsnum).tolist()
          if reducedDim > len(coordinate): self.raiseAnError(IOError,"The dimension defined for variables drew from the multivariate normal distribution is exceeded by the dimension used in Distribution (MultivariateNormal) ")
          probabilityValue = self.distDict[key].pdf(coordinate)
          self.inputInfo['SampledVarsPb'][key] = probabilityValue
          for var in self.distributions2variablesMapping[dist]:
            varID  = utils.first(var.keys())
            varDim = var[varID]
            for kkey in varID.strip().split(','):
              self.values[kkey] = np.atleast_1d(rvsnum)[varDim-1]
      else:
        self.raiseAnError(IOError,"Total dimension for given distribution should be >= 1")

    if len(self.inputInfo['SampledVarsPb'].keys()) > 0:
      self.inputInfo['PointProbability'  ] = reduce(mul, self.inputInfo['SampledVarsPb'].values())
      #self.inputInfo['ProbabilityWeight' ] = 1.0 #MC weight is 1/N => weight is one
    self.inputInfo['SamplerType'] = 'MC'

  def _localHandleFailedRuns(self,failedRuns):
    """Specialized method for samplers to handle failed runs.  Defaults to failing runs.
    @ In, failedRuns, list of JobHandler.ExternalRunner objects
    @ Out, None
    """
    if len(failedRuns)>0: self.raiseADebug('  Continuing with reduced-size Monte Carlo sampling.')

#
#
#
#
class Grid(Sampler):
  """
  Samples the model on a given (by input) set of points
  """
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Sampler.__init__(self)
    self.printTag = 'SAMPLER GRID'
    self.axisName             = []    # the name of each axis (variable)
    self.gridInfo             = {}    # {'name of the variable':Type}  --> Type: CDF/Value
    self.externalgGridCoord   = False # boolean attribute. True if the coordinate list has been filled by external source (see factorial sampler)
    self.gridCoordinate       = []    # current grid coordinates
    self.existing             = []    # restart points
    self.gridEntity           = GridEntities.returnInstance('GridEntity',self)

  def localInputAndChecks(self,xmlNode):
    """
    Class specific xml inputs will be read here and checked for validity.
    Specifically, reading and construction of the grid for this Sampler.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    @ Out, None
    """
    if 'limit' in xmlNode.attrib.keys(): self.raiseAnError(IOError,'limit is not used in Grid sampler')
    self.limit = 1
    self.gridEntity._readMoreXml(xmlNode,dimensionTags=["variable","Distribution"],messageHandler=self.messageHandler, dimTagsPrefix={"Distribution":"<distribution>"})
    grdInfo = self.gridEntity.returnParameter("gridInfo")
    for axis, value in grdInfo.items(): self.gridInfo[axis] = value[0]
    if len(self.toBeSampled.keys()) != len(grdInfo.keys()): self.raiseAnError(IOError,'inconsistency between number of variables and grid specification')
    self.axisName = list(grdInfo.keys())
    self.axisName.sort()

  def localAddInitParams(self,tempDict):
    """
    Appends a given dictionary with class specific member variables and their
    associated initialized values.
    @ InOut, tempDict: The dictionary where we will add the initialization
                       parameters specific to this Sampler.
    """
    for variable,value in self.gridInfo.items():
      tempDict[variable+' is sampled using a grid in '] = value

  def localAddCurrentSetting(self,tempDict):
    """
    Appends a given dictionary with class specific information regarding the
    current status of the object.
    @ InOut, tempDict: The dictionary where we will add the parameters specific
                       to this Sampler and their associated values.
    """
    for var, value in self.values.items():
      tempDict['coordinate '+var+' has value'] = value

  def localInitialize(self):
    """
    This is used to check if the points and bounds are compatible with the distribution provided.
    It could not have been done earlier since the distribution might not have been initialized first
    """
    self.gridEntity.initialize()
    self.limit = len(self.gridEntity)
    if self.restartData is not None:
      inps = self.restartData.getInpParametersValues()
      self.existing = zip(*list(v for v in inps.values()))

  def localGenerateInput(self,model,myInput):
    """
    Will generate an input and associate it with a probability
      @ In, model, the model to evaluate
      @ In, myInput, list of original inputs (unused)
      @ Out, None
    """
    self.inputInfo['distributionName'] = {} #Used to determine which distribution to change if needed.
    self.inputInfo['distributionType'] = {} #Used to determine which distribution type is used
    weight = 1.0
    found=False
    while not found:
      recastDict = {}
      for i in range(len(self.axisName)):
        varName = self.axisName[i]
        if self.gridInfo[varName]=='CDF':
          if self.distDict[varName].getDimensionality()==1: recastDict[varName] = [self.distDict[varName].ppf]
          else: recastDict[varName] = [self.distDict[varName].inverseMarginalDistribution,[self.variables2distributionsMapping[varName]['dim']-1]]
        elif self.gridInfo[varName]!='value': self.raiseAnError(IOError,self.gridInfo[varName]+' is not know as value keyword for type. Sampler: '+self.name)
      if self.externalgGridCoord: currentIndexes, coordinates = self.gridEntity.returnIteratorIndexesFromIndex(self.gridCoordinate), self.gridEntity.returnCoordinateFromIndex(self.gridCoordinate, True, recastDict)
      else                      : currentIndexes, coordinates = self.gridEntity.returnIteratorIndexes(), self.gridEntity.returnPointAndAdvanceIterator(True,recastDict)
      if coordinates == None: raise utils.NoMoreSamplesNeeded
      coordinatesPlusOne  = self.gridEntity.returnShiftedCoordinate(currentIndexes,dict.fromkeys(self.axisName,1))
      coordinatesMinusOne = self.gridEntity.returnShiftedCoordinate(currentIndexes,dict.fromkeys(self.axisName,-1))
      for i in range(len(self.axisName)):
        varName = self.axisName[i]
        # compute the SampledVarsPb for 1-D distribution
        if ("<distribution>" in varName) or (self.variables2distributionsMapping[varName]['totDim']==1):
          for key in varName.strip().split(','):
            self.inputInfo['distributionName'][key] = self.toBeSampled[varName]
            self.inputInfo['distributionType'][key] = self.distDict[varName].type
            self.values[key] = coordinates[varName]
            self.inputInfo['SampledVarsPb'][key] = self.distDict[varName].pdf(self.values[key])
        # compute the SampledVarsPb for N-D distribution
        else:
            if self.variables2distributionsMapping[varName]['reducedDim']==1:    # to avoid double count;
              distName = self.variables2distributionsMapping[varName]['name']
              ndCoordinate=[0]*len(self.distributions2variablesMapping[distName])
              positionList = self.distributions2variablesIndexList[distName]
              for var in self.distributions2variablesMapping[distName]:
                variable = utils.first(var.keys())
                position = utils.first(var.values())
                ndCoordinate[positionList.index(position)] = float(coordinates[variable.strip()])
                for key in variable.strip().split(','):
                  self.inputInfo['distributionName'][key] = self.toBeSampled[variable]
                  self.inputInfo['distributionType'][key] = self.distDict[variable].type
                  self.values[key] = coordinates[variable]
              # Based on the discussion with Diego, we will use the following to compute SampledVarsPb.
              self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(ndCoordinate)
        # Compute the ProbabilityWeight
        if ("<distribution>" in varName) or (self.variables2distributionsMapping[varName]['totDim']==1):
          if self.distDict[varName].getDisttype() == 'Discrete':
            weight *= self.distDict[varName].pdf(coordinates[varName])
          else:
            if self.gridInfo[varName]=='CDF':
              if coordinatesPlusOne[varName] != sys.maxsize and coordinatesMinusOne[varName] != -sys.maxsize:
                midPlusCDF   = (coordinatesPlusOne[varName]+self.distDict[varName].cdf(self.values[key]))/2.0
                midMinusCDF  = (coordinatesMinusOne[varName]+self.distDict[varName].cdf(self.values[key]))/2.0
                self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = midPlusCDF - midMinusCDF
                weight *= midPlusCDF - midMinusCDF
              if coordinatesMinusOne[varName] == -sys.maxsize:
                midPlusCDF   = (coordinatesPlusOne[varName]+self.distDict[varName].cdf(self.values[key]))/2.0
                midMinusCDF  = 0.0
                self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = midPlusCDF - midMinusCDF
                weight *= midPlusCDF - midMinusCDF
              if coordinatesPlusOne[varName] == sys.maxsize:
                midPlusCDF   = 1.0
                midMinusCDF  = (coordinatesMinusOne[varName]+self.distDict[varName].cdf(self.values[key]))/2.0
                self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = midPlusCDF - midMinusCDF
                weight *= midPlusCDF - midMinusCDF
            else:   # Value
              if coordinatesPlusOne[varName] != sys.maxsize and coordinatesMinusOne[varName] != -sys.maxsize:
                midPlusValue   = (self.values[key]+coordinatesPlusOne[varName])/2.0
                midMinusValue  = (self.values[key]+coordinatesMinusOne[varName])/2.0
                weight *= self.distDict[varName].cdf(midPlusValue) - self.distDict[varName].cdf(midMinusValue)
                self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.distDict[varName].cdf(midPlusValue) - self.distDict[varName].cdf(midMinusValue)
              if coordinatesMinusOne[varName] == -sys.maxsize:
                midPlusValue   = (self.values[key]+coordinatesPlusOne[varName])/2.0
                self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.distDict[varName].cdf(midPlusValue) - 0.0
                weight *= self.distDict[varName].cdf(midPlusValue) - 0.0
              if coordinatesPlusOne[varName] == sys.maxsize:
                midMinusValue  = (self.values[key]+coordinatesMinusOne[varName])/2.0
                self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = 1.0 - self.distDict[varName].cdf(midMinusValue)
                weight *= 1.0 - self.distDict[varName].cdf(midMinusValue)
        # ND variable
        else:
          if self.variables2distributionsMapping[varName]['reducedDim']==1:    # to avoid double count of weight for ND distribution; I need to count only one variable instaed of N
            distName = self.variables2distributionsMapping[varName]['name']
            ndCoordinate=np.zeros(len(self.distributions2variablesMapping[distName]))
            dxs=np.zeros(len(self.distributions2variablesMapping[distName]))
            positionList = self.distributions2variablesIndexList[distName]
            for var in self.distributions2variablesMapping[distName]:
              variable = utils.first(var.keys()).strip()
              position = utils.first(var.values())
              ndCoordinate[positionList.index(position)] = coordinates[variable.strip()]
              if self.gridInfo[variable]=='CDF':
                if coordinatesPlusOne[variable] != sys.maxsize and coordinatesMinusOne[variable] != -sys.maxsize:
                  dxs[positionList.index(position)] = (self.distDict[variable].inverseMarginalDistribution(coordinatesPlusOne[variable],self.variables2distributionsMapping[variable]['dim']-1)
                      - self.distDict[variable].inverseMarginalDistribution(coordinatesMinusOne[variable],self.variables2distributionsMapping[variable]['dim']-1))/2.0
                if coordinatesMinusOne[variable] == -sys.maxsize:
                  dxs[positionList.index(position)] = self.distDict[variable].inverseMarginalDistribution(coordinatesPlusOne[variable],self.variables2distributionsMapping[variable]['dim']-1) - coordinates[variable.strip()]
                if coordinatesPlusOne[variable] == sys.maxsize:
                  dxs[positionList.index(position)] = coordinates[variable.strip()] - self.distDict[variable].inverseMarginalDistribution(coordinatesMinusOne[variable],self.variables2distributionsMapping[variable]['dim']-1)
              else:
                if coordinatesPlusOne[variable] != sys.maxsize and coordinatesMinusOne[variable] != -sys.maxsize:
                  dxs[positionList.index(position)] = (coordinatesPlusOne[variable] - coordinatesMinusOne[variable])/2.0
                if coordinatesMinusOne[variable] == -sys.maxsize:
                  dxs[positionList.index(position)] = coordinatesPlusOne[variable] - coordinates[variable.strip()]
                if coordinatesPlusOne[variable] == sys.maxsize:
                  dxs[positionList.index(position)] = coordinates[variable.strip()] - coordinatesMinusOne[variable]
            self.inputInfo['ProbabilityWeight-'+varName.replace(",","!")] = self.distDict[varName].cellIntegral(ndCoordinate,dxs)
            weight *= self.distDict[varName].cellIntegral(ndCoordinate,dxs)
      newpoint = tuple(self.values[key] for key in self.values.keys())
      if newpoint not in self.existing:
        found=True
        self.raiseADebug('New point found: '+str(newpoint))
      else:
        self.counter+=1
        if self.counter>=self.limit: raise utils.NoMoreSamplesNeeded
        self.raiseADebug('Existing point: '+str(newpoint))
      self.inputInfo['PointProbability' ] = reduce(mul, self.inputInfo['SampledVarsPb'].values())
      self.inputInfo['ProbabilityWeight'] = copy.deepcopy(weight)
      self.inputInfo['SamplerType'] = 'Grid'
#
#
#
#
class Stratified(Grid):
  """
  Stratified sampler, also known as Latin Hypercube Sampling (LHS). Currently no
  special filling methods are implemented
  """
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Grid.__init__(self)
    self.sampledCoordinate    = [] # a list of list for i=0,..,limit a list of the coordinate to be used this is needed for the LHS
    self.printTag = 'SAMPLER Stratified'
    self.globalGrid          = {}    # Dictionary for the globalGrid. These grids are used only for Stratified for ND distributions.

  def localInputAndChecks(self,xmlNode):
    """
    Class specific xml inputs will be read here and checked for validity.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    @ Out, None
    """
    Sampler.readSamplerInit(self,xmlNode)
    Grid.localInputAndChecks(self,xmlNode)
    pointByVar  = [len(self.gridEntity.returnParameter("gridInfo")[variable][2]) for variable in self.gridInfo.keys()]
    if len(set(pointByVar))!=1: self.raiseAnError(IOError,'the latin Hyper Cube requires the same number of point in each dimension')
    self.pointByVar         = pointByVar[0]
    self.inputInfo['upper'] = {}
    self.inputInfo['lower'] = {}

  def localInitialize(self):
    """
    the local initialize is used to generate test the box being within the
    distribution upper/lower bound and filling mapping of the hyper cube.
    @ In, None
    @ Out, None
    """
    Grid.localInitialize(self)
    self.limit = (self.pointByVar-1)
    # For the multivariate normal distribtuion, if the user generates the grids on the transformed space, the user needs to provide the grid for each variables, no globalGrid is needed
    if self.variablesTransformationDict:
      tempFillingCheck = [[None]*(self.pointByVar-1)]*len(self.gridEntity.returnParameter("dimensionNames")) #for all variables
      self.sampledCoordinate = [[None]*len(self.axisName)]*(self.pointByVar-1)
      for i in range(len(tempFillingCheck)): tempFillingCheck[i]  = Distributions.randomPermutation(list(range(self.pointByVar-1)),self) #pick a random interval sequence
      mappingIdVarName = {}
      for cnt, varName in enumerate(self.axisName):
        mappingIdVarName[varName] = cnt
    # For the multivariate normal, if the user wants to generate the grids based on joint distribution, the user needs to provide the globalGrid for all corresponding variables
    else:
      globGridsCount = {}
      dimInfo = self.gridEntity.returnParameter("dimInfo")
      for val in dimInfo.values():
        if val[-1] is not None and val[-1] not in globGridsCount.keys(): globGridsCount[val[-1]] = 0
        globGridsCount[val[-1]] += 1
      diff = -sum(globGridsCount.values())+len(globGridsCount.keys())
      tempFillingCheck = [[None]*(self.pointByVar-1)]*(len(self.gridEntity.returnParameter("dimensionNames"))+diff) #for all variables
      self.sampledCoordinate = [[None]*len(self.axisName)]*(self.pointByVar-1)
      for i in range(len(tempFillingCheck)): tempFillingCheck[i]  = Distributions.randomPermutation(list(range(self.pointByVar-1)),self) #pick a random interval sequence
      cnt = 0
      mappingIdVarName = {}
      for varName in self.axisName:
        if varName not in dimInfo.keys(): mappingIdVarName[varName] = cnt
        else:
          for addKey,value in dimInfo.items():
            if value[1] == dimInfo[varName][1] and addKey not in mappingIdVarName.keys(): mappingIdVarName[addKey] = cnt
        if len(mappingIdVarName.keys()) == len(self.axisName): break
        cnt +=1

    for nPoint in range(self.pointByVar-1): self.sampledCoordinate[nPoint]= [tempFillingCheck[mappingIdVarName[varName]][nPoint] for varName in self.axisName]
    if self.restartData:
      self.counter+=len(self.restartData)
      self.raiseAMessage('Number of points from restart: %i' %self.counter)
      self.raiseAMessage('Number of points needed:       %i' %(self.limit-self.counter))

  def localGenerateInput(self,model,myInput):
    """
    Will generate an input and associate it with a probability
      @ In, model, the model to evaluate
      @ In, myInput, list of original inputs (unused)
      @ Out, None
    """
    varCount = 0
    self.inputInfo['distributionName'] = {} #Used to determine which distribution to change if needed.
    self.inputInfo['distributionType'] = {} #Used to determine which distribution type is used
    weight = 1.0
    for varName in self.axisName:
      # new implementation for ND LHS
      if not "<distribution>" in varName:
        if self.variables2distributionsMapping[varName]['totDim']>1 and self.variables2distributionsMapping[varName]['reducedDim'] == 1:    # to avoid double count of weight for ND distribution; I need to count only one variable instaed of N
          if self.variablesTransformationDict:
            distName = self.variables2distributionsMapping[varName]['name']
            for distVarName in self.distributions2variablesMapping[distName]:
              for kkey in utils.first(distVarName.keys()).strip().split(','):
                self.inputInfo['distributionName'][kkey] = self.toBeSampled[varName]
                self.inputInfo['distributionType'][kkey] = self.distDict[varName].type
            ndCoordinate = np.zeros(len(self.distributions2variablesMapping[distName]))
            dxs = np.zeros(len(self.distributions2variablesMapping[distName]))
            centerCoordinate = np.zeros(len(self.distributions2variablesMapping[distName]))
            positionList = self.distributions2variablesIndexList[distName]
            for var in self.distributions2variablesMapping[distName]:
              # if the varName is a comma separated list of strings the user wants to sample the comma separated variables with the same sampled value => link the value to all comma separated variables
              variable = utils.first(var.keys()).strip()
              position = utils.first(var.values())
              upper = self.gridEntity.returnShiftedCoordinate(self.gridEntity.returnIteratorIndexes(),{variable:self.sampledCoordinate[self.counter-1][varCount]+1})[variable]
              lower = self.gridEntity.returnShiftedCoordinate(self.gridEntity.returnIteratorIndexes(),{variable:self.sampledCoordinate[self.counter-1][varCount]})[variable]
              varCount += 1
              if self.gridInfo[variable] == 'CDF':
                coordinate = lower + (upper-lower)*Distributions.random()
                ndCoordinate[positionList.index(position)] = self.distDict[variable].inverseMarginalDistribution(coordinate,variable)
                dxs[positionList.index(position)] = self.distDict[variable].inverseMarginalDistribution(max(upper,lower),variable)-self.distDict[variable].inverseMarginalDistribution(min(upper,lower),variable)
                centerCoordinate[positionList.index(position)] = (self.distDict[variable].inverseMarginalDistribution(upper,variable)+self.distDict[variable].inverseMarginalDistribution(lower,variable))/2.0
                for kkey in variable.strip().split(','):
                  self.values[kkey] = ndCoordinate[positionList.index(position)]
                  self.inputInfo['upper'][kkey] = self.distDict[variable].inverseMarginalDistribution(max(upper,lower),variable)
                  self.inputInfo['lower'][kkey] = self.distDict[variable].inverseMarginalDistribution(min(upper,lower),variable)
              elif self.gridInfo[variable] == 'value':
                dxs[positionList.index(position)] = max(upper,lower) - min(upper,lower)
                centerCoordinate[positionList.index(position)] = (upper + lower)/2.0
                coordinateCdf = self.distDict[variable].marginalCdf(lower) + (self.distDict[variable].marginalCdf(upper) - self.distDict[variable].marginalCdf(lower))*Distributions.random()
                coordinate = self.distDict[variable].inverseMarginalDistribution(coordinateCdf,variable)
                ndCoordinate[positionList.index(position)] = coordinate
                for kkey in variable.strip().split(','):
                  self.values[kkey] = coordinate
                  self.inputInfo['upper'][kkey] = max(upper,lower)
                  self.inputInfo['lower'][kkey] = min(upper,lower)
            self.inputInfo['ProbabilityWeight-'+varName.replace(",","!")] = self.distDict[varName].cellIntegral(centerCoordinate,dxs)
            weight *= self.inputInfo['ProbabilityWeight-'+varName.replace(",","!")]
            self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(ndCoordinate)
          else:
            if self.gridInfo[varName] == 'CDF':
              upper = self.gridEntity.returnShiftedCoordinate(self.gridEntity.returnIteratorIndexes(),{varName:self.sampledCoordinate[self.counter-1][varCount]+1})[varName]
              lower = self.gridEntity.returnShiftedCoordinate(self.gridEntity.returnIteratorIndexes(),{varName:self.sampledCoordinate[self.counter-1][varCount]})[varName]
              varCount += 1
              coordinate = lower + (upper-lower)*Distributions.random()
              gridCoordinate, distName =  self.distDict[varName].ppf(coordinate), self.variables2distributionsMapping[varName]['name']
              for distVarName in self.distributions2variablesMapping[distName]:
                for kkey in utils.first(distVarName.keys()).strip().split(','):
                  self.inputInfo['distributionName'][kkey], self.inputInfo['distributionType'][kkey], self.values[kkey] = self.toBeSampled[varName], self.distDict[varName].type, np.atleast_1d(gridCoordinate)[distVarName.values()[0]-1]
              # coordinate stores the cdf values, we need to compute the pdf for SampledVarsPb
              self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(np.atleast_1d(gridCoordinate).tolist())
              weight *= max(upper,lower) - min(upper,lower)
              self.inputInfo['ProbabilityWeight-'+varName.replace(",","!")] = max(upper,lower) - min(upper,lower)
            else: self.raiseAnError(IOError,"Since the globalGrid is defined, the Stratified Sampler is only working when the sampling is performed on a grid on a CDF. However, the user specifies the grid on " + self.gridInfo[varName])
      if ("<distribution>" in varName) or self.variables2distributionsMapping[varName]['totDim']==1:   # 1D variable
        # if the varName is a comma separated list of strings the user wants to sample the comma separated variables with the same sampled value => link the value to all comma separated variables
        upper = self.gridEntity.returnShiftedCoordinate(self.gridEntity.returnIteratorIndexes(),{varName:self.sampledCoordinate[self.counter-1][varCount]+1})[varName]
        lower = self.gridEntity.returnShiftedCoordinate(self.gridEntity.returnIteratorIndexes(),{varName:self.sampledCoordinate[self.counter-1][varCount]})[varName]
        varCount += 1
        if self.gridInfo[varName] =='CDF':
          coordinate = lower + (upper-lower)*Distributions.random()
          ppfValue = self.distDict[varName].ppf(coordinate)
          ppfLower = self.distDict[varName].ppf(min(upper,lower))
          ppfUpper = self.distDict[varName].ppf(max(upper,lower))
          weight *= self.distDict[varName].cdf(ppfUpper) - self.distDict[varName].cdf(ppfLower)
          self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.distDict[varName].cdf(ppfUpper) - self.distDict[varName].cdf(ppfLower)
          self.inputInfo['SampledVarsPb'][varName]  = self.distDict[varName].pdf(ppfValue)
        elif self.gridInfo[varName] == 'value':
          coordinateCdf = self.distDict[varName].cdf(min(upper,lower)) + (self.distDict[varName].cdf(max(upper,lower))-self.distDict[varName].cdf(min(upper,lower)))*Distributions.random()
          if coordinateCdf == 0.0: self.raiseAWarning(IOError,"The grid lower bound and upper bound in value will generate ZERO cdf value!!!")
          coordinate = self.distDict[varName].ppf(coordinateCdf)
          weight *= self.distDict[varName].cdf(max(upper,lower)) - self.distDict[varName].cdf(min(upper,lower))
          self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.distDict[varName].cdf(max(upper,lower)) - self.distDict[varName].cdf(min(upper,lower))
          self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(coordinate)
        for kkey in varName.strip().split(','):
          self.inputInfo['distributionName'][kkey] = self.toBeSampled[varName]
          self.inputInfo['distributionType'][kkey] = self.distDict[varName].type
          if self.gridInfo[varName] =='CDF':
            self.values[kkey] = ppfValue
            self.inputInfo['upper'][kkey] = ppfUpper
            self.inputInfo['lower'][kkey] = ppfLower
          elif self.gridInfo[varName] =='value':
            self.values[kkey] = coordinate
            self.inputInfo['upper'][kkey] = max(upper,lower)
            self.inputInfo['lower'][kkey] = min(upper,lower)

    self.inputInfo['PointProbability'] = reduce(mul, self.inputInfo['SampledVarsPb'].values())
    self.inputInfo['ProbabilityWeight' ] = weight
    self.inputInfo['SamplerType'] = 'Stratified'
#
#
#
#
class DynamicEventTree(Grid):
  """
  DYNAMIC EVENT TREE Sampler (DET)
  """
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Grid.__init__(self)
    # Working directory (Path of the directory in which all the outputs,etc. are stored)
    self.workingDir                        = ""
    # (optional) if not present, the sampler will not change the relative keyword in the input file
    self.maxSimulTime                      = None
    # print the xml tree representation of the dynamic event tree calculation
    # see variable 'self.TreeInfo'
    self.printEndXmlSummary                = False
    # Dictionary of the probability bins for each distribution that have been
    #  inputted by the user ('distName':[Pb_Threshold_1, Pb_Threshold_2, ..., Pb_Threshold_n])
    self.branchProbabilities               = {}
    # Dictionary of the Values' bins for each distribution that have been
    #  inputted by the user ('distName':[Pb_Threshold_1, Pb_Threshold_2, ..., Pb_Threshold_n])
    # these are the invCDFs of the PBs inputted in branchProbabilities (if ProbabilityThresholds have been inputted)
    self.branchValues                      = {}
    # List of Dictionaries of the last probability bin level (position in the array) reached for each distribution ('distName':IntegerValue)
    # This container is a working dictionary. The branchedLevels are stored in the xml tree "self.TreeInfo" since they must track
    # the evolution of the dynamic event tree
    self.branchedLevel                     = []
    # Counter for the branch needs to be run after a calculation branched (it is a working variable)
    self.branchCountOnLevel                = 0
    # Dictionary tha contains the actual branching info
    # (i.e. distribution that triggered, values of the variables that need to be changed, etc)
    self.actualBranchInfo                  = {}
    # Parent Branch end time (It's a working variable used to set up the new branches need to be run.
    #   The new branches' start time will be the end time of the parent branch )
    self.actualEndTime                     = 0.0
    # Parent Branch end time step (It's a working variable used to set up the new branches need to be run.
    #  The end time step is used to construct the filename of the restart files needed for restart the new branch calculations)
    self.actualEndTs                       = 0
    # Xml tree object. It stored all the info regarding the DET. It is in continue evolution during a DET calculation
    self.TreeInfo                          = None
    # List of Dictionaries. It is a working variable used to store the information needed to create branches from a Parent Branch
    self.endInfo                           = []
    # Queue system. The inputs are waiting to be run are stored in this queue dictionary
    self.RunQueue                          = {}
    # identifiers of the inputs in queue (name of the history... for example DET_1,1,1)
    self.RunQueue['identifiers']           = []
    # Corresponding inputs
    self.RunQueue['queue']                 = []
    # mapping from jobID to rootname in TreeInfo {jobID:rootName}
    self.rootToJob                         = {}
    # dictionary of Hybrid Samplers available
    self.hybridSamplersAvail               = {'MonteCarlo':MonteCarlo,'Stratified':Stratified,'Grid':Grid}
    # dictionary of inputted hybridsamplers need to be applied
    self.hybridStrategyToApply             = {}
    # total number of hybridsampler samples (combination of all different hybridsampler strategy)
    self.hybridNumberSamplers              = 0
    # List of variables that represent the aleatory space
    self.standardDETvariables              = []
    # Dictionary of variables that represent the epistemic space (hybrid det). Format => {'epistemicVarName':{'HybridTree name':value}}
    self.epistemicVariables                = {}

  def _localWhatDoINeed(self):
    """
    This method is a local mirror of the general whatDoINeed method.
    It is implmented here because this Sampler requests special objects
    @ In , None, None
    @ Out, needDict, list of objects needed
    """
    needDict = Sampler._localWhatDoINeed(self)
    for hybridsampler in self.hybridStrategyToApply.values():
      preneedDict = hybridsampler.whatDoINeed()
      for key,value in preneedDict.items():
        if key not in needDict.keys(): needDict[key] = []
        needDict[key] = needDict[key] + value
    return needDict

  def localStillReady(self, ready): #,lastOutput=None
    """
    Function that inquires if there is at least an input the in the queue that
    needs to be run
    @ InOut, ready, boolean specifying whether the sampler is ready
    """
    self._endJobRunnable = max((len(self.RunQueue['queue']),1))
    if(len(self.RunQueue['queue']) != 0 or self.counter == 0): ready = True
    else:
      if self.printEndXmlSummary:
        myFile = open(os.path.join(self.workingDir,self.name + "_outputSummary.xml"),'w')
        for treeNode in self.TreeInfo.values(): treeNode.writeNodeTree(myFile)
        myFile.close()
      ready = False
    return ready

  def _retrieveParentNode(self,idj):
    """
    Grants access to the parent node of a particular job
    @ In, idj, the identifier of a job object
    @ Out, the parent node of the job linked to idj
    """
    if(idj == self.TreeInfo[self.rootToJob[idj]].getrootnode().name): parentNode = self.TreeInfo[self.rootToJob[idj]].getrootnode()
    else: parentNode = list(self.TreeInfo[self.rootToJob[idj]].getrootnode().iter(idj))[0]
    return parentNode

  def localFinalizeActualSampling(self,jobObject,model,myInput,genRunQueue=True):
    """
    General function (available to all samplers) that finalize the sampling
    calculation just ended. In this case (DET), The function reads the
    information from the ended calculation, updates the working variables, and
    creates the new inputs for the next branches
    @ In, jobObject: JobHandler Instance of the job (run) just finished
    @ In, model        : Model Instance... It may be a Code Instance, ROM, etc.
    @ In, myInput      : List of the original input files
    @ In, genRunQueue  : bool, generated Running queue at the end of the
                         finalization?
    @ Out, None
    """
    self.workingDir = model.workingDir

    # returnBranchInfo = self.__readBranchInfo(jobObject.output)
    # Get the parent element tree (xml object) to retrieve the information needed to create the new inputs
    parentNode = self._retrieveParentNode(jobObject.identifier)
    # set runEnded and running to true and false respectively
    parentNode.add('runEnded',True)
    parentNode.add('running',False)
    parentNode.add('endTime',self.actualEndTime)
    # Read the branch info from the parent calculation (just ended calculation)
    # This function stores the information in the dictionary 'self.actualBranchInfo'
    # If no branch info, this history is concluded => return
    if not self.__readBranchInfo(jobObject.output):
      parentNode.add('completedHistory', True)
      return False
    # Collect the branch info in a multi-level dictionary
    endInfo = {'endTime':self.actualEndTime,'endTimeStep':self.actualEndTs,'branchDist':list(self.actualBranchInfo.keys())[0]}
    endInfo['branchChangedParams'] = self.actualBranchInfo[endInfo['branchDist']]
    parentNode.add('actualEndTimeStep',self.actualEndTs)
    # # Get the parent element tree (xml object) to retrieve the information needed to create the new inputs
    # if(jobObject.identifier == self.TreeInfo[self.rootToJob[jobObject.identifier]].getrootnode().name): endInfo['parentNode'] = self.TreeInfo[self.rootToJob[jobObject.identifier]].getrootnode()
    # else: endInfo['parentNode'] = list(self.TreeInfo[self.rootToJob[jobObject.identifier]].getrootnode().iter(jobObject.identifier))[0]
    endInfo['parentNode'] = parentNode
    # get the branchedLevel dictionary
    branchedLevel = {}
    for distk, distpb in zip(endInfo['parentNode'].get('initiatorDistribution'),endInfo['parentNode'].get('PbThreshold')): branchedLevel[distk] = utils.index(self.branchProbabilities[distk],distpb)
    if not branchedLevel: self.raiseAnError(RuntimeError,'branchedLevel of node '+jobObject.identifier+'not found!')
    # Loop of the parameters that have been changed after a trigger gets activated
    for key in endInfo['branchChangedParams']:
      endInfo['n_branches'] = 1 + int(len(endInfo['branchChangedParams'][key]['actualValue']))
      if(len(endInfo['branchChangedParams'][key]['actualValue']) > 1):
        #  Multi-Branch mode => the resulting branches from this parent calculation (just ended)
        # will be more then 2
        # unchangedPb = probability (not conditional probability yet) that the event does not occur
        unchangedPb = 0.0
        try:
          # changed_pb = probability (not conditional probability yet) that the event A occurs and the final state is 'alpha' """
          for pb in xrange(len(endInfo['branchChangedParams'][key]['associatedProbability'])): unchangedPb = unchangedPb + endInfo['branchChangedParams'][key]['associatedProbability'][pb]
        except KeyError: pass
        if(unchangedPb <= 1): endInfo['branchChangedParams'][key]['unchangedPb'] = 1.0-unchangedPb
      else:
        # Two-Way mode => the resulting branches from this parent calculation (just ended) = 2
        if branchedLevel[endInfo['branchDist']] > len(self.branchProbabilities[endInfo['branchDist']])-1: pb = 1.0
        else: pb = self.branchProbabilities[endInfo['branchDist']][branchedLevel[endInfo['branchDist']]]
        endInfo['branchChangedParams'][key]['unchangedPb'] = 1.0 - pb
        endInfo['branchChangedParams'][key]['associatedProbability'] = [pb]

    self.branchCountOnLevel = 0
    # # set runEnded and running to true and false respectively
    # endInfo['parentNode'].add('runEnded',True)
    # endInfo['parentNode'].add('running',False)
    # endInfo['parentNode'].add('endTime',self.actualEndTime)
    # The branchedLevel counter is updated
    if branchedLevel[endInfo['branchDist']] < len(self.branchProbabilities[endInfo['branchDist']]): branchedLevel[endInfo['branchDist']] += 1
    # Append the parent branchedLevel (updated for the new branch/es) in the list tha contains them
    # (it is needed in order to avoid overlapping among info coming from different parent calculations)
    # When this info is used, they are popped out
    self.branchedLevel.append(branchedLevel)
    # Append the parent end info in the list tha contains them
    # (it is needed in order to avoid overlapping among info coming from different parent calculations)
    # When this info is used, they are popped out
    self.endInfo.append(endInfo)
    # Compute conditional probability
    self.computeConditionalProbability()
    # Create the inputs and put them in the runQueue dictionary (if genRunQueue is true)
    if genRunQueue: self._createRunningQueue(model,myInput)

    return True

  def computeConditionalProbability(self,index=None):
    """
    Function to compute Conditional probability of the branches that are going to be run.
    The conditional probabilities are stored in the self.endInfo object
    @ In, index: position in the self.endInfo list (optional). Default = 0
    @ Out, None
    """
    if not index: index = len(self.endInfo)-1
    # parentCondPb = associated conditional probability of the Parent branch
    #parentCondPb = 0.0
    try:
      parentCondPb = self.endInfo[index]['parentNode'].get('conditionalPbr')
      if not parentCondPb: parentCondPb = 1.0
    except KeyError: parentCondPb = 1.0
    # for all the branches the conditional pb is computed
    # unchangedConditionalPb = Conditional Probability of the branches in which the event has not occurred
    # changedConditionalPb   = Conditional Probability of the branches in which the event has occurred
    for key in self.endInfo[index]['branchChangedParams']:
      #try:
      self.endInfo[index]['branchChangedParams'][key]['changedConditionalPb'] = []
      self.endInfo[index]['branchChangedParams'][key]['unchangedConditionalPb'] = parentCondPb*float(self.endInfo[index]['branchChangedParams'][key]['unchangedPb'])
      for pb in range(len(self.endInfo[index]['branchChangedParams'][key]['associatedProbability'])): self.endInfo[index]['branchChangedParams'][key]['changedConditionalPb'].append(parentCondPb*float(self.endInfo[index]['branchChangedParams'][key]['associatedProbability'][pb]))
      #except? pass
    return

  def __readBranchInfo(self,outBase=None):
    """
    Function to read the Branching info that comes from a Model
    The branching info (for example, distribution that triggered, parameters must be changed, etc)
    are supposed to be in a xml format
    @ In, outBase: is the output root that, if present, is used to construct the file name the function is going
                    to try reading.
    @ Out, boolean: true if the info are present (a set of new branches need to be run), false if the actual parent calculation reached an end point
    """
    # Remove all the elements from the info container
    del self.actualBranchInfo
    branchPresent = False
    self.actualBranchInfo = {}
    # Construct the file name adding the outBase root if present
    if outBase: filename = outBase + "_actual_branch_info.xml"
    else: filename = "actual_branch_info.xml"
    if not os.path.isabs(filename): filename = os.path.join(self.workingDir,filename)
    if not os.path.exists(filename):
      self.raiseADebug('branch info file ' + os.path.basename(filename) +' has not been found. => No Branching.')
      return branchPresent
    # Parse the file and create the xml element tree object
    #try:
    branchInfoTree = ET.parse(filename)
    self.raiseADebug('Done parsing '+filename)
    root = branchInfoTree.getroot()
    # Check if endTime and endTimeStep (time step)  are present... In case store them in the relative working vars
    #try: #Branch info written out by program, so should always exist.
    self.actualEndTime = float(root.attrib['end_time'])
    self.actualEndTs   = int(root.attrib['end_ts'])
    #except? pass
    # Store the information in a dictionary that has as keywords the distributions that triggered
    for node in root:
      if node.tag == "Distribution_trigger":
        distName = node.attrib['name'].strip()
        self.actualBranchInfo[distName] = {}
        for child in node:
          self.actualBranchInfo[distName][child.text.strip()] = {'varType':child.attrib['type'].strip(),'actualValue':child.attrib['actual_value'].strip().split(),'oldValue':child.attrib['old_value'].strip()}
          if 'probability' in child.attrib:
            asPb = child.attrib['probability'].strip().split()
            self.actualBranchInfo[distName][child.text.strip()]['associatedProbability'] = []
            #self.actualBranchInfo[distName][child.text.strip()]['associatedProbability'].append(float(asPb))
            for index in range(len(asPb)): self.actualBranchInfo[distName][child.text.strip()]['associatedProbability'].append(float(asPb[index]))
      # we exit the loop here, because only one trigger at the time can be handled  right now
      break
    # remove the file
    os.remove(filename)
    branchPresent = True
    return branchPresent

  def _createRunningQueueBeginOne(self,rootTree,branchedLevel, model,myInput):
    """
    Method to generate the running internal queue for one point in the epistemic
    space. It generates the initial information to instantiate the root of a
    Deterministic Dynamic Event Tree.
    @ In, rootTree, TreeStructure object, the rootTree of the single coordinate in
          the epistemic space.
    @ In, branchedLevel, dict, dictionary of the levels reached by the rootTree
          mapped in the internal grid dictionary (self.branchProbabilities)
    @ In, model, Models object, the model that is used to explore the input space
          (e.g. a code, like RELAP-7)
    @ In, myInput, list, list of inputs for the Models object (passed through the
          Steps XML block)
    @ Out, None
    """
    precSampled = rootTree.getrootnode().get('hybridsamplerCoordinate')
    rootnode    =  rootTree.getrootnode()
    rname       = rootnode.name
    rootnode.add('completedHistory', False)
    # Fill th values dictionary in
    if precSampled: self.inputInfo['hybridsamplerCoordinate'  ] = copy.deepcopy(precSampled)
    self.inputInfo['prefix'                    ] = rname.encode()
    self.inputInfo['initiatorDistribution'     ] = []
    self.inputInfo['PbThreshold'               ] = []
    self.inputInfo['ValueThreshold'            ] = []
    self.inputInfo['branchChangedParam'        ] = [b'None']
    self.inputInfo['branchChangedParamValue'   ] = [b'None']
    self.inputInfo['startTime'                 ] = -sys.float_info.max
    self.inputInfo['endTimeStep'               ] = 0
    self.inputInfo['parentID'                  ] = 'root'
    self.inputInfo['conditionalPb'             ] = [1.0]
    self.inputInfo['conditionalPbr'            ] = 1.0
    for key in self.branchProbabilities.keys():self.inputInfo['initiatorDistribution'].append(key.encode())
    for key in self.branchProbabilities.keys():self.inputInfo['PbThreshold'].append(self.branchProbabilities[key][branchedLevel[key]])
    for key in self.branchProbabilities.keys():self.inputInfo['ValueThreshold'].append(self.branchValues[key][branchedLevel[key]])
    for varname in self.standardDETvariables:
      self.inputInfo['SampledVars'  ][varname] = self.branchValues[self.toBeSampled[varname]][branchedLevel[self.toBeSampled[varname]]]
      self.inputInfo['SampledVarsPb'][varname] = self.branchProbabilities[self.toBeSampled[varname]][branchedLevel[self.toBeSampled[varname]]]
    if precSampled:
      for precSample in precSampled:
        self.inputInfo['SampledVars'  ].update(precSample['SampledVars'])
        self.inputInfo['SampledVarsPb'].update(precSample['SampledVarsPb'])
    self.inputInfo['PointProbability' ] = reduce(mul, self.inputInfo['SampledVarsPb'].values())
    self.inputInfo['ProbabilityWeight'] = self.inputInfo['PointProbability' ]

    if(self.maxSimulTime): self.inputInfo['endTime'] = self.maxSimulTime
    # Call the model function "createNewInput" with the "values" dictionary just filled.
    # Add the new input path into the RunQueue system
    newInputs = model.createNewInput(myInput,self.type,**self.inputInfo)
    for key,value in self.inputInfo.items(): rootnode.add(key,value)
    self.RunQueue['queue'].append(newInputs)
    self.RunQueue['identifiers'].append(self.inputInfo['prefix'].encode())
    self.rootToJob[self.inputInfo['prefix']] = rname
    del newInputs
    self.counter += 1

  def _createRunningQueueBegin(self,model,myInput):
    """
    Method to generate the running internal queue for all the points in
    the epistemic space. It generates the initial information to
    instantiate the roots of all the N-D coordinates to construct multiple
    Deterministic Dynamic Event Trees.
    @ In, model, Models object, the model that is used to explore the input
          space (e.g. a code, like RELAP-7)
    @ In, myInput, list, list of inputs for the Models object (passed through
          the Steps XML block)
    @ Out, None
    """
    # We construct the input for the first DET branch calculation'
    # Increase the counter
    # The root name of the xml element tree is the starting name for all the branches
    # (this root name = the user defined sampler name)
    # Get the initial branchedLevel dictionary (=> the list gets empty)
    branchedLevel = self.branchedLevel.pop(0)
    for rootTree in self.TreeInfo.values(): self._createRunningQueueBeginOne(rootTree,branchedLevel, model,myInput)
    return

  def _createRunningQueueBranch(self,model,myInput,forceEvent=False):
    """ Method to generate the running internal queue right after a branch occurred
    It generates the the information to insatiate the branches' continuation of the Deterministic Dynamic Event Tree
    @ In, model, Models object, the model that is used to explore the input space (e.g. a code, like RELAP-7)
    @ In, myInput, list, list of inputs for the Models object (passed through the Steps XML block)
    @ In, forceEvent, boolean, if True the events are forced to happen (basically, the "unchanged event" is not created at all)
    """
    # The first DET calculation branch has already been run'
    # Start the manipulation:

    #  Pop out the last endInfo information and the branchedLevel
    branchedLevelParent     = self.branchedLevel.pop(0)
    endInfo                 = self.endInfo.pop(0)
    self.branchCountOnLevel = 0 #?
    # n_branches = number of branches need to be run
    nBranches = endInfo['n_branches']
    # Check if the distribution that just triggered hitted the last probability threshold .
    # In case we create a number of branches = endInfo['n_branches'] - 1 => the branch in
    # which the event did not occur is not going to be tracked
    if branchedLevelParent[endInfo['branchDist']] >= len(self.branchProbabilities[endInfo['branchDist']]):
      self.raiseADebug('Branch ' + endInfo['parentNode'].get('name') + ' hit last Threshold for distribution ' + endInfo['branchDist'])
      self.raiseADebug('Branch ' + endInfo['parentNode'].get('name') + ' is dead end.')
      self.branchCountOnLevel = 1
      nBranches -= 1
    else:
      if forceEvent == True:
        self.branchCountOnLevel = 1
        nBranches -= 1
    # Loop over the branches for which the inputs must be created
    for _ in range(nBranches):
      del self.inputInfo
      self.counter += 1
      self.branchCountOnLevel += 1
      branchedLevel = branchedLevelParent
      # Get Parent node name => the branch name is creating appending to this name  a comma and self.branchCountOnLevel counter
      rname = endInfo['parentNode'].get('name') + '-' + str(self.branchCountOnLevel)

      # create a subgroup that will be appended to the parent element in the xml tree structure
      subGroup = ETS.Node(rname.encode())
      subGroup.add('parent', endInfo['parentNode'].get('name'))
      subGroup.add('name', rname)
      subGroup.add('completedHistory', False)
      # condPbUn = conditional probability event not occur
      # condPbC  = conditional probability event/s occur/s
      condPbUn = 0.0
      condPbC  = 0.0
      # Loop over  branchChangedParams (events) and start storing information,
      # such as conditional pb, variable values, into the xml tree object
      for key in endInfo['branchChangedParams'].keys():
        subGroup.add('branchChangedParam',key)
        if self.branchCountOnLevel != 1:
          subGroup.add('branchChangedParamValue',endInfo['branchChangedParams'][key]['actualValue'][self.branchCountOnLevel-2])
          subGroup.add('branchChangedParamPb',endInfo['branchChangedParams'][key]['associatedProbability'][self.branchCountOnLevel-2])
          condPbC = condPbC + endInfo['branchChangedParams'][key]['changedConditionalPb'][self.branchCountOnLevel-2]
        else:
          subGroup.add('branchChangedParamValue',endInfo['branchChangedParams'][key]['oldValue'])
          subGroup.add('branchChangedParamPb',endInfo['branchChangedParams'][key]['unchangedPb'])
          condPbUn =  condPbUn + endInfo['branchChangedParams'][key]['unchangedConditionalPb']
      # add conditional probability
      if self.branchCountOnLevel != 1: subGroup.add('conditionalPbr',condPbC)
      else: subGroup.add('conditionalPbr',condPbUn)
      # add initiator distribution info, start time, etc.
      subGroup.add('initiatorDistribution',endInfo['branchDist'])
      subGroup.add('startTime', endInfo['parentNode'].get('endTime'))
      # initialize the endTime to be equal to the start one... It will modified at the end of this branch
      subGroup.add('endTime', endInfo['parentNode'].get('endTime'))
      # add the branchedLevel dictionary to the subgroup
      if self.branchCountOnLevel != 1: branchedLevel[endInfo['branchDist']] = branchedLevel[endInfo['branchDist']] - 1
      # branch calculation info... running, queue, etc are set here
      subGroup.add('runEnded',False)
      subGroup.add('running',False)
      subGroup.add('queue',True)
      #  subGroup.set('restartFileRoot',endInfo['restartRoot'])
      # Append the new branch (subgroup) info to the parentNode in the tree object
      endInfo['parentNode'].appendBranch(subGroup)
      # Fill the values dictionary that will be passed into the model in order to create an input
      # In this dictionary the info for changing the original input is stored
      self.inputInfo = {'prefix':rname.encode(),'endTimeStep':endInfo['endTimeStep'],
                'branchChangedParam':[subGroup.get('branchChangedParam')],
                'branchChangedParamValue':[subGroup.get('branchChangedParamValue')],
                'conditionalPb':[subGroup.get('conditionalPbr')],
                'startTime':endInfo['parentNode'].get('endTime'),
                'parentID':subGroup.get('parent')}
      # add the newer branch name to the map
      self.rootToJob[rname] = self.rootToJob[subGroup.get('parent')]
      # check if it is a preconditioned DET sampling, if so add the relative information
      precSampled = endInfo['parentNode'].get('hybridsamplerCoordinate')
      if precSampled:
        self.inputInfo['hybridsamplerCoordinate'] = copy.deepcopy(precSampled)
        subGroup.add('hybridsamplerCoordinate', precSampled)
      # Check if the distribution that just triggered hitted the last probability threshold .
      #  In this case there is not a probability threshold that needs to be added in the input
      #  for this particular distribution
      if not (branchedLevel[endInfo['branchDist']] >= len(self.branchProbabilities[endInfo['branchDist']])):
        self.inputInfo['initiatorDistribution'] = [endInfo['branchDist']]
        self.inputInfo['PbThreshold'           ] = [self.branchProbabilities[endInfo['branchDist']][branchedLevel[endInfo['branchDist']]]]
        self.inputInfo['ValueThreshold'        ] = [self.branchValues[endInfo['branchDist']][branchedLevel[endInfo['branchDist']]]]
      #  For the other distributions, we put the unbranched thresholds
      #  Before adding these thresholds, check if the keyword 'initiatorDistribution' is present...
      #  (In the case the previous if statement is true, this keyword is not present yet
      #  Add it otherwise
      if not ('initiatorDistribution' in self.inputInfo.keys()):
        self.inputInfo['initiatorDistribution' ] = []
        self.inputInfo['PbThreshold'           ] = []
        self.inputInfo['ValueThreshold'        ] = []
      # Add the unbranched thresholds
      for key in self.branchProbabilities.keys():
        if not (key in endInfo['branchDist']) and (branchedLevel[key] < len(self.branchProbabilities[key])): self.inputInfo['initiatorDistribution'].append(key.encode())
      for key in self.branchProbabilities.keys():
        if not (key in endInfo['branchDist']) and (branchedLevel[key] < len(self.branchProbabilities[key])):
          self.inputInfo['PbThreshold'   ].append(self.branchProbabilities[key][branchedLevel[key]])
          self.inputInfo['ValueThreshold'].append(self.branchValues[key][branchedLevel[key]])
      self.inputInfo['SampledVars']   = {}
      self.inputInfo['SampledVarsPb'] = {}
      for varname in self.standardDETvariables:
        self.inputInfo['SampledVars'][varname]   = self.branchValues[self.toBeSampled[varname]][branchedLevel[self.toBeSampled[varname]]]
        self.inputInfo['SampledVarsPb'][varname] = self.branchProbabilities[self.toBeSampled[varname]][branchedLevel[self.toBeSampled[varname]]]
      if precSampled:
        for precSample in precSampled:
          self.inputInfo['SampledVars'  ].update(precSample['SampledVars'])
          self.inputInfo['SampledVarsPb'].update(precSample['SampledVarsPb'])
      self.inputInfo['PointProbability' ] = reduce(mul, self.inputInfo['SampledVarsPb'].values())*subGroup.get('conditionalPbr')
      self.inputInfo['ProbabilityWeight'] = self.inputInfo['PointProbability' ]
      # Call the model function  "createNewInput" with the "values" dictionary just filled.
      # Add the new input path into the RunQueue system
      self.RunQueue['queue'].append(model.createNewInput(myInput,self.type,**self.inputInfo))
      self.RunQueue['identifiers'].append(self.inputInfo['prefix'])
      for key,value in self.inputInfo.items(): subGroup.add(key,value)
      popped = endInfo.pop('parentNode')
      subGroup.add('endInfo',copy.deepcopy(endInfo))
      endInfo['parentNode'] = popped
      del branchedLevel

  def _createRunningQueue(self, model, myInput, forceEvent=False):
    """
    Function to create and append new inputs to the queue. It uses all the containers have been updated by the previous functions
    @ In, model  : Model instance. It can be a Code type, ROM, etc.
    @ In, myInput: List of the original inputs

    @ Out, None
    """
    if self.counter >= 1:
      # The first DET calculation branch has already been run
      # Start the manipulation:
      #  Pop out the last endInfo information and the branchedLevel
      self._createRunningQueueBranch(model, myInput, forceEvent)
    else:
      # We construct the input for the first DET branch calculation'
      self._createRunningQueueBegin(model, myInput)
    return

  def __getQueueElement(self):
    """
    Function to get an input from the internal queue system
    @ In, None
    @ Out, jobInput: First input in the queue
    """
    # Pop out the first input in queue
    jobInput  = self.RunQueue['queue'      ].pop(0)
    jobId     = self.RunQueue['identifiers'].pop(0)
    #set running flags in self.TreeInfo
    root = self.TreeInfo[self.rootToJob[jobId]].getrootnode()
    # Update the run information flags
    if (root.name == jobId):
      root.add('runEnded',False)
      root.add('running',True)
      root.add('queue',False)
    else:
      subElm = list(root.iter(jobId))[0]
      if(subElm):
        subElm.add('runEnded',False)
        subElm.add('running',True)
        subElm.add('queue',False)
    return jobInput

  def generateInput(self,model,oldInput):
    """
    This method needs to be overwritten by the Dynamic Event Tree Sampler, since the input creation strategy is completely different with the respect the other samplers
    @in model   : it is the instance of a model
    @in oldInput: [] a list of the original needed inputs for the model (e.g. list of files, etc. etc)
    @return     : [] containing the new inputs -in reality it is the model that returns this, the Sampler generates the values to be placed in the model input
    """
    return self.localGenerateInput(model, oldInput)

  def localGenerateInput(self,model,myInput):
    """
    Will generate an input and associate it with a probability
      @ In, model, the model to evaluate
      @ In, myInput, list of original inputs (unused)
      @ Out, None
    """
    #self._endJobRunnable = max([len(self.RunQueue['queue']),1])
    if self.counter <= 1:
      # If first branch input, create the queue
      self._createRunningQueue(model, myInput)
    # retrieve the input from the queue
    newerinput = self.__getQueueElement()
    # If no inputs are present in the queue => a branch is finished
    if not newerinput: self.raiseADebug('A Branch ended!')
    return newerinput

  def _generateDistributions(self,availableDist,availableFunc):
    """
      Generates the distrbutions and functions.
      @ In, availDist, dict of distributions
      @ In, availDist, dict of functions
      @ Out, None
    """
    Grid._generateDistributions(self,availableDist,availableFunc)
    for hybridsampler in self.hybridStrategyToApply.values(): hybridsampler._generateDistributions(availableDist,availableFunc)

  def localInputAndChecks(self,xmlNode):
    """
    Class specific inputs will be read here and checked for validity.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    """
    self._localInputAndChecksDET(xmlNode)
    self._localInputAndChecksHybrid(xmlNode)

  def _localInputAndChecksDET(self,xmlNode):
    """
    Class specific inputs will be read here and checked for validity.
    This method reads the standard DET portion only (no hybrid)
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    """
    Grid.localInputAndChecks(self,xmlNode)
    if 'printEndXmlSummary' in xmlNode.attrib.keys():
      if xmlNode.attrib['printEndXmlSummary'].lower() in utils.stringsThatMeanTrue(): self.printEndXmlSummary = True
      else: self.printEndXmlSummary = False
    if 'maxSimulationTime' in xmlNode.attrib.keys():
      try:    self.maxSimulTime = float(xmlNode.attrib['maxSimulationTime'])
      except (KeyError,NameError): self.raiseAnError(IOError,'Can not convert maxSimulationTime in float number!!!')
    branchedLevel, error_found = {}, False
    gridInfo = self.gridEntity.returnParameter("gridInfo")
    errorFound = False
    for keyk in self.axisName:
      branchedLevel[self.toBeSampled[keyk]] = 0
      self.standardDETvariables.append(keyk)
      if self.gridInfo[keyk] == 'CDF':
        self.branchProbabilities[self.toBeSampled[keyk]] = gridInfo[keyk][2]
        self.branchProbabilities[self.toBeSampled[keyk]].sort(key=float)
        if max(self.branchProbabilities[self.toBeSampled[keyk]]) > 1:
          self.raiseAWarning("One of the Thresholds for distribution " + str(gridInfo[keyk][2]) + " is > 1")
          errorFound = True
          for index in range(len(sorted(self.branchProbabilities[self.toBeSampled[keyk]], key=float))):
            if sorted(self.branchProbabilities[self.toBeSampled[keyk]], key=float).count(sorted(self.branchProbabilities[self.toBeSampled[keyk]], key=float)[index]) > 1:
              self.raiseAWarning("In distribution " + str(self.toBeSampled[keyk]) + " the Threshold " + str(sorted(self.branchProbabilities[self.toBeSampled[keyk]], key=float)[index])+" appears multiple times!!")
              errorFound = True
      else:
        self.branchValues[self.toBeSampled[keyk]] = gridInfo[keyk][2]
        self.branchValues[self.toBeSampled[keyk]].sort(key=float)
        for index in range(len(sorted(self.branchValues[self.toBeSampled[keyk]], key=float))):
          if sorted(self.branchValues[self.toBeSampled[keyk]], key=float).count(sorted(self.branchValues[self.toBeSampled[keyk]], key=float)[index]) > 1:
            self.raiseAWarning("In distribution " + str(self.toBeSampled[keyk]) + " the Threshold " + str(sorted(self.branchValues[self.toBeSampled[keyk]], key=float)[index])+" appears multiple times!!")
            errorFound = True
    if errorFound: self.raiseAnError(IOError,"In sampler named " + self.name+' Errors have been found!' )
    # Append the branchedLevel dictionary in the proper list
    self.branchedLevel.append(branchedLevel)

  def _localInputAndChecksHybrid(self,xmlNode):
    """
    Class specific inputs will be read here and checked for validity.
    This method reads the hybrid det portion only
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    """
    for child in xmlNode:
      if child.tag == 'HybridSampler':
        if not 'type' in child.attrib.keys()                          : self.raiseAnError(IOError,'Not found attribute type in hybridsamplerSampler block!')
        if child.attrib['type'] in self.hybridStrategyToApply.keys()  : self.raiseAnError(IOError,'Hybrid Sampler type '+child.attrib['type'] + ' already inputted!')
        if child.attrib['type'] not in self.hybridSamplersAvail.keys(): self.raiseAnError(IOError,'Hybrid Sampler type ' +child.attrib['type'] + ' unknown. Available are '+ ','.join(self.hybridSamplersAvail.keys()) + '!')
        self.hybridNumberSamplers = 1
        # the user can decided how to sample the epistemic
        self.hybridStrategyToApply[child.attrib['type']] = self.hybridSamplersAvail[child.attrib['type']]()
        # give the hybridsampler sampler the message handler
        self.hybridStrategyToApply[child.attrib['type']].setMessageHandler(self.messageHandler)
        # make the hybridsampler sampler read  its own xml block
        self.hybridStrategyToApply[child.attrib['type']]._readMoreXML(child)
        # store the variables that represent the epistemic space
        self.epistemicVariables.update(dict.fromkeys(self.hybridStrategyToApply[child.attrib['type']].toBeSampled.keys(),{}))

  def localAddInitParams(self,tempDict):
    """
    Appends a given dictionary with class specific member variables and their
    associated initialized values.
    @ InOut, tempDict: The dictionary where we will add the initialization
                       parameters specific to this Sampler.
    """
    for key in self.branchProbabilities.keys(): tempDict['Probability Thresholds for dist ' + str(key) + ' are: '] = [str(x) for x in self.branchProbabilities[key]]
    for key in self.branchValues.keys()       : tempDict['Values Thresholds for dist ' + str(key) + ' are: '] = [str(x) for x in self.branchValues[key]]

  def localAddCurrentSetting(self,tempDict):
    """
    Appends a given dictionary with class specific information regarding the
    current status of the object.
    @ InOut, tempDict: The dictionary where we will add the parameters specific
                       to this Sampler and their associated values.
    """
    tempDict['actual threshold levels are '] = self.branchedLevel[0]

  def localInitialize(self):
    """
    Will perform all initialization specific to this Sampler. This will be
    called at the beginning of each Step where this object is used. See base
    class for more details.
    @ In None
    @ Out None
    """
    if len(self.hybridStrategyToApply.keys()) > 0: hybridlistoflist = []
    for cnt, preckey  in enumerate(self.hybridStrategyToApply.keys()):
      hybridsampler =  self.hybridStrategyToApply[preckey]
      hybridlistoflist.append([])
      hybridsampler.initialize()
      self.hybridNumberSamplers *= hybridsampler.limit
      while hybridsampler.amIreadyToProvideAnInput():
        hybridsampler.counter +=1
        hybridsampler.localGenerateInput(None,None)
        hybridsampler.inputInfo['prefix'] = hybridsampler.counter
        hybridlistoflist[cnt].append(copy.deepcopy(hybridsampler.inputInfo))
    if self.hybridNumberSamplers > 0:
      self.raiseAMessage('Number of Hybrid Samples are ' + str(self.hybridNumberSamplers) + '!')
      hybridNumber = self.hybridNumberSamplers
      combinations = list(itertools.product(*hybridlistoflist))
    else: hybridNumber = 1
    self.TreeInfo = {}
    for precSample in range(hybridNumber):
      elm = ETS.Node(self.name + '_' + str(precSample+1))
      elm.add('name', self.name + '_'+ str(precSample+1))
      elm.add('startTime', str(0.0))
      # Initialize the endTime to be equal to the start one...
      # It will modified at the end of each branch
      elm.add('endTime', str(0.0))
      elm.add('runEnded',False)
      elm.add('running',True)
      elm.add('queue',False)
      # if preconditioned DET, add the sampled from hybridsampler samplers
      if self.hybridNumberSamplers > 0:
        elm.add('hybridsamplerCoordinate', combinations[precSample])
        for point in combinations[precSample]:
          for epistVar, val in point['SampledVars'].items(): self.epistemicVariables[epistVar][elm.get('name')] = val
      # The dictionary branchedLevel is stored in the xml tree too. That's because
      # the advancement of the thresholds must follow the tree structure
      elm.add('branchedLevel', self.branchedLevel[0])
      # Here it is stored all the info regarding the DET => we create the info for all the
      # branchings and we store them
      self.TreeInfo[self.name + '_' + str(precSample+1)] = ETS.NodeTree(elm)

    for key in self.branchProbabilities.keys():
      #kk = self.toBeSampled.values().index(key)
      self.branchValues[key] = [self.distDict[self.toBeSampled.keys()[self.toBeSampled.values().index(key)]].ppf(float(self.branchProbabilities[key][index])) for index in range(len(self.branchProbabilities[key]))]
    for key in self.branchValues.keys():
      #kk = self.toBeSampled.values().index(key)
      self.branchProbabilities[key] = [self.distDict[self.toBeSampled.keys()[self.toBeSampled.values().index(key)]].cdf(float(self.branchValues[key][index])) for index in range(len(self.branchValues[key]))]
    self.limit = sys.maxsize
#
#
#
#
class AdaptiveDET(DynamicEventTree, LimitSurfaceSearch):
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    DynamicEventTree.__init__(self)     # init DET
    LimitSurfaceSearch.__init__(self)   # init Adaptive
    self.detAdaptMode         = 1       # Adaptive Dynamic Event Tree method (=1 -> DynamicEventTree as hybridsampler and subsequent LimitSurfaceSearch,=2 -> DynamicEventTree online adaptive)
    self.noTransitionStrategy = 1       # Strategy in case no transitions have been found by DET (1 = 'Probability MC', 2 = Increase the grid exploration)
    self.insertAdaptBPb       = True    # Add Probabability THs requested by adaptive in the initial grid (default = False)
    self.startAdaptive        = False   # Flag to trigger the begin of the adaptive limit surface search
    self.adaptiveReady        = False   # Flag to store the response of the LimitSurfaceSearch.localStillReady method
    self.investigatedPoints   = []      # List containing the points that have been already investigated
    self.completedHistCnt   = 1         # Counter of the completed histories
    self.hybridDETstrategy  = None      # Integer flag to turn the hybrid strategy on:
                                        # None -> No hybrid approach,
                                        # 1    -> the epistemic variables are going to be part of the limit surface search
                                        # 2    -> the epistemic variables are going to be treated by a normal hybrid DET approach and the LimitSurface search
                                        #         will be performed on each epistemic tree (n LimitSurfaces)
    self.foundEpistemicTree = False     # flag that testifies if an epistemic tree has been found (Adaptive Hybrid DET)
    self.actualHybridTree   = ''        # name of the root tree used in self.hybridDETstrategy=2 to check which Tree needs to be used for the current LS search
    self.sortedListOfHists  = []        # sorted list of histories

  @staticmethod
  def _checkIfRunnint(treeValues): return not treeValues['runEnded']
  @staticmethod
  def _checkEnded(treeValues): return treeValues['runEnded']
  @staticmethod
  def _checkCompleteHistory(treeValues): return treeValues['completedHistory']

  def _localWhatDoINeed(self):
    """
    This method is a local mirror of the general whatDoINeed method.
    It is implmented by the samplers that need to request special objects
    @ In , None, None
    @ Out, needDict, list of objects needed
    """
    adaptNeed = LimitSurfaceSearch._localWhatDoINeed(self)
    DETNeed   = DynamicEventTree._localWhatDoINeed(self)
    #adaptNeedInst = self.limitSurfaceInstances.values()[-1]._localWhatDoINeed()
    return dict(adaptNeed.items()+ DETNeed.items())

  def _checkIfStartAdaptive(self):
    """
    Function that checks if the adaptive needs to be started (mode 1)
    @ In, None
    @ Out, None
    """
    if not self.startAdaptive:
      self.startAdaptive = True
      for treer in self.TreeInfo.values():
        for _ in treer.iterProvidedFunction(self._checkIfRunnint):
          self.startAdaptive = False
          break
        if not self.startAdaptive: break

  def _checkClosestBranch(self):
    """
    Function that checks the closest branch already evaluated
    @ In, None
    @ Out, dict, key:gridPosition
    """
    # compute cdf of sampled vars
    lowerCdfValues = {}
    cdfValues         = {}
    self.raiseADebug("Check for closest branch:")
    self.raiseADebug("_"*50)
    for key,value in self.values.items():
      self.raiseADebug("Variable name   : "+str(key))
      self.raiseADebug("Distrbution name: "+str(self.toBeSampled[key]))
      if key not in self.epistemicVariables.keys():
        cdfValues[key] = self.distDict[key].cdf(value)
        lowerCdfValues[key] = utils.find_le(self.branchProbabilities[self.toBeSampled[key]],cdfValues[key])[0]
        self.raiseADebug("CDF value       : "+str(cdfValues[key]))
        self.raiseADebug("Lower CDF found : "+str(lowerCdfValues[key]))
      self.raiseADebug("_"*50)
    #if hybrid DET, we need to find the correct tree that matches the values of the epistemic
    if self.hybridDETstrategy is not None:
      self.foundEpistemicTree, treer, compareDict = False, None, dict.fromkeys(self.epistemicVariables.keys(),False)
      for tree in self.TreeInfo.values():
        epistemicVars = tree.getrootnode().get("hybridsamplerCoordinate")[0]['SampledVars']
        for key in self.epistemicVariables.keys(): compareDict[key] = utils.compare(epistemicVars[key],self.values[key])
        if all(compareDict.values()):
          # we found the right epistemic tree
          self.foundEpistemicTree, treer = True, tree
          break
    else: treer = self.TreeInfo.values()[0]

    # check if in the adaptive points already explored (if not push into the grid)
    if not self.insertAdaptBPb:
      candidatesBranch = []
      # check if adaptive point is better choice -> TODO: improve efficiency
      for invPoint in self.investigatedPoints:
        pbth = [invPoint[self.toBeSampled[key]] for key in cdfValues.keys()]
        if all(i <= pbth[cnt] for cnt,i in enumerate(cdfValues.values())): candidatesBranch.append(invPoint)
      if len(candidatesBranch) > 0:
        if None in lowerCdfValues.values(): lowerCdfValues = candidatesBranch[0]
        for invPoint in candidatesBranch:
          pbth = [invPoint[self.toBeSampled[key]] for key in cdfValues.keys()]
          if all(i >= pbth[cnt] for cnt,i in enumerate(lowerCdfValues.values())): lowerCdfValues = invPoint
    # Check if The adaptive point requested is outside the so far run grid; in case return None
    # In addition, if Adaptive Hybrid DET, if treer is None, we did not find any tree
    #              in the epistemic space => we need to create another one
    if None in lowerCdfValues.values() or treer is None:
      if self.hybridDETstrategy is not None: returnTuple = None, cdfValues, treer
      else                                 : returnTuple = None, cdfValues
      return returnTuple

    nntrain, mapping = None, {}
    for ending in treer.iterProvidedFunction(self._checkEnded):
      #already ended branches, create training set for nearest algorithm (take coordinates <= of cdfValues) -> TODO: improve efficiency
      pbth = [ending.get('SampledVarsPb')[key] for key in lowerCdfValues.keys()]
      if all(pbth[cnt] <= i for cnt,i in enumerate(lowerCdfValues.values())):
        if nntrain is None:
          nntrain = np.zeros((1,len(cdfValues.keys())))
          nntrain[0,:] = np.array(copy.copy(pbth))
        else: nntrain = np.concatenate((nntrain,np.atleast_2d(np.array(copy.copy(pbth)))),axis=0)
        mapping[nntrain.shape[0]] = ending
    if nntrain is not None:
      neigh = neighbors.NearestNeighbors(n_neighbors=len(mapping.keys()))
      neigh.fit(nntrain)
      valBranch = self._checkValidityOfBranch(neigh.kneighbors(lowerCdfValues.values()),mapping)
      if self.hybridDETstrategy is not None: returnTuple = valBranch,cdfValues,treer
      else                                 : returnTuple = valBranch,cdfValues
      return returnTuple
    else:
      if self.hybridDETstrategy is not None: return None,cdfValues,treer
      else                                 : return None,cdfValues

  def _checkValidityOfBranch(self,branchSet,mapping):
    """
    Function that checks if the nearest branches found by method _checkClosestBranch are valid
    @ In, tuple of branches
    @ In, dictionary of candidated branches
    @ Out, most valid branch (if noone found, return None)
    """
    validBranch   = None
    idOfBranches  = branchSet[1][-1]
    for closestBranch in idOfBranches:
      if not mapping[closestBranch+1].get('completedHistory'):
        validBranch = mapping[closestBranch+1]
        break
    return validBranch

  def _retrieveBranchInfo(self,branch):
    """
     Function that retrieves the key information from a branch to start a newer calculation
     @ In, branch
     @ Out, dictionary with those information
    """
    info = branch.getValues()
    info['actualBranchOnLevel'] = branch.numberBranches()
    info['parentNode']         = branch
    return info

  def _constructEndInfoFromBranch(self,model, myInput, info, cdfValues):
    """
    @ In, model, Models object, the model that is used to explore the input space (e.g. a code, like RELAP-7)
    @ In, myInput, list, list of inputs for the Models object (passed through the Steps XML block)
    @ In, info, dict, dictionary of information at the end of a branch (information collected by the method _retrieveBranchInfo)
    @ In, cdfValues, dict, dictionary of CDF thresholds reached by the branch that just ended.
    """
    endInfo = info['parentNode'].get('endInfo')
    del self.inputInfo
    self.counter           += 1
    self.branchCountOnLevel = info['actualBranchOnLevel']+1
    # Get Parent node name => the branch name is creating appending to this name  a comma and self.branchCountOnLevel counter
    rname = info['parentNode'].get('name') + '-' + str(self.branchCountOnLevel)
    info['parentNode'].add('completedHistory', False)
    self.raiseADebug(str(rname))
    bcnt = self.branchCountOnLevel
    while info['parentNode'].isAnActualBranch(rname):
      bcnt += 1
      rname = info['parentNode'].get('name') + '-' + str(bcnt)
    # create a subgroup that will be appended to the parent element in the xml tree structure
    subGroup = ETS.Node(rname)
    subGroup.add('parent', info['parentNode'].get('name'))
    subGroup.add('name', rname)
    self.raiseADebug('cond pb = '+str(info['parentNode'].get('conditionalPbr')))
    condPbC  = float(info['parentNode'].get('conditionalPbr'))

    # Loop over  branchChangedParams (events) and start storing information,
    # such as conditional pb, variable values, into the xml tree object
    if endInfo:
      for key in endInfo['branchChangedParams'].keys():
        subGroup.add('branchChangedParam',key)
        subGroup.add('branchChangedParamValue',endInfo['branchChangedParams'][key]['oldValue'][0])
        subGroup.add('branchChangedParamPb',endInfo['branchChangedParams'][key]['associatedProbability'][0])
    else:
      pass
    #condPbC = condPbC + copy.deepcopy(endInfo['branchChangedParams'][key]['unchangedConditionalPb'])
    # add conditional probability
    subGroup.add('conditionalPbr',condPbC)
    # add initiator distribution info, start time, etc.
    #subGroup.add('initiatorDistribution',copy.deepcopy(endInfo['branchDist']))
    subGroup.add('startTime', info['parentNode'].get('endTime'))
    # initialize the endTime to be equal to the start one... It will modified at the end of this branch
    subGroup.add('endTime', info['parentNode'].get('endTime'))
    # add the branchedLevel dictionary to the subgroup
    #branchedLevel[endInfo['branchDist']] = branchedLevel[endInfo['branchDist']] - 1
    # branch calculation info... running, queue, etc are set here
    subGroup.add('runEnded',False)
    subGroup.add('running',False)
    subGroup.add('queue',True)
    subGroup.add('completedHistory', False)
    # Append the new branch (subgroup) info to the parentNode in the tree object
    info['parentNode'].appendBranch(subGroup)
    # Fill the values dictionary that will be passed into the model in order to create an input
    # In this dictionary the info for changing the original input is stored
    self.inputInfo = {'prefix':rname,'endTimeStep':info['parentNode'].get('actualEndTimeStep'),
              'branchChangedParam':[subGroup.get('branchChangedParam')],
              'branchChangedParamValue':[subGroup.get('branchChangedParamValue')],
              'conditionalPb':[subGroup.get('conditionalPbr')],
              'startTime':info['parentNode'].get('endTime'),
              'parentID':subGroup.get('parent')}
    # add the newer branch name to the map
    self.rootToJob[rname] = self.rootToJob[subGroup.get('parent')]
    # check if it is a preconditioned DET sampling, if so add the relative information
    # precSampled = endInfo['parentNode'].get('hybridsamplerCoordinate')
    # if precSampled:
    #   self.inputInfo['hybridsamplerCoordinate'] = copy.deepcopy(precSampled)
    #   subGroup.add('hybridsamplerCoordinate', precSampled)
    # it exists only in case an hybridDET strategy is activated
    precSampled = info['parentNode'].get('hybridsamplerCoordinate')
    if precSampled:
      self.inputInfo['hybridsamplerCoordinate'  ] = copy.deepcopy(precSampled)
      subGroup.add('hybridsamplerCoordinate', copy.copy(precSampled))
    # The probability Thresholds are stored here in the cdfValues dictionary... We are sure that they are whitin the ones defined in the grid
    # check is not needed
    self.inputInfo['initiatorDistribution' ] = [self.toBeSampled[key] for key in cdfValues.keys()]
    self.inputInfo['PbThreshold'           ] = cdfValues.values()
    self.inputInfo['ValueThreshold'        ] = [self.distDict[key].ppf(value) for key,value in cdfValues.items()]
    self.inputInfo['SampledVars'           ] = {}
    self.inputInfo['SampledVarsPb'         ] = {}
    for varname in self.standardDETvariables:
      self.inputInfo['SampledVars'  ][varname] = self.distDict[varname].ppf(cdfValues[varname])
      self.inputInfo['SampledVarsPb'][varname] = cdfValues[varname]
    if precSampled:
      for precSample in precSampled:
        self.inputInfo['SampledVars'  ].update(precSample['SampledVars'])
        self.inputInfo['SampledVarsPb'].update(precSample['SampledVarsPb'])
    self.inputInfo['PointProbability' ] = reduce(mul, self.inputInfo['SampledVarsPb'].values())*subGroup.get('conditionalPbr')
    self.inputInfo['ProbabilityWeight'] = self.inputInfo['PointProbability' ]
    # Call the model function "createNewInput" with the "values" dictionary just filled.
    # Add the new input path into the RunQueue system
    self.RunQueue['queue'].append(model.createNewInput(myInput,self.type,**self.inputInfo))
    self.RunQueue['identifiers'].append(self.inputInfo['prefix'])
    for key,value in self.inputInfo.items(): subGroup.add(key,value)
    if endInfo: subGroup.add('endInfo',copy.deepcopy(endInfo))
    # Call the model function "createNewInput" with the "values" dictionary just filled.
    return

  def localStillReady(self,ready): #, lastOutput= None
    """
    Function that inquires if there is at least an input the in the queue that needs to be run
    @ InOut, ready, boolean
    @ Out, boolean
    """
    if self.counter == 0               : return     True
    if len(self.RunQueue['queue']) != 0: detReady = True
    else                               : detReady = False
    # since the RunQueue is empty, let's check if there are still branches running => if not => start the adaptive search
    self._checkIfStartAdaptive()
    if self.startAdaptive:
      #if self._endJobRunnable != 1: self._endJobRunnable = 1
      # retrieve the endHistory branches
      completedHistNames, finishedHistNames = [], []
      hybridTrees = self.TreeInfo.values() if self.hybridDETstrategy in [1,None] else [self.TreeInfo[self.actualHybridTree]]
      for treer in hybridTrees: # this needs to be solved
        for ending in treer.iterProvidedFunction(self._checkCompleteHistory):
          completedHistNames.append(self.lastOutput.getParam(typeVar='inout',keyword='none',nodeid=ending.get('name'),serialize=False))
          finishedHistNames.append(utils.first(completedHistNames[-1].keys()))
      # assemble a dictionary
      if len(completedHistNames) > self.completedHistCnt:
        # sort the list of histories
        self.sortedListOfHists.extend(list(set(finishedHistNames) - set(self.sortedListOfHists)))
        completedHistNames = [completedHistNames[finishedHistNames.index(elem)] for elem in self.sortedListOfHists]
        if len(completedHistNames[-1].values()) > 0:
          lastOutDict = {'inputs':{},'outputs':{}}
          for histd in completedHistNames:
            histdict = histd.values()[-1]
            for key in histdict['inputs' ].keys():
              if key not in lastOutDict['inputs'].keys(): lastOutDict['inputs'][key] = np.atleast_1d(histdict['inputs'][key])
              else                                      : lastOutDict['inputs'][key] = np.concatenate((np.atleast_1d(lastOutDict['inputs'][key]),np.atleast_1d(histdict['inputs'][key])))
            for key in histdict['outputs'].keys():
              if key not in lastOutDict['outputs'].keys(): lastOutDict['outputs'][key] = np.atleast_1d(histdict['outputs'][key])
              else                                       : lastOutDict['outputs'][key] = np.concatenate((np.atleast_1d(lastOutDict['outputs'][key]),np.atleast_1d(histdict['outputs'][key])))
        else: self.raiseAWarning('No Completed HistorySet! Not possible to start an adaptive search! Something went wrong!')
      if len(completedHistNames) > self.completedHistCnt:
        actualLastOutput      = self.lastOutput
        self.lastOutput       = copy.deepcopy(lastOutDict)
        ready                 = LimitSurfaceSearch.localStillReady(self,ready)
        self.lastOutput       = actualLastOutput
        self.completedHistCnt = len(completedHistNames)
        self.raiseAMessage("Completed full histories are "+str(self.completedHistCnt))
      else: ready = False
      self.adaptiveReady = ready
      if ready or detReady and self.persistence > self.repetition : return True
      else: return False
    return detReady

  def localGenerateInput(self,model,myInput):
    """
    Will generate an input and associate it with a probability
      @ In, model, the model to evaluate
      @ In, myInput, list of original inputs
      @ Out, None
    """

    if self.startAdaptive == True and self.adaptiveReady == True:
      LimitSurfaceSearch.localGenerateInput(self,model,myInput)
      #the adaptive sampler created the next point sampled vars
      #find the closest branch
      if self.hybridDETstrategy is not None: closestBranch, cdfValues, treer = self._checkClosestBranch()
      else                                 : closestBranch, cdfValues = self._checkClosestBranch()
      if closestBranch is None: self.raiseADebug('An usable branch for next candidate has not been found => create a parallel branch!')
      # add pbthresholds in the grid
      investigatedPoint = {}
      for key,value in cdfValues.items():
        ind = utils.find_le_index(self.branchProbabilities[self.toBeSampled[key]],value)
        if not ind: ind = 0
        if value not in self.branchProbabilities[self.toBeSampled[key]]:
          self.branchProbabilities[self.toBeSampled[key]].insert(ind,value)
          self.branchValues[self.toBeSampled[key]].insert(ind,self.distDict[key].ppf(value))
        investigatedPoint[self.toBeSampled[key]] = value
      # collect investigated point
      self.investigatedPoints.append(investigatedPoint)

      if closestBranch:
        info = self._retrieveBranchInfo(closestBranch)
        self._constructEndInfoFromBranch(model, myInput, info, cdfValues)
      else:
        # create a new tree, since there are no branches that are close enough to the adaptive request
        elm = ETS.Node(self.name + '_' + str(len(self.TreeInfo.keys())+1))
        elm.add('name', self.name + '_'+ str(len(self.TreeInfo.keys())+1))
        elm.add('startTime', 0.0)
        # Initialize the endTime to be equal to the start one...
        # It will modified at the end of each branch
        elm.add('endTime', 0.0)
        elm.add('runEnded',False)
        elm.add('running',True)
        elm.add('queue',False)
        elm.add('completedHistory', False)
        branchedLevel = {}
        for key,value in cdfValues.items(): branchedLevel[self.toBeSampled[key]] = utils.index(self.branchProbabilities[self.toBeSampled[key]],value)
        # The dictionary branchedLevel is stored in the xml tree too. That's because
        # the advancement of the thresholds must follow the tree structure
        elm.add('branchedLevel', branchedLevel)
        if self.hybridDETstrategy is not None and not self.foundEpistemicTree:
          # adaptive hybrid DET and not found a tree in the epistemic space
          # take the first tree and modify the hybridsamplerCoordinate
          hybridSampled = copy.deepcopy(self.TreeInfo.values()[0].getrootnode().get('hybridsamplerCoordinate'))
          for hybridStrategy in hybridSampled:
            for key in self.epistemicVariables.keys():
              if key in hybridStrategy['SampledVars'].keys():
                self.raiseADebug("epistemic var " + str(key)+" value = "+str(self.values[key]))
                hybridStrategy['SampledVars'][key]   = copy.copy(self.values[key])
                hybridStrategy['SampledVarsPb'][key] = self.distDict[key].pdf(self.values[key])
                hybridStrategy['prefix'] = len(self.TreeInfo.values())+1
            # TODO: find a strategy to recompute the probability weight here (for now == PointProbability)
            hybridStrategy['PointProbability'] = reduce(mul, self.inputInfo['SampledVarsPb'].values())
            hybridStrategy['ProbabilityWeight'] = reduce(mul, self.inputInfo['SampledVarsPb'].values())
          elm.add('hybridsamplerCoordinate', hybridSampled)
        # Here it is stored all the info regarding the DET => we create the info for all the branchings and we store them
        self.TreeInfo[self.name + '_' + str(len(self.TreeInfo.keys())+1)] = ETS.NodeTree(elm)
        self._createRunningQueueBeginOne(self.TreeInfo[self.name + '_' + str(len(self.TreeInfo.keys()))],branchedLevel, model,myInput)
    return DynamicEventTree.localGenerateInput(self,model,myInput)

  def localInputAndChecks(self,xmlNode):
    """
    Class specific inputs will be read here and checked for validity.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    """
    #check if the hybrid DET has been activated, in case remove the nodes and treat them separaterly
    hybridNodes = xmlNode.findall("HybridSampler")
    if len(hybridNodes) != 0:
      # check the type of hybrid that needs to be performed
      limitSurfaceHybrid = False
      for elm in hybridNodes:
        samplType = elm.attrib['type'] if 'type' in elm.attrib.keys() else None
        if samplType == 'LimitSurface':
          if len(hybridNodes) != 1: self.raiseAnError(IOError,'if one of the HybridSampler is of type "LimitSurface", it can not be combined with other strategies. Only one HybridSampler node can be inputted!')
          limitSurfaceHybrid = True
      if limitSurfaceHybrid == True:
        #remove the elements from original xmlNode and check if the types are compatible
        for elm in hybridNodes: xmlNode.remove(elm)
        self.hybridDETstrategy = 1
      else: self.hybridDETstrategy = 2
      if self.hybridDETstrategy == 2: self.raiseAnError(IOError, 'The sheaf of LSs for the Adaptive Hybrid DET is not yet available. Use type "LimitSurface"!')

    DynamicEventTree.localInputAndChecks(self,xmlNode)
    # now we put back the nodes into the xmlNode to initialize the LimitSurfaceSearch with those variables as well
    for elm in hybridNodes:
      for child in elm:
        if limitSurfaceHybrid == True              : xmlNode.append(child)
        if child.tag in ['variable','Distribution']: self.epistemicVariables[child.attrib['name']] = None
    LimitSurfaceSearch._readMoreXMLbase(self,xmlNode)
    LimitSurfaceSearch.localInputAndChecks(self,xmlNode)
    if 'mode' in xmlNode.attrib.keys():
      if   xmlNode.attrib['mode'].lower() == 'online': self.detAdaptMode = 2
      elif xmlNode.attrib['mode'].lower() == 'post'  : self.detAdaptMode = 1
      else:  self.raiseAnError(IOError,'unknown mode ' + xmlNode.attrib['mode'] + '. Available are "online" and "post"!')
    if 'noTransitionStrategy' in xmlNode.attrib.keys():
      if xmlNode.attrib['noTransitionStrategy'].lower() == 'mc'    : self.noTransitionStrategy = 1
      elif xmlNode.attrib['noTransitionStrategy'].lower() == 'grid': self.noTransitionStrategy = 2
      else:  self.raiseAnError(IOError,'unknown noTransitionStrategy '+xmlNode.attrib['noTransitionStrategy']+'. Available are "mc" and "grid"!')
    if 'updateGrid' in xmlNode.attrib.keys():
      if xmlNode.attrib['updateGrid'].lower() in utils.stringsThatMeanTrue(): self.insertAdaptBPb = True
    # we add an artificial threshold because I need to find a way to prepend a rootbranch into a Tree object
    for  val in self.branchProbabilities.values():
      if min(val) != 1e-3: val.insert(0, 1e-3)


  def _generateDistributions(self,availableDist,availableFunc):
    """
      Generates the distrbutions and functions.
      @ In, availDist, dict of distributions
      @ In, availDist, dict of functions
      @ Out, None
    """
    DynamicEventTree._generateDistributions(self,availableDist,availableFunc)

  def localInitialize(self,solutionExport = None):
    """
    Will perform all initialization specific to this Sampler. This will be
    called at the beginning of each Step where this object is used. See base
    class for more details.
    @ InOut, solutionExport: a PointSet to hold the solution
    @ Out None
    """
    if self.detAdaptMode == 2: self.startAdaptive = True
    # we first initialize the LimitSurfaceSearch sampler
    LimitSurfaceSearch.localInitialize(self,solutionExport=solutionExport)
    if self.hybridDETstrategy is not None:
      # we are running an adaptive hybrid DET and not only an adaptive DET
      if self.hybridDETstrategy == 1:
        gridVector = self.limitSurfacePP.gridEntity.returnParameter("gridVectors")
        # construct an hybrid DET through an XML node
        distDict, xmlNode = {}, ET.fromstring('<InitNode> <HybridSampler type="Grid"/> </InitNode>')
        for varName, dist in self.distDict.items():
          if varName.replace('<distribution>','') in self.epistemicVariables.keys():
            # found an epistemic
            varNode  = ET.Element('Distribution' if varName.startswith('<distribution>') else 'variable',{'name':varName.replace('<distribution>','')})
            varNode.append(ET.fromstring("<distribution>"+dist.name.strip()+"</distribution>"))
            distDict[dist.name.strip()] = self.distDict[varName]
            varNode.append(ET.fromstring('<grid construction="custom" type="value">'+' '.join([str(elm) for elm in gridVector.values()[0][varName.replace('<distribution>','')]])+'</grid>'))
            xmlNode.find("HybridSampler").append(varNode)
        self._localInputAndChecksHybrid(xmlNode)
        for hybridsampler in self.hybridStrategyToApply.values(): hybridsampler._generateDistributions(distDict, {})
    DynamicEventTree.localInitialize(self)
    if self.hybridDETstrategy == 2: self.actualHybridTree = utils.first(self.TreeInfo.keys())
    self._endJobRunnable    = sys.maxsize

  def generateInput(self,model,oldInput):
    """
    Will generate an input
    @in model   : it is the instance of a model
    @in oldInput: [] a list of the original needed inputs for the model (e.g.
                     list of files, etc. etc)
    @return     : [] containing the new inputs -in reality it is the model that
                     returns this, the Sampler generates the values to be placed
                     in the model input
    """
    return DynamicEventTree.generateInput(self, model, oldInput)

  def localFinalizeActualSampling(self,jobObject,model,myInput):
    """
    General function (available to all samplers) that finalizes the sampling
    calculation just ended. See base class for more information.
    @ In, jobObject    : JobHandler Instance of the job (run) just finished
    @ In, model        : Model Instance... It may be a Code Instance, ROM, etc.
    @ In, myInput      : List of the original input files
    @ Out, None
    """
    returncode = DynamicEventTree.localFinalizeActualSampling(self,jobObject,model,myInput,genRunQueue=False)
    forceEvent = True if self.startAdaptive else False
    if returncode:
      self._createRunningQueue(model,myInput, forceEvent)

#
#
#
#
class FactorialDesign(Grid):
  """
  Samples the model on a given (by input) set of points
  """
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Grid.__init__(self)
    self.printTag = 'SAMPLER FACTORIAL DESIGN'
    # accepted types. full = full factorial, 2levelFract = 2-level fracional factorial, pb = Plackett-Burman design. NB. full factorial is equivalent to Grid sampling
    self.acceptedTypes = ['full','2levelfract','pb'] # accepted factorial types
    self.factOpt       = {}                          # factorial options (type,etc)
    self.designMatrix  = None                        # matrix container

  def localInputAndChecks(self,xmlNode):
    """
    Class specific xml inputs will be read here and checked for validity.
    Specifically, reading and construction of the grid.
    @ In, xmlNode: The xml element node that will be checked against the
                   available options specific to this Sampler.
    @ Out, None
    """
    Grid.localInputAndChecks(self,xmlNode)
    factsettings = xmlNode.find("FactorialSettings")
    if factsettings == None: self.raiseAnError(IOError,'FactorialSettings xml node not found!')
    facttype = factsettings.find("algorithmType")
    if facttype == None: self.raiseAnError(IOError,'node "algorithmType" not found in FactorialSettings xml node!!!')
    elif not facttype.text.lower() in self.acceptedTypes:self.raiseAnError(IOError,' "type" '+facttype.text+' unknown! Available are ' + ' '.join(self.acceptedTypes))
    self.factOpt['algorithmType'] = facttype.text.lower()
    if self.factOpt['algorithmType'] == '2levelfract':
      self.factOpt['options'] = {}
      self.factOpt['options']['gen'] = factsettings.find("gen")
      self.factOpt['options']['genMap'] = factsettings.find("genMap")
      if self.factOpt['options']['gen'] == None: self.raiseAnError(IOError,'node "gen" not found in FactorialSettings xml node!!!')
      if self.factOpt['options']['genMap'] == None: self.raiseAnError(IOError,'node "genMap" not found in FactorialSettings xml node!!!')
      self.factOpt['options']['gen'] = self.factOpt['options']['gen'].text.split(',')
      self.factOpt['options']['genMap'] = self.factOpt['options']['genMap'].text.split(',')
      if len(self.factOpt['options']['genMap']) != len(self.gridInfo.keys()): self.raiseAnError(IOError,'number of variable in genMap != number of variables !!!')
      if len(self.factOpt['options']['gen']) != len(self.gridInfo.keys())   : self.raiseAnError(IOError,'number of variable in gen != number of variables !!!')
      rightOrder = [None]*len(self.gridInfo.keys())
      if len(self.factOpt['options']['genMap']) != len(self.factOpt['options']['gen']): self.raiseAnError(IOError,'gen and genMap different size!')
      if len(self.factOpt['options']['genMap']) != len(self.gridInfo.keys()): self.raiseAnError(IOError,'number of gen attributes and variables different!')
      for ii,var in enumerate(self.factOpt['options']['genMap']):
        if var not in self.gridInfo.keys(): self.raiseAnError(IOError,' variable "'+var+'" defined in genMap block not among the inputted variables!')
        rightOrder[self.axisName.index(var)] = self.factOpt['options']['gen'][ii]
      self.factOpt['options']['orderedGen'] = rightOrder
    if self.factOpt['algorithmType'] != 'full':
      self.externalgGridCoord = True
      for varname in self.gridInfo.keys():
        if len(self.gridEntity.returnParameter("gridInfo")[varname][2]) != 2:
          self.raiseAnError(IOError,'The number of levels for type '+
                        self.factOpt['algorithmType'] +' must be 2! In variable '+varname+ ' got number of levels = ' +
                        str(len(self.gridEntity.returnParameter("gridInfo")[varname][2])))
    else: self.externalgGridCoord = False

  def localAddInitParams(self,tempDict):
    """
    Appends a given dictionary with class specific member variables and their
    associated initialized values.
    @ InOut, tempDict: The dictionary where we will add the initialization
                       parameters specific to this Sampler.
    """
    Grid.localAddInitParams(self,tempDict)
    for key,value in self.factOpt.items():
      if key != 'options': tempDict['Factorial '+key] = value
      else:
        for kk,val in value.items(): tempDict['Factorial options '+kk] = val

  def localInitialize(self):
    """
    This method initialize the factorial matrix. No actions are taken for full-factorial since it is equivalent to the Grid sampling this sampler is based on
    """
    Grid.localInitialize(self)
    if   self.factOpt['algorithmType'] == '2levelfract': self.designMatrix = doe.fracfact(' '.join(self.factOpt['options']['orderedGen'])).astype(int)
    elif self.factOpt['algorithmType'] == 'pb'         : self.designMatrix = doe.pbdesign(len(self.gridInfo.keys())).astype(int)
    if self.designMatrix != None:
      self.designMatrix[self.designMatrix == -1] = 0 # convert all -1 in 0 => we can access to the grid info directly
      self.limit = self.designMatrix.shape[0]        # the limit is the number of rows

  def localGenerateInput(self,model,myInput):
    """
    Will generate an input and associate it with a probability
      @ In, model, the model to evaluate
      @ In, myInput, list of original inputs (unused)
      @ Out, None
    """
    if self.factOpt['algorithmType'] == 'full':  Grid.localGenerateInput(self,model, myInput)
    else:
      self.gridCoordinate = self.designMatrix[self.counter - 1][:].tolist()
      Grid.localGenerateInput(self,model, myInput)
#
#
#
#
class ResponseSurfaceDesign(Grid):
  """
  Samples the model on a given (by input) set of points
  """
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Grid.__init__(self)
    self.limit    = 1
    self.printTag = 'SAMPLER RESPONSE SURF DESIGN'
    self.respOpt         = {}                                    # response surface design options (type,etc)
    self.designMatrix    = None                                  # matrix container
    self.bounds          = {}                                    # dictionary of lower and upper
    self.mapping         = {}                                    # mapping between designmatrix coordinates and position in grid
    self.minNumbVars     = {'boxbehnken':3,'centralcomposite':2} # minimum number of variables
    # dictionary of accepted types and options (required True, optional False)
    self.acceptedOptions = {'boxbehnken':['ncenters'], 'centralcomposite':['centers','alpha','face']}

  def localInputAndChecks(self,xmlNode):
    """reading and construction of the grid"""
    Grid.localInputAndChecks(self,xmlNode)
    factsettings = xmlNode.find("ResponseSurfaceDesignSettings")
    if factsettings == None: self.raiseAnError(IOError,'ResponseSurfaceDesignSettings xml node not found!')
    facttype = factsettings.find("algorithmType")
    if facttype == None: self.raiseAnError(IOError,'node "algorithmType" not found in ResponseSurfaceDesignSettings xml node!!!')
    elif not facttype.text.lower() in self.acceptedOptions.keys():self.raiseAnError(IOError,'"type" '+facttype.text+' unknown! Available are ' + ' '.join(self.acceptedOptions.keys()))
    self.respOpt['algorithmType'] = facttype.text.lower()
    # set defaults
    if self.respOpt['algorithmType'] == 'boxbehnken': self.respOpt['options'] = {'ncenters':None}
    else                                             : self.respOpt['options'] = {'centers':(4,4),'alpha':'orthogonal','face':'circumscribed'}
    for child in factsettings:
      if child.tag not in 'algorithmType': self.respOpt['options'][child.tag] = child.text.lower()
    # start checking
    for key,value in self.respOpt['options'].items():
      if key not in self.acceptedOptions[facttype.text.lower()]: self.raiseAnError(IOError,'node '+key+' unknown. Available are "'+' '.join(self.acceptedOptions[facttype.text.lower()])+'"!!')
      if self.respOpt['algorithmType'] == 'boxbehnken':
        if key == 'ncenters':
          if self.respOpt['options'][key] != None:
            try   : self.respOpt['options'][key] = int(value)
            except: self.raiseAnError(IOError,'"'+key+'" is not an integer!')
      else:
        if key == 'centers':
          if len(value.split(',')) != 2: self.raiseAnError(IOError,'"'+key+'" must be a comma separated string of 2 values only!')
          try: self.respOpt['options'][key] = (int(value.split(',')[0]),int(value.split(',')[1]))
          except: self.raiseAnError(IOError,'"'+key+'" values must be integers!!')
        if key == 'alpha':
          if value not in ['orthogonal','rotatable']: self.raiseAnError(IOError,'Not recognized options for node ' +'"'+key+'". Available are "orthogonal","rotatable"!')
        if key == 'face':
          if value not in ['circumscribed','faced','inscribed']: self.raiseAnError(IOError,'Not recognized options for node ' +'"'+key+'". Available are "circumscribed","faced","inscribed"!')
    gridInfo = self.gridEntity.returnParameter('gridInfo')
    if len(self.toBeSampled.keys()) != len(gridInfo.keys()): self.raiseAnError(IOError,'inconsistency between number of variables and grid specification')
    for varName, values in gridInfo.items():
      if values[1] != "custom" : self.raiseAnError(IOError,"The grid construct needs to be custom for variable "+varName)
      if len(values[2]) != 2   : self.raiseAnError(IOError,"The number of values can be accepted are only 2 (lower and upper bound) for variable "+varName)
    self.gridCoordinate = [None]*len(self.axisName)
    if len(self.gridCoordinate) < self.minNumbVars[self.respOpt['algorithmType']]: self.raiseAnError(IOError,'minimum number of variables for type "'+ self.respOpt['type'] +'" is '+str(self.minNumbVars[self.respOpt['type']])+'!!')
    self.externalgGridCoord = True

  def localAddInitParams(self,tempDict):
    """
    Appends a given dictionary with class specific member variables and their
    associated initialized values.
    @ InOut, tempDict: The dictionary where we will add the initialization
                       parameters specific to this Sampler.
    """
    Grid.localAddInitParams(self,tempDict)
    for key,value in self.respOpt.items():
      if key != 'options': tempDict['Response Design '+key] = value
      else:
        for kk,val in value.items(): tempDict['Response Design options '+kk] = val

  def localInitialize(self):
    """
    This method initialize the response matrix. No actions are taken for full-factorial since it is equivalent to the Grid sampling this sampler is based on
    """
    if   self.respOpt['algorithmType'] == 'boxbehnken'      : self.designMatrix = doe.bbdesign(len(self.gridInfo.keys()),center=self.respOpt['options']['ncenters'])
    elif self.respOpt['algorithmType'] == 'centralcomposite': self.designMatrix = doe.ccdesign(len(self.gridInfo.keys()), center=self.respOpt['options']['centers'], alpha=self.respOpt['options']['alpha'], face=self.respOpt['options']['face'])
    gridInfo   = self.gridEntity.returnParameter('gridInfo')
    stepLength = {}
    for cnt, varName in enumerate(self.axisName):
      self.mapping[varName] = np.unique(self.designMatrix[:,cnt]).tolist()
      gridInfo[varName] = (gridInfo[varName][0],gridInfo[varName][1],InterpolatedUnivariateSpline(np.array([min(self.mapping[varName]), max(self.mapping[varName])]),
                           np.array([min(gridInfo[varName][2]), max(gridInfo[varName][2])]), k=1)(self.mapping[varName]).tolist())
      stepLength[varName] = [round(gridInfo[varName][-1][k+1] - gridInfo[varName][-1][k],14) for k in range(len(gridInfo[varName][-1])-1)]
    self.gridEntity.updateParameter("stepLength", stepLength, False)
    self.gridEntity.updateParameter("gridInfo", gridInfo)
    Grid.localInitialize(self)
    self.limit = self.designMatrix.shape[0]

  def localGenerateInput(self,model,myInput):
    gridcoordinate = self.designMatrix[self.counter - 1][:].tolist()
    for cnt, varName in enumerate(self.axisName): self.gridCoordinate[cnt] = self.mapping[varName].index(gridcoordinate[cnt])
    Grid.localGenerateInput(self,model, myInput)
#
#
#
#
class SparseGridCollocation(Grid):
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Grid.__init__(self)
    self.type           = 'SparseGridCollocationSampler'
    self.printTag       = 'SAMPLER '+self.type.upper()
    self.assemblerObjects={}    #dict of external objects required for assembly
    self.maxPolyOrder   = None  #L, the relative maximum polynomial order to use in any dimension
    self.indexSetType   = None  #TP, TD, or HC; the type of index set to use
    self.polyDict       = {}    #varName-indexed dict of polynomial types
    self.quadDict       = {}    #varName-indexed dict of quadrature types
    self.importanceDict = {}    #varName-indexed dict of importance weights
    self.maxPolyOrder   = None  #integer, relative maximum polynomial order to be used in any one dimension
    self.lastOutput     = None  #pointer to output dataObjects object
    self.ROM            = None  #pointer to ROM
    self.jobHandler     = None  #pointer to job handler for parallel runs
    self.doInParallel   = True  #compute sparse grid in parallel flag, recommended True
    self.existing       = []    #restart data points
    self.dists          = {}    #Contains the instance of the distribution to be used. keys are the variable names
    self._addAssObject('ROM','1')

  def _localWhatDoINeed(self):
    """
    This method is a local mirror of the general whatDoINeed method.
    It is implemented by the samplers that need to request special objects
    @ In , None, None
    @ Out, dict, dictionary of objects needed
    """
    gridDict = Grid._localWhatDoINeed(self)
    gridDict['internal'] = [(None,'jobHandler')]
    return gridDict

  def _localGenerateAssembler(self,initDict):
    """Generates the assembler.
    @ In, initDict, dict, init objects
    @ Out, None
    """
    Grid._localGenerateAssembler(self, initDict)
    self.jobHandler = initDict['internal']['jobHandler']
    self.dists = self.transformDistDict()
    #Do a distributions check for ND
    #This sampler only accept ND distributions with variable transformation defined in this sampler
    for dist in self.dists.values():
      if isinstance(dist,Distributions.NDimensionalDistributions): self.raiseAnError(IOError,'ND Dists contain the variables in the original input space are  not supported for this sampler!')

  def localInputAndChecks(self,xmlNode):
    """
    Reads in XML node
    @ In, xmlNode, XML node, input xml
    @ Out, None
    """
    self.doInParallel = xmlNode.attrib['parallel'].lower() in ['1','t','true','y','yes'] if 'parallel' in xmlNode.attrib.keys() else True
    self.writeOut = xmlNode.attrib['outfile'] if 'outfile' in xmlNode.attrib.keys() else None
    for child in xmlNode:
      if child.tag == 'Distribution':
        varName = '<distribution>'+child.attrib['name']
      elif child.tag == 'variable':
        varName = child.attrib['name']
        if varName not in self.dependentSample.keys():
          self.axisName.append(varName)

  def transformDistDict(self):
    """
      Performs distribution transformation
      If the method 'pca' is used in the variables transformation (i.e. latentVariables to manifestVariables), the corrrelated variables
      will be tranformed into uncorrelated variables with standard normal distributions. Thus, the dictionary of distributions will
      be also transformed.
      @ In, None
      @ Out, distDicts, dict, distribution dictionary {varName:DistributionObject}
    """
    # Generate a standard normal distribution, this is used to generate the sparse grid points and weights for multivariate normal
    # distribution if PCA is used.
    standardNormal = Distributions.Normal()
    standardNormal.messageHandler = self.messageHandler
    standardNormal.mean = 0.0
    standardNormal.sigma = 1.0
    standardNormal.initializeDistribution()
    distDicts = {}
    for varName in self.variables2distributionsMapping.keys():
      distDicts[varName] = self.distDict[varName]
    if self.variablesTransformationDict:
      for key,varsDict in self.variablesTransformationDict.items():
        if self.transformationMethod[key] == 'pca':
          listVars = varsDict['latentVariables']
          for var in listVars:
            distDicts[var] = standardNormal
    return distDicts

  def localInitialize(self):
    """Performs local initialization
    @ In, None
    @ Out, None
    """
    for key in self.assemblerDict.keys():
      if 'ROM' in key:
        for value in self.assemblerDict[key]: self.ROM = value[3]
    SVLs = self.ROM.SupervisedEngine.values()
    SVL = utils.first(SVLs) #often need only one
    self.features = SVL.features
    self._generateQuadsAndPolys(SVL)
    #print out the setup for each variable.
    msg=self.printTag+' INTERPOLATION INFO:\n'
    msg+='    Variable | Distribution | Quadrature | Polynomials\n'
    for v in self.quadDict.keys():
      msg+='   '+' | '.join([v,self.distDict[v].type,self.quadDict[v].type,self.polyDict[v].type])+'\n'
    msg+='    Polynomial Set Degree: '+str(self.maxPolyOrder)+'\n'
    msg+='    Polynomial Set Type  : '+str(SVL.indexSetType)+'\n'
    self.raiseADebug(msg)

    self.raiseADebug('Starting index set generation...')
    self.indexSet = IndexSets.returnInstance(SVL.indexSetType,self)
    self.indexSet.initialize(self.features,self.importanceDict,self.maxPolyOrder)
    if self.indexSet.type=='Custom':
      self.indexSet.setPoints(SVL.indexSetVals)

    self.raiseADebug('Starting sparse grid generation...')
    self.sparseGrid = Quadratures.SparseQuad()
    # NOTE this is the most expensive step thus far; try to do checks before here
    self.sparseGrid.initialize(self.features,self.indexSet,self.dists,self.quadDict,self.jobHandler,self.messageHandler)

    if self.writeOut != None:
      msg=self.sparseGrid.__csv__()
      outFile=open(self.writeOut,'w')
      outFile.writelines(msg)
      outFile.close()

    #if restart, figure out what runs we need; else, all of them
    if self.restartData != None:
      self.solns = self.restartData
      self._updateExisting()

    self.limit=len(self.sparseGrid)
    self.raiseADebug('Size of Sparse Grid  :'+str(self.limit))
    self.raiseADebug('Number of Runs Needed :'+str(self.limit-utils.iter_len(self.existing)))
    self.raiseADebug('Finished sampler generation.')

    self.raiseADebug('indexset:',self.indexSet)
    for SVL in self.ROM.SupervisedEngine.values():
      SVL.initialize({'SG':self.sparseGrid,
                      'dists':self.dists,
                      'quads':self.quadDict,
                      'polys':self.polyDict,
                      'iSet':self.indexSet})

  def _generateQuadsAndPolys(self,SVL):
    """
      Builds the quadrature objects, polynomial objects, and importance weights for all
      the distributed variables.  Also sets maxPolyOrder.
      @ In, SVL, SupervisedEngine object, one of the SupervisedEngine objects from the ROM
      @ Out, None
    """
    ROMdata = SVL.interpolationInfo()
    self.maxPolyOrder = SVL.maxPolyOrder
    #check input space consistency
    samVars=self.axisName[:]
    romVars=SVL.features[:]
    try:
      for v in self.axisName:
        samVars.remove(v)
        romVars.remove(v)
    except ValueError:
      self.raiseAnError(IOError,'variable '+v+' used in sampler but not ROM features! Collocation requires all vars in both.')
    if len(romVars)>0:
      self.raiseAnError(IOError,'variables '+str(romVars)+' specified in ROM but not sampler! Collocation requires all vars in both.')
    for v in ROMdata.keys():
      if v not in self.axisName:
        self.raiseAnError(IOError,'variable '+v+' given interpolation rules but '+v+' not in sampler!')
      else:
        self.gridInfo[v] = ROMdata[v] #quad, poly, weight
    #set defaults, then replace them if they're asked for
    for v in self.axisName:
      if v not in self.gridInfo.keys():
        self.gridInfo[v]={'poly':'DEFAULT','quad':'DEFAULT','weight':'1'}
    #establish all the right names for the desired types
    for varName,dat in self.gridInfo.items():
      if dat['poly'] == 'DEFAULT': dat['poly'] = self.dists[varName].preferredPolynomials
      if dat['quad'] == 'DEFAULT': dat['quad'] = self.dists[varName].preferredQuadrature
      polyType=dat['poly']
      subType = None
      distr = self.dists[varName]
      if polyType == 'Legendre':
        if distr.type == 'Uniform':
          quadType=dat['quad']
        else:
          quadType='CDF'
          subType=dat['quad']
          if subType not in ['Legendre','ClenshawCurtis']:
            self.raiseAnError(IOError,'Quadrature '+subType+' not compatible with Legendre polys for '+distr.type+' for variable '+varName+'!')
      else:
        quadType=dat['quad']
      if quadType not in distr.compatibleQuadrature:
        self.raiseAnError(IOError,'Quadrature type"',quadType,'"is not compatible with variable"',varName,'"distribution"',distr.type,'"')

      quad = Quadratures.returnInstance(quadType,self,Subtype=subType)
      quad.initialize(distr,self.messageHandler)
      self.quadDict[varName]=quad

      poly = OrthoPolynomials.returnInstance(polyType,self)
      poly.initialize(quad,self.messageHandler)
      self.polyDict[varName] = poly

      self.importanceDict[varName] = float(dat['weight'])

  def localGenerateInput(self,model,myInput):
    """
      Provide the next point in the sparse grid.
      @ In, model, Model, the model to evaluate
      @ In, myInput, list(str), list of original inputs
      @ Out, None
    """
    found=False
    while not found:
      try: pt,weight = self.sparseGrid[self.counter-1]
      except IndexError: raise utils.NoMoreSamplesNeeded
      if pt in self.existing:
        self.counter+=1
        if self.counter==self.limit: raise utils.NoMoreSamplesNeeded
        continue
      else:
        found=True

        for v,varName in enumerate(self.sparseGrid.varNames):
          # compute the SampledVarsPb for 1-D distribution
          if self.variables2distributionsMapping[varName]['totDim'] == 1:
            for key in varName.strip().split(','):
              self.values[key] = pt[v]
            self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(pt[v])
            self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.inputInfo['SampledVarsPb'][varName]
          # compute the SampledVarsPb for N-D distribution
          # Assume only one N-D distribution is associated with sparse grid collocation method
          elif self.variables2distributionsMapping[varName]['totDim'] > 1 and self.variables2distributionsMapping[varName]['reducedDim'] ==1:
            dist = self.variables2distributionsMapping[varName]['name']
            ndCoordinates = np.zeros(len(self.distributions2variablesMapping[dist]))
            positionList = self.distributions2variablesIndexList[dist]
            for varDict in self.distributions2variablesMapping[dist]:
              var = utils.first(varDict.keys())
              position = utils.first(varDict.values())
              location = -1
              for key in var.strip().split(','):
                if key in self.sparseGrid.varNames:
                  location = self.sparseGrid.varNames.index(key)
                  break
              if location > -1:
                ndCoordinates[positionList.index(position)] = pt[location]
              else:
                self.raiseAnError(IOError,'The variables ' + var + ' listed in sparse grid collocation sampler, but not used in the ROM!' )
              for key in var.strip().split(','):
                self.values[key] = pt[location]
            self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(ndCoordinates)
            self.inputInfo['ProbabilityWeight-'+varName.replace(",","!")] = self.inputInfo['SampledVarsPb'][varName]

        self.inputInfo['ProbabilityWeight'] = weight
        self.inputInfo['PointProbability'] = reduce(mul,self.inputInfo['SampledVarsPb'].values())
        self.inputInfo['SamplerType'] = 'Sparse Grid Collocation'

  def _updateExisting(self):
    """
      Goes through the stores solutions PointSet and pulls out solutions, ordering them
      by the order the features we're evaluating.
      @ In, None
      @ Out, None
    """
    #TODO: only append new points instead of resorting everyone
    if not self.solns.isItEmpty():
      inps = self.solns.getInpParametersValues()
      outs = self.solns.getOutParametersValues()
      #make reorder map
      reordmap=list(inps.keys().index(i) for i in self.features)
      solns = list(v for v in inps.values())
      ordsolns = [solns[i] for i in reordmap]
      existinginps = zip(*ordsolns)
      outvals = zip(*list(v for v in outs.values()))
      self.existing = dict(zip(existinginps,outvals))
#
#
#
#
class AdaptiveSparseGrid(AdaptiveSampler,SparseGridCollocation):
  def __init__(self):
    """
      Default Constructor that will initialize member variables with reasonable
      defaults or empty lists/dictionaries where applicable.
      @ In, None
      @ Out, None
    """
    SparseGridCollocation.__init__(self)
    #identification
    self.type                    = 'AdaptiveSparseGridSampler'
    self.printTag                = self.type
    #assembler objects
    self.solns                   = None   #TimePointSet of solutions -> assembled
    self.ROM                     = None   #eventual final ROM object
    #input parameters
    self.maxPolyOrder            = 0      #max size of polynomials to allow
    self.persistence             = 0      #number of forced iterations, default 2
    self.convType                = None   #convergence criterion to use
    self.logFile                 = None   #file to print log to, optional
    #convergence/training tools
    self.expImpact               = {}     #dict of potential included polynomials and their estimated impacts, [target][index]
    self.actImpact               = {}     #dict of included polynomials and their current impact, [target][index] = impact
    self.sparseGrid              = None   #current sparse grid
    self.oldSG                   = None   #previously-accepted sparse grid
    self.error                   = 0      #estimate of percent of moment calculated so far
    self.logCounter              = 0      #when printing the log, tracks the number of prints
    #convergence study
    self.doingStudy              = False  #true if convergenceStudy node defined for sampler
    self.studyFileBase           = 'out_' #can be replaced in input, not used if not doingStudy
    self.studyPoints             = []     #list of ints, runs at which to record a state
    self.studyPickle             = False  #if true, dumps ROM to pickle at each step
    #solution storage
    self.existing                = {}     #rolling list of sampled points
    self.neededPoints            = []     #queue of points to submit
    self.submittedNotCollected   = []     #list of points submitted but not yet collected and used
    self.pointsNeededToMakeROM   = set()  #list of distinct points needed in this process
    self.unfinished              = 0      #number of runs still running when convergence complete
    self.batchDone               = True   #flag for whether jobHandler has complete batch or not
    self.done                    = False  #flipped when converged
    self.newSolutionSizeShouldBe = None   #used to track and debug intended size of solutions
    self.inTraining              = set()  #list of index set points for whom points are being run

    self._addAssObject('TargetEvaluation','1')

  def localInputAndChecks(self,xmlNode):
    """
      Reads in XML node
      @ In, xmlNode, XML node, input xml
      @ Out, None
    """
    SparseGridCollocation.localInputAndChecks(self,xmlNode)
    if 'Convergence' not in list(c.tag for c in xmlNode): self.raiseAnError(IOError,'Convergence node not found in input!')
    convnode  = xmlNode.find('Convergence')
    logNode   = xmlNode.find('logFile')
    studyNode = xmlNode.find('convergenceStudy')
    self.convType     = convnode.attrib.get('target','variance')
    self.maxPolyOrder = int(convnode.attrib.get('maxPolyOrder',10))
    self.persistence  = int(convnode.attrib.get('persistence',2))
    self.maxRuns      = convnode.attrib.get('maxRuns',None)
    self.convValue    = float(convnode.text)
    if logNode      is not None: self.logFile = logNode.text
    if self.maxRuns is not None: self.maxRuns = int(self.maxRuns)
    if studyNode    is not None:
      self.doingStudy = True
      self.studyPoints = studyNode.find('runStatePoints').text
      filebaseNode = studyNode.find('baseFilename')
      self.studyPickle = studyNode.find('pickle') is not None
      if filebaseNode is None:
        self.raiseAWarning('No baseFilename specified in convergenceStudy node!  Using "%s"...' %self.studyFileBase)
      else:
        self.studyFileBase = studyNode.find('baseFilename').text
      if self.studyPoints is None:
        self.raiseAnError(IOError,'convergenceStudy node was included, but did not specify the runStatePoints node!')
      else:
        try:
          self.studyPoints = list(int(i) for i in self.studyPoints.split(','))
        except ValueError as e:
          self.raiseAnError(IOError,'Convergence state point not recognizable as an integer!',e)
        self.studyPoints.sort()

  def localInitialize(self):
    """Performs local initialization
      @ In, None
      @ Out, None
    """
    #set a pointer to the end-product ROM
    self.ROM = self.assemblerDict['ROM'][0][3]
    #obtain the DataObject that contains evaluations of the model
    self.solns = self.assemblerDict['TargetEvaluation'][0][3]
    #set a pointer to the GaussPolynomialROM object
    SVLs = self.ROM.SupervisedEngine.values()
    SVL = utils.first(SVLs) #sampler doesn't always care about which target
    self.features=SVL.features #the input space variables
    self.targets = self.ROM.initializationOptionDict['Target'].split(',') #the output space variables
    #initialize impact dictionaries by target
    for t in self.targets:
      self.expImpact[t] = {}
      self.actImpact[t] = {}
    mpo = self.maxPolyOrder #save it to re-set it after calling generateQuadsAndPolys
    self._generateQuadsAndPolys(SVL) #lives in GaussPolynomialRom object
    self.maxPolyOrder = mpo #re-set it

    #print out the setup for each variable.
    self.raiseADebug(' INTERPOLATION INFO:')
    self.raiseADebug('    Variable | Distribution | Quadrature | Polynomials')
    for v in self.quadDict.keys():
      self.raiseADebug('   '+' | '.join([v,self.distDict[v].type,self.quadDict[v].type,self.polyDict[v].type]))
    self.raiseADebug('    Polynomial Set Type  : adaptive')

    #create the index set
    self.raiseADebug('Starting index set generation...')
    self.indexSet = IndexSets.returnInstance('AdaptiveSet',self)
    self.indexSet.initialize(self.features,self.importanceDict,self.maxPolyOrder)
    for pt in self.indexSet.active:
      self.inTraining.add(pt)
      for t in self.targets:
        self.expImpact[t][pt] = 1.0 #dummy, just to help algorithm be consistent

    #set up the already-existing solutions (and re-order the inputs appropriately)
    self._updateExisting()

    #make the first sparse grid
    self.sparseGrid = self._makeSparseQuad(self.indexSet.active)

    #set up the points we need RAVEN to run before we can continue
    self.newSolutionSizeShouldBe = len(self.existing)
    self._addNewPoints()

  def localStillReady(self,ready,skipJobHandlerCheck=False):
    """
      Determines what additional points are necessary for RAVEN to run.
      @ In, ready, bool, true if ready
      @ In, skipJobHandlerCheck, optional bool, if true bypasses check on active runs in jobHandler
      @ Out, ready, bool, true if ready
    """
    #if we're done, be done
    if self.done: return False
    #update existing solutions
    self._updateExisting()
    #if we're not ready elsewhere, just be not ready
    if ready==False: return ready
    #if we still have a list of points to sample, just keep on trucking.
    if len(self.neededPoints)>0:
      return True
    #if points all submitted but not all done, not ready for now.
    if (not self.batchDone) or (not skipJobHandlerCheck and not self.jobHandler.isFinished()):
      return False
    if len(self.existing) < self.newSolutionSizeShouldBe:
      return False
    #if no points to check right now, search for points to sample
    #this should also mean the points for the poly-in-training are done
    while len(self.neededPoints)<1:
      #update sparse grid and set active impacts
      self._updateQoI()
      #move the index set forward -> that is, find the potential new indices
      self.indexSet.forward(self.maxPolyOrder)
      #estimate impacts of all potential indices
      for pidx in self.indexSet.active:
        self._estimateImpact(pidx)
      #check error convergence, using the largest impact from each target
      self.error = 0
      for pidx in self.indexSet.active:
        self.error += max(self.expImpact[t][pidx] for t in self.targets)
      #if logging, print to file
      if self.logFile is not None:
        self._printToLog()
      #if doing a study and past a statepoint, record the statepoint
      if self.doingStudy:
        while len(self.studyPoints)>0 and len(self.pointsNeededToMakeROM) > self.studyPoints[0]:
          self._writeConvergencePoint(self.studyPoints[0])
          if self.studyPickle: self._writePickle(self.studyPoints[0])
          #remove the point
          if len(self.studyPoints)>1: self.studyPoints=self.studyPoints[1:]
          else: self.studyPoints = []
      #if error small enough, converged!
      if abs(self.error) < self.convValue:
        self.done = True
        self.converged = True
        break
      #if maxRuns reached, no more samples!
      if self.maxRuns is not None and len(self.pointsNeededToMakeROM) >= self.maxRuns:
        self.raiseAMessage('Maximum runs reached!  No further polynomial will be added.')
        self.done = True
        self.converged = True
        self.neededPoints=[]
        break
      #otherwise, not converged...
      #what if we have no polynomials to consider...
      if len(self.indexSet.active)<1:
        self.raiseADebug('No new polynomials to consider!')
        break
      #find the highest overall impact to run next
      idx = self._findHighestImpactIndex()
      #add it to the training list, and append its points to the requested ones
      self.inTraining.add(idx)
      newSG = self._makeSparseQuad([idx])
      self._addNewPoints(newSG)
    #if we exited while loop without finding points, we must be done!
    if len(self.neededPoints)<1:
      self.converged = True
      self.raiseADebug('Index points in use, and their impacts:')
      for p in self.indexSet.points:
        self.raiseADebug('   ',p,list(self.actImpact[t][p] for t in self.targets))
      self._finalizeROM()
      self.unfinished = self.jobHandler.numRunning()
      self.jobHandler.terminateAll()
      self.neededPoints=[]
      self.done = True
      if self.doingStudy and len(self.studyPoints)>0:
        self.raiseAWarning('In the convergence study, the following numbers of runs were not reached:',self.studyPoints)
      return False
    #if we got here, we still have points to run!
    #print a status update...
    self.raiseAMessage('  Next: %s | error: %1.4e | runs: %i' %(str(idx),self.error,len(self.pointsNeededToMakeROM)))
    return True

  def localGenerateInput(self,model,myInput):
    """
      Generates an input. Parameters inherited.
      @ In, model, Model, unused
      @ In, myInput, list(str), unused
    """
    pt = self.neededPoints.pop()
    self.submittedNotCollected.append(pt)
    for v,varName in enumerate(self.sparseGrid.varNames):
      # compute the SampledVarsPb for 1-D distribution
      if self.variables2distributionsMapping[varName]['totDim'] == 1:
        for key in varName.strip().split(','):
          self.values[key] = pt[v]
        self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(pt[v])
        self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.inputInfo['SampledVarsPb'][varName]
        # compute the SampledVarsPb for N-D distribution
      elif self.variables2distributionsMapping[varName]['totDim'] > 1 and self.variables2distributionsMapping[varName]['reducedDim'] ==1:
        dist = self.variables2distributionsMapping[varName]['name']
        ndCoordinates = np.zeros(len(self.distributions2variablesMapping[dist]))
        positionList = self.distributions2variablesIndexList[dist]
        for varDict in self.distributions2variablesMapping[dist]:
          var = utils.first(varDict.keys())
          position = utils.first(varDict.values())
          location = -1
          for key in var.strip().split(','):
            if key in self.sparseGrid.varNames:
              location = self.sparseGrid.varNames.index(key)
              break
          if location > -1:
            ndCoordinates[positionList.index(position)] = pt[location]
          else:
            self.raiseAnError(IOError,'The variables ' + var + ' listed in sparse grid collocation sampler, but not used in the ROM!' )
          for key in var.strip().split(','):
            self.values[key] = pt[location]
        self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(ndCoordinates)
        self.inputInfo['ProbabilityWeight-'+varName.replace(",","!")] = self.inputInfo['SampledVarsPb'][varName]

    self.inputInfo['PointProbability'] = reduce(mul,self.inputInfo['SampledVarsPb'].values())
    self.inputInfo['SamplerType'] = self.type

  def localFinalizeActualSampling(self,jobObject,model,myInput):
    """Performs actions after samples have been collected.
      @ In, jobObject, External/InternalRunner object, the job that finished
      @ In, model, Model object, the model that was run
      @ In, myInput, list(str), the input used for the run
      @ Out, None
    """
    #check if all sampling is done
    if self.jobHandler.isFinished(): self.batchDone = True
    else: self.batchDone = False
    #batchDone is used to check if the sampler should find new points.

  def _addNewPoints(self,SG=None):
    """
      Sort through sparse grid and add any new needed points
      @ In, SG, SparseGrid (optional), sparse grid to comb for new points
      @ Out, None
    """
    if SG is None: SG = self.sparseGrid
    for pt in SG.points()[:]:
      self.pointsNeededToMakeROM.add(pt) #sets won't store redundancies
      if pt not in self.neededPoints and pt not in self.existing.keys():
        self.newSolutionSizeShouldBe+=1
        self.neededPoints.append(pt)

  def _convergence(self,poly,rom,target):
    """
      Checks the convergence of the adaptive index set via one of (someday) several ways, currently "variance"
      @ In, poly, list(int), the polynomial index to check convergence for
      @ In, rom, SupervisedEngine, the GaussPolynomialROM object with respect to which we check convergence
      @ In, target, string, target to check convergence with respect to
      @ Out, float, estimated impact factor for this index set and sparse grid
    """
    if self.convType.lower()=='variance':
      impact = rom.polyCoeffDict[poly]**2 / sum(rom.polyCoeffDict[p]**2 for p in rom.polyCoeffDict.keys())
    #FIXME 'coeffs' has to be updated to fit in the new rework before it can be used.
#    elif self.convType.lower()=='coeffs':
#      #new = self._makeARom(rom.sparseGrid,rom.indexSet).SupervisedEngine[target]
#      tot = 0 #for L2 norm of coeffs
#      if self.oldSG != None:
#        oSG,oSet = self._makeSparseQuad()
#        old = self._makeARom(oSG,oSet).SupervisedEngine[target]
#      else: old=None
#      for coeff in new.polyCoeffDict.keys():
#        if old!=None and coeff in old.polyCoeffDict.keys():
#          n = new.polyCoeffDict[coeff]
#          o = old.polyCoeffDict[coeff]
#          tot+= (n - o)**2
#        else:
#          tot+= new.polyCoeffDict[coeff]**2
#      impact = np.sqrt(tot)
    else: self.raiseAnError(KeyError,'Unexpected convergence criteria:',self.convType)
    return impact

  def _estimateImpact(self,idx):
    """
      Estimates the impact of polynomial with index idx by considering the product of its predecessor impacts.
      @ In, idx, tuple(int), polynomial index
      @ Out, None
    """
    #initialize
    for t in self.targets: self.expImpact[t][idx] = 1.
    have = 0 #tracks the number of preceeding terms I have (e.g., terms on axes have less preceeding terms)
    #create a list of actual impacts for predecessors of idx
    predecessors = {}
    for t in self.targets:
      predecessors[t]=[]
    for i in range(len(self.features)):
      subidx = list(idx)
      if subidx[i]>0:
        subidx[i] -= 1
        for t in self.targets:
          predecessors[t].append(self.actImpact[t][tuple(subidx)])
      else: continue #on an axis or axial plane
    #estimated impact is the product of the predecessor impacts raised to the power of the number of predecessors
    for t in self.targets:
      #raising each predecessor to the power of the predecessors makes a more fair order-of-magnitude comparison
      #  for indices on axes -> otherwise, they tend to be over-emphasized
      self.expImpact[t][idx] = np.prod(np.power(np.array(predecessors[t]),1.0/len(predecessors[t])))

  def _finalizeROM(self,rom=None):
    """
      Initializes final target ROM with necessary objects for training.
      @ In, rom, optional GaussPolynomailROM object, the rom to initialize, defaults to target rom
      @ Out, None
    """
    if rom == None: rom = self.ROM
    self.raiseADebug('No more samples to try! Declaring sampling complete.')
    #initialize final rom with final sparse grid and index set
    for target,SVL in rom.SupervisedEngine.items():
      SVL.initialize({'SG':self.sparseGrid,
                      'dists':self.dists,
                      'quads':self.quadDict,
                      'polys':self.polyDict,
                      'iSet':self.indexSet,
                      'numRuns':len(self.pointsNeededToMakeROM)-self.unfinished})

  def _findHighestImpactIndex(self,returnValue=False):
    """
      Finds and returns the index with the highest average expected impact factor across all targets
      Can optionally return the value of the highest impact, as well.
      @ In, returnValue, bool optional, returns the value of the index if True
      @ Out, tuple(int), polynomial index with greatest expected effect
    """
    point = None
    avg = 0
    for pt in self.expImpact.values()[0].keys():
      new = sum(self.expImpact[t][pt] for t in self.targets)/len(self.targets)
      if avg < new:
        avg = new
        point = pt
    self.raiseADebug('Highest impact point is',point,'with expected average impact',avg)
    if returnValue: return point,avg
    else: return point

  def _integrateFunction(self,sg,r,i):
    """
      Uses the sparse grid sg to effectively integrate the r-th moment of the model.
      @ In, sg, SparseGrid, sparseGrid object
      @ In, r, int, integer moment
      @ In, i, int, index of target to evaluate
      @ Out, float, approximate integral
    """
    tot=0
    for n in range(len(sg)):
      pt,wt = sg[n]
      if pt not in self.existing.keys():
        self.raiseAnError(RuntimeError,'Trying to integrate with point',pt,'but it is not in the solutions!')
      tot+=self.existing[pt][i]**r*wt
    return tot

  def _makeARom(self,grid,inset):
    """
      Generates a GaussPolynomialRom object using the passed in sparseGrid and indexSet,
      otherwise fundamentally a copy of the end-target ROM.
      @ In, grid, SparseGrid, sparseGrid
      @ In, inset, IndexSet, indexSet
      @ Out, GaussPolynomialROM object
    """
    #deepcopy prevents overwriting
    rom  = copy.deepcopy(self.ROM) #preserves interpolation requests via deepcopy
    sg   = copy.deepcopy(grid)
    iset = copy.deepcopy(inset)
    sg.messageHandler   = self.messageHandler
    iset.messageHandler = self.messageHandler
    rom.messageHandler  = self.messageHandler
    for svl in rom.SupervisedEngine.values():
      svl.initialize({'SG'   :sg,
                      'dists':self.dists,
                      'quads':self.quadDict,
                      'polys':self.polyDict,
                      'iSet' :iset
                      })
    #while the training won't always need all of solns, it is smart enough to take what it needs
    rom.train(self.solns)
    return rom

  def _makeSparseQuad(self,points=[]):
    """
      Generates a sparseGrid object using the self.indexSet adaptively established points
      as well as and additional points passed in (often the indexSet's adaptive points).
      @ In, points, list(tuple(int)), points
      @ Out, SparseGrid
    """
    sparseGrid = Quadratures.SparseQuad()
    iset = IndexSets.returnInstance('Custom',self)
    iset.initialize(self.features,self.importanceDict,self.maxPolyOrder)
    iset.setPoints(self.indexSet.points)
    iset.addPoints(points)
    sparseGrid.initialize(self.features,iset,self.dists,self.quadDict,self.jobHandler,self.messageHandler)
    return sparseGrid

  def _printToLog(self):
    """
      Prints adaptive state of this sampler to the log file.
      @ In, None
      @ Out, None
    """
    self.logCounter+=1
    pl = 4*len(self.features)+1
    f = file(self.logFile,'a')
    f.writelines('===================== STEP %i =====================\n' %self.logCounter)
    f.writelines('\nNumber of Runs: %i\n' %len(self.pointsNeededToMakeROM))
    f.writelines('Error: %1.9e\n' %self.error)
    f.writelines('Features: %s\n' %','.join(self.features))
    f.writelines('\nExisting indices:\n')
    f.writelines('    {:^{}}:'.format('poly',pl))
    for t in self.targets:
      f.writelines('  {:<16}'.format(t))
    f.writelines('\n')
    for idx in self.indexSet.points:
      f.writelines('    {:^{}}:'.format(idx,pl))
      for t in self.targets:
        f.writelines('  {:<9}'.format(self.actImpact[t][idx]))
      f.writelines('\n')
    f.writelines('\nPredicted indices:\n')
    f.writelines('    {:^{}}:'.format('poly',pl))
    for t in self.targets:
      f.writelines('  {:<16}'.format(t))
    f.writelines('\n')
    for idx in self.expImpact.values()[0].keys():
      f.writelines('    {:^{}}:'.format(idx,pl))
      for t in self.targets:
        f.writelines('  {:<9}'.format(self.expImpact[t][idx]))
      f.writelines('\n')
    f.writelines('===================== END STEP =====================\n')
    f.close()

  def _updateQoI(self):
    """
      Updates Reduced Order Models (ROMs) for Quantities of Interest (QoIs), as well as impact parameters and estimated error.
      @ In, None
      @ Out, None
    """
    #add active (finished) points to the sparse grid
    for active in list(self.inTraining):
      #add point to index set
      self.indexSet.accept(active)
      self.sparseGrid = self._makeSparseQuad()
      for t in self.targets:
        del self.expImpact[t][active]
      self.inTraining.remove(active)
    #update all the impacts
    rom = self._makeARom(self.sparseGrid,self.indexSet)
    for poly in self.indexSet.points:
      for t in self.targets:
        impact = self._convergence(poly,rom.SupervisedEngine[t],t)
        self.actImpact[t][poly] = impact

  def _writeConvergencePoint(self,runPoint):
    """
      Writes XML out for this ROM at this point in the run
      @ In, runPoint, int, the target runs for this statepoint
      @ Out, None
    """
    fname = self.studyFileBase+str(runPoint)
    self.raiseAMessage('Preparing to write state %i to %s.xml...' %(runPoint,fname))
    rom = copy.deepcopy(self.ROM)
    self._finalizeROM(rom)
    rom.train(self.solns)
    options = {'filenameroot':fname, 'what':'all'}
    rom.printXML(options)

  def _writePickle(self,runPoint):
    """
      Writes pickle for this ROM at this point in the run
      @ In, runPoint, int, the target runs for this statepoint
      @ Out, None
    """
    fname = self.studyFileBase+str(runPoint)
    self.raiseAMessage('Writing ROM at state %i to %s.pk...' %(runPoint,fname))
    rom = copy.deepcopy(self.ROM)
    self._finalizeROM(rom)
    rom.train(self.solns)
    pickle.dump(rom,file(fname+'.pk','w'))

#
#
#
#
class Sobol(SparseGridCollocation):
  def __init__(self):
    """
    Default Constructor that will initialize member variables with reasonable
    defaults or empty lists/dictionaries where applicable.
    @ In, None
    @ Out, None
    """
    Grid.__init__(self)
    self.type           = 'SobolSampler'
    self.printTag       = 'SAMPLER SOBOL'
    self.assemblerObjects={}    #dict of external objects required for assembly
    self.maxPolyOrder   = None  #L, the relative maximum polynomial order to use in any dimension
    self.sobolOrder     = None  #S, the order of the HDMR expansion (1,2,3), queried from the sobol ROM
    self.indexSetType   = None  #the type of index set to use, queried from the sobol ROM
    self.polyDict       = {}    #varName-indexed dict of polynomial types
    self.quadDict       = {}    #varName-indexed dict of quadrature types
    self.importanceDict = {}    #varName-indexed dict of importance weights
    self.references     = {}    #reference (mean) values for distributions, by var
    self.solns          = None  #pointer to output dataObjects object
    self.ROM            = None  #pointer to sobol ROM
    self.jobHandler     = None  #pointer to job handler for parallel runs
    self.doInParallel   = True  #compute sparse grid in parallel flag, recommended True
    self.existing       = []
    self.distinctPoints = set() #tracks distinct points used in creating this ROM

    self._addAssObject('ROM','1')

  def _localWhatDoINeed(self):
    """
      Used to obtain necessary objects.
      @ In, None
      @ Out, None
    """
    gridDict = Grid._localWhatDoINeed(self)
    gridDict['internal'] = [(None,'jobHandler')]
    return gridDict

  def _localGenerateAssembler(self,initDict):
    """
      Used to obtain necessary objects.
      @ In, initDict, dict, dictionary of objects required to initialize
      @ Out, None
    """
    Grid._localGenerateAssembler(self, initDict)
    self.jobHandler = initDict['internal']['jobHandler']
    self.dists = self.transformDistDict()

  def localInitialize(self):
    """
      Initializes Sampler, including building sub-ROMs for Sobol decomposition.  Note that re-using this
      sampler will destroy any ROM trained and attached to this sampler, and can be retrained after sampling.
      @ In, None
      @ Out, None
    """
    for key in self.assemblerDict.keys():
      if 'ROM' in key:
        indice = 0
        for value in self.assemblerDict[key]:
          self.ROM = self.assemblerDict[key][indice][3]
          indice += 1
    #make combination of ROMs that we need
    self.targets  = self.ROM.SupervisedEngine.keys()
    SVLs = self.ROM.SupervisedEngine.values()
    SVL = utils.first(SVLs)
    self.sobolOrder = SVL.sobolOrder
    self._generateQuadsAndPolys(SVL)
    self.features = SVL.features
    needCombos = itertools.chain.from_iterable(itertools.combinations(self.features,r) for r in range(self.sobolOrder+1))
    self.SQs={}
    self.ROMs={} #keys are [target][combo]
    for t in self.targets: self.ROMs[t]={}
    for combo in needCombos:
      if len(combo)==0:
        continue
      distDict={}
      quadDict={}
      polyDict={}
      imptDict={}
      limit=0
      for c in combo:
        distDict[c]=self.distDict[c]
        quadDict[c]=self.quadDict[c]
        polyDict[c]=self.polyDict[c]
        imptDict[c]=self.importanceDict[c]
      iset=IndexSets.returnInstance(SVL.indexSetType,self)
      iset.initialize(combo,imptDict,SVL.maxPolyOrder)
      self.SQs[combo] = Quadratures.SparseQuad()
      self.SQs[combo].initialize(combo,iset,distDict,quadDict,self.jobHandler,self.messageHandler)
      # initDict is for SVL.__init__()
      initDict={'IndexSet'       :iset.type,        # type of index set
                'PolynomialOrder':SVL.maxPolyOrder, # largest polynomial
                'Interpolation'  :SVL.itpDict,      # polys, quads per input
                'Features'       :','.join(combo),  # input variables
                'Target'         :None}             # set below, per-case basis
      #initializeDict is for SVL.initialize()
      initializeDict={'SG'   :self.SQs[combo],      # sparse grid
                      'dists':distDict,             # distributions
                      'quads':quadDict,             # quadratures
                      'polys':polyDict,             # polynomials
                      'iSet' :iset}                 # index set
      for name,SVL in self.ROM.SupervisedEngine.items():
        initDict['Target']     = SVL.target
        self.ROMs[name][combo] = SupervisedLearning.returnInstance('GaussPolynomialRom',self,**initDict)
        self.ROMs[name][combo].initialize(initializeDict)
        self.ROMs[name][combo].messageHandler = self.messageHandler
    #if restart, figure out what runs we need; else, all of them
    if self.restartData != None:
      self.solns = self.restartData
      self._updateExisting()
    #make combined sparse grids
    self.references={}
    for var in self.features:
      self.references[var]=self.distDict[var].untruncatedMean()
    self.pointsToRun=[]
    #make sure reference case gets in there
    newpt = np.zeros(len(self.features))
    for v,var in enumerate(self.features):
      newpt[v] = self.references[var]
    self.pointsToRun.append(tuple(newpt))
    self.distinctPoints.add(tuple(newpt))
    #now do the rest
    for combo,rom in utils.first(self.ROMs.values()).items(): #each target is the same, so just for each combo
      SG = rom.sparseGrid #they all should have the same sparseGrid
      SG._remap(combo)
      for l in range(len(SG)):
        pt,wt = SG[l]
        newpt = np.zeros(len(self.features))
        for v,var in enumerate(self.features):
          if var in combo: newpt[v] = pt[combo.index(var)]
          else: newpt[v] = self.references[var]
        newpt=tuple(newpt)
        self.distinctPoints.add(newpt)
        if newpt not in self.pointsToRun:# and newpt not in existing: #the second half used to be commented...
          self.pointsToRun.append(newpt)
    self.limit = len(self.pointsToRun)
    self.raiseADebug('Needed points: %i' %self.limit)
    initdict={'ROMs':None,
              'SG':self.SQs,
              'dists':self.distDict,
              'quads':self.quadDict,
              'polys':self.polyDict,
              'refs':self.references,
              'numRuns':len(self.distinctPoints)}
    for target in self.targets:
      initdict['ROMs'] = self.ROMs[target]
      self.ROM.SupervisedEngine[target].initialize(initdict)

  def localGenerateInput(self,model,myInput):
    """
      Generates an input. Parameters inherited.
      @ In, model, Model
      @ In, myInput, list(str)
    """
    found=False
    while not found:
      try: pt = self.pointsToRun[self.counter-1]
      except IndexError: raise utils.NoMoreSamplesNeeded
      if pt in self.existing:
        self.raiseADebug('point found in restart:',pt)
        self.counter+=1
        if self.counter==self.limit: raise utils.NoMoreSamplesNeeded
        continue
      else:
        self.raiseADebug('point found to run:',pt)
        found=True
      for v,varName in enumerate(self.features):
        self.values[varName] = pt[v]
        self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(self.values[varName])
        self.inputInfo['ProbabilityWeight-'+varName.replace(",","-")] = self.inputInfo['SampledVarsPb'][varName]
      self.inputInfo['PointProbability'] = reduce(mul,self.inputInfo['SampledVarsPb'].values())
      #self.inputInfo['ProbabilityWeight'] =  N/A
      self.inputInfo['SamplerType'] = 'Sparse Grids for Sobol'
#
#
#
#
class AdaptiveSobol(Sobol,AdaptiveSparseGrid):
  """
  Adaptive Sobol sampler to obtain points adaptively for training a HDMR ROM.
  """
  def __init__(self):
    """
    The constructor.
    @ In, None
    @ Out, None
    """
    Sobol.__init__(self)

    #identification
    self.type            = 'AdaptiveSobolSampler'
    self.printTag        = 'SAMPLER ADAPTIVE SOBOL'
    self.stateCounter    = 0       #counts number of times adaptive step moves forward

    #input parameters
    self.maxSobolOrder   = None    #largest dimensionality of a subset combination
    #self.maxPolyOrder    = None   #largest polynomial order to use in subset sparse grids #TODO maybe someday
    self.maxRuns         = None    #most runs to allow total before quitting
    self.convValue       = None    #value to converge adaptive sampling to
    self.tweakParam      = 1.0     #ranges 0 (only polynomials) to 2 (only subsets)
    self.statesFile      = None    #file to log the progression of the adaptive sampling
    self.subVerbosity    = 'quiet' #verbosity level for the ROMs, samplers, dataobjects created within this sampler

    #assembly objects
    self.solns           = None    #solution database, PointSet data object
    self.ROM             = None    #HDMR rom that will be constructed with the samples found here

    #storage dictionaries
    self.ROMs            = {} #subset reduced-order models by target,subset: self.ROMs[target][subset]
    self.SQs             = {} #stores sparse grid quadrature objects
    self.samplers        = {} #stores adaptive sparse grid sampling objects
    self.romShell        = {} #stores Model.ROM objects for each subset
    self.iSets           = {} #adaptive index set objects by target,subset
    self.pointsNeeded    = {} #by subset, the points needed for next step in adaptive SG sampler
    self.pointsCollected = {} #by subset, the points collected for next stip in adaptive SG sampler
    self.subsets         = {} #subset gPC ROMs to be used in full HDMR ROM that have at least started training
    self.references      = {} #mean-value cut reference points by variable
    self.useSet          = {} #accepted subsets and the associated ROMs, as useSet[subset][target]

    #convergence parameters
    self.subsetImpact    = {}    #actual impact on variance by subset combo
    self.subsetExpImpact = {}    #estimated impact on variance by subset combo
    self.done            = False #boolean to track if we've converged, or gone over limit
    self.distinctPoints  = set() #list of points needed to make this ROM, for counting purposes
    self.numConverged    = 0     #tracking for persistance
    self.persistence     = 2     #set in input, the number of successive converges to require

    #convergence study
    self.doingStudy      = False  #true if convergenceStudy node defined for sampler
    self.studyFileBase   = 'out_' #can be replaced in input, not used if not doingStudy
    self.studyPoints     = []     #list of ints, runs at which to record a state
    self.studyPickle     = False  #if true, creates a pickle of rom at statepoints

    #attributes
    self.features        = None #ROM features of interest, also input variable list
    self.targets         = None #ROM outputs of interest

    #point lists
    self.existing        = {}       #points from restart and calculations, and their solutions
    self.sorted          = []       #points that have been sorted into appropriate objects
    self.submittedNotCollected = [] #list of points that have been generated but not collected
    self.inTraining      = []       #usually just one tuple, unless multiple items in simultaneous training

    self._addAssObject('TargetEvaluation','1')

  def localInputAndChecks(self,xmlNode):
    """
    Extended readMoreXML.
    @ In, xmlNode, xmlNode, with head AdaptiveSobol
    @ Out, None
    """
    Sobol.localInputAndChecks(self,xmlNode)
    conv = xmlNode.find('Convergence')
    studyNode = xmlNode.find('convergenceStudy')
    if conv is None: self.raiseAnError(IOError,'"Convergence" node not found in input!')
    #self.convType      = conv.get('target',None) #TODO not implemented.  Currently only does variance.
    for child in conv:
      if   child.tag == 'relTolerance'   : self.convValue     = float(child.text)
      elif child.tag == 'maxRuns'        : self.maxRuns       =   int(child.text)
      elif child.tag == 'maxSobolOrder'  : self.maxSobolOrder =   int(child.text)
      #elif child.tag== 'maxPolyOrder'   : self.maxPolyOrder  =   int(child.text) #TODO someday maybe.
      elif child.tag == 'progressParam'  : self.tweakParam    = float(child.text)
      elif child.tag == 'logFile'        : self.statesFile    =  file(child.text,'w')
      elif child.tag == 'subsetVerbosity': self.subVerbosity  =       child.text.lower()
    if not 0 <= self.tweakParam <= 2:
      self.raiseAnError(IOError,'progressParam must be between 0 (only add polynomials) and 2 (only add subsets) (default 1).  Input value was',self.tweakParam,'!')
    if self.subVerbosity not in ['debug','all','quiet','silent']:
      self.raiseAWarning('subsetVerbosity parameter not recognized:',self.subVerbosity,' -> continuing with "quiet"')
      self.subVerbosity = 'quiet'
    if studyNode is not None:
      self.doingStudy = True
      self.studyPoints = studyNode.find('runStatePoints').text
      filebaseNode = studyNode.find('baseFilename')
      self.studyPickle = studyNode.find('pickle') is not None
      if filebaseNode is None:
        self.raiseAWarning('No baseFilename specified in convergenceStudy node!  Using "%s"...' %self.studyFileBase)
      else:
        self.studyFileBase = studyNode.find('baseFilename').text
      if self.studyPoints is None:
        self.raiseAnError(IOError,'convergenceStudy node was included, but did not specify the runStatePoints node!')
      else:
        try:
          self.studyPoints = list(int(i) for i in self.studyPoints.split(','))
        except ValueError as e:
          self.raiseAnError(IOError,'Convergence state point not recognizable as an integer!',e)
        self.studyPoints.sort()

  def localInitialize(self):
    """
    Initializes this sampler, building some starting subset roms for Sobol decomposition.
    @ In, None
    @ Out, None
    """
    #set up assembly-based objects
    self.solns = self.assemblerDict['TargetEvaluation'][0][3]
    self.ROM   = self.assemblerDict['ROM'][0][3]
    SVLs = self.ROM.SupervisedEngine.values()
    SVL = SVLs[0]
    self.features = SVL.features
    self.targets = self.ROM.initializationOptionDict['Target'].split(',')
    for t in self.targets:
      self.ROMs[t]            = {}
      self.subsetImpact[t]    = {}
    #generate quadratures and polynomials
    self._generateQuadsAndPolys(SVL)
    #set up reference case
    for var,dist in self.distDict.items():
      self.references[var] = dist.untruncatedMean()
    #set up first subsets, the mono-dimensionals
    self.firstCombos = list(itertools.chain.from_iterable(itertools.combinations(self.features,r) for r in [0,1]))
    for c in self.firstCombos[:]:
      #already did reference case, so remove it
      if len(c)<1:
        self.firstCombos.remove(c)
        continue
      self._makeSubsetRom(c)
      self.inTraining.append( ('poly',c,self.samplers[c]._findHighestImpactIndex()) )
      #get the points needed to push this subset forward
      self._retrieveNeededPoints(c)
    #update the solution storage array
    self._updateExisting()
    #set up the nominal point for a run
    #  Note: neededPoints is not going to be the main method for queuing points, but it will take priority.
    self.neededPoints = [tuple(self.references[var] for var in self.features)]

  def localStillReady(self,ready):
    """
    Determines if sampler is prepared to provide another input.  If not, and
    if jobHandler is finished, this will end sampling.
    @ In, ready, boolean
    @ Out, boolean
    """
    #if we've already capped runs or are otherwise done, return False
    if self.done:
      self.raiseADebug('Sampler is already done; no more runs available.')
      return False
    #if for some reason we're not ready already, just return that
    if not ready: return ready
    #collect points that have been run
    self._sortNewPoints()
    #if starting set of points is not done, just return
    if len(self.neededPoints)>0: return True
    #look for any new points to run, if we don't have any
    while sum(len(self.pointsNeeded[s[1]]) for s in self.inTraining)<1:
      #since we don't need any points to sample, we can train
      for item in self.inTraining:
        sub = item[1]
        # whether we were training a poly or a new subset, we need to update the subset
        self._updateSubset(sub)
      # now that we've updated the subsets, we can train them and update the actual and expected impacts
      for item in self.inTraining:
        sub = item[1]
        #train it
        self.samplers[sub]._finalizeROM()
        self.romShell[sub].train(self.samplers[sub].solns)
        #update the actual impacts
        for t in self.targets:
          self.subsetImpact[t][sub] = self._calcActualImpact(sub,t)
          if sub in self.subsetExpImpact.keys(): del self.subsetExpImpact[sub]
        #add new/update expected impacts of subsets
        self._generateSubsets(sub)
        #remove this item from the training queue
        self.inTraining.remove(item)
      #are we at maxRuns?  If so, we need to be done.
      if self.maxRuns is not None and len(self.distinctPoints)>self.maxRuns:
        self.raiseAMessage('Maximum runs reached!  No new polynomials or subsets will be added...')
        self._earlyExit()
        return False
      #get next-most influential poly/subset to add, update global error estimate
      which, todoSub, poly = self._getLargestImpact()
      self.raiseAMessage('Next: %6s %8s%12s' %(which,','.join(todoSub),str(poly)),'| error: %1.4e' %self.error,'| runs: %i' %len(self.distinctPoints))
      if self.statesFile is not None: self._printState(which,todoSub,poly)
      #if doing a study and past a statepoint, record the statepoint
      if self.doingStudy:
        while len(self.studyPoints)>0 and len(self.distinctPoints) > self.studyPoints[0]:
          self._writeConvergencePoint(self.studyPoints[0])
          if self.studyPickle: self._writePickle(self.studyPoints[0])
          #remove the point
          if len(self.studyPoints)>1: self.studyPoints=self.studyPoints[1:]
          else: self.studyPoints = []
      #are we converged?
      if self.error < self.convValue:
        self.raiseAMessage('Convergence achieved!  No new polynomials or subsets will be added...')
        self._earlyExit()
        return False
      #otherwise, we're not done...
      #  -> use the information from _getLargestImpact to add either a poly or a subset
      if which == 'poly':
        self.inTraining.append(('poly',todoSub,self.samplers[todoSub]._findHighestImpactIndex()))
        samp = self.samplers[todoSub]
        #add the poly to the subset sampler's training queue
        samp.inTraining.add(self.inTraining[-1][2])
        #add new necessary points to subset sampler
        samp._addNewPoints(samp._makeSparseQuad([self.inTraining[-1][2]]))
        #get those new needed points and store them locally
        self._retrieveNeededPoints(todoSub)
      elif which == 'subset':
        self._makeSubsetRom(todoSub)
        for t in self.targets: #TODO might be redundant, if you're cleaning up code.
          self.ROMs[t][todoSub] = self.romShell[todoSub].SupervisedEngine[t]
        self.inTraining.append(('subset',todoSub,self.romShell[todoSub]))
        #get initial needed points and store them locally
        self._retrieveNeededPoints(todoSub)
    #END while loop
    #if all the points we need are currently submitted but not collected, we have no points to offer
    if not self._havePointsToRun(): return False
    #otherwise, we can submit points!
    return True

  def localGenerateInput(self,model,oldInput):
    """
    Generates an input to be run.
    @ In, model, Model, the model to run
    @ In, oldInput, list(str), the old input used
    @ Out, None
    """
    #note: pointsNeeded is the collection of points needed by sampler,
    #      while neededPoints is just the reference point that needs running
    #if there's a point that THIS sampler needs, prioritize it
    if len(self.neededPoints)>0:
      pt = self.neededPoints.pop()
    #otherwise, take from the highest-impact sampler's needed points
    else:
      #pointsNeeded is in order from least to most impactful, so list reverse of keys.
      subsets = self.pointsNeeded.keys()
      subsets.reverse()
      #now they're in order of impact.  Look for the next point to run.
      found = False
      for sub in subsets:
        for p in self.pointsNeeded[sub]:
          pt = self._expandCutPoint(sub,p)
          if pt not in self.submittedNotCollected:
            self.submittedNotCollected.append(pt)
            found = True
            break
        if found: break
      if not found:
        #this should not occur, but is a good sign something went wrong in developing.
        self.raiseAnError(RuntimeError,'No point was found to generate!  This should not be possible...')
    #add the number of necessary distinct points to a set (so no duplicates).
    self.distinctPoints.add(pt)
    #set up the run.
    for v,varName in enumerate(self.features):
      self.values[varName] = pt[v]
      self.inputInfo['SampledVarsPb'][varName] = self.distDict[varName].pdf(self.values[varName])
    self.inputInfo['PointsProbability'] = reduce(mul,self.inputInfo['SampledVarsPb'].values())
    self.inputInfo['SamplerType'] = 'Adaptive Sobol Sparse Grids'

  def _addPointToDataObject(self,subset,point):
    """
    Adds a cut point to the data object for the subset sampler.
    @ In, subset, tuple(string), the cut point
    @ In, point, tuple(int), the cut point to add
    @ Out, None
    """
    pointSet = self.samplers[subset].solns
    #first, check if the output is in the subset's existing solution set already
    if point in self.samplers[subset].existing.keys():
      output = self.samplers[subset].existing[point]
    #if not, get it locally, but it costs more because we have to expand the cut point
    else:
      output = self.existing[self._expandCutPoint(subset,point)]
      self.samplers[subset].existing[point] = output
    #add the point to the data set.
    for v,var in enumerate(subset):
      pointSet.updateInputValue(var,point[v])
    for v,var in enumerate(self.targets):
      pointSet.updateOutputValue(var,output[v])

  def _calcActualImpact(self,subset,target):
    """
    Calculates the total impact of the current set.
    @ In, subset, tuple(str), new subset for which impact is considered
    @ Out, float, the "error" reduced by acquiring the new point
    """
    #add the new term to the use set
    if subset not in self.useSet.keys(): self.useSet[subset] = {}
    self.useSet[subset][target] = self.ROMs[target][subset]
    #compute the impact as the contribution to the variance
    totvar = 0
    for s in self.useSet.keys():
      totvar += self.ROMs[target][s].__variance__()
    #avoid div by 0 error
    if totvar > 0:
      return self.ROMs[target][subset].__variance__()/totvar
    else:
      return self.ROMs[target][subset].__variance__()

  def _calcExpImpact(self,subset,target):
    """
    Estimates the importance (impact) of the subset, based on its predecessors
    @ In, subset, tuple(str), the subset spanning the cut plane of interest
    @ In, target, str, target to estimate impact for
    @ Out, float, the expected impact
    """
    #estimate impact as the product of predecessors
    #TODO this could be improved for higher dimensions, ie s(a,b,c) = s(a)*s(b)*s(c) or s(a,b)*s(c) or ?
    #for now, using product of all of the immediate predecessors, which seems to be an okay guess
    impact = 1
    for sub in self.useSet.keys():
      #only use immediate predecessor
      if len(sub)<len(subset)-1: continue
      #use builtin set mechanics to figure out if "sub" is a subset of "subset"
      if set(sub).issubset(set(subset)): #confusing naming!  if sub is a predecessor of subset...
        impact*=self.subsetImpact[target][sub]
    return impact

  def _checkCutPoint(self,subset,pt):
    """
    Determines if a point is in the cut set for the features in the subset.
    @ In, subset, tuple(str), desired subset features
    @ In, pt, tuple(float), the full point
    @ Out, bool, True if pt only varies from reference in dimensions within the subset
    """
    for v,var in enumerate(self.features):
      if var in subset: continue #it's okay to vary if you're in the subset
      if pt[v] != self.references[var]: #we're outside the cut plane.
        return False
    return True #only if nothing outside the cut plane

  def _expandCutPoint(self,subset,pt):
    """
    Takes a trimmed point from the cut plane and expands it to include the reference values.
    @ In, subset, tuple(str), the subset describing this cut plane
    @ In, pt, tuple(float), the trimmed cutpoint to expand
    @ Out, tuple(float), full expanded points
    """
    #initialize full point
    full = np.zeros(len(self.features))
    for v,var in enumerate(self.features):
      #if it's a varying point (spanned by the subset), keep its value
      if var in subset: full[v] = pt[subset.index(var)]
      #else, use the reference value
      else: full[v] = self.references[var]
    return tuple(full)

  def _extractCutPoint(self,subset,pt):
    """
    Trims the dimensionality of pt to the cut plane spanning subset
    @ In, subset, tuple(str), the cut plane to trim to
    @ In, pt, tuple(float), the point to extract
    @ Out, tuple(pt,vals), extracted point with cardinality equal to the subset cardinality
    """
    #slightly faster all in one line.
    cutInp = tuple(pt[self.features.index(var)] for var in subset)
    return cutInp

  def _earlyExit(self):
    """
    In the event the sampler has to terminate before normal completion, this helps to assure
    a usable set of ROMs make it to the HDMR ROM.
    @ In, None
    @ Out, None
    """
    #remove unfinished subsets
    toRemove = []
    for subset in self.ROMs.values()[0]:
      if subset not in self.useSet.keys():
        toRemove.append(subset)
    for subset in toRemove:
      for t in self.targets:
        del self.ROMs[t][subset]
    #finalize subsets
    for sub in self.useSet.keys():
      self._finalizeSubset(sub)
    #set completion trigger
    self.done = True
    #note any missing statepoints if doing convergence study
    if self.doingStudy and len(self.studyPoints)>0:
      self.raiseAWarning('In the convergence study, the following numbers of runs were not reached:',self.studyPoints)
    #set up HDMRRom for training
    self._finalizeROM()

  def _finalizeROM(self,rom=None):
    """
    Delivers necessary structures to the HDMRRom object
    @ In, rom, optional HDMRRom object, rom to finalize before training, defaults to target rom
    @ Out, None
    """
    if rom == None: rom = self.ROM
    initDict = {'ROMs':None, # multitarget requires setting individually, below
                'SG':self.SQs,
                'dists':self.distDict,
                'quads':self.quadDict,
                'polys':self.polyDict,
                'refs':self.references,
                'numRuns':len(self.distinctPoints)}
    #initialize each HDMRRom object in the ROM
    for target in self.targets:
      initDict['ROMs'] = copy.deepcopy(self.ROMs[target])
      #remove unfinished subsets
      for subset in self.ROMs.values()[0]:
        if subset not in self.useSet.keys():
          del initDict['ROMs'][subset]
      rom.SupervisedEngine[target].initialize(initDict)

  def _finalizeSubset(self,subset):
    """
    On completion, finalizes the subset by initializing the associated ROM.
    @ In, subset, tuple(str), subset to finalize
    @ Out, None
    """
    sampler = self.samplers[subset]
    #add collected points to sampler's data object, just in case one's missing.  Could be optimized.
    for pt in self.pointsCollected[subset]:
      self._addPointToDataObject(subset,pt)
    #finalize the subset ROM
    sampler._finalizeROM()
    #train the ROM
    self.romShell[subset].train(sampler.solns)
    #store rom in dedicated use set
    for target in self.targets:
      self.useSet[subset][target] = self.romShell[subset].SupervisedEngine[target]

  def _generateSubsets(self,subset):
    """
    Returns a list of the possible subset combinations available, and estimates their impact
    @ In, subset, tuple(str), the leading subset to add more subsets from
    @ Out, None
    """
    #get length of subset
    l = len(subset)
    #we want all combinations of subsets using subset and adding only one more
    #first, get all possible combinations of that length
    #TODO this is wasteful, but I don't know a better way.
    potential = itertools.combinations(self.features,l+1)
    #if all the subset dimensions are in the potential, then it could possibly be used
    #but don't include if it's already there, or if it's in training.
    use = []
    self.raiseADebug('Generating subsets on',subset,'...')
    for p in potential:
      if all(i in p for i in subset):
        if p not in self.useSet.keys():
          if p not in list(s[1] for s in self.inTraining):
            use.append(p)
    if len(use)<1:
      self.raiseADebug('    no new potentials found.')
      return
    #now, look for ones that have all necessary subsets in the use set.
    for p in use:
      if len(p)>self.maxSobolOrder:
        self.raiseADebug('        Discarded',p,'for too large subset cardinality.')
        continue
      #to be included, p needs all of its precedents of lower cardinality to be in the useSet already.
      neededPrecedents = list(itertools.combinations(p,len(p)-1))
      if all(c in self.useSet.keys() for c in neededPrecedents):
        self.raiseADebug('  Adding subset:',p)
        self._makeSubsetRom(p)
        #get expected impact - the max impact among from the targets
        self.subsetExpImpact[p] = max(abs(self._calcExpImpact(p,t)) for t in self.targets)
    #now order the expected impacts so that lowest is first (-1 is highest)
    toSort = zip(self.subsetExpImpact.keys(),self.subsetExpImpact.values())
    toSort.sort(key=itemgetter(1))
    #restore them to the ordered dict.
    self.subsetExpImpact = OrderedDict()
    for key, impact in toSort:
      self.subsetExpImpact[key] = impact

  def _getLargestImpact(self):
    """
    Looks through potential subsets and existing subsets for the most effective polynomial to add
    @ In, None
    @ Out, (str, tuple(str), item ), either 'poly' or 'subset' along with the corresponding subset and either the poly or ''
    """
    #track the total error while we do this
    self.error = 0
    #storage for most impactful polynomial: its impact, the subset it belongs to, and the polynomial index
    maxPolyImpact = 0
    maxPolySubset = None
    poly = None
    #find most effective polynomial among existing subsets
    for subset in self.useSet.keys():
      #if it's already in training, move along
      if any(subset == s[1] for s in self.inTraining): continue
      pt,imp =  self.samplers[subset]._findHighestImpactIndex(returnValue = True)
      #apply tweaking parameter for favoring either polys or subsets
      imp = imp**self.tweakParam * (sum(self.subsetImpact[t][subset] for t in self.targets)/len(self.targets))**(2.-self.tweakParam)
      #update global estimated error
      self.error+=imp
      #update max if necessary
      if maxPolyImpact < imp:
        maxPolyImpact = imp
        maxPolySubset = subset
        poly = pt
    #storage for the most impactful subset: its impact, and the subset
    maxSubsetImpact = 0
    maxSubset = None
    #find the expected most effective subset among potential subsets
    for subset,expImp in self.subsetExpImpact.items():
      #if it's already in training, move along
      if any(subset == s[1] for s in self.inTraining): continue
      #apply favoring tweaking parameter - take abs() to assure fair comparison
      expImp = abs(expImp)**(2.-self.tweakParam)
      #update global expected error remaining
      self.error+=expImp
      #update max if necessary
      if maxSubsetImpact < expImp:
        maxSubsetImpact = expImp
        maxSubset = subset
    #which champion (poly or subset) is more significant? Slightly favour polynomials as a tiebreaker
    if maxPolySubset is None and maxSubset is None:
      self.raiseAnError(RuntimeError,'No polynomials or subsets found to consider!')
    if maxPolyImpact >= maxSubsetImpact:
      self.raiseADebug('Most impactful is resolving subset',maxPolySubset)
      return 'poly',maxPolySubset,poly
    else:
      self.raiseADebug('Most impactful is adding subset',maxSubset)
      return 'subset',maxSubset,''

  def _havePointsToRun(self):
    """
    Determines if there are points to submit to the jobHandler.
    @ In, None
    @ Out, bool, true if there are points to run
    """
    #check if there's any subsets in the useSet that need points run, that haven't been queued
    for subset in self.useSet.keys():
      for pt in self.pointsNeeded[subset]:
        if self._expandCutPoint(subset,pt) not in self.submittedNotCollected:
          return True
    #check if there's anything in training that needs points run, that haven't been queued
    for item in self.inTraining:
      subset = item[1]
      for pt in self.pointsNeeded[subset]:
        if self._expandCutPoint(subset,pt) not in self.submittedNotCollected:
          return True
    #if not, we have nothing to run.
    return False

  def _makeCutDataObject(self,subset):
    """
    Creates a new PointSet dataobject for a cut subset
    @ In, subset, tuple(str), the subset to make the object for
    @ Out, dataObject
    """
    #create a new data ojbect
    dataObject = DataObjects.returnInstance('PointSet',self)
    dataObject.type ='PointSet'
    #write xml to set up data object
    #  -> name it the amalgamation of the subset parts
    node = ET.Element('PointSet',{'name':'-'.join(subset),'verbosity':self.subVerbosity})
    inp = ET.Element('Input')
    inp.text = ','.join(s for s in subset)
    node.append(inp)
    out = ET.Element('Output')
    out.text = ','.join(self.targets)
    node.append(out)
    #initialize the data object
    dataObject.readXML(node,self.messageHandler)
    return dataObject

  def _makeSubsetRom(self,subset):
    """
    Constructs a ROM for the given subset (but doesn't train it!).
    @ In, subset, tuple(string), subset for cut plane
    @ Out, GaussPolynomialROM object, representing this cut plane (once it gets trained)
    """
    verbosity = self.subVerbosity #sets verbosity of created RAVEN objects
    SVL = self.ROM.SupervisedEngine.values()[0] #an example SVL for most parameters
    #replicate "normal" construction of the ROM
    distDict={}
    quadDict={}
    polyDict={}
    imptDict={}
    limit=0
    dists = {}
    #make use of the keys to get the distributions, quadratures, polynomials, importances we want
    for c in subset:
      distDict[c] = self.distDict[c]
      dists[c] = self.dists[c]
      quadDict[c] = self.quadDict[c]
      polyDict[c] = self.polyDict[c]
      imptDict[c] = self.importanceDict[c]
    #instantiate an adaptive index set for this ROM
    iset = IndexSets.returnInstance('AdaptiveSet',self)
    iset.initialize(subset,imptDict,self.maxPolyOrder)
    iset.verbosity=verbosity
    #instantiate a sparse grid quadrature
    self.SQs[subset] = Quadratures.SparseQuad()
    self.SQs[subset].initialize(subset,iset,distDict,quadDict,self.jobHandler,self.messageHandler)
    #instantiate the SVLs.  Note that we need to call both __init__ and initialize with dictionaries.
    for target in self.targets:
      initDict = {'IndexSet'       : iset.type,
                  'PolynomialOrder': SVL.maxPolyOrder,
                  'Interpolation'  : SVL.itpDict,
                  'Features'       : ','.join(subset),
                  'Target'         : target}
      self.ROMs[target][subset] = SupervisedLearning.returnInstance('GaussPolynomialRom',self,**initDict)
      initializeDict = {'SG'       : self.SQs[subset],
                        'dists'    : distDict,
                        'quads'    : quadDict,
                        'polys'    : polyDict,
                        'iSet'     : iset}
      self.ROMs[target][subset].initialize(initializeDict)
      self.ROMs[target][subset].messageHandler = self.messageHandler
      self.ROMs[target][subset].verbosity = verbosity
    #instantiate the shell ROM that contains the SVLs
    #   NOTE: the shell is only needed so we can call the train method with a data object.
    self.romShell[subset] = Models.returnInstance('ROM',{},self)
    self.romShell[subset].subType = 'GaussPolynomialRom'
    self.romShell[subset].messageHandler = self.messageHandler
    self.romShell[subset].verbosity = verbosity
    self.romShell[subset].initializationOptionDict['Target']=','.join(self.targets)
    self.romShell[subset].initializationOptionDict['Features']=','.join(subset)
    self.romShell[subset].initializationOptionDict['IndexSet']='TotalDegree'
    self.romShell[subset].initializationOptionDict['PolynomialOrder']='1'
    #coordinate SVLs
    for t in self.targets:
      self.romShell[subset].SupervisedEngine[t] = self.ROMs[t][subset]
    #instantiate the adaptive sparse grid sampler for this rom
    samp = returnInstance('AdaptiveSparseGrid',self)
    samp.messageHandler = self.messageHandler
    samp.verbosity      = verbosity
    samp.doInParallel   = self.doInParallel #TODO can't be set by user.
    samp.jobHandler     = self.jobHandler
    samp.convType       = 'variance'
    samp.maxPolyOrder   = self.maxPolyOrder
    samp.distDict       = distDict
    samp.dists          = dists
    samp.assemblerDict['ROM']              = [['','','',self.romShell[subset]]]
    soln = self._makeCutDataObject(subset)
    samp.assemblerDict['TargetEvaluation'] = [['','','',soln]]
    for var in subset: samp.axisName.append(var)
    samp.localInitialize()
    samp.printTag = 'ASG:('+','.join(subset)+')'
    #propogate sparse grid back from sampler #TODO self.SQs might not really be necessary.
    self.SQs[subset] = samp.sparseGrid
    for target in self.targets:
      self.ROMs[target][subset].sparseGrid  = samp.sparseGrid
    self.samplers[subset] = samp
    #initialize pointsNeeded and pointsCollected databases
    self.pointsNeeded[subset] = []
    self.pointsCollected[subset] = []
    #sort already-solved points
    for inp in self.sorted:
      if self._checkCutPoint(subset,inp):
        #get the solution
        soln = self.existing[inp]
        #get the cut point
        cinp = self._extractCutPoint(subset,inp)
        self.samplers[subset].existing[cinp] = soln
        self.pointsCollected[subset].append(cinp)
        self._addPointToDataObject(subset,cinp)
    #get the points needed by the subset samplers and store them locally
    self._retrieveNeededPoints(subset)
    #advance the subset forward if it doesn't have needed points
    if len(self.pointsNeeded[subset])<1:
      self._updateSubset(subset)

  def _printState(self,which,todoSub,poly):
    """
    Debugging tool.  Prints status of adaptive steps. Togglable in input by specifying logFile.
    @ In, which, string, the type of the next addition to make by the adaptive sampler: poly, or subset
    @ In, todoSub, tuple(str), the next subset that will be resolved as part of the adaptive sampling
    @ In, poly, tuple(int), the polynomial within the next subset that will be added to resolve it
    @ Out, None
    """
    #print status, including error; next step to make; and existing, training, and expected values
    self.stateCounter+=1
    self.statesFile.writelines('==================== STEP %s ====================\n' %self.stateCounter)
    #write error, next adaptive move to make in this step
    self.statesFile.writelines('\n\nError: %1.9e\n' %self.error)
    self.statesFile.writelines('Next: %6s %8s %12s\n' %(which,','.join(todoSub),str(poly)))
    #write a summary of the state of each subset sampler: existing points, training points, yet-to-try points, and their impacts on each target
    for sub in self.useSet.keys():
      self.statesFile.writelines('-'*50)
      self.statesFile.writelines('\nsubset %8s with impacts' %','.join(sub))
      for t in self.targets:
        self.statesFile.writelines(    ' [ %4s:%1.6e ] ' %(t,self.subsetImpact[t][sub]))
      self.statesFile.writelines('\n')
      #existing polynomials
      self.statesFile.writelines('ESTABLISHED:\n')
      self.statesFile.writelines('    %12s' %'polynomial')
      for t in self.targets:
        self.statesFile.writelines('  %12s' %t)
      self.statesFile.writelines('\n')
      for coeff in self.romShell[sub].SupervisedEngine.values()[0].polyCoeffDict.keys():
        self.statesFile.writelines('    %12s' %','.join(str(c) for c in coeff))
        for t in self.targets:
          self.statesFile.writelines('  %1.6e' %self.romShell[sub].SupervisedEngine[t].polyCoeffDict[coeff])
        self.statesFile.writelines('\n')
      #polynomials in training
      if any(sub==item[1] for item in self.inTraining): self.statesFile.writelines('TRAINING:\n')
      for item in self.inTraining:
        if sub == item[1]:
          self.statesFile.writelines('    %12s %12s\n' %(sub,item[2]))
      #polynomials on the fringe that aren't being trained
      self.statesFile.writelines('EXPECTED:\n')
      for poly in self.samplers[sub].expImpact.values()[0].keys():
        self.statesFile.writelines('    %12s' %','.join(str(c) for c in poly))
        self.statesFile.writelines('  %1.6e' %self.samplers[sub].expImpact[t][poly])
        self.statesFile.writelines('\n')
    self.statesFile.writelines('-'*50+'\n')
    #other subsets that haven't been started yet
    self.statesFile.writelines('EXPECTED SUBSETS\n')
    for sub,val in self.subsetExpImpact.items():
      self.statesFile.writelines('    %8s: %1.6e\n' %(','.join(sub),val))
    self.statesFile.writelines('\n==================== END STEP ====================\n')

  def _retrieveNeededPoints(self,subset):
    """
    Get the batch of points needed by the subset sampler and transfer them to local variables
    @ In, subset, tuple(str), cut plane dimensions
    @ Out, None
    """
    sampler = self.samplers[subset]
    #collect all the points and store them locally, so we don't have to inquire the subset sampler
    while len(sampler.neededPoints)>0:
      cutpt = sampler.neededPoints.pop()
      fullPoint = self._expandCutPoint(subset,cutpt)
      #if this point already in local existing, put it straight into collected and sampler existing
      if fullPoint in self.existing.keys():
        self.pointsCollected[subset].append(cutpt)
        self._addPointToDataObject(subset,cutpt)
        #add solutions, too
        sampler.existing[cutpt] = self.existing[fullPoint]
      #otherwise, this is a point that needs to be run!
      else:
        self.pointsNeeded[subset].append(cutpt)

  def _sortNewPoints(self):
    """
    Allocates points on cut planes to their respective adaptive sampling data objects.
    @ In, None
    @ Out, None
    """
    #if there's no solutions in the set, no work to do
    if self.solns.isItEmpty(): return
    #update self.exisitng for adaptive sobol sampler (this class)
    AdaptiveSparseGrid._updateExisting(self)
    for inp,soln in self.existing.items():
      #if point already sorted, don't re-do work
      if inp not in self.submittedNotCollected: continue
      #check through neededPoints to find subset that needed this point
      self.raiseADebug('sorting:',inp,soln)
      for subset,needs in self.pointsNeeded.items():
        #check if point in cut for subset
        if self._checkCutPoint(subset,inp):
          self.raiseADebug('...sorting into',subset)
          cutInp = self._extractCutPoint(subset,inp)
          self._addPointToDataObject(subset,cutInp)
          sampler = self.samplers[subset]
          #if needed or not, still add it to the sampler's existing points
          if cutInp not in sampler.existing.keys():
            sampler.existing[cutInp] = soln
          #check if it was requested
          if cutInp in needs:
            #if so, remove the point from Needed and into Collected
            #  - add key if not existing
            self.pointsNeeded[subset].remove(cutInp)
          if subset not in self.pointsCollected.keys(): self.pointsCollected[subset] = []
          self.pointsCollected[subset].append(cutInp)
      self.sorted.append(inp)
      self.submittedNotCollected.remove(inp)

  def _updateSubset(self,subset):
    """
    Updates the index set for the subset, and updates estimated impacts
    @ In, subset, tuple(str), the subset to advance
    @ Out, None
    """
    if len(self.pointsNeeded[subset])<1:
      sampler = self.samplers[subset]
      #update the ROM with the new polynomial point
      sampler._updateQoI()
      #refresh the list of potential points in the index set
      sampler.indexSet.forward(sampler.indexSet.points[-1])
      #update estimated impacts
      for pidx in sampler.indexSet.active:
        sampler._estimateImpact(pidx)

  def _writeConvergencePoint(self,runPoint):
    """
      Writes XML out for this ROM at this point in the run
      @ In, runPoint, int, the target runs for this statepoint
      @ Out, None
    """
    for sub in self.useSet.keys():
      self._finalizeSubset(sub)
    AdaptiveSparseGrid._writeConvergencePoint(self,runPoint)


#
#
#
#

"""
 Interface Dictionary (factory) (private)
"""
__base = 'Sampler'
__interFaceDict = {}
__interFaceDict['MonteCarlo'              ] = MonteCarlo
__interFaceDict['DynamicEventTree'        ] = DynamicEventTree
__interFaceDict['Stratified'              ] = Stratified
__interFaceDict['Grid'                    ] = Grid
__interFaceDict['LimitSurfaceSearch'      ] = LimitSurfaceSearch
__interFaceDict['AdaptiveDynamicEventTree'] = AdaptiveDET
__interFaceDict['FactorialDesign'         ] = FactorialDesign
__interFaceDict['ResponseSurfaceDesign'   ] = ResponseSurfaceDesign
__interFaceDict['SparseGridCollocation'   ] = SparseGridCollocation
__interFaceDict['AdaptiveSparseGrid'      ] = AdaptiveSparseGrid
__interFaceDict['Sobol'                   ] = Sobol
__interFaceDict['AdaptiveSobol'           ] = AdaptiveSobol
__knownTypes = list(__interFaceDict.keys())

def knownTypes():
  return __knownTypes

def addKnownTypes(newDict):
  for name, value in newDict.items():
    __interFaceDict[name]=value
    __knownTypes.append(name)

def returnInstance(Type,caller):
  """
  function used to generate a Sampler class
  @ In, Type : Sampler type
  @ Out,Instance of the Specialized Sampler class
  """
  try: return __interFaceDict[Type]()
  except KeyError: caller.raiseAnError(NameError,'not known '+__base+' type '+Type)

def optionalInputs(Type):
  pass

def mandatoryInputs(Type):
  pass
