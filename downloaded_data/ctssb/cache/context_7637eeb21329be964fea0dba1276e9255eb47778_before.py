# -*- coding: utf-8 -*-
# Stdlib imports
import datetime

# Core Django imports
from django.utils.encoding import smart_str, smart_unicode

# Third-party app imports
from rest_framework import serializers
from rest_framework_bulk import (
    BulkListSerializer,
    BulkSerializerMixin,
    ListBulkCreateUpdateDestroyAPIView,
)

# Imports from app
from .utils import url_validate
from .models import Article, Publisher, Author, PublisherFeed
from context.apps.entities.models import Entity


class ArticlerSerializer(BulkSerializerMixin, serializers.HyperlinkedModelSerializer):

    def to_representation(self, obj):
        return {
            'id': obj.pk,
            'name': obj.name,
            'url': obj.url,
            'publisher': obj.publisher.name,
            'authors': obj.authors.values(),
            'created_at': obj.created_at,
            'header_image': obj.header_image,
            'summary': obj.basic_summary,
        }

    # Defining behavior of when a new Article is added
    def create(self, data):
        # Get Publisher and validate URL
        publisher = None
        if 'url' in data:
            data['url'], publisher = url_validate(data['url'])

        try:
            django_article = Article.objects.get(url=data['url'])
        except Article.DoesNotExist:
            django_article = None

        if not django_article:
            if publisher:
                publisher = Publisher.objects.filter(url=publisher)
                data['publisher'] = publisher[
                    0] or Publisher.objects.filter(name="Other")

            data['basic_summary'] = smart_unicode(data['basic_summary'])

            author_list = None
            entity_list = None
            if 'authors' in data:
                author_list = data['authors']
                del data['authors']
            if 'entities' in data:
                entity_list = data['entities']
                del data['entities']

            data['added_at'] = datetime.datetime.now()

            django_article = Article.objects.create(**data)
            django_article.save()
            if author_list:
                for author in author_list:
                    django_article.authors.add(
                        Author.objects.filter(pk=author.pk)[0])
            if entities:
                for entity in entity_list:
                    django_article.entities.add(
                        Entity.objects.filter(pk=entity.pk)[0])

        return django_article

    class Meta:
        model = Article
        list_serializer_class = BulkListSerializer
        fields = ('url', 'name', 'created_at',
                  'header_image', 'authors', 'basic_summary', 'entities',)


class PublisherFeedSerializer(serializers.HyperlinkedModelSerializer):

    def to_representation(self, obj):
        return {
            'id': obj.pk,
            'publisher': obj.publisher,
            'feed_url': obj.feed_url,
            'tags': obj.tags,
        }

    class Meta:
        model = PublisherFeed
        fields = ('publisher', 'feed_url', 'tags',)


class PublisherSerializer(serializers.HyperlinkedModelSerializer):

    def to_representation(self, obj):
        return {
            'id': obj.pk,
            'name': obj.name,
            'url': obj.url,
            'publisher': obj.short_name
        }

    class Meta:
        model = Publisher
        fields = ('name', 'short_name', 'url', 'authors', 'basic_summary',)


class AuthorSerializer(serializers.HyperlinkedModelSerializer):

    def to_representation(self, obj):
        return {
            'id': obj.pk,
            'name': obj.name,
            'writes_for': obj.writes_for.values(),
        }

    class Meta:
        model = Author
        fields = ('name', 'writes_for',)
