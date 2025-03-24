import yaml, os, twiml
from flask import Flask, request
from client import StockzClient

# Configuration #

try:
	config = yaml.load(open('config.yml', 'r'))

	if not isinstance(config, dict):
		raise Exception()
except:
	raise Exception('Invalid config.yml')

if 'flask' not in config or not isinstance(config['flask'], dict):
	raise Exception('Missing flask from config')

if 'client' not in config or not isinstance(config['client'], dict):
	raise Exception('Missing client from config')

if 'errors' not in config or not isinstance(config['errors'], dict):
	raise Exception('Missing errors from config')

if 'default' not in config['errors'] or not isinstance(config['errors']['default'], basestring):
	raise Exception('Missing default error from config')

# Application #

app = Flask(__name__)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

app.secret_key = os.urandom(16)

# Client #

client = StockzClient(**config['client'])

# Functions #

def get_response(message):
	if not isinstance(message, basestring):
		raise TypeError('message must be a string')

	return twiml.response(twiml.message(message))

def get_error(name):
	if not isinstance(name, basestring):
		raise TypeError('name must be a string')

	if name in config['errors']:
		return config['errors'][name]

	return config['errors']['default']

# Routes #

@app.route('/sms', methods = ['GET', 'POST'])
def twilio():
	if 'From' not in request.form or 'Body' not in request.form:
		return get_response(get_error('default'))

	sender = request.form['From']
	body = request.form['Body']

	response = client.execute(body)

	if response is None:
		return get_response(get_error('InvalidActionError'))

	split = response.split()

	if split[0] == 'error':
		return get_response(get_error(split[1]))

	return twiml.response(twiml.message(response))

# Server #

if __name__ == '__main__':
	app.run(**config['flask'])
