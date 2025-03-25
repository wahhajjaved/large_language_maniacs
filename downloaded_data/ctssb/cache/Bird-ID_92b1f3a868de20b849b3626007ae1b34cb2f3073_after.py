import os
import re

import authlib
from authlib.integrations.flask_client import OAuth
from flask import (Blueprint, abort, make_response, redirect, request, session,
                   url_for)
from sentry_sdk import capture_exception

from web.config import (FRONTEND_URL, app, database, get_session_id, logger,
                        update_web_user, verify_session)

bp = Blueprint('user', __name__, url_prefix='/user')
oauth = OAuth(app)

relative_url_regex = re.compile(r"/(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))*")

DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
oauth.register(
    name='discord',
    client_id=601917808137338900,
    client_secret=DISCORD_CLIENT_SECRET,
    access_token_url='https://discordapp.com/api/oauth2/token',
    access_token_params=None,
    authorize_url='https://discordapp.com/api/oauth2/authorize',
    authorize_params=None,
    api_base_url='https://discordapp.com/api/',
    client_kwargs={
        'scope': 'identify',
        'prompt': 'consent'
    },
)
discord = oauth.discord

@bp.after_request  # enable CORS
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = FRONTEND_URL
    header['Access-Control-Allow-Credentials'] = 'true'
    return response

@bp.route('/login', methods=["GET"])
def login():
    logger.info("endpoint: login")
    redirect_uri = url_for('user.authorize', _external=True, _scheme='https')
    resp = make_response(oauth.discord.authorize_redirect(redirect_uri))
    redirect_after = request.args.get("redirect", FRONTEND_URL, str)
    if relative_url_regex.fullmatch(redirect_after) is not None:
        resp.headers.add('Set-Cookie', 'redirect=' + redirect_after + '; Max-Age=180; SameSite=None; HttpOnly; Secure')
    else:
        resp.headers.add('Set-Cookie', 'redirect=/; Max-Age=180; SameSite=None; HttpOnly; Secure')
    return resp

@bp.route('/logout', methods=["GET"])
def logout():
    logger.info("endpoint: logout")
    redirect_after = request.args.get("redirect", FRONTEND_URL, str)
    if relative_url_regex.fullmatch(redirect_after) is not None:
        redirect_url = redirect_after
    else:
        redirect_url = FRONTEND_URL

    session_id = get_session_id()
    user_id = verify_session(session_id)
    if isinstance(user_id, int):
        logger.info("deleting user data, session data")
        database.delete(f"web.user:{user_id}", f"web.session:{session_id}")
        session.clear()
    else:
        logger.info("deleting session data")
        database.delete(f"web.session:{session_id}")
        session.clear()
    return redirect(redirect_url)

@bp.route('/authorize')
def authorize():
    logger.info("endpoint: authorize")
    redirect_uri = url_for('user.authorize', _external=True, _scheme='https')
    oauth.discord.authorize_access_token(redirect_uri=redirect_uri)
    resp = oauth.discord.get('users/@me')
    profile = resp.json()
    # do something with the token and profile
    update_web_user(profile)
    redirect_cookie = str(request.cookies.get("redirect"))
    if relative_url_regex.fullmatch(redirect_cookie) is not None:
        redirection = FRONTEND_URL + redirect_cookie
    else:
        redirection = FRONTEND_URL + "/"
    session.pop("redirect", None)
    return redirect(redirection)

@bp.route('/profile')
def profile():
    logger.info("endpoint: profile")

    session_id = get_session_id()
    user_id = int(database.hget(f"web.session:{session_id}", "user_id"))

    if user_id != 0:
        avatar_hash, avatar_url, username, discriminator = (
            stat.decode("utf-8")
            for stat in database.hmget(f"web.user:{user_id}", "avatar_hash", "avatar_url", "username", "discriminator")
        )
        placings = int(database.zscore("users:global", str(user_id)))
        max_streak = int(database.zscore('streak.max:global', str(user_id)))
        missed_birds = [
            [stats[0].decode("utf-8"), int(stats[1])]
            for stats in database.zrevrangebyscore(f"incorrect.user:{user_id}", "+inf", "-inf", 0, 10, True)
        ]
        return {
            "avatar_hash": avatar_hash,
            "avatar_url": avatar_url,
            "username": username,
            "discriminator": discriminator,
            "rank": placings,
            "max_streak": max_streak,
            "missed": missed_birds
        }
    else:
        logger.info("not logged in")
        abort(403, "Sign in to continue")

@app.errorhandler(authlib.common.errors.AuthlibBaseError)
def handle_authlib_error(e):
    logger.info(f"error with oauth login: {e}")
    capture_exception(e)
    return 'An error occurred with the login', 500
