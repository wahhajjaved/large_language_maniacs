# Please edit this list and import only required elements
import webnotes
from webnotes.utils import cint

sql = webnotes.conn.sql

	
# -----------------------------------------------------------------------------------------

class DocType:
	def __init__(self,d,dl):
		self.doc, self.doclist = d,dl

	def autoname(self):
		self.doc.name = self.doc.criteria_name.lower().replace('(','').replace(')', '')\
			.replace('.','').replace(',','').replace('"', '').replace("'",'').replace(' ', '_')\
			.replace('/', '-')
		
		# for duplicates
		if sql("select name from `tabSearch Criteria` where name = %s", self.doc.name):
			m = sql("select name from `tabSearch Criteria` where name like '%s%%' order by name desc limit 1" % self.doc.name)[0][0]
			self.doc.name = self.doc.name + str(cint(m[-1]) + 1)

	def set_module(self):
		if not self.doc.module:
			doctype_module = sql("select module from tabDocType where name = '%s'" % (self.doc.doc_type))
			webnotes.conn.set(self.doc,'module',doctype_module and doctype_module[0][0] or 'NULL')

	def validate(self):
		if sql("select name from `tabSearch Criteria` where criteria_name=%s and name!=%s", (self.doc.criteria_name, self.doc.name)):
			webnotes.msgprint("Criteria Name '%s' already used, please use another name" % self.doc.criteria_name, raise_exception = 1)

	def on_update(self):
		self.set_module()
		self.export_doc()
	
	def export_doc(self):
		# export
		if self.doc.standard == 'Yes' and getattr(webnotes.defs, 'developer_mode', 0) == 1:
			from webnotes.modules.export_module import export_to_files
			export_to_files(record_list=[['Search Criteria', self.doc.name]])

	# patch to rename search criteria from old style numerical to
	# new style based on criteria name
	def rename(self):
		old_name = self.doc.name
		
		if not self.doc.module:
			self.set_module()
		
		self.autoname()
		sql("update `tabSearch Criteria` set name=%s where name=%s", (self.doc.name, old_name))
		
	def rename_export(self, old_name):
				
		# export the folders
		self.export_doc()
		import os, shutil
		from webnotes.modules import get_module_path, scrub
		
		path = os.path.join(get_module_path(self.doc.module), 'search_criteria', scrub(old_name))
		
		# copy py/js files
		self.copy_file(path, scrub(old_name), '.py')
		self.copy_file(path, scrub(old_name), '.js')
		self.copy_file(path, scrub(old_name), '.sql')
				
	def copy_file(self, path, old_name, extn):
		import os
		from webnotes.modules import get_module_path, scrub

		if os.path.exists(os.path.join(path, old_name + extn)):
			os.system('cp %s %s' % (os.path.join(path, old_name + extn), \
			os.path.join(get_module_path(self.doc.module), 'search_criteria', scrub(self.doc.name), scrub(self.doc.name) + extn)))
	
