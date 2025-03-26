"""The abstract values used by typegraphvm.

An abstract value in effect represents a type. Groups of types are
combined using typegraph and that is what we compute over.
"""

# Because of false positives:
# pylint: disable=unpacking-non-sequence
# pylint: disable=abstract-method
# pytype: disable=attribute-error

import collections
import hashlib
import itertools
import logging


from pytype import exceptions
from pytype import function
from pytype import mro
from pytype import output
from pytype import utils
from pytype.pyc import loadmarshal
from pytype.pytd import cfg as typegraph
from pytype.pytd import pep484
from pytype.pytd import pytd
from pytype.pytd import utils as pytd_utils
from pytype.pytd.parse import visitors

log = logging.getLogger(__name__)
chain = itertools.chain  # pylint: disable=invalid-name
WrapsDict = pytd_utils.WrapsDict  # pylint: disable=invalid-name


class ConversionError(ValueError):
  pass


class AsInstance(object):
  """Wrapper, used for marking things that we want to convert to an instance."""

  def __init__(self, cls):
    self.cls = cls


def variable_set_official_name(variable, name):
  """Set official_name on each value in the variable.

  Called for each entry in the top-level locals().

  Args:
    variable: A typegraph.Variable to name.
    name: The name to give.
  """
  for v in variable.bindings:
    v.data.official_name = name


def get_atomic_value(variable):
  if len(variable.bindings) == 1:
    return variable.bindings[0].data
  else:
    raise ConversionError(
        "Variable with too many options when trying to get atomic value. %s %s"
        % (variable, [a.data for a in variable.bindings]))


def get_atomic_python_constant(variable):
  """Get the concrete atomic Python value stored in this variable.

  This is used for things that are stored in typegraph.Variable, but we
  need the actual data in order to proceed. E.g. function / class defintions.

  Args:
    variable: A typegraph.Variable. It can only have one possible value.
  Returns:
    A Python constant. (Typically, a string, a tuple, or a code object.)
  Raises:
    ValueError: If the value in this Variable is purely abstract, i.e. doesn't
      store a Python value, or if it has more than one possible value.
    IndexError: If there is more than one possibility for this value.
  """
  atomic = get_atomic_value(variable)
  if isinstance(atomic, PythonConstant):
    return atomic.pyval
  raise ConversionError("Only some types are supported: %r" % type(atomic))


class AtomicAbstractValue(object):
  """A single abstract value such as a type or function signature.

  This is the base class of the things that appear in Variables. It represents
  an atomic object that the abstract interpreter works over just as variables
  represent sets of parallel options.

  Conceptually abstract values represent sets of possible concrete values in
  compact form. For instance, an abstract value with .__class__ = int represents
  all ints.
  """

  _value_id = 0  # for pretty-printing
  formal = False  # is this type non-instantiable?

  def __init__(self, name, vm):
    """Basic initializer for all AtomicAbstractValues."""
    assert hasattr(vm, "program"), type(self)
    self.vm = vm
    self.mro = []
    self.cls = None
    AtomicAbstractValue._value_id += 1
    self.id = AtomicAbstractValue._value_id
    self.name = name
    self.module = None
    self.official_name = None

  @property
  def full_name(self):
    return (self.module + "." if self.module else "") + self.name

  def __repr__(self):
    return self.name

  def default_mro(self):
    return [self, self.vm.convert.object_type.data[0]]

  def get_fullhash(self):
    """Hash this value and all of its children."""
    m = hashlib.md5()
    seen_ids = set()
    stack = [self]
    while stack:
      data = stack.pop()
      data_id = id(data)
      if data_id in seen_ids:
        continue
      seen_ids.add(data_id)
      m.update(str(data_id))
      for mapping in data.get_children_maps():
        m.update(str(mapping.changestamp))
        stack.extend(mapping.data)
    return m.digest()

  def get_children_maps(self):
    """Get this value's dictionaries of children.

    Returns:
      A sequence of dictionaries from names to child values.
    """
    return ()

  def get_type_parameter(self, node, name):
    return self.vm.convert.create_new_unsolvable(node, name)

  def property_get(self, callself, callcls):  # pylint: disable=unused-argument
    """Bind this value to the given self and class.

    This function is similar to __get__ except at the abstract level. This does
    not trigger any code execution inside the VM. See __get__ for more details.

    Args:
      callself: The Variable that should be passed as self when the call is
        made. None if this is class call.
      callcls: The Variable that should be used as the class when the call is
        made.

    Returns:
      Another abstract value that should be returned in place of this one. The
      default implementation returns self, so this can always be called safely.
    """
    return self

  def get_special_attribute(self, unused_node, unused_name):
    """Fetch a special attribute (e.g., __get__, __iter__)."""
    return None

  def call(self, node, func, args, condition=None):
    """Call this abstract value with the given arguments.

    The posargs and namedargs arguments may be modified by this function.

    Args:
      node: The CFGNode calling this function
      func: The typegraph.Binding containing this function.
      args: Arguments for the call.
      condition: The currently active if-condition.
    Returns:
      A tuple (cfg.Node, typegraph.Variable). The CFGNode corresponds
      to the function's "return" statement(s).
    Raises:
      FailedFunctionCall

    Make the call as required by this specific kind of atomic value, and make
    sure to annotate the results correctly with the origins (val and also other
    values appearing in the arguments).
    """
    raise NotImplementedError

  def is_closure(self):
    """Return whether this is a closure. Overridden by subclasses.

    This can only return True for InterpreterFunction and NativeFunction
    (i.e., at the time of this writing, never for functions e.g. from PYTD,
    which doesn't know about closures), and only if they bind variables from
    their outer scope. Inner functions not binding anything are not considered a
    closure.

    Returns:
      True if this is a closure.
    """
    return False

  def register_instance(self, instance):  # pylint: disable=unused-arg
    """Treating self as a class definition, register an instance of it.

    This is used for keeping merging call records on instances when generating
    the formal definition of a class.

    Args:
      instance: An instance of this class (as an AtomicAbstractValue)
    """
    pass  # Only InterpreterClass needs this, others can ignore it.

  def get_class(self):
    """Return the class of this object. Equivalent of x.__class__ in Python."""
    raise NotImplementedError(self.__class__.__name__)

  def get_instance_type(self, node, instance=None, seen=None):
    """Return the type an instance of us would have."""
    # We don't know whether we even *are* a type, so the default is anything.
    del node, instance, seen
    return pytd.AnythingType()

  def to_type(self, node, seen=None):
    """Get a PyTD type representing this object, as seen at a node."""
    raise NotImplementedError(self.__class__.__name__)

  def get_default_type_key(self):
    """Gets a default type key. See get_type_key."""
    return type(self)

  def get_type_key(self, seen=None):  # pylint: disable=unused-argument
    """Build a key from the information used to perform type matching.

    Get a hashable object containing this value's type information. Type keys
    are only compared amongst themselves, so we don't care what the internals
    look like, only that values with different types *always* have different
    type keys and values with the same type preferably have the same type key.

    Args:
      seen: The set of values seen before while computing the type key.

    Returns:
      A hashable object built from this value's type information.
    """
    return self.get_default_type_key()

  def instantiate(self, node):
    return Instance(self.to_variable(node, self.name),
                    self.vm, node).to_variable(node, self.name)

  def to_variable(self, node, name=None):
    """Build a variable out of this abstract value.

    Args:
      node: The current CFG node.
      name: The name to give the new variable.
    Returns:
      A typegraph.Variable.
    Raises:
      ValueError: If origins is an empty sequence. This is to prevent you from
        creating variables that have no origin and hence can never be used.
    """
    v = self.vm.program.NewVariable(name or self.name)
    v.AddBinding(self, source_set=[], where=node)
    return v

  def has_varargs(self):
    """Return True if this is a function and has a *args parameter."""
    return False

  def has_kwargs(self):
    """Return True if this is a function and has a **kwargs parameter."""
    return False

  def unique_parameter_values(self):
    return []

  def compatible_with(self, logical_value):  # pylint: disable=unused-argument
    """Returns the conditions under which the value could be True or False.

    Args:
      logical_value: Either True or False.

    Returns:
      False: If the value could not evaluate to logical_value under any
          circumstance (i.e. value is the empty list and logical_value is True).
      True: If it is possible for the value to evaluate to the logical_value,
          and any ambiguity cannot be described by additional bindings.
      DNF: A list of lists of bindings under which the value can evaluate to
          the logical value.  For example, isinstance() could be reduced
          to the set of bindings that would satisfy th isinstance() condition.
    """
    # By default a value is ambiguous - if could potentially evaluate to
    # either True or False, thus we return True here regardless of
    # logical_value.
    return True


class Empty(AtomicAbstractValue):
  """An empty value.

  These values represent items extracted from empty containers. Because of false
  positives in flagging containers as empty (consider:
    x = []
    def initialize():
      populate(x)
    def f():
      iterate(x)
  ), we treat these values as placeholders that we can do anything with, similar
  to Unsolvable, with the difference that they eventually convert to
  NothingType so that cases in which they are truly empty are discarded (see:
    x = ...  # type: List[nothing] or Dict[int, str]
    y = [i for i in x]  # The type of i is int; y is List[int]
  ). On the other hand, if Empty is the sole type candidate, we assume that the
  container was populated elsewhere:
    x = []
    def initialize():
      populate(x)
    def f():
      return x[0]  # Oops! The return type should be Any rather than nothing.
  The nothing -> anything conversion happens in InterpreterFunction.to_pytd_def
  and infer.CallTracer.pytd_for_types.
  """

  def __init__(self, vm):
    super(Empty, self).__init__("empty", vm)

  def to_type(self, node, seen=None):
    return pytd.NothingType()

  def get_instance_type(self, node, instance=None, seen=None):
    return pytd.AnythingType()

  def get_special_attribute(self, node, name):
    return self.vm.convert.unsolvable.to_variable(node, name)

  def call(self, node, func, args, condition=None):
    del func, args
    return node, self.vm.convert.unsolvable.to_variable(node, self.name)

  def get_class(self):
    return self.vm.convert.unsolvable.to_variable(
        self.vm.root_cfg_node, self.name)


class PythonConstant(object):
  """A mix-in for storing actual Python constants, not just their types.

  This is used for things that are stored in typegraph.Variable, but where we
  may need the actual data in order to proceed later. E.g. function / class
  definitions, tuples. Also, potentially: Small integers, strings (E.g. "w",
  "r" etc.).
  """

  def init_mixin(self, pyval):
    """Mix-in equivalent of __init__."""
    self.pyval = pyval


class TypeParameter(AtomicAbstractValue):
  """Parameter of a type.

  Attributes:
    name: Type parameter name
  """

  formal = True

  def __init__(self, name, vm):
    super(TypeParameter, self).__init__(name, vm)

  def __repr__(self):
    return "TypeParameter(%r)" % self.name


class TypeParameterInstance(AtomicAbstractValue):
  """An instance of a type parameter."""

  def __init__(self, name, instance, vm):
    super(TypeParameterInstance, self).__init__(name, vm)
    self.instance = instance

  def to_type(self, node, seen=None):
    if (self.name in self.instance.type_parameters and
        self.instance.type_parameters[self.name].bindings):
      return pytd_utils.JoinTypes(t.to_type(
          node, seen) for t in self.instance.type_parameters[self.name].data)
    else:
      # The type parameter was never initialized
      return pytd.AnythingType()


class SimpleAbstractValue(AtomicAbstractValue):
  """A basic abstract value that represents instances.

  This class implements instances in the Python sense. Instances of the same
  class may vary.

  Note that the cls attribute will point to another abstract value that
  represents the class object itself, not to some special type representation.
  """
  is_lazy = False

  def __init__(self, name, vm):
    """Initialize a SimpleAbstractValue.

    Args:
      name: Name of this value. For debugging and error reporting.
      vm: The TypegraphVirtualMachine to use.
    """
    super(SimpleAbstractValue, self).__init__(name, vm)
    self.members = utils.MonitorDict()
    self.type_parameters = utils.LazyAliasingMonitorDict()

  def get_children_maps(self):
    return (self.type_parameters, self.members)

  def get_type_parameter(self, node, name):
    """Get the typegraph.Variable representing the type parameter of self.

    This will be a typegraph.Variable made up of values that have been used in
    place of this type parameter.

    Args:
      node: The current CFG node.
      name: The name of the type parameter.
    Returns:
      A Variable which may be empty.
    """
    param = self.type_parameters.get(name)
    if not param:
      log.info("Creating new empty type param %s", name)
      param = self.vm.program.NewVariable(name, [], [], node)
      self.type_parameters[name] = param
    return param

  def merge_type_parameter(self, node, name, value):
    """Set the value of a type parameter.

    This will always add to the type_parameter unlike set_attribute which will
    replace value from the same basic block. This is because type parameters may
    be affected by a side effect so we need to collect all the information
    regardless of multiple assignments in one basic block.

    Args:
      node: The current CFG node.
      name: The name of the type parameter.
      value: The value that is being used for this type parameter as a Variable.
    """
    log.info("Modifying type param %s", name)
    if name in self.type_parameters:
      self.type_parameters[name].PasteVariable(value, node)
    else:
      self.type_parameters[name] = value

  # TODO(kramm): remove
  def overwrite_type_parameter(self, node, name, value):
    """Overwrite the value of a type parameter.

    Unlike merge_type_parameter, this will purge the previous value and set
    the type parameter only to the new value.

    Args:
      node: The current CFG node.
      name: The name of the type parameter.
      value: The new type parameter as a Variable.
    """
    log.info("Overwriting type param %s", name)
    self.type_parameters[name] = self.vm.program.NewVariable(
        name, value.data, [], node)

  def initialize_type_parameter(self, node, name, value):
    assert isinstance(name, str)
    log.info("Initializing type param %s: %r", name, value.data)
    self.type_parameters[name] = self.vm.program.NewVariable(
        name, value.data, [], node)

  def init_type_parameters(self, *names):
    """Initialize the named type parameters to nothing (empty)."""
    self.type_parameters = utils.LazyAliasingMonitorDict(
        (name, self.vm.program.NewVariable("empty")) for name in names)

  def load_lazy_attribute(self, name):
    """Load the named attribute into self.members."""
    if name not in self.members and name in self._member_map:
      variable = self._convert_member(name, self._member_map[name])
      assert isinstance(variable, typegraph.Variable)
      self.members[name] = variable

  def load_special_attribute(self, node, name):
    if name == "__class__" and self.cls is not None:
      return node, self.cls
    else:
      return node, None

  def call(self, node, _, args, condition=None):
    self_var = self.to_variable(node, self.name)
    node, var = self.vm.attribute_handler.get_attribute(
        node, self, "__call__", self_var.bindings[0])
    if var is not None and var.bindings:
      return self.vm.call_function(
          node, var, args.replace(posargs=(self_var,) + args.posargs),
          condition=condition)
    else:
      raise NotCallable(self)

  def __repr__(self):
    if self.cls:
      cls = self.cls.data[0]
      return "<v%d %s [%r]>" % (self.id, self.name, cls)
    else:
      return "<v%d %s>" % (self.id, self.name)

  def to_variable(self, node, name=None):
    return super(SimpleAbstractValue, self).to_variable(node, name or self.name)

  def get_class(self):
    # See Py_TYPE() in Include/object.h
    if self.cls:
      return self.cls
    elif isinstance(self, Class):
      return self.vm.convert.type_type

  def set_class(self, node, var):
    """Set the __class__ of an instance, for code that does "x.__class__ = y."""
    if self.cls:
      self.cls.PasteVariable(var, node)
    else:
      self.cls = var
    for cls in var.data:
      cls.register_instance(self)
    return node

  def to_type(self, node, seen=None):
    """Get a PyTD type representing this object, as seen at a node.

    This uses both the instance (for type parameters) as well as the class.

    Args:
      node: The node from which we want to observe this object.
      seen: The set of values seen before while computing the type.

    Returns:
      A PyTD Type
    """
    if self.cls:
      classvalues = (v.data for v in self.cls.bindings)
      types = []
      for cls in classvalues:
        types.append(cls.get_instance_type(node, self, seen=seen))
      ret = pytd_utils.JoinTypes(types)
      visitors.InPlaceFillInClasses(ret, self.vm.loader.builtins)
      return ret
    else:
      # We don't know this type's __class__, so return AnythingType to indicate
      # that we don't know anything about what this is.
      # This happens e.g. for locals / globals, which are returned from the code
      # in class declarations.
      log.info("Using ? for %s", self.name)
      return pytd.AnythingType()

  def get_type_key(self, seen=None):
    if not seen:
      seen = set()
    seen.add(self)
    key = set()
    if self.cls:
      key.update(self.cls.data)
    for name, var in self.type_parameters.items():
      subkey = frozenset(value.data.get_default_type_key() if value.data in seen
                         else value.data.get_type_key(seen)
                         for value in var.bindings)
      key.add((name, subkey))
    if key:
      return frozenset(key)
    else:
      return super(SimpleAbstractValue, self).get_type_key()

  def unique_parameter_values(self):
    """Get unique parameter subtypes as Values.

    This will retrieve 'children' of this value that contribute to the
    type of it. So it will retrieve type parameters, but not attributes. To
    keep the number of possible combinations reasonable, when we encounter
    multiple instances of the same type, we include only one.

    Returns:
      A list of list of Values.
    """
    parameters = self.type_parameters.values()
    clsvar = self.get_class()
    if clsvar:
      parameters.append(clsvar)
    # TODO(rechen): Remember which values were merged under which type keys so
    # we don't have to recompute this information in match_value_against_type.
    return [{value.data.get_type_key(): value
             for value in parameter.bindings}.values()
            for parameter in parameters]


class Instance(SimpleAbstractValue):
  """An instance of some object."""

  # Fully qualified names of types that are parameterized containers.
  _CONTAINER_NAMES = set([
      "__builtin__.list", "__builtin__.set", "__builtin__.frozenset"])

  def __init__(self, clsvar, vm, node):
    super(Instance, self).__init__(clsvar.data[0].name, vm)
    self.cls = clsvar
    for cls in clsvar.data:
      cls.register_instance(self)
      for base in cls.mro:
        if isinstance(base, ParameterizedClass):
          for name, param in base.type_parameters.items():
            if not param.formal:
              # We inherit from a ParameterizedClass with a non-formal
              # parameter, e.g., class Foo(List[int]). Initialize the
              # corresponding instance parameter appropriately.
              assert name not in self.type_parameters
              self.type_parameters.add_lazy_item(
                  name, param.instantiate, node)
            elif name != param.name:
              # We have type parameter renaming, e.g.,
              #  class List(Generic[T]): pass
              #  class Foo(List[U]): pass
              self.type_parameters.add_alias(name, param.name)

  def __str__(self):
    if self.cls:
      cls = self.cls.data[0]
      return "<instance of %s>" % cls.name
    else:
      return "<instance>"

  def make_template_unsolvable(self, template, node):
    for formal in template:
      self.initialize_type_parameter(
          node, formal.name, self.vm.convert.unsolvable.to_variable(
              node, formal.name))

  def compatible_with(self, logical_value):  # pylint: disable=unused-argument
    # Containers with unset parameters and NoneType instances cannot match True.
    name = self._get_full_name()
    if logical_value and name in Instance._CONTAINER_NAMES:
      return bool(self.type_parameters["T"].bindings)
    elif name == "__builtin__.NoneType":
      return not logical_value
    return True

  def _get_full_name(self):
    try:
      return get_atomic_value(self.get_class()).full_name
    except ConversionError:
      return None


class ValueWithSlots(Instance):
  """Convenience class for overriding slots with custom methods.

  This makes it easier to emulate built-in classes like dict which need special
  handling of some magic methods (__setitem__ etc.)
  """

  def __init__(self, clsvar, vm, node):
    super(ValueWithSlots, self).__init__(clsvar, vm, node)
    self._slots = {}
    self._super = {}
    self._function_cache = {}

  def make_native_function(self, name, method):
    key = (name, method)
    if key not in self._function_cache:
      self._function_cache[key] = NativeFunction(name, method, self.vm,
                                                 self.vm.root_cfg_node)
    return self._function_cache[key]

  def set_slot(self, name, method):
    """Add a new slot to this value."""
    assert name not in self._slots, "slot %s already occupied" % name
    f = self.make_native_function(name, method)
    self._slots[name] = f.to_variable(self.vm.root_cfg_node, name)
    _, attr = self.vm.attribute_handler.get_instance_attribute(
        self.vm.root_cfg_node, self, name,
        self.to_variable(self.vm.root_cfg_node).bindings[0])
    self._super[name] = attr

  def call_pytd(self, node, name, *args):
    """Call the (original) pytd version of a method we overwrote."""
    return self.vm.call_function(node, self._super[name], FunctionArgs(args))

  def get_special_attribute(self, _, name):
    if name in self._slots:
      return self._slots[name]


class Dict(ValueWithSlots, WrapsDict("_entries")):
  """Representation of Python 'dict' objects.

  It works like __builtins__.dict, except that, for string keys, it keeps track
  of what got stored.
  """

  # These match __builtins__.pytd:
  KEY_TYPE_PARAM = "K"
  VALUE_TYPE_PARAM = "V"

  def __init__(self, name, vm, node):
    super(Dict, self).__init__(vm.convert.dict_type, vm, node)
    self.name = name
    self._entries = {}
    self.set_slot("__getitem__", self.getitem_slot)
    self.set_slot("__setitem__", self.setitem_slot)
    self.init_type_parameters(self.KEY_TYPE_PARAM, self.VALUE_TYPE_PARAM)
    self.could_contain_anything = False

  def getitem_slot(self, node, name_var):
    """Implements the __getitem__ slot."""
    results = []
    unresolved = False
    if not self.could_contain_anything:
      for val in name_var.bindings:
        try:
          name = self.vm.convert.convert_value_to_string(val.data)
        except ValueError:  # ConversionError
          unresolved = True
        else:
          try:
            results.append(self._entries[name])
          except KeyError:
            self.vm.errorlog.key_error(self.vm.frame.current_opcode, name)
            unresolved = True
    if unresolved or self.could_contain_anything:
      # We *do* know the overall type of the values through the "V" type
      # parameter, even if we don't know the exact type of self[name]:
      results.append(self.get_type_parameter(node, "V"))
    # For call tracing only, we don't actually use the return value:
    node, _ = self.call_pytd(node, "__getitem__", name_var)
    return node, self.vm.join_variables(
        node, "getitem[var%s]" % name_var.id, results)

  def set_str_item(self, node, name, value_var):
    self.merge_type_parameter(
        node, self.KEY_TYPE_PARAM, self.vm.convert.build_string(node, name))
    self.merge_type_parameter(
        node, self.VALUE_TYPE_PARAM, value_var)
    if name in self._entries:
      self._entries[name].PasteVariable(value_var, node)
    else:
      self._entries[name] = value_var
    return node

  def setitem(self, node, name_var, value_var):
    assert isinstance(name_var, typegraph.Variable)
    assert isinstance(value_var, typegraph.Variable)
    for val in name_var.bindings:
      try:
        name = self.vm.convert.convert_value_to_string(val.data)
      except ValueError:  # ConversionError
        # Now the dictionary is abstract: We don't know what it contains
        # anymore. Note that the below is not a variable, so it'll affect
        # all branches.
        self.could_contain_anything = True
        continue
      if name in self._entries:
        self._entries[name].PasteVariable(value_var, node)
      else:
        self._entries[name] = value_var

  def setitem_slot(self, node, name_var, value_var):
    """Implements the __setitem__ slot."""
    self.setitem(node, name_var, value_var)
    return self.call_pytd(node, "__setitem__", name_var, value_var)

  def update(self, node, other_dict, omit=()):
    self.could_contain_anything = True
    if isinstance(other_dict, (Dict, dict)):
      for key, value in other_dict.items():
        # TODO(kramm): sources
        if key not in omit:
          self.set_str_item(node, key, value)
      if isinstance(other_dict, Dict):
        k = other_dict.get_type_parameter(node, self.KEY_TYPE_PARAM)
        v = other_dict.get_type_parameter(node, self.VALUE_TYPE_PARAM)
        self.merge_type_parameter(node, self.KEY_TYPE_PARAM, k)
        self.merge_type_parameter(node, self.VALUE_TYPE_PARAM, v)
      return True
    else:
      assert isinstance(other_dict, AtomicAbstractValue)
      return False

  def compatible_with(self, logical_value):
    # Always compatible with False.  Compatible with True only if type
    # parameters have been established (meaning that the dict can be
    # non-empty).
    return (not logical_value or
            bool(self.type_parameters[self.KEY_TYPE_PARAM].bindings))


class AbstractOrConcreteValue(Instance, PythonConstant):
  """Abstract value with a concrete fallback."""

  def __init__(self, pyval, clsvar, vm, node):
    super(AbstractOrConcreteValue, self).__init__(clsvar, vm, node)
    PythonConstant.init_mixin(self, pyval)

  def compatible_with(self, logical_value):
    return bool(self.pyval) == logical_value


class LazyAbstractOrConcreteValue(SimpleAbstractValue, PythonConstant):
  """Lazy abstract value with a concrete fallback."""

  is_lazy = True  # uses _convert_member

  def __init__(self, name, pyval, member_map, resolver, vm):
    SimpleAbstractValue.__init__(self, name, vm)
    self._member_map = member_map
    self._resolver = resolver
    PythonConstant.init_mixin(self, pyval)

  def _convert_member(self, name, pyval):
    return self._resolver(name, pyval)

  def compatible_with(self, logical_value):
    return bool(self.pyval) == logical_value


# TODO(rechen): Merge this class with pytype.typing.Union.
class Union(AtomicAbstractValue):
  """A list of types. Used for parameter matching.

  Attributes:
    options: Iterable of instances of AtomicAbstractValue.
  """

  def __init__(self, options, vm):
    super(Union, self).__init__("Union", vm)
    self.name = "Union[%s]" % ", ".join(sorted([str(t) for t in options]))
    self.options = options
    # TODO(rechen): Don't allow a mix of formal and non-formal types
    self.formal = any(t.formal for t in options)

  def instantiate(self, node):
    var = self.vm.program.NewVariable(self.name)
    for option in self.options:
      var.PasteVariable(option.instantiate(node), node)
    return var

  def to_type(self, node, seen=None):
    return pytd.UnionType(tuple(t.to_type(node, seen) for t in self.options))


class FunctionArgs(collections.namedtuple("_", ["posargs", "namedargs",
                                                "starargs", "starstarargs"])):
  """Represents the parameters of a function call."""

  def __new__(cls, posargs, namedargs=None, starargs=None, starstarargs=None):
    """Create arguments for a function under analysis.

    Args:
      posargs: The positional arguments. A tuple of typegraph.Variable.
      namedargs: The keyword arguments. A dictionary, mapping strings to
        typegraph.Variable.
      starargs: The *args parameter, or None.
      starstarargs: The **kwargs parameter, or None.
    Returns:
      A FunctionArgs instance.
    """
    assert isinstance(posargs, tuple), posargs
    cls.replace = cls._replace
    return super(FunctionArgs, cls).__new__(
        cls, posargs=posargs, namedargs=namedargs or {}, starargs=starargs,
        starstarargs=starstarargs)

  def starargs_as_tuple(self):
    try:
      args = self.starargs and get_atomic_python_constant(self.starargs)
      if isinstance(args, tuple):
        return args
    except ConversionError:
      pass
    return None

  def starstarargs_as_dict(self):
    try:
      kws = self.starstarargs and get_atomic_value(self.starstarargs)
      if isinstance(kws, Dict):
        return kws
    except ConversionError:
      pass
    return None

  def simplify(self, node):
    """Try to insert part of *args, **kwargs into posargs / namedargs."""
    posargs = self.posargs
    namedargs = self.namedargs
    starargs = self.starargs
    starstarargs = self.starstarargs
    starargs_as_tuple = self.starargs_as_tuple()
    if starargs_as_tuple is not None:
      posargs += starargs_as_tuple
      starargs = None
    starstarargs_as_dict = self.starstarargs_as_dict()
    if starstarargs_as_dict is not None:
      if namedargs is None:
        namedargs = starstarargs_as_dict
      else:
        namedargs.update(node, starstarargs_as_dict)
      starstarargs = None
    return FunctionArgs(posargs, namedargs, starargs, starstarargs)


class FailedFunctionCall(Exception):
  """Exception for failed function calls."""


class NotCallable(FailedFunctionCall):
  """For objects that don't have __call__."""

  def __init__(self, obj):
    super(NotCallable, self).__init__()
    self.obj = obj


BadCall = collections.namedtuple("_", ["sig", "passed_args"])


class InvalidParameters(FailedFunctionCall):
  """Exception for functions called with an incorrect parameter combination."""

  def __init__(self, sig, passed_args):
    super(InvalidParameters, self).__init__()
    self.name = sig.name
    self.bad_call = BadCall(sig=sig, passed_args=passed_args)


class WrongArgTypes(InvalidParameters):
  """For functions that were called with the wrong types."""
  pass


class WrongArgCount(InvalidParameters):
  """E.g. if a function expecting 4 parameters is called with 3."""
  pass


class WrongKeywordArgs(InvalidParameters):
  """E.g. an arg "x" is passed to a function that doesn't have an "x" param."""

  def __init__(self, sig, passed_args, extra_keywords):
    super(WrongKeywordArgs, self).__init__(sig, passed_args)
    self.extra_keywords = tuple(extra_keywords)


class DuplicateKeyword(InvalidParameters):
  """E.g. an arg "x" is passed to a function as both a posarg and a kwarg."""

  def __init__(self, sig, passed_args, duplicate):
    super(DuplicateKeyword, self).__init__(sig, passed_args)
    self.duplicate = duplicate


class MissingParameter(InvalidParameters):
  """E.g. a function requires parameter 'x' but 'x' isn't passed."""

  def __init__(self, sig, passed_args, missing_parameter):
    super(MissingParameter, self).__init__(sig, passed_args)
    self.missing_parameter = missing_parameter


class SuperInstance(AtomicAbstractValue):
  """The result of a super() call, i.e., a lookup proxy."""

  def __init__(self, cls, obj, vm):
    super(SuperInstance, self).__init__("super", vm)
    self.cls = self.vm.convert.super_type
    self.super_cls = cls
    self.super_obj = obj
    self.get = NativeFunction(
        "__get__", self.get, self.vm, self.vm.root_cfg_node)
    self.set = NativeFunction(
        "__set__", self.set, self.vm, self.vm.root_cfg_node)

  def get(self, node, *unused_args, **unused_kwargs):
    return node, self.to_variable(node, "get")

  def set(self, node, *unused_args, **unused_kwargs):
    return node, self.to_variable(node, "set")

  def get_special_attribute(self, node, name):
    if name == "__get__":
      return self.get.to_variable(node, name)
    elif name == "__set__":
      return self.set.to_variable(node, name)

  def to_type(self, node, seen=None):
    return pytd.NamedType("__builtin__.super")

  def get_class(self):
    return self.cls

  def call(self, node, _, args, condition=None):
    self.vm.errorlog.not_callable(
        self.vm.frame.current_opcode, self)
    return node, Unsolvable(self.vm).to_variable(node)


class Super(AtomicAbstractValue):
  """The super() function. Calling it will create a SuperInstance."""

  # Minimal signature, only used for constructing exceptions.
  _SIGNATURE = function.Signature(
      "super", ("cls", "self"), None, set(), None, {}, {"return": None}, {})

  def __init__(self, vm):
    super(Super, self).__init__("super", vm)

  def call(self, node, _, args, condition=None):
    result = self.vm.program.NewVariable("super")
    if len(args.posargs) == 1:
      # TODO(kramm): Add a test for this
      for cls in args.posargs[0].bindings:
        result.AddBinding(
            SuperInstance(cls.data, None, self.vm), [cls], node)
    elif len(args.posargs) == 2:
      for cls in args.posargs[0].bindings:
        for obj in args.posargs[1].bindings:
          if not isinstance(cls.data, Class):
            raise WrongArgTypes(
                self._SIGNATURE, self._SIGNATURE.print_args(args))
          result.AddBinding(
              SuperInstance(cls.data, obj.data, self.vm), [cls, obj], node)
    else:
      self.vm.errorlog.super_error(
          self.vm.frame.current_opcode, len(args.posargs))
      result = self.vm.convert.create_new_unsolvable(node, "super()")
    return node, result


class IsInstance(AtomicAbstractValue):
  """The isinstance() function."""

  # Minimal signature, only used for constructing exceptions.
  _SIGNATURE = function.Signature(
      "isinstance", ("obj", "type_or_types"), None, set(), None, {},
      {"return": None}, {})

  def __init__(self, vm):
    super(IsInstance, self).__init__("isinstance", vm)
    # Map of True/False/None (where None signals an ambiguous bool) to
    # vm values.
    self._vm_values = {
        True: vm.convert.true,
        False: vm.convert.false,
        None: vm.convert.primitive_class_instances[bool],
    }

  def call(self, node, _, args, condition=None):
    try:
      if len(args.posargs) != 2:
        raise WrongArgCount(self._SIGNATURE, self._SIGNATURE.print_args(args))
      elif args.namedargs.keys():
        raise WrongKeywordArgs(self._SIGNATURE,
                               self._SIGNATURE.print_args(args),
                               args.namedargs.keys())
      else:
        result = self.vm.program.NewVariable("isinstance")
        for left in args.posargs[0].bindings:
          for right in args.posargs[1].bindings:
            pyval = self._is_instance(left.data, right.data)
            result.AddBinding(self._vm_values[pyval],
                              source_set=(left, right), where=node)
    except InvalidParameters as ex:
      self.vm.errorlog.invalid_function_call(self.vm.frame.current_opcode, ex)
      result = self.vm.convert.create_new_unsolvable(node, "isinstance()")

    return node, result

  def _is_instance(self, obj, class_spec):
    """Check if the object matches a class specification.

    Args:
      obj: An AtomicAbstractValue, generally the left hand side of an
          isinstance() call.
      class_spec: An AtomicAbstractValue, generally the right hand side of an
          isinstance() call.

    Returns:
      True if the object is derived from a class in the class_spec, False if
      it is not, and None if it is ambiguous whether obj matches class_spec.
    """
    if isinstance(obj, AMBIGUOUS_OR_EMPTY):
      return None
    # Assume a single binding for the object's class variable.  If this isn't
    # the case, treat the call as ambiguous.
    cls_var = obj.get_class()
    if cls_var is None:
      return None
    try:
      obj_class = get_atomic_value(cls_var)
    except ConversionError:
      return None

    # Determine the flattened list of classes to check.
    classes = []
    ambiguous = self._flatten(class_spec, classes)

    for c in classes:
      if c in obj_class.mro:
        return True  # A definite match.
    # No matches, return result depends on whether _flatten() was
    # ambiguous.
    return None if ambiguous else False

  def _flatten(self, value, classes):
    """Flatten the contents of value into classes.

    If value is a Class, it is appended to classes.
    If value is a PythonConstant of type tuple, then each element of the tuple
    that has a single binding is also flattened.
    Any other type of value, or tuple elements that have multiple bindings are
    ignored.

    Args:
      value: An abstract value.
      classes: A list to be modified.

    Returns:
      True iff a value was ignored during flattening.
    """
    if isinstance(value, Class):
      # A single class, no ambiguity.
      classes.append(value)
      return False
    elif (isinstance(value, PythonConstant) and
          value.get_class() is self.vm.convert.tuple_type and
          isinstance(value.pyval, tuple)):
      # A tuple, need to process each element.
      ambiguous = False
      for var in value.pyval:
        if (len(var.bindings) != 1 or
            self._flatten(var.bindings[0].data, classes)):
          # There were either multiple bindings or ambiguity deeper in the
          # recursion.
          ambiguous = True
      return ambiguous
    else:
      return True

  def to_type(self, node, seen=None):
    return pytd.NamedType("__builtin__.function")


class Function(Instance):
  """Base class for function objects (NativeFunction, InterpreterFunction).

  Attributes:
    name: Function name. Might just be something like "<lambda>".
    vm: TypegraphVirtualMachine instance.
  """

  def __init__(self, name, vm, node):
    super(Function, self).__init__(vm.convert.function_type, vm, node)
    self.name = name
    self.is_attribute_of_class = False
    self.members["func_name"] = self.vm.convert.build_string(
        self.vm.root_cfg_node, name)

  def property_get(self, callself, callcls):
    if self.name == "__new__" or not callself or not callcls:
      return self
    self.is_attribute_of_class = True
    # We'd like to cache this, but we can't. "callself" contains Variables
    # that would be tied into a BoundFunction instance. However, those
    # Variables aren't necessarily visible from other parts of the CFG binding
    # this function. See test_duplicate_getproperty() in tests/test_flow.py.
    return self.bound_class(callself, callcls, self)

  def get_class(self):
    return self.vm.convert.function_type

  def to_type(self, node, seen=None):
    return pytd.NamedType("__builtin__.function")

  def __repr__(self):
    return self.name + "(...)"

  # We want to use __repr__ above rather than Instance.__str__
  __str__ = __repr__


class Mutation(collections.namedtuple("_", ["instance", "name", "value"])):
  pass


class PyTDSignature(object):
  """A PyTD function type (signature).

  This represents instances of functions with specific arguments and return
  type.
  """

  def __init__(self, name, pytd_sig, vm):
    self.vm = vm
    self.name = name
    self.pytd_sig = pytd_sig
    self.param_types = [
        self.vm.convert.convert_constant_to_value(
            pytd.Print(p), p.type, subst={}, node=self.vm.root_cfg_node)
        for p in self.pytd_sig.params]
    self.signature = function.Signature.from_pytd(vm, name, pytd_sig)

  def match_args(self, node, args, view):
    """Match arguments against this signature. Used by PyTDFunction."""
    arg_dict = {name: view[arg]
                for name, arg in zip(self.signature.param_names, args.posargs)}
    for name, arg in args.namedargs.items():
      if name in arg_dict:
        raise DuplicateKeyword(
            self.signature, self.signature.print_args(args), name)
      arg_dict[name] = view[arg]

    for p in self.pytd_sig.params:
      if p.name not in arg_dict:
        if (not p.optional and args.starargs is None and
            args.starstarargs is None):
          raise MissingParameter(
              self.signature, self.signature.print_args(args), p.name)
        # Assume the missing parameter is filled in by *args or **kwargs.
        # Unfortunately, we can't easily use *args or **kwargs to fill in
        # something more precise, since we need a Value, not a Variable.
        var = self.vm.convert.create_new_unsolvable(node, p.name)
        arg_dict[p.name] = var.bindings[0]

    for p in self.pytd_sig.params:
      if not (p.optional or p.name in arg_dict):
        raise MissingParameter(
            self.signature, self.signature.print_args(args), p.name)
    if not self.pytd_sig.has_optional:
      if len(args.posargs) > len(self.pytd_sig.params):
        raise WrongArgCount(self.signature, self.signature.print_args(args))
      invalid_names = set(args.namedargs) - {p.name
                                             for p in self.pytd_sig.params}
      if invalid_names:
        raise WrongKeywordArgs(self.signature, self.signature.print_args(args),
                               sorted(invalid_names))

    subst = self._compute_subst(node, arg_dict, view)
    if subst is None:
      raise WrongArgTypes(self.signature, self.signature.print_args(args))
    log.debug("Matched arguments against sig%s", pytd.Print(self.pytd_sig))
    for nr, p in enumerate(self.pytd_sig.params):
      log.info("param %d) %s: %s <=> %s", nr, p.name, p.type, arg_dict[p.name])
    for name, var in sorted(subst.items()):
      log.debug("Using %s=%r %r", name, var, var.data)

    return arg_dict, subst

  def call_with_args(self, node, func, arg_dict, subst, ret_map):
    """Call this signature. Used by PyTDFunction."""
    return_type = self.pytd_sig.return_type
    t = (return_type, subst)
    sources = [func] + arg_dict.values()
    if t not in ret_map:
      try:
        ret_map[t] = self.vm.convert.convert_constant(
            "ret", AsInstance(return_type), subst, node, source_sets=[sources])
      except self.vm.convert.TypeParameterError:
        # The return type contains a type parameter without a substitution. See
        # test_functions.test_type_parameter_in_return for an example of a
        # return type being set to Unknown here and solved later.
        ret_map[t] = Unknown(self.vm).to_variable(node, "ret")
      else:
        if (not ret_map[t].bindings and
            isinstance(return_type, pytd.TypeParameter)):
          ret_map[t].AddBinding(self.vm.convert.empty, [], node)
    else:
      # add the new sources
      for data in ret_map[t].data:
        ret_map[t].AddBinding(data, sources, node)
    mutations = self._get_mutation(node, arg_dict, subst)
    self.vm.trace_call(node, func, (self,),
                       tuple(arg_dict[p.name] for p in self.pytd_sig.params),
                       {},
                       ret_map[t])
    return node, ret_map[t], mutations

  def _compute_subst(self, node, arg_dict, view):
    """Compute information about type parameters using one-way unification.

    Given the arguments of a function call, try to find a substitution that
    matches them against the formal parameter of this PyTDSignature.

    Args:
      node: The current CFG node.
      arg_dict: A map of strings to pytd.Bindings instances.
      view: A mapping of Variable to Value.
    Returns:
      utils.HashableDict if we found a working substition, None otherwise.
    Raises:
      FailedFunctionCall: For incorrect parameter types.
    """
    if not arg_dict:
      return utils.HashableDict()
    subst = {}
    for p in self.pytd_sig.params:
      actual = arg_dict[p.name]
      formal = self.signature.annotations[p.name]
      subst = self.vm.matcher.match_value_against_type(
          actual, formal, subst, node, view)
      if subst is None:
        # These parameters didn't match this signature. There might be other
        # signatures that work, but figuring that out is up to the caller.
        return None
    return utils.HashableDict(subst)

  def _get_mutation(self, node, arg_dict, subst):
    """Mutation for changing the type parameters of mutable arguments.

    This will adjust the type parameters as needed for pytd functions like:
      def append_float(x: list[int]):
        x := list[int or float]
    This is called after all the signature matching has succeeded, and we
    know we're actually calling this function.

    Args:
      node: The current CFG node.
      arg_dict: A map of strings to pytd.Bindings instances.
      subst: Current type parameters.
    Returns:
      A list of Mutation instances.
    Raises:
      ValueError: If the pytd contains invalid information for mutated params.
    """
    # Handle mutable parameters using the information type parameters
    mutations = []
    for formal in self.pytd_sig.params:
      actual = arg_dict[formal.name]
      if formal.mutated_type is not None:
        if (isinstance(formal.type, pytd.GenericType) and
            isinstance(formal.mutated_type, pytd.GenericType) and
            formal.type.base_type == formal.mutated_type.base_type and
            isinstance(formal.type.base_type, pytd.ClassType) and
            formal.type.base_type.cls):
          arg = actual.data
          names_actuals = zip(formal.mutated_type.base_type.cls.template,
                              formal.mutated_type.parameters)
          for tparam, type_actual in names_actuals:
            log.info("Mutating %s to %s",
                     tparam.name,
                     pytd.Print(type_actual))
            type_actual_val = self.vm.convert.convert_constant(
                tparam.name, AsInstance(type_actual), subst, node,
                discard_concrete_values=True)
            mutations.append(Mutation(arg, tparam.name, type_actual_val))
        else:
          log.error("Old: %s", pytd.Print(formal.type))
          log.error("New: %s", pytd.Print(formal.mutated_type))
          log.error("Actual: %r", actual)
          raise ValueError("Mutable parameters setting a type to a "
                           "different base type is not allowed.")
    return mutations

  def get_positional_names(self):
    return [p.name for p in self.pytd_sig.params
            if not p.kwonly]

  def __repr__(self):
    return pytd.Print(self.pytd_sig)


class ClassMethod(AtomicAbstractValue):
  """Implements @classmethod methods in pyi."""

  def __init__(self, name, method, callself, callcls, vm):
    super(ClassMethod, self).__init__(name, vm)
    self.method = method
    self.callself = callself  # unused
    self.callcls = callcls  # unused
    self.signatures = self.method.signatures

  def call(self, node, func, args, condition=None):
    # Since this only used in pyi, we don't need to verify the type of the "cls"
    # arg a second time. So just pass an unsolveable. (All we care about is the
    # return type, anyway.)
    cls = self.vm.convert.create_new_unsolvable(node, "cls")
    return self.method.call(
        node, func, args.replace(posargs=(cls,) + args.posargs), condition)


class StaticMethod(AtomicAbstractValue):
  """Implements @staticmethod methods in pyi."""

  def __init__(self, name, method, callself, callcls, vm):
    super(StaticMethod, self).__init__(name, vm)
    self.method = method
    self.callself = callself  # unused
    self.callcls = callcls  # unused
    self.signatures = self.method.signatures

  def call(self, *args, **kwargs):
    return self.method.call(*args, **kwargs)


class PyTDFunction(Function):
  """A PyTD function (name + list of signatures).

  This represents (potentially overloaded) functions.
  """

  def __init__(self, name, signatures, kind, vm, node):
    super(PyTDFunction, self).__init__(name, vm, node)
    assert signatures
    self.kind = kind
    self.bound_class = BoundPyTDFunction
    self.signatures = signatures
    self._signature_cache = {}
    self._return_types = {sig.pytd_sig.return_type for sig in signatures}
    self._has_mutable = any(param.mutated_type is not None
                            for sig in signatures
                            for param in sig.pytd_sig.params)
    for sig in signatures:
      sig.function = self
      sig.name = self.name

  def property_get(self, callself, callcls):
    if self.kind == pytd.STATICMETHOD:
      return StaticMethod(self.name, self, callself, callcls, self.vm)
    elif self.kind == pytd.CLASSMETHOD:
      return ClassMethod(self.name, self, callself, callcls, self.vm)
    else:
      return Function.property_get(self, callself, callcls)

  def _log_args(self, arg_values_list, level=0, logged=None):
    if log.isEnabledFor(logging.DEBUG):
      if logged is None:
        logged = set()
      for i, arg_values in enumerate(arg_values_list):
        if level:
          if arg_values and any(v.data not in logged for v in arg_values):
            log.debug("%s%s:", "  " * level, arg_values[0].variable.id)
        else:
          log.debug("Arg %d", i)
        for value in arg_values:
          if value.data not in logged:
            log.debug("%s%s [var %d]", "  " * (level + 1), value.data,
                      value.variable.id)
            self._log_args(value.data.unique_parameter_values(), level + 2,
                           logged | {value.data})

  def call(self, node, func, args, condition=None):
    args = args.simplify(node)
    self._log_args(arg.bindings for arg in args.posargs)
    ret_map = {}
    retvar = self.vm.program.NewVariable("%s ret" % self.name)
    error = None
    variables = tuple(args.posargs) + tuple(args.namedargs.values())
    all_calls_failed = True
    all_mutations = []
    for combination in utils.deep_variable_product(variables):
      view = {value.variable: value for value in combination}
      if not node.CanHaveCombination(view.values()):
        log.info("Skipping combination %r", view.values())
        continue
      try:
        node, result, mutations = self._call_with_view(
            node, func, args, view, ret_map)
      except FailedFunctionCall as e:
        # TODO(kramm): Does this ever happen?
        error = error or e
      else:
        retvar.PasteVariable(result, node)
        all_mutations += mutations
        all_calls_failed = False
    if all_calls_failed and error:
      raise error  # pylint: disable=raising-bad-type

    log.info("Applying %d mutations", len(all_mutations))
    for obj, name, value in all_mutations:
      obj.merge_type_parameter(node, name, value)

    return node, retvar

  def _get_mutation_to_unknown(self, node, values):
    """Mutation for making all type parameters in a list of instances "unknown".

    This is used if we call a function that has mutable parameters and
    multiple signatures with unknown parameters.

    Args:
      node: The current CFG node.
      values: A list of instances of AtomicAbstractValue.

    Returns:
      A list of Mutation instances.
    """
    return [Mutation(v, name, self.vm.convert.create_new_unknown(
        node, name, action="type_param_" + name))
            for v in values if isinstance(v, SimpleAbstractValue)
            for name in v.type_parameters]

  def _call_with_view(self, node, func, args, view, ret_map):
    """Call function using a specific Variable->Value view."""
    log.debug("call_with_view function %r: %d signature(s)",
              self.name, len(self.signatures))
    log.debug("args in view: %r", [(a.bindings and view[a].data)
                                   for a in args.posargs])

    if not all(a.bindings for a in args.posargs):
      raise exceptions.ByteCodeTypeError(
          "Can't call function with <nothing> parameter")

    # If we're calling an overloaded pytd function with an unknown as a
    # parameter, we can't tell whether it matched or not. Hence, if multiple
    # signatures are possible matches, we don't know which got called. Check
    # if this is the case.
    if (len(self.signatures) > 1 and
        any(isinstance(view[arg].data, AMBIGUOUS_OR_EMPTY)
            for arg in chain(args.posargs, args.namedargs.values()))):
      signatures = tuple(self._yield_matching_signatures(node, args, view))
      if len(signatures) > 1:
        return self._call_with_signatures(node, func, args, view, signatures)
      else:
        (sig, arg_dict, subst), = signatures
    else:
      # We only take the first signature that matches, and ignore all after it.
      # This is because in the pytds for the standard library, the last
      # signature(s) is/are fallback(s) - e.g. list is defined by
      # def __init__(self: x: list)
      # def __init__(self, x: iterable)
      # def __init__(self, x: generator)
      # def __init__(self, x: object)
      # with the last signature only being used if none of the others match.
      sig, arg_dict, subst = next(self._yield_matching_signatures(
          node, args, view))
    return sig.call_with_args(node, func, arg_dict, subst, ret_map)

  def _call_with_signatures(self, node, func, args, view, signatures):
    """Perform a function call that involves multiple signatures."""
    if len(self._return_types) == 1:
      ret_type, = self._return_types
      try:
        # Even though we don't know which signature got picked, if the return
        # type is unique and does not contain any type parameter, we can use it.
        result = self.vm.convert.convert_constant(
            "ret", AsInstance(ret_type), {}, node)
      except self.vm.convert.TypeParameterError:
        # The return type contains a type parameter
        result = None
      else:
        log.debug("Unknown args. But return is always %s", pytd.Print(ret_type))
    else:
      result = None
    if result is None:
      log.debug("Creating unknown return")
      result = self.vm.convert.create_new_unknown(
          node, "<unknown return of " + self.name + ">", action="pytd_call")
    for i, arg in enumerate(args.posargs):
      if isinstance(view[arg].data, Unknown):
        for sig, _, _ in signatures:
          if (len(sig.param_types) > i and
              isinstance(sig.param_types[i], TypeParameter)):
            # Change this parameter from unknown to unsolvable to prevent the
            # unknown from being solved to a type in another signature. For
            # instance, with the following definitions:
            #  def f(x: T) -> T
            #  def f(x: int) -> T
            # the type of x should be Any, not int.
            view[arg] = arg.AddBinding(self.vm.convert.unsolvable, [], node)
            break
    if self._has_mutable:
      # TODO(kramm): We only need to whack the type params that appear in
      # a mutable parameter.
      mutations = self._get_mutation_to_unknown(
          node, (view[p].data for p in chain(args.posargs,
                                             args.namedargs.values())))
    else:
      mutations = []
    self.vm.trace_call(node, func, tuple(sig[0] for sig in signatures),
                       [view[arg] for arg in args.posargs],
                       {name: view[arg]
                        for name, arg in args.namedargs.items()},
                       result)
    return node, result, mutations

  def _yield_matching_signatures(self, node, args, view):
    """Try, in order, all pytd signatures, yielding matches."""
    error = None
    matched = False
    for sig in self.signatures:
      try:
        arg_dict, subst = sig.match_args(node, args, view)
      except FailedFunctionCall as e:
        error = error or e
      else:
        matched = True
        yield sig, arg_dict, subst
    if not matched:
      raise error  # pylint: disable=raising-bad-type

  def to_pytd_def(self, node, name):
    del node
    return pytd.Function(
        name, tuple(sig.pytd_sig for sig in self.signatures), pytd.METHOD)


class Class(object):
  """Mix-in to mark all class-like values."""

  def __new__(cls, *args, **kwds):
    """Prevent direct instantiation."""
    assert cls is not Class, "Cannot instantiate Class"
    return object.__new__(cls, *args, **kwds)

  def init_mixin(self, metaclass):
    """Mix-in equivalent of __init__."""
    if metaclass is None:
      for base in self.mro[1:]:
        if isinstance(base, Class) and base.cls is not None:
          self.cls = base.cls
          break
    else:
      # TODO(rechen): Check that the metaclass is a (non-strict) subclass of the
      # metaclasses of the base classes.
      self.cls = metaclass

  def to_type(self, node, seen=None):
    del node, seen
    return pytd.GenericType(base_type=pytd.NamedType("__builtin__.type"),
                            parameters=(pytd.NamedType(self.full_name),))

  def to_pytd_def(self, node, name):
    # Default method. Generate an empty pytd. Subclasses override this.
    del node
    return pytd.Class(name, None, (), (), (), ())

  def _call_new_and_init(self, node, value, args, condition):
    """Call __new__ if it has been overridden on the given value."""
    node, new = self.vm.attribute_handler.get_attribute(
        node, value.data, "__new__", value)
    if new is None:
      return node, None
    if len(new.bindings) == 1:
      f = new.bindings[0].data
      if isinstance(f, StaticMethod):
        f = f.method
      if isinstance(f, AMBIGUOUS_OR_EMPTY) or f is self.vm.convert.object_new:
        # Instead of calling object.__new__, our abstract classes directly
        # create instances of themselves.
        return node, None
    cls = value.AssignToNewVariable(value.data.name, node)
    new_args = args.replace(posargs=(cls,) + args.posargs)
    node, variable = self.vm.call_function(node, new, new_args,
                                           condition=condition)
    for val in variable.bindings:
      if val.data.cls and self in val.data.cls.data:
        node = self._call_init(node, val, args, condition)
    return node, variable

  def _call_init(self, node, value, args, condition):
    node, init = self.vm.attribute_handler.get_attribute(
        node, value.data, "__init__", value)
    # TODO(pludemann): Verify that this follows MRO:
    if init:
      log.debug("calling %s.__init__(...)", self.name)
      node, ret = self.vm.call_function(node, init, args, condition=condition)
      log.debug("%s.__init__(...) returned %r", self.name, ret)
    return node


class ParameterizedClass(AtomicAbstractValue, Class):
  """A class that contains additional parameters. E.g. a container.

  Attributes:
    cls: A PyTDClass representing the base type.
    type_parameters: An iterable of AtomicAbstractValue, one for each type
        parameter.
  """

  formal = True

  def __init__(self, base_cls, type_parameters, vm):
    # A ParameterizedClass is created by converting a pytd.GenericType, whose
    # base type is restricted to NamedType and ClassType.
    assert isinstance(base_cls, Class)
    super(ParameterizedClass, self).__init__(base_cls.name, vm)
    self.base_cls = base_cls
    self.type_parameters = type_parameters
    self.mro = (self,) + self.base_cls.mro[1:]
    Class.init_mixin(self, base_cls.cls)

  def __repr__(self):
    return "ParameterizedClass(cls=%r params=%s)" % (self.base_cls,
                                                     self.type_parameters)

  def __str__(self):
    params = [self.type_parameters[type_param.name]
              for type_param in self.base_cls.pytd_cls.template]
    base = pep484.PEP484_MaybeCapitalize(str(self.base_cls)) or self.base_cls
    return "%s[%s]" % (base, ", ".join(str(p) for p in params))

  def to_type(self, node, seen=None):
    return Class.to_type(self, node, seen)

  def get_instance_type(self, node, instance=None, seen=None):
    type_arguments = []
    for type_param in self.base_cls.pytd_cls.template:
      type_arguments.append(
          self.type_parameters[type_param.name].get_instance_type(
              node, None, seen))
    return pytd_utils.MakeClassOrContainerType(
        pytd_utils.NamedTypeWithModule(self.base_cls.pytd_cls.name,
                                       self.base_cls.module),
        type_arguments)


class PyTDClass(SimpleAbstractValue, Class):
  """An abstract wrapper for PyTD class objects.

  These are the abstract values for class objects that are described in PyTD.

  Attributes:
    cls: A pytd.Class
    mro: Method resolution order. An iterable of AtomicAbstractValue.
  """
  is_lazy = True  # uses _convert_member

  def __init__(self, name, pytd_cls, vm):
    super(PyTDClass, self).__init__(name, vm)
    mm = {}
    for val in pytd_cls.constants + pytd_cls.methods:
      mm[val.name] = val
    self._member_map = mm
    if pytd_cls.metaclass is None:
      metaclass = None
    else:
      metaclass = self.vm.convert.convert_constant(
          pytd.Print(pytd_cls.metaclass), pytd_cls.metaclass, subst={},
          node=self.vm.root_cfg_node)
    self.pytd_cls = pytd_cls
    self.mro = mro.compute_mro(self)
    Class.init_mixin(self, metaclass)

  def bases(self):
    convert = self.vm.convert
    return [convert.convert_constant_to_value(
        pytd.Print(parent), parent, subst={}, node=self.vm.root_cfg_node)
            for parent in self.pytd_cls.parents]

  def _convert_member(self, name, pyval, subst=None, node=None):
    """Convert a member as a variable. For lazy lookup."""
    subst = subst or {}
    node = node or self.vm.root_cfg_node
    if isinstance(pyval, pytd.Constant):
      return self.vm.convert.convert_constant(
          name, AsInstance(pyval.type), subst, node)
    elif isinstance(pyval, pytd.Function):
      c = self.vm.convert.convert_constant_to_value(
          repr(pyval), pyval, subst=subst, node=node)
      c.parent = self
      return c.to_variable(self.vm.root_cfg_node, name)
    else:
      raise AssertionError("Invalid class member %s", pytd.Print(pyval))

  def call(self, node, func, args, condition=None):
    node, results = self._call_new_and_init(node, func, args, condition)
    if results is None:
      value = Instance(self.vm.convert.convert_constant(
          self.name, self.pytd_cls), self.vm, node)
      for type_param in self.pytd_cls.template:
        if type_param.name not in value.type_parameters:
          value.type_parameters[type_param.name] = self.vm.program.NewVariable(
              type_param.name)
      results = self.vm.program.NewVariable(self.name)
      retval = results.AddBinding(value, [func], node)
      node = self._call_init(node, retval, args, condition)
    return node, results

  def instantiate(self, node):
    return self.vm.convert.convert_constant(
        self.name, AsInstance(self.pytd_cls), {}, node)

  def to_type(self, node, seen=None):
    return Class.to_type(self, node, seen)

  def get_instance_type(self, node, instance=None, seen=None):
    """Convert instances of this class to their PYTD type."""
    if seen is None:
      seen = set()
    type_params = self.pytd_cls.template
    if instance in seen:
      # We have a circular dependency in our types (e.g., lst[0] == lst). Stop
      # descending into the type parameters.
      type_params = ()
    if instance is not None:
      seen.add(instance)
    type_arguments = []
    for type_param in type_params:
      if instance is not None and type_param.name in instance.type_parameters:
        param = instance.type_parameters[type_param.name]
        type_arguments.append(pytd_utils.JoinTypes(
            data.to_type(node, seen=seen) for data in param.Data(node)))
      else:
        type_arguments.append(pytd.AnythingType())
    return pytd_utils.MakeClassOrContainerType(
        pytd_utils.NamedTypeWithModule(self.name, self.module),
        type_arguments)

  def __repr__(self):
    return self.name

  def to_pytd_def(self, node, name):
    # This happens if a module does e.g. "from x import y as z", i.e., copies
    # something from another module to the local namespace. We *could*
    # reproduce the entire class, but we choose a more dense representation.
    return self.to_type(node, name)

  def convert_as_instance_attribute(self, node, name, instance):
    try:
      c = self.pytd_cls.Lookup(name)
    except KeyError:
      return None
    if isinstance(c, pytd.Constant):
      try:
        self._convert_member(name, c)
      except self.vm.convert.TypeParameterError:
        # Constant c cannot be converted without type parameter substitutions,
        # so it must be an instance attribute.
        subst = {itm.name: TypeParameterInstance(
            itm.name, instance, self.vm).to_variable(node, name)
                 for itm in self.pytd_cls.template}
        return self._convert_member(name, c, subst, node)


class InterpreterClass(SimpleAbstractValue, Class):
  """An abstract wrapper for user-defined class objects.

  These are the abstract value for class objects that are implemented in the
  program.
  """

  def __init__(self, name, bases, members, vm):
    assert isinstance(name, str)
    assert isinstance(bases, list)
    assert isinstance(members, dict)
    super(InterpreterClass, self).__init__(name, vm)
    self._bases = bases
    self.mro = mro.compute_mro(self)
    Class.init_mixin(self, None)
    self.members = utils.MonitorDict(members)
    self.instances = set()  # filled through register_instance
    self._instance_cache = {}
    log.info("Created class: %r", self)

  def register_instance(self, instance):
    self.instances.add(instance)

  def bases(self):
    return utils.concat_lists(b.data for b in self._bases)

  def _new_instance(self):
    # We allow only one "instance" per code location, regardless of call stack.
    key = self.vm.frame.current_opcode
    if key not in self._instance_cache:
      cls = self.vm.program.NewVariable(self.name)
      cls.AddBinding(self, [], self.vm.root_cfg_node)
      self._instance_cache[key] = Instance(cls, self.vm, self.vm.root_cfg_node)
    return self._instance_cache[key]

  def call(self, node, value, args, condition=None):
    node, variable = self._call_new_and_init(node, value, args, condition)
    if variable is None:
      value = self._new_instance()
      variable = self.vm.program.NewVariable(self.name + " instance")
      val = variable.AddBinding(value, [], node)
      node = self._call_init(node, val, args, condition)
    return node, variable

  def to_type(self, node, seen=None):
    return Class.to_type(self, node, seen)

  def to_pytd_def(self, node, class_name):
    methods = {}
    constants = collections.defaultdict(pytd_utils.TypeBuilder)

    # class-level attributes
    for name, member in self.members.items():
      if name not in output.CLASS_LEVEL_IGNORE:
        for value in member.FilteredData(self.vm.exitpoint):
          if isinstance(value, Function):
            v = value.to_pytd_def(node, name)
            if isinstance(v, pytd.Function):
              methods[name] = v
            elif isinstance(v, pytd.TYPE):
              constants[name].add_type(v)
            else:
              raise AssertionError(str(type(v)))
          else:
            constants[name].add_type(value.to_type(node))

    # instance-level attributes
    for instance in self.instances:
      for name, member in instance.members.items():
        if name not in output.CLASS_LEVEL_IGNORE:
          for value in member.FilteredData(self.vm.exitpoint):
            constants[name].add_type(value.to_type(node))

    for name in list(methods):
      if name in constants:
        # If something is both a constant and a method, it means that the class
        # is, at some point, overwriting its own methods with an attribute.
        del methods[name]
        constants[name].add_type(pytd.AnythingType())

    bases = [pytd_utils.JoinTypes(b.get_instance_type(node)
                                  for b in basevar.data)
             for basevar in self._bases
             if basevar is not self.vm.convert.oldstyleclass_type]
    constants = [pytd.Constant(name, builder.build())
                 for name, builder in constants.items()
                 if builder]
    # TODO(rechen): Convert self.cls to a metaclass.
    return pytd.Class(name=class_name,
                      metaclass=None,
                      parents=tuple(bases),
                      methods=tuple(methods.values()),
                      constants=tuple(constants),
                      template=())

  def get_instance_type(self, node, instance=None, seen=None):
    del node, instance
    if self.official_name:
      return pytd_utils.NamedTypeWithModule(self.official_name, self.module)
    else:
      return pytd.AnythingType()

  def __repr__(self):
    return "InterpreterClass(%s)" % self.name


class NativeFunction(Function):
  """An abstract value representing a native function.

  Attributes:
    name: Function name. Might just be something like "<lambda>".
    func: An object with a __call__ method.
    vm: TypegraphVirtualMachine instance.
  """

  def __init__(self, name, func, vm, node):
    super(NativeFunction, self).__init__(name, vm, node)
    self.name = name
    self.func = func
    self.cls = self.vm.convert.function_type

  def argcount(self):
    return self.func.func_code.co_argcount

  def call(self, node, _, args, condition=None):
    # Originate a new variable for each argument and call.
    return self.func(
        node,
        *[u.AssignToNewVariable(u.name, node)
          for u in args.posargs],
        **{k: u.AssignToNewVariable(u.name, node)
           for k, u in args.namedargs.items()})

  def get_positional_names(self):
    code = self.func.func_code
    return list(code.co_varnames[:code.co_argcount])


class InterpreterFunction(Function):
  """An abstract value representing a user-defined function.

  Attributes:
    name: Function name. Might just be something like "<lambda>".
    code: A code object.
    closure: Tuple of cells (typegraph.Variable) containing the free variables
      this closure binds to.
    vm: TypegraphVirtualMachine instance.
  """

  _function_cache = {}

  @staticmethod
  def make_function(name, code, f_locals, f_globals, defaults, kw_defaults,
                    closure, annotations, late_annotations, vm):
    """Get an InterpreterFunction.

    Things like anonymous functions and generator expressions are created
    every time the corresponding code executes. Caching them makes it easier
    to detect when the environment hasn't changed and a function call can be
    optimized away.

    Arguments:
      name: Function name.
      code: A code object.
      f_locals: The locals used for name resolution.
      f_globals: The globals used for name resolution.
      defaults: Default arguments.
      kw_defaults: Default arguments for kwonly parameters.
      closure: The free variables this closure binds to.
      annotations: Function annotations. Dict of name -> AtomicAbstractValue.
      late_annotations: Late-evaled annotations. Dict of name -> str.
      vm: VirtualMachine instance.

    Returns:
      An InterpreterFunction.
    """
    annotations = annotations or {}
    late_annotations = late_annotations or {}
    key = (name, code,
           InterpreterFunction._hash_all(
               (f_globals.members, set(code.co_names)),
               (f_locals.members, set(code.co_varnames)),
               ({key: vm.program.NewVariable(key, [value], [],
                                             vm.root_cfg_node)
                 for key, value in annotations.items()}, None),
               (dict(enumerate(defaults)), None),
               (dict(enumerate(closure or ())), None)))
    if key not in InterpreterFunction._function_cache:
      InterpreterFunction._function_cache[key] = InterpreterFunction(
          name, code, f_locals, f_globals, defaults, kw_defaults,
          closure, annotations, late_annotations, vm, vm.root_cfg_node)
    return InterpreterFunction._function_cache[key]

  def __init__(self, name, code, f_locals, f_globals, defaults, kw_defaults,
               closure, annotations, late_annotations, vm, node):
    super(InterpreterFunction, self).__init__(name, vm, node)
    log.debug("Creating InterpreterFunction %r for %r", name, code.co_name)
    self.bound_class = BoundInterpreterFunction
    self.doc = code.co_consts[0] if code.co_consts else None
    self.name = name
    self.code = code
    self.f_globals = f_globals
    self.f_locals = f_locals
    self.defaults = tuple(defaults)
    self.kw_defaults = kw_defaults
    self.closure = closure
    self.annotations = annotations
    self.late_annotations = late_annotations
    self.cls = self.vm.convert.function_type
    self._call_records = {}
    self.nonstararg_count = self.code.co_argcount
    if self.code.co_kwonlyargcount >= 0:  # This is usually -1 or 0 (fast call)
      self.nonstararg_count += self.code.co_kwonlyargcount
    self.signature = self._build_signature()
    self.last_frame = None  # for BuildClass

  def _build_signature(self):
    """Build a function.Signature object representing this function."""
    vararg_name = None
    kwarg_name = None
    kwonly = set(self.code.co_varnames[
        self.code.co_argcount:self.nonstararg_count])
    arg_pos = self.nonstararg_count
    if self.has_varargs():
      vararg_name = self.code.co_varnames[arg_pos]
      arg_pos += 1
    if self.has_kwargs():
      kwarg_name = self.code.co_varnames[arg_pos]
      arg_pos += 1
    defaults = dict(zip(
        self.get_positional_names()[-len(self.defaults):], self.defaults))
    defaults.update(self.kw_defaults)
    return function.Signature(
        self.name,
        list(self.code.co_varnames[:self.nonstararg_count]),
        vararg_name,
        kwonly,
        kwarg_name,
        defaults,
        self.annotations,
        self.late_annotations)

  # TODO(kramm): support retrieving the following attributes:
  # 'func_{code, name, defaults, globals, locals, dict, closure},
  # '__name__', '__dict__', '__doc__', '_vm', '_func'

  def get_first_opcode(self):
    return self.code.co_code[0]

  def is_closure(self):
    return self.closure is not None

  def argcount(self):
    return self.code.co_argcount

  def _map_args(self, node, args):
    """Map call args to function args.

    This emulates how Python would map arguments of function calls. It takes
    care of keyword parameters, default parameters, and *args and **kwargs.

    Args:
      node: The current CFG node.
      args: The arguments.

    Returns:
      A dictionary, mapping strings (parameter names) to typegraph.Variable.

    Raises:
      FailedFunctionCall: If the caller supplied incorrect arguments.
    """
    # Originate a new variable for each argument and call.
    posargs = [u.AssignToNewVariable(u.name, node)
               for u in args.posargs]
    kws = {k: u.AssignToNewVariable(u.name, node)
           for k, u in args.namedargs.items()}
    if (self.vm.python_version[0] == 2 and
        self.code.co_name in ["<setcomp>", "<dictcomp>", "<genexpr>"]):
      # This code is from github.com/nedbat/byterun. Apparently, Py2 doesn't
      # know how to inspect set comprehensions, dict comprehensions, or
      # generator expressions properly. See http://bugs.python.org/issue19611.
      # Byterun says: "They are always functions of one argument, so just do the
      # right thing."
      assert len(posargs) == 1, "Surprising comprehension!"
      return {".0": posargs[0]}
    param_names = self.get_positional_names()
    num_defaults = len(self.defaults)
    callargs = dict(zip(param_names[-num_defaults:], self.defaults))
    callargs.update(self.kw_defaults)
    positional = dict(zip(param_names, posargs))
    for key in positional:
      if key in kws:
        raise DuplicateKeyword(
            self.signature, self.signature.print_args(args), key)
    callargs.update(positional)
    callargs.update(kws)
    for key, kwonly in self.get_nondefault_params():
      if key not in callargs:
        if args.starstarargs or (args.starargs and not kwonly):
          # We assume that because we have *args or **kwargs, we can use these
          # to fill in any parameters we might be missing.
          callargs[key] = self.vm.convert.create_new_unsolvable(node, key)
        else:
          raise MissingParameter(
              self.signature, self.signature.print_args(args), key)
    arg_pos = self.nonstararg_count
    if self.has_varargs():
      vararg_name = self.code.co_varnames[arg_pos]
      extraneous = posargs[self.code.co_argcount:]
      if args.starargs:
        if extraneous:
          log.warning("Not adding extra params to *%s", vararg_name)
        callargs[vararg_name] = args.starargs.AssignToNewVariable(
            "*args", node)
      else:
        callargs[vararg_name] = self.vm.convert.build_tuple(node, extraneous)
      arg_pos += 1
    elif len(posargs) > self.code.co_argcount:
      raise WrongArgCount(self.signature, self.signature.print_args(args))
    if self.has_kwargs():
      kwvararg_name = self.code.co_varnames[arg_pos]
      # Build a **kwargs dictionary out of the extraneous parameters
      if args.starstarargs:
        # TODO(kramm): modify type parameters to account for namedargs
        callargs[kwvararg_name] = args.starstarargs.AssignToNewVariable(
            "**kwargs", node)
      else:
        k = Dict("kwargs", self.vm, node)
        k.update(node, args.namedargs, omit=param_names)
        callargs[kwvararg_name] = k.to_variable(node, kwvararg_name)
      arg_pos += 1
    return callargs

  @staticmethod
  def _hash(vardict, names):
    """Hash a dictionary.

    This contains the keys and the full hashes of the data in the values.

    Arguments:
      vardict: A dictionary mapping str to Variable.
      names: If this is non-None, the snapshot will include only those
        dictionary entries whose keys appear in names.

    Returns:
      A hash of the dictionary.
    """
    if names is not None:
      vardict = {name: vardict[name] for name in names.intersection(vardict)}
    m = hashlib.md5()
    for name, var in sorted(vardict.items()):
      m.update(str(name))
      for value in var.bindings:
        m.update(value.data.get_fullhash())
    return m.digest()

  @staticmethod
  def _hash_all(*hash_args):
    """Convenience method for hashing a sequence of dicts."""
    return hashlib.md5("".join(InterpreterFunction._hash(*args)
                               for args in hash_args)).digest()

  def _check_call(self, node, args, condition):
    if not self.signature.has_param_annotations:
      return
    args = list(self.signature.iter_args(args))
    for i, (_, param_var, formal) in enumerate(args):
      if formal is not None:
        bad = self.vm.matcher.bad_matches(param_var, formal, node,
                                          condition=condition)
        if bad:
          passed = [(name, param.data[0]) for name, param, _ in args]
          if len(bad) == 1:
            passed[i] = (passed[i][0], bad[0].data)
          else:
            passed[i] = (passed[i][0], Union([b.data for b in bad], self.vm))
          # TODO(rechen): Is there a way to format the args in a non-printed
          # form so that we can use function.Signature.print_args here (which
          # would allow us move the call to print_args into errors.py)?
          raise WrongArgTypes(self.signature, passed)

  def call(self, node, _, args, condition=None, new_locals=None):
    args = args.simplify(node)
    if self.vm.is_at_maximum_depth() and self.name != "__init__":
      log.info("Maximum depth reached. Not analyzing %r", self.name)
      return (node,
              self.vm.convert.create_new_unsolvable(node, self.name + ":ret"))
    self._check_call(node, args, condition)
    callargs = self._map_args(node, args)
    # Might throw vm.RecursionException:
    frame = self.vm.make_frame(node, self.code, callargs,
                               self.f_globals, self.f_locals, self.closure,
                               new_locals=new_locals)
    if self.signature.has_return_annotation:
      frame.allowed_returns = self.signature.annotations["return"]
    if self.vm.options.skip_repeat_calls:
      callkey = self._hash_all(
          (callargs, None),
          (frame.f_globals.members, set(self.code.co_names)),
          (frame.f_locals.members, set(self.code.co_varnames)))
    else:
      # Make the callkey the number of times this function has been called so
      # that no call has the same key as a previous one.
      callkey = len(self._call_records)
    if callkey in self._call_records:
      _, old_ret, _, old_remaining_depth = self._call_records[callkey]
      # Optimization: This function has already been called, with the same
      # environment and arguments, so recycle the old return value and don't
      # record this call. We pretend that this return value originated at the
      # current node to make sure we don't miss any possible types.
      # We would want to skip this optimization and reanalyze the call
      # if the all the possible types of the return value was unsolvable
      # and we can transverse the function deeper.
      if (all(x == self.vm.convert.unsolvable for x in old_ret.data) and
          self.vm.remaining_depth() > old_remaining_depth):
        log.info("Reanalyzing %r because all of its call record's bindings are "
                 "Unsolvable; remaining_depth = %d,"
                 "record remaining_depth = %d",
                 self.name, self.vm.remaining_depth(), old_remaining_depth)
      else:
        ret = self.vm.program.NewVariable(old_ret.name, old_ret.data, [], node)
        return node, ret

    if self.code.co_flags & loadmarshal.CodeType.CO_GENERATOR:
      generator = Generator(frame, self.vm, node)
      # Run the generator right now, even though the program didn't call it,
      # because we need to know the contained type for futher matching.
      node2, _ = generator.run_until_yield(node)
      node_after_call, ret = node2, generator.to_variable(node2, self.name)
    else:
      node_after_call, ret = self.vm.run_frame(frame, node)
    self._call_records[callkey] = (callargs,
                                   ret,
                                   node_after_call,
                                   self.vm.remaining_depth())
    self.last_frame = frame
    return node_after_call, ret

  def _get_call_combinations(self):
    signature_data = set()
    for callargs, ret, node_after_call, _ in self._call_records.values():
      for combination in utils.variable_product_dict(callargs):
        for return_value in ret.bindings:
          values = combination.values() + [return_value]
          data = tuple(v.data for v in values)
          if data in signature_data:
            # This combination yields a signature we already know is possible
            continue
          if node_after_call.HasCombination(values):
            signature_data.add(data)
            yield node_after_call, combination, return_value

  def _fix_param_name(self, name):
    """Sanitize a parameter name; remove Python intrinstics."""
    # Python uses ".0" etc. for parameters that are tuples, like e.g. in:
    # "def f((x, y), z)".
    return name.replace(".", "_")

  def _with_replaced_annotations(self, node, params):
    """Insert type annotations into parameter list."""
    params = list(params)
    varnames = self.code.co_varnames[0:self.nonstararg_count]
    for name, formal_type in self.annotations.items():
      try:
        i = varnames.index(name)
      except ValueError:
        pass
      else:
        params[i] = params[i].Replace(type=formal_type.get_instance_type(node))
    return tuple(params)

  def _get_annotation_return(self, node, default):
    if "return" in self.annotations:
      return self.annotations["return"].get_instance_type(node)
    else:
      return default

  def _get_star_params(self):
    """Returns pytd nodes for *args, **kwargs."""
    if self.has_varargs():
      starargs = pytd.Parameter(self.signature.varargs_name,
                                pytd.NamedType("__builtin__.tuple"),
                                False, True, None)
    else:
      starargs = None
    if self.has_kwargs():
      starstarargs = pytd.Parameter(self.signature.kwargs_name,
                                    pytd.NamedType("__builtin__.dict"),
                                    False, True, None)
    else:
      starstarargs = None
    return starargs, starstarargs

  def to_pytd_def(self, node, function_name):
    """Generate a pytd.Function definition."""
    signatures = []
    combinations = tuple(self._get_call_combinations())
    for node_after, combination, return_value in combinations:
      params = tuple(pytd.Parameter(self._fix_param_name(name),
                                    combination[name].data.to_type(node),
                                    kwonly, optional, None)
                     for name, kwonly, optional in self.get_parameters())
      params = self._with_replaced_annotations(node_after, params)
      ret = self._get_annotation_return(
          node, default=return_value.data.to_type(node_after))
      if isinstance(ret, pytd.NothingType) and len(combinations) == 1:
        assert isinstance(return_value.data, Empty)
        ret = pytd.AnythingType()
      starargs, starstarargs = self._get_star_params()
      signatures.append(pytd.Signature(
          params=params,
          starargs=starargs,
          starstarargs=starstarargs,
          return_type=ret,
          exceptions=(),  # TODO(kramm): record exceptions
          template=()))
    if signatures:
      return pytd.Function(function_name, tuple(signatures), pytd.METHOD)
    else:
      # Fallback: Generate a pytd signature only from the definition of the
      # method, not the way it's being used.
      return pytd.Function(function_name, (self._simple_pytd_signature(node),),
                           pytd.METHOD)

  def _simple_pytd_signature(self, node):
    params = self._with_replaced_annotations(
        node, [pytd.Parameter(name, pytd.NamedType("__builtin__.object"),
                              kwonly, optional, None)
               for name, kwonly, optional in self.get_parameters()])
    starargs, starstarargs = self._get_star_params()
    ret = self._get_annotation_return(node, default=pytd.AnythingType())
    return pytd.Signature(
        params=params,
        starargs=starargs,
        starstarargs=starstarargs,
        return_type=ret,
        exceptions=(), template=())

  def get_positional_names(self):
    return list(self.code.co_varnames[:self.code.co_argcount])

  def get_nondefault_params(self):
    for i in range(self.nonstararg_count):
      yield self.code.co_varnames[i], i >= self.code.co_argcount

  def get_kwonly_names(self):
    return list(
        self.code.co_varnames[self.code.co_argcount:self.nonstararg_count])

  def get_parameters(self):
    default_pos = self.code.co_argcount - len(self.defaults)
    i = 0
    for name in self.get_positional_names():
      yield name, False, i >= default_pos
      i += 1
    for name in self.get_kwonly_names():
      yield name, True, name in self.kw_defaults
      i += 1

  def has_varargs(self):
    return bool(self.code.co_flags & loadmarshal.CodeType.CO_VARARGS)

  def has_kwargs(self):
    return bool(self.code.co_flags & loadmarshal.CodeType.CO_VARKEYWORDS)


class BoundFunction(AtomicAbstractValue):
  """An function type which has had an argument bound into it."""

  def __init__(self, callself, callcls, underlying):
    super(BoundFunction, self).__init__(underlying.name, underlying.vm)
    self._callself = callself
    self._callcls = callcls
    self.underlying = underlying
    self.is_attribute_of_class = False

  def argcount(self):
    return self.underlying.argcount() - 1  # account for self

  @property
  def signature(self):
    return self.underlying.signature.drop_first_parameter()

  def call(self, node, func, args, condition=None):
    try:
      return self.underlying.call(
          node, func, args.replace(posargs=(self._callself,) + args.posargs),
          condition)
    except InvalidParameters as e:
      if self._callself and self._callself.bindings:
        e.name = "%s.%s" % (self._callself.data[0].name, e.name)
      raise

  def get_positional_names(self):
    return self.underlying.get_positional_names()

  def has_varargs(self):
    return self.underlying.has_varargs()

  def has_kwargs(self):
    return self.underlying.has_kwargs()

  def to_type(self, node, seen=None):
    return pytd.NamedType("__builtin__.function")

  def __repr__(self):
    if self._callself and self._callself.bindings:
      callself = self._callself.data[0].name
    else:
      callself = "<class>"
    return callself + "." + repr(self.underlying)


class BoundInterpreterFunction(BoundFunction):
  """The method flavor of InterpreterFunction."""

  @property
  def annotations(self):
    return self.underlying.annotations

  def get_first_opcode(self):
    return self.underlying.code.co_code[0]


class BoundPyTDFunction(BoundFunction):
  pass


class Generator(Instance):
  """A representation of instances of generators.

  (I.e., the return type of coroutines).
  """

  TYPE_PARAM = "T"  # See class generator in pytd/builtins/__builtin__.pytd

  def __init__(self, generator_frame, vm, node):
    super(Generator, self).__init__(vm.convert.generator_type, vm, node)
    self.generator_frame = generator_frame
    self.runs = 0

  def get_special_attribute(self, node, name):
    if name == "__iter__":
      f = NativeFunction(name, self.__iter__, self.vm, node)
      return f.to_variable(node, name)
    elif name in ["next", "__next__"]:
      return self.to_variable(node, name)
    elif name == "throw":
      # We don't model exceptions in a way that would allow us to induce one
      # inside a coroutine. So just return ourself, mapping the call of
      # throw() to a next() (which won't be executed).
      return self.to_variable(node, name)

  def __iter__(self, node):  # pylint: disable=non-iterator-returned,unexpected-special-method-signature
    return node, self.to_variable(node, "__iter__")

  def run_until_yield(self, node):
    if self.runs == 0:  # Optimization: We only run the coroutine once.
      node, _ = self.vm.resume_frame(node, self.generator_frame)
      contained_type = self.generator_frame.yield_variable
      self.type_parameters[self.TYPE_PARAM] = contained_type
      self.runs += 1
    return node, self.type_parameters[self.TYPE_PARAM]

  def call(self, node, func, args, condition=None):
    """Call this generator or (more common) its "next" attribute."""
    del func, args
    return self.run_until_yield(node)


class Iterator(ValueWithSlots):
  """A representation of instances of iterators."""

  TYPE_PARAM = "T"

  def __init__(self, vm, return_var, node):
    super(Iterator, self).__init__(vm.convert.iterator_type, vm, node)
    self.set_slot("next", self.next_slot)
    self.init_type_parameters(self.TYPE_PARAM)
    # TODO(dbaum): Should we set type_parameters[self.TYPE_PARAM] to something
    # based on return_var?
    self._return_var = return_var

  def next_slot(self, node):
    return node, self._return_var


# TODO(rechen): Merge this class with Empty.
class Nothing(AtomicAbstractValue):
  """The VM representation of Nothing values.

  These are fake values that never exist at runtime, but they appear if you, for
  example, extract a value from an empty list.
  """

  formal = True

  def __init__(self, vm):
    super(Nothing, self).__init__("nothing", vm)

  def call(self, node, func, args, condition=None):
    raise AssertionError("Can't call empty object ('nothing')")

  def to_type(self, node, seen=None):
    return pytd.NothingType()


class Module(Instance):
  """Represents an (imported) module."""

  is_lazy = True  # uses _convert_member

  def __init__(self, vm, node, name, member_map):
    super(Module, self).__init__(vm.convert.module_type, vm=vm, node=node)
    self.name = name
    self._member_map = member_map

  def _convert_member(self, name, ty):
    """Called to convert the items in _member_map to cfg.Variable."""
    var = self.vm.convert.convert_constant(name, ty)
    for value in var.data:
      # Only do this if this class isn't already part of a module.
      # (This happens if e.g. foo.py does "from bar import x" and we then
      #  do "from foo import x".)
      if not value.module:
        value.module = self.name
    return var

  def has_getattr(self):
    """Does this module have a module-level __getattr__?

    We allow __getattr__ on the module level to specify that this module doesn't
    have any contents. The typical syntax is
      def __getattr__(name) -> Any
    .
    See https://www.python.org/dev/peps/pep-0484/#stub-files

    Returns:
      True if we have __getattr__.
    """
    f = self._member_map.get("__getattr__")
    if f:
      if isinstance(f, pytd.Function):
        if len(f.signatures) != 1:
          log.warning("overloaded module-level __getattr__ (in %s)", self.name)
        elif f.signatures[0].return_type != pytd.AnythingType():
          log.warning("module-level __getattr__ doesn't return Any (in %s)",
                      self.name)
        return True
      else:
        log.warning("__getattr__ in %s is not a function", self.name)
    return False

  def get_submodule(self, node, name):
    full_name = self.name + "." + name
    # The line below can raise load_pytd.BadDependencyError. This is OK since
    # we'll always be called from vm.byte_IMPORT_FROM which catches it.
    mod = self.vm.import_module(full_name, 0)  # 0: absolute import
    if mod is not None:
      return mod.to_variable(node, name)
    elif self.has_getattr():
      return self.vm.convert.create_new_unsolvable(node, full_name)
    else:
      log.warning("Couldn't find attribute / module %r", full_name)
      return None

  def items(self):
    return [(name, self._convert_member(name, ty))
            for name, ty in self._member_map.items()]

  def to_type(self, node, seen=None):
    return pytd.NamedType("__builtin__.module")


class BuildClass(AtomicAbstractValue):
  """Representation of the Python 3 __build_class__ object."""

  def __init__(self, vm):
    super(BuildClass, self).__init__("__build_class__", vm)

  def call(self, node, _, args, condition=None):
    funcvar, name = args.posargs[0:2]
    if len(funcvar.bindings) != 1:
      raise ConversionError("Invalid ambiguous argument to __build_class__")
    func, = funcvar.data
    if not isinstance(func, InterpreterFunction):
      raise ConversionError("Invalid argument to __build_class__")
    bases = args.posargs[2:]
    node, _ = func.call(node, funcvar.bindings[0],
                        args.replace(posargs=(), namedargs={}),
                        new_locals=True)
    return node, self.vm.make_class(
        node, name, list(bases),
        func.last_frame.f_locals.to_variable(node, "locals()"))


class Unsolvable(AtomicAbstractValue):
  """Representation of value we know nothing about.

  Unlike "Unknowns", we don't treat these as solveable. We just put them
  where values are needed, but make no effort to later try to map them
  to named types. This helps conserve memory where creating and solving
  hundreds of unknowns would yield us little to no information.

  This is typically a singleton. Since unsolvables are indistinguishable, we
  only need one.
  """
  IGNORED_ATTRIBUTES = ["__get__", "__set__", "__getattribute__"]

  # Since an unsolvable gets generated e.g. for every unresolved import, we
  # can have multiple circular Unsolvables in a class' MRO. Treat those special.
  SINGLETON = True

  def __init__(self, vm):
    super(Unsolvable, self).__init__("unsolveable", vm)
    self.mro = self.default_mro()

  def get_special_attribute(self, node, name):
    if name in self.IGNORED_ATTRIBUTES:
      return None
    else:
      return self.to_variable(node, self.name)

  def call(self, node, func, args, condition=None):
    del func, args
    # return ourself.
    return node, self.to_variable(node, self.name)

  def to_variable(self, node, name=None):
    return self.vm.program.NewVariable(
        name or self.name, [self], source_set=[], where=node)

  def get_class(self):
    # return ourself.
    return self.to_variable(self.vm.root_cfg_node, self.name)

  def to_pytd_def(self, node, name):
    """Convert this Unknown to a pytd.Class."""
    return pytd.Constant(name, self.to_type(node))

  def to_type(self, node, seen=None):
    return pytd.AnythingType()

  def get_instance_type(self, node, instance=None, seen=None):
    del node
    return pytd.AnythingType()

  def instantiate(self, node):
    # return ourself.
    return self.to_variable(node, self.name)


class Unknown(AtomicAbstractValue):
  """Representation of unknown values.

  These are e.g. the return values of certain functions (e.g. eval()). They
  "adapt": E.g. they'll respond to get_attribute requests by creating that
  attribute.

  Attributes:
    members: Attributes that were written or read so far. Mapping of str to
      typegraph.Variable.
    owner: typegraph.Binding that contains this instance as data.
  """

  _current_id = 0

  # For simplicity, Unknown doesn't emulate descriptors:
  IGNORED_ATTRIBUTES = ["__get__", "__set__", "__getattribute__"]

  def __init__(self, vm):
    name = "~unknown%d" % Unknown._current_id
    super(Unknown, self).__init__(name, vm)
    self.members = utils.MonitorDict()
    self.owner = None
    Unknown._current_id += 1
    self.class_name = self.name
    self._calls = []
    self.mro = self.default_mro()
    log.info("Creating %s", self.class_name)

  def get_children_maps(self):
    return (self.members,)

  @staticmethod
  def _to_pytd(node, v):
    if isinstance(v, typegraph.Variable):
      return pytd_utils.JoinTypes(Unknown._to_pytd(node, t) for t in v.data)
    elif isinstance(v, Unknown):
      # Do this directly, and use NamedType, in case there's a circular
      # dependency among the Unknown instances.
      return pytd.NamedType(v.class_name)
    else:
      return v.to_type(node)

  @staticmethod
  def _make_params(node, args):
    """Convert a list of types/variables to pytd parameters."""
    return tuple(pytd.Parameter("_%d" % (i + 1), Unknown._to_pytd(node, p),
                                kwonly=False, optional=False,
                                mutated_type=None)
                 for i, p in enumerate(args))

  def get_special_attribute(self, _, name):
    if name in self.IGNORED_ATTRIBUTES:
      return None
    if name in self.members:
      return self.members[name]
    new = self.vm.convert.create_new_unknown(self.vm.root_cfg_node,
                                             self.name + "." + name,
                                             action="getattr:" + name)
    # We store this at the root node, even though we only just created this.
    # From the analyzing point of view, we don't know when the "real" version
    # of this attribute (the one that's not an unknown) gets created, hence
    # we assume it's there since the program start.  If something overwrites it
    # in some later CFG node, that's fine, we'll then work only with the new
    # value, which is more accurate than the "fictional" value we create here.
    self.vm.attribute_handler.set_attribute(
        self.vm.root_cfg_node, self, name, new)
    return new

  def call(self, node, _, args, condition=None):
    ret = self.vm.convert.create_new_unknown(
        node, self.name + "()", source=self.owner, action="call:" + self.name)
    self._calls.append((args.posargs, args.namedargs, ret))
    return node, ret

  def to_variable(self, node, name=None):
    v = self.vm.program.NewVariable(name or self.name)
    val = v.AddBinding(self, source_set=[], where=node)
    self.owner = val
    self.vm.trace_unknown(self.class_name, v)
    return v

  def to_structural_def(self, node, class_name):
    """Convert this Unknown to a pytd.Class."""
    self_param = (pytd.Parameter("self", pytd.NamedType("__builtin__.object"),
                                 False, False, None),)
    # TODO(kramm): Record these.
    starargs = None
    starstarargs = None
    calls = tuple(pytd_utils.OrderedSet(
        pytd.Signature(self_param + self._make_params(node, args),
                       starargs,
                       starstarargs,
                       return_type=Unknown._to_pytd(node, ret),
                       exceptions=(),
                       template=())
        for args, _, ret in self._calls))
    if calls:
      methods = (pytd.Function("__call__", calls, pytd.METHOD),)
    else:
      methods = ()
    # TODO(rechen): Should we convert self.cls to a metaclass here as well?
    return pytd.Class(
        name=class_name,
        metaclass=None,
        parents=(pytd.NamedType("__builtin__.object"),),
        methods=methods,
        constants=tuple(pytd.Constant(name, Unknown._to_pytd(node, c))
                        for name, c in self.members.items()),
        template=())

  def get_class(self):
    # We treat instances of an Unknown as the same as the class.
    return self.to_variable(self.vm.root_cfg_node, "class of " + self.name)

  def instantiate(self, node):
    return self.to_variable(node, "instance of " + self.name)

  def to_type(self, node, seen=None):
    return pytd.NamedType(self.class_name)

  def get_instance_type(self, node, instance=None, seen=None):
    log.info("Using ? for instance of %s", self.name)
    return pytd.AnythingType()

AMBIGUOUS_OR_EMPTY = (Unknown, Unsolvable, Empty)
