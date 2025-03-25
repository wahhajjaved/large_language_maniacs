import functools
import itertools
import logging
import operator
import re
import urlparse
import warnings

from django.apps import apps
from django.contrib.contenttypes.fields import GenericRelation
from datetime import datetime

import pytz
from dirtyfields import DirtyFieldsMixin
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from keen import scoped_keys
from modularodm import Q as MQ
from osf_models.apps import AppConfig as app_config
from osf_models.models.citation import AlternativeCitation
from osf_models.models.contributor import Contributor, RecentlyAddedContributor, get_contributor_permissions
from osf_models.models.identifiers import Identifier
from osf_models.models.identifiers import IdentifierMixin
from osf_models.models.mixins import Loggable, Taggable, AddonModelMixin, NodeLinkMixin
from osf_models.models.tag import Tag
from osf_models.models.nodelog import NodeLog
from osf_models.models.mixins import CommentableMixin
from osf_models.models.sanctions import RegistrationApproval
from osf_models.models.user import OSFUser
from osf_models.models.spam import SpamMixin
from osf_models.models.subject import Subject
from osf_models.models.preprint_provider import PreprintProvider
from osf_models.models.validators import validate_title, validate_doi
from osf_models.modm_compat import Q
from osf_models.utils.auth import Auth, get_user
from osf_models.utils.base import api_v2_url
from osf_models.utils.datetime_aware_jsonfield import DateTimeAwareJSONField
from osf_models.exceptions import ValidationValueError
from typedmodels.models import TypedModel

from framework import status
from framework.mongo.utils import to_mongo_key
from framework.exceptions import PermissionsError
from framework.sentry import log_exception
from website import settings, language
from website.project.model import NodeUpdateError
from website.exceptions import (
    UserNotAffiliatedError,
    NodeStateError,
    InvalidTagError,
    TagNotFoundError,
)
from website.project import signals as project_signals
from website.citations.utils import datetime_to_csl
from website.util import api_url_for
from website.util import web_url_for
from website.util import sanitize
from website.util.permissions import (
    expand_permissions,
    reduce_permissions,
    DEFAULT_CONTRIBUTOR_PERMISSIONS,
    CREATOR_PERMISSIONS,
    READ,
    WRITE,
    ADMIN,
)
from .base import BaseModel, GuidMixin, Guid

logger = logging.getLogger(__name__)


class AbstractNode(DirtyFieldsMixin, TypedModel, AddonModelMixin, IdentifierMixin,
                   NodeLinkMixin, CommentableMixin, SpamMixin,
                   Taggable, Loggable, GuidMixin, BaseModel):
    """
    All things that inherit from AbstractNode will appear in
    the same table and will be differentiated by the `type` column.
    """

    class Meta:
        order_with_respect_to = 'parent_node'

    #: Whether this is a pointer or not
    primary = True

    FIELD_ALIASES = {
        'contributors': '_contributors',
    }

    CATEGORY_MAP = {
        'analysis': 'Analysis',
        'communication': 'Communication',
        'data': 'Data',
        'hypothesis': 'Hypothesis',
        'instrumentation': 'Instrumentation',
        'methods and measures': 'Methods and Measures',
        'procedure': 'Procedure',
        'project': 'Project',
        'software': 'Software',
        'other': 'Other',
        '': 'Uncategorized',
    }

    # Node fields that trigger an update to Solr on save
    SEARCH_UPDATE_FIELDS = {
        'title',
        'category',
        'description',
        'visible_contributor_ids',
        'tags',
        'is_fork',
        'is_registration',
        'retraction',
        'embargo',
        'is_public',
        'is_deleted',
        'wiki_pages_current',
        'is_retracted',
        'node_license',
        '_affiliated_institutions',
        'preprint_file',
    }

    # Node fields that trigger a check to the spam filter on save
    SPAM_CHECK_FIELDS = {
        'title',
        'description',
        'wiki_pages_current',
    }

    # Fields that are writable by Node.update
    WRITABLE_WHITELIST = [
        'title',
        'description',
        'category',
        'is_public',
        'node_license',
    ]

    # Named constants
    PRIVATE = 'private'
    PUBLIC = 'public'

    affiliated_institutions = models.ManyToManyField('Institution', related_name='nodes')
    alternative_citations = models.ManyToManyField(AlternativeCitation, related_name='nodes')
    category = models.CharField(max_length=255,
                                choices=CATEGORY_MAP.items(),
                                blank=True,
                                default='')
    # Dictionary field mapping user id to a list of nodes in node.nodes which the user has subscriptions for
    # {<User.id>: [<Node._id>, <Node2._id>, ...] }
    # TODO: Can this be a reference instead of data?
    child_node_subscriptions = DateTimeAwareJSONField(default=dict, blank=True)
    _contributors = models.ManyToManyField(OSFUser,
                                           through=Contributor,
                                           related_name='nodes')

    @property
    def contributors(self):
        # NOTE: _order field is generated by order_with_respect_to = 'node'
        return self._contributors.order_by('contributor___order')

    creator = models.ForeignKey(OSFUser,
                                db_index=True,
                                related_name='created',
                                on_delete=models.SET_NULL,
                                null=True, blank=True)
    # TODO: Uncomment auto_* attributes after migration is complete
    date_created = models.DateTimeField(default=timezone.now)  # auto_now_add=True)
    date_modified = models.DateTimeField(db_index=True, null=True, blank=True)  # auto_now=True)
    deleted_date = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    file_guid_to_share_uuids = DateTimeAwareJSONField(default=dict, blank=True)
    forked_date = models.DateTimeField(db_index=True, null=True, blank=True)
    forked_from = models.ForeignKey('self',
                                    related_name='forks',
                                    on_delete=models.SET_NULL,
                                    null=True, blank=True)
    is_fork = models.BooleanField(default=False, db_index=True)
    is_public = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    node_license = models.ForeignKey('NodeLicenseRecord', related_name='nodes',
                                     on_delete=models.SET_NULL, null=True, blank=True)
    parent_node = models.ForeignKey('self',
                                    related_name='nodes',
                                    on_delete=models.SET_NULL,
                                    null=True, blank=True)
    # permissions = Permissions are now on contributors
    piwik_site_id = models.IntegerField(null=True, blank=True)
    public_comments = models.BooleanField(default=True)
    primary_institution = models.ForeignKey(
        'Institution',
        related_name='primary_nodes',
        null=True, blank=True)
    root = models.ForeignKey('self',
                             related_name='absolute_parent',
                             on_delete=models.SET_NULL,
                             null=True, blank=True)
    suspended = models.BooleanField(default=False, db_index=True)

    # The node (if any) used as a template for this node's creation
    template_node = models.ForeignKey('self',
                                      related_name='templated_from',
                                      on_delete=models.SET_NULL,
                                      null=True, blank=True)
    title = models.TextField(
        validators=[validate_title]
    )  # this should be a charfield but data from mongo didn't fit in 255
    # TODO why is this here if it's empty
    users_watching_node = models.ManyToManyField(OSFUser, related_name='watching')
    wiki_pages_current = DateTimeAwareJSONField(default=dict, blank=True)
    wiki_pages_versions = DateTimeAwareJSONField(default=dict, blank=True)
    # Dictionary field mapping node wiki page to sharejs private uuid.
    # {<page_name>: <sharejs_id>}
    wiki_private_uuids = DateTimeAwareJSONField(default=dict, blank=True)

    identifiers = GenericRelation(Identifier, related_query_name='nodes')

    # Preprint fields
    # TODO: Uncomment when StoredFileNode is implemented
    # preprint_file = fields.ForeignField('StoredFileNode')
    preprint_created = models.DateTimeField(null=True, blank=True)
    preprint_subjects = models.ManyToManyField(Subject, related_name='preprints')
    preprint_providers = models.ManyToManyField(PreprintProvider, related_name='preprints')
    preprint_doi = models.CharField(max_length=128, null=True, blank=True, validators=[validate_doi])
    _is_preprint_orphan = models.NullBooleanField(default=False)

    def __init__(self, *args, **kwargs):
        self._parent = kwargs.pop('parent', None)
        super(AbstractNode, self).__init__(*args, **kwargs)

    def __unicode__(self):
        return u'{} : ({})'.format(self.title, self._id)

    @property
    def is_registration(self):
        """For v1 compat."""
        return False

    @property
    def is_preprint(self):
        # TODO: This is a temporary implementation.
        # Uncomment when StoredFileNode is implemented
        # if not self.preprint_file or not self.is_public:
        #     return False
        # if self.preprint_file.node == self:
        #     return True
        # else:
        #     self._is_preprint_orphan = True
        #     return False
        return bool(self.preprint_created)

    @property
    def preprint_file(self):
        return None

    @property
    def is_preprint_orphan(self):
        """For v1 compat."""
        return False

    @property
    def is_collection(self):
        """For v1 compat"""
        return False

    @property  # TODO Separate out for submodels
    def absolute_api_v2_url(self):
        if self.is_registration:
            path = '/registrations/{}/'.format(self._id)
            return api_v2_url(path)
        if self.is_collection:
            path = '/collections/{}/'.format(self._id)
            return api_v2_url(path)
        path = '/nodes/{}/'.format(self._id)
        return api_v2_url(path)

    @property
    def absolute_url(self):
        if not self.url:
            return None
        return urlparse.urljoin(app_config.domain, self.url)

    @property
    def deep_url(self):
        return '/project/{}/'.format(self._primary_key)

    @property
    def sanction(self):
        """For v1 compat. Registration has the proper implementation of this property."""
        return None

    @property
    def is_retracted(self):
        """For v1 compat."""
        return False

    @property
    def is_pending_registration(self):
        """For v1 compat."""
        return False

    @property
    def is_pending_retraction(self):
        """For v1 compat."""
        return False

    @property
    def is_pending_embargo(self):
        """For v1 compat."""
        return False

    @property
    def is_embargoed(self):
        """For v1 compat."""
        return False

    @property
    def archiving(self):
        """For v1 compat."""
        return False

    @property
    def embargo_end_date(self):
        """For v1 compat."""
        return False

    @property
    def forked_from_guid(self):
        if self.forked_from:
            return self.forked_from._id
        return None

    @property
    def linked_nodes_self_url(self):
        return self.absolute_api_v2_url + 'relationships/linked_nodes/'

    @property
    def linked_registrations_self_url(self):
        return self.absolute_api_v2_url + 'relationships/linked_registrations/'

    @property
    def linked_nodes_related_url(self):
        return self.absolute_api_v2_url + 'linked_nodes/'

    @property
    def linked_registrations_related_url(self):
        return self.absolute_api_v2_url + 'linked_registrations/'

    @property
    def institutions_url(self):
        return self.absolute_api_v2_url + 'institutions/'

    @property
    def institutions_relationship_url(self):
        return self.absolute_api_v2_url + 'relationships/institutions/'

    # For Comment API compatibility
    @property
    def target_type(self):
        """The object "type" used in the OSF v2 API."""
        return 'nodes'

    @property
    def root_target_page(self):
        """The comment page type associated with Nodes."""
        Comment = apps.get_model('osf_models.Comment')
        return Comment.OVERVIEW

    def belongs_to_node(self, node_id):
        """Check whether this node matches the specified node."""
        return self._id == node_id

    @property
    def category_display(self):
        """The human-readable representation of this node's category."""
        return settings.NODE_CATEGORY_MAP[self.category]

    @property
    def url(self):
        return '/{}/'.format(self._primary_key)

    @property
    def api_url(self):
        if not self.url:
            logger.error('Node {0} has a parent that is not a project'.format(self._id))
            return None
        return '/api/v1{0}'.format(self.deep_url)

    @property
    def display_absolute_url(self):
        url = self.absolute_url
        if url is not None:
            return re.sub(r'https?:', '', url).strip('/')

    @property
    def nodes_active(self):
        linked_node_ids = list(self.linked_nodes.filter(is_deleted=False).values_list('pk', flat=True))
        node_ids = list(self.nodes.filter(is_deleted=False).values_list('pk', flat=True))
        return AbstractNode.objects.filter(
            id__in=node_ids + linked_node_ids
        )

    def web_url_for(self, view_name, _absolute=False, _guid=False, *args, **kwargs):
        return web_url_for(view_name, pid=self._primary_key,
                           _absolute=_absolute, _guid=_guid, *args, **kwargs)

    def api_url_for(self, view_name, _absolute=False, *args, **kwargs):
        return api_url_for(view_name, pid=self._primary_key, _absolute=_absolute, *args, **kwargs)

    @property
    def project_or_component(self):
        # The distinction is drawn based on whether something has a parent node, rather than by category
        return 'project' if not self.parent_node else 'component'

    @property
    def templated_list(self):
        return self.templated_from.filter(is_deleted=False)

    @property
    def draft_registrations_active(self):
        DraftRegistration = apps.get_model('osf_models.DraftRegistration')
        return DraftRegistration.objects.filter(
            models.Q(branched_from=self) &
            (models.Q(registered_node=None) | models.Q(registered_node__is_deleted=True))
        )

    @property
    def has_active_draft_registrations(self):
        return self.draft_registrations_active.exists()

    @property
    def csl(self):  # formats node information into CSL format for citation parsing
        """a dict in CSL-JSON schema

        For details on this schema, see:
            https://github.com/citation-style-language/schema#csl-json-schema
        """
        csl = {
            'id': self._id,
            'title': sanitize.unescape_entities(self.title),
            'author': [
                contributor.csl_name  # method in auth/model.py which parses the names of authors
                for contributor in self.visible_contributors
            ],
            'publisher': 'Open Science Framework',
            'type': 'webpage',
            'URL': self.display_absolute_url,
        }

        doi = self.get_identifier_value('doi')
        if doi:
            csl['DOI'] = doi

        if self.logs:
            csl['issued'] = datetime_to_csl(self.logs.latest().date)

        return csl

    def update_search(self):
        from website import search

        try:
            search.search.update_node(self, bulk=False, async=True)
        except search.exceptions.SearchUnavailableError as e:
            logger.exception(e)
            log_exception()

    def delete_search_entry(self):
        from website import search
        try:
            search.search.delete_node(self)
        except search.exceptions.SearchUnavailableError as e:
            logger.exception(e)
            log_exception()

    def is_affiliated_with_institution(self, institution):
        return self.affiliated_institutions.filter(id=institution.id).exists()

    @classmethod
    def find_by_institutions(cls, inst, query=None):
        base_query = Q('affiliated_institutions', 'eq', inst)
        if query:
            final_query = base_query & query
        else:
            final_query = base_query
        return cls.find(final_query)

    def add_affiliated_institution(self, inst, user, save=False, log=True):
        if not user.is_affiliated_with_institution(inst):
            raise UserNotAffiliatedError('User is not affiliated with {}'.format(inst.name))
        if not self.is_affiliated_with_institution(inst):
            self.affiliated_institutions.add(inst)
        if log:
            from website.project.model import NodeLog

            self.add_log(
                action=NodeLog.AFFILIATED_INSTITUTION_ADDED,
                params={
                    'node': self._primary_key,
                    'institution': {
                        'id': inst._id,
                        'name': inst.name
                    }
                },
                auth=Auth(user)
            )

    def can_view(self, auth):
        if auth and getattr(auth.private_link, 'anonymous', False):
            return auth.private_link.nodes.filter(pk=self.pk).exists()

        if not auth and not self.is_public:
            return False

        return (self.is_public or
                (auth.user and self.has_permission(auth.user, 'read')) or
                auth.private_key in self.private_link_keys_active or
                self.is_admin_parent(auth.user))

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
            (user and self.has_permission(user, 'write')) or is_api_node
        )

    def get_aggregate_logs_query(self, auth):
        ids = [self._id] + [n._id
                            for n in self.get_descendants_recursive()
                            if n.can_view(auth)]
        query = Q('node', 'in', ids) & Q('should_hide', 'ne', True)
        return query

    def get_aggregate_logs_queryset(self, auth):
        query = self.get_aggregate_logs_query(auth)
        return NodeLog.find(query).sort('-date')

    @property
    def comment_level(self):
        if self.public_comments:
            return 'public'
        else:
            return 'private'

    @comment_level.setter
    def comment_level(self, value):
        if value == 'public':
            self.public_comments = True
        elif value == 'private':
            self.public_comments = False
        else:
            raise ValidationError(
                'comment_level must be either `public` or `private`')

    def get_absolute_url(self):
        return self.absolute_api_v2_url

    def get_permissions(self, user):
        try:
            contrib = user.contributor_set.get(node=self)
        except Contributor.DoesNotExist:
            return []
        return get_contributor_permissions(contrib)

    def get_visible(self, user):
        try:
            contributor = self.contributor_set.get(user=user)
        except Contributor.DoesNotExist:
            raise ValueError(u'User {0} not in contributors'.format(user))
        return contributor.visible

    def has_permission(self, user, permission, check_parent=True):
        """Check whether user has permission.

        :param User user: User to test
        :param str permission: Required permission
        :returns: User has required permission
        """
        if not user:
            return False
        try:
            contrib = user.contributor_set.get(node=self)
        except Contributor.DoesNotExist:
            if permission == 'read' and check_parent:
                return self.is_admin_parent(user)
            return False
        else:
            if getattr(contrib, permission, False):
                return True
        return False

    def has_permission_on_children(self, user, permission):
        """Checks if the given user has a given permission on any child nodes
            that are not registrations or deleted
        """
        if self.has_permission(user, permission):
            return True
        for node in self.nodes.filter(is_deleted=False):
            if node.has_permission_on_children(user, permission):
                return True
        return False

    def is_admin_parent(self, user):
        if self.has_permission(user, 'admin', check_parent=False):
            return True
        if self.parent_node:
            return self.parent_node.is_admin_parent(user)
        return False

    def find_readable_descendants(self, auth):
        """ Returns a generator of first descendant node(s) readable by <user>
        in each descendant branch.
        """
        new_branches = []
        for node in self.nodes.filter(is_deleted=False):
            if node.can_view(auth):
                yield node
            else:
                new_branches.append(node)

        for bnode in new_branches:
            for node in bnode.find_readable_descendants(auth):
                yield node

    @property
    def parents(self):
        if self.parent_node:
            return [self.parent_node] + self.parent_node.parents
        return []

    @property
    def admin_contributor_ids(self):
        def get_admin_contributor_ids(node):
            return Contributor.objects.select_related('user').filter(
                node=node,
                user__is_active=True,
                admin=True
            ).values_list('user__guid__guid', flat=True)
        contributor_ids = set(self.contributors.values_list('guid__guid', flat=True))
        admin_ids = set()
        for parent in self.parents:
            admins = get_admin_contributor_ids(parent)
            admin_ids.update(set(admins).difference(contributor_ids))
        return admin_ids

    @property
    def admin_contributors(self):
        return OSFUser.objects.filter(
            guid__guid__in=self.admin_contributor_ids
        ).order_by('family_name')

    def set_permissions(self, user, permissions, validate=True, save=False):
        # Ensure that user's permissions cannot be lowered if they are the only admin
        if validate and (reduce_permissions(self.get_permissions(user)) == ADMIN and
                                 reduce_permissions(permissions) != ADMIN):
            admin_contribs = Contributor.objects.filter(node=self, admin=True)
            if admin_contribs.count() <= 1:
                raise NodeStateError('Must have at least one registered admin contributor')

        contrib_obj = Contributor.objects.get(node=self, user=user)

        for permission_level in [READ, WRITE, ADMIN]:
            if permission_level in permissions:
                setattr(contrib_obj, permission_level, True)
            else:
                setattr(contrib_obj, permission_level, False)
        contrib_obj.save()
        if save:
            self.save()

    def add_permission(self, user, permission, save=False):
        contributor = user.contributor_set.get(node=self)
        if not getattr(contributor, permission, False):
            for perm in expand_permissions(permission):
                setattr(contributor, perm, True)
            contributor.save()
        else:
            if getattr(contributor, permission, False):
                raise ValueError('User already has permission {0}'.format(permission))
        if save:
            self.save()

    @property
    def registrations_all(self):
        """For v1 compat."""
        return self.registrations.all()

    @property
    def parent_id(self):
        if self.parent_node:
            return self.parent_node._id
        return None

    @property
    def license(self):
        node_license = self.node_license
        if not node_license and self.parent_node:
            return self.parent_node.license
        return node_license

    @property
    def visible_contributors(self):
        return OSFUser.objects.filter(
            contributor__node=self,
            contributor__visible=True
        ).order_by('contributor___order')

    # visible_contributor_ids was moved to this property
    @property
    def visible_contributor_ids(self):
        return self.contributor_set.filter(visible=True)\
            .order_by('_order')\
            .values_list('user__guid__guid', flat=True)

    @property
    def system_tags(self):
        """The system tags associated with this node. This currently returns a list of string
        names for the tags, for compatibility with v1. Eventually, we can just return the
        QuerySet.
        """
        return self.tags.filter(system=True).values_list('name', flat=True)

    # Override Taggable
    def add_tag_log(self, tag, auth):
        self.add_log(
            action=NodeLog.TAG_ADDED,
            params={
                'parent_node': self.parent_id,
                'node': self._id,
                'tag': tag.name
            },
            auth=auth,
            save=False
        )

    def remove_tag(self, tag, auth, save=True):
        if not tag:
            raise InvalidTagError
        elif not self.tags.filter(name=tag).exists():
            raise TagNotFoundError
        else:
            tag_obj = Tag.objects.get(name=tag)
            self.tags.remove(tag_obj)
            self.add_log(
                action=NodeLog.TAG_REMOVED,
                params={
                    'parent_node': self.parent_id,
                    'node': self._id,
                    'tag': tag,
                },
                auth=auth,
                save=False,
            )
            if save:
                self.save()
            return True

    def is_contributor(self, user):
        """Return whether ``user`` is a contributor on this node."""
        return user is not None and Contributor.objects.filter(user=user, node=self).exists()

    def set_visible(self, user, visible, log=True, auth=None, save=False):
        if not self.is_contributor(user):
            raise ValueError(u'User {0} not in contributors'.format(user))
        if visible and not Contributor.objects.filter(node=self, user=user, visible=True).exists():
            Contributor.objects.filter(node=self, user=user, visible=False).update(visible=True)
        elif not visible and Contributor.objects.filter(node=self, user=user, visible=True).exists():
            if Contributor.objects.filter(node=self, visible=True).count() == 1:
                raise ValueError('Must have at least one visible contributor')
            Contributor.objects.filter(node=self, user=user, visible=True).update(visible=False)
        else:
            return
        message = (
            NodeLog.MADE_CONTRIBUTOR_VISIBLE
            if visible
            else NodeLog.MADE_CONTRIBUTOR_INVISIBLE
        )
        if log:
            self.add_log(
                message,
                params={
                    'parent': self.parent_id,
                    'node': self._id,
                    'contributors': [user._id],
                },
                auth=auth,
                save=False,
            )
        if save:
            self.save()

    def add_contributor(self, contributor, permissions=None, visible=True,
                        send_email='default', auth=None, log=True, save=False):
        """Add a contributor to the project.

        :param User contributor: The contributor to be added
        :param list permissions: Permissions to grant to the contributor
        :param bool visible: Contributor is visible in project dashboard
        :param str send_email: Email preference for notifying added contributor
        :param Auth auth: All the auth information including user, API key
        :param bool log: Add log to self
        :param bool save: Save after adding contributor
        :returns: Whether contributor was added
        """
        MAX_RECENT_LENGTH = 15

        # If user is merged into another account, use master account
        contrib_to_add = contributor.merged_by if contributor.is_merged else contributor
        if not self.is_contributor(contrib_to_add):

            contributor_obj, created = Contributor.objects.get_or_create(user=contrib_to_add, node=self)
            contributor_obj.visible = visible

            # Add default contributor permissions
            permissions = permissions or DEFAULT_CONTRIBUTOR_PERMISSIONS
            for perm in permissions:
                setattr(contributor_obj, perm, True)
            contributor_obj.save()

            # Add contributor to recently added list for user
            if auth is not None:
                user = auth.user
                recently_added_contributor_obj, created = RecentlyAddedContributor.objects.get_or_create(
                    user=user,
                    contributor=contrib_to_add
                )
                recently_added_contributor_obj.date_added = timezone.now()
                recently_added_contributor_obj.save()
                count = user.recently_added.count()
                if count > MAX_RECENT_LENGTH:
                    difference = count - MAX_RECENT_LENGTH
                    for each in user.recentlyaddedcontributor_set.order_by('date_added')[:difference]:
                        each.delete()
            if log:
                self.add_log(
                    action=NodeLog.CONTRIB_ADDED,
                    params={
                        'project': self.parent_id,
                        'node': self._primary_key,
                        'contributors': [contrib_to_add._primary_key],
                    },
                    auth=auth,
                    save=False,
                )
            if save:
                self.save()

            if self._id and send_email != 'false':
                project_signals.contributor_added.send(self,
                                                       contributor=contributor,
                                                       auth=auth, email_template=send_email)

            return True

        # Permissions must be overridden if changed when contributor is
        # added to parent he/she is already on a child of.
        elif self.is_contributor(contrib_to_add) and permissions is not None:
            self.set_permissions(contrib_to_add, permissions)
            if save:
                self.save()

            return False
        else:
            return False

    def add_contributors(self, contributors, auth=None, log=True, save=False):
        """Add multiple contributors

        :param list contributors: A list of dictionaries of the form:
            {
                'user': <User object>,
                'permissions': <Permissions list, e.g. ['read', 'write']>,
                'visible': <Boolean indicating whether or not user is a bibliographic contributor>
            }
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
                save=False,
            )
        if save:
            self.save()

    def add_unregistered_contributor(self, fullname, email, auth, send_email='default',
                                     visible=True, permissions=None, save=False):
        """Add a non-registered contributor to the project.

        :param str fullname: The full name of the person.
        :param str email: The email address of the person.
        :param Auth auth: Auth object for the user adding the contributor.
        :returns: The added contributor
        :raises: DuplicateEmailError if user with given email is already in the database.
        """
        # Create a new user record
        contributor = OSFUser.create_unregistered(fullname=fullname, email=email)

        contributor.add_unclaimed_record(node=self, referrer=auth.user,
                                         given_name=fullname, email=email)
        try:
            contributor.save()
        except ValidationError:  # User with same email already exists
            contributor = get_user(email=email)
            # Unregistered users may have multiple unclaimed records, so
            # only raise error if user is registered.
            if contributor.is_registered or self.is_contributor(contributor):
                raise
            contributor.add_unclaimed_record(node=self, referrer=auth.user,
                                             given_name=fullname, email=email)
            contributor.save()

        self.add_contributor(
            contributor, permissions=permissions, auth=auth,
            visible=visible, send_email=send_email, log=True, save=False
        )
        self.save()
        return contributor

    def add_contributor_registered_or_not(self, auth, user_id=None,
                                          full_name=None, email=None, send_email='false',
                                          permissions=None, bibliographic=True, index=None, save=False):

        if user_id:
            contributor = OSFUser.load(user_id)
            if not contributor:
                raise ValueError('User with id {} was not found.'.format(user_id))
            if self.contributor_set.filter(user=contributor).exists():
                raise ValidationValueError('{} is already a contributor.'.format(contributor.fullname))
            self.add_contributor(contributor=contributor, auth=auth, visible=bibliographic,
                                 permissions=permissions, send_email=send_email, save=True)
        else:

            try:
                contributor = self.add_unregistered_contributor(
                    fullname=full_name, email=email, auth=auth,
                    send_email=send_email, permissions=permissions,
                    visible=bibliographic, save=True
                )
            except ValidationError:
                contributor = get_user(email=email)
                if self.contributor_set.filter(user=contributor).exists():
                    raise ValidationValueError('{} is already a contributor.'.format(contributor.fullname))
                self.add_contributor(contributor=contributor, auth=auth, visible=bibliographic,
                                     send_email=send_email, permissions=permissions, save=True)

        auth.user.email_last_sent = timezone.now()
        auth.user.save()

        if index is not None:
            self.move_contributor(user=contributor, index=index, auth=auth, save=True)

        contributor_obj = self.contributor_set.get(user=contributor)
        contributor.permission = get_contributor_permissions(contributor_obj, as_list=False)
        contributor.bibliographic = contributor_obj.visible
        contributor.node_id = self._id
        contributor_order = list(self.get_contributor_order())
        contributor.index = contributor_order.index(contributor_obj.pk)

        if save:
            contributor.save()

        return contributor

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
            for child in self.nodes.filter(is_deleted=False):
                messages.extend(
                    child.callback(
                        callback, recursive, *args, **kwargs
                    )
                )

        return messages

    def replace_contributor(self, old, new):
        try:
            contrib_obj = self.contributor_set.get(user=old)
        except Contributor.DoesNotExist:
            return False
        contrib_obj.user = new
        contrib_obj.save()

        # Remove unclaimed record for the project
        if self._id in old.unclaimed_records:
            del old.unclaimed_records[self._id]
            old.save()
        return True

    def remove_contributor(self, contributor, auth, log=True):
        """Remove a contributor from this node.

        :param contributor: User object, the contributor to be removed
        :param auth: All the auth information including user, API key.
        """
        # remove unclaimed record if necessary
        if self._primary_key in contributor.unclaimed_records:
            del contributor.unclaimed_records[self._primary_key]

        if not self.visible_contributor_ids:
            return False

        # Node must have at least one registered admin user
        admin_query = Contributor.objects.select_related('user').filter(
            user__is_active=True,
            admin=True
        ).exclude(user=contributor)
        if not admin_query.exists():
            return False

        contrib_obj = self.contributor_set.get(user=contributor)
        contrib_obj.delete()

        # After remove callback
        for addon in self.get_addons():
            message = addon.after_remove_contributor(self, contributor, auth)
            if message:
                # Because addons can return HTML strings, addons are responsible
                # for markupsafe-escaping any messages returned
                status.push_status_message(message, kind='info', trust=True)

        if log:
            self.add_log(
                action=NodeLog.CONTRIB_REMOVED,
                params={
                    'project': self.parent_id,
                    'node': self._id,
                    'contributors': [contributor._id],
                },
                auth=auth,
                save=False,
            )

        self.save()

        #send signal to remove this user from project subscriptions
        project_signals.contributor_removed.send(self, user=contributor)

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
                save=False,
            )

        if save:
            self.save()

        return all(results)

    def move_contributor(self, user, auth, index, save=False):
        if not self.has_permission(auth.user, ADMIN):
            raise PermissionsError('Only admins can modify contributor order')
        contributor_ids = list(self.get_contributor_order())
        contributor = self.contributor_set.get(user=user)
        old_index = contributor_ids.index(contributor.id)
        contributor_ids.insert(index, contributor_ids.pop(old_index))
        self.set_contributor_order(contributor_ids)
        self.add_log(
            action=NodeLog.CONTRIB_REORDERED,
            params={
                'project': self.parent_id,
                'node': self._id,
                'contributors': [
                    user._id
                ],
            },
            auth=auth,
            save=False,
        )
        if save:
            self.save()

    @classmethod
    def find_for_user(cls, user, subquery=None):
        combined_query = Q('contributors', 'eq', user)
        if subquery is not None:
            combined_query = combined_query & subquery
        return cls.find(combined_query)

    def can_comment(self, auth):
        if self.comment_level == 'public':
            return auth.logged_in and (
                self.is_public or
                (auth.user and self.has_permission(auth.user, 'read'))
            )
        return self.is_contributor(auth.user)

    def set_privacy(self, permissions, auth=None, log=True, save=True, meeting_creation=False):
        """Set the permissions for this node. Also, based on meeting_creation, queues
        an email to user about abilities of public projects.

        :param permissions: A string, either 'public' or 'private'
        :param auth: All the auth information including user, API key.
        :param bool log: Whether to add a NodeLog for the privacy change.
        :param bool meeting_creation: Whether this was created due to a meetings email.
        """
        if auth and not self.has_permission(auth.user, ADMIN):
            raise PermissionsError('Must be an admin to change privacy settings.')
        if permissions == 'public' and not self.is_public:
            if self.is_registration:
                if self.is_pending_embargo:
                    raise NodeStateError('A registration with an unapproved embargo cannot be made public.')
                elif self.is_pending_registration:
                    raise NodeStateError('An unapproved registration cannot be made public.')
                elif self.is_pending_embargo:
                    raise NodeStateError('An unapproved embargoed registration cannot be made public.')
                elif self.is_embargoed:
                    # Embargoed registrations can be made public early
                    self.request_embargo_termination(auth=auth)
                    return False
            self.is_public = True
            self.keenio_read_key = self.generate_keenio_read_key()
        elif permissions == 'private' and self.is_public:
            if self.is_registration and not self.is_pending_embargo:
                raise NodeStateError('Public registrations must be withdrawn, not made private.')
            else:
                self.is_public = False
                self.keenio_read_key = ''
        else:
            return False

        # After set permissions callback
        for addon in self.get_addons():
            message = addon.after_set_privacy(self, permissions)
            if message:
                status.push_status_message(message, kind='info', trust=False)

        if log:
            action = NodeLog.MADE_PUBLIC if permissions == 'public' else NodeLog.MADE_PRIVATE
            self.add_log(
                action=action,
                params={
                    'project': self.parent_id,
                    'node': self._primary_key,
                },
                auth=auth,
                save=False,
            )
        if save:
            self.save()
        if auth and permissions == 'public':
            project_signals.privacy_set_public.send(auth.user, node=self, meeting_creation=meeting_creation)
        return True

    def generate_keenio_read_key(self):
        return scoped_keys.encrypt(settings.KEEN['public']['master_key'], options={
            'filters': [{
                'property_name': 'node.id',
                'operator': 'eq',
                'property_value': str(self._id)
            }],
            'allowed_operations': ['read']
        })

    @property
    def private_links_active(self):
        return self.private_links.filter(is_deleted=False)

    @property
    def private_link_keys_active(self):
        return self.private_links.filter(is_deleted=False).values_list('key', flat=True)

    @property
    def private_link_keys_deleted(self):
        return self.private_links.filter(is_deleted=True).values_list('key', flat=True)

    @property
    def _root(self):
        if self.parent_node:
            return self.parent_node._root
        else:
            return self

    def find_readable_antecedent(self, auth):
        """ Returns first antecendant node readable by <user>.
        """
        next_parent = self.parent_node
        while next_parent:
            if next_parent.can_view(auth):
                return next_parent
            next_parent = next_parent.parent_node

    def copy_contributors_from(self, node):
        """Copies the contibutors from node (including permissions and visibility) into this node."""
        contribs = []
        for contrib in node.contributor_set.all():
            contrib.id = None
            contrib.node = self
            contribs.append(contrib)
        Contributor.objects.bulk_create(contribs)

    def register_node(self, schema, auth, data, parent=None):
        """Make a frozen copy of a node.

        :param schema: Schema object
        :param auth: All the auth information including user, API key.
        :param template: Template name
        :param data: Form data
        :param parent Node: parent registration of registration to be created
        """
        # TODO(lyndsysimon): "template" param is not necessary - use schema.name?
        # NOTE: Admins can register child nodes even if they don't have write access them
        if not self.can_edit(auth=auth) and not self.is_admin_parent(user=auth.user):
            raise PermissionsError(
                'User {} does not have permission '
                'to register this node'.format(auth.user._id)
            )
        if self.is_collection:
            raise NodeStateError('Folders may not be registered')

        original = self.load(self._primary_key)

        # Note: Cloning a node will clone each node wiki page version and add it to
        # `registered.wiki_pages_current` and `registered.wiki_pages_versions`.
        if original.is_deleted:
            raise NodeStateError('Cannot register deleted node.')

        registered = original.clone()
        registered.recast('osf_models.registration')
        # Need to save here in order to set many-to-many fields
        registered.save()

        registered.registered_date = timezone.now()
        registered.registered_user = auth.user
        registered.registered_schema.add(schema)
        registered.registered_from = original
        if not registered.registered_meta:
            registered.registered_meta = {}
        registered.registered_meta[schema._id] = data

        registered.copy_contributors_from(self)
        registered.forked_from = self.forked_from
        registered.creator = self.creator
        registered.tags.add(*self.tags.all())
        registered.affiliated_institutions.add(*self.affiliated_institutions.all())
        registered.alternative_citations.add(*self.alternative_citations.values_list('pk', flat=True))
        registered.node_license = original.license.copy() if original.license else None
        registered.wiki_private_uuids = {}

        # registered.save()

        # Clone each log from the original node for this registration.
        logs = original.logs.all()
        for log in logs:
            log.clone_node_log(registered._id)

        registered.is_public = False
        for node in registered.get_descendants_recursive():
            node.is_public = False
            node.save()

        if parent:
            registered.parent_node = parent

        # After register callback
        for addon in original.get_addons():
            _, message = addon.after_register(original, registered, auth.user)
            if message:
                status.push_status_message(message, kind='info', trust=False)

        child_pks = []
        for node_contained in original.nodes.filter(is_deleted=False):
            registered_child = node_contained.register_node(  # noqa
                schema=schema,
                auth=auth,
                data=data,
                parent=registered,
            )
            child_pks.append(registered_child.pk)
        # Preserve ordering of children
        registered.set_abstractnode_order(child_pks)

        # Copy linked nodes
        registered.linked_nodes.add(*original.linked_nodes.values_list('pk', flat=True))

        registered.save()

        if settings.ENABLE_ARCHIVER:
            registered.refresh_from_db()
            project_signals.after_create_registration.send(self, dst=registered, user=auth.user)

        return registered

    def _initiate_approval(self, user, notify_initiator_on_complete=False):
        end_date = timezone.now() + settings.REGISTRATION_APPROVAL_TIME
        self.registration_approval = RegistrationApproval.objects.create(
            initiated_by=user,
            end_date=end_date,
            notify_initiator_on_complete=notify_initiator_on_complete
        )
        self.save()  # Set foreign field reference Node.registration_approval
        admins = self.get_admin_contributors_recursive(unique_users=True)
        for (admin, node) in admins:
            self.registration_approval.add_authorizer(admin, node=node)
        self.registration_approval.save()  # Save approval's approval_state
        return self.registration_approval

    def require_approval(self, user, notify_initiator_on_complete=False):
        if not self.is_registration:
            raise NodeStateError('Only registrations can require registration approval')
        if not self.has_permission(user, 'admin'):
            raise PermissionsError('Only admins can initiate a registration approval')

        approval = self._initiate_approval(user, notify_initiator_on_complete)

        self.registered_from.add_log(
            action=NodeLog.REGISTRATION_APPROVAL_INITIATED,
            params={
                'node': self.registered_from._id,
                'registration': self._id,
                'registration_approval_id': approval._id,
            },
            auth=Auth(user),
            save=True,
        )

    # TODO optimize me
    def get_descendants_recursive(self, include=lambda n: True):
        for node in self.nodes.all():
            if include(node):
                yield node
            if node.primary:
                for descendant in node.get_descendants_recursive(include):
                    if include(descendant):
                        yield descendant

    @property
    def nodes_primary(self):
        """For v1 compat."""
        return self.nodes.all()

    @property
    def has_pointers_recursive(self):
        """Recursively checks whether the current node or any of its nodes
        contains a pointer.
        """
        if self.linked_nodes.exists():
            return True
        for node in self.nodes_primary:
            if node.has_pointers_recursive:
                return True
        return False

    def add_citation(self, auth, save=False, log=True, citation=None, **kwargs):
        if not citation:
            citation = AlternativeCitation.objects.create(**kwargs)
        self.alternative_citations.add(citation)
        citation_dict = {'name': citation.name, 'text': citation.text}
        if log:
            self.add_log(
                action=NodeLog.CITATION_ADDED,
                params={
                    'node': self._id,
                    'citation': citation_dict
                },
                auth=auth,
                save=False
            )
            if save:
                self.save()
        return citation

    def edit_citation(self, auth, instance, save=False, log=True, **kwargs):
        citation = {'name': instance.name, 'text': instance.text}
        new_name = kwargs.get('name', instance.name)
        new_text = kwargs.get('text', instance.text)
        if new_name != instance.name:
            instance.name = new_name
            citation['new_name'] = new_name
        if new_text != instance.text:
            instance.text = new_text
            citation['new_text'] = new_text
        instance.save()
        if log:
            self.add_log(
                action=NodeLog.CITATION_EDITED,
                params={
                    'node': self._primary_key,
                    'citation': citation
                },
                auth=auth,
                save=False
            )
        if save:
            self.save()
        return instance

    def remove_citation(self, auth, instance, save=False, log=True):
        citation = {'name': instance.name, 'text': instance.text}
        self.alternative_citations.remove(instance)
        if log:
            self.add_log(
                action=NodeLog.CITATION_REMOVED,
                params={
                    'node': self._primary_key,
                    'citation': citation
                },
                auth=auth,
                save=False
            )
        if save:
            self.save()

    # TODO: Optimize me (e.g. use bulk create)
    def fork_node(self, auth, title=None):
        """Recursively fork a node.

        :param Auth auth: Consolidated authorization
        :param str title: Optional text to prepend to forked title
        :return: Forked node
        """
        Registration = apps.get_model('osf_models.Registration')
        PREFIX = 'Fork of '
        user = auth.user

        # Non-contributors can't fork private nodes
        if not (self.is_public or self.has_permission(user, 'read')):
            raise PermissionsError('{0!r} does not have permission to fork node {1!r}'.format(user, self._id))

        when = timezone.now()

        original = self.load(self._id)

        if original.is_deleted:
            raise NodeStateError('Cannot fork deleted node.')

        # Note: Cloning a node will clone each node wiki page version and add it to
        # `registered.wiki_pages_current` and `registered.wiki_pages_versions`.
        forked = original.clone()
        if isinstance(forked, Registration):
            forked.recast('osf_models.node')

        forked.is_fork = True
        forked.forked_date = when
        forked.forked_from = original
        forked.creator = user
        forked.node_license = original.license.copy() if original.license else None
        forked.wiki_private_uuids = {}

        # Forks default to private status
        forked.is_public = False

        # Need to save here in order to access m2m fields
        forked.save()

        forked.tags.add(*self.tags.all())

        # Recursively fork child nodes
        for node_contained in original.nodes.filter(is_deleted=False).all():
            forked_node = None
            try:  # Catch the potential PermissionsError above
                forked_node = node_contained.fork_node(auth=auth, title='')
            except PermissionsError:
                pass  # If this exception is thrown omit the node from the result set
            if forked_node is not None:
                forked.nodes.add(forked_node)

        # Copy node links
        forked.linked_nodes.add(*self.linked_nodes.values_list('pk', flat=True))

        if title is None:
            forked.title = PREFIX + original.title
        elif title == '':
            forked.title = original.title
        else:
            forked.title = title

        # TODO: Optimize me
        for citation in self.alternative_citations.all():
            forked.add_citation(
                auth=auth,
                citation=citation.clone(),
                log=False,
                save=False
            )

        forked.add_contributor(
            contributor=user,
            permissions=CREATOR_PERMISSIONS,
            log=False,
            save=False
        )

        forked.save()

        # Need to call this after save for the notifications to be created with the _primary_key
        project_signals.contributor_added.send(forked, contributor=user, auth=auth)

        forked.add_log(
            action=NodeLog.NODE_FORKED,
            params={
                'parent_node': original.parent_id,
                'node': original._primary_key,
                'registration': forked._primary_key,  # TODO: Remove this in favor of 'fork'
                'fork': forked._primary_key,
            },
            auth=auth,
            log_date=when,
            save=False,
        )

        # Clone each log from the original node for this fork.
        for log in original.logs.all():
            log.clone_node_log(forked._id)

        forked.refresh_from_db()

        # After fork callback
        for addon in original.get_addons():
            _, message = addon.after_fork(original, forked, user)
            if message:
                status.push_status_message(message, kind='info', trust=True)

        return forked

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

        # Clear quasi-foreign fields
        new.wiki_pages_current.clear()
        new.wiki_pages_versions.clear()
        new.wiki_private_uuids.clear()
        new.file_guid_to_share_uuids.clear()

        # set attributes which may be overridden by `changes`
        new.is_public = False
        new.description = ''

        # apply `changes`
        for attr, val in attributes.iteritems():
            setattr(new, attr, val)

        # set attributes which may NOT be overridden by `changes`
        new.creator = auth.user
        new.template_node = self
        # Need to save in order to access contributors m2m table
        new.save(suppress_log=True)
        new.add_contributor(contributor=auth.user, permissions=CREATOR_PERMISSIONS, log=False, save=False)
        new.is_fork = False
        new.node_license = self.license.copy() if self.license else None

        # If that title hasn't been changed, apply the default prefix (once)
        if (
            new.title == self.title and top_level and
            language.TEMPLATED_FROM_PREFIX not in new.title
        ):
            new.title = ''.join((language.TEMPLATED_FROM_PREFIX, new.title, ))

        # Slight hack - date_created is a read-only field.
        new.date_created = timezone.now()

        new.save(suppress_log=True)

        # Log the creation
        new.add_log(
            NodeLog.CREATED_FROM,
            params={
                'node': new._primary_key,
                'template_node': {
                    'id': self._primary_key,
                    'url': self.url,
                    'title': self.title,
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
            for x in self.nodes.filter(is_deleted=False)
            if x.can_view(auth)
        ]
        new.save()
        return new

    def next_descendants(self, auth, condition=lambda auth, node: True):
        """
        Recursively find the first set of descedants under a given node that meet a given condition

        returns a list of [(node, [children]), ...]
        """
        ret = []
        for node in self.nodes.order_by('date_created').all():
            if condition(auth, node):
                # base case
                ret.append((node, []))
            else:
                ret.append((node, node.next_descendants(auth, condition)))
        ret = [item for item in ret if item[1] or condition(auth, item[0])]  # prune empty branches
        return ret

    def node_and_primary_descendants(self):
        """Return an iterator for a node and all of its primary (non-pointer) descendants.

        :param node Node: target Node
        """
        return itertools.chain([self], self.get_descendants_recursive(lambda n: n.primary))

    def active_contributors(self, include=lambda n: True):
        for contrib in self.contributors.filter(is_active=True):
            if include(contrib):
                yield contrib

    def get_active_contributors_recursive(self, unique_users=False, *args, **kwargs):
        """Yield (admin, node) tuples for this node and
        descendant nodes. Excludes contributors on node links and inactive users.

        :param bool unique_users: If True, a given admin will only be yielded once
            during iteration.
        """
        visited_user_ids = []
        for node in self.node_and_primary_descendants(*args, **kwargs):
            for contrib in node.active_contributors(*args, **kwargs):
                if unique_users:
                    if contrib._id not in visited_user_ids:
                        visited_user_ids.append(contrib._id)
                        yield (contrib, node)
                else:
                    yield (contrib, node)

    def _get_admin_contributors_query(self, users):
        return Contributor.objects.select_related('user').filter(
            user__in=users,
            user__is_active=True,
            admin=True
        )

    def get_admin_contributors(self, users):
        """Return a set of all admin contributors for this node. Excludes contributors on node links and
        inactive users.
        """
        return (each.user for each in self._get_admin_contributors_query(users))

    def get_admin_contributors_recursive(self, unique_users=False, *args, **kwargs):
        """Yield (admin, node) tuples for this node and
        descendant nodes. Excludes contributors on node links and inactive users.

        :param bool unique_users: If True, a given admin will only be yielded once
            during iteration.
        """
        visited_user_ids = []
        for node in self.node_and_primary_descendants(*args, **kwargs):
            for contrib in node.contributors.all():
                if node.has_permission(contrib, ADMIN) and contrib.is_active:
                    if unique_users:
                        if contrib._id not in visited_user_ids:
                            visited_user_ids.append(contrib._id)
                            yield (contrib, node)
                    else:
                        yield (contrib, node)

    # TODO: Optimize me
    def manage_contributors(self, user_dicts, auth, save=False):
        """Reorder and remove contributors.

        :param list user_dicts: Ordered list of contributors represented as
            dictionaries of the form:
            {'id': <id>, 'permission': <One of 'read', 'write', 'admin'>, 'visible': bool}
        :param Auth auth: Consolidated authentication information
        :param bool save: Save changes
        :raises: ValueError if any users in `users` not in contributors or if
            no admin contributors remaining
        """
        with transaction.atomic():
            users = []
            user_ids = []
            permissions_changed = {}
            visibility_removed = []
            to_retain = []
            to_remove = []
            for user_dict in user_dicts:
                user = OSFUser.load(user_dict['id'])
                if user is None:
                    raise ValueError('User not found')
                if not self.contributors.filter(id=user.id).exists():
                    raise ValueError(
                        'User {0} not in contributors'.format(user.fullname)
                    )
                permissions = expand_permissions(user_dict['permission'])
                if set(permissions) != set(self.get_permissions(user)):
                    # Validate later
                    self.set_permissions(user, permissions, validate=False, save=False)
                    permissions_changed[user._id] = permissions
                # visible must be added before removed to ensure they are validated properly
                if user_dict['visible']:
                    self.set_visible(user,
                                     visible=True,
                                     auth=auth)
                else:
                    visibility_removed.append(user)
                users.append(user)
                user_ids.append(user_dict['id'])

            for user in visibility_removed:
                self.set_visible(user,
                                 visible=False,
                                 auth=auth)

            for user in self.contributors.all():
                if user._id in user_ids:
                    to_retain.append(user)
                else:
                    to_remove.append(user)

            if users is None or not self._get_admin_contributors_query(users).exists():
                raise NodeStateError(
                    'Must have at least one registered admin contributor'
                )

            if to_retain != users:
                # TODO: Can we prevent n queries?
                sorted_contribs = [self.contributor_set.get(user=user).pk for user in users]
                self.set_contributor_order(sorted_contribs)
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
                    save=False,
                )

            if to_remove:
                self.remove_contributors(to_remove, auth=auth, save=False)

            if permissions_changed:
                self.add_log(
                    action=NodeLog.PERMISSIONS_UPDATED,
                    params={
                        'project': self.parent_id,
                        'node': self._id,
                        'contributors': permissions_changed,
                    },
                    auth=auth,
                    save=False,
                )
            if save:
                self.save()

        with transaction.atomic():
            if to_remove or permissions_changed and ['read'] in permissions_changed.values():
                project_signals.write_permissions_revoked.send(self)

    # TODO: optimize me
    def update_contributor(self, user, permission, visible, auth, save=False):
        """ TODO: this method should be updated as a replacement for the main loop of
        Node#manage_contributors. Right now there are redundancies, but to avoid major
        feature creep this will not be included as this time.

        Also checks to make sure unique admin is not removing own admin privilege.
        """
        if not self.has_permission(auth.user, ADMIN):
            raise PermissionsError('Only admins can modify contributor permissions')

        if permission:
            permissions = expand_permissions(permission)
            admins = self.contributor_set.filter(admin=True)
            if not admins.count() > 1:
                # has only one admin
                admin = admins.first()
                if admin.user == user and ADMIN not in permissions:
                    raise NodeStateError('{} is the only admin.'.format(user.fullname))
            if not self.contributor_set.filter(user=user).exists():
                raise ValueError(
                    'User {0} not in contributors'.format(user.fullname)
                )
            if set(permissions) != set(self.get_permissions(user)):
                self.set_permissions(user, permissions, save=save)
                permissions_changed = {
                    user._id: permissions
                }
                self.add_log(
                    action=NodeLog.PERMISSIONS_UPDATED,
                    params={
                        'project': self.parent_id,
                        'node': self._id,
                        'contributors': permissions_changed,
                    },
                    auth=auth,
                    save=save
                )
                with transaction.atomic():
                    if ['read'] in permissions_changed.values():
                        project_signals.write_permissions_revoked.send(self)
        if visible is not None:
            self.set_visible(user, visible, auth=auth)

    def save(self, *args, **kwargs):
        if self.pk:
            self.root = self._root
        if 'suppress_log' in kwargs.keys():
            self._suppress_log = kwargs['suppress_log']
            del kwargs['suppress_log']
        else:
            self._suppress_log = False
        return super(AbstractNode, self).save(*args, **kwargs)

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        django_obj = super(AbstractNode, cls).migrate_from_modm(modm_obj)
        # force order, fix in subsequent pass
        django_obj._order = 0
        return django_obj

    def resolve(self):
        """For compat with v1 Pointers."""
        return self

    def set_title(self, title, auth, save=False):
        """Set the title of this Node and log it.

        :param str title: The new title.
        :param auth: All the auth information including user, API key.
        """
        #Called so validation does not have to wait until save.
        validate_title(title)

        original_title = self.title
        new_title = sanitize.strip_html(title)
        # Title hasn't changed after sanitzation, bail out
        if original_title == new_title:
            return False
        self.title = new_title
        self.add_log(
            action=NodeLog.EDITED_TITLE,
            params={
                'parent_node': self.parent_id,
                'node': self._primary_key,
                'title_new': self.title,
                'title_original': original_title,
            },
            auth=auth,
            save=False,
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
        new_description = sanitize.strip_html(description)
        if original == new_description:
            return False
        self.description = new_description
        self.add_log(
            action=NodeLog.EDITED_DESCRIPTION,
            params={
                'parent_node': self.parent_id,
                'node': self._primary_key,
                'description_new': self.description,
                'description_original': original
            },
            auth=auth,
            save=False,
        )
        if save:
            self.save()
        return None

    def update(self, fields, auth=None, save=True):
        """Update the node with the given fields.

        :param dict fields: Dictionary of field_name:value pairs.
        :param Auth auth: Auth object for the user making the update.
        :param bool save: Whether to save after updating the object.
        """
        if not fields:  # Bail out early if there are no fields to update
            return False
        values = {}
        for key, value in fields.iteritems():
            if key not in self.WRITABLE_WHITELIST:
                continue
            if self.is_registration and key != 'is_public':
                raise NodeUpdateError(reason='Registered content cannot be updated', key=key)
            # Title and description have special methods for logging purposes
            if key == 'title':
                if not self.is_bookmark_collection:
                    self.set_title(title=value, auth=auth, save=False)
                else:
                    raise NodeUpdateError(reason='Bookmark collections cannot be renamed.', key=key)
            elif key == 'description':
                self.set_description(description=value, auth=auth, save=False)
            elif key == 'is_public':
                self.set_privacy(
                    Node.PUBLIC if value else Node.PRIVATE,
                    auth=auth,
                    log=True,
                    save=False
                )
            elif key == 'node_license':
                self.set_node_license(
                    value.get('id'),
                    value.get('year'),
                    value.get('copyright_holders'),
                    auth,
                    save=save
                )
            else:
                with warnings.catch_warnings():
                    try:
                        # This is in place because historically projects and components
                        # live on different ElasticSearch indexes, and at the time of Node.save
                        # there is no reliable way to check what the old Node.category
                        # value was. When the cateogory changes it is possible to have duplicate/dead
                        # search entries, so always delete the ES doc on categoryt change
                        # TODO: consolidate Node indexes into a single index, refactor search
                        if key == 'category':
                            self.delete_search_entry()
                        ###############
                        old_value = getattr(self, key)
                        if old_value != value:
                            values[key] = {
                                'old': old_value,
                                'new': value,
                            }
                            setattr(self, key, value)
                    except AttributeError:
                        raise NodeUpdateError(reason="Invalid value for attribute '{0}'".format(key), key=key)
                    except warnings.Warning:
                        raise NodeUpdateError(
                            reason="Attribute '{0}' doesn't exist on the Node class".format(key), key=key
                        )
        if save:
            updated = self.get_dirty_fields()
            self.save()
        else:
            updated = []
        for key in values:
            values[key]['new'] = getattr(self, key)
        if values:
            self.add_log(
                NodeLog.UPDATED_FIELDS,
                params={
                    'node': self._id,
                    'updated_fields': {
                        key: {
                            'old': values[key]['old'],
                            'new': values[key]['new']
                        }
                        for key in values
                    }
                },
                auth=auth)
        return updated

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
            raise PermissionsError(
                '{0!r} does not have permission to modify this {1}'.format(auth.user, self.category or 'node')
            )

        if self.nodes.filter(is_deleted=False).exists():
            raise NodeStateError('Any child components must be deleted prior to deleting this project.')

        # After delete callback
        for addon in self.get_addons():
            message = addon.after_delete(self, auth.user)
            if message:
                status.push_status_message(message, kind='info', trust=False)

        log_date = date or timezone.now()

        # Add log to parent
        if self.parent_node:
            self.parent_node.add_log(
                NodeLog.NODE_REMOVED,
                params={
                    'project': self._primary_key,
                },
                auth=auth,
                log_date=log_date,
                save=True,
            )
        else:
            self.add_log(
                NodeLog.PROJECT_DELETED,
                params={
                    'project': self._primary_key,
                },
                auth=auth,
                log_date=log_date,
                save=True,
            )

        self.is_deleted = True
        self.deleted_date = date
        self.save()

        project_signals.node_deleted.send(self)

        return True

    def admin_public_wiki(self, user):
        return (
            self.has_addon('wiki') and
            self.has_permission(user, 'admin') and
            self.is_public
        )

    def include_wiki_settings(self, user):
        """Check if node meets requirements to make publicly editable."""
        return (
            self.admin_public_wiki(user) or
            any(
                each.admin_public_wiki(user)
                for each in self.get_descendants_recursive()
            )
        )

    def get_wiki_page(self, name=None, version=None, id=None):
        NodeWikiPage = apps.get_model('osf_models.NodeWikiPage')
        if name:
            name = (name or '').strip()
            key = to_mongo_key(name)
            try:
                if version and (isinstance(version, int) or version.isdigit()):
                    id = self.wiki_pages_versions[key][int(version) - 1]
                elif version == 'previous':
                    id = self.wiki_pages_versions[key][-2]
                elif version == 'current' or version is None:
                    id = self.wiki_pages_current[key]
                else:
                    return None
            except (KeyError, IndexError):
                return None
        return NodeWikiPage.load(id)

    def update_node_wiki(self, name, content, auth):
        """Update the node's wiki page with new content.

        :param page: A string, the page's name, e.g. ``"home"``.
        :param content: A string, the posted content.
        :param auth: All the auth information including user, API key.
        """
        NodeWikiPage = apps.get_model('osf_models.NodeWikiPage')
        Comment = apps.get_model('osf_models.Comment')

        name = (name or '').strip()
        key = to_mongo_key(name)
        has_comments = False
        current = None

        if key not in self.wiki_pages_current:
            if key in self.wiki_pages_versions:
                version = len(self.wiki_pages_versions[key]) + 1
            else:
                version = 1
        else:
            current = NodeWikiPage.load(self.wiki_pages_current[key])
            version = current.version + 1
            current.save()
            if Comment.find(Q('root_target', 'eq', current._id)).count() > 0:
                has_comments = True

        new_page = NodeWikiPage(
            page_name=name,
            version=version,
            user=auth.user,
            node=self,
            content=content
        )
        new_page.save()

        if has_comments:
            Comment.update(Q('root_target', 'eq', current._id), data={'root_target': Guid.load(new_page._id)})
            Comment.update(Q('target', 'eq', current._id), data={'target': Guid.load(new_page._id)})

        if current:
            for contrib in self.contributors:
                if contrib.comments_viewed_timestamp.get(current._id, None):
                    timestamp = contrib.comments_viewed_timestamp[current._id]
                    contrib.comments_viewed_timestamp[new_page._id] = timestamp
                    contrib.save()
                    del contrib.comments_viewed_timestamp[current._id]

        # check if the wiki page already exists in versions (existed once and is now deleted)
        if key not in self.wiki_pages_versions:
            self.wiki_pages_versions[key] = []
        self.wiki_pages_versions[key].append(new_page._primary_key)
        self.wiki_pages_current[key] = new_page._primary_key

        self.add_log(
            action=NodeLog.WIKI_UPDATED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'page': new_page.page_name,
                'page_id': new_page._primary_key,
                'version': new_page.version,
            },
            auth=auth,
            log_date=new_page.date,
            save=False,
        )
        self.save()

    def delete_node_wiki(self, name, auth):
        name = (name or '').strip()
        key = to_mongo_key(name)
        page = self.get_wiki_page(key)

        del self.wiki_pages_current[key]
        if key != 'home':
            del self.wiki_pages_versions[key]

        self.add_log(
            action=NodeLog.WIKI_DELETED,
            params={
                'project': self.parent_id,
                'node': self._primary_key,
                'page': page.page_name,
                'page_id': page._primary_key,
            },
            auth=auth,
            save=False,
        )
        self.save()

    ##### Preprint methods #####
    def add_preprint_provider(self, preprint_provider, user, save=False):
        if not self.has_permission(user, ADMIN):
            raise PermissionsError('Only admins can update a preprint provider.')
        if not preprint_provider:
            raise ValueError('Must specify a provider to set as the preprint_provider')
        self.preprint_providers.add(preprint_provider)
        if save:
            self.save()

    def remove_preprint_provider(self, preprint_provider, user, save=False):
        if not self.has_permission(user, ADMIN):
            raise PermissionsError('Only admins can remove a preprint provider.')
        if not preprint_provider:
            raise ValueError('Must specify a provider to remove from this preprint.')
        if self.preprint_providers.filter(id=preprint_provider.id).exists():
            self.preprint_providers.remove(preprint_provider)
            if save:
                self.save()
            return True
        return False

    def set_preprint_subjects(self, preprint_subjects, auth, save=False):
        if not self.has_permission(auth.user, ADMIN):
            raise PermissionsError('Only admins can change a preprint\'s subjects.')

        self.preprint_subjects.clear()
        subject_pks = Subject.objects.filter(
            guid__object_id__in=preprint_subjects).values_list('pk', flat=True)
        if subject_pks.count() < preprint_subjects:
            raise ValidationValueError('Invalid subject ID passed')
        self.preprint_subjects.add(*subject_pks)
        if save:
            self.save()

    def set_preprint_file(self, preprint_file, auth, save=False):
        if not self.has_permission(auth.user, ADMIN):
            raise PermissionsError('Only admins can change a preprint\'s primary file.')

        # TODO: Uncomment when StoredFileNode is implemented
        # if not isinstance(preprint_file, StoredFileNode):
        #     preprint_file = preprint_file.stored_object
        #
        # if preprint_file.node != self or preprint_file.provider != 'osfstorage':
        #     raise ValueError('This file is not a valid primary file for this preprint.')
        #
        # # there is no preprint file yet! This is the first time!
        # if not self.preprint_file:
        #     self.preprint_file = preprint_file
        #     self.preprint_created = datetime.datetime.utcnow()
        #     self.add_log(action=NodeLog.PREPRINT_INITIATED, params={}, auth=auth, save=False)
        # elif preprint_file != self.preprint_file:
        #     # if there was one, check if it's a new file
        #     self.preprint_file = preprint_file
        #     self.add_log(
        #         action=NodeLog.PREPRINT_FILE_UPDATED,
        #         params={},
        #         auth=auth,
        #         save=False,
        #     )
        # if not self.is_public:
        #     self.set_privacy(
        #         Node.PUBLIC,
        #         auth=None,
        #         log=True
        #     )
        # if save:
        #     self.save()


class Node(AbstractNode):
    """
    Concrete Node class: Instance of AbstractNode(TypedModel). All things that inherit
    from AbstractNode will appear in the same table and will be differentiated by the `type` column.

    FYI: Behaviors common between Registration and Node should be on the parent class.
    """

    # TODO DELETE ME POST MIGRATION
    modm_model_path = 'website.project.model.Node'
    modm_query = functools.reduce(operator.and_, [
        MQ('is_registration', 'eq', False),
        MQ('is_collection', 'eq', False),
    ])

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        """
        Given a modm object, make a django object with the same local fields.

        This is a base method that may work for simple objects.
        It should be customized in the child class if it
        doesn't work.
        :param modm_obj:
        :return:
        """
        kwargs = {cls.primary_identifier_name: modm_obj._id}
        guid, created = Guid.objects.get_or_create(**kwargs)
        if created:
            logger.debug('Created a new Guid for {} ({})'.format(modm_obj.__class__.__name__, modm_obj._id))

        django_obj = cls()
        django_obj.guid = guid

        bad_names = ['institution_logo_name']
        local_django_fields = set(
            [x.name for x in django_obj._meta.get_fields() if not x.is_relation and x.name not in bad_names])

        intersecting_fields = set(modm_obj.to_storage().keys()).intersection(
            set(local_django_fields))

        for field in intersecting_fields:
            modm_value = getattr(modm_obj, field)
            if modm_value is None:
                continue
            if isinstance(modm_value, datetime):
                modm_value = pytz.utc.localize(modm_value)
            setattr(django_obj, field, modm_value)
        django_obj._order = 0
        return django_obj

    # /TODO DELETE ME POST MIGRATION

    @property
    def is_bookmark_collection(self):
        """For v1 compat"""
        return False


class Collection(AbstractNode):
    # TODO DELETE ME POST MIGRATION
    modm_model_path = 'website.project.model.Node'
    modm_query = functools.reduce(operator.and_, [
        MQ('is_registration', 'eq', False),
        MQ('is_collection', 'eq', True),
    ])
    # /TODO DELETE ME POST MIGRATION
    is_bookmark_collection = models.NullBooleanField(default=False, db_index=True)

    @property
    def is_collection(self):
        """For v1 compat."""
        return True

    @property
    def is_registration(self):
        """For v1 compat."""
        return False

    def remove_node(self, auth, date=None):
        if self.is_bookmark_collection:
            raise NodeStateError('Bookmark collections may not be deleted.')
        # Remove all the collections that this is pointing at.
        for pointed in self.linked_nodes.all():
            if pointed.is_collection:
                pointed.remove_node(auth=auth)
        return super(Collection, self).remove_node(auth=auth, date=date)

    def save(self, *args, **kwargs):
        # Bookmark collections are always named 'Bookmarks'
        if self.is_bookmark_collection and self.title != 'Bookmarks':
            self.title = 'Bookmarks'
        # On creation, ensure there isn't an existing Bookmark collection for the given user
        if not self.pk:
            # TODO: Use a partial index to enforce this constraint in the db
            if Collection.objects.filter(is_bookmark_collection=True, creator=self.creator).exists():
                raise NodeStateError('Only one bookmark collection allowed per user.')
        return super(Collection, self).save(*args, **kwargs)


##### Signal listeners #####

@receiver(post_save, sender=Collection)
@receiver(post_save, sender=Node)
def add_creator_as_contributor(sender, instance, created, **kwargs):
    if created:
        Contributor.objects.get_or_create(
            user=instance.creator,
            node=instance,
            visible=True,
            read=True,
            write=True,
            admin=True
        )

@receiver(post_save, sender=Collection)
@receiver(post_save, sender=Node)
def add_project_created_log(sender, instance, created, **kwargs):
    if created and not instance.is_fork and not instance._suppress_log:
        # Define log fields for non-component project
        log_action = NodeLog.PROJECT_CREATED
        log_params = {
            'node': instance._id,
        }
        if getattr(instance, 'parent_node', None):
            log_params.update({'parent_node': instance.parent_node._id})

        # Add log with appropriate fields
        instance.add_log(
            log_action,
            params=log_params,
            auth=Auth(user=instance.creator),
            log_date=instance.date_created,
            save=True,
        )


@receiver(post_save, sender=Collection)
@receiver(post_save, sender=Node)
def send_osf_signal(sender, instance, created, **kwargs):
    if created and not instance._suppress_log:
        project_signals.project_created.send(instance)


# TODO: Add addons

@receiver(pre_save, sender=Collection)
@receiver(pre_save, sender=Node)
def set_parent(sender, instance, *args, **kwargs):
    if getattr(instance, '_parent', None):
        instance.parent_node = instance._parent
