# -*- coding: utf-8 -*-
# Copyright (c) 2020, Rohit Industries Ltd. and contributors
# For license information, please see license.txt

#This Scheduled task deletes all the Unneeded Prepared Reports and their Associated Files which are older than 30 days

from __future__ import unicode_literals
import frappe
from frappe.utils.file_manager import delete_file_from_filesystem

def execute():
	set_days = 300
	query = """SELECT name, creation FROM `tabPrepared Report` 
		WHERE docstatus = 0 AND creation < (DATE_SUB(CURDATE(), INTERVAL %s DAY)) ORDER BY creation"""%(set_days)

	pr_list = frappe.db.sql(query , as_list=1)
	sno = 0
	for pr in pr_list:
		sno += 1
		print(str(sno) + " Deleting Prepared Report# " + pr[0])
		#frappe.db.sql("""DELETE FROM `tabPrepared Report` WHERE name = '%s'"""%(pr[0]))
		print ("Deleting File Data for Prepared Report# " + pr[0])
		file_name = frappe.db.sql("""SELECT name, file_name, is_private FROM `tabFile` 
			WHERE attached_to_doctype = 'Prepared Report' 
			AND attached_to_name = '%s' """%(pr[0]), as_list=1)

		frappe.db.sql("""DELETE FROM `tabFile` WHERE attached_to_doctype = 'Prepared Report' 
			AND attached_to_name = '%s'"""%(pr[0]))
		print ("Deleting the Actual File from System for Prepared Report# " + pr[0])
		file_doc_frappe = frappe.get_doc('File', file_name[0])
		delete_file_from_filesystem(file_doc_frappe)



		#frappe.delete_doc('Prepared Report', pr[0])
		if sno%50==0:
			print ("Committing Changes Current Files Done = " + str(sno))
			frappe.db.commit()