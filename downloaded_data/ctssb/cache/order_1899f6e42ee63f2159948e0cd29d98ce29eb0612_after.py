###############################################################################
# -*- coding: utf-8 -*-
# Order: A tool to characterize the local structure of liquid water 
#        by geometric order parameters
# 
# Authors: Pu Du
# 
# Released under the MIT License
###############################################################################

from __future__ import division, print_function
from six.moves import range

import numpy as np
from scipy.spatial import ConvexHull
from progress.bar import ChargingBar
from .util import pbc
from . import oto

class VoronoiCell(oto.Orientational):
    """asphericity of the Voronoi cell"""
    def __init__(self, filename, center, bins=100):
        super(VoronoiCell, self).__init__(filename, center, bins)
        self.Eta = np.zeros(bins+1)

    def polyhedron(self, c_coord, coords, L):
        """find the polyhedron for center molecule"""
        dist = np.zeros(self.traj.n_atoms, dtype=np.float)
        
        for i in range(self.traj.n_atoms):
                dx, dy, dz = coords[i] - c_coord

                #periodic boundary conditions
                dx, dy, dz = pbc(dx, dy, dz, L)

                dist[i] = np.sqrt(dx * dx + dy * dy + dz * dz)
        
        dist_sorted = sorted(enumerate(dist), key=lambda x:x[1])

        indexs = []
        for i in range(1, self.traj.n_atoms - 1):
            indexs.append(dist_sorted[i][0])
            if 2 * dist_sorted[i][1] < dist_sorted[i+1][1]:
                break
        
        points = []
        for index in indexs:
            dx, dy, dz = coords[index] - coords[i]

            #periodic boundary conditions
            dx, dy, dz = pbc(dx, dy, dz, L)

            point = np.array([dx, dy, dz])
            points.append(point)
        points = np.array(points, dtype=np.float)
        points += c_coord
        return points

    def compute_vc(self, points):
        """compute the Voronoi cell"""
        #total area of all planes
        S = 0.0

        #total volume of Voronoi polyhedron
        V = 0.0

        #compute S and V
        S = ConvexHull(points).area
        V = ConvexHull(points).volume

        #voronoi cell
        eta = S ** 3 / (36 * np.pi * V ** 2)

        return eta

    def asphericity(self, freq = 1):
        """compute asphericity of the Voronoi cell"""
        #progress bar
        frames = int(self.traj.n_frames / freq)
        bar = ChargingBar('Processing', max=frames, 
        suffix='%(percent).1f%% - %(eta)ds')

        for i in range(0, self.traj.n_frames, freq):
            for j in range(self.traj.n_atoms):
                if self.traj.atom_names[i][j] == self.center:
                    #center coordinate
                    c = self.traj.coords[i][j]
                    
                    #coordinates
                    cs = self.traj.coords[i]


                    L = self.traj.box_size[i]
                    points = self.polyhedron(c, cs, L)
                    e = self.compute_vc(points)
                    self.raw.append(e)
                    self.Eta[int(round(e * self.bins))] += 1
            bar.next()
        bar.finish()