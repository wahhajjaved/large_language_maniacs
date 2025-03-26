"""This module provides the HaaS service's public API.

TODO: Spec out and document what sanitization is required.
"""
from flask import Flask, request
from functools import wraps
import inspect
import importlib

from haas import model
from haas.config import cfg


class APIError(Exception):
    """An exception indicating an error that should be reported to the user.

    i.e. If such an error occurs in a rest API call, it should be reported as
    part of the HTTP response.
    """


class NotFoundError(APIError):
    """An exception indicating that a given resource does not exist."""


class DuplicateError(APIError):
    """An exception indicating that a given resource already exists."""


class AllocationError(APIError):
    """An exception indicating resource exhaustion."""


class BadArgumentError(APIError):
    """An exception indicating an invalid request on the part of the user."""


app = Flask(__name__)


def handle_client_errors(f):
    """A decorator which adds some error handling.

    If the function decorated with `handle_client_errors` raises an exception
    of type `APIError`, the error will be reported to the client, whereas
    other exceptions (being indications of a bug in the HaaS) will not be.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            resp = f(*args, **kwargs)
        except APIError as e:
            # Right now we're always returning 400 (Bad Request). This probably
            # isn't actually the right thing to do.
            #
            # Additionally, we're getting deprecation errors about the use of
            # the message attribute. TODO: figure out what the right way to do
            # this is.
            return e.message, 400
        if not resp:
            return ''
    return wrapped


def rest_call(method, path):
    """A decorator which generates a rest mapping to a python api call.

    path - the url-path to map the function to. The format is the same as for
           flask's router (e.g. app.route('/foo/<bar>/baz',...))
    method - the HTTP method for the api call

    Any parameters to the function not designated in the url will be pull from
    the form data.

    For example, given:

        @rest_call('POST', '/some-url/<baz>/<bar>')
        def foo(bar, baz, quux):
            pass

    When a POST request to /some-uril/*/* occurs, `foo` will be invoked
    with its bar and baz arguments pulleed from the url, and its quux from
    the form data in the body.

    The original function will returned by the call, not the wrapper. This
    way the test suite doesn't have to deal with the things flask has done
    to it - it can invoke the raw api calls..
    """
    def wrapper(func):
        argnames, _, _, _ = inspect.getargspec(func)

        @app.route(path, methods=[method])
        @wraps(func)
        @handle_client_errors
        def wrapped(*args, **kwargs):
            positional_args = []
            for name in argnames:
                if name in kwargs:
                    positional_args.append(kwargs[name])
                    del kwargs[name]
                else:
                    positional_args.append(request.form[name])
            return func(*positional_args, **kwargs)
        return func
    return wrapper


@rest_call('PUT', '/user/<username>')
def user_create(username, password):
    """Create user `username`.

    If the user already exists, a DuplicateError will be raised.
    """
    db = model.Session()
    _assert_absent(db, model.User, username)
    user = model.User(username, password)
    db.add(user)
    db.commit()


@rest_call('DELETE', '/user/<username>')
def user_delete(username):
    """Delete user `username`

    If the user does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    user = _must_find(db, model.User, username)
    db.delete(user)
    db.commit()

                            # Group Code #
                            ##############


@rest_call('PUT', '/group/<groupname>')
def group_create(groupname):
    """Create group 'groupname'.

    If the group already exists, a DuplicateError will be raised.
    """
    db = model.Session()
    _assert_absent(db, model.Group, groupname)
    group = model.Group(groupname)
    db.add(group)
    db.commit()


@rest_call('DELETE', '/group/<groupname>')
def group_delete(groupname):
    """Delete group 'groupname'

    If the group does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    group = _must_find(db, model.Group, groupname)
    db.delete(group)
    db.commit()


@rest_call('POST', '/group/<groupname>/add_user')
def group_add_user(groupname, user):
    """Add a group to a user

    If the group or user does not exist, a NotFoundError will be raised.
    """
    username = user

    db = model.Session()
    user = _must_find(db, model.User, username)
    group = _must_find(db, model.Group, groupname)
    if group in user.groups:
        raise DuplicateError(username)
    user.groups.append(group)
    db.commit()


@rest_call('POST', '/group/<groupname>/remove_user')
def group_remove_user(groupname, user):
    """Remove a group from a user

    If the group or user does not exist, a NotFoundError will be raised.
    """
    username = user

    db = model.Session()
    user = _must_find(db, model.User, username)
    group = _must_find(db, model.Group, groupname)
    if group not in user.groups:
        raise NotFoundError(username)
    user.groups.remove(group)
    db.commit()

                            # Project Code #
                            ################


@rest_call('PUT', '/project/<projectname>')
def project_create(projectname, group):
    """Create project 'projectname'.

    If the project already exists, a DuplicateError will be raised.
    """
    groupname = group

    db = model.Session()
    _assert_absent(db, model.Project, projectname)
    group = _must_find(db, model.Group, groupname)
    project = model.Project(group, projectname)
    db.add(project)
    db.commit()


@rest_call('DELETE', '/project/<projectname>')
def project_delete(projectname):
    """Delete project 'projectname'

    If the project does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    project = _must_find(db, model.Project, projectname)
    db.delete(project)
    db.commit()


@rest_call('POST', '/project/<projectname>/deploy')
def project_deploy(projectname):
    """Deploy project 'projectname'

    If the project does not exist, a NotFoundError will be raised.

    TODO: there are other possible errors, document them and how they are
    handled.
    """
    driver_name = cfg.get('general', 'active_switch')
    driver = importlib.import_module('haas.drivers.' + driver_name)

    db = model.Session()
    project = _must_find(db, model.Project, projectname)

    for net in project.networks:
        for nic in net.nics:
            driver.set_access_vlan(int(nic.port.label), net.vlan_no)

    if project.headnode:
        project.headnode.create()
        for hnic in project.headnode.hnics:
            hnic.create()
        project.headnode.start()
    else:
        pass  # TODO: at least log this, if not throw an error.


@rest_call('POST', '/project/<projectname>/connect_node')
def project_connect_node(projectname, node):
    """Add a project 'projectname' to an existing node

    If the node or project does not exist, a NotFoundError will be raised.
    """
    nodename = node

    db = model.Session()
    project = _must_find(db, model.Project, projectname)
    node = _must_find(db, model.Node, nodename)
    project.nodes.append(node)
    db.commit()


@rest_call('POST', '/project/<projectname>/detach_node')
def project_detach_node(projectname, node):
    """Remove a project 'projectname' from an existing node

    If the node or project does not exist, a NotFoundError will be raised.
    """
    nodename = node

    db = model.Session()
    project = _must_find(db, model.Project, projectname)
    node = _must_find(db, model.Node, nodename)
    if node not in project.nodes:
        raise NotFoundError(projectname)
    project.nodes.remove(node)
    db.commit()


                            # Node Code #
                            #############


@rest_call('PUT', '/node/<nodename>')
def node_register(nodename):
    """Create node 'nodename'.

    If the node already exists, a DuplicateError will be raised.
    """
    db = model.Session()
    _assert_absent(db, model.Node, nodename)
    node = model.Node(nodename)
    db.add(node)
    db.commit()


@rest_call('DELETE', '/node/<nodename>')
def node_delete(nodename):
    """Delete node 'nodename'

    If the node does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    node = _must_find(db, model.Node, nodename)
    db.delete(node)
    db.commit()


@rest_call('PUT', '/node/<nodename>/nic/<nic_name>')
def node_register_nic(nodename, nic_name, macaddr):
    """Register exitence of nic attached to given node

    If the node does not exist, a NotFoundError will be raised.

    If there is already an nic with that name, a DuplicateError will be raised.
    """
    db = model.Session()
    node = _must_find(db, model.Node, nodename)
    _assert_absent(db, model.Nic, nic_name)
    nic = model.Nic(node, nic_name, macaddr)
    db.add(nic)
    db.commit()


@rest_call('DELETE', '/node/<nodename>/nic/<nic_name>')
def node_delete_nic(nodename, nic_name):
    """Delete nic with given name.

    If the nic does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    nic = _must_find(db, model.Nic, nic_name)
    if nic.node.label != nodename:
        raise NotFoundError("Nic: " + nic_name)
    db.delete(nic)
    db.commit()


@rest_call('POST', '/node/<node_label>/nic/<nic_label>/connect_network')
def node_connect_network(node_label, nic_label, network):
    """Connect a physical NIC to a network"""
    network_label = network

    db = model.Session()

    node = _must_find(db, model.Node, node_label)
    nic = _must_find(db, model.Nic, nic_label)
    network = _must_find(db, model.Network, network_label)

    if nic.node is not node:
        raise NotFoundError('nic %s on node %s' % (nic_label, node_label))

    if nic.network:
        # The nic is already part of a network; report an error to the user.
        raise BusyError('nic %s on node %s is already part of a network' %
                        (nic_label, node_label))
    nic.network = network
    db.commit()


@rest_call('POST', '/node/<node_label>/nic/<nic_label>/detach_network')
def node_detach_network(node_label, nic_label):
    """Detach a physical nic from its network (if any).

    If the nic is not already a member of a network, this function does
    nothing.
    """
    db = model.Session()

    node = _must_find(db, model.Node, node_label)
    nic = _must_find(db, model.Nic, nic_label)

    if nic.node is not node:
        raise NotFoundError('nic %s on node %s' % (nic_label, node_label))

    nic.network = None
    db.commit()

                            # Head Node Code #
                            ##################


@rest_call('PUT', '/headnode/<nodename>')
def headnode_create(nodename, project):
    """Create head node 'nodename'.

    If the node already exists, a DuplicateError will be raised.
    """
    projectname = project

    db = model.Session()

    _assert_absent(db, model.Headnode, nodename)
    project = _must_find(db, model.Project, projectname)

    if project.headnode is not None:
        raise DuplicateError('project %s already has a headnode' %
                             (projectname))

    headnode = model.Headnode(project, nodename)

    db.add(headnode)
    db.commit()


@rest_call('DELETE', '/headnode/<nodename>')
def headnode_delete(nodename):
    """Delete node 'nodename'

    If the node does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    headnode = _must_find(db, model.Headnode, nodename)
    db.delete(headnode)
    db.commit()


@rest_call('PUT', '/headnode/<nodename>/hnic/<hnic_name>')
def headnode_create_hnic(nodename, hnic_name, macaddr):
    """Create hnic attached to given headnode

    If the node does not exist, a NotFoundError will be raised.

    If there is already an hnic with that name, a DuplicateError will
    be raised.
    """
    db = model.Session()
    headnode = _must_find(db, model.Headnode, nodename)
    _assert_absent(db, model.Hnic, hnic_name)
    hnic = model.Hnic(headnode, hnic_name, macaddr)
    db.add(hnic)
    db.commit()


@rest_call('DELETE', '/headnode/<nodename>/hnic/<hnic_name>')
def headnode_delete_hnic(nodename, hnic_name):
    """Delete hnic with given name.

    If the hnic does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    hnic = _must_find(db, model.Hnic, hnic_name)
    if hnic.headnode.label != nodename:
        # We raise a NotFoundError for the following reason: Hnic's SHOULD
        # belong to headnodes, and thus we SHOULD be doing a search of the
        # hnics belonging to the given headnode.  (In that situation, we will
        # honestly get a NotFoundError.)  We aren't right now, because
        # currently Hnic's labels are globally unique.
        raise NotFoundError("Hnic: " + hnic_name)
    db.delete(hnic)
    db.commit()


@rest_call('POST', '/headnode/<node_label>/hnic/<nic_label>/connect_network')
def headnode_connect_network(node_label, nic_label, network):
    """Connect a headnode's NIC to a network"""
    network_label = network

    # XXX: This is flagrantly copy/pasted from node_connect network. I feel a
    # little bad about myself, and we should fix this. same goes for
    # *_detach_network.
    db = model.Session()

    headnode = _must_find(db, model.Headnode, node_label)
    hnic = _must_find(db, model.Hnic, nic_label)
    network = _must_find(db, model.Network, network_label)

    if hnic.headnode is not headnode:
        raise NotFoundError('hnic %s on headnode %s' % (nic_label, node_label))

    if hnic.network:
        # The nic is already part of a network; report an error to the user.
        raise BusyError('hnic %s on headnode %s is already part of a network' %
                        (nic_label, node_label))
    hnic.network = network
    db.commit()


@rest_call('POST', '/headnode/<node_label>/hnic/<nic_label>/detach_network')
def headnode_detach_network(node_label, nic_label):
    """Detach a heanode's nic from its network (if any).

    If the nic is not already a member of a network, this function does
    nothing.
    """
    db = model.Session()

    headnode = _must_find(db, model.Headnode, node_label)
    hnic = _must_find(db, model.Hnic, nic_label)

    if hnic.headnode is not headnode:
        raise NotFoundError('hnic %s on headnode %s' % (nic_label, node_label))

    hnic.network = None
    db.commit()

                            # Network Code #
                            ################


@rest_call('PUT', '/network/<networkname>')
def network_create(networkname, project):
    """Create network 'networkname'.

    If the network already exists, a DuplicateError will be raised.
    If the network cannot be allocated (due to resource exhaustion), an
    AllocationError will be raised.
    """
    projectname = project

    db = model.Session()
    _assert_absent(db, model.Network, networkname)
    project = _must_find(db, model.Project, projectname)
    vlan = db.query(model.Vlan).filter_by(available=True).first()
    if vlan is None:
        raise AllocationError('No more networks')
    network = model.Network(project, vlan, networkname)
    db.add(network)
    db.commit()


@rest_call('DELETE', '/network/<networkname>')
def network_delete(networkname):
    """Delete network 'networkname'

    If the network does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    network = _must_find(db, model.Network, networkname)
    vlan = db.query(model.Vlan).filter_by(vlan_no=network.vlan_no).one()
    vlan.available = True
    db.delete(network)
    db.commit()


@rest_call('PUT', '/vlan/<vlan>')
def vlan_register(vlan):
    """Registers the vlan with vlan number `vlan`.

    Note that vlan should be a *string*, not a number. It is intended to be
    pulled right from the HTTP request; this function will validate the
    argument.
    """
    try:
        vlan_no = int(vlan)
    except Exception:
        raise BadArgumentError('vlan:%s' % vlan)
    if vlan_no < 1 or vlan_no > 4096:
        raise BadArgumentError('vlan out of range: %d', vlan_no)
    db = model.Session()
    _assert_absent(db, model.Vlan, str(vlan_no))
    db.add(model.Vlan(vlan_no))
    db.commit()


@rest_call('DELETE', '/vlan/<vlan>')
def vlan_delete(vlan):
    """Deletes the vlan with vlan number `vlan`.

    Note that vlan should be a *string*, not a number. It is intended to be
    pulled right from the HTTP request; this function will validate the
    argument.
    """
    try:
        vlan_no = int(vlan)
    except Exception:
        raise BadArgumentError('vlan:%s' % vlan)
    if vlan_no < 1 or vlan_no > 4096:
        raise BadArgumentError('vlan out of range: %d', vlan_no)

    db = model.Session()
    db.delete(_must_find(db, model.Vlan, str(vlan_no)))
    db.commit()


                            # Switch code #
                            ###############

@rest_call('PUT', '/switch/<name>')
def switch_register(name, driver):
    """Register the switch named `name`.

    If the switch already exists, a DuplicateError will be raised.
    """
    db = model.Session()
    _assert_absent(db, model.Switch, name)
    switch = model.Switch(name, driver)
    db.add(switch)
    db.commit()


@rest_call('DELETE', '/switch/<name>')
def switch_delete(name):
    db = model.Session()
    switch = _must_find(db, model.Switch, name)
    db.delete(switch)
    db.commit()


@rest_call('PUT', '/switch/<switch_name>/port/<port_name>')
def port_register(switch_name, port_name):
    """Register a port with name "port" on switch "switch".

    Currently, this label both must be unique AND will generally have to be
    decimal integers.  This is nonsense if there are multiple switches, but we
    don't support that anyways.

    If the port already exists, a DuplicateError will be raised.

    If the switch does not exist, a NotFoundError will be raised.
    """
    db = model.Session()
    switch = _must_find(db, model.Switch, switch_name)
    _assert_absent(db, model.Port, port_name)
    port = model.Port(switch, port_name)
    db.add(port)
    db.commit()


@rest_call('DELETE', '/switch/<switch_name>/port/<port_name>')
def port_delete(switch_name, port_name):
    """Delete a port with name "port" on switch "switch".

    If the port does not exist, or if the switch does not exist, a
    NotFoundError will be raised.
    """
    db = model.Session()
    switch = _must_find(db, model.Switch, switch_name)
    port = _must_find(db, model.Port, port_name)
    if port.switch is not switch:
        raise NotFoundError(port_name)
    db.delete(port)
    db.commit()


@rest_call('POST', '/switch/<switch_name>/port/<port_name>/connect_nic')
def port_connect_nic(switch_name, port_name, node, nic):
    """Connect a port on a switch to a nic on a node

    If any of the four arguments does not exist, a NotFoundError will be
    raised.

    If the port or the nic are already connected to something, a
    DuplicateError will be raised.
    """
    node_name = node
    nic_name = nic

    db = model.Session()

    switch = _must_find(db, model.Switch, switch_name)
    port = _must_find(db, model.Port, port_name)
    if port.switch is not switch:
        raise NotFoundError(port_name)

    node = _must_find(db, model.Node, node_name)
    nic = _must_find(db, model.Nic, nic_name)
    if nic.node is not node:
        raise NotFoundError(nic_name)

    if nic.port is not None:
        raise DuplicateError(nic_name)

    if port.nic is not None:
        raise DuplicateError(port_name)

    nic.port = port
    db.commit()


@rest_call('POST', '/switch/<switch_name>/port/<port_name>/detach_nic')
def port_detach_nic(switch_name, port_name):
    """Detach attached nic from a port

    If the port or switch are not found, a NotFoundError will be raised.

    If the port is not connected to anything, a NotFoundError will be raised.
    """
    db = model.Session()

    switch = _must_find(db, model.Switch, switch_name)
    port = _must_find(db, model.Port, port_name)
    if port.switch is not switch:
        raise NotFoundError(port_name)


    if port.nic is None:
        raise NotFoundError(port_name)

    port.nic = None
    db.commit()

    # Helper functions #
    ####################


def _assert_absent(session, cls, name):
    """Raises a DuplicateError if the given object is already in the database.

    This is useful for most of the *_create functions.

    Arguments:

    session - a sqlaclhemy session to use.
    cls - the class of the object to query.
    name - the name of the object in question.
    """
    obj = session.query(cls).filter_by(label=name).first()
    if obj:
        raise DuplicateError(cls.__name__ + ': ' + name)


def _must_find(session, cls, name):
    """Raises a NotFoundError if the given object doesn't exist in the datbase.
    Otherwise returns the object

    This is useful for most of the *_delete functions.

    Arguments:

    session - a sqlaclhemy session to use.
    cls - the class of the object to query.
    name - the name of the object in question.
    """
    obj = session.query(cls).filter_by(label=name).first()
    if not obj:
        raise NotFoundError(cls.__name__ + ': ' + name)
    return obj
