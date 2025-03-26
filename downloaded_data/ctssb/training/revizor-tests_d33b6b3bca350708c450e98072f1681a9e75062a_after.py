# coding: utf-8

"""
Created on 09.19.2014
@author: Eugeny Kurkovich
"""
import os
import logging
from lettuce import step, world
from revizor2.consts import Dist

LOG = logging.getLogger('Redis api steps')


def get_api_command_result(command):

 # Get api command result
    api_result = getattr(world, ''.join((command, '_res')))
    LOG.debug('Obtained api command {0} result: {1}'.format(
        command,
        api_result))
    return api_result


@step(r'number of redis instance is ([\d]+)')
def check_redis_instances_count(step, instances_count):
    api_result = get_api_command_result('list_processes')
    try:
        assertion_data = len(api_result.get('ports', []))
        assert (assertion_data == int(instances_count))
        LOG.debug('Number of running processes: ({0}), and expected:({1}) the same.'.format(
            assertion_data,
            instances_count
        ))
    except AssertionError:
        raise AssertionError('Number of running processes: ({0}), and expected:({1}) is not equal.'.format(
            assertion_data,
            instances_count
        ))


@step(r'redis instance ports is ([\d\,]+)')
def check_redis_instances_ports(step, instances_ports):
    api_result = get_api_command_result('list_processes')
    try:
        tested_instances_ports = [int(port.strip()) for port in instances_ports.split(',')]
        running_instances_ports = api_result.get('ports', [])
        assert all(port in tested_instances_ports for port in running_instances_ports)
        LOG.debug('Running redis processes: {0} listening to specific ports: {1}'.format(
            running_instances_ports,
            tested_instances_ports
        ))
    except AssertionError:
        raise AssertionError('Running redis processes: {0} listening to not specific ports: {1}'.format(
            running_instances_ports,
            tested_instances_ports
        ))


@step(r'([\d\,]+) redis instance is(?:\s([\w]+))? running')
def check_redis_instances_state(step, instances_ports, negation=None):
    redis_processes_states = get_api_command_result('get_service_status')
    try:
        tested_redis_processes = instances_ports.split(',')
        if not negation:
            assert all(redis_processes_states[port] == 0 for port in tested_redis_processes)
            LOG.debug('All redis processes: {0} is running'.format(tested_redis_processes))
        else:
            assert all(redis_processes_states[port] != 0 for port in tested_redis_processes)
            LOG.debug('All redis processes: {0} is not running'.format(tested_redis_processes))
    except AssertionError:
        raise AssertionError('Not all processes have the status: {0}: {1} .'.format(
            'running - (0)' if not negation else 'stoped - (3)',
            redis_processes_states))

@step(r'password for instance ([\d]+) was changed on ([\w\d]+)')
def check_instance_password(step, instance_port, serv_as):
    changed_password = get_api_command_result('reset_password')
    LOG.debug('Obtained redis instance: {0} changed_password: {1}'.format(
        instance_port,
        changed_password))
    list_processes_res = get_api_command_result('list_processes')
    stored_password = list_processes_res['passwords'][list_processes_res['ports'].index(int(instance_port))]
    LOG.debug('Obtained redis instance: {0} stored password: {1}'.format(
        instance_port,
        stored_password))
    try:
        assert (changed_password == stored_password)
        LOG.debug('Password was successfully changed for redis instance: {0}'.format(instance_port))
    except AssertionError:
        raise AssertionError('Password was not properly changed for redis instance: {0}\n'
                             'Changed password: {1} not equal stored {2}'.format(
                             instance_port,
                             changed_password,
                             stored_password))


@step(r'I write test data to ([\d]+) redis instance on ([\w\d]+)')
def write_data_to_instance(step, instance_port, serv_as):
    server = getattr(world, serv_as)
    # Get instance password
    list_processes_res = get_api_command_result('list_processes')
    password = list_processes_res['passwords'][list_processes_res['ports'].index(int(instance_port))]

    db_role = world.get_role()
    # Set credentials
    credentials = (int(instance_port), password)
    # Get connection to redis
    connection = db_role.db.get_connection(server, credentials, db=0)
    # Write data to redis instance
    try:
        connection.set(instance_port, password)
        connection.save()
        LOG.debug('Key:Value ({0}:{1}) pair was successfully set to redis instance {1} '.format(instance_port, password))
    except Exception as e:
        raise Exception(e.message)


@step(r'redis instance with port ([\d]+) has not ([\w]+) on ([\w\d]+)')
def check_instance_configs(step, instance_port, search_condition, serv_as):
    redis_path = {
        'debian':  {'conf': '/etc/redis',
                    'data': '/mnt/redisstorage'},
        'centos':  {'conf': '/etc',
                    'data': '/mnt/redisstorage'},
    }
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    # Get redis instance search condition
    if search_condition == 'configuration':
        path = redis_path.get(Dist.get_os_family(node.os[0]))['conf']
        file = 'redis.{0}.conf'.format(instance_port)
    else:
        path = redis_path.get(Dist.get_os_family(node.os[0]))['data']
        file = 'appendonly.{0}.aof'.format(instance_port)
    command = 'find {0} -name {1}'.format(path, file)
    LOG.debug('Search condition: ({0}/{1}) to find config for redis instance {2}'.format(path, file, instance_port))
    try:
        res = node.run(command)
        LOG.debug('The result: ({0}) of the find command for redis instance {1}'.format(res[0], instance_port))
        assert not (res[0])
    except AssertionError:
        raise AssertionError('Redis instance {0} config file ({1}/{2}) was not deleted.'.format(
            instance_port,
            path,
            file))
    LOG.debug('Redis instance {0} config file ({1}/{2}) was successfully deleted.'.format(
        instance_port,
        path,
        file))

@step(r'I read from ([\d]+) redis instance, and test data exists on ([\w\d]+)')
def read_data_from_instance(step, instance_port, serv_as):
    server = getattr(world, serv_as)
    # Get instance password
    list_processes_res = get_api_command_result('list_processes')
    password = list_processes_res['passwords'][list_processes_res['ports'].index(int(instance_port))]

    db_role = world.get_role()
    # Set credentials
    credentials = (int(instance_port), password)
    # Get connection to redis
    connection = db_role.db.get_connection(server, credentials, db=0)
    # Write data to redis instance
    try:
        res = connection.get(instance_port)
        LOG.debug('Test data: ({0}) was successfully get from redis instance {1}'.format(res, instance_port))
        assert (res == password)
    except Exception as e:
        if isinstance(e, AssertionError):
            e.message = 'Test data received from the server: ({0}) do not match written: ({1})'.format(
                res,
                password)
        raise type(e)(e.message)
    LOG.debug('The data obtained from redis instance: ({1}) and are relevant: ({0}).'.format(res, instance_port))