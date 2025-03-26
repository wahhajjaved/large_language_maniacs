"""
OdinWeb.Flask API
~~~~~~~~~~~~~~~~~

Flask implementation of the OdinWeb API interface.

The API integrates into Flask via Flasks blueprint features.

"""
from __future__ import absolute_import

from flask import Flask, request, session, make_response

from odinweb.api import ApiInterfaceBase
from odinweb.constants import Type, Method
from odinweb.data_structures import PathNode


TYPE_MAP = {
    Type.String: 'string',
    Type.Number: 'number',
    Type.Integer: 'int',
    Type.Boolean: 'bool',
    Type.Array: 'list',
    Type.File: 'string',
}


class RequestProxy(object):
    def __init__(self, r):
        self.GET = r.args
        self.POST = r.form
        self.headers = r.headers
        self.session = session
        self.request = r

        try:
            method = Method[r.method]
        except KeyError:
            method = None
        self.method = method

    @property
    def body(self):
        return self.request.data

    @property
    def host(self):
        return self.request.host


class ApiBlueprintSetupState(object):
    """Temporary holder object for registering a blueprint with the
    application.  An instance of this class is created by the
    :meth:`~flask.Blueprint.make_setup_state` method and later passed
    to all register callback functions.
    """

    def __init__(self, blueprint, app, options, first_registration):
        #: a reference to the current application
        self.app = app

        #: a reference to the blueprint that created this setup state.
        self.blueprint = blueprint

        #: a dictionary with all options that were passed to the
        #: :meth:`~flask.Flask.register_blueprint` method.
        self.options = options

        #: as blueprints can be registered multiple times with the
        #: application and not everything wants to be registered
        #: multiple times on it, this attribute can be used to figure
        #: out if the blueprint was registered in the past already.
        self.first_registration = first_registration

        subdomain = self.options.get('subdomain')
        if subdomain is None:
            subdomain = self.blueprint.subdomain

        #: The subdomain that the blueprint should be active for, ``None``
        #: otherwise.
        self.subdomain = subdomain

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        """A helper method to register a rule (and optionally a view function)
        to the application.  The endpoint is automatically prefixed with the
        blueprint's name.
        """
        options.setdefault('subdomain', self.subdomain)
        self.app.add_url_rule(rule, '%s.%s' % (self.blueprint.name, endpoint), view_func, **options)


class ApiBlueprint(ApiInterfaceBase):
    """
    A Flask Blueprint for an API::

        from flask import Flask
        from odinweb.flask.api import ApiBlueprint

        app = Flask(__name__)

        app.register_blueprint(
            ApiBlueprint(
                ApiVersion(
                    UserApi(),
                    version='v1
                )
            )
        )

    """
    _got_registered_once = False

    def __init__(self, *containers, **options):
        self.subdomain = options.pop('subdomain', None)
        super(ApiBlueprint, self).__init__(*containers, **options)

    @staticmethod
    def node_formatter(path_node):
        # type: (PathNode) -> str
        """
        Format a node to be consumable by the `UrlPath.parse`.
        """
        if path_node.type:
            node_type = TYPE_MAP.get(path_node.type, 'str')
            if path_node.type_args:
                return "<{}({}):{}>".format(node_type, ', '.join(path_node.type_args), path_node.name)
            return "<{}:{}>".format(node_type, path_node.name)
        return "<{}>".format(path_node.name)

    def _bound_callback(self, operation):
        def callback(**path_args):
            response = self.dispatch(operation, RequestProxy(request), **path_args)
            return make_response(response.body or ' ', response.status, response.headers)
        return callback

    def register(self, app, options, first_registration):
        # type: (Flask, dict, bool) -> None
        """
        Register interface

        :param app: Instance of flask.
        :param options: Options for blueprint
        :param first_registration: First registration of blueprint

        """
        self._got_registered_once = True
        state = ApiBlueprintSetupState(self, app, options, first_registration)

        for url_path, operation in self.op_paths():
            path = url_path.format(self.node_formatter)
            methods = tuple(m.value for m in operation.methods)
            state.add_url_rule(path, operation.operation_id, self._bound_callback(operation), methods=methods)
