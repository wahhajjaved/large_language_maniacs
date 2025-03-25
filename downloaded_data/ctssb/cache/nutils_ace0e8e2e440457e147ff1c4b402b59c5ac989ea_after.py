from . import util, numpy, numeric, log, prop, core, _
import sys, warnings

ELEM    = object()
POINTS  = object()
WEIGHTS = object()

# EVALUABLE
#
# Base class for everything that is evaluable. Evaluables hold an argument list
# and a callable, which will be called by the __call__ method. Function
# arguments that are themselves Evaluables are traced, and an optimal call
# ordering is determined such that any unique argument is evaluated only once.

class EvaluationError( Exception ):
  'evaluation error'

  def __init__( self, etype, evalue, evaluable, values ):
    'constructor'

    self.etype = etype
    self.evalue = evalue
    self.evaluable = evaluable
    self.values = values

  def __str__( self ):
    'string representation'

    return '\n%s --> %s: %s' % ( self.evaluable.stackstr( self.values ), self.etype.__name__, self.evalue )

class Evaluable( object ):
  'evaluable base classs'

  operations = None

  def __init__( self, args, evalf ):
    'constructor'

    self.__args = tuple(args)
    self.__evalf = evalf

  def verify( self, value ):
    'check result'

    return '= %s %s' % ( _obj2str(value), type(value) )

  def recurse_index( self, data, operations ):
    'compile'

    indices = numpy.empty( len(self.__args), dtype=int )
    for iarg, arg in enumerate( self.__args ):
      if isinstance(arg,Evaluable):
        for idx, (op,idcs) in enumerate( operations ):
          if op == arg:
            break
        else:
          idx = arg.recurse_index(data,operations)
      elif arg is ELEM:
        idx = -3
      elif arg is POINTS:
        idx = -2
      elif arg is WEIGHTS:
        idx = -1
      else:
        data.insert( 0, arg )
        idx = -len(data)-3
      indices[iarg] = idx
    operations.append( (self,indices) )
    return len(operations)-1

  def compile( self ):
    'compile'

    log.context( 'compiling' )

    if self.operations is None:
      self.data = []
      self.operations = []
      self.recurse_index( self.data, self.operations ) # compile expressions
      self.graphviz()

  def __call__( self, elem, ischeme ):
    'evaluate'

    if isinstance( ischeme, dict ):
      ischeme = ischeme[elem]

    if isinstance( ischeme, str ):
      points, weights = elem.eval( ischeme )
    elif isinstance( ischeme, tuple ):
      points, weights = ischeme
      assert points.shape[-1] == elem.ndims
      assert points.shape[:-1] == weights.shape, 'non matching shapes: points.shape=%s, weights.shape=%s' % ( points.shape, weights.shape )
    elif isinstance( ischeme, numpy.ndarray ):
      points = ischeme
      weights = None
      assert points.shape[-1] == elem.ndims
    elif ischeme is None:
      points = weights = None
    else:
      raise Exception, 'invalid integration scheme of type %r' % type(ischeme)

    self.compile()
    N = len(self.data) + 3
    values = list( self.data ) + [ elem, points, weights ]
    for op, indices in self.operations:
      args = [ values[N+i] for i in indices ]
      try:
        retval = op.__evalf( *args )
      except KeyboardInterrupt:
        raise
      except:
        etype, evalue, traceback = sys.exc_info()
        raise EvaluationError, ( etype, evalue, self, values ), traceback
      values.append( retval )
    return values[-1]

  def argnames( self ):
    'function argument names'
  
    import inspect
    try:
      argnames, varargs, keywords, defaults = inspect.getargspec( self.__evalf )
    except:
      argnames = [ '%%%d' % n for n in range(len(self.__args)) ]
    else:
      for n in range( len(self.__args) - len(argnames) ):
        argnames.append( '%s[%d]' % (varargs,n) )
    return argnames

  def __graphviz__( self ):
    'graphviz representation'

    args = [ '%s=%s' % ( argname, _obj2str(arg) ) for argname, arg in zip( self.argnames(), self.__args ) if not isinstance(arg,Evaluable) ]
    label = self.__class__.__name__
    return { 'label': r'\n'.join( [ label ] + args ) }

  def graphviz( self, title='graphviz' ):
    'create function graph'

    log.context( title )

    import os, subprocess

    dotpath = getattr( prop, 'dot', False )
    if not dotpath:
      return False
    if dotpath is True:
      dotpath = 'dot'

    imgtype = getattr( prop, 'imagetype', 'png' )
    imgpath = util.getpath( 'dot{0:03x}.' + imgtype )

    try:
      dot = subprocess.Popen( [dotpath,'-Tjpg'], stdin=subprocess.PIPE, stdout=open(imgpath,'w') )
    except OSError:
      log.error( 'error: failed to execute', dotpath )
      return False

    print >> dot.stdin, 'digraph {'
    print >> dot.stdin, 'graph [ dpi=72 ];'

    self.compile()
    for i, (op,indices) in enumerate( self.operations ):

      node = op.__graphviz__()
      node['label'] = '%d. %s' % ( i, node.get('label','') )
      print >> dot.stdin, '%d [%s]' % ( i, ' '.join( '%s="%s"' % item for item in node.iteritems() ) )
      argnames = op.argnames()
      for n, idx in enumerate( indices ):
        if idx >= 0:
          print >> dot.stdin, '%d -> %d [label="%s"];' % ( idx, i, argnames[n] );

    print >> dot.stdin, '}'
    dot.stdin.close()

    log.path( os.path.basename(imgpath) )

  def stackstr( self, values=None ):
    'print stack'

    self.compile()
    if values is None:
      values = self.data + ( '<elem>', '<points>', '<weights>' )

    N = len(self.data) + 3

    lines = []
    for i, (op,indices) in enumerate( self.operations ):
      line = '  %%%d =' % i
      args = [ '%%%d' % idx if idx >= 0 else _obj2str(values[N+idx]) for idx in indices ]
      try:
        code = op.__evalf.func_code
        names = code.co_varnames[ :code.co_argcount ]
        names += tuple( '%s[%d]' % ( code.co_varnames[ code.co_argcount ], n ) for n in range( len(indices) - len(names) ) )
        args = [ '%s=%s' % item for item in zip( names, args ) ]
      except:
        pass
      line += ' %s( %s )' % ( op.__evalf.__name__, ', '.join( args ) )
      if N+i < len(values):
        line += ' ' + op.verify( values[N+i] )
      lines.append( line )
      if N+i == len(values):
        break
    return '\n'.join( lines )

  def __eq__( self, other ):
    'compare'

    if self is other:
      return True
      
    if self.__class__ != other.__class__ or self.__evalf != other.__evalf or len( self.__args ) != len( other.__args ):
      return False

    return all( _equal(arg1,arg2) for arg1, arg2 in zip( self.__args, other.__args ) )

  def __ne__( self, other ):
    'not equal'

    return not self == other

  def asciitree( self ):
    'string representation'

    key = self.__evalf.__name__
    lines = []
    indent = '\n' + ' ' + ' ' * len(key)
    for it in reversed( self.__args ):
      s = it.asciitree() if isinstance(it,Evaluable) else _obj2str(it)
      lines.append( indent.join( s.splitlines() ) )
      indent = '\n' + '|' + ' ' * len(key)
    indent = '\n' + '+' + '-' * (len(key)-1) + ' '
    return key + ' ' + indent.join( reversed( lines ) )

class Tuple( Evaluable ):
  'combine'

  def __init__( self, items ):
    'constructor'

    self.items = tuple( items )
    Evaluable.__init__( self, args=self.items, evalf=self.vartuple )

  def __iter__( self ):
    'iterate'

    return iter(self.items)

  def __len__( self ):
    'length'

    return len(self.items)

  def __getitem__( self, item ):
    'get item'

    return self.items[item]

  def __add__( self, other ):
    'add'

    return Tuple( self.items + tuple(other) )

  def __radd__( self, other ):
    'add'

    return Tuple( tuple(other) + self.items )

  @staticmethod
  def vartuple( *f ):
    'evaluate'

    return f

# ARRAYFUNC
#
# The main evaluable. Closely mimics a numpy array.

class ArrayFunc( Evaluable ):
  'array function'

  __array_priority__ = 1. # http://stackoverflow.com/questions/7042496/numpy-coercion-problem-for-left-sided-binary-operator/7057530#7057530

  def __init__( self, evalf, args, shape ):
    'constructor'

    self.evalf = evalf
    self.shape = tuple(shape)
    self.ndim = len(self.shape)
    Evaluable.__init__( self, evalf=evalf, args=args )

  # mathematical operators

  def __mul__( self, other ): return multiply( self, other )
  def __rmul__( self, other ): return multiply( other, self )
  def __div__( self, other ): return divide( self, other )
  def __rdiv__( self, other ): return divide( other, self )
  def __add__( self, other ): return add( self, other )
  def __radd__( self, other ): return add( other, self )
  def __sub__( self, other ): return subtract( self, other )
  def __rsub__( self, other ): return subtract( other, self )
  def __neg__( self ): return negative( self )
  def __pow__( self, n ): return power( self, n )
  def sum( self, axes=-1 ): return sum( self, axes )

  # standalone methods

  @property
  def blocks( self ):
    s = tuple( None if n is None else numpy.arange(n) for n in self.shape )
    yield self, s

  def vector( self, ndims ):
    'vectorize'

    return vectorize( [self] * ndims )

  def get_func_ind( self, n=0 ):
    warnings.warn( '''f.get_func_ind(n=0) will be removed in future
  Please use list(f.blocks)[n] instead.''', DeprecationWarning, stacklevel=2 )
    return list(self.blocks)[n]

  def dot( self, weights ):
    'array contraction'

    weights = numpy.asarray( weights, dtype=float )
    assert weights.ndim == 1
    s = (slice(None),)+(numpy.newaxis,)*(self.ndim-1)
    return dot( self, weights[s], axes=0 )

  def __kronecker__( self, axis, length, pos ):
    'kronecker'

    assert self.shape[axis] == 1
    funcs = [ _zeros_like(self) ] * length
    funcs[pos] = self
    return Concatenate( funcs, axis=axis )

  def __getitem__( self, item ):
    'get item, general function which can eliminate, add or modify axes.'
  
    myitem = list( item if isinstance( item, tuple ) else [item] )
    n = 0
    arr = self
    while myitem:
      it = myitem.pop(0)
      if isinstance(it,int): # retrieve one item from axis
        arr = get( arr, n, it )
      elif it == _: # insert a singleton axis
        arr = insert( arr, n )
        n += 1
      elif it == slice(None): # select entire axis
        n += 1
      elif it == Ellipsis: # skip to end
        remaining_items = len(myitem) - myitem.count(_)
        skip = arr.ndim - n - remaining_items
        assert skip >= 0, 'shape=%s, item=%s' % ( self.shape, _obj2str(item) )
        n += skip
      elif isinstance(it,slice) and it.step in (1,None) and it.stop == ( it.start or 0 ) + 1: # special case: unit length slice
        arr = insert( get( arr, n, it.start ), n )
        n += 1
      elif isinstance(it,(slice,list,tuple,numpy.ndarray)): # modify axis (shorten, extend or renumber one axis)
        arr = take( arr, it, n )
        n += 1
      else:
        raise NotImplementedError
      assert n <= arr.ndim
    return arr

  def __iter__( self ):
    'split first axis'

    if not self.shape:
      raise TypeError, 'scalar function is not iterable'

    return ( self[i,...] for i in range(self.shape[0]) )

  @classmethod
  def stack( cls, funcs, axis ):
    'stack'

    return stack( funcs, axis )

  def verify( self, value ):
    'check result'

    s = '=> ' + _obj2str(value)
    s += ' \ (%s)' % ','.join(map(str,self.shape))
    return s

  def find( self, elem, C ):#target, start, tol=1e-10, maxiter=999 ):
    'iteratively find x for f(x) = target, starting at x=start'

    raise NotImplementedError
    assert self.ndim == 1
    points = start
    Jinv = inverse( localgradient( self, elem.ndims ) )
    r = target - self( elem, points )
    niter = 0
    while numpy.any( numeric.contract( r, r, axis=-1 ) > tol ):
      niter += 1
      if niter >= maxiter:
        raise Exception, 'failed to converge in %d iterations' % maxiter
      points = points.offset( numeric.contract( Jinv( elem, points ), r[:,_,:], axis=-1 ) )
      r = target - self( elem, points )
    return points

  def normalized( self ):
    'normalize last axis'

    return self / norm2( self, axis=-1 )

  def normal( self, ndims=-1 ):
    'normal'

    assert len(self.shape) == 1
    if ndims <= 0:
      ndims += self.shape[0]

    if self.shape[0] == 2 and ndims == 1:
      grad = localgradient( self, ndims=1 )
      normal = concatenate([ grad[1,:], -grad[0,:] ])
    elif self.shape[0] == 3 and ndims == 2:
      grad = localgradient( self, ndims=2 )
      normal = cross( grad[:,0], grad[:,1], axis=0 )
    elif self.shape[0] == 2 and ndims == 0:
      grad = localgradient( self, ndims=1 )
      normal = grad[:,0] * Orientation()
    elif self.shape[0] == 3 and ndims == 1:
      grad = localgradient( self, ndims=1 )
      normal = cross( grad[:,0], self.normal(), axis=0 )
    elif self.shape[0] == 1 and ndims == 0:
      return numpy.array( 1 ) # TODO fix direction!!!!
    else:
      raise NotImplementedError, 'cannot compute normal for %dx%d jacobian' % ( self.shape[0], ndims )
    return normal.normalized()

  def iweights( self, ndims ):
    'integration weights for [ndims] topology'

    J = localgradient( self, ndims )
    cndims, = self.shape
    assert J.shape == (cndims,ndims), 'wrong jacobian shape: got %s, expected %s' % ( J.shape, (cndims, ndims) )
    if cndims == ndims:
      detJ = determinant( J )
    elif ndims == 1:
      detJ = norm2( J[:,0], axis=0 )
    elif cndims == 3 and ndims == 2:
      detJ = norm2( cross( J[:,0], J[:,1], axis=0 ), axis=0 )
    elif ndims == 0:
      detJ = 1
    else:
      raise NotImplementedError, 'cannot compute determinant for %dx%d jacobian' % J.shape[:2]
    return detJ * IWeights()

  def curvature( self, ndims=-1 ):
    'curvature'

    return self.normal().div( self, ndims=ndims )

    #if ndims <= 0:
    #  ndims += self.shape[0]
    #assert ndims == 1 and self.shape == (2,)
    #J = localgradient( self, ndims )
    #H = localgradient( J, ndims )
    #dx, dy = J[:,0]
    #ddx, ddy = H[:,0,0]
    #return ( dx * ddy - dy * ddx ) / norm2( J[:,0], axis=0 )**3

  def swapaxes( self, n1, n2 ):
    'swap axes'

    trans = numpy.arange( self.ndim )
    trans[n1] = numeric.normdim( self.ndim, n2 )
    trans[n2] = numeric.normdim( self.ndim, n1 )
    return align( self, trans, self.ndim )

  def transpose( self, trans=None ):
    'transpose'

    return transpose( self, trans )

  def grad( self, coords, ndims=0 ):
    'gradient'

    assert coords.ndim == 1
    if ndims <= 0:
      ndims += coords.shape[0]
    J = localgradient( coords, ndims )
    if J.shape[0] == J.shape[1]:
      Jinv = inverse( J )
    elif J.shape[0] == J.shape[1] + 1: # gamma gradient
      G = ( J[:,:,_] * J[:,_,:] ).sum( 0 )
      Ginv = inverse( G )
      Jinv = ( J[_,:,:] * Ginv[:,_,:] ).sum()
    else:
      raise Exception, 'cannot invert %sx%s jacobian' % J.shape
    return sum( localgradient( self, ndims )[...,_] * Jinv, axes=-2 )

  def symgrad( self, coords, ndims=0 ):
    'gradient'

    g = self.grad( coords, ndims )
    return .5 * ( g + g.swapaxes(-2,-1) )

  def div( self, coords, ndims=0 ):
    'gradient'

    return trace( self.grad( coords, ndims ), -1, -2 )

  def dotnorm( self, coords, ndims=0 ):
    'normal component'

    return sum( self * coords.normal( ndims-1 ) )

  def ngrad( self, coords, ndims=0 ):
    'normal gradient'

    return self.grad( coords, ndims ).dotnorm( coords, ndims )

  def nsymgrad( self, coords, ndims=0 ):
    'normal gradient'

    return self.symgrad( coords, ndims ).dotnorm( coords, ndims )

  @property
  def T( self ):
    'transpose'

    return transpose( self )

  def __graphviz__( self ):
    'graphviz representation'

    args = Evaluable.__graphviz__( self )
    args['label'] += r'\n[%s]' % ','.join( map(str,self.shape) )
#   if self.__priority__:
#     args['fontcolor'] = 'white'
#     args['fillcolor'] = 'black'
#     args['style'] = 'filled'
    return args

  def __str__( self ):
    'string representation'

    return '%s<%s>' % ( self.__class__.__name__, ','.join(map(str,self.shape)) )

  __repr__ = __str__

  def norm2( self, axis=-1 ):
    warnings.warn( '''f.norm2(...) will be removed in future
  Please use function.norm2(f,...) instead.''', DeprecationWarning, stacklevel=2 )
    return norm2( self, axis )

  def localgradient( self, ndims ):
    warnings.warn( '''f.localgradient(...) will be removed in future
  Please use function.localgradient(f,...) instead.''', DeprecationWarning, stacklevel=2 )
    return localgradient( self, ndims )

  def trace( self, n1=-2, n2=-1 ):
    warnings.warn( '''f.trace(...) will be removed in future
  Please use function.trace(f,...) instead.''', DeprecationWarning, stacklevel=2 )
    return trace( self, n1=-2, n2=-1 )

class ElemArea( ArrayFunc ):
  'element area'

  def __init__( self, weights ):
    'constructor'

    assert weights.ndim == 0
    ArrayFunc.__init__( self, args=[weights], evalf=self.elemarea, shape=weights.shape )

  @staticmethod
  def elemarea( weights ):
    'evaluate'

    return sum( weights )

class ElemInt( ArrayFunc ):
  'elementwise integration'

  def __init__( self, func, weights ):
    'constructor'

    assert _isfunc( func ) and _isfunc( weights )
    assert weights.ndim == 0
    ArrayFunc.__init__( self, args=[weights,func], evalf=self.elemint, shape=func.shape )

  @staticmethod
  def elemint( w, f ):
    'evaluate'

    return numeric.dot( w, f ) if w.size else numpy.zeros( f.shape[1:] )

class Align( ArrayFunc ):
  'align axes'

  @classmethod
  def stack( cls, funcs, axis ):
    'stack funcs along new axis'

    axes = funcs[0].axes
    ndim = funcs[0].ndim
    if not all( isinstance(func,cls) and func.axes == axes and func.ndim == ndim for func in funcs ):
      return ArrayFunc.stack( funcs, axis )

    newaxes = [ ax if ax < axis else ax+1 for ax in axes ] + [ axis ]
    return Align( funcs[0].stack( funcs, len(axes) ), newaxes )

  def __init__( self, func, axes, ndim ):
    'constructor'

    assert func.ndim == len(axes)
    self.func = func
    assert all( 0 <= ax < ndim for ax in axes )
    self.axes = tuple(axes)
    shape = [ 1 ] * ndim
    for ax, sh in zip( self.axes, func.shape ):
      shape[ax] = sh
    negaxes = [ ax-ndim for ax in self.axes ]
    ArrayFunc.__init__( self, args=[func,negaxes,ndim], evalf=self.align, shape=shape )

  def __graphviz__( self ):
    'graphviz representation'

    newsh = [ '?' ] * self.ndim
    for src, dst in enumerate( self.axes ):
      newsh[dst] = str(src)
    return { 'shape': 'trapezium',
             'label': ','.join(newsh) }

  @staticmethod
  def align( arr, trans, ndim ):
    'align'

    extra = arr.ndim - len(trans)
    return numeric.align( arr, range(extra)+trans, ndim+extra )

  def _elemint( self, weights ):
    return align( elemint( self.func, weights ), self.axes, self.ndim )

  def _align( self, axes, ndim ):
    newaxes = [ axes[i] for i in self.axes ]
    return align( self.func, newaxes, ndim )

  def _takediag( self ):
    if self.ndim-1 not in self.axes:
      return align( self.func, self.axes, self.ndim-1 )
    if self.ndim-2 not in self.axes:
      axes = [ ax if ax != self.ndim-1 else self.ndim-2 for ax in self.axes ]
      return align( self.func, axes, self.ndim-1 )
    if self.axes[-2:] in [ (self.ndim-2,self.ndim-1), (self.ndim-1,self.ndim-2) ]:
      axes = self.axes[:-2] + (self.ndim-2,)
      return align( takediag( self.func ), axes, self.ndim-1 )

  def _get( self, i, item ):
    axes = [ ax - (ax>i) for ax in self.axes if ax != i ]
    if len(axes) == len(self.axes):
      return align( self.func, axes, self.ndim-1 )
    n = self.axes.index( i )
    return align( get( self.func, n, item ), axes, self.ndim-1 )

  def _sum( self, axis ):
    if axis in self.axes:
      idx = self.axes.index( axis )
      func = sum( self.func, idx )
    else:
      func = self.func
    trans = [ ax - (i<axis) for ax in self.axes if ax != axis ]
    return align( func, trans, self.ndim-1 )

  def _localgradient( self, ndims ):
    return align( localgradient( self.func, ndims ), self.axes+(self.ndim,), self.ndim+1 )

  def _multiply( self, other ):
    if not _isfunc(other) and len(self.axes) == other.ndim:
      return align( self.func * transpose( other, self.axes ), self.axes, self.ndim )
    if isinstance( other, Align ) and self.axes == other.axes:
      return align( self.func * other.func, self.axes, self.ndim )

  def _add( self, other ):
    #TODO make less restrictive:
    if isinstance( other, Align ) and self.axes == other.axes:
      return align( self.func + other.func, self.axes, self.ndim )
    if not _isfunc(other) and len(self.axes) == self.ndim:
      return align( self.func + transform( other, self.axes ), self.axes, self.ndim )

  def _divide( self, other ):
    #TODO make less restrictive:
    if isinstance( other, Align ) and self.axes == other.axes:
      return align( self.func / other.func, self.axes, self.ndim )
    if not _isfunc(other) and len(self.axes) == self.ndim:
      return align( self.func / transform( other, self.axes ), self.axes, self.ndim )

  def _take( self, indices, axis ):
    n = self.axes.index( axis )
    return align( take( self.func, indices, n ), self.axes, self.ndim )

class Get( ArrayFunc ):
  'get'

  def __init__( self, func, axis, item ):
    'constructor'

    self.func = func
    self.axis = axis
    self.item = item
    assert 0 <= axis < func.ndim, 'axis is out of bounds'
    assert 0 <= item < func.shape[axis], 'item is out of bounds'
    s = (Ellipsis,item) + (slice(None),)*(func.ndim-axis-1)
    shape = func.shape[:axis] + func.shape[axis+1:]
    ArrayFunc.__init__( self, args=(func,s), evalf=numpy.ndarray.__getitem__, shape=shape )

  def __graphviz__( self ):
    'graphviz representation'

    getitem = [ ':' ] * self.func.ndim
    getitem[self.axis] = str(self.item)
    return { 'shape': 'invtrapezium',
             'label': ','.join(getitem) }

  def _localgradient( self, ndims ):
    f = localgradient( self.func, ndims )
    return get( f, self.axis, self.item )

  def _get( self, i, item ):
    tryget = get( self.func, i+(i>=self.axis), item )
    if not isinstance( tryget, Get ): # avoid inf recursion
      return get( tryget, self.axis, self.item )

  def _take( self, indices, axis ):
    return get( take( self.func, indices, axis+(axis>=self.axis) ), self.axis, self.item )

class Reciprocal( ArrayFunc ):
  'reciprocal'

  def __init__( self, func ):
    'constructor'

    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.reciprocal, shape=func.shape )

  def _localgradient( self, ndims ):
    'local gradient'

    return -localgradient( self.func, ndims ) / self.func[...,_]**2

  def _get( self, i, item ):
    return reciprocal( get( self.func, i, item ) )

  def _align( self, axes, ndim ):
    return reciprocal( align( self.func, axes, ndim ) )

  def _multiply( self, other ):
    return other / self.func

class Product( ArrayFunc ):
  'product'

  def __init__( self, func, axis ):
    'constructor'

    self.func = func
    self.axis = axis
    assert 0 <= axis < func.ndim
    shape = func.shape[:axis] + func.shape[axis+1:]
    ArrayFunc.__init__( self, args=[func,axis-func.ndim], evalf=numpy.product, shape=shape )

  def _localgradient( self, ndims ):
    return self[...,_] * ( localgradient(self.func,ndims) / self.func[...,_] ).sum( self.axis )

  def _get( self, i, item ):
    func = get( self.func, i+(i>=self.axis), item )
    return product( func, self.axis-(i<self.axis) )

class IWeights( ArrayFunc ):
  'integration weights'

  def __init__( self ):
    'constructor'

    ArrayFunc.__init__( self, args=[ELEM,WEIGHTS], evalf=self.iweights, shape=() )

  @staticmethod
  def iweights( elem, weights ):
    'evaluate'

    det = 1
    while elem.parent:
      elem, transform = elem.parent
      det *= transform.det
    return weights * det

class Orientation( ArrayFunc ):
  'point orientation'

  def __init__( self ):
    'constructor'

    ArrayFunc.__init__( self, args=[ELEM], evalf=self.orientation, shape=() )

  @staticmethod
  def orientation( elem ):
    'evaluate'

    # VERY TEMPORARY
    elem, transform = elem.parent
    return ( transform.offset > .5 ) * 2 - 1

class Transform( ArrayFunc ):
  'transform'

  def __init__( self, fromdims, todims ):
    'constructor'

    assert fromdims > todims
    ArrayFunc.__init__( self, args=[ELEM,fromdims,todims], evalf=self.transform, shape=(fromdims,todims) )

  @staticmethod
  def transform( elem, fromdims, todims ):
    'transform'

    assert elem.ndims <= todims
    while elem.ndims < todims:
      elem, transform = elem.context or elem.parent

    fromelem = elem
    toelem, transform = fromelem.context or fromelem.parent

    T = transform.get_transform()
    while toelem.ndims < fromdims:
      toelem, transform = toelem.context or toelem.parent
      T = transform.transform_from( T, axis=0 )

    while fromelem.parent:
      fromelem, transform = fromelem.parent
      T = transform.transform_to( T, axis=1 )
    
    while toelem.parent:
      toelem, transform = toelem.parent
      T = transform.transform_from( T, axis=0 )

    return T

  def _localgradient( self, ndims ):
    return _zeros( self.shape + (ndims,) )

class Function( ArrayFunc ):
  'local gradient'

  def __init__( self, stdmap, igrad ):
    'constructor'

    self.stdmap = stdmap
    self.igrad = igrad
    ArrayFunc.__init__( self, args=(ELEM,POINTS,stdmap,igrad), evalf=self.function, shape=(None,)+(stdmap.ndims,)*igrad )

  @staticmethod
  def function( elem, points, stdmap, igrad ):
    'evaluate'

    while elem.ndims < stdmap.ndims:
      elem, transform = elem.context or elem.parent
      points = transform.eval( points )

    fvals = None
    while True:
      std = stdmap.get(elem)
      if std:
        if isinstance( std, tuple ):
          std, keep = std
          F = std.eval(points,grad=igrad)[(Ellipsis,keep)+(slice(None),)*igrad]
        else:
          F = std.eval(points,grad=igrad)
        fvals = F if fvals is None else numpy.concatenate( [ fvals, F ], axis=1 )
      if not elem.parent:
        break
      elem, transform = elem.parent
      points = transform.eval( points )
      if fvals is not None:
        for axis in range(2,2+igrad):
          fvals = numeric.dot( fvals, transform.invtrans, axis )

    assert fvals is not None, 'no function values encountered'
    return fvals

  def _localgradient( self, ndims ):
    assert ndims <= self.stdmap.ndims
    grad = Function( self.stdmap, self.igrad+1 )
    return grad if ndims == self.stdmap.ndims \
      else dot( grad[...,_], transform( self.stdmap.ndims, ndims ), axes=-2 )

class Choose( ArrayFunc ):
  'piecewise function'

  def __init__( self, level, choices, *warnargs ):
    'constructor'

    assert not warnargs, 'ERROR: the Choose object has changed. Please use piecewise instead.'

    self.level = level
    self.choices = tuple(choices)
    shape = _jointshape( *[ choice.shape for choice in choices ] )
    level = level[ (_,)*(len(shape)-level.ndim) ]
    assert level.ndim == len( shape )
    ArrayFunc.__init__( self, args=(level,)+self.choices, evalf=self.choose, shape=shape )

  @staticmethod
  def choose( level, *choices ):
    'choose'

    return numpy.choose( level, choices )

  def _localgradient( self, ndims ):
    grads = [ localgradient( choice, ndims ) for choice in self.choices ]
    if not any( grads ): # all-zero special case; better would be allow merging of intervals
      return _zeros( self.shape + (ndims,) )
    return Choose( self.level[...,_], grads )

class Choose2D( ArrayFunc ):
  'piecewise function'

  def __init__( self, coords, contour, fin, fout ):
    'constructor'

    shape = _jointshape( fin.shape, fout.shape )
    ArrayFunc.__init__( self, args=(coords,contour,fin,fout), evalf=self.choose2d, shape=shape )

  @staticmethod
  def choose2d( xy, contour, fin, fout ):
    'evaluate'

    from matplotlib import nxutils
    mask = nxutils.points_inside_poly( xy.T, contour )
    out = numpy.empty( fin.shape or fout.shape )
    out[...,mask] = fin[...,mask] if fin.shape else fin
    out[...,~mask] = fout[...,~mask] if fout.shape else fout
    return out

class Inverse( ArrayFunc ):
  'inverse'

  def __init__( self, func ):
    'constructor'

    assert func.shape[-1] == func.shape[-2]
    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numeric.inverse, shape=func.shape )

  def _localgradient( self, ndims ):
    G = localgradient( self.func, ndims )
    H = sum( self[...,_,:,:,_]
              * G[...,:,:,_,:], -3 )
    I = sum( self[...,:,:,_,_]
              * H[...,_,:,:,:], -3 )
    return -I

class DofMap( ArrayFunc ):
  'dof axis'

  def __init__( self, dofmap ):
    'new'

    self.dofmap = dofmap
    ArrayFunc.__init__( self, args=(ELEM,dofmap), evalf=self.evalmap, shape=[None] )

  @staticmethod
  def evalmap( elem, dofmap ):
    'evaluate'

    while elem.ndims < dofmap.ndims:
      elem, dummy = elem.context or elem.parent

    dofs = dofmap.get( elem )
    while dofs is None:
      elem, transform = elem.parent
      dofs = dofmap.get( elem )
    return dofs

class Concatenate( ArrayFunc ):
  'concatenate'

  def __init__( self, funcs, axis=0 ):
    'constructor'

    funcs = [ _asarray(func) for func in funcs ]
    ndim = funcs[0].ndim
    assert all( func.ndim == ndim for func in funcs )
    axis = numeric.normdim( ndim, axis )
    lengths = [ func.shape[axis] for func in funcs ]
    if any( n == None for n in lengths ):
      assert all( n == None for n in lengths )
      sh = None
    else:
      sh = sum( lengths )
    shape = _jointshape( *[ func.shape[:axis] + (sh,) + func.shape[axis+1:] for func in funcs ] )
    self.funcs = tuple(funcs)
    self.axis = axis
    ArrayFunc.__init__( self, args=(axis-ndim,)+self.funcs, evalf=self.concatenate, shape=shape )

  @staticmethod
  def concatenate( iax, *arrays ):
    'evaluate'

    ndim = numpy.max([ array.ndim for array in arrays ])
    axlen = util.sum( array.shape[iax] for array in arrays )
    shape = _jointshape( *[ (1,)*(ndim-array.ndim) + array.shape[:iax] + (axlen,) + ( array.shape[iax+1:] if iax != -1 else () ) for array in arrays ] )
    dtype = float if any( array.dtype == float for array in arrays ) else int
    retval = numpy.empty( shape, dtype=dtype )
    n0 = 0
    for array in arrays:
      n1 = n0 + array.shape[iax]
      retval[(slice(None),)*( iax if iax >= 0 else iax + ndim )+(slice(n0,n1),)] = array
      n0 = n1
    assert n0 == axlen
    return retval

  @property
  def blocks( self ):
    n = 0
    for func in self.funcs:
      for f, ind in func.blocks:
        yield f, ind[:self.axis] + (ind[self.axis]+n,) + ind[self.axis+1:]
      n += func.shape[self.axis]

  def _get( self, i, item ):
    if i == self.axis:
      for f in self.funcs:
        if item < f.shape[i]:
          return get( f, i, item )
        item -= f.shape[i]
    axis = self.axis - (self.axis > i)
    return concatenate( [ get( f, i, item ) for f in self.funcs ], axis=axis )

  def _localgradient( self, ndims ):
    funcs = [ localgradient( func, ndims ) for func in self.funcs ]
    return concatenate( funcs, axis=self.axis )

  def _multiply( self, other ):
    funcs = []
    n0 = 0
    for func in self.funcs:
      n1 = n0 + func.shape[ self.axis ]
      funcs.append( func * take( other, slice(n0,n1), self.axis ) )
      n0 = n1
    assert n0 == self.shape[ self.axis ]
    return concatenate( funcs, self.axis )

  def _add( self, other ):
    if isinstance( other, Concatenate ) and self.axis == other.axis:
      fg = zip( self.funcs, other.funcs )
      if all( f.shape == g.shape for (f,g) in fg ):
        return concatenate( [ f+g for (f,g) in fg ], axis=self.axis )
      raise NotImplementedError # TODO: create matching partition
    funcs = []
    n0 = 0
    for func in self.funcs:
      n1 = n0 + func.shape[ self.axis ]
      funcs.append( func + take( other, slice(n0,n1), self.axis ) )
      n0 = n1
    assert n0 == self.shape[ self.axis ]
    return concatenate( funcs, self.axis )

  def _subtract( self, other ):
    if isinstance( other, Concatenate ) and self.axis == other.axis:
      fg = zip( self.funcs, other.funcs )
      if all( f.shape == g.shape for (f,g) in fg ):
        return concatenate( [ f-g for (f,g) in fg ], axis=self.axis )
      raise NotImplementedError # TODO: create matching partition
    funcs = []
    n0 = 0
    for func in self.funcs:
      n1 = n0 + func.shape[ self.axis ]
      funcs.append( func - take( other, slice(n0,n1), self.axis ) )
      n0 = n1
    assert n0 == self.shape[ self.axis ]
    return concatenate( funcs, self.axis )

  def _sum( self, axis ):
    if axis == self.axis:
      return util.sum( sum( func, axis ) for func in self.funcs )
    funcs = [ sum( func, axis ) for func in self.funcs ]
    axis = self.axis - (axis<self.axis)
    return concatenate( funcs, axis )

  def _align( self, axes, ndim ):
    funcs = [ align( func, axes, ndim ) for func in self.funcs ]
    axis = axes[ self.axis ]
    return concatenate( funcs, axis )

  def _takediag( self ):
    if self.axis < self.ndim-2:
      return concatenate( [ takediag(f) for f in self.funcs ], axis=self.axis )
    axis = self.ndim-self.axis-3 # -1=>-2, -2=>-1
    n0 = 0
    funcs = []
    for func in self.funcs:
      n1 = n0 + func.shape[self.axis]
      funcs.append( takediag( take( func, slice(n0,n1), axis ) ) )
      n0 = n1
    assert n0 == self.shape[self.axis]
    return concatenate( funcs, axis=-1 )

  def _inflate( self, dofmap, length, axis ):
    assert self.shape[axis] == None
    return concatenate( [ inflate(func,dofmap,length,axis) for func in self.funcs ], self.axis )

  def _take( self, indices, axis ):
    if axis != self.axis:
      return concatenate( [ take(func,indices,axis) for func in self.funcs ], self.axis )
    funcs = []
    while len(indices):
      n = 0
      for func in self.funcs:
        if n <= indices[0] < n + func.shape[axis]:
          break
        n += func.shape[axis]
      else:
        raise Exception, 'index out of bounds'
      length = 1
      while length < len(indices) and n <= indices[length] < n + func.shape[axis]:
        length += 1
      funcs.append( take( func, indices[:length]-n, axis ) )
      indices = indices[length:]
    assert funcs, 'empty slice'
    if len( funcs ) == 1:
      return funcs[0]
    return concatenate( funcs, axis=axis )

  def _dot( self, other, axes ):
    n0 = 0
    funcs = []
    for f in self.funcs:
      n1 = n0 + f.shape[self.axis]
      funcs.append( dot( f, take( other, slice(n0,n1), self.axis ), axes ) )
      n0 = n1
    if self.axis in axes:
      return util.sum( funcs )
    return concatenate( funcs, self.axis - util.sum( ax<self.axis for ax in axes ) )

  def _negative( self ):
    return concatenate( [ -func for func in self.funcs ], self.axis )

class Interp1D( ArrayFunc ):
  'interpolate data'

  def __init__( self, x, xp, yp, left=None, right=None ):
    'constructor'

    assert _isfunc( x )
    xp = UseableArray( xp )
    yp = UseableArray( yp )
    assert ( numpy.diff(xp) > 0 ).all()
    assert xp.ndim == yp.ndim == 1
    assert xp.shape == yp.shape
    ArrayFunc.__init__( self, args=(x,xp,yp,left,right), evalf=numpy.interp, shape=() )

class Cross( ArrayFunc ):
  'cross product'

  def __init__( self, func1, func2, axis ):
    'contructor'

    self.func1 = func1
    self.func2 = func2
    self.axis = axis
    shape = _jointshape( func1.shape, func2.shape )
    assert 0 <= axis < len(shape), 'axis out of bounds: axis={0}, len(shape)={1}'.format( axis, len(shape) )
    ArrayFunc.__init__( self, args=(func1,func2,axis-len(shape)), evalf=numeric.cross, shape=shape )

  def _localgradient( self, ndims ):
    return cross( self.func1[...,_], localgradient(self.func2,ndims), axis=self.axis ) \
         - cross( self.func2[...,_], localgradient(self.func1,ndims), axis=self.axis )

  def _take( self, index, axis ):
    if axis != self.axis:
      return cross( take(self.func1,index,axis), take(self.func2,index,axis), self.axis )

class Determinant( ArrayFunc ):
  'normal'

  def __init__( self, func ):
    'contructor'

    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numeric.determinant, shape=func.shape[:-2] )

  def _localgradient( self, ndims ):
    Finv = inverse( self.func ).swapaxes(-2,-1)
    G = localgradient( self.func, ndims )
    return self[...,_] * sum( Finv[...,_] * G, axes=[-3,-2] )

class DofIndex( ArrayFunc ):
  'element-based indexing'

  @classmethod
  def stack( cls, funcs, axis ):
    'stack'

    array = funcs[0].array
    iax = funcs[0].iax
    if not all( isinstance(func,cls) and ( func.array == array ).all() and func.iax == iax for func in funcs ):
      return ArrayFunc.stack( funcs, axis )

    index = funcs[0].index.stack( [ func.index for func in funcs ], axis )
    return DofIndex( array, iax, index )

  def __init__( self, array, iax, index ):
    'constructor'

    assert index.ndim >= 1
    assert isinstance( array, numpy.ndarray )
    self.array = array
    assert 0 <= iax < self.array.ndim
    self.iax = iax
    self.index = index
    shape = self.array.shape[:iax] + index.shape + self.array.shape[iax+1:]
    item = [ slice(None) ] * self.array.ndim
    item[iax] = index
    ArrayFunc.__init__( self, args=[self.array]+item, evalf=self.dofindex, shape=shape )

  @staticmethod
  def dofindex( arr, *item ):
    'evaluate'

    return arr[item]

  def _get( self, i, item ):
    if self.iax <= i < self.iax + self.index.ndim:
      index = get( self.index, i - self.iax, item )
      return DofIndex( self.array, self.iax, index )
    return DofIndex( get( self.array, i, item ), self.iax if i > self.iax else self.iax-1, self.index )

  def _add( self, other ):
    if isinstance( other, DofIndex ) and self.iax == other.iax and self.index == other.index:
      n = _min( self.array.shape[0], other.array.shape[0] )
      return DofIndex( self.array[:n] + other.array[:n], self.iax, self.index )

  def _subtract( self, other ):
    if isinstance( other, DofIndex ) and self.iax == other.iax and self.index == other.index:
      n = _min( self.array.shape[0], other.array.shape[0] )
      return DofIndex( self.array[:n] - other.array[:n], self.iax, self.index )

  def _multiply( self, other ):
    if not _isfunc(other) and other.ndim == 0:
      return DofIndex( self.array * other, self.iax, self.index )

  def _localgradient( self, ndims ):
    return _zeros( self.shape + (ndims,) )

class Multiply( ArrayFunc ):
  'multiply'

  def __init__( self, func1, func2 ):
    'constructor'

    shape = _jointshape( func1.shape, func2.shape )
    self.funcs = func1, func2
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.multiply, shape=shape )

  def __eq__( self, other ):
    'compare'

    if self is other:
      return True
      
    if not isinstance(other,Multiply):
      return False

    return _equal( self.funcs[0], other.funcs[0] ) and _equal( self.funcs[1], other.funcs[1] ) \
        or _equal( self.funcs[0], other.funcs[1] ) and _equal( self.funcs[1], other.funcs[0] )

  def _sum( self, axis ):
    func1, func2 = self.funcs
    return dot( func1, func2, [axis] )

  def _get( self, i, item ):
    func1, func2 = self.funcs
    return get( func1, i, item ) * get( func2, i, item )

  def _add( self, other ):
    func1, func2 = self.funcs
    if other == func1:
      return func1 * (func2+1)
    if other == func2:
      return func2 * (func1+1)
    if isinstance( other, Multiply ):
      f1, f2 = other.funcs
      if f1 == func1:
        return f1 * ( f2 + func2 )
      if f1 == func2:
        return f1 * ( f2 + func1 )
      if f2 == func1:
        return f2 * ( f1 + func2 )
      if f2 == func2:
        return f2 * ( f1 + func1 )

  def _determinant( self ):
    if self.funcs[0].shape[-2:] == (1,1):
      return determinant( self.funcs[1] ) * self.funcs[0][...,0,0]
    if self.funcs[1].shape[-2:] == (1,1):
      return determinant( self.funcs[0] ) * self.funcs[1][...,0,0]

  def _product( self, axis ):
    func1, func2 = self.funcs
    return product( func1, axis ) * product( func2, axis )

  def _multiply( self, other ):
    if not _isfunc( other ):
      if not _isfunc( self.funcs[1] ):
        return self.funcs[0] * ( self.funcs[1] * other )
      if not _isfunc( self.funcs[0] ):
        return self.funcs[1] * ( self.funcs[0] * other )

  def _divide( self, other ):
    if not _isfunc( other ) and not _isfunc( self.funcs[1] ):
      return self.funcs[0] * ( self.funcs[1] / other )

  def _localgradient( self, ndims ):
    func1, func2 = self.funcs
    return func1[...,_] * localgradient( func2, ndims ) \
         + func2[...,_] * localgradient( func1, ndims )

  def _takediag( self ):
    func1, func2 = self.funcs
    return takediag( func1 ) * takediag( func2 )

  def _take( self, index, axis ):
    func1, func2 = self.funcs
    return take( func1, index, axis ) * take( func2, index, axis )

class Divide( ArrayFunc ):
  'divide'

  def __init__( self, func1, func2 ):
    'constructor'

    shape = _jointshape( func1.shape, func2.shape )
    self.funcs = func1, func2
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.divide, shape=shape )

  def _get( self, i, item ):
    func1, func2 = self.funcs
    return get( func1, i, item ) / get( func2, i, item )

  def _localgradient( self, ndims ):
    func1, func2 = self.funcs
    grad1 = localgradient( func1, ndims )
    grad2 = localgradient( func2, ndims )
    return ( grad1 - func1[...,_] * grad2 / func2[...,_] ) / func2[...,_]

  def _takediag( self ):
    func1, func2 = self.funcs
    return takediag( func1 ) / takediag( func2 )

  def _take( self, index, axis ):
    func1, func2 = self.funcs
    return take( func1, index, axis ) / take( func2, index, axis )

class Negative( ArrayFunc ):
  'negate'

  def __init__( self, func ):
    'constructor'

    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.negative, shape=func.shape )

  @property
  def blocks( self ):
    for f, ind in self.func.blocks:
      yield negative(f), ind

  def _add( self, other ):
    return other - self.func

  def _subtract( self, other ):
    return -( other + self.func )

  def _multiply( self, other ):
    if isinstance( other, Negative ):
      return self.func * other.func
    return -( self.func * other )

  def _divide( self, other ):
    if isinstance( other, Negative ):
      return self.func / other.func
    return -( self.func / other )

  def _negative( self ):
    return self.func

  def _elemint( self, weights ):
    return -elemint( self.func, weights )

  def _align( self, axes, ndim ):
    return -align( self.func, axes, ndim )

  def _get( self, i, item ):
    return -get( self.func, i, item )

  def _sum( self, axis ):
    return -sum( self.func, axis )

  def _localgradient( self, ndims ):
    return -localgradient( self.func, ndims )

  def _takediag( self ):
    return -takediag( self.func )

  def _take( self, index, axis ):
    return -take( self.func, index, axis )

class Add( ArrayFunc ):
  'add'

  def __init__( self, func1, func2 ):
    'constructor'

    self.funcs = func1, func2
    shape = _jointshape( func1.shape, func2.shape )
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.add, shape=shape )

  def __eq__( self, other ):
    'compare'

    return self is other or isinstance(other,Add) and (
        _equal( self.funcs[0], other.funcs[0] ) and _equal( self.funcs[1], other.funcs[1] )
     or _equal( self.funcs[0], other.funcs[1] ) and _equal( self.funcs[1], other.funcs[0] ) )

  def _sum( self, axis ):
    return sum( self.funcs[0], axis ) + sum( self.funcs[1], axis )

  def _localgradient( self, ndims ):
    func1, func2 = self.funcs
    return localgradient( func1, ndims ) + localgradient( func2, ndims )

  def _get( self, i, item ):
    func1, func2 = self.funcs
    return get( func1, i, item ) + get( func2, i, item )

  def _takediag( self ):
    func1, func2 = self.funcs
    return takediag( func1 ) + takediag( func2 )

  def _take( self, index, axis ):
    func1, func2 = self.funcs
    return take( func1, index, axis ) + take( func2, index, axis )

class Subtract( ArrayFunc ):
  'subtract'

  def __init__( self, func1, func2 ):
    'constructor'

    shape = _jointshape( func1.shape, func2.shape )
    self.funcs = func1, func2
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.subtract, shape=shape )

  def _sum( self, axis ):
    return sum( self.funcs[0], axis ) - sum( self.funcs[1], axis )

  def _negative( self ):
    func1, func2 = self.funcs
    return func2 - func1

  def _localgradient( self, ndims ):
    func1, func2 = self.funcs
    return localgradient( func1, ndims ) - localgradient( func2, ndims )

  def _takediag( self ):
    func1, func2 = self.funcs
    return takediag( func1 ) - takediag( func2 )

  def _take( self, index, axis ):
    func1, func2 = self.funcs
    return take( func1, index, axis ) - take( func2, index, axis )

class Dot( ArrayFunc ):
  'dot'

  def __init__( self, func1, func2, axes ):
    'constructor'

    shape = _jointshape( func1.shape, func2.shape )
    axes = _norm_and_sort( len(shape), axes )
    shape = list(shape)
    orig = range( len(shape) )
    for axis in reversed(axes):
      shape.pop( axis )
      assert orig.pop( axis ) == axis

    self.func1 = func1
    self.func2 = func2
    self.axes = axes
    self.orig = orig # new -> original axis
    ArrayFunc.__init__( self, args=(func1,func2,tuple( ax-func1.ndim for ax in axes )), evalf=numeric.contract, shape=shape )

  @classmethod
  def stack( cls, funcs, axis ):
    'stack funcs along new axis'

    axes = funcs[0].axes
    if not all( isinstance(func,cls) and func.axes == axes for func in funcs ):
      return ArrayFunc.stack( funcs, axis )

    func1 = funcs[0].func1
    if all( func.func1 == func1 for func in funcs ):
      func2 = funcs[0].func2
      newaxes = [ ax if ax < axis else ax + 1 for ax in axes ]
      return Dot( insert( func1, axis ), func2.stack( [ func.func2 for func in funcs ], axis ), newaxes )

    return ArrayFunc.stack( funcs, axis )

  def _get( self, i, item ):
    getax = self.orig[i]
    axes = [ ax - (ax>getax) for ax in self.axes ]
    return dot( get( self.func1, getax, item ), get( self.func2, getax, item ), axes )

  def _localgradient( self, ndims ):
    return dot( localgradient( self.func1, ndims ), self.func2[...,_], self.axes ) \
         + dot( self.func1[...,_], localgradient( self.func2, ndims ), self.axes )

  def _multiply( self, other ):
    if not _isfunc(other) and isinstance( self.func2, DofIndex ):
      return dot( self.func1, self.func2 * other, self.axes )

  def _add( self, other ):
    #TODO check for other combinations
    if isinstance( other, Dot ) and self.func1 == other.func1 and self.axes == other.axes and self.shape == other.shape:
      return dot( self.func1, self.func2 + other.func2, self.axes )

  def _subtract( self, other ):
    #TODO check for other combinations
    if isinstance( other, Dot ) and self.func1 == other.func1 and self.axes == other.axes and self.shape == other.shape:
      return dot( self.func1, self.func2 - other.func2, self.axes )

  def _takediag( self ):
    n1, n2 = self.orig[-2:]
    axes = [ ax-(n1<ax)-(n2<ax) for ax in self.axes ]
    return dot( takediag( self.func1, n1, n2 ), takediag( self.func2, n1, n2 ), axes )

  def _sum( self, axis ):
    axes = self.axes + (self.orig[axis],)
    return dot( self.func1, self.func2, axes )

  def _take( self, index, axis ):
    axis = self.orig[axis]
    return dot( take(self.func1,index,axis), take(self.func2,index,axis), self.axes )

# def _concatenate( self, other, axis ):
#   if isinstance( other, Dot ) and other.axes == self.axes:
#     for ax in self.axes:
#       if ax <= axis:
#         axis += 1
#     if self.func1 == other.func1:
#       return dot( self.func1, concatenate( [ self.func2, other.func2 ], axis ), self.axes )
#     if self.func1 == other.func2:
#       return dot( self.func1, concatenate( [ self.func2, other.func1 ], axis ), self.axes )
#     if self.func2 == other.func1:
#       return dot( self.func2, concatenate( [ self.func1, other.func2 ], axis ), self.axes )
#     if self.func2 == other.func2:
#       return dot( self.func2, concatenate( [ self.func1, other.func1 ], axis ), self.axes )

class Sum( ArrayFunc ):
  'sum'

  def __init__( self, func, axis ):
    'constructor'

    self.axis = axis
    self.func = func
    assert 0 <= axis < func.ndim, 'axis out of bounds'
    shape = func.shape[:axis] + func.shape[axis+1:]
    ArrayFunc.__init__( self, args=[func,axis-func.ndim], evalf=numpy.sum, shape=shape )

  def _sum( self, axis ):
    trysum = sum( self.func, axis+(axis>=self.axis) )
    if not isinstance( trysum, Sum ): # avoid inf recursion
      return sum( trysum, self.axis )

  def _localgradient( self, ndims ):
    return sum( localgradient( self.func, ndims ), self.axis )

class Debug( ArrayFunc ):
  'debug'

  def __init__( self, func ):
    'constructor'

    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=self.debug, shape=func.shape )

  @staticmethod
  def debug( arr ):
    'debug'

    print arr
    return arr

  def __str__( self ):
    'string representation'

    return '{DEBUG}'

  def _localgradient( self, ndims ):
    return Debug( localgradient( self.func, ndims ) )

class TakeDiag( ArrayFunc ):
  'extract diagonal'

  def __init__( self, func ):
    'constructor'

    assert func.shape[-1] == func.shape[-2]
    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numeric.takediag, shape=func.shape[:-1] )

  def _localgradient( self, ndims ):
    return takediag( localgradient( self.func, ndims ), -3, -2 ).swapaxes( -2, -1 )

  def _sum( self, axis ):
    if axis != self.ndim-1:
      return takediag( sum( self.func, axis ) )

class Take( ArrayFunc ):
  'generalization of numpy.take(), to accept lists, slices, arrays'

  def __init__( self, func, indices, axis ):
    'constructor'

    assert func.shape[axis] != 1
    self.func = func
    self.axis = axis
    self.indices = indices

    # try for regular slice
    start = indices[0]
    step = indices[1] - start
    stop = start + step * len(indices)

    s = [ slice(None) ] * func.ndim
    s[axis] = slice( start, stop, step ) if numpy.all( numpy.diff(indices) == step ) \
         else indices

    newlen, = numpy.empty( func.shape[axis] )[ indices ].shape
    assert newlen > 0
    shape = func.shape[:axis] + (newlen,) + func.shape[axis+1:]
    ArrayFunc.__init__( self, args=(func,(Ellipsis,)+tuple(s)), evalf=numpy.ndarray.__getitem__, shape=shape )

  def _localgradient( self, ndims ):
    return take( localgradient( self.func, ndims ), self.indices, self.axis )

  def _take( self, index, axis ):
    if axis == self.axis:
      if numpy.all( numpy.diff( self.indices ) == 1 ):
        indices = index + self.indices[0]
      else:
        indices = self.indices[index]
      return take( self.func, indices, axis )
    trytake = take( self.func, index, axis )
    if not isinstance( trytake, Take ): # avoid inf recursion
      return take( trytake, self.indices, self.axis )

class Power( ArrayFunc ):
  'power'

  def __init__( self, func, power ):
    'constructor'

    assert _isfunc( func )
    assert _isscalar( power )
    self.func = func
    self.power = power
    ArrayFunc.__init__( self, args=[func,power], evalf=numpy.power, shape=func.shape )

  def _localgradient( self, ndims ):
    return self.power * ( self.func**(self.power-1) )[...,_] * localgradient( self.func, ndims )

  def _get( self, i, item ):
    return get( self.func, i, item )**self.power

  def _sum( self, axis ):
    if self.power == 2:
      return dot( self.func, self.func, axis )

  def _takediag( self ):
    return takediag( self.func )**self.power

class Pointwise( ArrayFunc ):
  'pointwise transformation'

  def __init__( self, args, evalf, deriv ):
    'constructor'

    assert _isfunc( args )
    shape = args.shape[1:]
    self.args = args
    self.evalf = evalf
    self.deriv = deriv
    ArrayFunc.__init__( self, args=tuple(args), evalf=evalf, shape=shape )

  def _localgradient( self, ndims ):
    return ( self.deriv( self.args )[...,_] * localgradient( self.args, ndims ) ).sum( 0 )

  def _takediag( self ):
    return pointwise( takediag(self.args), self.evalf, self.deriv )

# PRIORITY OBJECTS
#
# Prority objects get priority in situations like A + B, which can be evaluated
# as A.__add__(B) and B.__radd__(A), such that they get to decide on how the
# operation is performed. The reason is that these objects are wasteful,
# generally introducing a lot of zeros, and we would like to see them disappear
# by the act of subsequent operations. For this annihilation to work well
# priority objects keep themselves at the surface where magic happens.

class PriorityFunc( ArrayFunc ):
  'just for graphviz'

  def __graphviz__( self ):
    'graphviz representation'

    args = ArrayFunc.__graphviz__( self )
    args['fontcolor'] = 'white'
    args['fillcolor'] = 'black'
    args['style'] = 'filled'
    return args

class Zeros( PriorityFunc ):
  'zero'

  def __init__( self, shape ):
    'constructor'

    arrayshape = tuple( shape )
    PriorityFunc.__init__( self, args=[POINTS,arrayshape], evalf=self.zeros, shape=shape )

  @property
  def blocks( self ):
    return ()

  @staticmethod
  def zeros( points, shape ):
    'prepend point axes'

    assert not any( sh is None for sh in shape ), 'cannot evaluate zeros for shape %s' % (shape,)
    shape = points.shape[:-1] + shape
    strides = [0] * len(shape)
    return numpy.lib.stride_tricks.as_strided( numpy.array(0.), shape, strides )

  def _repeat( self, length, axis ):
    assert self.shape[axis] == 1
    return _zeros( self.shape[:axis] + (length,) + self.shape[axis+1:] )

  def _localgradient( self, ndims ):
    return _zeros( self.shape+(ndims,) )

  def _add( self, other ):
    shape = _jointshape( self.shape, other.shape )
    return expand( other, shape )

  def _subtract( self, other ):
    shape = _jointshape( self.shape, other.shape )
    return -expand( other, shape )

  def _multiply( self, other ):
    shape = _jointshape( self.shape, other.shape )
    return _zeros( shape )

  def _dot( self, other, axes ):
    shape = [ sh for i, sh in enumerate(self.shape) if i not in axes ]
    return _zeros( shape )

  def _divide( self, other ):
    shape = _jointshape( self.shape, other.shape )
    return _zeros( shape )

  def _cross( self, other, axis ):
    return self

  def _negative( self ):
    return self

  def _diagonalize( self ):
    return _zeros( self.shape + (self.shape[-1],) )

  def _sum( self, axis ):
    return _zeros( self.shape[:axis] + self.shape[axis+1:] )

  def _align( self, axes, ndim ):
    shape = [1] * ndim
    for ax, sh in zip( axes, self.shape ):
      shape[ax] = sh
    return _zeros( shape )

  def _get( self, i, item ):
    return _zeros( self.shape[:i] + self.shape[i+1:] )

  def _takediag( self ):
    sh = max( self.shape[-2], self.shape[-1] )
    return _zeros( self.shape[:-2] + (sh,) )

  def _take( self, index, axis ):
    return _zeros( self.shape[:axis] + index.shape + self.shape[axis+1:] )

  def _inflate( self, dofmap, length, axis ):
    assert self.shape[axis] == None
    return _zeros( self.shape[:axis] + (length,) + self.shape[axis+1:] )

  def _elemint( self, weights ):
    return numpy.zeros( [1]*self.ndim )

  def _power( self, n ):
    return self

class Inflate( PriorityFunc ):
  'inflate'

  def __init__( self, func, dofmap, length, axis ):
    'constructor'

    self.func = func
    self.dofmap = dofmap
    self.length = length
    self.axis = axis
    shape = func.shape[:axis] + (length,) + func.shape[axis+1:]
    PriorityFunc.__init__( self, args=[func,dofmap,length,axis-func.ndim], evalf=self.inflate, shape=shape )

  @property
  def blocks( self ):
    for f, ind in self.func.blocks:
      assert ind[self.axis] == None
      yield f, ind[:self.axis] + (self.dofmap,) + ind[self.axis+1:]

  @staticmethod
  def inflate( array, indices, length, axis ):
    'inflate'

    shape = list( array.shape )
    shape[axis] = length
    inflated = numpy.zeros( shape )
    inflated[(Ellipsis,indices)+(slice(None),)*(-axis-1)] = array
    return inflated

  def _localgradient( self, ndims ):
    return inflate( localgradient(self.func,ndims), self.dofmap, self.length, self.axis )

  def _align( self, shuffle, ndims ):
    return inflate( align(self.func,shuffle,ndims), self.dofmap, self.length, shuffle[self.axis] )

  def _get( self, axis, item ):
    assert axis != self.axis
    return inflate( get(self.func,axis,item), self.dofmap, self.length, self.axis-(axis<self.axis) )

  def _dot( self, other, axes ):
    if isinstance( other, Inflate ) and other.axis == self.axis:
      other = other.func
    elif other.shape[self.axis] != 1:
      other = take( other, self.dofmap, self.axis )
    arr = dot( self.func, other, axes )
    if self.axis in axes:
      return arr
    return inflate( arr, self.dofmap, self.length, self.axis-util.sum(ax<self.axis for ax in axes) )

  def _multiply( self, other ):
    if isinstance( other, Inflate ) and self.axis == other.axis:
      other = other.func
    elif other.shape[self.axis] != 1:
      other = take( other, self.dofmap, self.axis )
    return inflate( multiply(self.func,other), self.dofmap, self.length, self.axis )

  def _divide( self, other ):
    if isinstance( other, Inflate ) and self.axis == other.axis:
      other = other.func
    elif other.shape[self.axis] != 1:
      other = take( other, self.dofmap, self.axis )
    return inflate( divide(self.func,other), self.dofmap, self.length, self.axis )

  def _add( self, other ):
    if isinstance( other, Inflate ) and self.axis == other.axis:
      other = other.func
    elif other.shape[self.axis] != 1:
      other = take( other, self.dofmap, self.axis )
    return inflate( add(self.func,other), self.dofmap, self.length, self.axis )

  def _subtract( self, other ):
    if isinstance( other, Inflate ) and self.axis == other.axis:
      other = other.func
    elif other.shape[self.axis] != 1:
      other = take( other, self.dofmap, self.axis )
    return inflate( subtract(self.func,other), self.dofmap, self.length, self.axis )

  def _cross( self, other, axis ):
    if isinstance( other, Inflate ) and self.axis == other.axis:
      other = other.func
    elif other.shape[self.axis] != 1:
      other = take( other, self.dofmap, self.axis )
    return inflate( cross(self.func,other), self.dofmap, self.length, self.axis )

  def _neg( self ):
    return inflate( neg(self.func), self.dofmap, self.length, self.axis )

  def _reciprocal( self ):
    return inflate( reciprocal(self.func), self.dofmap, self.length, self.axis )

  def _takediag( self ):
    assert self.axis < self.ndim-2
    return inflate( takediag(self.func), self.dofmap, self.length, self.axis )

  def _take( self, index, axis ):
    if axis == self.axis:
      assert index == self.dofmap
      return self.func
    return inflate( take( self.func, index, axis ), self.dofmap, self.length, self.axis )

  def _diagonalize( self ):
    assert self.axis < self.ndim-1
    return inflate( diagonalize(self.func), self.dofmap, self.length, self.axis )

  def _sum( self, axis ):
    arr = sum( self.func, axis )
    if axis == self.axis:
      return arr
    return inflate( arr, self.dofmap, self.length, self.axis-(axis<self.axis) )

class Diagonalize( PriorityFunc ):
  'diagonal matrix'

  def __init__( self, func ):
    'constructor'

    n = func.shape[-1]
    assert n != 1
    shape = func.shape + (n,)
    self.func = func
    PriorityFunc.__init__( self, args=[func], evalf=self.diagonalize, shape=shape )

  @staticmethod
  def diagonalize( data ):
    'evaluate'

    diagonalized = numpy.zeros( data.shape + (data.shape[-1],) )
    numeric.takediag( diagonalized )[:] = data
    return diagonalized

  def _get( self, i, item ):
    if i >= self.ndim-2:
      return kronecker( get( self.func, -1, item ), axis=-1, pos=item, length=self.func.shape[-1] )
    return diagonalize( get( self.func, i, item ) )

  def _inverse( self ):
    return diagonalize( reciprocal( self.func ) )

  def _determinant( self ):
    return product( self.func, -1 )

  def _multiply( self, other ):
    return diagonalize( self.func * takediag( other ) )

  def _negative( self ):
    return diagonalize( -self.func )

  def _sum( self, axis ):
    if axis >= self.ndim-2:
      return self.func
    return diagonalize( sum( self.func, axis ) )

  def _align( self, axes, ndim ):
    if axes[-2:] in [ (ndim-2,ndim-1), (ndim-1,ndim-2) ]:
      return diagonalize( align( self.func, axes[:-2] + (ndim-2,), ndim-1 ) )

class Repeat( PriorityFunc ):
  'repeat singleton axis'

  def __init__( self, func, length, axis ):
    'constructor'

    assert func.shape[axis] == 1
    self.func = func
    self.axis = axis
    self.length = length
    shape = func.shape[:axis] + (length,) + func.shape[axis+1:]
    PriorityFunc.__init__( self, args=[func,length,axis-func.ndim], evalf=numpy.repeat, shape=shape )

  def _negative( self ):
    return repeat( -self.func, self.length, self.axis )

  def _localgradient( self, ndims ):
    return repeat( localgradient( self.func, ndims ), self.length, self.axis )

  def _get( self, axis, item ):
    if axis == self.axis:
      assert 0 <= item < self.length
      return get( self.func, axis, 0 )
    return repeat( get( self.func, axis, item ), self.length, self.axis-(axis<self.axis) )

  def _sum( self, axis ):
    if axis == self.axis:
      return get( self.func, axis, 0 ) * self.length
    return repeat( sum( self.func, axis ), self.length, self.axis-(axis<self.axis) )

  def _product( self, axis ):
    if axis == self.axis:
      return get( self.func, axis, 0 )**self.length
    return repeat( product( self.func, axis ), self.length, self.axis-(axis<self.axis) )

  def _reciprocal( self ):
    return repeat( reciprocal( self.func ), self.length, self.axis )

  def _add( self, other ):
    return repeat( self.func + other, self.length, self.axis )

  def _subtract( self, other ):
    return repeat( self.func - other, self.length, self.axis )

  def _multiply( self, other ):
    return repeat( self.func * other, self.length, self.axis )

  def _divide( self, other ):
    return repeat( self.func / other, self.length, self.axis )

  def _align( self, shuffle, ndim ):
    return repeat( align(self.func,shuffle,ndim), self.length, shuffle[self.axis] )

  def _take( self, index, axis ):
    if axis == self.axis:
      return repeat( self.func, index.shape[0], self.axis )
    return repeat( take(self.func,index,axis), self.length, self.axis )

  def _cross( self, other, axis ):
    if axis != self.axis:
      return repeat( cross( self.func, other, axis ), self.length, self.axis )

class Const( PriorityFunc ):
  'pointwise transformation'

  def __init__( self, func ):
    'constructor'

    func = numpy.asarray( func )
    PriorityFunc.__init__( self, args=(POINTS,func), evalf=self.const, shape=func.shape )

  @staticmethod
  def const( points, arr ):
    'prepend point axes'

    shape = points.shape[:-1] + arr.shape
    strides = (0,) * (points.ndim-1) + arr.strides
    return numpy.lib.stride_tricks.as_strided( arr, shape, strides )

  def _localgradient( self, ndims ):
    return _zeros( self.shape+(ndims,) )

# AUXILIARY FUNCTIONS

def _jointshape( *shapes ):
  'determine shape after singleton expansion'

  ndim = len(shapes[0])
  combshape = [1] * ndim
  for shape in shapes:
    assert len(shape) == ndim
    for i, sh in enumerate(shape):
      if combshape[i] == 1:
        combshape[i] = sh
      else:
        assert sh in ( combshape[i], 1 ), 'incompatible shapes: %s' % ', '.join( str(sh) for sh in shapes )
  return tuple(combshape)

def _matchndim( *arrays ):
  'introduce singleton dimensions to match ndims'

  arrays = [ _asarray(array) for array in arrays ]
  ndim = _max( array.ndim for array in arrays )
  return [ array[(_,)*(ndim-array.ndim)] for array in arrays ]

def _isiterable( obj ):
  'check for iterability'

  try:
    iter(obj)
  except TypeError:
    return False
  return True

def _obj2str( obj ):
  'convert object to string'

  if isinstance( obj, numpy.ndarray ):
    if obj.size < 6:
      return _obj2str(obj.tolist())
    return 'array<%s>' % 'x'.join( map( str, obj.shape ) )
  if isinstance( obj, list ):
    if len(obj) < 6:
      return '[%s]' % ','.join( _obj2str(o) for o in obj )
    return '[#%d]' % len(obj)
  if isinstance( obj, (tuple,set) ):
    if len(obj) < 6:
      return '(%s)' % ','.join( _obj2str(o) for o in obj )
    return '(#%d)' % len(obj)
  if isinstance( obj, dict ):
    return '{#%d}@%x' % ( len(obj), id(obj) )
  if isinstance( obj, slice ):
    I = ''
    if obj.start is not None:
      I += str(obj.start)
    if obj.step is not None:
      I += ':' + str(obj.step)
    I += ':'
    if obj.stop is not None:
      I += str(obj.stop)
    return I
  if obj is Ellipsis:
    return '...'
  if obj is POINTS:
    return '<points>'
  if obj is WEIGHTS:
    return '<weights>'
  if obj is ELEM:
    return '<elem>'
  return str(obj)

_max = max
_min = min
_sum = sum
_isfunc = lambda arg: isinstance( arg, ArrayFunc )
_isscalar = lambda arg: _asarray(arg).ndim == 0
_isint = lambda arg: numpy.asarray( arg ).dtype == int
_ascending = lambda arg: ( numpy.diff(arg) > 0 ).all()
_iszero = lambda arg: isinstance( arg, Zeros ) or isinstance( arg, numpy.ndarray ) and numpy.all( arg == 0 )
_isunit = lambda arg: not _isfunc(arg) and ( numpy.asarray(arg) == 1 ).all()
_subsnonesh = lambda shape: tuple( 1 if sh is None else sh for sh in shape )
_normdims = lambda ndim, shapes: tuple( numeric.normdim(ndim,sh) for sh in shapes )
_zeros = lambda shape: Zeros( shape )
_zeros_like = lambda arr: _zeros( arr.shape )

def _call( obj, attr, *args ):
  'call method if it exists, return None otherwise'

  f = getattr( obj, attr, None )
  return f and f( *args )

def _norm_and_sort( ndim, args ):
  'norm axes, sort, and assert unique'

  normargs = tuple( sorted( numeric.normdim( ndim, arg ) for arg in args ) )
  assert _ascending( normargs ) # strict
  return normargs

def _jointdtype( *args ):
  'determine joint dtype'

  if any( _asarray(arg).dtype == float for arg in args ):
    return float
  return int

def _equal( arg1, arg2 ):
  'compare two objects'

  if arg1 is arg2:
    return True
  if not isinstance( arg1, numpy.ndarray ) and not isinstance( arg2, numpy.ndarray ):
    return arg1 == arg2
  arg1 = numpy.asarray( arg1 )
  arg2 = numpy.asarray( arg2 )
  if arg1.shape != arg2.shape:
    return False
  return numpy.all( arg1 == arg2 )

def _asarray( arg ):
  'convert to ArrayFunc or numpy.ndarray'
  
  if _isfunc(arg):
    return arg
  if isinstance( arg, (list,tuple) ) and any( _isfunc(f) for f in arg ):
    return stack( arg, axis=0 )
  arg = numpy.asarray( arg )
  if numpy.all( arg == 0 ):
    return _zeros( arg.shape )
  assert arg.dtype != object
  return arg

# FUNCTIONS

def insert( arg, n ):
  'insert axis'

  arg = _asarray( arg )
  n = numeric.normdim( arg.ndim+1, n )
  I = numpy.arange( arg.ndim )
  return align( arg, I + (I>=n), arg.ndim+1 )

def stack( args, axis=0 ):
  'stack functions along new axis'

  args = [ insert( arg, axis ) for arg in args ]
  ndim = args[0].ndim
  assert all( arg.ndim == ndim for arg in args[1:] ), 'arguments have non-matching shapes'
  return concatenate( args, axis )

def chain( funcs ):
  'chain'

  funcs = map( _asarray, funcs )
  shapes = [ func.shape[0] for func in funcs ]
  return [
    concatenate( [ func if i==j else _zeros( (sh,) + func.shape[1:] ) for j, sh in enumerate(shapes) ], axis=0 )
      for i, func in enumerate(funcs) ]

def vectorize( args ):
  'vectorize'

  return util.sum( kronecker( func, axis=1, length=len(args), pos=ifun ) for ifun, func in enumerate( chain( args ) ) )

def expand( arg, shape ):
  'expand'

  arg = _asarray( arg )
  shape = tuple(shape)
  assert len(shape) == arg.ndim

  for i, sh in enumerate( shape ):
    arg = repeat( arg, sh, i )
  assert arg.shape == shape

  return arg

def repeat( arg, length, axis ):
  'repeat'

  arg = _asarray( arg )
  axis = numeric.normdim( arg.ndim, axis )

  if arg.shape[axis] == length:
    return arg

  assert arg.shape[axis] == 1

  retval = _call( arg, '_repeat', length, axis )
  if retval is not None:
    return retval

  return Repeat( arg, length, axis )

def get( arg, iax, item ):
  'get item'

  assert _isint( item ) and _isscalar( item )

  arg = _asarray( arg )
  iax = numeric.normdim( arg.ndim, iax )
  sh = arg.shape[iax]
  assert isinstance(sh,int), 'cannot get item %r from axis %r' % ( item, sh )

  item = 0 if sh == 1 \
    else numeric.normdim( sh, item )

  if not _isfunc( arg ):
    return numeric.get( arg, iax, item )

  retval = _call( arg, '_get', iax, item )
  if retval is not None:
    return retval

  return Get( arg, iax, item )

def align( arg, axes, ndim ):
  'align'

  arg = _asarray( arg )

  assert ndim >= len(axes)
  assert len(axes) == arg.ndim
  axes = _normdims( ndim, axes )
  assert len(set(axes)) == len(axes), 'duplicate axes in align'

  if list(axes) == range(ndim):
    return arg

  if not _isfunc( arg ):
    return numeric.align( arg, axes, ndim )

  retval = _call( arg, '_align', axes, ndim )
  if retval is not None:
    return retval

  return Align( arg, axes, ndim )

def bringforward( arg, axis ):
  'bring axis forward'

  arg = _asarray(arg)
  axis = numeric.normdim(arg.ndim,axis)
  if axis == 0:
    return arg
  return transpose( args, [axis] + range(axis) + range(axis+1,args.ndim) )

def reciprocal( arg ):
  'reciprocal'

  arg = _asarray( arg )

  if not _isfunc( arg ):
    return numpy.reciprocal( arg )

  retval = _call( arg, '_reciprocal' )
  if retval is not None:
    return retval

  return Reciprocal( arg )

def elemint( arg, weights ):
  'elementwise integration'

  arg = _asarray( arg )

  if not _isfunc( arg ):
    return arg * ElemArea( weights )

  retval = _call( arg, '_elemint', weights )
  if retval is not None:
    return retval

  return ElemInt( arg, weights )

def grad( arg, coords, ndims=0 ):
  'local derivative'

  arg = _asarray( arg )
  if _isfunc( arg ):
    return arg.grad( coords, ndims )
  return _zeros( arg.shape + coords.shape )

def symgrad( arg, coords, ndims=0 ):
  'symmetric gradient'

  if _isfunc( arg ):
    return arg.symgrad( coords, ndims )
  return _zeros( arg.shape + coords.shape )

def div( arg, coords, ndims=0 ):
  'gradient'

  if _isfunc( arg ):
    return arg.div( coords, ndims )
  assert arg.shape[-1:] == coords.shape
  return _zeros( arg.shape[:-1] )

def sum( arg, axes=-1 ):
  'sum over multiply axes'

  arg = _asarray( arg )

  if _isiterable(axes):
    if len(axes) == 0:
      return arg
    axes = _norm_and_sort( arg.ndim, axes )
    assert numpy.all( numpy.diff(axes) > 0 ), 'duplicate axes in sum'
    arg = sum( arg, axes[1:] )
    axis = axes[0]
  else:
    axis = numeric.normdim( arg.ndim, axes )

  if arg.shape[axis] == 1:
    return get( arg, axis, 0 )

  if not _isfunc( arg ):
    return arg.sum( axis )

  retval = _call( arg, '_sum', axis )
  if retval is not None:
    return retval

  return Sum( arg, axis )

def dot( arg1, arg2, axes ):
  'dot product'

  arg1, arg2 = _matchndim( arg1, arg2 )
  shape = _jointshape( arg1.shape, arg2.shape )

  if _isiterable(axes):
    if len(axes) == 0:
      return arg1 * arg2
    axes = _norm_and_sort( len(shape), axes )
    assert numpy.all( numpy.diff(axes) > 0 ), 'duplicate axes in sum'
  else:
    axes = numeric.normdim( len(shape), axes ),

  for i, axis in enumerate( axes ):
    if arg1.shape[axis] == 1 or arg2.shape[axis] == 1:
      arg1 = sum( arg1, axis )
      arg2 = sum( arg2, axis )
      axes = axes[:i] + tuple( axis-1 for axis in axes[i+1:] )
      return dot( arg1, arg2, axes )

  if _isunit( arg1 ):
    return sum( expand( arg2, shape ), axes )

  if _isunit( arg2 ):
    return sum( expand( arg1, shape ), axes )

  if not _isfunc(arg1) and not _isfunc(arg2):
    return numeric.contract( arg1, arg2, axes )

  retval = _call( arg1, '_dot', arg2, axes )
  if retval is not None:
    return retval

  retval = _call( arg2, '_dot', arg1, axes )
  if retval is not None:
    return retval

  return Dot( arg1, arg2, axes )

def determinant( arg, axes=(-2,-1) ):
  'determinant'

  arg = _asarray( arg )
  ax1, ax2 = _norm_and_sort( arg.ndim, axes )
  assert ax2 > ax1 # strict

  n = arg.shape[ax1]
  assert n == arg.shape[ax2]
  if n == 1:
    return get( get( arg, ax2, 0 ), ax1, 0 )

  trans = range(ax1) + [-2] + range(ax1,ax2-1) + [-1] + range(ax2-1,arg.ndim-2)
  arg = align( arg, trans, arg.ndim )

  if not _isfunc( arg ):
    return numeric.determinant( arg )

  retval = _call( arg, '_determinant' )
  if retval is not None:
    return retval

  return Determinant( arg )

def det( arg, ax1, ax2 ):
  warnings.warn( '''det(array,i,j) will be removed in future
  Please use determinant(array,(i,j)) instead.''', DeprecationWarning, stacklevel=2 )
  return determinant( arg, (ax1,ax2) )

def inverse( arg, axes=(-2,-1) ):
  'inverse'

  arg = _asarray( arg )
  ax1, ax2 = _norm_and_sort( arg.ndim, axes )
  assert ax2 > ax1 # strict

  n = arg.shape[ax1]
  assert arg.shape[ax2] == n
  if n == 1:
    return reciprocal( arg )

  trans = range(ax1) + [-2] + range(ax1,ax2-1) + [-1] + range(ax2-1,arg.ndim-2)
  arg = align( arg, trans, arg.ndim )

  if not _isfunc( arg ):
    return numeric.inverse( arg ).transpose( trans )

  retval = _call( arg, '_inverse' )
  if retval is not None:
    return transpose( retval, trans )

  return transpose( Inverse(arg), trans )

def inv( arg, ax1=-2, ax2=-1 ):
  warnings.warn( '''inv(array,i,j) will be removed in future
  Please use inverse(array,(i,j)) instead.''', DeprecationWarning, stacklevel=2 )
  return inverse( arg, (ax1,ax2) )

def takediag( arg, ax1=-2, ax2=-1 ):
  'takediag'

  arg = _asarray( arg )
  ax1, ax2 = _norm_and_sort( arg.ndim, (ax1,ax2) )
  assert ax2 > ax1 # strict

  axes = range(ax1) + [-2] + range(ax1,ax2-1) + [-1] + range(ax2-1,arg.ndim-2)
  arg = align( arg, axes, arg.ndim )

  if arg.shape[-1] == 1:
    return get( arg, -1, 0 )

  if arg.shape[-2] == 1:
    return get( arg, -2, 0 )

  assert arg.shape[-1] == arg.shape[-2]

  if not _isfunc( arg ):
    return numeric.takediag( arg )

  retval = _call( arg, '_takediag' )
  if retval is not None:
    return retval

  return TakeDiag( arg )

def localgradient( arg, ndims ):
  'local derivative'

  arg = _asarray( arg )

  if not _isfunc( arg ):
    return _zeros( arg.shape + (ndims,) )

  lgrad = arg._localgradient( ndims )
  assert lgrad.ndim == arg.ndim + 1 and lgrad.shape[-1] == ndims \
     and all( sh2 == sh1 or sh1 is None and sh2 == 1 for sh1, sh2 in zip( arg.shape, lgrad.shape[:-1] ) ), \
      'bug found in localgradient(%d): %s -> %s' % ( ndims, arg.shape, lgrad.shape )

  return lgrad

def dotnorm( arg, coords, ndims=0 ):
  'normal component'

  return sum( arg * coords.normal( ndims-1 ) )

def kronecker( arg, axis, length, pos ):
  'kronecker'

  axis = numeric.normdim( arg.ndim+1, axis )
  arg = insert( arg, axis )
  args = [ _zeros_like(arg) ] * length
  args[pos] = arg
  return concatenate( args, axis=axis )

def diagonalize( arg ):
  'diagonalize'

  arg = _asarray( arg )

  if arg.shape[-1] == 1:
    return arg[...,_]

  retval = _call( arg, '_diagonalize' )
  if retval is not None:
    return retval

  return Diagonalize( arg )

def concatenate( args, axis=0 ):
  'concatenate'

  args = _matchndim( *args )
  axis = numeric.normdim( args[0].ndim, axis )
  i = 0

  if all( _iszero(arg) for arg in args ):
    shape = list( args[0].shape )
    axis = numeric.normdim( len(shape), axis )
    for arg in args[1:]:
      for i in range( len(shape) ):
        if i == axis:
          shape[i] += arg.shape[i]
        elif shape[i] == 1:
          shape[i] = arg.shape[i]
        else:
          assert arg.shape[i] in (shape[i],1)
    return _zeros( shape )

  while i+1 < len(args):
    arg1, arg2 = args[i:i+2]
    if not _isfunc(arg1) and not _isfunc(arg2):
      arg12 = numpy.concatenate( [ arg1, arg2 ], axis )
    else:
      arg12 = _call( arg1, '_concatenate', arg2, axis )
      if arg12 is None:
        i += 1
        continue
    args = args[:i] + [arg12] + args[i+2:]

  if len(args) == 1:
    return args[0]

  return Concatenate( args, axis )

def transpose( arg, trans=None ):
  'transpose'
  
  arg = _asarray( arg )
  if trans is None:
    invtrans = range( arg.ndim-1, -1, -1 )
  else:
    trans = _normdims( arg.ndim, trans )
    assert sorted(trans) == range(arg.ndim)
    invtrans = numpy.empty( arg.ndim, dtype=int )
    invtrans[ numpy.asarray(trans) ] = numpy.arange( arg.ndim )
  return align( arg, invtrans, arg.ndim )

def product( arg, axis ):
  'product'

  arg = _asarray( arg )
  axis = numeric.normdim( arg.ndim, axis )

  if arg.shape[axis] == 1:
    return get( arg, axis, 0 )

  if not _isfunc( arg ):
    return numpy.product( arg, axis )

  retval = _call( arg, '_product', axis )
  if retval is not None:
    return retval

  return Product( arg, axis )

def choose( level, choices ):
  'choose'
  
  choices = _matchndim( *choices )
  if _isfunc(level) or any( _isfunc(choice) for choice in choices ):
    return Choose( level, choices )
  return numpy.choose( level, choices )

def cross( arg1, arg2, axis ):
  'cross product'

  arg1, arg2 = _matchndim( arg1, arg2 )
  shape = _jointshape( arg1.shape, arg2.shape )
  axis = numeric.normdim( len(shape), axis )

  if not _isfunc(arg1) and not _isfunc(arg2):
    return numeric.cross(arg1,arg2,axis)

  retval = _call( arg1, '_cross', arg2, axis )
  if retval is not None:
    return retval

  retval = _call( arg2, '_cross', arg1, axis )
  if retval is not None:
    return -retval

  return Cross( arg1, arg2, axis )

def outer( arg1, arg2=None, axis=0 ):
  'outer product'

  arg1, arg2 = _matchndim( arg1, arg2 if arg2 is not None else arg1 )
  axis = numeric.normdim( arg1.ndim, axis )
  return insert(arg1,axis+1) * insert(arg1,axis)

def pointwise( args, evalf, deriv ):
  'general pointwise operation'

  args = _asarray( args )
  if _isfunc(args):
    return Pointwise( args, evalf, deriv )
  return evalf( *args )

def multiply( arg1, arg2 ):
  'multiply'

  arg1, arg2 = _matchndim( arg1, arg2 )
  shape = _jointshape( arg1.shape, arg2.shape )

  if _isunit( arg1 ):
    return expand( arg2, shape )

  if _isunit( arg2 ):
    return expand( arg1, shape )

  if not _isfunc(arg1) and not _isfunc(arg2):
    return numpy.multiply( arg1, arg2 )

  if _equal( arg1, arg2 ):
    return power( arg1, 2 )

  retval = _call( arg1, '_multiply', arg2 )
  if retval is not None:
    return retval

  retval = _call( arg2, '_multiply', arg1 )
  if retval is not None:
    return retval

  return Multiply( arg1, arg2 )

def divide( arg1, arg2 ):
  'divide'

  arg1, arg2 = _matchndim( arg1, arg2 )
  shape = _jointshape( arg1.shape, arg2.shape )

  if _isunit( arg1 ):
    return expand( reciprocal(arg2), shape )

  if _isunit( arg2 ):
    return expand( arg1, shape )

  if not _isfunc(arg1) and not _isfunc(arg2):
    return numpy.divide( arg1, arg2 )

  if not _isfunc(arg2):
    return arg1 * numpy.reciprocal(arg2)

  retval = _call( arg1, '_divide', arg2 )
  if retval is not None:
    return retval

  return Divide( arg1, arg2 )

def add( arg1, arg2 ):
  'add'

  arg1, arg2 = _matchndim( arg1, arg2 )
  shape = _jointshape( arg1.shape, arg2.shape )

  if _iszero( arg1 ):
    return expand( arg2, shape )

  if _iszero( arg2 ):
    return expand( arg1, shape )

  if not _isfunc(arg1) and not _isfunc(arg2):
    return numpy.add( arg1, arg2 )

  if _equal( arg1, arg2 ):
    return arg1 * 2

  retval = _call( arg1, '_add', arg2 )
  if retval is not None:
    return retval

  retval = _call( arg2, '_add', arg1 )
  if retval is not None:
    return retval

  return Add( arg1, arg2 )

def subtract( arg1, arg2 ):
  'subtract'

  arg1, arg2 = _matchndim( arg1, arg2 )
  shape = _jointshape( arg1.shape, arg2.shape )

  if _iszero( arg1 ):
    return expand( -arg2, shape )

  if _iszero( arg2 ):
    return expand( arg1, shape )

  if _equal( arg1, arg2 ):
    return _zeros( shape )

  if not _isfunc(arg1) and not _isfunc(arg2):
    return numpy.subtract( arg1, arg2 )

  if not _isfunc(arg2):
    return arg1 + numpy.negative(arg2)

  retval = _call( arg1, '_subtract', arg2 )
  if retval is not None:
    return retval

  return Subtract( arg1, arg2 )

def negative( arg ):
  'make negative'

  arg = _asarray(arg)

  if not _isfunc( arg ):
    return numpy.negative( arg )

  retval = _call( arg, '_negative' )
  if retval is not None:
    return retval

  return Negative( arg )

def power( arg, n ):
  'power'

  arg = _asarray( arg )
  assert _isscalar( n )

  if n == 1:
    return arg

  if n == 0:
    return numpy.ones( arg.shape )

  if n < 0:
    return reciprocal( power( arg, -n ) )

  retval = _call( arg, '_power', n )
  if retval is not None:
    return retval

  return Power( arg, n )

nsymgrad = lambda arg, coords: ( symgrad(arg,coords) * coords.normal() ).sum()
ngrad = lambda arg, coords: ( grad(arg,coords) * coords.normal() ).sum()
sin = lambda arg: pointwise( [arg], numpy.sin, cos )
cos = lambda arg: pointwise( [arg], numpy.cos, lambda x: -sin(x) )
tan = lambda arg: pointwise( [arg], numpy.tan, lambda x: cos(x)**-2 )
exp = lambda arg: pointwise( [arg], numpy.exp, exp )
ln = lambda arg: pointwise( [arg], numpy.log, reciprocal )
log2 = lambda arg: ln(arg) / ln(2)
log10 = lambda arg: ln(arg) / ln(10)
sqrt = lambda arg: arg**.5
argmin = lambda arg, axis: pointwise( bringforward(arg,axis), lambda *x: numpy.argmin(numeric.stack(x),axis=0), _zeros_like )
argmax = lambda arg, axis: pointwise( bringforward(arg,axis), lambda *x: numpy.argmax(numeric.stack(x),axis=0), _zeros_like )
arctan2 = lambda arg1, arg2=None: pointwise( arg1 if arg2 is None else [arg1,arg2], numpy.arctan2, lambda x: stack([x[1],-x[0]]) / sum(power(x,2),0) )
greater = lambda arg1, arg2=None: pointwise( arg1 if arg2 is None else [arg1,arg2], numpy.greater, _zeros_like )
less = lambda arg1, arg2=None: pointwise( arg1 if arg2 is None else [arg1,arg2], numpy.less, _zeros_like )
min = lambda arg1, *args: choose( argmin( arg1 if not args else (arg1,)+args, axis=0 ), arg1 if not args else (arg1,)+args )
max = lambda arg1, *args: choose( argmax( arg1 if not args else (arg1,)+args, axis=0 ), arg1 if not args else (arg1,)+args )
sign = lambda arg: pointwise( [arg], numpy.sign, _zeros_like )
abs = lambda arg: arg * sign(arg)
sinh = lambda arg: .5 * ( exp(arg) - exp(-arg) )
cosh = lambda arg: .5 * ( exp(arg) + exp(-arg) )
tanh = lambda arg: 1 - 2. / ( exp(2*arg) + 1 )
arctanh = lambda arg: .5 * ( ln(1+arg) - ln(1-arg) )
piecewise = lambda level, intervals, *funcs: choose( sum( greater( insert(level,-1), intervals ) ), funcs )
trace = lambda arg, n1=-2, n2=-1: sum( takediag( arg, n1, n2 ) )
eye = lambda n: diagonalize( expand( [1.], (n,) ) )
norm2 = lambda arg, axis=-1: sqrt( sum( arg * arg, axis ) )
heaviside = lambda arg: greater( arg, 0 )

class ElemMap( dict ):
  def __init__( self, d, ndims ):
    self.update( d )
    self.ndims = ndims
  def __eq__( self, other ):
    return self is other
  def __str__( self ):
    return 'ElemMap'
  def __repr__( self ):
    return 'ElemMap'

def function( stdmap, dofmap, ndofs, ndims ):
  'create function on ndims-element'

  func = Function( ElemMap(stdmap,ndims), igrad=0 )
  return Inflate( func, DofMap(ElemMap(dofmap,ndims)), length=ndofs, axis=0 )

def transform( fromdims, todims ):
  'transform to lower-dimensional space'

  if fromdims == todims:
    return eye( fromdims )
  assert fromdims > todims
  return Transform( fromdims, todims )

def take( arg, index, axis ):
  'take index'

  arg = _asarray( arg )
  axis = numeric.normdim( arg.ndim, axis )

  if isinstance( index, slice ):
    assert index.start == None or index.start >= 0
    assert index.stop != None and index.stop > 0
    index = numpy.arange( index.start or 0, index.stop, index.step )
    assert index.size > 0
  elif not _isfunc( index ):
    index = numpy.asarray( index, dtype=int )
    assert numpy.all( index >= 0 )
    assert index.size > 0
  assert index.ndim == 1

  if arg.shape[axis] == 1:
    return repeat( arg, index.shape[0], axis )

  if not _isfunc( index ):
    allindices = numpy.arange( arg.shape[axis] )
    index = allindices[index]
    if numpy.all( index == allindices ):
      return arg

  if index.shape[0] == 1:
    return insert( get( arg, axis, index[0] ), axis )

  retval = _call( arg, '_take', index, axis )
  if retval is not None:
    return retval

  if _isfunc( index ):
    return DofIndex( arg, axis, index )

  if not _isfunc( arg ):
    return numpy.take( arg, index, axis )

  return Take( arg, index, axis )

def inflate( arg, dofmap, length, axis ):
  'inflate'

  arg = _asarray( arg )
  axis = numeric.normdim( arg.ndim, axis )
  assert arg.shape[axis] == None

  retval = _call( arg, '_inflate', dofmap, length, axis )
  if retval is not None:
    return retval

  return Inflate( arg, dofmap, length, axis )

def Heaviside( arg ):
  warnings.warn( '''Heaviside will be removed in future
  Please use heaviside instead.''', DeprecationWarning, stacklevel=2 )
  return heaviside( arg )

def Chain( funcs ):
  warnings.warn( '''Chain will be removed in future
  Please use chain instead.''', DeprecationWarning, stacklevel=2 )
  return chain( funcs )

def Vectorize( funcs ):
  warnings.warn( '''Vectorize will be removed in future
  Please use vectorize instead.''', DeprecationWarning, stacklevel=2 )
  return vectorize( funcs )

def Tan( func ):
  warnings.warn( '''Tan will be removed in future
  Please use tan instead.''', DeprecationWarning, stacklevel=2 )
  return tan( func )

def Sin( func ):
  warnings.warn( '''Sin will be removed in future
  Please use sin instead.''', DeprecationWarning, stacklevel=2 )
  return sin( func )

def Cos( func ):
  warnings.warn( '''Cos will be removed in future
  Please use cos instead.''', DeprecationWarning, stacklevel=2 )
  return cos( func )

def Sinh( func ):
  warnings.warn( '''Sinh will be removed in future
  Please use sinh instead.''', DeprecationWarning, stacklevel=2 )
  return sinh( func )

def Cosh( func ):
  warnings.warn( '''Cosh will be removed in future
  Please use cosh instead.''', DeprecationWarning, stacklevel=2 )
  return cosh( func )

def Tanh( func ):
  warnings.warn( '''Tanh will be removed in future
  Please use tanh instead.''', DeprecationWarning, stacklevel=2 )
  return tanh( func )

def Arctanh( func ):
  warnings.warn( '''Arctanh will be removed in future
  Please use arctanh instead.''', DeprecationWarning, stacklevel=2 )
  return arctanh( func )

def StaticArray( arg ):
  warnings.warn( '''StaticArray will be removed in future
  Things should just work without it now.''', DeprecationWarning, stacklevel=2 )
  return arg

def Stack( arg ):
  warnings.warn( '''Stack will be removed in future
  Please use stack instead.''', DeprecationWarning, stacklevel=2 )
  return stack( arg )

def Log( arg ):
  warnings.warn( '''Log will be removed in future
  Please use ln instead.''', DeprecationWarning, stacklevel=2 )
  return ln( arg )

def Arctan2( arg1, arg2 ):
  warnings.warn( '''Arctan2 will be removed in future
  Please use arctan2 instead.''', DeprecationWarning, stacklevel=2 )
  return arctan2( arg1, arg2 )

def Min( arg1, arg2 ):
  warnings.warn( '''Min will be removed in future
  Please use min instead.''', DeprecationWarning, stacklevel=2 )
  return min( arg1, arg2 )

def Max( arg1, arg2 ):
  warnings.warn( '''Max will be removed in future
  Please use max instead.''', DeprecationWarning, stacklevel=2 )
  return max( arg1, arg2 )

def Log10( arg ):
  warnings.warn( '''Log10 will be removed in future
  Please use log10 instead.''', DeprecationWarning, stacklevel=2 )
  return log10( arg )

def Log2( arg ):
  warnings.warn( '''Log2 will be removed in future
  Please use log2 instead.''', DeprecationWarning, stacklevel=2 )
  return log2( arg )

# vim:shiftwidth=2:foldmethod=indent:foldnestmax=2
