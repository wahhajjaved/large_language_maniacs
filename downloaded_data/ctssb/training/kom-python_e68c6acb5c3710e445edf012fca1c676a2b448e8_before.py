import time
from urllib.request import urlopen

from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions

from ..general import Log, find_between
from ..web import hub_ip, hub_port, remote_execution, iframe_load_time, http_request_wait_time, \
    page_load_time
from ..web.drivers import browser, driver


class Browser:
    def __init__(self, module_name=None):
        self._active = False
        self._driver = None
        self.test_session_api = 'http://%s:%s/grid/api/testsession' % (hub_ip, hub_port)
        self.loaded_extension = None
        self.module_name = module_name

    def __set_focus(self):
        if remote_execution:
            Log.info("Setting focus to the Browser")
            self._driver.execute_script("alert('Focusing the window');")
            time.sleep(0.5)
            Alert(self._driver).accept()

    def __get_driver(self):
        if self._driver and not self._active:
            Log.info("Switching to the other browser")
            self.__set_focus()
            self._active = True
        return self._driver

    def __set_driver(self, value):
        self._driver = value
        if value:
            self.__set_focus()

    driver = property(__get_driver, __set_driver)

    def get_node_id(self):
        self.open("http://localhost")
        hub_session_api = "%s?session=%s" % (self.test_session_api, self.driver.session_id)
        result = urlopen(hub_session_api)
        string_data = str(result.read())
        Log.info("Result api: %s" % string_data)
        node_id = find_between(string_data, "http://", ":%s" % hub_port)
        Log.info("ProxyId: %s" % node_id)
        self.quit()
        return node_id

    def open(self, url, open_url=True, extension=None):
        Log.info("Opening %s url" % url)
        if not self.driver:
            Log.info("Creating an instance of a Browser: %s." % browser)
            self.driver = driver.create_session()
        elif extension and (not self.loaded_extension or self.loaded_extension != extension):
            self.quit()
            self.open(url, open_url=False, extension=extension)
            self.loaded_extension = extension
        if open_url:
            self.driver.get(url)

    def switch_to_frame(self, frame_locator):
        WebDriverWait(self.driver,
                      iframe_load_time).until(
            expected_conditions.frame_to_be_available_and_switch_to_it(frame_locator))

    def switch_to_default_content(self):
        self.driver.switch_to.default_content()

    def wait_until_http_requests_are_finished(self, wait_time=http_request_wait_time):
        try:
            WebDriverWait(self.driver, wait_time).until(
                lambda web_driver: self.driver.execute_script("return window.openHTTPs")
            )
        except TimeoutException:
            Log.error('HTTP request execution time is more than %s seconds' % wait_time)
            self.driver.execute_script("window.openHTTPs=0")

    def refresh(self):
        Log.info("Refreshing the browser")
        self.driver.refresh()
        self.wait_for_page_to_load()

    def quit(self):
        if self.driver:
            Log.info("Closing the browser")
            self.driver.quit()
            self.driver = None

    def wait_for_alert(self, wait_time=iframe_load_time):
        WebDriverWait(self.driver, wait_time).until(expected_conditions.alert_is_present(),
                                                    'Timed out waiting for alert to appear.')

    def accept_alert(self):
        Log.info("Accept alert")
        Alert(self._driver).accept()

    def enter_text_into_alert(self, text):
        Log.info('Enter "%s" text into Alert' % text)
        Alert(self._driver).send_keys(text)

    def enter_text_and_accept_alert(self, text):
        self.wait_for_alert()
        self.enter_text_into_alert(text)
        self.accept_alert()

    def current_url(self):
        return self.driver.current_url

    def execute_script(self, script):
        self.driver.execute_script(script)

    def get_browser_log(self):
        Log.info("Getting browser log")
        return self.driver.get_log('browser')

    def scroll_up(self):
        ActionChains(self.driver).send_keys(Keys.PAGE_UP).perform()
        time.sleep(0.5)

    def delete_all_cookies(self):
        self.driver.delete_all_cookies()

    def wait_for_page_to_load(self, wait_time=page_load_time):
        try:
            WebDriverWait(self.driver, wait_time).until(
                lambda web_driver: self.driver.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException:
            Log.info("Page was not loaded in %s seconds" % wait_time)

    def type_keys(self, keys):
        self.driver.switch_to.active_element.send_keys(keys)

