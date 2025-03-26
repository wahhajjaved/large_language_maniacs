from flask import render_template, request
from sqlalchemy.exc import IntegrityError
import json
import requests

import config
from database import db, User, Profile
from main import app
from sender import Sender

@app.route("/")
def main_page():
  return render_template("index.html")

@app.route("/signup")
def signup():
  return render_template("signup.html")

@app.route("/team")
def team():
  return render_template("team.html")

@app.route("/profiles", defaults={'page': 1})
@app.route("/profiles/page/<int:page>")
def profiles(page):
  pagination = User.query.paginate(page)
  return render_template("profiles.html", pagination=pagination)

@app.route("/profile/<int:id>")
def public_profile(id):
  user = User.query.filter(User.id == id).first()
  # TODO: Change when we will have more profiles per user
  profile = user.profiles[0]

  linkedin = json.loads(profile.data_json)

  return render_template("profile.html", user=user, linkedin=linkedin)

@app.route("/create_account", methods=["POST"])
def create_account():
  linkedin_oauth_token = request.form["linkedin_oauth_token"]
  r = requests.get("https://api.linkedin.com/v1/people::(~):(id,first-name,last-name,headline,location,industry,num-connections,summary,specialties,positions,picture-url,public-profile-url,email-address,associations,interests,publications,patents,languages,skills,certifications,educations,courses,volunteer,num-recommenders,honors-awards)",
      headers={"oauth_token": linkedin_oauth_token,
        "x-li-format": "json"})

  user_json = r.json()["values"][0]

  user = User(email = user_json["emailAddress"],
      display_name = "%s %s" % (user_json["firstName"], user_json["lastName"]),
      headline = user_json["headline"],
      industry = user_json["industry"],
      location = user_json["location"]["name"],
      interested_in = "",
      photo_url = user_json["pictureUrl"]
      )

  profile = Profile(external_key = user_json["id"],
      data_json = json.dumps(user_json))

  user.profiles.append(profile)

  db.session.add(user)
  db.session.add(profile)

  try:
    db.session.commit()
  except IntegrityError, e:
    db.session.rollback()
    user = User.query.filter(User.email == user_json["emailAddress"]).first()
    # TODO: Change when we will have more profiles per user
    profile = user.profiles[0]

  linkedin = json.loads(profile.data_json)

  sender = Sender(user)
  sender.send_welcome_email()

  return render_template("profile.html", user = user, linkedin = linkedin)

# AJAX API
@app.route("/account/<int:user_id>/interested_in", methods=["POST"])
def save_interested_in(user_id):
  user = User.query.filter(User.id == user_id).first()
  user.interested_in = request.form["interested_in"]
  db.session.commit()
  return "OK"

# Email receiver api
@app.route("/notify/mail", methods=["POST"])
def mailgun_notification():
  # TODO: check if it is mailgun
  recipient = request.form["recipient"]
  sender = request.form["sender"]
  body = request.form["body-plain"]
  stripped = request.form["stripped-text"]

  address_hash = recipient.split("@")[0]
  user = User.query.filter(User.address_hash == address_hash).first()

  if not user:
    app.logger.warn("Unknown user [From=%s] from [To=%s]" % (sender, recipient))
    return "Unknown user"

  app.logger.info("Waiting for following emails from user '%s'" % (sender))
  for email in user.active_emails:
    app.logger.info(" - purpose %s" % (email.purpose))

  matched_emails = filter(lambda e: e.email_hash in body, user.active_emails)

  if len(matched_emails) == 0:
    app.logger.info("No matched emails for '%s'" % (sender))
    return "No matched emails"

  if len(matched_emails) > 1:
    app.logger.info("Multiple matched email found '%s'" % (sender))

  matched_email = matched_emails[0]

  if matched_email.purpose == "verify":
    if "JOIN OZAUR" in stripped:
      app.logger.info("Verified user '%s'" % (sender))
      user.active = True
      archive = matched_email.to_archive("Verified!")
      db.session.remove(matched_email)
      db.session.add(user)
      db.session.add(archive)
      db.session.commit()
    else:
      app.logger.warn("Reply verify email was invalid")
  else:
    app.logger.warn("Unknown purpose '%s'" % (matched_email.purpose))
    return "Unknown purpose"

  return "OK"

if __name__ == "__main__":
    app.run(debug=config.APP_DEBUG)

