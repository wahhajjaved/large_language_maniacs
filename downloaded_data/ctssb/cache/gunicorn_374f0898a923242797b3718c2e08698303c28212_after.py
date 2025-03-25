# -*- coding: utf-8 -
#
# This file is part of gunicorn released under the MIT license. 
# See the NOTICE for more information.


import grp
import logging
import optparse as op
import os
import pwd
import pkg_resources
import re
import sys

from gunicorn.arbiter import Arbiter
from gunicorn import util, __version__

LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG
}

UMASK = 0

def options():
    return [
        op.make_option('-b', '--bind', dest='bind',
            help='Adress to listen on. Ex. 127.0.0.1:8000 or unix:/tmp/gunicorn.sock'),
        op.make_option('-w', '--workers', dest='workers', type='int',
            help='Number of workers to spawn. [%default]'),
        op.make_option('-p','--pid', dest='pidfile',
            help='set the background PID FILE'),
        op.make_option('-D', '--daemon', dest='daemon', action="store_true",
            help='Run daemonized in the background.'),
        op.make_option('-m', '--umask', dest="umask", type='int', 
            help="Define umask of daemon process"),
        op.make_option('-u', '--user', dest="user", 
            help="Change worker user"),
        op.make_option('-g', '--group', dest="group", 
            help="Change worker group"),
        op.make_option('--log-level', dest='loglevel', default='info',
            help='Log level below which to silence messages. [%default]'),
        op.make_option('--log-file', dest='logfile', default='-',
            help='Log to a file. - is stdout. [%default]'),
        op.make_option('-d', '--debug', dest='debug', action="store_true",
            default=False, help='Debug mode. only 1 worker.')
    ]

def configure_logging(opts):
    handlers = []
    if opts.logfile != "-":
        handlers.append(logging.FileHandler(opts.logfile))
    else:
        handlers.append(logging.StreamHandler())

    loglevel = LOG_LEVELS.get(opts.loglevel.lower(), logging.INFO)

    logger = logging.getLogger('gunicorn')
    logger.setLevel(loglevel)
    for h in handlers:
        h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s %(message)s"))
        logger.addHandler(h)
        
def daemonize(umask):
    if not 'GUNICORN_FD' in os.environ:
        if os.fork() == 0: 
            os.setsid()
            if os.fork() == 0:
                os.umask(umask) 
            else:
                os._exit(0)
        else:
            os._exit(0)
        
        maxfd = util.get_maxfd()

        # Iterate through and close all file descriptors.
        for fd in range(0, maxfd):
            try:
                os.close(fd)
            except OSError:	# ERROR, fd wasn't open to begin with (ignored)
                pass
        
        os.open(util.REDIRECT_TO, os.O_RDWR)
        os.dup2(0, 1)
        os.dup2(0, 2)

def set_owner_process(user,group):
    if group:
        if group.isdigit() or isinstance(group, int):
            gid = int(group)
        else:
            gid = grp.getgrnam(group).gr_gid
            os.setgid(gid)
    if user:
        if user.isdigit() or isinstance(user, int):
            uid = int(user)
        else:
            uid = pwd.getpwnam(user).pw_uid
        os.setuid(uid)
        
def main(usage, get_app):
    parser = op.OptionParser(usage=usage, option_list=options(),
                    version="%prog " + __version__)
    opts, args = parser.parse_args()

    app = get_app(parser, opts, args)
    workers = opts.workers or 1
    if opts.debug:
        workers = 1
        
    bind = opts.bind or '127.0.0.1'
    addr = util.parse_address(bind)
    
    umask = int(opts.umask or UMASK)

    kwargs = dict(
        debug=opts.debug,
        pidfile=opts.pidfile
    )
    
    arbiter = Arbiter(addr, workers, app, **kwargs)
    if opts.daemon:
        daemonize(umask)
    else:
        os.setpgrp()

    set_owner_process(opts.user, opts.group) 
    configure_logging(opts)
    arbiter.run()
    
def paste_server(app, global_conf=None, host="127.0.0.1", port=None, 
            *args, **kwargs):
    
    bind_addr = util.parse_address(host, port)

    # set others options
    debug = kwargs.get('debug')
    workers = kwargs.get("workers", 1)
    pid = kwargs.get("pid")
    daemon = kwargs.get("daemon")
    umask = kwargs.get('umask', UMASK)
    user = kwargs.get('user')
    group = kwargs.get('group')
    if kwargs:
        workers = int(global_conf.get('workers', workers))
        debug = global_conf.get('debug', debug) == "true"
        if debug:
            # we force to one worker in debug mode.
            workers = 1
        pid = global_conf.get('pid', pid)
        daemon = global_conf.get('daemon', daemonize)
        umask = global_conf.get('umask', umask)
        user = global_conf.get('user', user)
        group = global_conf.get('group', group)
   
    kwargs = dict(
        debug=debug,
        pidfile=pid
    )

    arbiter = Arbiter(bind_addr, workers, app, **kwargs)
    if daemon == "true":
        daemonize(umask)
    else:
        os.setpgrp()
    set_owner_process(opts.user, opts.group)
    arbiter.run()
    
def run():
    sys.path.insert(0, os.getcwd())
    
    def get_app(parser, opts, args):
        if len(args) != 1:
            parser.error("No application module specified.")

        try:
            return util.import_app(args[0])
        except:
            parser.error("Failed to import application module.")

    main("%prog [OPTIONS] APP_MODULE", get_app)
    
def run_django():
    
    def settings_notfound(path):
        error = "Settings file '%s' not found in current folder.\n" % path
        sys.stderr.write(error)
        sys.stderr.flush()
        sys.exit(1)

    def get_app(parser, opts, args):
        import django.core.handlers.wsgi

        project_path = os.getcwd()
        
        if args:
            settings_path = os.path.abspath(os.path.normpath(args[0]))
            if not os.path.isfile(settings_path):
                settings_notfound(settings_path)
            else:
                project_path = os.path.dirname(settings_path)
        else:
             settings_path = os.path.join(project_path, "settings.py")
             if not os.path.isfile(settings_path):
                 settings_notfound(settings_path)
            

        project_name = os.path.split(project_path)[-1]

        sys.path.insert(0, project_path)
        sys.path.append(os.path.join(project_path, os.pardir))

        # set environ
        os.environ['DJANGO_SETTINGS_MODULE'] = '%s.settings' % project_name
        
        # django wsgi app
        return django.core.handlers.wsgi.WSGIHandler()

    main("%prog [OPTIONS] [SETTINGS_PATH]", get_app)
    
def run_paster():
    from paste.deploy import loadapp, loadwsgi

    _scheme_re = re.compile(r'^[a-z][a-z]+:', re.I)


    def get_app(parser, opts, args):
        if len(args) != 1:
            parser.error("No application name specified.")

        config_file = os.path.abspath(os.path.normpath(
                            os.path.join(os.getcwd(), args[0])))

        if not os.path.exists(config_file):
            parser.error("Config file not found.")

        config_url = 'config:%s' % config_file
        relative_to = os.path.dirname(config_file)

        # load module in sys path
        sys.path.insert(0, relative_to)

        # add to eggs
        pkg_resources.working_set.add_entry(relative_to)
        ctx = loadwsgi.loadcontext(loadwsgi.SERVER, config_url,
                                relative_to=relative_to)

        if opts.workers:
            workers = opts.workers
        else:
            workers = int(ctx.local_conf.get('workers', 1))

        if not opts.umask:
            opts.umask = int(ctx.local_conf.get('umask', UMASK))
            
        if not opts.group:
            opts.group = ctx.local_conf.get('group')
        
        if not opts.user:
            opts.user = ctx.local_conf.get('user')
     
        if not opts.bind:
            host = ctx.local_conf.get('host')
            port = ctx.local_conf.get('port')
            if host:
                if port:
                    bind = "%s:%s" % (host, port)
                else:
                    bind = host
                opts.bind = bind
        
        debug = ctx.global_conf.get('debug') == "true"
        if debug:
            # we force to one worker in debug mode.
            workers = 1

        opts.workers=workers

        app = loadapp(config_url, relative_to=relative_to)
        return app

    main("%prog [OPTIONS] pasteconfig.ini", get_app)
    
