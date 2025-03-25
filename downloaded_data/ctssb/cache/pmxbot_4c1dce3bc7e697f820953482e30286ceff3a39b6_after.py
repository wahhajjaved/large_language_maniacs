# -*- coding: utf-8 -*-
import cherrypy
import string
import posixpath
from random import shuffle
import calendar
import datetime
import textwrap
from cgi import escape

import pkg_resources
import jinja2.loaders
from jinja2 import Environment
import pytz
from jaraco.util.numbers import ordinalth as th_it

import pmxbot.core
import pmxbot.logging
import pmxbot.util

jenv = Environment(loader=jinja2.loaders.PackageLoader('pmxbot.web'))
TIMEOUT=10.0


colors = ["06F", "900", "093", "F0C", "C30", "0C9", "666", "C90", "C36",
	"F60", "639", "630", "966", "69C", "039", '7e1e9c', '15b01a', '0343df',
	'ff81c0', '653700', 'e50000', '029386', 'f97306', 'c20078', '75bbfd']
shuffle(colors)

def get_context():
	c = cherrypy.request.app.config['botconf']['config']
	d = dict(
		request = cherrypy.request,
		name = c.bot_nickname,
		config = c,
		base = c.web_base,
		logo = c.logo
	)
	return d

def make_anchor(line):
	time, nick = line
	return "%s.%s" % (str(time).replace(':', '.'), nick)

def pmon(month):
	"""
	P the month

	>>> pmon('2012-08')
	'August, 2012'
	"""
	year, month = month.split('-')
	return '{month_name}, {year}'.format(
		month_name = calendar.month_name[int(month)],
		year = year,
	)

def pday(dayfmt):
	"""
	P the day

	>>> pday('2012-08-24')
	'Friday the 24th'
	"""

	year, month, day = map(int, dayfmt.split('-'))
	return '{day} the {number}'.format(
		day = calendar.day_name[calendar.weekday(year, month, day)],
		number = th_it(day),
	)

rev_month = {}
for x in xrange(1, 13):
	rev_month[calendar.month_name[x]] = x

def sort_month_key(m):
	parts = m.split(',')
	parts[0] = rev_month[parts[0]]
	return parts[1], parts[0]

def log_db():
	return pmxbot.logging.Logger.from_URI(
		cherrypy.request.app.config['botconf']['config'].database)

class ChannelPage(object):
	def default(self, channel):
		page = jenv.get_template('channel.html')

		db = log_db()
		context = get_context()
		contents = db.get_channel_days(channel)
		months = {}
		for fn in sorted(contents, reverse=True):
			mon_des, day = fn.rsplit('-', 1)
			months.setdefault(pmon(mon_des), []).append((pday(fn), fn))
		sort_key = lambda v: sort_month_key(v[0])
		context['months'] = sorted(months.items(), key=sort_key, reverse=True)
		context['channel'] = channel
		return page.render(**context).encode('utf-8')
	default.exposed = True

class DayPage(object):
	def default(self, channel, day):
		page = jenv.get_template('day.html')
		db = log_db()
		context = get_context()
		day_logs = db.get_day_logs(channel, day)
		data = [(t, n, make_anchor((t, n)), escape(m))
			for (t,n,m) in day_logs]
		usernames = [x[1] for x in data]
		color_map = {}
		clrs = colors[:]
		for u in usernames:
			if u not in color_map:
				try:
					color = clrs.pop(0)
				except IndexError:
					color = "000"
				color_map[u] = color
		context['color_map'] = color_map
		context['history'] = data
		context['channel'] = channel
		context['pdate'] = "{pday} of {days}".format(
			pday = pday(day),
			days = pmon(day.rsplit('-', 1)[0]),
		)
		return page.render(**context).encode('utf-8')
	default.exposed = True


def karma_comma(karma_results):
	"""
	(say that 5 times fast)

	Take the results of a karma query (keys, value) and return the same
	result with the keys joined by commas.
	"""
	return [
		(', '.join(keys), value)
		for keys, value in karma_results
	]

class KarmaPage(object):
	def default(self, term=""):
		page = jenv.get_template('karma.html')
		context = get_context()
		karma = pmxbot.util.Karma.from_URI(
			cherrypy.request.app.config['botconf']['config'].database
		)
		term = term.strip()
		if term:
			context['lookup'] = (
				[karma_comma(res) for res in karma.search(term)]
				or [('NO RESULTS FOUND', '')]
			)
		context['top100'] = karma_comma(karma.list(select=100))
		context['bottom100'] = karma_comma(karma.list(select=-100))
		return page.render(**context).encode('utf-8')
	default.exposed = True

class SearchPage(object):
	def default(self, term=''):
		page = jenv.get_template('search.html')
		context = get_context()
		db = log_db()
		#db.text_factory = lambda x: unicode(x, "utf-8", "ignore")

		# a hack to enable the database to create anchors when building search
		#  results
		db.make_anchor = make_anchor

		if not term:
			raise cherrypy.HTTPRedirect(cherrypy.request.base)
		terms = term.strip().split()
		results = sorted(db.search(*terms), key=lambda x: x[1], reverse=True)
		context['search_results'] = results
		context['num_results'] = len(results)
		context['term'] = term
		return page.render(**context).encode('utf-8')
	default.exposed = True


class HelpPage(object):
	def __init__(self):
		self.run = False

	def default(self):
		page = jenv.get_template('help.html')
		context = get_context()
		if not self.run:
			self.commands = []
			self.contains = []
			pmxbot.core.initialize(context['config'])
			for typ, name, f, doc, channels, exclude, rate, priority in \
					sorted(pmxbot.core._handler_registry, key=lambda x: x[1]):
				if typ == 'command':
					aliases = sorted([x[1]
						for x in pmxbot.core._handler_registry
						if x[0] == 'alias' and x[2] == f])
					self.commands.append((name, doc, aliases))
				elif typ == 'contains':
					self.contains.append((name, doc))
			self.run = True
		context['commands'] = self.commands
		context['contains'] = self.contains
		return page.render(**context).encode('utf-8')
	default.exposed = True


class LegacyPage():
	"""
	Forwards legacy /day/{channel}/{date}#{time}.{nick} in local time to
	the proper page at /day (in UTC).
	"""
	timezone = pytz.timezone('US/Pacific')

	@cherrypy.expose
	def default(self, channel, date_s):
		"""
		Return a web page that will get the fragment out and pass it to
		us so we can parse it.
		"""
		return textwrap.dedent("""
			<html>
			<head>
			<script type="text/javascript">
				window.onload = function() {
					fragment = parent.location.hash;
					window.location.pathname=window.location.pathname.replace(
						'legacy', 'legacy/forward') + "/" + window.location.hash.slice(1);
				};
			</script>
			</head>
			<body></body>
			</html>
		""").lstrip()

	@cherrypy.expose
	def forward(self, channel, date_s, fragment):
		"""
		Given an HREF in the legacy timezone, redirect to an href for UTC.
		"""
		time_s, sep, nick = fragment.rpartition('.')
		time = datetime.datetime.strptime(time_s, '%H.%M.%S')
		date = datetime.datetime.strptime(date_s, '%Y-%m-%d')
		dt = datetime.datetime.combine(date, time.time())
		loc_dt = self.timezone.localize(dt)
		utc_dt = loc_dt.astimezone(pytz.utc)
		url_fmt = '/day/{channel}/{target_date}#{target_time}.{nick}'
		raise cherrypy.HTTPRedirect(
			url_fmt.format(
				target_date = utc_dt.date().isoformat(),
				target_time = utc_dt.time().strftime('%H.%M.%S'),
				**vars()
				),
			301,
		)


class PmxbotPages(object):
	channel = ChannelPage()
	day = DayPage()
	karma = KarmaPage()
	search = SearchPage()
	help = HelpPage()
	legacy = LegacyPage()

	def default(self):
		page = jenv.get_template('index.html')
		db = log_db()
		context = get_context()
		chans = []
		for chan in sorted(db.list_channels(), key = string.lower):
			last = db.last_message(chan)
			summary = [
				chan,
				last['datetime'].strftime("%Y-%m-%d %H:%M"),
				last['datetime'].date(),
				last['datetime'].time(),
				last['nick'],
				escape(last['message'][:75]),
				make_anchor([last['datetime'].time(), last['nick']]),
			]
			chans.append(summary)
		context['chans'] = chans
		return page.render(**context).encode('utf-8')
	default.exposed = True

def patch_compat(config):
	"""
	Support older config values.
	"""
	if 'web_host' in config:
		config['host'] = config.pop('web_host')
	if 'web_port' in config:
		config['port'] = config.pop('web_port')

def startup(config):
	patch_compat(config)

	pmxbot.web.config.update(config)
	if not config.web_base.startswith('/'):
		config['web_base'] = '/' + config.web_base
	if config.web_base.endswith('/'):
		config['web_base'] = config.web_base.rstrip('/')
	if 'logo' not in config:
		config['logo'] = posixpath.join(config.web_base, 'pmxbot.png')

	# Cherrypy configuration here
	app_conf = {
		'global': {
			'server.socket_port': config.port,
			'server.socket_host': config.host,
			#'tools.encode.on': True,
			'tools.encode.encoding': 'utf-8',
		},
		'/pmxbot.png': {
			'tools.staticfile.on': True,
			'tools.staticfile.filename': pkg_resources.resource_filename(
				'pmxbot.web', 'templates/pmxbot.png'),
		},
		'botconf': {'config': config},
	}

	cherrypy.quickstart(PmxbotPages(), config.web_base, config=app_conf)

def run():
	startup(pmxbot.core.get_args().config)

if __name__ == '__main__':
	run()
