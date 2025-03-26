import os

import json
from flask import Flask, jsonify, abort, make_response

from amazon import run_test, top3
import db_model as db

app = Flask(__name__)

@app.route('/products', methods = ['GET'])
def get_products():
	return make_response(jsonify( { 'error': "Specify input" } ), 200)

@app.route('/products/<string:keyword>/<string:callback>', methods = ['GET'])
def get_product(keyword, callback):
	if (not keyword) or (not callback):
		abort(404)
	results = run_test('All', keyword, 'Images, ItemAttributes, OfferSummary')
	results = json.dumps( results )
	result = callback + '(' + results + ');'
	return result

@app.route('/get_user/<string:user_email>/<string:callback>', methods = ['GET'])
def get_user(user_email, callback):
	if (not user_email) or (not callback):
		abort(404)
	user_id = db.login(user_email)
	result = json.dumps( user_id )
	result = callback + '(' + result + ');'
	return result

@app.route('/get_questions/<string:callback>', methods = ['GET'])
def get_questions(callback):
	if (not callback):
		abort(404)
	questions = db.get_questions()
	result = json.dumps( questions )
	result = callback + '(' + result + ');'
	return result

@app.route('/get_answers/<string:user_id>/<string:callback>', methods = ['GET'])
def get_answers(user_id, callback):
	if (not callback):
		abort(404)
	answers = db.get_answers(user_id)
	result = json.dumps( answers )
	result = callback + '(' + result + ');'
	return result

@app.route('/set_answer/<string:user_id>/<string:question_id>/<string:answer_text>/<string:callback>', methods = ['GET'])
def set_answer(user_id, question_id, answer_text, callback):
	if (not callback):
		abort(404)
	answers = db.set_answer(user_id, question_id, answer_text)
	result = json.dumps( answers )
	result = callback + '(' + result + ');'
	return result


@app.route('/get_recs/<string:user_id>/<string:callback>', methods = ['GET'])
def get_recs(user_id, callback):
	if (not callback):
		abort(404)
	if (user_id == '1387154996'):
		user_id = 21
	answers = db.get_answers(user_id)
	answers = answers['results']
	recs = []
	for answer in answers:
		rec = top3('All', answer['answer_text'], 'Images, ItemAttributes, OfferSummary')
		recs.append({'question_text': answer['answer_text'], 'recs': rec['results']})
	result = json.dumps( {'results': recs, 'status': 0} )
	result = callback + '(' + result + ');'
	return result

@app.route('/get_questions_without_answer/<string:user_id>/<string:callback>', methods = ['GET'])
def get_questions_without_answer(user_id, callback):
	if (not callback):
		abort(404)
	result = db.get_questions_without_answer(user_id)
	result = json.dumps( result )
	result = callback + '(' + result + ');'
	return result


# @app.route('/users', methods = ['GET'])
# def get_users():
#     return jsonify( { 'results': get_users() })

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify( { 'error': 'Not found' } ), 404)

if __name__ == '__main__':
    app.run(debug = True)

