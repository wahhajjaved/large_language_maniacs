from __future__ import unicode_literals
import json
import frappe
import frappe.defaults
from frappe.desk.star import _toggle_star

def execute():
	for user in frappe.get_all("User"):
		username = user["name"]
		bookmarks = frappe.db.get_default("_bookmarks", username)

		if not bookmarks:
			continue

		if isinstance(bookmarks, basestring):
			bookmarks = json.loads(bookmarks)

		for opts in bookmarks:
			route = (opts.get("route") or "").strip("#/ ")

			if route and route.startswith("Form"):
				try:
					view, doctype, docname = opts["route"].split("/")
				except ValueError:
					continue

				if frappe.db.exists(doctype, docname):
					if doctype=="DocType" or frappe.get_meta(doctype).issingle:
						continue
					_toggle_star(doctype, docname, add="Yes", user=username)
