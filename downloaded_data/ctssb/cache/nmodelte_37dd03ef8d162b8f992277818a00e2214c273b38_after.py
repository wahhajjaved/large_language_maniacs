usage="""written to add / remove modes from a network"""

import numpy as np
import nmode_state as nm_s
import mode_selection as ms
import networks
from collections import defaultdict

####################################################################################################
#
#
# basic functions to separate modes based on a single number
#
#
####################################################################################################
def less_than(thr, x):
  """
  returns a list of modeNos with x[modeNo] <= thr
  """ 
  keys = []
  for key, val in x.items():
    if val <= thr:
      keys.append( key )

  return sorted(keys)

###
def greater_than(thr, x):
  """
  returns a list of keys with x[key] >= thr
  """
  keys = []
  for key, val in x.items():
    if val >= thr:
      keys.append( key )
  return sorted(keys)

###
def greater_less_than(thr, x):
  """
  returns 2 lists of keys: x[key]>=thr, x[key]<thr
  returns g, l
  """
  g = []
  l = []
  for key, val in x.items():
    if val >= thr:
      g.append( key )
    else:
      l.append( key )
  return sorted(g), sorted(l)

####################################################################################################
#
#
# methods that associate a single number with each triple
#
#
####################################################################################################
def Ethr(system, freqs=None, triples=None):
  """ 
  returns a dictionary
    key, value = triple, Ethr
  """
  if not freqs:
    freqs = system.compute_3mode_freqs()
  if not triples:
    triples = system.network.to_triples()

  Ethrs = {}
  for triple in triples:
    modeo, modei, modej, k = triple
    modeNoo = system.network.modeNoD[modeo.get_nlms()]
    Ethrs[triple] = ms.compute_Ethr(freqs[modeNoo], modei.w, modej.w, modei.y, modej.y, k)

  return Ethrs

def heuristic(system, freqs=None, triples=None):
  """ 
  returns a dictionary
    key, value = triple, heuristic
  """
  if not freqs:
    freqs = system.compute_3mode_freqs()
  if not triples:
    triples = system.network.to_triples()

  heuristics = {}
  for triple in triples:
    modeo, modei, modej, k = triple
    modeNoo = system.network.modeNoD[modeo.get_nlms()]
    heuristics[triple] = ms.compute_heuristic(freqs[modeNoo], modei.w, modej.w, modei.y, modej.y)

  return heuristics

####################################################################################################
#
#
# methods that associate a single number with each mode
#
#
####################################################################################################
def Alast(q, mode_nums=None):
  """
  returns a dictionary with key, value = modeNo, A[-1]
  """
  if not mode_nums:
    mode_nums = range(len(q))

  return dict( (modeNo, sum([l**2 for l in q[modeNo][-1]])**0.5) for modeNo in mode_nums )

#########################
def Elast(q, mode_nums=None):
  """
  returns a dictionary with key, value = modeNo, E[-1]
  """
  if not mode_nums:
    mode_nums = range(len(q))

  return dict( (modeNo, sum([l**2 for l in q[modeNo][-1]])) for modeNo in mode_nums )

#########################
def Ameanvar(q, mode_nums=None):
  """
  returns 2 dictionaries:
    key, value = modeNo, mean{A}
    key, value = modeNo, stdv{A}
  """
  if not mode_nums:
    mode_nums = range(len(q))

  A = nm_s.compute_A(q)
  n = len(A[0])
  Am = [1.0*sum(Ai)/n for Ai in A]
  As = [(1.0*sum((Ai-Aim)**2)/(n-1))**0.5 for Ai, Aim in zip(A, Am)]

  return dict( (modeNo, Am[modeNo]) for modeNo in mode_nums ), dict( (modeNo, As[modeNo]) for modeNo in num_modes )

#########################
def Emeanvar(q, mode_nums=None):
  """
  returns 2 dictionaries:
    key, value = modeNo, mean{E}
    key, value = modeNo, stdv{E}
  """
  if not mode_nums:
    mode_nums = range(len(q))

  E = nm_s.compute_E(q)
  n = len(E[0])
  Em = [1.0*sum(Ei)/n for Ei in E]
  Es = [(1.0*sum((Ei-Eim)**2)/(n-1))**0.5 for Ei, Eim in zip(E, Em)]

  return dict( (modeNo, Em[modeNo]) for modeNo in mode_nums ), dict( (modeNo, Es[modeNo]) for modeNo in mode_nums )

#########################
def AfitYfit(q, t_P=None, mode_nums=None):
  """
  returns 3 dictionaries:
    key, value = modeNo, Afit
    key, value = modeNo, yfit
    key, value = modeNo, chi2_red
  """
  if not t_P:
    t_P = range(len(q[0]))
  if not mode_nums:
    mode_nums = range(len(q))

  Af, yf, chi2_red = nm_s.A_exp_fit(t_P, q)

  return dict( (modeNo, Af[modeNo]) for modeNo in mode_nums ), dict( (modeNo, yf[modeNo]) for modeNo in mode_nums ), dict( (modeNo, chi2_red[modeNo]) for modeNo in mode_nums )

#########################
def num_k(network, mode_nums=None):
  """
  returns a dictionary:
    key, value = modeNo, len(network.K[modeNo])
  """
  if not mode_nums:
    mode_nums = range(len(network))

  return dict( (modeNo, len(network.K[modeNo])) for modeNo in mode_nums )

#########################
def min_Ethr(system, mode_nums=None, freqs=None):
  """
  returns a dictionary
    key, value = modeNo, min{Ethr}
  """
  if not mode_nums:
    mode_nums = range(len(system.network))

  min_Ethr = dict( (modeNo, np.infty) for modeNo in mode_nums )
  for triple, E in Ethr(system, freqs=freqs).items():
    for mode in triple[:3]:
      modeNo = system.network.modeNoD[mode.get_nlms()]
      if not min_Ethr.has_key(modeNo): print "couldn't find modeNo"
      if min_Ethr.has_key(modeNo) and (min_Ethr[modeNo] > E):
        min_Ethr[modeNo] = E

  return min_Ethr

#########################
def min_heuristic(system, mode_nums=None, freqs=None):
  """
  returns a dictionary
    key, value = modeNo, min{heuristic}
  """
  if not mode_nums:
    mode_nums = range(len(system.network))

  min_h = dict( (modeNo, np.infty) for modeNo in mode_nums )
  for triple, h in heuristic(system, freqs=freqs).items():
    for mode in triple[:3]:
      modeNo = system.network.modeNoD[mode.get_nlms()]
      if min_h.has_key(modeNo) and (min_h[modeNo] > h):
        min_h[modeNo] = h

  return min_h

#########################
def min_collE(system, freqs=None, mode_nums=None):
  """
  returns a dictionary
    key, value = modeNo, min{collE}
  """
  if not freqs:
    freqs = system.compute_3mode_freqs()
  if not mode_nums:
    mode_nums = range(len(system.network))

  modes = defaultdict( list )
  for triple, E in Ethr(system, freqs=freqs).items():
    w = [(abs(mode.w), ind) for ind, mode in enumerate(triple[:3])]    
    w.sort(key=lambda l:l[0], reverse=True)
    for mode in [triple[ind] for _,ind in w[1:]]: ## last 2 modes are children
      modes[system.network.modeNoD[mode.get_nlms()]].append( E )

  collE = {}
  for modeNo in mode_nums:
    if modes.has_key( modeNo ):
      collE[modeNo] = ms.compute_collE( sorted(modes[modeNo]) )
    else: 
      collE[modeNo] = ms.compute_collE( [] )

  return collE
    
#########################
def freqs_maxPSD(freq, fq, network, Oorb=False, mode_nums=None):
  """
  selects modes using the frequency data (freq, fq) and returns a list of modes

  modes = [(f, (n,l,m,w,y,U)), ...]

  if Oorb, we assume that freq contains (O/Oorb) data, and we convert it back to O [rad/sec] by multiplying by Oorb
  """
  if not mode_nums:
    mode_nums = range(len(network))

  maxs, mins = nm_s.find_freq_peaks(freq, fq, delta=0, __sort=True)

  modes = {}
  for modeNo in mode_nums:
    fit = maxs[modeNo]
    if len(fit) == 0:
      raise StandardError, "No frequency peak detected for modeNo=%d" % modeNo
    f,_ = fit[0]

    if Oorb:
      f = f*Oorb

    if (min_w <= f) and (f <= max_w):
      modes[modeNo] = f

  return modes

#########################
def freqs_lorentzian(freq, fq, network, Oorb=False, rtol=1e-8, max_iters=100, bw=0, n_lowpass=False, mode_nums=None):
  """
  selects modes using the frequency data (freq, fq) and returns a list of modes

  modes = [(f, (n,l,m,w,y,U)), ...]

  if Oorb, we assume that freq contains (O/Oorb) data, and we convert it back to O [rad/sec] by multiplying by Oorb
  """
  if not mode_nums:
    mode_nums = range(len(network))

  fit_params, fit_params_covar = nm_s.fit_peaks_lorentzian(freq, fq, max_iters=50, verbose=True)

  modes = {}
  for modeNo in mode_nums:
    fit = fit_params[modeNo]
    if len(fit) == 0:
      raise StandardError, "No frequency peak detected for modeNo=%d" % modeNo
    f,_,_ = fit[0]

    if Oorb:
      f = f*Oorb

    if (min_w <= f) and (f <= max_w):
      modes[modeNo] = f

  return modes

####################################################################################################
#
#
# methods that filter mode_nums by various statistics
#
#
####################################################################################################
def within_bandwidth_analytic(min_w, max_w, system, mode_nums=False):
  """
  computes the expected frequencies assuming 3mode equilibrium solutions

  uses family-tree generation functions defined within networks.network object
  """
  if not mode_nums:
    mode_nums = range(len(system.network))

  freqs = system.compute_3mode_freqs()
  freqs = dict( (modeNo, freqs[modeNo]) for modeNo in mode_nums )

  return [ (freqs[modeNo], system.network.modes[modeNo]) for modeNo in  less_than(max_w, dict( (modeNo, freqs[modeNo]) for modeNo in greater_than(min_w, freqs)) ) ]
  
##################################################
def within_bandwidth_maxPSD(freq, fq, min_w, max_w, network, Oorb=False, mode_nums=None):
  """
  selects modes using the frequency data (freq, fq) and returns a list of modes

  modes = [(f, (n,l,m,w,y,U)), ...]

  if Oorb, we assume that freq contains (O/Oorb) data, and we convert it back to O [rad/sec] by multiplying by Oorb
  """
  if not mode_nums:
    mode_nums = range(len(network))

  freqs = freqs_maxPSD(freq, fq, network, Oorb=Oorb, mode_nums=mode_nums)

  return [ (freqs[modeNo], system.network.modes[modeNo]) for modeNo in  less_than(max_w, dict( (modeNo, freqs[modeNo]) for modeNo in greater_than(min_w, freqs)) ) ]

##################################################
def within_bandwidth_lorentzian(freq, fq, min_w, max_w, network, Oorb=False, rtol=1e-8, max_iters=100, bw=0, n_lowpass=False, mode_nums=None):
  """
  selects modes using the frequency data (freq, fq) and returns a list of modes

  modes = [(f, (n,l,m,w,y,U)), ...]

  if Oorb, we assume that freq contains (O/Oorb) data, and we convert it back to O [rad/sec] by multiplying by Oorb
  """
  if not mode_nums:
    mode_nums = range(len(network))

  freqs = freqs_lorentzian(freq, fq, network, Oorb=Oorb, rtol=rtol, max_iters=max_iters, bw=bw, n_lowpass=n_lowpass, mode_nums=mode_nums)

  return [ (freqs[modeNo], system.network.modes[modeNo]) for modeNo in  less_than(max_w, dict( (modeNo, freqs[modeNo]) for modeNo in greater_than(min_w, freqs)) ) ]

##################################################
def __downselect(thrs, x, network):
  """ helper function for downselect methods """

  keeps = []
  removes = []
  for thr in thrs:
    g, l = greater_less_than(thr, x)
    keeps.append( [network.modes[modeNo].get_nlms() for modeNo in g] )
    removes.append( [network.modes[modeNo].get_nlms() for modeNo in l] )

  return keeps, removes

##################################################
def downselect_Alast(q, Athr, network, mode_nums=None):
  """
  applies an amplitude cut on all modes listed in q using the last Ai in q.
  return two lists:
    Alast > Athr
    Alast < Athr
  lists are (n,l,m,s)
  """
  if isinstance(Athr, (int,float)):
    Athr = [Athr]
    single = True

  keeps, removes = __downselect(Athr, Alast(q, mode_nums=mode_nums), network)

  if single:
    return keeps[0], removes[0]
  else:
   return keeps, removes

##################################################
def downselect_Amean(q, Athr, network, mode_nums=None):
  """
  applies an amplitude cut on all modes listed in q using <Ai>.
  returns two lists: 
    Amean > Athr
    Amean < Athr
  lists are (n,l,m,s)
  """
  if isinstance(Athr, (int,float)):
    Athr = [Athr]
    single = True

  keeps, removes = __downselect(Athr, Amean(q, mode_nums=mode_nums), network)

  if single:
    return keeps[0], removes[0]
  else:
    return keeps, removes

##################################################
def downselect_Afit(q, Athr, network, t_P=None, mode_nums=None):
  """
  applies an amplituded cut using the fit amplitude at t_P[-1] assuming an exponential decay
    also requires the fit decay constant to be less than zero (decay, not growth)

  if not t_P:
    we compute an evenly spaced time series with the length of A. This should only introduce a constant prefactor in the computation of 'yfit', but shouldn't change the decision about whether to keep a mode.

  returns two lists:
    (Afit > Athr) or (Afit < Athr and yfit > 0)
    (Afit < Athr) and (yfit < 0)

  lists are (n,l,m,s)
  """
  if isinstance(Athr, (int,float)):
    Athr = [Athr]
    single = True

  ### don't use __downselect() because this is a special case
  _Afit, _yfit, _chi2_red = AfitYfit(q, t_P=t_P, mode_nums=mode_nums)
  keeps = []
  removes = []
  for athr in Athr:
    g, l = greater_less_than(athr, _Afit)
    keep = [network.modes[modeNo].get_nlms() for modeNo in g]
    g, l = greater_less_than(0.0, dict( (modeNo, _yfit[modeNo]) for modeNo in l ) )
    keeps.append( keep + [network.modes[modeNo].get_nlms() for modeNo in g] )
    removes.append( [network.modes[modeNo].get_nlms() for modeNo in l] )    

  if single:
    return keeps[0], removes[0]
  else:
    return keeps, removes

##################################################
def downselect_num_k(thr, network, mode_nums=None):
  """
  applies a threshold to the number of couplings in the network.
  returns two lists:
    num_k > thr
    num_k < thr

  lists are (n,l,m,s)
  """
  if isinstance(thr, (int,float)):
    thr = [thr]
    single = True


  keeps, removes = __downselect(thr, num_k(network, mode_nums=mode_nums), network)
  
  if single:
    return keeps[0], removes[0]
  else:
    return keeps, removes

##################################################
def downselect_min_heuristic(thr, system, freqs=None, mode_nums=None):
  """
  applies a threshold to min{h}
  returns two lists:
    min{h} > thr
    min{h} < thr

  lists are (n,l,m,s)
  """
  if isinstance(thr, (int, float)):
    thr = [thr]
    single = True

  keeps, removes = __downselect(thr, min_heuristic(system, freqs=freqs, mode_nums=mode_nums), network)

  if single:
    return keeps[0], removes[0]
  else:
    return keeps, removes

##################################################
def downselect_min_Ethr(thr, system, freqs=None, mode_nums=None):
  """
  applies a threshold to min{Ethr}
  returns two lists:
    min{Ethr} > thr
    min{Ethr} < thr

  lists are (n,l,m,s)
  """
  if isinstance(thr, (int, float)):
    thr = [thr]
    single = True

  keeps, removes = __downselect(thr, min_Ethr(system, freqs=freqs, mode_nums=mode_nums), network)

  if single:
    return keeps[0], removes[0]
  else:
    return keeps, removes

##################################################
def downselect_collE(thr, system, freqs=None, mode_nums=None):
  """
  applies a threshold to collE
  returns two lists:
    collE > thr
    collE < thr

  lists are (n,l,m,s)
  """
  if isninstance(thr, (int,float)):
    thr = [thr]
    single = True

  keeps, removes = __downselect(thr, min_collE(system, freqs=None, mode_nums=None), network)

  if single:
    return keeps[0], removes[0]
  else:
    return keeps, removes

