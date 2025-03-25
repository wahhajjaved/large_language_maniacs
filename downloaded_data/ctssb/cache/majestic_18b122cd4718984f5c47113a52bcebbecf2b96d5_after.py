import os
import pathlib
import unittest

import majestic

MAJESTIC_DIR = pathlib.Path(__file__).resolve().parent
TEST_BLOG_DIR = MAJESTIC_DIR.joinpath('test-blog')

class TestLoadSettings(unittest.TestCase):
    """Default and site-specific settings tests"""
    def setUp(self):
        os.chdir(str(MAJESTIC_DIR))

    def test_load_default_settings(self):
        """Config class contains setting set only in default .cfg file"""
        settings = majestic.load_settings(default=True, local=False)
        self.assertTrue(settings.getboolean('testing', 'default cfg loaded'))

    def test_load_specific_only(self):
        """When given filenames, load only those files"""
        test_settings_fn = str(TEST_BLOG_DIR.joinpath('settings.cfg'))
        settings = majestic.load_settings(default=False, local=False,
                                          files=[test_settings_fn])
        self.assertTrue(settings.getboolean('testing', 'test-blog cfg loaded'))

    def test_load_default_and_local(self):
        """Properly load defaults and settings.cfg in current directory"""
        os.chdir(str(TEST_BLOG_DIR))
        settings = majestic.load_settings(default=True, local=True)
        self.assertTrue(settings.getboolean('testing', 'test-blog cfg loaded'))
        self.assertTrue(settings.getboolean('testing', 'default cfg loaded'))

    def test_defaults_overriden_by_local(self):
        """Config files loaded in order so that locals override defaults"""
        default_cfg = str(MAJESTIC_DIR.joinpath('majestic.cfg'))
        default_settings = majestic.load_settings(default=True, local=False)
        overridden_value = default_settings.getboolean('testing',
                                                       'overridden setting')
        self.assertFalse(overridden_value)
        os.chdir(str(TEST_BLOG_DIR))
        combined_settings = majestic.load_settings()
        overridden_value = combined_settings.getboolean('testing',
                                                        'overridden setting')
        self.assertTrue(overridden_value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
