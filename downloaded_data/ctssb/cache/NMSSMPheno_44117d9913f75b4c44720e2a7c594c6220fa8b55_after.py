#!/usr/bin/env python
"""
Submit lots of Pythia8 jobs to condor. All jobs run using the same input card.

The user should specify the Pythia executable, an input card with physics
processes & other instructions for Pythia8, an output directory on /hdfs,
the number of events to generate per job, and the number of jobs to submit.
There is also the option for a 'dry run' where all the files & directories are
set up, but the job is not submitted.

Note that this submits the jobs not one-by-one but as a DAG, to allow easier
monitoring of job status.
"""


import shutil
from time import strftime
from subprocess import call
import argparse
import sys
import os
import getpass
import logging


logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)


def submit_mc_jobs_htcondor(in_args=sys.argv[1:]):
    """
    Main function. Sets up all the relevant directories, makes condor
    job and DAG files, then submits them if necessary.
    """

    # Handle user options. The user can pass all the same options as they
    # would if running the program locally. However, for certain options,
    # we interecpt the argument(s) and modify if necessary.
    parser = argparse.ArgumentParser(description=__doc__)

    # Options for the job submitter
    parser.add_argument("jobIdRange",
                        help="Specify job ID range to run over. The ID is used"
                        " as the random number generator seed, so manual "
                        "control is needed to avoid making the same files. "
                        "Must be of the form: startID, endID. ",
                        nargs=2, type=int)  # no metavar, bug with positional args
    parser.add_argument("--oDir",
                        help="Directory for output HepMC files. "
                        "If no directory is specified, an automatic one will "
                        "be created at: "
                        "/hdfs/user/<username>/NMSSMPheno/Pythia8/<card>/<date>",
                        default="")
    parser.add_argument("--exe",
                        help="Executable to run.",
                        default="generateMC.exe")
    parser.add_argument("--massRange",
                        help="Specify mass range to run over. "
                        "Must be of the form: startMass, endMass, massStep. "
                        "For each mass point, njobs jobs will be submitted. "
                        "This will superseed any --mass option passed via --args",
                        nargs=3, type=float, metavar=('startMass', 'endMass', 'massStep'))
    # All other program arguments to pass to program directly.
    parser.add_argument("--args",
                        help="All other program arguments. "
                        "You must specify this after all other options",
                        nargs=argparse.REMAINDER)
    # Some generic script options
    parser.add_argument("--dry",
                        help="Dry run, don't submit to queue.",
                        action='store_true')
    parser.add_argument("-v",
                        help="Display debug messages.",
                        action='store_true')
    args = parser.parse_args(args=in_args)

    if args.v:
        log.setLevel(logging.DEBUG)

    log.debug(args)

    # Do some checks
    # -------------------------------------------------------------------------
    if not os.path.isfile(args.exe):
        raise RuntimeError('Executable %s does not exist' % args.exe)

    # Get the input card from user's options & check it exists
    card = get_option_in_args(args.args, "--card")
    if not os.path.isfile(card):
        raise RuntimeError('Input card %s does not exist!' % card)
    args.channel = os.path.splitext(os.path.basename(card))[0]

    # Auto generate output directory if necessary
    # -------------------------------------------------------------------------
    if args.oDir == "":
        args.oDir = generate_dir_soolin(args.channel)

    checkCreateDir(args.oDir, args.v)

    # Setup log directory
    # -------------------------------------------------------------------------
    log_dir = '%s/logs' % generate_subdir(args.channel)
    checkCreateDir(log_dir, args.v)

    # Copy executable to outputdir to sandbox it
    # -------------------------------------------------------------------------
    sandbox_exe = os.path.join(args.oDir, os.path.basename(args.exe))
    shutil.copy2(args.exe, sandbox_exe)

    # Loop over required mass(es), generating DAG files for each
    # -------------------------------------------------------------------------
    if args.massRange:
        masses = frange(args.massRange[0], args.massRange[1], args.massRange[2])
    else:
        masses = [get_option_in_args(args.args, '--mass')]

    for mass in masses:
        # File stem common for all dag and status files
        # -------------------------------------------------------------------------
        mass_str = '%g' % mass if isinstance(mass, float) else str(mass)
        file_stem = '%s/ma%s_%s' % (generate_subdir(args.channel),
                                    mass_str, strftime("%H%M%S"))
        checkCreateDir(os.path.dirname(file_stem), args.v)

        # Make DAG file
        # -------------------------------------------------------------------------
        dag_name = file_stem + '.dag'
        status_name = file_stem + '.status'
        write_dag_file(dag_filename=dag_name, condor_filename='HTCondor/mcJob.condor',
                       status_filename=status_name, exe=sandbox_exe,
                       log_dir=log_dir,
                       mass=mass_str, args=args)

        # Submit it
        # -------------------------------------------------------------------------
        if not args.dry:
            call(['condor_submit_dag', dag_name])
            log.info('Check status with:')
            log.info('DAGstatus.py %s' % status_name)
            print ''
            log.info('Condor log files written to: %s' % log_dir)


def write_dag_file(dag_filename, condor_filename, status_filename, log_dir, exe, mass, args):
    """Write a DAG file for a set of jobs.

    Creates a DAG file, adding extra flags for the worker node script.
    This includes setting the random number generator seed, and copying files
    to & from /hdfs. Also ensures a DAG status file will be written every 30s.

    dag_filename: str
        Name to be used for DAG job file.
    condor_filename: str
        Name of condor job file to be used for each job
    status_filename: str
        Name to be used for DAG status file.
    exe: str
        Location of sandboxed executable to copy accross
    mass: str
        Mass of a1 boson. Used to auto-generate HepMC filename.
    args: argparse.Namespace
        Contains info about output directory, job IDs, number of events per job,
        and args to pass to the executable.
    """
    # get number of events to generate per job
    if '--number' in args.args:
        n_events = get_option_in_args(args.args, "--number")
    elif '-n' in args.args:
        n_events = get_option_in_args(args.args, "-n")
    else:
        log.warning('Number of events per job not specified - assuming 1')
        n_events = 1

    # set mass in args passed to program
    set_option_in_args(args.args, '--mass', str(mass))

    log.debug(args.args)

    log.info("DAG file: %s" % dag_filename)
    with open(dag_filename, 'w') as dag_file:
        dag_file.write('# DAG for channel %s\n' % args.channel)
        dag_file.write('# Outputting to %s\n' % args.oDir)
        for job_ind in xrange(args.jobIdRange[0], args.jobIdRange[1] + 1):
            job_name = '%d_%s' % (job_ind, args.channel)
            dag_file.write('JOB %s %s\n' % (job_name, condor_filename))

            remote_exe = 'mc.exe'
            # args to pass to the script on the worker node
            job_opts = ['--copyToLocal', os.path.abspath('input_cards'), 'input_cards',
                        '--copyToLocal', exe, remote_exe,
                        '--exe', remote_exe]

            exe_args = args.args[:]
            # Add in RNG seed based on job index
            exe_args.extend(['--seed', str(job_ind)])

            # Sort out output files. Ensure that they have the seed appended to
            # filename, and that they will be copied to hdfs afterwards.

            for fmt in ['hepmc', 'root', 'lhe']:
                # special warning for hepmc files
                flag = '--%s' % fmt
                if fmt == "hepmc" and '--hepmc' not in exe_args:
                    log.warning("You didn't specify --hepmc in your list of --args. "
                                "No HepMC file will be produced.")
                if flag not in exe_args:
                    continue
                else:
                    # Auto generate output filename if necessary
                    # Little bit hacky, as we have to manually sync with PythiaProgramOpts.h
                    if not get_option_in_args(args.args, flag):
                        out_name = "%s_ma1_%s_n%s.%s" % (args.channel, mass, n_events, fmt)
                        set_option_in_args(exe_args, flag, out_name)

                    # Use the filename itself, ignore any directories from user.
                    out_name = os.path.basename(get_option_in_args(exe_args, flag))

                    # Add in seed/job ID to filename. Note that generateMC.cc adds the
                    # seed to the auto-generated filename, so we only need to modify it
                    # if the user has specified the name
                    out_name = "%s_seed%d.%s" % (os.path.splitext(out_name)[0], job_ind, fmt)
                    set_option_in_args(exe_args, flag, out_name)

                    # make sure we transfer hepmc to hdfs after generating
                    job_opts.extend(['--copyFromLocal', out_name, args.oDir])

            job_opts.append('--args')
            job_opts.extend(exe_args)
            log_name = os.path.splitext(os.path.basename(dag_filename))[0]
            dag_file.write('VARS %s opts="%s" logdir="%s" logfile="%s"\n' % (job_name,
                                                                             ' '.join(job_opts),
                                                                             log_dir,
                                                                             log_name))
        dag_file.write('NODE_STATUS_FILE %s 30\n' % status_filename)


def checkCreateDir(directory, info=False):
    """Check to see if directory exists, if not make it.

    Can optionally display message to user.
    """
    if not os.path.isdir(directory):
        if os.path.isfile(directory):
            raise RuntimeError("Cannot create directory %s, already "
                               "exists as a file object" % directory)
        os.makedirs(directory)
        if info:
            print "Making dir %s" % directory


def generate_subdir(channel):
    """Generate a subdirectory name using channel and date.
    Can be used for output and log files, so consistent between both.

    >>> generate_subdir('ggh_4tau')
    ggh_4tau/05_Oct_15
    """
    return os.path.join(channel, strftime("%d_%b_%y"))


def generate_dir_soolin(channel):
    """Generate a directory name on Iridis using userId, channel, and date.

    >>> generate_dir_iridis('ggh_4tau')
    /hdfs/user/<username>/NMSSMPheno/Pythia8/ggh_4tau/<date>
    """
    uid = getpass.getuser()
    return "/hdfs/user/%s/NMSSMPheno/Pythia8/%s" % (uid, generate_subdir(channel))


def get_option_in_args(args, flag):
    """Return value that accompanied flag in list of args.

    Will return None if there is no accompanying value, and will raise a
    KeyError if the flag does not appear in the list.

    >>> args = ['--foo', 'bar', '--man']
    >>> get_option_in_args(args, "--foo")
    bar
    >>> get_option_in_args(args, "--man")
    None
    >>> get_option_in_args(args, "--fish")
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "submit_mc_jobs_htcondor.py", line 272, in get_option_in_args
        raise KeyError('%s not in args' % flag)
    KeyError: '--fish not in args'
    """
    # maybe a dict would be better for this and set_option_in_args()?
    if flag not in args:
        raise KeyError('%s not in args' % flag)
    if flag == args[-1]:
        return None
    val = args[args.index(flag) + 1]
    if val.startswith('-'):
        return None
    return val


def set_option_in_args(args, flag, value):
    """Set value for flag in list of args.

    If no value already exists, it will insert the value after the flag.
    If the flag does not appear in args, a KeyError will be raised.

    >>> args = ['--foo', 'bar', '--man', '--pasta']
    >>> set_option_in_args(args, '--foo', 'ball')
    >>> args
    ['--foo', 'ball', '--man', '--pasta']
    >>> set_option_in_args(args, '--man', 'trap')
    >>> args
    ['--foo', 'ball', '--man', 'trap', --pasta']
    >>> set_option_in_args(args, '--pasta', 'bake')
    >>> args
    ['--foo', 'ball', '--man', 'trap', --pasta', 'bake']

    """
    # first check if a value already exists.
    if get_option_in_args(args, flag):
        args[args.index(flag) + 1] = value
    else:
        if flag == args[-1]:
            # if the flag is the last entry in args
            args.append(value)
        elif args[args.index(flag) + 1].startswith('-'):
            # if the next entry is a flag, we need to insert our value
            args.insert(args.index(flag) + 1, value)


def frange(start, stop, step=1.0):
    """Generate an iterator to loop over a range of floats."""
    i = start
    while i <= stop:
        yield i
        i += step


if __name__ == "__main__":
    submit_mc_jobs_htcondor()
