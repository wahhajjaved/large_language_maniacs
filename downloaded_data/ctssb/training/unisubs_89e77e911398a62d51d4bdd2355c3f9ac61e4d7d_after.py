# -*- coding: utf-8 -*-
from apps.webdriver_testing.webdriver_base import WebdriverTestCase
import datetime
import os
from apps.webdriver_testing import data_helpers
from apps.webdriver_testing.pages.editor_pages import subtitle_editor 
from apps.webdriver_testing.pages.site_pages.teams import dashboard_tab
from apps.webdriver_testing.data_factories import TeamMemberFactory
from apps.webdriver_testing.data_factories import TeamVideoFactory
from apps.webdriver_testing.data_factories import TaskFactory
from apps.webdriver_testing.data_factories import TeamContributorMemberFactory
from apps.webdriver_testing.data_factories import TeamManagerMemberFactory
from apps.webdriver_testing.data_factories import TeamLangPrefFactory
from apps.webdriver_testing.data_factories import WorkflowFactory
from apps.webdriver_testing.data_factories import UserFactory
from apps.webdriver_testing.data_factories import UserLangFactory
from apps.webdriver_testing.pages.editor_pages import dialogs
from subtitles.models import SubtitleVersion

class TestCaseTaskFreeDashboard(WebdriverTestCase):
    """Test suite for display of Team dashboard when there are no tasks.  """
    NEW_BROWSER_PER_TEST_CASE = False

    @classmethod
    def setUpClass(cls):
        super(TestCaseTaskFreeDashboard, cls).setUpClass()

        cls.data_utils = data_helpers.DataHelpers()
        cls.dashboard_tab = dashboard_tab.DashboardTab(cls)

        cls.logger.info('setup: Create a team and team owner, add some videos')
        cls.team_owner = UserFactory()
        cls.team = TeamMemberFactory.create(user = cls.team_owner,).team
        #Add some videos with various languages required.
        test_videos = [('jaws.mp4', 'fr', 'fr'),
                       ('Birds_short.oggtheora.ogg', None, None),
                       ('fireplace.mp4', 'en', 'en')
                       ]
        for vid in test_videos:
            vidurl_data = {'url': ('http://qa.pculture.org/amara_tests/%s' 
                                   % vid[0]),
                           'video__title': vid[0]}
            video = cls.data_utils.create_video(**vidurl_data)
            if vid[1] is not None:
                video_data = {'language_code': vid[1],
                              'video_language': vid[2],
                              'video': video.pk,
                              'draft': open('apps/videos/fixtures/test.srt'),
                              'is_complete': True
                              }
                cls.data_utils.upload_subs(video, video_data)

            TeamVideoFactory(video = video,
                             team = cls.team,
                             added_by = cls.team_owner)

        cls.logger.info('setup: Create team members Polly Glott and Mono Glot.')
        cls.polly_glott = TeamContributorMemberFactory.create(
                team = cls.team,
                user = UserFactory(username =  'PollyGlott')
                ).user
        cls.mono_glot = TeamContributorMemberFactory.create(
                team = cls.team,
                user = UserFactory(username =  'MonoGlot')
                ).user

    def setUp(self):
        self.dashboard_tab.open_team_page(self.team.slug)


    def test_members__generic_create_subs(self):
        """Dashboard displays generic create subs message when no orig lang specified.

        """
        #Create a user that's a member of a team with language preferences set.

        polly_speaks = ['en', 'cs', 'ru', 'ar']
        for lang in polly_speaks:
            UserLangFactory(user = self.polly_glott,
                            language = lang)
        #Login user and go to team dashboard page
        self.dashboard_tab.log_in(self.polly_glott.username, 'password')

        #Verify expected videos are displayed.
        self.dashboard_tab.open_team_page(self.team.slug)
        langs = self.dashboard_tab.languages_needed('Birds_short')
        self.assertEqual(['Create Subtitles'], langs)

    def test_members__no_languages(self):
        """Dashboard displays Create Subtitles when member has no langs specified.

        """
        #Create a user that's a member of a team with language preferences set.
        #Login user and go to team dashboard page
        self.dashboard_tab.log_in(self.mono_glot.username, 'password')

        #Verify expected videos are displayed.
        self.dashboard_tab.open_team_page(self.team.slug)
        langs = self.dashboard_tab.languages_needed('jaws')
        self.assertEqual(['Create Subtitles'], langs)



    def test_members__specific_langs_needed(self):
        """Dashboard displays videos matching members language preferences.     

        """
        #Create a user that's a member of a team with language preferences set.
        polly_speaks = ['en', 'cs', 'ru', 'ar']
        for lang in polly_speaks:
            UserLangFactory(user = self.polly_glott,
                            language = lang)
        #Login user and go to team dashboard page
        self.dashboard_tab.log_in(self.polly_glott.username, 'password')

        #Verify expected videos are displayed.
        expected_lang_list = ['Create English Subtitles', 
                              'Create Czech Subtitles',
                              'Create Russian Subtitles',
                              'Create Arabic Subtitles']
        self.dashboard_tab.open_team_page(self.team.slug)
        langs = self.dashboard_tab.languages_needed('fireplace.mp4')
        self.assertEqual(sorted(langs), sorted(expected_lang_list))

    def test_add_suggestion__displayed(self):
        """Add videos link displays for user with permissions, when no videos found.

        """
        test_team = TeamMemberFactory.create(team__name='Admin Manager Video Policy',
                                             team__slug='video-policy-2',
                                             user = self.team_owner,
                                             team__video_policy=2, 
                                             ).team
        self.dashboard_tab.log_in(self.team_owner.username, 'password')
        self.dashboard_tab.open_team_page(test_team.slug)
        self.assertTrue(self.dashboard_tab.suggestion_present(suggestion_type='add'))

    def test_add_suggestion__not_displayed(self):
        """Add videos link not displayed for user with no permissions, when no videos
          found.

        """
        test_team = TeamMemberFactory.create(team__name='Admin Manager Video Policy',
                                             team__slug='video-policy-2',
                                             team__video_policy=2,
                                             user=self.team_owner,
                                             ).team
        team_member = TeamContributorMemberFactory.create(
                team = test_team,
                user = UserFactory(username='NoAddEd')
                ).user
        self.dashboard_tab.log_in(team_member.username, 'password')
        self.dashboard_tab.open_team_page(test_team.slug)
        self.assertFalse(self.dashboard_tab.suggestion_present(suggestion_type='add'))

    def test_lang_suggestion__displayed(self):
        """Update preferred languages displayed, when no videos found.

        """
        
        test_team = TeamMemberFactory.create(team__name='No Videos yet',
                                             team__slug='no-videos',
                                             user=self.team_owner,
                                             ).team
        TeamContributorMemberFactory.create(
                team = test_team,
                user = self.mono_glot)
        self.dashboard_tab.log_in(self.mono_glot.username, 'password')
        self.dashboard_tab.open_team_page(test_team.slug)
        self.assertTrue(self.dashboard_tab.suggestion_present(
                             suggestion_type='language'))

    def test_browse_suggestion__displayed(self):
        """Browse videos link displayed, when no videos found.

        """
        test_team = TeamMemberFactory.create(team__name='No Videos yet',
                                             team__slug='no-videos',
                                             user=self.team_owner,
                                             ).team
        TeamContributorMemberFactory.create(
                team = test_team,
                user = self.mono_glot)

        self.dashboard_tab.log_in(self.mono_glot.username, 'password')
        self.dashboard_tab.open_team_page(test_team.slug)
        self.assertTrue(self.dashboard_tab.suggestion_present(
                             suggestion_type='browse'))

    def test_no_create__nonmember(self):
        """Non-members see dashboard videos without the option to create subtitles.

        """
        non_member = UserFactory(username = 'NonMember')
        self.dashboard_tab.log_in(non_member.username, 'password')
        self.dashboard_tab.open_team_page(self.team.slug)
        langs = self.dashboard_tab.languages_needed('fireplace.mp4')
        self.assertEqual(langs, None)

    def test_no_create__guest(self):
        """Guests see dashboard videos without the option to create subtitles.

        """
        self.dashboard_tab.log_out()
        self.dashboard_tab.open_team_page(self.team.slug)
        langs = self.dashboard_tab.languages_needed('fireplace.mp4')
        self.assertEqual(langs, None)


class TestCaseTasksEnabledDashboard(WebdriverTestCase):
    """Verify team dashboard displays for teams with tasks enabled.

    """
    NEW_BROWSER_PER_TEST_CASE = False

    @classmethod
    def setUpClass(cls):
        super(TestCaseTasksEnabledDashboard, cls).setUpClass()
        cls.data_utils = data_helpers.DataHelpers()
        cls.sub_editor = subtitle_editor.SubtitleEditor(cls)
        cls.create_modal = dialogs.CreateLanguageSelection(cls)
        cls.dashboard_tab = dashboard_tab.DashboardTab(cls)
        cls.user = UserFactory(username = 'user', is_partner=True)
        cls.data_utils.create_user_api_key(cls.user)
        cls.subs_file = os.path.join(os.path.dirname
                (os.path.abspath(__file__)), 'oneline.txt')

        #Add a team with workflows, tasks and preferred languages
        cls.logger.info('setup: Create a team with tasks enabled')
        cls.team = TeamMemberFactory.create(team__name='Tasks Enabled',
                                            team__slug='tasks-enabled',
                                            team__workflow_enabled=True,
                                            user = cls.user,
                                            ).team
        cls.team_workflow = WorkflowFactory(team = cls.team,
                                            autocreate_subtitle=True,
                                            autocreate_translate=True,
                                           )
        cls.team_workflow.review_allowed = 10
        cls.team_workflow.save()
        cls.logger.info('setup: Add some preferred languages to the team.')
        lang_list = ['en', 'ru', 'pt-br', 'fr', 'de', 'es']
        for language in lang_list:
            TeamLangPrefFactory.create(
                team = cls.team,
                language_code = language,
                preferred = True)

        #Create some users with different roles and languages.
        polly_speaks = ['en', 'fr', 'ru', 'ar']
        cls.logger.info("setup: Create user Polly who speaks: %s" 
                        % polly_speaks)
        cls.polly_glott = TeamContributorMemberFactory.create(
                team = cls.team,
                user = UserFactory(username =  'PollyGlott')
                ).user
        cls.logger.info("setup: Create manager reviewer who speaks: %s" 
                        % polly_speaks)
        cls.reviewer = TeamManagerMemberFactory.create(
                team = cls.team,
                user = UserFactory(username =  'reviewer')
                ).user
        for lang in polly_speaks:
            UserLangFactory(user = cls.polly_glott,
                            language = lang)
            UserLangFactory(user = cls.reviewer,
                            language = lang)

        #Add some videos with various languages required.
        cls.logger.info('setup: Add some videos and set primary audio lang.')
        d = {'url': 'http://qa.pculture.org/amara_tests/Birds_short.mp4',
             'video__title': 'Short Birds MP4', 
             'video__primary_audio_language_code': 'en'}
        cls.non_team_video = cls.data_utils.create_video(**d)
        test_videos = [('jaws.mp4', 'fr'),
                       ('Birds_short.oggtheora.ogg', 'de'),
                       ('fireplace.mp4', 'en'),
                       ('penguins.webm', None),
                       ('trailer.webm', 'en')
                       ]
        cls.vid_obj_list = []
        for vid in test_videos:
            vidurl_data = {'url': 'http://qa.pculture.org/amara_tests/%s' % vid[0],
                           'video__title': vid[0]}

            video = cls.data_utils.create_video(**vidurl_data)
            if vid[1] is not None:
                video.primary_audio_language_code = vid[1]
                video.save()
            cls.vid_obj_list.append(video)
            team_video = TeamVideoFactory(video = video,
                             team = cls.team,
                             added_by = cls.polly_glott)


    def setUp(self):
        super(TestCaseTasksEnabledDashboard, self).setUp()
        self.dashboard_tab.open_team_page(self.team.slug)
        self.dashboard_tab.handle_js_alert(action='accept')

    def test_members__assigned_tasks(self):
        """Members see “Videos you're working on” with  assigned languages.
 
        """
        video = self.data_utils.create_video()
        video.primary_audio_language_code = 'fr'
        video.save()
        tv = TeamVideoFactory(team=self.team, added_by=self.user, video=video)
        task = list(tv.task_set.incomplete_subtitle().filter(language='fr'))[0]
        task.assignee = self.polly_glott
        task.save()

        #Login user and go to team dashboard page
        self.dashboard_tab.log_in(self.polly_glott.username, 'password')

        #Verify expected videos are displayed.
        self.dashboard_tab.open_team_page(self.team.slug)
        self.assertTrue(self.dashboard_tab.dash_task_present(
                            task_type='Create French subtitles',
                            title=video.title))

    def test_members__available_tasks(self):
        """Members see “Videos that need your help” with the relevant tasks.
 
        """
        #Login user and go to team dashboard page
        self.dashboard_tab.log_in(self.polly_glott.username, 'password')

        #Verify expected videos are displayed.
        self.dashboard_tab.open_team_page(self.team.slug)
        expected_lang_list = ['Create English subtitles'] 
        langs = self.dashboard_tab.languages_needed('fireplace.mp4')
        self.assertEqual(sorted(langs), sorted(expected_lang_list))


    def test_no_langs__available_tasks(self):
        """Members with no lang prefs the list of available tasks in English.

        """
        mono_glot = TeamContributorMemberFactory.create(
                team = self.team,
                user = UserFactory()
                ).user
        video = self.data_utils.create_video()
        video.primary_audio_language_code = 'fr'
        video.save()
        tv = TeamVideoFactory(team=self.team, added_by=self.user, video=video)
        task = list(tv.task_set.incomplete_subtitle().filter(language='fr'))[0]
        task.assignee = mono_glot
        task.save()

        #Login user and go to team dashboard page
        self.dashboard_tab.log_in(mono_glot.username, 'password')
        self.dashboard_tab.open_team_page(self.team.slug)
        expected_lang_list = ['Create English subtitles'] 
        langs = self.dashboard_tab.languages_needed('fireplace.mp4')
        self.assertEqual(sorted(langs), sorted(expected_lang_list))


    def test_start__subtitles(self):
        """Member starts subtitling from dash, “Videos that need your help”.

        """

        video = self.data_utils.create_video()
        video.primary_audio_language_code = 'fr'
        video.save()
        TeamVideoFactory(team=self.team, added_by=self.user, video=video)
        self.create_modal = dialogs.CreateLanguageSelection(self)
        #Login user and go to team dashboard page
        self.logger.info('Polly Glott logs in and goes to team dashboard page.')
        self.dashboard_tab.log_in(self.polly_glott.username, 'password')
        self.dashboard_tab.set_skiphowto()
        self.dashboard_tab.open_team_page(self.team.slug)
        self.dashboard_tab.click_lang_task(video.title, 
                                          'Create French subtitles')
        self.create_modal.lang_selection()
        self.assertEqual('Typing', self.sub_editor.dialog_title())


    def test_start__translation(self):
        """Member starts translation from any task in “Videos that need your
           help”.

        """
        self.logger.info('setup: Setting task policy to all team members')
        self.team.task_assign_policy=20
        self.team.video_policy=1
        self.team.save()
        video = self.non_team_video
        self.data_utils.upload_subs(video)     
        tv = TeamVideoFactory(video = video,
                              team = self.team,
                              added_by = self.polly_glott)
        self.create_modal = dialogs.CreateLanguageSelection(self)
        #Login user and go to team dashboard page
        self.logger.info('Polly Glott logs in and goes to team dashboard page.')
        self.dashboard_tab.log_in(self.polly_glott.username, 'password')
        self.dashboard_tab.set_skiphowto()

        self.dashboard_tab.open_team_page(self.team.slug)
        self.dashboard_tab.click_lang_task('Short Birds MP4', 
                                           'Translate Russian')
        self.create_modal.lang_selection()
        self.assertEqual('Adding a New Translation', 
                         self.sub_editor.dialog_title())


    def test_start__review(self):
        """Member starts review from any task in “Videos that need your help”.

        """
        self.team_workflow.review_allowed = 10
        self.team_workflow.save()

        self.logger.info('setup: Setting task policy to all team members')
        self.team.task_assign_policy=20
        self.team.video_policy=1
        self.team.save()
        create_modal = dialogs.CreateLanguageSelection(self)

        video = self.data_utils.create_video()
        tv = TeamVideoFactory(team=self.team, added_by=self.user, video=video)
        video_data = {'language_code': 'en',
                      'primary_audio_language_code': 'en',
                      'video': video.pk,
                      'draft': open('apps/webdriver_testing/subtitle_data/'
                              'Timed_text.en.srt'),
                      'is_complete': True, 
                      'complete': 1
                     }
        self.data_utils.upload_subs(
                video,
                data=video_data, 
                user=dict(username=self.user.username, 
                password='password'))


        #Login as reviewer and start the review task.
        self.logger.info('Log in as user review to perform the review task.')
        self.dashboard_tab.log_in(self.reviewer.username, 'password')
        self.dashboard_tab.open_team_page(self.team.slug)
        self.logger.info("Clicking the Review English subtitles task")
        self.dashboard_tab.click_lang_task(video.title, 'Review English subtitles')
        self.assertEqual('Review subtitles', self.sub_editor.dialog_title())




class TestCaseLangSuggestion(WebdriverTestCase):
    """These dashboard tests need a fresh browser instance to run.
    """
    NEW_BROWSER_PER_TEST_CASE = True

    def setUp(self):
        super(TestCaseLangSuggestion, self).setUp()
        self.data_utils = data_helpers.DataHelpers()
        self.sub_editor = subtitle_editor.SubtitleEditor(self)
        self.create_modal = dialogs.CreateLanguageSelection(self)
        self.dashboard_tab = dashboard_tab.DashboardTab(self)
        self.user = UserFactory(username = 'user', is_partner=True)
        self.data_utils.create_user_api_key(self.user)

        #Add a team with workflows, tasks and preferred languages
        self.logger.info('setup: Create a team with tasks enabled')
        self.team = TeamMemberFactory.create(team__name='Tasks Enabled',
                                            team__slug='tasks-enabled',
                                            team__workflow_enabled=True,
                                            user = self.user,
                                            ).team
        self.team_workflow = WorkflowFactory(team = self.team,
                                            autocreate_subtitle=True,
                                            autocreate_translate=True,
                                           )
        self.team_workflow.review_allowed = 10
        self.team_workflow.save()
        self.logger.info('setup: Add some preferred languages to the team.')
        lang_list = ['en', 'ru', 'pt-br', 'fr', 'de', 'es']
        for language in lang_list:
            TeamLangPrefFactory.create(
                team = self.team,
                language_code = language,
                preferred = True)

        #Add some videos with various languages required.
        self.logger.info('setup: Add some videos and set primary audio lang.')
        d = {'url': 'http://qa.pculture.org/amara_tests/Birds_short.mp4',
             'video__title': 'Short Birds MP4', 
             'video__primary_audio_language_code': 'en'}
        self.non_team_video = self.data_utils.create_video(**d)
        test_videos = [('jaws.mp4', 'fr'),
                       ('trailer.webm', 'en')
                       ]
        self.vid_obj_list = []
        for vid in test_videos:
            vidurl_data = {'url': ('http://qa.pculture.org/amara_tests/%s' 
                                  % vid[0]),
                           'video__title': vid[0]}

            video = self.data_utils.create_video(**vidurl_data)
            if vid[1] is not None:
                video.primary_audio_language_code = vid[1]
                video.save()
            self.vid_obj_list.append(video)
            team_video = TeamVideoFactory(video = video,
                             team = self.team,
                             added_by = self.user)

    def get_task(self, video_id, team, task_type, lang):
        """Return the tasks give a video id, and language via the api.
 
        """
        url_part = 'teams/{0}/tasks?video_id={1}'.format(
            team.slug, video_id)
        status, response = self.data_utils.api_get_request(self.user, url_part) 
        task_objects =  response['objects']
        for task in task_objects:
            if task['type'] == task_type and task['language'] == lang:
                return task

    def test_member__language_suggestion(self):
        """Members with no lang pref see the prompt to set language preference.

        """
        mono_glot = TeamContributorMemberFactory.create(
                team = self.team,
                user = UserFactory()
                ).user
        self.dashboard_tab.open_team_page(self.team.slug)
        self.browser.delete_all_cookies()
        self.dashboard_tab.log_in(mono_glot.username, 'password')

        self.logger.info('Subtitle task for jaws video is assigned to Mono '
                         'Glot via api.')
        jaws_vid = self.vid_obj_list[0]  #see setUp for data details.
        task_resp = self.get_task(jaws_vid.video_id, self.team, 'Subtitle', 'fr')
        url_part = task_resp['resource_uri'] 
        updated_info = {'assignee': mono_glot.username} 
        status, response = self.data_utils.put_api_request(self.user, url_part, 
            updated_info)

        self.dashboard_tab.open_team_page(self.team.slug)
        self.assertTrue(self.dashboard_tab.suggestion_present(
                             suggestion_type='authed_language'))
