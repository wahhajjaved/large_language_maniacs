# Amara, universalsubtitles.org
#
# Copyright (C) 2013 Participatory Culture Foundation
#
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
# along with this program.  If not, see
# http://www.gnu.org/licenses/agpl-3.0.html.

"""stastic.hitcounts -- count/aggregate hits

This module handles tracking video hits and subtitle language views.
"""

import collections
import datetime
import string

from django import db
from django.db import transaction
from django.db.models import Sum

from statistic import models
from utils import applock

def now():
    return datetime.datetime.now()

def next_month(date):
    if date.month < 12:
        return date.replace(month=date.month+1)
    else:
        return date.replace(year=date.year+1, month=1)

class HitCountMigrater(object):
    """Handles migrating hit counts from table to table.

    We use 3 tables to track hit counts:
        - the hit table that tracks individual hits
        - the per-day table that aggregates hits per-day
        - the per-month table that aggregates hits per-month

    The idea is to balance database table size with precision.  We keep
    detailed data for recent activity, and summarize data for activity that
    happened a while ago.

    Specifically we:
    - Aggregate data from the hit table to the per-day table once the day is
    complete
    - Aggregate data from the per-day table to the per-month table once the
    month is complete
    - Delete rows from the hit table older than 24 hours
    - Delete rows from the per-day table older than 30 days
    """
    def __init__(self, obj_field_name, hit_model, per_day_model,
                 per_month_model, last_hit_counter_migration_type):
        self.obj_field_name = obj_field_name
        self.hit_model = hit_model
        self.per_day_model = per_day_model
        self.per_month_model = per_month_model
        self.last_hit_counter_migration_type = last_hit_counter_migration_type

    def migrate(self):
        lock_name = ('hitcount-migration-%s' %
                     self.last_hit_counter_migration_type)
        with transaction.commit_on_success():
            with applock.lock(lock_name):
                self._migrate()

    def _migrate(self):
        # calculate now once and keep it constant throughout the migration
        now_value = now()
        last_migration = self.get_last_migration()
        cursor = db.connection.cursor()
        self.migrate_hits(cursor, now_value, last_migration)
        self.migrate_per_day_counts(cursor, now_value, last_migration)
        self.delete_old_rows(cursor, now_value)
        self.update_last_hit_counter_migration(now_value, last_migration)

    def get_last_migration(self):
        try:
            return models.LastHitCountMigration.objects.get(
                type=self.last_hit_counter_migration_type)
        except models.LastHitCountMigration.DoesNotExist:
            return models.LastHitCountMigration(
                type=self.last_hit_counter_migration_type,
                date=None)

    def days_to_migrate_hits(self, now, last_migration):
        if last_migration.date is not None:
            day = last_migration.date
        else:
            try:
                first_datetime = (self.hit_model.objects
                                  .values_list('datetime', flat=True)
                                  .order_by('datetime'))[0]
            except IndexError:
                return
            day = first_datetime.date()
        end_day = now.date()
        while day < end_day:
            yield day
            day += datetime.timedelta(days=1)

    def migrate_hits(self, cursor, now, last_migration):
        for date in self.days_to_migrate_hits(now, last_migration):
            self.migrate_hits_for_day(cursor, date)

    def migrate_hits_for_day(self, cursor, date):
        sql = string.Template(
            "INSERT INTO $per_day_table(${obj_field}_id, date, count) "
            "SELECT ${obj_field}_id, %s, COUNT(*) "
            "FROM $hit_table "
            "WHERE datetime >= %s AND datetime < %s "
            "GROUP BY ${obj_field}_id").substitute(
                obj_field=self.obj_field_name,
                per_day_table=self.per_day_model._meta.db_table,
                hit_table=self.hit_model._meta.db_table)
        cursor.execute(sql, (date, date, date + datetime.timedelta(days=1)))

    def months_to_migrate_day_counts(self, now, last_migration):
        if last_migration.date is not None:
            month = last_migration.date.replace(day=1)
        else:
            try:
                first_date = (self.per_day_model.objects
                                  .values_list('date', flat=True)
                                  .order_by('date'))[0]
            except IndexError:
                return
            month = first_date.replace(day=1)
        end_month = now.date().replace(day=1)
        while month < end_month:
            yield month
            month = next_month(month)

    def migrate_per_day_counts(self, cursor, now, last_migration):
        for month in self.months_to_migrate_day_counts(now, last_migration):
            self.migrate_per_day_counts_for_month(cursor, month)

    def migrate_per_day_counts_for_month(self, cursor, month):
        sql = string.Template(
            "INSERT INTO $per_month_table(${obj_field}_id, date, count) "
            "SELECT ${obj_field}_id, %s, SUM(count) "
            "FROM $per_day_table "
            "WHERE date >= %s AND date < %s "
            "GROUP BY ${obj_field}_id").substitute(
                obj_field=self.obj_field_name,
                per_month_table=self.per_month_model._meta.db_table,
                per_day_table=self.per_day_model._meta.db_table)
        cursor.execute(sql, (month, month, next_month(month)))

    def hit_removal_date(self, now):
        return now - datetime.timedelta(days=1)

    def per_day_removal_date(self, now):
        return now.date() - datetime.timedelta(days=30)

    def delete_old_rows(self, cursor, now):
        (self.hit_model.objects
         .filter(datetime__lt=self.hit_removal_date(now))
         .delete())

        (self.per_day_model.objects
         .filter(date__lt=self.per_day_removal_date(now))
         .delete())

    def update_last_hit_counter_migration(self, now, last_migration):
        last_migration.date = now.date()
        last_migration.save()


class VideoHitCountMigrater(HitCountMigrater):
    def migrate_hits_for_day(self, cursor, date):
        HitCountMigrater.migrate_hits_for_day(self, cursor, date)
        sql = """\
UPDATE videos_video
SET view_count=view_count + (
    SELECT count FROM statistic_videoviewcounter counter
    WHERE counter.video_id=videos_video.id
    AND counter.date=%s)
WHERE videos_video.id IN (
    SELECT video_id FROM statistic_videoviewcounter counter
    WHERE counter.date=%s)"""
        cursor.execute(sql, (date, date, ))

class HitCountManager(object):
    """Track hit counts

    HitCountManager is the base class for VideoHitCountManager and
    SubtitleViewCountManager.  It handles the 3 inter-related tables that
    track hit counts, the hit table, the per-day table, and the per-month
    table.
    """

    # subclasses need to define these:

    # name of the field that identifies the object being tracked
    obj_field_name = None
    # model class that tracks individual hits
    hit_model = None
    # model class that tracks per-day hits
    per_day_model = None
    # model class that tracks per-month hits
    per_month_model = None
    # type value for the LastHitCountMigration table
    last_hit_counter_migration_type = None

    # code starts here:
    def __init__(self):
        self.migrater = self.make_hit_count_migrater()

    def make_hit_count_migrater(self):
        return HitCountMigrater(self.obj_field_name, self.hit_model,
                                self.per_day_model,
                                self.per_month_model,
                                self.last_hit_counter_migration_type)

    def add_hit(self, obj):
        self.hit_model.objects.create(**{
            self.obj_field_name: obj,
            'datetime': now()})

    def migrate(self):
        """Migrate hit counts for an object.

        See HitCountMigrater for details on what this does
        """
        self.migrater.migrate()

    def _count_hits(self, obj, start_datetime):
        qs = self.hit_model.objects.filter(**{
            self.obj_field_name: obj, 'datetime__gte': start_datetime
        })
        return qs.count()

    def _total_per_day_counts(self, obj, start_date):
        qs = self.per_day_model.objects.filter(**{
            self.obj_field_name: obj, 'date__gte': start_date,
        })
        rv = qs.aggregate(Sum('count'))['count__sum']
        if rv is not None:
            return rv
        else:
            return 0

    def _total_per_month_counts(self, obj, start_date):
        qs = self.per_month_model.objects.filter(**{
            self.obj_field_name: obj, 'date__gte': start_date,
        })
        rv = qs.aggregate(Sum('count'))['count__sum']
        if rv is not None:
            return rv
        else:
            return 0

    def get_counts(self, obj):
        """Get the hitcounts for an object.

        returns a dict with keys for various counts (today, week, month, year)
        """
        yesterday = now() - datetime.timedelta(days=1)
        counts = self._get_aggregate_counts(obj)
        counts['today'] = self._count_hits(obj, yesterday)
        return counts

    def _get_aggregate_counts(self, obj):
        try:
            last_migration = models.LastHitCountMigration.objects.get(
                type=self.last_hit_counter_migration_type)
        except models.LastHitCountMigration.DoesNotExist:
            return {
                'week': 0,
                'month': 0,
                'year': 0,
            }
        last_week = last_migration.date - datetime.timedelta(days=7)
        last_month = last_migration.date - datetime.timedelta(days=30)
        last_year = last_migration.date.replace(
            day=1, year=last_migration.date.year-1)

        return {
            'week': self._total_per_day_counts(obj, last_week),
            'month': self._total_per_day_counts(obj, last_month),
            'year': self._total_per_month_counts(obj, last_year),
        }

class VideoHitCountManager(HitCountManager):
    """Track hits on video pages"""
    obj_field_name = 'video'
    hit_model = models.VideoHit
    # for historical reasons, the per-day model is called VideoViewCounter
    per_day_model = models.VideoViewCounter
    per_month_model = models.VideoHitsPerMonth
    last_hit_counter_migration_type = 'V'

    def make_hit_count_migrater(self):
        return VideoHitCountMigrater(self.obj_field_name, self.hit_model,
                                     self.per_day_model,
                                     self.per_month_model,
                                     self.last_hit_counter_migration_type)

class SubtitleViewCountManager(HitCountManager):
    """Track subtitle views for video languages."""
    # NOTE: Right now this counter is not actually active because we don't
    # have a good way of knowing when the hit happened, especially for
    # languages that get synced to other servers like youtube.

    obj_field_name = 'subtitle_language'
    hit_model = models.SubtitleView
    per_day_model = models.SubtitleViewsPerDay
    per_month_model = models.SubtitleViewsPerMonth
    last_hit_counter_migration_type = 'S'

video_hits = VideoHitCountManager()
subtitle_views = SubtitleViewCountManager()

def migrate_all():
    video_counts.migrate()
    subtitle_views.migrate()
