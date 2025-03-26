# -*- coding: utf-8 -*-

import base64
import errno
import hashlib
import json
import logging as log
import os
import re
import shutil
import signal
import sys
import tempfile
from collections import OrderedDict, defaultdict
from io import BytesIO
from pathlib import Path
from typing import Dict, Generator, List, Optional

import treq
import yaml
from atomicwrites import atomic_write
from twisted.internet.defer import (
    Deferred,
    DeferredList,
    DeferredLock,
    inlineCallbacks,
)
from twisted.internet.error import ConnectError, ProcessDone
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.task import deferLater
from twisted.python.procutils import which

from gridsync import pkgdir
from gridsync import settings as global_settings
from gridsync.config import Config
from gridsync.crypto import trunchash
from gridsync.errors import TahoeCommandError, TahoeError, TahoeWebError
from gridsync.filter import filter_tahoe_log_message
from gridsync.monitor import Monitor
from gridsync.news import NewscapChecker
from gridsync.preferences import get_preference, set_preference
from gridsync.streamedlogs import StreamedLogs


def is_valid_furl(furl):
    return re.match(r"^pb://[a-z2-7]+@[a-zA-Z0-9\.:,-]+:\d+/[a-z2-7]+$", furl)


def get_nodedirs(basedir):
    nodedirs = []
    try:
        for filename in os.listdir(basedir):
            filepath = os.path.join(basedir, filename)
            confpath = os.path.join(filepath, "tahoe.cfg")
            if os.path.isdir(filepath) and os.path.isfile(confpath):
                log.debug("Found nodedir: %s", filepath)
                nodedirs.append(filepath)
    except OSError:
        pass
    return sorted(nodedirs)


class CommandProtocol(ProcessProtocol):
    def __init__(self, parent, callback_trigger=None):
        self.parent = parent
        self.trigger = callback_trigger
        self.done = Deferred()
        self.output = BytesIO()

    def outReceived(self, data):
        self.output.write(data)
        data = data.decode("utf-8")
        for line in data.strip().split("\n"):
            if line:
                self.parent.line_received(line)
            if not self.done.called and self.trigger and self.trigger in line:
                self.done.callback(self.transport.pid)

    def errReceived(self, data):
        self.outReceived(data)

    def processEnded(self, reason):
        if not self.done.called:
            self.done.callback(self.output.getvalue().decode("utf-8"))

    def processExited(self, reason):
        if not self.done.called and not isinstance(reason.value, ProcessDone):
            self.done.errback(
                TahoeCommandError(
                    self.output.getvalue().decode("utf-8").strip()
                )
            )


class Tahoe:

    STOPPED = 0
    STARTING = 1
    STARTED = 2
    STOPPING = 3

    def __init__(self, nodedir=None, executable=None, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self.executable = executable
        self.multi_folder_support = True
        if nodedir:
            self.nodedir = os.path.expanduser(nodedir)
        else:
            self.nodedir = os.path.join(os.path.expanduser("~"), ".tahoe")
        self.rootcap_path = os.path.join(self.nodedir, "private", "rootcap")
        self.servers_yaml_path = os.path.join(
            self.nodedir, "private", "servers.yaml"
        )
        self.config = Config(os.path.join(self.nodedir, "tahoe.cfg"))
        self.pidfile = os.path.join(self.nodedir, "twistd.pid")
        self.nodeurl = None
        self.shares_happy = 0
        self.name = os.path.basename(self.nodedir)
        self.api_token = None
        self.magic_folders_dir = os.path.join(self.nodedir, "magic-folders")
        self.lock = DeferredLock()
        self.rootcap = None
        self.magic_folders = defaultdict(dict)
        self.remote_magic_folders = defaultdict(dict)
        self.use_tor = False
        self.monitor = Monitor(self)
        streamedlogs_maxlen = None
        debug_settings = global_settings.get("debug")
        if debug_settings:
            log_maxlen = debug_settings.get("log_maxlen")
            if log_maxlen is not None:
                streamedlogs_maxlen = int(log_maxlen)
        self.streamedlogs = StreamedLogs(reactor, streamedlogs_maxlen)
        self.state = Tahoe.STOPPED
        self.newscap = ""
        self.newscap_checker = NewscapChecker(self)
        self.zkap_auth_required = False
        self.zkap_name: str = "Zero-Knowledge Access Pass"
        self.zkap_name_abbrev: str = "ZKAP"
        self.zkap_name_plural: str = "Zero-Knowledge Access Passes"
        self.zkap_unit_name: str = "Zero-Knowledge Access Pass"
        self.zkap_unit_name_abbrev: str = "ZKAP"
        self.zkap_unit_name_plural: str = "Zero-Knowledge Access Passes"
        self.zkap_unit_multiplier: int = 1
        self.zkap_payment_url_root: str = ""
        self.zkap_dircap: str = ""
        self.zkap_batch_size: int = 32768  # XXX Hardcoded in ZKAPAuthorizer
        self.settings: dict = {}

        self.monitor.zkaps_redeemed.connect(self.backup_zkaps)
        self.monitor.sync_finished.connect(self.update_zkap_checkpoint)

    @staticmethod
    def read_cap_from_file(filepath):
        try:
            with open(filepath) as f:
                cap = f.read().strip()
        except OSError:
            return None
        return cap

    def load_newscap(self):
        news_settings = global_settings.get("news:{}".format(self.name))
        if news_settings:
            newscap = news_settings.get("newscap")
            if newscap:
                self.newscap = newscap
                return
        newscap = self.read_cap_from_file(
            os.path.join(self.nodedir, "private", "newscap")
        )
        if newscap:
            self.newscap = newscap

    def config_set(self, section, option, value):
        self.config.set(section, option, value)

    def config_get(self, section, option):
        return self.config.get(section, option)

    def save_settings(self, settings: dict) -> None:
        with atomic_write(
            str(Path(self.nodedir, "private", "settings.json")), overwrite=True
        ) as f:
            f.write(json.dumps(settings))

        rootcap = settings.get("rootcap")
        if rootcap:
            with atomic_write(
                str(Path(self.nodedir, "private", "rootcap")), overwrite=True
            ) as f:
                f.write(rootcap)

        newscap = settings.get("newscap")
        if newscap:
            with atomic_write(
                str(Path(self.nodedir, "private", "newscap")), overwrite=True
            ) as f:
                f.write(newscap)

    def load_settings(self):
        try:
            with open(Path(self.nodedir, "private", "settings.json")) as f:
                settings = json.loads(f.read())
        except FileNotFoundError:
            settings = {}
        settings["nickname"] = self.name
        settings["shares-needed"] = self.config_get("client", "shares.needed")
        settings["shares-happy"] = self.config_get("client", "shares.happy")
        settings["shares-total"] = self.config_get("client", "shares.total")
        introducer = self.config_get("client", "introducer.furl")
        if introducer:
            settings["introducer"] = introducer
        storage_servers = self.get_storage_servers()
        if storage_servers:
            settings["storage"] = storage_servers
        icon_path = os.path.join(self.nodedir, "icon")
        icon_url_path = icon_path + ".url"
        if os.path.exists(icon_url_path):
            with open(icon_url_path) as f:
                settings["icon_url"] = f.read().strip()
        self.load_newscap()
        if self.newscap:
            settings["newscap"] = self.newscap
        if not settings.get("rootcap"):
            settings["rootcap"] = self.get_rootcap()
        zkap_name = settings.get("zkap_name", "")
        if zkap_name:
            self.zkap_name = zkap_name
            self.zkap_name_abbrev = "".join(
                [c for c in zkap_name if c.isupper()]
            )
            suffix = "es" if zkap_name.endswith("s") else "s"  # XXX
            self.zkap_name_plural = f"{zkap_name}{suffix}"

        zkap_unit_name = settings.get("zkap_unit_name", "")
        if zkap_unit_name:
            self.zkap_unit_name = zkap_unit_name
            suffix = "es" if zkap_unit_name.endswith("s") else "s"  # XXX
            self.zkap_unit_name_plural = f"{zkap_unit_name}{suffix}"

        zkap_unit_name_abbrev = settings.get("zkap_unit_name_abbrev", "")
        if zkap_unit_name_abbrev:
            self.zkap_unit_name_abbrev = zkap_unit_name_abbrev

        zkap_unit_multiplier = settings.get("zkap_unit_multiplier", 0)
        if zkap_unit_multiplier:
            self.zkap_unit_multiplier = zkap_unit_multiplier

        self.zkap_payment_url_root = settings.get("zkap_payment_url_root", "")
        # TODO: Verify integrity? Support 'icon_base64'?
        self.settings = settings

    def get_settings(self, include_rootcap=False):
        if not self.settings:
            self.load_settings()
        settings = dict(self.settings)
        if include_rootcap:
            settings["rootcap"] = self.get_rootcap()
        else:
            try:
                del settings["rootcap"]
            except KeyError:
                pass
        return settings

    def export(self, dest, include_rootcap=False):
        log.debug("Exporting settings to '%s'...", dest)
        settings = self.get_settings(include_rootcap)
        if self.use_tor:
            settings["hide-ip"] = True
        with atomic_write(dest, mode="w", overwrite=True) as f:
            f.write(json.dumps(settings))
        log.debug("Exported settings to '%s'", dest)

    def get_aliases(self):
        aliases = {}
        aliases_file = os.path.join(self.nodedir, "private", "aliases")
        try:
            with open(aliases_file) as f:
                for line in f.readlines():
                    if not line.startswith("#"):
                        try:
                            name, cap = line.split(":", 1)
                            aliases[name + ":"] = cap.strip()
                        except ValueError:
                            pass
            return aliases
        except IOError:
            return aliases

    def get_alias(self, alias):
        if not alias.endswith(":"):
            alias = alias + ":"
        try:
            for name, cap in self.get_aliases().items():
                if name == alias:
                    return cap
            return None
        except AttributeError:
            return None

    def _set_alias(self, alias, cap=None):
        if not alias.endswith(":"):
            alias = alias + ":"
        aliases = self.get_aliases()
        if cap:
            aliases[alias] = cap
        else:
            try:
                del aliases[alias]
            except (KeyError, TypeError):
                return
        tmp_aliases_file = os.path.join(self.nodedir, "private", "aliases.tmp")
        with atomic_write(tmp_aliases_file, mode="w", overwrite=True) as f:
            data = ""
            for name, dircap in aliases.items():
                data += "{} {}\n".format(name, dircap)
            f.write(data)
        aliases_file = os.path.join(self.nodedir, "private", "aliases")
        shutil.move(tmp_aliases_file, aliases_file)

    def add_alias(self, alias, cap):
        self._set_alias(alias, cap)

    def remove_alias(self, alias):
        self._set_alias(alias)

    def _read_servers_yaml(self):
        try:
            with open(self.servers_yaml_path) as f:
                return yaml.safe_load(f)
        except OSError:
            return {}

    def get_storage_servers(self):
        yaml_data = self._read_servers_yaml()
        if not yaml_data:
            return {}
        storage = yaml_data.get("storage")
        if not storage or not isinstance(storage, dict):
            return {}
        results = {}
        for server, server_data in storage.items():
            ann = server_data.get("ann")
            if not ann:
                continue
            results[server] = {
                "anonymous-storage-FURL": ann.get("anonymous-storage-FURL")
            }
            nickname = ann.get("nickname")
            if nickname:
                results[server]["nickname"] = nickname
            storage_options = ann.get("storage-options")
            if storage_options:
                results[server]["storage-options"] = storage_options
        return results

    def _configure_storage_plugins(self, storage_options: List[dict]) -> None:
        for options in storage_options:
            if not isinstance(options, dict):
                log.warning(
                    "Skipping unknown storage plugin option: %s", options
                )
                continue
            name = options.get("name")
            if name == "privatestorageio-zkapauthz-v1":
                # TODO: Append name instead of setting/overriding?
                self.config_set("client", "storage.plugins", name)
                self.config_set(
                    "storageclient.plugins.privatestorageio-zkapauthz-v1",
                    "redeemer",
                    "ristretto",
                )
                self.config_set(
                    "storageclient.plugins.privatestorageio-zkapauthz-v1",
                    "ristretto-issuer-root-url",
                    options.get("ristretto-issuer-root-url"),
                )
                pass_value = options.get("pass-value")
                if pass_value:
                    self.config_set(
                        "storageclient.plugins.privatestorageio-zkapauthz-v1",
                        "pass-value",
                        pass_value,
                    )
            else:
                log.warning(
                    "Skipping unknown storage plugin option: %s", options
                )

    def add_storage_server(
        self, server_id, furl, nickname=None, storage_options=None
    ):
        log.debug("Adding storage server: %s...", server_id)
        yaml_data = self._read_servers_yaml()
        if not yaml_data or not yaml_data.get("storage"):
            yaml_data["storage"] = {}
        yaml_data["storage"][server_id] = {
            "ann": {"anonymous-storage-FURL": furl}
        }
        if nickname:
            yaml_data["storage"][server_id]["ann"]["nickname"] = nickname
        if storage_options:
            yaml_data["storage"][server_id]["ann"][
                "storage-options"
            ] = storage_options
            self._configure_storage_plugins(storage_options)
        with atomic_write(
            self.servers_yaml_path, mode="w", overwrite=True
        ) as f:
            f.write(yaml.safe_dump(yaml_data, default_flow_style=False))
        log.debug("Added storage server: %s", server_id)

    def add_storage_servers(self, storage_servers):
        for server_id, data in storage_servers.items():
            nickname = data.get("nickname")
            storage_options = data.get("storage-options")
            furl = data.get("anonymous-storage-FURL")
            if furl:
                self.add_storage_server(
                    server_id, furl, nickname, storage_options
                )
            else:
                log.warning("No storage fURL provided for %s!", server_id)

    def load_magic_folders(self):
        data = {}
        yaml_path = os.path.join(self.nodedir, "private", "magic_folders.yaml")
        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
        except OSError:
            pass
        folders_data = data.get("magic-folders")
        if folders_data:
            for key, value in folders_data.items():  # to preserve defaultdict
                self.magic_folders[key] = value
        for folder in self.magic_folders:
            admin_dircap = self.get_admin_dircap(folder)
            if admin_dircap:
                self.magic_folders[folder]["admin_dircap"] = admin_dircap
        return self.magic_folders

    def line_received(self, line):
        # TODO: Connect to Core via Qt signals/slots?
        log.debug("[%s] >>> %s", self.name, line)

    @inlineCallbacks
    def command(self, args, callback_trigger=None):
        from twisted.internet import reactor

        # Some args may contain sensitive information. Don't show them in logs.
        if args[0] == "magic-folder":
            first_args = args[0:2]
        else:
            first_args = args[0:1]
        exe = self.executable if self.executable else which("tahoe")[0]
        args = [exe] + ["-d", self.nodedir] + args
        logged_args = [exe] + ["-d", self.nodedir] + first_args
        env = os.environ
        env["PYTHONUNBUFFERED"] = "1"
        log.debug("Executing: %s...", " ".join(logged_args))
        protocol = CommandProtocol(self, callback_trigger)
        reactor.spawnProcess(protocol, exe, args=args, env=env)
        output = yield protocol.done
        return output

    @inlineCallbacks
    def get_features(self):
        try:
            yield self.command(["magic-folder", "list"])
        except TahoeCommandError as err:
            if str(err).strip().endswith("Unknown command: list"):
                # Has magic-folder support but no multi-magic-folder support
                return self.executable, True, False
            # Has no magic-folder support ('Unknown command: magic-folder')
            # or something else went wrong; consider executable unsupported
            return self.executable, False, False
        # if output:
        # Has magic-folder support and multi-magic-folder support
        return self.executable, True, True

    @inlineCallbacks
    def create_client(self, **kwargs):
        if os.path.exists(self.nodedir):
            raise FileExistsError(
                "Nodedir already exists: {}".format(self.nodedir)
            )
        args = ["create-client", "--webport=tcp:0:interface=127.0.0.1"]
        for key, value in kwargs.items():
            if key in (
                "nickname",
                "introducer",
                "shares-needed",
                "shares-happy",
                "shares-total",
            ):
                args.extend(["--{}".format(key), str(value)])
            elif key in ["needed", "happy", "total"]:
                args.extend(["--shares-{}".format(key), str(value)])
            elif key == "hide-ip":
                args.append("--hide-ip")
        yield self.command(args)
        storage_servers = kwargs.get("storage")
        if storage_servers and isinstance(storage_servers, dict):
            self.add_storage_servers(storage_servers)

    def _win32_cleanup(self):
        # XXX A dirty hack to try to remove any stale magic-folder
        # sqlite databases that could not be removed earlier due to
        # being in-use by another process (i.e., Tahoe-LAFS).
        # See https://github.com/gridsync/gridsync/issues/294 and
        # https://github.com/LeastAuthority/magic-folder/issues/131
        if not self.magic_folders:
            self.load_magic_folders()  # XXX
        for p in Path(self.nodedir, "private").glob("magicfolder_*.sqlite"):
            folder_name = p.stem[12:]  # len("magicfolder_") -> 12
            if folder_name not in self.magic_folders:
                fullpath = p.resolve()
                log.debug("Trying to remove stale database %s...", fullpath)
                try:
                    p.unlink()
                except OSError as err:
                    log.warning("Error removing %s: %s", fullpath, str(err))
                    continue
                log.debug("Successfully removed %s", fullpath)

    def kill(self):
        try:
            with open(self.pidfile, "r") as f:
                pid = int(f.read())
        except (EnvironmentError, ValueError) as err:
            log.warning("Error loading pid from pidfile: %s", str(err))
            return
        log.debug("Trying to kill PID %d...", pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as err:
            if err.errno not in (errno.ESRCH, errno.EINVAL):
                log.error(err)
        if sys.platform == "win32":
            self._win32_cleanup()

    @inlineCallbacks
    def stop(self):
        log.debug('Stopping "%s" tahoe client...', self.name)
        if not os.path.isfile(self.pidfile):
            log.error('No "twistd.pid" file found in %s', self.nodedir)
            return
        self.state = Tahoe.STOPPING
        self.streamedlogs.stop()
        if self.lock.locked:
            log.warning(
                "Delaying stop operation; "
                "another operation is trying to modify the rootcap..."
            )
            yield self.lock.acquire()
            yield self.lock.release()
            log.debug("Lock released; resuming stop operation...")
        if sys.platform == "win32":
            self.kill()
        else:
            try:
                yield self.command(["stop"])
            except TahoeCommandError:  # Process already dead/not running
                pass
        try:
            os.remove(self.pidfile)
        except EnvironmentError:
            pass
        self.state = Tahoe.STOPPED
        log.debug('Finished stopping "%s" tahoe client', self.name)

    @inlineCallbacks
    def upgrade_legacy_config(self):
        log.debug("Upgrading legacy configuration layout..")
        nodedirs = get_nodedirs(self.magic_folders_dir)
        if not nodedirs:
            log.warning("No nodedirs found; returning.")
            return
        magic_folders = {}
        for nodedir in nodedirs:
            basename = os.path.basename(nodedir)
            log.debug("Migrating configuration for '%s'...", basename)

            tahoe = Tahoe(nodedir)
            directory = tahoe.config_get("magic_folder", "local.directory")
            poll_interval = tahoe.config_get("magic_folder", "poll_interval")

            collective_dircap = self.read_cap_from_file(
                os.path.join(nodedir, "private", "collective_dircap")
            )
            magic_folder_dircap = self.read_cap_from_file(
                os.path.join(nodedir, "private", "magic_folder_dircap")
            )

            magic_folders[basename] = {
                "collective_dircap": collective_dircap,
                "directory": directory,
                "poll_interval": poll_interval,
                "upload_dircap": magic_folder_dircap,
            }

            db_src = os.path.join(nodedir, "private", "magicfolderdb.sqlite")
            db_fname = "".join(["magicfolder_", basename, ".sqlite"])
            db_dest = os.path.join(self.nodedir, "private", db_fname)
            log.debug("Copying %s to %s...", db_src, db_dest)
            shutil.copyfile(db_src, db_dest)

            collective_dircap_rw = tahoe.get_alias("magic")
            if collective_dircap_rw:
                alias = hashlib.sha256(basename.encode()).hexdigest() + ":"
                yield self.command(["add-alias", alias, collective_dircap_rw])

        yaml_path = os.path.join(self.nodedir, "private", "magic_folders.yaml")
        log.debug("Writing magic-folder configs to %s...", yaml_path)
        with atomic_write(yaml_path, mode="w", overwrite=True) as f:
            f.write(yaml.safe_dump({"magic-folders": magic_folders}))

        log.debug("Backing up legacy configuration...")
        shutil.move(self.magic_folders_dir, self.magic_folders_dir + ".backup")

        log.debug("Enabling magic-folder for %s...", self.nodedir)
        self.config_set("magic_folder", "enabled", "True")

        log.debug("Finished upgrading legacy configuration")

    def get_streamed_log_messages(self):
        """
        Return a ``deque`` containing all buffered log messages.

        :return: A ``deque`` where each element is a UTF-8 & JSON encoded
            ``bytes`` object giving a single log event with older events
            appearing first.
        """
        return self.streamedlogs.get_streamed_log_messages()

    def get_log(self, apply_filter=False, identifier=None):
        messages = []
        if apply_filter:
            for line in self.streamedlogs.get_streamed_log_messages():
                messages.append(filter_tahoe_log_message(line, identifier))
        else:
            for line in self.streamedlogs.get_streamed_log_messages():
                messages.append(json.dumps(json.loads(line), sort_keys=True))
        return "\n".join(messages)

    @inlineCallbacks
    def start(self):
        log.debug('Starting "%s" tahoe client...', self.name)
        self.state = Tahoe.STARTING
        self.monitor.start()
        tcp = self.config_get("connections", "tcp")
        if tcp and tcp.lower() == "tor":
            self.use_tor = True
        if self.config_get(
            "storageclient.plugins.privatestorageio-zkapauthz-v1",
            "ristretto-issuer-root-url",
        ):
            self.zkap_auth_required = True

        if os.path.isfile(self.pidfile):
            yield self.stop()
        if self.multi_folder_support and os.path.isdir(self.magic_folders_dir):
            yield self.upgrade_legacy_config()
        pid = yield self.command(["run"], "client running")
        pid = str(pid)
        if sys.platform == "win32" and pid.isdigit():
            with atomic_write(self.pidfile, mode="w", overwrite=True) as f:
                f.write(pid)

        self.load_settings()

        with open(os.path.join(self.nodedir, "node.url")) as f:
            self.set_nodeurl(f.read().strip())
        token_file = os.path.join(self.nodedir, "private", "api_auth_token")
        with open(token_file) as f:
            self.api_token = f.read().strip()
        self.shares_happy = int(self.config_get("client", "shares.happy"))
        self.load_magic_folders()
        self.streamedlogs.start(self.nodeurl, self.api_token)
        self.load_newscap()
        self.newscap_checker.start()
        self.state = Tahoe.STARTED

        yield self.scan_storage_plugins()

        log.debug(
            'Finished starting "%s" tahoe client (pid: %s)', self.name, pid
        )

    def set_nodeurl(self, nodeurl):
        """
        Specify the location of the Tahoe-LAFS web API.

        :param str nodeurl: A text string giving the URI root of the web API.
        """
        self.nodeurl = nodeurl

    @inlineCallbacks
    def restart(self):
        from twisted.internet import reactor

        log.debug("Restarting %s client...", self.name)
        if self.state in (Tahoe.STOPPING, Tahoe.STARTING):
            log.warning(
                "Aborting restart operation; "
                'the "%s" client is already (re)starting',
                self.name,
            )
            return
        # Temporarily disable desktop notifications for (dis)connect events
        pref = get_preference("notifications", "connection")
        set_preference("notifications", "connection", "false")
        yield self.stop()
        if sys.platform == "win32":
            yield deferLater(reactor, 0.1, lambda: None)
            self._win32_cleanup()
        yield self.start()
        yield self.await_ready()
        yield deferLater(reactor, 1, lambda: None)
        set_preference("notifications", "connection", pref)
        log.debug("Finished restarting %s client.", self.name)

    @inlineCallbacks
    def get_grid_status(self):
        if not self.nodeurl:
            return None
        try:
            resp = yield treq.get(self.nodeurl + "?t=json")
        except ConnectError:
            return None
        if resp.code == 200:
            content = yield treq.content(resp)
            content = json.loads(content.decode("utf-8"))
            servers_connected = 0
            servers_known = 0
            available_space = 0
            if "servers" in content:
                servers = content["servers"]
                servers_known = len(servers)
                for server in servers:
                    if server["connection_status"].startswith("Connected"):
                        servers_connected += 1
                        if server["available_space"]:
                            available_space += server["available_space"]
            return servers_connected, servers_known, available_space
        return None

    @inlineCallbacks
    def get_connected_servers(self):
        if not self.nodeurl:
            return None
        try:
            resp = yield treq.get(self.nodeurl)
        except ConnectError:
            return None
        if resp.code == 200:
            html = yield treq.content(resp)
            match = re.search(
                "Connected to <span>(.+?)</span>", html.decode("utf-8")
            )
            if match:
                return int(match.group(1))
        return None

    @inlineCallbacks
    def is_ready(self):
        if not self.shares_happy:
            return False
        connected_servers = yield self.get_connected_servers()
        return bool(
            connected_servers and connected_servers >= self.shares_happy
        )

    @inlineCallbacks
    def await_ready(self):
        # TODO: Replace with "readiness" API?
        # https://tahoe-lafs.org/trac/tahoe-lafs/ticket/2844
        from twisted.internet import reactor

        ready = yield self.is_ready()
        if not ready:
            log.debug('Connecting to "%s"...', self.name)
        while not ready:
            yield deferLater(reactor, 0.2, lambda: None)
            ready = yield self.is_ready()
            if ready:
                log.debug('Connected to "%s"', self.name)

    @inlineCallbacks
    def mkdir(self, parentcap=None, childname=None):
        yield self.await_ready()
        url = self.nodeurl + "uri"
        params = {"t": "mkdir"}
        if parentcap and childname:
            url += "/" + parentcap
            params["name"] = childname
        resp = yield treq.post(url, params=params)
        if resp.code == 200:
            content = yield treq.content(resp)
            return content.decode("utf-8").strip()
        raise TahoeWebError(
            "Error creating Tahoe-LAFS directory: {}".format(resp.code)
        )

    @inlineCallbacks
    def create_rootcap(self):
        log.debug("Creating rootcap...")
        if os.path.exists(self.rootcap_path):
            raise OSError(
                "Rootcap file already exists: {}".format(self.rootcap_path)
            )
        yield self.lock.acquire()
        rootcap = yield self.mkdir()
        try:
            with atomic_write(self.rootcap_path, mode="w") as f:
                f.write(rootcap)
        except FileExistsError:
            log.warning("Rootcap already exists")
            return self.get_rootcap()
        finally:
            yield self.lock.release()
        log.debug("Rootcap saved to file: %s", self.rootcap_path)
        self.rootcap = rootcap
        return rootcap

    @inlineCallbacks
    def upload(self, local_path):
        log.debug("Uploading %s...", local_path)
        yield self.await_ready()
        with open(local_path, "rb") as f:
            resp = yield treq.put("{}uri".format(self.nodeurl), f)
        if resp.code == 200:
            content = yield treq.content(resp)
            log.debug("Successfully uploaded %s", local_path)
            return content.decode("utf-8")
        content = yield treq.content(resp)
        raise TahoeWebError(content.decode("utf-8"))

    @inlineCallbacks
    def download(self, cap, local_path):
        log.debug("Downloading %s...", local_path)
        yield self.await_ready()
        resp = yield treq.get("{}uri/{}".format(self.nodeurl, cap))
        if resp.code == 200:
            with atomic_write(local_path, mode="wb", overwrite=True) as f:
                yield treq.collect(resp, f.write)
            log.debug("Successfully downloaded %s", local_path)
        else:
            content = yield treq.content(resp)
            raise TahoeWebError(content.decode("utf-8"))

    @inlineCallbacks
    def link(self, dircap, childname, childcap):
        dircap_hash = trunchash(dircap)
        childcap_hash = trunchash(childcap)
        log.debug(
            'Linking "%s" (%s) into %s...',
            childname,
            childcap_hash,
            dircap_hash,
        )
        yield self.await_ready()
        yield self.lock.acquire()
        try:
            resp = yield treq.post(
                "{}uri/{}/?t=uri&name={}&uri={}".format(
                    self.nodeurl, dircap, childname, childcap
                )
            )
        finally:
            yield self.lock.release()
        if resp.code != 200:
            content = yield treq.content(resp)
            raise TahoeWebError(content.decode("utf-8"))
        log.debug(
            'Done linking "%s" (%s) into %s',
            childname,
            childcap_hash,
            dircap_hash,
        )

    @inlineCallbacks
    def unlink(self, dircap, childname):
        dircap_hash = trunchash(dircap)
        log.debug('Unlinking "%s" from %s...', childname, dircap_hash)
        yield self.await_ready()
        yield self.lock.acquire()
        try:
            resp = yield treq.post(
                "{}uri/{}/?t=unlink&name={}".format(
                    self.nodeurl, dircap, childname
                )
            )
        finally:
            yield self.lock.release()
        if resp.code != 200:
            content = yield treq.content(resp)
            raise TahoeWebError(content.decode("utf-8"))
        log.debug('Done unlinking "%s" from %s', childname, dircap_hash)

    @inlineCallbacks
    def link_magic_folder_to_rootcap(self, name):
        log.debug("Linking folder '%s' to rootcap...", name)
        rootcap = self.get_rootcap()
        tasks = []
        admin_dircap = self.get_admin_dircap(name)
        if admin_dircap:
            tasks.append(self.link(rootcap, name + " (admin)", admin_dircap))
        collective_dircap = self.get_collective_dircap(name)
        tasks.append(
            self.link(rootcap, name + " (collective)", collective_dircap)
        )
        personal_dircap = self.get_magic_folder_dircap(name)
        tasks.append(self.link(rootcap, name + " (personal)", personal_dircap))
        yield DeferredList(tasks)
        log.debug("Successfully linked folder '%s' to rootcap", name)

    @inlineCallbacks
    def unlink_magic_folder_from_rootcap(self, name):
        log.debug("Unlinking folder '%s' from rootcap...", name)
        rootcap = self.get_rootcap()
        tasks = []
        tasks.append(self.unlink(rootcap, name + " (collective)"))
        tasks.append(self.unlink(rootcap, name + " (personal)"))
        if "admin_dircap" in self.remote_magic_folders[name]:
            tasks.append(self.unlink(rootcap, name + " (admin)"))
        del self.remote_magic_folders[name]
        yield DeferredList(tasks)
        log.debug("Successfully unlinked folder '%s' from rootcap", name)

    @inlineCallbacks
    def _create_magic_folder(self, path, alias, poll_interval=60):
        log.debug("Creating magic-folder for %s...", path)
        admin_dircap = yield self.mkdir()
        admin_dircap_json = yield self.get_json(admin_dircap)
        collective_dircap = admin_dircap_json[1]["ro_uri"]
        upload_dircap = yield self.mkdir()
        upload_dircap_json = yield self.get_json(upload_dircap)
        upload_dircap_ro = upload_dircap_json[1]["ro_uri"]
        yield self.link(admin_dircap, "admin", upload_dircap_ro)
        yaml_path = os.path.join(self.nodedir, "private", "magic_folders.yaml")
        try:
            with open(yaml_path) as f:
                yaml_data = yaml.safe_load(f)
        except OSError:
            yaml_data = {}
        folders_data = yaml_data.get("magic-folders", {})
        folders_data[os.path.basename(path)] = {
            "directory": path,
            "collective_dircap": collective_dircap,
            "upload_dircap": upload_dircap,
            "poll_interval": poll_interval,
        }
        with atomic_write(yaml_path, mode="w", overwrite=True) as f:
            f.write(yaml.safe_dump({"magic-folders": folders_data}))
        self.add_alias(alias, admin_dircap)

    @inlineCallbacks
    def create_magic_folder(
        self, path, join_code=None, admin_dircap=None, poll_interval=60
    ):  # XXX See Issue #55
        from twisted.internet import reactor

        path = os.path.realpath(os.path.expanduser(path))
        poll_interval = str(poll_interval)
        try:
            os.makedirs(path)
        except OSError:
            pass
        name = os.path.basename(path)
        alias = hashlib.sha256(name.encode()).hexdigest() + ":"
        if join_code:
            yield self.command(
                [
                    "magic-folder",
                    "join",
                    "-p",
                    poll_interval,
                    "-n",
                    name,
                    join_code,
                    path,
                ]
            )
            if admin_dircap:
                self.add_alias(alias, admin_dircap)
        else:
            yield self.await_ready()
            # yield self.command(['magic-folder', 'create', '-p', poll_interval,
            #                    '-n', name, alias, 'admin', path])
            try:
                yield self._create_magic_folder(path, alias, poll_interval)
            except Exception as e:  # pylint: disable=broad-except
                log.debug(
                    'Magic-folder creation failed: "%s: %s"; retrying...',
                    type(e).__name__,
                    str(e),
                )
                yield deferLater(reactor, 3, lambda: None)  # XXX
                yield self.await_ready()
                yield self._create_magic_folder(path, alias, poll_interval)
        if not self.config_get("magic_folder", "enabled"):
            self.config_set("magic_folder", "enabled", "True")
        self.load_magic_folders()
        yield self.link_magic_folder_to_rootcap(name)

    @inlineCallbacks
    def restore_magic_folder(self, folder_name, dest):
        data = self.remote_magic_folders[folder_name]
        admin_dircap = data.get("admin_dircap")
        collective_dircap = data.get("collective_dircap")
        upload_dircap = data.get("upload_dircap")
        if not collective_dircap or not upload_dircap:
            raise TahoeError(
                'The capabilities needed to restore the folder "{}" could '
                "not be found. This probably means that the folder was "
                "never completely uploaded to begin with -- or worse, "
                "that your rootcap was corrupted somehow after the fact.\n"
                "\nYou will need to remove this folder and upload it "
                "again.".format(folder_name)
            )
        yield self.create_magic_folder(
            os.path.join(dest, folder_name),
            "{}+{}".format(collective_dircap, upload_dircap),
            admin_dircap,
        )

    def local_magic_folder_exists(self, folder_name):
        if folder_name in self.magic_folders:
            return True
        return False

    def remote_magic_folder_exists(self, folder_name):
        if folder_name in self.remote_magic_folders:
            return True
        return False

    def magic_folder_exists(self, folder_name):
        if self.local_magic_folder_exists(folder_name):
            return True
        if self.remote_magic_folder_exists(folder_name):
            return True
        return False

    @inlineCallbacks
    def magic_folder_invite(self, name, nickname):
        yield self.await_ready()
        admin_dircap = self.get_admin_dircap(name)
        if not admin_dircap:
            raise TahoeError(
                'No admin dircap found for folder "{}"; you do not have the '
                "authority to create invites for this folder.".format(name)
            )
        created = yield self.mkdir(admin_dircap, nickname)
        code = "{}+{}".format(self.get_collective_dircap(name), created)
        return code

    @inlineCallbacks
    def magic_folder_uninvite(self, name, nickname):
        log.debug('Uninviting "%s" from "%s"...', nickname, name)
        alias = hashlib.sha256(name.encode()).hexdigest()
        yield self.unlink(self.get_alias(alias), nickname)
        log.debug('Uninvited "%s" from "%s"...', nickname, name)

    @inlineCallbacks
    def remove_magic_folder(self, name):
        if name in self.magic_folders:
            del self.magic_folders[name]
            yield self.command(["magic-folder", "leave", "-n", name])
            self.remove_alias(hashlib.sha256(name.encode()).hexdigest())

    @inlineCallbacks
    def get_magic_folder_status(self, name):
        if not self.nodeurl or not self.api_token:
            return None
        try:
            resp = yield treq.post(
                self.nodeurl + "magic_folder",
                {"token": self.api_token, "name": name, "t": "json"},
            )
        except ConnectError:
            return None
        if resp.code == 200:
            content = yield treq.content(resp)
            return json.loads(content.decode("utf-8"))
        return None

    @inlineCallbacks
    def get_bytes(self, cap: str):
        if not cap or not self.nodeurl:
            return b""
        try:
            resp = yield treq.get(f"{self.nodeurl}uri/{cap}")
        except ConnectError:
            return b""
        if resp.code == 200:
            content = yield treq.content(resp)
            return content
        raise TahoeWebError(f"Error getting bytes: {resp.code}")

    @inlineCallbacks
    def get_json(self, cap):
        if not cap or not self.nodeurl:
            return None
        uri = "{}uri/{}/?t=json".format(self.nodeurl, cap)
        try:
            resp = yield treq.get(uri)
        except ConnectError:
            return None
        if resp.code == 200:
            content = yield treq.content(resp)
            return json.loads(content.decode("utf-8"))
        return None

    def get_rootcap(self):
        if not self.rootcap:
            self.rootcap = self.read_cap_from_file(self.rootcap_path)
        return self.rootcap

    def get_admin_dircap(self, name):
        if name in self.magic_folders:
            try:
                return self.magic_folders[name]["admin_dircap"]
            except KeyError:
                pass
        cap = self.get_alias(hashlib.sha256(name.encode()).hexdigest())
        self.magic_folders[name]["admin_dircap"] = cap
        return cap

    def _get_magic_folder_setting(self, folder_name, setting_name):
        if folder_name not in self.magic_folders:
            self.load_magic_folders()
        if folder_name in self.magic_folders:
            try:
                return self.magic_folders[folder_name][setting_name]
            except KeyError:
                return None
        return None

    def get_collective_dircap(self, name):
        return self._get_magic_folder_setting(name, "collective_dircap")

    def get_magic_folder_dircap(self, name):
        return self._get_magic_folder_setting(name, "upload_dircap")

    def get_magic_folder_directory(self, name):
        return self._get_magic_folder_setting(name, "directory")

    @inlineCallbacks
    def get_magic_folders_from_rootcap(self, content=None):
        if not content:
            content = yield self.get_json(self.get_rootcap())
        if content:
            folders = defaultdict(dict)
            for name, data in content[1]["children"].items():
                data_dict = data[1]
                if name.endswith(" (collective)"):
                    prefix = name.split(" (collective)")[0]
                    folders[prefix]["collective_dircap"] = data_dict["ro_uri"]
                elif name.endswith(" (personal)"):
                    prefix = name.split(" (personal)")[0]
                    folders[prefix]["upload_dircap"] = data_dict["rw_uri"]
                elif name.endswith(" (admin)"):
                    prefix = name.split(" (admin)")[0]
                    folders[prefix]["admin_dircap"] = data_dict["rw_uri"]
            self.remote_magic_folders = folders
            return folders
        return None

    @inlineCallbacks
    def ensure_folder_links(self, _):
        yield self.await_ready()
        if not self.get_rootcap():
            yield self.create_rootcap()
        if self.magic_folders:
            remote_folders = yield self.get_magic_folders_from_rootcap()
            for folder in self.magic_folders:
                if folder not in remote_folders:
                    self.link_magic_folder_to_rootcap(folder)
                else:
                    log.debug(
                        'Folder "%s" already linked to rootcap; ' "skipping.",
                        folder,
                    )

    @inlineCallbacks
    def get_magic_folder_members(self, name, content=None):
        if not content:
            content = yield self.get_json(self.get_collective_dircap(name))
        if content:
            members = []
            children = content[1]["children"]
            magic_folder_dircap = self.get_magic_folder_dircap(name)
            for member in children:
                readcap = children[member][1]["ro_uri"]
                if magic_folder_dircap:
                    my_fingerprint = magic_folder_dircap.split(":")[-1]
                    fingerprint = readcap.split(":")[-1]
                    if fingerprint == my_fingerprint:
                        self.magic_folders[name]["member"] = member
                        members.insert(0, (member, readcap))
                    else:
                        members.append((member, readcap))
                else:
                    members.append((member, readcap))
            return members
        return None

    @staticmethod
    def _extract_metadata(metadata):
        try:
            deleted = metadata["metadata"]["deleted"]
        except KeyError:
            deleted = False
        if deleted:
            cap = metadata["metadata"]["last_downloaded_uri"]
        else:
            cap = metadata["ro_uri"]
        return {
            "size": int(metadata["size"]),
            "mtime": float(metadata["metadata"]["tahoe"]["linkmotime"]),
            "deleted": deleted,
            "cap": cap,
        }

    @inlineCallbacks
    def get_magic_folder_state(self, name, members=None):
        total_size = 0
        history_dict = {}
        if not members:
            members = yield self.get_magic_folder_members(name)
        if members:
            for member, dircap in members:
                json_data = yield self.get_json(dircap)
                try:
                    children = json_data[1]["children"]
                except (TypeError, KeyError):
                    continue
                for filenode, data in children.items():
                    if filenode.endswith("@_"):
                        # Ignore subdirectories, due to Tahoe-LAFS bug #2924
                        # https://tahoe-lafs.org/trac/tahoe-lafs/ticket/2924
                        continue
                    try:
                        metadata = self._extract_metadata(data[1])
                    except KeyError:
                        continue
                    metadata["path"] = filenode.replace("@_", os.path.sep)
                    metadata["member"] = member
                    history_dict[metadata["mtime"]] = metadata
                    total_size += metadata["size"]
        history_od = OrderedDict(sorted(history_dict.items()))
        latest_mtime = next(reversed(history_od), 0)
        return members, total_size, latest_mtime, history_od

    @staticmethod
    def generate_voucher() -> str:
        return base64.urlsafe_b64encode(os.urandom(33)).decode("utf-8")

    @inlineCallbacks
    def add_voucher(self, voucher: Optional[str] = None):
        if not voucher:
            voucher = self.generate_voucher()
        resp = yield treq.put(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            "/voucher",
            json.dumps({"voucher": voucher}).encode(),
            headers={"Authorization": f"tahoe-lafs {self.api_token}"},
        )
        if resp.code == 200:
            return voucher
        raise TahoeWebError(f"Error adding voucher: {resp.code}")

    @inlineCallbacks
    def get_voucher(self, voucher: str):
        resp = yield treq.get(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            f"/voucher/{voucher}",
            headers={"Authorization": f"tahoe-lafs {self.api_token}"},
        )
        if resp.code == 200:
            content = yield treq.json_content(resp)
            return content
        raise TahoeWebError(f"Error getting voucher: {resp.code}")

    @inlineCallbacks
    def get_vouchers(self):
        resp = yield treq.get(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            "/voucher",
            headers={"Authorization": f"tahoe-lafs {self.api_token}"},
        )
        if resp.code == 200:
            content = yield treq.json_content(resp)
            return content.get("vouchers")
        raise TahoeWebError(f"Error getting vouchers: {resp.code}")

    @inlineCallbacks
    def get_zkaps(
        self, limit: Optional[int] = None, position: Optional[str] = None
    ):
        params = {}
        if limit:
            params["limit"] = limit
        if position:
            params["position"] = position  # type: ignore
        resp = yield treq.get(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            "/unblinded-token",
            params=params,
            headers={"Authorization": f"tahoe-lafs {self.api_token}"},
        )
        if resp.code == 200:
            content = yield treq.json_content(resp)
            return content
        raise TahoeWebError(f"Error getting ZKAPs: {resp.code}")

    def zkap_payment_url(self, voucher: str) -> str:
        if not self.zkap_payment_url_root:
            return ""
        return "{}?voucher={}&checksum={}".format(
            self.zkap_payment_url_root,
            voucher,
            hashlib.sha256(voucher.encode()).hexdigest(),
        )

    @inlineCallbacks
    def get_zkap_dircap(self):
        if not self.get_rootcap():
            yield self.create_rootcap()
        if self.zkap_dircap:
            return self.zkap_dircap
        root_json = yield self.get_json(self.rootcap)
        try:
            self.zkap_dircap = root_json[1]["children"][".zkaps"][1]["rw_uri"]
        except KeyError:
            self.zkap_dircap = yield self.mkdir(self.rootcap, ".zkaps")
        return self.zkap_dircap

    @inlineCallbacks
    def get(self, cap: str):
        yield self.await_ready()
        resp = yield treq.get("{}uri/{}".format(self.nodeurl, cap))
        content = yield treq.content(resp)
        if resp.code == 200:
            return content
        raise TahoeWebError(content.decode("utf-8"))

    @inlineCallbacks
    def update_zkap_checkpoint(self, _=None):
        zkaps_dir = os.path.join(self.nodedir, "private", "zkaps")
        os.makedirs(zkaps_dir, exist_ok=True)

        # The act of updating the checkpoint itself costs at least 1
        # ZKAP, so use the *second* token as the "checkpoint" (on the
        # assumption that the first/next token will be spent imminently)
        zkaps = yield self.get_zkaps(2)
        checkpoint = zkaps.get("unblinded-tokens")[1]
        checkpoint_path = os.path.join(zkaps_dir, "checkpoint")
        with atomic_write(checkpoint_path, overwrite=True) as f:
            f.write(checkpoint.strip())

        zkap_dircap = yield self.get_zkap_dircap()
        checkpoint_filecap = yield self.upload(checkpoint_path)
        yield self.link(zkap_dircap, "checkpoint", checkpoint_filecap)

    @inlineCallbacks
    def backup_zkaps(self, timestamp: str):
        zkaps_dir = os.path.join(self.nodedir, "private", "zkaps")
        os.makedirs(zkaps_dir, exist_ok=True)

        local_backup_filename = timestamp.replace(":", "_") + ".json"
        local_backup_path = os.path.join(zkaps_dir, local_backup_filename)
        if os.path.exists(local_backup_path):
            log.debug("ZKAP backup %s already uploaded", local_backup_filename)
            return
        try:
            with open(os.path.join(zkaps_dir, "last-redeemed")) as f:
                if timestamp == f.read():
                    log.debug(
                        "No ZKAP backup needed for %s; cancelling", timestamp
                    )
                    return
        except OSError:
            pass

        temp_path = os.path.join(zkaps_dir, "backup.json.tmp")

        zkaps = yield self.get_zkaps()
        zkaps["last-redeemed"] = timestamp

        with atomic_write(temp_path, overwrite=True) as f:  # type: ignore
            f.write(json.dumps(zkaps))

        zkap_dircap = yield self.get_zkap_dircap()
        backup_filecap = yield self.upload(temp_path)
        yield self.link(zkap_dircap, "backup.json", backup_filecap)

        yield self.update_zkap_checkpoint()

        shutil.move(temp_path, local_backup_path)

    @inlineCallbacks
    def insert_zkaps(self, zkaps: list):
        resp = yield treq.post(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            "/unblinded-token",
            json.dumps({"unblinded-tokens": zkaps}).encode(),
            headers={"Authorization": f"tahoe-lafs {self.api_token}"},
        )
        if resp.code == 200:
            content = yield treq.json_content(resp)
            return content
        raise TahoeWebError(f"Error inserting ZKAPs: {resp.code}")

    @inlineCallbacks
    def restore_zkaps(self):
        zkap_dircap = yield self.get_zkap_dircap()

        backup = yield self.get(zkap_dircap + "/backup.json")
        backup_decoded = json.loads(backup.decode())
        tokens = backup_decoded.get("unblinded-tokens")

        checkpoint = yield self.get(zkap_dircap + "/checkpoint")
        checkpoint = checkpoint.decode()

        yield self.insert_zkaps(tokens[tokens.index(checkpoint) :])

        zkaps_dir = os.path.join(self.nodedir, "private", "zkaps")
        os.makedirs(zkaps_dir, exist_ok=True)

        with atomic_write(
            str(Path(zkaps_dir, "last-redeemed")), overwrite=True
        ) as f:
            f.write(str(backup_decoded.get("last-redeemed")))

        with atomic_write(
            str(Path(zkaps_dir, "last-total")), overwrite=True
        ) as f:
            f.write(str(backup_decoded.get("total")))

    @inlineCallbacks
    def get_zkapauthz_version(self):
        resp = yield treq.get(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            "/version",
            headers={"Authorization": f"tahoe-lafs {self.api_token}"},
        )
        version = ""
        if resp.code == 200:
            content = yield treq.json_content(resp)
            version = content.get("version", "")
        return version

    @inlineCallbacks
    def calculate_price(self, sizes: List[int]) -> Generator[int, None, Dict]:
        if not self.nodeurl:
            return {}
        resp = yield treq.post(
            f"{self.nodeurl}storage-plugins/privatestorageio-zkapauthz-v1"
            "/calculate-price",
            json.dumps({"version": 1, "sizes": sizes}).encode(),
            headers={
                "Authorization": f"tahoe-lafs {self.api_token}",
                "Content-Type": "application/json",
            },
        )
        if resp.code == 200:  # type: ignore
            content = yield treq.json_content(resp)
            return content  # type: ignore
        raise TahoeWebError(
            f"Error calculating price: {resp.code}"  # type: ignore
        )

    @inlineCallbacks
    def get_sizes(self) -> Generator[int, None, List[Optional[int]]]:
        sizes: list = []
        rootcap = self.get_rootcap()
        rootcap_bytes = yield self.get_bytes(f"{rootcap}/?t=json")
        if not rootcap_bytes:
            return sizes
        sizes.append(len(rootcap_bytes))
        rootcap_data = json.loads(rootcap_bytes.decode("utf-8"))
        if rootcap_data:
            dircaps = []
            for data in rootcap_data[1]["children"].values():
                rw_uri = data[1].get("rw_uri", "")
                if rw_uri:  # Only care about dirs the user can write to
                    dircaps.append(rw_uri)
            for dircap in dircaps:
                dircap_bytes = yield self.get_bytes(f"{dircap}/?t=json")
                sizes.append(len(dircap_bytes))
                dircap_data = json.loads(dircap_bytes.decode("utf-8"))
                for data in dircap_data[1]["children"].values():
                    size = data[1].get("size", 0)
                    if size:
                        sizes.append(size)
        return sizes

    @inlineCallbacks
    def get_price(self) -> Generator[int, None, Dict]:
        sizes = yield self.get_sizes()
        price = yield self.calculate_price(sizes)
        return price  # type: ignore

    @inlineCallbacks
    def scan_storage_plugins(self):
        plugins = []
        log.debug("Scanning for known storage plugins...")
        version = yield self.get_zkapauthz_version()
        if version:
            plugins.append(("ZKAPAuthorizer", version))
        if plugins:
            log.debug("Found storage plugins: %s", plugins)
        else:
            log.debug("No storage plugins found")


@inlineCallbacks
def select_executable():
    if getattr(sys, "frozen", False):
        # Always select the bundled tahoe executable if using a binary build.
        # To prevent issues caused by potentially broken or outdated tahoe
        # installations on the user's PATH.
        if sys.platform == "win32":
            return os.path.join(pkgdir, "Tahoe-LAFS", "tahoe.exe")
        return os.path.join(pkgdir, "Tahoe-LAFS", "tahoe")
    executables = which("tahoe")
    if not executables:
        return None
    tmpdir = tempfile.TemporaryDirectory()
    tasks = []
    for executable in executables:
        log.debug(
            "Found %s; checking for multi-magic-folder support...", executable
        )
        tasks.append(Tahoe(tmpdir.name, executable=executable).get_features())
    results = yield DeferredList(tasks)
    for success, result in results:
        if success:
            path, has_folder_support, has_multi_folder_support = result
            if has_folder_support and has_multi_folder_support:
                log.debug("Found suitable executable: %s", path)
                return path
    return None
