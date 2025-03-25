# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
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

"""Download manager."""

import io
import os
import os.path
import shutil
import functools
import collections

from PyQt5.QtCore import (pyqtSlot, pyqtSignal, QObject, QTimer,
                          QStandardPaths, Qt, QVariant, QAbstractListModel,
                          QModelIndex)
from PyQt5.QtNetwork import QNetworkRequest, QNetworkReply
# We need this import so PyQt can use it inside pyqtSlot
from PyQt5.QtWebKitWidgets import QWebPage  # pylint: disable=unused-import

from qutebrowser.config import config
from qutebrowser.commands import cmdexc, cmdutils
from qutebrowser.utils import (message, http, usertypes, log, utils, urlutils,
                               objreg, standarddir, qtutils)
from qutebrowser.network import networkmanager


ModelRole = usertypes.enum('ModelRole', ['item'], start=Qt.UserRole,
                           is_int=True)


class DownloadItemStats(QObject):

    """Statistics (bytes done, total bytes, time, etc.) about a download.

    Class attributes:
        SPEED_REFRESH_INTERVAL: How often to refresh the speed, in msec.
        SPEED_AVG_WINDOW: How many seconds of speed data to average to
                          estimate the remaining time.

    Attributes:
        done: How many bytes there are already downloaded.
        total: The total count of bytes.  None if the total is unknown.
        speed: The current download speed, in bytes per second.
        _speed_avg: A rolling average of speeds.
        _last_done: The count of bytes which where downloaded when calculating
                    the speed the last time.
    """

    SPEED_REFRESH_INTERVAL = 500
    SPEED_AVG_WINDOW = 30

    updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.total = None
        self.done = 0
        self.speed = 0
        self._last_done = 0
        samples = int(self.SPEED_AVG_WINDOW *
                      (1000 / self.SPEED_REFRESH_INTERVAL))
        self._speed_avg = collections.deque(maxlen=samples)
        self.timer = usertypes.Timer(self, 'speed_refresh')
        self.timer.timeout.connect(self._update_speed)
        self.timer.setInterval(self.SPEED_REFRESH_INTERVAL)
        self.timer.start()

    @pyqtSlot()
    def _update_speed(self):
        """Recalculate the current download speed."""
        delta = self.done - self._last_done
        self.speed = delta * 1000 / self.SPEED_REFRESH_INTERVAL
        self._speed_avg.append(self.speed)
        self._last_done = self.done
        self.updated.emit()

    def finish(self):
        """Set the download stats as finished."""
        self.timer.stop()
        self.done = self.total

    def percentage(self):
        """The current download percentage, or None if unknown."""
        if self.total == 0 or self.total is None:
            return None
        else:
            return 100 * self.done / self.total

    def remaining_time(self):
        """The remaining download time in seconds, or None."""
        if self.total is None or not self._speed_avg:
            # No average yet or we don't know the total size.
            return None
        remaining_bytes = self.total - self.done
        avg = sum(self._speed_avg) / len(self._speed_avg)
        if avg == 0:
            # Download stalled
            return None
        else:
            return remaining_bytes / avg

    @pyqtSlot(int, int)
    def on_download_progress(self, bytes_done, bytes_total):
        """Upload local variables when the download progress changed.

        Args:
            bytes_done: How many bytes are downloaded.
            bytes_total: How many bytes there are to download in total.
        """
        if bytes_total == -1:
            bytes_total = None
        self.done = bytes_done
        self.total = bytes_total
        self.updated.emit()


class DownloadItem(QObject):

    """A single download currently running.

    There are multiple ways the data can flow from the QNetworkReply to the
    disk.

    If the filename/file object is known immediately when starting the
    download, QNetworkReply's readyRead writes to the target file directly.

    If not, readyRead is ignored and with self._read_timer we periodically read
    into the self._buffer BytesIO slowly, so some broken servers don't close
    our connection.

    As soon as we know the file object, we copy self._buffer over and the next
    readyRead will write to the real file object.

    Class attributes:
        MAX_REDIRECTS: The maximum redirection count.

    Attributes:
        stats: A DownloadItemStats object.
        successful: Whether the download has completed sucessfully.
        error_msg: The current error message, or None
        autoclose: Whether to close the associated file if the download is
                   done.
        fileobj: The file object to download the file to.
        reply: The QNetworkReply associated with this download.
        _filename: The filename of the download.
        _redirects: How many time we were redirected already.
        _buffer: A BytesIO object to buffer incoming data until we know the
                 target file.
        _read_timer: A QTimer which reads the QNetworkReply into self._buffer
                     periodically.

    Signals:
        data_changed: The downloads metadata changed.
        finished: The download was finished.
        cancelled: The download was cancelled.
        error: An error with the download occured.
               arg: The error message as string.
        redirected: Signal emitted when a download was redirected.
            arg 0: The new QNetworkRequest.
            arg 1: The old QNetworkReply.
    """

    MAX_REDIRECTS = 10
    data_changed = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    redirected = pyqtSignal(QNetworkRequest, QNetworkReply)

    def __init__(self, reply, parent=None):
        """Constructor.

        Args:
            reply: The QNetworkReply to download.
        """
        super().__init__(parent)
        self.stats = DownloadItemStats(self)
        self.stats.updated.connect(self.data_changed)
        self.autoclose = True
        self.reply = None
        self._buffer = io.BytesIO()
        self._read_timer = QTimer()
        self._read_timer.setInterval(500)
        self._read_timer.timeout.connect(self.on_read_timer_timeout)
        self._redirects = 0
        self.error_msg = None
        self.basename = '???'
        self.successful = False
        self.fileobj = None
        self._filename = None
        self.init_reply(reply)

    def __repr__(self):
        return utils.get_repr(self, basename=self.basename)

    def __str__(self):
        """Get the download as a string.

        Example: foo.pdf [699.2kB/s|0.34|16%|4.253/25.124]
        """
        speed = utils.format_size(self.stats.speed, suffix='B/s')
        down = utils.format_size(self.stats.done, suffix='B')
        perc = self.stats.percentage()
        remaining = self.stats.remaining_time()
        if self.error_msg is None:
            errmsg = ""
        else:
            errmsg = " - {}".format(self.error_msg)
        if all(e is None for e in (perc, remaining, self.stats.total)):
            return ('{name} [{speed:>10}|{down}]{errmsg}'.format(
                name=self.basename, speed=speed, down=down, errmsg=errmsg))
        if perc is None:
            perc = '??'
        else:
            perc = round(perc)
        if remaining is None:
            remaining = '?'
        else:
            remaining = utils.format_seconds(remaining)
        total = utils.format_size(self.stats.total, suffix='B')
        return ('{name} [{speed:>10}|{remaining:>5}|{perc:>2}%|'
                '{down}/{total}]{errmsg}'.format(
                    name=self.basename, speed=speed, remaining=remaining,
                    perc=perc, down=down, total=total, errmsg=errmsg))

    def _die(self, msg):
        """Abort the download and emit an error."""
        assert not self.successful
        self._read_timer.stop()
        self.reply.downloadProgress.disconnect()
        self.reply.finished.disconnect()
        self.reply.error.disconnect()
        self.reply.readyRead.disconnect()
        self.error_msg = msg
        self.stats.finish()
        self.error.emit(msg)
        self.reply.abort()
        self.reply.deleteLater()
        self.reply = None
        if self.fileobj is not None:
            try:
                self.fileobj.close()
            except OSError as e:
                self.error.emit(e.strerror)
        self.data_changed.emit()

    def init_reply(self, reply):
        """Set a new reply and connect its signals.

        Args:
            reply: The QNetworkReply to handle.
        """
        self.reply = reply
        reply.setReadBufferSize(16 * 1024 * 1024)  # 16 MB
        reply.downloadProgress.connect(self.stats.on_download_progress)
        reply.finished.connect(self.on_reply_finished)
        reply.error.connect(self.on_reply_error)
        reply.readyRead.connect(self.on_ready_read)
        if not self.fileobj:
            self._read_timer.start()
        # We could have got signals before we connected slots to them.
        # Here no signals are connected to the DownloadItem yet, so we use a
        # singleShot QTimer to emit them after they are connected.
        if reply.error() != QNetworkReply.NoError:
            QTimer.singleShot(0, lambda: self.error.emit(reply.errorString()))

    def bg_color(self):
        """Background color to be shown."""
        start = config.get('colors', 'downloads.bg.start')
        stop = config.get('colors', 'downloads.bg.stop')
        system = config.get('colors', 'downloads.bg.system')
        error = config.get('colors', 'downloads.bg.error')
        if self.error_msg is not None:
            assert not self.successful
            return error
        elif self.stats.percentage() is None:
            return start
        else:
            return utils.interpolate_color(
                start, stop, self.stats.percentage(), system)

    def cancel(self):
        """Cancel the download."""
        log.downloads.debug("cancelled")
        self._read_timer.stop()
        self.cancelled.emit()
        if self.reply is not None:
            self.reply.finished.disconnect(self.on_reply_finished)
            self.reply.abort()
            self.reply.deleteLater()
            self.reply = None
        if self.fileobj is not None:
            self.fileobj.close()
        if self._filename is not None and os.path.exists(self._filename):
            os.remove(self._filename)
        self.finished.emit()

    def set_filename(self, filename):
        """Set the filename to save the download to.

        Args:
            filename: The full filename to save the download to.
                      None: special value to stop the download.
        """
        if self.fileobj is not None:
            raise ValueError("fileobj was already set! filename: {}, "
                             "existing: {}, fileobj {}".format(
                                 filename, self._filename, self.fileobj))
        filename = os.path.expanduser(filename)
        if os.path.isabs(filename) and os.path.isdir(filename):
            # We got an absolute directory from the user, so we save it under
            # the default filename in that directory.
            self._filename = os.path.join(filename, self.basename)
        elif os.path.isabs(filename):
            # We got an absolute filename from the user, so we save it under
            # that filename.
            self._filename = filename
            self.basename = os.path.basename(self._filename)
        else:
            # We only got a filename (without directory) from the user, so we
            # save it under that filename in the default directory.
            download_dir = config.get('storage', 'download-directory')
            if download_dir is None:
                download_dir = standarddir.get(
                    QStandardPaths.DownloadLocation)
            self._filename = os.path.join(download_dir, filename)
            self.basename = filename
        log.downloads.debug("Setting filename to {}".format(filename))
        try:
            fileobj = open(self._filename, 'wb')
        except OSError as e:
            self._die(e.strerror)
        else:
            self.set_fileobj(fileobj)

    def set_fileobj(self, fileobj):
        """"Set the file object to write the download to.

        Args:
            fileobj: A file-like object.
        """
        if self.fileobj is not None:
            raise ValueError("fileobj was already set! Old: {}, new: "
                             "{}".format(self.fileobj, fileobj))
        self.fileobj = fileobj
        try:
            self._read_timer.stop()
            log.downloads.debug("buffer: {} bytes".format(self._buffer.tell()))
            self._buffer.seek(0)
            shutil.copyfileobj(self._buffer, fileobj)
            self._buffer.close()
            if self.reply.isFinished():
                # Downloading to the buffer in RAM has already finished so we
                # write out the data and clean up now.
                self.on_reply_finished()
            else:
                # Since the buffer already might be full, on_ready_read might
                # not be called at all anymore, so we force it here to flush
                # the buffer and continue receiving new data.
                self.on_ready_read()
        except OSError as e:
            self._die(e.strerror)

    def finish_download(self):
        """Write buffered data to disk and finish the QNetworkReply."""
        log.downloads.debug("Finishing download...")
        self._read_timer.stop()
        if self.reply.isOpen():
            self.fileobj.write(self.reply.readAll())
        if self.autoclose:
            self.fileobj.close()
        self.successful = self.reply.error() == QNetworkReply.NoError
        self.reply.close()
        self.reply.deleteLater()
        self.reply = None
        self.finished.emit()
        log.downloads.debug("Download finished")

    @pyqtSlot()
    def on_reply_finished(self):
        """Clean up when the download was finished.

        Note when this gets called, only the QNetworkReply has finished. This
        doesn't mean the download (i.e. writing data to the disk) is finished
        as well. Therefore, we can't close() the QNetworkReply in here yet.
        """
        if self.reply is None:
            return
        self.stats.finish()
        is_redirected = self._handle_redirect()
        if is_redirected:
            return
        log.downloads.debug("Reply finished, fileobj {}".format(self.fileobj))
        if self.fileobj is not None:
            # We can do a "delayed" write immediately to empty the buffer and
            # clean up.
            self.finish_download()

    @pyqtSlot()
    def on_ready_read(self):
        """Read available data and save file when ready to read."""
        if self.fileobj is None or self.reply is None:
            # No filename has been set yet (so we don't empty the buffer) or we
            # got a readyRead after the reply was finished (which happens on
            # qute:log for example).
            return
        if not self.reply.isOpen():
            raise IOError("Reply is closed!")
        try:
            self.fileobj.write(self.reply.readAll())
        except OSError as e:
            self._die(e.strerror)

    @pyqtSlot(int)
    def on_reply_error(self, code):
        """Handle QNetworkReply errors."""
        if code == QNetworkReply.OperationCanceledError:
            return
        else:
            self._die(self.reply.errorString())

    @pyqtSlot()
    def on_read_timer_timeout(self):
        """Read some bytes from the QNetworkReply periodically."""
        if not self.reply.isOpen():
            raise IOError("Reply is closed!")
        data = self.reply.read(1024)
        self._buffer.write(data)

    def _handle_redirect(self):
        """Handle a HTTP redirect.

        Return:
            True if the download was redirected, False otherwise.
        """
        redirect = self.reply.attribute(
            QNetworkRequest.RedirectionTargetAttribute)
        if redirect is None or redirect.isEmpty():
            return False
        new_url = self.reply.url().resolved(redirect)
        request = self.reply.request()
        if new_url == request.url():
            return False

        if self._redirects > self.MAX_REDIRECTS:
            self._die("Maximum redirection count reached!")
            return True  # so on_reply_finished aborts

        log.downloads.debug("{}: Handling redirect".format(self))
        self._redirects += 1
        request.setUrl(new_url)
        reply = self.reply
        reply.finished.disconnect(self.on_reply_finished)
        self._read_timer.stop()
        self.reply = None
        if self.fileobj is not None:
            self.fileobj.seek(0)
        self.redirected.emit(request, reply)  # this will change self.reply!
        reply.deleteLater()  # the old one
        return True


class DownloadManager(QAbstractListModel):

    """Manager and model for currently running downloads.

    Attributes:
        downloads: A list of active DownloadItems.
        questions: A list of Question objects to not GC them.
        _networkmanager: A NetworkManager for generic downloads.
        _win_id: The window ID the DownloadManager runs in.
    """

    def __init__(self, win_id, parent=None):
        super().__init__(parent)
        self._win_id = win_id
        self.downloads = []
        self.questions = []
        self._networkmanager = networkmanager.NetworkManager(win_id, self)

    def __repr__(self):
        return utils.get_repr(self, downloads=len(self.downloads))

    def _prepare_question(self):
        """Prepare a Question object to be asked."""
        q = usertypes.Question(self)
        q.text = "Save file to:"
        q.mode = usertypes.PromptMode.text
        q.completed.connect(q.deleteLater)
        q.destroyed.connect(functools.partial(self.questions.remove, q))
        self.questions.append(q)
        return q

    @cmdutils.register(instance='download-manager', scope='window')
    def download(self, url, dest=None):
        """Download a given URL, given as string.

        Args:
            url: The URL to download
            dest: The file path to write the download to, or None to ask.
        """
        url = urlutils.qurl_from_user_input(url)
        urlutils.raise_cmdexc_if_invalid(url)
        self.get(url, filename=dest)

    @pyqtSlot('QUrl', 'QWebPage')
    def get(self, url, page=None, fileobj=None, filename=None):
        """Start a download with a link URL.

        Args:
            url: The URL to get, as QUrl
            page: The QWebPage to get the download from.
            fileobj: The file object to write the answer to.
            filename: A path to write the data to.

        Return:
            If the download could start immediately, (fileobj/filename given),
            the created DownloadItem.

            If not, None.
        """
        if fileobj is not None and filename is not None:
            raise TypeError("Only one of fileobj/filename may be given!")
        if not url.isValid():
            urlutils.invalid_url_error(self._win_id, url, "start download")
            return
        req = QNetworkRequest(url)
        return self.get_request(req, page, fileobj, filename)

    def get_request(self, request, page=None, fileobj=None, filename=None):
        """Start a download with a QNetworkRequest.

        Args:
            request: The QNetworkRequest to download.
            page: The QWebPage to use.
            fileobj: The file object to write the answer to.
            filename: A path to write the data to.

        Return:
            If the download could start immediately, (fileobj/filename given),
            the created DownloadItem.

            If not, None.
        """
        if fileobj is not None and filename is not None:
            raise TypeError("Only one of fileobj/filename may be given!")
        # WORKAROUND for Qt corrupting data loaded from cache:
        # https://bugreports.qt-project.org/browse/QTBUG-42757
        request.setAttribute(QNetworkRequest.CacheLoadControlAttribute,
                             QNetworkRequest.AlwaysNetwork)
        if fileobj is not None or filename is not None:
            return self.fetch_request(request, filename, fileobj, page)
        q = self._prepare_question()
        q.default = urlutils.filename_from_url(request.url())
        message_bridge = objreg.get('message-bridge', scope='window',
                                    window=self._win_id)
        q.answered.connect(
            lambda fn: self.fetch_request(request, filename=fn, page=page))
        message_bridge.ask(q, blocking=False)
        return None

    def fetch_request(self, request, page=None, fileobj=None, filename=None):
        """Download a QNetworkRequest to disk.

        Args:
            request: The QNetworkRequest to download.
            page: The QWebPage to use.
            fileobj: The file object to write the answer to.
            filename: A path to write the data to.

        Return:
            The created DownloadItem.
        """
        if page is None:
            nam = self._networkmanager
        else:
            nam = page.networkAccessManager()
        reply = nam.get(request)
        return self.fetch(reply, fileobj, filename)

    @pyqtSlot('QNetworkReply')
    def fetch(self, reply, fileobj=None, filename=None):
        """Download a QNetworkReply to disk.

        Args:
            reply: The QNetworkReply to download.
            fileobj: The file object to write the answer to.
            filename: A path to write the data to.

        Return:
            The created DownloadItem.
        """
        if fileobj is not None and filename is not None:
            raise TypeError("Only one of fileobj/filename may be given!")
        if filename is not None:
            suggested_filename = os.path.basename(filename)
        elif fileobj is not None and getattr(fileobj, 'name', None):
            suggested_filename = fileobj.name
        else:
            _inline, suggested_filename = http.parse_content_disposition(reply)
        log.downloads.debug("fetch: {} -> {}".format(reply.url(),
                                                     suggested_filename))
        download = DownloadItem(reply, self)
        download.finished.connect(
            functools.partial(self.on_finished, download))
        download.data_changed.connect(
            functools.partial(self.on_data_changed, download))
        download.error.connect(self.on_error)
        download.redirected.connect(
            functools.partial(self.on_redirect, download))
        download.basename = suggested_filename
        idx = len(self.downloads) + 1
        self.beginInsertRows(QModelIndex(), idx, idx)
        self.downloads.append(download)
        self.endInsertRows()

        if filename is not None:
            download.set_filename(filename)
        elif fileobj is not None:
            download.set_fileobj(fileobj)
            download.autoclose = False
        else:
            q = self._prepare_question()
            q.default = suggested_filename
            q.answered.connect(download.set_filename)
            q.cancelled.connect(download.cancel)
            download.cancelled.connect(q.abort)
            download.error.connect(q.abort)
            message_bridge = objreg.get('message-bridge', scope='window',
                                        window=self._win_id)
            message_bridge.ask(q, blocking=False)

        return download

    @cmdutils.register(instance='download-manager', scope='window')
    def cancel_download(self, count: {'special': 'count'}=1):
        """Cancel the first/[count]th download.

        Args:
            count: The index of the download to cancel.
        """
        if count == 0:
            return
        try:
            download = self.downloads[count - 1]
        except IndexError:
            raise cmdexc.CommandError("There's no download {}!".format(count))
        download.cancel()

    @pyqtSlot(QNetworkRequest, QNetworkReply)
    def on_redirect(self, download, request, reply):
        """Handle a HTTP redirect of a download.

        Args:
            download: The old DownloadItem.
            request: The new QNetworkRequest.
            reply: The old QNetworkReply.
        """
        log.downloads.debug("redirected: {} -> {}".format(
            reply.url(), request.url()))
        new_reply = reply.manager().get(request)
        download.init_reply(new_reply)

    @pyqtSlot(DownloadItem)
    def on_finished(self, download):
        """Remove finished download."""
        log.downloads.debug("on_finished: {}".format(download))
        idx = self.downloads.index(download)
        self.beginRemoveRows(QModelIndex(), idx, idx)
        del self.downloads[idx]
        self.endRemoveRows()
        download.deleteLater()

    @pyqtSlot(DownloadItem)
    def on_data_changed(self, download):
        """Emit data_changed signal when download data changed."""
        idx = self.downloads.index(download)
        model_idx = self.index(idx, 0)
        qtutils.ensure_valid(model_idx)
        self.dataChanged.emit(model_idx, model_idx)

    @pyqtSlot(str)
    def on_error(self, msg):
        """Display error message on download errors."""
        message.error(self._win_id, "Download error: {}".format(msg))

    def has_downloads_with_nam(self, nam):
        """Check if the DownloadManager has any downloads with the given QNAM.

        Args:
            nam: The QNetworkAccessManager to check.

        Return:
            A boolean.
        """
        for download in self.downloads:
            if download.reply is not None and download.reply.manager() is nam:
                return True
        return False

    def last_index(self):
        """Get the last index in the model.

        Return:
            A (possibly invalid) QModelIndex.
        """
        idx = self.index(self.rowCount() - 1)
        return idx

    def headerData(self, section, orientation, role):
        """Simple constant header."""
        if (section == 0 and orientation == Qt.Horizontal and
                role == Qt.DisplayRole):
            return "Downloads"
        else:
            return ""

    def data(self, index, role):
        """Download data from DownloadManager."""
        qtutils.ensure_valid(index)
        if index.parent().isValid() or index.column() != 0:
            return QVariant()

        item = self.downloads[index.row()]
        if role == Qt.DisplayRole:
            data = str(item)
        elif role == Qt.ForegroundRole:
            data = config.get('colors', 'downloads.fg')
        elif role == Qt.BackgroundRole:
            data = item.bg_color()
        elif role == ModelRole.item:
            data = item
        elif role == Qt.ToolTipRole:
            if item.error_msg is None:
                data = QVariant()
            else:
                return item.error_msg
        else:
            data = QVariant()
        return data

    def flags(self, _index):
        """Override flags so items aren't selectable.

        The default would be Qt.ItemIsEnabled | Qt.ItemIsSelectable."""
        return Qt.ItemIsEnabled

    def rowCount(self, parent=QModelIndex()):
        """Get count of active downloads."""
        if parent.isValid():
            # We don't have children
            return 0
        return len(self.downloads)
