#    Copyright 2014 Red Hat, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nova.hacking import checks
from nova import test


class HackingTestCase(test.NoDBTestCase):
    """This class tests the hacking checks in nova.hacking.checks by passing
    strings to the check methods like the pep8/flake8 parser would. The parser
    loops over each line in the file and then passes the parameters to the
    check method. The parameter names in the check method dictate what type of
    object is passed to the check method. The parameter types are::

        logical_line: A processed line with the following modifications:
            - Multi-line statements converted to a single line.
            - Stripped left and right.
            - Contents of strings replaced with "xxx" of same length.
            - Comments removed.
        physical_line: Raw line of text from the input file.
        lines: a list of the raw lines from the input file
        tokens: the tokens that contribute to this logical line
        line_number: line number in the input file
        total_lines: number of lines in the input file
        blank_lines: blank lines before this one
        indent_char: indentation character in this file (" " or "\t")
        indent_level: indentation (with tabs expanded to multiples of 8)
        previous_indent_level: indentation on previous line
        previous_logical: previous logical line
        filename: Path of the file being run through pep8

    When running a test on a check method the return will be False/None if
    there is no violation in the sample input. If there is an error a tuple is
    returned with a position in the line, and a message. So to check the result
    just assertTrue if the check is expected to fail and assertFalse if it
    should pass.
    """
    def test_virt_driver_imports(self):
        self.assertTrue(checks.import_no_virt_driver_import_deps(
            "from nova.virt.libvirt import utils as libvirt_utils",
            "./nova/virt/xenapi/driver.py"))

        self.assertIsNone(checks.import_no_virt_driver_import_deps(
            "from nova.virt.libvirt import utils as libvirt_utils",
            "./nova/virt/libvirt/driver.py"))

        self.assertTrue(checks.import_no_virt_driver_import_deps(
            "import nova.virt.libvirt.utils as libvirt_utils",
            "./nova/virt/xenapi/driver.py"))

        self.assertTrue(checks.import_no_virt_driver_import_deps(
            "import nova.virt.libvirt.utils as libvirt_utils",
            "./nova/virt/xenapi/driver.py"))

        self.assertIsNone(checks.import_no_virt_driver_import_deps(
            "import nova.virt.firewall",
            "./nova/virt/libvirt/firewall.py"))

    def test_virt_driver_config_vars(self):
        self.assertTrue(checks.import_no_virt_driver_config_deps(
            "CONF.import_opt('volume_drivers', "
            "'nova.virt.libvirt.driver', group='libvirt')",
            "./nova/virt/xenapi/driver.py"))

        self.assertIsNone(checks.import_no_virt_driver_config_deps(
            "CONF.import_opt('volume_drivers', "
            "'nova.virt.libvirt.driver', group='libvirt')",
            "./nova/virt/libvirt/volume.py"))

    def test_virt_driver_imports(self):
        self.assertTrue(checks.no_author_tags("# author: jogo"))
        self.assertTrue(checks.no_author_tags("# @author: jogo"))
        self.assertTrue(checks.no_author_tags("# @Author: jogo"))
        self.assertTrue(checks.no_author_tags("# Author: jogo"))
        self.assertTrue(checks.no_author_tags(".. moduleauthor:: jogo"))
        self.assertFalse(checks.no_author_tags("# authorization of this"))
        self.assertEqual(2, checks.no_author_tags("# author: jogo")[0])
        self.assertEqual(2, checks.no_author_tags("# Author: jogo")[0])
        self.assertEqual(3, checks.no_author_tags(".. moduleauthor:: jogo")[0])

    def test_assert_true_instance(self):
        self.assertEqual(len(list(checks.assert_true_instance(
            "self.assertTrue(isinstance(e, "
            "exception.BuildAbortException))"))), 1)

        self.assertEqual(
            len(list(checks.assert_true_instance("self.assertTrue()"))), 0)

    def test_assert_equal_type(self):
        self.assertEqual(len(list(checks.assert_equal_type(
            "self.assertEqual(type(als['QuicAssist']), list)"))), 1)

        self.assertEqual(
            len(list(checks.assert_equal_type("self.assertTrue()"))), 0)

    def test_assert_equal_none(self):
        self.assertEqual(len(list(checks.assert_equal_none(
            "self.assertEqual(A, None)"))), 1)

        self.assertEqual(len(list(checks.assert_equal_none(
            "self.assertEqual(None, A)"))), 1)

        self.assertEqual(
            len(list(checks.assert_equal_none("self.assertIsNone()"))), 0)

    def test_no_translate_debug_logs(self):
        self.assertEqual(len(list(checks.no_translate_debug_logs(
            "LOG.debug(_('foo'))", "nova/scheduler/foo.py"))), 1)

        self.assertEqual(len(list(checks.no_translate_debug_logs(
            "LOG.debug('foo')", "nova/scheduler/foo.py"))), 0)

        self.assertEqual(len(list(checks.no_translate_debug_logs(
            "LOG.info(_('foo'))", "nova/scheduler/foo.py"))), 0)
