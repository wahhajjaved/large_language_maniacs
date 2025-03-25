"""
Generic support for objects with full-featured Parameters and
messaging.  Potentially useful for any large Python program that needs
user-modifiable object attributes.

$Id$
"""
__version__='$Revision$'

import sys
import copy
import re


from pprint import pprint

# JABALERT: Could consider using Python's logging facilities instead.
SILENT  = 0
WARNING = 50
NORMAL  = 100
MESSAGE = NORMAL
VERBOSE = 200
DEBUG   = 300

min_print_level = NORMAL

# Indicates whether warnings should be raised as errors, stopping
# processing.
warnings_as_exceptions = False

object_count = 0


# CEBALERT: isn't this the same as our current classlist()?
#  def classlist: return inspect.getmro(class_)[::-1]
# Also, classlist() has almost identical code as descendents().

def classlist(class_):
    """
    Return a list of the class hierarchy above (and including) the given class.

    The list is ordered from least- to most-specific.  Often useful in
    functions to get and set the full state of an object, e.g. for
    pickling.
    """
    assert isinstance(class_, type)
    q = [class_]
    out = []
    while len(q):
        x = q.pop(0)
        out.append(x)
        for b in x.__bases__:
            if b not in q and b not in out:
                q.append(b)
                
    return out[::-1]


def descendents(class_):
    """
    Return a list of the class hierarchy below (and including) the given class.

    The list is ordered from least- to most-specific.  Can be useful for
    printing the contents of an entire class hierarchy.
    """
    assert isinstance(class_,type)
    q = [class_]
    out = []
    while len(q):
        x = q.pop(0)
        out.insert(0,x)
        for b in x.__subclasses__():
            if b not in q and b not in out:
                q.append(b)
    return out[::-1]



class Parameter(object):
    """
    An attribute descriptor for declaring parameters.

    Parameters are a special kind of class attribute.  Setting a class
    attribute to be an instance of this class causes that attribute of
    the class and its instances to be treated as a Parameter.  This
    allows special behavior, including dynamically generated parameter
    values (using lambdas or generators), documentation strings,
    read-only (constant) parameters, and type or range checking at
    assignment time.

    For example, suppose someone wants to define two new kinds of
    objects Foo and Bar, such that Bar has a parameter delta, Foo is a
    subclass of Bar, and Foo has parameters alpha, sigma, and gamma
    (and delta inherited from Bar).  She would begin her class
    definitions with something like this:

    class Bar(ParameterizedObject):
        delta = Parameter(default=0.6, doc='The difference between steps.')
        ...
        
    class Foo(Bar):
        alpha = Parameter(default=0.1, doc='The starting value.')
        sigma = Parameter(default=0.5, doc='The standard deviation.', constant=True)
        gamma = Parameter(default=1.0, doc='The ending value.')
        ...

    Class Foo would then have four parameters, with delta defaulting to 0.6.

    Parameters have several advantages over plain attributes:

    1. Parameters can be set automatically when an instance is
       constructed: The default constructor for Foo (and Bar) will
       accept arbitrary keyword arguments, each of which can be used
       to specify the value of a Parameter of Foo (or any of Foo's
       superclasses).  E.g., if a script does this:

           myfoo = Foo(alpha=0.5)

       myfoo.alpha will return 0.5, without the Foo constructor
       needing special code to set alpha.

       If Foo implements its own constructor, keyword arguments will
       still be accepted if the constructor accepts a dictionary of
       keyword arguments (as in ``def __init__(self,**params):``), and
       then each class calls its superclass (as in
       ``super(Foo,self).__init__(**params)``) so that the
       ParameterizedObject constructor will process the keywords.

    2. A ParameterizedObject need specify only the attributes of a
       Parameter whose values differ from those declared in
       superclasses of the ParameterizedObject; the other values will
       be inherited.  E.g. if Foo declares

        delta = Parameter(default=0.2) 

       the default value of 0.2 will override the 0.6 inherited from
       Bar, but the doc will be inherited from Bar.

    3. The Parameter descriptor class can be subclassed to provide more
       complex behavior, allowing special types of parameters that, for
       example, require their values to be numbers in certain ranges,
       generate their values dynamically from a random distribution, or 
       read their values from a file or other external source.

    4. The attributes associated with Parameters provide enough
       information for automatically generating property sheets in
       graphical user interfaces, to allow ParameterizedObjects to be
       edited by users.       
    """
    # Because they implement __get__ and __set__, Parameters are known
    # as 'descriptors' in Python; see "Implementing Descriptors" and
    # "Invoking Descriptors" in the 'Customizing attribute access'
    # section of the Python reference manual:
    # http://docs.python.org/ref/attribute-access.html
    #
    #
    #
    #
    # Overview of Parameters for programmers
    # ======================================
    #
    # Consider the following code:
    #
    #
    # class A(ParameterizedObject):
    #     p = Parameter(default=1)
    #
    # a1 = A()
    # a2 = A()
    #
    #
    # * a1 and a2 share one Parameter object (A.__dict__['p']).
    #
    # * The default (class) value of p is stored in this Parameter
    #   object (A.__dict__['p'].default).
    #
    # * If the value of p is set on a1 (e.g. a1.p=2), a1's value of p
    #   is stored in a1 itself (a1.__dict__['_p_param_value'])
    #
    # * When a1.p is requested, a1.__dict__['_p_param_value'] is
    #   returned. When a2.p is requested, '_p_param_value' is not
    #   found in a2.__dict__, so A.__dict__['p'].default (i.e. A.p) is
    #   returned instead.
    #
    #
    # Be careful when referring to the 'name' of a Parameter:
    #                                                   
    # * A ParameterizedObject class has a name for the attribute which
    #   is being represented by the Parameter ('p' in the example above);
    #   in the code, this is called the 'attrib_name'.
    #
    # * When a ParameterizedObject instance has its own local value
    #   for a parameter, it is stored as '_X_param_value' (where X is
    #   the attrib_name for the Parameter); in the code, this is
    #   called the internal_name.



    # So that the extra features of Parameters do not require a lot of
    # overhead, Parameters are implemented using __slots__ (see
    # http://www.python.org/doc/2.4/ref/slots.html).  Instead of having
    # a full Python dictionary associated with each Parameter instance,
    # Parameter instances have an enumerated list (named __slots__) of
    # attributes, and reserve just enough space to store these
    # attributes.  Using __slots__ requires special support for
    # operations to copy and restore Parameters (e.g. for Python
    # persistent storage pickling); see __getstate__ and __setstate__.
    # 
    # To get the benefit of slots, subclasses must themselves define
    # __slots__, whether or not they define attributes not present in
    # the base Parameter class.  That's because a subclass will have
    # a __dict__ unless it also defines __slots__.
    __slots__ = ['_attrib_name','default','doc','hidden','precedence','instantiate','constant']

    ### JABALERT: hidden could perhaps be replaced with a very low
    ### (e.g. negative) precedence value.  That way by default the
    ### GUI could display those with precedence >0, but the user could
    ### select a level.
                                                                                                     

    __doc__ = property((lambda self: self.doc))
    # When a Parameter is owned by a ParameterizedObject, we want the
    # documentation for that object to print the doc slot for this
    # parameter, not the __doc__ value for the Parameter class or
    # subclass.  For instance, if we have a ParameterizedObject class X with
    # parameters y(doc="All about y") and z(doc="More about z"),
    # help(X) should include "All about y" in the section describing
    # y, and "More about z" in the section about z.
    #
    # We currently achieve this by making __doc__ return the value of
    # self.doc, using the code below.
    #
    # NOTE: This code must also be copied to any subclass of
    # Parameter, or else the documentation for y and z above will
    # be the documentation for their Parameter class, not those
    # specific parameters.
    #
    # JABHACKALERT: Unfortunately, this trick makes the documentation
    # for Parameter and its subclasses invisible, so that e.g.
    # help(Parameter) and help(Number) do not include the usual
    # docstring defined in those classes.  We could save a copy of
    # that docstring in a class attribute, and it *may* be possible
    # somehow to return that for help(Parameter), without breaking the
    # current support for help(X) (where X is a ParameterizedObject and help(X)
    # describes X's specific Parameters).  Seems difficult, though.



    def __init__(self,default=None,doc=None,hidden=False,
                 precedence=None,instantiate=False,constant=False):
        """
        Initialize a new Parameter object: store the supplied attributes.


        default: the owning class's value for the attribute
        represented by this Parameter.

        hidden is a flag that allows objects using Parameters to know
        whether or not to display them to the user (e.g. in GUI menus).

        precedence is a value, usually in the range 0.0 to 1.0, that
        allows the order of Parameters in a class to be defined (again
        for e.g. in GUI menus).

        default, doc, and precedence default to None. This is to allow
        inheritance of Parameter slots (attributes) from the owning-class'
        class hierarchy (see ParameterizedObjectMetaclass).
        """
        # CEBALERT: make sure that subclass authors have also declared
        # __slots__, so we get the optimization of no
        # dictionaries. Ideally, we'd like to check this with
        # something like pychecker instead.
        # We also need to check that subclasses have a __doc__ attribute.
        assert not hasattr(self,'__dict__'), \
               "Subclasses of Parameter should define __slots__; " \
               + `type(self)` + " does not."


        self._attrib_name = None  # used to cache attrib_name
        self.hidden=hidden
        self.precedence = precedence
        self.default = default
        self.doc = doc
        self.constant = constant
        # constant => instantiate
        self.instantiate = instantiate or constant

        
    def __get__(self,obj,objtype):
        """
        Return the value for this Parameter.

        If called for a ParameterizedObject class, produce that
        class's value (i.e. this Parameter object's 'default'
        attribute).

        If called for a ParameterizedObject instance, produce that
        instance's value, if one has been set - otherwise produce the
        class's value (default).
        """
        # NB: obj can be None (when __get__ called for a
        # ParameterizedObject class); objtype is never None
        
        if not obj:
            result = self.default
        else:
            result = obj.__dict__.get(self.internal_name(obj),self.default)
        return result
        

    def __set__(self,obj,val):
        """
        Set the value for this Parameter.

        If called for a ParameterizedObject class, set that class's
        value (i.e. set this Parameter object's 'default' attribute).

        If called for a ParameterizedObject instance, set the value of
        this Parameter on that instance (i.e. in the instance's
        __dict__, under the parameter's internal_name). 

        
        If the Parameter's constant attribute is True, only allows
        the value to be set for a ParameterizedObject class or on
        uninitialized ParameterizedObject instances.
        
        Note that until Topographica supports some form of read-only
        object, it is still possible to change the attributes of the
        object stored in a constant (e.g. the left bound of a
        BoundingBox).
        """
        # NB: obj can be None (when __set__ called for a
        # ParameterizedObject class)
        if self.constant:
            if not obj:
                self.default = val
            elif not obj.initialized:
                obj.__dict__[self.internal_name(obj)] = val
            else:
                raise TypeError("Constant parameter %s cannot be modified"%self.attrib_name)

        else:
            if not obj:
                self.default = val
            else:
                obj.__dict__[self.internal_name(obj)] = val
                

    def __delete__(self,obj):
        raise TypeError("Cannot delete %s: Parameters deletion not allowed."%self.attrib_name)


    def internal_name(self,obj):
        """
        Return the internal name (e.g. _X_param_name for attrib_name
        X) that the specified ParameterizedObject instance has (or
        would have*) for this parameter.

        * if the Parameter has not actually been set on ths instance,
        then internal_name will not be in the instance's __dict__
        """
        return '_%s_param_value'%self.attrib_name(obj,None)


    def attrib_name(self,obj=None,objtype=None):
        """
        Return the attribute name represented by this Parameter.
        
        Guarantees to return the attrib_name if at least one of obj
        and objtype is supplied; if neither obj nor objtype is
        supplied, and _discover_attrib_name has not previously been
        called successfully, an empty string will be returned.
        """
        return self._attrib_name or self._discover_attrib_name(obj,objtype)


    def _discover_attrib_name(self,obj,objtype):
        """
        Discover the name of the attribute this Parameter is
        representing (and cache a successful result in _attrib_name).

        Guarantees to return the attrib_name if at least one of obj
        and objtype is supplied; if neither obj nor objtype is
        supplied, an empty string will be returned.
        """
        # The parameter object itself does not initially know the name
        # of the attribute that it is representing, but it can discover
        # that name by looking for itself in the owning class hierarchy.

        if obj and not objtype: objtype = type(obj)

        classes = classlist(objtype)[::-1]
        for class_ in classes:
            for attrib_name in dir(class_):
                if hasattr(class_,'get_param_descriptor'):
                    desc,desctype = class_.get_param_descriptor(attrib_name)
                    if desc is self:
                        self._attrib_name = attrib_name
                        return attrib_name
                    
        return '' # could maybe rewrite this method so it's clearer
    

    def __getstate__(self):
        """
        All Parameters have slots, not a dict, so we have to support
        pickle and deepcopy ourselves.
        """
        # The only complication is that a subclass' __slots__ do
        # not contain superclass' __slots__ (the superclass' __slots__
        # end up as attributes of the subclass).
        classes = [klass for klass in classlist(type(self))
                   if hasattr(klass,'__slots__')]
        
        all_slots = []
        for klass in classes:
            all_slots+=klass.__slots__
        
        state = {}
        for slot in all_slots:
            state[slot] = getattr(self,slot)

        return state

    def __setstate__(self,state):
        """See __getstate__()"""
        for (k,v) in state.items():
            setattr(self,k,v)    



class ParameterizedObjectMetaclass(type):
    """
    The metaclass of ParameterizedObject (and all its descendents).

    The metaclass overrides type.__setattr__ to allow us to set
    Parameter values on classes without overwriting the attribute
    descriptor.  That is, for a ParameterizedObject of type X with a
    Parameter y, the user can type X.y=3, which sets the default value
    of Parameter y to be 3, rather than overwriting y with the
    constant value 3 (and thereby losing all other info about that
    Parameter, such as the doc string, bounds, etc.).

    The __init__ method is used when defining a ParameterizedObject
    class, usually when the module where that class is located is
    imported for the first time.  That is, the __init__ in this
    metaclass initializes the *class* object, while the __init__
    method defined in each ParameterizedObject class is called for
    each new instance of that class.

    Additionally, a class can declare itself abstract by having an
    attribute __abstract set to True. The 'abstract' attribute can be
    used to find out if a class is abstract or not.
    """    
    def __init__(self,name,bases,dict):
        """
        Initialize the class object (not an instance of the class, but the class itself).

        Initializes all the Parameters by looking up appropriate
        default values; see __param_inheritance().
        """
        type.__init__(self,name,bases,dict)

        # All objects (with their names) of type Parameter that are
        # defined in this class
        parameters = [(name,obj)
                      for (name,obj) in dict.items()
                      if isinstance(obj,Parameter)]
        
        for param_name,param in parameters:
            self.__param_inheritance(param_name,param)


    def __is_abstract(self):
        """
        Return True if the class has an attribute __abstract set to True.  
        Subclasses will return False unless they themselves have
        __abstract set to true.  This mechanism allows a class to
        declare itself to be abstract (e.g. to avoid it being offered
        as an option in a GUI), without the "abstract" property being
        inherited by its subclasses (at least one of which is
        presumably not abstract).
        """
        # Can't just do ".__abstract", because that is mangled to
        # _ParameterizedObjectMetaclass__abstract before running, but
        # the actual class object will have an attribute
        # _ClassName__abstract.  So, we have to mangle it ourselves at
        # runtime.
        try:
            return getattr(self,'_%s__abstract'%self.__name__)
        except AttributeError:
            return False
        
    abstract = property(__is_abstract)



    def __setattr__(self,attribute_name,value):
        """
        Implements 'self.attribute_name=value' in a way that also supports Parameters.

        If there is already a descriptor named attribute_name, and
        that descriptor is a Parameter, and the new value is *not* a
        Parameter, then call that Parameter's __set__ method with the
        specified value.
        
        In all other cases set the attribute normally (i.e. overwrite
        the descriptor).  If the new value is a Parameter, once it has
        been set we make sure that the value is inherited from
        ParameterizedObject superclasses as described in __param_inheritance().
        """        
        # Find out if there's a Parameter called attribute_name as a
        # class attribute of this class - if not, parameter is None.
        parameter,owning_class = self.get_param_descriptor(attribute_name)

        if parameter and not isinstance(value,Parameter):
            if owning_class != self:
                type.__setattr__(self,attribute_name,copy.copy(parameter))
            self.__dict__[attribute_name].__set__(None,value)

        else:    
            type.__setattr__(self,attribute_name,value)
            
            if isinstance(value,Parameter):
                self.__param_inheritance(attribute_name,value)
            else:
                print ("Warning: Setting non-Parameter class attribute %s.%s = %s "
                       % (self.__name__,attribute_name,`value`))

                
    def __param_inheritance(self,param_name,param):
        """
        Look for Parameter values in superclasses of this ParameterizedObject.

        Ordinarily, when a Python object is instantiated, attributes
        not given values in the constructor will inherit the value
        given in the object's class, or in its superclasses.  For
        Parameters owned by ParameterizedObjects, we have implemented an
        additional level of default lookup, should this ordinary
        lookup return only None.

        In such a case, i.e. when no non-None value was found for a
        Parameter by the usual inheritance mechanisms, we explicitly
        look for Parameters with the same name in superclasses of this
        ParameterizedObject, and use the first such value that we find.

        The goal is to be able to set the default value (or other
        slots) of a Parameter within a ParameterizedObject, just as we can set
        values for non-Parameter objects in ParameterizedObjects, and have the
        values inherited through the ParameterizedObject hierarchy as usual.
        """
        # get all relevant slots (i.e. slots defined in all superclasses of
        # this parameter)
        slots = {}
        for p_class in classlist(type(param)):
            if hasattr(p_class,'__slots__'):
                slots.update(dict.fromkeys(p_class.__slots__))

        # This is to make CompositeParameter.__set__ work
        # properly. Unlike __get__, the __set__ method of an attribute
        # descriptor doesn't get passed any indication of what class
        # it belongs to, when called without an instance.  In order
        # for CompositeParameter.__set__ to work, it needs to know
        # what class the Parameter belongs to. This code looks finds
        # any parameter with a slot named 'objtype' and sets the
        # slot's value to the current type (i.e. self).
        # JPALERT: This feels hackish.  Not sure if there's a better
        # way.  On the other hand, this mechanism might be useful for
        # other parameters too.
        if 'objtype' in slots:
            setattr(param,'objtype',self)
            del slots['objtype']
            

        for slot in slots.keys():
            superclasses = iter(classlist(self)[::-1])

            # Search up the hierarchy until param.slot (which
            # has to be obtained using getattr(param,slot))
            # is not None, or we run out of classes to search.
            #
            # CEBALERT: there's probably a better way than while
            # and an iterator, but it works.
            while getattr(param,slot)==None:
                try:
                    param_super_class = superclasses.next()
                except StopIteration:
                    break

                new_param = param_super_class.__dict__.get(param_name)
                if new_param != None and hasattr(new_param,slot):
                    # (slot might not be there because could be a more
                    # general type of Parameter)
                    new_value = getattr(new_param,slot)
                    setattr(param,slot,new_value)

        
    def get_param_descriptor(self,param_name):
        """
        Goes up the class hierarchy (starting from the current class)
        looking for a Parameter class attribute param_name. As soon as
        one is found as a class attribute, that Parameter is returned
        along with the class in which it is declared.
        """
        classes = classlist(self)
        for c in classes[::-1]:
            attribute = c.__dict__.get(param_name)
            if isinstance(attribute,Parameter):
                return attribute,c
        return None,None








# JABALERT: Only partially achieved so far -- objects of the same
# type and parameter values are treated as different, so anything
# for which instantiate == True is reported as being non-default.
# Note that this module-level Parameter won't actually do most 
# of the things a Parameter does, but using a Parameter here
# should be more readable anyway.

# CBERRORALERT: Parameters only work as expected inside ParameterizedObjects:
# >>> topo.base.parameterizedobject.script_repr_suppress_defaults=(Parameter=False)
# >>> topo.base.parameterizedobject.script_repr_suppress_defaults is True
# True
# In the case below, the behavior probably turns out ok because
# "if Parameter()" is True, and setting
# topo.base.parameterizedobject.script_repr_suppress_defaults=False
# just writes over the Parameter object anyway.
script_repr_suppress_defaults=Parameter(True, hidden=True, doc="""
    Whether script_repr should avoid reporting the values of parameters
    that are just inheriting their values from the class defaults.""")


dbprint_prefix=Parameter(None, hidden=True, doc="""
    If not None, the value of this Parameter will be called (using '()')
    before every call to __db_print, and is expected to evaluate to a
    string that is suitable for prefixing messages and warnings (such
    as some indicator of the global state).""")


    

class ParameterizedObject(object):
    """
    Base class for named objects that support Parameters and message formatting.
    
    Automatic object naming: Every ParameterizedObject has a name
    parameter.  If the user doesn't designate a name=<str> argument
    when constructing the object, the object will be given a name
    consisting of its class name followed by a unique 5-digit number.
    
    Automatic parameter setting: The ParameterizedObject __init__
    method will automatically read the list of keyword parameters.  If
    any keyword matches the name of a Parameter (see Parameter class)
    defined in the object's class or any of its superclasses, that
    parameter in the instance will get the value given as a keyword
    argument.  For example:
    
      class Foo(ParameterizedObject):
         xx = Parameter(default=1)
    
      foo = Foo(xx=20)
    
    in this case foo.xx gets the value 20.
    
    Message formatting: Each ParameterizedObject has several methods
    for optionally printing output according to the current 'print
    level', such as SILENT, WARNING, MESSAGE, VERBOSE, or DEBUG.  Each
    successive level allows more messages to be printed.  For example,
    when the level is VERBOSE, all warning, message, and verbose
    output will be printed.  When it is WARNING, only warnings will be
    printed.  When it is SILENT, no output will be printed.
    
    For each level (except SILENT) there's an associated print method:
    ParameterizedObject.warning(), .message(), .verbose(), and .debug().
    
    Each line printed this way is prepended with the name of the
    object that printed it.  The ParameterizedObject parameter
    print_level, and the module global variable min_print_level
    combine to determine what gets printed.  For example, if foo is a
    ParameterizedObject:
    
       foo.message('The answer is',42)
    
    is equivalent to:
    
       if max(foo.print_level,base.min_print_level) >= MESSAGE:
           print foo.name+':', 'The answer is', 42
    """

    __metaclass__ = ParameterizedObjectMetaclass

    ## CEBALERT: should be StringParameter, right?
    name           = Parameter(default=None,doc="String identifier for this object.")
    ### JABALERT: Should probably make this an Enumeration instead.
    print_level = Parameter(default=MESSAGE,hidden=True)

    
    def __init__(self,**params):
        """
        Initialize this ParameterizedObject.

        The values of parameters can be supplied as keyword arguments
        to the constructor (using parametername=parametervalue); these
        values will override the class default values for this one
        instance.

        If no 'name' parameter is supplied, self.name defaults to the
        object's class name with a unique number appended to it.
        """
        global object_count

        # Flag that can be tested to see if e.g. constant Parameters
        # can still be set
        self.initialized=False

        self.__generate_name()
        
        self._setup_params(**params)
        object_count += 1

        self.nopickle = []
        self.debug('Initialized',self)

        self.initialized=True


    def __generate_name(self):
        """
        Set name to a gensym formed from the object's type name and
        the object_count.
        """
        self.name = '%s%05d' % (self.__class__.__name__ ,object_count)


    def __repr__(self):
        """
        Provide a nearly valid Python representation that could be used to recreate
        the item with its parameters, if executed in the appropriate environment.
        
        Returns 'classname(parameter1=x,parameter2=y,...)', listing
        all the parameters of this object.
        """
        settings = ['%s=%s' % (name,repr(val))
                    for name,val in self.get_param_values()]
        return self.__class__.__name__ + "(" + ", ".join(settings) + ")"


    def script_repr(self,imports=[],prefix="    "):
        """
        Variant of __repr__ designed for generating a runnable script.
        """
        # Suppresses automatically generated names and print_levels.
        settings=[]
        for name,val in self.get_param_values(onlychanged=script_repr_suppress_defaults):
            if name == 'name' and re.match('^'+self.__class__.__name__+'[0-9]+$',val):
                rep=None
            elif name == 'print_level':
                rep=None
            elif isinstance(val,ParameterizedObject):
                rep=val.script_repr(imports=imports,prefix=prefix+"    ")
            elif isinstance(val,list):
                result=[]
                for i in val:
                    if hasattr(i,'script_repr'):
                        result.append(i.script_repr(imports=imports,prefix=prefix+"    "))
                    else:
                        result.append(repr(i))
                rep='['+','.join(result)+']'
            else:
                rep=repr(val)
            if rep is not None:
                settings.append('%s=%s' % (name,rep))

        # Generate import statement
        cls = self.__class__.__name__
        mod = self.__module__
        imports.append("from %s import %s" % (mod,cls))

        return self.__class__.__name__ + "(" + (",\n"+prefix).join(settings) + ")"

        
    def __str__(self):
        """Return a short representation of the name and class of this object."""
        return "<%s %s>" % (self.__class__.__name__,self.name)


    def __db_print(self,level=NORMAL,*args):
        """
        Print each of the given args iff print_level or
        self.db_print_level is greater than or equal to the given
        level.
        """
        if level <= max(min_print_level,self.print_level):
            s = ' '.join([str(x) for x in args])
            
            if dbprint_prefix and callable(dbprint_prefix):
                prefix=dbprint_prefix()
            else:
                prefix=""
                
            print "%s%s: %s" % (prefix,self.name,s)
            
        sys.stdout.flush()


    def warning(self,*args):
        """
        Print the arguments as a warning, unless module variable
        warnings_as_exceptions is True, then raise an Exception
        containing the arguments.
        """

        if not warnings_as_exceptions:
            self.__db_print(WARNING,"Warning:",*args)
        else:
            raise Exception, ' '.join(["Warning:",]+[str(x) for x in args])

    def message(self,*args):
        """Print the arguments as a message."""
        self.__db_print(MESSAGE,*args)
        
    def verbose(self,*args):
        """Print the arguments as a verbose message."""
        self.__db_print(VERBOSE,*args)
        
    def debug(self,*args):
        """Print the arguments as a debugging statement."""
        self.__db_print(DEBUG,*args)


    def _setup_params(self,**params):
        """
        Initialize default and keyword parameter values.

        First, ensures that all Parameters with 'instantiate=True'
        (typically used for mutable Parameters) are copied directly
        into each object, to ensure that there is an independent copy
        (to avoid suprising aliasing errors).  Then sets each of the
        keyword arguments, warning when any of them are not defined as
        parameters.
        """
        # Deepcopy all 'instantiate=True' parameters
        for class_ in classlist(type(self)):
            for (k,v) in class_.__dict__.items():
                if isinstance(v,Parameter) and v.instantiate:
                    new_object = copy.deepcopy(v.default)
                    self.__dict__[v.internal_name(self)]=new_object

                    # a new ParameterizedObject needs a new name
                    # CEBHACKALERT: this will write over any name given
                    # to the original object.
                    if isinstance(new_object,ParameterizedObject):
                        global object_count
                        object_count+=1
                        new_object.initialized=False
                        new_object.__generate_name()
                        new_object.initialized=True
                    
        for name,val in params.items():
            desc,desctype = self.__class__.get_param_descriptor(name)
            if desc:
                self.debug("Setting param %s ="%name, val)
            else:
                self.warning("CANNOT SET non-parameter %s ="%name, val)
            # i.e. if not desc it's setting an attribute in __dict__, not a Parameter
            setattr(self,name,val)


    def _check_params(self,params):
        """
        Print a warning if params contains something that is
        not a Parameter of this object.

        Typically invoked by a __call__() method that accepts keyword
        arguments for parameter setting.
        """
        for item in params:
            if item not in self.params():
                self.warning("'%s' was ignored (not a Parameter)."%item)


    def get_param_values(self,onlychanged=False):
        """Return a list of name,value pairs for all Parameters of this object"""
        vals = []
        for name,val in self.params().items():
            value = self.repr_value(name)
            if (not onlychanged or value != val.default):
                vals.append((name,value))

        vals.sort(key=lambda x:x[0])
        return vals



    # CEBALERT: the class equivalents of these are missing
    # (i.e. one can't yet do Gaussian.inspect_value('x') )
    
    # CEBALERT: can someone make this more elegant? Or at least
    # suggest some better names and help with the documentation?
    # Maybe it was better with the duplicated code?
    #
    # do I have to pass the method? Can't I get it somehow?
    def repr_value(self,name):
        """
        Return the object that generates the value of the named attribute.

        Same as getattr() except for Dynamic parameters, which have their
        value-generating object returned.
        """
        return self.__shenma(name,self.repr_value,"_%s_param_value"%name,'default')


    def inspect_value(self,name):
        """
        Return the current value of the named attribute without modifying it.

        Same as getattr() except for Dynamic parameters, which have their
        last value returned.
        """
        return self.__shenma(name,self.inspect_value,"_%s_param_value_last"%name,'last_default')


    def is_dynamically_generated(self,name):
        """
        Return True if the attribute is a parameter being dynamically
        generated, otherwise return False.
        """
        # this method is for convenience: just avoids people having to investigate Dynamic
        param_obj = self.params().get(name)
        
        if not param_obj:
            return False
        else:
            return param_obj._value_is_dynamically_generated(self)
        

    def __shenma(self,name,mthd,local_attr_name,param_attr_name):
        """
        Get the attribute specified by name; for non-parameters, this is the same
        as getattr(), but for Parameters:-

        * CompositeParameter: mthd is called for all attribs (recursive) 
        * Dynamic Parameters: look for local_attr_name in this object's dictionary;
          if that's not found, find param_attr_name on the Parameter itself.
        """
        param_obj = self.params().get(name)

        if not param_obj:
            value = getattr(self,name)

        # CompositeParameter detected by being a Parameter and having 'attribs'
        elif hasattr(param_obj,'attribs'):
            value = [mthd(a) for a in param_obj.attribs]

        # not a Dynamic Parameter 
        elif not hasattr(param_obj,'last_default'):
            value = getattr(self,name)

        # Dynamic Parameter...
        else:
            try:
                # ...which had been set on this object
                value = self.__dict__[local_attr_name]
            except KeyError:
                # ...not set on object:
                value = getattr(param_obj,param_attr_name)

        return value


    def print_param_values(self):
        for name,val in self.get_param_values():
            print '%s.%s = %s' % (self.name,name,val)

            
    def __getstate__(self):
        """
        Save the object's state: return a dictionary that is a shallow
        copy of the object's __dict__, except that entries in __dict__
        which are Parameters get deep copied.

        (i.e. we assume mutable objects are in Parameters.)

        ParameterizedObjects always have a __dict__ and do not have __slots__.
        """
        # shallow copy the __dict__ because we change some entries
        state = self.__dict__.copy()

##  JPHACKALERT: After discussing with JAB and CEB, I'm commenting out
##  these entire functions, because they seem to only exist for the
##  purpose of deepcopying the parameters, which is (probably?) not
##  necessary.  Note that this function and the accompanying
##  __setstate__ don't seem to do anything useful -- they just copy
##  self.__dict__ -- but I get weird warnings from 'make tests' if I
##  remove them.

## CB: __setstate__ exists only to set 'self.initialized'. If that
## were not necessary, we wouldn't need it; that is, __setstate__ does
## not exist to support pickling, but to work around problems
## setting Constant parameters when either copying or recreating (unpickling)
## parameterized objects (I can't remember which -- maybe it's both).

## The weird warnings caused by removing __gestate__ appear to be from
## something internal to python's default handling of getstate and
## setstate; python seems to pass around some seemingly undocumented
## __slotnames__ thing in the keyword arguments, and of course we
## assume things in keywords are parameters to be set on parameterized
## objects, hence the weird warnings. Anyone want to look at the
## source code for python? Because it seems like otherwise we could
## delete this __getstate__ method.
## (Why would there be anything to do with slots for ParameterizedObjects,
## anyway?)

        # CB (note to myself): note that this code applies *only* when
        # a __something_param_value contains a Parameter.
        # e.g. k is a ParameterizedObject with a Parameter p.
        #   k.p = DynamicNumber(something)
        # k.p is then a Parameter itself. 
        
        # deep copy Parameters; overwrites their original shallow copies 
##         for (k,v) in self.__dict__.items():
##             if isinstance(v,Parameter):
##                 state[k] = copy.deepcopy(v)

        return state


    def __setstate__(self,state):
        """
        Restore objects from the state dictionary to this object.

        During this process the object is considered uninitialized.
        """
        self.initialized=False
        
        for k,v in state.items():
            setattr(self,k,v)
            
        self.initialized=True


    @classmethod
    def params(cls):
        """
        Return the Parameters of this class as the
        dictionary {name: parameter_object}

        Includes Parameters from this class and its
        superclasses.
        """
        paramdict = {}
        for class_ in classlist(cls):
            for name,val in class_.__dict__.items():
                if isinstance(val,Parameter):
                    paramdict[name] = val
        return paramdict


    @classmethod
    def print_param_defaults(cls):
        for key,val in cls.__dict__.items():
            if isinstance(val,Parameter):
                print cls.__name__+'.'+key, '=', repr(val.default)




    # CEBALERTs:
    # * name should be a constant Parameter, rather than needing to test
    #   specially for name here
    # * what happens to dynamic parameters?
    # * doing the right thing for instantiate? (see note below)
    def defaults(self):
        """
        Return {parameter_name:parameter.default} for all non-constant
        Parameters.

        Note that a Parameter for which instantiate==True has its default
        instantiated.
        """
        d = {}
        for param_name,param in self.params().items():
            if param.constant or param_name=='name': # fake constant name
                pass
            # CEBHACKALERT
            elif param.instantiate:
                # should use other code to instantiate. missing
                # object count increase, etc? need some method to
                # do this for everywhere that needs it?
                d[param_name]=copy.deepcopy(param.default)
            else:
                d[param_name]=param.default
        return d

        


def print_all_param_defaults():
    print "_______________________________________________________________________________"
    print ""
    print "                           Parameter Default Values"
    print ""
    classes = descendents(ParameterizedObject)
    classes.sort(key=lambda x:x.__name__)
    for c in classes:
        c.print_param_defaults()
    print "_______________________________________________________________________________"





import __main__
import inspect
class PicklableClassAttributes(object):
    """
    Supports pickling of ParameterizedObject class attributes for a given module.

    When requested to be pickled, stores a module's PO classes' attributes,
    and any given startup_commands. On unpickling, executes the startup
    commands and sets the class attributes.
    """
    # CB: might have mixed up module and package in the docs.
    def __init__(self,module,exclusions=(),startup_commands=()):
        """
        module: a module object, such as topo
        
        Any submodules listed by name in exclusions will not have their
        classes' attributes saved.
        """
        self.module=module
        self.exclude=exclusions
        self.startup_commands=startup_commands
        
    def __getstate__(self):
        """
        Return a dictionary of self.module's PO classes' attributes, plus
        self.startup_commands.
        """
        # warn that classes & functions defined in __main__ won't unpickle
        import types
        for k,v in __main__.__dict__.items():
            # there's classes and functions...what else?
            if isinstance(v,type) or isinstance(v,types.FunctionType):
                if v.__module__ == "__main__":
                    ParameterizedObject().warning("%s (type %s) has source in __main__; it will only be found on unpickling if the class is explicitly defined (e.g. by running the same script first) before unpickling."%(k,type(v)))

        
        class_attributes = {}
        self.get_PO_class_attributes(self.module,class_attributes,[],exclude=self.exclude)

        # CB: we don't want to pickle anything about this object except what
        # we want to have executed on unpickling (this object's not going to be hanging around).
        return {'class_attributes':class_attributes,
                'startup_commands':self.startup_commands}


    def __setstate__(self,state):
        """
        Execute the startup commands and set class attributes.
        """
        self.startup_commands = state['startup_commands']
        
        for cmd in self.startup_commands:
            exec cmd in __main__.__dict__
            
        for class_name,state in state['class_attributes'].items():
            
            # from "topo.base.parameter.Parameter", we want "topo.base.parameter"
            module_path = class_name[0:class_name.rindex('.')]
            exec 'import '+module_path in __main__.__dict__
            
            # now restore class Parameter values
            for p_name,p in state.items():
                # CEBHACKALERT: doesn't seem like a great mechanism;
                # could write over a user's variable?
                __main__.__dict__['val'] = p
                try:
                    exec 'setattr('+class_name+',"'+p_name+'",val)' in __main__.__dict__
                except:
                    ParameterizedObject().warning('Problem restoring parameter %s=%s for class %s; name may have changed since the snapshot was created.' % (p_name,repr(p),class_name))


    # CEBALERT: might could be simplified
    # (in addition to simplifications that could be made now this is a method rather than
    # a standalone function).
    def get_PO_class_attributes(self,module,class_attributes,processed_modules,exclude=()):
        """
        Recursively search module and get attributes of ParameterizedObject classes within it.

        class_attributes is a dictionary {module.path.and.Classname: state}, where state
        is the dictionary {attribute: value}.

        Something is considered a module for our purposes if inspect says it's a module,
        and it defines __all__. We only search through modules listed in __all__.

        Keeps a list of processed modules to avoid looking at the same one
        more than once (since e.g. __main__ contains __main__ contains
        __main__...)

        Modules can be specifically excluded if listed in exclude.
        """
        dict_ = module.__dict__
        for (k,v) in dict_.items():
            if '__all__' in dict_ and inspect.ismodule(v) and k not in exclude:
                if k in dict_['__all__'] and v not in processed_modules:
                    self.get_PO_class_attributes(v,class_attributes,processed_modules,exclude)
                processed_modules.append(v)

            else:
                if isinstance(v,type) and issubclass(v,ParameterizedObject):

                    # Note: we take the class name as v.__name__, not k, because
                    # k might be just a label for the true class. For example,
                    # if Topographica falls back to the unoptimized components,
                    # k could be "CFPRF_DotProduct_opt", but v.__name__
                    # - and the actual class - is "CFPRF_DotProduct". It
                    # is correct to set the attributes on the true class.
                    full_class_path = v.__module__+'.'+v.__name__
                    class_attributes[full_class_path] = {}
                    # POs always have __dict__, never slots
                    for (name,obj) in v.__dict__.items():
                        if isinstance(obj,Parameter):
                            class_attributes[full_class_path][name] = obj

