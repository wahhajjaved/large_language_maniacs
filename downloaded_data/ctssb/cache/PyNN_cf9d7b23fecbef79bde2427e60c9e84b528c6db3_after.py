# encoding: utf-8
"""
Defines a common implementation of the PyNN API.

Simulator modules are not required to use any of the code herein, provided they
provide the correct interface, but it is suggested that they use as much as is
consistent with good performance (optimisations may require overriding some of
the default definitions given here).

Exceptions:
    InvalidParameterValueError
    NonExistentParameterError
    InvalidDimensionsError
    ConnectionError
    InvalidModelError
    RoundingWarning
    NothingToWriteError
    InvalidWeightError
    NotLocalError
    RecordingError    

Utility functions and classes:
    is_listlike()
    is_number()
    is_conductance()
    check_weight()
    check_delay()
    distance()
    distances()
    next_n()
    ConstIter
    
Accessing individual neurons:
    IDMixin

Standard cells/parameter translation:
    build_translations()    
    StandardModelType
    StandardCellType
    ModelNotAvailable
    
Common API implementation/base classes:
  1. Simulation set-up and control:
    setup()
    end()
    run()
    get_time_step()
    get_current_time()
    get_min_delay()
    get_max_delay()
    rank()
    num_processes()

  2. Creating, connecting and recording from individual neurons:
    create()
    connect()
    set()
    build_record()

  3. Creating, connecting and recording from populations of neurons:
    Population
    Projection
    Connector
    
  4. Specification of synaptic plasticity:
    SynapseDynamics
    ShortTermPlasticityMechanism
    STDPMechanism
    STDPWeightDependence
    STDPTimingDependence

$Id$
"""

import types, copy, sys
import numpy
import logging
from math import *
from pyNN import random, utility
from string import Template

if not 'simulator' in locals():
    simulator = None # should be set by simulator-specific modules

DEFAULT_WEIGHT = 0.0
DEFAULT_BUFFER_SIZE = 10000

logger = logging.getLogger("PyNN")

class InvalidParameterValueError(Exception):
    """Inappropriate parameter value"""
    pass # should subclass ValueError?

class NonExistentParameterError(Exception):
    """
    Model parameter does not exist.
    """
    
    def __init__(self, parameter_name, model):
        self.parameter_name = parameter_name
        if isinstance(model, type):
            if issubclass(model, StandardModelType):
                self.model_name = model.__name__
                self.valid_parameter_names = model.default_parameters.keys()
                self.valid_parameter_names.sort()
        elif isinstance(model, basestring):
            self.model_name = model
            self.valid_parameter_names = ['unknown']
        else:
            raise Exception("When raising a NonExistentParameterError, model must be a class or a string, not a %s" % type(model))

    def __str__(self):
        return "%s (valid parameters for %s are: %s)" % (self.parameter_name,
                                                         self.model_name,
                                                         ", ".join(self.valid_parameter_names))

class InvalidDimensionsError(Exception):
    """Argument has inappropriate shape/dimensions."""
    pass

class ConnectionError(Exception):
    """Attempt to create an invalid connection or access a non-existent connection."""
    pass

class InvalidModelError(Exception):
    """Attempt to use a non-existent model type."""
    pass

class NoModelAvailableError(Exception):
    """The simulator does not implement the requested model."""
    pass

class RoundingWarning(Warning):
    """The argument has been rounded to a lower level of precision by the simulator."""
    pass

class NothingToWriteError(Exception):
    """There is no data available to write."""
    pass # subclass IOError?

class InvalidWeightError(Exception): # subclass ValueError? or InvalidParameterValueError?
    """Invalid value for the synaptic weight."""
    pass

class NotLocalError(Exception):
    """Attempt to access a cell or connection that does not exist on this node (but exists elsewhere)."""
    pass

class RecordingError(Exception): # subclass AttributeError?
    """Attempt to record a variable that does not exist for this cell type."""
    
    def __init__(self, variable, cell_type):
        self.variable = variable
        self.cell_type = cell_type
        
    def __str__(self):
        return "Cannot record %s from cell type %s" % (self.variable, self.cell_type.__class__.__name__)


# ==============================================================================
#   Utility functions and classes
# ==============================================================================

def is_listlike(obj):
    return hasattr(obj, "__len__") and not isinstance(obj, basestring)

def is_number(obj):
    return isinstance(obj, float) or isinstance(obj, int) or isinstance(obj, long) or isinstance(obj, numpy.float64)

def is_conductance(target_cell):
    """
    Returns True if the target cell uses conductance-based synapses, False if it
    uses current-based synapses, and None if the synapse-basis cannot be determined.
    """
    if hasattr(target_cell, 'local') and target_cell.local and hasattr(target_cell, 'cellclass'):
        if isinstance(target_cell.cellclass, type):
            is_conductance = target_cell.cellclass.conductance_based
        else: # where cellclass is a string, i.e. for native cell types in NEST
            is_conductance = "cond" in target_cell.cellclass
    else:
        is_conductance = None
    return is_conductance

def check_weight(weight, synapse_type, is_conductance):
    if weight is None:
        weight = DEFAULT_WEIGHT
    if is_listlike(weight):
        weight = numpy.array(weight)
        all_negative = (weight<=0).all()
        all_positive = (weight>=0).all()
        if not (all_negative or all_positive):
            raise InvalidWeightError("Weights must be either all positive or all negative")
    elif is_number(weight):
        all_positive = weight >= 0
        all_negative = weight < 0
    else:
        raise Exception("Weight must be a number or a list/array of numbers.")
    if is_conductance or synapse_type == 'excitatory':
        if not all_positive:
            raise InvalidWeightError("Weights must be positive for conductance-based and/or excitatory synapses")
    elif is_conductance==False and synapse_type == 'inhibitory':
        if not all_negative:
            raise InvalidWeightError("Weights must be negative for current-based, inhibitory synapses")
    else: # is_conductance is None. This happens if the cell does not exist on the current node.
        logger.debug("Can't check weight, conductance status unknown.")
    return weight

def check_delay(delay):
    if delay is None:
        delay = get_min_delay()
    # If the delay is too small , we have to throw an error
    if delay < get_min_delay() or delay > get_max_delay():
        raise ConnectionError("delay (%s) is out of range [%s,%s]" % (delay, get_min_delay(), get_max_delay()))
    return delay

def distance(src, tgt, mask=None, scale_factor=1.0, offset=0.0,
             periodic_boundaries=None): # may need to add an offset parameter
    """
    Return the Euclidian distance between two cells.
    `mask` allows only certain dimensions to be considered, e.g.::
      * to ignore the z-dimension, use `mask=array([0,1])`
      * to ignore y, `mask=array([0,2])`
      * to just consider z-distance, `mask=array([2])`
    `scale_factor` allows for different units in the pre- and post- position
    (the post-synaptic position is multipied by this quantity).
    """
    d = src.position - scale_factor*(tgt.position + offset)
    
    if not periodic_boundaries == None:
        d = numpy.minimum(abs(d), periodic_boundaries-abs(d))
    if mask is not None:
        d = d[mask]
    return numpy.sqrt(numpy.dot(d, d))

def distances(pre, post, mask=None, scale_factor=1.0, offset=0.0,
              periodic_boundaries=None):
    """
    Calculate the entire distance matrix at once.
    From http://projects.scipy.org/pipermail/numpy-discussion/2007-April/027203.html
    """
    # Note that `mask` is not used.
    if isinstance(pre, Population):
        x = pre.positions
    else: 
        x = pre.position
        x = x.reshape(3, 1)
    if isinstance(post, Population):
        y = post.positions
    else: 
        y = post.position
        y = y.reshape(3, 1)
    y = scale_factor*(y + offset)
    d = numpy.zeros((x.shape[1], y.shape[1]), dtype=x.dtype)
    for i in xrange(x.shape[0]):
        diff2 = abs(x[i,:,None] - y[i,:])
        if periodic_boundaries is not None:
            dims  = diff2.shape
            diff2 = diff2.flatten()
            diff2 = numpy.minimum(diff2, periodic_boundaries[i]-diff2)
            diff2 = diff2.reshape(dims)
        diff2 **= 2
        d += diff2
    numpy.sqrt(d, d)
    return d

class ConstIter(object):
    """An iterator that always returns the same value."""
    def __init__(self, x):
        self.x = x
    def next(self):
        return self.x

def next_n(sequence, N, start_index, mask_local):
    assert isinstance(N, int), "N is %s, should be an integer" % N
    if isinstance(sequence, random.RandomDistribution):
        values = numpy.array(sequence.next(N, mask_local=mask_local))
    elif isinstance(sequence, (int, float)):
        if mask_local is not None:
            assert mask_local.size == N
            N = mask_local.sum()
            assert isinstance(N, int), "N is %s, should be an integer" % N
        values = numpy.ones((N,))*float(sequence)
    elif hasattr(sequence, "__len__"):
        values = numpy.array(sequence[start_index:start_index+N], float)
        if mask_local is not None:
            assert mask_local.size == N
            assert len(mask_local.shape) == 1, mask_local.shape
            values = values[mask_local]
    else:
        raise Exception("sequence is of type %s" % type(sequence))
    return values

# ==============================================================================
#   Accessing individual neurons
# ==============================================================================

class IDMixin(object):
    """
    Instead of storing ids as integers, we store them as ID objects,
    which allows a syntax like:
        p[3,4].tau_m = 20.0
    where p is a Population object.
    """
    # Simulator ID classes should inherit both from the base type of the ID
    # (e.g., int or long) and from IDMixin.
    # Ideally, the base type need not be numeric, but the position property
    # will have to be modified for that (probably break off into another Mixin
    # class
    
    non_parameter_attributes = ('parent', '_cellclass', 'cellclass',
                                '_position', 'position', 'hocname', '_cell',
                                'inject', '_v_init', 'local')
    
    def __init__(self):
        self.parent = None
        self._cellclass = None
        self.local = True

    def __getattr__(self, name):
        if name in self.non_parameter_attributes or not self.is_standard_cell():
            val = self.__getattribute__(name)
        else:
            try:
                val = self.get_parameters()[name]
            except KeyError:
                raise NonExistentParameterError(name, self.cellclass)
        return val
    
    def __setattr__(self, name, value):
        if name in self.non_parameter_attributes or not self.is_standard_cell():
            object.__setattr__(self, name, value)
        else:
            return self.set_parameters(**{name:value})

    def set_parameters(self, **parameters):
        """Set cell parameters, given as a sequence of parameter=value arguments."""
        # if some of the parameters are computed from the values of other
        # parameters, need to get and translate all parameters
        if self.local:
            if self.is_standard_cell():
                computed_parameters = self.cellclass.computed_parameters()
                have_computed_parameters = numpy.any([p_name in computed_parameters for p_name in parameters])
                if have_computed_parameters:     
                    all_parameters = self.get_parameters()
                    all_parameters.update(parameters)
                    parameters = all_parameters
                parameters = self.cellclass.translate(parameters)
            self.set_native_parameters(parameters)
        else:
            raise NotLocalError("Cannot set parameters for a cell that does not exist on this node.")
    
    def get_parameters(self):
        """Return a dict of all cell parameters."""
        if self.local:
            parameters = self.get_native_parameters()
            if self.is_standard_cell():
                parameters = self.cellclass.reverse_translate(parameters)
            return parameters
        else:
            raise NotLocalError("Cannot obtain parameters for a cell that does not exist on this node.")

    def _set_cellclass(self, cellclass):
        if self.parent is None and self._cellclass is None:
            self._cellclass = cellclass
        else:
            raise Exception("Cell class cannot be changed after the neuron has been created.")

    def _get_cellclass(self):
        if self.parent is not None:
            celltype = self.parent.celltype
            if isinstance(celltype, str):
                return celltype
            else:
                return celltype.__class__
        else:
            return self._cellclass
        
    cellclass = property(fget=_get_cellclass, fset=_set_cellclass)
    
    def is_standard_cell(self):
        return (type(self.cellclass) == type and issubclass(self.cellclass, StandardCellType))
        
    def _set_position(self, pos):
        """
        Set the cell position in 3D space.
        
        Cell positions are stored in an array in the parent Population, if any,
        or within the ID object otherwise.
        """
        assert isinstance(pos, (tuple, numpy.ndarray))
        assert len(pos) == 3
        if self.parent:
            # the following line makes too many assumptions about the
            # implementation of Population. Should use a public method of
            # Population.
            index = numpy.where(self.parent.cell.flatten() == int(self))[0][0]
            self.parent.positions[:, index] = pos
        else:
            self._position = numpy.array(pos)
        
    def _get_position(self):
        """
        Return the cell position in 3D space.
        
        Cell positions are stored in an array in the parent Population, if any,
        or within the ID object otherwise. Positions are generated the first
        time they are requested and then cached.
        """
        if self.parent:
            index = self.parent.id_to_index(self)
            return self.parent.positions[:, index]  
        else:
            try:
                return self._position
            except (AttributeError, KeyError):
                self._position = numpy.array((self, 0.0, 0.0), float)
                return self._position

    position = property(_get_position, _set_position)
      
    def inject(self, current_source):
        """Inject current from a current source object into the cell."""
        current_source.inject_into([self])
        

# ==============================================================================
#   Standard cells
# ==============================================================================

def build_translations(*translation_list):
    """
    Build a translation dictionary from a list of translations/transformations.
    """
    translations = {}
    for item in translation_list:
        assert 2 <= len(item) <= 4, "Translation tuples must have between 2 and 4 items. Actual content: %s" % str(item)
        pynn_name = item[0]
        sim_name = item[1]
        if len(item) == 2: # no transformation
            f = pynn_name
            g = sim_name
        elif len(item) == 3: # simple multiplicative factor
            scale_factor = item[2]
            f = "float(%g)*%s" % (scale_factor, pynn_name)
            g = "%s/float(%g)" % (sim_name, scale_factor)
        elif len(item) == 4: # more complex transformation
            f = item[2]
            g = item[3]
        translations[pynn_name] = {'translated_name': sim_name,
                                   'forward_transform': f,
                                   'reverse_transform': g}
    return translations

class StandardModelType(object):
    """Base class for standardized cell model and synapse model classes."""
    
    translations = {}
    default_parameters = {}
    
    def __init__(self, parameters):
        self.parameters = self.__class__.checkParameters(parameters, with_defaults=True)
        self.parameters = self.__class__.translate(self.parameters)
    
    @classmethod
    def checkParameters(cls, supplied_parameters, with_defaults=False):
        """
        Returns a parameter dictionary, checking that each
        supplied_parameter is in the default_parameters and
        converts to the type of the latter.

        If with_defaults==True, parameters not in
        supplied_parameters are in the returned dictionary
        as in default_parameters.

        """
        default_parameters = cls.default_parameters
        if with_defaults:
            parameters = copy.copy(default_parameters)
        else:
            parameters = {}
        if supplied_parameters:
            for k in supplied_parameters.keys():
                if default_parameters.has_key(k):
                    err_msg = "For %s in %s, expected %s, got %s (%s)" % \
                              (k, cls.__name__, type(default_parameters[k]),
                               type(supplied_parameters[k]), supplied_parameters[k])
                    # same type
                    if type(supplied_parameters[k]) == type(default_parameters[k]): 
                        parameters[k] = supplied_parameters[k]
                    # float and something that can be converted to a float
                    elif type(default_parameters[k]) == types.FloatType: 
                        try:
                            parameters[k] = float(supplied_parameters[k]) 
                        except (ValueError, TypeError):
                            raise InvalidParameterValueError(err_msg)
                    # list and something that can be transformed to a list
                    elif type(default_parameters[k]) == types.ListType:
                        try:
                            parameters[k] = list(supplied_parameters[k])
                        except TypeError:
                            raise InvalidParameterValueError(err_msg)
                    else:
                        raise InvalidParameterValueError(err_msg)
                else:
                    raise NonExistentParameterError(k, cls)
        return parameters
    
    @classmethod
    def translate(cls, parameters):
        """Translate standardized model parameters to simulator-specific parameters."""
        parameters = cls.checkParameters(parameters, with_defaults=False)
        native_parameters = {}
        for name in parameters:
            D = cls.translations[name]
            pname = D['translated_name']
            if is_listlike(cls.default_parameters[name]):
                parameters[name] = numpy.array(parameters[name])
            try:
                pval = eval(D['forward_transform'], globals(), parameters)
            except NameError, errmsg:
                raise NameError("Problem translating '%s' in %s. Transform: '%s'. Parameters: %s. %s" \
                                % (pname, cls.__name__, D['forward_transform'], parameters, errmsg))
            except ZeroDivisionError:
                pval = 1e30 # this is about the highest value hoc can deal with
            native_parameters[pname] = pval
        return native_parameters
    
    @classmethod
    def reverse_translate(cls, native_parameters):
        """Translate simulator-specific model parameters to standardized parameters."""
        standard_parameters = {}
        for name,D  in cls.translations.items():
            if is_listlike(cls.default_parameters[name]):
                tname = D['translated_name']
                native_parameters[tname] = numpy.array(native_parameters[tname])
            try:
                standard_parameters[name] = eval(D['reverse_transform'], {}, native_parameters)
            except NameError, errmsg:
                raise NameError("Problem translating '%s' in %s. Transform: '%s'. Parameters: %s. %s" \
                                % (name, cls.__name__, D['reverse_transform'], native_parameters, errmsg))
        return standard_parameters

    @classmethod
    def simple_parameters(cls):
        """Return a list of parameters for which there is a one-to-one
        correspondance between standard and native parameter values."""
        return [name for name in cls.translations if cls.translations[name]['forward_transform'] == name]

    @classmethod
    def scaled_parameters(cls):
        """Return a list of parameters for which there is a unit change between
        standard and native parameter values."""
        return [name for name in cls.translations if "float" in cls.translations[name]['forward_transform']]
    
    @classmethod
    def computed_parameters(cls):
        """Return a list of parameters whose values must be computed from
        more than one other parameter."""
        return [name for name in cls.translations if name not in cls.simple_parameters()+cls.scaled_parameters()]
        
    def update_parameters(self, parameters):
        """
        update self.parameters with those in parameters 
        """
        self.parameters.update(self.translate(parameters))
        
    def describe(self, template='standard'):
        return str(self)
    

class StandardCellType(StandardModelType):
    """Base class for standardized cell model classes."""

    recordable = ['spikes', 'v', 'gsyn']
    synapse_types = ('excitatory', 'inhibitory')
    conductance_based = True # over-ride for cells with current-based synapses


class ModelNotAvailable(object):
    """Not available for this simulator."""
    
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("The %s model is not available for this simulator." % self.__class__.__name__)

# ==============================================================================
#   Functions for simulation set-up and control
# ==============================================================================

def setup(timestep=0.1, min_delay=0.1, max_delay=10.0, debug=False,
          **extra_params):
    """
    Should be called at the very beginning of a script.
    extra_params contains any keyword arguments that are required by a given
    simulator but not by others.
    """
    invalid_extra_params = ('mindelay', 'maxdelay', 'dt')
    for param in invalid_extra_params:
        if param in extra_params:
            raise Exception("%s is not a valid argument for setup()" % param)
    if min_delay > max_delay:
        raise Exception("min_delay has to be less than or equal to max_delay.")
    if min_delay < timestep:
        "min_delay (%g) must be greater than timestep (%g)" % (min_delay, timestep)
    
    if simulator:
        backend = simulator.__name__.replace('.simulator', '')
        log_file = "%s.log" % backend
    else:
        log_file = "pyNN.log"
    if debug:
        if isinstance(debug, basestring):
            log_file = debug
    if simulator and not simulator.state.initialized:
        utility.init_logging(log_file, debug, num_processes(), rank())
        logger.info("Initialization of %s (use setup(.., debug=True) to see a full logfile)" % backend)
        simulator.state.initialized = True
    
    
def end(compatible_output=True):
    """Do any necessary cleaning up before exiting."""
    raise NotImplementedError
    
def run(simtime):
    """Run the simulation for simtime ms."""
    raise NotImplementedError

def get_current_time():
    """Return the current time in the simulation."""
    return simulator.state.t

def get_time_step():
    """Return the integration time step."""
    return simulator.state.dt

def get_min_delay():
    """Return the minimum allowed synaptic delay."""
    return simulator.state.min_delay

def get_max_delay():
    """Return the maximum allowed synaptic delay."""
    return simulator.state.max_delay

def num_processes():
    """Return the number of MPI processes."""
    return simulator.state.num_processes

def rank():
    """Return the MPI rank of the current node."""
    return simulator.state.mpi_rank

# ==============================================================================
#   Low-level API for creating, connecting and recording from individual neurons
# ==============================================================================

def create(cellclass, cellparams=None, n=1):
    """
    Create n cells all of the same type.
    
    If n > 1, return a list of cell ids/references.
    If n==1, return just the single id.
    """
    all_cells, mask_local, first_id, last_id = simulator.create_cells(cellclass, cellparams, n)
    for id in all_cells[mask_local]:
        id.cellclass = cellclass
    all_cells = all_cells.tolist() # not sure this is desirable, but it is consistent with the other modules
    if n == 1:
        all_cells = all_cells[0]
    return all_cells

def connect(source, target, weight=None, delay=None, synapse_type=None, p=1, rng=None):
    """
    Connect a source of spikes to a synaptic target.
    
    source and target can both be individual cells or lists of cells, in which
    case all possible connections are made with probability p, using either the
    random number generator supplied, or the default rng otherwise.
    Weights should be in nA or µS.
    """
    # This duplicates code from the Connector/FixedProbabilityConnector classes
    # should refactor to eliminate this repetition
    logger.debug("connecting %s to %s on host %d" % (source, target, rank()))
    if not is_listlike(source):
        source = [source]
    if not is_listlike(target):
        target = [target]
    delay = check_delay(delay)
    if p < 1:
        rng = rng or numpy.random
    connection_manager = simulator.ConnectionManager()
    for tgt in target:
        #if not isinstance(tgt, IDMixin):
        #    raise ConnectionError("target is not a cell, actually %s" % type(tgt))
        sources = numpy.array(source, dtype=type(source))
        if p < 1:
            rarr = rng.uniform(0, 1, len(source))
            sources = sources[rarr<p]
        weight = check_weight(weight, synapse_type, is_conductance(tgt))
        for src in sources:
            connection_manager.connect(src, tgt, weight, delay, synapse_type)
    return connection_manager


def set(cells, param, val=None):
    """
    Set one or more parameters of an individual cell or list of cells.
    
    param can be a dict, in which case val should not be supplied, or a string
    giving the parameter name, in which case val is the parameter value.
    """
    if val:
        param = {param:val}
    if not hasattr(cells, '__len__'):
        cells = [cells]
    # see comment in Population.set() below about the efficiency of the
    # following
    for cell in (cell for cell in cells if cell.local):
        cell.set_parameters(**param)

def build_record(variable, simulator):
    def record(source, filename):
        """
        Record spikes to a file. source can be an individual cell or a list of
        cells.
        """
        # would actually like to be able to record to an array and choose later
        # whether to write to a file.
        if not hasattr(source, '__len__'):
            source = [source]
        recorder = simulator.Recorder(variable, file=filename)
        recorder.record(source)
        simulator.recorder_list.append(recorder)
    if variable == 'v':
        record.__doc__ = """
            Record membrane potential to a file. source can be an individual cell or
            a list of cells."""
    elif variable == 'gsyn':
        record.__doc__ = """
            Record synaptic conductances to a file. source can be an individual cell
            or a list of cells."""
    return record

# ==============================================================================
#   High-level API for creating, connecting and recording from populations of
#   neurons.
# ==============================================================================

class Population(object):
    """
    An array of neurons all of the same type. `Population' is used as a generic
    term intended to include layers, columns, nuclei, etc., of cells.
    """
    
    def __init__(self, dims, cellclass, cellparams=None, label=None, parent=None):
        """
        Create a population of neurons all of the same type.
        
        dims should be a tuple containing the population dimensions, or a single
          integer, for a one-dimensional population.
          e.g., (10,10) will create a two-dimensional population of size 10x10.
        cellclass should either be a standardized cell class (a class inheriting
        from common.StandardCellType) or a string giving the name of the
        simulator-specific model that makes up the population.
        cellparams should be a dict which is passed to the neuron model
          constructor
        label is an optional name for the population.
        """
        
        self.dim = dims
        if isinstance(dims, int): # also allow a single integer, for a 1D population
            self.dim = (self.dim,)
        else:
            assert isinstance(dims, tuple), "`dims` must be an integer or a tuple. You have supplied a %s" % type(dims)
        self.label = label
        self.celltype = cellclass
        self.ndim = len(self.dim)
        self.cellparams = cellparams
        self.size = self.dim[0]
        self.parent = parent
        for i in range(1, self.ndim):
            self.size *= self.dim[i]
    
    def __getitem__(self, addr):
        """
        Return a representation of the cell with coordinates given by addr,
        suitable for being passed to other methods that require a cell id.
        Note that __getitem__ is called when using [] access, e.g.
            p = Population(...)
            p[2,3] is equivalent to p.__getitem__((2,3)).
        Also accepts slices, e.g.
            p[0,3:6]
        which returns an array of cells.
        """
        if isinstance(addr, (int, slice)):
            addr = (addr,)
        if len(addr) == self.ndim:
            id = self.all_cells[addr]
        else:
            raise InvalidDimensionsError, "Population has %d dimensions. Address was %s" % (self.ndim, str(addr))
        return id
    
    def __iter__(self):
        """Iterator over cell ids on the local node."""
        return iter(self.local_cells.flat)
        
    def __address_gen(self):
        """
        Generator to produce an iterator over all cells on this node,
        returning addresses.
        """
        for i in self.__iter__():
            yield self.locate(i)

    def addresses(self):
        """Iterator over cell addresses on the local node."""
        return self.__address_gen()
    
    def ids(self):
        """Iterator over cell ids on the local node."""
        return self.__iter__()
    
    def all(self):
        """Iterator over cell ids on all nodes."""
        return self.all_cells.flat
    
    def locate(self, id):
        """
        Given an element id in a Population, return the coordinates.
            e.g. for  4 6  , element 2 has coordinates (1,0) and value 7
                      7 9
        """
        # this implementation assumes that ids are consecutive
        # a slower (for large populations) implementation that does not make
        # this assumption is:
        #   return tuple([a.tolist()[0] for a in numpy.where(self.all_cells == id)])
        idx = self.id_to_index(id)
        if self.ndim == 3:
            rows = self.dim[1]; cols = self.dim[2]
            i = idx/(rows*cols); remainder = idx%(rows*cols)
            j = remainder/cols; k = remainder%cols
            coords = (i,j,k)
        elif self.ndim == 2:
            cols = self.dim[1]
            i = idx/cols; j = idx%cols
            coords = (i,j)
        elif self.ndim == 1:
            coords = (idx,)
        else:
            raise common.InvalidDimensionsError
        return coords
    
    def id_to_index(self, id):
        """
        Given the ID of a cell in the Population, return its index (order in the
        Population).
        >>> assert id_to_index(p.index(5)) == 5
        """
        assert self.first_id <= id <= self.last_id 
        return id - self.first_id # this assumes ids are consecutive
    
    def index(self, n):
        """
        Return the nth cell in the population (Indexing starts at 0).
        n may be a list or array, e.g., [i,j,k], in which case, returns the
        ith, jth and kth cells in the population."""
        if hasattr(n, '__len__'):
            n = numpy.array(n)
        return self.all_cells.flatten()[n]
    
    def __len__(self):
        """Return the total number of cells in the population."""
        return self.size
    
    def _get_positions(self):
        """
        Try to return self._positions. If it does not exist, create it and then return it
        """
        try:
            return self._positions
        except AttributeError:
            x,y,z = numpy.indices(list(self.dim) + [1]*(3-len(self.dim))).astype(float)
            x = x.flatten(); y = y.flatten(); z = z.flatten()
            self._positions = numpy.array((x,y,z))
            return self._positions

    def _set_positions(self, pos_array):
        assert isinstance(pos_array, numpy.ndarray)
        assert pos_array.shape == (3, self.size), "%s != %s" % (pos_array.shape, (3, self.size))
        self._positions = pos_array.copy() # take a copy in case pos_array is changed later

    positions = property(_get_positions, _set_positions,
                         """A 3xN array (where N is the number of neurons in the Population)
                         giving the x,y,z coordinates of all the neurons (soma, in the
                         case of non-point models).""")
    
    def nearest(self, position):
        """Return the neuron closest to the specified position."""
        # doesn't always work correctly if a position is equidistant between two
        # neurons, i.e. 0.5 should be rounded up, but it isn't always.
        # also doesn't take account of periodic boundary conditions
        pos = numpy.array([position]*self.positions.shape[1]).transpose()
        dist_arr = (self.positions - pos)**2
        distances = dist_arr.sum(axis=0)
        nearest = distances.argmin()
        return self.index(nearest)
    
    def get(self, parameter_name, as_array=False): # would be nice to add a 'gather' argument
        """
        Get the values of a parameter for every cell in the population.
        """
        # if all the cells have the same value for this parameter, should
        # we return just the number, rather than an array?
        if as_array:
            values = numpy.NaN*numpy.ones(self.dim)
            for cell in self.all():
                addr = self.locate(cell)
                if cell.local:
                    values[addr] = getattr(cell, parameter_name)
        else:
            values = [getattr(cell, parameter_name) for cell in self]
        return values
            
    def set(self, param, val=None):
        """
        Set one or more parameters for every cell in the population. param
        can be a dict, in which case val should not be supplied, or a string
        giving the parameter name, in which case val is the parameter value.
        val can be a numeric value, or list of such (e.g. for setting spike times).
        e.g. p.set("tau_m",20.0).
             p.set({'tau_m':20,'v_rest':-65})
        """
        if isinstance(param, str):
            if isinstance(val, (str, float, int)):
                param_dict = {param: float(val)}
            elif isinstance(val, (list, numpy.ndarray)):
                param_dict = {param: val}
            else:
                raise InvalidParameterValueError
        elif isinstance(param, dict):
            param_dict = param
        else:
            raise InvalidParameterValueError
        logger.debug("%s.set(%s)", self.label, param_dict)
        for cell in self:
            cell.set_parameters(**param_dict)

    def tset(self, parametername, value_array):
        """
        'Topographic' set. Set the value of parametername to the values in
        value_array, which must have the same dimensions as the Population.
        """
        if self.dim == value_array.shape: # the values are numbers or non-array objects
            local_values = value_array[self._mask_local]
            assert local_values.size == self.local_cells.size, "%d != %d" % (local_values.size, self.local_cells.size)
        elif len(value_array.shape) == len(self.dim)+1: # the values are themselves 1D arrays
            local_values = value_array[self._mask_local] # not sure this works
        else:
            raise InvalidDimensionsError, "Population: %s, value_array: %s" % (str(self.dim),
                                                                               str(value_array.shape))
        assert local_values.shape[0] == self.local_cells.size, "%d != %d" % (local_values.size, self.local_cells.size)
        
        try:
            logger.debug("%s.tset('%s', array(shape=%s, min=%s, max=%s))",
                         self.label, parametername, value_array.shape,
                         value_array.min(), value_array.max())
        except TypeError: # min() and max() won't work for non-numeric values
            logger.debug("%s.tset('%s', non_numeric_array(shape=%s))",
                         self.label, parametername, value_array.shape)
        
        # Set the values for each cell
        for cell, val in zip(self, local_values):
            setattr(cell, parametername, val)
    
    def rset(self, parametername, rand_distr):
        """
        'Random' set. Set the value of parametername to a value taken from
        rand_distr, which should be a RandomDistribution object.
        """
        rarr = rand_distr.next(n=self.all_cells.size, mask_local=self._mask_local.flatten())
        rarr = numpy.array(rarr)
        logger.debug("%s.rset('%s', %s)", self.label, parametername, rand_distr)
        for cell,val in zip(self, rarr):
            setattr(cell, parametername, val)
    
    def _call(self, methodname, arguments):
        """
        Call the method methodname(arguments) for every cell in the population.
        e.g. p.call("set_background","0.1") if the cell class has a method
        set_background().
        """
        raise NotImplementedError()
    
    def _tcall(self, methodname, objarr):
        """
        `Topographic' call. Call the method methodname() for every cell in the 
        population. The argument to the method depends on the coordinates of the
        cell. objarr is an array with the same dimensions as the Population.
        e.g. p.tcall("memb_init", vinitArray) calls
        p.cell[i][j].memb_init(vInitArray[i][j]) for all i,j.
        """
        raise NotImplementedError()

    def randomInit(self, rand_distr):
        """
        Set initial membrane potentials for all the cells in the population to
        random values.
        """
        self.rset('v_init', rand_distr)

    def can_record(self, variable):
        """Determine whether `variable` can be recorded from this population."""
        if isinstance(self.celltype, StandardCellType):
            return (variable in self.celltype.recordable)
        else:
            return True # for now, not able to check for native cells, although it should be possible in principle

    def _record(self, variable, record_from=None, rng=None, to_file=True):
        """
        Private method called by record() and record_v().
        """
        if not self.can_record(variable):
            raise RecordingError(variable, self.celltype)
        if isinstance(record_from, list): #record from the fixed list specified by user
            pass
        elif record_from is None: # record from all cells:
            record_from = self.all_cells.flatten()
        elif isinstance(record_from, int): # record from a number of cells, selected at random  
            # Each node will record N/nhost cells...
            nrec = int(record_from/num_processes())
            if not rng:
                rng = random.NumpyRNG()
            record_from = rng.permutation(self.all_cells.flatten())[0:nrec]
            # need ID objects, permutation returns integers
            # ???
        else:
            raise Exception("record_from must be either a list of cells or the number of cells to record from")
        # record_from is now a list or numpy array. We do not have to worry about whether the cells are
        # local because the Recorder object takes care of this.
        logger.debug("%s.record('%s', %s)", self.label, variable, record_from[:5])
        self.recorders[variable].record(record_from)

    def record(self, record_from=None, rng=None, to_file=True):
        """
        If record_from is not given, record spikes from all cells in the Population.
        record_from can be an integer - the number of cells to record from, chosen
        at random (in this case a random number generator can also be supplied)
        - or a list containing the ids of the cells to record.
        """
        self._record('spikes', record_from, rng, to_file)

    def record_v(self, record_from=None, rng=None, to_file=True):
        """
        If record_from is not given, record the membrane potential for all cells in
        the Population.
        record_from can be an integer - the number of cells to record from, chosen
        at random (in this case a random number generator can also be supplied)
        - or a list containing the ids of the cells to record.
        """
        self._record('v', record_from, rng, to_file)

    def record_gsyn(self, record_from=None, rng=None, to_file=True):
        """
        If record_from is not given, record synaptic conductances
        for all cells in the Population.
        record_from can be an integer - the number of cells to record from, chosen
        at random (in this case a random number generator can also be supplied)
        - or a list containing the ids of the cells to record.
        """
        self._record('gsyn', record_from, rng, to_file)

    def printSpikes(self, file, gather=True, compatible_output=True):
        """
        Write spike times to file.
        
        file should be either a filename or a PyNN File object.
        
        If compatible_output is True, the format is "spiketime cell_id",
        where cell_id is the index of the cell counting along rows and down
        columns (and the extension of that for 3-D).
        This allows easy plotting of a `raster' plot of spiketimes, with one
        line for each cell.
        The timestep, first id, last id, and number of data points per cell are
        written in a header, indicated by a '#' at the beginning of the line.
        
        If compatible_output is False, the raw format produced by the simulator
        is used. This may be faster, since it avoids any post-processing of the
        spike files.
        
        For parallel simulators, if gather is True, all data will be gathered
        to the master node and a single output file created there. Otherwise, a
        file will be written on each node, containing only the cells simulated
        on that node.
        """        
        self.recorders['spikes'].write(file, gather, compatible_output)
    
    def getSpikes(self, gather=True, compatible_output=True):
        """
        Return a 2-column numpy array containing cell ids and spike times for
        recorded cells.

        Useful for small populations, for example for single neuron Monte-Carlo.
        """
        return self.recorders['spikes'].get(gather, compatible_output)

    def print_v(self, file, gather=True, compatible_output=True):
        """
        Write membrane potential traces to file.
        
        file should be either a filename or a PyNN File object.
        
        If compatible_output is True, the format is "v cell_id",
        where cell_id is the index of the cell counting along rows and down
        columns (and the extension of that for 3-D).
        The timestep, first id, last id, and number of data points per cell are
        written in a header, indicated by a '#' at the beginning of the line.
        
        If compatible_output is False, the raw format produced by the simulator
        is used. This may be faster, since it avoids any post-processing of the
        voltage files.
        
        For parallel simulators, if gather is True, all data will be gathered
        to the master node and a single output file created there. Otherwise, a
        file will be written on each node, containing only the cells simulated
        on that node.
        """
        self.recorders['v'].write(file, gather, compatible_output)
    
    def get_v(self, gather=True, compatible_output=True):
        """
        Return a 2-column numpy array containing cell ids and Vm for
        recorded cells.
        """
        return self.recorders['v'].get(gather, compatible_output)
    
    def print_gsyn(self, file, gather=True, compatible_output=True):
        """
        Write synaptic conductance traces to file.
        
        file should be either a filename or a PyNN File object.
        
        If compatible_output is True, the format is "t g cell_id",
        where cell_id is the index of the cell counting along rows and down
        columns (and the extension of that for 3-D).
        The timestep, first id, last id, and number of data points per cell are
        written in a header, indicated by a '#' at the beginning of the line.

        If compatible_output is False, the raw format produced by the simulator
        is used. This may be faster, since it avoids any post-processing of the
        voltage files.
        """
        self.recorders['gsyn'].write(file, gather, compatible_output)
    
    def get_gsyn(self, gather=True, compatible_output=True):
        """
        Return a 3-column numpy array containing cell ids and synaptic
        conductances for recorded cells.
        """
        return self.recorders['gsyn'].get(gather, compatible_output)
        
    def get_spike_counts(self, gather=True):
        """
        Returns the number of spikes for each neuron.
        """
        return self.recorders['spikes'].count(gather)
        
    def meanSpikeCount(self, gather=True):
        """
        Returns the mean number of spikes per neuron.
        """
        spike_counts = self.recorders['spikes'].count(gather)
        total_spikes = sum(spike_counts.values())
        return float(total_spikes)/len(spike_counts)
    
    def describe(self, template='standard', fill=lambda t,c: Template(t).safe_substitute(c)):
        """
        Returns a human-readable description of the population
        """
        if template == 'standard':
            #lines = ['==== Population $label ====',
            #         '  Dimensions: $dim',
            #         '  Local cells: $n_cells_local',
            #         '  Cell type: $celltype',
            #         '  ID range: $first_id-$last_id',
            #         '  First cell on this node:',
            #         '    ID: $local_first_id',
            #         '    Parameters: $cell_parameters']
            lines = ['------- Population description -------',
                     'Population called $label is made of $n_cells cells [$n_cells_local being local]']
            if self.parent:
                lines += ['This population is a subpopulation of population $parent_label']
            lines += ["-> Cells are arranged on a ${ndim}D grid of size $dim",
                      "-> Celltype is $celltype",
                      "-> ID range is $first_id-$last_id",]
            if len(self.local_cells) > 0:
                lines += ["-> Cell Parameters used for first cell on this node are: "]
                for name, value in self.local_cells[0].get_parameters().items():
                    lines += ["    | %-12s: %s" % (name, value)]
            else:
                lines += ["-> There are no cells on this node."]
            lines += ["--- End of Population description ----"]
            template = "\n".join(lines)
            
        context = self.__dict__.copy()
        if len(self.local_cells) > 0:
            first_id = self.local_cells[0]
            context.update(local_first_id=first_id)
            cell_parameters = first_id.get_parameters()
            names = cell_parameters.keys()
            names.sort()
            context.update(cell_parameters=[(name,cell_parameters[name]) for name in names])
        context.update(celltype=self.celltype.__class__.__name__)
        context.update(n_cells=len(self))
        context.update(n_cells_local=len(self.local_cells))
        for k in context.keys():
            if k[0] == '_':
                context.pop(k)
                
        if template == None:
            return context
        else:
            return fill(template, context)
    
    def inject(self, current_source):
        """
        Connect a current source to all cells in the Population.
        """
        if 'v' not in self.celltype.recordable:
            raise TypeError("Can't inject current into a spike source.")
        current_source.inject_into(self)
    
    def getSubPopulation(self, cells):
        """
        Returns a sub population from a population object. The shape of cells will
        determine the dimensions of the sub population. cells should contains cells
        member of the parent population.
        Ex z = pop.getSubPopulation([pop[1],pop[3],pop[5]])
        """
        raise NotImplementedError()
    
# ==============================================================================

class Projection(object):
    """
    A container for all the connections of a given type (same synapse type and
    plasticity mechanisms) between two populations, together with methods to set
    parameters of those connections, including of plasticity mechanisms.
    """
    
    def __init__(self, presynaptic_population, postsynaptic_population,
                 method,
                 source=None, target=None, synapse_dynamics=None,
                 label=None, rng=None):
        """
        presynaptic_population and postsynaptic_population - Population objects.
        
        source - string specifying which attribute of the presynaptic cell
                 signals action potentials. This is only needed for
                 multicompartmental cells with branching axons or dendrodendritic
                 synapses. All standard cells have a single source, and this
                 is the default.
                 
        target - string specifying which synapse on the postsynaptic cell to
                 connect to. For standard cells, this can be 'excitatory' or
                 'inhibitory'. For non-standard cells, it could be 'NMDA', etc.
                 If target is not given, the default values of 'excitatory' is used.
        
        method - a Connector object, encapsulating the algorithm to use for
                 connecting the neurons.
        
        synapse_dynamics - a `SynapseDynamics` object specifying which
                 synaptic plasticity mechanisms to use.
        
        rng - specify an RNG object to be used by the Connector.
        """
        
        self.pre    = presynaptic_population  # } these really        
        self.source = source                  # } should be
        self.post   = postsynaptic_population # } read-only
        self.target = target                  # }
        self.label  = label
        if isinstance(rng, random.AbstractRNG):
            self.rng = rng
        elif rng is None:
            self.rng = random.NumpyRNG(seed=151985012, rank=rank(), num_processes=num_processes(), parallel_safe=True)
        else:
            raise Exception("rng must be either None, or a subclass of pyNN.random.AbstractRNG")
        self._method = method
        self.synapse_dynamics = synapse_dynamics
        #self.connection = None # access individual connections. To be defined by child, simulator-specific classes
        self.weights = []
        if label is None:
            if self.pre.label and self.post.label:
                self.label = "%s→%s" % (self.pre.label, self.post.label)
    
        # Deal with synaptic plasticity
        self.short_term_plasticity_mechanism = None
        self.long_term_plasticity_mechanism = None
        if self.synapse_dynamics:
            assert isinstance(self.synapse_dynamics, SynapseDynamics), \
              "The synapse_dynamics argument, if specified, must be a SynapseDynamics object, not a %s" % type(synapse_dynamics)
            if self.synapse_dynamics.fast:
                assert isinstance(self.synapse_dynamics.fast, ShortTermPlasticityMechanism)
                if hasattr(self.synapse_dynamics.fast, 'native_name'):
                    self.short_term_plasticity_mechanism = self.synapse_dynamics.fast.native_name
                else:
                    self.short_term_plasticity_mechanism = self.synapse_dynamics.fast.possible_models
                self._short_term_plasticity_parameters = self.synapse_dynamics.fast.parameters.copy()
            if self.synapse_dynamics.slow:
                assert isinstance(self.synapse_dynamics.slow, STDPMechanism)
                assert 0 <= self.synapse_dynamics.slow.dendritic_delay_fraction <= 1.0
                td = self.synapse_dynamics.slow.timing_dependence
                wd = self.synapse_dynamics.slow.weight_dependence
                self._stdp_parameters = td.parameters.copy()
                self._stdp_parameters.update(wd.parameters)
                
                possible_models = td.possible_models.intersection(wd.possible_models)
                if len(possible_models) == 1 :
                    self.long_term_plasticity_mechanism = list(possible_models)[0]
                elif len(possible_models) == 0 :
                    raise NoModelAvailableError("No available plasticity models")
                elif len(possible_models) > 1 :
                    if self.synapse_dynamics.slow.model:
                        # addition of the `model` attribute (see r415) is a pragmatic solution
                        # but not an elegant one, and I don't think it should go into a released API
                        # Since the problem of multiple models only seems to appear for NEST
                        # with homogeneous and non-homogeneous versions, it would be better either
                        # for the code to decide itself which to use (would be complex, as
                        # connection creation would have to be deferred to run()) or to have
                        # a global OPTIMIZED variable (possibly set in setup()) - if this was
                        # set True the homogeneous version would be used and later attempts to
                        # change parameters of the synapse would raise Exceptions.
                        if self.synapse_dynamics.slow.model in list(possible_models):
                            self.long_term_plasticity_mechanism = self.synapse_dynamics.slow.model
                        else:
                            print "The particular model %s does not exist !" %self.synapse_dynamics.slow.model
                    else:
                        # we pass the set of models back to the simulator-specific module for it to deal with
                        self.long_term_plasticity_mechanism = possible_models
                     
    def __len__(self):
        """Return the total number of connections."""
        return len(self.connection_manager)
    
    def __repr__(self):
        return 'Projection("%s")' % self.label
    
    # --- Methods for setting connection parameters ----------------------------
    
    def setWeights(self, w):
        """
        w can be a single number, in which case all weights are set to this
        value, or a list/1D array of length equal to the number of connections
        in the projection.
        Weights should be in nA for current-based and µS for conductance-based
        synapses.
        """
        # should perhaps add a "distribute" argument, for symmetry with "gather" in getWeights()
        self.connection_manager.set('weight', w)
    
    def randomizeWeights(self, rand_distr):
        """
        Set weights to random values taken from rand_distr.
        """
        # Arguably, we could merge this with set_weights just by detecting the
        # argument type. It could make for easier-to-read simulation code to
        # give it a separate name, though. Comments?
        self.setWeights(rand_distr.next(len(self)))
    
    def setDelays(self, d):
        """
        d can be a single number, in which case all delays are set to this
        value, or a list/1D array of length equal to the number of connections
        in the projection.
        """
        self.connection_manager.set('delay', d)
    
    def randomizeDelays(self, rand_distr):
        """
        Set delays to random values taken from rand_distr.
        """
        self.setDelays(rand_distr.next(len(self)))

    def setSynapseDynamics(self, param, value):
        """
        Set parameters of the dynamic synapses for all connections in this
        projection.
        """
        self.connection_manager.set(param, value)

    def randomizeSynapseDynamics(self, param, rand_distr):
        """
        Set parameters of the synapse dynamics to values taken from rand_distr
        """
        self.setSynapseDynamics(param, rand_distr.next(len(self)))
    
    # --- Methods for writing/reading information to/from file. ----------------
    
    def getWeights(self, format='list', gather=True):
        """
        Get synaptic weights for all connections in this Projection.
        
        Possible formats are: a list of length equal to the number of connections
        in the projection, a 2D weight array (with NaN for non-existent
        connections). Note that for the array format, if there is more than
        one connection between two cells, the summed weight will be given.
        """
        if gather:
            logger.error("getWeights() with gather=True not yet implemented")
        return self.connection_manager.get('weight', format, offset=(self.pre.first_id, self.post.first_id))
            
    def getDelays(self, format='list', gather=True):
        """
        Get synaptic delays for all connections in this Projection.
        
        Possible formats are: a list of length equal to the number of connections
        in the projection, a 2D delay array (with NaN for non-existent
        connections).
        """
        if gather:
            logger.error("getDelays() with gather=True not yet implemented")
        return self.connection_manager.get('delay', format, offset=(self.pre.first_id, self.post.first_id))

    def getSynapseDynamics(self, parameter_name, format='list', gather=True):
        """
        Get parameters of the dynamic synapses for all connections in this
        Projection.
        """
        if gather:
            logger.error("getSynapseDynamics() with gather=True not yet implemented")
        return self.connection_manager.get(parameter_name, format, offset=(self.pre.first_id, self.post.first_id))
    
    def saveConnections(self, filename, gather=False):
        """
        Save connections to file in a format suitable for reading in with a
        FromFileConnector.
        """
        if gather == True:
            raise Exception("saveConnections(gather=True) not yet supported")
        elif num_processes() > 1:
            filename += '.%d' % rank()
        logger.debug("--- Projection[%s].__saveConnections__() ---" % self.label)
        f = open(filename, 'w', DEFAULT_BUFFER_SIZE)
        fmt = "%s%s\t%s%s\t%s\t%s\n" % (self.pre.label, "%s", self.post.label,
                                        "%s", "%g", "%g")
        for c in self.connections:     
            line = fmt  % (self.pre.locate(c.source),
                           self.post.locate(c.target),
                           c.weight,
                           c.delay)
            line = line.replace('(','[').replace(')',']')
            f.write(line)
        f.close()
    
    def printWeights(self, filename, format='list', gather=True):
        """Print synaptic weights to file. In the array format, zeros are printed
        for non-existent connections."""
        weights = self.getWeights(format=format, gather=gather)
        f = open(filename, 'w', DEFAULT_BUFFER_SIZE)
        if format == 'list':
            f.write("\n".join([str(w) for w in weights]))
        elif format == 'array':
            weights = numpy.where(numpy.isnan(weights), 0.0, weights)
            numpy.savetxt(f, weights, "%g")
            #fmt = "%g "*len(self.post) + "\n"
            #for row in weights:
            #    f.write(fmt % tuple(row))
        f.close()
    
    def weightHistogram(self, min=None, max=None, nbins=10):
        """
        Return a histogram of synaptic weights.
        If min and max are not given, the minimum and maximum weights are
        calculated automatically.
        """
        # it is arguable whether functions operating on the set of weights
        # should be put here or in an external module.
        bins = numpy.arange(min, max, float(max-min)/nbins)
        return numpy.histogram(self.getWeights(format='list', gather=True), bins) # returns n, bins
    
    def describe(self, template='standard'):
        """
        Return a human-readable description of the projection
        """
        if template == 'standard':
            lines = ["------- Projection description -------",
                     "Projection '$label' from '$pre_label' [$pre_n_cells cells] to '$post_label' [$post_n_cells cells]",
                     "    | Connector : $connector",
                     "    | Weights : $weights",
                     "    | Delays : $delays",
                     "    | Plasticity : $plasticity",
                     "    | Num. connections : $nconn",
                    ]        
            lines += ["---- End of Projection description -----"]
            template = '\n'.join(lines)
        
        context = self.__dict__.copy()
        context.update({
            'nconn': len(self),
            'pre_label': self.pre.label,
            'post_label': self.post.label,
            'pre_n_cells': self.pre.size,
            'post_n_cells': self.post.size,
            'weights': str(self._method.weights),
            'delays': str(self._method.delays),
            'connector': self._method.__class__.__name__
        })
        if self.synapse_dynamics:
            context.update(plasticity=self.synapse_dynamics.describe())
        else:
            context.update(plasticity='None')
            
        if template == None:
            return context
        else:
            return Template(template).substitute(context)


# ==============================================================================
#   Connection method classes
# ==============================================================================

class Connector(object):
    """Base class for Connector classes."""
    
    def __init__(self, weights=0.0, delays=None, check_connections=False):
        self.w_index = 0 # should probably use a generator
        self.d_index = 0 # rather than storing these values
        self.weights = weights
        self.delays = delays
        self.check_connections = check_connections
        if delays is None:
            self.delays = get_min_delay()
    
    def connect(self, projection):
        """Connect all neurons in ``projection``"""
        raise NotImplementedError()
    
    def get_weights(self, N, mask_local=None):
        """
        Returns the next N weight values
        """
        weights = next_n(self.weights, N, self.w_index, mask_local)
        self.w_index += N
        return weights
    
    def get_delays(self, N, mask_local=None):
        """
        Returns the next N delay values
        """
        delays = next_n(self.delays, N, self.d_index, mask_local)
        self.d_index += N
        if self.check_connections:
            assert numpy.all(delays >= get_min_delay()), \
            "Delay values must be greater than or equal to the minimum delay %g. The smallest delay is %g." % (get_min_delay(), delays.min())
            assert numpy.all(delays <= get_max_delay()), \
            "Delay values must be less than or equal to the maximum delay %s. The largest delay is %s" % (get_max_delay(), delays.max())                                                                                              
        return delays
    
    def weights_iterator(self):
        w = self.weights
        if w is not None:
            if hasattr(w, '__len__'): # w is an array
                weights = w.__iter__()
            else:
                weights = ConstIter(w)
        else: 
            weights = ConstIter(1.0)
        return weights
    
    def delays_iterator(self):
        d = self.delays
        min_delay = get_min_delay()
        if d is not None:
            if hasattr(d, '__len__'): # d is an array
                if min(d) < min_delay:
                    raise Exception("The array of delays contains one or more values that is smaller than the simulator minimum delay.")
                delays = d.__iter__()
            else:
                delays = ConstIter(max((d, min_delay)))
        else:
            delays = ConstIter(min_delay)
        return delays
        
# ==============================================================================
#   Synapse Dynamics classes
# ==============================================================================

class SynapseDynamics(object):
    """
    For specifying synapse short-term (faciliation, depression) and long-term
    (STDP) plasticity. To be passed as the `synapse_dynamics` argument to
    `Projection.__init__()` or `connect()`.
    """
    
    def __init__(self, fast=None, slow=None):
        """
        Create a new specification for a dynamic synapse, combining a `fast`
        component (short-term facilitation/depression) and a `slow` component
        (long-term potentiation/depression).
        """
        self.fast = fast
        self.slow = slow
    
    def describe(self, template='standard'):
        """
        Return a human-readable description of the synaptic properties.
        """
        if template == 'standard':
            lines = ["Short-term plasticity mechanism: $fast",
                     "Long-term plasticity mechanism: $slow"]
            template = "\n".join(lines)
        context = {'fast': self.fast and self.fast.describe() or 'None',
                   'slow': self.slow and self.slow.describe() or 'None'}
        if template == None:
            return context
        else:
            return Template(template).substitute(context)
        
        
class ShortTermPlasticityMechanism(StandardModelType):
    """Abstract base class for models of short-term synaptic dynamics."""
    
    def __init__(self):
        raise NotImplementedError


class STDPMechanism(object):
    """Specification of STDP models."""
    
    def __init__(self, timing_dependence=None, weight_dependence=None,
                 voltage_dependence=None, dendritic_delay_fraction=1.0): #, model=None):
        """
        Create a new specification for an STDP mechanism, by combining a
        weight-dependence, a timing-dependence, and, optionally, a voltage-
        dependence.
        
        For point neurons, the synaptic delay `d` can be interpreted either as
        occurring purely in the pre-synaptic axon + synaptic cleft, in which
        case the synaptic plasticity mechanism 'sees' the post-synaptic spike
        immediately and the pre-synaptic spike after a delay `d`
        (`dendritic_delay_fraction = 0`) or as occurring purely in the post-
        synaptic dendrite, in which case the pre-synaptic spike is seen
        immediately, and the post-synaptic spike after a delay `d`
        (`dendritic_delay_fraction = 1`), or as having both pre- and post-
        synaptic components (`dendritic_delay_fraction` between 0 and 1).
        
        In a future version of the API, we will allow the different
        components of the synaptic delay to be specified separately in
        milliseconds.
        """
        self.timing_dependence = timing_dependence
        self.weight_dependence = weight_dependence
        self.voltage_dependence = voltage_dependence
        self.dendritic_delay_fraction = dendritic_delay_fraction
        #self.model = model # see comment in Projection.__init__()
        
    def describe(self):
        """
        Return a human-readable description of the STDP mechanism.
        """
        return "STDP mechanism (this description needs to be filled out)."


class STDPWeightDependence(StandardModelType):
    """Abstract base class for models of STDP weight dependence."""
    
    def __init__(self):
        raise NotImplementedError


class STDPTimingDependence(StandardModelType):
    """Abstract base class for models of STDP timing dependence (triplets, etc)"""
    
    def __init__(self):
        raise NotImplementedError


# ==============================================================================
