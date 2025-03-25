import unittest
import urllib
import app
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
import sys
import os
import time

import pandas

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'tmp_data')

class SampleTestCase(unittest.TestCase):
    """Test that the website shows the proper things"""
    def setUp(self):
        if "SAUCE_USERNAME" in os.environ:
            username = os.environ["SAUCE_USERNAME"]
            access_key = os.environ["SAUCE_ACCESS_KEY"]
            command_executor = "http://{}:{}@ondemand.saucelabs.com:80/wd/hub".format(username, access_key)
            capabilities = {}
            capabilities["tunnel-identifier"] = os.environ["TRAVIS_JOB_NUMBER"]
            capabilities["platform"] = "Mac OS X 10.9"
            capabilities["browserName"] = "chrome"
            capabilities["version"] = "48"
            self.driver = webdriver.Remote(desired_capabilities=capabilities, command_executor=command_executor)
            self.action_chains = ActionChains(self.driver)
        else:
            # Reference http://elementalselenium.com/tips/2-download-a-file
            new_profile = FirefoxProfile()
            new_profile.default_preferences['browser.download.dir'] = DOWNLOAD_DIR
            new_profile.default_preferences['browser.download.folderList'] = 2
            new_profile.default_preferences['browser.helperApps.neverAsk.saveToDisk'] = 'text/csv'
            self.driver = webdriver.Firefox(firefox_profile=new_profile)
            self.action_chains = ActionChains(self.driver)

        self.db = app.db
        self.db.create_all()
        self.client = app.app.test_client()

    def tearDown(self):
        # clear the database
        self.db.drop_all()
        self.driver.quit()
        if "SAUCE_USERNAME" in os.environ:
            self.clear_dir(DOWNLOAD_DIR)

    def clear_dir(self, dir_to_clear):
        for output_file in os.listdir(dir_to_clear):
            os.remove(os.path.join(dir_to_clear, output_file))

    def is_text_present(self, text):
        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        return text in body_text

    def find_by_value(self, value):
        elements = self.driver.find_elements(By.XPATH, '//*[@value="%s"]' % value)
        return elements

    def mouse_over(self, element):
        """
        Performs a mouse over the element.
        Currently works only on Chrome driver.
        """
        self.action_chains.move_to_element(element)
        self.action_chains.perform()

    def mouse_out(self):
        self.action_chains.move_by_offset(5000, 5000)
        self.action_chains.perform()

    def test_get_base(self):
        r = self.client.get('/')
        assert r._status_code == 200
        assert b'Baltic Sea Reference Metagenome' in r.data

        assert b'Filtering Options' in r.data

    def test_filtering_search(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        # Verify the accordion unfolding
        filter_search_text = "Filter by a search term"
        assert not self.is_text_present(filter_search_text)

        self.driver.find_element(by=By.ID, value="filter_accordion").click()

        time.sleep(0.3) # The accordion takes some time to unfold

        assert self.is_text_present(filter_search_text)

        # Verify the search term filtering
        self.find_by_value(value="filter_with_search")[0].click()
        self.driver.find_element(by=By.ID, value='search_annotations').send_keys("glycosy")
        time.sleep(2) # wait for search result to load
        self.driver.execute_script("window.scrollTo(0,400)")
        assert self.is_text_present("Showing 8 out of 8 in total")

        self.driver.find_element(by=By.ID, value='submit_view').click()

        time.sleep(2) # wait for page to reload with new result
        # There are only six of these which is present as annotations
        # in the test result
        rpkm_tbody = self.driver.find_elements(by=By.CLASS_NAME, value='rpkm_values_tbody')[0]
        assert len(rpkm_tbody.find_elements(by=By.TAG_NAME, value= 'tr')) == 6 # only showing the filtered rows

    def test_filtering_type_identifier(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        self.driver.find_element(by=By.ID, value="filter_accordion").click()
        time.sleep(1) # The accordion takes some time to unfold

        # Verify the type identifiers filtering
        self.find_by_value("filter_with_type_identifiers")[0].click()
        self.driver.find_element(by=By.ID, value='type_identifiers-0').send_keys('pfam00535')

        self.driver.find_element(by=By.ID, value='submit_view').click()
        assert self.is_text_present("pfam00535")
        rpkm_tbody = self.driver.find_elements(by=By.CLASS_NAME, value='rpkm_values_tbody')[0]
        assert len(rpkm_tbody.find_elements(by=By.TAG_NAME, value='tr')) == 1

        self.driver.find_element(by=By.ID, value="filter_accordion").click()
        time.sleep(1) # The accordion takes some time to unfold

        with self.assertRaises(NoSuchElementException):
            self.driver.find_element(by=By.ID, value='type_identifiers-1')
        self.driver.find_element(by=By.ID, value='AddAnotherTypeIdentifier').click()
        self.driver.find_element(by=By.ID, value='type_identifiers-1').send_keys('TIGR01420')

        self.driver.find_element(by=By.ID, value='submit_view').click()
        assert "pfam00535" in self.driver.find_elements(by=By.TAG_NAME, value='table')[0].text
        assert "TIGR01420" in self.driver.find_elements(by=By.TAG_NAME, value='table')[0].text
        rpkm_tbody = self.driver.find_elements(by=By.CLASS_NAME, value='rpkm_values_tbody')[0]
        assert len(rpkm_tbody.find_elements(by=By.TAG_NAME, value='tr')) == 2

    def test_annotation_information(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        self.mouse_over(self.driver.find_elements(by=By.LINK_TEXT, value='COG0059')[0])
        time.sleep(1)
        assert self.is_text_present("Ketol-acid reductoisomerase [Amino acid transport and metabolism")

        self.mouse_out()
        time.sleep(1)
        assert not self.is_text_present("Ketol-acid reductoisomerase [Amino acid transport and metabolism")

        self.driver.find_element(by=By.ID, value='toggle_description_column').click()
        time.sleep(1)
        assert self.is_text_present("Ketol-acid reductoisomerase [Amino acid transport and metabolism")

        self.driver.find_element(by=By.ID, value='toggle_description_column').click()
        time.sleep(1)
        assert not self.is_text_present("Ketol-acid reductoisomerase [Amino acid transport and metabolism")



    def test_show_sample_information(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        assert not self.is_text_present("2014-06-08")
        assert not self.is_text_present("16.3665")
        self.mouse_over(self.driver.find_elements(by=By.LINK_TEXT, value='P1994_119')[0])
        time.sleep(1)
        assert self.is_text_present("2014-06-08")
        assert self.is_text_present("16.3665")

        self.mouse_out()
        time.sleep(1)

        assert not self.is_text_present("2014-06-08")
        assert not self.is_text_present("16.3665")

        self.driver.find_element(by=By.ID, value='toggle_sample_description').click()
        time.sleep(1)

        assert self.is_text_present("2014-06-08")
        assert self.is_text_present("16.3665")

        self.driver.find_element(by=By.ID, value='toggle_sample_description').click()
        time.sleep(1)
        assert not self.is_text_present("2014-06-08")
        assert not self.is_text_present("16.3665")

    def test_filter_samples(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        # This sample should disappear after filtering
        assert self.is_text_present("120813")
        assert self.is_text_present("P1994_119")

        self.driver.find_element(by=By.ID, value="filter_accordion").click()
        time.sleep(1) # The accordion takes some time to unfold

        select_sample = Select(self.driver.find_element(by=By.ID, value='select_sample_groups'))
        select_sample.select_by_visible_text("redox")

        self.driver.find_element(by=By.ID, value='submit_view').click()
        assert self.is_text_present("P2236_103")
        assert self.is_text_present("P2236_104")
        assert self.is_text_present("P2236_105")
        assert not self.is_text_present("120813")
        assert not self.is_text_present("P1994_119")

        self.driver.find_element(by=By.ID, value="filter_accordion").click()
        time.sleep(1) # The accordion takes some time to unfold

        select_sample = Select(self.driver.find_element(by=By.ID, value='select_sample_groups'))

        # This should not unselect redox
        select_sample.select_by_visible_text("lmo")

        self.driver.find_element(by=By.ID, value='submit_view').click()
        assert self.is_text_present("P2236_103")
        assert self.is_text_present("P2236_104")
        assert self.is_text_present("P2236_105")
        assert self.is_text_present("120813")
        assert not self.is_text_present("P1994_119")


    def test_download_gene_list(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        self.driver.find_element(by=By.ID, value="filter_accordion").click()
        time.sleep(1) # The accordion takes some time to unfold

        
        self.driver.find_element(by=By.ID, value="submit_download").click()
        time.sleep(3)

        gene_list = os.path.join(DOWNLOAD_DIR, 'gene_list.csv')
        assert os.path.isfile(gene_list)
        df = pandas.read_table(gene_list, sep=',', header=None, names=['gene_name', 'type_identifier'])
        assert len(df) == 24
        assert len(df.columns) == 2
        assert len(df['type_identifier'].unique()) == 20
        assert df.ix[0]['gene_name'] == 'PROKKA_MOD_PART0_00096'
        assert df.ix[0]['type_identifier'] == 'COG0059'



    def test_download_annotation_counts(self):
        url = "http://localhost:5000/"
        self.driver.get(url)

        self.driver.find_element(by=By.ID, value="filter_accordion").click()
        time.sleep(1) # The accordion takes some time to unfold

        select_what_to_download = Select(
                self.driver.find_element(by=By.ID, value='download_select')
                )
        select_sample.select_by_visible_text("Annotation Counts")

        self.driver.find_element(by=By.ID, value="submit_download").click()
        time.sleep(3)

        output_file = os.path.join(DOWNLOAD_DIR, 'annotation_counts.csv')
        assert os.path.isfile(output_file)
        df = pandas.read_table(output_file, sep=',', index_col=0)
        assert len(df) == 20
        assert len(df.columns) == 10
        assert len(df['type_identifier'].uniq) == 20
        assert df.ix[0]['gene_name'] == 'PROKKA_MOD_PART0_00096'
        assert df.ix[0]['type_identifier'] == 'COG0059'
