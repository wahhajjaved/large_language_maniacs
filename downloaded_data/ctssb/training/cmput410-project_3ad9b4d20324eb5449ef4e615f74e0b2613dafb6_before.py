from __future__ import unicode_literals
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, HTTP_HEADER_ENCODING
from rest_framework.authentication import BaseAuthentication
from django.contrib.auth import authenticate
import base64
from Hindlebook.models import Node


def get_authorization_header(request):
    """
    Return request's 'Authorization:' header, as a bytestring.
    Hide some test client ickyness where the header can be unicode.
    """
    auth = request.META.get('HTTP_AUTHORIZATION', b'')
    if isinstance(auth, type('')):
        # Work around django test client oddness
        auth = auth.encode(HTTP_HEADER_ENCODING)
    return auth


def get_user_header(request):
    """
    Return request's 'x-user:' header, as a bytestring.
    Hide some test client ickyness where the header can be unicode.
    """
    user = request.META.get('HTTP_UUID', b'')
    if isinstance(user, type('')):
        # Work around django test client oddness
        user = user.encode(HTTP_HEADER_ENCODING)
    return user


class ForeignNodeAuthentication(BaseAuthentication):
    """
    Custom HTTP Basic authentication against username/password.
    """
    www_authenticate_realm = 'api'

    def authenticate(self, request):
        """
        Returns a `Foreign User` if a correct username and password corresponding to a `Node`
        have been supplied using HTTP Basic authentication.  Otherwise returns `None`.
        """
        # Process Basic Auth host/password header
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != b'basic':
            return None

        if len(auth) == 1:
            msg = _('Invalid basic header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid basic header. Credentials string should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            auth_parts = base64.b64decode(auth[1]).decode(HTTP_HEADER_ENCODING).split(':')
        except (TypeError, UnicodeDecodeError):
            msg = _('Invalid basic header. Credentials not correctly base64 encoded.')
            raise exceptions.AuthenticationFailed(msg)

        if(len(auth_parts) != 2) or auth_parts[0] == '' or auth_parts[1] == '':
            msg = _('Invalid basic header. Expect host:password')
            raise exceptions.AuthenticationFailed(msg)

        host_name, password = auth_parts[0], auth_parts[1]

        return self.authenticate_foreign_credentials(host_name, password)

    def authenticate_foreign_credentials(self, host_name, password):
        """
        Authenticate the host and password and return the vouched Foreign Author
        """
        node = Node.objects.filter(host=host_name).first()

        if node is None:
            raise exceptions.AuthenticationFailed(_('Node %s does not exist.') % host_name)

        if node.password != password:
            raise exceptions.AuthenticationFailed(_('Invalid node password.'))

        return(node, None)

    def authenticate_header(self, request):
        return 'Basic realm="%s"' % self.www_authenticate_realm
