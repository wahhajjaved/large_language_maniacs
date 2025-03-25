#
# deluge/ui/web/json_api.py
#
# Copyright (C) 2009 Damien Churchill <damoxc@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
#   The Free Software Foundation, Inc.,
#   51 Franklin Street, Fifth Floor
#   Boston, MA  02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.
#
#

import os
import time
import base64
import urllib
import logging
import hashlib
import tempfile

from types import FunctionType
from twisted.internet.defer import Deferred, DeferredList
from twisted.web import http, resource, server

from deluge import common, component
from deluge.configmanager import ConfigManager
from deluge.ui import common as uicommon
from deluge.ui.client import client, Client

from deluge.ui.web.common import _
json = common.json

log = logging.getLogger(__name__)

AUTH_LEVEL_DEFAULT = None

class JSONComponent(component.Component):
    def __init__(self, name, interval=1, depend=None):
        super(JSONComponent, self).__init__(name, interval, depend)
        self._json = component.get("JSON")
        self._json.register_object(self, name)

def export(auth_level=AUTH_LEVEL_DEFAULT):
    """
    Decorator function to register an object's method as an RPC.  The object
    will need to be registered with an `:class:RPCServer` to be effective.

    :param func: function, the function to export
    :param auth_level: int, the auth level required to call this method

    """
    global AUTH_LEVEL_DEFAULT
    if AUTH_LEVEL_DEFAULT is None:
        from deluge.ui.web.auth import AUTH_LEVEL_DEFAULT
    
    def wrap(func, *args, **kwargs):
        func._json_export = True
        func._json_auth_level = auth_level
        return func

    if type(auth_level) is FunctionType:
        func = auth_level
        auth_level = AUTH_LEVEL_DEFAULT
        return wrap(func)
    else:
        return wrap

class JSONException(Exception):
    def __init__(self, inner_exception):
        self.inner_exception = inner_exception
        Exception.__init__(self, str(inner_exception))

class JSON(resource.Resource, component.Component):
    """
    A Twisted Web resource that exposes a JSON-RPC interface for web clients
    to use.
    """
    
    def __init__(self):
        resource.Resource.__init__(self)
        component.Component.__init__(self, "JSON")
        self._remote_methods = []
        self._local_methods = {}
        client.disconnect_callback = self._on_client_disconnect
    
    def connect(self, host="localhost", port=58846, username="", password=""):
        """
        Connects the client to a daemon
        """
        d = Deferred()
        _d = client.connect(host, port, username, password)
        
        def on_get_methods(methods):
            """
            Handles receiving the method names
            """
            self._remote_methods = methods
            methods = list(self._remote_methods)
            methods.extend(self._local_methods)
            d.callback(methods)
        
        def on_client_connected(connection_id):
            """
            Handles the client successfully connecting to the daemon and 
            invokes retrieving the method names.
            """
            d = client.daemon.get_method_list()
            d.addCallback(on_get_methods)
            component.get("PluginManager").start()
        _d.addCallback(on_client_connected)
        return d
    
    def _on_client_disconnect(self, *args):
        component.get("PluginManager").stop()
    
    def _exec_local(self, method, params):
        """
        Handles executing all local methods.
        """
        if method == "system.listMethods":
            d = Deferred()
            methods = list(self._remote_methods)
            methods.extend(self._local_methods)
            d.callback(methods)
            return d
        elif method in self._local_methods:
            # This will eventually process methods that the server adds
            # and any plugins.
            return self._local_methods[method](*params)
        raise JSONException("Unknown system method")
    
    def _exec_remote(self, method, params):
        """
        Executes methods using the Deluge client.
        """
        component, method = method.split(".")
        return getattr(getattr(client, component), method)(*params)
    
    def _handle_request(self, request):
        """
        Takes some json data as a string and attempts to decode it, and process
        the rpc object that should be contained, returning a deferred for all
        procedure calls and the request id.
        """
        request_id = None
        try:
            request = json.loads(request)
        except ValueError:
            raise JSONException("JSON not decodable")
        
        if "method" not in request or "id" not in request or \
           "params" not in request:
            raise JSONException("Invalid JSON request")
        
        method, params = request["method"], request["params"]
        request_id = request["id"]
        
        try:
            if method.startswith("system."):
                return self._exec_local(method, params), request_id
            elif method in self._local_methods:
                return self._exec_local(method, params), request_id
            elif method in self._remote_methods:
                return self._exec_remote(method, params), request_id
        except Exception, e:
            log.exception(e)
            d = Deferred()
            d.callback(None)
            return d, request_id
    
    def _on_rpc_request_finished(self, result, response, request):
        """
        Sends the response of any rpc calls back to the json-rpc client.
        """
        response["result"] = result
        return self._send_response(request, response)

    def _on_rpc_request_failed(self, reason, response, request):
        """
        Handles any failures that occured while making an rpc call.
        """
        print type(reason)
        request.setResponseCode(http.INTERNAL_SERVER_ERROR)
        return ""
    
    def _on_json_request(self, request):
        """
        Handler to take the json data as a string and pass it on to the
        _handle_request method for further processing.
        """
        log.debug("json-request: %s", request.json)
        response = {"result": None, "error": None, "id": None}
        d, response["id"] = self._handle_request(request.json)
        d.addCallback(self._on_rpc_request_finished, response, request)
        d.addErrback(self._on_rpc_request_failed, response, request)
        return d
    
    def _on_json_request_failed(self, reason, request):
        """
        Errback handler to return a HTTP code of 500.
        """
        log.exception(reason)
        request.setResponseCode(http.INTERNAL_SERVER_ERROR)
        return ""
    
    def _send_response(self, request, response):
        response = json.dumps(response)
        request.setHeader("content-type", "application/x-json")
        request.write(response)
        request.finish()
    
    def render(self, request):
        """
        Handles all the POST requests made to the /json controller.
        """

        if request.method != "POST":
            request.setResponseCode(http.NOT_ALLOWED)
            return ""
        
        try:
            request.content.seek(0)
            request.json = request.content.read()
            d = self._on_json_request(request)
            return server.NOT_DONE_YET
        except Exception, e:
            return self._on_json_request_failed(e, request)
    
    def register_object(self, obj, name=None):
        """
        Registers an object to export it's rpc methods.  These methods should
        be exported with the export decorator prior to registering the object.

        :param obj: object, the object that we want to export
        :param name: str, the name to use, if None, it will be the class name of the object
        """
        name = name or obj.__class__.__name__
        name = name.lower()

        for d in dir(obj):
            if d[0] == "_":
                continue
            if getattr(getattr(obj, d), '_json_export', False):
                log.debug("Registering method: %s", name + "." + d)
                self._local_methods[name + "." + d] = getattr(obj, d)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 58846

DEFAULT_HOSTS = {
    "hosts": [(hashlib.sha1(str(time.time())).hexdigest(),
        DEFAULT_HOST, DEFAULT_PORT, "", "")]
}
HOSTLIST_ID = 0
HOSTLIST_NAME = 1
HOSTLIST_PORT = 2
HOSTLIST_USER = 3
HOSTLIST_PASS = 4

HOSTS_ID = HOSTLIST_ID
HOSTS_NAME = HOSTLIST_NAME
HOSTS_PORT = HOSTLIST_PORT
HOSTS_STATUS = 3
HOSTS_INFO = 4

FILES_KEYS = ["files", "file_progress", "file_priorities"]

class WebApi(JSONComponent):
    def __init__(self):
        super(WebApi, self).__init__("Web")
        self.host_list = ConfigManager("hostlist.conf.1.2", DEFAULT_HOSTS)
    
    def get_host(self, host_id):
        """
        Return the information about a host
        
        :param host_id: str, the id of the host
        :returns: the host information
        :rtype: list
        """
        for host in self.host_list["hosts"]:
            if host[0] == host_id:
                return host
    
    @export
    def connect(self, host_id):
        """
        Connect the client to a daemon
        
        :param host_id: str, the id of the daemon in the host list
        :returns: the methods the daemon supports
        :rtype: list
        """
        d = Deferred()
        def on_connected(methods):
            d.callback(methods)
        for host in self.host_list["hosts"]:
            if host_id != host[0]:
                continue
            self._json.connect(*host[1:]).addCallback(on_connected)
        return d
    
    @export
    def connected(self):
        """
        The current connection state.
        
        :returns: True if the client is connected
        :rtype: bool
        """
        d = Deferred()
        d.callback(client.connected())
        return d
    
    @export
    def disconnect(self):
        """
        Disconnect the web interface from the connected daemon.
        """
        d =  Deferred()
        client.disconnect()
        d.callback(True)
        return d
    
    @export
    def update_ui(self, keys, filter_dict):
        """
        Gather the information required for updating the web interface.
        
        :param keys: list, the information about the torrents to gather
        :param filter_dict: dict, the filters to apply when selecting torrents.
        :returns: The torrent and ui information.
        :rtype: dict
        """
        ui_info = {
            "torrents": None,
            "filters": None,
            "stats": None
        }
        
        d = Deferred()
        
        log.info("Updating ui with keys '%r' and filters '%r'", keys,
            filter_dict)
        
        def got_stats(stats):
            ui_info["stats"] = stats
        
        def got_filters(filters):
            ui_info["filters"] = filters
            
        def got_torrents(torrents):
            ui_info["torrents"] = torrents

        def on_complete(result):
            d.callback(ui_info)
        
        d1 = client.core.get_torrents_status(filter_dict, keys)
        d1.addCallback(got_torrents)

        d2 = client.core.get_filter_tree()
        d2.addCallback(got_filters)

        d3 = client.core.get_stats()
        d3.addCallback(got_stats)
        
        dl = DeferredList([d1, d2, d3], consumeErrors=True)
	dl.addCallback(on_complete)
        return d
    
    def _on_got_files(self, torrent, d):
        files = torrent.get("files")
        file_progress = torrent.get("file_progress")
        file_priorities = torrent.get("file_priorities")

        paths = []
        info = {}
        for index, torrent_file in enumerate(files):
            path = torrent_file["path"]
            paths.append(path)
            torrent_file["progress"] = file_progress[index]
            torrent_file["priority"] = file_priorities[index]
            torrent_file["index"] = index
            info[path] = torrent_file
        
        def walk(path, item):
            if type(item) is dict:
                return item
            return [info[path]["index"], info[path]["size"],
                info[path]["progress"], info[path]["priority"]]

        file_tree = uicommon.FileTree(paths)
        file_tree.walk(walk)
        d.callback(file_tree.get_tree())
    
    @export
    def get_torrent_files(self, torrent_id):
        """
        Gets the files for a torrent in tree format
        
        :param torrent_id: string, the id of the torrent to retrieve.
        :returns: The torrents files in a tree
        :rtype: dict
        """
        main_deferred = Deferred()        
        d = client.core.get_torrent_status(torrent_id, FILES_KEYS)        
        d.addCallback(self._on_got_files, main_deferred)
        return main_deferred

    @export
    def download_torrent_from_url(self, url):
        """
        Download a torrent file from a url to a temporary directory.
        
        :param url: str, the url of the torrent
        :returns: the temporary file name of the torrent file
        :rtype: str
        """
        tmp_file = os.path.join(tempfile.gettempdir(), url.split("/")[-1])
        filename, headers = urllib.urlretrieve(url, tmp_file)
        log.debug("filename: %s", filename)
        d = Deferred()
        d.callback(filename)
        return d
    
    @export
    def get_torrent_info(self, filename):
        """
        Return information about a torrent on the filesystem.
        
        :param filename: str, the path to the torrent
        :returns:
        {
            "filename": the torrent file
            "name": the torrent name
            "size": the total size of the torrent
            "files": the files the torrent contains
            "info_hash" the torrents info_hash
        }
        """
        d = Deferred()
        try:
            torrent_info = uicommon.TorrentInfo(filename.strip())
            d.callback(torrent_info.as_dict("name", "info_hash", "files_tree"))
        except:
            d.callback(False)
        return d

    @export
    def add_torrents(self, torrents):
        """
        Add torrents by file
        
        :param torrents: A list of dictionaries containing the torrent
        path and torrent options to add with.
        :type torrents: list
        
        **Usage**
        >>> json_api.web.add_torrents([{
                "path": "/tmp/deluge-web/some-torrent-file.torrent",
                "options": {"download_path": "/home/deluge/"}
            }])
        """
        for torrent in torrents:
            filename = os.path.basename(torrent["path"])
            fdump = base64.encodestring(open(torrent["path"], "rb").read())
            log.info("Adding torrent from file `%s` with options `%r`",
                filename, torrent["options"])
            client.core.add_torrent_file(filename, fdump, torrent["options"])
        d = Deferred()
        d.callback(True)
        return d
    
    @export
    def get_hosts(self):
        """
        Return the hosts in the hostlist.
        """
        log.debug("get_hosts called")
    	d = Deferred()
    	d.callback([(host[HOSTS_ID:HOSTS_PORT+1] + [_("Offline"),]) for host in self.host_list["hosts"]])
    	return d

    @export
    def get_host_status(self, host_id):
    	"""
    	Returns the current status for the specified host.
    	"""
    	main_deferred = Deferred()
    	
    	(host_id, host, port, user, password) = self.get_host(host_id)
    	
    	def callback(status, info=None):
    		main_deferred.callback((host_id, host, port, status, info))
    	
    	def on_connect(connected, c, host_id):
            def on_info(info, c):
                c.disconnect()
                callback(_("Online"), info)
            
            def on_info_fail(reason):
                callback(_("Offline"))
            
            if not connected:
                callback(_("Offline"))
                return

            d = c.daemon.info()
            d.addCallback(on_info, c)
            d.addErrback(on_info_fail)
            
        def on_connect_failed(reason, host_id):
            callback(_("Offline"))
            
        if client.connected() and (host, port, "localclient" if not \
            user and host in ("127.0.0.1", "localhost") else \
            user)  == client.connection_info():
            def on_info(info):
                callback(_("Connected"), info)

            client.daemon.info().addCallback(on_info)
        
        c = Client()
        d = c.connect(host, port, user, password)
        d.addCallback(on_connect, c, host_id)
        d.addErrback(on_connect_failed, host_id)
        return main_deferred
    
    @export
    def stop_daemon(self, connection_id):
        """
        Stops a running daemon.

        :param connection_id: str, the hash id of the connection

        """
        main_deferred = Deferred()
        host = self.get_host(connection_id)
        if not host:
            main_deferred.callback((False, _("Daemon doesn't exist")))
            return main_deferred
        
        try:
            def on_connect(connected, c):
                if not connected:
                    main_deferred.callback((False, _("Daemon not running")))
                    return
                c.daemon.shutdown()
                main_deferred.callback((True, ))
            
            def on_connect_failed(reason):
                main_deferred.callback((False, reason))

            host, port, user, password = host[1:5]
            c = Client()
            d = c.connect(host, port, user, password)
            d.addCallback(on_connect, c)
            d.addErrback(on_connect_failed)
        except:
            main_deferred.callback((False, "An error occured"))
        return main_deferred
    
    @export
    def add_host(self, host, port, username="", password=""):
        """
        Adds a host to the list.

        :param host: str, the hostname
        :param port: int, the port
        :param username: str, the username to login as
        :param password: str, the password to login with

        """
        d = Deferred()
        # Check to see if there is already an entry for this host and return
        # if thats the case
        for entry in self.host_list["hosts"]:
            if (entry[0], entry[1], entry[2]) == (host, port, username):
                d.callback((False, "Host already in the list"))
        
        try:
            port = int(port)
        except:
            d.callback((False, "Port is invalid"))
            return d
        
        # Host isn't in the list, so lets add it
        connection_id = hashlib.sha1(str(time.time())).hexdigest()
        self.host_list["hosts"].append([connection_id, host, port, username,
            password])
        self.host_list.save()
        d.callback((True,))
        return d
    
    @export
    def remove_host(self, connection_id):
        """
        Removes a host for the list

        :param connection_Id: str, the hash id of the connection

        """
        d = Deferred()
        host = self.get_host(connection_id)
        if host is None:
            d.callback(False)
        
        self.host_list["hosts"].remove(host)
        self.host_list.save()
        d.callback(True)
        return d
