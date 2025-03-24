import numpy as np
from numpy.linalg import LinAlgError, inv
from numpy import dot
import pandas as pd

from lifelines.plotting import plot_dataframes
from lifelines.utils import dataframe_from_events_censorship, basis

import pdb



class NelsonAalenFitter(object):
    """
    Class for fitting the Nelson-Aalen estimate for the cumulative hazard. 

    NelsonAalenFitter( alpha=0.95, nelson_aalen_smoothing=True)

    alpha: The alpha value associated with the confidence intervals. 
    nelson_aalen_smoothing: If the event times are naturally discrete (like discrete years, minutes, etc.)
      then it is advisable to turn this parameter to False. See [1], pg.84.

    """
    def __init__(self, alpha=0.95, nelson_aalen_smoothing=True):
        self.alpha = alpha
        self.nelson_aalen_smoothing = nelson_aalen_smoothing
        if nelson_aalen_smoothing:
          self._variance_f = self._variance_f_smooth
          self._additive_f = self._additive_f_smooth
        else:
          self._variance_f = self._variance_f_discrete
          self._additive_f = self._additive_f_discrete

    def fit(self, event_times,censorship=None, timeline=None, columns=['NA-estimate']):
        """
        Parameters:
          event_times: an (n,1) array of times that the death event occured at 
          timeline: return the best estimate at the values in timelines (postively increasing)

        Returns:
          DataFrame with index either event_times or timelines (if not None), with
          values as the NelsonAalen estimate
        """
        
        if censorship is None:
           self.censorship = np.ones_like(event_times, dtype=bool) #why boolean?
        else:
           self.censorship = censorship.copy()

        self.event_times = dataframe_from_events_censorship(event_times, self.censorship)

        if timeline is None:
           self.timeline = self.event_times.index.values.copy()
        else:
           self.timeline = timeline
        self.cumulative_hazard_, cumulative_sq_ = _additive_estimate(self.event_times, 
                                                                     self.timeline, self.censorship, 
                                                                     self._additive_f, 0, columns, self._variance_fgi )
        self.confidence_interval_ = self._bounds(cumulative_sq_)
        self.plot = plot_dataframes(self, "cumulative_hazard_")

        return

    def _bounds(self, cumulative_sq_):
        alpha2 = inv_normal_cdf(1 - (1-self.alpha)/2)
        df = pd.DataFrame( index=self.timeline)
        df["upper_bound_%.2f"%self.alpha] = self.cumulative_hazard_.values*np.exp(alpha2*np.sqrt(cumulative_sq_)/self.cumulative_hazard_.values )
        df["lower_bound_%.2f"%self.alpha] = self.cumulative_hazard_.values*np.exp(-alpha2*np.sqrt(cumulative_sq_)/self.cumulative_hazard_.values )
        return df

    def _variance_f_smooth(self, N, d):
        if N==d==0:
            return 0
        return np.sum([1./(N-i)**2 for i in range(d)])

    def _variance_f_discrete(self, N, d):
        if N==d==0:
            return 0
        return 1.*(N-d)*d/N**3

    def _additive_f_smooth(self, N, d):
        if N==d==0:
          return 0
        return np.sum([1./(N-i) for i in range(d)])

    def _additive_f_discrete(self, N,d ):
       #check it 0
       if N==d==0:
          return 0
       return 1.*d/N


class KaplanMeierFitter(object):
   
  def __init__(self, alpha = 0.95):
       self.alpha = alpha

  def fit(self, event_times,censorship=None, timeline=None, columns=['KM-estimate']):
       """
       Parameters:
         event_times: an (n,1) array of times that the death event occured at 
         timeline: return the best estimate at the values in timelines (postively increasing)
         censorship: an (n,1) array of booleans -- True if the the death was observed, False if the event 
            was lost (right-censored). Defaults all True if censorship==None
       Returns:
         DataFrame with index either event_times or timelines (if not None), with
         values as the NelsonAalen estimate
       """
       #need to sort event_times
       if censorship is None:
          self.censorship = np.ones_like(event_times, dtype=bool) #why boolean?
       else:
          self.censorship = censorship.copy()

       self.event_times = dataframe_from_events_censorship(event_times, self.censorship)

       if timeline is None:
          self.timeline = self.event_times.index.values.copy()
       else:
          self.timeline = timeline
       log_surivial_function, cumulative_sq_ = _additive_estimate(self.event_times, self.timeline, 
                                                                  self.censorship, self._additive_f, 
                                                                  0, columns, self._variance_f )
       self.survival_function_ = np.exp(log_surivial_function)
       self.median_ = median_survival_times(self.survival_function_)
       self.confidence_interval_ = self._bounds(cumulative_sq_)
       self.plot = plot_dataframes(self, "survival_function_")
       return self

  def _additive_f(self,N,d):
      if N==d==0:
        return 0
      return np.log(1 - 1.*d/N)

  def _bounds(self, cumulative_sq_):
      alpha2 = inv_normal_cdf(1 - (1-self.alpha)/2)
      df = pd.DataFrame( index=self.timeline)
      df["upper_bound_%.2f"%self.alpha] = self.survival_function_.values**(np.exp(alpha2*cumulative_sq_/np.log(self.survival_function_.values)))
      df["lower_bound_%.2f"%self.alpha] = self.survival_function_.values**(np.exp(-alpha2*cumulative_sq_/np.log(self.survival_function_.values)))
      return df

  def _variance_f(self,N,d):
     if N==d==0:
        return 0
     return 1.*d/(N*(N-d))


def _additive_estimate(event_times, timeline, observed, additive_f, initial, columns, variance_f):
    """

    nelson_aalen_smoothing: see section 3.1.3 in Survival and Event History Analysis

    """
    timeline = timeline.astype(float)
    if timeline[0] > 0:
       timeline = np.insert(timeline,0,0.)

    n = timeline.shape[0]
    _additive_estimate_ = pd.DataFrame(np.zeros((n,1)), index=timeline, columns=columns)
    _additive_var = pd.DataFrame(np.zeros((n,1)), index=timeline)

    N = event_times["removed"].sum()
    t_0 =0
    _additive_estimate_.ix[(timeline<t_0)]=initial
    _additive_var.ix[(timeline<t_0)]=0

    v = initial
    v_sq = 0
    for t, removed, observed_deaths in event_times.itertuples():
        _additive_estimate_.ix[ (t_0<=timeline)*(timeline<t) ] = v  
        _additive_var.ix[ (t_0<=timeline)*(timeline<t) ] = v_sq
        missing = removed - observed_deaths
        N -= missing
        v += additive_f(N,observed_deaths)
        v_sq += variance_f(N,observed_deaths)
        N -= observed_deaths
        t_0 = t
    _additive_estimate_.ix[(timeline>=t)]=v
    _additive_var.ix[(timeline>=t)]=v_sq
    return _additive_estimate_, _additive_var


class AalenAdditiveFitter(object):

  def __init__(self,fit_intercept=True, alpha=0.95, penalizer = 0.0):
    self.fit_intercept = fit_intercept
    self.alpha = alpha
    self.penalizer = penalizer

  def fit(self, event_times, X, timeline = None, censorship=None, columns=None):
    """currently X is a static (n,d) array

    event_times: (n,1) array of event times
    X: (n,d) the design matrix, either a numpy matrix or DataFrame.  
    timeline: (t,1) timepoints in ascending order
    censorship: (n,1) boolean array of censorships: True if observed, False if right-censored.
                By default, assuming all are observed.

    Fits: self.cumulative_hazards_: a (t,d+1) dataframe of cumulative hazard coefficients
          self.hazards_: a (t,d+1) dataframe of hazard coefficients

    """
    #deal with the covariate matrix. Check if it is a dataframe or numpy array
    n,d = X.shape
    if type(X)==pd.core.frame.DataFrame:
      X_ = X.values.copy()
      if columns is None:
        columns = X.columns
    else:
      X_ = X.copy()

    # append a columns of ones for the baseline hazard
    ix = event_times.argsort()[0,:]
    X_ = X_[ix,:].copy() if not self.fit_intercept else np.c_[ X_[ix,:].copy(), np.ones((n,1)) ]
    sorted_event_times = event_times[0,ix].copy()

    #set the column's names of the dataframe.
    if columns is None:
      columns = range(d) + ["baseline"]
    else:
      columns =  [c for c in columns ] + ["baseline"]

    #set the censorship events. 1 if the death was observed.
    if censorship is None:
        observed = np.ones(n, dtype=bool)
    else:
        observed = censorship.reshape(n)

    #set the timeline -- this is used as DataFrame index in the results
    if timeline is None:
        timeline = sorted_event_times

    timeline = timeline.astype(float)
    if timeline[0] > 0:
       timeline = np.insert(timeline,0,0.)
    
    zeros = np.zeros((timeline.shape[0],d+self.fit_intercept))
    self.cumulative_hazards_ = pd.DataFrame(zeros.copy() , index=timeline, columns = columns)
    self.hazards_ = pd.DataFrame(np.zeros((event_times.shape[1],d+self.fit_intercept)), index=sorted_event_times, columns = columns)
    self._variance = pd.DataFrame(zeros.copy(), index=timeline, columns = columns)
    
    #create the penalizer matrix for L2 regression
    penalizer = self.penalizer*np.eye(d + self.fit_intercept)
    
    t_0 = sorted_event_times[0]
    cum_v = np.zeros((d+self.fit_intercept,1))
    v = cum_v.copy()
    for i,time in enumerate(sorted_event_times):
        relevant_times = (t_0<timeline)*(timeline<=time)
        if observed[i] == 0:
          X_[i,:] = 0
        try:
          V = dot(inv(dot(X_.T,X_) - penalizer), X_.T)
        except LinAlgError:
          #if penalizer > 0, this should not occur.
          self.cumulative_hazards_.ix[relevant_times] =cum_v.T
          self.hazards_.iloc[i] = v.T 
          self._variance.ix[relevant_times] = dot( V[:,i][:,None], V[:,i][None,:] ).diagonal()
          X_[i,:] = 0
          t_0 = time
          continue

        v = dot(V, basis(n,i))
        cum_v = cum_v + v
        self.cumulative_hazards_.ix[relevant_times] = self.cumulative_hazards_.ix[relevant_times].values + cum_v.T
        self.hazards_.iloc[i] = self.hazards_.iloc[i].values + v.T
        self._variance.ix[relevant_times] = self._variance.ix[relevant_times].values + dot( V[:,i][:,None], V[:,i][None,:] ).diagonal()
        t_0 = time
        X_[i,:] = 0

    #clean up last iteration
    relevant_times = (timeline>time)
    self.cumulative_hazards_.ix[relevant_times] = cum_v.T
    self.hazards_.iloc[i] = v.T
    self._variance.ix[relevant_times] = dot( V[:,i][:,None], V[:,i][None,:] ).diagonal()
    self.timeline = timeline
    self.X = X
    self.censorship = censorship
    self._compute_confidence_intervals()
    return self

  def smoothed_hazards_(self, bandwith=1):
    """
    Using the gaussian kernel to smooth the hazard function, with sigma/bandwith

    """
    C = self.censorship.astype(bool)
    return pd.DataFrame( np.dot(gaussian(self.timeline[:,None], self.timeline[C][None,:],bandwith), self.hazards_.values[C,:]), 
            columns=self.hazards_.columns, index=self.timeline)

  def _compute_confidence_intervals(self):
    alpha2 = inv_normal_cdf(1 - (1-self.alpha)/2)
    n = self.timeline.shape[0]
    d = self.cumulative_hazards_.shape[1]
    index = [['upper']*n+['lower']*n, np.concatenate( [self.timeline, self.timeline] ) ]
    self.confidence_intervals_ = pd.DataFrame(np.zeros((2*n,d)),index=index)
    self.confidence_intervals_.ix['upper'] = self.cumulative_hazards_.values + alpha2*np.sqrt(self._variance.values)
    self.confidence_intervals_.ix['lower'] = self.cumulative_hazards_.values - alpha2*np.sqrt(self._variance.values)
    return 

  def predict_cumulative_hazard(self, X):
    """
    X: a (n,d) covariate matrix

    Returns the hazard rates for the individuals
    """
    n,d = X.shape
    try:
      X_ = X.values.copy()
    except:
      X_ = X.copy()
    X_ = X.copy() if not self.fit_intercept else np.c_[ X.copy(), np.ones((n,1)) ]
    return pd.DataFrame(np.dot(self.cumulative_hazards_, X_.T), index=self.timeline, columns=self.hazards_.columns)

  def predict_survival_function(self,X):
    """
    X: a (n,d) covariate matrix

    Returns the survival functions for the individuals
    """
    return np.exp(-self.predict_cumulative_hazard(X))

  def predict_median_lifetimes(self,X):
    """
    X: a (n,d) covariate matrix
    Returns the median lifetimes for the individuals
    """
    return median_survival_times(self.predict_survival_function(X))


#utils

def qth_survival_times(q, survival_functions):
    """
    survival_functions: a (n,d) dataframe or numpy array.
    If dataframe, will return index values (actual times)
    If numpy array, will return indices.

    Returns -1 if infinity.
    """
    assert 0<=q<=1, "q must be between 0 and 1"
    sv_b = (survival_functions < q)
    try:
        v = sv_b.idxmax(0)
        v[~sv_b.iloc[-1,:]] = -1
    except:
        v = sv_b.argmax(0)
        v[~sv_b[-1,:]] = -1
    return v

def median_survival_times(survival_functions):
    return qth_survival_times(0.5, survival_functions)

def gaussian(t,T,sigma=1.):
    return 1./np.sqrt(np.pi*2.*sigma**2)*np.exp(-0.5*(t-T)**2/sigma)

def ipcw(target_event_times, target_censorship, predicted_event_times ):
    pass


def inv_normal_cdf(p):
    if p < 0.5:
      return -AandS_approximation(p)
    else:
      return AandS_approximation(1-p)

def AandS_approximation(p):
    #Formula 26.2.23 from A&S and help from John Cook ;)
    # http://www.johndcook.com/normal_cdf_inverse.html
    c_0 = 2.515517
    c_1 = 0.802853
    c_2 = 0.010328

    d_1 = 1.432788
    d_2 = 0.189269
    d_3 = 0.001308

    t = np.sqrt(-2*np.log(p))

    return t - (c_0+c_1*t+c_2*t**2)/(1+d_1*t+d_2*t*t+d_3*t**3)

"""
References:
[1] Aalen, O., Borgan, O., Gjessing, H., 2008. Survival and Event History Analysis

"""
