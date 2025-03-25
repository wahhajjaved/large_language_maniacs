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

from __future__ import unicode_literals
"""
Transactions are defined as collection of classes, a ModelWrapper represents collection of Document
objects for a transaction with main and children.

Group actions like save, etc are performed on doclists
"""

import webnotes
from webnotes.utils import cint
from webnotes.model.doc import Document

class ModelWrapper:
	"""
	Collection of Documents with one parent and multiple children
	"""
	def __init__(self, dt=None, dn=None):
		self.docs = []
		self.obj = None
		self.to_docstatus = 0
		if dt and dn:
			self.load_from_db(dt, dn)
		if isinstance(dt, list):
			self.set_doclist(dt)

	def load_from_db(self, dt=None, dn=None, prefix='tab'):
		"""
			Load doclist from dt
		"""
		from webnotes.model.doc import Document, getchildren

		if not dt: dt = self.doc.doctype
		if not dn: dn = self.doc.name

		doc = Document(dt, dn, prefix=prefix)

		# get all children types
		tablefields = webnotes.model.meta.get_table_fields(dt)

		# load chilren
		doclist = webnotes.doclist([doc,])
		for t in tablefields:
			doclist += getchildren(doc.name, t[0], t[1], dt, prefix=prefix)

		self.set_doclist(doclist)

	def __iter__(self):
		"""
			Make this iterable
		"""
		return self.docs.__iter__()

	def from_compressed(self, data, docname):
		"""
			Expand called from client
		"""
		from webnotes.model.utils import expand
		self.docs = expand(data)
		self.set_doclist(self.docs)
		
	def set_doclist(self, docs):
		for i, d in enumerate(docs):
			if isinstance(d, dict):
				docs[i] = Document(fielddata=d)
		
		self.docs = self.doclist = webnotes.doclist(docs)
		self.doc, self.children = docs[0], webnotes.doclist(docs[1:])
		if self.obj:
			self.obj.doclist = self.doclist
			self.obj.doc = self.doc

	def make_obj(self):
		"""
			Create a DocType object
		"""
		if self.obj: return self.obj

		from webnotes.model.code import get_obj
		self.obj = get_obj(doc=self.doc, doclist=self.doclist)
		return self.obj

	def to_dict(self):
		"""
			return as a list of dictionaries
		"""
		return [d.fields for d in self.docs]

	def check_if_latest(self):
		"""
			Raises exception if the modified time is not the same as in the database
		"""
		from webnotes.model.meta import is_single

		if (not is_single(self.doc.doctype)) and (not cint(self.doc.fields.get('__islocal'))):
			tmp = webnotes.conn.sql("""
				SELECT modified FROM `tab%s` WHERE name="%s" for update"""
				% (self.doc.doctype, self.doc.name))

			if not tmp:
				webnotes.msgprint("""This record does not exist. Please refresh.""", raise_exception=1)

			if tmp and str(tmp[0][0]) != str(self.doc.modified):
				webnotes.msgprint("""
				Document has been modified after you have opened it.
				To maintain the integrity of the data, you will not be able to save your changes.
				Please refresh this document. [%s/%s]""" % (tmp[0][0], self.doc.modified), raise_exception=1)

	def check_permission(self):
		"""
			Raises exception if permission is not valid
		"""
		if not self.doc.check_perm(verbose=1):
			webnotes.msgprint("Not enough permission to save %s" % 
				self.doc.doctype, raise_exception=1)

	def check_links(self):
		"""
			Checks integrity of links (throws exception if links are invalid)
		"""
		ref, err_list = {}, []
		for d in self.docs:
			if not ref.get(d.doctype):
				ref[d.doctype] = d.make_link_list()

			err_list += d.validate_links(ref[d.doctype])

		if err_list:
			webnotes.msgprint("""[Link Validation] Could not find the following values: %s.
			Please correct and resave. Document Not Saved.""" % ', '.join(err_list), raise_exception=1)

	def update_timestamps_and_docstatus(self):
		"""
			Update owner, creation, modified_by, modified, docstatus
		"""
		from webnotes.utils import now
		ts = now()
		user = webnotes.__dict__.get('session', {}).get('user') or 'Administrator'

		for d in self.docs:
			if self.doc.fields.get('__islocal'):
				d.owner = user
				d.creation = ts

			d.modified_by = user
			d.modified = ts
			if d.docstatus != 2 and self.to_docstatus >= d.docstatus: # don't update deleted
				d.docstatus = self.to_docstatus

	def prepare_for_save(self, check_links):
		"""
			Set owner, modified etc before saving
		"""
		self.check_if_latest()
		self.check_permission()
		if check_links:
			self.check_links()
		self.update_timestamps_and_docstatus()
		self.update_parent_info()
		
	def update_parent_info(self):
		idx_map = {}
		for i, d in enumerate(self.doclist[1:]):
			if d.parentfield:
				d.parenttype = self.doc.doctype
				d.parent = self.doc.name
			if not d.idx:
				d.idx = idx_map.setdefault(d.parentfield, 0) + 1
			
			idx_map[d.parentfield] = d.idx

	def run_method(self, method):
		"""
		Run a method and custom_method
		"""
		self.make_obj()
		if hasattr(self.obj, method):
			getattr(self.obj, method)()
		if hasattr(self.obj, 'custom_' + method):
			getattr(self.obj, 'custom_' + method)()

		trigger(method, self.obj.doc)
		
		self.set_doclist(self.obj.doclist)

	def save_main(self):
		"""
			Save the main doc
		"""
		try:
			self.doc.save(cint(self.doc.fields.get('__islocal')))
		except NameError, e:
			webnotes.msgprint('%s "%s" already exists' % (self.doc.doctype, self.doc.name))

			# prompt if cancelled
			if webnotes.conn.get_value(self.doc.doctype, self.doc.name, 'docstatus')==2:
				webnotes.msgprint('[%s "%s" has been cancelled]' % (self.doc.doctype, self.doc.name))
			webnotes.errprint(webnotes.utils.getTraceback())
			raise e

	def save_children(self):
		"""
			Save Children, with the new parent name
		"""
		child_map = {}
		for d in self.children:
			if (d.fields.has_key('parent') and d.fields.get('parent')) or \
					(d.fields.has_key("parentfield") and d.fields.get("parentfield")):
				# if d.parent:
				d.parent = self.doc.name # rename if reqd
				d.parenttype = self.doc.doctype
				
				d.save(new = cint(d.fields.get('__islocal')))
			
			child_map.setdefault(d.doctype, []).append(d.name)
		
		# delete all children in database that are not in the child_map
		
		# get all children types
		tablefields = webnotes.model.meta.get_table_fields(self.doc.doctype)
				
		for dt in tablefields:
			cnames = child_map.get(dt[0]) or []
			if cnames:
				webnotes.conn.sql("""delete from `tab%s` where parent=%s and parenttype=%s and
					name not in (%s)""" % (dt[0], '%s', '%s', ','.join(['%s'] * len(cnames))), 
						tuple([self.doc.name, self.doc.doctype] + cnames))
			else:
				webnotes.conn.sql("""delete from `tab%s` where parent=%s and parenttype=%s""" \
					% (dt[0], '%s', '%s'), (self.doc.name, self.doc.doctype))

	def save(self, check_links=1):
		"""
			Save the list
		"""
		self.prepare_for_save(check_links)
		self.run_method('validate')
		self.save_main()
		self.save_children()
		self.run_method('on_update')

	def submit(self):
		"""
			Save & Submit - set docstatus = 1, run "on_submit"
		"""
		if self.doc.docstatus != 0:
			webnotes.msgprint("Only draft can be submitted", raise_exception=1)
		self.to_docstatus = 1
		self.save()
		self.run_method('on_submit')

	def cancel(self):
		"""
			Cancel - set docstatus 2, run "on_cancel"
		"""
		if self.doc.docstatus != 1:
			webnotes.msgprint("Only submitted can be cancelled", raise_exception=1)
		self.to_docstatus = 2
		self.prepare_for_save(1)
		self.save_main()
		self.save_children()
		self.run_method('on_cancel')

	def update_after_submit(self):
		"""
			Update after submit - some values changed after submit
		"""
		if self.doc.docstatus != 1:
			webnotes.msgprint("Only to called after submit", raise_exception=1)
		self.to_docstatus = 1
		self.prepare_for_save(1)
		self.save_main()
		self.save_children()
		self.run_method('on_update_after_submit')

# clone

def clone(source_wrapper):
	""" Copy previous invoice and change dates"""
	if isinstance(source_wrapper, list):
		source_wrapper = ModelWrapper(source_wrapper)
	
	new_wrapper = ModelWrapper(source_wrapper.doclist.copy())
	new_wrapper.doc.fields.update({
		"amended_from": None,
		"amendment_date": None,
	})
	
	for d in new_wrapper.doclist:
		d.fields.update({
			"name": None,
			"__islocal": 1,
			"docstatus": 0,
		})
	
	return new_wrapper


def trigger(method, doc):
	"""trigger doctype events"""
	try:
		import startup.event_handlers
	except ImportError:
		return
		
	if hasattr(startup.event_handlers, method):
		getattr(startup.event_handlers, method)(doc)
		
	if hasattr(startup.event_handlers, 'doclist_all'):
		startup.event_handlers.doclist_all(doc, method)

# for bc
def getlist(doclist, parentfield):
	"""
		Return child records of a particular type
	"""
	import webnotes.model.utils
	return webnotes.model.utils.getlist(doclist, parentfield)

def copy_doclist(doclist, no_copy = []):
	"""
		Make a copy of the doclist
	"""
	import webnotes.model.utils
	return webnotes.model.utils.copy_doclist(doclist, no_copy)

