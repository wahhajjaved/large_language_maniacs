"""Tests for the instructions.html and associated view"""
from selenium import webdriver
from django.test import LiveServerTestCase
from charades import strings

class InstructionsTests(LiveServerTestCase):
    """
    Index.html tests for page elements and button uses
    """
    
    @classmethod
    def setUpClass(cls):
        """
        Start chrome instance of webdriver
        """
        super(InstructionsTests, cls).setUpClass()
        cls.browser = webdriver.Chrome()
        cls.browser.implicitly_wait(10)
     

    def test_generic_page_elements(self):
        """
        test the non-actor and non-viewer spesific content
        """
        self.browser.get('%s%s' % (self.live_server_url,
                                    '/instructions/?session_id=test-room'))
        self.assertTrue('Charades' in self.browser.title)
        page_title = self.browser.find_element_by_class_name('page_title').text
        self.assertEqual('Instructions', page_title)
        session_id = self.browser.find_element_by_id('session_id').text
        self.assertEqual('Session Id: test-room', session_id)
    
    def test_page_elements_actor(self):
        """
        test the elements of the actor page
        """
        self.browser.get('%s%s' % (self.live_server_url,
                                    '/instructions/?session_id=test-room&user_type=Actor'))
        inst_para = self.browser.find_element_by_id('instruction_para').text
        self.assertEqual(strings.actor_instructions(), inst_para)
        actor_form = self.browser.find_element_by_id('phrase_selection')
        self.assertIsNotNone(actor_form)
        phrase_selection_button = self.browser.find_element_by_id('phrase_selection_button')
        self.assertIsNotNone(phrase_selection_button)
    
    def test_actor_button_to_phrase_selection(self):
        """
        test that the actor button for phrase selection
        moves the user to the phrase_selection.html page
        """
        self.browser.get('%s%s' % (self.live_server_url,
                                   '/instructions/?user_type=Actor'))
        phrase_sel_button = self.browser.find_element_by_id('phrase_selection_button')
        phrase_sel_button.click()
        current_url = self.browser.current_url
        self.assertTrue(r'localhost:8081/select_phrase/' in current_url)
        
        
    def test_page_elements_viewer(self):
        """
        test the elements of the viewer page
        """
        self.browser.get('%s%s' % (self.live_server_url,
                                    '/instructions/?session_id=test-room&user_type=Viewer'))
        inst_para = self.browser.find_element_by_id('instruction_para').text
        self.assertEqual(strings.viewer_instructions(), inst_para)
        please_wait = self.browser.find_element_by_id('please_wait_para').text
        self.assertEqual(please_wait, "Please wait for the actor to select a phrase")

    def tearDown(self):
        self.browser.refresh()
        
    @classmethod
    def tearDownClass(cls):
        """
        Close webdriver instance
        """
        cls.browser.refresh()
        cls.browser.quit()
        super(InstructionsTests, cls).tearDownClass()
