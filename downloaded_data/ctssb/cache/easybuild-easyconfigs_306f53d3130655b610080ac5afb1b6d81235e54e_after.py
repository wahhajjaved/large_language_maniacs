##
# Copyright 2009-2012 Stijn Deweirdt, Dries Verdegem, Kenneth Hoste, Pieter De Baets, Jens Timmerman
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
import fileinput
import os
import re
import sys
from easybuild.framework.application import Application
from easybuild.tools.filetools import patch_perl_script_autoflush, run_cmd, run_cmd_qa
from easybuild.easyblocks.n.netcdf import set_netcdf_env_vars, get_netcdf_module_set_cmds

class WRF(Application):
    """Support for building/installing WRF."""

    def __init__(self,*args,**kwargs):
        """Add extra config options specific to WRF."""

        Application.__init__(self, args,kwargs)
        
        self.build_in_installdir = True

        self.wrfsubdir = None

        self.cfg.update({
                         'buildtype':[None, "Specify the type of build (serial, smpar (OpenMP), dmpar (MPI), dm+sm (hybrid OpenMP/MPI))."],
                         'rewriteopts':[True, "Replace default -O3 option in configure.wrf with CFLAGS/FFLAGS from environment (default: True)."],
                         'runtest':[True, "Build and run WRF tests (default: True)."]
                         })

    def configure(self):        
        """Configure build: 
            - set some magic environment variables
            - run configure script
            - adjust configure.wrf file if needed
        """

        # netCDF dependency
        set_netcdf_env_vars(self.log)

        # HDF5 (optional) dependency
        hdf5 = os.getenv('SOFTROOTHDF5')
        if hdf5:
            # check if this is parallel HDF5
            phdf5_bins = ['h5pcc','ph5diff']
            parallel_hdf5 = True
            for f in phdf5_bins:
                if not os.path.exists(os.path.join(hdf5, 'bin', f)):
                    parallel_hdf5 = False
                    break
            if not (hdf5 or parallel_hdf5):
                self.log.error("Parallel HDF5 module not loaded?")
            else:
                os.putenv('PHDF5', hdf5)
        else:
            self.log.info("HDF5 module not loaded, assuming that's OK...")

        # enable support for large file support in netCDF
        os.putenv('WRFIO_NCD_LARGE_FILE_SUPPORT', '1')

        # patch arch/Config_new.pl script, so that run_cmd_qa receives all output to answer questions
        patch_perl_script_autoflush(os.path.join("arch", "Config_new.pl"))

        # determine build type option to look for
        build_type_option = None
        if self.tk.toolkit_comp_family() == "Intel":
            build_type_option = "Linux x86_64 i486 i586 i686, ifort compiler with icc"

        elif self.tk.toolkit_comp_family() == "GCC":
            build_type_option = "x86_64 Linux, gfortran compiler with gcc"

        else:
            self.log.error("Don't know how to figure out build type to select.")

        # fetch selected build type (and make sure it makes sense)
        knownbuildtypes = ['serial', 'smpar', 'dmpar', 'dm+sm']
        bt = self.getcfg('buildtype')

        if not bt in knownbuildtypes:
            self.log.error("Unknown build type: '%s'. Supported build types: %s" % (bt, knownbuildtypes))

        # fetch option number based on build type option and selected build type
        build_type_question = "\s*(?P<nr>[0-9]+).\s*%s\s*\(%s\)" % (build_type_option, bt)

        # run configure script
        cmd = "./configure"
        qa = {
              # named group in match will be used to construct answer
              "Compile for nesting? (1=basic, 2=preset moves, 3=vortex following) [default 1]:":"1",
              "Compile for nesting? (0=no nesting, 1=basic, 2=preset moves, 3=vortex following) [default 0]:":"0"
              }
        no_qa = []
        std_qa = {
                  # named group in match will be used to construct answer
                  r"%s.*\n(.*\n)*Enter selection\s*\[[0-9]+-[0-9]+\]\s*:" % build_type_question:"%(nr)s",
                  }

        run_cmd_qa(cmd, qa, no_qa=no_qa, std_qa=std_qa, log_all=True, simple=True)

        cfgfile= 'configure.wrf'

        # make sure correct compilers are being used
        comps = {
                 'SCC':os.getenv('CC'),
                 'SFC':os.getenv('F90'),
                 'CCOMP':os.getenv('CC'),
                 'DM_FC':os.getenv('MPIF90'),
                 'DM_CC':"%s -DMPI2_SUPPORT" % os.getenv('MPICC'),
                 }
        for line in fileinput.input(cfgfile, inplace=1, backup='.orig.comps'):
            for k,v in comps.items():
                line = re.sub(r"^(%s\s*=\s*).*$" % k, r"\1 %s" % v, line)
            sys.stdout.write(line)

        # rewrite optimization options if desired
        if self.getcfg('rewriteopts'):

            ## replace default -O3 option in configure.wrf with CFLAGS/FFLAGS from environment

            self.log.info("Rewriting optimization options in %s" % cfgfile)

            # set extra flags for Intel compilers
            # see http://software.intel.com/en-us/forums/showthread.php?t=72109&p=1#146748
            if os.getenv('SOFTROOTICC') or os.getenv('SOFTROOTIFORT'):

                # -O3 -heap-arrays is required to resolve compilation error
                for envvar in ['CFLAGS', 'FFLAGS']:
                    val = os.getenv(envvar)
                    if '-O3' in val:
                        os.environ[envvar] = '%s -heap-arrays' % val
                        self.log.info("Updated %s to '%s'" % (envvar, os.getenv(envvar)))

            # replace -O3 with desired optimization options
            for line in fileinput.input(cfgfile, inplace=1, backup='.orig.rewriteopts'):
                line = re.sub(r"^(FCOPTIM.*)(\s-O3)(\s.*)$", r"\1 %s \3" % os.getenv('FFLAGS'), line)
                line = re.sub(r"^(CFLAGS_LOCAL.*)(\s-O3)(\s.*)$", r"\1 %s \3" % os.getenv('CFLAGS'), line)
                sys.stdout.write(line)

    def make(self):
        """Build and install WRF and testcases using provided compile script."""

        # enable parallel build
        p = self.getcfg('parallel')
        self.par = ""
        if p:
            self.par="-j %s"%p

        # build wrf
        cmd = "./compile %s wrf" % self.par
        run_cmd(cmd, log_all=True, simple=True, log_output=True)

    def test(self):
        """Build and run tests included in the WRF distribution."""
        if self.getcfg('runtest'):

            # get list of WRF test cases
            self.testcases = []
            try:
                self.testcases = os.listdir('test')

            except OSError, err:
                self.log.error("Failed to determine list of test cases: %s" % err)

            # exclude 2d testcases in non-parallel WRF builds
            if self.getcfg('buildtype') in ["dmpar","smpar","dm+sm"]:
                self.testcases = [test for test in self.testcases if not "2d_" in test]

            # exclude real testcases
            self.testcases = [test for test in self.testcases if not "_real" in test]

            # reg exp to check for successful test run

            # build an run each test case individually
            for test in self.testcases:

                self.log.debug("Building and running test %s" % test)

                # build
                cmd = "./compile %s %s"%(self.par, test)
                run_cmd(cmd, log_all=True, simple=True)

                # prepare run command

                ## stack limit needs to be set to unlimited for WRF to work well
                cmd = "ulimit -s unlimited && mpirun -n 1 ideal.exe && mpirun -n %s wrf.exe" % self.par

                # run test
                try:
                    os.chdir('run')

                    (out, _) = run_cmd(cmd, log_all=True, simple=False)

                    os.chdir('..')

                except OSError, err:
                    self.log.error("An error occured when running test %s: %s" % (test, err))

    # installing is done in make, so we can run tests
    def make_install(self):
        pass

    def sanitycheck(self):
        """Custom sanity check for WRF."""

        if not self.getcfg('sanityCheckPaths'):

            mainver = self.version().split('.')[0]
            self.wrfsubdir = "WRFV%s"%mainver

            fs = ["libwrflib.a", "wrf.exe", "ideal.exe", "real.exe", "ndown.exe", "nup.exe", "tc.exe"]
            ds = ["main", "run"]

            self.setcfg('sanityCheckPaths',{'files':[os.path.join(self.wrfsubdir,"main",x) for x in fs],
                                            'dirs':[os.path.join(self.wrfsubdir,x) for x in ds]
                                            })

            self.log.info("Customized sanity check paths: %s"%self.getcfg('sanityCheckPaths'))

        Application.sanitycheck(self)

    def make_module_req_guess(self):

        maindir = os.path.join(self.wrfsubdir,"main")

        return {
            'PATH': [maindir],
            'LD_LIBRARY_PATH': [maindir],
            'MANPATH': [],
        }

    def make_module_extra(self):

        txt = Application.make_module_extra(self)

        txt += get_netcdf_module_set_cmds(self.log)

        return txt
