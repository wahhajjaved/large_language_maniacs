import sys, os
import webnotes
import webnotes.defs
import webnotes.utils

form = webnotes.form
form_dict = webnotes.form_dict

sql = None
session = None
errdoc = ''
errdoctype = ''
errmethod = ''


# Logs

@webnotes.whitelist(allow_guest=True)
def startup():
	import webnotes
	import webnotes.session_cache

	webnotes.response.update(webnotes.session_cache.get())

def cleanup_docs():
	import webnotes.model.utils
	if webnotes.response.get('docs') and type(webnotes.response['docs'])!=dict:
		webnotes.response['docs'] = webnotes.model.utils.compress(webnotes.response['docs'])

# server calls
# ------------------------------------------------------------------------------------

@webnotes.whitelist()
def runserverobj(arg=None):
	import webnotes.widgets.form.run_method
	webnotes.widgets.form.run_method.runserverobj()

@webnotes.whitelist(allow_guest=True)
def logout():
	webnotes.login_manager.logout()


# DocType Mapper
# ------------------------------------------------------------------------------------

@webnotes.whitelist()
def dt_map():
	import webnotes
	import webnotes.model.utils
	from webnotes.model.code import get_obj
	from webnotes.model.doc import Document
	
	form_dict = webnotes.form_dict
	
	dt_list = webnotes.model.utils.expand(form_dict.get('docs'))
	from_doctype = form_dict.get('from_doctype')
	to_doctype = form_dict.get('to_doctype')
	from_docname = form_dict.get('from_docname')
	from_to_list = form_dict.get('from_to_list')
	
	dm = get_obj('DocType Mapper', from_doctype +'-' + to_doctype)
	dl = dm.dt_map(from_doctype, to_doctype, from_docname, Document(fielddata = dt_list[0]), [], from_to_list)
	
	webnotes.response['docs'] = dl

# Load Month Events
# ------------------------------------------------------------------------------------

@webnotes.whitelist()
def load_month_events():
	import webnotes
	form = webnotes.form

	mm = form.getvalue('month')
	yy = form.getvalue('year')
	m_st = str(yy) + '-' + str(mm) + '-01'
	m_end = str(yy) + '-' + str(mm) + '-31'

	import webnotes.widgets.event
	webnotes.response['docs'] = webnotes.widgets.event.get_cal_events(m_st, m_end)

# Data import
# ------------------------------------------------------------------------------------

@webnotes.whitelist()
def import_csv():
	import webnotes.model.import_docs
	form = webnotes.form
	from webnotes.utils import cint
	
	i = webnotes.model.import_docs.CSVImport()
	r = i.import_csv(form.getvalue('csv_file'), form.getvalue('dateformat'), form_dict.get('overwrite', 0) and 1)
	
	webnotes.response['type']='iframe'
	rhead = '''<style>body, html {font-family: Arial; font-size: 12px;}</style>'''
	webnotes.response['result']= rhead + r

@webnotes.whitelist()
def get_template():
	import webnotes.model.import_docs
	webnotes.model.import_docs.get_template()
	

# File Upload
# ------------------------------------------------------------------------------------

@webnotes.whitelist()
def uploadfile():
	import webnotes.utils.file_manager
	if webnotes.form_dict.get('from_form'):
		webnotes.utils.file_manager.upload()
	else:
		# save the file
		fid, fname = webnotes.utils.file_manager.save_uploaded()
		
		# do something with the uploaded file
		if fid:
			if webnotes.form_dict.get('server_obj'):
				from webnotes.model.code import get_obj
				getattr(get_obj(webnotes.form_dict.get('server_obj')), webnotes.form_dict.get('method'))(fid, fname)
		
			elif webnotes.form_dict.get('modulename'):
				# calls a python module to handle the script
				__import__(webnotes.form_dict['modulename'])
				import sys
				moduleobj = sys.modules[webnotes.form_dict['modulename']]
				getattr(moduleobj, webnotes.form_dict['method'])(fid, fname)


			webnotes.response['result'] = '<script>window.parent.upload_callback("'+webnotes.form_dict.get('uploader_id')+'", "'+fid+'")</script>'
	
# File upload (from scripts)
# ------------------------------------------------------------------------------------

@webnotes.whitelist()
def upload_many():
	from webnotes.model.code import get_obj

	# pass it on to upload_many method in Control Panel
	cp = get_obj('Control Panel')
	cp.upload_many(webnotes.form)
	
	webnotes.response['result'] = """
<script type='text/javascript'>
%s
</script>
%s
%s""" % (cp.upload_callback(webnotes.form), '\n----\n'.join(webnotes.message_log).replace("'", "\'"), '\n----\n'.join(webnotes.debug_log).replace("'", "\'").replace("\n","<br>"))
	webnotes.response['type'] = 'iframe'


@webnotes.whitelist()
def get_file():
	import webnotes
	import webnotes.utils.file_manager
	form = webnotes.form

	res = webnotes.utils.file_manager.get_file(form.getvalue('fname'))
	if res:
		webnotes.response['type'] = 'download'
		webnotes.response['filename'] = res[0]
		
		if hasattr(res[1], 'tostring'):
			webnotes.response['filecontent'] = res[1].tostring()
		else: 
			webnotes.response['filecontent'] = res[1]
	else:
		webnotes.msgprint('[get_file] Unknown file name')

@webnotes.whitelist(allow_guest=True)
def reset_password():
	form_dict = webnotes.form_dict
	from webnotes.model.code import get_obj
	
	user = form_dict.get('user', '')
	if webnotes.conn.sql("""select name from tabProfile where name=%s""", user):
		get_obj('Profile', user).reset_password()
		webnotes.msgprint("Password has been reset and sent to your email id.")
	else:
		webnotes.msgprint("No such user (%s)", user)


def handle():
	"""handle request"""
	cmd = webnotes.form_dict['cmd']

	if cmd!='login':
		# login executed in webnotes.auth
		try:
			execute_cmd(cmd)
		except webnotes.ValidationError:
			webnotes.conn.rollback()
		except:
			webnotes.errprint(webnotes.utils.getTraceback())
			webnotes.conn and webnotes.conn.rollback()
			
	if webnotes.conn:
		webnotes.conn.close()
		
	print_response()

def execute_cmd(cmd):
	"""execute a request as python module"""
	validate_cmd(cmd)
	method = get_method(cmd)

	# check if whitelisted
	if webnotes.session['user'] == 'Guest':
		if (method not in webnotes.guest_methods):
			webnotes.msgprint('Not Allowed, %s' % str(method))
			raise Exception, 'Not Allowed, %s' % str(method)
	else:
		if not method in webnotes.whitelisted:
			webnotes.msgprint('Not Allowed, %s' % str(method))
			raise Exception, 'Not Allowed, %s' % str(method)
		
	if not webnotes.conn.in_transaction:
		webnotes.conn.begin()

	if 'arg' in webnotes.form_dict:
		# direct method call
		ret = method(webnotes.form_dict.get('arg'))
	else:
		ret = method()

	# returns with a message
	if ret:
		webnotes.response['message'] = ret

	# update session
	webnotes.session_obj.update()

	if webnotes.conn.in_transaction:
		webnotes.conn.commit()

def get_method(cmd):
	"""get method object from cmd"""
	if '.' in cmd:
		module = __import__('.'.join(cmd.split('.')[:-1]), fromlist=[''])
		method = getattr(module, cmd.split('.')[-1])
	else:
		method = globals()[cmd]
	return method
	
def validate_cmd(cmd):
	# check if there is no direct possibility of malicious script injection
	if cmd.startswith('webnotes.model.code'):
		raise Exception, 'Cannot call any methods from webnotes.model.code directly from the handler'

	if cmd.startswith('webnotes.model.db_schema'):
		raise Exception, 'Cannot call any methods from webnotes.model.db_schema directly from the handler'

	if cmd.startswith('webnotes.conn'):
		raise Exception, 'Cannot call database connection method directly from the handler'
		
def print_response():
	import string
	import os

	if webnotes.response.get('type')=='csv':
		print_csv()
	elif webnotes.response.get('type')=='iframe':
		print_iframe()
	elif webnotes.response.get('type')=='download':
		print_raw()
	else:
		print_json()
		
def print_csv():
	print "Content-Type: text/csv"
	print "Content-Disposition: attachment; filename="+webnotes.response['doctype'].replace(' ', '_')+".csv"
	print
	print webnotes.response['result']

def print_iframe():
	print "Content-Type: text/html"
	print
	if webnotes.response.get('result'):
		print webnotes.response['result']
	if webnotes.debug_log:
		print '''<script type='text/javascript'>alert("%s");</script>''' % ('-------'.join(webnotes.debug_log).replace('"', '').replace('\n',''))

def print_raw():
	import mimetypes
	print "Content-Type: %s" % (mimetypes.guess_type(webnotes.response['filename'])[0] or 'application/unknown')
	print "Content-Disposition: filename="+webnotes.response['filename'].replace(' ', '_')
	print
	print webnotes.response['filecontent']

def print_json():
	make_logs()
	cleanup_docs()

	import json
	str_out = json.dumps(webnotes.response)
	
	if accept_gzip() and len(str_out)>512:
		out_buf = compressBuf(str_out)
		print "Content-Encoding: gzip"
		print "Content-Length: %d" % (len(out_buf))
		str_out = out_buf
		
	print "Content-Type: text/html; charset: utf-8"
	print_cookies()

	# Headers end
	print 
	print str_out

def accept_gzip():
	"""return true if client accepts gzip"""
	try:
		if string.find(os.environ["HTTP_ACCEPT_ENCODING"], "gzip") != -1:
			return True
	except:
		return False

def make_logs():
	"""make strings for msgprint and errprint"""
	if webnotes.debug_log:
		t = '\n----------------\n'.join(webnotes.debug_log)
		webnotes.response['exc'] = t

	if webnotes.message_log:
		t = '\n----------------\n'.join(webnotes.message_log)
		webnotes.response['server_messages'] = t	

def print_cookies():
	"""if there ar additional cookies defined during the request, add them"""
	if webnotes.cookies or webnotes.add_cookies: 
		for c in webnotes.add_cookies.keys():
			webnotes.cookies[c] = webnotes.add_cookies[c]
		
		print webnotes.cookies

def compressBuf(buf):
	import gzip, cStringIO
	zbuf = cStringIO.StringIO()
	zfile = gzip.GzipFile(mode = 'wb',  fileobj = zbuf, compresslevel = 5)
	zfile.write(buf)
	zfile.close()
	return zbuf.getvalue()
