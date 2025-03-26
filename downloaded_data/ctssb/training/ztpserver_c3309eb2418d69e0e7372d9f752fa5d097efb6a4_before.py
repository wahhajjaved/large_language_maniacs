#
# Copyright (c) 2014, Arista Networks, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#   Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
#   Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
#   Neither the name of Arista Networks nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# pylint: disable=W0622,W0402,W0613,W0142,R0201, E1103
#

import logging
import os
import routes
import urlparse

from string import Template
from webob.static import FileApp

import ztpserver.config
import ztpserver.neighbordb

from ztpserver.wsgiapp import WSGIController, WSGIRouter

from ztpserver.neighbordb import create_node, load_pattern

from ztpserver.repository import create_repository
from ztpserver.repository import FileObjectNotFound, FileObjectError
from ztpserver.constants import HTTP_STATUS_NOT_FOUND, HTTP_STATUS_CREATED
from ztpserver.constants import HTTP_STATUS_BAD_REQUEST, HTTP_STATUS_CONFLICT
from ztpserver.constants import HTTP_STATUS_INTERNAL_SERVER_ERROR
from ztpserver.constants import CONTENT_TYPE_JSON, CONTENT_TYPE_PYTHON
from ztpserver.constants import CONTENT_TYPE_YAML, CONTENT_TYPE_OTHER

DEFINITION_FN = 'definition'
STARTUP_CONFIG_FN = 'startup-config'
PATTERN_FN = 'pattern'
NODE_FN = '.node'
ATTRIBUTES_FN = 'attributes'
BOOTSTRAP_CONF = 'bootstrap.conf'

log = logging.getLogger(__name__)    # pylint: disable=C0103


class ValidationError(Exception):
    ''' Base exception class for :py:class:`Pattern` '''
    pass


class BaseController(WSGIController):

    FOLDER = None

    def __init__(self, **kwargs):
        data_root = ztpserver.config.runtime.default.data_root
        self.repository = create_repository(data_root)
        super(BaseController, self).__init__()

    def expand(self, *args, **kwargs):
        ''' Returns an expanded file path relative to data_root '''

        file_path = os.path.join(*args)
        folder = kwargs.get('folder', self.FOLDER)
        return os.path.join(folder, file_path)

    def http_bad_request(self, *args, **kwargs):
        ''' Returns HTTP 400 Bad Request '''
        return dict(body='', content_type='text/html',
                    status=HTTP_STATUS_BAD_REQUEST)

    def http_not_found(self, *args, **kwargs):
        ''' Returns HTTP 404 Not Found '''

        return dict(body='', content_type='text/html',
                    status=HTTP_STATUS_NOT_FOUND)

    def http_internal_server_error(self, *args, **kwargs):
        ''' Returns HTTP 500 Internal server error '''

        return dict(body='', content_type='text/html',
                    status=HTTP_STATUS_INTERNAL_SERVER_ERROR)


class FilesController(BaseController):

    FOLDER = 'files'

    def __repr__(self):
        return 'FilesController(folder=%s)' % self.FOLDER

    def show(self, request, resource, **kwargs):
        ''' Handles GET /files/{resource} '''
        log.debug('%s\nResource: %s\n' % (request, resource))

        try:
            urlvars = request.urlvars
            if urlvars.get('format') is not None:
                resource += '.%s' % urlvars.get('format')
            file_path = self.expand(resource)
            filename = self.repository.get_file(file_path).name
            return FileApp(filename, content_type=CONTENT_TYPE_OTHER)
        except FileObjectNotFound as err:
            log.error('File %s not found (%s)' % (resource, err))
            return self.http_not_found()


class ActionsController(BaseController):

    FOLDER = 'actions'

    def __repr__(self):
        return 'ActionsController(folder=%s)' % self.FOLDER

    def show(self, request, resource, **kwargs):
        ''' Handles GET /actions/{resource} '''
        log.debug('%s\nResource: %s\n' % (request, resource))

        try:
            file_path = self.expand(resource)
            body = self.repository.get_file(file_path).read(CONTENT_TYPE_PYTHON)
            return dict(body=body, content_type=CONTENT_TYPE_PYTHON)
        except FileObjectNotFound as err:
            log.error('File %s not found (%s)' % (resource, err))
            return self.http_not_found()


class NodesController(BaseController):

    FOLDER = 'nodes'

    def __repr__(self):
        return 'NodesController(folder=%s)' % self.FOLDER

    def create(self, request, **kwargs):
        """ Handle the POST /nodes request

        The create method will handle in incoming POST request from the node
        and determine if the node already exists or not.  If the node
        does not exist, then the node will be created based on the
        request body.

        Args:
            request (webob.Request): the request object from WSGI

        Returns:
            A dict as the result of the state machine which is used to
            create a WSGI response object.

        """
        log.debug('%s\n' % request)

        try:
            node = create_node(request.json)
        except Exception as err:       # pylint: disable=W0703
            log.error('Unable to create node: %s (request=%s)' % (err, request))
            response = self.http_bad_request()
            return self.response(**response)

        node_id = node.identifier()
        if not node_id:
            log.error('Missing node identifier: %s (request=%s)' % 
                      (node, request))
            response = self.http_bad_request()
            return self.response(**response)

        return self.fsm('node_exists', request=request, 
                        node=node, node_id=node_id)

    def show(self, request, resource, *args, **kwargs):
        """ Handle the GET /nodes/{resource} request

        Args:
            request (webob.Request): the request object from WSGI
            resource (str): the resource being requested

        Returns:
            A dict as the result of the state machine which is used to
            create a WSGI response object.

        """
        log.debug('%s\nResource: %s\n' % (request, resource))

        node_id = resource.split('/')[0]
        try:
            fobj = self.repository.get_file(self.expand(resource, NODE_FN))
            node = fobj.read(CONTENT_TYPE_JSON)
        except Exception as err:           # pylint: disable=W0703
            log.error('%s: unable to read file resource %s: %s' % 
                      (node_id, resource, err))
            response = self.http_bad_request()
            return self.response(**response)

        return self.fsm('get_definition', resource=resource, 
                        node=node, node_id=node_id)

    def get_config(self, request, resource, **kwargs):
        log.debug('%s: node resource GET request: \n%s\n' % 
                  (resource, request))

        response = dict()
        try:
            filename = self.expand(resource, STARTUP_CONFIG_FN)
            response['body'] = self.repository.get_file(filename).read()
            response['content_type'] = CONTENT_TYPE_OTHER
        except FileObjectNotFound as err:
            log.error('Missing startup-config file %s: %s' % 
                      (filename, err))
            raise
        return (response, None)

    def put_config(self, *args, **kwargs):
        log.debug('%s: node resource PUT request: \n%s\n' % 
                  (kwargs['resource'], kwargs['request']))

        response = dict()
        try:
            body = str(kwargs['request'].body)
            content_type = str(kwargs['request'].content_type)
            filename = self.expand(kwargs['resource'], STARTUP_CONFIG_FN)
            fobj = self.repository.get_file(filename)
        except FileObjectNotFound:
            log.debug('File not found: %s - adding it' % filename)
            fobj = self.repository.add_file(filename)
        finally:
            fobj.write(body, content_type)
        return (response, None)

    def fsm(self, state, **kwargs):
        ''' Execute the FSM for the request '''

        log.debug('%s: running %s' % (kwargs['node_id'], state))
        response = dict()
        try:
            while state != None:
                method = getattr(self, state)
                prev_state = state
                (response, state) = method(response, **kwargs)
        except ValidationError:            # pylint: disable=W0703
            log.error('%s: validation error in %s' % 
                      (kwargs['node_id'], prev_state))
            response = self.http_bad_request()
        except Exception as err:            # pylint: disable=W0703
            log.error('%s: error in %s: %s' % 
                      (kwargs['node_id'], prev_state, err))
            response = self.http_bad_request()

        log.debug('%s: response to %s: %s' % 
                  (kwargs['node_id'], prev_state, response))
        return response                     # pylint: disable=W0150

    def node_exists(self, response, *args, **kwargs):
        """ Checks if the node already exists and determines the next state

        This method will check for the existence of the node in the
        repository based on the node_id.  The node_id keyword is pulled
        from the kwargs dict.

        Args:
            response (dict): the response object being constructed
            kwargs (dict): arbitrary keyword arguments

        Returns:
            A tuple that includes the updated response object and the
            next state to transition to.  If the node already exists
            in the repository with a valid definition or startup-config,
            then the next state is 'dump_node' otherwise the next state
            is 'post_config'

        """
        next_state = 'post_config'
        node_id = kwargs.get('node_id')

        if self.repository.exists(self.expand(node_id, DEFINITION_FN)) or \
           self.repository.exists(self.expand(node_id, STARTUP_CONFIG_FN)):
            response['status'] = HTTP_STATUS_CONFLICT
            next_state = 'dump_node'

        return (response, next_state)

    def dump_node(self, response, *args, **kwargs):
        """ Writes the contents of the node to the repository

        Args:
            response (dict): the response object being constructed
            kwargs (dict): arbitrary keyword arguments

        Returns:
            a tuple of response object and next state.  The next state is
            'set_location'

        """

        try:
            node = kwargs.get('node')
            node_id = kwargs.get('node_id')
            contents = node.serialize()
            filename = self.expand(node_id, NODE_FN)
            fobj = self.repository.get_file(filename)
        except FileObjectNotFound:
            fobj = self.repository.add_file(filename)
        finally:
            fobj.write(contents, CONTENT_TYPE_JSON)
        return (response, 'set_location')

    def post_config(self, response, *args, **kwargs):
        """ Writes the nodes startup config file if found in the request

        Args:
            response (dict): the response object being constructed
            kwargs (dict): arbitrary keyword arguments

        Returns:
            a tuple of response object and next state.  If a config key
            was found in the request, the next state is 'set_location'.
            If not, the next state is 'post_node'.

        """

        if 'config' not in kwargs['request'].json:
            log.warning('Config attribute missing from request: %s' %
                        kwargs['request'])
            next_state = 'post_node'
        else:
            config = kwargs['request'].json['config']
            node_id = kwargs['node_id']

            self.repository.add_folder(self.expand(node_id))

            config_fn = self.expand(node_id, STARTUP_CONFIG_FN)
            self.repository.add_file(config_fn).write(config)

            response['status'] = HTTP_STATUS_CREATED
            next_state = 'set_location'

        return (response, next_state)

    def post_node(self, response, *args, **kwargs):
        """ Checks topology validation matches and writes node specific files

        This method will attempt to match the current node against the
        defined topology.  If a match is found, then the pattern matched
        and definition (defined in the pattern) are written to the nodes
        folder in the repository and the response status is set to HTTP
        201 Created.

        Args:
            response (dict): the response object being constructed
            kwargs (dict): arbitrary keyword arguments

        Returns:
            a tuple of response object and next state.  The next state
            is 'dump_node'

        Raises:
            If a match is not found, then a log message is created and
            an IndexError is raised.  If the node does not already
            exist in the repository, then a log message is created and a
            FileObjectNotFound exception is raised
            """
        try:
            node = kwargs['node']
            node_id = kwargs['node_id']

            neighbordb = ztpserver.neighbordb.load_neighbordb(node_id)
            # pylint: disable=E1103
            matches = neighbordb.match_node(node)
            log.info('Node matched %d pattern(s)', len(matches))
            match = matches[0]

            definition_url = self.expand(match.definition, folder='definitions')
            fobj = self.repository.get_file(definition_url)
            definition = fobj.read(content_type=CONTENT_TYPE_YAML)
            definition_fn = self.expand(node_id, DEFINITION_FN)

            self.repository.add_folder(self.expand(node_id))

            fobj = self.repository.add_file(definition_fn)
            fobj.write(definition, CONTENT_TYPE_YAML)

            pattern_fn = self.expand(node_id, PATTERN_FN)
            fobj = self.repository.add_file(pattern_fn)
            fobj.write(match.serialize(), CONTENT_TYPE_YAML)

            response['status'] = HTTP_STATUS_CREATED
        except IndexError as err:
            log.error('Failed to find pattern match for %s (%s)' % 
                      (node_id, err))
            raise
        except FileObjectNotFound as err:
            log.error('Failed to find file: %s' % err)
            raise
        return (response, 'dump_node')

    def set_location(self, response, *args, **kwargs):
        """ Writes the HTTP Content-Location header

        Args:
            response (dict): the response object being constructed
            kwargs (dict): arbitrary keyword arguments

        Returns:
            a tuple of response object and next state.  The next state is
            None.

        Raises:
            Exception: catches a general exception for logging and then
                       re-raises it
        """
        node_id = kwargs.get('node_id')
        response['location'] = self.expand(node_id)
        return (response, None)

    def get_definition(self, response, *args, **kwargs):
        ''' Reads the node specific definition from disk and stores it in the
        repsonse dict with key `definition`
        '''

        try:
            filename = self.expand(kwargs['resource'], DEFINITION_FN)
            fobj = self.repository.get_file(filename)
            definition = fobj.read(CONTENT_TYPE_YAML)
            response['definition'] = definition
            log.debug('%s: defintion is %s (%s)' % (kwargs['resource'], 
                                                    filename,
                                                    definition['actions']))
        except FileObjectNotFound as err:
            log.warning('%s: missing definition %s: %s' % 
                        (kwargs['resource'], filename, err))
        return (response, 'do_validation')

    def get_startup_config(self, response, *args, **kwargs):
        response['get_startup_config'] = False
        try:
            filename = self.expand(kwargs['resource'], STARTUP_CONFIG_FN)
            self.repository.get_file(filename)
            response['get_startup_config'] = True
            if 'definition' not in response:
                response['definition'] = dict(name='Autogenerated definition',
                                              actions=list())
            response['definition']['actions'].append(\
                ztpserver.neighbordb.replace_config_action(kwargs['resource'],
                                                           STARTUP_CONFIG_FN))
        except FileObjectNotFound as err:
            log.warning('%s: missing startup-config %s: %s' % 
                        (kwargs['resource'], filename, err))

        return (response, 'do_actions')

    def do_actions(self, response, *args, **kwargs):
        actions = response['definition']['actions']
        _actions = list()
        for action in actions:
            always_execute = action.get('always_execute', False)
            if always_execute:
                _actions.append(action)
                log.debug('%s: always_execute action %s included '
                          'in definition' %
                          (kwargs['resource'],  action.get('name')))
            elif not response['get_startup_config']:
                _actions.append(action)
                log.debug('%s: action %s included '
                          'in definition' %
                          (kwargs['resource'],  action.get('name')))
            else:
                log.debug('%s: action %s not included '
                          'in definition' %
                          (kwargs['resource'],  action.get('name')))
        response['definition']['actions'] = _actions
            
        return (response, 'get_attributes')

    def do_validation(self, response, *args, **kwargs):
        config = ztpserver.config.runtime
        if not config.default.disable_topology_validation:
            filename = self.expand(kwargs['resource'], PATTERN_FN)
            fobj = self.repository.get_file(filename)

            pattern = load_pattern(kwargs['resource'], fobj.name)
            if not pattern.match_node(kwargs['node']):
                log.error('%s: node failed pattern validation (%s)' % 
                          (kwargs['resource'], filename))
                raise ValidationError('%s: node failed pattern '
                                      'validation (%s)' %
                                      (kwargs['resource'], filename))
            log.debug('%s: node passed pattern validation (%s)' % 
                      (kwargs['resource'], filename))
        else:
            log.warning('%s: topology validation is disabled' %
                        kwargs['resource'])
        return (response, 'get_startup_config')

    def get_attributes(self, response, *args, **kwargs):
        ''' Reads the resource specific attributes file and stores it in the
        response dict as 'attributes'
        '''
        try:
            filename = self.expand(kwargs['resource'], ATTRIBUTES_FN)
            fileobj = self.repository.get_file(filename)
            attributes = fileobj.read(CONTENT_TYPE_YAML)
            response['attributes'] = attributes
            log.debug('%s: loaded %s attributes from %s' % 
                      (kwargs['resource'], attributes, filename))
        except FileObjectNotFound:
            log.warning('%s: no node specific attributes file' %
                        kwargs['resource'])
            response['attributes'] = dict()

        return (response, 'do_substitution')

    def do_substitution(self, response, *args, **kwargs):
        # pylint: disable=R0914
        definition = response.get('definition')
        attrs = definition.get('attributes', dict())

        nodeattrs = response.get('attributes', dict())

        def lookup(name):
            log.debug('%s: lookup up value for variable %s' % 
                      (kwargs['resource'], name))
            return nodeattrs.get(name, attrs.get(name))

        _actions = list()
        for action in definition['actions']:
            log.debug('%s: processing action %s (variable substitution)' %
                      (kwargs['resource'], action.get('name')))
            _attributes = dict()
            if 'attributes' in action:
                for key, value in action.get('attributes').items():
                    try:
                        update = dict()
                        for _key, _value in value.items():
                            if str(_value).startswith('$'):
                                _value = lookup(_value[1:])
                            update[_key] = _value
                    except AttributeError:
                        if str(value).startswith('$'):
                            value = lookup(value[1:])
                        update = value
                    finally:
                        _attributes[key] = update
            action['attributes'] = _attributes
            _actions.append(action)
        definition['actions'] = _actions
        response['definition'] = definition
        return (response, 'do_resources')

    def do_resources(self, response, *args, **kwargs):
        definition = response['definition']
        node = kwargs.get('node')
        _actions = list()
        for action in definition.get('actions'):
            attrs = action.get('attributes', dict())

            action['attributes'] = \
                ztpserver.neighbordb.resources(attrs, node, kwargs['resource'])
            _actions.append(action)
        definition['actions'] = _actions
        response['definition'] = definition
        return (response, 'finalize_response')

    def finalize_response(self, response, *args, **kwargs):
        _response = dict()
        _response['body'] = response['definition']
        _response['status'] = response.get('status', 200)
        _response['content_type'] = response.get('content_type',
                                                 CONTENT_TYPE_JSON)
        return (_response, None)



class BootstrapController(BaseController):

    DEFAULTCONFIG = {
        'logging': list(),
        'xmpp': dict()
    }

    FOLDER = 'bootstrap'

    def __repr__(self):
        return 'BootstrapController(folder=%s)' % self.FOLDER

    def config(self, request, **kwargs):
        ''' Handles GET /bootstrap/config '''

        try:
            filename = self.expand(BOOTSTRAP_CONF)
            body = self.repository.get_file(filename).read(CONTENT_TYPE_YAML)
            resp = dict(body=body, content_type=CONTENT_TYPE_JSON)
        except FileObjectNotFound:
            log.warning('Bootstrap config file not found - using defaults')
            body = self.DEFAULTCONFIG
            resp = dict(body=body, content_type=CONTENT_TYPE_JSON)
        except FileObjectError as err:
            log.error('Failed to read bootstrap config file: %s' % err)
            resp = self.http_bad_request()
        return resp

    def index(self, request, **kwargs):
        ''' Handles GET /bootstrap '''

        try:
            filename = self.expand(ztpserver.config.runtime.bootstrap.filename)
            fobj = self.repository.get_file(filename).read(CONTENT_TYPE_PYTHON)
            default_server = ztpserver.config.runtime.default.server_url
            body = Template(fobj).substitute(SERVER=default_server)
            resp = dict(body=body, content_type=CONTENT_TYPE_PYTHON)
        except KeyError as err:
            log.debug('Missing variable: %s' % err)
            resp = self.http_bad_request()
        except (FileObjectNotFound, FileObjectError) as err:
            log.error('Failed to read bootstrap file: %s' % err)
            resp = self.http_bad_request()
        return resp


class MetaController(BaseController):

    FOLDER = 'meta'

    BODY = {'size': None,
            'sha1': None}

    def __repr__(self):
        return 'MetaController(folder=%s)' % self.FOLDER

    def metadata(self, request, **kwargs):
        ''' Handles GET /meta/[actions|files|nodes]/<PATH_INFO> '''

        file_path = '%s/%s' % (kwargs['type'], kwargs['path_info'])

        try:
            try:
                file_resource = self.repository.get_file(file_path)
            except (FileObjectNotFound, IOError) as exc:
                # IOError is file_path points to a folder
                log.error('%s is a folder, not a file: %s' % 
                          (file_path, str(exc)))
                resp = self.http_not_found()
            else:
                self.BODY['size'] = file_resource.size()
                self.BODY['sha1'] = file_resource.hash()
                resp = dict(body=self.BODY, content_type=CONTENT_TYPE_JSON)
        except IOError as exc:
            log.error('Failed to collect meta information for %s: %s' %
                      (file_path, exc))
            resp = self.http_internal_server_error()
        return resp


class Router(WSGIRouter):
    ''' Routes incoming requests by mapping the URL to a controller '''

    def __init__(self):
        # pylint: disable=E1103,W0142

        mapper = routes.Mapper()

        kwargs = {}

        url = ztpserver.config.runtime.default.server_url
        log.debug('server URL: %s', url)
        parts = urlparse.urlsplit(url)
        if parts.path:
            path = parts.path[:-1] if parts.path.endswith('/') else parts.path
            if path:
                log.debug('path_prefix is %s', path)
                kwargs['path_prefix'] = path

        with mapper.submapper(**kwargs) as router_mapper:

            # configure /bootstrap
            router_mapper.connect('bootstrap', '/bootstrap',
                                  controller=BootstrapController,
                                  action='index',
                                  conditions=dict(method=['GET']))

            router_mapper.connect('bootstrap_config', '/bootstrap/config',
                                  controller=BootstrapController,
                                  action='config',
                                  conditions=dict(method=['GET']))


            # configure /meta
            router_mapper.connect('meta', 
                                  '/meta/{type:actions|files|nodes}/'
                                  '{path_info:.*}',
                                  controller=MetaController,
                                  action='metadata',
                                  conditions=dict(method=['GET']))

            # configure /nodes
            router_mapper.collection('nodes', 'node',
                                     controller=NodesController,
                                     collection_actions=['create'],
                                     member_actions=['show'],
                                     member_prefix='/{resource}')

            router_mapper.connect('get_node_config',
                                  '/nodes/{resource}/startup-config',
                                  controller=NodesController,
                                  action='get_config',
                                  conditions=dict(method=['GET']))

            router_mapper.connect('put_node_config',
                                  '/nodes/{resource}/startup-config',
                                  controller=NodesController,
                                  action='put_config',
                                  conditions=dict(method=['PUT']))

            # configure /actions
            router_mapper.collection('actions', 'action',
                                     controller=ActionsController,
                                     collection_actions=[],
                                     member_actions=['show'],
                                     member_prefix='/{resource}')

            # configure /files
            router_mapper.collection('files', 'file',
                                     controller=FilesController,
                                     collection_actions=[],
                                     member_actions=['show'],
                                     member_prefix='/{resource:.*}')

        super(Router, self).__init__(mapper)
