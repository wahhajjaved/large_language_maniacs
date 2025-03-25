import os
import sys
import logging
import socket
import time
import copy
import json
import concurrent.futures

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger(__name__)

BUFFER_SIZE = 256
QUORUM = 3

class Proposer():
    def __init__(self, sequence_number_manager, packet_manager, server_address, server_addresses, port):
        self.sequence_number = sequence_number_manager
        self.response_list = {}
        self.packet_manager = packet_manager
        self.server_address = server_address
        self.server_addresses = server_addresses
        self.port = port
        self.accept_count = 0

    def propose(self, data):
        sequence_number = self.sequence_number.increment()
        key = data['data']['key']
        value = data['data']['value']
        operation = data['operation']
        response_list, request_list = self.__prepare_propose_commit(sequence_number, key, value, operation)
        if len(request_list) < QUORUM:
            accept_list, highest_value = self.__accept(response_list, key, value, operation)
            if (self.accept_count > QUORUM):
                packet = self.packet_manager.get_packet('paxos', 'commit', {'key': highest_value['key'], 'value': highest_value['value']}, highest_value['operation'])
                self.__send_commit(packet, accept_list)
        else:
            logger.error('Quorum not received, rejecting promises')
        return self.packet_manager.get_packet('tcp', 'success', 'success')


    # Phase 1
    def __prepare_propose_commit(self, sequence_number, key, value, operation):
        request_list = copy.copy(self.server_addresses)
        response_list = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for server in self.server_addresses:
                    response_list.append(executor.submit(self.__propose_commit, server, request_list, sequence_number))
                beg_time = time.time()
                while len(request_list) >= QUORUM and time.time() - beg_time < 1:  # Timeout after 5 seconds
                    pass
                executor.shutdown(wait=False)
        except ConnectionError as e:
            logger.error('failed to connect to server {}'.format(e))
        except Exception as e:
            print(e)
        return response_list, request_list

    def __propose_commit(self, server_address, request_list, sequence_number):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        count = 0
        sock.settimeout(.5)
        while True:
            try:
                sock.connect((server_address, self.port))
                break
            except:
                count += 1
                if (count > 5): # timeout after 5 tries
                    sock.close()
                    return
        packet = self.packet_manager.get_packet('paxos', 'prepare commit', sequence_number)
        logger.error('Sending prepare commit {} to {}'.format(packet, server_address))
        sock.sendall(packet)
        msg = sock.recv(BUFFER_SIZE).decode()
        if (isinstance(msg, str)):
            msg = json.loads(msg)
        logger.error('Promise {} received from {}'.format(msg, server_address))

        if (msg['status'] == 'promise'):
            request_list.remove(server_address)
        return sock, msg, server_address

    # Phase 2
    def __accept(self, response_list, key, value, operation):
        values = []
        value_count = {}
        for response in response_list:
            response = response.result()
            msg = response[1]
            if (isinstance(msg, str)):
                msg = json.loads(msg)
            data = msg['data']
            print('msg: {}'.format(msg))
            if data['value'] in values:
                value_count[data['value']['value']] += 1
            else:
                values.append(data['value'])
                if (data['value']):
                    value_count[data['value']['value']] = 1
                else:
                    value_count[data['value']] = 1
        highest_value = values[0]
        highest_count = value_count[values[0]['value']]
        for val in values:
            val = val['value']
            if (value_count[val] > highest_count):
                highest_count = value_count[val]
                highest_value = val
        accept_list = []
        sequence_number = self.sequence_number.get_sequence_number()
        if not highest_value:
            packet = self.packet_manager.get_packet('paxos', 'accept', {'key': key, 'value': value, 'sequence_number': sequence_number}, operation)
        else:
            packet = self.packet_manager.get_packet('paxos', 'accept', {'key': highest_value['key'], 'value': highest_value['value'], 'sequence_number': sequence_number}, highest_value['operation'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for response in response_list:
                response = response.result()
                accept_list.append(executor.submit(self.__send_accept, response[0], response[2], packet))
            beg_time = time.time()
            while self.accept_count < QUORUM and time.time() - beg_time < 1:  # Timeout after 5 seconds
                pass
            return accept_list, highest_value

    def __send_accept(self, sock, client_address, packet):
        logger.error('Sending accept ok {} to {}'.format(packet, client_address))
        sock.sendall(packet)
        msg = sock.recv(BUFFER_SIZE).decode()
        logger.error('Accept {} received from {}'.format(msg, client_address))
        if (isinstance(msg, str)):
            msg = json.loads(msg)
        if (msg['status'] == 'accept'):
            self.accept_count += 1
            return sock, client_address
        else:
            sock.close()


    # Phase 3
    def __send_commit(self, packet, response_list):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for response in response_list:
                response = response.result()
                print('response: {}'.format(response))
                executor.submit(self.__commit, response[0], response[1], packet)

    def __commit(self, sock, client_address, packet):
        logger.error('Sending commit ok {} to {}'.format(packet, client_address))
        sock.sendall(packet)
        sock.close()