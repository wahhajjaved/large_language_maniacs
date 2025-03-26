from flask import render_template, request, flash, redirect, url_for, make_response, session, g
from wwag import app, database, forms
from wwag.decorators import player_login_required
from MySQLdb import IntegrityError

@app.route("/games")
def games():
  games = database.execute("SELECT * FROM Game ORDER BY StarRating DESC;").fetchall()
  return render_template('games/index.html',games=games)

@app.route("/games/create", methods=['GET', 'POST'])
@player_login_required
def games_create():
  form = forms.GameForm(request.form)
  if request.method == "POST" and form.validate():
    lastrowid = database.execute("INSERT INTO Game (GameName, Genre, Review, StarRating, ClassificationRating, PlatformNotes, PromotionLink, Cost) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);", (form.game_name.data, form.genre.data, form.review.data, form.star_rating.data, form.classification_rating.data,  ' '.join(form.platform_notes.data), form.promotion_link.data, form.cost.data)).lastrowid
    database.commit()
    flash("You have created a new game successfully!", 'notice')
    return redirect(url_for('games'))
  else:
    return render_template('games/new.html', form=form)

@app.route("/games/<game_id>/update", methods=['GET', 'POST'])
@player_login_required
def games_update(game_id):
  game = database.execute("SELECT * FROM Game WHERE GameID = %s", (game_id,)).fetchone()
  form = forms.GameForm(request.form, game_name=game['GameName'], genre=game['Genre'], review=game['Review'], star_rating=game['StarRating'], classification_rating=game['ClassificationRating'], platform_notes=game['PlatformNotes'].split(" "), cost=game['Cost'], promotion_link=game['PromotionLink'])
  if request.method == "POST" and form.validate():
    database.execute("UPDATE Game SET GameName = %s, Genre = %s, Review = %s,  StarRating = %s, ClassificationRating = %s, PlatformNotes = %s, Cost = %s, PromotionLink = %s WHERE GameID = %s;", (form.game_name.data, form.genre.data, form.review.data, form.star_rating.data, form.classification_rating.data, ' '.join(form.platform_notes.data), form.cost.data, form.promotion_link.data, game['GameID']))
    database.commit()
    flash("You have updated the video successfully!", 'notice')
    return redirect(url_for('games_show', game_id=game_id))
  else:
    return render_template('games/edit.html', form=form, game=game)

@app.route("/games/<game_id>")
def games_show(game_id):
  game = database.execute("SELECT * FROM Game WHERE GameID = %s", (game_id,)).fetchone()
  return render_template('games/show.html', game=game)

@app.route("/games/<game_id>/delete", methods=['POST'])
@player_login_required
def games_delete(game_id):
  try:
    database.execute("DELETE FROM Game WHERE GameID = %s", (game_id,))
    database.commit()
  except IntegrityError as e:
    flash("You cannot delete this game because some videos or instance Run may depend on it!", 'error')
    return redirect(url_for('games_show', game_id=game_id))
  flash("You have deleted the game.", 'notice')
  return redirect(url_for('games'))
