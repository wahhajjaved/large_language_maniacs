"""Create publication-quality maps.
Copyright (C) 2011 Thomas Nauss

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Please send any comments, suggestions, criticism, or (for our sake) bug
reports to nausst@googlemail.com
"""

__author__ = "Thomas Nauss <nausst@googlemail.com>"
__version__ = "2010-08-07"
__license__ = "GNU GPL, see http://www.gnu.org/licenses/"

import numpy
import pylab
import math
from mpl_toolkits.basemap import Basemap
from matplotlib.mlab import griddata
from  julendat.processtools import eumeltools


class Data2Map(object):
    """Instance for creating publication-quality maps.
    
    The instance is a representation of a cartographic map object and includes
    the following functions:
        function compute_map_resolution: Compute grid dimension of the map to
            match desired map resolution
        function compress data: Compress dataset with respect to the
            latitude/longitude extension of the map and map the dataset to a
            regular grid.
        function plot_map: Create a publication-quality cartographic map in
            different DTP formats using the Basemap class from Jeffrey Whitaker  
    """

    def __init__(self, act_data, lat_data, lon_data, mapfile, 
                 map_resolution=10000, label=None,
                 lat_range=None, lon_range=None,
                 overlay_resolution='h', projection='tmerc',
                 lat_0=None, lon_0=None, 
                 parallels_interval=None, meridians_interval=None):
        """Inits Data2Map.
        
        Args:
            act_data : Numpy array holding the actual data values
            lat_data : Numpy array holding latitude dataset
            lon_data : Numpy array holding longigute dataset
            lat_range : Latitude range to be included into the map
            lon_range : Longitude range to be included into the map
            mapfile : String or tuple with full path of the output map file(s).
            map_resolution : Resolution of the map (defualt: 10000 m).
            label : Label for the map (default: none)
            overlay_resolution : Setting of the Basemap vector overlay
                ('c' for crude, 'l' for low, 'i' for intermediate,
                'h' for high, 'f' for full or None; default: 'h')
            projection : Map projection used for map creation
                ('aeqd' = Azimuthal Equidistant
                'poly' = Polyconic
                'gnom' = Gnomonic
                'moll' = Mollweide
                'tmerc' = Transverse Mercator
                'nplaea' = North-Polar Lambert Azimuthal
                'mill' = Miller Cylindrical
                'merc' = Mercator
                'stere' = Stereographic
                'npstere' = North-Polar Stereographic
                'geos' = Geostationary
                'laea' = Lambert Azimuthal Equal Area \
                'sinu' = Sinusoidal \
                'spstere' = South-Polar Stereographic \
                'lcc' = Lambert Conformal \
                'npaeqd' = North-Polar Azimuthal Equidistant \
                'eqdc' = Equidistant Conic \
                'cyl' = Cylindrical Equidistant \
                'omerc' = Oblique Mercator \
                'aea' = Albers Equal Area \
                'spaeqd' = South-Polar Azimuthal Equidistant \
                'ortho' = Orthographic \
                'cass' = Cassini-Soldner \
                'splaea' = South-Polar Lambert Azimuthal \
                'robin' = Robinson \
                 Default: 'tmerc'.)
            lat_0 : Center of the map in degrees (default: from lat_range)
            lon_0 : Center of the map in degrees (default: from lon_range)
            parallels_interval : Interval defining which parallel will be drawn
            meridians_interval : Interval defining which meridian will be drawn
        """
        self.data = act_data
        self.lat = lat_data
        self.lon = lon_data
        self.lat_range = lat_range
        self.lon_range = lon_range
        self.mapfile = mapfile
        if map_resolution is None:
            self.map_resolution = 10000
        else:
            self.map_resolution = map_resolution
        if label is None:
            self.label = ''
        else:
            self.label = label
        self.overlay_resolution = overlay_resolution
        self.projection = projection
        self.lat_0 = lat_0
        self.lon_0 = lon_0
        self.parallels_interval = parallels_interval    
        self.meridians_interval = meridians_interval
        self.lat_map_resolution = None
        self.lon_map_resolution = None

    def compute_mapgrid_resolution(self):
        """Computes number of cells in the regular map grid to match spatial
        desired resolution.
        """
        print 'Computing grid resolution of map...'
        grid_factor = math.cos(math.radians(
                               min(abs(self.lat_range[0]),
                                   abs(self.lat_range[1])))) * \
                      400240000.0 / 360.0 / self.map_resolution

        self.lat_map_resolution = int(abs(self.lat_range[0] - 
                                      self.lat_range[1]) * grid_factor)
        self.lon_map_resolution = int(abs(self.lon_range[0] - 
                                      self.lon_range[1]) * grid_factor)

    def compress_data(self):
        """Compresses data with respect to map latitude and longitude boundaries
        and map data to a regular grid.
        """
        print 'Arranging data to map latitude/longitude boundaries...'
        dummy, mask_lat, value_range = \
            eumeltools.mask_values(self.lat,
                                   self.lat_range)
        if self.lat_range is None:
            self.lat_range = value_range

        dummy, mask_lon, value_range = \
            eumeltools.mask_values(self.lon,
                                   self.lon_range)
        if self.lon_range is None:
            self.lon_range = value_range

        mask = numpy.logical_and(mask_lon,mask_lat)

        self.lat = numpy.ravel(self.lat)
        self.lat = numpy.compress(mask==1,self.lat)
        self.lon = numpy.ravel(self.lon)
        self.lon = numpy.compress(mask==1,self.lon)
        self.data = numpy.ravel(self.data)
        self.data = numpy.compress(mask==1,self.data)

        # If map grid resolution has not been computed yet, do it.
        if self.lat_map_resolution is None or self.lat_map_resolution is None:
            self.compute_mapgrid_resolution()

        # Map input data on regular grid.
        print 'Mapping data to regular grid...'
        lat_reg = numpy.linspace(self.lat_range[0], self.lat_range[1],
                                 self.lat_map_resolution)
        lon_reg = numpy.linspace(self.lon_range[0], self.lon_range[1],
                                 self.lon_map_resolution)
        self.data = griddata(self.lon, self.lat, self.data, 
                            lon_reg,lat_reg)
        self.lon, self.lat = numpy.meshgrid(lon_reg, lat_reg)

    def plot_map(self):
        """Creates a publication quality map using the Basemap class.
        """
        fig=pylab.figure()

        # Setup Basemap class
        if self.lat_0 is None:
            self.lat_0 = (self.lat_range[1] + self.lat_range[0]) / 2.0
        if self.lon_0 is None:
            self.lon_0 = (self.lon_range[1] + self.lon_range[0]) / 2.0 

        print 'Computing map with the following settings:'
        print 'Longitude range:           ', self.lon_range[0], \
                                             self.lon_range[1]
        print 'Latidute range:            ', self.lat_range[0], \
                                             self.lat_range[1]
        print 'Centre of map (lat/lon):   ', self.lat_0, self.lon_0
        print 'Grid resolution [m]:       ', self.map_resolution
        print 'Gridpoints in x direction: ', self.lon_map_resolution
        print 'Gridpoints in y direction: ', self.lat_map_resolution

        m = Basemap(self.lon_range[0], self.lat_range[0],
                    self.lon_range[1], self.lat_range[1],
                    self.overlay_resolution, self.projection,
                    self.lat_0,self.lon_0)

        ax = fig.add_axes([0.1,0.1,0.7,0.7])

        # Make a filled contour plot.
        x, y = m(self.lon, self.lat)
        CS = m.contourf(x,y,self.data,255,cmap= pylab.cm.jet)

        # Setup colorbar axes instance.
        pos = ax.get_position()
        l, b, w, h = pos.bounds
        cax = pylab.axes([l+w+0.075, b, 0.05, h]) # setup colorbar axes
        pylab.colorbar(drawedges=False, cax=cax) # draw colorbar
        pylab.axes(ax)  # make the original axes current again

        # Draw coastlines and political boundaries.
        m.drawcoastlines()
        m.drawmapboundary()
        #m.fillcontinents()

        # Draw parallels and meridians.
        if self.parallels_interval is None:
            self.parallels_interval = \
            int(abs(self.lat_range[0]-self.lat_range[1])/5.0)
        if self.meridians_interval is None:
            self.meridians_interval = \
            int(abs(self.lon_range[0]-self.lon_range[1])/5.0)
        parallels = numpy.arange(-90., 90, self.parallels_interval)
        m.drawparallels(parallels,labels=[1,0,0,0])
        meridians = numpy.arange(-180., 180., self.meridians_interval)
        m.drawmeridians(meridians,labels=[0,0,0,1])

        pylab.title(self.label)

        print 'Writing map to output file...'
        if isinstance(self.mapfile, str):
            pylab.savefig(self.mapfile)
        elif isinstance(self.mapfile, tuple):
            for filename in self.mapfile:
                pylab.savefig(filename)
