"""
Implementation of MRG31k3p random number generator for Theano

Generator code in SSJ package (L'Ecuyer & Simard)
http://www.iro.umontreal.ca/~simardr/ssj/indexe.html

"""
import sys
import numpy

from theano import Op, Apply, shared, config
from theano.tensor import raw_random, TensorType, as_tensor_variable, get_vector_length, cast, opt
from theano.tensor import zeros_like, sqrt, log, sin, cos, join
from theano.compile import optdb
from theano.gof import local_optimizer

from theano.sandbox.cuda.opt import register_opt as gpu_register_opt
from theano.sandbox.cuda import cuda_enabled, CudaNdarrayType #, gpu_from_host, host_from_gpu, CudaNdarrayType

def mulmod(a, b, c, m):
    r = numpy.int32((numpy.int64(a)*b + c) % m)
    return r if r >= 0 else r+m

def matVecModM(A, s, m):
    # return (A * s) % m
    x = numpy.zeros_like(s)
    for i in xrange(len(x)):
        for j in xrange(len(s)):
            x[i] = mulmod(A[i][j], s[j], x[i], m)
    return x

def multMatVect(v, A, m1, B, m2):
   #multiply the first half of v by A with a modulo of m1
   #and the second half by B with a modulo of m2
   r = numpy.zeros_like(v)
   r[:3] = matVecModM(A, v[:3], m1)
   r[3:] = matVecModM(B, v[3:], m2)
   return r

#MRG31k3p
#generator constants :
M1 = numpy.int32(2147483647)    #2^31 - 1
M2 = numpy.int32(2147462579)    #2^31 - 21069
MASK12 = numpy.int32(511)       #2^9 - 1
MASK13 = numpy.int32(16777215)  #2^24 - 1
MASK2 = numpy.int32(65535)      #2^16 - 1
MULT2 = numpy.int32(21069)
NORM = 4.656612873077392578125e-10;

A1p0 = numpy.asarray([[0, 4194304, 129], [1, 0, 0], [0, 1, 0]])
A2p0 = numpy.asarray([[32768, 0, 32769], [1, 0, 0], [0, 1, 0]])

A1p72 = numpy.asarray([[1516919229, 758510237, 499121365],
       [1884998244, 1516919229, 335398200],
       [601897748, 1884998244, 358115744]]) 
A2p72 = numpy.asarray([[1228857673, 1496414766, 954677935],
   [1133297478, 1407477216, 1496414766],
   [2002613992, 1639496704, 1407477216]])

A1p134 = numpy.asarray(
  [[1702500920, 1849582496, 1656874625],
   [828554832, 1702500920, 1512419905],
   [1143731069, 828554832, 102237247]])
A2p134 = numpy.asarray(
  [[796789021, 1464208080, 607337906],
   [1241679051, 1431130166, 1464208080],
   [1401213391, 1178684362, 1431130166]])

def ff_2p134(rstate):
    return multMatVect(rstate, A1p134, M1, A2p134, M2)

def ff_2p72(rstate):
    return multMatVect(rstate, A1p72, M1, A2p72, M2)

def mrg_next_value(rstate, new_rstate):
    x11, x12, x13, x21, x22, x23 = rstate
    assert type(x11) == numpy.int32

    i0, i7, i9, i15, i16, i22, i24 = [numpy.int32(i) for i in (0,7, 9, 15, 16, 22, 24)]

    #first component
    y1 = ((x12 & MASK12) << i22) + (x12 >> i9) + ((x13 & MASK13) << i7) + (x13 >> i24);

    assert type(y1) == numpy.int32
    if (y1 < 0 or y1 >= M1):     #must also check overflow
        y1 -= M1;
    y1 += x13;
    if (y1 < 0 or y1 >= M1):
        y1 -= M1;

    x13 = x12;
    x12 = x11;
    x11 = y1;

    #second component
    y1 = ((x21 & MASK2) << i15) + (MULT2 * (x21 >> i16));
    assert type(y1) == numpy.int32
    if (y1 < 0 or y1 >= M2):
        y1 -= M2;
    y2 = ((x23 & MASK2) << i15) + (MULT2 * (x23 >> i16));
    assert type(y2) == numpy.int32
    if (y2 < 0 or y2 >= M2):
        y2 -= M2;
    y2 += x23;
    if (y2 < 0 or y2 >= M2):
        y2 -= M2;
    y2 += y1;
    if (y2 < 0 or y2 >= M2):
        y2 -= M2;

    x23 = x22;
    x22 = x21;
    x21 = y2;

    # Must never return either 0 or M1+1
    new_rstate[...] = [x11, x12, x13, x21, x22, x23]
    assert new_rstate.dtype == numpy.int32
    if (x11 <= x21):
        return (x11 - x21 + M1) * NORM
    else:
        return (x11 - x21) * NORM

class mrg_uniform_base(Op):
    def __init__(self, output_type, inplace=False):
        Op.__init__(self)
        self.output_type = output_type
        self.inplace=inplace
        if inplace:
            self.destroy_map = {0:[0]}

    def __eq__(self, other):
        return type(self) == type(other) \
                and self.output_type == other.output_type \
                and self.inplace == other.inplace

    def __hash__(self):
        return hash(type(self)) ^ hash(self.output_type) ^ hash(self.inplace)

    def make_node(self, rstate, size):
        # error checking slightly redundant here, since
        # this op should not be called directly.
        #
        # call through MRG_RandomStreams instead.
        return Apply(self, 
                [rstate, size], 
                [rstate.type(), self.output_type()])

class mrg_uniform(mrg_uniform_base):
    #CPU VERSION

    @classmethod
    def new(cls, rstate, ndim, dtype, size):
        v_size = as_tensor_variable(size)
        if ndim is None:
            ndim = get_vector_length(v_size)
        op = cls(TensorType(dtype, (False,)*ndim))
        return op(rstate, cast(v_size, 'int32'))

    def perform(self, node, (rstate, size), (o_rstate, o_sample)):
        n_elements = 1

        rstate = numpy.asarray(rstate) # bring state from GPU if necessary
        if not self.inplace:
            rstate = rstate.copy()

        for s in size:
            n_elements *= s

        n_streams,_ = rstate.shape

        rval = numpy.zeros(n_elements, dtype=self.output_type.dtype)

        for i in xrange(n_elements):
            sample = mrg_next_value(rstate[i%n_streams], rstate[i%n_streams])
            rval[i] = sample

        o_rstate[0] = node.outputs[0].type.filter(rstate) # send to GPU if necessary
        o_sample[0] = node.outputs[1].type.filter(rval.reshape(size))# send to GPU if necessary

    def c_code_cache_version(self):
        return ()

    def c_code(self, node, name, (rstate, size), (o_rstate, o_sample), sub):
        if self.inplace:
            o_rstate_requirement = 'NPY_C_CONTIGUOUS|NPY_ALIGNED'
        else:
            o_rstate_requirement = 'NPY_ENSURECOPY|NPY_C_CONTIGUOUS|NPY_ALIGNED' 
        ndim = self.output_type.ndim
        o_type_num = numpy.asarray(0, dtype=self.output_type.dtype).dtype.num
        fail = sub['fail']
        if self.output_type.dtype == 'float32':
            otype = 'float' 
            NORM = '4.6566126e-10f' #numpy.float32(1.0/(2**31+65))
            # this was determined by finding the biggest number such that
            # numpy.float32(number * M1) < 1.0
        else:
            otype = 'double' 
            NORM = '4.656612873077392578125e-10'
        return """
        //////// <code generated by mrg_uniform>

        npy_intp odims[%(ndim)s];
        int n_elements = 1;
        int n_streams = 0;
        int must_alloc_sample = ((NULL == %(o_sample)s) || (%(o_sample)s->nd != %(ndim)s));
        %(otype)s * sample_data;
        npy_int32 * state_data;

        const npy_int32 i0 = 0;
        const npy_int32 i7 = 7;
        const npy_int32 i9 = 9;
        const npy_int32 i15 = 15;
        const npy_int32 i16 = 16;
        const npy_int32 i22 = 22;
        const npy_int32 i24 = 24;

        const npy_int32 M1 = 2147483647;      //2^31 - 1
        const npy_int32 M2 = 2147462579;      //2^31 - 21069
        const npy_int32 MASK12 = 511;       //2^9 - 1
        const npy_int32 MASK13 = 16777215;  //2^24 - 1
        const npy_int32 MASK2 = 65535;      //2^16 - 1
        const npy_int32 MULT2 = 21069;

        if (%(size)s->nd != 1)
        {
            PyErr_SetString(PyExc_ValueError, "size must be vector");
            %(fail)s
        }
        if (%(size)s->dimensions[0] != %(ndim)s)
        {
            PyErr_Format(PyExc_ValueError, "size must have length %%i", %(ndim)s);
            %(fail)s
        }
        if (%(size)s->descr->type_num != PyArray_INT32)
        {
            PyErr_SetString(PyExc_ValueError, "size must be int32");
            %(fail)s
        }
        for (int i = 0; i < %(ndim)s; ++i)
        {
            odims[i] = ((npy_int32*)(%(size)s->data + %(size)s->strides[0] * i))[0];
            n_elements *= odims[i];
            must_alloc_sample = must_alloc_sample || (%(o_sample)s->dimensions[i] != odims[i]);
            //fprintf(stderr, "size %%i %%i\\n", i, (int)odims[i]);
            // TODO CHECK STRIDES OF o_sample?
        }
        if (must_alloc_sample)
        {
            Py_XDECREF(%(o_sample)s);
            %(o_sample)s = (PyArrayObject*)PyArray_SimpleNew(%(ndim)s, odims, %(o_type_num)s);
            if(!%(o_sample)s) {
                PyErr_SetString(PyExc_MemoryError, "failed to alloc mrg_uniform output");
                %(fail)s
            }
        }
        Py_XDECREF(%(o_rstate)s);
        %(o_rstate)s = (PyArrayObject*)PyArray_FromAny(py_%(rstate)s, NULL, 0, 0, %(o_rstate_requirement)s,NULL);

        if (%(o_rstate)s->nd != 2)
        {
            PyErr_SetString(PyExc_ValueError, "rstate must be matrix");
            %(fail)s
        }
        if (%(o_rstate)s->dimensions[1] != 6)
        {
            PyErr_Format(PyExc_ValueError, "rstate must have 6 columns");
            %(fail)s
        }
        if (%(o_rstate)s->descr->type_num != PyArray_INT32)
        {
            PyErr_SetString(PyExc_ValueError, "rstate must be int32");
            %(fail)s
        }
        n_streams = %(o_rstate)s->dimensions[0];

        sample_data = (%(otype)s *) %(o_sample)s->data;
        state_data = (npy_int32 *) %(o_rstate)s->data;
        for (int i = 0; i < n_elements; ++i)
        {
            npy_int32 * state_data_i = state_data + (i%%n_streams)*6;
            npy_int32 y1, y2, x11, x12, x13, x21, x22, x23;

            x11 = state_data_i[0];
            x12 = state_data_i[1];
            x13 = state_data_i[2];
            x21 = state_data_i[3];
            x22 = state_data_i[4];
            x23 = state_data_i[5];

            y1 = ((x12 & MASK12) << i22) + (x12 >> i9) + ((x13 & MASK13) << i7) + (x13 >> i24);
            if ((y1 < 0 || y1 >= M1))     //must also check overflow
                y1 -= M1;
            y1 += x13;
            if ((y1 < 0 or y1 >= M1))
                y1 -= M1;
            x13 = x12;
            x12 = x11;
            x11 = y1;

            y1 = ((x21 & MASK2) << i15) + (MULT2 * (x21 >> i16));
            if (y1 < 0 || y1 >= M2)
                y1 -= M2;
            y2 = ((x23 & MASK2) << i15) + (MULT2 * (x23 >> i16));
            if (y2 < 0 || y2 >= M2)
                y2 -= M2;
            y2 += x23;
            if (y2 < 0 || y2 >= M2)
                y2 -= M2;
            y2 += y1;
            if (y2 < 0 or y2 >= M2)
                y2 -= M2;

            x23 = x22;
            x22 = x21;
            x21 = y2;

            if (x11 <= x21) {
                assert((x11 - x21 + M1) <= M1);
                sample_data[i] = (x11 - x21 + M1) * %(NORM)s;
            }
            else
            {
                assert(x11 - x21 <= M1);
                sample_data[i] = (x11 - x21) * %(NORM)s;
            }

            state_data_i[0]= x11;
            state_data_i[1]= x12;
            state_data_i[2]= x13;
            state_data_i[3]= x21;
            state_data_i[4]= x22;
            state_data_i[5]= x23;
        }
        //////// </ code generated by mrg_uniform>
        """ %locals()

class GPU_mrg_uniform(mrg_uniform_base):
    #GPU VERSION

    @classmethod
    def new(cls, rstate, ndim, dtype, size):
        v_size = as_tensor_variable(size)
        if ndim is None:
            ndim = get_vector_length(v_size)
        op = cls(CudaNdarrayType((False,)*ndim))
        return op(rstate, cast(v_size, 'int32'))

    def c_support_code_apply(self, node, nodename):
        if self.output_type.dtype == 'float32':
            otype = 'float' 
            NORM = '4.6566126e-10f' #numpy.float32(1.0/(2**31+65))
            # this was determined by finding the biggest number such that
            # numpy.float32(number * M1) < 1.0
        else:
            otype = 'double' 
            NORM = '4.656612873077392578125e-10'
        return """

        static __global__ void %(nodename)s_mrg_uniform(
                %(otype)s*sample_data,
                npy_int32*state_data,
                const int Nsamples)
        {
            const npy_int32 i0 = 0;
            const npy_int32 i7 = 7;
            const npy_int32 i9 = 9;
            const npy_int32 i15 = 15;
            const npy_int32 i16 = 16;
            const npy_int32 i22 = 22;
            const npy_int32 i24 = 24;

            const npy_int32 M1 = 2147483647;      //2^31 - 1
            const npy_int32 M2 = 2147462579;      //2^31 - 21069
            const npy_int32 MASK12 = 511;       //2^9 - 1
            const npy_int32 MASK13 = 16777215;  //2^24 - 1
            const npy_int32 MASK2 = 65535;      //2^16 - 1
            const npy_int32 MULT2 = 21069;

            const unsigned int numThreads = blockDim.x * gridDim.x;
            const unsigned int idx = blockIdx.x * blockDim.x + threadIdx.x;
            npy_int32 y1, y2, x11, x12, x13, x21, x22, x23;

            x11 = state_data[idx*6+0];
            x12 = state_data[idx*6+1];
            x13 = state_data[idx*6+2];
            x21 = state_data[idx*6+3];
            x22 = state_data[idx*6+4];
            x23 = state_data[idx*6+5];

            for (int i = idx; i < Nsamples; i += numThreads)
            {
                y1 = ((x12 & MASK12) << i22) + (x12 >> i9) + ((x13 & MASK13) << i7) + (x13 >> i24);
                if ((y1 < 0 || y1 >= M1))     //must also check overflow
                    y1 -= M1;
                y1 += x13;
                if ((y1 < 0 or y1 >= M1))
                    y1 -= M1;
                x13 = x12;
                x12 = x11;
                x11 = y1;

                y1 = ((x21 & MASK2) << i15) + (MULT2 * (x21 >> i16));
                if (y1 < 0 || y1 >= M2)
                    y1 -= M2;
                y2 = ((x23 & MASK2) << i15) + (MULT2 * (x23 >> i16));
                if (y2 < 0 || y2 >= M2)
                    y2 -= M2;
                y2 += x23;
                if (y2 < 0 || y2 >= M2)
                    y2 -= M2;
                y2 += y1;
                if (y2 < 0 or y2 >= M2)
                    y2 -= M2;

                x23 = x22;
                x22 = x21;
                x21 = y2;

                if (x11 <= x21) {
                    sample_data[i] = (x11 - x21 + M1) * %(NORM)s;
                }
                else
                {
                    sample_data[i] = (x11 - x21) * %(NORM)s;
                }
            }

            state_data[idx*6+0]= x11;
            state_data[idx*6+1]= x12;
            state_data[idx*6+2]= x13;
            state_data[idx*6+3]= x21;
            state_data[idx*6+4]= x22;
            state_data[idx*6+5]= x23;
        }  

        """ %locals()

    def c_code_cache_version(self):
        return ()

    def c_code(self, node, nodename, (rstate, size), (o_rstate, o_sample), sub):
        inplace = int(self.inplace)
        ndim = self.output_type.ndim
        o_type_num = numpy.asarray(0, dtype=self.output_type.dtype).dtype.num
        fail = sub['fail']

        if self.output_type.dtype == 'float32':
            otype = 'float' 
        else:
            otype = 'double' 

        SYNC="CNDA_THREAD_SYNC";
        return """
        //////// <code generated by mrg_uniform>

        int odims[%(ndim)s];
        int n_elements = 1;
        unsigned int n_streams;
        int must_alloc_sample = ((NULL == %(o_sample)s)
                || !CudaNdarray_Check(py_%(o_sample)s)
                || (%(o_sample)s->nd != %(ndim)s));

        if (%(size)s->nd != 1)
        {
            PyErr_SetString(PyExc_ValueError, "size must be vector");
            %(fail)s
        }
        if (%(size)s->dimensions[0] != %(ndim)s)
        {
            PyErr_Format(PyExc_ValueError, "size must have length %%i", %(ndim)s);
            %(fail)s
        }
        if (%(size)s->descr->type_num != PyArray_INT32)
        {
            PyErr_SetString(PyExc_ValueError, "size must be int32");
            %(fail)s
        }
        for (int i = 0; i < %(ndim)s; ++i)
        {
            odims[i] = ((npy_int32*)(%(size)s->data + %(size)s->strides[0] * i))[0];
            n_elements *= odims[i];
            must_alloc_sample = (must_alloc_sample 
                    || CudaNdarray_HOST_DIMS(%(o_sample)s)[i] != odims[i]);
        }
        if (must_alloc_sample)
        {
            Py_XDECREF(%(o_sample)s);
            %(o_sample)s = (CudaNdarray*)CudaNdarray_NewDims(%(ndim)s, odims);
            if(!%(o_sample)s)
            {
                %(fail)s;
            }
        }
        if (!CudaNdarray_Check(py_%(rstate)s))
        {
            PyErr_Format(PyExc_ValueError, "rstate must be cudandarray");
            %(fail)s;
        }

        Py_XDECREF(%(o_rstate)s);
        if (%(inplace)s)
        {
            Py_INCREF(%(rstate)s);
            %(o_rstate)s = %(rstate)s;
        }
        else
        {
            %(o_rstate)s = (CudaNdarray*)CudaNdarray_Copy(%(rstate)s);
        }

        if (%(o_rstate)s->nd != 1)
        {
            PyErr_SetString(PyExc_ValueError, "rstate must be vector");
            %(fail)s;
        }
        if (CudaNdarray_HOST_DIMS(%(o_rstate)s)[0] %% 6)
        {
            PyErr_Format(PyExc_ValueError, "rstate len must be multiple of 6");
            %(fail)s;
        }
        n_streams = std::min(CudaNdarray_HOST_DIMS(%(o_rstate)s)[0]/6, n_elements);

        {
            unsigned int threads_per_block = std::min(n_streams, (unsigned int)NUM_VECTOR_OP_THREADS_PER_BLOCK);
            unsigned int n_blocks = std::min(ceil_intdiv(n_streams, threads_per_block), (unsigned int)NUM_VECTOR_OP_BLOCKS);
            if (threads_per_block * n_blocks < n_streams)
            {
                fprintf(stderr, "WARNING: unused streams above %%i (Tune GPU_mrg get_n_streams)\\n", threads_per_block * n_blocks );
            }
            %(nodename)s_mrg_uniform<<<n_blocks,threads_per_block>>>(
                CudaNdarray_DEV_DATA(%(o_sample)s),
                (npy_int32*)CudaNdarray_DEV_DATA(%(o_rstate)s),
                n_elements);
        }

        %(SYNC)s;

        {
            cudaError_t err = cudaGetLastError();
            if( cudaSuccess != err) 
            {
                PyErr_Format(PyExc_RuntimeError, "Cuda error: %%s: %%s.\\n", "mrg_uniform", cudaGetErrorString(err));
                %(fail)s;
            }                         
        }

        //////// </ code generated by mrg_uniform>
        """ %locals()

class MRG_RandomStreams(object):
    """Module component with similar interface to numpy.random (numpy.random.RandomState)"""

    def __init__(self, seed=12345, use_cuda=None):
        """
        :type seed: None or int

        :param seed: a default seed to initialize the RandomState instances after build.  See
        `RandomStreamsInstance.__init__` for more details.
        """
        super(MRG_RandomStreams, self).__init__()
        if isinstance(seed, int):
            self.rstate = numpy.asarray([seed]*6, dtype='int32')
        elif len(seed)==6:
            self.rstate = numpy.asarray(seed, dtype='int32')
        else:
            raise TypeError("seed should be 1 integer or 6 integers")
        if use_cuda is None:
            self.use_cuda = cuda_enabled
        else:
            self.use_cuda = use_cuda

    def inc_rstate(self):
        """Update self.rstate to be skipped 2^134 steps forward to the next stream start"""
        self.rstate = ff_2p134(self.rstate)
        assert self.rstate.dtype == numpy.int32

    def get_substream_rstates(self, n_streams, inc_rstate=True):
        """Initialize a matrix in which each row is a MRG stream state,
        and they are spaced by 2**72 samples.
        """
        assert n_streams < 2**72
        assert n_streams > 0
        rval = numpy.zeros((n_streams,6), dtype='int32')
        rval[0] = self.rstate
        for i in xrange(1, n_streams):
            rval[i] = ff_2p72(rval[i-1])
        if inc_rstate:
            self.inc_rstate()
        return rval

    def n_streams(self, size):
        if isinstance(size, (tuple, list)):
            r = 1
            for s in size:
                r *= s
            return r
        try:
            rval =  int(size)
            assert rval > 0
            return rval
        except:
            pass
        print >> sys.stderr, "MRG_RandomStreams Can't determine #streams from size (%s), guessing 30*256"%str(size)
        return 30*256

    def pretty_return(self, node_rstate, new_rstate, sample):
        sample.rstate = node_rstate
        sample.update = (node_rstate, new_rstate)
        node_rstate.default_update = new_rstate
        return sample

    def uniform(self, size=None, low=0.0, high=1.0, ndim=None, dtype=config.floatX):
        """
        Sample a tensor of given size whose element from a uniform
        distribution between low and high.

        If the size argument is ambiguous on the number of dimensions,
        ndim may be a plain integer to supplement the missing
        information.
        """
        if self.use_cuda and dtype=='float32':
            rstates = self.get_substream_rstates(self.n_streams(size))
            rstates = rstates.flatten()
            # HACK - we use fact that int32 and float32 have same size to 
            # sneak ints into the CudaNdarray type.
            # these *SHOULD NEVER BE USED AS FLOATS*
            tmp_float_buf = numpy.frombuffer(rstates.data, dtype='float32')
            assert tmp_float_buf.shape == rstates.shape
            assert tmp_float_buf.data[:24] == rstates.data[:24]
            node_rstate = shared(tmp_float_buf) # transfer to device
            assert isinstance(node_rstate.type, CudaNdarrayType)

            # we can't use the normal mrg_uniform constructor + later optimization
            # because of the tmp_float_buf hack above.  There is
            # currently no Theano node that will do a frombuffer reinterpretation.
            u = self.pretty_return(node_rstate, 
                    *GPU_mrg_uniform.new(node_rstate, ndim, dtype, size))
        else:
            node_rstate = shared(self.get_substream_rstates(self.n_streams(size)))
            u = self.pretty_return(node_rstate, 
                    *mrg_uniform.new(node_rstate, ndim, dtype, size))
        r = u * (high-low) + low
        
        if u.type.broadcastable != r.type.broadcastable:
            raise NotImplementedError( 'Increase the size to match the broadcasting pattern of `low` and `high` arguments')
        return  r

    def binomial(self, size=None, n=1, p=0.5, ndim=None, dtype='int64'):
        if n == 1:
            return cast(self.uniform(size=size) < p, dtype)
        else:
            raise NotImplementedError("MRG_RandomStreams.binomial with n > 1")

    def normal(self, size=None, avg=0.0, std=1.0, ndim=None, dtype=config.floatX):
        # We need an even number of ]0,1[ samples. Then we split them
        # in two halves. First half becomes our U1's for Box-Muller,
        # second half our U2's. See Wikipedia page:
        # http://en.wikipedia.org/wiki/Box%E2%80%93Muller_transform

        n_samples = self.n_streams(size)
        evened = False
           
        if n_samples % 2 == 1:
            n_samples += 1
            evened = True

        flattened = self.uniform(size=(n_samples,), dtype=dtype)

        U1 = flattened[:n_samples/2]
        U2 = flattened[n_samples/2:]

        #normal_samples = zeros_like(flattened)
        sqrt_ln_U1 = sqrt(-2.0*log(U1))
        # TypeError: 'TensorVariable' object does not support item assignment
        # so this doesn't work...
        #normal_samples[:n_samples/2] = sqrt_ln_U1 * cos(2.0*numpy.pi*U2)
        #normal_samples[n_samples/2:] = sqrt_ln_U1 * sin(2.0*numpy.pi*U2)

        # so trying this instead
        first_half = sqrt_ln_U1 * cos(2.0*numpy.pi*U2)
        second_half = sqrt_ln_U1 * sin(2.0*numpy.pi*U2)
        normal_samples = join(0, first_half, second_half)

        final_samples = None
        if evened:
            final_samples = normal_samples[:-1]
        else:
            final_samples = normal_samples

        final_samples = avg + std * final_samples

        if size:
            final_samples = final_samples.reshape(size)

        return final_samples

@local_optimizer([None])
def mrg_random_make_inplace(node):
    op = node.op
    if isinstance(op, mrg_uniform) and not op.inplace:
        # op might be gpu version
        new_op = op.__class__(op.output_type, inplace=True)
        return new_op.make_node(*node.inputs).outputs
    return False
optdb.register('random_make_inplace_mrg', opt.in2out(mrg_random_make_inplace, ignore_newtrees=True), 99, 'fast_run', 'inplace')


#
#
#
#
#
import time
import theano

def test_rng0():

    def basictest(f, steps, prefix=""):
        dt = 0.0
        for i in xrange(steps):
            t0 = time.time()
            ival = f()
            dt += time.time() - t0
            ival = numpy.asarray(ival)
            if i == 0:
                mean = numpy.array(ival, copy=True)
            else:
                alpha = 1.0 / (1+i)
                mean = alpha * ival + (1-alpha)*mean

        print prefix, 'mean', numpy.mean(mean)
        assert abs(numpy.mean(mean) - 0.5) < .01, 'bad mean?'
        print prefix, 'time', dt
        print prefix, 'elements', steps*sample_size[0]*sample_size[1]
        print prefix, 'samples/sec', steps*sample_size[0]*sample_size[1] / dt
        if 0:
            mean, std, min, max = numpy.mean(l), numpy.std(l), numpy.min(l), numpy.max(l)

            print prefix, 'mean', mean
            print prefix, 'std', std
            print prefix, 'min', repr(min)
            print prefix, 'max', repr(max)

            assert max < 1.0
            assert min >= 0.0
            assert abs(mean - 0.5) < .01, 'bad mean?'

    sample_size = (1000,100)

    print ''
    print 'ON CPU:'

    R = MRG_RandomStreams(234, use_cuda=False)
    u = R.uniform(size=sample_size)
    f = theano.function([], u)
    theano.printing.debugprint(f)
    print 'random?[:10]\n', f()[0,0:10]
    basictest(f, 1000, prefix='mrg  ')

    print ''
    print 'ON GPU:'
    R = MRG_RandomStreams(234, use_cuda=True)
    u = R.uniform(size=sample_size)
    assert u.dtype == 'float32' #well, it's really that this test w GPU doesn't make sense otw
    f = theano.function([], theano.Out(
        theano.sandbox.cuda.basic_ops.gpu_from_host(u),
        borrow=True))
    theano.printing.debugprint(f)
    print 'random?[:10]\n', numpy.asarray(f())[0,0:10]
    basictest(f, 1000, prefix='mrg  ')

    print ''
    print 'ON CPU w NUMPY:'
    RR = theano.tensor.shared_randomstreams.RandomStreams(234)

    uu = RR.uniform(size=sample_size)
    ff = theano.function([], uu)

    basictest(ff, 1000, prefix='numpy')




def test_normal0():

    def basictest(f, steps, target_avg, target_std, prefix=""):
        dt = 0.0
        avg_std = 0.0
        for i in xrange(steps):
            t0 = time.time()
            ival = f()
            dt += time.time() - t0
            ival = numpy.asarray(ival)
            if i == 0:
                mean = numpy.array(ival, copy=True)
                avg_std = numpy.std(ival)
            else:
                alpha = 1.0 / (1+i)
                mean = alpha * ival + (1-alpha)*mean
                avg_std = alpha * numpy.std(ival) + (1-alpha)*avg_std

        print prefix, 'mean', numpy.mean(mean)
        assert abs(numpy.mean(mean) - target_avg) < .01, 'bad mean?'
        print prefix, 'std', avg_std
        assert abs(avg_std - target_std) < .01, 'bad std?'
        print prefix, 'time', dt
        print prefix, 'elements', steps*sample_size[0]*sample_size[1]
        print prefix, 'samples/sec', steps*sample_size[0]*sample_size[1] / dt

    sample_size = (999,100)

    print ''
    print 'ON CPU:'

    R = MRG_RandomStreams(234, use_cuda=False)
    n = R.normal(size=sample_size, avg=-5.0, std=2.0)
    f = theano.function([], n)
    theano.printing.debugprint(f)
    print 'random?[:10]\n', f()[0,0:10]
    basictest(f, 50, -5.0, 2.0, prefix='mrg ')

    sys.stdout.flush()

    # now with odd number of samples
    sample_size = (999,99)

    print ''
    print 'ON GPU:'
    R = MRG_RandomStreams(234, use_cuda=True)
    n = R.normal(size=sample_size, avg=-5.0, std=2.0, dtype='float32')
    assert n.dtype == 'float32' #well, it's really that this test w GPU doesn't make sense otw
    f = theano.function([], theano.Out(
        theano.sandbox.cuda.basic_ops.gpu_from_host(n),
        borrow=True))
    theano.printing.debugprint(f)
    print 'random?[:10]\n', numpy.asarray(f())[0,0:10]
    basictest(f, 50, -5.0, 2.0, prefix='gpu mrg ')

    sys.stdout.flush()

    print ''
    print 'ON CPU w NUMPY:'
    RR = theano.tensor.shared_randomstreams.RandomStreams(234)

    nn = RR.normal(size=sample_size, avg=-5.0, std=2.0)
    ff = theano.function([], nn)

    basictest(ff, 50, -5.0, 2.0, prefix='numpy ')


#if __name__ == '__main__':
#    # with: export THEANO_FLAGS=device=gpu0,floatX=float32
#    test_normal0()


