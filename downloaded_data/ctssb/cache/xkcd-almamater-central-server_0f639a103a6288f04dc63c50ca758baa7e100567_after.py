import os
import base64
import logging
import string
import itertools

from flask import Flask, request, render_template
from flask_mongoengine import MongoEngine
from flask_mongoengine import Document

from mongoengine.fields import StringField, IntField

chars = string.ascii_letters
iter_thing = itertools.combinations_with_replacement(chars, r=32)

# Determining the project root.
PROJECT_ROOT = os.path.dirname(os.path.realpath(__file__))

# Creating the Flask app object
app = Flask(__name__, static_folder=os.path.join(PROJECT_ROOT, 'static'), static_url_path='/max_sucks')
app.config['DEBUG'] = True
app.config['MONGODB_DB'] = 'hashes'


db = MongoEngine(app)

def jump_to_next_block():
    num_to_jump = 50000000
    return next(itertools.islice(iter_thing, num_to_jump, num_to_jump), None)

class Submission(Document):
    original = StringField(max_length=1024, required=True)
    diff_bits = IntField(required=True)
    submitted_by = StringField(max_length=2048, required=False, default='')


@app.route('/')
def index():
    submissions = Submission.objects().order_by('diff_bits')
    context = {'submissions': submissions}
    return render_template('index.html', **context)


@app.route('/submit/')
def get_hash():
    original = request.args.get('original', None)
    diff_bits = request.args.get('diff', None)
    submitted_by = request.args.get('submitted_by', None)

    if not submitted_by or submitted_by == '(null)':
        submitted_by = ""

    if original and diff_bits:
        submission = Submission(original=original, diff_bits=diff_bits, submitted_by=submitted_by)
        submission.save()
        return "Submission saved successfully"
    return "Missing parameter"


@app.route('/next_block')
def get_block():
    jump_to_next_block()
    return ''.join(iter_thing.next()) + '\n'


def calculate_diff(original, hash):
    original_b = base64.b64decode(original)
    hash_b = base64.b64decode(hash)
    total = 0
    for x, y in zip(original_b, hash_b):
        total += x == y
    return total


port = int(os.environ.get('PORT', 5000))
app.run(port=port, host='0.0.0.0')
