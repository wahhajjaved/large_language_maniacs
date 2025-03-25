# -*- coding: utf-8 -*-
# dabo/db/dCursorMixin

import datetime
import time
import re
from decimal import Decimal
import dabo
import dabo.dConstants as kons
from dabo.dLocalize import _
import dabo.dException as dException
from dabo.dObject import dObject
from dNoEscQuoteStr import dNoEscQuoteStr
from dabo.db.dDataSet import dDataSet
from dabo.lib import dates
from dabo.lib.utils import noneSortKey, caseInsensitiveSortKey


class dCursorMixin(dObject):
	"""Dabo's cursor class, representing the lowest tier."""
	_call_initProperties = False
	# Make this a class attribute, so that it is shared among all instances
	_fieldStructure = {}

	def __init__(self, sql="", *args, **kwargs):
		self._convertStrToUnicode = True
		self._initProperties()
		if sql and isinstance(sql, basestring) and len(sql) > 0:
			self.UserSQL = sql

		#self.super()
		#super(dCursorMixin, self).__init__()
		## pkm: Neither of the above are correct. We need to explicitly
		##      call dObject's __init__, otherwise the cursor object with
		##      which we are mixed-in will take the __init__.
		dObject.__init__(self, *args, **kwargs)

		# Just in case this is used outside of the context of a bizobj
		if not hasattr(self, "superCursor") or self.superCursor is None:
			myBases = self.__class__.__bases__
			for base in myBases:
				# Find the first base class that doesn't have the 'autoPopulatePK'
				# attribute. Designate that class as the superCursor class.
				if hasattr(base, "fetchall"):
					self.superCursor = base
					break


	def _initProperties(self):
		# Holds the dict used for adding new blank records
		self._blank = {}
		# Flag for indicating NULL default values were set
		self._nullDefaults = False
		# Writable version of the dbapi 'description' attribute
		self.descriptionClean = None
		# Last executed sql params
		self.lastParams = None
		# Column on which the result set is sorted
		self.sortColumn = ""
		# Order of the sorting. Should be either ASC, DESC or empty for no sort
		self.sortOrder = ""
		# Is the sort case-sensitive?
		self.sortCase = True
		# Holds the last SQL run in a requery() call.
		self._lastSQL = ""
		# Hold the time that this cursor was last requeried.
		self.lastRequeryTime = 0
		# These are used to determine if the field list of successive select statements
		# are identical.
		self.__lastExecute = ""
		self.__lastFieldList = ""
		self._whitespacePat = re.compile(r"(\s+)")
		self._selectStatementPat = re.compile(r"\bselect\b(.+)\bfrom\b", re.I | re.M | re.S)
		# Holds the keys in the original, unsorted order for unsorting the dataset
		self.__unsortedRows = []
		# Holds the name of fields to be skipped when updating the backend, such
		# as calculated or derived fields, or fields that are otherwise not to be updated.
		self.__nonUpdateFields = None
		# User-editable list of non-updated fields
		self.nonUpdateFields = []
		# Flag that is set when the user explicitly sets the Key Field
		self._keyFieldSet = False
		# Cursor that manages this cursor's SQL. Default to self;
		# in some cases, such as a single bizobj managing several cursors,
		# it will be a separate object.
		self.sqlManager = self
		# Attribute that holds the data of the cursor
		self._records = dDataSet()
		# Attribute that holds the current row number
		self.__rownumber = -1
		# Data structure info
		self._dataStructure = None
		self._table = ""
		self._keyField = ""
		self._userSQL = None
		self._virtualFields = {}

		self._autoPopulatePK = True
		self._autoQuoteNames = True

		self.__tmpPK = -1		# temp PK value for new records.
		# Holds the data types for each field
		self._types = {}

		# Holds reference to auxiliary cursor that handles queries that
		# are not supposed to affect the record set.
		self.__auxCursor = None
		# Marks the cursor as an auxiliary cursor
		self._isAuxiliary = False

		# Reference to the object with backend-specific behaviors
		self.__backend = None

		# Reference to the bizobj that 'owns' this cursor, if any,
		self._bizobj = None

		# set properties for the SQL Builder functions
		self.clearSQL()
		self.hasSqlBuilder = True

		# props for building the auxiliary cursor
		self._cursorFactoryFunc = None
		self._cursorFactoryClass = None

		# mementos and new records, keyed on record object ids:
		self._mementos = {}
		self._newRecords = {}

		# Flag preference cursors so that they don't fill up the logs
		self._isPrefCursor = False

		self.initProperties()


	def setCursorFactory(self, func, cls):
		self._cursorFactoryFunc = func
		self._cursorFactoryClass = cls


	def clearSQL(self):
		self._fieldClause = ""
		self._fromClause = ""
		self._joinClause = ""
		self._whereClause = ""
		self._childFilterClause = ""
		self._groupByClause = ""
		self._orderByClause = ""
		self._limitClause = ""
		self._defaultLimit = 1000


	def getSortColumn(self):
		return self.sortColumn


	def getSortOrder(self):
		return self.sortOrder


	def getSortCase(self):
		return self.sortCase


	def pkExpression(self, rec=None):
		"""Returns the PK expression for the passed record."""
		if rec is None:
			try:
				rec = self._records[self.RowNumber]
			except IndexError:
				rec = {}
		if isinstance(self.KeyField, tuple):
			if rec:
				pk = tuple([rec[kk] for kk in self.KeyField])
			else:
				pk = tuple([None for kk in self.KeyField])
		else:
			pk = rec.get(self.KeyField, None)
		return pk


	def pkFieldExpression(self):
		"""Returns the field or comma-separated list of field names
		for the PK for this cursor's table.
		"""
		if isinstance(self.KeyField, tuple):
			pkField = ", ".join([kk for kk in self.KeyField])
		else:
			pkField = self.KeyField
		return pkField


	def _correctFieldType(self, field_val, field_name, _newQuery=False):
		"""Correct the type of the passed field_val, based on self.DataStructure.

		This is called by self.execute(), and contains code to convert all strings
		to unicode, as well as to correct any datatypes that don't match what
		self.DataStructure reports. The latter can happen with SQLite, for example,
		which only knows about a quite limited number of types.
		"""
		ret = field_val
		if _newQuery:
			pythonType = self._types.get(field_name, type(field_val))
			if pythonType is None:
				pythonType = self._types[field_name] = dabo.db.getDataType(type(field_val))

			if pythonType is None or isinstance(field_val, pythonType):
				# No conversion needed.
				return ret

			if pythonType in (unicode,):
				# Unicode conversion happens below.
				pass
			elif field_val is None:
				# Fields of any type can be None (NULL).
				return field_val
			elif pythonType in (datetime.datetime, ) and isinstance(field_val, basestring):
				ret = dates.getDateTimeFromString(field_val)
				if ret is None:
					ret = field_val
				else:
					return ret
			elif pythonType in (datetime.date,) and isinstance(field_val, basestring):
				ret = dates.getDateFromString(field_val)
				if ret is None:
					ret = field_val
				else:
					return ret
			elif pythonType in (Decimal,):
				ds = self.DataStructure
				ret = None
				_field_val = field_val
				if type(field_val) in (float,):
					# Can't convert to decimal directly from float
					_field_val = str(_field_val)
				# Need to convert to the correct scale:
				scale = None
				for s in ds:
					if s[0] == field_name:
						if len(s) > 5:
							scale = s[5]
				if scale is None:
					scale = 2
				return Decimal(_field_val).quantize(Decimal("0.%s" % (scale * "0",)))
			else:
				try:
					return pythonType(field_val)
				except Exception, e:
					dabo.infoLog.write(_("_correctFieldType() failed for field: '%s'; value: '%s'; type: '%s'") %
							(field_name, field_val, type(field_val)))

		# Do the unicode conversion last:
		if isinstance(field_val, str) and self._convertStrToUnicode:
			try:
				decoded = field_val.decode(self.Encoding)
				return decoded
			except UnicodeDecodeError, e:
				# Try some common encodings:
				ok = False
				for enc in ("utf-8", "latin-1", "iso-8859-1"):
					if enc != self.Encoding:
						try:
							ret = field_val.decode(enc)
							ok = True
						except UnicodeDecodeError:
							continue
						if ok:
							# change self.Encoding and log the message
							self.Encoding = enc
							dabo.errorLog.write(_("Field %(fname)s: Incorrect unicode encoding set; using '%(enc)s' instead")
								% {'fname':field_name, 'enc':enc} )
							return ret
				else:
					raise e
# 		elif isinstance(field_val, array.array):
# 			# Usually blob data
# 			ret = field_val.tostring()

			dabo.errorLog.write(_("%s couldn't be converted to %s (field %s)")
					% (repr(field_val), pythonType, field_name))
		return ret


	def execute(self, sql, params=None, _newQuery=False, errorClass=None):
		"""Execute the sql, and populate the DataSet if it is a select statement."""
		# The idea here is to let the super class do the actual work in
		# retrieving the data. However, many cursor classes can only return
		# row information as a list, not as a dictionary. This method will
		# detect that, and convert the results to a dictionary.
		if isinstance(sql, unicode):
			sql = sql.encode(self.Encoding)
		# Some backends, notably Firebird, require that fields be specially marked.
		sql = self.processFields(sql)

		try:
			if params:
				res = self.superCursor.execute(self, sql, params)
				if not self.IsPrefCursor:
					dabo.dbActivityLog.write("SQL: %s, PARAMS: %s" % (
							sql.decode(self.Encoding).replace("\n", " "),
							', '.join("%s" % p for p in params)))
			else:
				res = self.superCursor.execute(self, sql)
				if not self.IsPrefCursor:
					dabo.dbActivityLog.write("SQL: %s" % (
							sql.decode(self.Encoding).replace("\n", " "),))
		except Exception, e:
			# There can be cases where errors are expected. In those cases, the
			# calling routine will pass the class of the expected error, and will
			# handle it appropriately.
			if errorClass is not None and isinstance(e, errorClass):
				raise e
			if params:
				dabo.dbActivityLog.write("FAILED SQL: %s, PARAMS: %s" % (
						sql.decode(self.Encoding).replace("\n", " "),
						', '.join("%s" % p for p in params)))
			else:
				dabo.dbActivityLog.write("FAILED SQL: %s" % (
						sql.decode(self.Encoding).replace("\n", " "),))
			# Database errors need to be decoded from database encoding.
			try:
				errMsg = str(e).decode(self.Encoding)
			except UnicodeError:
				errMsg = unicode(e)
			# If this is due to a broken connection, let the user know.
			# Different backends have different messages, but they
			# should all contain the string 'connect' in them.
			if "connect" in errMsg.lower():
				raise dException.ConnectionLostException(errMsg)
			elif "access" in errMsg.lower():
				raise dException.DBNoAccessException(errMsg)
			else:
				raise dException.DBQueryException(errMsg, sql)

		# Some backend programs do odd things to the description
		# This allows each backend to handle these quirks individually.
		self.BackendObject.massageDescription(self)

		if self._newStructure(sql):
			self._storeFieldTypes()

		if sql.split(None, 1)[0].lower() not in ("select", "pragma"):
			# No need to massage the data for DML commands
			self._records = dDataSet(tuple())
			return res

		try:
			_records = self.fetchall()
		except Exception, e:
			_records = dabo.db.dDataSet()
			# Database errors need to be decoded from database encoding.
			try:
				errMsg = str(e).decode(self.Encoding)
			except UnicodeError:
				errMsg = unicode(e)
			dabo.errorLog.write("Error fetching records: %s" % errMsg)

		if _records and not self.BackendObject._alreadyCorrectedFieldTypes:
			if isinstance(_records[0], (tuple, list)):
				# Need to convert each row to a Dict, since the backend didn't do it.
				tmpRows = []
				fldNames = [f[0] for f in self.FieldDescription]
				for row in _records:
					dic = {}
					for idx, fldName in enumerate(fldNames):
						dic[fldName] = self._correctFieldType(field_val=row[idx],
								field_name=fldName, _newQuery=_newQuery)
					tmpRows.append(dic)
				_records = tmpRows
			else:
				# Already a DictCursor, but we still need to correct the field types.
				for row in _records:
					for fld, val in row.items():
						row[fld] = self._correctFieldType(field_val=val,
								field_name=fld, _newQuery=_newQuery)

		self._records = dDataSet(_records)
		# This will handle bounds issues
		self.RowNumber = self.RowNumber
		return res


	def executeSafe(self, sql, params=None):
		"""Execute the passed SQL using an auxiliary cursor.
		This is considered 'safe', because it won't harm the contents
		of the main cursor. Returns the temp cursor.
		"""
		ac = self.AuxCursor
		self._syncAuxProperties()
		ac.execute(sql, params)
		return ac


	def _newStructure(self, sql):
		"""Attempts to parse the SQL to determine if the fields being selected will require
		a new call to set the structure. Non-select statements likewise will return False.
		"""
		if self._isAuxiliary:
			return False
		if sql == self.__lastExecute:
			return False
		# See if it's a select statement
		mtch = self._selectStatementPat.search(sql)
		if not mtch:
			return False
		# Normalize white space
		fldlist = self._whitespacePat.sub(" ", mtch.groups()[0]).strip()
		if self.__lastFieldList == fldlist:
			return False
		else:
			self.__lastFieldList = fldlist
			return True


	def _syncAuxProperties(self):
		"""Make sure that the auxiliary cursor has the same property
		settings as the main cursor.
		"""
		if self._isAuxiliary:
			# Redundant!
			return
		ac = self.AuxCursor
		ac.AutoPopulatePK = self.AutoPopulatePK
		ac.AutoQuoteNames = self.AutoQuoteNames
		ac.DataStructure = self.DataStructure
		ac.IsPrefCursor = self.IsPrefCursor
		ac.KeyField = self.KeyField
		ac.Table = self.Table


	def requery(self, params=None):
		currSQL = self.CurrentSQL
		newQuery = (self._lastSQL != currSQL)
		self._lastSQL = currSQL
		self.lastParams = params
		self._savedStructureDescription = []

		self.execute(currSQL, params, _newQuery=newQuery)

		# clear mementos and new record flags:
		self._mementos = {}
		self._newRecords = {}
		# Record the requery time for caching purposes
		self.lastRequeryTime = time.time()

		if newQuery:
			# Check for any derived fields that should not be included in
			# any updates.
			self.__setNonUpdateFields()

		# Clear the unsorted list, and then apply the current sort
		self.__unsortedRows = []
		if self.sortColumn:
			try:
				self.sort(self.sortColumn, self.sortOrder)
			except dException.NoRecordsException:
				# No big deal
				pass
		return True


	def _storeFieldTypes(self, target=None):
		"""Stores the data type for each column in the result set."""
		if target is None:
			target = self
		target._types = {}
		for field in self.DataStructure:
			field_alias, field_type = field[0], field[1]
			target._types[field_alias] = dabo.db.getPythonType(field_type)


	def sort(self, col, ord=None, caseSensitive=True):
		""" Sort the result set on the specified column in the specified order. If the sort
		direction is not specified, default to ascending order. If 'cycle' is specified as the
		direction, use the next ordering in the list [None, 'ASC', 'DESC']. The possible
		values for 'ord' are:
			None
			"" (i.e., an empty string)
			ASC
			DESC
			CYCLE
		Only the first three characters are significant; case is ignored.
		"""
		currCol = self.sortColumn
		currOrd = self.sortOrder
		currCase = self.sortCase
		if ord is None:
			ord = "ASC"
		elif ord == "":
			ord = None
		if ord[:3].upper() == "CYC":
			ord = {"ASC": "DESC", "DES": None, None: "ASC"}[currOrd]
			col = currCol

		# Make sure that the specified column is a column in the result set
		if not [True for t in self.DataStructure if t[0] == col]  and col not in self.VirtualFields:
			raise dException.dException(
					_("Invalid column specified for sort: ") + col)

		newCol = col
		if col == currCol:
			# Not changing the column; most likely they are flipping
			# the sort order.
			if (ord is None) or not ord:
				# They didn't specify the sort order. Cycle through the sort orders
				if currOrd == "ASC":
					newOrd = "DESC"
				elif currOrd == "DESC":
					newOrd = ""
				else:
					newOrd = "ASC"
			else:
				if ord.upper() in ("ASC", "DESC", ""):
					newOrd = ord.upper()
				else:
					raise dException.dException(
							_("Invalid Sort direction specified: ") + ord)

		else:
			# Different column specified.
			if (ord is None) or not ord:
				# Start in ASC order
				newOrd = "ASC"
			else:
				if ord.upper() in ("ASC", "DESC", ""):
					newOrd = ord.upper()
				else:
					raise dException.dException(
							_("Invalid Sort direction specified: ") + ord)

		self.__sortRows(newCol, newOrd, caseSensitive)
		# Save the current sort values
		self.sortColumn = newCol
		self.sortOrder = newOrd
		self.sortCase = caseSensitive


	def __sortRows(self, col, ord, caseSensitive):
		""" Sort the rows of the cursor.

		At this point, we know we have a valid column and order. We need to
		preserve the unsorted order if we haven't done that yet; then we sort
		the data according to the request.
		"""
		kf = self.KeyField
		if not kf or not self.RowCount:
			return

		if not self.__unsortedRows:
			# Record the PK values
			for row in self._records:
				if self._compoundKey:
					key = tuple([row[k] for k in kf])
					self.__unsortedRows.append(key)
				else:
					self.__unsortedRows.append(row[kf])

		# First, preserve the PK of the current row so that we can reset
		# the RowNumber property to point to the same row in the new order.
		try:
			if self._compoundKey:
				currRow = self._records[self.RowNumber]
				currRowKey = tuple([currRow[k] for k in kf])
			else:
				currRowKey = self._records[self.RowNumber][kf]
		except IndexError:
			# Row no longer exists, such as after a Requery that returns
			# fewer rows.
			currRowKey = None
		# Create the list to hold the rows for sorting
		sortList = []
		if not ord:
			# Restore the rows to their unsorted order
			for row in self._records:
				if self._compoundKey:
					key = tuple([row[k] for k in kf])
					sortList.append([self.__unsortedRows.index(key), row])
				else:
					sortList.append([self.__unsortedRows.index(row[kf]), row])
		else:
			for row, rec in enumerate(self._records):
				sortList.append([self.getFieldVal(col, row), rec])
		# At this point we have a list consisting of lists. Each of these member
		# lists contain the sort value in the zeroth element, and the row as
		# the first element.
		# First, see if we are comparing strings
		compString = isinstance(sortList[0][0], basestring)

		if compString and not caseSensitive:
			sortKey = caseInsensitiveSortKey
		else:
			sortKey = noneSortKey
		sortList.sort(key=sortKey, reverse=(ord == "DESC"))

		# Extract the rows into a new list, then convert them back to the _records tuple
		newRows = [elem[1] for elem in sortList]
		self._records = dDataSet(newRows)

		# restore the RowNumber
		if currRowKey:
			for ii in range(0, self.RowCount):
				row = self._records[ii]
				if self._compoundKey:
					key = tuple([row[k] for k in kf])
					found = (key == currRowKey)
				else:
					found = row[kf] == currRowKey
				if found:
					self.RowNumber = ii
					break
		else:
			self.RowNumber = 0


	def cursorToXML(self):
		""" Returns an XML string containing the information necessary to
		re-create this cursor.
		"""
		base = """<?xml version="1.0" encoding="%s"?>
<dabocursor xmlns="http://www.dabodev.com"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.dabodev.com dabocursor.xsd"
xsi:noNamespaceSchemaLocation = "http://dabodev.com/schema/dabocursor.xsd">
	<cursor autopopulate="%s" keyfield="%s" table="%s">
%s
	</cursor>
</dabocursor>"""

		rowTemplate = """		<row>
%s
		</row>
"""

		colTemplate = """			<column name="%s" type="%s">%s</column>"""

		rowXML = ""
		for rec in self._records:
			recInfo = [ colTemplate % (k, self.getType(v), self.escape(v))
					for k,v in rec.items() ]
			rowXML += rowTemplate % "\n".join(recInfo)
		return base % (self.Encoding, self.AutoPopulatePK, self.KeyField,
				self.Table, rowXML)


	def _xmlForRow(self, row=None):
		"""Returns the XML for the specified row; if no row is specified,
		the current row is used.
		"""
		colTemplate = """	<column name="%s" type="%s">%s</column>"""
		recInfo = [ colTemplate % (k, self.getType(v), self.escape(v))
				for k,v in self._records[self.RowNumber].items() ]
		return "\n".join(recInfo)


	def getType(self, val):
		try:
			ret = re.search("type '([^']+)'", str(type(val))).groups()[0]
		except IndexError:
			ret = "-unknown-"
		return ret


	def escape(self, val):
		""" Provides the proper escaping of values in XML output """
		ret = val
		if isinstance(val, basestring):
			if ("\n" in val) or ("<" in val) or ("&" in val):
				ret = "<![CDATA[%s]]>" % val.encode(self.Encoding)
		return ret


	def setNonUpdateFields(self, fldList=None):
		if fldList is None:
			fldList = []
		self.nonUpdateFields = fldList


	def getNonUpdateFields(self):
		if self.__nonUpdateFields is None:
			# They haven't been set yet
			self.__setNonUpdateFields()
		return list(set(self.nonUpdateFields + self.__nonUpdateFields))


	def __setNonUpdateFields(self, nonUp=None):
		"""Automatically set the non-update fields."""
		if nonUp is not None:
			# This is being called back by the BackendObject
			self.__nonUpdateFields = nonUp
			return
		dataStructure = getattr(self, "_dataStructure", None)
		if dataStructure is not None:
			# Use the explicitly-set DataStructure to find the NonUpdateFields.
			self.__nonUpdateFields = [f[0] for f in self.DataStructure
					if (f[3] != self.Table) or not f[4]]
		else:
			# Create the _dataStructure attribute
			self._getDataStructure()
			# Delegate to the backend object to figure it out.
			self.__nonUpdateFields = self.BackendObject.setNonUpdateFields(self)


	def isChanged(self, allRows=True, includeNewUnchanged=False):
		"""Return True if there are any changes to the local field values.

		If allRows is True (the default), all records in the recordset will be
		considered. Otherwise, only the current record will be checked.

		If includeNewUnchanged is True, new records that have not been
		modified from their default values, which normally are not
		considered 'changed', will be counted as 'changed'.
		"""
		if allRows:
			if includeNewUnchanged:
				return (len(self._mementos) > 0) or (len(self._newRecords) > 0)
			else:
				return len(self._mementos) > 0
		else:
			row = self.RowNumber
			try:
				rec = self._records[row]
			except IndexError:
				# self.RowNumber doesn't exist (init phase?) Nothing's changed:
				return False
			recKey = self.pkExpression(rec)
			modrec = self._mementos.get(recKey, None)
			if not modrec and includeNewUnchanged:
				modrec = self._newRecords.get(recKey, None)
			return bool(modrec)


	def setNewFlag(self):
		"""Set the current record to be flagged as a new record.

		dBizobj will automatically call this method as appropriate, but if you are
		using dCursor without a proxy dBizobj, you'll need to manually call this
		method after cursor.new(), and (if applicable) after cursor.genTempAutoPK().
		For example:
			cursor.new()
			cursor.genTempAutoPK()
			cursor.setNewFlag()
		"""
		pk = None
		if self.KeyField:
			pk = self.getPK()
			self._newRecords[pk] = None
		# Add the 'new record' flag
		self._records[self.RowNumber][kons.CURSOR_TMPKEY_FIELD] = pk


	def genTempAutoPK(self):
		""" Create a temporary PK for a new record. Set the key field to this
		value, and also create a temp field to hold it so that when saving the
		new record, child records that are linked to this one can be updated
		with the actual PK value.
		"""
		rec = self._records[self.RowNumber]
		kf = self.KeyField
		try:
			if isinstance(kf, tuple):
				pkVal = rec[kf[0]]
			else:
				pkVal = rec[kf]
		except IndexError:
			# No records; default to string
			pkVal = ""

		tmpPK = self._genTempPKVal(pkVal)
		if isinstance(kf, tuple):
			for key in kf:
				rec[key] = tmpPK
		else:
			rec[kf] = tmpPK
		rec[kons.CURSOR_TMPKEY_FIELD] = tmpPK
		return tmpPK


	def _genTempPKVal(self, pkValue):
		""" Return the next available temp PK value. It will be a string, and
		postfixed with '-dabotmp' to avoid potential conflicts with actual PKs
		"""
		ret = self.__tmpPK
		# Decrement the temp PK value
		self.__tmpPK -= 1
		if isinstance(pkValue, basestring):
			ret = "%s-dabotmp" % ret
		return ret


	def getPK(self):
		""" Returns the value of the PK field in the current record. If that record
		is new an unsaved record, return the temp PK value. If this is a compound
		PK, return a tuple containing each field's values.
		"""
		ret = None
		if self.RowCount <= 0:
			raise dException.NoRecordsException(
					_("No records in the data set."))
		rec = self._records[self.RowNumber]
		recKey = self.pkExpression()
		if (recKey in self._newRecords) and self.AutoPopulatePK:
			# New, unsaved record
			ret = rec[kons.CURSOR_TMPKEY_FIELD]
		else:
			kf = self.KeyField
			if isinstance(kf, tuple):
				ret = tuple([rec[k] for k in kf])
			else:
				ret = rec.get(kf, None)
		return ret


	def getFieldVal(self, fld, row=None, _rowChangeCallback=None):
		"""Return the value of the specified field in the current or specified row."""
		if self.RowCount <= 0:
			raise dException.NoRecordsException(_("No records in the data set."))
		if row is None:
			row = self.RowNumber
		try:
			rec = self._records[row]
		except IndexError:
			raise dException.RowNotFoundException(
					_("Row #%s requested, but the data set has only %s row(s),") % (row, len(self._records)))
		if isinstance(fld, (tuple, list)):
			ret = []
			for xFld in fld:
				ret.append(self.getFieldVal(xFld, row=row))
			return tuple(ret)
		else:
			try:
				return rec[fld]
			except KeyError:
				try:
					vf = self.VirtualFields[fld]
					if not isinstance(vf, dict):
						vf = {"func": vf}

					requery_children = (vf.get("requery_children", False) and bool(_rowChangeCallback))

					# Move to specified row if necessary, and then call the VirtualFields
					# function, which expects to be on the correct row.
					if not requery_children:
						# The VirtualFields 'requery_children' key is False, or
						# we aren't being called by a bizobj, so there aren't child bizobjs.
						_oldrow = self.RowNumber
						self.RowNumber = row
						ret = vf["func"]()
						self.RowNumber = _oldrow
						return ret
					else:
						# The VirtualFields definition's 'requery_children' key is True, so
						# we need to request a row change and requery of any child bizobjs
						# as necessary, before executing the virtual field function.
						_rowChangeCallback(row)
						return vf["func"]()
				except KeyError:
					raise dException.FieldNotFoundException("%s '%s' %s" % (
							_("Field"), fld, _("does not exist in the data set")))


	def _fldTypeFromDB(self, fld):
		"""Try to determine the field type from the database information
		If the field isn't found, return None.
		"""
		ret = None
		flds = self.getFields()
		try:
			typ = [ff[1] for ff in flds if ff[0] == fld][0]
		except IndexError:
			# This 'fld' value is not a native field, so no way to
			# determine its type
			typ = None
		if typ:
			try:
				ret = {"C": unicode, "D": datetime.date, "B": bool, "G": long,
					"N": float, "M": unicode, "I": int, "T": datetime.datetime}[typ]
			except KeyError:
				ret = None
		return ret


	def _hasValidKeyField(self):
		"""Return True if the KeyField exists and names valid fields."""
		try:
			self.checkPK()
		except dException.MissingPKException:
			return False
		return True


	def setValuesByDict(self, valDict, row=None):
		"""Set the value for multiple fields with one call by passing a dict containing
		the field names as keys, and the new values as values.
		"""
		for fld, val in valDict.items():
			self.setFieldVal(fld, val, row)


	def setFieldVal(self, fld, val, row=None):
		"""Set the value of the specified field."""
		if self.RowCount <= 0:
			raise dException.NoRecordsException(_("No records in the data set"))
		if row is None:
			row = self.RowNumber

		try:
			rec = self._records[row]
		except IndexError:
			raise dException.RowNotFoundException(
					_("Row #%s requested, but the data set has only %s row(s),") % (row, len(self._records)))
		valid_pk = self._hasValidKeyField()
		keyField = self.KeyField
		if fld not in rec:
			if fld in self.VirtualFields:
				# ignore
				return
			raise dException.FieldNotFoundException(
					_("Field '%s' does not exist in the data set.") % (fld,))

		try:
			fldType = self._types[fld]
		except KeyError:
			fldType = self._fldTypeFromDB(fld)
		nonUpdateFields = self.getNonUpdateFields()
		if fldType is not None:
			if fldType != type(val):
				convTypes = (str, unicode, int, float, long, complex)
				if isinstance(val, convTypes) and isinstance(rec[fld], basestring):
					if isinstance(fldType, str):
						val = str(val)
					else:
						val = unicode(val)
				elif isinstance(rec[fld], int) and isinstance(val, bool):
					# convert bool to int (original field val was bool, but UI
					# changed to int.
					val = int(val)
				elif isinstance(rec[fld], int) and isinstance(val, long):
					# convert long to int (original field val was int, but UI
					# changed to long.
					val = int(val)
				elif isinstance(rec[fld], long) and isinstance(val, int):
					# convert int to long (original field val was long, but UI
					# changed to int.
					val = long(val)

			if fldType != type(val):
				ignore = False
				# Date and DateTime types are handled as character, even if the
				# native field type is not. Ignore these. NOTE: we have to deal with the
				# string representation of these classes, as there is no primitive for either
				# 'DateTime' or 'Date'.
				dtStrings = ("<type 'DateTime'>", "<type 'Date'>", "<type 'datetime.datetime'>")
				if str(fldType) in dtStrings and isinstance(val, basestring):
					ignore = True
				elif issubclass(fldType, basestring) and isinstance(val, basestring):
					ignore = True
				elif val is None or fldType is type(None):
					# Any field type can potentially hold None values (NULL). Ignore these.
					ignore = True
				elif isinstance(val, dNoEscQuoteStr):
					# Sometimes you want to set it to a sql function, equation, ect.
					ignore = True
				elif fld in nonUpdateFields:
					# don't worry so much if this is just a calculated field.
					ignore = True
				else:
					# This can also happen with a new record, since we just stuff the
					# fields full of empty strings.
					ignore = (rec.get(keyField, None) in self._newRecords)

				if not ignore:
					msg = _("!!! Data Type Mismatch: field=%s. Expecting: %s; got: %s") \
							% (fld, str(fldType), str(type(val)))
					dabo.errorLog.write(msg)

		# If the new value is different from the current value, change it and also
		# update the mementos if necessary.
		old_val = rec[fld]
		if old_val != val:
			if valid_pk:
				if fld == keyField:
					# Changing the key field value, need to key the mementos on the new
					# value, not the old. Additionally, need to copy the mementos from the
					# old key value to the new one.
					keyFieldValue = val
					old_mem = self._mementos.get(old_val, None)
					if old_mem is not None:
						self._mementos[keyFieldValue] = old_mem
						del self._mementos[old_val]
				else:
					if self._compoundKey:
						keyFieldValue = tuple([rec[k] for k in keyField])
					else:
						keyFieldValue = rec[keyField]
				mem = self._mementos.get(keyFieldValue, {})
				if (fld in mem) or (fld in nonUpdateFields):
					# Memento is already there, or it isn't updateable.
					pass
				else:
					# Save the memento for this field.
					mem[fld] = old_val

				try:
					if mem[fld] == val:
						# Value changed back to the original memento value; delete the memento.
						del mem[fld]
				except KeyError:
					pass
				if mem:
					self._mementos[keyFieldValue] = mem
				else:
					self._clearMemento(row)
			else:
				dabo.infoLog.write("Field value changed, but the memento"
						" can't be saved, because there is no valid KeyField.")

			# Finally, save the new value to the field:
			rec[fld] = val


	def getRecordStatus(self, row=None, pk=None):
		""" Returns a dictionary containing an element for each changed
		field in the specified record (or the current record if none is specified).
		The field name is the key for each element; the value is a 2-element
		tuple, with the first element being the original value, and the second
		being the current value. You can specify the record by either the
		row number or the PK.
		"""
		ret = {}
		if pk is not None:
			recs = [r for r in self._records
					if r[self._keyField] == pk]
			try:
				rec = recs[0]
			except IndexError:
				return ret
		else:
			if row is None:
				row = self.RowNumber
			rec = self._records[row]
			pk = self.pkExpression(rec)

		mem = self._mementos.get(pk, {})

		for k, v in mem.items():
			ret[k] = (v, rec[k])
		return ret


	def _getNewRecordDiff(self, row=None, pk=None):
		""" Returns a dictionary containing an element for each field
		in the specified record (or the current record if none is specified). You
		may specify the record by either row number or PK value.
		The field name is the key for each element; the value is a 2-element
		tuple, with the first element being the original value, and the second
		being the current value.

		This is used internally in __saverow, and only applies to new records.
		"""
		ret = {}
		if pk is not None:
			recs = [r for r in self._records
					if r[self._keyField] == pk]
			try:
				rec = recs[0]
			except IndexError:
				return ret
		else:
			if row is None:
				row = self.RowNumber
			rec = self._records[row]
			pk = self.pkExpression(rec)

		for k, v in rec.items():
			if k not in (kons.CURSOR_TMPKEY_FIELD,):
				ret[k] = (None, v)
		return ret


	def getCurrentRecord(self):
		"""Returns the current record (as determined by self.RowNumber)
		as a dict, or None if the RowNumber is not a valid record.
		"""
		try:
			ret = self.getDataSet(rowStart=self.RowNumber, rows=1)[0]
		except IndexError:
			ret = None
		return ret


	def getDataSet(self, flds=(), rowStart=0, rows=None, returnInternals=False):
		""" Get the entire data set encapsulated in a dDataSet object.

		If the optional	'flds' parameter is given, the result set will be filtered
		to only include the specified fields. rowStart specifies the starting row
		to include, and rows is the number of rows to return.
		"""
		ds = []
		internals = (kons.CURSOR_TMPKEY_FIELD,)

		if rows is None:
			rows = self.RowCount
		for row, rec in enumerate(self._records):
			if row >= rowStart and row < (rowStart+rows):
				tmprec = rec.copy()
				for k, v in self.VirtualFields.items():
					# only calc requested virtualFields
					if (flds and k in flds) or not flds:
						tmprec.update({k: self.getFieldVal(k, row)})
				if flds:
					# user specified specific fields - get rid of all others
					for k in tmprec.keys():
						if k not in flds:
							del tmprec[k]
				if not flds and not returnInternals:
					# user didn't specify explicit fields and doesn't want internals
					for internal in internals:
						tmprec.pop(internal, None)
				ds.append(tmprec)
		return dDataSet(ds)


	def appendDataSet(self, ds):
		"""Appends the rows in the passed dataset to this cursor's dataset. No checking
		is done on the dataset columns to make sure that they are correct for this cursor;
		it is the responsibility of the caller to make sure that they match. If invalid data is
		passed, a dException.FieldNotFoundException will be raised.
		"""
		kf = self.KeyField
		if not isinstance(kf, tuple):
			kf = (kf, )
		for rec in ds:
			self.new()
			for col, val in rec.items():
				if self.AutoPopulatePK and (col in kf):
					continue
				self.setFieldVal(col, val)


	def cloneRecord(self):
		"""Creates a copy of the current record and adds it to the dataset."""
		if not self.RowCount:
			raise dException.NoRecordsException(_("No records in the data set."))
		rec = self._records[self.RowNumber].copy()
		if self.AutoPopulatePK:
			kf = self.KeyField
			blank = self._getBlankRecord()
			if not isinstance(kf, tuple):
				kf = (kf, )
			for fld in kf:
				rec[fld] = blank[fld]
		self.appendDataSet((rec, ))


	def getDataTypes(self):
		"""Returns the internal _types dict."""
		return self._types


	def _storeData(self, data, typs):
		"""Accepts a dataset and type dict from an external source and
		uses it as its own. Also resets the lastRequeryTime value.
		"""
		# clear mementos and new record flags:
		self._mementos = {}
		self._newRecords = {}
		self.lastRequeryTime = time.time()
		# If None is passed as the data, exit after resetting the flags
		if data is None:
			return
		# Store the values
		self._records = data
		self._types = typs
		# Clear the unsorted list, and then apply the current sort
		self.__unsortedRows = []
		if self.sortColumn:
			try:
				self.sort(self.sortColumn, self.sortOrder)
			except dException.NoRecordsException:
				# No big deal
				pass


	def filter(self, fld, expr, op="="):
		"""Apply a filter to the current records."""
		self._records = self._records.filter(fld=fld, expr=expr, op=op)

	def filterByExpression(self, expr):
		"""Allows you to filter by any expression that would make a
		valid 'where' clause in SQLite.
		"""
		self._records = self._records.filterByExpression(expr)

	def removeFilter(self):
		"""Remove the most recently applied filter."""
		self._records = self._records.removeFilter()


	def removeFilters(self):
		"""Remove all applied filters, going back to the original data set."""
		self._records = self._records.removeFilters()


	def replace(self, field, valOrExpr, scope=None):
		"""Replaces the value of the specified field with the given value
		or expression. All records matching the scope are affected; if
		no scope is specified, all records are affected.

		'valOrExpr' will be treated as a literal value, unless it is prefixed
		with an equals sign. All expressions will therefore be a string
		beginning with '='. Literals can be of any type.
		"""
		# Make sure that the data set object has any necessary references
		self._records.Cursor = self
		self._records.Bizobj = self._bizobj
		self._records.replace(field, valOrExpr, scope=scope)


	def first(self):
		""" Move the record pointer to the first record of the data set."""
		if self.RowCount > 0:
			self.RowNumber = 0
		else:
			raise dException.NoRecordsException(_("No records in data set"))


	def prior(self):
		""" Move the record pointer back one position in the recordset."""
		if self.RowCount > 0:
			if self.RowNumber > 0:
				self.RowNumber -= 1
			else:
				raise dException.BeginningOfFileException(
						_("Already at the beginning of the data set."))
		else:
			raise dException.NoRecordsException(
					_("No records in data set"))


	def next(self):
		""" Move the record pointer forward one position in the recordset."""
		if self.RowCount > 0:
			if self.RowNumber < (self.RowCount-1):
				self.RowNumber += 1
			else:
				raise dException.EndOfFileException(
						_("Already at the end of the data set."))
		else:
			raise dException.NoRecordsException(_("No records in data set"))


	def last(self):
		""" Move the record pointer to the last record in the recordset."""
		if self.RowCount > 0:
			self.RowNumber = self.RowCount-1
		else:
			raise dException.NoRecordsException(_("No records in data set"))


	def save(self, allRows=False):
		""" Save any changes to the data back to the data store."""
		# Make sure that there is data to save
		if self.RowCount <= 0:
			raise dException.NoRecordsException(_("No data to save"))
		# Make sure that there is a PK
		self.checkPK()

		def saverow(row):
			try:
				self.__saverow(row)
			except dException.DBQueryException, e:
				# Error was encountered. Raise an exception so that the
				# calling bizobj can rollback the transaction if necessary
				try:
					errMsg = str(e).decode(self.Encoding)
				except UnicodeError:
					errMsg = unicode(e)
				dabo.dbActivityLog.write(
						_("DBQueryException encountered in save(): %s") % errMsg)
				raise e
			except StandardError, e:
				errMsg = str(e)
				if "connect" in errMsg.lower():
					dabo.dbActivityLog.write(
							_("Connection Lost exception encountered in saverow(): %s") % errMsg)
					raise dException.ConnectionLostException(errMsg)
				else:
					# Error was encountered. Raise an exception so that the
					# calling bizobj can rollback the transaction if necessary
					raise

		self._syncAuxProperties()

		# Faster to deal with 2 specific cases: all rows or just current row
		if allRows:
			pks_to_save = self._mementos.keys()
			for pk_id in pks_to_save:
				row, rec = self._getRecordByPk(pk_id)
				saverow(row)
		else:
			pk = self.pkExpression()
			if pk in self._mementos.keys():
				saverow(self.RowNumber)


	def __saverow(self, row):
		rec = self._records[row]
		recKey = self.pkExpression(rec)
		newrec = kons.CURSOR_TMPKEY_FIELD in rec
		
		newPKVal = None
		if newrec and self.AutoPopulatePK:
			# Some backends do not provide a means to retrieve
			# auto-generated PKs; for those, we need to create the
			# PK before inserting the record so that we can pass it on
			# to any linked child records. NOTE: if you are using
			# compound PKs, this cannot be done.
			newPKVal = self.pregenPK()
			if newPKVal and not self._compoundKey:
				self.setFieldVal(self.KeyField, newPKVal, row)

		if newrec:
			diff = self._getNewRecordDiff(row)
		else:
			diff = self.getRecordStatus(row)
		aq = self.AutoQuoteNames
		if diff:
			if newrec:
				flds = ""
				vals = ""
				kf = self.KeyField
				for kk, vv in diff.items():
					if self.AutoPopulatePK:
						if self._compoundKey:
							skipIt = (kk in kf)
						else:
							# Skip the key field, unless we pre-generated its value above.
							skipIt = (kk == self.KeyField) and not newPKVal
						if skipIt:
							# we don't want to include the PK in the insert
							continue
					if kk in self.getNonUpdateFields():
						# Skip it.
						continue
					if self._nullDefaults and vv == (None, None):
						# Skip these, too
						continue
					# Append the field and its value.
					flds += ", " + self.BackendObject.encloseNames(kk, aq)
					# add value to expression
					vals += ", %s" % (self.formatForQuery(vv[1]),)

				# Trim leading comma-space from the strings
				flds = flds[2:]
				vals = vals[2:]
				if not flds:
					# Some backends (sqlite) require non-empty field clauses. We already
					# know that we are expecting the backend to generate the PK, so send
					# NULL as the PK Value:
					flds = self.KeyField
					vals = "NULL"
				sql = "insert into %s (%s) values (%s) " % (
						self.BackendObject.encloseNames(self.Table, aq), flds, vals)

			else:
				pkWhere = self.makePkWhere(row)
				updClause = self.makeUpdClause(diff)
				sql = "update %s set %s where %s" % (self.BackendObject.encloseNames(self.Table, aq),
						updClause, pkWhere)

			#run the update
			aux = self.AuxCursor
			res = aux.execute(sql)

			if newrec and self.AutoPopulatePK and (newPKVal is None):
				# Call the database backend-specific code to retrieve the
				# most recently generated PK value.
				newPKVal = aux.getLastInsertID()
				if newPKVal and not self._compoundKey:
					self.setFieldVal(self.KeyField, newPKVal, row)

			if newrec and self._nullDefaults:
				# We need to retrieve any new default values
				aux = self.AuxCursor
				if not isinstance(self.KeyField, tuple):
					keyFIelds = [self.KeyField]
				else:
					keyFIelds = self.KeyField
				wheres = []
				for kf in keyFIelds:
					fld = self.BackendObject.encloseNames(kf, self.AutoQuoteNames)
					val = self.getFieldVal(kf)
					if isinstance(val, basestring):
						val = "'" + val.encode(self.Encoding) + "' "
					elif isinstance(val, (datetime.date, datetime.datetime)):
						val = self.formatDateTime(val)
					else:
						val = str(val)
					wheres.append("%s = %s" % (fld, val))
				where = " and ".join(wheres)
				aux.execute("select * from %s where %s" % (self.Table, where))
				try:
					data = aux.getDataSet()[0]
					for fld, val in data.items():
						try:
							self.setFieldVal(fld, val)
						except dException.FieldNotFoundException:
							# Field is not in the dataset
							pass
				except IndexError:
					# For some reason we could not retrieve the matching PK record
					pass

			self._clearMemento(row)
			if newrec:
				self._clearNewRecord(row=row, pkVal=recKey)
			else:
				if not res:
					# Different backends may cause res to be None
					# even if the save is successful.
					self.BackendObject.noResultsOnSave()


	def _clearMemento(self, row=None):
		"""Erase the memento for the passed row, or current row if none passed."""
		if row is None:
			row = self.RowNumber
		rec = self._records[row]

		try:
			pk = self.getPK()
			del self._mementos[pk]
		except KeyError:
			# didn't exist
			pass


	def _clearNewRecord(self, row=None, pkVal=None):
		"""Erase the new record flag for the passed row, or current row if none passed."""
		# If pkVal passed, delete that reference:
		if pkVal is not None:
			try:
				del self._newRecords[pkVal]
				if row is None:
					# We deleted based on pk, don't delete flag for the current row.
					return
			except KeyError:
				pass

		if row is None:
			row = self.RowNumber
		rec = self._records[row]

		try:
			pk = self.getPK()
			del self._newRecords[pk]
		except KeyError:
			# didn't exist
			pass
		# Remove the temp key field column, if still present.
		rec.pop(kons.CURSOR_TMPKEY_FIELD, None)


	def getDataDiff(self, allRows=False):
		"""Create a compact representation of all the modified records
		for this cursor.
		"""
		diff = []
		def rowDiff(pk):
			newrec = pk in self._newRecords
			if newrec:
				ret = self._getNewRecordDiff(pk=pk)
			else:
				ret = self.getRecordStatus(pk=pk)
			ret[self._keyField] = pk
			ret[kons.CURSOR_TMPKEY_FIELD] = newrec
			return ret

		if allRows:
			for pk in self._mementos.keys():
				diff.append(rowDiff(pk))
		else:
			pk = self.getPK()
			if pk in self._mementos:
				diff.append(rowDiff(pk))
		return diff


	def pregenPK(self):
		"""Various backend databases require that you manually
		generate new PKs if you need to refer to their values afterward.
		This method will call the backend to generate and
		retrieve a new PK if the backend supports this. We use the
		auxiliary cursor so as not to alter the current data.
		"""
		return self.BackendObject.pregenPK(self.AuxCursor)


	def _getBlankRecord(self):
		"""Returns a record template, with each field set to the 'blank' value
		for that data type.
		"""
		if not self._blank:
			self.__setStructure()
		return self._blank.copy()


	def new(self):
		"""Add a new record to the data set."""
		blank = self._getBlankRecord()
		self._records = dDataSet(self._records + (blank,))
		# Adjust the RowCount and position
		self.RowNumber = self.RowCount - 1


	def cancel(self, allRows=False, ignoreNoRecords=None):
		""" Revert any changes to the data set back to the original values."""
		if ignoreNoRecords is None:
			ignoreNoRecords = True
		if self.RowCount == 0:
			if ignoreNoRecords:
				# Nothing to do!
				return
			else:
				raise dException.NoRecordsException(_("No data to cancel."))

		# Faster to deal with 2 specific cases: all rows or just current row
		if allRows:
			try:
				recs = self._records.UnfilteredDataSet
			except AttributeError:
				# Not a dDataSet
				recs = self._records

			if self._newRecords:
				recs = list(recs)
				delrecs_ids = self._newRecords.keys()
				delrecs_idx = []
				for rec_id in delrecs_ids:
					# Remove any memento associated with the canceled new record, and
					# append to the list of indexes to delete.
					row, rec = self._getRecordByPk(rec_id)
					self._clearMemento(row)
					delrecs_idx.append(self._records._index(rec))
				delrecs_idx.sort(reverse=True)
				for idx in delrecs_idx:
					del recs[idx]
				self._newRecords = {}
				recs = dDataSet(recs)
				if self.RowNumber >= self.RowCount:
					self.RowNumber = self.RowCount - 1

			for rec_pk, mem in self._mementos.items():
				row, rec = self._getRecordByPk(rec_pk)
				for fld, val in mem.items():
					self._records[row][fld] = val
			self._mementos = {}

		else:
			row = self.RowNumber
			rec = self._records[row]
			recKey = self.pkExpression(rec)
			if recKey in self._newRecords:
				# We simply need to remove the row, and clear the memento and newrec flag.
				self._clearMemento(row)
				self._clearNewRecord(row)
				recs = list(self._records)
				del recs[recs.index(rec)]
				self._records = dDataSet(recs)
				if self.RowNumber >= self.RowCount:
					self.RowNumber = self.RowCount - 1
				return

			# Not a new record: need to manually replace the old values:
			for fld, val in self._mementos.get(recKey, {}).items():
				self._records[row][fld] = val
			self._clearMemento(row)


	def delete(self, delRowNum=None):
		"""Delete the specified row, or the currently active row."""
		if self.RowNumber < 0 or self.RowCount == 0:
			# No query has been run yet
			raise dException.NoRecordsException(_("No record to delete"))
		if delRowNum is None:
			# assume that it is the current row that is to be deleted
			delRowNum = self.RowNumber

		rec = self._records[delRowNum]
		pk = self.pkExpression(rec)
		if pk in self._newRecords:
			res = True
			del self._newRecords[pk]
			if pk in self._mementos:
				del self._mementos[pk]
		else:
			pkWhere = self.makePkWhere()
			# some backends(PostgreSQL) don't return information about number of deleted rows
			# try to fetch it before
			sql = "select count(*) as cnt from %s where %s" % (self.Table, pkWhere)
			aux = self.AuxCursor
			aux.execute(sql)
			res = aux.getFieldVal('cnt')
			if res:
				sql = "delete from %s where %s" % (self.Table, pkWhere)
				aux.execute(sql)


		if not res:
			# Nothing was deleted
			self.BackendObject.noResultsOnDelete()
		else:
			# Delete the record from the current dataset
			self._removeRow(delRowNum)


	def _removeRow(self, row):
		## Since record sets are tuples and thus immutable, we need to do this
		## little dance to remove a row.
		lRec = list(self._records)
		del lRec[row]
		self._records = dDataSet(lRec)
		self.RowNumber = min(self.RowNumber, self.RowCount-1)


	def flush(self):
		""" Some backends need to be prompted to flush changes
		to disk even without starting a transaction. This is the method
		to call to accomplish this.
		"""
		self.BackendObject.flush(self)


	def setDefaults(self, vals):
		"""Set the default field values for newly added records. The
		'vals' parameter is a dictionary of fields and their default values.
		If vals is None, the defaults for all but the KeyField will be set to
		None, and their values will not be included in the insert statement
		when saved unless the user changes them to some non-null
		value.
		"""
		rec = self._records[self.RowNumber]
		keyField = self.KeyField
		keyFieldSet = False
		self._nullDefaults = (vals is None)

		def setDefault(field, val):
			if field in rec:
				# If it is a function, execute it to get the value, else use literal.
				if callable(val):
					val = val()
				elif isinstance(val, tuple) and val and callable(val[0]):
					# This is a tuple consisting of a function and zero to many parameters
					fnc = val[0]
					prms = val[1:]
					val = fnc(*prms)
				self.setFieldVal(field, val)
			else:
				raise dException.FieldNotFoundException(
						_("Can't set default value for nonexistent field '%s'.") % field)

		if self._nullDefaults:
			for field in rec.keys():
				if field == keyField:
					continue
				self.setFieldVal(field, None)
		else:
			if keyField in vals.keys():
				# Must set the pk default value first, for mementos to be filled in
				# correctly.
				setDefault(keyField, vals[keyField])
				keyFieldSet = True

			for field, val in vals.items():
				if field == keyField and keyFieldSet:
					continue
				setDefault(field, val)


	def __setStructure(self):
		"""Set the structure of a newly-added record."""
		for field in self.DataStructure:
			field_alias = field[0]
			field_type = field[1]
			field_ispk = field[2]
			table_name = field[3]
			field_name = field[4]
			field_scale = field[5]

			typ = dabo.db.getPythonType(field_type)
			# Handle the non-standard cases
			if typ is Decimal:
				newval = Decimal()
				# If the backend reports a decimal scale, use it. Scale refers to the
				# number of decimal places.
				scale = field_scale
				if scale is None:
					scale = 2
				ex = "0.%s" % ("0"*scale)
				newval = newval.quantize(Decimal(ex))
			elif typ is datetime.datetime:
				newval = datetime.datetime.min
			elif typ is datetime.date:
				newval = datetime.date.min
			elif typ is None:
				newval = None
			else:
				try:
					newval = typ()
				except Exception, e:
					dabo.errorLog.write(_("Failed to create newval for field '%s'") % field_alias)
					dabo.errorLog.write(str(e))
					newval = u""

			self._blank[field_alias] = newval

		# Mark the calculated and derived fields.
		self.__setNonUpdateFields()


	def getChangedRows(self, includeNewUnchanged=False):
		"""Returns a list of rows with changes."""
		chKeys = self._mementos.keys()
		if includeNewUnchanged:
			# We need to also count all new records
			chKeys = dict.fromkeys(chKeys + self._newRecords.keys()).keys()
		return map(self._getRowByPk, chKeys)


	def _getRecordByPk(self, pk):
		"""Find the record with the passed primary key; return (row, record)."""
		kf = self.KeyField
		if kf:
			for idx, rec in enumerate(self._records):
				key = self.getFieldVal(kf, row=idx)
				if key == pk:
					return (idx, rec)
		return (None, None)


	def _getRowByPk(self, pk):
		"""Find the record with the passed primary key value; return row number."""
		row, rec = self._getRecordByPk(pk)
		return row


	def moveToPK(self, pk):
		""" Find the record with the passed primary key, and make it active.

		If the record is not found, the position is set to the first record.
		"""
		row, rec = self._getRecordByPk(pk)
		if row is None:
			row = 0
		self.RowNumber = row


	def moveToRowNum(self, rownum):
		""" Move the record pointer to the specified row number.

		If the specified row does not exist, the pointer remains where it is,
		and an exception is raised.
		"""
		if (rownum >= self.RowCount) or (rownum < 0):
			raise dException.dException(_("Invalid row specified: %s. RowCount=%s") % (rownum, self.RowCount))
		self.RowNumber = rownum


	def seek(self, val, fld=None, caseSensitive=True, near=False, movePointer=True):
		""" Find the first row where the field value matches the passed value.

		Returns the row number of the first record that matches the passed
		value in the designated field, or -1 if there is no match. If 'near' is
		True, a match will happen on the row whose value is the greatest value
		that is less than the passed value. If 'caseSensitive' is set to False,
		string comparisons are done in a case-insensitive fashion.
		"""
		ret = -1
		if fld is None:
			# Default to the current sort order field
			fld = self.sortColumn
		if self.RowCount <= 0:
			# Nothing to seek within
			return ret
		# Make sure that this is a valid field
		if not fld:
			raise dException.FieldNotFoundException(_("No field specified for seek()"))
		if (fld not in self._records[0]) and (fld not in self.VirtualFields):
			raise dException.FieldNotFoundException(_("Non-existent field '%s'") % (fld,))

		# Copy the specified field vals and their row numbers to a list, and
		# add those lists to the sort list
		sortList = []
		for row in range(0, self.RowCount):
			sortList.append([self.getFieldVal(fld, row=row), row])

		# Determine if we are seeking string values
		field_type = self._types.get(fld, type(sortList[0][0]))
		compString = issubclass(field_type, basestring)

		if not compString:
			# coerce val to be the same type as the field type
			if issubclass(field_type, int):
				try:
					val = int(val)
				except ValueError:
					val = int(0)

			elif issubclass(field_type, long):
				try:
					val = long(val)
				except ValueError:
					val = long(0)

			elif issubclass(field_type, float):
				try:
					val = float(val)
				except ValueError:
					val = float(0)

		if compString and not caseSensitive:
			sortList.sort(key=caseInsensitiveSortKey)
		else:
			sortList.sort()

		# Now iterate through the list to find the matching value. I know that
		# there are more efficient search algorithms, but for this purpose, we'll
		# just use brute force
		for fldval, row in sortList:
			if not compString or caseSensitive:
				match = (fldval == val)
			else:
				# Case-insensitive string search.
				l_fldval, l_val = fldval, val
				if l_fldval is not None:
					l_fldval = l_fldval.lower()
				if l_val is not None:
					l_val = l_val.lower()
				match = (l_fldval == l_val)

			if match:
				ret = row
				break
			else:
				if near:
					ret = row
				# If we are doing a near search, see if the row is less than the
				# requested matching value. If so, update the value of 'ret'. If not,
				# we have passed the matching value, so there's no point in
				# continuing the search.
				if compString and not caseSensitive:
					toofar = l_fldval > l_val
				else:
					toofar = fldval > val
				if toofar:
					break
		if movePointer and ret > -1:
			# Move the record pointer
			self.RowNumber = ret
		return ret


	def checkPK(self):
		""" Verify that the field(s) specified in the KeyField prop exist."""
		# First, make sure that there is *something* in the field
		kf = self.KeyField
		if not kf:
			raise dException.MissingPKException(
					_("checkPK failed; no primary key specified"))

		if isinstance(kf, basestring):
			kf = [kf]
		# Make sure that there is a field with that name in the data set
		try:
			for fld in kf:
				self._records[0][fld]
		except KeyError:
			raise dException.MissingPKException(
					_("Primary key field does not exist in the data set: ") + fld)


	def makePkWhere(self, row=None):
		""" Create the WHERE clause used for updates, based on the pk field.

		Optionally pass in a row number, otherwise use the current record.
		"""
		if not self.KeyField:
			# Cannot update without a KeyField
			return "1 = 0"
		bo = self.BackendObject
		tblPrefix = bo.getWhereTablePrefix(self.Table,
					autoQuote=self.AutoQuoteNames)
		if not row:
			row = self.RowNumber
		rec = self._records[row]

		if self._compoundKey:
			keyFields = [fld for fld in self.KeyField]
		else:
			keyFields = [self.KeyField]
		recKey = self.pkExpression(rec)
		mem = self._mementos.get(recKey, {})

		def getPkVal(fld):
			try:
				return mem[fld]
			except KeyError:
				return rec[fld]

		ret = ""
		for fld in keyFields:
			fldSafe = bo.encloseNames(fld, self.AutoQuoteNames)
			if ret:
				ret += " AND "
			pkVal = getPkVal(fld)
			if isinstance(pkVal, basestring):
				ret += tblPrefix + fldSafe + "='" + pkVal.encode(self.Encoding) + "' "
			elif isinstance(pkVal, (datetime.date, datetime.datetime)):
				ret += tblPrefix + fldSafe + "=" + self.formatDateTime(pkVal) + " "
			else:
				ret += tblPrefix + fldSafe + "=" + str(pkVal) + " "
		return ret


	def makeUpdClause(self, diff):
		""" Create the 'set field=val' section of the Update statement. """
		ret = ""
		bo = self.BackendObject
		aq = self.AutoQuoteNames
		tblPrefix = bo.getUpdateTablePrefix(self.Table, autoQuote=aq)
		nonup = self.getNonUpdateFields()
		for fld, val in diff.items():
			old_val, new_val = val
			# Skip the fields that are not to be updated.
			if fld in nonup:
				continue
			if ret:
				ret += ", "
			ret += tblPrefix + bo.encloseNames(fld, aq) + " = " + self.formatForQuery(new_val)
		return ret


	def processFields(self, txt):
		return self.BackendObject.processFields(txt)


	def escQuote(self, val):
		""" Escape special characters in SQL strings. """
		ret = val
		if isinstance(val, basestring):
			ret = self.BackendObject.escQuote(val)
		return ret


	def getTables(self, includeSystemTables=False):
		""" Return a tuple of tables in the current database."""
		return self.BackendObject.getTables(self.AuxCursor, includeSystemTables)


	def getTableRecordCount(self, tableName):
		""" Get the number of records in the backend table."""
		return self.BackendObject.getTableRecordCount(tableName, self.AuxCursor)


	def getFields(self, tableName=None):
		""" Get field information about the backend table.

		Returns a list of 3-tuples, where the 3-tuple's elements are:
			0: the field name (string)
			1: the field type ('I', 'N', 'C', 'M', 'B', 'D', 'T')
			2: boolean specifying whether this is a pk field.
		"""
		if tableName is None:
			# Use the default
			tableName = self.Table
		key = "%s:::%s" % (tableName, self.CurrentSQL)
		try:
			return self._fieldStructure[key]
		except KeyError:
			flds = self.BackendObject.getFields(tableName, self.AuxCursor)
			self._fieldStructure[key] = flds
			return flds


	def getFieldInfoFromDescription(self):
		""" Get field information from the cursor description.

		Returns a tuple of 3-tuples, where the 3-tuple's elements are:
			0: the field name (string)
			1: the field type ('I', 'N', 'C', 'M', 'B', 'D', 'T'), or None.
			2: boolean specifying whether this is a pk field, or None.
		"""
		return self.BackendObject.getFieldInfoFromDescription(self.descriptionClean)


	def getLastInsertID(self):
		""" Return the most recently generated PK """
		ret = None
		if self.BackendObject:
			ret = self.BackendObject.getLastInsertID(self)
		return ret


	def formatForQuery(self, val):
		""" Format any value for the backend """
		ret = val
		if self.BackendObject:
			ret = self.BackendObject.formatForQuery(val)
		return ret


	def formatDateTime(self, val):
		""" Format DateTime values for the backend """
		ret = val
		if self.BackendObject:
			ret = self.BackendObject.formatDateTime(val)
		return ret


	def formatNone(self):
		""" Format None values for the backend """
		if self.BackendObject:
			return self.BackendObject.formatNone()


	def beginTransaction(self):
		""" Begin a SQL transaction."""
		ret = None
		if self.BackendObject:
			ret = self.BackendObject.beginTransaction(self.AuxCursor)
		return ret


	def commitTransaction(self):
		""" Commit a SQL transaction."""
		ret = None
		if self.BackendObject:
			ret = self.BackendObject.commitTransaction(self.AuxCursor)
		return ret


	def rollbackTransaction(self):
		""" Roll back (revert) a SQL transaction."""
		ret = None
		if self.BackendObject:
			ret = self.BackendObject.rollbackTransaction(self.AuxCursor)
		return ret


	def createTable(self, tabledef):
		"""Create a table based on the table definition."""
		self.BackendObject.createJustTable(tabledef, self)


	def createIndexes(self, tabledef):
		"""Create indexes based on the table definition."""
		self.BackendObject.createJustIndexes(tabledef, self)


	def createTableAndIndexes(self, tabledef):
		"""Create a table and its indexes based on the table definition."""
		self.BackendObject.createTableAndIndexes(tabledef, self)


	###     SQL Builder methods     ########
	def getFieldClause(self):
		""" Get the field clause of the sql statement."""
		return self.sqlManager._fieldClause


	def setFieldClause(self, clause):
		""" Set the field clause of the sql statement."""
		self.sqlManager._fieldClause = self.sqlManager.BackendObject.setFieldClause(clause)


	def addField(self, exp, alias=None):
		""" Add a field to the field clause."""
		sm = self.sqlManager
		beo = sm.BackendObject
		if beo:
			sm._fieldClause = beo.addField(sm._fieldClause, exp, alias,
					autoQuote=self.AutoQuoteNames)
		return sm._fieldClause


	def getFromClause(self):
		""" Get the from clause of the sql statement."""
		return self.sqlManager._fromClause


	def setFromClause(self, clause):
		""" Set the from clause of the sql statement."""
		self.sqlManager._fromClause = self.sqlManager.BackendObject.setFromClause(clause,
					autoQuote=self.AutoQuoteNames)


	def addFrom(self, exp, alias=None):
		""" Add a table to the sql statement. For joins, use
		the addJoin() method.
		"""
		if self.sqlManager.BackendObject:
			self.sqlManager._fromClause = self.sqlManager.BackendObject.addFrom(self.sqlManager._fromClause,
					exp, alias, autoQuote=self.AutoQuoteNames)
		return self.sqlManager._fromClause


	def getJoinClause(self):
		""" Get the join clause of the sql statement."""
		return self.sqlManager._joinClause


	def setJoinClause(self, clause):
		""" Set the join clause of the sql statement."""
		self.sqlManager._joinClause = self.sqlManager.BackendObject.setJoinClause(clause,
					autoQuote=self.AutoQuoteNames)


	def addJoin(self, tbl, joinCondition, joinType=None):
		""" Add a joined table to the sql statement."""
		if self.sqlManager.BackendObject:
			self.sqlManager._joinClause = self.sqlManager.BackendObject.addJoin(tbl,
					joinCondition, self.sqlManager._joinClause, joinType,
					autoQuote=self.AutoQuoteNames)
		return self.sqlManager._joinClause



	def getWhereClause(self):
		""" Get the where clause of the sql statement."""
		return self.sqlManager._whereClause


	def setWhereClause(self, clause):
		""" Set the where clause of the sql statement."""
		self.sqlManager._whereClause = self.sqlManager.BackendObject.setWhereClause(clause,
					autoQuote=self.AutoQuoteNames)


	def addWhere(self, exp, comp="and"):
		""" Add an expression to the where clause."""
		if self.sqlManager.BackendObject:
			self.sqlManager._whereClause = self.sqlManager.BackendObject.addWhere(
					self.sqlManager._whereClause, exp, comp, autoQuote=self.AutoQuoteNames)
		return self.sqlManager._whereClause


	def prepareWhere(self, clause):
		""" Modifies WHERE clauses as needed for each backend. """
		return self.sqlManager.BackendObject.prepareWhere(clause,
					autoQuote=self.AutoQuoteNames)


	def setChildFilter(self, fld, val):
		""" This method sets the appropriate filter for dependent child queries."""

		def getTableAlias(fromClause):
			if not fromClause.strip():
				return None

			joinStrings = ["left join", "right join", "outer join", "inner join", "join"]
			foundAlias = None
			for joinString in joinStrings:
				at = fromClause.lower().find(joinString)
				if at >= 0:
					foundAlias = fromClause[:at].strip()
					break
			if not foundAlias:
				# The alias is the last 'word' in the FROM clause
				foundAlias = fromClause.strip().split()[-1]
			return foundAlias

		alias = getTableAlias(self.sqlManager._fromClause)
		if not alias:
			# Use the old way (pre 2180) of using the Table (DataSource) property.
			alias = self.Table
		filtExpr = " %s.%s = %s " % (alias, fld, val)
		self.setChildFilterClause(filtExpr)


	def setNonMatchChildFilterClause(self):
		""" Called when the parent has no records, which implies that the child
		cannot have any, either.
		"""
		self.setChildFilterClause(" 1 = 0 ")


	def getChildFilterClause(self):
		""" Get the child filter part of the sql statement."""
		return self.sqlManager._childFilterClause


	def setChildFilterClause(self, clause):
		""" Set the child filter clause of the sql statement."""
		self.sqlManager._childFilterClause = self.sqlManager.BackendObject.setChildFilterClause(clause)


	def getGroupByClause(self):
		""" Get the group-by clause of the sql statement."""
		return self.sqlManager._groupByClause


	def setGroupByClause(self, clause):
		""" Set the group-by clause of the sql statement."""
		self.sqlManager._groupByClause = self.sqlManager.BackendObject.setGroupByClause(clause)


	def addGroupBy(self, exp):
		""" Add an expression to the group-by clause."""
		if self.sqlManager.BackendObject:
			self.sqlManager._groupByClause = self.sqlManager.BackendObject.addGroupBy(self.sqlManager._groupByClause,
					exp, autoQuote=self.AutoQuoteNames)
		return self.sqlManager._groupByClause


	def getOrderByClause(self):
		""" Get the order-by clause of the sql statement."""
		return self.sqlManager._orderByClause


	def setOrderByClause(self, clause):
		""" Set the order-by clause of the sql statement."""
		self.sqlManager._orderByClause = self.sqlManager.BackendObject.setOrderByClause(clause)


	def addOrderBy(self, exp):
		""" Add an expression to the order-by clause."""
		if self.sqlManager.BackendObject:
			self.sqlManager._orderByClause = self.sqlManager.BackendObject.addOrderBy(self.sqlManager._orderByClause,
					exp, autoQuote=self.AutoQuoteNames)
		return self.sqlManager._orderByClause


	def getLimitClause(self):
		""" Get the limit clause of the sql statement."""
		return self.sqlManager._limitClause


	def setLimitClause(self, clause):
		""" Set the limit clause of the sql statement."""
		self.sqlManager._limitClause = clause

	# For simplicity's sake, create aliases
	setLimit, getLimit = setLimitClause, getLimitClause



	def getLimitWord(self):
		""" Return the word to use in the db-specific limit clause."""
		ret = "limit"
		if self.sqlManager.BackendObject:
			ret = self.sqlManager.BackendObject.getLimitWord()
		return ret


	def getLimitPosition(self):
		""" Return the position to place the limit clause.

		For currently-supported dbapi's, the return values of 'top' or 'bottom'
		are sufficient.
		"""
		ret = "bottom"
		if self.sqlManager.BackendObject:
			ret = self.sqlManager.BackendObject.getLimitPosition()
		return ret


	def getSQL(self):
		""" Get the complete SQL statement from all the parts."""
		fieldClause = self.sqlManager._fieldClause
		fromClause = self.sqlManager._fromClause
		joinClause = self.sqlManager._joinClause
		whereClause = self.sqlManager._whereClause
		childFilterClause = self.sqlManager._childFilterClause
		groupByClause = self.sqlManager._groupByClause
		orderByClause = self.sqlManager._orderByClause
		limitClause = self.sqlManager._limitClause

		if not fieldClause:
			fieldClause = "*"

		if not fromClause:
			fromClause = self.Table

		if childFilterClause:
			# Prepend it to the where clause
			if whereClause:
				childFilterClause += "\nand "
			whereClause = childFilterClause + " " + whereClause

		if fromClause:
			fromClause = "  from " + fromClause
		else:
			fromClause = "  from " + self.sqlManager.Table
		if joinClause:
			joinClause = " " + joinClause
		if whereClause:
			whereClause = " where " + whereClause
		if groupByClause:
			groupByClause = " group by " + groupByClause
		if orderByClause:
			orderByClause = " order by " + orderByClause
		if limitClause:
			limitClause = " %s %s" % (self.sqlManager.getLimitWord(), limitClause)
		elif limitClause is None:
			# The limit clause was specifically disabled.
			limitClause = ""
		else:
			limitClause = " %s %s" % (self.sqlManager.getLimitWord(), self.sqlManager._defaultLimit)

		return self.sqlManager.BackendObject.formSQL(fieldClause, fromClause, joinClause,
				whereClause, groupByClause, orderByClause, limitClause)


	def getStructureOnlySql(self):
		"""Creates a SQL statement that will not return any records."""
		holdWhere = self.sqlManager._whereClause
		self.sqlManager.setWhereClause("")
		holdLimit = self.sqlManager._limitClause
		self.sqlManager.setLimitClause(1)
		ret = self.sqlManager.getSQL()
		self.sqlManager.setWhereClause(holdWhere)
		self.sqlManager.setLimitClause(holdLimit)
		return ret


	def executeSQL(self, *args, **kwargs):
		self.sqlManager.execute(self.sqlManager.getSQL(), *args, **kwargs)
	###     end - SQL Builder methods     ########


	def getWordMatchFormat(self):
		return self.sqlManager.BackendObject.getWordMatchFormat()


	def oldVal(self, fieldName, row=None):
		"""Returns the value of the field as it existed after the last requery."""
		if self.RowCount < 1:
			raise dabo.dException.NoRecordsException
		if row is None:
			row = self.RowNumber
		rec = self._records[row]
		pk = self.pkExpression(rec)
		mem = self._mementos.get(pk, None)
		if mem and (fieldName in mem):
			return mem[fieldName]
		return self.getFieldVal(fieldName, row)


	def _setTableForRemote(self, tbl):
		"""Used when running as a remote application. We don't want to trigger
		the methods to query the database for field information.
		"""
		self._table = self.AuxCursor._table = self.sqlManager._table = "%s" % tbl


	## Property getter/setter methods ##
	def _getAutoSQL(self):
		return self.getSQL()


	def _getAutoPopulatePK(self):
		try:
			return self._autoPopulatePK and bool(self.KeyField)
		except AttributeError:
			return True

	def _setAutoPopulatePK(self, autopop):
		self._autoPopulatePK = self.AuxCursor._autoPopulatePK = bool(autopop)


	def _getAutoQuoteNames(self):
		return self._autoQuoteNames

	def _setAutoQuoteNames(self, val):
		self._autoQuoteNames = self.AuxCursor._autoQuoteNames = val


	def _getAuxCursor(self):
		isnew = self.__auxCursor is None
		if isnew:
			if self._cursorFactoryClass is not None:
				if self._cursorFactoryFunc is not None:
					self.__auxCursor = self._cursorFactoryFunc(self._cursorFactoryClass)
		if not self.__auxCursor:
			self.__auxCursor = self.BackendObject.getCursor(self.__class__)
		self.__auxCursor.BackendObject = self.BackendObject
		self.__auxCursor._isAuxiliary = True
		if isnew:
			ac = self.__auxCursor
			ac._autoPopulatePK = self._autoPopulatePK
			ac._autoQuoteNames = self._autoQuoteNames
			ac._dataStructure = self._dataStructure
			if self.BackendObject:
				ac._encoding = self.Encoding
			ac._isPrefCursor = self._isPrefCursor
			ac._keyField = self._keyField
			ac._table = self._table
		return self.__auxCursor


	def _getBackendObject(self):
		return self.__backend

	def _setBackendObject(self, obj):
		self.__backend = obj
		if obj and obj._cursor is None:
			obj._cursor = self
		if self.__auxCursor:
			self.__auxCursor.__backend = obj


	def _getCurrentSQL(self):
		if self.UserSQL:
			return self.UserSQL
		return self.AutoSQL


	def _getDescrip(self):
		return self.__backend.getDescription(self)


	def _getDataStructure(self):
		val = getattr(self, "_dataStructure", None)
		if val is None:
			# Get the information from the backend. Note that elements 3 and 4 get
			# guessed-at values.
			val = getattr(self, "_savedStructureDescription", [])
			if not val:
				if self.BackendObject is None:
					# Nothing we can do. We are probably an AuxCursor
					pass
				else:
					ds = self.BackendObject.getStructureDescription(self)
					gf_names = [gf[0] for gf in self.getFields(self.Table)]
					for field in ds:
						field_name, field_type, pk = field[0], field[1], field[2]
						try:
							field_scale = field[5]
						except IndexError:
							field_scale = None
						if field_name in gf_names:
							table_name = self.Table
						else:
							table_name = "_foreign_table_"
						val.append((field_name, field_type, pk, table_name, field_name, field_scale))
				self._savedStructureDescription = val
			self._dataStructure = val
		return tuple(val)

	def _setDataStructure(self, val):
		# Go through the sequence, raising exceptions or adding default values as
		# appropriate.
		val = list(val)
		for idx, field in enumerate(val):
			field_alias = field[0]
			field_type = field[1]
			try:
				field_pk = field[2]
			except IndexError:
				field_pk = False
			try:
				table_name = field[3]
			except IndexError:
				table_name = self.Table
			try:
				field_name = field[4]
			except IndexError:
				field_name = field_alias
			try:
				field_scale = field[5]
			except IndexError:
				field_scale = None
			val[idx] = (field_alias, field_type, field_pk, table_name, field_name, field_scale)
		self._dataStructure = self.AuxCursor._dataStructure = tuple(val)


	def _getEncoding(self):
		return self.BackendObject.Encoding

	def _setEncoding(self, val):
		self.BackendObject.Encoding = val


	def _getIsAdding(self):
		""" Return True if the current record is a new record."""
		if self.RowCount <= 0:
			return False
		try:
			getattr(self.Record, kons.CURSOR_TMPKEY_FIELD)
			return True
		except dException.FieldNotFoundException:
			return False


	def _getIsPrefCursor(self):
		return self._isPrefCursor

	def _setIsPrefCursor(self, val):
		self._isPrefCursor = self.AuxCursor._isPrefCursor = val


	def _getKeyField(self):
		return self._keyField

	def _setKeyField(self, kf):
		if "," in kf:
			flds = [f.strip() for f in kf.split(",")]
			self._keyField = tuple(flds)
			self._compoundKey = True
		else:
			self._keyField = str(kf)
			self._compoundKey = False
		self.AuxCursor._keyField = self._keyField
		self.AuxCursor._compoundKey = self._compoundKey
		self._keyFieldSet = self.AuxCursor._keyFieldSet = (self._hasValidKeyField)


	def _getLastSQL(self):
		try:
			v = self._lastSQL
		except AttributeError:
			v = self._lastSQL = None
		return v


	def _getRecord(self):
		try:
			ret = self._cursorRecord
		except AttributeError:
			class CursorRecord(object):
				def __init__(self):
					self.cursor = None
					super(CursorRecord, self).__init__()

				def __getattr__(self, att):
					return self.cursor.getFieldVal(att)

				def __setattr__(self, att, val):
					if att in ("cursor", ):
						super(CursorRecord, self).__setattr__(att, val)
					else:
						self.cursor.setFieldVal(att, val)

			ret = self._cursorRecord = CursorRecord()
			self._cursorRecord.cursor = self
		return ret


	def _getRowCount(self):
		try:
			ret = len(self._records)
		except AttributeError:
			ret = -1
		return ret


	def _getRowNumber(self):
		try:
			ret = min(self.__rownumber, self._getRowCount()-1)
		except AttributeError:
			ret = -1
		return ret


	def _setRowNumber(self, num):
		rn = max(0, num)
		maxrow = max(0, (self.RowCount-1) )
		self.__rownumber = min(rn, maxrow)


	def _getTable(self):
		return self._table

	def _setTable(self, table):
		self._table = self.AuxCursor._table = self.sqlManager._table = "%s" % table
		if table and not self._keyFieldSet:
			flds = self.getFields(table)
			if flds is None:
				return
			# Get the PK field, if any
			try:
				self._keyField = [fld[0] for fld in flds
						if fld[2] ][0]
			except IndexError:
				pass


	def _getUserSQL(self):
		return self._userSQL

	def _setUserSQL(self, val):
		self._userSQL = val


	def _getVirtualFields(self):
		return self._virtualFields

	def _setVirtualFields(self, val):
		assert isinstance(val, dict)
		self._virtualFields = val


	AutoPopulatePK = property(_getAutoPopulatePK, _setAutoPopulatePK, None,
			_("When inserting a new record, does the backend populate the PK field?"))

	AutoQuoteNames = property(_getAutoQuoteNames, _setAutoQuoteNames, None,
			_("""When True (default), table and column names are enclosed with
			quotes during SQL creation.  (bool)"""))

	AutoSQL = property(_getAutoSQL, None, None,
			_("Returns the SQL statement automatically generated by the sql manager."))

	AuxCursor = property(_getAuxCursor, None, None,
			_("""Auxiliary cursor object that handles queries that would otherwise
			affect the main cursor's data set.  (dCursorMixin subclass)"""))

	BackendObject = property(_getBackendObject, _setBackendObject, None,
			_("Returns a reference to the object defining backend-specific behavior (dBackend)"))

	CurrentSQL = property(_getCurrentSQL, None, None,
			_("Returns the current SQL that will be run, which is one of UserSQL or AutoSQL."))

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

	Encoding = property(_getEncoding, _setEncoding, None,
			_("Encoding type used by the Backend  (string)") )

	FieldDescription = property(_getDescrip, None, None,
			_("Tuple of field names and types, as returned by the backend  (tuple)") )

	IsAdding = property(_getIsAdding, None, None,
			_("Returns True if the current record is new and unsaved"))

	IsPrefCursor = property(_getIsPrefCursor, _setIsPrefCursor, None,
			_("""Returns True if this cursor is used for managing internal
			Dabo preferences and settings. Default=False.  (bool)"""))

	LastSQL = property(_getLastSQL, None, None,
			_("Returns the last executed SQL statement."))

	KeyField = property(_getKeyField, _setKeyField, None,
			_("""Name of field that is the PK. If multiple fields make up the key,
			separate the fields with commas. (str)"""))

	Record = property(_getRecord, None, None,
			_("""Represents a record in the data set. You can address individual
			columns by referring to 'self.Record.fieldName' (read-only) (no type)"""))

	RowNumber = property(_getRowNumber, _setRowNumber, None,
			_("Current row in the recordset."))

	RowCount = property(_getRowCount, None, None,
			_("Current number of rows in the recordset. Read-only."))

	Table = property(_getTable, _setTable, None,
			_("The name of the table in the database that this cursor is updating."))

	UserSQL = property(_getUserSQL, _setUserSQL, None,
			_("SQL statement to run. If set, the automatic SQL builder will not be used."))

	VirtualFields = property(_getVirtualFields, _setVirtualFields, None,
			_("""A dictionary mapping virtual_field_name to a function to call.

			The specified function will be called when getFieldVal() is called on
			the specified field name."""))
