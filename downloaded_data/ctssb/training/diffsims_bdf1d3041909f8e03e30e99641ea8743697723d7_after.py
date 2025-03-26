# -*- coding: utf-8 -*-
# Copyright 2017-2019 The diffsims developers
#
# This file is part of diffsims.
#
# diffsims is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# diffsims is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with diffsims.  If not, see <http://www.gnu.org/licenses/>.

import pytest
import numpy as np
from diffsims.generators.rotation_list_generators import get_local_grid, get_grid_around_beam_direction,get_fundemental_zone_grid
from diffsims.utils.rotation_conversion_utils import Euler


@pytest.mark.parametrize("center",[(0.0,0.0,0.0),(0.0,10.0,0.0)])
def test_get_local_grid(center):
    grid = get_local_grid(center,10,2)
    assert isinstance(grid,list)
    assert isinstance(grid[0],tuple)
    assert center in grid
    center_plus_2 = (center[0],center[1],center[2]+2)
    assert center_plus_2 in grid

@pytest.mark.skip(reason="functionality under discussion")
def test_get_grid_around_beam_direction():
    grid_simple = get_grid_around_beam_direction([1,1,1],1,(0, 360))
    assert isinstance(grid_simple,list)
    assert isinstance(grid_simple[0],tuple)
    assert len(grid_simple) == 360

@pytest.mark.parametrize("space_group_number",[1,3,30,190,215,229])
def test_get_fundemental_zone_grid(space_group_number):
    grid = get_fundemental_zone_grid(space_group_number,resolution=3)


@pytest.mark.skip(reason="This tests a theoretical underpinning of the code")
def test_small_angle_shortcut(): #pragma: no cover
    """ Demonstrates that cutting larger 'out of plane' in euler space doesn't
    effect the result """

    def process_angles(raw_angles, max_rotation):
        raw_angles = raw_angles.to_AxAngle()
        raw_angles.remove_large_rotations(np.deg2rad(max_rotation))
        return raw_angles

    max_rotation = 20
    lsa = create_linearly_spaced_array_in_rzxz(2)
    alsa = _create_advanced_linearly_spaced_array_in_rzxz(2,360,max_rotation+10,360)

    long_true_way = process_angles(lsa, max_rotation)
    quick_way = process_angles(alsa, max_rotation)

    assert long_true_way.data.shape == quick_way.data.shape
