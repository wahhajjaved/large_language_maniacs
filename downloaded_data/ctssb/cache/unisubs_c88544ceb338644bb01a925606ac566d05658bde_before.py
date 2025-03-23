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
import json
from django.contrib.auth.decorators import login_required

from videos.models import Video
from teams.models import Task
from subtitles.models import SubtitleLanguage, SubtitleVersion

from django.db.models import Count
from django.contrib import messages
from django.template import RequestContext
from django.utils.translation import ugettext as _
from django.shortcuts import render_to_response, get_object_or_404, redirect

from teams.permissions import can_post_edit_subtitles, can_assign_task


def _version_data(version):
    '''
    Creates a dict with version info, suitable for encoding
    into json and bootstrapping the editor.
    '''
    return {
        'number': version.version_number,
        'subtitlesXML': version.get_subtitles().to_xml(),
        'title': version.title,
        'description': version.description,
    }

def _language_data(language, editing_version, translated_from_version):
    '''
    Creates a dict with language info, suitable for encoding
    into json and bootstrapping the editor. Includes
    the version data for the version being edited and the
    original translation source, if any.
    '''
    versions_data = []

    for version_number in range(1, language.num_versions +1):
        version_data = {'version_no':version_number}
        if editing_version and editing_version.version_number == version_number and \
            editing_version.subtitle_language == language:
            version_data.update(_version_data(editing_version))
        elif translated_from_version and translated_from_version.version_number == version_number and \
            translated_from_version.subtitle_language == language:
            version_data.update(_version_data(translated_from_version))

        versions_data.append(version_data)

    subtitle_language = editing_version.subtitle_language if editing_version else ''

    return {
        'translatedFrom': translated_from_version and {
            'language_code': translated_from_version.subtitle_language.language_code,
            'version_number': translated_from_version.version_number,
        },
        'editingLanguage': language == subtitle_language,
        'code': language.language_code,
        'name': language.get_language_code_display(),
        'pk': language.pk,
        'numVersions': language.num_versions,
        'versions': versions_data,
        'is_primary_audio_language': language.is_primary_audio_language()
    }

def _check_team_video_locking(user, video, language_code, task_id=None):
    """Check whether the a team prevents the user from editing the subs.

    Returns a message appropriate for sending back if the user should be
    prevented from editing them, or None if the user can safely edit.

    """
    team_video = video.get_team_video()

    if not team_video:
        # If there's no team video to worry about, just bail early.
        return None, None

    team = team_video.team

    if team.is_visible:
        message = _(u"These subtitles are moderated. See the %s team page for information on how to contribute." % str(team_video.team))
    else:
        message = _(u"Sorry, these subtitles are privately moderated.")

    if not team_video.video.can_user_see(user):
        return message, None

    language = video.subtitle_language(language_code)

    if (language and language.is_complete_and_synced()
                 and team.moderates_videos()
                 and not can_post_edit_subtitles(team, user)):
        return _("Sorry, you do not have the permission to edit these subtitles. If you believe that they need correction, please contact the team administrator."), None

    # Check that there are no open tasks for this action.
    # todo: make this better.
    if task_id:
        tasks = [Task.objects.get(id=task_id)]
    else:
        tasks = team_video.task_set.incomplete().filter(language__in=[language_code, ''])

    if tasks:
        task = tasks[0]
        # can_assign verify if the user has permission to either
        # 1. assign the task to himself
        # 2. do the task himself (the task is assigned to him)
        if (task.assignee and task.assignee != user) or (not task.assignee and not can_assign_task(task, user)):
            return _("You can't edit because there is a task for this language and you can't complete it."), task
        else:
            return None, task

    return None, None

@login_required
def subtitle_editor(request, video_id, language_code, task_id=None):
    '''
    Renders the subtitle-editor page, with all data neeeded for the UI
    as a json object on the html document.
    If the language does not exist, it will create one and lock it.
    Also decides what source version should be shown initially (if
    it is a translation).
    '''
    # FIXME: permissions
    video = get_object_or_404(Video, video_id=video_id)

    try:
        editing_language = video.newsubtitlelanguage_set.get(language_code=language_code)
    except SubtitleLanguage.DoesNotExist:
        editing_language = SubtitleLanguage(video=video,language_code=language_code)

    if not editing_language.can_writelock(request.browser_id):
        messages.error(request, _("You can't edit this subtitle because it's locked"))
        return redirect(video)

    message, task = _check_team_video_locking(request.user, video, language_code, task_id)

    if message:
        messages.error(request, message)
        return redirect(video)

    editing_language.writelock(request.user, request.browser_id, save=True)

    # if this language is a traslation, show both
    editing_version = editing_language.get_tip(public=False)
    translated_from_version = None
    lineage = editing_version and editing_version.get_lineage()
    translated_from_language_code = editing_language.get_translation_source_language()

    if editing_version and translated_from_language_code and \
        translated_from_language_code != editing_language.language_code :
        translated_from_version = SubtitleVersion.objects.get(
            subtitle_language__video=video,
            subtitle_language__language_code=translated_from_language_code,
            version_number=lineage.values()[0]
        )

    languages = video.newsubtitlelanguage_set.having_nonempty_versions().annotate(
        num_versions=Count('subtitleversion'))

    editor_data = {
        # front end needs this to be able to set the correct
        # api headers for saving subs
        'authHeaders': {
            'x-api-username': request.user.username,
            'x-apikey': request.user.get_api_key()
        },
        'video': {
            'id': video.video_id,
            'videoURL': video.get_video_url()
        },
        'languages': [_language_data(lang, editing_version, translated_from_version) for lang in languages],
    }

    if task:
        editor_data['task'] = task.id

    return render_to_response("subtitles/subtitle-editor.html", {
        'video': video,
        'language': editing_language,
        'other_languages': languages,
        'version': editing_version,
        'translated_from_version': translated_from_version,
        'task': task,
        'editor_data': json.dumps(editor_data, indent=4)
    }, context_instance=RequestContext(request))

