"""numerical differentiation function, gradient, Jacobian, and Hessian

Author : josef-pkt
License : BSD
"""

#These are simple forward differentiation, so that we have them available
#without dependencies.
#
#* Jacobian should be faster than numdifftools because it doesn't use loop over observations.
#* numerical precision will vary and depend on the choice of stepsizes
#
#Todo:
#* some cleanup
#* check numerical accuracy (and bugs) with numdifftools and analytical derivatives
#  - linear least squares case: (hess - 2*X'X) is 1e-8 or so
#  - gradient and Hessian agree with numdifftools when evaluated away from minimum
#  - forward gradient, Jacobian evaluated at minimum is inaccurate, centered (+/- epsilon) is ok
#* dot product of Jacobian is different from Hessian, either wrong example or a bug (unlikely),
#  or a real difference
#
#
#What are the conditions that Jacobian dotproduct and Hessian are the same?
#see also:
#BHHH: Greene p481 17.4.6,  MLE Jacobian = d loglike / d beta , where loglike is vector for each observation
#   see also example 17.4 when J'J is very different from Hessian
#   also does it hold only at the minimum, what's relationship to covariance of Jacobian matrix
#http://projects.scipy.org/scipy/ticket/1157
#http://en.wikipedia.org/wiki/Levenberg%E2%80%93Marquardt_algorithm
#   objective: sum((y-f(beta,x)**2),   Jacobian = d f/d beta   and not d objective/d beta as in MLE Greene
#   similar: http://crsouza.blogspot.com/2009/11/neural-network-learning-by-levenberg_18.html#hessian
#
#in example: if J = d x*beta / d beta then J'J == X'X
#   similar to http://en.wikipedia.org/wiki/Levenberg%E2%80%93Marquardt_algorithm
import numpy as np

#NOTE: we only do double precision internally so far
EPS = np.MachAr().eps

def approx_fprime(x, f, epsilon=1e-12, args=(), centered=False):
    '''
    Gradient of function, or Jacobian if function f returns 1d array

    Parameters
    ----------
    x : array
        parameters at which the derivative is evaluated
    f : function
        `*((x,)+args)` returning either one value or 1d array
    epsilon : float
        stepsize
    args : tuple
        tuple of additional arguments for function f
    centered : bool
        Whether central difference should be returned. If not, does forward
        differencing.

    Returns
    -------
    grad : array
        gradient or Jacobian

    Notes
    -----
    If f returns a 1d array, it returns a Jacobian. If a 2d array is returned
    by f (e.g., with a value for each observation), it returns a 3d array
    with the Jacobian of each observation with shape xk x nobs x xk. I.e.,
    the Jacobian of the first observation would be [:, 0, :]
    '''
    #TODO:  add scaled stepsize
    f0 = f(*((x,)+args))
    dim = np.atleast_1d(f0).shape # it could be a scalar
    grad = np.zeros((len(x),) + dim, float)
    ei = np.zeros((len(x),), float)
    if not centered:
        for k in range(len(x)):
            ei[k] = epsilon
            grad[k,:] = (f(*((x+ei,)+args)) - f0)/epsilon
            ei[k] = 0.0
    else:
        for k in range(len(x)):
            ei[k] = epsilon/2.
            grad[k,:] = (f(*((x+ei,)+args)) - f(*((x-ei,)+args)))/epsilon
            ei[k] = 0.0
    return grad.squeeze().T

def approx_hess(x, f, epsilon=None, args=()):
    '''calculate Hessian with finite difference derivative approximation

    Parameters
    ----------
    x : array_like
       value at which function derivative is evaluated
    f : function
       function of one array f(x)
    epsilon : float
       stepsize, if None, then stepsize is automatically chosen

    Returns
    -------
    hess : ndarray
       array of partial second derivatives, Hessian

    Notes
    -----
    based on equation 9 in
    M. S. RIDOUT: Statistical Applications of the Complex-step Method
    of Numerical Differentiation, University of Kent, Canterbury, Kent, U.K.

    The stepsize is the same for the complex and the finite difference part.
    '''

    if epsilon is None:
        h = EPS**(1/5.)*np.maximum(np.abs(x),1e-2) # 1/4 from ...
    else:
        h = epsilon
    xh = x + h
    h = xh - x
    ee = np.diag(h)
    hess = np.outer(h,h)

    n = dim = np.size(x) #TODO: What's the assumption on the shape here?

    for i in range(n):
        for j in range(i,n):
            hess[i,j] = (f(*((x + ee[i,:] + ee[j,:],)+args))
                            - f(*((x + ee[i,:] - ee[j,:],)+args))
                         - (f(*((x - ee[i,:] + ee[j,:],)+args))
                            - f(*((x - ee[i,:] - ee[j,:],)+args)))
                         )/4./hess[i,j]
            hess[j,i] = hess[i,j]

    return hess

def approx_fhess_p(x, p, fprime, epsilon, *args):
    """
    Approximate the Hessian when the Jacobian is available.

    Parameters
    ----------
    x : array-like
        Point at which to evaluate the Hessian
    p : array-like
        Point
    fprime : func
        The Jacobian function
    epsilon : float

    """
    f2 = fprime(*((x+epsilon*p,)+args))
    f1 = fprime(*((x,)+args))
    return (f2 - f1)/epsilon

def approx_fprime_cs(x, f, args=(), h=1.0e-20):
    '''
    Calculate gradient or Jacobian with complex step derivative approximation

    Parameters
    ----------
    f : function
       function of one array f(x)
    x : array_like
       value at which function derivative is evaluated

    Returns
    -------
    partials : ndarray
       array of partial derivatives, Gradient or Jacobian
    '''
    #From Guilherme P. de Freitas, numpy mailing list
    #May 04 2010 thread "Improvement of performance"
    #http://mail.scipy.org/pipermail/numpy-discussion/2010-May/050250.html
    dim = np.size(x) #TODO: What's the assumption on the shape here?
    increments = np.identity(dim) * 1j * h
    #TODO: see if this can be vectorized, but usually dim is small
    partials = [f(x+ih, *args).imag / h for ih in increments]
    return np.array(partials).T

def approx_hess_cs(x, f, epsilon=None, args=()):
    '''calculate Hessian with complex step (and fd) derivative approximation

    Parameters
    ----------
    x : array_like
       value at which function derivative is evaluated
    f : function
       function of one array f(x)
    epsilon : float
       stepsize, if None, then stepsize is automatically chosen

    Returns
    -------
    hess : ndarray
       array of partial second derivatives, Hessian

    Notes
    -----
    based on equation 10 in
    M. S. RIDOUT: Statistical Applications of the Complex-step Method
    of Numerical Differentiation, University of Kent, Canterbury, Kent, U.K.

    The stepsize is the same for the complex and the finite difference part.
    '''

    if epsilon is None: #NOTE: isn't the recomendation 1/3.?
        h = EPS**(1/5.)*np.maximum(np.abs(x),1e-2) # 1/4 from ...
    else:
        h = epsilon
    xh = x + h
    h = xh - x
    ee = np.diag(h)
    hess = np.outer(h,h)

    n = dim = np.size(x) #TODO: What's the assumption on the shape here?

    for i in range(n):
        for j in range(i,n):
            hess[i,j] = (f(*((x + 1j*ee[i,:] + ee[j,:],)+args))
                - f(*((x + 1j*ee[i,:] - ee[j,:],)+args))).imag/2./hess[i,j]
            hess[j,i] = hess[i,j]

    return hess


if __name__ == '__main__': #pragma : no cover
    import statsmodels.api as sm
    from scipy.optimize.optimize import approx_fhess_p
    import numpy as np

    data = sm.datasets.spector.load()
    data.exog = sm.add_constant(data.exog)
    mod = sm.Probit(data.endog, data.exog)
    res = mod.fit(method="newton")
    test_params = [1,0.25,1.4,-7]
    llf = mod.loglike
    score = mod.score
    hess = mod.hessian

    # below is Josef's scratch work

    #NOTE: this is the old version of approx_hess here for posterity
    def approx_hess_old(x, f, epsilon=None, args=(), retgrad=True):
        '''
        Calculate Hessian and Gradient by forward differentiation

        Parameters
        ----------
        x
        f
        epsilon
        args
        retgrad

        Returns
        -------
        '''
        if epsilon is None:  #check
            step = None
        else:
            step = epsilon  #TODO: shouldn't be here but I need to figure out args

        # Compute the stepsize (h)
        if step is None:  #check
            h = EPS**(1/3.)*np.maximum(np.abs(x),1e-2)
        else:
            h = step
        xh = x + h
        h = xh - x
        ee = np.diag(h.ravel())

        f0 = f(*((x,)+args))
        # Compute forward step
        n = len(x)
        g = np.zeros(n);
        for i in range(n):
            g[i] = f(*((x+ee[i,:],)+args))

        hess = np.outer(h,h)
        # Compute "double" forward step
        for i in range(n):
            for j in range(i,n):
                hess[i,j] = (f(*((x+ee[i,:]+ee[j,:],)+args))-g[i]-g[j]+f0)/hess[i,j]
                hess[j,i] = hess[i,j]
        if retgrad:
            grad = (g - f0)/h
            return hess, grad
        else:
            return hess


    def approx_hess_cs_old(x, func, args=(), h=1.0e-20, epsilon=1e-6):
        def grad(x):
            return approx_fprime_cs(x, func, args=args, h=1.0e-20)

        #Hessian from gradient:
        return (approx_fprime(x, grad, epsilon)
                + approx_fprime(x, grad, -epsilon))/2.


    def fun(beta, x):
        return np.dot(x, beta).sum(0)

    def fun1(beta, y, x):
        #print beta.shape, x.shape
        xb = np.dot(x, beta)
        return (y-xb)**2 #(xb-xb.mean(0))**2

    def fun2(beta, y, x):
        #print beta.shape, x.shape
        return fun1(beta, y, x).sum(0)

    nobs = 200
    x = np.arange(nobs*3).reshape(nobs,-1)
    x = np.random.randn(nobs,3)

    xk = np.array([1,2,3])
    xk = np.array([1.,1.,1.])
    #xk = np.zeros(3)
    beta = xk
    y = np.dot(x, beta) + 0.1*np.random.randn(nobs)
    xk = np.dot(np.linalg.pinv(x),y)


    epsilon = 1e-6
    args = (y,x)
    from scipy import optimize
    xfmin = optimize.fmin(fun2, (0,0,0), args)
    print approx_fprime((1,2,3),fun,epsilon,x)
    jac = approx_fprime(xk,fun1,epsilon,args)
    jacmin = approx_fprime(xk,fun1,-epsilon,args)
    #print jac
    print jac.sum(0)
    print '\nnp.dot(jac.T, jac)'
    print np.dot(jac.T, jac)
    print '\n2*np.dot(x.T, x)'
    print 2*np.dot(x.T, x)
    jac2 = (jac+jacmin)/2.
    print np.dot(jac2.T, jac2)

    #he = approx_hess(xk,fun2,epsilon,*args)
    print approx_hess_old(xk,fun2,1e-3,args)
    he = approx_hess_old(xk,fun2,None,args)
    print 'hessfd'
    print he
    print 'epsilon =', None
    print he[0] - 2*np.dot(x.T, x)

    for eps in [1e-3,1e-4,1e-5,1e-6]:
        print 'eps =', eps
        print approx_hess_old(xk,fun2,eps,args)[0] - 2*np.dot(x.T, x)

    hcs2 = approx_hess_cs(xk,fun2,args=args)
    print 'hcs2'
    print hcs2 - 2*np.dot(x.T, x)

    hfd3 = approx_hess(xk,fun2,args=args)
    print 'hfd3'
    print hfd3 - 2*np.dot(x.T, x)

    import numdifftools as nd
    hnd = nd.Hessian(lambda a: fun2(a, y, x))
    hessnd = hnd(xk)
    print 'numdiff'
    print hessnd - 2*np.dot(x.T, x)
    #assert_almost_equal(hessnd, he[0])
    gnd = nd.Gradient(lambda a: fun2(a, y, x))
    gradnd = gnd(xk)
