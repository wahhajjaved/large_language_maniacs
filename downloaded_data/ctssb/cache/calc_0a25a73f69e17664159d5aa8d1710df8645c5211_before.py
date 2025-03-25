from django.conf import settings
from django.test import LiveServerTestCase

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from contracts.mommy_recipes import get_contract_recipe
from model_mommy.recipe import seq
from itertools import cycle

import re
import time
import os
from datetime import datetime

TESTING_KEY = 'REMOTE_TESTING'
REMOTE_TESTING = hasattr(settings, TESTING_KEY) and getattr(settings, TESTING_KEY) or {}
TESTING_URL = os.environ.get('LOCAL_TUNNEL_URL', REMOTE_TESTING.get('url'))

def _get_testing_config(key, default=None):
    return REMOTE_TESTING.get(key, os.environ.get('%s_%s' % (TESTING_KEY, key.upper()), default))

def _get_webdriver(name):
    name = name.lower()
    if name == 'chrome':
        return webdriver.Chrome()
    elif name == 'firefox':
        return webdriver.Firefox()
    elif name == 'phantomjs':
        return webdriver.PhantomJS()
    raise 'No such webdriver: "%s"' % name

class FunctionalTests(LiveServerTestCase):
    connect = None
    driver = None
    screenshot_filename = 'selenium_tests/screenshot.png'
    window_size = (1000, 1000)

    @classmethod
    def get_driver(cls):
        if not REMOTE_TESTING or not TESTING_URL:
            return _get_webdriver(os.environ.get('TESTING_BROWSER', 'phantomjs'))

        if REMOTE_TESTING.get('enabled') == False:
            pass

        username = _get_testing_config('username')
        access_key = _get_testing_config('access_key')
        hub_url = _get_testing_config('hub_url')
        if None in (username, access_key, hub_url):
            raise Error('You must provide a username, access_key and hub URL!')

        desired_cap = webdriver.DesiredCapabilities.CHROME
        # these are the standard Selenium capabilities
        desired_cap['platform'] = _get_testing_config('platform', 'Windows 7')
        desired_cap['browserName'] = _get_testing_config('browser', 'internet explorer')
        desired_cap['version'] = _get_testing_config('browser_version', '9.0')
        # this shows up in the left-hand column of Sauce tests
        desired_cap['name'] = 'CALC'
        other_caps = REMOTE_TESTING.get('capabilities')
        if other_caps:
            desired_cap.update(other_caps)
        print('capabilities:', desired_cap)

        driver = webdriver.Remote(
            desired_capabilities=desired_cap,
            command_executor=hub_url % (username, access_key)
        )

        # XXX should this be higher?
        driver.implicitly_wait(20)
        return driver

    @classmethod
    def setUpClass(cls):
        cls.driver = cls.get_driver()
        cls.longMessage = True
        cls.maxDiff = None
        super(FunctionalTests, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.take_screenshot()
        cls.driver.quit()
        if cls.connect:
            cls.connect.shutdown_connect()

    @classmethod
    def take_screenshot(cls):
        """
        Take a screenshot of the browser whenever the test fails?
        """
        png = cls.screenshot_filename
        if '%' in png:
            png = png % {'date': datetime.today()}
        cls.driver.get_screenshot_as_file(png)
        print('screenshot taken: %s' % png)

    def _fail(self, *args, **kwargs):
        super(FunctionalTests, self).fail(*args, **kwargs)

    def setUp(self):
        self.base_url = self.live_server_url
        if TESTING_URL:
            self.base_url = TESTING_URL
        self.driver.set_window_size(*self.window_size)
        super(FunctionalTests, self).setUp()

    def load(self, uri='/'):
        url = self.base_url + uri
        print('loading URL: %s' % url)
        self.driver.get(url)
        # self.driver.execute_script('$("body").addClass("selenium")')
        return self.driver

    def load_and_wait(self, uri='/'):
        self.load(uri)
        self.wait_for(self.data_is_loaded)
        return self.driver

    def wait_for(self, condition, timeout=10):
        try:
            wait_for(condition, timeout=timeout)
        except Exception, err:
            return self.fail(err)
        return True

    def get_form(self):
        return self.driver.find_element_by_id('search')

    def submit_form(self):
        form = self.get_form()
        form.submit()
        time.sleep(.001)
        return form

    def submit_form_and_wait(self):
        form = self.submit_form()
        self.wait_for(self.data_is_loaded)
        return form

    def search_for(self, query):
        q = self.driver.find_element_by_name('q')
        q.clear()
        q.send_keys(query)
        # XXX oh my god why do we have to do this???
        self.driver.execute_script('$("[name=q]").blur()')

    def data_is_loaded(self):
        form = self.get_form()
        if has_class(form, 'error'):
            self.driver.get_screenshot_as_file('test/data_not_loaded.png')
            return self.fail("Form submit error: '%s'" % form.find_element_by_css_selector('.error-message').text)
        return has_class(form, 'loaded')

    def test_results_count__empty_result_set(self):
        driver = self.load_and_wait()
        self.assert_results_count(driver, 0)

    def test_results_count(self):
        get_contract_recipe().make(_quantity=10, labor_category=seq("Engineer"))
        driver = self.load_and_wait()
        self.assert_results_count(driver, 10)

    def test_titles_are_correct(self):
        get_contract_recipe().make(_quantity=1, labor_category=seq("Architect"))
        driver = self.load_and_wait()
        self.assertTrue(driver.title.startswith('Hourglass'), 'Title mismatch, {} does not start with Hourglass'.format(driver.title))

    def test_filter_order_is_correct(self):
        get_contract_recipe().make(_quantity=1, labor_category=seq("Architect"))
        driver = self.load()
        form = self.get_form()

        inputs = form.find_elements_by_css_selector("input:not([type='hidden'])")

        # the last visible form inputs should be the price filters
        self.assertEqual(inputs[-2].get_attribute('name'), 'price__gte')
        self.assertEqual(inputs[-1].get_attribute('name'), 'price__lte')
    
    # TODO bring this back!
    def xtest_form_submit_loading(self):
        get_contract_recipe().make(_quantity=1, labor_category=seq("Architect"))
        self.load()
        self.search_for('Architect')
        form = self.submit_form()
        # print(self.driver.execute_script('document.querySelector("#search").className'))
        self.assertTrue(has_class(form, 'loading'), "Form doesn't have 'loading' class")
        self.wait_for(self.data_is_loaded)
        self.assertTrue(has_class(form, 'loaded'), "Form doesn't have 'loaded' class")
        self.assertFalse(has_class(form, 'loading'), "Form shouldn't have 'loading' class after loading")

    def test_search_input(self):
        get_contract_recipe().make(_quantity=9, labor_category=cycle(["Engineer", "Architect", "Writer"]))
        driver = self.load()
        self.search_for('Engineer')
        self.submit_form()
        self.assertTrue('q=Engineer' in driver.current_url, 'Missing "q=Engineer" in query string')
        self.wait_for(self.data_is_loaded)

        self.assert_results_count(driver, 3)
        labor_cell = driver.find_element_by_css_selector('tbody tr .column-labor_category')
        self.assertTrue('Engineer' in labor_cell.text, 'Labor category cell text mismatch')

    def test_price_gte(self):
        # note: the hourly rates here will actually start at 80-- this seems
        # like a bug, but whatever
        get_contract_recipe().make(_quantity=10, labor_category=seq("Contractor"), hourly_rate_year1=seq(70, 10), current_price=seq(70, 10))
        driver = self.load()
        form = self.get_form()
        self.search_for('Contractor')

        minimum = 100
        # add results count check
        self.set_form_value(form, 'price__gte', minimum)
        self.submit_form_and_wait()
        self.assertTrue(('price__gte=%d' % minimum) in driver.current_url, 'Missing "price__gte={0}" in query string: {1}'.format(minimum, driver.current_url))
        self.assert_results_count(driver, 8)

    def test_price_lte(self):
        # note: the hourly rates here will actually start at 80-- this seems
        # like a bug, but whatever
        get_contract_recipe().make(_quantity=10, labor_category=seq("Contractor"), hourly_rate_year1=seq(70, 10), current_price=seq(70, 10))
        driver = self.load()
        form = self.get_form()
        self.search_for('Contractor')

        maximum = 100
        # add results count check
        self.set_form_value(form, 'price__lte', maximum)
        self.submit_form_and_wait()
        self.assertTrue(('price__lte=%d' % maximum) in driver.current_url, 'Missing "price__lte=%d" in query string' % maximum)
        self.assert_results_count(driver, 3)

    def test_price_range(self):
        # note: the hourly rates here will actually start at 80-- this seems
        # like a bug, but whatever
        get_contract_recipe().make(_quantity=10, labor_category=seq("Contractor"), hourly_rate_year1=seq(70, 10), current_price=seq(70, 10))
        driver = self.load()
        form = self.get_form()
        self.search_for('Contractor')

        minimum = 100
        maximum = 130
        self.set_form_value(form, 'price__gte', minimum)
        self.set_form_value(form, 'price__lte', maximum)
        self.submit_form_and_wait()
        self.assert_results_count(driver, 4)
        self.assertTrue(('price__gte=%d' % minimum) in driver.current_url, 'Missing "price__gte=%d" in query string' % minimum)
        self.assertTrue(('price__lte=%d' % maximum) in driver.current_url, 'Missing "price__lte=%d" in query string' % maximum)

    def test_there_is_no_business_size_column(self):
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Large Biz"), business_size='o')
        driver = self.load()
        form = self.get_form()

        col_headers = get_column_headers(driver)

        for head in col_headers:
            self.assertFalse(has_matching_class(head, 'column-business[_-]size'))

    def test_filter_to_only_small_businesses(self):
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Large Biz"), business_size='o')
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Small Biz"), business_size='s')
        driver = self.load_and_wait()
        form = self.get_form()

        self.set_form_value(form, 'business_size', 's')
        self.submit_form_and_wait()

        self.assert_results_count(driver, 5)

        self.assertIsNone(re.search(r'Large Biz\d+', driver.page_source))
        self.assertIsNotNone(re.search(r'Small Biz\d+', driver.page_source))

    def test_filter_to_only_large_businesses(self):
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Large Biz"), business_size='o')
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Small Biz"), business_size='s')
        driver = self.load_and_wait()
        form = self.get_form()

        self.set_form_value(form, 'business_size', 'o')
        self.submit_form_and_wait()

        self.assert_results_count(driver, 5)

        self.assertIsNone(re.search(r'Small Biz\d+', driver.page_source))
        self.assertIsNotNone(re.search(r'Large Biz\d+', driver.page_source))

    def test_no_filter_shows_all_sizes_of_business(self):
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Large Biz"), business_size='o')
        get_contract_recipe().make(_quantity=5, vendor_name=seq("Small Biz"), business_size='s')
        driver = self.load_and_wait()

        self.assert_results_count(driver, 10)

        self.assertIsNotNone(re.search(r'Small Biz\d+', driver.page_source))
        self.assertIsNotNone(re.search(r'Large Biz\d+', driver.page_source))

    def test_schedule_column_is_collapsed_by_default(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load()
        col_header = find_column_header(driver, 'schedule')

        self.assertTrue(has_class(col_header, 'collapsed'))

    def test_unhide_schedule_column(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load()
        col_header = find_column_header(driver, 'schedule')

        # un-hide column
        col_header.find_element_by_css_selector('.toggle-collapse').click()

        self.assertFalse(has_class(col_header, 'collapsed'))

        # re-hide column
        col_header.find_element_by_css_selector('.toggle-collapse').click()

        self.assertTrue(has_class(col_header, 'collapsed'))

    def test_schedule_column_is_last(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        col_headers = get_column_headers(driver)
        self.assertTrue(has_class(col_headers[-1], 'column-schedule'))

    def test_sortable_columns__non_default(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()

        for col in ['labor_category', 'education_level', 'min_years_experience']:
            self._test_column_is_sortable(driver, col)

    def test_price_column_is_sortable_and_is_the_default_sort(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        col_header = find_column_header(driver, 'current_price')
        # current_price should be sorted ascending by default
        self.assertTrue(has_class(col_header, 'sorted'), "current_price is not the default sort")
        self.assertTrue(has_class(col_header, 'sortable'), "current_price column is not sortable")
        self.assertFalse(has_class(col_header, 'descending'), "current_price column is descending by default")
        col_header.click()
        self.assertTrue(has_class(col_header, 'sorted'), "current_price is still sorted after clicking")

    def test_one_column_is_sortable_at_a_time(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        header1 = find_column_header(driver, 'education_level')
        header2 = find_column_header(driver, 'labor_category')

        header1.click()
        self.assertTrue(has_class(header1, 'sorted'), "column 1 is not sorted")
        self.assertFalse(has_class(header2, 'sorted'), "column 2 is still sorted (but should not be)")

        header2.click()
        self.assertTrue(has_class(header2, 'sorted'), "column 2 is not sorted")
        self.assertFalse(has_class(header1, 'sorted'), "column 1 is still sorted (but should not be)")

    def test_histogram_is_shown(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        rect_count = len(driver.find_elements_by_css_selector('.histogram rect'))
        self.assertTrue(rect_count > 0, "No histogram rectangles found (selector: '.histogram rect')")

    def xtest_histogram_shows_min_max(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        histogram = driver.find_element_by_css_selector('.histogram')
        for metric in ('min', 'max', 'average'):
            node = histogram.find_element_by_class_name(metric)
            self.assertTrue(node.text.startswith(u'$'), "histogram '.%s' node does not start with '$': '%s'" % (metric, node.text))

    # XXX this test is deprecated because it's too brittle.
    # We shouldn't really care about the number of x-axis ticks.
    def xtest_histogram_shows_intevals(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        ticks = driver.find_elements_by_css_selector('.histogram .x.axis .tick')
        # XXX there should be 10 bins, but 11 labels (one for each bin edge)
        self.assertEqual(len(ticks), 11, "Found wrong number of x-axis ticks: %d" % len(ticks))

    def test_histogram_shows_tooltips(self):
        get_contract_recipe().make(_quantity=5)
        driver = self.load_and_wait()
        bars = driver.find_elements_by_css_selector('.histogram .bar')
        # TODO: check for "real" tooltips?
        for i, bar in enumerate(bars):
            title = bar.find_element_by_css_selector('title')
            self.assertIsNotNone(title.text, "Histogram bar #%d has no text" % i)

    def test_query_type_matches_words(self):
        get_contract_recipe().make(_quantity=3, labor_category=cycle(['Systems Engineer', 'Software Engineer', 'Consultant']))
        driver = self.load()
        form = self.get_form()
        self.search_for('engineer')
        self.submit_form_and_wait()
        cells = driver.find_elements_by_css_selector('table.results tbody td.column-labor_category')
        self.assertEqual(len(cells), 2, 'wrong cell count: %d (expected 2)' % len(cells))
        for cell in cells:
            self.assertTrue('Engineer' in cell.text, 'found cell without "Engineer": "%s"' % cell.text)

    def test_query_type_matches_phrase(self):
        get_contract_recipe().make(_quantity=3, labor_category=cycle(['Systems Engineer I', 'Software Engineer II', 'Consultant II']))
        driver = self.load()
        form = self.get_form()
        self.search_for('software engineer')
        self.set_form_values(form, query_type='match_phrase')
        self.submit_form_and_wait()
        cells = driver.find_elements_by_css_selector('table.results tbody td.column-labor_category')
        self.assertEqual(len(cells), 1, 'wrong cell count: %d (expected 1)' % len(cells))
        self.assertEqual(cells[0].text, 'Software Engineer II', 'bad cell text: "%s"' % cells[0].text)

    def test_query_type_matches_exact(self):
        get_contract_recipe().make(_quantity=3, labor_category=cycle(['Software Engineer I', 'Software Engineer', 'Senior Software Engineer']))
        driver = self.load()
        form = self.get_form()
        self.search_for('software engineer')
        self.set_form_values(form, query_type='match_exact')
        # self.assertEqual(driver.execute_script('document.querySelector("input[value=\'match_exact\']").checked'), True, 'match_exact not checked!')
        self.submit_form_and_wait()
        cells = driver.find_elements_by_css_selector('table.results tbody td.column-labor_category')
        self.assertEqual(len(cells), 1, 'wrong cell count: %d (expected 1)' % len(cells))
        self.assertEqual(cells[0].text, 'Software Engineer', 'bad cell text: "%s"' % cells[0].text)

    def _test_column_is_sortable(self, driver, colname):
        col_header = find_column_header(driver, colname)
        self.assertTrue(has_class(col_header, 'sortable'), "{} column is not sortable".format(colname))
        # NOT sorted by default
        self.assertFalse(has_class(col_header, 'sorted'), "{} column is sorted by default".format(colname))
        col_header.click()
        self.assertTrue(has_class(col_header, 'sorted'), "{} column is not sorted after clicking".format(colname))

    def assert_results_count(self, driver, num):
        results_count = driver.find_element_by_id('results-count').text
        # remove commas from big numbers (e.g. "1,000" -> "1000")
        results_count = results_count.replace(',', '')
        self.assertNotEqual(results_count, u'', "No results count")
        self.assertEqual(results_count, str(num), "Results count mismatch: '%s' != %d" % (results_count, num))

    def set_form_value(self, form, key, value):
        fields = form.find_elements_by_name(key)
        field = fields[0]
        if field.tag_name == 'select':
            Select(field).select_by_value(value)
        else:
            field_type = field.get_attribute('type')
            if field_type in ('checkbox', 'radio'):
                for _field in fields:
                    if _field.get_attribute('value') == value:
                        _field.click()
            else:
                field.send_keys(str(value))
        return field


    def set_form_values(self, form, **values):
        for key, value in values.items():
            self.set_form_value(form, key, value)


def wait_for(condition, timeout=3):
    start = time.time()
    while time.time() < start + timeout:
        if condition():
            return True
        else:
            time.sleep(0.01)
    raise Exception('Timeout waiting for {}'.format(condition.__name__))

def has_class(element, klass):
    return klass in element.get_attribute('class').split(' ')

def has_matching_class(element, regex):
    return re.search(regex, element.get_attribute('class'))

def find_column_header(driver, col_name):
    return driver.find_element_by_css_selector('th.column-{}'.format(col_name))

def get_column_headers(driver):
    return driver.find_elements_by_xpath('//thead/tr/th')


# We only need this monkey patch here because the stack traces clutter up the
# test results output. --shawn
def patch_broken_pipe_error():
    """
    Monkey patch BaseServer.handle_error to not write a stack trace to stderr
    on broken pipe: <http://stackoverflow.com/a/22618740/362702>
    """
    import sys
    from SocketServer import BaseServer
    from wsgiref import handlers

    handle_error = BaseServer.handle_error
    log_exception = handlers.BaseHandler.log_exception

    def is_broken_pipe_error():
        type, err, tb = sys.exc_info()
        r = repr(err)
        return r in ("error(32, 'Broken pipe')", "error(54, 'Connection reset by peer')")

    def my_handle_error(self, request, client_address):
        if not is_broken_pipe_error():
            handle_error(self, request, client_address)

    def my_log_exception(self, exc_info):
        if not is_broken_pipe_error():
            log_exception(self, exc_info)

    BaseServer.handle_error = my_handle_error
    handlers.BaseHandler.log_exception = my_log_exception

patch_broken_pipe_error()


if __name__ == '__main__':
    import unittest
    unittest.main()
