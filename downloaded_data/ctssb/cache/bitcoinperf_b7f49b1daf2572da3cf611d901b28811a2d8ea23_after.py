#!/usr/bin/env python3
"""
Run a series of benchmarks against a particular Bitcoin Core revision.

See bin/run_bench for a sample invocation.

"""

import argparse
import re
import atexit
import os
import subprocess
import tempfile
import json
import datetime
import contextlib
import time
import requests
import logging
import logging.handlers
import shlex
import socket
import sys
import getpass
import multiprocessing
import traceback
from collections import defaultdict
from pathlib import Path

from . import output


# Get physical memory specs
MEM_GIB = (
    os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024. ** 3))

HOSTNAME = socket.gethostname()
BENCH_NAMES = {
    'gitclone', 'build', 'makecheck', 'functionaltests',
    'microbench', 'ibd', 'reindex'}

parser = argparse.ArgumentParser(description=__doc__)


def addarg(name, default, help='', *, type=str):
    envvar_name = name.upper().replace('-', '_')
    default = os.environ.get(envvar_name, default)
    if help and not help.endswith('.'):
        help += '.'
    parser.add_argument(
        '--%s' % name, default=default,
        help='{} Default overriden by {} env var (default: {})'.format(
            help, envvar_name, default), type=type)


def csv_type(s):
    return s.split(',')


def name_to_count_type(s):
    if not s:
        return {}
    out = {}
    for i in s.split(','):
        name, num = i.split(':')
        out[name] = int(num)
    return out


addarg('repo-location', 'https://github.com/bitcoin/bitcoin.git')
addarg('repo-branch', 'master', 'The branch to test')
addarg('workdir', '',
       'Path to where the temporary bitcoin clone will be checked out')
addarg('ibd-peer-address', '',
       'Network address to synced peer to IBD from. If left blank, '
       'IBD will be done from the mainnet P2P network.')
addarg('synced-data-dir', '',
       'When using a local IBD peer, specify a path to a datadir synced to a '
       'chain high enough to do the requested IBD '
       '(see --bitcoind-stopatheight)')
addarg('synced-bitcoin-repo-dir', os.environ['HOME'] + '/bitcoin',
       'Where the bitcoind binary which will serve blocks for IBD lives')
addarg('synced-bitcoind-args', '',
       'Additional arguments to pass to the bitcoind invocation for '
       'the synced IBD peer, e.g. -minimumchainwork')
addarg('codespeed-url', '')
addarg('slack-webhook-url', '')
addarg(
    'run-counts', '',
    help=(
        "Specify the number of times a benchmark should be run, e.g. "
        "'ibd:3,microbench:2'"),
    type=name_to_count_type)
addarg(
    'benches-to-run', default=','.join(BENCH_NAMES),
    help='Only run a subset of benchmarks',
    type=csv_type)

addarg('compilers', 'clang,gcc', type=csv_type)
addarg('make-jobs', '1', type=int)

addarg(
    'commits', '',
    help=("The branches, tags, or commits to test, e.g. 'master,my_change'"),
    type=csv_type)

addarg('bitcoind-dbcache', '2048' if MEM_GIB > 3 else '512')
addarg('bitcoind-stopatheight', '522000')
addarg('bitcoind-assumevalid',
       '000000000000000000176c192f42ad13ab159fdb20198b87e7ba3c001e47b876',
       help=('Should be set to a known block (e.g. the block hash of '
             'BITCOIND_STOPATHEIGHT) to make sure it is not set to a future '
             'block that we are not aware of'))
addarg('bitcoind-port', '9003')
addarg('bitcoind-rpcport', '9004')
addarg('log-level', 'DEBUG')
addarg('nproc', min(4, int(multiprocessing.cpu_count())), type=int)
addarg('no-teardown', False,
       'If true, leave the Bitcoin checkout intact after finishing', type=bool)
addarg('no-caution', False,
       "If true, don't perform a variety of startup checks and cache drops",
       type=bool)
addarg('no-clean', False,
       "If true, do not call `make distclean` before builds. Useful for when "
       "you don't care about build times.", type=bool)
addarg('codespeed-user', '')
addarg('codespeed-password', '')
addarg('codespeed-envname', {
    'bench-odroid-1': 'ccl-bench-odroid-1',
    'bench-raspi-1': 'ccl-bench-raspi-1',
    'bench-hdd-1': 'ccl-bench-hdd-1',
    'bench-ssd-1': 'ccl-bench-ssd-1',
}.get(HOSTNAME))


args = parser.parse_args()
args.benches_to_run = list(filter(None, args.benches_to_run))
args.compilers = list(sorted(args.compilers))


def check_args(args):
    if args.codespeed_url:
        assert(args.codespeed_user)
        assert(args.codespeed_password)
        assert(args.codespeed_envname)

    for name in args.benches_to_run:
        if name not in BENCH_NAMES:
            print("Unrecognized bench name %r" % name)
            sys.exit(1)

    for comp in args.compilers:
        if comp not in {'gcc', 'clang'}:
            print("Unrecognized compiler name %r" % comp)
            sys.exit(1)


if __name__ == '__main__':
    check_args(args)


class SlackLogHandler(logging.Handler):
    def emit(self, record):
        fmtd = self.format(record)

        # If the log is multiple lines, treat the first line as the title and
        # the remainder as text.
        title, *rest = fmtd.split('\n', 1)
        return send_to_slack_attachment(
            title, {}, text=(rest[0] if rest else None), success=False)


def _get_logger():
    logger = logging.getLogger(__name__)
    sh = logging.StreamHandler(sys.stdout)
    log_fmt = '%(asctime)s %(name)s [%(levelname)s] %(message)s'
    sh.setLevel(args.log_level)
    sh.setFormatter(logging.Formatter(log_fmt))

    filehandler = logging.handlers.TimedRotatingFileHandler(
        "bitcoinperf.log", when='D', interval=2)
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(logging.Formatter(log_fmt))

    slack = SlackLogHandler()
    slack.setLevel(logging.WARNING)
    slack.setFormatter(logging.Formatter('%(message)s'))

    logger.addHandler(sh)
    logger.addHandler(filehandler)
    logger.addHandler(slack)
    logger.setLevel(logging.DEBUG)
    return logger


logger = _get_logger()

RUNNING_SYNCED_BITCOIND_LOCALLY = False

# True when running an IBD from random peers on the network, i.e. a "real" IBD.
IBD_FROM_NETWORK = False

if args.ibd_peer_address in ('localhost', '127.0.0.1', '0.0.0.0'):
    RUNNING_SYNCED_BITCOIND_LOCALLY = True
    args.ibd_peer_address = '127.0.0.1'
    logger.info(
        "Running synced chain node on localhost (no remote addr specified)")
elif not args.ibd_peer_address:
    IBD_FROM_NETWORK = True
    logger.info(
        "Running a REAL IBD from the P2P network. "
        "This may result in inconsistent IBD times.")


logger.info("Running with configuration:")
logger.info("")
for name, val in sorted(args.__dict__.items()):
    logger.info("  {0:<26} {1:<40}".format(name, str(val)))
logger.info("")


class RunData:
    """Data set at runtime for global reference."""
    current_commit = None

    # The non-SHA name of the ref being tested.
    current_ref = None

    # The working directory for this benchmark. Contains a `bitcoin/` subdir.
    workdir = None

    # Did we acquire the benchmarking lockfile?
    lockfile_acquired = False

    compiler = None


RUN_DATA = RunData()

# TODO Actually, commit name -> {bench name -> measurement}.
NAME_TO_TIME = defaultdict(lambda: defaultdict(list))


@contextlib.contextmanager
def timer(name: str):
    start = time.time()
    yield
    NAME_TO_TIME[RUN_DATA.current_ref][name].append(time.time() - start)


# Maintain a lockfile that is global across the host to ensure that we're not
# running more than one instance on a given system.
LOCKFILE_PATH = Path("/tmp/bitcoin_bench.lock")


BENCH_SPECIFIC_BITCOIND_ARGS = (
    # To "complete" (i.e. latch false out of) initialblockdownload for
    # stopatheight for a lowish height, we need to set a very large maxtipage.
    '-maxtipage=99999999999999999999 '

    # If we don't set minimumchainwork to 0, low heights may cause the syncing
    # peer to never download blocks and thus hang indefinitely during IBD.
    # See https://github.com/bitcoin/bitcoin/blob/e83d82a85c53196aff5b5ac500f20bb2940663fa/src/net_processing.cpp#L517-L521  # noqa
    '-minimumchainwork=0x00 '

    # Output buffering into memory during ps.communicate() can cause OOM errors
    # on machines with small memory, so only output to debug.log files in disk.
    '-printtoconsole=0 '
)


@contextlib.contextmanager
def run_synced_bitcoind():
    """
    Context manager which spawns (and cleans up) a bitcoind instance that has a
    synced chain high enough to service an IBD up to BITCOIND_STOPATHEIGHT.
    """
    if not RUNNING_SYNCED_BITCOIND_LOCALLY:
        # If we're not running a node locally, don't worry about setup and
        # teardown.
        yield
        return

    bitcoinps = _popen(
        # Relies on bitcoind being precompiled and synced chain data existing
        # in /bitcoin_data; see runner/Dockerfile.
        "%s/src/bitcoind -datadir=%s -noconnect -listen=1 %s %s" % (
            args.synced_bitcoin_repo_dir, args.synced_data_dir,
            BENCH_SPECIFIC_BITCOIND_ARGS, args.synced_bitcoind_args,
            ))

    logger.info(
        "started synced node with '%s' (pid %s)",
        bitcoinps.args, bitcoinps.pid)

    # Wait for bitcoind to come up.
    num_tries = 100
    sleep_time_secs = 2
    bitcoind_up = False

    def stop_synced_bitcoind():
        _run("%s/src/bitcoin-cli -datadir=%s stop" %
             (args.synced_bitcoin_repo_dir, args.synced_data_dir))
        bitcoinps.wait(timeout=120)

    while num_tries > 0 and bitcoinps.returncode is None and not bitcoind_up:
        info = None
        info_call = _run(
            "{}/src/bitcoin-cli -datadir={} getblockchaininfo".format(
                args.synced_bitcoin_repo_dir, args.synced_data_dir),
            check_returncode=False)

        if info_call[2] == 0:
            info = json.loads(info_call[0].decode())
        else:
            logger.debug(
                "non-zero returncode (%s) from synced bitcoind status check",
                info_call[2])

        if info and info["blocks"] < int(args.bitcoind_stopatheight):
            stop_synced_bitcoind()  # Stop process; we're exiting.
            raise RuntimeError(
                "synced bitcoind node doesn't have enough blocks "
                "(%s vs. %s)" %
                (info['blocks'], int(args.bitcoind_stopatheight)))
        elif info:
            bitcoind_up = True
        else:
            num_tries -= 1
            time.sleep(sleep_time_secs)

    if not bitcoind_up:
        raise RuntimeError("Couldn't bring synced node up")

    logger.info("synced node is active (pid %s) %s", bitcoinps.pid, info)

    try:
        yield
    finally:
        logger.info("shutting down synced node (pid %s)", bitcoinps.pid)
        stop_synced_bitcoind()

        if bitcoinps.returncode != 0:
            logger.warning(
                "synced bitcoind returned with nonzero return code "
                "%s" % bitcoinps.returncode)


def _drop_caches():
    # N.B.: the host sudoer file needs to be configured to allow non-superusers
    # to run this command. See: https://unix.stackexchange.com/a/168670
    if not args.no_caution:
        _run("sudo /sbin/sysctl vm.drop_caches=3")


def _startup_assertions():
    """
    Ensure the benchmark environment is suitable in various ways.
    """
    if not args.no_caution:
        if _run("pgrep --list-name bitcoin | grep -v bitcoinperf",
                check_returncode=False)[2] == 0:
            raise RuntimeError(
                "benchmarks shouldn't run concurrently with unrelated bitcoin "
                "processes")

        if _run("$(which time) -f %M sleep 0.01",
                check_returncode=False)[2] != 0:
            raise RuntimeError("the time package is required")

        _run('sudo swapoff -a')

        if _run('cat /proc/swaps | grep -v "^Filename"',
                check_returncode=False)[2] != 1:
            raise RuntimeError("swap must be disabled during benchmarking")

    if not _try_acquire_lockfile():
        raise RuntimeError(
            "Couldn't acquire lockfile %s; exiting", LOCKFILE_PATH)


BENCH_PREFIX = (
    "bench-%s-%s-" %
    (args.repo_branch,
     datetime.datetime.utcnow().strftime('%Y-%m-%d')))


def get_commits():
    args.commits = list(filter(None, args.commits))

    if not args.commits:
        return ['HEAD']
    return args.commits


def get_times_to_run(bench_name):
    return args.run_counts.get(bench_name, 1)


def benchmark(name):
    """A decorator used to declare benchmark steps.

    Handles skipping and count-based execution."""
    def wrapper(func):
        def inner(*args_, **kwargs):
            if name not in args.benches_to_run:
                logger.debug("Skipping benchmark %r", name)
            else:
                count = get_times_to_run(name)
                logger.info("Running benchmark %r %d times", name, count)
                # Drop system caches to ensure fair runs.
                _drop_caches()

                for i in range(count):
                    func(*args_, **kwargs)

        return inner
    return wrapper


@benchmark('gitclone')
def bench_gitclone():
    with timer("gitclone"):
        _run("git clone -b %s %s" % (args.repo_branch, args.repo_location))


@benchmark('build')
def bench_build():
    _run("./contrib/install_db4.sh .")

    my_env = os.environ.copy()
    my_env['BDB_PREFIX'] = "%s/bitcoin/db4" % RUN_DATA.workdir

    _run("./autogen.sh")

    configure_prefix = ''
    if RUN_DATA.compiler == 'clang':
        configure_prefix = 'CC=clang CXX=clang++ '

    # Ensure build is clean.
    makefile_path = RUN_DATA.workdir / 'bitcoin' / 'Makefile'
    if makefile_path.is_file() and not args.no_clean:
        _run('make distclean')

    boostflags = ''
    armlib_path = '/usr/lib/arm-linux-gnueabihf/'

    if Path(armlib_path).is_dir():
        # On some architectures we need to manually specify this,
        # otherwise configuring with clang can fail.
        boostflags = '--with-boost-libdir=%s' % armlib_path

    _run(
        configure_prefix +
        './configure BDB_LIBS="-L${BDB_PREFIX}/lib -ldb_cxx-4.8" '
        'BDB_CFLAGS="-I${BDB_PREFIX}/include" '
        # Ensure ccache is disabled so that subsequent make runs
        # are timed accurately.
        '--disable-ccache ' + boostflags,
        env=my_env)

    _try_execute_and_report(
        'build.make.%s.%s' % (args.make_jobs, RUN_DATA.compiler),
        "make -j %s" % args.make_jobs,
        executable='make')


@benchmark('makecheck')
def bench_makecheck():
    _try_execute_and_report(
        'makecheck.%s.%s' % (RUN_DATA.compiler, args.nproc - 1),
        "make -j %s check" % (args.nproc - 1),
        num_tries=3, executable='make')


@benchmark('functionaltests')
def bench_functests():
    _try_execute_and_report(
        'functionaltests.%s' % RUN_DATA.compiler,
        "./test/functional/test_runner.py --exclude rpc_bind",
        num_tries=3, executable='functional-test-runner')


@benchmark('microbench')
def bench_microbench():
    with timer("microbench.%s" % RUN_DATA.compiler):
        _drop_caches()
        microbench_ps = _popen("./src/bench/bench_bitcoin")
        (microbench_stdout,
         microbench_stderr) = microbench_ps.communicate()

    if microbench_ps.returncode != 0:
        text = "stdout:\n%s\nstderr:\n%s" % (
            microbench_stdout.decode(), microbench_stderr.decode())

        send_to_slack_attachment(
            "Microbench exited with code %s" %
            microbench_ps.returncode, {}, text=text, success=False)

    microbench_lines = [
        # Skip the first line (header)
        i.decode().split(', ')
        for i in microbench_stdout.splitlines()[1:]]

    for line in microbench_lines:
        # Line strucure is
        # "Benchmark, evals, iterations, total, min, max, median"
        assert(len(line) == 7)
        (bench, median, max_, min_) = (
            line[0], float(line[-1]), float(line[-2]), float(line[-3]))
        if not (max_ >= median >= min_):
            logger.warning(
                "%s has weird results: %s, %s, %s" %
                (bench, max_, median, min_))
            assert False
        send_to_codespeed(
            "micro.%s.%s" % (RUN_DATA.compiler, bench),
            median, 'bench-bitcoin', result_max=max_, result_min=min_)


@benchmark('ibd')
def bench_ibd_and_reindex(run_bitcoind_cmd):
    ibd_bench_name = 'ibd.real' if IBD_FROM_NETWORK else 'ibd.local'

    # Ensure empty data before each IBD.
    datadir = RUN_DATA.workdir / 'bitcoin' / 'data'
    _run("rm -rf %s" % datadir, check_returncode=False)
    if not datadir.exists():
        datadir.mkdir()

    with run_synced_bitcoind():
        _try_execute_and_report(
            '%s.%s.dbcache=%s' % (
                ibd_bench_name,
                args.bitcoind_stopatheight, args.bitcoind_dbcache),
            run_bitcoind_cmd,
        )

    if 'reindex' in args.benches_to_run:
        _try_execute_and_report(
            'reindex.%s.dbcache=%s' % (
                args.bitcoind_stopatheight, args.bitcoind_dbcache),
            '%s -reindex' % run_bitcoind_cmd)


def run_benches():
    """
    Create a tmp directory in which we will clone bitcoin, build it, and run
    various benchmarks.
    """
    logger.info(
        "Running benchmarks %s with compilers %s",
        args.benches_to_run, args.compilers)

    _startup_assertions()

    if args.workdir:
        workdir = Path(args.workdir)
    else:
        workdir = Path(tempfile.mkdtemp(prefix=BENCH_PREFIX))
    RUN_DATA.workdir = workdir
    RUN_DATA.current_ref = args.repo_branch

    os.chdir(str(workdir))

    bench_gitclone()

    os.chdir(str(workdir / 'bitcoin'))

    for commit in get_commits():
        if commit != 'HEAD':
            logger.info("Checking out commit %s", commit)
            _run("git checkout %s" % commit)

        RUN_DATA.current_ref = commit
        RUN_DATA.current_commit = subprocess.check_output(
            shlex.split('git rev-parse HEAD')).strip().decode()

        for compiler in args.compilers:
            RUN_DATA.compiler = compiler
            bench_build()
            bench_makecheck()
            bench_functests()
            bench_microbench()

        connect_config = '-listen=0' if IBD_FROM_NETWORK else '-connect=0'
        addnode_config = (
            # If we aren't IBDing from random peers on the network, specify the
            # peer.
            ('-addnode=%s' % args.ibd_peer_address)
            if not IBD_FROM_NETWORK else '')

        run_bitcoind_cmd = (
            './src/bitcoind -datadir={}/bitcoin/data '
            '-dbcache={} -txindex=1 '
            '{} -debug=all -stopatheight={} -assumevalid={} '
            '-port={} -rpcport={} {} {}'.format(
                workdir, args.bitcoind_dbcache, connect_config,
                args.bitcoind_stopatheight, args.bitcoind_assumevalid,
                args.bitcoind_port, args.bitcoind_rpcport,
                addnode_config,
                BENCH_SPECIFIC_BITCOIND_ARGS,
            ))

        bench_ibd_and_reindex(run_bitcoind_cmd)


def _try_acquire_lockfile():
    if LOCKFILE_PATH.exists():
        return False

    with LOCKFILE_PATH.open('w') as f:
        f.write("%s,%s" % (datetime.datetime.utcnow(), getpass.getuser()))
    RUN_DATA.lockfile_acquired = True
    return True


def _clean_shutdown():
    # Release lockfile if we've got it
    if RUN_DATA.lockfile_acquired:
        LOCKFILE_PATH.unlink()
        logger.debug("shutdown: removed lockfile at %s", LOCKFILE_PATH)

    # Clean up to avoid filling disk
    if RUN_DATA.workdir and not args.no_teardown and RUN_DATA.workdir.is_dir():
        os.chdir(str(RUN_DATA.workdir / ".."))
        _stash_debug_file()
        _run("rm -rf %s" % RUN_DATA.workdir)
        logger.debug("shutdown: removed workdir at %s", RUN_DATA.workdir)
    elif args.no_teardown:
        logger.debug("shutdown: leaving workdir at %s", RUN_DATA.workdir)


def _stash_debug_file():
    # Move the debug.log file out into /tmp for diagnostics.
    debug_file = RUN_DATA.workdir / "/bitcoin/data/debug.log"
    if debug_file.is_file():
        # Overwrite the file so as not to fill up disk.
        debug_file.rename(Path("/tmp/bench-debug.log".format(BENCH_PREFIX)))


atexit.register(_clean_shutdown)


def _run(*args, check_returncode=True, **kwargs) -> (bytes, bytes, int):
    p = subprocess.Popen(
        *args, **kwargs,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

    (stdout, stderr) = p.communicate()

    if check_returncode and p.returncode != 0:
        raise RuntimeError(
            "Command '%s' failed with code %s\nstderr:\n%s\nstdout:\n%s" % (
                args[0], p.returncode, stderr, stdout))
    return (stdout, stderr, p.returncode)


def _popen(args, env=None):
    return subprocess.Popen(
        args, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)


def _try_execute_and_report(
        bench_name, cmd, *, report_memory=True, report_time=True, num_tries=1,
        check_returncode=True, executable='bitcoind'):
    """
    Attempt to execute some command a number of times and then report
    its execution memory usage or execution time to codespeed over HTTP.
    """
    for i in range(num_tries):
        start = time.time()
        ps = _popen('$(which time) -f %M ' + cmd)

        logger.info("[%s] command '%s' starting", bench_name, cmd)

        (stdout, stderr) = ps.communicate()
        total_time = time.time() - start
        # Get the last 10,000 characters of output.
        stdout = stdout.decode()[-10000:]
        stderr = stderr.decode()[-10000:]

        if (check_returncode and ps.returncode != 0) \
                or check_for_failure(
                    bench_name, stdout, stderr, total_time_secs=total_time):
            logger.error(
                "[%s] command failed\nstdout:\n%s\nstderr:\n%s",
                bench_name, stdout, stderr)

            if i == (num_tries - 1):
                return False
            continue
        else:
            # Command succeeded
            break

    memusage = int(stderr.strip().split('\n')[-1])

    logger.info(
        "[%s] command finished successfully "
        "with maximum resident set size %.3f MiB",
        bench_name, memusage / 1024)

    mem_name = bench_name + '.mem-usage'
    NAME_TO_TIME[RUN_DATA.current_ref][mem_name].append(memusage)
    if report_memory:
        send_to_codespeed(
            mem_name, memusage, executable, units_title='Size', units='KiB')

    logger.info(
        "[%s] command finished successfully in %.3f seconds (%s)",
        bench_name, total_time, datetime.timedelta(seconds=total_time))

    NAME_TO_TIME[RUN_DATA.current_ref][bench_name].append(total_time)
    if report_time:
        send_to_codespeed(bench_name, total_time, executable)


def check_for_failure(bench_name, stdout, stderr, total_time_secs):
    """
    Sometimes certain benchmarks may fail with zero returncodes and we must
    examine other things to detect the failure.
    """
    if re.match(r'ibd.*|reindex', bench_name):
        disk_warning_ps = subprocess.run(
            "tail -n 10000 %s/bitcoin/data/debug.log | "
            "grep 'Disk space is low!' " % RUN_DATA.workdir, shell=True)

        if disk_warning_ps.returncode == 0:
            logger.warning(
                "Ran out of disk space while running benchmark %s" %
                bench_name)
            return True

    if re.match(r'ibd.*', bench_name):
        one_hour_secs = 60 * 60 * 2

        if total_time_secs < one_hour_secs:
            logger.warning("IBD finished implausibly quickly")
            return True

    return False


def send_to_codespeed(
        bench_name, result, executable,
        lessisbetter=True, units_title='Time', units='seconds', description='',
        result_max=None, result_min=None):
    """
    Send a benchmark result to codespeed over HTTP.
    """
    # Mandatory fields
    data = {
        'commitid': RUN_DATA.current_commit,
        'branch': args.repo_branch,
        'project': 'Bitcoin Core',
        'executable': executable,
        'benchmark': bench_name,
        'environment': args.codespeed_envname,
        'result_value': result,
        # Optional. Default is taken either from VCS integration or from
        # current date
        # 'revision_date': current_date,
        # 'result_date': current_date,  # Optional, default is current date
        # 'std_dev': std_dev,  # Optional. Default is blank
        'max': result_max,  # Optional. Default is blank
        'min': result_min,  # Optional. Default is blank
        # Ignored if bench_name already exists:
        'lessisbetter': lessisbetter,
        'units_title': units_title,
        'units': units,
        'description': description,
    }

    logger.debug(
        "Attempting to send benchmark (%s, %s) to codespeed",
        bench_name, result)

    if not args.codespeed_url:
        return

    resp = requests.post(
        args.codespeed_url + '/result/add/',
        data=data, auth=(args.codespeed_user, args.codespeed_password))

    if resp.status_code != 202:
        raise ValueError(
            'Request to codespeed returned an error %s, the response is:\n%s'
            % (resp.status_code, resp.text)
        )


def send_to_slack_txt(txt):
    _send_to_slack({'text': "[%s] %s" % (HOSTNAME, txt)})


def send_to_slack_attachment(title, fields, text="", success=True):
    fields['Host'] = HOSTNAME
    fields['Commit'] = (RUN_DATA.current_commit or '')[:6]
    fields['Branch'] = args.repo_branch

    data = {
        "attachments": [{
            "title": title,
            "fields": [
                {"title": title, "value": val, "short": True} for (title, val)
                in fields.items()
            ],
            "color": "good" if success else "danger",
        }],
    }

    if text:
        data['attachments'][0]['text'] = text

    _send_to_slack(data)


def _send_to_slack(slack_data):
    if not args.slack_webhook_url:
        return

    response = requests.post(
        args.slack_webhook_url, data=json.dumps(slack_data),
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )


def main():
    try:
        run_benches()

        if len(get_commits()) <= 1:
            timestr = output.get_times_table(
                NAME_TO_TIME[RUN_DATA.current_ref])
            print(timestr)
        else:
            output.print_comparative_times_table(NAME_TO_TIME)
    except Exception:
        send_to_slack_attachment(
            "Error", {}, text=traceback.format_exc(), success=False)
        raise
