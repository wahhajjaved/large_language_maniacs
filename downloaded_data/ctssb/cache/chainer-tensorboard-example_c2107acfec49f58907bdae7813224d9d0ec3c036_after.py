import collections

import numpy
import six

import cupy
from cupy import cuda
from cupy.cuda import cublas
from cupy import elementwise
from cupy import internal


def dot(a, b, out=None):
    """Returns a dot product of two arrays.

    For arrays with more than one axis, it computes the dot product along the
    last axis of ``a`` and the second-to-last axis of ``b``. This is just a
    matrix product if the both arrays are 2-D. For 1-D arrays, it uses their
    unique axis as an axis to take dot product over.

    Args:
        a (cupy.ndarray): The left argument.
        b (cupy.ndarray): The right argument.
        out (cupy.ndarray): Output array.

    Returns:
        cupy.ndarray: The dot product of ``a`` and ``b``.

    .. seealso:: :func:`numpy.dot`

    """
    a_ndim = a.ndim
    b_ndim = b.ndim
    assert a_ndim > 0 and b_ndim > 0
    a_is_vec = a_ndim == 1
    b_is_vec = b_ndim == 1

    if a_is_vec:
        a = cupy.reshape(a, (1, a.size))
        a_ndim = 2
    if b_is_vec:
        b = cupy.reshape(b, (b.size, 1))
        b_ndim = 2

    if a.dtype == b.dtype:
        ret_dtype = a.dtype.type
    else:
        ret_dtype = numpy.find_common_type((a.dtype, b.dtype), ()).type

    # Cast to float32 or float64
    if ret_dtype == numpy.float32 or ret_dtype == numpy.float64:
        dtype = ret_dtype
    else:
        dtype = numpy.find_common_type((ret_dtype, numpy.float32), ()).type

    a = a.astype(dtype, copy=False)
    b = b.astype(dtype, copy=False)

    a_axis = a_ndim - 1
    b_axis = b_ndim - 2

    if a.shape[a_axis] != b.shape[b_axis]:
        raise ValueError('Axis dimension mismatch')

    if a_axis != 0:
        a = cupy.rollaxis(a, a_axis, 0)
    if b_axis != 0:
        b = cupy.rollaxis(b, b_axis, 0)

    k = a.shape[0]
    m = b.size // k
    n = a.size // k

    ret_shape = a.shape[1:] + b.shape[1:]
    if out is None:
        if a_is_vec:
            ret_shape = () if b_is_vec else ret_shape[1:]
        elif b_is_vec:
            ret_shape = ret_shape[:-1]
    else:
        if out.size != internal.prod(ret_shape):
            raise ValueError('Output array has an invalid size')
        if not out.flags.c_contiguous:
            raise ValueError('Output array must be C-contiguous')

    return _tensordot_core(a, b, out, n, m, k, ret_shape, ret_dtype, dtype)


def vdot(a, b):
    """Returns the dot product of two vectors.

    The input arrays are flattened into 1-D vectors and then it performs inner
    product of these vectors.

    Args:
        a (cupy.ndarray): The first argument.
        b (cupy.ndarray): The second argument.

    Returns:
        cupy.ndarray: Zero-dimensional array of the dot product result.

    .. seealso:: :func:`numpy.vdot`

    """
    a = a.ravel()
    b = b.ravel()
    return a.dot(b)


def inner(a, b):
    """Returns the inner product of two arrays.

    It uses the last axis of each argument to take sum product.

    Args:
        a (cupy.ndarray): The first argument.
        b (cupy.ndarray): The second argument.

    Returns:
        cupy.ndarray: The inner product of ``a`` and ``b``.

    .. seealso:: :func:`numpy.inner`

    """
    if a.ndim == 0 or b.ndim == 0:
        return a * b
    else:
        return tensordot(a, b, axes=(-1, -1))


def outer(a, b, out=None):
    """Returns the outer product of two vectors.

    The input arrays are flattened into 1-D vectors and then it performs outer
    product of these vectors.

    Args:
        a (cupy.ndarray): The first argument.
        b (cupy.ndarray): The second argument.
        out (cupy.ndarray): Output array.

    Returns:
        cupy.ndarray: 2-D array of the outer product of ``a`` and ``b``.

    .. seealso:: :func:`numpy.outer`

    """
    a = cupy.reshape(a, (a.size, 1))
    b = cupy.reshape(b, (1, b.size))
    if out is None:
        return dot(a, b)
    elif out.flags.c_contiguous:
        return dot(a, b, out)
    else:
        out[:] = dot(a, b)
        return out


def tensordot(a, b, axes=2):
    """Returns the tensor dot product of two arrays along specified axes.

    This is equivalent to compute dot product along the specified axes which
    are treated as one axis by reshaping.

    Args:
        a (cupy.ndarray): The first argument.
        b (cupy.ndarray): The second argument.
        axes:
            - If it is an integer, then ``axes`` axes at the last of ``a`` and
              the first of ``b`` are used.
            - If it is a pair of sequences of integers, then these two
              sequences specify the list of axes for ``a`` and ``b``. The
              corresponding axes are paired for sum-product.
        out (cupy.ndarray): Output array.

    Returns:
        cupy.ndarray: The tensor dot product of ``a`` and ``b`` along the
        axes specified by ``axes``.

    .. seealso:: :func:`numpy.tensordot`

    """
    a_ndim = a.ndim
    b_ndim = b.ndim
    if a_ndim == 0 or b_ndim == 0:
        if axes != 0 and axes != ((), ()):
            raise ValueError('An input is zero-dim while axes has dimensions')
        return cupy.multiply(a, b)

    if a.dtype == b.dtype:
        ret_dtype = a.dtype.type
    else:
        ret_dtype = numpy.find_common_type((a.dtype, b.dtype), ()).type

    # Cast to float32 or float64
    if ret_dtype == numpy.float32 or ret_dtype == numpy.float64:
        dtype = ret_dtype
    else:
        dtype = numpy.find_common_type((ret_dtype, numpy.float32), ()).type

    a = a.astype(dtype, copy=False)
    b = b.astype(dtype, copy=False)

    if isinstance(axes, collections.Sequence):
        if len(axes) != 2:
            raise ValueError('Axes must consist of two arrays.')
        a_axes, b_axes = axes
        if numpy.isscalar(a_axes):
            a_axes = a_axes,
        if numpy.isscalar(b_axes):
            b_axes = b_axes,
    else:
        a_axes = tuple(six.moves.range(a_ndim - axes, a_ndim))
        b_axes = tuple(six.moves.range(axes))

    sum_ndim = len(a_axes)
    if sum_ndim != len(b_axes):
        raise ValueError('Axes length mismatch')

    for a_axis, b_axis in zip(a_axes, b_axes):
        if a.shape[a_axis] != b.shape[b_axis]:
            raise ValueError('Axis dimension mismatch')

    # Make the axes non-negative
    a = _move_axes_to_head(a, [axis % a_ndim for axis in a_axes])
    b = _move_axes_to_head(b, [axis % b_ndim for axis in b_axes])

    ret_shape = a.shape[sum_ndim:] + b.shape[sum_ndim:]

    k = internal.prod(a.shape[:sum_ndim])
    n = a.size // k
    m = b.size // k

    return _tensordot_core(a, b, None, n, m, k, ret_shape, ret_dtype, dtype)


def _tensordot_core(a, b, out, n, m, k, ret_shape, ret_dtype, dtype):

    if 0 in a.shape or 0 in b.shape:
        if 0 not in a.shape or 0 not in b.shape:
            raise ValueError('cannot dot zero-sized and non-zero-sized arrays')
        if out is None:
            return cupy.zeros(ret_shape, dtype=ret_dtype)
        else:
            out.fill(0)
            return out

    if out is None:
        out = cupy.empty(ret_shape, dtype)
        if dtype == ret_dtype:
            ret = out
        else:
            ret = cupy.empty(ret_shape, ret_dtype)
    else:
        ret = out
        if out.dtype != dtype:
            out = cupy.empty(ret_shape, dtype)

    # It copies the operands if needed
    if a.shape != (k, n):
        a = cupy.reshape(a, (k, n))
    if b.shape != (k, m):
        b = cupy.reshape(b, (k, m))
    c = out
    if c.shape != (n, m):
        c = c.view()
        c.shape = (n, m)

    # Be careful that cuBLAS uses the FORTRAN-order matrix representation.
    handle = cuda.Device().cublas_handle
    if k == 1:
        if n == 1:
            # Scalar-vector product
            cupy.multiply(a, b, c)
        elif m == 1:
            # Scalar-vector product
            cupy.multiply(a.T, b, c)
        else:
            # Outer product A^T * B
            # c is C-contiguous while cuBLAS requires F-contiguous arrays, so
            # we compute C^T = B^T * A here.
            c.fill(0)
            a, inca = _to_cublas_vector(a, 1)
            b, incb = _to_cublas_vector(b, 1)
            if dtype == numpy.float32:
                ger = cublas.sger
            elif dtype == numpy.float64:
                ger = cublas.dger
            ger(handle, m, n, 1, b._fptr, incb, a._fptr, inca, c._fptr, m)
    elif n == 1:
        if m == 1:
            # Inner product
            a, inca = _to_cublas_vector(a, 0)
            b, incb = _to_cublas_vector(b, 0)
            mode = cublas.getPointerMode(handle)
            cublas.setPointerMode(handle,
                                  cublas.CUBLAS_POINTER_MODE_DEVICE)
            if dtype == numpy.float32:
                dot = cublas.sdot
            elif dtype == numpy.float64:
                dot = cublas.ddot
            try:
                dot(handle, k, a._fptr, inca, b._fptr, incb, c._fptr)
            finally:
                cublas.setPointerMode(handle, mode)
        else:
            # Matrix-vector product B^T * A
            a, inca = _to_cublas_vector(a, 0)
            b, transb, ldb = _mat_to_cublas_contiguous(b, True)
            if transb:
                # gemv requires (m, k) as the original matrix dimensions
                # rather than the transposed dimensions.
                m, k = k, m
            if dtype == numpy.float32:
                gemv = cublas.sgemv
            elif dtype == numpy.float64:
                gemv = cublas.dgemv
            gemv(handle, transb, m, k, 1, b._fptr, ldb, a._fptr, inca,
                 0, c._fptr, 1)
    elif m == 1:
        # Matrix-vector product A^T * B
        a, transa, lda = _mat_to_cublas_contiguous(a, True)
        b, incb = _to_cublas_vector(b, 1)
        if not transa:
            # gemv requires (n, k) as the original matrix dimensions rather
            # than the transposed dimensions.
            n, k = k, n
        if dtype == numpy.float32:
            gemv = cublas.sgemv
        elif dtype == numpy.float64:
            gemv = cublas.dgemv
        gemv(handle, transa, n, k, 1, a._fptr, lda, b._fptr, incb, 0, c._fptr,
             1)
    else:
        # Matrix-Matrix product A^T * B
        # c is C-contiguous while cuBLAS assumes F-contiguous inputs, so we
        # compute C^T = B^T * A here.
        a, transa, lda = _mat_to_cublas_contiguous(a, False)
        b, transb, ldb = _mat_to_cublas_contiguous(b, True)
        if dtype == numpy.float32:
            gemm = cublas.sgemm
        elif dtype == numpy.float64:
            gemm = cublas.dgemm
        gemm(handle, transb, transa, m, n, k, 1, b._fptr, ldb, a._fptr,
             lda, 0, c._fptr, m)

    if dtype != ret_dtype:
        elementwise.copy(out, ret)
    return ret


def einsum(subscripts, *args):
    # TODO(beam2d): Implement it
    raise NotImplementedError


def matrix_power(M, n):
    # TODO(beam2d): Implement it
    raise NotImplementedError


def kron(a, b):
    # TODO(beam2d): Implement it
    raise NotImplementedError


def _move_axes_to_head(a, axes):
    # This function moves the axes of ``s`` to the head of the shape.
    for idx, axis in enumerate(axes):
        if idx == axis:
            continue
        return cupy.transpose(
            a, axes + [i for i in six.moves.range(a.ndim) if i not in axes])
    return a


def _mat_to_cublas_contiguous(a, trans):
    assert a.ndim == 2
    f = a.flags
    if f.f_contiguous:
        ld = a.strides[1] // a.itemsize
        if trans:
            return a, cublas.CUBLAS_OP_T, ld
        else:
            return a, cublas.CUBLAS_OP_N, ld
    if not f.c_contiguous:
        a = a.copy()
    ld = a.strides[0] // a.itemsize
    if trans:
        return a, cublas.CUBLAS_OP_N, ld
    else:
        return a, cublas.CUBLAS_OP_T, ld


def _to_cublas_vector(a, rundim):
    if a.strides[rundim] < 0:
        return a.copy(), 1
    else:
        return a, a.strides[rundim] // a.itemsize
