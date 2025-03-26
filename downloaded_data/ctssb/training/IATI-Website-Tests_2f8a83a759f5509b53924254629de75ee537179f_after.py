from datetime import datetime, timedelta
from dateutil import parser as date_parser
import pytest
import pytz
from web_test_base import *

class TestIATIDashboard(WebTestBase):
    requests_to_load = {
        'Dashboard Homepage': {
            'url': 'http://dashboard.iatistandard.org/'
        }
    }

    def test_contains_links(self, loaded_request):
        """
        Test that each page contains links to the defined URLs.
        """
        result = utility.get_links_from_page(loaded_request)

        assert "https://github.com/IATI/IATI-Dashboard/" in result

    def test_recently_generated(self, loaded_request):
        """
        Tests that the dashboard was generated in the past 7 days.
        """
        max_delay = timedelta(days=2)
        generation_time_xpath = '//*[@id="footer"]/div/p/em[1]'
        data_time_xpath = '//*[@id="footer"]/div/p/em[2]'

        generation_time_arr = utility.get_text_from_xpath(loaded_request, generation_time_xpath)
        data_time_arr = utility.get_text_from_xpath(loaded_request, data_time_xpath)

        generation_time = date_parser.parse(generation_time_arr[0])
        data_time = date_parser.parse(data_time_arr[0])
        now = datetime.now(pytz.utc)

        assert len(generation_time_arr) == 1
        assert len(data_time_arr) == 1
        assert (now - max_delay) < generation_time
        assert (now - max_delay) < data_time
