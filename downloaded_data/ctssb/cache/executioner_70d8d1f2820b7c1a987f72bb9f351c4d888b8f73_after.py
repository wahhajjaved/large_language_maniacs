import json
import os

from twisted.internet.threads import deferToThread
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET

from ansible import utils
from ansible.inventory import Inventory
import ansible.runner


def jsonify(request, ret):
    """
    Helper function to return json api response
    """
    request.setHeader('Content-Type', 'application/json')
    return json.dumps(ret)


def error_page(request):
    request.setResponseCode(500)
    return "Internal server error"


class ExecutionerApiHandler(Resource):
    """
    Class to process all requests coming to the api.

    """
    isLeaf = False

    def __init__(self):
        Resource.__init__(self)
        #  Add resource types
        self.putChild('runcommand', RunCommandHandler())
        self.putChild('modules', ModuleHandler())
        self.putChild("inventory", InventoryHandler())
        self.putChild("", self)

    def render_GET(self, request):
        """
        Render list all resource types as json
        """
        ret = {"resourcetypes": [ \
            {"inventory":"/api/inventory"}, \
            {"modules":"/api/modules"},  \
            {"modules":"/api/runcommand"}  \
          ]}
        return jsonify(request, ret)


class InventoryHandler(Resource):
    """
      Renders in json list of hosts and groups from configured ansible
      inventory file.
    """

    isLeaf = True

    def render_GET(self, request):
        i = Inventory()
        inv = []
        try:
            hosts = i.get_hosts()
            groups = i.get_groups()
        except:
            return self.error_page(request)
        inv.extend([{"name": x.name, "type":"host"} for x in sorted(hosts)])
        inv.extend([{"name": x.name, "type":"group"} for x in sorted(groups)])
        return jsonify(request, inv)


class ModuleHandler(Resource):
    """
      Renders in json all the ansible modules.
    """

    isLeaf = True

    def render_GET(self, request):
        module_paths = utils.plugins.module_finder._get_paths()
        modules = set()
        for path in module_paths:
            if os.path.isdir(path):
                fs = os.listdir(path)
                modules = modules.union(fs)
        ret = [{"name":x} for x in sorted(modules)]
        return jsonify(request, ret)


class RunCommandHandler(Resource):
    """
     Runs ansible commands and renders the output as json.
     Long lasting jobs may cause timeout (TODO: test if it happens).
    """
    isLeaf = True

    def render_GET(self, request):
        host = self._get_argument(request, "host")
        module = self._get_argument(request, "module")
        attr = self._get_argument(request, "attr")
        d = deferToThread(self.runAnsibleCmd, request, host=host, module=module, attr=attr)
        d.addCallback(self._callback, request=request)
        d.addErrback(self._errback, request=request)
        return NOT_DONE_YET

    def runAnsibleCmd(self, request, host="", module="", attr=""):
        runner = ansible.runner.Runner(
           module_name=module,
           module_args=attr,
           pattern=host,
           forks=10
        )
        data = runner.run()
        return data

    def _callback(self, data, request=None):
        request.write(jsonify(request, {"runresult": data}))
        request.finish()
        return

    def _errback(self, data, request=None):
        request.write(jsonify(request, error_page(request)))
        request.finish()
        return

    def _get_argument(self, request, name, default=""):
        try:
            arg = request.args[name]
            if len(arg) == 0:
                return default
            arg = arg[0]
        except:
            return default
        return arg

