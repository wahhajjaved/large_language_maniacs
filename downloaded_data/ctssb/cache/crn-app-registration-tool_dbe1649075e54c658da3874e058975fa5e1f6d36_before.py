#!/usr/bin/env python
# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
The Agave wrapper in python
"""
from os import path as op, getenv
from glob import glob
from random import shuffle
from argparse import ArgumentParser, RawTextHelpFormatter
from textwrap import dedent
import logging
from yaml import load as loadyml
from cappat import __version__, AGAVE_JOB_OUTPUT


wlogger = logging.getLogger('wrapper')


def get_subject_list(bids_dir, participant_label=None, randomize=True):
    """
    Returns a the list of subjects to be processed

    """
    # Build settings dict
    bids_dir = op.abspath(bids_dir)
    all_subjects = sorted([op.basename(subj)[4:] for subj in glob(op.join(bids_dir, 'sub-*'))])

    if participant_label is None:
        participant_label = []

    if isinstance(participant_label, (str, basestring)):
        participant_label = [s for s in participant_label.strip().split(' ') if s]

    if not participant_label:
        subject_list = all_subjects
    else:
        # remove sub- prefix, get unique
        subject_list = [subj[4:] if subj.startswith('sub-') else subj
                        for subj in participant_label]
        subject_list = sorted(list(set(subject_list)))

        if list(set(subject_list) - set(all_subjects)):
            non_exist = list(set(subject_list) - set(all_subjects))
            raise RuntimeError('Participant label(s) not found in the '
                               'BIDS root directory: {}'.format(' '.join(non_exist)))

    if randomize:
        shuffle(subject_list)

    wlogger.info('Subject list: %s', ' '.join(subject_list))
    return subject_list


def get_task_list(bids_dir, app_name, subject_list, group_size=1,
                  workdir=False, args=None):
    """
    Generate a list of tasks for launcher or slurm
    """
    groups = [sorted(subject_list[i:i+group_size])
              for i in range(0, len(subject_list), group_size)]

    task_list = []
    for i, part_group in enumerate(groups):
        task_str = '{0} {1} {2} participant --participant_label {3}'.format(
            app_name, bids_dir, AGAVE_JOB_OUTPUT, ' '.join(part_group))
        if workdir:
            task_str += ' -w work/sjob-{:04d}'.format(i)
        if args:
            task_str += ' ' + args
        task_list.append(task_str)

    wlogger.info('Task list: \n\t%s', '\n\t'.join(task_list))
    return task_list


def run_wrapper(opts):
    """
    A python wrapper to BIDS-Apps for Agave
    """
    from cappat.manager.base import TaskManager
    from cappat.utils import check_folder

    # Read settings from yml
    with open(opts.settings) as sfh:
        settings = loadyml(sfh)

    app_settings = settings['app']
    levels = app_settings.get('level_plan', ['participant'])

    if not app_settings['bids_dir'].strip():
        raise RuntimeError('Missing BIDS directory')

    if not op.isdir(app_settings['bids_dir']):
        wlogger.critical('BIDS folder path (%s) does not exist',
                         app_settings['bids_dir'])
        raise RuntimeError
    # Ensure folders exist
    check_folder(op.abspath(app_settings['output_dir']))
    log_dir = check_folder(op.abspath(app_settings['log_dir']))
    logging.basicConfig(
        filename=op.join(log_dir, 'logfile.txt'),
        level=getattr(logging, app_settings.get('log_level', 'INFO')))

    # Generate subjects list
    subject_list = get_subject_list(
        app_settings['bids_dir'],
        app_settings.get('participant_label', None),
        randomize=app_settings.get('randomize_part_level', True))

    # Ensure modules is a list of modules
    if app_settings.get('modules'):
        if not isinstance(app_settings['modules'], list):
            app_settings['modules'] = [app_settings['modules']]

    # Generate tasks & submit
    task_list = get_task_list(
        app_settings['bids_dir'], app_settings['executable'], subject_list,
        group_size=app_settings.get('parallel_npart', 1),
        args=app_settings.get('participant_args'))

    app_settings['ncpus'] = getenv('CRNENV_SYSTEM_NCPUS', 16)
    # TaskManager factory will return the appropriate submission object
    stm = TaskManager.build(task_list, settings=app_settings)
    # Participant level mapping
    stm.map_participant()
    # Participant level polling
    stm.wait_participant()

    # Group level reduce
    if 'group' in levels:
        try:
            stm.run_grouplevel()
        except Exception:
            wlogger.error('Error in execution of grouplevel command')
            raise

    # Clean up

def parser():
    argparser = ArgumentParser(formatter_class=RawTextHelpFormatter, description=dedent('''\
        cappwrapp: The CRN's APP WRAPPer tool
        -------------------------------------

    '''))

    argparser.add_argument('-v', '--version', action='version',
                        version='BIDS-Apps wrapper v{}'.format(__version__))
    argparser.add_argument('settings', action='store', help='settings file')
    return argparser

def main():
    """Entry point"""
    args = parser().parse_args()
    run_wrapper(args)

if __name__ == '__main__':
    main()
