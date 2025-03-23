from pyrad import packet,dictionary
import socket
import six
import select
import robot
from robot.libraries.BuiltIn import BuiltIn

class RadiusClientLibrary(object):
    def __init__(self,addr,port,secret,dictionary='dictionary'):
        self._cache = robot.utils.ConnectionCache('No Sessions Created')
        self.builtin = BuiltIn()
        self.addr = (addr, int(port))
        self.attributes = []
        self.secret = str(secret)
        self.dictionary = dictionary
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0',0))
        self.sock.settimeout(3.0)
        self.sock.setblocking(0)

    def create_session(self, alias, address, port, secret, dictionary='dictionary'):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0',0))
        sock.settimeout(3.0)
        sock.setblocking(0)
        session= { 'sock': sock,
                   'address': address,
                   'port': port,
                   'secret': six.b(str(secret)),
                   'dictionary': dictionary}
        self._cache.register(session, alias=alias)
        return session

    def send_request(self, alias, code, attributes):
        session = self._cache.switch(alias)
        p = packet.AuthPacket(code=code, secret=session['secret'], id=124,dict=dictionary.Dictionary(session['dictionary']))
        
        for attr in attributes:
            if attr[0] == 'User-Password':
                p[attr[0]] = p.PwCrypt(attr[1])
            else:
                p[attr[0]] = attr[1]

        raw = p.RequestPacket()
       
        session.sock.sendto(raw,self.addr)
        
    def add_attribute(self,name,value):
        if type(name) == unicode:
            name = str(name)
        self.attributes.append((name,value))

    def send_access_request(self):
        p = packet.AuthPacket(code=1, secret=six.b(self.secret), id=124,dict=dictionary.Dictionary(self.dictionary))
        
        for attr in self.attributes:
            if attr[0] == 'User-Password':
                p[attr[0]] = p.PwCrypt(attr[1])
            else:
                p[attr[0]] = attr[1]

        raw = p.RequestPacket()
       
        self.sock.sendto(raw,self.addr)

    def receive_access_accept(self):
        ready = select.select([self.sock], [], [], 5)
        p = None
        if ready[0]:
            data, addr = self.sock.recvfrom(1024)
            p = packet.Packet(secret=self.secret,packet=data,dict=dictionary.Dictionary(self.dictionary))
            
            if p.code != packet.AccessAccept:
                raise Exception("received {}",format(p.code))
        if p == None:
          raise Exception("Did not receive any answer")
        else:
          self.response = p

    def response_attribute_count(self):
        return len(self.response)
    def response_attribute_equals(self,k,v):
        if type(k) == unicode:
          k = str(k)
        if type(v) == unicode:
          v = str(v)
        if  k not in self.response:
          raise Exception('Attribute {0} does not exist'.format(k))
        if type(v) == list:
          if v != self.response[k]:
            raise Exception('{0} != {1}'.format(self.response[k], v))

        else:
          if v not in self.response[k]:
            raise Exception('{0} not in  {1}'.format(self.response[k], v))

    def receive_access_reject(self):
        ready = select.select([self.sock], [], [], 5)
        p = None
        if ready[0]:
            data, addr = self.sock.recvfrom(1024)
            p = packet.Packet(secret=self.secret,packet=data,dict=dictionary.Dictionary(self.dictionary))
            
            if p.code != packet.AccessReject:
                raise Exception("Did not receive Access Reject")
        print p
        self.response = p

    def send_accounting_request(self):
        p = packet.AcctPacket(secret=self.secret, id=124,dict=dictionary.Dictionary(self.dictionary))
        print self.attributes
        for attr in self.attributes:
            p[attr[0]] = attr[1]
        print p
        raw = p.RequestPacket()
       
        self.sock.sendto(raw,self.addr)

    def receive_accounting_response(self):
        ready = select.select([self.sock], [], [], 1)
        p = None
        while True:
            if ready[0]:
                data, addr = self.sock.recvfrom(1024)
                p = packet.AcctPacket(secret=self.secret,packet=data,dict=dictionary.Dictionary(self.dictionary))
                break
        if p.code != packet.AccountingResponse:
            raise Exception("received {}",format(p.code))
        elif  p == None:
            raise Exception("Did not receive any answer")
        print p
        self.response = p
