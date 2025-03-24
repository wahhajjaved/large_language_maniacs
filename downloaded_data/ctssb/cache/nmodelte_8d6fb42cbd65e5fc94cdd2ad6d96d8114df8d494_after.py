usage="""
provides general utility functions for nmode scripts
"""

import pickle, sys, pygsl
import numpy as np
from pygsl import fft

#from mode_selection import compute_wo

####################################################################################################
#
#
#                 useful numerical constants
#
#
####################################################################################################
### SI units
SI_G = 6.67e-11 # m^3 kg^-1 s^-2
SI_Msun = 1.9891e30 # kg
SI_Rsun = 6.955e8 # m
SI_Mjup = 1.898e27 # kg

SI_units = {"mass":"kg", "length":"m", "time":"s", "frequency":"Hz", "energy":"J"}

### CGS units
CGS_G = SI_G * (1e2)**2 * (1e3)**-1 # cm^3 g^-1 s^-2
CGS_Msun = SI_Msun * 1e3 # g
CGS_Rsun = SI_Rsun * 1e2 # cm
CGS_Mjup = SI_Mjup * 1e3 # g

CGS_units = {"mass":"g", "length":"cm", "time":"s", "frequency":"Hz", "energy":"erg"}

##################################################
def set_units(system="SI"):
  """
  sets up the system of units. default is SI
  known systems are : SI
                      CGS
  """

  global G
  global Msun
  global Rsun
  global Mjup 
  global units
  global unit_system 

  if system == "SI":
    G = SI_G
    Msun = SI_Msun
    Mjup = SI_Mjup
    Rsun = SI_Rsun
    units = SI_units
    unit_system = system
  elif system == "CGS":
    G = CGS_G
    Msun = CGS_Msun
    Mjup = CGS_Mjup
    Rsun = CGS_Rsun
    units = CGS_units
    unit_system = system
  else:
    sys.exit("unknown system of units: %s" % system)

  return unit_system

##################################################
def convert_time(x, unit1, unit2):
  """
  converts the length 'x' from unit1 -> unit2
  known times are : s
                    min
                    hour
                    day
                    week
                    year
  """
  if unit1 == unit2: return x
  known_times = {"s":1., "min":1./60., "hour":1./3600., "day":1./86400., "week":1./(7*86400.), "year":1./(365*86400.)}
  if not known_times.has_key(unit1):
    raise ValueError("unkown time unit: %s" % unit1)
  if not known_times.has_key(unit2):
    raise ValueError("unkown time unit: %s" % unit2)
  
  return x * known_times[unit2]/known_times[unit1]

##################################################
def convert_length(x, unit1, unit2):
  """ 
  converts the length 'x' from unit1 -> unit2 
  known lengths are : m
                      cm
                      AU
                      Rsun
                      pc (parsec)
  """
  if unit1 == unit2: return x
  known_lengths = {"m":1., "cm":100., "AU":1/149597870700., "Rsun":1./SI_Rsun, "pc":1./(3.08567758*10**16)} # known length units in meters
  if not known_lengths.has_key(unit1):
    raise ValueError("unknown length unit: %s" % unit1)
  if not known_lengths.has_key(unit2):
    raise ValueError("unknown length unit: %s" % unit2)

  return x * known_lengths[unit2]/known_lengths[unit1]

##################################################
def convert_mass(x, unit1, unit2):
  """ 
  converts the mass 'x' from unit1 -> unit2 
  known mass units are : kg
                         g
                         Msun
                         Mjup
  """
  if unit1 == unit2: return x
  known_masses = {"kg":1., "g":1000., "Msun":1./SI_Msun, "Mjup":1./SI_Mjup} # known masses in units of kg
  if not known_masses.has_key(unit1):
    raise ValueError("unknown mass unit: %s" % unit1)
  if not known_masses.has_key(unit2):
    raise ValueError("unknown mass unit: %s" % unit2)

  return x * known_masses[unit2]/known_masses[unit1]

##################################################
def convert_energy(x, unit1, unit2):
  """ 
  converts the energy 'x' from unit1 -> unit2 
  known energy units are : J
                           erg
  """
  if unit1 == unit2: return x
  known_energies = {"J":1., "erg":convert_mass(1., "kg", "g")*(convert_length(1., "m", "cm")**2)} # known energies in units of J
  if not known_energies.has_key(unit1):
    raise ValueError("unkown energy unit: %s" % unit1)
  if not known_energies.has_key(unit2):
    raise ValueError("unkown energy unit: %s" % unit2)

  return x * known_energies[unit2]/known_energies[unit1]

##################################################
### call set_units to establish default units
set_units()

####################################################################################################
#
#
#                       Orbital parameters
#
#
###################################################################################################
def Eorb(system):
  """
  computes the orbital energy in the current system of units
  """
  Mprim = Msun*system.Mprim
  Mcomp = Mjup*system.Mcomp
  mu = Mprim*Mcomp/(Mprim+Mcomp)
  Mtot = Mprim + Mcomp
  return -(1./2) * G * Mtot * mu * (G*Mtot/(4*np.pi**2) * system.Porb**2 )**(-1./3) , units['energy']

##################################################
def aorb(system):
  """
  computes the orbital semi-major axis in the current system of units
  """
  Mprim = Msun*system.Mprim
  Mcomp = Mjup*system.Mcomp
  Mtot = Mprim + Mcomp
  return ( (G*Mtot) / (4*np.pi**2) )**(1./3) * system.Porb**(2./3), units['length']

##################################################
def Lorb(system):
  """
  computes the orbital angular momentum in the current system of units
  """
  Mprim = Msun*system.Mprim
  Mcomp = Mjup*system.Mcomp
  mu = Mprim*Mcomp/(Mprim+Mcomp)
  Mtot = Mprim + Mcomp
  return (G*Mtot)**(2./3) * mu * (system.Porb/(2*np.pi))**(1./3) * (1-system.eccentricity**2)**0.5, "%s^2%s/%s" % (units['length'], units['mass'], units['time'])

####################################################################################################
#
#
#                                normalization for mode amplitudes
#
#
####################################################################################################
def Eo(system):
  """
  computes the energy which corresponds to mode amplitude of unity.
  """
  Mprim = system.Mprim*Msun
  Rprim = system.Rprim*Rsun
  return G * Mprim**2 / Rprim, units['energy']

####################################################################################################
#
#
#                     loading and writing functions
#
#
####################################################################################################
def load_out_f(filename):
  """ 
  load in the output fo nmode_f.py and puts it into a standar structure
  this method delegates to numpy.loadtxt() and therefore reads in ALL the data, but it might be faster than load_out()
  """
  data = np.loadtxt(filename).transpose()
  t_P = list(data[0])
  data = data[1:]
  N_m = len(data)/2
  q = []
  for ind in range(N_m):
    q.append( zip(data[2*ind], data[2*ind+1]) )

  return t_P, q, N_m

##################################################  
def load_out(filename, tmin=False, tmax=False, downsample=False):
  """ loads in the output of nmode_f.py and puts it into a standard structure """
  f = open(filename, 'r')

  # find out how many modes there are
  for line in f:
    if line[0] != '#':
      line = [ l for l in line.strip().split()]
      N_m = (len(line) - 1) /2 # number of modes
      break
  else:
    return [], [], 0
  f.close

  f = open(filename, 'r')
  # pull data
  t_P = [] # time divided by number of orbital periods
  q = [[] for n in range(N_m)] # real and imaginary parts of the mode amplitudes
  line_num = 0
  for line in f:
    if line[0] != '#':
      line = line.strip().split()
      if len(line) == 1+2*N_m:
        line = [float(l) for l in line]
        if (tmin) and (line[0] < tmin): # too early, so we skip it
          continue
        elif (tmax) and (line[0] > tmax): # too late, so we end the iteration
          break
        else:
          if (not downsample) or (line_num%downsample == 0): # downsample when reading in data 
            t_P.append(line[0])
            for n in range(N_m):
              q[n].append([line[2*n+1], line[2*n+2]]) # store real and imaginary parts of each mode
          line_num += 1
  f.close()

  return t_P, q, N_m

##################################################
def load_log(filename, enforce_float=False):
  """
  loads system from pickled file
  """
  import networks
  import gmodes, pmodes
  from mode_selection import compute_wo

  network = networks.network()

  f=open(filename,'r')

  Porb = pickle.load(f)
  eccentricity = pickle.load(f)
  Mprim = pickle.load(f)
  Mcomp = pickle.load(f)
  Rprim = pickle.load(f)

  wo = compute_wo(Mprim, Rprim)

  for mode_tuple, mode_type in pickle.load(f):
    if mode_type == "generic":
      mode = networks.mode().from_tuple(mode_tuple)
    elif mode_type == "gmode":
      mode = gmodes.gmode().from_tuple(mode_tuple, wo=wo)
    elif mode_type == "pmode":
      mode = pmodes.pmode().from_tuple(mode_tuple)
    else:
      sys.exit("unknown mode_type : %s" % mode_type)
    network.modes.append( mode )

  network.K = pickle.load(f)
  if enforce_float:
    network.K = [ [(i,j,float(k)) for i,j,k in coup] for coup in network.K ]
  network._update()

  f.close()

  system = networks.system(Mprim, Mcomp, Rprim, Porb, eccentricity, net=network)

  return system

##################################################
def write_log(filename, system, enforce_float=False):
  """
  writes system into pickled file
  """
  f=open(filename, "w")

  pickle.dump(system.Porb, f)
  pickle.dump(system.eccentricity, f)
  pickle.dump(system.Mprim, f)
  pickle.dump(system.Mcomp, f)
  pickle.dump(system.Rprim, f)

  pickle.dump([(m.into_tuple(), m.mode_type) for m in system.network.modes], f)
  if enforce_float:
    system.network.K = [ [(i,j,float(k)) for i,j,k in coup] for coup in system.network.K]
  pickle.dump(system.network.K, f)

  f.close()
  return True

##################################################
def load_ste(filename):
  """
  loads pickled output from nmode_s.py
  """
  stefile = open(filename, "r")
  sdata = pickle.load(stefile)
  mdata = pickle.load(stefile)
  stefile.close()

  return sdata, mdata

##################################################
def merge_ste(filenames, verbose=False):
  """
  loads the ste data from filenames, 
  checks to make sure time_domain, freq_domain, system agree
  updates sdata, mdata in order of filenames
  """
  sdata = mdata = False
  for filename in filenames:
    if verbose: print "working on ", filename

    _sdata, _mdata = load_ste(filename)
    if not sdata: # first file in the list
      sdata = _sdata
      mdata = _mdata
    elif sdata["system"]["logfilename"] == _sdata["system"]["logfilename"]: # check logfilename

      if _sdata.has_key("time_domain") and sdata.has_key("time_domain"):
        for key in sdata["time_domain"].keys(): # compare keys for time_domain match
          if sdata["time_domain"][key] != _sdata["time_domain"][key]:
            raise ValueError("time_domain are in conflict on key : %s" % key)
        else:
          sdata["stats"].update(  _sdata["stats"] ) # update sdata["stats"] with new info

      elif _sdata.has_key("time_domain"): # include new time_domain 
        sdata["time_domain"] = _sdata["time_domain"]
        sdata["stats"].update( _sdata["stats"] ) # update sdata["stats"] with new info
      
      if _sdata.has_key("freq_domain") and sdata.has_key("freq_domain"):
        for key in sdata["freq_domain"].keys():
          if sdata["freq_domain"][key] != _sdata["freq_domain"][key]:
            raise ValueError("freq_domain are in conflict on key: %s" % key)
        else:
          pass

      elif _sdata.has_key("freq_domain"):
        sdata["freq_domain"] = _sdata["freq_domain"]

    else:
      raise ValueError("logfilenames are in conflict in nmode_utils.merge_ste")
    
  return sdata, mdata

####################################################################################################
#
#
#                       utility functions
#
#
####################################################################################################
def report_func(t, q, P=1., phase=False):
  """ builds a string representing the state of the system """
  if phase:
    report = str(t/(2*np.pi)) # convert from phase --> t/P
  else:
    report = str(t/P) # convert from t --> t/P
  for m in range(len(q)):
    report += " "+str(q[m])
  return report

##################################################
def float_to_scientific(x, verbose=False):
  """ the decimal and exponent for scientific notation """
  if x == 0: # special case that will break this notation
    return 0, 0
  try:
    _exp = int(np.floor(np.log10(abs(x))))
    return x*10**(-_exp), _exp
  except:
    if verbose: print "WARNING: something went wrong with float_to_scientific. Defaulting to 0e0"
    return 0, 0

##################################################
def dwn_smpl(x, f=10):
  return [ x[ind] for ind in range(len(x)) if ind%f == 0 ]

##################################################
def phs(x,y):
  """ determines the phase of a complex number (x + 1j*y) """
  if x > 0 and y >= 0:
    phs = np.arctan(y/x)
  elif x < 0 and y >= 0:
    phs = np.arctan(y/x) + np.pi
  elif x < 0 and y < 0:
    phs = np.arctan(y/x) + np.pi
  elif x > 0 and y < 0:
    phs = np.arctan(y/x) + 2*np.pi
  else:
    if y > 0:
      phs = np.pi/2
    else:
      phs = 3*np.pi/2

  return phs

##################################################
def amp(x,y):
  return (x**2 + y**2)**0.5

##################################################
def peakdet(v, delta=0, x=None, n_lowpass=False):
  """
  Returns two arrays: maxtab, mintab

  maxtab = [(xi, vi), ...] # list of local maxima 
  mintab = [(xi, vi), ...] # list of local minima

  a maximum/minimum is defined as a point that is at least `delta' far away from neighboring points
  """
  maxtab = []
  mintab = []

  if n_lowpass:
    v = wavelet_lowpass(v, n=n_lowpass)

  if x is None:
    x = np.arange(len(v))
  v = np.asarray(v)
  if len(v) != len(x):
    sys.exit('Input vectors v and x must have same length')
  if not np.isscalar(delta):
    sys.exit('Input argument delta must be a scalar')
  if delta < 0:
    sys.exit('Input argument delta must be non-negative semi-definite')

  mn, mx = np.Inf, -np.Inf
  mnpos, mxpos = np.NaN, np.NaN
  lookformax = True

  for i in np.arange(len(v)):
    this = v[i]
    if this > mx:
      mx = this
      mxpos = x[i]
    if this < mn:
      mn = this
      mnpos = x[i]

    if lookformax:
      if this < mx-delta:
        maxtab.append((mxpos, mx))
        mn = this
        mnpos = x[i]
        lookformax = False
    else:
      if this > mn+delta:
        mintab.append((mnpos, mn))
        mx = this
        mxpos = x[i]
        lookformax = True

  return maxtab, mintab

##################################################
def nmode_fft(t_P, q, verbose=False):
  """
  defines my fft routine in one location

  frequency spacing checked against the GSL documentation on 5/5/2013
  """
  N_m = len(q)
  freq = fft_freq(t_P) # frequency spacing to match GSL FFT

  fq = []
  for m in range(N_m):
    if verbose: print "computing FFT for mode "+str(m)
    if verbose: print "\tcasting time domain as complex"
    cq = [complex(l[0],l[1]) for l in q[m]]
    if verbose: print "\tcomputing complex FFT"
    cfq = list(fft.complex_forward_float(cq))
    cfq = cfq[len(cfq)/2+1:] + cfq[:len(cfq)/2+1]
    if len(cfq) != len(freq):
      print len(cfq)
      print len(freq)
      print len_t_P
      sys.exit("Something's wrong in Nmode_utils.nmode_fft: len(cfq) != len(freq)")
    if verbose: print "\tappending complex FFT to fq in standard format (list of reals)"
    fq.append( [ [L.real, L.imag] for L in cfq ] )

  return freq, fq, N_m

##################################################
def single_fft(t_P, A, verbose=False):
  """
  performs the fft over the single value A and returns a list of lists of real numbers
  """
  freq = fft_freq(t_P) # frequency spacing to match GSL FFT

  if verbose: print "computing complex FFT"
  cfA = list(fft.complex_forward_float(A))
  cfA = cfA[len(cfA)/2+1:] + cfA[:len(cfA)/2+1]
  if len(cfA) != len(freq):
    print len(cfA)
    print len(freq)
    print len_t_P
    sys.exit("Something's wrong in Nmode_utils.nmode_fft: len(cfq) != len(freq)")
  if verbose: print "\tconverting complex FFT to standard format (list of reals)"
  fA = [ [L.real, L.imag] for L in cfA ]

  return freq, fA

##################################################
def fft_freq(t_P):
  len_t_P = len(t_P)
  fmax = 1/(2*(t_P[-1] - t_P[-2])) # assumes constant spacing in time
  df = 1/(t_P[-1] - t_P[0]) # gets time range
  return np.linspace(-fmax+df, fmax-df*(len_t_P%2), len_t_P) # frequency spacing to match GSL FFT


##################################################
def wavelet_lowpass(x, wavelet="db6", n=1):
  """
  throws out the n-th detail coefficient and reconstructs the series using the wavelet decomposition specified by wavelet
  """
  import pywt

  decomp = [(x,)]
  for ind in range(1,n+1):
    ac, dc = pywt.dwt(decomp[ind-1][0], wavelet)
    decomp.append( (ac, dc) )

  for ind in range(n):
    ac = pywt.idwt(ac, np.zeros((len(decomp[n-ind][1]),)), wavelet, correct_size=True)

  return ac

##################################################
def convert(t_P, q, current, target, system, Porb):
  """ converts from current -> target
  uses values in network and time steps in t_p
  """
  if target == current:
    return t_P, q, target

  network = system.network
  W = [p.w for p in network.modes] # natural frequencies of the modes
  N_m = len(W) # number of modes

  ### compute 3mode frequencies
  if current == "y" or target == "y":
    freqs = dict( [(modeNo, freq) for freq, modeNo in enumerate(system.compute_3mode_freqs())] ) # modeNo:freq

  if current == "x":
    if target == "q": # q = x * e^{-i*W*t)
      for n in range(N_m):
        w = W[n] # pull out only once
        Q = q[n]
        for ind, t_p in enumerate(t_P):
          t = t_p*Porb
          # compute time-dependent values
          cos_wt = np.cos(w*t)
          sin_wt = np.sin(w*t)
          r_q, i_q = Q[ind]

          Q[ind][0] = r_q*cos_wt + i_q*sin_wt
          Q[ind][1] = i_q*cos_wt - r_q*sin_wt

    elif target == "y": # y = x * e^{-i*D*t}
      for n in range(N_m):
        d = W[n] - freqs[n]
        Q = q[n]
        for ind, t_p in enumerate(t_P):
          t = t_p*Porb
          cos_dt = np.cos(d*t)
          sin_dt = np.sin(d*t)
          r_q, i_q = Q[ind]

          Q[ind][0] = r_q*cos_dt + i_q*sin_dt
          Q[ind][1] = i_q*cos_dt - r_q*sin_dt

    else:
      raise ValueError, "target=%s not understood in convert()"%target

  elif current == "q":
    if target == "x": # x = q * e^{i*W*t}
      for n in range(N_m):
        w = W[n]
        Q = q[n]
        for ind, t_p in enumerate(t_P):
          t = t_p*P
          cos_wt = np.cos(w*t)
          sin_wt = np.sin(w*t)
          r_q, i_q = Q[ind]

          Q[ind][0] = r_q*cos_wt - i_q*sin_wt
          Q[ind][1] = r_q*sin_wt + i_q*cos_wt

    elif target == "y": # y = q * e^{i*(W-D)*t}
      for n in range(N_m):
        f = freqs[n]
        Q = q[n]
        for ind, t_p in enumerate(t_P):
          t = t_p*P
          cos_ft = np.cos(f*t)
          sin_ft = np.sin(f*t)
          r_q, i_q = Q[ind]

          Q[ind][0] = r_q*cos_ft - i_q*sin_ft
          Q[ind][1] = i_q*cos_ft + r_q*sin_ft

    else:
      raise ValueError, "target=%s not understood in convert()"%target

  elif current == "y":
    if target == "x": # x = y * e^{i*D*t}
      for n in range(N_m):
        d = W[n] - freqs[n]
        Q = q[n]
        for ind, t_p in enumerate(t_P):
          t = t_p*P
          cos_dt = np.cos(dt)
          sin_dt = np.sin(dt)
          r_q, i_q = Q[ind]

          Q[ind][0] = r_q*cos_dt - i_q*sin_dt
          Q[ind][1] = i_q*cos_dt + r_q*sin_dt

    elif target == "q": # q = y * e^{-i*(W-D)*t}
      for n in range(N_m):
        f = freqs[n]
        Q = q[n]
        for ind, t_p in enumerate(t_P):
          t = t_p*P
          cos_ft = np.cos(f*t)
          sin_ft = np.sin(f*t)
          r_q, i_q = Q[ind]

          Q[ind][0] = r_q*cos_ft + i_q*sin_ft
          Q[ind][1] = i_q*cos_ft - r_q*sin_ft

    else:
      raise ValueError, "target=%s not understood in convert()"%target
  else:
    raise ValueError, "current=%s not understood in convert()"%current

  return t_P, q, target


##################################################
def modeNo_map(n_l_m_s1, n_l_m_s2):
  """
  constructs the mappings: (dictionaries)
    modeNo1 --> modeNo2
    modeNo2 --> modeNo1

  if there is no corresponding mode, the value is set to "none"

  returns modeNo_map12, modeNo_map21
  """
  nlms1D = dict( (nlms, ind) for ind, nlms in enumerate(n_l_m_s1) )
  nlms2D = dict( (nlms, ind) for ind, nlms in enumerate(n_l_m_s2) )

  n_l_m_s_1 = sorted(n_l_m_s1)
  n_l_m_s_2 = sorted(n_l_m_s2)

  N_m_1 = len(n_l_m_s_1)
  N_m_2 = len(n_l_m_s_2)

  modeNo_map12 = {}
  modeNo_map21 = {}
  ind1 = 0
  ind2 = 0
#  nlms1 = n_l_m_s_1[ind1]
#  nlms2 = n_l_m_s_2[ind2]
  while (ind1 < N_m_1) and (ind2 < N_m_2):
    nlms1 = n_l_m_s_1[ind1]
    nlms2 = n_l_m_s_2[ind2]
    if nlms1 == nlms2:
      modeNo_map12[nlms1D[nlms1]] = nlms2D[nlms2]
      modeNo_map21[nlms2D[nlms2]] = nlms1D[nlms1]
      ind1 += 1
      ind2 += 1
    elif nlms1 > nlms2:
      modeNo_map21[nlms2D[nlms2]] = "none"
      ind2 +=1
    else: # nlm1 < nlm2
      modeNo_map12[nlms1D[nlms1]] = "none"
      ind1 += 1 

  while (ind1 < N_m_1):
    modeNo_map12[nlms1D[n_l_m_s_1[ind1]]] = "none"
    ind1 += 1

  while (ind2 < N_m_2):
    modeNo_map21[nlms2D[n_l_m_s_2[ind2]]] = "none"
    ind2 += 1

  return modeNo_map12, modeNo_map21

##################################################
def common_nlms(n_l_m_s1, n_l_m_s2):
  """
  looks for the common modes in both networks. Returns a list of tuples:
    [ ((n,l,m), modeNo1, modeNo2), ...]
  """
  nlm1D = dict( (nlms, ind) for ind, nlms in enumerate(n_l_m_s1) )
  nlm2D = dict( (nlms, ind) for ind, nlms in enumerate(n_l_m_s2) )

  n_l_m_s1 = sorted(n_l_m_s1)
  n_l_m_s2 = sorted(n_l_m_s2)

  N_m_1 = len(n_l_m_s1)
  N_m_2 = len(n_l_m_s2)

  common_modes = []
  ind1 = 0
  ind2 = 0
  nlms1 = n_l_m_s1[ind1]
  nlms2 = n_l_m_s2[ind2]
  while (ind1 < N_m_1) and (ind2 < N_m_2):
    nlms1 = n_l_m_s1[ind1]
    nlms2 = n_l_m_s2[ind2]
    if nlms1 == nlms2:
      common_modes.append( ( nlms1, ind1, ind2 ) )
      ind1 += 1
      ind2 += 1
    elif nlms1 > nlms2:
      ind2 +=1
    else: # nlm1 < nlm2
      ind1 += 1

  return common_modes
