# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt 

# metadata

from __future__ import unicode_literals
import frappe, json
from frappe.utils import cstr, cint
from frappe.model import integer_docfield_properties, default_fields
from frappe.model.document import Document
from frappe.model.base_document import BaseDocument
from frappe.model.db_schema import type_map

######

def get_meta(doctype, cached=True):
	if cached:
		return frappe.cache().get_value("meta:" + doctype, lambda: Meta(doctype))
	else:
		return Meta(doctype)

class Meta(Document):
	_metaclass = True
	default_fields = default_fields[1:]
	special_doctypes = ("DocField", "DocPerm", "Role", "DocType", "Module Def")
	def __init__(self, doctype):
		self._fields = {}
		super(Meta, self).__init__("DocType", doctype)
		self.process()
	
	def load_from_db(self):
		try:
			super(Meta, self).load_from_db()
		except frappe.DoesNotExistError:
			if self.doctype=="DocType" and self.name in self.special_doctypes:
				fname = frappe.scrub(self.name)
				with open(frappe.get_app_path("frappe", "core", "doctype", fname, fname + ".json"), "r") as f:
					txt = f.read()

				self.__dict__.update(json.loads(txt))
				self.fields = [BaseDocument(d) for d in self.fields]
				if hasattr(self, "permissions"):
					self.permissions = [BaseDocument(d) for d in self.permissions]
			else:
				raise
	
	def get_link_fields(self):
		tmp = self.get("fields", {"fieldtype":"Link", "options":["!=", "[Select]"]})
		for df in self.get("fields", {"fieldtype":"Select", "options": "^link:"}):
			tmp.append(frappe._dict({"fieldname":df.fieldname, "label":df.label, 
				"fieldtype":"Link", "options": df.options[5:]}))
		return tmp
	
	def get_table_fields(self):
		if not hasattr(self, "_table_fields"):
			if self.name!="DocType":
				self._table_fields = self.get('fields', {"fieldtype":"Table"})
			else:
				self._table_fields = doctype_table_fields
				
		return self._table_fields

	def get_valid_columns(self):
		if not hasattr(self, "_valid_columns"):
			if self.name in ("DocType", "DocField", "DocPerm", "Property Setter"):
				self._valid_columns = frappe.db.get_table_columns(self.name)
			else:
				self._valid_columns = self.default_fields + \
					[df.fieldname for df in self.get("fields") if df.fieldtype in type_map]
		
		return self._valid_columns
				
	def get_table_field_doctype(self, fieldname):
		return { "fields": "DocField", "permissions": "DocPerm"}.get(fieldname)
	
	def get_field(self, fieldname):
		if not fieldname in self._fields:
			fields = self.get("fields", {"fieldname":fieldname})
			self._fields[fieldname] = fields[0] if fields else frappe._dict()
		return self._fields[fieldname]

	def get_label(self, fieldname):
		return self.get_field(fieldname).label
		
	def get_options(self, fieldname):
		return self.get_field(fieldname).options
		
	def process(self):
		# don't process for special doctypes
		# prevent's circular dependency
		if self.name in self.special_doctypes:
			return
		
		self.add_custom_fields()
		self.apply_property_setters()
		self.sort_fields()
		
	def add_custom_fields(self):
		try:
			self.extend("fields", frappe.db.sql("""SELECT * FROM `tabCustom Field`
				WHERE dt = %s AND docstatus < 2""", (self.name,), as_dict=1))
		except Exception, e:
			if e.args[0]==1146:
				return
			else:
				raise
	
	def apply_property_setters(self):
		for ps in frappe.db.sql("""select * from `tabProperty Setter` where
			doc_type=%s""", (self.name,), as_dict=1):
			if ps.doctype_or_field=='DocType':
				if ps.property_type in ('Int', 'Check'):
					ps.value = cint(ps.value)

				self.set(ps.property, ps.value)
			else:
				docfield = self.get("fields", {"fieldname":ps.field_name}, limit=1)[0]

				if not docfield: continue
				if ps.property in integer_docfield_properties:
					ps.value = cint(ps.value)

				docfield.set(ps.property, ps.value)
				
	def sort_fields(self):
		"""sort on basis of previous_field"""
		newlist = []
		pending = self.get("fields")

		if self.get("_idx"):
			for fieldname in json.loads(self.get("_idx")):
				d = self.get("fields", {"fieldname": fieldname}, limit=1)
				if d:
					newlist.append(d[0])
					pending.remove(d[0])
		else:
			maxloops = 20
			while (pending and maxloops>0):
				maxloops -= 1
				for d in pending[:]:
					if d.get("previous_field"):
						# field already added
						for n in newlist:
							if n.fieldname==d.previous_field:
								newlist.insert(newlist.index(n)+1, d)
								pending.remove(d)
								break
					else:
						newlist.append(d)
						pending.remove(d)

		# recurring at end	
		if pending:
			newlist += pending

		# renum
		idx = 1
		for d in newlist:
			d.idx = idx
			idx += 1

		self.set("fields", newlist)
		
	def get_restricted_fields(self, restricted_types):
		restricted_fields = self.get("fields", {
			"fieldtype":"Link", 
			"parent": self.name, 
			"ignore_restrictions":("!=", 1), 
			"options":("in", restricted_types)
		})
		if self.name in restricted_types:
			restricted_fields.append(frappe._dict({
				"label":"Name", "fieldname":"name", "options": self.name
			}))
		return restricted_fields


doctype_table_fields = [
	frappe._dict({"fieldname": "fields", "options": "DocField"}), 
	frappe._dict({"fieldname": "permissions", "options": "DocPerm"})
]

#######

def is_single(doctype):
	try:
		return frappe.db.get_value("DocType", doctype, "issingle")
	except IndexError, e:
		raise Exception, 'Cannot determine whether %s is single' % doctype

def get_parent_dt(dt):
	parent_dt = frappe.db.sql("""select parent from tabDocField 
		where fieldtype="Table" and options=%s and (parent not like "old_parent:%%") 
		limit 1""", dt)
	return parent_dt and parent_dt[0][0] or ''

def set_fieldname(field_id, fieldname):
	frappe.db.set_value('DocField', field_id, 'fieldname', fieldname)

def get_field_currency(df, doc):
	"""get currency based on DocField options and fieldvalue in doc"""
	currency = None
	
	if ":" in cstr(df.options):
		split_opts = df.options.split(":")
		if len(split_opts)==3:
			currency = frappe.db.get_value(split_opts[0], doc.get(split_opts[1]), 
				split_opts[2])
	else:
		currency = doc.get(df.options)

	return currency
	
def get_field_precision(df, doc):
	"""get precision based on DocField options and fieldvalue in doc"""
	from frappe.utils import get_number_format_info
	
	number_format = None
	if df.fieldtype == "Currency":
		currency = get_field_currency(df, doc)
		if currency:
			number_format = frappe.db.get_value("Currency", currency, "number_format")
		
	if not number_format:
		number_format = frappe.db.get_default("number_format") or "#,###.##"
		
	decimal_str, comma_str, precision = get_number_format_info(number_format)

	if df.fieldtype == "Float":
		precision = cint(frappe.db.get_default("float_precision")) or 3

	return precision
	
def clear_cache(doctype=None):
	def clear_single(dt):
		frappe.cache().delete_value("meta:" + dt)
		frappe.cache().delete_value("form_meta:" + dt)

	if doctype:
		clear_single(doctype)

		# clear all parent doctypes
		for dt in frappe.db.sql("""select parent from tabDocField 
			where fieldtype="Table" and options=%s""", (doctype,)):
			clear_single(dt[0])

		# clear all notifications
		from frappe.core.doctype.notification_count.notification_count import delete_notification_count_for
		delete_notification_count_for(doctype)

	else:
		# clear all
		for dt in frappe.db.sql("""select name from tabDocType"""):
			clear_single(dt[0])

	frappe.cache().delete_value("is_table")