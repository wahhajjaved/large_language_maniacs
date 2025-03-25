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

# util __init__.py

from __future__ import unicode_literals
import webnotes

user_time_zone = None
user_format = None

no_value_fields = ['Section Break', 'Column Break', 'HTML', 'Table', 'FlexTable',
	'Button', 'Image', 'Graph']
default_fields = ['doctype', 'name', 'owner', 'creation', 'modified', 'modified_by',
	'parent', 'parentfield', 'parenttype', 'idx', 'docstatus']

# used in import_docs.py
# TODO: deprecate it
def getCSVelement(v):
	"""
		 Returns the CSV value of `v`, For example: 
		 
		 * apple becomes "apple"
		 * hi"there becomes "hi""there"
	"""
	v = cstr(v)
	if not v: return ''
	if (',' in v) or ('\n' in v) or ('"' in v):
		if '"' in v: v = v.replace('"', '""')
		return '"'+v+'"'
	else: return v or ''

def get_fullname(profile):
	"""get the full name (first name + last name) of the user from Profile"""
	p = webnotes.conn.sql("""select first_name, last_name from `tabProfile`
		where name=%s""", profile, as_dict=1)
	if p:
		profile = " ".join(filter(None, 
			[p[0].get('first_name'), p[0].get('last_name')])) or profile
	
	return profile

def get_formatted_email(user):
	"""get email id of user formatted as: John Doe <johndoe@example.com>"""
	if user == "Administrator":
		return user
	from email.utils import formataddr
	fullname = get_fullname(user)
	return formataddr((fullname, user))
	
def extract_email_id(email):
	"""fetch only the email part of the email id"""
	from email.utils import parseaddr
	if ',' in email and email.count("@")==1:
		email = email.split(",")[-1]
	fullname, email_id = parseaddr(email)
	return email_id
	
def validate_email_add(email_str):
	"""Validates the email string"""
	email = extract_email_id(email_str)
	import re
	return re.match("[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", email.lower())

def sendmail(recipients, sender='', msg='', subject='[No Subject]'):
	"""Send an email. For more details see :func:`email_lib.sendmail`"""
	import webnotes.utils.email_lib
	return email_lib.sendmail(recipients, sender, msg, subject)

def get_request_site_address():
	"""get app url from request"""
	import os
	try:
		return 'HTTPS' in os.environ.get('SERVER_PROTOCOL') and 'https://' or 'http://' \
			+ os.environ.get('HTTP_HOST')
	except TypeError, e:
		return 'http://localhost'

def random_string(length):
	"""generate a random string"""
	import string
	from random import choice
	return ''.join([choice(string.letters + string.digits) for i in range(length)])

def load_json(arg):
	# already a dictionary?
	if not isinstance(arg, basestring):
		return arg
	
	import json
	return json.loads(arg, encoding='utf-8')
	
# Get Traceback
# ==============================================================================

def getTraceback():
	"""
		 Returns the traceback of the Exception
	"""
	import sys, traceback, string
	exc_type, value, tb = sys.exc_info()
	
	trace_list = traceback.format_tb(tb, None) + \
		traceback.format_exception_only(exc_type, value)
	body = "Traceback (innermost last):\n" + "%-20s %s" % \
		(unicode((b"").join(trace_list[:-1]), 'utf-8'), unicode(trace_list[-1], 'utf-8'))
	
	if webnotes.logger:
		webnotes.logger.error('Db:'+(webnotes.conn and webnotes.conn.cur_db_name or '') \
			+ ' - ' + body)
	
	return body

def log(event, details):
	webnotes.logger.info(details)

# datetime functions
def getdate(string_date):
	"""
		 Coverts string date (yyyy-mm-dd) to datetime.date object
	"""
	import datetime
	
	if isinstance(string_date, datetime.date):
		return string_date
	elif isinstance(string_date, datetime.datetime):
		return datetime.date()
	
	if " " in string_date:
		string_date = string_date.split(" ")[0]
	
	try:
		return datetime.datetime.strptime(string_date, "%Y-%m-%d").date()
	except ValueError, e:
		webnotes.msgprint("Cannot understand date - '%s'" % \
			(string_date,), raise_exception=1)

def add_to_date(date, years=0, months=0, days=0):
	"""Adds `days` to the given date"""
	format = isinstance(date, basestring)
	if date:
		date = getdate(date)
	else:
		raise Exception, "Start date required"
	
	from dateutil.relativedelta import relativedelta
	date += relativedelta(years=years, months=months, days=days)
	
	if format:
		return date.strftime("%Y-%m-%d")
	else:
		return date

def add_days(date, days):
	return add_to_date(date, days=days)

def add_months(date, months):
	return add_to_date(date, months=months)

def add_years(date, years):
	return add_to_date(date, years=years)

def date_diff(string_ed_date, string_st_date):
	return (getdate(string_ed_date) - getdate(string_st_date)).days
	
def time_diff_in_seconds(string_ed_date, string_st_date):
	return (getdate(string_ed_date) - getdate(string_st_date)).seconds

def now_datetime():
	global user_time_zone
	from datetime import datetime
	from pytz import timezone
	
	# get localtime
	if not user_time_zone:
		user_time_zone = webnotes.conn.get_value('Control Panel', None, 'time_zone') \
			or 'Asia/Calcutta'

	# convert to UTC
	utcnow = timezone('UTC').localize(datetime.utcnow())

	# convert to user time zone
	return utcnow.astimezone(timezone(user_time_zone))

def now():
	"""return current datetime as yyyy-mm-dd hh:mm:ss"""
	return now_datetime().strftime('%Y-%m-%d %H:%M:%S')
	
def nowdate():
	"""return current date as yyyy-mm-dd"""
	return now_datetime().strftime('%Y-%m-%d')

def today():
	return nowdate()
	
def nowtime():
	"""return current time in hh:mm"""
	return now_datetime().strftime('%H:%M')

def get_first_day(dt, d_years=0, d_months=0):
	"""
	 Returns the first day of the month for the date specified by date object
	 Also adds `d_years` and `d_months` if specified
	"""
	import datetime
	dt = getdate(dt)

	# d_years, d_months are "deltas" to apply to dt	
	overflow_years, month = divmod(dt.month + d_months - 1, 12)
	year = dt.year + d_years + overflow_years

	return datetime.date(year, month + 1, 1)

def get_last_day(dt):
	"""
	 Returns last day of the month using:
	 `get_first_day(dt, 0, 1) + datetime.timedelta(-1)`
	"""
	import datetime
	return get_first_day(dt, 0, 1) + datetime.timedelta(-1)

def get_datetime(datetime_str):
	from datetime import datetime
	if isinstance(datetime_str, datetime):
		return datetime_str.replace(microsecond=0, tzinfo=None)
	
	return datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
	
def get_datetime_str(datetime_obj):
	if isinstance(datetime_obj, basestring):
		datetime_obj = get_datetime(datetime_obj)
	
	return datetime_obj.strftime('%Y-%m-%d %H:%M:%S')

def formatdate(string_date=None):
	"""
	 	Convers the given string date to :data:`user_format`
		User format specified in :term:`Control Panel`

		 Examples:

		 * dd-mm-yyyy
		 * mm-dd-yyyy
		 * dd/mm/yyyy
	"""
	if string_date:
		string_date = getdate(string_date)
	else:
		string_date = nowdate()
	
	global user_format
	if not user_format:
		user_format = webnotes.conn.get_value('Control Panel', None, 'date_format')
		
	out = user_format
	return out.replace("dd", string_date.strftime("%d"))\
		.replace("mm", string_date.strftime("%m"))\
		.replace("yyyy", string_date.strftime("%Y"))
		
def global_date_format(date):
	"""returns date as 1 January 2012"""
	formatted_date = getdate(date).strftime("%d %B %Y")
	return formatted_date.startswith("0") and formatted_date[1:] or formatted_date
	
def dict_to_str(args, sep='&'):
	"""
	Converts a dictionary to URL
	"""
	import urllib
	t = []
	for k in args.keys():
		t.append(str(k)+'='+urllib.quote(str(args[k] or '')))
	return sep.join(t)

def timestamps_equal(t1, t2):
	"""Returns true if same the two string timestamps are same"""
	scrub = lambda x: x.replace(':', ' ').replace('-',' ').split()

	t1, t2 = scrub(t1), scrub(t2)
	
	if len(t1) != len(t2):
		return
	
	for i in range(len(t1)):
		if t1[i]!=t2[i]:
			return
	return 1

def has_common(l1, l2):
	"""Returns truthy value if there are common elements in lists l1 and l2"""
	return set(l1) & set(l2)
	
def flt(s, precision=None):
	"""Convert to float (ignore commas)"""
	if isinstance(s, basestring):
		s = s.replace(',','')
	try:
		num = float(s)
		if precision:
			num = round(num, precision)
	except Exception, e:
		num = 0
	return num

def cint(s):
	"""Convert to integer"""
	try: num = int(float(s))
	except: num = 0
	return num

def cstr(s):
	if isinstance(s, unicode):
		return s
	elif s==None: 
		return ''
	elif isinstance(s, basestring):
		return unicode(s, 'utf-8')
	else:
		return unicode(s)

def encode(obj, encoding="utf-8"):
	if isinstance(obj, list):
		out = []
		for o in obj:
			if isinstance(o, unicode):
				out.append(o.encode(encoding))
			else:
				out.append(o)
		return out
	elif isinstance(obj, unicode):
		return obj.encode(encoding)
	else:
		return obj

def parse_val(v):
	"""Converts to simple datatypes from SQL query results"""
	import datetime
	
	if isinstance(v, (datetime.date, datetime.datetime)):
		v = unicode(v)
	elif isinstance(v, datetime.timedelta):
		v = ":".join(unicode(v).split(":")[:2])
	elif isinstance(v, long):
		v = int(v)
	return v

def fmt_money(amount, precision=None):
	"""
	Convert to string with commas for thousands, millions etc
	"""
	import webnotes, re
	from webnotes import _
	
	curr = webnotes.conn.get_value('Control Panel', None, 
		'currency_format') or 'Millions'
	number_format = webnotes.conn.get_default("number_format") or "#,###.##"
		
	breaks = re.findall('[^#\d]+', number_format)
	if len(breaks) < 2:
		webnotes.msgprint(_("Incorrect Number Format:") + number_format, 
			raise_exception=True)
	
	decimal_str = breaks[-1]
	comma_str = breaks[0]
	if not precision:
		precision = len(number_format.split(decimal_str)[-1]) or 2
	
	amount = '%.*f' % (precision, flt(amount))
	val = 2
	if curr == 'Millions': val = 3

	if amount.find('.') == -1:	temp = '00'
	else: temp = amount.split('.')[1]

	l = []
	minus = ''
	if flt(amount) < 0: minus = '-'

	amount = cstr(abs(flt(amount))).split('.')[0]
	
	# main logic	
	if len(amount) > 3:
		nn = amount[len(amount)-3:]
		l.append(nn)
		amount = amount[0:len(amount)-3]
		while len(amount) > val:
			nn = amount[len(amount)-val:]
			l.insert(0,nn)
			amount = amount[0:len(amount)-val]
	
	if len(amount) > 0:	l.insert(0,amount)

	amount = comma_str.join(l) + decimal_str + temp
	amount = minus + amount
	return amount

#
# convet currency to words
#
def money_in_words(number, main_currency = None, fraction_currency=None):
	"""
	Returns string in words with currency and fraction currency. 
	"""
	
	d = get_defaults()
	if not main_currency:
		main_currency = d.get('currency', 'INR')
	if not fraction_currency:
		fraction_currency = webnotes.conn.get_value("Currency", main_currency, "fraction") or "Cent"

	n = "%.2f" % flt(number)
	main, fraction = n.split('.')
	if len(fraction)==1: fraction += '0'
	
	out = main_currency + ' ' + in_words(main).title()
	if cint(fraction):
		out = out + ' and ' + in_words(fraction).title() + ' ' + fraction_currency

	return out + ' only.'

#
# convert number to words
#
def in_words(integer):
	"""
	Returns string in words for the given integer.
	"""

	in_million = webnotes.conn.get_default('currency_format')=='Millions' and 1 or 0

	n=int(integer)
	known = {0: 'zero', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
		11: 'eleven', 12: 'twelve', 13: 'thirteen', 14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen', 18: 'eighteen',
		19: 'nineteen', 20: 'twenty', 30: 'thirty', 40: 'forty', 50: 'fifty', 60: 'sixty', 70: 'seventy', 80: 'eighty', 90: 'ninety'}
	
	def psn(n, known, xpsn):
		import sys; 
		if n in known: return known[n]
		bestguess, remainder = str(n), 0

		if n<=20:
			print >>sys.stderr, n, "How did this happen?"
			assert 0
		elif n < 100:
			bestguess= xpsn((n//10)*10, known, xpsn) + '-' + xpsn(n%10, known, xpsn)
			return bestguess
		elif n < 1000:
			bestguess= xpsn(n//100, known, xpsn) + ' ' + 'hundred'
			remainder = n%100
		else:
			if in_million:
				if n < 1000000:
					bestguess= xpsn(n//1000, known, xpsn) + ' ' + 'thousand'
					remainder = n%1000
				elif n < 1000000000:
					bestguess= xpsn(n//1000000, known, xpsn) + ' ' + 'million'
					remainder = n%1000000
				else:
					bestguess= xpsn(n//1000000000, known, xpsn) + ' ' + 'billion'
					remainder = n%1000000000				
			else:
				if n < 100000:
					bestguess= xpsn(n//1000, known, xpsn) + ' ' + 'thousand'
					remainder = n%1000
				elif n < 10000000:
					bestguess= xpsn(n//100000, known, xpsn) + ' ' + 'lakh'
					remainder = n%100000
				else:
					bestguess= xpsn(n//10000000, known, xpsn) + ' ' + 'crore'
					remainder = n%10000000
		if remainder:
			if remainder >= 100:
				comma = ','
			else:
				comma = ''
			return bestguess + comma + ' ' + xpsn(remainder, known, xpsn)
		else:
			return bestguess

	return psn(n, known, psn)
	

# Get Defaults
# ==============================================================================

def get_defaults(key=None):
	"""
	Get dictionary of default values from the :term:`Control Panel`, or a value if key is passed
	"""
	return webnotes.conn.get_defaults(key)

def set_default(key, val):
	"""
	Set / add a default value to :term:`Control Panel`
	"""
	return webnotes.conn.set_default(key, val)

def remove_blanks(d):
	"""
		Returns d with empty ('' or None) values stripped
	"""
	empty_keys = []
	for key in d:
		if d[key]=='' or d[key]==None:
			# del d[key] raises runtime exception, using a workaround
			empty_keys.append(key)
	for key in empty_keys:
		del d[key]
		
	return d
		
def pprint_dict(d, level=1, no_blanks=True):
	"""
		Pretty print a dictionary with indents
	"""
	if no_blanks:
		remove_blanks(d)
		
	# make indent
	indent, ret = '', ''
	for i in range(0,level): indent += '\t'
	
	# add lines
	comment, lines = '', []
	kl = d.keys()
	kl.sort()
		
	# make lines
	for key in kl:
		if key != '##comment':
			tmp = {key: d[key]}
			lines.append(indent + str(tmp)[1:-1] )
	
	# add comment string
	if '##comment' in kl:
		ret = ('\n' + indent) + '# ' + d['##comment'] + '\n'

	# open
	ret += indent + '{\n'
	
	# lines
	ret += indent + ',\n\t'.join(lines)
	
	# close
	ret += '\n' + indent + '}'
	
	return ret
				
def get_common(d1,d2):
	"""
		returns (list of keys) the common part of two dicts
	"""
	return [p for p in d1 if p in d2 and d1[p]==d2[p]]

def get_common_dict(d1, d2):
	"""
		return common dictionary of d1 and d2
	"""
	ret = {}
	for key in d1:
		if key in d2 and d2[key]==d1[key]:
			ret[key] = d1[key]
	return ret

def get_diff_dict(d1, d2):
	"""
		return common dictionary of d1 and d2
	"""
	diff_keys = set(d2.keys()).difference(set(d1.keys()))
	
	ret = {}
	for d in diff_keys: ret[d] = d2[d]
	return ret


def get_file_timestamp(fn):
	"""
		Returns timestamp of the given file
	"""
	import os
	from webnotes.utils import cint
	
	try:
		return str(cint(os.stat(fn).st_mtime))
	except OSError, e:
		if e.args[0]!=2:
			raise e
		else:
			return None

# to be deprecated
def make_esc(esc_chars):
	"""
		Function generator for Escaping special characters
	"""
	return lambda s: ''.join(['\\' + c if c in esc_chars else c for c in s])

# esc / unescape characters -- used for command line
def esc(s, esc_chars):
	"""
		Escape special characters
	"""
	if not s:
		return ""
	for c in esc_chars:
		esc_str = '\\' + c
		s = s.replace(c, esc_str)
	return s

def unesc(s, esc_chars):
	"""
		UnEscape special characters
	"""
	for c in esc_chars:
		esc_str = '\\' + c
		s = s.replace(esc_str, c)
	return s
	
def strip_html(text):
	"""
		removes anything enclosed in and including <>
	"""
	import re
	return re.compile(r'<.*?>').sub('', text)
	
def escape_html(text):
	html_escape_table = {
		"&": "&amp;",
		'"': "&quot;",
		"'": "&apos;",
		">": "&gt;",
		"<": "&lt;",
	}

	return "".join(html_escape_table.get(c,c) for c in text)

def get_doctype_label(dt=None):
	"""
		Gets label of a doctype
	"""
	if dt:
		res = webnotes.conn.sql("""\
			SELECT name, dt_label FROM `tabDocType Label`
			WHERE name=%s""", dt)
		return res and res[0][0] or dt
	else:
		res = webnotes.conn.sql("SELECT name, dt_label FROM `tabDocType Label`")
		dt_label_dict = {}
		for r in res:
			dt_label_dict[r[0]] = r[1]

		return dt_label_dict


def get_label_doctype(label):
	"""
		Gets doctype from its label
	"""
	res = webnotes.conn.sql("""\
		SELECT name FROM `tabDocType Label`
		WHERE dt_label=%s""", label)

	return res and res[0][0] or label


def pretty_date(iso_datetime):
	"""
		Takes an ISO time and returns a string representing how
		long ago the date represents.
		Ported from PrettyDate by John Resig
	"""
	if not iso_datetime: return ''
	from datetime import datetime
	import math
	
	if isinstance(iso_datetime, basestring):
		iso_datetime = datetime.strptime(iso_datetime, '%Y-%m-%d %H:%M:%S')
	now_dt = datetime.strptime(now(), '%Y-%m-%d %H:%M:%S')
	dt_diff = now_dt - iso_datetime
	
	# available only in python 2.7+
	# dt_diff_seconds = dt_diff.total_seconds()
	
	dt_diff_seconds = dt_diff.days * 86400.0 + dt_diff.seconds
	
	dt_diff_days = math.floor(dt_diff_seconds / 86400.0)
	
	# differnt cases
	if dt_diff_seconds < 60.0:
		return 'just now'
	elif dt_diff_seconds < 120.0:
		return '1 minute ago'
	elif dt_diff_seconds < 3600.0:
		return '%s minutes ago' % cint(math.floor(dt_diff_seconds / 60.0))
	elif dt_diff_seconds < 7200.0:
		return '1 hour ago'
	elif dt_diff_seconds < 86400.0:
		return '%s hours ago' % cint(math.floor(dt_diff_seconds / 3600.0))
	elif dt_diff_days == 1.0:
		return 'Yesterday'
	elif dt_diff_days < 7.0:
		return '%s days ago' % cint(dt_diff_days)
	elif dt_diff_days < 31.0:
		return '%s week(s) ago' % cint(math.ceil(dt_diff_days / 7.0))
	elif dt_diff_days < 365.0:
		return '%s months ago' % cint(math.ceil(dt_diff_days / 30.0))
	else:
		return 'more than %s year(s) ago' % cint(math.floor(dt_diff_days / 365.0))
		
def execute_in_shell(cmd, verbose=0):
	# using Popen instead of os.system - as recommended by python docs
	from subprocess import Popen, PIPE
	import tempfile
	
	with tempfile.TemporaryFile() as stdout:
		with tempfile.TemporaryFile() as stderr:
			p = Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
			p.wait()
			
			stdout.seek(0)
			out = stdout.read()
			
			stderr.seek(0)
			err = stderr.read()

	if verbose:
		if err: print err
		if out: print out

	return err, out

def comma_or(some_list):
	return comma_sep(some_list, " or ")
	
def comma_and(some_list):
	return comma_sep(some_list, " and ")
	
def comma_sep(some_list, sep):
	if isinstance(some_list, (list, tuple)):
		# list(some_list) is done to preserve the existing list
		some_list = [unicode(s) for s in list(some_list)]
		if not some_list:
			return ""
		elif len(some_list) == 1:
			return some_list[0]
		else:
			some_list = ["'%s'" % s for s in some_list]
			return ", ".join(some_list[:-1]) + sep + some_list[-1]
	else:
		return some_list
		
def get_base_path():
	import conf
	import os
	return os.path.dirname(os.path.abspath(conf.__file__))
