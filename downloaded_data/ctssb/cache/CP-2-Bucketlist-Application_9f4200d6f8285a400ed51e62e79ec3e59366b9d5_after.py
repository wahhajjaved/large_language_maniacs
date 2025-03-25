from datetime import datetime, timedelta
import re

from flask import jsonify, request, abort, url_for
import jwt

from app import app
from app import databases
from app.v1.models import Users, BucketList, Items

databases.create_all()


@app.route('/bucketlist/api/v1/auth/register', methods=['POST'])
def register():
    '''
    This endpoint uses the post request method to add users in your database.
    It acceps data in json format with username and password as keys.
    '''
    request.get_json(force=True)
    try:

        uname = request.json['username']
        passwd = request.json['password']
        if not uname:
            response = jsonify({'error': 'Username cannot be blank'})
            return response
        elif not re.match("^[a-zA-Z0-9_]*$", uname):
            response = jsonify({'error':
                                'Username cannot contain special characters'})
            response.status_code = 400
            return response
        elif len(passwd) < 5:
            response = jsonify({'error':
                                'Password should be more than 5 characters'})
            response.status_code = 400
            return response
        else:
            res = Users.query.all()
            uname_check = [r.username for r in res]
            if uname in uname_check:
                response = jsonify({'error':
                                    'This username is already in use'})
                return response
            else:
                userInfo = Users(username=uname)
                userInfo.hash_password(passwd)
                userInfo.save()
                response = jsonify(
                    {'Registration status':
                     'Successfully registered ' + userInfo.username})
                response.status_code = 201
                return response
    except KeyError:
        response = jsonify({
            'error': 'Please use username and password for dict keys.'
        })
        response.status_code = 500
        return response


@app.route('/bucketlist/api/v1/auth/login', methods=['POST'])
def login():
    '''
    Accepts user crendtials and generates a jwt token for each user.
    The token expires after an hour. This can be adjusted by setting
    the 'exp'private Claim to whatever timeout you prefer.
    '''
    request.get_json(force=True)
    try:
        user_name = request.json['username']
        passwd = request.json['password']
        res = Users.query.filter_by(username=user_name)
        user_name_check = [user.username for user in res
                           if user.verify_password(passwd) is True]
        user_id = [user.id for user in res if user_name in user_name_check]
        if not user_name:
            response = jsonify({'error': 'Username field cannot be blank'})
            response.status_code = 400
            return response
        elif not passwd:
            response = jsonify({'error': 'Password field cannot be blank'})
            response.status_code = 400
            return response

        elif not re.match("^[a-zA-Z0-9_]*$", user_name):
            response = jsonify({'error':
                                'Username cannot contain special characters'})
            response.status_code = 400
            return response
        elif user_name in user_name_check:
            payload = {
                "user_id": user_id,
                "exp": datetime.utcnow() + timedelta(minutes=60)}
            token = jwt.encode(payload,
                               app.config['SECRET_KEY'], algorithm='HS256')

            response = jsonify(
                {'Login status': 'Successfully Logged in ',
                 'Token': token.decode('utf-8')})
            response.status_code = 200
            return response
        else:
            response = jsonify(
                {'Login status': 'Invalid credentials'})
            response.status_code = 401
            return response
    except KeyError:
        response = jsonify({
            'error': 'Please use username and password for dict keys.'
        })
        response.status_code = 500
        return response


@app.route('/bucketlist/api/v1/bucketlist', methods=['POST'])
def create_bucketlist():
    '''
    This endpoint creates a new bucketlist for the user.
    '''
    request.get_json(force=True)
    try:
        payload = verify_token(request)
        if isinstance(payload, dict):
            user_id = payload['user_id']
        else:
            return payload
        bucketlist_name = request.json['name']
        if not bucketlist_name:
            response = jsonify({'error':
                                'Your Bucketlist needs a title to proceed.'})
            response.status_code = 403
            return response
        else:
            bucket = BucketList(name=bucketlist_name, created_by=user_id[0])
            bucket.save()
            response = jsonify(
                {'Status': 'Success'})
            response.status_code = 201
            return response
    except KeyError:
        response = jsonify({
            'error': 'Please use name for dict key.'
        })
        response.status_code = 500
        return response


@app.route('/bucketlist/api/v1/bucketlist',
           methods=['GET'])
def get_bucketlist():
    '''
    This endpoint queries userspecific data and outputs it in json.
    '''
    msg = 'Ooops! No bucketlists here'
    endpoint = '/bucketlist/api/v1/bucketlist'
    payload = verify_token(request)
    if isinstance(payload, dict):
        user_id = payload['user_id']
    else:
        return payload
    limit = int(request.args.get("limit", 20))
    page = int(request.args.get("page", 1))
    if limit > 100 or page < 1:
        page = 1
        limit = 100
    else:
        limit = 20
    resp = BucketList.query.filter_by(created_by=user_id[0]).paginate(page,
                                                                      limit,
                                                                      False)
    if not resp:
        response = jsonify({'error':
                            'Ooops! You have not created any bucketlist yet!'})
        response.status_code = 404
        return response
    else:
        search = request.args.get("q", "")
        if search:
            resp = BucketList.query.filter(BucketList.name.contains(
                search), BucketList.created_by ==
                user_id[0]).paginate(page, limit, False)

            res = resp.items
            pages = resp.pages

            if resp.has_next or resp.has_prev:
                # Generate next and previous endpoint urls
                url_next = (url_for(request.endpoint) + "?page=" +
                            (str(page + 1) + "&limit" + (str(limit))))
                url_prev = (url_for(request.endpoint) + "?page=" +
                            (str(page - 1) + "&limit" + (str(limit))))
            else:
                url_next = None
                url_prev = None

            if len(res) < 1:
                msg = "Ooops! This particular item doesn't exist"
                response = jsonify({'error': msg})
                response.status_code = 404
                return response
            else:
                bucketlist_data = []
                for data in res:
                    final = {
                        'id': data.__dict__['id'],
                        'name': data.__dict__['name'],
                        'date-created': data.__dict__['date_created'],
                        'date_modified': data.__dict__['date_modified'],
                        'created_by': data.__dict__['created_by'],
                    }
                    bucketlist_data.append(final)
                response = jsonify(
                    {"Info": {"url_next": url_next, "url_prev": url_prev,
                              "Total pages": pages}}, bucketlist_data)
                response.status_code = 200
                return response
        else:
            pages = resp.pages
            if resp.has_next or resp.has_prev:
                url_next = (url_for(request.endpoint) + "?page=" +
                            (str(page + 1) + "&limit" + (str(limit))))
                url_prev = (url_for(request.endpoint) + "?page=" +
                            (str(page - 1) + "&limit" + (str(limit))))
            else:
                url_next = None
                url_prev = None

            res = [bucket for bucket in resp.items]
            bucketlist_data = []

            if not res:
                response = jsonify({'error': msg})
                response.status_code = 404
                return response
            else:
                for data in res:
                    final = {
                        'id': data.__dict__['id'],
                        'name': data.__dict__['name'],
                        'date-created': data.__dict__['date_created'],
                        'date_modified': data.__dict__['date_modified'],
                        'created_by': data.__dict__['created_by'],
                    }
                    bucketlist_data.append(final)
                response = jsonify(
                    {"Info": {"url_next": url_next, "url_prev": url_prev,
                              "Total pages": pages}}, bucketlist_data)
                response.status_code = 200
                return response


@app.route('/bucketlist/api/v1/bucketlist/<int:bucket_id>',
           methods=['GET', 'PUT', 'DELETE'])
def bucketlist_by_id(bucket_id):
    '''
    This endpoint accepts three request methods. When putting it updates
    bucketlist data. The get method gets the bucketlist as per the specified id
    in the endpoint url.
    '''
    payload = verify_token(request)
    if isinstance(payload, dict):
        user_id = payload['user_id']
    else:
        return payload
    res = BucketList.query.all()
    bucket_data = [bucket for bucket in res if bucket.id ==
                   bucket_id and bucket.created_by in user_id]
    if request.method == 'GET':
        data = {}
        for data in bucket_data:
            final_data = []
            for item_data in data.items:
                item_data = {
                    'id': item_data.id,
                    'name': item_data.name,
                    'date-created': item_data.datecreated,
                    'date_modified': item_data.date_modified,
                }
                final_data.append(item_data)
            data = {
                'id': data.id,
                'name': data.name,
                'date-created': data.date_created,
                'date_modified': data.date_modified,
                'items': final_data
            }
        if bucket_id not in data.values():
            response = jsonify({'warning':
                                'Ooops! Sorry this bucketlist does not exist.'
                                })
            response.status_code = 404
            return response
        else:
            response = jsonify(data)
            response.status_code = 200
            return response
    elif request.method == 'DELETE':
        data = {}
        for data in bucket_data:
            data = {
                'id': data.id,
                'name': data.name,
                'date-created': data.date_created,
                'date_modified': data.date_modified
            }
        if bucket_id not in data.values():
            response = jsonify({'warning':
                                'Ooops! Sorry this bucketlist does not exist.'
                                })
            response.status_code = 404
            return response
        else:
            del_data = BucketList.query.filter_by(id=bucket_id).first()
            databases.session.delete(del_data)
            databases.session.commit()
            response = jsonify({'Status': 'Bucketlist successfully deleted.'})
            response.status_code = 200
            return response
    elif request.method == 'PUT':
        request.get_json(force=True)
        data = BucketList.query.filter(BucketList.created_by == user_id[0],
                                       BucketList.id == bucket_id).first()
        if not data:
            response = jsonify({'warning':
                                'Ooops! Sorry this bucketlist does not exist.'
                                })
            response.status_code = 404
            return response
        else:
            try:
                name = request.json['name']
                data.name = name
                databases.session.commit()
                data = {}
                for data in bucket_data:
                    data = {
                        'id': data.id,
                        'name': data.name,
                        'date-created': data.date_created,
                        'date_modified': data.date_modified

                    }
                response = jsonify(data)
                response.status_code = 201
                return response
            except KeyError:
                response = jsonify({
                    'error': 'Please use name for dict keys.'
                })
                response.status_code = 500
                return response


@app.route('/bucketlist/api/v1/bucketlist/<int:bucket_id>/items',
           methods=['POST'])
def add_items(bucket_id):
    '''
    Adds items to a users's bucketlist.
    '''
    payload = verify_token(request)
    if isinstance(payload, dict):
        user_id = payload['user_id']
    else:
        return payload
    resp = BucketList.query.all()
    res = [data for data in resp if data.created_by in user_id and data.id ==
           bucket_id]
    if not res:
        response = jsonify({'Warning':
                            'Ooops! The bucketlist_id does not exist.'})
        response.status_code = 404
        return response
    else:
        try:
            item_data = Items.query.all()
            request.get_json(force=True)
            item_name = request.json['name']
            item_check = [item.name for item in item_data
                          if item.name == item_name]
            if item_check:
                response = jsonify({
                    'Warning':
                    'Ooops! Sorry, this particular item already exists.'
                })
                return response
            else:
                item_add = Items(name=item_name, id=bucket_id)
                item_add.save()
                response = jsonify({
                    'Status': 'Success'
                })
                response.status_code = 200
                return response
        except KeyError:
            response = jsonify({
                'error': 'Please use name for dict keys.'
            })
            response.status_code = 500
            return response


@app.route('/bucketlist/api/v1/bucketlist/<int:bucket_id>/items/<int:item_id>',
           methods=['PUT'])
def edit_items(bucket_id, item_id):
    '''
    Edits a user's items according to the specified bucketlist.
    '''
    request.get_json(force=True)
    payload = verify_token(request)
    if isinstance(payload, dict):
        user_id = payload['user_id']
    else:
        return payload
    resp = BucketList.query.all()
    res = [data for data in resp if data.created_by in user_id and
           data.id == bucket_id]
    items_response = Items.query.filter(BucketList.created_by ==
                                        user_id[0], Items.id ==
                                        item_id).first()
    if not res:
        response = jsonify({'Warning':
                            'Ooops! The bucketlist_id does not exist.'})
        response.status_code = 404
        return response
    elif not items_response:
        response = jsonify({'Warning': 'Ooops! The item_id does not exist.'})
        response.status_code = 404
        return response
    else:
        try:
            new_name = request.json['name']
            items_response.name = new_name
            databases.session.commit()
            response = jsonify({'Status':
                                'Bucketlist Item successfully updated.'})
            response.status_code = 200
            return response
        except KeyError:
            response = jsonify({
                'error': 'Please use name for dict keys.'
            })
            response.status_code = 500
            return response


@app.route('/bucketlist/api/v1/bucketlist/<int:bucket_id>/items/<int:item_id>',
           methods=['DELETE'])
def delete_item(bucket_id, item_id):
    '''
    Deletes an item from abucketlist.
    '''
    payload = verify_token(request)
    if isinstance(payload, dict):
        user_id = payload['user_id']
    else:
        return payload
    res = BucketList.query.filter(BucketList.created_by ==
                                  user_id[0], BucketList.id ==
                                  bucket_id).first()
    items_response = Items.query.filter(BucketList.created_by ==
                                        user_id[0], Items.id ==
                                        item_id).first()
    if not res:
        response = jsonify({'Warning':
                            'Ooops! The bucketlist_id does not exist.'})
        response.status_code = 404
        return response
    elif not items_response:
        response = jsonify({'Warning': 'Ooops! The item_id does not exist.'})
        response.status_code = 404
        return response
    else:
        databases.session.delete(items_response)
        databases.session.commit()
        response = jsonify({'Status': 'Item successfully deleted.'})
        response.status_code = 200
        return response


def verify_token(request):
    '''
    Verifies the passed token's authenticity and return the user_id to which
    the token belongs.
    '''
    token = request.headers.get("Authorization")
    if not token:
        abort(401)
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'],
                             leeway=timedelta(seconds=2))
    except jwt.InvalidTokenError:
        response = jsonify({'error': 'Ooops! Invalid Token'})
        response.status_code = 401
        return response
    except jwt.ExpiredSignatureError:
        return jsonify({'Warning': 'Ooops! Expired Token'})
    return payload


@app.errorhandler(404)
def page_not_found(e):
    response = jsonify({
        'error': 'Oooops! Please check your endpoint url!'
    })
    response.status_code = 404
    return response


@app.errorhandler(405)
def method_not_allowed(e):
    response = jsonify({
        'error':
        'Oooops!Invalid request method. Please check your request method!'
    })
    response.status_code = 405
    return response
