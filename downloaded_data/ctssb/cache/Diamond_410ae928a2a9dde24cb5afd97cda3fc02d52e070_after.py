
import inspect
import os
import socket

from diamond import *
from diamond.metric import Metric

# Detect the architecture of the system and set the counters for MAX_VALUES
# appropriately. Otherwise, rolling over counters will cause incorrect or
# negative values.

if platform.architecture()[0] == '64bit':
    MAX_COUNTER = (2 ** 64) - 1
else:
    MAX_COUNTER = (2 ** 32) - 1

from diamond.metric import Metric

class Collector(object):
    """
    The Collector class is a base class for all metric collectors.
    """

    def __init__(self, config, handlers):
        """
        Create a new instance of the Collector class
        """
        # Initialize Logger
        self.log = logging.getLogger('diamond')
        # Initialize Members
        self.name = self.__class__.__name__
        self.handlers = handlers
        self.last_values = {}

        # Get Collector class
        cls = self.__class__

        # Initialize config
        self.config = configobj.ConfigObj()
        
        # Check if default config is defined
        if self.get_default_config() is not None:
            # Merge default config
            self.config.merge(self.get_default_config())
            
        # Merge default Collector config
        self.config.merge(config['collectors']['default'])
        
        # Check if Collector config section exists
        if cls.__name__ in config['collectors']:
            # Merge Collector config section
            self.config.merge(config['collectors'][cls.__name__])
            
        # Check for config file in config directory
        configfile = os.path.join(config['server']['collectors_config_path'], cls.__name__) + '.conf'
        if os.path.exists(configfile):
            # Merge Collector config file
            self.config.merge(configobj.ConfigObj(configfile))
            
        # Handle some config file changes transparently
        if isinstance(self.config['byte_unit'], basestring):
            units = self.config['byte_unit'].split()
            self.config['byte_unit'] = []
            for unit in units:
                self.config['byte_unit'].append(unit)

    def get_default_config_help(self):
        """
        Returns the help text for the configuration options for this collector
        """
        return {
            'enabled'   : 'Enable collecting these metrics',
            'byte_unit' : 'Default numeric output(s)',
        }

    def get_default_config(self):
        """
        Return the default config for the collector
        """
        return {
            ### Defaults options for all Collectors
            
            # Uncomment and set to hardcode a hostname for the collector path
            # Keep in mind, periods are seperators in graphite
            # 'hostname': 'my_custom_hostname',
            
            # If you perfer to just use a different way of calculating the hostname
            # Uncomment and set this to one of these values:
            # fqdn_short  = Default. Similar to hostname -s
            # fqdn        = hostname output
            # fqdn_rev    = hostname in reverse (com.example.www)
            # uname_short = Similar to uname -n, but only the first part
            # uname_rev   = uname -r in reverse (com.example.www)
            # 'hostname_method': 'fqdn_short',
            
            # All collectors are disabled by default
            'enabled': False,
            
            # Path Prefix
            'path_prefix': 'servers',
            
            # Default splay time (seconds)
            'splay': 1,
            
            # Default Poll Interval (seconds)
            'interval': 300,
            
            # Default collector threading model
            'method': 'Sequential',
            
            # Default numeric output
            'byte_unit': 'byte',
        }

    def get_schedule(self):
        """
        Return schedule for the collector
        """
        # Return a dict of tuples containing (collector function, collector function args, splay, interval)
        return {self.__class__.__name__: (self._run, None, int(self.config['splay']), int(self.config['interval']))}

    def get_hostname(self):
        if 'hostname' in self.config:
            return self.config['hostname']
        if 'hostname_method' not in self.config or self.config['hostname_method'] == 'fqdn_short':
            return socket.getfqdn().split('.')[0]
        if self.config['hostname_method'] == 'fqdn':
            return socket.getfqdn().replace('.','_')
        if self.config['hostname_method'] == 'fqdn_rev':
            hostname = socket.getfqdn().split('.')
            hostname.reverse()
            hostname = '.'.join(hostname)
            return hostname
        if self.config['hostname_method'] == 'uname_short':
            return os.uname()[1].split('.')[0]
        if self.config['hostname_method'] == 'uname_rev':
            hostname = os.uname()[1].split('.')
            hostname.reverse()
            hostname = '.'.join(hostname)
            return hostname
        if self.config['hostname_method'].lower() == 'none':
            return None
        raise NotImplementedError(self.config['hostname_method'])

    def get_metric_path(self, name):
        """
        Get metric path
        """
        if 'path_prefix' in self.config:
            prefix = self.config['path_prefix']
        else:
            prefix = 'systems'

        hostname = self.get_hostname()
        if hostname is not None:
            prefix = prefix + "." + hostname

        if 'path' in self.config:
            path = self.config['path']
        else:
            path = self.__class__.__name__

        if path == '.':
            return '.'.join([prefix, name])
        else:
            return '.'.join([prefix, path, name])

    def collect(self):
        """
        Default collector method
        """
        raise NotImplementedError()

    def publish(self, name, value, precision=0):
        """
        Publish a metric with the given name
        """
        # Get metric Path
        path = self.get_metric_path(name)

        # Create Metric
        metric = Metric(path, value, None, precision)

        # Publish Metric
        self.publish_metric(metric)

    def publish_metric(self, metric):
        """
        Publish a Metric object
        """
        # Process Metric
        for h in self.handlers:
            h.process(metric)

    def derivative(self, name, new, max_value=0):
        """
        Calculate the derivative of the metric.
        """
        # Format Metric Path
        path = self.get_metric_path(name)

        if path in self.last_values:
            old = self.last_values[path]
            # Check for rollover
            if new < old:
                old = old - max_value
            # Get Change in X (value)
            dx = new - old
            # Get Change in Y (time)
            dy = int(self.config['interval'])
            result =  float(dx) / float(dy)
        else:
            result = 0

        # Store Old Value
        self.last_values[path] = new

        # Return result
        return result

    def _run(self):
        """
        Run the collector
        """
        # Log
        self.log.debug("Collecting data from: %s" % (self.__class__.__name__))
        try:
            # Collect Data
            self.collect()
        except Exception, e:
            # Log Error
            self.log.error(traceback.format_exc())
