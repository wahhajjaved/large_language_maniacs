"""`main` is the top level module for your Flask application."""

# Import the Flask Framework
from flask import Flask, request, make_response, current_app
from datetime import timedelta
from functools import update_wrapper
from google.appengine.ext import ndb
import time
app = Flask(__name__)
# Note: We don't need to call run() since our application is embedded within
# the App Engine WSGI application server.

def crossdomain(origin=None, methods=None, headers=None,
                max_age=21600, attach_to_all=True,
                automatic_options=True):
    if methods is not None:
        methods = ', '.join(sorted(x.upper() for x in methods))
    if headers is not None and not isinstance(headers, basestring):
        headers = ', '.join(x.upper() for x in headers)
    if not isinstance(origin, basestring):
        origin = ', '.join(origin)
    if isinstance(max_age, timedelta):
        max_age = max_age.total_seconds()

    def get_methods():
        if methods is not None:
            return methods

        options_resp = current_app.make_default_options_response()
        return options_resp.headers['allow']

    def decorator(f):
        def wrapped_function(*args, **kwargs):
            if automatic_options and request.method == 'OPTIONS':
                resp = current_app.make_default_options_response()
            else:
                resp = make_response(f(*args, **kwargs))
            if not attach_to_all and request.method != 'OPTIONS':
                return resp

            h = resp.headers

            h['Access-Control-Allow-Origin'] = origin
            h['Access-Control-Allow-Methods'] = get_methods()
            h['Access-Control-Max-Age'] = str(max_age)
            if headers is not None:
                h['Access-Control-Allow-Headers'] = headers
            return resp

        f.provide_automatic_options = False
        return update_wrapper(wrapped_function, f)
    return decorator

class detail(ndb.Model):
    session = ndb.StringProperty()
    text = ndb.StringProperty()
    stackNum = ndb.StringProperty()
    timestamp = ndb.StringProperty()

class room(ndb.Model):
    session = ndb.StringProperty()
    number = ndb.StringProperty()
    order = ndb.StringProperty()
    goto = ndb.StringProperty()
    timestamp = ndb.StringProperty()

class goto(ndb.Model):
    session = ndb.StringProperty()
    number = ndb.StringProperty()
    detail = ndb.StringProperty()
    answer1 = ndb.StringProperty()
    answer2 = ndb.StringProperty()
    timestamp = ndb.StringProperty()

class notes(ndb.Model):
    session = ndb.StringProperty()
    json = ndb.StringProperty()
    timestamp = ndb.StringProperty()

@app.route('/')
def hello():
    return '<p>You realize you aren&rsquo;t supposed to be here, right?</p><p>You can&rsquo;t get here by following the rules and yet here you are. Is this how you always do things? Is this how life works in your world &ndash; sneaking around, cheating, losing the thread, getting distracted from the most important fucking task in the world?</p><p><strong>What does that say about you?</strong></p><p><strong>What does that say about your chances of finding your daughter alive and unhurt?</strong></p><p>Get out of here. Go find your little girl.</p>'

@app.route('/logDetails', methods=['POST', 'GET'])
@crossdomain(origin='*')
def logDetails():
    if request.method == 'POST':
        thisDetail = detail(session = request.form['session'], text = request.form['text'], stackNum = request.form['stackNum'], timestamp = time.strftime("%y-%m-%d-%H%M:%S"))
        thisDetail.put();
        return 'posted'
    else:
        return 'This method only accepts POSTs'

@app.route('/logNotes', methods=['POST', 'GET'])
@crossdomain(origin='*')
def logNotes():
    if request.method == 'POST':
        thisNotes = notes(session = request.form['session'], json = request.form['json'], timestamp = time.strftime("%y-%m-%d-%H%M:%S"))
        thisGoto.put();
        return 'posted'
    else:
        return 'This method only accepts POSTs'

@app.route('/logGoto', methods=['POST', 'GET'])
@crossdomain(origin='*')
def logGoto():
    if request.method == 'POST':
        thisGoto = goto(session = request.form['session'], number = request.form['number'], detail = request.form['detail'], answer1 = request.form['answer1'], answer2 = request.form['answer2'], timestamp = time.strftime("%y-%m-%d-%H%M:%S"))
        thisGoto.put();
        return 'posted'
    else:
        return 'This method only accepts POSTs'

@app.route('/logRoom', methods=['POST', 'GET'])
@crossdomain(origin='*')
def logRoom():
    if request.method == 'POST':
        thisRoom = room(session = request.form['session'], number = request.form['number'], order = request.form['order'], goto = request.form['gotoNum'], timestamp = time.strftime("%y-%m-%d-%H%M:%S"))
        thisRoom.put();
        return 'posted'
    else:
        return 'This method only accepts POSTs'

@app.errorhandler(404)
def page_not_found(e):
    """Return a custom 404 error."""
    return 'Sorry, Nothing at this URL.', 404


@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500
