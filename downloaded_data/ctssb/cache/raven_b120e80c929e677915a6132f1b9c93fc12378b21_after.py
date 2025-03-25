'''
Created on Dec 2, 2014

@author: talbpw
'''
#for future compatibility with Python 3-----------------------------------------------
from __future__ import division, print_function, unicode_literals, absolute_import
import warnings
warnings.simplefilter('default',DeprecationWarning)
#End compatibility block for Python 3-------------------------------------------------

#External Modules---------------------------------------------------------------------
import numpy as np
import scipy.special.orthogonal as quads
from scipy.fftpack import ifft
from scipy.misc import factorial
from itertools import product
from collections import OrderedDict as OrdDict
from operator import itemgetter
#External Modules End-----------------------------------------------------------------

#Internal Modules
from BaseClasses import BaseType
from JobHandler import JobHandler
from utils import returnPrintTag, returnPrintPostTag, find_distribution1D
#Internal Modules End-----------------------------------------------------------------


class SparseQuad(object):
  '''Base class to produce sparse-grid multiple-dimension quadrature.'''
  #TODO is this where this class should be defined?  It's not a Quadrature, but it's related.
  def __init__(self):
    self.type     = 'SparseQuad'
    self.printTag = 'SparseQuad' #FIXME use utility methods for right length
    self.c        = [] #array of coefficient terms for component tensor grid entries
    self.oldsg    = [] #storage space for re-ordered versions of sparse grid
    self.indexSet = None #IndexSet object
    self.distDict = None #dict{varName: Distribution object}
    self.quadDict = None #dict{varName: Quadrature object}
    self.polyDict = None #dict{varName: OrthoPolynomial object}
    self.varNames = []   #array of names, in order of distDict.keys()
    self.N        = None #dimensionality of input space
    self.SG       = None #dict{ (point,point,point): weight}

  ##### OVERWRITTEN BUILTINS #####
  def __getitem__(self,n):
    '''Returns the point and weight for entry 'n'.
    @ In n, integer, index of desired components
    @ Out, tuple, points and weight at index n
    '''
    return self.points(n),self.weights(n)

  def __len__(self):
    ''' Returns cardinality of sparse grid.
    @ In None, None
    @ Out int, size of sparse grid
    '''
    return len(self.weights())

  def __repr__(self):
    '''Slightly more human-readable version of printout.
    @ In None, None
    @ Out string, list of points and weights
    '''
    msg='SparseQuad: (point) | weight\n'
    for p in range(len(self)):
      msg+='    ('
      pt,wt = self[p]
      for i in pt:
        if i<0:
          msg+='%1.9f,' %i
        else:
          msg+=' %1.9f,' %i
      msg=msg[:-1]+') | %1.9f'%wt+'\n'
      #msg+='    '+str(self[p])+'\n'
    return msg

  def __csv__(self):
    '''Slightly more human-readable version of printout.
    @ In None, None
    @ Out string, list of points and weights
    '''
    msg=''
    for _ in range(len(self[0][0])):
      msg+='pt,'
    msg+='wt\n'
    for p in range(len(self)):
      pt,wt = self[p]
      for i in pt:
        msg+='%1.9f,' %i
      msg+='%1.9f\n' %wt
    return msg

  def __getstate__(self):
    '''Determines picklable items
    @ In None, None
    @ Out tuple(tuple(float),float), points and weights
    '''
    return [self.points(),self.weights()]

  def __setstate__(self,state):
    '''Determines how to load from picklable items
    @ In tuple(tuple(float),float), points and weights
    @ Out None, None
    '''
    if   type(state)==dict: self.__initFromDict(state)
    elif type(state)==list: self.__initFromPoints(state[0],state[1])

  def __eq__(self,other):
    '''Checks equivalency between sparsequads
    @ In other, object, object to compare to
    @ Out, bool, equivalency
    '''
    if not isinstance(other,self.__class__): return False
    if len(self.SG)!=len(other.SG):return False
    for pt,wt in self.SG.items():
      if wt != other.SG[pt]:
        return False
    return True

  def __ne__(self,other):
    '''Checks inequivalency between sparsequads
    @ In other, object, object to compare to
    @ Out, bool, inequivalency
    '''
    return not self.__eq__(other)

  ##### PRIVATE MEMBERS #####
  def __initFromPoints(self,pts,wts):
    '''Initializes sparse grid from pt, wt arrays
    @ In pts, array(tuple(float)), points for grid
    @ In wts, array(float), weights for grid
    @ Out None, None
    '''
    newSG={}
    for p,pt in enumerate(pts):
      newSG[pt]=wts[p]
    self.SG=newSG

  def __initFromDict(self,ndict):
    '''Initializes sparse grid from dictionary
    @ In ndict, {tuple(float): float}, {point: weight}
    @ Out None, None
    '''
    self.SG=ndict.copy()

  ##### PROTECTED MEMBERS #####
  def _remap(self,newNames):
    '''Reorders data in the sparse grid.  For instance,
       original:       { (a1,b1,c1): w1,
                         (a2,b2,c2): w2,...}
       remap([a,c,b]): { (a1,c1,b1): w1,
                         (a2,c2,b2): w2,...}
    @ In newNames, tuple(str), list of dimension names
    @ Out None, None
    '''
    #TODO optimize me!~~
    oldNames = self.varNames[:]
    #check consistency
    if len(oldNames)!=len(newNames): raise KeyError('SPARSEGRID: Remap mismatch! Dimensions are not the same!')
    for name in oldNames:
      if name not in newNames: raise KeyError('SPARSEGRID: Remap mismatch! '+name+' not found in original variables!')
    wts = self.weights()
    #split by columns (dim) instead of rows (points)
    oldlists = self._xy()
    #stash point lists by name
    oldDict = {}
    for n,name in enumerate(oldNames):
      oldDict[name]=oldlists[n]
    #make new lists
    newlists = list(oldDict[name] for name in newNames)
    #sort new list
    newptwt = list( list(pt)+[wts[p]] for p,pt in enumerate(zip(*newlists)))
    newptwt.sort(key=itemgetter(*range(len(newptwt[0]))))
    #recompile as ordered dict
    newSG=OrdDict()
    for combo in newptwt:
      newSG[tuple(combo[:-1])]=combo[-1] #weight is last entry
    self.oldsg.append(self.SG) #FIXME this could be expensive if not needed
    self.SG = newSG
    self.varNames = newNames

#  def _extrema(self):
#    '''Finds largest and smallest point among all points by dimension.'''
#    points = self.point()
#    low= np.ones(len(points[0]))*1e300
#    hi = np.ones(len(points[0]))*(-1e300)
#    for pt in pts:
#      for i,p in enumerate(pt):
#        low[i]=min(low[i],p)
#        hi[i] =max(hi[i] ,p)
#    return low,hi

  def _xy(self):
    '''Returns reordered points.
       Points = [(a1,b1,...,z1),
                 (a2,b2,...,z2),
                 ...]
       Returns [(a1,a2,a3,...),
                (b1,b2,b3,...),
                ...,
                (z1,z2,z3,...)]
    @ In , None  , None
    @ Out, array of tuples, points by dimension
    '''
    return zip(*self.points())

  ##### PUBLIC MEMBERS #####
  def initialize(self, indexSet, maxPoly, distDict, quadDict, polyDict, handler):
    '''Initializes sparse quad to be functional.
    @ In indexSet, IndexSet object, index set
    @ In maxPoly, int, relative largest polynomial order to use
    @ In distDict, dict{varName,Distribution object}, distributions
    @ In quadDict, dict{varName,Quadrature object}, quadratures
    @ In polyDict, dict{varName,OrthoPolynomial object}, polynomials
    @ In handler, JobHandler, parallel processing tool
    @ Out, None, None
    '''
    self.indexSet = np.array(indexSet[:])
    self.distDict = distDict
    self.quadDict = quadDict
    self.polyDict = polyDict
    self.varNames = self.distDict.keys()
    self.N        = len(self.varNames)
    #we know how this ends if it's tensor product index set
    if indexSet.type=='Tensor Product':
      self.c=[1]
      self.indexSet=[self.indexSet[-1]]
    else:
      if handler !=None:
        self.parallelMakeCoeffs(handler)
      else:
        self.smarterMakeCoeffs()
      survive = np.nonzero(self.c!=0)
      self.c=self.c[survive]
      self.indexSet=self.indexSet[survive]
    self.SG=OrdDict() #keys on points, values on weights
    if handler!=None: self.parallelSparseQuadGen(handler)
    else:
      for j,cof in enumerate(self.c):
        idx = self.indexSet[j]
        m = self.quadRule(idx)+1
        new = self.tensorGrid((m,idx))
        for i in range(len(new[0])):
          newpt=tuple(new[0][i])
          newwt=new[1][i]*self.c[j]
          if newpt in self.SG.keys():
            self.SG[newpt]+=newwt
          else:
            self.SG[newpt] = newwt

  def parallelSparseQuadGen(self,handler):
    '''Generates sparse quadrature points in parallel.
    @ In handler, JobHandler, parallel processing tool
    @ Out, None, None
    '''
    numRunsNeeded=len(self.c)
    j=-1
    while True:
      finishedJobs = handler.getFinished()
      for job in finishedJobs:
        if job.getReturnCode() == 0:
          new = job.returnEvaluation()[1]
          for i in range(len(new[0])):
            newpt = tuple(new[0][i])
            newwt = new[1][i]*float(job.identifier)
            if newpt in self.SG.keys():
              self.SG[newpt]+= newwt
            else:
              self.SG[newpt] = newwt
        else:
          print(self.printTag+': Sparse quad generation',job.identifier,'failed...')
      if j<numRunsNeeded-1:
        for k in range(min(numRunsNeeded-1-j,handler.howManyFreeSpots())):
          j+=1
          cof=self.c[j]
          idx = self.indexSet[j]
          m=self.quadRule(idx)+1
          handler.submitDict['Internal']((m,idx),self.tensorGrid,str(cof))
      else:
        if handler.isFinished() and len(handler.getFinishedNoPop())==0:break

  def quadRule(self,idx):
    '''Collects the cumulative effect of quadrature rules across the dimensions.i
    @ In idx, tuple(int), index set point
    @ Out, tuple(int), quadrature orders to use
    '''
    tot=np.zeros(len(idx),dtype=np.int64)
    for i,ix in enumerate(idx):
      tot[i]=self.quadDict.values()[i].quadRule(ix)
    return tot

  def points(self,n=None):
    '''Returns sparse grid points
    @ In n,string,splice instruction
    @ Out, tuple(float) or tuple(tuple(float)), requested points
    '''
    if n==None:
      return self.SG.keys()
    else:
      return self.SG.keys()[n]

  def weights(self,n=None):
    '''Either returns the list of weights, or the weight indexed at n, or the weight corresponding to point n.
    @ In n,string,splice instruction
    @ Out, float or tuple(float), requested weights
    '''
    if n==None:
      return self.SG.values()
    else:
      try: return self.SG[tuple(n)]
      except TypeError:  return self.SG.values()[n]

#  def serialMakeCoeffs(self):
#    '''Brute force method to create coefficients for each index set in the sparse grid approximation.
#      This particular implementation is faster for 2 dimensions, but slower for
#      more than 2 dimensions, than the smarterMakeCeoffs.'''
#    #TODO FIXME or just remove me.
#    print('WARNING: serialMakeCoeffs may be broken.  smarterMakeCoeffs is better.')
#    self.c=np.zeros(len(self.indexSet))
#    jIter = product([0,1],repeat=self.N) #all possible combinations in the sum
#    for jx in jIter: #from here down goes in the paralellized bit
#      for i,ix in enumerate(self.indexSet):
#        ix = np.array(ix)
#        comb = tuple(jx+ix)
#        if comb in self.indexSet:
#          self.c[i]+=(-1)**sum(jx)

  def smarterMakeCoeffs(self):
    '''Somewhat optimized method to create coefficients for each index set in the sparse grid approximation.
       This particular implementation is faster for any more than 2 dimensions in comparison with the
       serialMakeCoeffs method.
    @ In, None, None
    @ Out, None, None
    '''
    N=len(self.indexSet)
    iSet = self.indexSet[:]
    self.c=np.ones(N)
    for i in range(N): #could be parallelized from here
      idx = iSet[i]
      for j in range(i+1,N):
        jdx = iSet[j]
        d = jdx-idx
        if all(np.logical_and(d>=0,d<=1)):
          self.c[i]+=(-1)**sum(d)

  def parallelMakeCoeffs(self,handler):
    '''Same thing as smarterMakeCoeffs, but in parallel.
    @ In, None, None
    @ Out, None, None
    '''
    N=len(self.indexSet)
    self.c=np.zeros(N)
    i=-1
    while True:
      finishedJobs = handler.getFinished()
      for job in finishedJobs:
        if job.getReturnCode() == 0:
          self.c[int(job.identifier)]=job.returnEvaluation()[1]
        else:
          print(self.printTag+': Sparse grid index',job.identifier,'failed...')
      if i<N-1: #load new inputs, up to 100 at a time
        for k in range(min(handler.howManyFreeSpots(),N-1-i)):
          i+=1
          handler.submitDict['Internal']((N,i,self.indexSet[i],self.indexSet[:]),self.makeSingleCoeff,str(i))
      else:
        if handler.isFinished() and len(handler.getFinishedNoPop())==0:break

  def makeSingleCoeff(self,arglist):
    '''Batch-style algorithm to calculate a single coefficient
    @ In arglist, tuple(int,int,tuple(int),IndexSet), required arguments
    @ Out, float, coefficient for subtensor i
    '''
    N,i,idx,iSet = arglist
    c=1
    for j in range(i+1,N):
      jdx = iSet[j]
      d = jdx-idx
      if all(np.logical_and(d>=0,d<=1)):
        c += (-1)**sum(d)
    return c

  def tensorGrid(self,args):
    '''Creates a tensor product of quadrature points.
    @ In args, tuple(int,tuple(int)), number points and index set point
    @ Out tuple(tuple(float),float), requisite points and weights
    '''
    m,idx = args
    pointLists=[]
    weightLists=[]
    for n,distr in enumerate(self.distDict.values()):
      quad = self.quadDict.values()[n]
      mn = m[n]
      pts,wts=quad(mn)
      pts=pts.real
      wts=wts.real
      pts = distr.convertToDistr(quad.type,pts)
      pointLists.append(pts)
      weightLists.append(wts)
    points = list(product(*pointLists))
    weights= list(product(*weightLists))
    for k,wtset in enumerate(weights):
      weights[k]=np.product(wtset)
    return points,weights




class QuadratureSet(object):
  '''Base class to produce standard quadrature points and weights.
     Points and weights are obtained as
     -------------------
     myQuad = Legendre()
     pts,wts = myQuad(n)
     '''
  def __init__(self):
    self.type = self.__class__.__name__
    self.name = self.__class__.__name__
    self.debug = False #toggles print statements
    self.rule  = None #tool for generating points and weights for a given order
    self.params = [] #additional parameters for quadrature (alpha,beta, etc)

  def __call__(self,order):
    '''Defines operations to return correct pts, wts
    @ In order, int, order of desired quadrature
    @ Out, tuple(tuple(float),float) points and weight
    '''
    pts,wts = self.rule(order,*self.params)
    pts = np.around(pts,decimals=15) #TODO helps with checking equivalence, might not be desirable
    return pts,wts

  def __eq__(self,other):
    """Checks equivalency of quad set
    @ In , other, object , object to compare to
    @ Out, boolean, equivalency
    """
    return self.rule==other.rule and self.params==other.params

  def __ne__(self,other):
    """Checks inequivalency of quad set
    @ In , other, object , object to compare to
    @ Out, boolean, inequivalency
    """
    return not self.__eq__(other)

  def initialize(self,distr):
    '''Initializes specific settings for quadratures.  Must be overwritten.
    @ In distr, Distribution object, distro represented by this quad
    @ Out, None, None
    '''
    pass

  def quadRule(self,i):
    '''Quadrature rule to use for order.  Defaults to Gauss, CC should set its own.
    @ In i, int, quadrature level
    @ Out, int, quadrature order
    '''
    return GaussQuadRule(i)


class Legendre(QuadratureSet):
  def initialize(self,distr):
    self.rule   = quads.p_roots
    self.params = []
    self.pointRule = GaussQuadRule

class Hermite(QuadratureSet):
  def initialize(self,distr):
    self.rule   = quads.he_roots
    self.params = []
    self.pointRule = GaussQuadRule

class Laguerre(QuadratureSet):
  def initialize(self,distr):
    self.rule   = quads.la_roots
    self.pointRule = GaussQuadRule
    if distr.type=='Gamma':
      self.params=[distr.alpha-1]
    else:
      raise IOError('No implementation for Laguerre quadrature on '+distr.type+' distribution!')

class Jacobi(QuadratureSet):
  def initialize(self,distr):
    self.rule   = quads.j_roots
    self.pointRule = GaussQuadRule
    if distr.type=='Beta':
      self.params=[distr.beta-1,distr.alpha-1]
    #NOTE this looks totally backward, BUT it is right!
    #The Jacobi measure switches the exponent naming convention
    #for Beta distribution, it's  x^(alpha-1) * (1-x)^(beta-1)
    #for Jacobi measure, it's (1+x)^alpha * (1-x)^beta
    else:
      raise IOError('No implementation for Jacobi quadrature on '+distr.type+' distribution!')

class ClenshawCurtis(QuadratureSet):
  def initialize(self,distr):
    self.rule = self.cc_roots
    self.params = []
    self.quadRule = CCQuadRule

  def cc_roots(self,o):
    '''Computes Clenshaw Curtis nodes and weights for given order n=2^o+1
    @ In o,int,level of quadrature to obtain
    @ Out, tuple(tuple(float),float), points and weights
    '''
    #TODO FIXME a depreciation warning is being thrown in this prodedure
    n1=o
    if o==1:
      return np.array([np.array([0]),np.array([2])])
    else:
      n = n1-1
      C = np.zeros((n1,2))
      k = 2*(1+np.arange(np.floor(n/2)))
      C[::2,0] = 2/np.hstack((1,1-k*k))
      C[1,1]=-n
      V = np.vstack((C,np.flipud(C[1:n,:])))
      F = np.real(ifft(V,n=None,axis=0))
      x = F[0:n1,1]
      w = np.hstack((F[0,0],2*F[1:n,0],F[n,0]))
    return x,w


class CDFLegendre(Legendre): #added just for name distinguish; equiv to Legendre
  pass

class CDFClenshawCurtis(ClenshawCurtis): #added just for name distinguish; equiv to ClenshawCurtis
  pass


def CCQuadRule(i):
  '''In order to get nested points, we need 2**i on Clenshaw-Curtis points instead of just i.
     For example, i=2 is not nested in i==1, but i==2**2 is.
  @ In i,int,level desired
  @ Out, int,desired quad order
  '''
  try: return np.array(list((0 if p==0 else 2**p) for p in i))
  except TypeError: return 0 if i==0 else 2**i


def GaussQuadRule(i):
  '''We need no modification for Gauss rules, as we don't expect them to be nested.
  @ In i,int,level desired
  @ Out, int,desired quad order
  '''
  return i


'''
 Interface Dictionary (factory) (private)
'''
__base = 'QuadratureSet'
__interFaceDict = {}
__interFaceDict['Legendre'] = Legendre
__interFaceDict['CDFLegendre'] = CDFLegendre
__interFaceDict['CDFClenshawCurtis'] = CDFClenshawCurtis
__interFaceDict['Hermite'] = Hermite
__interFaceDict['Laguerre'] = Laguerre
__interFaceDict['Jacobi'] = Jacobi
__interFaceDict['ClenshawCurtis'] = ClenshawCurtis
__knownTypes = __interFaceDict.keys()

def knownTypes():
  return __knownTypes

def returnInstance(Type,**kwargs):
  '''
    function used to generate a Filter class
    @ In, Type : Filter type
    @ Out,Instance of the Specialized Filter class
  '''
  # some modification necessary to distinguish CDF on Legendre versus CDF on ClenshawCurtis
  if Type=='CDF':
    if   kwargs['Subtype']=='Legendre'      : return __interFaceDict['CDFLegendre']()
    elif kwargs['Subtype']=='ClenshawCurtis': return __interFaceDict['CDFClenshawCurtis']()
  if Type in knownTypes(): return __interFaceDict[Type]()
  else: raise NameError('not known '+__base+' type '+Type)

