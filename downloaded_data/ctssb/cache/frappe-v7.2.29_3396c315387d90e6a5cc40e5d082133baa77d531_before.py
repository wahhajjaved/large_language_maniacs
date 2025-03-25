# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt
"""
globals attached to frappe module
+ some utility functions that should probably be moved
"""
from __future__ import unicode_literals

from werkzeug.local import Local, release_local
import os, importlib, inspect, logging, json

# public
from frappe.__version__ import __version__
from .exceptions import *
from .utils.jinja import get_jenv, get_template, render_template

local = Local()

class _dict(dict):
	"""dict like object that exposes keys as attributes"""
	def __getattr__(self, key):
		ret = self.get(key)
		if not ret and key.startswith("__"):
			raise AttributeError()
		return ret
	def __setattr__(self, key, value):
		self[key] = value
	def __getstate__(self):
		return self
	def __setstate__(self, d):
		self.update(d)
	def update(self, d):
		"""update and return self -- the missing dict feature in python"""
		super(_dict, self).update(d)
		return self
	def copy(self):
		return _dict(dict(self).copy())

def _(msg):
	"""Returns translated string in current lang, if exists."""
	if local.lang == "en":
		return msg

	from frappe.translate import get_full_dict
	return get_full_dict(local.lang).get(msg, msg)

def get_lang_dict(fortype, name=None):
	"""Returns the translated language dict for the given type and name.

	 :param fortype: must be one of `doctype`, `page`, `report`, `include`, `jsfile`, `boot`
	 :param name: name of the document for which assets are to be returned."""
	if local.lang=="en":
		return {}
	from frappe.translate import get_dict
	return get_dict(fortype, name)

def set_user_lang(user, user_language=None):
	"""Guess and set user language for the session. `frappe.local.lang`"""
	from frappe.translate import get_user_lang
	local.lang = get_user_lang(user)

# local-globals
db = local("db")
conf = local("conf")
form = form_dict = local("form_dict")
request = local("request")
request_method = local("request_method")
response = local("response")
session = local("session")
user = local("user")
flags = local("flags")

error_log = local("error_log")
debug_log = local("debug_log")
message_log = local("message_log")

lang = local("lang")

def init(site, sites_path=None):
	"""Initialize frappe for the current site. Reset thread locals `frappe.local`"""
	if getattr(local, "initialised", None):
		return

	if not sites_path:
		sites_path = '.'

	local.error_log = []
	local.message_log = []
	local.debug_log = []
	local.flags = _dict({})
	local.rollback_observers = []
	local.test_objects = {}

	local.site = site
	local.sites_path = sites_path
	local.site_path = os.path.join(sites_path, site)

	local.request_method = request.method if request else None
	local.request_ip = None
	local.response = _dict({"docs":[]})

	local.conf = _dict(get_site_config())
	local.lang = local.conf.lang or "en"

	local.module_app = None
	local.app_modules = None

	local.user = None
	local.role_permissions = {}

	local.jenv = None
	local.jloader =None
	local.cache = {}

	setup_module_map()

	local.initialised = True

def connect(site=None, db_name=None):
	"""Connect to site database instance.

	:param site: If site is given, calls `frappe.init`.
	:param db_name: Optional. Will use from `site_config.json`."""
	from database import Database
	if site:
		init(site)
	local.db = Database(user=db_name or local.conf.db_name)
	local.form_dict = _dict()
	local.session = _dict()
	set_user("Administrator")

def get_site_config(sites_path=None, site_path=None):
	"""Returns `site_config.json` combined with `sites/common_site_config.json`.
	`site_config` is a set of site wide settings like database name, password, email etc."""
	config = {}

	sites_path = sites_path or getattr(local, "sites_path", None)
	site_path = site_path or getattr(local, "site_path", None)

	if sites_path:
		common_site_config = os.path.join(sites_path, "common_site_config.json")
		if os.path.exists(common_site_config):
			config.update(get_file_json(common_site_config))

	if site_path:
		site_config = os.path.join(site_path, "site_config.json")
		if os.path.exists(site_config):
			config.update(get_file_json(site_config))

	return _dict(config)

def destroy():
	"""Closes connection and releases werkzeug local."""
	if db:
		db.close()

	release_local(local)

# memcache
redis_server = None
def cache():
	"""Returns memcache connection."""
	global redis_server
	if not redis_server:
		from frappe.utils.redis_wrapper import RedisWrapper
		redis_server = RedisWrapper.from_url(conf.get("cache_redis_server") or "redis://localhost")
	return redis_server

def get_traceback():
	"""Returns error traceback."""
	import utils
	return utils.get_traceback()

def errprint(msg):
	"""Log error. This is sent back as `exc` in response.

	:param msg: Message."""
	from utils import cstr
	if not request or (not "cmd" in local.form_dict):
		print cstr(msg)

	error_log.append(cstr(msg))

def log(msg):
	"""Add to `debug_log`.

	:param msg: Message."""
	if not request:
		if conf.get("logging") or False:
			print repr(msg)

	from utils import cstr
	debug_log.append(cstr(msg))

def msgprint(msg, small=0, raise_exception=0, as_table=False):
	"""Print a message to the user (via HTTP response).
	Messages are sent in the `__server_messages` property in the
	response JSON and shown in a pop-up / modal.

	:param msg: Message.
	:param small: [optional] Show as a floating message in the footer.
	:param raise_exception: [optional] Raise given exception and show message.
	:param as_table: [optional] If `msg` is a list of lists, render as HTML table.
	"""
	def _raise_exception():
		if raise_exception:
			if flags.rollback_on_exception:
				db.rollback()
			import inspect
			if inspect.isclass(raise_exception) and issubclass(raise_exception, Exception):
				raise raise_exception, msg
			else:
				raise ValidationError, msg

	if flags.mute_messages:
		_raise_exception()
		return

	from utils import cstr
	if as_table and type(msg) in (list, tuple):
		msg = '<table border="1px" style="border-collapse: collapse" cellpadding="2px">' + ''.join(['<tr>'+''.join(['<td>%s</td>' % c for c in r])+'</tr>' for r in msg]) + '</table>'

	if flags.print_messages:
		print "Message: " + repr(msg)

	message_log.append((small and '__small:' or '')+cstr(msg or ''))
	_raise_exception()

def throw(msg, exc=ValidationError):
	"""Throw execption and show message (`msgprint`).

	:param msg: Message.
	:param exc: Exception class. Default `frappe.ValidationError`"""
	msgprint(msg, raise_exception=exc)

def create_folder(path, with_init=False):
	"""Create a folder in the given path and add an `__init__.py` file (optional).

	:param path: Folder path.
	:param with_init: Create `__init__.py` in the new folder."""
	from frappe.utils import touch_file
	if not os.path.exists(path):
		os.makedirs(path)

		if with_init:
			touch_file(os.path.join(path, "__init__.py"))

def set_user(username):
	"""Set current user.

	:param username: **User** name to set as current user."""
	from frappe.utils.user import User
	local.session.user = username
	local.session.sid = username
	local.cache = {}
	local.form_dict = _dict()
	local.jenv = None
	local.session.data = _dict()
	local.user = User(username)
	local.role_permissions = {}

def get_request_header(key, default=None):
	"""Return HTTP request header.

	:param key: HTTP header key.
	:param default: Default value."""
	return request.headers.get(key, default)

def sendmail(recipients=(), sender="", subject="No Subject", message="No Message",
		as_markdown=False, bulk=False, ref_doctype=None, ref_docname=None,
		add_unsubscribe_link=False, attachments=None, content=None, doctype=None, name=None, reply_to=None):
	"""Send email using user's default **Email Account** or global default **Email Account**.


	:param recipients: List of recipients.
	:param sender: Email sender. Default is current user.
	:param subject: Email Subject.
	:param message: (or `content`) Email Content.
	:param as_markdown: Convert content markdown to HTML.
	:param bulk: Send via scheduled email sender **Bulk Email**. Don't send immediately.
	:param ref_doctype: (or `doctype`) Append as communication to this DocType.
	:param ref_docname: (or `name`) Append as communication to this document name.
	:param add_unsubscribe_link: Allow user to unsubscribe from these emails.
	:param attachments: List of attachments.
	:param reply_to: Reply-To email id.
	"""

	if bulk:
		import frappe.email.bulk
		frappe.email.bulk.send(recipients=recipients, sender=sender,
			subject=subject, message=content or message, ref_doctype = doctype or ref_doctype,
			ref_docname = name or ref_docname, add_unsubscribe_link=add_unsubscribe_link, attachments=attachments,
			reply_to=reply_to)

	else:
		import frappe.email
		if as_markdown:
			frappe.email.sendmail_md(recipients, sender=sender,
				subject=subject, msg=content or message, attachments=attachments, reply_to=reply_to)
		else:
			frappe.email.sendmail(recipients, sender=sender,
				subject=subject, msg=content or message, attachments=attachments, reply_to=reply_to)

logger = None
whitelisted = []
guest_methods = []
def whitelist(allow_guest=False):
	"""
	Decorator for whitelisting a function and making it accessible via HTTP.
	Standard request will be `/api/method/[path.to.method]`

	:param allow_guest: Allow non logged-in user to access this method.

	Use as:

		@frappe.whitelist()
		def myfunc(param1, param2):
			pass
	"""
	def innerfn(fn):
		global whitelisted, guest_methods
		whitelisted.append(fn)

		if allow_guest:
			guest_methods.append(fn)

		return fn

	return innerfn

def only_for(roles):
	"""Raise `frappe.PermissionError` if the user does not have any of the given **Roles**.

	:param roles: List of roles to check."""
	if not isinstance(roles, (tuple, list)):
		roles = (roles,)
	roles = set(roles)
	myroles = set(get_roles())
	if not roles.intersection(myroles):
		raise PermissionError

def clear_cache(user=None, doctype=None):
	"""Clear **User**, **DocType** or global cache.

	:param user: If user is given, only user cache is cleared.
	:param doctype: If doctype is given, only DocType cache is cleared."""
	import frappe.sessions
	if doctype:
		import frappe.model.meta
		frappe.model.meta.clear_cache(doctype)
		reset_metadata_version()
	elif user:
		frappe.sessions.clear_cache(user)
	else: # everything
		import translate
		frappe.sessions.clear_cache()
		translate.clear_cache()
		reset_metadata_version()
		frappe.local.cache = {}

		for fn in frappe.get_hooks("clear_cache"):
			get_attr(fn)()

	frappe.local.role_permissions = {}

def get_roles(username=None):
	"""Returns roles of current user."""
	if not local.session:
		return ["Guest"]

	return get_user(username).get_roles()

def get_user(username):
	"""Returns `frappe.utils.user.User` instance of given user."""
	from frappe.utils.user import User
	if not username or username == local.session.user:
		return local.user
	else:
		return User(username)

def has_permission(doctype, ptype="read", doc=None, user=None):
	"""Raises `frappe.PermissionError` if not permitted.

	:param doctype: DocType for which permission is to be check.
	:param ptype: Permission type (`read`, `write`, `create`, `submit`, `cancel`, `amend`). Default: `read`.
	:param doc: [optional] Checks User permissions for given doc.
	:param user: [optional] Check for given user. Default: current user."""
	import frappe.permissions
	return frappe.permissions.has_permission(doctype, ptype, doc, user=user)

def is_table(doctype):
	"""Returns True if `istable` property (indicating child Table) is set for given DocType."""
	tables = cache().get_value("is_table")
	if tables==None:
		tables = db.sql_list("select name from tabDocType where ifnull(istable,0)=1")
		cache().set_value("is_table", tables)
	return doctype in tables

def generate_hash(txt=None):
	"""Generates random hash for given text + current timestamp + random string."""
	import hashlib, time
	from .utils import random_string
	return hashlib.sha224((txt or "") + repr(time.time()) + repr(random_string(8))).hexdigest()

def reset_metadata_version():
	"""Reset `metadata_version` (Client (Javascript) build ID) hash."""
	v = generate_hash()
	cache().set_value("metadata_version", v)
	return v

def new_doc(doctype, parent_doc=None, parentfield=None):
	"""Returns a new document of the given DocType with defaults set.

	:param doctype: DocType of the new document.
	:param parent_doc: [optional] add to parent document.
	:param parentfield: [optional] add against this `parentfield`."""
	from frappe.model.create_new import get_new_doc
	return get_new_doc(doctype, parent_doc, parentfield)

def set_value(doctype, docname, fieldname, value):
	"""Set document value. Calls `frappe.client.set_value`"""
	import frappe.client
	return frappe.client.set_value(doctype, docname, fieldname, value)

def get_doc(arg1, arg2=None):
	"""Return a `frappe.model.document.Document` object of the given type and name.

	:param arg1: DocType name as string **or** document JSON.
	:param arg2: [optional] Document name as string.

	Examples:

		# insert a new document
		todo = frappe.get_doc({"doctype":"ToDo", "description": "test"})
		tood.insert()

		# open an existing document
		todo = frappe.get_doc("ToDo", "TD0001")

	"""
	import frappe.model.document
	return frappe.model.document.get_doc(arg1, arg2)

def get_single(doctype):
	"""Return a `frappe.model.document.Document` object of the given Single doctype."""
	return get_doc(doctype, doctype)

def get_meta(doctype, cached=True):
	"""Get `frappe.model.meta.Meta` instance of given doctype name."""
	import frappe.model.meta
	return frappe.model.meta.get_meta(doctype, cached=cached)

def delete_doc(doctype=None, name=None, force=0, ignore_doctypes=None, for_reload=False,
	ignore_permissions=False, flags=None):
	"""Delete a document. Calls `frappe.model.delete_doc.delete_doc`.

	:param doctype: DocType of document to be delete.
	:param name: Name of document to be delete.
	:param force: Allow even if document is linked. Warning: This may lead to data integrity errors.
	:param ignore_doctypes: Ignore if child table is one of these.
	:param for_reload: Call `before_reload` trigger before deleting.
	:param ignore_permissions: Ignore user permissions."""
	import frappe.model.delete_doc
	frappe.model.delete_doc.delete_doc(doctype, name, force, ignore_doctypes, for_reload,
		ignore_permissions, flags)

def delete_doc_if_exists(doctype, name):
	"""Delete document if exists."""
	if db.exists(doctype, name):
		delete_doc(doctype, name)

def reload_doctype(doctype):
	"""Reload DocType from model (`[module]/[doctype]/[name]/[name].json`) files."""
	reload_doc(db.get_value("DocType", doctype, "module"), "doctype", doctype)

def reload_doc(module, dt=None, dn=None, force=False):
	"""Reload Document from model (`[module]/[doctype]/[name]/[name].json`) files.

	:param module: Module name.
	:param dt: DocType name.
	:param dn: Document name.
	:param force: Reload even if `modified` timestamp matches.
	"""

	import frappe.modules
	return frappe.modules.reload_doc(module, dt, dn, force=force)

def rename_doc(doctype, old, new, debug=0, force=False, merge=False, ignore_permissions=False):
	"""Rename a document. Calls `frappe.model.rename_doc.rename_doc`"""
	from frappe.model.rename_doc import rename_doc
	return rename_doc(doctype, old, new, force=force, merge=merge, ignore_permissions=ignore_permissions)

def get_module(modulename):
	"""Returns a module object for given Python module name using `importlib.import_module`."""
	return importlib.import_module(modulename)

def scrub(txt):
	"""Returns sluggified string. e.g. `Sales Order` becomes `sales_order`."""
	return txt.replace(' ','_').replace('-', '_').lower()

def unscrub(txt):
	"""Returns titlified string. e.g. `sales_order` becomes `Sales Order`."""
	return txt.replace('_',' ').replace('-', ' ').title()

def get_module_path(module, *joins):
	"""Get the path of the given module name.

	:param module: Module name.
	:param *joins: Join additional path elements using `os.path.join`."""
	module = scrub(module)
	return get_pymodule_path(local.module_app[module] + "." + module, *joins)

def get_app_path(app_name, *joins):
	"""Return path of given app.

	:param app: App name.
	:param *joins: Join additional path elements using `os.path.join`."""
	return get_pymodule_path(app_name, *joins)

def get_site_path(*joins):
	"""Return path of current site.

	:param *joins: Join additional path elements using `os.path.join`."""
	return os.path.join(local.site_path, *joins)

def get_pymodule_path(modulename, *joins):
	"""Return path of given Python module name.

	:param modulename: Python module name.
	:param *joins: Join additional path elements using `os.path.join`."""
	joins = [scrub(part) for part in joins]
	return os.path.join(os.path.dirname(get_module(scrub(modulename)).__file__), *joins)

def get_module_list(app_name):
	"""Get list of modules for given all via `app/modules.txt`."""
	return get_file_items(os.path.join(os.path.dirname(get_module(app_name).__file__), "modules.txt"))

def get_all_apps(with_frappe=False, with_internal_apps=True, sites_path=None):
	"""Get list of all apps via `sites/apps.txt`."""
	if not sites_path:
		sites_path = local.sites_path

	apps = get_file_items(os.path.join(sites_path, "apps.txt"), raise_not_found=True)
	if with_internal_apps:
		apps.extend(get_file_items(os.path.join(local.site_path, "apps.txt")))
	if with_frappe:
		apps.insert(0, 'frappe')
	return apps

def get_installed_apps():
	"""Get list of installed apps in current site."""
	if getattr(flags, "in_install_db", True):
		return []
	installed = json.loads(db.get_global("installed_apps") or "[]")
	return installed

@whitelist()
def get_versions():
	"""Get versions of all installed apps.

	Example:

		{
			"frappe": {
				"title": "Frappe Framework",
				"version": "5.0.0"
			}
		}"""
	versions = {}
	for app in get_installed_apps():
		versions[app] = {
			"title": get_hooks("app_title", app_name=app),
			"description": get_hooks("app_description", app_name=app)
		}
		try:
			versions[app]["version"] = get_attr(app + ".__version__")
		except AttributeError:
			versions[app]["version"] = '0.0.1'

	return versions

def get_hooks(hook=None, default=None, app_name=None):
	"""Get hooks via `app/hooks.py`

	:param hook: Name of the hook. Will gather all hooks for this name and return as a list.
	:param default: Default if no hook found.
	:param app_name: Filter by app."""
	def load_app_hooks(app_name=None):
		hooks = {}
		for app in [app_name] if app_name else get_installed_apps():
			app = "frappe" if app=="webnotes" else app
			try:
				app_hooks = get_module(app + ".hooks")
			except ImportError:
				if local.flags.in_install_app:
					# if app is not installed while restoring
					# ignore it
					pass
				raise
			for key in dir(app_hooks):
				if not key.startswith("_"):
					append_hook(hooks, key, getattr(app_hooks, key))
		return hooks

	def append_hook(target, key, value):
		if isinstance(value, dict):
			target.setdefault(key, {})
			for inkey in value:
				append_hook(target[key], inkey, value[inkey])
		else:
			append_to_list(target, key, value)

	def append_to_list(target, key, value):
		target.setdefault(key, [])
		if not isinstance(value, list):
			value = [value]
		target[key].extend(value)

	if app_name:
		hooks = _dict(load_app_hooks(app_name))
	else:
		hooks = _dict(cache().get_value("app_hooks", load_app_hooks))

	if hook:
		return hooks.get(hook) or (default if default is not None else [])
	else:
		return hooks

def setup_module_map():
	"""Rebuild map of all modules (internal)."""
	_cache = cache()

	if conf.db_name:
		local.app_modules = _cache.get_value("app_modules")
		local.module_app = _cache.get_value("module_app")

	if not local.app_modules:
		local.module_app, local.app_modules = {}, {}
		for app in get_all_apps(True):
			if app=="webnotes": app="frappe"
			local.app_modules.setdefault(app, [])
			for module in get_module_list(app):
				module = scrub(module)
				local.module_app[module] = app
				local.app_modules[app].append(module)

		if conf.db_name:
			_cache.set_value("app_modules", local.app_modules)
			_cache.set_value("module_app", local.module_app)

def get_file_items(path, raise_not_found=False, ignore_empty_lines=True):
	"""Returns items from text file as a list. Ignores empty lines."""
	import frappe.utils

	content = read_file(path, raise_not_found=raise_not_found)
	if content:
		content = frappe.utils.strip(content)

		return [p.strip() for p in content.splitlines() if (not ignore_empty_lines) or (p.strip() and not p.startswith("#"))]
	else:
		return []

def get_file_json(path):
	"""Read a file and return parsed JSON object."""
	with open(path, 'r') as f:
		return json.load(f)

def read_file(path, raise_not_found=False):
	"""Open a file and return its content as Unicode."""
	from frappe.utils import cstr
	if os.path.exists(path):
		with open(path, "r") as f:
			return cstr(f.read())
	elif raise_not_found:
		raise IOError("{} Not Found".format(path))
	else:
		return None

def get_attr(method_string):
	"""Get python method object from its name."""
	modulename = '.'.join(method_string.split('.')[:-1])
	methodname = method_string.split('.')[-1]
	return getattr(get_module(modulename), methodname)

def call(fn, *args, **kwargs):
	"""Call a function and match arguments."""
	if hasattr(fn, 'fnargs'):
		fnargs = fn.fnargs
	else:
		fnargs, varargs, varkw, defaults = inspect.getargspec(fn)

	newargs = {}
	for a in fnargs:
		if a in kwargs:
			newargs[a] = kwargs.get(a)

	if "flags" in newargs:
		del newargs["flags"]

	return fn(*args, **newargs)

def make_property_setter(args, ignore_validate=False, validate_fields_for_doctype=True):
	"""Create a new **Property Setter** (for overriding DocType and DocField properties)."""
	args = _dict(args)
	ps = get_doc({
		'doctype': "Property Setter",
		'doctype_or_field': args.doctype_or_field or "DocField",
		'doc_type': args.doctype,
		'field_name': args.fieldname,
		'property': args.property,
		'value': args.value,
		'property_type': args.property_type or "Data",
		'__islocal': 1
	})
	ps.flags.ignore_validate = ignore_validate
	ps.flags.validate_fields_for_doctype = validate_fields_for_doctype
	ps.insert()

def import_doc(path, ignore_links=False, ignore_insert=False, insert=False):
	"""Import a file using Data Import Tool."""
	from frappe.core.page.data_import_tool import data_import_tool
	data_import_tool.import_doc(path, ignore_links=ignore_links, ignore_insert=ignore_insert, insert=insert)

def copy_doc(doc, ignore_no_copy=True):
	""" No_copy fields also get copied."""
	import copy

	def remove_no_copy_fields(d):
		for df in d.meta.get("fields", {"no_copy": 1}):
			if hasattr(d, df.fieldname):
				d.set(df.fieldname, None)

	if not isinstance(doc, dict):
		d = doc.as_dict()
	else:
		d = doc

	newdoc = get_doc(copy.deepcopy(d))
	newdoc.name = None
	newdoc.set("__islocal", 1)
	newdoc.owner = None
	newdoc.creation = None
	newdoc.amended_from = None
	newdoc.amendment_date = None
	if not ignore_no_copy:
		remove_no_copy_fields(newdoc)

	for d in newdoc.get_all_children():
		d.name = None
		d.parent = None
		d.set("__islocal", 1)
		d.owner = None
		d.creation = None
		if not ignore_no_copy:
			remove_no_copy_fields(d)

	return newdoc

def compare(val1, condition, val2):
	"""Compare two values using `frappe.utils.compare`

	`condition` could be:
	- "^"
	- "in"
	- "not in"
	- "="
	- "!="
	- ">"
	- "<"
	- ">="
	- "<="
	- "not None"
	- "None"
	"""
	import frappe.utils
	return frappe.utils.compare(val1, condition, val2)

def respond_as_web_page(title, html, success=None, http_status_code=None):
	"""Send response as a web page with a message rather than JSON. Used to show permission errors etc.

	:param title: Page title and heading.
	:param message: Message to be shown.
	:param success: Alert message.
	:param http_status_code: HTTP status code."""
	local.message_title = title
	local.message = html
	local.message_success = success
	local.response['type'] = 'page'
	local.response['page_name'] = 'message'
	if http_status_code:
		local.response['http_status_code'] = http_status_code

def build_match_conditions(doctype, as_condition=True):
	"""Return match (User permissions) for given doctype as list or SQL."""
	import frappe.desk.reportview
	return frappe.desk.reportview.build_match_conditions(doctype, as_condition)

def get_list(doctype, *args, **kwargs):
	"""List database query via `frappe.model.db_query`. Will also check for permissions.

	:param doctype: DocType on which query is to be made.
	:param fields: List of fields or `*`.
	:param filters: List of filters (see example).
	:param order_by: Order By e.g. `modified desc`.
	:param limit_page_start: Start results at record #. Default 0.
	:param limit_poge_length: No of records in the page. Default 20.

	Example usage:

		# simple dict filter
		frappe.get_list("ToDo", fields=["name", "description"], filters = {"owner":"test@example.com"})

		# filter as a list of lists
		frappe.get_list("ToDo", fields="*", filters = [["modified", ">", "2014-01-01"]])

		# filter as a list of dicts
		frappe.get_list("ToDo", fields="*", filters = {"description": ("like", "test%")})
	"""
	import frappe.model.db_query
	return frappe.model.db_query.DatabaseQuery(doctype).execute(None, *args, **kwargs)

def get_all(doctype, *args, **kwargs):
	"""List database query via `frappe.model.db_query`. Will **not** check for conditions.
	Parameters are same as `frappe.get_list`

	:param doctype: DocType on which query is to be made.
	:param fields: List of fields or `*`. Default is: `["name"]`.
	:param filters: List of filters (see example).
	:param order_by: Order By e.g. `modified desc`.
	:param limit_page_start: Start results at record #. Default 0.
	:param limit_poge_length: No of records in the page. Default 20.

	Example usage:

		# simple dict filter
		frappe.get_all("ToDo", fields=["name", "description"], filters = {"owner":"test@example.com"})

		# filter as a list of lists
		frappe.get_all("ToDo", fields=["*"], filters = [["modified", ">", "2014-01-01"]])

		# filter as a list of dicts
		frappe.get_all("ToDo", fields=["*"], filters = {"description": ("like", "test%")})
	"""
	kwargs["ignore_permissions"] = True
	return get_list(doctype, *args, **kwargs)

def add_version(doc):
	"""Insert a new **Version** of the given document.
	A **Version** is a JSON dump of the current document state."""
	get_doc({
		"doctype": "Version",
		"ref_doctype": doc.doctype,
		"docname": doc.name,
		"doclist_json": json.dumps(doc.as_dict(), indent=1, sort_keys=True)
	}).insert(ignore_permissions=True)

def get_test_records(doctype):
	"""Returns list of objects from `test_records.json` in the given doctype's folder."""
	from frappe.modules import get_doctype_module, get_module_path
	path = os.path.join(get_module_path(get_doctype_module(doctype)), "doctype", scrub(doctype), "test_records.json")
	if os.path.exists(path):
		with open(path, "r") as f:
			return json.loads(f.read())
	else:
		return []

def format_value(value, df, doc=None, currency=None):
	"""Format value with given field properties.

	:param value: Value to be formatted.
	:param df: DocField object with properties `fieldtype`, `options` etc."""
	import frappe.utils.formatters
	return frappe.utils.formatters.format_value(value, df, doc, currency=currency)

def get_print(doctype, name, print_format=None, style=None, as_pdf=False):
	"""Get Print Format for given document.

	:param doctype: DocType of document.
	:param name: Name of document.
	:param print_format: Print Format name. Default 'Standard',
	:param style: Print Format style.
	:param as_pdf: Return as PDF. Default False."""
	from frappe.website.render import build_page
	from frappe.utils.pdf import get_pdf

	local.form_dict.doctype = doctype
	local.form_dict.name = name
	local.form_dict.format = print_format
	local.form_dict.style = style

	html = build_page("print")

	if as_pdf:
		return get_pdf(html)
	else:
		return html

def attach_print(doctype, name, file_name):
	from frappe.utils import scrub_urls

	print_settings = db.get_singles_dict("Print Settings")
	if int(print_settings.send_print_as_pdf or 0):
		return {
			"fname": file_name + ".pdf",
			"fcontent": get_print(doctype, name, as_pdf=True)
		}
	else:
		return {
			"fname": file_name + ".html",
			"fcontent": scrub_urls(get_print(doctype, name)).encode("utf-8")
		}

logging_setup_complete = False
def get_logger(module=None):
	from frappe.setup_logging import setup_logging
	global logging_setup_complete

	if not logging_setup_complete:
		setup_logging()
		logging_setup_complete = True

	return logging.getLogger(module or "frappe")
