"""Simulator backends for NeuronUnit models"""

import sys
import os
import platform
import re
import copy
import tempfile
import pickle
import importlib
import shelve
import subprocess

import neuronunit.capabilities as cap
from quantities import ms, mV, nA
from pyneuroml import pynml
from quantities import ms, mV
from neo.core import AnalogSignal
import neuronunit.capabilities.spike_functions as sf
import sciunit
from sciunit.utils import dict_hash, import_module_from_path
try:
    import neuron
    from neuron import h
    NEURON_SUPPORT = True
except:
    NEURON_SUPPORT = False


class Backend(object):
    """Base class for simulator backends that implement simulator-specific
    details of modifying, running, and reading results from the simulation
    """
    #self.tstop = None
    def init_backend(self, *args, **kwargs):
        #self.attrs = {} if attrs is None else attrs
        self.model.unpicklable = []
        self.model.attrs = {}
        self.use_memory_cache = kwargs.get('use_memory_cache', True)
        if self.use_memory_cache:
            self.init_memory_cache()
        self.use_disk_cache = kwargs.get('use_disk_cache', False)
        if self.use_disk_cache:
            self.init_disk_cache()
        #print(2)
        self.load_model()
        
    #attrs = None

    # Name of the backend
    backend = None

    #The function (e.g. from pynml) that handles running the simulation
    f = None

    def init_cache(self):
        self.init_memory_cache()
        self.init_disk_cache()

    def init_memory_cache(self):
        self.memory_cache = {}

    def init_disk_cache(self):
        try:
            # Cleanup old disk cache files
            path = self.disk_cache_location
            os.remove(path)
        except:
            pass
        self.disk_cache_location = os.path.join(tempfile.mkdtemp(),'cache')

    def get_memory_cache(self, state):
        """Returns result in memory cache for key 'state' or None if it 
        is not found"""
        self._results = self.memory_cache.get(state)
        return self._results

    def get_disk_cache(self, state):
        """Returns result in disk cache for key 'state' or None if it 
        is not found"""
        if not getattr(self,'disk_cache_location',False):
            self.init_disk_cache()
        disk_cache = shelve.open(self.disk_cache_location)
        self._results = disk_cache.get(state)
        disk_cache.close()
        return self._results

    def set_memory_cache(self, results, state=None):
        """Stores result in memory cache with key 
        corresponding to model state"""
        state = self.model.state if state is None else state
        self.memory_cache[state] = results

    def set_disk_cache(self, results, state=None):
        """Stores result in disk cache with key 
        corresponding to model state"""
        if not getattr(self,'disk_cache_location',False):
            self.init_disk_cache()
        disk_cache = shelve.open(self.disk_cache_location)
        state = self.model.state if state is None else state
        disk_cache[state] = results
        disk_cache.close()

    def set_attrs(self, **attrs):
        """Set model attributes, e.g. input resistance of a cell"""
        #If the key is in the dictionary, it updates the key with the new value.
        self.model.attrs.update(attrs)
        pass

    def set_run_params(self, **params):
        """Set run-time parameters, e.g. the somatic current to inject"""
        self.model.run_params.update(params)
        self.check_run_params()
        pass

    def check_run_params(self):
        """Check to see if the run parameters are reasonable for this model
        class.  Raise a sciunit.BadParameterValueError if any of them are not.
        """
        pass

    def load_model(self):
        """Load the model into memory"""
        pass

    def local_run(self):
        """Checks for cached results in memory and on disk, then runs the model
        if needed"""
        state = self.model.state
        if self.use_memory_cache and self.get_memory_cache(state):
            return self._results
        if self.use_disk_cache and self.get_disk_cache(state):
            return self._results
        results = self._local_run()
        if self.use_memory_cache:
            self.set_memory_cache(results, state)
        if self.use_disk_cache:
            self.set_disk_cache(results, state)
        return results

    def _local_run(self):
        """Runs the model via the backend"""
        raise NotImplementedError("Each backend must implement '_local_run'")

    def save_results(self, path='.'):
        with open(path,'wb') as f:
            pickle.dump(self.results,f)


class BackendException(Exception):
    pass


class jNeuroMLBackend(Backend):
    """Used for simulation with jNeuroML, a reference simulator for NeuroML"""

    backend = 'jNeuroML'

    def init_backend(self, *args, **kwargs):
        self.model.create_lems_file(self.model.name)
        super(jNeuroMLBackend,self).init_backend(*args, **kwargs)

    def set_attrs(self, **attrs):
        self.model.attrs.update(attrs)
        self.set_lems_attrs(attrs)

    def set_run_params(self, **params):
        super(jNeuroMLBackend,self).set_run_params(**params)
        self.model.set_lems_run_params()

    def inject_square_current(self, current):
        self.set_run_params(injected_square_current=current)

    def _local_run(self):
        f = pynml.run_lems_with_jneuroml
        self.exec_in_dir = tempfile.mkdtemp()
        results = f(self.model.lems_file_path, 
                    include=[os.path.dirname(self.model.orig_lems_file_path)],
                    skip_run=self.model.skip_run,
                    nogui=self.model.run_params['nogui'],
                    load_saved_data=True, plot=False,
                    exec_in_dir=self.exec_in_dir,
                    verbose=self.model.run_params['v'])
        return results


class NEURONBackend(Backend):
    """Used for simulation with NEURON, a popular simulator
    http://www.neuron.yale.edu/neuron/
    Units used by NEURON are sometimes different to quantities/neo
    (note nA versus pA)
    http://neurosimlab.org/ramcd/pyhelp/modelspec/programmatic/mechanisms/mech.html#IClamp
    NEURON's units:
    del -- ms
    dur -- ms
    amp -- nA
    i -- nA
    """

    def init_backend(self, attrs=None):    
        if not NEURON_SUPPORT:
            raise BackendException("The neuron module was not successfully imported")
        self.neuron = None
        self.model_path = None
        self.h = h
        #Should check if MPI parallel neuron is supported and invoked.
        self.h.load_file("stdlib.hoc")
        self.h.load_file("stdgui.hoc")
        self.lookup = {}
        #print(1)
        super(NEURONBackend,self).init_backend()
        self.model.unpicklable += ['h','ns','_backend']
    
    backend = 'NEURON'

    def reset_neuron(self, neuronVar):
        """Sets the NEURON h variable"""

        self.h = neuronVar.h
        self.neuron = neuronVar

    def set_stop_time(self, stopTime = 1600*ms):
        """Sets the simulation duration
        stopTimeMs: duration in milliseconds
        """

        tstop = stopTime
        tstop.units = ms
        self.h.tstop = float(tstop)

    def set_time_step(self, integrationTimeStep = 1/128.0 * ms):
        """Sets the simulation itegration fixed time step
        integrationTimeStepMs: time step in milliseconds.
        Powers of two preferred. Defaults to 1/128.0
        """

        dt = integrationTimeStep
        dt.units = ms
        self.h.dt = self.fixedTimeStep = float(dt)

    def set_tolerance(self, tolerance = 0.001):
        """Sets the variable time step integration method absolute tolerance.
        tolerance: absolute tolerance value
        """

        self.h.cvode.atol(tolerance)
	# Unsure if these lines actually work:
        # self.cvode = self.h.CVode()
        # self.cvode.atol(tolerance)

    def set_integration_method(self, method = "fixed"):
        """Sets the simulation itegration method
        method: either "fixed" or "variable". Defaults to fixed.
        cvode is used when "variable" """

	# This line is compatible with the above cvodes
	# statements.
        self.h.cvode.active(1 if method == "variable" else 0)

        try:
            assert self.cvode.active()
        except:
            self.cvode = self.h.CVode()
            self.cvode.active(1 if method == "variable" else 0)

    def get_membrane_potential(self):
        """Must return a neo.core.AnalogSignal.
        And must destroy the hoc vectors that comprise it.
        """

        if self.h.cvode.active() == 0:
            dt = float(copy.copy(self.h.dt))
            fixed_signal = copy.copy(self.vVector.to_python())
        else:
            dt = float(copy.copy(self.fixedTimeStep))
            fixed_signal =copy.copy(self.get_variable_step_analog_signal())

        self.h.dt = dt
        self.fixedTimeStep = float(1.0/dt)
        return AnalogSignal(fixed_signal,
                            units = mV,
                            sampling_period = dt * ms)

    def get_variable_step_analog_signal(self):
        """Converts variable dt array values to fixed
        dt array by using linear interpolation"""

        # Fixed dt potential
        fPots = []
        fDt = self.fixedTimeStep
        # Variable dt potential
        vPots = self.vVector.to_python()
        # Variable dt times
        vTimes = self.tVector.to_python()
        duration = vTimes[len(vTimes)-1]
        # Fixed and Variable dt times
        fTime = vTime = vTimes[0]
        # Index of variable dt time array
        vIndex = 0
        # Advance the fixed dt position
        while fTime <= duration:

            # If v and f times are exact, no interpolation needed
            if fTime == vTime:
                fPots.append(vPots[vIndex])

            # Interpolate between the two nearest vdt times
            else:

                # Increment vdt time until it surpases the fdt time
                while fTime > vTime and vIndex < len(vTimes):
                    vIndex += 1
                    vTime = vTimes[vIndex]

                # Once surpassed, use the new vdt time and t-1 for interpolation
                vIndexMinus1 = max(0, vIndex-1)
                vTimeMinus1 = vTimes[vIndexMinus1]

                fPot = self.linearInterpolate(vTimeMinus1, vTime, \
                                          vPots[vIndexMinus1], vPots[vIndex], \
                                          fTime)

                fPots.append(fPot)

            # Go to the next fdt time step
            fTime += fDt

        return fPots

    def linearInterpolate(self, tStart, tEnd, vStart, vEnd, tTarget):
        tRange = float(tEnd - tStart)
        tFractionAlong = (tTarget - tStart)/tRange
        vRange = vEnd - vStart
        vTarget = vRange*tFractionAlong + vStart

        return vTarget

    def load(self):
        nrn_path = os.path.splitext(self.model.orig_lems_file_path)[0]+'_nrn.py'
        #import neuron # This is necessary to avoid a segmentation fault
        nrn = import_module_from_path(nrn_path)
        #print(4)
        self.reset_neuron(nrn.neuron)
        #print(5)#make sure mechanisms are loaded
        modeldirname = os.path.dirname(self.model.orig_lems_file_path)
        #if load_mechanisms:
        #    self.neuron.load_mechanisms(modeldirname)
        self.set_stop_time(1600*ms)
        self.h.tstop
        #print(6)
        #curr_dir = os.getcwd()
        # Set to the directory with the module because this will also have
        # the compiled files that NEURON needs to run the simulatuon.   
        #os.chdir(self.exec_in_dir)
        #print(os.getcwd())
        self.ns = nrn.NeuronSimulation(self.h.tstop, dt=0.0025)
        #os.chdir(curr_dir)
        #print(7)

    def load_mechanisms(self):
        neuron.load_mechanisms(self.neuron_model_dir)

    def load_model(self, verbose=True):
        """
        Inputs: NEURONBackend instance object
        Outputs: nothing mutates input object.
        Take a declarative model description, and convert it
        into an implementation, stored in a pyhoc file.
        import the pyhoc file thus dragging the neuron variables
        into memory/python name space.
        Since this only happens once outside of the optimization
        loop its a tolerable performance hit.
        """
        
        #Create a pyhoc file using jneuroml to convert from NeuroML to pyhoc.
        #import the contents of the file into the current names space.
        
        
        #The code block below does not actually function:
        #architecture = platform.machine()
        base_name = os.path.splitext(self.model.orig_lems_file_path)[0]
        NEURON_file_path ='{0}_nrn.py'.format(base_name)

        self.neuron_model_dir = os.path.dirname(self.model.orig_lems_file_path)
        if not os.path.exists(NEURON_file_path):
            #print(2.5)
            # Generate NEURON scripts.  
            pynml.run_lems_with_jneuroml_neuron(self.model.orig_lems_file_path,
                              skip_run=False,
                              nogui=True,
                              load_saved_data=False,
                              only_generate_scripts=True,
                              plot=False,
                              show_plot_already=False,
                              exec_in_dir = self.neuron_model_dir,
                              verbose=verbose,
                              exit_on_fail = True)
            subprocess.run(["cd %s; nrnivmodl" % self.neuron_model_dir],shell=True)
            self.load_mechanisms()
        elif os.path.realpath(os.getcwd()) != os.path.realpath(self.neuron_model_dir):
            # Load mechanisms unless they've already been loaded
            self.load_mechanisms()

        #print(3)
        self.load()

        #Although the above approach successfuly instantiates a LEMS/neuroml model in pyhoc
        #the resulting hoc variables for current source and cell name are idiosyncratic (not generic).
        #The resulting idiosyncracies makes it hard not have a hard coded approach make non hard coded, and generalizable code.
        #work around involves predicting the hoc variable names from pyneuroml LEMS file that was used to generate them.
        more_attributes = pynml.read_lems_file(self.model.orig_lems_file_path)
        #print("Components are %s" % more_attributes.components)
        for i in more_attributes.components:
            #This code strips out simulation parameters from the xml tree also such as duration.
            #Strip out values from something a bit like an xml tree.
            if str('pulseGenerator') in i.type:
                self.current_src_name = i.id
            if str('Cell') in i.type:
                self.cell_name = i.id
        more_attributes = None #force garbage collection of more_attributes, its not needed anymore.
        return self

    #def set_attrs(self,**attrs):
    #    '''
    #    set model attributes in HOC memory space.
    #    over riding a stub of the parent class.
    #    '''

    def set_attrs(self, **attrs):
        self.model.attrs.update(attrs)
        #self.set_lems_attrs(attrs)

        #def set_attrs(self, **attrs):                                                                               
        #self.attrs.update(attrs)                                                                                
        #self.set_lems_attrs(attrs)                                                                                    
                                                                   

        #super(NEURONBackend,self).set_attrs(attrs)
        assert type(self.model.attrs) is not type(None)
        for h_key,h_value in attrs.items():
            self.h('m_RS_RS_pop[0].{0} = {1}'.format(h_key,h_value))
            self.h('m_{0}_{1}_pop[0].{2} = {3}'.format(self.cell_name,self.cell_name,h_key,h_value))
            self.h('psection()')


        # Below are experimental rig recording parameters.
        # These can possibly go in a seperate method.

        self.h(' { v_time = new Vector() } ')
        self.h(' { v_time.record(&t) } ')
        self.h(' { v_v_of0 = new Vector() } ')
        self.h(' { v_v_of0.record(&RS_pop[0].v(0.5)) } ')
        self.h(' { v_u_of0 = new Vector() } ')
        self.h(' { v_u_of0.record(&m_RS_RS_pop[0].u) } ')

        self.tVector = self.h.v_time
        self.vVector = self.h.v_v_of0

        return self

    def inject_square_current(self, current):
        '''
        Inputs: current : a dictionary
         like:
        {'amplitude':-10.0*pq.pA,
         'delay':100*pq.ms,
         'duration':500*pq.ms}}
        where 'pq' is the quantities package
        #purge the HOC space, this is necessary because model recycling between runs is bad
        #models when models are not re-initialized properly, as its common for a recycled model
        #to retain charge from stimulation in previous simulations.
        #Although the complete purge is and reinit is computationally expensive,
        #and a more minimal purge is probably sufficient.
        '''
        self.h = None
        self.neuron = None
        import neuron
        self.reset_neuron(neuron)
        self.set_attrs(**self.attrs)

        c = copy.copy(current)
        if 'injected_square_current' in c.keys():
            c = current['injected_square_current']

        c['delay'] = re.sub('\ ms$', '', str(c['delay']))
        c['duration'] = re.sub('\ ms$', '', str(c['duration']))
        c['amplitude'] = re.sub('\ pA$', '', str(c['amplitude']))
        #Todo want to convert from nano to pico amps using quantities.
        amps=float(c['amplitude'])/1000.0 #This is the right scale.
        prefix = 'explicitInput_%s%s_pop0.' % (self.current_src_name,self.cell_name)
        self.h(prefix+'amplitude=%s'%amps)
        self.h(prefix+'duration=%s'%c['duration'])
        self.h(prefix+'delay=%s'%c['delay'])
        self.local_run()

    def _local_run(self):
        self.h('run()')
        results={}
        # Prepare NEURON vectors for quantities/sciunit 
        # By rescaling voltage to milli volts, and time to milli seconds.
        results['vm'] = [float(x/1000.0) for x in copy.copy(self.neuron.h.v_v_of0.to_python())]
        results['t'] = [float(x/1000.0) for x in copy.copy(self.neuron.h.v_time.to_python())]
        if 'run_number' in results.keys():
            results['run_number'] = results['run_number']+1
        else:
            results['run_number'] = 1
        return results

    def get_spike_train(self):
        import neuronunit.capabilities.spike_functions as sf
        return sf.get_spike_train(self.get_membrane_potential())

    def get_APs(self):
        import neuronunit.capabilities.spike_functions as sf
        return sf.get_spike_waveforms(self.get_membrane_potential())


class HasSegment(sciunit.Capability):
    """Model has a membrane segment of NEURON simulator"""

    def setSegment(self, section, location = 0.5):
        """Sets the target NEURON segment object
        section: NEURON Section object
        location: 0.0-1.0 value that refers to the location
        along the section length. Defaults to 0.5
        """

        self.section = section
        self.location = location

    def getSegment(self):
        """Returns the segment at the active section location"""

        return self.section(self.location)

class SingleCellModel(NEURONBackend):
    def __init__(self, \
                 neuronVar, \
                 section, \
                 loc = 0.5, \
                 name=None):
        super(SingleCellModel,self).__init__()#name=name, hVar=hVar)
        hs = HasSegment()
        hs.setSegment(section, loc)
        self.reset_neuron(neuronVar)
        self.section = section
        self.loc = loc
        self.name = name
        #section = soma
        #super(SingleCellModel,self).reset_neuron(self, neuronVar)
        # Store voltage and time values
        self.tVector = self.h.Vector()
        self.vVector = self.h.Vector()
        self.vVector.record(hs.getSegment()._ref_v)
        self.tVector.record(self.h._ref_t)

        return
