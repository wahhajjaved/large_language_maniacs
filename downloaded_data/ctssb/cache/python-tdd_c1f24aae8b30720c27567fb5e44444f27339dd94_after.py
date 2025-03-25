import platform
import os

from selenium import webdriver


def make_driver(browser_type='chrome'):
    system_type = platform.system()
    src_dir = os.path.dirname(os.path.abspath(__file__))
    executable_dir = os.path.join(src_dir, '.', 'chromedriver')
    if browser_type in ['chrome', 'h_chrome']:
        options = webdriver.ChromeOptions()
        options.add_argument('window-size=800x600')
        if browser_type == "h_chrome":
            options.add_argument('headless')
            options.add_argument("disable-gpu")

        if system_type == 'Linux':
            executable_name = 'chromedriver_linux64'
        elif system_type == 'Darwin':
            executable_name = 'chromedriver_mac64'
        else:
            raise NameError('Unknown system type: {}'.format(system_type))
        executable_path = os.path.join(executable_dir, executable_name)

        driver = webdriver.Chrome(executable_path=executable_path,
                                  options=options,
                                  service_log_path=os.path.devnull)
    else:
        raise ValueError("Unknown browser : %s" % browser_type)
    return driver
