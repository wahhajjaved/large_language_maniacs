# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt 

from __future__ import unicode_literals

import frappe, os
from frappe.core.page.data_import_tool.data_import_tool import import_doclist, export_fixture, export_csv

def sync_fixtures():
	for app in frappe.get_installed_apps():
		if os.path.exists(frappe.get_app_path(app, "fixtures")):
			for fname in os.listdir(frappe.get_app_path(app, "fixtures")):
				if fname.endswith(".json") or fname.endswith(".csv"):
					import_doclist(frappe.get_app_path(app, "fixtures", fname), ignore_links=True, overwrite=True)


def export_fixtures():
	for app in frappe.get_installed_apps():
		for fixture in frappe.get_hooks("fixture", app_name=app):
			print "Exporting " + fixture
			if frappe.db.get_value("DocType", fixture, "issingle"):
				export_fixture(fixture, fixture, app)
			else:
				export_csv(fixture, frappe.get_app_path(app, "fixtures", frappe.scrub(fixture) + ".csv"))
