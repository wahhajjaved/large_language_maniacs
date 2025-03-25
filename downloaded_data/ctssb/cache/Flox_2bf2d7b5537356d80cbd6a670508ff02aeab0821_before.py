# -*- coding: utf-8 -*-
# 
#  evolver.py
#  Flox
#  
#  Created by Alexander Rudy on 2014-06-01.
#  Copyright 2014 Alexander Rudy. All rights reserved.
# 

from __future__ import (absolute_import, unicode_literals, division, print_function)

from ..evolver._magneto import MagnetoEvolver as _MagnetoEvolver
from ..hydro.evolver import HydroBase

class MagnetoBase(HydroBase):
    """Base for magnetic fields"""
    
    def get_data_list(self):
        """docstring for get_data_list"""
        return super(MagnetoBase, self).get_data_list() + [ "VectorPotential", "dVectorPotential", "CurrentDensity" ]
        
    @classmethod
    def from_system(cls, system, **kwargs):
        """Create an evolver from a system."""
        ev = super(MagnetoBase, cls).from_system(system, **kwargs)
        ev.Q = system.nondimensionalize(system.Chandrasekhar).value
        ev.q = system.nondimensionalize(system.Roberts).value
        return ev
        
class MagnetoEvolver(MagnetoBase, _MagnetoEvolver):
    """Evolver with magnetic fields"""
    def __init__(self, *args, **kwargs):
        super(MagnetoEvolver, self).__init__(*args, **kwargs)        
        