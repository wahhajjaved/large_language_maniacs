"""
Experimentation script for Score Predictors

Options
=======

-i <INPUT>, --in <INPUT>
    specify training file name
-t <TEST>, --test <TEST>
    specify test file name
-o <OUTPUT>, --out <OUTPUT>
    specify output file name
-m <METHOD>, --method <METHOD>
    specify algorithm: default=pmf

    * pmf : probabilistic matrix factorization
    * plsam : pLSA (multinomial / use expectation in prediction)
    * plsamm : pLSA (multinomial / use mode in prediction)

-v <VALIDATION>, --validation <VALIDATION>
    validation scheme: default=holdout

    * holdout : tested on the specified hold-out data
    * cv : cross validation

-f <FOLD>, --fold <FOLD>
    the number of folds in cross validation, default=5
-n, --no-timestamp or --timestamp
    specify whether .event files has 'timestamp' information,
    default=timestamp
-d <DOMAIN>, --domain <DOMAIN>
    The domain of scores specified by three floats: min, max, increment
    default=auto
-C <C>, --lambda <C>
    regularization parameter, default=0.01.
-k <K>, --dim <K>
    the number of latent factors, default=1.
--alpha <ALPHA>
    smoothing parameter of multinomial pLSA
--tol <TOL>
    optimization parameter. the size of norm of gradient. default=1e-05.
--maxiter <MAXITER>
    maximum number of iterations is maxiter times the number of parameters.
    default=200
-q, --quiet
    set logging level to ERROR, no messages unless errors
--rseed <RSEED>
    random number seed. if None, use /dev/urandom (default None)
-h, --help
    show this help message and exit
--version
    show program's version number and exit
"""

from __future__ import (
    print_function,
    division,
    absolute_import)
from six.moves import xrange

# =============================================================================
# Imports
# =============================================================================

import sys
import argparse
import datetime
import json
import logging
import os
import platform
import subprocess

import numpy as np
import scipy as sp
import sklearn
from sklearn.model_selection import LeaveOneGroupOut

from kamrecsys.data import EventWithScoreData
from kamrecsys.model_selection import interlace_group

# =============================================================================
# Module metadata variables
# =============================================================================

__author__ = "Toshihiro Kamishima ( http://www.kamishima.net/ )"
__date__ = "2014/07/06"
__version__ = "3.1.0"
__copyright__ = "Copyright (c) 2014 Toshihiro Kamishima all rights reserved."
__license__ = "MIT License: http://www.opensource.org/licenses/mit-license.php"

# =============================================================================
# Public symbols
# =============================================================================

__all__ = ['do_task']

# =============================================================================
# Constants
# =============================================================================

# =============================================================================
# Module variables
# =============================================================================

# =============================================================================
# Functions
# =============================================================================


def load_data(fp, ts):
    """
    load event with scores data

    Parameters
    ----------
    fp : string
        input file pointer
    ts : bool
        has timestamp field

    Returns
    -------
    x : array
        structured array containing event and related information
    """

    # have timestamp?
    if ts:
        dt = np.dtype([
            ('event', int, 2),
            ('score', float),
            ('event_feature', np.dtype([('timestamp', int)]))
        ])
    else:
        dt = np.dtype([
            ('event', int, 2),
            ('score', float)
        ])

    # load training data
    x = np.genfromtxt(fname=fp, delimiter='\t', dtype=dt)

    # close file
    if fp is not sys.stdin:
        fp.close()

    return x


def training(info, ev, tsc, event_feature=None, fold=0):
    """
    training model

    Parameters
    ----------
    info : dict
        Information about the target task
    ev : array, size=(n_events, 2), dtype=int
        array of events in external ids
    tsc : array, size=(n_events,), dtype=float
        true scores
    event_feature : optional, structured array
        structured array of event features
    fold : int, default=0
        fold No.

    Returns
    -------
    rec : EventScorePredictor
        trained recommender
    """

    # start new fold
    n_folds = info['test']['n_folds']
    logger.info("training fold = " + str(fold + 1) + " / " + str(n_folds))

    # generate event data
    data = EventWithScoreData(n_otypes=2, n_stypes=1)
    score_domain = info['data']['score_domain']
    if np.all(np.array(score_domain) == 0):
        score_domain = [
            np.min(tsc), np.max(tsc), np.min(np.diff(np.unique(tsc)))]
        info['data']['score_domain'] = score_domain
        logger.info("score domain is changed to " + str(score_domain))
    data.set_events(
        ev, tsc, score_domain=score_domain, event_feature=event_feature)

    # set starting time
    start_time = datetime.datetime.now()
    start_utime = os.times()[0]
    if 'start_time' not in info['training']:
        info['training']['start_time'] = [0] * n_folds
    info['training']['start_time'][fold] = start_time.isoformat()
    logger.info("training_start_time = " + start_time.isoformat())

    # create and learning model
    rec = info['assets']['recommender'](**info['model']['options'])
    rec.fit(data)

    # set end and elapsed time
    end_time = datetime.datetime.now()
    end_utime = os.times()[0]
    elapsed_time = end_time - start_time
    elapsed_utime = end_utime - start_utime
    if 'end_time' not in info['training']:
        info['training']['end_time'] = [0] * n_folds
    info['training']['end_time'][fold] = end_time.isoformat()
    logger.info("training_end_time = " + end_time.isoformat())

    if 'elapsed_time' not in info['training']:
        info['training']['elapsed_time'] = elapsed_time
    else:
        info['training']['elapsed_time'] += elapsed_time
    logger.info("training_elapsed_time = " +
                str(info['training']['elapsed_time']))
    if 'elapsed_utime' not in info['training']:
        info['training']['elapsed_utime'] = elapsed_utime
    else:
        info['training']['elapsed_utime'] += elapsed_utime
    logger.info("training_elapsed_utime = " +
                str(info['training']['elapsed_utime']))

    # preserve optimizer's outputs
    if 'results' not in info['training']:
        info['training']['results'] = [{}] * n_folds
    info['training']['results'][fold] = rec.fit_results_

    return rec


def testing(rec, info, ev, fold=0):
    """
    test and output results

    Parameters
    ----------
    rec : EventScorePredictor
        trained recommender
    info : dict
        Information about the target task
    ev : array, size=(n_events, 2), dtype=int
        array of events in external ids
    fold : int, default=0
        fold No.
    
    Returns
    -------
    esc : array, shape=(n_events,), dtype=float
        estimated scores
    """

    # start new fold
    n_folds = info['test']['n_folds']
    logger.info("test fold = " + str(fold + 1) + " / " + str(n_folds))

    # set starting time
    start_time = datetime.datetime.now()
    start_utime = os.times()[0]
    if 'start_time' not in info['test']:
        info['test']['start_time'] = [0] * n_folds
    info['test']['start_time'][fold] = start_time.isoformat()
    logger.info("test_start_time = " + start_time.isoformat())

    # prediction
    esc = rec.predict(ev)

    # set end and elapsed time
    end_time = datetime.datetime.now()
    end_utime = os.times()[0]
    elapsed_time = end_time - start_time
    elapsed_utime = end_utime - start_utime

    if 'end_time' not in info['test']:
        info['test']['end_time'] = [0] * n_folds
    info['test']['end_time'][fold] = start_time.isoformat()
    logger.info("test_end_time = " + end_time.isoformat())
    if 'elapsed_time' not in info['test']:
        info['test']['elapsed_time'] = elapsed_time
    else:
        info['test']['elapsed_time'] += elapsed_time
    logger.info("test_elapsed_time = " + str(info['test']['elapsed_time']))
    if 'elapsed_utime' not in info['test']:
        info['test']['elapsed_utime'] = elapsed_utime
    else:
        info['test']['elapsed_utime'] += elapsed_utime
    logger.info("test_elapsed_utime = " + str(info['test']['elapsed_utime']))

    # preserve predictor's outputs
    if 'results' not in info['test']:
        info['test']['results'] = [{}] * n_folds
    info['test']['results'][fold] = {'n_events': ev.shape[0]}

    return esc


def holdout_test(info):
    """
    tested on specified hold-out test data

    Parameters
    ----------
    info : dict
        Information about the target task
    """

    # prepare training data
    train_x = load_data(
        info['assets']['infile'],
        info['data']['has_timestamp'])
    info['training']['file'] = str(info['assets']['infile'])
    info['training']['version'] = get_version_info()
    info['training']['system'] = get_system_info()
    info['training']['random_seed'] = info['model']['options']['random_state']

    # prepare test data
    if info['assets']['testfile'] is None:
        raise IOError('hold-out test data is required')
    test_x = load_data(
        info['assets']['testfile'],
        info['data']['has_timestamp'])
    info['test']['file'] = str(info['assets']['testfile'])
    info['test']['version'] = get_version_info()
    info['test']['system'] = get_system_info()
    info['test']['random_seed'] = info['model']['options']['random_state']
    if info['data']['has_timestamp']:
        ef = train_x['event_feature']
    else:
        ef = None

    # training
    rec = training(info, train_x['event'], train_x['score'], event_feature=ef)
    info['training']['elapsed_time'] = str(info['training']['elapsed_time'])
    info['training']['elapsed_utime'] = str(info['training']['elapsed_utime'])

    # test
    esc = testing(rec, info, test_x['event'])
    info['test']['elapsed_time'] = str(info['training']['elapsed_time'])
    info['test']['elapsed_utime'] = str(info['training']['elapsed_utime'])

    # set predicted result
    info['prediction'] = {
        'event': test_x['event'].tolist(),
        'true': test_x['score'].tolist(),
        'predicted': esc.tolist()}
    if info['data']['has_timestamp']:
        info['prediction']['event_feature'] = (
            {'timestamp': test_x['event_feature']['timestamp'].tolist()})


def cv_test(info):
    """
    tested on specified hold-out test data

    Parameters
    ----------
    info : dict
        Information about the target task
    """

    # prepare training data
    x = load_data(
        info['assets']['infile'],
        info['data']['has_timestamp'])
    info['training']['file'] = str(info['assets']['infile'])
    info['training']['version'] = get_version_info()
    info['training']['system'] = get_system_info()
    info['training']['random_seed'] = info['model']['options']['random_state']
    info['test']['file'] = str(info['assets']['infile'])
    info['test']['version'] = get_version_info()
    info['test']['system'] = get_system_info()
    info['test']['random_seed'] = info['model']['options']['random_state']
    n_events = x.shape[0]
    ev = x['event']
    tsc = x['score']

    fold = 0
    esc = np.empty(n_events, dtype=float)
    cv = LeaveOneGroupOut()
    for train_i, test_i in cv.split(
            ev, groups=interlace_group(n_events, info['test']['n_folds'])):

        # training
        if info['data']['has_timestamp']:
            rec = training(
                info, ev[train_i], tsc[train_i], fold=fold,
                event_feature=x['event_feature'][train_i])
        else:
            rec = training(
                info, ev[train_i], tsc[train_i], fold=fold)

        # test
        esc[test_i] = testing(rec, info, ev[test_i], fold=fold)

        fold += 1

    info['training']['elapsed_time'] = str(info['training']['elapsed_time'])
    info['training']['elapsed_utime'] = str(info['training']['elapsed_utime'])
    info['test']['elapsed_time'] = str(info['training']['elapsed_time'])
    info['test']['elapsed_utime'] = str(info['training']['elapsed_utime'])

    # set predicted result
    info['prediction'] = {
        'event': ev.tolist(), 'true': tsc.tolist(), 'predicted': esc.tolist()}
    if info['data']['has_timestamp']:
        info['prediction']['event_feature'] = {
            'timestamp': x['event_feature']['timestamp'].tolist()}


def get_system_info():
    """
    Get System hardware information

    Returns
    -------
    sys_info : dict
        Information about an operating system and a hardware.
    """
    # import subprocess
    # import platform

    # information collected by a platform package
    sys_info = {
        'system': platform.system(),
        'node': platform.node(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor()}

    # obtain hardware information
    with open('/dev/null', 'w') as DEVNULL:
        if platform.system() == 'Darwin':
            process_pipe = subprocess.Popen(
                ['/usr/sbin/system_profiler',
                 '-detailLevel', 'mini', 'SPHardwareDataType'],
                stdout=subprocess.PIPE, stderr=DEVNULL)
            hard_info, _ = process_pipe.communicate()
            hard_info = hard_info.decode('utf-8').split('\n')[4:-2]
            hard_info = [i.lstrip(' ') for i in hard_info]
        elif platform.system() == 'FreeBSD':
            process_pipe = subprocess.Popen(
                ['/sbin/sysctl', 'hw'],
                stdout=subprocess.PIPE, stderr=DEVNULL)
            hard_info, _ = process_pipe.communicate()
            hard_info = hard_info.decode('utf-8').split('\n')
        elif platform.system() == 'Linux':
            process_pipe = subprocess.Popen(
                ['/bin/cat', '/proc/cpuinfo'],
                stdout=subprocess.PIPE, stderr=DEVNULL)
            hard_info, _ = process_pipe.communicate()
            hard_info = hard_info.decode('utf-8').split('\n')
        else:
            hard_info = []
    sys_info['hardware'] = hard_info

    return sys_info


def get_version_info():
    """
    Get version numbers of a Python interpreter and packages.  
    
    Returns
    -------
    version_info : dict
        Version numbers of a Python interpreter and packages. 
    """
    # import platform
    # import numpy as np
    # import scipy as sp
    # import sklearn

    version_info = {
        'python_compiler': platform.python_compiler(),
        'python_implementation': platform.python_implementation(),
        'python': platform.python_version(),
        'numpy': np.__version__,
        'scipy': sp.__version__,
        'sklearn': sklearn.__version__}

    return version_info


def do_task(info):
    """
    Main task

    Parameters
    ----------
    info : dict
        Information about the target task
    """

    # suppress warnings in numerical computation
    np.seterr(all='ignore')

    # update information dictionary
    info['script']['name'] = os.path.basename(sys.argv[0])
    info['script']['version'] = __version__
    info['model']['type'] = 'event_score_predictor'
    info['model']['module'] = info['assets']['recommender'].__module__

    # select validation scheme
    if info['test']['scheme'] == 'holdout':
        info['test']['n_folds'] = 1
        logger.info("the nos of folds is set to 1")
        holdout_test(info)
    elif info['test']['scheme'] == 'cv':
        cv_test(info)
    else:
        raise TypeError("Invalid validation scheme: {0:s}".format(opt.method))

    # output information
    outfile = info['assets']['outfile']
    info['prediction']['file'] = str(outfile)
    del info['assets']
    outfile.write(json.dumps(info))
    if outfile is not sys.stdout:
        outfile.close()

# =============================================================================
# Classes
# =============================================================================

# =============================================================================
# Main routine
# =============================================================================


def command_line_parser():
    """
    Parsing Command-Line Options
    
    Returns
    -------
    opt : argparse.Namespace
        Parsed command-line arguments
    """
    # import argparse
    # import sys

    # command-line option parsing
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)

    # common options
    ap.add_argument('--version', action='version',
                    version='%(prog)s ' + __version__)

    apg = ap.add_mutually_exclusive_group()
    apg.set_defaults(verbose=True)
    apg.add_argument('--verbose', action='store_true')
    apg.add_argument('-q', '--quiet', action='store_false', dest='verbose')

    ap.add_argument("--rseed", type=int, default=None)

    # basic file i/o
    ap.add_argument('-i', '--in', dest='infile', default=None,
                    type=argparse.FileType('rb'))
    ap.add_argument('infilep', nargs='?', metavar='INFILE', default=sys.stdin,
                    type=argparse.FileType('rb'))
    ap.add_argument('-o', '--out', dest='outfile', default=None,
                    type=argparse.FileType('w'))
    ap.add_argument('outfilep', nargs='?', metavar='OUTFILE',
                    default=sys.stdout, type=argparse.FileType('w'))
    ap.add_argument('-t', '--test', dest='testfile', default=None,
                    type=argparse.FileType('rb'))

    # script specific options
    ap.add_argument('-m', '--method', type=str, default='pmf',
                    choices=['pmf', 'plsam', 'plsamm'])
    ap.add_argument('-v', '--validation', type=str, default='holdout',
                    choices=['holdout', 'cv'])
    ap.add_argument('-f', '--fold', type=int, default=5)

    ap.add_argument('-d', '--domain', nargs=3, default=[0, 0, 0], type=float)
    apg = ap.add_mutually_exclusive_group()
    apg.set_defaults(timestamp=True)
    apg.add_argument('-n', '--no-timestamp',
                     dest='timestamp', action='store_false')
    apg.add_argument('--timestamp',
                     dest='timestamp', action='store_true')

    ap.add_argument('-C', '--lambda', dest='C', type=float, default=0.01)
    ap.add_argument('-k', '--dim', dest='k', type=int, default=1)
    ap.add_argument('--alpha', dest='alpha', type=float, default=1.0)
    ap.add_argument('--tol', type=float, default=1e-05)
    ap.add_argument('--maxiter', type=int, default=200)

    # parsing
    opt = ap.parse_args()

    # post-processing for command-line options
    # basic file i/o
    if opt.infile is None:
        opt.infile = opt.infilep
    del vars(opt)['infilep']
    if opt.outfile is None:
        opt.outfile = opt.outfilep
    del vars(opt)['outfilep']

    # disable logging messages by changing logging level
    if opt.verbose:
        logger.setLevel(logging.INFO)
        logging.getLogger('kamrecsys').setLevel(logging.INFO)

    # output option information
    logger.info("list of options:")
    for key_name, key_value in vars(opt).items():
        logger.info("{0}={1}".format(key_name, str(key_value)))

    return opt


def init_info(opt):
    """
    Initialize information dictionary

    Parameters
    ----------
    opt : argparse.Namespace
        Parsed command-line options

    Returns
    -------
    info : dict
        Information about the target task
    """

    info = {'script': {}, 'data': {}, 'training': {}, 'test': {},
            'model': {'options': {}}, 'assets': {}}

    # files
    info['assets']['infile'] = opt.infile
    info['assets']['outfile'] = opt.outfile
    info['assets']['testfile'] = opt.testfile

    # model

    # model
    info['model']['options']['random_state'] = opt.rseed
    if opt.method == 'pmf':
        from kamrecsys.score_predictor.matrix_factorization import PMF
        info['model']['method'] = 'PMF'
        info['model']['options']['C'] = opt.C
        info['model']['options']['k'] = opt.k
        info['model']['options']['tol'] = opt.tol
        info['model']['options']['maxiter'] = opt.maxiter
        info['assets']['recommender'] = PMF
    elif opt.method == 'plsam':
        from kamrecsys.score_predictor.topic_model import MultinomialPLSA
        info['model']['method'] = 'MultinomialPLSA_ExpectationPredictor'
        info['model']['options']['alpha'] = opt.alpha
        info['model']['options']['k'] = opt.k
        info['model']['options']['tol'] = opt.tol
        info['model']['options']['use_expectation'] = True
        info['model']['options']['maxiter'] = opt.maxiter
        info['assets']['recommender'] = MultinomialPLSA
    elif opt.method == 'plsamm':
        from kamrecsys.score_predictor.topic_model import MultinomialPLSA
        info['model']['method'] = 'MultinomialPLSA_ModePredictor'
        info['model']['options']['alpha'] = opt.alpha
        info['model']['options']['k'] = opt.k
        info['model']['options']['tol'] = opt.tol
        info['model']['options']['use_expectation'] = False
        info['model']['options']['maxiter'] = opt.maxiter
        info['assets']['recommender'] = MultinomialPLSA
    else:
        raise TypeError(
            "Invalid method name: {0:s}".format(info['model']['method']))

    # test
    info['test']['scheme'] = opt.validation
    info['test']['n_folds'] = opt.fold

    # data
    info['data']['score_domain'] = list(opt.domain)
    info['data']['has_timestamp'] = opt.timestamp

    return info


def main():
    """ Main routine
    """
    # command-line arguments
    opt = command_line_parser()

    # collect assets and information
    info = init_info(opt)

    # do main task
    do_task(info)

# top level -------------------------------------------------------------------
# init logging system
logger = logging.getLogger(os.path.basename(sys.argv[0]))
logging.basicConfig(level=logging.INFO,
                    format='[%(name)s: %(levelname)s'
                           ' @ %(asctime)s] %(message)s')
logger.setLevel(logging.ERROR)
logging.getLogger('kamrecsys').setLevel(logging.ERROR)

# Call main routine if this is invoked as a top-level script environment.
if __name__ == '__main__':

    main()

    sys.exit(0)
