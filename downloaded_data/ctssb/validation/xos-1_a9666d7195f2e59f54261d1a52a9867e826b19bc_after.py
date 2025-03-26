import hashlib
import os
import socket
import sys
import base64
import time
from django.db.models import F, Q
from xos.config import Config
from observer.syncstep import SyncStep
from observer.ansible import run_template_ssh
from core.models import Service, Slice, ControllerSlice, ControllerUser
from util.logger import Logger, logging

logger = Logger(level=logging.INFO)

class SyncInstanceUsingAnsible(SyncStep):
    # All of the following should be defined for classes derived from this
    # base class. Examples below use VCPETenant.

    # provides=[VCPETenant]
    # observes=VCPETenant
    # requested_interval=0
    # template_name = "sync_vcpetenant.yaml"
    # service_key_name = "/opt/xos/observers/vcpe/vcpe_private_key"

    def __init__(self, **args):
        SyncStep.__init__(self, **args)

    def defer_sync(self, o, reason):
        logger.info("defer object %s due to %s" % (str(o), reason))
        raise Exception("defer object %s due to %s" % (str(o), reason))

    def get_extra_attributes(self, o):
        # This is a place to include extra attributes that aren't part of the
        # object itself.

        return {}

    def get_instance(self, o):
        # We need to know what instance is associated with the object. Let's
        # assume 'o' has a field called 'instance'. If the field is called
        # something else, or if custom logic is needed, then override this
        # method.

        return o.instance

    def run_playbook(self, o, fields, template_name=None):
        if not template_name:
            template_name = self.template_name
        tStart = time.time()
        run_template_ssh(template_name, fields)
        logger.info("playbook execution time %d" % int(time.time()-tStart))

    def pre_sync_hook(self, o, fields):
        pass

    def post_sync_hook(self, o, fields):
        pass

    def sync_fields(self, o, fields):
        self.run_playbook(o, fields)

    def prepare_record(self, o):
        pass

    def get_node(self,o):
        return o.node

    def get_node_key(self, node):
        return "/root/setup/node_key"

    def get_ansible_fields(self, instance):
        # return all of the fields that tell Ansible how to talk to the context
        # that's setting up the container.

        if (instance.isolation == "vm"):
            # legacy where container was configured by sync_vcpetenant.py

            fields = { "instance_name": instance.name,
                       "hostname": instance.node.name,
                       "instance_id": instance.instance_id,
                       "username": "ubuntu",
                     }
            key_name = self.service_key_name
        elif (instance.isolation == "container"):
            # container on bare metal
            node = self.get_node(instance)
            hostname = node.name
            fields = { "hostname": hostname,
                       "baremetal_ssh": True,
                       "instance_name": "rootcontext",
                       "username": "root",
                     }
            key_name = self.get_node_key(node)
        else:
            # container in a VM
            if not instance.parent:
                raise Exception("Container-in-VM has no parent")
            if not instance.parent.instance_id:
                raise Exception("Container-in-VM parent is not yet instantiated")
            if not instance.parent.slice.service:
                raise Exception("Container-in-VM parent has no service")
            if not instance.parent.slice.service.private_key_fn:
                raise Exception("Container-in-VM parent service has no private_key_fn")
            fields = { "hostname": instance.parent.node.name,
                       "instance_name": instance.parent.name,
                       "instance_id": instance.parent.instance_id,
                       "username": "ubuntu",
                       "nat_ip": instance.parent.get_ssh_ip(),
                         }
            key_name = instance.parent.slice.service.private_key_fn

        if not os.path.exists(key_name):
            raise Exception("Node key %s does not exist" % node_key_name)

        key = file(key_name).read()

        fields["private_key"] = key

        # now the ceilometer stuff

        cslice = ControllerSlice.objects.get(slice=instance.slice)
        if not cslice:
            raise Exception("Controller slice object for %s does not exist" % instance.slice.name)

        cuser = ControllerUser.objects.get(user=instance.creator)
        if not cuser:
            raise Exception("Controller user object for %s does not exist" % instance.creator)

        fields.update({"keystone_tenant_id": cslice.tenant_id,
                       "keystone_user_id": cuser.kuser_id,
                       "rabbit_user": instance.controller.rabbit_user,
                       "rabbit_password": instance.controller.rabbit_password,
                       "rabbit_host": instance.controller.rabbit_host})

        return fields

    def sync_record(self, o):
        logger.info("sync'ing object %s" % str(o))

        self.prepare_record(o)

        instance = self.get_instance(o)

        if isinstance(instance, basestring):
            # sync to some external host

            # XXX - this probably needs more work...

            fields = { "hostname": instance,
                       "instance_id": "ubuntu",     # this is the username to log into
                       "private_key": service.key,
                     }
        else:
            # sync to an XOS instance
            if not instance:
                self.defer_sync(o, "waiting on instance")
                return

            if not instance.instance_name:
                self.defer_sync(o, "waiting on instance.instance_name")
                return

            fields = self.get_ansible_fields(instance)

            fields["ansible_tag"] =  o.__class__.__name__ + "_" + str(o.id)

        # If 'o' defines a 'sync_attributes' list, then we'll copy those
        # attributes into the Ansible recipe's field list automatically.
        if hasattr(o, "sync_attributes"):
            for attribute_name in o.sync_attributes:
                fields[attribute_name] = getattr(o, attribute_name)

        fields.update(self.get_extra_attributes(o))

        self.sync_fields(o, fields)

        o.save()

    def delete_record(self, m):
        pass

