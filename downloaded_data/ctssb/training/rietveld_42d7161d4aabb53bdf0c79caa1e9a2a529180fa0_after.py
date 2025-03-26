# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Custom middleware.  Some of this may be generally useful."""

import logging

from google.appengine.api import users
from google.appengine.runtime import apiproxy_errors
from google.appengine.runtime import DeadlineExceededError

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.template import Context, loader

from codereview import models


class AddHSTSHeaderMiddleware(object):
  """Add HTTP Strict Transport Security header."""

  def process_response(self, request, response):
    if request.is_secure():
      response['Strict-Transport-Security'] = (
          'max-age=%d' % settings.HSTS_MAX_AGE)
    return response


class AddUserToRequestMiddleware(object):
  """Add a user object and a user_is_admin flag to each request."""

  def process_request(self, request):
    request.user = users.get_current_user()
    request.user_is_admin = users.is_current_user_admin()

    # Update the cached value of the current user's Account
    account = None
    if request.user is not None:
      account = models.Account.get_account_for_user(request.user)
    models.Account.current_user_account = account


class PropagateExceptionMiddleware(object):
  """Catch exceptions, log them and return a friendly error message.
     Disables itself in DEBUG mode.
  """

  def _text_requested(self, request):
    """Returns True if a text/plain response is requested."""
    # We could use a better heuristics that takes multiple
    # media_ranges and quality factors into account. For now we return
    # True iff 'text/plain' is the only media range the request
    # accepts.
    media_ranges = request.META.get('HTTP_ACCEPT', '').split(',')
    return len(media_ranges) == 1 and media_ranges[0] == 'text/plain'


  def process_exception(self, request, exception):
    if settings.DEBUG or isinstance(exception, Http404):
      return None
    if isinstance(exception, apiproxy_errors.CapabilityDisabledError):
      msg = ('Rietveld: App Engine is undergoing maintenance. '
             'Please try again in a while.')
      status = 503
    elif isinstance(exception, (DeadlineExceededError, MemoryError)):
      msg = ('Rietveld is too hungry at the moment.'
             'Please try again in a while.')
      status = 503
    else:
      msg = 'Unhandled exception.'
      status = 500
    logging.exception('%s: ' % exception.__class__.__name__)
    technical = '%s [%s]' % (exception, exception.__class__.__name__)
    if self._text_requested(request):
      content = '%s\n\n%s\n' % (msg, technical)
      content_type = 'text/plain'
    else:
      tpl = loader.get_template('exception.html')
      ctx = Context({'msg': msg, 'technical': technical})
      content = tpl.render(ctx)
      content_type = 'text/html'
    return HttpResponse(content, status=status, content_type=content_type)


class RedirectDotVersionMiddleware(object):
  """Work around the -dot- version problem with HTTPS-SNI certificate."""
  def process_request(self, request):
    if request.method == 'POST':
      return
    host = request.get_host().split(':')[0]
    parts = host.split('.')
    if (len(parts) > 3 and
        parts[-1] == 'com' and
        parts[-2] in ('appspot', 'googleplex')):
      host = '-dot-'.join(parts[:-3] + ['.'.join(parts[-3:])])
      return HttpResponsePermanentRedirect(
          'https://%s%s' % (host, request.get_full_path()))


class RedirectToHTTPSMiddleware(object):
  """Redirect HTTP requests to the equivalent HTTPS resource."""
  def process_request(self, request):
    if settings.DEBUG or request.method == 'POST':
      return
    if not request.is_secure():
      host = request.get_host().split(':')[0]
      return HttpResponsePermanentRedirect(
          'https://%s%s' % (host, request.get_full_path()))
