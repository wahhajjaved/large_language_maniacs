from polls.models import rcp_races, rcp_modules, rcp_questions, rcp_pollsters, fte_pollsters
from polls.models import firebase
import re, requests, lxml.html, logging, datetime, json
from pprint import pprint as pp
from collections import defaultdict, OrderedDict

import dateutil.parser

logging.basicConfig(level=logging.DEBUG)

requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.WARN)

class RCPCurrent(object):
	@staticmethod
	def download():

		def find_poll_in_module(poll):
			potential_polls = []
			pollster = poll['pollster']
			candidates_values = sorted([(x['name'], x['value']) for x in poll['candidate']])
			poll['date'] = dateutil.parser.parse(poll['date'])
			# print candidates_values
			# print ""
			response = requests.get("http://cdn.realclearpolitics.com/epolls/json/%s_polling_module.js" % poll['poll_id'])
			module = json.loads(response.content.replace("\\'", "'"))

			module['rcp_polls']['moduleInfo']['lastBuildDate'] = dateutil.parser.parse(module['rcp_polls']['moduleInfo']['lastBuildDate'])

			if poll['date'].date() > module['rcp_polls']['moduleInfo']['lastBuildDate'].date():
				return {"id": "", "date": "", "last_build_date": module['rcp_polls']['moduleInfo']['lastBuildDate']}

			for module_poll in module['rcp_polls']['poll']:
				if module_poll['type'] not in ['poll', 'poll_rcp_avg']: continue
				module_poll_pollster = module_poll['pollster']
				module_poll_candidates_values = sorted([(x['name'], x['value']) for x in module_poll['candidate']])
				module_poll['updated'] = dateutil.parser.parse(module_poll['updated'])
				module_poll['last_build_date'] = module['rcp_polls']['moduleInfo']['lastBuildDate']
				# print module_poll['pollster'], module_poll_candidates_values
				# module_poll_pollster == pollster and
				if module_poll['updated'].date() == poll['date'].date() and candidates_values == module_poll_candidates_values:
					potential_polls.append(module_poll)
			if len(potential_polls) == 1:
				return potential_polls[0]
			else:
				# return sorted([x['updated'] for x in potential_polls])[-1]
				raise Exception("find too many (%d) polls in module poll for module %s" % (len(potential_polls), poll['poll_id']))

		firebase.delete('/rcp', None)

		data = requests.get("http://cdn.realclearpolitics.com/epolls/json/latest_election_polls_clean.js").json()
		for poll in data['election']['poll']:
			date = dateutil.parser.parse(poll['date']).date()
			# if date >= datetime.datetime.today().date() - datetime.timedelta(1):
			module_poll = find_poll_in_module(poll)
			result = firebase.post(url='/rcp', data={"poll": poll, "module_poll": module_poll}, headers={'print': 'pretty'})
			print module_poll['id'], "|", poll['date'], poll['pollster'], "|", poll['race'], "|", poll['poll_id']

def get_module_ids():
	response = requests.get("http://cdn.realclearpolitics.com/epolls/json/")
	logging.debug("lxml parsing response")
	doc = lxml.html.fromstring(response.content)
	filenames = [x.get('href') for x in doc.cssselect("tr td a")]

	ids_polling_module = []
	ids_historical = []
	ids_current_rcp_average = []
	for filename in filenames:
		if "_polling_module.js" in filename: ids_polling_module.append(int(filename.replace("_polling_module.js", "")))
		if "_historical.js" in filename and "_map_historical.js" not in filename:
			ids_historical.append(int(filename.replace("_historical.js", "")))
		if "_current_rcp_average.js" in filename and "m" not in filename:
			ids_current_rcp_average.append(int(filename.replace("_current_rcp_average.js", "")))

	# module_ids = list(set(ids_polling_module) & set(ids_historical) & set(ids_current_rcp_average))
	# return module_ids
	return ids_polling_module

def get_races():
	election_ids = OrderedDict([
		("2010 Senate", 1),
		("2010 House", 12),
		("2010 Governor", 4), # Test 23
		("2012 House", 19),
		("2012 President", 21), # Test 16
		("2012 Senate", 22), # Test 17
		("2012 Governor", 24),
		("2014 Senate", 25),
		("2014 Governor", 26),
		("2014 House", 28)
	])

	for election, election_id in election_ids.iteritems():
		data = requests.get("http://cdn.realclearpolitics.com/epolls/json/%d_map.js" % election_id).json()
		for race in data['election']['race']:
			race['election'] = election
			race['_id'] = race['id']
			logging.debug(" ".join([race['election'], race['race_id'], race['region_key'], race['status'], ", ".join([x['name'] for x in race['candidate']])]))
			rcp_races.insert(race)

def get_jsons(module_ids):
	for module_id in module_ids:
		polling_module_url = "http://www.realclearpolitics.com/epolls/json/%d_polling_module.js" % module_id

		try:
			polling_module = requests.get(polling_module_url).json()
			polling_module['_id'] = polling_module['rcp_polls']['moduleInfo']['id']
			info = polling_module['rcp_polls']['moduleInfo']
			logging.debug(" ".join([info['id'], info['title'], info['state'], info['link']]))
			rcp_modules.insert(polling_module)
		except Exception as e:
			print e
			continue

def extract_rcp_questions():
	for module in rcp_modules.find():
		info = module['rcp_polls']['moduleInfo']
		items = module['rcp_polls']['poll']

		cycle_or_type = re.search(r"http://www.realclearpolitics.com/epolls/(.*?)/.*", module['rcp_polls']['moduleInfo']['link'], re.I).groups()[0]
		if cycle_or_type.isdigit():
			cycle = int(cycle_or_type)
			question_type = "voting"
		elif cycle_or_type in ["other", "approval_rating"]:
			cycle = None
			question_type = cycle_or_type
		else:
			raise Exception("regex failed on module link")

		for item in items:
			if item['type'] in ['poll', 'poll_rcp_avg']:
				item['_id'] = item.pop('id')
				item['state'] = info['state']
				item['country'] = info['country']
				item['title'] = info['title']
				item['module_id'] = info['id']
				item['module_link'] = info['link']
				item['cycle'] = cycle
				item['type'] = question_type
				logging.debug(" ".join([item['_id'], item['title'], item['state'], item['pollster'], ", ". join([x['name'] for x in item['candidate']])]))
				rcp_questions.insert(item)

def group_pollsters_by_id():
	pollsters_by_id = defaultdict(set)

	for question in rcp_questions.find():
		pollster = question['pollster'].replace("*", "")
		m = re.match(r"(.*)\s\(([D,R])(?:-)?(.*)\)", pollster, re.I)
		if m: pollster = m.group(1)

		if pollster not in pollsters_by_id[question.get('pollster_id')]:
			pollsters_by_id[question.get('pollster_id')] |= set([pollster])

	return pollsters_by_id

def group_pollsters_by_name():
	pollsters = defaultdict(set)

	for question in rcp_questions.find():
		pollster = question['pollster'].replace("*", "")
		m = re.match(r"(.*)\s\(([D,R])(?:-)?(.*)\)", pollster, re.I)
		if m: pollster = m.group(1)

		if question.get('pollster_id') and question.get('pollster_id') not in pollsters[pollster]:
			pollsters[pollster] |= set([question.get('pollster_id')])

	return pollsters

def group_pollsters_by_name_and_id(log=False):
	pollsters = {}
	pollsters_by_name = group_pollsters_by_name()
	pollsters_by_id = group_pollsters_by_id()

	del pollsters_by_id[None]

	duplicate_names = {}
	for pollster_id, pollster_names in pollsters_by_id.iteritems():
		if len(pollster_names) > 1:
			canonical = pollster_names.pop()
			duplicate_names[canonical] = pollster_names | set([canonical])
			for pollster_name in pollster_names:
				pollsters_by_name[canonical] |= set(pollsters_by_name[pollster_name])
				del pollsters_by_name[pollster_name]

	for pollster, pollster_ids in pollsters_by_name.iteritems():
		for pollster_id in pollster_ids:
			if pollster in pollsters:
				pollsters[pollster]['names'] |= set(pollsters_by_id.get(pollster_id)) if pollsters_by_id.get(pollster_id) else set()
				pollsters[pollster]['ids'] |= set(pollster_ids)
			else:
				pollsters[pollster] = {'names': set(), 'ids': set()}
				pollsters[pollster]['names'] |= set(pollsters_by_id.get(pollster_id)) if pollsters_by_id.get(pollster_id) else set()
				pollsters[pollster]['ids'] |= set(pollster_ids)

	for pollster_name, alternate_names in duplicate_names.iteritems():
		pollsters[pollster_name]['names'] |= alternate_names

	return pollsters

def extract_rcp_pollsters():
	pollsters = group_pollsters_by_name_and_id()
	for pollster_name, pollster in pollsters.iteritems():
		pollster['_id'] = pollster_name
		pollster['names'] = list(pollster['names'])
		pollster['ids'] = list(pollster['ids'])
		print pollster
		rcp_pollsters.insert(pollster)

if __name__ == '__main__':

	if rcp_races.count() == 0:
		races = get_races()

	if rcp_modules.count() == 0:
		module_ids = get_module_ids()
		get_jsons(module_ids)

	if rcp_questions.count() == 0:
		extract_rcp_questions()

	if rcp_pollsters.count() == 0:
		extract_rcp_pollsters()

	if rcp_pollsters.find({"ftename": {"$exists": True}}).count() == 0:

		with open("data/rcp_mapping.csv") as f:
			reader = csv.reader(f)
			for row in reader:
				pollster = rcp_pollsters.find_one(row[0])
				if pollster:
					print row[0], "| saved"
					pollster['ftename'] = row[1]
					rcp_pollsters.save(pollster)
				else:
					print row[0], "| not found"

		for rcp_pollster in rcp_pollsters.find():
			fte_pollster = fte_pollsters.find_one({"name": rcp_pollster['_id']})
			if fte_pollster and not rcp_pollster.get('ftename'):
				rcp_pollster['ftename'] = fte_pollster['name']
				print rcp_pollster['_id'], "| saved"
				rcp_pollsters.save(rcp_pollster)

	RCPCurrent.download()


	# group_pollsters_by_id()
	# group_pollsters_by_name()
	# group_pollsters_by_name_and_id()
