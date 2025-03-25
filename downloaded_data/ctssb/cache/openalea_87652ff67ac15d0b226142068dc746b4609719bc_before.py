# -*- python -*-
#
#       OpenAlea.Core: OpenAlea Core
#
#       Copyright or (C) or Copr. 2006 INRIA - CIRAD - INRA  
#
#       File author(s): Samuel Dufour-Kowalski <samuel.dufour@sophia.inria.fr>
#                       Christophe Pradal <christophe.prada@cirad.fr>
#
#       Distributed under the Cecill-C License.
#       See accompanying file LICENSE.txt or copy at
#           http://www.cecill.info/licences/Licence_CeCILL-C_V1-en.html
# 
#       OpenAlea WebSite : http://openalea.gforge.inria.fr
#


__doc__="""
Node and NodeFactory classes.

A Node is generalized functor which is embeded in a dataflow.
A Factory build Node from its description. Factories instantiate
Nodes on demand for the dataflow.
"""

__license__= "Cecill-C"
__revision__=" $Id$ "

import imp
import inspect
import os, sys
import string
import types


#from signature import get_parameters
import signature as sgn
from observer import Observed, AbstractListener

# Exceptions
class RecursionError (Exception):
    pass

class InstantiationError(Exception):
    pass


##############################################################################

def gen_port_list(size):
    """ Generate a list of port description """
    l = []
    for i in range(size):
        l.append(dict(name=str(i), interface=None, value=None))
    return l



###############################################################################


class Node(Observed):
    """
    A Node is the atomic entity in a dataflow.
    It is a callable object with typed inputs and outputs.
    Inputs and Outpus are indexed by their position or by a name (str)
    """

    def __init__(self, inputs=(), outputs=()):
        """
        @param inputs    : list of dict(name='X', interface=IFloat, value=0)
        @param outputs   : list of dict(name='X', interface=IFloat)

        Nota : if IO names are not a string, they will be converted to with str()
        """

        Observed.__init__(self)

        # Values
        self.inputs = []
        self.outputs = []

        # Description (list of dict (name=, interface=, ...))
        self.input_desc = []
        self.output_desc = []        
        
        self.map_index_in = {}
        self.map_index_out = {}

        # Input states : "connected", "hidden"
        self.input_states = []

        # Node State
        self.modified = True
        # Lazy State : if False, disable lazy evaluation
        self.lazy = True

        # Factory
        self.factory = None

        # Internal Data (caption...)
        self.internal_data = {}
        self.internal_data['caption'] = str(self.__class__.__name__)

        # Process in and out
        if(inputs):
            for d in inputs:
                self.add_input(**d)
        if(outputs):
            for d in outputs:
                self.add_output(**d)


    def __call__(self, inputs = ()):
        """ Call function. Must be overriden """
        
        raise NotImplementedError()


    def get_obj(self):
        return self

    obj = property(get_obj)


    # Accessor
    def get_factory(self):
        """ Return the factory of the node (if any) """
        return self.factory


    # Internal data accessor
    def set_caption(self, newcaption):
        """ Define the node caption """
        self.internal_data['caption'] = newcaption
        self.notify_listeners( ("caption_modified",) )


    def set_data(self, key, value):
        """ Set internal node data """
        self.internal_data[key] = value
        self.notify_listeners( ("data_modified",) )


    # Status
    def unvalidate_input(self, index_key):
        """ Unvalidate node and notify listeners """
        self.modified = True
        index = self.map_index_in[index_key]
        self.notify_listeners( ("input_modified", index) )


    # Declarations
    def add_input(self, **kargs):
        """ Create an input port """

        # Get parameters
        name = str(kargs['name'])
        interface = kargs.get('interface', None)
        value = kargs.get('value', None)

        # default value
        if(interface and value==None):
            value = interface.default()
            
        name = str(name) #force to have a string
        self.inputs.append( value )

        self.input_desc.append(kargs)
        
        self.input_states.append(None)
        index = len(self.inputs) - 1
        self.map_index_in[name] = index 
        self.map_index_in[index]= index 


    def add_output(self, **kargs):
        """ Create an output port """

        # Get parameters
        name = str(kargs['name'])
        self.outputs.append( None )
        
        self.output_desc.append(kargs)
        index =  len(self.outputs) - 1
        self.map_index_out[name] = index
        self.map_index_out[index]= index 


    # I/O Functions
   
    def get_input(self, index_key):
        """ Return an input port value """
        
        index = self.map_index_in[index_key]
        return self.inputs[index]


    def set_input(self, index_key, val):
        """ Define the input value for the specified index/key """
        
        index = self.map_index_in[index_key]

        changed = True
        if(self.lazy):
            # Test if the inputs has changed
            try:
                changed = (self.inputs[index] != val)
            except:
                pass

        if(changed):
            self.inputs[index] = val
            self.unvalidate_input(index)


    def get_output(self, index_key):
        """ Return the output for the specified index/key """
        index = self.map_index_out[index_key]
        return self.outputs[index]


    def set_output(self, index_key, val):
        """ Set the output value for the specified index/key """
        index = self.map_index_out[index_key]
        self.outputs[index] = val


    def get_input_state(self, index_key):
        index = self.map_index_in[index_key]
        return self.input_states[index]

    
    def set_input_state(self, index_key, state):
        """ Set the state of the input index/key (state is a string) """
        
        index = self.map_index_in[index_key]
        self.input_states[index] = state
        self.unvalidate_input(index)


    def get_input_index(self, key):
        """ Return the index of input identified by key """
        return self.map_index_in[key]
    
        
    def get_nb_input(self):
        """ Return the nb of input ports """
        return len(self.inputs)

    
    def get_nb_output(self):
        """ Return the nb of output ports """
        return len(self.outputs)


    
    # Functions used by the node evaluator
    def eval(self):
        """
        Evaluate the node by calling __call__python inspect performance issue
        Return True if the node has been calculated
        """

        # lazy evaluation
        if(self.lazy and not self.modified):
            return False

        self.modified = False
        
        outlist = self.__call__(self.inputs)
        self.notify_listeners( ("status_modified",self.modified) )

        #if(not outlist) : return True
        
        if(not isinstance(outlist, tuple) and
           not isinstance(outlist, list)):
            outlist = (outlist,)

        for i in range( min ( len(outlist), len(self.outputs))):
            self.outputs[i] = outlist[i]

        return True

    #Shortcut for compatibility
    get_input_by_key = get_input
    set_input_by_key = set_input
    get_output_by_key = get_output
    set_output_by_key = set_output



###############################################################################

class FuncNode(Node):
    """ Node with external function or function """

    def __init__(self, inputs, outputs, func):
        """
        @param inputs    : list of dict(name='X', interface=IFloat, value=0)
        @param outputs   : list of dict(name='X', interface=IFloat)
        @param func : A function
        """

        Node.__init__(self, inputs, outputs)
        self.func = func
        self.__doc__ = func.__doc__


    def __call__(self, inputs = ()):
        """ Call function. Must be overriden """
        
        if(self.func):
            return self.func(*inputs)


    def get_obj(self):
        return self.func

    obj = property(get_obj)
    

###############################################################################


class AbstractFactory(Observed):
    """
    Abstract Factory is Factory base class
    """

    mimetype = "openalea/nodefactory"

    def __init__(self,
                 name,
                 description = '',
                 category = '',
                 inputs = None,
                 outputs = None,
                 lazy = False,
                 **kargs):
        
        """
        Create a factory.
        
        @param name : user name for the node (must be unique) (String)
        @param description : description of the node (String)
        @param category : category of the node (String)
        @param inputs : inputs description
        @param outputs : outputs description, value=0
        @param lazy : enable lazy evaluation (default = False)

        Nota : inputs and outputs parameters are list of dictionnary such
        inputs = (dict(name='x', interface=IInt, value=0,)
        outputs = (dict(name='y', interface=IInt)
        """
        
        Observed.__init__(self)

        # Factory info
        self.name = name
        self.description = description
        self.category = category

        self.package = None

        self.inputs = inputs
        self.outputs = outputs

        self.lazy = lazy


    def get_id(self):
        """ Return the node factory Id """
        return self.name


    def get_tip(self):
        """ Return the node description """

        return "Name : %s\n"%(self.name,) +\
               "Category  : %s\n"%(self.category,) +\
               "Description : %s\n"%(self.description,)

       
    def instantiate(self, call_stack=[]):
        """ Return a node instance
        @param call_stack : the list of NodeFactory id already in call stack
        (in order to avoir infinite recursion)
        """
        raise NotImplementedError()
    

    def instantiate_widget(self, node=None, parent=None, edit=False):
        """ Return the corresponding widget initialised with node"""
        raise NotImplementedError()

    
    def get_writer(self):
        """ Return the writer class """
        raise NotImplementedError()
    


class NodeFactory(AbstractFactory):
    """
    A Node factory is able to create nodes on demand,
    and their associated widgets.
    """

    def __init__(self,
                 name,
                 description = '',
                 category = '',
                 inputs = None,
                 outputs = None,
                 nodemodule = '',
                 nodeclass = None,
                 widgetmodule = None,
                 widgetclass = None,
                 search_path = [],
                 **kargs):
        
        """
        Create a node factory.
        
        @param name : user name for the node (must be unique) (String)
        @param description : description of the node (String)
        @param category : category of the node (String)
        @param nodemodule : python module to import for node (String)
        @param nodeclass :  node class name to be created (String)
        @param widgetmodule : python module to import for widget (String)
        @param widgetclass : widget class name (String)
        @param inputs : inputs description
        @param outputs : outputs description
        @param seach_path (opt) : list of directories where to search for module
        
        Nota : inputs and outputs parameters are list of dictionnary such
        inputs = (dict(name='x', interface=IInt, value=0,)
        outputs = (dict(name='y', interface=IInt)
        """
        
        AbstractFactory.__init__(self, name, description, category,
                                 inputs, outputs, **kargs)

        # Factory info
        self.nodemodule_name = nodemodule
        self.nodeclass_name = nodeclass
        self.widgetmodule_name = widgetmodule
        self.widgetclass_name = widgetclass

        # Cache
        self.nodeclass = None
        self.src_cache = None

        # Module path, value=0
        self.nodemodule_path = None
        self.search_path = search_path
        
        # Context directory
        # inspect.stack()[1][1] is the caller python module
        caller_dir = os.path.dirname(os.path.abspath(inspect.stack()[1][1]))
        if(not caller_dir in self.search_path):
            self.search_path.append(caller_dir)


    def __getstate__(self):
        """ Pickle function """
        odict = self.__dict__.copy() 
        odict['nodemodule_path'] = None
        odict['nodemodule'] = None
        odict['nodeclass'] = None      
        return odict
    
       
    def instantiate(self, call_stack=[]):
        """ Return a node instance
        @param call_stack : the list of NodeFactory id already in call stack
        (in order to avoir infinite recursion)
        """
        
        module = self.get_node_module()
        classobj = module.__dict__[self.nodeclass_name]

        
        # If class is not a Node, embed object in a Node class
        if(not hasattr(classobj, 'mro') or not Node in classobj.mro()):

            # Check inputs and outputs
            if(self.inputs == None) :
                s = sgn.Signature(classobj)
                self.inputs = s.get_parameters()
            if(self.outputs == None) : self.outputs = (dict(name="out", interface=None),)

 
            # Check and Instantiate if we have a functor class
            if((type(classobj) == types.TypeType)
               or (type(classobj) == types.ClassType)):

                classobj = classobj()
            
            node = FuncNode(self.inputs, self.outputs, classobj)
            node.set_caption(self.name)

        # Class inherits from Node
        else:
            try:
                node = classobj(self.inputs, self.outputs)
            except TypeError:
                node = classobj()
                
        node.factory = self
        node.lazy = self.lazy
        return node
                    

    def instantiate_widget(self, node=None, parent=None, edit=False):
        """ Return the corresponding widget initialised with node """

        # Code Editor
        if(edit):
            from openalea.visualea.code_editor import NodeCodeEditor
            return NodeCodeEditor(self, parent)

        # Node Widget
        if(node == None): node = self.instantiate()

        modulename = self.widgetmodule_name
        if(not modulename) :
            modulename = self.nodemodule_name

        
        # if no widget declared, we create a default one
        if(not modulename or not self.widgetclass_name) :

            from openalea.visualea.node_widget import DefaultNodeWidget
            return DefaultNodeWidget(node, parent)
        
        else:
            # load module
            (file, pathname, desc) = imp.find_module(modulename,\
                                                     self.search_path + sys.path)

            sys.path.append(os.path.dirname(pathname))
            module = imp.load_module(modulename, file, pathname, desc)
            sys.path.pop()
            
            if(file) : file.close()

            widgetclass = module.__dict__[self.widgetclass_name]
            return widgetclass(node, parent)

            

    def edit_widget(self, parent=None):
        """ Return the widget to edit the factory """
            

    def get_writer(self):
        """ Return the writer class """

        return PyNodeFactoryWriter(self)


    def get_node_module(self):
        """
        Return the python module object (if available)
        Raise an Import Error if no module is associated
        """

        if(self.nodemodule_name):

            # Test if the module is already in sys.modules
            if(self.nodemodule_name in sys.modules.keys()):
                m = sys.modules[self.nodemodule_name]
                self.nodemodule_path = m.__file__
                return m
            
            # load module
            (file, pathname, desc) = imp.find_module(self.nodemodule_name,
                                                     self.search_path + sys.path)
            self.nodemodule_path = pathname

            sys.path.append(os.path.dirname(pathname))
            nodemodule = imp.load_module(self.nodemodule_name, file, pathname, desc)
            sys.path.pop()
                
            if(file) : file.close()
            return nodemodule
                
        else :
            # By default use __builtin module
            import __builtin__
            return __builtin__
    

    def get_node_src(self):
        """
        Return a string containing the node src
        Return None if src is not available
        """

        # Return cached source if any
        if(self.src_cache) : return self.src_cache
        
        module = self.get_node_module()

        import linecache
        # get the code
        linecache.checkcache(self.nodemodule_path)
        cl = module.__dict__[self.nodeclass_name]
        return inspect.getsource(cl)

        
    def apply_new_src(self, newsrc):
        """
        Execute new src
        """
        module = self.get_node_module()
        # Run src
        exec newsrc in module.__dict__

        # save the current newsrc
        self.src_cache = newsrc


    def save_new_src(self, newsrc):
        
        module = self.get_node_module()
        nodesrc = self.get_node_src()
        
        # Run src
        exec newsrc in module.__dict__

        # get the module code
        import inspect
        modulesrc = inspect.getsource(module)

        # Pass if no modications
        if(nodesrc == newsrc) : return
        
        # replace old code with new one
        modulesrc = modulesrc.replace(nodesrc, newsrc)
        

        # write file
        file = open(self.nodemodule_path, 'w')
        file.write(modulesrc)
        file.close()

        # unload module
        if(self.nodemodule_name in sys.modules.keys()) : del(sys.modules[self.nodemodule_name])
        self.src_cache = None
 
        # Recompile
        import py_compile
        py_compile.compile(self.nodemodule_path)
        
        

#class Factory:
Factory = NodeFactory




###############################################################################

class NodeWidget(AbstractListener):
    """
    Base class for node instance widgets.
    """

    def __init__(self, node):
        """ Init the widget with the associated node """
        
        self.__node = node

        # register to observed node
        self.initialise(node)


    def get_node(self):
        """ Return the associated node """
        return self.__node


    def set_node(self, node):
        """ Define the associated node """
        self.__node = node

    node = property(get_node, set_node)


    def notify(self, sender, event):
        """
        This function is called by the Observed objects
        and must be overloaded
        """
        pass

    def is_empty( self ):
        return False
        


################################################################################
        


class PyNodeFactoryWriter(object):
    """ NodeFactory python Writer """

    nodefactory_template = """

    nf = Factory(name=$NAME, 
                 description=$DESCRIPTION, 
                 category=$CATEGORY, 
                 nodemodule=$NODEMODULE,
                 nodeclass=$NODECLASS,
                 inputs=$LISTIN,
                 outputs=$LISTOUT,
                 widgetmodule=$WIDGETMODULE,
                 widgetclass=$WIDGETCLASS,
                 )

    pkg.add_factory( nf )

"""

    def __init__(self, factory):
        self.factory = factory

    def __repr__(self):
        """ Return the python string representation """
        f = self.factory
        fstr = string.Template(self.nodefactory_template)
        result = fstr.safe_substitute(NAME=repr(f.name),
                                      DESCRIPTION=repr(f.description),
                                      CATEGORY=repr(f.category), 
                                      NODEMODULE=repr(f.nodemodule_name),
                                      NODECLASS=repr(f.nodeclass_name),
                                      LISTIN=repr(f.inputs),
                                      LISTOUT=repr(f.outputs),
                                      WIDGETMODULE=repr(f.widgetmodule_name),
                                      WIDGETCLASS=repr(f.widgetclass_name),)
        return result
           




   
        





        


