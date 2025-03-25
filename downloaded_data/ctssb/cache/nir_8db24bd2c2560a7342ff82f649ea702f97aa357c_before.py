# coding: utf-8

import traceback
import multiprocessing
import logging
import logging.config
import os
import re
import sys
import zmq
import json
import argparse
import ConfigParser

import syncer.wdb
import syncer.wdb2ts
import syncer.utils
import syncer.zeromq

import modelstatus

DEFAULT_CONFIG_PATH = '/etc/syncer.ini'
DEFAULT_LOG_FILE_PATH = '/var/log/syncer.log'
DEFAULT_LOG_LEVEL = 'DEBUG'
DEFAULT_LOG_FORMAT = '%(asctime)s (%(levelname)s) %(message)s'

EXIT_SUCCESS = 0
EXIT_CONFIG = 1
EXIT_LOGGING = 2

MONITORING_OK = 0
MONITORING_WARNING = 1
MONITORING_CRITICAL = 2


class Configuration(object):
    def __init__(self, *args, **kwargs):
        self.config_parser = kwargs['config_parser'] if 'config_parser' in kwargs else self.create_config_parser()
        self.argument_parser = kwargs['argument_parser'] if 'argument_parser' in kwargs else self.create_argument_parser()
        self.setup_config_parser()
        self.setup_argument_parser()
        self.args = object

    def load(self, config_file):
        """Read a configuration file"""
        self.config_parser.readfp(config_file)

    @staticmethod
    def create_config_parser():
        """Instantiate a configuration parser"""
        return ConfigParser.SafeConfigParser()

    @staticmethod
    def create_argument_parser():
        """Instantiate a command line argument parser"""
        return argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    def setup_config_parser(self):
        self.config_parser.add_section('syncer')
        self.config_parser.add_section('wdb')

    def setup_argument_parser(self):
        self.argument_parser.add_argument('-c', '--config', help='path to configuration file', default=DEFAULT_CONFIG_PATH)

    def parse_args(self, args):
        self.args = self.argument_parser.parse_args(args)

    def get(self, section, key):
        return self.config_parser.get(section, key)

    def section_keys(self, section_name):
        return [x[0] for x in self.config_parser.items(section_name)]

    def section_options(self, section_name):
        return dict(self.config_parser.items(section_name))


class Model(modelstatus.utils.SerializeBase):
    __serializable__ = ['data_provider', 'model_run_age_warning', 'model_run_age_critical',
                        'available_model_run', 'wdb_model_run', 'wdb2ts_model_run',
                        'available_updated', 'wdb_updated', 'wdb2ts_updated',
                        'model_run_version', '_available_model_run_initialized',
                        ]

    def __init__(self, data):
        [setattr(self, key, value) for key, value in data.iteritems()]

        # Most recent model run according to web service
        self.available_model_run = None
        self._available_model_run_initialized = False

        # Model run loaded into WDB
        self.wdb_model_run = None

        # Model run used to update WDB2TS
        self.wdb2ts_model_run = None

        # Updated timestamps
        self.available_updated = None
        self.wdb_updated = None
        self.wdb2ts_updated = None

        # Overrides from --force
        self.must_update_wdb = False
        self.must_update_wdb2ts = False

        # Internal version increments of datasets
        self.model_run_version = {}

    @staticmethod
    def data_from_config_section(config, section_name):
        """Return config options for a model. Raise exception if mandatory config option is missing"""

        data = {}
        mandatory_options = ['data_provider', 'data_uri_pattern', 'data_file_count', 'load_program']

        section_keys = config.section_keys(section_name)
        for option in mandatory_options:
            if option not in section_keys:
                raise ConfigParser.NoOptionError(option, section_name)

        data = config.section_options(section_name)
        data['data_file_count'] = int(data['data_file_count'])

        for param in ['model_run_age_warning', 'model_run_age_critical']:
            if param in data:
                data[param] = int(data[param])

        return data

    def get_data_provider_or_group(self):
        """
        Return the name of the data provider group if the model has this
        attribute. If not, return the data provider name.
        """
        for attr in ['data_provider_group', 'data_provider']:
            if hasattr(self, attr):
                return getattr(self, attr)
        raise RuntimeError("A bug in the code enabled 'data_provider' to be a non-mandatory configuration option to Model.")

    def _valid_model_run(self, model_run):
        return isinstance(model_run, modelstatus.BaseResource)

    def _validate_model_run(self, model_run):
        """
        Check that `model_run` is of the correct type.
        """
        if model_run is not None and not self._valid_model_run(model_run):
            raise TypeError("%s argument 'model_run' must inherit from modelstatus.BaseResource" % sys._getframe().f_code.co_name)

    def set_available_model_run(self, model_run):
        """
        Update `self.available_model_run` with the most recent model run,
        usually from the REST API service.
        """
        self._validate_model_run(model_run)
        self.available_model_run = model_run
        self._available_model_run_initialized = True
        self.available_updated = syncer.utils.get_utc_now()
        if self.available_model_run:
            logging.info("Model %s has new model run: %s" % (self, self.available_model_run))

    def model_run_initialized(self):
        """
        Return True if this Model has a ModelRun available.
        """
        return self._available_model_run_initialized is True

    def set_wdb_model_run(self, model_run):
        """
        Update `self.wdb_model_run` with the model run that has been loaded into WDB.
        """
        self._validate_model_run(model_run)
        self.wdb_model_run = model_run
        self.wdb_updated = syncer.utils.get_utc_now()
        self.set_must_update_wdb(False)
        logging.info("Model %s has been loaded into WDB, model run: %s" % (self, self.wdb_model_run))

    def set_wdb2ts_model_run(self, model_run):
        """
        Update `self.wdb2ts_model_run` with the model run that has been used to update WDB2TS.
        """
        self._validate_model_run(model_run)
        self.wdb2ts_model_run = model_run
        self.wdb2ts_updated = syncer.utils.get_utc_now()
        self.set_must_update_wdb2ts(False)
        logging.info("Model %s has been updated in WDB2TS, model run: %s" % (self, self.wdb2ts_model_run))

    def has_pending_wdb_load(self):
        """
        Returns True if the available model run has not been loaded into WDB yet.
        """
        if self.model_run_initialized():
            if self.available_model_run is None:
                return False
            if self.must_update_wdb:
                return True
            if self.wdb_model_run is None:
                return True
            return self.available_model_run.id != self.wdb_model_run.id
        return False

    def has_pending_wdb2ts_update(self):
        """
        Returns True if the model run loaded into WDB has not been used to update WDB2TS yet.
        """
        if self.wdb_model_run is None:
            return False
        if self.must_update_wdb2ts:
            return True
        if self.wdb2ts_model_run is None:
            return True
        return self.wdb_model_run.id != self.wdb2ts_model_run.id

    def set_must_update_wdb(self, value):
        """
        Override internal state of WDB model run
        """
        self.must_update_wdb = value

    def set_must_update_wdb2ts(self, value):
        """
        Override internal state of WDB2TS model run
        """
        self.must_update_wdb2ts = value

    def get_matching_data(self, dataset):
        """
        Return a subset of the list `dataset' that matches self.data_uri_pattern.
        """
        subset = []
        for data in dataset:
            if re.search(self.data_uri_pattern, data.href) is not None:
                subset += [data]
        return subset

    def is_complete_dataset(self, dataset):
        """
        Returns True if get_matching_data(dataset) returns the amount of data
        entries required by the data_file_count configuration option for this model.
        """
        return len(self.get_matching_data(dataset)) == self.data_file_count

    def get_model_run_key(self, model_run):
        """
        Return a compound key used for identifying a unique reference time and
        data provider combination used in a specific model run.
        """
        return model_run.serialize_reference_time(model_run.reference_time)

    def set_model_run_version(self, model_run, version):
        """
        Set the internal version of a model run.
        """
        key = self.get_model_run_key(model_run)
        self.model_run_version[key] = version

    def get_model_run_version(self, model_run):
        """
        Return the definite version of the specified model run; a combination
        of authoritative version and internal version.
        """
        return model_run.version + self.get_internal_model_run_version(model_run)

    def get_internal_model_run_version(self, model_run):
        """
        Return the internal version of the specified model run.
        """
        key = self.get_model_run_key(model_run)
        if key not in self.model_run_version:
            return 0
        return self.model_run_version[key]

    def increment_model_run_version(self, model_run):
        """
        Increment the internal model run version counter by one.
        """
        self.set_model_run_version(model_run, self.get_internal_model_run_version(model_run) + 1)

    def get_monitoring_state(self):
        """
        Return monitoring state: OK, WARNING or CRITICAL
        """
        if not self.model_run_initialized():
            return MONITORING_OK
        age = self.available_model_run.age() / 60
        if age > self.model_run_age_critical:
            return MONITORING_CRITICAL
        if age > self.model_run_age_warning:
            return MONITORING_WARNING
        return MONITORING_OK

    def _serialize_model_run(self, value):
        return value.serialize() if self._valid_model_run(value) else None

    def serialize_available_model_run(self, value):
        return self._serialize_model_run(value)

    def serialize_wdb_model_run(self, value):
        return self._serialize_model_run(value)

    def serialize_wdb2ts_model_run(self, value):
        return self._serialize_model_run(value)

    def serialize_available_updated(self, value):
        return self._serialize_datetime(value) if value else None

    def serialize_wdb_updated(self, value):
        return self._serialize_datetime(value) if value else None

    def serialize_wdb2ts_updated(self, value):
        return self._serialize_datetime(value) if value else None

    def _unserialize_model_run(self, value):
        return modelstatus.ModelRun(value) if value else None

    def unserialize_available_model_run(self, value):
        return self._unserialize_model_run(value)

    def unserialize_wdb_model_run(self, value):
        return self._unserialize_model_run(value)

    def unserialize_wdb2ts_model_run(self, value):
        return self._unserialize_model_run(value)

    def unserialize_available_updated(self, value):
        return self._unserialize_datetime(value) if value else None

    def unserialize_wdb_updated(self, value):
        return self._unserialize_datetime(value) if value else None

    def unserialize_wdb2ts_updated(self, value):
        return self._unserialize_datetime(value) if value else None

    def __repr__(self):
        return self.data_provider


class Daemon(object):
    def __init__(self, config, models, zmq_subscriber, zmq_agent, wdb, wdb2ts, model_run_collection, data_collection, tick, state_file):
        self.config = config
        self.models = models
        self.zmq_subscriber = zmq_subscriber
        self.zmq_agent = zmq_agent
        self.wdb = wdb
        self.wdb2ts = wdb2ts
        self.model_run_collection = model_run_collection
        self.data_collection = data_collection
        self.tick = tick
        self.state_file = state_file

        # Set up polling on the ZeroMQ sockets
        self.zmq_poller = zmq.Poller()
        self.zmq_poller.register(self.zmq_subscriber.sock, zmq.POLLIN)
        self.zmq_poller.register(self.zmq_agent.sub, zmq.POLLIN)

        if not isinstance(models, set):
            raise TypeError("'models' must be a set of models")
        for model in self.models:
            if not isinstance(model, Model):
                raise TypeError("'models' set must contain only models")

        logging.info("Daemon initialized with the following model configuration:")
        num_models = len(self.models)
        for num, model in enumerate(self.models):
            logging.info(" %2d of %2d: %s" % (num + 1, num_models, model.data_provider))
        logging.info("Main loop interval set to %d seconds.", self.tick)

        state = self.read_state_file()
        try:
            self.load_state(state)
        except Exception:
            logging.critical("Either the state file is corrupt, or you encountered a bug. Cannot read this state file!")
            raise

    def read_state_file(self):
        """
        Read JSON state information from a file into a dictionary.
        """
        logging.info("Loading state information from %s" % self.state_file)
        try:
            with open(self.state_file, 'r') as f:
                contents = f.read().strip()
            if not contents:
                return {}
            return json.loads(contents)
        except ValueError:
            logging.critical("Syntax error in state file, expecting valid JSON")
            raise
        except IOError:
            if os.path.isfile(self.state_file):
                raise
            logging.info("File does not exist, continuing with blank slate.")
        return {}

    def write_state_file(self, state):
        """
        Write JSON state information into a file.
        """
        logging.info("Writing state information to %s" % self.state_file)
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, sort_keys=True, indent=4)
        except IOError, e:
            logging.error("Error writing state file: %s" % unicode(e))

    def load_state(self, state):
        """
        Load state from a dictionary.
        """
        if 'models' not in state:
            return
        for model in self.models:
            for serialized in state['models']:
                if serialized['data_provider'] == model.data_provider:
                    model.unserialize(serialized)

    def make_state(self):
        """
        Generate a dictionary with state data.
        """
        model_state = [model.serialize() for model in self.models]
        return {
            'models': model_state
        }

    def write_state(self):
        """
        Shortcut to make_state and write_state_file.
        """
        state = self.make_state()
        return self.write_state_file(state)

    def sync_zmq_status(self):
        """
        Send status update to the ZeroMQ controller.
        """
        logging.debug("Synchronizing model status with ZeroMQ controller.")
        model_list = [model.serialize() for model in self.models]
        self.zmq_agent.sync_status({'models': model_list})

    def get_latest_model_run(self, model):
        """Fetch the latest model run from REST API, and assign it to the provided Model."""

        if not isinstance(model, Model):
            raise TypeError("Only accepts syncer.Model as argument")

        try:
            # Try fetching the latest data set
            latest = self.model_run_collection.get_latest(model.data_provider)

            # No results from server, should only happen in freshly installed instances
            if len(latest) == 0:
                logging.info("REST API does not contain any recorded model runs.")
                logging.warn("Syncer will not query for model runs again until restarted, or notified by publisher.")
                self.set_available_model_run(model, None, False)

            # More than one result, this is a server error and should not happen
            elif len(latest) > 1:
                logging.error("REST API returned more than one result when fetching latest model run, this should not happen!")

            # Valid result
            else:
                self.set_available_model_run(model, latest[0], False)

        # Server threw an error, recover from that
        except syncer.exceptions.RESTException, e:
            logging.error("REST API threw up with an exception: %s" % e)

    def handle_zmq_event(self, event):
        logging.info("Received %s" % unicode(event))
        if event.resource == 'model_run':
            id = event.id
        elif event.resource == 'data':
            try:
                data_object = self.data_collection.get_object(event.id)
            except syncer.exceptions.RESTException, e:
                logging.error("Server returned invalid resource: %s" % e)
                return
            id = data_object.model_run_id
        else:
            logging.info("Nothing to do with this kind of event; no action taken.")
            return

        self.load_model_run(id, False)

    def load_model_run(self, id, forced):
        """
        Download model run information from Modelstatus, and set it as an available model run
        """
        try:
            model_run_object = self.model_run_collection.get_object(id)
        except syncer.exceptions.RESTException, e:
            logging.error("Server returned invalid resource: %s" % e)
            return False

        for model in self.models:
            if model.data_provider == model_run_object.data_provider:
                self.set_available_model_run(model, model_run_object, forced)
                if forced:
                    logging.warning("Forcing WDB load and WDB2TS update for model run %d" % id)
                    model.set_must_update_wdb(True)
                    model.set_must_update_wdb2ts(True)
                return True

        logging.info("Syncer is not configured to load model '%s', no action taken" % model_run_object.data_provider)
        return False

    def handle_zmq_command(self, tokens):
        """
        Execute a command from the internal command queue.
        This input is already sanitized.
        """
        logging.info("Executing remote command: %s" % tokens)

        if tokens['command'] == 'load':
            self.load_model_run(tokens['model_run_id'], tokens['force'])

    def set_available_model_run(self, model, model_run, forced):
        """
        Check if a model run contains data sets, and set it as an available model run
        """
        if model_run is not None:
            if len(model_run.data) == 0:
                logging.warn("Model run %s contains no data, discarding." % model_run.id)
                return
            if not model.is_complete_dataset(model_run.data):
                if forced:
                    logging.warn("Model run %s is not complete, but I'm being forced, so loading it anyway." % model_run.id)
                else:
                    logging.warn("Model run %s is not complete, discarding." % model_run.id)
                    return

            model.increment_model_run_version(model_run)

        model.set_available_model_run(model_run)
        self.sync_zmq_status()
        self.write_state()

    def load_model(self, model):
        """
        Load the latest model run of a certain model into WDB
        """
        logging.info("Loading model %s into WDB..." % model)

        try:
            self.wdb.load_model_run(model, model.available_model_run)
            self.wdb.cache_model_run(model.available_model_run)
            model.set_wdb_model_run(model.available_model_run)
            self.sync_zmq_status()
            self.write_state()

        except syncer.exceptions.WDBLoadFailed, e:
            logging.error("WDB load failed: %s" % e)
        except syncer.exceptions.OpdataURIException, e:
            logging.error("Failed to load some model data due to erroneous opdata uri: %s" % e)
        except syncer.exceptions.WDBCacheFailed, e:
            logging.error("Failed to cache model data, will try loading again: %s" % e)

    def update_wdb2ts(self, model):
        """
        Update WDB2TS with new model information.
        """
        logging.info("Updating model %s in WDB2TS..." % model)

        try:
            self.wdb2ts.update_wdb2ts(model, model.wdb_model_run)
            model.set_wdb2ts_model_run(model.wdb_model_run)
            self.sync_zmq_status()
            self.write_state()

        except syncer.exceptions.WDB2TSException, e:
            logging.error("Failed to update WDB2TS: %s" % unicode(e))

    def main_loop_poll(self):
        """
        If ZeroMQ events do not arrive, Syncer might not load a model.
        This function will make sure that the REST API server is explicitly
        checked for updated model data if Syncer is currently issuing a WARNING
        or CRITICAL state for that model.
        """
        for model in self.models:
            state = model.get_monitoring_state()
            if state == MONITORING_WARNING:
                state = 'WARNING'
            elif state == MONITORING_CRITICAL:
                state = 'CRITICAL'
            else:
                continue

            logging.warning("Model %s is out of date (state %s). We might have missed a signal from ZeroMQ. Trying to fetch latest version from API..." % (model, state))
            self.get_latest_model_run(model)

    def main_loop_zmq(self):
        """
        Check if we've got something from the Modelstatus ZeroMQ publisher or
        the internal command queue.  This function will block for the amount of
        seconds defined in the configuration option `syncer.tick`.
        """

        events = dict(self.zmq_poller.poll(self.tick * 1000))
        if not events:
            return None

        if self.zmq_subscriber.sock in events:
            zmq_event = self.zmq_subscriber.get_event()
            if zmq_event:
                self.handle_zmq_event(zmq_event)

        if self.zmq_agent.sub in events:
            zmq_command = self.zmq_agent.get_command()
            self.handle_zmq_command(zmq_command)

    def main_loop_inner(self):
        """
        This function is a single iteration in the main loop.
        It checks for ZeroMQ messages, downloads model run information from the
        Modelstatus REST API service, loads data into WDB, and updates WDB2TS
        if applicable.
        """

        # Try to initialize all un-initialized models with current model run status
        for model in self.models:
            if not model.model_run_initialized():
                logging.info("Model %s does not have any information about model runs, initializing from API..." % model)
                self.get_latest_model_run(model)

        # Loop through models and see which are not loaded into WDB yet
        for model in self.models:
            if model.has_pending_wdb_load():
                logging.info("Model %s has a new model run, not yet loaded into WDB." % model)
                self.load_model(model)

        # Loop through models again, and see which are loaded into WDB but not yet used to update WDB2TS
        update_models = []
        for model in self.models:
            if model.has_pending_wdb2ts_update():
                update_models += [model]

        # Fetch new WDB2TS status information if a model needs updating
        if update_models:
            try:
                self.wdb2ts.load_status()
            except syncer.exceptions.WDB2TSMissingContentException, e:
                logging.critical("Error in WDB2TS configuration: %s", unicode(e))
            except syncer.exceptions.WDB2TSServerException, e:
                logging.error("Can not fetch WDB2TS status information: %s", unicode(e))
            else:

                # Update all models in WDB2TS
                for model in update_models:
                    logging.info("WDB2TS is out of sync with WDB on model %s" % model)
                    self.update_wdb2ts(model)

    def run(self):
        """Responsible for running the main loop. Returns the program exit code."""
        logging.info("Daemon started.")

        self.sync_zmq_status()
        self.write_state()

        try:
            while True:
                self.main_loop_poll()
                self.main_loop_inner()
                self.main_loop_zmq()

        except KeyboardInterrupt:
            logging.info("Terminated by SIGINT")

        logging.info("Daemon is terminating.")
        return EXIT_SUCCESS


def setup_logging(config_file):
    """Set up logging based on configuration file."""
    return logging.config.fileConfig(config_file, disable_existing_loggers=True)


def run(argv):

    # Parse command line arguments and read the configuration file
    try:
        config = Configuration()
        config.parse_args(argv)
        config.load(open(config.args.config))
    except IOError, e:
        logging.critical("Could not read configuration file: %s" % unicode(e))
        return EXIT_CONFIG
    except Exception, e:
        logging.critical("Unhandled exception while loading configuration: %s" % unicode(e))
        raise e

    # Set up proper logging
    try:
        setup_logging(config.args.config)
    except ConfigParser.Error, e:
        logging.critical("There is an error in the logging configuration: %s" % unicode(e))
        return EXIT_LOGGING
    except IOError, e:
        logging.critical("Could not read logging configuration file: %s" % unicode(e))
        return EXIT_LOGGING

    try:
        wdb = syncer.wdb.WDB(config.get('wdb', 'host'), config.get('wdb', 'ssh_user'))

        # Get all wdb2ts services from comma separated list in config
        wdb2ts_services = [s.strip() for s in config.get('wdb2ts', 'services').split(',')]
        wdb2ts = syncer.wdb2ts.WDB2TS(config.get('wdb2ts', 'base_url'), wdb2ts_services)
    except ConfigParser.NoOptionError, e:
        logging.critical("Missing configuration for WDB host")
        return EXIT_CONFIG

    # Read configuration
    logging.info("Syncer is started")
    model_keys = set([model.strip() for model in config.get('syncer', 'models').split(',')])
    models = set([Model(Model.data_from_config_section(config, 'model_%s' % key)) for key in model_keys])
    base_url = config.get('webservice', 'url')
    verify_ssl = bool(int(config.get('webservice', 'verify_ssl')))
    tick = int(config.get('syncer', 'tick'))
    state_file = config.get('syncer', 'state_file')

    # Instantiate REST API collection objects
    model_run_collection = modelstatus.ModelRunCollection(base_url, verify_ssl)
    data_collection = modelstatus.DataCollection(base_url, verify_ssl)

    # Start the ZeroMQ modelstatus subscriber process
    zmq_subscriber_socket = config.get('zeromq', 'socket')
    tcp_keepalive_interval = int(config.get('zeromq', 'tcp_keepalive_interval'))
    tcp_keepalive_count = int(config.get('zeromq', 'tcp_keepalive_count'))
    zmq_subscriber = syncer.zeromq.ZMQSubscriber(zmq_subscriber_socket, tcp_keepalive_interval, tcp_keepalive_count)
    logging.info("ZeroMQ subscriber listening for events from %s, TCP keepalive interval=%d count=%d" % (zmq_subscriber_socket, tcp_keepalive_interval, tcp_keepalive_count))

    # Instantiate ZeroMQ agent class
    zmq_agent = syncer.zeromq.ZMQAgent()

    # Start the ZeroMQ controller process
    zmq_controller_socket = config.get('zeromq', 'controller_socket')
    zmq_ctl_proc = multiprocessing.Process(target=run_zmq_controller, args=(zmq_controller_socket,))
    zmq_ctl_proc.start()
    logging.info("ZeroMQ controller socket listening for commands on %s" % zmq_controller_socket)

    # Start main application
    try:
        daemon = Daemon(config, models, zmq_subscriber, zmq_agent, wdb, wdb2ts, model_run_collection, data_collection, tick, state_file)
        exit_code = daemon.run()
    except:
        zmq_ctl_proc.terminate()
        raise

    return exit_code


def run_zmq_controller(sock):
    controller = syncer.zeromq.ZMQController(sock)
    try:
        controller.run()
    except (SystemExit, KeyboardInterrupt):
        pass


def main(argv):
    # Set up default initial logging, in case something goes wrong during config parsing
    logging.basicConfig(format=DEFAULT_LOG_FORMAT, level=DEFAULT_LOG_LEVEL)
    logging.info("Starting Syncer...")

    try:
        exit_code = run(argv)
    except:
        exception = traceback.format_exc().split("\n")
        logging.critical("***********************************************************")
        logging.critical("Uncaught exception during program execution. THIS IS A BUG!")
        logging.critical("***********************************************************")
        for line in exception:
            logging.critical(line)
        exit_code = 255

    logging.info("Exiting with status %d", exit_code)
    sys.exit(exit_code)
