from inspect import getargspec, getmembers, ismethod
from copy import copy
import re

from twisted.spread import pb
from twisted.web import resource

try:
    import simplejson as json
except ImportError:
    import json

import ibid

class Processor(object):

    event_types = ('message',)
    addressed = True
    processed = False
    priority = 0
    autoload = True

    def __new__(cls, *args):
        if cls.processed and cls.priority == 0:
            cls.priority = 1500

        for name, option in options.items():
            new = copy(option)
            new.default = getattr(cls, name)
            setattr(cls, name, new)

        return super(Processor, cls).__new__(cls)

    def __init__(self, name):
        self.name = name
        self.setup()

    def setup(self):
        pass

    def shutdown(self):
        pass

    def process(self, event):
        if event.type not in self.event_types:
            return

        if self.addressed and ('addressed' not in event or not event.addressed):
            return

        if not self.processed and event.processed:
            return

        found = False
        for name, method in getmembers(self, ismethod):
            if hasattr(method, 'handler'):
                if not hasattr(method, 'pattern'):
                    found = True
                    method(event)
                elif hasattr(event, 'message'):
                    found = True
                    match = method.pattern.search(event.message[method.message_version])
                    if match is not None:
                        if not hasattr(method, 'authorised') or auth_responses(event, self.permission):
                            method(event, *match.groups())
                        elif not getattr(method, 'auth_passthrough', True):
                            event.processed = True

        if not found:
            raise RuntimeError(u'No handlers found in %s' % self)

        return event

# This is a bit yucky, but necessary since ibid.config imports Processor
from ibid.config import BoolOption, IntOption
options = {
    'addressed': BoolOption('addressed', u'Only process events if bot was addressed'),
    'processed': BoolOption('processed', u"Process events even if they've already been processed"),
    'priority': IntOption('priority', u'Processor priority'),
}

def handler(function):
    function.handler = True
    function.message_version = 'clean'
    return function

def match(regex, version='clean'):
    pattern = re.compile(regex, re.I | re.DOTALL)
    def wrap(function):
        function.handler = True
        function.pattern = pattern
        function.message_version = version
        return function
    return wrap

def auth_responses(event, permission):
    if not ibid.auth.authorise(event, permission):
        event.complain = u'notauthed'
        return False

    return True

def authorise(fail_silently=True):
    def wrap(function):
        function.authorised = True
        function.auth_passthrough = fail_silently
        return function
    return wrap

from ibid.source.http import templates

class RPC(pb.Referenceable, resource.Resource):
    isLeaf = True

    def __init__(self):
        ibid.rpc[self.feature] = self
        self.form = templates.get_template('plugin_form.html')
        self.list = templates.get_template('plugin_functions.html')

    def get_function(self, request):
        method = request.postpath[0]

        if hasattr(self, 'remote_%s' % method):
            return getattr(self, 'remote_%s' % method)

        return None

    def render_POST(self, request):
        args = []
        for arg in request.postpath[1:]:
            try:
                arg = json.loads(arg)
            except ValueError, e:
                pass
            args.append(arg)

        kwargs = {}
        for key, value in request.args.items():
            try:
                value = json.loads(value[0])
            except ValueError, e:
                value = value[0]
            kwargs[key] = value

        function = self.get_function(request)
        if not function:
            return "Not found"

        #self.log.debug(u'%s(%s, %s)', function, ', '.join([str(arg) for arg in args]), ', '.join(['%s=%s' % (k,v) for k,v in kwargs.items()]))

        try:
            result = function(*args, **kwargs)
            return json.dumps(result)
        except Exception, e:
            return json.dumps({'exception': True, 'message': unicode(e)})

    def render_GET(self, request):
        function = self.get_function(request)
        if not function:
            functions = []
            for name, method in getmembers(self, ismethod):
                if name.startswith('remote_'):
                    functions.append(name.replace('remote_', '', 1))

            return self.list.render(object=self.feature, functions=functions).encode('utf-8')

        args, varargs, varkw, defaults = getargspec(function)
        del args[0]
        if len(args) == 0 or len(request.postpath) > 1 or len(request.args) > 0:
            return self.render_POST(request)

        return self.form.render(args=args).encode('utf-8')

# vi: set et sta sw=4 ts=4:
