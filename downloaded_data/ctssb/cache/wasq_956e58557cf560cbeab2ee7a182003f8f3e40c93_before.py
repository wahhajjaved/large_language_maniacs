
from Cell import Cells
import PoissonCover as PC
from metrics.dihedral_rmsd import dihedral_rmsd
from Trajectory import calc_dihedral, calc_phipsi

import pxul
import mdprep
from mdq.md.gmx import guamps_get, guamps_set, editconf, mdrun, tpr_set_scalar, tpr_get_scalar, disable_gromacs_backups
import pwq

import mdtraj

import numpy as np
from scipy.spatial import distance

import array
import functools
import glob
import os
import shutil
import tempfile
import cPickle as pickle
import copy

__DEFAULT_METRIC = PC.DEFAULT_METRIC


def load_guamps(path, dtype=str):
    data = open(path).read().strip().split('\n')

    if len(data) == 1: # scalar
        result = dtype(data[0])
        return result

    elif len(data) > 1: # vector
        assert len(data) > 4 # make sure the header is there
        cells, crds, dims = data[:3]
        cells, crds, dims = [
            int(line.strip().split()[-1])
            for line in [cells, crds, dims]
            ]
        values = data[4:]
        assert cells == 1
        assert len(values) == crds * dims
        values = np.array(values).astype(dtype)
        values = values.reshape((crds, dims))
        return values

    else:
        raise ValueError

def write_guamps(path, X):
    with open(path, 'w') as fd:
        try:
            cells = 1
            crds, dims = X.shape
            fd.write('ncells: %d\n' % cells)
            fd.write('ncoords: %d\n' % crds)
            fd.write('ndims: %d\n' % dims)
            fd.write('\n')
            np.savetxt(fd, X.flatten(), fmt='%f')
        except AttributeError:
            fd.write('%f\n' % X)


class SimulationState(object):
    def __init__(self, x=None, v=None, t=None, meta=None):
        assert x is not None
        assert v is not None
        assert t is not None
        self.x = x
        self.v = v
        self.t = t
        self.meta = meta or dict()

    @classmethod
    def from_tpr(cls, path, meta=None):
        path = os.path.abspath(path)
        with pxul.os.TmpDir():
            x,v,t = 'x v t'.split()
            guamps_get(f=path, s='positions',  o=x)
            guamps_get(f=path, s='velocities', o=v)
            guamps_get(f=path, s='time',       o=t)
            return cls(x=load_guamps(x, dtype=float),
                       v=load_guamps(v, dtype=float),
                       t=load_guamps(t, dtype=float),
                       meta=meta)

    @classmethod
    def from_trr(cls, path, frame, meta=None):
        path = os.path.abspath(path)
        with pxul.os.TmpDir():
            x,v,t = 'x v t'.split()
            guamps_get(f=path, s='positions',  o=x, i=frame)
            guamps_get(f=path, s='velocities', o=v, i=frame)
            guamps_get(f=path, s='time',       o=t, i=frame)
            return cls(x=load_guamps(x, dtype=float),
                       v=load_guamps(v, dtype=float),
                       t=load_guamps(t, dtype=float),
                       meta=meta)

    def writeX(self, path): write_guamps(path, self.x)
    def writeV(self, path): write_guamps(path, self.v)
    def writeT(self, path): write_guamps(path, self.t)


class AbstractMDEngine(object):
    def __init__(self, state, **kws):
        self.state = state
        self._kws = kws

    def sample(self):
        """
        return :: tuple =
          trajectory :: mdtraj.Trajectory
          state      :: [SimulationState]
        """
        raise NotImplementedError

    def run(self, R, C, L, workarea=None):
        """
        Returns tuple ::
          C :: NxD array: centroids
          L :: N   array: labels
        """
        if workarea is None:
            dir_ctx = pxul.os.TmpDir
        elif type(workarea) is str:
            dir_ctx = lambda: pxul.os.StackDir(workarea)
        else:
            dir_ctx = lambda: pxul.os.StackDir(workarea())

        with dir_ctx():
            return self.sample()


class GromacsMDEngine(AbstractMDEngine):
    def __init__(self, state, tpr=None, threads=0, **kws):
        super(GromacsMDEngine, self).__init__(state, **kws)
        assert tpr is not None
        self._tpr = tpr
        self._threads = threads

    def sample(self):
        with disable_gromacs_backups():
            x,v,t,tpr = 'x.gps v.gps t.gps topol.tpr'.split()
            # setup
            self.state.writeX(x)
            self.state.writeV(v)
            self.state.writeT(t)
            shutil.copy(self._tpr, tpr)

            # resume
            guamps_set(f=tpr, s='positions',  i=x)
            guamps_set(f=tpr, s='velocities', i=v)
            guamps_set(f=tpr, s='time',       i=t)

            # run
            trr = 'traj.trr'
            pdb = 'topol.pdb'
            mdrun(s=tpr, o=trr, c=pdb, nt=self._threads)

            # result
            traj = mdtraj.load(trr, top=pdb)
            state = np.zeros(len(traj), dtype=np.object)
            for i in xrange(len(traj)):
                new_state = SimulationState.from_trr(trr, i, meta=self.state.meta)
                state[i] = new_state

            return traj, state


class Engines:
    @classmethod
    def create(cls, state, engine_params=None):
        params = engine_params or dict()
        params = copy.copy(engine_params)
        name = params.pop('name', 'gromacs')
        if name == 'gromacs':
            if 'tpr' not in params:
                params['tpr'] = state.meta['tpr']
            e = GromacsMDEngine(state, **params)
        else:
            raise ValueError, 'Could not create MDEngine with params {}'.format(engine_params)

        return e


class Walker(object):
    """
    A walker creates the engine necessary to run the sampling simulation.
    """
    def __init__(self, cell_id, metric=None, engine_params=None):
        self.cell_id   = cell_id
        self.engine_params = engine_params or dict()
        self._metric = metric or dihedral_rmsd

    def cover(self, traj, labels, R, C, L, eps=0.000001):
        phipsi = calc_phipsi(traj)
        C, L = PC.online_poisson_cover(phipsi, R, L=labels, Cprev=C, Lprev=L, metric=self._metric)
        return C, L

    def run(self, radius, cells):
        state = cells.L[self.cell_id]
        engine = Engines.create(state, self.engine_params)
        traj, labels = engine.sample()
        C, L = self.cover(traj, labels, radius, cells.C, cells.L)
        Cnew = C[len(cells):]
        Lnew = L[len(cells):]
        return Cnew, Lnew


class AbstractAdaptiveSampler(object):
    def __init__(self, radius, cells, iterations=float('inf'), workarea='AS', engine='gromacs', engine_params=None):
        self.R = radius                          # :: float: the radius
        self.cells = cells                       # :: Cells
        self.current_iteration = 0               # :: int
        self.max_iterations = iterations         # :: int
        self.metric = dihedral_rmsd              # :: a -> a -> a
        self.workarea = workarea                 # :: filepath
        self.engine_params = engine_params or {} # :: dict(string -> a)
        self.engine_params['name'] = engine

    @classmethod
    def from_tprs(cls, initials, radius, **init_kws):
        C = []
        L = np.zeros(len(initials), dtype=np.object)
        inits = map(os.path.abspath, initials)
        with pxul.os.TmpDir(), disable_gromacs_backups():
            pdb = 'topol.pdb'
            for tprid, tpr in enumerate(inits):
                editconf(f=tpr, o=pdb)
                traj = mdtraj.load(pdb)
                phipsi = calc_phipsi(traj)
                L[tprid] = SimulationState.from_tpr(tpr, meta = dict(tpr=tpr, tprid=tprid))
                C.append(phipsi)
        C = np.vstack(C)
        cells = Cells(C, L)

        return cls(radius, cells, **init_kws)

    @property
    def cells_dir(self):
        return os.path.join(self.workarea, 'cells')

    @property
    def iteration_dir(self):
        return os.path.join(self.workarea, 'iteration', '{:05d}'.format(self.current_iteration))

    @property
    def final_dir(self):
        return os.path.join(self.workarea, 'iteration', 'last')

    def select_by_kissing_number(self):
        """
        Select a subset of centroids to start new walkers from
        Accepts:
          C :: NxM array: the centroids
        Returns:
          I :: [Int]: indices into C to start new simulations from
        """
        ns = PC.neighborhood_size(self.cells.C, self.R)
        dim = self.cells.dim
        kissing_number = PC.KISSING_NUMBERS[dim]
        fringes = np.where(ns < kissing_number)[0]
        return fringes

    def select(self):
        return self.select_by_kissing_number()

    def _select(self):
        count = self.select()
        if len(count) < 1:
            raise StopIteration
        else:
            return count

    def current_walkers(self):
        return self.cells.L

    def run_walker(self, walker):
        raise NotImplementedError

    def collect_results(self):
        raise NotImplementedError

    def iterate(self):
        "Run one iteration"
        walkers = set(self._select())

        with pxul.os.StackDir(self.iteration_dir):
            print self.current_iteration, len(walkers)
            with open('nwalkers.txt', 'w') as fd:
                fd.write('{}\n'.format(len(walkers)))

        for i,cellid in enumerate(walkers):
            w = Walker(cellid, metric=self.metric, engine_params=self.engine_params)
            self.run_walker(w)

        ncells = len(self.cells)
        C = self.cells.C
        L = self.cells.L
        for Cw, Sw in self.collect_results():
            C, L = PC.online_poisson_cover(Cw, self.R, L=Sw, Cprev=C, Lprev=L, metric=self.metric)
        self.cells.learn(C[ncells:], L[ncells:])

    def write_log(self, logdir=None):
        outdir = logdir or self.cells_dir
        self.cells.write_to_dir(outdir)

    def run(self, eps=0.000001):
        while self.current_iteration < self.max_iterations:
            self.write_log()
            try: self.iterate()
            except StopIteration: break
            self.current_iteration += 1
        self.write_log()


class LocalAdaptiveSampler(AbstractAdaptiveSampler):
    "Run adaptive sampling on the local  machine"
    def __init__(self, *args, **kws):
        super(LocalAdaptiveSampler, self).__init__(*args, **kws)
        self._iteration_results = list()

    def run_walker(self, walker):
        r = walker.run(self.R, self.cells)
        self._iteration_results.append(r)

    def collect_results(self):
        for r in self._iteration_results:
            yield r
        self._iteration_results = list()



class WorkQueueWalker(object):
    def __init__(self, cellid, radius, cellsdir, engine_params):
        self.cellid = cellid
        self.radius = radius
        self.cellsdir = cellsdir
        self.engine_params = engine_params

    def add_state(self, task, state):
        engine = self.engine_params['name']
        if engine == 'gromacs':
            tpr_worker = 'ref-{i}_{base}.tpr'.format(i=state.meta['tprid'], base='topol')
            tpr_master = state.meta['tpr']
            self.engine_params['tpr'] = tpr_worker
            self.engine_params['threads']
            task.specify_input_file(tpr_master, tpr_worker, cache=True)
        else:
            raise ValueError, 'Unknown engine {}'.format(engine)

    def run(self):
        from wasq.Cell import Cells
        from wasq.AdaptiveSampling import Walker
        import cPickle as pickle

        cells  = Cells.load_from_dir(self.cellsdir)
        walker = Walker(self.cellid, engine_params=self.engine_params)
        result = walker.run(self.radius, cells)
        return result


class PythonTaskWorkQueueAdaptiveSampler(AbstractAdaptiveSampler):
    "Run using WorkQueue, but the Tasks are just pickled Walkers"

    def __init__(self, *args, **kws):
        super(PythonTaskWorkQueueAdaptiveSampler, self).__init__(*args, **kws)
        self._wq = None
        self.task_files_dir = os.path.join(self.workarea, 'task_files')
        pxul.os.ensure_dir(self.task_files_dir)

        self.worker_walker = 'walker.pkl'
        self.worker_result = 'result.pkl'
        self.log_tasks = None

    def set_workqueue(self, wq):
        self._wq = wq

    def set_task_logger(self, logger):
        self.log_tasks = logger

    def log_task(self, task):
        if self.log_tasks is not None:
            self.log_tasks.process(task)

    def run_walker(self, walker):
        pxul.os.ensure_dir(self.iteration_dir)

        remote_cells_dir = os.path.basename(self.cells_dir)
        wrapped_walker = WorkQueueWalker(walker.cell_id, self.R, remote_cells_dir, self.engine_params)

        wasq_root = os.environ['WASQ_ROOT']

        runtask = os.path.join(wasq_root, 'wasq', 'runtask.py')

        t = pwq.Task('python runtask.py -i {input} -o {output}'.format(input=self.worker_walker, output=self.worker_result))
        t.specify_input_file(runtask, 'runtask.py', cache=True)

        t.specify_input_file(self.walker_path(t), self.worker_walker, cache=False)
        t.specify_output_file(self.result_path(t), self.worker_result, cache=False)

        self.cells.write_to_dir(self.cells_dir)
        t.specify_input_file(self.cells_dir, remote_cells_dir, cache=True)

        wrapped_walker.add_state(t, self.cells.L[walker.cell_id])

        pickle.dump(wrapped_walker, open(self.walker_path(t), 'wb'), pickle.HIGHEST_PROTOCOL)
        self._wq.submit(t)

    def walker_path(self, task):
        return os.path.join(self.task_files_dir, '{name}.{ext}'.format(name=self.worker_walker, ext=task.uuid))
    def result_path(self, task):
        return os.path.join(self.task_files_dir, '{name}.{ext}'.format(name=self.worker_result, ext=task.uuid))

    def collect_results(self):

        while not self._wq.empty():
            t = self._wq.wait(5)

            # success
            if t and t.success:
                self.log_task(t)
                walker_pkl = self.walker_path(t)
                os.unlink(walker_pkl)

            # failure
            elif t:
                self.log_task(t)
                msg = 'task %s failed with code %s\n' % (t.command, t.result)
                msg += t.output
                raise Exception, msg

        for result_pkl in glob.iglob(os.path.join(self.task_files_dir, '{}.*'.format(self.worker_result))):
            result = pickle.load(open(result_pkl, 'rb'))
            yield result
            os.unlink(result_pkl)


def test(opts):
    sampler = PythonTaskWorkQueueAdaptiveSampler.from_tprs(opts.ref, opts.tprs, opts.radius, iterations=opts.iterations)
    walkers = sampler.current_walkers()
    w = walkers.next()
    sampler.run_walker(w)
    

def getopts():
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    engine_choices = ['gromacs']

    p = ArgumentParser()
    p.add_argument('-d', '--debug', default=False, help='Turn on debugging')
    p.add_argument('-p', '--port', default=9123, help='Start WorkQueue on this port')
    p.add_argument('-n', '--name', help='Use <name> with the Catalog Server')
    p.add_argument('-l', '--logdir', default='wq', help='Where to log WQ statistics')
    p.add_argument('-r', '--radius', default=20.0, type=float, help='Radius to use when covering data points')
    p.add_argument('-i', '--iterations', type=int, default=float('inf'), help='Number of AS iterations to run')
    p.add_argument('-e', '--engine', default='gromacs', choices=engine_choices)
    p.add_argument('tprs', metavar='TPR', nargs='+', help='Coordinates for the initial states.')

    opts = p.parse_args()
    print 'iterations:', opts.iterations
    opts.tprs = map(os.path.abspath, opts.tprs)
    return opts

def main(opts):
    sampler = PythonTaskWorkQueueAdaptiveSampler.from_tprs(opts.tprs, opts.radius, iterations=opts.iterations, engine=opts.engine,
                                                           engine_params = dict(threads = 0))

    mkq = pwq.MkWorkQueue().replicate().port(opts.port)

    if opts.debug:
        mkq.debug()
    if opts.name:
        mkq.catalog().name(opts.name)
    if opts.logdir:
        logdir = os.path.join(sampler.workarea, opts.logdir)
        pxul.os.ensure_dir(logdir)
        log_master_path = os.path.join(logdir, 'wq.log')
        log_tasks_path  = os.path.join(logdir, 'tasks.gz')
        mkq.logfile(log_master_path)
        logger = pwq.TaskStatsLogger(log_tasks_path)
        sampler.set_task_logger(logger)

    q = mkq()
    print 'WorkQueue running on', q.port
    sampler.set_workqueue(q)

    sampler.run()

if __name__ == '__main__':
    opts = getopts()
    main(opts)
