# -*- coding: utf-8 -*-
import logging
import httplib as http

from modularodm.exceptions import ModularOdmException
from framework.flask import request
from framework import push_errors_to_status, Q

from framework import StoredObject
from framework.auth.decorators import must_be_logged_in, collect_auth
import framework.status as status
from framework.exceptions import HTTPError
from framework.forms.utils import sanitize
from framework.mongo.utils import from_mongo

from website import language

from website.exceptions import NodeStateError
from website.project import clean_template_name, new_node, new_private_link
from website.project.decorators import (
    must_be_contributor_or_public,
    must_be_valid_project,
    must_have_permission,
    must_not_be_registration,
)
from website.project.model import has_anonymous_link
from website.project.forms import NewProjectForm, NewNodeForm, NewFolderForm
from website.models import Node, Pointer, WatchConfig, PrivateLink
from website import settings
from website.views import _render_nodes, find_dashboard
from website.profile import utils
from website.project import new_folder
from website.util.sanitize import deep_clean, scrub_html

from .log import _get_logs

logger = logging.getLogger(__name__)

@must_be_valid_project  # returns project
@must_have_permission('write')
@must_not_be_registration
def edit_node(auth, **kwargs):
    node = kwargs['node'] or kwargs['project']
    post_data = request.json
    edited_field = post_data.get('name')
    value = scrub_html(post_data.get('value', ''))
    if edited_field == 'title':
        node.set_title(value, auth=auth)
    elif edited_field == 'description':
        node.set_description(value, auth=auth)
    node.save()
    return {'status': 'success'}


##############################################################################
# New Project
##############################################################################


@must_be_logged_in
def project_new(**kwargs):
    return {}


@must_be_logged_in
def project_new_post(**kwargs):
    user = kwargs['auth'].user
    form = NewProjectForm(request.form)
    if form.validate():
        if form.template.data:
            # Create a project from a template
            original_node = Node.load(form.template.data)

            project_changes = {
                'title': form.title.data
            }

            # If the user entered a description, use it instead of the source's
            if form.description.data:
                project_changes['description'] = form.description.data

            project = original_node.use_as_template(
                auth=kwargs['auth'],
                changes={
                    form.template.data: project_changes
                }
            )
        else:
            # Create a new project
            project = new_node(
                'project', form.title.data, user, form.description.data
            )
        return {}, 201, None, project.url
    else:
        push_errors_to_status(form.errors)
    raise HTTPError(http.BAD_REQUEST)


@must_be_logged_in
@must_be_valid_project
def project_new_from_template(**kwargs):
    original_node = kwargs.get('node')
    new_node = original_node.use_as_template(
        auth=kwargs['auth'],
        changes=dict(),
    )
    return {'url': new_node.url}, http.CREATED, None

##############################################################################
# New Folder
##############################################################################


@must_be_logged_in
def folder_new(**kwargs):
    node_id = kwargs['nid']
    return_value = {}
    if node_id is not None:
        return_value = {'node_id': node_id}
    return return_value


@must_be_logged_in
def folder_new_post(auth, nid, **kwargs):
    user = auth.user
    form = NewFolderForm(request.form)
    if form.validate():
        node = Node.load(nid)
        if node.is_deleted or node.is_registration or not node.is_folder:
            raise HTTPError(http.BAD_REQUEST)
        folder = new_folder(
            scrub_html(form.title.data), user
        )
        folders = [folder]
        _add_pointers(node, folders, auth)
        return {}, 201, None, "/dashboard/"
    else:
        push_errors_to_status(form.errors)
    raise HTTPError(http.BAD_REQUEST)

def rename_folder(**kwargs):
    pass

@collect_auth
def add_folder(**kwargs):
    auth = kwargs['auth']
    user = auth.user
    title = scrub_html(request.json.get('title'))
    node_id = request.json.get('node_id')
    node = Node.load(node_id)
    if node.is_deleted or node.is_registration or not node.is_folder:
        raise HTTPError(http.BAD_REQUEST)

    folder = new_folder(
        title, user
    )
    folders = [folder]
    _add_pointers(node, folders, auth)
    return {}, 201, None

##############################################################################
# New Node
##############################################################################


@must_be_valid_project # returns project
@must_have_permission('write')
@must_not_be_registration
def project_new_node(**kwargs):
    form = NewNodeForm(request.form)
    project = kwargs['project']
    user = kwargs['auth'].user
    if form.validate():
        node = new_node(
            title=form.title.data,
            user=user,
            category=form.category.data,
            project=project,
        )
        return {
            'status': 'success',
        }, 201, None, node.url
    else:
        push_errors_to_status(form.errors)
    raise HTTPError(http.BAD_REQUEST, redirect_url=project.url)


@must_be_logged_in
@must_be_valid_project  # returns project
def project_before_fork(**kwargs):

    node = kwargs['node'] or kwargs['project']
    user = kwargs['auth'].user

    prompts = node.callback('before_fork', user=user)

    if node.has_pointers_recursive:
        prompts.append(
            language.BEFORE_FORK_HAS_POINTERS.format(
                category=node.project_or_component
            )
        )

    return {'prompts': prompts}


@must_be_logged_in
@must_be_valid_project
def node_fork_page(**kwargs):
    project = kwargs['project']
    node = kwargs['node']
    auth = kwargs['auth']

    if node:
        node_to_use = node
        raise HTTPError(
            http.FORBIDDEN,
            message='At this time, only projects can be forked; however, this behavior is coming soon.',
            redirect_url=node_to_use.url
        )
    else:
        node_to_use = project

    fork = node_to_use.fork_node(auth)

    return fork.url


@must_be_valid_project
@must_be_contributor_or_public # returns user, project
def node_registrations(**kwargs):
    auth = kwargs['auth']
    node_to_use = kwargs['node'] or kwargs['project']
    return _view_project(node_to_use, auth, primary=True)



@must_be_valid_project
@must_be_contributor_or_public # returns user, project
def node_forks(**kwargs):
    project = kwargs['project']
    node = kwargs['node']
    auth = kwargs['auth']
    node_to_use = node or project
    return _view_project(node_to_use, auth, primary=True)



@must_be_valid_project
@must_have_permission('write')
def node_setting(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    if not node.can_edit(auth):
        raise HTTPError(http.FORBIDDEN)

    rv = _view_project(node, auth, primary=True)

    addons_enabled = []
    addon_enabled_settings = []

    for addon in node.get_addons():

        addons_enabled.append(addon.config.short_name)
        if 'node' in addon.config.configs:
            addon_enabled_settings.append(addon.to_json(auth.user))

    rv['addon_categories'] = settings.ADDON_CATEGORIES
    rv['addons_available'] = [
        addon
        for addon in settings.ADDONS_AVAILABLE
        if 'node' in addon.owners
        and 'node' not in addon.added_mandatory
        and not addon.short_name in settings.SYSTEM_ADDED_ADDONS['node']
    ]
    rv['addons_enabled'] = addons_enabled
    rv['addon_enabled_settings'] = addon_enabled_settings
    rv['addon_capabilities'] = settings.ADDON_CAPABILITIES

    rv['comments'] = {
        'level': node.comment_level,
    }

    return rv

@must_have_permission('write')
@must_not_be_registration
def node_choose_addons(**kwargs):
    node = kwargs['node'] or kwargs['project']
    auth = kwargs['auth']
    node.config_addons(request.json, auth)


@must_be_valid_project
@must_have_permission('read')
def node_contributors(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    rv = _view_project(node, auth)
    rv['contributors'] = utils.serialize_contributors(node.contributors, node)
    return rv


@must_have_permission('write')
def configure_comments(**kwargs):
    node = kwargs['node'] or kwargs['project']
    comment_level = request.json.get('commentLevel')
    if not comment_level:
        node.comment_level = None
    elif comment_level in ['public', 'private']:
        node.comment_level = comment_level
    else:
        raise HTTPError(http.BAD_REQUEST)
    node.save()


##############################################################################
# View Project
##############################################################################

@must_be_valid_project
@must_be_contributor_or_public
def view_project(**kwargs):
    auth = kwargs['auth']
    node_to_use = kwargs['node'] or kwargs['project']
    primary = '/api/v1' not in request.path
    rv = _view_project(node_to_use, auth, primary=primary)
    rv['addon_capabilities'] = settings.ADDON_CAPABILITIES
    return rv

#### Expand/Collapse

@must_be_valid_project
@must_be_contributor_or_public
def is_expanded(**kwargs):
    auth = kwargs['auth']
    node_to_use = kwargs['node'] or kwargs['project']
    return node_to_use.is_expanded(auth=auth)

@must_be_valid_project
@must_be_contributor_or_public
def expand(**kwargs):
    auth = kwargs['auth']
    node_to_use = kwargs['node'] or kwargs['project']
    node_to_use.expand(auth=auth)

@must_be_valid_project
@must_be_contributor_or_public
def collapse(**kwargs):
    auth = kwargs['auth']
    node_to_use = kwargs['node'] or kwargs['project']
    node_to_use.collapse(auth=auth)

#### Reorder components

@must_be_valid_project
@must_not_be_registration
@must_have_permission('write')
def project_reorder_components(project, **kwargs):
    """Reorders the components in a project's component list.

    :param-json list new_list: List of strings that include node IDs and
        node type delimited by ':'.

    """
    # TODO(sloria): Change new_list parameter to be an array of objects
    # {
    #   'newList': {
    #       {'key': 'abc123', 'type': 'node'}
    #   }
    # }
    new_list = [
        tuple(node.split(':'))
        for node in request.json.get('new_list', [])
    ]
    nodes_new = [
        StoredObject.get_collection(schema).load(key)
        for key, schema in new_list
    ]

    valid_nodes = [
        node for node in project.nodes
        if not node.is_deleted
    ]
    deleted_nodes = [
        node for node in project.nodes
        if node.is_deleted
    ]
    if len(valid_nodes) == len(nodes_new) and set(valid_nodes) == set(nodes_new):
        project.nodes = nodes_new + deleted_nodes
        project.save()
        return {}

    logger.error('Got invalid node list in reorder components')
    raise HTTPError(http.BAD_REQUEST)


##############################################################################


@must_be_valid_project
@must_be_contributor_or_public # returns user, project
def project_statistics(**kwargs):
    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']
    if not (node.can_edit(auth) or node.is_public):
        raise HTTPError(http.FORBIDDEN)
    return _view_project(node, auth, primary=True)



###############################################################################
# Make Private/Public
###############################################################################


@must_be_valid_project
@must_have_permission('admin')
def project_before_set_public(**kwargs):
    node = kwargs['node'] or kwargs['project']

    return {
        'prompts': node.callback('before_make_public')
    }

@must_be_valid_project
@must_have_permission('admin')
def project_set_privacy(auth, **kwargs):

    permissions = kwargs.get('permissions')
    if permissions is None:
        raise HTTPError(http.BAD_REQUEST)

    node = kwargs['node'] or kwargs['project']

    node.set_privacy(permissions, auth)

    return {
        'status': 'success',
        'permissions': permissions,
    }


@must_be_valid_project  # returns project
@must_be_contributor_or_public
@must_not_be_registration
def watch_post(**kwargs):
    node = kwargs['node'] or kwargs['project']
    user = kwargs['auth'].user
    watch_config = WatchConfig(node=node,
                               digest=request.json.get('digest', False),
                               immediate=request.json.get('immediate', False))
    try:
        user.watch(watch_config)
    except ValueError:  # Node is already being watched
        raise HTTPError(http.BAD_REQUEST)

    user.save()

    return {
        'status': 'success',
        'watchCount': len(node.watchconfig__watched)
    }


@must_be_valid_project  # returns project
@must_be_contributor_or_public
@must_not_be_registration
def unwatch_post(**kwargs):
    node = kwargs['node'] or kwargs['project']
    user = kwargs['auth'].user
    watch_config = WatchConfig(node=node,
                               digest=request.json.get('digest', False),
                               immediate=request.json.get('immediate', False))
    try:
        user.unwatch(watch_config)
    except ValueError:  # Node isn't being watched
        raise HTTPError(http.BAD_REQUEST)

    return {
        'status': 'success',
        'watchCount': len(node.watchconfig__watched)
    }


@must_be_valid_project  # returns project
@must_be_contributor_or_public
@must_not_be_registration
def togglewatch_post(**kwargs):
    '''View for toggling watch mode for a node.'''
    # TODO: refactor this, watch_post, unwatch_post (@mambocab)
    node = kwargs['node'] or kwargs['project']
    user = kwargs['auth'].user
    watch_config = WatchConfig(
        node=node,
        digest=request.json.get('digest', False),
        immediate=request.json.get('immediate', False)
    )
    try:
        if user.is_watching(node):
            user.unwatch(watch_config)
        else:
            user.watch(watch_config)
    except ValueError:
        raise HTTPError(http.BAD_REQUEST)

    user.save()

    return {
        'status': 'success',
        'watchCount': len(node.watchconfig__watched),
        'watched': user.is_watching(node)
    }


@must_be_valid_project # returns project
@must_have_permission('admin')
@must_not_be_registration
def component_remove(**kwargs):
    """Remove component, and recursively remove its children. If node has a
    parent, add log and redirect to parent; else redirect to user dashboard.

    """
    node_to_use = kwargs['node'] or kwargs['project']
    auth = kwargs['auth']

    try:
        node_to_use.remove_node(auth)
    except NodeStateError as e:
        raise HTTPError(
            http.BAD_REQUEST,
            data={
                'message_long': 'Could not delete component: ' + e.message
            },
        )
    node_to_use.save()

    message = '{} deleted'.format(
        node_to_use.project_or_component.capitalize()
    )
    status.push_status_message(message)
    if node_to_use.node__parent:
        redirect_url = node_to_use.node__parent[0].url
    else:
        redirect_url = '/dashboard/'

    return {
        'url': redirect_url,
    }

@must_be_valid_project # returns project
@must_have_permission('admin')
@must_not_be_registration
def delete_folder(**kwargs):
    """Remove folder node

    """
    node = kwargs['node'] or kwargs['project']
    if node is None:
        raise HTTPError(http.BAD_REQUEST)

    if not node.is_folder or node.is_dashboard:
        raise HTTPError(http.BAD_REQUEST)

    auth = kwargs['auth']


    try:
        node.remove_node(auth)
    except NodeStateError as e:
        raise HTTPError(
            http.BAD_REQUEST,
            data={
                'message_long': 'Could not delete component: ' + e.message
            },
        )

    message = 'Folder deleted'
    status.push_status_message(message)
    redirect_url = '/dashboard/'

    return {
        'url': redirect_url,
    }

@collect_auth
def delete_folder_quietly(**kwargs):
    """Remove folder node without notification

    """
    node_id = request.json.get('node_id')
    if node_id is None:
        raise HTTPError(http.BAD_REQUEST)

    node = Node.load(node_id)

    if not node.is_folder or node.is_dashboard:
        raise HTTPError(http.BAD_REQUEST)

    auth = kwargs['auth']

    try:
        node.remove_node(auth)
    except NodeStateError as e:
        raise HTTPError(
            http.BAD_REQUEST,
            data={
                'message_long': 'Could not delete component: ' + e.message
            },
        )

    return {}


@must_be_valid_project # returns project
@must_have_permission("admin")
def remove_private_link(*args, **kwargs):
    link_id = request.json['private_link_id']

    try:
        link = PrivateLink.load(link_id)
        link.is_deleted = True
        link.save()
    except ModularOdmException:
        raise HTTPError(http.NOT_FOUND)


# TODO: Split into separate functions
def _render_addon(node):

    widgets = {}
    configs = {}
    js = []
    css = []

    for addon in node.get_addons():

        configs[addon.config.short_name] = addon.config.to_json()
        js.extend(addon.config.include_js.get('widget', []))
        css.extend(addon.config.include_css.get('widget', []))

        js.extend(addon.config.include_js.get('files', []))
        css.extend(addon.config.include_css.get('files', []))

    return widgets, configs, js, css


def _view_project(node, auth, primary=False):
    """Build a JSON object containing everything needed to render

    project.view.mako.

    """

    user = auth.user

    parent = node.parent_node
    view_only_link = auth.private_key or request.args.get('view_only', '').strip('/')
    anonymous = has_anonymous_link(node, view_only_link) if view_only_link else False
    recent_logs, has_more_logs= _get_logs(node, 10, auth, anonymous)
    widgets, configs, js, css = _render_addon(node)

    # Before page load callback; skip if not primary call
    if primary:
        for addon in node.get_addons():
            messages = addon.before_page_load(node, user) or []
            for message in messages:
                status.push_status_message(message)
    data = {
        'node': {
            'id': node._primary_key,
            'title': node.title,
            'category': node.category_display,
            'node_type': node.project_or_component,
            'description': node.description or '',
            'url': node.url,
            'api_url': node.api_url,
            'absolute_url': node.absolute_url,
            'display_absolute_url': node.display_absolute_url,
            'citations': {
                'apa': node.citation_apa,
                'mla': node.citation_mla,
                'chicago': node.citation_chicago,
            },
            'is_public': node.is_public,
            'date_created': node.date_created.strftime('%m/%d/%Y %H:%M UTC'),
            'date_modified': node.logs[-1].date.strftime('%m/%d/%Y %H:%M UTC') if node.logs else '',

            'tags': [tag._primary_key for tag in node.tags],
            'children': bool(node.nodes),
            'children_ids': [str(child._primary_key) for child in node.nodes],
            'is_registration': node.is_registration,
            'registered_from_url': node.registered_from.url if node.is_registration else '',
            'registered_date': node.registered_date.strftime('%Y/%m/%d %H:%M UTC') if node.is_registration else '',
            'registered_meta': [
                {
                    'name_no_ext': from_mongo(meta),
                    'name_clean': clean_template_name(meta),
                }
                for meta in node.registered_meta or []
            ],
            'registration_count': len(node.registration_list),

            'is_fork': node.is_fork,
            'forked_from_id': node.forked_from._primary_key if node.is_fork else '',
            'forked_from_display_absolute_url': node.forked_from.display_absolute_url if node.is_fork else '',
            'forked_date': node.forked_date.strftime('%Y/%m/%d %I:%M %p') if node.is_fork else '',
            'fork_count': len(node.fork_list),
            'templated_count': len(node.templated_list),
            'watched_count': len(node.watchconfig__watched),
            'private_links': [x.to_json() for x in node.private_links_active],
            'link': view_only_link,
            'anonymous': anonymous,
            'logs': recent_logs,
            'has_more_logs': has_more_logs,
            'points': node.points,
            'piwik_site_id': node.piwik_site_id,

            'comment_level': node.comment_level,
            'has_comments': bool(getattr(node, 'commented', [])),
            'has_children': bool(getattr(node, 'commented', False)),

        },
        'parent_node': {
            'id': parent._primary_key if parent else '',
            'title': parent.title if parent else '',
            'url': parent.url if parent else '',
            'api_url': parent.api_url if parent else '',
            'absolute_url':  parent.absolute_url if parent else '',
            'is_public': parent.is_public if parent else '',
            'is_contributor': parent.is_contributor(user) if parent else '',
            'can_view': (auth.private_key in parent.private_link_keys_active) if parent else False
        },
        'user': {
            'is_contributor': node.is_contributor(user),
            'can_edit': (node.can_edit(auth)
                                and not node.is_registration),
            'permissions': node.get_permissions(user) if user else [],
            'is_watching': user.is_watching(node) if user else False,
            'piwik_token': user.piwik_token if user else '',
            'id': user._id if user else None,
            'username': user.username if user else None,
            'can_comment': node.can_comment(auth),
        },
        'badges': _get_badge(user),
        # TODO: Namespace with nested dicts
        'addons_enabled': node.get_addon_names(),
        'addons': configs,
        'addon_widgets': widgets,
        'addon_widget_js': js,
        'addon_widget_css': css,

    }
    return data


def _get_badge(user):
    if user:
        badger = user.get_addon('badges')
        if badger:
            return {
                'can_award': badger.can_award,
                'badges': badger.get_badges_json()
            }
    return {}


def _get_children(node, auth, indent=0):

    children = []

    for child in node.nodes_primary:
        if not child.is_deleted and child.can_edit(auth):
            children.append({
                'id': child._primary_key,
                'title': child.title,
                'indent': indent,
            })
            children.extend(_get_children(child, auth, indent+1))

    return children


@must_be_valid_project # returns project
@must_have_permission('admin')
def private_link_table(**kwargs):
    node = kwargs['node'] or kwargs['project']
    data = {
        'node': {
            'absolute_url': node.absolute_url,
            'private_links': [x.to_json() for x in node.private_links_active],
            }
    }
    return data


@collect_auth
@must_be_valid_project
def get_editable_children(auth, **kwargs):

    node = kwargs['node'] or kwargs['project']

    if not node.can_edit(auth):
        return

    children = _get_children(node, auth)

    return {
        'node': {'title': node.title,},
        'children': children,
    }


def _get_user_activity(node, auth, rescale_ratio):

    # Counters
    total_count = len(node.logs)

    # Note: It's typically much faster to find logs of a given node
    # attached to a given user using node.logs.find(...) than by
    # loading the logs into Python and checking each one. However,
    # using deep caching might be even faster down the road.

    if auth.user:
        ua_count = node.logs.find(Q('user', 'eq', auth.user)).count()
    else:
        ua_count = 0

    non_ua_count = total_count - ua_count # base length of blue bar

    # Normalize over all nodes
    try:
        ua = ua_count / rescale_ratio * settings.USER_ACTIVITY_MAX_WIDTH
    except ZeroDivisionError:
        ua = 0
    try:
        non_ua = non_ua_count / rescale_ratio * settings.USER_ACTIVITY_MAX_WIDTH
    except ZeroDivisionError:
        non_ua = 0

    return ua_count, ua, non_ua


@must_be_valid_project
def get_recent_logs(**kwargs):
    node_to_use = kwargs['node'] or kwargs['project']
    logs = list(reversed(node_to_use.logs._to_primary_keys()))[:3]
    return {'logs': logs}


def _get_summary(node, auth, rescale_ratio, primary=True, link_id=None, view_only_link=None):
    # TODO(sloria): Refactor this or remove (lots of duplication with _view_project)
    summary = {
        'id': link_id if link_id else node._id,
        'primary': primary,
    }

    if node.can_view(auth):
        summary.update({
            'can_view': True,
            'can_edit': node.can_edit(auth),
            'primary_id': node._id,
            'url': node.url,
            'primary': primary,
            'api_url': node.api_url,
            'title': node.title,
            'category': node.category,
            'node_type': node.project_or_component,
            'is_registration': node.is_registration,
            'anonymous': has_anonymous_link(node, view_only_link),
            'registered_date': node.registered_date.strftime('%Y-%m-%d %H:%M UTC')
                if node.is_registration
                else None,
            'nlogs': None,
            'ua_count': None,
            'ua': None,
            'non_ua': None,
            'addons_enabled': node.get_addon_names(),
            'is_public': node.is_public
        })
        if rescale_ratio:
            ua_count, ua, non_ua = _get_user_activity(node, auth, rescale_ratio)
            summary.update({
                'nlogs': len(node.logs),
                'ua_count': ua_count,
                'ua': ua,
                'non_ua': non_ua,
            })
    else:
        summary['can_view'] = False

    # TODO: Make output format consistent with _view_project
    return {
        'summary': summary,
    }


@collect_auth
@must_be_valid_project
def get_summary(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']
    rescale_ratio = kwargs.get('rescale_ratio')
    primary = kwargs.get('primary')
    link_id = kwargs.get('link_id')
    view_only_link = auth.private_key or request.args.get('view_only', '').strip('/')

    return _get_summary(
        node, auth, rescale_ratio, primary=primary, link_id=link_id, view_only_link=view_only_link
    )


@must_be_contributor_or_public
def get_children(**kwargs):
    node_to_use = kwargs['node'] or kwargs['project']
    return _render_nodes([
        node
        for node in node_to_use.nodes
        if not node.is_deleted
    ])

@must_be_contributor_or_public
def get_folder_pointers(**kwargs):
    node_to_use = kwargs['node'] or kwargs['project']
    if not node_to_use.is_folder:
        return []
    return [
        node.resolve()._id
        for node in node_to_use.nodes
        if node is not None and not node.is_deleted and not node.primary
    ]

@must_be_contributor_or_public
def get_forks(**kwargs):
    node_to_use = kwargs['node'] or kwargs['project']
    forks = node_to_use.node__forked.find(
        Q('is_deleted', 'eq', False)
    )
    return _render_nodes(forks)


@must_be_contributor_or_public
def get_registrations(**kwargs):
    node_to_use = kwargs['node'] or kwargs['project']
    registrations = node_to_use.node__registrations
    return _render_nodes(registrations)


@must_be_valid_project # returns project
@must_have_permission('admin')
def project_generate_private_link_post(auth, **kwargs):
    """ creata a new private link object and add it to the node and its selected children"""

    node_to_use = kwargs['node'] or kwargs['project']
    node_ids = request.json.get('node_ids', [])
    name = request.json.get('name', '')
    anonymous = request.json.get('anonymous', False)

    if node_to_use._id not in node_ids:
        node_ids.insert(0, node_to_use._id)

    nodes = [Node.load(node_id) for node_id in node_ids]

    new_link = new_private_link(
        name=name, user=auth.user, nodes=nodes, anonymous=anonymous
    )

    return new_link


@must_be_valid_project # returns project
@must_have_permission('admin')
def project_private_link_edit(auth, **kwargs):
    new_name = request.json.get('value', '')
    private_link_id = request.json.get('pk','')
    private_link = PrivateLink.load(private_link_id)
    if private_link:
        private_link.name = new_name
        private_link.save()


def _serialize_node_search(node):
    """Serialize a node for use in pointer search.

    :param Node node: Node to serialize
    :return: Dictionary of node data

    """
    title = node.title
    if node.is_registration:
        title += ' (registration)'
    return {
        'id': node._id,
        'title': title,
        'firstAuthor': node.contributors[0].family_name,
        'etal': len(node.contributors) > 1,
    }


@must_be_logged_in
def search_node(**kwargs):
    """

    """
    # Get arguments
    auth = kwargs['auth']
    node = Node.load(request.json.get('nodeId'))
    include_public = request.json.get('includePublic')
    query = request.json.get('query', '').strip()
    if not query:
        return {'nodes': []}

    # Build ODM query
    title_query = Q('title', 'icontains', query)
    not_deleted_query = Q('is_deleted', 'eq', False)
    visibility_query = Q('contributors', 'eq', auth.user)
    no_folders_query = Q('is_folder', 'eq', False)
    if include_public:
        visibility_query = visibility_query | Q('is_public', 'eq', True)
    odm_query = title_query & not_deleted_query & visibility_query & no_folders_query

    # Exclude current node from query if provided
    if node:
        nin = [node._id] + node.node_ids
        odm_query = (
            odm_query &
            Q('_id', 'nin', nin)
        )

    # TODO: Parameterize limit; expose pagination
    cursor = Node.find(odm_query).limit(20)

    return {
        'nodes': [
            _serialize_node_search(each)
            for each in cursor
            if each.contributors
        ]
    }


def _add_pointers(node, pointers, auth):
    """

    :param Node node: Node to which pointers will be added
    :param list pointers: Nodes to add as pointers

    """
    added = False
    for pointer in pointers:
        node.add_pointer(pointer, auth, save=False)
        added = True

    if added:
        node.save()

@collect_auth
def move_pointers(auth):
    """Move pointer from one node to another node.

    """

    from_node_id = request.json.get('fromNodeId')
    to_node_id = request.json.get('toNodeId')
    pointers_to_move = request.json.get('pointerIds')

    if from_node_id is None or to_node_id is None or pointers_to_move is None:
        raise HTTPError(http.BAD_REQUEST)

    from_node = Node.load(from_node_id)
    to_node = Node.load(to_node_id)

    if to_node is None or from_node is None:
        raise HTTPError(http.BAD_REQUEST)

    for pointer_to_move in pointers_to_move:
        pointer_id = from_node.pointing_at(pointer_to_move)
        pointer_node = Node.load(pointer_to_move)

        pointer = Pointer.load(pointer_id)
        if pointer is None:
            raise HTTPError(http.BAD_REQUEST)

        try:
            from_node.rm_pointer(pointer, auth=auth)
        except ValueError:
            raise HTTPError(http.BAD_REQUEST)

        from_node.save()
        _add_pointers(to_node, [pointer_node], auth)

@collect_auth
def add_pointer(auth):
    """Add a single pointer to a node using only JSON parameters

    """

    to_node_id = request.json.get('toNodeID')
    pointer_to_move = request.json.get('pointerID')

    if not (to_node_id and pointer_to_move):
        raise HTTPError(http.BAD_REQUEST)

    pointer = Node.load(pointer_to_move)
    to_node = Node.load(to_node_id)

    _add_pointers(to_node, [pointer], auth)

@must_have_permission('write')
@must_not_be_registration
def add_pointers(**kwargs):
    """Add pointers to a node.

    """
    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']
    node_ids = request.json.get('nodeIds')

    if not node_ids:
        raise HTTPError(http.BAD_REQUEST)

    nodes = [
        Node.load(node_id)
        for node_id in node_ids
    ]

    _add_pointers(node, nodes, auth)

    return {}


@must_have_permission('write')
@must_not_be_registration
def remove_pointer(**kwargs):
    """Remove a pointer from a node, raising a 400 if the pointer is not
    in `node.nodes`.

    """
    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']
    # TODO: since these a delete request, shouldn't use request body. put pointer
    # id in the URL instead
    pointer_id = request.json.get('pointerId')
    if pointer_id is None:
        raise HTTPError(http.BAD_REQUEST)

    pointer = Pointer.load(pointer_id)
    if pointer is None:
        raise HTTPError(http.BAD_REQUEST)

    try:
        node.rm_pointer(pointer, auth=auth, save=False)
    except ValueError:
        raise HTTPError(http.BAD_REQUEST)

    node.save()

@must_be_valid_project # returns project
@must_have_permission('write')
@must_not_be_registration
def remove_pointer_from_folder(pointer_id, **kwargs):
    """Remove a pointer from a node, raising a 400 if the pointer is not
    in `node.nodes`.

    """
    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    if pointer_id is None:
        raise HTTPError(http.BAD_REQUEST)

    pointer_id = node.pointing_at(pointer_id)

    pointer = Pointer.load(pointer_id)

    if pointer is None:
        raise HTTPError(http.BAD_REQUEST)

    try:
        node.rm_pointer(pointer, auth=auth)
    except ValueError:
        raise HTTPError(http.BAD_REQUEST)

    node.save()

@must_be_valid_project # returns project
@must_have_permission('write')
@must_not_be_registration
def remove_pointers_from_folder(**kwargs):
    """Remove multiple pointers from a node, raising a 400 if the pointer is not
    in `node.nodes`.
    """
    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']
    pointer_ids = request.json.get('pointerIds')

    if pointer_ids is None:
        raise HTTPError(http.BAD_REQUEST)

    for pointer_id in pointer_ids:
        pointer_id = node.pointing_at(pointer_id)

        pointer = Pointer.load(pointer_id)

        if pointer is None:
            raise HTTPError(http.BAD_REQUEST)

        try:
            node.rm_pointer(pointer, auth=auth)
        except ValueError:
            raise HTTPError(http.BAD_REQUEST)

    node.save()



@must_have_permission('write')
@must_not_be_registration
def fork_pointer(**kwargs):
    """Fork a pointer. Raises BAD_REQUEST if pointer not provided, not found,
    or not present in `nodes`.

    """
    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']
    pointer_id = request.json.get('pointerId')
    pointer = Pointer.load(pointer_id)

    if pointer is None:
        raise HTTPError(http.BAD_REQUEST)

    try:
        node.fork_pointer(pointer, auth=auth, save=True)
    except ValueError:
        raise HTTPError(http.BAD_REQUEST)


def abbrev_authors(node):
    rv = node.contributors[0].family_name
    if len(node.visiblecontributors) > 1:
        rv += ' et al.'
    return rv


@must_be_contributor_or_public
def get_pointed(**kwargs):

    node = kwargs['node'] or kwargs['project']
    return {'pointed': [
        {
            'url': each.node__parent[0].url,
            'title': each.node__parent[0].title,
            'authorShort': abbrev_authors(node),
        }
        for each in node.pointed
    ]}

