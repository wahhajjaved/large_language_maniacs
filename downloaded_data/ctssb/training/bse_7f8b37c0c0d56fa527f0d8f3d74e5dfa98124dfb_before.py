import json

import falcon
from falcon_multipart.middleware import MultipartMiddleware

from tasks import search_task, add_book_task
from utils import (validate_email, extract_username, save_file)
from es import (create_index, delete_index, count_items, add_book, search)


class BSEResource(object):
    """
    Books Search Engine main class
    """

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200  # This is the default status
        resp.content_type = 'text/html'
        with open('./templates/base.html', 'r') as f:
            html_template = f.read()
        with open('./static/js/bse.js', 'r') as f:
            js_script = f.read()
        html_template = html_template.replace("<script></script>", "<script>" + js_script + "</script>")
        resp.body = html_template

    def on_post(self, req, resp):
        try:
            raw_json = req.stream.read().decode("utf-8")
        except Exception as ex:
            raise falcon.HTTPError(falcon.HTTP_400, 'Error', ex.args)

        try:
            result_json = json.loads(raw_json, encoding='utf-8')
        except ValueError:
            raise falcon.HTTPError(falcon.HTTP_400,
                                   'Malformed JSON',
                                   'Could not decode the request body. The '
                                   'JSON was incorrect.')

        # inner request object
        reqo = {}
        for item in result_json:
            reqo[item['name']] = item['value']

        email = reqo['email']

        # inner response object
        reso = {}
        if not validate_email(email):
            reso['is_e'] = True
            reso['e'] = 'Email ' + email + ' is invalid.'
        else:
            reso['is_e'] = False
            reso['username'] = extract_username(email)
            reso['email'] = email

            search_task.delay(reqo)

        resp.body = json.dumps(reso)
        resp.status = falcon.HTTP_200


class AdminResource(object):
    """
    Books Search Engine admin class
    """

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200  # This is the default status
        resp.content_type = 'text/html'
        with open('./templates/admin.html', 'r') as f:
            html_template = f.read()
        with open('./static/js/admin.js', 'r') as f:
            js_script = f.read()
        html_template = html_template.replace("<script></script>", "<script>" + js_script + "</script>")
        resp.body = html_template

    def on_post(self, req, resp):
        cmd = req.get_param('cmd')

        result = {}
        if cmd == 'add':
            book = req.get_param('book')
            file_path = save_file(book)
            path = {'path': file_path}
            add_book.delay(path)
            result = {'msg': 'file add queued'}
        elif cmd == 'create':
            result = create_index()
        elif cmd == 'delete':
            result = delete_index()
        elif cmd == 'count':
            result = count_items()
        elif cmd == 'search':
            q = req.get_param('q')
            result = search(q)

        resp.body = json.dumps({'result': result})
        resp.status = falcon.HTTP_200


# falcon.API instances are callable WSGI apps
app = falcon.API(middleware=[MultipartMiddleware()])

# Resources are represented by long-lived class instances
bse = BSEResource()
adm = AdminResource()

# things will handle all requests to the '/things' URL path
app.add_route('/', bse)
app.add_route('/admin', adm)
