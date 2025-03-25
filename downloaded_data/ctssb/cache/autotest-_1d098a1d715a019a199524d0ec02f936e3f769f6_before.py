# This will need more work on the configuration stuff before it will function
import test
from autotest_utils import *

class lmbench(test.test):
	version = 1

	def setup(self, tarball = 'lmbench3.tar.gz'):
		tarball = unmap_url(self.bindir, tarball, self.tmpdir)
		# http://www.bitmover.com/lm/lmbench/lmbench3.tar.gz
		# + lmbench3.diff 
		#	removes Makefile references to bitkeeper
		#	default mail to no, fix job placement defaults (masouds)
		extract_tarball_to_dir(tarball, self.srcdir)
		os.chdir(self.srcdir)

		system('make')


	def execute(self, iterations = 1, mem = '', fastmem = 'NO', 
			slowfs = 'NO', disks = '', disks_desc = '', 
			mhz = '', remote = '', enough = '5000', sync_max = '1',
			fsdir = None, file = None):
		if not fsdir:
			fsdir = self.tmpdir
		if not file:
			file = self.tmpdir+'XXX'

		system("make results")
		cmd = "( cd " + self.srcdir + " && make rerun )"
		for i in range(1, iterations+1):
			system(cmd)

		# Do a profiling run if necessary
		profilers = self.job.profilers
		if profilers.present():
			profilers.start(self)
			system(cmd)
			profilers.stop(self)
			profilers.report(self)
		# Get the results:
		system("make -C " + self.srcdir + "/results summary > summary.txt")
