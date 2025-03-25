from flask import Flask, redirect, render_template, request, url_for
from flask.ext.sqlalchemy import SQLAlchemy

import re
import nltk
from stop_words import stops
from collections import Counter
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config["DEBUG"] = True

SQLALCHEMY_DATABASE_URI = "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
    username="sappho",
    password="mysqldbpw0o0o",
    hostname="sappho.mysql.pythonanywhere-services.com",
    databasename="sappho$comments",
)

app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_POOL_RECYCLE"] = 299

db = SQLAlchemy(app)

class Comment(db.Model):

    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(4096))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("main_page.html", comments=Comment.query.all())

    comment = Comment(content=request.form["contents"])
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/index', methods=['GET', 'POST'])
def new_index():
    errors = []
    results = {}
    if request.method == "POST":
        try:
            text = request.form['contents']
        except:
            errors.append(
                "Unable to get URL. Please make sure it's valid and try again."
            )
        #return text
        #raw = Comment(content=request.form["contents"])
        #nltk.data.path.append('./nltk_data/')  # set the path
        #tokens = nltk.word_tokenize(raw)
        #text = nltk.Text(tokens)
        # remove punctuation, count raw words
        nonPunct = re.compile('.*[A-Za-z].*')
        raw_words = [w for w in text if nonPunct.match(w)]
        raw_word_count = Counter(raw_words)
        # stop words
        #no_stop_words = [w for w in raw_words if w.lower() not in stops]
        #no_stop_words_count = Counter(no_stop_words)
        # save the results
        results = sorted(
            no_stop_words_count.items(),
            key=operator.itemgetter(1),
            reverse=True
           )
    #    try:
    #        result = Result(
    #            url=url,
    #            result_all=raw_word_count,
    #            result_no_stop_words=no_stop_words_count
    #            )
    #        db.session.add(result)
    #       db.session.commit()
    #   except:
    #        errors.append("Unable to add item to database.")

    return render_template('index.html', errors=errors, results=results)


@app.route('/post')
def post():
    return render_template('post.html')