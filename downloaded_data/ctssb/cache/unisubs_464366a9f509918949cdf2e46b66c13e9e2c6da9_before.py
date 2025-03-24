# Universal Subtitles, universalsubtitles.org
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
import datetime

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.signals import post_save, post_delete, pre_delete
from django.http import Http404
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from haystack import site
from haystack.query import SQ

import teams.moderation_const as MODERATION
from apps.comments.models import Comment
from auth.models import CustomUser as User
from messages import tasks as notifier
from messages.models import Message
from teams.moderation_const import WAITING_MODERATION
from teams.permissions_const import (
    TEAM_PERMISSIONS, PROJECT_PERMISSIONS, LANG_PERMISSIONS, ROLE_OWNER,
    ROLE_ADMIN, ROLE_MANAGER, ROLE_CONTRIBUTOR
)
from teams.tasks import update_one_team_video
from utils import DEFAULT_PROTOCOL
from utils.amazon import S3EnabledImageField
from utils.panslugify import pan_slugify
from utils.searching import get_terms
from videos.models import Video, SubtitleLanguage, SubtitleVersion


ALL_LANGUAGES = [(val, _(name))for val, name in settings.ALL_LANGUAGES]


def get_perm_names(model, perms):
    return [("%s-%s-%s" % (model._meta.app_label,
                           model._meta.object_name,
                           p[0]),
             p[1])
            for p in perms]


# Teams
class TeamManager(models.Manager):
    def get_query_set(self):
        """Return a QS of all non-deleted teams."""
        return super(TeamManager, self).get_query_set().filter(deleted=False)

    def for_user(self, user):
        """Return a QS of all the (non-deleted) teams visible for the given user."""
        if user.is_authenticated():
            return self.get_query_set().filter(
                    models.Q(is_visible=True) |
                    models.Q(members__user=user)
            ).distinct()
        else:
            return self.get_query_set().filter(is_visible=True)

class Team(models.Model):
    APPLICATION = 1
    INVITATION_BY_MANAGER = 2
    INVITATION_BY_ALL = 3
    OPEN = 4
    INVITATION_BY_ADMIN = 5
    MEMBERSHIP_POLICY_CHOICES = (
            (OPEN, _(u'Open')),
            (APPLICATION, _(u'Application')),
            (INVITATION_BY_ALL, _(u'Invitation by any team member')),
            (INVITATION_BY_MANAGER, _(u'Invitation by manager')),
            (INVITATION_BY_ADMIN, _(u'Invitation by admin')),
            )

    VP_MEMBER = 1
    VP_MANAGER = 2
    VP_ADMIN = 3
    VIDEO_POLICY_CHOICES = (
        (VP_MEMBER, _(u'Any team member')),
        (VP_MANAGER, _(u'Managers and admins')),
        (VP_ADMIN, _(u'Admins only'))
    )

    TASK_ASSIGN_CHOICES = (
            (10, 'Any team member'),
            (20, 'Managers and admins'),
            (30, 'Admins only'),
            )
    TASK_ASSIGN_NAMES = dict(TASK_ASSIGN_CHOICES)
    TASK_ASSIGN_IDS = dict([choice[::-1] for choice in TASK_ASSIGN_CHOICES])

    SUBTITLE_CHOICES = (
            (10, 'Anyone'),
            (20, 'Any team member'),
            (30, 'Only managers and admins'),
            (40, 'Only admins'),
            )
    SUBTITLE_NAMES = dict(SUBTITLE_CHOICES)
    SUBTITLE_IDS = dict([choice[::-1] for choice in SUBTITLE_CHOICES])

    name = models.CharField(_(u'name'), max_length=250, unique=True)
    slug = models.SlugField(_(u'slug'), unique=True)
    description = models.TextField(_(u'description'), blank=True, help_text=_('All urls will be converted to links. Line breaks and HTML not supported.'))

    logo = S3EnabledImageField(verbose_name=_(u'logo'), blank=True, upload_to='teams/logo/', thumb_options=dict(autocrop=True, upscale=True))
    is_visible = models.BooleanField(_(u'publicly Visible?'), default=True)
    videos = models.ManyToManyField(Video, through='TeamVideo',  verbose_name=_('videos'))
    users = models.ManyToManyField(User, through='TeamMember', related_name='teams', verbose_name=_('users'))

    # these allow unisubs to do things on user's behalf such as uploding subs to Youtub
    third_party_accounts = models.ManyToManyField("accountlinker.ThirdPartyAccount",  related_name='tseams', verbose_name=_('third party accounts'))

    points = models.IntegerField(default=0, editable=False)
    applicants = models.ManyToManyField(User, through='Application', related_name='applicated_teams', verbose_name=_('applicants'))
    created = models.DateTimeField(auto_now_add=True)
    highlight = models.BooleanField(default=False)
    video = models.ForeignKey(Video, null=True, blank=True, related_name='intro_for_teams', verbose_name=_(u'Intro Video'))
    application_text = models.TextField(blank=True)
    page_content = models.TextField(_(u'Page content'), blank=True, help_text=_(u'You can use markdown. This will replace Description.'))
    is_moderated = models.BooleanField(default=False)
    header_html_text = models.TextField(blank=True, default='', help_text=_(u"HTML that appears at the top of the teams page."))
    last_notification_time = models.DateTimeField(editable=False, default=datetime.datetime.now)

    # Enabling Features
    projects_enabled = models.BooleanField(default=False)
    workflow_enabled = models.BooleanField(default=False)

    # Policies and Permissions
    membership_policy = models.IntegerField(_(u'membership policy'),
            choices=MEMBERSHIP_POLICY_CHOICES,
            default=OPEN)
    video_policy = models.IntegerField(_(u'video policy'),
            choices=VIDEO_POLICY_CHOICES,
            default=VP_MEMBER)
    task_assign_policy = models.IntegerField(_(u'task assignment policy'),
            choices=TASK_ASSIGN_CHOICES,
            default=TASK_ASSIGN_IDS['Any team member'])
    subtitle_policy = models.IntegerField(_(u'subtitling policy'),
            choices=SUBTITLE_CHOICES,
            default=SUBTITLE_IDS['Anyone'])
    translate_policy = models.IntegerField(_(u'translation policy'),
            choices=SUBTITLE_CHOICES,
            default=SUBTITLE_IDS['Anyone'])
    max_tasks_per_member = models.PositiveIntegerField(_(u'maximum tasks per member'),
            default=None, null=True, blank=True)
    task_expiration = models.PositiveIntegerField(_(u'task expiration (days)'),
            default=None, null=True, blank=True)

    deleted = models.BooleanField(default=False)

    objects = TeamManager()
    all_objects = models.Manager() # For accessing deleted teams, if necessary.

    class Meta:
        ordering = ['name']
        verbose_name = _(u'Team')
        verbose_name_plural = _(u'Teams')


    def save(self, *args, **kwargs):
        creating = self.pk is None
        super(Team, self).save(*args, **kwargs)
        if creating:
            # make sure we create a default project
            self.default_project

    def __unicode__(self):
        return self.name

    def render_message(self, msg):
        """Return a string of HTML represention a team header for a notification.

        TODO: Get this out of the model and into a templatetag or something.

        """
        author_page = msg.author.get_absolute_url() if msg.author else ''
        context = {
            'team': self,
            'msg': msg,
            'author': msg.author,
            'author_page': author_page,
            'team_page': self.get_absolute_url(),
            "STATIC_URL": settings.STATIC_URL,
        }
        return render_to_string('teams/_team_message.html', context)

    def is_open(self):
        """Return whether this team's membership is open to the public."""
        return self.membership_policy == self.OPEN

    def is_by_application(self):
        """Return whether this team's membership is by application only."""
        return self.membership_policy == self.APPLICATION

    @classmethod
    def get(cls, slug, user=None, raise404=True):
        """Return the Team with the given slug.

        If a user is given the Team must be visible to that user.  Otherwise the
        Team must be visible to the public.

        If raise404 is given an Http404 exception will be raised if a suitable
        team is not found.  Otherwise None will be returned.

        """
        if user:
            qs = cls.objects.for_user(user)
        else:
            qs = cls.objects.filter(is_visible=True)
        try:
            return qs.get(slug=slug)
        except cls.DoesNotExist:
            try:
                return qs.get(pk=int(slug))
            except (cls.DoesNotExist, ValueError):
                pass

        if raise404:
            raise Http404

    def get_workflow(self):
        """Return the workflow for the given team.

        A workflow will always be returned.  If one isn't specified for the team
        a default (unsaved) one will be populated with default values and
        returned.

        TODO: Refactor this behaviour into something less confusing.

        """
        return Workflow.get_for_target(self.id, 'team')


    # Thumbnails
    def logo_thumbnail(self):
        """Return the URL for a kind-of small version of this team's logo, or None."""
        if self.logo:
            return self.logo.thumb_url(100, 100)

    def medium_logo_thumbnail(self):
        """Return the URL for a medium version of this team's logo, or None."""
        if self.logo:
            return self.logo.thumb_url(280, 100)

    def small_logo_thumbnail(self):
        """Return the URL for a really small version of this team's logo, or None."""
        if self.logo:
            return self.logo.thumb_url(50, 50)


    # URLs
    @models.permalink
    def get_absolute_url(self):
        return ('teams:detail', [self.slug])

    def get_site_url(self):
        """Return the full, absolute URL for this team, including http:// and the domain."""
        return '%s://%s%s' % (DEFAULT_PROTOCOL,
                              Site.objects.get_current().domain,
                              self.get_absolute_url())


    # Membership and roles
    def _is_role(self, user, role=None):
        """Return whether the given user has the given role in this team.

        Safe to use with null or unauthenticated users.

        If no role is given, simply return whether the user is a member of this team at all.

        TODO: Change this to use the stuff in teams.permissions.

        """
        if not user or not user.is_authenticated():
            return False
        qs = self.members.filter(user=user)
        if role:
            qs = qs.filter(role=role)
        return qs.exists()

    def is_admin(self, user):
        """Return whether the given user is an admin of this team."""
        return self._is_role(user, TeamMember.ROLE_ADMIN)

    def is_manager(self, user):
        """Return whether the given user is a manager of this team."""
        return self._is_role(user, TeamMember.ROLE_MANAGER)

    def is_member(self, user):
        """Return whether the given user is a member of this team."""
        return self._is_role(user)

    def is_contributor(self, user, authenticated=True):
        """Return whether the given user is a contributor of this team, False otherwise."""
        return self._is_role(user, TeamMember.ROLE_CONTRIBUTOR)

    def can_see_video(self, user, team_video=None):
        """I have no idea.

        TODO: Figure out what this thing is, and if it's still necessary.

        """
        if not user.is_authenticated():
            return False
        return self.is_member(user)

    # moderation


    # Moderation
    def moderates_videos(self):
        """Return whether this team moderates videos in some way, False otherwise.

        Moderation means the team restricts who can create subtitles and/or
        translations.

        """
        if self.subtitle_policy != Team.SUBTITLE_IDS['Anyone']:
            return True

        if self.translate_policy != Team.SUBTITLE_IDS['Anyone']:
            return True

        return False

    def video_is_moderated_by_team(self, video):
        """Return whether this team moderates the given video."""
        return video.moderated_by == self


    # Item counts
    @property
    def member_count(self):
        """Return the number of members of this team.

        Caches the result in-object for performance.

        """
        if not hasattr(self, '_member_count'):
            setattr(self, '_member_count', self.users.count())
        return self._member_count

    @property
    def videos_count(self):
        """Return the number of videos of this team.

        Caches the result in-object for performance.

        """
        if not hasattr(self, '_videos_count'):
            setattr(self, '_videos_count', self.videos.count())
        return self._videos_count

    @property
    def tasks_count(self):
        """Return the number of incomplete, undeleted tasks of this team.

        Caches the result in-object for performance.

        """
        if not hasattr(self, '_tasks_count'):
            setattr(self, '_tasks_count', Task.objects.filter(team=self, deleted=False, completed=None).count())
        return self._tasks_count


    # Applications (people applying to join)
    def application_message(self):
        """Return the membership application message for this team, or '' if none exists."""
        try:
            return self.settings.get(key=Setting.KEY_IDS['messages_application']).data
        except Setting.DoesNotExist:
            return ''

    @property
    def applications_count(self):
        """Return the number of open membership applications to this team.

        Caches the result in-object for performance.

        """
        if not hasattr(self, '_applications_count'):
            setattr(self, '_applications_count', self.applications.count())
        return self._applications_count


    # Language pairs
    def _lang_pair(self, lp, suffix):
        return SQ(content="{0}_{1}_{2}".format(lp[0], lp[1], suffix))

    def get_videos_for_languages_haystack(self, language, project=None, user=None, query=None, sort=None):
        from teams.search_indexes import TeamVideoLanguagesIndex

        is_member = (user and user.is_authenticated()
                     and self.members.filter(user=user).exists())

        if is_member:
            qs =  TeamVideoLanguagesIndex.results_for_members(self).filter(team_id=self.id)
        else:
            qs =  TeamVideoLanguagesIndex.results().filter(team_id=self.id)

        if project:
            qs = qs.filter(project_pk=project.pk)

        if query:
            for term in get_terms(query):
                qs = qs.filter(video_title__icontains=qs.query.clean(term))

        if language:
            qs = qs.filter(video_completed_langs=language)

        qs = qs.order_by({
             'name':  'video_title_exact',
            '-name': '-video_title_exact',
             'subs':  'num_completed_subs',
            '-subs': '-num_completed_subs',
             'time':  'team_video_create_date',
            '-time': '-team_video_create_date',
        }.get(sort or '-time'))

        return qs


    # Projects
    @property
    def default_project(self):
        """Return the default project for this team.

        If it doesn't already exist it will be created.

        TODO: Move the creation into a signal on the team to avoid creating
        multiple default projects here?

        """
        try:
            return Project.objects.get(team=self, slug=Project.DEFAULT_NAME)
        except Project.DoesNotExist:
            p = Project(team=self,name=Project.DEFAULT_NAME)
            p.save()
            return p

    @property
    def has_projects(self):
        """Return whether this team has projects other than the default one."""
        return self.project_set.count() > 1


    # Readable/writeable language codes
    def get_writable_langs(self):
        """Return a list of language code strings that are writable for this team.

        This value may come from memcache.

        """
        return TeamLanguagePreference.objects.get_writable(self)

    def get_readable_langs(self):
        """Return a list of language code strings that are readable for this team.

        This value may come from memcache.

        """
        return TeamLanguagePreference.objects.get_readable(self)


    # Unpublishing
    def unpublishing_enabled(self):
        '''Return whether unpublishing is enabled for this team.

        At the moment unpublishing is only available if the team has reviewing
        and/or approving enabled.

        '''
        w = self.get_workflow()
        return True if w.review_enabled or w.approve_enabled else False


# This needs to be constructed after the model definition since we need a
# reference to the class itself.
Team._meta.permissions = TEAM_PERMISSIONS


# Project
class ProjectManager(models.Manager):
    def for_team(self, team_identifier):
        """Return all non-default projects for the given team with the given identifier.

        The team_identifier passed may be an actual Team object, or a string
        containing a team slug, or the primary key of a team as an integer.

        """
        if hasattr(team_identifier, "pk"):
            team = team_identifier
        elif isinstance(team_identifier, int):
            team = Team.objects.get(pk=team_identifier)
        elif isinstance(team_identifier, str):
            team = Team.objects.get(slug=team_identifier)
        return Project.objects.filter(team=team).exclude(name=Project.DEFAULT_NAME)

class Project(models.Model):
    # All tvs belong to a project, wheather the team has enabled them or not
    # the default project is just a convenience UI that pretends to be part of
    # the team . If this ever gets changed, you need to change migrations/0044
    DEFAULT_NAME = "_root"

    team = models.ForeignKey(Team)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(blank=True)

    name = models.CharField(max_length=255, null=False)
    description = models.TextField(blank=True, null=True, max_length=2048)
    guidelines = models.TextField(blank=True, null=True, max_length=2048)

    slug = models.SlugField(blank=True)
    order = models.PositiveIntegerField(default=0)

    workflow_enabled = models.BooleanField(default=False)

    objects = ProjectManager()

    def __unicode__(self):
        if self.is_default_project:
            return u"---------"
        return u"%s" % (self.name)

    def save(self, slug=None,*args, **kwargs):
        self.modified = datetime.datetime.now()
        slug = slug if slug is not None else self.slug or self.name
        self.slug = pan_slugify(slug)
        super(Project, self).save(*args, **kwargs)

    @property
    def is_default_project(self):
        """Return whether this project is a default project for a team."""
        return self.name == Project.DEFAULT_NAME


    def get_site_url(self):
        """Return the full, absolute URL for this project, including http:// and the domain."""
        return '%s://%s%s' % (DEFAULT_PROTOCOL, Site.objects.get_current().domain, self.get_absolute_url())

    @models.permalink
    def get_absolute_url(self):
        return ('teams:project_video_list', [self.team.slug, self.slug])


    @property
    def videos_count(self):
        """Return the number of videos in this project.

        Caches the result in-object for performance.

        """
        if not hasattr(self, '_videos_count'):
            setattr(self, '_videos_count', TeamVideo.objects.filter(project=self).count())
        return self._videos_count

    @property
    def tasks_count(self):
        """Return the number of incomplete, undeleted tasks in this project.

        Caches the result in-object for performance.

        """
        tasks = Task.objects.filter(team=self.team, deleted=False, completed=None)

        if not hasattr(self, '_tasks_count'):
            setattr(self, '_tasks_count', tasks.filter(team_video__project = self).count())
        return self._tasks_count


    class Meta:
        unique_together = (
                ("team", "name",),
                ("team", "slug",),
        )
        permissions = PROJECT_PERMISSIONS


# TeamVideo
class TeamVideo(models.Model):
    team = models.ForeignKey(Team)
    video = models.ForeignKey(Video)
    title = models.CharField(max_length=2048, blank=True)
    description = models.TextField(blank=True,
        help_text=_(u'Use this space to explain why you or your team need to '
                    u'caption or subtitle this video. Adding a note makes '
                    u'volunteers more likely to help out!'))
    thumbnail = S3EnabledImageField(upload_to='teams/video_thumbnails/', null=True, blank=True,
        help_text=_(u'We automatically grab thumbnails for certain sites, e.g. Youtube'))
    all_languages = models.BooleanField(_('Need help with all languages'), default=False,
        help_text=_(u'If you check this, other languages will not be displayed.'))
    added_by = models.ForeignKey(User)
    created = models.DateTimeField(auto_now_add=True)
    completed_languages = models.ManyToManyField(SubtitleLanguage, blank=True)

    project = models.ForeignKey(Project)

    class Meta:
        unique_together = (('team', 'video'),)

    def __unicode__(self):
        return self.title or unicode(self.video)

    def link_to_page(self):
        if self.all_languages:
            return self.video.get_absolute_url()
        return self.video.video_link()

    @models.permalink
    def get_absolute_url(self):
        return ('teams:team_video', [self.pk])

    def get_thumbnail(self):
        if self.thumbnail:
            return self.thumbnail.thumb_url(100, 100)

        if self.video.thumbnail:
            th = self.video.get_thumbnail()
            if th:
                return th

        if self.team.logo:
            return self.team.logo_thumbnail()

        return ''

    def _original_language(self):
        if not hasattr(self, 'original_language_code'):
            sub_lang = self.video.subtitle_language()
            setattr(self, 'original_language_code', None if not sub_lang else sub_lang.language)
        return getattr(self, 'original_language_code')

    def _calculate_percent_complete(self, sl0, sl1):
        # maybe move this to Video model in future.
        if not sl0 or not sl0.is_dependable():
            return -1
        if not sl1:
            return 0
        if sl1.language == self._original_language():
            return -1
        if sl1.is_dependent():
            if sl1.percent_done == 0:
                return 0
            elif sl0.is_dependent():
                l_dep0 = sl0.real_standard_language()
                l_dep1 = sl1.real_standard_language()
                if l_dep0 and l_dep1 and l_dep0.id == l_dep1.id:
                    return sl1.percent_done
                else:
                    return -1
            else:
                l_dep1 = sl1.real_standard_language()
                return sl1.percent_done if \
                    l_dep1 and l_dep1.id == sl0.id else -1
        else:
            sl1_subtitle_count = 0
            latest_version = sl1.latest_version()
            if latest_version:
                sl1_subtitle_count = latest_version.subtitle_set.count()
            return 0 if sl1_subtitle_count == 0 else -1

    def save(self, *args, **kwargs):
        if not hasattr(self, "project"):
            self.project = self.team.default_project
        super(TeamVideo, self).save(*args, **kwargs)


    def is_checked_out(self, ignore_user=None):
        '''Return whether this video is checked out in a task.

        If a user is given, checkouts by that user will be ignored.  This
        provides a way to ask "can user X check out or work on this task?".

        This is similar to the writelocking done on Videos and
        SubtitleLanguages.

        '''
        tasks = self.task_set.filter(
                # Find all tasks for this video which:
                deleted=False,           # - Aren't deleted
                assignee__isnull=False,  # - Are assigned to someone
                language="",             # - Aren't specific to a language
                completed__isnull=True,  # - Are unfinished
        )
        if ignore_user:
            tasks = tasks.exclude(assignee=ignore_user)

        return tasks.exists()


    # Convenience functions
    def subtitles_started(self):
        """Return whether subtitles have been started for this video."""
        sl = self.video.subtitle_language()
        return True if sl and sl.had_version else False

    def subtitles_finished(self):
        """Return whether at least one set of subtitles has been finished for this video."""
        return (self.subtitles_started() and
                self.video.subtitle_language().is_complete_and_synced())

    def get_workflow(self):
        """Return the appropriate Workflow for this TeamVideo."""
        return Workflow.get_for_team_video(self)


def _create_translation_tasks(team_video, subtitle_version):
    """Create any translation tasks that should be autocreated for this video.

    subtitle_version should be the original SubtitleVersion that these tasks
    will probably be translating from.

    """
    preferred_langs = TeamLanguagePreference.objects.get_preferred(team_video.team)

    for lang in preferred_langs:
        # Don't create tasks for languages that are already complete.
        sl = team_video.video.subtitle_language(lang)
        if sl and sl.is_complete_and_synced():
            continue

        # Don't create tasks for languages that already have one.
        # Doesn't matter if it's complete or not.
        task_exists = Task.objects.filter(
            team=team_video.team, team_video=team_video, language=lang,
            type=Task.TYPE_IDS['Translate']
        ).exists()
        if task_exists:
            continue

        # Otherwise, go ahead and create it.
        task = Task(team=team_video.team, team_video=team_video,
                    subtitle_version=subtitle_version,
                    language=lang, type=Task.TYPE_IDS['Translate'])
        task.save()


def team_video_save(sender, instance, created, **kwargs):
    """Update the Solr index for this team video.

    TODO: Rename this to something more specific.

    """
    update_one_team_video.delay(instance.id)

def team_video_delete(sender, instance, **kwargs):
    """Perform necessary actions for when a TeamVideo is deleted.

    TODO: Split this up into separate signals.

    """
    from videos import metadata_manager
    # not using an async task for this since the async task
    # could easily execute way after the instance is gone,
    # and backend.remove requires the instance.
    tv_search_index = site.get_index(TeamVideo)
    tv_search_index.backend.remove(instance)
    try:
        video = instance.video
        # we need to publish all unpublished subs for this video:
        SubtitleVersion.objects.filter(language__video=video).update(
            moderation_status=MODERATION.UNMODERATED)
        video.is_public = True
        video.moderated_by = None
        video.save()

        metadata_manager.update_metadata(video.pk)
    except Video.DoesNotExist:
        pass


def team_video_autocreate_task(sender, instance, created, raw, **kwargs):
    """Create subtitle/translation tasks for a newly added TeamVideo, if necessary."""
    if created and not raw:
        workflow = Workflow.get_for_team_video(instance)
        if workflow.autocreate_subtitle:
            existing_subtitles = instance.video.completed_subtitle_languages(public_only=True)
            if not existing_subtitles:
                Task(team=instance.team, team_video=instance, subtitle_version=None,
                    language='', type=Task.TYPE_IDS['Subtitle']).save()
            else:
                _create_translation_tasks(instance, existing_subtitles[0].latest_version())

def team_video_add_video_moderation(sender, instance, created, raw, **kwargs):
    """Set the .moderated_by attribute on a newly created TeamVideo's Video, if necessary."""
    if created and not raw and instance.team.moderates_videos():
        instance.video.moderated_by = instance.team
        instance.video.save()

def team_video_rm_video_moderation(sender, instance, **kwargs):
    """Clear the .moderated_by attribute on a newly deleted TeamVideo's Video, if necessary."""
    try:
        # when removing a video, this will be triggered by the fk constraing
        # and will be already removed
        instance.video.moderated_by = None
        instance.video.save()
    except Video.DoesNotExist:
        pass


post_save.connect(team_video_save, TeamVideo, dispatch_uid="teams.teamvideo.team_video_save")
post_save.connect(team_video_autocreate_task, TeamVideo, dispatch_uid='teams.teamvideo.team_video_autocreate_task')
post_save.connect(team_video_add_video_moderation, TeamVideo, dispatch_uid='teams.teamvideo.team_video_add_video_moderation')
post_delete.connect(team_video_delete, TeamVideo, dispatch_uid="teams.teamvideo.team_video_delete")
post_delete.connect(team_video_rm_video_moderation, TeamVideo, dispatch_uid="teams.teamvideo.team_video_rm_video_moderation")




# TeamMember
class TeamMemberManager(models.Manager):
    use_for_related_fields = True

    def create_first_member(self, team, user):
        """Make sure that new teams always have an 'owner' member."""

        tm = TeamMember(team=team, user=user, role=ROLE_OWNER)
        tm.save()
        return tm

class TeamMember(models.Model):
    ROLE_OWNER = ROLE_OWNER
    ROLE_ADMIN = ROLE_ADMIN
    ROLE_MANAGER = ROLE_MANAGER
    ROLE_CONTRIBUTOR = ROLE_CONTRIBUTOR

    ROLES = (
        (ROLE_OWNER, _("Owner")),
        (ROLE_MANAGER, _("Manager")),
        (ROLE_ADMIN, _("Admin")),
        (ROLE_CONTRIBUTOR, _("Contributor")),
    )

    team = models.ForeignKey(Team, related_name='members')
    user = models.ForeignKey(User, related_name='team_members')
    role = models.CharField(max_length=16, default=ROLE_CONTRIBUTOR, choices=ROLES, db_index=True)

    objects = TeamMemberManager()

    def __unicode__(self):
        return u'%s' % self.user


    def project_narrowings(self):
        """Return any project narrowings applied to this member."""
        return self.narrowings.filter(project__isnull=False)

    def language_narrowings(self):
        """Return any language narrowings applied to this member."""
        return self.narrowings.filter(project__isnull=True)


    def project_narrowings_fast(self):
        """Return any project narrowings applied to this member.

        Caches the result in-object for speed.

        """
        return [n for n in  self.narrowings_fast() if n.project]

    def language_narrowings_fast(self):
        """Return any language narrowings applied to this member.

        Caches the result in-object for speed.

        """
        return [n for n in self.narrowings_fast() if n.language]

    def narrowings_fast(self):
        """Return any narrowings (both project and language) applied to this member.

        Caches the result in-object for speed.

        """
        if hasattr(self, '_cached_narrowings'):
            if self._cached_narrowings is not None:
                return self._cached_narrowings

        self._cached_narrowings = self.narrowings.all()
        return self._cached_narrowings


    def has_max_tasks(self):
        """Return whether this member has the maximum number of tasks."""
        max_tasks = self.team.max_tasks_per_member
        if max_tasks:
            if self.user.task_set.incomplete().filter(team=self.team).count() >= max_tasks:
                return True
        return False


    class Meta:
        unique_together = (('team', 'user'),)


def clear_tasks(sender, instance, *args, **kwargs):
    """Unassign all tasks assigned to a user.

    Used when deleting a user from a team.

    """
    tasks = instance.team.task_set.incomplete().filter(assignee=instance.user)
    tasks.update(assignee=None)

pre_delete.connect(clear_tasks, TeamMember, dispatch_uid='teams.members.clear-tasks-on-delete')


# MembershipNarrowing
class MembershipNarrowing(models.Model):
    """Represent narrowings that can be made on memberships.

    A single MembershipNarrowing can apply to a project or a language, but not both.

    """
    member = models.ForeignKey(TeamMember, related_name="narrowings")
    project = models.ForeignKey(Project, null=True, blank=True)
    language = models.CharField(max_length=24, blank=True, choices=ALL_LANGUAGES)

    added_by = models.ForeignKey(TeamMember, related_name="narrowing_includer", null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True, blank=None)
    modified = models.DateTimeField(auto_now=True, blank=None)

    def __unicode__(self):
        if self.project:
            return u"Permission restriction for %s to project %s " % (self.member, self.project)
        else:
            return u"Permission restriction for %s to language %s " % (self.member, self.language)


# Application
class Application(models.Model):
    team = models.ForeignKey(Team, related_name='applications')
    user = models.ForeignKey(User, related_name='team_applications')
    note = models.TextField(blank=True)

    class Meta:
        unique_together = (('team', 'user'),)


    def approve(self):
        """Approve the application.

        This will create an appropriate TeamMember record and then delete itself.

        """
        TeamMember.objects.get_or_create(team=self.team, user=self.user)
        self.delete()

    def deny(self):
        """Queue a Celery task that will handle properly denying this application."""

        # We can't delete the row until the notification task has run.
        notifier.team_application_denied.delay(self.pk)


# Invites
class Invite(models.Model):
    team = models.ForeignKey(Team, related_name='invitations')
    user = models.ForeignKey(User, related_name='team_invitations')
    note = models.TextField(blank=True, max_length=200)
    author = models.ForeignKey(User)
    role = models.CharField(max_length=16, choices=TeamMember.ROLES,
                            default=TeamMember.ROLE_CONTRIBUTOR)

    class Meta:
        unique_together = (('team', 'user'),)


    def accept(self):
        """Accept this invitation.

        Creates an appropriate TeamMember record, sends a notification and
        deletes itself.

        """
        member, created = TeamMember.objects.get_or_create(team=self.team,
                                                           user=self.user,
                                                           role=self.role)
        notifier.team_member_new.delay(member.pk)
        self.delete()

    def deny(self):
        """Deny this invitation.

        Currently just deletes itself, but it could be useful to send
        a notification here in the future.

        """
        self.delete()


    def message_json_data(self, data, msg):
        data['can-reply'] = False
        return data

models.signals.pre_delete.connect(Message.on_delete, Invite)


# Workflows
class Workflow(models.Model):
    REVIEW_CHOICES = (
        (00, "Don't require review"),
        (10, 'Peer must review'),
        (20, 'Manager must review'),
        (30, 'Admin must review'),
    )
    REVIEW_NAMES = dict(REVIEW_CHOICES)
    REVIEW_IDS = dict([choice[::-1] for choice in REVIEW_CHOICES])

    APPROVE_CHOICES = (
        (00, "Don't require approval"),
        (10, 'Manager must approve'),
        (20, 'Admin must approve'),
    )
    APPROVE_NAMES = dict(APPROVE_CHOICES)
    APPROVE_IDS = dict([choice[::-1] for choice in APPROVE_CHOICES])

    team = models.ForeignKey(Team)

    project = models.ForeignKey(Project, blank=True, null=True)
    team_video = models.ForeignKey(TeamVideo, blank=True, null=True)

    autocreate_subtitle = models.BooleanField(default=False)
    autocreate_translate = models.BooleanField(default=False)

    review_allowed = models.PositiveIntegerField(
            choices=REVIEW_CHOICES, verbose_name='reviewers', default=0)

    approve_allowed = models.PositiveIntegerField(
            choices=APPROVE_CHOICES, verbose_name='approvers', default=0)

    created = models.DateTimeField(auto_now_add=True, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        unique_together = ('team', 'project', 'team_video')


    @classmethod
    def _get_target_team(cls, id, type):
        """Return the team for the given target.

        The target is identified by id (its PK as an integer) and type (a string
        of 'team_video', 'project', or 'team').

        """
        if type == 'team_video':
            return TeamVideo.objects.select_related('team').get(pk=id).team
        elif type == 'project':
            return Project.objects.select_related('team').get(pk=id).team
        else:
            return Team.objects.get(pk=id)

    @classmethod
    def get_for_target(cls, id, type, workflows=None):
        '''Return the most specific Workflow for the given target.

        If target object does not exist, None is returned.

        If workflows is given, it should be a QS or List of all Workflows for
        the TeamVideo's team.  This will let you look it up yourself once and
        use it in many of these calls to avoid hitting the DB each time.

        If workflows is not given it will be looked up with one DB query.

        '''
        if not workflows:
            team = Workflow._get_target_team(id, type)
            workflows = list(Workflow.objects.filter(team=team.id).select_related('project', 'team', 'team_video'))
        else:
            team = workflows[0].team

        default_workflow = Workflow(team=team)

        if not workflows:
            return default_workflow

        if type == 'team_video':
            try:
                return [w for w in workflows
                        if w.team_video and w.team_video.id == id][0]
            except IndexError:
                # If there's no video-specific workflow for this video, there
                # might be a workflow for its project, so we'll start looking
                # for that instead.
                team_video = TeamVideo.objects.get(pk=id)
                id, type = team_video.project_id, 'project'

        if type == 'project':
            try:
                return [w for w in workflows
                        if w.project and w.project.workflow_enabled
                        and w.project.id == id and not w.team_video][0]
            except IndexError:
                # If there's no project-specific workflow for this project,
                # there might be one for its team, so we'll fall through.
                pass

        if not team.workflow_enabled:
            return default_workflow

        return [w for w in workflows
                if (not w.project) and (not w.team_video)][0]


    @classmethod
    def get_for_team_video(cls, team_video, workflows=None):
        '''Return the most specific Workflow for the given team_video.

        If workflows is given, it should be a QuerySet or List of all Workflows
        for the TeamVideo's team.  This will let you look it up yourself once
        and use it in many of these calls to avoid hitting the DB each time.

        If workflows is not given it will be looked up with one DB query.

        NOTE: This function caches the workflow for performance reasons.  If the
        workflow changes within the space of a single request that
        _cached_workflow should be cleared.

        '''
        if not hasattr(team_video, '_cached_workflow'):
            team_video._cached_workflow = Workflow.get_for_target(team_video.id, 'team_video', workflows)
        return team_video._cached_workflow

    @classmethod
    def get_for_project(cls, project, workflows=None):
        '''Return the most specific Workflow for the given project.

        If workflows is given, it should be a QuerySet or List of all Workflows
        for the Project's team.  This will let you look it up yourself once
        and use it in many of these calls to avoid hitting the DB each time.

        If workflows is not given it will be looked up with one DB query.

        '''
        return Workflow.get_for_target(project.id, 'project', workflows)

    @classmethod
    def add_to_team_videos(cls, team_videos):
        '''Add the appropriate Workflow objects to each TeamVideo as .workflow.

        This will only perform one DB query, and it will add the most specific
        workflow possible to each TeamVideo.

        This only exists for performance reasons.

        '''
        if not team_videos:
            return []

        workflows = list(Workflow.objects.filter(team=team_videos[0].team))

        for tv in team_videos:
            tv.workflow = Workflow.get_for_team_video(tv, workflows)


    def get_specific_target(self):
        """Return the most specific target that this workflow applies to."""
        return self.team_video or self.project or self.team


    def __unicode__(self):
        target = self.get_specific_target()
        return u'Workflow %s for %s (%s %d)' % (
                self.pk, target, target.__class__.__name__, target.pk)


    # Convenience functions for checking if a step of the workflow is enabled.
    @property
    def review_enabled(self):
        """Return whether any form of review is enabled for this workflow."""
        return True if self.review_allowed else False

    @property
    def approve_enabled(self):
        """Return whether any form of approval is enabled for this workflow."""
        return True if self.approve_allowed else False


# Tasks
class TaskManager(models.Manager):
    def not_deleted(self):
        """Return a QS of tasks that are not deleted."""
        return self.get_query_set().filter(deleted=False)


    def incomplete(self):
        """Return a QS of tasks that are not deleted or completed."""
        return self.not_deleted().filter(completed=None)

    def complete(self):
        """Return a QS of tasks that are not deleted, but are completed."""
        return self.not_deleted().filter(completed__isnull=False)


    def _type(self, type, completed, approved=None):
        """Return a QS of tasks that are not deleted and are of the given type.

        type should be a string matching a label in Task.TYPE_CHOICES.

        completed should be one of:

        * True (only show completed tasks)
        * False (only show incomplete tasks)
        * None (don't filter on completion status)

        approved should be either None or a string matching a label in
        Task.APPROVED_CHOICES.

        """
        qs = self.not_deleted().filter(type=Task.TYPE_IDS[type])

        if completed == False:
            qs = qs.filter(completed=None)
        elif completed == True:
            qs = qs.filter(completed__isnull=False)

        if approved:
            qs = qs.filter(approved=Task.APPROVED_IDS[approved])

        return qs


    def incomplete_subtitle(self):
        """Return a QS of subtitle tasks that are not deleted or completed."""
        return self._type('Subtitle', False)

    def incomplete_translate(self):
        """Return a QS of translate tasks that are not deleted or completed."""
        return self._type('Translate', False)

    def incomplete_review(self):
        """Return a QS of review tasks that are not deleted or completed."""
        return self._type('Review', False)

    def incomplete_approve(self):
        """Return a QS of approve tasks that are not deleted or completed."""
        return self._type('Approve', False)


    def complete_subtitle(self):
        """Return a QS of subtitle tasks that are not deleted, but are completed."""
        return self._type('Subtitle', True)

    def complete_translate(self):
        """Return a QS of translate tasks that are not deleted, but are completed."""
        return self._type('Translate', True)

    def complete_review(self, approved=None):
        """Return a QS of review tasks that are not deleted, but are completed.

        If approved is given the tasks are further filtered on their .approved
        attribute.  It must be a string matching one of the labels in
        Task.APPROVED_CHOICES, like 'Rejected'.

        """
        return self._type('Review', True, approved)

    def complete_approve(self, approved=None):
        """Return a QS of approve tasks that are not deleted, but are completed.

        If approved is given the tasks are further filtered on their .approved
        attribute.  It must be a string matching one of the labels in
        Task.APPROVED_CHOICES, like 'Rejected'.

        """
        return self._type('Approve', True, approved)


    def all_subtitle(self):
        """Return a QS of subtitle tasks that are not deleted."""
        return self._type('Subtitle', None)

    def all_translate(self):
        """Return a QS of translate tasks that are not deleted."""
        return self._type('Translate', None)

    def all_review(self):
        """Return a QS of review tasks that are not deleted."""
        return self._type('Review', None)

    def all_approve(self):
        """Return a QS of tasks that are not deleted."""
        return self._type('Approve', None)

    def all_review_or_approve(self):
        """Return a QS of review or approve tasks that are not deleted."""
        return self.not_deleted().filter(type__in=(Task.TYPE_IDS['Review'],
                                                   Task.TYPE_IDS['Approve']))

class Task(models.Model):
    TYPE_CHOICES = (
        (10, 'Subtitle'),
        (20, 'Translate'),
        (30, 'Review'),
        (40, 'Approve'),
    )
    TYPE_NAMES = dict(TYPE_CHOICES)
    TYPE_IDS = dict([choice[::-1] for choice in TYPE_CHOICES])

    APPROVED_CHOICES = (
        (10, 'In Progress'),
        (20, 'Approved'),
        (30, 'Rejected'),
    )
    APPROVED_NAMES = dict(APPROVED_CHOICES)
    APPROVED_IDS = dict([choice[::-1] for choice in APPROVED_CHOICES])
    APPROVED_FINISHED_IDS = (20, 30)

    type = models.PositiveIntegerField(choices=TYPE_CHOICES)

    team = models.ForeignKey(Team)
    team_video = models.ForeignKey(TeamVideo)
    language = models.CharField(max_length=16, choices=ALL_LANGUAGES, blank=True,
                                db_index=True)
    assignee = models.ForeignKey(User, blank=True, null=True)
    subtitle_version = models.ForeignKey(SubtitleVersion, blank=True, null=True)

    deleted = models.BooleanField(default=False)

    public = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)
    completed = models.DateTimeField(blank=True, null=True)
    expiration_date = models.DateTimeField(blank=True, null=True)

    # Review and Approval -specific fields
    approved = models.PositiveIntegerField(choices=APPROVED_CHOICES,
                                           null=True, blank=True)
    body = models.TextField(blank=True, default="")

    objects = TaskManager()

    def __unicode__(self):
        return u'Task %s (%s) for %s' % (self.id or "unsaved",
                                         self.get_type_display(),
                                         self.team_video)


    @property
    def workflow(self):
        '''Return the most specific workflow for this task's TeamVideo.'''
        return Workflow.get_for_team_video(self.team_video)


    def _add_comment(self):
        """Add a comment on the SubtitleLanguage for this task with the body as content."""
        if self.body.strip():
            lang_ct = ContentType.objects.get_for_model(SubtitleLanguage)
            comment = Comment(
                content=self.body,
                object_pk=self.subtitle_version.language.pk,
                content_type=lang_ct,
                submit_date=self.completed,
                user=self.assignee,
            )
            comment.save()
            notifier.send_video_comment_notification(comment.pk,
                                    version=self.subtitle_version.pk)

    def future(self):
        """Return whether this task expires in the future."""
        return self.expiration_date > datetime.datetime.now()

    def get_widget_url(self):
        """Return a URL for whatever dialog is used to perform this task."""
        mode = Task.TYPE_NAMES[self.type].lower()
        if self.subtitle_version:
            base_url = self.subtitle_version.language.get_widget_url(mode, self.pk)
        else:
            video = self.team_video.video
            if self.language and video.subtitle_language(self.language):
                lang = video.subtitle_language(self.language)
                base_url = reverse("videos:translation_history", kwargs={
                    "video_id": video.video_id,
                    "lang": lang.language,
                    "lang_id": lang.pk,
                })
            else:
                # subtitle tasks might not have a language
                base_url = video.get_absolute_url()
        return base_url + "?t=%s" % self.pk


    def _set_version_moderation_status(self):
        """Set this task's subtitle_version's moderation_status to the appropriate value.

        This assumes that this task is an Approve/Review task, and that the
        approved field is set to Approved or Rejected.

        """
        assert self.get_type_display() in ('Approve', 'Review'), \
               "Tried to set version moderation status from a non-review/approval task."

        assert self.get_approved_display() in ('Approved', 'Rejected'), \
               "Tried to set version moderation status from an un-ruled-upon task."

        if self.approved == Task.APPROVED_IDS['Approved']:
            self.subtitle_version.moderation_status = MODERATION.APPROVED
        else:
            self.subtitle_version.moderation_status = MODERATION.REJECTED

        self.subtitle_version.save()

    def _send_back(self, sends_notification=True):
        """Handle "rejection" of this task.

        This will:

        * Create a new task with the appropriate type (translate or subtitle).
        * Try to reassign it to the previous assignee, leaving it unassigned
          if that's not possible.
        * Send a notification unless sends_notification is given as False.

        NOTE: This function does not modify the *current* task in any way.

        """
        previous_task = Task.objects.complete().filter(
            team_video=self.team_video, language=self.language, team=self.team,
            type__in=(Task.TYPE_IDS['Subtitle'], Task.TYPE_IDS['Translate'])
        ).order_by('-completed')[:1]

        if previous_task:
            assignee = previous_task[0].assignee
        else:
            assignee = None

        if self.subtitle_version.language.is_original:
            type = Task.TYPE_IDS['Subtitle']
        else:
            type = Task.TYPE_IDS['Translate']

        task = Task(team=self.team, team_video=self.team_video,
                    subtitle_version=self.subtitle_version,
                    language=self.language, type=type, assignee=assignee)
        task.save()

        if sends_notification:
            # notify original submiter (assignee of self)
            notifier.reviewed_and_sent_back.delay(self.pk)


    def complete(self):
        '''Mark as complete and return the next task in the process if applicable.'''
        self.completed = datetime.datetime.now()
        self.save()

        return { 'Subtitle': self._complete_subtitle,
                 'Translate': self._complete_translate,
                 'Review': self._complete_review,
                 'Approve': self._complete_approve,
        }[Task.TYPE_NAMES[self.type]]()

    def _complete_subtitle(self):
        """Handle the messy details of completing a subtitle task."""
        subtitle_version = self.team_video.video.latest_version(public_only=False)

        if self.workflow.review_enabled:
            task = Task(team=self.team, team_video=self.team_video,
                        subtitle_version=subtitle_version,
                        language=self.language, type=Task.TYPE_IDS['Review'])
            task.save()
        elif self.workflow.approve_enabled:
            task = Task(team=self.team, team_video=self.team_video,
                        subtitle_version=subtitle_version,
                        language=self.language, type=Task.TYPE_IDS['Approve'])
            task.save()
        else:
            # Subtitle task is done, and there is no approval or review
            # required, so we mark the version as approved.
            subtitle_version.moderation_status = MODERATION.APPROVED
            subtitle_version.save()

            # We need to make sure this is updated correctly here.
            from apps.videos import metadata_manager
            metadata_manager.update_metadata(self.team_video.video.pk)

            if self.workflow.autocreate_translate:
                _create_translation_tasks(self.team_video, self.subtitle_version)

    def _complete_translate(self):
        """Handle the messy details of completing a translate task."""
        subtitle_version = self.team_video.video.latest_version(language_code=self.language, public_only=False)

        if self.workflow.review_enabled:
            task = Task(team=self.team, team_video=self.team_video,
                        subtitle_version=subtitle_version,
                        language=self.language, type=Task.TYPE_IDS['Review'])
            task.save()
        elif self.workflow.approve_enabled:
            # The review step may be disabled.  If so, we check the approve step.
            task = Task(team=self.team, team_video=self.team_video,
                        subtitle_version=subtitle_version,
                        language=self.language, type=Task.TYPE_IDS['Approve'])
            task.save()
        else:
            # Translation task is done, and there is no approval or review
            # required, so we mark the version as approved.
            subtitle_version.moderation_status = MODERATION.APPROVED
            subtitle_version.save()

            # We need to make sure this is updated correctly here.
            from apps.videos import metadata_manager
            metadata_manager.update_metadata(self.team_video.video.pk)

            task = None

        return task

    def _complete_review(self):
        """Handle the messy details of completing a review task."""
        self._add_comment()

        task = None
        if self.workflow.approve_enabled:
            # Approval is enabled, so if the reviewer thought these subtitles
            # were good we create the next task.
            if self.approved == Task.APPROVED_IDS['Approved']:
                task = Task(team=self.team, team_video=self.team_video,
                            subtitle_version=self.subtitle_version,
                            language=self.language, type=Task.TYPE_IDS['Approve'])
                task.save()
                # approval review
                notifier.reviewed_and_pending_approval.delay(self.pk)
            else:
                # The reviewer rejected this version, so it should be explicitly
                # made non-public.
                self._set_version_moderation_status()

                # Send the subtitles back for improvement.
                self._send_back()
        else:
            # Approval isn't enabled, so the ruling of this Review task
            # determines whether the subtitles go public.
            self._set_version_moderation_status()

            if self.approved == Task.APPROVED_IDS['Approved']:
                # If the subtitles are okay, go ahead and autocreate translation
                # tasks if necessary.
                if self.workflow.autocreate_translate:
                    _create_translation_tasks(self.team_video, self.subtitle_version)

                # non approval review
                notifier.reviewed_and_published.delay(self.pk)
            else:
                # Send the subtitles back for improvement.
                self._send_back()

        return task

    def _complete_approve(self):
        """Handle the messy details of completing an approve task."""
        self._add_comment()

        # If we manage to get here, the ruling on this Approve task determines
        # whether the subtitles should go public.
        self._set_version_moderation_status()

        # If the subtitles are okay, go ahead and autocreate translation tasks.
        is_ok = self.approved == Task.APPROVED_IDS['Approved']
        if is_ok:
            # But only if we haven't already.
            if self.workflow.autocreate_translate:
                _create_translation_tasks(self.team_video, self.subtitle_version)
        else:
            # Send the subtitles back for improvement.
            self._send_back(sends_notification=False)
        notifier.approved_notification.delay(self.pk, is_ok)


    def get_perform_url(self):
        '''Return the URL that will open whichever dialog is necessary to perform this task.'''
        mode = Task.TYPE_NAMES[self.type].lower()
        if self.subtitle_version:
            base_url = self.subtitle_version.language.get_widget_url(mode, self.pk)
        else:
            video = self.team_video.video
            if self.language and video.subtitle_language(self.language) :
                lang = video.subtitle_language(self.language)
                base_url = reverse("videos:translation_history", kwargs={
                    "video_id": video.video_id,
                    "lang": lang.language,
                    "lang_id": lang.pk,
                })
            else:
                # subtitle tasks might not have a language
                base_url = video.get_absolute_url()
        return base_url+  "?t=%s" % self.pk

    def get_reviewer(self):
        if self.type == 40:
            previous = Task.objects.complete().filter(
                team_video=self.team_video,
                language=self.language,
                team=self.team,
                type=Task.TYPE_IDS['Review']).order_by('-completed')[:1]

            if previous:
                reviewer = previous[0].assignee
            else:
                reviewer = None

            return reviewer

    def set_expiration(self):
        """Set the expiration_date of this task.  Does not save().

        Requires that self.team and self.assignee be set correctly.

        """
        if not self.team.task_expiration or not self.assignee:
            self.expiration_date = None
        else:
            limit = datetime.timedelta(days=self.team.task_expiration)
            self.expiration_date = datetime.datetime.now() + limit


    def save(self, update_team_video_index=True, *args, **kwargs):
        result = super(Task, self).save(*args, **kwargs)
        if update_team_video_index:
            update_one_team_video.delay(self.team_video.pk)
        return result


def task_moderate_version(sender, instance, created, **kwargs):
    """If we create a review or approval task for this subtitle_version, mark it.

    It *must* be awaiting moderation if we've just created one of these tasks
    (and it's not a pre-completed task).

    """
    if created and instance.subtitle_version:
        if instance.type in (Task.TYPE_IDS['Review'], Task.TYPE_IDS['Approve']):
            if not instance.completed:
                instance.subtitle_version.moderation_status = WAITING_MODERATION
                instance.subtitle_version.save()

post_save.connect(task_moderate_version, Task,
                  dispatch_uid="teams.task.task_moderate_version")


# Settings
class SettingManager(models.Manager):
    use_for_related_fields = True

    def guidelines(self):
        """Return a QS of settings related to team guidelines."""
        keys = [key for key, name in Setting.KEY_CHOICES
                if name.startswith('guidelines_')]
        return self.get_query_set().filter(key__in=keys)

    def messages(self):
        """Return a QS of settings related to team messages."""
        keys = [key for key, name in Setting.KEY_CHOICES
                if name.startswith('messages_')]
        return self.get_query_set().filter(key__in=keys)

    def messages_guidelines(self):
        """Return a QS of settings related to team messages or guidelines."""
        keys = [key for key, name in Setting.KEY_CHOICES
                if name.startswith('messages_') or name.startswith('guidelines_')]
        return self.get_query_set().filter(key__in=keys)

class Setting(models.Model):
    KEY_CHOICES = (
        (100, 'messages_invite'),
        (101, 'messages_manager'),
        (102, 'messages_admin'),
        (103, 'messages_application'),
        (200, 'guidelines_subtitle'),
        (201, 'guidelines_translate'),
        (202, 'guidelines_review'),
    )
    KEY_NAMES = dict(KEY_CHOICES)
    KEY_IDS = dict([choice[::-1] for choice in KEY_CHOICES])

    key = models.PositiveIntegerField(choices=KEY_CHOICES)
    data = models.TextField(blank=True)
    team = models.ForeignKey(Team, related_name='settings')

    created = models.DateTimeField(auto_now_add=True, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)

    objects = SettingManager()

    class Meta:
        unique_together = (('key', 'team'),)

    def __unicode__(self):
        return u'%s - %s' % (self.team, self.key_name)

    @property
    def key_name(self):
        """Return the key name for this setting.

        TODO: Remove this and replace with get_key_display()?

        """
        return Setting.KEY_NAMES[self.key]


# TeamLanguagePreferences
class TeamLanguagePreferenceManager(models.Manager):
    def _generate_writable(self, team):
        """Return the set of language codes that are writeable for this team."""
        langs_set = set([x[0] for x in settings.ALL_LANGUAGES])

        unwritable = self.for_team(team).filter(allow_writes=False, preferred=False).values("language_code")
        unwritable = set([x['language_code'] for x in unwritable])

        return langs_set - unwritable

    def _generate_readable(self, team):
        """Return the set of language codes that are readable for this team."""
        langs = set([x[0] for x in settings.ALL_LANGUAGES])

        unreadable = self.for_team(team).filter(allow_reads=False, preferred=False).values("language_code")
        unreadable = set([x['language_code'] for x in unreadable])

        return langs - unreadable

    def _generate_preferred(self, team):
        """Return the set of language codes that are preferred for this team."""
        preferred = self.for_team(team).filter(preferred=True).values("language_code")
        return set([x['language_code'] for x in preferred])


    def for_team(self, team):
        """Return a QS of all language preferences for the given team."""
        return self.get_query_set().filter(team=team)

    def on_changed(cls, sender,  instance, *args, **kwargs):
        """Perform any necessary actions when a language preference changes.

        TODO: Refactor this out of the manager...

        """
        from teams.cache import invalidate_lang_preferences
        invalidate_lang_preferences(instance.team)


    def get_readable(self, team):
        """Return the set of language codes that are readable for this team.

        This value may come from memcache if possible.

        """
        from teams.cache import get_readable_langs
        return get_readable_langs(team)

    def get_writable(self, team):
        """Return the set of language codes that are writeable for this team.

        This value may come from memcache if possible.

        """
        from teams.cache import get_writable_langs
        return get_writable_langs(team)

    def get_preferred(self, team):
        """Return the set of language codes that are preferred for this team.

        This value may come from memcache if possible.

        """
        from teams.cache import get_preferred_langs
        return get_preferred_langs(team)

class TeamLanguagePreference(models.Model):
    """Represent language preferences for a given team.

    First, TLPs may mark a language as "preferred".  If that's the case then the
    other attributes of this model are irrelevant and can be ignored.
    "Preferred" languages will have translation tasks automatically created for
    them when subtitles are added.

    If preferred is False, the TLP describes a *restriction* on the language
    instead.  Writing in that language may be prevented, or both reading and
    writing may be prevented.

    (Note: "writing" means not only writing new subtitles but also creating
    tasks, etc)

    This is how the restriction settings should interact.  TLP means that we
    have created a TeamLanguagePreference for that team and language.

    | Action                                 | NO  | allow_read=True,  | allow_read=False, |
    |                                        | TLP | allow_write=False | allow_write=False |
    ========================================================================================
    | assignable as tasks                    | X   |                   |                   |
    | assignable as narrowing                | X   |                   |                   |
    | listed on the widget for viewing       | X   | X                 |                   |
    | listed on the widget for improving     | X   |                   |                   |
    | returned from the api read operations  | X   | X                 |                   |
    | upload / write operations from the api | X   |                   |                   |
    | show up on the start dialog            | X   |                   |                   |
    +----------------------------------------+-----+-------------------+-------------------+

    Remember, this table only applies if preferred=False.  If the language is
    preferred the "restriction" attributes are effectively garbage.  Maybe we
    should make the column nullable to make this more clear?

    allow_read=True, allow_write=True, preferred=False is invalid.  Just remove
    the row all together.

    """
    team = models.ForeignKey(Team, related_name="lang_preferences")
    language_code = models.CharField(max_length=16)

    allow_reads = models.BooleanField()
    allow_writes = models.BooleanField()
    preferred = models.BooleanField(default=False)

    objects = TeamLanguagePreferenceManager()

    class Meta:
        unique_together = ('team', 'language_code')


    def clean(self, *args, **kwargs):
        if self.allow_reads and self.allow_writes:
            raise ValidationError("No sense in having all allowed, just remove the preference for this language.")

        if self.preferred and (self.allow_reads or self.allow_writes):
            raise ValidationError("Cannot restrict a preferred language.")

        super(TeamLanguagePreference, self).clean(*args, **kwargs)

    def __unicode__(self):
        return u"%s preference for team %s" % (self.language_code, self.team)


post_save.connect(TeamLanguagePreference.objects.on_changed, TeamLanguagePreference)


# TeamNotificationSettings
class TeamNotificationSettingManager(models.Manager):
    def notify_team(self, team_pk, video_id, event_name, language_pk=None, version_pk=None):
        """Notify the given team of a given event.

        Finds the matching notification settings for this team, instantiates
        the notifier class, and sends the appropriate notification.

        If the notification settings has an email target, sends an email.

        If the http settings are filled, then sends the request.

        This can be ran as a Celery task, as it requires no objects to be passed.

        """
        try:
            notification_settings = self.get(team__id=team_pk)
        except TeamNotificationSetting.DoesNotExist:
            return
        notification_settings.notify(Video.objects.get(video_id=video_id), event_name,
                                                 language_pk, version_pk)

class TeamNotificationSetting(models.Model):
    """Info on how a team should be notified of changes to its videos.

    For now, a team can be notified by having a http request sent with the
    payload as the notification information.  This cannot be hardcoded since
    teams might have different urls for each environment.

    Some teams have strict requirements on mapping video ids to their internal
    values, and also their own language codes. Therefore we need to configure
    a class that can do the correct mapping.

    TODO: allow email notifications

    """
    EVENT_VIDEO_NEW = "video-new"
    EVENT_VIDEO_EDITED = "video-edited"
    EVENT_LANGUAGE_NEW = "language-new"
    EVENT_LANGUAGE_EDITED = "language-edit"
    EVENT_SUBTITLE_NEW = "subs-new"
    EVENT_SUBTITLE_APPROVED = "subs-approved"
    EVENT_SUBTITLE_REJECTED = "subs-rejected"

    team = models.OneToOneField(Team, related_name="notification_settings")

    # the url to post the callback notifing partners of new video activity
    request_url = models.URLField(blank=True, null=True)
    basic_auth_username = models.CharField(max_length=255, blank=True, null=True)
    basic_auth_password = models.CharField(max_length=255, blank=True, null=True)

    # not being used, here to avoid extra migrations in the future
    email = models.EmailField(blank=True, null=True)

    # integers mapping to classes, see unisubs-integration/notificationsclasses.py
    notification_class = models.IntegerField(default=1,)

    objects = TeamNotificationSettingManager()

    def get_notification_class(self):
        # move this import to the module level and test_settings break. Fun.
        import sentry_logger
        logger = sentry_logger.logging.getLogger("teams.models")
        try:
            from notificationclasses import NOTIFICATION_CLASS_MAP

            return NOTIFICATION_CLASS_MAP[self.notification_class]
        except ImportError:
            logger.exception("Apparently unisubs-integration is not installed")


    def notify(self, video, event_name, language_pk=None, version_pk=None):
        """Resolve the notification class for this setting and fires notfications."""
        notification = self.get_notification_class()(
            self.team, video, event_name, language_pk, version_pk)
        if self.request_url:
            success, content = notification.send_http_request(
                self.request_url,
                self.basic_auth_username,
                self.basic_auth_password
            )
            return success, content
        # FIXME: spec and test this, for now just return
        return
        if self.email:
            notification.send_email(self.email, self.team, video, event_name, language_pk)

    def __unicode__(self):
        return u'NotificationSettings for team %s' % (self.team)

