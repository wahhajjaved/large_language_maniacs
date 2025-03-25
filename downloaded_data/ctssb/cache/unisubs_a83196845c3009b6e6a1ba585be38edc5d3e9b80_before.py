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

import chardet
from itertools import izip

import babelsubs
from django import forms
from django.utils.encoding import force_unicode
from django.utils.translation import ugettext_lazy as _

from apps.subtitles import pipeline
from apps.subtitles.shims import is_dependent
from apps.subtitles.models import ORIGIN_UPLOAD, SubtitleLanguage
from apps.teams.models import Task
from apps.teams.permissions import (
    can_perform_task, can_create_and_edit_subtitles,
    can_create_and_edit_translations
)
from apps.videos.tasks import video_changed_tasks
from utils.translation import get_language_choices, get_language_label


SUBTITLE_FILESIZE_LIMIT_KB = 512
SUBTITLE_FILE_FORMATS = babelsubs.get_available_formats()


class SubtitlesUploadForm(forms.Form):
    draft = forms.FileField(required=True)
    complete = forms.BooleanField(initial=False, required=False)

    language_code = forms.ChoiceField(required=True,
                                      choices=())
    primary_audio_language_code = forms.ChoiceField(required=False,
                                                    choices=())
    from_language_code = forms.ChoiceField(required=False,
                                           choices=(),
                                           initial='')

    def __init__(self, user, video, allow_transcription=True, *args, **kwargs):
        self.video = video
        self.user = user
        self._sl_created = False

        super(SubtitlesUploadForm, self).__init__(*args, **kwargs)

        # This has to be set here.  get_language_choices looks at the language
        # of the current thread via the magical get_language() Django function,
        # so if you just set it once at the beginning of the file it's not going
        # to properly change for the user's UI language.
        all_languages = get_language_choices(with_empty=True)
        self.fields['language_code'].choices = all_languages
        self.fields['primary_audio_language_code'].choices = all_languages

        language_qs = (SubtitleLanguage.objects.having_public_versions()
                       .filter(video=video))
        choices = [
            (sl.language_code, sl.get_language_code_display())
            for sl in language_qs
        ]
        if allow_transcription:
            choices.append(('', 'None (Direct from Video)'))

        self.fields['from_language_code'].choices = choices


    # Validation for various restrictions on subtitle uploads.
    def _verify_not_writelocked(self, subtitle_language):
        writelocked = (subtitle_language.is_writelocked and
                       subtitle_language.writelock_owner != self.user)
        if writelocked:
            raise forms.ValidationError(_(
                u"Sorry, we can't upload your subtitles because work on "
                u"this language is already in progress."))

    def _verify_no_translation_conflict(self, subtitle_language,
                                        from_language_code):
        existing_from_language = subtitle_language.get_translation_source_language()
        existing_from_language_code = (
            existing_from_language and existing_from_language.language_code) or ''

        # If the user said this is a translation, but the language already
        # exists and *isn't* a translation, fail.
        if from_language_code:
            language_is_not_a_translation = (not existing_from_language_code)
            if language_is_not_a_translation and subtitle_language.get_tip():
                raise forms.ValidationError(_(
                    u"The language already exists and is not a translation."))
            # If it's marked as a translation from a different language, don't
            # allow that until our UI can handle showing different reference
            # languages
            elif existing_from_language_code and existing_from_language_code != from_language_code:
                raise forms.ValidationError(_(
                    u"The language already exists as a translation from %s." % existing_from_language.get_language_code_display()))

    def _verify_no_blocking_subtitle_translate_tasks(self, team_video,
                                                     language_code):
        tasks = list(
            team_video.task_set.incomplete_subtitle_or_translate().filter(
                language__in=[language_code, '']
            )
        )[:1]

        if tasks:
            task = tasks[0]

            # If this language is already assigned to someone else, fail.
            if (task.assignee and task.assignee != self.user):
                raise forms.ValidationError(_(
                    u"Sorry, we can't upload your subtitles because another "
                    u"user is already assigned to this language."))

            # If this language is unassigned, and the user can't assign herself
            # to it, fail.
            if (not task.assignee and not can_perform_task(self.user, task)):
                raise forms.ValidationError(_(
                    u"Sorry, we can't upload your subtitles because you do not "
                    u"have permission to claim this language."))

    def _verify_no_blocking_review_approve_tasks(self, team_video,
                                                 language_code):
        tasks = team_video.task_set.incomplete_review_or_approve().filter(
            language=language_code
        ).exclude(assignee=self.user).exclude(assignee__isnull=True)

        if tasks.exists():
            raise forms.ValidationError(_(
                u"Sorry, we can't upload your subtitles because a draft for "
                u"this language is already in moderation."))

    def _verify_team_policies(self, team_video, language_code,
                              from_language_code):
        # if this is being saved as part of a task, than permissions mean
        # something else. For example a team might require admins to transcribe
        # but if it allows managers to review, then saves done as part of a review
        # task can be done by a manager (nice huh?)
        possible_task_languages = [language_code, '']
        try:
            # If a task exist, we should let permissions be checked by _verify_no_blocking_review...
            # so don't bother with assignment
            team_video.task_set.incomplete_review_or_approve().filter(language__in=possible_task_languages).exists()
            return
        except Task.DoesNotExist:
            pass

        is_transcription = (not from_language_code)
        if is_transcription:
            allowed = can_create_and_edit_subtitles(self.user, team_video,
                                                    language_code)
            if not allowed:
                raise forms.ValidationError(_(
                    u"Sorry, we can't upload your subtitles because this "
                    u"language is moderated and you don't have permission to "
                    u"transcribe subtitles."))
        else:
            allowed = can_create_and_edit_translations(self.user, team_video,
                                                       language_code)
            if not allowed:
                raise forms.ValidationError(_(
                    u"Sorry, we can't upload your subtitles because this "
                    u"language is moderated and you don't have permission to "
                    u"translate subtitles."))

    def _verify_translation_subtitle_counts(self, from_language_code):
        if from_language_code:
            from_count = len(self.from_sv.get_subtitles())
            current_count = len(self._parsed_subtitles.get_subtitles())

            if current_count > from_count:
                raise forms.ValidationError(_(
                    u"Sorry, we couldn't upload your file because the number "
                    u"of lines in your translation ({0}) doesn't match the "
                    u"original ({1})."
                    .format(current_count, from_count)
                ))

    def clean_draft(self):
        data = self.cleaned_data['draft']

        if data.size > SUBTITLE_FILESIZE_LIMIT_KB * 1024:
            raise forms.ValidationError(_(
                u'File size must be less than %d kb.'
                % SUBTITLE_FILESIZE_LIMIT_KB))

        parts = data.name.rsplit('.', 1)
        self.extension = parts[-1].lower()

        if self.extension not in SUBTITLE_FILE_FORMATS:
            raise forms.ValidationError(_(
                u'Unsupported format. Please upload one of the following: %s'
                % ", ".join(SUBTITLE_FILE_FORMATS)))

        text = data.read()
        encoding = chardet.detect(text)['encoding']

        if not encoding:
            raise forms.ValidationError(_(u'Can not detect file encoding'))

        # For xml based formats we can't just convert to unicode, as the parser
        # will complain that the string encoding doesn't match the encoding
        # declaration in the xml file if it's not utf-8.
        is_xml = self.extension in ('dfxp', 'ttml', 'xml')
        decoded = force_unicode(text, encoding) if not is_xml else text

        try:
            parser = babelsubs.load_from(decoded, type=self.extension)
            self._parsed_subtitles = parser.to_internal()
        except TypeError, e:
            raise forms.ValidationError(e)
        except ValueError, e:
            raise forms.ValidationError(e)

        data.seek(0)

        return data

    def clean(self):
        if self.video.is_writelocked:
            raise forms.ValidationError(_(
                u'Somebody is subtitling this video right now. Try later.'))

        from_language_code = self.cleaned_data.get('from_language_code')
        language_code = self.cleaned_data['language_code']
        subtitle_language = self.video.subtitle_language(language_code)

        if from_language_code:
            # If this is a translation, we'll retrieve the source
            # language/version here so we can use it later.
            self.from_sl = self.video.subtitle_language(from_language_code)
            if self.from_sl is None:
                raise forms.ValidationError(
                    _(u'Invalid from language: %(language)s') % {
                        'language': get_language_label(from_language_code),
                    })
            self.from_sv = self.from_sl.get_tip(public=True)
            if self.from_sv is None:
                raise forms.ValidationError(
                    _(u'%(language)s has no public versions') % {
                        'language': get_language_label(from_language_code),
                    })
        else:
            self.from_sl = None
            self.from_sv = None

        # If this SubtitleLanguage already exists, we need to verify a few
        # things about it before we let the user upload a set of subtitles to
        # it.
        if subtitle_language:
            # Verify that it's not writelocked.
            self._verify_not_writelocked(subtitle_language)

            # Make sure there are no translation conflicts.  Basically, fail if
            # any of the following are true:
            #
            # 1. The user specified that this was a translation, but the
            #    existing SubtitleLanguage is *not* a translation.
            # 2. The user specified that this was a translation, and the
            #    existing language is a translation, but of a different language
            #    than the user gave.
            self._verify_no_translation_conflict(subtitle_language,
                                                 from_language_code)

        # If we are translating from another version, check that the number of
        # subtitles matches the source.
        self._verify_translation_subtitle_counts(from_language_code)

        # Videos that are part of a team have a few more restrictions.
        team_video = self.video.get_team_video()
        if team_video:
            # You can only upload to a language with a subtitle/translate task
            # open if that task is assigned to you, or if it's unassigned and
            # you can assign yourself.
            self._verify_no_blocking_subtitle_translate_tasks(team_video,
                                                              language_code)

            # You cannot upload at all to a language that has a review or
            # approve task open.
            self._verify_no_blocking_review_approve_tasks(team_video,
                                                          language_code)

            # Finally ensure that the teams "who can translate/transcribe"
            # settings don't prevent this upload.
            self._verify_team_policies(team_video, language_code,
                                       from_language_code)

        return self.cleaned_data


    def _find_title_description(self, language_code):
        """Find the title and description that should be used.

        Uploads have no way to set the title or description, so just set them to
        the previous version's or the video's.

        """
        subtitle_language = self.video.subtitle_language(language_code)
        title, description = self.video.title, self.video.description

        if subtitle_language:
            previous_version = subtitle_language.get_tip()
            if previous_version:
                title = previous_version.title
                description = previous_version.description

        return title, description

    def _find_parents(self, from_language_code):
        """Find the parents that should be used for this upload.

        Until the new UI is in place we need to fake translations by setting
        parentage.

        """
        parents = []

        if from_language_code:
            from_language = self.video.subtitle_language(from_language_code)
            from_version = from_language.get_tip(full=True)
            parents = [from_version]

        return parents

    def _save_primary_audio_language_code(self):
        palc = self.cleaned_data['primary_audio_language_code']
        if palc:
            self.video.primary_audio_language_code = palc
            self.video.save()

    def save(self):
        # If the primary audio language code was given, we adjust it on the
        # video NOW, before saving the subtitles, so that the pipeline can take
        # it into account when determining task types.
        self._save_primary_audio_language_code()

        language_code = self.cleaned_data['language_code']
        from_language_code = self.cleaned_data['from_language_code']
        complete = self.cleaned_data['complete']


        subtitles = self._parsed_subtitles
        if from_language_code:
            # If this is a translation, its subtitles should use the timing data
            # from the source.  We know that the source has at least as many
            # subtitles as the new version, so we can just match them up
            # first-come, first-serve.
            source_subtitles = self.from_sv.get_subtitles()
            i = 0
            # instead of translating to subtitle_items, we're updating the
            # dfxp elements in place. This guarantees no monkey business with
            # escaping / styling
            for old, new in izip(source_subtitles.subtitle_items(), subtitles.get_subtitles()):
                subtitles.update(i, from_ms=old.start_time, to_ms=old.end_time)
                i += 1
        else:
            # Otherwise we can just use the subtitles the user uploaded as-is.
            # No matter what, text files that aren't translations cannot be
            # complete because they don't have timing data.
            if self.extension == 'txt':
                complete = False

        title, description = self._find_title_description(language_code)
        parents = self._find_parents(from_language_code)

        version = pipeline.add_subtitles(
            self.video, language_code, subtitles,
            title=title, description=description, author=self.user,
            parents=parents, committer=self.user, complete=complete,
            origin=ORIGIN_UPLOAD)

        # Handle forking SubtitleLanguages that were translations when
        # a standalone version is uploaded.
        #
        # For example: assume there is a French translation of English.
        # Uploading a "straight from video" version of French should fork it.
        sl = version.subtitle_language
        if not from_language_code and is_dependent(sl):
            sl.fork()

        # TODO: Pipeline this.
        video_changed_tasks.delay(sl.video_id, version.id)

        return version


    def get_errors(self):
        output = {}
        for key, value in self.errors.items():
            output[key] = '\n'.join([force_unicode(i) for i in value])
        return output

