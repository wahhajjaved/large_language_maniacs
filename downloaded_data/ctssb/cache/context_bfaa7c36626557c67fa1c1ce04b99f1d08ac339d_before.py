# -*- coding: utf-8 -*-
# Third-party app imports
from rest_framework import serializers

# Imports from app
from .models import Type, Entity


class TypeSerializer(serializers.HyperlinkedModelSerializer):

    def to_representation(self, obj):
        return {
            'id': obj.pk,
            'name': obj.name,
            'description': obj.description,
            'parent_type': obj.parent_type,
        }

    def create(self, data):
        parent_type = None
        if 'parent_type' in data:
            parent_type = data['parent_type']
            del data['parent_type']

        django_type = Type.objects.create(**data)
        if parent_type:
            django_type.parent_type = Type.objects.filter(pk=parent_type.pk)[0]

        django_type.save()
        return django_type

    class Meta:
        model = Type
        fields = ('name', 'description', 'parent_type',)


class EntitySerializer(serializers.HyperlinkedModelSerializer):

    def to_representation(self, obj):
        return {
            'id': obj.pk,
            'name': obj.name,
            'description': obj.description,
            'main_type': obj.main_type.name,
            'sub_types': obj.sub_types.values(),
        }

    def create(self, data):
        subtypes = None
        main_type = None
        if 'sub_types' in data:
            subtypes = data['sub_types']
            del data['sub_types']
        if 'main_type' in data:
            main_type = data['main_type']
            del data['main_type']

        django_entity = Entity.objects.create(**data)
        if main_type:
            django_entity.main_type = Type.objects.filter(pk=main_type.pk)[0]
        if subtypes:
            for subtype in subtypes:
                django_entity.sub_types.add(
                    Type.objects.filter(pk=subtype.pk)[0])
        django_entity.save()
        return django_entity

    class Meta:
        model = Entity
        fields = ('name', 'description', 'main_type', 'sub_types',)
