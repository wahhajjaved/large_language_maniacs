import autocorr as ac
import bz2
import emcee
import numpy as np
import os
import os.path as op
import pickle

def load_runner(dir):
    """Loads the saved runner from the given directory.

    """
    with bz2.BZ2File(op.join(dir, 'runner.pkl.bz2'), 'r') as inp:
        runner = pickle.load(inp)
    return runner

class EnsembleSamplerRunner(object):
    """Runner object for an emcee sampler.

    """

    def __init__(self, sampler, pts):
        """Initialise the runner with the given sampler and initial ensemble
        position.

        """

        self.sampler = sampler
        self.reset(pts=pts)

    @property
    def chain(self):
        """The current state of the sampler's chain.

        """
        return self.sampler.chain

    @property
    def lnprobability(self):
        """The current state of the sampler's lnprobability.

        """
        return self.sampler.lnprobability

    @property
    def burnedin_chain(self):
        """Returns a chain with the first 1/6 of the samples removed.  This
        chain corresponds to the samples that are then thinned to
        produce the ``thin_chain`` property.  There is, of course, no
        guarantee that this chain is actually burned in.

        """
        nensembles = self.chain.shape[1]
        istart = int(round(nensembles/6.0))

        return self.chain[:,istart:,:]

    @property
    def thin_chain(self):
        """Return a thinned chain (if possible), using
        :func:`ac.emcee_thinned_chain`

        """
        if self.chain.shape[1] == 0:
            return None
        else:
            return ac.emcee_thinned_chain(self.chain)

    @property
    def thin_flatchain(self):
        """Returns a thinned chain that has been flattened.

        """
        tc = self.thin_chain
        if tc is None:
            return None
        else:
            return tc.reshape((-1, tc.shape[2]))

    @property
    def acls(self):
        """Return the estimate of the current chain's autocorrelation lengths,
        using :func:`plotutils.autocorr.emcee_chain_autocorrelation_lengths`.

        """
        return ac.emcee_chain_autocorrelation_lengths(self.chain)

    def save_state(self, dir):
        """Save the state of the runner stored chain, lnprob, and thin
        parameter in the given directory.  Three files will be created
        (approximately atomically, so the operation is nearly safe
        from interruption):

         * ``chain.npy.bz2``
         * ``lnprob.npy.bz2``
         * ``thin.txt``

        Storing the current chain, lnprob and the thin parameter.

        In addition, the file runner.pkl.bz2 will be created storing a
        pickled version of the runner object.

        """

        with bz2.BZ2File(op.join(dir, 'chain.npy.bz2.temp'), 'w') as out:
            np.save(out, self.chain)
        with bz2.BZ2File(op.join(dir, 'lnprob.npy.bz2.temp'), 'w') as out:
            np.save(out, self.lnprobability)
        with open(op.join(dir, 'thin.txt.temp'), 'w') as out:
            out.write('{0:d}\n'.format(self.thin))

        try:
            os.rename(op.join(dir, 'chain.npy.bz2.temp'),
                      op.join(dir, 'chain.npy.bz2'))
            os.rename(op.join(dir, 'lnprob.npy.bz2.temp'),
                      op.join(dir, 'lnprob.npy.bz2'))
            os.rename(op.join(dir, 'thin.txt.temp'),
                      op.join(dir, 'thin.txt'))
        except:
            print 'WARNING: EnsembleSamplerRunner: interrupted during save, inconsistent saved state'
            raise

        try:
            with bz2.BZ2File(op.join(dir, 'runner.pkl.bz2.temp'), 'w') as out:
                pickle.dump(self, out)
            os.rename(op.join(dir, 'runner.pkl.bz2.temp'),
                      op.join(dir, 'runner.pkl.bz2'))
        except:
            print 'WARNING: EnsembleSampleRunner: pickling of runner failed.'

    def load_state(self, dir):
        """Load a stored state from the given directory.

        """
        try:
            with bz2.BZ2File(op.join(dir, 'chain.npy.bz2'), 'r') as inp:
                self.sampler._chain = np.load(inp)
            with bz2.BZ2File(op.join(dir, 'lnprob.npy.bz2'), 'r') as inp:
                self.sampler._lnprob = np.load(inp)
            with open(op.join(dir, 'thin.txt'), 'r') as inp:
                self.thin = int(inp.readline())

            self.result = self.chain[:,-1,:]
            self._first_step = True
        except:
            print 'WARNING: EnsembleSamplerRunner: interrupted during load, inconsistent loaded state'
            raise

    def run_mcmc(self, nthinsteps):
        """Run the associated sampler to produce ``nthinsteps`` worth of
        stored ensembles (i.e. the sampler will be run for
        ``nthinsteps*self.thin`` total steps).

        """

        nsteps = self.thin * nthinsteps
        
        if self._first_step:
            self.result = self.sampler.run_mcmc(self.result, nsteps, thin=self.thin)
            self._first_step = False
        else:
            self.result = self.sampler.run_mcmc(self.result[0], nsteps, lnprob0=self.result[1], thin=self.thin)

        return self.result

    def run_to_neff(self, neff, savedir=None):
        """Run the sampler, thinning as necessary, until ``neff`` effective
        ensembles are obtained.  When ``savedir`` is not ``None``, the
        sampler will be periodically saved to the given directory.

        """
        
        while self.chain.shape[1] == 0 or self.thin_chain is None or self.thin_chain.shape[1] < neff:
            self.run_mcmc(neff)
            
            print 'Accumulated ', self.chain.shape[1], ' ensembles'
            if self.thin_chain is not None:
                print 'Equivalent to ', self.thin_chain.shape[1], ' effective ensembles'

            if savedir is not None:
                print 'Saving state...'
                self.save_state(savedir)

            if self.chain.shape[1] > 10*neff:
                self.rethin()
                print 'Thinned chain; now ', self.chain.shape[1], ' ensembles'

    def rethin(self):
        """Increase the thinning parameter by a factor of two, modifying the
        stored chain and lnprob states accordingly.  

        """

        self.sampler._chain = self.sampler._chain[:,1::2,:]
        self.sampler._lnprob = self.sampler._lnprob[:,1::2]
        self.thin *= 2

    def reset(self, pts=None):
        """Resets the stored sampler and internal state.  If no ``pts``
        argument is given, will use the last position of the sampler
        as the new starting position; otherwise, the new starting
        position will be given by ``pts``.

        """

        if pts is None:
            if self._first_step:
                pts = self.result
            else:
                pts = self.result[0]

        self.result = pts
        self._first_step = True

        self.thin = 1

        self.sampler.reset()

class PTSamplerRunner(EnsembleSamplerRunner):
    r"""Runner class for the PTSampler; basically behaves as
    :class:`EnsembleSamplerRunner`, but tailored to the different
    chain shape and behaviour of :class:`emcee.PTSampler`.

    """

    def __init__(self, sampler, pts):
        """Initialise the runner with the given sampler and initial ensemble
        position.

        """

        super(PTSamplerRunner, self).__init__(sampler, pts)

    @property
    def lnlikelihood(self):
        """Returns the current state of the sampler's lnlikelihood.
        
        """
        return self.sampler.lnlikelihood

    @property
    def burnedin_chain(self):
        """Returns a chain with the first 1/6 of the samples removed.  This
        chain corresponds to the samples that are then thinned to
        produce the ``thin_chain`` property.  There is, of course, no
        guarantee that this chain is actually burned in.

        """
        nensembles = self.chain.shape[2]
        istart = int(round(nensembles/6.0))

        return self.chain[:,:,istart:,:]

    @property
    def thin_chain(self):
        """Return a thinned chain (if possible), using
        :func:`ac.emcee_thinned_ptchain`

        """
        if self.chain is None or self.chain.shape[2] == 0:
            return None
        else:
            return ac.emcee_thinned_ptchain(self.chain)

    @property
    def thin_flatchain(self):
        """Returns a thinned chain that has been flattened.

        """
        tc = self.thin_chain
        if tc is None:
            return None
        else:
            return tc.reshape((tc.shape[0], -1, tc.shape[3]))

    @property
    def acls(self):
        """Return the estimate of the current chain's autocorrelation lengths,
        using :func:`plotutils.autocorr.emcee_ptchain_autocorrelation_lengths`.

        """
        return ac.emcee_ptchain_autocorrelation_lengths(self.chain)

    def save_state(self, dir):
        """Save the state of the runner stored chain, lnprob, lnlike, betas,
        and thin parameter in the given directory.  Three files will
        be created (approximately atomically, so the operation is
        nearly safe from interruption):

         * ``chain.npy.bz2``
         * ``lnprob.npy.bz2``
         * ``lnlike.npy.bz2``
         * ``betas.txt``
         * ``thin.txt``

        Storing the current chain, lnprob, lnlike, betas (inverse
        temperatures), and the thin parameter.

        In addition, the file runner.pkl.bz2 will be created storing a
        pickled version of the runner object.

        """

        with bz2.BZ2File(op.join(dir, 'chain.npy.bz2.temp'), 'w') as out:
            np.save(out, self.chain)
        with bz2.BZ2File(op.join(dir, 'lnprob.npy.bz2.temp'), 'w') as out:
            np.save(out, self.lnprobability)
        with bz2.BZ2File(op.join(dir, 'lnlike.npy.bz2.temp'), 'w') as out:
            np.save(out, self.lnlikelihood)
        with open(op.join(dir, 'betas.txt.temp'), 'w') as out:
            np.savetxt(out, self.sampler.betas.reshape((1, -1)))
        with open(op.join(dir, 'thin.txt.temp'), 'w') as out:
            out.write('{0:d}\n'.format(self.thin))

        try:
            os.rename(op.join(dir, 'chain.npy.bz2.temp'),
                      op.join(dir, 'chain.npy.bz2'))
            os.rename(op.join(dir, 'lnprob.npy.bz2.temp'),
                      op.join(dir, 'lnprob.npy.bz2'))
            os.rename(op.join(dir, 'lnlike.npy.bz2.temp'),
                      op.join(dir, 'lnlike.npy.bz2'))
            os.rename(op.join(dir, 'betas.txt.temp'),
                      op.join(dir, 'betas.txt'))
            os.rename(op.join(dir, 'thin.txt.temp'),
                      op.join(dir, 'thin.txt'))
        except:
            print 'WARNING: EnsembleSamplerRunner: interrupted during save, inconsistent saved state'
            raise

        try:
            with bz2.BZ2File(op.join(dir, 'runner.pkl.bz2.temp'), 'w') as out:
                pickle.dump(self, out)
            os.rename(op.join(dir, 'runner.pkl.bz2.temp'),
                      op.join(dir, 'runner.pkl.bz2'))
        except:
            print 'WARNING: EnsembleSampleRunner: pickling of runner failed.'

    def load_state(self, dir):
        """Load a stored state from the given directory.

        """
        try:
            with bz2.BZ2File(op.join(dir, 'chain.npy.bz2'), 'r') as inp:
                self.sampler._chain = np.load(inp)
            with bz2.BZ2File(op.join(dir, 'lnprob.npy.bz2'), 'r') as inp:
                self.sampler._lnprob = np.load(inp)
            with bz2.BZ2File(op.join(dir, 'lnlike.npy.bz2'), 'r') as inp:
                self.sampler._lnlikelihood = np.load(inp)
            with open(op.join(dir, 'betas.txt'), 'r') as inp:
                self.sampler._betas = np.loadtxt(inp)
            with open(op.join(dir, 'thin.txt'), 'r') as inp:
                self.thin = int(inp.readline())

            self.result = self.chain[:,:,-1,:]
            self._first_step = True
        except:
            print 'WARNING: EnsembleSamplerRunner: interrupted during load, inconsistent loaded state'
            raise

    def run_to_neff(self, neff, savedir=None):
        """Run the sampler, thinning as necessary, until ``neff`` effective
        ensembles are obtained.  When ``savedir`` is not ``None``, the
        sampler will be periodically saved to the given directory.

        """
        
        while self.thin_chain is None or self.thin_chain.shape[2] < neff:
            self.run_mcmc(neff)
            
            print 'Accumulated ', self.chain.shape[2], ' ensembles'
            if self.thin_chain is not None:
                print 'Equivalent to ', self.thin_chain.shape[2], ' effective ensembles'

            if savedir is not None:
                print 'Saving state...'
                self.save_state(savedir)

            if self.chain.shape[2] > 10*neff:
                self.rethin()
                print 'Thinned chain; now ', self.chain.shape[2], ' ensembles'

    def rethin(self):
        """Increase the thinning parameter by a factor of two, modifying the
        stored chain and lnprob states accordingly.  

        """

        self.sampler._chain = self.sampler._chain[:,:,1::2,:]
        self.sampler._lnprob = self.sampler._lnprob[:,:,1::2]
        self.sampler._lnlikelihood = self.sampler._lnlikelihood[:,:,1::2]
        self.thin *= 2
