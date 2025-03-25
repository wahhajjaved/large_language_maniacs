#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File: pyneo4jet.py
Author: huxuan - i(at)huxuan.org
Created: 2012-11-25
Last modified: 2012-12-04
Description:
    Main interface for pyneo4jet

Copyrgiht (c) 2012 by huxuan. All rights reserved.
License GPLv3
"""

import os
import sys
import datetime

import gevent.monkey
gevent.monkey.patch_all()
from bottle import run, get, post, request, response
from bottle import template, redirect, static_file

try:
    from config import VERSION, INVITATION_CODE, COOKIES_SECRET
except ImportError:
    print '[Error] config.py is NEEDED! Refer to config-sample.py'
    sys.exit(1)

from model import User, Tweet
from database import GRAPHDB as db

@get('/')
def index_get():
    """
    Show signin or signup form according to 'action' param
    If already signed in, redirect to timeline page

    :rtype: login or signup page or redirect to timeline page
    """
    action = request.GET.get('action', '')
    if action == 'signup':
        return template('signup')
    elif action == 'signout':
        response.delete_cookie('username')
    else:
        username = request.get_cookie('username', secret=COOKIES_SECRET)
        if username:
            redirect('/%s/timeline/' % username)
    return template('signin')

@post('/')
def index_post():
    """
    Check validation for SignIn or SignUp

    :rtype: login page with form
    """
    action = request.GET.get('action', 'signin')
    username = request.forms.get('username')
    password = request.forms.get('password')
    if action == 'signup':
        password_confirm = request.forms.get('password_confirm')
        invitation = request.forms.get('invitation')
        res, msg = User.add(username, password, password_confirm, invitation)
    else:
        res, msg = User.auth(username, password)
    if res:
        response.set_cookie('username', username, secret=COOKIES_SECRET)
        redirect('/%s/timeline/' % username)
    else:
        return template(action, username=username, msg=msg)

@get('/<username>/')
def profile_get(username):
    """
    Show user's profile with at most recent 10 tweets

    :param username: username of the user
    :type username: string
    :rtype: profile page of the user

    Note:
        Need to check whether authenticated or not
        if so add an profile edit button
        if not follow button or followed status

        Use 'action' param to judge whether to update profile or password
        if it is 'profile', show profile update form
        if it is 'password', show password update form
    """
    user = User.get(username)
    ownername = request.get_cookie('username', secret=COOKIES_SECRET)
    owner = User.get(ownername)
    action = request.GET.get('action', '')
    if owner == username:
        if action == 'profile':
            return template('profile_update', user=user)
        elif action == 'password':
            return template('password_update', user=user)
    tweets = user.get_tweets()
    isfollow = owner.isfollow(username)
    return template('profile', user=user, owner=owner, tweets=tweets,
        isfollow=isfollow)

@post('/<username>/')
def profile_post(username):
    """
    Update user's profile or password

    :param username: username of the user
    :type username: string
    :rtype: profile page of the user

    Note:
        Use 'action' param to judge whether to update profile or password
    """
    user = User.get(username)
    ownername = request.get_cookie('username', secret=COOKIES_SECRET)
    owner = User.get(ownername)
    action = request.GET.get('action', '')
    if ownername == username:
        if action == 'profile':
            avatar = request.files.avatar
            username_new = request.forms.username or username
            avatar_new = user.avatar
            if avatar and avatar.file:
                avatar_new = 'images/avatar_%s%s' % (username,
                    os.path.splitext(avatar.filename)[-1], )
                avatar_file = file(avatar_new, 'w')
                print >>avatar_file, avatar.file.read()
                avatar_file.close()
            res, msg = user.update(username_new, avatar_new)
            return template('profile_update', user=user, msg=msg)
        elif action == 'password':
            old_pw = request.forms.get('old_pw')
            new_pw1 = request.forms.get('new_pw1')
            new_pw2 = request.forms.get('new_pw2')
            res, msg = user.update_password(old_pw, new_pw1, new_pw2)
            return template('password_update', user=user, msg=msg)
        elif action == 'tweet':
            param = {
                'username': username,
                'text': request.forms.text,
                'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            res, msg = Tweet.add(**param)
            return template('tweet_update', user=user, tweet_msg=msg)
        elif action == 'follow':
            owner.follow(username)
        elif action == 'unfollow':
            owner.unfollow(username)
    redirect('/%s/' % username)

@get('/<username>/timeline/')
@get('/<username>/timeline/<index:int>')
def timeline(username, index=0):
    """
    Show user's timeline

    :param username: username of the user
    :type username: string
    :param index: the begin index of timeline list, default to 0
    :type index: int
    :rtype: timeline page shown
    """
    user = User.get(username)
    tweets = user.get_timeline(index) or {}
    return template('tweets',
        title='Timeline',
        username=username,
        tweets=tweets,
    )

@get('/<username>/tweets/')
@get('/<username>/tweets/<index:int>')
def tweets(username, index=0):
    """
    Show user's tweets

    :param username: username of the user
    :type username: string
    :param index: the begin index of tweets list, default to 0
    :type index: int
    :rtype: tweets page shown
    """
    user = User.get(username)
    tweets = user.get_tweets(index)
    return template('tweets',
        title='%s\'s Tweets' % username,
        username=username,
        tweets=tweets,
    )

@get('/<username>/followers/')
@get('/<username>/followers/<index:int>')
def followers(username, index=0):
    """
    Show user's followers

    :param username: username of the user
    :type username: string
    :param index: the begin index of followers list, default to 0
    :type index: int
    :rtype: followers list page
    """
    user = User.get(username)
    users = user.get_followers(index) or {}
    return template('users',
        title='%s\'s followers' % username,
        username=username,
        users=users,
    )

@get('/<username>/following/')
@get('/<username>/following/<index:int>')
def following(username, index=0):
    """
    Show user's following

    :param username: username of the user
    :type username: string
    :param index: the begin index of following list, default to 0
    :type index: int
    :rtype: following list page
    """
    user = User.get(username)
    users = user.get_following(index)
    return template('users',
        title='%s\'s following' % username,
        username=username,
        users=users,
    )

@get('/images/<filename:path>')
def images(filename):
    """
    Retrun static images
    """
    return static_file(filename, root='images/')

@get('/favicon.ico')
def images():
    """
    Retrun favicon images
    """
    return static_file('favicon.ico', root='images/')

def main():
    """Parse the args and run the server"""
    if len(sys.argv) == 2 and sys.argv[1].isdigit():
        port = sys.argv[1]
    else:
        port = 8888
    try:
        run(server='gevent', host='0.0.0.0', port=port,
            debug=(VERSION != 'production'))
    except:
        pass
    finally:
        print '[MSG] Please wait neo4j to shutdown!'
        db.shutdown()

if __name__ == '__main__':
    main()
