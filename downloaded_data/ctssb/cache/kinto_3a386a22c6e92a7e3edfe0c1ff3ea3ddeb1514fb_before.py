"""Main entry point
"""
import pkg_resources

#: Module version, as defined in PEP-0396.
__version__ = pkg_resources.get_distribution(__package__).version

import six

from pyramid.config import Configurator
from pyramid.events import NewRequest
from pyramid_multiauth import MultiAuthenticationPolicy

from readinglist import authentication
from readinglist.resource import TimeStamp


API_VERSION = 'v%s' % __version__.split('.')[0]


def main(global_config, **settings):
    config = Configurator(settings=settings)
    config.route_prefix = '/%s' % API_VERSION

    backend_module = config.maybe_dotted(settings['readinglist.backend'])
    config.registry.backend = backend_module.load_from_config(config)

    policies = [
        authentication.Oauth2AuthenticationPolicy(),
        authentication.BasicAuthAuthenticationPolicy(),
    ]
    authn_policy = MultiAuthenticationPolicy(policies)
    authz_policy = authentication.AuthorizationPolicy()

    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)

    config.include("cornice")
    config.scan("readinglist.views")

    # Attachments on requests

    def attach_objects_to_request(event):
        event.request.db = config.registry.backend
        http_scheme = config.registry.settings.get('readinglist.http_scheme')
        if http_scheme:
            event.request.scheme = http_scheme

    config.add_subscriber(attach_objects_to_request, NewRequest)

    # Timestamp in response headers

    def add_timestamp_header_to_responses(event):
        timestamp = six.text_type(TimeStamp.now())
        event.request.response.headers['Timestamp'] = timestamp

    config.add_subscriber(add_timestamp_header_to_responses, NewRequest)

    return config.make_wsgi_app()
