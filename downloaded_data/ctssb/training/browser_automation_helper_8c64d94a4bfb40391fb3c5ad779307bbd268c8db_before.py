
#################################################
########   Define your driver path here   #######
#################################################

DRIVER_PATH = ""

#################################################

import time
from bs4 import BeautifulSoup as bs

class BrowserHelper:
    ''' class to help automate browser '''
    def __init__(self, browser="chrome", driver_path=None,
                 options=False, log_file="log.txt"):

        if driver_path is None:
            # maybe variable is defined
            global DRIVER_PATH

            if DRIVER_PATH:
                self.driver_path = DRIVER_PATH  # no checks here
            else:
                self.driver_path = self.get_driver(browser)
                if not self.driver_path:
                    exit()
                else:
                    # dynamically edit lines in this file
                    self.replace_driver_path_line_if_necessary(
                                                        self.driver_path)
        else:
            self.driver_path = driver_path

        self.br = False
        self.log_file = log_file
        # for later use
        self.keys = ""
        self.elem = ""

        self.options = options  # supply dictionary
        self.which_browser = browser

    def __repr__(self):
        ''' Testing '''
        text = (f"<BrowserHelper (browser={repr(self.which_browser)}, "
                f"driver_path='{self.driver_path}')>")
        return text

    def __str__(self):
        ''' Testing '''
        text = f'<BrowserHelper object for {self.which_browser}>'
        return text

    def replace_driver_path_line_if_necessary(self, driver_path):
        '''
        replace current files driver_path line,
        if user gives this information,
        to not repeat same process more than once

        adds appropriate string in line
        DRIVER_PATH = ""
        plus comment before that line that it changed dynamically
        '''
        import os
        import sys
        import re

        try:
            # works for scripts usage
            curr_file = os.path.abspath(os.path.realpath(__file__))
        except:
            # added for shell support, as __file__ is not defined here
            # may need modification/refinement
            curr_file = os.path.join(os.getcwd(), sys.argv[0])

        # read
        with open(curr_file, "r") as f: content = f.read()
        # edit
        notif_line = ('""" Line Changed Automatically At'
                      f'| {time.ctime()} """')

        content = re.sub(
            '\nDRIVER_PATH = ""\n',
            f'\n{notif_line}\n'
            f'DRIVER_PATH = "{driver_path}"\n', content)

        # write
        with open(curr_file, "w") as f: f.write(content)
        print(f"Driver location {self.driver_path} saved".center(70))
        # be careful here

    def get_driver(self, browser):
        '''
        Search file system and get driver files locations.

        then as, which one to use, if none found, tell about it,
        and try to get this info from user, otherwise exit.

        P.s. here we have an infinite loop.
        '''
        from pathlib import Path
        import os

        drivers = {"chrome": "chromedriver",
                   "firefox": "geckodriver",
                   # "test": "this_file_should_not_be_found",

                   }

        if browser not in drivers:
            print(f"Sorry, {browser} is not supported yet")
            return

        driver_name = drivers[browser]
        possible_drivers = []

        print(f'Searching for driver files for {browser}'.center(70))

        try:
            for i in Path("/").glob(f"**/*{driver_name}*"):
                link = str(i).lower()

                if driver_name in link:
                    # check that file is .exe(windows) or has no extension
                    # for now, avoid complications with system types
                    if link.split(".")[-1] == "exe" or \
                            any([link.endswith(j) for j in drivers.values()]):
                        # path seems to not working correctly
                        # (or we should read its docs),
                        # so make check
                        possible_drivers.append(i)
        except OSError:
            pass  # sometimes error appears at the end, bug (?)

        # check answer
        if not possible_drivers:
            print(f"Sorry, drivers for {browser} not found, please download one."
                  "\nFor chrome   -   http://chromedriver.chromium.org/downloads"
                  "\nFor Firefox  -   https://github.com/mozilla/geckodriver/releases" 
                  "\n\nexiting")
            return
        else:
            print("="*70, "\n")
            print(f"{len(possible_drivers)} possible driver files found,"
                  " which one should I use?".center(70))
            print("* P.s. you can also supply full path to driver here\n")
            print("="*70, "\n")

            for index, i in enumerate(possible_drivers):
                print(f' {index}. {i}')

            answer = input().strip()

            # else:
            while not os.path.isfile(answer) or not answer.isdigit():
                if answer.isdigit():
                    index = int(answer)
                    max_good_index = len(possible_drivers) - 1

                    if not (0 <= index <= max_good_index):
                        print(f"Please use index between 0 and {max_good_index}")
                    else:
                        print(f"Thanks,")
                        return possible_drivers[index]
                else:
                    print("File not found, try again")
                answer = input().strip()

            print(f"Thanks,")
            return answer

    def add_necessary_options(self, args):
        '''
        change/add options to browser instance,
        such as custom download location,
        proxy address, visibility(hide/show browser)

        args --> dictionary, ex: {'proxy' : '1.2.3.4:5', 'visibility': False }
        full list:
            . visibility - True/False - boolean_value
            . download_location - /path/to/folder - string
            . window_size - (width, height) - tuple
            . hide_images - True/False - boolean
            . disable_javascript - True/False - boolean
            . proxy - ip:port - string
            . user-data-dir - path/to/chrome/profile - string
            . disable_infobars - show or not infobars(default - False)
                              (including chrome is being...) - boolean

        '''
        if self.which_browser == "chrome":
            from selenium.webdriver.chrome.options import Options
        elif self.which_browser == "firefox":
            from selenium.webdriver.firefox.options import Options

        self.browser_options = Options()

        # things to change by default
        self.browser_options.add_argument("--disable-infobars")

        if self.options:
            for key, value in self.options.items():
                # proxy
                if key == "proxy":
                    self.browser_options.add_argument(
                        f"--proxy-server=http://{value}")
                    self.browser_options.add_argument(
                        f"--proxy-server=https://{value}")

                # window size
                elif key == "window_size":
                    self.browser_options.add_argument(
                        f'--window-size={value[0]},{value[1]}')

                # download folder
                elif key == "download_location":
                    add_me = {'download.default_directory': value}
                    self.browser_options.add_experimental_option(
                                                     'prefs', add_me)
                # display or not images
                elif key == "hide_images":
                    if value:
                        self.browser_options.add_argument(
                            '--blink-settings=imagesEnabled=false')

                # disable or not javascript
                elif key == "disable_javascript":
                    if value:
                        self.browser_options.add_experimental_option(
                                        "prefs",
                                        {'profile.managed_default'
                                         '_content_settings.javascript': 2})

                elif key == "disable_infobars":
                    if not value:
                        # self.browser_options.add_argument(
                        #                         "--enable-infobars")
                        self.browser_options.arguments.remove(
                                                        "--disable-infobars")

                # hide or not browser window
                elif key == "visibility":
                    if not value:
                        self.browser_options.add_argument('--headless')

                # chrome profile to use
                elif key == "user-data-dir":
                    self.browser_options.add_argument(
                                f'user-data-dir={value}')

                else:
                    pass

    def initialize_browser_if_necessary(self):
        '''
        initialize(open and assign to object) browser if necessary
        '''
        if not self.br:
            from selenium import webdriver
            # for later use
            from selenium.webdriver.common.keys import Keys

            self.add_necessary_options(self.options)
            # breakpoint()

            if self.which_browser == "chrome":

                self.br = webdriver.Chrome(executable_path=self.driver_path,
                                           options=self.browser_options)
            elif self.which_browser == "firefox":
                self.br = webdriver.Firefox(executable_path=self.driver_path,
                                            options=self.browser_options)
            self.keys = Keys

    def close(self):
        '''just close browser'''
        self.br.quit()

    def css(self, selector):
        '''find all matches by css selector'''
        return self.br.find_elements_by_css_selector(selector)

    def css1(self, selector):
        ''' find first element by css selector'''
        elem = self.br.find_element_by_css_selector(selector)
        self.elem = elem  # to use later in clicks
        return elem

    def xpath(self, selector):
        ''' find all matches by xpath'''
        return self.br.find_elements_by_xpath(selector)

    def xpath1(self, selector):
        ''' find first element by xpath'''
        elem = self.br.find_element_by_xpath(selector)
        self.elem = elem
        return elem

    def find(self, text, ignore_case=False,
             tag="*", all_=False, exact=False, interactable=True):
        '''
        get element on a page containing given text
        (not exact text match, just
        any element containing that text,
        if we want exact match, set exact argument to True,
        but be careful, as sometimes whitespace is not visible)

        it is possible to make case insensitive search,
        if ignore_case is set to True

        We can also supply parent tag string, to
        narrow down results, for example, find
        only <a> tags with text 'Hello',

        by default tag is *, so we search for all matches.

        * cool tip:
            We can inject xpath selector parts(after*) for more specific
        elements, for example, we can set tag to:
            *[@title='Xpath Seems Also Cool']
        and result will be the element with given title attribute.

        all_ argument controls, if all matches should be returned.

        in some cases, to avoid errors, for example if we are not sure
        if element will be present, we can set all_ to True
        (default is False) and we will get empty list if no elements found,
        when in opposite case(default) we will get errrroor

        Set interactable to False, to get not 
        interactable elements also 
        '''

        if not ignore_case:
            if exact:
                sel = f'//{tag}[text() = "{text}"]'
            else:
                sel = f'//{tag}[contains(text(), "{text}")]'
        else:
            uppers = "".join(sorted(set(text.upper())))
            lowers = "".join(sorted(set(text.lower())))

            if exact:
                sel = (f"""//{tag}[translate(text(), '{uppers}', """
                       f"""'{lowers}') = '{text.lower()}']""")
            else:
                sel = (f"""//{tag}[contains(translate(text(), '{uppers}', """
                       f"""'{lowers}'), '{text.lower()}')]""")

        # print(sel)

        # do not check for interactability
        if not interactable:
            if all_:
                answer = self.xpath(sel)
            else:
                answer = self.xpath1(sel)

        else:
            answer = self.xpath(sel)          

            answer = [i for i in answer if 
                          i.is_displayed() and i.is_enabled()]
            if not all_:
                # raise error if no interactable element found
                answer = answer[0]

        return answer

    def get(self, url, add_protocol=True):
        '''
        load url page.

        if browser is not initialized yet, it will
        start with given options

        if add_protocol is set to False(default=True),
        exact url load will be tried,
        otherwise, if url is not starting
        with http:// or https:// , we will add http://.
        This makes process of page retrieval easier,
        as we do not need to type http:// every time,
        just br.get("example.com") will work.
        '''
        # initialize browser
        self.initialize_browser_if_necessary()

        # add http:// if needed
        if add_protocol:
            if url.split("//")[0].lower() not in ["http:", "https:"]:
                url = "http://" + url

        # get page
        self.br.get(url)

    def log_info(self, text):
        '''
            Log information
        '''

        with open(self.log_file, "a") as f:
            line = f'{time.ctime()} | {text}\n'
            f.write(line)

    def press(self, key, elem=False):
        # ! test !
        '''
            assume that before that, last selection call(css1 or xpath1) was on
            element that we want to click on -->
                to make things easier to use for now
        '''
        # if no argument supplied, last found element will be used
        if not elem:
            # elem = self.elem
            elem = br.css1("body")

        key = getattr(self.keys, key.upper())
        elem.send_keys(key)

    # for now, works on only chrome
    def show_downloads(self):
        '''
        show downloads tab in browser.

        for now, works on chrome only
        '''
        self.get("chrome://downloads/", add_protocol=False)

    def show_history(self):
        '''
        show history tab in browser.

        for now, works on chrome only
        '''
        # breakpoint()
        self.get("chrome://history/", add_protocol=False)

    def show_settings(self):
        '''
        show settings tab in browser.

        for now, works on chrome only
        '''
        self.get("chrome://settings/", add_protocol=False)

    def show_infos(self):
        '''
        show information about browser,
        such as versions, user agent & profile path.

        for now, works on chrome only
        '''
        self.get("chrome://version/", add_protocol=False)

    def ip(self):
        '''
        make duck duck go search to see
        current ip
        '''
        # url = "https://whatismyipaddress.com/"
        url = "https://duckduckgo.com/?q=my+ip&t=h_&ia=answer"
        self.get(url)

    def speed(self):
        '''
        go to website that checks internet speed
        for now it is https://fast.com
        '''
        url = "https://fast.com"
        self.get(url)

    def bcss(self, selector):
        '''
        get elements using bs4 & whole page source
        *it seems faster in most cases

        ##################################################
        good enough approach if only one selection is used
        on a page, otherwise, wait for speed optimization...
        ##################################################
        '''
        soup = bs(self.br.page_source, "lxml")
        return soup.select(selector)

    def bcss1(self, selector):
        '''
        get first match using bs4 & whole page source
        *it seems faster in most cases

        ##################################################
        good enough approach if only one selection is used
        on a page, otherwise, wait for speed optimization...
        ##################################################
        '''
        soup = bs(self.br.page_source, "lxml")
        return soup.select(selector)[0]

    def js(self, comm):
        '''execute given command with javascript'''
        self.br.execute_script(comm)

    def google(self, s=None, domain="com"):
        '''
            Google given text with
            given google country domain
            (default=com)

            if no search string supplied,
            just google page will be opened
        '''
        from urllib.parse import quote

        # url = "google.com"

        if s is None:
            url = f'google.{domain}'
        else:
            q = quote(s)
            url = f'google.{domain}/search?q={q}'

        self.get(url)

    def duck(self, s=None):
        '''
            simillar as google method,
            but using duckduckgo and without
            different domains support
        '''
        from urllib.parse import quote

        # url = "google.com"

        if s is None:
            url = f'duckduckgo.com'
        else:
            q = quote(s)
            url = f'duckduckgo.com/?q={q}'

        self.get(url)

####################################################
# More cool functions here
####################################################
