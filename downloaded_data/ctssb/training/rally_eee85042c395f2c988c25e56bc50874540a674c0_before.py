# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from rally.common.i18n import _
from rally.common import logging
from rally.common import utils as rutils
from rally.common import validation
from rally import osclients
from rally.plugins.openstack.cleanup import manager as resource_manager
from rally.plugins.openstack.scenarios.nova import utils as nova_utils
from rally.plugins.openstack import types
from rally.task import context


LOG = logging.getLogger(__name__)


@validation.add("required_platform", platform="openstack", users=True)
@context.configure(name="servers", order=430)
class ServerGenerator(context.Context):
    """Context class for adding temporary servers for benchmarks.

    Servers are added for each tenant.
    """

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "image": {
                "description": "Name of image to boot server(s) from.",
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                }
            },
            "flavor": {
                "description": "Name of flavor to boot server(s) with.",
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                }
            },
            "servers_per_tenant": {
                "description": "Number of servers to boot in each Tenant.",
                "type": "integer",
                "minimum": 1
            },
            "auto_assign_nic": {
                "description": "True if NICs should be assigned.",
                "type": "boolean",
            },
            "nics": {
                "type": "array",
                "description": "List of networks to attach to server.",
                "items": {"oneOf": [
                    {"type": "object",
                     "properties": {"net-id": {"type": "string"}},
                     "description": "Network ID in a format like OpenStack API"
                                    " expects to see."},
                    {"type": "string", "description": "Network ID."}]},
                "minItems": 1
            }
        },
        "required": ["image", "flavor"],
        "additionalProperties": False
    }

    DEFAULT_CONFIG = {
        "servers_per_tenant": 5,
        "auto_assign_nic": False
    }

    @logging.log_task_wrapper(LOG.info, _("Enter context: `Servers`"))
    def setup(self):
        image = self.config["image"]
        flavor = self.config["flavor"]
        auto_nic = self.config["auto_assign_nic"]
        servers_per_tenant = self.config["servers_per_tenant"]
        kwargs = {}
        if self.config.get("nics"):
            if isinstance(self.config["nics"][0], dict):
                # it is a format that Nova API expects
                kwargs["nics"] = self.config["nics"]
            else:
                kwargs["nics"] = [{"net-id": nic}
                                  for nic in self.config["nics"]]

        clients = osclients.Clients(self.context["users"][0]["credential"])
        image_id = types.GlanceImage.transform(clients=clients,
                                               resource_config=image)
        flavor_id = types.Flavor.transform(clients=clients,
                                           resource_config=flavor)

        for iter_, (user, tenant_id) in enumerate(rutils.iterate_per_tenants(
                self.context["users"])):
            LOG.debug("Booting servers for user tenant %s "
                      % (user["tenant_id"]))
            tmp_context = {"user": user,
                           "tenant": self.context["tenants"][tenant_id],
                           "task": self.context["task"],
                           "owner_id": self.context["owner_id"],
                           "iteration": iter_}
            nova_scenario = nova_utils.NovaScenario(tmp_context)

            LOG.debug("Calling _boot_servers with image_id=%(image_id)s "
                      "flavor_id=%(flavor_id)s "
                      "servers_per_tenant=%(servers_per_tenant)s"
                      % {"image_id": image_id,
                         "flavor_id": flavor_id,
                         "servers_per_tenant": servers_per_tenant})

            servers = nova_scenario._boot_servers(image_id, flavor_id,
                                                  requests=servers_per_tenant,
                                                  auto_assign_nic=auto_nic,
                                                  **kwargs)

            current_servers = [server.id for server in servers]

            LOG.debug("Adding booted servers %s to context"
                      % current_servers)

            self.context["tenants"][tenant_id][
                "servers"] = current_servers

    @logging.log_task_wrapper(LOG.info, _("Exit context: `Servers`"))
    def cleanup(self):
        resource_manager.cleanup(names=["nova.servers"],
                                 users=self.context.get("users", []),
                                 superclass=nova_utils.NovaScenario,
                                 task_id=self.get_owner_id())
