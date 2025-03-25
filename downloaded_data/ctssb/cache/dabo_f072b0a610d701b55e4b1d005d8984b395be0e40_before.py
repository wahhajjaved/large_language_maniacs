# -*- coding: utf-8 -*-
import types
import re
import warnings
import time
import dabo
import dabo.dConstants as kons
from dabo.db.dCursorMixin import dCursorMixin
from dabo.dLocalize import _
import dabo.dException as dException
from dabo.dObject import dObject
from dabo.lib.RemoteConnector import RemoteConnector


NO_RECORDS_PK = "75426755-2f32-4d3d-86b6-9e2a1ec47f2c"  ## Can't use None



class dBizobj(dObject):
	""" The middle tier, where the business logic resides."""
	# Class to instantiate for the cursor object
	dCursorMixinClass = dCursorMixin
	# Tell dObject that we'll call before and afterInit manually:
	_call_beforeInit, _call_afterInit, _call_initProperties = False, False, False


	def __init__(self, conn=None, properties=None, *args, **kwargs):
		""" User code should override beforeInit() and/or afterInit() instead."""
		self.__att_try_setFieldVal = False
		# Collection of cursor objects. MUST be defined first.
		self.__cursors = {}
		# PK of the currently-selected cursor
		self.__currentCursorKey = None
		self._dataStructure = None

		# Dictionary holding any default values to apply when a new record is created. This is
		# now the DefaultValues property (used to be self.defaultValues attribute)
		self._defaultValues = {}

		# PKs of rows to be filtered out when filtering Virtual fields
		self.__filterPKVirtual = []
		
		self._beforeInit()
		# This starts as a list that will hold cursors created in the initial process
		# if RequeryOnLoad is True. This is necessary because not all of the required
		# properties will have been set at this point. 
		# It will be set to None in the _afterInit() code, to indicate that it is no longer relevant.
		self.__cursorsToRequery = []
		self._requeryOnLoad = self._extractKey((properties, kwargs), "RequeryOnLoad", False)
		self.setConnection(conn)
		# We need to make sure the cursor is created *before* the call to
		# initProperties()
		self._initProperties()
		super(dBizobj, self).__init__(properties=properties, *args, **kwargs)
		self._afterInit()
		self.__att_try_setFieldVal = True


	def _beforeInit(self):
		# Cursor to manage SQL Builder info.
		self._sqlMgrCursor = None
		self._cursorFactory = None
		self.__params = ()		# tuple of params to be merged with the sql in the cursor
		self.__children = []		# Collection of child bizobjs
		self._baseClass = dBizobj
		self.__areThereAnyChanges = False	# Used by the isChanged() method.
		# Used by the LinkField property
		self._linkField = ""
		self._parentLinkField = ""
		# Used the the _addChildByRelationDict() method to eliminate infinite loops
		self.__relationDictSet = False
		# Do we try to same on the same record during a requery?
		self._restorePositionOnRequery = True

		# Various attributes used for Properties
		self._caption = ""
		self._dataSource = ""
		self._nonUpdateFields = []
		self._scanRestorePosition = True
		self._scanRequeryChildren = False
		self._scanReverse = False
		self._userSQL = None
		self._parent  = None
		self._autoPopulatePK = True
		self._autoQuoteNames = True
		self._keyField = ""
		self._requeryChildOnSave = False
		self._newRecordOnNewParent = False
		self._newChildOnNew = False
		self._fillLinkFromParent = False
		self.exitScan = False
		self.dbapiCursorClass = None
		self._childCacheInterval = None

		##########################################
		### referential integrity stuff ####
		##########################################
		### Possible values for each type (not all are relevant for each action):
		### IGNORE - don't worry about the presence of child records
		### RESTRICT - don't allow action if there are child records
		### CASCADE - changes to the parent are cascaded to the children
		self.deleteChildLogic = kons.REFINTEG_CASCADE  # child records will be deleted
		self.updateChildLogic = kons.REFINTEG_IGNORE   # parent keys can be changed w/o
		                                            # affecting children
		self.insertChildLogic = kons.REFINTEG_IGNORE   # child records can be inserted
		                                            # even if no parent record exists.
		##########################################

		self.beforeInit()


	def _afterInit(self):
		super(dBizobj, self)._afterInit()
		for crs in self.__cursorsToRequery:
			self._syncCursorProps(crs)
			crs.requery()
		self.__cursorsToRequery = None


	def setConnection(self, conn):
		"""Normally connections are established before bizobj creation, but
		for those cases where connections are created later, use this method to
		establish the connection used by the bizobj.
		"""
		self._cursorFactory = self._connection = conn
		if conn:
			# Base cursor class : the cursor class from the db api
			self.dbapiCursorClass = self._cursorFactory.getDictCursorClass()
			# If there are any problems in the createCursor process, an
			# exception will be raised in that method.
			self.createCursor()


	def _getConnection(self):
		return self._connection


	def getTempCursor(self, sql=None, params=None, requery=True):
		"""Occasionally it is useful to be able to run ad-hoc queries against
		the database. For these queries, where the results are not meant to
		be managed as in regular bizobj/cursor relationships, a temp cursor
		will allow you to run those queries, get the results, and then dispose
		of the cursor.

		If you send no arguments, you'll get a cursor to use how you want, like:

			cur = self.getTempCursor()
			cur.UserSQL = "select count(*) as count from invoices where cust_id = ?"
			cur.requery((883929,))
			invoiceCount = cur.Record.count

		But you can also simplify by sending the sql and params in the call:

			cur = self.getTempCursor("select count(*) as count...", (883929,))
			invoiceCount = cur.Record.count

		Note that if you send params, the cursor will be requeried even if
		the requery arg is False.
		"""
		cf = self._cursorFactory
		cursorClass = self._getCursorClass(self.dCursorMixinClass,
				self.dbapiCursorClass)
		crs = cf.getCursor(cursorClass)
		crs.BackendObject = cf.getBackendObject()
		crs.setCursorFactory(cf.getCursor, cursorClass)

		cur = crs.AuxCursor

		if sql:
			cur.UserSQL = sql
			if params or requery:
				cur.requery(params)
		return cur
		

	def createCursor(self, key=None):
		""" Create the cursor that this bizobj will be using for data, and store it
		in the dictionary for cursors, with the passed value of 'key' as its dict key.
		For independent bizobjs, that key will be None.

		Subclasses should override beforeCreateCursor() and/or afterCreateCursor()
		instead of overriding this method, if possible. Returning any non-empty value
		from beforeCreateCursor() will prevent the rest of this method from
		executing.
		"""
		if self.__cursors:
			_dataStructure = getattr(self.__cursors[self.__cursors.keys()[0]], "_dataStructure", None)
			self._virtualFields = getattr(self.__cursors[self.__cursors.keys()[0]], "_virtualFields", {})
		else:
			# The first cursor is being created, before DataStructure is assigned.
			_dataStructure = None
			self._virtualFields = {}
		errMsg = self.beforeCreateCursor()
		if errMsg:
			raise dException.dException(errMsg)

		if not self.dbapiCursorClass:
			return
		cursorClass = self._getCursorClass(self.dCursorMixinClass,
				self.dbapiCursorClass)

		if key is None:
			key = self.__currentCursorKey

		cf = self._cursorFactory
		self.__cursors[key] = cf.getCursor(cursorClass)
		self.__cursors[key].setCursorFactory(cf.getCursor, cursorClass)

		crs = self.__cursors[key]
		if _dataStructure is not None:
			crs._dataStructure = _dataStructure
		crs.BackendObject = cf.getBackendObject()
		crs.sqlManager = self.SqlManager
		crs._bizobj = self
		self._syncCursorProps(crs)
		if self.RequeryOnLoad:
			if self.__cursorsToRequery is None:
				# We've already passed the bizobj init process
				crs.requery()
				self.first()
			else:
				# Still in the init, so add it to the list
				self.__cursorsToRequery.append(crs)
		self.afterCreateCursor(crs)
		return crs


	def _getCursorClass(self, main, secondary):
		class cursorMix(main, secondary):
			superMixin = main
			superCursor = secondary
			def __init__(self, *args, **kwargs):
				if hasattr(main, "__init__"):
					apply(main.__init__,(self,) + args, kwargs)
				if hasattr(secondary, "__init__"):
					apply(secondary.__init__,(self,) + args, kwargs)
		return  cursorMix


	def first(self):
		""" Move to the first record of the data set.

		Any child bizobjs will be requeried to reflect the new parent record. If
		there are no records in the data set, an exception will be raised.
		"""
		errMsg = self.beforeFirst()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		self._CurrentCursor.first()
		self.requeryAllChildren()

		self.afterPointerMove()
		self.afterFirst()


	def prior(self):
		""" Move to the prior record of the data set.

		Any child bizobjs will be requeried to reflect the new parent record. If
		there are no records in the data set, an exception will be raised.
		"""
		errMsg = self.beforePrior()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		self._CurrentCursor.prior()
		self.requeryAllChildren()

		self.afterPointerMove()
		self.afterPrior()


	def next(self):
		""" Move to the next record of the data set.

		Any child bizobjs will be requeried to reflect the new parent record. If
		there are no records in the data set, an exception will be raised.
		"""
		errMsg = self.beforeNext()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		self._CurrentCursor.next()
		self.requeryAllChildren()

		self.afterPointerMove()
		self.afterNext()


	def last(self):
		""" Move to the last record of the data set.

		Any child bizobjs will be requeried to reflect the new parent record. If
		there are no records in the data set, an exception will be raised.
		"""
		errMsg = self.beforeLast()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		self._CurrentCursor.last()
		self.requeryAllChildren()

		self.afterPointerMove()
		self.afterLast()


	def beginTransaction(self):
		"""Attempts to begin a transaction at the database level, and returns
		True/False depending on its success.
		"""
		rp = self._RemoteProxy
		if rp:
			return rp.beginTransaction()
		ret = self._getTransactionToken()
		if ret:
			self._CurrentCursor.beginTransaction()
		return ret


	def commitTransaction(self):
		"""Attempts to commit a transaction at the database level, and returns
		True/False depending on its success.
		"""
		rp = self._RemoteProxy
		if rp:
			return rp.commitTransaction()
		ret = self._hasTransactionToken() and self._CurrentCursor.commitTransaction()
		if ret:
			self._releaseTransactionToken()
		return ret


	def rollbackTransaction(self):
		"""Attempts to rollback a transaction at the database level, and returns
		True/False depending on its success.
		"""
		rp = self._RemoteProxy
		if rp:
			return rp.rollbackTransaction()
		ret = self._hasTransactionToken() and self._CurrentCursor.rollbackTransaction()
		if ret:
			self._releaseTransactionToken()
		return ret


	def _getTransactionToken(self):
		"""Ask the Application for the transaction token. If the token is granted,
		then this bizobj has the ability to begin and end transactions.
		"""
		try:
			return self.Application.getTransactionToken(self)
		except AttributeError:
			if not hasattr(dabo, "_bizTransactionToken"):
				dabo._bizTransactionToken = self
				return True
			return False


	def _hasTransactionToken(self):
		"""Returns True/False, depending on whether this bizobj
		currently "holds" the transaction token.
		"""
		try:
			ret = self.Application.hasTransactionToken(self)
		except AttributeError:
			ret = hasattr(dabo, "_bizTransactionToken") and (dabo._bizTransactionToken is self)
		return ret


	def _releaseTransactionToken(self):
		"""Ask the Application to give up the transaction token. Once this is done,
		other bizobjs can receive the token to begin and end transactions.
		"""
		try:
			self.Application.releaseTransactionToken(self)
		except AttributeError:
			# No Application in play: fake it.
			if hasattr(dabo, "_bizTransactionToken") and dabo._bizTransactionToken == self:
				del(dabo._bizTransactionToken)


	def saveAll(self, startTransaction=True):
		"""Saves all changes to the bizobj and children."""
		rp = self._RemoteProxy
		if rp:
			return rp.saveAll(startTransaction=startTransaction)
		cursorKey = self.__currentCursorKey
		current_row = self.RowNumber
		startTransaction = startTransaction and self.beginTransaction()
		try:
			self.scanChangedRows(self.save, includeNewUnchanged=self.SaveNewUnchanged,
					startTransaction=False)
			if startTransaction:
				self.commitTransaction()

		except dException.ConnectionLostException:
			self._CurrentCursor = cursorKey
			self.RowNumber = current_row
			raise
		except dException.DBQueryException:
			# Something failed; reset things.
			if startTransaction:
				self.rollbackTransaction()
			self._CurrentCursor = cursorKey
			self.RowNumber = current_row
			# Pass the exception to the UI
			raise
		except dException.dException:
			if startTransaction:
				self.rollbackTransaction()
			self._CurrentCursor = cursorKey
			self.RowNumber = current_row
			raise
		self._CurrentCursor = cursorKey
		if current_row >= 0:
			try:
				self.RowNumber = current_row
			except StandardError, e:
				# Need to record what sort of error could be thrown
				dabo.errorLog.write(_("Failed to set RowNumber. Error: %s") % e)


	def save(self, startTransaction=True):
		"""Save any changes that have been made in the current row.

		If the save is successful, the saveAll() of all child bizobjs will be
		called as well.
		"""
		rp = self._RemoteProxy
		if rp:
			return rp.save(startTransaction=startTransaction)
		cursor = self._CurrentCursor
		errMsg = self.beforeSave()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		if self.KeyField is None:
			raise dException.MissingPKException(
					_("No key field defined for table: ") + self.DataSource)

		# Validate any changes to the data. If there is data that fails
		# validation, an Exception will be raised.
		self._validate()

		startTransaction = startTransaction and self.beginTransaction()
		# Save to the Database, but first save the IsAdding flag as the save() call
		# will reset it to False:
		isAdding = self.IsAdding
		try:
			cursor.save(includeNewUnchanged=self.SaveNewUnchanged)
			if isAdding:
				# Call the hook method for saving new records.
				self._onSaveNew()

			# Iterate through the child bizobjs, telling them to save themselves.
			for child in self.__children:
				# No need to start another transaction. And since this is a child bizobj,
				# we need to save all rows that have changed.
				if child.RowCount > 0:
					child.saveAll(startTransaction=False)

			# Finish the transaction, and requery the children if needed.
			if startTransaction:
				self.commitTransaction()
			if self.RequeryChildOnSave:
				self.requeryAllChildren()

		except dException.ConnectionLostException:
			raise

		except dException.NoRecordsException:
			raise

		except dException.DBQueryException:
			# Something failed; reset things.
			if startTransaction:
				self.rollbackTransaction()
			# Pass the exception to the UI
			raise

		except dException.dException:
			# Something failed; reset things.
			if startTransaction:
				self.rollbackTransaction()
			# Pass the exception to the UI
			raise

		# Two hook methods: one specific to Save(), and one which is called after any change
		# to the data (either save() or delete()).
		self.afterChange()
		self.afterSave()


	def cancelAll(self, ignoreNoRecords=None):
		"""Cancel all changes made to the current dataset, including all children
		and all new, unmodified records.
		"""
		self.scanChangedRows(self.cancel, allCursors=False, includeNewUnchanged=True,
				ignoreNoRecords=ignoreNoRecords)


	def cancel(self, ignoreNoRecords=None):
		"""Cancel all changes to the current record and all children.

		Two hook methods will be called: beforeCancel() and afterCancel(). The
		former, if it returns an error message, will raise an exception and not
		continue cancelling the record.
		"""
		errMsg = self.beforeCancel()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)
		if ignoreNoRecords is None:
			# Canceling changes when there are no records should
			# normally not be a problem.
			ignoreNoRecords = True
		# Tell the cursor and all children to cancel themselves:
		self._CurrentCursor.cancel(ignoreNoRecords=ignoreNoRecords)
		for child in self.__children:
			child.cancelAll(ignoreNoRecords=ignoreNoRecords)
		self.afterCancel()


	def deleteAllChildren(self, startTransaction=True):
		"""Delete all children associated with the current record without
		deleting the current record in this bizobj.
		"""
		cursorKey = self.__currentCursorKey
		errMsg = self.beforeDeleteAllChildren()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		startTransaction = startTransaction and self.beginTransaction()
		try:
			for child in self.__children:
				child.deleteAll(startTransaction=False)
			if startTransaction:
				self.commitTransaction()

		except dException.DBQueryException:
			if startTransaction:
				self.rollbackTransaction()
			self._CurrentCursor = cursorKey
			raise
		except StandardError:
			if startTransaction:
				self.rollbackTransaction()
			self._CurrentCursor = cursorKey
			raise
		self._CurrentCursor = cursorKey
		self.afterDeleteAllChildren()


	def delete(self, startTransaction=True, inLoop=False):
		"""Delete the current row of the data set."""
		rp = self._RemoteProxy
		if rp:
			return rp.delete()
		cursor = self._CurrentCursor
		errMsg = self.beforeDelete()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		if self.KeyField is None:
			raise dException.dException(
					_("No key field defined for table: ") + self.DataSource)

		if self.deleteChildLogic == kons.REFINTEG_RESTRICT:
			# See if there are any child records
			for child in self.__children:
				if child.RowCount > 0:
					raise dException.dException(
							_("Deletion prohibited - there are related child records."))

		startTransaction = startTransaction and self.beginTransaction()
		try:
			cursor.delete()
			if self.RowCount == 0:
				# Hook method for handling the deletion of the last record in the cursor.
				self.onDeleteLastRecord()
			# Now cycle through any child bizobjs and fire their cancel() methods. This will
			# ensure that any changed data they may have is reverted. They are then requeried to
			# populate them with data for the current record in this bizobj.
			for child in self.__children:
				if self.deleteChildLogic == kons.REFINTEG_CASCADE:
					child.deleteAll(startTransaction=False)
				else:
					child.cancelAll()
				child.requery()
			if startTransaction:
				self.commitTransaction()

			if not inLoop:
				self.afterPointerMove()
				self.afterChange()
				self.afterDelete()
		except dException.DBQueryException:
			if startTransaction:
				self.rollbackTransaction()
			raise
		except StandardError:
			if startTransaction:
				self.rollbackTransaction()
			raise


	def deleteAll(self, startTransaction=True):
		""" Delete all rows in the data set."""
		rp = self._RemoteProxy
		if rp:
			return rp.deleteAll()
		cursorKey = self.__currentCursorKey
		startTransaction = startTransaction and self.beginTransaction()
		try:
			while self.RowCount > 0:
				self.first()
				self.delete(startTransaction=False, inLoop=True)
			if startTransaction:
				self.commitTransaction()

			self.afterPointerMove()
			self.afterChange()
			self.afterDelete()
		except dException.DBQueryException:
			if startTransaction:
				self.rollbackTransaction()
			self._CurrentCursor = cursorKey
			raise
		except StandardError:
			if startTransaction:
				self.rollbackTransaction()
			self._CurrentCursor = cursorKey
			raise
		self._CurrentCursor = cursorKey


	def execute(self, sql, params=None):
		"""Execute the sql on the cursor. Dangerous. Use executeSafe instead."""
		self._syncWithCursors()
		return self._CurrentCursor.execute(sql, params)


	def executeSafe(self, sql, params=None):
		"""Execute the passed SQL using an auxiliary cursor.

		This is considered 'safe', because it won't harm the contents of the
		main cursor.
		"""
		self._syncWithCursors()
		return self._CurrentCursor.executeSafe(sql, params)


	def getDataDiff(self, allRows=False):
		"""Get a dict that is keyed on the hash value of this bizobj, with the value
		being  a list of record changes. Default behavior is to only consider the
		current row; you can change that by passing allRows=True. Each changed
		row will be present in the diff, with its PK and any columns whose values
		have changed. If there are any related child bizobjs, their diffs will be
		added to the dict under the key 'children' so that they can be processed
		accordingly.
		"""
		myData = self._CurrentCursor.getDataDiff(allRows=allRows)
		kids = {}
		for child in self.__children:
			kids.update(child.getDataDiff(allRows=True))
		diff = {hash(self): (self.DataSource, self.KeyField, myData, kids)}
		return diff


	def getChangedRows(self, includeNewUnchanged=False):
		""" Returns a list of row numbers for which isChanged() returns True. The
		changes may therefore not be in the record itself, but in a dependent child
		record. If includeNewUnchanged is True, the presence of a new unsaved
		record that has not been modified from its defaults will suffice to mark the
		record as changed.
		"""
		if self.__children:
			# Must iterate all records to find potential changes in children:
			self.__changedRows = []
			self.scan(self._listChangedRows, includeNewUnchanged)
			return self.__changedRows
		else:
			# Can use the much faster cursor.getChangedRows():
			return self._CurrentCursor.getChangedRows(includeNewUnchanged)


	def _listChangedRows(self, includeNewUnchanged=False):
		""" Called from a scan loop. If the current record is changed,
		append the RowNumber to the list.
		"""
		if self.isChanged(includeNewUnchanged):
			self.__changedRows.append(self.RowNumber)


	def getRecordStatus(self, rownum=None):
		""" Returns a dictionary containing an element for each changed
		field in the specified record (or the current record if none is specified).
		The field name is the key for each element; the value is a 2-element
		tuple, with the first element being the original value, and the second
		being the current value.
		"""
		if rownum is None:
			rownum = self.RowNumber
		return self._CurrentCursor.getRecordStatus(rownum)


	def bizIterator(self):
		"""Returns an iterator that moves the bizobj's record pointer from
		the first record to the last. You may call the iterator's reverse() method
		before beginning iteration in order to iterate from the last record
		back to the first.
		"""
		return _bizIterator(self)


	def scan(self, func, *args, **kwargs):
		"""Iterate over all records and apply the passed function to each.

		Set self.exitScan to True to exit the scan on the next iteration.

		If self.ScanRestorePosition is True, the position of the current
		record in the recordset is restored after the iteration.
		
		If self.ScanRequeryChildren is True, any child bizobjs will be requeried
		for each row in the bizobj. Only use this if you know the size of the data
		involved will be small.

		You may optionally send reverse=True to scan the records in reverse
		order, which you'll want to do if, for example, you are deleting 
		records in your scan function. If the reverse argument is not sent,
		self.ScanReverse will be queried to determine the behavior.
		"""
		self.scanRows(func, range(self.RowCount), *args, **kwargs)


	def scanRows(self, func, rows, *args, **kwargs):
		"""Iterate over the specified rows and apply the passed function to each.

		Set self.exitScan to True to exit the scan on the next iteration.
		"""
		# Flag that the function can set to prematurely exit the scan
		self.exitScan = False
		rows = list(rows)
		try:
			reverse = kwargs["reverse"]
			del(kwargs["reverse"])
		except KeyError:
			reverse = self.ScanReverse
		try:
			currPK = self.getPK()
			currRow = None
		except dException.dException:
			# No PK defined
			currPK = None
			currRow = self.RowNumber

		def restorePosition():
			if self.ScanRestorePosition:
				if currPK is not None:
					self._positionUsingPK(currPK)
				else:
					try:
						self.RowNumber = currRow
					except StandardError, e:
						# Perhaps the row was deleted; at any rate, leave the pointer
						# at the end of the data set
						row = self.RowCount  - 1
						if row >= 0:
							self.RowNumber = row
		requeryChildren = self.ScanRequeryChildren
		try:
			if reverse:
				rows.reverse()
			for i in rows:
				self._moveToRowNum(i, updateChildren=requeryChildren)
				func(*args, **kwargs)
				if self.exitScan:
					break
		except Exception:
			restorePosition()
			raise
		restorePosition()


	def scanChangedRows(self, func, allCursors=False, includeNewUnchanged=False,
			*args, **kwargs):
		"""Move the record pointer to each changed row, and call func.

		If allCursors is True, all other cursors for different parent records will
		be iterated as well.

		If includeNewUnchanged is True, new unsaved records that have not been
		edited from their default values will be counted as 'changed'.

		If you want to end the scan on the next iteration, set self.exitScan=True.

		Records are scanned in arbitrary order. Any exception raised by calling
		func() will be passed	up to the caller.
		"""
		self.exitScan = False
		currCursor = self._CurrentCursor
		old_currentCursorKey = self.__currentCursorKey
		try:
			old_pk = currCursor.getPK()
		except dException.NoRecordsException:
			# no rows to scan
			return

		if allCursors:
			cursors = self.__cursors
		else:
			cursors = {old_currentCursorKey: currCursor}

		for key, cursor in cursors.iteritems():
			self._CurrentCursor = key
			changedRows = self.getChangedRows(includeNewUnchanged)
			for row in sorted(changedRows, reverse=True):
				self._moveToRowNum(row)
				try:
					func(*args, **kwargs)
				except StandardError, e:
					# Reset things and bail
					dabo.errorLog.write(_("Error in scanChangedRows: %s") % e)
					self._CurrentCursor = old_currentCursorKey
					self._positionUsingPK(old_pk)
					raise

		self._CurrentCursor = old_currentCursorKey
		if old_pk is not None:
			self._positionUsingPK(old_pk)


	def getFieldNames(self):
		"""Returns a tuple of all the field names in the cursor."""
		rp = self._RemoteProxy
		if rp:
			return rp.getFieldNames()
		flds = self._CurrentCursor.getFields()
		# This is a tuple of 3-tuples; we just want the names
		return tuple([ff[0] for ff in flds])


	def _fldReplace(self, expr):
		"""Takes a user-defined, SQL-like expression, and substitutes any 
		field name with the reference for that value in the bizobj.
		Example (assuming 'price' is a column in the data):
			self._fldReplace("price > 50")
				=> returns "self.Record.price > 50"
		"""
		patTemplate = r"(.*\b)%s(\b.*)"
		ret = expr
		for fld in self.getFieldNames():
			pat = patTemplate % fld
			mtch = re.match(pat, ret)
			if mtch:
				ret = mtch.groups()[0] + "self.Record.%s" % fld + mtch.groups()[1]
		return ret


	def replace(self, field, valOrExpr, scope=None):
		"""Replaces the value of the specified field with the given value
		or expression. All records matching the scope are affected; if
		no scope is specified, all records are affected.

		'valOrExpr' will be treated as a literal value, unless it is prefixed
		with an equals sign. All expressions will therefore be a string
		beginning with '='. Literals can be of any type.
		"""
		self.scan(self._replace, field, valOrExpr, scope)


	def _replace(self, field, valOrExpr, scope):
		"""Called once for each record in the bizobj when the replace() method
		is invoked.
		"""
		if scope is not None:
			scope = self._fldReplace(scope)
			if not eval(scope):
				return
		literal = True
		try:
			if valOrExpr.startswith("="):
				literal = False
				valOrExpr = valOrExpr.strip()[1:]
				valOrExpr = self._fldReplace(valOrExpr)
				valOrExpr = eval(valOrExpr)
		except AttributeError:
			# Not a string expression; no worries
			pass
		self.setFieldVal(field, valOrExpr)


	def new(self):
		""" Create a new record and populate it with default values. Default
		values are specified in the DefaultValues dictionary.
		"""
		errMsg = self.beforeNew()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		self._CurrentCursor.new()
		self._onNew()

		# Update all child bizobjs
		self.requeryAllChildren()

		if self.NewChildOnNew:
			# Add records to all children set to have records created on a new parent record.
			for child in self.__children:
				if child.NewRecordOnNewParent:
					child.new()

		self.afterPointerMove()
		self.afterNew()


	def setSQL(self, sql=None):
		""" Set the SQL query that will be executed upon requery().

		This allows you to manually override the sql executed by the cursor. If no
		sql is passed, the SQL will get set to the value returned by getSQL().
		"""
		if sql is None:
			# sql not passed; get it from the sql mixin:
			# Set the appropriate child filter on the link field
			self.setChildLinkFilter()
		else:
			# sql passed; set it explicitly
			self.UserSQL = sql


	def requery(self):
		""" Requery the data set.

		Refreshes the data set with the current values in the database,
		given the current state of the filtering parameters.
		"""
		rp = self._RemoteProxy
		if rp:
			return rp.requery()
		errMsg = self.beforeRequery()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)
		if self.KeyField is None:
			errMsg = _("No Primary Key defined in the Bizobj for %s") % self.DataSource
			raise dException.MissingPKException(errMsg)

		# If this is a dependent (child) bizobj, this will enforce the relation
		_childParamTuple = self.setChildLinkFilter()

		# Hook method for creating the param tuple. Note that the child filter
		# clause, if any, will always be the first clause in the WHERE expression.
		params = _childParamTuple + self.getParams()

		# Record this in case we need to restore the record position
		try:
			currPK = self.getPK()
		except dException.NoRecordsException:
			currPK = None

		# run the requery
		uiException = None
		cursor = self._CurrentCursor
		try:
			cursor.requery(params)

		except dException.ConnectionLostException:
			raise

		except dException.DBQueryException:
			raise

		except dException.NoRecordsException:
			# Pass the exception to the UI
			uiException = dException.NoRecordsException

		except dException.dException:
			raise

		if self.RestorePositionOnRequery:
			self._positionUsingPK(currPK)

		try:
			self.requeryAllChildren()
		except dException.NoRecordsException:
			pass
		self.afterRequery()
		if uiException:
			raise uiException


	def setChildLinkFilter(self):
		""" If this is a child bizobj, its record set is dependent on its parent's
		current PK value. This will add the appropriate WHERE clause to
		filter the child records. If the parent is a new, unsaved record, or if
		there is no parent record, there cannot be any child records saved yet,
		so an empty query is built.
		"""
		# Return a tuple of the params. Default to an empty tuple.
		ret = tuple()
		if self.DataSource and self.LinkField and self.Parent:
			if self.Parent.RowCount == 0:
				# Parent is new and not yet saved, so we cannot have child records yet.
				self._CurrentCursor.setNonMatchChildFilterClause()
			else:
				val = self.getParentLinkValue()
				linkFieldParts = self.LinkField.split(".")
				if len(linkFieldParts) < 2:
					linkField = self.LinkField
				else:
					# The source table was specified in the LinkField
					linkField = linkFieldParts[1]
				self._CurrentCursor.setChildFilter(linkField)
				ret = (val, )
		return ret


	def getParentLinkValue(self):
		"""Return the value of the parent record on which this bizobj is dependent. Usually this
		is the PK of the parent, but can be a non-PK field, if this bizobj's ParentLinkField is
		not empty.
		"""
		ret = None
		if self.Parent:
			fld = self.ParentLinkField
			try:
				if not fld:
					# Use the PK value
					ret = self.getParentPK()
				else:
					ret = self.Parent.getFieldVal(fld)
			except dException.NoRecordsException:
				ret = NO_RECORDS_PK
		return ret


	def sort(self, col, ordr=None, caseSensitive=True):
		""" Sort the rows based on values in a specified column.

		Called when the data is to be sorted on a particular column
		in a particular order. All the checking on the parameters is done
		in the cursor.
		"""
		cc = self._CurrentCursor
		if cc is not None:
			self._CurrentCursor.sort(col, ordr, caseSensitive)


	def setParams(self, params):
		""" Set the query parameters for the cursor.

		Accepts a tuple that will be merged with the sql statement using the
		cursor's standard method for merging.
		"""
		if not isinstance(params, tuple):
			params = (params, )
		self.__params = params


	def filter(self, fld, expr, op="="):
		"""
		This takes a field name, an expression, and an optional operator, and applies that 
		to the current dataset. The original dataset is preserved; calling removeFilter() will 
		remove the last filter applied to the bizobj. If the current record is in the filtered 
		dataset, that record will still be current; if it is filtered out, the current row will 
		be row 0.
		If the operator is specified, it will be used literally in the evaluation instead of the 
		equals sign, unless it is one of the following strings, which will be interpreted 
		as indicated:
			eq, equals: =
			ne, nequals: !=
			gt: >
			gte: >=
			lt: <
			lte: <=
			startswith, beginswith: fld.startswith(expr)
			endswith: fld.endswith(expr)
			contains: expr in fld
		"""
		currPK = self.getPK()
		if fld in self.VirtualFields:
			self.scan(self.scanVirtualFields, fld=fld, expr=expr, op=op, reverse=True)
			self._CurrentCursor.filterByExpression("%s IN (%s)" % (
					self.KeyField, ", ".join( "%i" % key for key in self.__filterPKVirtual)))
			# clear filter ids
			self.__filterPKVirtual = []
		else:
			self._CurrentCursor.filter(fld=fld, expr=expr, op=op)

		try:
			newPK = self.getPK()
		except dException.NoRecordsException:
			newPK = currPK

		if newPK != currPK:
			try:
				self.moveToPK(currPK)
			except dabo.dException.RowNotFoundException:
				# The old row was filtered out of the dataset
				try:
					self.first()
				except dException.NoRecordsException:
					# All records were filtered out
					pass


	def filterByExpression(self, expr):
		"""Allows you to filter by any valid Python expression."""
		self._CurrentCursor.filterByExpression(expr)


	def scanVirtualFields(self, fld, expr, op):
		virtValue = self.getFieldVal(fld)

		if op.lower() in ("eq", "equals", "="):
			if virtValue == expr:
				self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

		elif op.lower() in ("ne", "nequals", "!="):
			if virtValue != expr:
				self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

		elif op.lower() in ("gt", ">", "greater than"):
			if expr > virtValue:
				self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

		elif op.lower() in ("gte", ">=", "greater than/equal to"):
			if expr >= virtValue:
				self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

		elif op.lower() in ("lt", "<", "less than"):
			if expr < virtValue:
				self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

		elif op.lower() in ("lte", "<=", "less than/equal to"):
			if expr <= virtValue:
				self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

		else:
			if isinstance(virtValue, basestring) and isinstance(expr, basestring):
				virtLower = virtValue.lower()
				exprLower = expr.lower()

			if op.lower() in ("starts with", "begins with"):
				if virtLower.startswith(exprLower):
					self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

			elif op.lower() == "endswith":
				if virtLower.endswith(exprLower):
					self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))

			elif op.lower() == "contains":
				if exprLower in virtLower:
					self.__filterPKVirtual.append(self.getFieldVal(self.KeyField))


	def removeFilter(self):
		"""Remove the most recently applied filter."""
		self._CurrentCursor.removeFilter()


	def removeFilters(self):
		"""Remove all applied filters, going back to the original data set."""
		self._CurrentCursor.removeFilters()


	def _validate(self):
		""" Internal method. User code should override validateRecord().

		_validate() is called by the save() routine before saving any data.
		If any data fails validation, an exception will be raised, and the
		save() will not be allowed to proceed.
		"""
		errMsg = ""
		if self.isChanged():
			# No need to validate if the data hasn't changed
			message = self.validateRecord()
			if message:
				errMsg += message
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)


	def validateRecord(self):
		""" Hook for subclass business rule validation code.

		This is the method that you should customize in your subclasses
		to create checks on the data entered by the user to be sure that it
		conforms to your business rules. Your validation code should return
		an error message that describes the reason why the data is not
		valid; this message will be propagated back up to the UI where it can
		be displayed to the user so that they can correct the problem.
		Example:

			if not myNonEmptyField:
				return "MyField must not be blank"

		It is assumed that we are on the correct record for testing before
		this method is called.
		"""
		pass


	def fieldValidation(self, fld, val):
		"""This is called by the form when a control that is marked for field-
		level validation loses focus. It handles communication between the
		bizobj methods and the form. When creating Dabo apps, if you want
		to add field-level validation rules, you should override fieldValidation()
		with your specific code.
		"""
		errMsg = ""
		message = self.validateField(fld, val)
		if message == kons.BIZ_DEFAULT_FIELD_VALID:
			# No validation was done
			return
		if message:
			errMsg += message
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)
		else:
			raise dException.BusinessRulePassed


	def validateField(self, fld, val):
		"""This is the method to override if you need field-level validation
		to your app. It will receive the field name and the new value; you can
		then apply your business rules to determine if the new value is
		valid. If not, return a string describing the problem. Any non-empty
		return value from this method will prevent the control's value
		from being changed.
		"""
		return kons.BIZ_DEFAULT_FIELD_VALID


	def _moveToRowNum(self, rownum, updateChildren=True):
		""" For internal use only! Should never be called from a developer's code.
		It exists so that a bizobj can move through the records in its cursor
		*without* firing additional code.
		"""
		self._CurrentCursor.moveToRowNum(rownum)
		if updateChildren:
			for child in self.__children:
				# Let the child update to the current record.
				child.setCurrentParent()


	def _positionUsingPK(self, pk, updateChildren=True):
		""" For internal use only! Should never be called from a developer's code.
		It exists so that a bizobj can move through the records in its cursor
		*without* firing additional code.
		"""
		if pk is not None:
			self._CurrentCursor.moveToPK(pk)
			if updateChildren:
				for child in self.__children:
					# Let the child update to the current record.
					child.setCurrentParent()


	def moveToPK(self, pk):
		"""Move to the row with the specified pk value, or raise RowNotFoundException."""
		row = self.seek(pk, self.KeyField, caseSensitive=True, near=False,
				runRequery=True)
		if row == -1:
			# Need to use str(pk) because pk might be a tuple.
			raise dabo.dException.RowNotFoundException, _("PK Value '%s' not found in the dataset") % str(pk)


	def hasPK(self, pk):
		"""Return True if the passed PK value is present in the dataset."""
		return self._CurrentCursor.hasPK(pk)


	def seek(self, val, fld=None, caseSensitive=False, near=False, runRequery=True):
		""" Search for a value in a field, and move the record pointer to the match.

		Used for searching of the bizobj's cursor for a particular value in a
		particular field. Can be optionally case-sensitive.

		If 'near' is True, and no exact match is found in the cursor, the cursor's
		record pointer will be placed at the record whose value in that field
		is closest to the desired value without being greater than the requested
		value.

		If runRequery is True, and the record pointer is moved, all child bizobjs
		will be requeried, and the afterPointerMove() hook method will fire.

		Returns the RowNumber of the found record, or -1 if no match found.
		"""
		ret = self._CurrentCursor.seek(val, fld, caseSensitive, near)
		if ret != -1:
			if runRequery:
				self.requeryAllChildren()
				self.afterPointerMove()
		return ret


	def isAnyChanged(self, useCurrentParent=None, includeNewUnchanged=None):
		"""Returns True if any record in the current record set has been changed."""
		if includeNewUnchanged is None:
			includeNewUnchanged = self.SaveNewUnchanged
		if useCurrentParent is None:
			cc = self._CurrentCursor
		else:
			key = self.getParentLinkValue()
			cc = self.__cursors.get(key, None)
		if cc is None:
			# No cursor, no changes.
			return False

		if cc.isChanged(allRows=True, includeNewUnchanged=includeNewUnchanged):
			return True

		# Nothing's changed in the top level, so we need to recurse the children:
		for child in self.__children:
			if child.isAnyChanged(useCurrentParent=useCurrentParent, includeNewUnchanged=includeNewUnchanged):
				return True
		# If we made it to here, there are no changes.
		return False


	def isChanged(self, includeNewUnchanged=None):
		""" Return True if data has changed in this bizobj and any children.

		By default, only the current record is checked. Call isAnyChanged() to
		check all records.
		"""
		if includeNewUnchanged is None:
			includeNewUnchanged = self.SaveNewUnchanged
		cc = self._CurrentCursor
		if cc is None:
			# No cursor, no changes.
			return False
		ret = cc.isChanged(allRows=False, includeNewUnchanged=includeNewUnchanged)

		if not ret:
			# see if any child bizobjs have changed
			if not self.RowCount:
				# If there are no records, there can be no changes
				return False
			for child in self.__children:
				ret = child.isAnyChanged(useCurrentParent=True, includeNewUnchanged=includeNewUnchanged)
				if ret:
					break
		return ret


	def onDeleteLastRecord(self):
		""" Hook called when the last record has been deleted from the data set."""
		pass


	def _onSaveNew(self):
		""" Called after successfully saving a new record."""
		# If this is a new parent record with a new auto-generated PK, pass it on
		# to the children before they save themselves.
		if self.AutoPopulatePK:
			pk = self.getPK()
			for child in self.__children:
				child.setParentFK(pk)
		# Call the custom hook method
		self.onSaveNew()


	def onSaveNew(self):
		""" Hook method called after successfully saving a new record."""
		pass


	def _onNew(self, setDefaults=True):
		""" Populate the record with any default values.

		User subclasses should leave this alone and instead override onNew().
		"""
		cursor = self._CurrentCursor
		currKey = self.__currentCursorKey
		if self.AutoPopulatePK:
			# Provide a temporary PK so that any linked children can be properly
			# identified until the record is saved and a permanent PK is obtained.
			tmpKey = cursor.genTempAutoPK()
			if currKey is None:
				self.__currentCursorKey = tmpKey
				del self.__cursors[currKey]
				self.__cursors[tmpKey] = cursor
		if setDefaults:
			cursor.setDefaults(self.DefaultValues)
		cursor.setNewFlag()
		# Fill in the link to the parent record
		if self.Parent and self.FillLinkFromParent and self.LinkField:
			self.setParentFK()

		# Call the custom hook method
		self.onNew()

		# Remove the memento for the new record, as we want to only record
		# changes made after this point.
		cursor._clearMemento()


	def onNew(self):
		"""Called when a new record is added.

		Use this hook to add additional default field values, or anything else
		you need. If you change field values here, the memento system will not
		catch it (the record will not be marked 'dirty'). Use afterNew() if you
		instead want the memento system to record the changes.
		"""
		pass


	def setParentFK(self, val=None):
		""" Accepts and sets the foreign key value linking to the
		parent table for all records.
		"""
		if self.LinkField:
			if val is None:
				val = self.getParentLinkValue()
			self.scan(self._setParentFK, val)

	def _setParentFK(self, val):
		self.setFieldVal(self.LinkField, val)


	def setCurrentParent(self, val=None):
		""" Lets dependent child bizobjs update to the current parent
		record.
		"""
		if self.LinkField:
			if val is None:
				val = self.getParentLinkValue()
			# Update the key value for the cursor
			self.__currentCursorKey = val
			# Make sure there is a cursor object for this key.
			self._CurrentCursor = val
			# Propagate the change to any children:
			for child in self.__children:
				child.setCurrentParent()


	def addChild(self, child):
		""" Add the passed child bizobj to this bizobj.

		During the creation of the form, child bizobjs are added by the parent.
		This stores the child reference here, and sets the reference to the
		parent in the child.
		"""
		if child not in self.__children:
			self.__children.append(child)
			child.Parent = self


	def getAncestorByDataSource(self, ds):
		"""Given a DataSource, finds the ancestor (parent, grandparent, etc.) of
		this bizobj that has that DataSource. If no such ancestor exists, returns None.
		"""
		ret = None
		if self.Parent:
			if self.Parent.DataSource == ds:
				ret = self.Parent
			else:
				ret = self.Parent.getAncestorByDataSource(ds)
		return ret


	def requeryAllChildren(self):
		""" Requery each child bizobj's data set.

		Called to assure that all child bizobjs have had their data sets
		refreshed to match the current master row. This will normally happen
		automatically when appropriate, but user code may call this as well
		if needed.
		"""
		if not self.__children:
			return True

		errMsg = self.beforeChildRequery()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)

		for child in self.__children:
			# Let the child know the current dependent PK
			if child.RequeryWithParent:
				child.setCurrentParent()
				if not child.isAnyChanged(useCurrentParent=True):
					# Check for caching
					if child.cacheExpired():
						child.requery()
		self.afterChildRequery()


	def cacheExpired(self):
		"""This controls if a child requery is needed when a parent is requeried."""
		ret = True
		if self._childCacheInterval:
			last = self._CurrentCursor.lastRequeryTime
			ret = ((time.time() - last) > self._childCacheInterval)
		return ret


	def getPK(self):
		""" Return the value of the PK field."""
		if self.KeyField is None:
			raise dException.dException(
					_("No key field defined for table: ") + self.DataSource)
		cc = self._CurrentCursor
		return cc.pkExpression()


	def getParentPK(self):
		""" Return the value of the parent bizobjs' PK field. Alternatively,
		user code can just call self.Parent.getPK().
		"""
		try:
			return self.Parent.getPK()
		except dException.NoRecordsException:
			# The parent bizobj has no records
			return None


	def getFieldVal(self, fld, row=None, _forceNoCallback=False):
		"""Return the value of the specified field in the current or specified row."""
		cursor = self._CurrentCursor
		oldRow = self.RowNumber
		ret = None

		def changeRowNumCallback(row):
			# dCursorMixin is requesting a rowchange, which we must do here so that
			# child bizobjs get requeried. This is especially important (and only
			# currently happens) for virtual fields, in case they rely on values
			# gotten from children.
			self._moveToRowNum(row)
			for ch in self.__children:
				if ch.RowCount == 0:
					ch.requery()

		if _forceNoCallback:
			changeRowNumCallback = None

		if cursor is not None:
			try:
				ret = cursor.getFieldVal(fld, row, _rowChangeCallback=changeRowNumCallback)
			except dException.RowNotFoundException:
				return None

		if oldRow != self.RowNumber:
			self._moveToRowNum(oldRow)
		return ret


	def setFieldVal(self, fld, val, row=None):
		"""Set the value of the specified field in the current or specified row."""
		cursor = self._CurrentCursor
		if cursor is not None:
			try:
				ret = cursor.setFieldVal(fld, val, row)
			except (dException.NoRecordsException, dException.RowNotFoundException):
				ret = False
		return ret


	def setFieldVals(self, valDict=None, row=None, **kwargs):
		"""Allows you to set the value for multiple fields with one call by passing a dict
		containing the field names as keys, and the new values as values.
		"""
		if valDict is None:
			valDict = kwargs
		else:
			valDict.update(kwargs)
		cursor = self._CurrentCursor
		if cursor is not None:
			try:
				ret = cursor.setValuesByDict(valDict, row)
			except dException.NoRecordsException:
				ret = False
		return ret

	setValues = setFieldVals  ## deprecate setValues in future version


	_baseXML = """<?xml version="1.0" encoding="%s"?>
<dabocursor xmlns="http://www.dabodev.com"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.dabodev.com dabocursor.xsd"
xsi:noNamespaceSchemaLocation = "http://dabodev.com/schema/dabocursor.xsd">
	<cursor autopopulate="%s" keyfield="%s" table="%s">
%s
	</cursor>
</dabocursor>
"""
	_rowTemplate = """<row>
%s
</row>
"""
	_childTemplate = """
	<child table="%s">
%s
	</child>"""
	_childEmptyTemplate = """
	<child table="%s" />"""


	def dataToXML(self):
		"""Returns XML representing the data set. If there are child bizobjs,
		the data for the related child records will be nested inside of the
		parent record; this nesting can go as many levels deep as there are
		child/grandchild/etc. bizobjs.
		"""
		xml = self._dataToXML()
		return self._baseXML % (self.Encoding, self.AutoPopulatePK, self.KeyField,
				self.DataSource, xml)


	def _dataToXML(self, level=None, rows=None):
		self._xmlBody = ""
		if level is None:
			level = 0
		def addToBody(txt, lvl=None):
			if lvl:
				txt = "\n".join(["%s%s" % ("\t"*lvl, ln) for ln in txt.splitlines()])
				if txt and not txt.endswith("\n"):
					txt += "\n"
			self._xmlBody += txt
		if rows is None:
			self.scan(self._xmlForRow, level=level+1, callback=addToBody)
		else:
			self.scanRows(self._xmlForRow, self.RowNumber, level=level+1,
					callback=addToBody)
		return self._xmlBody


	def _xmlForRow(self, level, callback):
		"""Returns the xml for the given row to the specified
		callback function.
		"""
		xml = self._CurrentCursor._xmlForRow()
		kidXML = ""
		for kid in self.__children:
			kidstuff = kid._dataToXML(level=level+1)
			if kidstuff:
				kidXML += self._childTemplate % (kid.DataSource, kidstuff)
			else:
				kidXML += self._childEmptyTemplate % kid.DataSource
		callback(self._rowTemplate % ("%s%s" % (xml, kidXML)), level)


	def getDataSet(self, flds=(), rowStart=0, rows=None, returnInternals=False):
		""" Get the entire data set encapsulated in a list.

		If the optional	'flds' parameter is given, the result set will be filtered
		to only include the specified fields. rowStart specifies the starting row
		to include, and rows is the number of rows to return.
		"""
		ret = None
		cc = self._CurrentCursor
		if cc is not None:
			ret = self._CurrentCursor.getDataSet(flds, rowStart, rows, returnInternals=returnInternals)
		return ret


	def appendDataSet(self, ds):
		"""Appends the rows in the passed dataset to this bizobj's dataset. No checking
		is done on the dataset columns to make sure that they are correct for this bizobj;
		it is the responsibility of the caller to make sure that they match. If invalid data is
		passed, a dException.FieldNotFoundException will be raised.
		"""
		self._CurrentCursor.appendDataSet(ds)


	def cloneRecord(self):
		"""Creates a copy of the current record and adds it to the dataset. The KeyField
		is not copied.
		"""
		cc = self._CurrentCursor
		# Cloning the record affects the cursor's _mementos dict. Save a copy
		# beforehand, and restore after the call to cloneRecord().
		memsave = cc._mementos.copy()
		cc.cloneRecord()
		cc._mementos = memsave
		self._onNew(setDefaults=False)


	def isRemote(self):
		"""Returns True/False, depending on whether this bizobj's connection
		is remote or not.
		"""
		return self._connection.isRemote()


	def getDataTypes(self):
		"""Returns the field type definitions as set in the cursor."""
		return self._CurrentCursor.getDataTypes()


	def _storeData(self, data, typs, stru):
		"""Accepts a data set and type defintion dict, and updates the cursor
		with these values.
		"""
		if stru:
			self.DataStructure = stru
		self._CurrentCursor._storeData(data, typs)


	def getDataStructure(self):
		""" Gets the structure of the DataSource table. Returns a list
		of 3-tuples, where the 3-tuple's elements are:
			0: the field name (string)
			1: the field type ('I', 'N', 'C', 'M', 'B', 'D', 'T')
			2: boolean specifying whether this is a pk field.
		"""
		return self._CurrentCursor.DataStructure


	def getDataStructureFromDescription(self):
		""" Gets the structure of the DataSource table. Returns a list
		of 3-tuples, where the 3-tuple's elements are:
			0: the field name (string)
			1: the field type ('I', 'N', 'C', 'M', 'B', 'D', 'T')
			2: boolean specifying whether this is a pk field.
		"""
		return self._CurrentCursor.getFieldInfoFromDescription()


	def getDataTypeForField(self, fld):
		"""Given a field name, returns its Python type, or None if no
		DataStructure information is available.
		"""
		ds = self.getDataStructure()
		if not ds:
			return None
		try:
			fldInfo = [rec[1] for rec in ds
					if rec[0] == fld][0]
		except IndexError:
			return None
			#raise ValueError(_("Field '%s' does not exist in the DataStructure") % fld)
		return dabo.db.getPythonType(fldInfo)


	def getParams(self):
		""" Return the parameters to send to the cursor's execute method.

		This is the place to define the parameters to be used to modify
		the SQL statement used to produce the record set. Normally if you have
		known parameters, you would simply call setParams(<param tuple>).
		But in cases where the parameter values need to be dynamically calculated,
		override this method in your subclass to determine the tuple to return.
		"""
		return self.__params


	def getChildren(self):
		""" Return a tuple of the child bizobjs."""
		ret = []
		for child in self.__children:
			ret.append(child)
		return tuple(ret)


	def getChildByDataSource(self, dataSource):
		""" Return a reference to the child bizobj with the passed dataSource."""
		ret = None
		for child in self.getChildren():
			if child.DataSource == dataSource:
				ret = child
				break
		return ret


	def escQuote(self, val):
		""" Escape special characters in SQL strings.

		Escapes any single quotes that could cause SQL syntax errors. Also
		escapes backslashes, since they have special meaning in SQL parsing.
		Finally, wraps the value in single quotes.
		"""
		return self._CurrentCursor.escQuote(val)


	def formatForQuery(self, val):
		""" Wrap up any value(int, long, string, date, date-time, decimal, none)
		for use to be in a query.
		"""
		return self._CurrentCursor.formatForQuery(val)


	def formatDateTime(self, val):
		""" Wrap a date or date-time value in the format
		required by the backend.
		"""
		return self._CurrentCursor.formatDateTime(val)


	def moveToRowNumber(self, rowNumber):
		""" Move to the specified row number."""
		self.RowNumber = rowNumber


	def getWordMatchFormat(self):
		"""Returns the backend's SQL format for creating queries that are based
		on matching words in a given column.
		"""
		return self._CurrentCursor.getWordMatchFormat()


	def oldVal(self, fieldName, row=None):
		"""Returns the value that was in the specified field when it was last fetched
		from the backend. Used to determine if the current value has been modified.
		"""
		return self._CurrentCursor.oldVal(fieldName, row)


	########## SQL Builder interface section ##############
	def addField(self, exp, alias=None):
		""" Add a field to the field clause."""
		return self._CurrentCursor.addField(exp, alias)
	def addFrom(self, exp, alias=None):
		""" Add a table to the sql statement. For joins, use
		the addJoin() method.
		"""
		return self._CurrentCursor.addFrom(exp, alias)
	def addJoin(self, tbl, exp, joinType=None):
		"""Add SQL JOIN clause.

		tbl: the name of the table to join with
		exp: the join expression
		joinType examples: "LEFT", "RIGHT", "INNER", "OUTER"
		"""
		return self._CurrentCursor.addJoin(tbl, exp, joinType)
	def addGroupBy(self, exp):
		"""Add an expression to the group-by clause."""
		return self._CurrentCursor.addGroupBy(exp)
	def addOrderBy(self, exp):
		"""Add an expression to the order-by clause."""
		return self._CurrentCursor.addOrderBy(exp)
	def addWhere(self, exp, comp="and"):
		"""Add a filter expression to the where clause."""
		return self._CurrentCursor.addWhere(exp, comp=comp)
	def getSQL(self):
		"""Returns the SQL statement currently set in the backend."""
		return self._CurrentCursor.getSQL()
	def setFieldClause(self, clause):
		"""Explicitly set the field clause. Replaces any existing field settings."""
		return self._CurrentCursor.setFieldClause(clause)
	def setFromClause(self, clause):
		"""Explicitly set the from clause. Replaces any existing from settings."""
		return self._CurrentCursor.setFromClause(clause)
	def setJoinClause(self, clause):
		"""Explicitly set the join clauses. Replaces any existing join settings."""
		return self._CurrentCursor.setJoinClause(clause)
	def setGroupByClause(self, clause):
		"""Explicitly set the group-by clause. Replaces any existing group-by settings."""
		return self._CurrentCursor.setGroupByClause(clause)
	def getLimitClause(self):
		"""Returns the current limit clause set in the backend."""
		return self._CurrentCursor.getLimitClause()
	def setLimitClause(self, clause):
		"""Explicitly set the limit clause. Replaces any existing limit settings."""
		return self._CurrentCursor.setLimitClause(clause)
	# For simplicity's sake, create aliases
	setLimit, getLimit = setLimitClause, getLimitClause
	def setOrderByClause(self, clause):
		"""Explicitly set the order-by clause. Replaces any existing order-by settings."""
		return self._CurrentCursor.setOrderByClause(clause)
	def setWhereClause(self, clause):
		"""Explicitly set the where clause. Replaces any existing where settings."""
		return self._CurrentCursor.setWhereClause(clause)
	def prepareWhere(self, clause):
		"""Calls the backend's pre-processing routine for improving efficiency
		of filter expressions. If the backend does not have this capability,
		nothing is done.
		"""
		return self._CurrentCursor.prepareWhere(clause)
	def getFieldClause(self):
		"""Returns the current field clause set in the backend."""
		return self._CurrentCursor.getFieldClause()
	def getFromClause(self):
		"""Returns the current from clause set in the backend."""
		return self._CurrentCursor.getFromClause()
	def getJoinClause(self):
		"""Returns the current join clause set in the backend."""
		return self._CurrentCursor.getJoinClause()
	def getWhereClause(self):
		"""Returns the current where clause set in the backend."""
		return self._CurrentCursor.getWhereClause()
	def getGroupByClause(self):
		"""Returns the current group-by clause set in the backend."""
		return self._CurrentCursor.getGroupByClause()
	def getOrderByClause(self):
		"""Returns the current order-by clause set in the backend."""
		return self._CurrentCursor.getOrderByClause()
	########## END - SQL Builder interface section ##############




	def _makeHookMethod(name, action,  mainDoc=None, additionalDoc=None):
		mode = name[:5]
		if mode == "befor":
			mode = "before"
		if mainDoc is None:
			mainDoc = "Hook method called %s %s." % (mode, action)
		if additionalDoc is None:
			if mode == "before":
				additionalDoc =  """Subclasses can put in additional code to run, and/or return a non-empty
string to signify that the action should not happen. The contents
of the string will be displayed to the user."""
			else:
				additionalDoc = ""

		def method(self):
			return ""
		method.__doc__ =  "%s\n\n%s" % (mainDoc, additionalDoc)
		method.func_name = name
		return method


	########## Pre-hook interface section ##############
	beforeNew = _makeHookMethod("beforeNew", "a new record is added")
	beforeDelete = _makeHookMethod("beforeDelete", "a record is deleted")
	beforeFirst = _makeHookMethod("beforeFirst", "navigating to the first record")
	beforePrior = _makeHookMethod("beforePrior", "navigating to the prior record")
	beforeNext = _makeHookMethod("beforeNext", "navigating to the next record")
	beforeFirst = _makeHookMethod("beforeFirst", "navigating to the next record")
	beforeLast = _makeHookMethod("beforeLast", "navigating to the last record")
	beforePointerMove = _makeHookMethod("beforePointerMove",
			"the record pointer moves")
	beforeDeleteAllChildren = _makeHookMethod("beforeDeleteAllChildren",
			"all child records are deleted")
	beforeSetRowNumber = _makeHookMethod("beforeSetRowNumber",
			"the RowNumber property is set")
	beforeSave = _makeHookMethod("beforeSave", "the changed records are saved.")
	beforeCancel = _makeHookMethod("beforeCancel",
			"the changed records are canceled.")
	beforeRequery = _makeHookMethod("beforeRequery", "the cursor is requeried")
	beforeChildRequery = _makeHookMethod("beforeChildRequery",
			"the child bizobjs are requeried")
	beforeCreateCursor = _makeHookMethod("beforeCreateCursor",
			"the underlying cursor object is created")


	########## Post-hook interface section ##############

	afterNew = _makeHookMethod("afterNew", "a new record is added",
			additionalDoc = \
"""Use this hook to change field values of newly added records. If
you change field values here, the memento system will catch it and
prompt you to save if needed later on. If you want to change field
values and not trigger the memento system, override onNew() instead.
""")
	afterDelete = _makeHookMethod("afterDelete", "a record is deleted")
	afterFirst = _makeHookMethod("afterFirst", "navigating to the first record")
	afterPrior = _makeHookMethod("afterPrior", "navigating to the prior record")
	afterNext = _makeHookMethod("afterNext", "navigating to the next record")
	afterFirst = _makeHookMethod("afterFirst", "navigating to the next record")
	afterLast = _makeHookMethod("afterLast", "navigating to the last record")
	afterPointerMove = _makeHookMethod("afterPointerMove",
			"the record pointer moves")
	afterDeleteAllChildren = _makeHookMethod("afterDeleteAllChildren",
			"all child records are deleted")
	afterSetRowNumber = _makeHookMethod("afterSetRowNumber",
			"the RowNumber property is set")
	afterSave = _makeHookMethod("afterSave", "the changed records are saved.")
	afterCancel = _makeHookMethod("afterCancel",
			"the changed records are canceled.")
	afterRequery = _makeHookMethod("afterRequery", "the cursor is requeried")
	afterChildRequery = _makeHookMethod("afterChildRequery",
			"the child bizobjs are requeried")
	afterChange = _makeHookMethod("afterChange", "a record is changed",
			additionalDoc=\
"""This hook will be called after a successful save() or delete(). Contrast
with the afterSave() hook which only gets called after a save(), and the
afterDelete() which is only called after a delete().""")


	def afterCreateCursor(self, crs):
		"""This hook is called after the underlying cursor object is created.
		The crs argument will contain the reference to the newly-created
		cursor."""


	def _syncWithCursors(self):
		"""Many bizobj properties need to be passed through to the cursors
		that provide it with data connectivity. This method ensures that all
		such cursors are in sync with the bizobj.
		"""
		for crs in self.__cursors.values():
			self._syncCursorProps(crs)


	def _syncCursorProps(self, crs):
		"""This method ensures that the passed cursor's properties
		are in sync with this bizobj.
		"""
		crs.KeyField = self._keyField
		crs.AutoPopulatePK = self._autoPopulatePK
		crs.AutoQuoteNames = self._autoQuoteNames
		if self._dataStructure is not None:
			crs.DataStructure = self._dataStructure
		if not self._RemoteProxy:
			crs.Table = self._dataSource
		else:
			crs._setTableForRemote(self._dataSource)
		crs.UserSQL = self._userSQL
		crs.VirtualFields = self._virtualFields
		crs.Encoding = self.Encoding
		crs.setNonUpdateFields(self._nonUpdateFields)


	def _cursorDictReference(self):
		"""In rare situations, bizobj subclasses may need to reference the
		internal __cursors attribute. This provides a way to do that, but
		it should be stressed that this is potentially dangerous and could
		lead to lost data if not handled correctly.
		"""
		return self.__cursors


	## Property getter/setter methods ##
	def _getAutoPopulatePK(self):
		try:
			return self._autoPopulatePK
		except AttributeError:
			return True

	def _setAutoPopulatePK(self, val):
		self._autoPopulatePK = bool(val)
		self._syncWithCursors()


	def _getAutoQuoteNames(self):
		return self._autoQuoteNames

	def _setAutoQuoteNames(self, val):
		self._autoQuoteNames = val
		self._syncWithCursors()


	def _getAutoSQL(self):
		try:
			return self._CurrentCursor.getSQL()
		except AttributeError:
			return None


	def _getCaption(self):
		try:
			return self._caption
		except AttributeError:
			return self.DataSource

	def _setCaption(self, val):
		self._caption = u"%s" % val


	def _getChildCacheInterval(self):
		return self._childCacheInterval

	def _setChildCacheInterval(self, val):
		self._childCacheInterval = val


	def _getCurrentSQL(self):
		return self._CurrentCursor.CurrentSQL


	def _getCurrentCursor(self):
		try:
			return self.__cursors[self.__currentCursorKey]
		except (KeyError, AttributeError):
			# There is no current cursor. Try creating one.
			self.createCursor()
			try:
				return self.__cursors[self.__currentCursorKey]
			except KeyError:
				return None

	def _setCurrentCursor(self, val):
		""" Sees if there is a cursor in the cursors dict with a key that matches
		the current parent key. If not, creates one.
		"""
		self.__currentCursorKey = val
		if not self.__cursors.has_key(val):
			self.createCursor()


	def _getDataSource(self):
		try:
			return self._dataSource
		except AttributeError:
			return ""

	def _setDataSource(self, val):
		self._dataSource = u"%s" % val
		self._syncWithCursors()


	def _getDataStructure(self):
		# We need to save the explicitly-assigned DataStructure here in the bizobj,
		# so that we are able to propagate it to any future-assigned child cursors.
		_ds = self._dataStructure
		if _ds is not None:
			return _ds
		return self._CurrentCursor.DataStructure

	def _setDataStructure(self, val):
		for key, cursor in self.__cursors.items():
			cursor.DataStructure = val
		self._dataStructure = val


	def _getDefaultValues(self):
		return self._defaultValues

	def _setDefaultValues(self, val):
		self._defaultValues = val


	def _getVirtualFields(self):
		# We need to save the explicitly-assigned VirtualFields here in the bizobj,
		# so that we are able to propagate it to any future-assigned child cursors.
		_df = getattr(self, "_virtualFields", None)
		if _df is not None:
			return _df
		return self._CurrentCursor.VirtualFields

	def _setVirtualFields(self, val):
		self._virtualFields = val
		self._syncWithCursors()


	def _getEncoding(self):
		try:
			ret = self._encoding
		except AttributeError:
			ret = None
			cursor = self._CurrentCursor
			if cursor is not None:
				ret = cursor.Encoding
			if ret is None:
				if self.Application:
					ret = self.Application.Encoding
				else:
					ret = dabo.defaultEncoding
			self._encoding = ret
		return ret

	def _setEncoding(self, val):
		self._encoding = val
		self._syncWithCursors()


	def _getFillLinkFromParent(self):
		try:
			return self._fillLinkFromParent
		except AttributeError:
			return False

	def _setFillLinkFromParent(self, val):
		self._fillLinkFromParent = bool(val)


	def _isAdding(self):
		return self._CurrentCursor.IsAdding


	def _getKeyField(self):
		try:
			return self._keyField
		except AttributeError:
			return ""

	def _setKeyField(self, val):
		self._keyField = val
		self._syncWithCursors()


	def _getLastSQL(self):
		try:
			v = self._CurrentCursor.LastSQL
		except AttributeError:
			v = None
		return v


	def _getLinkField(self):
		try:
			return self._linkField
		except AttributeError:
			return ""

	def _setLinkField(self, val):
		self._linkField = u"%s" % val


	def _getNewChildOnNew(self):
		try:
			return self._newChildOnNew
		except AttributeError:
			return False

	def _setNewChildOnNew(self, val):
		self._newChildOnNew = bool(val)


	def _getNewRecordOnNewParent(self):
		try:
			return self._newRecordOnNewParent
		except AttributeError:
			return False

	def _setNewRecordOnNewParent(self, val):
		self._newRecordOnNewParent = bool(val)


	def _getNonUpdateFields(self):
		return self._CurrentCursor.getNonUpdateFields()

	def _setNonUpdateFields(self, fldList=None):
		if fldList is None:
			fldList = []
		self._nonUpdateFields = fldList
		self._syncWithCursors()


	def _getParent(self):
		try:
			return self._parent
		except AttributeError:
			return None

	def _setParent(self, val):
		if isinstance(val, dBizobj):
			self._parent = val
		else:
			raise TypeError(_("Parent must descend from dBizobj"))


	def _getParentLinkField(self):
		try:
			return self._parentLinkField
		except AttributeError:
			return ""

	def _setParentLinkField(self, val):
		self._parentLinkField = u"%s" % val


	def _getRecord(self):
		return self._CurrentCursor.Record


	def _getRemoteProxy(self):
		if self.isRemote():
			try:
				return self._remoteProxy
			except AttributeError:
				self._remoteProxy = RemoteConnector(self)
				return self._remoteProxy
		else:
			return None


	def _getRequeryChildOnSave(self):
		try:
			return self._requeryChildOnSave
		except AttributeError:
			return False

	def _setRequeryChildOnSave(self, val):
		self._requeryChildOnSave = bool(val)


	def _getRequeryOnLoad(self):
		try:
			ret = self._requeryOnLoad
		except AttributeError:
			ret = False
		return ret

	def _setRequeryOnLoad(self, val):
		self._requeryOnLoad = bool(val)


	def _getRestorePositionOnRequery(self):
		try:
			return self._restorePositionOnRequery
		except AttributeError:
			return True

	def _setRestorePositionOnRequery(self, val):
		self._restorePositionOnRequery = bool(val)


	def _getRequeryWithParent(self):
		v = getattr(self, "_requeryWithParent", None)
		if v is None:
			v = self._requeryWithParent = True
		return v

	def _setRequeryWithParent(self, val):
		self._requeryWithParent = bool(val)


	def _getRowCount(self):
		try:
			ret = self._CurrentCursor.RowCount
		except AttributeError:
			ret = None
		return ret


	def _getRowNumber(self):
		try:
			ret = self._CurrentCursor.RowNumber
		except AttributeError:
			ret = None
		return ret

	def _setRowNumber(self, rownum):
		errMsg = self.beforeSetRowNumber()
		if not errMsg:
			errMsg = self.beforePointerMove()
		if errMsg:
			raise dException.BusinessRuleViolation(errMsg)
		self._moveToRowNum(rownum)
		self.requeryAllChildren()
		self.afterPointerMove()
		self.afterSetRowNumber()


	def _getSaveNewUnchanged(self):
		try:
			ret = self._saveNewUnchanged
		except AttributeError:
			ret = self._saveNewUnchanged = False
		return ret

	def _setSaveNewUnchanged(self, val):
		self._saveNewUnchanged = val


	def _getScanRestorePosition(self):
		return self._scanRestorePosition

	def _setScanRestorePosition(self, val):
		self._scanRestorePosition = val


	def _getScanRequeryChildren(self):
		return self._scanRequeryChildren

	def _setScanRequeryChildren(self, val):
		self._scanRequeryChildren = val


	def _getScanReverse(self):
		return self._scanReverse

	def _setScanReverse(self, val):
		self._scanReverse = val


	def _getSQL(self):
		warnings.warn(_("""This property is deprecated, and will be removed in the next version
of the framework. Use the 'UserSQL' property instead."""), DeprecationWarning, 1)
		return self.UserSQL

	def _setSQL(self, val):
		warnings.warn(_("""This property is deprecated, and will be removed in the next version
of the framework. Use the 'UserSQL' property instead."""), DeprecationWarning, 1)
		self.UserSQL = val


	def _getSqlMgr(self):
		if self._sqlMgrCursor is None:
			cursorClass = self._getCursorClass(self.dCursorMixinClass,
					self.dbapiCursorClass)
			cf = self._cursorFactory
			crs = self._sqlMgrCursor = cf.getCursor(cursorClass)
			crs.setCursorFactory(cf.getCursor, cursorClass)
			crs.KeyField = self.KeyField
			crs.Table = self.DataSource
			crs.AutoPopulatePK = self.AutoPopulatePK
			crs.AutoQuoteNames = self.AutoQuoteNames
			crs.BackendObject = cf.getBackendObject()
		return self._sqlMgrCursor


	def _getUserSQL(self):
		return self._userSQL

	def _setUserSQL(self, val):
		self._CurrentCursor.UserSQL = self._userSQL = val



	### -------------- Property Definitions ------------------  ##
	AutoPopulatePK = property(_getAutoPopulatePK, _setAutoPopulatePK, None,
			_("Determines if we are using a table that auto-generates its PKs. (bool)"))

	AutoQuoteNames = property(_getAutoQuoteNames, _setAutoQuoteNames, None,
			_("""When True (default), table and column names are enclosed with
			quotes during SQL creation in the cursor.  (bool)"""))

	AutoSQL = property(_getAutoSQL, None, None,
			_("Returns the SQL statement automatically generated by the sql manager."))

	Caption = property(_getCaption, _setCaption, None,
			_("The friendly title of the cursor, used in messages to the end user. (str)"))

	ChildCacheInterval = property(_getChildCacheInterval, _setChildCacheInterval, None,
			_("""If this is a child bizobj, this represents the length of time in seconds that a
			subsequent requery request will be ignored.  (int)"""))

	CurrentSQL = property(_getCurrentSQL, None, None,
			_("Returns the current SQL that will be run, which is one of UserSQL or AutoSQL."))

	_CurrentCursor = property(_getCurrentCursor, _setCurrentCursor, None,
			_("The cursor object for the currently selected key value. (dCursorMixin child)"))

	DataSource = property(_getDataSource, _setDataSource, None,
			_("The title of the cursor. Used in resolving DataSource references. (str)"))

	DataStructure = property(_getDataStructure, _setDataStructure, None,
			_("""Returns the structure of the cursor in a tuple of 6-tuples.

				0: field alias (str)
				1: data type code (str)
				2: pk field (bool)
				3: table name (str)
				4: field name (str)
				5: field scale (int or None)

				This information will try to come from a few places, in order:
				1) The explicitly-set DataStructure property
				2) The backend table method"""))

	DefaultValues = property(_getDefaultValues, _setDefaultValues, None,
			_("""A dictionary specifying default values for fields when a new record is added.

			The values of the dictionary can be literal (must match the field type), or
			they can be a function object which will be called when the new record is added
			to the bizobj."""))

	Encoding = property(_getEncoding, _setEncoding, None,
			_("Name of encoding to use for unicode  (str)") )

	FillLinkFromParent = property(_getFillLinkFromParent, _setFillLinkFromParent, None,
			_("""In the onNew() method, do we fill in the foreign key field specified by the
			LinkField property with the value returned by calling the bizobj's 	getParentPK()
			method? (bool)"""))

	IsAdding = property(_isAdding, None, None,
			_("Returns True if the current record is new and unsaved."))

	KeyField = property(_getKeyField, _setKeyField, None,
			_("""Name of field that is the PK. If multiple fields make up the key,
			separate the fields with commas. (str)"""))

	LastSQL = property(_getLastSQL, None, None,
			_("Returns the last executed SQL statement."))

	LinkField = property(_getLinkField, _setLinkField, None,
			_("Name of the field that is the foreign key back to the parent. (str)"))

	NewChildOnNew = property(_getNewChildOnNew, _setNewChildOnNew, None,
			_("Should new child records be added when a new parent record is added? (bool)"))

	NewRecordOnNewParent = property(_getNewRecordOnNewParent, _setNewRecordOnNewParent, None,
			_("If this bizobj's parent has NewChildOnNew==True, do we create a record here? (bool)"))

	NonUpdateFields = property(_getNonUpdateFields, _setNonUpdateFields, None,
			_("Fields in the cursor to be ignored during updates"))

	Parent = property(_getParent, _setParent, None,
			_("Reference to the parent bizobj to this one. (dBizobj)"))

	ParentLinkField = property(_getParentLinkField, _setParentLinkField, None,
			_("""Name of the field in the parent table that is used to determine child
			records. If empty, it is assumed that the parent's PK is used  (str)"""))

	Record = property(_getRecord, None, None,
			_("""Represents a record in the data set. You can address individual
			columns by referring to 'self.Record.fieldName' (read-only) (no type)"""))

	_RemoteProxy = property(_getRemoteProxy, None, None,
			_("""If this bizobj is being run remotely, returns a reference to the RemoteConnector
			object that will handle communication with the server.  (read-only) (RemoteConnector)"""))

	RequeryChildOnSave = property(_getRequeryChildOnSave, _setRequeryChildOnSave, None,
			_("Do we requery child bizobjs after a save()? (bool)"))

	RequeryOnLoad = property(_getRequeryOnLoad, _setRequeryOnLoad, None,
			_("""When True, the cursor object runs its query immediately. This
			is useful for lookup tables or fixed-size (small) tables. (bool)"""))

	RequeryWithParent = property(_getRequeryWithParent, _setRequeryWithParent, None,
			_("""Specifies whether a child bizobj gets requeried automatically.

				When True (the default) moving the record pointer or requerying the
				parent bizobj will result in the child bizobj's getting requeried
				as well. When False, user code will have to manually call
				child.requery() at the appropriate time.
				"""))

	RestorePositionOnRequery = property(_getRestorePositionOnRequery, _setRestorePositionOnRequery, None,
			_("After a requery, do we try to restore the record position to the same PK?"))

	RowCount = property(_getRowCount, None, None,
			_("""The number of records in the cursor's data set. It will be -1 if the
			cursor hasn't run any successful queries yet. (int)"""))

	RowNumber = property(_getRowNumber, _setRowNumber, None,
			_("The current position of the record pointer in the result set. (int)"))

	SaveNewUnchanged = property(_getSaveNewUnchanged, _setSaveNewUnchanged, None,
			_("""Normally new, unmodified records are not saved. If you need
			this behavior, set this to True.  (bool)"""))

	ScanRestorePosition = property(_getScanRestorePosition, _setScanRestorePosition, None,
			_("""After running a scan, do we attempt to restore the record position to
			where it was before the scan (True, default), or do we leave the pointer
			at the end of the recordset (False). (bool)"""))

	ScanRequeryChildren = property(_getScanRequeryChildren, _setScanRequeryChildren, None,
			_("""When calling the scan() function, this property determines if we 
			requery any child bizobjs for each row in this bizobj. The default is False,
			as this has the potential to cause performance issues.  (bool)"""))

	ScanReverse = property(_getScanReverse, _setScanReverse, None,
			_("""Do we scan the records in reverse order? (Default: False) (bool)"""))

	SQL = property(_getSQL, _setSQL, None,
			_("DEPRECATED. Equivalent to UserSQL. (str)"))

	SqlManager = property(_getSqlMgr, None, None,
			_("Reference to the cursor that handles SQL Builder information (cursor)") )

	UserSQL = property(_getUserSQL, _setUserSQL, None,
			_("SQL statement to run. If set, the automatic SQL builder will not be used."))

	VirtualFields = property(_getVirtualFields, _setVirtualFields, None,
			_("""A dictionary mapping virtual_field_name to function to call.

			The specified function will be called when getFieldVal() is called on
			the specified virtual field name."""))



class _bizIterator(object):
	def __init__(self, obj):
		self.obj = obj
		self.__firstpass = True
		self.__nextfunc = self._next


	def reverse(self):
		"""Configures the iterator to process the records in reverse order.
		Must be called before beginning the iteration.
		"""
		if not self.__firstpass:
			raise RuntimeError(_("Cannot reverse in the middle of iteration."))
		self.__nextfunc = self._prior
		return self


	def _prior(self):
		if self.__firstpass:
			try:
				self.obj.last()
				self.__firstpass = False
			except dException.NoRecordsException:
				raise StopIteration
		else:
			try:
				self.obj.prior()
			except dException.BeginningOfFileException:
				raise StopIteration
		return self.obj.RowNumber


	def _next(self):
		if self.__firstpass:
			try:
				self.obj.first()
				self.__firstpass = False
			except dException.NoRecordsException:
				raise StopIteration
		else:
			try:
				self.obj.next()
			except dException.EndOfFileException:
				raise StopIteration
		return self.obj.RowNumber


	def next(self):
		"""Moves the record pointer to the next record."""
		return self.__nextfunc()


	def __iter__(self):
		self.__firstpass = True
		return self
