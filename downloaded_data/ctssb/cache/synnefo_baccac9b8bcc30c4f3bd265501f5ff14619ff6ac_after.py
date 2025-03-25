# Copyright 2011 GRNET S.A. All rights reserved.
# 
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the following
# conditions are met:
# 
#   1. Redistributions of source code must retain the above
#      copyright notice, this list of conditions and the following
#      disclaimer.
# 
#   2. Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials
#      provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY GRNET S.A. ``AS IS'' AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GRNET S.A OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# 
# The views and conclusions contained in the software and
# documentation are those of the authors and should not be
# interpreted as representing official policies, either expressed
# or implied, of GRNET S.A.

from functools import wraps
from time import time
from traceback import format_exc
from wsgiref.handlers import format_date_time
from binascii import hexlify, unhexlify
from datetime import datetime, tzinfo, timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import simplejson as json
from django.utils.http import http_date, parse_etags
from django.utils.encoding import smart_str
from django.core.files.uploadhandler import FileUploadHandler
from django.core.files.uploadedfile import UploadedFile

from pithos.api.compat import parse_http_date_safe, parse_http_date
from pithos.api.faults import (Fault, NotModified, BadRequest, Unauthorized, Forbidden, ItemNotFound,
                                Conflict, LengthRequired, PreconditionFailed, RequestEntityTooLarge,
                                RangeNotSatisfiable, ServiceUnavailable)
from pithos.backends import connect_backend
from pithos.backends.base import NotAllowedError, QuotaError

import logging
import re
import hashlib
import uuid
import decimal


logger = logging.getLogger(__name__)


class UTC(tzinfo):
   def utcoffset(self, dt):
       return timedelta(0)

   def tzname(self, dt):
       return 'UTC'

   def dst(self, dt):
       return timedelta(0)

def json_encode_decimal(obj):
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    raise TypeError(repr(obj) + " is not JSON serializable")

def isoformat(d):
   """Return an ISO8601 date string that includes a timezone."""

   return d.replace(tzinfo=UTC()).isoformat()

def rename_meta_key(d, old, new):
    if old not in d:
        return
    d[new] = d[old]
    del(d[old])

def printable_header_dict(d):
    """Format a meta dictionary for printing out json/xml.
    
    Convert all keys to lower case and replace dashes with underscores.
    Format 'last_modified' timestamp.
    """
    
    d['last_modified'] = isoformat(datetime.fromtimestamp(d['last_modified']))
    return dict([(k.lower().replace('-', '_'), v) for k, v in d.iteritems()])

def format_header_key(k):
    """Convert underscores to dashes and capitalize intra-dash strings."""
    return '-'.join([x.capitalize() for x in k.replace('_', '-').split('-')])

def get_header_prefix(request, prefix):
    """Get all prefix-* request headers in a dict. Reformat keys with format_header_key()."""
    
    prefix = 'HTTP_' + prefix.upper().replace('-', '_')
    # TODO: Document or remove '~' replacing.
    return dict([(format_header_key(k[5:]), v.replace('~', '')) for k, v in request.META.iteritems() if k.startswith(prefix) and len(k) > len(prefix)])

def get_account_headers(request):
    meta = get_header_prefix(request, 'X-Account-Meta-')
    groups = {}
    for k, v in get_header_prefix(request, 'X-Account-Group-').iteritems():
        n = k[16:].lower()
        if '-' in n or '_' in n:
            raise BadRequest('Bad characters in group name')
        groups[n] = v.replace(' ', '').split(',')
        while '' in groups[n]:
            groups[n].remove('')
    return meta, groups

def put_account_headers(response, meta, groups, policy):
    if 'count' in meta:
        response['X-Account-Container-Count'] = meta['count']
    if 'bytes' in meta:
        response['X-Account-Bytes-Used'] = meta['bytes']
    response['Last-Modified'] = http_date(int(meta['modified']))
    for k in [x for x in meta.keys() if x.startswith('X-Account-Meta-')]:
        response[smart_str(k, strings_only=True)] = smart_str(meta[k], strings_only=True)
    if 'until_timestamp' in meta:
        response['X-Account-Until-Timestamp'] = http_date(int(meta['until_timestamp']))
    for k, v in groups.iteritems():
        k = smart_str(k, strings_only=True)
        k = format_header_key('X-Account-Group-' + k)
        v = smart_str(','.join(v), strings_only=True)
        response[k] = v
    for k, v in policy.iteritems():
        response[smart_str(format_header_key('X-Account-Policy-' + k), strings_only=True)] = smart_str(v, strings_only=True)

def get_container_headers(request):
    meta = get_header_prefix(request, 'X-Container-Meta-')
    policy = dict([(k[19:].lower(), v.replace(' ', '')) for k, v in get_header_prefix(request, 'X-Container-Policy-').iteritems()])
    return meta, policy

def put_container_headers(request, response, meta, policy):
    if 'count' in meta:
        response['X-Container-Object-Count'] = meta['count']
    if 'bytes' in meta:
        response['X-Container-Bytes-Used'] = meta['bytes']
    response['Last-Modified'] = http_date(int(meta['modified']))
    for k in [x for x in meta.keys() if x.startswith('X-Container-Meta-')]:
        response[smart_str(k, strings_only=True)] = smart_str(meta[k], strings_only=True)
    l = [smart_str(x, strings_only=True) for x in meta['object_meta'] if x.startswith('X-Object-Meta-')]
    response['X-Container-Object-Meta'] = ','.join([x[14:] for x in l])
    response['X-Container-Block-Size'] = request.backend.block_size
    response['X-Container-Block-Hash'] = request.backend.hash_algorithm
    if 'until_timestamp' in meta:
        response['X-Container-Until-Timestamp'] = http_date(int(meta['until_timestamp']))
    for k, v in policy.iteritems():
        response[smart_str(format_header_key('X-Container-Policy-' + k), strings_only=True)] = smart_str(v, strings_only=True)

def get_object_headers(request):
    meta = get_header_prefix(request, 'X-Object-Meta-')
    if request.META.get('CONTENT_TYPE'):
        meta['Content-Type'] = request.META['CONTENT_TYPE']
    if request.META.get('HTTP_CONTENT_ENCODING'):
        meta['Content-Encoding'] = request.META['HTTP_CONTENT_ENCODING']
    if request.META.get('HTTP_CONTENT_DISPOSITION'):
        meta['Content-Disposition'] = request.META['HTTP_CONTENT_DISPOSITION']
    if request.META.get('HTTP_X_OBJECT_MANIFEST'):
        meta['X-Object-Manifest'] = request.META['HTTP_X_OBJECT_MANIFEST']
    return meta, get_sharing(request), get_public(request)

def put_object_headers(response, meta, restricted=False):
    response['ETag'] = meta['ETag']
    response['Content-Length'] = meta['bytes']
    response['Content-Type'] = meta.get('Content-Type', 'application/octet-stream')
    response['Last-Modified'] = http_date(int(meta['modified']))
    if not restricted:
        response['X-Object-Hash'] = meta['hash']
        response['X-Object-Modified-By'] = smart_str(meta['modified_by'], strings_only=True)
        response['X-Object-Version'] = meta['version']
        response['X-Object-Version-Timestamp'] = http_date(int(meta['version_timestamp']))
        for k in [x for x in meta.keys() if x.startswith('X-Object-Meta-')]:
            response[smart_str(k, strings_only=True)] = smart_str(meta[k], strings_only=True)
        for k in ('Content-Encoding', 'Content-Disposition', 'X-Object-Manifest',
                  'X-Object-Sharing', 'X-Object-Shared-By', 'X-Object-Allowed-To',
                  'X-Object-Public'):
            if k in meta:
                response[k] = smart_str(meta[k], strings_only=True)
    else:
        for k in ('Content-Encoding', 'Content-Disposition'):
            if k in meta:
                response[k] = meta[k]

def update_manifest_meta(request, v_account, meta):
    """Update metadata if the object has an X-Object-Manifest."""
    
    if 'X-Object-Manifest' in meta:
        etag = ''
        bytes = 0
        try:
            src_container, src_name = split_container_object_string('/' + meta['X-Object-Manifest'])
            objects = request.backend.list_objects(request.user_uniq, v_account,
                                src_container, prefix=src_name, virtual=False)
            for x in objects:
                src_meta = request.backend.get_object_meta(request.user_uniq,
                                        v_account, src_container, x[0], x[1])
                etag += src_meta['ETag']
                bytes += src_meta['bytes']
        except:
            # Ignore errors.
            return
        meta['bytes'] = bytes
        md5 = hashlib.md5()
        md5.update(etag)
        meta['ETag'] = md5.hexdigest().lower()

def update_sharing_meta(request, permissions, v_account, v_container, v_object, meta):
    if permissions is None:
        return
    allowed, perm_path, perms = permissions
    if len(perms) == 0:
        return
    ret = []
    r = ','.join(perms.get('read', []))
    if r:
        ret.append('read=' + r)
    w = ','.join(perms.get('write', []))
    if w:
        ret.append('write=' + w)
    meta['X-Object-Sharing'] = '; '.join(ret)
    if '/'.join((v_account, v_container, v_object)) != perm_path:
        meta['X-Object-Shared-By'] = perm_path
    if request.user_uniq != v_account:
        meta['X-Object-Allowed-To'] = allowed

def update_public_meta(public, meta):
    if not public:
        return
    meta['X-Object-Public'] = public

def validate_modification_preconditions(request, meta):
    """Check that the modified timestamp conforms with the preconditions set."""
    
    if 'modified' not in meta:
        return # TODO: Always return?
    
    if_modified_since = request.META.get('HTTP_IF_MODIFIED_SINCE')
    if if_modified_since is not None:
        if_modified_since = parse_http_date_safe(if_modified_since)
    if if_modified_since is not None and int(meta['modified']) <= if_modified_since:
        raise NotModified('Resource has not been modified')
    
    if_unmodified_since = request.META.get('HTTP_IF_UNMODIFIED_SINCE')
    if if_unmodified_since is not None:
        if_unmodified_since = parse_http_date_safe(if_unmodified_since)
    if if_unmodified_since is not None and int(meta['modified']) > if_unmodified_since:
        raise PreconditionFailed('Resource has been modified')

def validate_matching_preconditions(request, meta):
    """Check that the ETag conforms with the preconditions set."""
    
    etag = meta.get('ETag', None)
    
    if_match = request.META.get('HTTP_IF_MATCH')
    if if_match is not None:
        if etag is None:
            raise PreconditionFailed('Resource does not exist')
        if if_match != '*' and etag not in [x.lower() for x in parse_etags(if_match)]:
            raise PreconditionFailed('Resource ETag does not match')
    
    if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
    if if_none_match is not None:
        # TODO: If this passes, must ignore If-Modified-Since header.
        if etag is not None:
            if if_none_match == '*' or etag in [x.lower() for x in parse_etags(if_none_match)]:
                # TODO: Continue if an If-Modified-Since header is present.
                if request.method in ('HEAD', 'GET'):
                    raise NotModified('Resource ETag matches')
                raise PreconditionFailed('Resource exists or ETag matches')

def split_container_object_string(s):
    if not len(s) > 0 or s[0] != '/':
        raise ValueError
    s = s[1:]
    pos = s.find('/')
    if pos == -1 or pos == len(s) - 1:
        raise ValueError
    return s[:pos], s[(pos + 1):]

def copy_or_move_object(request, src_account, src_container, src_name, dest_account, dest_container, dest_name, move=False):
    """Copy or move an object."""
    
    meta, permissions, public = get_object_headers(request)
    src_version = request.META.get('HTTP_X_SOURCE_VERSION')
    try:
        if move:
            version_id = request.backend.move_object(request.user_uniq, src_account, src_container, src_name,
                                                        dest_account, dest_container, dest_name,
                                                        meta, False, permissions)
        else:
            version_id = request.backend.copy_object(request.user_uniq, src_account, src_container, src_name,
                                                        dest_account, dest_container, dest_name,
                                                        meta, False, permissions, src_version)
    except NotAllowedError:
        raise Forbidden('Not allowed')
    except (NameError, IndexError):
        raise ItemNotFound('Container or object does not exist')
    except ValueError:
        raise BadRequest('Invalid sharing header')
    except AttributeError, e:
        raise Conflict('\n'.join(e.data) + '\n')
    except QuotaError:
        raise RequestEntityTooLarge('Quota exceeded')
    if public is not None:
        try:
            request.backend.update_object_public(request.user_uniq, dest_account, dest_container, dest_name, public)
        except NotAllowedError:
            raise Forbidden('Not allowed')
        except NameError:
            raise ItemNotFound('Object does not exist')
    return version_id

def get_int_parameter(p):
    if p is not None:
        try:
            p = int(p)
        except ValueError:
            return None
        if p < 0:
            return None
    return p

def get_content_length(request):
    content_length = get_int_parameter(request.META.get('CONTENT_LENGTH'))
    if content_length is None:
        raise LengthRequired('Missing or invalid Content-Length header')
    return content_length

def get_range(request, size):
    """Parse a Range header from the request.
    
    Either returns None, when the header is not existent or should be ignored,
    or a list of (offset, length) tuples - should be further checked.
    """
    
    ranges = request.META.get('HTTP_RANGE', '').replace(' ', '')
    if not ranges.startswith('bytes='):
        return None
    
    ret = []
    for r in (x.strip() for x in ranges[6:].split(',')):
        p = re.compile('^(?P<offset>\d*)-(?P<upto>\d*)$')
        m = p.match(r)
        if not m:
            return None
        offset = m.group('offset')
        upto = m.group('upto')
        if offset == '' and upto == '':
            return None
        
        if offset != '':
            offset = int(offset)
            if upto != '':
                upto = int(upto)
                if offset > upto:
                    return None
                ret.append((offset, upto - offset + 1))
            else:
                ret.append((offset, size - offset))
        else:
            length = int(upto)
            ret.append((size - length, length))
    
    return ret

def get_content_range(request):
    """Parse a Content-Range header from the request.
    
    Either returns None, when the header is not existent or should be ignored,
    or an (offset, length, total) tuple - check as length, total may be None.
    Returns (None, None, None) if the provided range is '*/*'.
    """
    
    ranges = request.META.get('HTTP_CONTENT_RANGE', '')
    if not ranges:
        return None
    
    p = re.compile('^bytes (?P<offset>\d+)-(?P<upto>\d*)/(?P<total>(\d+|\*))$')
    m = p.match(ranges)
    if not m:
        if ranges == 'bytes */*':
            return (None, None, None)
        return None
    offset = int(m.group('offset'))
    upto = m.group('upto')
    total = m.group('total')
    if upto != '':
        upto = int(upto)
    else:
        upto = None
    if total != '*':
        total = int(total)
    else:
        total = None
    if (upto is not None and offset > upto) or \
        (total is not None and offset >= total) or \
        (total is not None and upto is not None and upto >= total):
        return None
    
    if upto is None:
        length = None
    else:
        length = upto - offset + 1
    return (offset, length, total)

def get_sharing(request):
    """Parse an X-Object-Sharing header from the request.
    
    Raises BadRequest on error.
    """
    
    permissions = request.META.get('HTTP_X_OBJECT_SHARING')
    if permissions is None:
        return None
    
    # TODO: Document or remove '~' replacing.
    permissions = permissions.replace('~', '')
    
    ret = {}
    permissions = permissions.replace(' ', '')
    if permissions == '':
        return ret
    for perm in (x for x in permissions.split(';')):
        if perm.startswith('read='):
            ret['read'] = list(set([v.replace(' ','').lower() for v in perm[5:].split(',')]))
            if '' in ret['read']:
                ret['read'].remove('')
            if '*' in ret['read']:
                ret['read'] = ['*']
            if len(ret['read']) == 0:
                raise BadRequest('Bad X-Object-Sharing header value')
        elif perm.startswith('write='):
            ret['write'] = list(set([v.replace(' ','').lower() for v in perm[6:].split(',')]))
            if '' in ret['write']:
                ret['write'].remove('')
            if '*' in ret['write']:
                ret['write'] = ['*']
            if len(ret['write']) == 0:
                raise BadRequest('Bad X-Object-Sharing header value')
        else:
            raise BadRequest('Bad X-Object-Sharing header value')
    
    # Keep duplicates only in write list.
    dups = [x for x in ret.get('read', []) if x in ret.get('write', []) and x != '*']
    if dups:
        for x in dups:
            ret['read'].remove(x)
        if len(ret['read']) == 0:
            del(ret['read'])
    
    return ret

def get_public(request):
    """Parse an X-Object-Public header from the request.
    
    Raises BadRequest on error.
    """
    
    public = request.META.get('HTTP_X_OBJECT_PUBLIC')
    if public is None:
        return None
    
    public = public.replace(' ', '').lower()
    if public == 'true':
        return True
    elif public == 'false' or public == '':
        return False
    raise BadRequest('Bad X-Object-Public header value')

def raw_input_socket(request):
    """Return the socket for reading the rest of the request."""
    
    server_software = request.META.get('SERVER_SOFTWARE')
    if server_software and server_software.startswith('mod_python'):
        return request._req
    if 'wsgi.input' in request.environ:
        return request.environ['wsgi.input']
    raise ServiceUnavailable('Unknown server software')

MAX_UPLOAD_SIZE = 5 * (1024 * 1024 * 1024) # 5GB

def socket_read_iterator(request, length=0, blocksize=4096):
    """Return a maximum of blocksize data read from the socket in each iteration.
    
    Read up to 'length'. If 'length' is negative, will attempt a chunked read.
    The maximum ammount of data read is controlled by MAX_UPLOAD_SIZE.
    """
    
    sock = raw_input_socket(request)
    if length < 0: # Chunked transfers
        # Small version (server does the dechunking).
        if request.environ.get('mod_wsgi.input_chunked', None) or request.META['SERVER_SOFTWARE'].startswith('gunicorn'):
            while length < MAX_UPLOAD_SIZE:
                data = sock.read(blocksize)
                if data == '':
                    return
                yield data
            raise BadRequest('Maximum size is reached')
        
        # Long version (do the dechunking).
        data = ''
        while length < MAX_UPLOAD_SIZE:
            # Get chunk size.
            if hasattr(sock, 'readline'):
                chunk_length = sock.readline()
            else:
                chunk_length = ''
                while chunk_length[-1:] != '\n':
                    chunk_length += sock.read(1)
                chunk_length.strip()
            pos = chunk_length.find(';')
            if pos >= 0:
                chunk_length = chunk_length[:pos]
            try:
                chunk_length = int(chunk_length, 16)
            except Exception, e:
                raise BadRequest('Bad chunk size') # TODO: Change to something more appropriate.
            # Check if done.
            if chunk_length == 0:
                if len(data) > 0:
                    yield data
                return
            # Get the actual data.
            while chunk_length > 0:
                chunk = sock.read(min(chunk_length, blocksize))
                chunk_length -= len(chunk)
                if length > 0:
                    length += len(chunk)
                data += chunk
                if len(data) >= blocksize:
                    ret = data[:blocksize]
                    data = data[blocksize:]
                    yield ret
            sock.read(2) # CRLF
        raise BadRequest('Maximum size is reached')
    else:
        if length > MAX_UPLOAD_SIZE:
            raise BadRequest('Maximum size is reached')
        while length > 0:
            data = sock.read(min(length, blocksize))
            if not data:
                raise BadRequest()
            length -= len(data)
            yield data

class SaveToBackendHandler(FileUploadHandler):
    """Handle a file from an HTML form the django way."""
    
    def __init__(self, request=None):
        super(SaveToBackendHandler, self).__init__(request)
        self.backend = request.backend
    
    def put_data(self, length):
        if len(self.data) >= length:
            block = self.data[:length]
            self.file.hashmap.append(self.backend.put_block(block))
            self.md5.update(block)
            self.data = self.data[length:]
    
    def new_file(self, field_name, file_name, content_type, content_length, charset=None):
        self.md5 = hashlib.md5()        
        self.data = ''
        self.file = UploadedFile(name=file_name, content_type=content_type, charset=charset)
        self.file.size = 0
        self.file.hashmap = []
    
    def receive_data_chunk(self, raw_data, start):
        self.data += raw_data
        self.file.size += len(raw_data)
        self.put_data(self.request.backend.block_size)
        return None
    
    def file_complete(self, file_size):
        l = len(self.data)
        if l > 0:
            self.put_data(l)
        self.file.etag = self.md5.hexdigest().lower()
        return self.file

class ObjectWrapper(object):
    """Return the object's data block-per-block in each iteration.
    
    Read from the object using the offset and length provided in each entry of the range list.
    """
    
    def __init__(self, backend, ranges, sizes, hashmaps, boundary):
        self.backend = backend
        self.ranges = ranges
        self.sizes = sizes
        self.hashmaps = hashmaps
        self.boundary = boundary
        self.size = sum(self.sizes)
        
        self.file_index = 0
        self.block_index = 0
        self.block_hash = -1
        self.block = ''
        
        self.range_index = -1
        self.offset, self.length = self.ranges[0]
    
    def __iter__(self):
        return self
    
    def part_iterator(self):
        if self.length > 0:
            # Get the file for the current offset.
            file_size = self.sizes[self.file_index]
            while self.offset >= file_size:
                self.offset -= file_size
                self.file_index += 1
                file_size = self.sizes[self.file_index]
            
            # Get the block for the current position.
            self.block_index = int(self.offset / self.backend.block_size)
            if self.block_hash != self.hashmaps[self.file_index][self.block_index]:
                self.block_hash = self.hashmaps[self.file_index][self.block_index]
                try:
                    self.block = self.backend.get_block(self.block_hash)
                except NameError:
                    raise ItemNotFound('Block does not exist')
            
            # Get the data from the block.
            bo = self.offset % self.backend.block_size
            bl = min(self.length, len(self.block) - bo)
            data = self.block[bo:bo + bl]
            self.offset += bl
            self.length -= bl
            return data
        else:
            raise StopIteration
    
    def next(self):
        if len(self.ranges) == 1:
            return self.part_iterator()
        if self.range_index == len(self.ranges):
            raise StopIteration
        try:
            if self.range_index == -1:
                raise StopIteration
            return self.part_iterator()
        except StopIteration:
            self.range_index += 1
            out = []
            if self.range_index < len(self.ranges):
                # Part header.
                self.offset, self.length = self.ranges[self.range_index]
                self.file_index = 0
                if self.range_index > 0:
                    out.append('')
                out.append('--' + self.boundary)
                out.append('Content-Range: bytes %d-%d/%d' % (self.offset, self.offset + self.length - 1, self.size))
                out.append('Content-Transfer-Encoding: binary')
                out.append('')
                out.append('')
                return '\r\n'.join(out)
            else:
                # Footer.
                out.append('')
                out.append('--' + self.boundary + '--')
                out.append('')
                return '\r\n'.join(out)

def object_data_response(request, sizes, hashmaps, meta, public=False):
    """Get the HttpResponse object for replying with the object's data."""
    
    # Range handling.
    size = sum(sizes)
    ranges = get_range(request, size)
    if ranges is None:
        ranges = [(0, size)]
        ret = 200
    else:
        check = [True for offset, length in ranges if
                    length <= 0 or length > size or
                    offset < 0 or offset >= size or
                    offset + length > size]
        if len(check) > 0:
            raise RangeNotSatisfiable('Requested range exceeds object limits')
        ret = 206
        if_range = request.META.get('HTTP_IF_RANGE')
        if if_range:
            try:
                # Modification time has passed instead.
                last_modified = parse_http_date(if_range)
                if last_modified != meta['modified']:
                    ranges = [(0, size)]
                    ret = 200
            except ValueError:
                if if_range != meta['ETag']:
                    ranges = [(0, size)]
                    ret = 200
    
    if ret == 206 and len(ranges) > 1:
        boundary = uuid.uuid4().hex
    else:
        boundary = ''
    wrapper = ObjectWrapper(request.backend, ranges, sizes, hashmaps, boundary)
    response = HttpResponse(wrapper, status=ret)
    put_object_headers(response, meta, public)
    if ret == 206:
        if len(ranges) == 1:
            offset, length = ranges[0]
            response['Content-Length'] = length # Update with the correct length.
            response['Content-Range'] = 'bytes %d-%d/%d' % (offset, offset + length - 1, size)
        else:
            del(response['Content-Length'])
            response['Content-Type'] = 'multipart/byteranges; boundary=%s' % (boundary,)
    return response

def put_object_block(request, hashmap, data, offset):
    """Put one block of data at the given offset."""
    
    bi = int(offset / request.backend.block_size)
    bo = offset % request.backend.block_size
    bl = min(len(data), request.backend.block_size - bo)
    if bi < len(hashmap):
        hashmap[bi] = request.backend.update_block(hashmap[bi], data[:bl], bo)
    else:
        hashmap.append(request.backend.put_block(('\x00' * bo) + data[:bl]))
    return bl # Return ammount of data written.

def hashmap_hash(request, hashmap):
    """Produce the root hash, treating the hashmap as a Merkle-like tree."""
    
    def subhash(d):
        h = hashlib.new(request.backend.hash_algorithm)
        h.update(d)
        return h.digest()
    
    if len(hashmap) == 0:
        return hexlify(subhash(''))
    if len(hashmap) == 1:
        return hashmap[0]
    
    s = 2
    while s < len(hashmap):
        s = s * 2
    h = [unhexlify(x) for x in hashmap]
    h += [('\x00' * len(h[0]))] * (s - len(hashmap))
    while len(h) > 1:
        h = [subhash(h[x] + h[x + 1]) for x in range(0, len(h), 2)]
    return hexlify(h[0])

def update_response_headers(request, response):
    if request.serialization == 'xml':
        response['Content-Type'] = 'application/xml; charset=UTF-8'
    elif request.serialization == 'json':
        response['Content-Type'] = 'application/json; charset=UTF-8'
    elif not response['Content-Type']:
        response['Content-Type'] = 'text/plain; charset=UTF-8'
    
    if not response.has_header('Content-Length') and not (response.has_header('Content-Type') and response['Content-Type'].startswith('multipart/byteranges')):
        response['Content-Length'] = len(response.content)
    
    if settings.TEST:
        response['Date'] = format_date_time(time())

def render_fault(request, fault):
    if settings.DEBUG or settings.TEST:
        fault.details = format_exc(fault)
    
    request.serialization = 'text'
    data = '\n'.join((fault.message, fault.details)) + '\n'
    response = HttpResponse(data, status=fault.code)
    update_response_headers(request, response)
    return response

def request_serialization(request, format_allowed=False):
    """Return the serialization format requested.
    
    Valid formats are 'text' and 'json', 'xml' if 'format_allowed' is True.
    """
    
    if not format_allowed:
        return 'text'
    
    format = request.GET.get('format')
    if format == 'json':
        return 'json'
    elif format == 'xml':
        return 'xml'
    
    for item in request.META.get('HTTP_ACCEPT', '').split(','):
        accept, sep, rest = item.strip().partition(';')
        if accept == 'application/json':
            return 'json'
        elif accept == 'application/xml' or accept == 'text/xml':
            return 'xml'
    
    return 'text'

def api_method(http_method=None, format_allowed=False, user_required=True):
    """Decorator function for views that implement an API method."""
    
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            try:
                if http_method and request.method != http_method:
                    raise BadRequest('Method not allowed.')
                if user_required and getattr(request, 'user', None) is None:
                    raise Unauthorized('Access denied')
                
                # The args variable may contain up to (account, container, object).
                if len(args) > 1 and len(args[1]) > 256:
                    raise BadRequest('Container name too large.')
                if len(args) > 2 and len(args[2]) > 1024:
                    raise BadRequest('Object name too large.')
                
                # Fill in custom request variables.
                request.serialization = request_serialization(request, format_allowed)
                request.backend = connect_backend()
                
                response = func(request, *args, **kwargs)
                update_response_headers(request, response)
                return response
            except Fault, fault:
                return render_fault(request, fault)
            except BaseException, e:
                logger.exception('Unexpected error: %s' % e)
                fault = ServiceUnavailable('Unexpected error')
                return render_fault(request, fault)
            finally:
                if getattr(request, 'backend', None) is not None:
                    request.backend.close()
        return wrapper
    return decorator
