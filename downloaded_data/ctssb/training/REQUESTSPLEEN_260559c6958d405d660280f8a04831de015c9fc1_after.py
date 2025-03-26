import os

from flask import Flask, render_template, request
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from validate_email import validate_email

from password import SQLALCHEMY_DATABASE_URI
import config


app = Flask(__name__)
app.config.from_object("config")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
db = SQLAlchemy(app)


class Leak(db.Model):
    __tablename__ = 'LEAKS'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String())
    password = db.Column(db.String())
    password_hash = db.Column(db.String())
    name = db.Column(db.String())
    nickname = db.Column(db.String())
    leak_source = db.Column(db.String())

    def __init__(self, email="", password_hash="", password="",
                 name="", nickname="", leak_source=""):
        self.email = email
        self.password = password
        self.password_hash = password_hash
        self.name = name
        self.nickname = nickname
        self.leak_source = leak_source

    def __repr__(self):
        return '<Leak %r>' % self.email


@app.route("/")
def homepage():
    search_query = request.args.get("srch")
    if not search_query:
        return render_template('home.html')
    else:
        if "@" in search_query:
            if validate_email(search_query):
                res = Leak.query.filter_by(email=search_query).all()
                return render_template('home.html', search_query=search_query, result_list=res)
            elif search_query[0] == "@":
                res = Leak.query.filter(Leak.email.like("%" + search_query + "%")).all()
                return render_template('home.html', search_query=search_query, result_list=res)
        else:
            name_surname = search_query.split()
            if len(name_surname) == 2:
                name = name_surname[0]
                surname = name_surname[1]
                S = surname
                s = surname[0]
                N = name
                n = name[0]
                res = Leak.query.filter(Leak.email.like(S + "." + n + "%")).all()
                res += Leak.query.filter(Leak.email.like(n + "." + S + "%")).all()
                res += Leak.query.filter(Leak.email.like(s + "." + N + "%")).all()
                res += Leak.query.filter(Leak.email.like(N + "." + s + "%")).all()
                res += Leak.query.filter(Leak.email.like(S + "." + N + "%")).all()
                res += Leak.query.filter(Leak.email.like(N + "." + S + "%")).all()
                res += Leak.query.filter(Leak.email.like(S + n + "%")).all()
                res += Leak.query.filter(Leak.email.like(n + S + "%")).all()
                res += Leak.query.filter(Leak.email.like(s + N + "%")).all()
                res += Leak.query.filter(Leak.email.like(N + s + "%")).all()
                res += Leak.query.filter(Leak.email.like(S + N + "%")).all()
                res += Leak.query.filter(Leak.email.like(N + S + "%")).all()
                return render_template('home.html', search_query=search_query, result_list=res)
            elif len(name_surname) == 1:
                res = Leak.query.filter(Leak.email.like(search_query + "%")).all()
                return render_template('home.html', search_query=search_query, result_list=res)
            else:
                return render_template('home.html')

if __name__ == '__main__':
    app.run(debug=True, threaded=True)