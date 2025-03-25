
__author__    = "Individual contributors (see AUTHORS file)"
__date__      = "$DATE$"
__rev__       = "$REV$"
__license__   = "AGPL v.3"
__copyright__ = """
This file is part of the ESP Web Site
Copyright (c) 2007 by the individual contributors
  (see AUTHORS file)

The ESP Web Site is free software; you can redistribute it and/or
modify it under the terms of the GNU Affero General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public
License along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

Contact information:
MIT Educational Studies Program
  84 Massachusetts Ave W20-467, Cambridge, MA 02139
  Phone: 617-253-4882
  Email: esp-webmasters@mit.edu
Learning Unlimited, Inc.
  527 Franklin St, Cambridge, MA 02139
  Phone: 617-379-0178
  Email: web-team@lists.learningu.org
"""

import datetime
import simplejson as json

from django.conf import settings
from django.template import RequestContext, Context
from django.http import HttpResponse, Http404
from django.db.models.base import ObjectDoesNotExist
from django.utils.translation import ugettext as _

class Http403(Exception):
    pass

class ESPError_Log(Exception):
    pass

class ESPError_NoLog(Exception):
    pass

def ESPError(log=True):
    """ Use this to raise an error in the ESP world.
    Example usage::
        from esp.middleware import ESPError
        raise ESPError(False), 'This error will not be logged.'
    """
    if log:
        return ESPError_Log
    else:
        return ESPError_NoLog
 
""" Adapted from http://www.djangosnippets.org/snippets/802/ """
class AjaxErrorMiddleware(object):
    '''Return AJAX errors to the browser in a sensible way.

    Includes some code from http://www.djangosnippets.org/snippets/650/
    '''

    # Some useful errors that this middleware will catch.
    class AjaxError(Exception):
        def __init__(self, message):
            self.message = message
            super(AjaxErrorMiddleWare.AjaxError, self).__init__(message)

    class AjaxParameterMissingError(AjaxError):
        def __init__(self, param):
            super(AjaxErrorMiddleware.AjaxParameterMissingError, self).__init__(
                _('Required parameter missing: %s') % param)


    def process_exception(self, request, exception):
        #   This line has been commented out for debugging so that requests
        #   can be made using a normal browser like Firefox with UrlParams.
        if not request.is_ajax(): return

        if isinstance(exception, (ObjectDoesNotExist, Http404)):
            return self.not_found(request, exception)

        if isinstance(exception, AjaxErrorMiddleware.AjaxError):
            return self.bad_request(request, exception)

        return None
    

    def serialize_error(self, status, message):
        return HttpResponse(json.dumps({
                    'status': status,
                    'error': message}),
                            status=status)

    
    def not_found(self, request, exception):
        return self.serialize_error(404, str(exception))

    
    def bad_request(self, request, exception):
        return self.serialize_error(200, exception.message)


    def server_error(self, request, exception):
        if settings.DEBUG:
            import sys, traceback
            (exc_type, exc_info, tb) = sys.exc_info()
            message = "%s\n" % exc_type.__name__
            message += "%s\n\n" % exc_info
            message += "TRACEBACK:\n"    
            for tb in traceback.format_tb(tb):
                message += "%s\n" % tb
            return self.serialize_error(500, message)
        else:
            return self.serialize_error(500, _('Internal error'))

AjaxError = AjaxErrorMiddleware.AjaxError

class ESPErrorMiddleware(object):
    """ This middleware handles errors appropriately.
    It will display a friendly error if there indeed was one
    (and emails the admin). This, of course, is only true if DEBUG is
    False in the settings.py. Otherwise, it doesn't do any of that.
    """

    def process_exception(self, request, exception):
        from django.shortcuts import render_to_response
        from django.conf import settings
        from django.core.mail import mail_admins
        
        import sys

        debug = settings.DEBUG  # get the debug value
        
        exc_info = sys.exc_info()
        if isinstance(exception, ESPError_Log) or exception == ESPError_Log:
            # Subject of the email
            subject = 'Error (%s IP): %s' % ((request.META.get('REMOTE_ADDR') in \
                                              settings.INTERNAL_IPS and 'internal' or 'EXTERNAL'), \
                                              getattr(request, 'path', ''))
                
            try:
                request_repr = repr(request)
            except:
                request_repr = "Request repr() unavailable"
                        

            # get a friendly traceback
            traceback = self._get_traceback(exc_info)

            # Message itself
            message = "%s\n\n%s" % (traceback, request_repr)

            # Now we send the email
            mail_admins(subject, message, fail_silently=True)

            # Now we store the error into the database:
            try:
                # We're going to 'try' everything
                from esp.dblog.models import Log
                new_log = Log(text        = str(exc_info[1]),
                              extra       = str(request_repr),
                              stack_trace = str(traceback))
                new_log.save()

            except:
                # we just won't do anything if we can't log it...
                pass

        elif isinstance(exception, Http403):
            context = {'error': exc_info[1]}
            try:
                # attempt to set up variables the template needs
                # - actually, some things will fail to be set up due to our
                #   silly render_to_response hack, but hopefully that will all
                #   just silently fail...
                # - alternatively, we could, I dunno, NOT GET RID OF THE SAFE
                #   TEMPLATE in main?
                context_instance = RequestContext(request)
            except:
                # well, we couldn't, but at least display something
                # (actually it will immediately fail on main because someone
                # removed the safe version of the template and
                # miniblog_for_user doesn't silently fail but best not to put
                # in ugly hacks and make random variables just happen to work.)
                context_instance = Context()
            response = render_to_response('403.html', context, context_instance=context_instance)
            response.status_code = 403
            return response


        if isinstance(exception, ESPError_NoLog) or exception == ESPError_NoLog \
                or isinstance(exception, ESPError_Log) or exception == ESPError_Log: # No logging, just output
            context = {'error': exc_info[1]}
            try:
                # attempt to set up variables the template needs
                # - actually, some things will fail to be set up due to our
                #   silly render_to_response hack, but hopefully that will all
                #   just silently fail...
                # - alternatively, we could, I dunno, NOT GET RID OF THE SAFE
                #   TEMPLATE in main?
                context_instance = RequestContext(request)
            except:
                # well, we couldn't, but at least display something
                # (actually it will immediately fail on main because someone
                # removed the safe version of the template and
                # miniblog_for_user doesn't silently fail but best not to put
                # in ugly hacks and make random variables just happen to work.)
                context_instance = Context()
            response = render_to_response('error.html', context, context_instance=context_instance)  # Will use a pretty ESP error page...
            response.status_code = 500
            return response
        return None

            
    def _get_traceback(self, exc_info=None):
        "Helper function to return the traceback as a string"
        import traceback
        return '\n'.join(traceback.format_exception(*(exc_info or sys.exc_info())))

