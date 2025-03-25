from flask import Flask, jsonify, redirect, url_for
from client.db_client import db_client


exp = '''SELECT * FROM DUMMY'''
fecthing_vets = '''SELECT * FROM VETS'''
exp_insert = '''INSERT INTO DUMMY VALUES (%s)'''
vet_insert = '''INSERT INTO VETS (name,age) values (%s, %s)'''

app = Flask(__name__)


@app.route("/dummy/", methods=['GET'])
def show_dummy():
    rows = db_client.fetch(exp)
    return jsonify(rows)


@app.route("/vets/", methods=['GET'])
def show_vets():
    rows = list(db_client.fetch(fecthing_vets))
    return jsonify(**rows)


@app.route("/dummy_insert/", methods=['POST'])
def insert_dummy_post():
    db_client.insert(exp_insert, (33,))
    return redirect(url_for('show_dummy'))


@app.route("/vet_insert/", methods=['POST'])
def insert_vet_post():
    db_client.insert(vet_insert, ('Ahmet Davarci', 18))
    return redirect(url_for('show_vets'))


@app.route("/")
def home_page():
    return "Initializing........"


if __name__ == '__main__':
    app.run()
