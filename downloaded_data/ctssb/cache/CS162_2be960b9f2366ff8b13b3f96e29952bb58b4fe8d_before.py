import sys
import socket
import select

PORT = 0
SOCKET_LIST = []
channels = {'home':[]}
client_info = {}
RECV_BUFFER = 4096

def join_channel(message, server_socket, client_socket):
    if message[1] not in channels:
        client_socket.send('There is no channel named %s' % message[1])
    else:
        client_channel = client_info[s.getpeername()]
        channels[client_channel[1]].remove(client_socket)
        channels[message[1]].append(client_socket)
        client_info[s.getpeername()] = (client_channel[0], message[1])

def list_channel(message, server_socket, client_socket):
    for channel in channels:
        client_socket.send[channel]

def create_channel(message, server_socket, client_socket):
    if message[1] in channel:
        client_socket.send('There is already a channel named %s' % message[1])
    else:
        client_channel = client_info[s.getpeername()]
        channels[client_channel[1]].remove(client_socket)
        channels[message[1]] = [client_socket]
        client_info[s.getpeername()] = (client_channel[0], message[1])


commands = {'/join': join_channel, '/list': list_channel, '/create': create_channel}

def process_message(message, server_socket, client_socket):
    if message[0] == '/':
        command = message.split()
        commands[command[0]](message, server_socket, client_socket)
    else:
        message.rstrip()
        client_channel = client_info[s.getpeername()][1]
        for s in SOCKET_LIST:
            if s != server_socket and s != client_socket and s in channels[client_channel]:
                message = '[' + client_info[s.getpeername()][0] + ']' + message
                s.send(message)


def server():

    server_socket = socket.socket()
    server_socket.bind(('127.0.0.1', PORT))
    server_socket.listen(10)

    SOCKET_LIST.append(server_socket)
 
    while 1:

        ready_to_read,ready_to_write,in_error = select.select(SOCKET_LIST,[],[],0)
      
        for sock in ready_to_read:
            # client message recieved
            if sock != server_socket:
                client_channel = client_info[sock.getpeername()][1]
                try:
                    message = sock.recv(RECV_BUFFER)
                    if message:
                        process_message(message, server_socket, sock)
                    else:
                        SOCKET_LIST.remove(sock)
                        channels[client_channel].remove(sock)
                except Exception, e:
                    SOCKET_LIST.remove(sock)
                    channels[client_channel].remove(sock)
                    print str(e)
                    return
            # a new connection request recieved
            elif sock == server_socket: 
                new_socket, addr = server_socket.accept()
                SOCKET_LIST.append(new_socket)
                name = new_socket.recv(RECV_BUFFER)
                client_info[addr] = (name, 'home')
                channels['home'].append(new_socket)
                print "%s has joined" % name

 
if __name__ == "__main__":

    PORT = int(sys.argv[1])
    sys.exit(server()) 