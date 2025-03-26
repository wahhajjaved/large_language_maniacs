#!python3
#
# Copyright (C) 2014 Julius Susanto
#
# PYPOWER-Dynamics is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# PYPOWER-Dynamics is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PYPOWER-Dynamics. If not, see <http://www.gnu.org/licenses/>.

"""
PYPOWER-Dynamics
Build modified Ybus matrix

"""

import numpy as np
from pypower.idx_bus import BUS_I, BUS_TYPE, PD, QD, GS, BS, BUS_AREA, \
    VM, VA, VMAX, VMIN, LAM_P, LAM_Q, MU_VMAX, MU_VMIN, REF


def mod_Ybus(Ybus, elements, bus, gen, baseMVA):
    # Add equivalent generator and grid admittances to Ybus matrix
    for element in elements.values():
        Ye = 0
        
        # 6th order machine
        if element.__module__ == 'sym_order6':
            i = gen[element.gen_no,0]
            Ye = 1 / (element.params['Ra'] + 1j * 0.5 * (element.params['Xdpp'] + element.params['Xqpp']))
        
        # 4th order machine
        if element.__module__ == 'sym_order4':
            i = gen[element.gen_no,0]
            Ye = 1 / (element.params['Ra'] + 1j * 0.5 * (element.params['Xdp'] + element.params['Xqp']))
        
        # External grid
        if element.__module__ == 'ext_grid':
            i = gen[element.gen_no,0]
            Ye = 1 / (1j * element.Xdp)
        
        if Ye != 0:
            Ybus[i,i] = Ybus[i,i] + Ye

    # Add equivalent load admittance to Ybus matrix
    Pl, Ql = bus[:, PD], bus[:, QD]
    for i in range(len(Pl)):
        S_load = np.complex(Pl[i],Ql[i]) / baseMVA
        y_load = S_load / bus[i, VM] ** 2
        Ybus[i,i] = Ybus[i,i] + y_load
    
    return Ybus