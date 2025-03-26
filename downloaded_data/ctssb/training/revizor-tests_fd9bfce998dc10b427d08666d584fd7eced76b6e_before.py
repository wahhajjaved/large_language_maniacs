import os
import time
import logging

from lettuce import world

from revizor2.api import Farm, IMPL
from revizor2.conf import CONF
from revizor2.fixtures import tables
from revizor2.consts import BEHAVIORS_ALIASES, DIST_ALIASES
from revizor2.exceptions import NotFound
from revizor2.helpers.roles import get_role_versions


from lxml import etree

LOG = logging.getLogger(__name__)


@world.absorb
def give_empty_running_farm():
    farm_id = os.environ.get('RV_FARM_ID', CONF.main.farm_id)
    world.farm = Farm.get(farm_id)
    world.farm.roles.reload()
    if len(world.farm.roles):
        IMPL.farm.clear_roles(world.farm.id)
    world.farm.vhosts.reload()
    world.farm.domains.reload()
    for vhost in world.farm.vhosts:
        LOG.info('Delete vhost: %s' % vhost.name)
        vhost.delete()
    for domain in world.farm.domains:
        LOG.info('Delete domain: %s' % domain.name)
        domain.delete()
    if world.farm.terminated:
        world.farm.launch()
    LOG.info('Return empty running farm: %s' % world.farm.id)


@world.absorb
def add_role_to_farm(behavior, options=None, scripting=None, storages=None, alias=None):
    """
    Insert role to farm by behavior and find role in Scalr by generated name.
    Role name generate by the following format:
    {behavior}{RV_ROLE_VERSION}-{RV_DIST}-{RV_ROLE_TYPE}
    Moreover if we setup environment variable RV_ROLE_ID it added role with this ID (not by name)
    """
    def get_role(behavior, dist=None):
        if CONF.feature.role_type == 'shared':
            #TODO: Try get from Scalr
            role = tables('roles-shared').filter({'dist': CONF.feature.dist,
                                                  'behavior': behavior,
                                                  'platform': CONF.feature.driver.scalr_cloud}).first()
            role = IMPL.role.get(role.keys()[0])
        else:
            if behavior in BEHAVIORS_ALIASES:
                behavior = BEHAVIORS_ALIASES[behavior]
            mask = '%s*-%s-%s' % (behavior, dist, CONF.feature.role_type)
            LOG.info('Get role versions by mask: %s' % mask)
            versions = get_role_versions(mask)
            #TODO: Return RV_ROLE_VERSION
            role_name = '%s%s-%s-%s' % (behavior, versions[0],
                                        dist, CONF.feature.role_type)
            LOG.info('Get role by name: %s' % role_name)
            roles = IMPL.role.list(query=role_name)
            if not roles:
                raise NotFound('Role with name: %s not found in Scalr' % role_name)
            role = roles[0]
        return role
    if CONF.feature.dist in DIST_ALIASES:
        dist = DIST_ALIASES[CONF.feature.dist]
    else:
        dist = CONF.feature.dist
    if CONF.feature.role_id:
        if CONF.feature.role_id.isdigit():
            role = IMPL.role.get(CONF.feature.role_id)
        else:
            roles = IMPL.role.list(query=CONF.feature.role_id)
            if roles:
                role = roles[0]
        # if not behavior in role['behaviors']: #TODO: Think about role id and behavior
        #     LOG.warning('Behavior %s not in role behaviors %s' % (behavior, role['behaviors']))
        #     role = get_role(behavior, role['dist'])
        if not role:
            raise NotFound('Role with id %s not found in Scalr, please check' % CONF.feature.role_id)
    else:
        role = get_role(behavior, dist)
    world.wrt(etree.Element('meta', name='role', value=role['name']))
    world.wrt(etree.Element('meta', name='dist', value=role['dist']))
    old_roles_id = [r.id for r in world.farm.roles]
    alias = alias or role['name']
    LOG.info('Add role %s with alias %s to farm' % (role['id'], alias))
    world.farm.add_role(role['id'], options=options, scripting=scripting, storages=storages, alias=alias)
    time.sleep(3)
    world.farm.roles.reload()
    new_role = [r for r in world.farm.roles if r.id not in old_roles_id]
    if not new_role:
        raise AssertionError('Added role "%s" not found in farm' % role.name)
    return new_role[0]