# -*- coding: utf-8 -*-
"""
Created on Wed Dec  3 08:56:09 2014

@author: kmratliff
"""
import numpy as np


def add_to_neighboring_cells(z, sub, inc, win=1):
    """Add a value to all neighboring cells.

    Parameters
    ----------
    z : ndarray
        2D array of values.
    sub : tuple of int
        Row/column subscripts into array.
    inc : float
        Value to increment *z* by.
    win : int
        Size of the window around *sub*.

    Examples
    --------
    >>> x = np.zeros((4, 5))
    >>> add_around_cell(x, (0, 0), 1)
    """
    z[max(0, sub[0] - win): min(z.shape[0], sub[0] + win + 1),
      max(0, sub[1] - win): min(z.shape[1], sub[1] + win + 1)] += inc


def dep_blanket(current_SL, blanket_rate, n, riv_i, riv_j, ch_depth):
    depo_flag = np.ones(n.shape, dtype=np.int)

    # don't deposit in the river course
    depo_flag[riv_i, riv_j] = 0

    # don't deposit if cell <= sea level
    # ASK BRAD ABOUT THIS (no cell is below SL right now)
    # but it might be when couple?? need to figure out if keeping up
    # with elevation RELATIVE to sea level or actual elevation??
    depo_flag[n <= current_SL] = 0

    # if cell elevation is above bankfull elev, don't deposit
    bankfull_elevation = n[riv_i, riv_j] + ch_depth
    for row in riv_i:
        depo_flag[row, n[row] > bankfull_elevation[row]] = 0

    # don't deposit on first two rows b/c inlet rise rate does that
    depo_flag[:2, :] = 0

    # deposit "blanket" deposition on qualified cells
    n[depo_flag == 1] += blanket_rate

    #dn_fp = depo_flag * blanket_rate

    #return n, dn_fp


def distance_to_river(y, y0):
    return np.absolute(y - y0)


def within_wetland(y, riv_ind, wetland_width=0.):
    dy = distance_to_river(y, y[riv_ind])
    is_wetland = dy < wetland_width
    is_wetland[riv_ind] = False
    return is_wetland


def wetlands(current_SL, WL_Z, wetland_width, n, riv_i, riv_j, x, y):
    depo_wetland = np.zeros(n.shape, dtype=np.int)

    for row, col in zip(riv_i, riv_j):
        dist = within_wetland(y[row], col, wetland_width=wetland_width)
        elev = n[row] < current_SL + WL_Z

        cols = dist & elev & (depo_wetland[row] == 0)

        before = n[row, cols].copy()
        n[row, cols] = current_SL + WL_Z
        wetland_dep = n[row, cols] - before

        depo_wetland[row, cols] == 1


def dep_splay(n, ij_fail, old_path, splay_dep, splay_type=1):
    """Deposit around a failed river cell.

    Parameters
    ----------
    n : ndarray
        Elevation array.
    ij_path : tuple of int
        Row and column of the river failure.
    old_path : tuple of array_like
        Row and column indices for the old river path.
    a : int
        River path index of the failure.
    splay_depth : float
        Deposition depth.
    splay_type : {1, 2}, optional
        Failure type

    USE DEPTH-DEPENDENCE IN THE FUTURE
        SE1 = (n[riv_x[a]/dx][riv_y[a]/dy] + ch_depth - \
                n[new_riv_x[a]/dx][new_riv_y[a]/dy]) / ch_depth

    ADD LARGER SPLAY TYPE IN FUTURE?
    (could be first two failed river cells + surrounding)

    This could possibly be improved by comparing to find nearest beach routine (CEM)
    or using some sort of search radius 
    """
    river_elevations = n[old_path]

    if splay_type == 1:  # splay deposition just at first failed river cell
        n[ij_fail] += splay_dep
    if splay_type == 2:     # splay deposition at first failed river cell
                            # and the adjacent cells
        add_to_neighboring_cells(n, ij_fail, splay_dep)

    n[old_path] = river_elevations
