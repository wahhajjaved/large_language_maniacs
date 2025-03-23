def gen_explicit_RK(f, h, ti, tf, yi, Q, a):
    '''
    Computes an ODE using explicit Runge Kutta method.
    
    Input:
    - (f)  The function dy/dt of the initial value problem
    - (h)  Step size
    - (ti) Initial time
    - (tf) Final time
    - (yi) Initial y value
    - (Q)  The matrix from the Butchers tableau
    - (a)  The bottom row of the Butchers tableau
    
    Output:
    - (t) Time steps
    - (y) Solutions
    
    To use the "Classic" RK4 method Q and a would be:
    Q = np.array([[0   ,    0, 0, 0],
                  [1./2,    0, 0, 0],
                  [   0, 1./2, 0, 0],
                  [   0,    0, 1, 0]])

    a = np.array([1./6, 1./3, 1./3, 1./6])
    '''
    steps = int((tf-t0)/h) + 1
    y = np.zeros(steps)
    t = np.zeros(steps)
    y[0] = yi
    t[0] = ti
    
    p = np.sum(Q, axis=1)
    
    for i in range(steps - 1):
        k = np.zeros(len(p))
        for j in range(len(k)):
            k[j] = f(t[i] + h*p[j], y[i] + h*(np.dot(Q[j], k)))
        y[i+1] = y[i] + h*np.dot(a, k)
        t[i+1] = t[i] + h
        
    return t, y
