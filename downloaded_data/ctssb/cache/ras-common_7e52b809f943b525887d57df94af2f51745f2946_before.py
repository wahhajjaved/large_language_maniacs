##############################################################################
#                                                                            #
#   Generic Configuration tool for Micro-Service environment discovery       #
#   License: MIT                                                             #
#   Copyright (c) 2017 Crown Copyright (Office for National Statistics)      #
#                                                                            #
##############################################################################
#
#   ONSEnvironment wraps the application environment in terms of configuration
#   files, environment variables and anything else that pops up.
#
##############################################################################
from platform import system
if system() == "Linux":
    from twisted.internet import epollreactor
    epollreactor.install()
from twisted.internet import reactor
from twisted.web import client
from configparser import ConfigParser, ExtendedInterpolation
from os import getenv
from connexion import App
from flask import Flask
from flask_cors import CORS
from flask_twisted import Twisted
from .ons_database import ONSDatabase
from .ons_cloudfoundry import ONSCloudFoundry
from .ons_logger import ONSLogger
from .ons_jwt import ONSJwt
from .ons_swagger import ONSSwagger
from .ons_cryptographer import ONSCryptographer
from .ons_registration import ONSRegistration
from .ons_rabbit import ONSRabbit
from socket import socket, AF_INET, SOCK_STREAM
from pathlib import Path
from os import getcwd

class ONSEnvironment(object):
    """

    """
    def __init__(self):
        """
        Setup access to ini files and the environment based on the environment
        variable ONS_ENV ...
        """
        self._jwt_algorithm = None
        self._jwt_secret = None
        self._port = None
        self._host = None
        self._gateway = None
        self._debug = None
        self.api_protocol = None
        self.api_host = None
        self.api_port = None
        self.flask_protocol = None
        self.flask_host = None
        self.flask_port = None

        self._config = ConfigParser()
        self._config._interpolation = ExtendedInterpolation()
        self._env = getenv('ONS_ENV', 'development')
        self._logger = ONSLogger(self)
        self._database = ONSDatabase(self)
        self._rabbit = ONSRabbit(self)
        self._cloudfoundry = ONSCloudFoundry(self)
        self._swagger = ONSSwagger(self)
        self._jwt = ONSJwt(self)
        self._cryptography = ONSCryptographer(self)
        self._registration = ONSRegistration(self)

    def info(self, text):
        self.logger.info('[env] {}'.format(text))

    def setup(self):
        """
        Setup the various modules, we want to call this specifically from the test routines
        as they won't want a running reactor for testing purposes ...
        """
        self.setup_ini()
        self._logger.activate()
        self._cloudfoundry.activate()
        self._database.activate()
        self._swagger.activate()
        self._jwt.activate()
        self._cryptography.activate()
        self._rabbit.activate()

    def activate(self, callback=None):
        """
        Start the ball rolling ...
        """
        self.setup()
        self._registration.activate()
        self.info('Acquired listening port "{}"'.format(self._port))


        if self.swagger.has_api:
            swagger_file = '{}/{}'.format(self.swagger.path, self.swagger.file)
            if not Path(swagger_file).is_file():
                self.info('Unable to access swagger file "{}"'.format(swagger_file))
                return

            swagger_ui = self.get('swagger_ui', 'ui')
            app = App(__name__, specification_dir='{}/{}'.format(getcwd(), self.swagger.path))
            app.add_api(self.swagger.file, arguments={'title': self.ms_name}, swagger_url=swagger_ui)
            CORS(app.app)
        else:
            app = Flask(__name__)
            CORS(app)

        reactor.suggestThreadPoolSize(200)
        client._HTTP11ClientFactory.noisy = False
        if callback:
            callback(app)

        Twisted(app).run(host='0.0.0.0', port=self.port)

    def setup_ini(self):
        self._config.read(['local.ini', '../local.ini', 'config.ini', '../config.ini'])
        self._jwt_algorithm = self.get('jwt_algorithm')
        self._jwt_secret = self.get('jwt_secret')
        self._port = self.get('port', getenv('PORT', self.get_free_port()))
        #self._gateway = self.get('api_host')
        self.api_host = self.get('api_host')
        self.api_port = self.get('api_port')
        self.api_protocol = self.get('api_protocol')
        self.flask_host = self.get('flask_host')
        self.flask_port = self.get('flask_port', self._port)
        self.flask_protocol = self.get('flask_protocol')
        self._debug = self.get('debug', False).lower() in ['yes', 'true']

    def get(self, attribute, default=None, section=None):
        """
        Recover an attribute from a section in a .INI file

        :param attribute: The attribute to recover
        :param default: The section to recover it from
        :param section: An optional section name, otherwise we use the environment
        :return: The value of the attribute or 'default' if not found
        """
        if not section:
            section = self._env
        if section not in self._config:
            return default
        return self._config[section].get(attribute, default)

    def set(self, attribute, value):
        """
        Store a variable back into the memory copy of our .INI file

        :param attribute: The key to write to
        :param value: The value to write
        """
        self._config[self._env][attribute] = value

    def get_free_port(self):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.bind(('localhost', 0))
        _, port = sock.getsockname()
        sock.close()
        return port

    @property
    def drop_database(self):
        return self.get('drop_database', 'false').lower() in ['yes', 'true']

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        self._port = value

    @property
    def host(self):
        return self._host if self._host else 'localhost'

    @host.setter
    def host(self, value):
        self._host = value

    @property
    def gateway(self):
        #return self._gateway
        return self.api_host

    @property
    def db(self):
        return self._database

    @property
    def logger(self):
        return self._logger

    @property
    def cf(self):
        return self._cloudfoundry

    @property
    def crypt(self):
        return self._cryptography

    @property
    def cipher(self):
        return self._cryptography

    @property
    def swagger(self):
        return self._swagger

    @property
    def jwt_algorithm(self):
        return self._jwt_algorithm

    @property
    def jwt_secret(self):
        return self._jwt_secret

    @property
    def jwt(self):
        return self._jwt

    @property
    def environment(self):
        return self._env

    @property
    def ms_name(self):
        return "ONS Micro-Service"

    @property
    def is_secure(self):
        return self.get('authentication', 'true').lower() in ['yes', 'true']

    @property
    def protocol(self):
        #return self.get('api_protocol', 'http')
        return self.api_protocol

    @property
    def api_protocol(self):
        return self._api_protocol

    @api_protocol.setter
    def api_protocol(self, value):
        self._api_protocol = value

    @property
    def api_host(self):
        return self._api_host

    @api_host.setter
    def api_host(self, value):
        self._api_host = value

    @property
    def api_port(self):
        return self._api_port

    @api_port.setter
    def api_port(self, value):
        self._api_port = value

    @property
    def flask_protocol(self):
        return self._flask_protocol

    @flask_protocol.setter
    def flask_protocol(self, value):
        self._flask_protocol = value

    @property
    def flask_host(self):
        return self._flask_host

    @flask_host.setter
    def flask_host(self, value):
        self._flask_host = value

    @property
    def flask_port(self):
        return self._flask_port

    @flask_port.setter
    def flask_port(self, value):
        self._flask_port = value

    @property
    def rabbit(self):
        return self._rabbit

    @property
    def debug(self):
        return self._debug