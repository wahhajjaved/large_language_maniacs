#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
    Class to interface with google drive api
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import socket
import time
import httplib2
import oauth2client
from oauth2client import client, tools
from apiclient import discovery
from apiclient.http import MediaIoBaseDownload
from apiclient.errors import HttpError

SCOPES = 'https://www.googleapis.com/auth/drive'
CLIENT_SECRET_FILE = 'sync_app/client_secrets.json'
APPLICATION_NAME = 'Python API'

fields = ', '.join(('id', 'name', 'md5Checksum', 'modifiedTime', 'size',
                    'parents', 'fileExtension', 'mimeType', 'webContentLink'))
list_fields = 'kind, nextPageToken, files(%s)' % fields
CHUNKSIZE = 2 * 1024 * 1024


class TExecuteException(Exception):
    pass


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.gdrive')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'gdrive.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        credentials = tools.run_flow(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials


def t_execute(request):
    timeout = 1
    while True:
        try:
            return request.execute()
        except socket.error:
            time.sleep(timeout)
        except HttpError as exc:
            if 'user rate limit exceeded' in exc.content.lower():
                if timeout > 1:
                    print('timeout %s' % timeout)
                time.sleep(timeout)
                timeout *= 2
                if timeout >= 64:
                    raise
            elif 'sufficient permissions' in exc.content.lower():
                raise TExecuteException('insufficient permission')
            else:
                print(dir(exc))
                print('content', exc.content)
                print('response', exc.resp)
                raise TExecuteException(exc)


class GdriveInstance(object):
    """ class to make use of google python api """

    def __init__(self, app='drive', version='v3', number_to_process=-1):
        """ init function """

        self.list_of_keys = {}
        self.list_of_mimetypes = {}
        self.items_processed = 0
        self.list_of_folders = {}
        self.list_of_items = {}

        self.credentials = get_credentials()
        http = self.credentials.authorize(httplib2.Http())
        self.service = discovery.build(app, version, http=http)
        self.gfiles = self.service.files()

        self.number_to_process = number_to_process

    def process_response(self, response, callback_fn=None, resptype='files'):
        """ callback_fn applied to each item returned by response """

        if not callback_fn:
            return 0
        for item_ in response['files']:
            if self.number_to_process > 0 \
                    and self.items_processed > self.number_to_process:
                return 0
            if callback_fn:
                callback_fn(item_)
            self.items_processed += 1
        return 1

    def process_request(self, request, callback_fn=None):
        """ call process_response until new_request exists or until stopped """
        response = t_execute(request)

        new_request = True
        while new_request:
            if self.process_response(response, callback_fn) == 0:
                return
            next_token = response.get('nextPageToken', None)
            if next_token is None:
                return

            new_request = self.gfiles.list(pageToken=next_token,
                                           fields=list_fields)
            if not new_request:
                return
            request = new_request
            try:
                response = t_execute(request)
            except HttpError:
                time.sleep(5)
                print('HttpError')
                response = t_execute(request)
        return

    def list_files(self, callback_fn, searchstr=None):
        """ list non-directory files """
        query_string = 'mimeType != "application/vnd.google-apps.folder"'
        if searchstr:
            query_string += ' and name contains "%s"' % searchstr

        request = self.gfiles.list(q=query_string, fields=list_fields)
        return self.process_request(request, callback_fn)

    def get_file(self, fid):
        request = self.gfiles.get(fileId=fid, fields=fields)
        return t_execute(request)

    def get_folders(self, callback_fn, searchstr=None):
        """ get folders """
        query_string = 'mimeType = "application/vnd.google-apps.folder"'
        if searchstr:
            query_string += ' and name contains "%s"' % searchstr
        request = self.gfiles.list(q=query_string, fields=list_fields)
        return self.process_request(request, callback_fn)

    def download(self, fileid, exportfile, md5sum=None, export_mimetype=None):
        """ download using dlink url """
        dirname = os.path.dirname(exportfile)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        if export_mimetype:
            request = self.gfiles.export_media(fileId=fileid,
                                               mimeType=export_mimetype)
        else:
            request = self.gfiles.get_media(fileId=fileid)
        with open('%s.new' % exportfile, 'wb') as outfile:
            downloader = MediaIoBaseDownload(outfile, request)
            try:
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    prog = status.progress()
                    if status.total_size is None:
                        break
                    if prog < 1.0:
                        print('total_size', status.total_size)
                        print('progress', status.progress() * 100)
            except HttpError as exc:
                print('download', exc)
                raise
        if md5sum:
            from sync_app.util import get_md5, get_filetype
            md_ = get_md5('%s.new' % exportfile)
            if md_ != md5sum:
                ftype = get_filetype('%s.new' % exportfile)
                if 'PDF document' in ftype or 'JPEG image data' in ftype:
                    pass
                else:
                    print(get_filetype('%s.new' % exportfile))
                    raise TypeError('%s md_ %s md5sum %s' % (exportfile, md_,
                                                             md5sum))
        os.rename('%s.new' % exportfile, exportfile)
        return True

    def upload(self, fname, parent_id):
        """ upload fname and assign parent_id if provided """
        assert parent_id is not None
        fn_ = os.path.basename(fname)
        body_obj = {'name': fn_,
                    'parents': [parent_id]}
        request = self.gfiles.create(body=body_obj, media_body=fname)
        response = t_execute(request)
        fid = response['id']
        return fid

    def set_parent_id(self, fid, parent_id):
        """ set parent_id """
        request = self.get_file(fid)
        response = t_execute(request)
        previous_pids = response['parents']
        request = self.gfiles.update(fileId=fid, addParents=parent_id,
                                     removeParents=previous_pids,
                                     fields=fields)
        return t_execute(request)

    def rename(self, fid, new_filename):
        body_obj = {'name': new_filename}
        request = self.gfiles.update(fileId=fid, body=body_obj, fields=fields)
        return t_execute(request)

    def create_directory(self, dname, parent_id):
        """ create directory, assign parent_id if supplied """
        assert parent_id is not None
        dname = os.path.basename(dname)
        body_obj = {'name': dname,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]}
#        print(body_obj)
        request = self.gfiles.create(body=body_obj, fields=fields)
        try:
            response = t_execute(request)
        except TExecuteException:
            print('dname:', dname)
            print('parent_id:', parent_id)
            print('body_obj:', body_obj)
            raise
        return response

    def delete_file(self, fileid):
        """ delete file by fileid """
        request = self.gfiles.delete(fileId=fileid)
        try:
            response = t_execute(request)
        except Exception as exc:
            print('delete', exc)
            raise
#            return False
        return response

    def get_parents(self, fids=None):
        """ get parents of files by fileid """
        if not fids:
            return
        parents_output = []
        for fid in fids:
            request = self.get_file(fid)
            response = t_execute(request)
            parents_output.extend(response['parents'])
        return parents_output


def test_gdrive_instance():
    """ test GdriveInstance """
    from nose.tools import raises
    tmp = GdriveInstance()
    assert tmp.process_response(None) == 0

    class MockRequest(object):
        """ ... """
        def execute(self):
            """ ... """
            pass
    assert tmp.process_request(MockRequest()) is None
    assert tmp.get_parents() is None

    @raises(TExecuteException)
    def test_tmp():
        """ ... """
        tmp.get_parents(fids=range(10))
    test_tmp()
