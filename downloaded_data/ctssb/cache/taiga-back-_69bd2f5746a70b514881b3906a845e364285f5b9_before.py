# -*- coding: utf-8 -*-

from rest_framework import serializers

from greenmine.scrum.models import *
from picklefield.fields import dbsafe_encode, dbsafe_decode

import json, reversion


class PickleField(serializers.WritableField):
    """
    Pickle objects serializer.
    """
    def to_native(self, obj):
        return obj

    def from_native(self, data):
        return data


class PointsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Points
        fields = ()


class ProjectSerializer(serializers.ModelSerializer):
    tags = PickleField()
    list_of_milestones = serializers.Field(source='list_of_milestones')

    class Meta:
        model = Project
        fields = ()


class UserStorySerializer(serializers.ModelSerializer):
    tags = PickleField()
    is_closed = serializers.Field(source='is_closed')

    class Meta:
        model = UserStory
        fields = ()
        depth = 0


class MilestoneSerializer(serializers.ModelSerializer):
    user_stories = UserStorySerializer(many=True, required=False)

    class Meta:
        model = Milestone
        fields = ()


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField('get_url')

    def get_url(self, obj):
        # FIXME: add sites or correct url.
        return "http://localhost:8000{0}".format(obj.attached_file.url)

    class Meta:
        model = Attachment
        fields = ('id', 'project', 'owner', 'attached_file',
                  'created_date', 'object_id', 'url')
        read_only_fields = ('owner',)


class TaskSerializer(serializers.ModelSerializer):
    tags = PickleField(blank=True, default=[])

    class Meta:
        model = Task
        fields = ()


class IssueSerializer(serializers.ModelSerializer):
    tags = PickleField()
    comment = serializers.SerializerMethodField('get_comment')
    history = serializers.SerializerMethodField('get_history')
    is_closed = serializers.Field(source='is_closed')

    class Meta:
        model = Issue
        fields = ()

    def get_comment(self, obj):
        return ''

    def get_issues_diff(self, old_issue_version, new_issue_version):
        old_obj = old_issue_version.field_dict
        new_obj = new_issue_version.field_dict

        diff_dict = {
            'modified_date': new_obj['modified_date'],
            'by': old_issue_version.revision.user,
            'comment': old_issue_version.revision.comment,
        }

        for key in old_obj.keys():
            if key == 'modified_date':
                continue

            if old_obj[key] == new_obj[key]:
                continue

            diff_dict[key] = {
                'old': old_obj[key],
                'new': new_obj[key],
            }

        return diff_dict

    def get_history(self, obj):
        diff_list = []
        current = None

        for version in reversed(list(reversion.get_for_object(obj))):
            if current:
                issues_diff = self.get_issues_diff(version, current)
                diff_list.append(issues_diff)

            current = version

        return diff_list


class SeveritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Severity
        fields = ()


class IssueStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueStatus
        fields = ()


class TaskStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStatus
        fields = ()


class UserStoryStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStoryStatus
        fields = ()


class PrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Priority
        fields = ()


class IssueTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueType
        fields = ()


