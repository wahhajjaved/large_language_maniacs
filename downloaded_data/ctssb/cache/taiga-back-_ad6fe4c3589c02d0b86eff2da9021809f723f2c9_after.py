# Copyright (C) 2014 Andrey Antukh <niwi@niwi.be>
# Copyright (C) 2014 Jesús Espino <jespinog@gmail.com>
# Copyright (C) 2014 David Barragán <bameda@dbarragan.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Examples:
# python manage.py rebuild_timeline --settings=settings.local_timeline --initial_date 2014-10-02 --final_date 2014-10-03
# python manage.py rebuild_timeline --settings=settings.local_timeline --purge
# python manage.py rebuild_timeline --settings=settings.local_timeline --initial_date 2014-10-02

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.db.models import Model
from django.db import reset_queries

from taiga.projects.models import Project
from taiga.projects.history import services as history_services
from taiga.projects.history.choices import HistoryType
from taiga.projects.history.models import HistoryEntry
from taiga.timeline.models import Timeline
from taiga.timeline.service import (_add_to_object_timeline, _get_impl_key_from_model,
    _timeline_impl_map, extract_user_info)
from taiga.timeline.signals import on_new_history_entry, _push_to_timelines
from taiga.users.models import User

from unittest.mock import patch
from optparse import make_option

import gc

class BulkCreator(object):
    def __init__(self):
        self.timeline_objects = []
        self.created = None

    def create_element(self, element):
        self.timeline_objects.append(element)
        if len(self.timeline_objects) > 1000:
            self.flush()

    def flush(self):
        Timeline.objects.bulk_create(self.timeline_objects, batch_size=1000)
        del self.timeline_objects
        self.timeline_objects = []
        gc.collect()

bulk_creator = BulkCreator()


def custom_add_to_object_timeline(obj:object, instance:object, event_type:str, namespace:str="default", extra_data:dict={}):
    assert isinstance(obj, Model), "obj must be a instance of Model"
    assert isinstance(instance, Model), "instance must be a instance of Model"
    event_type_key = _get_impl_key_from_model(instance.__class__, event_type)
    impl = _timeline_impl_map.get(event_type_key, None)

    bulk_creator.create_element(Timeline(
        content_object=obj,
        namespace=namespace,
        event_type=event_type_key,
        project=instance.project,
        data=impl(instance, extra_data=extra_data),
        data_content_type = ContentType.objects.get_for_model(instance.__class__),
        created = bulk_creator.created,
    ))


def generate_timeline(initial_date, final_date, project_id):
    if initial_date or final_date or project_id:
        timelines = Timeline.objects.all()
        if initial_date:
            timelines = timelines.filter(created__gte=initial_date)
        if final_date:
            timelines = timelines.filter(created__lt=final_date)
        if project_id:
            timelines = timelines.filter(project__id=project_id)

        timelines.delete()

    with patch('taiga.timeline.service._add_to_object_timeline', new=custom_add_to_object_timeline):
        # Projects api wasn't a HistoryResourceMixin so we can't interate on the HistoryEntries in this case
        projects = Project.objects.order_by("created_date")
        history_entries = HistoryEntry.objects.order_by("created_at")

        if initial_date:
            projects = projects.filter(created_date__gte=initial_date)
            history_entries = history_entries.filter(created_at__gte=initial_date)

        if final_date:
            projects = projects.filter(created_date__lt=final_date)
            history_entries = history_entries.filter(created_at__lt=final_date)

        if project_id:
            project = Project.objects.get(id=project_id)
            us_keys = ['userstories.userstory:%s'%(id) for id in project.user_stories.values_list("id", flat=True)]
            tasks_keys = ['tasks.task:%s'%(id) for id in project.tasks.values_list("id", flat=True)]
            issue_keys = ['issues.issue:%s'%(id) for id in project.issues.values_list("id", flat=True)]
            wiki_keys = ['wiki.wikipage:%s'%(id) for id in project.wiki_pages.values_list("id", flat=True)]
            keys = us_keys + tasks_keys + issue_keys + wiki_keys

            projects = projects.filter(id=project_id)
            history_entries = history_entries.filter(key__in=keys)

            #Memberships
            for membership in project.memberships.exclude(user=None).exclude(user=project.owner):
                bulk_creator.created = membership.created_at
                _push_to_timelines(project, membership.user, membership, "create")

        for project in projects.iterator():
            bulk_creator.created = project.created_date
            print("Project:", bulk_creator.created)
            extra_data = {
                "values_diff": {},
                "user": extract_user_info(project.owner),
            }
            _push_to_timelines(project, project.owner, project, "create", extra_data=extra_data)
            del extra_data

        for historyEntry in history_entries.iterator():
            print("History entry:", historyEntry.created_at)
            try:
                bulk_creator.created = historyEntry.created_at
                on_new_history_entry(None, historyEntry, None)
            except ObjectDoesNotExist as e:
                print("Ignoring")

    bulk_creator.flush()


class Command(BaseCommand):
    help = 'Regenerate project timeline'
    option_list = BaseCommand.option_list + (
        make_option('--purge',
                    action='store_true',
                    dest='purge',
                    default=False,
                    help='Purge existing timelines'),
        ) + (
        make_option('--initial_date',
                    action='store',
                    dest='initial_date',
                    default=None,
                    help='Initial date for timeline generation'),
        ) + (
        make_option('--final_date',
                    action='store',
                    dest='final_date',
                    default=None,
                    help='Final date for timeline generation'),
        ) + (
        make_option('--project',
                    action='store',
                    dest='project',
                    default=None,
                    help='Selected project id for timeline generation'),
        )


    def handle(self, *args, **options):
        debug_enabled = settings.DEBUG
        if debug_enabled:
            print("Please, execute this script only with DEBUG mode disabled (DEBUG=False)")
            return

        if options["purge"] == True:
            Timeline.objects.all().delete()

        generate_timeline(options["initial_date"], options["final_date"], options["project"])
