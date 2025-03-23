import glob
import hashlib
import os
import sys

import enum
import shutil
import stat
import subprocess
import json
import tempfile
import urllib.request

from argparse import ArgumentParser
from json import JSONDecodeError
from traceback import format_exc
from urllib.error import URLError
from urllib.parse import urlparse

DESCRIPTION = 'Run an experiment as described in a BLUEFILE.'
JSON_INDENT = 2
OUTPUT_DIRECTORY = '/outputs'


def attach_args(parser):
    parser.add_argument(
        'blue_file', action='store', type=str, metavar='BLUEFILE',
        help='BLUEFILE (json) containing an experiment description as local PATH or http URL.'
    )
    parser.add_argument(
        '-o', '--outputs', action='store_true',
        help='Enable connectors specified in the BLUEFILE outputs section.'
    )
    parser.add_argument(
        '-d', '--debug', action='store_true',
        help='Write debug info, including detailed exceptions, to stdout.'
    )


def main():
    parser = ArgumentParser(description=DESCRIPTION)
    attach_args(parser)
    args = parser.parse_args()

    result = run(args)

    if args.__dict__.get('debug'):
        print(json.dumps(result, indent=JSON_INDENT))

    scheme = urlparse(args.blue_file).scheme
    if _is_file_scheme_remote(scheme):
        _post_result(args.blue_file, result)

    if result['state'] == 'succeeded':
        return 0

    return 1


class OutputMode(enum.Enum):
    Connectors = 0
    Directory = 1


def run(args):
    result = {
        'command': None,
        'process': None,
        'debugInfo': None,
        'state': 'succeeded'
    }

    connector_manager = ConnectorManager()
    try:
        blue_location = args.blue_file
        if args.outputs:
            output_mode = OutputMode.Connectors
        else:
            output_mode = OutputMode.Directory

        blue_data = get_blue_data(blue_location)

        working_dir = blue_data.get('workDir')
        if working_dir is None:
            raise KeyError('Invalid BLUE file. "workDir" is required.')
        create_working_dir(working_dir)

        if output_mode == OutputMode.Connectors and 'outputs' not in blue_data:
            raise AssertionError('--outputs/-o argument is set but no outputs section is defined in BLUE file.')

        # validate command
        command = blue_data.get('command')
        _validate_command(command)
        result['command'] = command

        # import, validate and execute connectors
        inputs = blue_data.get('inputs')
        if inputs is None:
            raise KeyError('Invalid BLUE file. "inputs" is not specified.')
        connector_manager.import_input_connectors(inputs)

        outputs = blue_data.get('outputs', {})
        cli = blue_data.get('cli', {})
        cli_outputs = cli.get('outputs', {})
        connector_manager.import_output_connectors(outputs, cli_outputs, output_mode)
        connector_manager.prepare_directories()

        connector_manager.validate_connectors(validate_outputs=(output_mode == OutputMode.Connectors))
        connector_manager.receive_connectors()

        # execute command
        execution_result = execute(command, work_dir=working_dir)
        result['process'] = execution_result.to_dict()
        if not execution_result.successful():
            raise ExecutionError('Execution of command "{}" failed with the following message:\n{}'
                                 .format(' '.join(command), execution_result.get_std_err()))

        # check output files/directories
        connector_manager.check_outputs(working_dir)

        # send files and directories
        if output_mode == OutputMode.Connectors:
            connector_manager.send_connectors(working_dir)
        elif output_mode == OutputMode.Directory:
            connector_manager.move_output_files(working_dir, OUTPUT_DIRECTORY)

    except Exception as e:
        print_exception(e)
        result['debugInfo'] = exception_format()
        result['state'] = 'failed'
    finally:
        # umount directories
        umount_errors = connector_manager.umount_connectors()
        errors_len = len(umount_errors)
        umount_errors = [_format_exception(e) for e in umount_errors]
        if errors_len == 1:
            result['debugInfo'] += '\n{}'.format(umount_errors[0])
        elif errors_len > 1:
            result['debugInfo'] += '\n{}'.format('\n'.join(umount_errors))

    return result


def get_blue_data(blue_location):
    """
    If blue_file is an URL fetches this URL and loads the json content, otherwise tries to load the file as local file.
    :param blue_location: An URL or local file path as string
    :return: A tuple containing the content of the given file or url and a fetch mode.
    """
    scheme = urlparse(blue_location).scheme

    if _is_file_scheme_local(scheme):
        try:
            if scheme == 'path':
                blue_location = blue_location[5:]
            blue_file = open(blue_location, 'r')
        except FileNotFoundError as file_error:
            raise ExecutionError('Could not find blue file "{}" locally. Failed with the following message:\n{}'
                                 .format(blue_location, str(file_error)))
    elif _is_file_scheme_remote(scheme):
        try:
            blue_file = urllib.request.urlopen(blue_location)
        except (URLError, ValueError) as http_error:
            raise ExecutionError('Could not fetch blue file "{}". Failed with the following message:\n{}.'
                                 .format(blue_location, str(http_error)))
    else:
        raise ExecutionError('Unknown scheme for blue file "{}". Should be on of ["", "path", "http", "https"] but "{}"'
                             ' was found.'.format(blue_location, scheme))

    try:
        blue_data = json.load(blue_file)
    except JSONDecodeError as e:
        blue_file.close()
        raise ExecutionError('Could not decode blue file "{}". Blue file is not in json format.\n{}'
                             .format(blue_location, str(e)))
    return blue_data


def _is_file_scheme_local(file_scheme):
    return file_scheme == 'path' or file_scheme == ''


def _is_file_scheme_remote(file_scheme):
    return file_scheme == 'http' or file_scheme == 'https'


def _post_result(url, result):
    """
    Posts the given result dictionary to the given url
    :param url: The url to post the result to
    :param result: The result to post
    """
    bytes_data = bytes(json.dumps(result), encoding='utf-8')

    request = urllib.request.Request(url, data=bytes_data)
    request.add_header('Content-Type', 'application/json')

    # ignore response here
    urllib.request.urlopen(request)


def _validate_command(command):
    if command is None:
        raise ExecutionError('Invalid BLUE File. "command" is not specified.')

    if not isinstance(command, list):
        raise ExecutionError('Invalid BLUE File. "command" has to be a list of strings.\n'
                             'command: "{}"'.format(command))

    for s in command:
        if not isinstance(s, str):
            raise ExecutionError('Invalid BLUE File. "command" has to be a list of strings.\n'
                                 'command: "{}"\n'
                                 '"{}" is not a string'.format(command, s))


def create_working_dir(working_dir):
    """
    Tries to create the working directory for the executed process.
    :param working_dir: The directory where to execute the main command and from where to search output-files.
    :raise Exception: If working_dir could not be created
    """
    try:
        ensure_directory(working_dir)
    except FileExistsError:
        raise FileExistsError('Could not create working dir "{}", because it already exists and is not empty.'
                              .format(working_dir))
    except PermissionError as e:
        raise PermissionError('Failed to create working_dir "{}", because of insufficient permissions.\n{}'
                              .format(working_dir, str(e)))


def ensure_directory(d):
    """
    Ensures that directory d exists, is empty and is writable
    :param d: The directory that you want to make sure is either created or exists already.
    :raise PermissionError: If
    """
    if os.path.exists(d):
        if os.listdir(d):
            raise FileExistsError('Directory "{}" already exists and is not empty.'.format(d))
        else:
            return
    os.makedirs(d)

    # check write permissions
    st = os.stat(d)
    user_has_permissions = bool(st.st_mode & stat.S_IRUSR) and bool(st.st_mode & stat.S_IWUSR)
    group_has_permissions = bool(st.st_mode & stat.S_IRGRP) and bool(st.st_mode & stat.S_IWGRP)
    others_have_permissions = bool(st.st_mode & stat.S_IROTH) and bool(st.st_mode & stat.S_IWOTH)

    if (not user_has_permissions) and (not group_has_permissions) and (not others_have_permissions):
        raise PermissionError('Directory "{}" is not writable.'.format(d))


def resolve_connector_cli_version(connector_command, connector_cli_version_cache):
    """
    Returns the cli-version of the given connector.
    :param connector_command: The connector command to resolve the cli-version for.
    :param connector_cli_version_cache: Cache for connector cli version
    :return: The cli version string of the given connector
    :raise ConnectorError: If the cli-version could not be resolved.
    """
    cache_value = connector_cli_version_cache.get(connector_command)
    if cache_value:
        return cache_value

    try:
        result = execute([connector_command, 'cli-version'])
    except FileNotFoundError:
        raise ConnectorError('Could not find connector "{}"'.format(connector_command))

    std_out = result.std_out
    if result.successful() and len(std_out) == 1:
        cli_version = std_out[0]
        connector_cli_version_cache[connector_command] = cli_version
        return cli_version
    else:
        std_err = result.get_std_err()
        raise ConnectorError('Could not detect cli version for connector "{}". Failed with following message:\n{}'
                             .format(connector_command, std_err))


def execute_connector(connector_command, top_level_argument, access=None, path=None, listing=None):
    """
    Executes the given connector command with
    :param connector_command: The connector command to execute
    :param top_level_argument: The top level argument of the connector
    :param access: An access dictionary, if given the connector is executed with a temporary file as argument, that
    contains the access information
    :param path: The path where to receive the file/directory to or which file/directory to send
    :param listing: An optional listing, that is given to the connector as temporary file
    :return: A dictionary with keys 'returnCode', 'stdOut', 'stdErr'
    """
    # create access file
    access_file = None
    if access is not None:
        access_file = tempfile.NamedTemporaryFile('w')
        json.dump(access, access_file)
        access_file.flush()

    # create listing file
    listing_file = None
    if listing is not None:
        listing_file = tempfile.NamedTemporaryFile('w')
        json.dump(listing, listing_file)
        listing_file.flush()

    # build command
    command = [connector_command, top_level_argument]
    if access_file is not None:
        command.append('{}'.format(access_file.name))
    if path is not None:
        command.append('{}'.format(path))
    if listing_file is not None:
        command.append('--listing={}'.format(listing_file.name))

    # execute connector
    execution_result = execute(command)

    # remove temporary files
    if access_file is not None:
        access_file.close()
    if listing_file is not None:
        listing_file.close()

    return execution_result


class ConnectorType(enum.Enum):
    File = 0
    Directory = 1


class ConnectorClass:
    def __init__(self, connector_type, is_array, is_optional):
        self.connector_type = connector_type
        self._is_array = is_array
        self._is_optional = is_optional

    @staticmethod
    def from_string(s):
        is_optional = s.endswith('?')
        if is_optional:
            s = s[:-1]

        is_array = s.endswith('[]')
        if is_array:
            s = s[:-2]

        connector_type = None
        for ct in ConnectorType:
            if s == ct.name:
                connector_type = ct

        if connector_type is None:
            raise ConnectorError('Could not extract connector class from string "{}". Connector classes should start '
                                 'with "File" or "Directory" and optionally end with "[]" or "?" or "[]?"'.format(s))

        return ConnectorClass(connector_type, is_array, is_optional)

    def to_string(self):
        if self._is_array:
            return '{}[]'.format(self.connector_type.name)
        else:
            return self.connector_type.name

    def __repr__(self):
        return self.to_string()

    def __eq__(self, other):
        return (self.connector_type == other.connector_type) and (self._is_array == other.is_array())

    def is_file(self):
        return self.connector_type == ConnectorType.File

    def is_directory(self):
        return self.connector_type == ConnectorType.Directory

    def is_array(self):
        return self._is_array

    def is_optional(self):
        return self._is_optional


class InputConnectorRunner:
    """
    A ConnectorRunner can be used to execute the different functions of a Connector.

    A ConnectorRunner subclass is associated with a connector cli-version.
    Subclasses implement different cli-versions for connectors.

    A ConnectorRunner instance is associated with a blue input, that uses a connector.
    For every blue input, that uses a connector a new ConnectorRunner instance is created.
    """

    def __init__(self,
                 input_key,
                 input_index,
                 connector_command,
                 input_class,
                 mount,
                 access,
                 path,
                 listing=None,
                 checksum=None,
                 size=None):
        """
        Initiates an InputConnectorRunner.

        :param input_key: The blue input key
        :param input_index: The input index in case of File/Directory lists
        :param connector_command: The connector command to execute
        :param input_class: Either 'File' or 'Directory'
        :param mount: Whether the associated connector mounts or not
        :param access: The access information for the connector
        :param path: The path where to put the data
        :param listing: An optional listing for the associated connector
        :param checksum: An optional checksum (sha1 hash) for the associated file
        :param size: The optional size of the associated file in bytes
        """
        self._input_key = input_key
        self._input_index = input_index
        self._connector_command = connector_command
        self._input_class = input_class
        self._mount = mount
        self._access = access
        self._path = path
        self._listing = listing
        self._checksum = checksum
        self._size = size

        # Is set to true, after mounting
        self._has_mounted = False

    def get_input_class(self):
        return self._input_class

    def is_mounting(self):
        """
         :return: Returns whether this runner is mounting or not.
        """
        return self._mount

    def prepare_directory(self):
        """
        In case of input_class == 'Directory' creates path.
        In case of input_class == 'File' creates os.path.dirname(path).
        :raise ConnectorError: If the directory could not be created or if the path already exist.
        """
        path_to_create = self._path if self._input_class.is_directory() else os.path.dirname(self._path)

        try:
            ensure_directory(path_to_create)
        except PermissionError as e:
            raise ConnectorError('Could not prepare directory for input key "{}" with path "{}". PermissionError:\n{}'
                                 .format(self.format_input_key(), path_to_create, str(e)))
        except FileExistsError as e:
            raise ConnectorError('Could not prepare directory for input key "{}" with path "{}". '
                                 'Directory already exists and is not empty.\n{}'
                                 .format(self.format_input_key(), path_to_create, str(e)))

    def _receive_directory_content_check(self):
        """
        Checks if the given directory exists and if listing is set, if the listing is fulfilled.
        :raise ConnectorError: If the directory content is not as expected.
        """
        if not os.path.isdir(self._path):
            raise ConnectorError('Content check for input directory "{}" failed. Path "{}" does not exist.'
                                 .format(self.format_input_key(), self._path))

        if self._listing:
            listing_check_result = InputConnectorRunner.directory_listing_content_check(self._path, self._listing)
            if listing_check_result is not None:
                raise ConnectorError('Content check for input key "{}" failed. Listing is not fulfilled:\n{}'
                                     .format(self.format_input_key(), listing_check_result))

    @staticmethod
    def directory_listing_content_check(directory_path, listing):
        """
        Checks if a given listing is present under the given directory path.

        :param directory_path: The path to the base directory
        :param listing: The listing to check
        :return: None if no errors could be found, otherwise a string describing the error
        """
        for sub in listing:
            path = os.path.join(directory_path, sub['basename'])
            if sub['class'] == 'File':
                if not os.path.isfile(path):
                    return 'listing contains "{}" but this file could not be found on disk.'.format(path)
            elif sub['class'] == 'Directory':
                if not os.path.isdir(path):
                    return 'listing contains "{}" but this directory could not be found on disk'.format(path)
                listing = sub.get('listing')
                if listing:
                    res = InputConnectorRunner.directory_listing_content_check(path, listing)
                    if res is not None:
                        return res
        return None

    def _receive_file_content_check(self):
        """
        Checks if the given file exists. If a checksum is given checks if this checksum matches. If a size is given
        checks if this size matches the file size.
        :raise ConnectorError: If the given file does not exist, if the given hash does not match or if the given file
        size does not match.
        """
        if not os.path.isfile(self._path):
            raise ConnectorError('Content check for input file "{}" failed. Path "{}" does not exist.'
                                 .format(self.format_input_key(), self._path))
        if self._checksum:
            hasher = hashlib.sha1()
            with open(self._path, 'rb') as file:
                buf = file.read()
                hasher.update(buf)
            checksum = 'sha1${}'.format(hasher.hexdigest())
            if self._checksum != checksum:
                raise ConnectorError('Content check for input file "{}" failed. The given checksum "{}" '
                                     'does not match the checksum calculated from the file "{}".'
                                     .format(self.format_input_key(), self._checksum, checksum))

        if self._size is not None:
            size = os.path.getsize(self._path)
            if self._size != size:
                raise ConnectorError('Content check for input file "{}" failed. The given file size "{}" '
                                     'does not match the calculated file size "{}".'
                                     .format(self.format_input_key(), self._size, size))

    def validate_receive(self):
        """
        Executes receive_file_validate, receive_dir_validate or mount_dir_validate depending on input_class and mount
        """
        if self._input_class.is_directory():
            if self._mount:
                self.mount_dir_validate()
            else:
                self.receive_dir_validate()
        elif self._input_class.is_file():
            self.receive_file_validate()

    def receive(self):
        """
        Executes receive_file, receive_directory or receive_mount depending on input_class and mount
        """
        if self._input_class.is_directory():
            if self._mount:
                self.mount_dir()
                self._receive_directory_content_check()
                self._has_mounted = True
            else:
                self.receive_dir()
                self._receive_directory_content_check()
        elif self._input_class.is_file():
            self.receive_file()
            self._receive_file_content_check()

    def try_umount(self):
        """
        Executes umount, if connector is mounting and has mounted, otherwise does nothing.
        :raise ConnectorError: If the Connector fails to umount the directory
        """
        if self._has_mounted:
            self.umount_dir()

    def format_input_key(self):
        return format_key_index(self._input_key, self._input_index)

    def receive_file(self):
        raise NotImplementedError()

    def receive_file_validate(self):
        raise NotImplementedError()

    def receive_dir(self):
        raise NotImplementedError()

    def receive_dir_validate(self):
        raise NotImplementedError()

    def mount_dir_validate(self):
        raise NotImplementedError()

    def mount_dir(self):
        raise NotImplementedError()

    def umount_dir(self):
        raise NotImplementedError()


def _resolve_glob_pattern(glob_pattern, working_dir, connector_type=None):
    """
    Tries to resolve the given glob_pattern.
    :param glob_pattern: The glob pattern to resolve
    :param working_dir: The working dir from where to access output files
    :param connector_type: The connector class to search for
    :return: the resolved glob_pattern as list of strings
    """
    glob_pattern = os.path.join(working_dir, glob_pattern)
    glob_result = glob.glob(glob_pattern)
    if connector_type == ConnectorType.File:
        glob_result = [f for f in glob_result if os.path.isfile(f)]
    elif connector_type == ConnectorType.Directory:
        glob_result = [f for f in glob_result if os.path.isdir(f)]
    return glob_result


def _resolve_glob_pattern_and_throw(glob_pattern, output_key, working_dir, connector_type=None):
    """
    Tries to resolve the given glob_pattern. Raises an error, if the pattern could not be resolved or is ambiguous
    :param glob_pattern: The glob pattern to resolve
    :param output_key: The corresponding output key for Exception text
    :param working_dir: The working dir from where to access output files
    :param connector_type: The connector class to search for
    :return: The resolved path as string
    :raise ConnectorError: If the given glob_pattern could not be resolved or is ambiguous
    """
    paths = _resolve_glob_pattern(glob_pattern, working_dir, connector_type)
    if len(paths) == 1:
        return paths[0]
    elif len(paths) == 0:
        raise ConnectorError('Could not resolve glob "{}" for output key "{}". File/Directory not found.'
                             .format(glob_pattern, output_key))
    else:
        raise ConnectorError('Could not resolve glob "{}" for output key "{}". Glob is ambiguous.'
                             .format(glob_pattern, output_key))


class OutputConnectorRunner:
    """
    A OutputConnectorRunner can be used to execute different output functions of a Connector.

    A ConnectorRunner subclass is associated with a connector cli-version.
    Subclasses implement different cli-versions for connectors.

    A ConnectorRunner instance is associated with a blue input, that uses a connector.
    For every blue input, that uses a connector a new ConnectorRunner instance is created.
    """

    def __init__(self, output_key, connector_command, output_class, access, glob_pattern, listing=None):
        """
        initiates a OutputConnectorRunner.

        :param output_key: The blue output key
        :param connector_command: The connector command to execute
        :param output_class: The ConnectorClass for this output
        :param access: The access information for the connector
        :param glob_pattern: The glob_pattern to match
        :param listing: An optional listing for the associated connector
        """
        self._output_key = output_key
        self._connector_command = connector_command
        self._output_class = output_class
        self._access = access
        self._glob_pattern = glob_pattern
        self._listing = listing

    def validate_send(self):
        """
        Executes send_file_validate, send_dir_validate or send_mount_validate depending on input_class and mount
        """
        if self._output_class.is_directory():
            self.send_dir_validate()
        elif self._output_class.is_file():
            self.send_file_validate()

    def try_send(self, working_dir):
        """
        Executes send_file or send_dir depending on input_class.
        :param working_dir: The working dir from where to access output files
        :raise ConnectorError: If the given glob_pattern could not be resolved or is ambiguous.
                               Or if the executed connector fails.
        """
        path = _resolve_glob_pattern_and_throw(self._glob_pattern,
                                               self._output_key,
                                               working_dir,
                                               self._output_class.connector_type)
        if self._output_class.is_file():
            self.send_file(path)
        elif self._output_class.is_directory():
            self.send_dir(path)

    def send_file_validate(self):
        raise NotImplementedError()

    def send_file(self, path):
        raise NotImplementedError()

    def send_dir_validate(self):
        raise NotImplementedError()

    def send_dir(self, path):
        raise NotImplementedError()


class CliOutputRunner:
    """
    This CliOutputRunner is used to check if an cli output key is fulfilled and move the corresponding file into the
    outputs directory if needed.
    """
    def __init__(self, output_key, glob_pattern, output_class):
        """
        Creates a new CliOutputRunner
        :param output_key: The corresponding output key
        :param glob_pattern: The glob pattern to match against output files
        :param output_class: The class of the output
        """
        self._output_key = output_key
        self._glob_pattern = glob_pattern
        self._output_class = output_class

    def try_move(self, working_dir, output_dir):
        """
        Tries to move the associated output file into the output_dir.

        :param working_dir: The working directory from where to glob the output file
        :param output_dir: The directory to move the output files to.
        :raise ConnectorError: If the given glob_pattern could not be resolved or is ambiguous.
        """
        working_path = _resolve_glob_pattern_and_throw(self._glob_pattern,
                                                       self._output_key,
                                                       working_dir,
                                                       self._output_class.connector_type)

        # create output path
        output_dir = os.path.join(output_dir, self._output_key)
        output_path = os.path.join(output_dir, os.path.basename(working_path))
        try:
            ensure_directory(output_dir)
        except FileExistsError:
            raise FileExistsError('Could not create path for output key "{}", because path "{}" already exists and is '
                                  'not empty.'.format(self._output_key, output_dir))
        except PermissionError as e:
            raise PermissionError('Failed to create path "{}" for output key "{}", because of insufficient permissions.'
                                  '\n{}'.format(output_dir, self._output_key, str(e)))

        shutil.move(working_path, output_path)

    def check_output(self, working_dir):
        """
        Checks if the corresponding output is present relative to the given working directory.
        :param working_dir: The Directory from where to look for the file/directory.
        :raise ConnectorError: If the corresponding file/directory is not present on disk
        """
        glob_result = _resolve_glob_pattern(self._glob_pattern, working_dir, self._output_class.connector_type)

        # check ambiguous
        if len(glob_result) >= 2:
            files_directories = 'files' if self._output_class.connector_type == ConnectorType.File else 'directories'

            raise ConnectorError('Could not resolve glob "{}" for output key "{}". Glob is '
                                 'ambiguous. Found the following {}:\n{}'
                                 .format(self._glob_pattern, self._output_key, files_directories, glob_result))

        # check if key is required
        if not self._output_class.is_optional():
            if len(glob_result) == 0:
                file_directory = 'File' if self._output_class.connector_type == ConnectorType.File else 'Directory'
                raise ConnectorError('Could not resolve glob "{}" for required output key "{}". {} not '
                                     'found.'.format(self._glob_pattern, self._output_key, file_directory))


class InputConnectorRunner01(InputConnectorRunner):
    """
    This InputConnectorRunner implements the connector cli-version 0.1
    """

    def receive_file(self):
        execution_result = execute_connector(self._connector_command,
                                             'receive-file',
                                             access=self._access,
                                             path=self._path)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to receive file for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))

    def receive_file_validate(self):
        execution_result = execute_connector(self._connector_command,
                                             'receive-file-validate',
                                             access=self._access)
        if not execution_result.successful():
            raise ConnectorError('Connector failed to validate receive file for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))

    def receive_dir(self):
        execution_result = execute_connector(self._connector_command,
                                             'receive-dir',
                                             access=self._access,
                                             path=self._path,
                                             listing=self._listing)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to receive directory for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))

    def receive_dir_validate(self):
        execution_result = execute_connector(self._connector_command,
                                             'receive-dir-validate',
                                             access=self._access,
                                             listing=self._listing)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to validate receive directory for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))

    def mount_dir(self):
        execution_result = execute_connector(self._connector_command,
                                             'mount-dir',
                                             access=self._access,
                                             path=self._path)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to mount directory for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))

    def mount_dir_validate(self):
        execution_result = execute_connector(self._connector_command,
                                             'mount-dir-validate',
                                             access=self._access)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to validate mount directory for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))

    def umount_dir(self):
        execution_result = execute_connector(self._connector_command,
                                             'umount-dir', path=self._path)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to umount directory for input key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self.format_input_key(), execution_result.get_std_err()))


class OutputConnectorRunner01(OutputConnectorRunner):
    """
    This OutputConnectorRunner implements the connector cli-version 0.1
    """

    def send_file(self, path):
        execution_result = execute_connector(self._connector_command,
                                             'send-file',
                                             access=self._access,
                                             path=path)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to send file for output key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self._output_key, execution_result.get_std_err()))

    def send_file_validate(self):
        execution_result = execute_connector(self._connector_command,
                                             'send-file-validate',
                                             access=self._access)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to validate send file for output key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self._output_key, execution_result.get_std_err()))

    def send_dir(self, path):
        execution_result = execute_connector(self._connector_command,
                                             'send-dir',
                                             access=self._access,
                                             path=path,
                                             listing=self._listing)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to validate send file for output key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self._output_key, execution_result.get_std_err()))

    def send_dir_validate(self):
        execution_result = execute_connector(self._connector_command,
                                             'send-dir-validate',
                                             access=self._access,
                                             listing=self._listing)

        if not execution_result.successful():
            raise ConnectorError('Connector failed to validate send directory for output key "{}".\n'
                                 'Failed with the following message:\n{}'
                                 .format(self._output_key, execution_result.get_std_err()))


CONNECTOR_CLI_VERSION_INPUT_RUNNER_MAPPING = {
    '0.1': InputConnectorRunner01,
}


def create_input_connector_runner(input_key, input_value, input_index, assert_class, assert_list,
                                  connector_cli_version_cache):
    """
    Creates a proper InputConnectorRunner instance for the given connector command.

    :param input_key: The input key of the runner
    :param input_value: The input to create an runner for
    :param input_index: The index of the input in case of File/Directory lists
    :param assert_class: Assert this input class
    :param assert_list: Assert the input class to be a list of Files or Directories. Otherwise fail.
    :param connector_cli_version_cache: Cache for connector cli version
    :return: A ConnectorRunner
    :rtype InputConnectorRunner
    """
    try:
        connector_data = input_value['connector']
        connector_command = connector_data['command']
        access = connector_data['access']

        input_class = ConnectorClass.from_string(input_value['class'])
        path = input_value['path']
    except KeyError as e:
        raise ConnectorError('Could not create connector for input key "{}".\n'
                             'The following property was not found: "{}"'
                             .format(format_key_index(input_key, input_index), str(e)))

    mount = connector_data.get('mount', False)
    listing = input_value.get('listing')
    checksum = input_value.get('checksum')
    size = input_value.get('size')

    try:
        cli_version = resolve_connector_cli_version(connector_command, connector_cli_version_cache)
    except ConnectorError:
        raise ConnectorError('Could not resolve connector cli version for connector "{}" in input key "{}"'
                             .format(connector_command, format_key_index(input_key, input_index)))

    if mount and not input_class.is_directory():
        raise ConnectorError('Connector for input key "{}" has mount flag set but class is "{}". '
                             'Unable to mount if class is different from "Directory"'
                             .format(format_key_index(input_key, input_index), input_class.to_string()))

    # check if is ConnectorType matches
    if assert_list and not input_class.is_array():
        raise ConnectorError('Connector for input key "{}" is given as list, but input class is not list.'
                             .format(format_key_index(input_key, input_index)))
    if (assert_list is None) and input_class.is_array():
        raise ConnectorError('Connector for input key "{}" is not given as list, but input class is list.'
                             .format(format_key_index(input_key, input_index)))
    if (assert_class is not None) and (assert_class != input_class):
        raise ConnectorError('Connector for input key "{}" has unexpected class "{}". Expected class is "{}"'
                             .format(format_key_index(input_key, input_index), input_class, assert_class))

    connector_runner_class = CONNECTOR_CLI_VERSION_INPUT_RUNNER_MAPPING.get(cli_version)
    if connector_runner_class is None:
        raise Exception('This agent does not support connector cli-version "{}", but needed by connector "{}"'
                        .format(cli_version, connector_command))

    connector_runner = connector_runner_class(input_key,
                                              input_index,
                                              connector_command,
                                              input_class,
                                              mount,
                                              access,
                                              path,
                                              listing,
                                              checksum,
                                              size)

    return connector_runner


CONNECTOR_CLI_VERSION_OUTPUT_RUNNER_MAPPING = {
    '0.1': OutputConnectorRunner01,
}


def create_output_connector_runner(output_key, output_value, cli_output_value, connector_cli_version_cache):
    """
    Creates a proper OutputConnectorRunner instance for the given connector command.

    :param output_key: The output key of the runner
    :param output_value: The output to create a runner for
    :param cli_output_value: The cli description for the runner
    :param connector_cli_version_cache: Cache for connector cli version
    :return: A ConnectorRunner
    """
    try:
        connector_data = output_value['connector']
        connector_command = connector_data['command']
        access = connector_data['access']

        output_class = ConnectorClass.from_string(output_value['class'])
        glob_pattern = cli_output_value['outputBinding']['glob']
    except KeyError as e:
        raise ConnectorError('Could not create connector for output key "{}".\n'
                             'The following property was not found: "{}"'
                             .format(output_key, str(e)))

    mount = connector_data.get('mount', False)
    listing = output_value.get('listing')

    try:
        cli_version = resolve_connector_cli_version(connector_command, connector_cli_version_cache)
    except ConnectorError:
        raise ConnectorError('Could not resolve connector cli version for connector "{}" in output key "{}"'
                             .format(connector_command, output_key))

    if mount and not output_class.is_directory():
        raise ConnectorError('Connector for input key "{}" has mount flag set but class is "{}". '
                             'Unable to mount if class is different from "Directory"'
                             .format(output_key, output_class.to_string()))

    connector_runner_class = CONNECTOR_CLI_VERSION_OUTPUT_RUNNER_MAPPING.get(cli_version)
    if connector_runner_class is None:
        raise Exception('This agent does not support connector cli-version "{}", but needed by connector "{}"'
                        .format(cli_version, connector_command))

    connector_runner = connector_runner_class(output_key,
                                              connector_command,
                                              output_class,
                                              access,
                                              glob_pattern,
                                              listing)

    return connector_runner


def create_cli_output_runner(cli_output_key, cli_output_value):
    """
    Creates a CliOutputRunner.
    :param cli_output_key: The output key of the corresponding cli output
    :param cli_output_value: The output value given in the blue file of the corresponding cli output
    :return: A new instance of CliOutputRunner
    :raise ConnectorError: If the cli output is not valid.
    """
    try:
        output_class = ConnectorClass.from_string(cli_output_value['type'])
        glob_pattern = cli_output_value['outputBinding']['glob']
    except KeyError as e:
        raise ConnectorError('Could not create cli runner for output key "{}".\n'
                             'The following property was not found: "{}"'.format(cli_output_key, str(e)))

    return CliOutputRunner(cli_output_key, glob_pattern, output_class)


class ExecutionResult:
    def __init__(self, std_out, std_err, return_code):
        """
        Initializes a new ExecutionResult
        :param std_out: The std_err of the execution as list of strings
        :param std_err: The std_out of the execution as list of strings
        :param return_code: The return code of the execution
        """
        self.std_out = std_out
        self.std_err = std_err
        self.return_code = return_code

    def get_std_err(self):
        return '\n'.join(self.std_err)

    def get_std_out(self):
        return '\n'.join(self.std_out)

    def successful(self):
        return self.return_code == 0

    def to_dict(self):
        return {'stdErr': self.std_err,
                'stdOut': self.std_out,
                'returnCode': self.return_code}


def _exec(command, work_dir):
    try:
        sp = subprocess.Popen(command,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              cwd=work_dir,
                              universal_newlines=True,
                              encoding='utf-8')
    except TypeError:
        sp = subprocess.Popen(command,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              cwd=work_dir,
                              universal_newlines=True)
    return sp


def execute(command, work_dir=None):
    """
    Executes a given commandline command and returns a dictionary with keys: 'returnCode', 'stdOut', 'stdErr'
    :param command: The command to execute as list of strings.
    :param work_dir: The working directory for the executed command
    :return: An ExecutionResult
    """
    try:
        sp = _exec(command, work_dir)
    except FileNotFoundError as e:
        error_msg = ['Command "{}" not found.'.format(command[0])]
        error_msg.extend(_split_lines(str(e)))
        return ExecutionResult([], error_msg, 127)

    std_out, std_err = sp.communicate()
    return_code = sp.returncode

    return ExecutionResult(_split_lines(std_out), _split_lines(std_err), return_code)


def format_key_index(input_key, input_index=None):
    if input_index is None:
        return input_key
    return '{}:{}'.format(input_key, input_index)


class ConnectorManager:
    def __init__(self):
        self._input_runners = []
        self._output_runners = []
        self._cli_output_runners = []
        self._connector_cli_version_cache = {}

    def import_input_connectors(self, inputs):
        """
        Creates InputConnectorRunner for every key in inputs (or more Runners for File/Directory lists).
        :param inputs: The inputs to create Runner for
        """
        for input_key, input_value in inputs.items():
            if isinstance(input_value, dict):
                runner = create_input_connector_runner(input_key,
                                                       input_value,
                                                       None,
                                                       None,
                                                       False,
                                                       self._connector_cli_version_cache)
                self._input_runners.append(runner)
            elif isinstance(input_value, list):
                assert_class = None
                for index, sub_input in enumerate(input_value):
                    runner = create_input_connector_runner(input_key,
                                                           sub_input,
                                                           index,
                                                           assert_class,
                                                           True,
                                                           self._connector_cli_version_cache)
                    assert_class = runner.get_input_class()
                    self._input_runners.append(runner)

    def import_output_connectors(self, outputs, cli_outputs, output_mode):
        """
        Creates OutputConnectorRunner for every key in outputs.
        In Addition creates a CliOutputRunner for every key in cli_outputs.
        :param outputs: The outputs to create runner for.
        :param cli_outputs: The output cli description.
        :param output_mode: The output mode for this execution
        """
        if output_mode == OutputMode.Connectors:
            for output_key, output_value in outputs.items():
                cli_output_value = cli_outputs.get(output_key)
                if cli_output_value is None:
                    raise KeyError('Could not find output key "{}" in cli description, but was given in "outputs".'
                                   .format(output_key))

                runner = create_output_connector_runner(output_key,
                                                        output_value,
                                                        cli_output_value,
                                                        self._connector_cli_version_cache)
                self._output_runners.append(runner)

        for cli_output_key, cli_output_value in cli_outputs.items():
            runner = create_cli_output_runner(cli_output_key,
                                              cli_output_value)

            self._cli_output_runners.append(runner)

    def prepare_directories(self):
        """
        Tries to create directories needed to execute the connectors.
        :raise ConnectorError: If the needed directory could not be created, or if a received file does already exists
        """
        for runner in self._input_runners:
            runner.prepare_directory()

    def validate_connectors(self, validate_outputs):
        """
        Validates connectors.

        :param validate_outputs: If True, output runners are validated
        """
        for runner in self._input_runners:
            runner.validate_receive()

        if validate_outputs:
            for runner in self._output_runners:
                runner.validate_send()

    def receive_connectors(self):
        """
        Executes receive_file, receive_dir or receive_mount for every input with connector.
        Schedules the mounting runners first for performance reasons.
        """
        not_mounting_runners = []
        # receive mounting input runners
        for runner in self._input_runners:
            if runner.is_mounting():
                runner.receive()
            else:
                not_mounting_runners.append(runner)

        # receive not mounting input runners
        for runner in not_mounting_runners:
            runner.receive()

    def send_connectors(self, working_dir):
        """
        Tries to executes send for all output connectors.
        If a send runner fails, will try to send the other runners and fails afterwards.
        :param working_dir: The working dir where command is executed
        :raise ConnectorError: If one ore more OutputRunners fail to send.
        """
        errors = []
        for runner in self._output_runners:
            try:
                runner.try_send(working_dir)
            except ConnectorError as e:
                errors.append(e)

        errors_len = len(errors)
        if errors_len == 1:
            raise errors[0]
        elif errors_len > 1:
            error_strings = [_format_exception(e) for e in errors]
            raise ConnectorError('{} output connectors failed:\n{}'.format(errors_len, '\n'.join(error_strings)))

    def move_output_files(self, working_dir, output_dir):
        """
        Moves the output files to output directory.

        :param working_dir: The directory from where to search the output files/directories
        :param output_dir: The directory where the output files/directories should be moved to
        """
        for runner in self._cli_output_runners:
            runner.try_move(working_dir, output_dir)

    def check_outputs(self, working_dir):
        """
        Checks if all output files/directories are present relative to the given working directory
        :param working_dir: The working directory from where to expect the output files/directories
        :raise ConnectorError: If an output file/directory could not be found
        """
        for runner in self._cli_output_runners:
            runner.check_output(working_dir)

    def umount_connectors(self):
        """
        Tries to execute umount for every connector.
        :return: The errors that occurred during execution
        """
        errors = []
        for runner in self._input_runners:
            try:
                runner.try_umount()
            except ConnectorError as e:
                errors.append(e)

        return errors


def exception_format():
    exc_text = format_exc()
    return [_lstrip_quarter(l.replace("'", '').rstrip()) for l in exc_text.split('\n') if l]


def _lstrip_quarter(s):
    len_s = len(s)
    s = s.lstrip()
    len_s_strip = len(s)
    quarter = (len_s - len_s_strip) // 4
    return ' ' * quarter + s


def _format_exception(exception):
    return '[{}]\n{}\n'.format(type(exception).__name__, str(exception))


def print_exception(exception):
    """
    Prints the exception message and the name of the exception class to stderr.

    :param exception: The exception to print
    """
    print(_format_exception(exception), file=sys.stderr)


def _split_lines(lines):
    return [l for l in lines.split(os.linesep) if l]


class ConnectorError(Exception):
    pass


class ExecutionError(Exception):
    pass


if __name__ == '__main__':
    main()
