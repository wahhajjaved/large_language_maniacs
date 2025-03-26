# Amara, universalsubtitles.org
#
# Copyright (C) 2012 Participatory Culture Foundation
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
import logging
from datetime import datetime

from django.conf import settings
from django.db.models import Sum, Q
from django.utils import translation
from django.utils.translation import ugettext as _

from icanhaz.models import VideoVisibilityPolicy
from statistic.tasks import st_widget_view_statistic_update
from teams.models import Task, Workflow
from teams.moderation_const import UNMODERATED, WAITING_MODERATION
from teams.permissions import (
    can_create_and_edit_subtitles, can_create_and_edit_translations,
    can_publish_edits_immediately, can_review, can_approve, can_assign_task
)
from teams.signals import (
    api_subtitles_edited, api_subtitles_approved, api_subtitles_rejected,
    api_language_new, api_language_edited, api_video_edited
)
from uslogging.models import WidgetDialogLog
from utils import send_templated_email
from utils.forms import flatten_errorlists
from utils.translation import get_user_languages_from_request
from videos import models
from videos.tasks import video_changed_tasks
from widget import video_cache
from widget.base_rpc import BaseRpc
from widget.forms import  FinishReviewForm, FinishApproveForm
from widget.models import SubtitlingSession


yt_logger = logging.getLogger("youtube-ei-error")

ALL_LANGUAGES = settings.ALL_LANGUAGES
LANGUAGES_MAP = dict(ALL_LANGUAGES)

def add_general_settings(request, dict):
    dict.update({
            'writelock_expiration' : models.WRITELOCK_EXPIRATION,
            'embed_version': settings.EMBED_JS_VERSION,
            'languages': ALL_LANGUAGES,
            'metadata_languages': settings.METADATA_LANGUAGES
            })
    if request.user.is_authenticated():
        dict['username'] = request.user.username

class Rpc(BaseRpc):
    # Logging
    def log_session(self, request,  log):
        dialog_log = WidgetDialogLog(
            browser_id=request.browser_id,
            log=log)
        dialog_log.save()
        send_templated_email(
            settings.WIDGET_LOG_EMAIL,
            'Subtitle save failure',
            'widget/session_log_email.txt',
            { 'log_pk': dialog_log.pk },
            fail_silently=False)
        return { 'response': 'ok' }

    def log_youtube_ei_failure(self, request, page_url):
        user_agent = request.META.get('HTTP_USER_AGENT', '(Unknown)')
        yt_logger.error(
            "Youtube ExternalInterface load failure",
            extra={
                'request': request,
                'data': {
                    'user_agent': user_agent,
                    'page_url': page_url }
                })
        return { 'response': 'ok' }


    # Widget
    def _check_visibility_policy_for_widget(self, request, video_id):
        """Return an error if the user cannot see the widget, None otherwise."""

        visibility_policy = video_cache.get_visibility_policies(video_id)

        if visibility_policy.get('widget', None) != VideoVisibilityPolicy.WIDGET_VISIBILITY_PUBLIC:
            can_show = VideoVisibilityPolicy.objects.can_show_widget(
                video_id, referer=request.META.get('referer'), user=request.user)

            if not can_show:
                return {"error_msg": _("Video embedding disabled by owner")}

    def _get_video_urls_for_widget(self, video_url, video_id):
        """Return the video URLs, 'cleaned' video id, and error."""

        try:
            video_urls = video_cache.get_video_urls(video_id)
        except models.Video.DoesNotExist:
            video_cache.invalidate_video_id(video_url)

            try:
                video_id = video_cache.get_video_id(video_url)
            except Exception as e:
                return None, None, {"error_msg": unicode(e)}

            video_urls = video_cache.get_video_urls(video_id)

        return video_urls, video_id, None

    def _find_remote_autoplay_language(self, request):
        language = None
        if not request.user.is_authenticated() or request.user.preferred_language == '':
            language = translation.get_language_from_request(request)
        else:
            language = request.user.preferred_language
        return language if language != '' else None

    def _get_subtitles_for_widget(self, request, base_state, video_id, is_remote):
        # keeping both forms valid as backwards compatibility layer
        lang_code = base_state and base_state.get("language_code", base_state.get("language", None))

        if base_state is not None and lang_code is not None:
            lang_pk = base_state.get('language_pk', None)

            if lang_pk is  None:
                lang_pk = video_cache.pk_for_default_language(video_id, lang_code)

            return self._autoplay_subtitles(request.user, video_id, lang_pk,
                                            base_state.get('revision', None))
        else:
            if is_remote:
                autoplay_language = self._find_remote_autoplay_language(request)
                language_pk = video_cache.pk_for_default_language(video_id, autoplay_language)

                if autoplay_language is not None:
                    return self._autoplay_subtitles(request.user, video_id,
                                                    language_pk, None)

    def show_widget(self, request, video_url, is_remote, base_state=None, additional_video_urls=None):
        try:
            video_id = video_cache.get_video_id(video_url)
        except Exception as e:
            # for example, private youtube video or private widgets
            return {"error_msg": unicode(e)}

        if video_id is None:
            return None

        error = self._check_visibility_policy_for_widget(request, video_id)
        if error:
            return error

        video_urls, video_id, error = self._get_video_urls_for_widget(video_url, video_id)
        if error:
            return error

        resp = {
            'video_id' : video_id,
            'subtitles': None,
            'video_urls': video_urls,
            'is_moderated': video_cache.get_is_moderated(video_id),
        }
        if additional_video_urls is not None:
            for url in additional_video_urls:
                video_cache.associate_extra_url(url, video_id)

        add_general_settings(request, resp)

        if request.user.is_authenticated():
            resp['username'] = request.user.username

        resp['drop_down_contents'] = video_cache.get_video_languages(video_id)
        resp['my_languages'] = get_user_languages_from_request(request)
        resp['subtitles'] = self._get_subtitles_for_widget(request, base_state,
                                                           video_id, is_remote)
        return resp


    # Statistics
    def track_subtitle_play(self, request, video_id):
        st_widget_view_statistic_update.delay(video_id=video_id)
        return { 'response': 'ok' }


    # Start Dialog (aka "Subtitle Into" Dialog)
    def fetch_start_dialog_contents(self, request, video_id):
        my_languages = get_user_languages_from_request(request)
        my_languages.extend([l[:l.find('-')] for l in my_languages if l.find('-') > -1])
        video = models.Video.objects.get(video_id=video_id)
        team_video = video.get_team_video()
        video_languages = [language_summary(l, team_video, request.user) for l
                           in video.subtitlelanguage_set.all()]

        original_language = None
        if video.subtitle_language():
            original_language = video.subtitle_language().language

        tv = video.get_team_video()
        writable_langs = list(tv.team.get_writable_langs()) if tv else []

        return {
            'my_languages': my_languages,
            'video_languages': video_languages,
            'original_language': original_language,
            'limit_languages': writable_langs,
            'is_moderated': video.is_moderated, }


    # Fetch Video ID and Settings
    def fetch_video_id_and_settings(self, request, video_id):
        is_original_language_subtitled = self._subtitle_count(video_id) > 0
        general_settings = {}
        add_general_settings(request, general_settings)
        return {
            'video_id': video_id,
            'is_original_language_subtitled': is_original_language_subtitled,
            'general_settings': general_settings }


    # Start Editing
    def _check_team_video_locking(self, user, video_id, language_code, is_translation, mode, is_edit):
        """Check whether the a team prevents the user from editing the subs.

        Returns a dict appropriate for sending back if the user should be
        prevented from editing them, or None if the user can safely edit.

        """
        video = models.Video.objects.get(video_id=video_id)
        team_video = video.get_team_video()

        if not team_video:
            # If there's no team video to worry about, just bail early.
            return None

        if team_video.team.is_visible:
            message = _(u"These subtitles are moderated. See the %s team page for information on how to contribute." % str(team_video.team))
        else:
            message = _(u"Sorry, these subtitles are privately moderated.")

        # Check that there are no open tasks for this action.
        tasks = team_video.task_set.incomplete().filter(language__in=[language_code, ''])

        if tasks:
            task = tasks[0]
            # can_assign verify if the user has permission to either
            # 1. assign the task to himself
            # 2. do the task himself (the task is assigned to him)
            if not user.is_authenticated() or (task.assignee and task.assignee != user) or (not task.assignee and not can_assign_task(task, user)):
                    return { "can_edit": False, "locked_by": str(task.assignee or task.team), "message": message }

        # Check that the team's policies don't prevent the action.
        if not is_edit and mode not in ['review', 'approve']:
            if is_translation:
                can_edit = can_create_and_edit_translations(user, team_video, language_code)
            else:
                can_edit = can_create_and_edit_subtitles(user, team_video, language_code)

            if not can_edit:
                return { "can_edit": False, "locked_by": str(team_video.team), "message": message }

    def _get_version_to_edit(self, language, session):
        """Return a version (and other info) that should be edited.

        When subtitles are going to be created or edited for a given language,
        we need to have a "base" version to work with.  This function returns
        this base version along with its number and a flag specifying whether it
        is an edit (as opposed to a brand new set of subtitles).

        """
        version_for_subs = language.version(public_only=False)

        if not version_for_subs:
            version_for_subs = self._create_version_from_session(session)
            version_no = 0
        else:
            version_no = version_for_subs.version_no + 1

        return version_for_subs, version_no

    def _get_base_language(self, language_code, original_language_code, base_language_pk):
        """Return the subtitle language to use as a base (and its pk), if any."""
        if language_code == original_language_code:
            base_language_pk = None

        if base_language_pk is not None:
            base_language = models.SubtitleLanguage.objects.get(pk=base_language_pk)
        else:
            base_language = None

        return base_language, base_language_pk

    def start_editing(self, request, video_id, language_code,
                      subtitle_language_pk=None, base_language_pk=None,
                      original_language_code=None, mode=None):
        """Called by subtitling widget when subtitling or translation is to commence on a video.

        Does a lot of things, some of which should probably be split out into
        other functions.

        """
        # TODO: remove whenever blank SubtitleLanguages become illegal.
        self._fix_blank_original(video_id)

        # Find the subtitle language to use as a base for these edits, if any.
        base_language, base_language_pk = self._get_base_language(
            language_code, original_language_code, base_language_pk)

        # Find the subtitle language we'll be editing (if available).
        language, locked = self._get_language_for_editing(
            request, video_id, language_code, subtitle_language_pk, base_language)

        if locked:
            return locked

        # Ensure that the user is not blocked from editing this video by team
        # permissions.
        locked = self._check_team_video_locking(
            request.user, video_id, language_code, bool(base_language_pk), 
            mode, bool(language.version(public_only=False)))

        if locked:
            return locked

        # just lock the video *after* we verify if team moderation happened
        language.writelock(request)
        language.save()

        # Create the subtitling session and subtitle version for these edits.
        session = self._make_subtitling_session(request, language, base_language)
        version_for_subs, version_no = self._get_version_to_edit(language, session)

        subtitles = self._subtitles_dict(
            version_for_subs, version_no, base_language_pk is None)
        return_dict = { "can_edit": True,
                        "session_pk": session.pk,
                        "subtitles": subtitles }

        # If this is a translation, include the subtitles it's based on in the response.
        if base_language:
            original_subtitles = self._subtitles_dict(base_language.latest_version())
            return_dict['original_subtitles'] = original_subtitles

        # If we know the original language code for this video, make sure it's
        # saved and there's a SubtitleLanguage for it in the database.
        #
        # Remember: the "original language" is the language of the video, NOT
        # the language these subs are a translation of (if any).
        if original_language_code:
            self._save_original_language(video_id, original_language_code)

        # Writelock this language for this video before we successfully return.
        video_cache.writelock_add_lang(video_id, language.language)

        return return_dict


    # Resume Editing
    def resume_editing(self, request, session_pk):
        session = SubtitlingSession.objects.get(pk=session_pk)
        if session.language.can_writelock(request) and \
                session.parent_version == session.language.version():
            session.language.writelock(request)
            # FIXME: Duplication between this and start_editing.
            version_for_subs = session.language.version()
            if not version_for_subs:
                version_for_subs = self._create_version_from_session(session)
                version_no = 0
            else:
                version_no = version_for_subs.version_no + 1
            subtitles = self._subtitles_dict(version_for_subs, version_no)
            return_dict = { "response": "ok",
                            "can_edit" : True,
                            "session_pk" : session.pk,
                            "subtitles" : subtitles }
            if session.base_language:
                return_dict['original_subtitles'] = \
                    self._subtitles_dict(session.base_language.latest_version())
            return return_dict
        else:
            return { 'response': 'cannot_resume' }


    # Locking
    def release_lock(self, request, session_pk):
        language = SubtitlingSession.objects.get(pk=session_pk).language
        if language.can_writelock(request):
            language.release_writelock()
            language.save()
            video_cache.writelocked_langs_clear(language.video.video_id)
        return { "response": "ok" }

    def regain_lock(self, request, session_pk):
        language = SubtitlingSession.objects.get(pk=session_pk).language
        if not language.can_writelock(request):
            return { 'response': 'unlockable' }
        else:
            language.writelock(request)
            language.save()
            video_cache.writelock_add_lang(
                language.video.video_id, language.language)
            return { 'response': 'ok' }


    # Permissions
    def can_user_edit_video(self, request, video_id):
        """Return a dictionary of information about what the user can do with this video.

        The response will contain can_subtitle and can_translate attributes.

        """
        video = models.Video.objects.get(video_id=video_id)
        team_video = video.get_team_video()

        if not team_video:
            can_subtitle = True
            can_translate = True
        else:
            can_subtitle = can_create_and_edit_subtitles(request.user, team_video)
            can_translate = can_create_and_edit_translations(request.user, team_video)

        return { 'response': 'ok',
                 'can_subtitle': can_subtitle,
                 'can_translate': can_translate, }


    # Finishing and Saving
    def _get_user_message_for_save(self, user, language, is_complete):
        """Return the message that should be sent to the user regarding this save.

        This may be a message saying that the save was successful, or an error message.

        The message displayed to the user  has a complex requirement / outcomes
        1) Subs will go live in a moment. Works for unmoderated subs and for D and H
        D. Transcript, post-publish edit by moderator with the power to approve. Will go live immediately.
        H. Translation, post-publish edit by moderator with the power to approve. Will go live immediately.
        2) Subs must be completed before being submitted to moderators. Works for A and E
        A. Transcript, incomplete (checkbox not ticked). Must be completed before being submitted to moderators.
        E. Translation, incomplete (some lines missing). Must be completed before being submitted to moderators.
        3) Subs will be submitted for review/approval. Works for B, C, F, and G
        B. Transcript, complete (checkbox ticked). Will be submitted to moderators promptly for approval or rejection.
        C. Transcript, post-publish edit by contributor. Will be submitted to moderators promptly for approval or rejection.
        F. Translation, complete (all the lines filled). Will be submitted to moderators promptly for approval or rejection.
        G. Translation, post-publish edit by contributor. Will be submitted to moderators promptly for approval or rejection.

        TODO: Localize this?

        """
        message_will_be_live_soon = "Your changes have been saved. It may take a moment for your subtitles to appear."
        message_will_be_submited = ("This video is moderated by %s."
                                    "Your changes will be reviewed by the "
                                    "team's moderators.")
        message_incomplete = ("These subtitles are incomplete. "
                              "They will not be submitted for publishing "
                              "until they've been completed.")

        under_moderation = language.video.is_moderated

        _user_can_publish =  True
        team_video = language.video.get_team_video()
        if under_moderation and team_video:
            # videos are only supposed to have one team video
            _user_can_publish = can_publish_edits_immediately(team_video, user, language.language)

        # this is case 1
        if under_moderation and not _user_can_publish:
            if is_complete:
                # case 3
                return message_will_be_submited % language.video.moderated_by.name
            else:
                # case 2
                return message_incomplete
        else:
            return message_will_be_live_soon

    def _save_tasks_for_save(self, request, save_for_later, language,
                             new_version, is_complete, task_id, task_type,
                             task_notes, task_approved):
        """Handle any outstanding tasks for this save.  May return an error.

        save_for_later is the most important argument here.  It determines
        whether any tasks will actually be completed.

        """

        if not save_for_later:
            # If we've just saved a completed subtitle language, we may need to
            # complete a subtitle or translation task.
            if is_complete:
                team_video = language.video.get_team_video()
                if team_video:
                    tasks = team_video.task_set.incomplete().filter(
                        type__in=(Task.TYPE_IDS['Subtitle'],
                                Task.TYPE_IDS['Translate']),
                        language=language.language
                    )
                    for task in tasks:
                        task.complete()

        # If the user is specifically performing a review/approve task we should
        # handle it.
        if task_id:
            if task_type == 'review':
                handle = self._save_review
            elif task_type == 'approve':
                handle = self._save_approve

            error = handle(request, save_for_later, task_id, task_notes,
                           task_approved, new_version=new_version)
            if error:
                return error

    def _save_subtitles(self, subtitle_set, json_subs, forked):
        """Create Subtitle objects into the given queryset from the JSON subtitles."""

        for s in json_subs:
            if not forked:
                subtitle_set.create(
                    subtitle_id=s['subtitle_id'],
                    subtitle_text=s['text'])
            else:
                subtitle_set.create(
                    subtitle_id=s['subtitle_id'],
                    subtitle_text=s['text'],
                    start_time=s['start_time'],
                    end_time=s['end_time'],
                    subtitle_order=s['sub_order'],
                    start_of_paragraph=s.get('start_of_paragraph', False))

    def _copy_subtitles(self, source_version, dest_version):
        """Copy the Subtitle objects from one version to another, unchanged.

        Used when the title or description of some subs is changed but the
        actual subtitles remain the same.

        """
        for s in source_version.subtitle_set.all():
            s.duplicate_for(dest_version).save()

    def _get_new_version_for_save(self, subtitles, language, session, user, forked, new_title, new_description):
        """Return a new subtitle version for this save, or None if not needed."""

        new_version = None
        previous_version = language.latest_version(public_only=False)

        title_changed = (previous_version
                         and new_title is not None
                         and new_title != previous_version.title)
        desc_changed = (previous_version
                        and new_description is not None
                        and new_description != previous_version.description)
        subtitles_changed = (
            subtitles is not None
            and (len(subtitles) > 0 or previous_version is not None)
        )

        should_create_new_version = (
            subtitles_changed or title_changed or desc_changed)

        if should_create_new_version:
            new_version = self._create_version_from_session(
                session, user, forked, new_title, new_description)

            new_version.save()

            if subtitles_changed:
                self._save_subtitles(
                    new_version.subtitle_set, subtitles, new_version.is_forked)
            else:
                self._copy_subtitles(previous_version, new_version)

            # this is really really hackish.
            # TODO: clean all this mess on a friday
            if not new_version.language.is_complete_and_synced(public_only=False):
                self._moderate_incomplete_version(new_version, user)
            elif hasattr(new_version, 'task_to_save'):
                task = new_version.task_to_save
                task.subtitle_version = new_version
                if task.get_type_display() in ['Review', 'Approve']:
                    task.review_base_version = new_version

                task.save()

        return new_version

    def _update_language_attributes_for_save(self, language, completed):
        """Update the attributes of the language as necessary and save it.

        Will also send the appropriate API notification if needed.

        """
        must_trigger_api_language_edited = False

        if completed is not None:
            if language.is_complete != completed:
                must_trigger_api_language_edited = True
            language.is_complete = completed

        language.save()

        if must_trigger_api_language_edited:
            language.video.save()
            api_language_edited.send(language)

    def save_finished(self, request, user, session, subtitles, new_title=None,
                      completed=None, forked=False, new_description=None,
                      task_id=None, task_notes=None, task_approved=None,
                      task_type=None, save_for_later=None):
        # TODO: lock all this in a transaction please!

        language = session.language

        new_version = self._get_new_version_for_save(
            subtitles, language, session, user, forked, new_title,
            new_description)

        language.release_writelock()

        self._update_language_attributes_for_save(language, completed)

        if new_version:
            video_changed_tasks.delay(language.video.id, new_version.id)
            api_subtitles_edited.send(new_version)
        else:
            video_changed_tasks.delay(language.video.id)
            api_video_edited.send(language.video)

        is_complete = language.is_complete or language.calculate_percent_done() == 100
        user_message = self._get_user_message_for_save(user, language, is_complete)

        error = self._save_tasks_for_save(
                request, save_for_later, language, new_version, is_complete,
                task_id, task_type, task_notes, task_approved)
        if error:
            return error

        return { 'response': 'ok', 'user_message': user_message }

    def finished_subtitles(self, request, session_pk, subtitles=None,
                           new_title=None, completed=None, forked=False,
                           throw_exception=False, new_description=None,
                           task_id=None, task_notes=None, task_approved=None,
                           task_type=None, save_for_later=None):
        """Called when a user has finished a set of subtitles and they should be saved.

        TODO: Rename this to something verby, like "finish_subtitles".

        """
        session = SubtitlingSession.objects.get(pk=session_pk)

        if not request.user.is_authenticated():
            return { 'response': 'not_logged_in' }
        if not session.language.can_writelock(request):
            return { "response" : "unlockable" }
        if not session.matches_request(request):
            return { "response" : "does not match request" }

        if throw_exception:
            raise Exception('purposeful exception for testing')

        return self.save_finished(
            request, request.user, session, subtitles, new_title, completed,
            forked, new_description, task_id, task_notes, task_approved,
            task_type, save_for_later)


    def _get_review_or_approve_task(self, team_video, subtitle_language):
        lang = subtitle_language.language
        workflow = Workflow.get_for_team_video(team_video)

        if workflow.review_allowed:
            type = Task.TYPE_IDS['Review']
            can_do = can_review
        elif workflow.approve_allowed:
            type = Task.TYPE_IDS['Approve']
            can_do = can_approve
        else:
            return None

        # TODO: Dedupe this and Task._find_previous_assignee

        # Find the assignee.
        #
        # For now, we'll assign the review/approval task to whomever did
        # it last time (if it was indeed done), but only if they're
        # still eligible to perform it now.
        last_task = team_video.task_set.complete().filter(
            language=lang, type=type
        ).order_by('-completed')[:1]

        assignee = None
        if last_task:
            candidate = last_task[0].assignee
            if candidate and can_do(team_video, candidate, lang):
                assignee = candidate

        # This is just terrible.
        #
        # We have to create a task here, but we need to have the
        # subtitle_version to do it correctly, and that doesn't get
        # saved until much later, a few functions away.
        return Task(team=team_video.team, team_video=team_video,
                    assignee=assignee, language=lang, type=type)

    def _moderate_incomplete_version(self, subtitle_version, user):
        """ Verifies if it's possible to create a transcribe/translate task (if there's
        no other transcribe/translate task) and tries to assign to user. 
        Also, if the video belongs to a team, change its status.
        """

        team_video = subtitle_version.video.get_team_video()

        if not team_video:
            return

        language = subtitle_version.language.language
        transcribe_task = team_video.task_set.incomplete_subtitle_or_translate()\
                                     .filter(language=language)

        if transcribe_task.exists():
            task = transcribe_task[0]
            return

        subtitle_version.moderation_status = WAITING_MODERATION
        subtitle_version.save()

        task = Task(team=team_video.team, team_video=team_video,
                    language=language, type=Task.TYPE_IDS['Subtitle'])

        if can_create_and_edit_subtitles(user, team_video):
            task.assignee = user

        task.save()

    def _moderate_session(self, session, user):
        """Return the right moderation_status for a version based on the given session.

        Also may possibly return a Task object that needs to be saved once the
        subtitle_version is ready.

        Also perform any ancillary tasks that are appropriate, assuming the
        version actually gets created later.

        Also :(

        """
        sl = session.language
        team_video = sl.video.get_team_video()

        if not team_video:
            return UNMODERATED, None

        # If there are any open team tasks for this video/language, it needs to
        # be kept under moderation.
        tasks = team_video.task_set.incomplete().filter(
                Q(language=sl.language)
              | Q(type=Task.TYPE_IDS['Subtitle'])
        )
        if tasks:
            for task in tasks:
                if task.type == Task.TYPE_IDS['Subtitle']:
                    if not task.language:
                        task.language = sl.language
                        task.save()
            return WAITING_MODERATION, None

        if sl.has_version:
            # If there are already active subtitles for this language, we're
            # dealing with an edit.
            if not can_publish_edits_immediately(team_video, user, sl.language):
                task = self._get_review_or_approve_task(team_video, sl)
                if task:
                    task.set_expiration()
                    return WAITING_MODERATION, task
        else:
            # Otherwise we're dealing with a new set of subtitles for this
            # language.
            task = self._get_review_or_approve_task(team_video, sl)
            if task:
                return WAITING_MODERATION, task

        return UNMODERATED, None

    def _create_version_from_session(self, session, user=None, forked=False, new_title=None, new_description=None):
        latest_version = session.language.version(public_only=False)
        forked_from = (forked and latest_version) or None

        moderation_status, task = self._moderate_session(session, user)

        kwargs = dict(language=session.language,
                      version_no=(0 if latest_version is None
                                  else latest_version.version_no + 1),
                      is_forked=(session.base_language is
                                 None or forked == True),
                      forked_from=forked_from,
                      datetime_started=session.datetime_started,
                      moderation_status=moderation_status)

        if user is not None:
            kwargs['user'] = user

        if new_title is not None:
            kwargs['title'] = new_title
        elif latest_version:
            kwargs['title'] = latest_version.title
        else:
            kwargs['title'] = session.language.video.title

        if new_description is not None:
            kwargs['description'] = new_description
        elif latest_version:
            kwargs['description'] = latest_version.description
        else:
            kwargs['description'] = session.language.video.description

        version = models.SubtitleVersion(**kwargs)

        if task:
            # We may have a task that needs to be saved *after* this version is
            # saved.
            version.task_to_save = task

        return version

    def fetch_subtitles(self, request, video_id, language_pk):
        cache = video_cache.get_subtitles_dict(
            video_id, language_pk, None,
            lambda version: self._subtitles_dict(version))
        return cache

    def get_widget_info(self, request):
        return {
            'all_videos': models.Video.objects.count(),
            'subtitles_fetched_count': models.Video.objects.aggregate(s=Sum('subtitles_fetched_count'))['s'],
            'videos_with_captions': models.Video.objects.exclude(subtitlelanguage=None).count(),
            'translations_count': models.SubtitleLanguage.objects.filter(is_original=False).count()
        }

    def _make_subtitling_session(self, request, language, base_language):
        session = SubtitlingSession(
            language=language,
            base_language=base_language,
            parent_version=language.version(),
            browser_id=request.browser_id)
        if request.user.is_authenticated():
            session.user = request.user
        session.save()
        return session


    # Review
    def fetch_review_data(self, request, task_id):
        task = Task.objects.get(pk=task_id)
        return {'response': 'ok', 'body': task.body}

    def _save_review(self, request, save_for_later, task_id=None, body=None,
                     approved=None, new_version=None):
        """
        If the task performer has edited this version, then we need to
        set the task's version to the new one that he has edited.
        """
        data = {'task': task_id, 'body': body, 'approved': approved}

        form = FinishReviewForm(request, data)

        if form.is_valid():
            task = form.cleaned_data['task']
            task.body = form.cleaned_data['body']
            task.approved = form.cleaned_data['approved']

            # If there is a new version, update the task's version.
            if new_version:
                task.subtitle_version = new_version

            task.save()

            if not save_for_later:
                if task.approved in Task.APPROVED_FINISHED_IDS:
                    task.complete()

            task.subtitle_version.language.release_writelock()
            task.subtitle_version.language.followers.add(request.user)

            video_changed_tasks.delay(task.team_video.video_id)
        else:
            return {'error_msg': _(u'\n'.join(flatten_errorlists(form.errors)))}


    # Approval
    def fetch_approve_data(self, request, task_id):
        task = Task.objects.get(pk=task_id)
        return {'response': 'ok', 'body': task.body}

    def _save_approve(self, request, save_for_later, task_id=None, body=None,
                      approved=None, new_version=None):
        """
        If the task performer has edited this version, then we need to
        set the task's version to the new one that he has edited.
        """
        data = {'task': task_id, 'body': body, 'approved': approved}

        form = FinishApproveForm(request, data)

        if form.is_valid():
            task = form.cleaned_data['task']
            task.body = form.cleaned_data['body']
            task.approved = form.cleaned_data['approved']

            # If there is a new version, update the task's version.
            if new_version:
                task.subtitle_version = new_version
            task.save()

            if not save_for_later:
                if task.approved in Task.APPROVED_FINISHED_IDS:
                    task.complete()

            task.subtitle_version.language.release_writelock()

            if form.cleaned_data['approved'] == Task.APPROVED_IDS['Approved']:
                api_subtitles_approved.send(task.subtitle_version)
            elif form.cleaned_data['approved'] == Task.APPROVED_IDS['Rejected']:
                api_subtitles_rejected.send(task.subtitle_version)

            video_changed_tasks.delay(task.team_video.video_id)
        else:
            return {'error_msg': _(u'\n'.join(flatten_errorlists(form.errors)))}


    def _find_base_language(self, base_language):
        if base_language:
            video = base_language.video
            if base_language.is_original or base_language.is_forked:
                return base_language
            else:
                if base_language.standard_language:
                    return base_language.standard_language
                else:
                    return video.subtitle_language()
        else:
            return None

    def _needs_new_sub_language(self, language, base_language):
        if language.standard_language and not base_language:
            # forking existing
            return False
        elif language.is_forked and base_language:
            return True
        else:
            return language.standard_language != base_language

    def _get_language_for_editing(self, request, video_id, language_code,
                                  subtitle_language_pk=None, base_language=None):
        """Return the subtitle language to edit or a lock response."""

        video = models.Video.objects.get(video_id=video_id)

        editable = False
        create_new = False

        if subtitle_language_pk is not None:
            language = models.SubtitleLanguage.objects.get(pk=subtitle_language_pk)
            if self._needs_new_sub_language(language, base_language):
                create_new = True
            else:
                editable = language.can_writelock(request)
        else:
            create_new = True

        if create_new:
            standard_language = self._find_base_language(base_language)
            forked = standard_language is None
            language, created = models.SubtitleLanguage.objects.get_or_create(
                video=video,
                language=language_code,
                standard_language=standard_language,
                defaults={
                    'created': datetime.now(),
                    'is_forked': forked,
                    'writelock_session_key': '' })
            editable = created or language.can_writelock(request)

        if editable:
            if create_new:
                api_language_new.send(language)

            return language, None
        else:
            return None, { "can_edit": False,
                           "locked_by": language.writelock_owner_name }

    def _fix_blank_original(self, video_id):
        # TODO: remove this method as soon as blank SubtitleLanguages
        # become illegal
        video = models.Video.objects.get(video_id=video_id)
        originals = video.subtitlelanguage_set.filter(is_original=True, language='')
        to_delete = []
        if len(originals) > 0:
            for original in originals:
                if not original.latest_version():
                    # result of weird practice of saving SL with is_original=True
                    # and blank language code on Video creation.
                    to_delete.append(original)
                else:
                    # decided to mark authentic blank originals as English.
                    original.language = 'en'
                    original.save()
        for sl in to_delete:
            sl.delete()

    def _save_original_language(self, video_id, language_code):
        video = models.Video.objects.get(video_id=video_id)
        has_original = False
        for sl in video.subtitlelanguage_set.all():
            if sl.is_original and sl.language != language_code:
                sl.is_original = False
                sl.save()
            elif not sl.is_original and sl.language == language_code:
                sl.is_original = True
                sl.save()
            if sl.is_original:
                has_original = True
        if not has_original:
            sl = models.SubtitleLanguage(
                video=video,
                language=language_code,
                is_forked=True,
                is_original=True,
                writelock_session_key='')
            sl.save()

    def _autoplay_subtitles(self, user, video_id, language_pk, version_no):
        cache =  video_cache.get_subtitles_dict(
            video_id, language_pk, version_no,
            lambda version: self._subtitles_dict(version))
        if cache and cache.get("language", None) is not None:
            cache['language_code'] = cache['language'].language
            cache['language_pk'] = cache['language'].pk
        return cache

    def _subtitles_dict(self, version, forced_version_no=None, force_forked=False):
        language = version.language
        base_language = None
        if language.is_dependent() and not version.is_forked and not force_forked:
            base_language = language.standard_language
        version_no = version.version_no if forced_version_no is None else forced_version_no
        is_latest = False
        latest_version = language.latest_version()
        if latest_version is None or version_no >= latest_version.version_no:
            is_latest = True
        return self._make_subtitles_dict(
            [s.__dict__ for s in version.subtitles()],
            language.language,
            language.pk,
            language.is_original,
            None if base_language is not None else language.is_complete,
            version_no,
            is_latest,
            version.is_forked or force_forked,
            base_language,
            language.get_title(public_only=False),
            language.get_description(public_only=False),
            language.is_rtl()
        )


def language_summary(language, team_video=-1, user=None):
    """Return a dictionary of info about the given SubtitleLanguage.

    The team video can be given to avoid an extra database lookup.

    """
    if team_video == -1:
        team_video = language.video.get_team_video()

    summary = {
        'pk': language.pk,
        'language': language.language,
        'dependent': language.is_dependent(),
        'subtitle_count': language.subtitle_count,
        'in_progress': language.is_writelocked,
        'disabled_from': False,
        'disabled_to': False }

    if team_video:
        tasks = team_video.task_set.incomplete().filter(language=language.language)
        if tasks:
            task = tasks[0]
            if user and user != task.assignee:
                summary['disabled_to'] = True

    if not language.latest_version():
        summary['disabled_from'] = True

    if language.is_dependent():
        summary['percent_done'] = language.percent_done
        if language.standard_language:
            summary['standard_pk'] = language.standard_language.pk
    else:
        summary['is_complete'] = language.is_complete

    return summary
