#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2010 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

"""
HTTP utilities to help pulp web services with HTTP using the web.py framework
"""

import base64
import httplib
import os
import re
import urllib

import web

# python 2.4 compat instead of: httplib.responses
http_responses = {
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request-URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    100: 'Continue',
    101: 'Switching Protocols',
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    306: '(Unused)',
    307: 'Temporary Redirect',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported'}

# request methods -------------------------------------------------------------

def request_info(key):
    """
    Get information from the request.
    Returns the value corresponding the given key.
    Returns None if the key isn't found.
    @type key: str
    @param key: lookup key in the request information
    @rtype: str or None
    @return: request value
    """
    return web.ctx.environ.get(key, None)


def request_url():
    """
    Rebuild the full request url from the request information.
    @rtype: str
    @return: full request url
    """
    scheme = request_info('wsgi.url_scheme') or 'https'
    host = request_info('HTTP_HOST') or 'localhost'
    uri = request_info('REQUEST_URI') or ''
    path = uri.split('?')[0]
    return '%s://%s%s' % (scheme, host, path)


def query_parameters(valid):
    """
    @type valid: list of str's
    @param valid: list of expected query parameters
    @return: dict of param: [value(s)] of uri query parameters
    """
    # NOTE If a keyword argument of foo=[] is not passed into web.input,
    # web.py will not record multiple parameters of 'foo' from the URI.
    # So this line of code constructs those keyword arguments for 'valid'
    # (ie expected) query parameters.
    # This will return a list for every valid parameter, even if it's empty or
    # only contains one element
    defaults = {}.fromkeys(valid, [])
    params = web.input(**defaults)
    # scrub out invalid keys and empty lists from the parameters
    return dict((k, v) for k, v in params.items() if k in valid and v)

# http auth methods -----------------------------------------------------------

_whitespace_regex = re.compile('\w+')


class HTTPAuthError(Exception):
    pass


def http_authorization():
    """
    Return the current http authorization credentials, if any
    @return: str representing the http authorization credentials if found,
             None otherwise
    """
    return request_info('HTTP_AUTHORIZATION')


def _is_basic_auth(credentials):
    """
    Check if the credentials are for http basic authorization
    @type credentials: str
    @param credentials: value of the HTTP_AUTHORIZATION header
    @return: True if the credentials are for http basic authorization,
             False otherwise
    """
    if len(credentials) < 5:
        return False
    type = credentials[:5].lower()
    return type == 'basic'


def _basic_username_password(credentials):
    """
    Get the username and password from http basic authorization credentials
    """
    credentials = credentials.strip()
    if not _whitespace_regex.match(credentials):
        raise HTTPAuthError('malformed basic authentication information')
    encoded_str = _whitespace_regex.split(credentials, 1)[1].strip()
    # All requests come in with a blank Basic authorization (for repo auth),
    # in addition to one that may be specified.  Remove the blank one.
    if encoded_str.endswith(', Basic'):
        encoded_str = encoded_str[:-7]
    decoded_str = base64.decodestring(encoded_str)
    if decoded_str.find(':') < 0:
        raise HTTPAuthError('malformed basic authentication information')
    return decoded_str.split(':', 1)


def _is_digest_auth(credentials):
    """
    Check if the credentials are for http digest authorization
    @type credentials: str
    @param credentials: value of the HTTP_AUTHORIZATION header
    @return: True if the credentials are for http digest authorization,
             False otherwise
    """
    if len(credentials) < 6:
        return False
    type = credentials[:6].lower()
    return type == 'digest'


def _digest_username_password(credentials):
    """
    Get the username and password from http digest authorization credentials
    """
    raise NotImplementedError('HTTP Digest Authorization not yet implemented')


def username_password():
    """
    Return a the username, password tuple from the http authorization header
    Return a tuple of Nones if the header isn't found
    @rtype: tuple of str's or Nones
    @return: username, password tuple
    """
    credentials = http_authorization()
    if credentials is None:
        return (None, None)
    if _is_basic_auth(credentials):
        return _basic_username_password(credentials)
    if _is_digest_auth(credentials):
        return _digest_username_password(credentials)
    return (None, None)

# ssl methods -----------------------------------------------------------------

def ssl_client_cert():
    """
    Return the ssl client cert if it is found, None otherwise
    @rtype: str or None
    @return: pem encoded cert
    """
    return web.ctx.environ.get('SSL_CLIENT_CERT', None)

# uri path functions ----------------------------------------------------------

def uri_path():
    """
    Return the current URI path
    @return: full current URI path
    """
    return web.http.url(web.ctx.path)


def extend_uri_path(suffix):
    """
    Return the current URI path with the suffix appended to it
    @type suffix: str
    @param suffix: path fragment to be appended to the current path
    @return: full path with the suffix appended
    """
    # steps:
    # cleanly concatenate the current path with the suffix
    # add the application prefix
    # all urls are paths, so need a trailing '/'
    # make sure the path is properly encoded
    prefix = uri_path()
    suffix = urllib.pathname2url(suffix)
    path = os.path.normpath(os.path.join(prefix, suffix))
    if not path.endswith('/'):
        path += '/'
    return path


def resource_path(path=None):
    """
    Return the uri path with the /pulp/api prefix stripped off
    @type path: None or str
    @param path: The uri path to convert into a resource path,
                 if the path is None, defaults to the current uri path
    @rtype: str
    @return: uri formatted path
    """
    # NOTE this function actually sucks, it makes the assumption that pulp has
    # been deployed under /pulp/api. A better way would be to grab the urls
    # from the top-level web.py application, but we can't do that directly as
    # it causes a circular dependency in the imports.
    # I wonder if we can inspect the application at runtime via the web module
    if path is None:
        path = uri_path()
    parts = [p for p in path.split('/') if p]
    while parts and parts[0] in ('pulp', 'api'):
        parts = parts[1:]
    if not parts:
        return '/'
    return '/%s/' % '/'.join(parts)

# response functions ----------------------------------------------------------

def header(hdr, value, unique=True):
    """
    Adds 'hdr: value' to the response.
    This function has, in some regards, the opposite semantics of the web.header
    function. If unique is True, the hdr will be overwritten if it already
    exists in the response. Otherwise it will be appended.
    @type hdr: str
    @param hdr: valid http header key
    @type value: str
    @param value: valid value for corresponding header key
    @type unique: bool
    @param unique: whether only one instance of the header is in the response
    """
    hdr = web.utf8(hdr)
    value = web.utf8(value)
    previous = []
    for h, v in web.ctx.headers:
        if h.lower() == hdr.lower():
            previous.append((h, v))
    if unique:
        for p in previous:
            web.ctx.headers.remove(p)
    web.ctx.headers.append((hdr, value))

# status functions ------------------------------------------------------------

def _status(code):
    """
    Non-public function to set the web ctx status
    @type code: int
    @param code: http response code
    """
    web.ctx.status = '%d %s' % (code, http_responses[code])


def status_ok():
    """
    Set response code to ok
    """
    _status(httplib.OK)


def status_created():
    """
    Set response code to created
    """
    _status(httplib.CREATED)


def status_no_content():
    """
    Set response code to no content
    """
    _status(httplib.NO_CONTENT)


def status_accepted():
    """
    Set response code to accepted
    """
    _status(httplib.ACCEPTED)


def status_bad_request():
    """
    Set the response code to bad request
    """
    _status(httplib.BAD_REQUEST)


def status_unauthorized():
    """
    Set response code to unauthorized
    """
    _status(httplib.UNAUTHORIZED)


def status_not_found():
    """
    Set response code to not found
    """
    _status(httplib.NOT_FOUND)


def status_method_not_allowed():
    """
    Set response code to method not allowed
    """
    _status(httplib.METHOD_NOT_ALLOWED)


def status_not_acceptable():
    """
    Set response code to not acceptable
    """
    _status(httplib.NOT_ACCEPTABLE)


def status_conflict():
    """
    Set response code to conflict
    """
    _status(httplib.CONFLICT)

def status_internal_server_error():
    """
    Set the resonse code to internal server error
    """
    _status(httplib.INTERNAL_SERVER_ERROR)

def status_partial():
    '''
    Set the response code to partial content
    '''
    _status(httplib.PARTIAL_CONTENT)
