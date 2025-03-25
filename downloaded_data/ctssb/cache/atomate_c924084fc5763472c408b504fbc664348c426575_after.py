import shlex
import subprocess
from custodian import Custodian
from custodian.vasp.jobs import VaspJob
from custodian.vasp.handlers import VaspErrorHandler, AliasingErrorHandler, MeshSymmetryErrorHandler, \
    UnconvergedErrorHandler, MaxForceErrorHandler, PotimErrorHandler, FrozenJobErrorHandler, NonConvergingErrorHandler, \
    PositiveEnergyErrorHandler
from custodian.vasp.validators import VasprunXMLValidator
from fireworks import explicit_serialize, FireTaskBase, FWAction
from matmethods.utils.utils import env_chk

__author__ = 'Anubhav Jain <ajain@lbl.gov>'
__credits__ = 'Shyue Ping Ong <ong.sp>'


@explicit_serialize
class RunVaspDirect(FireTaskBase):
    """
    Run VASP directly (no custodian).

    Required params:
        vasp_cmd (str): the name of the full executable for running VASP. Supports env_chk.
    """

    required_params = ["vasp_cmd"]

    def run_task(self, fw_spec):
        vasp_cmd = env_chk(self["vasp_cmd"], fw_spec)

        print("Running VASP using exe: {}".format(vasp_cmd))
        return_code = subprocess.call(vasp_cmd, shell=True)
        print("VASP finished running with returncode: {}".format(return_code))


@explicit_serialize
class RunVaspCustodianFromObjects(FireTaskBase):
    """
    Run VASP using custodian in a generic manner using built-in custodian objects

    Required params:
        jobs: ([Job]) - a list of custodian jobs to run
        handlers: ([ErrorHandler]) - a list of error handlers

    Optional params:
        validators: ([Validator]) - a list of Validators
        custodian_params ({}) - dict of all other custodian parameters
    """

    required_params = ["jobs", "handlers"]
    optional_params = ["validators", "custodian_params"]

    def run_task(self, fw_spec):
        c = Custodian(self["handlers"], self["jobs"], self.get("validators"), **self.get("custodian_params", {}))
        output = c.run()
        return FWAction(stored_data=output)


@explicit_serialize
class RunVaspCustodian(FireTaskBase):
    """
    Run VASP using custodian "on rails", i.e. in a simple way that supports most common options.

    Required params:
        vasp_cmd (str): the name of the full executable for running VASP. Supports env_chk.

    Optional params:
        job_type: (str) - choose from "normal" (default), "double_relaxation_run" (two consecutive jobs), and "full_opt_run"
        handler_lvl: (int) - level of handlers to use,0-4. 0 means no handlers, 2 is the default, 4 is highest level.
        scratch_dir: (str) - if specified, uses this directory as the root scratch dir. Supports env_chk.
        gzip_output: (bool) - gzip output (default=T)
        max_errors: (int) - maximum # of errors to fix before giving up (default=2)
        auto_npar: (bool) - use auto_npar (default=F). Recommended set to T for single-node jobs only. Supports env_chk.
        gamma_vasp_cmd: (str) - cmd for Gamma-optimized VASP compilation. Supports env_chk.

    """

    required_params = ["vasp_cmd"]
    optional_params = ["job_type", "handler_lvl", "scratch_dir", "gzip_output", "max_errors", "auto_npar", "gamma_vasp_cmd"]

    def run_task(self, fw_spec):
        vasp_cmd = env_chk(self["vasp_cmd"], fw_spec)
        if isinstance(vasp_cmd, basestring):
            vasp_cmd = shlex.split(vasp_cmd)

        # initialize variables
        job_type = self.get("job_type", "normal")
        scratch_dir = env_chk(self.get("scratch_dir"), fw_spec)
        gzip_output = self.get("gzip_output", True)
        max_errors = self.get("max_errors", 2)
        auto_npar = self.get("auto_npar", True)
        gamma_vasp_cmd = self.get("gamma_vasp_cmd")

        # construct jobs
        jobs = []
        if job_type == "normal":
            jobs = [VaspJob(vasp_cmd, auto_npar=auto_npar, gamma_vasp_cmd=gamma_vasp_cmd)]
        elif job_type == "double_relaxation_run":
            jobs = VaspJob.double_relaxation_run(vasp_cmd, auto_npar=auto_npar)
        elif job_type == "full_opt_run":
            jobs = VaspJob.full_opt_run(vasp_cmd, auto_npar=auto_npar, max_steps=4)
        else:
            raise ValueError("Unsupported job type: {}".format(job_type))

        # construct handlers
        handlers = []
        handler_lvl = self.get("handler_lvl", 2)
        if handler_lvl > 0:
            handlers.extend([VaspErrorHandler(), MeshSymmetryErrorHandler(), UnconvergedErrorHandler(),
                            NonConvergingErrorHandler(), PotimErrorHandler(), PositiveEnergyErrorHandler()])
        if handler_lvl > 1:
            handlers.append(AliasingErrorHandler())
        if handler_lvl > 2:
            handlers.append(FrozenJobErrorHandler())
        if handler_lvl > 3:
            handlers.append(MaxForceErrorHandler())

        validators = [VasprunXMLValidator()]

        c = Custodian(handlers, jobs, validators=validators, max_errors=max_errors,
                      scratch_dir=scratch_dir, gzipped_output=gzip_output)

        output = c.run()
        return FWAction(stored_data=output)