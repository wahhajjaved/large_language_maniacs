# -*- coding: utf-8 -*-
# Copyright 2018 GIG Technology NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @@license_version:1.4@@
import logging
import re
from datetime import datetime

from google.appengine.api import users
from google.appengine.ext import ndb
from google.appengine.ext.deferred import deferred

import influxdb
from dateutil.relativedelta import relativedelta
from framework.bizz.job import run_job, MODE_BATCH
from framework.plugin_loader import get_config
from framework.utils import now
from mcfw.consts import MISSING, DEBUG
from mcfw.exceptions import HttpNotFoundException, HttpBadRequestException
from mcfw.rpc import returns, arguments
from plugins.its_you_online_auth.bizz.profile import get_profile
from plugins.its_you_online_auth.models import Profile
from plugins.rogerthat_api.api import system
from plugins.rogerthat_api.exceptions import BusinessException
from plugins.rogerthat_api.to import UserDetailsTO
from plugins.tff_backend.bizz import get_rogerthat_api_key
from plugins.tff_backend.bizz.authentication import RogerthatRoles
from plugins.tff_backend.bizz.iyo.utils import get_iyo_username
from plugins.tff_backend.bizz.messages import send_message_and_email
from plugins.tff_backend.bizz.odoo import get_nodes_from_odoo, get_serial_number_by_node_id
from plugins.tff_backend.bizz.service import add_user_to_role, remove_user_from_role
from plugins.tff_backend.bizz.todo import update_hoster_progress, HosterSteps
from plugins.tff_backend.bizz.user import get_tff_profile
from plugins.tff_backend.configuration import InfluxDBConfig
from plugins.tff_backend.models.hoster import NodeOrder, NodeOrderStatus
from plugins.tff_backend.models.nodes import Node, NodeStatus, NodeChainStatus
from plugins.tff_backend.models.user import TffProfile
from plugins.tff_backend.plugin_consts import NAMESPACE
from plugins.tff_backend.to.nodes import UpdateNodePayloadTO, UpdateNodeStatusTO
from plugins.tff_backend.utils.app import get_app_user_tuple

SKIPPED_STATS_KEYS = ['disk.size.total']
NODE_ID_REGEX = re.compile('([a-f0-9]{12})')


def check_online_nodes():
    run_job(_get_node_orders, [], check_if_node_comes_online, [])


def _get_node_orders():
    return NodeOrder.list_check_online()


def check_if_node_comes_online(order_key):
    order = order_key.get()  # type: NodeOrder
    order_id = order.id
    if not order.odoo_sale_order_id:
        raise BusinessException('Cannot check status of node order without odoo_sale_order_id')
    odoo_nodes = get_nodes_from_odoo(order.odoo_sale_order_id)
    odoo_node_keys = [Node.create_key(n['id']) for n in odoo_nodes]
    if not odoo_nodes:
        raise BusinessException('Could not find nodes for sale order %s on odoo' % order_id)
    statuses = {n.id: n.status for n in ndb.get_multi(odoo_node_keys) if n}
    iyo_username = get_iyo_username(order.app_user)
    user_nodes = {node.id: node for node in Node.list_by_user(iyo_username)}
    to_add = []
    logging.debug('odoo_nodes: %s\n statuses: %s\n', odoo_nodes, statuses)
    for node in odoo_nodes:
        if node['id'] not in user_nodes:
            to_add.append(node)
    if to_add:
        logging.info('Setting username %s on nodes %s', iyo_username, to_add)
        deferred.defer(assign_nodes_to_user, iyo_username, to_add)
    if all([status == NodeStatus.RUNNING for status in statuses.itervalues()]):
        _set_node_status_arrived(order_key, odoo_nodes)
    else:
        logging.info('Nodes %s from order %s are not all online yet', odoo_nodes, order_id)


@ndb.transactional()
def _set_node_status_arrived(order_key, nodes):
    order = order_key.get()
    logging.info('Marking nodes %s from node order %s as arrived', nodes, order_key)
    human_user, app_id = get_app_user_tuple(order.app_user)
    order.populate(arrival_time=now(),
                   status=NodeOrderStatus.ARRIVED)
    order.put()
    deferred.defer(update_hoster_progress, human_user.email(), app_id, HosterSteps.NODE_POWERED,
                   _transactional=True)


@ndb.transactional(xg=True)
@returns([Node])
@arguments(iyo_username=unicode, nodes=[dict])
def assign_nodes_to_user(iyo_username, nodes):
    existing_nodes = {node.id: node for node in ndb.get_multi([Node.create_key(node['id']) for node in nodes]) if node}
    to_put = []
    for new_node in nodes:
        node = existing_nodes.get(new_node['id'])
        if node:
            node.username = iyo_username
            node.serial_number = new_node['serial_number']
            to_put.append(node)
        else:
            to_put.append(Node(key=Node.create_key(new_node['id']),
                               serial_number=new_node['serial_number'],
                               username=iyo_username))
    ndb.put_multi(to_put)
    deferred.defer(_put_node_status_user_data, TffProfile.create_key(iyo_username), _countdown=5)
    return to_put


def get_nodes_for_user(app_user):
    # type: (users.User) -> list[dict]
    nodes = []
    for order in NodeOrder.list_by_user(app_user):
        if order.status in (NodeOrderStatus.SENT, NodeOrderStatus.ARRIVED):
            nodes.extend(get_nodes_from_odoo(order.odoo_sale_order_id))
    return nodes


def check_offline_nodes():
    date = datetime.now() - relativedelta(minutes=20)
    run_job(_get_offline_nodes, [date], _handle_offline_nodes, [date], mode=MODE_BATCH, batch_size=25,
            qry_transactional=False)


def _get_offline_nodes(date):
    return Node.list_running_by_last_update(date)


@ndb.transactional(xg=True)
def _handle_offline_nodes(node_keys, date):
    # type: (list[ndb.Key], datetime) -> None
    # No more than 25 node_keys should be supplied to this function (max nr of entity groups in a single transaction)
    nodes = ndb.get_multi(node_keys)  # type: list[Node]
    to_notify = []  # type: list[dict]
    # List of usernames
    to_update = set()  # type: set[unicode]
    for node in nodes:
        node.status = NodeStatus.HALTED
        node.status_date = date
        if node.username:
            to_update.add(node.username)
            to_notify.append({'u': node.username,
                              'sn': node.serial_number,
                              'date': date,
                              'status': NodeStatus.HALTED})
    ndb.put_multi(nodes)
    if to_update or to_notify:
        deferred.defer(after_check_node_status, to_update, to_notify, _transactional=True, _countdown=5)


def save_node_statuses():
    points = []
    date = datetime.now()
    # Round to 5 minutes to always have consistent results
    date = date - relativedelta(minutes=date.minute % 5, seconds=date.second, microseconds=date.microsecond)
    timestamp = date.isoformat() + 'Z'
    for node in Node.query(projection=[Node.status]):
        points.append({
            'measurement': 'node-info',
            'tags': {
                'node_id': node.id,
                'status': node.status,
            },
            'time': timestamp,
            'fields': {
                'id': node.id
            }
        })
    client = get_influx_client()
    if client:
        client.write_points(points, time_precision='m')


def after_check_node_status(to_update, to_notify):
    # type: (set[unicode], list[dict]) -> None
    for obj in to_notify:
        logging.info('Sending node status update message to %s. Status: %s', obj['u'], obj['status'])
        deferred.defer(_send_node_status_update_message, obj['u'], obj['status'], obj['date'], obj['sn'])
    for username in to_update:
        deferred.defer(_put_node_status_user_data, TffProfile.create_key(username))


def _put_node_status_user_data(tff_profile_key):
    tff_profile = tff_profile_key.get()
    user, app_id = get_app_user_tuple(tff_profile.app_user)
    data = {'nodes': [n.to_dict() for n in Node.list_by_user(tff_profile.username)]}
    system.put_user_data(get_rogerthat_api_key(), user.email(), app_id, data)
    if not data['nodes']:
        user_detail = UserDetailsTO(email=user.email(), app_id=app_id)
        deferred.defer(remove_user_from_role, user_detail, RogerthatRoles.HOSTERS)


def _send_node_status_update_message(username, to_status, date, serial_number):
    profile = get_tff_profile(username)
    app_user = profile.app_user
    date_str = date.strftime('%Y-%m-%d %H:%M:%S')
    if to_status == NodeStatus.HALTED:
        subject = u'Connection to your node(%s) has been lost since %s UTC' % (serial_number, date_str)
        msg = u'Dear ThreeFold Member,\n\n' \
              u'Connection to your node(%s) has been lost since %s UTC.' \
              u' Please check the network connection of your node.\n' \
              u'Kind regards,\n' \
              u'The ThreeFold Team' % (serial_number, date_str)
    elif to_status == NodeStatus.RUNNING:
        subject = u'Connection to your node(%s) has been resumed since %s UTC' % (serial_number, date_str)
        msg = u'Dear ThreeFold Member,\n\n' \
              u'Congratulations!' \
              u' Your node(%s) is now successfully connected to our system, and has been resumed since %s UTC.\n' \
              u'Kind regards,\n' \
              u'The ThreeFold Team' % (serial_number, date_str)
    else:
        logging.debug(
            "_send_node_status_update_message not sending message for status '%s' => '%s'", to_status)
        return

    send_message_and_email(app_user, msg, subject)


def _get_limited_profile(profile):
    if not profile:
        return None
    assert isinstance(profile, Profile)
    return {
        'username': profile.username,
        'full_name': profile.full_name,
        'email': profile.email,
    }


def list_nodes_by_status(status=None):
    # type: (unicode) -> list[dict]
    if status:
        qry = Node.list_by_status(status)
    else:
        qry = Node.query()
    nodes = qry.fetch()  # type: list[Node]
    profiles = {profile.username: profile for profile in
                ndb.get_multi([Profile.create_key(node.username) for node in nodes if node.username])}
    include_node = ['status', 'serial_number', 'chain_status']
    results = [{'profile': _get_limited_profile(profiles.get(node.username)),
                'node': node.to_dict(include=include_node)} for node in nodes]
    return sorted(results, key=lambda k: (k['profile']['full_name']) if k['profile'] else k['node']['id'])


@ndb.transactional()
def _set_serial_number_on_node(node_id):
    node = Node.create_key(node_id).get()
    node.serial_number = get_serial_number_by_node_id(node_id)
    if node.serial_number:
        node.put()
    return node


def get_node(node_id):
    # type: (unicode) -> Node
    node = Node.create_key(node_id).get()
    if not node:
        raise HttpNotFoundException('node_not_found', {'id': node_id})
    return node


@ndb.transactional(xg=True)
def update_node(node_id, data):
    # type: (unicode, UpdateNodePayloadTO) -> Node
    node = get_node(node_id)
    if data.username:
        profile = get_profile(data.username)
        if profile.app_email:
            email, app_id = get_app_user_tuple(users.User(profile.app_email))
            user_details = UserDetailsTO(email=email.email(), app_id=app_id)
            deferred.defer(add_user_to_role, user_details, RogerthatRoles.HOSTERS, _transactional=True)
    node.username = data.username
    node.put()
    return node


@ndb.transactional()
def delete_node(node_id):
    # type: (unicode) -> None
    node = get_node(node_id)
    if node.username:
        deferred.defer(_put_node_status_user_data, TffProfile.create_key(node.username), _transactional=True,
                       _countdown=5)
    node.key.delete()
    client = get_influx_client()
    if client:
        client.query('DELETE FROM "node-stats" WHERE ("id" = \'%(id)s\');'
                     'DELETE FROM "node-info" WHERE ("node_id" = \'%(id)s\')' % {'id': node_id})


def _validate_node_id(node_id):
    if len(node_id) != 12 or not NODE_ID_REGEX.match(node_id):
        raise HttpBadRequestException('invalid_node_id')


@ndb.transactional()
def _save_node_stats(node_id, data, date):
    # type: (unicode, UpdateNodeStatusTO, datetime) -> None
    node_key = Node.create_key(node_id)
    node = node_key.get()
    if not node:
        node = Node(key=node_key,
                    status_date=date)
        deferred.defer(_set_serial_number_on_node, node_id, _transactional=True)
    if data.chain_status and data.chain_status is not MISSING:
        if not node.chain_status:
            node.chain_status = NodeChainStatus()
        node.chain_status.populate(**data.chain_status.to_dict())
    if node.status != NodeStatus.RUNNING and node.username:
        deferred.defer(_put_node_status_user_data, TffProfile.create_key(node.username), _transactional=True)
        deferred.defer(_send_node_status_update_message, node.username, NodeStatus.RUNNING, date, node.serial_number,
                       _transactional=True)
    if data.info and data.info is not MISSING:
        node.info = data.info
    node.populate(last_update=date,
                  status=NodeStatus.RUNNING)
    node.put()


def save_node_stats(node_id, data, date):
    # type: (unicode, UpdateNodeStatusTO, datetime) -> None
    _validate_node_id(node_id)
    _save_node_stats(node_id, data, date)
    if data.stats and data.stats is not MISSING:
        _save_node_stats_to_influx(node_id, data.stats)


def _save_node_stats_to_influx(node_id, stats):
    # type: (unicode, dict) -> None
    points = []
    for stat_key, values in stats.iteritems():
        stat_key_split = stat_key.split('/')
        if stat_key_split[0] in SKIPPED_STATS_KEYS:
            continue
        tags = {
            'id': node_id,
            'type': stat_key_split[0],
        }
        if len(stat_key_split) == 2:
            tags['subtype'] = stat_key_split[1]
        for values_on_time in values:
            points.append({
                'measurement': 'node-stats',
                'tags': tags,
                'time': datetime.utcfromtimestamp(values_on_time['start']).isoformat() + 'Z',
                'fields': {
                    'max': float(values_on_time['max']),
                    'avg': float(values_on_time['avg'])
                }
            })
    logging.info('Writing %s datapoints to influxdb for node %s', len(points), node_id)
    client = get_influx_client()
    if client and points:
        client.write_points(points)


def get_influx_client():
    config = get_config(NAMESPACE).influxdb  # type: InfluxDBConfig
    if config is MISSING or (DEBUG and 'localhost' not in config.host):
        return None
    return influxdb.InfluxDBClient(config.host, config.port, config.username, config.password, config.database,
                                   config.ssl, config.ssl)


def get_nodes_stats_from_influx(nodes):
    # type: (list[Node]) -> list[dict]
    client = get_influx_client()
    if not client:
        return []
    stats_per_node = {node.id: dict(stats=[], **node.to_dict()) for node in nodes}
    stat_types = (
        'machine.CPU.percent', 'machine.memory.ram.available', 'network.throughput.incoming',
        'network.throughput.outgoing')
    queries = []
    hours_ago = 6
    statements = []  # type: list[tuple]
    for node in nodes:
        for stat_type in stat_types:
            qry = """SELECT mean("avg") FROM "node-stats" WHERE ("type" = '%(type)s' AND "id" = '%(node_id)s') AND time >= now() - %(hours)dh GROUP BY time(15m)""" % {
                'type': stat_type, 'node_id': node.id, 'hours': hours_ago}
            statements.append((node, stat_type))
            queries.append(qry)
    query_str = ';'.join(queries)
    logging.debug(query_str)
    result_sets = client.query(query_str)
    for statement_id, (node, stat_type) in enumerate(statements):
        for result_set in result_sets:
            if result_set.raw['statement_id'] == statement_id:
                stats_per_node[node.id]['stats'].append({
                    'type': stat_type,
                    'data': result_set.raw.get('series', [])
                })
    return stats_per_node.values()
