"""
cclib is a parser for computational chemistry log files.

See http://cclib.sf.net for more information.

Copyright (C) 2006 Noel O'Boyle and Adam Tenderholt

 This program is free software; you can redistribute and/or modify it
 under the terms of the GNU General Public License as published by the
 Free Software Foundation; either version 2, or (at your option) any later
 version.

 This program is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY, without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 General Public License for more details.

Contributions (monetary as well as code :-) are encouraged.
"""
import re,time
import Numeric
import random # For sometimes running the progress updater
import logging

from calculationmethod import Method

class Population(Method):
    """A base class for all population-type methods"""
    def __init__(self,parser,progress=None, \
                 loglevel=logging.INFO,logname="Log"):

        # Call the __init__ method of the superclass
        super(Population, self).__init__(parser,progress,loglevel,logname)
        self.fragresults=None
        
    def __str__(self):
        """Return a string representation of the object."""
        return "Population"

    def __repr__(self):
        """Return a representation of the object."""
        return "Population"
    

#create array for mulliken charges
        self.logger.info("Creating atomcharges: array[1]")
        size=len(self.atomresults[0][0])
        self.atomcharges=Numeric.zeros([size],"f")
        
        for spin in range(len(self.atomresults)):

            for i in range(self.parser.homos[spin]+1):

                temp=Numeric.reshape(self.atomresults[spin][i],(size,))
                self.atomcharges=Numeric.add(self.atomcharges,temp)
        
        if not unrestricted:
            self.atomcharges=Numeric.multiply(self.atomcharges,2)

        return True

    def partition(self,indices=None):

        if not hasattr(self,"aoresults"):
            self.calculate()

        if not indices:
#build list of groups of orbitals in each atom for atomresults
            if hasattr(self.parser,"aonames"):
                names=self.parser.aonames
            elif hasattr(self.parser,"fonames"):
                names=self.parser.fonames

            atoms=[]
            indices=[]

            name=names[0].split('_')[0]
            atoms.append(name)
            indices.append([0])

            for i in range(1,len(names)):
                name=names[i].split('_')[0]
                try:
                    index=atoms.index(name)
                except ValueError: #not found in atom list
                    atoms.append(name)
                    indices.append([i])
                else:
                    indices[index].append(i)

        natoms=len(indices)
        nmocoeffs=len(self.aoresults[0])
        
#build results Numeric array[3]
        if len(self.aoresults)==2:
            results=Numeric.zeros([2,nmocoeffs,natoms],"f")
        else:
            results=Numeric.zeros([1,nmocoeffs,natoms],"f")
        
#for each spin, splice Numeric array at ao index, and add to correct result row
        for spin in range(len(results)):

            for i in range(natoms): #number of groups

                for j in range(len(indices[i])): #for each group
                
                    temp=self.aoresults[spin,:,indices[i][j]]
                    results[spin,:,i]=Numeric.add(results[spin,:,i],temp)

        self.logger.info("Saving partitioned results in fragresults: array[3]")
        self.fragresults=results

        return True

if __name__=="__main__":
    import doctest,mpa
    doctest.testmod(mpa,verbose=False)
