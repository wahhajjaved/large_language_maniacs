import unittest
from orthrus.commands import *
from orthrusutils.orthrusutils import *

class TestOrthrusCoverage(unittest.TestCase):

    description = 'Test harness'
    orthrusdirname = '.orthrus'

    def test_coverage(self):
        args = parse_cmdline(self.description, ['coverage', '-j', self.add_cmd.jobId])
        cmd = OrthrusCoverage(args, self.config)
        self.assertTrue(cmd.run())
        time.sleep(90)
        subprocess.Popen('ls .orthrus/jobs/'+self.add_cmd.jobId+'/afl-out/cov; genhtml --version', shell=True, executable='/bin/bash')
        self.assertTrue(os.path.isfile(self.orthrusdirname + '/jobs/' + self.add_cmd.jobId + \
                                       '/afl-out/cov/web/lcov-web-final.html'))

    def setUp(self):
        self.config = {'orthrus' : {'directory': self.orthrusdirname}}
        args = parse_cmdline(self.description, ['create', '-fuzz', '-cov'])
        cmd = OrthrusCreate(args, self.config)
        cmd.run()
        args = parse_cmdline(self.description, ['add', '--job=main @@',
                                                '-s=./seeds'])
        self.add_cmd = OrthrusAdd(args, self.config)
        self.assertTrue(self.add_cmd.run())
        args = parse_cmdline(self.description, ['start', '-j', self.add_cmd.jobId])
        start_cmd = OrthrusStart(args, self.config)
        self.assertTrue(start_cmd.run())
        time.sleep(10)
        args = parse_cmdline(self.description, ['stop'])
        cmd = OrthrusStop(args, self.config)
        self.assertTrue(cmd.run())

    def tearDown(self):
        shutil.rmtree(self.orthrusdirname)