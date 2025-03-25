import json
import socket

from user import User
from blockchain import Peoplechain

import requests
from klein import Klein
from uuid import uuid4

FULL_NODE_PORT = "21007"
NODES_URL = "http://{}:{}/nodes" # GET RETURNS ALL THE NODES, POST ADDS NODE
USERS_URL = "http://{}:{}/users" # GET RETURNS ALL THE USER, POST ADDS NEW USER
USER_URL = "http://{}:{}/{}" # GET RETURNS USER DATA, POST EDITS USER DATA

# SEARCH FOR PEER NODES
# GET CHAIN FROM OTHER NODES OR INITIALIZE BLOCKCHAIN IF NO OTHER NODE
# BROADCAST NODEs
# BROADCAST NEW USER/USER CHANGE
# ACCEPT NODES
# SEND CHAIN
# ACCEPT NEW USERS/USER CHANGE

class Node:

    full_nodes = set()
    app = Klein()

    def __init__(self, full_node=None):

        if full_node is None:
            self.peoplechain = Peoplechain()
            self.full_nodes.add(self.my_node())
        else:
            self.add_node(full_node)
            self.request_nodes(full_node, FULL_NODE_PORT)
            self.request_nodes_from_all()
            self.broadcast_node()
            longest = 0
            for node in self.full_nodes:
                user_chain = self.request_users(node)
                if len(user_chain) > longest:
                    remote_users = user_chain
                    longest = len(user_chain)

            self.peoplechain = Peoplechain(remote_users)
            self.full_nodes.add(self.my_node())
            
        print ("\nFull node server started...\n\n")
        self.app.run('0.0.0.0', FULL_NODE_PORT)

    def request_nodes(self, node, port):
        if node == self.my_node():
            return None
        url = NODES_URL.format(node, port)
        try:
            response = requests.get(url)
            if response.status_code == 200:
                all_nodes = response.json()
                return all_nodes
        except requests.exceptions.RequestException as re:
            pass
        return None

    def request_nodes_from_all(self):
        full_nodes = self.full_nodes.copy()
        bad_nodes = set()

        for node in full_nodes:
            all_nodes = self.request_nodes(node, FULL_NODE_PORT)
            if all_nodes is not None:
                full_nodes = full_nodes.union(all_nodes["full_nodes"])
            else:
                bad_nodes.add(node)

        self.full_nodes = full_nodes #NOW DOWNLOAD BLOCKCHAIN FROM ALL NODES AND SET THE LONGEST CHAIN AS MY CHAIN

        for node in bad_nodes:
            self.remove_node(node)
        return

    def my_node(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        my_node = s.getsockname()[0]
        s.close()
        return my_node

    def remove_node(self, node):
        pass

    def add_node(self, host):

        if host == self.my_node():
            return

        if host not in self.full_nodes:
            self.full_nodes.add(host)

    def broadcast_node(self):

        bad_nodes = set()
        my_node = self.my_node()
        data = {
            "host": my_node
        }

        for node in self.full_nodes:
            if node == my_node:
                continue
            url = NODES_URL.format(node, FULL_NODE_PORT)
            try:
                requests.post(url, json=data)
            except requests.exceptions.RequestException as re:
                bad_nodes.add(node)

        for node in bad_nodes:
            self.remove_node(node)
        bad_nodes.clear()
        return

    def broadcast_user(self, user):
        self.request_nodes_from_all()
        bad_nodes = set()
        data = {
            "user": user.to_json()
        }

        for node in self.full_nodes:
            if node == self.my_node():
                continue
            url = USERS_URL.format(node, FULL_NODE_PORT)
            try:
                response = requests.post(url, json=data)
            except requests.exceptions.RequestException as re:
                bad_nodes.add(node)

        for node in bad_nodes:
            self.remove_node(node)
        bad_nodes.clear()
        return

    def edit_user(self, user):
        pass

    def request_users(self, node):
        url = USERS_URL.format(node, FULL_NODE_PORT)
        users = []
        try:
            response = requests.get(url)
            if response.status_code == 200:
                users_list = response.json()
                for user_list in users_list:
                    user = User(user_list['_address'], user_list['_name'], user_list['_balance'], user_list['_data'])
                    users.append(user)
                return users
        except requests.exceptions.RequestException as re:
            pass
        return 0

    @app.route('/nodes', methods=['GET'])
    def get_nodes(self, request):
        response = {
            "full_nodes": list(self.full_nodes)
        }
        return json.dumps(response).encode('utf-8')

    @app.route('/nodes', methods=['POST'])
    def post_nodes(self, request):
        request_body = json.loads(request.content.read())
        host = request_body['host']
        self.add_node(host)
        response = {
            "message": "Node registered"
        }
        return json.dumps(response).encode('utf-8')

    @app.route('/users', methods=['GET'])
    def get_users(self, request):
        return json.dumps([user.__dict__ for user in self.peoplechain.get_all_users()]).encode('utf-8')

    @app.route('/users', methods=['POST'])
    def post_users(self, request):
        body = json.loads(request.content.read())
        user = User.from_json(body['user'])
        self.peoplechain.add_user(user)
        self.broadcast_user(user)
        response = {
            'success': "User added"
        }
        return json.dumps(response).encode('utf-8')

    @app.route('/user/<address>', methods=['GET'])
    def get_user_by_address(self, request, address):
        user = self.peoplechain.get_user_by_address(address)
        if user is not None:
            response = {
                "user": user.to_json()
            }
            return json.dumps(response)
        else:
            response = {
                "message": "User not found"
            }
            return json.dumps(response).encode('utf-8')

    @app.route('/user/<address>', methods=['POST'])
    def edit_user_by_address(self, request, address):
        pass

if __name__ == '__main__':

    node = Node()
