# coding: utf-8
from copy import deepcopy
import logging
from constants import retainLocalChangesColumns

class DataHandler(object):
	def __init__(self, srcData, srcHdr, dstHdr, handler):
		self._srcData = deepcopy(srcData)
		for row in [record for record in self._srcData if len(str(record[0])) == 0 ]:
			self._srcData.remove(row)

		#Set up logger
		self._logger = logging.getLogger(__name__)
		self._logger.setLevel(logging.DEBUG)
		#self._logger.addHandler(handler)

		self._srcHdr = deepcopy(srcHdr) #_requiredColumnsSorted
		self._hdr = deepcopy(srcHdr) #new list than reference
		self._dstHdr = deepcopy(dstHdr) #_requiredFBPColumnsSorted
		self._data = []

		self._mergeHeader()

	def getHeader(self):
		return self._hdr

	def getData(self):
		return self._data

	def _mergeHeader(self):
		localHeaders = [hdr for hdr in self._srcHdr] #new list object
		extraHeaders = [hdr for hdr in self._dstHdr if hdr not in localHeaders]
		print "extra headers:",extraHeaders
		for hdr in extraHeaders:
			pre = [self._dstHdr[preId] for preId in range(self._dstHdr.index(hdr), 0, -1) \
					if self._dstHdr[preId] in localHeaders]
			insertAfterId = (len(pre) != 0) and localHeaders.index(pre[0]) + 1 or 0
			localHeaders.insert(insertAfterId, hdr)
			self._logger.info('Saving new header %s in posId:%d', hdr, insertAfterId)
		self._hdr = localHeaders
		if 'Hint' not in self._hdr: self._hdr.append('Hint')
		self._setIndexes()

	def _setIndexes(self):
		#Indexes
		self._fidIndex = self._hdr.index('Feature or Subfeature')
		self._fidIndexSrc = self._srcHdr.index('Feature or Subfeature')
		self._priorityIndex = self._hdr.index('Common RL Product Backlog Priority')
		self._priorityIndexSrc = self._srcHdr.index('Common RL Product Backlog Priority')
		self._hintIndex = self._hdr.index('Hint')
		self._srcFidIndexMap = {self._srcData[rowId][self._fidIndexSrc]: rowId for rowId in range(0, len(self._srcData))}
		#print self._srcFidIndexMap.keys()

	def collectAndMergeData(self, filteredRowIds, getCellValue, isFidInUpstream):
		'''collect data from FBP and merge with local data'''
		self._isFidValidInUpstream = isFidInUpstream

		numOfLocals = len(self._srcData)
		data = []
		rowId = 0
		data.append([unicode(hdr) for hdr in self._hdr]) #Header
		
		for fbpRowId in filteredRowIds:
			colValue = lambda x: x not in self._dstHdr and u'default' or getCellValue(fbpRowId, hdr)
			rowData = [colValue(hdr) for hdr in self._hdr ]
			data.append(rowData)
			rowId = rowId + 1

		if len(self._srcData) > 0:
			self._mergeData(data)
		else:
			self._data = data
			self._logger.info("Local records %d, filtered %d records(upstream), %d records left", numOfLocals, rowId, len(self._data))

	def _mergeData(self, combinedData):
		'''Merge local loaded data with combinedData (3-way merge), and fill in missing column as possible'''
		self._isNewCol = lambda colId: self._srcHdr.count(self._hdr[colId]) == 0
		self._shouldRetainCol = lambda colId: retainLocalChangesColumns.count(self._hdr[colId]) > 0
		self._getLocalColId = lambda colId: self._srcHdr.index(self._hdr[colId])
		self._data = [combinedData[0]] #Save static header

		mergeCandidates = [rowRecord for rowRecord in combinedData[1:] if self._srcFidIndexMap.has_key(rowRecord[self._fidIndex])]
		importList = [rowRecord for rowRecord in combinedData[1:] if rowRecord not in mergeCandidates]
		self._logger.info('We have %d records for merge, %d records for import', len(mergeCandidates), len(importList))

		eraseList = []
		for rowRecord in mergeCandidates:
			fid = rowRecord[self._fidIndex]
			localRowId = self._srcFidIndexMap[fid]
			localRecord = self._srcData[localRowId]
			assert(localRecord[self._fidIndexSrc] == fid)
			#self._logger.debug('comparing local:%s<%d> with fbp:%s', localRecord[self._fidIndex], localRowId, fid)
			self._mergeRecord(rowRecord, localRecord)
			#Remove local record accordingly
			#self._logger.debug('Merged record with fid=%s'%fid)
			eraseList.append(localRecord)
			self._data.append(rowRecord)
		
		#Update status for imported ones	
		for rowRecord in importList:
			#self._logger.debug('Updating new record with fid=%s'%rowRecord[self._fidIndex])
			rowRecord[self._hintIndex] = u'imported'
			for col in range(0, len(rowRecord)):
				if rowRecord[col] == u'default':
					rowRecord[col] = ''
			self._data.append(rowRecord)

		self._logger.info('Number of local records:%d, will remove %d of them which are merged!', len(self._srcData), len(eraseList))		
		#Erase merged data
		for record in eraseList:
			self._srcData.remove(record)	

		self._removeDangling()
		
		#Keep local
		for rowData in self._srcData:
			#self._logger.debug("Keep local record with fid=%s", rowRecord[self._fidIndex])
			rowRecord = [(self._isNewCol(col) and u'unspecified' or rowData[self._getLocalColId(col)])
									for col in range(0, len(self._hdr))]
			rowRecord[self._hintIndex] = u'local'
			self._data.append(rowRecord)
		self._logger.info("Filtered %d records", len(self._data))

	def _mergeRecord(self, rowRecord, localRecord):
		diffColIds = []
		conflictColIds = []
		for col in range(0, len(rowRecord)): 
			if self._isNewCol(col) or localRecord[self._getLocalColId(col)] != rowRecord[col]:
				#new column or same colmn with different value
				diffColIds.append(col)
		for col in diffColIds:
			if (rowRecord[col] == 'default') and (not self._isNewCol(col)): 
				#Filled in during parsing (populate data previously) - definitely local column
				#self._logger.debug("[deault found] Set col:%d as %s", col, self._getLocalColId(col))
				rowRecord[col] = localRecord[self._getLocalColId(col)]
			else:
				if self._isNewCol(col):
					localValue = u''
				else:
					conflictColIds.append(col) 
					localValue = localRecord[self._getLocalColId(col)]
				newValue = rowRecord[col]
				if newValue == u'default': newValue = ''

				if self._shouldRetainCol(col):
					self._logger.info("Retaining %s:%s - local:%s, new:%s, take local value though new value is different",
								rowRecord[self._fidIndex], self._hdr[col], localValue, newValue)
					rowRecord[col] = localValue #New value is "", keep local
				else:
					#overwritten
					rowRecord[col] = newValue #keep new value and overwrite local
					self._logger.info("Overwritting %s:%s - local:%s, new:%s, take new value anyway since this is imported field",
							rowRecord[self._fidIndex], self._hdr[col], localValue, newValue)
		if len(conflictColIds) > 0:
			rowRecord[self._hintIndex] = unicode(','.join([str(id) for id in conflictColIds]))
		else:
			rowRecord[self._hintIndex] = u'updated'
		return diffColIds

	def _removeDangling(self):
		''' Remove dangling old records'''
		eraseList = []
		for rowData in self._srcData:
			fid = rowData[self._fidIndex]
			if fid.startswith("LBT") or fid.startswith("lbt") or fid.startswith("LTE") or fid.startswith("lte") or fid.startswith('CT'):
				if not self._isFidValidInUpstream(rowData[self._fidIndex]):
					self._logger.warning("Tag %s as to be removed since it's no longer a valid official feature in FBP now", fid)
					eraseList.append(rowData)
			else:
				#local feature, keep still
				self._logger.info("Will keep %s as local - suppose this is a internal feature", fid)
				if not fid.startswith('OAM'):
					self._logger.warning("Malformed dangling feature %s found, check if it's properly set!", fid)
		
		self._logger.info('Number of local records:%d, will remove %d of them as dangling!', len(self._srcData), len(eraseList))
		for record in eraseList:
			self._srcData.remove(record)

	def purgeDoneFeatures(self):
		'''Perge the done features if all its sub-features and the parent feature is done'''
		self._raIndex = self._hdr.index('Requirement Area')
		statusIndex = self._hdr.index("COMMON DEV STATUS")
		isFeatureInMyRA = lambda row: row[self._raIndex] == 'TDD-AifSiteS'
		rowCnt = len(self._data)

		#Filter through second-level features as parent
		# A feature will be removed if all the sub-features of its parent is done
		isFeatureDone = lambda row: row[statusIndex] == 'done' or row[statusIndex] == 'obsolete'
		getFid = lambda row: row[self._fidIndex]
		isSubFeature = lambda child, parent: getFid(child).find(getFid(parent)) == 0

		doneFeatures = [row for row in self._data if isFeatureDone(row)]
		parentFeatureList = [row for row in doneFeatures if getFid(row).count('-') <= 1]

		keepList = []
		for parent in parentFeatureList:
			unDones = [row for row in self._data if isSubFeature(row, parent) and (not isFeatureDone(row))]
			unDonesInRA = [row for row in unDones if isFeatureInMyRA(row)]
			#Have unDone features, and (have raUnDones or parent lead by RA) 
			if len(unDones) > 0 and ((len(unDonesInRA) > 0) or isFeatureInMyRA(parent)):
				keepList.append(parent)
				self._logger.info('Parent feature %s will be kept since below features undone:%s',
						getFid(parent), ','.join([row[self._fidIndex] for row in unDones]))

		for parent in [row for row in parentFeatureList if row not in keepList]:
			#remove all sub-features
			for row in [row for row in self._data if isSubFeature(row, parent)]:
				self._logger.debug('Remove done/obsolete feature:%s(subfeture of %s) as whole feature is done/obsolete!',
						getFid(row), getFid(parent));
				self._data.remove(row)
		self._logger.info('Leftover feature number:%d, removed:%d', len(self._data) - 1, rowCnt - len(self._data))

	def sortData(self):
		''' sort data by backlog priority'''
		dataContent = self._data[1:]
		def sortByPrioAndName(x, y):
			ret = cmp(int(x[self._priorityIndex]), int(y[self._priorityIndex]))
			if ret == 0:
				ret = cmp(x[self._fidIndex], y[self._fidIndex])
			return ret
		dataContent.sort(sortByPrioAndName)

		self._data = [self._data[0]]
		self._data.extend(dataContent)
		self._logger.info("Data sorted by column:%s", self._data[0][self._priorityIndex])