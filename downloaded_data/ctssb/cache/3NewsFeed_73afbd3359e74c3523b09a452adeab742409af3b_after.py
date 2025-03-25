#!/usr/bin/env python

"""
NewsFeed

A Python/Tk RSS/RDF/Atom news aggregator. See included README.html for documentation.

Martin Doege, 2015-02-19

"""

__author__    = "Martin C. Doege (mdoege@compuserve.com)"
__copyright__ = "Copyright 2003-2015, Martin C. Doege"
__license__   = "GPL"
__version__   = "3.3"

from  tkinter import *
import sys
assert sys.version >= '3.3', "This program does not work with older versions of Python.\
 Please install Python 3.3 or later."

import os, sys, time, string, re, webbrowser, pickle, signal, socket, urllib.request, urllib.error, urllib.parse, difflib
socket.setdefaulttimeout(20)
from hashlib import md5
from multiprocessing import Queue
from queue import Empty, Full
from html.entities import html5 as entdic
from html.parser import HTMLParser

import feedparser, rssfinder, play_wav

# Python multiprocessing ic combination with urllib is broken on OS X
# and MP behaves differently on Windows, so it is only enabled on Linux and FreeBSD:
if 'freebsd' in sys.platform or 'linux' in sys.platform:
	use_threads = True
else:
	use_threads = False
if use_threads:
	import dlthreads

################################################################################################

# NOTE:
# You can set the USER AGENT for fetching feeds in feedparser.py if you have problems...

# Setting this to a nonexistent filename will disable sound notification:
soundfile = os.getenv("NEWSFEED_SOUND")
if not soundfile:
	soundfile = "/usr/share/newsfeed/sounds/email.wav"
sound = play_wav.Sound()

# Media player used for opening enclosures. A few suggestions for different systems:
media_player = os.getenv("MEDIA_PLAYER")
if not media_player:
	if 'freebsd' in sys.platform or 'linux' in sys.platform:
		media_player = "vlc"		# A nice choice under Linux
	elif 'darwin' in sys.platform:
		media_player = "open"		# Suggested for Mac OS X
	else:
		media_player = ""		# Empty string -> Enclosures get opened
						#                 in default web browser.
#
# Notes on media players:
#  1. It is a good idea to use a non-blocking player, i.e. one that accepts an URL
#     and then returns control to NewsFeed. Otherwise NewsFeed will be unresponsive
#     while the player is running.
#  2. Of course you can also use a download manager like kget here.

# Program that is used when the user clicks on 'export':
#   (Mail client, weblog editor, printing application, or whatever...)
#
#   Some Examples---
#     Create a new email in kmail:
export_application = "kmail -s '%(title)s' --msg %(description_path)s"
#     Print using a2ps:
#export_application = "a2ps --header='%(title)s' --center-title='%(title)s' %(description_path)s"

# Open links in a new browser window?
if os.getenv("BROWSER_NEW") in ['no', 'No']: open_in_new_window = False
else: open_in_new_window = True

# Ask for confimation before deleting channels? (initial value for current session)
ask_before_deletion = True

# Custom feed update interval (in minutes)
custom_interval = .333

# Number of old configuration files that are kept:
old_revisions_to_keep = 3
# Note: They are suffixed .1, .2, .3, etc. with lower numbers
#       designating more recent versions.

# Colors in text pane:
tp_foreground = 'black'
tp_background = '#fffbea'
tps_foreground = 'white'
tps_background = '#233a8e' 

# Default font sizes (points):
fontsize = {}
fontsize['Headline']    = 24
fontsize['Description'] = 18
fontsize['URL']         = 12
fontsize['Date']        = 12
fontsize['Navigation']  = 14

### Parse an (optional) Python script with additional configuration
###  (overrides the settings above):

try:
	sys.path = [''] + sys.path	# search for module in current directory first,
					#  then in the NewsFeed installation directory
	from newsfeed_defaults import *
except: pass

################################################################################################
#  NO CHANGES SHOULD NORMALLY BE REQUIRED BELOW THIS LINE  #####################################
################################################################################################


# Some program default values at first startup:
config = {}

config['mode']                     = "gui"
config['progname']                 = "NewsFeed"
config['refresh_every']            = 30		# Refresh interval in minutes
config['maxtime']                  = 30		# Maximum time (in days) to keep items

# Program default values that get saved automatically if changed:
config['geom_root']                = "900x600"  # Default
config['geom_info']                = "675x380"  #         window
config['geom_search']              = "350x200"  #                sizes
config['search_is_case_sensitive'] = 0          # Make new searches case sensitive?
config['search_match_whole_words'] = 0          # Match only entire words in searches?
config['search_only_unread']       = 0          # Search only in unread entries?
config['widescreen']               = False	# Widescreen view?

try: config_file != None
except:
	config_file  = os.path.join(os.path.expanduser('~'), '.'
					+ config['progname'].lower())
else:
	if '~' in config_file:
		config_file = config_file.replace('~',os.path.expanduser('~'))
pid_file     = config_file + '.pid'
addfeed_file = config_file + '.addfeed'
export_file  = config_file + '.export'

newsfeeds = []

initial = [
  ("?Welcome",           "http://home.arcor.de/mdoege/newsfeed/welcome.rss",                       60, 999),
  ("Wired News",         "http://www.wired.com/rss/index.xml"),
  ("ScienceDaily",       "http://www.sciencedaily.com/newsfeed.xml",                               60, 10),
  ("Slashdot",           "http://slashdot.org/slashdot.rss"),
  ("MetaFilter",         "http://feeds.feedburner.com/Metafilter",                                 30,  3),
  ("Food Consumer",      "http://www.foodconsumer.org/newsite/feed/index.1.rss",                   60, 10),
  ("Python News",        "http://www.python.org/dev/peps/peps.rss",                                60, 30),
  ("CNN Top Stories",    "http://rss.cnn.com/rss/cnn_topstories.rss",                              15, 10),
  ("Project Gutenberg",  "http://www.gutenberg.org/feeds/today.rss",                               60, 30),
  ("Yahoo! Top Stories", "http://rss.news.yahoo.com/rss/topstories",                               15,  1),
  ("BBC News",           "http://feeds.bbci.co.uk/news/rss.xml",                                   15, 10)
]

if use_threads:
	dlthreads.start()
new_data = {}		# global hash for freshly-downloaded feed content

class InternetConnectivity:
	"A class to test if the Internet is reachable."
	def __init__(s):
		s.host = "www.yahoo.com"
		s.status = False
		s.override = False	# allows the user to set offline mode manually
		s.lastchecked = time.time()
		s.app_start = True

	def check(s):
		"Determine if the Internet can be reached by trying to resolve the given hostname."
		if s.status: delta = 90
		else: delta = 30
		if s.override: return False
		# Check regularly, but give the GUI an initial two seconds to fully draw itself:
		if time.time() - s.lastchecked > delta or (
				s.app_start and time.time() - s.lastchecked > 2):
			s.lastchecked = time.time()
			try: t = socket.getaddrinfo(s.host, 'http')
			except: s.status = False
			else: s.status = True
			s.app_start = False
		return s.status

	def text_status(s):
		"Return status text for title bar."
		if s.override: return " *offline* (manual override)"
		elif s.status or s.app_start: return ""
		else: return " *offline*"
		
netchecker = InternetConnectivity()

class History:
	"A class to keep track of the selected items, for use with the Forward and Back buttons."
	def __init__(s):
		s.items = []
		s.active_item = 0
		s.max_len = 200		# maximum number of history items

	def add(s, x):
		"Add an item x to the history."
		ihash = gethash(x.title, x.descr)
		ifeed = x.fromfeed
		if not s.items:
			s.items = [[ihash, ifeed]]
			return
		elif s.items[s.active_item][0] != ihash:
			s.active_item += 1
			if s.active_item == len(s.items):
				s.items.append([ihash, ifeed])
			else:
				s.items[s.active_item] = [ihash, ifeed]
				s.items = s.items[:s.active_item + 1]
		d = len(s.items) - s.max_len
		if d > 0:
			s.items = s.items[d:]
			s.active_item -= d
		if s.active_item < 0:
			s.active_item = 0

	def is_first(s):
		"Are we at the first item of the history?"
		return not s.active_item

	def is_last(s):
		"Are we at the last item of the history?"
		return s.active_item == len(s.items) - 1

	def get_previous(s):
		"Get index of previous item in history."
		a, b = None, None
		while (a, b) == (None, None) and not s.is_first():
			s.active_item -= 1
			a, b = s._find_item()
		return a, b

	def get_next(s):
		"Get index of next item in history."
		a, b = None, None
		while (a, b) == (None, None) and not s.is_last():
			s.active_item += 1
			a, b = s._find_item()
		return a, b

	def _find_item(s):
		"Find the current history item in the feed list."
		global newsfeeds

		for f in range(len(newsfeeds)):
			if newsfeeds[f].name == s.items[s.active_item][1]:
				for x in range(len(newsfeeds[f].content)):
					title = newsfeeds[f].content[x].title
					descr = newsfeeds[f].content[x].descr
					ihash = gethash(title, descr)
					if s.items[s.active_item][0] == ihash:
						return f, x

		# If we get here the user has presumably changed the feed name,
		# so we simply ignore it this time:
		for f in range(len(newsfeeds)):
			for x in range(len(newsfeeds[f].content)):
				title = newsfeeds[f].content[x].title
				descr = newsfeeds[f].content[x].descr
				ihash = gethash(title, descr)
				if s.items[s.active_item][0] == ihash:
					return f, x
		return None, None

history = History()

class ContentItem:
	"A channel content class."
	def __init__(s, title, descr, link, date, fromfeed = "", enclosure = []):
		s.title     = title
		s.descr     = descr
		s.link      = link
		s.date      = date
		s.fromfeed  = fromfeed
		s.enclosure = enclosure
		s.unread    = True
		s.marked    = False
		s.link_visited = False

	def show(s, num):
		"Print item info for console interface."
		print("[%2u] %s" % (num, s.get_title()))
		if s.descr != "(none)":
			print(s.descr)
		print("%80s" % s.link)

	def get_p_title(s):
		"Return textbox title of item."
		title = htmlrender(stripcontrol(s.title)).strip()
		title = re.sub("<.*?>", "", title)
		if not title:
			title = htmlrender(stripcontrol(s.descr))
			title = re.sub("<.*?>", "", title)
			if len(title) > 80:
				title = title[:80] + "..."
		if title == title.upper(): title = title_caps(title)
		title = [x for x in title.split() if x not in ('{/', '{[', ']}')]
		return ' '.join(title)

	def get_title(s):
		"Return listview title of item. Add parentheses if read; add exclamation marks if marked."
		title = s.get_p_title()
		try: marked = s.marked
		except: marked = False
		if marked: title = " !!!  " + title
		if s.unread: return title
		else: return "  (" + title + ")"

	def get_s_title(s):
		"Return title of item as seen in search results."
		return s.get_title() + " [" + s.fromfeed + "]"

	def get_date(s):
		"Return the date of the item."
		return s.date

	def has_enclosure(s):
		"Does the item have an enclosure attached?"
		try: return s.enclosure != []
		except: return False

class NewsWire:
	"A channel class that stores its content in s.contents"
	def __init__(s, url = "", name = "", homeurl = "",
			refresh = config['refresh_every'], expire = config['maxtime']):
		if url == "": raise IOError
		s.url        = url
		s.name       = name
		s.descr      = ""
		s.homeurl    = homeurl
		s.refresh    = refresh
		s.expire     = expire
		s.content    = []
		s.headlines  = {}
		s.u_time     = 0		# Time of last update
		s.failed     = False
		s.lastresult = None		# Store last result for conditional GET

	def get_name(s):
		"Return newsfeed name, optionally with number of unread items."
		if s.failed or not s.content: return "  [" + s.name + "]"
		num_unread = s.get_unread()
		if num_unread: return s.name + " (" + str(num_unread) + ")"
		else: return s.name

	def get_unread(s):
		"Return number of unread items in newsfeed."
		return len([x for x in s.content if x.unread])

	def _get_atom(s, l):
		"Get HTML or text content from Atom feed."
		if not l: return ""
		res = ""
		for x in l:
			t = x.get("type", "").lower()
			if "html" in t or "text" in t or not t:
				res = x.get("value", "")
		return res

	def _get_diff(s, a, b, only_added = False):
		"Get a difference between the texts a and b."
		x = difflib.ndiff(a.splitlines(1), b.splitlines(1))
		if only_added: x = [y[2:] for y in x if y[0] == '+' and len(y) > 5]
		return '<br>'.join(x)

	def url_is_webpage(s):
		"Does the feed URL point to text instead of XML?"
		if s.url == 'http://':
			return False
		try: s.is_webpage
		except: s.update_content_type()
		return s.is_webpage

	def update_content_type(s):
		"Update feed type (HTML or XML) global variable."
		c = s._get_content_type()
		if 'html' in c: s.is_webpage = True
		else: s.is_webpage = False

	def _get_content_type(s):
		"Get the URL content type, differentiate between HTML and XML."
		if '.htm' in s.url.split('/')[-1]:
			return 'text/html'
		try:
			ugen = urllib.request.urlopen(s.url)
			th = ugen.info().typeheader

			# some servers mistakenly report "text/html" for XML files,
			#   so check the actual page content:
			if 'xml' not in th:
				rawhtml = ugen.read()
				if '<?xml' in rawhtml or '<rss' in rawhtml: return 'text/xml'
				elif '<html' in rawhtml.lower(): return 'text/html'
				else: return th
			else: return th
		except: return '(None)'

	def get_news(s, refresh = False):
		"Get news items from the Web and decode to instance variables."
		result = {}
		newcontent = []

		if s.homeurl == "" or s.homeurl == "http://":
			try: s.homeurl = re.compile("http://([^/]+)/").match(s.url).expand("\g<0>")
			except: pass

		if (s.content == [] or s.failed or refresh) and s.url not in ('', "http://"):

			# For backwards compatibility:
			try: s.lastresult
			except AttributeError:
				s.lastresult = {}
				s.lastresult['etag'] = ''
				s.lastresult['modified'] = ''
			try: s.webpage
			except AttributeError: s.webpage = ''

			if s.url_is_webpage():
				try:
					rawhtml = new_data.get(s.url)
					if rawhtml == "failed": raise TypeError
				except:
					s.failed = True
					return 0
				else: s.failed = False
				if not rawhtml: return 0
				result = {}
				result['items'] = []
				result['channel'] = {'title' : s.url}
				webpage = stripcontrol(rawhtml, keep_newlines = True)
				di = s._get_diff(s.webpage, webpage, only_added = True)
				if di:
					s.webpage = webpage
					if not s.u_time: s.u_time = approx_time()
					dip = ' '.join([x for x in di.split() if x[0] != '{'])

					result['items'].append({'title': '%s' %
						htmlrender(stripcontrol(dip))[:80],
						'description': di, 'link': s.url})
				else:
					return 0
			else:
				# Parse the data, return a dictionary:
				try:
					result = new_data.get(s.url)
					if result == "failed": raise TypeError
					result['bozo_exception'] = ""
					s.lastresult = result
					if not len(result['items']): return 0
					if not s.u_time: s.u_time = approx_time()
				except:
					s.failed = True
					return 0
			s.title  = result['channel'].get('title', "").strip()
			if s.name[0] == '?' and s.title: s.name = s.title
			s.date   = (result['channel'].get('modified',
				time.strftime("%Y-%m-%d %H:%M", time.localtime(s.u_time))).strip())
			try:
				s.descr  = ( result['channel'].get('description', "").strip() or
					result['channel'].get('summary', s.descr).strip() )
			except: s.descr = ""
			for item in result['items']:
				# Each item is a dictionary mapping properties to values
				descr = ( item.get('description', "") or
					     s._get_atom(item.get('content', "")) or
					     item.get('summary', "") or
					     "No description available." )
				title = item.get('title', re.sub("<.*?>", "", descr)[:80])
				hash = gethash(title, descr)
				if hash not in list(s.headlines.keys()):
					s.headlines[hash] = s.u_time
					link  = item.get('link', "(none)")
					date  = item.get('modified', s.date)
					enc   = item.get('enclosures', [])
					newcontent.append(ContentItem(title, descr, link,
							date, fromfeed = s.name, enclosure = enc))
			s.content = newcontent + s.content

			for i in list(s.headlines.keys()):
				if (time.time() - s.headlines[i]) / 86400 > s.expire:
					for j in range(len(s.content) - 1, -1, -1):
						try: marked = s.content[j].marked
						except: marked = False
						if (gethash(s.content[j].title, s.content[j].descr) == i
						  and not marked):
							del s.content[j]
							s.headlines[i] = None
			for i in list(s.headlines.keys()):
				if s.headlines[i] == None: del s.headlines[i]
		return len(newcontent)

	def print_news(s):
		"Print items to screen and open selected item's URI in browser."
		if not isinstance(s, SearchWire):
			if (time.time() - s.u_time) / 60. > s.refresh:
				s.u_time = time.time()
				s.get_news(refresh = True)
			else:
				s.get_news()
		else:
			s.get_news()
		if s.content == []:
			print("\nCurrently no newsfeed. Please try again later.")
			return
		try:
			print("\n%80s" % s.date)
		except:
			pass
		if s.name != "": print(s.name, "--", end=' ')
		try:
			print(s.title)
		except:
			print()
		print(80 * '=')
		print()
		i = 1
		for item in s.content:
			item.show(i)
			item.unread = False
			print()
			i = i + 1
		while 1:
			try:
				topic = eval(input("\nPlease select your topic (\"0\" to go back to menu): "))
			except SyntaxError:
				continue
			if 0 < topic <= len(s.content):
				s.content[topic-1].link_visited = True
				open_url(s.content[topic-1].link)
			else: break

class SearchWire(NewsWire):
	"A class for searches in newsfeeds."
	def __init__(s, terms, method = "exact", case = 0, words = 0, only_unread = 0):
		s.terms      = terms.strip()
		s.method     = method
		s.case       = case
		s.words      = words
		s.only_unread = only_unread
		if not case: s.terms = s.terms.lower()
		s.name       = "Search for '" + s.terms + "'"
		s.content    = []
		s.headlines  = {}
		s.u_time     = approx_time()	# Time of last update
		s.failed     = False

	def get_news(s, refresh = False):
		"Search for 'terms' in other newsfeeds."
		if s.content and not refresh: return 0
		keepcontent  = []
		newcontent   = []
		oldheadlines = s.headlines
		s.headlines  = {}
		s.u_time     = approx_time()

		while "\\b" in s.terms:
			s.terms = s.terms[2:-2]
		if s.words: terms = "\\b" + s.terms + "\\b"
		else: terms = s.terms
		if not s.case: find = re.compile(terms, re.IGNORECASE)
		else: find = re.compile(s.terms)
		if s.content == [] or s.failed or refresh:
			for f in [x for x in newsfeeds if not isinstance(x, SearchWire)]:
				for t in f.content:
					if find.search(t.title) or find.search(t.descr):
						if not s.only_unread or (s.only_unread and t.unread):
							t.fromfeed = f.name
							newcontent.append(t)
							hash = gethash(t.title, t.descr)
							s.headlines[hash] = f.headlines.get(
									hash, s.u_time)
		if s.only_unread:
			keepcontent = [x for x in s.content if not x.unread]
			for t in keepcontent:
				hash = gethash(t.title, t.descr)
				s.headlines[hash] = oldheadlines.get(hash, s.u_time)
		s.content = keepcontent + newcontent
		s.sort_items()
		return 0

	def sort_items(s):
		s.content.sort(key=lambda r: -_by_time_order(r))

class Recently_visited(SearchWire):
	"A class that shows the articles that were opened recently."
	def __init__(s):
		s.name       = "RECENTLY VISITED"
		s.content    = []
		s.headlines  = {}
		s.u_time     = approx_time()	# Time of last update
		s.failed     = False

	def get_news(s, refresh = False):
		s.content = []
		for f in [n for n in newsfeeds if not isinstance(n, SearchWire)]:
			res = [z for z in f.content if z.link_visited]
			s.content += res
			for t in res:
				hash = gethash(t.title, t.descr)
				s.headlines[hash] = f.headlines.get(hash, s.u_time)
		return 0

class Marked_items(SearchWire):
	"A class that shows the articles that were marked as important."
	def __init__(s):
		s.name       = "IMPORTANT ITEMS"
		s.content    = []
		s.headlines  = {}
		s.u_time     = approx_time()	# Time of last update
		s.failed     = False

	def get_name(s):
		"Return newsfeed name and its item count."
		n = SearchWire.get_name(s)
		i = len(s.content)
		if i: return "%s [%u]" % (n, i)
		else: return n

	def get_news(s, refresh = False):
		s.content = []
		for f in [n for n in newsfeeds if not isinstance(n, SearchWire)]:
			res = []
			for z in f.content:
				try: ismarked = z.marked
				except: ismarked = False
				if ismarked: res.append(z)
			s.content += res
			for t in res:
				hash = gethash(t.title, t.descr)
				s.headlines[hash] = f.headlines.get(hash, s.u_time)
		return 0

def add_feeds(obj):
	"Accept a list of tuples and add them to the global newsfeed pool."
	global newsfeeds, config

	for i in obj:
		try:
			if len(i) > 2: newsfeeds.append(NewsWire(i[1], name=i[0],
						refresh = i[2], expire = i[3]))
			else: newsfeeds.append(NewsWire(i[1], name=i[0]))
		except IOError:
			print("Error: Could not find a suitable newsfeed.")

def add_feeds_helper(signum = None, frame = None):
	"Add feeds from helper script. Called at the beginning of the program and when SIGUSR1 is received."
	global newsfeeds, config

	try:
		for x in open(addfeed_file, 'r').readlines(): add_feeds((("?New Feed", x.strip()),))
		os.unlink(addfeed_file)
	except: pass
	if sys.platform != 'win32':
		signal.signal(signal.SIGUSR1, add_feeds_helper)

def _load_older_revision():
	"Look for an older revision of the config file if the current one does not exist."
	global newsfeeds, config

	for x in range(1, 100):
		name = "%s.%u" % (config_file, x)
		try:
			newsfeeds, config = pickle.load(open(name, 'rb'))
			print("*** Configuration file %s is unreadable or nonexistent." % config_file)
			print("*** Using older revision %s instead." % name)
			return
		except: pass
	# Load a default configuration if nothing suitable is found on disk:
	print("*** No configuration file found, loading defaults.")
	add_feeds(initial)

def load_feeds():
	"Load feeds and configuration data from file."
	global newsfeeds, config

	try: newsfeeds, config = pickle.load(open(config_file, 'rb'))
	except: _load_older_revision()
	if not [x for x in newsfeeds if isinstance(x, Recently_visited)]:
		newsfeeds = [Recently_visited()] + newsfeeds
	if not [x for x in newsfeeds if isinstance(x, Marked_items)]:
		newsfeeds += [Marked_items()]
	if 'fontscaling' not in config.keys():
		config['fontscaling'] = 1.

def version_file(filename, num_revs):
	"Perform a VMS-like versioning of file, keeping at most num_revs old copies."
	if num_revs < 1: return
	if num_revs > 99: num_revs = 99
	for x in range(num_revs, 1, -1):
		ofile = "%s.%u" % (filename, x - 1)
		nfile = "%s.%u" % (filename, x)
		move_file(ofile, nfile)
	move_file(filename, filename + ".1")

def save():
	"Save document cache and configuration options."
	try: pickle.dump((newsfeeds, config), open(config_file + ".current", 'wb'), 1)
	except:
		print("*** Error: Configuration file could not be written to disk.")
		return False
	else:
		version_file(config_file, old_revisions_to_keep)
		move_file(config_file + ".current", config_file)
		return True
		
def move_file(x, y):
	"Move file x to name y, trying to delete y first to accommodate Windows."
	try: os.unlink(y)
	except: pass
	try: os.rename(x, y)
	except: pass

def quit(event = ""):
	"Exit Program."
	sys.exit(0)

def open_url(url):
	"Open URL in browser."
	try:
		if browser_cmd: os.system(browser_cmd % url)
	except:
		try:
			if open_in_new_window:
				webbrowser.open_new(url)
			else:
				webbrowser.open(url, new = False)
		except:
			sys.stderr.write("*** Error: Opening browser failed for URL '%s'.\n" % url)

def open_enclosure(url):
	"Open enclosure URL."
	if media_player:
		command = '%s "%s"' % (media_player, url)
		os.system(command)
	else: open_url(url)

def approx_time():
	"Return an approximate timestamp, so that feeds and stories stay in sync."
	return 10. * int(time.time() / 10)

def plural_s(i):
	"Return an 's' if i > 1."
	if i > 1: return 's'
	return ""

def about_equal(x, y):
	"Test if two floating point numbers are very close to each other."
	eps = .0001

	if abs(x - y) < eps: return True
	else: return False

def _by_time_order(x):
	"Function for sorting items by download time."
	return newsfeeds[app.sel_f].headlines.get(gethash(x.title, x.descr), 0)

def title_caps(t):
	"Do a decent title capitalization."
	words = ["a", "an", "the", "some", "and", "but", "of",
				"on", "or", "nor", "for", "with", "to", "at"]
	t = t.title()
	t = t.replace("'S", "'s")
	for i in words: t = t.replace(" %s " % i.title(), " %s " % i)
	return t

def unemoji(t):
	"Replace emoji characters with white square character as Tcl/Tk cannot display them"
	# ( from http://stackoverflow.com/questions/13729638/how-can-i-filter-emoji-characters-from-my-input-so-i-can-save-in-mysql-5-5 )
	try:
		# UCS-4
		highpoints = re.compile(u'[\U00010000-\U0010ffff]')
	except re.error:
		# UCS-2
		highpoints = re.compile(u'[\uD800-\uDBFF][\uDC00-\uDFFF]')
	# mytext = u'<some string containing 4-byte chars>'
	t = highpoints.sub(u'\u25FD', t)
	return t

def stripcontrol(t, keep_newlines = False):
	"Strip control characters from t."
	if keep_newlines:
		subs = ('\r', ''),
	else:
		subs = ('\r', ''), ('\n', ' ')
	for i in subs: t = t.replace(i[0], i[1])
	return t

def _entity_unicode(p):
	"Helper function for entity substitution."
	x = p.group(1)
	y = ""
	for i in x:
		if i.isdigit(): y += i
		else: break
	try: return chr(int(y))
	except: return '_'

class MyHTMLParser(HTMLParser):
	"Parser for htmlrender function."
	def __init__(s):
		s.out = ''
		super().__init__()
	def handle_starttag(s, t, a):
		if t == 'a':
			for at in a:
				if at[0] == 'href':
					s.out += ' {[ ' + at[1] + ' | '
		if t == 'br':
			s.out += ' {/ '
		if t == 'b':
			s.out += '*'
		if t == 'strong':
			s.out += '**'
		if t == 'u':
			s.out += '_'
		if t == 'i' or t == 'em':
			s.out += '~'
		if t == 'img':
			s.out += '[Image]'
		if t == 'blockquote':
			s.out += ' {/ {/ '
		if t == 'li':
			s.out += ' {/ *'
	def handle_endtag(s, t):
		if t == 'a':
			s.out += ' ]} '
		if t == 'p':
			s.out += ' {/ {/ '
		if t == 'b':
			s.out += '*'
		if t == 'strong':
			s.out += '**'
		if t == 'u':
			s.out += '_'
		if t == 'i' or t == 'em':
			s.out += '~'
		if t == 'li':
			s.out += ' {/ '
	def handle_data(s, d):
		s.out += d
	def handle_entityref(s, n):
		s.out += entdic.get(n + ';', '&' + n)
	def handle_charref(s, c):
		if c.startswith('x'):
			s.out += chr(int(c[1:], 16))
		else:
			s.out += chr(int(c))

def htmlrender(t):
	"Transform HTML markup to printable text."
	parser = MyHTMLParser()
	try:
		parser.feed(t)
	except:
		return t
	else:
		return parser.out

def _find_next(t, i, p):
	"Find index of next occurence of pattern p in t starting from index i. Return i if p is not found."
	for x in range(i, len(t)):
		if t[x] == p: return x
	return i

def gethash(*args):
	"Compute the MD5 hash of the arguments concatenated together."
	h = md5()
	for i in args:
		if type(i) != type(""): h.update(i)
		else: h.update(i.encode("utf-8", "replace"))
	return h.hexdigest()

def get_content_unicode(url):
	"Get the URL content and convert to Unicode."
	ugen = urllib.request.urlopen(url)
	rawhtml = ugen.read()
	content_type = 'iso-8859-1'
	th = ugen.info().typeheader
	if 'charset' in th:
		content_type = th.split('=')[-1]
	elif 'charset=' in rawhtml:
		for x in rawhtml.splitlines(1):
			try:
				c = re.compile('charset=(.+)"').search(x).expand("\g<0>")
				content_type = c.split('=')[-1][0:-1]
			except: pass
			else: break
	try: rawhtml = rawhtml.decode(content_type)
	except:
		sys.stderr.write("*** Warning: Encoding %s not supported by Python, defaulting to iso-8859-1.\n"
					% content_type)
		rawhtml = rawhtml.decode('iso-8859-1')
	return rawhtml

def text_interface():
	"Present the user with a simple textual interface to the RSS feeds."
	if newsfeeds:
		while 1:
			print("\nAvailable newsfeeds:\n")
			for i in range(len(newsfeeds)):
				print("[%2u] %s" % (i+1,
					newsfeeds[i].get_name()))
			try:
				feed = eval(input("\nPlease select your feed (\"0\" to quit): "))
			except SyntaxError: continue
			if 0 < feed <= len(newsfeeds):
				newsfeeds[feed-1].print_news()
			else: quit()

class TkApp:
	"GUI class for use with the Tk interface."
	def __init__(s, parent):
		s.sel_f  = -1		# Index of selected feed (0..(n-1))
		s.sel_t  = -1		# Index of selected topic in feed (0..(n-1))
		s.parent = parent
		s.refresh_feeds     = []	# List of feeds to update right now
		s.num_refresh_feeds = 0 	# Number of feeds to update
		s.num_done_feeds    = 0		# Number of currently updated feeds
		s.refresh_now       = 0		# Stage of refresh flag
		s.num_empty_feeds   = 0		# Total number of empty feeds
		s.idle_since        = time.time()	# Time of last user interaction
		s.last_saved        = time.time()	# Time of last save to file
		s.total_unread      = 0		# Total number of unread items
		s.cursor_state      = ["normal", "visible"]	# Current mouse pointer state
		s.widescreen        = config.get("widescreen", False)

		s.infowin   = ""
		s.searchwin = ""

		# Frames:
		f1 = Frame(parent)
		f1.pack(side = TOP, expand = 0, fill = X)
		f2 = Frame(parent)
		f2.pack(side = BOTTOM, expand = 1, fill = BOTH)
		f3 = Frame(f1)
		f3.pack(side = LEFT, expand = 1, fill = BOTH)
		f4 = Frame(f1)
		f4.pack(side = RIGHT, expand = 1, fill = BOTH)
		f5 = Frame(f2)
		f5.pack(side = LEFT, expand = 0, fill = Y)
		s.f6 = Frame(f2)
		s.f6.pack(side = RIGHT, expand = 1, fill = BOTH)

		s.add_content_area()

		# Buttons:
		s.b_refresh = Button(f3, text = "Refresh Now", command = s.refresh)
		s.b_refresh.pack(side = LEFT)
		s.b_info = Button(f3, text = "Edit Channel", command = s.info)
		s.b_info.pack(side = LEFT)
		s.b_sub = Button(f3, text = "Subscribe", command = s.sub)
		s.b_sub.pack(side = LEFT)
		s.b_unsub = Button(f3, text = "Unsubscribe", command = s.unsub)
		s.b_unsub.pack(side = LEFT)
		s.b_search = Button(f3, text = "Search News", command = s.new_search)
		s.b_search.pack(side = LEFT)

		s.b_delall = Button(f4, text = "Delete All", command = s.delete_all_in_feed)
		s.b_delall.pack(side = RIGHT)
		s.b_del = Button(f4, text = "Delete", command = s.delete_one)
		s.b_del.pack(side = RIGHT)
		s.b_allread = Button(f4, text = "Mark All As Read", command = s.mark_all_as_read)
		s.b_allread.pack(side = RIGHT)
		s.b_next = Button(f4, text = "Next Unread", command = s.next_unread)
		s.b_next.pack(side = RIGHT)

		# Listboxes and Text widget:
		f9 = Frame(f5)
		f9.pack(side = BOTTOM, fill = BOTH)
		s.pbar = Canvas(f9, width = 120, height = 24)
		s.pbar.pack(side = TOP, fill = BOTH)
		s.pbar.create_rectangle(0, 4, 150, 22, fill = "white")
		s.pbarline = s.pbar.create_rectangle(0, 4, 0, 22, fill = "#009b2e")

		f_ud = Frame(f5)
		f_ud.pack(side = BOTTOM, expand = 0, fill = X)
		f_ud1 = Frame(f_ud)
		f_ud1.pack(side = LEFT, expand = 1, fill = X)
		f_ud2 = Frame(f_ud)
		f_ud2.pack(side = RIGHT, expand = 1, fill = X)
		s.b_up = Button(f_ud1, text = "Move Up", command = s.up)
		s.b_up.pack(side = LEFT, expand = 1, fill = X)
		s.b_dn = Button(f_ud2, text = "Move Down", command = s.down)
		s.b_dn.pack(side = RIGHT, expand = 1, fill = X)

		s.lb_scr = Scrollbar(f5)
		s.lb_scr.pack(side = RIGHT, fill = Y)
		s.lb = Listbox(f5, width = 24, selectmode = SINGLE, yscrollcommand = s.lb_scr.set)
		for i in newsfeeds:
			s.lb.insert(END, i.get_name())
		s.lb.config(background = "#96c8ff", selectforeground = "white",
							selectbackground = "#328bff")
		s.lb.pack(side = TOP, expand = 1, fill = BOTH)
		s.lb_scr.config(command = s.lb.yview)

		s.parent.bind("<space>",     s.next_keyb)
		s.parent.bind("s",           s.new_search)
		s.parent.bind("R",           s.refresh)
		s.parent.bind("r",           s.refresh_this)
		s.parent.bind("e",           s.info)
		s.parent.bind("i",           s.iconify)
		s.parent.bind("m",           s.mark_all_as_read_keyb)
		s.parent.bind("n",           s.mark_unmark)
		s.parent.bind("C",           s.catch_up)
		s.parent.bind("<Return>",    s.open)
		s.parent.bind("o",           s.toggle_offline)
		s.parent.bind("h",           s.open_home)
		s.parent.bind("v",           s.open_visited)
		s.parent.bind("N",           s.open_marked)
		s.parent.bind("<BackSpace>", s.delete_one)
		s.parent.bind("d",           s.delete_one)
		s.parent.bind("q",             quit)
		s.parent.bind("<Prior>",     s.page_up)
		s.parent.bind("<Next>",      s.page_down)
		s.parent.bind("<Up>",        s.previous_topic)
		s.parent.bind("<Down>",      s.next_topic)
		s.parent.bind("<Left>",      s.previous_feed)
		s.parent.bind("<Right>",     s.next_feed)
		s.parent.bind("<End>",       s.last_page)
		s.parent.bind("<Home>",      s.first_page)
		s.parent.bind("<less>",      s.back)
		s.parent.bind(">",           s.forward)
		s.parent.bind("[",           s.back)
		s.parent.bind("]",           s.forward)
		s.parent.bind("+",           s.larger_font)
		s.parent.bind("-",           s.smaller_font)
		s.parent.bind("x",           s.export_item)
		s.parent.bind("w",           s.toggle_wide)
		s.parent.bind("<Motion>",    s._show_cursor)

		s.parent.focus()

		parent.after(250, s.beat)

	def add_content_area(s, event =""):
		"Add the list of items in a feed and the text area for item content."
		if not s.widescreen:
			s.f7 = Frame(s.f6)
			s.f7.pack(side = TOP, expand = 1, fill = BOTH)
			s.f8 = Frame(s.f6)
			s.f8.pack(side = BOTTOM, expand = 1, fill = BOTH)
			date_width, text_width = 30, 80
		else:
			s.f7 = Frame(s.f6)
			s.f7.pack(side = LEFT, expand = 1, fill = BOTH)
			s.f8 = Frame(s.f6)
			s.f8.pack(side = RIGHT, expand = 1, fill = BOTH)
			date_width, text_width = 20, 25

		s.r1b_scr = Scrollbar(s.f7)
		s.r1b_scr.pack(side = RIGHT, fill = Y)
		s.r11b = Listbox(s.f7, selectmode = SINGLE, width = date_width, yscrollcommand = s.r1b_scr.set)
		for i in newsfeeds[0].content:
			s.r11b.insert(END, i.date)
		s.r11b.config(background = "#ffefaf", selectforeground = "white",
							selectbackground = "#328bff")
		s.r11b.pack(side = RIGHT, expand = 0, fill = BOTH)

		s.r1b = Listbox(s.f7, selectmode = SINGLE, yscrollcommand = s.r1b_scr.set)
		for i in newsfeeds[0].content:
			s.r1b.insert(END, unemoji(i.get_title()))
		s.r1b.config(background = "#ffefaf", selectforeground = "white",
							selectbackground = "#328bff")
		s.r1b.pack(side = TOP, expand = 1, fill = BOTH)
		s.r1b_scr.config(command = s._yview)

		s.r2b_scr = Scrollbar(s.f8)
		s.r2b_scr.pack(side = RIGHT, fill = Y)
		s.r2b = Text(s.f8, wrap = WORD, cursor = "", width = text_width, yscrollcommand = s.r2b_scr.set)
		s.r2b.config(state = DISABLED,
				foreground = tp_foreground, background = tp_background,
				selectforeground = tps_foreground, selectbackground = tps_background)
		s.r2b.pack(side = BOTTOM, expand = 1, fill = BOTH)
		s.r2b_scr.config(command = s.r2b.yview)

	def larger_font(s, event = ""):
		"Increase font size."
		global config

		if config['fontscaling'] < 2.3: config['fontscaling'] += .2
		if about_equal(config['fontscaling'], 1.4) or about_equal(config['fontscaling'], 1.8):
			s.larger_font()
			return
		s.change_content(feed = s.sel_f, topic = s.sel_t)

	def smaller_font(s, event = ""):
		"Decrease font size."
		global config

		if config['fontscaling'] > .7: config['fontscaling'] -= .2
		if about_equal(config['fontscaling'], 1.4) or about_equal(config['fontscaling'], 1.8):
			s.smaller_font()
			return
		s.change_content(feed = s.sel_f, topic = s.sel_t)

	def toggle_wide(s, event = ""):
		"Toggle widescreen view."
		s.widescreen = not s.widescreen
		s.f7.destroy()
		s.f8.destroy()
		s.add_content_area()
		s.change_content(feed = s.sel_f, topic = s.sel_t)
		config["widescreen"] = s.widescreen

	def toggle_offline(s, event = ""):
		"Toggle offline mode manually."
		netchecker.override = not netchecker.override
		s._window_title(s.sel_f)

	def iconify(s, event = ""):
		"Iconify the application."
		s.parent.iconify()

	def _yview(s, *args):
		"Update the message header and date listbox in unison."
		s.r11b.yview(*args)
		s.r1b.yview(*args)

	def next_feed(s, event = ""):
		"Jump to next feed."
		s._hide_cursor()
		if s.sel_f < len(newsfeeds) - 1: s.change_content(feed = s.sel_f + 1)

	def previous_feed(s, event = ""):
		"Jump to previous feed."
		s._hide_cursor()
		if s.sel_f: s.change_content(feed = s.sel_f - 1)

	def next_topic(s, event = ""):
		"Jump to next topic."
		s._hide_cursor()
		if s.sel_t < len(newsfeeds[s.sel_f].content) - 1:
			s.change_content(feed = s.sel_f, topic = s.sel_t + 1)

	def previous_topic(s, event = ""):
		"Jump to previous topic."
		s._hide_cursor()
		if s.sel_t:
			s.change_content(feed = s.sel_f, topic = s.sel_t - 1)

	def line_down(s, event = ""):
		"Scroll text widget down one line."
		s._hide_cursor()
		s.r2b.yview(SCROLL, 1, UNITS)

	def line_up(s, event = ""):
		"Scroll text widget up one line."
		s._hide_cursor()
		s.r2b.yview(SCROLL, -1, UNITS)

	def page_down(s, event = ""):
		"Scroll text widget down one page."
		s._hide_cursor()
		s.r2b.yview(SCROLL, 1, PAGES)

	def page_up(s, event = ""):
		"Scroll text widget up one page."
		s._hide_cursor()
		s.r2b.yview(SCROLL, -1, PAGES)

	def last_page(s, event = ""):
		"Go to last page of text."
		s._hide_cursor()
		s.r2b.yview(MOVETO, 1.0)

	def first_page(s, event = ""):
		"Go to first page of text."
		s._hide_cursor()
		s.r2b.yview(MOVETO, 0.0)

	def open_visited(s, event = ""):
		"Jump to the feed containing the recently visited items."
		s._hide_cursor()
		for x in range(len(newsfeeds)):
			if isinstance(newsfeeds[x], Recently_visited):
				s.change_content(feed = x)
				return

	def open_marked(s, event = ""):
		"Jump to the feed containing the marked items."
		s._hide_cursor()
		for x in range(len(newsfeeds)):
			if isinstance(newsfeeds[x], Marked_items):
				s.change_content(feed = x)
				return

	def progress(s):
		"Return the current progress value in percent."
		try: return 100 * float(s.num_done_feeds) / float(s.num_refresh_feeds)
		except ZeroDivisionError: return 0

	def draw_bar(s, p):
		"Draw a progress bar while updating the feeds."
		if p > 100 or p < 0: p = 0
		s.pbar.coords(s.pbarline, 1, 4, int(1.5 * p), 22)

	def _update_feed_list(s):
		"Update the list of feeds."
		s.lb.delete(0, END)
		for i in newsfeeds:
			feedname = s._active(i.get_name(), i, newsfeeds[s.sel_f])
			s.lb.insert(END, feedname)

	def _window_title(s, feed):
		"Update the Root window title."
		title = "%s - %s" % (newsfeeds[feed].name, config['progname'])
		i = 0
		j = 0
		for f in newsfeeds:
			if not isinstance(f, SearchWire):
				num_unread = f.get_unread()
				i = i + num_unread
				if num_unread: j = j + 1
		if i:
			title = "%s (%u unread item%s in %u channel%s)" % (
				title, i, plural_s(i), j, plural_s(j))
			iconname = "%u unread" % i
		else: iconname = config['progname']
		title += netchecker.text_status()
		s.parent.title(title)
		if s.refresh_feeds: iconname = "%u (%2u%%)" % (i, s.progress())
		s.parent.iconname(iconname)

		# Play notification sound if there are new unread messages:
		if not s.total_unread and i:
			if soundfile != "none":
				try:
					sound.playFile(soundfile)
				except:
					print("Audio file", soundfile, "not found or audio interface unavailable!")
		s.total_unread = i

	def _active(s, str, a, b, mark = 0):
		"Return an 'active' version of str if a == b."
		if a == b and mark: return str.replace(' ', '_') + 200 * '_'
		elif a == b:
			try: return str.upper()
			except: return str
		else: return str

	def change_content(s, feed = -1, topic = -1):
		"Switch to a different content item."
		global newsfeeds, history

		feed  = int(feed)
		topic = int(topic)
		if feed >= len(newsfeeds): feed = len(newsfeeds) - 1
		if feed < 0: feed = 0
		newsfeeds[feed].get_news()
		if topic >= len(newsfeeds[feed].content): topic = len(newsfeeds[feed].content) - 1
		if ((feed != s.sel_f and isinstance(newsfeeds[feed], SearchWire))
		    or isinstance(newsfeeds[feed], Recently_visited)
		    or isinstance(newsfeeds[feed], Marked_items)):
			s.sel_f = feed
			newsfeeds[s.sel_f].sort_items()
		if topic == -2:
			for n, q in enumerate(newsfeeds[feed].content):
				if q.unread:
					topic = n
					break
		if topic < 0: s.sel_t = 0
		else: s.sel_t = topic
		s.sel_f = feed

		if isinstance(newsfeeds[s.sel_f], SearchWire):
			s.b_info.config(state = DISABLED)
			if newsfeeds[s.sel_f].content:
				history.add(newsfeeds[s.sel_f].content[s.sel_t])
				if newsfeeds[s.sel_f].content[s.sel_t].unread:
					newsfeeds[s.sel_f].content[s.sel_t].unread = False
					item = newsfeeds[s.sel_f].content[s.sel_t]
					hash = gethash(item.title, item.descr)
					for f in newsfeeds:
						if f is not newsfeeds[s.sel_f]:
							for t in [x for x in f.content if gethash(
								x.title, x.descr) == hash]:
								t.unread = False
			items = [x.get_s_title() for x in newsfeeds[s.sel_f].content]
		else:
			if s.b_info.cget("state") == "disabled": s.b_info.config(state = NORMAL)
			if newsfeeds[s.sel_f].content:
				history.add(newsfeeds[s.sel_f].content[s.sel_t])
				newsfeeds[s.sel_f].content[s.sel_t].unread = False
			items = [x.get_title() for x in newsfeeds[s.sel_f].content]

		s._change_text(s.r2b)
		s._change_list(s.r1b, items, s.sel_t)
		s._change_list(s.r11b, [x.get_date() for x in newsfeeds[s.sel_f].content], s.sel_t)
		s._change_list(s.lb, [x.get_name() for x in newsfeeds], s.sel_f)
		s._window_title(s.sel_f)

	def _cursor_over_link(s, event = ""):
		"Mouse pointer is hovering over hyperlink."
		s.cursor_state[0] = "link"
		if s.cursor_state[1] == "hidden": return
		s.parent.config(cursor = "hand2")

	def _cursor_not_over_link(s, event = ""):
		"Mouse pointer is hovering over normal text."
		s.cursor_state[0] = "leavinglink"
		if s.cursor_state[1] == "hidden": return
		s._show_cursor()

	def _hide_cursor(s, event = ""):
		"Hide mouse pointer (during keyboard navigation)."
		if s.cursor_state[1] == "hidden": return
		s.cursor_state[1] = "hidden"
		kNullCursorData = """
  		#define t_cur_width 1
  		#define t_cur_height 1
  		#define t_cur_x_hot 0
  		#define t_cur_y_hot 0
  		static unsigned char t_cur_bits[] = { 0x00 };
 		"""
		try:
			f = open(config_file + "-blank-cursor", 'w')
			f.write(kNullCursorData)
			f.close()
			s.parent.config(cursor = "@%s-blank-cursor white" % config_file)
		except: pass

	def _show_cursor(s, event = ""):
		"Show mouse pointer."
		if s.cursor_state[1] == "visible" and s.cursor_state[0] != "leavinglink": return
		if s.cursor_state[0] == "link":
			s.cursor_state = ["link", "visible"]
			s._cursor_over_link()
		else:
			s.cursor_state = ["normal", "visible"]
			s.parent.config(cursor = "")
			
	def back(s, event = ""):
		"Jump to previous item in history."
		global history

		f, t = history.get_previous()
		if f != None: s.change_content(feed = f, topic = t)

	def forward(s, event = ""):
		"Jump to next item in history."
		global history

		f, t = history.get_next()
		if f != None: s.change_content(feed = f, topic = t)

	def _insert_nav_bar(s, obj):
		"Insert the item-specific navigation toolbar."
		global newsfeeds, config

		obj.insert(END, "",           "NAV")
		obj.insert(END, "  back  ",      "BNAV")
		obj.insert(END, "~",             "NAV")
		obj.insert(END, "  forward    ", "FNAV")
		try: marked = newsfeeds[s.sel_f].content[s.sel_t].marked
		except: marked = False
		if marked: obj.tag_config("MNAV", foreground = "red")
		else: obj.tag_config("MNAV", foreground = "black")
		obj.tag_config("MNAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		obj.tag_config("SNAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		obj.tag_config("LNAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		obj.tag_config("ENAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		obj.tag_config("DNAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		obj.tag_bind("MNAV", "<ButtonRelease-1>", s.mark_unmark)
		obj.tag_bind("MNAV", "<ButtonRelease-2>", s.mark_unmark)
		obj.tag_bind("SNAV", "<ButtonRelease-1>", s.smaller_font)
		obj.tag_bind("ENAV", "<ButtonRelease-1>", s.export_item)
		if about_equal(config['fontscaling'], .6):  obj.tag_config("SNAV", foreground = "#aaaaaa")
		else: obj.tag_config("SNAV", foreground = "black")
		if about_equal(config['fontscaling'], 2.4): obj.tag_config("LNAV", foreground = "#aaaaaa")
		else: obj.tag_config("LNAV", foreground = "black")
		obj.tag_bind("LNAV", "<ButtonRelease-1>", s.larger_font)
		obj.insert(END, "~",             "NAV")
		obj.insert(END, "    smaller  ", "SNAV")
		obj.insert(END, "~",             "NAV")
		obj.insert(END, "  larger    ",  "LNAV")
		obj.insert(END, "~",             "NAV")
		obj.insert(END, "    mark    ",    "MNAV")
		obj.insert(END, "~",             "NAV")
		obj.insert(END, "    export  ",  "ENAV")
		obj.insert(END, "\n\n",        "NAV")

	def mark_unmark(s, event = ""):
		"Toggle the marking status of an item and redraw."
		try: marked = newsfeeds[s.sel_f].content[s.sel_t].marked
		except: marked = False
		marked = newsfeeds[s.sel_f].content[s.sel_t].marked = not marked
		s.change_content(feed = s.sel_f, topic = s.sel_t)

	def export_item(s, event = ""):
		"Export the current item to stdout."
		e = s.r2b.get(1.0, END).split('\n')
		del e[1]
		f = open(export_file, 'w')
		for x in e:
			f.write(x + '\n')
		f.close()
		os.system(export_application % {
			'description_path': export_file,
			'title': (e[2] or 'NewsFeed item')
		})

	def _change_text(s, obj):
		"Change textbox content."
		global history, newsfeeds

		obj.config(state = NORMAL)
		obj.delete(1.0, END)
		obj.config(state = DISABLED)
		if not newsfeeds[s.sel_f].content: return

		obj.config(state = NORMAL)
		obj.tag_config("DATE", foreground = "#00059e", justify = RIGHT, font = ("Courier",
			fontsize['Date']))
		obj.tag_config("DLDATE", foreground = "#00059e", justify = RIGHT, font = ("Courier",
			fontsize['Date']))
		if newsfeeds[s.sel_f].content[s.sel_t].link_visited:
			obj.tag_config("HEADLINE", foreground = "#9600b5", underline = 1,
						font = ("Times", int(config['fontscaling'] * fontsize['Headline'])))
		else: obj.tag_config("HEADLINE", foreground = "blue", underline = 1,
						font = ("Times", int(config['fontscaling'] * fontsize['Headline'])))
		obj.tag_bind("HEADLINE", "<ButtonRelease-1>", s.open)
		obj.tag_bind("HEADLINE", "<ButtonRelease-2>", s.open)
		obj.tag_bind("HEADLINE", "<Enter>", s._cursor_over_link)
		obj.tag_bind("HEADLINE", "<Leave>", s._cursor_not_over_link)
		obj.tag_config("DESCR", spacing2 = 5, font = ("Times", int(
			config['fontscaling'] * fontsize['Description'])))
		obj.tag_config("URL", foreground = "#ff2600", justify = RIGHT, font = ("Courier",
			fontsize['URL']))
		
		obj.tag_config("NAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		obj.tag_config("NAV", foreground = "black")
		
		obj.tag_config("BNAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		if history.is_first(): obj.tag_config("BNAV", foreground = "#aaaaaa")
		else: obj.tag_config("BNAV", foreground = "black")
		obj.tag_bind("BNAV", "<ButtonRelease-1>", s.back)
		obj.tag_bind("BNAV", "<ButtonRelease-2>", s.back)
		
		obj.tag_config("FNAV", font = ("Helvetica", fontsize['Navigation'], "bold"))
		if history.is_last(): obj.tag_config("FNAV", foreground = "#aaaaaa")
		else: obj.tag_config("FNAV", foreground = "black")
		obj.tag_bind("FNAV", "<ButtonRelease-1>", s.forward)
		obj.tag_bind("FNAV", "<ButtonRelease-2>", s.forward)

		story = newsfeeds[s.sel_f].content[s.sel_t]

		obj.insert(END, story.date + "\n", "DATE")
		s._insert_nav_bar(obj)
		obj.insert(END, unemoji(story.get_p_title() + "\n\n"), "HEADLINE")
		#print story.descr.encode("ascii", "replace") #########
		textbody = unemoji(htmlrender(stripcontrol(story.descr))).split()
		try:
			search_terms = newsfeeds[s.sel_f].terms
		except:
			pass
		else:
			textbody2 = []
			for x in textbody:
				if search_terms.lower().strip() in x.strip().lower():
					textbody2.append(x.upper())
				else:
					textbody2.append(x)
			textbody = textbody2
		#print entities(htmlrender(stripcontrol(story.descr))).encode("ascii", "replace") #########

		# Look for link open and close tags that do not match:
		numleft  = textbody.count("{[")
		numright = textbody.count("]}")
		if numleft > numright: textbody += (numleft - numright) * ["]}"]
		#elif numleft < numright: textbody = (numright - numleft) * ["{["] + textbody

		# Insert hyperlinks as clickable text:
		i = 0
		while i < len(textbody):
			x = textbody[i]
			if x == "{/": obj.insert(END, "\n", "DESCR")
			elif x == "{[":
				link = textbody[i + 1]
				text = textbody[i + 3 : _find_next(textbody, i + 3, "]}")]
				text = [x for x in text if x[0] != '{']

				mytag = "LINK%u" % i

				obj.tag_config(mytag, foreground = "blue",
						underline = 1, spacing2 = 5,
						font = ("Times", int(config['fontscaling'] * fontsize['Description'])))
				obj.tag_bind(mytag, "<ButtonRelease-1>", lambda x, link = link: open_url(link))
				obj.tag_bind(mytag, "<ButtonRelease-2>", lambda x, link = link: open_url(link))
				obj.tag_bind(mytag, "<Enter>", s._cursor_over_link)
				obj.tag_bind(mytag, "<Leave>", s._cursor_not_over_link)

				obj.insert(END, ' '.join(text), mytag)
				obj.insert(END, ' ', "DESCR")
				i = _find_next(textbody, i + 3, "]}")
			else: obj.insert(END, x + " ", "DESCR")
			i += 1
		if story.has_enclosure():
			etype = story.enclosure[0].get('type',   'unknown')
			elen  = story.enclosure[0].get('length', 'unknown')
			eurl  = story.enclosure[0].get('url',    'unknown')
			obj.tag_config("ENC", foreground = "blue",
					underline = 1, spacing2 = 5,
					font = ("Times", int(config['fontscaling'] * fontsize['Description'])))
			obj.tag_bind("ENC", "<ButtonRelease-1>", lambda x, link = eurl: open_enclosure(link))
			obj.tag_bind("ENC", "<ButtonRelease-2>", lambda x, link = eurl: open_url(link))
			obj.tag_bind("ENC", "<Enter>", s._cursor_over_link)
			obj.tag_bind("ENC", "<Leave>", s._cursor_not_over_link)
			obj.insert(END, "\n\n\n  Enclosure (type %s, size %s):\n  " % (etype, elen), "DESCR")
			obj.insert(END, "%s\n" % eurl, "ENC")
		obj.insert(END, "\n\n" + story.link + "\n\n", "URL")
		try: obj.insert(END, time.strftime("%Y-%m-%d %H:%M",
			time.localtime(newsfeeds[s.sel_f].headlines[
				gethash(story.title, story.descr)])), "DLDATE")
		except: pass
		obj.config(state = DISABLED)

	def _change_list(s, obj, ilist, selnum):
		"Change one of the listboxes."
		a, b = [int(.5 + obj.size() * x) for x in obj.yview()]
		b -= 1

		obj.delete(0, END)
		if not ilist: return
		ilist2 = [unemoji(ll) for ll in ilist]
		if obj is s.lb:
			for i in range(len(ilist2)): obj.insert(END, s._active(ilist2[i], i, selnum, mark = 1))
		else:
			for i in range(len(ilist2)): obj.insert(END, s._active(ilist2[i], i, selnum))

		if selnum:
			if selnum < a or selnum > b: obj.see(selnum)
			else: obj.yview(a)

		obj.select_clear(0, END)
		if obj is s.r1b: obj.select_set(selnum)
		
	def next_keyb(s, event = ""):
		"Next unread item (keyboard navigation callback)."
		s._hide_cursor()
		s.next_unread()

	def next_unread(s, event = ""):
		"Jump to next unread item."
		if s.total_unread == 1:
			s.b_next.config(state = DISABLED)
		t = s._next_in_feed(feed = s.sel_f, topic = s.sel_t)
		if t:
			s.change_content(feed = s.sel_f, topic = t - 1)
			return
		s.b_allread.config(state = DISABLED)
		for f in list(range(s.sel_f, len(newsfeeds))) + list(range(0, s.sel_f)):
			t = s._next_in_feed(feed = f)
			if t:
				s.change_content(feed = f, topic = -2)
				return

	def _next_in_feed(s, feed = 0, topic = 0):
		"Find next unread message in feed 'feed', starting from topic 'topic'."
		for i in range(topic, len(newsfeeds[feed].content)):
			if newsfeeds[feed].content[i].unread:
				return i + 1
		for i in range(0, topic):
			if newsfeeds[feed].content[i].unread:
				return i + 1
		return 0

	def mark_all_as_read_keyb(s, event = ""):
		"Mark all as read (keyboard navigation callback)."
		s._hide_cursor()		
		s.mark_all_as_read()

	def mark_all_as_read(s, event = ""):
		"Mark all items in current channel as read."
		for i in newsfeeds[s.sel_f].content:
			i.unread = False
		s.b_allread.config(state = DISABLED)
		s.change_content(feed = s.sel_f, topic = 0)

	def catch_up(s, event = ""):
		"Mark all items in all channels as read."
		for f in newsfeeds:
			for x in f.content:
				x.unread = False
		s.change_content(feed = 0, topic = 0)

	def delete_one(s, event = ""):
		"Delete one entry (and remember not to download it again)."
		t = newsfeeds[s.sel_f].content[s.sel_t]
		hash = gethash(t.title, t.descr)
		if isinstance(newsfeeds[s.sel_f], SearchWire):
			for f in newsfeeds:
				if f is not newsfeeds[s.sel_f]:
					f.content = [x for x in f.content if gethash(
							x.title, x.descr) != hash]
		del newsfeeds[s.sel_f].content[s.sel_t]
		s.change_content(feed = s.sel_f, topic = s.sel_t)
		s._update_searches()

	def delete_all_in_feed(s):
		"Delete all items in current feed as well as copies in other feeds and then refresh view."
		if isinstance(newsfeeds[s.sel_f], SearchWire):
			for t in newsfeeds[s.sel_f].content:
				hash = gethash(t.title, t.descr)
				for f in newsfeeds:
					if f is not newsfeeds[s.sel_f]:
						f.content = [x for x in f.content if gethash(
								x.title, x.descr) != hash]
						if hash in f.headlines: del f.headlines[hash]
		newsfeeds[s.sel_f].content   = []
		newsfeeds[s.sel_f].headlines.clear()
		newsfeeds[s.sel_f].lastresult = None
		s.change_content(feed = s.sel_f, topic = 0)

	def open(s, event = ""):
		"Open news item link in web browser."
		if not newsfeeds[s.sel_f].content: return
		newsfeeds[s.sel_f].content[s.sel_t].link_visited = True
		open_url(newsfeeds[s.sel_f].content[s.sel_t].link)
		s.change_content(feed = s.sel_f, topic = s.sel_t)

	def open_home(s, event = ""):
		"Open feed home page in browser."
		try:
			if not isinstance(newsfeeds[s.sel_f], SearchWire):
				open_url(newsfeeds[s.sel_f].homeurl)
			else:
				theurl = ''
				for x in newsfeeds:
					if not isinstance(x, SearchWire) and x.name == newsfeeds[s.sel_f].content[s.sel_t].fromfeed:
						theurl = x.homeurl
				open_url(theurl)
		except: pass

	def refresh(s, event = ""):
		"Refresh all newsfeeds."
		if s.refresh_now < 1:
			s.refresh_now = 1

	def refresh_this(s, event =""):
		"Refresh the current feed."
		s._hide_cursor()
		if not isinstance(newsfeeds[s.sel_f], SearchWire):
			newsfeeds[s.sel_f].u_time = 0

	def discover(s):
		"Try to discover RSS feed for given site."
		rss = ""
		try: rss = rssfinder.getFeeds(s.e2.get())
		except (IOError, Exception): pass
		else:
			if len(rss) > 1:
				newcontent = []
				for i in range(len(rss)):
					newcontent.insert(0, NewsWire(
						name = "? #%u (%s)" % (i + 1, s.e2.get()),
									url = rss[i]))
				for i in newcontent: newsfeeds.insert(s.sel_f + 1, i)
			elif rss:
				newsfeeds[s.sel_f].url = rss[0]
				s.e3.delete(0, END)
				s.e3.insert(END, newsfeeds[s.sel_f].url)
			else:
				s.e3.delete(0, END)
				s.e3.insert(END, "Unable to locate feed for site " + s.e2.get())
		
	def _is_window_open(s, w):
		"Is the window 'w' already open? If so, raise it."
		try: w.geometry()
		except (TclError, Exception): return 0
		else:
			w.lift()
			w.focus()
			return 1

	def info(s, event = "", focus = 1):
		"Display editable info about current channel."
		if isinstance(newsfeeds[s.sel_f], SearchWire): return
		if s._is_window_open(s.infowin): return

		s.infowin = Toplevel()
		s.infosel = s.sel_f
		s.infowin.title("Subscription Info")
		s.infowin.geometry(config['geom_info'])

		f1 = Frame(s.infowin, borderwidth = 10)
		f1.pack(side = TOP)
		f2 = Frame(f1)
		f2.pack(side = LEFT)
		l1 = Label(f2, text = "Name:")
		l1.pack()
		f3 = Frame(f1)
		f3.pack(side = RIGHT)
		s.e1 = Entry(f3, width = 65)
		s.e1.insert(END, newsfeeds[s.sel_f].name)
		s.e1.pack(side = LEFT)

		f4 = Frame(s.infowin, borderwidth = 10)
		f4.pack(side = TOP)
		f5 = Frame(f4)
		f5.pack(side = LEFT)
		l2 = Label(f5, text = "Home:")
		l2.pack()
		f6 = Frame(f4)
		f6.pack(side = RIGHT)
		s.e2 = Entry(f6, width = 65)
		s.e2.insert(END, newsfeeds[s.sel_f].homeurl)
		s.e2.pack(side = LEFT)

		f7 = Frame(s.infowin, borderwidth = 10)
		f7.pack(side = TOP)
		f8 = Frame(f7)
		f8.pack(side = LEFT)
		l3 = Label(f8, text = "  RSS:")
		l3.pack()
		f9 = Frame(f7)
		f9.pack(side = RIGHT)
		s.e3 = Entry(f9, width = 65)
		s.e3.insert(END, newsfeeds[s.sel_f].url)
		s.e3.pack(side = LEFT)

		f14 = Frame(s.infowin)
		f14.pack(side = TOP, padx = 90, pady = 10, fill = X)
		f15 = Frame(f14)
		f15.pack(side = LEFT)
		f16 = Frame(f14)
		f16.pack(side = RIGHT)
		f17 = Frame(f15)
		f17.pack(side = LEFT)
		f18 = Frame(f15)
		f18.pack(side = RIGHT)
		f19 = Frame(f16)
		f19.pack(side = LEFT)
		f20 = Frame(f16)
		f20.pack(side = RIGHT)
		l4 = Label(f17, text = "Update every:")
		l4.pack(side = RIGHT)
		s.o1var = StringVar()
		cust_name = "Custom (%u s)" % round(60 * custom_interval)
		if newsfeeds[s.sel_f].refresh == 5: s.o1var.set("5 minutes")
		elif newsfeeds[s.sel_f].refresh == 15: s.o1var.set("15 minutes")
		elif newsfeeds[s.sel_f].refresh == 30: s.o1var.set("30 minutes")
		elif newsfeeds[s.sel_f].refresh == 60: s.o1var.set("60 minutes")		
		else: s.o1var.set(cust_name)
		o1 = OptionMenu(f18, s.o1var, "5 minutes", "15 minutes", 
			"30 minutes", "60 minutes", cust_name)
		o1.config(width = 11)
		o1.pack(side = LEFT)
		l5 = Label(f19, text = "Expire after:")
		l5.pack(side = RIGHT)
		s.o2var = StringVar()
		if newsfeeds[s.sel_f].expire == 1: s.o2var.set("1 day")
		elif newsfeeds[s.sel_f].expire == 3: s.o2var.set("3 days")
		elif newsfeeds[s.sel_f].expire == 10: s.o2var.set("10 days")
		elif newsfeeds[s.sel_f].expire == 30: s.o2var.set("30 days")
		else: s.o2var.set("Never")
		o2 = OptionMenu(f20, s.o2var, "1 day", "3 days", "10 days", "30 days" , "Never")
		o2.config(width = 8)
		o2.pack(side = LEFT)

		f10 = Frame(s.infowin)
		f10.pack(side = TOP, pady = 20)
		f11 = Frame(f10)
		f11.pack(side = LEFT)
		f12 = Frame(f10, width = 120)
		f12.pack(side = LEFT)
		f13 = Frame(f10)
		f13.pack(side = LEFT)
		b1 = Button(f11, text = "Auto-Detect RSS Feed", command = s.discover)
		b1.pack(side = LEFT)
		b2 = Button(f13, text = "Save Information", command = s._update)
		b2.pack(side = RIGHT)

		# Add site description:
		f14 = Frame(s.infowin)
		f14.pack(side = TOP, padx = 50)
		s.t_descr = Text(f14, wrap = WORD, width = 60, height = 8)
		s.t_descr.insert(END, newsfeeds[s.sel_f].descr)
		s.t_descr.config(state = DISABLED, background = "#fffbea",
					selectforeground = "white", selectbackground ="#233a8e")
		s.t_descr.pack(side = BOTTOM, expand = 1, fill = BOTH)
		s.e1.bind("<Return>", s._update)
		s.e2.bind("<Return>", s._update)
		s.e3.bind("<Return>", s._update)
		s.infowin.bind("<Escape>", lambda x: s.infowin.destroy())

		if focus == 1: s.e1.focus()
		else: s.e2.focus()

	def _update(s, event = ""):
		"Update the channel information."
		if not s.e1.get().strip() or not s.e3.get().strip():
			return
		if '.' not in s.e3.get().strip():
			s.discover()
		else:
			newurl = s.e3.get().strip()
			if newurl != newsfeeds[s.infosel].url:
				newsfeeds[s.infosel].u_time = 0
				try:
					del newsfeeds[s.infosel].webpage
					del newsfeeds[s.infosel].is_webpage
				except: pass
				newsfeeds[s.infosel].url = newurl

		newsfeeds[s.infosel].name    = s.e1.get().strip()
		for x in newsfeeds[s.infosel].content:
			x.fromfeed = newsfeeds[s.infosel].name
		newsfeeds[s.infosel].homeurl = s.e2.get().strip()

		refresh = s.o1var.get()
		rf = refresh.split()[0]
		if rf.isdigit():
			newsfeeds[s.infosel].refresh = int(rf)
		else:
			newsfeeds[s.infosel].refresh = custom_interval

		expire  = s.o2var.get()
		try: newsfeeds[s.infosel].expire  = int(expire.split()[0])
		except ValueError: newsfeeds[s.infosel].expire = 999999
		
		config['geom_info'] = s.infowin.geometry()
		s.infowin.destroy()
		if ((not isinstance(newsfeeds[s.infosel], SearchWire))
			and newsfeeds[s.infosel].name and newsfeeds[s.infosel].name[0] == '?'):
			newsfeeds[s.infosel].u_time = 0
		s.change_content(feed = s.sel_f)

	def sub(s):
		"Subscribe to a new channel."
		newsfeeds.insert(s.sel_f + 1, NewsWire(name = "?New Channel",
						url = "http://", homeurl = "http://"))
		s.change_content(feed = s.sel_f + 1)
		s.info(focus = 3)

	def unsub(s):
		"Remove the current channel."
		global ask_before_deletion

		if s.refresh_now or len(newsfeeds) == 1: return
		if ask_before_deletion: s.ask_conf("'%s'" % newsfeeds[s.sel_f].name)
		else: s.unsub_conf()

	def unsub_conf(s):
		"Confirmed: Remove the current channel."
		global ask_before_deletion

		if s.refresh_now or len(newsfeeds) == 1: return
		try:
			if s.cwin.track_checkbutton.get(): ask_before_deletion = False
			else: ask_before_deletion = True
			s.cwin.destroy()
		except: pass
		if isinstance(newsfeeds[s.sel_f], SearchWire):
			del newsfeeds[s.sel_f]
		else:
			del newsfeeds[s.sel_f]
			s._update_searches()
		s.change_content(feed = s.sel_f, topic = 0)

	def ask_conf(s, name = "this channel"):
		"Ask for confirmation before unsubscribing."
		global root, config

		s.cwin     = Toplevel()
		wh, x, y   = config['geom_root'].split('+')
		w, h       = wh.split('x')
		x, y, w, h = [float(z) for z in (x, y, w, h)]
		w2, h2     = 480, 160
		sx, sy     = root.winfo_screenwidth(), root.winfo_screenheight()
		xpos, ypos = max(0, x + .5 * (w - w2)), max(0, y + .5 * (h - h2))
		if xpos + w2 > sx: xpos = sx - w2 - 20
		if ypos + h2 > sy: ypos = sy - h2 - 60
		s.cwin.geometry("%ux%u+%u+%u" % (w2, h2, xpos, ypos))
		s.cwin.title("Confirm Channel Deletion")
		s.cwin.transient(root)
		s.cwin.grab_set()
		s.cwin.initial_focus = s.cwin
		s.cwin.bind("<Escape>", lambda x: s.cwin.destroy())
		f1 = Frame(s.cwin, borderwidth = 15)
		f1.pack(side = TOP, pady = 5)
		f2 = Frame(s.cwin, borderwidth = 10)
		f2.pack(side = TOP, fill = X)
		Label(f1, text = "Do you really want to unsubscribe from %s?" % name).pack()
		s.cwin.track_checkbutton = IntVar()
		Checkbutton(f1, text = "Do not ask this again",
				variable = s.cwin.track_checkbutton).pack(pady = 10)
		Button(f2, text = "Keep", command = s.cwin.destroy).pack(side = LEFT)
		Button(f2, text = "Delete", command = s.unsub_conf).pack(side = RIGHT)
		root.wait_window(s.cwin)

	def new_search(s, event = ""):
		"Create a new search entry."
		if s._is_window_open(s.searchwin): return
		s.searchwin = Toplevel()
		s.searchwin.title("Create New Search")
		s.searchwin.geometry(config['geom_search'])

		f1 = Frame(s.searchwin)
		f1.pack(side = TOP)
		f2 = Frame(f1)
		f2.pack(side = LEFT)
		f3 = Frame(f1)
		f3.pack(side = RIGHT)
		l_search = Label(f2, text = "Search for:")
		l_search.pack(side = TOP)
		s.e_search = Entry(f3)
		s.e_search.pack(side = TOP, pady = 20)

		f4 = Frame(s.searchwin)
		f4.pack(side = TOP, fill = X, padx = 40)
		s.search_is_case_sensitive = IntVar()
		s.search_is_case_sensitive.set(config['search_is_case_sensitive'])
		s.c_search_case = Checkbutton(f4, text = "Match Case",
						variable = s.search_is_case_sensitive)
		s.c_search_case.pack(side = LEFT)

		f5 = Frame(s.searchwin)
		f5.pack(side = TOP, fill = X, padx = 40)
		s.search_match_whole_words = IntVar()
		s.search_match_whole_words.set(config['search_match_whole_words'])
		s.c_search_words = Checkbutton(f5, text = "Match Whole Words",
						variable = s.search_match_whole_words)
		s.c_search_words.pack(side = LEFT)

		f6 = Frame(s.searchwin)
		f6.pack(side = TOP, fill = X, padx = 40)
		s.search_only_unread = IntVar()
		s.search_only_unread.set(config['search_only_unread'])
		s.c_search_only_unread = Checkbutton(f6, text = "Search Only in Unread Items",
						variable = s.search_only_unread)
		s.c_search_only_unread.pack(side = LEFT)

		s.b_search = Button(s.searchwin, text = "Accept", command = s._new_search_finished)
		s.b_search.pack(side = TOP, pady = 20)
		s.e_search.bind("<Return>", s._new_search_finished)
		s.searchwin.bind("<Escape>", lambda x: s.searchwin.destroy())
		s.e_search.focus()

	def _new_search_finished(s, event = ""):
		"Accept the user's search."
		case  = int(s.search_is_case_sensitive.get())
		words = int(s.search_match_whole_words.get())
		only_unread = int(s.search_only_unread.get())
		newsfeeds.insert(s.sel_f + 1, SearchWire(s.e_search.get().strip(), case = case,
							words = words, only_unread = only_unread))
		config['search_is_case_sensitive'] = case
		config['search_match_whole_words'] = words
		config['search_only_unread']       = only_unread
		s.change_content(feed = s.sel_f + 1)
		config['geom_search'] = s.searchwin.geometry()
		s.searchwin.destroy()
		s.refresh_feeds.append(newsfeeds[s.sel_f])
		s.num_refresh_feeds += 1
		s.draw_bar(s.progress())

	def _update_searches(s):
		"Update all search feeds."
		for i in newsfeeds:
			if isinstance(i, SearchWire):
				s.refresh_feeds.append(i)
				s.num_refresh_feeds += 1
				s.draw_bar(s.progress())

	def up(s):
		"Move a channel up in list."
		if s.refresh_now: return
		if s.sel_f:
			newsfeeds[s.sel_f], newsfeeds[s.sel_f - 1] = newsfeeds[
							s.sel_f - 1], newsfeeds[s.sel_f]
			s.sel_f -= 1
			s._change_list(s.lb, [x.get_name() for x in newsfeeds], s.sel_f)

	def down(s):
		"Move a channel down in list."
		if s.refresh_now: return
		if s.sel_f < len(newsfeeds) - 1:
			newsfeeds[s.sel_f], newsfeeds[s.sel_f + 1] = newsfeeds[
							s.sel_f + 1], newsfeeds[s.sel_f]
			s.sel_f += 1
			s._change_list(s.lb, [x.get_name() for x in newsfeeds], s.sel_f)

	def beat(s):
		"Look if any updating of feeds is necessary."
		global netchecker
		cur = None

		s.lb.xview_moveto(0.0)
		s.r1b.xview_moveto(0.0)
		s.r11b.xview_moveto(0.0)

		if len(s.lb.curselection())  and int(s.lb.curselection()[0])    != s.sel_f:
			s.idle_since = time.time()
			s.change_content(feed = s.lb.curselection()[0])
		if len(s.r1b.curselection()) and int(s.r1b.curselection()[0])   != s.sel_t:
			s.idle_since = time.time()
			s.change_content(feed = s.sel_f, topic = s.r1b.curselection()[0])
		if len(s.r11b.curselection()) and int(s.r11b.curselection()[0]) != s.sel_t:
			s.idle_since = time.time()
			s.change_content(feed = s.sel_f, topic = s.r11b.curselection()[0])

		# Look for changes in the number of empty feeds:
		num_empty_feeds = len([x for x in newsfeeds if (x.content == [] and not isinstance(x, SearchWire))])
		if num_empty_feeds != s.num_empty_feeds and not s.num_refresh_feeds: s._update_searches()
		s.num_empty_feeds = num_empty_feeds

		# First stage of global refresh. Add all feeds to array of feeds to be reloaded:
		if s.refresh_now == 1:
			newsfeeds[s.sel_f].u_time = approx_time()
			s.refresh_feeds.append(newsfeeds[s.sel_f])
			for i in [x for x in newsfeeds if x is not newsfeeds[s.sel_f]
			    and not isinstance(x, SearchWire)]:
				s.refresh_feeds.append(i)
				i.u_time = newsfeeds[s.sel_f].u_time
			for i in newsfeeds:
				if isinstance(i, SearchWire): s.refresh_feeds.append(i)
			s.num_refresh_feeds += len(newsfeeds)
			s.refresh_now = 2

		# Second stage, do the actual downloading:
		rr = ''
		if s.refresh_feeds:
			if s. b_refresh.cget("state") == "normal":
				for b in s.b_refresh, s.b_unsub, s.b_up, s.b_dn:
					b.config(state = DISABLED)
			cur = s.refresh_feeds[0]
			s.draw_bar(s.progress())
			if isinstance(cur, SearchWire):
				cur.get_news(refresh = True)
				s.refresh_feeds.pop(0)
				s.num_done_feeds += 1
			else:
				try:
					etag = cur.lastresult.get('etag', '')
					lr = cur.lastresult.get('modified', '')
				except: etag, lr = '', ''
				try:
					if use_threads:
						dlthreads.urlq.put_nowait((cur.url_is_webpage(), (cur.url, etag, lr)))
					else:
						if cur.url_is_webpage():
							try:
								rr = get_content_unicode(cur.url)
							except:
								rr = "failed"
						else:
							try:
								# Parse data, return a dictionary:
								rr = feedparser.parse(cur.url, etag = etag, modified = lr)
								rr['bozo_exception'] = ''
							except:
								raise
								rr = "failed"
						rr = (cur.url, rr)
				except Full: pass
				else: s.refresh_feeds.pop(0)

		result = ''
		if s.num_done_feeds >= s.num_refresh_feeds:
			if s. b_refresh.cget("state") == "disabled":
				for b in s.b_refresh, s.b_unsub, s.b_up, s.b_dn:
					if b.cget("state") == "disabled": b.config(state = NORMAL)
			s.refresh_now = 0
			s.num_refresh_feeds = 0
			s.num_done_feeds = 0
			s.draw_bar(0)
		try:
			if use_threads:
				rr = dlthreads.urlr.get_nowait()
		except Empty:
			pass
		else:
			if rr:
				s.num_done_feeds += 1
				s.draw_bar(s.progress())
				res_url, result = rr[0], rr[1]
				for x in range(len(newsfeeds)):
					try: nurl = newsfeeds[x].url
					except: nurl = ''
					if nurl == res_url:
						if result and result != "failed":
							newsfeeds[x].failed = False
						else:
							newsfeeds[x].failed = True
		if result and result != "failed":
			new_data[res_url] = result
			for x in range(len(newsfeeds)):
				nl = 0
				try: nurl = newsfeeds[x].url
				except: nurl = ''
				if nurl == res_url:
					nl = newsfeeds[x].get_news(refresh = True)
				if x == s.sel_f:
					s.change_content(feed = s.sel_f,
						topic = s.sel_t + nl)
				else:
					s._window_title(s.sel_f)

		# Enable / disable a few buttons:
		if (s.b_allread.cget("state") == "disabled" and
		  [x for x in newsfeeds[s.sel_f].content if x.unread]):
			s.b_allread.config(state = NORMAL)
		elif (s.b_allread.cget("state") == "normal" and
		  not [x for x in newsfeeds[s.sel_f].content if x.unread]):
			s.b_allread.config(state = DISABLED)
		if s.b_next.cget("state") == "disabled" and s.total_unread:
			s.b_next.config(state = NORMAL)
		elif s.b_next.cget("state") == "normal" and not s.total_unread:
			s.b_next.config(state = DISABLED)
		if s.b_del.cget("state") == "disabled" and newsfeeds[s.sel_f].content:
			s.b_del.config(state = NORMAL)
		elif s.b_del.cget("state") == "normal" and not newsfeeds[s.sel_f].content:
			s.b_del.config(state = DISABLED)

		# Look for feeds that require updating:
		some_feeds_need_updating = 0
		new_time = approx_time()
		for i in [x for x in newsfeeds if not isinstance(x, SearchWire)]:
			if (time.time() - i.u_time) / 60. > i.refresh and netchecker.check():
				some_feeds_need_updating = 1
				i.u_time = new_time
				s.refresh_feeds.append(i)
				s.num_refresh_feeds += 1

		# Also update the searches if one or more feeds need to be updated:
		if some_feeds_need_updating: s._update_searches()

		# Save window sizes and positions:
		config['geom_root'] = s.parent.geometry()
		try: config['geom_info'] = s.infowin.geometry()
		except (TclError, Exception): pass
		try: config['geom_search'] = s.searchwin.geometry()
		except (TclError, Exception): pass

		# Save program state automatically every ten minutes:
		if (time.time() - s.last_saved > 600 and
			time.time() - s.idle_since > 10 and not s.refresh_feeds):
			if save(): s.last_saved = time.time()
			else: s.last_saved = time.time() - 300

		# This reduction of interactivity is done to limit Tkinter memory leakage:
		if time.time() - s.idle_since > 60 and not s.refresh_feeds:
			s.parent.after(1000, s.beat)
		elif time.time() - s.idle_since > 10 and not s.refresh_feeds:
			s.parent.after(200, s.beat)
		else: s.parent.after(50, s.beat)

class dummysound:
	"Use this if Snack is unavailable."
	def play(s): pass

def gui_interface():
	"Tk interface routine."
	global app, sound, root

	root = Tk()

	root.title(config['progname'] + " - " + newsfeeds[0].name)
	root.geometry(config['geom_root'])

	app = TkApp(root)
	app.change_content()
	root.protocol("WM_DELETE_WINDOW", quit)
	root.iconname(config['progname'])

	root.mainloop()

def main(nogui = False):
	"Main Program. Start either textual or graphical interface."
	open(pid_file, 'w').write("%u" % os.getpid())
	load_feeds()
	add_feeds_helper()
	if config['mode'] == "text" or nogui: text_interface()
	else: gui_interface()

if __name__ == '__main__':
	print("This is the NewsFeed module.")
	print("Please run 'newsfeed' or 'Start_NewsFeed.py' instead to launch the program.")
	print()
