#!/usr/bin/python
#
# (c) 2019 Piotr Wojciechowski <piotr@it-playground.pl>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: docker_host_facts

short_description: Retrieves facts about docker host and lists of objects of the services.

description:
  - Retrieves facts about a docker host.
  - Essentially returns the output of C(docker system info).
  - The module also allows to list object names for containers, images, networks and volumes.
    It also allows to query information on disk usage.
  - The output differs depending on API version of the docker daemon.
  - If the docker daemon cannot be contacted or does not meet the API version requirements,
    the module will fail.

version_added: "2.8"

options:
  containers:
    description:
      - Whether to list containers.
    type: bool
    default: no
  containers_filters:
    description:
      - A dictionary of filter values used for selecting containers to delete.
      - "For example, C(until: 24h)."
      - See L(the docker documentation,https://docs.docker.com/engine/reference/commandline/container_prune/#filtering)
        for more information on possible filters.
    type: dict
  images:
    description:
      - Whether to list images.
    type: bool
    default: no
  images_filters:
    description:
      - A dictionary of filter values used for selecting images to delete.
      - "For example, C(dangling: true)."
      - See L(the docker documentation,https://docs.docker.com/engine/reference/commandline/image_prune/#filtering)
        for more information on possible filters.
    type: dict
  networks:
    description:
      - Whether to list networks.
    type: bool
    default: no
  networks_filters:
    description:
      - A dictionary of filter values used for selecting networks to delete.
      - See L(the docker documentation,https://docs.docker.com/engine/reference/commandline/network_prune/#filtering)
        for more information on possible filters.
    type: dict
  volumes:
    description:
      - Whether to list volumes.
    type: bool
    default: no
  volumes_filters:
    description:
      - A dictionary of filter values used for selecting volumes to delete.
      - See L(the docker documentation,https://docs.docker.com/engine/reference/commandline/volume_prune/#filtering)
        for more information on possible filters.
    type: dict
  disk_usage:
    description:
      - Summary information on used disk space by all Docker layers.
      - The output is a sum of images, volumes, containers and build cache.
    type: bool
    default: no
  verbose_output:
    description:
      - When set to C(yes) and I(networks), I(volumes), I(images), I(containers) or I(disk_usage) is set to C(yes)
        then output will contain verbose information about objects matching the full output of API method.
        For details see the documentation of your version of Docker API at L(https://docs.docker.com/engine/api/).
      - The verbose output in this module contains only subset of information returned by I(_facts) module
        for each type of the objects.
    type: bool
    default: no
extends_documentation_fragment:
  - docker
  - docker.docker_py_1_documentation

author:
  - Piotr Wojciechowski (@WojciechowskiPiotr)

requirements:
  - "docker-py >= 1.10.0"
  - "Docker API >= 1.21"
'''

EXAMPLES = '''
- name: Get info on docker host
  docker_host_facts:
  register: result

- name: Get info on docker host and list images
  docker_host_facts:
    images: yes
  register: result

- name: Get info on docker host and list images matching the filter
  docker_host_facts:
    images: yes
    images_filters:
      label: "mylabel"
  register: result

- name: Get info on docker host and verbose list images
  docker_host_facts:
    images: yes
    verbose_output: yes
  register: result

- name: Get info on docker host and used disk space
  docker_host_facts:
    disk_usage: yes
  register: result

- debug:
    var: result.docker_host_facts

'''

RETURN = '''
can_talk_to_docker:
    description:
      - Will be C(true) if the module can talk to the docker daemon.
    returned: both on success and on error
    type: bool

docker_host_facts:
    description:
      - Facts representing the basic state of the docker host. Matches the C(docker system info) output.
    returned: always
    type: dict
docker_volumes_list:
    description:
      - List of dict objects containing the basic information about each volume.
        Keys matches the C(docker volume ls) output unless I(verbose_output=yes).
        See description for I(verbose_output).
    returned: When I(volumes) is C(yes)
    type: list
docker_networks_list:
    description:
      - List of dict objects containing the basic information about each network.
        Keys matches the C(docker network ls) output unless I(verbose_output=yes).
        See description for I(verbose_output).
    returned: When I(networks) is C(yes)
    type: list
docker_containers_list:
    description:
      - List of dict objects containing the basic information about each container.
        Keys matches the C(docker container ls) output unless I(verbose_output=yes).
        See description for I(verbose_output).
    returned: When I(containers) is C(yes)
    type: list
docker_images_list:
    description:
      - List of dict objects containing the basic information about each image.
        Keys matches the C(docker image ls) output unless I(verbose_output=yes).
        See description for I(verbose_output).
    returned: When I(images) is C(yes)
    type: list
docker_disk_usage:
    description:
      - Information on summary disk usage by images, containers and volumes on docker host
        unless I(verbose_output=yes). See description for I(verbose_output).
    returned: When I(disk_usage) is C(yes)
    type: dict

'''

from ansible.module_utils.docker.common import AnsibleDockerClient, DockerBaseClass
from ansible.module_utils._text import to_native

try:
    from docker.errors import APIError
except ImportError:
    # missing docker-py handled in ansible.module_utils.docker.common
    pass

from ansible.module_utils.docker.common import clean_dict_booleans_for_docker_api


class DockerHostManager(DockerBaseClass):

    def __init__(self, client, results):

        super(DockerHostManager, self).__init__()

        self.client = client
        self.results = results
        self.verbose_output = self.client.module.params['verbose_output']

        listed_objects = ['volumes', 'networks', 'containers', 'images']

        self.results['docker_host_facts'] = self.get_docker_host_facts()

        if self.client.module.params['disk_usage']:
            self.results['docker_disk_usage'] = self.get_docker_disk_usage_facts()

        for docker_object in listed_objects:
            if self.client.module.params[docker_object]:
                returned_name = "docker_" + docker_object + "_list"
                filter_name = docker_object + "_filters"
                filters = clean_dict_booleans_for_docker_api(client.module.params.get(filter_name))
                self.results[returned_name] = self.get_docker_items_list(docker_object, filters)

    def get_docker_host_facts(self):
        try:
            return self.client.info()
        except APIError as exc:
            self.client.fail("Error inspecting docker host: %s" % to_native(exc))

    def get_docker_disk_usage_facts(self):
        try:
            if self.verbose_output:
                return self.client.df()
            else:
                return dict(LayerSize=self.client.df()['LayersSize'])
        except APIError as exc:
            self.client.fail("Error inspecting docker host: %s" % to_native(exc))

    def get_docker_items_list(self, docker_object=None, filters=None, verbose=False):
        items = None
        items_list = []

        header_containers = ['Id', 'Image', 'Command', 'Created', 'Status', 'Ports', 'Names']
        header_volumes = ['Driver', 'Name']
        header_images = ['Id', 'RepoTags', 'Created', 'Size']
        header_networks = ['Id', 'Driver', 'Name', 'Scope']

        try:
            if docker_object == 'containers':
                items = self.client.containers(filters=filters)
            elif docker_object == 'networks':
                items = self.client.networks(filters=filters)
            elif docker_object == 'images':
                items = self.client.images(filters=filters)
            elif docker_object == 'volumes':
                items = self.client.volumes(filters=filters)
        except APIError as exc:
            self.client.fail("Error inspecting docker host for object '%s': %s" %
                             (docker_object, to_native(exc)))

        if self.verbose_output:
            if docker_object != 'volumes':
                return items
            else:
                return items['Volumes']

        if docker_object == 'volumes':
            items = items['Volumes']

        for item in items:
            item_record = dict()

            if docker_object == 'containers':
                for key in header_containers:
                    item_record[key] = item.get(key)
            elif docker_object == 'networks':
                for key in header_networks:
                    item_record[key] = item.get(key)
            elif docker_object == 'images':
                for key in header_images:
                    item_record[key] = item.get(key)
            elif docker_object == 'volumes':
                for key in header_volumes:
                    item_record[key] = item.get(key)
            items_list.append(item_record)

        return items_list


def main():
    argument_spec = dict(
        containers=dict(type='bool', default=False),
        containers_filters=dict(type='dict'),
        images=dict(type='bool', default=False),
        images_filters=dict(type='dict'),
        networks=dict(type='bool', default=False),
        networks_filters=dict(type='dict'),
        volumes=dict(type='bool', default=False),
        volumes_filters=dict(type='dict'),
        disk_usage=dict(type='bool', default=False),
        verbose_output=dict(type='bool', default=False),
    )

    client = AnsibleDockerClient(
        argument_spec=argument_spec,
        supports_check_mode=True,
        min_docker_version='1.10.0',
        min_docker_api_version='1.21',
        fail_results=dict(
            can_talk_to_docker=False,
        ),
    )
    client.fail_results['can_talk_to_docker'] = True

    results = dict(
        changed=False,
        docker_host_facts=[]
    )

    DockerHostManager(client, results)
    client.module.exit_json(**results)


if __name__ == '__main__':
    main()
