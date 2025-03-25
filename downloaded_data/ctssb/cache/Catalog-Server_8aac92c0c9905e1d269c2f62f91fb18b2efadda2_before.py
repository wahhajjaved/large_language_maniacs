#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, jsonify, \
    url_for, make_response, g
from flask import session as login_session
from flask_httpauth import HTTPBasicAuth
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import psycopg2
import httplib2
import json
import requests
import random
import string

# Global vars and constants
app = Flask(__name__)
app.secret_key = ''.join(
    random.choice(string.ascii_uppercase + string.digits)
    for x in range(32))
auth = HTTPBasicAuth()
CLIENT_ID = json.loads(
    open('/home/catalog/Catalog-Server/client_secrets.json', 'r').read()
)['web']['client_id']


# page renders
@app.route('/oauth/<provider>', methods=['POST'])
def login(provider):
    # Validate state token
    if request.args.get('state') != login_session.get('state'):
        response = make_response(json.dumps('Invalid state parameter'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    auth_code = request.data
    if provider == 'google':
        return googleLogin(auth_code)
    else:
        response = make_response(
            json.dumps('Unrecognized Provider'), 401
        )
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/oauth/logout')
def logout():
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected'), 401
        )
        response.headers['Content-Type'] = 'application/json'
        return response
    if login_session.get('provider') == 'google':
        return googleLogout(access_token)
    else:
        response = make_response(
            json.dumps('Unrecognized Provider'), 401
        )
        response.headers['Content-Type'] = 'application/json'
        return response


def googleLogin(auth_code):
    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets(
            './client_secrets.json',
            scope=''
        )
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(auth_code)
    except FlowExchangeError:
        response = make_response(json.dumps(
            'Failed to upgrade the authorization code'),
            401
        )
        response.headers['Content-Type'] = 'application/json'
        return response
    # Check that the access token is valid
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Verify that the access token is used for the intended user
    g_id = credentials.id_token['sub']
    if result['user_id'] != g_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match user ID"),
            401
        )
        response.headers['Content-Type'] = 'application/json'
        return response
    # Verify that the access token is valid for this app
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app client ID"),
            401
        )
        response.headers['Content-Type'] = 'application/json'
        return response
    # See if user is already connected
    stored_access_token = login_session.get('access_token')
    stored_g_id = login_session.get('g_id')
    if stored_access_token is not None and g_id == stored_g_id:
        response = make_response(
            json.dumps('Current user is already connected'),
            200
        )
        response.headers['Content-Type'] = 'application/json'
        return response
    # Store the access token in session
    login_session['access_token'] = credentials.access_token
    login_session['g_id'] = g_id
    # Get user info and store in session
    url = 'https://www.googleapis.com/oauth2/v1/userinfo'
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    result = requests.get(url, params=params)
    data = result.json()
    login_session['username'] = data['name']
    login_session['email'] = data['email']
    login_session['provider'] = 'google'
    # see if user exists, if it doesn't make a new one
    user_id = getUserID(data['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    return login_session['username']


def googleLogout(access_token):
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['g_id']
        del login_session['provider']
        del login_session['user_id']
        del login_session['username']
        del login_session['email']
        return redirect(url_for('showHome'))
    else:
        response = make_response(
            json.dumps('Failed to revoke token for given user'),
            400
        )
        response.headers['Content-Type'] = 'applicatin/json'
        return response


def createUser(login_session):
    SQL = 'INSERT INTO users (name, email) VALUES (%s, %s)'
    execute(SQL, (login_session['username'], login_session['email']))
    return getUserID(login_session['email'])


def getUserID(email):
    try:
        SQL = 'SELECT users.id FROM users WHERE users.email = %s'
        user = query(SQL, (email,))
        return user[0][0]
    except:
        return None

def getCategories():
    try:
        SQL = 'SELECT * FROM categories;'
        categories = query(SQL)
        return categories
    except:
        return []
        
def getLatestItems():
    try:
        SQL = 'SELECT * FROM categoryitems ORDER BY categoryitems.id DESC LIMIT 10;'
        items = query(SQL)
        return items
    except:
        return []

def createCategory(name):
    SQL = 'INSERT INTO categories (name) VALUES (%s)'
    execute(SQL, (name,))
    
def getCategory(id):
    try:
        SQL = 'SELECT * FROM categories WHERE categories.id = %s'
        category = query(SQL, (id,))
        return category[0]
    except:
        return []

def getItems(category_id):
    try:
        SQL = 'SELECT * FROM categoryitems WHERE categoryitems.category_id = %s'
        items = query(SQL, (category_id,))
        return items
    except:
        return []

def addItem(name, description, category_id, user_id):
    SQL = 'INSERT INTO categoryitems (name, description, category_id, user_id) VALUES (%s, %s, %s, %s)'
    execute(SQL, (name, description, category_id, user_id))
    return getItem(name, description, category_id, user_id)

def updateItem(item):
    SQL = 'UPDATE categoryitems SET name = %s, description = %s, category_id = %s WHERE id = %s'
    execute(SQL, (item[1], item[2], item[3], item[0]))
    return getItemById(item[0])
    
def getItem(name, description, category_id, user_id):
    try:
        SQL = 'SELECT * FROM categoryitems WHERE categoryitems.name = %s AND categoryitems.description = %s AND categoryitems.category_id = %s AND categoryitems.user_id = %s'
        item = query(SQL, (name, description, category_id, user_id))
        return item[0]
    except:
        return []
        
def getItemById(id):
    try:
        SQL = 'SELECT * FROM categoryitems WHERE categoryitems.id = %s'
        item = query(SQL, (id,))
        return item[0]
    except:
        return []
        
def removeItemFromDb(id):
    SQL = 'DELETE FROM categoryitems WHERE id = %s'
    execute(SQL, (id,))


@app.route('/catalog/')
@app.route('/')
def showHome():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in range(32))
    login_session['state'] = state
    categories = getCategories()
    latestItems = getLatestItems()
    return render_template(
        'catalog.html',
        categories=categories,
        latestItems=latestItems,
        STATE=state
    )


@app.route('/category/new', methods=['GET', 'POST'])
def newCategory():
    if 'username' not in login_session:
        return redirect(url_for('showHome'))
    if request.method == 'POST':
        createCategory(request.form['name'])
        return redirect(url_for('showHome'))
    else:
        return render_template('newCategory.html')


@app.route('/category/<int:category_id>/')
@app.route('/category/<int:category_id>/items')
def showCategoryItems(category_id):
    allCategories = getCategories()
    selectedCategory = getCategory(category_id)
    items = getItems(category_id)
    return render_template(
        'categoryItems.html',
        allCategories=allCategories,
        selectedCategory=selectedCategory,
        items=items
    )


@app.route('/category/items/new/<init_category_id>', methods=['GET', 'POST'])
def newItem(init_category_id):
    if 'username' not in login_session:
        return redirect(url_for('showHome'))
    if request.method == 'POST':
        item = addItem(
            request.form['name'],
            request.form['description'],
            request.form['category_id'],
            login_session['user_id']
        )
        return redirect(url_for(
            'showItem',
            item_id=item[0],
            category_id=item[3]
        ))
    else:
        categories = getCategories()
        if init_category_id == 'NONE' and len(categories) > 0:
            init_category_id = categories[0].id
        return render_template(
            'newItem.html',
            categories=categories,
            init_category_id=init_category_id
        )


@app.route('/category/<int:category_id>/items/<int:item_id>')
def showItem(item_id, category_id):
    item = getItemById(item_id)
    allCategories = getCategories()
    allowEdit = item[4] == login_session.get('user_id')
    return render_template(
        'itemDetails.html',
        item=item,
        allCategories=allCategories,
        allowEdit=allowEdit
    )


@app.route(
    '/category/<int:category_id>/items/<int:item_id>/edit',
    methods=['GET', 'POST']
)
def editItem(item_id, category_id):
    item = getItemById(item_id)
    if item[4] != login_session.get('user_id'):
        return redirect(url_for('showHome'))
    if request.method == 'POST':
        item = list(item)
        if request.form['name']:
            item[1] = request.form['name']
        if request.form['description']:
            item[2] = request.form['description']
        if request.form['category_id']:
            item[3] = request.form['category_id']
        item = updateItem(tuple(item))
        return redirect(url_for(
            'showItem',
            item_id=item[0],
            category_id=item[3]
        ))
    else:
        allCategories = getCategories()
        return render_template(
            'editItem.html',
            item=item,
            allCategories=allCategories
        )


@app.route(
    '/category/<int:category_id>/items/<int:item_id>/delete',
    methods=['GET', 'POST'])
def deleteItem(item_id, category_id):
    item = getItemById(item_id)
    if item[4] != login_session.get('user_id'):
        return redirect(url_for('showHome'))
    if request.method == 'POST':
        itemId = item[3]
        removeItemFromDb(item_id)
        return redirect(url_for(
            'showCategoryItems',
            category_id=itemId
        ))
    else:
        return render_template(
            'deleteItem.html',
            item=item,
        )

def execute(SQL, params):
    conn = None
    try:
        conn = psycopg2.connect(database='catalog', user='catalog', password='catalog')
        cur = conn.cursor()
        cur.execute(SQL, params)
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

def query(SQL, params=None):
    try:
        conn = psycopg2.connect(database='catalog', user='catalog', password='catalog')
        cur = conn.cursor()
        if params is not None:
            cur.execute(SQL, params)
        else:
            cur.execute(SQL)
        results = cur.fetchall()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()
    return results


if __name__ == '__main__':
    app.debug = True
    app.run()
