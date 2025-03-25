# REMEMBER to update this
# ========================

last_patch = 357

#-------------------------------------------

def execute(patch_no):
	import webnotes
	from webnotes.modules.module_manager import reload_doc

	from webnotes.model.code import get_obj
	sql = webnotes.conn.sql
	from webnotes.utils import cint, cstr, flt
	from webnotes.model.doc import Document
	from webnotes.model import delete_doc

	if patch_no == 301:
		from patches.delivery_billing_status_patch import run_patch
		run_patch()
	elif patch_no == 302:
		sql("update `tabDocField` set no_copy = 1 where fieldname = 'naming_series'")
	elif patch_no == 303:
		pass
	elif patch_no == 304:
		sql("delete from `tabDocField` where parent = 'company' and label = 'Trash Company' and fieldtype = 'button'")
		reload_doc('setup', 'doctype', 'company')
	elif patch_no == 305:
		sql("update `tabDocField` set options = 'link:Company' where options='link:Company' and fieldname='company' and fieldtype='Select'")
	elif patch_no == 306:
		sql("update `tabDocField` set options = '\nAccount\nCompany\nCustomer\nSupplier\nEmployee\nWarehouse\nItem' where parent = 'Rename Tool' and fieldname = 'select_doctype'")
		sql("update `tabDocField` set options = 'link:Item' where parent = 'Raw Materials Supplied' and fieldname = 'po_item'")
		sql("update `tabDocField` set options = 'Sales Order' where parent = 'Indent Detail' and fieldname = 'sales_order_no'")
		sql("update `tabDocField` set options = 'link:Company', fieldtype = 'Select' where parent = 'Stock Ledger Entry' and fieldname = 'company'")
		reload_doc('utilities', 'doctype', 'rename_tool')
	elif patch_no == 307:
		sql("delete from `tabDocField` where parent = 'company' and label = 'Trash Company' and fieldtype = 'Button'")
		reload_doc('setup', 'doctype', 'company')
	elif patch_no == 308:
		sql("update `tabDocField` set reqd = 0 where fieldname = 'select_item' and parent = 'Property Setter'")
	elif patch_no == 309:
		sql("delete from `tabDocField` where fieldname = 'item_attachments_details' and parent = 'Item'")
		sql("delete from `tabModule Def Item` where parent = 'Stock' and doc_name = 'Landed Cost Wizard'")
	elif patch_no == 310:
		from erpnext_structure_cleanup import run_patches
		run_patches()
	elif patch_no == 311:
		sql("update `tabDocField` set reqd = 0 where fieldname = 'select_item' and parent = 'Property Setter'")
		#reload_doc('core', 'doctype', 'property_setter')
	elif patch_no == 312:
		sql("delete from `tabSessions`")
		sql("delete from `__SessionCache`")
	elif patch_no == 313:
		dt = ['GL Entry', 'Stock Ledger Entry']
		for t in dt:
			rec = sql("select voucher_type, voucher_no, ifnull(is_cancelled, 'No') from `tab%s` where modified >= '2011-07-06 10:00:00' group by voucher_no" % t)
			for d in rec:
				sql("update `tab%s` set docstatus = %s where name = '%s'" % (d[0], d[2]=='No' and 1 or 2, d[1]))

		other_dt = ['Enquiry', 'Quotation', 'Sales Order', 'Indent', 'Purchase Order', 'Production Order', 'Customer Issue', 'Installation Note']
		for dt in other_dt:
			rec = sql("select name, status from `tab%s` where modified >= '2011-07-06 10:00:00'" % dt)
			for r in rec:
				sql("update `tab%s` set docstatus = %s where name = '%s'" % (dt, (r[1] in ['Submitted', 'Closed'] and 1 or r[1]=='Cancelled' and 2 or 0), r[0]))


		dt_list = ['Delivery Note', 'Purchase Receipt']
		for dt in dt_list:
			sql("update `tab%s` set status = 'Submitted' where docstatus = 1 and modified >='2011-07-06 10:00:00'" % dt)
			sql("update `tab%s` set status = 'Cancelled' where docstatus = 2 and modified >='2011-07-06 10:00:00'" % dt)

		dt_list = ['Enquiry', 'Quotation', 'Sales Order', 'Indent', 'Purchase Order', 'Production Order', 'Customer Issue', 'Installation Note', 'Receivable Voucher', 'Payable Voucher', 'Delivery Note', 'Purchase Receipt', 'Journal Voucher', 'Stock Entry']
		for d in dt_list:
			tbl = sql("select options from `tabDocField` where fieldtype = 'Table' and parent = '%s'" % d)
			for t in tbl:
				sql("update `tab%s` t1, `tab%s` t2 set t1.docstatus = t2.docstatus where t1.parent = t2.name" % (t[0], d))

	elif patch_no == 314:
		# delete double feed
		sql("delete from tabFeed where subject like 'New %'")
	elif patch_no == 315:
		# delete double feed
		sql("delete from tabFeed where doc_name like 'New %'")
		reload_doc('core', 'doctype', 'property_setter')

		from webnotes.model.doc import Document
		m = Document('Module Def Role')
		m.role = 'All'
		m.parent = 'Home'
		m.parenttype = 'Module Def'
		m.parentfield = 'roles'
		m.save(1)
	elif patch_no == 316:
		pass
	elif patch_no == 317:
		sql("update `tabPage` set name = 'profile-settings' where page_name = 'Profile Settings'")
	elif patch_no == 318:
		reload_doc('utilities', 'doctype', 'bulk_rename_tool')
	elif patch_no == 319:
		sql("delete from tabFeed where doc_name like 'New %'")
	elif patch_no == 320:
		reload_doc('setup', 'doctype', 'series_detail')
	elif patch_no == 321:
		reload_doc('hr','doctype','leave_application')
	elif patch_no == 322:
		sql("delete from `tabDocField` where parent = 'Leave Application' and fieldname = 'latter_head'")
	elif patch_no == 323:
		reload_doc('stock', 'doctype', 'stock_entry')
		sql("update `tabDocField` set options = 'get_stock_and_rate' where parent = 'Stock Entry' and label = 'Get Stock and Rate'")
		sql("delete from `tabDocField` where label = 'Get Current Stock' and parent = 'Stock Entry'")
	elif patch_no == 324:
		sql("delete from `tabDocField` where fieldname = 'test_field' and parent = 'Customer'")
	elif patch_no == 325:
		sql("update `tabDocField` set fieldtype = 'Data' where parent = 'Salary Slip' and fieldname = 'total_days_in_month'")
		reload_doc('hr', 'doctype', 'salary_slip')
	elif patch_no == 326:
		# load the new billing page
		if cint(webnotes.conn.get_value('Control Panel',None,'sync_with_gateway')):
			reload_doc('server_tools','page','billing')
	elif patch_no == 327:
		# patch for support email settings now moved to email settings
		reload_doc('setup','doctype','email_settings')

		# map fields from support to email settings
		field_map = {
			'support_email': 'email',
			'support_host':'host',
			'support_username': 'username',
			'support_password': 'password',
			'support_use_ssl': 'use_ssl',
			'sync_support_mails': 'integrate_incoming',
			'signature': 'support_signature'
		}

		for key in field_map:
			webnotes.conn.set_value('Email Settings',None,key, \
				webnotes.conn.get_value('Support Email Settings',None,field_map[key]))

		# delete support email settings
		delete_doc('DocType', 'Support Email Settings')

		reload_doc('support','doctype','support_ticket')
		sql("delete from tabDocField where fieldname='problem_description' and parent='Support Ticket'")
	elif patch_no == 328:
		if webnotes.conn.get_value('Control Panel', None, 'account_id') != 'axjanak2011':
			sql("delete from `tabDocField` where fieldname = 'supplier_status' and parent = 'Supplier'")
	elif patch_no == 329:
		reload_doc('utilities', 'doctype', 'rename_tool')
		reload_doc('utilities', 'doctype', 'bulk_rename_tool')
	elif patch_no == 330:
		reload_doc('accounts', 'doctype', 'lease_agreement')
		reload_doc('accounts', 'doctype', 'lease_installment')

		reload_doc('accounts', 'search_criteria', 'lease_agreement_list')
		reload_doc('accounts', 'search_criteria', 'lease_monthly_future_installment_inflows')
		reload_doc('accounts', 'search_criteria', 'lease_overdue_age_wise')
		reload_doc('accounts', 'search_criteria', 'lease_over_due_list')
		reload_doc('accounts', 'search_criteria', 'lease_receipts_client_wise')
		reload_doc('accounts', 'search_criteria', 'lease_receipt_summary_year_to_date')
		reload_doc('accounts', 'search_criteria', 'lease_yearly_future_installment_inflows')

		reload_doc('accounts', 'Module Def', 'Accounts')
	elif patch_no == 331:
		p = get_obj('Patch Util')
		# permission
		p.add_permission('Lease Agreement', 'Accounts Manager', 0, read = 1, write=1,submit=1, cancel=1,amend=1)
		p.add_permission('Lease Agreement', 'Accounts Manager', 1, read = 1)
	elif patch_no == 332:
		sql("update `tabDocField` set permlevel=1, hidden = 1 where parent = 'Bulk Rename Tool' and fieldname = 'file_list'")
	elif patch_no == 333:
		sql("update `tabDocPerm` set `create`  =1 where role = 'Accounts Manager' and parent = 'Lease Agreement'")

		p = get_obj('Patch Util')
		p.add_permission('DocType Mapper', 'System Manager', 0, read = 1, write=1, create=1)
		p.add_permission('Role', 'System Manager', 0, read = 1, write=1, create=1)
		p.add_permission('Print Format', 'System Manager', 0, read = 1, write=1, create=1)
	elif patch_no == 334:
		reload_doc('knowledge_base', 'doctype', 'answer')
	elif patch_no == 335:
		for dt in ['Account', 'Cost Center', 'Territory', 'Item Group', 'Customer Group']:
			sql("update `tabDocField` set fieldtype = 'Link', options = %s where fieldname = 'old_parent' and parent = %s", (dt, dt))
	elif patch_no == 336:
		reload_doc('server_tools','page','billing')
	elif patch_no == 337:
		item_list = webnotes.conn.sql("""SELECT name, description_html
									FROM tabItem""")
		if item_list:
			for item, html in item_list:
				if html and "getfile" in html and "acx" in html:
					ac_id = webnotes.conn.sql("""SELECT value FROM `tabSingles` WHERE doctype='Control Panel' AND field='account_id'""")
					sp_acx = html.split("acx=")
					l_acx = len(sp_acx)
					if l_acx > 1:
						for i in range(l_acx-1):
							sp_quot = sp_acx[i+1].split('"')
							if len(sp_quot) > 1: sp_quot[0] = str(ac_id[0][0])
							sp_acx[i+1] = '"'.join(sp_quot)
					html = "acx=".join(sp_acx)
					webnotes.conn.sql("""UPDATE tabItem SET description_html=%s WHERE name=%s""", (html, item))
	elif patch_no == 338:
		# Patch for billing status based on amount
		# reload so and dn
		reload_doc('selling','doctype','sales_order')
		reload_doc('stock','doctype','delivery_note')

		# delete billed_qty field
		sql("delete from `tabDocField` where fieldname = 'billed_qty' and parent in ('Sales Order Detail', 'Delivery Note Detail')")

		# update billed amt in item table in so and dn
		sql("""	update `tabSales Order Detail` so
				set billed_amt = (select sum(amount) from `tabRV Detail` where `so_detail`= so.name and docstatus=1 and parent not like 'old%%'), modified = now()""")

		sql(""" update `tabDelivery Note Detail` dn
				set billed_amt = (select sum(amount) from `tabRV Detail` where `dn_detail`= dn.name and docstatus=1 and parent not like 'old%%'), modified = now()""")

		# calculate % billed based on item table
		sql("""	update `tabSales Order` so
				set per_billed = (select sum(if(amount > ifnull(billed_amt, 0), billed_amt, amount))/sum(amount)*100 from `tabSales Order Detail` where parent = so.name), modified = now()""")

		sql("""	update `tabDelivery Note` dn
				set per_billed = (select sum(if(amount > ifnull(billed_amt, 0), billed_amt, amount))/sum(amount)*100 from `tabDelivery Note Detail` where parent = dn.name), modified = now()""")

		# update billing status based on % billed
		sql("""update `tabSales Order` set billing_status = if(ifnull(per_billed,0) < 0.001, 'Not Billed',
				if(per_billed >= 99.99, 'Fully Billed', 'Partly Billed'))""")
		sql("""update `tabDelivery Note` set billing_status = if(ifnull(per_billed,0) < 0.001, 'Not Billed',
				if(per_billed >= 99.99, 'Fully Billed', 'Partly Billed'))""")

		# update name of questions page
		sql("update tabPage set name='questions' where name='Questions'")
		sql("update tabPage set name='question-view' where name='Question View'")
	elif patch_no == 339:
		reload_doc('production','doctype','bill_of_materials')
	elif patch_no == 340:
		sql("update `tabDocField` set permlevel = 0 where (fieldname in ('process', 'production_order', 'fg_completed_qty') or label = 'Get Items') and parent = 'Stock Entry'")
	elif patch_no == 341:
		reload_doc('stock','doctype','delivery_note')
		reload_doc('stock','doctype','item')
		reload_doc('selling','doctype','quotation')
		reload_doc('stock','Print Format','Delivery Note Packing List Wise')

		if not sql("select format from `tabDocFormat` where name = 'Delivery Note Packing List Wise' and parent = 'Delivery Note'"):
			from webnotes.model.doc import addchild
			dt_obj = get_obj('DocType', 'Delivery Note', with_children = 1)
			ch = addchild(dt_obj.doc, 'formats', 'DocFormat', 1)
			ch.format = 'Delivery Note Packing List Wise'
			ch.save(1)
	elif patch_no == 342:
		sql("update `tabDocField` set permlevel = 0 where parent = 'Stock Entry Detail' and fieldname in ('s_warehouse', 't_warehouse', 'fg_item')")
	elif patch_no == 343:
		reload_doc('stock','doctype','item_customer_detail')
	elif patch_no == 344:
		sql("delete from `tabDocFormat` where ifnull(format, '') = '' and parent = 'Delivery Note'")
		reload_doc('stock', 'doctype', 'delivery_note_detail')
		reload_doc('stock', 'doctype', 'item_customer_detail')
	elif patch_no == 345:
		# rerun 343 (merge confict)
		reload_doc('stock','doctype','item_customer_detail')
		sql("delete from `tabModule Def Item` where display_name = 'Salary Slip Control Panel' and parent = 'HR'")
		reload_doc('hr','Module Def','HR')
	elif patch_no == 346:
		pass
	elif patch_no == 347:
		sql("delete from `tabField Mapper Detail` where from_field = to_field and map = 'Yes' and ifnull(checking_operator, '') = ''")
	elif patch_no == 348:
		sql("update `tabStock Ledger Entry` set is_cancelled = 'No' where voucher_type = 'Serial No'")
	elif patch_no == 349:
		delete_doc('Custom Script', 'Update Series-Server')
		delete_doc('Custom Script', 'Profile-Client')
		delete_doc('Custom Script', 'Event-Client')
		delete_doc('Custom Script', 'File-Server')

		# reload profile with new fields for security
		delete_doc('DocType', 'Profile')
		reload_doc('core', 'doctype', 'profile')
	elif patch_no == 350:
		reload_doc('stock', 'doctype', 'delivery_note_detail')
		reload_doc('stock', 'doctype', 'item_customer_detail')
	elif patch_no == 351:
		reload_doc('home', 'page', 'dashboard')
	elif patch_no == 352:
		reload_doc('stock','doctype','delivery_note')
		reload_doc('stock','doctype','item')
		reload_doc('selling','doctype','quotation')
		reload_doc('stock','Print Format','Delivery Note Packing List Wise')

		if not sql("select format from `tabDocFormat` where name = 'Delivery Note Packing List Wise' and parent = 'Delivery Note'"):
			from webnotes.model.doc import addchild
			dt_obj = get_obj('DocType', 'Delivery Note', with_children = 1)
			ch = addchild(dt_obj.doc, 'formats', 'DocFormat', 1)
			ch.format = 'Delivery Note Packing List Wise'
			ch.save(1)
	elif patch_no == 353:
		reload_doc('hr', 'doctype', 'salary_manager')
	elif patch_no == 354:
		reload_doc('setup', 'doctype','features_setup')
		reload_doc('stock','doctype','item')
		sql("update tabDocField set label='Produced Qty',description='Updated after finished goods are transferred to FG Warehouse through Stock Entry' where parent='Production Order' and fieldname='produced_qty'")
		rs = sql("select fieldname from tabDocField where parent='Features Setup' and fieldname is not null")
		from webnotes.model.doc import Document
		m = Document('Features Setup')
		for d in rs:
			m.fields[d[0]] = 1
		m.save()
	elif patch_no == 355:
		reload_doc('hr', 'doctype', 'salary_slip')
		delete_doc('DocType', 'Salary Control Panel')
	elif patch_no == 356:
		reload_doc('doctype', 'core', 'doctype')
		sql("update `tabDocType` set default_print_format = 'Standard' where name = 'Delivery Note'")
	elif patch_no == 357:
		sql("delete from `tabDocField` where (fieldname in ('client_string', 'server_code_error', 'server_code_compiled', 'server_code', 'server_code_core', 'client_script', 'client_script_core', 'dt_template', 'change_log') or label = 'Template') and parent = 'DocType'")
