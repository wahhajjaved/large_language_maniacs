"""Algorithms for time series analysis.

Algorithms for analysis of time-series derived from neuroimaging data

1. Coherency: calculate the pairwise correlation between time-series in the
frequency domain and related quantities

2. Spectral estimation: calculate the spectra of time-series and cross-spectra
between time-series

3. Event-related analysis: calculate the correlation between time-series and
external events

The algorithms in this library are the functional form of the algorithms, which
accept as inputs numpy array and produce numpy array outputs. Therfore, they
can be used on any type of data which can be represented in numpy arrays. 

"""

#import packages:
import numpy as np
from scipy import signal 
from scipy import stats
from matplotlib import mlab
from scipy import linalg
import utils as ut

#-----------------------------------------------------------------------------
#  Coherency 
#-----------------------------------------------------------------------------

"""
XXX write a docstring for this part.
"""

def coherency(time_series,csd_method= None):
    r"""
    Compute the coherency between the spectra of n-tuple of time series.
    Input to this function is in the time domain

    Parameters
    ----------
    time_series: n*t float array
       an array of n different time series of length t each

    csd_method: dict, optional

    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    Returns
    -------
    f: float array
    The central frequencies for the frequency
    bands for which the spectra are estimated

    c: n-d array This is a symmetric matrix with the coherencys of the
    signals. The coherency of signal i and signal j is in f[i][j]. Note that
    f[i][j] = f[j][i].conj()

    See also
    --------
    
    :func:`coherency_calculate`
    
    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default
  
    f,fxy = get_spectra(time_series,csd_method)

    #A container for the coherencys, with the size and shape of the expected
    #output:
    c=np.zeros((time_series.shape[0],
               time_series.shape[0],
               f.shape[0]), dtype = complex) #Make sure it's complex
    
    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            c[i][j] = coherency_calculate(fxy[i][j], fxy[i][i], fxy[j][j])  

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric
    
    return f,c 

def coherency_calculate(fxy, fxx, fyy): 
    r"""
    Compute the coherency between the spectra of two time series. 

    Input to this function is in the frequency domain.
    
    Parameters
    ----------
    
    fxy : float array
         The cross-spectrum of the time series 
    
    fyy,fxx : float array
         The spectra of the signals
    
    Returns 
    -------
    
    complex array 
        the frequency-band-dependent coherency

    Notes
    -----
    
    This is an implementation of equation (1) of Sun et al. (2005) [Sun2005]_: 

    .. math::

        R_{xy} (\lambda) = \frac{f_{xy}(\lambda)}
        {\sqrt{f_{xx} (\lambda) \cdot f_{yy}(\lambda)}}

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data. Neuroimage, 28: 227-37.

    See also
    --------
    :func: `coherency`
    """

    return fxy / np.sqrt(fxx*fyy)

def coherence(time_series,csd_method=None):
    r"""Compute the coherence between the spectra of an n-tuple of time_series. 

    Parameters of this function are in the time domain.

    Parameters
    ----------
    time_series: n*t float array
       an array of n different time series of length t each

   time_series: n*t float array
       an array of n different time series of length t each

    csd_method: dict, optional
    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    
    Returns
    -------
    f: float array
    The central frequencies for the frequency
    bands for which the spectra are estimated

    c: n-d array This is a symmetric matrix with the coherencys of the
    signals. The coherency of signal i and signal j is in f[i][j].
    
    Notes
    -----
    
    This is an implementation of equation (2) of Sun et al. (2005) [Sun2005]_:

    .. math::

        Coh_{xy}(\lambda) = |{R_{xy}(\lambda)}|^2 = 
        \frac{|{f_{xy}(\lambda)}|^2}{f_{xx}(\lambda) \cdot f_{yy}(\lambda)}

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data.  Neuroimage, 28: 227-37.

    See also
    --------
    :func:`coherence_calculate`
         
    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    #A container for the coherences, with the size and shape of the expected
    #output:
    c=np.zeros((time_series.shape[0],
               time_series.shape[0],
               f.shape[0]))
    
    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            c[i][j] = coherence_calculate(fxy[i][j], fxy[i][i], fxy[j][j])  

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return f,c 

def coherence_calculate(fxy, fxx, fyy):
    r"""
    Compute the coherence between the spectra of two time series. 

    Parameters of this function are in the frequency domain.

    Parameters
    ----------
    
    fxy : array
         The cross-spectrum of the time series 

    fyy,fxx : array
         The spectra of the signals 
    
    Returns 
    -------
    
    float
        a frequency-band-dependent measure of the linear association between
        the two time series
         
    Notes
    -----
    
    This is an implementation of equation (2) of Sun et al. (2005) [Sun2005]_:

    .. math::

        Coh_{xy}(\lambda) = |{R_{xy}(\lambda)}|^2 = 
        \frac{|{f_{xy}(\lambda)}|^2}{f_{xx}(\lambda) \cdot f_{yy}(\lambda)}

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data.  Neuroimage, 28: 227-37.

    See also
    --------
    :func:`coherence`
         
    """

    c = (np.abs(fxy))**2 / (fxx * fyy)

#    c = ((np.abs(coherency_calculate(fxy,fxx,fyy)))**2)
    return c  

def coherency_regularized(time_series,epsilon,alpha,csd_method=None):
    r"""
    Same as coherence, except regularized in order to overcome numerical
    imprecisions

    Parameters
    ----------
    
    time_series: n-d float array
    The time series data for which the regularized coherence is calculated 

    epsilon: float
    small regularization parameter

    alpha: float
    large regularization parameter

    csd_method: dict, optional
    time_series: n*t float array
       an array of n different time series of length t each

    csd_method: dict, optional
    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    Returns
    -------
    f: float array
    The central frequencies for the frequency
    bands for which the spectra are estimated

    c: n-d array This is a symmetric matrix with the coherencys of the
    signals. The coherency of signal i and signal j is in f[i][j]. Note that
    f[i][j] = f[j][i].conj()


    frequencies, coherence

    Notes
    -----
    The regularization scheme is as follows:

    .. math::
        Coh_{xy}^R = \frac{(\alpha f_{xx} + \epsilon) ^2}
		{\alpha^{2}(f_{xx}+\epsilon)(f_{yy}+\epsilon)}

    See also
    --------
    :func:`coherency_regularized_calculate`

    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    #A container for the coherences, with the size and shape of the expected
    #output:
    c=np.zeros((time_series.shape[0],
               time_series.shape[0],
               f.shape[0]), dtype = complex)  #Make sure it's complex
    
    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            c[i][j] = coherency_reqularized_calculate(fxy[i][j], fxy[i][i],
                                                      fxy[j][j], epsilon, alpha)

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return f,c 

def coherency_reqularized_calculate(fxy, fxx, fyy, epsilon, alpha):

    r"""A regularized version of the calculation of coherency, which is more
    robust to numerical noise than the standard calculation

    Input to this function is in the frequency domain.

    Parameters
    ----------

    fxy, fxx, fyy: float arrays
    The cross- and power-spectral densities of the two signals x and y

    epsilon: float
    First regularization parameter. Should be much smaller than any
    meaningful value of coherence you might encounter

    alpha: float
    Second regularization parameter. Should be much larger than any meaningful
    value of coherence you might encounter (preferably much larger than 1)

    Returns
    -------
    float array
    The coherence values

    Notes
    -----

    The regularization scheme used is as follows:

    .. math::
        Coh_{xy}^R = \frac{(\alpha f_{xx} + \epsilon) ^2}
		{\alpha^{2}(f_{xx}+\epsilon)(f_{yy}+\epsilon)}
    """
    
    return ( ( (alpha*fxy + epsilon) ) /
         np.sqrt( ((alpha**2) * (fxx+epsilon) * (fyy + epsilon) ) ) )

def coherence_regularized(time_series,epsilon,alpha,csd_method=None):
    r"""
    Same as coherence, except regularized in order to overcome numerical
    imprecisions

    Parameters
    ----------
    
    time_series: n-d float array
    The time series data for which the regularized coherence is calculated 

    epsilon: float
    small regularization parameter

    alpha: float
    large regularization parameter

    csd_method: dict, optional
time_series: n*t float array
       an array of n different time series of length t each

    csd_method: dict, optional

    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    Returns
    -------
    f: float array
    The central frequencies for the frequency
    bands for which the spectra are estimated

    c: n-d array This is a symmetric matrix with the coherencys of the
    signals. The coherency of signal i and signal j is in f[i][j].
    
    Returns
    -------
    frequencies, coherence

    Notes
    -----
    The regularization scheme is as follows:

    ..math::
        coherence(x,y) =
        \frac{(alpha*fxx + epsilon) ^2}{alpha^{2}*((fxx+epsilon)*(fyy+epsilon))}
    
    See also
    --------
    :func:`coherence_regularized_calculate`

    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    #A container for the coherences, with the size and shape of the expected
    #output:
    c=np.zeros((time_series.shape[0],
               time_series.shape[0],
               f.shape[0]))
    
    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            c[i][j] = coherence_reqularized_calculate(fxy[i][j], fxy[i][i],
                                                      fxy[j][j], epsilon, alpha)

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return f,c 


def coherence_reqularized_calculate(fxy, fxx, fyy, epsilon, alpha):

    r"""A regularized version of the calculation of coherence, which is more
    robust to numerical noise than the standard calculation. 

    Input to this function is in the frequency domain

    Parameters
    ----------

    fxy, fxx, fyy: float arrays
    The cross- and power-spectral densities of the two signals x and y

    epsilon: float
    First regularization parameter. Should be much smaller than any
    meaningful value of coherence you might encounter

    alpha: float
    Second regularization parameter. Should be much larger than any meaningful
    value of coherence you might encounter (preferably much larger than 1)

    Returns
    -------
    float array
    The coherence values

    Notes
    -----

    The regularization scheme used is as follows:

    ..math::
    
     coherence(x,y) = \frac{(alpha*fxx + epsilon)^2}
                      {alpha^{2}*((fxx+epsilon)*(fyy+epsilon))}

"""
    
    return ( ( (alpha*np.abs(fxy) + epsilon)**2 ) /
         ((alpha**2) * (fxx+epsilon) * (fyy + epsilon) ) )

def coherency_bavg(time_series,lb=0,ub=None,csd_method=None):
    r"""
    Compute the band-averaged coherency between the spectra of two time series. 

    Input to this function is in the time domain.

    Parameters
    ----------
    time_series: n*t float array
       an array of n different time series of length t each

    lb, ub: float, optional
       the upper and lower bound on the frequency band to be used in averaging
       defaults to 1,max(f)

    csd_method: dict, optional

    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    Returns 
    -------
    c: n*n array float array

    This is an upper-diagonal array, where c[i][j] is the band-averaged
    coherency between time_series[i] and time_series[j]
    
    Notes
    -----
    
    This is an implementation of equation (A4) of Sun et al. (2005) [Sun2005]_: 

    .. math::

        \bar{Coh_{xy}} (\bar{\lambda}) =
        \frac{\left|{\sum_\lambda{\hat{f_{xy}}}}\right|^2}
        {\sum_\lambda{\hat{f_{xx}}}\cdot sum_\lambda{\hat{f_{yy}}}} 

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data. Neuroimage, 28: 227-37.

    See also
    --------
    coherency, coherence

    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    lb_idx,ub_idx = ut.get_bounds(f,lb,ub)

    if lb==0:
        lb_idx = 1 #The lowest frequency band should be f0

    c = np.zeros((time_series.shape[0],
               time_series.shape[0]), dtype = complex)
    
    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            c[i][j] = coherency_bavg_calculate(fxy[i][j][lb_idx:ub_idx],
                                               fxy[i][i][lb_idx:ub_idx],
                                               fxy[j][j][lb_idx:ub_idx])

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return c

def coherency_bavg_calculate(fxy, fxx, fyy): 
    r"""
    Compute the band-averaged coherency between the spectra of two time series. 

    Input to this function is in the frequency domain.

    Parameters
    ----------
    
    fxy : float array
         The cross-spectrum of the time series 
    
    fyy,fxx : float array
         The spectra of the signals
    
    See also
    --------
    coherency, coherence

 
    Returns 
    -------
    
    float
        the band-averaged coherency

    Notes
    -----
    
    This is an implementation of equation (A4) of Sun et al. (2005) [Sun2005]_: 

    .. math::

        \bar{Coh_{xy}} (\bar{\lambda}) =
        \frac{\left|{\sum_\lambda{\hat{f_{xy}}}}\right|^2}
        {\sum_\lambda{\hat{f_{xx}}}\cdot sum_\lambda{\hat{f_{yy}}}} 

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data. Neuroimage, 28: 227-37.
    """

    #Average the phases and the magnitudes separately and then
    #recombine:

    p = coherency_phase_spectrum_calculate(fxy) 
    p_bavg = np.mean(p)

    m = np.abs(coherency_calculate(fxy,fxx,fyy))
    m_bavg = np.mean(m)

    return  m_bavg * (np.cos(p_bavg) + np.sin(p_bavg) *1j) #recombine
                                        #according to z = r(cos(phi)+sin(phi)i)

def coherence_bavg (time_series,lb=0,ub=None,csd_method=None):
    r"""
    Compute the band-averaged coherence between the spectra of two time series. 

    Input to this function is in the time domain.

    Parameters
    ----------
    time_series: n*t float array
       an array of n different time series of length t each

    lb, ub: float, optional
       the upper and lower bound on the frequency band to be used in averaging
       defaults to 1,max(f)

    csd_method: dict, optional

    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    Returns 
    -------
    c: n*n array float array

    This is an upper-diagonal array, where c[i][j] is the band-averaged
    coherency between time_series[i] and time_series[j]
    """

    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)
    
    lb_idx,ub_idx = ut.get_bounds(f,lb,ub)

    if lb==0:
        lb_idx = 1 #The lowest frequency band should be f0

    c = np.zeros((time_series.shape[0],
                time_series.shape[0]))
    
    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            c[i][j] = coherence_bavg_calculate(fxy[i][j][lb_idx:ub_idx],
                                               fxy[i][i][lb_idx:ub_idx],
                                               fxy[j][j][lb_idx:ub_idx])

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return c

def coherence_bavg_calculate(fxy, fxx, fyy):
    r"""
    Compute the band-averaged coherency between the spectra of two time series. 
    input to this function is in the frequency domain

    Parameters
    ----------
    
    fxy : float array
         The cross-spectrum of the time series 
    
    fyy,fxx : float array
         The spectra of the signals
    
    See also
    --------
    coherency, coherence

 
    Returns 
    -------
    
    float:
        the band-averaged coherence
    """

    return ( ( np.abs( fxy.sum() )**2 ) /
             ( fxx.sum() * fyy.sum() ) )

def coherence_partial(time_series,r,csd_method=None):
    r"""
    Compute the band-specific partial coherence between the spectra of
    two time series.

    The partial coherence is the part of the coherence between x and
    y, which cannot be attributed to a common cause, r. 
    
    Input to this function is in the time domain.

    Parameters
    ----------

    time_series: n*t float array
       an array of n different time series of length t each
    
    r: the temporal sequence of the common cause, sampled at the same rate as
    time_series

        csd_method: dict, optional

    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'


    Returns 
    -------
    returns the tuple (f,c), where

    f: array, the frequencies
    c: n*n*len(f) array, with the frequency dependent partial coherence between
    time_series i and time_series j in c[i][j] and in c[j][i]
     
        
    See also
    --------
    coherency, coherence 

    Notes
    -----
    
    This is an implementation of equation (2) of Sun et al. (2004) [Sun2004]_: 

    .. math::

        Coh_{xy|r} = \frac{|{R_{xy}(\lambda) - R_{xr}(\lambda)
        R_{ry}(\lambda)}|^2}{(1-|{R_{xr}}|^2)(1-|{R_{ry}}|^2)}

    .. [Sun2004] F.T. Sun and L.M. Miller and M. D'Esposito(2004). Measuring
    interregional functional connectivity using coherence and partial coherence
    analyses of fMRI data Neuroimage, 21: 647-58.
    """
    
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    #Initialize c according to the size of f:
    
    c=np.zeros((time_series.shape[0],
                time_series.shape[0],
                f.shape[0]), dtype = complex)       

    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            f,fxx,frr,frx = get_spectra_bi(time_series[i],r,csd_method)
            f,fyy,frr,fry = get_spectra_bi(time_series[j],r,csd_method)
            coherence_partial_calculate(fxy[i][j],fxy[i][i],fxy[j][j],
                                        frx,fry,frr)

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return f,c

def coherence_partial_calculate(fxy,fxx,fyy,fxr,fry,frr): 
    r"""
    Compute the band-specific partial coherence between the spectra of
    two time series.

    The partial coherence is the part of the coherence between x and
    y, which cannot be attributed to a common cause, r. 
    
    Input to this function is in the frequency domain.

    Parameters
    ----------
    fxy : float array
         The cross-spectrum of the time series 
    
    fyy,fxx : float array
         The spectra of the signals

    fxr,fry : float array
         The cross-spectra of the signals with the event
    
    Returns 
    -------
    float
        the band-averaged coherency

    See also
    --------
    coherency, coherence 

    Notes
    -----
    This is an implementation of equation (2) of Sun et al. (2004) [Sun2004]_: 

    .. math::

        Coh_{xy|r} = \frac{|{R_{xy}(\lambda) - R_{xr}(\lambda)
        R_{ry}(\lambda)}|^2}{(1-|{R_{xr}}|^2)(1-|{R_{ry}}|^2)}

    .. [Sun2004] F.T. Sun and L.M. Miller and M. D'Esposito(2004). Measuring
    interregional functional connectivity using coherence and partial coherence
    analyses of fMRI data Neuroimage, 21: 647-58.
    """
    abs = np.abs
    coh = coherency_calculate
    Rxr = coh(fxr,fxx,frr)
    Rry = coh(fry,fyy,frr)
    Rxy = coh(fxy,fxx,fyy)

    return (( Rxy - (Rxr*Rry) ) /
            np.sqrt( (1-Rxr*Rxr.conjugate()) * (1-Rry*Rry.conjugate()) ) )

def coherence_partial_bavg(x,y,r,csd_method=None,lb=0,ub=None):
    r""" Band-averaged partial coherence
    
    """ 
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    c=np.zeros((time_series.shape[0],
                time_series.shape[0],
                f.shape[0]), dtype = complex)       

    lb_idx,ub_idx = ut.get_bounds(f,lb,ub)

    if lb==0:
        lb_idx = 1 #The lowest frequency band should be f0

    c = np.zeros((time_series.shape[0],
                time_series.shape[0]))

    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            f,fxx,frr,frx = get_spectra_bi(time_series[i],r,csd_method)
            f,fyy,frr,fry = get_spectra_bi(time_series[j],r,csd_method)
            coherence_partial_bavg_calculate(f[lb_idx:ub_idx],
                                        fxy[i][j][lb_idx:ub_idx],
                                        fxy[i][i][lb_idx:ub_idx],
                                        fxy[j][j][lb_idx:ub_idx],
                                        fxr[lb_idx:ub_idx],
                                        fry[lb_idx:ub_idx],
                                        frr[lb_idx:ub_idx])

    idx = ut.tril_indices(time_series.shape[0],-1)
    c[idx[0],idx[1],...] = c[idx[1],idx[0],...].conj() #Make it symmetric

    return c

def coherence_partial_bavg_calculate(f,fxy,fxx,fyy,fxr,fry,frr):
    r"""
    Compute the band-averaged partial coherence between the spectra of
    two time series.
    
    Input to this function is in the frequency domain.

    Parameters
    ----------

    f: the frequencies
    
    fxy : float array
         The cross-spectrum of the time series 
    
    fyy,fxx : float array
         The spectra of the signals

    fxr,fry : float array
         The cross-spectra of the signals with the event
         
    Returns 
    -------
    float
        the band-averaged coherency

    See also
    --------
    coherency, coherence, coherence_partial, coherency_bavg
   
    """
    coh = coherency
    Rxy = coh(fxy,fxx,fyy)
    Rxr = coh(fxr,fxx,frr)
    Rry = coh(fry,fyy,frr)

    return (np.sum(Rxy-Rxr*Rry)/
            np.sqrt(np.sum(1-Rxr*Rxr.conjugate)*np.sum(1-Rry*Rry.conjugate)))

def coherency_phase_spectrum (time_series,csd_method=None):
    """
    Compute the phase spectrum of the cross-spectrum between two time series. 

    The parameters of this function are in the time domain.

    Parameters
    ----------
    
    time_series: n*t float array
    The time series, with t, time, as the last dimension
        
    Returns 
    -------
    
    f: mid frequencies of the bands
    
    p: an array with the pairwise phase spectrum between the time
    series, where p[i][j] is the phase spectrum between time series[i] and
    time_series[j]
    
    Notes
    -----
    
    This is an implementation of equation (3) of Sun et al. (2005) [Sun2005]_:

    .. math::

        \phi(\lambda) = arg [R_{xy} (\lambda)] = arg [f_{xy} (\lambda)]

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data.  Neuroimage, 28: 227-37.
    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default
         
    f,fxy = get_spectra(time_series,csd_method)

    p=np.zeros((time_series.shape[0],
               time_series.shape[0],
               f.shape[0]))
    
    for i in xrange(time_series.shape[0]): 
      for j in xrange(i,time_series.shape[0]):
        p[i][j] = coherency_phase_spectrum_calculate(fxy[i][j])
        p[j][i] = coherency_phase_spectrum_calculate(fxy[i][j].conjugate)
         
    return f,p

def coherency_phase_spectrum_calculate(fxy):
    r"""
    Compute the phase spectrum of the cross-spectrum between two time series. 

    The parameters of this function are in the frequency domain.

    Parameters
    ----------
    
    fxy : float array
         The cross-spectrum of the time series 
        
    Returns 
    -------
    
    float
        a frequency-band-dependent measure of the phase between the two
        time-series 
         
    Notes
    -----
    
    This is an implementation of equation (3) of Sun et al. (2005) [Sun2005]_:

    .. math::

        \phi(\lambda) = arg [R_{xy} (\lambda)] = arg [f_{xy} (\lambda)]

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data.  Neuroimage, 28: 227-37.
    """
    phi = np.angle(fxy)
    
    return phi

def coherency_phase_delay(time_series,lb=0,ub=None,csd_method=None):
    """
    XXX write docstring
    """
    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    lb_idx,ub_idx = ut.get_bounds(f,lb,ub)

    if lb_idx == 0:
        lb_idx = 1
    
    p = np.zeros((time_series.shape[0],time_series.shape[0],
                  f[lb_idx:ub_idx].shape[-1]))

    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            p[i][j] = coherency_phase_delay_calculate(f[lb_idx:ub_idx],
                                                      fxy[i][j][lb_idx:ub_idx])
            p[j][i] = coherency_phase_delay_calculate(f[lb_idx:ub_idx],
                                           fxy[i][j][lb_idx:ub_idx].conjugate())


    return f[lb_idx:ub_idx],p

def coherency_phase_delay_calculate(f,fxy):
    r"""
    Compute the phase delay between the spectra of two signals 

    Parameters
    ----------

    f: float array
         The frequencies 
         
    fxy : float array
         The cross-spectrum of the time series 
    
    Returns 
    -------
    
    float array
        the phase delay (in sec) for each frequency band.
        
    See also
    --------
    coherency, coherence, coherenecy_phase_spectrum_calculate

    Notes
    -----
    """

    phi = coherency_phase_spectrum_calculate(fxy)
    
    t =  (phi)  / (2*np.pi*f)
        
    return t


def coherency_phase_delay_bavg(time_series,lb=0,ub=None,csd_method=None):
    """ XXX write doc string"""

    if csd_method is None:
        csd_method = {'this_method':'mlab'} #The default

    f,fxy = get_spectra(time_series,csd_method)

    lb_idx,ub_idx = ut.get_bounds(f,lb,ub)

    if lb_idx == 0:
        lb_idx = 1
    
    p = np.zeros((time_series.shape[0],time_series.shape[0],
                  f[lb_idx:ub_idx].shape[-1]))

    for i in xrange(time_series.shape[0]): 
        for j in xrange(i,time_series.shape[0]):
            p[i][j] = coherency_phase_delay_bavg_calculate(f[lb_idx:ub_idx],
                                                      fxy[i][j][lb_idx:ub_idx])
            p[j][i] = coherency_phase_delay_bavg_calculate(f[lb_idx:ub_idx],
                                           fxy[i][j][lb_idx:ub_idx].conjugate())

    return p

def coherency_phase_delay_bavg_calculate(f,fxy):
    r"""
    Compute the band-averaged phase delay between the spectra of two signals 

    Parameters
    ----------

    f: float array
         The frequencies 
         
    fxy : float array
         The cross-spectrum of the time series 
    
    Returns 
    -------
    
    float
        the phase delay (in sec)
        
    See also
    --------
    coherency, coherence, coherenecy_phase_spectrum

    Notes
    -----
    
    This is an implementation of equation (8) of Sun et al. (2005) [Sun2005]_: 

    .. math::

    XXX Write down the equation

    .. [Sun2005] F.T. Sun and L.M. Miller and M. D'Esposito(2005). Measuring
        temporal dynamics of functional networks using phase spectrum of fMRI
        data. Neuroimage, 28: 227-37.
   
    """
    return np.mean(coherency_phase_spectrum (fxy)/(2*np.pi*f))
    
#XXX def coherence_partial_phase()

def correlation_spectrum(x1,x2, Fs=2, norm=False):
    """Calculate the spectral decomposition of the correlation

    Parameters
    ----------
    x1,x2: ndarray
    Two arrays to be correlated. Same dimensions

    Fs: float, optional
    Sampling rate in Hz. If provided, an array of
    frequencies will be returned.Defaults to 2

    norm: bool, optional
    When this is true, the spectrum is normalized to sum to 1
    
    Returns
    -------
    ccn: ndarray
    The spectral decomposition of the correlation

    f: ndarray, optional
    ndarray with the frequencies
    
    Notes
    -----
    Equation 15 of Cordes et al (2000) [Cordes2000]_:

    .. math::

    XXX write down the equation

    .. [Cordes2000] D Cordes, V M Haughton, K Arfanakis, G J Wendt, P A Turski,
    C H Moritz, M A Quigley, M E Meyerand (2000). Mapping functionally related
    regions of brain with functional connectivity MR imaging. AJNR American
    journal of neuroradiology 21:1636-44
    
    """

    x1 = x1 - np.mean(x1)
    x2 = x2 - np.mean(x2)
    x1_f = np.fft.fft(x1)
    x2_f = np.fft.fft(x2)
    D = np.sqrt( np.sum(x1**2) * np.sum(x2**2) )
    n = x1.shape[0]

    ccn =( ( np.real(x1_f) * np.real(x2_f) +
             np.imag(x1_f) * np.imag(x2_f) ) /
           (D*n) )

    if norm:
        ccn = ccn / np.sum(ccn) * 2 #Only half of the sum is sent back because
                                    #of the freq domain symmetry. XXX Does
                                    #normalization make this strictly positive? 

    f = get_freqs(Fs,n)
    return f,ccn[0:n/2]

#-----------------------------------------------------------------------------
#Event related analysis
#-----------------------------------------------------------------------------

def fir(timeseries,design):
    """Calculate the FIR (finite impulse response) HRF, according to [Burock2000]_
    
    
    Parameters
    ----------
    
    timeseries : float array
            timeseries data
    
    design : int array
          This is a design matrix.  It has to have shape = (number
          of TRS, number of conditions * length of HRF)
    
          The form of the matrix is: 
            
              A B C ... 
          
          where A is a (number of TRs) x (length of HRF) matrix with a unity
          matrix placed with its top left corner placed in each TR in which
          event of type A occured in the design. B is the equivalent for
          events of type B, etc.
    
    Returns 
    -------

    float array 
        HRF is a numpy array of 1X(length of HRF * number of conditions)
        with the HRFs for the different conditions concatenated.

    Notes
    -----

    Implements equation for in[Burock2000]_:

    .. math::

        \hat{h} = (X^T X)^{-1} X^T y
        
    .. [Burock2000] M.A. Burock and A.M.Dale (2000). Estimation and Detection of
        Event-Related fMRI Signals with Temporally Correlated Noise: A
        Statistically Efficient and Unbiased Approach. Human Brain Mapping,
        11:249-260
         
    """
    X = np.matrix(design)
    y = np.matrix(timeseries)
    h = np.array(linalg.pinv(X.T*X) * X.T*y.T)
    return h   

def event_related(tseries,events,Tbefore, Tafter, Fs=1):
    """
    Calculates the  event related timeseries, using a cross-correlation in the
    frequency domain

    This will return an answer in the units it got (% signal change, z score,
    etc.)

    
    Notes
    -----
    Translated from Matlab code written by Lavi Secundo
    
    """

    fft = np.fft.fft
    ifft = np.fft.ifft
    fftshift = np.fft.fftshift

    E = fftshift ( ifft ( fft(tseries) * fft(np.fliplr([events]) ) ) )
                     
    return E[0][ np.ceil(len(E[0])/2)-Tbefore*Fs :
                    np.ceil(len(E[0])/2)+Tafter*Fs ]

def event_related_zscored(tseries,events,Tbefore, Tafter, Fs=1):
    """
    Calculates the z-scored event related timeseries

    
    Notes
    -----
    Translated from Matlab code written by Lavi Secundo
    
    """

    fft = np.fft.fft
    ifft = np.fft.ifft
    fftshift = np.fft.fftshift

    E = fftshift ( ifft ( fft(tseries) * fft(np.fliplr([events]) ) ) )
    meanSurr = np.mean(E)
    stdSurr = np.std(E)
    
    
    return ( ( (E[0][ np.ceil(len(E[0])/2)-Tbefore*Fs :
                    np.ceil(len(E[0])/2)+Tafter*Fs ])
             - meanSurr)
             / stdSurr )

#-----------------------------------------------------------------------------
# Spectral estimation
#-----------------------------------------------------------------------------
def get_spectra(time_series,method=None):
    r"""
    Compute the spectra of an n-tuple of time series and all of
    the pairwise cross-spectra.

    Parameters
    ----------
    time_series: n*t float array
    The time-series, where t (time) is the last dimension

    method: dict, optional
    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2pi
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that timeseries.algorithms.periodogram
    will be used in order to calculate the psd/csd, in which case, additional
    optional inputs (and default values) are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2pi
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2pi
    sides = 'onesided'

    Returns
    -------
    
    f: float array

    The central frequencies for the frequency bands for which
    the spectra are estimated

    fxy: n-d array

    A semi-filled matrix with the cross-spectra of the signals. The csd of
    signal i and signal j is in f[j][i], but not in f[i][j] (which will be
    filled with zeros). For i=j fxy[i][j] is the psd of signal i.

    See also
    --------

    :func: `periodogram_csd`
    :func: `multi_taper_csd`

    """
    
    if method is None:
        method = {'this_method':'mlab'} #The default
        
    if method['this_method'] == 'mlab':
        NFFT = method.get('NFFT',64)
        Fs = method.get('Fs',2*np.pi)
        detrend = method.get('detrend',mlab.detrend_none)
        window = method.get('window',mlab.window_hanning)
        n_overlap = method.get('n_overlap',int(np.ceil(NFFT/2.0)))

        fxy = np.zeros((time_series.shape[0],
                        time_series.shape[0],
                        NFFT/2.0 +1), dtype = complex) #Make sure it's complex
                                                      
        for i in xrange(time_series.shape[0]): 
            for j in xrange(i,time_series.shape[0]):
                #Notice funny indexing, in order to conform to the conventions
                #of the other methods:
                temp, f = mlab.csd(time_series[j],time_series[i],
                                   NFFT,Fs,detrend,window,n_overlap,
                                   scale_by_freq=True)
                 
                fxy[i][j] = temp.squeeze() #the output of mlab.csd has a wierd
                                            #shape
    else:
        # these methods should work with similar signatures
        mdict = method.copy()
        func = eval(mdict.pop('this_method'))
        freqs, fxy = func(time_series, **mdict)
        f = ut.circle_to_hz(freqs, mdict.get('Fs', 2*np.pi))

    return f,fxy

def get_spectra_bi(x,y,method = None):
    r"""
    Computes the spectra of two timeseries and the cross-spectrum between them

    Parameters
    ----------

    x,y : float arrays
    time series data
    
    method: dict, optional
    contains:
    this_method:'mlab' indicates that mlab's
    psd will be used in order to calculate the psd/csd, in which case,
    additional optional inputs (and default values) are:
    
    NFFT=256
    Fs=2
    detrend=mlab.detrend_none
    window=mlab.window_hanning
    n_overlap=0
    
    this_method:'periodogram_csd' indicates that
    timeseries.algorithms.periodogram will be used in order to calculate the
    psd/csd, in which case, additional optional inputs (and default values)
    are:

    Skx=None
    Sky=None
    N=None
    sides='onesided'
    normalize=True
    Fs=2
    
    this_method:'multi_taper_csd' indicates that
    timeseries.algorithms.multi_taper_psd used in order to calculate psd/csd,
    in which case additional optional inputs (and default values) are:

    BW=0.01
    Fs=2
    sides = 'onesided'
    
    Returns
    -------
    f: float array
        The central frequencies for the frequency
        bands for which the spectra are estimated
    fxx: float array
         The psd of the first signal
    fyy: float array
        The psd of the second signal
    fxy: float array
        The cross-spectral density of the two signals

    See also
    --------
    :func: `periodogram_csd`
    :func: `multi_taper_csd`

    """
    f, fij = get_spectra(np.vstack((x,y)), method=method)
    fxx = fij[0,0].real
    fyy = fij[1,1].real
    fxy = fij[0,1]
    return f, fxx, fyy, fxy


# The following spectrum estimates are normalized to the following convention..
# By definition, Sxx(f) = DTFT{sxx(n)}, where sxx(n) is the autocorrelation
# function of s(n). Therefore the integral from
# [-PI, PI] of Sxx/(2PI) is sxx(0)
# And from the definition of sxx(n), sxx(0) = Expected-Value{s(n)s*(n)},
# which is estimated simply as (s*s.conj()).mean()

def periodogram(s, Sk=None, N=None, sides='onesided', normalize=True):
    """Takes an N-point periodogram estimate of the PSD function. The
    number of points N, or a precomputed FFT Sk may be provided. By default,
    the PSD function returned is normalized so that the integral of the PSD
    is equal to the mean squared amplitude (mean energy) of s (see Notes).

    Parameters
    ----------
    s : ndarray
        Signal(s) for which to estimate the PSD, time dimension in the last axis
    Sk : ndarray (optional)
        Precomputed FFT of s
    N : int (optional)
        Indicates an N-point FFT where N != s.shape[-1]
    sides : str (optional)        
        Indicates whether to return a one-sided or two-sided PSD
    normalize : boolean (optional)
        Normalizes the PSD

    Returns
    -------
    PSD estimate for each row of s

    Notes
    -----
    setting dw = 2*PI/N, then the integral from -PI, PI (or 0,PI) of PSD/(2PI)
    will be nearly equal to sxx(0), where sxx is the autocorrelation function
    of s(n). By definition, sxx(0) = E{s(n)s*(n)} ~ (s*s.conj()).mean()
    """
    if Sk is not None:
        N = Sk.shape[-1]
    else:
        N = s.shape[-1] if not N else N
        Sk = np.fft.fft(s, n=N)
    pshape = list(Sk.shape)
    norm = float(s.shape[-1])
    # if the time series is a complex vector, a one sided PSD is invalid..
    # should we check for that?
    if sides=='onesided':
        # putative Nyquist freq
        Fn = N/2 + 1
        # last duplicate freq
        Fl = (N+1)/2
        pshape[-1] = Fn
        P = np.zeros(pshape, 'd')
        freqs = np.linspace(0, np.pi, Fn)
        P[...,0] = (Sk[...,0]*Sk[...,0].conj())
        P[...,1:Fl] = 2 * (Sk[...,1:Fl]*Sk[...,1:Fl].conj())
        if Fn > Fl:
            P[...,Fn-1] = (Sk[...,Fn-1]*Sk[...,Fn-1].conj())
    else:
        P = (Sk*Sk.conj()).real
        freqs = np.linspace(0, 2*np.pi, N, endpoint=False)
    if normalize:
        P /= norm
    return freqs, P

def periodogram_csd(s, Sk=None, N=None, sides='onesided', normalize=True):
    """Takes an N-point periodogram estimate of all the cross spectral
    density functions between rows of s.

    The number of points N, or a precomputed FFT Sk may be provided. By
    default, the CSD function returned is normalized so that the integral of
    the PSD is equal to the mean squared amplitude (mean energy) of s (see
    Notes).

    Paramters
    ---------
    s : ndarray
        Signals for which to estimate the CSD, time dimension in the last axis
    Sk : ndarray (optional)
        Precomputed FFT of rows of s
    N : int (optional)
        Indicates an N-point FFT where N != s.shape[-1]
    sides : str (optional)        
        Indicates whether to return a one-sided or two-sided CSD
    normalize : boolean (optional)
        Normalizes the PSD

    Returns
    -------
    (freqs, csd_est) : ndarrays
        The estimatated CSD and the frequency points vector.
        The CSD{i,j}(f) are returned in a square "matrix" of vectors
        holding Sij(f). For an input array that is reshaped to (M,N),
        the output is (M,M,N)

    Notes
    -----
    setting dw = 2*PI/N, then the integral from -PI, PI (or 0,PI) of PSD/(2PI)
    will be nearly equal to sxy(0), where sxx is the crosscorrelation function
    of s1(n), s2(n). By definition, sxy(0) = E{s1(n)s2*(n)} ~ (s1*s2.conj()).mean()
    """
    s_shape = s.shape
    s.shape = (np.prod(s_shape[:-1]), s_shape[-1])
    # defining an Sk_loc is a little opaque, but it avoids having to
    # reset the shape of any user-given Sk later on
    if Sk is not None:
        Sk_shape = Sk.shape
        N = Sk.shape[-1]
        Sk_loc = Sk.reshape(np.prod(Sk_shape[:-1]), N)
    else:
        N = s.shape[-1] if not N else N
        Sk_loc = np.fft.fft(s, n=N)
    # reset s.shape
    s.shape = s_shape

    M = Sk_loc.shape[0]
    norm = float(s.shape[-1])
    if sides=='onesided':
        # putative Nyquist freq
        Fn = N/2 + 1
        # last duplicate freq
        Fl = (N+1)/2
        csd_mat = np.empty((M,M,Fn), 'D')
        freqs = np.linspace(0, np.pi, Fn)
        for i in xrange(M):
            for j in xrange(i+1):
                csd_mat[i,j,0] = Sk_loc[i,0]*Sk_loc[j,0].conj()
                csd_mat[i,j,1:Fl] = 2 * (Sk_loc[i,1:Fl]*Sk_loc[j,1:Fl].conj())
                if Fn > Fl:
                    csd_mat[i,j,Fn-1] = Sk_loc[i,Fn-1]*Sk_loc[j,Fn-1].conj()
                    
    else:
        csd_mat = np.empty((M,M,N), 'D')
        freqs = np.linspace(0, 2*np.pi, N, endpoint=False)        
        for i in xrange(M):
            for j in xrange(i+1):
                csd_mat[i,j] = Sk_loc[i]*Sk_loc[j].conj()
    if normalize:
        csd_mat /= norm

    upper_idc = ut.triu_indices(M,k=1)
    lower_idc = ut.tril_indices(M,k=-1)
    csd_mat[upper_idc] = csd_mat[lower_idc].conj()
    return freqs, csd_mat


def nDPSS(Fs, N, BW):
    """Given a sampling frequency, number of samples, and an approximate
    DPSS window bandwidth, return the number of DPSSs to use in a
    multi-taper PSD estimate: K = N*BW/Fs = BW/f0
    Also returns the true bandwidth.

    Paramters
    ---------
    Fs : float
        sampling frequency
    N : int
        sequence length
    BW : float
        window bandwidth to match

    Returns
    -------
    K, true_BW : int, float
        The optimal number of DPSS windows to use in PSD estimation, and
        the true bandwidth of the windows.

    Notes
    -----
    The bandwidth parameter reflects the length of the interval [-BW/2, BW/2].
    """
    K = int(N*BW/Fs + 0.5)
    true_BW = Fs*K/N
    return K, true_BW

def DPSS_windows(N, W, Kmax):
    """Returns the first Kmax-1 Discrete Prolate Spheroidal Sequences for
    a given frequency-spacing multiple W and sequence length N. 

    Paramters
    ---------
    N : int
        sequence length
    W : float
        half bandwidth corresponding to 2W = Kmax*f0 = (Kmax/T)
    Kmax : int
        number of DPSS windows to return is Kmax-1

    Returns
    -------
    v : ndarray
        an array of DPSS windows shaped (Kmax-1, N)

    Notes
    -----
    Tridiagonal form of DPSS calculation from:

    Slepian, D. Prolate spheroidal wave functions, Fourier analysis, and
    uncertainty V: The discrete case. Bell System Technical Journal,
    Volume 57 (1978), 1371430
    """
    # here we want to set up an optimization problem to find a sequence
    # whose energy is maximally concentrated within band [-W,W].
    # Thus, the measure lambda(T,W) is the ratio between the energy within
    # that band, and the total energy. This leads to the eigen-system
    # (A - (l1)I)v = 0, where the eigenvector corresponding to the largest
    # eigenvalue is the sequence with maximally concentrated energy. The
    # collection of eigenvectors of this system are called Slepian sequences,
    # or discrete prolate spheroidal sequences (DPSS). Only the first K-1,
    # K = 2NW orders of DPSS will exhibit good spectral concentration
    # [see http://en.wikipedia.org/wiki/Spectral_concentration_problem]
    
    # Here I set up an alternative symmetric tri-diagonal eigenvalue problem
    # such that
    # (B - (l2)I)v = 0, and v are our DPSS (but eigenvalues l2 != l1)
    # the main diagonal = ([N-1-2*t]/2)**2 cos(2PIW), t=[0,1,2,...,N-1]
    # and the first off-diangonal = t(N-t)/2, t=[1,2,...,N-1]
    # [see Percival and Walden, 1993]
    ab = np.zeros((2,N), 'd')
    nidx = np.arange(N)
    ab[0,1:] = nidx[1:]*(N-nidx[1:])/2.
    ab[1] = ((N-1-2*nidx)/2.)**2 * np.cos(2*np.pi*W)
    # only calculate the highest Kmax-1 eigenvectors
    l,v = linalg.eig_banded(ab, select='i', select_range=(N+1-Kmax, N-1))
    return v.transpose()[::-1]

def multi_taper_psd(s, BW=None, Fs=2*np.pi, sides='onesided'):
    """Returns an estimate of the PSD function of s using the multitaper
    method. If BW and Fs are not specified by the user, a bandwidth of 4
    times the fundamental frequency, corresponding to K = 8.

    Parameters
    ----------
    s : ndarray
        An array of sampled random processes, where the time axis is
        assumed to be on the last axis
    BW : float (optional)
        The bandwidth of the windowing function will determine the number
        tapers to use. Normal values are in the range [3/2,5] * 2f0, where
        f0 is the fundamental frequency of an N-length sequence.
        This parameters represents trade-off between frequency resolution (BW)
        and variance reduction (number of tapers).
    Fs : float (optional)
        The sampling frequency
    sides : str (optional)
        Indicates whether to return a one-sided or two-sided PSD

    Returns
    -------
    (freqs, psd_est) : ndarrays
        The estimatated PSD and the frequency points vector

    """
    # have last axis be time series for now
    N = s.shape[-1]

    # choose bw 2W to be a small multiple of the fundamental freq f0=Fs/N
    if not BW:
        W = 4 * Fs / N # 2W = 4 * 2f0
        Kmax = 8
    else:
        Kmax, true_BW = nDPSS(Fs, N, BW)
        W = true_BW/2.

    v = DPSS_windows(N, W, Kmax)

    sig_sl = [slice(None)]*len(s.shape)
    sig_sl.insert(-1, np.newaxis)

    # tapers.shape is (..., Kmax-1, N)
    tapers = s[sig_sl] * v
    # don't normalize the periodograms by 1/N as normal.. since the taper
    # windows are orthonormal, they effectively scale the signal by 1/N
    tapers_sdf = periodogram(tapers, sides=sides, normalize=False)
    if sides=='onesided':
        freqs = np.linspace(0, np.pi, N/2+1)
    else:
        freqs = np.linspace(0, 2*np.pi, N, endpoint=False)
    psd_est = tapers_sdf.mean(axis=-2)
    return freqs, psd_est

def multi_taper_csd(s, BW=None, Fs=2*np.pi, sides='onesided'):
    """Returns an estimate of the PSD function of s using the multitaper
    method. If BW and Fs are not specified by the user, a bandwidth of 4
    times the fundamental frequency, corresponding to K = 8.

    Parameters
    ----------
    s : ndarray
        An array of sampled random processes, where the time axis is
        assumed to be on the last axis. If ndim > 2, the number of time
        series to compare will still be taken as prod(s.shape[:-1])
        
    BW : float (optional)
        The bandwidth of the windowing function will determine the number
        tapers to use. Normal values are in the range [3/2,5] * 2f0, where
        f0 is the fundamental frequency of an N-length sequence.
        This parameters represents trade-off between frequency resolution
        (narrow BW) and variance reduction (number of tapers).
    Fs : float (optional)
        The sampling frequency
    sides : str (optional)
        Indicates whether to return a one-sided or two-sided PSD

    Returns
    -------
    (freqs, csd_est) : ndarrays
        The estimatated CSD and the frequency points vector.
        The CSD{i,j}(f) are returned in a square "matrix" of vectors
        holding Sij(f). For an input array of (M,N), the output is (M,M,N)
    """
    s_shape = s.shape
    M, N = np.prod(s_shape[:-1]), s_shape[-1]
    s.shape = (M, N)
    
    # choose bw W to be a small multiple of the fundamental freq f0=Fs/N
    if not BW:
        W = 4 * Fs/N # 2W = 4 * 2f0
        Kmax = 8
    else:
        Kmax, true_BW = nDPSS(Fs, N, BW)
        W = true_BW/2.

    v = DPSS_windows(N, W, Kmax)

    sig_sl = [slice(None)]*len(s.shape)
    sig_sl.insert(len(s.shape)-1, np.newaxis)
    
    # tapers.shape is (M, Kmax-1, N)
    tapers = s[sig_sl] * v

    Sk = np.fft.fft(tapers)
    if sides=='onesided':
        Fl = (N+1)/2
        Fn = N/2 + 1
        csd_mat = np.empty((M,M,Fn), 'D')
        freqs = np.linspace(0, np.pi, Fn)
        for i in xrange(M):
            for j in xrange(i+1):
                csd = np.zeros((Kmax-1,Fn), 'D')
                csd[:,0] = (Sk[i,:,0]*Sk[j,:,0].conj())
                csd[:,1:Fl] = 2 * (Sk[i,:,1:Fl]*Sk[j,:,1:Fl].conj())
                if Fn > Fl:
                    csd[:,Fn-1] = Sk[i,:,Fn-1]*Sk[j,:,Fn-1].conj()
                csd_mat[i,j] = csd.mean(axis=0)
    else:
        csd_mat = np.empty((M,M,N), 'D')
        freqs = np.linspace(0, 2*np.pi, N, endpoint=False)
        for i in xrange(M):
            for j in xrange(i+1):
                csd_mat[i,j] = (Sk[i]*Sk[j].conj()).mean(axis=0)

    upper_idc = ut.triu_indices(M,k=1)
    lower_idc = ut.tril_indices(M,k=-1)
    csd_mat[upper_idc] = csd_mat[lower_idc].conj()

    return freqs, csd_mat 

def my_freqz(b, a=1., Nfreqs=1024, sides='onesided'):
    if sides=='onesided':
        fgrid = np.linspace(0,np.pi,Nfreqs/2+1)
    else:
        fgrid = np.linspace(0,2*np.pi,Nfreqs,endpoint=False)
    float_type = type(1.)
    int_type = type(1)
    Nfreqs = len(fgrid)
    if isinstance(b, float_type) or isinstance(b, int_type) or len(b) == 1:
        bw = np.ones(Nfreqs, 'D')*b
    else:
        L = len(b)
        DTFT = np.exp(-1j*fgrid[:,np.newaxis]*np.arange(0,L))
        bw = np.dot(DTFT, b)
    if isinstance(a, float_type) or isinstance(a, int_type) or len(a) == 1:
        aw = np.ones(Nfreqs, 'D')*a
    else:
        L = len(a)
        DTFT = np.exp(-1j*fgrid[:,np.newaxis]*np.arange(0,L))
        aw = np.dot(DTFT, a)
    return fgrid, bw/aw
    

def yule_AR_est(s, order, Nfreqs, sxx=None, sides='onesided', system=False):
    """Finds the parameters for an autoregressive model of order norder
    of the process s. Using these parameters, an estimate of the PSD
    is calculated from [-PI,PI) in Nfreqs, or [0,PI] in {N/2+1}freqs.
    Uses the basic Yule Walker system of equations, and a baised estimate
    of sxx (unless sxx is provided).

    The model for the autoregressive process takes this convention:
    s[n] = a1*s[n-1] + a2*s[n-2] + ... aP*s[n-P] + v[n]

    where v[n] is a zero-mean white noise process with variance=sigma_v

    Parameters
    ----------
    s : ndarray
        The sampled autoregressive random process

    order : int
        The order P of the AR system

    Nfreqs : int
        The number of spacings on the frequency grid from [-PI,PI).
        If sides=='onesided', Nfreqs/2+1 frequencies are computed from [0,PI]

    sxx : ndarray (optional)
        An optional, possibly unbiased estimate of the autocorrelation of s

    sides : str (optional)
        Indicates whether to return a one-sided or two-sided PSD

    system : bool (optional)
        If True, return the AR system parameters, sigma_v and a{k}
    
    Returns
    -------
    (w, ar_psd)
    w : Array of normalized frequences from [-.5, .5) or [0,.5]
    ar_psd : A PSD estimate computed by sigma_v / |1-a(f)|**2 , where
             a(f) = DTFT(ak)
    """
    if sxx is not None and type(sxx) == np.ndarray:
        sxx_m = sxx[:order+1]
    else:
        sxx_m = ut.autocorr(s)[:order+1]

    R = linalg.toeplitz(sxx_m[:order].conj())
    y = sxx_m[1:].conj()
    ak = linalg.solve(R,y)
    sigma_v = sxx_m[0] - np.dot(sxx_m[1:], ak)
    if system:
        return sigma_v, ak
    # compute the psd as |h(f)|**2, where h(f) is the transfer function..
    # for this model s[n] = a1*s[n-1] + a2*s[n-2] + ... aP*s[n-P] + v[n]
    # Taken as a FIR system from s[n] to v[n],
    # v[n] = w0*s[n] + w1*s[n-1] + w2*s[n-2] + ... + wP*s[n-P],
    # where w0 = 1, and wk = -ak for k>0
    # the transfer function here is H(f) = DTFT(w)
    # leading to Sxx(f) = Vxx(f) / |H(f)|**2 = sigma_v / |H(f)|**2
    w, hw = my_freqz(sigma_v**0.5, a=np.concatenate(([1], -ak)),
                     Nfreqs=Nfreqs, sides=sides)
    ar_psd = (hw*hw.conj()).real
    return (w,2*ar_psd) if sides=='onesided' else (w,ar_psd)
    
    
def LD_AR_est(s, order, Nfreqs, sxx=None, sides='onesided', system=False):
    """Finds the parameters for an autoregressive model of order norder
    of the process s. Using these parameters, an estimate of the PSD
    is calculated from [-PI,PI) in Nfreqs, or [0,PI] in {N/2+1}freqs.
    Uses the Levinson-Durbin recursion method, and a baised estimate
    of sxx (unless sxx is provided).

    The model for the autoregressive process takes this convention:
    s[n] = a1*s[n-1] + a2*s[n-2] + ... aP*s[n-P] + v[n]

    where v[n] is a zero-mean white noise process with variance=sigma_v

    Parameters
    ----------
    s : ndarray
        The sampled autoregressive random process

    order : int
        The order P of the AR system

    Nfreqs : int
        The number of spacings on the frequency grid from [-PI,PI).
        If sides=='onesided', Nfreqs/2+1 frequencies are computed from [0,PI]

    sxx : ndarray (optional)
        An optional, possibly unbiased estimate of the autocorrelation of s

    sides : str (optional)
        Indicates whether to return a one-sided or two-sided PSD

    system : bool (optional)
        If True, return the AR system parameters, sigma_v and a{k}
    
    Returns
    -------
    (w, ar_psd)
    w : Array of normalized frequences from [-.5, .5) or [0,.5]
    ar_psd : A PSD estimate computed by sigma_v / |1-a(f)|**2 , where
             a(f) = DTFT(ak)
    """
    if sxx is not None and type(sxx) == np.ndarray:
        sxx_m = sxx[:order+1]
    else:
        sxx_m = ut.autocorr(s)[:order+1]
    
    phi = np.zeros((order+1, order+1), 'd')
    sig = np.zeros(order+1)
    # initial points for the recursion
    phi[1,1] = sxx_m[1]/sxx_m[0]
    sig[1] = sxx_m[0] - phi[1,1]*sxx_m[1]
    for k in xrange(2,order+1):
        phi[k,k] = (sxx_m[k]-np.dot(phi[1:k,k-1], sxx_m[1:k][::-1]))/sig[k-1]
        for j in xrange(1,k):
            phi[j,k] = phi[j,k-1] - phi[k,k]*phi[k-j,k-1]
        sig[k] = sig[k-1]*(1 - phi[k,k]**2)

    sigma_v = sig[-1]; ak = phi[1:,-1]
    if system:
        return sigma_v, ak
    w, hw = my_freqz(sigma_v**0.5, a=np.concatenate(([1], -ak)),
                     Nfreqs=Nfreqs, sides=sides)
    ar_psd = (hw*hw.conj()).real
    return (w,2*ar_psd) if sides=='onesided' else (w,ar_psd)
        
#--------------------------------------------------------------------------------
#Coherency calculated using cached spectra
#--------------------------------------------------------------------------------
"""The idea behind this set of functions is to keep a cache of the windowed fft
calculations of each time-series in a massive collection of time-series, so
that this calculation doesn't have to be repeated each time a cross-spectrum is
calculated. The first function creates the cache and then, another function
takes the cached spectra and calculates PSDs and CSDs, which are then passed to
coherency_calculate and organized in a data structure similar to the one
created by coherence"""

def cache_fft(time_series,ij,lb=0,ub=None,
                  method=None,prefer_speed_over_memory=False,
                  scale_by_freq=True):
    """compute and cache the windowed FFTs of the time_series, in such a way
    that computing the psd and csd of any combination of them can be done
    quickly.

    Parameters
    ----------

    time_series: an ndarray with time-series, where time is the last dimension

    ij: a list of tuples, each containing a pair of indices. The resulting
    cache will contain the fft of time-series in the rows indexed by the unique
    elements of the union of i and j
    
    lb,ub: defines a frequency band of interest

    method: optional, dict

    Returns
    -------
    freqs, cache

    where: cache = {'FFT_slices':FFT_slices,'FFT_conj_slices':FFT_conj_slices,
             'norm_val':norm_val}

    
    Notes
    ----
    - For now, the only method implemented is 'mlab'
    - Notice that detrending the input is not an option here, in order to save
    time on an empty function call!
    
    """
    if method is None:
        method = {'this_method':'mlab'} #The default
        
    if method['this_method'] == 'mlab':
        NFFT = method.get('NFFT',64)
        Fs = method.get('Fs',2*np.pi)
        window = method.get('window',mlab.window_hanning)
        n_overlap = method.get('n_overlap',int(np.ceil(NFFT/2.0)))
        
    time_series = ut.zero_pad(time_series,NFFT)
    
    #The shape of the zero-padded version:
    n_channels, n_time_points = time_series.shape

    # get all the unique channels in time_series that we are interested in by
    # checking the ij tuples
    all_channels = set()
    for i,j in ij:
        all_channels.add(i); all_channels.add(j)
    n_channels = len(all_channels)

    # for real time_series, ignore the negative frequencies
    if np.iscomplexobj(time_series): n_freqs = NFFT
    else: n_freqs = NFFT//2+1

    #Which frequencies
    freqs = ut.get_freqs(Fs,NFFT)

    #If there are bounds, limit the calculation to within that band,
    #potentially include the DC component:
    lb_idx,ub_idx = ut.get_bounds(freqs,lb,ub)

    n_freqs=ub_idx-lb_idx
    #Make the window:
    if mlab.cbook.iterable(window):
        assert(len(window) == NFFT)
        window_vals = window
    else:
        window_vals = window(np.ones(NFFT, time_series.dtype))
        
    #Each fft needs to be normalized by the square of the norm of the window
    #and, for consistency with newer versions of mlab.csd (which, in turn, are
    #consistent with Matlab), normalize also by the sampling rate:
   
    if scale_by_freq:
        #This is the normalization factor for one-sided estimation, taking into
        #account the sampling rate. This makes the PSD a density function, with
        #units of dB/Hz, so that integrating over frequencies gives you the RMS
        #(XXX this should be in the tests!).
        norm_val = (np.abs(window_vals)**2).sum()*(Fs/2)
        
    else:
        norm_val = (np.abs(window_vals)**2).sum()/2
   
    # cache the FFT of every windowed, detrended NFFT length segement
    # of every channel.  If prefer_speed_over_memory, cache the conjugate
    # as well
        
    i_times = range(0, n_time_points-NFFT+1, NFFT-n_overlap)
    n_slices = len(i_times)
    FFT_slices = {}
    FFT_conj_slices = {}
    Pxx = {}
    
    for i_channel in all_channels:
        Slices = np.zeros( (n_slices,n_freqs), dtype=np.complex)
        for iSlice in xrange(n_slices):
            thisSlice = time_series[i_channel,
                                    i_times[iSlice]:i_times[iSlice]+NFFT]

            
            #Windowing: 
            thisSlice = window_vals*thisSlice #No detrending
            #Derive the fft for that slice:
            Slices[iSlice,:] = (np.fft.fft(thisSlice)[lb_idx:ub_idx])
            
        FFT_slices[i_channel] = Slices


        if prefer_speed_over_memory:
            FFT_conj_slices[i_channel] = np.conjugate(Slices)

    cache = {'FFT_slices':FFT_slices,'FFT_conj_slices':FFT_conj_slices,
             'norm_val':norm_val}

    return freqs,cache

def cache_to_psd(cache,ij):
    """ From a set of cached set of windowed fft's, calculate the psd
    for all the ij"""

    #This is the way it is saved by cache_spectra:
    FFT_slices=cache['FFT_slices']
    FFT_conj_slices=cache['FFT_conj_slices']
    norm_val=cache['norm_val']

    #This is where the output goes to: 
    Pxx = {}
    all_channels = set()
    for i,j in ij:
        all_channels.add(i); all_channels.add(j)
    n_channels = len(all_channels)

    for i in all_channels:

        #If we made the conjugate slices:
        if FFT_conj_slices:
            Pxx[i] = FFT_slices[i] * FFT_conj_slices[i]
        else:
            Pxx[i] = FFT_slices[i] * np.conjugate(FFT_slices[i])
        
        #If there is more than one window
        if FFT_slices[i].shape[0]>1:
            Pxx[i] = np.mean(Pxx[i],0)

        Pxx[i] /= norm_val
    
    
    return Pxx

def cache_to_phase(cache,ij):
    """ From a set of cached set of windowed fft's, calculate the
    frequency-band dependent phase for all the ij"""

    #This is the way it is saved by cache_spectra:
    FFT_slices=cache['FFT_slices']

    Phase = {}

    all_channels = set()
    for i,j in ij:
        all_channels.add(i); all_channels.add(j)
    n_channels = len(all_channels)

    for i in all_channels:
        Phase[i] = np.angle(FFT_slices[i])
        #If there is more than one window, average over all the windows: 
        if FFT_slices[i].shape[0]>1:
            Phase[i] = np.mean(Phase[i],0)
    
    return Phase

def cache_to_coherency(cache,ij):
    """From a set of cached spectra, calculate the coherency
    relationships

    Parameters
    ----------
    cache: a cache with fft's, created by .. function:: cache_fft

    ij: the pairs of 
    """

    #This is the way it is saved by cache_spectra:
    FFT_slices=cache['FFT_slices']
    FFT_conj_slices=cache['FFT_conj_slices']
    norm_val=cache['norm_val']

    Pxx = cache_to_psd(cache,ij)
    
    Cxy = {}
    Phase = {}
    for i,j in ij:

        #If we made the conjugate slices:
        if FFT_conj_slices:
            Pxy = FFT_slices[i] * FFT_conj_slices[j]
        else:
            Pxy = FFT_slices[i] * np.conjugate(FFT_slices[j])

        #If there is more than one window
        if FFT_slices.items()[0][1].shape[0]>1:
            Pxy = np.mean(Pxy,0)

        Pxy /= norm_val
        Cxy[i,j] = coherency_calculate(Pxy,Pxx[i],Pxx[j])
       
       
    return Cxy


#--------------------------------------------------------------------------------
# Granger causality
#--------------------------------------------------------------------------------

"""XXX docstring for Granger causality algorithms """


#-----------------------------------------------------------------------------
# Signal generation
#-----------------------------------------------------------------------------
def gauss_white_noise(npts):
    """Gaussian white noise.

    XXX - incomplete."""

    # Amplitude - should be a parameter
    a = 1.
    # Constant, band-limited amplitudes
    # XXX - no bandlimiting yet
    amp = np.zeros(npts)
    amp.fill(a)
    
    # uniform phases
    phi = np.random.uniform(high=2*np.pi, size=npts)
    # frequency-domain signal
    c = amp*np.exp(1j*phi)
    # time-domain
    n = np.fft.ifft(c)

    # XXX No validation that output is gaussian enough yet
    return n

def autocov(x):
    """ Calculate the auto-covariance of a signal.

    This assumes that the signal is wide-sense stationary

    Parameters
    ----------

    x: 1-d float array

    The signal

    Returns
    -------

    nXn array (where n is x.shape[0]) with the autocovariance matrix of the
    signal x

    Notes
    -----

    See: http://en.wikipedia.org/wiki/Autocovariance

    Examples:
    ---------

    >>> x = np.random.randn(3)
    >>> a = tsa.autocov(x)
    >>> a
    array([[ 1.05518268,  2.81185132,  1.05518268],
          [ 2.40275058,  1.36620712,  0.51137247],
          [ 0.24181483,  1.36620712,  2.57539073]])
    >>> x = tsa.gauss_white_noise(3)
    >>> a = tsa.autocov(x)
    >>> a
    array([[-0.30238689,  0.78882452, -0.30238689],
          [ 0.7937778 , -0.17635249, -0.00367334],
          [-0.11933134, -0.17635249, -0.08868673]])
    
    """

    n = x.shape[0]
    autocov = np.empty((n,n))

    for i in range(n):
        autocov[i] = np.correlate(x,np.roll(x,-i),'same') - x.mean()**2

    return autocov
        
        
    
    
    
