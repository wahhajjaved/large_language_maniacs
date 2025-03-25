#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pandas as pd
from flask import Flask, request, jsonify, redirect, url_for
from sys import argv

from plot.bars import HotUsers

app = Flask(__name__)

@app.route("/")
def homepage():
    return "home"

@app.route('/hot_users', methods=["GET"])
def hot_users():
	sample = [{"index":2,"user":"Listener","hotness":59},{"index":1,"user":"Cicranis","hotness":43},{"index":0,"user":"Fulano da Silva","hotness":30},{"index":5,"user":"Hackeador","hotness":30},{"index":3,"user":"Lorem Ipsum","hotness":25},{"index":4,"user":"Bla bla","hotness":11}]
	return jsonify(sample)

@app.route('/hot_users_bar', methods=["GET"])
def hot_users_bar():
	sample = hot_users()
	sample_df = pd.DataFrame.from_dict(sample)
	return HotUsers().bar(sample, plot=False)





# @app.route('/wordcount', methods=["GET"])
# def wordcount2():
# 	text = text_cleaner(open(text_path, "r").read().lower())
# 	wordcount_map = Counter(text.split())
	
# 	word = request.args.get('word')
# 	pm.save_word(word)

# 	return jsonify({'word': word, 'count': wordcount_map[word]})

# @app.route('/word_entries', methods=['GET'])
# def word_entries():
# 	return jsonify(pm.word_entries())

# @app.route('/user_entries', methods=['GET'])
# def user_entries():
# 	return jsonify(pm.user_entries())

# @app.route('/form', methods = ['GET'])
# def form():
# 	return template.form()

# @app.route('/add_name', methods = ['POST'])
# def add_name():
# 	name = request.get_json()["name"]
# 	return success(name)

# def success(name):
# 	pm.save_user(name)
# 	return template.success_html(name)

if __name__ == '__main__':

	app.run(host="10.30.100.68", port=8080, debug=True)

