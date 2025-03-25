"""Holds the algorithms to perform replica exchange.

Algorithms implemented by Robert Meissner and Riccardo Petraglia, 2016
"""

# This file is part of i-PI.
# i-PI Copyright (C) 2014-2016 i-PI developers
# See the "licenses" directory for full license information.


import numpy as np
import time

from ipi.engine.smotion import Smotion
from ipi.engine.ensembles import ensemble_swap
from ipi.utils.depend import *
from ipi.utils.softexit import softexit
from ipi.utils.messages import verbosity, info



__all__ = ['ReplicaExchange']


# TODO: Do not shout :-)
#       (1) Exchange of Hamiltonians is missing

class ReplicaExchange(Smotion):
    """Replica exchange routine.

    Attributes:
        every: on which steps REMD should be performed
        exchange:
            temperature: activate temperature replica exchange
            hamiltonian: activate hamiltonian replica exchange
            bias: activate hamiltonian replica exchange ***not yet implemented
    """

    def __init__(self, stride=1.0, repindex = None):
        """Initialises REMD.

        Args:

        """

        super(ReplicaExchange, self).__init__()

        self.swapfile = "PARATEMP" #!TODO make this an option!
        self.rescalekin = True  #!TODO make this an option!
        # replica exchange options
        self.stride = stride
        
        #! TODO ! allow saving and storing the replica indices
        self.repindex = repindex

    def bind(self, syslist, prng):

        super(ReplicaExchange,self).bind(syslist, prng)
        
        if self.repindex is None:
            self.repindex = np.asarray(range(len(self.syslist)))
        else:
            if len(self.syslist) != len(self.repindex):
                raise ValueError("Size of replica index does not match number of systems replicas")

    def step(self, step=None):
        """Tries to exchange replica."""
        
        if self.stride <= 0.0: return
        
        info("\nTrying to exchange replicas on STEP %d" % step, verbosity.debug)

        fxc = False
        sl = self.syslist        
        for i in range(len(sl)):
           for j in range(i):
              if (1.0/self.stride < self.prng.u) : continue  # tries a swap with probability 1/stride
              ti = sl[i].ensemble.temp
              tj = sl[j].ensemble.temp
              eci = sl[i].ensemble.econs
              ecj = sl[j].ensemble.econs
              pensi = sl[i].ensemble.lpens
              pensj = sl[j].ensemble.lpens
              print i, j, "APotentials: ", sl[i].forces.pot, sl[j].forces.pot, "Temp: ", sl[i].ensemble.temp, sl[j].ensemble.temp
              
              ensemble_swap(sl[i].ensemble, sl[j].ensemble)  # tries to swap the ensembles!
              
              # it is generally a good idea to rescale the kinetic energies,
              # which means that the exchange is done only relative to the potential energy part.
              if self.rescalekin: 
                  # also rescales the velocities -- should do the same with cell velocities 
                  sl[i].beads.p *= np.sqrt(tj/ti)
                  sl[j].beads.p *= np.sqrt(ti/tj)
                  try: # if motion has a barostat, and barostat has a momentum, does the swap
                      # also note that the barostat has a hidden T dependence inside the mass, so 
                      # as a matter of fact <p^2> \propto T^2                  
                      sl[i].motion.barostat.p *= (tj/ti)
                      sl[j].motion.barostat.p *= (ti/tj)
                  except AttributeError:
                      pass

              newpensi = sl[i].ensemble.lpens
              newpensj = sl[j].ensemble.lpens
              
              print i, j, "BPotentials: ", sl[i].forces.pot, sl[j].forces.pot, "Temp: ", sl[i].ensemble.temp, sl[j].ensemble.temp
                            
              pxc = np.exp((newpensi+newpensj)-(pensi+pensj))
              print pensi, pensj, " --> ", newpensi, newpensj, " == ", pxc


              if (pxc > self.prng.u): # really does the exchange
                  info(" @ PT:  SWAPPING replicas % 5d and % 5d." % (i,j), verbosity.low)     
                  # we just have to carry on with the swapped ensembles, but we also keep track of the changes in econs
                  sl[i].ensemble.eens += eci - sl[i].ensemble.econs
                  sl[j].ensemble.eens += ecj - sl[j].ensemble.econs
                  self.repindex[i], self.repindex[j] = self.repindex[j], self.repindex[i] # keeps track of the swap
                  
                  fxc = True # signal that an exchange has been made!          
              else: # undoes the swap
                  ensemble_swap(sl[i].ensemble, sl[j].ensemble)
                  
                  if self.rescalekin:
                      sl[i].beads.p *= np.sqrt(ti/tj)
                      sl[j].beads.p *= np.sqrt(tj/ti)                  
                      try:
                          sl[i].motion.barostat.p *= (ti/tj)
                          sl[j].motion.barostat.p *= (tj/ti)
                      except AttributeError:
                          pass
                  info(" @ PT:  SWAP REJECTED BETWEEN replicas % 5d and % 5d." % (i,j), verbosity.low)
                 
                 #tempi = copy(self.syslist[i].ensemble.temp)
                 
                 #self.syslist[i].ensemble.temp = copy(self.syslist[j].ensemble.temp)
                 # velocities have to be adjusted according to the new temperature
        
        if fxc: # writes out the new status
            with open(self.swapfile,"a") as sf:
                 sf.write("% 10d" % (step))
                 for i in self.repindex:
                     sf.write(" % 5d" % (i))
                 sf.write("\n") 
