
from __future__ import print_function, absolute_import
import random
import sys

import scicfg
from clusterjobs import datafile
import environments
import explorers
import learners

from ..tools import chrono, autosave
from .. import provenance


def exploration_step(env, explorer, tries=3):
    """Explore the step"""
    try_count = 0
    while try_count < tries:
        try:
            meta = {}
            exploration = explorer.explore()

            m_signal = exploration['m_signal']
            feedback = env.execute(m_signal, meta=meta)
            break
        except env.OrderNotExecutableError:
            try_count += 1

    explorer.receive(exploration, feedback)
    return {'exploration': exploration, 'feedback': feedback, 'meta': meta}

def load_existing_datafile(cfg, core_keys):
    """Load existing datafile and checks, if it exists."""
    if datafile.isfile(cfg.hardware.datafile):
        history = chrono.ChronoHistory(cfg.hardware.datafile, cfg.hardware.logfile,
                                       core_keys=core_keys,
                                       extralog=cfg.hardware.logs,
                                       verbose=True)
        # compare config.run with config
        assert history.meta['jobcfg.pristine'] == cfg
        # load config.track & tracking checks
        #tracking.check(history.meta['cfg.track'])
        return history

def load_src_files(cfg, env_m_channels):
    """Load datafile from the source tasks and create corresponding datasets"""
    src_datasets = []

    for src_filepath in cfg.hardware.src_files:
        src_history      = chrono.ChronoHistory(src_filepath, extralog=False, verbose=True)
        src_explorations = [(entry['data']['exploration'], entry['data']['feedback'])  for entry in src_history]
        src_cfg          = src_history.meta['jobcfg']['exploration']
        src_dataset      = {'m_channels'  : src_cfg.explorer.m_channels,
                            's_channels'  : src_cfg.explorer.s_channels,
                            'explorations': src_explorations}
        src_datasets.append(src_dataset)
        assert env_m_channels == src_cfg.explorer.m_channels

    return src_datasets

def gather_provenance(cfg, env, check_dirty=True):
    prov_cfg = scicfg.SciConfig()
    prov_cfg.check_dirty = cfg.provenance.check_dirty
    prov_cfg.packages = provenance.packages_info(cfg.provenance.package_names)
    prov_cfg.platform = provenance.platform_info()
    prov_cfg.env      = env.info()
    prov_cfg.code     = cfg.provenance._get('code', scicfg.SciConfig())

    if check_dirty:
        provenance.check_dirty(prov_cfg)

    return prov_cfg

def check_provenance(cfg, prov_cfg):
    assert cfg.provenance.packages == prof_cfg.packages
    assert cfg.platform.python     == prof_cfg.python
    assert cfg.env                 == prof_cfg.env

def explore(cfg):
    cfg_orig = cfg._deepcopy()
    autosave.period = cfg.hardware.autosave_period

    try:
            ## Load potentially existing data ##
        history = load_existing_datafile(cfg, core_keys=('exploration', 'feedback'))
        if history is None:
            # set a random seed if none already set.
            cfg.hardware._setdefault('seed', random.randint(0, 9223372036854775807)) # sys.maxint
        else:
            # replace config by the previous (matching) config,
            # as it contains non-reproductible explorers uuids, and provenance data.
            cfg = history.meta['jobcfg']

        random.seed(cfg.hardware.seed)


            ## Instanciating the environment ##

        env = environments.Environment.create(cfg.exploration.env)


            ## Instanciating the explorer ##

        src_datasets = load_src_files(cfg, env.m_channels)
        if history is None:
            cfg.exploration.explorer.m_channels = env.m_channels
            cfg.exploration.explorer.s_channels = env.s_channels
        explorer = explorers.Explorer.create(cfg.exploration.explorer, datasets=src_datasets)
        print('configuration:\n', cfg, '\n', sep='')


            ## Running learning ##

        prov_cfg = gather_provenance(cfg, env, check_dirty=True)

        if history is not None:
            check_provenance(cfg, prov_cfg)
        else:
            cfg.provenance._update(prov_cfg, overwrite=True)

            history = chrono.ChronoHistory(cfg.hardware.datafile, cfg.hardware.logfile,
                                           meta={'jobcfg.pristine': cfg_orig,
                                                 'jobcfg': cfg,
                                                 'm_channels': env.m_channels,
                                                 's_channels': env.s_channels,
                                                 'random_state': random.getstate()},
                                           core_keys=('exploration', 'feedback'),
                                           extralog=cfg.hardware.logs,
                                           verbose=True, load=False)

        # setting random state
        random.setstate(history.meta['random_state'])

        # replaying history
        for entry in history:
            explorer.receive(entry['data']['exploration'], entry['data']['feedback'])


        # running exploration; the next three lines are the core of the experiment.
        for t in range(len(history), cfg.exploration.steps):
            entry = exploration_step(env, explorer)
            history.add_entry(t, entry)
            if autosave.autosave():
                # save history at regular intervals
                history['random_state'] = random.getstate()
                history.save()


            ## Finishing ##

        feedback_history = chrono.ChronoHistory(cfg.hardware.sensoryfile, None,
                                                core_keys=('s_signal', 'from'), load=False,
                                                meta={'jobcfg': cfg,
                                                      'm_channels': env.m_channels,
                                                      's_channels': env.s_channels})
        for t, entry in enumerate(history):
            exploration = entry['data']['exploration']
            feedback    = entry['data']['feedback']

            feedback_history.add_entry(t, {'s_signal': feedback['s_signal'], 'from': exploration['from']})
        feedback_history.save()

        history.save(verbose=True, done=True)
        datafile.save_config(cfg, filename=cfg.hardware.configfile+'.done', directory='')

    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        env.close()
