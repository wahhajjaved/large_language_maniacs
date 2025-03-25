# encoding: utf-8

#*    dslib - Python library for Datove schranky
#*    Copyright (C) 2009-2010  CZ.NIC, z.s.p.o. (http://www.nic.cz)
#*
#*    This library is free software; you can redistribute it and/or
#*    modify it under the terms of the GNU Library General Public
#*    License as published by the Free Software Foundation; either
#*    version 2 of the License, or (at your option) any later version.
#*
#*    This library is distributed in the hope that it will be useful,
#*    but WITHOUT ANY WARRANTY; without even the implied warranty of
#*    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#*    Library General Public License for more details.
#*
#*    You should have received a copy of the GNU Library General Public
#*    License along with this library; if not, write to the Free
#*    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#*

"""
This is the main part of the dslib library - a client object resides here
which is responsible for all communication with the DS server..
"""

# standard library imports
# suds does not work properly without this
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import base64
import logging
import re

# local imports
import pkcs7.pkcs7_decoder
import pkcs7.verifier
import pkcs7.tstamp_helper
from sudsds.client import Client as SudsClient
from sudsds.transport.http import HttpAuthenticated, HttpTransport
import exceptions
from ds_exceptions import DSException
import models
from properties.properties import Properties as props
import certs.cert_loader


class Dispatcher(object):
  """
  DS splits its functionality between several parts. These have different URLs
  as well as different WSDL files.
  Dispatcher is a simple client that handles one of these parts
  """

  # this is a map between a signed version of a method and its
  # normal counterpart which should be used to decode the content after it's
  # unpacked from pkcs7 
  SIGNED_TO_DECODING_METHOD = {"SignedMessageDownload":"MessageDownload",
                               "SignedSentMessageDownload":"MessageDownload",
                               "GetSignedDeliveryInfo":"GetDeliveryInfo",}

  def __init__(self, ds_client, wsdl_url, soap_url=None, proxy=None,
               server_certs=None):
    """proxy can be a string 'hostname:port' or None"""
    self.ds_client = ds_client # this is a Client instance; username, password, etc. will be take from it
    self.wsdl_url = wsdl_url
    self.soap_url = soap_url # if None, default from WSDL will be used
    self.proxy = proxy
    transport_args = dict(ca_certs=server_certs,
                          cert_verifier=Client.CERT_VERIFIER,
                          username=self.ds_client.login,
                          password=self.ds_client.password
                          )
    transport_class = HttpAuthenticated # for Basic HTTP authentication
    if self.ds_client.login_method == "certificate":
      transport_args.update(client_certfile = self.ds_client.client_certfile,
                            client_keyfile = self.ds_client.client_keyfile)
      transport_class = HttpTransport # we do not need Basic authentication
                                      # - we use certs
    if self.proxy:
      transport_args.update(proxy={'https':self.proxy})
    transport = transport_class(**transport_args)
    if not self.soap_url:
      self.soap_client = SudsClient(self.wsdl_url, transport=transport)
    else:
      self.soap_client = SudsClient(self.wsdl_url, transport=transport, location=self.soap_url)
    
  def __getattr__(self, name):
    def _simple_wrapper(method):
      def f(*args, **kw):
        reply = method(*args, **kw)
        status = self._extract_status(reply)
        data = getattr(reply, name)
        return Reply(status, data)
      return f
    return _simple_wrapper(getattr(self.soap_client.service, name))

  @classmethod
  def _extract_status(self, reply):
    if hasattr(reply, "dmStatus"):
      status = models.dmStatus(reply.dmStatus)
    elif hasattr(reply, "dbStatus"):
      status = models.dbStatus(reply.dbStatus)
    else:
      raise ValueError("Neither dmStatus, nor dbStatus found in reply:\n%s" % reply)
    return status


  def _handle_dmrecords_and_status_response(self, method):
    reply = method()
    status = self._extract_status(reply)
    # the following is a hack around a bug in the suds library that
    # does not properly create a list when only one object is present
    if reply.dmRecords == "":
      result = []
    else:
      messages = reply.dmRecords.dmRecord
      if type(messages) != list:
        result = [models.Message(messages)]
      else:
        result = [models.Message(message) for message in messages]
    return Reply(status, result)
    
  def GetListOfSentMessages(self):
    method = self.soap_client.service.GetListOfSentMessages
    return self._handle_dmrecords_and_status_response(method)

  def GetListOfReceivedMessages(self):
    method = self.soap_client.service.GetListOfReceivedMessages
    return self._handle_dmrecords_and_status_response(method)

  def MessageEnvelopeDownload(self, msgid):
    reply = self.soap_client.service.MessageEnvelopeDownload(msgid)
    if hasattr(reply, 'dmReturnedMessageEnvelope'):
      message = models.Message(reply.dmReturnedMessageEnvelope)
    else:
      message = None
    return Reply(self._extract_status(reply), message)

  def MessageDownload(self, msgid):
    reply = self.soap_client.service.MessageDownload(msgid)
    if hasattr(reply, 'dmReturnedMessage'):
      message = models.Message(reply.dmReturnedMessage)
    else:
      message = None
    return Reply(self._extract_status(reply), message)

  def DummyOperation(self):
    reply = self.soap_client.service.DummyOperation()
    assert reply == None
    return Reply(None, None)

  def FindDataBox(self, info):
    """info = dbOwnerInfo instance"""
    soap_info = self.soap_client.factory.create("dbOwnerInfo")
    info.copy_to_soap_object(soap_info)
    reply = self.soap_client.service.FindDataBox(soap_info)
    if reply.dbResults:
      ret_infos = reply.dbResults.dbOwnerInfo
      if type(ret_infos) != list:
        ret_infos = [ret_infos]
      result = [models.dbOwnerInfo(ret_info) for ret_info in ret_infos]
    else:
      result = []
    return Reply(self._extract_status(reply), result)

  def CreateMessage(self, envelope, files):
    """returns message id as reply.data"""
    soap_envelope = self.soap_client.factory.create("tMessageEnvelopeSub")
    envelope.copy_to_soap_object(soap_envelope)
    soap_files = self.soap_client.factory.create("dmFiles")
    for f in files:
      soap_file = self.soap_client.factory.create("dmFile")
      f.copy_to_soap_object(soap_file)
      soap_files.dmFile.append(soap_file)
    reply = self.soap_client.service.CreateMessage(soap_envelope, soap_files)
    if hasattr(reply,"dmID"):
      dmID = reply.dmID
    else:
      dmID = None
    return Reply(self._extract_status(reply), dmID)
    
  def GetOwnerInfoFromLogin(self):
    reply = self.soap_client.service.GetOwnerInfoFromLogin()
    if hasattr(reply, 'dbOwnerInfo'):
      message = models.dbOwnerInfo(reply.dbOwnerInfo)
    else:
      message = None
    return Reply(self._extract_status(reply), message)

  def GetUserInfoFromLogin(self):
    reply = self.soap_client.service.GetUserInfoFromLogin()
    if hasattr(reply, 'dbUserInfo'):
      message = models.dbUserInfo(reply.dbUserInfo)
    else:
      message = None
    return Reply(self._extract_status(reply), message)
 
  def _verify_der_msg(self, der_message):
    '''
    Verifies message in DER format (decoded b64 content of dmSIgnature)
    '''    
    verification_result = pkcs7.verifier.verify_msg(der_message)
    if verification_result:        
        logging.debug("Message verified")
    else:
        logging.debug("Verification of pkcs7 message failed")
    return verification_result
    
  def _xml_parse_msg(self, string_msg, method):
    '''
    Parses content of pkcs7 message. Outputs xml document.
    '''
    import sudsds.sax.parser as p
    parser = p.Parser()
    soapbody = parser.parse(string = string_msg)
    meth_name = method.name
    decoding_method = Dispatcher.SIGNED_TO_DECODING_METHOD.get(meth_name, None)
    if not decoding_method:
      raise Exception("Decoding of XML result of '%s' is not supported." % meth_name)
    internal_method = getattr(self.soap_client.service, decoding_method).method  
    document = internal_method.binding.input
    soapbody = document.multiref.process(soapbody)
    nodes = document.replycontent(internal_method, soapbody)
    rtypes = document.returned_types(internal_method)
    if len(rtypes) > 1:
        result = document.replycomposite(rtypes, nodes)
        return result
    if len(rtypes) == 1:
        if rtypes[0].unbounded():
            result = document.replylist(rtypes[0], nodes)
            return result
        if len(nodes):
            unmarshaller = document.unmarshaller()
            resolved = rtypes[0].resolve(nobuiltin=True)
            result = unmarshaller.process(nodes[0], resolved)
            return result
    return None
    

  def _prepare_PKCS7_data(self, decoded_msg): 
    '''
    Creates objects representing pkcs7 message.
    '''   
    pkcs_data = models.PKCS7_data(decoded_msg)
    return pkcs_data
  
  def _generic_get_signed(self, der_encoded, method):
    '''
    "Base" of methods downloading signed versions of messages and
    delivery information.
    Returns tuple xml_document, pkcs7_data, verified flag 
    method is either a SOAP method or its name as string   
    '''
    if type(method) in (str, unicode):
      method = getattr(self.soap_client.service, method)
    # decode DER encoding
    decoded_msg = pkcs7.pkcs7_decoder.decode_msg(der_encoded)    
    if props.VERIFY_MESSAGE:
      # verify the message
      verified = self._verify_der_msg(decoded_msg)
    else:
      verified = None            
    # prepare PKCS7 to supply to the Message
    pkcs_data = self._prepare_PKCS7_data(decoded_msg)
    # extract sent message from pkcs7 document
    str_msg = pkcs_data.message
    # parse string xml to create xml document
    xml_document = self._xml_parse_msg(str_msg, method.method)
    return xml_document, pkcs_data, verified
  

  
  def _mark_invalid_certificates(self, message, bad_certs_ids):
    '''
    In messages's pkcs7 data mark invalid certificates       
    (sets their 'is_cerified' attribute to False)
    bad_certs_ids is array of tuples with issuer name and cert sn
    '''
    import certs.cert_finder as finder
    msg_certs = message.pkcs7_data.certificates
    for cert in bad_certs_ids:
      found = finder.find_cert_by_iss_sn(msg_certs, cert[0], cert[1])
      if found:
        found.is_verified = False
          
      
  def _signed_msg_download(self, ws_name, msg_id):
    '''
    Common method for downloading signed message (sent or received)
    '''
    method = getattr(self.soap_client.service, ws_name)
    if (method is None):
        raise Exception("Unknown method: %s" % ws_name)
    reply = method.__call__(msg_id)
    status = self._extract_status(reply)
    if not reply.dmSignature:
      return Reply(status, None)
    message = self.signature_to_message(reply.dmSignature, method)
    return Reply(status, message, raw_data=reply.dmSignature)
  
  def signature_to_message(self, signature, method):
    """
    method is either a SOAP method or its name as string
    """
    if type(method) in (str, unicode):
      method = getattr(self.soap_client.service, method)
    der_encoded = base64.b64decode(signature) 
    xml_document, pkcs_data, verified  = self._generic_get_signed(der_encoded, method)
    if method.method.name in ("SignedSentMessageDownload","SignedMessageDownload"):
      message = models.Message(xml_document.dmReturnedMessage)
    else:
      raise Exception("Unsupported signed method '%s'" % method.method.name) 
    message.pkcs7_data = pkcs_data
    if (verified):
        message.is_verified = True
    return message

  def _check_timestamp(self, message):
    '''
    Checks message timestamp - parses and verifies it. TimeStampToken
    is attached to the message.
    Method returns flag that says, if the content of messages's dmHash element
    is the same as the message imprint
    '''
    # if message had dmQtimestamp, parse and verify it
    if message.dmQTimestamp is not None:
        tstamp_verified, tstamp = pkcs7.tstamp_helper\
                                        .parse_qts(message.dmQTimestamp,\
                                                   verify=props.VERIFY_TIMESTAMP)
        
        # certificate verification (if properties say so)
        if props.VERIFY_CERTIFICATE:
          for cert in tstamp.asn1_certificates:
            c = CertificateManager.get_certificate(cert)
            if not tstamp.certificates_contain(c.tbsCertificate.serial_number):
              tstamp.certificates.append(c)            
        
        message.tstamp_verified = tstamp_verified
        message.tstamp_token = tstamp
        
        imprint = tstamp.msgImprint.imprint
        imprint = base64.b64encode(imprint)
    
        hashFromMsg = message.dmHash.value
    
        if hashFromMsg == imprint:
            logging.info("Message imprint in timestamp and dmHash value are the same")
            return True
        else:
            logging.error("Message imprint in timestamp and dmHash value differ!")
            return False

        
  def SignedMessageDownload(self, msgId):
    return self._signed_msg_download("SignedMessageDownload", msgId)
    
  def SignedSentMessageDownload(self, msgId):
    return self._signed_msg_download("SignedSentMessageDownload", msgId)
    
  def GetSignedDeliveryInfo(self, msgId):
    method = self.soap_client.service.GetSignedDeliveryInfo
    reply = method(msgId)
    der_encoded = base64.b64decode(reply.dmSignature)  
    xml_document, pkcs_data, verified  = self._generic_get_signed(der_encoded, method)
    # create Message instance to return 
    message = models.Message(xml_document.dmDelivery)        
    message.pkcs7_data = pkcs_data
    if (verified):
        message.is_verified = True
    
    '''
    if props.VERIFY_CERTIFICATE:
      # set verified value of message certificates    
      for c in message.pkcs7_data.certificates:
        c.is_verified = True
      if len(bad_certs) > 0:
        self._mark_invalid_certificates(message, bad_certs) 
    '''
    return Reply(self._extract_status(reply), message)

  def GetDeliveryInfo(self, msgId):
    reply = self.soap_client.service.GetDeliveryInfo(msgId)
    if hasattr(reply, 'dmDelivery'):
      message = models.Message(reply.dmDelivery)
    else:
      message = None
    return Reply(self._extract_status(reply), message)
  
  def GetPasswordInfo(self):
    reply = self.soap_client.service.GetPasswordInfo()    
    # minOccur = 0, maxOccur = 1
    expiry_date = None
    if hasattr(reply, 'pswExpDate'):
      expiry_date = reply.pswExpDate    
    return Reply(self._extract_status(reply), expiry_date)
  
  def ChangeISDSPassword(self, old_pass, new_pass):
    reply = self.soap_client.service.ChangeISDSPassword(old_pass, new_pass) 
    status = models.dbStatus(reply)   
    return Reply(status, None)

    
class Client(object):

  cur_path = os.path.dirname(os.path.abspath(__file__))
  if cur_path.startswith("/"):
    WSDL_URL_BASE = 'file://%s/wsdl/' % cur_path
  else:
    WSDL_URL_BASE = 'file:///%s/wsdl/' % cur_path
    
  attr2dispatcher_name = {"GetListOfSentMessages": "info",
                          "GetListOfReceivedMessages": "info",
                          "MessageDownload": "operations",
                          "MessageEnvelopeDownload": "info",
                          "DummyOperation": "operations",
                          "GetDeliveryInfo": "info",
                          "FindDataBox": "search",
                          "CreateMessage": "operations",
                          "SignedMessageDownload" : "operations",
                          "SignedSentMessageDownload" : "operations",
                          "GetSignedDeliveryInfo" : "info",
                          "GetPasswordInfo" : "access",
                          "GetOwnerInfoFromLogin": "access",
                          "GetUserInfoFromLogin": "access",
                          "ChangeISDSPassword" : "access",
                          "signature_to_message": "operations",
                          }

  dispatcher_name2config = {"info": {"wsdl_name": "dm_info.wsdl",
                                     "soap_url_end": "dx"},
                            "operations": {"wsdl_name": "dm_operations.wsdl",
                                           "soap_url_end": "dz"},
                            "search": {"wsdl_name": "db_search.wsdl",
                                       "soap_url_end": "df"},
                            "access": {"wsdl_name": "db_access.wsdl",
                                       "soap_url_end": "DsManage"},
                            }
  test2soap_url = {True: "https://www.czebox.cz/",
                   False: "https://www.mojedatovaschranka.cz/"}

  login_method2url_part = {"username": "DS",
                           "certificate": "cert/DS",
                           }

  def __init__(self, login=None, password=None, soap_url=None, test_environment=None,
               login_method="username", proxy=None, server_certs=None,
               client_certfile=None, client_keyfile=None):
    """
    if soap_url is not given and test_environment is given, soap_url will be
    infered from the value of test_environment based on what is set in test2soap_url;
    if neither soap_url not test_environment is provided, it will be empty and
    the dispatcher will use the value from WSDL;
    if soap_url id used, it will be used without regard to test_environment value
    proxy can be a string 'hostname:port' or None or -1 for automatic
    detection using the urllib2 library
    server_certs - path to a certificate chain used for verification of server
    certificate, if None, no check on server certificate is performed
    client_keyfile, client_certfile - are used with login_method 'certificate'
    """
    self.login = login
    self.password = password
    self.client_keyfile = client_keyfile
    self.client_certfile = client_certfile
    self.login_method = login_method  
    # check authentication data
    if self.login_method == "certificate":
      if not self.client_certfile:
        raise ValueError("You must supply client_certfile when using\
 'certificate' login method")
      if not self.client_keyfile:
        raise ValueError("You must supply client_keyfile when using\
 'certificate' login method")
    elif self.login_method == "username":
      if not self.login:
        raise ValueError("You must supply a username when using\
 'username' login method")
      if not self.password:
        raise ValueError("You must supply a password when using\
 'username' login method")
    if soap_url:
      self.soap_url = soap_url
    elif test_environment != None:
      self.soap_url = Client.test2soap_url[test_environment]
    else:
      self.soap_url = None
    self.test_environment = test_environment
    self._dispatchers = {}
    self.proxy = proxy
    self.server_certs = server_certs


  def __getattr__(self, name):
    """called when the user tries to access attribute or method;
    it looks if some dispatcher supports it and then returns the
    corresponding dispatchers method."""
    if name not in Client.attr2dispatcher_name:
      raise AttributeError("Client object does not have an attribute named '%s'"%name)
    dispatcher_name = Client.attr2dispatcher_name[name]
    dispatcher = self.get_dispatcher(dispatcher_name)
    return getattr(dispatcher, name)


  def get_dispatcher(self, name):
    """returns a dispatcher object based on its name;
    creates the dispatcher if it does not exist yet"""
    if name not in self._dispatchers:
      if name in Client.dispatcher_name2config:
        return self._create_dispatcher(name)
      else:
        raise Exception("Wrong or unsupported dispatcher name '%s'" % name)
    else:
      return self._dispatchers[name]


  def _create_dispatcher(self, name):
    """creates a dispatcher based on it name;
    config for a name is present in Client.dispatcher_name2config
    """
    config = Client.dispatcher_name2config[name]
    this_soap_url = None
    if self.soap_url:
      if self.soap_url.endswith("/"):
        this_soap_url = self.soap_url
      else:
        this_soap_url = self.soap_url + "/"
      this_soap_url += Client.login_method2url_part[self.login_method] + "/" + config['soap_url_end']
    dis = Dispatcher(self, Client.WSDL_URL_BASE+config['wsdl_name'], soap_url=this_soap_url,\
                      proxy=self.get_real_proxy(), server_certs=self.server_certs)
    self._dispatchers[name] = dis
    return dis

  def get_real_proxy(self):
    return self.proxy_to_real_proxy(self.proxy)

  @classmethod
  def proxy_to_real_proxy(cls, proxy):
    """interpret the proxy setting to obtain a real name and port or None"""
    if proxy == None:
      return None
    elif proxy == -1:
      import urllib2
      return urllib2.getproxies().get('https',None) 
    else:
      return proxy
    
  @classmethod
  def verify_server_certificate(cls, cert):
    """
    this is given to suds HTTPTransport augmented to checking certificates
    it should return True when certificate passes and False when not
    - we check mainly the name for which the certificate was issued
    """
    ok = False
    for parts in cert['subject']:
      # somehow 1-member tuples are used so we cycle again...
      for name, value in parts:
        if name == "organizationName" and \
           re.search(u"Ministerstv[oa] vnitra ČR", value, re.IGNORECASE):
          ok = True
          break
    return ok 

  # set this to None to omit checks or to custom function to allow custom checks
  CERT_VERIFIER = verify_server_certificate
   

class Reply(object):
  """represent a reply from the SOAP server"""

  def __init__(self, status, data, **kw):
    self.status = status
    self.data = data
    self.additional_data = {}
    self.additional_data.update(kw)

  def __unicode__(self):
    return "Reply: StatusCode: %s; DataType: %s" % (self.status.dmStatusCode, data.__class__.__name__)

  def add_addtional_data(self, **kw):
    self.add_addtional_data.update(kw)
