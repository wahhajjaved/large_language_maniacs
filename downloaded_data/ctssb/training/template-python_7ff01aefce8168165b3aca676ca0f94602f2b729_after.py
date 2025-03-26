import socket
import sys
import ssl
import logging
import os
import inspect
from logging import handlers
from mycroft import helpers, event, messages, logger

_LOG_FORMAT = "[$BOLD%(asctime)-20s$RESET] [%(levelname)-18s]  %(message)s"
_COLOR_FORMAT = logger.formatter_message(_LOG_FORMAT, True)


class App(helpers.HelpersMixin, messages.MessagesMixin):
    """
    Superclass for Mycroft applications.

    Mycroft can fire the following event names:
      internal events:
        'connect' - fired after connection is established
        'error' - fired on error
        'event_loop' - before the event loop starts
        'end' - fired, if possible, when start() is exiting
      external events:
        any verb from Mycroft, such as
        'APP_MANIFEST_OK'
        'APP_MANIFEST_FAIL'
        etc ...
    """

    def start(
            self,
            manifest,
            name,
            host='localhost',
            port=1847,
            key_path='',
            cert_path='',
            silent=True):
        """
        Start this App.
        This attempts to connect to Mycroft.
        If connection is successful it sends APP_MANIFEST.
        Args:
            manifest - str or file-like, the path to this application's manifest
                       or a file-like object that will read() the manifest
            name - a name for your application
            host - str, the host to connect to (default 'localhost')
            port - int, the port to connect to (default 1847)
            key_path - str, path to the keyfile
            cert_path - str, path to the crt file
            silent - don't log anything
        """
        try:
            self.name = name
            self.manifest = manifest
            self.closing = False
            self.dependencies = {}
            self.setup_logger(silent)
            self.setup_handlers()
            self.setup_socket(
                '--no-tls' not in sys.argv,
                host=host,
                port=port,
                key_path=key_path,
                cert_path=cert_path
            )
            self.handlers('connect', fail_silently=True)
            self.logger.info('Sending Manifest')
            self.send_manifest(manifest)
            self.handlers('event_loop', fail_silently=True)
            try:
                self.event_loop()
            finally:
                self.handle_close()
        except IOError as e:
            if not hasattr(self, 'closing') or not self.closing:
                if hasattr(self, 'handlers'):
                    self.handlers('error', e, fail_silently=True)
                raise e
        except Exception as e:
            if hasattr(self, 'handlers'):
                self.handlers('error', e, fail_silently=True)
        finally:
            if hasattr(self, 'handlers'):
                self.handlers('end', fail_silently=True)

    def setup_logger(self, silent):
        """
        Setup the logger.
        Assigns the logger to `self.logger`
        Args:
            silent - when True, doesn't add any handlers
        """
        self.logger = logging.getLogger("mycroft")
        if silent:
            return
        self.logger.setLevel(logging.DEBUG)
        color_formatter = logger.ColoredFormatter(_COLOR_FORMAT)
        regular_formatter = logging.Formatter(
            '[%(asctime)-20s][%(levelname)-5s]  %(message)s'
        )
        try:
            os.mkdir('logs')
        except OSError:
            pass
        file_handler = handlers.TimedRotatingFileHandler(
            "{0}/{1}.log".format('logs', self.name),
            'midnight'
        )
        file_handler.setFormatter(regular_formatter)

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(color_formatter)
        self.logger.addHandler(console)
        self.logger.addHandler(file_handler)

    def setup_socket(
            self,
            use_tls=False,
            host='localhost',
            port=1847,
            key_path='',
            cert_path=''):
        """
        Setup the socket connection to Mycroft
        The socket is assigned to `self.socket`
        Args:
            use_tls - bool, True to use TLS (default False)
            host - string, host to use for connecting (default 'localhost')
            port - int, port to connect to (default 1847)
            key_path - string, file path to the keyfile
            cert_path - string, file path to the certificate file
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if use_tls:
            self.socket = ssl.wrap_socket(
                self.socket,
                keyfile=key_path,
                certfile=cert_path
            )
        self.socket.connect((host, port))

    def setup_handlers(self):
        """
        Construct the event handling object.
        The object is assigned to `self.handlers`
        Methods that are added by default:
            -any methods that are registered with the @mycroft.on('')
             decorator
            -methods that start with on_*** (event name is ***)
        """
        self.handlers = event.EventHandler(self.logger)
        for attr_name, val in inspect.getmembers(self):
            # handle the first type of event registration
            if hasattr(val, '_mycroft_events'):
                for ev_name in val._mycroft_events:
                    self.handlers[ev_name] = val
            # handle the second type of event registration
            elif (attr_name.startswith('on') and
                  attr_name != 'on' and
                  hasattr(val, '__call__')):
                self.handlers[attr_name[3:]] = val

    def on(self, ev_name, func):
        """
        Add a function to the record of handlers
        Args:
            ev_name: str, the type of message to which this responds
            func: function, what to call for responding to this message
        """
        self.handlers[ev_name] = func

    def event_loop(self):
        """
        Loops forever listening for messages
        """
        while not self.closing:
            self.handle_read()

    def handle_read(self):
        """
        Handle one message
        """
        length = int(self.recv_until_newline())
        message = str(self.socket.recv(length), encoding='UTF-8')
        parsed = self.parse_message(message)
        self.logger.info('Got {0}'.format(parsed['type']))
        self.logger.debug(parsed['data'])
        self.handlers(
            parsed['type'],
            body=parsed['data'],
        )

    def handle_close(self):
        self.down()
        self.logger.info('Disconnected from Mycroft')
        self.socket.close()
        for handler in self.logger.handlers:
            handler.close()

    def close(self):
        self.closing = True
        self.handle_close()

    def on_app_manifest_ok(self, body):
        self.verified = True
        self.logger.info('Manifest Verified')

    def on_app_manifest_fail(self, body):
        self.logger.error('Invalid application manifest')
        raise Exception('Invalid application manifest')

    def on_message_general_failure(self, body):
        self.logger.error(body['message'])
