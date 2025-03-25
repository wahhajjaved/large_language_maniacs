import logging
import json
import multiprocessing
import os
import signal
from threading import Lock
import time

import tornado.web
from zmq.eventloop import ioloop

from db_store import Obdb
from market import Market
from network_util import get_random_free_tcp_port
from transport import CryptoTransportLayer
import upnp
from util import open_default_webbrowser, is_mac
from ws import WebSocketHandler

if is_mac():
    from util import osx_check_dyld_library_path
    osx_check_dyld_library_path()

ioloop.install()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.redirect("/html/index.html")


class OpenBazaarStaticHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("X-Frame-Options", "DENY")
        self.set_header("X-Content-Type-Options", "nosniff")


class OpenBazaarContext(object):
    """
    This Object holds all of the runtime parameters
    necessary to start an OpenBazaar instance.

    This object is convenient to pass on method interfaces,
    and reduces issues of API inconsistencies (as in the order
    in which parameters are passed, which can cause bugs)
    """

    def __init__(self,
                 nat_status,
                 server_public_ip,
                 server_public_port,
                 http_ip,
                 http_port,
                 db_path,
                 log_path,
                 log_level,
                 market_id,
                 bm_user,
                 bm_pass,
                 bm_port,
                 seed_peers,
                 seed_mode,
                 dev_mode,
                 dev_nodes,
                 disable_upnp,
                 disable_stun_check,
                 disable_open_browser,
                 disable_sqlite_crypt,
                 enable_ip_checker):
        self.nat_status = nat_status
        self.server_public_ip = server_public_ip
        self.server_public_port = server_public_port
        self.http_ip = http_ip
        self.http_port = http_port
        self.db_path = db_path
        self.log_path = log_path
        self.log_level = log_level
        self.market_id = market_id
        self.bm_user = bm_user
        self.bm_pass = bm_pass
        self.bm_port = bm_port
        self.seed_peers = seed_peers
        self.seed_mode = seed_mode
        self.dev_mode = dev_mode
        self.dev_nodes = dev_nodes
        self.disable_upnp = disable_upnp
        self.disable_stun_check = disable_stun_check
        self.disable_open_browser = disable_open_browser
        self.disable_sqlite_crypt = disable_sqlite_crypt
        self.enable_ip_checker = enable_ip_checker

        # to deduct up-time, and (TODO) average up-time
        # time stamp in (non-local) Coordinated Universal Time format.
        self.started_utc_timestamp = long(time.time())

    def __repr__(self):
        r = {"nat_status.nat_type": self.nat_status['nat_type'] if self.nat_status is not None else None,
             "nat_status.external_ip": self.nat_status['external_ip'] if self.nat_status is not None else None,
             "nat_status.external_port": self.nat_status['external_port'] if self.nat_status is not None else None,
             "server_public_ip": self.server_public_ip,
             "server_public_port": self.server_public_port,
             "http_ip": self.http_ip,
             "http_port": self.http_port,
             "log_path": self.log_path,
             "market_id": self.market_id,
             "bm_user": self.bm_user,
             "bm_pass": self.bm_pass,
             "bm_port": self.bm_port,
             "seed_peers": self.seed_peers,
             "seed_mode": self.seed_mode,
             "dev_mode": self.dev_mode,
             "dev_nodes": self.dev_nodes,
             "log_level": self.log_level,
             "db_path": self.db_path,
             "disable_upnp": self.disable_upnp,
             "disable_open_browser": self.disable_open_browser,
             "disable_sqlite_crypt": self.disable_sqlite_crypt,
             "enable_ip_checker": self.enable_ip_checker,
             "started_utc_timestamp": self.started_utc_timestamp,
             "uptime_in_secs": long(time.time()) - long(self.started_utc_timestamp)}

        return json.dumps(r).replace(", ", ",\n  ")

    @staticmethod
    def get_defaults():
        return {'MARKET_ID': 1,
                'SERVER_IP': '127.0.0.1',
                'SERVER_PORT': 12345,
                'LOG_DIR': 'logs',
                'LOG_FILE': 'production.log',
                'DB_DIR': 'db',
                'DB_FILE': 'ob.db',
                'DEV_DB_FILE': 'ob-dev-{0}.db',
                'DEVELOPMENT': False,
                'DEV_NODES': 3,
                'SEED_MODE': False,
                'SEED_HOSTNAMES': ['seed.openbazaar.org',
                                   'seed2.openbazaar.org',
                                   'seed.openlabs.co',
                                   'us.seed.bizarre.company',
                                   'eu.seed.bizarre.company'],
                'DISABLE_UPNP': False,
                'DISABLE_STUN_CHECK': False,
                'DISABLE_OPEN_DEFAULT_WEBBROWSER': False,
                'DISABLE_SQLITE_CRYPT': False,
                # CRITICAL=50, ERROR=40, WARNING=30, DEBUG=10, NOTSET=0
                'LOG_LEVEL': 10,
                'NODES': 3,
                'HTTP_IP': '127.0.0.1',
                'HTTP_PORT': None,
                'BITMESSAGE_USER': None,
                'BITMESSAGE_PASS': None,
                'BITMESSAGE_PORT': -1,
                'ENABLE_IP_CHECKER': False,
                'CONFIG_FILE': None}

    @staticmethod
    def create_default_instance():
        defaults = OpenBazaarContext.get_defaults()
        return OpenBazaarContext(None,
                                 server_public_ip=defaults['SERVER_IP'],
                                 server_public_port=defaults['SERVER_PORT'],
                                 http_ip=defaults['SERVER_IP'],
                                 http_port=defaults['SERVER_PORT'],
                                 db_path=os.path.join(defaults['DB_DIR'], defaults['DB_FILE']),
                                 log_path=os.path.join(defaults['LOG_DIR'], defaults['LOG_FILE']),
                                 log_level=defaults['LOG_LEVEL'],
                                 market_id=defaults['MARKET_ID'],
                                 bm_user=defaults['BITMESSAGE_USER'],
                                 bm_pass=defaults['BITMESSAGE_PASS'],
                                 bm_port=defaults['BITMESSAGE_PORT'],
                                 seed_peers=defaults['SEED_HOSTNAMES'],
                                 seed_mode=defaults['SEED_MODE'],
                                 dev_mode=defaults['DEVELOPMENT'],
                                 dev_nodes=defaults['DEV_NODES'],
                                 disable_upnp=defaults['DISABLE_UPNP'],
                                 disable_stun_check=defaults['DISABLE_STUN_CHECK'],
                                 disable_open_browser=defaults['DISABLE_OPEN_DEFAULT_WEBBROWSER'],
                                 disable_sqlite_crypt=defaults['DISABLE_SQLITE_CRYPT'],
                                 enable_ip_checker=defaults['ENABLE_IP_CHECKER'])


class MarketApplication(tornado.web.Application):
    def __init__(self, ob_ctx):
        self.shutdown_mutex = Lock()
        self.ob_ctx = ob_ctx
        db = Obdb(ob_ctx.db_path, ob_ctx.disable_sqlite_crypt)
        self.transport = CryptoTransportLayer(ob_ctx, db)
        self.market = Market(self.transport, db)
        self.upnp_mapper = None

        peers = ob_ctx.seed_peers if not ob_ctx.seed_mode else []
        self.transport.join_network(peers)

        handlers = [
            (r"/", MainHandler),
            (r"/main", MainHandler),
            (r"/html/(.*)", OpenBazaarStaticHandler, {'path': './html'}),
            (r"/ws", WebSocketHandler,
             dict(transport=self.transport, market_application=self, db=db))
        ]

        # TODO: Move debug settings to configuration location
        settings = dict(debug=True)
        super(MarketApplication, self).__init__(handlers, **settings)

    def start_app(self):
        error = True
        p2p_port = self.ob_ctx.server_public_port

        if self.ob_ctx.http_port is None:
            self.ob_ctx.http_port = get_random_free_tcp_port(8889, 8988)

        while error:
            try:
                self.listen(self.ob_ctx.http_port, self.ob_ctx.http_ip)
                error = False
            except IOError:
                self.ob_ctx.http_port += 1

        if not self.ob_ctx.disable_upnp:
            self.setup_upnp_port_mappings(p2p_port)
        else:
            print "MarketApplication.listen(): Disabling upnp setup"

    def get_transport(self):
        return self.transport

    def setup_upnp_port_mappings(self, p2p_port):
        result = False

        if not self.ob_ctx.disable_upnp:
            upnp.PortMapper.DEBUG = False
            print "Setting up UPnP Port Map Entry..."
            self.upnp_mapper = upnp.PortMapper()
            self.upnp_mapper.clean_my_mappings(p2p_port)

            result_tcp_p2p_mapping = self.upnp_mapper.add_port_mapping(p2p_port,
                                                                       p2p_port)
            print ("UPnP TCP P2P Port Map configuration done (%s -> %s) => %s" %
                   (str(p2p_port), str(p2p_port), str(result_tcp_p2p_mapping)))

            result_udp_p2p_mapping = self.upnp_mapper.add_port_mapping(p2p_port,
                                                                       p2p_port,
                                                                       'UDP')
            print ("UPnP UDP P2P Port Map configuration done (%s -> %s) => %s" %
                   (str(p2p_port), str(p2p_port), str(result_udp_p2p_mapping)))

            result = result_tcp_p2p_mapping and result_udp_p2p_mapping
            if not result:
                print "Warning: UPnP was not setup correctly. Ports could not be automatically mapped."

        return result

    def cleanup_upnp_port_mapping(self):
        if not self.ob_ctx.disable_upnp:
            try:
                if self.upnp_mapper is not None:
                    print "Cleaning UPnP Port Mapping -> ", \
                        self.upnp_mapper.clean_my_mappings(self.transport.port)
            except AttributeError:
                print "[openbazaar] MarketApplication.clean_upnp_port_mapping() failed!"

    def shutdown(self, x=None, y=None):
        self.shutdown_mutex.acquire()
        print "MarketApplication.shutdown!"
        locallogger = logging.getLogger(
            '[%s] %s' % (self.market.market_id, 'root')
        )
        locallogger.info("Received TERMINATE, exiting...")

        # transport.broadcast_goodbye()
        self.cleanup_upnp_port_mapping()
        tornado.ioloop.IOLoop.instance().stop()

        self.transport.shutdown()
        self.shutdown_mutex.release()
        os._exit(0)


def start_io_loop():
    if not tornado.ioloop.IOLoop.instance():
        ioloop.install()

    try:
        tornado.ioloop.IOLoop.instance().start()
    except Exception as e:
        print "openbazaar::start_io_loop Exception:", e
        raise


def create_logger(ob_ctx):
    logger = None
    try:
        logging.basicConfig(
            level=int(ob_ctx.log_level),
            format=u'%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            filename=ob_ctx.log_path
        )
        logging._defaultFormatter = logging.Formatter(u'%(message)s')
        logger = logging.getLogger('[%s] %s' % (ob_ctx.market_id, 'root'))

        handler = logging.handlers.RotatingFileHandler(
            ob_ctx.log_path,
            encoding='utf-8',
            maxBytes=50000000,
            backupCount=1
        )
        logger.addHandler(handler)
    except Exception as e:
        print "Could not setup logger, continuing: ", e.message
    return logger

def log_openbazaar_start(logger, ob_ctx):
    logger.info("Started OpenBazaar Web App at http://%s:%s" % (ob_ctx.http_ip, ob_ctx.http_port))
    print "Started OpenBazaar Web App at http://%s:%s" % \
          (ob_ctx.http_ip, ob_ctx.http_port)


def attempt_browser_open(ob_ctx):
    if not ob_ctx.disable_open_browser:
        open_default_webbrowser('http://%s:%s' % (ob_ctx.http_ip, ob_ctx.http_port))


def setup_signal_handlers(application):
    try:
        signal.signal(signal.SIGTERM, application.shutdown)
    except ValueError:
        pass


def node_starter(ob_ctxs):
    # This is the target for the the Process which
    # will spawn the children processes that spawn
    # the actual OpenBazaar instances.

    for ob_ctx in ob_ctxs:
        p = multiprocessing.Process(target=start_node, args=(ob_ctx,),
                                    name="Process::openbazaar_daemon::target(start_node)")
        p.daemon = False  # python has to wait for this user thread to end.
        p.start()


def start_node(ob_ctx):
    logger = create_logger(ob_ctx)
    application = MarketApplication(ob_ctx)
    setup_signal_handlers(application)
    application.start_app()
    log_openbazaar_start(logger, ob_ctx)
    attempt_browser_open(ob_ctx)
    start_io_loop()
