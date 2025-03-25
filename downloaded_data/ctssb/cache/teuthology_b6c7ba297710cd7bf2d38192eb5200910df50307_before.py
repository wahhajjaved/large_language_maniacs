import fcntl
import logging
import os
import subprocess
import sys
import tempfile
import time
import yaml

from datetime import datetime

from teuthology import setup_log_file
from . import beanstalk
from . import report
from . import safepath
from .config import config as teuth_config
from .kill import kill_job
from .misc import read_config
from .repo_utils import enforce_repo_state, BranchNotFoundError

log = logging.getLogger(__name__)
start_time = datetime.utcnow()
restart_file_path = '/tmp/teuthology-restart-workers'


def need_restart():
    if not os.path.exists(restart_file_path):
        return False
    file_mtime = datetime.utcfromtimestamp(os.path.getmtime(restart_file_path))
    if file_mtime > start_time:
        return True
    else:
        return False


def restart():
    log.info('Restarting...')
    args = sys.argv[:]
    args.insert(0, sys.executable)
    os.execv(sys.executable, args)


def install_except_hook():
    """
    Install an exception hook that first logs any uncaught exception, then
    raises it.
    """
    def log_exception(exc_type, exc_value, exc_traceback):
        if not issubclass(exc_type, KeyboardInterrupt):
            log.critical("Uncaught exception", exc_info=(exc_type, exc_value,
                                                         exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    sys.excepthook = log_exception


class filelock(object):
    # simple flock class
    def __init__(self, fn):
        self.fn = fn
        self.fd = None

    def acquire(self):
        assert not self.fd
        self.fd = file(self.fn, 'w')
        fcntl.lockf(self.fd, fcntl.LOCK_EX)

    def release(self):
        assert self.fd
        fcntl.lockf(self.fd, fcntl.LOCK_UN)
        self.fd = None


def fetch_teuthology_branch(branch):
    """
    Make sure we have the correct teuthology branch checked out and up-to-date

    :param branch: The branche we want
    :returns:      The destination path
    """
    src_base_path = teuth_config.src_base_path
    dest_path = os.path.join(src_base_path, 'teuthology_' + branch)
    # only let one worker create/update the checkout at a time
    lock = filelock(dest_path.rstrip('/') + '.lock')
    lock.acquire()
    try:
        teuthology_git_upstream = teuth_config.ceph_git_base_url + \
            'teuthology.git'
        enforce_repo_state(teuthology_git_upstream, dest_path, branch)

        log.debug("Bootstrapping %s", dest_path)
        # This magic makes the bootstrap script not attempt to clobber an
        # existing virtualenv. But the branch's bootstrap needs to actually
        # check for the NO_CLOBBER variable.
        env = os.environ.copy()
        env['NO_CLOBBER'] = '1'
        cmd = './bootstrap'
        boot_proc = subprocess.Popen(cmd, shell=True, cwd=dest_path, env=env,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        returncode = boot_proc.wait()
        if returncode != 0:
            for line in boot_proc.stdout.readlines():
                log.warn(line.strip())
        log.info("Bootstrap exited with status %s", returncode)

    finally:
        lock.release()

    return dest_path


def fetch_qa_suite(branch):
    """
    Make sure ceph-qa-suite is checked out.

    :param branch: The branch to fetch
    :returns:      The destination path
    """
    src_base_path = teuth_config.src_base_path
    dest_path = os.path.join(src_base_path, 'ceph-qa-suite_' + branch)
    qa_suite_url = os.path.join(teuth_config.ceph_git_base_url,
                                'ceph-qa-suite')
    # only let one worker create/update the checkout at a time
    lock = filelock(dest_path.rstrip('/') + '.lock')
    lock.acquire()
    try:
        enforce_repo_state(qa_suite_url, dest_path, branch)
    finally:
        lock.release()
    return dest_path


def main(ctx):
    loglevel = logging.INFO
    if ctx.verbose:
        loglevel = logging.DEBUG
    log.setLevel(loglevel)

    log_file_path = os.path.join(ctx.log_dir, 'worker.{tube}.{pid}'.format(
        pid=os.getpid(), tube=ctx.tube,))
    setup_log_file(log, log_file_path)

    install_except_hook()

    if not os.path.isdir(ctx.archive_dir):
        sys.exit("{prog}: archive directory must exist: {path}".format(
            prog=os.path.basename(sys.argv[0]),
            path=ctx.archive_dir,
        ))
    else:
        teuth_config.archive_base = ctx.archive_dir

    read_config(ctx)

    connection = beanstalk.connect()
    beanstalk.watch_tube(connection, ctx.tube)
    result_proc = None

    while True:
        # Check to see if we have a teuthology-results process hanging around
        # and if so, read its return code so that it can exit.
        if result_proc is not None and result_proc.poll() is not None:
            log.debug("teuthology-results exited with code: %s",
                      result_proc.returncode)
            result_proc = None

        if need_restart():
            restart()

        job = connection.reserve(timeout=60)
        if job is None:
            continue

        # bury the job so it won't be re-run if it fails
        job.bury()
        log.info('Reserved job %d', job.jid)
        log.info('Config is: %s', job.body)
        job_config = yaml.safe_load(job.body)

        job_config['job_id'] = str(job.jid)
        safe_archive = safepath.munge(job_config['name'])
        job_config['worker_log'] = log_file_path
        archive_path_full = os.path.join(
            ctx.archive_dir, safe_archive, str(job.jid))
        job_config['archive_path'] = archive_path_full

        # If the teuthology branch was not specified, default to master and
        # store that value.
        teuthology_branch = job_config.get('teuthology_branch', 'master')
        job_config['teuthology_branch'] = teuthology_branch

        try:
            teuth_path = fetch_teuthology_branch(branch=teuthology_branch)
            ceph_branch = job_config['branch']
            suite_branch = job_config.get('suite_branch', ceph_branch)
            suite_path = fetch_qa_suite(suite_branch)
        except BranchNotFoundError:
            log.exception(
                "Branch not found; throwing job away")
            # Optionally, we could mark the job as dead, but we don't have a
            # great way to express why it is dead.
            report.try_delete_jobs(job_config['name'],
                                   job_config['job_id'])
            continue

        teuth_bin_path = os.path.join(teuth_path, 'virtualenv', 'bin')
        if not os.path.isdir(teuth_bin_path):
            raise RuntimeError("teuthology branch %s at %s not bootstrapped!" %
                               (teuthology_branch, teuth_bin_path))

        if job_config.get('last_in_suite'):
            if teuth_config.results_server:
                report.try_delete_jobs(job_config['name'],
                                       job_config['job_id'])
            log.info('Generating results email for %s', job_config['name'])
            args = [
                os.path.join(teuth_bin_path, 'teuthology-results'),
                '--timeout',
                str(job_config.get('results_timeout', 32400)),
                '--email',
                job_config['email'],
                '--archive-dir',
                os.path.join(ctx.archive_dir, safe_archive),
                '--name',
                job_config['name'],
            ]
            # Execute teuthology-results, passing 'preexec_fn=os.setpgrp' to
            # make sure that it will continue to run if this worker process
            # dies (e.g. because of a restart)
            result_proc = subprocess.Popen(args=args, preexec_fn=os.setpgrp)
            log.info("teuthology-results PID: %s", result_proc.pid)
        else:
            log.info('Creating archive dir %s', archive_path_full)
            safepath.makedirs(ctx.archive_dir, safe_archive)
            log.info('Running job %d', job.jid)
            run_job(job_config, teuth_bin_path, suite_path)
        job.delete()


def run_with_watchdog(process, job_config):
    job_start_time = datetime.utcnow()

    # Only push the information that's relevant to the watchdog, to save db
    # load
    job_info = dict(
        name=job_config['name'],
        job_id=job_config['job_id'],
    )

    # Sleep once outside of the loop to avoid double-posting jobs
    time.sleep(teuth_config.watchdog_interval)
    symlink_worker_log(job_config['worker_log'], job_config['archive_path'])
    while process.poll() is None:
        # Kill jobs that have been running longer than the global max
        run_time = datetime.utcnow() - job_start_time
        total_seconds = run_time.days * 60 * 60 * 24 + run_time.seconds
        if total_seconds > teuth_config.max_job_time:
            log.warning("Job ran longer than {max}s. Killing...".format(
                max=teuth_config.max_job_time))
            kill_job(job_info['name'], job_info['job_id'],
                     teuth_config.archive_base)

        report.try_push_job_info(job_info, dict(status='running'))
        time.sleep(teuth_config.watchdog_interval)

    # The job finished. Let's make sure paddles knows.
    branches_sans_reporting = ('argonaut', 'bobtail', 'cuttlefish', 'dumpling')
    if job_config.get('teuthology_branch') in branches_sans_reporting:
        # The job ran with a teuthology branch that may not have the reporting
        # feature. Let's call teuthology-report (which will be from the master
        # branch) to report the job manually.
        cmd = "teuthology-report -v -D -r {run_name} -j {job_id}".format(
            run_name=job_info['name'],
            job_id=job_info['job_id'])
        try:
            log.info("Executing %s" % cmd)
            report_proc = subprocess.Popen(cmd, shell=True,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT)
            while report_proc.poll() is None:
                for line in report_proc.stdout.readlines():
                    log.info(line.strip())
                time.sleep(1)
            log.info("Reported results via the teuthology-report command")
        except Exception:
            log.exception("teuthology-report failed")
    else:
        # Let's make sure that paddles knows the job is finished. We don't know
        # the status, but if it was a pass or fail it will have already been
        # reported to paddles. In that case paddles ignores the 'dead' status.
        # If the job was killed, paddles will use the 'dead' status.
        report.try_push_job_info(job_info, dict(status='dead'))


def run_job(job_config, teuth_bin_path, suite_path):
    arg = [
        os.path.join(teuth_bin_path, 'teuthology'),
    ]
    # The following is for compatibility with older schedulers, from before we
    # started merging the contents of job_config['config'] into job_config
    # itself.
    if 'config' in job_config:
        inner_config = job_config.pop('config')
        if not isinstance(inner_config, dict):
            log.warn("run_job: job_config['config'] isn't a dict, it's a %s",
                     str(type(inner_config)))
        else:
            job_config.update(inner_config)

    if job_config['verbose']:
        arg.append('-v')

    arg.extend([
        '--lock',
        '--block',
        '--owner', job_config['owner'],
        '--archive', job_config['archive_path'],
        '--name', job_config['name'],
    ])
    if job_config['description'] is not None:
        arg.extend(['--description', job_config['description']])
    arg.append('--')

    with tempfile.NamedTemporaryFile(prefix='teuthology-worker.',
                                     suffix='.tmp',) as tmp:
        yaml.safe_dump(data=job_config, stream=tmp)
        tmp.flush()
        arg.append(tmp.name)
        p = subprocess.Popen(args=arg, environ=dict(PYTHONPATH=suite_path))
        log.info("Job archive: %s", job_config['archive_path'])
        log.info("Job PID: %s", str(p.pid))

        if teuth_config.results_server:
            log.info("Running with watchdog")
            try:
                run_with_watchdog(p, job_config)
            except Exception:
                log.exception("run_with_watchdog had an unhandled exception")
                raise
        else:
            log.info("Running without watchdog")
            # This sleep() is to give the child time to start up and create the
            # archive dir.
            time.sleep(5)
            symlink_worker_log(job_config['worker_log'],
                               job_config['archive_path'])
            p.wait()

        if p.returncode != 0:
            log.error('Child exited with code %d', p.returncode)
        else:
            log.info('Success!')


def symlink_worker_log(worker_log_path, archive_dir):
    try:
        log.debug("Worker log: %s", worker_log_path)
        os.symlink(worker_log_path, os.path.join(archive_dir, 'worker.log'))
    except Exception:
        log.exception("Failed to symlink worker log")
