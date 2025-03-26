#pylint: disable=C0301
#pylint: disable=R0904

import os
import re
try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen

import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.service as service
import osgtest.library.osgunittest as osgunittest


class TestCondorCE(osgunittest.OSGTestCase):

    def setUp(self):
        # Enforce SciToken or GSI auth for testing
        os.environ['_condor_SEC_CLIENT_AUTHENTICATION_METHODS'] = 'SCITOKENS, GSI'
        core.skip_ok_unless_installed('condor', 'htcondor-ce')
        self.skip_bad_unless(service.is_running('condor-ce'), 'ce not running')

        self.command = []
        if core.state['token.condor_write_created']:
            self.command = [f"_condor_SCITOKENS_FILE={core.config['token.condor_write']}"]

    def tearDown(self):
        os.environ.pop('_condor_SEC_CLIENT_AUTHENTICATION_METHODS')

    def check_write_creds(self):
        """Check for credentials necessary for HTCondor-CE WRITE
        """
        self.skip_bad_unless(core.state['proxy.valid'] or core.state['token.condor_write_created'],
                             'requires a scitoken or a proxy')

    def check_schedd_ready(self):
        """Check if the HTCondor-CE schedd is up as expected
        """
        self.skip_bad_unless(core.state['condor-ce.schedd-ready'], 'CE schedd not ready to accept jobs')

    def run_blahp_trace(self, lrms):
        """Run condor_ce_trace() against a non-HTCondor backend and verify the cache"""
        lrms_cache_prefix = {'pbs': 'qstat', 'slurm': 'slurm'}

        cwd = os.getcwd()
        os.chdir('/tmp')
        self.command += ['condor_ce_trace',
                         '-a osgTestBatchSystem = %s' % lrms.lower(),
                         '--debug',
                         core.get_hostname()]
        trace_out, _, _ = core.check_system(self.command, 'ce trace against %s' % lrms.lower(), user=True)

        try:
            backend_jobid = re.search(r'%s_JOBID=(\d+)' % lrms.upper(), trace_out).group(1)
        except AttributeError:
            # failed to find backend job ID
            self.fail('did not run against %s' % lrms.upper())
        cache_file = '/var/tmp/%s_cache_%s/blahp_results_cache' % (lrms_cache_prefix[lrms.lower()],
                                                                   core.options.username)
        with open(cache_file, 'r') as handle:
            cache = handle.read()

        # Verify backend job ID in cache for multiple formats between the different
        # versions of the blahp. For blahp-1.18.16.bosco-1.osg32:
        #
        # 2: [BatchJobId="2"; WorkerNode="fermicloud171.fnal.gov-0"; JobStatus=4; ExitCode= 0; ]\n
        #
        # For blahp-1.18.25.bosco-1.osg33:
        #
        # 5347907	"(dp0
        # S'BatchJobId'
        # p1
        # S'""5347907""'
        # p2
        # sS'WorkerNode'
        # p3
        # S'""node1358""'
        # p4
        # sS'JobStatus'
        # p5
        # S'2'
        # p6
        # s."
        self.assertTrue(re.search(r'BatchJobId[=\s"\'p1S]+%s' % backend_jobid, cache),
                        'Job %s not found in %s blahp cache:\n%s' % (backend_jobid, lrms.upper(), cache))

        os.chdir(cwd)

    def test_01_status(self):
        command = ('condor_ce_status', '-any')
        core.check_system(command, 'ce status', user=True)

    def test_02_queue(self):
        command = ('condor_ce_q', '-verbose')
        core.check_system(command, 'ce queue', user=True)

    def test_03_ping(self):
        self.check_write_creds()
        self.command += ['condor_ce_ping', 'WRITE', '-verbose']
        stdout, _, _ = core.check_system(self.command, 'ping using GSI and gridmap', user=True)
        self.assertTrue(re.search(r'Authorized:\s*TRUE', stdout), 'could not authorize with GSI')

    def test_04_trace(self):
        self.check_schedd_ready()
        self.check_write_creds()

        cwd = os.getcwd()
        os.chdir('/tmp')

        self.command += ['condor_ce_trace', '--debug', core.get_hostname()]
        core.check_system(self.command, 'ce trace', user=True)

        os.chdir(cwd)

    def test_05_pbs_trace(self):
        core.skip_ok_unless_installed('torque-mom', 'torque-server', 'torque-scheduler', 'torque-client', 'munge',
                                      by_dependency=True)
        self.skip_ok_unless(service.is_running('pbs_server'), 'pbs service not running')
        self.check_schedd_ready()
        self.check_write_creds()
        self.run_blahp_trace('pbs')

    def test_06_slurm_trace(self):
        core.skip_ok_unless_installed(core.SLURM_PACKAGES)
        self.skip_bad_unless(core.state['condor-ce.schedd-ready'], 'CE schedd not ready to accept jobs')
        self.skip_ok_unless(service.is_running(core.config['slurm.service-name']), 'slurm service not running')
        self.check_schedd_ready()
        self.check_write_creds()
        self.run_blahp_trace('slurm')

    def test_07_ceview(self):
        core.config['condor-ce.view-listening'] = False
        core.skip_ok_unless_installed('htcondor-ce-view')
        view_url = 'http://%s:%s' % (core.get_hostname(), int(core.config['condor-ce.view-port']))
        try:
            src = core.to_str(urlopen(view_url).read())
            core.log_message(src)
        except EnvironmentError as err:
            debug_file = '/var/log/condor-ce/CEViewLog'
            debug_contents = 'Contents of %s\n%s\n' % (debug_file, '=' * 20)
            try:
                debug_contents += files.read(debug_file, True)
            except EnvironmentError:
                debug_contents += 'Failed to read %s\n' % debug_file
            core.log_message(debug_contents)
            self.fail('Could not reach HTCondor-CE View at %s: %s' % (view_url, err))
        self.assertTrue(re.search(r'HTCondor-CE Overview', src), 'Failed to find expected CE View contents')
        core.config['condor-ce.view-listening'] = True
