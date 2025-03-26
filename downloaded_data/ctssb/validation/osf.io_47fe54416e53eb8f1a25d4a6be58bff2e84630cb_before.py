import sys

from rest_framework import serializers as ser

from api.base.serializers import (
    JSONAPISerializer,
    IDField,
    TypeField,
    Link,
    LinksField,
    RelationshipField,
    DateByVersion,
)
from api.base.utils import absolute_reverse

from framework.auth.core import Auth


class WikiSerializer(JSONAPISerializer):

    filterable_fields = frozenset([
        'name',
        'date_modified'
    ])

    id = IDField(source='_id', read_only=True)
    type = TypeField()
    name = ser.CharField(source='page_name')
    kind = ser.SerializerMethodField()
    size = ser.SerializerMethodField()
    path = ser.SerializerMethodField()
    materialized_path = ser.SerializerMethodField(method_name='get_path')
    date_modified = DateByVersion(source='date')
    content_type = ser.SerializerMethodField()
    current_user_can_comment = ser.SerializerMethodField(help_text='Whether the current user is allowed to post comments')
    extra = ser.SerializerMethodField(help_text='Additional metadata about this wiki')

    user = RelationshipField(
        related_view='users:user-detail',
        related_view_kwargs={'user_id': '<user._id>'}
    )

    # LinksField.to_representation adds link to "self"
    links = LinksField({
        'info': Link('wikis:wiki-detail', kwargs={'wiki_id': '<_id>'}),
        'download': 'get_wiki_content'
    })

    class Meta:
        type_ = 'wikis'

    def get_absolute_url(self, obj):
        return obj.get_absolute_url()

    def get_path(self, obj):
        return '/{}'.format(obj)

    def get_kind(self, obj):
        return 'file'

    def get_size(self, obj):
        return sys.getsizeof(obj.content)

    def get_current_user_can_comment(self, obj):
        user = self.context['request'].user
        auth = Auth(user if not user.is_anonymous() else None)
        return obj.node.can_comment(auth)

    def get_content_type(self, obj):
        return 'text/markdown'

    def get_extra(self, obj):
        return {
            'version': obj.version
        }

    def get_wiki_content(self, obj):
        return absolute_reverse('wikis:wiki-content', kwargs={
            'wiki_id': obj._id,
            'version': self.context['request'].parser_context['kwargs']['version']
        })


class NodeWikiSerializer(WikiSerializer):

    node = RelationshipField(
        related_view='nodes:node-detail',
        related_view_kwargs={'node_id': '<node._id>'}
    )

    comments = RelationshipField(
        related_view='nodes:node-comments',
        related_view_kwargs={'node_id': '<node._id>'},
        related_meta={'unread': 'get_unread_comments_count'},
        filter={'target': '<_id>'}
    )


class RegistrationWikiSerializer(WikiSerializer):

    node = RelationshipField(
        related_view='registrations:registration-detail',
        related_view_kwargs={'node_id': '<node._id>'}
    )

    comments = RelationshipField(
        related_view='registrations:registration-comments',
        related_view_kwargs={'node_id': '<node._id>'},
        related_meta={'unread': 'get_unread_comments_count'},
        filter={'target': '<_id>'}
    )


class NodeWikiDetailSerializer(NodeWikiSerializer):
    """
    Overrides NodeWikiSerializer to make id required.
    """
    id = IDField(source='_id', required=True)


class RegistrationWikiDetailSerializer(RegistrationWikiSerializer):
    """
    Overrides NodeWikiSerializer to make id required.
    """
    id = IDField(source='_id', required=True)
