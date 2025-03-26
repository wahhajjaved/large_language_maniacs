"""Tests for the views of the freckle_budgets app."""
from django.test import RequestFactory, TestCase

from mock import MagicMock, patch

from . import fixtures
from .. import views


class YearViewTestCase(TestCase):
    """Tests for the ``YearView`` view."""
    longMessage = True

    def test_view(self):
        with patch('freckle_budgets.freckle_api.requests.request') as request_mock:  # NOQA
            request_mock.return_value = MagicMock()
            request_mock.return_value.status_code = 200
            request_mock.return_value.json = MagicMock()
            request_mock.return_value.json.return_value = \
                fixtures.get_api_response()
            req = RequestFactory().get('/')
            resp = views.YearView.as_view()(req)
            self.assertEqual(resp.status_code, 200, msg=('View is callable'))
