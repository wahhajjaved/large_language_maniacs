#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Amara, universalsubtitles.org
#
# Copyright (C) 2013 Participatory Culture Foundation
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program.  If not, see http://www.gnu.org/licenses/agpl-3.0.html.

"""Long-running data migration script for the Data Model Refactor."""

# #      __     __------
# #   __/o `\ ,~   _~~  . .. pb. ..
# #  ~ -.   ,'   _~-----
# #      `\     ~~~--_'__
# #        `~-==-~~~~~---'
# #
# # The [Arctic Tern] is strongly migratory, seeing two summers each year as it
# # migrates from its northern breeding grounds along a winding route to the
# # oceans around Antarctica and back, a round trip of about 70,900 km (44,300
# # miles) each year.  This is by far the longest regular migration by any known
# # animal.
# #
# # https://en.wikipedia.org/wiki/Arctic_Tern

import datetime
import csv as csv_module
import os, sys
import random
import re
import warnings
from optparse import OptionGroup, OptionParser


csv = csv_module.writer(sys.stdout)
single = False
language_pk = None
dry = False

BOLD_RE_INNER = re.compile(r'\*\*(\S+?)\*\*')
BOLD_RE_OUTER = re.compile(r'\b\*\*(.+?)\*\*\b')
ITALIC_RE_INNER = re.compile(r'\*(\S+?)\*')
ITALIC_RE_OUTER = re.compile(r'\b\*(.+?)\*\b')
UNDER_RE_INNER = re.compile(r'_(\S+?)_')
UNDER_RE_OUTER = re.compile(r'\b_(.+?)_\b')


# Utilities -------------------------------------------------------------------
def err(m):
    sys.stderr.write(m)
    sys.stderr.write("\n")
    sys.stderr.flush()

def log(model, event_type, original_pk, new_pk, extra=None):
    csv.writerow([
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        model,
        event_type,
        str(original_pk),
        str(new_pk),
        repr(extra),
    ])
    sys.stdout.flush()

def die(msg):
    sys.stderr.write('ERROR: %s\n' % msg)
    sys.exit(1)

def get_random(qs):
    """Return a single random model from the given queryset.

    This works around MySQL's broken-ass ORDER BY RAND() so we don't spend the
    next year migrating data.

    """
    return qs[random.randint(0, qs.count())]

def get_specific_language(pk):
    from apps.videos.models import SubtitleLanguage

    try:
        sl = SubtitleLanguage.objects.get(pk=int(language_pk))
    except SubtitleLanguage.DoesNotExist:
        die("No SubtitleLanguage exists with primary key %s!" % language_pk)

    if sl.standard_language and sl.standard_language.needs_sync:
        die("SubtitleLanguage %s is a translation of %s, which must be synced first!"
            % (language_pk, sl.standard_language.pk))

    return sl

def get_unsynced_subtitle_language():
    """Return a SubtitleLanguage that needs to be synced.

    SubtitleLanguages will be returned in no specific order (except that "base"
    languages will always come before their translations).  Forcing the syncing
    code to deal with this will make it robust against different data in
    dev/staging/prod.

    """
    from apps.videos.models import SubtitleLanguage

    try:
        sl = get_random(SubtitleLanguage.objects.filter(needs_sync=True))
    except IndexError:
        return None

    if sl.standard_language and sl.standard_language.needs_sync:
        return sl.standard_language
    else:
        return sl

def get_unsynced_subtitle_version_language():
    """Return a SubtitleLanguage with one or more unsynced versions.

    This will let us sync SubtitleVersions in "chunks" of a language at a time.

    The SubtitleLanguage itself must have already been synced on its own.

    Languages will be returned in no specific order (but "base" languages will
    come before translations).  Forcing the syncing code to deal with this will
    make it robust against different data in dev/staging/prod.

    """
    from apps.videos.models import SubtitleVersion

    try:
        sv = get_random(SubtitleVersion.objects.filter(
            needs_sync=True, language__needs_sync=False
        ))
    except IndexError:
        return None

    sl = sv.language
    base = sl.standard_language

    if base:
        # If the version we picked is from a translation, and the source version
        # has unsynced versions, we should sync *that* one first.
        unsynced_base = (base.subtitleversion_set.filter(needs_sync=True)
                                                 .exists())
        if unsynced_base:
            return base

    return sl

def get_counts():
    from apps.videos.models import SubtitleLanguage, SubtitleVersion

    slo = SubtitleLanguage.objects
    sl_total = slo.count()
    sl_unsynced = slo.filter(new_subtitle_language=None, needs_sync=True).count()
    sl_broken   = slo.filter(new_subtitle_language=None, needs_sync=False).count()
    sl_outdated = slo.filter(new_subtitle_language__isnull=False, needs_sync=True).count()
    sl_done     = slo.filter(new_subtitle_language__isnull=False, needs_sync=False).count()

    svo = SubtitleVersion.objects
    sv_total = svo.count()
    sv_unsynced = svo.filter(new_subtitle_version=None, needs_sync=True).count()
    sv_broken   = svo.filter(new_subtitle_version=None, needs_sync=False).count()
    sv_outdated = svo.filter(new_subtitle_version__isnull=False, needs_sync=True).count()
    sv_done     = svo.filter(new_subtitle_version__isnull=False, needs_sync=False).count()

    return (sl_total, sl_unsynced, sl_broken, sl_outdated, sl_done,
            sv_total, sv_unsynced, sv_broken, sv_outdated, sv_done,)

def markup_to_dfxp(text):
    from django.template.defaultfilters import escape

    # Escape the HTML entities in the text first.  So something like:
    #
    #     x < _10_
    #
    # gets escaped to:
    #
    #     x &lt; _10_
    text = escape(text)

    # Now we substitute in the DFXP formatting tags for our custom Markdown-like
    # thing:
    #
    #     x &lt; _10_
    #
    # gets turned into:
    #
    #     x &lt; <span tts:textDecoration="underline">10</span>
    text = BOLD_RE_INNER.sub(r'<span tts:fontWeight="bold">\1</span>', text)
    text = BOLD_RE_OUTER.sub(r'<span tts:fontWeight="bold">\1</span>', text)
    text = ITALIC_RE_INNER.sub(r'<span tts:fontStyle="italic">\1</span>', text)
    text = ITALIC_RE_OUTER.sub(r'<span tts:fontStyle="italic">\1</span>', text)
    text = UNDER_RE_INNER.sub(r'<span tts:textDecoration="underline">\1</span>', text)
    text = UNDER_RE_OUTER.sub(r'<span tts:textDecoration="underline">\1</span>', text)

    return text

def log_subtitle_error(sv, subtitles):
    err("=" * 60)
    err("Error occured for version: %s" % sv.pk)
    err("=" * 60)
    err("Subtitles:")
    err("-" * 60)
    from pprint import pprint
    pprint(subtitles, stream=sys.stderr)
    err("=" * 60)

def fix_blank_original(video):
    # Copied from the widget RPC code in production.
    # Note that this doesn't necessarily fix all blank languages.  The ones that
    # are marked as "is_original=False" and have versions won't be touched.
    languages = video.subtitlelanguage_set.filter(language='')
    to_delete = []
    for sl in languages:
        if not sl.latest_version():
            # result of weird practice of saving SL with is_original=True
            # and blank language code on Video creation.
            to_delete.append(sl)
        elif sl.is_original:
            # Mark blank originals as English.
            sl.language = 'en'
            sl.save()
            log('SubtitleLanguage', 'englished', sl.pk, None)
        else:
            # TODO: Determine what to do with these.
            log('SubtitleLanguage', 'skipped', sl.pk, None)
    for sl in to_delete:
        log('SubtitleLanguage', 'deleted', sl.pk, None)
        sl.delete()


# These mock request/user classes are for writelocking the old languages.
class FakeUser(object):
    def is_authenticated(self):
        return False

class FakeRequest(object):
    def __init__(self):
        self.browser_id = 'tern_sync'
        self.user = FakeUser()


TERN_REQUEST = FakeRequest()


# Basic Commands --------------------------------------------------------------
def header():
    print 'Time,Model,Action,Original PK,New PK'

def count():
    sl_total, sl_unsynced, sl_broken, sl_outdated, sl_done, \
    sv_total, sv_unsynced, sv_broken, sv_outdated, sv_done = get_counts()

    print "SubtitleLanguage"
    print "-" * 40
    print "%10d total" % sl_total
    print "%10d never synced" % sl_unsynced
    print "%10d synced but out of date" % sl_outdated
    print "%10d synced and up to date" % sl_done
    print "%10d broken" % sl_broken
    print

    print "SubtitleVersion"
    print "-" * 40
    print "%10d total" % sv_total
    print "%10d never synced" % sv_unsynced
    print "%10d synced but out of date" % sv_outdated
    print "%10d synced and up to date" % sv_done
    print "%10d broken" % sv_broken
    print

def report_metrics():
    from utils.metrics import Gauge

    sl_total, sl_unsynced, sl_broken, sl_outdated, sl_done, \
    sv_total, sv_unsynced, sv_broken, sv_outdated, sv_done = get_counts()

    Gauge('data-model-refactor.subtitle-language.total').report(sl_total)
    Gauge('data-model-refactor.subtitle-language.unsynced').report(sl_unsynced)
    Gauge('data-model-refactor.subtitle-language.broken').report(sl_broken)
    Gauge('data-model-refactor.subtitle-language.outdated').report(sl_outdated)
    Gauge('data-model-refactor.subtitle-language.done').report(sl_done)

    Gauge('data-model-refactor.subtitle-version.total').report(sv_total)
    Gauge('data-model-refactor.subtitle-version.unsynced').report(sv_unsynced)
    Gauge('data-model-refactor.subtitle-version.broken').report(sv_broken)
    Gauge('data-model-refactor.subtitle-version.outdated').report(sv_outdated)
    Gauge('data-model-refactor.subtitle-version.done').report(sv_done)


# Languages -------------------------------------------------------------------
def _add_sl(sl):
    """Actually create a new SL in the database for the given old SL.
    
    Doesn't perform any sanity checks.

    """
    from apps.subtitles.models import SubtitleLanguage as NewSubtitleLanguage

    nsl = NewSubtitleLanguage(
        video=sl.video,
        language_code=sl.language,
        subtitles_complete=sl.is_complete,
        writelock_time=sl.writelock_time,
        writelock_session_key=sl.writelock_session_key,
        writelock_owner=sl.writelock_owner,
        is_forked=sl.is_forked,
    )

    if not dry:
        nsl.save()

        # Has to be set separately because it's a magic Redis field.
        nsl.subtitles_fetched_counter = sl.subtitles_fetched_counter

        # TODO: is this right, or does it need to be save()'ed?
        nsl.followers = sl.followers.all()

        sl.new_subtitle_language = nsl
        sl.needs_sync = False
        sl.save(tern_sync=True)

    return nsl


def _stack_version(sv, nsl):
    """Stack the given version onto the given new SL."""
    from apps.subtitles import pipeline

    visibility = 'public' if sv.is_public else 'private'

    subtitles = _get_subtitles(sv)

    try:
        subtitles = list(subtitles)
        nsv = pipeline.add_subtitles(
            nsl.video, nsl.language_code, subtitles,
            title=sv.title, description=sv.description, parents=[],
            visibility=visibility, author=sv.user,
            created=sv.datetime_started)
    except:
        log_subtitle_error(sv, subtitles)
        raise

    sv.new_subtitle_version = nsv
    sv.needs_sync = False

    sv.save(tern_sync=True)

    log('SubtitleVersion', 'stacked', sv.pk, nsv.pk)

def _stack_versions(sls):
    """Stack the versions of the given SubtitleLanguages.

    There are a couple of parts to this:

    1. We need to create a single new SL that will contain all the data.
    2. We need to shove all the versions into it.

    """
    from apps.subtitles.models import SubtitleLanguage as NewSubtitleLanguage

    # First we'll turn the Queryset into a list so we don't hit the DB all the
    # time.
    sls = list(sls)

    try:
        for sl in sls:
            if sl.can_writelock(TERN_REQUEST):
                sl.writelock(TERN_REQUEST)
            else:
                # If any of the languages in question are writelocked, bail.
                return

        # All these SLs share the same video and language code.
        video = sls[0].video
        language_code = sls[0].language

        # Sort the languages properly.
        def _last_version_date(sl):
            """SubtitleLanguages will be stacked in order of last version."""
            last_sv = sl.subtitleversion_set.order_by('-version_no')[0]
            return last_sv.datetime_started

        sls = sorted(sls, key=_last_version_date)

        # Next we'll turn the list of languages into a (flat) list of versions.
        svs = []
        for sl in sls:
            for sv in sl.subtitleversion_set.order_by('version_no'):
                svs.append(sv)

        # Now we can get the single new SL for this batch.
        try:
            # We can't just blindly create one, because there may already be one.
            nsl = NewSubtitleLanguage.objects.get(video=video,
                                                  language_code=language_code)
        except NewSubtitleLanguage.DoesNotExist:
            # If there aren't any yet, we'll add one and base it off the most
            # recent SL.
            source = sls[-1]
            nsl = _add_sl(source)
            log('SubtitleLanguage', 'created_single_for_dupe', source.pk, nsl.pk)

        # And finally we'll stack the versions into it.
        for sv in svs:
            if not sv.needs_sync:
                # This version has already been synced at some point and is up
                # to date.
                pass
            else:
                # We need to sync this subtitle version.
                if sv.new_subtitle_version:
                    # This version has already been synced in the past, but
                    # needs an update.  Since its new_subtitle_version field
                    # will have been set we can just use the normal tern
                    # machinery here.
                    _update_subtitle_version(sv)
                else:
                    # This version has never been synced before, so we'll stack
                    # it on top of the rest.
                    _stack_version(sv, nsl)

        # Update the batch of duplicate SLs to point to the new one.
        for sl in sls:
            sl.needs_sync = False
            sl.new_subtitle_language = nsl
            sl.save(tern_sync=True)
    finally:
        # Release the writelocks on any languages that tern locked (but not on
        # languages that were locked by someone else).
        for sl in sls:
            if sl.can_writelock(TERN_REQUEST):
                sl.release_writelock()


def _handle_duplicate_languages(sl):
    """Handle SubtitleLanguages who have siblings with the same language code.

    There are two steps to this process:

    1. First, if there are any siblings with 0 versions, delete them.
    2. Otherwise, we need to "stack" their versions.

    Yes, this means that running tern --languages will actually sync a few
    versions as well.  I don't think it's a big problem.

    """
    from apps.videos.models import SubtitleLanguage

    if dry:
        # Yeah I'm not even gonna try to handle this fully, we'll just bail on
        # dry runs.
        return

    sls = SubtitleLanguage.objects.filter(video=sl.video, language=sl.language)

    empty_sls = []
    for sl in sls:
        if not sl.subtitleversion_set.exists():
            empty_sls.append(sl)

    if empty_sls:
        for sl in empty_sls:
            log('SubtitleLanguage', 'deleted_empty', sl.pk, None)
            sl.delete()
    else:
        _stack_versions(sls)


def _create_subtitle_language(sl):
    """Sync the given subtitle language, creating a new one."""
    from apps.subtitles.models import VALID_LANGUAGE_CODES
    from apps.videos.models import SubtitleLanguage
    from utils.metrics import Meter

    duplicates = (SubtitleLanguage.objects.filter(video=sl.video,
                                                  language=sl.language)
                                          .exclude(pk=sl.pk)
                                          .exists())

    if duplicates:
        log('SubtitleLanguage', 'ERROR_DUPLICATE_LANGUAGE', sl.pk, None)
        log('SubtitleLanguage', 'duplicate_version_counts', sl.pk, None,
            [l.subtitleversion_set.count() for l
             in sl.video.subtitlelanguage_set.filter(language=sl.language)]
        )
        log('SubtitleLanguage', 'duplicate_subtitle_counts', sl.pk, None,
            [[len(v.subtitles())
              for v in l.subtitleversion_set.order_by('version_no')]
             for l in sl.video.subtitlelanguage_set.filter(language=sl.language)]
        )
        Meter('data-model-refactor.language-errors.duplicate-language').inc()
        _handle_duplicate_languages(sl)
    elif sl.language not in VALID_LANGUAGE_CODES:
        log('SubtitleLanguage', 'ERROR_INVALID_LANGUAGE_CODE', sl.pk, None)
        Meter('data-model-refactor.language-errors.invalid-language-code').inc()
    else:
        nsl = _add_sl(sl)
        log('SubtitleLanguage', 'create', sl.pk, nsl.pk)


def _update_subtitle_language(sl):
    """Sync the given subtitle language, updating the existing new SL."""

    nsl = sl.new_subtitle_language

    nsl.video = sl.video
    nsl.language_code = sl.language
    nsl.subtitles_complete = sl.is_complete
    nsl.writelock_time = sl.writelock_time
    nsl.writelock_session_key = sl.writelock_session_key
    nsl.writelock_owner = sl.writelock_owner
    nsl.is_forked = sl.is_forked
    nsl.subtitles_fetched_counter = sl.subtitles_fetched_counter

    if not dry:
        nsl.save()

        # TODO: is this right, or does it need to be save()'ed?
        nsl.followers = sl.followers.all()

        sl.needs_sync = False
        sl.save(tern_sync=True)

    log('SubtitleLanguage', 'update', sl.pk, nsl.pk)


def _sync_language(language_pk=None):
    """Try to sync one SubtitleLanguage.

    Returns True if a language was synced (or skipped, but we should try it
    again later), False if there were no more left.

    """

    from utils.metrics import Meter

    sl = (get_specific_language(language_pk)
          if language_pk
          else get_unsynced_subtitle_language())

    if not sl:
        return False

    if sl.can_writelock(TERN_REQUEST):
        sl.writelock(TERN_REQUEST)
    else:
        # If we picked a writelocked language, bail for now, but come back to it
        # later.
        log('SubtitleLanguage', 'ERROR_WRITELOCKED', sl.pk, None)
        Meter('data-model-refactor.language-errors.writelocked').inc()
        return True

    try:
        if sl.language == '':
            fix_blank_original(sl.video)

            # For now, we'll actually bail on this language and come back to it
            # later.  Hopefully it will have been fixed by the above call, but
            # there's a chance that it's is_original=False and so is still borked.
            log('SubtitleLanguage', 'ERROR_EMPTY_LANGUAGE', sl.pk, None)
            Meter('data-model-refactor.language-errors.empty-language').inc()
            return True

        if sl.new_subtitle_language:
            _update_subtitle_language(sl)
        else:
            _create_subtitle_language(sl)
    except:
        Meter('data-model-refactor.language-errors.other').inc()
        raise
    finally:
        sl.release_writelock()

    if not dry:
        Meter('data-model-refactor.language-syncs').inc()

        if random.random() < 0.01:
            report_metrics()

    return True

def sync_languages():
    if language_pk:
        result = _sync_language(language_pk)
    else:
        result = _sync_language()
        if not single:
            while result:
                result = _sync_language()


# Versions --------------------------------------------------------------------
def _get_subtitles(sv):
    """Return a generator of subtitle tuples for the given (old) version."""

    subtitle_objects = sv.subtitle_set.all()

    if not sv.is_dependent():
        # If this version is not dependent on another its subtitle set should be
        # self-contained.  We can just iterate through it and yield the
        # appropriate fields.
        for s in subtitle_objects:
            yield (
                s.start_time,
                s.end_time,
                markup_to_dfxp(s.subtitle_text),
                {'new_paragraph': s.start_of_paragraph},
            )
    else:
        # Otherwise this is a translation and we need to look at the translation
        # source to get the timing data.  Kill me now.
        source_version = sv._get_standard_collection(public_only=True)

        if source_version:
            source_subtitles = dict(
                (s.subtitle_id, s)
                for s in source_version.subtitle_set.all()
            )
        else:
            # If we can't get the source subtitles for some reason then we'll do
            # the best we can (basically: the subs in the target version will be
            # marked as unsynced).
            source_subtitles = {}

        for s in subtitle_objects:
            source = source_subtitles.get(s.subtitle_id)

            if source:
                start = source.start_time
                end = source.end_time
                paragraph = source.start_of_paragraph
            else:
                start = None
                end = None
                paragraph = s.start_of_paragraph

            yield (
                start,
                end,
                markup_to_dfxp(s.subtitle_text),
                {'new_paragraph': paragraph},
            )


def _create_subtitle_version(sv, last_version):
    """Sync the old SubtitleVersion by creating a new SubtitleVersion.

    If this language is a translation, and we're creating the final version in
    the chain, the parents of the new version will set to the tip of the source:

    """
    from apps.subtitles import pipeline

    sl = sv.language
    nsl = sl.new_subtitle_language

    visibility = 'public' if sv.is_public else 'private'

    subtitles = _get_subtitles(sv)

    parents = []
    if last_version and sl.is_dependent():
        tip = sl.standard_language.new_subtitle_language.get_tip()
        if tip:
            parents = [tip]

    if not dry:
        try:
            subtitles = list(subtitles)
            nsv = pipeline.add_subtitles(
                nsl.video, nsl.language_code, subtitles,
                title=sv.title, description=sv.description, parents=parents,
                visibility=visibility, author=sv.user,
                created=sv.datetime_started)
        except:
            log_subtitle_error(sv, subtitles)
            raise

        sv.new_subtitle_version = nsv
        sv.needs_sync = False

        sv.save(tern_sync=True)

        log('SubtitleVersion', 'create', sv.pk, nsv.pk)


def _update_subtitle_version(sv):
    """Update a previously-synced SubtitleVersion.

    The new SubtitleVersion *should* be immutable in the new data model, but for
    now there may be a few changes.

    """
    nsv = sv.new_subtitle_version

    nsv.title = sv.title
    nsv.description = sv.description
    nsv.note = sv.note
    nsv.visibility = 'public' if sv.is_public else 'private'

    sv.needs_sync = False

    if not dry:
        nsv.save()
        sv.save(tern_sync=True)

    log('SubtitleVersion', 'update', sv.pk, nsv.pk)


def _sync_versions(language_pk=None):
    """Sync a single language worth of SubtitleVersions."""

    from utils.metrics import Meter
    meter = Meter('data-model-refactor.version-syncs')

    sl = get_unsynced_subtitle_version_language()

    if not sl:
        return False

    if sl.can_writelock(TERN_REQUEST):
        sl.writelock(TERN_REQUEST)
    else:
        # If we picked a writelocked language, bail for now, but come back to it
        # later.
        log('SubtitleLanguage', 'ERROR_WRITELOCKED', sl.pk, None)
        Meter('data-model-refactor.version-errors.writelocked').inc()
        return True

    try:
        # First update any versions that have been synced but have changed since.
        versions = sl.subtitleversion_set.filter(needs_sync=True,
                                                 new_subtitle_version__isnull=False)

        for version in versions.order_by('version_no'):
            _update_subtitle_version(version)
            if not dry:
                meter.inc()

        # Then sync any new versions.
        versions = sl.subtitleversion_set.filter(needs_sync=True,
                                                 new_subtitle_version=None)

        # This is ugly, but we (may) need to do something special on the last
        # version we sync.
        new_versions = list(versions.order_by('version_no'))

        for version in new_versions[:-1]:
            _create_subtitle_version(version, False)
            if not dry:
                meter.inc()

        for version in new_versions[-1:]:
            _create_subtitle_version(version, True)
            if not dry:
                meter.inc()
    except:
        Meter('data-model-refactor.version-errors.other').inc()
        raise
    finally:
        sl.release_writelock()

    if not dry:
        if random.random() < 0.01:
            report_metrics()

    return True

def sync_versions():
    if language_pk:
        _sync_versions(language_pk)
    else:
        result = _sync_versions()
        if not single:
            while result:
                result = _sync_versions()


# Setup -----------------------------------------------------------------------
def setup_path():
    """Set up the Python path with the appropriate magic directories."""

    sys.path.insert(0, './apps')
    sys.path.insert(0, './libs')
    sys.path.insert(0, '..') # Don't ask.
    sys.path.insert(0, '.')

def setup_settings(options):
    """Set up the Django settings module boilerplate."""

    if not options.settings:
        die('you must specify a Django settings module!')

    os.environ['DJANGO_SETTINGS_MODULE'] = options.settings

    from django.conf import settings
    assert settings
    settings.TERN_IMPORT = True


# Main ------------------------------------------------------------------------
def build_option_parser():
    p = OptionParser('usage: %prog [options]')

    p.add_option('-d', '--dry-run', default=False,
                 dest='dry', action='store_true',
                 help='don\'t actually write the the DB')

    p.add_option('-o', '--one', default=False,
                 dest='single', action='store_true',
                 help='only sync one object instead of all of them')

    p.add_option('-l', '--language-pk', default=None,
                 help='primary key of a specific language to sync (implies --one)',
                 metavar='PRIMARY_KEY')

    p.add_option('-s', '--settings', default=None,
                 help='django settings module to use',
                 metavar='MODULE_NAME')

    g = OptionGroup(p, "Commands")

    g.add_option('-C', '--count', dest='command', default=None,
                 action='store_const', const='count',
                 help='output the number of unsynced items remaining')

    g.add_option('-M', '--report-metrics', dest='command', default=None,
                 action='store_const', const='report_metrics',
                 help='report the counts to the metrics server')

    g.add_option('-L', '--languages', dest='command',
                 action='store_const', const='languages',
                 help='sync SubtitleLanguage objects')

    g.add_option('-V', '--versions', dest='command',
                 action='store_const', const='versions',
                 help='sync SubtitleVersion objects')

    g.add_option('-H', '--header', dest='command',
                 action='store_const', const='header',
                 help='output the header for the CSV output')

    p.add_option_group(g)

    return p

def main():
    global dry, single, language_pk

    parser = build_option_parser()
    (options, args) = parser.parse_args()

    if not options.command:
        die('no command given!')

    single = options.single
    language_pk = options.language_pk
    dry = options.dry

    setup_path()
    setup_settings(options)

    if options.command == 'count':
        count()
    elif options.command == 'languages':
        sync_languages()
    elif options.command == 'versions':
        sync_versions()
    elif options.command == 'header':
        header()
    elif options.command == 'report_metrics':
        report_metrics()

if __name__ == '__main__':
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        warnings.filterwarnings("ignore", category=UserWarning, message=".*was already imported from.*")
        warnings.filterwarnings("ignore", message=".*integer argument expected, got float.*")

        main()
