from pritunl import __version__

from pritunl.constants import *
from pritunl.exceptions import *
from pritunl.helpers import *
from pritunl import logger
from pritunl import settings
from pritunl import static
from pritunl import utils
from pritunl import patches
from pritunl import wsgiserver
from pritunl import upgrade
from pritunl import listener

import logging
import signal
import time
import os
import pymongo
import json
import flask
import threading

server = None
app = flask.Flask(__name__)
upgrade_done = threading.Event()
setup_ready = threading.Event()
db_ready = threading.Event()
server_ready = threading.Event()
db_setup = None
server_upgrade = None

def stop_server():
    def stop():
        server.interrupt = StopServer('Stop server')
    setup_ready.set()
    settings.local.server_ready.wait()
    threading.Thread(target=stop).start()

try:
    import OpenSSL
    from pritunl.wsgiserver import ssl_pyopenssl
    SSLAdapter = ssl_pyopenssl.pyOpenSSLAdapter
except ImportError:
    from pritunl.wsgiserver import ssl_builtin
    SSLAdapter = ssl_builtin.BuiltinSSLAdapter

@app.route('/', methods=['GET'])
def index_get():
    return flask.redirect('setup')

@app.route('/setup', methods=['GET'])
def setup_get():
    if not db_setup:
        return flask.redirect('upgrade')

    try:
        static_file = static.StaticFile(settings.conf.www_path,
            DBCONF_NAME, cache=False)
    except InvalidStaticFile:
        return flask.abort(404)

    return static_file.get_response()

@app.route('/upgrade', methods=['GET'])
def upgrade_get():
    if db_setup:
        return flask.redirect('setup')

    try:
        static_file = static.StaticFile(settings.conf.www_path,
            UPGRADE_NAME, cache=False)
    except InvalidStaticFile:
        return flask.abort(404)

    return static_file.get_response()

@app.route('/setup/s/<file_name>', methods=['GET'])
def static_get(file_name):
    file_path = {
        'fredoka-one.eot': 'fonts/fredoka-one.woff',
        'fredoka-one.woff': 'fonts/fredoka-one.woff',
        'ubuntu-bold.eot': 'fonts/ubuntu-bold.eot',
        'ubuntu-bold.woff': 'fonts/ubuntu-bold.woff',
    }[file_name]

    try:
        static_file = static.StaticFile(settings.conf.www_path,
            file_path, cache=False)
    except InvalidStaticFile:
        return flask.abort(404)

    return static_file.get_response()

@app.route('/setup/mongodb', methods=['PUT'])
def setup_mongodb_put():
    mongodb_uri = flask.request.json['mongodb_uri']

    if not mongodb_uri:
        return utils.jsonify({
            'error': MONGODB_URI_INVALID,
            'error_msg': MONGODB_URI_INVALID_MSG,
        }, 400)

    try:
        client = pymongo.MongoClient(mongodb_uri,
            connectTimeoutMS=MONGO_CONNECT_TIMEOUT)
        database = client.get_default_database()
    except pymongo.errors.ConfigurationError as error:
        if 'auth failed' in str(error):
            return utils.jsonify({
                'error': MONGODB_AUTH_ERROR,
                'error_msg': MONGODB_AUTH_ERROR_MSG,
            }, 400)
        raise
    except pymongo.errors.ConnectionFailure:
        return utils.jsonify({
            'error': MONGODB_CONNECT_ERROR,
            'error_msg': MONGODB_CONNECT_ERROR_MSG,
        }, 400)

    settings.conf.mongodb_uri = mongodb_uri
    settings.conf.commit()

    if server_ready:
        stop_server()
    else:
        upgrade_database()

    return ''

@app.route('/setup/upgrade', methods=['GET'])
def setup_upgrade_get():
    if upgrade_done.wait(15):
        stop_server()
        return 'true'
    return ''

def server_thread():
    app.logger.setLevel(logging.DEBUG)
    app.logger.addFilter(logger.log_filter)
    app.logger.addHandler(logger.log_handler)

    global server
    server = wsgiserver.CherryPyWSGIServer(
        (settings.conf.bind_addr, settings.conf.port), app,
        server_name=wsgiserver.CherryPyWSGIServer.version,
        timeout=1,
        shutdown_timeout=0.5,
    )

    if settings.conf.ssl:
        server.ssl_adapter = SSLAdapter(
            settings.conf.server_cert_path, settings.conf.server_key_path)

    try:
        server.start()
    except StopServer:
        pass

    setup_ready.set()
    settings.local.server_start.set()

def upgrade_database():
    global db_setup
    db_setup = False

    def _upgrade_thread():
        try:
            upgrade.upgrade_server()
            upgrade_done.set()
            stop_server()
        except:
            logger.exception('Server upgrade failed')
            set_global_interrupt()
    threading.Thread(target=_upgrade_thread).start()

def on_system_msg(msg):
    if msg['message'] == SHUT_DOWN:
        logger.warning('Received shut down event', 'setup')
        set_global_interrupt()

def setup_server():
    db_ver_int = utils.get_db_ver_int()

    listener.add_listener('system', on_system_msg)

    if db_ver_int > settings.local.version_int:
        logger.error('Database version is newer than server version',
            'setup',
            db_version=db_ver_int,
            server_version=settings.local.version_int,
        )
        exit(75)

    # Fix for replaced conf file in 0.10.x upgrade
    if db_ver_int < 10000000000004000 and not settings.conf.mongodb_uri:
        settings.conf.mongodb_uri = 'mongodb://localhost:27017/pritunl'
        settings.conf.commit()

    global db_setup
    db_setup = not settings.conf.mongodb_uri

    global server_upgrade
    server_upgrade = db_ver_int and db_ver_int < settings.local.version_int

    if db_setup or server_upgrade:
        logger.info('Starting setup server', 'setup')

        if not db_setup:
            upgrade_database()

        settings.local.server_start.clear()

        thread = threading.Thread(target=server_thread)
        thread.daemon = True
        thread.start()

        setup_ready.wait()

    utils.set_db_ver(__version__)
