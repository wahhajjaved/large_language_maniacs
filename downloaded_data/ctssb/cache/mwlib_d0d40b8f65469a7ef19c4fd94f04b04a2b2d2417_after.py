#! /usr/bin/env python

"""WSGI server interface to mw-render and mw-zip"""

import os
import re
import simplejson
import subprocess

from mwlib import utils
from mwlib import wsgi

# ==============================================================================

class Application(wsgi.Application):
    metabook_filename = 'metabook.json'
    error_filename = 'errors.txt'
    status_filename = 'status.txt'
    output_filename = 'output'
    
    collection_id_rex = re.compile(r'^[a-z0-9]+$')
    
    def __init__(self, cache_dir,
        mwrender_cmd, mwrender_logfile,
        mwzip_cmd, mwzip_logfile):
        self.cache_dir = utils.ensure_dir(cache_dir)
        self.mwrender_cmd = mwrender_cmd
        self.mwrender_logfile = mwrender_logfile
        self.mwzip_cmd = mwzip_cmd
        self.mwzip_logfile = mwzip_logfile
    
    def dispatch(self, request):
        try:
            command = request.post_data['command']
        except KeyError:
            return self.error_response('no command given')
        try:
            method = getattr(self, 'do_%s' % command)
        except AttributeError:
            return self.error_response('invalid command %r' % command)
        try:
            return method(request.post_data)
        except Exception, exc:
            return self.error_response('error executing command %r: %s' % (
                command, exc,
            ))
        
    def json_response(self, data):
        return wsgi.Response(
            content=simplejson.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
    
    def error_response(self, error):
        if isinstance(error, str):
            error = unicode(error, 'utf-8', 'ignore')
        elif not isinstance(error, unicode):
            error = unicode(repr(error), 'ascii')
        return self.json_response({
            'error': error,
        })
    
    def get_collection_dir(self, collection_id):
        return os.path.join(self.cache_dir, collection_id)
    
    def get_collection(self, post_data):
        collection_id = post_data.get('collection_id')
        if not collection_id or not self.collection_id_rex.match(collection_id):
            raise RuntimeError('invalid collection ID %r' % collection_id)
        collection_dir = self.get_collection_dir(collection_id)
        if not os.path.exists(collection_dir):
            raise RuntimeError('no such collection: %r' % collection_id)
        return collection_id
    
    def new_collection(self):
        while True:
            collection_id = utils.uid()
            collection_dir = self.get_collection_dir(collection_id)
            if os.path.isdir(collection_dir):
                continue
            os.makedirs(collection_dir)
            return collection_id
    
    def get_path(self, collection_id, filename):
        return os.path.join(self.get_collection_dir(collection_id), filename)
    
    def do_render(self, post_data):
        try:
            metabook_data = post_data['metabook']
            base_url = post_data['base_url']
            writer = post_data['writer']
        except KeyError, exc:
            return self.error_response('POST argument required: %s' % exc)
        writer_options = post_data.get('writer_options', '')
        template_blacklist = post_data.get('template_blacklist', '')
        
        collection_id = self.new_collection()
        
        metabook_path = self.get_path(collection_id, self.metabook_filename)
        f = open(metabook_path, 'wb')
        f.write(metabook_data)
        f.close()
        
        args=[
            self.mwrender_cmd,
            '--logfile', self.mwrender_logfile,
            '--error-file', self.get_path(collection_id, self.error_filename),
            '--status-file', self.get_path(collection_id, self.status_filename),
            '--metabook', metabook_path,
            '--conf', base_url,
            '--writer', writer,
            '--output', self.get_path(collection_id, self.output_filename),
        ]
        if writer_options:
            args.extend(['--writer-options', writer_options])
        if template_blacklist:
            args.extend(['--template-blacklist', template_blacklist])
        
        try:
            subprocess.Popen(executable=self.mwrender_cmd, args=args)
        except OSError, exc:
            raise RuntimeError('Could not execute command %r: %s' % (
                self.mwrender_cmd, exc,
            ))
        
        return self.json_response({
            'collection_id': collection_id,
        })
    
    def read_status_file(self, collection_id):
        try:
            f = open(self.get_path(collection_id, self.status_filename), 'rb')
            return simplejson.loads(f.read())
            f.close()
        except (IOError, ValueError):
            return {'progress': 0}
    
    def do_render_status(self, post_data):
        collection_id = self.get_collection(post_data)
        
        if os.path.exists(self.get_path(collection_id, self.output_filename)):
            return self.json_response({
                'collection_id': collection_id,
                'state': 'finished',
            })
        
        error_path = self.get_path(collection_id, self.error_filename)
        if os.path.exists(error_path):
            text = unicode(open(error_path, 'rb').read(), 'utf-8', 'ignore')
            return self.json_response({
                'collection_id': collection_id,
                'state': 'failed',
                'error': text,
            })
        
        return self.json_response({
            'collection_id': collection_id,
            'state': 'progress',
            'status': self.read_status_file(collection_id),
        })
        
    def do_download(self, post_data):
        collection_id = self.get_collection(post_data)
        filename = self.get_path(collection_id, self.output_filename)
        content = open(filename, 'rb').read()
        status = self.read_status_file(collection_id)
        response = wsgi.Response(content=content)
        if 'content_type' in status:
            response.headers['Content-Type'] = status['content_type'].encode('utf-8', 'ignore')
        if 'file_extension' in status:
            response.headers['Content-Disposition'] = 'inline;filename="collection.%s"' %  (
                status['file_extension'].encode('utf-8', 'ignore'),
            )
        return response
    
    def do_zip_post(self, post_data):
        try:
            metabook_data = post_data['metabook']
            base_url = post_data['base_url']
            post_url = post_data['post_url']
        except KeyError, exc:
            return self.error_response('POST argument required: %s' % exc)
        template_blacklist = post_data.get('template_blacklist', '')
        
        collection_id = self.new_collection()
        
        metabook_path = self.get_path(collection_id, self.metabook_filename)
        open(metabook_path, 'wb').write(metabook_data)
        
        args = [
            self.mwzip_cmd,
            '--logfile', self.mwzip_logfile,
            '--metabook', metabook_path,
            '--conf', base_url,
            '--posturl', post_url,
        ]
        if template_blacklist:
            args.extend(['--template-blacklist', template_blacklist])
        try:
            subprocess.Popen(executable=self.mwzip_cmd, args=args)
        except OSError, exc:
            raise RuntimeError('Could not execute command %r: %s' % (
                self.mwzip_cmd, exc,
            ))
        
        return self.json_response({'state': 'ok'})
    
