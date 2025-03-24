# Universal Subtitles, universalsubtitles.org
# 
# Copyright (C) 2010 Participatory Culture Foundation
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

from auth.models import CustomUser as User
from django import forms
from teams.models import Team, TeamMember, TeamVideo, Task, Project, Workflow
from django.utils.translation import ugettext_lazy as _
from utils.validators import MaxFileSizeValidator
from django.conf import settings
from videos.models import VideoMetadata, VIDEO_META_TYPE_IDS
from videos.forms import AddFromFeedForm
from django.utils.safestring import mark_safe
from utils.forms import AjaxForm
import re
from utils.translation import get_languages_list
from utils.forms.unisub_video_form import UniSubBoundVideoField

from apps.teams.moderation import add_moderation, remove_moderation

from doorman import feature_is_on


class EditLogoForm(forms.ModelForm, AjaxForm):
    logo = forms.ImageField(validators=[MaxFileSizeValidator(settings.AVATAR_MAX_SIZE)], required=False)

    
    class Meta:
        model = Team
        fields = ('logo',)

    def clean(self):
        if 'logo' in self.cleaned_data and not self.cleaned_data.get('logo'):
            del self.cleaned_data['logo']
        return self.cleaned_data

class EditTeamVideoForm(forms.ModelForm):
    author = forms.CharField(max_length=255, required=False)
    creation_date = forms.DateField(required=False, input_formats=['%Y-%m-%d'],
                                    help_text="Format: YYYY-MM-DD")

    
    project = forms.ModelChoiceField(
        label=_(u'Project'),
        queryset = Project.objects.none(),
        required=True,
        empty_label=None,
        help_text=_(u"Let's keep things tidy, shall we?")
    )
                                             
    class Meta:
        model = TeamVideo
        fields = ('title', 'description', 'thumbnail', 'project',)
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        
        super(EditTeamVideoForm, self).__init__(*args, **kwargs)


        self.fields['project'].queryset = self.instance.team.project_set.all()
        if feature_is_on("MODERATION"):
            self.should_add_moderation = self.should_remove_moderation = False

            if self.instance:
                video  = self.instance.video
                team = self.instance.team

                if video and team:
                    who_owns = video.moderated_by
                    is_ours = who_owns and who_owns == team
                    is_moderated = False
                    if who_owns and not is_ours:
                        self.is_moderated_by_other_team = who_owns
                        # should write about moderation
                        pass
                    else:
                        if is_ours:
                            is_moderated = True
                        self.fields['is_moderated'] = forms.BooleanField(
                            label=_("Moderate subtitles"),
                            initial=is_moderated,
                            required=False
                        )

    def clean(self, *args, **kwargs):
        super(EditTeamVideoForm, self).clean(*args, **kwargs)

        if feature_is_on("MODERATION"):
            should_moderate = self.cleaned_data.get("is_moderated", False)
            if self.instance:

                team = self.instance.team
                video = self.instance.video
                who_owns = video.moderated_by
                is_ours = who_owns and who_owns == team
                if should_moderate:
                    if  is_ours:
                    # do nothing, we are good!
                        pass
                    elif  who_owns:
                        self._errors['is_moderated'] = self.error_class([u"This video is already moderated by team %s" % who_owns])
                        del self.cleaned_data['is_moderated']
                    else:
                        self.should_add_moderation = True
                else:
                    if not who_owns:
                        # do nothing we are good!
                        pass
                    elif is_ours:
                        self.should_remove_moderation = True

        return self.cleaned_data

    def save(self, *args, **kwargs):
        obj = super(EditTeamVideoForm, self).save(*args, **kwargs)

        video = obj.video
        team = obj.team

        if feature_is_on("MODERATION"):
            if self.should_add_moderation:
                try:
                    add_moderation(video, team, self.user)
                except Exception ,e:
                    raise
                    self._errors["should_moderate"] = [e]
            elif self.should_remove_moderation:

                    try:
                        remove_moderation(video, team, self.user)
                    except Exception ,e:
                        raise
                        self._errors["should_moderate"] = [e]

        author = self.cleaned_data['author'].strip()
        creation_date = VideoMetadata.date_to_string(self.cleaned_data['creation_date'])

        self._save_metadata(video, 'Author', author)
        self._save_metadata(video, 'Creation Date', creation_date)

    def _save_metadata(self, video, meta, content):
        '''Save a single piece of metadata for the given video.

        The metadata is only saved if necessary (i.e. it's not blank OR it's blank
        but there's already other data that needs to be overwritten).

        '''
        meta_type_id = VIDEO_META_TYPE_IDS[meta]

        try:
            meta = VideoMetadata.objects.get(video=video, metadata_type=meta_type_id)
            meta.content = content
            meta.save()
        except VideoMetadata.DoesNotExist:
            if content:
                VideoMetadata(video=video, metadata_type=meta_type_id,
                              content=content).save()

class BaseVideoBoundForm(forms.ModelForm):
    video_url = UniSubBoundVideoField(label=_('Video URL'), verify_exists=True, 
        help_text=_("Enter the URL of any compatible video or any video on our site. You can also browse the site and use the 'Add Video to Team' menu."))
    
    def __init__(self, *args, **kwargs):
        super(BaseVideoBoundForm, self).__init__(*args, **kwargs)
        if hasattr(self, 'user'):
            self.fields['video_url'].user = self.user
    
class AddTeamVideoForm(BaseVideoBoundForm):
    language = forms.ChoiceField(label=_(u'Video language'), choices=settings.ALL_LANGUAGES,
                                 required=False,
                                 help_text=_(u'It will be saved only if video does not exist in our database.'))


    project = forms.ModelChoiceField(
        label=_(u'Project'),
        queryset = Project.objects.none(),
        required=False,
        empty_label=None,
        help_text=_(u"Let's keep things tidy, shall we?")
    )
    class Meta:
        model = TeamVideo
        fields = ('video_url', 'language', 'title', 'description', 'thumbnail', 'project',)
        
    def __init__(self, team, user, *args, **kwargs):
        self.team = team
        self.user = user
        super(AddTeamVideoForm, self).__init__(*args, **kwargs)
        self.fields['language'].choices = get_languages_list(True)
        self.fields['project'].queryset = self.team.project_set.all()

    def clean_video_url(self):
        video_url = self.cleaned_data['video_url']
        video = self.fields['video_url'].video
        try:
            tv = TeamVideo.objects.get(team=self.team, video=video)
            raise forms.ValidationError(mark_safe(u'Team has this <a href="%s">video</a>' % tv.get_absolute_url()))
        except TeamVideo.DoesNotExist:
            pass
        
        return video_url
    
    def clean(self):
        language = self.cleaned_data['language']
        video = self.fields['video_url'].video
        original_sl = video.subtitle_language()

        if video and (original_sl and not original_sl.language) and not language:
            msg = _(u'Set original language for this video.')
            self._errors['language'] = self.error_class([msg])
            
        return self.cleaned_data
    
    def save(self, commit=True):
        video_language = self.cleaned_data['language']
        video = self.fields['video_url'].video
        if video_language:
            original_language = video.subtitle_language()
            if original_language and not original_language.language and \
                not video.subtitlelanguage_set.filter(language=video_language).exists():
                original_language.language = video_language
                original_language.save()
            
        obj = super(AddTeamVideoForm, self).save(False)
        obj.video = video
        obj.team = self.team
        commit and obj.save()
        return obj

class AddTeamVideosFromFeedForm(AddFromFeedForm):
    def __init__(self, team, user, *args, **kwargs):
        self.team = team
        super(AddTeamVideosFromFeedForm, self).__init__(user, *args, **kwargs)

    def save(self, *args, **kwargs):
        videos = super(AddTeamVideosFromFeedForm, self).save(*args, **kwargs)

        team_videos = []
        project = self.team.default_project
        for video, video_created in videos:
            try:
                tv = TeamVideo.objects.get(video=video, team=self.team)
                tv_created = False
            except TeamVideo.DoesNotExist:
                tv = TeamVideo(video=video, team=self.team, added_by=self.user,
                               project=project)
                tv.save()
                tv_created = True
            team_videos.append((tv, tv_created))

        return team_videos

    def success_message(self):
        if not self.video_limit_routreach:
            return _(u"%(count)s videos have been added. "
                     u"It will take a minute or so for them to appear.")
        else:
            return _(u"%(count)s videos have been added. "
                     u"It will take a minute or so for them to appear. "
                     u"To add the remaining videos from this feed, "
                     u"submit this feed again and make sure to "
                     u'check "Save feed" box.')



class CreateTeamForm(BaseVideoBoundForm):
    logo = forms.ImageField(validators=[MaxFileSizeValidator(settings.AVATAR_MAX_SIZE)], required=False)
    
    class Meta:
        model = Team
        fields = ('name', 'slug', 'description', 'logo', 'membership_policy', 'is_moderated', 'video_policy', 
                  'is_visible', 'video_url')
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(CreateTeamForm, self).__init__(*args, **kwargs)
        self.fields['video_url'].label = _(u'Team intro video URL')
        self.fields['video_url'].required = False
        self.fields['video_url'].help_text = _(u'''You can put an optional video 
on your team homepage that explains what your team is about, to attract volunteers. 
Enter a link to any compatible video, or to any video page on our site.''')
        self.fields['is_visible'].widget.attrs['class'] = 'checkbox'
        self.fields['is_moderated'].widget.attrs['class'] = 'checkbox'
        self.fields['slug'].label = _(u'Team URL: http://universalsubtitles.org/teams/')
    
    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if re.match('^\d+$', slug):
            raise forms.ValidationError('Field can\'t contains only numbers')
        return slug
            
    def save(self, user):
        team = super(CreateTeamForm, self).save(False)
        video = self.fields['video_url'].video
        if video:
            team.video = video
        team.save()
        TeamMember(team=team, user=user, role=TeamMember.ROLE_MANAGER).save()
        return team
    
class EditTeamForm(BaseVideoBoundForm):
    logo = forms.ImageField(validators=[MaxFileSizeValidator(settings.AVATAR_MAX_SIZE)], required=False)

    class Meta:
        model = Team
        fields = ('name', 'description', 'logo', 
                  'membership_policy', 'is_moderated', 'video_policy', 
                  'is_visible', 'video_url', 'application_text', 
                  'page_content')

    def __init__(self, *args, **kwargs):
        super(EditTeamForm, self).__init__(*args, **kwargs)
        self.fields['video_url'].label = _(u'Team intro video URL')
        self.fields['video_url'].required = False
        self.fields['video_url'].help_text = _(u'''You can put an optional video 
on your team homepage that explains what your team is about, to attract volunteers. 
Enter a link to any compatible video, or to any video page on our site.''')
        self.fields['is_visible'].widget.attrs['class'] = 'checkbox'
        self.fields['is_moderated'].widget.attrs['class'] = 'checkbox'
        
    def clean(self):
        if 'logo' in self.cleaned_data:
            #It is saved with edit_logo view
            del self.cleaned_data['logo']
        return self.cleaned_data
    
    def save(self):
        team = super(EditTeamForm, self).save(False)
        video = self.fields['video_url'].video
        if video:
            team.video = video
        team.save()

        if team.is_open():
            for item in team.applications.all():
                item.approve()
        return team    

class EditTeamFormAdmin(EditTeamForm):
    logo = forms.ImageField(validators=[MaxFileSizeValidator(settings.AVATAR_MAX_SIZE)], required=False)

    class Meta:
        model = Team
        fields = ('name', 'header_html_text', 'description', 'logo', 
                  'membership_policy', 'is_moderated', 'video_policy', 
                  'is_visible', 'video_url', 'application_text', 
                  'page_content')


class TaskAssignForm(forms.Form):
    task = forms.ModelChoiceField(queryset=Task.objects.all())
    assignee = forms.ModelChoiceField(queryset=User.objects.all())

    def __init__(self, team, member, *args, **kwargs):
        super(TaskAssignForm, self).__init__(*args, **kwargs)

        self.team = team
        self.member = member
        self.fields['assignee'].queryset = User.objects.filter(teammember__team=team)


    def clean_task(self):
        task = self.cleaned_data['task']

        # TODO: check that self.user has permission to assign the task

        return task

    def clean(self):
        if not self.member.can_assign_tasks():
            raise forms.ValidationError(_(
                u'You do not have permission to assign this task.'))

        # TODO: check that the assignee can be assigned to the given task

        return self.cleaned_data

class TaskDeleteForm(forms.Form):
    task = forms.ModelChoiceField(queryset=Task.objects.all())

    def __init__(self, user, *args, **kwargs):
        self.user = user
        return super(TaskDeleteForm, self).__init__(*args, **kwargs)


    def clean_task(self):
        task = self.cleaned_data['task']

        # TODO: check that self.user has permission to delete the task

        return task


class GuidelinesMessagesForm(forms.Form):
    messages_invite = forms.CharField(max_length=1024, required=False)
    messages_manager = forms.CharField(max_length=1024, required=False)
    messages_admin = forms.CharField(max_length=1024, required=False)

    guidelines_subtitle = forms.CharField(max_length=1024, required=False)
    guidelines_translate = forms.CharField(max_length=1024, required=False)
    guidelines_review = forms.CharField(max_length=1024, required=False)

class SettingsForm(forms.ModelForm):
    # TODO: Handle slug change.
    class Meta:
        model = Team
        fields = ('name', 'membership_policy', 'video_policy', 'description',
                  'workflow_enabled')

class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ('perm_subtitle', 'perm_translate', 'perm_review', 'perm_approve')
