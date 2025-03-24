# -*- coding: utf-8 -*-
import subprocess
import uuid
import hashlib
import calendar
import datetime
import os
import re
import unicodedata
import urllib
import urlparse
import logging
from HTMLParser import HTMLParser

import pytz
from dulwich.repo import Repo
from dulwich.object_store import tree_lookup_path
import blinker

from modularodm.exceptions import ValidationValueError, ValidationTypeError

from framework import status
from framework.mongo import ObjectId
from framework.mongo.utils import to_mongo
from framework.auth import get_user, User, Auth
from framework.analytics import (
    get_basic_counters, increment_user_activity_counters, piwik
)
from framework.exceptions import PermissionsError
from framework.git.exceptions import FileNotModified
from framework import StoredObject, fields, utils
from framework import GuidStoredObject, Q
from framework.addons import AddonModelMixin


from website.exceptions import NodeStateError
from website.util.permissions import (expand_permissions,
    DEFAULT_CONTRIBUTOR_PERMISSIONS,
    CREATOR_PERMISSIONS
)
from website.project.metadata.schemas import OSF_META_SCHEMAS
from website import language, settings
from website.util import web_url_for, api_url_for

html_parser = HTMLParser()

logger = logging.getLogger(__name__)


def utc_datetime_to_timestamp(dt):
    return float(
        str(calendar.timegm(dt.utcnow().utctimetuple())) + '.' + str(dt.microsecond)
    )


def normalize_unicode(ustr):
    return unicodedata.normalize('NFKD', ustr)\
        .encode('ascii', 'ignore')


signals = blinker.Namespace()
contributor_added = signals.signal('contributor-added')
unreg_contributor_added = signals.signal('unreg-contributor-added')


class MetaSchema(StoredObject):

    _id = fields.StringField(default=lambda: str(ObjectId()))
    name = fields.StringField()
    schema = fields.DictionaryField()
    category = fields.StringField()

    # Version of the Knockout metadata renderer to use (e.g. if data binds
    # change)
    metadata_version = fields.IntegerField()
    # Version of the schema to use (e.g. if questions, responses change)
    schema_version = fields.IntegerField()


def ensure_schemas(clear=True):
    """Import meta-data schemas from JSON to database, optionally clearing
    database first.

    :param clear: Clear schema database before import

    """
    if clear:
        MetaSchema.remove()
    for schema in OSF_META_SCHEMAS:
        try:
            MetaSchema.find_one(
                Q('name', 'eq', schema['name']) &
                Q('schema_version', 'eq', schema['schema_version'])
            )
        except:
            schema['name'] = schema['name'].replace(' ', '_')
            schema_obj = MetaSchema(**schema)
            schema_obj.save()


class MetaData(GuidStoredObject):

    _id = fields.StringField(primary=True)

    target = fields.AbstractForeignField(backref='metadata')
    data = fields.DictionaryField()

    date_created = fields.DateTimeField(auto_now_add=datetime.datetime.utcnow)
    date_modified = fields.DateTimeField(auto_now=datetime.datetime.utcnow)


def validate_comment_reports(value, *args, **kwargs):
    for key, val in value.iteritems():
        if not User.load(key):
            raise ValidationValueError('Keys must be user IDs')
        if not isinstance(val, dict):
            raise ValidationTypeError('Values must be dictionaries')
        if 'category' not in val or 'text' not in val:
            raise ValidationValueError(
                'Values must include `category` and `text` keys'
            )


class Comment(GuidStoredObject):

    _id = fields.StringField(primary=True)

    user = fields.ForeignField('user', required=True, backref='commented')
    node = fields.ForeignField('node', required=True, backref='comment_owner')
    target = fields.AbstractForeignField(required=True, backref='commented')

    date_created = fields.DateTimeField(auto_now_add=datetime.datetime.utcnow)
    date_modified = fields.DateTimeField(auto_now=datetime.datetime.utcnow)
    modified = fields.BooleanField()

    is_deleted = fields.BooleanField(default=False)
    content = fields.StringField()

    # Dictionary field mapping user IDs to dictionaries of report details:
    # {
    #   'icpnw': {'category': 'hate', 'message': 'offensive'},
    #   'cdi38': {'category': 'spam', 'message': 'godwins law'},
    # }
    reports = fields.DictionaryField(validate=validate_comment_reports)

    @classmethod
    def create(cls, auth, **kwargs):

        comment = cls(**kwargs)
        comment.save()

        comment.node.add_log(
            NodeLog.COMMENT_ADDED,
            {
                'project': comment.node.parent_id,
                'node': comment.node._id,
                'user': comment.user._id,
                'comment': comment._id,
            },
            auth=auth,
        )

        return comment

    def edit(self, content, auth, save=False):
        self.content = content
        self.modified = True
        self.node.add_log(
            NodeLog.COMMENT_UPDATED,
            {
                'project': self.node.parent_id,
                'node': self.node._id,
                'user': self.user._id,
                'comment': self._id,
            },
            auth=auth,
        )
        if save:
            self.save()

    def delete(self, auth, save=False):
        self.is_deleted = True
        self.node.add_log(
            NodeLog.COMMENT_REMOVED,
            {
                'project': self.node.parent_id,
                'node': self.node._id,
                'user': self.user._id,
                'comment': self._id,
            },
            auth=auth,
        )
        if save:
            self.save()

    def undelete(self, auth, save=False):
        self.is_deleted = False
        self.node.add_log(
            NodeLog.COMMENT_ADDED,
            {
                'project': self.node.parent_id,
                'node': self.node._id,
                'user': self.user._id,
                'comment': self._id,
            },
            auth=auth,
        )
        if save:
            self.save()

    def report_abuse(self, user, save=False, **kwargs):
        """Report that a comment is abuse.

        :param User user: User submitting the report
        :param bool save: Save changes
        :param dict kwargs: Report details
        :raises: ValueError if the user submitting abuse is the same as the
            user who posted the comment

        """
        if user == self.user:
            raise ValueError
        self.reports[user._id] = kwargs
        if save:
            self.save()

    def unreport_abuse(self, user, save=False):
        """Revoke report of abuse.

        :param User user: User who submitted the report
        :param bool save: Save changes
        :raises: ValueError if user has not reported comment as abuse

        """
        try:
            self.reports.pop(user._id)
        except KeyError:
            raise ValueError('User has not reported comment as abuse')

        if save:
            self.save()


class ApiKey(StoredObject):

    # The key is also its primary key
    _id = fields.StringField(
        primary=True,
        default=lambda: str(ObjectId()) + str(uuid.uuid4())
    )
    # A display name
    label = fields.StringField()

    @property
    def user(self):
        return self.user__keyed[0] if self.user__keyed else None

    @property
    def node(self):
        return self.node__keyed[0] if self.node__keyed else None


class NodeLog(StoredObject):

    _id = fields.StringField(primary=True, default=lambda: str(ObjectId()))

    date = fields.DateTimeField(default=datetime.datetime.utcnow)
    action = fields.StringField()
    params = fields.DictionaryField()

    user = fields.ForeignField('user', backref='created')
    api_key = fields.ForeignField('apikey', backref='created')
    foreign_user = fields.StringField()

    DATE_FORMAT = '%m/%d/%Y %H:%M UTC'

    # Log action constants
    CREATED_FROM = 'created_from'

    PROJECT_CREATED = 'project_created'
    PROJECT_REGISTERED = 'project_registered'

    NODE_CREATED = 'node_created'
    NODE_FORKED = 'node_forked'
    NODE_REMOVED = 'node_removed'

    POINTER_CREATED = 'pointer_created'
    POINTER_FORKED = 'pointer_forked'
    POINTER_REMOVED = 'pointer_removed'

    WIKI_UPDATED = 'wiki_updated'

    CONTRIB_ADDED = 'contributor_added'
    CONTRIB_REMOVED = 'contributor_removed'
    CONTRIB_REORDERED = 'contributors_reordered'

    PERMISSIONS_UPDATED = 'permissions_updated'

    MADE_PRIVATE = 'made_private'
    MADE_PUBLIC = 'made_public'

    TAG_ADDED = 'tag_added'
    TAG_REMOVED = 'tag_removed'

    EDITED_TITLE = 'edit_title'
    EDITED_DESCRIPTION = 'edit_description'

    FILE_ADDED = 'file_added'
    FILE_REMOVED = 'file_removed'
    FILE_UPDATED = 'file_updated'

    ADDON_ADDED = 'addon_added'
    ADDON_REMOVED = 'addon_removed'
    COMMENT_ADDED = 'comment_added'
    COMMENT_REMOVED = 'comment_removed'
    COMMENT_UPDATED = 'comment_updated'

    @property
    def node(self):
        return (
            Node.load(self.params.get('node')) or
            Node.load(self.params.get('project'))
        )

    @property
    def tz_date(self):
        '''Return the timezone-aware date.
        '''
        # Date should always be defined, but a few logs in production are
        # missing dates; return None and log error if date missing
        if self.date:
            return self.date.replace(tzinfo=pytz.UTC)
        logging.error('Date missing on NodeLog {}'.format(self._primary_key))

    @property
    def formatted_date(self):
        '''Return the timezone-aware, ISO-formatted string representation of
        this log's date.
        '''
        if self.tz_date:
            return self.tz_date.isoformat()

    def _render_log_contributor(self, contributor):
        user = User.load(contributor)
        if not user:
            return None
        if self.node:
            fullname = user.display_full_name(node=self.node)
        else:
            fullname = user.fullname
        return {
            'id': user._primary_key,
            'fullname': fullname,
            'registered': user.is_registered,
        }

    # TODO: Move to separate utility function
    def serialize(self):
        '''Return a dictionary representation of the log.'''
        return {
            'id': str(self._primary_key),
            'user': self.user.serialize()
                    if isinstance(self.user, User)
                    else {'fullname': self.foreign_user},
            'contributors': [self._render_log_contributor(c) for c in self.params.get("contributors", [])],
            'contributor': self._render_log_contributor(self.params.get("contributor")),
            'api_key': self.api_key.label if self.api_key else '',
            'action': self.action,
            'params': self.params,
            'date': utils.rfcformat(self.date),
            'node': self.node.serialize() if self.node else None
        }


class Tag(StoredObject):

    _id = fields.StringField(primary=True)
    count_public = fields.IntegerField(default=0)
    count_total = fields.IntegerField(default=0)

    @property
    def url(self):
        return '/search/?q=tags:{}'.format(self._id)


class Pointer(StoredObject):
    """A link to a Node. The Pointer delegates all but a few methods to its
    contained Node. Forking and registration are overridden such that the
    link is cloned, but its contained Node is not.

    """
    #: Whether this is a pointer or not
    primary = False

    _id = fields.StringField()
    node = fields.ForeignField('node', backref='_pointed')

    _meta = {'optimistic': True}

    def _clone(self):
        if self.node:
            clone = self.clone()
            clone.node = self.node
            clone.save()
            return clone

    def fork_node(self, *args, **kwargs):
        return self._clone()

    def register_node(self, *args, **kwargs):
        return self._clone()

    def use_as_template(self, auth, changes=None, top_level=False):
        return self._clone()

    def resolve(self):
        return self.node

    def __getattr__(self, item):
        """Delegate attribute access to the node being pointed to.
        """
        # Prevent backref lookups from being overriden by proxied node
        try:
            return super(Pointer, self).__getattr__(item)
        except AttributeError:
            pass
        if self.node:
            return getattr(self.node, item)
        raise AttributeError(
            'Pointer object has no attribute {0}'.format(
                item
            )
        )


class Node(GuidStoredObject, AddonModelMixin):

    redirect_mode = 'proxy'
    #: Whether this is a pointer or not
    primary = True

    # Node fields that trigger an update to Solr on save
    SOLR_UPDATE_FIELDS = {
        'title',
        'category',
        'description',
        'contributors',
        'tags',
        'is_fork',
        'is_registration',
        'is_public',
        'is_deleted',
        'wiki_pages_current',
    }

    _id = fields.StringField(primary=True)

    date_created = fields.DateTimeField(auto_now_add=datetime.datetime.utcnow)

    # Privacy
    is_public = fields.BooleanField(default=False)

    # User mappings
    permissions = fields.DictionaryField()
    visible_contributor_ids = fields.StringField(list=True)

    is_deleted = fields.BooleanField(default=False)
    deleted_date = fields.DateTimeField()

    is_registration = fields.BooleanField(default=False)
    registered_date = fields.DateTimeField()
    registered_user = fields.ForeignField('user', backref='registered')
    registered_schema = fields.ForeignField('metaschema', backref='registered')
    registered_meta = fields.DictionaryField()

    is_fork = fields.BooleanField(default=False)
    forked_date = fields.DateTimeField()

    title = fields.StringField(versioned=True)
    description = fields.StringField()
    category = fields.StringField()

    registration_list = fields.StringField(list=True)
    fork_list = fields.StringField(list=True)

    # One of 'public', 'private'
    # TODO: Add validator
    comment_level = fields.StringField(default='private')

    files_current = fields.DictionaryField()
    files_versions = fields.DictionaryField()
    wiki_pages_current = fields.DictionaryField()
    wiki_pages_versions = fields.DictionaryField()

    creator = fields.ForeignField('user', backref='created')
    contributors = fields.ForeignField('user', list=True, backref='contributed')
    users_watching_node = fields.ForeignField('user', list=True, backref='watched')

    logs = fields.ForeignField('nodelog', list=True, backref='logged')
    tags = fields.ForeignField('tag', list=True, backref='tagged')

    # Tags for internal use
    system_tags = fields.StringField(list=True, index=True)

    nodes = fields.AbstractForeignField(list=True, backref='parent')
    forked_from = fields.ForeignField('node', backref='forked')
    registered_from = fields.ForeignField('node', backref='registrations')

    # The node (if any) used as a template for this node's creation
    template_node = fields.ForeignField('node', backref='template_node')

    api_keys = fields.ForeignField('apikey', list=True, backref='keyed')

    piwik_site_id = fields.StringField()

    _meta = {
        'optimistic': True,
    }

    def __init__(self, *args, **kwargs):

        super(Node, self).__init__(*args, **kwargs)

        # Crash if parent provided and not project
        project = kwargs.get('project')
        if project and project.category != 'project':
            raise ValueError('Parent must be a project.')

        if kwargs.get('_is_loaded', False):
            return

        if self.creator:
            self.contributors.append(self.creator)
            self.set_visible(self.creator, visible=True)

            # Add default creator permissions
            for permission in CREATOR_PERMISSIONS:
                self.add_permission(self.creator, permission, save=False)

    @property
    def private_links(self):
        return self.privatelink__shared

    @property
    def private_links_active(self):
        return [x for x in self.private_links if not x.is_deleted]

    @property
    def private_link_keys_active(self):
        return [x.key for x in self.private_links if not x.is_deleted]

    @property
    def private_link_keys_deleted(self):
        return [x.key for x in self.private_links if x.is_deleted]

    def can_edit(self, auth=None, user=None):
        """Return if a user is authorized to edit this node.
        Must specify one of (`auth`, `user`).

        :param Auth auth: Auth object to check
        :param User user: User object to check
        :returns: Whether user has permission to edit this node.

        """
        if not auth and not user:
            raise ValueError('Must pass either `auth` or `user`')
        if auth and user:
            raise ValueError('Cannot pass both `auth` and `user`')
        user = user or auth.user
        if auth:
            is_api_node = auth.api_node == self
        else:
            is_api_node = False
        return (
            (user and self.has_permission(user, 'write'))
            or is_api_node
        )

    def can_view(self, auth):
        if auth.user and auth.user.private_links:
            key_ring = set(auth.user.private_link_keys)
            return self.is_public or auth.user \
                and self.has_permission(auth.user, 'read') \
                or not key_ring.isdisjoint(self.private_link_keys_active)
        else:
            return self.is_public or auth.user \
                and self.has_permission(auth.user, 'read') \
                or auth.private_key in self.private_link_keys_active

    def add_permission(self, user, permission, save=False):
        """Grant permission to a user.

        :param User user: User to grant permission to
        :param str permission: Permission to grant
        :param bool save: Save changes
        :raises: ValueError if user already has permission

        """
        if user._id not in self.permissions:
            self.permissions[user._id] = [permission]
        else:
            if permission in self.permissions[user._id]:
                raise ValueError('User already has permission {0}'.format(permission))
            self.permissions[user._id].append(permission)
        if save:
            self.save()

    def remove_permission(self, user, permission, save=False):
        """Revoke permission from a user.

        :param User user: User to revoke permission from
        :param str permission: Permission to revoke
        :param bool save: Save changes
        :raises: ValueError if user does not have permission

        """
        try:
            self.permissions[user._id].remove(permission)
        except (KeyError, ValueError):
            raise ValueError('User does not have permission {0}'.format(permission))
        if save:
            self.save()

    def clear_permission(self, user, save=False):
        """Clear all permissions for a user.

        :param User user: User to revoke permission from
        :param bool save: Save changes
        :raises: ValueError if user not in permissions

        """
        try:
            self.permissions.pop(user._id)
        except KeyError:
            raise ValueError(
                'User {0} not in permissions list for node {1}'.format(
                    user._id, self._id,
                )
            )
        if save:
            self.save()

    def set_permissions(self, user, permissions, save=False):
        self.permissions[user._id] = permissions
        if save:
            self.save()

    def has_permission(self, user, permission):
        """Check whether user has permission.

        :param User user: User to test
        :param str permission: Required permission
        :returns: User has required permission

        """
        if user is None:
            logger.error('User is ``None``.')
            return False
        try:
            return permission in self.permissions[user._id]
        except KeyError:
            return False

    def get_permissions(self, user):
        """Get list of permissions for user.

        :param User user: User to check
        :returns: List of permissions
        :raises: ValueError if user not found in permissions

        """
        return self.permissions.get(user._id, [])

    def adjust_permissions(self):
        for key in self.permissions.keys():
            if key not in self.contributors:
                self.permissions.pop(key)

    @property
    def visible_contributors(self):
        return [
            User.load(_id)
            for _id in self.visible_contributor_ids
        ]

    def is_visible_contributor(self, user):
        return user and user._id in self.visible_contributor_ids

    def get_visible(self, user):
        if not self.is_contributor(user):
            raise ValueError(u'User {0} not in contributors'.format(user))
        return user._id in self.visible_contributor_ids

    def set_visible(self, user, visible):
        if not self.is_contributor(user):
            raise ValueError(u'User {0} not in contributors'.format(user))
        if visible and user._id not in self.visible_contributor_ids:
            self.visible_contributor_ids.append(user._id)
        elif not visible and user._id in self.visible_contributor_ids:
            self.visible_contributor_ids.remove(user._id)

    def can_comment(self, auth):
        if self.comment_level == 'public':
            return auth.logged_in and self.can_view(auth)
        return self.can_edit(auth)

    def save(self, *args, **kwargs):

        self.adjust_permissions()

        first_save = not self._is_loaded
        is_original = not self.is_registration and not self.is_fork
        if 'suppress_log' in kwargs.keys():
            suppress_log = kwargs['suppress_log']
            del kwargs['suppress_log']
        else:
            suppress_log = False

        saved_fields = super(Node, self).save(*args, **kwargs)

        if first_save and is_original and not suppress_log:

            #
            # TODO: This logic also exists in self.use_as_template()
            for addon in settings.ADDONS_AVAILABLE:
                if 'node' in addon.added_default:
                    self.add_addon(addon.short_name, auth=None, log=False)

            #
            if getattr(self, 'project', None):

                # Append log to parent
                self.project.nodes.append(self)
                self.project.save()

                # Define log fields for component
                log_action = NodeLog.NODE_CREATED
                log_params = {
                    'node': self._primary_key,
                    'project': self.project._primary_key,
                }

            else:

                # Define log fields for non-component project
                log_action = NodeLog.PROJECT_CREATED
                log_params = {
                    'project': self._primary_key,
                }

            # Add log with appropriate fields
            self.add_log(
                log_action,
                params=log_params,
                auth=Auth(user=self.creator),
                log_date=self.date_created,
                save=True,
            )

        # Only update Solr if at least one stored field has changed, and if
        # public or privacy setting has changed
        need_update = bool(self.SOLR_UPDATE_FIELDS.intersection(saved_fields))
        if not self.is_public:
            if first_save or 'is_public' not in saved_fields:
                need_update = False
        if need_update:
            self.update_search()

        # This method checks what has changed.
        if settings.PIWIK_HOST:
            piwik.update_node(self, saved_fields)

        # Return expected value for StoredObject::save
        return saved_fields

    ######################################
    # Methods that return a new instance #
    ######################################

    def use_as_template(self, auth, changes=None, top_level=True):
        """Create a new project, using an existing project as a template.

        :param auth: The user to be assigned as creator
        :param changes: A dictionary of changes, keyed by node id, which
                        override the attributes of the template project or its
                        children.
        :return: The `Node` instance created.
        """

        changes = changes or dict()

        # build the dict of attributes to change for the new node
        try:
            attributes = changes[self._id]
            # TODO: explicitly define attributes which may be changed.
        except (AttributeError, KeyError):
            attributes = dict()

        new = self.clone()

        # clear permissions, which are not cleared by the clone method
        new.permissions = {}
        new.visible_contributor_ids = []

        # Clear quasi-foreign fields
        new.files_current = {}
        new.files_versions = {}
        new.wiki_pages_current = {}
        new.wiki_pages_versions = {}
        new.fork_list = []
        new.registration_list = []

        # set attributes which may be overridden by `changes`
        new.is_public = False
        new.description = None

        # apply `changes`
        for attr, val in attributes.iteritems():
            setattr(new, attr, val)

        # set attributes which may NOT be overridden by `changes`
        new.creator = auth.user
        new.add_contributor(contributor=auth.user, log=False, save=False)
        new.template_node = self
        new.is_fork = False
        new.is_registration = False

        # If that title hasn't been changed, apply the default prefix (once)
        if (new.title == self.title
                and top_level
                and language.TEMPLATED_FROM_PREFIX not in new.title):
            new.title = ''.join((language.TEMPLATED_FROM_PREFIX, new.title, ))

        # Slight hack - date_created is a read-only field.
        new._fields['date_created'].__set__(
            new,
            datetime.datetime.utcnow(),
            safe=True
        )

        new.save(suppress_log=True)

        # Log the creation
        new.add_log(
            NodeLog.CREATED_FROM,
            params={
                'node': new._primary_key,
                'template_node': {
                    'id': self._primary_key,
                    'url': self.url,
                },
            },
            auth=auth,
            log_date=new.date_created,
            save=False,
        )

        # add mandatory addons
        # TODO: This logic also exists in self.save()
        for addon in settings.ADDONS_AVAILABLE:
            if 'node' in addon.added_default:
                new.add_addon(addon.short_name, auth=None, log=False)

        # deal with the children of the node, if any
        new.nodes = [
            x.use_as_template(auth, changes, top_level=False)
            for x in self.nodes
            if x.can_view(auth)
        ]

        new.save()
        return new

    ############
    # Pointers #
    ############

    def add_pointer(self, node, auth, save=True):
        """Add a pointer to a node.

        :param Node node: Node to add
        :param Auth auth: Consolidated authorization
        :param bool save: Save changes
        :return: Created pointer

        """
        # Fail if node already in nodes / pointers. Note: cast node and node
        # to primary keys to test for conflicts with both nodes and pointers
        # contained in `self.nodes`.
        if node._id in self.node_ids:
            raise ValueError(
                'Pointer to node {0} already in list'.format(node._id)
            )

        # Append pointer
        pointer = Pointer(node=node)
        pointer.save()
        self.nodes.append(pointer)

        # Add log
        self.add_log(
            action=NodeLog.POINTER_CREATED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'pointer': {
                    'id': pointer.node._id,
                    'url': pointer.node.url,
                    'title': pointer.node.title,
                    'category': pointer.node.category,
                },
            },
            auth=auth,
            save=False,
        )

        # Optionally save changes
        if save:
            self.save()

        return pointer

    def rm_pointer(self, pointer, auth, save=True):
        """Remove a pointer.

        :param Pointer pointer: Pointer to remove
        :param Auth auth: Consolidated authorization
        :param bool save: Save changes

        """
        # Remove pointer from `nodes`
        self.nodes.remove(pointer)

        # Add log
        self.add_log(
            action=NodeLog.POINTER_REMOVED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'pointer': {
                    'id': pointer.node._id,
                    'url': pointer.node.url,
                    'title': pointer.node.title,
                    'category': pointer.node.category,
                },
            },
            auth=auth,
            save=False,
        )

        # Optionally save changes
        if save:
            self.save()
            pointer.remove_one(pointer)

    @property
    def node_ids(self):
        return [
            node._id if node.primary else node.node._id
            for node in self.nodes
        ]

    @property
    def nodes_primary(self):
        return [
            node
            for node in self.nodes
            if node.primary
        ]

    @property
    def nodes_pointer(self):
        return [
            node
            for node in self.nodes
            if not node.primary
        ]

    @property
    def pointed(self):
        return getattr(self, '_pointed', [])

    @property
    def points(self):
        return len(self.pointed)

    def resolve(self):
        return self

    def fork_pointer(self, pointer, auth, save=True):
        """Replace a pointer with a fork. If the pointer points to a project,
        fork the project and replace the pointer with a new pointer pointing
        to the fork. If the pointer points to a component, fork the component
        and add it to the current node.

        :param Pointer pointer:
        :param Auth auth:
        :param bool save:
        :return: Forked node

        """
        # Fail if pointer not contained in `nodes`
        try:
            index = self.nodes.index(pointer)
        except ValueError:
            raise ValueError('Pointer {0} not in list'.format(pointer._id))

        # Get pointed node
        node = pointer.node

        # Fork into current node and replace pointer with forked component
        forked = node.fork_node(auth)
        if forked is None:
            raise ValueError('Could not fork node')

        self.nodes[index] = forked

        # Optionally save changes
        if save:
            self.save()
            # Garbage-collect pointer. Note: Must save current node before
            # removing pointer, else remove will fail when trying to remove
            # backref from self to pointer.
            Pointer.remove_one(pointer)

        # Add log
        self.add_log(
            NodeLog.POINTER_FORKED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'pointer': {
                    'id': pointer.node._id,
                    'url': pointer.node.url,
                    'title': pointer.node.title,
                    'category': pointer.node.category,
                },
            },
            auth=auth,
        )

        # Return forked content
        return forked

    def get_recent_logs(self, n=10):
        """Return a list of the n most recent logs, in reverse chronological
        order.

        :param int n: Number of logs to retrieve

        """
        return list(reversed(self.logs)[:n])

    @property
    def date_modified(self):
        '''The most recent datetime when this node was modified, based on
        the logs.
        '''
        try:
            return self.logs[-1].date
        except IndexError:
            return None

    def set_title(self, title, auth, save=False):
        """Set the title of this Node and log it.

        :param str title: The new title.
        :param auth: All the auth information including user, API key.

        """
        original_title = self.title
        self.title = title
        self.add_log(
            action=NodeLog.EDITED_TITLE,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'title_new': self.title,
                'title_original': original_title,
            },
            auth=auth,
        )
        if save:
            self.save()
        return None

    def set_description(self, description, auth, save=False):
        """Set the description and log the event.

        :param str description: The new description
        :param auth: All the auth informtion including user, API key.
        :param bool save: Save self after updating.

        """
        original = self.description
        self.description = description
        if save:
            self.save()
        self.add_log(
            action=NodeLog.EDITED_DESCRIPTION,
            params={
                'project': self.parent_node,  # None if no parent
                'node': self._primary_key,
                'description_new': self.description,
                'description_original': original
            },
            auth=auth,
        )
        return None

    def update_search(self):
        import website.search.search as search
        search.update_node(self)

    def remove_node(self, auth, date=None):
        """Marks a node as deleted.

        TODO: Call a hook on addons
        Adds a log to the parent node if applicable

        :param auth: an instance of :class:`Auth`.
        :param date: Date node was removed
        :type date: `datetime.datetime` or `None`

        """
        # TODO: rename "date" param - it's shadowing a global


        if not self.can_edit(auth):
            raise PermissionsError()

        if [x for x in self.nodes_primary if not x.is_deleted]:
            raise NodeStateError("Any child components must be deleted prior to deleting this project.")

        log_date = date or datetime.datetime.utcnow()

        # Add log to parent
        if self.node__parent:
            self.node__parent[0].add_log(
                NodeLog.NODE_REMOVED,
                params={
                    'project': self._primary_key,
                },
                auth=auth,
                log_date=log_date,
            )

        # Remove self from parent registration list
        if self.is_registration:
            try:
                self.registered_from.registration_list.remove(self._primary_key)
            except ValueError:
                pass
            else:
                self.registered_from.save()

        # Remove self from parent fork list
        if self.is_fork:
            try:
                self.forked_from.fork_list.remove(self._primary_key)
            except ValueError:
                pass
            else:
                self.forked_from.save()

        self.is_deleted = True
        self.deleted_date = date
        self.save()

        return True

    def fork_node(self, auth, title='Fork of '):
        """Recursively fork a node.

        :param Auth auth: Consolidated authorization
        :param str title: Optional text to prepend to forked title
        :return: Forked node

        """
        user = auth.user

        # todo: should this raise an error?
        if not self.can_view(auth):
            return

        folder_old = os.path.join(settings.UPLOADS_PATH, self._primary_key)

        when = datetime.datetime.utcnow()

        original = self.load(self._primary_key)

        # Note: Cloning a node copies its `files_current` and
        # `wiki_pages_current` fields, but does not clone the underlying
        # database objects to which these dictionaries refer. This means that
        # the cloned node must pass itself to its file and wiki objects to
        # build the correct URLs to that content.
        forked = original.clone()

        forked.logs = self.logs
        forked.tags = self.tags

        for node_contained in original.nodes:
            forked_node = node_contained.fork_node(auth=auth, title='')
            if forked_node is not None:
                forked.nodes.append(forked_node)

        forked.title = title + forked.title
        forked.is_fork = True
        forked.is_registration = False
        forked.forked_date = when
        forked.forked_from = original
        forked.creator = user

        # Forks default to private status
        forked.is_public = False

        # Clear permissions before adding users
        forked.permissions = {}
        forked.visible_contributor_ids = []

        forked.add_contributor(contributor=user, log=False, save=False)

        forked.add_log(
            action=NodeLog.NODE_FORKED,
            params={
                'project': original.parent_id,
                'node': original._primary_key,
                'registration': forked._primary_key,
            },
            auth=auth,
            log_date=when,
            save=False,
        )

        forked.save()

        # After fork callback
        for addon in original.get_addons():
            _, message = addon.after_fork(original, forked, user)
            if message:
                status.push_status_message(message)

        if os.path.exists(folder_old):
            folder_new = os.path.join(settings.UPLOADS_PATH, forked._primary_key)
            Repo(folder_old).clone(folder_new)

        original.fork_list.append(forked._primary_key)
        original.save()

        return forked

    def register_node(self, schema, auth, template, data):
        """Make a frozen copy of a node.

        :param schema: Schema object
        :param auth: All the auth informtion including user, API key.
        :template: Template name
        :data: Form data

        """
        if not self.can_edit(auth):
            return

        folder_old = os.path.join(settings.UPLOADS_PATH, self._primary_key)
        template = urllib.unquote_plus(template)
        template = to_mongo(template)

        when = datetime.datetime.utcnow()

        original = self.load(self._primary_key)

        # Note: Cloning a node copies its `files_current` and
        # `wiki_pages_current` fields, but does not clone the underlying
        # database objects to which these dictionaries refer. This means that
        # the cloned node must pass itself to its file and wiki objects to
        # build the correct URLs to that content.
        registered = original.clone()

        registered.is_registration = True
        registered.registered_date = when
        registered.registered_user = auth.user
        registered.registered_schema = schema
        registered.registered_from = original
        if not registered.registered_meta:
            registered.registered_meta = {}
        registered.registered_meta[template] = data

        registered.contributors = self.contributors
        registered.forked_from = self.forked_from
        registered.creator = self.creator
        registered.logs = self.logs
        registered.tags = self.tags

        registered.save()

        # After register callback
        for addon in original.get_addons():
            _, message = addon.after_register(original, registered, auth.user)
            if message:
                status.push_status_message(message)

        if os.path.exists(folder_old):
            folder_new = os.path.join(settings.UPLOADS_PATH, registered._primary_key)
            Repo(folder_old).clone(folder_new)

        registered.nodes = []

        for node_contained in original.nodes:
            registered_node = node_contained.register_node(
                 schema, auth, template, data
            )
            if registered_node is not None:
                registered.nodes.append(registered_node)


        original.add_log(
            action=NodeLog.PROJECT_REGISTERED,
            params={
                'project':original.parent_id,
                'node':original._primary_key,
                'registration':registered._primary_key,
            },
            auth=auth,
            log_date=when,
        )
        original.registration_list.append(registered._id)
        original.save()

        registered.save()

        return registered

    def remove_tag(self, tag, auth, save=True):
        if tag in self.tags:
            self.tags.remove(tag)
            self.add_log(
                action=NodeLog.TAG_REMOVED,
                params={
                    'project':self.parent_id,
                    'node':self._primary_key,
                    'tag':tag,
                },
                auth=auth,
            )
            if save:
                self.save()

    def add_tag(self, tag, auth, save=True):
        if tag not in self.tags:
            new_tag = Tag.load(tag)
            if not new_tag:
                new_tag = Tag(_id=tag)
            new_tag.count_total += 1
            if self.is_public:
                new_tag.count_public += 1
            new_tag.save()
            self.tags.append(new_tag)
            self.add_log(
                action=NodeLog.TAG_ADDED,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                    'tag': tag,
                },
                auth=auth,
            )
            if save:
                self.save()

    def get_file(self, path, version=None):
        from website.addons.osffiles.model import NodeFile
        if version is not None:
            folder_name = os.path.join(settings.UPLOADS_PATH, self._primary_key)
            if os.path.exists(os.path.join(folder_name, ".git")):
                file_object = NodeFile.load(self.files_versions[path.replace('.', '_')][version])
                repo = Repo(folder_name)
                tree = repo.commit(file_object.git_commit).tree
                (mode, sha) = tree_lookup_path(repo.get_object, tree, path)
                return repo[sha].data, file_object.content_type
        return None, None

    def get_file_object(self, path, version=None):
        from website.addons.osffiles.model import NodeFile
        if version is not None:
            directory = os.path.join(settings.UPLOADS_PATH, self._primary_key)
            if os.path.exists(os.path.join(directory, '.git')):
                return NodeFile.load(self.files_versions[path.replace('.', '_')][version])
            # TODO: Raise exception here
        return None, None # TODO: Raise exception here

    def remove_file(self, auth, path):
        '''Removes a file from the filesystem, NodeFile collection, and does a git delete ('git rm <file>')

        :param auth: All the auth informtion including user, API key.
        :param path:

        :return: True on success, False on failure
        '''
        from website.addons.osffiles.model import NodeFile

        #FIXME: encoding the filename this way is flawed. For instance - foo.bar resolves to the same string as foo_bar.
        file_name_key = path.replace('.', '_')

        repo_path = os.path.join(settings.UPLOADS_PATH, self._primary_key)

        # TODO make sure it all works, otherwise rollback as needed
        # Do a git delete, which also removes from working filesystem.
        try:
            subprocess.check_output(
                ['git', 'rm', path],
                cwd=repo_path,
                shell=False
            )

            repo = Repo(repo_path)

            message = '{path} deleted'.format(path=path)
            committer = self._get_committer(auth)

            repo.do_commit(message, committer)

        except subprocess.CalledProcessError as error:
            # This exception can be ignored if the file has already been
            # deleted, e.g. if two users attempt to delete a file at the same
            # time. If another subprocess error is raised, fail.
            if error.returncode == 128 and 'did not match any files' in error.output:
                logger.warning(
                    'Attempted to delete file {0}, but file was not found.'.format(
                        path
                    )
                )
                return True
            return False

        if file_name_key in self.files_current:
            nf = NodeFile.load(self.files_current[file_name_key])
            nf.is_deleted = True
            nf.save()
            self.files_current.pop(file_name_key, None)

        if file_name_key in self.files_versions:
            for i in self.files_versions[file_name_key]:
                nf = NodeFile.load(i)
                nf.is_deleted = True
                nf.save()
            self.files_versions.pop(file_name_key)

        # Updates self.date_modified
        self.save()

        self.add_log(
            action=NodeLog.FILE_REMOVED,
            params={
                'project':self.parent_id,
                'node':self._primary_key,
                'path':path
            },
            auth=auth,
            log_date=nf.date_modified,
        )

        return True

    @staticmethod
    def _get_committer(auth):

        user = auth.user
        api_key = auth.api_key

        if api_key:
            commit_key_msg = ':{}'.format(api_key.label)
            if api_key.user:
                commit_name = api_key.user.fullname
                commit_id = api_key.user._primary_key
                commit_category = 'user'
            if api_key.node:
                commit_name = api_key.node.title
                commit_id = api_key.node._primary_key
                commit_category = 'node'

        elif user:
            commit_key_msg = ''
            commit_name = user.fullname
            commit_id = user._primary_key
            commit_category = 'user'

        else:
            raise Exception('Must provide either user or api_key.')

        committer = u'{name}{key_msg} <{category}-{id}@osf.io>'.format(
            name=commit_name,
            key_msg=commit_key_msg,
            category=commit_category,
            id=commit_id,
        )

        committer = normalize_unicode(committer)

        return committer

    def add_file(self, auth, file_name, content, size, content_type):
        """
        Instantiates a new NodeFile object, and adds it to the current Node as
        necessary.
        """
        from website.addons.osffiles.model import NodeFile
        # TODO: Reading the whole file into memory is not scalable. Fix this.

        # This node's folder
        folder_name = os.path.join(settings.UPLOADS_PATH, self._primary_key)

        # TODO: This should be part of the build phase, not here.
        # verify the upload root exists
        if not os.path.isdir(settings.UPLOADS_PATH):
            os.mkdir(settings.UPLOADS_PATH)

        # Make sure the upload directory contains a git repo.
        if os.path.exists(folder_name):
            if os.path.exists(os.path.join(folder_name, ".git")):
                repo = Repo(folder_name)
            else:
                # ... or create one
                repo = Repo.init(folder_name)
        else:
            # if the Node's folder isn't there, create it.
            os.mkdir(folder_name)
            repo = Repo.init(folder_name)

        # Is this a new file, or are we updating an existing one?
        file_is_new = not os.path.exists(os.path.join(folder_name, file_name))

        if not file_is_new:
            # Get the hash of the old file
            old_file_hash = hashlib.md5()
            with open(os.path.join(folder_name, file_name), 'rb') as f:
                for chunk in iter(
                        lambda: f.read(128 * old_file_hash.block_size),
                        b''
                ):
                    old_file_hash.update(chunk)

            # If the file hasn't changed
            if old_file_hash.digest() == hashlib.md5(content).digest():
                raise FileNotModified()

        # Write the content of the temp file into a new file
        with open(os.path.join(folder_name, file_name), 'wb') as f:
            f.write(content)

        # Deal with git
        repo.stage([file_name])

        committer = self._get_committer(auth)

        commit_id = repo.do_commit(
            message=unicode(file_name +
                            (' added' if file_is_new else ' updated')),
            committer=committer,
        )

        # Deal with creating a NodeFile in the database
        node_file = NodeFile(
            path=file_name,
            filename=file_name,
            size=size,
            node=self,
            uploader=auth.user,
            git_commit=commit_id,
            content_type=content_type,
        )
        node_file.save()

        # Add references to the NodeFile to the Node object
        file_name_key = node_file.clean_filename

        # Reference the current file version
        self.files_current[file_name_key] = node_file._primary_key

        # Create a version history if necessary
        if not file_name_key in self.files_versions:
            self.files_versions[file_name_key] = []

        # Add reference to the version history
        self.files_versions[file_name_key].append(node_file._primary_key)

        self.add_log(
            action=NodeLog.FILE_ADDED if file_is_new else NodeLog.FILE_UPDATED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'path': node_file.path,
                'version': len(self.files_versions),
                'urls': {
                    'view': node_file.url(self),
                    'download': node_file.download_url(self),
                },
            },
            auth=auth,
            log_date=node_file.date_uploaded
        )

        return node_file

    def add_log(self, action, params, auth, foreign_user=None, log_date=None, save=True):
        user = auth.user if auth else None
        api_key = auth.api_key if auth else None
        log = NodeLog(
            action=action,
            user=user,
            foreign_user=foreign_user,
            api_key=api_key,
            params=params,
        )
        if log_date:
            log.date = log_date
        log.save()
        self.logs.append(log)
        if save:
            self.save()
        if user:
            increment_user_activity_counters(user._primary_key, action, log.date)
        if self.node__parent:
            parent = self.node__parent[0]
            parent.logs.append(log)
            parent.save()
        return log

    @property
    def url(self):
        return '/{}/'.format(self._primary_key)

    def web_url_for(self, view_name, _absolute=False, *args, **kwargs):
        # Note: Check `parent_node` rather than `category` to avoid database
        # inconsistencies [jmcarp]
        if self.parent_node is None:
            return web_url_for(view_name, pid=self._primary_key, _absolute=_absolute,
                *args, **kwargs)
        else:
            return web_url_for(view_name, pid=self.parent_node._primary_key,
                nid=self._primary_key, _absolute=_absolute, *args, **kwargs)

    def api_url_for(self, view_name, _absolute=False, *args, **kwargs):
        # Note: Check `parent_node` rather than `category` to avoid database
        # inconsistencies [jmcarp]
        if self.parent_node is None:
            return api_url_for(view_name, pid=self._primary_key, _absolute=_absolute,
                *args, **kwargs)
        else:
            return api_url_for(view_name, pid=self.parent_node._primary_key,
                nid=self._primary_key, _absolute=_absolute, *args, **kwargs)

    @property
    def absolute_url(self):
        if not self.url:
            logging.error("Node {0} has a parent that is not a project".format(self._id))
            return None
        return urlparse.urljoin(settings.DOMAIN, self.url)

    @property
    def display_absolute_url(self):
        url = self.absolute_url
        if url is not None:
            return re.sub(r'https?:', '', url).strip('/')

    @property
    def api_url(self):
        if not self.url:
            logging.error('Node {0} has a parent that is not a project'.format(self._id))
            return None
        return '/api/v1{0}'.format(self.deep_url)

    @property
    def deep_url(self):
        if self.category == 'project':
            return '/project/{}/'.format(self._primary_key)
        else:
            if self.node__parent and self.node__parent[0].category == 'project':
                return '/project/{}/node/{}/'.format(
                    self.parent_id,
                    self._primary_key
                )
        logging.error("Node {0} has a parent that is not a project".format(self._id))

    def author_list(self, and_delim='&'):
        author_names = [
            author.biblio_name
            for author in self.visible_contributors
            if author
        ]
        if len(author_names) < 2:
            return ' {0} '.format(and_delim).join(author_names)
        if len(author_names) > 7:
            author_names = author_names[:7]
            author_names.append('et al.')
            return ', '.join(author_names)
        return u'{0}, {1} {2}'.format(
            ', '.join(author_names[:-1]),
            and_delim,
            author_names[-1]
        )

    @property
    def templated_list(self):
        return [
            x
            for x in self.node__template_node
            if not x.is_deleted
        ]

    @property
    def citation_apa(self):
        return u'{authors}, ({year}). {title}. Retrieved from Open Science Framework, <a href="{url}">{display_url}</a>'.format(
            authors=self.author_list(and_delim='&'),
            year=self.logs[-1].date.year if self.logs else '?',
            title=self.title,
            url=self.url,
            display_url=self.display_absolute_url,
        )

    @property
    def citation_mla(self):
        return u'{authors}. "{title}". Open Science Framework, {year}. <a href="{url}">{display_url}</a>'.format(
            authors=self.author_list(and_delim='and'),
            year=self.logs[-1].date.year if self.logs else '?',
            title=self.title,
            url=self.url,
            display_url=self.display_absolute_url,
        )

    @property
    def citation_chicago(self):
        return u'{authors}. "{title}". Open Science Framework ({year}). <a href="{url}">{display_url}</a>'.format(
            authors=self.author_list(and_delim='and'),
            year=self.logs[-1].date.year if self.logs else '?',
            title=self.title,
            url=self.url,
            display_url=self.display_absolute_url,
        )

    @property
    def parent_node(self):
        """The parent node, if it exists, otherwise ``None``. Note: this
        property is named `parent_node` rather than `parent` to avoid a
        conflict with the `parent` back-reference created by the `nodes`
        field on this schema.

        """
        try:
            if not self.node__parent[0].is_deleted:
                return self.node__parent[0]
        except IndexError:
            pass
        return None

    @property
    def watch_url(self):
        return os.path.join(self.api_url, "watch/")

    @property
    def parent_id(self):
        if self.node__parent:
            return self.node__parent[0]._primary_key
        return None

    @property
    def project_or_component(self):
        return 'project' if self.category == 'project' else 'component'

    def is_contributor(self, user):
        return (
            user is not None
            and (
                user._id in self.contributors
            )
        )

    def add_addon(self, addon_name, auth, log=True):
        """Add an add-on to the node.

        :param str addon_name: Name of add-on
        :param Auth auth: Consolidated authorization object
        :param bool log: Add a log after adding the add-on
        :return bool: Add-on was added

        """
        rv = super(Node, self).add_addon(addon_name, auth)
        if rv and log:
            config = settings.ADDONS_AVAILABLE_DICT[addon_name]
            self.add_log(
                action=NodeLog.ADDON_ADDED,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                    'addon': config.full_name,
                },
                auth=auth,
            )
        return rv

    def delete_addon(self, addon_name, auth):
        """Delete an add-on from the node.

        :param str addon_name: Name of add-on
        :param Auth auth: Consolidated authorization object
        :return bool: Add-on was deleted

        """
        rv = super(Node, self).delete_addon(addon_name, auth)
        if rv:
            config = settings.ADDONS_AVAILABLE_DICT[addon_name]
            self.add_log(
                action=NodeLog.ADDON_REMOVED,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                    'addon': config.full_name,
                },
                auth=auth,
            )
        return rv

    def callback(self, callback, recursive=False, *args, **kwargs):
        """Invoke callbacks of attached add-ons and collect messages.

        :param str callback: Name of callback method to invoke
        :param bool recursive: Apply callback recursively over nodes
        :return list: List of callback messages

        """
        messages = []

        for addon in self.get_addons():
            method = getattr(addon, callback)
            message = method(self, *args, **kwargs)
            if message:
                messages.append(message)

        if recursive:
            for child in self.nodes:
                if not child.is_deleted:
                    messages.extend(
                        child.callback(
                            callback, recursive, *args, **kwargs
                        )
                    )

        return messages

    def get_pointers(self):
        pointers = self.nodes_pointer
        for node in self.nodes:
            pointers.extend(node.get_pointers())
        return pointers

    def replace_contributor(self, old, new):
        for i, contrib in enumerate(self.contributors):
            if contrib._primary_key == old._primary_key:
                self.contributors[i] = new
                # Remove unclaimed record for the project
                if self._primary_key in old.unclaimed_records:
                    del old.unclaimed_records[self._primary_key]
                    old.save()
                for permission in self.get_permissions(old):
                    self.add_permission(new, permission)
                self.permissions.pop(old._id)
                if old._id in self.visible_contributor_ids:
                    self.visible_contributor_ids.remove(old._id)
                return True
        return False

    def remove_contributor(self, contributor, auth, log=True):
        """Remove a contributor from this node.

        :param contributor: User object, the contributor to be removed
        :param auth: All the auth information including user, API key.

        """
        # remove unclaimed record if necessary
        if self._primary_key in contributor.unclaimed_records:
            del contributor.unclaimed_records[self._primary_key]

        self.contributors.remove(contributor._id)

        self.clear_permission(contributor)
        if contributor._id in self.visible_contributor_ids:
            self.visible_contributor_ids.remove(contributor._id)

        # Node must have at least one registered admin user
        # TODO: Move to validator or helper
        admins = [
            user for user in self.contributors
            if self.has_permission(user, 'admin')
                and user.is_registered
        ]
        if not admins:
            return False

        # Clear permissions for removed user
        self.permissions.pop(contributor._id, None)

        self.save()

        # After remove callback
        for addon in self.get_addons():
            message = addon.after_remove_contributor(self, contributor)
            if message:
                status.push_status_message(message)

        if log:
            self.add_log(
                action=NodeLog.CONTRIB_REMOVED,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                    'contributor': contributor._id,
                },
                auth=auth,
            )

        return True

    def remove_contributors(self, contributors, auth=None, log=True, save=False):

        results = []
        removed = []

        for contrib in contributors:
            outcome = self.remove_contributor(
                contributor=contrib, auth=auth, log=False,
            )
            results.append(outcome)
            removed.append(contrib._id)
        if log:
            self.add_log(
                action=NodeLog.CONTRIB_REMOVED,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                    'contributors': removed,
                },
                auth=auth,
                save=save,
            )

        if save:
            self.save()

        if False in results:
            return False

        return True

    def manage_contributors(self, user_dicts, auth, save=False):
        """Reorder and remove contributors.

        :param list user_dicts: Ordered list of contributors represented as
            dictionaries of the form:
            {'id': <id>, 'permission': <One of 'read', 'write', 'admin'>}
        :param Auth auth: Consolidated authentication information
        :param bool save: Save changes
        :raises: ValueError if any users in `users` not in contributors or if
            no admin contributors remaining

        """
        users = []
        permissions_changed = {}
        for user_dict in user_dicts:
            user = User.load(user_dict['id'])
            if user is None:
                raise ValueError('User not found')
            if user not in self.contributors:
                raise ValueError(
                    'User {0} not in contributors'.format(user.fullname)
                )
            permissions = expand_permissions(user_dict['permission'])
            if set(permissions) != set(self.get_permissions(user)):
                self.set_permissions(user, permissions, save=False)
                permissions_changed[user._id] = permissions
            self.set_visible(user, user_dict['visible'])
            users.append(user)

        to_retain = [
            user for user in self.contributors
            if user in users
        ]
        to_remove = [
            user for user in self.contributors
            if user not in users
        ]

        # TODO: Move to validator or helper @jmcarp
        # TODO: Test me @jmcarp
        admins = [
            user for user in users
            if self.has_permission(user, 'admin')
                and user.is_registered
        ]
        if users is None or not admins:
            raise ValueError(
                'Must have at least one registered admin contributor'
            )

        # TODO: Test me @jmcarp
        if to_retain != users:
            self.add_log(
                action=NodeLog.CONTRIB_REORDERED,
                params={
                    'project': self.parent_id,
                    'node': self._id,
                    'contributors': [
                        user._id
                        for user in users
                    ],
                },
                auth=auth,
                save=save,
            )

        if to_remove:
            self.remove_contributors(to_remove, auth=auth, save=False)

        self.contributors = users

        if permissions_changed:
            self.add_log(
                action=NodeLog.PERMISSIONS_UPDATED,
                params={
                    'project': self.parent_id,
                    'node': self._id,
                    'contributors': permissions_changed,
                },
                auth=auth,
                save=save,
            )

        if save:
            self.save()

    def add_contributor(self, contributor, permissions=None, visible=True,
                        auth=None, log=True, save=False):
        """Add a contributor to the project.

        :param User contributor: The contributor to be added
        :param list permissions: Permissions to grant to the contributor
        :param bool visible: Contributor is visible in project dashboard
        :param Auth auth: All the auth information including user, API key
        :param bool log: Add log to self
        :param bool save: Save after adding contributor
        :returns: Whether contributor was added

        """
        MAX_RECENT_LENGTH = 15

        # If user is merged into another account, use master account
        contrib_to_add = contributor.merged_by if contributor.is_merged else contributor
        if contrib_to_add not in self.contributors:

            self.contributors.append(contrib_to_add)
            if visible:
                self.set_visible(contrib_to_add, visible=True)

            # Add default contributor permissions
            permissions = permissions or DEFAULT_CONTRIBUTOR_PERMISSIONS
            for permission in permissions:
                self.add_permission(contrib_to_add, permission, save=False)

            # Add contributor to recently added list for user
            if auth is not None:
                user = auth.user
                if contrib_to_add in user.recently_added:
                    user.recently_added.remove(contrib_to_add)
                user.recently_added.insert(0, contrib_to_add)
                while len(user.recently_added) > MAX_RECENT_LENGTH:
                    user.recently_added.pop()

            if log:
                self.add_log(
                    action=NodeLog.CONTRIB_ADDED,
                    params={
                        'project': self.parent_id,
                        'node': self._primary_key,
                        'contributors': [contrib_to_add._primary_key],
                    },
                    auth=auth,
                    save=save,
                )
            if save:
                self.save()

            contributor_added.send(self, contributor=contributor, auth=auth)
            return True
        else:
            return False

    def add_contributors(self, contributors, auth=None, log=True, save=False):
        """Add multiple contributors

        :param contributors: A list of User objects to add as contributors.
        :param auth: All the auth information including user, API key.
        :param log: Add log to self
        :param save: Save after adding contributor

        """
        for contrib in contributors:
            self.add_contributor(
                contributor=contrib['user'], permissions=contrib['permissions'],
                visible=contrib['visible'], auth=auth, log=False, save=False,
            )
        if log and contributors:
            self.add_log(
                action=NodeLog.CONTRIB_ADDED,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                    'contributors': [
                        contrib['user']._id
                        for contrib in contributors
                    ],
                },
                auth=auth,
                save=save,
            )
        if save:
            self.save()

    def add_unregistered_contributor(self, fullname, email, auth,
                                     permissions=None, save=False):
        """Add a non-registered contributor to the project.

        :param str fullname: The full name of the person.
        :param str email: The email address of the person.
        :param Auth auth: Auth object for the user adding the contributor.
        :returns: The added contributor

        :raises: DuplicateEmailError if user with given email is already in the database.

        """
        # Create a new user record
        contributor = User.create_unregistered(fullname=fullname, email=email)

        contributor.add_unclaimed_record(node=self, referrer=auth.user,
            given_name=fullname, email=email)
        try:
            contributor.save()
        except ValidationValueError:  # User with same email already exists
            contributor = get_user(username=email)
            # Unregistered users may have multiple unclaimed records, so
            # only raise error if user is registered.
            if contributor.is_registered or self.is_contributor(contributor):
                raise
            contributor.add_unclaimed_record(node=self, referrer=auth.user,
                given_name=fullname, email=email)
            contributor.save()

        self.add_contributor(
            contributor, permissions=permissions, auth=auth,
            log=True, save=save,
        )
        return contributor

    def set_privacy(self, permissions, auth=None):
        """Set the permissions for this node.

        :param permissions: A string, either 'public' or 'private'
        :param auth: All the auth informtion including user, API key.

        """
        if permissions == 'public' and not self.is_public:
            self.is_public = True
            # If the node doesn't have a piwik site, make one.
            if settings.PIWIK_HOST:
                piwik.update_node(self)
        elif permissions == 'private' and self.is_public:
            self.is_public = False
        else:
            return False

        # After set permissions callback
        for addon in self.get_addons():
            message = addon.after_set_privacy(self, permissions)
            if message:
                status.push_status_message(message)

        action = NodeLog.MADE_PUBLIC if permissions == 'public' else NodeLog.MADE_PRIVATE
        self.add_log(
            action=action,
            params={
                'project':self.parent_id,
                'node':self._primary_key,
            },
            auth=auth,
        )
        return True

    # TODO: Move to wiki add-on
    def get_wiki_page(self, page, version=None):
        from website.addons.wiki.model import NodeWikiPage

        page = urllib.unquote_plus(page)
        page = to_mongo(page)

        page = str(page).lower()
        if version:
            try:
                version = int(version)
            except:
                return None

            if not page in self.wiki_pages_versions:
                return None

            if version > len(self.wiki_pages_versions[page]):
                return None
            else:
                return NodeWikiPage.load(self.wiki_pages_versions[page][version-1])

        if page in self.wiki_pages_current:
            pw = NodeWikiPage.load(self.wiki_pages_current[page])
        else:
            pw = None

        return pw

    # TODO: Move to wiki add-on
    def update_node_wiki(self, page, content, auth):
        """Update the node's wiki page with new content.

        :param page: A string, the page's name, e.g. ``"home"``.
        :param content: A string, the posted content.
        :param auth: All the auth informtion including user, API key.

        """
        from website.addons.wiki.model import NodeWikiPage

        temp_page = page

        page = urllib.unquote_plus(page)
        page = to_mongo(page)
        page = str(page).lower()

        if page not in self.wiki_pages_current:
            version = 1
        else:
            current = NodeWikiPage.load(self.wiki_pages_current[page])
            current.is_current = False
            version = current.version + 1
            current.save()

        v = NodeWikiPage(
            page_name=temp_page,
            version=version,
            user=auth.user,
            is_current=True,
            node=self,
            content=content
        )
        v.save()

        if page not in self.wiki_pages_versions:
            self.wiki_pages_versions[page] = []
        self.wiki_pages_versions[page].append(v._primary_key)
        self.wiki_pages_current[page] = v._primary_key

        self.add_log(
            action=NodeLog.WIKI_UPDATED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'page': v.page_name,
                'version': v.version,
            },
            auth=auth,
            log_date=v.date
        )

    def get_stats(self, detailed=False):
        if detailed:
            raise NotImplementedError(
                'Detailed stats exist, but are not yet implemented.'
            )
        else:
            return get_basic_counters('node:%s' % self._primary_key)

    def serialize(self):
        # TODO: incomplete implementation
        return {
            'id': str(self._primary_key),
            'category': self.project_or_component,
            'url': self.url,
            # TODO: Titles shouldn't contain escaped HTML in the first place
            'title': html_parser.unescape(self.title),
            'api_url': self.api_url,
            'is_public': self.is_public,
        }


@Node.subscribe('before_save')
def validate_permissions(schema, instance):
    """Ensure that user IDs in `contributors` and `permissions` match.

    """
    node = instance
    contributor_ids = set([user._id for user in node.contributors])
    permission_ids = set(node.permissions.keys())
    mismatched_contributors = contributor_ids.difference(permission_ids)
    if mismatched_contributors:
        raise ValidationValueError(
            'Contributors {0} missing from `permissions` on node {1}'.format(
                ', '.join(mismatched_contributors),
                node._id,
            )
        )
    mismatched_permissions = permission_ids.difference(contributor_ids)
    if mismatched_permissions:
        raise ValidationValueError(
            'Permission keys {0} missing from `contributors` on node {1}'.format(
                ', '.join(mismatched_contributors),
                node._id,
            )
        )


@Node.subscribe('before_save')
def validate_visible_contributors(schema, instance):
    """Ensure that user IDs in `contributors` and `visible_contributor_ids`
    match.

    """
    node = instance
    for user_id in node.visible_contributor_ids:
        if user_id not in node.contributors:
            raise ValidationValueError(
                ('User {0} is in `visible_contributor_ids` but not in '
                 '`contributors` on node {1}').format(
                    user_id,
                    node._id,
                )
            )


class WatchConfig(StoredObject):

    _id = fields.StringField(primary=True, default=lambda: str(ObjectId()))
    node = fields.ForeignField('Node', backref='watched')
    digest = fields.BooleanField(default=False)
    immediate = fields.BooleanField(default=False)


class MailRecord(StoredObject):

    _id = fields.StringField(primary=True, default=lambda: str(ObjectId()))
    data = fields.DictionaryField()
    records = fields.AbstractForeignField(list=True, backref='created')


class PrivateLink(StoredObject):

    _id = fields.StringField(primary=True, default=lambda: str(ObjectId()))
    date_created = fields.DateTimeField(auto_now_add=datetime.datetime.utcnow)
    key = fields.StringField(required=True)
    name = fields.StringField()
    is_deleted = fields.BooleanField(default=False)

    nodes = fields.ForeignField('node', list=True, backref='shared')
    creator = fields.ForeignField('user', backref='created')

    @property
    def node_ids(self):
        node_ids = [node._id for node in self.nodes]
        return node_ids

    def node_scale(self, node):
        if node.parent_id not in self.node_id_lists:
            return 0
        else:
            return 20 + self.node_scale(node.parent_node)

    def to_json(self):
        return {
            "id": self._id,
            "date_created": self.date_created.strftime('%m/%d/%Y %I:%M %p UTC'),
            "key": self.key,
            "name": self.name,
            "creator": self.creator.fullname,
            "nodes": [{'title': x.title, 'url': x.url, 'scale': str(self.node_scale(x)) + 'px'} for x in self.nodes],
        }

