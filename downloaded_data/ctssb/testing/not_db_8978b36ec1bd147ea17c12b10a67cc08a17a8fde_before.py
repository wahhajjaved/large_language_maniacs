from flask_restful import Resource, Api
from flask import Flask, request, render_template
from not_db import not_db
import json
app = Flask(__name__)
api = Api(app)

@app.route('/')
def healthcheck():
    return render_template("base.html")

class Base(Resource):

    Book = None 
    def not_found(self, thing):
        return None, 404 

    def parse_request(self, request):
        if request.json:
           return request.json
        else:
           return request.form.get('data')

class Book(Base):
    def get(self, db):
        self.create_book(db)

    def post(self, db):
        self.create_book(db)

    def put(self, db):
        self.create_book(db)

    def delete(self, db):
        self.create_book(db)
        self.Book.drop()

    def create_book(self, db, *args, **kwargs):    
        if not self.Book:
           self.Book = not_db(db, driver="s3")
        if self.Book.error:
            return self.Book.error


class List(Book):
    def get_list(self, list_name, db):
        if not self.Book:
            self.create_book(db)
        l = self.Book.get_contents(list_name)
        return l if l else self.not_found(l)

    def get(self, list_name, db):
        return self.get_list(list_name, db)

    def put(self, list_name, db):
        l = self.get_list(list_name, db)
        if not l[0]:
            self.Book.set(list_name, [self.parse_request(request)])
        else:
            self.Book.set(list_name, l + [self.parse_request(request)])
        return self.Book.get_contents(list_name)

    def post(self, *args, **kwargs):
        return self.put(*args, **kwargs)

    def delete(self, list_name, db):
        l = self.get_list(list_name, db)
        resp = 404 if l[-1] == 404 else 200
        self.Book.remove(list_name)
        return None, resp


class Item(List):


    def index_fail(self, index, list_name, db):
        list_ = self.get_list(list_name, db)
        try:
            list_[index]
            return (list_, True)
        except:
            return (list_, False)

    def get(self, index, list_name, db):
        list_, index_exist = self.index_fail(index, list_name, db) 
        if not index_exist:
            return self.not_found(list_) 
        return self.Book.get_contents(list_name, db)[index]


    def put(self, index, list_name, db):
        list_, index_exist = self.index_fail(index, list_name, db)
        if not index_exist:
            return self.not_found(list_) 
        list_.insert(index, self.parse_request(request))
        self.Book.set(list_name, list_)
        return self.Book.get_contents(list_name)

    def post(self, index, list_name, db):
        list_, index_exist = self.index_fail(index, list_name, db)
        if not index_exist:
            return self.not_found(list_) 
        list_[index] = self.parse_request(request)
        self.Book.set(list_name, list_)
        return self.Book.get_contents(list_name)

    def delete(self, index, list_name, db):
        list_, index_exist = self.index_fail(index, list_name, db)
        if not index_exist:
            return self.not_found(list_) 
        list_.pop(index)
        self.Book.set(list_name, list_)
        return self.Book.get_contents(list_name)

class File(Book):
    def get(self, file_name,  db):
        if not self.Book:
            self.create_book(db)
        return self.Book.get_contents(file_name, raw=True)

    def put(self, db, file_name=None):
        if not self.Book:
            self.create_book(db)
        for file_ in request.files:
            if file_name is None:
               file_name = request.files[file_].filename
               self.Book.raw_set(file_name, request.files[file_].read())
            else:    
               self.Book.raw_set(file_name, request.files[file_].read())
        return "/{}/file/{}".format(self.Book.name, file_name) 

    def post(self, *args, **kwargs):
        return self.put(*args, **kwargs)

    def delete(self, file_name, db):
        l = self.get_list(list_name, db)
        resp = 404 if l[-1] == 404 else 200
        self.Book.remove(list_name)
        return None, resp


class File_Auto_Name(File):
    pass

api.add_resource(Item, '/<string:db>/list/<string:list_name>/<int:index>')
api.add_resource(List, '/<string:db>/list/<string:list_name>')
api.add_resource(File, '/<string:db>/file/<string:file_name>')
api.add_resource(File_Auto_Name, '/<string:db>/file/')
api.add_resource(Book, '/<string:db>')

def main():
   app.run(host="0.0.0.0", debug=True)

if __name__ == '__main__':
   app.run(host="0.0.0.0", debug=True)
