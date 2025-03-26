#  _________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright (c) 2014 Sandia Corporation.
#  Under the terms of Contract DE-AC04-94AL85000 with Sandia Corporation,
#  the U.S. Government retains certain rights in this software.
#  This software is distributed under the BSD License.
#  _________________________________________________________________________

__all__ = ['Model', 'ConcreteModel', 'AbstractModel', 'global_option']

import logging
import sys
from weakref import ref as weakref_ref
import gc
import time
import math
import functools

try:
    from collections import OrderedDict
except ImportError:                         #pragma:nocover
    from ordereddict import OrderedDict
try:
    from pympler import muppy
    from pympler import summary
    pympler_available = True
except ImportError:                         #pragma:nocover
    pympler_available = False

from pyomo.util.plugin import ExtensionPoint
from pyutilib.math import *
from pyutilib.misc import tuplize, Container, PauseGC, Bunch

import pyomo.util
from pyomo.util._task import pyomo_api
from pyomo.core.base.var import _VarData, Var
from pyomo.core.base.constraint import _ConstraintData, Constraint
from pyomo.core.base.objective import Objective, _ObjectiveData
from pyomo.core.base.set_types import *
from pyomo.core.base.suffix import active_import_suffix_generator
from pyomo.core.base.symbol_map import SymbolMap
from pyomo.core.base.indexed_component import IndexedComponent
from pyomo.core.base.DataPortal import *
from pyomo.core.base.plugin import *
from pyomo.core.base.numvalue import *
from pyomo.core.base.block import SimpleBlock
from pyomo.core.base.sets import Set
from pyomo.core.base.component import register_component, Component, ComponentUID
from pyomo.core.base.plugin import TransformationFactory
from pyomo.core.base.label import CNameLabeler, CuidLabeler
import pyomo.opt
from pyomo.opt.base import ProblemFormat, guess_format
from pyomo.opt.results import SolverResults, Solution, SolutionStatus, UndefinedData

from six import itervalues, iteritems, StringIO
from six.moves import xrange
try:
    unicode
except:
    basestring = unicode = str

logger = logging.getLogger('pyomo.core')


def global_option(function, name, value):
    """
    Declare the default value for a global Pyomo configuration option.

    Example use:

    @global_option('config.foo.bar', 1)
    def functor():
        ...
    """
    PyomoConfig._option[tuple(name.split('.'))] = value
    def wrapper_function(*args, **kwargs):
        return function(*args, **kwargs)
    return wrapper_function


class PyomoConfig(Container):
    """
    This is a pyomo-specific configuration object, which is a subclass of Container.
    """

    _option = {}

    def __init__(self, *args, **kw):
        Container.__init__(self, *args, **kw)
        self.set_name('PyomoConfig')
        #
        # Create the nested options specified by the the PyomoConfig._option
        # dictionary, which has been populated with the global_option decorator.
        #
        for item in PyomoConfig._option:
            d = self
            for attr in item[:-1]:
                if not attr in d:
                    d[attr] = Container()
                d = d[attr]
            d[item[-1]] = PyomoConfig._option[item]


class ModelSolution(object):

    def __init__(self):
        self._metadata = {}
        self._metadata['status'] = None
        self._metadata['message'] = None
        self._metadata['gap'] = None
        self._entry = {}
        #
        # entry[name]: id -> (object weakref, entry)
        #
        for name in ['objective', 'variable', 'constraint', 'problem']:
            self._entry[name] = {}

    def __getattr__(self, name):
        if name[0] == '_':
            return self.__dict__[name]
        return self.__dict__['_metadata'][name]

    def __setattr__(self, name, val):
        if name[0] == '_':
            self.__dict__[name] = val
            return
        self.__dict__['_metadata'][name] = val


class ModelSolutions(object):

    def __init__(self, instance):
        self._instance = weakref_ref(instance)
        self.clear()

    def clear(self, clear_symbol_maps=True):
        # _symbol_map: smap_id -> SymbolMap
        if clear_symbol_maps:
            self.symbol_map = {}
        self.solutions = []
        self.index = None

    def __getstate__(self):
        state = {}
        state['index'] = self.index
        state['_instance'] = self._instance()
        solutions = []
        for soln in self.solutions:
            soln_ = {}
            soln_['metadata'] = soln._metadata
            tmp = {}
            for (name, data) in iteritems(soln._entry):
                tmp[name] = {}
                tmp[name].update( (ComponentUID(obj()), entry) for (obj, entry) in itervalues(data) )
            soln_['entry'] = tmp
            solutions.append(soln_)
        state['solutions'] = solutions
        return state
        
    def __setstate__(self, state):
        self.clear()
        self.index = state['index']
        self._instance = weakref_ref(state['_instance'])
        instance = self._instance()
        for soln in state['solutions']:
            soln_ = ModelSolution()
            soln_._metadata = soln['metadata']
            for key,value in iteritems(soln['entry']):
                d = soln_._entry[key]
                for cuid, entry in iteritems(value):
                    obj = cuid.find_component(instance)
                    d[id(obj)] = (obj, entry)
            self.solutions.append(soln_)

    def __len__(self):
        return len(self.solutions)

    def __getitem__(self, index):
        return self.solutions[index]

    def add_symbol_map(self, symbol_map):
        self.symbol_map[id(symbol_map)] = symbol_map

    def delete_symbol_map(self, smap_id):
        if not smap_id is None:
            del self.symbol_map[smap_id]

    def load(self, results,
                allow_consistent_values_for_fixed_vars=False,
                comparison_tolerance_for_fixed_vars=1e-5,
                ignore_invalid_labels=False, 
                id=None,
                delete_symbol_map=True,
                clear=True,
                select=0):
        """
        Load solver results
        """
        instance = self._instance()
        #
        # If there is a warning, then print a warning message.
        #
        if (results.solver.status == pyomo.opt.SolverStatus.warning):
            print('WARNING - Loading a SolverResults object with a ' \
                  'warning status into model=%s' % instance.name)
        #
        # If the solver status not one of either OK or Warning, then generate an error.
        #
        elif results.solver.status != pyomo.opt.SolverStatus.ok:
            if (results.solver.status == pyomo.opt.SolverStatus.aborted) and (len(results.solution) > 0):
               print("WARNING - Loading a SolverResults object with an 'aborted' status, but containing a solution")
            else:
               msg = 'Cannot load a SolverResults object with bad status: %s'
               raise ValueError(msg % str( results.solver.status ))
        if clear:
            #
            # Clear the solutions, but not the symbol map
            #
            self.clear(clear_symbol_maps=False)
        #
        # Load all solutions
        #
        if len(results.solution) == 0:
            return
        smap_id = results.__dict__.get('_smap_id')
        cache = {}
        if not id is None:
            self.add_solution(results.solution(id), smap_id, delete_symbol_map=False, cache=cache, ignore_invalid_labels=ignore_invalid_labels)
        else:
            for i in range(len(results.solution)):
                self.add_solution(results.solution(i), smap_id, delete_symbol_map=False, cache=cache, ignore_invalid_labels=ignore_invalid_labels)
                
        if delete_symbol_map:
            self.delete_symbol_map(smap_id)
        #
        # Load the first solution into the model
        #
        if not select is None:
            self.select(
                select,
                allow_consistent_values_for_fixed_vars=allow_consistent_values_for_fixed_vars,
                comparison_tolerance_for_fixed_vars=comparison_tolerance_for_fixed_vars,
                ignore_invalid_labels=ignore_invalid_labels)

    def store(self, results, cuid=False):
        """
        Return a Solution() object that is populated with the values in the model.
        """
        instance = self._instance()
        results.solution.clear()
        results._smap_id = None

        for soln_ in self.solutions:
            soln = Solution()
            soln._cuid = cuid
            for key, val in iteritems(soln_._metadata):
                setattr(soln, key, val)

            if cuid:
                labeler = CuidLabeler()
            else:
                labeler = CNameLabeler()
            sm = SymbolMap()

            entry = soln_._entry['objective']
            for obj in instance.component_data_objects(Objective, active=True):
                vals = entry.get(id(obj), None)
                if vals is None:
                    vals = {}
                else:
                    vals = vals[1]
                vals['Value'] = value(obj)
                soln.objective[ sm.getSymbol(obj, labeler) ] = vals
            entry = soln_._entry['variable']
            for obj in instance.component_data_objects(Var, active=True):
                if obj.stale:
                    continue
                vals = entry.get(id(obj), None)
                if vals is None:
                    vals = {}
                else:
                    vals = vals[1]
                vals['Value'] = value(obj)
                soln.variable[ sm.getSymbol(obj, labeler) ] = vals
            entry = soln_._entry['constraint']
            for obj in instance.component_data_objects(Constraint, active=True):
                vals = entry.get(id(obj), None)
                if vals is None:
                    continue
                else:
                    vals = vals[1]
                soln.constraint[ sm.getSymbol(obj, labeler) ] = vals
            results.solution.insert( soln )

    def add_solution(self, solution, smap_id, delete_symbol_map=True, cache=None, ignore_invalid_labels=False, ignore_missing_symbols=True):
        instance = self._instance()

        soln = ModelSolution()
        soln._metadata['status'] = solution.status
        if not type(solution.message) is UndefinedData:
            soln._metadata['message'] = solution.message
        if not type(solution.gap) is UndefinedData:
            soln._metadata['gap'] = solution.gap

        if smap_id is None:
            #
            # Cache symbol names, which might be re-used in subsequent calls to add_solution()
            #
            if cache is None:
                cache = {}
            if solution._cuid:
                #
                # Loading a solution with CUID keys
                #
                if len(cache) == 0:
                    for obj in instance.component_data_objects(Var):
                        cache[ComponentUID(obj)] = obj
                    for obj in instance.component_data_objects(Objective, active=True):
                        cache[ComponentUID(obj)] = obj
                    for obj in instance.component_data_objects(Constraint, active=True):
                        cache[ComponentUID(obj)] = obj

                for name in ['problem', 'objective', 'variable', 'constraint']:
                    tmp = soln._entry[name]
                    for cuid, val in iteritems(getattr(solution, name)):
                        obj = cache.get(cuid, None)
                        if obj is None:
                            if ignore_invalid_labels:
                                continue
                            raise RuntimeError("CUID %s is missing from model %s" % (str(cuid), instance.name))
                        tmp[id(obj)] = (weakref_ref(obj), val)
            else:
                #
                # Loading a solution with string keys
                #
                if len(cache) == 0:
                    for obj in instance.component_data_objects(Var):
                        cache[obj.cname(True)] = obj
                    for obj in instance.component_data_objects(Objective, active=True):
                        cache[obj.cname(True)] = obj
                    for obj in instance.component_data_objects(Constraint, active=True):
                        cache[obj.cname(True)] = obj

                for name in ['problem', 'objective', 'variable', 'constraint']:
                    tmp = soln._entry[name]
                    for symb, val in iteritems(getattr(solution, name)):
                        obj = cache.get(symb, None)
                        if obj is None:
                            if ignore_invalid_labels:
                                continue
                            raise RuntimeError("Symbol %s is missing from model %s" % (symb, instance.name))
                        tmp[id(obj)] = (weakref_ref(obj), val)
        else:
            #
            # Map solution
            #
            smap = self.symbol_map[smap_id]
            for name in ['problem', 'objective', 'variable', 'constraint']:
                tmp = soln._entry[name]
                for symb, val in iteritems(getattr(solution, name)):
                    if symb in smap.bySymbol:
                        obj = smap.bySymbol[symb]
                    elif symb in smap.aliases:
                        obj = smap.aliases[symb]
                    elif ignore_missing_symbols:
                        continue
                    else:                                   #pragma:nocover
                        #
                        # This should never happen ...
                        #
                        raise RuntimeError("ERROR: Symbol %s is missing from model %s when loading with a symbol map!" % (symb, instance.name))
                    tmp[id(obj())] = (obj, val)
            #
            # Wrap up
            #
            if delete_symbol_map:
                self.delete_symbol_map(smap_id)

        #
        # Collect fixed variables
        #
        tmp = soln._entry['variable']
        for vdata in instance.component_data_objects(Var):
            if vdata.fixed:
                tmp[id(vdata)] = (weakref_ref(vdata), {'Value':value(vdata)})
                
        self.solutions.append(soln)
        return len(self.solutions)-1

    def select(self, index=0,
                        allow_consistent_values_for_fixed_vars=False,
                        comparison_tolerance_for_fixed_vars=1e-5,
                        ignore_invalid_labels=False,
                        ignore_fixed_vars=False):
        """
        Select a solution from the model's solutions.

	    allow_consistent_values_for_fixed_vars: a flag that
	    indicates whether a solution can specify consistent
	    values for variables in the model that are fixed.

	    ignore_invalid_labels: a flag that indicates whether
	    labels in the solution that don't appear in the model
	    yield an error. This allows for loading a results object
	    generated from one model into another related, but not
	    identical, model.
        """
        instance = self._instance()
        #
        # Set the "stale" flag of each variable in the model prior to loading the
        # solution, so you known which variables have "real" values and which ones don't.
        #
        instance._flag_vars_as_stale()
        if not index is None:
            self.index = index
        soln = self.solutions[self.index]
        #
        # Generate the list of active import suffixes on this top level model
        #
        valid_import_suffixes = dict(active_import_suffix_generator(instance))
        #
        # To ensure that import suffix data gets properly overwritten (e.g.,
        # the case where nonzero dual values exist on the suffix and but only
        # sparse dual values exist in the results object) we clear all active
        # import suffixes.
        #
        for suffix in itervalues(valid_import_suffixes):
            suffix.clearAllValues()
        #
        # Load problem (model) level suffixes. These would only come from ampl
        # interfaced solution suffixes at this point in time.
        #
        for id_, (pobj,entry) in iteritems(soln._entry['problem']):
            for _attr_key, attr_value in iteritems(entry):
                attr_key = _attr_key[0].lower() + _attr_key[1:]
                if attr_key in valid_import_suffixes:
                    valid_import_suffixes[attr_key][pobj] = attr_value
        #
        # Load objective data (suffixes)
        #
        for id_, (odata, entry) in iteritems(soln._entry['objective']):
            odata = odata()
            for _attr_key, attr_value in iteritems(entry):
                attr_key = _attr_key[0].lower() + _attr_key[1:]
                if attr_key in valid_import_suffixes:
                    valid_import_suffixes[attr_key][odata] = attr_value
        #
        # Load variable data (suffixes and values)
        #
        for id_, (vdata, entry) in iteritems(soln._entry['variable']):
            vdata = vdata()
            val = entry['Value']
            if vdata.fixed is True:
                if ignore_fixed_vars:
                    continue
                if not allow_consistent_values_for_fixed_vars:
                    msg = "Variable '%s' in model '%s' is currently fixed - new" \
                          ' value is not expected in solution'
                    raise TypeError(msg % ( vdata.cname(), instance.name ))
                if math.fabs(val - vdata.value) > comparison_tolerance_for_fixed_vars:
                    msg = "Variable '%s' in model '%s' is currently fixed - a value of '%s' in solution is not within tolerance=%s of the current value of '%s'"
                    raise TypeError(msg % ( vdata.cname(), instance.name, str(val), str(comparison_tolerance_for_fixed_vars), str(vdata.value) ))
            vdata.value = val
            vdata.stale = False

            for _attr_key, attr_value in iteritems(entry):
                attr_key = _attr_key[0].lower() + _attr_key[1:]
                if attr_key == 'value':
                    continue
                elif attr_key in valid_import_suffixes:
                    valid_import_suffixes[attr_key][vdata] = attr_value
        #
        # Load constraint data (suffixes)
        #
        for id_, (cdata, entry) in iteritems(soln._entry['constraint']):
            cdata = cdata()
            for _attr_key, attr_value in iteritems(entry):
                attr_key = _attr_key[0].lower() + _attr_key[1:]
                if attr_key in valid_import_suffixes:
                    valid_import_suffixes[attr_key][cdata] = attr_value


class Model(SimpleBlock):
    """
    An optimization model.  By default, this defers construction of components
    until data is loaded.
    """

    preprocessor_ep = ExtensionPoint(IPyomoPresolver)


    def __init__(self, name='unknown', _error=True, **kwargs):
        """Constructor"""
        if _error:
            raise ValueError("Using the 'Model' class is deprecated.  Please use the AbstractModel or ConcreteModel class instead.")
        #
        # NOTE: The 'ctype' keyword argument is not defined here.  Thus,
        # a model is treated as a 'Block' class type.  This simplifies
        # the definition of the block_data_objects() method, since we treat
        # Model and Block objects as the same.  Similarly, this avoids
        # the requirement to import PyomoModel.py in the block.py file.
        #
        SimpleBlock.__init__(self, **kwargs)
        self.name = name
        self.statistics = Container()
        self.config = PyomoConfig()
        self.solutions = ModelSolutions(self)
        self.config.preprocessor = 'pyomo.model.simple_preprocessor'
        self._preprocessed = False

    def model(self):
        #
        # Special case: the "Model" is always the top-level block, so if
        # this is the top-level block, it must be the model
        #
        if self.parent_block() is None:
            return self
        else:
            return super(Model, self).model()

    def compute_statistics(self, recompute=False, active=True):
        """
        Compute model statistics
        """
        if len(self.statistics) > 0:
            return
        self.statistics.number_of_variables = 0
        self.statistics.number_of_constraints = 0
        self.statistics.number_of_objectives = 0
        for block in self.block_data_objects(active=True):
            for data in self.component_map(Var, active=True).itervalues():
                self.statistics.number_of_variables += len(data)
            for data in self.component_map(Objective, active=True).itervalues():
                self.statistics.number_of_objectives += len(data)
            for data in self.component_map(Constraint, active=True).itervalues():
                self.statistics.number_of_constraints += len(data)

    def nvariables(self):
        self.compute_statistics()
        return self.statistics.number_of_variables

    def nconstraints(self):
        self.compute_statistics()
        return self.statistics.number_of_constraints

    def nobjectives(self):
        self.compute_statistics()
        return self.statistics.number_of_objectives

    def valid_problem_types(self):
        """This method allows the pyomo.opt convert function to work with a Model object."""
        return [ProblemFormat.pyomo]

    def create_instance(self, filename=None, **kwargs):
        """
        Create a concrete instance of an abstract model.
        """
        if self._constructed:
            logger.warn("DEPRECATION WARNING: Cannot call Model.create_instance() on a concrete model.")
            return self
        kwargs['filename'] = filename
        functor = kwargs.pop('functor', None)
        if functor is None:
            data = pyomo.util.PyomoAPIFactory(self.config.create_functor)(self.config, model=self, **kwargs)
        else:
            data = pyomo.util.PyomoAPIFactory(functor)(self.config, model=self, **kwargs)
        #
        # Creating a model converts it from Abstract -> Concrete
        #
        data.instance._constructed = True
        return data.instance

    def clone(self):
        instance = SimpleBlock.clone(self)
        # Do not keep cloned solutions, which point to the original model
        instance.solutions.clear()
        instance.solutions._instance = weakref_ref(instance)
        return instance

    def reset(self):
        # TODO: check that this works recursively for nested models
        self._preprocessed = False
        for block in self.block_data_objects():
            for obj in itervalues(block.component_map()):
                obj.reset()

    def preprocess(self, preprocessor=None):
        """Apply the preprocess plugins defined by the user"""
        if True or not self._preprocessed:
            self._preprocessed = True
            suspend_gc = PauseGC()
            if preprocessor is None:
                preprocessor = self.config.preprocessor
            pyomo.util.PyomoAPIFactory(preprocessor)(self.config, model=self)

    def Xstore(self, dp, components, namespace=None):
        for c in components:
            try:
                name = c.cname()
            except:
                name = c
            dp._data.get(namespace,{})[name] = c.data()

    def load(self, arg, namespaces=[None], profile_memory=0, report_timing=False):
        """
        Load the model with data from a file, dictionary or DataPortal object.
        """
        if arg is None or type(arg) is str:
            self._load_model_data(DataPortal(filename=arg,model=self), namespaces, profile_memory=profile_memory, report_timing=report_timing)
            return True
        elif type(arg) is DataPortal:
            self._load_model_data(arg, namespaces, profile_memory=profile_memory, report_timing=report_timing)
            return True
        elif type(arg) is dict:
            self._load_model_data(DataPortal(data_dict=arg,model=self), namespaces, profile_memory=profile_memory, report_timing=report_timing)
            return True
        else:
            msg = "Cannot load model model data from with object of type '%s'"
            raise ValueError(msg % str( type(arg) ))

    def _tuplize(self, data, setobj):
        if data is None:            #pragma:nocover
            return None
        if setobj.dimen == 1:
            return data
        ans = {}
        for key in data:
            if type(data[key][0]) is tuple:
                return data
            ans[key] = tuplize(data[key], setobj.dimen, setobj.name)
        return ans

    def _load_model_data(self, modeldata, namespaces, **kwds):
        """
        Load declarations from a DataPortal object.
        """
        #
        # As we are primarily generating objects here (and acyclic ones
        # at that), there is no need to run the GC until the entire
        # model is created.  Simple reference-counting should be
        # sufficient to keep memory use under control.
        #
        suspend_gc = PauseGC()

        #
        # Unlike the standard method in the pympler summary module, the tracker
        # doesn't print 0-byte entries to pad out the limit.
        #
        profile_memory = kwds.get('profile_memory', 0)

        #
        # It is often useful to report timing results for various activities during model construction.
        #
        report_timing = kwds.get('report_timing', False)

        if (pympler_available is True) and (profile_memory >= 2):
            mem_used = muppy.get_size(muppy.get_objects())
            print("")
            print("      Total memory = %d bytes prior to model construction" % mem_used)

        if (pympler_available is True) and (profile_memory >= 3):
            gc.collect()
            mem_used = muppy.get_size(muppy.get_objects())
            print("      Total memory = %d bytes prior to model construction (after garbage collection)" % mem_used)

        #
        # Do some error checking
        #
        for namespace in namespaces:
            if not namespace is None and not namespace in modeldata._data:
                msg = "Cannot access undefined namespace: '%s'"
                raise IOError(msg % namespace)

        #
        # Initialize each component in order.
        #

        if report_timing is True:
            import pyomo.core.base.expr_coopr3
            construction_start_time = time.time()

        for component_name, component in iteritems(self.component_map()):

            if component.type() is Model:
                continue

            if report_timing is True:
                start_time = time.time()
                clone_counters = (
                    pyomo.core.base.expr_coopr3.generate_expression.clone_counter,
                    pyomo.core.base.expr_coopr3.generate_relational_expression.clone_counter,
                    pyomo.core.base.expr_coopr3.generate_intrinsic_function_expression.clone_counter,
                    )

            self._initialize_component(modeldata, namespaces, component_name, profile_memory)

            if report_timing is True:
                total_time = time.time() - start_time
                comp = self.find_component(component_name)
                if isinstance(comp, IndexedComponent):
                    clen = len(comp)
                else:
                    assert isinstance(comp, Component)
                    clen = 1
                print("    %%6.%df seconds required to construct component=%s; %d indicies total" \
                          % (total_time>=0.005 and 2 or 0, component_name, clen) \
                          % total_time)
                tmp_clone_counters = (
                    pyomo.core.base.expr_coopr3.generate_expression.clone_counter,
                    pyomo.core.base.expr_coopr3.generate_relational_expression.clone_counter,
                    pyomo.core.base.expr_coopr3.generate_intrinsic_function_expression.clone_counter,
                    )
                if clone_counters != tmp_clone_counters:
                    clone_counters = tmp_clone_counters
                    print("             Cloning detected! (clone counters: %d, %d, %d)" % clone_counters)

        # Note: As is, connectors are expanded when using command-line pyomo but not calling model.create(...) in a Python script.
        # John says this has to do with extension points which are called from commandline but not when writing scripts.
        # Uncommenting the next two lines switches this (command-line fails because it tries to expand connectors twice)
        #connector_expander = ConnectorExpander()
        #connector_expander.apply(instance=self)

        if report_timing is True:
            total_construction_time = time.time() - construction_start_time
            print("      %6.2f seconds required to construct instance=%s" % (total_construction_time, self.name))

        if (pympler_available is True) and (profile_memory >= 2):
            print("")
            print("      Summary of objects following instance construction")
            post_construction_summary = summary.summarize(muppy.get_objects())
            summary.print_(post_construction_summary, limit=100)
            print("")

    def _initialize_component(self, modeldata, namespaces, component_name, profile_memory):
        declaration = self.component(component_name)

        if component_name in modeldata._default:
            if declaration.type() is not Set:
                declaration.set_default(modeldata._default[component_name])
        data = None

        for namespace in namespaces:
            if component_name in modeldata._data.get(namespace,{}):
                if declaration.type() is Set:
                    data = self._tuplize(modeldata._data[namespace][component_name],
                                         declaration)
                else:
                    data = modeldata._data[namespace][component_name]
            if not data is None:
                break

        if __debug__ and logger.isEnabledFor(logging.DEBUG):
            _blockName = "Model" if self.parent_block() is None \
                else "Block '%s'" % self.cname(True)
            logger.debug( "Constructing %s '%s' on %s from data=%s",
                          declaration.__class__.__name__,
                          declaration.cname(), _blockName, str(data) )
        try:
            declaration.construct(data)
        except:
            err = sys.exc_info()[1]
            logger.error(
                "Constructing component '%s' from data=%s failed:\n%s: %s",
                str(declaration.cname(True)), str(data).strip(),
                type(err).__name__, err )
            raise

        if __debug__ and logger.isEnabledFor(logging.DEBUG):
                _out = StringIO()
                declaration.pprint(ostream=_out)
                logger.debug("Constructed component '%s':\n%s"
                             % ( declaration.cname(True), _out.getvalue()))

        if (pympler_available is True) and (profile_memory >= 2):
            mem_used = muppy.get_size(muppy.get_objects())
            print("      Total memory = %d bytes following construction of component=%s" % (mem_used, component_name))

        if (pympler_available is True) and (profile_memory >= 3):
            gc.collect()
            mem_used = muppy.get_size(muppy.get_objects())
            print("      Total memory = %d bytes following construction of component=%s (after garbage collection)" % (mem_used, component_name))


    def write(self, filename=None, format=ProblemFormat.cpxlp, solver_capability=None, io_options={}):
        """
        Write the model to a file, with a given format.
        """
        self.preprocess()

        #
        # Guess the format if none is specified
        #
        if format is None and not filename is None:
            format = guess_format(filename)
        problem_writer = pyomo.opt.WriterFactory(format)
        if problem_writer is None:
            raise ValueError(\
                    "Cannot write model in format '%s': no model writer " \
                    "registered for that format" \
                    % str(format))

        if solver_capability is None:
            solver_capability = lambda x: True
        (filename, smap) = problem_writer(self, filename, solver_capability, io_options)
        smap_id = id(smap)
        self.solutions.add_symbol_map(smap)

        if __debug__ and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Writing model '%s' to file '%s' with format %s",
                         self.name,
                         str(filename),
                         str(format))
        return filename, smap_id

    def create(self, filename=None, **kwargs):
        """
        Create a concrete instance of this Model, possibly using data
        read in from a file.
        """
        logger.warn("DEPRECATION WARNING: the Model.create() method is deprecated.  Call Model.create_instance() if to create a concrete model from an abstract model.  You do not need to call Model.create() for a concrete model.")
        return self.create_instance(filename=filename, **kwargs)

    def transform(self, name=None, **kwds):
        logger.warn("DEPRECATION WARNING: This method has been removed.  Use the TransformationFactory to construct a transformation object.")
        if name is None:
            return TransformationFactory.services()
        xfrm = TransformationFactory(name)
        if xfrm is None:
            raise ValueError("Bad model transformation '%s'" % name)
        return xfrm(self, **kwds)


class ConcreteModel(Model):
    """
    A concrete optimization model that does not defer construction of
    components.
    """

    def __init__(self, *args, **kwds):
        kwds['_error'] = False
        kwds['concrete'] = True
        Model.__init__(self, *args, **kwds)
        self.config.create_functor = 'pyomo.model.default_constructor'


class AbstractModel(Model):
    """
    An abstract optimization model that defers construction of
    components.
    """

    def __init__(self, *args, **kwds):
        kwds['_error'] = False
        Model.__init__(self, *args, **kwds)
        self.config.create_functor = 'pyomo.model.default_constructor'



@pyomo_api(namespace='pyomo.model')
def default_constructor(data, model=None, filename=None, data_dict={}, name=None, namespace=None, namespaces=None, preprocess=True, profile_memory=0, report_timing=False, clone=None):
    """
    Create a concrete instance of this Model, possibly using data
    read in from a file.

    Required:
        model:              An AbstractModel object.

    Optional:
        filename:           The name of a Pyomo Data File that will be used to load
                                data into the model.
        data_dict:          A dictionary containing initialization data for the model
                                to be used if there is no filename
        name:               The name given to the model.
        namespace:          A namespace used to select data.
        namespaces:         A list of namespaces used to select data.
        preprocess:         If False, then preprocessing is suppressed.
        profile_memory:     A number that indicates the profiling level.
        report_timing:      Report timing statistics during construction.
        clone:              Force a clone of the model if this is True.

    Return:
        instance:           Return the model that is constructed.
    """
    if name is None:
        name = model.name
    #
    # Generate a warning if this is a concrete model but the filename is specified.
    # A concrete model is already constructed, so passing in a data file is a waste
    # of time.
    #
    if model.is_constructed() and isinstance(filename,basestring):
        msg = "The filename=%s will not be loaded - supplied as an argument to the create() method of a ConcreteModel instance with name=%s." % (filename, name)
        logger.warning(msg)
    #
    # If construction is deferred, then clone the model and
    #
    if not model._constructed:
        instance = model.clone()

        if namespaces is None or len(namespaces) == 0:
            if filename is None:
                instance.load(data_dict, namespaces=[None], profile_memory=profile_memory, report_timing=report_timing)
            else:
                instance.load(filename, namespaces=[None], profile_memory=profile_memory, report_timing=report_timing)
        else:
            if filename is None:
                instance.load(data_dict, namespaces=namespaces+[None], profile_memory=profile_memory, report_timing=report_timing)
            else:
                instance.load(filename, namespaces=namespaces+[None], profile_memory=profile_memory, report_timing=report_timing)
    else:
        if clone:
            instance = model.clone()
        else:
            instance = model
    #
    # Preprocess the new model
    #
    if preprocess is True:

        if report_timing is True:
            start_time = time.time()

        instance.preprocess()

        if report_timing is True:
            total_time = time.time() - start_time
            print("      %6.2f seconds required for preprocessing" % total_time)

        if (pympler_available is True) and (profile_memory >= 2):
            mem_used = muppy.get_size(muppy.get_objects())
            print("      Total memory = %d bytes following instance preprocessing" % mem_used)
            print("")

        if (pympler_available is True) and (profile_memory >= 2):
            print("")
            print("      Summary of objects following instance preprocessing")
            post_preprocessing_summary = summary.summarize(muppy.get_objects())
            summary.print_(post_preprocessing_summary, limit=100)

    if not name is None:
        instance.name=name

    return Bunch(instance=instance)


register_component(Model, 'Model objects can be used as a component of other models.')
register_component(ConcreteModel, 'A concrete optimization model that does not defer construction of components.')
register_component(AbstractModel, 'An abstract optimization model that defers construction of components.')

