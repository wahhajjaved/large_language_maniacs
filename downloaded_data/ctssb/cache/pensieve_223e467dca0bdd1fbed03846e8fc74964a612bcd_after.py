from flask import Flask, render_template, request, make_response, jsonify
from elasticsearch import Elasticsearch
from urlparse import urlparse
from flask_cors import cross_origin
from logging import FileHandler
import logging
import requests
import os

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/index', methods=['POST'])
def createIndex():
    es = Elasticsearch()
    if not es.indices.exists(urlparse(request.form['url']).netloc):
        url = request.form['url']
        if not request.form['url'].endswith('/'):
            url = request.form['url'] + '/'
        try:
            contents = requests.get(url + "pages").json()
            for content in contents:
                es.index(index=urlparse(request.form['url']).netloc,
                         doc_type="html", body=content, id=content['id'])
            response = make_response()
            response.data = "Website indexed."
            return response
        except:
            response = make_response()
            response.status_code = 204
            # response.mimetype = "application/json"
            # response.data = {"reason": "No content found."}
            return response
    else:
        response = make_response()
        response.status_code = 409
        response.data = {"reason": "Index already exists"}
        return response


@app.route("/update", methods=['POST'])
@cross_origin()
def update():
    es = Elasticsearch()
    es.index(index=request.form['index'],
             doc_type=request.form['doc_type'],
             body=request.form['content'],
             id=request.form['id'])
    response = make_response()
    response.data = "Updated."
    return response


@app.route("/search")
def search():
    return render_template('search.html')


@app.route("/search/<string:index>/<string:doc_type>", methods=['GET'])
@cross_origin()
def searchByParams(index, doc_type):
    es = Elasticsearch()
    if 'type' in request.args:
        query = es.search(index, doc_type, body={'query':
                                                 {'prefix':
                                                  {request.args['type']:
                                                   request.args['q']
                                               }}})
    else:
        query = es.search(index, doc_type, body={'query':
                                                 {'prefix':
                                                  {"_all": request.args['q']
                                               }}})
    return jsonify(query['hits'])


@app.route("/hits/<string:index>/<string:doc_type>")
@cross_origin()
def getHits(index, doc_type):
    es = Elasticsearch()
    query_body = {"size": 0,
                  "aggs":
                  {"grouped_by":
                   {
                       "terms":
                       {
                           "field": request.args['field'],
                           "size": 0
                       }
                   }
               }
              }
    query = es.search(index, doc_type, body=query_body)
    return jsonify(query['aggregations'])


fil = FileHandler(os.path.join(os.path.dirname(__file__), 'logme'), mode='a')
fil.setLevel(logging.ERROR)
app.logger.addHandler(fil)


if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5001, debug=True)