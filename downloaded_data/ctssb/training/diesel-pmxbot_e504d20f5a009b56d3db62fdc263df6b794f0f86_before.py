import re
import datetime
import itertools
import struct

import pytz

from . import storage

class Logger(storage.SelectableStorage):
	"Base Logger class"

init_logger = Logger.from_URI

class SQLiteLogger(Logger, storage.SQLiteStorage):

	def init_tables(self):
		LOG_CREATE_SQL = '''
		CREATE TABLE IF NOT EXISTS logs (
			id INTEGER NOT NULL,
			datetime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			channel VARCHAR NOT NULL,
			nick VARCHAR NOT NULL,
			message TEXT,
			PRIMARY KEY (id) )
		'''
		INDEX_DTC_CREATE_SQL = 'CREATE INDEX IF NOT EXISTS ix_logs_datetime_channel ON logs (datetime, channel)'
		INDEX_DT_CREATE_SQL = 'CREATE INDEX IF NOT EXISTS ix_logs_datetime ON logs (datetime desc)'
		self.db.execute(LOG_CREATE_SQL)
		self.db.execute(INDEX_DTC_CREATE_SQL)
		self.db.execute(INDEX_DT_CREATE_SQL)
		self.db.commit()

	def message(self, channel, nick, msg):
		INSERT_LOG_SQL = 'INSERT INTO logs (datetime, channel, nick, message) VALUES (?, ?, ?, ?)'
		now = datetime.datetime.now()
		channel = channel.replace('#', '')
		self.db.execute(INSERT_LOG_SQL, [now, channel.lower(), nick, msg])
		self.db.commit()

	def last_seen(self, nick):
		FIND_LAST_SQL = 'SELECT datetime, channel FROM logs WHERE nick = ? ORDER BY datetime DESC LIMIT 1'
		res = list(self.db.execute(FIND_LAST_SQL, [nick]))
		self.db.commit()
		if not res:
			return None
		else:
			return res[0]

	def strike(self, channel, nick, count):
		count += 1 # let's get rid of 'the last !strike' too!
		if count > 20:
			count = 20
		LAST_N_IDS_SQL = '''select channel, nick, id from logs where channel = ? and nick = ? and date(datetime) = date('now','localtime') order by datetime desc limit ?'''
		DELETE_LINE_SQL = '''delete from logs where channel = ? and nick = ? and id = ?'''
		channel = channel.replace('#', '')

		ids_to_delete = self.db.execute(LAST_N_IDS_SQL, [channel.lower(), nick, count]).fetchall()
		if ids_to_delete:
			deleted = self.db.executemany(DELETE_LINE_SQL, ids_to_delete)
			self.db.commit()
			rows_deleted = deleted.rowcount - 1
		else:
			rows_deleted = 0
		rows_deleted = deleted.rowcount - 1
		self.db.commit()
		return rows_deleted

	def get_random_logs(self, limit):
		query = "SELECT message FROM logs order by random() limit %(limit)s" % vars()
		return self.db.execute(query)

	def get_channel_days(self, channel):
		query = 'select distinct date(datetime) from logs where channel = ?'
		return [x[0] for x in self.db.execute(query, [channel])]

	def get_day_logs(self, channel, day):
		query = """
			SELECT time(datetime), nick, message from logs
			where channel = ? and date(datetime) = ? order by datetime
			"""
		return self.db.execute(query, [channel, day])

	def search(self, *terms):
		SEARCH_SQL = (
			'SELECT id, date(datetime), time(datetime), datetime, '
			'channel, nick, message FROM logs WHERE %s' % (
				' AND '.join(["message like '%%%s%%'" % x for x in terms])
			)
		)

		matches = []
		alllines = []
		search_res = self.db.execute(SEARCH_SQL).fetchall()
		for id, date, time, dt, channel, nick, message in search_res:
			line = (time, nick, message)
			if line in alllines:
				continue
			prev_q = """
				SELECT time(datetime), nick, message
				from logs
				where channel = ?
				  and datetime < ?
				order by datetime desc
				limit 2
				"""
			prev2 = self.db.execute(prev_q, [channel, dt])
			next_q = prev_q.replace('<', '>').replace('desc', 'asc')
			next2 = self.db.execute(next_q, [channel, dt])
			lines = prev2.fetchall() + [line] + next2.fetchall()
			marker = self.make_anchor(line[:2])
			matches.append((channel, date, marker, lines))
			alllines.extend(lines)
		return matches

	def list_channels(self):
		query = "SELECT distinct channel from logs"
		return (chan[0] for chan in self.db.execute(query).fetchall())

	def last_message(self, channel):
		query = """
			SELECT datetime, nick, message
			from logs
			where channel = ?
			order by datetime desc
			limit 1
		"""
		time, nick, message = self.db.execute(query, [channel]).fetchone()
		result = dict(datetime=time, nick=nick, message=message)
		parse_date(result)
		return result

	def export_all(self):
		query = 'SELECT id, datetime, nick, message, channel from logs'
		def robust_text(text):
			for encoding in 'utf-8', 'latin-1':
				try:
					return text.decode(encoding)
				except UnicodeDecodeError:
					pass
			raise
		self.db.text_factory = robust_text
		cursor = self.db.execute(query)
		fields = 'id', 'datetime', 'nick', 'message', 'channel'
		results = (dict(zip(fields, record)) for record in cursor)
		return itertools.imap(parse_date, results)

def parse_date(record):
	dt = record.pop('datetime')
	fmts = [
		'%Y-%m-%d %H:%M:%S.%f',
		'%Y-%m-%d %H:%M:%S',
	]
	for fmt in fmts:
		try:
			dt = datetime.datetime.strptime(dt, fmt)
			break
		except ValueError:
			pass
	else:
		raise
	tz = pytz.timezone('US/Pacific')
	loc_dt = tz.localize(dt)
	record['datetime'] = loc_dt
	return record

class MongoDBLogger(Logger, storage.MongoDBStorage):
	collection_name = 'logs'

	def message(self, channel, nick, msg):
		self.db.ensure_index('datetime.d')
		channel = channel.replace('#', '')
		now = datetime.datetime.utcnow()
		self.db.insert(dict(channel=channel, nick=nick, message=msg,
			datetime=self._fmt_date(now),
			))

	@staticmethod
	def _fmt_date(datetime):
		return dict(d=str(datetime.date()), t=str(datetime.time()))

	def last_seen(self, nick):
		fields = 'channel',
		query = dict(nick=nick)
		cursor = self.db.find(query, fields=fields)
		cursor = cursor.sort('_id', storage.pymongo.DESCENDING)
		res = first(cursor)
		if not res:
			return None
		return [res['_id'].generation_time, res['channel']]

	def strike(self, channel, nick, count):
		channel = channel.replace('#', '')
		# cap at 19 messages
		count = min(count, 19)
		# get rid of 'the last !strike' too!
		limit = count+1
		# don't delete anything before the current date
		date_limit = storage.pymongo.ObjectId.from_datetime(datetime.date.today())
		query = dict(channel=channel, nick=nick)
		query['$gt'] = dict(_id=date_limit)
		cursor = self.db.find(query).sort('_id', storage.pymongo.DESCENDING)
		cursor = cursor.limit(limit)
		ids_to_delete = [row['_id'] for row in cursor]
		if ids_to_delete:
			self.db.remove({'_id': {'$in': ids_to_delete}}, safe=True)
		rows_deleted = max(len(ids_to_delete) - 1, 0)
		return rows_deleted

	def get_random_logs(self, limit):
		cur = self.db.find()
		limit = max(limit, cur.count())
		return (item['message'] for item in random.sample(cur, limit))

	def get_channel_days(self, channel):
		return self.db.find(fields=['datetime.d']).distinct('datetime.d')

	def get_day_logs(self, channel, day):
		query = {'datetime.d': day}
		cur = self.db.find(query).sort('_id')
		return (
			(rec['datetime']['t'], rec['nick'], rec['message'])
			for rec in cur
		)

	def search(self, *terms):
		patterns = [re.compile('.*' + term + '.*') for term in terms]
		query = dict(message = {'$all': patterns})

		matches = []
		alllines = []
		for match in self.db.find(query):
			channel = match['channel']
			row_date = lambda row: row['_id'].generation_time.date()
			to_line = lambda row: (row['_id'].generation_time.time(),
				row['nick'], row['message'])
			line = to_line(match)
			if line in alllines:
				# we've seen this line in the context of a previous hit
				continue
			# get the context for this line
			prev2 = self.db.find(dict(
				channel=match['channel'],
				_id={'$lt': match['_id']}
				)).sort('_id', storage.pymongo.DESCENDING).limit(2)
			prev2 = map(to_line, prev2)
			next2 = self.db.find(dict(
				channel=match['channel'],
				_id={'$gt': match['_id']}
				)).sort('_id', storage.pymongo.ASCENDING).limit(2)
			next2 = map(to_line, next2)
			context = prev2 + [line] + next2
			marker = self.make_anchor(line[:2])
			matches.append((channel, row_date(match), marker, context))
			alllines.extend(context)
		return matches

	def list_channels(self):
		return self.db.distinct('channel')

	def last_message(self, channel):
		rec = next(
			self.db.find(
				dict(channel=channel)
			).sort('_id', storage.pymongo.DESCENDING).limit(1)
		)
		return dict(
			datetime=rec['_id'].generation_time,
			nick=rec['nick'],
			message=rec['message']
		)

	def all_messages(self):
		return self.db.find()

	@staticmethod
	def extract_legacy_id(oid):
		"""
		Given a special OID which includes the legacy sqlite ID, extract
		the sqlite ID.
		"""
		return struct.unpack('L', oid.binary[-4:])[0]

	def import_(self, message):
		# construct a unique objectid with the correct datetime.
		dt = message['datetime']
		oid_time = storage.pymongo.objectid.ObjectId.from_datetime(dt)
		# store the original sqlite object ID in the
		orig_id = message.pop('id')
		orig_id_packed = struct.pack('>Q', orig_id)
		oid_new = oid_time.binary[:4] + orig_id_packed
		oid = storage.pymongo.objectid.ObjectId(oid_new)
		if not hasattr(Logger, 'log_id_map'): Logger.log_id_map = dict()
		Logger.log_id_map[orig_id] = oid
		message['_id'] = oid
		message['datetime'] = self._fmt_date(dt)
		self.db.insert(message)
