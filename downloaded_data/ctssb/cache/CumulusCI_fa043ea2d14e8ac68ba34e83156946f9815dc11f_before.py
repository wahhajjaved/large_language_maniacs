import datetime
import httplib
import json
import os
import unittest

import responses

from release_notes.generator import BaseReleaseNotesGenerator
from release_notes.generator import StaticReleaseNotesGenerator
from release_notes.generator import DirectoryReleaseNotesGenerator
from release_notes.generator import GithubReleaseNotesGenerator
from release_notes.generator import PublishingGithubReleaseNotesGenerator
from release_notes.parser import BaseChangeNotesParser
from release_notes.tests.util_github_api import GithubApiTestMixin

__location__ = os.path.split(os.path.realpath(__file__))[0]


class DummyParser(BaseChangeNotesParser):

    def parse(self, change_note):
        pass

    def _render(self):
        return 'dummy parser output'.format(self.title)


class TestBaseReleaseNotesGenerator(unittest.TestCase):

    def test_render_no_parsers(self):
        release_notes = BaseReleaseNotesGenerator()
        content = release_notes.render()
        self.assertEqual(content, '')

    def test_render_dummy_parsers(self):
        release_notes = BaseReleaseNotesGenerator()
        release_notes.parsers.append(DummyParser('Dummy 1'))
        release_notes.parsers.append(DummyParser('Dummy 2'))
        expected = u'# Dummy 1\r\n\r\ndummy parser output\r\n\r\n' +\
                   u'# Dummy 2\r\n\r\ndummy parser output'
        self.assertEqual(release_notes.render(), expected)


class TestStaticReleaseNotesGenerator(unittest.TestCase):

    def test_init_parser(self):
        release_notes = StaticReleaseNotesGenerator([])
        assert len(release_notes.parsers) == 3


class TestDirectoryReleaseNotesGenerator(unittest.TestCase):

    def test_init_parser(self):
        release_notes = DirectoryReleaseNotesGenerator('change_notes')
        assert len(release_notes.parsers) == 3

    def test_full_content(self):
        change_notes_dir = os.path.join(
            __location__,
            'change_notes',
            'full',
        )
        release_notes = DirectoryReleaseNotesGenerator(
            change_notes_dir,
        )

        content = release_notes()
        expected = "# Critical Changes\r\n\r\n* This will break everything!\r\n\r\n# Changes\r\n\r\nHere's something I did. It was really cool\r\nOh yeah I did something else too!\r\n\r\n# Issues Closed\r\n\r\n#2345\r\n#6236"
        print expected
        print '-------------------------------------'
        print content

        self.assertEqual(content, expected)


class TestGithubReleaseNotesGenerator(unittest.TestCase):

    def setUp(self):
        self.current_tag = 'prod/1.4'
        self.last_tag = 'prod/1.3'
        self.github_info = {
            'github_owner': 'TestOwner',
            'github_repo': 'TestRepo',
            'github_username': 'TestUser',
            'github_password': 'TestPass',
        }

    def test_init_without_last_tag(self):
        github_info = self.github_info.copy()
        generator = GithubReleaseNotesGenerator(github_info, self.current_tag)
        self.assertEqual(generator.github_info, github_info)
        self.assertEqual(generator.current_tag, self.current_tag)
        self.assertEqual(generator.last_tag, None)
        self.assertEqual(generator.change_notes.current_tag, self.current_tag)
        self.assertEqual(generator.change_notes._last_tag, None)

    def test_init_with_last_tag(self):
        github_info = self.github_info.copy()
        generator = GithubReleaseNotesGenerator(
            github_info, self.current_tag, self.last_tag)
        self.assertEqual(generator.github_info, github_info)
        self.assertEqual(generator.current_tag, self.current_tag)
        self.assertEqual(generator.last_tag, self.last_tag)
        self.assertEqual(generator.change_notes.current_tag, self.current_tag)
        self.assertEqual(generator.change_notes._last_tag, self.last_tag)


class TestPublishingGithubReleaseNotesGenerator(unittest.TestCase, GithubApiTestMixin):

    def setUp(self):
        self.init_github()
        self.github_info = {
            'github_owner': 'TestOwner',
            'github_repo': 'TestRepo',
            'github_username': 'TestUser',
            'github_password': 'TestPass',
        }

    @responses.activate
    def test_publish_beta_new(self):

        current_tag = 'beta/1.4-Beta_1'

        # mock the attempted GET of non-existent release
        api_url = '{}/releases/tags/{}'.format(self.repo_api_url, current_tag)
        expected_response = self._get_expected_not_found()
        responses.add(
            method=responses.GET,
            url=api_url,
            json=expected_response,
            status=httplib.NOT_FOUND,
        )

        # mock the release creation
        api_url = '{}/releases'.format(self.repo_api_url)
        expected_response = self._get_expected_release(None, False, True)
        responses.add(
            method=responses.POST,
            url=api_url,
            json=expected_response,
        )

        generator = self._create_generator(current_tag)

        # inject content into the Changes parser
        generator.parsers[1].content.append('foo')
        content = generator.render()
        release_body = generator.publish(content)
        expected_release_body = '# Changes\r\n\r\nfoo'
        body = json.loads(responses.calls._calls[1].request.body)
        self.assertEqual(release_body, expected_release_body)
        self.assertEqual(body['prerelease'], True)
        self.assertEqual(body['draft'], False)
        self.assertEqual(len(responses.calls._calls), 2)

    @responses.activate
    def test_publish_prod_new(self):

        current_tag = 'prod/1.4'

        # mock the attempted GET of non-existent release
        api_url = '{}/releases/tags/{}'.format(self.repo_api_url, current_tag)
        expected_response = self._get_expected_not_found()
        responses.add(
            method=responses.GET,
            url=api_url,
            json=expected_response,
            status=httplib.NOT_FOUND,
        )

        # mock the release creation
        api_url = '{}/releases'.format(self.repo_api_url)
        expected_response = self._get_expected_release(None, False, True)
        responses.add(
            method=responses.POST,
            url=api_url,
            json=expected_response,
        )

        generator = self._create_generator(current_tag)

        # inject content into the Changes parser
        generator.parsers[1].content.append('foo')
        content = generator.render()
        release_body = generator.publish(content)
        expected_release_body = '# Changes\r\n\r\nfoo'
        body = json.loads(responses.calls._calls[1].request.body)
        self.assertEqual(release_body, expected_release_body)
        self.assertEqual(body['prerelease'], False)
        self.assertEqual(body['draft'], True)
        self.assertEqual(len(responses.calls._calls), 2)

    def _create_generator(self, current_tag, last_tag=None):
        generator = PublishingGithubReleaseNotesGenerator(
            self.github_info.copy(), current_tag, last_tag)
        return generator
