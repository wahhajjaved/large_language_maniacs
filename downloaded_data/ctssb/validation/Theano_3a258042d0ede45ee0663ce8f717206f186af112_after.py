"""Provide CudaNdarrayType
"""
import sys, os, StringIO
import numpy

from theano import Op, Type, Apply, Variable, Constant
from theano import tensor, config

import cuda_ndarray.cuda_ndarray as cuda
import cuda_ndarray

from theano.sandbox.cuda.nvcc_compiler import nvcc_module_compile_str

class CudaNdarrayType(Type):

    typenum = 11 # Until hardware improves, this class deals with floats.

    dtype = 'float32'

    Variable = None
    """ This will be set to the Variable type corresponding to this class.

    That variable type is `CudaNdarrayVariable` defined in the ``var.py`` file beside this one.

    :note: 
    The var file depends on the file basic_ops.py, which depends on this file.
    A cyclic dependency is avoided by not hardcoding ``Variable = CudaNdarrayVariable``.
    """

    Constant = None
    """ This will be set to `CudaNdarrayConstant` defined in ``var.py``

    :note: 
    The var file depends on the file basic_ops.py, which depends on this file.
    A cyclic dependency is avoided by not hardcoding this class. 
    """

    SharedVariable = None
    """ This will be set to `CudaNdarraySharedVariable` defined in ``var.py``

    :note: 
    The var file depends on the file basic_ops.py, which depends on this file.
    A cyclic dependency is avoided by not hardcoding this class. 
    """

    def __init__(self, broadcastable, name=None, dtype=None):
        if dtype != None and dtype != 'float32':
            raise TypeError(self.__class__.__name__+' only support dtype float32 for now.')
        self.broadcastable = tuple(broadcastable)
        self.name = name
        self.dtype_specs() # error checking is done there

    def filter(self, data, strict=False):
        return cuda.filter(data, self.broadcastable, strict)

    @staticmethod
    def values_eq(a, b):
        #TODO: make the comparaison without transfert.
        return tensor.TensorType.values_eq(numpy.asarray(a), numpy.asarray(b))

    @staticmethod
    def values_eq_approx(a, b):
        #TODO: make the comparaison without transfert.
        return tensor.TensorType.values_eq_approx(numpy.asarray(a), numpy.asarray(b))

    def dtype_specs(self):
        """Return a tuple (python type, c type, numpy typenum) that corresponds to
        self.dtype.
        
        This function is used internally as part of C code generation.
        """
        #TODO: add more type correspondances for e.g. int32, int64, float32,
        #complex64, etc.
        try:
            return {'float32': (float, 'npy_float32', 'NPY_FLOAT32'),
                    'float64': (float, 'npy_float64', 'NPY_FLOAT64'),
                    'uint8': (int, 'npy_uint8', 'NPY_UINT8'),
                    'int8': (int, 'npy_int8', 'NPY_INT8'),
                    'uint16': (int, 'npy_uint16', 'NPY_UINT16'),
                    'int16': (int, 'npy_int16', 'NPY_INT16'),
                    'uint32': (int, 'npy_uint32', 'NPY_UINT32'),
                    'int32': (int, 'npy_int32', 'NPY_INT32'),
                    'uint64': (int, 'npy_uint64', 'NPY_UINT64'),
                    'int64': (int, 'npy_int64', 'NPY_INT64'),
                    'complex128': (complex, 'theano_complex128', 'NPY_COMPLEX128'),
                    'complex64': (complex, 'theano_complex64', 'NPY_COMPLEX64')}[self.dtype]
        except KeyError:
            raise TypeError("Unsupported dtype for %s: %s" % (self.__class__.__name__, self.dtype))

    def __eq__(self, other):
        """Compare True iff other is the same kind of CudaNdarrayType"""
        return type(self) == type(other) and other.broadcastable == self.broadcastable

    def __hash__(self):
        """Hash equal for same kinds of CudaNdarrayType"""
        return hash(type(self)) ^ hash(self.broadcastable)

    ndim = property(lambda self: len(self.broadcastable), doc = "number of dimensions")
    """Number of dimensions

    This read-only property is the preferred way to get the number of dimensions
    of a `CudaNdarrayType`.
    
    """

    def make_variable(self, name = None):
        """Return a `TensorVariable` of this type

        :Parameters:
         - `name`: str
           A pretty name to identify this `Variable` when printing and debugging

        """
        return self.Variable(self, name = name)

    def __str__(self):
        if self.name:
            return self.name
        else:
            b = self.broadcastable
            #bcast = str(self.broadcastable)
            if not numpy.any(b):
                s="%iD" % len(b)
            else: s=str(b)

            bcast = {(): 'scalar',
                     (False,): 'vector',
                     (False, True): 'col',
                     (True, False): 'row',
                     (False, False): 'matrix'}.get(b, s)
            return "CudaNdarrayType(%s, %s)" % (str(self.dtype), bcast)

    def __repr__(self):
        return str(self)
        #"CudaNdarrayType{%s, %s}" % (str(self.dtype), str(self.broadcastable))

    def c_declare(self, name, sub):
        ndim = self.ndim
        c_typename = self.dtype_specs()[1]
        return """ CudaNdarray * %(name)s;""" %locals()

    def c_init(self, name, sub):
        return "%(name)s = NULL;" % locals()

    def c_extract(self, name, sub):
        sio = StringIO.StringIO()
        fail = sub['fail']
        nd = self.ndim
        print >> sio, """
        assert(py_%(name)s->ob_refcnt >= 2); // There should be at least one ref from the container object, 
        // and one ref from the local scope.

        if (CudaNdarray_Check(py_%(name)s))
        {
            //fprintf(stderr, "c_extract CNDA object w refcnt %%p %%i\\n", py_%(name)s, (py_%(name)s->ob_refcnt));
            %(name)s = (CudaNdarray*)py_%(name)s;
            //std::cerr << "c_extract " << %(name)s << '\\n';
            if (%(name)s->nd != %(nd)s)
            {
                PyErr_Format(PyExc_RuntimeError, "Some CudaNdarray has rank %%i, it was supposed to have rank %(nd)s", %(name)s->nd);
                %(name)s = NULL;
                %(fail)s;
            }
            //std::cerr << "c_extract " << %(name)s << " nd check passed\\n";
        """ %locals()
        for i, b in enumerate(self.broadcastable):
            if b:
                print >> sio, """
            if (CudaNdarray_HOST_DIMS(%(name)s)[%(i)s] != 1)
            {
                PyErr_Format(PyExc_RuntimeError, "Some CudaNdarray has dim %%i on broadcastable dimension %%i", CudaNdarray_HOST_DIMS(%(name)s)[%(i)s], %(i)s);
                %(name)s = NULL;
                %(fail)s;
            }
            //std::cerr << "c_extract " << %(name)s << "dim check %(i)s passed\\n";
            //std::cerr << "c_extract " << %(name)s << "checking bcast %(i)s <" << %(name)s->str<< ">\\n";
            //std::cerr << "c_extract " << %(name)s->str[%(i)s] << "\\n";
            if (CudaNdarray_HOST_STRIDES(%(name)s)[%(i)s])
            {
                //std::cerr << "c_extract bad stride detected...\\n";
                PyErr_Format(PyExc_RuntimeError, "Some CudaNdarray has a nonzero stride %%i on a broadcastable dimension %%i", CudaNdarray_HOST_STRIDES(%(name)s)[%(i)s], %(i)s);
                %(name)s = NULL;
                %(fail)s;
            }
            //std::cerr << "c_extract " << %(name)s << "bcast check %(i)s passed\\n";
                """ %locals()
        print >> sio, """
            assert(%(name)s);
            Py_INCREF(py_%(name)s);
        }
        else
        {
            //fprintf(stderr, "FAILING c_extract CNDA object w refcnt %%p %%i\\n", py_%(name)s, (py_%(name)s->ob_refcnt));
            PyErr_SetString(PyExc_TypeError, "Argument not a CudaNdarray");
            %(name)s = NULL;
            %(fail)s;
        }
        //std::cerr << "c_extract done " << %(name)s << '\\n';
        """ % locals()
        #print sio.getvalue()
        return sio.getvalue()

    def c_cleanup(self, name, sub):
        return """
        //std::cerr << "cleanup " << py_%(name)s << " " << %(name)s << "\\n";
        //fprintf(stderr, "c_cleanup CNDA py_object w refcnt %%p %%i\\n", py_%(name)s, (py_%(name)s->ob_refcnt));
        if (%(name)s)
        {
            //fprintf(stderr, "c_cleanup CNDA cn_object w refcnt %%p %%i\\n", %(name)s, (%(name)s->ob_refcnt));
            Py_XDECREF(%(name)s);
        }
        //std::cerr << "cleanup done" << py_%(name)s << "\\n";
        """ % locals()

    def c_sync(self, name, sub):
        """Override `CLinkerOp.c_sync` """
        return """
        //std::cerr << "sync\\n";
        if (NULL == %(name)s) {  
            // failure: sync None to storage
            Py_XDECREF(py_%(name)s);
            py_%(name)s = Py_None;
            Py_INCREF(py_%(name)s);
        }
        else
        {
            if (py_%(name)s != (PyObject*)%(name)s)
            {
                Py_XDECREF(py_%(name)s);
                py_%(name)s = (PyObject*)%(name)s;
                Py_INCREF(py_%(name)s);
            }
            assert(py_%(name)s->ob_refcnt);
        }
        """ % locals()

    def c_headers(self):
        """Override `CLinkerOp.c_headers` """
        return ['cuda_ndarray.cuh']

    def c_header_dirs(self):
        """Override `CLinkerOp.c_headers` """
        ret = [os.path.dirname(cuda_ndarray.__file__)]
        cuda_root = config.cuda.root
        if cuda_root:
            ret.append(os.path.join(cuda_root,'include'))
        return ret

    def c_lib_dirs(self):
        ret = [os.path.dirname(cuda_ndarray.__file__)]
        cuda_root = config.cuda.root
        if cuda_root:
            ret.append(os.path.join(cuda_root,'lib'))
        return ret

    def c_libraries(self):
        return ['cudart']

    def c_support_code(cls):
        return ""

    def c_code_cache_version(self):
        #return ()
        #no need to put nvcc.fastmath in the tuple as the c_compile_args is put in the key.
        return (2,) # with assertion about refcounts

    def c_compiler(self):
        return nvcc_module_compile_str

    def c_compile_args(self):
        ret = []
        if config.nvcc.fastmath:
            ret.append('-use_fast_math')
        return ret

# THIS WORKS
# But CudaNdarray instances don't compare equal to one another, and what about __hash__ ?
# So the unpickled version doesn't equal the pickled version, and the cmodule cache is not
# happy with the situation.
import copy_reg
def CudaNdarray_unpickler(npa):
    return cuda_ndarray.CudaNdarray(npa)
copy_reg.constructor(CudaNdarray_unpickler)

def CudaNdarray_pickler(cnda):
    return (CudaNdarray_unpickler, (numpy.asarray(cnda),))

copy_reg.pickle(cuda.CudaNdarray, CudaNdarray_pickler, CudaNdarray_unpickler)

