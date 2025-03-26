import configparser
from logging.config import fileConfig

from pkg_resources import resource_filename, Requirement


# region Transformation functions

class ConfigValueError(Exception):
    """ Raised when a configuration value is not valid for the key """

    def __init__(self, key_name, type_name, actual_value, help_message=None):
        self.message = "key '%s' expects an %s value, but was '%s'" % \
                       (key_name, type_name, actual_value)

        if help_message:
            self.message += ": %s" % help_message


def ip_port(key_name: str, value: str) -> int:
    """
    Parses a port in string format, returning the corresponding port as
    an integer. Raises a ValueError if the port is not valid with a good
    error message indicating the error.
    """
    try:
        port = int(value)
        if not (0 < port < 65536):
            raise ValueError()

    except ValueError:
        raise ConfigValueError(
            key_name,
            type_name='IP port',
            actual_value=value,
            help_message="must be an integer value between 0 and 65536"
        )

    return port


def positive_float(key_name: str, value: str) -> float:
    """
    Converts the specified value to a float if the value is positive.

    :param key_name: name of the key to which the vlaue corresponds
    :param value: the value to convert to a float
    :return: float value
    :raise ValueError: if the value is not a float or is a non-positive float
    """

    try:
        converted_value = float(value)
        if converted_value <= 0:
            raise ValueError()

    except ValueError:
        raise ConfigValueError(
            key_name,
            type_name='positive float',
            actual_value=value
        )

    return converted_value


def string(key_name: str, value: str) -> str:
    """ Returns the specified value without performing any action """
    return value


# endregion


class AethalometerConfiguration:
    # Resource for the default configurations for the loggers
    LOGS_CONF_FILE = resource_filename(
        Requirement.parse("aethalometer_collector"),
        'aethalometer_collector/logs.ini')

    # Resource for the default configuration file
    DEFAULT_CONF_FILE = resource_filename(
        Requirement.parse("aethalometer_collector"),
        'aethalometer_collector/default.ini')

    # This dictionary stores the configuration keys
    # For each key it stores the section where the key is placed and the
    # transformation function to transform the string value into the required
    # value format (see transformation functions below)
    config_keys = {
        'reconnect_period': ('base', positive_float),
        'message_period': ('base', positive_float),
        'producer_ip': ('aethalometer', string),
        'producer_port': ('aethalometer', ip_port),
        'storage_directory': ('aethalometer', string),
    }

    def __init__(self):
        """
        Initializes the configuration with the default values defined in the
        'default.ini' file.
        """
        self._config = configparser.ConfigParser()

        # Load the default configurations for the loggers
        fileConfig(self.LOGS_CONF_FILE)

        # Load the default configurations
        self.read(self.DEFAULT_CONF_FILE)

    def read(self, config_file):
        """
        Reads configurations from some configuration file. The values defined
        in the specified file will override the current values.

        :param config_file: the path to the config file to be read
        :raise NotFoundError: if the specified config file does not exist
        """
        with open(config_file) as file:
            self._config.read_file(file)

    def __getitem__(self, config_key):
        """
        Returns the config value for the specified config key. The value is
        returned in the required format (as specified in the config_key
        dictionary).

        :raise KeyError: if the specified key is not supported by this
        configuration
        """
        section, transform = self.config_keys[config_key]
        value = self._config[section][config_key]
        return transform(config_key, value)

    def __setitem__(self, key, value):
        section, transform = self.config_keys[key]
        self._config[section][key] = value
