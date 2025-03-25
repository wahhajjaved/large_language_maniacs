#!/usr/bin/python
# -*- coding: UTF-8 -*-

# Copyright (C) 2016 Michel Müller, Tokyo Institute of Technology

# This file is part of Hybrid Fortran.

# Hybrid Fortran is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Hybrid Fortran is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with Hybrid Fortran. If not, see <http://www.gnu.org/licenses/>.

import re, sys, copy
import logging
import pdb
from tools.metadata import *
from tools.commons import enum, BracketAnalyzer, Singleton, UsageError, \
	splitTextAtLeftMostOccurrence, splitIntoComponentsAndRemainder, getComponentNameAndBracketContent
from tools.patterns import RegExPatterns
from tools.analysis import SymbolDependencyAnalyzer, SymbolType
from machinery.commons import ConversionOptions, parseSpecification, implement

#   Boxes = Symbol States
#   X -> Transition Texts = Methods being called by parser
#   Other Texts = Helper Functions
#
#                                        +----------------+
#                                        | NOTHING_LOADED |
#                                        +------+---------+
#                                               |
#                                         loadTemplate
#                                               |
#                                        +------v----------+
#                                        | TEMPLATE_LOADED |
#                                        +------+----------+
#                                               |                 X -> (routine entry)
#                                               |  loadDomainDependantEntryNodeAttributes
#                                               |                              ^
#                              +----------------v-----------------------+      |
#                              | DEPENDANT_ENTRYNODE_ATTRIBUTES_LOADED  |      | (module entry)
#                              +----+-----------+-----------------------+      |
#                     X ->          +           |           X ->               |
# +-------------+  loadRoutineNodeAttributes    |   loadModuleNodeAttributes  +-----------+
# |                                 +           |                              |          |
# |                                 |           |                              |          |
# |                                +v-----------v------------------+           |          |
# |                                | ROUTINENODE_ATTRIBUTES_LOADED |    +------+          |
# |                                +---+--------+------------------+    |                 |
# |                                    |        |            X ->       +                 |
# |                                    |        |    loadImportInformation+----------------------------------+
# |             X -> loadDeclaration   |        |               +      +                  |                  |
# |                       +            |        |               |      |                  |                  |
# |                       |           +v--------v-----------+   |      |                  |                  |
# |                       |           | DECLARATION_LOADED  |   |      |                  |                  |
# |                       |           +---------------------+   |      |                  |                  |
# |                       |                                     |      |                  |                  |
# |                       |                                     |      |                  |                  |
# |                       v                                     v      |                  |                  |
# |                       getReorderedDomainsAccordingToDeclaration    |                  |                  |
# |                                                                    |                  |                  |
# |                                                                    |                  |                  |
# |                                                                    |                  |                  |
# |                                                                    |                  |                  |
# |                                                                    |                  |                  |
# +-----------------------------------> loadTemplateAttributes <--------------------------+                  |
#                                         +       +                    |                                     |
#                                         |       |                    |                                     |
#                                         |       |                    |                                     |
#                                         |       |                    |                                     |
#                                         |       |                    |                                     v
#   loadDomains <-------------------------+       +----------------------------------------------------->  loadDeclarationPrefixFromString
#        ^                                                             |
#        |                                                             |
#        |                                                             |
#        |                                                             |
#        +-------------------------------------------------------------+

Init = enum(
	"NOTHING_LOADED",
	"TEMPLATE_LOADED",
	"DEPENDANT_ENTRYNODE_ATTRIBUTES_LOADED",
	"ROUTINENODE_ATTRIBUTES_LOADED",
	"DECLARATION_LOADED"
)

#Set of declaration types that are mutually exlusive for
#declaration lines in Hybrid Fortran.
#-> You cannot mix and match declarations of different types
DeclarationType = enum(
	"UNDEFINED",
	"LOCAL_ARRAY",
	"LOCAL_MODULE_SCALAR",
	"MODULE_ARRAY",
	"FOREIGN_MODULE_SCALAR",
	"FRAMEWORK_ARRAY",
	"MODULE_ARRAY_PASSED_IN_AS_ARGUMENT",
	"OTHER_ARGUMENT",
	"OTHER_ARRAY",
	"OTHER_SCALAR",
	"LOCAL_SCALAR"
)

def limitLength(name):
	return name[:min(len(name), 31)] #cut after 31 chars because of Fortran 90 limitation

def frameworkArrayName(calleeName):
	return "hfimp_%s" %(calleeName)

def dimensionStringFromSpecification(symbolName, specTuple):
	if specTuple[0] == None:
		raise Exception("no declaration found")
	if specTuple[0].find("dimension") >= 0:
		declarationComponents, _ = splitIntoComponentsAndRemainder(specTuple[0])
		for component in declarationComponents:
			componentName, bracketContent = getComponentNameAndBracketContent(component)
			if componentName == "dimension":
				if bracketContent in [None, ""]:
					raise Exception("dimension attribute without content")
				return bracketContent
	if specTuple[1] == None:
		raise Exception("symbol %s not found in specification tuple %s" %(symbolName, specTuple))
	for symbolSpec in specTuple[1]:
		if symbolSpec[0] == symbolName:
			return symbolSpec[1]
	raise Exception("symbol %s not found in specification tuple %s" %(symbolName, specTuple))

def symbolNamesFromSpecificationTuple(specTuple):
	return tuple([
        symbolSpec[0]
        for symbolSpec in specTuple[1]
    ])

def rightHandSpecificationFromDataObjectTuple(dataObjectTuple):
	return "%s(%s)" %(dataObjectTuple[0], dataObjectTuple[1]) \
		if dataObjectTuple[1] \
		else dataObjectTuple[0]

def purgeFromDeclarationDirectives(directives, purgeList):
	declarationComponents, remainder = splitIntoComponentsAndRemainder(directives)
	purgedDeclarationDirectives = ""
	for component in declarationComponents:
		for keywordToPurge in purgeList:
			if component.lower().find(keywordToPurge) == 0:
				break
		else:
			if purgedDeclarationDirectives != "":
				purgedDeclarationDirectives += ", "
			purgedDeclarationDirectives += component
	return (purgedDeclarationDirectives + " " + remainder.strip()).strip()

def splitAndPurgeSpecification(line, purgeList=['intent']):
	declarationDirectives = ""
	symbolDeclarationStr = ""
	specTuple = parseSpecification(line)
	if not specTuple[0]:
		raise Exception("When trying to extract a device declaration: This is not a valid declaration: %s" %(line))
	declarationDirectives = specTuple[0]
	symbolDeclarationStr = ", ".join(
		rightHandSpecificationFromDataObjectTuple(dataObjectTuple)
		for dataObjectTuple in specTuple[1]
	)
	return purgeFromDeclarationDirectives(declarationDirectives, purgeList), declarationDirectives, symbolDeclarationStr

def getReorderedDomainsAccordingToDeclaration(domains, dimensionSizesInDeclaration, purgeUndeclared=False):
	def getNextUnusedIndexForDimensionSize(domainSize, dimensionSizesInDeclaration, usedIndices):
		index_candidate = None
		startAt = 0
		while True:
			if startAt > len(dimensionSizesInDeclaration) - 1:
				return None
			try:
				index_candidate = dimensionSizesInDeclaration[startAt:].index(domainSize) + startAt
			except ValueError:
				return None #example: happens when domains are declared for allocatables with :
			if index_candidate in usedIndices:
				startAt = index_candidate + 1
			else:
				break
		return index_candidate

	if not dimensionSizesInDeclaration:
		return domains
	if len(domains) == 0:
		return domains
	if len(domains) != len(dimensionSizesInDeclaration) and not purgeUndeclared:
		return domains
	# if purgeUndeclared:
	#     newDomains = []
	#     for (domainName, domainSize) in domains:
	#         if domainSize in dimensionSizesInDeclaration:
	#             newDomains.append((domainName, domainSize))
	#     domains = newDomains
	reorderedDomains = [0] * len(domains)
	usedIndices = []
	fallBackToCurrentOrder = False
	for (domainName, domainSize) in domains:
		index = getNextUnusedIndexForDimensionSize(domainSize, dimensionSizesInDeclaration, usedIndices)
		if index == None:
			fallBackToCurrentOrder = True
			break
		usedIndices.append(index)
		reorderedDomains[index] = (domainName, domainSize)
	if fallBackToCurrentOrder:
		return domains
	return reorderedDomains

def uniqueIdentifier(symbolName, suffix):
	return (symbolName + "_hfauto_" + suffix).strip()

def deviceVersionIdentifier(symbolName):
	return (symbolName + "_hfdev").strip()

MERGEABLE_DEFAULT_SYMBOL_INSTANCE_ATTRIBUTES = {
	"isDeclaredExplicitely": False,
	"hasUndecidedDomainSizes": False,
	"isMatched": False,
	"usedTypeParameters": set([]),
	"_isTypeParameter": False,
	"_declarationPrefix": None,
	"_sourceModuleIdentifier": None,
	"_sourceSymbol": None,
	"parallelRegionTemplates": None,
	"declaredDimensionSizes": None,
	"isAutoDom": False, #MMU 2015-11-6: At this point we can still not make autoDom the default. It would generate the following error in ASUCA:
#                        Error when parsing file /work1/t2g-kaken-S/mueller/asuca/hybrid/asuca-kij/./build/hf_preprocessed/physics.h90 on line 475:
#                        There are multiple known dimension sizes for domain i. Cannot insert domain for autoDom symbol densrjd. Please use explicit declaration;
#                        Debug Print: None; Print of line:
#                        real(rp):: densrjd(nz)
	"_isHostSymbol": False,
	"isCompacted": False,
	"domPPName": None,
	"accPPName": None,
	"analysis": None,
	"_declarationTypeOverride": None,
	"_templateDomains": None
}

MERGEABLE_DEFAULT_SYMBOL_INSTANCE_DOMAIN_ATTRIBUTES = {
	"domains": [],
	"_kernelDomainNames": [], #!Important: The order of this list must remain insignificant when it is used
	"_kernelInactiveDomainSizes": [], #!Important: The order of this list must remain insignificant when it is used
	"_knownKernelDomainSizesByName": {}
}

class ScopeError(Exception):
    pass

class Symbol(object):
	def __init__(self, name, template=None, patterns=None, symbolEntry=None, scopeNode=None, analysis=None, parallelRegionTemplates=[]):
		if not name or name == "":
			raise Exception("Name required for initializing symbol")

		self.loadDefaults()
		self.name = name
		if patterns != None:
			self.patterns = patterns
		else:
			self.patterns = RegExPatterns.Instance()
		self.analysis = analysis
		self.importPattern = self.patterns.get(r'^\s*use\s*(\w*)\s*,\s*only\s*.*?\W\s*' + re.escape(name) + r'(?:\W|$).*')
		self.importMapPattern = self.patterns.get(r'.*?\W' + re.escape(name) + r'\s*\=\>\s*(\w*).*')
		self.pointerOrAllocatablePattern = self.patterns.get(r'\s*(?:double\s+precision|real|integer|character|logical|complex).*?(?:pointer|allocatable).*?[\s,:]+' + re.escape(name))
		self.typeDependencyPattern = self.patterns.get(r'.*?\W' + re.escape(name) + r'\W.*')
		self.initLevel = Init.NOTHING_LOADED
		self.routineNode = None
		self.declarationSuffix = None
		self._entryNode = symbolEntry
		if template != None:
			self.loadTemplate(template)
		else:
			self.template = None
		if (symbolEntry != None or scopeNode != None) \
		and (symbolEntry == None or scopeNode == None):
			raise Exception("symbol entry (%s) and scope node (%s) need to be set together for symbol %s" %(symbolEntry, scopeNode, self))
		if symbolEntry != None:
			self.isModuleSymbol = scopeNode.tagName == "module"
			self.loadDomainDependantEntryNodeAttributes(symbolEntry)
			if self.isModuleSymbol:
				self.loadModuleNodeAttributes(scopeNode)
			else:
				self.loadRoutineNodeAttributes(scopeNode, parallelRegionTemplates)

		self.createdBy = ""
		if ConversionOptions.Instance().debugPrint:
			import inspect
			self.createdBy = inspect.getouterframes(inspect.currentframe(), 2)[1][3]
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] initialized")

	def __repr__(self):
		return self.name
	def __hash__(self):
		return hash(self.nameInScope())
	def __eq__(self, other):
		if other == None:
			return False
		return self.nameInScope() == other.nameInScope()
	def __ne__(self, other):
		if other == None:
			return True
		return self.nameInScope() != other.nameInScope()
	def __lt__(self, other):
		if other == None:
			return False
		return self.nameInScope() < other.nameInScope()
	def __le__(self, other):
		if other == None:
			return False
		return self.nameInScope() <= other.nameInScope()
	def __gt__(self, other):
		if other == None:
			return True
		return self.nameInScope() > other.nameInScope()
	def __ge__(self, other):
		if other == None:
			return False
		return self.nameInScope() >= other.nameInScope()

	@property
	def nameIsGuaranteedUniqueInScope(self):
		return self.isArgument or self.isUserSpecified or self.residingModule == self.sourceModule

	@property
	def sourceModule(self):
		if self._sourceModuleIdentifier not in ['', None, 'HF90_LOCAL_MODULE']:
			return self._sourceModuleIdentifier
		if not self.routineNode:
			return None
		sourceModule = self.routineNode.getAttribute('module')
		if sourceModule in ['', None]:
			sourceModule = self.routineNode.getAttribute('name') #looks like a module node is loaded for this symbol instead
		return sourceModule

	@sourceModule.setter
	def sourceModule(self, _sourceModuleIdentifier):
		self._sourceModuleIdentifier = _sourceModuleIdentifier

	@property
	def residingModule(self):
		if self._residingModule:
			return self._residingModule
		if not self.routineNode:
			raise Exception("cannot determine residing module for %s at this point" %(self.name))
		moduleName = self.routineNode.getAttribute('module')
		if moduleName:
			return moduleName
		moduleName = self.routineNode.getAttribute('name')
		if not moduleName:
			raise Exception("cannot determine residing module for %s at this point" %(self.name))
		return moduleName

	@residingModule.setter
	def residingModule(self, residingModule):
		self._residingModule = residingModule

	@property
	def declarationPrefix(self):
		return self._declarationPrefix

	@declarationPrefix.setter
	def declarationPrefix(self, _declarationPrefix):
		self._declarationPrefix = _declarationPrefix

	@property
	def isArgument(self):
		return self._isArgumentOverride or (self.analysis and self.analysis.symbolType in [SymbolType.ARGUMENT_WITH_DOMAIN_DEPENDANT_SPEC, SymbolType.ARGUMENT])

	@isArgument.setter
	def isArgument(self, _isArgumentOverride):
		self._isArgumentOverride = _isArgumentOverride

	@property
	def isUsingDevicePostfix(self):
		return self._isUsingDevicePostfix

	@isUsingDevicePostfix.setter
	def isUsingDevicePostfix(self, _isUsingDevicePostfix):
		self._isUsingDevicePostfix = _isUsingDevicePostfix

	@property
	def nameOfScope(self):
		if self._nameOfScopeOverride:
			return self._nameOfScopeOverride
		if self.routineNode:
			return self.routineNode.getAttribute('name')
		raise Exception("undefined name of scope for %s" %(self.name))

	@nameOfScope.setter
	def nameOfScope(self, _nameOfScopeOverride):
		self._nameOfScopeOverride = _nameOfScopeOverride

	@property
	def isTypeParameter(self):
		return self._isTypeParameter

	@isTypeParameter.setter
	def isTypeParameter(self, _isTypeParameter):
		self._isTypeParameter = _isTypeParameter
		if self._isTypeParameter:
			logging.debug("Symbol %s has been found to be a type parameter" %(self))

	@property
	def sourceSymbol(self):
		if not self._sourceSymbol:
			return None
		if self.isUsingDevicePostfix:
			return deviceVersionIdentifier(self._sourceSymbol)
		return self._sourceSymbol

	@sourceSymbol.setter
	def sourceSymbol(self, _sourceSymbol):
		self._sourceSymbol = _sourceSymbol

	@property
	def isHostSymbol(self):
		return self._isHostSymbol and not self.isPresent and not self.isToBeTransfered

	@isHostSymbol.setter
	def isHostSymbol(self, _isHostSymbol):
		self._isHostSymbol = _isHostSymbol

	@property
	def isPresent(self):
		if self._isToBeTransfered:
			return False
		if self._isPresent:
			return True
		if self.parallelRegionPosition in ["within", "outside"]:
			return True #as a general rule in HF, if we have a kernel in our subroutine, all symbols are to be already present on the device
		return False

	@isPresent.setter
	def isPresent(self, _isPresent):
		self._isPresent = _isPresent

	@property
	def isToBeTransfered(self):
		return self._isToBeTransfered

	@isToBeTransfered.setter
	def isToBeTransfered(self, _isToBeTransfered):
		self._isToBeTransfered = _isToBeTransfered

	@property
	def isArray(self):
		if self.domains and len(self.domains) > 0:
			return True
		return self.declarationType in [
			DeclarationType.LOCAL_ARRAY,
			DeclarationType.MODULE_ARRAY,
			DeclarationType.FRAMEWORK_ARRAY,
			DeclarationType.MODULE_ARRAY_PASSED_IN_AS_ARGUMENT,
			DeclarationType.OTHER_ARRAY
		]

	@property
	def numOfParallelDomains(self):
		if self.parallelRegionPosition in ["outside", None, ""]:
			return 0
		return len(self._kernelDomainNames)

	@property
	def activeDomainsMatchSpecification(self):
		if not self.domains:
			return False
		templateDomains = self._templateDomains if self._templateDomains else []
		return (self.isAutoDom and len(self.domains) in [
				len(templateDomains),
				len(templateDomains) + len(self._kernelInactiveDomainSizes),
				len(self._kernelDomainNames) + len(self._kernelInactiveDomainSizes)
			]) \
			or (not self.isAutoDom and len(self.domains) == len(templateDomains))

	@property
	def declarationType(self):
		def hasSourceModule(symbol, onlyLocal=False):
			if symbol._sourceModuleIdentifier == "HF90_LOCAL_MODULE" \
			or (
				symbol._sourceModuleIdentifier not in [None, ""] \
				and (symbol._sourceModuleIdentifier == self.routineNode.getAttribute('module') \
					or symbol._sourceModuleIdentifier == self.routineNode.getAttribute('name')\
				) \
			):
				return True
			if onlyLocal:
				return False
			if symbol._sourceModuleIdentifier not in [None, ""]:
				return True
			return False

		if self._declarationTypeOverride != None:
			return self._declarationTypeOverride
		if not self.routineNode:
			raise Exception("Cannot define declaration type for symbol %s without a routine or module node loaded" %(self))
		if len(self.domains) > 0:
			if hasSourceModule(self):
				if self.isArgument:
					return DeclarationType.MODULE_ARRAY_PASSED_IN_AS_ARGUMENT
				return DeclarationType.MODULE_ARRAY
			if self.isArgument:
				return DeclarationType.OTHER_ARGUMENT
			if self.initLevel < Init.ROUTINENODE_ATTRIBUTES_LOADED:
				return DeclarationType.UNDEFINED
			if self.intent == "local":
				return DeclarationType.LOCAL_ARRAY
			return DeclarationType.OTHER_ARRAY
		if self.isArgument:
			return DeclarationType.OTHER_ARGUMENT
		if hasSourceModule(self, onlyLocal=True):
			return DeclarationType.LOCAL_MODULE_SCALAR
		if hasSourceModule(self):
			return DeclarationType.FOREIGN_MODULE_SCALAR
		if self.intent == "local":
			return DeclarationType.LOCAL_SCALAR
		if self.initLevel < Init.ROUTINENODE_ATTRIBUTES_LOADED:
			return DeclarationType.UNDEFINED
		return DeclarationType.OTHER_SCALAR

	@declarationType.setter
	def declarationType(self, _declarationTypeOverride):
		self._declarationTypeOverride = _declarationTypeOverride

	def _getPurgedDeclarationPrefix(self, purgeList=[]):
		if self.declarationPrefix == None or self.declarationPrefix == "":
			if self.routineNode:
				routineHelperText = " for subroutine %s," %(self.nameOfScope)
			raise Exception("Symbol %s (type %i) needs to be automatically declared%s but there is no information about its type. \
Please either use an @domainDependant specification in the imported module's module scope OR \
specify the type like in a Fortran 90 declaration line using a @domainDependant {declarationPrefix([TYPE DECLARATION])} directive within the current subroutine.\n\n\
EXAMPLE:\n\
@domainDependant {declarationPrefix(real(8))}\n\
%s\n\
@end domainDependant" %(self.nameInScope(), self.declarationType, routineHelperText, self.name)
			)

		declarationPrefix = self.declarationPrefix
		if "::" not in declarationPrefix:
			declarationPrefix = declarationPrefix.rstrip() + " ::"
		if len(purgeList) != 0:
			patterns = RegExPatterns.Instance()
			declarationDirectivesWithoutIntent, _,  symbolDeclarationStr = splitAndPurgeSpecification(
				declarationPrefix + " " + str(self),
				purgeList=purgeList
			)
			declarationPrefix = declarationDirectivesWithoutIntent
		return declarationPrefix.strip()

	@property
	def uniqueIdentifier(self):
		if not self.routineNode:
			raise Exception("routine node needs to be loaded at this point")
		return uniqueIdentifier(self.name, self.nameOfScope)

	def updateNameInScope(self, forceAutomaticName=False, residingModule=None):
		#Give a symbol representation that is guaranteed to *not* collide with any local namespace (as long as programmer doesn't use any 'hfXXX' pre- or postfixes)
		def automaticName(symbol):
			if symbol.analysis and symbol.routineNode and not forceAutomaticName:
				aliasName = symbol.analysis.aliasNamesByRoutineName.get(symbol.nameOfScope)
				if aliasName not in [None, '']:
					return aliasName
			if symbol.nameIsGuaranteedUniqueInScope and not forceAutomaticName:
				return symbol.name
			referencingName = None
			if symbol.declarationType in [
				DeclarationType.LOCAL_MODULE_SCALAR,
				DeclarationType.MODULE_ARRAY,
				DeclarationType.FOREIGN_MODULE_SCALAR,
				DeclarationType.MODULE_ARRAY_PASSED_IN_AS_ARGUMENT
			] and symbol._sourceModuleIdentifier not in [None, ""]:
				referencingName = uniqueIdentifier(self.name, self.sourceModule)
			else:
				referencingName = symbol.uniqueIdentifier
			return referencingName

		self._nameInScope = None
		if residingModule:
			self.residingModule = residingModule
		if forceAutomaticName:
			self._nameInScope = automaticName(self)
		elif self.isUserSpecified:
			self._nameInScope = self.name
		else:
			self._nameInScope = automaticName(self)

	def nameInScope(self, useDeviceVersionIfAvailable=True):
		if self._nameInScope == None:
			raise ScopeError("name in scope undefined at this point for %s; scope name: %s" %(self.name, self.nameOfScope))
		if useDeviceVersionIfAvailable and self.isUsingDevicePostfix:
			return limitLength(deviceVersionIdentifier(self._nameInScope))
		return limitLength(self._nameInScope)

	def splitTextAtLeftMostOccurrence(self, text):
		return splitTextAtLeftMostOccurrence([self.name], text)

	def isDummySymbolForRoutine(self, routineName):
		if not self.analysis:
			return False
		return self.analysis.argumentIndexByRoutineName.get(routineName) != None

	def loadDefaults(self):
		def loadAttributesFromObject(obj):
			for attribute in obj:
				setattr(self, attribute, obj[attribute])

		self.intent = None
		self.isConstant = False
		self.routineNode = None
		self.attributes = None
		self.parallelRegionPosition = None
		self._isUsingDevicePostfix = False
		self.isOnDevice = False
		self.isModuleSymbol = False
		self._isArgumentOverride = False
		self._nameOfScopeOverride = None
		self._nameInScope = None
		self.isUserSpecified = False
		self.isPresent = False
		self.isToBeTransfered = False
		self._residingModule = None
		loadAttributesFromObject(MERGEABLE_DEFAULT_SYMBOL_INSTANCE_ATTRIBUTES)
		loadAttributesFromObject(MERGEABLE_DEFAULT_SYMBOL_INSTANCE_DOMAIN_ATTRIBUTES)

	def merge(self, otherSymbol):
		def getMergedSimpleAttributeValue(attributeName):
			mine = getattr(self, attributeName)
			other = getattr(otherSymbol, attributeName)
			if mine != other \
			and mine not in ["", MERGEABLE_DEFAULT_SYMBOL_INSTANCE_ATTRIBUTES[attributeName]] \
			and other not in ["", MERGEABLE_DEFAULT_SYMBOL_INSTANCE_ATTRIBUTES[attributeName]]:
				return mine
			if other not in ["", MERGEABLE_DEFAULT_SYMBOL_INSTANCE_ATTRIBUTES[attributeName]]:
				return other
			return mine

		def getMergedDomains():
			mine = self.domains
			other = otherSymbol.domains
			if len(mine) > 0 and len(other) > 0 and len(mine) != len(other):
				return mine
			if len(mine) > 0 and len(other) > 0:
				for index, entry in enumerate(mine):
					if entry != other[index]:
						break
					else:
						return mine
				merged = []
				for index, entry in enumerate(mine):
					if entry[1] != other[index][1]:
						break
					myDomName = entry[0]
					otherDomName = other[index][0]
					if myDomName == otherDomName:
						merged.append(entry)
					elif myDomName == 'HF_GENERIC_DIM':
						merged.append(other[index])
					elif otherDomName == 'HF_GENERIC_DIM':
						merged.append(entry)
					else:
						break
				else:
					return merged
				return mine
			if len(other) > 0:
				return other
			return mine

		def getMergedCollection(attributeName):
			mine = getattr(self, attributeName)
			other = getattr(otherSymbol, attributeName)
			if type(mine) != type(other):
				raise Exception("Symbol %s in (%s|%s): Type conflict with attribute %s: %s vs %s." %(
					self.name,
					self.nameOfScope,
					otherSymbol.nameOfScope,
					attributeName,
					type(mine),
					type(other)
				))
			if isinstance(mine, dict):
				if len(mine.keys()) > 0 and len(other.keys()) > 0:
					return mine
				if len(other.keys()) > 0:
					return other
				return mine
			if not isinstance(mine, list):
				raise Exception("unrecognized collection type for attribute %s" %(attributeName))
			if len(mine) > 0 and len(other) > 0:
				return mine
			if len(other) > 0:
				return other
			return mine

		def isEmpty(obj):
			if isinstance(obj, dict):
				return len(obj.keys()) == 0
			if obj == None:
				return True
			return len(obj) == 0

		def allAttributesEmpty(obj, attributeList):
			for attribute in attributeList:
				entry = getattr(obj, attribute)
				if not isEmpty(entry):
					break
			else:
				return True
			return False

		if self.name != otherSymbol.name and self.sourceSymbol != otherSymbol.name and self.name != otherSymbol.sourceSymbol:
			raise Exception("cannot merge %s with %s - doesn't seem to be be the same symbol" %(self.name, otherSymbol.name))
		for attribute in MERGEABLE_DEFAULT_SYMBOL_INSTANCE_ATTRIBUTES:
			setattr(self, attribute, getMergedSimpleAttributeValue(attribute))
		for domainAttributeName in MERGEABLE_DEFAULT_SYMBOL_INSTANCE_DOMAIN_ATTRIBUTES.keys():
			if domainAttributeName == "domains":
				self.domains = getMergedDomains()
			else:
				setattr(self, domainAttributeName, getMergedCollection(domainAttributeName))
		self.isPresent = self.isPresent or otherSymbol.isPresent
		#isToBeTransfered shall be kept from curr symbol
		if self.isAutoDom and not otherSymbol.isAutoDom and self.parallelRegionTemplates:
			self.loadDomains(getDomNameAndSize(otherSymbol.template), self.parallelRegionTemplates)
		self.initLevel = max(self.initLevel, otherSymbol.initLevel)
		self.checkIntegrityOfDomains()

	def loadTemplate(self, template):
		if self.initLevel > Init.DEPENDANT_ENTRYNODE_ATTRIBUTES_LOADED:
			raise Exception(
				"Cannot load a new template for symbol %s at init level %s" %(
					str(self),
					self.initLevel
				)
			)
		self.template = template
		self.attributes = getAttributes(self.template)
		self.setOptionsFromAttributes(self.attributes)
		self.initLevel = max(self.initLevel, Init.TEMPLATE_LOADED)

	def setOptionsFromAttributes(self, attributes):
		if "present" in attributes:
			self.isPresent = True
		if "autoDom" in attributes:
			self.isAutoDom = True
		if "host" in attributes:
			self.isHostSymbol = True
		if "transferHere" in attributes:
			if self._isPresent:
				raise Exception("Symbol %s has contradicting attributes 'transferHere' and 'present'" %(self))
			self._isToBeTransfered = True
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] attributes set")

	def storeDomainDependantEntryNodeAttributes(self, overloadEntryNode=None):
		domainDependantEntryNode = self._entryNode
		if overloadEntryNode != None:
			domainDependantEntryNode = overloadEntryNode
		if domainDependantEntryNode == None:
			raise Exception("no entry node specified for %s - cannot store attributes" %(self.name))
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] storing symbol attributes. Init Level: %s" %(str(self.initLevel)))
		if self.intent:
			domainDependantEntryNode.setAttribute("intent", self.intent)
		if self.declarationPrefix:
			domainDependantEntryNode.setAttribute("declarationPrefix", self.declarationPrefix)
		if self._sourceModuleIdentifier:
			domainDependantEntryNode.setAttribute("_sourceModuleIdentifier", self._sourceModuleIdentifier)
		if self.sourceSymbol:
			domainDependantEntryNode.setAttribute("sourceSymbol", self.sourceSymbol)
		domainDependantEntryNode.setAttribute("isDeclaredExplicitely", "yes" if self.isDeclaredExplicitely else "no")
		domainDependantEntryNode.setAttribute("isUsingDevicePostfix", "yes" if self.isUsingDevicePostfix else "no")
		domainDependantEntryNode.setAttribute("hasUndecidedDomainSizes", "yes" if self.hasUndecidedDomainSizes else "no")
		if self.domains and len(self.domains) > 0:
			domainDependantEntryNode.setAttribute(
				"declaredDimensionSizes", ",".join(
					[dimSize for _, dimSize in self.domains]
				)
			)

	def loadDomainDependantEntryNodeAttributes(self, domainDependantEntryNode, warnOnOverwrite=True):
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] +++++++++ LOADING DOMAIN DEPENDANT NODE ++++++++++ ")

		#   This symbol has an explicit domain dependant entry - make sure to store this as the name used in the scope
		self._nameInScope = self.name

		self.intent = domainDependantEntryNode.getAttribute("intent") if self.intent in [None, ''] else self.intent
		self.declarationPrefix = domainDependantEntryNode.getAttribute("declarationPrefix") if self.declarationPrefix in [None, ''] else self.declarationPrefix
		self._sourceModuleIdentifier = domainDependantEntryNode.getAttribute("_sourceModuleIdentifier") if self._sourceModuleIdentifier in [None, ''] else self._sourceModuleIdentifier
		self.sourceSymbol = domainDependantEntryNode.getAttribute("sourceSymbol") if self.sourceSymbol in [None, ''] else self.sourceSymbol
		if self.isModuleSymbol:
			self._sourceModuleIdentifier = "HF90_LOCAL_MODULE" if self._sourceModuleIdentifier in [None, ''] else self._sourceModuleIdentifier
		self.hasUndecidedDomainSizes = domainDependantEntryNode.getAttribute("hasUndecidedDomainSizes") == "yes"
		self.isUsingDevicePostfix = domainDependantEntryNode.getAttribute("isUsingDevicePostfix") == "yes"
		self.isDeclaredExplicitely = domainDependantEntryNode.getAttribute("isDeclaredExplicitely") == "yes"
		declaredDimensionSizes = domainDependantEntryNode.getAttribute("declaredDimensionSizes")
		self.declaredDimensionSizes = declaredDimensionSizes.split(",") \
			if declaredDimensionSizes \
			and self.declaredDimensionSizes == None \
			else self.declaredDimensionSizes
		if self.declaredDimensionSizes and len(self.declaredDimensionSizes) > 0 and self.initLevel < Init.ROUTINENODE_ATTRIBUTES_LOADED:
			self.domains = []
			for dimSize in self.declaredDimensionSizes:
				if dimSize.strip() != "":
					self.domains.append(('HF_GENERIC_DIM', dimSize))
					self._kernelInactiveDomainSizes.append(dimSize)
			logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] dimsizes from domain dependant node: %s " %(str(self.declaredDimensionSizes)))
		self.initLevel = max(self.initLevel, Init.DEPENDANT_ENTRYNODE_ATTRIBUTES_LOADED)
		self.checkIntegrityOfDomains()

	def checkIntegrityOfDomains(self):
		if self.declaredDimensionSizes:
			for dimensionSize in self.declaredDimensionSizes:
				if not type(dimensionSize) in [str, unicode] or dimensionSize == "":
					raise Exception("Invalid definition of dimension size in symbol %s: %s" %(self.name, dimensionSize))
		for domain in self.domains:
			if not isinstance(domain, tuple):
				raise Exception("Invalid definition of domain in symbol %s: %s" %(self.name, str(domain)))
		parallelDomainSizesDict = {}
		for domainName, domainSize in self.domains:
			if not domainName in self._kernelDomainNames:
				continue
			parallelDomainSizesDict[domainSize] = None
		if self.initLevel >= Init.ROUTINENODE_ATTRIBUTES_LOADED \
		and len(self.domains) != len(self._kernelDomainNames) + len(self._kernelInactiveDomainSizes):
			raise Exception("Wrong number of domains for symbol %s: || active: %s; || inactive: %s || actual: %s || parallel dom index: %s || region position: %s" %(
				self.name,
				self._kernelDomainNames,
				self._kernelInactiveDomainSizes,
				self.domains,
				self._knownKernelDomainSizesByName,
				self.parallelRegionPosition
			))
		if self.initLevel >= Init.ROUTINENODE_ATTRIBUTES_LOADED \
		and not self.isAutoDom \
		and self.parallelRegionPosition in ["within", "inside"] \
		and len(self.domains) != len(self._templateDomains):
			raise Exception("Wrong number of domains for manual dom symbol %s: || template: %s; || actual: %s" %(
				self.name,
				self._templateDomains,
				self.domains
			))
		if self.initLevel >= Init.ROUTINENODE_ATTRIBUTES_LOADED \
		and self.parallelRegionPosition in ["outside", None, ""] \
		and self.isAutoDom \
		and len(self.domains) != len(self._kernelInactiveDomainSizes):
			raise Exception("Wrong number of domains for autoDom symbol %s: || template: %s; || declared: %s || actual: %s || kernel: %s || non-kernel: %s" %(
				self.name,
				self._templateDomains,
				self.declaredDimensionSizes,
				self.domains,
				self._kernelDomainNames,
				self._kernelInactiveDomainSizes
			))
		if self.initLevel >= Init.DECLARATION_LOADED and self.declaredDimensionSizes == None:
			raise Exception("symbol %s is in declaration loaded state, but dimensions are not initialized" %(self.name))
		logging.debug("domain integrity checked for symbol %s" %(self))

	def loadTemplateAttributes(self, parallelRegionTemplates=[]):
		if self.initLevel < Init.TEMPLATE_LOADED:
			raise Exception(
				"Cannot load template attributes for %s at init level %s" %(
					str(self),
					self.initLevel
				)
			)
		templateDomains = getDomNameAndSize(self.template)
		declarationPrefixFromTemplate = getDeclarationPrefix(self.template)
		self.loadDeclarationPrefixFromString(declarationPrefixFromTemplate)
		self.loadDomains(templateDomains, parallelRegionTemplates)
		self.adjustDomainsToKernelPosition()
		logging.debug(
			"[" + str(self) + ".init " + str(self.initLevel) + "] Domains loaded from callgraph information for symbol %s. Parallel active: %s. Parallel Inactive: %s. Declaration Prefix: %s. templateDomains: %s declarationPrefix: %s. Parallel Regions: %i\n" %(
				str(self),
				str(self._kernelDomainNames),
				str(self._kernelInactiveDomainSizes),
				declarationPrefixFromTemplate,
				templateDomains,
				declarationPrefixFromTemplate,
				len(parallelRegionTemplates)
			)
		)

	def loadDeclarationPrefixFromString(self, declarationPrefix):
		if declarationPrefix != None and declarationPrefix.strip() != "":
			self.declarationPrefix = declarationPrefix
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] declaration prefix loaded: %s" %(declarationPrefix))

	def loadDomains(self, templateDomains, parallelRegionTemplates=[]):
		if templateDomains == None or len(templateDomains) == 0:
			dependantDomSizeByName = dict(
				("%s_%i" %(value[0],index),value[1])
				for index,value
				in enumerate(self.domains)
			) #in case we have generic domain names, need to include the index here so the order doesn't get messed up.
		else:
			dependantDomSizeByName = dict(
				(dependantDomName,dependantDomSize)
				for (dependantDomName, dependantDomSize)
				in templateDomains
			)

		self._kernelDomainNames = []
		self._kernelInactiveDomainSizes = []
		self._knownKernelDomainSizesByName = {}
		self._templateDomains = templateDomains

		#   adjust the loaded domains by the new information given:
		if not self.domains or len(self.domains) <= len(templateDomains):
			self.domains = templateDomains

		#   which of those dimensions are kernel dimensions?
		#   -> build up index of domain sizes and and names and put them in the 'kernel domain names' set
		parallelRegionDomNamesBySize = {}
		for parallelRegionTemplate in parallelRegionTemplates:
			regionDomNameAndSize = getDomNameAndSize(parallelRegionTemplate)
			logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] analyzing domains for parallel region: %s; dependant domsize by name: %s" %(
				str(regionDomNameAndSize),
				str(dependantDomSizeByName)
			))
			for index, (regionDomName, regionDomSize) in enumerate(regionDomNameAndSize):
				#The same domain name can sometimes have different domain sizes used in different parallel regions, so we build up a list of these sizes.
				if not regionDomName in self._knownKernelDomainSizesByName:
					self._knownKernelDomainSizesByName[regionDomName] = [regionDomSize]
				elif regionDomSize not in self._knownKernelDomainSizesByName[regionDomName]:
					self._knownKernelDomainSizesByName[regionDomName].append(regionDomSize)
				parallelRegionDomNamesBySize[regionDomSize] = regionDomName
		orderedDomains = self._templateDomains if self._templateDomains else self.domains
		for domName, domSize in orderedDomains:
			if domName in self._knownKernelDomainSizesByName:
				self._kernelDomainNames.append(domName)
			elif "HF_" in domName and domSize in parallelRegionDomNamesBySize:
				self._kernelDomainNames.append(parallelRegionDomNamesBySize[domSize])

		#   add the template information to the parallel region index; this is important in case the domainDependant template information differs from the parallel region
		for dependantDomName, dependantDomSize in orderedDomains:
			if not dependantDomName in self._kernelDomainNames:
				continue
			parallelRegionDomNamesBySize[dependantDomSize] = dependantDomName

		#   match the domain sizes to those in the index. this is important so we don't cancel them out later in the region position adjustment code
		dimsBeforeReset = copy.deepcopy(self.domains)
		self.domains = []
		for (dependantDomName, dependantDomSize) in dimsBeforeReset:
			domNameAlias = parallelRegionDomNamesBySize.get(dependantDomSize, dependantDomName)
			self.domains.append((domNameAlias, dependantDomSize))

		#   put the non parallel domains in the '_kernelInactiveDomainSizes' set.
		for (dependantDomName, dependantDomSize) in self.domains:
			#build up parallel inactive dimensions again
			if not dependantDomName in self._kernelDomainNames \
			and not dependantDomSize in parallelRegionDomNamesBySize: #$$$ can this second clause be removed?
				self._kernelInactiveDomainSizes.append(dependantDomSize)
			#use the declared domain size (potentially overriding automatic sizes)
			domNameAlias = parallelRegionDomNamesBySize.get(dependantDomSize, "")
			if domNameAlias in self._knownKernelDomainSizesByName \
			and dependantDomSize not in self._knownKernelDomainSizesByName[domNameAlias]:
				self._knownKernelDomainSizesByName[domNameAlias].append(dependantDomSize)

	def loadModuleNodeAttributes(self, moduleNode):
		if self.initLevel < Init.DEPENDANT_ENTRYNODE_ATTRIBUTES_LOADED:
			raise Exception("Symbol %s's routine node attributes are loaded without loading the entry node attributes first."
				%(str(self))
			)
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] +++++++++ LOADING MODULE NODE ++++++++++ ")
		self.routineNode = moduleNode #MMU 2015-11-18: $$$ This needs to be commented or rethought
		self.loadTemplateAttributes()
		self.updateNameInScope()
		self.initLevel = max(self.initLevel, Init.ROUTINENODE_ATTRIBUTES_LOADED)
		self.checkIntegrityOfDomains()
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] symbol attributes loaded from module node. Domains at this point: %s. Init Level: %s" %(str(self.domains), str(self.initLevel)))

	def loadRoutineNodeAttributes(self, routineNode, parallelRegionTemplates):
		if self.initLevel < Init.DEPENDANT_ENTRYNODE_ATTRIBUTES_LOADED:
			raise Exception("Symbol %s's routine node attributes are loaded without loading the entry node attributes first."
				%(str(self))
			)
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] +++++++++ LOADING ROUTINE NODE ++++++++++ ")
		self.routineNode = routineNode
		#get and check parallelRegionPosition
		routineName = self.nameOfScope
		if not routineName:
			raise Exception("Routine node without name: %s" %(routineNode.toxml()))
		parallelRegionPosition = routineNode.getAttribute("parallelRegionPosition")
		parallelRegionTemplatesUsedForLoading = []
		if parallelRegionPosition and parallelRegionPosition != "":
			self.parallelRegionPosition = parallelRegionPosition
			self.parallelRegionTemplates = parallelRegionTemplates
			if parallelRegionPosition not in ["inside", "outside", "within"]:
				raise Exception("Invalid parallel region position definition ('%s') for routine %s" %(parallelRegionPosition, routineName))
			parallelRegionTemplatesUsedForLoading = parallelRegionTemplates
		self.loadTemplateAttributes(parallelRegionTemplatesUsedForLoading)
		self.updateNameInScope()
		self.initLevel = max(self.initLevel, Init.ROUTINENODE_ATTRIBUTES_LOADED)
		self.checkIntegrityOfDomains()
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] routine node attributes loaded for symbol %s. Domains at this point: %s" %(self.name, str(self.domains)))

	def adjustDomainsToKernelPosition(self):
		if self.parallelRegionPosition in [None, ""] and self.declaredDimensionSizes != None:
			self.domains = [
				("HF_GENERIC_PARALLEL_INACTIVE_DIM", domSize) for domSize in self.declaredDimensionSizes
			]
		elif self.parallelRegionPosition in [None, "", "outside"]:
			self.domains = [
				(domName, domSize) for (domName, domSize) in self.domains
				if not domName in self._kernelDomainNames
			]
		if self.parallelRegionPosition in [None, "", "outside"]:
			self._kernelDomainNames = []
			self._kernelInactiveDomainSizes = [s for (_, s) in self.domains]
		self.domains = [
			(domName, domSize) for (domName, domSize) in self.domains
			if domName in self._kernelDomainNames \
			or domSize in self._kernelInactiveDomainSizes \
			or domSize == ":"
		]

	def loadDeclaration(self, specTuple, currentRoutineArguments, currParentName):
		if self.initLevel < Init.TEMPLATE_LOADED:
			raise Exception(
				"Cannot load declaration for %s at init level %s" %(
					str(self),
					self.initLevel
				)
			)

		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] +++++++++ LOADING DECLARATION ++++++++++ ")

		#   The name used in the declaration pattern is just self.name - so store this as the scoped name for now
		self._nameInScope = self.name

		#   Same with the scope itself - since the declaration line is within a certain scope, this becomes a known known (thanks Mr. Rumsfield...)
		self.nameOfScope = currParentName
		self.isDeclaredExplicitely = True

		declarationLine = "%s :: %s %s" %(
			specTuple[0],
			", ".join([
				rightHandSpecificationFromDataObjectTuple(doTuple)
				for doTuple in specTuple[1]
			]),
			specTuple[2]
		)
		declarationDirectives = specTuple[0]
		self.declarationPrefix = purgeFromDeclarationDirectives(declarationDirectives.rstrip() + " " + "::", ["dimension"])

		#   get and check intent                                      #
		intentMatch = RegExPatterns.Instance().intentPattern.match(specTuple[0])
		newIntent = None
		if intentMatch and intentMatch.group(1).strip() != "":
			newIntent = intentMatch.group(1)
		elif self.name in currentRoutineArguments:
			newIntent = "unspecified" #dummy symbol without specified intent (basically F77 style)
		else:
			newIntent = "local"
		if newIntent not in ["", None, "unspecified"]:
			self.intent = newIntent

		#   check whether the symbol has undecided domains
		dimensionStr = dimensionStringFromSpecification(self.name, specTuple)
		self.hasUndecidedDomainSizes = self.pointerOrAllocatablePattern.match(declarationLine) != None and ":" in dimensionStr

		#   look at declaration of symbol and get its                 #
		#   dimensions.                                               #
		remainder = specTuple[2]
		self.declarationSuffix = remainder.strip()
		dimensionSizes = [sizeStr.strip() for sizeStr in dimensionStr.split(',') if sizeStr.strip() != ""] if dimensionStr != None else []
		self.declaredDimensionSizes = dimensionSizes

		knownDimensionSizes = [d for (_, d) in self.domains]
		if self.isAutoDom and self.hasUndecidedDomainSizes:
			if len(self.domains) == 0:
				for dimensionSize in dimensionSizes:
					if dimensionSize in knownDimensionSizes:
						continue
					self.domains.append(("HF_GENERIC_UNKNOWN_DIM", dimensionSize))
					self._kernelInactiveDomainSizes.append(dimensionSize)
			elif len(dimensionSizes) != len(self.domains):
				raise Exception("Symbol %s's declared shape does not match its domainDependant directive. \
Automatic reshaping is not supported since this is a pointer type. Domains in Directive: %s || dimensions in declaration: %s \
|| kernel domains: %s || kernel inactive domain sizes: %s" %(
					self.name,
					self.domains,
					dimensionSizes,
					self._kernelDomainNames,
					self._kernelInactiveDomainSizes
				))
		elif self.isAutoDom:
			# for the stencil use case: user will still specify the dimensions in the declaration
			# -> autodom picks them up and integrates them as parallel active dims
			logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] Loading dimensions for autoDom, non-pointer symbol %s. Declared dimensions: %s, Known dimension sizes used for parallel regions: %s, Parallel Active Dims: %s, Parallel Inactive Dims: %s" %(
				str(self), str(dimensionSizes), str(self._knownKernelDomainSizesByName), str(self._kernelDomainNames), str(self._kernelInactiveDomainSizes)
			))
			for dimensionSize in dimensionSizes:
				if dimensionSize in knownDimensionSizes:
					continue
				self.domains.append(("HF_GENERIC_PARALLEL_INACTIVE_DIM", dimensionSize))
				self._kernelInactiveDomainSizes.append(dimensionSize)

		if not self.hasUndecidedDomainSizes:
			self.adjustDomainsToKernelPosition()

		#    Sanity checks                                            #
		if len(self.domains) < len(dimensionSizes):
			raise Exception("Something is wrong with autoDom Symbol %s's declaration: Cannot match its dimension sizes to the parallel regions it is being used in. \
Please make sure to use the same string names for its dimensions both in the parallel region as well as in its declarations -or- declare its dimensions explicitely (without autoDom).\
Declared domain: %s, Domain after init: %s, Parallel dims: %s, Independant dims: %s, \
Parallel region position: %s, Current template: %s"
				%(self.name, str(dimensionSizes), str(self.domains), str(self._kernelDomainNames), str(self._kernelInactiveDomainSizes), self.parallelRegionPosition, self.template.toxml())
			)
		if not self.hasUndecidedDomainSizes:
			self.domains = getReorderedDomainsAccordingToDeclaration(self.domains, dimensionSizes)
		self.initLevel = max(self.initLevel, Init.DECLARATION_LOADED)
		self.checkIntegrityOfDomains()
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] declaration loaded for symbol %s. Domains at this point: %s" %(self.name, str(self.domains)))

	def getModuleNameAndSourceSymbolNameFromImportMatch(self, importMatch):
		sourceModuleName = importMatch.group(1)
		if sourceModuleName == "":
			raise Exception("Invalid module in use statement for symbol %s" %(symbol.name))
		mapMatch = self.importMapPattern.match(importMatch.group(0))
		sourceSymbolName = ""
		if mapMatch:
			sourceSymbolName = mapMatch.group(1)
			if sourceSymbolName == "":
				raise Exception("Invalid source symbol in use statement for symbol %s" %(symbol.name))
		if sourceSymbolName == "":
			sourceSymbolName = self.name
		return sourceModuleName, sourceSymbolName

	def loadImportInformation(self, cgDoc, moduleNode, sourceSymbolName=None):
		if self.initLevel < Init.TEMPLATE_LOADED:
			raise Exception(
				"Cannot load import information for %s at init level %s" %(
					str(self),
					self.initLevel
				)
			)
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] +++++++++ LOADING IMPORT INFORMATION ++++++++++ ")
		self._sourceModuleIdentifier = moduleNode.getAttribute('name')

		#   From this point on we need this list set in order for intermittent consistency checks to pass
		self.declaredDimensionSizes = []

		#   The name used in the import pattern is just self.name - so store this as the scoped name for now
		self._nameInScope = self.name
		if sourceSymbolName != None:
			self.sourceSymbol = sourceSymbolName
		if self.sourceSymbol in [None, ""]:
			raise Exception("no source symbol name defined for %s" %(self))
		if not moduleNode:
			return

		templatesAndEntries = getDomainDependantTemplatesAndEntries(cgDoc, moduleNode)
		informationLoadedFromModule = False
		routineTemplate = self.template
		moduleTemplate = None
		for template, entry in templatesAndEntries:
			dependantName = entry.firstChild.nodeValue
			if dependantName != self.sourceSymbol:
				continue
			self.loadDomainDependantEntryNodeAttributes(entry, warnOnOverwrite=False)
			moduleTemplate = template
			break
		else:
			return
			#MMU 2015-9-14: This check fails with older CUDA Fortran based implementations where module data wasn't yet supported
			# raise Exception("Symbol %s not found in module information available to Hybrid Fortran. Please use an appropriate @domainDependant specification." %(self.name))
		informationLoadedFromModule = True
		logging.debug(
				"[" + str(self) + ".init " + str(self.initLevel) + "] Loading symbol information for %s imported from %s\n\
Current Domains: %s\n" %(
					self.name, self._sourceModuleIdentifier, str(self.domains)
				)
			)
		attributes, domains, declarationPrefix, accPP, domPP = getAttributesDomainsDeclarationPrefixAndMacroNames(moduleTemplate, routineTemplate)
		self.setOptionsFromAttributes(attributes)
		self.loadDeclarationPrefixFromString(declarationPrefix)
		self.loadDomains(domains, self.parallelRegionTemplates if self.parallelRegionTemplates != None else [])
		self.declaredDimensionSizes = [s for (_, s) in self.domains] #since we don't get this array from the declaration we need to set it here for non-templated module data
		self.domains = getReorderedDomainsAccordingToDeclaration(self.domains, self.declaredDimensionSizes)
		self.accPPName = accPP
		self.domPPName = domPP
		self.initLevel = max(self.initLevel, Init.DECLARATION_LOADED)
		self.checkIntegrityOfDomains()
		logging.debug(
				"[" + str(self) + ".init " + str(self.initLevel) + "] Symbol %s's initialization completed using module information.\nDomains found in module: %s; parallel active: %s; parallel inactive: %s\n" %(
					str(self),
					str(domains),
					str(self._kernelDomainNames),
					str(self._kernelInactiveDomainSizes)
				)
			)

	def getSanitizedDeclarationPrefix(self, purgeList=None):
		def nameInScopeImplementationFunction(work, remainder, symbol, iterators, parallelRegionTemplate, callee, useDeviceVersionIfAvailable):
			return symbol.nameInScope(), remainder

		if self.declarationPrefix in [None, ""]:
			raise ScopeError("Cannot generate declaration prefix for %s (from %s)" %(self, self.nameOfScope))
		if purgeList == None:
			purgeList = ['intent', 'public', 'parameter', 'save']
		result = self._getPurgedDeclarationPrefix(purgeList)
		kindMatch = self.patterns.declarationKindPattern.match(result)
		if kindMatch:
			result = kindMatch.group(1) + kindMatch.group(2) + kindMatch.group(3)

		return implement(
			result,
			[typeParameter for typeParameter in self.usedTypeParameters if typeParameter.name in result],
			symbolImplementationFunction=nameInScopeImplementationFunction
		)

	def getDeclarationLine(self, parentRoutine, purgeList=None, patterns=RegExPatterns.Instance(), name_prefix="", useDomainReordering=True, skip_on_missing_declaration=False):
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] Decl.Line.Gen: Purge List: %s, Name Prefix: %s, Domain Reordering: %s, Skip on Missing: %s." %(
			str(purgeList),
			name_prefix,
			str(useDomainReordering),
			str(skip_on_missing_declaration)
		))
		if skip_on_missing_declaration and (self.declarationPrefix == None or self.declarationPrefix == ""):
			return ""
		declarationPrefix = self.getSanitizedDeclarationPrefix(purgeList)
		result = "%s %s %s %s" %(
			declarationPrefix.strip(),
			name_prefix,
			self.domainRepresentation(parentRoutine, useDomainReordering),
			self.declarationSuffix if self.declarationSuffix else ""
		)
		return result

	def selectAllRepresentation(self):
		if self.initLevel < Init.ROUTINENODE_ATTRIBUTES_LOADED:
			raise Exception("Symbol %s's selection representation is accessed without loading the routine node attributes first" %(str(self)))

		result = self.nameInScope()
		if len(self.domains) == 0:
			return result
		result = result + "("
		for i in range(len(self.domains)):
			if i != 0:
				result = result + ","
			result = result + ":"
		result = result + ")"
		return result

	def allocationRepresentation(self):
		if self.initLevel < Init.ROUTINENODE_ATTRIBUTES_LOADED:
			raise Exception("Symbol %s's allocation representation is accessed without loading the routine node attributes first" %(str(self)))

		result = self.nameInScope()
		if len(self.domains) == 0:
			return result
		needsAdditionalClosingBracket = False
		result += "("
		domPP, isExplicit = self.domPP()
		if self.useOrderingMacro(
			[domSize for _, domSize in self.domains],
			True,
			domPP,
			isExplicit
		):
			#$$$ we need to include the template here to make pointers compatible with templating
			needsAdditionalClosingBracket = True
			result += domPP + "("
		for index, domain in enumerate(self.domains):
			if index != 0:
				result = result + ","
			dimSize = domain[1]
			if dimSize == ":":
				raise Exception("Cannot generate allocation call for symbol %s on the device - one or more dimension sizes (%s) are unknown at this point. \
Please specify the domains and their sizes with domName and domSize attributes in the corresponding @domainDependant directive." %(self.name, self.domains))
			result += dimSize
		if needsAdditionalClosingBracket:
			result += ")"
		result += ")"
		return result

	def domainRepresentation(self, parentRoutine, useDomainReordering=True):
		name = self.nameInScope(
			useDeviceVersionIfAvailable=len(self.domains) > 0
		)
		result = name
		if len(self.domains) == 0:
			return result
		needsAdditionalClosingBracket = False
		domPP, isExplicit = self.domPP()
		if self.useOrderingMacro(
			[domSize for _, domSize in self.domains],
			useDomainReordering,
			domPP,
			isExplicit
		):
			result = result + "(" + domPP + "("
			needsAdditionalClosingBracket = True
		else:
			result = result + "("
		for i in range(len(self.domains)):
			if i != 0:
				result += ","
			if (not parentRoutine or (not self.isToBeTransfered and not parentRoutine.isCallingKernel)) and self.hasUndecidedDomainSizes \
			or "pointer" in self.declarationPrefix:
				result += ":"
			else:
				(domName, domSize) = self.domains[i]
				result += domSize.strip()
		if needsAdditionalClosingBracket:
			result = result + "))"
		else:
			result = result + ")"
		return result

	def totalArrayLength(self):
		result = ""
		for i in range(len(self.domains)):
			if i != 0:
				result += " * "
			(domName, domSize) = self.domains[i]
			sizeParts = domSize.split(':')
			if len(sizeParts) == 1:
				result += sizeParts[0]
			elif len(sizeParts) == 2:
				result += "(%s - %s + 1)" %(sizeParts[1], sizeParts[0])
			else:
				raise Exception("invalid domain size for symbol %s: %s" %(self.name, domSize))

		return result

	def useOrderingMacro(self, iterators, useDomainReordering, accPP, accPPIsExplicit):
		return useDomainReordering and accPP != "" \
			and ( \
				self.numOfParallelDomains > 0 \
				or ( accPPIsExplicit and len(iterators) >= 3 ) \
			) \
			and self.activeDomainsMatchSpecification

	def accessRepresentation(
		self,
		parallelIterators,
		accessors,
		parallelRegionNode,
		useDomainReordering=True,
		isPointerAssignment=False,
		isInsideParallelRegion=False,
		callee=None,
		useDeviceVersionIfAvailable=True
	):
		def getIterators(domains, parallelIterators, offsets):
			iterators = []
			nextOffsetIndex = 0
			if len(parallelIterators) == 0 and len(offsets) == 0:
				return iterators
			for i in range(len(domains)):
				if len(parallelIterators) == 0 and len(offsets) == len(domains):
					iterators.append(str(offsets[i]))
					continue
				elif len(parallelIterators) == 0 \
				and len(offsets) == len(domains) - self.numOfParallelDomains \
				and i < self.numOfParallelDomains:
					iterators.append(":")
					continue
				elif len(parallelIterators) == 0 \
				and len(offsets) == len(domains) - self.numOfParallelDomains \
				and i >= self.numOfParallelDomains:
					iterators.append(str(offsets[i - self.numOfParallelDomains]))
					continue

				#if we reach this there are parallel iterators specified.
				if len(offsets) == len(domains):
					iterators.append(str(offsets[nextOffsetIndex]))
					nextOffsetIndex += 1
				elif domains[i][0] in parallelIterators:
					iterators.append(str(domains[i][0]))
				elif nextOffsetIndex < len(offsets):
					iterators.append(str(offsets[nextOffsetIndex]))
					nextOffsetIndex += 1
				elif len(offsets) + len(parallelIterators) == len(domains) and i < len(parallelIterators):
					iterators.append(str(parallelIterators[i]))
				elif len(offsets) + len(parallelIterators) == len(domains):
					iterators.append(str(offsets[i - len(parallelIterators)]))
				else:
					raise Exception("Cannot generate access representation for symbol %s: Unknown parallel iterators specified (%s) or not enough offsets (%s)."
						%(str(self), str(parallelIterators), str(offsets))
					)
			if (callee or isPointerAssignment) and all([iterator == ':' for iterator in iterators]):
				return [] #working around a problem in PGI 15.1: Inliner bails out in certain situations (module test kernel 3+4) if arrays are passed in like a(:,:,:).
			return [iterator.strip().replace(" ", "") for iterator in iterators]

		if isPointerAssignment \
		or len(self.domains) == 0 \
		or ( \
			not isInsideParallelRegion \
			and not callee \
			and not isPointerAssignment \
			and not self.isModuleSymbol \
			and not self.isHostSymbol \
			and len(accessors) == 0 \
		):
			return self.nameInScope()

		iterators = copy.copy(parallelIterators)
		numOfIndependentDomains = 0
		if len(self.domains) > 0: #0 domains could be an external function call which we cannot touch
			numOfIndependentDomains = len(self.domains) - self.numOfParallelDomains
			if len(accessors) != numOfIndependentDomains and len(accessors) != len(self.domains) and len(accessors) != 0:
				raise UsageError("Unexpected array access for symbol %s (%s): Please use either %i (number of parallel independant dimensions) \
	or %i (dimensions of loaded domain for this array) or zero accessors. Symbol Domains: %s; Symbol Init Level: %i; Parallel Region Position: %s; Parallel Active: %s; Symbol template:\n%s\n" %(
					self.name,
					str(accessors),
					numOfIndependentDomains,
					len(self.domains),
					str(self.domains),
					self.initLevel,
					str(self.parallelRegionPosition),
					self._kernelDomainNames,
					self.template.toxml()
				))
			if callee and hasattr(callee, "node") and callee.node.getAttribute("parallelRegionPosition") != "outside":
				iterators = [] #reset the parallel iterators if this symbol is accessed in a subroutine call and it's NOT being passed in inside a kernel

		offsets = []
		if len(accessors) == 0 and (callee or isPointerAssignment):
			for i in range(len(self.domains) - self.numOfParallelDomains):
				offsets.append(":")
		else:
			offsets += accessors

		symbolNameUsedInAccessor = None
		if (not self.isUsingDevicePostfix and len(offsets) == len(self.domains) and not all([offset == ':' for offset in offsets])) \
		or (self.intent == "in" and len(offsets) == len(self.domains) and not any([offset == ':' for offset in offsets])) \
		or (callee and not hasattr(callee, "implementation")):
			symbolNameUsedInAccessor = self.nameInScope(useDeviceVersionIfAvailable=False) #not on device or scalar accesses to symbol that can't change
		else:
			symbolNameUsedInAccessor = self.nameInScope(useDeviceVersionIfAvailable=useDeviceVersionIfAvailable)

		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] producing access representation for symbol %s; parallel iterators: %s, offsets: %s" %(self.name, str(iterators), str(offsets)))

		if len(iterators) == 0 \
		and len(offsets) != 0 \
		and len(offsets) != len(self.domains) - self.numOfParallelDomains \
		and len(offsets) != len(self.domains):
			raise Exception("Unexpected number of offsets specified for symbol %s; Offsets: %s, Expected domains: %s" \
				%(self.name, offsets, self.domains))
		if len(iterators) != 0 \
		and len(offsets) + len(iterators) != len(self.domains) \
		and len(offsets) != len(self.domains):
			raise Exception("Unexpected number of offsets and iterators specified for symbol %s; Offsets: %s, Iterators: %s, Expected domains: %s" \
				%(self.name, offsets, iterators, self.domains))

		result = symbolNameUsedInAccessor

		if len(self.domains) == 0:
			logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] Symbol has 0 domains - only returning name.")
			return result
		iterators = getIterators(self.domains, iterators, offsets)
		if len(iterators) == 0:
			logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] No iterators have been determined - only returning name.")
			return result

		needsAdditionalClosingBracket = False
		result += "( " #we add a space here so there is a higher change that the line can be broken up. iterators with preprocessor macros can take a lot of space.
		accPP, accPPIsExplicit = self.accPP()
		logging.debug("[" + self.name + ".init " + str(self.initLevel) + "] accPP Macro: %s, Explicit Macro: %s, Active Domains matching domain dependant template: %s, Number of Parallel Domains: %i\
Currently loaded template: %s\n" %(
				accPP, str(accPPIsExplicit), self.activeDomainsMatchSpecification, self.numOfParallelDomains, self.template.toxml() if self.template != None else "None"
			))
		if self.useOrderingMacro(iterators, useDomainReordering, accPP, accPPIsExplicit):
			needsAdditionalClosingBracket = True
			if not accPPIsExplicit and parallelRegionNode:
				template = getTemplate(parallelRegionNode)
				if template != '':
					accPP += "_" + template
			result += accPP + "("
		result += ",".join(iterators)

		if needsAdditionalClosingBracket:
			result = result + ")"
		result = result + " )" #same reason for the spacing as for the opening bracket.
		return result

	def getTemplateEntryNodeValues(self, parentName):
		if not self.template:
			return None
		parentNodes = self.template.getElementsByTagName(parentName)
		if not parentNodes or len(parentNodes) == 0:
			return None
		return [entry.firstChild.nodeValue for entry in parentNodes[0].childNodes]

	def getSpecificationTuple(self, line):
		specTuple = parseSpecification(line)
		if not specTuple[0]:
			return specTuple
		symbolNames = symbolNamesFromSpecificationTuple(specTuple)
		if self.name in symbolNames:
			return specTuple
		return None, None, None

	def domPP(self):
		domPPEntries = self.getTemplateEntryNodeValues("domPP")
		if domPPEntries and len(domPPEntries) > 0:
			return domPPEntries[0], True

		if self.domPPName not in ['', None]:
			return self.domPPName, True

		if self.isAutoDom:
			numOfDimensions = len(self.domains)
			domPPName = ""
			if numOfDimensions < 3:
				domPPName = ""
			elif numOfDimensions == 3:
				domPPName = "DOM"
			else:
				domPPName = "DOM%i" %(numOfDimensions)
			return domPPName, False
		else:
			return "", False


	def accPP(self):
		accPPEntries = self.getTemplateEntryNodeValues("accPP")
		if accPPEntries and len(accPPEntries) > 0:
			return accPPEntries[0], True

		if self.accPPName not in ['', None]:
			return self.accPPName, True

		if self.isAutoDom:
			numOfDimensions = len(self.domains)
			accPPName = ""
			if numOfDimensions < 3:
				accPPName = ""
			elif numOfDimensions == 3:
				accPPName = "AT"
			else:
				accPPName = "AT%i" %(numOfDimensions)
			return accPPName, False
		else:
			return "", False

class ImplicitForeignModuleSymbol(Symbol):
	def __init__(self, _sourceModuleIdentifier, nameInScope, sourceSymbol, template=None):
		Symbol.__init__(self, nameInScope, template)
		self._nameInScope = nameInScope
		self._sourceModuleIdentifier = _sourceModuleIdentifier
		self.sourceSymbol = sourceSymbol

class FrameworkArray(Symbol):
	def __init__(self, calleeName, declarationPrefix, domains, isOnDevice):
		if not calleeName or calleeName == "":
			raise Exception("Name required for initializing framework array")
		if not declarationPrefix or declarationPrefix == "":
			raise Exception("Declaration prefix required for initializing framework array")
		if len(domains) != 1:
			raise Exception("Currently unsupported non-1D-array specified as framework array")
		identifier = frameworkArrayName(calleeName)
		Symbol.__init__(self, identifier)
		self.domains = domains
		self.isMatched = True
		self.isOnDevice = isOnDevice
		self.isConstant = True
		self.declarationPrefix = declarationPrefix
		self._declarationTypeOverride = DeclarationType.FRAMEWORK_ARRAY
		self._nameInScope = identifier
		self.compactedSymbols = None