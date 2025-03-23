from cms import externals
from cms.apps.pages.models import Page
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from ..models import Job, Jobs


class ApplicationTestCase(TestCase):

    def setUp(self):
        # Note: as this is the only page in the database, it's absolute URL
        # will simply be '/'

        with externals.watson.context_manager("update_index")():
            content_type = ContentType.objects.get_for_model(Jobs)
            self.page = Page.objects.create(
                content_type=content_type,
                title='Foo',
                slug='foo',
            )

            self.job_page = Jobs.objects.create(
                page=self.page,
            )

        self.job = Job.objects.create(
            page=self.job_page,
            url_title='foo-bar',
            title='Tester',
        )

    def test_job_get_absolute_url(self):
        self.assertEqual(self.job.get_absolute_url(), '/foo-bar/')

    def test_job_unicode(self):
        self.assertEqual(self.job.__unicode__(), 'Tester')
