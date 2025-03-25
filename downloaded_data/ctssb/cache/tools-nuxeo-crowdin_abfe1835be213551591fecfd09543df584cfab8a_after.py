#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-
"""
Handles download/push from/to Crowdin.

Usage: ./crowdin_updater.py [options] project

Options:
    -h / --help
        Print this message and exit.

    See other options below (TODO)
"""

import string, sys, os, shutil, zipfile, gzip, requests, argparse
from StringIO import StringIO
from xml.dom import minidom

ENV_CROWDIN_API_KEY = 'CROWDIN_API_KEY'


class CrowdinUpdater:

    """
    Handles download/push from/to Crowdin.

    The Crowdin API key must be set in the "CROWDIN_API_KEY" environment variable.
    """
    def __init__(self, project, format=None):
        self.project = project
        self.format = format
        if ENV_CROWDIN_API_KEY not in os.environ:
            raise ValueError('Missing Crowdin API key in environment, please set %s environment variable.'
                % ENV_CROWDIN_API_KEY)
        self.key = os.environ[ENV_CROWDIN_API_KEY].strip()

    def build(self):
        params = {'key': self.key}
        r = requests.get('https://api.crowdin.com/api/project/%s/export' %(self.project,), params=params)
        res = self.parseXMLResponse(r)
        if res[0] < 0:
            raise ValueError("Build failed: %s" %(res[1],))
        return res

    def download(self, outputdir, build=True, package=None, parentdir=None):
        if package is None:
            package = "all"
        if build is True:
            # build first to make sure translations are up to date
            self.build()
        # download translations
        params = {'key': self.key}
        r = requests.get('https://api.crowdin.com/api/project/%s/download/%s.zip' %(self.project, package), params=params, verify=False)
        res = self.parseXMLResponse(r)
        if res[0] == -2:
            # consider it's the zip response
            zipdata = StringIO(r.content)
            with zipfile.ZipFile(zipdata) as zf:
                for filepath in zf.namelist():
                    # let's skip folder entries
                    if not filepath.endswith('/'):
                        filename = os.path.basename(filepath)
                        if filename:
                            # making sure that filepath matches pattern <lang>/<parent>/<filename>
                            language = filepath.split('/')[0]
                            if os.path.dirname(filepath).replace(language, '').strip('/') == (parentdir.strip('/') if parentdir else ''):
                                if self.format == 'json':
                                    root, ext = os.path.splitext(filename)
                                    target_filename = '%s-%s%s' % (root, language, ext)
                                else:
                                    target_filename = filename
                                target = file(os.path.join(outputdir, target_filename), "wb")
                                source = zf.open(filepath)
                                with source, target:
                                    shutil.copyfileobj(source, target)
        else:
            raise ValueError('Download failed: %s' % res[1])
        return res

    def upload(self, inputfile, parentdir=None):
        data = {
            'update_option': 'update_as_unapproved',
        }
        files = {
            'files[%s]' % os.path.join(parentdir or '', os.path.basename(inputfile)): open(inputfile, 'rb')
        }
        r = requests.post('https://api.crowdin.com/api/project/%s/update-file?key=%s' %(self.project, self.key), data=data, files=files)
        res = self.parseXMLResponse(r)
        if res[0] <= 0:
            raise ValueError('Upload failed: %s' % res[1])
        return res

    # Returns a tuple (error code, message)
    #
    # Errors code:
    # -2 if not a status response
    # -1 if error
    # 1 if success
    # 0 if unknown status
    def parseXMLResponse(self, r):
        if not r.headers['content-type'].startswith('text/xml'):
            return (-2, 'Wrong response content type: %s' % (r.headers['content-type'],))
        xmldoc = minidom.parseString(r.text)
        errors = xmldoc.getElementsByTagName('error')
        if errors.length != 0:
            error = errors.item(0)
            message = 'unknown error'
            messages = error.getElementsByTagName('message')
            if messages.length != 0:
                message = messages.item(0).firstChild.nodeValue
            return (-1, message)
        successes = xmldoc.getElementsByTagName('success')
        if successes.length != 0:
            success = successes.item(0)
            if success.hasAttribute('status'):
                return (1, success.attributes['status'].value)
            else:
                return (1, 'no status')
        return (0, 'unknown status')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', help='the Crowdin project name (mandatory)')
    parser.add_argument('-F', dest='format', help='Crowdin project format, possible values: "json" only for now')
    parser.add_argument('--uc', dest='update_crowdin', action='store_true', help='Update Crowdin from Nuxeo')
    parser.add_argument('-f', dest='inputfile', help='Update file path')
    parser.add_argument('--un', dest='update_nuxeo', action='store_true', help='Update Nuxeo from Crowdin')
    parser.add_argument('-o', dest='outputdir', help='Output directory')
    parser.add_argument('-p', dest='parentdir', help='Crowdin parent folder')
    args = parser.parse_args()

    cu = CrowdinUpdater(args.project, format=args.format)
    if args.update_crowdin:
        cu.upload(args.inputfile, parentdir=args.parentdir)
    if args.update_nuxeo:
        cu.download(args.outputdir, parentdir=args.parentdir)

if __name__ == '__main__':
    main()
