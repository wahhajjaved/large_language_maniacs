# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

import os
import sys

import io
import locale
import shutil
import subprocess
import tempfile
import unittest

import lxml.html
import pytest

from nikola import __main__
import nikola
import nikola.plugins.command
import nikola.plugins.command.init
import nikola.utils

from .base import BaseTestCase, cd, LocaleSupportInTesting

LocaleSupportInTesting.initialize()


class EmptyBuildTest(BaseTestCase):
    """Basic integration testcase."""

    dataname = None

    @classmethod
    def setUpClass(cls):
        """Setup a demo site."""
        # for tests that need bilingual support override language_settings
        cls.language_settings()
        cls.startdir = os.getcwd()
        cls.tmpdir = tempfile.mkdtemp()
        cls.target_dir = os.path.join(cls.tmpdir, "target")
        cls.init_command = nikola.plugins.command.init.CommandInit()
        cls.fill_site()
        cls.patch_site()
        cls.build()

    @classmethod
    def language_settings(cls):
        LocaleSupportInTesting.initialize_locales_for_testing("unilingual")

    @classmethod
    def fill_site(self):
        """Add any needed initial content."""
        self.init_command.create_empty_site(self.target_dir)
        self.init_command.create_configuration(self.target_dir)

        if self.dataname:
            src = os.path.join(os.path.dirname(__file__), 'data',
                               self.dataname)
            for root, dirs, files in os.walk(src):
                for src_name in files:
                    rel_dir = os.path.relpath(root, src)
                    dst_file = os.path.join(self.target_dir, rel_dir, src_name)
                    src_file = os.path.join(root, src_name)
                    shutil.copy2(src_file, dst_file)

    @classmethod
    def patch_site(self):
        """Make any modifications you need to the site."""

    @classmethod
    def build(self):
        """Build the site."""
        with cd(self.target_dir):
            __main__.main(["build"])

    @classmethod
    def tearDownClass(self):
        """Remove the demo site."""
        # Don't saw off the branch you're sitting on!
        os.chdir(self.startdir)
        # ignore_errors=True for windows by issue #782
        shutil.rmtree(self.tmpdir, ignore_errors=(sys.platform == 'win32'))
        # Fixes Issue #438
        try:
            del sys.modules['conf']
        except KeyError:
            pass
        # clear LocaleBorg state
        nikola.utils.LocaleBorg.reset()
        if hasattr(self.__class__, "ol"):
            delattr(self.__class__, "ol")

    def test_build(self):
        """Ensure the build did something."""
        index_path = os.path.join(
            self.target_dir, "output", "archive.html")
        self.assertTrue(os.path.isfile(index_path))


class DemoBuildTest(EmptyBuildTest):
    """Test that a default build of --demo works."""

    @classmethod
    def fill_site(self):
        """Fill the site with demo content."""
        self.init_command.copy_sample_site(self.target_dir)
        self.init_command.create_configuration(self.target_dir)
        # File for Issue #374 (empty post text)
        with io.open(os.path.join(self.target_dir, 'posts', 'empty.txt'), "w+", encoding="utf8") as outf:
            outf.write(
                ".. title: foobar\n"
                ".. slug: foobar\n"
                ".. date: 2013-03-06 19:08:15\n"
            )

    def test_index_in_sitemap(self):
        sitemap_path = os.path.join(self.target_dir, "output", "sitemap.xml")
        sitemap_data = io.open(sitemap_path, "r", encoding="utf8").read()
        self.assertTrue('<loc>http://getnikola.com/index.html</loc>' in sitemap_data)

    def test_avoid_double_slash_in_rss(self):
        rss_path = os.path.join(self.target_dir, "output", "rss.xml")
        rss_data = io.open(rss_path, "r", encoding="utf8").read()
        self.assertFalse('http://getnikola.com//' in rss_data)


class RepeatedPostsSetting(DemoBuildTest):
    """Duplicate POSTS, should not read each post twice, which causes conflicts."""
    @classmethod
    def patch_site(self):
        """Set the SITE_URL to have a path"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "a", encoding="utf8") as outf:
            outf.write('\nPOSTS = (("posts/*.txt", "posts", "post.tmpl"),("posts/*.txt", "posts", "post.tmpl"))\n')


class FuturePostTest(EmptyBuildTest):
    """Test a site with future posts."""

    @classmethod
    def fill_site(self):
        import datetime
        from nikola.utils import current_time
        self.init_command.copy_sample_site(self.target_dir)
        self.init_command.create_configuration(self.target_dir)

        # Change COMMENT_SYSTEM_ID to not wait for 5 seconds
        with io.open(os.path.join(self.target_dir, 'conf.py'), "a+", encoding="utf8") as outf:
            outf.write('\nCOMMENT_SYSTEM_ID = "nikolatest"\n')

        with io.open(os.path.join(self.target_dir, 'posts', 'empty1.txt'), "w+", encoding="utf8") as outf:
            outf.write(
                ".. title: foo\n"
                ".. slug: foo\n"
                ".. date: %s\n" % (current_time() + datetime.timedelta(-1)).strftime('%Y-%m-%d %H:%M:%S')
            )

        with io.open(os.path.join(self.target_dir, 'posts', 'empty2.txt'), "w+", encoding="utf8") as outf:
            outf.write(
                ".. title: bar\n"
                ".. slug: bar\n"
                ".. date: %s\n" % (current_time() + datetime.timedelta(1)).strftime('%Y-%m-%d %H:%M:%S')
            )

    def test_future_post(self):
        """ Ensure that the future post is not present in the index and sitemap."""
        index_path = os.path.join(self.target_dir, "output", "index.html")
        sitemap_path = os.path.join(self.target_dir, "output", "sitemap.xml")
        foo_path = os.path.join(self.target_dir, "output", "posts", "foo.html")
        bar_path = os.path.join(self.target_dir, "output", "posts", "bar.html")
        self.assertTrue(os.path.isfile(index_path))
        self.assertTrue(os.path.isfile(foo_path))
        self.assertTrue(os.path.isfile(bar_path))
        index_data = io.open(index_path, "r", encoding="utf8").read()
        sitemap_data = io.open(sitemap_path, "r", encoding="utf8").read()
        self.assertTrue('foo.html' in index_data)
        self.assertFalse('bar.html' in index_data)
        self.assertTrue('foo.html' in sitemap_data)
        self.assertFalse('bar.html' in sitemap_data)

        # Run deploy command to see if future post is deleted
        with cd(self.target_dir):
            __main__.main(["deploy"])

        self.assertTrue(os.path.isfile(index_path))
        self.assertTrue(os.path.isfile(foo_path))
        self.assertFalse(os.path.isfile(bar_path))


class TranslatedBuildTest(EmptyBuildTest):
    """Test a site with translated content."""

    dataname = "translated_titles"

    @classmethod
    def language_settings(cls):
        LocaleSupportInTesting.initialize_locales_for_testing("bilingual")
        # the other language
        cls.ol = LocaleSupportInTesting.langlocales["other"][0]

    def test_translated_titles(self):
        """Check that translated title is picked up."""
        en_file = os.path.join(self.target_dir, "output", "stories", "1.html")
        pl_file = os.path.join(self.target_dir, "output", self.ol, "stories", "1.html")
        # Files should be created
        self.assertTrue(os.path.isfile(en_file))
        self.assertTrue(os.path.isfile(pl_file))
        # And now let's check the titles
        with io.open(en_file, 'r', encoding='utf8') as inf:
            doc = lxml.html.parse(inf)
            self.assertEqual(doc.find('//title').text, 'Foo | Demo Site')
        with io.open(pl_file, 'r', encoding='utf8') as inf:
            doc = lxml.html.parse(inf)
            self.assertEqual(doc.find('//title').text, 'Bar | Demo Site')


class TranslationsPatternTest1(TranslatedBuildTest):
    """Check that the path.lang.ext TRANSLATIONS_PATTERN works too"""

    @classmethod
    def patch_site(self):
        """Set the TRANSLATIONS_PATTERN to the old v6 default"""
        os.rename(os.path.join(self.target_dir, "stories", "1.%s.txt" % self.ol),
                  os.path.join(self.target_dir, "stories", "1.txt.%s" % self.ol)
                  )
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('TRANSLATIONS_PATTERN = "{path}.{lang}.{ext}"',
                                'TRANSLATIONS_PATTERN = "{path}.{ext}.{lang}"')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)


class MissingDefaultLanguageTest(TranslatedBuildTest):
    """Make sure posts only in secondary languages work."""

    @classmethod
    def fill_site(self):
        super(MissingDefaultLanguageTest, self).fill_site()
        os.unlink(os.path.join(self.target_dir, "stories", "1.txt"))

    def test_translated_titles(self):
        """Do not test titles as we just removed the translation"""
        pass


class TranslationsPatternTest2(TranslatedBuildTest):
    """Check that the path_lang.ext TRANSLATIONS_PATTERN works too"""

    @classmethod
    def patch_site(self):
        """Set the TRANSLATIONS_PATTERN to the old v6 default"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        os.rename(os.path.join(self.target_dir, "stories", "1.%s.txt" % self.ol),
                  os.path.join(self.target_dir, "stories", "1.txt.%s" % self.ol)
                  )
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('TRANSLATIONS_PATTERN = "{path}.{lang}.{ext}"',
                                'TRANSLATIONS_PATTERN = "{path}.{ext}.{lang}"')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)


class RelativeLinkTest(DemoBuildTest):
    """Check that SITE_URL with a path doesn't break links."""

    @classmethod
    def patch_site(self):
        """Set the SITE_URL to have a path"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('SITE_URL = "http://getnikola.com/"',
                                'SITE_URL = "http://getnikola.com/foo/bar/"')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)

    def test_relative_links(self):
        """Check that the links in output/index.html are correct"""
        test_path = os.path.join(self.target_dir, "output", "index.html")
        flag = False
        with open(test_path, "rb") as inf:
            data = inf.read()
            for _, _, url, _ in lxml.html.iterlinks(data):
                # Just need to be sure this one is ok
                if url.endswith("css"):
                    self.assertFalse(url.startswith(".."))
                    flag = True
        # But I also need to be sure it is there!
        self.assertTrue(flag)

    def test_index_in_sitemap(self):
        """Test that the correct path is in sitemap, and not the wrong one."""
        sitemap_path = os.path.join(self.target_dir, "output", "sitemap.xml")
        sitemap_data = io.open(sitemap_path, "r", encoding="utf8").read()
        self.assertFalse('<loc>http://getnikola.com/</loc>' in sitemap_data)
        self.assertTrue('<loc>http://getnikola.com/foo/bar/index.html</loc>' in sitemap_data)


class TestCheck(DemoBuildTest):
    """The demo build should pass 'nikola check'"""

    def test_check_links(self):
        with cd(self.target_dir):
            try:
                __main__.main(['check', '-l'])
            except SystemExit as e:
                self.assertEqual(e.code, 0)

    def test_check_files(self):
        with cd(self.target_dir):
            try:
                __main__.main(['check', '-f'])
            except SystemExit as e:
                self.assertEqual(e.code, 0)


class TestCheckAbsoluteSubFolder(TestCheck):
    """Validate links in a site which is:

    * built in URL_TYPE="absolute"
    * deployable to a subfolder (BASE_URL="http://getnikola.com/foo/")
    """

    @classmethod
    def patch_site(self):
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('SITE_URL = "http://getnikola.com/"',
                                'SITE_URL = "http://getnikola.com/foo/"')
            data = data.replace("# URL_TYPE = 'rel_path'",
                                "URL_TYPE = 'absolute'")
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)
            outf.flush()

    def test_index_in_sitemap(self):
        """Test that the correct path is in sitemap, and not the wrong one."""
        sitemap_path = os.path.join(self.target_dir, "output", "sitemap.xml")
        sitemap_data = io.open(sitemap_path, "r", encoding="utf8").read()
        self.assertTrue('<loc>http://getnikola.com/foo/index.html</loc>' in sitemap_data)


class TestCheckFullPathSubFolder(TestCheckAbsoluteSubFolder):
    """Validate links in a site which is:

    * built in URL_TYPE="full_path"
    * deployable to a subfolder (BASE_URL="http://getnikola.com/foo/")
    """

    @classmethod
    def patch_site(self):
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('SITE_URL = "http://getnikola.com/"',
                                'SITE_URL = "http://getnikola.com/foo/"')
            data = data.replace("# URL_TYPE = 'rel_path'",
                                "URL_TYPE = 'full_path'")
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)
            outf.flush()


class TestCheckFailure(DemoBuildTest):
    """The demo build should pass 'nikola check'"""

    def test_check_links_fail(self):
        with cd(self.target_dir):
            os.unlink(os.path.join("output", "archive.html"))
            try:
                __main__.main(['check', '-l'])
            except SystemExit as e:
                self.assertNotEqual(e.code, 0)

    def test_check_files_fail(self):
        with cd(self.target_dir):
            with io.open(os.path.join("output", "foobar"), "w+", encoding="utf8") as outf:
                outf.write("foo")
            try:
                __main__.main(['check', '-f'])
            except SystemExit as e:
                self.assertNotEqual(e.code, 0)


class RelativeLinkTest2(DemoBuildTest):
    """Check that dropping stories to the root doesn't break links."""

    @classmethod
    def patch_site(self):
        """Set the SITE_URL to have a path"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('("stories/*.txt", "stories", "story.tmpl"),',
                                '("stories/*.txt", "", "story.tmpl"),')
            data = data.replace('("stories/*.rst", "stories", "story.tmpl"),',
                                '("stories/*.rst", "", "story.tmpl"),')
            data = data.replace('# INDEX_PATH = ""',
                                'INDEX_PATH = "blog"')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)
            outf.flush()

    def test_relative_links(self):
        """Check that the links in a story are correct"""
        test_path = os.path.join(self.target_dir, "output", "about-nikola.html")
        flag = False
        with open(test_path, "rb") as inf:
            data = inf.read()
            for _, _, url, _ in lxml.html.iterlinks(data):
                # Just need to be sure this one is ok
                if url.endswith("css"):
                    self.assertFalse(url.startswith(".."))
                    flag = True
        # But I also need to be sure it is there!
        self.assertTrue(flag)

    def test_index_in_sitemap(self):
        """Test that the correct path is in sitemap, and not the wrong one."""
        sitemap_path = os.path.join(self.target_dir, "output", "sitemap.xml")
        sitemap_data = io.open(sitemap_path, "r", encoding="utf8").read()
        self.assertFalse('<loc>http://getnikola.com/</loc>' in sitemap_data)
        self.assertTrue('<loc>http://getnikola.com/blog/index.html</loc>' in sitemap_data)


class MonthlyArchiveTest(DemoBuildTest):
    """Check that the monthly archives build and are correct."""

    @classmethod
    def patch_site(self):
        """Set the SITE_URL to have a path"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('# CREATE_MONTHLY_ARCHIVE = False',
                                'CREATE_MONTHLY_ARCHIVE = True')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)
            outf.flush()

    def test_monthly_archive(self):
        """See that it builds"""
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, 'target', 'output', '2012', '03', 'index.html')))


class DayArchiveTest(DemoBuildTest):
    """Check that per-day archives build and are correct."""

    @classmethod
    def patch_site(self):
        """Set the SITE_URL to have a path"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('# ADD_DAY_ARCHIVES = False',
                                'ADD_DAY_ARCHIVES = True')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)
            outf.flush()

    def test_day_archive(self):
        """See that it builds"""
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, 'target', 'output', '2012', '03', '30', 'index.html')))


class FullArchiveTest(DemoBuildTest):
    """Check that full archives build and are correct."""

    @classmethod
    def patch_site(self):
        """Set the SITE_URL to have a path"""
        conf_path = os.path.join(self.target_dir, "conf.py")
        with io.open(conf_path, "r", encoding="utf-8") as inf:
            data = inf.read()
            data = data.replace('# CREATE_FULL_ARCHIVES = False',
                                'CREATE_FULL_ARCHIVES = True')
        with io.open(conf_path, "w+", encoding="utf8") as outf:
            outf.write(data)
            outf.flush()

    def test_full_archive(self):
        """See that it builds"""
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, 'target', 'output', 'archive.html')))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, 'target', 'output', '2012', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, 'target', 'output', '2012', '03', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, 'target', 'output', '2012', '03', '30', 'index.html')))


class SubdirRunningTest(DemoBuildTest):
    """Check that running nikola from subdir works."""

    def test_subdir_run(self):
        """Check whether build works from posts/"""

        with cd(os.path.join(self.target_dir, 'posts')):
            result = __main__.main(['build'])
            self.assertEquals(result, 0)


class InvariantBuildTest(EmptyBuildTest):
    """Test that a default build of --demo works."""

    @classmethod
    def build(self):
        """Build the site."""
        try:
            self.oldlocale = locale.getlocale()
            locale.setlocale(locale.LC_ALL, ("en_US", "utf8"))
        except:
            pytest.skip('no en_US locale!')
        else:
            with cd(self.target_dir):
                __main__.main(["build", "--invariant"])
        finally:
            try:
                locale.setlocale(locale.LC_ALL, self.oldlocale)
            except:
                pass

    @classmethod
    def fill_site(self):
        """Fill the site with demo content."""
        self.init_command.copy_sample_site(self.target_dir)
        self.init_command.create_configuration(self.target_dir)
        os.system('rm "{0}/stories/creating-a-theme.rst" "{0}/stories/extending.txt" "{0}/stories/internals.txt" "{0}/stories/manual.rst" "{0}/stories/social_buttons.txt" "{0}/stories/theming.rst" "{0}/stories/upgrading-to-v6.txt"'.format(self.target_dir))

    def test_invariance(self):
        """Compare the output to the canonical output."""
        if sys.version_info[0:2] != (2, 7):
            pytest.skip('only python 2.7 is supported right now')
        good_path = os.path.join(os.path.dirname(__file__), 'data', 'baseline{0[0]}.{0[1]}'.format(sys.version_info))
        if not os.path.exists(good_path):
            pytest.skip('no baseline found')
        with cd(self.target_dir):
            try:
                diff = subprocess.check_output(['diff', '-ubwr', good_path, 'output'])
                self.assertEqual(diff.strip(), '')
            except subprocess.CalledProcessError as exc:
                print('Unexplained diff for the invariance test. (-canonical +built)')
                print(exc.output.decode('utf-8'))
                self.assertEqual(exc.returncode, 0, 'Unexplained diff for the invariance test.')


if __name__ == "__main__":
    unittest.main()
