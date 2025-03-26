from flask import render_template, request, redirect, url_for, session
from app import app, db
import os, hashlib

@app.before_request
def initSession():
	if session.get('CURR_USER') is None:
		session['CURR_USER'] = ''
	if session.get('LOGGED_IN') is None:
		session['LOGGED_IN'] = 'NO'

@app.route('/')
@app.route('/index')
def index():
	return render_template("index.html", logged_in=session['LOGGED_IN'], username=session['CURR_USER'])
	
@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		sql_str = "SELECT Username FROM UserTable WHERE Username='" + request.form['username'] + "';"
		req_user = db.engine.execute(sql_str).fetchall()
		hashed_pass = hashlib.sha256(request.form['password'] + "SALT").hexdigest()
		sql_str = "SELECT Password FROM UserTable WHERE Password='" + hashed_pass + "';"
		req_pass = db.engine.execute(sql_str).fetchall()
		valid = False
		if len(req_user) == 1 and len(req_pass) == 1:
			if str(req_user[0][0]) == request.form['username']:
				if str(req_pass[0][0]) == hashed_pass:
					valid = True
					
		if valid == True:
			session['CURR_USER'] = request.form['username']
			session['LOGGED_IN'] = 'YES'
			return redirect(url_for('success'))
		else:
			return render_template("login.html", error=True, logged_in=session['LOGGED_IN'])
				
	# return the user login page on a GET request
	return render_template("login.html", error=False, logged_in=session['LOGGED_IN'])
	
@app.route('/signup', methods=['GET', 'POST'])
def signup():
	error = False
	if request.method == 'POST':
		sql_str = "SELECT Email FROM UserTable WHERE Email='" + request.form['email'] + "';"
		req_email = db.engine.execute(sql_str).fetchall()
		if len(req_email) != 0:
			error = True
		hashed_pass = hashlib.sha256(request.form['password'] + "SALT").hexdigest()
		sql_str = "INSERT INTO UserTable(Username, Password, Email, Artist_Url) VALUES ('" + request.form['username'] + "', '" + \
		hashed_pass + "', '" + request.form['email'] + "', '" + request.form['username'] + "');"
		create_user = db.engine.execute(sql_str)
		session['CURR_USER'] = request.form['username']
		session['LOGGED_IN'] = 'YES'
		if error == False:
			return redirect(url_for('success'))
	return render_template("signup.html", error=error, logged_in=session['LOGGED_IN'], username=session['CURR_USER'])
	
@app.route('/success')
def success():
	return render_template("success.html", logged_in=session['LOGGED_IN'], username=session['CURR_USER'])
	
@app.route('/logout')
def logout():
	session['CURR_USER'] = ''
	session['LOGGED_IN'] = 'NO'
	return redirect(url_for('index'))
	
@app.route('/upload', methods=['GET', 'POST'])
def upload():
	if request.method == 'POST':
		sql_str = "INSERT INTO Song(Title, Created_at, Soundcloud_Views, Song_Url, Genre, Track_type, Duration, " + \
		"Soundcloud_Favorites) VALUES('" + request.form['title'] + "', 1234, 0, '" + request.form['song_url'] + \
		"', '" + request.form['genre'] + "', '" + request.form['track_type'] + "', 8, 0);"
		new_song = db.engine.execute(sql_str)
		return redirect(url_for('songs'))
	return render_template("upload.html", username=session['CURR_USER'], logged_in=session['LOGGED_IN'])
	
@app.route('/songs')
def songs():
	sql_str = "SELECT * FROM Song;"
	all_songs = db.engine.execute(sql_str).fetchall()
	return render_template("songs.html", username=session['CURR_USER'], logged_in=session['LOGGED_IN'], song_list=all_songs)
	
@app.route('/delete', methods=['GET', 'POST'])
def delete():
	if request.method == 'POST':
		sql_str = "SELECT Song_Url FROM Song WHERE Song_Url='" + request.form['song_url'] + "';"
		req_song = db.engine.execute(sql_str).fetchall()
		if len(req_song) == 0:
			error = True
			return render_template("delete.html", username=session['CURR_USER'], logged_in=session['LOGGED_IN'], error='True')
		
		sql_str = "DELETE FROM Song WHERE Song_Url='" + request.form['song_url'] + "';"
		del_song = db.engine.execute(sql_str)
		return render_template("delete.html", username=session['CURR_USER'], logged_in=session['LOGGED_IN'], error='False')
	return render_template("delete.html", username=session['CURR_USER'], logged_in=session['LOGGED_IN'])
	
@app.route('/edit/<song_url>', methods=['GET', 'POST'])
def song_edit(song_url):
	if request.method == 'POST':
		sql_str = "UPDATE Song SET Title='" + request.form['title'] + "', " + "Genre='" + request.form['genre'] + \
		"', Track_type='" + request.form['track_type'] + "' WHERE Song_Url='" + song_url + "';"
		updated_song = db.engine.execute(sql_str)
		return render_template("edit.html", error='False')
	elif request.method == 'GET':
		sql_str = "SELECT * FROM Song WHERE Song_Url='" + song_url + "';"
		req_song = db.engine.execute(sql_str).fetchall()
		song_title = req_song[0][0]
		genre = req_song[0][4]
		track_type = req_song[0][5]
		return render_template("edit.html", username=session['CURR_USER'], logged_in=session['LOGGED_IN'], song_title=song_title, song_url=song_url, genre=genre, track_type=track_type)