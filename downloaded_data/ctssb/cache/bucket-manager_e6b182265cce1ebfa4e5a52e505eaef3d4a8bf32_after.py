## flask modules
from flask import Flask
from flask import request, Response
from flask import render_template
from flask import make_response
from flask import g
from flask import redirect
from flask import session
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.security import *
from flask.ext.security.datastore.sqlalchemy import SQLAlchemyUserDatastore

## python modules
from werkzeug import secure_filename
import json
import os
from random import choice
from math import *
from smtplib import *
from email.mime.text import MIMEText
import email
import re
from base64 import *

## local modules
from Neo4jInterface import *
from AuthInterface import *
from StatsInterface import *
from BucketStructure import *


app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SECRET_KEY'] = 'VKqerq3E/adf23d0444'

AUTH_LEVEL = 4


def checkAuth():
    token = request.args.get('token')
    if not token:
        try:
            token = session['access_token']
        except KeyError:
            return redirect('http://data-dashboard.herokuapp.com')

    session['access_token'] = str(token)
    session['auth_level'] = getAccessLevel(session['access_token'])
    if session['auth_level'] < AUTH_LEVEL:
        return redirect('http://data-dashboard.herokuapp.com')

    updateSession(session['access_token'], session['auth_level'])


def parseEmail(emailstr):
    print emailstr, 'input'
    pattern = '[A-z0-9._%-]+@[A-z0-9.-]+\.[A-z]{2,4}'
    return re.findall(pattern, emailstr)


def sendEmail(content, recips, subjectline="results from twitter-xray"):
    errors = []

    for emailto in recips:
        ## emails the data using lextarget.adaptly@gmail.com to send messages
        user = 'lextarget.adaptly@gmail.com'
        pwd = 'lexmemaybe'
        server = SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(user, pwd)

        msg = email.MIMEMultipart.MIMEMultipart()
        msg['Subject'] = subjectline
        msg['From'] = user
        msg['To'] = emailto

        for filename in content:
            attachment = email.mime.base.MIMEBase('application', 'octect-stream')
            attachment.set_payload(content[filename])
            email.encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', 'attachment;filename=' + filename)
            msg.attach(attachment)

        try:
            server.sendmail(user, emailto, msg.as_string())
        except Exception as e:
            errors.append(e.message)

    server.close()
    return errors


#### BEGIN APP ####


@app.route('/', methods=['POST', 'GET'])
def show_bucket():
##    checkAuth()

    if 'tags' in session:
        bucket_list = getBuckets(session['tags'])
    else:
        bucket_list = getBuckets()
    if not bucket_list:
        bucket_list = ['---']

    if request.method == 'GET':
        if 'selected_bucket' in session and \
           session['selected_bucket'] in bucket_list:
            selected_bucket = session['selected_bucket']
            del session['selected_bucket']
        else:
            selected_bucket = choice(bucket_list)
    else:
        selected_bucket = request.form['bucket_menu']

    bucket_data = loadBucket(selected_bucket)
    if bucket_data:
        keywords_hash = bucket_data.getHash()
        stats_fetcher = StatsFetcher(keywords_hash, ['CPC', 'CPM', 'CTR'])

        keywords = bucket_data.getWords()
##        edges = bucket_data.dumpEdges()
        centrality = bucket_data.dumpCentrality()
        bucket_stats = bucket_data.dumpStats()

        centrality_scores = centrality.values()

##        edge_scores = sorted(edges.values(), reverse=True)
##        nedges = len(edge_scores)

##        n_longest_edges = int(nedges/10) + 1
##        topic_range = sum(edge_scores[0:n_longest_edges]) / float(n_longest_edges)
##        cohesion = 100 * len(centrality_scores) / sum(centrality_scores)

        max_size = min(50.0, 50.0 * 4. / (sqrt(len(centrality_scores))))
        min_centrality = min(centrality_scores)
        cloud_data = map(lambda k: {"text":k, "size":max_size * pow(min_centrality / centrality[k], 1.25)}, centrality)

        list_data = '\n'.join(map(lambda k: ('%.3f' % (1.0 / k[1]))[1:] + '\t\t' + k[0], sorted(centrality.items(), key=lambda j: j[1])))

        historic_stats = stats_fetcher.getStats()
        if 'CPC' in historic_stats:
            historic_stats['CPC'] = "$%.2f" % (historic_stats['CPC'] / 100)
        if 'CPM' in historic_stats:
            historic_stats['CPM'] = "$%.2f" % (historic_stats['CPM'] / 100)
        if 'CTR' in historic_stats:
            historic_stats['CTR'] = '%.3f' % (100 * historic_stats['CTR']) + '%'
    else:
        keywords = []
##        edges = []
        centrality = {}
        bucket_stats = {}

        cloud_data = []
        list_data = ""

##        topic_range = 0.0
##        cohesion = 0.0

        historic_stats = {}

    bucket_stats.update({'SIZE__':len(keywords), 'CTR__':historic_stats.get('CTR', 'unknown'), 'CPC__':historic_stats.get('CPC', 'unknown'), 'CPM__':historic_stats.get('CPM', 'unknown')})
    if not 'REACH__' in bucket_stats:
        bucket_stats['REACH__'] = 'unknown'

    return render_template('show_bucket.html', selected_bucket=bucket_stats, \
                                               bucket_list=bucket_list, \
                                               keywords=keywords, \
                                               keyword_centrality=centrality, \
                                               cloud_data = json.dumps(cloud_data), \
                                               list_data = json.dumps(list_data)
                          )


@app.route('/save/', methods=['POST'])
def save_bucket():
##    checkAuth()

    bucket_name = request.form['new_bucket_name'].strip()
    tags = request.form['new_bucket_tags'].strip()
    keywords = request.form['new_bucket_contents'].strip()

    tags = filter(lambda j: j, map(lambda k: k.strip().lower(), tags.split(',')))
    keywords = filter(lambda j: j, map(lambda k: k.strip(), keywords.split(',')))

    new_bucket = BucketStructure(keywords)
    new_bucket.calculateEdges()
    saveBucket(bucket_name, tags, new_bucket)

    session['selected_bucket'] = bucket_name

    return redirect('/')


@app.route('/filter/', methods=['POST'])
def filter_bucket_list():
##    checkAuth()
    if 'tags' in session:
        del session['tags']

    tag_filter = filter(lambda j: j, map(lambda k: k.strip(), request.form['tags'].split(',')))
    if tag_filter:
        session['tags'] = tag_filter
    return redirect('/')


@app.route('/export/', methods=['POST'])
def export_data():
    export_data = dict(request.form)

    email_to = parseEmail(export_data["emailto"][0])
    del export_data["emailto"]

    bucket_name = export_data["bucketname"][0]
    bucket_tag = re.sub(' ', '_', bucket_name)
    del export_data["bucketname"]

    email_data = {}
    if 'word_cloud' in export_data:
        email_data[bucket_tag + '_CLOUD.png'] = b64decode(export_data['word_cloud'][0].split(',')[1])

    if 'csv' in export_data:
        email_data[bucket_tag + '.csv'] = export_data['csv'][0].encode('utf-16')

    sendEmail(email_data, email_to, subjectline=bucket_name + ' data')

    return redirect('/')


if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

