# -*- coding: utf-8 -*-

import time
import logging

import numpy as np
import numpy.matlib

import pyhrf

from pyhrf.ndarray import xndarray, stack_cuboids
from pyhrf import xmlio
from pyhrf.tools import array_summary, get_2Dtable_string


logger = logging.getLogger(__name__)


class DuplicateVariableException(Exception):
    def __init__(self, vName, v):
        self.variableName = vName
        self.variableObject = v

    def __str__(self):
        return 'vname:' + str(self.variableName)


class VariableTypeException(Exception):
    def __init__(self, vClass, vName, v):
        self.variableName = vName
        self.variableObject = v
        self.variableClass = vClass


class GibbsSampler:

    """
    Generic class of a Gibbs sampler with gathers common operations for any
    gibbs sampling: variable initialisation, observables updates (posterior mean),
    outputs ...
    """

    def __init__(self, variables, nbIt, smplHistoryPace=-1,
                 obsHistoryPace=-1, nbSweeps=None,
                 callbackObj=None, randomSeed=None, globalObsHistoryPace=-1,
                 check_ftval=None, output_fit=False):
        """
        Initialize a new GibbsSampler object.
        @param variables: contains all instances of type C{GibbsSamplerVariable}
        involved in sampling.
        @param dataInput: data to fit
        @param nbIt: is the number of maximum steps to terminate the sampling
        @param callbackObj: is an object which function L{callback()} is called
        after each sampling iteration (typically for plotting/report purpose.
        See C{GSDefaultCallbackHandler}.
        """

        # TODO change to Exceptions ...
        # Check for type consistency :
        if type(variables) != type(list()):
            logger.error('Error : given variables of type : \'%s\' '
                         '-> need a list', type(variables))
            return
        self.variablesMapping = {}
        for var in variables:
            # if var is not an instance of GibbsSamplerVariable
            if not isinstance(var, GibbsSamplerVariable):
                # TODO : exception ...
                logger.error('!Err : variable(%s) of wrong type -> '
                             'need a derivation of GibbsSamplerVariable',
                             var.__class__)
                raise VariableTypeException(var.__class__, var.name, var)
            else:
                if not self.variablesMapping.has_key(var.name):
                    self.variablesMapping[var.name] = var
                else:
                    raise DuplicateVariableException(var.name, var)
        self.variables = variables  # variables involved in sampling

        if callbackObj is None:
            self.callbacker = GSDefaultCallbackHandler()
        else:
            self.callbacker = callbackObj

        self.nbSweeps = nbSweeps
        self.nbIterations = nbIt
        self.output_fit = output_fit
        self.smplHistoryPace = smplHistoryPace
        self.obsHistoryPace = obsHistoryPace
        self.globalObsHistoryPace = globalObsHistoryPace
        self.globalObsHistoryIts = None
        self.globalObsHistoryTiming = None

        self.tSamplingOnly = 0
        self.analysis_duration = 0
        self.tVars = np.zeros(len(variables), dtype=float)

        for v in variables:
            v.registerNbIterations(nbIt)
            v.setSamplerEngine(self)

        self.sharedData = None
        self.randomSeed = randomSeed

        self.check_ftval = check_ftval

    def set_nb_iterations(self, n):
        prev_its = self.nbIterations
        self.nbIterations = n

        logger.debug('set_nb_iterations to %d', n)
        logger.debug('prev nb sweep %d', self.nbSweeps)

        if self.nbSweeps > 0:
            self.nbSweeps = int(np.ceil(self.nbSweeps * (n * 1. / prev_its)))

        logger.debug('new nb sweep %d', self.nbSweeps)

        if self.smplHistoryPace > 0:
            self.smplHistoryPace = int(np.ceil(self.smplHistoryPace *
                                               (n * 1. / prev_its)))

        if self.obsHistoryPace > 0:
            self.obsHistoryPace = int(np.ceil(self.obsHistoryPace *
                                              (n * 1. / prev_its)))

    def linkToData(self, dataInput):
        #-> set input data
        self.dataInput = dataInput
        self.fit = None  # TODO init fit according to input signal shape
        for v in self.variables:
            logger.info('%s -> linking to data', v.name)
            v.linkToData(dataInput)
            if (v.axes_names is not None) and ('condition' in v.axes_names):
                v.axes_domains['condition'] = self.dataInput.cNames

    def regVarsInPipeline(self):

        if self.sharedData == None:
            raise Exception("sharedData isn\'t initialized !")

        rules = []
        for v in self.variables:
            rules.append({'label': v.name, 'ref': v})

        self.sharedData.addDependencies(rules)

    def get_variable(self, label):
        return self.variablesMapping[label]

    def iterate_sampling(self):
        it = 0
        while it < self.nbIterations and not self.stop_criterion(it):
            yield it
            it += 1

    def stop_criterion(self, it):
        return False

    def runSampling(self, atomData=None):
        # np.seterr(all='raise')
        """
        Launch a complete sampling process by calling the function
        L{GibbsSamplerVariable.sampleNext()} of each variable. Call the callback
        function after each iteration. Measure time elapsed and store it in
        L{tSamplinOnly} and L{analysis_duration}
        """
        if self.randomSeed is not None:
            logger.info('setting random seed: %s', str(self.randomSeed))
            np.random.seed(self.randomSeed)
        else:
            logger.info('No random seed specified ')

        #self.itAxis = []
        if self.nbSweeps is None:
            self.nbSweeps = self.nbIterations / 3

        logger.info('Nb sweeps: %d', self.nbSweeps)
        logger.info('obs hist pace: %d', self.obsHistoryPace)
        logger.info('smpl hist pace: %d', self.obsHistoryPace)

        for v in self.variables:
            logger.info('Init of ' + v.name)
            logger.info(v.get_summary())
            v.checkAndSetInitValue(self.variables)
            if type(v.currentValue) == numpy.ndarray:
                logger.debug(v.currentValue)
            else:
                logger.debug(v.currentValue)

        # Warming up variables to sample (precalculations):
        for v in self.variables:
            if v.useTrueValue:
                if v.trueValue is None:
                    raise Exception("No true value defined for %s" % v.name)

            logger.info('Warming of ' + v.name)
            v.samplingWarmUp(self.variables)
            v.initObservables()
        self.initGlobalObservables()

        # init for time measures :
        tGlobIni = time.time()
        tIni = time.time()

        # main loop over variables to sample :
        nbIt2EstimTime = max(1, min(10, int(self.nbIterations * 0.1)))
        tLoopShown = False
        logger.info('Starting sampling (%d it)...', self.nbIterations)
        try:
            lhrf = self.get_variable('hrf').hrfLength
        except KeyError:
            lhrf = self.get_variable('brf').hrfLength

        logger.info('Data dims : nbvox=%d, ny=%d, nbCond=%d, nb coeffs hrf=%d',
                    self.dataInput.nbVoxels, self.dataInput.ny,
                    self.dataInput.nbConditions, lhrf)

        tLoopIni = time.time()
        for v in self.variables:
            if self.smplHistoryPace != -1:
                logger.info('Saving init value of %s', v.name)
                v.saveCurrentValue(-1)

        rerror = np.array([])
        loglkhd = np.array([])

        for it in self.iterate_sampling():
            iv = 0

            for v in self.variables:
                tIniv = time.time()

                if not v.sampleFlag:
                    logger.info('(it %d) %s not sampled', it, v.name)
                else:
                    logger.info('(it %d) Sampling of %s ...', it, v.name)
                v.sampleNext(self.variables)

                logger.debug('current value of %s:', v.name)
                logger.debug(v.currentValue)
                if v.sampleFlag:
                    logger.info('(it %d) Sampling of %s done !', it, v.name)
                self.tVars[iv] += time.time() - tIniv
                iv += 1

            for v in self.variables:

                v.record_trajectories(it)

                if self.smplHistoryPace != -1 and (it % self.smplHistoryPace) == 0:
                    logger.info('(it %d) saving sample of %s)', it, v.name)
                    v.saveCurrentValue(it)

                # Update observables after burn-in period :
                if it >= self.nbSweeps:
                    v.updateObsersables()
                    if self.obsHistoryPace != -1 and (it % self.obsHistoryPace) == 0:
                        logger.info(
                            '(it %d) saving observables of %s', it, v.name)
                        v.saveObservables(it)

            if it >= self.nbSweeps:
                self.updateGlobalObservables()
                if self.globalObsHistoryPace != -1 and \
                        (it % self.globalObsHistoryPace) == 0:
                    self.saveGlobalObservables(it)

            # if pyhrf.verbose.verbosity >= 6:
            #     try:
            #         f = self.computeFit()
            #         err = np.sqrt((self.dataInput.varMBY - f)**2)
            #         pyhrf.verbose(6, 'Errors:')
            #         pyhrf.verbose.printNdarray(6, err)
            #     except NotImplementedError:
            #         pass

            # Save jde_fit()
            #self.jde_fit_vec = np.append(self.jde_fit_vec, self.computeFit())

            # Compute error measures
            try:
                bold = atomData.bold

                # relative reconstruction error
                jde_fit = self.computeFit()
                r = bold - jde_fit
                rec_error_j = np.sum(r ** 2, 0)
                bold2 = np.sum(bold ** 2, 0)
                #rec_error = np.mean(rec_error_j/bold2)   # Univariate analysis
                rec_error = np.mean(rec_error_j) / np.mean(bold2)
                rerror = np.append(rerror, rec_error)

                # Loglikelihood
                var_noise = self.get_variable('noise_var').currentValue
                loglh = 0
                N = r.shape[0]
                J = r.shape[1]
                for j in np.arange(0, J):
                    loglh -= (np.log(np.abs(2*np.pi*var_noise[j]*N)) + \
                        np.dot(r[:,j].T,r[:,j])/var_noise[j] / 2)
                loglkhd = np.append(loglkhd, loglh)

            except AttributeError:
                pass


            # Some verbose about online profiling :
            now = time.time()
            self.loop_timing = (now - tLoopIni)

            if not tLoopShown and it >= nbIt2EstimTime - 1:
                tLoop = self.loop_timing / nbIt2EstimTime
                tSampling = tLoop * (self.nbIterations - nbIt2EstimTime)
                logger.info('Time of loop : %1.2fs => total time ~%1.2fs',
                            tLoop, tSampling)
                logger.info(
                    'Now is: %s', time.strftime('%c', time.localtime()))
                logger.info('Sampling should end at : %s',
                            time.strftime('%c', time.localtime(now + tSampling)))
                tLoopShown = True

            # measure the time spent in sampling only :
            tFin = time.time()
            self.tSamplingOnly += tFin - tIni

            # launch callback function after each sample step :
            logger.info('calling callback ...')
            self.callbacker(it, self.variables, self)
            tIni = time.time()
        self.final_iteration = it
        logger.info('##- Sampling done, final iteration=%d -##',
                    self.final_iteration)

        try:
            bold = atomData.bold
            Q, J = bold.shape

            #BIC
            self.converror = rerror
            self.loglikelihood = loglkhd
            try:
                hrf = self.get_variable('brf').currentValue
            except KeyError:
                hrf = self.get_variable('hrf').currentValue
            if len(hrf.shape) > 1:
                M = hrf.shape[1]
            else:
                M = 1
            D = hrf.shape[0]
            p = 2 * M * J + 2 * (D - 1) + J * Q + J
            n = N * J
            self.bic = loglh + p / 2 * np.log(n)
        except AttributeError:
            pass

        # Finalizing everything :
        for v in self.variables:
            if v.finalValue is None:
                v.setFinalValue()

        for v in self.variables:
            logger.info(v.name + '-> finalizing sampling ...')
            v.finalizeSampling()
            logger.info(v.get_final_summary())

        for v in self.variables:
            logger.info(v.name + '-> cleaning observables ...')
            v.cleanObservables()

        logger.info('Finalizing overall sampling ...')

        self.finalizeSampling()
        #outputs = self.getGlobalOutputs()
        # measure time for sampling and callback :
        self.analysis_duration = time.time() - tGlobIni
        #print self.getTinyProfile()

        return

    def finalizeSampling(self):
        pass

    def getOutputs(self):
        outputs = {}
        logger.info('get output of sampled variables ...')
        for v in self.variables:
            logger.debug('get outputs of %s', v.name)
            outputs.update(v.getOutputs())

        logger.info('get output of global observables ...')
        outputs.update(self.getGlobalOutputs())

        #tp = time.time()
        d = {'parcel_size': np.array([self.dataInput.nbVoxels])}
        outputs['analysis_duration'] = xndarray(\
                                            np.array([self.analysis_duration]),
                                            axes_names=['parcel_size'],
                                            axes_domains=d)
        try:
            outputs['conv_error'] = xndarray(np.array(self.converror))
            outputs['loglikelihood'] = xndarray(np.array([self.loglikelihood]))
            outputs['bic'] = xndarray(np.array([self.bic]),
                                                axes_names = ['parcel_size'],
                                                axes_domains = d)
        except AttributeError:
            pass

        # for on, o in outputs.iteritems():
        #     #print 'on:', o
        #     yield (on,o)
        return outputs

    def getShortProfile(self):
        prof = ''
        prof += '---------------------\n'
        prof += '|| Short profile   ||\n'
        prof += '---------------------\n'
        prof += '|| Sampling done !\n'  # TODO: add option for printing report on/off
        prof += '|| time spent in sampling : '+ str(self.tSamplingOnly) + ' sec\n'
        prof += '|| time spent in sampling and callbacks : '+ \
                str(self.analysis_duration) + ' sec\n'
        prof += '|| time spent in sampling for each variable : \n'
        for iv in xrange(len(self.variables)):
            v = self.variables[iv]
            prof += '|| ' + v.name + ' -> ' + str(self.tVars[iv]) + ' sec\n'
        return prof

    def getTinyProfile(self):
        return 'Total time spent : ' + str(self.analysis_duration)

    def computeFit(self):
        raise NotImplementedError

    def getFitAxes(self):
        raise NotImplementedError

    def initGlobalObservables(self):
        pass

    def updateGlobalObservables(self):
        pass

    def saveGlobalObservables(self, it):
        if self.globalObsHistoryIts is None:
            self.globalObsHistoryIts = []
        if self.globalObsHistoryTiming is None:
            self.globalObsHistoryTiming = []

        self.globalObsHistoryIts.append(it)
        self.globalObsHistoryTiming.append(self.loop_timing)

    def getGlobalOutputs(self):
        outputs = {}
        axes_domains = {
            'time': np.arange(self.dataInput.ny) * self.dataInput.tr}
        if pyhrf.__usemode__ == pyhrf.DEVEL:
            # output of design matrix:
            dMat = np.zeros_like(self.dataInput.varX[0, :, :])
            for ic, vx in enumerate(self.dataInput.varX):
                dMat += vx * (ic + 1)

            outputs['matX'] = xndarray(dMat, axes_names=['time', 'P'],
                                       axes_domains=axes_domains,
                                       value_label='value')

            ad = axes_domains.copy()
            ad['condition'] = self.dataInput.cNames
            outputs['varX'] = xndarray(self.dataInput.varX.astype(np.int8),
                                       axes_names=['condition', 'time', 'P'],
                                       axes_domains=ad,
                                       value_label='value')
        if self.output_fit:
            try:
                fit = self.computeFit()
                if self.dataInput.varMBY.ndim == 2:
                    axes_names = ['time', 'voxel']
                else:  # multisession
                    axes_names = ['session', 'time', 'voxel']
                bold = xndarray(self.dataInput.varMBY.astype(np.float32),
                                axes_names=axes_names,
                                axes_domains=axes_domains,
                                value_label='BOLD')

                # TODO: outputs of paradigm
                # outputs of onsets, per condition:
                # get binary sequence sampled at TR
                # build a xndarray from it
                # build time axis values

                cfit = xndarray(fit.astype(np.float32),
                                axes_names=axes_names,
                                axes_domains=axes_domains,
                                value_label='BOLD')
                # if self.dataInput.simulData is not None:

                    # s = xndarray(self.dataInput.simulData.stimInduced,
                               # axes_names=axes_names,
                               # axes_domains=axes_domains,
                               # value_label='BOLD')

                    # outputs['fit'] = stack_cuboids([s,cfit], 'type',
                                                   # ['simu', 'fit'])
                # else:
                outputs['bold_fit'] = stack_cuboids([bold,cfit],
                                                    'stype', ['bold', 'fit'])

                # e = np.sqrt((fit.astype(np.float32) - \
                #             self.dataInput.varMBY.astype(np.float32))**2)
                # outputs['error'] = xndarray(e, axes_names=axes_names,
                #                            axes_domains=axes_domains,
                #                            value_label='Error')
                # outputs['rmse'] = xndarray(e.mean(0), axes_names=['voxel'],
                #                            value_label='Rmse')

            except NotImplementedError:
                print 'Compute fit not implemented !'
                pass

        return outputs

    # def initGlobalObservablesOutputs(self, outputs, nbROI):
        # if self.fit is not None:
        #fitAxes = 'iteration' + self.getFitAxes()
        #outputs['fit_history'] = None

    # def fillGlobalObservablesOutputs(self, outputs, iROI):
        # pass
        # if len(self.fitHistory) > 0:


class Trajectory:

    """ Keep track of a numpy array that is modified _inplace_ iteratively
    """

    def __init__(self, variable, axes_names, axes_domains, history_pace,
                 history_start, max_iterations, first_saved_iteration=-1):
        """
        Args:
            *variable* is a numpy array that has to be modified _inplace_ else
            the reference to it is lost.
            *axes_names* is a list of string for the axes of *variable*.
            *axes_domains* is a dict of numpy arrays for the domains of the axes.
            *history_pace* is the pace at which each value of *variable* is saved.
            *history_start* is the iteration when to start saving values of
                            *variable*
            *max_iterations* is the total maximal number of iterations
                           (for allocating memory)
            *first_saved_iteration* sets the integer value of the first
                           saved iteration. -1 is useful to mark the init
                           value which is prior to the 1st iteration (0).
        """
        self.variable = variable
        self.axes_names = axes_names
        self.axes_domains = axes_domains
        self.hist_pace = history_pace
        self.hist_start = history_start

        if history_pace > 0:
            nsamples_max = max_iterations / history_pace - history_start
        else:
            nsamples_max = 0

        if first_saved_iteration == -1:
            nsamples_max += 1  # +1 because of init

        self.history = np.zeros((nsamples_max,) + variable.shape,
                                dtype=variable.dtype)

        self.sample_count = 0
        self.saved_iterations = []
        if first_saved_iteration == -1:
            #-1 is initialisation.
            self.history[0] = self.variable[:]
            self.saved_iterations.append(-1)
            self.sample_count = 1

    def record(self, iteration):
        """
        Increment the history saving.
        """
        if self.hist_pace > 0 and iteration >= self.hist_start and \
                (iteration % self.hist_pace) == 0:
            self.history[self.sample_count] = self.variable[:]
            self.saved_iterations.append(iteration)
            self.sample_count += 1

    def get_last(self):
        """ Return the last saved element """
        return self.history[self.sample_count - 1]

    def to_cuboid(self):
        """ Pack the current trajectory in a xndarray
        """

        if self.axes_names is not None:
            an = ['iteration'] + self.axes_names
        else:
            an = ['iteration'] + \
                ['axis_%02d' % i for i in xrange(self.variable.ndim)]

        if self.axes_domains is not None:
            ad = self.axes_domains.copy()
        else:
            ad = {}
        ad['iteration'] = np.array(self.saved_iterations, dtype=int)
        c = xndarray(self.history, axes_names=an, axes_domains=ad)
        return c


class GibbsSamplerVariable:

    # TODO: make GibbsSamplerVariable be XMLParamDrivenClass
    # to factorize common parametrisation

    def __init__(self, name, valIni=None, trueVal=None, sampleFlag=1,
                 useTrueValue=False, axes_names=None, axes_domains=None,
                 value_label='value'):
        """
        #TODO : comment


        """
        self.axes_domains = {} if axes_domains is None else axes_domains
        self.axes_names = axes_names
        logger.info('Init of GibbsSamplerVariable %s with axes: %s', name,
                    str(axes_names))
        self.value_label = value_label
        self.useTrueValue = useTrueValue
        self.name = name

        if valIni is not None and not isinstance(valIni, np.ndarray):
            raise Exception('Init value of variable %s should be a numpy array '
                            '(if scalar variable then it should encapsulated in'
                            'an array)' % self.name)
        if trueVal is not None and not isinstance(trueVal, np.ndarray):
            raise Exception('true value of variable %s should be a numpy array '
                            '(if scalar variable then it should encapsulated in'
                            'an array)' % self.name)

        if self.useTrueValue:
            self.currentValue = trueVal
        else:
            self.currentValue = valIni  # if None -> must be
            # generated later

        self.trueValue = trueVal  # should only be defined with linkToData (?)
        self.sampleFlag = sampleFlag
        self.sampleNext = self.chooseSampleNext(sampleFlag)
        self.finalValue = None

        self.smplHistory = None
        self.smplHistoryIts = []
        self.meanHistory = None
        self.errorHistory = None
        self.obsHistoryIts = []

        # Used to save history of samples:
        self.tracked_quantities = {}

    def chooseSampleNext(self, flag):
        if flag:
            return self.sampleNextInternal
        else:
            return self.sampleNextAlt

    def get_variable(self, label):
        """
        Return a sibling GibbsSamplerVariable
        """
        return self.samplerEngine.get_variable(label)

    def __setstate__(self, d):
        d['sampleNext'] = self.chooseSampleNext(d['sampleFlag'])
        self.__dict__ = d

    def __getstate__(self):  # use for compatibilty with pickles which doesn't
                            # support instance variable methods
        # copy the __dict__ so that further changes
        # do not affect the current instance
        d = dict(self.__dict__)
        # remove the closure that cannot be pickled
        if d.has_key('sampleNext'):
            del d['sampleNext']
        # return state to be pickled
        return d

    def get_summary(self):
        s = self.name + ' summary:'
        s += '  sample flag:' + ['Off', 'On'][self.sampleFlag]
        s += '  use true value:' + str(self.useTrueValue)
        return s

    def get_string_value(self, v):
        if v.size == 1:
            return '%1.4f' % v[0]
        if self.axes_names is not None and 'condition' == self.axes_names[0]:
            cNames = self.dataInput.cNames
            if v.ndim == 1:
                return get_2Dtable_string(v, cNames, ['Value'])
            else:
                # print 'cNames:', cNames
                # print 'v.shape:', v.shape
                v = v[:len(cNames), :]
                return get_2Dtable_string(v.reshape(v.shape[0], 1, -1),
                                          cNames, ['Value'])
        else:
            return array_summary(v)

    def get_final_summary(self):
        s = self.name + ' sampling report: \n'
        sv = self.get_string_value(self.get_final_value())
        if '\n' in sv:
            s += ' - final value:\n' + sv
        else:
            s += ' - final value: ' + sv + '\n'
        if self.trueValue is not None:
            # TODO: handle condition matching
            self.trueValue = np.array(self.trueValue)
            sv = self.get_string_value(self.trueValue)
            if '\n' in sv:
                s += ' - true value:\n' + sv
            else:
                s += ' - true value: ' + sv + '\n'
            if self.trueValue.shape == self.finalValue.shape:
                err = abs(self.trueValue - self.finalValue)
                sv = self.get_string_value(err)
                if '\n' in sv:
                    s += ' - error:\n' + sv
                else:
                    s += ' - error: ' + sv + '\n'
        return s

    def _track_quantity(self, q, name, axes_names, axes_domains,
                        history_pace, hist_start):
        if not self.tracked_quantities.has_key(name):
            max_its = self.samplerEngine.nbIterations
            trajectory = Trajectory(q, axes_names, axes_domains,
                                    history_pace, hist_start, max_its)
            self.tracked_quantities[name] = trajectory
        else:
            raise Exception('Quantity %s already tracked' % name)

    def track_sampled_quantity(self, q, name, axes_names=None, axes_domains=None,
                               history_pace=None):
        if history_pace is None:
            history_pace = self.samplerEngine.smplHistoryPace

        self._track_quantity(q, name, axes_names, axes_domains,
                             history_pace, hist_start=0)

    def track_obs_quantity(self, q, name, axes_names=None, axes_domains=None,
                           history_pace=None):

        if history_pace is None:
            history_pace = self.samplerEngine.obsHistoryPace

        burnin = self.samplerEngine.nbSweeps
        self._track_quantity(q, name, axes_domains, axes_domains,
                             history_pace, hist_start=burnin)

    def record_trajectories(self, it):
        for q in self.tracked_quantities.values():
            q.record(it)

    def initObservables(self):

        if not np.isscalar(self.currentValue):
            self.cumul = np.zeros(self.currentValue.shape, dtype=np.float64)
            #self.cumul2 = np.zeros(self.currentValue.shape, dtype=np.float64)
            self.cumul3 = np.zeros(self.currentValue.shape, dtype=np.float64)
        else:
            self.cumul = 0.0
            #self.cumul2 = 0.0
            self.cumul3 = 0.0

        self.nbItObservables = 0

    def updateObsersables(self):
        self.nbItObservables += 1
        logger.debug('Generic update Observables for var %s, it=%d ...',
                     self.name, self.nbItObservables)
        logger.debug('CurrentValue:')
        logger.debug(self.currentValue)

        self.cumul += self.currentValue
        #self.cumul2 += self.currentValue**2

        logger.debug('Cumul:')
        logger.debug(self.cumul)

        self.mean = self.cumul / self.nbItObservables

        # Another Computing of error to avoid negative value when cumul is < 1
        self.cumul3 += (self.currentValue - self.mean) ** 2
        logger.debug('Cumul3:')
        logger.debug(self.cumul3)

        logger.debug('Mean')
        logger.debug(self.mean)

        if self.nbItObservables < 2:
            self.error = np.zeros_like(self.cumul3) + 1e-6
        else:
            self.error = self.cumul3 / self.nbItObservables

        tol = 1e-10
        neg_close_to_zero = np.where(np.bitwise_and(self.error < 0,
                                                    np.abs(self.error) < tol))
        self.error[neg_close_to_zero] = tol

        logger.debug('Error:')
        logger.debug(self.error)

        if (self.error < 0.).any():
            raise Exception('neg error on variable %s' % self.name)

    def saveObservables(self, it):

        self.obsHistoryIts.append(it)
        if self.meanHistory is not None:
            self.meanHistory = np.concatenate((self.meanHistory,
                                               [self.mean]))
        else:
            self.meanHistory = np.array([self.mean.copy()])

        if self.errorHistory is not None:
            self.errorHistory = np.concatenate((self.errorHistory,
                                                [self.error]))
        else:
            self.errorHistory = np.array([self.error.copy()])

    def saveCurrentValue(self, it):
        self.smplHistoryIts.append(it)
        if self.smplHistory is not None:
            self.smplHistory = np.concatenate((self.smplHistory,
                                               [self.currentValue]))
        else:
            self.smplHistory = np.array([self.currentValue.copy()])

    def roiMapped(self):
        logger.debug('roiMapped ?')
        logger.debug(' -> self.axes_names : %s', str(self.axes_names))
        return False if (self.axes_names == None) else ('voxel' in self.axes_names)

    def manageMappingInit(self, shape, axes_names):
        tans = self.dataInput.voxelMapping.getTargetAxesNames()
        i = axes_names.index('voxel')
        axes_names = axes_names[:i] + tans + axes_names[i + 1:]
        shape = shape[:i] + self.dataInput.finalShape + shape[i + 1:]
        logger.debug('manageMappingInit returns :')
        logger.debug(' -> sh: %s, axes_names: %s', str(shape), str(axes_names))
        return shape, axes_names

    def getOutputs(self):

        # Backward compatibilty with older results
        if hasattr(self, 'axesNames'):
            self.axes_names = self.axesNames
        if hasattr(self, 'axesDomains'):
            self.axes_domains = self.axesDomains
        if hasattr(self, 'valueLabel'):
            self.value_label = self.valueLabel

        outputs = {}
        if self.axes_names is None:
            # print ' "%s" -> no axes_names defined' %self.name
            sh = (1,) if np.isscalar(
                self.finalValue) else self.finalValue.shape
            #an = ['axis%d'%i for i in xrange(self.finalValue.ndim)]
            an = ['axis%d' % i for i in xrange(len(sh))]
        else:
            an = self.axes_names

        if self.meanHistory is not None:
            outName = self.name + '_pm_history'
            if hasattr(self, 'obsHistoryIts'):
                axes_domains = {'iteration': self.obsHistoryIts}
            else:
                axes_domains = {}
            axes_domains.update(self.axes_domains)

            axes_names = ['iteration'] + an
            outputs[outName] = xndarray(self.meanHistory,
                                        axes_names=axes_names,
                                        axes_domains=axes_domains,
                                        value_label=self.value_label)

        if hasattr(self, 'smplHistory') and self.smplHistory is not None:
            axes_names = ['iteration'] + an
            outName = self.name + '_smpl_history'
            if hasattr(self, 'smplHistoryIts'):
                axes_domains = {'iteration': self.smplHistoryIts}
            else:
                axes_domains = {}
            axes_domains.update(self.axes_domains)
            outputs[outName] = xndarray(self.smplHistory,
                                        axes_names=axes_names,
                                        axes_domains=axes_domains,
                                        value_label=self.value_label)

            if hasattr(self, 'autocorrelation'):
                outName = self.name + '_smpl_autocorr'
                axes_names = ['lag'] + an
                outputs[outName] = xndarray(self.autocorrelation,
                                            axes_names=axes_names,
                                            axes_domains=self.axes_domains,
                                            value_label='acorr')

                outName = self.name + '_smpl_autocorr_test'
                outputs[outName] = xndarray(self.autocorrelation_test,
                                            axes_names=axes_names,
                                            axes_domains=self.axes_domains,
                                            value_label='acorr')

                outName = self.name + '_smpl_autocorr_pval'
                outputs[outName] = xndarray(self.autocorrelation_pvalue,
                                            axes_names=axes_names,
                                            axes_domains=self.axes_domains,
                                            value_label='pvalue')

                outName = self.name + '_smpl_autocorr_thresh'
                outputs[outName] = xndarray(np.array([self.autocorrelation_thresh]),
                                            value_label='acorr')

            if hasattr(self, 'median'):
                outName = self.name + '_post_median'
                outputs[outName] = xndarray(self.median,
                                            axes_names=self.axes_names,
                                            axes_domains=self.axes_domains,
                                            value_label='median')

        logger.info('%s final value:', self.name)
        logger.info(self.finalValue)
        if 1 and hasattr(self, 'error'):
            err = self.error ** .5
        else:
            err = None

        c = xndarray(self.get_final_value().astype(np.float32),
                     axes_names=self.axes_names,
                     axes_domains=self.axes_domains,
                     value_label=self.value_label)

        if self.trueValue is not None:
            c_true = xndarray(np.array(self.get_true_value()),
                              axes_names=self.axes_names,
                              axes_domains=self.axes_domains,
                              value_label=self.value_label)

            c = stack_cuboids([c, c_true], axis='type', domain=['estim', 'true'],
                              axis_pos='last')

        outputs[self.name + '_pm'] = c

        if ((err is not None) or ((err.size == 1) and (err != 0))):
            c_err = xndarray(self.error.astype(np.float32),
                             axes_names=self.axes_names,
                             axes_domains=self.axes_domains,
                             value_label=self.value_label)
            # c = stack_cuboids([c,c_err], axis='error', domain=['value','std'],
            #                   axis_pos='last')
            outputs[self.name + '_mcmc_var'] = c_err

        if hasattr(self, 'tracked_quantities'):
            for qname, q in self.tracked_quantities.iteritems():
                outputs[qname] = q.to_cuboid()

        if len(self.report_check_ft_val) > 0:
            r = self.report_check_ft_val
            outputs[self.name + '_abs_err'] = xndarray(r['abs_error'],
                                                       axes_names=self.axes_names,
                                                       axes_domains=self.axes_domains)

            outputs[self.name + '_rel_err'] = xndarray(r['rel_error'],
                                                       axes_names=self.axes_names,
                                                       axes_domains=self.axes_domains)
            on = self.name + '_inaccuracies'
            an = r['accuracy'][0]
            ad = {}
            if an is not None:
                ad = dict((a, self.axes_domains[a])
                          for a in an if self.axes_domains.has_key(a))
            inacc = np.bitwise_not(r['accuracy'][1]).astype(np.int8)
            outputs[on] = xndarray(inacc, axes_names=an, axes_domains=ad)

        return outputs

    def manageMapping(self, cuboid):
        pass

    def cleanObservables(self):
        del self.cumul3
        del self.cumul
        del self.currentValue

    def registerNbIterations(self, nbIt):
        pass

    def setSamplerEngine(self, sampler):
        # TODO : comment
        self.samplerEngine = sampler

    def linkToData(self,):
        raise NotImplementedError()

    def checkAndSetInitValue(self, variables):
        if self.currentValue is None:
            print 'Error - ', self.name, ' - initial value not set !'

    def samplingWarmUp(self, variables):
        """
        Called before the launch of the main sampling loop by the sampler
        engine. Should be overriden and perform precalculations.
        """
        pass

    def finalizeSampling(self):
        #from scikits.talkbox.tools.correlations import  acorr
        from pyhrf.stats import acorr
        if 0 and self.smplHistory is not None:
            logger.info('Compute autocorrelation of %s samples, shape=%s',
                        self.name, str(self.smplHistory.shape))
            trajectory = self.smplHistory[self.samplerEngine.nbSweeps::2]
            self.autocorrelation = acorr(trajectory)
            sn = trajectory.shape[0] ** .5
            t95 = 1.959963984540054 / sn
            self.autocorrelation_test = np.zeros(self.autocorrelation.shape,
                                                 dtype=np.int32)
            self.autocorrelation_test[np.where(self.autocorrelation > t95)] = 1
            self.autocorrelation_test[
                np.where(self.autocorrelation < -t95)] = -1

            self.autocorrelation_thresh = t95

            from scipy.stats import norm
            self.autocorrelation_pvalue = np.zeros(self.autocorrelation.shape,
                                                   dtype=np.float32)
            m_pos = np.where(self.autocorrelation > 0)
            if len(m_pos[0]) > 0:
                ac_pos = self.autocorrelation[m_pos]
                self.autocorrelation_pvalue[m_pos] = norm.sf(ac_pos * sn)

            m_neg = np.where(self.autocorrelation < 0)
            if len(m_neg[0]) > 0:
                ac_neg = self.autocorrelation[m_neg]
                self.autocorrelation_pvalue[m_neg] = norm.cdf(ac_neg * sn)

            logger.info('Compute posterior median for %s ', self.name)
            self.median = np.median(self.smplHistory, axis=0)

        self.check_final_value()

    def check_final_value(self):
        report = {}
        if self.samplerEngine.check_ftval is not None:
            if self.trueValue is None:
                logger.info('Warning: no true val to check against for %s',
                            self.name)
            elif self.sampleFlag:
                fv = self.get_final_value()
                tv = self.get_true_value()
                rtol = 0.1      # Relative tolerance value: 10%
                # Absolute tolerance value. TODO: dependency to parameter
                atol = 0.1

                # report['true_value'] = tv
                # report['final_value'] = fv
                abs_error = np.abs(tv - fv)
                report['abs_error'] = abs_error
                rel_error = abs_error / np.maximum(np.abs(tv), np.abs(fv))
                report['rel_error'] = rel_error

                report['accuracy'] = self.get_accuracy(abs_error, rel_error,
                                                       fv, tv, atol, rtol)
                is_accurate = report['accuracy'][1].all()
                logger.info('Fit error for %s: aerr=%f, rerr=%f, is_accurate=%s',
                            self.name, abs_error.mean(), rel_error.mean(),
                            is_accurate)
                if not is_accurate:
                    m = "Final value of %s is not close to " \
                        "true value.\n -> aerror: %s\n -> rerror: %s\n" \
                        " Final value:\n %s\n True value:\n %s\n" \
                        % (self.name, array_summary(report['abs_error']),
                           array_summary(report['rel_error']),
                           str(fv), str(tv))
                    if self.samplerEngine.check_ftval == 'raise':
                        raise Exception(m)
                    elif self.samplerEngine.check_ftval == 'print':
                        print '\n'.join(['!! ' + s for s in m.split('\n')])

        self.report_check_ft_val = report

    def get_accuracy(self, abs_error, rel_error, fv, tv, atol, rtol):
        """ Return the accuray of the estimate *fv*, compared to the true
        value *tv*

        Output:
            axes_names (list of str), accuracy (numpy array of booleans)
        """
        # same criterion as np.allclose:
        acc = abs_error <= (atol + rtol * np.maximum(np.abs(tv),
                                                     np.abs(fv)))
        return self.axes_names, acc

    def get_final_value(self):
        return self.finalValue

    def get_true_value(self):
        return self.trueValue

    def setFinalValue(self):
        self.finalValue = self.getMean()
        # if self.name=='nrl_by_session':
        # print 'self.cumul:', self.cumul[2,2,15]

    def sampleNextAlt(self, variables):
        """
        Define the behaviour of the variable at each sampling step when its
        sampling is not activated.
        """
        # print self.name, ' skip sampling ...'
        pass

    def sampleNextInternal(self, variables):
        """
        Define the behaviour of the variable at each sampling step when its
        sampling is not activated. Must be overriden in child classes.
        """
        raise NotImplementedError()

    def getMean(self):  # , itStart=None, itEnd=None, pace=1):
        """
        Wip ...
        Compute mean over MCMC iterations within the window defined by itStart,
        itEnd and pace. By default itStart is set to 'nbSweeps' and itEnd to
        the last iteration.
        """
        # print 'seeelf:', self, self.mean
        return self.mean
# if itStart == None :
##            itStart = self.samplerEngine.nbSweeps
# if itEnd == None :
##            itEnd = len(self.valHistory)-1
# print 'getMean '
# print 'itStart = ', itStart
# print 'itEnd = ', itEnd
# print 'range = ', arange(itStart, itEnd+1, pace)
# return self.valHistory[arange(itStart, itEnd+1, pace)].mean(0)

    def getMeanHistory(self):  # , itStart=None, histPace=1):
        if self.meanHistory is None:
            return (None, None)
        else:
            return (self.obsHistoryIts, self.meanHistory)

# if itStart == None :
##            itStart = self.samplerEngine.nbSweeps

##        itMax = len(self.valHistory)
##        meanHistory = [self.getMean(itStart, itStart+1)]
# for ite in xrange(itStart+1, itMax, histPace):
##            m = self.getMean(itStart, ite)
# if m != None:
##                meanHistory = concatenate( (meanHistory,[m]) )

##        itAxis = range(itStart, itMax, histPace)
# return (itAxis,meanHistory)

    # TODO idem as mean with variance ...


class GSDefaultCallbackHandler(xmlio.XmlInitable):
    """
    Class handling default action after Gibbs Sampling step (nothing). Should be inherited to define more specialized actions (such as plotting and reporting).

    """

    def __init__(self):
        xmlio.XmlInitable.__init__(self)

    def callback(self, it, vars, samplerEngine):
        """
        Execute action to be made after each Gibbs Sampling step (here : nothing). Should be overriden to define more specialized actions.
        @param it: the number of iterations elapsed in the current sampling process.
        @param samplerEngine: the parent gibbs sampler object
        @param vars: variables envolved in the sampling process (list of C{GibbsSamplerVariable} whose index is defined in L{samplerEngine})
        """
        pass

    def __call__(self, it, v, e):
        self.callback(it, v, e)


# class BayesFactorCallback(xmlio.XMLParamDrivenClass):

    # defaultParameters = {
        #'monParametre' : 458.,
        #}

    # def __init__(self, parameters=None, xmlHandler=xmlio.TypedXMLHandler(),
        # xmlLabel=None, xmlComment=None):
        # xmlio.XMLParamDrivenClass.__init__(self, parameters, xmlHandler,
        # xmlLabel, xmlComment)

        # Recuperation des parametres:
        #self.monParam = self.parameters['monParametre']
        # print 'BayesFactorCallback.__init__ :',
        # print 'self.monParam :', self.monParam

    # def callback(self, it, vars, samplerEngine):

        #samplerEngine.invLike = 1.
        #LVformer = 1.
        # N = samplerEngine.dataInput.varMBY.shape[0]       # N is the number of rows of P or H or yj
        #M = samplerEngine.dataInput.nbConditions
        # Q = samplerEngine.dataInput.colP       # Q is the number of columns of P
        #delta = samplerEngine.dataInput.delta
        #shrf = samplerEngine.get_variable('hrf')
        #snrl = samplerEngine.get_variable('nrl')
        #snoise = samplerEngine.get_variable('noise')
        # h = shrf.currentValue # shape = (nbCoeffHrf)
        # a = snrl.currentValue # shape = (nbConditions, nbVoxels)
        # y = samplerEngine.dataInput.varMBY # shape = (nbScans, nbVoxels)
        #H = shrf.varXh
        # noiseVars = snoise.currentValues # sh = (nbVoxels)
        #In = eye(N, dtype=float)

        # print 'Iteration :', it
        # if  it >= samplerEngine.nbSweeps:
        #shrf = samplerEngine.get_variable('hrf')

        # LVcurrent_value = LVformer*(0.5*(N-Q-M)-2)!*(0.5
        #samplerEngine.invLike = samplerEngine.invLike*(it-1)/it + LVcurrent_value/it
        #samplerEngine.Like = 1/samplerEngine.Like
        #LVformer = LVcurrent_value

        # print ' -> hrf value:', shrf.currentValue
        # print ' -> nrl value:', snrl.currentValue

        # print 'Harmonic mean estimate of the integrated likelihood...'

    # def finalize(self):
        # pass


class GSPrintCallbackHandler(GSDefaultCallbackHandler):
    """
    Class defining behaviour after each Gibbs Sampling step : printing reports to stdout.

    """

    def __init__(self, pace):
        self.pace = pace

    def callback(self, it, variables, samplerEngine):
        if not it % self.pace:
            print 'Iteration : ', it
            for v in variables:
                print v.name
                print v.currentValue
                print ' '
            print ' '
