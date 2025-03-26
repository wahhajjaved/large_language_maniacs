import numpy as np
import scipy.constants as const
import matplotlib as matlib
matlib.use('Agg')                    # This allows the standalone application to plot and save figs.
import matplotlib.pyplot as mplot
from pylab import *
import Laser
import Ionization as Ion
import SpaceSolver
import Plasmaunit as punit
from datetime import datetime

#%% Full propagation! With W1 and W2
def main():    

    # Define the length and size of the simulation window. Units are in dt and dz respectively.
    TIME = 400
    SIZE = 2000
    dim = [TIME,SIZE]
    
    # Initialise the various fields to be calculated
    E = np.zeros(SIZE)
    Etemp = np.zeros(SIZE)
    B = np.zeros(SIZE)
    J = np.zeros(SIZE)
    n = np.zeros(SIZE)
    ntemp = np.zeros(SIZE)
    W1 = np.zeros(SIZE)
    W2 = np.zeros(SIZE)

    Ni1 = np.zeros(SIZE)
    Ni1tot = np.zeros(dim)
    Ni1temp = np.zeros(SIZE)
    Ni0 = np.ones(SIZE)
    Ni0tot = np.zeros(dim)
    Ni0temp = np.zeros(SIZE)

    ne = np.zeros(SIZE)
    netemp = np.zeros(SIZE)

    Etot = np.zeros(dim)
    Btot = np.zeros(dim)
    Jtot = np.zeros(dim)
    ntot = np.zeros(dim)
    W1tot = np.zeros(dim)
    netot = np.zeros(dim)
    plott = np.arange(TIME)
    plotz = np.arange(SIZE)
    
    dt = 0.1        # Time step
    dz = 0.1        # Spatial step. dt = dz is the magic step using plasma units
    nu = 0           # Collision rate

    # Parameters for laser pulse.
    c = const.speed_of_light
    epsilon = const.epsilon_0 
    LAMBDA = 800e-9 
    f = c/LAMBDA
    PULSELENGTH = 1000
    PULSESTART = 0
    OMEGAREAL = 2*np.pi*f
    OMEGAPRIM = 2                       # this is the plasma omega, use this everywhere in the code
    OMEGA_0 = OMEGAREAL/OMEGAPRIM       # this is the arbitrary omega, use this as argument in punits
    t0REAL = 50e-15 
    I0 = 4e18 
    E0REAL = np.sqrt(2*I0/(epsilon*c))
    E0 = punit.Eplasma(E0REAL,OMEGA_0)
    t0 = punit.tplasma(t0REAL,OMEGA_0)
    Laser.Gauss_forward(E,B,E0,PULSELENGTH,PULSESTART,OMEGAPRIM,t0,dt)
    
    # Parameters for the atomdensity
    NatREAL = 3e25 
    Nat = punit.nplasma(NatREAL,OMEGA_0)
    Nat = np.ones(SIZE)*Nat

    # Defines the lenght which we allow the gas to be ionized
    PLASMASTART = 50
    PLASMASTOPP = 100
    
    print(str(datetime.now())+': Beginning simulation.')
    for i in range(1,TIME):

        E = SpaceSolver.E(E,B,J,dt,dz)
        B = SpaceSolver.B(E,B,dt,dz)

        for z in range(len(E)):
            if abs(E[z]) == 0:
                W1[z] = 0
                W2[z] = 0
            else:
                if z > PLASMASTART and z < PLASMASTOPP:
                    W1[z] = Ion.Landau(E[z],OMEGA_0,1,dt)
                    W2[z] = Ion.Landau(E[z],OMEGA_0,2,dt)
                else:
                    W1[z] = 0
                    W2[z] = 0

        for z in range(len(E)):
            Ni0[z] = Nat[z]-Ni1[z]
            Ni1[z] = (Ni1[z]*(1-(dt/2)*W2[z])+(dt/2)*W1[z]*(Ni0[z]+Ni0temp[z]))/(1+(dt/2)*W2[z])
            ne[z] = 1*Ni1[z]
            Ni0temp[z] = Ni0[z]

        J = SpaceSolver.J(E,J,ne,ntemp,nu,dt,dz)
        netemp = ne

        Etot[i] = E
        Jtot[i] = J
        W1tot[i] = W1
        netot[i] = ne
        Ni0tot[i] = Ni0
        Ni1tot[i] = Ni1
    print(str(datetime.now())+': Simulation complete.')
    z = np.arange(len(Etot[0]))
    plotnsave(z, Etot[100], '', 'etot.png')
    mplot.clf()
    
    t = np.arange(TIME)

#%%
def plotnsave(x, y, args, filename):
    print(str(datetime.now())+': Beginning plot.')
    mplot.plot(x, y, args)
    if filename:
        mplot.savefig(filename)
        print(str(datetime.now())+ ': Plot saved.')
        np.savetxt(filename, y, delimiter=',')
    else:
        print(str(datetime.now())+': Plot complete.')
    

def energy_total_1d(F):
    if np.ndim(F) == 0:
        print('Field seems to be a scalar. Please make sure it\'s a vector.')
        print('Error in energy_total_1d')
        return 0
    elif np.ndim(F) > 1:
        print('Field seems to be a matrix. Please make sure it\'s a vector.')
        print('Error in energy_total_1d')
        return 0
    else:
        return np.sum(F**2)/2
    
# plotz = np.arange(SIZE)
# plott = np.arange(TIME)

# t = 500
# z = 100
# mplot.plot(plotz,Etot[t]*1,'b')
# #mplot.plot(k,W1tot[t]*1e-2)
# mplot.plot(plotz,netot[t]*1,'r')
# mplot.plot(plotz,Jtot[t]*300,'y')
#mplot.plot(plott,Etot[:,300])
#mplot.plot(plott,W1tot[:,20])
#mplot.plot(plott,Ni1tot[:,z])

#%%

# Eefter = Etot[0:1500,2*PULSELENGTH+10]
# #plotz = np.arange(len(Eefter))
# #mplot.plot(plotz,Eefter)
# Efft = np.fft.fft(Eefter)
# mplot.plot(plotz,np.abs(Efft))
# Efore = Etot[0:1500,PULSELENGTH-1]
# plotz = np.arange(len(Efore))
# Efft = np.fft.fft(Efore)
# mplot.plot(plotz,np.abs(Efft))

# #%% Real units

# nreal = Plasmaunit.nreal(n[200],OMEGAUNIT)
# print(nreal)
# omegareal = Plasmaunit.omegareal(OMEGA,OMEGAUNIT)
# print(omegareal)

if __name__ == '__main__':
    main()
