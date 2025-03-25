'''
A REST interface for Salt using the Flask framework
'''
import itertools
import json
import os

import cheroot.wsgi
import cheroot.ssllib.ssl_builtin

import flask
import flask.globals
import flask.views
import werkzeug.exceptions

import salt.client
import salt.log
import salt.runner
import salt.utils

import saltapi

logger = salt.log.logging.getLogger(__name__)

def __virtual__():
    '''
    Verify enough infos to actually start server.
    '''
    # if not 'port' in __opts__ or not __opts__['port']:
    #     return False

    return 'rest'

class SaltAPI(flask.views.MethodView):
    '''
    Base class for salt objects
    '''
    def __init__(self, app, *args, **kwargs):
        self.app = app
        self.api = saltapi.APIClient(__opts__)

    def post(self):
        '''
        Run a given function in a given client with the given args
        '''
        lowvals = itertools.izip_longest(*[i[1] for i in flask.request.form.lists()])
        lowdata = [dict(zip(flask.request.form.keys(), i)) for i in lowvals]
        logger.debug("SaltAPI is passing LowData: %s", lowdata)
        ret = [self.api.run(chunk) for chunk in lowdata]
        return json_response(ret)


#FIXME: the subclasses below have not yet been updated to use the new low-data
# interface. they may be updated or deleted outright. no promises

class JobsView(SaltAPI):
    '''
    * List previously run jobs (up to the :conf_master:`keep_jobs` expiration).
    * View the full return from a job.
    '''
    def _get_job_by_jid(self, jid):
        '''
        Return the output from a previously run job
        '''
        ret = self.runner.cmd('jobs.lookup_jid', [jid])
        return flask.jsonify(ret)

    def _get_jobs_list(self):
        '''
        Return a list of previously run jobs
        '''
        ret = self.runner.cmd('jobs.list_jobs', [])
        return flask.jsonify(ret)

    def get(self, jid=None):
        '''
        View a list of previously run jobs, or fetch a single job
        '''
        if jid:
            return self._get_job_by_jid(jid)

        return self._get_jobs_list()

class MinionsView(SaltAPI):
    '''
    * View lists of minions and available grains and execution modules for each
      minion.
    * Run commands on minions.
    '''
    def get(self, mid=None):
        '''
        Return grains and functions for all minions or for a single minion if
        specified. This runs the :py:func:`salt.modules.grains.items` and
        :py:func:`salt.modules.sys.list_functions` commands.
        '''
        return flask.jsonify(self.local.cmd(mid or '*',
            ['sys.list_functions', 'grains.items'], [[], []]))

    def post(self):
        '''
        Execute a Salt command and return the job ID. Commands are executed as
        a compound command so you may specify multiple functions to run. All
        function parameters *must* have a corresponding arguments parameter,
        even if it is empty.
        '''
        tgt = flask.request.form.get('tgt')
        expr = flask.request.form.get('expr', 'glob')
        funs = flask.request.form.getlist('fun')
        args = []

        # Make a list & strip out empty strings: ['']
        for i in flask.request.form.getlist('arg'):
            args.append([i] if i else [])

        if not tgt:
            raise werkzeug.exceptions.BadRequest("Missing target.")

        if not funs:
            raise werkzeug.exceptions.BadRequest("Missing command(s).")

        if len(funs) != len(args):
            raise werkzeug.exceptions.BadRequest(
                    "Mismatched number of commands and args.")

        jid = self.local.run_job(tgt, funs, args, expr_form=expr).get('jid')
        return flask.redirect(flask.url_for('jobs', jid=jid, _method='GET'))

class RunnersView(SaltAPI):
    '''
    * View lists of available runners.
    * Execute runners on the master.
    '''
    def get(self):
        '''
        Return all available runners
        '''
        return flask.jsonify({'runners': self.runner.functions.keys()})

    def post(self):
        '''
        Execute a runner command and return the result
        '''
        fun = flask.request.form.get('fun')
        arg = flask.request.form.get('arg')

        # pylint: disable-msg=W0142
        ret = self.runner.cmd(fun, arg)
        return flask.jsonify({'return': ret})


def json_response(obj):
    return flask.globals.current_app.response_class(json.dumps(obj),
            mimetype='application/json')

def build_app():
    '''
    Build the Flask app
    '''
    app = flask.Flask(__name__)

    def make_json_error(ex):
        '''
        Return errors as JSON objects
        '''
        status = getattr(ex, 'code', 500)

        response = flask.jsonify(message='Error {0}: {1}'.format(
            status,
            ex if app.debug else 'Internal server error',
        ))
        response.status_code = status

        return response

    # FIXME: Y U NO TRAILING SLASH?!

    app.config.update({
        # Allow using custom error handler when debug=True
        'PROPAGATE_EXCEPTIONS' : False,
        'TRAP_HTTP_EXCEPTIONS' : True,
        # Only set cookies over SSL
        'SESSION_COOKIE_SECURE': True,
    })

    app.error_handler_spec[None][500] = make_json_error

    jobs = JobsView.as_view('jobs', app=app)
    app.add_url_rule('/jobs', view_func=jobs, methods=['GET', 'POST'])
    app.add_url_rule('/jobs/<jid>', view_func=jobs, methods=['GET'])

    minions = MinionsView.as_view('minions', app=app)
    app.add_url_rule('/minions', view_func=minions, methods=['GET', 'POST'])
    app.add_url_rule('/minions/<mid>', view_func=minions,
            methods=['GET', 'POST'])

    runners = RunnersView.as_view('runners', app=app)
    app.add_url_rule('/runners', view_func=runners, methods=['GET', 'POST'])

    api = SaltAPI.as_view('api', app=app)
    app.add_url_rule('/', view_func=api, methods=['POST'])

    return app

def verify_certs(*args):
    msg = ("Could not find a certificate: {0}\n"
            "If you want to quickly generate a self-signed certificate, use "
            "the tls.create_self_signed_cert function in Salt")

    for arg in args:
        if not os.path.exists(arg):
            raise Exception(msg.format(arg))

def start():
    '''
    Server loop here. Started in a multiprocess.
    '''
    apiopts = __opts__.get('saltapi', {}).get(__name__.rsplit('.', 1)[-1], {})
    debug = apiopts.get('debug', False)
    port = apiopts.get('port', 8080)

    ssl_crt = apiopts.get('ssl_crt', '')
    ssl_key = apiopts.get('ssl_key', '')
    verify_certs(ssl_crt, ssl_key)

    app = build_app()

    if debug:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        ssl_a = cheroot.ssllib.ssl_builtin.BuiltinSSLAdapter(ssl_crt, ssl_key)
        wsgi_d = cheroot.wsgi.WSGIPathInfoDispatcher({'/': app})
        server = cheroot.wsgi.WSGIServer(('0.0.0.0', port),
                wsgi_app=wsgi_d,
                ssl_adapter=ssl_a)

        try:
            server.start()
        except KeyboardInterrupt:
            server.stop()
