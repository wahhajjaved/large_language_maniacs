from datetime import datetime, timedelta
from unittest import mock

from django.test import TestCase

from .models import Posts


class PostsTestCase(TestCase):
    def test_how_long_0_secs(self):
        creation = datetime(year=1966, month=6, day=6)

        post = Posts(publication_date=creation)
        with mock.patch('blog.posts.models.datetime') as dt:
            dt.now = mock.Mock()
            dt.now.return_value = creation
            self.assertEqual(post.how_long_ago(), '0 seconds ago')

    def test_how_long_1_sec_ago(self):
        creation = datetime(year=1966, month=6, day=6)

        post = Posts(publication_date=creation)
        with mock.patch('blog.posts.models.datetime') as dt:
            dt.now = mock.Mock()
            dt.now.return_value = creation + timedelta(seconds=1)
            self.assertEqual(post.how_long_ago(), '1 second ago')

    def test_how_long_multiple_seconds(self):
        creation = datetime(year=1966, month=6, day=6)

        post = Posts(publication_date=creation)
        with mock.patch('blog.posts.models.datetime') as dt:
            dt.now = mock.Mock()
            dt.now.return_value = creation + timedelta(seconds=42)
            self.assertEqual(post.how_long_ago(), '42 seconds ago')

    def test_how_long_1_minute(self):
        creation = datetime(year=1966, month=6, day=6)

        post = Posts(publication_date=creation)
        with mock.patch('blog.posts.models.datetime') as dt:
            dt.now = mock.Mock()
            dt.now.return_value = creation + timedelta(minutes=1)
            self.assertEqual(post.how_long_ago(), '1 minute ago')

    def test_how_long_multiple_minutes(self):
        creation = datetime(year=1966, month=6, days=6)

        post = Posts(publication_date=creation)
        with mock.patch('blog.posts.models.datetime') as dt:
            dt.now = mock.Mock()
            dt.now.return_value = creation + timedelta(minutes=42)
            self.assertEqual(post.how_long_ago(), '42 minutes ago')
