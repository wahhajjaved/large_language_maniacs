#!/usr/bin/env python
"""
update_dreqs_0171.py

Called from a cron job. It submits jobs to LOTUS to fully check all files
in the CERFACS WP5 submissions as many contain HDF errors.
"""
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)
import argparse
import json
import logging.config
import os
import subprocess
import sys

import django
django.setup()
from pdata_app.models import DataSubmission, Settings

__version__ = '0.1.0b1'

DEFAULT_LOG_LEVEL = logging.WARNING
DEFAULT_LOG_FORMAT = '%(levelname)s: %(message)s'

logger = logging.getLogger(__name__)


ADMIN_USER = Settings.get_solo().contact_user_id
PARALLEL_SCRIPT = ('/home/users/jseddon/primavera/LIVE-prima-dm/scripts/'
                   'parallel_primavera')
VALIDATE_SCRIPT = 'validate_data_submission.py'
MAX_VALIDATE_SCRIPTS = 5
NUM_PROCS_USE_LOTUS = 4
JSON_FILE = 'cerfacs-wp5.json'
LOG_DIR = '/home/users/jseddon/lotus/cerfacs-wp5'


def is_max_jobs_reached(job_name, max_num_jobs):
    """
    Check if the maximum number of jobs has been reached.

    :param str job_name: a component of the job name to check
    :param int max_num_jobs: the maximum number of jobs that can run
    :returns: True if `max_num_jobs` with `name` are running
    """
    cmd_out = subprocess.run('bjobs -w', stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=True)

    if cmd_out.returncode:
        logger.error('bjobs returned code {}. Assuming the maximum number of '
                     'jobs has been reached.'.format(cmd_out.returncode))
        return True

    num_jobs = 0
    for line in cmd_out.stdout.decode('utf-8').split('\n'):
        if job_name in line:
            num_jobs += 1

    logger.debug('{} {} jobs running'.format(num_jobs, job_name))

    if num_jobs >= max_num_jobs:
        return True
    else:
        return False


def submit_validation(submission_directory):
    """
    Submit a LOTUS job to run the validation.

    :param str submission_directory: The full path to the directory to
        validate.
    """
    job_name = submission_directory.split('/')[9]
    lotus_options = ('-o {}/{}.o -q par-multi -n {} -R "span[hosts=1]" '
                     '-W 24:00 -R "rusage[mem=65536.0]" -M 65536'.
                     format(LOG_DIR, job_name, NUM_PROCS_USE_LOTUS))

    cmd_cmpts = [
        'bsub',
        lotus_options,
        PARALLEL_SCRIPT,
        VALIDATE_SCRIPT,
        '--log-level',
        'DEBUG',
        '--no-prepare',
        '--processes',
        '{}'.format(NUM_PROCS_USE_LOTUS),
        '--data-limit',
        # 1 terabyte
        '1099511627776',
        submission_directory
    ]

    cmd = ' '.join(cmd_cmpts)

    logger.debug('Command is:\n{}'.format(cmd))

    bsub_out = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, shell=True)

    if bsub_out.returncode:
        logger.error('Non-zero return code {} from:\n{}\n{}'.
                     format(bsub_out.returncode, ' '.join(cmd),
                            bsub_out.stderr.decode('utf-8')))
    else:
        logger.debug('Submission submitted for directory: {}\n{}'.
                     format(submission_directory,
                            bsub_out.stdout.decode('utf-8')))


def parse_args():
    """
    Parse command-line arguments
    """
    parser = argparse.ArgumentParser(description='Automatically perform '
                                                 'PRIMAVERA tape writes.')
    parser.add_argument('-l', '--log-level', help='set logging level to one of '
                                                  'debug, info, warn (the '
                                                  'default), or error')
    parser.add_argument('--version', action='version',
                        version='%(prog)s {}'.format(__version__))
    args = parser.parse_args()

    return args


def main():
    """
    Main entry point
    """
    logger.debug('Starting update_dreqs_0171.py')

    if not os.path.exists(LOG_DIR):
        logger.debug('Making {}'.format(LOG_DIR))
        os.makedirs(LOG_DIR)
    if not os.path.exists(os.path.join(LOG_DIR, JSON_FILE)):
        logger.debug('No JSON file, creating submission names')
        submissions = DataSubmission.objects.filter(
            incoming_directory__startswith='/gws/nopw/j04/primavera4/upload/'
                                           'CNRM-CERFACS/CNRM-CM6-1/incoming/'
                                           'CNRM-CM6-1_primWP5-amv'
        ).order_by('id')

        sub_dicts = [{
            'directory': submiss.incoming_directory,
            'run': False
        } for submiss in submissions]
    else:
        with open(os.path.join(LOG_DIR, JSON_FILE)) as fh:
            sub_dicts = json.load(fh)
        logger.debug('Loaded JSON file')

    for submission in sub_dicts:
        if submission['run']:
            continue
        if is_max_jobs_reached(VALIDATE_SCRIPT, MAX_VALIDATE_SCRIPTS):
            logger.debug('Maximum number of jobs reached.')
            break
        logger.debug('Processing {}'.format(submission['directory']))
        submit_validation(submission['directory'])
        submission['run'] = True

    with open(os.path.join(LOG_DIR, JSON_FILE), 'w') as fh:
        json.dump(sub_dicts, fh, indent=4)


if __name__ == "__main__":
    cmd_args = parse_args()

    # determine the log level
    if cmd_args.log_level:
        try:
            log_level = getattr(logging, cmd_args.log_level.upper())
        except AttributeError:
            logger.setLevel(logging.WARNING)
            logger.error('log-level must be one of: debug, info, warn or error')
            sys.exit(1)
    else:
        log_level = DEFAULT_LOG_LEVEL

    # configure the logger
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': DEFAULT_LOG_FORMAT,
            },
        },
        'handlers': {
            'default': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'standard'
            },
        },
        'loggers': {
            '': {
                'handlers': ['default'],
                'level': log_level,
                'propagate': True
            }
        }
    })

    # run the code
    main()
