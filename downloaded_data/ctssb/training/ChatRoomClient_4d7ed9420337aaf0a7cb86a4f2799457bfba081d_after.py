# Colby Jeffries & Scott Stoudt
# chatroom_server.py

'''
This script is the server for our chatroom client.

INSERT DOCS HERE

'''

# Modules
import socket
import random
import string
import threading
import hashlib, uuid
import json

class ChatRoom:
    '''
    This class contains an individual chat room.

    INSERT DOCS HERE

    '''
    def __init__(self, parent, name, port, password=None, salt=None):
        '''
        CONSTRUCTOR DOCS

        '''
        self.parent = parent
        self.users = {}
        self.name = name
        self.port = port
        self.max_users = 64
        self.password = password
        self.salt = salt
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('', self.port))

        self.thread = threading.Thread(target=self.run, args=())
        self.thread.start()


    def run(self):
        '''
        DOCS

        '''
        while not self.users:
            pass
        while self.users:
            data, addr = self.socket.recvfrom(1024)
            if data and (addr in self.users.keys()):
                data = data.decode()
                if data.split()[0] == 'MESSAGE':
                    data = data[7:]
                    data = (self.users[addr] + ': ' + data + '\r\n')
                    for user in self.users.keys():
                        self.socket.sendto(('MESSAGE '+ data).encode(), user)

                elif data.split()[0] == 'QUIT':
                    self.socket.sendto('GOODBYE 0\r\n'.encode(), addr)
                    for user in self.users.keys():
                        if user != addr:
                            self.socket.sendto(('MESSAGE' + self.users[addr] + 'has left the room.').encode(), user)

                    del self.users[addr]


        self.socket.close()
        del self.parent.chat_rooms[self.name]


class ManagerServer:
    '''
    This class contains the overall chat server.

    INSERT DOCS HERE

    '''
    def __init__(self):
        '''
        CONSTRUCTOR DOCS

        '''
        # Initialize needed containers.
        self.chat_rooms = {}
        self.users = {}

        # Guest counter.
        self.guest_counter = 1

        # Initialize entry point socket.
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serverPort = 25000
        self.serverSocket.bind(('', self.serverPort))
        self.serverSocket.listen(10)

        # Infinite loop.
        while True:
            # Accept connections, save the address.
            connectionSocket, addr = self.serverSocket.accept()
            thread = threading.Thread(target=self.on_new_client, args=(connectionSocket, addr))
            thread.start()

    def on_new_client(self, connectionSocket, addr):
        while True:
            message = connectionSocket.recv(1024)
            if addr not in self.users.keys():
                self.users[addr] = 'Guest {}'.format(self.guest_counter)
                self.guest_counter += 1
                if self.guest_counter > 99999:
                    self.guest_counter = 1

            if message:
                message_tokens = message.decode().split()
                # USER username
                # Adds uers to the global list of users.
                if message_tokens[0] == 'USER':
                    if message_tokens[1] not in self.users.values():
                        self.users[addr] = message_tokens[1]
                        connectionSocket.send('User name added 0\r\n'.encode())
                    else:
                        connectionSocket.send('User name in use 1\r\n'.encode())

                # ROOM roomname *password*
                # Creates a room with the given room name and password. Password is
                # optional.
                elif message_tokens[0] == 'ROOM':
                    if message_tokens[2] not in self.chat_rooms.keys():
                        if len(message_tokens) > 3:
                            salt = uuid.uuid4().hex.encode()
                            pas = hashlib.sha512(message_tokens[3].encode() + salt).hexdigest()
                        else:
                            pas = None
                            salt = None

                        user_port = message_tokens[1]
                        new_addr = (addr[0], int(user_port))

                        port = random.randint(25001, 50000)
                        self.chat_rooms[message_tokens[2]] = ChatRoom(self, message_tokens[2], port, pas, salt)
                        self.chat_rooms[message_tokens[2]].users[new_addr] = self.users[addr]
                        connectionSocket.send('ChatRoom established and joined {0} 0\r\n'.format(self.chat_rooms[message_tokens[2]].port).encode())
                    else:
                        connectionSocket.send('ChatRoom name in use 1\r\n'.encode())

                # JOIN roomname *password*
                # Joins a room with the given room name and password. Password is
                # optional.
                elif message_tokens[0] == 'JOIN':
                    if message_tokens[2] in self.chat_rooms.keys():
                        if len(message_tokens) > 3:
                            pas = message_tokens[3]
                        else:
                            pas = None

                        udp_port = message_tokens[1]
                        new_addr = (addr[0], int(udp_port))

                        if (pas is None and self.chat_rooms[message_tokens[2]].password is None) or (hashlib.sha512(pas.encode() + self.chat_rooms[message_tokens[2]].salt).hexdigest() == self.chat_rooms[message_tokens[2]].password):
                            if len(self.chat_rooms[message_tokens[2]].users) < self.chat_rooms[message_tokens[2]].max_users:
                                connectionSocket.send('Connected to chat room {0} 0\r\n'.format(self.chat_rooms[message_tokens[2]].port).encode())
                                self.chat_rooms[message_tokens[2]].users[new_addr] = self.users[addr]
                        else:
                            connectionSocket.send('Incorrect password 1\r\n'.encode())
                    else:
                        connectionSocket.send('Invlaid room 1\r\n'.encode())

                elif message_tokens[0] == 'QUIT':
                    del self.users[addr]
                    connectionSocket.send('Goodbye! 0\r\n'.encode())

                elif message_tokens[0] == 'INFO':
                    dict_list = []
                    for i in self.chat_rooms.values():
                        temp = {}
                        temp['name'] = i.name
                        temp['users'] = len(i.users)
                        if i.password is None:
                            temp['pass'] = 0
                        else:
                            temp['pass'] = 1

                        dict_list.append(temp)

                    connectionSocket.send(json.dumps(dict_list).encode())

                else:
                    connectionSocket.send('Invalid command 1\r\n'.encode())

            else:
                connectionSocket.send('Invalid command 1\r\n'.encode())


if __name__ == '__main__':
    server = ManagerServer()
