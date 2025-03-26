from flask import Flask, request, render_template, make_response, jsonify
from flask_restful import Resource, Api, reqparse, inputs
import pymongo
import datetime
import sys
import smtplib, ssl
import string
import random
import time
from cassandra.cluster import Cluster

app = Flask(__name__)
api = Api(app)

class AddQuestion(Resource):
	def post(self):
		parser = reqparse.RequestParser()
		parser.add_argument('title')
		parser.add_argument('body')
		parser.add_argument('username')
		parser.add_argument('tags', action='append')
		parser.add_argument('media', action='append')
		args = parser.parse_args()
		if args['media'][0] is None:
			args['media'] = None
		print("Adding question -> {}".format(str(args)), sys.stderr)
		if args['media'] is not None:
			tup = check_questions_free(args['media'])
			if not tup[0]:
				return {'status':'error', 'error':'media id {} already associated'.format(tup[1])}
		questions = get_questions_coll()
		dbidnum = questions.find_one({'idnum':{'$gt': 0}})
		if dbidnum == None:
			idnum = {}
			idnum['idnum'] = 0
			questions.insert_one(idnum)
		idnum = (dbidnum['idnum'] + 1) if dbidnum is not None else 1
		questions.update_one({'idnum':{'$gt':-1}}, {'$set':{'idnum':idnum}})
		question = {}
		question['id'] = args['username'] + '_q_' + str(idnum) 
		question['title'] = args['title']
		question['body'] = args['body']
		question['username'] = args['username']
		question['tags'] = [] if args['tags'] is None else args['tags']
		question['score'] = 1
		question['view_count'] = 0
		question['answer_count'] = 0
		question['timestamp'] = time.time()
		question['accepted_answer_id'] = None
		question['media'] = args['media']
		self._set_added(args['media'])
		question['viewed'] = []
		questions.insert_one(question)
		return {'status': 'OK', 'id': question['id']}

	def _set_added(self, ids):
		cluster = Cluster(['130.245.171.50'])
		session = cluster.connect(keyspace='stackoverflow')
		if len(ids) == 1:
			inlist = '(\'{}\')' .format(ids[0])
		else:
			inlist = '('
			for id in ids:
				inlist += "'{}',".format(id)
			inlist = inlist[:-1]
			inlist += ')'
		cqlupdate = "update media set added = true where id in {};".format(inlist)
		session.execute(cqlupdate)


	

class GetQuestion(Resource):
	def post(self):
		args = parse_args_list(['id', 'user'])
		print("getting question {}".format(str(args)), sys.stderr)
		questions = get_questions_coll()
		question = questions.find_one({'id':args['id']})
		if question is None:
			return {'status':'error', 'error': 'no question with id ' + args['id']}, 400
		viewed = question['viewed']
		inc = args['user'] not in viewed
		if inc:
			viewed.append(args['user'])
			questions.update_one({'id':args['id']}, {'$push':{'viewed':args['user']}, 
				'$set':{'view_count':len(viewed)}})
		resp = {}
		resp['status'] = 'OK'
		q = {}
		q['id'] = question['id']
		q['title'] = question['title']
		q['body'] = question['body']
		q['score'] = question['score']
		q['view_count'] = question['view_count'] if not inc else len(viewed)
		q['answer_count'] = question['answer_count']
		q['timestamp'] = question['timestamp']
		q['media'] = question['media'] if question['media'] is not None else []
		q['tags'] = question['tags']
		q['accepted_answer_id'] = question['accepted_answer_id']
		users = get_users_coll()
		user = users.find_one({'username':question['username']})
		u = {}
		u['username'] = user['username']
		u['reputation'] = user['reputation']
		q['user'] = u
		resp['question'] = q
		#print(str(resp) + "<- is resp ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^", sys.stderr)
		return resp

class DeleteQuestion(Resource):
	def delete(self):
		args = parse_args_list(['id', 'user'])
		questions = get_questions_coll()
		question = questions.find_one({'id':args['id']})
		if question is not None and question['username'] == args['user']:
			self._delete_answers(args['id'])
			media = question['media']
			if media is not None:
				self._delete_media(media)
			questions.delete_one({'id':args['id']})
			#TODO : Delete answers and associated metadata
			return {'status': 'OK'}
		else:
			resp = {'status': 'error'}, 400
			return resp
	def _delete_answers(self, id):
		answers = get_answers_coll()
		answers.delete_many({'question_id': id})

	def _delete_media(self, ids):
		cluster = Cluster(['130.245.171.50'])
		session = cluster.connect(keyspace='stackoverflow')
		liststring = '('
		if len(ids) == 1:
			liststring = "('{}')".format(ids[0])
		else:
			for id in ids:
				liststring += "'{}',".format(id)
			liststring = liststring[:-1]
			liststring += ')'
		cqldelete = 'delete from media where id in {};'.format(liststring)
		session.execute(cqldelete)



class AddAnswer(Resource):
	def post(self):
		parser = reqparse.RequestParser()
		parser.add_argument('body')
		parser.add_argument('username')
		parser.add_argument('id')
		parser.add_argument('media', action='append')
		args = parser.parse_args()
		answers = get_answers_coll()
		answer = {}
		dbidnum = answers.find_one({'idnum':{'$gt': 0}})
		if dbidnum == None:
			idnum = {}
			idnum['idnum'] = 0
			answers.insert_one(idnum)
		idnum = (dbidnum['idnum'] + 1) if dbidnum is not None else 1
		answers.update_one({'idnum':{'$gt':-1}}, {'$set':{'idnum':idnum}})
		answer['id'] = args['username'] + '_a_' + str(idnum)
		answer['question_id'] = args['id']
		answer['body'] = args['body']
		answer['media'] = args.get('media')
		answer['user'] = args['username']
		answer['score'] = 1
		answer['is_accepted'] = False
		answer['timestamp'] = time.time()
		answers.insert_one(answer)
		resp = {}
		resp['status'] = 'OK'
		resp['id'] = answer['id']
		return resp

class GetAnswers(Resource):
	def get(self, id):
		answers = get_answers_coll()
		questions = get_questions_coll()
		question = questions.find_one({'id':id})
		if question is None:
			return {'status':'error', 'error': 'no question with id ' + id}, 400
		answers_cur = answers.find({'question_id':id})
		resp = {}
		resp['answers'] = []
		for doc in answers_cur:
			ans = {}
			ans['id'] = doc['id']
			ans['user'] = doc['user']
			ans['body'] = doc['body']
			ans['score'] = doc['score']
			ans['is_accepted'] = doc['is_accepted']
			ans['timestamp'] = doc['timestamp']
			ans['media'] = doc['media']
			resp['answers'].append(ans)
		resp['status'] = 'OK'
		return resp

class Search(Resource):
	def post(self):
		parser = reqparse.RequestParser()
		parser.add_argument('timestamp', type=float)
		parser.add_argument('limit', type=int)
		parser.add_argument('query')
		parser.add_argument('sort_by')
		parser.add_argument('tags', action='append')
		parser.add_argument('has_media', type=inputs.boolean)
		parser.add_argument('accepted', type=inputs.boolean)
		args = parser.parse_args()
		questions = get_questions_coll()
		questions.create_index([('title', 'text'), ('body', 'text')], default_language='none')
		#print('#####################' + str(args), sys.stderr)
		cur = None
		query = {}
		sort_by_score = True
		if args['tags'] is not None and args['tags'][0] is None:
			args['tags'] = None
		#print('#####################' + str(args), sys.stderr)
		if args['query'] is None and args['tags'] is None and args['has_media'] is None and args['accepted'] is None:
			query['timestamp'] = {'$lt':args['timestamp']}
		# if args['query'] is None or args['query'] == '':	# if search query wasn't entered
			# cur = questions.find({'timestamp':{'$lt':args['timestamp']}}).limit(args['limit'])
		else:
			query['$and'] = [{'timestamp':{'$lt':args['timestamp']}}]
			
			if args['query'] is not None:	# if search query was entered
				query['$and'].append({'$text':{'$search':args['query']}})
			if args['tags'] is not None:
				query['$and'].append({'tags':{'$all':args['tags']}})
			if args['has_media'] is not None and args['has_media']:
				query['$and'].append({'media':{'$ne':None}})
			if args['accepted'] is not None and args['accepted']:
				query['$and'].append({'accepted_answer_id':{'$ne':None}})
#			if args['sort_by'] is not None:
#				print('sort_by: ' + str(args['sort_by']), sys.stderr)
#				if args['sort_by'] == 'timestamp':
#					sort_by_score = False


			# cur = questions.find({'$and': [{'timestamp':{'$lt':args['timestamp']}},
			# 							  {'$text':{'$search':args['query']}}]}).limit(args['limit'])
		cur = None
		if args['sort_by'] is not None:
			if args['sort_by'] == 'timestamp':
				sort_by_score = False
		#print('--------------------query: ' + str(query), sys.stderr)
		if sort_by_score:
			#print("^^^^^^^^^^^^^^^^^^^^^^^sorting by score", sys.stderr)
			cur = questions.find(query).limit(args['limit']).sort('score', -1)
		else:
			#print('^^^^^^^^^^^^^^^^^^^^^^^sorting by timestamp', sys.stderr)
			cur = questions.find(query).limit(args['limit']).sort('timestamp', -1)
		users = get_users_coll()
		listquestions = []
		for question in cur:
			#print(str(question) + '----------------------------', sys.stderr)
			resp = {}
			resp['status'] = 'OK'
			resp['id'] = question['id']
			resp['title'] = question['title']
			resp['body'] = question['body']
			resp['score'] = question['score']
			resp['view_count'] = question['view_count'] 
			resp['answer_count'] = question['answer_count']
			resp['timestamp'] = question['timestamp']
			resp['media'] = question['media'] if question['media'] is not None else []
			resp['tags'] = question['tags']
			resp['accepted_answer_id'] = question['accepted_answer_id']
			user = users.find_one({'username':question['username']})
			u = {}
			u['username'] = user['username']
			u['reputation'] = user['reputation']
			resp['user'] = u
			listquestions.append(resp)
		resp = {}
		resp['status'] = 'OK'
		resp['questions'] = listquestions
		return resp

class TopTen(Resource):
	def get(self):
		questions = get_questions_coll()
		resp = {}
		topten = []
		cur = questions.find({'view_count':{'$gt':-1}}).limit(10)
		for q in cur:
			#print(str(q) + '------------------------', std.err)
			question = {}
			question['id'] = q['id']
			question['title'] = q['title']
			question['body'] = q['body']
			question['view_count'] = q['view_count']
			topten.append(question)
		resp['status'] = 'OK'
		resp['questions'] = topten
		return resp

class Upvote(Resource):
	def post(self, id):
		parser = reqparse.RequestParser()
		parser.add_argument('username')
		parser.add_argument('upvote', type=inputs.boolean)
		args = parser.parse_args()
		#print('####################' + str(args), sys.stderr)
		username = args['username']
		upvote = args['upvote']
		step = 1 if upvote else -1
		users = get_users_coll()
		questions = get_questions_coll()
		question = questions.find_one({'id':id})
		score = question['score']
		poster_username = question['username']
		user = users.find_one({'username': username})
		poster = users.find_one({'username': poster_username})
		rep = poster['reputation']
		upvoted = user['upvoted']
		downvoted = user['downvoted']
		#print('id: {}, upvoted: {}, downvoted: {}'.format(id, str(upvoted), str(downvoted)), sys.stderr)
		if upvote:
			if id in upvoted:
				step -= 2
				users.update_one({'username':username}, {'$pull':{'upvoted':id}})
			elif id in downvoted:
				step += 1
				users.update_one({'username':username}, {'$pull':{'downvoted':id}, 
					'$push':{'upvoted':id}})
			else:
				#print('adding {} to upvoted'.format(id), sys.stderr)
				users.update_one({'username':username}, {'$push':{'upvoted':id}})
		else:
			if id in upvoted:
				step -= 1
				users.update_one({'username':username}, {'$pull':{'upvoted':id},
					'$push':{'downvoted':id}})
			elif id in downvoted:
				step += 2
				users.update_one({'username':username}, {'$pull':{'downvoted':id}})
			else:
				#print('adding {} to downvoted'.format(id), sys.stderr)
				users.update_one({'username':username}, {'$push':{'downvoted':id}})
		score += step
		questions.update_one({'id':id}, {'$set':{'score':score}})
		rep = rep + step if rep + step > 1 else 1
		users.update_one({'username':poster_username}, {'$set':{'reputation':rep}})
		resp = {}
		resp['status'] = 'OK'
		return resp

class UpvoteAnswer(Resource):
	def post(self, id):
		parser = reqparse.RequestParser()
		parser.add_argument('username')
		parser.add_argument('upvote', type=inputs.boolean)
		args = parser.parse_args()
		#print('####################' + str(args), sys.stderr)
		username = args['username']
		upvote = args['upvote']
		step = 1 if upvote else -1
		users = get_users_coll()
		answers = get_answers_coll()
		answer = answers.find_one({'id':id})
		score = answer['score']
		poster_username = answer['user']
		user = users.find_one({'username': username})
		poster = users.find_one({'username': poster_username})
		rep = poster['reputation']
		upvoted = user['upvoted']
		downvoted = user['downvoted']
		#print('id: {}, upvoted: {}, downvoted: {}'.format(id, str(upvoted), str(downvoted)), sys.stderr)
		if upvote:
			if id in upvoted:
				step -= 2
				users.update_one({'username':username}, {'$pull':{'upvoted':id}})
			elif id in downvoted:
				step += 1
				users.update_one({'username':username}, {'$pull':{'downvoted':id}, 
					'$push':{'upvoted':id}})
			else:
				#print('adding {} to upvoted'.format(id), sys.stderr)
				users.update_one({'username':username}, {'$push':{'upvoted':id}})
		else:
			if id in upvoted:
				step -= 1
				users.update_one({'username':username}, {'$pull':{'upvoted':id},
					'$push':{'downvoted':id}})
			elif id in downvoted:
				step += 2
				users.update_one({'username':username}, {'$pull':{'downvoted':id}})
			else:
				#print('adding {} to downvoted'.format(id), sys.stderr)
				users.update_one({'username':username}, {'$push':{'downvoted':id}})
		score += step
		answers.update_one({'id':id}, {'$set':{'score':score}})
		rep = rep + step if rep + step > 1 else 1
		users.update_one({'username':poster_username}, {'$set':{'reputation':rep}})
		resp = {}
		resp['status'] = 'OK'
		return resp

class AcceptAnswer(Resource):
	def post(self, id):
		args = parse_args_list(['username'])
		username = args['username']
		questions = get_questions_coll()
		answers = get_answers_coll()
		answer = answers.find_one({'id':id})
		qid = answer['question_id']
		question = questions.find_one({'id':qid})
		if username != question['username']:
			return {'status':'error', 'error':'not original asker'}, 400
		accepted_id = question['accepted_answer_id']
		if accepted_id is not None:
			return {'status':'error', 'error':'there is already an accepted answer'}, 400
		questions.update_one({'id':qid}, {'$set':{'accepted_answer_id':id}})
		answers.update_one({'id':id}, {'$set':{'is_accepted':True}})
		return {'status':'OK'}

class Reset(Resource):
	def get(self):
		myclient = pymongo.MongoClient('mongodb://130.245.170.88:27017/')
		myclient.drop_database('finalproject')
		return {'status':'OK'}
		# mydb = myclient['finalproject']


def check_questions_free(ids):
	cluster = Cluster(['130.245.171.50'])
	session = cluster.connect(keyspace='stackoverflow')
	if len(ids) == 1:
		inlist = '(\'{}\')' .format(ids[0])
	else:
		inlist = '('
		for id in ids:
			inlist += "'{}',".format(id)
		inlist = inlist[:-1]
		inlist += ')'
	cqlselect = 'select id, added from media where id in {}'.format(inlist)
	cur = session.execute(cqlselect)
	for row in cur:
		if not row[1]:
			return (False, row[0])
	return (True, None)

def parse_args_list(argnames):
	parser = reqparse.RequestParser()
	for arg in argnames:
		parser.add_argument(arg)
	args = parser.parse_args()
	return args

def get_questions_coll():
	# reconnecting may cause performance issues
	myclient = pymongo.MongoClient('mongodb://130.245.170.88:27017/')
	mydb = myclient['finalproject']
	users = mydb['questions']
	return users

def get_users_coll():
	myclient = pymongo.MongoClient('mongodb://130.245.170.88:27017/')
	mydb = myclient['finalproject']
	users = mydb['users']
	return users

def get_answers_coll():
	myclient = pymongo.MongoClient('mongodb://130.245.170.88:27017/')
	mydb = myclient['finalproject']
	users = mydb['answers']
	return users

api.add_resource(AddQuestion, '/add')
api.add_resource(GetQuestion, '/getquestion')
api.add_resource(AddAnswer, '/addanswer')
api.add_resource(GetAnswers, '/getanswers/<id>')
api.add_resource(Search, '/search')
api.add_resource(TopTen, '/topten')
api.add_resource(DeleteQuestion, '/deletequestion')
api.add_resource(Upvote, '/upvote/<id>')
api.add_resource(UpvoteAnswer, '/upvoteanswer/<id>')
api.add_resource(AcceptAnswer, '/acceptanswer/<id>')
api.add_resource(Reset, '/reset')

if __name__ == '__main__':
	app.run(debug=True)
