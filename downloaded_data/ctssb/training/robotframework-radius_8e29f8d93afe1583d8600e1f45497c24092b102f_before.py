"""RobotFramework Radius Module"""
import select
import socket
from pyrad import packet, dictionary, tools
import six
import robot
from robot.libraries.BuiltIn import BuiltIn

#class ClientConnection:
#    def __init__(self,sock,address,port,secret,raddict):
#        self._sock = sock
#        self.address = address
#        self.port = port
#        self.secret = secret
#        self.raddict =  dictionary.Dictionary(raddict)
#        self.close = self._sock.close
class RadiusLibrary(object):
    """Main Class"""

    ROBOT_LIBRARY_SCOPE = 'TEST CASE'

    def __init__(self):
        self._client = robot.utils.ConnectionCache('No Clients Created')

        self._server = robot.utils.ConnectionCache('No Servers Created')

        self.builtin = BuiltIn()


    def create_client(self, alias, address, port,
                      secret, raddict='dictionary',
                      authenticator=True):
        """Creates client"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', 0))
        sock.settimeout(3.0)
        sock.setblocking(0)
        request = robot.utils.ConnectionCache('No Client Sessions Created')
        response = robot.utils.ConnectionCache('No Client Response Created')
        session = {'sock': sock,
                   'address': str(address),
                   'port': int(port),
                   'secret': six.b(str(secret)),
                   'dictionary': dictionary.Dictionary(raddict),
                   'authenticator': authenticator,
                   'request': request,
                   'response': response}

        self._client.register(session, alias=alias)
        return session

    def create_access_request(self,alias=None):
        client = self._get_session(self._client,alias)
        request = packet.AuthPacket(code=packet.AccessRequest,secret=client['secret'],dict=client['dictionary'])
        #request.authenticator = packet.Packet.CreateAuthenticator()
        client['request'].register(request, str(request.id))
        return request

    def create_accounting_request(self,alias=None):
        client = self._get_session(self._client,alias)
        request = packet.AuthPacket(code=packet.AccountingRequest,secret=client['secret'],dict=client['dictionary'])
        client['request'].register(request, str(request.id))
        return request

    ### Request sesction
    def add_request_attribute(self, key, value, alias=None,crypt=False):
        key = str(key)
        client = self._get_session(self._client,alias)
        request = client['request'].get_connection(alias)
        attr_dict_item = request.dict.attributes[key]

        if crypt:
            value = request.PwCrypt(value)
        request.AddAttribute(key,value)

    def send_request(self, alias=None):
        client = self._get_session(self._client,alias)
        request = client['request'].get_connection(alias)
        pdu =  request.RequestPacket()
        client['sock'].sendto(pdu, (client['address'], client['port']))
        return dict(request)

    ### Auth request section


    def add_response_attribute(self, key, value, alias=None):
        key = str(key)
        server = self._get_session(self._server,alias)
        response = server['response'].get_connection(alias)
        response.AddAttribute(key,value)

    def send_response(self, alias=None):
        server = self._get_session(self._server, alias)
        request = server['request'].get_connection(alias)
        response = server['response'].get_connection(alias)
        pdu =  response.ReplyPacket()
        server['sock'].sendto(pdu, request.addr)
        return request


    def receive_access_accept(self, alias=None, timeout=1):
        """Receives access accept"""
        return self.receive_response(alias, packet.AccessAccept, timeout)

    def receive_access_reject(self, alias=None, timeout=1):
        """Receives access accept"""
        return self.receive_response(alias, packet.AccessReject, timeout)

    def receive_accounting_response(self, alias=None, timeout=1):
        """Receives access accept"""
        return self.receive_response(alias, packet.AccountingResponse, timeout)

    def receive_request(self,alias,code,timeout):
        server = self._get_session(self._server, alias)
        ready = select.select([server['sock']], [], [], float(timeout))

        pkt = None
        if ready[0]:
            data, addr = server['sock'].recvfrom(1024)
            pkt = packet.Packet(secret=server['secret'], packet=data,
                                    dict=server['dictionary'])
            server['request'].register(pkt,str(pkt.id))

            self.builtin.log(pkt.code)
            if pkt.code != code:
                self.builtin.log('Expected {0}, received {1}'.format(code, pkt.code))
                raise Exception("received {}".format(pkt.code))
        if pkt is None:
            raise Exception("Did not receive any answer")
        pkt.addr = addr
        return pkt

    def receive_response(self,alias,code,timeout):
        client = self._get_session(self._client, alias)
        ready = select.select([client['sock']], [], [], float(timeout))

        pkt = None
        if ready[0]:
            data, addr = client['sock'].recvfrom(1024)
            pkt = packet.Packet(secret=client['secret'], packet=data,
            dict=client['dictionary'])
            client['response'].register(pkt,str(pkt.id))

            self.builtin.log(pkt.keys())
            if pkt.code != code:
                self.builtin.log('Expected {0}, received {1}'.format(code, pkt.code))
                raise Exception("received {}".format(pkt.code))
        if pkt is None:
                raise Exception("Did not receive any answer")

        return pkt

    def receive_accounting_request(self, alias=None, timeout=1):
        """Receives access request"""
        return self.receive_request(alias, packet.AccountingRequest, timeout)

    def receive_access_request(self, alias=None, timeout=1):
        """Receives access request"""
        return self.receive_request(alias, packet.AccessRequest, timeout)

    def _get_session(self, cache, alias):
        # Switch to related client alias
        if alias:
            return cache.switch(alias)
        else:
            return cache.get_connection()

    def create_accounting_response(self, alias=None):
        """Send Response"""
        session = self._get_session(self._server,alias)
        request = session['request'].get_connection(alias)

        reply = request.CreateReply()
        reply.code = packet.AccountingResponse

        pdu = reply.ReplyPacket()
        session['sock'].sendto(pdu, request.addr)
        session['response'].register(reply,str(reply.code))
        #todo: deregister request
        return reply

    def create_access_accept(self, alias=None):
        """Send Response"""
        session = self._get_session(self._server,alias)
        request = session['request'].get_connection(alias)

        reply = request.CreateReply()
        reply.code = packet.AccessAccept
        session['response'].register(reply,str(reply.code))
        #todo: deregister request
        return reply

    def send_accounting_request(self, alias=None, **attributes):
        session=self._get_session(self._client, alias)

        pkt = packet.AcctPacket(code=packet.AccountingRequest, secret=session['secret'],
                                dict=session['dictionary'], **attributes)

        #pkt.authenticator = pkt.CreateAuthenticator()
        pdu = pkt.RequestPacket()

        session['request'].register(pkt, str(pkt.id))
        session['sock'].sendto(pdu, (session['address'], session['port']))

        return pkt

    def send_accounting_response(self, alias=None, **attributes):
        session=self._get_session(self._server, alias)

        pkt = session['request'].get_connection()
        reply_pkt = pkt.CreateReply(**attributes)
        reply_pkt.code = packet.AccountingResponse
        pdu = reply_pkt.ReplyPacket()
        session['sock'].sendto(pdu, pkt.addr)
        return reply_pkt


    #def create_server(self, alias=u'default', address='127.0.0.1', port=0, secret='secret', raddict='dictionary'):
    def create_server(self, alias=None, address='127.0.0.1', port=0, secret='secret', raddict='dictionary'):
        """Creates Radius Server"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((address, int(port)))
        #sock.settimeout(3.0)
        sock.setblocking(0)
        request = robot.utils.ConnectionCache('No Server Requests Created')
        response = robot.utils.ConnectionCache('No Server Responses Created')
        server = {'sock': sock,
                  'secret': six.b(str(secret)),
                  'dictionary': dictionary.Dictionary(raddict),
                  'request':request,
                  'response':response}

        self._server.register(server, alias=alias)
        return server

    def destroy_server(self,alias):
        session = self._server.switch(alias)
        session['sock'].close()
        self._server.empty_cache()

    def should_contain_attribute(self,cache,key,val,alias):
        session=self._get_session(cache, alias)
        request = None
        if cache == self._client:
            request = session['response'].get_connection(alias)
        elif cache == self._server:
            request = session['request'].get_connection(alias)
        else:
            raise BaseException('No match for cache')
        if not val:
            if str(key) in request:
                return True
            else:
                raise BaseException('key not found')
        else:

            if str(key) in request and val in request[str(key)]:
                return
            else:
                raise BaseException('value "{}" not in {}'.format(val,request[str(key)]))

    def request_should_contain_attribute(self, key, val=None, alias=None):
        return self.should_contain_attribute(self._server,key,val,alias)

    def response_should_contain_attribute(self, key, val=None, alias=None):
        return self.should_contain_attribute(self._client,key,val,alias)
