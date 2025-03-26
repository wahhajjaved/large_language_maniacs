#!/usr/bin/env python3

import numpy as np
import argparse
import sys,math
sys.path.append(sys.path[0] + '/..')

import growthclasses as gc
from scipy.stats import poisson
import itertools

def func_xexp(ax1,ax2,params):
    m1,m2  = gc.getInoculumMatrices(ax1,ax2)
    n      = m1 + m2
    x      = np.zeros(np.shape(n))
    x[n>0] = m1[n>0]/n[n>0]
    
    return x * np.exp(-params['expconst'] * x)

def func_x(ax1,ax2,params):
    m1,m2  = gc.getInoculumMatrices(ax1,ax2)
    n      = m1 + m2
    x      = np.zeros(np.shape(n))
    x[n>0] = m1[n>0]/n[n>0]
    
    return x
    
def func_exp(ax1,ax2,params):
    m1,m2  = gc.getInoculumMatrices(ax1,ax2)
    n      = m1 + m2
    x      = np.zeros(np.shape(n))
    x[n>0] = m1[n>0]/n[n>0]
    
    return np.exp(-params['expconst'] * x)
    

def main():

    parser = argparse.ArgumentParser()
    parser_param = parser.add_argument_group(description = "==== Parameters ====")
    parser_param.add_argument("-s","--yieldinc",default=2,type=float)
    parser_param.add_argument("-c","--expconst",default=1,type=float)
    parser_param.add_argument("-m","--maxpoisson",default=100,type=int)

    parser = gc.AddLatticeParameters(parser)
    args   = parser.parse_args()
    
    
    
    axis1,axis2 = gc.getInoculumAxes(**vars(args))
    shape       = (len(axis1),len(axis2))
    m           = np.arange(args.maxpoisson)
    xw1         = np.zeros(shape)
    params      = {   'sigma':      args.yieldinc,
                      'expconst':   args.expconst }

    for i,a1 in enumerate(axis1):
        for j,a2 in enumerate(axis2):
            inoc  = gc.TransformInoculum([a1,a2],inabs = args.AbsoluteCoordinates, outabs = True)
            Exexp = gc.SeedingAverage(func_xexp(m,m,params), inoc)
            Ex    = gc.SeedingAverage(func_x   (m,m,params), inoc)
            Eexp  = gc.SeedingAverage(func_exp (m,m,params), inoc)
            
            xw1[i,j] = (Exexp - Ex * Eexp) / (params['sigma']/(params['sigma']-1) - Eexp)
            
            print("{:14.6e} {:14.6e} {:14.6e}".format(a1,a2,xw1[i,j]))
        print("")

if __name__ == "__main__":
    main()






