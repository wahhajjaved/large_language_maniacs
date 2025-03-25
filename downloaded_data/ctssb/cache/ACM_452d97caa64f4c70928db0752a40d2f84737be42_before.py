"""

This simple website takes in your journal entries, stores it for you
and allows you to edit it.

This website is in flask.

Stores data as a hash map
"""

#all the imports
from flask import Flask, request, session, g, redirect, url_for, abort, \
    render_template, flash
import pickle
import os

#configuration
DATABASE = ''
DEBUG = False
SECRET_KEY = 'development key'
USERNAME = 'admin'
PASSWORD = 'default'
DATAFILE = 'dataStore'

#create our little application
app = Flask(__name__)
app.config.from_object(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/get")
def get_value():
    key = request.args.get('key')
    value_exists = g.data.has_key(key)
    value = False
    if(value_exists):
        value = g.data.get(request.args.get('key',''))
    return render_template('get.html', value=value, value_exists=value_exists, key=key)

@app.route("/put", methods=['POST'])
def put_value():
    key = request.form['key']
    value = request.form['value']
    g.data.add(key,value)
    return "" + key + " is now associated with: " + value

@app.route("/delete", methods=['POST'])
def remove_value():
    key = request.form['key']
    g.data.remove(key)
    return render_template('get.html', value=None, value_exists=False, key=key) 

@app.before_request
def before_request():
    """Initializes a datastore for this session"""
    g.data = dataStore()
    
@app.teardown_request
def teardown_request(exception):
    """sends data to a persistent file, closes connection"""
    g.data.serialize()

class dataStore:
    def __init__(self):
        if os.path.isfile(DATAFILE):
            fileobject = open(DATAFILE, "r")
            self.root = pickle.load(fileobject)  
        else:
            self.root = None 

    def get(self, key):
        """used to get an item in the map"""
        if(self.root is None):
            return None
        else:
            node, parent = self.root.lookup(key)
            return node.value

    def has_key(self, key):
        """Check if a key is associated with a value in the map"""
        v = self.get(key)
        return v != None

    def add(self,key,value):
        """used to add an item in the map, must be of the form {key:value}"""
        if(self.root is not None):
            self.root.insert(key, value)
        else:
            self.root = Node(key, value)

    def remove(self,key):
        """used to remove an item from the map"""
        if(self.root is not None):
            self.root.delete(key)

    def isEmpty(self):
        """checks if hashmap is empty, returns a boolean"""
        return self.root is None

    def makeEmpty(self):
        """makes the hashmap empty, if it isn't already"""
        self.root = None

    def serialize(self):
        fileobject = open(DATAFILE, "w")
        pickle.dump(g.data.root, fileobject)
        #sends the datastructure to a file on teardown
        #to load simply do x = pickle.load(fileobject)

class Node:
    """
    Tree node: left and right child + data which can be any object
    Credit to Laurent Luce
    """
    def __init__(self, key, value):
        """
        Node constructor

        @param data node data object
        """
        self.left = None
        self.right = None
        self.key = key
        self.value = value

    def insert(self, key, value):
        """
        Insert new node with data

        @param data node data object to insert
        """
        if key < self.key:
          if self.left is None:
            self.left = Node(key, value)
          else:
            self.left.insert(key, value)
        else:
          if self.right is None:
            self.right = Node(key, value)
          else:
            self.right.insert(key, value)

    def lookup(self, key, parent=None):
        """
        Lookup node containing data

        @param data node data object to look up
        @param parent node's parent
        @returns node and node's parent if found or None, None
        """
        if key < self.key:
            if self.left is None:
                return None, None
            return self.left.lookup(key, self)
        elif key > self.key:
            if self.right is None:
                return None, None
            return self.right.lookup(key, self)
        else:
            return self, parent

    def delete(self, key):
          """
          Delete node containing data

          @param data node's content to delete
          """
          # get node containing data
          node, parent = self.lookup(key, value)
          if node is not None:
              if parent.left is node:
                  parent.left = None
              else:
                  parent.right = None
              del node

    def tree_data(self):
        """
        Generator to get the tree nodes data
        """
        # we use a stack to traverse the tree in a non-recursive way
        stack = []
        node = self
        while stack or node: 
            if node:
                stack.append(node)
                node = node.left
            else: # we are returning so we pop the node and we yield it
                node = stack.pop()
                yield [node.key, node.value]
                node = node.right

if __name__ == '__main__':
    app.debug = True
    app.run()
