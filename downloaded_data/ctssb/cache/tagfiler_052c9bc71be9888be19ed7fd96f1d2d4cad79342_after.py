

# 
# Copyright 2010 University of Southern California
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import re
import urllib
import web
import psycopg2
import os
import logging
import subprocess
import itertools
import socket
import datetime
import dateutil.parser
import pytz
import traceback
import distutils.sysconfig
import sys
import random
import time
import math
import string
from logging.handlers import SysLogHandler
import json
try:
    import webauthn
except:
    pass

# we interpret RFC 3986 reserved chars as metasyntax for dispatch and
# structural understanding of URLs, and all escaped or
# "percent-encoded" sequences as payload within that structure.
# clients MUST NOT percent-encode the metacharacters structuring the
# query, and MUST percent-encode those characters when they are meant
# to form parts of the payload strings.  the client MAY percent-encode
# other non-reserved characters but it is not necessary.
#
# we dispatch everything through parser and then dispatch on AST.
#
# see Application.__init__() and prepareDispatch() for real dispatch
# see rules = [ ... ] for real matching rules

render = None

""" Set the logger """
logger = logging.getLogger('tagfiler')

filehandler = logging.FileHandler('/var/www/tagfiler-logs/messages')
fileformatter = logging.Formatter('%(asctime)s %(name)s: %(levelname)s: %(message)s')
filehandler.setFormatter(fileformatter)
logger.addHandler(filehandler)

sysloghandler = SysLogHandler(address='/dev/log', facility=SysLogHandler.LOG_LOCAL1)
syslogformatter = logging.Formatter('%(name)s: %(levelname)s: %(message)s')
sysloghandler.setFormatter(syslogformatter)
logger.addHandler(sysloghandler)

logger.setLevel(logging.INFO)

if hasattr(json, 'write'):
    jsonWriter = json.write
elif hasattr(json, 'dumps'):
    jsonWriter = json.dumps
else:
    raise RuntimeError('Could not configure JSON library.')

def urlquote(url):
    "define common URL quote mechanism for registry URL value embeddings"
    if type(url) != type('text'):
        url = str(url)
    return urllib.quote(url, safe="")

def urlunquote(url):
    if type(url) != type('text'):
        url = str(url)
    return urllib.unquote_plus(url)

def parseBoolString(theString):
    if theString.lower() in [ 'true', 't', 'yes', 'y' ]:
        return True
    else:
        return False
              
def predlist_linearize(predlist):
    def pred_linearize(pred):
        vals = [ urlquote(val) for val in pred['vals'] ]
        vals.sort()
        vals = ','.join(vals)
        return '%s%s%s' % (urlquote(pred['tag']), pred['op'], vals)
    predlist = [ pred_linearize(pred) for pred in predlist ]
    predlist.sort()
    return ';'.join(predlist)

def reduce_name_pred(x, y):
    if x['tag'] == 'name' and x['op'] == '=' and len(x['vals']) > 0:
        return x['vals'][0]
    elif y['tag'] == 'name' and y['op'] == '=' and len(y['vals']) > 0:
        return y['vals'][0]
    else:
        return None
            
def make_filter(allowed):
    allchars = string.maketrans('', '')
    delchars = ''.join([c for c in allchars if c not in allowed])
    return lambda s, a=allchars, d=delchars: (str(s)).translate(a, d)

idquote = make_filter(string.letters + string.digits + '_-:.' )

def buildPolicyRules(rules, fatal=False):
    remap = dict()
    for rule in rules:
        srcrole, dstrole, readers, writers = rule.split(';', 4)
        srcrole = urllib.unquote(srcrole.strip())
        dstrole = urllib.unquote(dstrole.strip())
        readers = readers.strip()
        writers = writers.strip()
        if remap.has_key(srcrole):
            web.debug('Policy rule "%s" duplicates already-mapped source role.' % rule)
            if fatal:
                raise KeyError()
            else:
                continue
        if dstrole == '':
            web.debug('Policy rule "%s" has illegal empty destination role.' % rule)
            if fatal:
                raise ValueError()
            else:
                continue
        if readers != '':
            readers = [ urllib.unquote(reader.strip()) for reader in readers.split(',') ]
            readers = [ reader for reader in readers if reader != '' ]
        else:
            readers = []
        if writers != '':
            writers = [ urllib.unquote(writer.strip()) for writer in writers.split(',') ]
            writers = [ writer for writer in writers if writer != '' ]
        else:
            writers = []
        remap[srcrole] = (dstrole, readers, writers)
    return remap

class WebException (web.HTTPError):
    def __init__(self, status, data='', headers={}, desc='%s'):
        self.detail = urlquote(desc % data)
        web.debug(self.detail, desc, data)
        data = render.Error(status, desc, data)
        m = re.match('.*MSIE.*',
                     web.ctx.env.get('HTTP_USER_AGENT', 'unknown'))
        if m:
            status = '200 OK'
        web.HTTPError.__init__(self, status, headers=headers, data=data)

class NotFound (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '404 Not Found'
        desc = 'The requested %s could not be found.'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

class Forbidden (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '403 Forbidden'
        desc = 'The requested %s is forbidden.'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

class Unauthorized (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '401 Unauthorized'
        desc = 'The requested %s requires authorization.'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

class BadRequest (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '400 Bad Request'
        desc = 'The request is malformed. %s'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

class Conflict (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '409 Conflict'
        desc = 'The request conflicts with the state of the server. %s'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

class IntegrityError (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '500 Internal Server Error'
        desc = 'The request execution encountered a integrity error: %s.'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

class RuntimeError (WebException):
    "provide an exception we can catch in our own transactions"
    def __init__(self, data='', headers={}):
        status = '500 Internal Server Error'
        desc = 'The request execution encountered a runtime error: %s.'
        WebException.__init__(self, status, headers=headers, data=data, desc=desc)

# BUG: use locking to avoid assumption that global interpreter lock protects us?
configDataCache = dict()

class Application:
    "common parent class of all service handler classes to use db etc."
    __slots__ = [ 'dbnstr', 'dbstr', 'db', 'home', 'store_path', 'chunkbytes', 'render', 'help', 'jira', 'remap', 'webauthnexpiremins' ]

    def getParamDb(self, suffix, default=None, name=None):
        results = self.getParamsDb(suffix, name)
        if len(results) == 1:
            return results[0]
        elif len(results) == 0:
            return default
        else:
            raise ValueError

    def getParamsDb(self, suffix, name=None):
        if name == None:
            name = 'tagfiler configuration'

        if configDataCache.has_key(name):
            l1 = configDataCache[name]
            if l1.has_key(suffix):
                return l1[suffix]

        status = web.ctx.status
        try:
            tagdef = self.static_tagdefs.get('_cfg_%s' % suffix, None)
            if tagdef == None:
                web.debug('getParamsDb: Cannot find tagdef for _cfg_%s' % suffix)
                return []
            results = self.select_files_by_predlist(predlist=[ dict(tag='name', op='=', vals=[name]) ],
                                                    listtags=[ 'id', '_cfg_%s' % suffix ],
                                                    versions='latest',
                                                    tagdefs=self.static_tagdefs)
            if len(results) == 0:
                web.debug('getParamsDb: Cannot find subject %s' % name)
                return []
            
            subject = results[0]
            results = subject['_cfg_%s' % suffix]
            if tagdef.multivalue:
                if results == None:
                    results = []
            else:
                if results == None:
                    results = []
                else:
                    results = [ results ]
            if not configDataCache.has_key(name):
                configDataCache[name] = dict()
            configDataCache[name][suffix] = results
            return results

        except NotFound:
            web.ctx.status = status
            return []

    def __init__(self):
        "store common configuration data for all service classes"
        global render

        self.skip_preDispatch = False

        self.version = None
        self.predlist = []
        self.globals = dict()

        self.ops = [ ('', 'Tagged'),
                     (':not:', 'Not tagged'),
                     ('=', 'Equal'),
                     ('!=', 'Not equal'),
                     (':lt:', 'Less than'),
                     (':leq:', 'Less than or equal'),
                     (':gt:', 'Greater than'),
                     (':geq:', 'Greater than or equal'),
                     (':like:', 'LIKE (SQL operator)'),
                     (':simto:', 'SIMILAR TO (SQL operator)'),
                     (':regexp:', 'Regular expression (case sensitive)'),
                     (':!regexp:', 'Negated regular expression (case sensitive)'),
                     (':ciregexp:', 'Regular expression (case insensitive)'),
                     (':!ciregexp:', 'Negated regular expression (case insensitive)')]

        self.opsDB = dict([ ('=', '='),
                            ('!=', '!='),
                            (':lt:', '<'),
                            (':leq:', '<='),
                            (':gt:', '>'),
                            (':geq:', '>='),
                            (':like:', 'LIKE'),
                            (':simto:', 'SIMILAR TO'),
                            (':regexp:', '~'),
                            (':!regexp:', '!~'),
                            (':ciregexp:', '~*'),
                            (':!ciregexp:', '!~*') ])

        # this ordered list can be pruned to optimize transactions
        self.needed_db_globals = [ 'roleinfo', 'typeinfo', 'typesdict' ]

        myAppName = os.path.basename(web.ctx.env['SCRIPT_NAME'])

        def getParamEnv(suffix, default=None):
            return web.ctx.env.get('%s.%s' % (myAppName, suffix), default)

        try:
            p = subprocess.Popen(['/usr/bin/whoami'], stdout=subprocess.PIPE)
            line = p.stdout.readline()
            self.daemonuser = line.strip()
        except:
            self.daemonuser = 'tagfiler'

        self.hostname = socket.gethostname()

        self.logmsgs = []
        self.middispatchtime = None

        self.dbnstr = getParamEnv('dbnstr', 'postgres')
        self.dbstr = getParamEnv('dbstr', '')
        self.db = web.database(dbn=self.dbnstr, db=self.dbstr)

        # static representation of important tagdefs
        self.static_tagdefs = []
        # -- the system tagdefs needed by the select_files_by_predlist call we make below
        for prototype in [ ('id', 'int8', False, 'system', True),
                           ('tagdef', 'text', False, 'system', True),
                           ('tagdef type', 'type', False, 'system', False),
                           ('tagdef multivalue', 'empty', False, 'system', False),
                           ('tagdef active', 'empty', False, 'system', False),
                           ('tagdef readpolicy', 'tagpolicy', False, 'system', False),
                           ('tagdef writepolicy', 'tagpolicy', False, 'system', False),
                           ('tagdef unique', 'empty', False, 'system', False),
                           ('tag read users', 'rolepat', True, 'fowner', False),
                           ('tag write users', 'rolepat', True, 'fowner', False),
                           ('read users', 'rolepat', True, 'fowner', False),
                           ('write users', 'rolepat', True, 'fowner', False),
                           ('owner', 'role', False, 'fowner', False),
                           ('modified', 'timestamptz', False, 'system', False),
                           ('name', 'text', False, 'system', False),
                           ('version', 'int8', False, 'system', False),
                           ('latest with name', 'text', False, 'system', True),
                           ('_cfg_applet custom properties', 'text', False, 'file', False),
                           ('_cfg_applet tags', 'tagname', True, 'file', False),
                           ('_cfg_applet tags require', 'tagname', True, 'file', False),
                           ('_cfg_applet test log', 'text', False, 'file', False),
                           ('_cfg_applet test properties', 'text', True, 'file', False),
                           ('_cfg_bugs', 'text', False, 'file', False),
                           ('_cfg_chunk bytes', 'text', False, 'file', False),
                           ('_cfg_client chunk bytes', 'text', False, 'file', False),
                           ('_cfg_client connections', 'text', False, 'file', False),
                           ('_cfg_client download chunks', 'text', False, 'file', False),
                           ('_cfg_client socket buffer size', 'text', False, 'file', False),
                           ('_cfg_client upload chunks', 'text', False, 'file', False),
                           ('_cfg_contact', 'text', False, 'file', False),
                           ('_cfg_file list tags', 'tagname', True, 'file', False),
                           ('_cfg_file list tags write', 'tagname', True, 'file', False),
                           ('_cfg_help', 'text', False, 'file', False),
                           ('_cfg_home', 'text', False, 'file', False),
                           ('_cfg_local files immutable', 'text', False, 'file', False),
                           ('_cfg_log path', 'text', False, 'file', False),
                           ('_cfg_logo', 'text', False, 'file', False),
                           ('_cfg_policy remappings', 'text', True, 'file', False),
                           ('_cfg_remote files immutable', 'text', False, 'file', False),
                           ('_cfg_store path', 'text', False, 'file', False),
                           ('_cfg_subtitle', 'text', False, 'file', False),
                           ('_cfg_tag list tags', 'tagname', True, 'file', False),
                           ('_cfg_template path', 'text', False, 'file', False),
                           ('_cfg_webauthn home', 'text', False, 'file', False),
                           ('_cfg_webauthn require', 'text', False, 'file', False) ]:
            deftagname, typestr, multivalue, writepolicy, unique = prototype
            self.static_tagdefs.append(web.Storage(tagname=deftagname,
                                                   owner=None,
                                                   typestr=typestr,
                                                   multivalue=multivalue,
                                                   active=True,
                                                   readpolicy='anonymous',
                                                   readok=True,
                                                   writepolicy=writepolicy,
                                                   unique=unique,
                                                   tagreaders=[],
                                                   tagwriters=[]))

        self.static_tagdefs = dict( [ (tagdef.tagname, tagdef) for tagdef in self.static_tagdefs ] )

        # BEGIN: get runtime parameters from database

        # set default anonymous authn info
        self.set_authn(webauthn.providers.AuthnInfo('root', set(['root']), None, None, False, None))

        # these properties are used by Python code but not templates
        self.store_path = self.getParamDb('store path', '/var/www/%s-data' % self.daemonuser)
        self.chunkbytes = int(self.getParamDb('chunk bytes', 64 * 1024))
        self.log_path = self.getParamDb('log path', '/var/www/%s-logs' % self.daemonuser)
        self.template_path = self.getParamDb('template path', '%s/tagfiler/templates' % distutils.sysconfig.get_python_lib())
        self.home = self.getParamDb('home', 'https://%s' % self.hostname)
        
        self.remap = buildPolicyRules(self.getParamsDb('policy remappings'))
        self.localFilesImmutable = parseBoolString(self.getParamDb('local files immutable', 'False'))
        self.remoteFilesImmutable = parseBoolString(self.getParamDb('remote files immutable', 'False'))

        self.render = web.template.render(self.template_path, globals=self.globals)
        render = self.render # HACK: make this available to exception classes too
        
        # we need this early for getParamsDb() to work... so it's not optional anymore
        self.globals['tagdefsdict'] = dict ([ (tagdef.tagname, tagdef) for tagdef in self.select_tagdef() ])

        # 'globals' are local to this Application instance and also used by its templates
        self.globals['render'] = self.render # HACK: make render available to templates too
        self.globals['urlquote'] = urlquote
        self.globals['idquote'] = idquote
        self.globals['jsonWriter'] = jsonWriter
        self.globals['subject2identifiers'] = lambda subject, showversions=True: self.subject2identifiers(subject, showversions)

        self.globals['home'] = self.home + web.ctx.homepath
        self.globals['homepath'] = web.ctx.homepath
        self.globals['help'] = self.getParamDb('help')
        self.globals['bugs'] = self.getParamDb('bugs')
        self.globals['subtitle'] = self.getParamDb('subtitle', '')
        self.globals['logo'] = self.getParamDb('logo', '')
        self.globals['contact'] = self.getParamDb('contact', None)

        self.globals['webauthnhome'] = self.getParamDb('webauthn home')
        self.globals['webauthnrequire'] = parseBoolString(self.getParamDb('webauthn require', 'False'))

        self.globals['filelisttags'] = self.getParamsDb('file list tags')
        self.globals['filelisttagswrite'] = self.getParamsDb('file list tags write')
                
        self.globals['appletTestProperties'] = self.getParamDb('applet test properties', None)
        self.globals['appletLogfile'] = self.getParamDb('applet test log', None)
        self.globals['appletCustomProperties'] = None # self.getParamDb('applet custom properties', None)
        self.globals['clientChunkbytes'] = int(self.getParamDb('client chunk bytes', 4194304))
        self.globals['clientConnections'] = self.getParamDb('client connections', '2')
        self.globals['clientUploadChunks'] = parseBoolString(self.getParamDb('client upload chunks', 'False'))
        self.globals['clientDownloadChunks'] = parseBoolString(self.getParamDb('client download chunks', 'False'))
        self.globals['clientSocketBufferSize'] = int(self.getParamDb('client socket buffer size', 8192))
        
        # END: get runtime parameters from database

        try:
            def parsekv(kv):
                if len(kv) == 2:
                    return kv
                else:
                    return [ kv[0], None ]
                
            uri = web.ctx.env['REQUEST_URI']
            self.storage = web.storage([ parsekv(kv.split('=', 1)) for kv in uri.split('?', 1)[1].replace(';', '&').split('&') ])
        except:
            self.storage = web.storage([]) 

        self.rfc1123 = '%a, %d %b %Y %H:%M:%S UTC%z'

        self.tagnameValidators = { 'owner' : self.validateRole,
                                   'read users' : self.validateRolePattern,
                                   'write users' : self.validateRolePattern,
                                   'modified by' : self.validateRole,
                                   'typedef values' : self.validateEnumeration,
                                   '_cfg_policy remappings' : self.validatePolicyRule }
        
        self.tagtypeValidators = { 'tagname' : self.validateTagname,
                                   'file' : self.validateFilename,
                                   'vfile' : self.validateVersionedFilename }

        self.systemTags = ['created', 'modified', 'modified by', 'bytes', 'name', 'url', 'sha256sum']
        self.ownerTags = ['read users', 'write users']

    def validateFilename(self, file, tagname='', subject=None):        
        results = self.select_files_by_predlist(predlist=[dict(tag='name', op='=', vals=[file])],
                                                listtags=['id'])
        if len(results) == 0:
            raise Conflict('Supplied file name "%s" for tag "%s" is not found.' % (file, tagname))

    def validateVersionedFilename(self, vfile, tagname='', subject=None):
        m = re.match('^(?P<data_id>.*)@(?P<version>[0-9]+)', vfile)
        if m:
            g = m.groupdict()
            try:
                version = int(g['version'])
            except ValueError:
                raise BadRequest('Supplied versioned file name "%s" for tag "%s" has an invalid version suffix.' % (vfile, tagname))
            if g['data_id'] == '':
                raise BadRequest('Supplied versioned file name "%s" for tag "%s" has an invalid name.' % (vfile, tagname))
            results = self.select_files_by_predlist(predlist=[dict(tag='name', op='=', vals=[file]),
                                                              dict(tag='version', op='=', vals=[version])],
                                                    listtags=['id'],
                                                    versions='any')
            if len(results) == 0:
                raise Conflict('Supplied versioned file name "%s" for tag "%s" is not found.' % (vfile, tagname))
        else:
            raise BadRequest('Supplied versioned file name "%s" for tag "%s" has invalid syntax.' % (vfile, tagname))

    def validateTagname(self, tag, tagname=None, subject=None):
        if tag == '':
            raise Conflict('You must specify a defined tag name to set values for "%s".' % tagname)
        results = self.select_tagdef(tag)
        if len(results) == 0:
            raise Conflict('Supplied tag name "%s" is not defined.' % tag)

    def validateRole(self, role, tagname=None, subject=None):
        if self.authn:
            try:
                valid = self.authn.roleProvider.testRole(self.db, role)
            except NotImplemented, AttributeError:
                valid = True
            if not valid:
                web.debug('Supplied tag value "%s" is not a valid role.' % role)
                raise Conflict('Supplied tag value "%s" is not a valid role.' % role)
                
    def validateRolePattern(self, role, tagname=None, subject=None):
        if role in [ '*' ]:
            return
        return self.validateRole(role)

    def validateEnumeration(self, enum, tagname=None, subject=None):
        try:
            key, desc = enum.split(" ", 1)
            key = urlunquote(key)
        except:
            raise BadRequest('Supplied enumeration value "%s" does not have key and description fields.' % enum)

        if tagname == 'typedef values':
            results = self.gettagvals('typedef', subject=subject)
            if len(results) == 0:
                raise Conflict('Set the "typedef" tag before trying to set "typedef values".')
            typename = results[0]
            results = self.get_type(typename)
            if len(results) == 0:
                raise Conflict('The type "%s" is not defined!' % typename)
            type = results[0]
            dbtype = type['typedef dbtype']
            try:
                key = self.downcast_value(dbtype, key)
            except:
                raise BadRequest(data='The key "%s" cannot be converted to type "%s" (%s).' % (key, type['typedef description'], dbtype))

    def validatePolicyRule(self, rule, tagname=None, subject=None):
        try:
            remap = buildPolicyRules([rule], fatal=True)
        except (ValueError, KeyError):
            raise BadRequest('Supplied rule "%s" is invalid for tag "%s"' % (rule, tagname))
        srcrole, mapping = remap.items()[0]
        if self.remap.has_key(srcrole):
            raise BadRequest('Supplied rule "%s" duplicates already mapped source role "%s".' % (rule, srcrole))

    def logfmt(self, action, dataset=None, tag=None, mode=None, user=None, value=None):
        parts = []
        if dataset:
            parts.append('dataset "%s"' % dataset)
        if tag:
            parts.append('tag "%s"' % tag)
        if value:
            parts.append('value "%s"' % value)
        if mode:
            parts.append('mode "%s"' % mode)
        if not self.authn.role:
            user = 'anonymous'
        else:
            user = self.authn.role
        return ('%s ' % action) + ', '.join(parts) + ' by user "%s"' % user

    def log(self, action, dataset=None, tag=None, mode=None, user=None, value=None):
        logger.info(self.logfmt(action, dataset, tag, mode, user, value))

    def txlog(self, action, dataset=None, tag=None, mode=None, user=None, value=None):
        self.logmsgs.append(self.logfmt(action, dataset, tag, mode, user, value))

    def set_authn(self, authn):
        self.authn = authn
        self.globals['authn'] = authn

    def renderlist(self, title, renderlist, refresh=True):
        if refresh:
            self.globals['pollmins'] = 1
        else:
            self.globals['pollmins'] = None

        self.globals['title'] = title
 
        return "".join([unicode(r) for r in 
                        [self.render.Top()] 
                        + renderlist
                        + [self.render.Bottom()]])

    def preDispatchFake(self, uri, app):
        self.db = app.db
        self.set_authn(app.authn)

    def preDispatchCore(self, uri, setcookie=True):
        if self.globals['webauthnhome']:
            if not self.db:
                self.db = web.database(dbn=self.dbnstr, db=self.dbstr)
            self.set_authn(webauthn.session.test_and_update_session(self.db,
                                                                    referer=self.home + uri,
                                                                    setcookie=setcookie))
            self.middispatchtime = datetime.datetime.now()
            if not self.authn.role and self.globals['webauthnrequire']:
                raise web.seeother(self.globals['webauthnhome'] + '/login?referer=%s' % urlquote(self.home + uri))
        else:
            try:
                user = web.ctx.env['REMOTE_USER']
                roles = set([ user ])
            except:
                user = None
                roles = set()
            self.set_authn(webauthn.providers.AuthnInfo(user, roles, None, None, False, None))

    def preDispatch(self, uri):
        def body():
            self.preDispatchCore(uri)

        def postCommit(results):
            pass

        if not self.skip_preDispatch:
            self.dbtransact(body, postCommit)

    def postDispatch(self, uri=None):
        def body():
            if self.globals['webauthnhome']:
                t = self.db.transaction()
                try:
                    webauthn.session.test_and_update_session(self.db, self.authn.guid,
                                                             ignoremustchange=True,
                                                             setcookie=False)
                    t.commit()
                except:
                    t.rollback()
                    raise

        def postCommit(results):
            pass

        self.dbtransact(body, postCommit)

    def midDispatch(self):
        now = datetime.datetime.now()
        if self.middispatchtime == None or (now - self.middispatchtime).seconds > 30:
            self.preDispatchCore(web.ctx.homepath, setcookie=False)

    def setNoCache(self):
        now = datetime.datetime.now(pytz.timezone('UTC'))
        now_rfc1123 = now.strftime(self.rfc1123)
        web.header('Cache-control', 'no-cache')
        web.header('Expires', now_rfc1123)

    def logException(self, context=None):
        if context == None:
            context = 'unspecified'
        et, ev, tb = sys.exc_info()
        web.debug('exception "%s"' % context,
                  traceback.format_exception(et, ev, tb))

    def dbtransact(self, body, postCommit):
        """re-usable transaction pattern

           using caller-provided thunks under boilerplate
           commit/rollback/retry logic
        """
        if not self.db:
            self.db = web.database(dbn=self.dbnstr, db=self.dbstr)

        try:
            count = 0
            limit = 3
            while True:
                try:
                    t = self.db.transaction()
                    
                    try:
                        self.logmsgs = []
                        count = count + 1
                        self.subject = None
                        self.datapred = None
                        self.dataname = None
                        self.dataid = None

                        # build up globals useful to almost all classes, to avoid redundant coding
                        # this is fragile to make things fast and simple
                        db_globals_dict = dict(roleinfo=lambda : self.buildroleinfo(),
                                               typeinfo=lambda : self.get_type(),
                                               typesdict=lambda : dict([ (type['typedef'], type) for type in self.globals['typeinfo'] ]))
                        for key in self.needed_db_globals:
                            self.globals[key] = db_globals_dict[key]()

                        def tagOptions(tagname, values=[]):
                            tagdef = self.globals['tagdefsdict'][tagname]
                            tagnames = self.globals['tagdefsdict'].keys()
                            type = self.globals['typesdict'][tagdef.typestr]
                            typevals = type['typedef values']
                            roleinfo = self.globals['roleinfo']
                            if tagdef.typestr in ['role', 'rolepat', 'tagname'] or typevals:
                                if typevals:
                                    options = [ ( typeval[0], '%s (%s)' % typeval ) for typeval in typevals.items() ]
                                elif tagdef.typestr in [ 'role', 'rolepat' ]:
                                    if roleinfo != None:
                                        if tagdef.typestr == 'rolepat':
                                            options = [ (role, role) for role in set(roleinfo).union(set(['*'])).difference(set(values)) ]
                                        else:
                                            options = [ (role, role) for role in set(roleinfo).difference(set(values)) ]
                                    else:
                                        options = None
                                elif tagdef.typestr == 'tagname' and tagnames:
                                    options = [ (tag, tag) for tag in set(tagnames).difference(set(values)) ]
                            else:
                                options = None
                            return options

                        self.globals['tagOptions'] = tagOptions

                        # and set defaults if they weren't overridden by caller
                        for globalname, default in [ ('view', None),
                                                     ('referer', web.ctx.env.get('HTTP_REFERER', None)),
                                                     ('tagspace', 'tags'),
                                                     ('datapred', self.datapred),
                                                     ('dataname', self.dataname),
                                                     ('dataid', self.dataid) ]:
                            current = self.globals.get(globalname, None)
                            if not current:
                                self.globals[globalname] = default

                        bodyval = body()
                        t.commit()
                        break
                        # syntax "Type as var" not supported by Python 2.4
                    except (psycopg2.InterfaceError), te:
                        # pass this to outer handler

                        raise te
                    except (web.SeeOther), te:
                        t.commit()
                        raise te
                    except (NotFound, BadRequest, Unauthorized, Forbidden, Conflict), te:
                        t.rollback()
                        self.logException('web error in transaction body')
                        raise te
                    except (psycopg2.DataError, psycopg2.ProgrammingError), te:
                        t.rollback()
                        self.logException('database error in transaction body')
                        raise BadRequest(data='Logical error: ' + str(te))
                    except TypeError, te:
                        t.rollback()
                        self.logException('programming error in transaction body')
                        raise RuntimeError(data=str(te))
                    except (psycopg2.IntegrityError, IOError), te:
                        t.rollback()
                        if count > limit:
                            self.logException('too many retries during transaction body')
                            raise te
                        # else fall through to retry...
                    except:
                        t.rollback()
                        self.logException('unmatched error in transaction body')
                        raise

                except psycopg2.InterfaceError:
                    # try reopening the database connection
                    self.db = web.database(db=self.dbstr, dbn=self.dbnstr)

                # exponential backoff...
                # count=1 is roughly 0.1 microsecond
                # count=9 is roughly 10 seconds
                # randomly jittered from 75-125% of exponential delay
                delay =  random.uniform(0.75, 1.25) * math.pow(10.0, count) * 0.00000001
                web.debug('transaction retry: delaying %f' % delay)
                time.sleep(delay)

        finally:
            pass
                    
        for msg in self.logmsgs:
            logger.info(msg)
        self.logmsgs = []
        return postCommit(bodyval)

    def acceptPair(self, s):
        parts = s.split(';')
        q = 1.0
        t = parts[0]
        for p in parts[1:]:
            fields = p.split('=')
            if len(fields) == 2 and fields[0] == 'q':
                q = fields[1]
        return (q, t)
        
    def acceptTypesPreferedOrder(self):
        try:
            accept = web.ctx.env['HTTP_ACCEPT']
        except:
            accept = ""
            
        return [ pair[1]
                 for pair in
                 sorted([ self.acceptPair(s) for s in accept.lower().split(',') ],
                        key=lambda pair: pair[0]) ]

    # a bunch of little database access helpers for this app, to be run inside
    # the dbtransact driver

    def buildroleinfo(self):
        if self.authn.roleProvider:
            try:
                roleinfo = [ role for role in self.authn.roleProvider.listRoles(self.db) ]
                return roleinfo
            except NotImplemented, AttributeError:
                return None

    def validate_predlist_unique(self, acceptName=False):
        """Evaluate self.predlist as True for guaranteed unique, False for named latest iff acceptName=True, else raise Conflict."""
        got_name = False
        got_version = False
        for pred in self.predlist:
            tagdef = self.globals['tagdefsdict'].get(pred['tag'], None)
            if tagdef == None:
                raise Conflict('Tag "%s" referenced in subject predicate list is not defined on this server.' % pred['tag'])
            if tagdef.get('unique', False) and pred['op'] == '=' and len(pred['vals']) > 0:
                return True
            elif tagdef.tagname == 'name' and pred['op'] == '=' and len(pred['vals']) > 0:
                got_name = True
            elif tagdef.tagname == 'version' and pred['op'] == '=' and len(pred['vals']) > 0:
                got_version = True
        if got_name and got_version:
            # we accept fully constrained name+version as a unique key too
            return True
        elif got_name and acceptName:
            return False
        else:
            raise Conflict('Subject-identifying predicate list requires a unique identifying constraint.')

    def enforce_file_authz_special(self, mode, subject):
        if mode == 'read':
            # special rules only affect write mode
            return

        dtype = subject.dtype
        if dtype == 'url':
            if subject['Image Set']:
                # rewrite dtype for immutable files test
                dtype = 'file'

        if dtype == 'file' and self.localFilesImmutable or dtype == 'url' and self.remoteFilesImmutable:
            raise Forbidden(data='modification of immutable dataset "%s"' % self.subject2identifiers(subject)[0])
    
    def test_file_authz(self, mode, subject):
        """Check whether access is allowed to user given mode and owner.

           True: access allowed
           False: access forbidden
           None: user needs to authenticate to be sure"""
        status = web.ctx.status
        try:
            self.enforce_file_authz_special(mode, subject)
        except:
            # if special rules are violated, treat like unauthorized
            web.ctx.status = status
            return False

        # read is authorized or subject would not be found
        if mode == 'write':
            if len(set(subject.get('%s users' % mode, []))
                   .union(set(['*']))
                   .intersection(set(subject['write users']))) > 0:
                return True
            elif self.authn.role:
                return False
            else:
                return None
        else:
            return True

    def test_tag_authz(self, mode, subject, tagdef):
        """Check whether access is allowed to user given policy_tag and owner.

           True: access allowed
           False: access forbidden
           None: user needs to authenticate to be sure"""
        if tagdef[mode + 'ok']:
            return True
        elif tagdef[mode + 'ok'] == None:
            if tagdef[mode + 'policy'] == 'file' and dict(read=True, write=subject.writeok)[mode]:
                return True
            elif tagdef[mode + 'policy']  == 'fowner' and subject.owner in self.authn.roles:
                return True
        if self.authn == None:
            return None
        else:
            return False

    def test_tagdef_authz(self, mode, tagdef):
        """Check whether access is allowed."""
        if mode == 'read':
            return True
        elif self.authn.role:
            return tagdef.owner in self.authn.roles
        else:
            return None

    def enforce_file_authz(self, mode, subject):
        """Check whether access is allowed and throw web exception if not."""
        # enforce these early, so they can throw more specific exceptions
        self.enforce_file_authz_special(mode, subject)
            
        allow = self.test_file_authz(mode, subject)
        data = '%s of dataset "%s"' % self.subject2identifiers(subject)[0]
        if allow == False:
            raise Forbidden(data=data)
        elif allow == None:
            raise Unauthorized(data=data)

    def enforce_tag_authz(self, mode, subject, tagdef):
        """Check whether access is allowed and throw web exception if not."""
        allow = self.test_tag_authz(mode, subject, tagdef)
        data = '%s of tag "%s" on dataset "%s"' % (mode, tagdef.tagname, self.subject2identifiers(subject)[0])
        if allow == False:
            raise Forbidden(data=data)
        elif allow == None:
            raise Unauthorized(data=data)

    def enforce_tagdef_authz(self, mode, tagdef):
        """Check whether access is allowed and throw web exception if not."""
        allow = self.test_tagdef_authz(mode, tagdef)
        data = '%s of tagdef="%s"' % (mode, tagdef.tagname)
        if allow == False:
            raise Forbidden(data=data)
        elif allow == None:
            raise Unauthorized(data=data)

    def wraptag(self, tagname, suffix='', prefix='_'):
        return '"' + prefix + tagname.replace('"','""') + suffix + '"'

    def subject2identifiers(self, subject, showversions=True):
        datapred = None
        for tagname in [ 'tagdef', 'typedef' ]:
            keyv = subject.get(tagname, None)
            if keyv:
                if self.globals['tagdefsdict'][tagname].multivalue:
                    keyv = keyv[0]
                datapred = '%s=%s' % (urlquote(tagname), urlquote(keyv))
                dataid = datapred
                dataname = '%s=%s' % (tagname, keyv)
                break
        name = subject.get('name', None)
        version = subject.get('version', None)
        if datapred == None:
            if version != None and name != None and showversions:
                dataid = '%s@%s' % (urlquote(name), version)
                datapred = 'name=%s;version=%s' % (urlquote(name), version) 
                dataname = '%s@%s' % (name, version)
            elif name != None:
                dataid = urlquote(name)
                datapred = 'name=%s' % urlquote(name) 
                dataname = name
            else:
                datapred = 'id=%s' % subject.id
                dataid = datapred
                dataname = datapred
        return (datapred, dataid, dataname)

    def get_type(self, typename=None):
        def valexpand(res):
            # replace raw "key desc" string with (key, desc) pair
            if res['typedef values'] != None:
                vals = []
                for val in res['typedef values']:
                    key, desc = val.split(" ", 1)
                    key = urlunquote(key)
                    dbtype = res['typedef dbtype']
                    key = self.downcast_value(dbtype, key)
                    vals.append( (key, desc) )
                res['typedef values'] = dict(vals)
            return res
        if typename != None:
            predlist = [ dict(tag='typedef', op='=', vals=[typename]) ]
        else:
            predlist = [ dict(tag='typedef', op=None, vals=[]) ]
        listtags = [ 'typedef', 'typedef description', 'typedef dbtype', 'typedef values' ]
        return [ valexpand(res) for res in self.select_files_by_predlist(predlist=predlist, listtags=listtags) ]

    def select_file_members(self, subject, membertag='vcontains'):
        # return the children of the dataset as referenced by its membertag, e.g. vcontains or contains
        if membertag == 'contains':
            versions = 'latest'
        else:
            versions = 'any'
        return self.select_files_by_predlist_path([ ([ dict(tag='id', op='=', vals=[subject.id]) ], [ membertag ], [ ]),
                                                    ( [], [], [] ) ],
                                                  versions=versions)

    def select_file_versions(self, name):
        vars = dict(name=name)
        query = 'SELECT n.subject AS id, n.value AS file, v.value AS version FROM "_name" AS n JOIN "_version" AS v USING (subject)' \
                 + ' WHERE n.value = $name'
        return self.db.query(query, vars)

    def select_dataset_size(self, key, membertag='vcontains'):
        # return statistics aout the children of the dataset as referenced by its membertag
        query, values = self.build_files_by_predlist_path([ ([dict(tag='key', op='=', vals=[key])], [membertag], []),
                                                            ([], ['name', 'bytes'], []) ])
        query = 'SELECT SUM(bytes) AS size, COUNT(*) AS count FROM (%s) AS q' % query
        return self.db.query(query, values)

    def insert_file(self, name, version, dtype, storagename=None):
        newid = self.db.query("INSERT INTO resources DEFAULT VALUES RETURNING subject")[0].subject
        subject = web.Storage(id=newid)

        if version:
            self.set_tag(subject, self.globals['tagdefsdict']['version'], version)

        if name:
            self.set_tag(subject, self.globals['tagdefsdict']['name'], name)

            if version > 1:
                self.update_latestfile_version(name, newid)
            elif version == 1:
                self.set_tag(subject, self.globals['tagdefsdict']['latest with name'], name)

        self.set_tag(subject, self.globals['tagdefsdict']['dtype'], dtype)

        if storagename and dtype == 'file':
            self.set_tag(subject, self.globals['tagdefsdict']['storagename'], storagename)

        return newid

    def update_latestfile_version(self, name, next_latest_id):
        vars=dict(name=name, id=next_latest_id)
        self.db.query('UPDATE "_latest with name" SET subject = $id WHERE value = $name', vars=vars)

    def delete_file(self, subject):
        wheres = []

        if subject.has_key('name') and subject.has_key('version'):
            versions = [ file for file in self.select_file_versions(subject.name) ]
            versions.sort(key=lambda res: res.version, reverse=True)

            latest = versions[0]
        
            if subject.version == latest.version and len(versions) > 1:
                # we're deleting the latest version and there are previous versions
                self.update_latestfile_version(subject.name, versions[1].id)
                
        query = 'DELETE FROM resources WHERE subject = $id'
        self.db.query(query, vars=dict(id=subject.id))

    tagdef_listas =  { 'tagdef': 'tagname', 
                       'tagdef type': 'typestr', 
                       'tagdef multivalue': 'multivalue',
                       'tagdef active': 'active',
                       'tagdef readpolicy': 'readpolicy',
                       'tagdef writepolicy': 'writepolicy',
                       'tagdef unique': 'unique',
                       'tag read users': 'tagreaders',
                       'tag write users': 'tagwriters' }

    def select_tagdef(self, tagname=None, predlist=[], order=None):
        listtags = [ 'owner' ]
                           
        listtags += Application.tagdef_listas.keys()

        if order:
            ordertags = [ order ]
        else:
            ordertags = []

        def add_authz(tagdef):
            def compute_authz(mode, tagdef):
                policy = tagdef['%spolicy' % mode]
                if policy == 'system':
                    return False
                elif policy in [ 'fowner', 'file' ]:
                    return None
                elif policy == 'tag':
                    return tagdef.owner in self.authn.roles \
                           or len(set(self.authn.roles)
                                  .union(['*'])
                                  .intersection(set(tagdef['tag'] + mode[0:4] + 'ers'))) > 0
                elif policy == 'users':
                    return self.authn.role != None
                else:
                    # policy == 'anonymous'
                    return True
            
            for mode in 'read', 'write':
                tagdef['%sok' % mode] = compute_authz(mode, tagdef)
                return tagdef
            
        if tagname:
            predlist = predlist + [ dict(tag='tagdef', op='=', vals=[tagname]) ]
        else:
            predlist = predlist + [ dict(tag='tagdef', op=None, vals=[]) ]

        results = [ add_authz(tagdef) for tagdef in self.select_files_by_predlist(predlist, listtags, ordertags, listas=Application.tagdef_listas, tagdefs=self.static_tagdefs) ]
        #web.debug(results)
        return results

    def insert_tagdef(self):
        results = self.select_tagdef(self.tag_id)
        if len(results) > 0:
            raise Conflict('Tagdef "%s" already exists. Delete it before redefining.' % self.tag_id)

        owner = self.authn.role
        newid = self.insert_file(None, None, 'dtype', None)
        subject = web.Storage(id=newid)
        tags = [ ('created', 'now'),
                 ('tagdef', self.tag_id),
                 ('tagdef active', None),
                 ('tagdef type', self.typestr),
                 ('tagdef readpolicy', self.readpolicy),
                 ('tagdef writepolicy', self.writepolicy) ]
        if owner:
            tags.append( ('owner', owner) )
        if self.multivalue:
            tags.append( ('tagdef multivalue', None) )

        for tag, value in tags:
            self.set_tag(subject, self.globals['tagdefsdict'][tag], value)

        tagdef = web.Storage([ (Application.tagdef_listas.get(key, key), value) for key, value in tags ])
        tagdef.id = newid
        if owner == None:
            tagdef.owner = None
        tagdef.multivalue = self.multivalue

        self.deploy_tagdef(tagdef)

    def deploy_tagdef(self, tagdef):
        tabledef = "CREATE TABLE %s" % (self.wraptag(tagdef.tagname))
        tabledef += " ( subject bigint NOT NULL REFERENCES resources (subject) ON DELETE CASCADE"
        indexdef = ''

        type = self.globals['typesdict'].get(tagdef.typestr, None)
        if type == None:
            raise BadRequest('Referenced type "%s" is not defined.' % tagdef.typestr)

        dbtype = type['typedef dbtype']
        if dbtype != '':
            tabledef += ", value %s" % dbtype
            if dbtype == 'text':
                tabledef += " DEFAULT ''"
            tabledef += ' NOT NULL'
            
            if tagdef.typestr == 'file':
                tabledef += ' REFERENCES "_latest with name" (value) ON DELETE CASCADE'
            elif tagdef.typestr == 'vfile':
                tabledef += ' REFERENCES "_vname" (value) ON DELETE CASCADE'
                
            if not tagdef.multivalue:
                tabledef += ", UNIQUE(subject)"
            else:
                tabledef += ", UNIQUE(subject, value)"
                
            indexdef = 'CREATE INDEX %s' % (self.wraptag(tagdef.tagname, '_value_idx'))
            indexdef += ' ON %s' % (self.wraptag(tagdef.tagname))
            indexdef += ' (value)'
        else:
            tabledef += ', UNIQUE(subject)'
            
        tabledef += " )"
        self.db.query(tabledef)
        if indexdef:
            self.db.query(indexdef)

    def delete_tagdef(self, tagdef):
        self.undeploy_tagdef(tagdef)
        self.delete_file( tagdef )

    def undeploy_tagdef(self, tagdef):
        self.db.query('DROP TABLE %s' % (self.wraptag(tagdef.tagname)))

    def select_tag_noauthn(self, subject, tagdef, value=None):
        query = 'SELECT tag.* FROM %s AS tag' % self.wraptag(tagdef.tagname) \
                + ' WHERE subject = $subject'
        if tagdef.typestr != 'empty' and value != None:
            if value == '':
                query += ' AND tag.value IS NULL'
            else:
                query += ' AND tag.value = $value'
            query += '  ORDER BY value'
        vars = dict(subject=subject.id, value=value)
        #web.debug(query, vars)
        return self.db.query(query, vars=vars)

    def select_tag(self, subject, tagdef, value=None):
        # subject would not be found if read of subject is not OK
        if tagdef.readok == False or (tagdef.readok == None and subject.owner not in self.authn.roles):
            raise Forbidden('read access to /tags/"%s"/%s' % (self.subject2identifiers(subject)[0], tagdef.tagname))
        return self.select_tag_noauthn(subject, tagdef, value)

    def gettagvals(self, subject, tagdef):
        results = self.select_tag(subject, tagdef)
        values = [ ]
        for result in results:
            try:
                value = result.value
                if value == None:
                    value = ''
                values.append(value)
            except:
                pass
        return values

    def select_filetags_noauthn(self, subject=None, tagname=None):
        wheres = []
        vars = dict()
        if subject:
            vars['id'] = subject.id
            wheres.append("subject = $id")

        if tagname:
            vars['tagname'] = tagname
            wheres.append("tagname = $tagname")
        
        wheres = ' AND '.join(wheres)
        if wheres:
            wheres = " WHERE " + wheres
            
        query = 'SELECT subject AS id, tagname FROM subjecttags' \
                + wheres \
                + " ORDER BY id, tagname"
        
        #web.debug(query, vars)
        return self.db.query(query, vars=vars)

    def delete_tag(self, subject, tagdef, value=None):
        wheres = ['tag.subject = $id']

        if value or value == '':
            wheres.append('tag.value = $value')
        if wheres:
            wheres = ' WHERE ' + ' AND '.join(wheres)
        else:
            wheres = ''

        query = 'DELETE FROM %s AS tag' % self.wraptag(tagdef.tagname) + wheres
        vars=dict(id=subject.id, value=value, tagname=tagdef.tagname)
        self.db.query(query, vars=vars)

        results = self.select_tag_noauthn(subject, tagdef)
        if len(results) == 0:
            web.debug('delete from subjecttags %s %s' % (subject.id, tagdef.tagname))
            query = 'DELETE FROM subjecttags AS tag WHERE subject = $id AND tagname = $tagname'
            self.db.query(query, vars=vars)

    def downcast_value(self, dbtype, value):
        if dbtype == 'int8':
            value = int(value)
        elif dbtype == 'float8':
            value = float(value)
        elif dbtype in [ 'date', 'timestamptz' ]:
            if value == 'now':
                value = datetime.datetime.now(pytz.timezone('UTC'))
            elif type(value) == str:
                value = dateutil.parser.parse(value)
        else:
            pass
        return value
            
    def set_tag(self, subject, tagdef, value=None):
        typedef = self.globals['typesdict'].get(tagdef.typestr, None)
        if typedef == None:
            raise Conflict('The tag definition references a field type "%s" which is not defined!' % typestr)
        dbtype = typedef['typedef dbtype']
        
        validator = self.tagnameValidators.get(tagdef.tagname)
        if validator:
            validator(value, tagdef, subject)

        validator = self.tagtypeValidators.get(typedef.typedef)
        if validator:
            validator(value, tagdef, subject)

        try:
            if value:
                value = self.downcast_value(dbtype, value)
        except:
            raise BadRequest(data='The value "%s" cannot be converted to stored type "%s".' % (value, dbtype))

        if not tagdef.multivalue:
            results = self.select_tag_noauthn(subject, tagdef)
            if len(results) > 0:
                if dbtype == '' or results[0].value == value:
                    return
                else:
                    self.delete_tag(subject, tagdef)
        else:
            results = self.select_tag_noauthn(subject, tagdef, value)
            if len(results) > 0:
                # (file, tag, value) already set, so we're done
                return

        if dbtype != '' and value != None:
            query = 'INSERT INTO %s' % self.wraptag(tagdef.tagname) \
                    + ' (subject, value) VALUES ($subject, $value)'
        else:
            # insert untyped or typed w/ default value...
            query = 'INSERT INTO %s' % self.wraptag(tagdef.tagname) \
                    + ' (subject) VALUES ($subject)'

        vars = dict(subject=subject.id, value=value, tagname=tagdef.tagname)
        #web.debug(query, vars)
        self.db.query(query, vars=vars)
        
        results = self.select_filetags_noauthn(subject, tagdef.tagname)
        if len(results) == 0:
            results = self.db.query("INSERT INTO subjecttags (subject, tagname) VALUES ($subject, $tagname)", vars=vars)
        else:
            # may already be reverse-indexed in multivalue case
            pass            

    def select_next_transmit_number(self):
        query = "SELECT NEXTVAL ('transmitnumber')"
        vars = dict()
        # now, as we can set manually dataset names, make sure the new generated name is unique
        while True:
            result = self.db.query(query)
            name = str(result[0].nextval).rjust(9, '0')
            vars['value'] = name
            res = self.db.query('SELECT * FROM "_name" WHERE value = $value', vars)
            if len(res) == 0:
                return name

    def select_next_key_number(self):
        query = "SELECT NEXTVAL ('keygenerator')"
        vars = dict()
        # now, as we can set manually dataset names, make sure the new generated name is unique
        while True:
            result = self.db.query(query)
            value = str(result[0].nextval).rjust(9, '0')
            vars['value'] = value
            res = self.db.query('SELECT * FROM "_key" WHERE value = $value', vars)
            if len(res) == 0:
                return value

    def build_select_files_by_predlist(self, predlist=None, listtags=None, ordertags=[], id=None, version=None, qd=0, versions='latest', tagdefs=None):

        def dbquote(s):
            return s.replace("'", "''")
        
        if predlist == None:
            predlist = self.predlist

        if listtags == None:
            listtags = [ x for x in self.globals['filelisttags'] ]
        else:
            listtags = [ x for x in listtags ]

        # make sure we have no repeats in listtags before embedding in query
        listtags = set(listtags)
        listtags = listtags.union( set(['read users',
                                        'write users',
                                        'owner',
                                        'name',
                                        'version',
                                        'latest with name',
                                        'modified']) )
        listtags = listtags.union( set(ordertags) )
        listtags = [ t for t in listtags ]

        roles = [ r for r in self.authn.roles ]
        roles.append('*')

        if tagdefs == None:
            tagdefs = self.globals['tagdefsdict']

        tags_needed = set([ pred['tag'] for pred in predlist ])
        tags_needed = tags_needed.union(set([ tagname for tagname in listtags ]))
        tagdefs_needed = []
        for tagname in tags_needed:
            try:
                tagdefs_needed.append(tagdefs[tagname])
            except KeyError:
                #web.debug(tagname)
                raise BadRequest(data='The tag "%s" is not defined on this server.' % tagname)

        innertables = []  # (table, alias)
        outertables = [('_owner', None)]
        selects = ['subject AS subject', '_owner.value AS owner']
        wheres = []
        values = dict()

        need_fowner_test = False
        role_val_list = ','.join(["'%s'" % dbquote(role) for role in roles])

        for p in range(0, len(predlist)):
            pred = predlist[p]
            tag = pred['tag']
            op = pred['op']
            vals = pred['vals']
            tagdef = tagdefs[tag]

            if op == ':not:':
                # not matches if tag column is null
                if tag == 'id':
                    raise Conflict('The "id" tag is bound for all catalog entries and is non-sensical to use with the :not: operator.')
                outertables.append((self.wraptag(tag), 't%s' % p ))
                if tagdef.readok == False:
                    # this tag cannot be read so act like it is absent
                    wheres.append('True')
                elif tagdef.readpolicy == 'fowner':
                    # this tag rule is more restrictive than file or static checks already done
                    # act like it is NULL if user isn't allowed to read this tag
                    wheres.append('t%s.subject IS NULL OR (_owner.value NOT IN (%s))' % (p, role_val_list))
                else:
                    # covers all cases where tag is more or equally permissive to file or static checks already done
                    wheres.append('t%s.subject IS NULL' % p)
            else:
                # all others match if and only if tag column is not null and we have read access
                # ...and any value constraints are met
                if tagdef.readok == False:
                    # this predicate is conjunctive with access denial
                    wheres.append('False')
                else:
                    if tagdef.readpolicy == 'fowner':
                        # this predicate is conjunctive with more restrictive access check, which we only need to add once
                        need_fowner_test = True
                                    
                    if tag != 'id':
                        innertables.append((self.wraptag(tag), 't%s' % p))

                    if op and vals and len(vals) > 0:
                        valpreds = []
                        for v in range(0, len(vals)):
                            if tag != 'id':
                                valpreds.append("t%s.value %s $val%s_%s_%d" % (p, self.opsDB[op], p, v, qd))
                            else:
                                valpreds.append("subject %s $val%s_%s_%d" % (self.opsDB[op], p, v, qd))
                            values["val%s_%s_%d" % (p, v, qd)] = vals[v]
                        wheres.append(" OR ".join(valpreds))
                    

        if need_fowner_test:
            # at least one predicate test requires fowner-based read access rights
            wheres.append('_owner.value IN (%s)' % role_val_list)

        # all results are filtered by file read access rights
        wheres.append('_owner.value IN (%s) OR "_read users".value IN (%s)' % (role_val_list, role_val_list))
        # compute file write access rights for later consumption
        selects.append('bool_or(_owner.value IN (%s) OR "_write users".value IN (%s)) AS writeok' % (role_val_list, role_val_list))

        if id:
            # special single-entry lookup
            values['id_%d' % qd] = id
            wheres.append("subject = $id_$d" % qd)

        # constrain to latest named files ONLY
        if versions == 'latest':
            outertables.append(('"_latest with name"', None))
            outertables.append(('_name', None))
            wheres.append('"_name".value IS NULL OR "_latest with name".value IS NOT NULL')

        outertables = outertables \
                      + [('_owner', None),
                         ('"_read users"', None),
                         ('"_write users"', None)]

        # idempotent insertion of (table, alias)
        joinset = set()
        innertables2 = []
        outertables2 = []

        if len(innertables) == 0:
            innertables.append( ('resources', None) ) # make sure we have at least one entry for 'subject'

        for tablepair in innertables:
            if tablepair not in joinset:
                innertables2.append(tablepair)
                joinset.add(tablepair)

        for tablepair in outertables:
            if tablepair not in joinset:
                outertables2.append(tablepair)
                joinset.add(tablepair)

        def rewrite_tablepair(tablepair, suffix=''):
            table, alias = tablepair
            if alias:
                table += ' AS %s' % alias
            return table + suffix

        innertables2 = [ rewrite_tablepair(innertables2[0]) ] \
                       + [ rewrite_tablepair(table, ' USING (subject)') for table in innertables2[1:] ]
        outertables2 = [ rewrite_tablepair(table, ' USING (subject)') for table in outertables2 ]

        # this query produces a set of (subject, owner, writeok) rows that match the query result set
        subject_query = 'SELECT %s' % ','.join(selects) \
                        + ' FROM %s' % ' LEFT OUTER JOIN '.join([' JOIN '.join(innertables2)] + outertables2 ) \
                        + ' WHERE %s' % ' AND '.join([ '(%s)' % where for where in wheres ]) \
                        + ' GROUP BY subject, owner'

        # now build the outer query that attaches listtags metadata to results
        selects = ['subjects.writeok AS writeok', 'subjects.owner AS owner', 'subjects.subject AS id']
        innertables = [('(%s)' % subject_query, 'subjects')]
        outertables = []
        groupbys = ['subjects.subject', 'subjects.owner', 'subjects.writeok']

        jointags = set(['subject', 'id', 'owner', 'writeok'])

        # add custom per-file single-val tags to results
        singlevaltags = [ tagname for tagname in listtags
                          if not tagdefs[tagname].multivalue and tagname not in jointags ]
        for tagname in singlevaltags:
            jointags.add(tagname)
            outertables.append((self.wraptag(tagname), None))
            if tagdefs[tagname].typestr == 'empty':
                expr = '%s.subject IS NOT NULL' % self.wraptag(tagname)
                groupbys.append('%s.subject' % self.wraptag(tagname))
            else:
                expr = '%s.value' % self.wraptag(tagname)
                groupbys.append('%s.value' % self.wraptag(tagname))
            if tagdefs[tagname].readpolicy == 'fowner':
                expr = 'CASE WHEN subjects.owner IN (%s)' % role_val_list \
                       + ' THEN %s ELSE NULL END' % expr
            selects.append('%s AS %s' % (expr, self.wraptag(tagname, prefix='')))

        # add custom per-file multi-val tags to results
        multivaltags = [ tagname for tagname in listtags
                         if tagdefs[tagname].multivalue and tagname not in jointags ]
        for tagname in multivaltags:
            jointags.add(tagname)
            outertables.append(('(SELECT subject, array_agg(value) AS value FROM %s GROUP BY subject)' % self.wraptag(tagname), self.wraptag(tagname)))
            groupbys.append('%s.value' % self.wraptag(tagname))
            expr = '%s.value' % self.wraptag(tagname)
            if tagdefs[tagname].readpolicy == 'fowner':
                expr = 'CASE WHEN subjects.owner IN (%s)' % role_val_list \
                       + ' THEN %s ELSE NULL END' % expr
            selects.append('%s AS %s' % (expr, self.wraptag(tagname, prefix='')))

        innertables2 = [ rewrite_tablepair(innertables[0]) ] \
                       + [ rewrite_tablepair(table, ' USING (subject)') for table in innertables[1:] ]
        outertables2 = [ rewrite_tablepair(table, ' USING (subject)') for table in outertables ]

        # this query produces a set of (subject, owner, writeok) rows that match the query result set
        value_query = 'SELECT %s' % ','.join(selects) \
                        + ' FROM %s' % ' LEFT OUTER JOIN '.join([' JOIN '.join(innertables2)] + outertables2 ) \
                        + ' GROUP BY %s' % ','.join(groupbys)

        # set up reasonable default sort order to use as minor sort criteria after major user-supplied ordering(s)
        order_suffix = ['id']
        for tagname in [ 'typedef', 'tagdef', 'name' ]:
            if tagname in listtags:
                order_suffix.insert(0, '"%s" NULLS LAST' % tagname)
        if 'modified' in listtags:
            order_suffix.insert(0, 'modified DESC NULLS LAST')

        value_query += " ORDER BY " + ", ".join([self.wraptag(tag, prefix='') for tag in ordertags] + order_suffix)

        #web.debug(query)
        return (value_query, values)

    def select_files_by_predlist(self, predlist=None, listtags=None, ordertags=[], id=None, version=None, versions='latest', listas=None, tagdefs=None):
        def select_clause(listtag):
            if listas.has_key(listtag):
                return '"%s" AS "%s"' % (listtag, listas[listtag])
            else:
                return listtag

        if listas != None:
            if listtags == None:
                listtags = [ x for x in self.globals['filelisttags'] ]

            query, values = self.build_select_files_by_predlist(predlist, listtags, ordertags=[], id=id, version=version, versions=versions, tagdefs=tagdefs)
            query = "SELECT %s FROM (%s) AS a" % (",".join([ select_clause(listtag) for listtag in set(listtags).union(set(['writeok', 'owner', 'id'])) ]),
                                                  query)
            if ordertags:
                query += " ORDER BY " + ",".join([self.wraptag(tag, prefix='') for tag in ordertags])
        else:
            query, values = self.build_select_files_by_predlist(predlist, listtags, ordertags, id, version, versions=versions, tagdefs=tagdefs)

        #web.debug(len(query), query, values)
        #web.debug('%s bytes in query:' % len(query))
        #for string in query.split(','):
        #    web.debug (string)
        #web.debug(values)
        #web.debug('...end query')
        #for r in self.db.query('EXPLAIN ANALYZE %s' % query, vars=values):
        #    web.debug(r)
        return self.db.query(query, vars=values)

    def build_files_by_predlist_path(self, path=None, versions='latest'):
        if path == None:
            path = [ ([], [], []) ]

        queries = []
        values = dict()
        tagdefs = self.globals['tagdefsdict']

        context = ''
        context_attr = None

        for e in range(0, len(path)):
            predlist, listtags, ordertags = path[e]
            q, v = self.build_select_files_by_predlist(predlist, listtags + ['vname', 'name'], ordertags, qd=e, versions=versions, tagdefs=tagdefs)
            values.update(v)

            if e < len(path) - 1:
                if len(listtags) != 1:
                    raise BadRequest("Path element %d of %d has ambiguous projection with %d list-tags" % (e, len(path), len(listtags)))
                projection = listtags[0]
                if tagdefs[projection].typestr not in [ 'text', 'file', 'vfile', 'id' ]:
                    raise BadRequest('Projection tag "%s" does not have a valid type to be used as a file context.' % projection)
                if tagdefs[projection].multivalue:
                    projectclause = 'unnest("%s")' % projection
                else:
                    projectclause = '"%s"' % projection
                if e == 0:
                    context = '(SELECT DISTINCT %s FROM (%s) AS q_%d)' % (projectclause, q, e)
                else:
                    context = '(SELECT DISTINCT %s FROM (%s) AS q_%d WHERE q_%d.%s IN (%s))' % (projectclause, q, e, e, context_attr, context)
                context_attr = dict(text='name', file='name', vfile='vname', id='id')[tagdefs[projection].typestr]
            else:
                if context:
                    query = '(%s) AS q_%d WHERE q_%d.%s IN (%s)' % (q, e, e, context_attr, context)
                else:
                    query = '(%s) AS q_%d' % (q, e)
            
        if listtags == None:
            listtags = self.listtags
        listtags = set(listtags).union(set(['writeok', 'owner', 'id']))
        
        selects = [ 'q_%d."%s" AS "%s"' % (len(path)-1, listtag, listtag)
                    for listtag in listtags ]
        selects = ', '.join(selects)

        query = 'SELECT ' + selects + ' FROM ' + query
        #web.debug(query, values)
        return (query, values)

    def select_files_by_predlist_path(self, path=None, versions='latest'):
        query, values = self.build_files_by_predlist_path(path, versions)
        return self.db.query(query, values)

    
