from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse


class HTTPMethodRestrictionMiddleware(object):

    def __init__(self):
        """
        Middleware used to return a HTTP 405 (method not allowed) when a request's HTTP method
        is not in the ALLOWED_HTTP_METHODS setting.
        If no setting is supplied (or set to None), then this middleware is not used.
        If a blank iterable is supplied for the setting, then there are no restrictions.
        """

        allowed_methods = getattr(settings, 'ALLOWED_HTTP_METHODS')

        if allowed_methods is None:
            raise MiddlewareNotUsed

        self.allowed_methods = allowed_methods

    def process_request(self, request):

        if request.method in self.allowed_methods:
            return None

        return HttpResponse(status=501)
