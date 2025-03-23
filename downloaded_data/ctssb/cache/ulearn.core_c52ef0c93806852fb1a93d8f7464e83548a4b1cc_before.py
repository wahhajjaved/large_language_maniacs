from plone import api
from infrae.rest import REST as REST_BASE
from infrae.rest.interfaces import RESTMethodPublishedEvent
from infrae.rest.components import IRESTComponent
from infrae.rest.interfaces import MethodNotAllowed
from zeam.component import getComponent
from ulearn.core.content.community import CommunityForbiddenAction
from zExceptions import NotFound
from zope.event import notify
from zope.component import queryUtility
from zope.interface import alsoProvides

from plone.registry.interfaces import IRegistry

from maxclient import MaxClient
from mrs.max.browser.controlpanel import IMAXUISettings
import json
import sys
from Acquisition import aq_acquire

_marker = object()
ALLOWED_REST_METHODS = ('GET', 'POST', 'HEAD', 'PUT', 'DELETE')

import logging
logger = logging.getLogger(__name__)

try:
    from plone.protect.interfaces import IDisableCSRFProtection
except:
    DISABLE_CSRF = True
else:
    DISABLE_CSRF = False

class BadParameters(Exception):
    pass


class MissingParameters(Exception):
    pass


class ObjectNotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class Redirect(Exception):
    def __init__(self, location):
        self.location = location


class ApiResponse(object):
    def __init__(self, data, code=200):
        self.code = code
        self.data = data

    @classmethod
    def from_string(cls, message, code=200):
        obj = cls({'message': message}, code)
        return obj


class api_resource(object):
    """
        Decorator to validate ws parameters and format output
    """

    def __init__(self, **settings):
        self.__dict__.update(settings)

    def __call__(self, fun):
        settings = self.__dict__.copy()
        self.required = settings.pop('required', [])
        self.required_roles = settings.pop('required_roles', [])
        self.get_target = settings.pop('get_target', False)
        
	def wrapped(resource, *args):
            response_content = {}
            response_code = 200
            if not DISABLE_CSRF:
                alsoProvides(resource.request, IDisableCSRFProtection)
            try:
                resource.extract_params(required=self.required)
                if self.get_target:
                    resource.lookup_community()
                if self.required_roles:
                    resource.check_roles(obj=resource.target, roles=self.required_roles)

                response = fun(resource, *args)
                response_content = response.data
                response_code = response.code

            except ObjectNotFound as exc:
                response_code = 404
                response_content = {
                    'status_code': response_code,
                    'error_type': 'Object Not Found',
                    'error': exc.args[0]
                }

            except BadParameters as exc:
                response_code = 400
                response_content = {
                    'status_code': response_code,
                    'error_type': 'Bad parameters',
                    'error': exc.args[0]
                }

            except MissingParameters as exc:
                response_code = 400
                response_content = {
                    'status_code': response_code,
                    'error_type': 'Missing parameters',
                    'error': 'Those parameters are missing: {}'.format(', '.join([a for a in exc.args[0]]))
                }

            except Forbidden as exc:
                response_code = 403
                response_content = {
                    'status_code': response_code,
                    'error_type': 'Forbidden',
                    'error': exc.args[0]
                }

            except CommunityForbiddenAction as exc:
                response_code = 403
                response_content = {
                    'status_code': response_code,
                    'error_type': 'Forbidden',
                    'error': exc.args[0]
                }

            except Redirect as exc:
                response_code = 302
                response_content = {
                    'status_code': response_code,
                    'error_type': 'Redirect',
                    'error': 'Redirecting, no such error',
                    'redirecting_to': exc.location
                }
                resource.response.redirect(exc.location)

            except Exception as exc:
                traceback = sys.exc_info()[2]
                log = aq_acquire(resource, '__error_log__', containment=1)
                error_log_url = log.raising((type(exc), exc, traceback))

                # For testing purposes, requests doesn't have environ
                # And a convenient way to see the traceback
                environ = getattr(resource.request, 'environ', {})
                server_name = environ.get('SERVER_NAME', 'testing')
                server_port = environ.get('SERVER_PORT', '8080')
                if server_name == 'testing':
                    import traceback as trbk
                    print trbk.format_exc()

                instance_id = '{}:{}'.format(server_name, server_port)
                response_code = 500

                response_content = {
                    'status_code': response_code,
                    'error_type': 'Internal server error',
                    'error': '{}: {}'.format(type(exc).__name__, exc.message),
                    'error_url': error_log_url,
                    'error_instance': instance_id
                }

            resource.response.setHeader(
                'Content-Type',
                'application/json; charset=utf-8'
            )

            resource.response.setStatus(response_code)
            response_content = json.dumps(response_content, indent=2, sort_keys=True)
            return response_content

        return wrapped


class MethodNotImplemented(Exception):
    """This method is not implemented in this class
    """
    def __init__(self, klass, method):
        self.args = (klass, method)
        self.message = '{}.{}'.format(klass, method)


def queryRESTComponent(specs, args, name=u'', parent=None, id=_marker, placeholder=None):
    """Query the ZCA for a REST component.
    """
    factory = getComponent(specs, IRESTComponent, name, default=None)
    if factory is not None:
        result = factory(*args)
        if result is not None and IRESTComponent.providedBy(result):
            # Set parenting information / for security
            if id is _marker:
                id = name
            result.__name__ = id
            result.__parent__ = parent
            result.__matchdict__ = {}
            result.__matchdict__.update(getattr(parent, '__matchdict__', {}))
            if placeholder is not None:
                result.__matchdict__.update(placeholder)

            return result
    return None

from five import grok


class REST(REST_BASE):
    grok.baseclass()
    """
        Enchanced version of infrae.rest REST class, that can behave like a
        generic url part. To make use of the generic behaviour, derived classes
        need two attributes:

        placeholder_id
        placeholder_type

        the placeholder_type must be the lowercase name of a class in the same
        nesting pattern defined in infrae.rest. The placeholder_id, is the key
        that will be used to store the url part in the class instance
        __matchdict__ object. This dict will accomulate all generic REST
        components in the way.

        if no placeholder_* attributes found, default behaviour will remain.
        Any nested REST class defined with a name trying to be a placeholder
        will be treated as the nestes class.
    """

    target = None

    def browserDefault(self, request):
        """Render the component using a method called the same way
        that the HTTP method name.
        """
        if request.method in ALLOWED_REST_METHODS:
            if hasattr(self, request.method):
                return self, (request.method,)
            else:
                raise MethodNotImplemented(str(self.__class__), request.method)
        raise MethodNotAllowed(request.method)

    def get_max_client(self):
        registry = queryUtility(IRegistry)
        maxui_settings = registry.forInterface(IMAXUISettings)

        maxclient = MaxClient(maxui_settings.max_server, maxui_settings.oauth_server)
        maxclient.setActor(maxui_settings.max_restricted_username)
        maxclient.setToken(maxui_settings.max_restricted_token)

        return maxclient

    def lowerUsersId(self):
        if self.params.get('users', None):
            for user in self.params['users']:
                try:
                    user['id'] = user['id'].lower()
                except:
                    raise BadParameters(user)

    def extract_params(self, required=[]):
        """
            Extract parameters from request and stores them ass class attributes
            Returns false if some required parameter is missing
        """
        required_params = list(required)
        required_params += self.__matchdict__.keys()
        self.params = {}
        self.params.update(self.__matchdict__)
        self.params.update(self.request.form)
        try:
            self.payload = json.loads(self.request['BODY'])
        except:
            self.payload = self.request.form
        else:
            self.params.update(self.payload)

        self.lowerUsersId()

        # Return False if param not found or empty
        for param_name in required_params:
            parameter_missing = param_name not in self.params
            parameter_empty = self.params.get(param_name, None) in [[], {}, None, '']
            if parameter_missing or parameter_empty:
                raise MissingParameters(set(required_params) - set(self.params.keys()))

        return True

    def check_roles(self, obj=None, roles=[]):
        allowed = False
        memberdata = api.user.get_current()
        user_roles = memberdata.getRoles()
        if obj:
           local_roles = obj.__ac_local_roles__.get(memberdata.id, [])
           user_roles = list(set(user_roles + local_roles))
           
        for role in roles:
            if role in user_roles:
                allowed = True

        if not allowed:
            raise Forbidden('You are not allowed to modify this object')

        return allowed

    def lookup_community(self):
        pc = api.portal.get_tool(name='portal_catalog')
        result = pc.searchResults(community_hash=self.params['community'])

        if not result:
            # Fallback search by gwuuid
            result = pc.searchResults(gwuuid=self.params['community'])

            if not result:
                # Not found either by hash nor by gwuuid
                error_message = 'Community with has {} not found.'.format(self.params['community'])
                logger.error(error_message)
                raise ObjectNotFound(error_message)

        self.target = result[0].getObject()

    def check_permission(self, obj, permission):
        if not api.user.has_permission(permission, obj):
            self.response.setStatus(401)
            return self.json_response(dict(error='You are not allowed to modify this object',
                                           status_code=401))

        return True

    def publishTraverse(self, request, name):
        """You can traverse to a method called the same way that the
        HTTP method name, or a sub view
        """
        overriden_method = request.getHeader('X-HTTP-Method-Override', None)
        is_valid_overriden_method = overriden_method in ['DELETE', 'PUT']
        is_POST_request = request.method.upper() == 'POST'
        is_valid_override = is_valid_overriden_method and is_POST_request
        request_method = overriden_method if is_valid_override else request.method

        if request_method != request.method:
            request.method = request_method

        if name in ALLOWED_REST_METHODS and name == request.method:
            if hasattr(self, request_method):
                notify(RESTMethodPublishedEvent(self, name))
                return getattr(self, request_method)

        view = queryRESTComponent(
            (self, self.context),
            (self.context, request),
            name=name,
            parent=self)

        placeholder = getattr(self, 'placeholder_type', None)

        if view is None and placeholder is not None:
            placeholder_id = getattr(self, 'placeholder_id')
            view = queryRESTComponent(
                (self, self.context),
                (self.context, request),
                name=placeholder,
                parent=self,
                placeholder={placeholder_id: name}
            )
        if view is None:
            raise NotFound(name)
        return view
