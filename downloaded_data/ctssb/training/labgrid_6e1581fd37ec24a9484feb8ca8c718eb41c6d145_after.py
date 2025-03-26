# pylint: disable=no-member
import tempfile
import logging
import subprocess
import os
import socket
from functools import wraps

import attr
from ..driver.exception import ExecutionError

from .helper import get_free_port

__all__ = ['sshmanager', 'SSHConnection', 'ForwardError']


@attr.s
class SSHConnectionManager:
    """The SSHConnectionManager manages multiple SSH connections. This class
    should not be directly instanciated, use the exported sshmanager from this
    module instead.
    """
    _connections = attr.ib(
        default=attr.Factory(dict),
        init=False,
        validator=attr.validators.optional(attr.validators.instance_of(dict))
    )

    def __attrs_post_init__(self):
        self.logger = logging.getLogger("{}".format(self))

    def get(self, host: str):
        """Retrieve or create a new connection to a given host

        Arguments:
            host (str): host to retrieve the connection for

        Returns:
            :obj:`SSHConnection`: the SSHConnection for the host"""
        host = socket.getfqdn(host)
        instance = self._connections.get(host)
        if instance is None:
            # pylint: disable=unsupported-assignment-operation
            self.logger.debug("Creating SSHConnection for {}".format(host))
            instance = SSHConnection(host)
            instance.connect()
            self._connections[host] = instance
        return instance

    def add_connection(self, connection):
        """Add an existing SSHConnection to the manager.
        This is useful for manually created connections which should also be
        available via the manager.

        Arguments:
            connection (:obj:`SSHConnection`): SSHconnection to add to the manager
        """
        # pylint: disable=unsupported-assignment-operation
        assert isinstance(connection, SSHConnection)
        if connection.host not in self._connections:
            self._connections[connection.host] = connection

    def remove_connection(self, connection):
        # pylint: disable=unsupported-assignment-operation
        assert isinstance(connection, SSHConnection)
        if connection.isconnected():
            raise ExecutionError("Can't remove connected connection")
        del self._connections[connection.host]

    def remove_by_name(self, name):
        # pylint: disable=unsupported-assignment-operation
        del self._connections[name]

    def open(self, host):
        return self.get(host)

    def close(self, host):
        con = self.get(host)
        con.disconnect()
        self.remove_connection(con)

    def request_forward(self, host, dest, port):
        con = self.get(host)
        return con.add_port_forward(dest, port)

    def remove_forward(self, host, dest, port):
        con = self.get(host)
        con.remove_port_forward(dest, port)

    def put_file(self, host, local_file, remote_file):
        con = self.get(host)
        con.put_file(local_file, remote_file)

    def get_file(self, host, remote_file, local_file):
        con = self.get(host)
        con.get_file(remote_file, local_file)

    def close_all(self):
        """Close all open connections and remove them from the manager """
        for name, connection in self._connections.items():
            if connection.isconnected():
                connection.disconnect()
        names = self._connections.copy().keys()
        for name in names:
            self.remove_by_name(name)


@attr.s
class SSHConnection:
    """SSHConnections are individual connections to hosts managed by a control
    socket. In addition to command execution this class also provides an
    interface to manage port forwardings. These are used in the remote
    infrastructure to tunnel multiple connections over one SSH link.

    A public identity infrastructure is assumed, no extra username or passwords
    are supported."""
    host = attr.ib(validator=attr.validators.instance_of(str))
    _connected = attr.ib(
        default=False, init=False, validator=attr.validators.instance_of(bool)
    )
    _tmpdir = attr.ib(
        default=attr.Factory(lambda: tempfile.mkdtemp(prefix="labgrid-connection-")),
        init=False,
        validator=attr.validators.instance_of(str)
    )
    _forwards = attr.ib(init=False, default=attr.Factory(dict))

    def __attrs_post_init__(self):
        self._logger = logging.getLogger("{}".format(self))
        self._socket = None
        self._master = None
        self._keepalive = None

    def _get_ssh_base_args(self):
        return ["-x", "-o", "LogLevel=ERROR", "-o", "PasswordAuthentication=no"]

    def _get_ssh_control_args(self):
        if self._socket:
            return [
                "-o", "ControlMaster=no",
                "-o", "ControlPath={}".format(self._socket),
            ]
        return []

    def _get_ssh_args(self):
        args = self._get_ssh_base_args()
        args += self._get_ssh_control_args()
        return args

    def _open_connection(self):
        """Internal function which appends the control socket and checks if the
        connection is already open"""
        if self._check_external_master():
            self._logger.info("Using existing SSH connection to {}".format(self.host))
        else:
            self._start_own_master()
            self._logger.info("Created new SSH connection to {}".format(self.host))
        self._start_keepalive()
        self._connected = True

    def _run_socket_command(self, command, forward=None):
        "Internal function to send a command to the control socket"
        complete_cmd = ["ssh"] + self._get_ssh_args()
        complete_cmd += ["-O", command]
        if forward:
            for item in forward:
                complete_cmd.append(item)
        complete_cmd.append(self.host)
        res = subprocess.check_call(
            complete_cmd,
            stdin=subprocess.DEVNULL,
            timeout=2,
        )

        return res

    def _check_connected(func):
        """Check if an SSHConnection is connected as a decorator"""

        @wraps(func)
        def wrapper(self, *_args, **_kwargs):
            if not self.isconnected():
                raise ExecutionError(
                    "{} can not be called ({} is not connected)".format(
                        func.__qualname__, self
                    )
                )
            return func(self, *_args, **_kwargs)

        return wrapper

    @_check_connected
    def run_command(self, command):
        """Run a command over the SSHConnection

        Args:
            command (string): The command to run

        Returns:
            int: exitcode of the command
        """
        complete_cmd = ["ssh"] + self._get_ssh_args()
        complete_cmd += [self.host, command]
        res = subprocess.check_call(
            complete_cmd,
            stdin=subprocess.DEVNULL,
        )

        return res

    @_check_connected
    def get_file(self, remote_file, local_file):
        """Get a file from the remote host"""
        complete_cmd = ["scp"] + self._get_ssh_control_args()
        complete_cmd += [
            "{}:{}".format(self.host, remote_file),
            "{}".format(local_file)
        ]
        subprocess.check_call(
            complete_cmd,
            stdin=subprocess.DEVNULL,
        )

    @_check_connected
    def put_file(self, local_file, remote_path):
        """Put a file onto the remote host"""
        complete_cmd = ["rsync", "--copy-links", "-e",
                        " ".join(['ssh'] + self._get_ssh_args())]
        complete_cmd += [
            "{}".format(local_file),
            "{}:{}".format(self.host, remote_path)
        ]
        subprocess.check_call(
            complete_cmd,
            stdin=subprocess.DEVNULL,
        )

    @_check_connected
    def add_port_forward(self, remote_host, remote_port):
        """forward command"""
        local_port = get_free_port()
        destination = "{}:{}".format(remote_host, remote_port)

        # pylint: disable=not-an-iterable
        if destination in self._forwards:
            return self._forwards[destination]
        self._run_socket_command(
            "forward", [
                "-L"
                "{local}:{destination}".
                format(local=local_port, destination=destination)
            ]
        )
        self._forwards[destination] = local_port
        return local_port

    @_check_connected
    def remove_port_forward(self, remote_host, remote_port):
        """cancel command"""
        destination = "{}:{}".format(remote_host, remote_port)
        local_port = self._forwards.pop(destination, None)

        # pylint: disable=not-an-iterable
        if local_port is None:
            raise ForwardError("Forward does not exist")

        self._run_socket_command(
            "cancel", [
                "-L"
                "{local}:localhost:{remote}".
                format(local=local_port, remote=remote_port)
            ]
        )

    def connect(self):
        if not self._connected:
            self._open_connection()

    @_check_connected
    def disconnect(self):
        self._disconnect()

    def isconnected(self):
        return self._connected and self._check_keepalive()

    def _check_external_master(self):
        args = ["ssh", "-O", "check", "{}".format(self.host)]
        # We don't want to confuse the use with SSHs output here, so we need to
        # capture and parse it.
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        stdout, _ = proc.communicate(timeout=60)
        check = proc.wait()
        if check == 0:
            self._logger.debug("Found existing control socket")
            return True
        elif b"No such file or directory" in stdout:
            self._logger.debug("No existing control socket found")
            return False

        self._logger.debug("Unexpected ssh check output '{}'".format(stdout))
        return False

    def _start_own_master(self):
        """Starts a controlmaster connection in a temporary directory."""
        control = os.path.join(self._tmpdir, 'control-{}'.format(self.host))

        args = ["ssh"] + self._get_ssh_base_args()
        args += [
            "-n", "-MN",
            "-o", "ConnectTimeout=30",
            "-o", "ControlPersist=300",
            "-o", "ControlMaster=yes",
            "-o", "ControlPath={}".format(control),
            # We don't want to ask the user to confirm host keys here.
            "-o", "StrictHostKeyChecking=yes",
            self.host,
        ]

        assert self._master is None
        self._master = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            if self._master.wait(timeout=30) is not 0:
                raise ExecutionError(
                    "failed to connect to {} with args {}, returncode={} {},{} ".format(
                        self.host, args, self._master.wait(),
                        self._master.stdout.readlines(),
                        self._master.stderr.readlines()
                    )
                )
        except subprocess.TimeoutExpired:
            raise ExecutionError(
                "failed to connect (timeout) to {} with args {} {},{}".format(
                    self.host, args, self._master.stdout.readlines(),
                    self._master.stderr.readlines()
                )
            )

        if not os.path.exists(control):
            raise ExecutionError("no control socket to {}".format(self.host))

        self._socket = control

        self._logger.debug('Connected to %s', self.host)

    def _stop_own_master(self):
        assert self._socket is not None
        assert self._master is not None

        try:
            self._run_socket_command("cancel")
            self._run_socket_command("exit")
            # if the master doesn't terminate in less than 60 seconds,
            # something is very wrong
            self._master.wait(timeout=60)
        finally:
            self._socket = None
            self._master = None

    def _start_keepalive(self):
        """Starts a keepalive connection via the own or external master."""
        args = ["ssh"] + self._get_ssh_args() + [self.host, "cat"]

        assert self._keepalive is None
        self._keepalive = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._logger.debug('Started keepalive for %s', self.host)

    def _check_keepalive(self):
        return self._keepalive.poll() is None

    def _stop_keepalive(self):
        assert self._keepalive is not None

        self._logger.debug('Stopping keepalive for %s', self.host)

        try:
            self._keepalive.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            self._keepalive.kill()

        try:
            self._keepalive.wait(timeout=60)
        finally:
            self._keepalive = None

    def _disconnect(self):
        assert self._connected
        try:
            if self._socket:
                self._logger.info("Closing SSH connection to {}".format(self.host))
                self._stop_keepalive()
                self._stop_own_master()
        finally:
            self._connected = False

sshmanager = SSHConnectionManager()

@attr.s
class ForwardError(Exception):
    msg = attr.ib(validator=attr.validators.instance_of(str))
