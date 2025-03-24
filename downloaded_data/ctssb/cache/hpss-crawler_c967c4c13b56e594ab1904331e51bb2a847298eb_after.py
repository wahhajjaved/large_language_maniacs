from hpssic import messages as MSG
import os
import pdb
import pexpect
import re
import sys
from hpssic import testhelp as th
from hpssic import util as U

M = sys.modules['__main__']
if 'py.test' in M.__file__:
    import pytest
    attr = pytest.mark.attr
else:
    from nose.plugins.attrib import attr


# -----------------------------------------------------------------------------
class ScriptBase(th.HelpedTestCase):
    # -------------------------------------------------------------------------
    def script_which_module(self, modname):
        """
        ScriptBase: Make sure we're loading the right tcc module
        """
        try:
            mod = sys.modules[modname]
        except KeyError:
            sep = impname = ''
            for comp in modname.split('.'):
                impname += sep + comp
                sep = '.'
                __import__(impname)
            mod = sys.modules[modname]

        tdir = improot(__file__, __name__)
        mdir = improot(mod.__file__, modname)
        self.assertEqual(tdir, mdir, "Expected '%s', got '%s'" % (tdir, mdir))

    # -------------------------------------------------------------------------
    def script_which_command(self, cmdname):
        """
        ScriptBase: Make sure the tcc command exists and is executable
        """
        cmd = pexpect.which(cmdname)
        if cmd is None:
            cmd = "bin/" + cmdname
        self.assertTrue(os.access(cmd, os.X_OK))

    # -------------------------------------------------------------------------
    def script_help(self, cmdname, helplist):
        """
        ScriptBase: Make sure 'tcc help' generates something reasonable
        """
        cmd = pexpect.which(cmdname)
        if cmd is None:
            cmd = "bin/" + cmdname
        result = pexpect.run("%s help" % cmd)
        self.assertFalse("Traceback" in result,
                         "'Traceback' not expected in %s" %
                         U.line_quote(result))
        for item in helplist:
            self.assertTrue(item in result,
                            "Expected '%s' in '%s'" % (item, result))


# -----------------------------------------------------------------------------
class Test_CRAWL(ScriptBase):
    # -------------------------------------------------------------------------
    def test_crawl_syspath(self):
        result = pexpect.run("crawl syspath")
        # self.fail('here we are')
        pass

    # -------------------------------------------------------------------------
    def test_crawl_which_lib(self):
        """
        Test_CRAWL:
        """
        super(Test_CRAWL, self).script_which_module("hpssic.crawl_lib")

    # -------------------------------------------------------------------------
    def test_crawl_which_module(self):
        """
        Test_CRAWL:
        """
        super(Test_CRAWL, self).script_which_module("hpssic.crawl")

    # -------------------------------------------------------------------------
    def test_crawl_which_command(self):
        """
        Test_CRAWL:
        """
        super(Test_CRAWL, self).script_which_command("crawl")

    # -------------------------------------------------------------------------
    def test_crawl_help(self):
        """
        Test_CRAWL:
        """
        super(Test_CRAWL, self).script_help("crawl",
                                            ["cfgdump - ",
                                             "cleanup - ",
                                             "dbdrop - ",
                                             "fire - ",
                                             "log - ",
                                             "pw_decode - ",
                                             "pw_encode - ",
                                             "start - ",
                                             "status - ",
                                             "stop - ",
                                             ])


# -----------------------------------------------------------------------------
class Test_CV(ScriptBase):
    # -------------------------------------------------------------------------
    def test_cv_help(self):
        """
        Test_CV:
        """
        super(Test_CV, self).script_help("cv",
                                         ["fail_reset - ",
                                          "nulltest - ",
                                          "report - ",
                                          "show_next - ",
                                          "simplug - ",
                                          "test_check - ",
                                          ])

    # -------------------------------------------------------------------------
    def test_cv_which_command(self):
        """
        Test_CV:
        """
        super(Test_CV, self).script_which_command("cv")

    # -------------------------------------------------------------------------
    def test_cv_which_module(self):
        """
        Test_CV:
        """
        super(Test_CV, self).script_which_module("hpssic.cv")

    # -------------------------------------------------------------------------
    def test_cv_which_plugin(self):
        """
        Test_CV:
        """
        super(Test_CV, self).script_which_module("hpssic.plugins.cv_plugin")


# -----------------------------------------------------------------------------
class Test_MPRA(ScriptBase):
    # -------------------------------------------------------------------------
    def test_mpra_help(self):
        """
        Test_MPRA:
        """
        super(Test_MPRA, self).script_help("mpra",
                                           ["age - ",
                                            "date_age - ",
                                            "epoch - ",
                                            "history - ",
                                            "migr_recs - ",
                                            "purge_recs - ",
                                            "reset - ",
                                            "simplug - ",
                                            "times - ",
                                            "xplocks - ",
                                            "ymd",
                                            ])

    # -------------------------------------------------------------------------
    def test_mpra_which_command(self):
        """
        Test_MPRA:
        """
        super(Test_MPRA, self).script_which_command("mpra")

    # -------------------------------------------------------------------------
    def test_mpra_which_lib(self):
        """
        Test_MPRA:
        """
        super(Test_MPRA, self).script_which_module("hpssic.mpra_lib")

    # -------------------------------------------------------------------------
    def test_mpra_which_module(self):
        """
        Test_MPRA:
        """
        super(Test_MPRA, self).script_which_module("hpssic.mpra")

    # -------------------------------------------------------------------------
    def test_mpra_which_plugin(self):
        """
        Test_MPRA:
        """
        super(Test_MPRA, self).script_which_module(
            "hpssic.plugins.mpra_plugin")


# -----------------------------------------------------------------------------
class Test_RPT(ScriptBase):
    # -------------------------------------------------------------------------
    def test_rpt_help(self):
        """
        Test_RPT:
        """
        super(Test_RPT, self).script_help("rpt",
                                          ["report - ",
                                           "simplug - ",
                                           "testmail - ",
                                           ])

    # -------------------------------------------------------------------------
    def test_rpt_which_command(self):
        """
        Test_RPT:
        """
        super(Test_RPT, self).script_which_command("rpt")

    # -------------------------------------------------------------------------
    def test_rpt_which_lib(self):
        """
        Test_RPT:
        """
        super(Test_RPT, self).script_which_module("hpssic.rpt_lib")

    # -------------------------------------------------------------------------
    def test_rpt_which_module(self):
        """
        Test_RPT:
        """
        super(Test_RPT, self).script_which_module("hpssic.rpt")

    # -------------------------------------------------------------------------
    def test_rpt_which_plugin(self):
        """
        Test_RPT:
        """
        super(Test_RPT, self).script_which_module("hpssic.plugins.rpt_plugin")


# -----------------------------------------------------------------------------
class Test_TCC(ScriptBase):
    # -------------------------------------------------------------------------
    def test_tcc_help(self):
        """
        Test_TCC:
        """
        super(Test_TCC, self).script_help("tcc",
                                          ["bfid - ",
                                           "bfpath - ",
                                           "copies_by_cos - ",
                                           "copies_by_file - ",
                                           "report - ",
                                           "selbf - ",
                                           "simplug - ",
                                           "tables - ",
                                           "zreport - ",
                                           ])

    # -------------------------------------------------------------------------
    def test_tcc_which_command(self):
        """
        Test_TCC:
        """
        super(Test_TCC, self).script_which_command("tcc")

    # -------------------------------------------------------------------------
    def test_tcc_which_lib(self):
        """
        Test_TCC:
        """
        super(Test_TCC, self).script_which_module("hpssic.tcc_lib")

    # -------------------------------------------------------------------------
    def test_tcc_which_module(self):
        """
        Test_TCC:
        """
        super(Test_TCC, self).script_which_module("hpssic.tcc")

    # -------------------------------------------------------------------------
    def test_tcc_which_plugin(self):
        """
        Test_TCC:
        """
        super(Test_TCC, self).script_which_module("hpssic.plugins.tcc_plugin")


# -----------------------------------------------------------------------------
class Test_MISC(th.HelpedTestCase):
    # -------------------------------------------------------------------------
    def test_duplicates(self):
        """
        Scan all .py files for duplicate function names
        """
        dupl = {}
        for r, d, f in os.walk('hpssic'):
            for fname in f:
                path = os.path.join(r, fname)
                if "CrawlDBI" in path:
                    continue
                if path.endswith(".py") and not fname.startswith(".#"):
                    result = check_for_duplicates(path)
                    if result != '':
                        dupl[path] = result
        if dupl != {}:
            rpt = ''
            for key in dupl:
                rpt += "Duplicates in %s:" % key + dupl[key] + "\n"
            self.fail(rpt)

    # -------------------------------------------------------------------------
    @attr(slow=True)
    def test_pep8(self):
        full_result = ""
        for r, d, f in os.walk('hpssic'):
            pylist = [os.path.abspath(os.path.join(r, fn))
                      for fn in f
                      if fn.endswith('.py') and not fn.startswith(".#")]
            inputs = " ".join(pylist)
            if any([r == "./test",
                    ".git" in r,
                    ".attic" in r,
                    "" == inputs]):
                continue
            result = pexpect.run("pep8 %s" % inputs)
            full_result += result.replace(MSG.cov_no_data, "")
        self.assertEqual("", full_result, "\n" + full_result)


# -----------------------------------------------------------------------------
@U.memoize
def defrgx(obarg):
    """
    Return a compiled regex for finding function definitions
    """
    return re.compile("^\s*def\s+(\w+)\s*\(")


# -----------------------------------------------------------------------------
def check_for_duplicates(path):
    """
    Scan *path* for duplicate function names
    """
    rgx = defrgx(0)
    flist = []
    rval = ''
    with open(path, 'r') as f:
        for l in f.readlines():
            q = rgx.match(l)
            if q:
                flist.append(q.groups()[0])
    if len(flist) != len(set(flist)):
        flist.sort()
        last = ''
        for foof in flist:
            if last == foof and foof != '__init__':
                rval += "\n   %s" % foof
            last = foof
    return rval


# -----------------------------------------------------------------------------
def improot(path, modpath):
    """
    Navigate upward in *path* as many levels as there are in *modpath*
    """
    rval = path
    for x in modpath.split('.'):
        rval = os.path.dirname(rval)
    return rval
