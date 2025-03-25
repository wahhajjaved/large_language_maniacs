# Copyright (c) 2012 Web Notes Technologies Pvt Ltd (http://erpnext.com)
# 
# MIT License (MIT)
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A 
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT 
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 

# Please edit this list and import only required elements
import webnotes

from webnotes.utils import add_days, add_months, add_years, cint, cstr, date_diff, default_fields, flt, fmt_money, formatdate, generate_hash, getTraceback, get_defaults, get_first_day, get_last_day, getdate, has_common, month_name, now, nowdate, replace_newlines, sendmail, set_default, str_esc_quote, user_format, validate_email_add
from webnotes.model import db_exists, default_fields
from webnotes.model.doc import Document, addchild, removechild, getchildren, make_autoname, SuperDocType
from webnotes.model.doclist import getlist, copy_doclist
from webnotes.model.code import get_obj, get_server_obj, run_server_obj, updatedb, check_syntax
from webnotes import session, form, is_testing, msgprint, errprint

set = webnotes.conn.set
sql = webnotes.conn.sql
get_value = webnotes.conn.get_value
in_transaction = webnotes.conn.in_transaction
convert_to_lists = webnotes.conn.convert_to_lists
	
# -----------------------------------------------------------------------------------------


class DocType:
	def __init__(self, doc, doclist=[]):
		self.doc = doc
		self.doclist = doclist
		self.ref_doc = ''
		
	# Autoname
	#---------------------------------------------------------------------------
	def autoname(self):
		self.doc.name = make_autoname(self.doc.from_doctype + '-' + self.doc.to_doctype)

	
	# Maps the fields in 'To DocType'
	#---------------------------------------------------------------------------
	def dt_map(self, from_doctype, to_doctype, from_docname, to_doc, doclist, from_to_list = '[]'):
		'''
			String <from_doctype> : contains the name of DocType initiating the function
			String <to_doctype>	 : contains the name of DocType created by the function
			String <from_docname> : contains ID(name) of 'from_doctype'
			String <to_doc>			 : contains doc of 'to_doctype'
			String <doclist>			: contains doclist of 'to_doctype'
			String <from_to_list> : contains list of tables which will be mapped
		'''
		
		if not from_docname:
			msgprint(from_doctype + " not selected for mapping", raise_exception=1)
		
		# Validate reference doc docstatus
		self.ref_doc = from_docname
		self.check_ref_docstatus()
		
		if not doclist:
			doclist.append(to_doc)

		tbl_list = sql("select from_table, to_table, from_field, to_field, match_id, validation_logic from `tabTable Mapper Detail` where parent ='%s' order by match_id" % self.doc.name, as_dict=1)

		for t in tbl_list:
			if [t['from_table'], t['to_table']] in eval(from_to_list):
				self.map_fields(t, from_doctype, from_docname, to_doc, doclist)
		
		# Doclist is required when called from server side for refreshing table
		return doclist


	#---------------------------------------------------------------------------
	def map_fields(self, t, from_dt, from_dn, to_doc, doclist):
		"""
			Creates from, to obj and maps flds as per mapper and with same name
		"""
		flds = self.get_mapper_fields(t)
		flds += self.get_fields_with_same_name(t, flds)

		if flds:
			from_docnames = self.get_docnames(t, from_dt, from_dn)
		
			for dn in from_docnames:		
				# Creates object for 'From DocType', it can be parent or child
				from_doc_obj = Document(t['from_table'], dn[0])
			
				# Add a row in target table in 'To DocType' and returns obj
				if t['to_table'] != self.doc.to_doctype:
					to_doc_obj = addchild(to_doc, t['to_field'], t['to_table'], 1, doclist)
				else:
					to_doc_obj = to_doc

				self.set_value(flds, from_doc_obj, to_doc_obj)
				
	#---------------------------------------------------------------------------	
	def get_docnames(self, t, from_dt, from_dn):
		"""
			Returns docnames of source document (parent/child)
		"""
		docnames = ()
		if t['from_table'] == self.doc.from_doctype:
			docnames = sql("select name from `tab%s` where name = '%s' and %s" % (from_dt, from_dn, t['validation_logic']))			
			if not docnames:
				msgprint("Validation failed in doctype mapper. Please contact Administrator.", raise_exception=1)
		else:
			docnames = sql("select name from `tab%s` where parent='%s' and parenttype = '%s' and %s order by idx" % (t['from_table'], from_dn, self.doc.from_doctype, t['validation_logic']))
		
		return docnames
	
	
	#---------------------------------------------------------------------------
	def get_mapper_fields(self, t):	
		return [[f[0], f[1], f[2]] for f in sql("""
			select from_field, to_field, map 
			from `tabField Mapper Detail` 
			where parent = '%s' and match_id = %s		
		""" % (self.doc.name, t['match_id']))]


	#---------------------------------------------------------------------------
	def get_fields_with_same_name(self, t, flds):
		"""
			Returns field list with same name in from and to doctype
		"""
		import copy
		exception_flds = copy.copy(default_fields)
		exception_flds += [f[1] for f in flds]
		
		similar_flds = [
			[d[0], d[0], 'Yes'] for d in sql("""
				select t1.fieldname 
				from `tabDocField` t1, `tabDocField` t2 
				where t1.parent = %s and t2.parent = %s 
				and t1.fieldname = t2.fieldname 
				and t1.docstatus != 2 and t2.docstatus != 2 
				and ifnull(t1.no_copy, 0) = 0
				and ifnull(t1.fieldname, '') != ''
				and t1.fieldtype not in ('Table', 'Section Break', 'Column Break', 'HTML')
			""",(t['from_table'], t['to_table'])) if d[0] not in exception_flds
		]

		return similar_flds		
		
	#---------------------------------------------------------------------------
	def set_value(self, fld_list, obj, to_doc):
		"""
			Assigns value to fields in "To Doctype"
		"""
		for f in fld_list:
			if f[2] == 'Yes':
				if f[0].startswith('eval:'):
					try:
						val = eval(f[0][5:])
					except:
						val = ''
						
					to_doc.fields[f[1]] = val
				else:
					to_doc.fields[f[1]] = obj.fields.get(f[0])
				
				
	#---------------------------------------------------------------------------
	def validate(self):
		"""
			Validate mapper while saving
		"""
		for d in getlist(self.doclist, 'field_mapper_details'):
			# Automatically assigns default value if not entered
			if not d.match_id:
				d.match_id = 0
			if not d.map:
				d.map = 'Yes'
		for d in getlist(self.doclist, 'table_mapper_details'):
			if not d.reference_doctype_key:
				d.reference_doctype_key = ''
			if not d.reference_key:
				d.reference_key = ''
				
		# Check wrong field name
		self.check_fields_in_dt()
		
		
	#---------------------------------------------------------------------------
	def check_fields_in_dt(self):
		"""
			Check if any wrong fieldname entered in mapper
		"""
		for d in getlist(self.doclist, 'field_mapper_details'):
			table_name = sql("select from_table, to_table from `tabTable Mapper Detail` where parent ='%s' and match_id = '%s'" % (self.doc.name, d.match_id))
			
			if table_name:
				exists1 = sql("select name from tabDocField where parent = '%s' and fieldname = '%s'" % (table_name[0][0], d.from_field))
				exists2 = sql("select name from tabDocField where parent = '%s' and fieldname = '%s'" % (table_name[0][1], d.to_field))
				
				# Default fields like name, parent, owner does not exists in DocField
				if not exists1 and d.from_field not in default_fields:
					msgprint('"' + cstr(d.from_field) + '" does not exists in DocType "' + cstr(table_name[0][0]) + '"')
				if not exists2 and d.to_field not in default_fields:
					msgprint('"' + cstr(d.to_field) + '" does not exists in DocType "' + cstr(table_name[0][1]) + '"')
					
					
	# Check consistency of value with reference document
	#---------------------------------------------------
	def validate_reference_value(self, obj, to_docname):
		for t in getlist(self.doclist, 'table_mapper_details'):
			# Reference key is the fieldname which will relate to the from_table
			if t.reference_doctype_key:
				for d in getlist(obj.doclist, t.to_field):
					if d.fields[t.reference_doctype_key] == self.doc.from_doctype:
						self.check_consistency(obj.doc, d, to_docname)
						self.check_ref_docstatus()
				
	# Make list of fields whose value will be consistent with prevdoc
	#-----------------------------------------------------------------
	def get_checklist(self):
		checklist = []
		for f in getlist(self.doclist, 'field_mapper_details'):
		
			# Check which field's value will be compared
			if f.checking_operator:
				checklist.append([f.from_field, f.to_field, f.checking_operator, f.match_id])
		return checklist
				
	def check_fld_type(self, tbl, fld, cur_val):
		ft = sql("select fieldtype from tabDocField where fieldname = '%s' and parent = '%s'" % (fld,tbl))
		ft	= ft and ft[0][0] or ''
		if ft == 'Currency' or ft == 'Float':
			cur_val = '%.2f' % cur_val
		return cur_val, ft
				
	# Check consistency
	#-------------------
	def check_consistency(self, par_obj, child_obj, to_docname):
		checklist = self.get_checklist()
		self.ref_doc = ''
		for t in getlist(self.doclist, 'table_mapper_details'):
			if t.reference_key and child_obj.fields[t.reference_key]:
				for cl in checklist:
					if cl[3] == t.match_id:
						if t.to_field:
							cur_val = child_obj.fields[cl[1]]
						else:
							cur_val = par_obj.fields[cl[1]]
						
						ft = self.check_fld_type(t.to_table, cl[1], cur_val)
						cur_val = ft[0]

						if cl[2] == '=' and (ft[1] == 'Currency' or ft[1] == 'Float'):
							consistent = sql("select name, %s from `tab%s` where name = '%s' and '%s' - %s <= 0.5" % (cl[0], t.from_table, child_obj.fields[t.reference_key], flt(cur_val), cl[0]))
						else:
							consistent = sql("select name, %s from `tab%s` where name = '%s' and '%s' %s ifnull(%s, '')" % (cl[0], t.from_table, child_obj.fields[t.reference_key], ft[1] in ('Currency', 'Float', 'Int') and flt(cur_val) or cstr(cur_val), cl[2],	cl[0]))

						if not self.ref_doc:
							det = sql("select name, parent from `tab%s` where name = '%s'" % (t.from_table, child_obj.fields[t.reference_key]))
							self.ref_doc = det[0][1] and det[0][1] or det[0][0]			 

						if not consistent:
							self.give_message(t.from_table, t.to_table, cl[0], cl[1], child_obj.fields[t.reference_key], cl[2])
							
	# Gives message and raise exception
	#-----------------------------------
	def give_message(self, from_table, to_table, from_field, to_field, ref_value, operator):
		# Select label of the field
		to_fld_label = sql("select label from tabDocField where parent = '%s' and fieldname = '%s'" % (to_table, to_field))
		from_fld_label = sql("select label from tabDocField where parent = '%s' and fieldname = '%s'" % (from_table, from_field))
		
		op_in_words = {'=':'equal to ', '>=':'greater than equal to ', '>':'greater than ', '<=':'less than equal to ', '<':'less than '}
		msgprint(to_fld_label[0][0] + " should be " + op_in_words[operator] + from_fld_label[0][0] + " of " +	self.doc.from_doctype + ": " + self.ref_doc, raise_exception=1)
		
	def check_ref_docstatus(self):
		if self.ref_doc:
			det = sql("select name, docstatus from `tab%s` where name = '%s'" % (self.doc.from_doctype, self.ref_doc))
			if not det:
				msgprint(self.doc.from_doctype + ": " + self.ref_doc + " does not exists in the system", raise_exception=1)
			elif self.doc.ref_doc_submitted and det[0][1] != 1:
				msgprint(self.doc.from_doctype + ": " + self.ref_doc + " is not Submitted Document.", raise_exception=1)

	def on_update(self):
		"""
			If developer_mode = 1, mapper will be written to files
		"""
		import webnotes.defs
		if hasattr(webnotes.defs, 'developer_mode') and webnotes.defs.developer_mode:
			from webnotes.modules.export_module import export_to_files
			export_to_files(record_list=[[self.doc.doctype, self.doc.name]])		
