# INFO: #
# First version.
# Not tested.
# ===================================

'''
TO DO:
'''

import socket, Queue
from threading import Thread

# Constants: #
## General: ##
NUM_OF_THREADS = 20
SIZE_OF_QUEUE = 40
## FLAGS: ##
TO_DATABASE=("REG", "AUT", "EXI")
TO_MEMORY=("MNF", "LUD", "GET")
## Connectivity: ##
PORT = 3417
MEMORY_IP = '127.0.0.1'
MEMORY_PORT = '3330'
DATABASE_IP = '127.0.0.1'
DATABASE_PORT = '6853'

# Methods: #
## SSL/TLS Methods: ##
def secure_accept(server_socket):
    ''' This method needs to accept a new client and establish a secure TCP connection with him (over SSL/TLS).
        It will return exacly what the normal accept method returns UNLESS we will need to change it.
    '''
    cs,ca = server_socket.accept()
    return (cs, ca)

def secure_recv(sock, size = '5000'):
    ''' This method needs to receive the encrypted message (the ciphertext), decrypt it and return the plaintext.
    '''
    return sock.recv(size)

def file_recv(sock):
    ''' This method is for reciving large files.
    '''
    response=secure_recv(sock)
    flag, str_size = response.split(';')
    try:
        if flag != 'SIZ':
            raise
        size = int(str_size)
    except:
        if count < 3: #Just making sure that it won't attemt endlessly
            seure_send(sock, 'NAK')
            final_response = file_recv(sock, count+1)
        else:
            final_response = 'WTF'
        return final_response
    seure_send(sock, 'ACK')
    final_response = secure_recv(sock, size)
    return final_response
def secure_send(sock, mess):
    ''' This method needs to get the message (the plaintext), encrypt it and send it (the ciphertext).
    '''
    print "sending {m}".format(m=mess) # -For The Record-
    sock.send(mess)

def file_send(sock, mess):
    ''' This method is for sending large files.
    '''
    size=len(mess)
    secure_send(sock, 'SIZ;{}'.format(size))
    response=secure_recv(sock)
    if response == 'NAK':
        file_send(sock, mess)
        return
    elif response == 'ACK':
        secure_send(sock, mess)
    else: #Just so there'll be an else...
        pass

def secure_close(sock):
    ''' This method needs to...
    '''
    sock.close()
    
## General Methods: ##
def do_work():
    client_socket, client_addr = q.get()
    while True:
        req = secure_recv(client_socket)
        if req == "":
            secure_close(client_socket)
            print "Closed connection" # -For The Record-
            q.task_done()
        else:
            try:
                data=req.split(';')
                cmd=data[0]
                get=False
                if cmd == 'GET':
                    cmd == 'EXI'
                    req='EXI;{}'.format(data[1]) # Change the command on the request
                    get=True
                if cmd in TO_MEMORY: # A request for the memory module
                    target_ip=MEMORY_IP
                    targer_port=MEMORY_PORT
                elif cmd in TO_DATABASE: # A request for the memory module
                    target_ip=DATABASE_IP
                    targer_port=DATABASE_PORT
                else: # An unknown request
                    raise
            except: # An unknown request
                secure_send(client_socket, 'WTF')
            else: # A known request
                forward_socket=socket.socket()
                forward_socket.connect((target_ip, target_port))
                secure_Send(forward_socket, req)
                module_response=secure_recv(forward_socket)
                secure_close(forward_socket)
                if get: # It was a get request, thus it requires a second operation - obtaining the folder
                    parsed_module_response=module_response.splot(';')
                    flag = parsed_module_response[0]
                    if flag == 'SCS': # Only if the name exists this flag should appear, and only then we should attemt to get the folder
                        req='GET;{}'.format(data[1]) # Return the request to it's original form
                        forward_socket.connect((MEMORY_IP, MEMORY_PORT))
                        secure_send(forward_socket, req)
                        module_response = file_recv(forward_socket)
                        secure_close(forward_socket)
                    elif flag == 'NNM':
                        module_response = 'NNM'
                    else:
                        module_response = 'WTF'
                    file_send(client_socket, module_response)
                else:
                    secure_send(client_socket, module_response)
            

def make_threads_and_queue(num, size):
    global q
    q = Queue.Queue(size)
    for i in xrange(num):
        t = Thread(target=do_work)
        t.deamon = True
        t.start()


## Main Activity Method: ##
def main():
    make_threads_and_queue(NUM_OF_THREADS, SIZE_OF_QUEUE)
    server_socket = socket.socket()
    server_socket.bind(('0.0.0.0',PORT))
    print "Running... on port {}".format(port) # -For The Record-

    while True:
        client_socket, client_addr = secure_accept(server_socket)
        print "A client accepted" # -For The Record-
        q.put((client_socket, client_addr))

'''
Exciting. Satisfying. Period.
.
'''
