# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014-2015 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Utilities for IPC with existing instances."""

import os
import time
import json
import getpass
import binascii
import hashlib

from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject
from PyQt5.QtNetwork import QLocalSocket, QLocalServer, QAbstractSocket

from qutebrowser.utils import log, usertypes, error, objreg


CONNECT_TIMEOUT = 100
WRITE_TIMEOUT = 1000
READ_TIMEOUT = 5000


def _get_socketname(basedir, user=None):
    """Get a socketname to use."""
    if user is None:
        user = getpass.getuser()
    parts = ['qutebrowser', user]
    if basedir is not None:
        md5 = hashlib.md5(basedir.encode('utf-8'))
        parts.append(md5.hexdigest())
    return '-'.join(parts)


class Error(Exception):

    """Exception raised when there was a problem with IPC."""


class ListenError(Error):

    """Exception raised when there was a problem with listening to IPC.

    Args:
        code: The error code.
        message: The error message.
    """

    def __init__(self, server):
        """Constructor.

        Args:
            server: The QLocalServer which has the error set.
        """
        super().__init__()
        self.code = server.serverError()
        self.message = server.errorString()

    def __str__(self):
        return "Error while listening to IPC server: {} (error {})".format(
            self.message, self.code)


class AddressInUseError(ListenError):

    """Emitted when the server address is already in use."""


class IPCServer(QObject):

    """IPC server to which clients connect to.

    Attributes:
        ignored: Whether requests are ignored (in exception hook).
        _timer: A timer to handle timeouts.
        _server: A QLocalServer to accept new connections.
        _socket: The QLocalSocket we're currently connected to.
        _socketname: The socketname to use.

    Signals:
        got_args: Emitted when there was an IPC connection and arguments were
                  passed.
        got_invalid_data: Emitted when there was invalid incoming data.
    """

    got_args = pyqtSignal(list, str)
    got_invalid_data = pyqtSignal()

    def __init__(self, socketname, parent=None):
        """Start the IPC server and listen to commands.

        Args:
            socketname: The socketname to use.
            parent: The parent to be used.
        """
        super().__init__(parent)
        self.ignored = False
        self._socketname = socketname
        self._timer = usertypes.Timer(self, 'ipc-timeout')
        self._timer.setInterval(READ_TIMEOUT)
        self._timer.timeout.connect(self.on_timeout)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self.handle_connection)
        self._socket = None

    def _remove_server(self):
        """Remove an existing server."""
        ok = QLocalServer.removeServer(self._socketname)
        if not ok:
            raise Error("Error while removing server {}!".format(
                self._socketname))

    def listen(self):
        """Start listening on self._servername."""
        log.ipc.debug("Listening as {}".format(self._socketname))
        self._remove_server()
        ok = self._server.listen(self._socketname)
        if not ok:
            if self._server.serverError() == QAbstractSocket.AddressInUseError:
                raise AddressInUseError(self._server)
            else:
                raise ListenError(self._server)

    @pyqtSlot(int)
    def on_error(self, err):
        """Convenience method which calls _socket_error on an error."""
        if self._socket is None:
            log.ipc.warn("In on_error with None socket!")
            # Sometimes this gets called from stale sockets.
            return
        self._timer.stop()
        log.ipc.debug("Socket error {}: {}".format(
            self._socket.error(), self._socket.errorString()))
        if err != QLocalSocket.PeerClosedError:
            _socket_error("handling IPC connection", self._socket)

    @pyqtSlot()
    def handle_connection(self):
        """Handle a new connection to the server."""
        if self.ignored:
            return
        if self._socket is not None:
            log.ipc.debug("Got new connection but ignoring it because we're "
                          "still handling another one.")
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            log.ipc.debug("No new connection to handle.")
            return
        log.ipc.debug("Client connected.")
        self._timer.start()
        self._socket = socket
        socket.readyRead.connect(self.on_ready_read)
        if socket.canReadLine():
            log.ipc.debug("We can read a line immediately.")
            self.on_ready_read()
        socket.error.connect(self.on_error)
        if socket.error() not in (QLocalSocket.UnknownSocketError,
                                  QLocalSocket.PeerClosedError):
            log.ipc.debug("We got an error immediately.")
            self.on_error(socket.error())
        socket.disconnected.connect(self.on_disconnected)
        if socket.state() == QLocalSocket.UnconnectedState:
            log.ipc.debug("Socket was disconnected immediately.")
            self.on_disconnected()

    @pyqtSlot()
    def on_disconnected(self):
        """Clean up socket when the client disconnected."""
        log.ipc.debug("Client disconnected.")
        self._timer.stop()
        if self._socket is None:
            log.ipc.warn("In on_disconnected with None socket!")
        else:
            self._socket.deleteLater()
            self._socket = None
        # Maybe another connection is waiting.
        self.handle_connection()

    @pyqtSlot()
    def on_ready_read(self):
        """Read json data from the client."""
        if self._socket is None:
            # This happens when doing a connection while another one is already
            # active for some reason.
            log.ipc.warn("In on_ready_read with None socket!")
            return
        self._timer.start()
        while self._socket is not None and self._socket.canReadLine():
            data = bytes(self._socket.readLine())
            log.ipc.debug("Read from socket: {}".format(data))
            try:
                decoded = data.decode('utf-8')
            except UnicodeDecodeError:
                log.ipc.error("Ignoring invalid IPC data.")
                log.ipc.debug("invalid data: {}".format(
                    binascii.hexlify(data)))
                self.got_invalid_data.emit()
                self._socket.error.connect(self.on_error)
                self._socket.disconnectFromServer()
                return
            log.ipc.debug("Processing: {}".format(decoded))
            try:
                json_data = json.loads(decoded)
            except ValueError:
                log.ipc.error("Ignoring invalid IPC data.")
                log.ipc.debug("invalid json: {}".format(decoded.strip()))
                self.got_invalid_data.emit()
                self._socket.error.connect(self.on_error)
                self._socket.disconnectFromServer()
                return
            try:
                args = json_data['args']
            except KeyError:
                log.ipc.error("Ignoring invalid IPC data.")
                log.ipc.debug("no args: {}".format(decoded.strip()))
                self.got_invalid_data.emit()
                self._socket.error.connect(self.on_error)
                self._socket.disconnectFromServer()
                return
            cwd = json_data.get('cwd', None)
            self.got_args.emit(args, cwd)

    @pyqtSlot()
    def on_timeout(self):
        """Cancel the current connection if it was idle for too long."""
        log.ipc.error("IPC connection timed out.")
        self._socket.close()

    def shutdown(self):
        """Shut down the IPC server cleanly."""
        if self._socket is not None:
            self._socket.deleteLater()
            self._socket = None
        self._timer.stop()
        self._server.close()
        self._server.deleteLater()
        self._remove_server()


def _socket_error(action, socket):
    """Raise an Error based on an action and a QLocalSocket.

    Args:
        action: A string like "writing to running instance".
        socket: A QLocalSocket.
    """
    raise Error("Error while {}: {} (error {})".format(
        action, socket.errorString(), socket.error()))


def send_to_running_instance(socketname, command, *, socket=None):
    """Try to send a commandline to a running instance.

    Blocks for CONNECT_TIMEOUT ms.

    Args:
        socketname: The name which should be used for the socket.
        command: The command to send to the running instance.
        socket: The socket to read data from, or None.

    Return:
        True if connecting was successful, False if no connection was made.
    """
    if socket is None:
        socket = QLocalSocket()
    log.ipc.debug("Connecting to {}".format(socketname))
    socket.connectToServer(socketname)
    connected = socket.waitForConnected(100)
    if connected:
        log.ipc.info("Opening in existing instance")
        json_data = {'args': command}
        try:
            cwd = os.getcwd()
        except OSError:
            pass
        else:
            json_data['cwd'] = cwd
        line = json.dumps(json_data) + '\n'
        data = line.encode('utf-8')
        log.ipc.debug("Writing: {}".format(data))
        socket.writeData(data)
        socket.waitForBytesWritten(WRITE_TIMEOUT)
        if socket.error() != QLocalSocket.UnknownSocketError:
            _socket_error("writing to running instance", socket)
        else:
            socket.disconnectFromServer()
            if socket.state() != QLocalSocket.UnconnectedState:
                socket.waitForDisconnected(100)
            return True
    else:
        if socket.error() not in (QLocalSocket.ConnectionRefusedError,
                                  QLocalSocket.ServerNotFoundError):
            _socket_error("connecting to running instance", socket)
        else:
            log.ipc.debug("No existing instance present (error {})".format(
                socket.error()))
            return False


def display_error(exc, args):
    """Display a message box with an IPC error."""
    error.handle_fatal_exc(
        exc, args, "Error while connecting to running instance!",
        post_text="Maybe another instance is running but frozen?")


def send_or_listen(args):
    """Send the args to a running instance or start a new IPCServer.

    Args:
        args: The argparse namespace.

    Return:
        The IPCServer instance if no running instance was detected.
        None if an instance was running and received our request.
    """
    socketname = _get_socketname(args.basedir)
    try:
        sent = send_to_running_instance(socketname, args.command)
        if sent:
            return None
        log.init.debug("Starting IPC server...")
        server = IPCServer(_get_socketname(args.basedir))
        server.listen()
        objreg.register('ipc-server', server)
        return server
    except AddressInUseError as e:
        # This could be a race condition...
        log.init.debug("Got AddressInUseError, trying again.")
        time.sleep(0.5)
        sent = send_to_running_instance(socketname, args.command)
        if sent:
            return None
        else:
            display_error(e, args)
            raise
    except Error as e:
        display_error(e, args)
        raise
