import json
import base64
import httplib2
import binascii
from zope.interface import Interface
from zope.interface import Attribute
from zope.interface import implementer
from paste.httpheaders import AUTHORIZATION
from paste.httpheaders import WWW_AUTHENTICATE
from pyramid.security import authenticated_userid
from pyramid.security import Everyone
from pyramid.security import Authenticated
from pyramid.interfaces import IAuthenticationPolicy
from pyramid.httpexceptions import HTTPUnauthorized
from defpage.lib.exceptions import ServiceCallError

def authenticated(func):
    def wrapper(req):
        if not authenticated_userid(req):
            raise HTTPUnauthorized
        return func(req)
    return wrapper

class User:

    authenticated = False
    userid = None
    email = None

def get_user_info(request, cookie_name, sessions_url):
    user = User()
    key = request.cookies.get(cookie_name)
    if key:
        h = httplib2.Http()
        r, c = h.request(sessions_url + key)
        if r.status == 200:
            info = json.loads(c)
            user.userid = info["user_id"]
            user.email = info["email"]
            user.authenticated = True
        elif r.status != 404:
            raise ServiceCallError
    return user

@implementer(IAuthenticationPolicy)
class UserInfoAuthenticationPolicy(object):

    def authenticated_userid(self, request):
        return request.user.userid

    def unauthenticated_userid(self, request):
        return None

    def effective_principals(self, request):
        if request.user.authenticated:
            return [request.user.user_id, Authenticated, Everyone]
        return [Everyone]

    def remember(self, request, principal, email):
        return []

    def forget(self, request):
        return []

def _get_basicauth_credentials(request):
    authorization = AUTHORIZATION(request.environ)
    try:
        authmeth, auth = authorization.split(' ', 1)
    except ValueError: # not enough values to unpack
        return None
    if authmeth.lower() == 'basic':
        try:
            auth = auth.strip().decode('base64')
        except binascii.Error: # can't decode
            return None
        try:
            login, password = auth.split(':', 1)
        except ValueError: # not enough values to unpack
            return None
        return {'login':login, 'password':password}
    return None

@implementer(IAuthenticationPolicy)
class BasicAuthenticationPolicy(object):

    def __init__(self, check, realm='Realm'):
        self.check = check
        self.realm = realm

    def authenticated_userid(self, request):
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return None
        userid = credentials['login']
        if self.check(credentials, request) is not None: # is not None!
            return userid

    def effective_principals(self, request):
        effective_principals = [Everyone]
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return effective_principals
        userid = credentials['login']
        groups = self.check(credentials, request)
        if groups is None: # is None!
            return effective_principals
        effective_principals.append(Authenticated)
        effective_principals.append(userid)
        effective_principals.extend(groups)
        return effective_principals

    def unauthenticated_userid(self, request):
        creds = _get_basicauth_credentials(request)
        if creds is not None:
            return creds['login']
        return None

    def remember(self, request, principal, **kw):
        return []

    def forget(self, request):
        head = WWW_AUTHENTICATE.tuples('Basic realm="%s"' % self.realm)
        return head
