# -*- coding: utf-8 -*-

import platform
from hashlib import sha1
from base64 import urlsafe_b64encode

from .config import _BLOCK_SIZE

try:
    import zlib
    binascii = zlib
except ImportError:
    zlib = None
    import binascii

from requests.compat import is_py2

from .exceptions import QiniuServiceException
from . import __version__


sys_info = '{0}; {1}'.format(platform.system(), platform.machine())
py_ver = platform.python_version()

USER_AGENT = 'QiniuPython/{0} ({1}; ) Python/{2}'.format(__version__, sys_info, py_ver)


def base64Encode(data):
    if not is_py2:
        if isinstance(data, str):
            data = bytes(data, 'utf-8')
    ret = urlsafe_b64encode(data)
    if not is_py2:
        if isinstance(data, bytes):
            ret = ret.decode('utf-8')
    return ret


def localFileCrc32(filePath):
    crc = 0
    with open(filePath, 'rb') as f:
        for block in _fileIter(f, _BLOCK_SIZE):
            crc = binascii.crc32(block, crc) & 0xFFFFFFFF
    return crc


def crc32(data):
    if not is_py2:
        if isinstance(data, str):
            data = bytes(data, 'utf-8')
    return binascii.crc32(data) & 0xffffffff


def _ret(req):
    ret = req.json() if req.text != '' else {}
    if req.status_code//100 != 2:
        reqId = req.headers['X-Reqid']
        raise QiniuServiceException(req.status_code, ret['error'], reqId)
    return ret


def _fileIter(inputStream, size):
    d = inputStream.read(size)
    while d:
        yield d
        d = inputStream.read(size)


def _sha1(data):
    h = sha1()
    h.update(data)
    d = h.digest()
    if not is_py2:
        if isinstance(data, bytes):
            d = ret.decode('ascii')
    return d


def _etag(inputStream):
    l = [_sha1(block) for block in _fileIter(inputStream, 4 * 1024 * 1024)]
    if len(l) == 1:
        return base64Encode('\x16' + l[0])
    return base64Encode('\x96' + _sha1(''.join(l)))


def etag(filePath):
    with open(filePath, 'rb') as f:
        return _etag(f)
