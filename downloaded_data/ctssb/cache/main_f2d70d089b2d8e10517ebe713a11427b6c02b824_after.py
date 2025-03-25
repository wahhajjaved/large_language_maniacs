'''
backends/s3c.py - this file is part of S3QL (http://s3ql.googlecode.com)

Copyright (C) Nikolaus Rath <Nikolaus@rath.org>

This program can be distributed under the terms of the GNU GPLv3.
'''

from ..logging import logging # Ensure use of custom logger class
from ..common import BUFSIZE, QuietError
from .common import (AbstractBackend, NoSuchObject, retry, AuthorizationError, http_connection, 
    AuthenticationError, DanglingStorageURLError, is_temp_network_error)
from base64 import b64encode
from email.utils import parsedate_tz, mktime_tz
from urllib.parse import urlsplit
from xml.etree import ElementTree
import hashlib
import hmac
import http.client
import re
import tempfile
import time
import urllib.parse


C_DAY_NAMES = [ 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun' ]
C_MONTH_NAMES = [ 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec' ]

XML_CONTENT_RE = re.compile(r'^(?:application|text)/xml(?:;|$)', re.IGNORECASE)

log = logging.getLogger(__name__)

class Backend(AbstractBackend):
    """A backend to stored data in some S3 compatible storage service.
    
    This class uses standard HTTP connections to connect to GS.
    
    The backend guarantees only immediate get after create consistency.
    """

    def __init__(self, storage_url, login, password, ssl_context):
        '''Initialize backend object

        *ssl_context* may be a `ssl.SSLContext` instance or *None*.
        '''
        
        super().__init__()

        (host, port, bucket_name, prefix) = self._parse_storage_url(storage_url, ssl_context)

        self.bucket_name = bucket_name
        self.prefix = prefix
        self.hostname = host
        self.port = port
        self.ssl_context = ssl_context
        self.conn = self._get_conn()

        self.password = password
        self.login = login
        self.namespace = 'http://s3.amazonaws.com/doc/2006-03-01/'

    @staticmethod
    def _parse_storage_url(storage_url, ssl_context):
        '''Extract information from storage URL
        
        Return a tuple * (host, port, bucket_name, prefix) * .
        '''

        hit = re.match(r'^[a-zA-Z0-9]+://' # Backend
                       r'([^/:]+)' # Hostname
                       r'(?::([0-9]+))?' # Port 
                       r'/([^/]+)' # Bucketname
                       r'(?:/(.*))?$', # Prefix
                       storage_url)
        if not hit:
            raise QuietError('Invalid storage URL')

        hostname = hit.group(1)
        if hit.group(2):
            port = int(hit.group(2))
        elif ssl_context:
            port = 443
        else:
            port = 80
        bucketname = hit.group(3)
        prefix = hit.group(4) or ''

        return (hostname, port, bucketname, prefix)

    def _get_conn(self):
        '''Return connection to server'''
        
        return http_connection(self.hostname, self.port, self.ssl_context)

    def is_temp_failure(self, exc): #IGNORE:W0613
        '''Return true if exc indicates a temporary error
    
        Return true if the given exception indicates a temporary problem. Most instance methods
        automatically retry the request in this case, so the caller does not need to worry about
        temporary failures.
        
        However, in same cases (e.g. when reading or writing an object), the request cannot
        automatically be retried. In these case this method can be used to check for temporary
        problems and so that the request can be manually restarted if applicable.
        '''

        if isinstance(exc, (InternalError, BadDigestError, IncompleteBodyError, 
                            RequestTimeoutError, OperationAbortedError, SlowDownError, 
                            RequestTimeTooSkewedError)):
            return True

        elif is_temp_network_error(exc):
            return True
        
        elif isinstance(exc, HTTPError) and exc.status >= 500 and exc.status <= 599:
            return True
        
        return False

    @retry
    def delete(self, key, force=False):
        '''Delete the specified object'''

        log.debug('delete(%s)', key)
        try:
            resp = self._do_request('DELETE', '/%s%s' % (self.prefix, key))
            assert resp.length == 0
        except NoSuchKeyError:
            if force:
                pass
            else:
                raise NoSuchObject(key) from None

    def list(self, prefix=''):
        '''List keys in backend

        Returns an iterator over all keys in the backend. This method
        handles temporary errors.
        '''

        log.debug('list(%s): start', prefix)

        marker = ''
        waited = 0
        interval = 1 / 50
        iterator = self._list(prefix, marker)
        while True:
            try:
                marker = next(iterator)
                waited = 0
            except StopIteration:
                break
            except Exception as exc:
                if not self.is_temp_failure(exc):
                    raise
                if waited > 60 * 60:
                    log.error('list(): Timeout exceeded, re-raising %s exception', 
                              type(exc).__name__)
                    raise

                log.info('Encountered %s exception (%s), retrying call to s3c.Backend.list()',
                          type(exc).__name__, exc)
                
                if hasattr(exc, 'retry_after') and exc.retry_after:
                    interval = exc.retry_after
                                    
                time.sleep(interval)
                waited += interval
                interval = min(5*60, 2*interval)
                iterator = self._list(prefix, marker)

            else:
                yield marker

    def _list(self, prefix='', start=''):
        '''List keys in backend, starting with *start*

        Returns an iterator over all keys in the backend. This method
        does not retry on errors.
        '''

        keys_remaining = True
        marker = start
        prefix = self.prefix + prefix

        while keys_remaining:
            log.debug('list(%s): requesting with marker=%s', prefix, marker)

            keys_remaining = None
            resp = self._do_request('GET', '/', query_string={ 'prefix': prefix,
                                                              'marker': marker,
                                                              'max-keys': 1000 })

            if not XML_CONTENT_RE.match(resp.getheader('Content-Type')):
                raise RuntimeError('unexpected content type: %s' % resp.getheader('Content-Type'))

            itree = iter(ElementTree.iterparse(resp, events=("start", "end")))
            (event, root) = next(itree)

            namespace = re.sub(r'^\{(.+)\}.+$', r'\1', root.tag)
            if namespace != self.namespace:
                raise RuntimeError('Unsupported namespace: %s' % namespace)

            try:
                for (event, el) in itree:
                    if event != 'end':
                        continue

                    if el.tag == '{%s}IsTruncated' % self.namespace:
                        keys_remaining = (el.text == 'true')

                    elif el.tag == '{%s}Contents' % self.namespace:
                        marker = el.findtext('{%s}Key' % self.namespace)
                        yield marker[len(self.prefix):]
                        root.clear()

            except GeneratorExit:
                # Need to read rest of response
                while True:
                    buf = resp.read(BUFSIZE)
                    if buf == b'':
                        break
                break

            if keys_remaining is None:
                raise RuntimeError('Could not parse body')

    @retry
    def lookup(self, key):
        """Return metadata for given key"""

        log.debug('lookup(%s)', key)

        try:
            resp = self._do_request('HEAD', '/%s%s' % (self.prefix, key))
            assert resp.length == 0
        except HTTPError as exc:
            if exc.status == 404:
                raise NoSuchObject(key) from None
            else:
                raise

        return extractmeta(resp)

    @retry
    def get_size(self, key):
        '''Return size of object stored under *key*'''

        log.debug('get_size(%s)', key)

        try:
            resp = self._do_request('HEAD', '/%s%s' % (self.prefix, key))
            assert resp.length == 0
        except HTTPError as exc:
            if exc.status == 404:
                raise NoSuchObject(key) from None
            else:
                raise

        for (name, val) in resp.getheaders():
            if name.lower() == 'content-length':
                return int(val)
        raise RuntimeError('HEAD request did not return Content-Length')


    @retry
    def open_read(self, key):
        """Open object for reading

        Return a file-like object. Data can be read using the `read` method. metadata is stored in
        its *metadata* attribute and can be modified by the caller at will. The object must be
        closed explicitly.
        """

        try:
            resp = self._do_request('GET', '/%s%s' % (self.prefix, key))
        except NoSuchKeyError:
            raise NoSuchObject(key) from None

        return ObjectR(key, resp, self, extractmeta(resp))

    def open_write(self, key, metadata=None, is_compressed=False):
        """Open object for writing

        `metadata` can be a dict of additional attributes to store with the object. Returns a file-
        like object. The object must be closed explicitly. After closing, the *get_obj_size* may be
        used to retrieve the size of the stored object (which may differ from the size of the
        written data).
        
        The *is_compressed* parameter indicates that the caller is going to write compressed data,
        and may be used to avoid recompression by the backend.
                        
        Since Amazon S3 does not support chunked uploads, the entire data will
        be buffered in memory before upload.
        """

        log.debug('open_write(%s): start', key)

        headers = dict()
        if metadata:
            for (hdr, val) in metadata.items():
                headers['x-amz-meta-%s' % hdr] = val

        return ObjectW(key, self, headers)


    @retry
    def copy(self, src, dest):
        """Copy data stored under key `src` to key `dest`
        
        If `dest` already exists, it will be overwritten. The copying is done on
        the remote side.
        """

        log.debug('copy(%s, %s): start', src, dest)

        try:
            resp = self._do_request('PUT', '/%s%s' % (self.prefix, dest),
                                    headers={ 'x-amz-copy-source': '/%s/%s%s' % (self.bucket_name,
                                                                                self.prefix, src)})
            # Discard response body
            resp.read()
        except NoSuchKeyError:
            raise NoSuchObject(src) from None

    def _do_request(self, method, path, subres=None, query_string=None,
                    headers=None, body=None):
        '''Send request, read and return response object'''

        log.debug('_do_request(): start with parameters (%r, %r, %r, %r, %r, %r)',
                  method, path, subres, query_string, headers, body)

        if headers is None:
            headers = dict()

        headers['connection'] = 'keep-alive'

        if not body:
            headers['content-length'] = '0'

        redirect_count = 0
        while True:
                
            resp = self._send_request(method, path, headers, subres, query_string, body)
            log.debug('_do_request(): request-id: %s', resp.getheader('x-amz-request-id'))

            if (resp.status < 300 or resp.status > 399):
                break

            # Assume redirect
            new_url = resp.getheader('Location')
            if new_url is None:
                break
            log.info('_do_request(): redirected to %s', new_url)
                        
            redirect_count += 1
            if redirect_count > 10:
                raise RuntimeError('Too many chained redirections')
    
            # Pylint can't infer SplitResult Types
            #pylint: disable=E1103
            o = urlsplit(new_url)
            if o.scheme:
                if isinstance(self.conn, http.client.HTTPConnection) and o.scheme != 'http':
                    raise RuntimeError('Redirect to non-http URL')
                elif isinstance(self.conn, http.client.HTTPSConnection) and o.scheme != 'https':
                    raise RuntimeError('Redirect to non-https URL')
            if o.hostname != self.hostname or o.port != self.port:
                self.hostname = o.hostname
                self.port = o.port
                self.conn = self._get_conn()
            else:
                raise RuntimeError('Redirect to different path on same host')
            
            if body and not isinstance(body, (bytes, bytearray, memoryview)):
                body.seek(0)

            # Read and discard body
            log.debug('Response body: %s', resp.read())

        # We need to call read() at least once for httplib to consider this
        # request finished, even if there is no response body.
        if resp.length == 0:
            resp.read()

        # Success 
        if resp.status >= 200 and resp.status <= 299:
            return resp

        # If method == HEAD, server must not return response body
        # even in case of errors
        if method.upper() == 'HEAD':
            raise HTTPError(resp.status, resp.reason)

        content_type = resp.getheader('Content-Type')
        if not content_type or not XML_CONTENT_RE.match(content_type):
            raise HTTPError(resp.status, resp.reason, resp.getheaders(), resp.read())
 
        # Error
        tree = ElementTree.parse(resp).getroot()
        raise get_S3Error(tree.findtext('Code'), tree.findtext('Message'))


    def clear(self):
        """Delete all objects in backend
        
        Note that this method may not be able to see (and therefore also not
        delete) recently uploaded objects.
        """

        # We have to cache keys, because otherwise we can't use the
        # http connection to delete keys.
        for (no, s3key) in enumerate(list(self)):
            if no != 0 and no % 1000 == 0:
                log.info('clear(): deleted %d objects so far..', no)

            log.debug('clear(): deleting key %s', s3key)

            # Ignore missing objects when clearing bucket
            self.delete(s3key, True)

    def __str__(self):
        return 's3c://%s/%s/%s' % (self.hostname, self.bucket_name, self.prefix)

    def _send_request(self, method, path, headers, subres=None, query_string=None, body=None):
        '''Add authentication and send request
        
        Note that *headers* is modified in-place. Returns the response object.
        '''

        # See http://docs.amazonwebservices.com/AmazonS3/latest/dev/RESTAuthentication.html

        # Lowercase headers
        keys = list(headers.keys())
        for key in keys:
            key_l = key.lower()
            if key_l == key:
                continue
            headers[key_l] = headers[key]
            del headers[key]

        # Date, can't use strftime because it's locale dependent
        now = time.gmtime()
        headers['date'] = ('%s, %02d %s %04d %02d:%02d:%02d GMT'
                           % (C_DAY_NAMES[now.tm_wday],
                              now.tm_mday,
                              C_MONTH_NAMES[now.tm_mon - 1],
                              now.tm_year, now.tm_hour,
                              now.tm_min, now.tm_sec))

        auth_strs = [method, '\n']

        for hdr in ('content-md5', 'content-type', 'date'):
            if hdr in headers:
                auth_strs.append(headers[hdr])
            auth_strs.append('\n')

        for hdr in sorted(x for x in headers if x.startswith('x-amz-')):
            val = ' '.join(re.split(r'\s*\n\s*', headers[hdr].strip()))
            auth_strs.append('%s:%s\n' % (hdr, val))


        # Always include bucket name in path for signing
        sign_path = urllib.parse.quote('/%s%s' % (self.bucket_name, path))
        auth_strs.append(sign_path)
        if subres:
            auth_strs.append('?%s' % subres)

        # False positive, hashlib *does* have sha1 member
        #pylint: disable=E1101
        auth_str = ''.join(auth_strs).encode()
        signature = b64encode(hmac.new(self.password.encode(), auth_str,
                                       hashlib.sha1).digest()).decode()

        headers['authorization'] = 'AWS %s:%s' % (self.login, signature)

        # Construct full path
        if not self.hostname.startswith(self.bucket_name):
            path = '/%s%s' % (self.bucket_name, path)
        path = urllib.parse.quote(path)
        if query_string:
            s = urllib.parse.urlencode(query_string, doseq=True)
            if subres:
                path += '?%s&%s' % (subres, s)
            else:
                path += '?%s' % s
        elif subres:
            path += '?%s' % subres

        try:
            log.debug('_send_request(): sending request for %s', path)
            self.conn.request(method, path, body, headers)

            log.debug('_send_request(): Reading response..')
            return self.conn.getresponse()
        except:
            # We probably can't use the connection anymore
            self.conn.close()
            raise
        
class ObjectR(object):
    '''An S3 object open for reading'''

    # NOTE: This class is used as a base class for the swift backend,
    # so changes here should be checked for their effects on other
    # backends.
    
    def __init__(self, key, resp, backend, metadata=None):
        self.key = key
        self.resp = resp
        self.md5_checked = False
        self.backend = backend
        self.metadata = metadata

        # False positive, hashlib *does* have md5 member
        #pylint: disable=E1101        
        self.md5 = hashlib.md5()

    def read(self, size=None):
        '''Read object data
        
        For integrity checking to work, this method has to be called until
        it returns an empty string, indicating that all data has been read
        (and verified).
        '''

        # chunked encoding handled by httplib
        buf = self.resp.read(size)

        # Check MD5 on EOF
        if not buf and not self.md5_checked:
            etag = self.resp.getheader('ETag').strip('"')
            self.md5_checked = True
            
            if not self.resp.isclosed():
                # http://bugs.python.org/issue15633, but should be fixed in 
                # Python 3.3 and newer
                log.error('ObjectR.read(): response not closed after end of data, '
                          'please report on http://code.google.com/p/s3ql/issues/')
                log.error('Method: %s, chunked: %s, read length: %s '
                          'response length: %s, chunk_left: %s, status: %d '
                          'reason "%s", version: %s, will_close: %s',
                          self.resp._method, self.resp.chunked, size, self.resp.length,
                          self.resp.chunk_left, self.resp.status, self.resp.reason,
                          self.resp.version, self.resp.will_close)             
                self.resp.close() 
            
            if etag != self.md5.hexdigest():
                log.warning('ObjectR(%s).close(): MD5 mismatch: %s vs %s', self.key, etag,
                         self.md5.hexdigest())
                raise BadDigestError('BadDigest', 'ETag header does not agree with calculated MD5')
            
            return buf

        self.md5.update(buf)
        return buf

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        '''Close object'''

        pass

class ObjectW(object):
    '''An S3 object open for writing
    
    All data is first cached in memory, upload only starts when
    the close() method is called.
    '''
    
    # NOTE: This class is used as a base class for the swift backend,
    # so changes here should be checked for their effects on other
    # backends.
    
    def __init__(self, key, backend, headers):
        self.key = key
        self.backend = backend
        self.headers = headers
        self.closed = False
        self.obj_size = 0
        
        # According to http://docs.python.org/3/library/functions.html#open
        # the buffer size is typically ~8 kB. We process data in much 
        # larger chunks, so buffering would only hurt performance.
        self.fh = tempfile.TemporaryFile(buffering=0) 

        # False positive, hashlib *does* have md5 member
        #pylint: disable=E1101        
        self.md5 = hashlib.md5()

    def write(self, buf):
        '''Write object data'''

        self.fh.write(buf)
        self.md5.update(buf)
        self.obj_size += len(buf)

    def is_temp_failure(self, exc):
        return self.backend.is_temp_failure(exc)

    @retry
    def close(self):
        '''Close object and upload data'''

        # Access to protected member ok
        #pylint: disable=W0212

        log.debug('ObjectW(%s).close(): start', self.key)

        self.closed = True
        self.headers['Content-Length'] = self.obj_size

        self.fh.seek(0)
        resp = self.backend._do_request('PUT', '/%s%s' % (self.backend.prefix, self.key),
                                       headers=self.headers, body=self.fh)
        etag = resp.getheader('ETag').strip('"')
        assert resp.length == 0

        if etag != self.md5.hexdigest():
            log.warning('ObjectW(%s).close(): MD5 mismatch (%s vs %s)', self.key, etag,
                     self.md5.hexdigest)
            try:
                self.backend.delete(self.key)
            except:
                log.exception('Objectw(%s).close(): unable to delete corrupted object!',
                              self.key)
            raise BadDigestError('BadDigest', 'Received ETag does not agree with our calculations.')

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def get_obj_size(self):
        if not self.closed:
            raise RuntimeError('Object must be closed first.')
        return self.obj_size


def get_S3Error(code, msg):
    '''Instantiate most specific S3Error subclass'''

    # Special case
    # http://code.google.com/p/s3ql/issues/detail?id=369
    if code == 'Timeout':
        code = 'RequestTimeout'  

    if code.endswith('Error'):
        name = code
    else:
        name = code + 'Error'
    class_ = globals().get(name, S3Error)    
    
    if not issubclass(class_, S3Error):
        return S3Error(code, msg)
    
    return class_(code, msg)

def extractmeta(resp):
    '''Extract metadata from HTTP response object'''

    meta = dict()
    for (name, val) in resp.getheaders():
        hit = re.match(r'^x-amz-meta-(.+)$', name)
        if not hit:
            continue
        meta[hit.group(1)] = val

    return meta

class HTTPError(Exception):
    '''
    Represents an HTTP error returned by S3.
    '''

    def __init__(self, status, msg, headers=None, body=None):
        super().__init__()
        self.status = status
        self.msg = msg
        self.headers = headers
        self.body = body
        self.retry_after = None
        
        if self.headers is not None:
            self._set_retry_after()
        
    def _set_retry_after(self):
        '''Parse headers for Retry-After value'''
        
        val = None
        for (k, v) in self.headers:
            if k.lower() == 'retry-after':
                hit = re.match(r'^\s*([0-9]+)\s*$', v)
                if hit:
                    val = int(v)
                else:
                    date = parsedate_tz(v)
                    if date is None:
                        log.warning('Unable to parse header: %s: %s', k, v)
                        continue
                    val = mktime_tz(*date) - time.time()
                    
        if val is not None:
            if val > 300 or val < 0:
                log.warning('Ignoring invalid retry-after value of %.3f', val)
            else:
                self.retry_after = val
            
    def __str__(self):
        return '%d %s' % (self.status, self.msg)

class S3Error(Exception):
    '''
    Represents an error returned by S3. For possible codes, see
    http://docs.amazonwebservices.com/AmazonS3/latest/API/ErrorResponses.html
    '''

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg

    def __str__(self):
        return '%s: %s' % (self.code, self.msg)

class NoSuchKeyError(S3Error): pass
class AccessDeniedError(S3Error, AuthorizationError): pass
class BadDigestError(S3Error): pass
class IncompleteBodyError(S3Error): pass
class InternalError(S3Error): pass
class InvalidAccessKeyIdError(S3Error, AuthenticationError): pass
class InvalidSecurityError(S3Error, AuthenticationError): pass
class SignatureDoesNotMatchError(S3Error, AuthenticationError): pass
class OperationAbortedError(S3Error): pass
class RequestTimeoutError(S3Error): pass
class SlowDownError(S3Error): pass
class RequestTimeTooSkewedError(S3Error): pass
class NoSuchBucketError(S3Error, DanglingStorageURLError): pass
