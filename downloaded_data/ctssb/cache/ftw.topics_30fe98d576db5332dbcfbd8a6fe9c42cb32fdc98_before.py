from ftw.topics.interfaces import ITopicSupport
from ftw.topics.testing import SIMPLELAYOUT_TOPICS_INTEGRATION_TESTING
from plone.app.testing import TEST_USER_ID
from plone.app.testing import TEST_USER_NAME
from plone.app.testing import login
from plone.app.testing import setRoles
from unittest2 import TestCase


class TestSchemaExtender(TestCase):

    layer = SIMPLELAYOUT_TOPICS_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer['portal']

        setRoles(self.portal, TEST_USER_ID, ['Manager'])
        login(self.portal, TEST_USER_NAME)


    def test_extends_ITopicSupport(self):
        page = self.portal.get(self.portal.invokeFactory(
                'ContentPage', 'page'))

        self.assertTrue(
            ITopicSupport.providedBy(page),
            'Expected ContentPage objects to provide ITopicSupport'
            ' but it doesnt.')

        field = page.Schema().get('topics')
        self.assertTrue(field, 'Field "topics" missing on ContentPage')

    def test_does_not_extend_others(self):
        obj = self.portal.get(self.portal.invokeFactory('File', 'file'))

        self.assertFalse(ITopicSupport.providedBy(file),
                         'Did not expect "File" to provide "ITopicSupport"')

        field = obj.Schema().get('topics')
        self.assertFalse(
            field, '"File" object should not have "topics" field')
