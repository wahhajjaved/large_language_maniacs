from flask import render_template, flash, redirect, request, session
from app import app
import requests
import json
import time
import os


CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']


def error_healing(error_code):
    if error_code == 1:
        return 'Произошла неизвестная ошибка'
    elif error_code == 2:
        return 'Сорян, админ все повыключал'
    elif error_code == 5:
        return 'Авторизация не удалась'
    elif error_code == 6:
        time.sleep(2)
        return None
    elif error_code == 9:
        return 'Слишком много однотипных действий'
    elif error_code == 14:
        return 'Прости, вылезла капча. Попробуй перезайти'
    elif error_code == 15:
        return 'Этот юзер спрятался от меня'
    elif error_code == 17:
        return 'Так исторически сложилось, что тебе придется войти'
    elif error_code == 18:
        return 'Эта страничка удалена, у нее нет друзей'
    elif error_code == 113:
        return 'Прости, но ты ввел что-то не так, как я ожидаю'
    elif error_code == 1000:
        return 'Нет, сначала положи что-нибудь в форму!'
    else:
        return 'Тебе повезло! Ты нашел новую ошибку!'


def form_url(CLIENT_ID, redirect_uri):
    params = {'client_id': CLIENT_ID,
              'display': 'page',
              'redirect_uri': redirect_uri,
              'scope': 'friends',
              'response_type': 'code',
              'v': '5.62',
              }
    request = requests.Request('GET', 'https://oauth.vk.com/authorize',
                               params=params)
    request.prepare()
    return request.prepare().url


def get_users_info(token, list_of_users_ids):
    params = {'user_ids': list_of_users_ids,
              'access_token': token,
              }
    url = 'https://api.vk.com/method/users.get'
    request = json.loads(requests.get(url, params).text)
    return request


def get_online_friends_ids(short_name, token):
    if not short_name:
        return {'error': {'error_code': 1000}}

    user_info = get_users_info(token, short_name)
    if 'error' in user_info:
        return user_info
    url = 'https://api.vk.com/method/friends.getOnline'
    params = {'user_id': user_info['response'][0]['uid'],
              'access_token': token,
              'order': 'hints',
              'count': 5000,  # vk won't return more
              'v': '5.62',
              'online_mobile': 1,
              }
    vk_friends_online = json.loads(requests.get(url, params).text)
    return vk_friends_online


def get_friends_info(token, list_of_friends_ids)
    friends_info = get_users_info(token, list_of_friends_ids)
    if 'error' in friends_info:
        friends_info = error_healing(friend_info['error']['error_code'])
    return friends_info


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():

    params = {'logged_in': False,
              'auth_url': form_url(CLIENT_ID, request.url_root + 'getpas'),
              'logout_url': '/logout'
              }
    short_name = request.args.get('text', '')
    if 'access_token' not in session:
        return render_template('index.html', **params)
    params['logged_in'] = True
    token = session['access_token']
    online_friends_ids = get_online_friends_ids(short_name, token)
    if 'error' in online_friends_ids:
        params['error'] = error_healing(online_friends_ids['error']['error_code'])
        return render_template('index.html', **params)
    online_friends_ids = online_friends_ids['response']
    pc_online_friends_info = get_friends_info(token, online_friends_ids['online'])
    telephone_online_friends_info =get_friends_info(token, online_friends_ids['online_mobile'])
    if 'error' in pc_online_friends_info:
        params['error'] = error_healing(pc_online_friends_info['error']['error_code'])
        return render_template('index.html', **params)
    if 'error in telephone_online_friends_info:
        params['error'] = error_healing(telephone_online_friends_info['error']['error_code'])
        return render_template('index.html', **params)
    params['online_friends_mobile'] = telephone_online_friends_info
    params['online_friends_pc'] = pc_online_friends_info
    params.pop('online_friends', None)
    return render_template('index.html', **params)


@app.route('/getpas', methods=['GET', 'POST'])
def getpas():

    code = request.args.get('code')
    if code is None:
        return redirect('/index')

    redirect_uri = request.url_root + 'getpas'
    vk_params = {'client_id': CLIENT_ID,
                 'client_secret': CLIENT_SECRET,
                 'redirect_uri': redirect_uri,
                 'code': code,
                 }
    response = requests.get('https://oauth.vk.com/access_token', params=vk_params)
    token = response.json().get('access_token', None)
    session['access_token'] = token
    return redirect('index')


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('access_token',None)
    return redirect('/index')
