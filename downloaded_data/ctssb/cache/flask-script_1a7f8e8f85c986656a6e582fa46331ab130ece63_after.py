from flask import Flask, jsonify, request, render_template
import json
import traceback
import sys
import datetime

from model import StatsData, db

app = Flask(__name__)
app.debug = True

#vars used for page
global tokens
global listing_count
global reviews_count

@app.route('/')
def hello():
	global tokens, listing_count, reviews_count
	try:
		tokens
	except NameError:
		print ("well, it WASN'T defined after all!")
		tokens = {}
		listing_count = 0
		reviews_count = 0

	return render_template('home.html', tokens=tokens)


@app.route('/updatetoken', methods=['POST'])
def udpate_token():
	try:
		print('update tokens')
		global tokens, listing_count, reviews_count
		try:
			tokens
		except NameError:
			print ("define for the first time!!")
			tokens = {}
			listing_count = 0
			reviews_count = 0

		raw_str = request.get_data().decode('utf-8')
		json_obj = json.loads(raw_str)
		tokens[json_obj['token']] = {'listing': 0, 'review': 0, 'name': json_obj['location_name'], 'start_time': datetime.datetime.now(), 'last_updated_at': datetime.datetime.now()}
		print('created token for location: ', json_obj['location_name'])
		return jsonify({'status': 'ok'})
	except:
		print('error saving tokens')
		return jsonify({'status': 'fail'})



@app.route('/updatevalues', methods=['POST'])
def update_value():
	global tokens, listing_count, reviews_count
	print('updating values')
	raw_str = request.get_data().decode('utf-8')
	json_obj = json.loads(raw_str)
	print(json_obj)

	try:
		if json_obj['listing']:
			print('listing maybe ', json_obj['listing'])
			tokens[json_obj['token']]['listing'] += 1
			listing_count += 1
			tokens[json_obj['token']]['last_updated_at'] = datetime.datetime.now()
			print('done udpating listing')
	except KeyError:
		try:
			if json_obj['review']:
				print('review maybe ', json_obj['review'])
				tokens[json_obj['token']]['review'] += 1
				reviews_count += 1
				tokens[json_obj['token']]['last_updated_at'] = datetime.datetime.now()
				print('done udpating reviews')
		except KeyError:
			print ('not proper request')
			print(json_obj)
			tokens[json_obj['token']] = {'listing': 0, 'review': 0, 'name': json_obj['location_name'], 'start_time': datetime.datetime.now(), 'last_updated_at': datetime.datetime.now()}
		except NameError:
			reviews_count = 0
		

	return jsonify({'status': 'ok'})


@app.route('/getValues')
def get_values():
	global tokens
	try:
		tokens
	except NameError:
		print ("define for the first time!!")
		tokens = {}
		traceback.print_exc(file=sys.stdout)
	return jsonify(**tokens)


@app.route('/getRL')
def get_data():
	global reviews_count, listing_count
	try:
		reviews_count, listing_count
	except NameError:
		print ("define for the first time!")
		reviews_count = 0
		listing_count = 0
	temp= {'reviews': reviews_count, 'listings': listing_count}
	return jsonify(**temp)


@app.route('/savetodb')
def save_to_db():
	try:
		global tokens
		for token in tokens:
			payload = StatsData(token_id=token,
						location_name=tokens[token]['name'],
						listing_count=tokens[token]['listing'],
						review_count=tokens[token]['review'],
						start_date=tokens[token]['start_time'],
						last_updated_date=tokens[token]['last_updated_at'])
			db.session.add(payload)
			db.session.commit()
		return jsonify({'status': 'ok'})
	except:
		print('error saving to db')
		db.session.rollback()
		traceback.print_exc(file=sys.stdout)
		return jsonify({'status': 'failed'})
	finally:
		db.session.close()
		return jsonify({'status': 'failed'})


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.errorhandler(404)
def handle_404(e):
	return jsonify({'status': '404'})	


@app.errorhandler(500)
def handle_500(e):
	return jsonify({'status': '500'})	

if __name__ == "__main__":
	app.debug = True
	app.run()
