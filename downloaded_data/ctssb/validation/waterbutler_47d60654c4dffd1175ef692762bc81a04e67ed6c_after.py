import os
import asyncio
import hashlib

from lxml import objectify
from boto.s3.connection import S3Connection

from waterbutler.core import streams
from waterbutler.core import provider
from waterbutler.core import exceptions

from waterbutler.s3 import settings
from waterbutler.s3.metadata import S3Revision
from waterbutler.s3.metadata import S3FileMetadata
from waterbutler.s3.metadata import S3FolderMetadata
from waterbutler.s3.metadata import S3FolderKeyMetadata
from waterbutler.s3.metadata import S3FileMetadataHeaders


class S3Provider(provider.BaseProvider):
    """Provider for the Amazon's S3
    """

    def __init__(self, auth, credentials, settings):
        """
        Note: Neither `S3Connection#__init__` nor `S3Connection#get_bucket`
        sends a request.
        :param dict auth: Not used
        :param dict credentials: Dict containing `access_key` and `secret_key`
        :param dict settings: Dict containing `bucket`
        """
        super().__init__(auth, credentials, settings)
        self.connection = S3Connection(credentials['access_key'], credentials['secret_key'])
        self.bucket = self.connection.get_bucket(settings['bucket'], validate=False)

    def can_intra_copy(self, dest_provider):
        return type(self) == type(dest_provider)

    def can_intra_move(self, dest_provider):
        return type(self) == type(dest_provider)

    @asyncio.coroutine
    def intra_copy(self, dest_provider, source_options, dest_options):
        """Copy key from one S3 bucket to another. The credentials specified in
        `dest_provider` must have read access to `source.bucket`.
        """
        dest_key = dest_provider.bucket.new_key(dest_options['path'])
        source_path = '/' + os.path.join(self.settings['bucket'], source_options['path'])
        headers = {'x-amz-copy-source': source_path}
        url = dest_key.generate_url(
            settings.TEMP_URL_SECS,
            'PUT',
            headers=headers,
        )
        yield from self.make_request(
            'PUT',
            url,
            headers=headers,
            expects=(200, ),
            throws=exceptions.IntraCopyError,
        )
        return (yield from dest_provider.metadata(dest_options['path']))

    @asyncio.coroutine
    def download(self, path, accept_url=False, **kwargs):
        """Returns a ResponseWrapper (Stream) for the specified path
        raises FileNotFoundError if the status from S3 is not 200

        :param str path: Path to the key you want to download
        :param dict **kwargs: Additional arguments that are ignored
        :rtype ResponseWrapper:
        :raises: waterbutler.FileNotFoundError
        """
        if not path:
            raise exceptions.ProviderError('Path can not be empty', code=400)

        key = self.bucket.new_key(path)
        url = key.generate_url(settings.TEMP_URL_SECS, headers={'response-content-disposition': 'attachment'})

        if accept_url:
            return url

        resp = yield from self.make_request(
            'GET',
            url,
            expects=(200, ),
            throws=exceptions.DownloadError,
        )

        return streams.ResponseStreamReader(resp)

    @asyncio.coroutine
    def upload(self, stream, path, **kwargs):
        """Uploads the given stream to S3
        :param ResponseWrapper stream: The stream to put to S3
        :param str path: The full path of the key to upload to/into
        :rtype ResponseWrapper:
        """
        stream.add_writer('md5', streams.HashStreamWriter(hashlib.md5))
        key = self.bucket.new_key(path)
        url = key.generate_url(settings.TEMP_URL_SECS, 'PUT')
        resp = yield from self.make_request(
            'PUT', url,
            data=stream,
            headers={'Content-Length': str(stream.size)},
            expects=(200, 201),
            throws=exceptions.UploadError,
        )
        # md5 is returned as ETag header as long as server side encryption is not used.
        # TODO: nice assertion error goes here
        assert resp.headers['ETag'].replace('"', '') == stream.writers['md5'].hexdigest

        return (yield from self.metadata(path))

    @asyncio.coroutine
    def delete(self, path, **kwargs):
        """Deletes the key at the specified path
        :param str path: The path of the key to delete
        :rtype ResponseWrapper:
        """
        key = self.bucket.new_key(path)
        url = key.generate_url(settings.TEMP_URL_SECS, 'DELETE')
        yield from self.make_request(
            'DELETE',
            url,
            expects=(200, 204),
            throws=exceptions.DeleteError,
        )

    @asyncio.coroutine
    def revisions(self, path, **kwargs):
        """Get past versions of the requested key
        :param str path: The path to a key
        :rtype list:
        """
        url = self.bucket.generate_url(settings.TEMP_URL_SECS, 'GET', query_parameters={'versions': ''})
        resp = yield from self.make_request(
            'GET',
            url,
            params={'prefix': path, 'delimiter': '/'},
            expects=(200, ),
            throws=exceptions.MetadataError,
        )
        content = yield from resp.read_and_close()
        obj = objectify.fromstring(content)
        return [
            S3Revision(path, item).serialized()
            for item in getattr(obj, 'Version', [])
        ]

    @asyncio.coroutine
    def metadata(self, path, **kwargs):
        """Get Metadata about the requested file or folder
        :param str path: The path to a key or folder
        :rtype dict:
        :rtype list:
        """
        if not path or path.endswith('/'):
            return (yield from self._folder_metadata(path))

        return (yield from self._key_metadata(path))

    @asyncio.coroutine
    def _key_metadata(self, path):
        url = self.bucket.new_key(path).generate_url(settings.TEMP_URL_SECS, 'HEAD')
        resp = yield from self.make_request(
            'HEAD',
            url,
            expects=(200, ),
            throws=exceptions.MetadataError,
        )
        return S3FileMetadataHeaders(path, resp.headers).serialized()

    @asyncio.coroutine
    def _folder_metadata(self, path):
        url = self.bucket.generate_url(settings.TEMP_URL_SECS, 'GET')
        resp = yield from self.make_request(
            'GET',
            url,
            params={'prefix': path, 'delimiter': '/'},
            expects=(200, ),
            throws=exceptions.MetadataError,
        )
        contents = yield from resp.read_and_close()
        obj = objectify.fromstring(contents)

        items = [
            S3FolderMetadata(item).serialized()
            for item in getattr(obj, 'CommonPrefixes', [])
            if item.Prefix.text
        ]

        for content in getattr(obj, 'Contents', []):
            if not content.Key.text or content.Key.text == path:
                continue

            if content.Key.text.endswith('/'):
                items.append(S3FolderKeyMetadata(content).serialized())
            else:
                items.append(S3FileMetadata(content).serialized())

        return items
